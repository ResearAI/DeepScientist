from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
from hashlib import sha256
from hmac import new as hmac_new
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request

from ..network import urlopen_with_proxy as urlopen
from ..shared import append_jsonl, ensure_dir, utc_now
from ..connector.weixin_support import (
    WEIXIN_UPLOAD_MEDIA_FILE,
    WEIXIN_UPLOAD_MEDIA_IMAGE,
    WEIXIN_UPLOAD_MEDIA_VIDEO,
    clear_weixin_context_send_state,
    download_weixin_remote_attachment,
    get_weixin_context_entry,
    get_weixin_context_token,
    mark_weixin_context_stale,
    normalize_weixin_base_url,
    normalize_weixin_cdn_base_url,
    send_weixin_message,
    upload_local_media_to_weixin,
)
from .base import BaseConnectorBridge, BridgeWebhookResult


class TelegramConnectorBridge(BaseConnectorBridge):
    name = "telegram"

    def parse_webhook(self, *, method: str, headers: dict[str, str], query: dict[str, list[str]], raw_body: bytes, body: dict[str, Any] | None, config: dict[str, Any]) -> BridgeWebhookResult:
        if method != "POST":
            return BridgeWebhookResult(ok=False, status_code=405, response_body={"ok": False, "message": "Method not allowed"})
        secret = self.read_secret(config, "webhook_secret", "webhook_secret_env")
        if secret:
            header_secret = headers.get("X-Telegram-Bot-Api-Secret-Token") or headers.get("x-telegram-bot-api-secret-token") or ""
            if header_secret != secret:
                return BridgeWebhookResult(ok=False, status_code=401, response_body={"ok": False, "message": "Invalid Telegram webhook secret"})
        packet = body or self.parse_json_bytes(raw_body)
        message = packet.get("message") or packet.get("edited_message") or packet.get("channel_post")
        if not isinstance(message, dict):
            return BridgeWebhookResult(events=[])
        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        sender = message.get("from") if isinstance(message.get("from"), dict) else {}
        chat_type_raw = str(chat.get("type") or "private").strip().lower()
        chat_type = "direct" if chat_type_raw == "private" else "group"
        chat_id = str(chat.get("id") or "").strip()
        sender_id = str(sender.get("id") or "").strip()
        sender_name = str(sender.get("username") or sender.get("first_name") or sender_id).strip()
        text = str(message.get("text") or message.get("caption") or "").strip()
        entities = message.get("entities") if isinstance(message.get("entities"), list) else []
        mentioned = any(isinstance(item, dict) and item.get("type") == "mention" for item in entities)
        event = {
            "chat_type": chat_type,
            "group_id": chat_id if chat_type == "group" else "",
            "direct_id": chat_id if chat_type == "direct" else sender_id,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "message_id": str(message.get("message_id") or ""),
            "conversation_id": f"telegram:{chat_type}:{chat_id}",
            "text": text,
            "mentioned": mentioned,
            "raw_event": packet,
        }
        return BridgeWebhookResult(events=[event] if text else [])

    def format_outbound(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        target = self.extract_target(payload.get("conversation_id"))
        return {
            "method": "sendMessage",
            "chat_id": target["chat_id"],
            "text": self.render_text(payload.get("text"), payload.get("attachments")),
            "reply_to_message_id": payload.get("reply_to_message_id"),
        }

    def deliver_direct(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        token = self.read_secret(config, "bot_token", "bot_token_env")
        if not token:
            return None
        body = self.format_outbound(payload, config)
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        request = Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST")
        request.add_header("Content-Type", "application/json; charset=utf-8")
        with urlopen(request, timeout=8) as response:  # noqa: S310
            response_text = response.read().decode("utf-8", errors="replace")
            return {"ok": 200 <= response.status < 300, "status_code": response.status, "response": response_text[:500], "transport": "telegram-http"}


class SlackConnectorBridge(BaseConnectorBridge):
    name = "slack"

    def parse_webhook(self, *, method: str, headers: dict[str, str], query: dict[str, list[str]], raw_body: bytes, body: dict[str, Any] | None, config: dict[str, Any]) -> BridgeWebhookResult:
        if method != "POST":
            return BridgeWebhookResult(ok=False, status_code=405, response_body={"ok": False, "message": "Method not allowed"})
        signing_secret = self.read_secret(config, "signing_secret", "signing_secret_env")
        if signing_secret:
            timestamp = headers.get("X-Slack-Request-Timestamp") or headers.get("x-slack-request-timestamp") or ""
            signature = headers.get("X-Slack-Signature") or headers.get("x-slack-signature") or ""
            message = f"v0:{timestamp}:{raw_body.decode('utf-8')}".encode("utf-8")
            expected = "v0=" + hmac_new(signing_secret.encode("utf-8"), message, sha256).hexdigest()
            if not signature or signature != expected:
                return BridgeWebhookResult(ok=False, status_code=401, response_body={"ok": False, "message": "Invalid Slack signature"})
        content_type = headers.get("Content-Type") or headers.get("content-type") or ""
        packet = body or {}
        if not packet:
            packet = self.parse_form_bytes(raw_body) if "application/x-www-form-urlencoded" in content_type else self.parse_json_bytes(raw_body)
            if "payload" in packet:
                packet = json.loads(packet["payload"])
        if packet.get("type") == "url_verification":
            return BridgeWebhookResult(response_body={"challenge": packet.get("challenge", "")})
        event = packet.get("event") if isinstance(packet.get("event"), dict) else packet
        if not isinstance(event, dict):
            return BridgeWebhookResult(events=[])
        if event.get("subtype") == "bot_message":
            return BridgeWebhookResult(events=[])
        text = str(event.get("text") or "").strip()
        if not text:
            return BridgeWebhookResult(events=[])
        channel_id = str(event.get("channel") or "").strip()
        channel_type = str(event.get("channel_type") or packet.get("channel_type") or "channel").strip().lower()
        chat_type = "direct" if channel_type == "im" else "group"
        event_payload = {
            "chat_type": chat_type,
            "group_id": channel_id if chat_type == "group" else "",
            "direct_id": channel_id if chat_type == "direct" else str(event.get("user") or ""),
            "sender_id": str(event.get("user") or "").strip(),
            "sender_name": str(event.get("username") or event.get("user") or "").strip(),
            "message_id": str(event.get("ts") or event.get("event_ts") or "").strip(),
            "conversation_id": f"slack:{chat_type}:{channel_id}",
            "text": text,
            "mentioned": str(event.get("type") or "").strip() == "app_mention" or text.strip().startswith("<@"),
            "raw_event": packet,
        }
        return BridgeWebhookResult(events=[event_payload])

    def format_outbound(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        target = self.extract_target(payload.get("conversation_id"))
        result = {
            "channel": target["chat_id"],
            "text": self.render_text(payload.get("text"), payload.get("attachments")),
        }
        reply_to = str(payload.get("reply_to_message_id") or "").strip()
        if reply_to:
            result["thread_ts"] = reply_to
        return result

    def deliver_direct(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        token = self.read_secret(config, "bot_token", "bot_token_env")
        if not token:
            return None
        request = Request("https://slack.com/api/chat.postMessage", data=json.dumps(self.format_outbound(payload, config), ensure_ascii=False).encode("utf-8"), method="POST")
        request.add_header("Content-Type", "application/json; charset=utf-8")
        request.add_header("Authorization", f"Bearer {token}")
        with urlopen(request, timeout=8) as response:  # noqa: S310
            response_text = response.read().decode("utf-8", errors="replace")
            return {"ok": 200 <= response.status < 300, "status_code": response.status, "response": response_text[:500], "transport": "slack-http"}


class FeishuConnectorBridge(BaseConnectorBridge):
    name = "feishu"

    def parse_webhook(self, *, method: str, headers: dict[str, str], query: dict[str, list[str]], raw_body: bytes, body: dict[str, Any] | None, config: dict[str, Any]) -> BridgeWebhookResult:
        if method != "POST":
            return BridgeWebhookResult(ok=False, status_code=405, response_body={"ok": False, "message": "Method not allowed"})
        packet = body or self.parse_json_bytes(raw_body)
        if "challenge" in packet:
            token = self.read_secret(config, "verification_token", "verification_token_env")
            body_token = str(packet.get("token") or "").strip()
            if token and body_token and body_token != token:
                return BridgeWebhookResult(ok=False, status_code=401, response_body={"ok": False, "message": "Invalid Feishu verification token"})
            return BridgeWebhookResult(response_body={"challenge": packet.get("challenge", "")})
        event = packet.get("event") if isinstance(packet.get("event"), dict) else {}
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        sender = event.get("sender") if isinstance(event.get("sender"), dict) else {}
        sender_id_info = sender.get("sender_id") if isinstance(sender.get("sender_id"), dict) else {}
        content_raw = message.get("content")
        content: dict[str, Any] = {}
        if isinstance(content_raw, str):
            try:
                content = json.loads(content_raw)
            except json.JSONDecodeError:
                content = {"text": content_raw}
        elif isinstance(content_raw, dict):
            content = content_raw
        text = str(content.get("text") or "").strip()
        if not text:
            return BridgeWebhookResult(events=[])
        chat_type_raw = str(message.get("chat_type") or "p2p").strip().lower()
        chat_type = "direct" if chat_type_raw == "p2p" else "group"
        chat_id = str(message.get("chat_id") or "").strip()
        sender_id = str(sender_id_info.get("open_id") or sender_id_info.get("user_id") or "").strip()
        event_payload = {
            "chat_type": chat_type,
            "group_id": chat_id if chat_type == "group" else "",
            "direct_id": chat_id if chat_type == "direct" else sender_id,
            "sender_id": sender_id,
            "sender_name": str(sender.get("sender_type") or sender_id).strip(),
            "message_id": str(message.get("message_id") or "").strip(),
            "conversation_id": f"feishu:{chat_type}:{chat_id}",
            "text": text,
            "mentioned": str(message.get("mentions") or "") != "",
            "raw_event": packet,
        }
        return BridgeWebhookResult(events=[event_payload])

    def format_outbound(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        target = self.extract_target(payload.get("conversation_id"))
        return {
            "receive_id": target["chat_id"],
            "receive_id_type": "chat_id",
            "msg_type": "text",
            "content": json.dumps({"text": self.render_text(payload.get("text"), payload.get("attachments"))}, ensure_ascii=False),
        }

    def deliver_direct(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        app_id = str(config.get("app_id") or "").strip()
        app_secret = self.read_secret(config, "app_secret", "app_secret_env")
        if not app_id or not app_secret:
            return None
        token_request = Request(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            data=json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8"),
            method="POST",
        )
        token_request.add_header("Content-Type", "application/json; charset=utf-8")
        with urlopen(token_request, timeout=8) as token_response:  # noqa: S310
            token_payload = json.loads(token_response.read().decode("utf-8"))
        tenant_access_token = str(token_payload.get("tenant_access_token") or "").strip()
        if not tenant_access_token:
            return {"ok": False, "status_code": token_response.status, "response": json.dumps(token_payload, ensure_ascii=False)[:500], "transport": "feishu-http"}
        request = Request(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
            data=json.dumps(self.format_outbound(payload, config), ensure_ascii=False).encode("utf-8"),
            method="POST",
        )
        request.add_header("Content-Type", "application/json; charset=utf-8")
        request.add_header("Authorization", f"Bearer {tenant_access_token}")
        with urlopen(request, timeout=8) as response:  # noqa: S310
            response_text = response.read().decode("utf-8", errors="replace")
            return {"ok": 200 <= response.status < 300, "status_code": response.status, "response": response_text[:500], "transport": "feishu-http"}


class WhatsAppConnectorBridge(BaseConnectorBridge):
    name = "whatsapp"

    def parse_webhook(self, *, method: str, headers: dict[str, str], query: dict[str, list[str]], raw_body: bytes, body: dict[str, Any] | None, config: dict[str, Any]) -> BridgeWebhookResult:
        if method == "GET":
            verify_token = self.read_secret(config, "verify_token", "verify_token_env")
            mode = (query.get("hub.mode") or [""])[0]
            token = (query.get("hub.verify_token") or [""])[0]
            challenge = (query.get("hub.challenge") or [""])[0]
            if mode == "subscribe" and verify_token and token == verify_token:
                return BridgeWebhookResult(response_headers={"Content-Type": "text/plain; charset=utf-8"}, response_body=challenge)
            return BridgeWebhookResult(ok=False, status_code=403, response_body="forbidden")
        if method != "POST":
            return BridgeWebhookResult(ok=False, status_code=405, response_body={"ok": False, "message": "Method not allowed"})
        packet = body or self.parse_json_bytes(raw_body)
        events: list[dict[str, Any]] = []
        for entry in packet.get("entry") or []:
            if not isinstance(entry, dict):
                continue
            for change in entry.get("changes") or []:
                if not isinstance(change, dict):
                    continue
                value = change.get("value") if isinstance(change.get("value"), dict) else {}
                contacts = value.get("contacts") if isinstance(value.get("contacts"), list) else []
                names: dict[str, str] = {}
                for item in contacts:
                    if not isinstance(item, dict):
                        continue
                    wa_id = str(item.get("wa_id") or "").strip()
                    profile = item.get("profile") if isinstance(item.get("profile"), dict) else {}
                    if wa_id:
                        names[wa_id] = str(profile.get("name") or wa_id).strip()
                for message in value.get("messages") or []:
                    if not isinstance(message, dict):
                        continue
                    sender_id = str(message.get("from") or "").strip()
                    text_body = ""
                    if isinstance(message.get("text"), dict):
                        text_body = str(message["text"].get("body") or "").strip()
                    if not text_body:
                        continue
                    events.append(
                        {
                            "chat_type": "direct",
                            "group_id": "",
                            "direct_id": sender_id,
                            "sender_id": sender_id,
                            "sender_name": names.get(sender_id, sender_id),
                            "message_id": str(message.get("id") or "").strip(),
                            "conversation_id": f"whatsapp:direct:{sender_id}",
                            "text": text_body,
                            "mentioned": False,
                            "raw_event": packet,
                        }
                    )
        return BridgeWebhookResult(events=events)

    def format_outbound(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        target = self.extract_target(payload.get("conversation_id"))
        return {
            "messaging_product": "whatsapp",
            "to": target["chat_id"],
            "type": "text",
            "text": {
                "body": self.render_text(payload.get("text"), payload.get("attachments")),
            },
        }

    def deliver_direct(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        transport = str(config.get("transport") or "").strip().lower()
        session_dir = str(config.get("session_dir") or "").strip()
        if transport == "local_session" and session_dir:
            root = ensure_dir(Path(session_dir).expanduser())
            outbox_path = root / "outbox.jsonl"
            record = {
                "created_at": utc_now(),
                "transport": "local_session",
                "payload": self.format_outbound(payload, config),
                "normalized_payload": payload,
            }
            append_jsonl(outbox_path, record)
            return {
                "ok": True,
                "queued": True,
                "transport": "whatsapp-local-session",
                "outbox_path": str(outbox_path),
            }
        provider = str(config.get("provider") or "relay").strip().lower()
        if provider != "meta":
            return None
        token = self.read_secret(config, "access_token", "access_token_env")
        phone_number_id = str(config.get("phone_number_id") or "").strip()
        if not token or not phone_number_id:
            return None
        api_base_url = str(config.get("api_base_url") or "https://graph.facebook.com").rstrip("/")
        api_version = str(config.get("api_version") or "v21.0").strip()
        url = f"{api_base_url}/{api_version}/{phone_number_id}/messages"
        request = Request(url, data=json.dumps(self.format_outbound(payload, config), ensure_ascii=False).encode("utf-8"), method="POST")
        request.add_header("Content-Type", "application/json; charset=utf-8")
        request.add_header("Authorization", f"Bearer {token}")
        with urlopen(request, timeout=8) as response:  # noqa: S310
            response_text = response.read().decode("utf-8", errors="replace")
            return {"ok": 200 <= response.status < 300, "status_code": response.status, "response": response_text[:500], "transport": "whatsapp-http"}


class DiscordConnectorBridge(BaseConnectorBridge):
    name = "discord"

    def parse_webhook(self, *, method: str, headers: dict[str, str], query: dict[str, list[str]], raw_body: bytes, body: dict[str, Any] | None, config: dict[str, Any]) -> BridgeWebhookResult:
        if method != "POST":
            return BridgeWebhookResult(ok=False, status_code=405, response_body={"ok": False, "message": "Method not allowed"})
        relay_token = str(config.get("relay_auth_token") or "").strip()
        if relay_token and not self.verify_bearer_token(headers, relay_token):
            return BridgeWebhookResult(ok=False, status_code=401, response_body={"ok": False, "message": "Invalid Discord bridge token"})
        packet = body or self.parse_json_bytes(raw_body)
        if packet.get("type") == 1:
            return BridgeWebhookResult(response_body={"type": 1})
        if isinstance(packet.get("normalized"), dict):
            return BridgeWebhookResult(events=[packet["normalized"]])
        message = packet.get("message") if isinstance(packet.get("message"), dict) else packet
        author = message.get("author") if isinstance(message.get("author"), dict) else {}
        text = str(message.get("content") or packet.get("content") or "").strip()
        if not text:
            return BridgeWebhookResult(events=[])
        channel_id = str(message.get("channel_id") or packet.get("channel_id") or "").strip()
        chat_type_raw = str(packet.get("channel_type") or message.get("channel_type") or "").strip().lower()
        chat_type = "direct" if chat_type_raw in {"dm", "direct"} else "group"
        event = {
            "chat_type": chat_type,
            "group_id": channel_id if chat_type == "group" else "",
            "direct_id": channel_id if chat_type == "direct" else str(author.get("id") or ""),
            "sender_id": str(author.get("id") or "").strip(),
            "sender_name": str(author.get("username") or author.get("global_name") or "").strip(),
            "message_id": str(message.get("id") or "").strip(),
            "conversation_id": f"discord:{chat_type}:{channel_id}",
            "text": text,
            "mentioned": bool(message.get("mentions")),
            "raw_event": packet,
        }
        return BridgeWebhookResult(events=[event])

    def format_outbound(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        target = self.extract_target(payload.get("conversation_id"))
        return {
            "channel_id": target["chat_id"],
            "content": self.render_text(payload.get("text"), payload.get("attachments")),
            "message_reference": {"message_id": payload.get("reply_to_message_id")} if payload.get("reply_to_message_id") else None,
        }

    def deliver_direct(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        token = self.read_secret(config, "bot_token", "bot_token_env")
        if not token:
            return None
        formatted = self.format_outbound(payload, config)
        channel_id = str(formatted.pop("channel_id") or "").strip()
        if not channel_id:
            return None
        formatted = {key: value for key, value in formatted.items() if value is not None}
        request = Request(f"https://discord.com/api/v10/channels/{channel_id}/messages", data=json.dumps(formatted, ensure_ascii=False).encode("utf-8"), method="POST")
        request.add_header("Content-Type", "application/json; charset=utf-8")
        request.add_header("Authorization", f"Bot {token}")
        request.add_header("User-Agent", "DiscordBot (https://github.com/ResearAI/DeepScientist, 1.5.17)")
        with urlopen(request, timeout=8) as response:  # noqa: S310
            response_text = response.read().decode("utf-8", errors="replace")
            return {"ok": 200 <= response.status < 300, "status_code": response.status, "response": response_text[:500], "transport": "discord-http"}


class QQConnectorBridge(BaseConnectorBridge):
    name = "qq"
    _token_cache: dict[str, dict[str, float | str]] = {}
    _IMAGE_FILE_TYPE = 1
    _FILE_FILE_TYPE = 4

    def parse_webhook(self, *, method: str, headers: dict[str, str], query: dict[str, list[str]], raw_body: bytes, body: dict[str, Any] | None, config: dict[str, Any]) -> BridgeWebhookResult:
        return BridgeWebhookResult(
            ok=False,
            status_code=410,
            response_body={
                "ok": False,
                "message": "QQ webhook callback mode was removed. Use the built-in QQ gateway direct connection instead.",
            },
        )

    def deliver(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        return self.deliver_direct(payload, config)

    def format_outbound(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        target = self.extract_target(payload.get("conversation_id"))
        reply_to = str(payload.get("reply_to_message_id") or "").strip()
        requested_render_mode = self._requested_render_mode(payload)
        render_mode, render_mode_warning = self._effective_render_mode(requested_render_mode, config)
        native_attachments, residual_attachments, attachment_issues = self._partition_native_attachments(payload.get("attachments"), config)
        text = self.render_text(payload.get("text"), residual_attachments)
        return {
            "chat_type": target["chat_type"],
            "chat_id": target["chat_id"],
            "reply_to_message_id": reply_to or None,
            "requested_render_mode": requested_render_mode,
            "render_mode": render_mode,
            "render_mode_warning": render_mode_warning,
            "text": text,
            "native_attachments": native_attachments,
            "attachment_issues": attachment_issues,
        }

    def deliver_direct(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        app_id = str(config.get("app_id") or "").strip()
        app_secret = self.read_secret(config, "app_secret", "app_secret_env")
        if not app_id or not app_secret:
            return None
        formatted = self.format_outbound(payload, config)
        chat_type = str(formatted.get("chat_type") or "").strip().lower()
        chat_id = str(formatted.get("chat_id") or "").strip()
        if chat_type not in {"direct", "group"} or not chat_id:
            return None
        access_token = self._access_token(app_id, app_secret)
        reply_to = str(formatted.get("reply_to_message_id") or "").strip() or None
        text = str(formatted.get("text") or "").strip()
        render_mode = str(formatted.get("render_mode") or "plain").strip().lower()
        native_attachments = [dict(item) for item in (formatted.get("native_attachments") or []) if isinstance(item, dict)]
        attachment_issues = [dict(item) for item in (formatted.get("attachment_issues") or []) if isinstance(item, dict)]
        parts: list[dict[str, Any]] = []
        warnings: list[str] = []
        if str(formatted.get("render_mode_warning") or "").strip():
            warnings.append(str(formatted.get("render_mode_warning")).strip())
        for issue in attachment_issues:
            error = str(issue.get("error") or "").strip()
            if error:
                warnings.append(error)
        if text or not native_attachments:
            text_result = self._send_text_message(
                access_token=access_token,
                chat_type=chat_type,
                chat_id=chat_id,
                text=text,
                reply_to_message_id=reply_to,
                render_mode=render_mode,
            )
            parts.append({"part": "text", "render_mode": render_mode, **text_result})
        for index, attachment in enumerate(native_attachments, start=1):
            media_kind = str(attachment.get("qq_media_kind") or "file").strip()
            media_result = self._send_media_attachment(
                access_token=access_token,
                chat_type=chat_type,
                chat_id=chat_id,
                attachment=attachment,
                reply_to_message_id=reply_to,
            )
            parts.append(
                {
                    "part": f"attachment_{index}",
                    "media_kind": media_kind,
                    "path": attachment.get("path"),
                    "url": attachment.get("url"),
                    **media_result,
                }
            )
        succeeded = [item for item in parts if bool(item.get("ok", False))]
        failed = [item for item in parts if not bool(item.get("ok", False))]
        error_messages = [str(item.get("error") or "").strip() for item in failed if str(item.get("error") or "").strip()]
        error_messages.extend(warnings)
        last_success = succeeded[-1] if succeeded else {}
        return {
            "ok": bool(succeeded),
            "queued": False,
            "partial": bool(succeeded and (failed or warnings)),
            "transport": "qq-http",
            "status_code": last_success.get("status_code") or (failed[-1].get("status_code") if failed else None),
            "message_id": last_success.get("message_id"),
            "response": str(last_success.get("response") or "").strip()[:500] or None,
            "parts": parts,
            "warnings": warnings,
            "error": "; ".join(error_messages) if error_messages else None,
        }

    @staticmethod
    def _requested_render_mode(payload: dict[str, Any]) -> str:
        connector_hints = payload.get("connector_hints") if isinstance(payload.get("connector_hints"), dict) else {}
        qq_hints = connector_hints.get("qq") if isinstance(connector_hints.get("qq"), dict) else {}
        requested = str(qq_hints.get("render_mode") or "auto").strip().lower()
        return requested if requested in {"auto", "plain", "markdown"} else "auto"

    @staticmethod
    def _effective_render_mode(requested: str, config: dict[str, Any]) -> tuple[str, str | None]:
        markdown_enabled = bool(config.get("enable_markdown_send", False))
        if requested == "markdown" and not markdown_enabled:
            return "plain", "QQ markdown send was requested, but `enable_markdown_send` is disabled."
        if requested == "markdown":
            return "markdown", None
        return "plain", None

    @classmethod
    def _partition_native_attachments(
        cls,
        attachments: Any,
        config: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        native_enabled = bool(config.get("enable_file_upload_experimental", False))
        native_items: list[dict[str, Any]] = []
        residual_items: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        for index, raw_item in enumerate(attachments if isinstance(attachments, list) else [], start=1):
            if not isinstance(raw_item, dict):
                continue
            item = dict(raw_item)
            if str(item.get("path_error") or "").strip():
                issues.append(
                    {
                        "attachment_index": index,
                        "error": f"attachment {index}: path resolution failed for {item.get('path')}",
                    }
                )
                continue
            connector_delivery = item.get("connector_delivery") if isinstance(item.get("connector_delivery"), dict) else {}
            qq_delivery = connector_delivery.get("qq") if isinstance(connector_delivery.get("qq"), dict) else {}
            media_kind = str(qq_delivery.get("media_kind") or "").strip().lower()
            allow_internal_auto_media = bool(qq_delivery.get("allow_internal_auto_media"))
            if media_kind not in {"image", "file"}:
                residual_items.append(item)
                continue
            if not native_enabled and not allow_internal_auto_media:
                issues.append(
                    {
                        "attachment_index": index,
                        "error": (
                            f"attachment {index}: QQ native media send is disabled by "
                            "`enable_file_upload_experimental`."
                        ),
                    }
                )
                continue
            source_path = str(item.get("path") or "").strip()
            source_url = str(item.get("url") or "").strip()
            if not source_path and not source_url:
                issues.append(
                    {
                        "attachment_index": index,
                        "error": f"attachment {index}: QQ {media_kind} send requires `path` or `url`.",
                    }
                )
                continue
            item["qq_media_kind"] = media_kind
            native_items.append(item)
        return native_items, residual_items, issues

    @staticmethod
    def _message_endpoint(chat_type: str, chat_id: str) -> str:
        return (
            f"https://api.sgroup.qq.com/v2/users/{chat_id}/messages"
            if chat_type == "direct"
            else f"https://api.sgroup.qq.com/v2/groups/{chat_id}/messages"
        )

    @staticmethod
    def _files_endpoint(chat_type: str, chat_id: str) -> str:
        return (
            f"https://api.sgroup.qq.com/v2/users/{chat_id}/files"
            if chat_type == "direct"
            else f"https://api.sgroup.qq.com/v2/groups/{chat_id}/files"
        )

    @staticmethod
    def _message_seq(reply_to_message_id: str | None) -> int | None:
        if not reply_to_message_id:
            return None
        return max(int(time.time() * 1000) % 65536, 1)

    def _send_text_message(
        self,
        *,
        access_token: str,
        chat_type: str,
        chat_id: str,
        text: str,
        reply_to_message_id: str | None,
        render_mode: str,
    ) -> dict[str, Any]:
        if not text.strip():
            return {"ok": False, "error": "QQ text message content is empty."}
        body: dict[str, Any]
        if render_mode == "markdown":
            body = {"markdown": {"content": text}, "msg_type": 2}
        else:
            body = {"content": text, "msg_type": 0}
        msg_seq = self._message_seq(reply_to_message_id)
        if msg_seq is not None:
            body["msg_seq"] = msg_seq
        if reply_to_message_id:
            body["msg_id"] = reply_to_message_id
        return self._post_json(
            endpoint=self._message_endpoint(chat_type, chat_id),
            access_token=access_token,
            body=body,
        )

    def _send_media_attachment(
        self,
        *,
        access_token: str,
        chat_type: str,
        chat_id: str,
        attachment: dict[str, Any],
        reply_to_message_id: str | None,
    ) -> dict[str, Any]:
        media_kind = str(attachment.get("qq_media_kind") or "file").strip().lower()
        upload_payload: dict[str, Any] = {
            "file_type": self._IMAGE_FILE_TYPE if media_kind == "image" else self._FILE_FILE_TYPE,
            "srv_send_msg": False,
        }
        url_value = str(attachment.get("url") or "").strip()
        path_value = str(attachment.get("path") or "").strip()
        try:
            if url_value:
                upload_payload["url"] = url_value
            elif path_value:
                payload, file_name = self._file_data_payload(Path(path_value), media_kind=media_kind)
                upload_payload["file_data"] = payload
                if media_kind == "file" and file_name:
                    upload_payload["file_name"] = file_name
            else:
                return {"ok": False, "error": "QQ native media send requires `path` or `url`."}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        upload_result = self._post_json(
            endpoint=self._files_endpoint(chat_type, chat_id),
            access_token=access_token,
            body=upload_payload,
        )
        if not upload_result.get("ok", False):
            upload_result["error"] = str(upload_result.get("error") or "QQ media upload failed.").strip()
            return upload_result
        file_info = str(upload_result.get("payload", {}).get("file_info") or "").strip()
        if not file_info:
            return {
                "ok": False,
                "error": "QQ media upload succeeded but returned no `file_info`.",
                "status_code": upload_result.get("status_code"),
                "response": upload_result.get("response"),
            }
        message_body: dict[str, Any] = {
            "msg_type": 7,
            "media": {"file_info": file_info},
        }
        msg_seq = self._message_seq(reply_to_message_id)
        if msg_seq is not None:
            message_body["msg_seq"] = msg_seq
        if reply_to_message_id:
            message_body["msg_id"] = reply_to_message_id
        send_result = self._post_json(
            endpoint=self._message_endpoint(chat_type, chat_id),
            access_token=access_token,
            body=message_body,
        )
        if not send_result.get("ok", False):
            send_result["error"] = str(send_result.get("error") or "QQ media message send failed.").strip()
        return send_result

    @staticmethod
    def _file_data_payload(path: Path, *, media_kind: str) -> tuple[str, str]:
        if not path.exists():
            raise FileNotFoundError(f"QQ native {media_kind} attachment path does not exist: {path}")
        payload = base64.b64encode(path.read_bytes()).decode("utf-8")
        return payload, path.name

    def _post_json(self, *, endpoint: str, access_token: str, body: dict[str, Any]) -> dict[str, Any]:
        request = Request(endpoint, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST")
        request.add_header("Content-Type", "application/json; charset=utf-8")
        request.add_header("Authorization", f"QQBot {access_token}")
        try:
            with urlopen(request, timeout=8) as response:  # noqa: S310
                response_text = response.read().decode("utf-8", errors="replace")
                payload = json.loads(response_text) if response_text else {}
                return {
                    "ok": 200 <= response.status < 300,
                    "status_code": response.status,
                    "response": response_text[:500],
                    "payload": payload if isinstance(payload, dict) else {},
                    "message_id": str((payload or {}).get("id") or "").strip() or None,
                }
        except HTTPError as exc:
            response_text = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(response_text) if response_text else {}
            except json.JSONDecodeError:
                payload = {}
            return {
                "ok": False,
                "status_code": exc.code,
                "response": response_text[:500],
                "payload": payload if isinstance(payload, dict) else {},
                "error": str((payload or {}).get("message") or response_text or exc.reason).strip() or "QQ HTTP error",
            }
        except Exception as exc:  # pragma: no cover - defensive network transport guard
            return {
                "ok": False,
                "status_code": None,
                "response": None,
                "payload": {},
                "error": str(exc),
            }

    @classmethod
    def _access_token(cls, app_id: str, app_secret: str) -> str:
        cached = cls._token_cache.get(app_id)
        now = time.time()
        if cached is not None:
            token = str(cached.get("token") or "").strip()
            expires_at = float(cached.get("expires_at") or 0)
            if token and now < expires_at - 300:
                return token
        request = Request(
            "https://bots.qq.com/app/getAppAccessToken",
            data=json.dumps({"appId": app_id, "clientSecret": app_secret}).encode("utf-8"),
            method="POST",
        )
        request.add_header("Content-Type", "application/json; charset=utf-8")
        with urlopen(request, timeout=8) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        access_token = str(payload.get("access_token") or "").strip()
        if not access_token:
            raise ValueError(payload.get("message") or "QQ access token exchange failed.")
        expires_in = int(payload.get("expires_in") or 7200)
        cls._token_cache[app_id] = {
            "token": access_token,
            "expires_at": now + expires_in,
        }
        return access_token


class WeixinSendItemsError(RuntimeError):
    def __init__(self, message: str, *, message_ids: list[str], failed_index: int) -> None:
        super().__init__(message)
        self.message_ids = list(message_ids)
        self.failed_index = int(failed_index)


class WeixinConnectorBridge(BaseConnectorBridge):
    name = "weixin"
    _MEDIA_ITEM_TYPES = {2, 4, 5}
    _MEDIA_SEND_INITIAL_DELAY_SECONDS = 0.8
    _TEXT_SEND_RETRY_DELAYS_SECONDS = (0.8, 1.5, 3.0)
    _MEDIA_SEND_RETRY_DELAYS_SECONDS = (1.5, 3.0, 5.0)
    _STALE_CONTEXT_SUPPRESSED_KINDS = {"progress", "milestone", "assistant", "summary", "ack"}

    def deliver(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        return self.deliver_direct(payload, config)

    def deliver_direct(self, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        token = self.read_secret(config, "bot_token", "bot_token_env")
        if not token:
            return None
        target = self.extract_target(payload.get("conversation_id"))
        to_user_id = str(target.get("chat_id") or "").strip()
        if not to_user_id:
            return {
                "ok": False,
                "queued": False,
                "transport": "weixin-ilink",
                "error": "Weixin outbound target is empty.",
            }
        connector_root = self._connector_root(config)
        kind = str(payload.get("kind") or "").strip().lower()
        context_entry = get_weixin_context_entry(connector_root, to_user_id)
        context_token = get_weixin_context_token(connector_root, to_user_id)
        if not context_token:
            if kind in self._STALE_CONTEXT_SUPPRESSED_KINDS:
                return self._queued_context_wait_response(
                    reason=f"Weixin context_token is missing for `{to_user_id}`. Waiting for the next inbound message.",
                )
            return {
                "ok": False,
                "queued": False,
                "transport": "weixin-ilink",
                "error": f"Weixin context_token is missing for `{to_user_id}`. Wait for one inbound message first.",
            }
        if bool(context_entry.get("stale_context")) and kind in self._STALE_CONTEXT_SUPPRESSED_KINDS:
            stale_since = str(context_entry.get("stale_since") or "").strip()
            warning = "Weixin outbound is paused until the next inbound message refreshes context_token."
            if stale_since:
                warning = f"{warning} stale_since={stale_since}"
            return self._queued_context_wait_response(reason=warning)

        native_attachments, residual_attachments, warnings = self._partition_native_attachments(payload.get("attachments"))
        rendered_text = self.render_text(payload.get("text"), residual_attachments)
        base_url = normalize_weixin_base_url(config.get("base_url"))
        cdn_base_url = normalize_weixin_cdn_base_url(config.get("cdn_base_url"))
        route_tag = str(config.get("route_tag") or "").strip() or None
        timeout_ms = int(config.get("request_timeout_ms") or 15_000)
        parts: list[dict[str, Any]] = []
        temp_dir = ensure_dir(connector_root / "tmp")

        try:
            if native_attachments:
                item_list: list[dict[str, Any]] = []
                for index, attachment in enumerate(native_attachments, start=1):
                    media_type, message_item, resolved_path = self._prepare_attachment_item(
                        attachment=attachment,
                        to_user_id=to_user_id,
                        base_url=base_url,
                        cdn_base_url=cdn_base_url,
                        token=token,
                        route_tag=route_tag,
                        timeout_ms=timeout_ms,
                        quest_root=payload.get("quest_root"),
                        temp_dir=temp_dir,
                    )
                    item_list.append(message_item)
                    parts.append(
                        {
                            "part": f"attachment_{index}",
                            "ok": True,
                            "media_type": media_type,
                            "path": str(resolved_path),
                        }
                    )
                if rendered_text:
                    item_list.append(
                        {
                            "type": 1,
                            "text_item": {"text": rendered_text},
                        }
                    )
                    parts.append({"part": "text", "ok": True})
                try:
                    send_result = self._send_items(
                        to_user_id=to_user_id,
                        context_token=context_token,
                        item_list=item_list,
                        base_url=base_url,
                        token=token,
                        route_tag=route_tag,
                        timeout_ms=timeout_ms,
                    )
                    message_ids = list(send_result.get("message_ids") or [])
                    if not message_ids and send_result.get("message_id"):
                        message_ids = [str(send_result.get("message_id"))]
                    for index, part in enumerate(parts):
                        if index < len(message_ids):
                            part["message_id"] = message_ids[index]
                except WeixinSendItemsError as exc:
                    for index, part in enumerate(parts):
                        if index < len(exc.message_ids):
                            part["message_id"] = exc.message_ids[index]
                        elif index == exc.failed_index:
                            part["ok"] = False
                            part["error"] = str(exc)
                        elif index > exc.failed_index:
                            part["ok"] = False
                            part["error"] = "Skipped because an earlier Weixin send failed."
                    raise
            elif rendered_text:
                parts.append(
                    {
                        "part": "text",
                        **self._send_text(
                            to_user_id=to_user_id,
                            context_token=context_token,
                            text=rendered_text,
                            base_url=base_url,
                            token=token,
                            route_tag=route_tag,
                            timeout_ms=timeout_ms,
                        ),
                    }
                )
            else:
                warnings.append("Weixin outbound payload contained neither text nor sendable attachments.")
        except Exception as exc:
            if "ret=-2" in str(exc or "").lower():
                mark_weixin_context_stale(
                    connector_root,
                    user_id=to_user_id,
                    error=str(exc),
                    kind=kind or None,
                )
                if kind in self._STALE_CONTEXT_SUPPRESSED_KINDS:
                    queued = self._queued_context_wait_response(
                        reason="Weixin send hit stale context and was deferred until the next inbound refresh.",
                    )
                    queued["parts"] = parts
                    queued["warnings"] = [*warnings, *(queued.get("warnings") or [])]
                    return queued
            return {
                "ok": False,
                "queued": False,
                "transport": "weixin-ilink",
                "parts": parts,
                "warnings": warnings,
                "error": str(exc),
            }

        succeeded = [item for item in parts if bool(item.get("ok"))]
        failed = [item for item in parts if not bool(item.get("ok"))]
        error_messages = [str(item.get("error") or "").strip() for item in failed if str(item.get("error") or "").strip()]
        error_messages.extend(warnings)
        last_success = succeeded[-1] if succeeded else {}
        if succeeded:
            clear_weixin_context_send_state(
                connector_root,
                user_id=to_user_id,
                kind=kind or None,
            )
        return {
            "ok": bool(succeeded),
            "queued": False,
            "partial": bool(succeeded and (failed or warnings)),
            "transport": "weixin-ilink",
            "message_id": last_success.get("message_id"),
            "parts": parts,
            "warnings": warnings,
            "error": "; ".join(error_messages) if error_messages else None,
        }

    @staticmethod
    def _queued_context_wait_response(*, reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "queued": True,
            "transport": "weixin-ilink",
            "parts": [],
            "warnings": [str(reason or "").strip()],
            "error": None,
        }

    @staticmethod
    def _partition_native_attachments(
        attachments: Any,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        native_items: list[dict[str, Any]] = []
        residual_items: list[dict[str, Any]] = []
        warnings: list[str] = []
        for index, raw_item in enumerate(attachments if isinstance(attachments, list) else [], start=1):
            if not isinstance(raw_item, dict):
                continue
            item = dict(raw_item)
            if str(item.get("path_error") or "").strip():
                warnings.append(f"attachment {index}: path resolution failed for {item.get('path')}")
                continue
            connector_delivery = item.get("connector_delivery") if isinstance(item.get("connector_delivery"), dict) else {}
            weixin_delivery = connector_delivery.get("weixin") if isinstance(connector_delivery.get("weixin"), dict) else {}
            media_kind = str(weixin_delivery.get("media_kind") or "").strip().lower()
            if media_kind in {"image", "video", "file"}:
                item["weixin_media_kind"] = media_kind
            if WeixinConnectorBridge._has_sendable_attachment_reference(item):
                native_items.append(item)
                continue
            if media_kind in {"image", "video", "file"}:
                warnings.append(
                    "attachment "
                    f"{index}: Weixin native media delivery was requested but no usable path/url/source_path/output_path/artifact_path was provided."
                )
            residual_items.append(item)
        return native_items, residual_items, warnings

    @staticmethod
    def _connector_root(config: dict[str, Any]) -> Path:
        raw = str(config.get("_connector_root") or "").strip()
        if raw:
            return ensure_dir(Path(raw))
        return ensure_dir(Path.cwd() / ".deepscientist-weixin")

    @staticmethod
    def _next_client_id() -> str:
        return f"openclaw-weixin:{int(time.time() * 1000)}-{os.urandom(4).hex()}"

    @classmethod
    def _item_type(cls, item: dict[str, Any]) -> int:
        return int(item.get("type") or 0)

    @classmethod
    def _is_media_item(cls, item: dict[str, Any]) -> bool:
        return cls._item_type(item) in cls._MEDIA_ITEM_TYPES

    @classmethod
    def _retry_delays_for_item(cls, item: dict[str, Any], exc: Exception) -> tuple[float, ...]:
        message = str(exc or "").strip().lower()
        if "ret=-2" not in message:
            return ()
        item_type = cls._item_type(item)
        if item_type in {4, 5}:
            return cls._MEDIA_SEND_RETRY_DELAYS_SECONDS
        if item_type == 1:
            return cls._TEXT_SEND_RETRY_DELAYS_SECONDS
        return ()

    def _send_items(
        self,
        *,
        to_user_id: str,
        context_token: str,
        item_list: list[dict[str, Any]],
        base_url: str,
        token: str,
        route_tag: str | None,
        timeout_ms: int,
    ) -> dict[str, Any]:
        if not item_list:
            return {"ok": False, "error": "Weixin outbound item_list is empty."}
        message_ids: list[str] = []
        for item in item_list:
            media_item = self._is_media_item(item)
            if media_item:
                time.sleep(self._MEDIA_SEND_INITIAL_DELAY_SECONDS)
            retry_delays: tuple[float, ...] = ()
            max_retries = max(len(self._TEXT_SEND_RETRY_DELAYS_SECONDS), len(self._MEDIA_SEND_RETRY_DELAYS_SECONDS))
            for attempt in range(1 + max_retries):
                client_id = self._next_client_id()
                try:
                    send_weixin_message(
                        base_url=base_url,
                        token=token,
                        route_tag=route_tag,
                        timeout_ms=timeout_ms,
                        body={
                            "msg": {
                                "from_user_id": "",
                                "to_user_id": to_user_id,
                                "client_id": client_id,
                                "message_type": 2,
                                "message_state": 2,
                                "context_token": context_token,
                                "item_list": [item],
                            }
                        },
                    )
                    message_ids.append(client_id)
                    break
                except Exception as exc:
                    retry_delays = self._retry_delays_for_item(item, exc)
                    if attempt >= len(retry_delays):
                        raise WeixinSendItemsError(
                            str(exc),
                            message_ids=message_ids,
                            failed_index=len(message_ids),
                        ) from exc
                    time.sleep(retry_delays[attempt])
        return {
            "ok": True,
            "message_id": message_ids[-1],
            "message_ids": message_ids,
        }

    def _send_text(
        self,
        *,
        to_user_id: str,
        context_token: str,
        text: str,
        base_url: str,
        token: str,
        route_tag: str | None,
        timeout_ms: int,
    ) -> dict[str, Any]:
        if not str(text or "").strip():
            return {"ok": False, "error": "Weixin text content is empty."}
        return self._send_items(
            to_user_id=to_user_id,
            context_token=context_token,
            item_list=[
                {
                    "type": 1,
                    "text_item": {"text": text},
                }
            ],
            base_url=base_url,
            token=token,
            route_tag=route_tag,
            timeout_ms=timeout_ms,
        )

    def _prepare_attachment_item(
        self,
        *,
        attachment: dict[str, Any],
        to_user_id: str,
        base_url: str,
        cdn_base_url: str,
        token: str,
        route_tag: str | None,
        timeout_ms: int,
        quest_root: Any,
        temp_dir: Path,
    ) -> tuple[str, dict[str, Any], Path]:
        resolved_path = self._resolve_attachment_path(attachment=attachment, quest_root=quest_root, temp_dir=temp_dir)
        media_type, message_item = self._build_media_item(
            attachment=attachment,
            file_path=resolved_path,
            to_user_id=to_user_id,
            base_url=base_url,
            cdn_base_url=cdn_base_url,
            token=token,
            route_tag=route_tag,
            timeout_ms=timeout_ms,
        )
        return media_type, message_item, resolved_path

    def _build_media_item(
        self,
        *,
        attachment: dict[str, Any],
        file_path: Path,
        to_user_id: str,
        base_url: str,
        cdn_base_url: str,
        token: str,
        route_tag: str | None,
        timeout_ms: int,
    ) -> tuple[str, dict[str, Any]]:
        requested_media_kind = str(attachment.get("weixin_media_kind") or "").strip().lower()
        content_type = str(attachment.get("content_type") or "").strip().lower()
        mime_type = content_type or str(mimetypes.guess_type(file_path.name)[0] or "application/octet-stream").lower()
        if requested_media_kind == "image" or (not requested_media_kind and mime_type.startswith("image/")):
            uploaded = upload_local_media_to_weixin(
                file_path=file_path,
                to_user_id=to_user_id,
                base_url=base_url,
                cdn_base_url=cdn_base_url,
                token=token,
                media_type=WEIXIN_UPLOAD_MEDIA_IMAGE,
                route_tag=route_tag,
                timeout_ms=timeout_ms,
            )
            return "image", {
                "type": 2,
                "image_item": {
                    "media": {
                        "encrypt_query_param": uploaded["download_param"],
                        "aes_key": uploaded["aes_key_base64"],
                        "encrypt_type": 1,
                    },
                    "mid_size": uploaded["ciphertext_size"],
                },
            }
        if requested_media_kind == "video" or (not requested_media_kind and mime_type.startswith("video/")):
            uploaded = upload_local_media_to_weixin(
                file_path=file_path,
                to_user_id=to_user_id,
                base_url=base_url,
                cdn_base_url=cdn_base_url,
                token=token,
                media_type=WEIXIN_UPLOAD_MEDIA_VIDEO,
                route_tag=route_tag,
                timeout_ms=timeout_ms,
            )
            return "video", {
                "type": 5,
                "video_item": {
                    "media": {
                        "encrypt_query_param": uploaded["download_param"],
                        "aes_key": uploaded["aes_key_base64"],
                        "encrypt_type": 1,
                    },
                    "video_size": uploaded["ciphertext_size"],
                },
            }
        uploaded = upload_local_media_to_weixin(
            file_path=file_path,
            to_user_id=to_user_id,
            base_url=base_url,
            cdn_base_url=cdn_base_url,
            token=token,
            media_type=WEIXIN_UPLOAD_MEDIA_FILE,
            route_tag=route_tag,
            timeout_ms=timeout_ms,
        )
        return "file", {
            "type": 4,
            "file_item": {
                "media": {
                    "encrypt_query_param": uploaded["download_param"],
                    "aes_key": uploaded["aes_key_base64"],
                    "encrypt_type": 1,
                },
                "file_name": file_path.name,
                "len": str(uploaded["file_size"]),
            },
        }

    @staticmethod
    def _has_sendable_attachment_reference(attachment: dict[str, Any]) -> bool:
        for key in ("path", "source_path", "output_path", "artifact_path", "url"):
            if str(attachment.get(key) or "").strip():
                return True
        return False

    def _resolve_attachment_path(self, *, attachment: dict[str, Any], quest_root: Any, temp_dir: Path) -> Path:
        base_root = Path(str(quest_root or "").strip()) if str(quest_root or "").strip() else Path.cwd()
        last_error: Exception | None = None
        for key in ("path", "source_path", "output_path", "artifact_path"):
            raw_path = str(attachment.get(key) or "").strip()
            if not raw_path:
                continue
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = (base_root / candidate).resolve()
            else:
                candidate = candidate.resolve()
            if not candidate.exists():
                last_error = FileNotFoundError(f"Weixin attachment {key} does not exist: {candidate}")
                continue
            if not candidate.is_file():
                last_error = IsADirectoryError(f"Weixin attachment {key} is not a file: {candidate}")
                continue
            return candidate
        raw_url = str(attachment.get("url") or "").strip()
        if raw_url:
            return download_weixin_remote_attachment(url=raw_url, dest_dir=temp_dir)
        if last_error is not None:
            raise last_error
        raise FileNotFoundError(
            "Weixin attachment requires a usable `path`, `source_path`, `output_path`, `artifact_path`, or `url`."
        )


class PassthroughConnectorBridge(BaseConnectorBridge):
    def parse_webhook(self, *, method: str, headers: dict[str, str], query: dict[str, list[str]], raw_body: bytes, body: dict[str, Any] | None, config: dict[str, Any]) -> BridgeWebhookResult:
        if method != "POST":
            return BridgeWebhookResult(ok=False, status_code=405, response_body={"ok": False, "message": "Method not allowed"})
        packet = body or self.parse_json_bytes(raw_body)
        if isinstance(packet.get("normalized"), dict):
            return BridgeWebhookResult(events=[packet["normalized"]])
        if isinstance(packet, dict):
            return BridgeWebhookResult(events=[packet])
        return BridgeWebhookResult(events=[])
