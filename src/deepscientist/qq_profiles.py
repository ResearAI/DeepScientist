from __future__ import annotations

from copy import deepcopy
from typing import Any

from .shared import slugify


QQ_PROFILE_ID_PREFIX = "qq-profile"
QQ_DEFAULT_SECRET_ENV = "QQ_APP_SECRET"


def default_qq_profile() -> dict[str, Any]:
    return {
        "profile_id": None,
        "enabled": True,
        "app_id": None,
        "app_secret": None,
        "app_secret_env": QQ_DEFAULT_SECRET_ENV,
        "bot_name": "DeepScientist",
        "main_chat_id": None,
    }


def _as_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _profile_id_seed(*, profile_id: Any, app_id: Any, bot_name: Any, index: int) -> str:
    explicit = _as_text(profile_id)
    if explicit:
        return explicit
    app_text = _as_text(app_id)
    if app_text:
        return f"qq-{app_text}"
    bot_text = slugify(str(bot_name or "").strip(), default="")
    if bot_text:
        return f"{QQ_PROFILE_ID_PREFIX}-{bot_text}"
    return f"{QQ_PROFILE_ID_PREFIX}-{index:03d}"


def _unique_profile_id(seed: str, *, used: set[str]) -> str:
    base = slugify(seed, default=QQ_PROFILE_ID_PREFIX)
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def list_qq_profiles(config: dict[str, Any] | None) -> list[dict[str, Any]]:
    normalized = normalize_qq_connector_config(config)
    profiles = normalized.get("profiles")
    return [dict(item) for item in profiles] if isinstance(profiles, list) else []


def find_qq_profile(
    config: dict[str, Any] | None,
    *,
    profile_id: str | None = None,
    app_id: str | None = None,
) -> dict[str, Any] | None:
    normalized_profile_id = _as_text(profile_id)
    normalized_app_id = _as_text(app_id)
    for profile in list_qq_profiles(config):
        if normalized_profile_id and str(profile.get("profile_id") or "").strip() == normalized_profile_id:
            return profile
        if normalized_app_id and str(profile.get("app_id") or "").strip() == normalized_app_id:
            return profile
    return None


def merge_qq_profile_config(shared_config: dict[str, Any] | None, profile: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_qq_connector_config(shared_config)
    merged = deepcopy(normalized)
    merged.pop("profiles", None)
    merged.update(
        {
            "profile_id": str(profile.get("profile_id") or "").strip() or None,
            "app_id": _as_text(profile.get("app_id")),
            "app_secret": _as_text(profile.get("app_secret")),
            "app_secret_env": _as_text(profile.get("app_secret_env")) or QQ_DEFAULT_SECRET_ENV,
            "bot_name": _as_text(profile.get("bot_name")) or str(normalized.get("bot_name") or "DeepScientist"),
            "main_chat_id": _as_text(profile.get("main_chat_id")),
            "enabled": bool(normalized.get("enabled", False)) and bool(profile.get("enabled", True)),
            "transport": "gateway_direct",
        }
    )
    return merged


def qq_profile_label(profile: dict[str, Any] | None) -> str:
    if not isinstance(profile, dict):
        return "QQ"
    bot_name = _as_text(profile.get("bot_name"))
    app_id = _as_text(profile.get("app_id"))
    if bot_name and app_id:
        return f"{bot_name} · {app_id}"
    if bot_name:
        return bot_name
    if app_id:
        return f"QQ · {app_id}"
    return "QQ"


def normalize_qq_connector_config(config: dict[str, Any] | None) -> dict[str, Any]:
    payload = deepcopy(config or {})
    shared_defaults = {
        "enabled": False,
        "transport": "gateway_direct",
        "app_id": None,
        "app_secret": None,
        "app_secret_env": QQ_DEFAULT_SECRET_ENV,
        "bot_name": "DeepScientist",
        "command_prefix": "/",
        "main_chat_id": None,
        "require_at_in_groups": True,
        "auto_bind_dm_to_active_quest": True,
        "gateway_restart_on_config_change": True,
        "auto_send_main_experiment_png": True,
        "auto_send_analysis_summary_png": True,
        "auto_send_slice_png": True,
        "auto_send_paper_pdf": True,
        "enable_markdown_send": False,
        "enable_file_upload_experimental": False,
        "profiles": [],
    }
    shared = {**shared_defaults, **payload}
    shared["transport"] = "gateway_direct"
    shared["command_prefix"] = _as_text(shared.get("command_prefix")) or "/"
    shared["bot_name"] = _as_text(shared.get("bot_name")) or "DeepScientist"
    shared["app_secret_env"] = _as_text(shared.get("app_secret_env")) or QQ_DEFAULT_SECRET_ENV

    raw_profiles = payload.get("profiles")
    items = list(raw_profiles) if isinstance(raw_profiles, list) else []
    legacy_profile_seed = {
        "app_id": payload.get("app_id"),
        "app_secret": payload.get("app_secret"),
        "app_secret_env": payload.get("app_secret_env"),
        "bot_name": payload.get("bot_name"),
        "main_chat_id": payload.get("main_chat_id"),
    }
    if not items:
        if any(_as_text(legacy_profile_seed.get(key)) for key in ("app_id", "app_secret", "main_chat_id", "bot_name")):
            items = [legacy_profile_seed]

    profiles: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for index, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            continue
        current = {**default_qq_profile(), **raw}
        current["enabled"] = bool(current.get("enabled", True))
        current["app_id"] = _as_text(current.get("app_id"))
        current["app_secret"] = _as_text(current.get("app_secret"))
        current["app_secret_env"] = _as_text(current.get("app_secret_env")) or shared["app_secret_env"]
        current["bot_name"] = _as_text(current.get("bot_name")) or shared["bot_name"]
        current["main_chat_id"] = _as_text(current.get("main_chat_id"))
        current["profile_id"] = _unique_profile_id(
            _profile_id_seed(
                profile_id=current.get("profile_id"),
                app_id=current.get("app_id"),
                bot_name=current.get("bot_name"),
                index=index,
            ),
            used=used_ids,
        )
        profiles.append(current)

    shared["profiles"] = profiles
    if len(profiles) == 1:
        mirror = profiles[0]
        shared["app_id"] = mirror.get("app_id")
        shared["app_secret"] = mirror.get("app_secret")
        shared["app_secret_env"] = mirror.get("app_secret_env")
        shared["bot_name"] = mirror.get("bot_name")
        shared["main_chat_id"] = mirror.get("main_chat_id")
    else:
        shared["app_id"] = None
        shared["app_secret"] = None
        shared["main_chat_id"] = None

    return shared
