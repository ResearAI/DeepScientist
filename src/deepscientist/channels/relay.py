from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..connector_runtime import (
    build_discovered_target,
    conversation_identity_key,
    format_conversation_id,
    infer_connector_transport,
    merge_discovered_targets,
    parse_conversation_id,
)
from ..connector_profiles import (
    PROFILEABLE_CONNECTOR_NAMES,
    connector_profile_label,
    find_connector_profile,
    list_connector_profiles,
    merge_connector_profile_config,
)
from ..bridges import get_connector_bridge
from ..shared import append_jsonl, ensure_dir, generate_id, read_json, read_jsonl, utc_now, write_json
from .base import BaseChannel


class GenericRelayChannel(BaseChannel):
    display_mode = "user_facing_only"
    recent_conversation_limit = 20
    recent_event_limit = 12

    def __init__(self, home: Path, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(home)
        self.name = name
        self.config = config or {}
        self.root = ensure_dir(home / "logs" / "connectors" / name)
        self.inbox_path = self.root / "inbox.jsonl"
        self.outbox_path = self.root / "outbox.jsonl"
        self.ignored_path = self.root / "ignored.jsonl"
        self.bindings_path = self.root / "bindings.json"
        self.state_path = self.root / "state.json"

    def _profiles(self) -> list[dict[str, Any]]:
        if self.name not in PROFILEABLE_CONNECTOR_NAMES:
            return []
        return list_connector_profiles(self.name, self.config)

    def _should_encode_profile_id(self) -> bool:
        return len(self._profiles()) > 1

    def _conversation_id(self, chat_type: str, chat_id: str, *, profile_id: str | None = None) -> str:
        return format_conversation_id(
            self.name,
            chat_type,
            chat_id,
            profile_id=profile_id if self._should_encode_profile_id() else None,
        )

    def _profile(self, profile_id: str | None) -> dict[str, Any] | None:
        normalized = str(profile_id or "").strip() or None
        if normalized:
            return find_connector_profile(self.name, self.config, profile_id=normalized)
        profiles = self._profiles()
        if len(profiles) == 1:
            return profiles[0]
        return None

    def _profile_label(self, profile_id: str | None) -> str | None:
        profile = self._profile(profile_id)
        if profile is None:
            return None
        return connector_profile_label(self.name, profile)

    def _profile_runtime_state(self, profile_id: str | None = None) -> dict[str, Any]:
        runtime_path = self.root / "runtime.json"
        normalized = str(profile_id or "").strip()
        if normalized:
            runtime_path = self.root / "profiles" / normalized / "runtime.json"
        payload = read_json(runtime_path, {})
        return payload if isinstance(payload, dict) else {}

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        formatted = self._format_outbound(payload)
        record = {"sent_at": utc_now(), **formatted}
        try:
            delivery = self._deliver(record)
        except Exception as exc:  # pragma: no cover - defensive transport guard
            delivery = {
                "ok": False,
                "queued": False,
                "error": str(exc),
                "transport": f"{self.name}-bridge",
            }
        if not isinstance(delivery, dict):
            transport = infer_connector_transport(self.name, self.config)
            delivery = {
                "ok": False,
                "queued": False,
                "error": f"{self.name} outbound delivery has no active `{transport}` transport.",
                "transport": transport or f"{self.name}-bridge",
            }
        else:
            delivery = {
                **delivery,
                "ok": bool(delivery.get("ok", False)),
                "queued": bool(delivery.get("queued", False)),
                "transport": str(
                    delivery.get("transport")
                    or infer_connector_transport(self.name, self.config)
                    or f"{self.name}-bridge"
                ),
            }
        record["delivery"] = delivery
        append_jsonl(self.outbox_path, record)
        self._remember_conversation(
            conversation_id=record.get("conversation_id"),
            updated_at=str(record.get("sent_at") or utc_now()),
            source="outbound_delivery",
            quest_id=str(record.get("quest_id") or "").strip() or None,
        )
        return {
            "ok": bool(delivery.get("ok", False)),
            "queued": bool(delivery.get("queued", False)),
            "channel": self.name,
            "payload": record,
            "delivery": delivery,
        }

    def poll(self) -> list[dict[str, Any]]:
        return read_jsonl(self.inbox_path)

    def status(self) -> dict[str, Any]:
        bindings = self.list_bindings()
        state = self._read_state()
        runtime_state = self._profile_runtime_state()
        profiles = self._profiles()
        profile_states: dict[str, dict[str, Any]] = {}
        for profile in profiles:
            profile_id = str(profile.get("profile_id") or "").strip()
            profile_state = self._profile_runtime_state(profile_id)
            if not profile_state and len(profiles) == 1 and isinstance(runtime_state, dict):
                profile_state = runtime_state
            profile_states[profile_id] = profile_state
        runtime_last_conversation_candidates = [
            str((runtime_state or {}).get("last_conversation_id") or "").strip()
            if isinstance(runtime_state, dict)
            else "",
            *[
                str((profile_state or {}).get("last_conversation_id") or "").strip()
                for profile_state in profile_states.values()
                if isinstance(profile_state, dict)
            ],
        ]
        runtime_last_conversation_id = next((item for item in runtime_last_conversation_candidates if item), None)
        last_conversation_id = str((state or {}).get("last_conversation_id") or runtime_last_conversation_id or "").strip() or None
        profile_transports = [
            infer_connector_transport(
                self.name,
                merge_connector_profile_config(self.name, self.config, profile),
            )
            for profile in profiles
        ]
        if len(set(item for item in profile_transports if item)) == 1 and profile_transports:
            transport = profile_transports[0]
        elif profile_transports:
            transport = "mixed"
        else:
            transport = infer_connector_transport(self.name, self.config)
        default_conversation_id = last_conversation_id or (bindings[0]["conversation_id"] if bindings else None)
        recent_conversations = self._recent_conversations(state)
        known_targets = self._known_targets(state)
        discovered_targets = merge_discovered_targets(
            [
                *[
                    {
                        **(
                            build_discovered_target(
                                item.get("conversation_id"),
                                source=str(item.get("source") or "known_target"),
                                is_default=item.get("conversation_id") == default_conversation_id,
                                label=str(item.get("label") or "").strip() or None,
                                quest_id=str(item.get("quest_id") or "").strip() or None,
                                updated_at=str(item.get("updated_at") or "").strip() or None,
                                profile_id=str(item.get("profile_id") or "").strip() or None,
                                profile_label=str(item.get("profile_label") or "").strip() or self._profile_label(
                                    str(item.get("profile_id") or "").strip() or None
                                ),
                            )
                            or {}
                        ),
                        "first_seen_at": str(item.get("first_seen_at") or "").strip() or None,
                    }
                    for item in known_targets
                ],
                *[
                    build_discovered_target(
                        item.get("conversation_id"),
                        source=str(item.get("source") or "recent_activity"),
                        is_default=item.get("conversation_id") == default_conversation_id,
                        label=str(item.get("label") or "").strip() or None,
                        quest_id=str(item.get("quest_id") or "").strip() or None,
                        updated_at=str(item.get("updated_at") or "").strip() or None,
                        profile_id=str(item.get("profile_id") or "").strip() or None,
                        profile_label=str(item.get("profile_label") or "").strip() or self._profile_label(
                            str(item.get("profile_id") or "").strip() or None
                        ),
                    )
                    for item in recent_conversations
                ],
                *(
                    [
                        build_discovered_target(
                            runtime_last_conversation_id,
                            source="recent_runtime_activity",
                            is_default=runtime_last_conversation_id == default_conversation_id,
                            updated_at=str((runtime_state or {}).get("updated_at") or "").strip() or None,
                        )
                    ]
                    if runtime_last_conversation_id
                    else []
                ),
                *[
                    build_discovered_target(
                        str((profile_state or {}).get("last_conversation_id") or "").strip() or None,
                        source="recent_runtime_activity",
                        is_default=str((profile_state or {}).get("last_conversation_id") or "").strip() == default_conversation_id,
                        updated_at=str((profile_state or {}).get("updated_at") or "").strip() or None,
                        profile_id=profile_id or None,
                        profile_label=self._profile_label(profile_id),
                    )
                    for profile_id, profile_state in profile_states.items()
                ],
                *[
                    build_discovered_target(
                        item.get("conversation_id"),
                        source="quest_binding",
                        is_default=item.get("conversation_id") == default_conversation_id,
                        quest_id=str(item.get("quest_id") or "").strip() or None,
                        updated_at=str(item.get("updated_at") or "").strip() or None,
                        profile_id=str(item.get("profile_id") or "").strip() or None,
                        profile_label=str(item.get("profile_label") or "").strip() or self._profile_label(
                            str(item.get("profile_id") or "").strip() or None
                        ),
                    )
                    for item in bindings
                ],
            ]
        )
        default_target = next((item for item in discovered_targets if item.get("is_default")), None)
        def runtime_connection_state(
            *,
            config: dict[str, Any],
            runtime_snapshot: dict[str, Any],
            runtime_transport: str,
            last_seen_conversation_id: str | None,
        ) -> tuple[str, str]:
            connection_state = self._connection_state(runtime_transport, last_seen_conversation_id, config=config)
            auth_state = self._auth_state(runtime_transport, config=config)
            if (
                bool(config.get("enabled", False))
                and isinstance(runtime_snapshot, dict)
                and str(runtime_snapshot.get("transport") or "").strip() == runtime_transport
            ):
                snapshot_connection_state = str(runtime_snapshot.get("connection_state") or "").strip()
                snapshot_auth_state = str(runtime_snapshot.get("auth_state") or "").strip()
                if snapshot_connection_state:
                    connection_state = snapshot_connection_state
                elif runtime_snapshot.get("connected") is True:
                    connection_state = "connected"
                elif runtime_snapshot.get("last_error"):
                    connection_state = "error"
                if snapshot_auth_state:
                    auth_state = snapshot_auth_state
                elif runtime_snapshot.get("auth_ok") is True:
                    auth_state = "ready"
                elif runtime_snapshot.get("auth_ok") is False:
                    auth_state = "error"
            return connection_state, auth_state

        def matches_profile(item: dict[str, Any], profile_id: str) -> bool:
            item_profile_id = str(item.get("profile_id") or "").strip()
            return item_profile_id == profile_id or (not item_profile_id and len(profiles) == 1)

        profile_snapshots = []
        for profile in profiles:
            profile_id = str(profile.get("profile_id") or "").strip()
            profile_config = merge_connector_profile_config(self.name, self.config, profile)
            profile_transport = infer_connector_transport(self.name, profile_config)
            profile_runtime_state = profile_states.get(profile_id, {})
            profile_last_conversation_id = str(profile_runtime_state.get("last_conversation_id") or "").strip() or None
            profile_connection_state, profile_auth_state = runtime_connection_state(
                config=profile_config,
                runtime_snapshot=profile_runtime_state,
                runtime_transport=profile_transport,
                last_seen_conversation_id=profile_last_conversation_id,
            )
            profile_targets = [
                dict(item)
                for item in discovered_targets
                if matches_profile(item, profile_id)
            ]
            profile_recent_conversations = [
                dict(item)
                for item in recent_conversations
                if matches_profile(item, profile_id)
            ]
            profile_bindings = [
                dict(item)
                for item in bindings
                if matches_profile(item, profile_id)
            ]
            profile_snapshots.append(
                {
                    "profile_id": profile_id,
                    "label": connector_profile_label(self.name, profile),
                    "bot_name": str(profile.get("bot_name") or "").strip() or None,
                    "transport": profile_transport,
                    "last_conversation_id": profile_last_conversation_id,
                    "connection_state": profile_connection_state,
                    "auth_state": profile_auth_state,
                    "discovered_targets": profile_targets,
                    "recent_conversations": profile_recent_conversations,
                    "bindings": profile_bindings,
                    "target_count": len(profile_targets),
                    "binding_count": len(profile_bindings),
                    "last_error": profile_runtime_state.get("last_error") if isinstance(profile_runtime_state, dict) else None,
                }
            )

        if profile_snapshots:
            aggregate_connection_candidates = [
                str(item.get("connection_state") or "").strip()
                for item in profile_snapshots
                if str(item.get("connection_state") or "").strip()
            ]
            aggregate_auth_candidates = [
                str(item.get("auth_state") or "").strip()
                for item in profile_snapshots
                if str(item.get("auth_state") or "").strip()
            ]
            connection_state = next(
                (
                    candidate
                    for candidate in (
                        "connected",
                        "connecting",
                        "starting",
                        "configured",
                        "ready",
                        "awaiting_first_message",
                        "error",
                        "needs_credentials",
                        "disabled",
                    )
                    if candidate in aggregate_connection_candidates
                ),
                "disabled" if not bool(self.config.get("enabled", False)) else "configured",
            )
            auth_state = next(
                (
                    candidate
                    for candidate in (
                        "ready",
                        "configured",
                        "error",
                        "missing_credentials",
                        "missing_configuration",
                        "disabled",
                    )
                    if candidate in aggregate_auth_candidates
                ),
                "disabled" if not bool(self.config.get("enabled", False)) else "configured",
            )
        else:
            connection_state, auth_state = runtime_connection_state(
                config=self.config,
                runtime_snapshot=runtime_state,
                runtime_transport=transport,
                last_seen_conversation_id=last_conversation_id,
            )
        return {
            "name": self.name,
            "display_mode": self.display_mode,
            "mode": self.config.get("mode", transport),
            "transport": transport,
            "enabled": bool(self.config.get("enabled", False)),
            "connection_state": connection_state,
            "auth_state": auth_state,
            "last_conversation_id": last_conversation_id,
            "last_error": next(
                (
                    str(item.get("last_error") or "").strip()
                    for item in profile_snapshots
                    if str(item.get("last_error") or "").strip()
                ),
                str(runtime_state.get("last_error") or "").strip() or None if isinstance(runtime_state, dict) else None,
            ),
            "inbox_count": len(read_jsonl(self.inbox_path)),
            "outbox_count": len(read_jsonl(self.outbox_path)),
            "ignored_count": len(read_jsonl(self.ignored_path)),
            "binding_count": len(bindings),
            "bindings": bindings,
            "known_targets": known_targets,
            "recent_conversations": recent_conversations,
            "recent_events": self._recent_events(),
            "target_count": len(discovered_targets),
            "default_target": default_target,
            "discovered_targets": discovered_targets,
            "profiles": profile_snapshots,
        }

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = self.normalize_inbound(payload)
        if not normalized.get("accepted", False):
            append_jsonl(self.ignored_path, {"received_at": utc_now(), **normalized})
            return {"ok": True, "accepted": False, "normalized": normalized}
        append_jsonl(self.inbox_path, {"received_at": utc_now(), **normalized})
        self._remember_conversation(
            conversation_id=normalized.get("conversation_id"),
            updated_at=str(normalized.get("created_at") or utc_now()),
            source="recent_inbound",
            sender_id=str(normalized.get("sender_id") or "").strip() or None,
            sender_name=str(normalized.get("sender_name") or "").strip() or None,
            quest_id=str(normalized.get("quest_id") or "").strip() or None,
            message_id=str(normalized.get("message_id") or "").strip() or None,
            profile_id=str(normalized.get("profile_id") or "").strip() or None,
            profile_label=str(normalized.get("profile_label") or "").strip() or None,
        )
        return {"ok": True, "accepted": True, "normalized": normalized}

    def normalize_inbound(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("text") or payload.get("message") or payload.get("content") or "").strip()
        sender_id = str(payload.get("sender_id") or payload.get("from") or payload.get("user_id") or "").strip()
        sender_name = str(payload.get("sender_name") or payload.get("from_name") or payload.get("username") or sender_id).strip()
        group_id = str(payload.get("group_id") or payload.get("channel_id") or payload.get("room_id") or "").strip()
        direct_id = str(payload.get("direct_id") or payload.get("chat_id") or payload.get("peer_id") or sender_id).strip()
        chat_type = str(payload.get("chat_type") or ("group" if group_id else "direct")).strip().lower()
        if chat_type not in {"group", "direct"}:
            chat_type = "group" if group_id else "direct"
        chat_key = group_id if chat_type == "group" else direct_id
        parsed_conversation = parse_conversation_id(payload.get("conversation_id"))
        profile_id = str(payload.get("profile_id") or (parsed_conversation or {}).get("profile_id") or "").strip() or None
        profiles = self._profiles()
        if profile_id is None and len(profiles) == 1:
            profile_id = str(profiles[0].get("profile_id") or "").strip() or None
        profile_config = self._profile(profile_id)
        profile_label = self._profile_label(profile_id)
        conversation_id = str(
            payload.get("conversation_id")
            or self._conversation_id(chat_type, chat_key or "unknown", profile_id=profile_id)
        )
        message_id = str(payload.get("message_id") or payload.get("event_id") or generate_id(self.name))
        mentioned = bool(payload.get("mentioned")) or self._looks_like_mention(text, profile=profile_config)
        normalized_text = self._strip_mention_prefix(text, profile=profile_config)
        is_command = normalized_text.startswith(self.command_prefix())

        group_access = self._check_group_access(group_id=group_id, sender_id=sender_id)
        if chat_type == "group" and group_access is not None:
            return {
                "accepted": False,
                "reason": group_access,
                "conversation_id": conversation_id,
                "chat_type": chat_type,
                "message_id": message_id,
                "text": text,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "group_id": group_id,
                "profile_id": profile_id,
                "profile_label": profile_label,
            }

        dm_access = self._check_dm_access(sender_id=sender_id)
        if chat_type == "direct" and dm_access is not None:
            return {
                "accepted": False,
                "reason": dm_access,
                "conversation_id": conversation_id,
                "chat_type": chat_type,
                "message_id": message_id,
                "text": text,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "profile_id": profile_id,
                "profile_label": profile_label,
            }

        if chat_type == "group" and self.config.get("require_mention_in_groups", True) and not (mentioned or is_command):
            return {
                "accepted": False,
                "reason": "group_message_requires_mention",
                "conversation_id": conversation_id,
                "chat_type": chat_type,
                "message_id": message_id,
                "text": text,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "profile_id": profile_id,
                "profile_label": profile_label,
            }

        return {
            "accepted": True,
            "channel": self.name,
            "conversation_id": conversation_id,
            "chat_type": chat_type,
            "message_id": message_id,
            "text": normalized_text,
            "raw_text": text,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "group_id": group_id or None,
            "direct_id": direct_id or None,
            "mentioned": mentioned,
            "is_command": is_command,
            "profile_id": profile_id,
            "profile_label": profile_label,
            "created_at": utc_now(),
            "raw_event": payload,
        }

    def bind_conversation(self, conversation_id: str, quest_id: str) -> dict[str, Any]:
        bindings = read_json(self.bindings_path, {"bindings": {}})
        binding_map = dict(bindings.get("bindings") or {})
        parsed = parse_conversation_id(conversation_id)
        profile_id = str((parsed or {}).get("profile_id") or "").strip() or None
        binding_map[conversation_id] = {
            "quest_id": quest_id,
            "updated_at": utc_now(),
            "profile_id": profile_id,
            "profile_label": self._profile_label(profile_id),
        }
        bindings["bindings"] = binding_map
        write_json(self.bindings_path, bindings)
        self._remember_conversation(
            conversation_id=conversation_id,
            updated_at=str(binding_map[conversation_id].get("updated_at") or utc_now()),
            source="quest_binding",
            quest_id=quest_id,
            profile_id=profile_id,
            profile_label=str(binding_map[conversation_id].get("profile_label") or "").strip() or None,
        )
        return binding_map[conversation_id]

    def unbind_conversation(self, conversation_id: str, *, quest_id: str | None = None) -> bool:
        bindings = read_json(self.bindings_path, {"bindings": {}})
        binding_map = dict(bindings.get("bindings") or {})
        existing = binding_map.get(conversation_id)
        if quest_id and isinstance(existing, dict) and str(existing.get("quest_id") or "").strip() != quest_id:
            return False
        if conversation_id not in binding_map:
            return False
        binding_map.pop(conversation_id, None)
        bindings["bindings"] = binding_map
        write_json(self.bindings_path, bindings)
        return True

    def resolve_bound_quest(self, conversation_id: str) -> str | None:
        bindings = read_json(self.bindings_path, {"bindings": {}})
        item = (bindings.get("bindings") or {}).get(conversation_id)
        if not isinstance(item, dict):
            return None
        quest_id = item.get("quest_id")
        return str(quest_id) if quest_id else None

    def list_bindings(self) -> list[dict[str, Any]]:
        bindings = read_json(self.bindings_path, {"bindings": {}})
        items: list[dict[str, Any]] = []
        for conversation_id, payload in sorted((bindings.get("bindings") or {}).items()):
            if not isinstance(payload, dict):
                continue
            parsed = parse_conversation_id(conversation_id)
            profile_id = str((parsed or {}).get("profile_id") or payload.get("profile_id") or "").strip() or None
            items.append(
                {
                    "conversation_id": conversation_id,
                    "profile_id": profile_id,
                    "profile_label": str(payload.get("profile_label") or "").strip() or self._profile_label(profile_id),
                    **payload,
                }
            )
        return items

    def command_prefix(self) -> str:
        return str(self.config.get("command_prefix") or "/").strip() or "/"

    def _looks_like_mention(self, text: str, *, profile: dict[str, Any] | None = None) -> bool:
        lowered = (text or "").lower()
        profile_config = profile or {}
        bot_name = str(profile_config.get("bot_name") or self.config.get("bot_name") or "DeepScientist").strip().lower()
        return f"@{bot_name}" in lowered

    def _strip_mention_prefix(self, text: str, *, profile: dict[str, Any] | None = None) -> str:
        cleaned = str(text or "").strip()
        profile_config = profile or {}
        bot_name = str(profile_config.get("bot_name") or self.config.get("bot_name") or "DeepScientist").strip()
        prefix = f"@{bot_name}"
        if cleaned.startswith(prefix):
            return cleaned[len(prefix):].strip()
        return cleaned

    def _format_outbound(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("message") or "").strip()
        kind = str(payload.get("kind") or "message").strip()
        attachments = self._normalize_attachments(payload.get("attachments"))
        return {
            "conversation_id": payload.get("conversation_id"),
            "reply_to_message_id": payload.get("reply_to_message_id"),
            "kind": kind,
            "text": text,
            "attachments": attachments,
            "surface_actions": [dict(item) for item in (payload.get("surface_actions") or []) if isinstance(item, dict)],
            "quest_id": payload.get("quest_id"),
            "quest_root": payload.get("quest_root"),
            "importance": payload.get("importance"),
            "response_phase": payload.get("response_phase"),
        }

    @staticmethod
    def _normalize_attachments(value: Any) -> list[dict[str, Any]]:
        attachments: list[dict[str, Any]] = []
        if not isinstance(value, list):
            return attachments
        for item in value:
            if isinstance(item, str):
                attachments.append({"kind": "path", "path": item})
            elif isinstance(item, dict):
                attachments.append(dict(item))
        return attachments

    def _check_dm_access(self, *, sender_id: str) -> str | None:
        policy = str(self.config.get("dm_policy") or "pairing").strip().lower()
        allow_from = self._list_values(self.config.get("allow_from"))
        if policy == "disabled":
            return "direct_messages_disabled"
        if policy == "allowlist" and not self._matches_allowlist(sender_id, allow_from):
            return "direct_sender_not_allowlisted"
        if policy == "open":
            return None
        if policy == "pairing":
            return None
        return None

    def _check_group_access(self, *, group_id: str, sender_id: str) -> str | None:
        groups = self._list_values(self.config.get("groups"))
        if groups and "*" not in groups and (not group_id or group_id not in groups):
            return "group_not_allowlisted"
        policy = str(self.config.get("group_policy") or "open").strip().lower()
        group_allow_from = self._list_values(self.config.get("group_allow_from"))
        allow_from = self._list_values(self.config.get("allow_from"))
        effective_allow_from = group_allow_from or allow_from
        if policy == "disabled":
            return "group_messages_disabled"
        if policy == "allowlist" and not self._matches_allowlist(sender_id, effective_allow_from):
            return "group_sender_not_allowlisted"
        return None

    @staticmethod
    def _list_values(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        items: list[str] = []
        for item in value:
            normalized = str(item or "").strip()
            if normalized:
                items.append(normalized)
        return items

    @staticmethod
    def _matches_allowlist(sender_id: str, allow_from: list[str]) -> bool:
        normalized_sender = str(sender_id or "").strip()
        if not normalized_sender:
            return False
        if "*" in allow_from:
            return True
        return normalized_sender in allow_from

    def _deliver(self, record: dict[str, Any]) -> dict[str, Any] | None:
        delivery_config = self.config
        parsed = parse_conversation_id(record.get("conversation_id"))
        profile_id = str((parsed or {}).get("profile_id") or "").strip() or None
        profile = self._profile(profile_id)
        if profile is not None:
            delivery_config = merge_connector_profile_config(self.name, self.config, profile)
        bridge = get_connector_bridge(self.name)
        if bridge is not None:
            delivery = bridge.deliver(record, delivery_config)
            if delivery is not None:
                return delivery
        return None

    def _read_state(self) -> dict[str, Any]:
        payload = read_json(self.state_path, {})
        return payload if isinstance(payload, dict) else {}

    def _write_state(self, payload: dict[str, Any]) -> None:
        write_json(self.state_path, payload)

    def _recent_conversations(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        items = state.get("recent_conversations")
        if not isinstance(items, list):
            return []
        merged: dict[str, dict[str, Any]] = {}
        for raw in items:
            if not isinstance(raw, dict):
                continue
            conversation_id = str(raw.get("conversation_id") or "").strip()
            if not conversation_id:
                continue
            identity = conversation_identity_key(conversation_id)
            existing = merged.get(identity)
            current = dict(raw)
            if existing is None:
                merged[identity] = current
                continue
            if str(current.get("updated_at") or "") >= str(existing.get("updated_at") or ""):
                merged[identity] = {**existing, **current}
            else:
                merged[identity] = {**current, **existing}
        ordered = sorted(
            merged.values(),
            key=lambda item: (str(item.get("updated_at") or ""), str(item.get("conversation_id") or "")),
            reverse=True,
        )
        return ordered[: self.recent_conversation_limit]

    def _remember_conversation(
        self,
        *,
        conversation_id: Any,
        updated_at: str,
        source: str,
        sender_id: str | None = None,
        sender_name: str | None = None,
        quest_id: str | None = None,
        message_id: str | None = None,
        profile_id: str | None = None,
        profile_label: str | None = None,
    ) -> None:
        entry = self._build_recent_conversation_entry(
            conversation_id=conversation_id,
            updated_at=updated_at,
            source=source,
            sender_id=sender_id,
            sender_name=sender_name,
            quest_id=quest_id,
            message_id=message_id,
            profile_id=profile_id,
            profile_label=profile_label,
        )
        if entry is None:
            return
        state = self._read_state()
        state["last_conversation_id"] = entry["conversation_id"]
        if message_id:
            state["last_message_id"] = message_id
        state["updated_at"] = updated_at
        state["recent_conversations"] = self._recent_conversations(
            {
                "recent_conversations": [entry, *list(state.get("recent_conversations") or [])],
            }
        )
        state["known_targets"] = self._upsert_known_targets(state, entry)
        self._write_state(state)

    def _build_recent_conversation_entry(
        self,
        *,
        conversation_id: Any,
        updated_at: str,
        source: str,
        sender_id: str | None = None,
        sender_name: str | None = None,
        quest_id: str | None = None,
        message_id: str | None = None,
        profile_id: str | None = None,
        profile_label: str | None = None,
    ) -> dict[str, Any] | None:
        parsed = parse_conversation_id(conversation_id)
        if parsed is None:
            return None
        payload: dict[str, Any] = {
            **parsed,
            "label": self._conversation_label(
                chat_type=parsed["chat_type"],
                chat_id=parsed["chat_id"],
                sender_name=sender_name,
            ),
            "updated_at": updated_at,
            "source": source,
        }
        resolved_profile_id = str(profile_id or parsed.get("profile_id") or "").strip() or None
        resolved_profile_label = str(profile_label or "").strip() or self._profile_label(resolved_profile_id)
        if resolved_profile_id:
            payload["profile_id"] = resolved_profile_id
        if resolved_profile_label:
            payload["profile_label"] = resolved_profile_label
        if sender_id:
            payload["sender_id"] = sender_id
        if sender_name:
            payload["sender_name"] = sender_name
        if quest_id:
            payload["quest_id"] = quest_id
        if message_id:
            payload["message_id"] = message_id
        return payload

    def _known_targets(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        items = state.get("known_targets")
        if not isinstance(items, list):
            return []
        merged: dict[str, dict[str, Any]] = {}
        for raw in items:
            if not isinstance(raw, dict):
                continue
            conversation_id = str(raw.get("conversation_id") or "").strip()
            if not conversation_id:
                continue
            identity = conversation_identity_key(conversation_id)
            current = dict(raw)
            current["conversation_id"] = conversation_id
            existing = merged.get(identity)
            if existing is None:
                merged[identity] = current
                continue
            merged_entry = {**existing, **current}
            merged_entry["first_seen_at"] = (
                str(existing.get("first_seen_at") or "").strip()
                or str(current.get("first_seen_at") or "").strip()
                or str(existing.get("updated_at") or "").strip()
                or str(current.get("updated_at") or "").strip()
            )
            if str(existing.get("updated_at") or "") > str(current.get("updated_at") or ""):
                merged_entry["updated_at"] = existing.get("updated_at")
            merged[identity] = merged_entry
        return sorted(
            merged.values(),
            key=lambda item: (str(item.get("updated_at") or ""), str(item.get("conversation_id") or "")),
            reverse=True,
        )

    def _upsert_known_targets(self, state: dict[str, Any], entry: dict[str, Any]) -> list[dict[str, Any]]:
        identity = conversation_identity_key(entry.get("conversation_id"))
        items = list(state.get("known_targets") or [])
        next_items: list[dict[str, Any]] = []
        replaced = False
        for raw in items:
            if not isinstance(raw, dict):
                continue
            if conversation_identity_key(raw.get("conversation_id")) != identity:
                next_items.append(dict(raw))
                continue
            merged = {**raw, **entry}
            merged["first_seen_at"] = (
                str(raw.get("first_seen_at") or "").strip()
                or str(entry.get("first_seen_at") or "").strip()
                or str(raw.get("updated_at") or "").strip()
                or str(entry.get("updated_at") or "").strip()
            )
            next_items.append(merged)
            replaced = True
        if not replaced:
            next_items.append(
                {
                    **entry,
                    "first_seen_at": str(entry.get("updated_at") or "").strip() or utc_now(),
                }
            )
        return self._known_targets({"known_targets": next_items})

    @staticmethod
    def _conversation_label(*, chat_type: str, chat_id: str, sender_name: str | None = None) -> str:
        if sender_name and str(chat_type or "").strip().lower() == "direct":
            return f"{sender_name} · {chat_id}"
        return f"{chat_type} · {chat_id}"

    def _recent_events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for record in read_jsonl(self.inbox_path)[-self.recent_event_limit :]:
            event = self._build_recent_event("inbound", record)
            if event is not None:
                events.append(event)
        for record in read_jsonl(self.outbox_path)[-self.recent_event_limit :]:
            event = self._build_recent_event("outbound", record)
            if event is not None:
                events.append(event)
        for record in read_jsonl(self.ignored_path)[-self.recent_event_limit :]:
            event = self._build_recent_event("ignored", record)
            if event is not None:
                events.append(event)
        events.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("conversation_id") or "")), reverse=True)
        return events[: self.recent_event_limit]

    def _build_recent_event(self, event_type: str, record: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(record, dict):
            return None
        conversation_id = str(record.get("conversation_id") or "").strip()
        parsed = parse_conversation_id(conversation_id) if conversation_id else None
        delivery = record.get("delivery") if isinstance(record.get("delivery"), dict) else {}
        chat_type = str((parsed or {}).get("chat_type") or record.get("chat_type") or "direct")
        chat_id = str((parsed or {}).get("chat_id") or record.get("chat_id") or "unknown")
        return {
            "event_type": event_type,
            "created_at": str(record.get("received_at") or record.get("sent_at") or record.get("created_at") or record.get("updated_at") or utc_now()),
            "conversation_id": conversation_id or None,
            "chat_type": chat_type,
            "chat_id": chat_id,
            "label": self._conversation_label(
                chat_type=chat_type,
                chat_id=chat_id,
                sender_name=str(record.get("sender_name") or "").strip() or None,
            ),
            "kind": str(record.get("kind") or "").strip() or None,
            "message": self._event_preview(
                str(record.get("text") or record.get("message") or record.get("raw_text") or "").strip()
            )
            or None,
            "reason": str(record.get("reason") or "").strip() or None,
            "ok": bool(delivery.get("ok", False)) if event_type == "outbound" else None,
            "queued": bool(delivery.get("queued", False)) if event_type == "outbound" else None,
            "transport": str(delivery.get("transport") or "").strip() or None,
        }

    @staticmethod
    def _event_preview(text: str, *, limit: int = 140) -> str:
        normalized = " ".join(str(text or "").split())
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[: max(limit - 1, 0)].rstrip()}…"

    def _connection_state(self, transport: str, last_conversation_id: str | None, *, config: dict[str, Any] | None = None) -> str:
        payload = config or self.config
        if not bool(payload.get("enabled", False)):
            return "disabled"
        if self._has_runtime_credentials(transport, config=payload):
            return "ready" if last_conversation_id else "configured"
        return "needs_credentials"

    def _auth_state(self, transport: str, *, config: dict[str, Any] | None = None) -> str:
        payload = config or self.config
        if not bool(payload.get("enabled", False)):
            return "disabled"
        return "ready" if self._has_runtime_credentials(transport, config=payload) else "missing_credentials"

    def _has_runtime_credentials(self, transport: str, *, config: dict[str, Any] | None = None) -> bool:
        payload = config or self.config
        if self.name == "telegram":
            return bool(self._secret("bot_token", "bot_token_env", config=payload))
        if self.name == "discord":
            return bool(self._secret("bot_token", "bot_token_env", config=payload))
        if self.name == "slack":
            if transport == "socket_mode":
                return bool(
                    self._secret("bot_token", "bot_token_env", config=payload)
                    and self._secret("app_token", "app_token_env", config=payload)
                )
            return bool(self._secret("bot_token", "bot_token_env", config=payload))
        if self.name == "feishu":
            return bool(str(payload.get("app_id") or "").strip() and self._secret("app_secret", "app_secret_env", config=payload))
        if self.name == "whatsapp":
            if transport == "local_session":
                return bool(str(payload.get("session_dir") or "").strip())
            return bool(
                self._secret("access_token", "access_token_env", config=payload)
                and str(payload.get("phone_number_id") or "").strip()
            )
        return False

    def _secret(self, key: str, env_key: str, *, config: dict[str, Any] | None = None) -> str:
        payload = config or self.config
        direct = str(payload.get(key) or "").strip()
        if direct:
            return direct
        env_name = str(payload.get(env_key) or "").strip()
        if not env_name:
            return ""
        return str(os.environ.get(env_name) or "").strip()
