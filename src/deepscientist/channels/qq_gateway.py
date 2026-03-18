from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect as websocket_connect

from ..bridges.connectors import QQConnectorBridge
from ..connector_runtime import format_conversation_id
from ..qq_profiles import qq_profile_label
from ..shared import read_json, utc_now, write_json


QQ_GROUP_AND_C2C_INTENT = 1 << 25


class QQGatewayService:
    def __init__(
        self,
        *,
        home: Path,
        config: dict[str, Any],
        on_event: Callable[[dict[str, Any]], None],
        log: Callable[[str, str], None] | None = None,
    ) -> None:
        self.home = home
        self.config = config
        self.on_event = on_event
        self.log = log or self._default_log
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._connection = None
        self._heartbeat_stop = threading.Event()
        self._session_id: str | None = None
        self._seq: int | None = None
        self.profile_id = str(self.config.get("profile_id") or "").strip() or "qq-profile"
        self.profile_label = qq_profile_label(self.config)
        self.encode_profile_id = bool(self.config.get("encode_profile_id"))
        self._root = home / "logs" / "connectors" / "qq" / "profiles" / self.profile_id
        self._state_path = self._root / "gateway.json"

    def start(self) -> bool:
        if not self.is_enabled():
            self._write_state(enabled=False, connected=False, mode="gateway-direct", updated_at=utc_now())
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="deepscientist-qq-gateway")
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

    def is_enabled(self) -> bool:
        return (
            bool(self.config.get("enabled", False))
            and bool(str(self.config.get("app_id") or "").strip())
            and bool(QQConnectorBridge.read_secret(self.config, "app_secret", "app_secret_env"))
        )

    def _run(self) -> None:
        backoff_seconds = 1.0
        self._write_state(enabled=True, connected=False, mode="direct", started_at=utc_now(), updated_at=utc_now())
        while not self._stop_event.is_set():
            try:
                access_token = self._access_token()
                gateway_url = self._gateway_url(access_token)
                self._write_state(gateway_url=gateway_url, updated_at=utc_now())
                with websocket_connect(gateway_url, open_timeout=10, close_timeout=5, ping_interval=None) as connection:
                    self._connection = connection
                    self._consume_connection(connection, access_token=access_token, gateway_url=gateway_url)
                backoff_seconds = 1.0
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                self.log("warning", f"qq.gateway: reconnecting after error: {exc}")
                self._write_state(connected=False, last_error=str(exc), updated_at=utc_now())
                self._stop_event.wait(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2.0, 30.0)
            finally:
                self._heartbeat_stop.set()
                self._connection = None
        self._write_state(connected=False, stopped_at=utc_now(), updated_at=utc_now())

    def _consume_connection(self, connection: Any, *, access_token: str, gateway_url: str) -> None:
        hello = self._recv_payload(connection, timeout=10.0)
        if hello.get("op") != 10:
            raise ValueError(f"Expected QQ gateway hello op=10, got {hello.get('op')!r}.")
        self._heartbeat_stop.clear()
        heartbeat_interval_ms = int(((hello.get("d") or {}).get("heartbeat_interval") or 40000))
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(connection, heartbeat_interval_ms / 1000.0),
            daemon=True,
            name="deepscientist-qq-heartbeat",
        )
        heartbeat_thread.start()
        self._send_handshake(connection, access_token)
        self._write_state(connected=True, gateway_url=gateway_url, last_error=None, updated_at=utc_now())
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

    def _send_handshake(self, connection: Any, access_token: str) -> None:
        if self._session_id and self._seq is not None:
            payload = {
                "op": 6,
                "d": {
                    "token": f"QQBot {access_token}",
                    "session_id": self._session_id,
                    "seq": self._seq,
                },
            }
        else:
            payload = {
                "op": 2,
                "d": {
                    "token": f"QQBot {access_token}",
                    "intents": QQ_GROUP_AND_C2C_INTENT,
                    "shard": [0, 1],
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
            raise EOFError("QQ gateway requested reconnect.")
        if op == 9:
            can_resume = bool(payload.get("d"))
            if not can_resume:
                self._session_id = None
                self._seq = None
            raise EOFError("QQ gateway invalid session.")
        if op != 0:
            return

        if event_type == "READY":
            self._session_id = str(data.get("session_id") or "").strip() or None
            self._write_state(connected=True, session_id=self._session_id, last_error=None, updated_at=utc_now())
            return
        if event_type == "RESUMED":
            self._write_state(connected=True, resumed_at=utc_now(), updated_at=utc_now())
            return

        normalized = self._normalize_event(event_type, data)
        if normalized is None:
            return
        self.on_event(normalized)
        self._write_state(
            connected=True,
            last_event_at=utc_now(),
            last_event_type=event_type,
            last_conversation_id=normalized.get("conversation_id"),
            updated_at=utc_now(),
        )

    def _normalize_event(self, event_type: str, data: dict[str, Any]) -> dict[str, Any] | None:
        if event_type == "C2C_MESSAGE_CREATE":
            author = data.get("author") if isinstance(data.get("author"), dict) else {}
            openid = str(author.get("user_openid") or author.get("id") or "").strip()
            if not openid:
                return None
            return {
                "chat_type": "direct",
                "direct_id": openid,
                "openid": openid,
                "profile_id": self.profile_id,
                "profile_label": self.profile_label,
                "sender_id": openid,
                "sender_name": str(author.get("id") or openid).strip(),
                "conversation_id": format_conversation_id(
                    "qq",
                    "direct",
                    openid,
                    profile_id=self.profile_id if self.encode_profile_id else None,
                ),
                "content": str(data.get("content") or "").strip(),
                "attachments": list(data.get("attachments") or []),
                "message_id": str(data.get("id") or "").strip(),
                "raw_event": {"t": event_type, "d": data},
            }
        if event_type == "GROUP_AT_MESSAGE_CREATE":
            author = data.get("author") if isinstance(data.get("author"), dict) else {}
            group_openid = str(data.get("group_openid") or "").strip()
            member_openid = str(author.get("member_openid") or author.get("id") or "").strip()
            if not group_openid:
                return None
            return {
                "chat_type": "group",
                "group_id": group_openid,
                "group_openid": group_openid,
                "profile_id": self.profile_id,
                "profile_label": self.profile_label,
                "sender_id": member_openid,
                "sender_name": member_openid or group_openid,
                "conversation_id": format_conversation_id(
                    "qq",
                    "group",
                    group_openid,
                    profile_id=self.profile_id if self.encode_profile_id else None,
                ),
                "content": str(data.get("content") or "").strip(),
                "attachments": list(data.get("attachments") or []),
                "message_id": str(data.get("id") or "").strip(),
                "mentioned": True,
                "raw_event": {"t": event_type, "d": data},
            }
        return None

    @staticmethod
    def _recv_payload(connection: Any, *, timeout: float) -> dict[str, Any]:
        raw = connection.recv(timeout=timeout)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    def _access_token(self) -> str:
        app_id = str(self.config.get("app_id") or "").strip()
        app_secret = QQConnectorBridge.read_secret(self.config, "app_secret", "app_secret_env")
        if not app_id or not app_secret:
            raise ValueError("QQ direct gateway requires `app_id` + `app_secret`.")
        return QQConnectorBridge._access_token(app_id, app_secret)

    @staticmethod
    def _gateway_url(access_token: str) -> str:
        request = Request("https://api.sgroup.qq.com/gateway")
        request.add_header("Authorization", f"QQBot {access_token}")
        with urlopen(request, timeout=8) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        gateway_url = str(payload.get("url") or "").strip()
        if not gateway_url:
            raise ValueError(payload.get("message") or "QQ gateway URL lookup failed.")
        return gateway_url

    def _write_state(self, **patch: Any) -> None:
        state = read_json(self._state_path, {}) or {}
        if not isinstance(state, dict):
            state = {}
        state.update(patch)
        write_json(self._state_path, state)

    @staticmethod
    def _default_log(level: str, message: str) -> None:
        print(f"[{level}] {message}")
