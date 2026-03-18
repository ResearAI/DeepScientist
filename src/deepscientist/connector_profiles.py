from __future__ import annotations

from copy import deepcopy
from typing import Any

from .connector_runtime import infer_connector_transport
from .shared import slugify


PROFILEABLE_CONNECTOR_NAMES = ("telegram", "discord", "slack", "feishu", "whatsapp")


CONNECTOR_PROFILE_SPECS: dict[str, dict[str, Any]] = {
    "telegram": {
        "profile_id_prefix": "telegram-profile",
        "shared_fields": (
            "enabled",
            "profiles",
            "transport",
            "bot_name",
            "bot_token",
            "bot_token_env",
            "command_prefix",
            "dm_policy",
            "allow_from",
            "group_policy",
            "group_allow_from",
            "groups",
            "require_mention_in_groups",
            "auto_bind_dm_to_active_quest",
        ),
        "profile_defaults": {
            "profile_id": None,
            "enabled": True,
            "transport": "polling",
            "bot_name": "DeepScientist",
            "bot_token": None,
            "bot_token_env": "TELEGRAM_BOT_TOKEN",
        },
        "profile_fields": (
            "enabled",
            "transport",
            "bot_name",
            "bot_token",
            "bot_token_env",
        ),
        "migration_keys": ("bot_token",),
        "label_fields": ("bot_name",),
        "id_fields": ("bot_name",),
    },
    "discord": {
        "profile_id_prefix": "discord-profile",
        "shared_fields": (
            "enabled",
            "profiles",
            "transport",
            "bot_name",
            "bot_token",
            "bot_token_env",
            "command_prefix",
            "application_id",
            "dm_policy",
            "allow_from",
            "group_policy",
            "group_allow_from",
            "groups",
            "require_mention_in_groups",
            "auto_bind_dm_to_active_quest",
            "guild_allowlist",
        ),
        "profile_defaults": {
            "profile_id": None,
            "enabled": True,
            "transport": "gateway",
            "bot_name": "DeepScientist",
            "bot_token": None,
            "bot_token_env": "DISCORD_BOT_TOKEN",
            "application_id": None,
        },
        "profile_fields": (
            "enabled",
            "transport",
            "bot_name",
            "bot_token",
            "bot_token_env",
            "application_id",
        ),
        "migration_keys": ("bot_token", "application_id"),
        "label_fields": ("bot_name", "application_id"),
        "id_fields": ("application_id", "bot_name"),
    },
    "slack": {
        "profile_id_prefix": "slack-profile",
        "shared_fields": (
            "enabled",
            "profiles",
            "transport",
            "bot_name",
            "bot_token",
            "bot_token_env",
            "bot_user_id",
            "app_token",
            "app_token_env",
            "command_prefix",
            "dm_policy",
            "allow_from",
            "group_policy",
            "group_allow_from",
            "groups",
            "require_mention_in_groups",
            "auto_bind_dm_to_active_quest",
        ),
        "profile_defaults": {
            "profile_id": None,
            "enabled": True,
            "transport": "socket_mode",
            "bot_name": "DeepScientist",
            "bot_token": None,
            "bot_token_env": "SLACK_BOT_TOKEN",
            "bot_user_id": None,
            "app_token": None,
            "app_token_env": "SLACK_APP_TOKEN",
        },
        "profile_fields": (
            "enabled",
            "transport",
            "bot_name",
            "bot_token",
            "bot_token_env",
            "bot_user_id",
            "app_token",
            "app_token_env",
        ),
        "migration_keys": ("bot_token", "bot_user_id", "app_token"),
        "label_fields": ("bot_name", "bot_user_id"),
        "id_fields": ("bot_user_id", "bot_name"),
    },
    "feishu": {
        "profile_id_prefix": "feishu-profile",
        "shared_fields": (
            "enabled",
            "profiles",
            "transport",
            "bot_name",
            "app_id",
            "app_secret",
            "app_secret_env",
            "api_base_url",
            "command_prefix",
            "dm_policy",
            "allow_from",
            "group_policy",
            "group_allow_from",
            "groups",
            "require_mention_in_groups",
            "auto_bind_dm_to_active_quest",
        ),
        "profile_defaults": {
            "profile_id": None,
            "enabled": True,
            "transport": "long_connection",
            "bot_name": "DeepScientist",
            "app_id": None,
            "app_secret": None,
            "app_secret_env": "FEISHU_APP_SECRET",
            "api_base_url": "https://open.feishu.cn",
        },
        "profile_fields": (
            "enabled",
            "transport",
            "bot_name",
            "app_id",
            "app_secret",
            "app_secret_env",
            "api_base_url",
        ),
        "migration_keys": ("app_id", "app_secret"),
        "label_fields": ("bot_name", "app_id"),
        "id_fields": ("app_id", "bot_name"),
    },
    "whatsapp": {
        "profile_id_prefix": "whatsapp-profile",
        "shared_fields": (
            "enabled",
            "profiles",
            "transport",
            "bot_name",
            "auth_method",
            "session_dir",
            "command_prefix",
            "dm_policy",
            "allow_from",
            "group_policy",
            "group_allow_from",
            "groups",
            "auto_bind_dm_to_active_quest",
        ),
        "profile_defaults": {
            "profile_id": None,
            "enabled": True,
            "transport": "local_session",
            "bot_name": "DeepScientist",
            "auth_method": "qr_browser",
            "session_dir": "~/.deepscientist/connectors/whatsapp",
        },
        "profile_fields": (
            "enabled",
            "transport",
            "bot_name",
            "auth_method",
            "session_dir",
        ),
        "migration_keys": ("session_dir",),
        "label_fields": ("bot_name",),
        "id_fields": ("bot_name",),
    },
}


