from __future__ import annotations

import json
import platform
import threading
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect as websocket_connect

from ..connector_runtime import format_conversation_id
from ..shared import read_json, utc_now, write_json


DISCORD_GATEWAY_INTENTS = (1 << 0) | (1 << 9) | (1 << 12) | (1 << 15)


class DiscordGatewayService:
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
        self._heartbeat_stop = threading.Event()
        self._connection = None
        self._session_id: str | None = None
        self._seq: int | None = None
        self._bot_user_id: str | None = None
        self._root = home / "logs" / "connectors" / "discord"
        if self.profile_id:
            self._root = self._root / "profiles" / self.profile_id
        self._runtime_path = self._root / "runtime.json"

    def start(self) -> bool:
        enabled = bool(self.config.get("enabled", False))
        transport = str(self.config.get("transport") or "gateway").strip().lower()
        token = self._token()
        if not enabled:
            self._write_state(
                enabled=False,
                transport="gateway",
                connected=False,
                connection_state="disabled",
                auth_state="disabled",
                updated_at=utc_now(),
            )
            return False
        if transport != "gateway":
            return False
        if not token:
            self._write_state(
                enabled=True,
                transport="gateway",
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
            name=f"deepscientist-discord-gateway-{self.profile_id or 'default'}",
        )
        self._thread.start()
        return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        self._heartbeat_stop.set()
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
        token = self._token()
        self._write_state(
            enabled=True,
            transport="gateway",
            connected=False,
            connection_state="starting",
            auth_state="ready" if token else "missing_credentials",
            updated_at=utc_now(),
        )
        while not self._stop_event.is_set():
            try:
                gateway_url = self._gateway_url(token)
                self._write_state(
                    auth_state="ready",
                    connection_state="connecting",
                    gateway_url=gateway_url,
                    last_error=None,
                    updated_at=utc_now(),
                )
                with websocket_connect(gateway_url, open_timeout=10, close_timeout=5, ping_interval=None) as connection:
                    self._connection = connection
                    self._consume_connection(connection, token=token, gateway_url=gateway_url)
                backoff_seconds = 1.0
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                self.log("warning", f"discord.gateway: reconnecting after error: {exc}")
                self._write_state(
                    connected=False,
                    connection_state="error",
                    auth_state="ready" if token else "missing_credentials",
                    last_error=str(exc),
                    updated_at=utc_now(),
                )
                self._stop_event.wait(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2.0, 30.0)
            finally:
                self._heartbeat_stop.set()
                self._connection = None
        self._write_state(
            connected=False,
            connection_state="stopped",
            updated_at=utc_now(),
        )

    def _consume_connection(self, connection: Any, *, token: str, gateway_url: str) -> None:
        hello = self._recv_payload(connection, timeout=10.0)
        if hello.get("op") != 10:
            raise ValueError(f"Expected Discord gateway hello op=10, got {hello.get('op')!r}.")
        self._heartbeat_stop.clear()
        heartbeat_interval_ms = int(((hello.get("d") or {}).get("heartbeat_interval") or 45000))
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(connection, heartbeat_interval_ms / 1000.0),
            daemon=True,
            name="deepscientist-discord-heartbeat",
        )
        heartbeat_thread.start()
        self._send_handshake(connection, token)
        self._write_state(
            connected=True,
            connection_state="connecting",
            auth_state="ready",
            gateway_url=gateway_url,
            last_error=None,
            updated_at=utc_now(),
        )
        try:
            while not self._stop_event.is_set():
                try:
                    payload = self._recv_payload(connection, timeout=1.0)
                except TimeoutError:
                    continue
                self._handle_payload(payload)
        except EOFError:
            return
        except ConnectionClosed:
            return
        finally:
            self._heartbeat_stop.set()
            heartbeat_thread.join(timeout=1.0)

    def _heartbeat_loop(self, connection: Any, interval_seconds: float) -> None:
        interval = max(interval_seconds, 1.0)
        while not self._heartbeat_stop.wait(interval):
            if self._stop_event.is_set():
                return
            try:
                connection.send(json.dumps({"op": 1, "d": self._seq}))
            except Exception:
                return

    def _send_handshake(self, connection: Any, token: str) -> None:
        if self._session_id and self._seq is not None:
            payload = {
                "op": 6,
                "d": {
                    "token": token,
                    "session_id": self._session_id,
                    "seq": self._seq,
                },
            }
        else:
            payload = {
                "op": 2,
                "d": {
                    "token": token,
                    "intents": DISCORD_GATEWAY_INTENTS,
                    "properties": {
                        "os": platform.system().lower() or "linux",
                        "browser": "deepscientist",
                        "device": "deepscientist",
                    },
                },
            }
        connection.send(json.dumps(payload))

    def _handle_payload(self, payload: dict[str, Any]) -> None:
        seq = payload.get("s")
        if isinstance(seq, int):
            self._seq = seq
        op = payload.get("op")
        event_type = str(payload.get("t") or "").strip()
        data = payload.get("d") if isinstance(payload.get("d"), dict) else {}
        if op == 11:
            return
        if op == 7:
            raise EOFError("Discord gateway requested reconnect.")
        if op == 9:
            resumable = bool(payload.get("d"))
            if not resumable:
                self._session_id = None
                self._seq = None
            raise EOFError("Discord gateway invalid session.")
        if op != 0:
            return
        if event_type == "READY":
            self._session_id = str(data.get("session_id") or "").strip() or None
            user = data.get("user") if isinstance(data.get("user"), dict) else {}
            self._bot_user_id = str(user.get("id") or "").strip() or None
            self._write_state(
                connected=True,
                connection_state="connected",
                auth_state="ready",
                session_id=self._session_id,
                bot_user_id=self._bot_user_id,
                identity=str(user.get("username") or "").strip() or None,
                last_error=None,
                updated_at=utc_now(),
            )
            return
        if event_type == "RESUMED":
            self._write_state(
                connected=True,
                connection_state="connected",
                auth_state="ready",
                resumed_at=utc_now(),
                updated_at=utc_now(),
            )
            return
        normalized = self._normalize_event(event_type, data)
        if normalized is None:
            return
        self.on_event(normalized)
        self._write_state(
            connected=True,
            connection_state="connected",
            auth_state="ready",
            last_event_at=utc_now(),
            last_event_type=event_type,
            last_conversation_id=normalized.get("conversation_id"),
            updated_at=utc_now(),
        )

    def _normalize_event(self, event_type: str, data: dict[str, Any]) -> dict[str, Any] | None:
        if event_type != "MESSAGE_CREATE":
            return None
        author = data.get("author") if isinstance(data.get("author"), dict) else {}
        if author.get("bot") is True or data.get("webhook_id"):
            return None
        text = str(data.get("content") or "").strip()
        if not text:
            return None
        channel_id = str(data.get("channel_id") or "").strip()
        guild_id = str(data.get("guild_id") or "").strip()
        chat_type = "direct" if not guild_id else "group"
        sender_id = str(author.get("id") or "").strip()
        mentions = data.get("mentions") if isinstance(data.get("mentions"), list) else []
        mentioned = any(str(item.get("id") or "").strip() == str(self._bot_user_id or "").strip() for item in mentions if isinstance(item, dict))
        normalized_text = self._strip_bot_mention(text, str(self._bot_user_id or ""))
        return {
            "chat_type": chat_type,
            "group_id": channel_id if chat_type == "group" else "",
            "direct_id": channel_id if chat_type == "direct" else sender_id,
            "sender_id": sender_id,
            "sender_name": str(author.get("global_name") or author.get("username") or sender_id).strip(),
            "message_id": str(data.get("id") or "").strip(),
            "conversation_id": self._conversation_id(chat_type, channel_id),
            "profile_id": self.profile_id,
            "profile_label": self.profile_label,
            "text": normalized_text,
            "mentioned": mentioned,
            "raw_event": data,
        }

    def _conversation_id(self, chat_type: str, chat_id: str) -> str:
        return format_conversation_id(
            "discord",
            chat_type,
            chat_id,
            profile_id=self.profile_id if self._encode_profile_id else None,
        )

    @staticmethod
    def _strip_bot_mention(text: str, bot_user_id: str) -> str:
        cleaned = str(text or "").strip()
        normalized_user_id = str(bot_user_id or "").strip()
        if not normalized_user_id:
            return cleaned
        for prefix in (f"<@{normalized_user_id}>", f"<@!{normalized_user_id}>"):
            if cleaned.startswith(prefix):
                return cleaned[len(prefix):].strip()
        return cleaned

    def _gateway_url(self, token: str) -> str:
        payload = self._http_json(
            "https://discord.com/api/v10/gateway/bot",
            headers={"Authorization": f"Bot {token}"},
        )
        url = str(payload.get("url") or "").strip()
        if not url:
            raise ValueError(str(payload.get("message") or "Discord gateway URL lookup failed."))
        return f"{url}?v=10&encoding=json"

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

    def _token(self) -> str:
        direct = str(self.config.get("bot_token") or "").strip()
        if direct:
            return direct
        env_name = str(self.config.get("bot_token_env") or "").strip()
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
