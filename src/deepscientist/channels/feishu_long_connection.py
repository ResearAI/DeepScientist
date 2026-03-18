from __future__ import annotations

import asyncio
import contextlib
import json
import threading
from importlib import import_module
from pathlib import Path
from typing import Any, Callable

from ..bridges.connectors import FeishuConnectorBridge
from ..connector_runtime import format_conversation_id, parse_conversation_id
from ..shared import read_json, utc_now, write_json


class _FeishuEventHandler:
    def __init__(self, service: "FeishuLongConnectionService") -> None:
        self.service = service

    def do_without_validation(self, payload: bytes) -> None:
        self.service._handle_sdk_payload(payload)
        return None


class FeishuLongConnectionService:
    def __init__(
        self,
        *,
        home: Path,
        config: dict[str, Any],
        on_event: Callable[[dict[str, Any]], None],
        log: Callable[[str, str], None] | None = None,
        profile_id: str | None = None,
        profile_label: str | None = None,
        encode_profile_id: bool = False,
    ) -> None:
        self.home = home
        self.config = config
        self.on_event = on_event
        self.log = log or self._default_log
        self.profile_id = str(profile_id or "").strip() or None
        self.profile_label = str(profile_label or "").strip() or None
        self._encode_profile_id = bool(encode_profile_id and self.profile_id)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._async_stop: asyncio.Event | None = None
        self._client: Any = None
        self._root = home / "logs" / "connectors" / "feishu"
        if self.profile_id:
            self._root = self._root / "profiles" / self.profile_id
        self._runtime_path = self._root / "runtime.json"

    def start(self) -> bool:
        enabled = bool(self.config.get("enabled", False))
        transport = str(self.config.get("transport") or "long_connection").strip().lower()
        app_id = str(self.config.get("app_id") or "").strip()
        app_secret = self._secret("app_secret", "app_secret_env")
        if not enabled:
            self._write_state(
                enabled=False,
                transport="long_connection",
                connected=False,
                connection_state="disabled",
                auth_state="disabled",
                updated_at=utc_now(),
            )
            return False
        if transport != "long_connection":
            return False
        if not (app_id and app_secret):
            self._write_state(
                enabled=True,
                transport="long_connection",
                connected=False,
                connection_state="needs_credentials",
                auth_state="missing_credentials",
                updated_at=utc_now(),
            )
            return False
        if self._sdk_bundle() is None:
            self._write_state(
                enabled=True,
                transport="long_connection",
                connected=False,
                connection_state="needs_dependency",
                auth_state="missing_dependency",
                updated_at=utc_now(),
            )
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name=f"deepscientist-feishu-long-connection-{self.profile_id or 'default'}",
        )
        self._thread.start()
        return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        loop = self._loop
        async_stop = self._async_stop
        if loop is not None and async_stop is not None:
            loop.call_soon_threadsafe(async_stop.set)
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._loop = None
        self._async_stop = None
        self._client = None

    def _run(self) -> None:
        sdk = self._sdk_bundle()
        if sdk is None:
            return
        client_module = sdk["client_module"]
        client_cls = sdk["client_cls"]
        log_level = sdk["log_level"]
        handler = _FeishuEventHandler(self)
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        client_module.loop = loop
        stop_signal = asyncio.Event()
        self._async_stop = stop_signal
        app_id = str(self.config.get("app_id") or "").strip()
        app_secret = self._secret("app_secret", "app_secret_env")
        domain = str(self.config.get("api_base_url") or "https://open.feishu.cn").rstrip("/")

        async def runner() -> None:
            backoff_seconds = 1.0
            self._write_state(
                enabled=True,
                transport="long_connection",
                connected=False,
                connection_state="starting",
                auth_state="ready",
                updated_at=utc_now(),
            )
            while not stop_signal.is_set():
                ping_task: asyncio.Task[Any] | None = None
                try:
                    client = client_cls(
                        app_id=app_id,
                        app_secret=app_secret,
                        log_level=log_level.INFO,
                        event_handler=handler,
                        domain=domain,
                        auto_reconnect=False,
                    )
                    self._client = client
                    await client._connect()
                    ping_task = loop.create_task(client._ping_loop())
                    self._write_state(
                        connected=True,
                        connection_state="connected",
                        auth_state="ready",
                        last_error=None,
                        updated_at=utc_now(),
                    )
                    while not stop_signal.is_set():
                        await asyncio.sleep(0.5)
                        if getattr(client, "_conn", None) is None:
                            raise ConnectionError("Feishu long connection closed.")
                    break
                except Exception as exc:
                    if stop_signal.is_set():
                        break
                    self.log("warning", f"feishu.long_connection: reconnecting after error: {exc}")
                    self._write_state(
                        connected=False,
                        connection_state="error",
                        auth_state="ready",
                        last_error=str(exc),
                        updated_at=utc_now(),
                    )
                    await asyncio.sleep(backoff_seconds)
                    backoff_seconds = min(backoff_seconds * 2.0, 30.0)
                finally:
                    if ping_task is not None:
                        ping_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await ping_task
                    client = self._client
                    if client is not None and getattr(client, "_conn", None) is not None:
                        with contextlib.suppress(Exception):
                            await client._disconnect()
                    self._client = None
            self._write_state(
                connected=False,
                connection_state="stopped",
                updated_at=utc_now(),
            )

        try:
            loop.run_until_complete(runner())
        finally:
            loop.close()

    def _handle_sdk_payload(self, payload: bytes) -> None:
        data = json.loads(payload.decode("utf-8"))
        result = FeishuConnectorBridge().parse_webhook(
            method="POST",
            headers={},
            query={},
            raw_body=payload,
            body=data,
            config=self.config,
        )
        for event in result.events:
            normalized = self._normalize_event(event)
            self.on_event(normalized)
            self._write_state(
                connected=True,
                connection_state="connected",
                auth_state="ready",
                last_event_at=utc_now(),
                last_conversation_id=normalized.get("conversation_id"),
                updated_at=utc_now(),
            )

    def _normalize_event(self, event: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(event)
        chat_type = str(normalized.get("chat_type") or "direct").strip().lower() or "direct"
        group_id = str(normalized.get("group_id") or "").strip()
        direct_id = str(normalized.get("direct_id") or "").strip()
        chat_id = group_id if chat_type == "group" else direct_id
        if not chat_id:
            parsed = parse_conversation_id(normalized.get("conversation_id"))
            if parsed is not None:
                chat_type = str(parsed.get("chat_type") or chat_type).strip().lower() or chat_type
                chat_id = str(parsed.get("chat_id") or "").strip()
        normalized["conversation_id"] = self._conversation_id(chat_type, chat_id or "unknown")
        normalized["profile_id"] = self.profile_id
        normalized["profile_label"] = self.profile_label
        return normalized

    def _conversation_id(self, chat_type: str, chat_id: str) -> str:
        return format_conversation_id(
            "feishu",
            chat_type,
            chat_id,
            profile_id=self.profile_id if self._encode_profile_id else None,
        )

    @staticmethod
    def _sdk_bundle() -> dict[str, Any] | None:
        try:
            client_module = import_module("lark_oapi.ws.client")
            enum_module = import_module("lark_oapi.core.enum")
        except ImportError:
            return None
        return {
            "client_module": client_module,
            "client_cls": getattr(client_module, "Client"),
            "log_level": getattr(enum_module, "LogLevel"),
        }

    def _secret(self, key: str, env_key: str) -> str:
        direct = str(self.config.get(key) or "").strip()
        if direct:
            return direct
        env_name = str(self.config.get(env_key) or "").strip()
        if not env_name:
            return ""
        from os import environ

        return str(environ.get(env_name) or "").strip()

    def _write_state(self, **patch: Any) -> None:
        state = read_json(self._runtime_path, {}) or {}
        if not isinstance(state, dict):
            state = {}
        if self.profile_id:
            state["profile_id"] = self.profile_id
        if self.profile_label:
            state["profile_label"] = self.profile_label
        state.update(patch)
        write_json(self._runtime_path, state)

    @staticmethod
    def _default_log(level: str, message: str) -> None:
        print(f"[{level}] {message}")
