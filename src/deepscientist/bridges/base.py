from __future__ import annotations

import hmac
import json
import os
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs
from urllib.request import Request, urlopen

from ..connector_runtime import parse_conversation_id


@dataclass
class BridgeWebhookResult:
    ok: bool = True
    status_code: int = 200
    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: dict[str, Any] | str | bytes | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    message: str = "ok"


class BaseConnectorBridge:
    name = "base"

    def parse_webhook(
        self,
        *,
        method: str,
        headers: dict[str, str],
        query: dict[str, list[str]],
        raw_body: bytes,
        body: dict[str, Any] | None,
        config: dict[str, Any],
    ) -> BridgeWebhookResult:
        return BridgeWebhookResult(ok=False, status_code=405, response_body={"ok": False, "message": "Unsupported"})

    def format_outbound(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        target = self.extract_target(payload.get("conversation_id"))
        return {
            "connector": self.name,
            "target": target,
            "message": self.render_text(payload.get("text"), payload.get("attachments")),
            "reply_to_message_id": payload.get("reply_to_message_id"),
            "attachments": payload.get("attachments") or [],
            "connector_hints": payload.get("connector_hints") or {},
            "quest_id": payload.get("quest_id"),
            "quest_root": payload.get("quest_root"),
            "importance": payload.get("importance"),
            "response_phase": payload.get("response_phase"),
        }

    def deliver(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        return self.deliver_direct(payload, config)

    def deliver_direct(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        return None

    @staticmethod
    def extract_target(conversation_id: Any) -> dict[str, str]:
        parsed = parse_conversation_id(conversation_id)
        if parsed is not None:
            return {
                "connector": str(parsed.get("connector") or ""),
                "chat_type": str(parsed.get("chat_type") or ""),
                "chat_id": str(parsed.get("chat_id") or ""),
                "profile_id": str(parsed.get("profile_id") or ""),
            }
        raw = str(conversation_id or "").strip()
        return {
            "connector": "",
            "chat_type": "",
            "chat_id": raw,
            "profile_id": "",
        }

    @staticmethod
    def render_text(text: Any, attachments: Any) -> str:
        base = str(text or "").strip()
        items = attachments if isinstance(attachments, list) else []
        if not items:
            return base
        attachment_lines: list[str] = []
        for item in items:
            if isinstance(item, str):
                attachment_lines.append(f"- {item}")
            elif isinstance(item, dict):
                if str(item.get("path_error") or "").strip():
                    continue
                candidate = item.get("label") or item.get("path") or item.get("url")
                if candidate:
                    attachment_lines.append(f"- {candidate}")
        if not attachment_lines:
            return base
        if base:
            return f"{base}\n\nAttachments:\n" + "\n".join(attachment_lines)
        return "Attachments:\n" + "\n".join(attachment_lines)

    @staticmethod
    def read_secret(config: dict[str, Any], key: str, env_key: str) -> str:
        direct = str(config.get(key) or "").strip()
        if direct:
            return direct
        env_name = str(config.get(env_key) or "").strip()
        if env_name:
            return str(os.environ.get(env_name) or "").strip()
        return ""

    @staticmethod
    def parse_json_bytes(raw_body: bytes) -> dict[str, Any]:
        if not raw_body:
            return {}
        return json.loads(raw_body.decode("utf-8"))

    @staticmethod
    def parse_form_bytes(raw_body: bytes) -> dict[str, str]:
        if not raw_body:
            return {}
        values = parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)
        return {key: items[-1] if items else "" for key, items in values.items()}

    @staticmethod
    def verify_bearer_token(headers: dict[str, str], expected_token: str) -> bool:
        if not expected_token:
            return True
        header = headers.get("Authorization") or headers.get("authorization") or ""
        return hmac.compare_digest(header, f"Bearer {expected_token}")

    @staticmethod
    def verify_hmac_sha256(*, secret: str, message: bytes, signature: str, prefix: str = "") -> bool:
        if not secret:
            return False
        digest = hmac.new(secret.encode("utf-8"), message, sha256).hexdigest()
        candidate = f"{prefix}{digest}" if prefix else digest
        return hmac.compare_digest(candidate, signature)

    @staticmethod
    def _post_json(url: str, payload: dict[str, Any], *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        request = Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urlopen(request, timeout=8) as response:  # noqa: S310
                response_text = response.read().decode("utf-8", errors="replace")
                return {
                    "ok": 200 <= response.status < 300,
                    "status_code": response.status,
                    "response": response_text[:500],
                }
        except URLError as exc:
            return {
                "ok": False,
                "status_code": None,
                "error": str(exc),
            }
