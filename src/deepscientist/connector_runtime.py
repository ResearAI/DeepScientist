from __future__ import annotations

from typing import Any


CONNECTOR_PROFILE_CHAT_ID_SEPARATOR = "::"
QQ_PROFILE_CHAT_ID_SEPARATOR = CONNECTOR_PROFILE_CHAT_ID_SEPARATOR


def infer_connector_transport(name: str, config: dict[str, Any] | None) -> str:
    normalized = str(name or "").strip().lower()
    payload = config or {}
    explicit = str(payload.get("transport") or "").strip().lower()
    if explicit and explicit not in {
        "relay",
        "legacy_webhook",
        "legacy_interactions",
        "legacy_events_api",
        "legacy_meta_cloud",
    }:
        return explicit

    if normalized == "qq":
        return "gateway_direct"
    if normalized == "telegram":
        return "polling"
    if normalized == "discord":
        return "gateway"
    if normalized == "slack":
        if str(payload.get("app_token") or "").strip():
            return "socket_mode"
        return "socket_mode"
    if normalized == "feishu":
        return "long_connection"
    if normalized == "whatsapp":
        return "local_session"
    if normalized == "lingzhu":
        return "openclaw_sse"
    return "direct"


def _decode_chat_id(*, connector: str, chat_id: str) -> tuple[str | None, str]:
    if CONNECTOR_PROFILE_CHAT_ID_SEPARATOR not in chat_id:
        return None, chat_id
    profile_id, resolved_chat_id = chat_id.split(CONNECTOR_PROFILE_CHAT_ID_SEPARATOR, 1)
    normalized_profile_id = str(profile_id or "").strip() or None
    normalized_chat_id = str(resolved_chat_id or "").strip() or chat_id
    return normalized_profile_id, normalized_chat_id


def encode_chat_id(*, connector: str, chat_id: Any, profile_id: Any = None) -> str:
    normalized_chat_id = str(chat_id or "").strip()
    if not normalized_chat_id:
        return ""
    normalized_profile_id = str(profile_id or "").strip()
    if not normalized_profile_id:
        return normalized_chat_id
    return f"{normalized_profile_id}{CONNECTOR_PROFILE_CHAT_ID_SEPARATOR}{normalized_chat_id}"


def format_conversation_id(connector: str, chat_type: str, chat_id: Any, *, profile_id: Any = None) -> str:
    normalized_connector = str(connector or "").strip().lower()
    normalized_chat_type = str(chat_type or "").strip().lower()
    encoded_chat_id = encode_chat_id(connector=normalized_connector, chat_id=chat_id, profile_id=profile_id)
    return f"{normalized_connector}:{normalized_chat_type}:{encoded_chat_id}"


def parse_conversation_id(conversation_id: Any) -> dict[str, str] | None:
    raw = str(conversation_id or "").strip()
    parts = raw.split(":", 2)
    if len(parts) != 3:
        return None
    connector, chat_type, chat_id = parts
    if not connector or not chat_type or not chat_id:
        return None
    profile_id, resolved_chat_id = _decode_chat_id(connector=connector, chat_id=chat_id)
    return {
        "conversation_id": raw,
        "connector": connector,
        "chat_type": chat_type,
        "chat_id": resolved_chat_id,
        "chat_id_raw": chat_id,
        "profile_id": profile_id or "",
    }


def normalize_conversation_id(conversation_id: Any) -> str:
    raw = str(conversation_id or "").strip()
    if not raw:
        return "local:default"
    lowered = raw.lower()
    if lowered in {"web", "cli", "api", "command", "local", "local-ui", "tui-ink", "tui-textual", "web-react", "tui-local"}:
        return "local:default"
    parsed = parse_conversation_id(raw)
    if parsed is not None:
        return format_conversation_id(
            parsed["connector"].lower(),
            parsed["chat_type"].lower(),
            parsed["chat_id"],
            profile_id=parsed.get("profile_id") or None,
        )
    if ":" in raw:
        return raw
    return f"{lowered}:default"


def conversation_identity_key(conversation_id: Any) -> str:
    normalized = normalize_conversation_id(conversation_id)
    parsed = parse_conversation_id(normalized)
    if parsed is None:
        return normalized.lower()
    profile_key = str(parsed.get("profile_id") or "").strip().lower()
    return ":".join(
        item
        for item in (
            parsed["connector"].lower(),
            profile_key,
            parsed["chat_type"].lower(),
            parsed["chat_id"].lower(),
        )
        if item
    )


def build_discovered_target(
    conversation_id: Any,
    *,
    source: str,
    is_default: bool = False,
    label: str | None = None,
    quest_id: str | None = None,
    updated_at: str | None = None,
    profile_id: str | None = None,
    profile_label: str | None = None,
) -> dict[str, Any] | None:
    parsed = parse_conversation_id(conversation_id)
    if parsed is None:
        return None
    target = {
        **parsed,
        "source": source,
        "sources": [source],
        "label": label or f"{parsed['chat_type']} · {parsed['chat_id']}",
    }
    if profile_id or parsed.get("profile_id"):
        target["profile_id"] = str(profile_id or parsed.get("profile_id") or "").strip() or None
    if profile_label:
        target["profile_label"] = profile_label
    if is_default:
        target["is_default"] = True
    if quest_id:
        target["quest_id"] = quest_id
    if updated_at:
        target["updated_at"] = updated_at
    return target


def merge_discovered_targets(items: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        conversation_id = str(item.get("conversation_id") or "").strip()
        if not conversation_id:
            continue
        identity = conversation_identity_key(conversation_id)
        existing = merged.get(identity)
        if existing is None:
            merged[identity] = dict(item)
            continue
        sources = list(existing.get("sources") or [])
        for source in item.get("sources") or []:
            normalized = str(source or "").strip()
            if normalized and normalized not in sources:
                sources.append(normalized)
        existing["sources"] = sources
        existing["is_default"] = bool(existing.get("is_default")) or bool(item.get("is_default"))
        if not existing.get("quest_id") and item.get("quest_id"):
            existing["quest_id"] = item["quest_id"]
        if not existing.get("updated_at") and item.get("updated_at"):
            existing["updated_at"] = item["updated_at"]
        elif item.get("updated_at") and str(item["updated_at"]) > str(existing.get("updated_at") or ""):
            existing["updated_at"] = item["updated_at"]
        if existing.get("label") == f"{existing.get('chat_type')} · {existing.get('chat_id')}" and item.get("label"):
            existing["label"] = item["label"]
        if not existing.get("source") and item.get("source"):
            existing["source"] = item["source"]
        for key, value in item.items():
            if key in {
                "conversation_id",
                "connector",
                "chat_type",
                "chat_id",
                "sources",
                "is_default",
                "quest_id",
                "updated_at",
                "label",
                "source",
            }:
                continue
            if value is None:
                continue
            if key not in existing or existing.get(key) in {None, ""}:
                existing[key] = value
                continue
            if key in {"bound_quest_id", "bound_quest_title", "warning", "first_seen_at"}:
                existing[key] = value

    return sorted(
        merged.values(),
        key=lambda item: (
            0 if item.get("is_default") else 1,
            0 if str(item.get("chat_type") or "") == "direct" else 1,
            str(item.get("conversation_id") or ""),
        ),
    )
