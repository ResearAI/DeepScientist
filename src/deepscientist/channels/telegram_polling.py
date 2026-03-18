from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

from ..connector_runtime import format_conversation_id
from ..shared import read_json, utc_now, write_json


class TelegramPollingService:
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
        self._root = home / "logs" / "connectors" / "telegram"
        if self.profile_id:
            self._root = self._root / "profiles" / self.profile_id
        self._runtime_path = self._root / "runtime.json"

    def start(self) -> bool:
        enabled = bool(self.config.get("enabled", False))
        transport = str(self.config.get("transport") or "polling").strip().lower()
        token = self._token()
        if not enabled:
            self._write_state(
                enabled=False,
                transport="polling",
                connected=False,
                connection_state="disabled",
                auth_state="disabled",
                updated_at=utc_now(),
            )
            return False
        if transport != "polling":
            return False
        if not token:
            self._write_state(
                enabled=True,
                transport="polling",
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
            name=f"deepscientist-telegram-polling-{self.profile_id or 'default'}",
        )
        self._thread.start()
        return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def is_enabled(self) -> bool:
        return (
            bool(self.config.get("enabled", False))
            and str(self.config.get("transport") or "polling").strip().lower() == "polling"
            and bool(self._token())
        )

    def _run(self) -> None:
        backoff_seconds = 1.0
        state = read_json(self._runtime_path, {}) or {}
        offset = int((state or {}).get("update_offset") or 0)
        token = self._token()
        self._write_state(
            enabled=True,
            transport="polling",
            connected=False,
            connection_state="starting",
            auth_state="ready" if token else "missing_credentials",
            started_at=utc_now(),
            updated_at=utc_now(),
        )
        if not token:
            self._write_state(
                connected=False,
                connection_state="needs_credentials",
                auth_state="missing_credentials",
                updated_at=utc_now(),
            )
            return
        try:
            self._prepare_polling(token)
            self._write_state(
                auth_state="ready",
                connection_state="configured",
                last_error=None,
                updated_at=utc_now(),
            )
        except Exception as exc:
            self.log("warning", f"telegram.polling: failed to prepare polling: {exc}")
            self._write_state(
                connected=False,
                connection_state="error",
                auth_state="error",
                last_error=str(exc),
                updated_at=utc_now(),
            )
            return
        while not self._stop_event.is_set():
            try:
                offset = self._poll_once(token, offset=offset)
                backoff_seconds = 1.0
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                self.log("warning", f"telegram.polling: reconnecting after error: {exc}")
                self._write_state(
                    connected=False,
                    connection_state="error",
                    auth_state="ready",
                    last_error=str(exc),
                    updated_at=utc_now(),
                )
                self._stop_event.wait(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2.0, 30.0)
        self._write_state(
            connected=False,
            connection_state="stopped",
            updated_at=utc_now(),
        )

    def _prepare_polling(self, token: str) -> None:
        # Clear any stale webhook so long polling can take over without a public callback URL.
        self._bot_api_json(
            token,
            "deleteWebhook",
            payload={"drop_pending_updates": False},
            timeout=10.0,
        )

    def _poll_once(self, token: str, *, offset: int) -> int:
        payload = self._bot_api_json(
            token,
            "getUpdates",
            payload={
                "timeout": 25,
                "offset": max(offset, 0),
                "allowed_updates": ["message", "edited_message", "channel_post"],
            },
            timeout=35.0,
        )
        if not payload.get("ok", False):
            raise ValueError(payload.get("description") or "Telegram getUpdates failed.")
        results = payload.get("result") if isinstance(payload.get("result"), list) else []
        next_offset = offset
        self._write_state(
            transport="polling",
            connected=True,
            connection_state="connected",
            auth_state="ready",
            last_error=None,
            updated_at=utc_now(),
        )
        for item in results:
            if not isinstance(item, dict):
                continue
            update_id = item.get("update_id")
            if isinstance(update_id, int):
                next_offset = max(next_offset, update_id + 1)
            normalized = self._normalize_update(item)
            if normalized is None:
                continue
            self.on_event(normalized)
            self._write_state(
                last_event_at=utc_now(),
                last_conversation_id=normalized.get("conversation_id"),
                updated_at=utc_now(),
            )
        if next_offset != offset:
            self._write_state(update_offset=next_offset, updated_at=utc_now())
        return next_offset

    def _normalize_update(self, update: dict[str, Any]) -> dict[str, Any] | None:
        message = update.get("message") or update.get("edited_message") or update.get("channel_post")
        if not isinstance(message, dict):
            return None
        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        sender = message.get("from") if isinstance(message.get("from"), dict) else {}
        text = str(message.get("text") or message.get("caption") or "").strip()
        if not text:
            return None
        chat_type_raw = str(chat.get("type") or "private").strip().lower()
        chat_type = "direct" if chat_type_raw == "private" else "group"
        chat_id = str(chat.get("id") or "").strip()
        sender_id = str(sender.get("id") or "").strip()
        sender_name = str(sender.get("username") or sender.get("first_name") or sender_id).strip()
        entities = []
        for key in ("entities", "caption_entities"):
            values = message.get(key)
            if isinstance(values, list):
                entities.extend(item for item in values if isinstance(item, dict))
        mentioned = any(item.get("type") == "mention" for item in entities)
        bot_name = str(self.config.get("bot_name") or "DeepScientist").strip()
        normalized_text = self._normalize_command_target(text, bot_name=bot_name)
        return {
            "chat_type": chat_type,
            "group_id": chat_id if chat_type == "group" else "",
            "direct_id": chat_id if chat_type == "direct" else sender_id,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "message_id": str(message.get("message_id") or "").strip(),
            "conversation_id": self._conversation_id(chat_type, chat_id),
            "profile_id": self.profile_id,
            "profile_label": self.profile_label,
            "text": normalized_text,
            "mentioned": mentioned,
            "raw_event": update,
        }

    def _conversation_id(self, chat_type: str, chat_id: str) -> str:
        return format_conversation_id(
            "telegram",
            chat_type,
            chat_id,
            profile_id=self.profile_id if self._encode_profile_id else None,
        )

    @staticmethod
    def _normalize_command_target(text: str, *, bot_name: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned.startswith("/"):
            return cleaned
        first, *rest = cleaned.split(maxsplit=1)
        command = first
        if "@" in command:
            prefix, _, target = command.partition("@")
            normalized_target = target.strip().lower()
            normalized_name = bot_name.strip().lower()
            if not normalized_target or normalized_target == normalized_name:
                command = prefix
        suffix = rest[0] if rest else ""
        return f"{command} {suffix}".strip()

    def _token(self) -> str:
        direct = str(self.config.get("bot_token") or "").strip()
        if direct:
            return direct
        env_name = str(self.config.get("bot_token_env") or "").strip()
        if not env_name:
            return ""
        from os import environ

        return str(environ.get(env_name) or "").strip()

    @staticmethod
    def _bot_api_json(
        token: str,
        method: str,
        *,
        payload: dict[str, Any] | None = None,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        url = f"https://api.telegram.org/bot{token}/{method}"
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(url, data=body, method="POST" if body is not None else "GET")
        if body is not None:
            request.add_header("Content-Type", "application/json; charset=utf-8")
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))

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
