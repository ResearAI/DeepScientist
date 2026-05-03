from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..runners.metadata import get_runner_metadata, list_builtin_runner_names

CONFIG_NAMES = ("config", "runners", "connectors", "plugins", "mcp_servers")
REQUIRED_CONFIG_NAMES = ("config", "runners", "connectors")
OPTIONAL_CONFIG_NAMES = ("plugins", "mcp_servers")
SYSTEM_CONNECTOR_NAMES = ("qq", "weixin", "telegram", "discord", "slack", "feishu", "whatsapp", "lingzhu")


@dataclass(frozen=True)
class ConfigFileInfo:
    name: str
    path: Path
    required: bool
    exists: bool


def config_filename(name: str) -> str:
    return f"{name}.yaml"


def default_system_enabled_connectors() -> dict[str, bool]:
    return {name: name in {"qq", "weixin", "telegram", "feishu", "whatsapp", "lingzhu"} for name in SYSTEM_CONNECTOR_NAMES}


def default_config(home: Path) -> dict:
    return {
        "home": str(home),
        "default_runner": "codex",
        "default_locale": "zh-CN",
        "daemon": {
            "session_restore_on_start": True,
            "max_concurrent_quests": 1,
            "ack_timeout_ms": 1000,
        },
        "ui": {
            "host": "0.0.0.0",
            "port": 20999,
            "auth_enabled": False,
            "auto_open_browser": True,
            "default_mode": "web",
        },
        "logging": {
            "level": "info",
            "console": True,
            "keep_days": 30,
        },
        "hardware": {
            "gpu_selection_mode": "all",
            "selected_gpu_ids": [],
            "include_system_hardware_in_prompt": False,
        },
        "memory": {
            "read_visibility_mode": "independent",
        },
        "literature": {
            "deepxiv": {
                "enabled": False,
                "base_url": "https://data.rag.ac.cn",
                "token": None,
                "token_env": "DEEPXIV_TOKEN",
                "default_result_size": 10,
                "preview_characters": 1200,
                "request_timeout_seconds": 20,
            },
        },
        "git": {
            "auto_checkpoint": True,
            "auto_push": False,
            "default_remote": "origin",
            "graph_formats": ["svg", "png", "json"],
        },
        "skills": {
            "sync_global_on_init": True,
            "sync_quest_on_create": True,
            "sync_quest_on_open": True,
        },
        "bootstrap": {
            "runner_readiness": {
                name: {
                    "ready": False,
                    "last_checked_at": None,
                    "last_result": {},
                }
                for name in list_builtin_runner_names()
            },
            "codex_ready": False,
            "codex_last_checked_at": None,
            "codex_last_result": {},
            "locale_source": "default",
            "locale_initialized_from_browser": False,
            "locale_initialized_at": None,
            "locale_initialized_browser_locale": None,
        },
        "connectors": {
            "auto_ack": True,
            "milestone_push": True,
            "direct_chat_enabled": True,
            "system_enabled": default_system_enabled_connectors(),
        },
        "cloud": {
            "enabled": False,
            "base_url": "https://deepscientist.cc",
            "token": None,
            "token_env": "DEEPSCIENTIST_TOKEN",
            "verify_token_on_start": False,
            "sync_mode": "disabled",
        },
        "acp": {
            "compatibility_profile": "deepscientist-acp-compat/v1",
            "events_transport": "rest-poll",
            "sdk_bridge_enabled": False,
            "sdk_module": "acp",
        },
    }


def default_runners() -> dict:
    codex = get_runner_metadata("codex")
    claude = get_runner_metadata("claude")
    kimi = get_runner_metadata("kimi")
    opencode = get_runner_metadata("opencode")
    return {
        "codex": {
            "enabled": True,
            "binary": codex.default_binary,
            "config_dir": codex.default_config_dir,
            "profile": "",
            "model": "inherit",
            "model_reasoning_effort": "xhigh",
            "approval_policy": "never",
            "sandbox_mode": "danger-full-access",
            "retry_on_failure": True,
            "retry_max_attempts": 7,
            "retry_initial_backoff_sec": 10.0,
            "retry_backoff_multiplier": 6.0,
            "retry_max_backoff_sec": 1800.0,
            "mcp_tool_timeout_sec": 172800,
            "env": {},
        },
        "claude": {
            "enabled": False,
            "binary": claude.default_binary,
            "config_dir": claude.default_config_dir,
            "model": "inherit",
            "permission_mode": "bypassPermissions",
            "mcp_timeout_ms": 172800000,
            "mcp_tool_timeout_ms": 172800000,
            "retry_on_failure": True,
            "retry_max_attempts": 4,
            "retry_initial_backoff_sec": 10.0,
            "retry_backoff_multiplier": 4.0,
            "retry_max_backoff_sec": 600.0,
            "env": {},
            "status": "supported_experimental",
        },
        "kimi": {
            "enabled": False,
            "binary": kimi.default_binary,
            "config_dir": kimi.default_config_dir,
            "model": "inherit",
            "agent": "",
            "thinking": False,
            "yolo": True,
            "mcp_tool_timeout_ms": 172800000,
            "retry_on_failure": True,
            "retry_max_attempts": 4,
            "retry_initial_backoff_sec": 10.0,
            "retry_backoff_multiplier": 4.0,
            "retry_max_backoff_sec": 600.0,
            "env": {},
            "status": "supported_experimental",
        },
        "opencode": {
            "enabled": False,
            "binary": opencode.default_binary,
            "config_dir": opencode.default_config_dir,
            "model": "inherit",
            "permission_mode": "allow",
            "default_agent": "",
            "variant": "",
            "mcp_timeout_ms": 172800000,
            "retry_on_failure": True,
            "retry_max_attempts": 4,
            "retry_initial_backoff_sec": 10.0,
            "retry_backoff_multiplier": 4.0,
            "retry_max_backoff_sec": 600.0,
            "env": {},
            "status": "supported_experimental",
        },
    }


