from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect as websocket_connect

from ..connector_runtime import format_conversation_id
from ..shared import read_json, utc_now, write_json


class SlackSocketModeService:
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
        self._connection = None
        self._root = home / "logs" / "connectors" / "slack"
        if self.profile_id:
            self._root = self._root / "profiles" / self.profile_id
        self._runtime_path = self._root / "runtime.json"

    def start(self) -> bool:
        enabled = bool(self.config.get("enabled", False))
        transport = str(self.config.get("transport") or "socket_mode").strip().lower()
        bot_token = self._secret("bot_token", "bot_token_env")
        app_token = self._secret("app_token", "app_token_env")
        if not enabled:
            self._write_state(
                enabled=False,
                transport="socket_mode",
                connected=False,
                connection_state="disabled",
                auth_state="disabled",
                updated_at=utc_now(),
            )
            return False
        if transport != "socket_mode":
            return False
        if not (bot_token and app_token):
            self._write_state(
                enabled=True,
                transport="socket_mode",
                connected=False,
                connection_state="needs_credentials",
                auth_state="missing_credentials",
                updated_at=utc_now(),
            )
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name=f"deepscientist-slack-socket-mode-{self.profile_id or 'default'}",
        )
        self._thread.start()
        return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        connection = self._connection
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._connection = None

    def _run(self) -> None:
        backoff_seconds = 1.0
        bot_token = self._secret("bot_token", "bot_token_env")
        app_token = self._secret("app_token", "app_token_env")
        self._write_state(
            enabled=True,
            transport="socket_mode",
            connected=False,
            connection_state="starting",
            auth_state="ready" if bot_token and app_token else "missing_credentials",
            updated_at=utc_now(),
        )
        while not self._stop_event.is_set():
            try:
                identity = self._auth_test(bot_token)
                bot_user_id = str(self.config.get("bot_user_id") or identity.get("user_id") or "").strip()
                socket_info = self._socket_open(app_token)
                socket_url = str(socket_info.get("url") or "").strip()
                if not socket_url:
                    raise ValueError(str(socket_info.get("error") or "Slack apps.connections.open did not return a websocket URL."))
                self._write_state(
                    auth_state="ready",
                    connection_state="connecting",
                    socket_url=socket_url,
                    bot_user_id=bot_user_id or None,
                    identity=identity.get("user"),
                    team_id=identity.get("team_id"),
                    last_error=None,
                    updated_at=utc_now(),
                )
                with websocket_connect(socket_url, open_timeout=10, close_timeout=5, ping_interval=20, ping_timeout=20) as connection:
                    self._connection = connection
                    self._consume_connection(connection, bot_user_id=bot_user_id)
                backoff_seconds = 1.0
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                self.log("warning", f"slack.socket_mode: reconnecting after error: {exc}")
                self._write_state(
                    connected=False,
                    connection_state="error",
                    auth_state="ready" if bot_token and app_token else "missing_credentials",
                    last_error=str(exc),
                    updated_at=utc_now(),
                )
                self._stop_event.wait(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2.0, 30.0)
            finally:
                self._connection = None
        self._write_state(
            connected=False,
            connection_state="stopped",
            updated_at=utc_now(),
        )

    def _consume_connection(self, connection: Any, *, bot_user_id: str) -> None:
        while not self._stop_event.is_set():
            try:
                payload = self._recv_payload(connection, timeout=1.0)
            except TimeoutError:
                continue
            except ConnectionClosed:
                return
            self._handle_payload(payload, connection=connection, bot_user_id=bot_user_id)

    def _handle_payload(self, payload: dict[str, Any], *, connection: Any, bot_user_id: str) -> None:
        payload_type = str(payload.get("type") or "").strip()
        envelope_id = str(payload.get("envelope_id") or "").strip()
        if envelope_id:
            connection.send(json.dumps({"envelope_id": envelope_id}))
        if payload_type == "hello":
            self._write_state(
                connected=True,
                connection_state="connected",
                auth_state="ready",
                last_error=None,
                updated_at=utc_now(),
            )
            return
        if payload_type == "disconnect":
            raise EOFError("Slack Socket Mode requested reconnect.")
        normalized = None
        if payload_type == "events_api":
            event_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
            normalized = self._normalize_events_api(event_payload, bot_user_id=bot_user_id)
        elif payload_type == "slash_commands":
            command_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
            normalized = self._normalize_slash_command(command_payload)
        if normalized is None:
            return
        self.on_event(normalized)
        self._write_state(
            connected=True,
            connection_state="connected",
            auth_state="ready",
            last_event_at=utc_now(),
            last_conversation_id=normalized.get("conversation_id"),
            updated_at=utc_now(),
        )

    def _normalize_events_api(self, payload: dict[str, Any], *, bot_user_id: str) -> dict[str, Any] | None:
        event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
        if not isinstance(event, dict):
            return None
        event_type = str(event.get("type") or "").strip()
        if event_type not in {"message", "app_mention"}:
            return None
        if event.get("subtype") in {"bot_message", "message_deleted", "message_changed"}:
            return None
        if event.get("bot_id"):
            return None
        text = str(event.get("text") or "").strip()
        if not text:
            return None
        channel_id = str(event.get("channel") or "").strip()
        channel_type = str(event.get("channel_type") or self._infer_channel_type(channel_id)).strip().lower()
        chat_type = "direct" if channel_type == "im" else "group"
        sender_id = str(event.get("user") or "").strip()
        mentioned = event_type == "app_mention" or self._contains_bot_mention(text, bot_user_id)
        normalized_text = self._strip_bot_mention(text, bot_user_id)
        return {
            "chat_type": chat_type,
            "group_id": channel_id if chat_type == "group" else "",
            "direct_id": channel_id if chat_type == "direct" else sender_id,
            "sender_id": sender_id,
            "sender_name": str(event.get("username") or sender_id).strip(),
            "message_id": str(event.get("ts") or event.get("event_ts") or "").strip(),
            "conversation_id": self._conversation_id(chat_type, channel_id),
            "profile_id": self.profile_id,
            "profile_label": self.profile_label,
            "text": normalized_text,
            "mentioned": mentioned,
            "raw_event": payload,
        }

    def _normalize_slash_command(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        channel_id = str(payload.get("channel_id") or "").strip()
        if not channel_id:
            return None
        command = str(payload.get("command") or "").strip()
        text = str(payload.get("text") or "").strip()
        combined = f"{command} {text}".strip()
        channel_name = str(payload.get("channel_name") or "").strip().lower()
        chat_type = "direct" if channel_name in {"directmessage", "im"} or channel_id.startswith("D") else "group"
        sender_id = str(payload.get("user_id") or "").strip()
        return {
            "chat_type": chat_type,
            "group_id": channel_id if chat_type == "group" else "",
            "direct_id": channel_id if chat_type == "direct" else sender_id,
            "sender_id": sender_id,
            "sender_name": str(payload.get("user_name") or sender_id).strip(),
            "message_id": str(payload.get("trigger_id") or "").strip(),
            "conversation_id": self._conversation_id(chat_type, channel_id),
            "profile_id": self.profile_id,
            "profile_label": self.profile_label,
            "text": combined,
            "mentioned": True,
            "raw_event": payload,
        }

    def _conversation_id(self, chat_type: str, chat_id: str) -> str:
        return format_conversation_id(
            "slack",
            chat_type,
            chat_id,
            profile_id=self.profile_id if self._encode_profile_id else None,
        )

    @staticmethod
    def _infer_channel_type(channel_id: str) -> str:
        if str(channel_id).startswith("D"):
            return "im"
        return "channel"

    @staticmethod
    def _contains_bot_mention(text: str, bot_user_id: str) -> bool:
        normalized_user_id = str(bot_user_id or "").strip()
        if not normalized_user_id:
            return False
        return f"<@{normalized_user_id}>" in str(text or "")

    @staticmethod
    def _strip_bot_mention(text: str, bot_user_id: str) -> str:
        cleaned = str(text or "").strip()
        normalized_user_id = str(bot_user_id or "").strip()
        if not normalized_user_id:
            return cleaned
        prefix = f"<@{normalized_user_id}>"
        if cleaned.startswith(prefix):
            return cleaned[len(prefix):].strip()
        return cleaned

    def _auth_test(self, bot_token: str) -> dict[str, Any]:
        payload = self._http_json(
            "https://slack.com/api/auth.test",
            method="POST",
            headers={"Authorization": f"Bearer {bot_token}"},
        )
        if not payload.get("ok", False):
            raise ValueError(str(payload.get("error") or "Slack auth.test failed."))
        return payload

    def _socket_open(self, app_token: str) -> dict[str, Any]:
        payload = self._http_json(
            "https://slack.com/api/apps.connections.open",
            method="POST",
            headers={"Authorization": f"Bearer {app_token}"},
        )
        if not payload.get("ok", False):
            raise ValueError(str(payload.get("error") or "Slack apps.connections.open failed."))
        return payload

    @staticmethod
    def _recv_payload(connection: Any, *, timeout: float) -> dict[str, Any]:
        raw = connection.recv(timeout=timeout)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    @staticmethod
    def _http_json(
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        encoded = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = Request(url, data=encoded, method=method)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        if encoded is not None:
            request.add_header("Content-Type", "application/json; charset=utf-8")
        with urlopen(request, timeout=10) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))

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