def _as_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _profile_seed(connector_name: str, raw: dict[str, Any], *, index: int) -> str:
    spec = CONNECTOR_PROFILE_SPECS[connector_name]
    explicit = _as_text(raw.get("profile_id"))
    if explicit:
        return explicit
    for key in spec["id_fields"]:
        candidate = _as_text(raw.get(key))
        if candidate:
            return f"{connector_name}-{candidate}"
    return f"{spec['profile_id_prefix']}-{index:03d}"


def _unique_profile_id(seed: str, *, prefix: str, used: set[str]) -> str:
    base = slugify(seed, default=prefix)
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def default_connector_profile(connector_name: str) -> dict[str, Any]:
    spec = CONNECTOR_PROFILE_SPECS[connector_name]
    return deepcopy(spec["profile_defaults"])


def connector_profile_label(connector_name: str, profile: dict[str, Any] | None) -> str:
    if not isinstance(profile, dict):
        return connector_name.capitalize()
    spec = CONNECTOR_PROFILE_SPECS[connector_name]
    parts = [_as_text(profile.get(key)) for key in spec["label_fields"]]
    filtered = [item for item in parts if item]
    return " · ".join(filtered) if filtered else connector_name.capitalize()


def normalize_connector_config(connector_name: str, config: dict[str, Any] | None) -> dict[str, Any]:
    if connector_name not in CONNECTOR_PROFILE_SPECS:
        raise KeyError(f"Connector `{connector_name}` does not support generic profile normalization.")
    spec = CONNECTOR_PROFILE_SPECS[connector_name]
    payload = deepcopy(config or {})
    shared = {
        key: deepcopy(payload.get(key))
        for key in spec["shared_fields"]
        if key in payload
    }
    shared["profiles"] = []

    raw_profiles = payload.get("profiles")
    items = list(raw_profiles) if isinstance(raw_profiles, list) else []
    if not items and any(_as_text(payload.get(key)) for key in spec["migration_keys"]):
        items = [{key: payload.get(key) for key in spec["profile_fields"]}]

    used_ids: set[str] = set()
    profiles: list[dict[str, Any]] = []
    for index, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            continue
        current = default_connector_profile(connector_name)
        for key in ("profile_id", *spec["profile_fields"]):
            if key in raw:
                current[key] = deepcopy(raw.get(key))
        current["enabled"] = bool(current.get("enabled", True))
        for key in spec["profile_fields"]:
            if key in {"enabled", "transport", "mode"}:
                continue
            if isinstance(current.get(key), list):
                continue
            if current.get(key) is None:
                continue
            current[key] = _as_text(current.get(key))
        current["transport"] = infer_connector_transport(connector_name, current)
        if "mode" in spec["profile_defaults"] or current.get("mode") is not None:
            current["mode"] = _as_text(current.get("mode")) or str(spec["profile_defaults"].get("mode") or "")
        current["profile_id"] = _unique_profile_id(
            _profile_seed(connector_name, current, index=index),
            prefix=str(spec["profile_id_prefix"]),
            used=used_ids,
        )
        profiles.append(current)

    shared["transport"] = infer_connector_transport(connector_name, shared)
    shared["profiles"] = profiles
    if len(profiles) == 1:
        for key in spec["profile_fields"]:
            shared[key] = profiles[0].get(key)
    return shared


def list_connector_profiles(connector_name: str, config: dict[str, Any] | None) -> list[dict[str, Any]]:
    normalized = normalize_connector_config(connector_name, config)
    profiles = normalized.get("profiles")
    return [dict(item) for item in profiles] if isinstance(profiles, list) else []


def find_connector_profile(
    connector_name: str,
    config: dict[str, Any] | None,
    *,
    profile_id: str | None = None,
) -> dict[str, Any] | None:
    normalized_profile_id = _as_text(profile_id)
    for profile in list_connector_profiles(connector_name, config):
        if normalized_profile_id and str(profile.get("profile_id") or "").strip() == normalized_profile_id:
            return profile
    return None


def merge_connector_profile_config(
    connector_name: str,
    shared_config: dict[str, Any] | None,
    profile: dict[str, Any],
) -> dict[str, Any]:
    normalized = normalize_connector_config(connector_name, shared_config)
    merged = deepcopy(normalized)
    merged.pop("profiles", None)
    for key in CONNECTOR_PROFILE_SPECS[connector_name]["profile_fields"]:
        merged[key] = profile.get(key)
    merged["profile_id"] = str(profile.get("profile_id") or "").strip() or None
    merged["enabled"] = bool(normalized.get("enabled", False)) and bool(profile.get("enabled", True))
    return merged