def default_connectors() -> dict:
    return {
        "_routing": {
            "primary_connector": None,
            "artifact_delivery_policy": "fanout_all",
        },
        "qq": {
            "enabled": False,
            "transport": "gateway_direct",
            "profiles": [],
            "app_id": None,
            "app_secret": None,
            "app_secret_env": None,
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
        },
        "weixin": {
            "enabled": False,
            "transport": "ilink_long_poll",
            "bot_name": "DeepScientist",
            "command_prefix": "/",
            "auto_send_main_experiment_png": True,
            "stale_replay_latest_limit": 5,
            "stale_replay_interval_seconds": 2.0,
            "base_url": "https://ilinkai.weixin.qq.com",
            "cdn_base_url": "https://novac2c.cdn.weixin.qq.com/c2c",
            "bot_type": "3",
            "bot_token": None,
            "bot_token_env": None,
            "account_id": None,
            "login_user_id": None,
            "route_tag": None,
            "dm_policy": "pairing",
            "allow_from": [],
            "group_policy": "disabled",
            "group_allow_from": [],
            "groups": [],
            "auto_bind_dm_to_active_quest": True,
        },
        "telegram": {
            "enabled": False,
            "profiles": [],
            "transport": "polling",
            "bot_name": "DeepScientist",
            "command_prefix": "/",
            "bot_token": None,
            "bot_token_env": None,
            "dm_policy": "pairing",
            "allow_from": [],
            "group_policy": "open",
            "group_allow_from": [],
            "groups": [],
            "require_mention_in_groups": True,
            "auto_bind_dm_to_active_quest": True,
        },
        "discord": {
            "enabled": False,
            "profiles": [],
            "transport": "gateway",
            "bot_name": "DeepScientist",
            "command_prefix": "/",
            "bot_token": None,
            "bot_token_env": None,
            "application_id": None,
            "dm_policy": "pairing",
            "allow_from": [],
            "group_policy": "open",
            "group_allow_from": [],
            "groups": [],
            "require_mention_in_groups": True,
            "auto_bind_dm_to_active_quest": True,
            "guild_allowlist": [],
        },
        "slack": {
            "enabled": False,
            "profiles": [],
            "transport": "socket_mode",
            "bot_name": "DeepScientist",
            "command_prefix": "/",
            "bot_token": None,
            "bot_token_env": None,
            "bot_user_id": None,
            "app_token": None,
            "app_token_env": None,
            "dm_policy": "pairing",
            "allow_from": [],
            "group_policy": "open",
            "group_allow_from": [],
            "groups": [],
            "require_mention_in_groups": True,
            "auto_bind_dm_to_active_quest": True,
        },
        "feishu": {
            "enabled": False,
            "profiles": [],
            "transport": "long_connection",
            "bot_name": "DeepScientist",
            "command_prefix": "/",
            "app_id": None,
            "app_secret": None,
            "app_secret_env": None,
            "api_base_url": "https://open.feishu.cn",
            "dm_policy": "pairing",
            "allow_from": [],
            "group_policy": "open",
            "group_allow_from": [],
            "groups": [],
            "require_mention_in_groups": True,
            "auto_bind_dm_to_active_quest": True,
        },
        "whatsapp": {
            "enabled": False,
            "profiles": [],
            "transport": "local_session",
            "bot_name": "DeepScientist",
            "command_prefix": "/",
            "auth_method": "qr_browser",
            "session_dir": "~/.deepscientist/connectors/whatsapp",
            "dm_policy": "pairing",
            "allow_from": [],
            "group_policy": "allowlist",
            "group_allow_from": [],
            "groups": [],
            "auto_bind_dm_to_active_quest": True,
        },
        "lingzhu": {
            "enabled": False,
            "transport": "openclaw_sse",
            "local_host": "127.0.0.1",
            "gateway_port": 18789,
            "public_base_url": None,
            "auth_ak": None,
            "agent_id": "main",
            "include_metadata": True,
            "request_timeout_ms": 60000,
            "system_prompt": "",
            "default_navigation_mode": "0",
            "enable_follow_up": True,
            "follow_up_max_count": 3,
            "max_image_bytes": 5242880,
            "session_mode": "per_user",
            "session_namespace": "lingzhu",
            "auto_receipt_ack": True,
            "visible_progress_heartbeat": True,
            "visible_progress_heartbeat_sec": 10,
            "debug_logging": False,
            "debug_log_payloads": False,
            "debug_log_dir": None,
            "enable_experimental_native_actions": False,
        },
    }


def default_plugins(home: Path) -> dict:
    return {
        "load_paths": [str(home / "plugins")],
        "enabled": [],
        "disabled": [],
        "allow_unsigned": False,
    }


def default_mcp_servers() -> dict:
    return {"servers": {}}


def default_payload(name: str, home: Path) -> dict:
    if name == "config":
        return default_config(home)
    if name == "runners":
        return default_runners()
    if name == "connectors":
        return default_connectors()
    if name == "plugins":
        return default_plugins(home)
    if name == "mcp_servers":
        return default_mcp_servers()
    raise KeyError(name)
