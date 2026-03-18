from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable

from ..connector_runtime import format_conversation_id, parse_conversation_id
from ..shared import append_jsonl, ensure_dir, read_json, utc_now, write_json


class WhatsAppLocalSessionService:
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
        self._root = home / "logs" / "connectors" / "whatsapp"
        if self.profile_id:
            self._root = self._root / "profiles" / self.profile_id
        self._runtime_path = self._root / "runtime.json"
        self._cursor_path = self._root / "local_session.cursor.json"

    def start(self) -> bool:
        enabled = bool(self.config.get("enabled", False))
        transport = str(self.config.get("transport") or "local_session").strip().lower()
        session_dir = self._session_dir()
        if not enabled:
            self._write_state(
                enabled=False,
                transport="local_session",
                connected=False,
                connection_state="disabled",
                auth_state="disabled",
                updated_at=utc_now(),
            )
            return False
        if transport != "local_session":
            return False
        if not session_dir:
            self._write_state(
                enabled=True,
                transport="local_session",
                connected=False,
                connection_state="needs_credentials",
                auth_state="missing_configuration",
                updated_at=utc_now(),
            )
            return False
        ensure_dir(session_dir)
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name=f"deepscientist-whatsapp-local-session-{self.profile_id or 'default'}",
        )
        self._thread.start()
        return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        session_dir = self._session_dir()
        self._write_state(
            enabled=True,
            transport="local_session",
            connected=False,
            connection_state="configured",
            auth_state="configured",
            session_dir=str(session_dir) if session_dir else None,
            updated_at=utc_now(),
        )
        while not self._stop_event.wait(1.0):
            try:
                self._sync_runtime(session_dir)
                self._drain_inbox(session_dir)
            except Exception as exc:
                self.log("warning", f"whatsapp.local_session: sync failed: {exc}")
                self._write_state(
                    connected=False,
                    connection_state="error",
                    auth_state="error",
                    last_error=str(exc),
                    updated_at=utc_now(),
                )
        self._write_state(
            connected=False,
            connection_state="stopped",
            updated_at=utc_now(),
        )

    def _sync_runtime(self, session_dir: Path | None) -> None:
        if session_dir is None:
            return
        source = read_json(session_dir / "runtime.json", {}) or {}
        if not isinstance(source, dict):
            source = {}
        connected = bool(source.get("connected", False))
        authenticated = bool(source.get("authenticated", False))
        connection_state = str(source.get("connection_state") or ("connected" if connected else "configured")).strip()
        auth_state = str(source.get("auth_state") or ("ready" if authenticated else "configured")).strip()
        patch = {
            "enabled": True,
            "transport": "local_session",
            "connected": connected,
            "connection_state": connection_state or "configured",
            "auth_state": auth_state or "configured",
            "session_dir": str(session_dir),
            "last_error": source.get("last_error"),
            "updated_at": utc_now(),
        }
        for key in ("account_id", "phone_number", "display_name", "qr_code", "qr_updated_at"):
            if key in source:
                patch[key] = source.get(key)
        self._write_state(**patch)

    def _drain_inbox(self, session_dir: Path | None) -> None:
        if session_dir is None:
            return
        inbox_path = session_dir / "inbox.jsonl"
        if not inbox_path.exists():
            return
        cursor = read_json(self._cursor_path, {}) or {}
        offset = int((cursor or {}).get("offset") or 0)
        with inbox_path.open("r", encoding="utf-8") as handle:
            handle.seek(offset)
            while True:
                line = handle.readline()
                if not line:
                    break
                offset = handle.tell()
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    append_jsonl(self._root / "local_session.ignored.jsonl", {"received_at": utc_now(), "raw": line})
                    continue
                if not isinstance(payload, dict):
                    continue
                normalized = self._normalize_entry(payload)
                if normalized is None:
                    append_jsonl(self._root / "local_session.ignored.jsonl", {"received_at": utc_now(), "raw": payload})
                    continue
                self.on_event(normalized)
                self._write_state(
                    connected=True,
                    connection_state="connected",
                    auth_state="ready",
                    last_event_at=utc_now(),
                    last_conversation_id=normalized.get("conversation_id"),
                    updated_at=utc_now(),
                )
        write_json(self._cursor_path, {"offset": offset})

    def _normalize_entry(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if isinstance(payload.get("normalized"), dict):
            normalized = dict(payload["normalized"])
            normalized.setdefault("raw_event", payload)
            parsed = parse_conversation_id(normalized.get("conversation_id"))
            chat_type = str((parsed or {}).get("chat_type") or normalized.get("chat_type") or "direct").strip().lower() or "direct"
            chat_id = str((parsed or {}).get("chat_id") or normalized.get("group_id") or normalized.get("direct_id") or "").strip() or "unknown"
            normalized["conversation_id"] = self._conversation_id(chat_type, chat_id)
            normalized["profile_id"] = self.profile_id
            normalized["profile_label"] = self.profile_label
            return normalized
        conversation_id = str(payload.get("conversation_id") or "").strip()
        chat_type = str(payload.get("chat_type") or "").strip().lower()
        chat_id = str(payload.get("chat_id") or payload.get("jid") or payload.get("peer_id") or "").strip()
        sender_id = str(payload.get("sender_id") or payload.get("sender") or payload.get("from") or "").strip()
        if conversation_id:
            parts = conversation_id.split(":", 2)
            if len(parts) == 3:
                if not chat_type:
                    chat_type = parts[1]
                if not chat_id:
                    chat_id = parts[2]
        if not chat_type:
            if chat_id.endswith("@g.us"):
                chat_type = "group"
            else:
                chat_type = "direct"
        if not chat_id:
            chat_id = sender_id
        text = str(payload.get("text") or payload.get("body") or payload.get("message") or payload.get("content") or "").strip()
        if not text or not chat_id:
            return None
        sender_name = str(payload.get("sender_name") or payload.get("pushName") or payload.get("notify_name") or sender_id).strip()
        message_id = str(payload.get("message_id") or payload.get("id") or "").strip()
        return {
            "chat_type": chat_type,
            "group_id": chat_id if chat_type == "group" else "",
            "direct_id": chat_id if chat_type == "direct" else sender_id,
            "sender_id": sender_id or chat_id,
            "sender_name": sender_name or sender_id or chat_id,
            "message_id": message_id,
            "conversation_id": self._conversation_id(chat_type, chat_id),
            "profile_id": self.profile_id,
            "profile_label": self.profile_label,
            "text": text,
            "mentioned": False,
            "raw_event": payload,
        }

    def _conversation_id(self, chat_type: str, chat_id: str) -> str:
        return format_conversation_id(
            "whatsapp",
            chat_type,
            chat_id,
            profile_id=self.profile_id if self._encode_profile_id else None,
        )

    def _session_dir(self) -> Path | None:
        raw = str(self.config.get("session_dir") or "").strip()
        if not raw:
            return None
        return Path(raw).expanduser().resolve()

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
