from __future__ import annotations

import base64
from collections import deque
from dataclasses import dataclass
import faulthandler
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import signal
import shutil
import subprocess
import sys
import threading
import time
import traceback
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request

from .. import __version__
from ..annotations import AnnotationService
from ..admin import AdminTaskService
from ..admin.repairs import AdminRepairService
from ..admin.service import AdminService
from ..acp import build_session_update
from ..artifact import ArtifactService
from ..benchstore import BenchStoreService
from ..bash_exec import BashExecService
from ..bash_exec.models import TerminalClient
from ..bash_exec.service import DEFAULT_TERMINAL_SESSION_ID
from ..bridges import register_builtin_connector_bridges
from ..bridges.connectors import QQConnectorBridge
from ..channels import QQRelayChannel, get_channel_factory, list_channel_names, register_builtin_channels
from ..channels.discord_gateway import DiscordGatewayService
from ..channels.feishu_long_connection import FeishuLongConnectionService
from ..channels.qq_gateway import QQGatewayService
from ..channels.slack_socket import SlackSocketModeService
from ..channels.telegram_polling import TelegramPollingService
from ..channels.weixin_ilink import WeixinIlinkService
from ..channels.whatsapp_local_session import WhatsAppLocalSessionService
from ..cloud import CloudLinkService
from ..connector.connector_profiles import (
    CONNECTOR_PROFILE_SPECS,
    PROFILEABLE_CONNECTOR_NAMES,
    connector_profile_label,
    list_connector_profiles,
    merge_connector_profile_config,
    normalize_connector_config,
)
from ..connector_runtime import conversation_identity_key, format_conversation_id, normalize_conversation_id, parse_conversation_id
from ..config import ConfigManager
from ..config.models import SYSTEM_CONNECTOR_NAMES
from ..diagnostics import FailureDiagnosis, diagnose_runner_failure
from ..home import repo_root
from ..memory import MemoryService
from ..network import urlopen_with_proxy as urlopen
from ..latex_runtime import QuestLatexService
from ..connector.lingzhu_support import (
    lingzhu_detect_tool_call_from_text,
    lingzhu_normalize_command_text,
    lingzhu_extract_task_text,
    lingzhu_extract_user_text,
    lingzhu_health_payload,
    lingzhu_is_passive_conversation_id,
    lingzhu_passive_conversation_id,
    lingzhu_request_conversation_id,
    lingzhu_request_sender_id,
    lingzhu_sse_answer,
    lingzhu_sse_tool_call,
    lingzhu_surface_action_tool_call,
    lingzhu_verify_auth_header,
)
from ..prompts import PromptBuilder
from ..prompts.builder import classify_turn_intent, current_standard_skills
from ..connector.qq_profiles import list_qq_profiles, merge_qq_profile_config, normalize_qq_connector_config
from ..quest import QuestService
from ..runners import ClaudeRunner, CodexRunner, OpenCodeRunner, RunRequest, get_runner_factory, register_builtin_runners
from ..runners.metadata import get_runner_metadata
from ..runtime_logs import JsonlLogger
from ..shared import append_jsonl, ensure_dir, generate_id, iter_jsonl, read_json, read_jsonl, read_jsonl_tail, read_text, resolve_within, run_command, slugify, utc_now, utf8_text_subprocess_kwargs, which, write_json
from ..skills import SkillInstaller
from ..team import SingleTeamService
from ..connector.weixin_support import (
    DEFAULT_WEIXIN_BOT_TYPE,
    fetch_weixin_qrcode,
    get_weixin_replay_cursor,
    normalize_weixin_base_url,
    normalize_weixin_cdn_base_url,
    poll_weixin_qrcode_status,
    update_weixin_replay_cursor,
)
from .api import ApiHandlers, match_route
from .sessions import SessionStore
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request as WebSocketRequest
from websockets.http11 import Response
from websockets.sync.server import Server as WebSocketServer
from websockets.sync.server import ServerConnection, serve as websocket_serve

TERMINAL_STREAM_IDLE_SLEEP_SECONDS = 0.02
_AUTO_CONTINUE_DELAY_SECONDS = 240.0
_AUTO_CONTINUE_ACTIVE_WORK_DELAY_SECONDS = 0.2
_TERMINAL_PREWARM_DEBOUNCE_SECONDS = 20.0
_STALLED_RUNNING_TURN_INACTIVITY_SECONDS = 30 * 60
_STALLED_RUNNING_TURN_INTERRUPT_TIMEOUT_SECONDS = 5.0
_IMMEDIATE_READ_INTERRUPT_TIMEOUT_SECONDS = 5.0
_RESUME_CONTINUE_TEXT = "Continue"
CODEX_RETRY_DEFAULT_MAX_ATTEMPTS = 7
PREVIOUS_CODEX_RETRY_DEFAULT_MAX_ATTEMPTS = 5
CODEX_RETRY_DEFAULT_INITIAL_BACKOFF_SEC = 10.0
CODEX_RETRY_DEFAULT_BACKOFF_MULTIPLIER = 6.0
CODEX_RETRY_DEFAULT_MAX_BACKOFF_SEC = 1800.0
LEGACY_CODEX_RETRY_INITIAL_BACKOFF_SEC = 1.0
LEGACY_CODEX_RETRY_BACKOFF_MULTIPLIER = 2.0
LEGACY_CODEX_RETRY_MAX_BACKOFF_SEC = 8.0
_CRASH_AUTO_RESUME_COOLDOWN = timedelta(minutes=10)
_CRASH_AUTO_RESUME_MAX_RECENT_ATTEMPTS = 2
_CHINESE_DIGIT_MAP = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CHINESE_UNIT_MAP = {
    "十": 10,
    "百": 100,
    "千": 1000,
}
_LINGZHU_SHORT_COMMAND_DIRECT_MAP = {
    "帮助": "help",
    "列表": "list",
    "状态": "status",
    "总结": "summary",
    "图谱": "graph",
    "指标": "metrics",
}
_LINGZHU_SHORT_COMMAND_PREFIX_MAP = {
    "绑定": "use",
    "新建": "new",
    "删除": "delete",
    "暂停": "stop",
    "恢复": "resume",
}
_LINGZHU_SHORT_LATEST_ALIASES = {"latest", "newest", "最新", "最新的"}
_WEIXIN_STALE_REPLAY_LIMIT_DEFAULT = 5
_WEIXIN_STALE_REPLAY_INTERVAL_SECONDS_DEFAULT = 2.0
_LINGZHU_DELETE_CONFIRM_ALIASES = {"确认", "强制", "--yes", "-y"}
_BROWSER_AUTH_COOKIE_NAME = "ds_local_auth"
_BROWSER_AUTH_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365
_BROWSER_AUTH_QUERY_PARAM = "token"
_BROWSER_AUTH_STORAGE_KEY = "ds_local_auth_token"
_BROWSER_AUTH_PUBLIC_ROUTE_NAMES = {"root", "spa_root", "ui_asset", "asset", "auth_login"}
_BROWSER_AUTH_EXEMPT_ROUTE_NAMES = {"lingzhu_health", "lingzhu_sse"}
_BROWSER_AUTH_REALM = "DeepScientist"


@dataclass(frozen=True)
class BrowserAuthState:
    authenticated: bool
    token_source: str | None = None
    response_cookie: str | None = None


def _windows_hidden_subprocess_kwargs() -> dict[str, object]:
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW")}
    return {}


class DaemonApp:
    _MAX_INBOUND_ATTACHMENT_BYTES = 25 * 1024 * 1024

    def __init__(
        self,
        home: Path,
        *,
        browser_auth_enabled: bool | None = None,
        browser_auth_token: str | None = None,
        prompt_version_selection: str | None = None,
    ) -> None:
        self.home = home.resolve()
        self.daemon_id = str(os.environ.get("DS_DAEMON_ID") or "").strip() or generate_id("daemon")
        self.daemon_managed_by = str(os.environ.get("DS_DAEMON_MANAGED_BY") or "manual").strip() or "manual"
        self.repo_root = repo_root()
        self.config_manager = ConfigManager(home)
        self.runtime_config = self.config_manager.load_runtime_config()
        self.runners_config = self.config_manager.load_runners_config()
        self.connectors_config = self.config_manager.load_named_normalized("connectors")
        self.skill_installer = SkillInstaller(self.repo_root, home)
        self.quest_service = QuestService(home, skill_installer=self.skill_installer)
        self.latex_service = QuestLatexService(self.quest_service)
        self.memory_service = MemoryService(home)
        self.annotation_service = AnnotationService(home)
        self.artifact_service = ArtifactService(home)
        self.benchstore_service = BenchStoreService(home, repo_root=self.repo_root)
        self.bash_exec_service = BashExecService(home)
        self.team_service = SingleTeamService(home)
        self.cloud_service = CloudLinkService(home)
        config = self.runtime_config
        skill_config = config.get("skills") if isinstance(config.get("skills"), dict) else {}
        self.skill_sync_summary = self.skill_installer.ensure_release_sync(
            installed_version=__version__,
            sync_global_enabled=bool(skill_config.get("sync_global_on_init", True)),
            sync_existing_quests_enabled=bool(skill_config.get("sync_quest_on_open", True)),
        )
        self.logger = JsonlLogger(home / "logs", level=config.get("logging", {}).get("level", "info"))
        self.admin_task_service = AdminTaskService(
            home,
            repo_root=self.repo_root,
            logger=self.logger,
            system_update_status_fn=self.system_update_status,
            system_update_action_fn=self.request_system_update,
        )
        self.admin_task_service.logger = self.logger
        self.admin_repair_service = AdminRepairService(self)
        self.admin_service = AdminService(self)
        self.reconciled_quests = self.quest_service.reconcile_runtime_state()
        for item in self.reconciled_quests:
            self.logger.log(
                "warning",
                "quest.runtime_reconciled",
                quest_id=item.get("quest_id"),
                previous_status=item.get("previous_status"),
                abandoned_run_id=item.get("abandoned_run_id"),
                status=item.get("status"),
            )
        self.prompt_builder = PromptBuilder(
            self.repo_root,
            home,
            prompt_version_selection=prompt_version_selection,
        )
        self.codex_runner = CodexRunner(
            home=home,
            repo_root=self.repo_root,
            binary=self.runners_config.get("codex", {}).get("binary", "codex"),
            logger=self.logger,
            prompt_builder=self.prompt_builder,
            artifact_service=self.artifact_service,
        )
        self.claude_runner = ClaudeRunner(
            home=home,
            repo_root=self.repo_root,
            binary=self.runners_config.get("claude", {}).get("binary", "claude"),
            logger=self.logger,
            prompt_builder=self.prompt_builder,
            artifact_service=self.artifact_service,
        )
        self.opencode_runner = OpenCodeRunner(
            home=home,
            repo_root=self.repo_root,
            binary=self.runners_config.get("opencode", {}).get("binary", "opencode"),
            logger=self.logger,
            prompt_builder=self.prompt_builder,
            artifact_service=self.artifact_service,
        )
        register_builtin_runners(
            codex_runner=self.codex_runner,
            claude_runner=self.claude_runner,
            opencode_runner=self.opencode_runner,
        )
        register_builtin_connector_bridges()
        register_builtin_channels(home=home, connectors_config=self.connectors_config)
        self.runners = {
            name: self._create_runner(name)
            for name in ("codex", "claude", "opencode")
        }
        self.channels = {name: self._create_channel(name) for name in list_channel_names()}
        self.sessions = SessionStore()
        self._canonicalize_lingzhu_binding_state()
        self._turn_lock = threading.Lock()
        self._turn_state: dict[str, dict[str, object]] = {}
        self._terminal_prewarm_lock = threading.Lock()
        self._terminal_prewarm_recent: dict[str, float] = {}
        self._server: ThreadingHTTPServer | None = None
        self._terminal_attach_server: WebSocketServer | None = None
        self._terminal_attach_thread: threading.Thread | None = None
        self._terminal_attach_host: str | None = None
        self._terminal_attach_port: int | None = None
        self._serve_host: str | None = None
        self._serve_port: int | None = None
        self._shutdown_requested = threading.Event()
        self._qq_gateways: dict[str, QQGatewayService] = {}
        self._weixin_ilink: WeixinIlinkService | None = None
        self._telegram_polling: dict[str, TelegramPollingService] = {}
        self._slack_socket: dict[str, SlackSocketModeService] = {}
        self._discord_gateway: dict[str, DiscordGatewayService] = {}
        self._feishu_long_connection: dict[str, FeishuLongConnectionService] = {}
        self._whatsapp_local_session: dict[str, WhatsAppLocalSessionService] = {}
        self._weixin_login_sessions: dict[str, dict[str, Any]] = {}
        self._process_hooks_installed = False
        self._faulthandler_stream = None
        self._recovered_quest_ids: set[str] = set()
        ui_config = config.get("ui") if isinstance(config.get("ui"), dict) else {}
        configured_browser_auth_enabled = self._parse_browser_auth_bool(ui_config.get("auth_enabled"))
        env_browser_auth_enabled = self._parse_browser_auth_bool(os.environ.get("DS_UI_AUTH_ENABLED"))
        explicit_browser_auth_enabled = self._parse_browser_auth_bool(browser_auth_enabled)
        if explicit_browser_auth_enabled is not None:
            self.browser_auth_enabled = explicit_browser_auth_enabled
        elif env_browser_auth_enabled is not None:
            self.browser_auth_enabled = env_browser_auth_enabled
        elif configured_browser_auth_enabled is not None:
            self.browser_auth_enabled = configured_browser_auth_enabled
        else:
            self.browser_auth_enabled = False
        explicit_browser_auth_token = self._normalize_browser_auth_token(browser_auth_token)
        env_browser_auth_token = self._normalize_browser_auth_token(os.environ.get("DS_UI_AUTH_TOKEN"))
        if self.browser_auth_enabled:
            self.browser_auth_token = explicit_browser_auth_token or env_browser_auth_token or self.generate_browser_auth_token()
        else:
            self.browser_auth_token = None
        self.handlers = ApiHandlers(self)

    @staticmethod
    def _parse_browser_auth_bool(value: object) -> bool | None:
        if isinstance(value, bool):
            return value
        normalized = str(value or "").strip().lower()
        if not normalized:
            return None
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return None

    @staticmethod
    def _normalize_browser_auth_token(value: object) -> str | None:
        token = str(value or "").strip()
        return token or None

    @staticmethod
    def generate_browser_auth_token() -> str:
        return secrets.token_hex(8)

    def masked_browser_auth_token(self) -> str | None:
        token = self.browser_auth_token
        if not token:
            return None
        if len(token) <= 6:
            return "*" * len(token)
        return f"{token[:3]}{'*' * (len(token) - 6)}{token[-3:]}"

    @staticmethod
    def _header_value(headers: dict[str, str] | None, name: str) -> str:
        if not isinstance(headers, dict):
            return ""
        target = name.strip().lower()
        for key, value in headers.items():
            if str(key).strip().lower() == target:
                return str(value or "")
        return ""

    @staticmethod
    def _parse_bearer_token(header_value: str) -> str | None:
        normalized = str(header_value or "").strip()
        prefix = "bearer "
        if not normalized or normalized[: len(prefix)].lower() != prefix:
            return None
        token = normalized[len(prefix) :].strip()
        return token or None

    def _request_cookie_token(self, headers: dict[str, str] | None) -> str | None:
        raw_cookie = self._header_value(headers, "Cookie")
        if not raw_cookie:
            return None
        try:
            cookie = SimpleCookie()
            cookie.load(raw_cookie)
        except Exception:
            return None
        morsel = cookie.get(_BROWSER_AUTH_COOKIE_NAME)
        if morsel is None:
            return None
        token = str(getattr(morsel, "value", "") or "").strip()
        return token or None

    @staticmethod
    def _request_query_token(path: str) -> str | None:
        query = parse_qs(urlparse(path).query, keep_blank_values=True)
        token = str((query.get(_BROWSER_AUTH_QUERY_PARAM) or [""])[0] or "").strip()
        return token or None

    def _browser_auth_cookie_header(self, token: str | None = None) -> str:
        cookie = SimpleCookie()
        cookie[_BROWSER_AUTH_COOKIE_NAME] = token or (self.browser_auth_token or "")
        morsel = cookie[_BROWSER_AUTH_COOKIE_NAME]
        morsel["path"] = "/"
        morsel["httponly"] = True
        morsel["samesite"] = "Strict"
        morsel["max-age"] = str(_BROWSER_AUTH_COOKIE_MAX_AGE_SECONDS)
        return morsel.OutputString()

    @staticmethod
    def _browser_auth_clear_cookie_header() -> str:
        cookie = SimpleCookie()
        cookie[_BROWSER_AUTH_COOKIE_NAME] = ""
        morsel = cookie[_BROWSER_AUTH_COOKIE_NAME]
        morsel["path"] = "/"
        morsel["httponly"] = True
        morsel["samesite"] = "Strict"
        morsel["max-age"] = "0"
        morsel["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
        return morsel.OutputString()

    def browser_auth_matches(self, token: str | None) -> bool:
        expected = self.browser_auth_token
        candidate = self._normalize_browser_auth_token(token)
        return bool(expected and candidate and hmac.compare_digest(candidate, expected))

    def rotate_browser_auth_token(self) -> str:
        if not self.browser_auth_enabled:
            raise RuntimeError("Browser authentication is disabled.")
        rotated = self.generate_browser_auth_token()
        self.browser_auth_token = rotated
        return rotated

    def browser_auth_state_for_request(self, path: str, headers: dict[str, str] | None = None) -> BrowserAuthState:
        if not self.browser_auth_enabled:
            return BrowserAuthState(authenticated=True)
        expected = self.browser_auth_token
        if not expected:
            return BrowserAuthState(authenticated=False)

        candidates = (
            ("authorization", self._parse_bearer_token(self._header_value(headers, "Authorization"))),
            ("query", self._request_query_token(path)),
            ("cookie", self._request_cookie_token(headers)),
        )
        for source, candidate in candidates:
            if candidate and hmac.compare_digest(candidate, expected):
                response_cookie = self._browser_auth_cookie_header(expected) if source in {"authorization", "query"} else None
                return BrowserAuthState(authenticated=True, token_source=source, response_cookie=response_cookie)
        return BrowserAuthState(authenticated=False, response_cookie=self._browser_auth_clear_cookie_header())

    @staticmethod
    def _auth_response_headers(auth_state: BrowserAuthState | None) -> dict[str, str]:
        if auth_state is None or not auth_state.response_cookie:
            return {}
        return {"Set-Cookie": auth_state.response_cookie}

    @staticmethod
    def _merge_response_headers(
        base: dict[str, str] | None = None,
        extra: dict[str, str] | None = None,
    ) -> dict[str, str]:
        merged: dict[str, str] = {}
        if isinstance(extra, dict):
            merged.update(extra)
        if isinstance(base, dict):
            merged.update(base)
        return merged

    def _route_requires_browser_auth(self, route_name: str | None) -> bool:
        if not self.browser_auth_enabled or not route_name:
            return False
        if route_name in _BROWSER_AUTH_PUBLIC_ROUTE_NAMES:
            return False
        if route_name in _BROWSER_AUTH_EXEMPT_ROUTE_NAMES:
            return False
        return True

    def browser_auth_runtime_payload(self) -> dict[str, object]:
        return {
            "enabled": self.browser_auth_enabled,
            "tokenQueryParam": _BROWSER_AUTH_QUERY_PARAM,
            "storageKey": _BROWSER_AUTH_STORAGE_KEY,
        }

    def browser_auth_tokenized_url(self, url: str) -> str:
        if not self.browser_auth_enabled or not self.browser_auth_token:
            return url
        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        query[_BROWSER_AUTH_QUERY_PARAM] = [self.browser_auth_token]
        return parsed._replace(query=urlencode(query, doseq=True)).geturl()

    def list_connector_statuses(self) -> list[dict[str, object]]:
        title_by_quest = self._quest_titles_by_id()
        items = [
            self._augment_connector_status(channel.status(), title_by_quest=title_by_quest)
            for name, channel in self.channels.items()
            if name == "local" or (name != "lingzhu" and self._is_connector_system_enabled(name))
        ]
        lingzhu_config = self.connectors_config.get("lingzhu")
        if isinstance(lingzhu_config, dict):
            items.append(self._augment_connector_status(self.config_manager.lingzhu_snapshot(lingzhu_config), title_by_quest=title_by_quest))
        return items

    def _quest_titles_by_id(self) -> dict[str, str | None]:
        return {
            str(item.get("quest_id") or "").strip(): str(item.get("title") or "").strip() or None
            for item in self.quest_service.list_quests()
        }

    def _augment_connector_status(
        self,
        snapshot: dict[str, object],
        *,
        title_by_quest: dict[str, str | None] | None = None,
    ) -> dict[str, object]:
        if not isinstance(snapshot, dict):
            return snapshot
        connector_name = str(snapshot.get("name") or "").strip().lower()
        titles = title_by_quest or self._quest_titles_by_id()
        binding_map: dict[str, dict[str, str | None]] = {}
        for raw in snapshot.get("bindings") or []:
            if not isinstance(raw, dict):
                continue
            conversation_id = str(raw.get("conversation_id") or "").strip()
            if not conversation_id:
                continue
            quest_id = str(raw.get("quest_id") or "").strip() or None
            binding_map[conversation_identity_key(conversation_id)] = {
                "quest_id": quest_id,
                "quest_title": titles.get(quest_id or ""),
            }

        def augment_target(target: object) -> dict[str, object] | None:
            if not isinstance(target, dict):
                return None
            payload = dict(target)
            conversation_id = str(payload.get("conversation_id") or "").strip()
            if not conversation_id:
                return payload
            binding = binding_map.get(conversation_identity_key(conversation_id)) or {}
            bound_quest_id = str(binding.get("quest_id") or "").strip() or None
            bound_quest_title = str(binding.get("quest_title") or "").strip() or None
            if bound_quest_id:
                payload["bound_quest_id"] = bound_quest_id
                payload["bound_quest_title"] = bound_quest_title
                payload["is_bound"] = True
                payload["warning"] = f"Currently bound to {bound_quest_id}"
            else:
                payload["bound_quest_id"] = None
                payload["bound_quest_title"] = None
                payload["is_bound"] = False
            payload["selectable"] = True
            if not payload.get("connector") and connector_name:
                payload["connector"] = connector_name
            return payload

        known_targets = [item for item in (augment_target(target) for target in snapshot.get("known_targets") or []) if item is not None]
        discovered_targets = [item for item in (augment_target(target) for target in snapshot.get("discovered_targets") or []) if item is not None]
        bindings = []
        for raw in snapshot.get("bindings") or []:
            if not isinstance(raw, dict):
                continue
            payload = dict(raw)
            quest_id = str(payload.get("quest_id") or "").strip() or None
            payload["quest_title"] = titles.get(quest_id or "")
            bindings.append(payload)
        payload = dict(snapshot)
        if known_targets:
            payload["known_targets"] = known_targets
        if discovered_targets:
            payload["discovered_targets"] = discovered_targets
            payload["target_count"] = len(discovered_targets)
        default_target = augment_target(snapshot.get("default_target"))
        if default_target is not None:
            payload["default_target"] = default_target
        if bindings:
            payload["bindings"] = bindings
        profiles_payload = []
        for raw_profile in snapshot.get("profiles") or []:
            if not isinstance(raw_profile, dict):
                continue
            profile_payload = dict(raw_profile)
            profile_payload["discovered_targets"] = [
                item
                for item in (
                    augment_target(target)
                    for target in raw_profile.get("discovered_targets") or []
                )
                if item is not None
            ]
            profile_payload["recent_conversations"] = [
                dict(item)
                for item in raw_profile.get("recent_conversations") or []
                if isinstance(item, dict)
            ]
            profile_payload["bindings"] = [
                {
                    **dict(item),
                    "quest_title": titles.get(str(item.get("quest_id") or "").strip() or ""),
                }
                for item in raw_profile.get("bindings") or []
                if isinstance(item, dict)
            ]
            profiles_payload.append(profile_payload)
        if profiles_payload:
            payload["profiles"] = profiles_payload
        return payload

    @staticmethod
    def _connector_has_delivery_target(snapshot: dict[str, object]) -> bool:
        if str(snapshot.get("main_chat_id") or "").strip():
            return True
        if str(snapshot.get("last_conversation_id") or "").strip():
            return True
        if isinstance(snapshot.get("default_target"), dict) and snapshot.get("default_target"):
            return True
        if isinstance(snapshot.get("bindings"), list) and snapshot.get("bindings"):
            return True
        if isinstance(snapshot.get("recent_conversations"), list) and snapshot.get("recent_conversations"):
            return True
        if isinstance(snapshot.get("discovered_targets"), list) and snapshot.get("discovered_targets"):
            return True
        for key in ("binding_count", "target_count"):
            try:
                if int(snapshot.get(key) or 0) > 0:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def connector_availability_summary(self) -> dict[str, object]:
        available_connectors: list[dict[str, object]] = []
        preferred_connector_name: str | None = None
        preferred_conversation_id: str | None = None
        has_enabled_external_connector = False
        has_bound_external_connector = False

        for item in self.list_connector_statuses():
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name or name == "local":
                continue
            enabled = bool(item.get("enabled"))
            connection_state = str(item.get("connection_state") or "").strip() or None
            has_target = self._connector_has_delivery_target(item)
            if enabled:
                has_enabled_external_connector = True
            if enabled and has_target:
                has_bound_external_connector = True
                if preferred_connector_name is None:
                    preferred_connector_name = name
                    preferred_conversation_id = str(
                        ((item.get("default_target") or {}) if isinstance(item.get("default_target"), dict) else {}).get(
                            "conversation_id"
                        )
                        or item.get("last_conversation_id")
                        or ""
                    ).strip() or None
            available_connectors.append(
                {
                    "name": name,
                    "enabled": enabled,
                    "connection_state": connection_state,
                    "binding_count": int(item.get("binding_count") or 0),
                    "target_count": int(item.get("target_count") or 0),
                    "has_delivery_target": has_target,
                }
            )

        return {
            "has_enabled_external_connector": has_enabled_external_connector,
            "has_bound_external_connector": has_bound_external_connector,
            "should_recommend_binding": not has_bound_external_connector,
            "preferred_connector_name": preferred_connector_name,
            "preferred_conversation_id": preferred_conversation_id,
            "available_connectors": available_connectors,
        }

    def _log_unhandled_exception(
        self,
        *,
        event_type: str,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: Any,
        thread_name: str | None = None,
    ) -> None:
        try:
            traceback_text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        except Exception:
            traceback_text = str(exc_value or "")
        payload: dict[str, Any] = {
            "exception_type": getattr(exc_type, "__name__", str(exc_type)),
            "message": str(exc_value),
            "traceback": traceback_text,
            "pid": os.getpid(),
        }
        if thread_name:
            payload["thread_name"] = thread_name
        self.logger.log("error", event_type, **payload)

    def _handle_process_signal(self, signame: str) -> None:
        self.logger.log(
            "warning",
            "daemon.signal_received",
            signal=signame,
            pid=os.getpid(),
        )
        self.request_shutdown(source=f"signal:{str(signame).lower()}")

    def _install_process_observability(self) -> None:
        if self._process_hooks_installed:
            return
        self._process_hooks_installed = True
        faulthandler_path = self.home / "logs" / "daemon-faulthandler.log"
        try:
            ensure_dir(faulthandler_path.parent)
            self._faulthandler_stream = open(faulthandler_path, "a", encoding="utf-8")
            faulthandler.enable(file=self._faulthandler_stream)
            dump_signal = getattr(signal, "SIGUSR1", None)
            if dump_signal is not None:
                faulthandler.register(
                    dump_signal,
                    file=self._faulthandler_stream,
                    all_threads=True,
                    chain=False,
                )
        except Exception as exc:
            self.logger.log("warning", "daemon.faulthandler_enable_failed", error=str(exc))

        def _sys_excepthook(exc_type: type[BaseException], exc_value: BaseException, exc_traceback: Any) -> None:
            self._log_unhandled_exception(
                event_type="daemon.unhandled_exception",
                exc_type=exc_type,
                exc_value=exc_value,
                exc_traceback=exc_traceback,
            )

        def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
            self._log_unhandled_exception(
                event_type="daemon.thread_exception",
                exc_type=args.exc_type,
                exc_value=args.exc_value,
                exc_traceback=args.exc_traceback,
                thread_name=getattr(args.thread, "name", None),
            )

        sys.excepthook = _sys_excepthook
        threading.excepthook = _thread_excepthook
        for signame in ("SIGTERM", "SIGHUP", "SIGINT"):
            signum = getattr(signal, signame, None)
            if signum is None:
                continue
            try:
                signal.signal(signum, lambda _signum, _frame, _signame=signame: self._handle_process_signal(_signame))
            except Exception as exc:
                self.logger.log(
                    "warning",
                    "daemon.signal_handler_install_failed",
                    signal=signame,
                    error=str(exc),
                )
        self.logger.log("info", "daemon.process_hooks_installed", pid=os.getpid())

    def _resume_reconciled_quests(self) -> list[dict[str, Any]]:
        resumed: list[dict[str, Any]] = []
        for item in self.reconciled_quests:
            if not isinstance(item, dict):
                continue
            quest_id = str(item.get("quest_id") or "").strip()
            if not quest_id or quest_id in self._recovered_quest_ids:
                continue
            if not bool(item.get("recoverable")):
                continue
            recent_attempts = self._recent_crash_auto_resume_count(quest_id)
            if recent_attempts >= _CRASH_AUTO_RESUME_MAX_RECENT_ATTEMPTS:
                self._record_auto_resume_suppressed(
                    quest_id=quest_id,
                    previous_status=str(item.get("previous_status") or "").strip() or None,
                    abandoned_run_id=str(item.get("abandoned_run_id") or "").strip() or None,
                    last_transition_at=str(item.get("last_transition_at") or "").strip() or None,
                    recent_attempts=recent_attempts,
                )
                continue
            try:
                resume_payload = self.resume_quest(quest_id, source="auto:daemon-recovery")
                snapshot = (
                    dict(resume_payload.get("snapshot") or {})
                    if isinstance(resume_payload.get("snapshot"), dict)
                    else self.quest_service.snapshot(quest_id)
                )
                reason = (
                    "queued_user_messages"
                    if int(snapshot.get("pending_user_message_count") or 0) > 0
                    else "auto_continue"
                )
                retry_delay_seconds = self._recovery_retry_delay_seconds(snapshot) if reason == "auto_continue" else None
                if retry_delay_seconds is not None and retry_delay_seconds > 0:
                    self._schedule_turn_later(
                        quest_id,
                        reason=reason,
                        delay_seconds=retry_delay_seconds,
                    )
                    scheduled = {
                        "scheduled": True,
                        "started": False,
                        "queued": True,
                        "reason": reason,
                        "delayed": True,
                        "delay_seconds": retry_delay_seconds,
                    }
                else:
                    scheduled = self.schedule_turn(quest_id, reason=reason)
                event = {
                    "event_id": generate_id("evt"),
                    "type": "quest.runtime_auto_resumed",
                    "quest_id": quest_id,
                    "previous_status": item.get("previous_status"),
                    "abandoned_run_id": item.get("abandoned_run_id"),
                    "last_transition_at": item.get("last_transition_at"),
                    "reason": reason,
                    "scheduled": bool(scheduled.get("scheduled")),
                    "started": bool(scheduled.get("started")),
                    "queued": bool(scheduled.get("queued")),
                    "delayed": bool(scheduled.get("delayed")),
                    "delay_seconds": scheduled.get("delay_seconds"),
                    "created_at": utc_now(),
                }
                append_jsonl(self.home / "quests" / quest_id / ".ds" / "events.jsonl", event)
                self.logger.log(
                    "warning",
                    "quest.runtime_auto_resumed",
                    quest_id=quest_id,
                    previous_status=item.get("previous_status"),
                    abandoned_run_id=item.get("abandoned_run_id"),
                    last_transition_at=item.get("last_transition_at"),
                    reason=reason,
                    scheduled=bool(scheduled.get("scheduled")),
                    started=bool(scheduled.get("started")),
                    queued=bool(scheduled.get("queued")),
                    delayed=bool(scheduled.get("delayed")),
                    delay_seconds=scheduled.get("delay_seconds"),
                )
                self._recovered_quest_ids.add(quest_id)
                resumed.append(
                    {
                        "quest_id": quest_id,
                        "previous_status": item.get("previous_status"),
                        "abandoned_run_id": item.get("abandoned_run_id"),
                        "last_transition_at": item.get("last_transition_at"),
                        "reason": reason,
                        "scheduled": dict(scheduled),
                    }
                )
            except Exception as exc:
                self.logger.log(
                    "warning",
                    "quest.runtime_auto_resume_failed",
                    quest_id=quest_id,
                    previous_status=item.get("previous_status"),
                    abandoned_run_id=item.get("abandoned_run_id"),
                    error=str(exc),
                )
        return resumed

    @staticmethod
    def _parse_event_timestamp(value: Any) -> datetime | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        candidate = normalized.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _recent_crash_auto_resume_count(self, quest_id: str) -> int:
        quest_root = self.home / "quests" / quest_id
        events = read_jsonl_tail(quest_root / ".ds" / "events.jsonl", 400)
        now = datetime.now(UTC)
        count = 0
        for event in reversed(events[-200:]):
            if str(event.get("type") or "").strip() != "quest.runtime_auto_resumed":
                continue
            parsed = self._parse_event_timestamp(event.get("created_at"))
            if parsed is None:
                continue
            if now - parsed > _CRASH_AUTO_RESUME_COOLDOWN:
                continue
            count += 1
        return count

    def _recovery_retry_delay_seconds(self, snapshot: dict[str, Any]) -> float | None:
        retry_state = snapshot.get("retry_state") if isinstance(snapshot.get("retry_state"), dict) else None
        if not retry_state:
            return None
        next_retry_at = str(retry_state.get("next_retry_at") or "").strip()
        if not next_retry_at:
            return None
        parsed = self._parse_event_timestamp(next_retry_at)
        if parsed is None:
            return None
        return max((parsed - datetime.now(UTC)).total_seconds(), 0.0)

    def _resume_retry_state(
        self,
        snapshot: dict[str, Any],
        *,
        max_attempts: int,
    ) -> tuple[int, str | None, dict[str, Any] | None]:
        retry_state = snapshot.get("retry_state") if isinstance(snapshot.get("retry_state"), dict) else None
        resume_source = str(snapshot.get("last_resume_source") or "").strip()
        if not retry_state or not resume_source.startswith("auto:daemon-recovery"):
            return 1, None, None

        try:
            recorded_attempt = int(retry_state.get("attempt_index") or 0)
        except (TypeError, ValueError):
            recorded_attempt = 0
        if recorded_attempt <= 0:
            return 1, None, None

        next_retry_at = str(retry_state.get("next_retry_at") or "").strip()
        start_attempt = recorded_attempt + 1 if next_retry_at else recorded_attempt
        if start_attempt > max_attempts:
            start_attempt = max_attempts
        if start_attempt <= 1:
            return 1, None, None

        turn_id = str(retry_state.get("turn_id") or "").strip() or None
        previous_run_id = str(retry_state.get("last_run_id") or "").strip() or None
        failure_summary = str(retry_state.get("last_error") or "").strip() or None
        retry_context = {
            "turn_id": turn_id,
            "attempt_index": recorded_attempt,
            "max_attempts": max_attempts,
            "previous_run_id": previous_run_id,
            "failure_kind": "daemon_recovery",
            "failure_summary": failure_summary or "Recovered retry state after daemon restart.",
            "previous_exit_code": None,
            "previous_output_text": "",
            "stderr_tail": "",
            "recent_messages": [],
            "tool_progress": [],
            "workspace_summary": {},
            "recent_artifacts": [],
        }
        return start_attempt, turn_id, retry_context

    def _record_auto_resume_suppressed(
        self,
        *,
        quest_id: str,
        previous_status: str | None,
        abandoned_run_id: str | None,
        last_transition_at: str | None,
        recent_attempts: int,
    ) -> None:
        summary = self._polite_copy(
            zh=(
                "检测到 quest 在短时间内连续异常恢复，系统已暂时停止自动继续运行，"
                "以避免进入重复崩溃循环。请先检查运行环境或 runner 侧问题，再手动恢复。"
            ),
            en=(
                "DeepScientist detected repeated crash recovery attempts in a short window, "
                "so automatic continuation has been paused to avoid a crash loop. "
                "Inspect the runtime or runner path before resuming manually."
            ),
        )
        payload = {
            "event_id": generate_id("evt"),
            "type": "quest.runtime_auto_resume_suppressed",
            "quest_id": quest_id,
            "previous_status": previous_status,
            "abandoned_run_id": abandoned_run_id,
            "last_transition_at": last_transition_at,
            "recent_attempts": recent_attempts,
            "cooldown_minutes": int(_CRASH_AUTO_RESUME_COOLDOWN.total_seconds() // 60),
            "summary": summary,
            "created_at": utc_now(),
        }
        append_jsonl(self.home / "quests" / quest_id / ".ds" / "events.jsonl", payload)
        self.logger.log(
            "warning",
            "quest.runtime_auto_resume_suppressed",
            quest_id=quest_id,
            previous_status=previous_status,
            abandoned_run_id=abandoned_run_id,
            last_transition_at=last_transition_at,
            recent_attempts=recent_attempts,
            cooldown_minutes=int(_CRASH_AUTO_RESUME_COOLDOWN.total_seconds() // 60),
        )
        self.quest_service.append_message(
            quest_id,
            role="assistant",
            content=summary,
            source="system-control",
        )
        self._relay_quest_message_to_bound_connectors(
            quest_id,
            message=summary,
            kind="progress",
            response_phase="control",
            importance="warning",
            attachments=[
                {
                    "kind": "quest_control",
                    "action": "auto_resume_suppressed",
                    "previous_status": previous_status,
                    "abandoned_run_id": abandoned_run_id,
                    "recent_attempts": recent_attempts,
                    "cooldown_minutes": int(_CRASH_AUTO_RESUME_COOLDOWN.total_seconds() // 60),
                }
            ],
        )

    def _normalize_requested_connector_bindings(
        self,
        requested_connector_bindings: list[dict[str, object]] | None,
    ) -> list[dict[str, str | None]]:
        items = requested_connector_bindings if isinstance(requested_connector_bindings, list) else []
        normalized_by_connector: dict[str, dict[str, str | None]] = {}
        for raw in items:
            if not isinstance(raw, dict):
                continue
            raw_connector_name = str(raw.get("connector") or "").strip().lower()
            conversation_id = normalize_conversation_id(raw.get("conversation_id"))
            parsed = parse_conversation_id(conversation_id)
            connector_name = raw_connector_name
            if parsed is not None:
                connector_name = str(parsed.get("connector") or connector_name).strip().lower()
            if not connector_name or connector_name == "local":
                continue
            if connector_name not in self.channels:
                continue
            if not self._is_connector_system_enabled(connector_name):
                continue
            if parsed is not None and str(parsed.get("connector") or "").strip().lower() != connector_name:
                continue
            normalized_by_connector[connector_name] = {
                "connector": connector_name,
                "conversation_id": conversation_id or None,
            }
        return list(normalized_by_connector.values())

    def _launcher_update_base_command(self) -> list[str]:
        node_binary = str(os.environ.get("DEEPSCIENTIST_NODE_BINARY") or "").strip() or which("node") or which("nodejs")
        launcher_path = str(os.environ.get("DEEPSCIENTIST_LAUNCHER_PATH") or "").strip()
        if not launcher_path:
            launcher_path = str(self.repo_root / "bin" / "ds.js")
        if not node_binary:
            raise RuntimeError("Node.js is not available on PATH, so DeepScientist cannot check npm updates.")
        if not Path(launcher_path).exists():
            raise RuntimeError(f"DeepScientist launcher path does not exist: {launcher_path}")
        return [node_binary, launcher_path, "update", "--home", str(self.home)]

    def system_update_status(self) -> dict[str, object]:
        command = [*self._launcher_update_base_command(), "--check", "--json"]
        try:
            result = subprocess.run(
                command,
                cwd=str(self.repo_root),
                capture_output=True,
                timeout=8,
                check=False,
                env=os.environ.copy(),
                **utf8_text_subprocess_kwargs(),
                **_windows_hidden_subprocess_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("DeepScientist update check timed out.") from exc
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "Update check failed.").strip())
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("DeepScientist update check returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("DeepScientist update check returned an invalid payload.")
        return payload

    def request_system_update(self, *, action: str) -> dict[str, object]:
        normalized = str(action or "").strip().lower()
        if normalized not in {"install_latest", "remind_later", "skip_version"}:
            raise ValueError(f"Unsupported update action `{action}`.")
        command = self._launcher_update_base_command()
        if normalized == "install_latest":
            host = self._serve_host or "0.0.0.0"
            port = self._serve_port or 20999
            command.extend(
                [
                    "--yes",
                    "--background",
                    "--restart-daemon",
                    "--host",
                    str(host),
                    "--port",
                    str(port),
                    "--json",
                ]
            )
        elif normalized == "remind_later":
            command.extend(["--remind-later", "--json"])
        else:
            command.extend(["--skip-version", "--json"])

        try:
            result = subprocess.run(
                command,
                cwd=str(self.repo_root),
                capture_output=True,
                timeout=8,
                check=False,
                env=os.environ.copy(),
                **utf8_text_subprocess_kwargs(),
                **_windows_hidden_subprocess_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("DeepScientist update request timed out.") from exc
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "Update request failed.").strip())
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("DeepScientist update request returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("DeepScientist update request returned an invalid payload.")
        return payload

    def start_benchstore_install(self, entry_id: str) -> dict[str, Any]:
        entry_payload = self.benchstore_service.get_entry(entry_id)
        entry = entry_payload.get("entry") if isinstance(entry_payload.get("entry"), dict) else {}
        normalized_id = str(entry.get("id") or entry_id).strip() or str(entry_id).strip()
        entry_name = str(entry.get("name") or normalized_id).strip() or normalized_id
        return self.admin_task_service.start_task(
            "benchstore_install",
            metadata={
                "entry_id": normalized_id,
                "entry_name": entry_name,
            },
            target=lambda reporter, current_task: self.benchstore_service.run_install_task(
                entry_id=normalized_id,
                reporter=reporter,
                task_id=str(current_task.get("task_id") or ""),
            ),
        )

    def _process_terminal_attach_request(
        self,
        connection: ServerConnection,
        request: WebSocketRequest,
    ) -> Response | None:
        query = parse_qs(urlparse(request.path).query)
        token = str((query.get("token") or [""])[0] or "").strip()
        if not token:
            return Response(
                400,
                "Bad Request",
                Headers({"Content-Type": "text/plain; charset=utf-8"}),
                b"Missing terminal attach token.",
            )
        attach_token, runtime = self.bash_exec_service.resolve_terminal_attach_token(token)
        if attach_token is None:
            return Response(
                404,
                "Not Found",
                Headers({"Content-Type": "text/plain; charset=utf-8"}),
                b"Terminal attach token is invalid or expired.",
            )
        if runtime is None:
            try:
                session = self.bash_exec_service.get_session(attach_token.quest_root, attach_token.bash_id)
            except FileNotFoundError:
                return Response(
                    404,
                    "Not Found",
                    Headers({"Content-Type": "text/plain; charset=utf-8"}),
                    b"Terminal session is no longer available.",
                )
            status = str(session.get("status") or "").strip().lower()
            kind = str(session.get("kind") or "").strip().lower()
            if status in {"completed", "failed", "terminated"} or kind not in {"exec"}:
                return Response(
                    409,
                    "Conflict",
                    Headers({"Content-Type": "text/plain; charset=utf-8"}),
                    b"Terminal runtime is no longer active.",
                )
        setattr(connection, "_ds_terminal_attach_token", token)
        return None

    def _handle_logged_terminal_attach_connection(
        self,
        connection: ServerConnection,
        *,
        attach_token,
        send_lock: threading.Lock,
    ) -> None:
        session = self.bash_exec_service.get_session(attach_token.quest_root, attach_token.bash_id)
        stop_event = threading.Event()

        with send_lock:
            connection.send(
                json.dumps(
                    {
                        "type": "ready",
                        "bash_id": attach_token.bash_id,
                        "status": session.get("status"),
                        "cwd": session.get("cwd"),
                        "workdir": session.get("workdir"),
                    },
                    ensure_ascii=False,
                )
            )

        def _encode_exec_log_entry(entry: dict[str, Any]) -> bytes:
            line = str(entry.get("line") or "")
            stream = str(entry.get("stream") or "").strip().lower()
            if line.startswith("__DS_PROGRESS__") or line.startswith("__DS_BASH_STATUS__"):
                return b""
            if line.startswith("__DS_BASH_CR__"):
                payload = line[len("__DS_BASH_CR__") :].lstrip()
                return f"\r\x1b[K{payload}".encode("utf-8", errors="replace")
            if stream in {"prompt", "partial"}:
                return line.encode("utf-8", errors="replace")
            if stream == "system" and not line.strip():
                return b""
            return f"{line}\n".encode("utf-8", errors="replace")

        def _relay_output() -> None:
            last_seq = 0
            try:
                entries, meta = self.bash_exec_service.read_log_entries(
                    attach_token.quest_root,
                    attach_token.bash_id,
                    limit=2000,
                    order="asc",
                )
                if isinstance(meta.get("latest_seq"), int):
                    last_seq = int(meta["latest_seq"])
                elif entries:
                    last_seq = max(int(item.get("seq") or 0) for item in entries)
                for entry in entries:
                    payload = _encode_exec_log_entry(entry)
                    if not payload:
                        continue
                    with send_lock:
                        connection.send(payload)

                while not stop_event.is_set():
                    entries, _meta = self.bash_exec_service.read_log_entries(
                        attach_token.quest_root,
                        attach_token.bash_id,
                        limit=400,
                        after_seq=last_seq,
                        order="asc",
                    )
                    for entry in entries:
                        last_seq = max(last_seq, int(entry.get("seq") or 0))
                        payload = _encode_exec_log_entry(entry)
                        if not payload:
                            continue
                        with send_lock:
                            connection.send(payload)
                    current = self.bash_exec_service.get_session(
                        attach_token.quest_root,
                        attach_token.bash_id,
                    )
                    status = str(current.get("status") or "").strip().lower()
                    if status in {"completed", "failed", "terminated"}:
                        with send_lock:
                            connection.send(
                                json.dumps(
                                    {
                                        "type": "exit",
                                        "bash_id": attach_token.bash_id,
                                        "status": current.get("status"),
                                        "exit_code": current.get("exit_code"),
                                        "stop_reason": current.get("stop_reason"),
                                        "finished_at": current.get("finished_at"),
                                    },
                                    ensure_ascii=False,
                                )
                            )
                        return
                    time.sleep(TERMINAL_STREAM_IDLE_SLEEP_SECONDS)
            except Exception as exc:
                if stop_event.is_set():
                    return
                try:
                    with send_lock:
                        connection.send(
                            json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False)
                        )
                except Exception:
                    pass

        relay_thread = threading.Thread(
            target=_relay_output,
            daemon=True,
            name=f"exec-attach-{attach_token.bash_id}",
        )
        relay_thread.start()
        try:
            while True:
                try:
                    message = connection.recv()
                except ConnectionClosed:
                    break
                if message is None:
                    break
                if isinstance(message, bytes):
                    self.bash_exec_service.append_terminal_input(
                        attach_token.quest_root,
                        attach_token.bash_id,
                        data=message.decode("utf-8", errors="replace"),
                        source="web-pty",
                    )
                    continue
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                message_type = str(payload.get("type") or "").strip().lower()
                if message_type == "input":
                    self.bash_exec_service.append_terminal_input(
                        attach_token.quest_root,
                        attach_token.bash_id,
                        data=str(payload.get("data") or ""),
                        source="web-pty",
                    )
                    continue
                if message_type == "binary_input":
                    raw = str(payload.get("data") or "")
                    if raw:
                        self.bash_exec_service.append_terminal_input(
                            attach_token.quest_root,
                            attach_token.bash_id,
                            data=base64.b64decode(raw).decode("utf-8", errors="replace"),
                            source="web-pty",
                        )
                    continue
                if message_type == "resize":
                    cols = int(payload.get("cols") or 0)
                    rows = int(payload.get("rows") or 0)
                    self.bash_exec_service.resize_terminal_session(
                        attach_token.quest_root,
                        attach_token.bash_id,
                        cols=cols,
                        rows=rows,
                    )
                    continue
                if message_type == "detach":
                    break
                if message_type == "ping":
                    with send_lock:
                        connection.send(json.dumps({"type": "pong"}, ensure_ascii=False))
        finally:
            stop_event.set()
            relay_thread.join(timeout=1)

    def _handle_terminal_attach_connection(self, connection: ServerConnection) -> None:
        token_value = str(getattr(connection, "_ds_terminal_attach_token", "") or "").strip()
        attach_token, runtime = self.bash_exec_service.consume_terminal_attach_token(token_value)
        if attach_token is None:
            try:
                connection.close(code=1011, reason="terminal_attach_unavailable")
            except Exception:
                pass
            return

        send_lock = threading.Lock()
        if runtime is None:
            try:
                self._handle_logged_terminal_attach_connection(
                    connection,
                    attach_token=attach_token,
                    send_lock=send_lock,
                )
            except Exception as exc:
                try:
                    with send_lock:
                        connection.send(
                            json.dumps(
                                {"type": "error", "message": str(exc)},
                                ensure_ascii=False,
                            )
                        )
                except Exception:
                    pass
            finally:
                try:
                    connection.close()
                except Exception:
                    pass
            return

        client = TerminalClient(
            client_id=generate_id("tclient"),
            send_text=connection.send,
            send_binary=connection.send,
            close=connection.close,
            send_lock=send_lock,
        )
        runtime.attach_client(client)
        try:
            session = self.bash_exec_service.get_session(attach_token.quest_root, attach_token.bash_id)
            with send_lock:
                connection.send(
                    json.dumps(
                        {
                            "type": "ready",
                            "bash_id": attach_token.bash_id,
                            "status": session.get("status"),
                            "cwd": session.get("cwd"),
                            "workdir": session.get("workdir"),
                        },
                        ensure_ascii=False,
                    )
                )
                for chunk in runtime.snapshot_replay():
                    if chunk:
                        connection.send(chunk)
            while True:
                try:
                    message = connection.recv()
                except ConnectionClosed:
                    break
                if message is None:
                    break
                if isinstance(message, bytes):
                    runtime.write_binary_input(message)
                    continue
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                message_type = str(payload.get("type") or "").strip().lower()
                if message_type == "input":
                    self.bash_exec_service.append_terminal_input(
                        attach_token.quest_root,
                        attach_token.bash_id,
                        data=str(payload.get("data") or ""),
                        source="web-pty",
                    )
                    continue
                if message_type == "binary_input":
                    raw = str(payload.get("data") or "")
                    if raw:
                        runtime.write_binary_input(base64.b64decode(raw))
                    continue
                if message_type == "resize":
                    cols = int(payload.get("cols") or 0)
                    rows = int(payload.get("rows") or 0)
                    self.bash_exec_service.resize_terminal_session(
                        attach_token.quest_root,
                        attach_token.bash_id,
                        cols=cols,
                        rows=rows,
                    )
                    continue
                if message_type == "detach":
                    break
                if message_type == "ping":
                    with send_lock:
                        connection.send(json.dumps({"type": "pong"}, ensure_ascii=False))
        except Exception as exc:
            try:
                with send_lock:
                    connection.send(
                        json.dumps(
                            {"type": "error", "message": str(exc)},
                            ensure_ascii=False,
                        )
                    )
            except Exception:
                pass
        finally:
            runtime.detach_client(client.client_id)
            try:
                connection.close()
            except Exception:
                pass

    def _start_terminal_attach_server(self, host: str, port: int) -> None:
        if self._terminal_attach_server is not None:
            return
        candidates: list[int] = []
        if port > 0 and port < 65535:
            candidates.append(port + 1)
        candidates.append(0)
        last_error: Exception | None = None
        for candidate in candidates:
            try:
                server = websocket_serve(
                    self._handle_terminal_attach_connection,
                    host=host,
                    port=candidate,
                    process_request=self._process_terminal_attach_request,
                    compression=None,
                    max_size=None,
                    max_queue=None,
                )
                self._terminal_attach_server = server
                self._terminal_attach_host = host
                self._terminal_attach_port = int(server.socket.getsockname()[1])
                thread = threading.Thread(
                    target=server.serve_forever,
                    daemon=True,
                    name="deepscientist-terminal-attach",
                )
                thread.start()
                self._terminal_attach_thread = thread
                return
            except OSError as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise last_error

    def _stop_terminal_attach_server(self) -> None:
        server = self._terminal_attach_server
        thread = self._terminal_attach_thread
        self._terminal_attach_server = None
        self._terminal_attach_thread = None
        self._terminal_attach_host = None
        self._terminal_attach_port = None
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

    def get_runner(self, name: str):
        normalized = str(name or "").strip().lower()
        try:
            return self.runners[normalized]
        except KeyError as exc:
            available = ", ".join(sorted(self.runners)) or "none"
            raise KeyError(f"Unknown runner `{normalized}`. Available runners: {available}.") from exc

    def _create_runner(self, name: str):
        factory = get_runner_factory(name)
        return factory(home=self.home, app=self, config=self.runners_config.get(name, {}))

    def _create_channel(self, name: str):
        factory = get_channel_factory(name)
        return factory(home=self.home, app=self, config=self.connectors_config.get(name, {}))

    def _system_enabled_connector_names(self) -> set[str]:
        connectors = self.runtime_config.get("connectors") if isinstance(self.runtime_config.get("connectors"), dict) else {}
        system_enabled = connectors.get("system_enabled") if isinstance(connectors.get("system_enabled"), dict) else {}
        return {
            name
            for name in SYSTEM_CONNECTOR_NAMES
            if bool(system_enabled.get(name, name in {"qq", "weixin"}))
        }

    def _is_connector_system_enabled(self, connector_name: str) -> bool:
        normalized = str(connector_name or "").strip().lower()
        if normalized == "local":
            return True
        if normalized == "lingzhu":
            return True
        enabled = self._system_enabled_connector_names()
        if normalized in enabled:
            return True
        if normalized in SYSTEM_CONNECTOR_NAMES:
            return False
        return True

    def reload_runtime_config(self, *, restart_background: bool = True) -> dict[str, object]:
        previous_enabled = self._system_enabled_connector_names()
        self.runtime_config = self.config_manager.load_runtime_config()
        logging_config = self.runtime_config.get("logging") if isinstance(self.runtime_config.get("logging"), dict) else {}
        self.logger.level = str(logging_config.get("level") or "info").strip().lower() or "info"
        enabled = self._system_enabled_connector_names()
        restarted = False
        if restart_background and self._server is not None and enabled != previous_enabled:
            self._stop_background_connectors()
            self._start_background_connectors()
            restarted = True
        return {
            "ok": True,
            "system_enabled_connectors": sorted(enabled),
            "restarted_background_connectors": restarted,
        }

    def reload_connectors_config(self, *, restart_background: bool = True) -> dict[str, object]:
        self.connectors_config = self.config_manager.load_named_normalized("connectors")
        register_builtin_channels(home=self.home, connectors_config=self.connectors_config)
        for name, channel in self.channels.items():
            config = self.connectors_config.get(name, {})
            if hasattr(channel, "config") and isinstance(getattr(channel, "config"), dict):
                channel.config.clear()
                if isinstance(config, dict):
                    channel.config.update(config)
        if restart_background and self._server is not None:
            self._stop_background_connectors()
            self._start_background_connectors()
        return {
            "ok": True,
            "connectors": sorted(
                name
                for name, config in self.connectors_config.items()
                if not str(name).startswith("_")
                and isinstance(config, dict)
                and self._is_connector_system_enabled(str(name))
            ),
        }

    def reload_runners_config(self) -> dict[str, object]:
        self.runners_config = self.config_manager.load_runners_config()
        runner_instances = {
            "codex": self.codex_runner,
            "claude": self.claude_runner,
            "opencode": self.opencode_runner,
        }
        payload: dict[str, object] = {
            "ok": True,
            "runners": sorted(name for name, config in self.runners_config.items() if isinstance(config, dict)),
        }
        for runner_name, instance in runner_instances.items():
            runner_config = self.runners_config.get(runner_name, {})
            if isinstance(runner_config, dict):
                instance.binary = str(runner_config.get("binary") or getattr(instance, "binary", runner_name))
            payload[runner_name] = {
                "binary": getattr(instance, "binary", None),
                "enabled": runner_config.get("enabled") if isinstance(runner_config, dict) else None,
                "model": runner_config.get("model") if isinstance(runner_config, dict) else None,
                "config_dir": runner_config.get("config_dir") if isinstance(runner_config, dict) else None,
            }
            if runner_name == "codex" and isinstance(runner_config, dict):
                payload[runner_name]["approval_policy"] = runner_config.get("approval_policy")
                payload[runner_name]["sandbox_mode"] = runner_config.get("sandbox_mode")
                payload[runner_name]["mcp_tool_timeout_sec"] = runner_config.get("mcp_tool_timeout_sec")
        return payload

    def _preferred_locale(self) -> str:
        return str(self.runtime_config.get("default_locale") or "en-US").lower()

    def _polite_copy(self, *, zh: str, en: str) -> str:
        return zh if self._preferred_locale().startswith("zh") else en

    @staticmethod
    def _resume_continue_source(source: str) -> str:
        normalized = normalize_conversation_id(source)
        parsed = parse_conversation_id(normalized)
        if parsed is not None and str(parsed.get("connector") or "").strip().lower() != "local":
            return normalized
        return "local"

    def submit_user_message(
        self,
        quest_id: str,
        *,
        text: str,
        source: str,
        attachments: list[dict[str, object]] | None = None,
        reply_to_interaction_id: str | None = None,
        client_message_id: str | None = None,
    ) -> dict:
        previous_snapshot = self.quest_service.snapshot(quest_id)
        previous_status = str(previous_snapshot.get("runtime_status") or previous_snapshot.get("status") or "").strip()
        message = self.quest_service.append_message(
            quest_id,
            role="user",
            content=text,
            source=source,
            attachments=[dict(item) for item in (attachments or []) if isinstance(item, dict)],
            reply_to_interaction_id=reply_to_interaction_id,
            client_message_id=client_message_id,
        )
        snapshot = self.quest_service.snapshot(quest_id)
        snapshot = self._reconcile_stale_active_turn(quest_id, snapshot=snapshot)
        runtime_status = str(snapshot.get("runtime_status") or snapshot.get("status") or "").strip()
        auto_resumed = previous_status in {"stopped", "paused", "completed"} and runtime_status not in {"stopped", "paused", "completed"}
        if auto_resumed:
            self._append_control_event(
                quest_id,
                action="resume",
                source=f"auto:{source}",
                status=runtime_status or "active",
                interrupted=False,
                summary=f"Quest {quest_id} automatically resumed after a new user message.",
                automated=True,
            )
        turn_state = self._refresh_turn_worker_state(quest_id)
        has_live_turn = bool(turn_state.get("running"))
        stalled_details = self._stalled_running_turn_details(
            quest_id,
            snapshot=snapshot,
            turn_state=turn_state,
            turn_reason="user_message",
        )
        if runtime_status == "running" and has_live_turn and stalled_details is None:
            scheduled = {
                "scheduled": True,
                "started": False,
                "queued": True,
                "reason": "queued_for_artifact_interact",
            }
        else:
            scheduled = self.schedule_turn(quest_id, reason="user_message")
        return {
            "message": message,
            "auto_resumed": auto_resumed,
            "previous_status": previous_status or None,
            **scheduled,
        }

    def submit_web_user_message(
        self,
        quest_id: str,
        *,
        text: str,
        source: str,
        attachment_draft_ids: list[str],
        reply_to_interaction_id: str | None = None,
        client_message_id: str | None = None,
    ) -> dict:
        finalized_attachments = self.quest_service.finalize_chat_attachment_drafts(
            quest_id,
            draft_ids=attachment_draft_ids,
            client_message_id=client_message_id,
        )
        return self.submit_user_message(
            quest_id,
            text=text,
            source=source,
            attachments=finalized_attachments,
            reply_to_interaction_id=reply_to_interaction_id,
            client_message_id=client_message_id,
        )

    def create_quest(
        self,
        *,
        goal: str,
        title: str | None = None,
        quest_id: str | None = None,
        source: str = "local",
        announce_connector_binding: bool = True,
        exclude_conversation_id: str | None = None,
        preferred_connector_conversation_id: str | None = None,
        requested_connector_bindings: list[dict[str, object]] | None = None,
        force_connector_rebind: bool = True,
        auto_bind_latest_connectors: bool = True,
        requested_baseline_ref: dict[str, object] | None = None,
        startup_contract: dict[str, object] | None = None,
    ) -> dict:
        normalized_requested_bindings = self._normalize_requested_connector_bindings(requested_connector_bindings)
        if len(normalized_requested_bindings) > 1:
            raise ValueError("A quest may bind at most one external connector target.")
        configured = self.config_manager.load_named("config")
        default_runner = str(configured.get("default_runner") or "codex").strip().lower() or "codex"
        snapshot = self.quest_service.create(
            goal=goal,
            title=title,
            quest_id=quest_id,
            runner=default_runner,
            requested_baseline_ref=dict(requested_baseline_ref) if isinstance(requested_baseline_ref, dict) else None,
            startup_contract=dict(startup_contract) if isinstance(startup_contract, dict) else None,
        )
        baseline_id = (
            str((requested_baseline_ref or {}).get("baseline_id") or "").strip()
            if isinstance(requested_baseline_ref, dict)
            else ""
        )
        variant_id = (
            str((requested_baseline_ref or {}).get("variant_id") or "").strip() or None
            if isinstance(requested_baseline_ref, dict)
            else None
        )
        if baseline_id:
            try:
                quest_root = Path(snapshot["quest_root"])
                attachment = self.artifact_service.attach_baseline(quest_root, baseline_id, variant_id)
                if not attachment.get("ok"):
                    raise RuntimeError(
                        str(attachment.get("message") or f"Unable to materialize requested baseline `{baseline_id}`.")
                    )
                self.artifact_service.confirm_baseline(
                    quest_root,
                    baseline_path=f"baselines/imported/{baseline_id}",
                    baseline_id=baseline_id,
                    variant_id=variant_id,
                    summary=f"Baseline `{baseline_id}` confirmed during quest creation.",
                )
                snapshot = self.quest_service.snapshot(snapshot["quest_id"])
            except Exception as exc:
                shutil.rmtree(Path(snapshot["quest_root"]), ignore_errors=True)
                self.logger.log(
                    "warning",
                    "quest.baseline_bootstrap_failed",
                    quest_id=snapshot.get("quest_id"),
                    baseline_id=baseline_id,
                    message=str(exc),
                )
                raise RuntimeError(
                    f"Quest creation failed because the requested baseline `{baseline_id}` could not be attached and confirmed: {exc}"
                ) from exc
        preferred_binding = normalize_conversation_id(preferred_connector_conversation_id)
        preferred_parsed = parse_conversation_id(preferred_binding)
        if normalized_requested_bindings:
            try:
                binding_result = self.update_quest_bindings(
                    snapshot["quest_id"],
                    normalized_requested_bindings,
                    force=force_connector_rebind,
                )
                if isinstance(binding_result, tuple):
                    raise RuntimeError(str(binding_result[1].get("message") or "Unable to bind connector targets."))
                if announce_connector_binding:
                    for result in binding_result.get("results") or []:
                        if not isinstance(result, dict):
                            continue
                        conversation_id = str(result.get("conversation_id") or "").strip()
                        connector_name = str(result.get("connector") or "").strip().lower()
                        if not conversation_id or not connector_name or connector_name == "local":
                            continue
                        channel = self._channel_with_bindings(connector_name)
                        channel.send(
                            {
                                "conversation_id": conversation_id,
                                "quest_id": snapshot["quest_id"],
                                "kind": "ack",
                                "message": self._quest_created_connector_message(
                                    connector_name,
                                    quest_id=snapshot["quest_id"],
                                    goal=goal,
                                    previous_quest_id=str(result.get("previous_quest_id") or "").strip() or None,
                                ),
                            }
                        )
                snapshot = self.quest_service.snapshot(snapshot["quest_id"])
            except Exception as exc:
                shutil.rmtree(Path(snapshot["quest_root"]), ignore_errors=True)
                self.sessions.forget(snapshot["quest_id"])
                self.logger.log(
                    "warning",
                    "quest.connector_binding_failed",
                    quest_id=snapshot.get("quest_id"),
                    message=str(exc),
                )
                raise RuntimeError(
                    f"Quest creation failed because one or more selected connector targets could not be bound: {exc}"
                ) from exc
        elif (
            preferred_binding
            and preferred_parsed
            and str(preferred_parsed.get("connector") or "").strip().lower() in self.channels
            and str(preferred_parsed.get("connector") or "").strip().lower() != "local"
        ):
            connector_name = str(preferred_parsed.get("connector") or "").strip().lower()
            result = self.update_quest_binding(snapshot["quest_id"], preferred_binding, force=True)
            if isinstance(result, tuple):
                self.logger.log(
                    "warning",
                    "quest.preferred_connector_binding_failed",
                    quest_id=snapshot.get("quest_id"),
                    conversation_id=preferred_binding,
                    status=result[0],
                    message=str(result[1].get("message") or "Unable to bind preferred connector target."),
                )
            elif announce_connector_binding:
                channel = self._channel_with_bindings(connector_name)
                channel.send(
                    {
                        "conversation_id": preferred_binding,
                        "quest_id": snapshot["quest_id"],
                        "kind": "ack",
                        "message": self._quest_created_connector_message(
                            connector_name,
                            quest_id=snapshot["quest_id"],
                            goal=goal,
                            previous_quest_id=str(result.get("previous_quest_id") or "").strip() or None,
                        ),
                    }
                )
        elif auto_bind_latest_connectors:
            self._auto_bind_connectors_to_latest_quest(
                snapshot["quest_id"],
                goal=goal,
                source=source,
                announce=announce_connector_binding,
                exclude_conversation_id=exclude_conversation_id,
            )
        return snapshot

    def schedule_turn(self, quest_id: str, *, reason: str = "user_message") -> dict:
        snapshot = self.quest_service.snapshot(quest_id)
        snapshot = self._reconcile_stale_active_turn(quest_id, snapshot=snapshot)
        recovery = self._recover_stalled_running_turn(quest_id, snapshot=snapshot, turn_reason=reason)
        snapshot = dict(recovery.get("snapshot") or snapshot)
        if recovery.get("blocked"):
            return {
                "scheduled": True,
                "started": False,
                "queued": True,
                "reason": "stalled_turn_recovery_pending",
            }
        self._refresh_turn_worker_state(quest_id)
        with self._turn_lock:
            state = self._turn_state.setdefault(quest_id, {"running": False, "pending": False})
            state["pending"] = True
            state["stop_requested"] = False
            state.pop("recovery_pending", None)
            state["reason"] = reason
            if state.get("running"):
                return {
                    "scheduled": True,
                    "started": False,
                    "queued": True,
                    "reason": "queued_for_artifact_interact" if reason == "user_message" else reason,
                }
            state["running"] = True
            worker = threading.Thread(
                target=self._drain_turns,
                args=(quest_id,),
                daemon=True,
                name=f"deepscientist-turn-{quest_id}",
            )
            state["worker"] = worker
        worker.start()
        return {
            "scheduled": True,
            "started": True,
            "queued": False,
            "reason": reason,
        }

    @staticmethod
    def _turn_worker_is_alive(worker: object) -> bool:
        return isinstance(worker, threading.Thread) and worker.is_alive()

    def schedule_latest_quest_terminal_prewarm(
        self,
        quest_id: str,
        *,
        source: str = "quest_session_prewarm",
    ) -> None:
        normalized_quest_id = str(quest_id or "").strip()
        if not normalized_quest_id or os.name == "nt":
            return
        try:
            quests = self.quest_service.list_quests()
        except Exception:
            return
        latest_quest_id = str((quests[0].get("quest_id") if quests else "") or "").strip()
        if latest_quest_id != normalized_quest_id:
            return
        now = time.monotonic()
        with self._terminal_prewarm_lock:
            last_attempt = float(self._terminal_prewarm_recent.get(normalized_quest_id) or 0.0)
            if now - last_attempt < _TERMINAL_PREWARM_DEBOUNCE_SECONDS:
                return
            self._terminal_prewarm_recent[normalized_quest_id] = now
        threading.Thread(
            target=self._prewarm_terminal_for_quest,
            args=(normalized_quest_id, source),
            daemon=True,
            name=f"deepscientist-terminal-prewarm-{normalized_quest_id}",
        ).start()

    def _prewarm_terminal_for_quest(self, quest_id: str, source: str) -> None:
        try:
            quest_root = self.quest_service._quest_root(quest_id)
            workspace_root = self.quest_service.active_workspace_root(quest_root)
            self.bash_exec_service.ensure_terminal_session(
                quest_root,
                quest_id=quest_id,
                bash_id=DEFAULT_TERMINAL_SESSION_ID,
                cwd=workspace_root,
                source=source,
            )
        except Exception as exc:
            with self._terminal_prewarm_lock:
                self._terminal_prewarm_recent.pop(quest_id, None)
            self.logger.log(
                "warning",
                "terminal.prewarm_failed",
                quest_id=quest_id,
                source=source,
                error=str(exc),
            )

    def _refresh_turn_worker_state(self, quest_id: str) -> dict[str, object]:
        with self._turn_lock:
            state = self._turn_state.setdefault(quest_id, {"running": False, "pending": False})
            if bool(state.get("running")) and not self._turn_worker_is_alive(state.get("worker")):
                state["running"] = False
                state.pop("worker", None)
            return dict(state)

    def _wait_for_turn_worker_exit(self, quest_id: str, *, timeout_seconds: float) -> dict[str, object]:
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        state = self._refresh_turn_worker_state(quest_id)
        while state.get("running") and time.monotonic() < deadline:
            time.sleep(0.05)
            state = self._refresh_turn_worker_state(quest_id)
        return state

    def _ensure_recovery_resume_watch(self, quest_id: str, *, turn_reason: str) -> None:
        with self._turn_lock:
            state = self._turn_state.setdefault(quest_id, {"running": False, "pending": False})
            if state.get("recovery_watch_active"):
                return
            state["recovery_watch_active"] = True
        watcher = threading.Thread(
            target=self._wait_and_resume_recovered_turn,
            args=(quest_id, turn_reason),
            daemon=True,
            name=f"deepscientist-recovery-watch-{quest_id}",
        )
        watcher.start()

    def _wait_and_resume_recovered_turn(self, quest_id: str, turn_reason: str) -> None:
        try:
            while True:
                state = self._refresh_turn_worker_state(quest_id)
                if not state.get("recovery_pending"):
                    return
                if not state.get("running"):
                    break
                time.sleep(0.1)

            snapshot = self.quest_service.snapshot(quest_id)
            runtime_status = str(snapshot.get("runtime_status") or snapshot.get("status") or "").strip().lower()
            if runtime_status in {"paused", "stopped", "completed", "error"}:
                with self._turn_lock:
                    state = self._turn_state.setdefault(quest_id, {"running": False, "pending": False})
                    state.pop("recovery_pending", None)
                    state["stop_requested"] = runtime_status in {"paused", "stopped"}
                return
            pending_user_count = int(snapshot.get("pending_user_message_count") or 0)
            if pending_user_count > 0:
                with self._turn_lock:
                    state = self._turn_state.setdefault(quest_id, {"running": False, "pending": False})
                    state.pop("recovery_pending", None)
                self.schedule_turn(quest_id, reason=turn_reason)
                return

            with self._turn_lock:
                state = self._turn_state.setdefault(quest_id, {"running": False, "pending": False})
                state.pop("recovery_pending", None)
                state["stop_requested"] = False
        except Exception as exc:
            self.logger.log(
                "warning",
                "quest.turn_state_recovery_watch_failed",
                quest_id=quest_id,
                reason=turn_reason,
                error=str(exc),
            )
        finally:
            with self._turn_lock:
                state = self._turn_state.setdefault(quest_id, {"running": False, "pending": False})
                state.pop("recovery_watch_active", None)

    def _stalled_running_turn_details(
        self,
        quest_id: str,
        *,
        snapshot: dict | None = None,
        turn_state: dict[str, object] | None = None,
        turn_reason: str,
    ) -> dict[str, int] | None:
        if str(turn_reason or "").strip() not in {"user_message", "queued_user_messages"}:
            return None
        snapshot = dict(snapshot or self.quest_service.snapshot(quest_id))
        runtime_status = str(snapshot.get("runtime_status") or snapshot.get("status") or "").strip().lower()
        active_run_id = str(snapshot.get("active_run_id") or "").strip()
        if runtime_status != "running" or not active_run_id:
            return None
        state = dict(turn_state or self._refresh_turn_worker_state(quest_id))
        if not state.get("running"):
            return None
        pending_user_count = int(snapshot.get("pending_user_message_count") or 0)
        if pending_user_count <= 0:
            return None
        counts = snapshot.get("counts") if isinstance(snapshot.get("counts"), dict) else {}
        if int(counts.get("bash_running_count") or 0) > 0:
            return None
        silent_seconds = snapshot.get("seconds_since_last_tool_activity")
        if silent_seconds is None:
            watchdog = snapshot.get("interaction_watchdog") if isinstance(snapshot.get("interaction_watchdog"), dict) else {}
            silent_seconds = watchdog.get("seconds_since_last_tool_activity")
        try:
            silent_seconds_int = int(silent_seconds or 0)
        except (TypeError, ValueError):
            return None
        if silent_seconds_int < _STALLED_RUNNING_TURN_INACTIVITY_SECONDS:
            return None
        return {
            "pending_user_count": pending_user_count,
            "silent_seconds": silent_seconds_int,
        }

    def _reconcile_stale_active_turn(self, quest_id: str, *, snapshot: dict | None = None) -> dict:
        snapshot = dict(snapshot or self.quest_service.snapshot(quest_id))
        active_run_id = str(snapshot.get("active_run_id") or "").strip()
        if not active_run_id:
            self._refresh_turn_worker_state(quest_id)
            return snapshot
        turn_state = self._refresh_turn_worker_state(quest_id)
        if turn_state.get("running"):
            return snapshot

        quest_root = self.quest_service._quest_root(quest_id)
        result_payload = read_json(quest_root / ".ds" / "runs" / active_run_id / "result.json", {})
        completed_at = str(result_payload.get("completed_at") or "").strip() if isinstance(result_payload, dict) else ""
        exit_code = result_payload.get("exit_code") if isinstance(result_payload, dict) else None
        previous_status = (
            str(snapshot.get("runtime_status") or snapshot.get("status") or snapshot.get("display_status") or "running").strip()
            or "running"
        )
        normalized_status = "active" if previous_status == "running" else previous_status
        summary = (
            f"Cleared stale active turn state for run `{active_run_id}` after no live worker was found."
            if not completed_at
            else f"Cleared stale active turn state for completed run `{active_run_id}`."
        )
        append_jsonl(
            quest_root / ".ds" / "events.jsonl",
            {
                "event_id": generate_id("evt"),
                "type": "quest.turn_state_reconciled",
                "quest_id": quest_id,
                "abandoned_run_id": active_run_id,
                "previous_status": previous_status,
                "status": normalized_status,
                "completed_at": completed_at or None,
                "exit_code": exit_code if isinstance(exit_code, int) else None,
                "summary": summary,
                "created_at": utc_now(),
            },
        )
        self.logger.log(
            "warning",
            "quest.turn_state_reconciled",
            quest_id=quest_id,
            abandoned_run_id=active_run_id,
            previous_status=previous_status,
            status=normalized_status,
            completed_at=completed_at or None,
            exit_code=exit_code if isinstance(exit_code, int) else None,
        )
        return self.quest_service.mark_turn_finished(quest_id, status=normalized_status)

    def _recover_stalled_running_turn(
        self,
        quest_id: str,
        *,
        snapshot: dict | None = None,
        turn_reason: str,
    ) -> dict[str, object]:
        snapshot = dict(snapshot or self.quest_service.snapshot(quest_id))
        turn_state = self._refresh_turn_worker_state(quest_id)
        with self._turn_lock:
            state = self._turn_state.setdefault(quest_id, {"running": False, "pending": False})
            if state.get("recovery_pending"):
                return {
                    "snapshot": snapshot,
                    "blocked": True,
                }
        details = self._stalled_running_turn_details(
            quest_id,
            snapshot=snapshot,
            turn_state=turn_state,
            turn_reason=turn_reason,
        )
        if details is None:
            return {
                "snapshot": snapshot,
                "blocked": False,
            }

        active_run_id = str(snapshot.get("active_run_id") or "").strip()
        runner_name = self._runner_name_for(snapshot)
        with self._turn_lock:
            state = self._turn_state.setdefault(quest_id, {"running": False, "pending": False})
            if state.get("recovery_pending"):
                return {
                    "snapshot": snapshot,
                    "blocked": True,
                }
            state["pending"] = False
            state["stop_requested"] = True
            state["recovery_pending"] = True
        interrupted = False
        try:
            try:
                runner = self.get_runner(runner_name)
            except KeyError:
                runner = None
            if runner is not None and hasattr(runner, "interrupt"):
                interrupted = bool(getattr(runner, "interrupt")(quest_id))
            stopped_bash_session_ids = self._stop_active_bash_exec_sessions(
                quest_id,
                run_id=active_run_id or None,
                reason="stalled_turn_recovery",
                user_id="auto:stalled-turn-recovery",
            )
            turn_state = self._wait_for_turn_worker_exit(
                quest_id,
                timeout_seconds=_STALLED_RUNNING_TURN_INTERRUPT_TIMEOUT_SECONDS,
            )
            if turn_state.get("running"):
                self._ensure_recovery_resume_watch(quest_id, turn_reason="queued_user_messages")
                self.logger.log(
                    "warning",
                    "quest.turn_state_recovery_pending",
                    quest_id=quest_id,
                    abandoned_run_id=active_run_id or None,
                    reason=turn_reason,
                    silent_seconds=int(details.get("silent_seconds") or 0),
                    pending_user_message_count=int(details.get("pending_user_count") or 0),
                    interrupted=interrupted,
                )
                return {
                    "snapshot": snapshot,
                    "blocked": True,
                }

            previous_status = (
                str(snapshot.get("runtime_status") or snapshot.get("status") or snapshot.get("display_status") or "running").strip()
                or "running"
            )
            normalized_status = "active" if previous_status == "running" else previous_status
            summary = (
                f"Recovered stalled running turn `{active_run_id}` after "
                f"{int(details.get('silent_seconds') or 0)} seconds without tool activity while "
                f"{int(details.get('pending_user_count') or 0)} queued user message(s) were waiting."
            )
            if interrupted:
                summary = f"{summary} The active runner process was interrupted."
            if stopped_bash_session_ids:
                summary = f"{summary} Stopped {len(stopped_bash_session_ids)} bash_exec session(s)."
            quest_root = self.quest_service._quest_root(quest_id)
            append_jsonl(
                quest_root / ".ds" / "events.jsonl",
                {
                    "event_id": generate_id("evt"),
                    "type": "quest.turn_state_reconciled",
                    "quest_id": quest_id,
                    "abandoned_run_id": active_run_id or None,
                    "previous_status": previous_status,
                    "status": normalized_status,
                    "completed_at": None,
                    "exit_code": None,
                    "summary": summary,
                    "recovery_kind": "stalled_live_turn",
                    "interrupted": interrupted,
                    "stopped_bash_session_ids": stopped_bash_session_ids,
                    "created_at": utc_now(),
                },
            )
            self.logger.log(
                "warning",
                "quest.turn_state_reconciled",
                quest_id=quest_id,
                abandoned_run_id=active_run_id or None,
                previous_status=previous_status,
                status=normalized_status,
                recovery_kind="stalled_live_turn",
                interrupted=interrupted,
                stopped_bash_session_count=len(stopped_bash_session_ids),
            )
            snapshot = self.quest_service.mark_turn_finished(quest_id, status=normalized_status)
            with self._turn_lock:
                state = self._turn_state.setdefault(quest_id, {"running": False, "pending": False})
                state.pop("recovery_pending", None)
            return {
                "snapshot": snapshot,
                "blocked": False,
            }
        except Exception:
            with self._turn_lock:
                state = self._turn_state.setdefault(quest_id, {"running": False, "pending": False})
                state.pop("recovery_pending", None)
            raise

    def control_quest(self, quest_id: str, *, action: str, source: str = "local") -> dict:
        normalized_action = str(action or "").strip().lower()
        if normalized_action == "pause":
            return self.pause_quest(quest_id, source=source)
        if normalized_action == "stop":
            return self.stop_quest(quest_id, source=source)
        if normalized_action == "resume":
            return self.resume_quest(quest_id, source=source)
        raise ValueError(f"Unsupported quest control action `{action}`.")

    def pause_quest(self, quest_id: str, *, source: str = "local") -> dict:
        return self._interrupt_quest(quest_id, action="pause", status="paused", source=source)

    def stop_quest(self, quest_id: str, *, source: str = "local") -> dict:
        return self._interrupt_quest(quest_id, action="stop", status="stopped", source=source)

    def _interrupt_quest(self, quest_id: str, *, action: str, status: str, source: str) -> dict:
        previous_snapshot = self.quest_service.snapshot(quest_id)
        runner_name = self._runner_name_for(previous_snapshot)
        interrupted = False
        stopped_bash_session_ids: list[str] = []
        cancelled_pending = {
            "batch_id": None,
            "cancelled_count": 0,
            "cancelled": [],
        }
        try:
            runner = self.get_runner(runner_name)
        except KeyError:
            runner = None
        if runner is not None and hasattr(runner, "interrupt"):
            interrupted = bool(getattr(runner, "interrupt")(quest_id))
        with self._turn_lock:
            state = self._turn_state.setdefault(quest_id, {"running": False, "pending": False})
            state["pending"] = False
            state["stop_requested"] = True
        stopped_bash_session_ids = self._stop_active_bash_exec_sessions(
            quest_id,
            run_id=str(previous_snapshot.get("active_run_id") or "").strip() or None,
            reason=f"quest_{action}",
            user_id=source,
        )
        if action == "stop" and source == "local-admin":
            cancel_reason = "cancelled_by_daemon_shutdown" if source == "local-admin" else "cancelled_by_stop"
            cancelled_pending = self.quest_service.cancel_pending_user_messages(
                quest_id,
                reason=cancel_reason,
                action=action,
                source=source,
            )
        stop_reason = "daemon_shutdown" if action == "stop" and source == "local-admin" else f"user_{action}"
        snapshot = self.quest_service.mark_turn_finished(quest_id, status=status, stop_reason=stop_reason)
        verb = "paused" if action == "pause" else "stopped"
        summary = f"Quest {quest_id} {verb}."
        if interrupted:
            summary = f"Quest {quest_id} {verb} and the active runner was interrupted."
        if stopped_bash_session_ids:
            summary = f"{summary} Stopped {len(stopped_bash_session_ids)} bash_exec session(s)."
        cancelled_count = int(cancelled_pending.get("cancelled_count") or 0)
        if cancelled_count > 0:
            summary = f"{summary} Cancelled {cancelled_count} queued user message(s)."
        event = self._append_control_event(
            quest_id,
            action=action,
            source=source,
            status=str(snapshot.get("status") or status),
            interrupted=interrupted,
            cancelled_pending_user_message_count=cancelled_count,
            summary=summary,
        )
        notice = self._announce_control_state(
            quest_id,
            action=action,
            source=source,
            snapshot=snapshot,
            interrupted=interrupted,
            cancelled_pending_user_message_count=cancelled_count,
            previous_snapshot=previous_snapshot,
        )
        return {
            "ok": True,
            "quest_id": quest_id,
            "action": action,
            "interrupted": interrupted,
            "cancelled_pending_user_message_count": cancelled_count,
            "stopped_bash_session_ids": stopped_bash_session_ids,
            "snapshot": snapshot,
            "message": summary,
            "event": event,
            "notice": notice,
        }

    def _quiet_interrupt_for_turn_restart(self, quest_id: str, *, source: str) -> dict[str, Any]:
        snapshot = self.quest_service.snapshot(quest_id)
        snapshot = self._reconcile_stale_active_turn(quest_id, snapshot=snapshot)
        runner_name = self._runner_name_for(snapshot)
        active_run_id = str(snapshot.get("active_run_id") or "").strip() or None
        turn_state = self._refresh_turn_worker_state(quest_id)
        runtime_status = str(snapshot.get("runtime_status") or snapshot.get("status") or "").strip().lower()
        if not active_run_id and not turn_state.get("running"):
            if runtime_status in {"stopped", "paused", "completed", "error"}:
                snapshot = self.quest_service.set_status(quest_id, "active")
            return {
                "snapshot": snapshot,
                "interrupted": False,
                "stopped_bash_session_ids": [],
            }

        interrupted = False
        try:
            runner = self.get_runner(runner_name)
        except KeyError:
            runner = None
        with self._turn_lock:
            state = self._turn_state.setdefault(quest_id, {"running": False, "pending": False})
            state["pending"] = False
            state["stop_requested"] = True
        runner_supports_interrupt = runner is not None and hasattr(runner, "interrupt")
        if runner_supports_interrupt:
            interrupted = bool(getattr(runner, "interrupt")(quest_id))
        stopped_bash_session_ids = self._stop_active_bash_exec_sessions(
            quest_id,
            run_id=active_run_id,
            reason="immediate_read",
            user_id=source,
        )
        turn_state = self._wait_for_turn_worker_exit(
            quest_id,
            timeout_seconds=_IMMEDIATE_READ_INTERRUPT_TIMEOUT_SECONDS,
        )
        if turn_state.get("running"):
            detail_parts = [
                f"runner={runner_name or 'unknown'}",
                f"interrupt_attempted={runner_supports_interrupt}",
                f"interrupt_returned={interrupted}",
                f"active_run_id={active_run_id or 'none'}",
                f"runtime_status={runtime_status or 'unknown'}",
                f"timeout_seconds={_IMMEDIATE_READ_INTERRUPT_TIMEOUT_SECONDS:g}",
            ]
            worker = turn_state.get("worker")
            if isinstance(worker, threading.Thread):
                detail_parts.append(f"worker_alive={worker.is_alive()}")
                detail_parts.append(f"worker_name={worker.name}")
            stopped_count = len(stopped_bash_session_ids)
            if stopped_count > 0:
                detail_parts.append(f"stopped_bash_sessions={stopped_count}")
            if runner is None:
                detail_parts.append("reason=runner_not_available")
            elif not runner_supports_interrupt:
                detail_parts.append("reason=runner_has_no_interrupt")
            elif not interrupted:
                detail_parts.append("reason=runner_interrupt_returned_false")
            else:
                detail_parts.append("reason=worker_did_not_exit_before_timeout")
            raise RuntimeError(
                "The active agent turn could not be interrupted for immediate read. "
                + "; ".join(detail_parts)
            )
        normalized_status = "active" if runtime_status == "running" else (runtime_status or "active")
        if normalized_status in {"stopped", "paused", "completed", "error"}:
            snapshot = self.quest_service.set_status(quest_id, "active")
        else:
            snapshot = self.quest_service.mark_turn_finished(quest_id, status=normalized_status)
        with self._turn_lock:
            state = self._turn_state.setdefault(quest_id, {"running": False, "pending": False})
            state["stop_requested"] = False
            state["running"] = False
            state.pop("worker", None)
        return {
            "snapshot": snapshot,
            "interrupted": interrupted,
            "stopped_bash_session_ids": stopped_bash_session_ids,
        }

    def read_queued_user_messages_now(
        self,
        quest_id: str,
        *,
        message_id: str | None = None,
        source: str = "local",
    ) -> dict[str, Any]:
        snapshot = self.quest_service.snapshot(quest_id)
        snapshot = self._reconcile_stale_active_turn(quest_id, snapshot=snapshot)
        quest_root = self.quest_service._quest_root(quest_id)
        target_message_id = str(message_id or "").strip() or None
        if target_message_id:
            status_payload = self.quest_service.pending_user_message_status(
                quest_root,
                message_id=target_message_id,
            )
            queue_state = str(status_payload.get("queue_state") or "missing")
            current_message_state = (
                dict(status_payload.get("message_state") or {})
                if isinstance(status_payload.get("message_state"), dict)
                else None
            )
            if queue_state == "read":
                return {
                    "ok": True,
                    "status": "already_read",
                    "quest_id": quest_id,
                    "message": "This message was already sent to the agent.",
                    "message_ids": [target_message_id],
                    "current_message_state": current_message_state,
                    "snapshot": snapshot,
                }
            if queue_state == "withdrawn":
                return {
                    "ok": False,
                    "status": "withdrawn",
                    "quest_id": quest_id,
                    "message": "This message was already withdrawn from the waiting queue.",
                    "message_ids": [target_message_id],
                    "current_message_state": current_message_state,
                    "snapshot": snapshot,
                }
            if queue_state == "missing":
                return {
                    "ok": False,
                    "status": "missing",
                    "quest_id": quest_id,
                    "message": f"Message `{target_message_id}` is not waiting in the queue.",
                    "message_ids": [target_message_id],
                    "current_message_state": current_message_state,
                    "snapshot": snapshot,
                }
        queue_payload = self.quest_service._read_message_queue(quest_root)
        pending = [dict(item) for item in (queue_payload.get("pending") or [])]
        if not pending:
            return {
                "ok": False,
                "status": "empty",
                "quest_id": quest_id,
                "message": "No unread user message is waiting in the queue.",
                "snapshot": snapshot,
            }

        try:
            restart = self._quiet_interrupt_for_turn_restart(quest_id, source=source)
        except RuntimeError as exc:
            failed_message_ids = (
                [target_message_id]
                if target_message_id
                else [
                    str(item.get("message_id") or "").strip()
                    for item in pending
                    if str(item.get("message_id") or "").strip()
                ]
            )
            return {
                "ok": False,
                "status": "interrupt_failed",
                "quest_id": quest_id,
                "message": str(exc),
                "message_ids": failed_message_ids,
                "snapshot": snapshot,
            }
        mailbox_payload = self.quest_service.consume_pending_user_messages(
            quest_root,
            interaction_id=None,
            delivery_reason="immediate_read",
        )
        recent_inbound_messages = [
            dict(item)
            for item in (mailbox_payload.get("recent_inbound_messages") or [])
            if isinstance(item, dict)
        ]
        if not recent_inbound_messages:
            return {
                "ok": False,
                "quest_id": quest_id,
                "message": "No unread user message remained after the restart.",
            }

        self.quest_service.set_turn_message_override(
            quest_root,
            turn_reason="immediate_read",
            message=str(mailbox_payload.get("agent_instruction") or "").strip(),
            message_ids=[
                str(item.get("message_id") or "").strip()
                for item in recent_inbound_messages
                if str(item.get("message_id") or "").strip()
            ],
            delivery_batch_id=str(((mailbox_payload.get("delivery_batch") or {}).get("batch_id") or "")).strip() or None,
            source=source,
        )
        post_snapshot = self.quest_service.snapshot(quest_id)
        runtime_status = str(post_snapshot.get("runtime_status") or post_snapshot.get("status") or "").strip().lower()
        if runtime_status in {"stopped", "paused", "completed", "error"}:
            post_snapshot = self.quest_service.set_status(quest_id, "active")
        scheduling = self.schedule_turn(quest_id, reason="immediate_read")
        return {
            "ok": True,
            "status": "scheduled",
            "quest_id": quest_id,
            "snapshot": self.quest_service.snapshot(quest_id),
            "message_ids": [
                str(item.get("message_id") or "").strip()
                for item in recent_inbound_messages
                if str(item.get("message_id") or "").strip()
            ],
            "delivery_batch": mailbox_payload.get("delivery_batch"),
            "recent_inbound_messages": recent_inbound_messages,
            "interrupted": bool(restart.get("interrupted")),
            "stopped_bash_session_ids": list(restart.get("stopped_bash_session_ids") or []),
            "message": "Queued user messages were forced into an immediate-read turn.",
            **scheduling,
        }

    def withdraw_queued_user_message(
        self,
        quest_id: str,
        *,
        message_id: str,
        source: str = "local",
    ) -> dict[str, Any]:
        quest_root = self.quest_service._quest_root(quest_id)
        result = self.quest_service.withdraw_pending_user_message(
            quest_id,
            message_id=message_id,
            source=source,
        )
        result.setdefault("quest_id", quest_id)
        result["snapshot"] = self.quest_service.snapshot(quest_id)
        return result

    def _stop_active_bash_exec_sessions(
        self,
        quest_id: str,
        *,
        run_id: str | None,
        reason: str,
        user_id: str,
    ) -> list[str]:
        quest_root = self.quest_service._quest_root(quest_id)
        try:
            sessions = self.bash_exec_service.list_sessions(quest_root, limit=500)
        except Exception:
            return []

        stopped: list[str] = []
        for session in sessions:
            bash_id = str(session.get("bash_id") or "").strip()
            if not bash_id:
                continue
            kind = str(session.get("kind") or "exec").strip().lower()
            status = str(session.get("status") or "").strip().lower()
            if kind == "terminal" or status in {"completed", "failed", "terminated"}:
                continue
            session_run_id = str(session.get("agent_instance_id") or session.get("task_id") or "").strip()
            if run_id and session_run_id and session_run_id != run_id:
                continue
            try:
                self.bash_exec_service.request_stop(
                    quest_root,
                    bash_id,
                    reason=reason,
                    user_id=user_id,
                )
            except Exception:
                continue
            stopped.append(bash_id)
        return stopped

    def resume_quest(self, quest_id: str, *, source: str = "local") -> dict:
        previous_snapshot = self.quest_service.snapshot(quest_id)
        with self._turn_lock:
            state = self._turn_state.setdefault(quest_id, {"running": False, "pending": False})
            state["stop_requested"] = False
        snapshot = self.quest_service.snapshot(quest_id)
        next_status = "running" if snapshot.get("status") == "running" else "active"
        snapshot = self.quest_service.set_status(quest_id, next_status)
        recovery_abandoned_run_id = None
        recovery_summary = None
        if source.startswith("auto:daemon-recovery"):
            recent_events = self.quest_service.events(quest_id)["events"]
            for item in reversed(recent_events[-20:]):
                if str(item.get("type") or "").strip() != "quest.runtime_reconciled":
                    continue
                recovery_abandoned_run_id = str(item.get("abandoned_run_id") or "").strip() or None
                recovery_summary = str(item.get("summary") or "").strip() or None
                break
        self.quest_service.update_runtime_state(
            quest_root=self.quest_service._quest_root(quest_id),
            last_resume_source=source,
            last_resume_at=utc_now(),
            last_recovery_abandoned_run_id=recovery_abandoned_run_id,
            last_recovery_summary=recovery_summary,
        )
        scheduling: dict[str, Any] | None = None
        if not source.startswith("auto:"):
            if int(snapshot.get("pending_user_message_count") or 0) > 0:
                scheduling = self.schedule_turn(quest_id, reason="queued_user_messages")
            else:
                continue_payload = self.submit_user_message(
                    quest_id,
                    text=_RESUME_CONTINUE_TEXT,
                    source=self._resume_continue_source(source),
                )
                scheduling = {
                    "scheduled": bool(continue_payload.get("scheduled")),
                    "started": bool(continue_payload.get("started")),
                    "queued": bool(continue_payload.get("queued")),
                    "reason": str(continue_payload.get("reason") or "user_message"),
                    "resume_trigger_message": continue_payload.get("message"),
                }
        summary = f"Quest {quest_id} resumed."
        event = self._append_control_event(
            quest_id,
            action="resume",
            source=source,
            status=str(snapshot.get("status") or next_status),
            interrupted=False,
            summary=summary,
            automated=source.startswith("auto:"),
        )
        notice = self._announce_control_state(
            quest_id,
            action="resume",
            source=source,
            snapshot=snapshot,
            interrupted=False,
            cancelled_pending_user_message_count=0,
            previous_snapshot=previous_snapshot,
        )
        return {
            "ok": True,
            "quest_id": quest_id,
            "action": "resume",
            "interrupted": False,
            "snapshot": snapshot,
            "message": summary,
            "event": event,
            "notice": notice,
            **(dict(scheduling or {})),
        }

    def _append_control_event(
        self,
        quest_id: str,
        *,
        action: str,
        source: str,
        status: str,
        interrupted: bool,
        summary: str,
        cancelled_pending_user_message_count: int = 0,
        automated: bool = False,
    ) -> dict:
        payload = {
            "event_id": generate_id("evt"),
            "type": "quest.control",
            "quest_id": quest_id,
            "action": action,
            "source": source,
            "status": status,
            "interrupted": interrupted,
            "cancelled_pending_user_message_count": max(0, int(cancelled_pending_user_message_count or 0)),
            "summary": summary,
            "automated": automated,
            "created_at": utc_now(),
        }
        append_jsonl(self.home / "quests" / quest_id / ".ds" / "events.jsonl", payload)
        return payload

    def _announce_control_state(
        self,
        quest_id: str,
        *,
        action: str,
        source: str,
        snapshot: dict,
        interrupted: bool,
        cancelled_pending_user_message_count: int,
        previous_snapshot: dict | None = None,
    ) -> dict:
        quest_root = self.quest_service._quest_root(quest_id)
        message = self._control_notice_message(
            quest_id,
            action=action,
            source=source,
            snapshot=snapshot,
            interrupted=interrupted,
            cancelled_pending_user_message_count=cancelled_pending_user_message_count,
            previous_snapshot=previous_snapshot,
        )
        history_record = self.quest_service.append_message(
            quest_id,
            role="assistant",
            content=message,
            source="system-control",
        )
        connectors = self.artifact_service._connectors_config()
        targets = self.artifact_service._select_delivery_targets(
            self.artifact_service._bound_conversations(quest_root),
            connectors=connectors,
        )
        attachments = [
            {
                "kind": "quest_control",
                "action": action,
                "status": snapshot.get("status"),
                "source": source,
                "branch": snapshot.get("branch"),
                "workspace_root": snapshot.get("current_workspace_root") or snapshot.get("quest_root"),
                "interrupted": interrupted,
                "cancelled_pending_user_message_count": int(cancelled_pending_user_message_count or 0),
                "previous_status": (
                    (previous_snapshot or {}).get("runtime_status")
                    or (previous_snapshot or {}).get("status")
                ),
                "stop_reason": snapshot.get("stop_reason"),
            }
        ]
        delivery_targets: list[str] = []
        importance = "warning" if action in {"pause", "stop"} else "info"
        for target in targets:
            channel_name = self.artifact_service._normalize_channel_name(target)
            payload = {
                "quest_root": str(quest_root),
                "quest_id": quest_id,
                "conversation_id": target,
                "kind": "progress",
                "message": message,
                "response_phase": "control",
                "importance": importance,
                "attachments": attachments,
            }
            if self.artifact_service._send_to_channel(channel_name, payload, connectors=connectors):
                delivery_targets.append(target)
        return {
            "message": message,
            "history_record": history_record,
            "delivery_targets": delivery_targets,
        }

    def _control_notice_message(
        self,
        quest_id: str,
        *,
        action: str,
        source: str,
        snapshot: dict,
        interrupted: bool,
        cancelled_pending_user_message_count: int,
        previous_snapshot: dict | None = None,
    ) -> str:
        if action == "resume":
            lines = [
                self._polite_copy(
                    zh=f"我回来继续干活啦，Quest `{quest_id}` 已恢复。",
                    en=f"I’m back on it. Quest `{quest_id}` has resumed. ✨",
                ),
                self._polite_copy(
                    zh="刚才的进度都还在，我会直接接着往下推。",
                    en="The current progress is still here, and I’ll pick up right where I left off.",
                ),
            ]
            if source.startswith("auto:daemon-recovery"):
                lines.append(
                    self._polite_copy(
                        zh="刚才是 daemon 意外断开了，不过现在已经自动接回来了。",
                        en="The daemon dropped unexpectedly, but it has been recovered automatically. 🔧",
                    )
                )
        elif action == "pause":
            lines = [
                self._polite_copy(
                    zh=f"我先帮您把 Quest `{quest_id}` 稳稳停在这里啦。",
                    en=f"I’ve paused Quest `{quest_id}` right here for now. ⏸️",
                ),
                self._polite_copy(
                    zh="当前进度我都保留好了，您发新消息或者执行 `/resume`，我就会继续。",
                    en="I kept the current progress safe. Send a new message or use `/resume`, and I’ll continue.",
                ),
            ]
        else:
            lines = [
                self._polite_copy(
                    zh=f"这轮我先收住啦，Quest `{quest_id}` 已停止运行。",
                    en=f"I’m wrapping this round here. Quest `{quest_id}` has stopped. 📌",
                ),
                self._polite_copy(
                    zh="不过别担心，当前进度我都保留好了；您发新消息或者执行 `/resume`，我就能接着干。",
                    en="Don’t worry, the current progress is still preserved. Send a new message or use `/resume`, and I’ll keep going.",
                ),
            ]
        if interrupted:
            lines.append(
                self._polite_copy(
                    zh="刚才正在跑的任务已经被打断了。",
                    en="The active runner was interrupted.",
                )
            )
        cancelled_count = max(0, int(cancelled_pending_user_message_count or 0))
        if cancelled_count > 0:
            lines.append(
                self._polite_copy(
                    zh=f"另外我还顺手清掉了 {cancelled_count} 条排队消息，避免旧指令继续堆着。",
                    en=f"I also cleared {cancelled_count} queued message(s) so stale instructions do not pile up.",
                )
            )
        previous_status = str(
            (previous_snapshot or {}).get("runtime_status")
            or (previous_snapshot or {}).get("status")
            or ""
        ).strip()
        if previous_status and action == "resume":
            lines.append(
                self._polite_copy(
                    zh=f"恢复前的状态是：`{previous_status}`。",
                    en=f"Previous status: `{previous_status}`.",
                )
            )
        return "\n".join(lines)

    def _drain_turns(self, quest_id: str) -> None:
        while True:
            with self._turn_lock:
                state = self._turn_state.setdefault(quest_id, {"running": True, "pending": False})
                if not state.get("pending"):
                    state["running"] = False
                    state.pop("worker", None)
                    return
                state["pending"] = False
            try:
                self._run_quest_turn(quest_id)
            except Exception as exc:
                self.logger.log(
                    "error",
                    "daemon.turn_worker_crashed",
                    quest_id=quest_id,
                    error=str(exc),
                    traceback=traceback.format_exc(),
                )

    def _run_quest_turn(self, quest_id: str) -> None:
        with self._turn_lock:
            state = dict(self._turn_state.get(quest_id) or {})
        turn_reason = str(state.get("reason") or "user_message").strip() or "user_message"
        if state.get("stop_requested"):
            return
        snapshot = self.quest_service.snapshot(quest_id)
        runtime_status = str(snapshot.get("runtime_status") or snapshot.get("status") or "").strip()
        if runtime_status in {"stopped", "paused", "completed", "error"} and not snapshot.get("active_run_id"):
            return
        quest_root = Path(snapshot["quest_root"])
        turn_override = (
            self.quest_service.consume_turn_message_override(
                quest_root,
                expected_turn_reason=turn_reason,
            )
            if turn_reason == "immediate_read"
            else None
        )
        latest_user_message = self._latest_actionable_user_message(quest_id, turn_reason=turn_reason)
        if turn_reason not in {"auto_continue", "immediate_read"} and latest_user_message is None:
            return

        runner_name = self._runner_name_for(snapshot)
        runner_cfg = self.runners_config.get(runner_name, {})
        turn_intent = self._turn_intent_for(latest_user_message, turn_reason=turn_reason)
        turn_mode = self._turn_mode_for(snapshot, latest_user_message, turn_reason=turn_reason)
        skill_id = self._turn_skill_for(snapshot, latest_user_message, turn_reason=turn_reason, turn_mode=turn_mode)
        run_id = generate_id("run")
        model = str(runner_cfg.get("model", "gpt-5.4"))
        run_message = ""
        claimed_message_id: str | None = None
        if turn_reason == "immediate_read":
            run_message = str((turn_override or {}).get("message") or "").strip()
            if not run_message:
                return
        elif turn_reason != "auto_continue":
            run_message = str((latest_user_message or {}).get("content") or "").strip()
            claimed_message_id = str((latest_user_message or {}).get("id") or "").strip() or None
            if not run_message:
                return

        if runner_cfg.get("enabled") is False:
            self._record_turn_error(
                quest_id=quest_id,
                runner_name=runner_name,
                run_id=run_id,
                skill_id=skill_id,
                model=model,
                summary=f"Runner `{runner_name}` is disabled in `runners.yaml`.",
            )
            return

        try:
            runner = self.get_runner(runner_name)
        except KeyError as exc:
            self._record_turn_error(
                quest_id=quest_id,
                runner_name=runner_name,
                run_id=run_id,
                skill_id=skill_id,
                model=model,
                summary=str(exc),
            )
            return

        binary_issue = self._runner_binary_issue(runner_name, runner)
        if binary_issue is not None:
            self._record_turn_error(
                quest_id=quest_id,
                runner_name=runner_name,
                run_id=run_id,
                skill_id=skill_id,
                model=model,
                summary=binary_issue,
            )
            return

        raw_reasoning_effort = runner_cfg.get("model_reasoning_effort") if isinstance(runner_cfg, dict) else None
        reasoning_effort = (
            str(raw_reasoning_effort).strip()
            if raw_reasoning_effort is not None and str(raw_reasoning_effort).strip()
            else ("xhigh" if raw_reasoning_effort is None else None)
        )
        with self._turn_lock:
            if bool((self._turn_state.get(quest_id) or {}).get("stop_requested")):
                return
        if claimed_message_id:
            self.quest_service.claim_pending_user_message_for_turn(
                quest_id,
                message_id=claimed_message_id,
                run_id=run_id,
            )
        retry_policy = self._runner_retry_policy(runner_name, runner_cfg if isinstance(runner_cfg, dict) else {})
        max_attempts = int(retry_policy.get("max_attempts") or 1)
        resumed_start_attempt, resumed_turn_id, retry_context = self._resume_retry_state(
            snapshot,
            max_attempts=max_attempts,
        )
        turn_id = resumed_turn_id or generate_id("turn")
        worktree_root = Path(str(snapshot["current_workspace_root"])) if snapshot.get("current_workspace_root") else None

        for attempt_index in range(resumed_start_attempt, max_attempts + 1):
            current_run_id = run_id if attempt_index == 1 else generate_id("run")
            if attempt_index > 1:
                self._append_retry_event(
                    quest_id,
                    event_type="runner.turn_retry_started",
                    runner_name=runner_name,
                    run_id=current_run_id,
                    turn_id=turn_id,
                    skill_id=skill_id,
                    model=model,
                    attempt_index=attempt_index,
                    max_attempts=max_attempts,
                    summary=f"Retry attempt {attempt_index}/{max_attempts} started.",
                    previous_run_id=str((retry_context or {}).get("previous_run_id") or "") or None,
                )

            request = RunRequest(
                quest_id=quest_id,
                quest_root=quest_root,
                worktree_root=worktree_root,
                run_id=current_run_id,
                skill_id=skill_id,
                message=run_message,
                model=model,
                approval_policy=str(runner_cfg.get("approval_policy", "on-request")),
                sandbox_mode=str(runner_cfg.get("sandbox_mode", "workspace-write")),
                turn_reason=turn_reason,
                turn_intent=turn_intent,
                turn_mode=turn_mode,
                reasoning_effort=reasoning_effort,
                turn_id=turn_id,
                attempt_index=attempt_index,
                max_attempts=max_attempts,
                retry_context=retry_context,
            )
            self.quest_service.mark_turn_started(quest_id, run_id=current_run_id, status="running")
            if attempt_index > 1:
                self.quest_service.update_runtime_state(
                    quest_root=quest_root,
                    display_status="retrying",
                    retry_state={
                        "turn_id": turn_id,
                        "attempt_index": attempt_index,
                        "max_attempts": max_attempts,
                        "last_run_id": str((retry_context or {}).get("previous_run_id") or "") or None,
                        "last_error": str((retry_context or {}).get("failure_summary") or "") or None,
                        "next_retry_at": None,
                    },
                )
            try:
                try:
                    result = runner.run(request)
                except Exception as exc:  # pragma: no cover - exercised via integration behavior
                    if self._turn_stop_requested(quest_id):
                        return
                    failure_summary = f"Runner `{runner_name}` failed on attempt {attempt_index}/{max_attempts}: {exc}"
                    retry_context = self._build_retry_context(
                        quest_id=quest_id,
                        failed_run_id=current_run_id,
                        turn_id=turn_id,
                        attempt_index=attempt_index,
                        max_attempts=max_attempts,
                        failure_kind="exception",
                        failure_summary=failure_summary,
                        previous_exit_code=None,
                        previous_output_text="",
                        stderr_text=str(exc),
                    )
                    diagnosis = self._non_retryable_failure_diagnosis(
                        runner_name=runner_name,
                        summary=failure_summary,
                        stderr_text=str(exc),
                        output_text="",
                    )
                    if diagnosis is not None:
                        self.quest_service.update_runtime_state(
                            quest_root=quest_root,
                            continuation_policy="wait_for_user_or_resume",
                            continuation_reason="non_retryable_runner_error",
                            continuation_updated_at=utc_now(),
                        )
                        self._record_turn_error(
                            quest_id=quest_id,
                            runner_name=runner_name,
                            run_id=current_run_id,
                            skill_id=skill_id,
                            model=model,
                            summary=f"{diagnosis.problem} {failure_summary}".strip(),
                            retry_state=None,
                            diagnosis_code=diagnosis.code,
                            guidance=list(diagnosis.guidance),
                        )
                        return
                    if bool(retry_policy.get("enabled")) and attempt_index < max_attempts:
                        delay_seconds = self._retry_delay_seconds(retry_policy, attempt_index=attempt_index + 1)
                        next_retry_at = self._retry_next_timestamp(delay_seconds)
                        self.quest_service.update_runtime_state(
                            quest_root=quest_root,
                            status="running",
                            display_status="retrying",
                            active_run_id=None,
                            retry_state={
                                "turn_id": turn_id,
                                "attempt_index": attempt_index,
                                "max_attempts": max_attempts,
                                "last_run_id": current_run_id,
                                "last_error": failure_summary,
                                "next_retry_at": next_retry_at,
                            },
                        )
                        self._append_retry_event(
                            quest_id,
                            event_type="runner.turn_retry_scheduled",
                            runner_name=runner_name,
                            run_id=current_run_id,
                            turn_id=turn_id,
                            skill_id=skill_id,
                            model=model,
                            attempt_index=attempt_index,
                            max_attempts=max_attempts,
                            summary=f"Attempt {attempt_index}/{max_attempts} failed. Retrying in {delay_seconds:.1f}s.",
                            failure_summary=failure_summary,
                            backoff_seconds=delay_seconds,
                            next_attempt_index=attempt_index + 1,
                        )
                        if self._wait_for_retry_delay(quest_id, delay_seconds):
                            continue
                        self._append_retry_event(
                            quest_id,
                            event_type="runner.turn_retry_aborted",
                            runner_name=runner_name,
                            run_id=current_run_id,
                            turn_id=turn_id,
                            skill_id=skill_id,
                            model=model,
                            attempt_index=attempt_index,
                            max_attempts=max_attempts,
                            summary="Retry sequence aborted because the quest was stopped or paused.",
                            failure_summary=failure_summary,
                        )
                        return
                    exhausted_summary = f"{failure_summary} Retry budget exhausted after {attempt_index} attempt(s)."
                    self._append_retry_event(
                        quest_id,
                        event_type="runner.turn_retry_exhausted",
                        runner_name=runner_name,
                        run_id=current_run_id,
                        turn_id=turn_id,
                        skill_id=skill_id,
                        model=model,
                        attempt_index=attempt_index,
                        max_attempts=max_attempts,
                        summary=exhausted_summary,
                        failure_summary=failure_summary,
                    )
                    self._record_turn_error(
                        quest_id=quest_id,
                        runner_name=runner_name,
                        run_id=current_run_id,
                        skill_id=skill_id,
                        model=model,
                        summary=exhausted_summary,
                        retry_state=None,
                    )
                    return

                if self._turn_stop_requested(quest_id):
                    return

                if result.ok:
                    self.quest_service.update_runtime_state(quest_root=quest_root, retry_state=None)
                    if result.output_text:
                        result_attachment = [
                            {
                                "kind": "runner_result",
                                "run_id": result.run_id,
                                "skill_id": skill_id,
                                "runner": runner_name,
                                "model": result.model,
                                "exit_code": result.exit_code,
                                "history_root": str(result.history_root),
                                "run_root": str(result.run_root),
                            }
                        ]
                        try:
                            self.quest_service.append_message(
                                quest_id,
                                role="assistant",
                                content=result.output_text,
                                source=runner_name,
                                run_id=result.run_id,
                                skill_id=skill_id,
                            )
                        except Exception as exc:
                            self._record_turn_postprocess_warning(
                                quest_id=quest_id,
                                runner_name=runner_name,
                                run_id=result.run_id,
                                skill_id=skill_id,
                                model=result.model,
                                stage="append_message",
                                error=exc,
                            )
                        try:
                            self._relay_quest_message_to_bound_connectors(
                                quest_id,
                                message=result.output_text,
                                kind="assistant",
                                response_phase="final",
                                importance="normal",
                                attachments=result_attachment,
                            )
                        except Exception as exc:
                            self._record_turn_postprocess_warning(
                                quest_id=quest_id,
                                runner_name=runner_name,
                                run_id=result.run_id,
                                skill_id=skill_id,
                                model=result.model,
                                stage="connector_relay",
                                error=exc,
                            )
                    self._normalize_status_after_turn(quest_id, turn_reason=turn_reason)
                    return

                failure_summary = f"Runner `{runner_name}` exited with code {result.exit_code} on attempt {attempt_index}/{max_attempts}."
                stderr_excerpt = self._trim_text(result.stderr_text, limit=240)
                if stderr_excerpt:
                    failure_summary = f"{failure_summary} stderr: {stderr_excerpt}"
                retry_context = self._build_retry_context(
                    quest_id=quest_id,
                    failed_run_id=result.run_id,
                    turn_id=turn_id,
                    attempt_index=attempt_index,
                    max_attempts=max_attempts,
                    failure_kind="exit_code",
                    failure_summary=failure_summary,
                    previous_exit_code=result.exit_code,
                    previous_output_text=result.output_text,
                    stderr_text=result.stderr_text,
                )
                diagnosis = self._non_retryable_failure_diagnosis(
                    runner_name=runner_name,
                    summary=failure_summary,
                    stderr_text=result.stderr_text,
                    output_text=result.output_text,
                )
                if diagnosis is not None:
                    self.quest_service.update_runtime_state(
                        quest_root=quest_root,
                        continuation_policy="wait_for_user_or_resume",
                        continuation_reason="non_retryable_runner_error",
                        continuation_updated_at=utc_now(),
                    )
                    self._record_turn_error(
                        quest_id=quest_id,
                        runner_name=runner_name,
                        run_id=result.run_id,
                        skill_id=skill_id,
                        model=model,
                        summary=f"{diagnosis.problem} {failure_summary}".strip(),
                        retry_state=None,
                        diagnosis_code=diagnosis.code,
                        guidance=list(diagnosis.guidance),
                    )
                    return
                if bool(retry_policy.get("enabled")) and attempt_index < max_attempts:
                    delay_seconds = self._retry_delay_seconds(retry_policy, attempt_index=attempt_index + 1)
                    next_retry_at = self._retry_next_timestamp(delay_seconds)
                    self.quest_service.update_runtime_state(
                        quest_root=quest_root,
                        status="running",
                        display_status="retrying",
                        active_run_id=None,
                        retry_state={
                            "turn_id": turn_id,
                            "attempt_index": attempt_index,
                            "max_attempts": max_attempts,
                            "last_run_id": result.run_id,
                            "last_error": failure_summary,
                            "next_retry_at": next_retry_at,
                        },
                    )
                    self._append_retry_event(
                        quest_id,
                        event_type="runner.turn_retry_scheduled",
                        runner_name=runner_name,
                        run_id=result.run_id,
                        turn_id=turn_id,
                        skill_id=skill_id,
                        model=model,
                        attempt_index=attempt_index,
                        max_attempts=max_attempts,
                        summary=f"Attempt {attempt_index}/{max_attempts} failed. Retrying in {delay_seconds:.1f}s.",
                        failure_summary=failure_summary,
                        backoff_seconds=delay_seconds,
                        next_attempt_index=attempt_index + 1,
                    )
                    if self._wait_for_retry_delay(quest_id, delay_seconds):
                        continue
                    self._append_retry_event(
                        quest_id,
                        event_type="runner.turn_retry_aborted",
                        runner_name=runner_name,
                        run_id=result.run_id,
                        turn_id=turn_id,
                        skill_id=skill_id,
                        model=model,
                        attempt_index=attempt_index,
                        max_attempts=max_attempts,
                        summary="Retry sequence aborted because the quest was stopped or paused.",
                        failure_summary=failure_summary,
                    )
                    return

                exhausted_summary = f"{failure_summary} Retry budget exhausted after {attempt_index} attempt(s)."
                self._append_retry_event(
                    quest_id,
                    event_type="runner.turn_retry_exhausted",
                    runner_name=runner_name,
                    run_id=result.run_id,
                    turn_id=turn_id,
                    skill_id=skill_id,
                    model=model,
                    attempt_index=attempt_index,
                    max_attempts=max_attempts,
                    summary=exhausted_summary,
                    failure_summary=failure_summary,
                )
                self._record_turn_error(
                    quest_id=quest_id,
                    runner_name=runner_name,
                    run_id=result.run_id,
                    skill_id=skill_id,
                    model=model,
                    summary=exhausted_summary,
                    retry_state=None,
                )
                return
            finally:
                self._ensure_turn_cleanup(
                    quest_id,
                    run_id=current_run_id,
                    turn_reason=turn_reason,
                )

    def _runner_name_for(self, snapshot: dict) -> str:
        configured = self.config_manager.load_named("config")
        return str(snapshot.get("runner") or configured.get("default_runner", "codex")).strip().lower()

    @staticmethod
    def _stage_state_fingerprint(snapshot: dict) -> str:
        paper_health = (
            dict(snapshot.get("paper_contract_health") or {})
            if isinstance(snapshot.get("paper_contract_health"), dict)
            else {}
        )
        payload = {
            "active_anchor": str(snapshot.get("active_anchor") or "").strip() or None,
            "active_run_id": str(snapshot.get("active_run_id") or "").strip() or None,
            "active_analysis_campaign_id": str(snapshot.get("active_analysis_campaign_id") or "").strip() or None,
            "next_pending_slice_id": str(snapshot.get("next_pending_slice_id") or "").strip() or None,
            "current_workspace_branch": str(snapshot.get("current_workspace_branch") or "").strip() or None,
            "continuation_policy": str(snapshot.get("continuation_policy") or "").strip() or None,
            "paper": {
                "closure_state": str(paper_health.get("closure_state") or "").strip() or None,
                "delivery_state": str(paper_health.get("delivery_state") or "").strip() or None,
                "recommended_next_stage": str(paper_health.get("recommended_next_stage") or "").strip() or None,
                "recommended_action": str(paper_health.get("recommended_action") or "").strip() or None,
                "blocking_reasons": list(paper_health.get("blocking_reasons") or []),
                "keep_bundle_fixed_by_default": bool(paper_health.get("keep_bundle_fixed_by_default")),
            },
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    @staticmethod
    def _turn_intent_for(latest_user_message: dict | None, *, turn_reason: str = "user_message") -> str:
        if str(turn_reason or "").strip() == "auto_continue" or latest_user_message is None:
            return "continue_stage"
        return classify_turn_intent(str(latest_user_message.get("content") or "").strip())

    @staticmethod
    def _turn_mode_for(snapshot: dict, latest_user_message: dict | None, *, turn_reason: str = "user_message") -> str:
        normalized_reason = str(turn_reason or "").strip() or "user_message"
        if normalized_reason == "auto_continue":
            resume_source = str(snapshot.get("last_resume_source") or "").strip()
            if resume_source.startswith("auto:daemon-recovery"):
                return "recovering"
            continuation_policy = str(snapshot.get("continuation_policy") or "auto").strip().lower() or "auto"
            if continuation_policy == "when_external_progress":
                return "monitoring"
            if continuation_policy in {"wait_for_user_or_resume", "none"}:
                return "parked"
            return "stage_execution"
        turn_intent = DaemonApp._turn_intent_for(latest_user_message, turn_reason=turn_reason)
        if turn_intent == "answer_user_question_first":
            return "answering"
        if turn_intent == "execute_user_command_first":
            return "command_execution"
        return "stage_execution"

    @staticmethod
    def _continuation_anchor_for(snapshot: dict) -> str:
        available_stage_skills = current_standard_skills(repo_root())
        continuation_anchor = str(snapshot.get("continuation_anchor") or "").strip()
        if continuation_anchor in available_stage_skills:
            return continuation_anchor
        active_anchor = str(snapshot.get("active_anchor") or "").strip()
        return active_anchor if active_anchor in available_stage_skills else "decision"

    @staticmethod
    def _workspace_mode_for(snapshot: dict) -> str:
        value = str(snapshot.get("workspace_mode") or "").strip().lower()
        if value in {"copilot", "autonomous"}:
            return value
        startup_contract = snapshot.get("startup_contract")
        if isinstance(startup_contract, dict):
            value = str(startup_contract.get("workspace_mode") or "").strip().lower()
            if value in {"copilot", "autonomous"}:
                return value
        return "autonomous"

    def _resolve_continuation_policy(self, snapshot: dict, *, current_policy: str) -> tuple[str, str]:
        normalized = str(current_policy or "auto").strip().lower() or "auto"
        if normalized != "auto":
            return normalized, str(snapshot.get("continuation_reason") or "").strip() or "explicit_continuation_policy"
        if self._has_external_progress(snapshot):
            return "when_external_progress", "background_external_progress_active"
        if self._workspace_mode_for(snapshot) == "copilot":
            return "wait_for_user_or_resume", "copilot_mode"
        return "auto", "autonomous_prepare_or_launch_long_run"

    @staticmethod
    def _auto_continue_delay_for_policy(policy: str) -> float:
        normalized = str(policy or "").strip().lower() or "auto"
        if normalized == "when_external_progress":
            return _AUTO_CONTINUE_DELAY_SECONDS
        return _AUTO_CONTINUE_ACTIVE_WORK_DELAY_SECONDS

    @staticmethod
    def _turn_skill_stage_gate(snapshot: dict, candidate_skill: str) -> str:
        skill = str(candidate_skill or "").strip()
        baseline_gate = str(snapshot.get("baseline_gate") or "pending").strip().lower() or "pending"
        startup_contract = snapshot.get("startup_contract") if isinstance(snapshot.get("startup_contract"), dict) else {}
        raw_need_research_paper = startup_contract.get("need_research_paper")
        need_research_paper = raw_need_research_paper if isinstance(raw_need_research_paper, bool) else True
        active_idea_id = str(snapshot.get("active_idea_id") or "").strip()

        if (
            baseline_gate == "pending"
            and skill in {"idea", "optimize", "experiment", "analysis-campaign", "write", "review", "rebuttal", "finalize"}
        ):
            return "baseline"

        if skill == "experiment" and not active_idea_id:
            return "idea" if need_research_paper else "optimize"

        return skill

    @staticmethod
    def _direct_user_turn_skill(snapshot: dict) -> str:
        available_stage_skills = current_standard_skills(repo_root())
        workspace_mode = DaemonApp._workspace_mode_for(snapshot)
        has_explicit_baseline_context = bool(
            isinstance(snapshot.get("confirmed_baseline_ref"), dict)
            or isinstance(snapshot.get("requested_baseline_ref"), dict)
            or str(snapshot.get("active_baseline_id") or "").strip()
        )
        for candidate in (
            str(snapshot.get("active_anchor") or "").strip(),
            str(snapshot.get("continuation_anchor") or "").strip(),
        ):
            if candidate in available_stage_skills and candidate != "decision":
                if workspace_mode == "copilot" and candidate == "baseline" and not has_explicit_baseline_context:
                    continue
                return DaemonApp._turn_skill_stage_gate(snapshot, candidate)
        if workspace_mode == "copilot" and "scout" in available_stage_skills:
            fallback = "scout"
        else:
            fallback = "baseline" if "baseline" in available_stage_skills else "scout"
        return DaemonApp._turn_skill_stage_gate(snapshot, fallback)

    @staticmethod
    def _turn_skill_for(
        snapshot: dict,
        latest_user_message: dict | None,
        *,
        turn_reason: str = "user_message",
        turn_mode: str = "stage_execution",
    ) -> str:
        available_stage_skills = current_standard_skills(repo_root())
        workspace_mode = DaemonApp._workspace_mode_for(snapshot)

        reply_target = str((latest_user_message or {}).get("reply_to_interaction_id") or "").strip()
        if reply_target:
            for item in (snapshot.get("active_interactions") or []):
                candidate_ids = {
                    str(item.get("interaction_id") or "").strip(),
                    str(item.get("artifact_id") or "").strip(),
                }
                if reply_target in candidate_ids and (
                    str(item.get("status") or "") == "waiting"
                    or str(item.get("reply_mode") or "") == "blocking"
                    or str(item.get("kind") or "") == "decision_request"
                ):
                    return "decision"
            for item in (snapshot.get("recent_reply_threads") or []):
                candidate_ids = {
                    str(item.get("interaction_id") or "").strip(),
                    str(item.get("artifact_id") or "").strip(),
                }
                if reply_target not in candidate_ids:
                    continue
                if (
                    str(item.get("reply_mode") or "") == "blocking"
                    or str(item.get("kind") or "") == "decision_request"
                ):
                    return "decision"
                if str(item.get("reply_mode") or "") == "threaded":
                    if workspace_mode == "copilot" or turn_mode in {"answering", "command_execution"}:
                        return DaemonApp._direct_user_turn_skill(snapshot)
                    return DaemonApp._turn_skill_stage_gate(
                        snapshot,
                        DaemonApp._continuation_anchor_for(snapshot),
                    )
        if turn_mode == "recovering":
            return "decision"
        if workspace_mode == "copilot" and latest_user_message is not None:
            return DaemonApp._direct_user_turn_skill(snapshot)
        if turn_mode in {"answering", "command_execution"}:
            return DaemonApp._direct_user_turn_skill(snapshot)
        if str(turn_reason or "").strip() == "auto_continue" or latest_user_message is None:
            return DaemonApp._turn_skill_stage_gate(
                snapshot,
                DaemonApp._continuation_anchor_for(snapshot),
            )
        continuation_policy = str(snapshot.get("continuation_policy") or "auto").strip().lower() or "auto"
        if continuation_policy == "wait_for_user_or_resume":
            return DaemonApp._turn_skill_stage_gate(
                snapshot,
                DaemonApp._continuation_anchor_for(snapshot),
            )
        active_anchor = str(snapshot.get("active_anchor") or "").strip()
        return DaemonApp._turn_skill_stage_gate(
            snapshot,
            active_anchor if active_anchor in available_stage_skills else "decision",
        )

    def _latest_user_message(self, quest_id: str) -> dict | None:
        for item in reversed(self.quest_service.history(quest_id, limit=200)):
            if str(item.get("role") or "") == "user":
                return item
        return None

    def _latest_actionable_user_message(self, quest_id: str, *, turn_reason: str) -> dict | None:
        normalized_reason = str(turn_reason or "").strip() or "user_message"
        if normalized_reason in {"user_message", "queued_user_messages"}:
            pending_message = self.quest_service.latest_pending_user_message(quest_id)
            if pending_message is not None:
                return pending_message
        return self._latest_user_message(quest_id)

    @staticmethod
    def _runner_binary_issue(runner_name: str, runner: object) -> str | None:
        binary = getattr(runner, "binary", None)
        if not isinstance(binary, str) or not binary.strip():
            return None
        candidate = binary.strip()
        if os.sep in candidate or candidate.startswith("."):
            return None if Path(candidate).expanduser().exists() else f"Runner `{runner_name}` binary was not found at `{candidate}`."
        return None if which(candidate) else f"Runner `{runner_name}` binary `{candidate}` is not on PATH."

    @staticmethod
    def _trim_text(value: object, *, limit: int = 320) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            text = value.strip()
        else:
            try:
                text = json.dumps(value, ensure_ascii=False)
            except TypeError:
                text = str(value)
        if len(text) <= limit:
            return text
        return text[: limit - 1].rstrip() + "…"

    @staticmethod
    def _coerce_positive_int(value: object, default: int) -> int:
        try:
            resolved = int(value)
        except (TypeError, ValueError):
            return default
        return resolved if resolved > 0 else default

    @staticmethod
    def _coerce_nonnegative_float(value: object, default: float) -> float:
        try:
            resolved = float(value)
        except (TypeError, ValueError):
            return default
        return resolved if resolved >= 0 else default

    @staticmethod
    def _float_matches(left: float, right: float) -> bool:
        return abs(left - right) < 1e-9

    def _runner_retry_policy(self, runner_name: str, runner_cfg: dict[str, Any]) -> dict[str, Any]:
        enabled = bool(runner_cfg.get("retry_on_failure", True))
        max_attempts = min(
            CODEX_RETRY_DEFAULT_MAX_ATTEMPTS,
            self._coerce_positive_int(runner_cfg.get("retry_max_attempts", CODEX_RETRY_DEFAULT_MAX_ATTEMPTS), CODEX_RETRY_DEFAULT_MAX_ATTEMPTS),
        )
        initial_backoff = self._coerce_nonnegative_float(
            runner_cfg.get("retry_initial_backoff_sec", CODEX_RETRY_DEFAULT_INITIAL_BACKOFF_SEC),
            CODEX_RETRY_DEFAULT_INITIAL_BACKOFF_SEC,
        )
        multiplier = max(
            1.0,
            self._coerce_nonnegative_float(
                runner_cfg.get("retry_backoff_multiplier", CODEX_RETRY_DEFAULT_BACKOFF_MULTIPLIER),
                CODEX_RETRY_DEFAULT_BACKOFF_MULTIPLIER,
            ),
        )
        max_backoff = max(
            initial_backoff,
            self._coerce_nonnegative_float(
                runner_cfg.get("retry_max_backoff_sec", CODEX_RETRY_DEFAULT_MAX_BACKOFF_SEC),
                CODEX_RETRY_DEFAULT_MAX_BACKOFF_SEC,
            ),
        )
        if (
            runner_name == "codex"
            and self._float_matches(initial_backoff, LEGACY_CODEX_RETRY_INITIAL_BACKOFF_SEC)
            and self._float_matches(multiplier, LEGACY_CODEX_RETRY_BACKOFF_MULTIPLIER)
            and self._float_matches(max_backoff, LEGACY_CODEX_RETRY_MAX_BACKOFF_SEC)
        ):
            initial_backoff = CODEX_RETRY_DEFAULT_INITIAL_BACKOFF_SEC
            multiplier = CODEX_RETRY_DEFAULT_BACKOFF_MULTIPLIER
            max_backoff = CODEX_RETRY_DEFAULT_MAX_BACKOFF_SEC
        if (
            runner_name == "codex"
            and max_attempts == PREVIOUS_CODEX_RETRY_DEFAULT_MAX_ATTEMPTS
            and self._float_matches(initial_backoff, CODEX_RETRY_DEFAULT_INITIAL_BACKOFF_SEC)
            and self._float_matches(multiplier, CODEX_RETRY_DEFAULT_BACKOFF_MULTIPLIER)
            and self._float_matches(max_backoff, CODEX_RETRY_DEFAULT_MAX_BACKOFF_SEC)
        ):
            max_attempts = CODEX_RETRY_DEFAULT_MAX_ATTEMPTS
        return {
            "enabled": enabled,
            "max_attempts": max_attempts,
            "initial_backoff_sec": initial_backoff,
            "backoff_multiplier": multiplier,
            "max_backoff_sec": max_backoff,
        }

    def _turn_stop_requested(self, quest_id: str) -> bool:
        with self._turn_lock:
            state = dict(self._turn_state.get(quest_id) or {})
        if state.get("stop_requested"):
            return True
        snapshot = self.quest_service.snapshot(quest_id)
        return str(snapshot.get("runtime_status") or snapshot.get("status") or "").strip() in {"paused", "stopped"}

    def _retry_delay_seconds(self, retry_policy: dict[str, Any], *, attempt_index: int) -> float:
        if attempt_index <= 1:
            return 0.0
        initial_backoff = float(retry_policy.get("initial_backoff_sec") or 0.0)
        multiplier = float(retry_policy.get("backoff_multiplier") or 2.0)
        max_backoff = float(retry_policy.get("max_backoff_sec") or initial_backoff or 0.0)
        delay = initial_backoff * pow(multiplier, max(0, attempt_index - 2))
        return max(0.0, min(delay, max_backoff))

    @staticmethod
    def _retry_next_timestamp(delay_seconds: float) -> str:
        if delay_seconds <= 0:
            return utc_now()
        return (datetime.now(UTC) + timedelta(seconds=delay_seconds)).replace(microsecond=0).isoformat()

    def _wait_for_retry_delay(self, quest_id: str, delay_seconds: float) -> bool:
        if delay_seconds <= 0:
            return not self._turn_stop_requested(quest_id)
        deadline = time.monotonic() + delay_seconds
        while time.monotonic() < deadline:
            if self._turn_stop_requested(quest_id):
                return False
            time.sleep(min(0.1, max(0.01, deadline - time.monotonic())))
        return not self._turn_stop_requested(quest_id)

    def _append_retry_event(
        self,
        quest_id: str,
        *,
        event_type: str,
        runner_name: str,
        run_id: str,
        turn_id: str,
        skill_id: str,
        model: str,
        attempt_index: int,
        max_attempts: int,
        summary: str,
        failure_summary: str | None = None,
        backoff_seconds: float | None = None,
        next_attempt_index: int | None = None,
        previous_run_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "event_id": generate_id("evt"),
            "type": event_type,
            "quest_id": quest_id,
            "turn_id": turn_id,
            "run_id": run_id,
            "source": runner_name,
            "skill_id": skill_id,
            "model": model,
            "attempt_index": attempt_index,
            "max_attempts": max_attempts,
            "summary": summary,
            "created_at": utc_now(),
        }
        if failure_summary:
            payload["failure_summary"] = failure_summary
        if backoff_seconds is not None:
            payload["backoff_seconds"] = backoff_seconds
        if next_attempt_index is not None:
            payload["next_attempt_index"] = next_attempt_index
        if previous_run_id:
            payload["previous_run_id"] = previous_run_id
        append_jsonl(self.home / "quests" / quest_id / ".ds" / "events.jsonl", payload)
        self.logger.log(
            "warning" if "scheduled" in event_type or "exhausted" in event_type else "info",
            event_type,
            quest_id=quest_id,
            run_id=run_id,
            turn_id=turn_id,
            attempt_index=attempt_index,
            max_attempts=max_attempts,
            failure_summary=failure_summary,
            backoff_seconds=backoff_seconds,
            next_attempt_index=next_attempt_index,
            previous_run_id=previous_run_id,
        )
        return payload

    def _build_retry_context(
        self,
        *,
        quest_id: str,
        failed_run_id: str,
        turn_id: str,
        attempt_index: int,
        max_attempts: int,
        failure_kind: str,
        failure_summary: str,
        previous_exit_code: int | None,
        previous_output_text: str,
        stderr_text: str,
    ) -> dict[str, Any]:
        snapshot = self.quest_service.snapshot(quest_id)
        quest_root = Path(snapshot["quest_root"])
        workspace_root = Path(str(snapshot.get("current_workspace_root") or snapshot.get("quest_root") or quest_root))
        run_events_window: deque[dict[str, Any]] = deque(maxlen=120)
        for event in iter_jsonl(quest_root / ".ds" / "events.jsonl"):
            if str(event.get("run_id") or "").strip() != failed_run_id:
                continue
            run_events_window.append(event)
        run_events = list(run_events_window)

        recent_messages: list[str] = []
        tool_progress: list[dict[str, str]] = []
        seen_messages: set[str] = set()
        for event in run_events:
            event_type = str(event.get("type") or "").strip()
            if event_type in {"runner.delta", "runner.agent_message", "runner.reasoning"}:
                text = self._trim_text(event.get("text"), limit=280)
                if text and text not in seen_messages:
                    recent_messages.append(text)
                    seen_messages.add(text)
                continue
            if event_type not in {"runner.tool_call", "runner.tool_result"}:
                continue
            tool_progress.append(
                {
                    "tool_name": str(event.get("tool_name") or "tool").strip() or "tool",
                    "status": str(event.get("status") or "").strip(),
                    "args": self._trim_text(event.get("args"), limit=220),
                    "output": self._trim_text(event.get("output"), limit=220),
                }
            )

        git_status_lines: list[str] = []
        try:
            git_status = run_command(["git", "status", "--short"], cwd=workspace_root, check=False)
            git_status_lines = [
                line.strip()
                for line in str(git_status.stdout or git_status.stderr or "").splitlines()
                if line.strip()
            ][:12]
        except Exception:
            git_status_lines = []

        bash_sessions = self.bash_exec_service.list_sessions(quest_root, limit=3)
        bash_session_summaries = [
            {
                "bash_id": str(item.get("bash_id") or item.get("id") or "").strip(),
                "status": str(item.get("status") or "").strip(),
                "command": self._trim_text(item.get("command"), limit=180),
            }
            for item in bash_sessions[:3]
        ]

        recent_artifacts: list[str] = []
        for item in (snapshot.get("recent_artifacts") or [])[-3:]:
            if not isinstance(item, dict):
                continue
            payload = item.get("payload") or {}
            label = (
                str((payload or {}).get("artifact_id") or "").strip()
                or Path(str(item.get("path") or "artifact")).stem
            )
            summary = self._trim_text(
                (payload or {}).get("summary") or (payload or {}).get("reason") or (payload or {}).get("guidance"),
                limit=220,
            )
            recent_artifacts.append(
                " -> ".join(part for part in (str(item.get("kind") or "artifact").strip(), label, summary) if part)
            )

        return {
            "turn_id": turn_id,
            "attempt_index": attempt_index,
            "max_attempts": max_attempts,
            "previous_run_id": failed_run_id,
            "previous_exit_code": previous_exit_code,
            "failure_kind": failure_kind,
            "failure_summary": failure_summary,
            "previous_output_text": self._trim_text(previous_output_text, limit=1800),
            "stderr_tail": self._trim_text(stderr_text, limit=1800),
            "recent_messages": recent_messages[-6:],
            "tool_progress": tool_progress[-8:],
            "workspace_summary": {
                "branch": str(snapshot.get("branch") or "").strip(),
                "git_status": git_status_lines,
                "bash_sessions": bash_session_summaries,
            },
            "recent_artifacts": [item for item in recent_artifacts if item],
        }

    def _record_turn_error(
        self,
        *,
        quest_id: str,
        runner_name: str,
        run_id: str,
        skill_id: str,
        model: str,
        summary: str,
        display_status: str = "error",
        retry_state: dict[str, Any] | None = None,
        diagnosis_code: str | None = None,
        guidance: list[str] | None = None,
    ) -> None:
        quest_root = self.home / "quests" / quest_id
        normalized_guidance = [str(line) for line in (guidance or []) if str(line).strip()]
        append_jsonl(
            quest_root / ".ds" / "events.jsonl",
            {
                "event_id": generate_id("evt"),
                "type": "runner.turn_error",
                "quest_id": quest_id,
                "run_id": run_id,
                "source": runner_name,
                "skill_id": skill_id,
                "model": model,
                "summary": summary,
                "diagnosis_code": str(diagnosis_code or "").strip() or None,
                "guidance": normalized_guidance,
                "created_at": utc_now(),
            },
        )
        self.quest_service.update_runtime_state(
            quest_root=quest_root,
            status="active",
            display_status=display_status,
            active_run_id=None,
            retry_state=retry_state,
        )
        runner_label = self._connector_runner_label(runner_name)
        user_notice = self._polite_copy(
            zh=f"DeepScientist 意外停止运行，请检查你所绑定的{runner_label}是否能够顺利连接。",
            en=f"DeepScientist stopped unexpectedly. Please check whether the bound {runner_label} can connect normally.",
        )
        notice_message = "\n".join([user_notice, "", summary]).strip()
        if normalized_guidance:
            notice_message = "\n".join(
                [
                    user_notice,
                    "",
                    summary,
                    "",
                    "Suggested fix:",
                    *[f"- {line}" for line in normalized_guidance[:3]],
                ]
            ).strip()
        self.logger.log(
            "error",
            "runner.turn_error",
            quest_id=quest_id,
            run_id=run_id,
            runner=runner_name,
            skill_id=skill_id,
            model=model,
            summary=summary,
        )
        self._relay_quest_message_to_bound_connectors(
            quest_id,
            message=notice_message,
            kind="error",
            response_phase="final",
            importance="warning",
            attachments=[
                {
                    "kind": "runner_error",
                    "run_id": run_id,
                    "skill_id": skill_id,
                    "runner": runner_name,
                    "model": model,
                    "diagnosis_code": str(diagnosis_code or "").strip() or None,
                }
            ],
        )

    @staticmethod
    def _non_retryable_failure_diagnosis(
        *,
        runner_name: str,
        summary: str,
        stderr_text: str,
        output_text: str,
    ) -> FailureDiagnosis | None:
        diagnosis = diagnose_runner_failure(
            runner_name=runner_name,
            summary=summary,
            stderr_text=stderr_text,
            output_text=output_text,
        )
        if diagnosis is None or diagnosis.retriable:
            return None
        return diagnosis

    def _record_turn_postprocess_warning(
        self,
        *,
        quest_id: str,
        runner_name: str,
        run_id: str,
        skill_id: str,
        model: str,
        stage: str,
        error: Exception,
    ) -> None:
        quest_root = self.home / "quests" / quest_id
        summary = f"Runner post-run stage `{stage}` failed for run `{run_id}`: {error}"
        append_jsonl(
            quest_root / ".ds" / "events.jsonl",
            {
                "event_id": generate_id("evt"),
                "type": "runner.turn_postprocess_warning",
                "quest_id": quest_id,
                "run_id": run_id,
                "source": runner_name,
                "skill_id": skill_id,
                "model": model,
                "stage": stage,
                "summary": summary,
                "created_at": utc_now(),
            },
        )
        self.logger.log(
            "error",
            "runner.turn_postprocess_warning",
            quest_id=quest_id,
            run_id=run_id,
            runner=runner_name,
            skill_id=skill_id,
            model=model,
            stage=stage,
            error=str(error),
        )

    def _ensure_turn_cleanup(self, quest_id: str, *, run_id: str, turn_reason: str) -> None:
        snapshot = self.quest_service.snapshot(quest_id)
        if str(snapshot.get("active_run_id") or "").strip() != str(run_id or "").strip():
            return
        try:
            self._normalize_status_after_turn(quest_id, turn_reason=turn_reason)
            return
        except Exception as exc:
            current_status = str(snapshot.get("status") or snapshot.get("display_status") or "active").strip() or "active"
            normalized_status = "active" if current_status == "running" else current_status
            self.quest_service.mark_turn_finished(quest_id, status=normalized_status)
            quest_root = self.quest_service._quest_root(quest_id)
            append_jsonl(
                quest_root / ".ds" / "events.jsonl",
                {
                    "event_id": generate_id("evt"),
                    "type": "runner.turn_cleanup_recovered",
                    "quest_id": quest_id,
                    "run_id": run_id,
                    "status": normalized_status,
                    "summary": f"Recovered turn cleanup after `_normalize_status_after_turn` failed: {exc}",
                    "created_at": utc_now(),
                },
            )
            self.logger.log(
                "error",
                "runner.turn_cleanup_recovered",
                quest_id=quest_id,
                run_id=run_id,
                status=normalized_status,
                error=str(exc),
            )

    def _normalize_status_after_turn(self, quest_id: str, *, turn_reason: str = "user_message") -> None:
        with self._turn_lock:
            if bool((self._turn_state.get(quest_id) or {}).get("stop_requested")):
                return
        snapshot = self.quest_service.snapshot(quest_id)
        current_status = str(snapshot.get("status") or snapshot.get("display_status") or "active").strip() or "active"
        normalized_status = "active" if current_status == "running" else current_status
        snapshot = self.quest_service.mark_turn_finished(quest_id, status=normalized_status)
        runtime_updates: dict[str, Any] = {}
        current_fingerprint = self._stage_state_fingerprint(snapshot)
        previous_fingerprint = str(snapshot.get("last_stage_fingerprint") or "").strip() or None
        same_fingerprint_count = int(snapshot.get("same_fingerprint_auto_turn_count") or 0)
        if str(turn_reason or "").strip() == "auto_continue":
            same_fingerprint_count = same_fingerprint_count + 1 if previous_fingerprint == current_fingerprint else 1
        else:
            same_fingerprint_count = 0
        runtime_updates.update(
            {
                "last_stage_fingerprint": current_fingerprint,
                "last_stage_fingerprint_at": utc_now(),
                "same_fingerprint_auto_turn_count": same_fingerprint_count,
            }
        )
        if (
            str(turn_reason or "").strip() == "auto_continue"
            and str(snapshot.get("active_anchor") or "").strip() == "finalize"
            and same_fingerprint_count >= 2
            and int(snapshot.get("pending_user_message_count") or 0) == 0
        ):
            runtime_updates.update(
                {
                    "continuation_policy": "wait_for_user_or_resume",
                    "continuation_anchor": "decision",
                    "continuation_reason": "unchanged_finalize_state",
                    "continuation_updated_at": utc_now(),
                }
            )
            self.quest_service.update_runtime_state(
                quest_root=self.quest_service._quest_root(quest_id),
                **runtime_updates,
            )
            snapshot = self.quest_service.snapshot(quest_id)
        else:
            self.quest_service.update_runtime_state(
                quest_root=self.quest_service._quest_root(quest_id),
                **runtime_updates,
            )
            snapshot = self.quest_service.snapshot(quest_id)
        status = str(snapshot.get("status") or "")
        if status in {"stopped", "paused", "completed", "error"}:
            return
        if status == "waiting_for_user":
            if snapshot.get("waiting_interaction_id"):
                return
            if int(snapshot.get("pending_user_message_count") or 0) > 0:
                self.schedule_turn(quest_id, reason="queued_user_messages")
            else:
                continuation_policy = str(snapshot.get("continuation_policy") or "auto").strip().lower() or "auto"
                resolved_external_progress = False
                if continuation_policy == "auto":
                    continuation_policy, continuation_reason = self._resolve_continuation_policy(
                        snapshot,
                        current_policy=continuation_policy,
                    )
                    resolved_external_progress = continuation_policy == "when_external_progress"
                    self.quest_service.update_runtime_state(
                        quest_root=self.quest_service._quest_root(quest_id),
                        continuation_policy=continuation_policy,
                        continuation_reason=continuation_reason,
                        continuation_updated_at=utc_now(),
                    )
                    snapshot = self.quest_service.snapshot(quest_id)
                if continuation_policy not in {"wait_for_user_or_resume", "none"}:
                    self._schedule_turn_later(
                        quest_id,
                        reason="auto_continue",
                        delay_seconds=self._auto_continue_delay_for_policy(continuation_policy),
                    )
            return
        if int(snapshot.get("pending_user_message_count") or 0) > 0:
            self.schedule_turn(quest_id, reason="queued_user_messages")
            return
        continuation_policy = str(snapshot.get("continuation_policy") or "auto").strip().lower() or "auto"
        resolved_external_progress = False
        if continuation_policy == "auto":
            continuation_policy, continuation_reason = self._resolve_continuation_policy(
                snapshot,
                current_policy=continuation_policy,
            )
            resolved_external_progress = continuation_policy == "when_external_progress"
            self.quest_service.update_runtime_state(
                quest_root=self.quest_service._quest_root(quest_id),
                continuation_policy=continuation_policy,
                continuation_reason=continuation_reason,
                continuation_updated_at=utc_now(),
            )
            snapshot = self.quest_service.snapshot(quest_id)
        if continuation_policy == "none":
            return
        if continuation_policy == "wait_for_user_or_resume":
            return
        if continuation_policy == "when_external_progress":
            if not resolved_external_progress and not self._has_external_progress(snapshot):
                next_policy = "wait_for_user_or_resume" if self._workspace_mode_for(snapshot) == "copilot" else "auto"
                next_reason = "external_progress_finished" if next_policy == "wait_for_user_or_resume" else "external_progress_finished_continue_autonomous"
                self.quest_service.update_runtime_state(
                    quest_root=self.quest_service._quest_root(quest_id),
                    continuation_policy=next_policy,
                    continuation_reason=next_reason,
                    continuation_updated_at=utc_now(),
                )
                if next_policy != "wait_for_user_or_resume":
                    self._schedule_turn_later(
                        quest_id,
                        reason="auto_continue",
                        delay_seconds=self._auto_continue_delay_for_policy(next_policy),
                    )
                return
        self._schedule_turn_later(
            quest_id,
            reason="auto_continue",
            delay_seconds=self._auto_continue_delay_for_policy(continuation_policy),
        )

    def _schedule_turn_later(self, quest_id: str, *, reason: str, delay_seconds: float) -> None:
        def _delayed() -> None:
            time.sleep(max(0.0, delay_seconds))
            if self._turn_stop_requested(quest_id):
                return
            snapshot = self.quest_service.snapshot(quest_id)
            status = str(snapshot.get("status") or snapshot.get("runtime_status") or "").strip().lower()
            if status in {"completed", "paused", "stopped", "error", "waiting_for_user"}:
                return
            continuation_policy = str(snapshot.get("continuation_policy") or "auto").strip().lower() or "auto"
            resolved_external_progress = False
            if continuation_policy == "auto":
                continuation_policy, continuation_reason = self._resolve_continuation_policy(
                    snapshot,
                    current_policy=continuation_policy,
                )
                resolved_external_progress = continuation_policy == "when_external_progress"
                self.quest_service.update_runtime_state(
                    quest_root=self.quest_service._quest_root(quest_id),
                    continuation_policy=continuation_policy,
                    continuation_reason=continuation_reason,
                    continuation_updated_at=utc_now(),
                )
                snapshot = self.quest_service.snapshot(quest_id)
            if continuation_policy in {"none", "wait_for_user_or_resume"}:
                return
            if continuation_policy == "when_external_progress":
                if not resolved_external_progress and not self._has_external_progress(snapshot):
                    next_policy = "wait_for_user_or_resume" if self._workspace_mode_for(snapshot) == "copilot" else "auto"
                    next_reason = "external_progress_finished" if next_policy == "wait_for_user_or_resume" else "external_progress_finished_continue_autonomous"
                    self.quest_service.update_runtime_state(
                        quest_root=self.quest_service._quest_root(quest_id),
                        continuation_policy=next_policy,
                        continuation_reason=next_reason,
                        continuation_updated_at=utc_now(),
                    )
                    return
            self.schedule_turn(quest_id, reason=reason)

        threading.Thread(
            target=_delayed,
            daemon=True,
            name=f"deepscientist-turn-delay-{quest_id}",
        ).start()

    def _has_external_progress(self, snapshot: dict) -> bool:
        if bool(snapshot.get("active_run_id")):
            return True
        quest_id = str(snapshot.get("quest_id") or "").strip()
        if not quest_id:
            return False
        counts = snapshot.get("counts") if isinstance(snapshot.get("counts"), dict) else {}
        try:
            quest_root = self.quest_service._quest_root(quest_id)
        except FileNotFoundError:
            return int(counts.get("bash_running_count") or 0) > 0
        try:
            sessions = self.bash_exec_service.list_sessions(quest_root, limit=200)
            if any(str(item.get("status") or "").strip().lower() == "running" for item in sessions if isinstance(item, dict)):
                return True
        except Exception:
            pass
        return int(counts.get("bash_running_count") or 0) > 0

    def _relay_quest_message_to_bound_connectors(
        self,
        quest_id: str,
        *,
        message: str,
        kind: str = "assistant",
        response_phase: str | None = "final",
        importance: str | None = "normal",
        attachments: list[dict[str, object]] | None = None,
    ) -> list[str]:
        text = str(message or "").strip()
        if not text:
            return []
        quest_root = self.quest_service._quest_root(quest_id)
        connectors = self.artifact_service._connectors_config()
        targets = self.artifact_service._select_delivery_targets(
            self.artifact_service._bound_conversations(quest_root),
            connectors=connectors,
        )
        delivered: list[str] = []
        for target in targets:
            channel_name = self.artifact_service._normalize_channel_name(target)
            payload = {
                "quest_root": str(quest_root),
                "quest_id": quest_id,
                "conversation_id": target,
                "kind": kind,
                "message": text,
                "response_phase": response_phase,
                "importance": importance,
                "attachments": attachments or [],
            }
            if self.artifact_service._send_to_channel(channel_name, payload, connectors=connectors):
                delivered.append(target)
        return delivered

    def request_shutdown(self, *, source: str = "local-admin") -> dict:
        if self._shutdown_requested.is_set():
            return {
                "ok": True,
                "message": "DeepScientist daemon shutdown is already in progress.",
                "source": source,
            }
        interrupted_quests: list[str] = []
        for snapshot in self.quest_service.list_quests():
            quest_id = str(snapshot.get("quest_id") or "").strip()
            if not quest_id:
                continue
            if snapshot.get("status") != "running" and not snapshot.get("active_run_id"):
                continue
            result = self.stop_quest(quest_id, source=source)
            if result.get("ok"):
                interrupted_quests.append(quest_id)
        self._shutdown_requested.set()
        self._stop_background_connectors()
        self._stop_terminal_attach_server()
        self.admin_service.system_monitor.stop()
        self.bash_exec_service.shutdown()
        self.logger.log(
            "info",
            "daemon.shutdown_requested",
            source=source,
            interrupted_quests=interrupted_quests,
        )

        server = self._server

        def _shutdown_server() -> None:
            time.sleep(0.05)
            if server is not None:
                try:
                    server.shutdown()
                except Exception:
                    return

        threading.Thread(
            target=_shutdown_server,
            daemon=True,
            name="deepscientist-daemon-shutdown",
        ).start()
        return {
            "ok": True,
            "message": "DeepScientist daemon shutdown requested.",
            "source": source,
            "interrupted_quests": interrupted_quests,
        }

    def handle_qq_inbound(self, body: dict) -> dict:
        return self.handle_connector_inbound("qq", body)

    def list_qq_bindings(self) -> list[dict]:
        return self._qq_channel().list_bindings()

    def list_connector_bindings(self, connector_name: str) -> list[dict]:
        channel = self._channel_with_bindings(connector_name)
        return channel.list_bindings()

    def start_weixin_login_qr(self, *, force: bool = False) -> dict[str, Any]:
        connectors = self.config_manager.load_named_normalized("connectors")
        weixin = connectors.get("weixin") if isinstance(connectors.get("weixin"), dict) else {}
        base_url = normalize_weixin_base_url(weixin.get("base_url"))
        bot_type = str(weixin.get("bot_type") or DEFAULT_WEIXIN_BOT_TYPE).strip() or DEFAULT_WEIXIN_BOT_TYPE
        route_tag = str(weixin.get("route_tag") or "").strip() or None
        qr_payload = fetch_weixin_qrcode(base_url=base_url, bot_type=bot_type, route_tag=route_tag)
        qrcode_token = str(qr_payload.get("qrcode") or "").strip()
        qrcode_content = str(qr_payload.get("qrcode_img_content") or qr_payload.get("url") or "").strip()
        if not qrcode_token or not qrcode_content:
            raise RuntimeError("Weixin QR login did not return a valid qrcode token or renderable content.")
        session_key = generate_id("wxqr")
        self._weixin_login_sessions[session_key] = {
            "session_key": session_key,
            "qrcode": qrcode_token,
            "qrcode_content": qrcode_content,
            "base_url": base_url,
            "bot_type": bot_type,
            "route_tag": route_tag,
            "started_at": time.time(),
            "refresh_count": 0,
            "force": bool(force),
        }
        return {
            "ok": True,
            "session_key": session_key,
            "qrcode_content": qrcode_content,
            "qrcode_url": qrcode_content,
            "message": "Weixin QR code is ready. Scan it with WeChat to connect DeepScientist.",
        }

    def wait_weixin_login_qr(self, *, session_key: str, timeout_ms: int = 1_500) -> dict[str, Any]:
        normalized_session_key = str(session_key or "").strip()
        if not normalized_session_key:
            return {
                "ok": False,
                "connected": False,
                "message": "Weixin QR session key is required.",
            }
        session = self._weixin_login_sessions.get(normalized_session_key)
        if not isinstance(session, dict):
            return {
                "ok": False,
                "connected": False,
                "message": "Weixin QR session was not found. Start a new login first.",
            }

        deadline = time.time() + max(int(timeout_ms or 1_500), 500) / 1000.0
        while time.time() < deadline:
            remaining = max(deadline - time.time(), 1.0)
            try:
                status = poll_weixin_qrcode_status(
                    base_url=str(session.get("base_url") or ""),
                    qrcode=str(session.get("qrcode") or ""),
                    route_tag=str(session.get("route_tag") or "").strip() or None,
                    timeout=min(remaining, 35.0),
                )
            except Exception as exc:
                message = str(exc or "").strip().lower()
                if isinstance(exc, TimeoutError) or "timed out" in message or "timeout" in message:
                    break
                raise
            state = str(status.get("status") or "wait").strip().lower() or "wait"
            session["status"] = state
            if state == "confirmed":
                return self._persist_weixin_login_session(session, status)
            if state == "expired":
                refreshed = self._refresh_weixin_login_session(session)
                return {
                    "ok": True,
                    "connected": False,
                    "status": "expired",
                    "session_key": normalized_session_key,
                    "qrcode_content": refreshed.get("qrcode_content"),
                    "qrcode_url": refreshed.get("qrcode_content"),
                    "message": "Weixin QR code expired and was refreshed automatically.",
                }
            if state in {"scaned", "scanned"}:
                return {
                    "ok": True,
                    "connected": False,
                    "status": "scaned",
                    "session_key": normalized_session_key,
                    "qrcode_content": str(session.get("qrcode_content") or "").strip() or None,
                    "qrcode_url": str(session.get("qrcode_content") or "").strip() or None,
                    "message": "QR code scanned. Confirm the login inside WeChat.",
                }
        return {
            "ok": True,
            "connected": False,
            "status": str(session.get("status") or "wait").strip() or "wait",
            "session_key": normalized_session_key,
            "qrcode_content": str(session.get("qrcode_content") or "").strip() or None,
            "qrcode_url": str(session.get("qrcode_content") or "").strip() or None,
            "message": "Waiting for Weixin QR confirmation.",
        }

    def _refresh_weixin_login_session(self, session: dict[str, Any]) -> dict[str, Any]:
        qr_payload = fetch_weixin_qrcode(
            base_url=str(session.get("base_url") or ""),
            bot_type=str(session.get("bot_type") or DEFAULT_WEIXIN_BOT_TYPE),
            route_tag=str(session.get("route_tag") or "").strip() or None,
        )
        session["qrcode"] = str(qr_payload.get("qrcode") or "").strip()
        session["qrcode_content"] = str(qr_payload.get("qrcode_img_content") or qr_payload.get("url") or "").strip()
        session["started_at"] = time.time()
        session["refresh_count"] = int(session.get("refresh_count") or 0) + 1
        return session

    def _persist_weixin_login_session(self, session: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
        bot_token = str(status.get("bot_token") or "").strip()
        account_id = str(status.get("ilink_bot_id") or "").strip()
        login_user_id = str(status.get("ilink_user_id") or "").strip() or None
        if not bot_token or not account_id:
            return {
                "ok": False,
                "connected": False,
                "status": "confirmed",
                "message": "Weixin QR login confirmed, but the platform did not return `bot_token` or `ilink_bot_id`.",
            }
        connectors = self.config_manager.load_named_normalized("connectors")
        weixin = connectors.get("weixin") if isinstance(connectors.get("weixin"), dict) else {}
        weixin.update(
            {
                "enabled": True,
                "transport": "ilink_long_poll",
                "base_url": normalize_weixin_base_url(status.get("baseurl") or session.get("base_url")),
                "cdn_base_url": normalize_weixin_cdn_base_url(weixin.get("cdn_base_url")),
                "bot_type": str(session.get("bot_type") or DEFAULT_WEIXIN_BOT_TYPE),
                "bot_token": bot_token,
                "account_id": account_id,
                "login_user_id": login_user_id,
            }
        )
        connectors["weixin"] = weixin
        save_result = self.config_manager.save_named_payload("connectors", connectors)
        if not bool(save_result.get("ok")):
            self.logger.log(
                "warning",
                "connector.weixin_qr_persist_failed",
                session_key=str(session.get("session_key") or ""),
                account_id=account_id,
                errors=save_result.get("errors") or [],
                warnings=save_result.get("warnings") or [],
            )
            return {
                "ok": False,
                "connected": False,
                "status": "confirmed",
                "errors": save_result.get("errors") or [],
                "warnings": save_result.get("warnings") or [],
                "message": "Weixin login succeeded, but DeepScientist could not persist the connector config.",
            }
        self.reload_connectors_config()
        self._weixin_login_sessions.pop(str(session.get("session_key") or ""), None)
        snapshot = next(
            (item for item in self.list_connector_statuses() if str(item.get("name") or "").strip().lower() == "weixin"),
            None,
        )
        return {
            "ok": True,
            "connected": True,
            "status": "confirmed",
            "account_id": account_id,
            "login_user_id": login_user_id,
            "base_url": str(weixin.get("base_url") or "").strip() or None,
            "snapshot": snapshot,
            "message": "Weixin login succeeded and the connector config was saved.",
        }

    def delete_connector_profile(self, connector_name: str, profile_id: str) -> dict | tuple[int, dict]:
        normalized_connector = str(connector_name or "").strip().lower()
        normalized_profile_id = str(profile_id or "").strip()
        if not normalized_connector:
            return 400, {"ok": False, "message": "Connector name is required."}
        if not normalized_profile_id:
            return 400, {"ok": False, "message": "Profile id is required."}
        if normalized_connector != "qq" and normalized_connector not in PROFILEABLE_CONNECTOR_NAMES:
            return 400, {"ok": False, "message": f"Connector `{normalized_connector}` does not support profile deletion."}

        connectors = self.config_manager.load_named_normalized("connectors")
        connector_config = connectors.get(normalized_connector)
        if not isinstance(connector_config, dict):
            return 404, {"ok": False, "message": f"Unknown connector `{normalized_connector}`."}

        if normalized_connector == "qq":
            profiles = list_qq_profiles(connector_config)
        else:
            profiles = list_connector_profiles(normalized_connector, connector_config)
        if not profiles:
            return 404, {"ok": False, "message": f"Connector `{normalized_connector}` has no configured profiles."}

        remaining_profiles = [
            dict(item)
            for item in profiles
            if str(item.get("profile_id") or "").strip() != normalized_profile_id
        ]
        if len(remaining_profiles) == len(profiles):
            return 404, {
                "ok": False,
                "message": f"Profile `{normalized_profile_id}` was not found under connector `{normalized_connector}`.",
            }

        deleting_last_profile = len(remaining_profiles) == 0
        related_conversations = self._connector_profile_bound_conversations(
            normalized_connector,
            normalized_profile_id,
            include_all_if_single_profile=deleting_last_profile,
        )
        for conversation_id in related_conversations:
            self._unbind_connector_conversation_everywhere(normalized_connector, conversation_id)

        next_connector_config = dict(connector_config)
        next_connector_config["profiles"] = remaining_profiles
        if deleting_last_profile:
            next_connector_config["enabled"] = False
            if normalized_connector == "qq":
                for key in ("app_id", "app_secret", "app_secret_env", "main_chat_id"):
                    next_connector_config[key] = None
            else:
                profile_spec = CONNECTOR_PROFILE_SPECS.get(normalized_connector, {})
                for key in profile_spec.get("profile_fields", ()):
                    if key in {"enabled", "transport", "mode"}:
                        continue
                    next_connector_config[key] = None
        if normalized_connector == "qq":
            connectors[normalized_connector] = normalize_qq_connector_config(next_connector_config)
        else:
            connectors[normalized_connector] = normalize_connector_config(normalized_connector, next_connector_config)
        save_result = self.config_manager.save_named_payload("connectors", connectors)
        if not bool(save_result.get("ok")):
            return 409, {
                "ok": False,
                "message": "Failed to persist connector profile deletion.",
                "errors": save_result.get("errors") or [],
                "warnings": save_result.get("warnings") or [],
            }

        self._cleanup_connector_profile_runtime(
            normalized_connector,
            normalized_profile_id,
            clear_all=deleting_last_profile,
        )
        self.reload_connectors_config()
        snapshot = next(
            (item for item in self.list_connector_statuses() if str(item.get("name") or "").strip().lower() == normalized_connector),
            None,
        )
        return {
            "ok": True,
            "connector": normalized_connector,
            "profile_id": normalized_profile_id,
            "deleted": True,
            "deleted_bound_conversations": related_conversations,
            "remaining_profile_count": len(remaining_profiles),
            "snapshot": snapshot,
        }

    def _connector_profile_bound_conversations(
        self,
        connector_name: str,
        profile_id: str,
        *,
        include_all_if_single_profile: bool = False,
    ) -> list[str]:
        normalized_connector = str(connector_name or "").strip().lower()
        normalized_profile_id = str(profile_id or "").strip()
        if not normalized_connector or not normalized_profile_id:
            return []
        try:
            channel = self._channel_with_bindings(normalized_connector)
        except Exception:
            return []
        conversations: list[str] = []
        seen: set[str] = set()
        for item in channel.list_bindings():
            if not isinstance(item, dict):
                continue
            conversation_id = str(item.get("conversation_id") or "").strip()
            if not conversation_id:
                continue
            item_profile_id = str(item.get("profile_id") or "").strip()
            if not include_all_if_single_profile and item_profile_id != normalized_profile_id:
                continue
            identity = conversation_identity_key(conversation_id)
            if identity in seen:
                continue
            seen.add(identity)
            conversations.append(conversation_id)
        return conversations

    def _unbind_connector_conversation_everywhere(self, connector_name: str, conversation_id: str) -> bool:
        normalized_connector = str(connector_name or "").strip().lower()
        normalized_conversation_id = normalize_conversation_id(conversation_id)
        if not normalized_connector or not normalized_conversation_id:
            return False
        try:
            channel = self._channel_with_bindings(normalized_connector)
        except Exception:
            return False
        bound_quest_id = str(channel.resolve_bound_quest(normalized_conversation_id) or "").strip() or None
        removed = channel.unbind_conversation(
            normalized_conversation_id,
            quest_id=bound_quest_id,
        )
        if bound_quest_id:
            self.sessions.unbind(bound_quest_id, normalized_conversation_id)
            self.quest_service.unbind_source(bound_quest_id, normalized_conversation_id)
        return removed

    def _cleanup_connector_profile_runtime(
        self,
        connector_name: str,
        profile_id: str,
        *,
        clear_all: bool = False,
    ) -> None:
        normalized_connector = str(connector_name or "").strip().lower()
        normalized_profile_id = str(profile_id or "").strip()
        if not normalized_connector or not normalized_profile_id:
            return
        connector_root = self.home / "logs" / "connectors" / normalized_connector
        profile_root = connector_root / "profiles" / normalized_profile_id
        shutil.rmtree(profile_root, ignore_errors=True)

        def matches_profile(payload: object, *, conversation_id: str | None = None) -> bool:
            if clear_all:
                return True
            item = payload if isinstance(payload, dict) else {}
            item_profile_id = str(item.get("profile_id") or "").strip() if isinstance(item, dict) else ""
            if item_profile_id:
                return item_profile_id == normalized_profile_id
            parsed = parse_conversation_id(conversation_id or "")
            return str((parsed or {}).get("profile_id") or "").strip() == normalized_profile_id

        bindings_path = connector_root / "bindings.json"
        bindings_payload = read_json(bindings_path, {"bindings": {}})
        binding_map = bindings_payload.get("bindings")
        if isinstance(binding_map, dict):
            filtered_bindings = {
                key: value
                for key, value in binding_map.items()
                if not matches_profile(value, conversation_id=str(key))
            }
            bindings_payload["bindings"] = filtered_bindings
            write_json(bindings_path, bindings_payload)

        state_path = connector_root / "state.json"
        state_payload = read_json(state_path, {})
        if isinstance(state_payload, dict):
            for key in ("recent_conversations", "known_targets"):
                raw_items = state_payload.get(key)
                if isinstance(raw_items, list):
                    state_payload[key] = [
                        item
                        for item in raw_items
                        if not matches_profile(
                            item,
                            conversation_id=str((item or {}).get("conversation_id") or "") if isinstance(item, dict) else "",
                        )
                    ]
            if clear_all:
                state_payload["last_conversation_id"] = None
            else:
                last_conversation_id = str(state_payload.get("last_conversation_id") or "").strip()
                if last_conversation_id and matches_profile({}, conversation_id=last_conversation_id):
                    state_payload["last_conversation_id"] = None
            write_json(state_path, state_payload)

        if clear_all:
            runtime_path = connector_root / "runtime.json"
            if runtime_path.exists():
                write_json(runtime_path, {})

    def preview_connector_binding_conflicts(
        self,
        requested_bindings: list[dict[str, object]] | None,
        *,
        quest_id: str | None = None,
    ) -> list[dict[str, object]]:
        normalized_bindings = self._normalize_requested_connector_bindings(requested_bindings)
        conflicts: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        for item in normalized_bindings:
            connector_name = str(item.get("connector") or "").strip().lower()
            conversation_id = str(item.get("conversation_id") or "").strip()
            if not connector_name or not conversation_id:
                continue
            for conflict in self._inspect_connector_binding_conflicts(quest_id, conversation_id):
                conflict_quest_id = str(conflict.get("quest_id") or "").strip()
                identity = (connector_name, conflict_quest_id)
                if not conflict_quest_id or identity in seen:
                    continue
                seen.add(identity)
                conflicts.append(
                    {
                        "connector": connector_name,
                        "conversation_id": conversation_id,
                        **conflict,
                    }
                )
        return conflicts

    def _inspect_connector_binding_conflicts(
        self,
        quest_id: str | None,
        conversation_id: str,
    ) -> list[dict[str, object]]:
        normalized = normalize_conversation_id(conversation_id)
        parsed = parse_conversation_id(normalized)
        if parsed is None or str(parsed.get("connector") or "").strip().lower() == "local":
            return []
        connector_name = str(parsed.get("connector") or "").strip().lower()
        if connector_name not in self.channels:
            return []
        channel = self._channel_with_bindings(connector_name)
        conversation_key = conversation_identity_key(normalized)
        titles = self._quest_titles_by_id()
        conflicts: list[dict[str, object]] = []
        existing_bound = channel.resolve_bound_quest(normalized)
        normalized_quest_id = str(quest_id or "").strip() or None
        if existing_bound and existing_bound != normalized_quest_id:
            conflicts.append(
                {
                    "quest_id": existing_bound,
                    "title": titles.get(existing_bound),
                    "reason": "connector_binding",
                }
            )
        for item in self.quest_service.list_quests():
            other_id = str(item.get("quest_id") or "").strip()
            if not other_id or other_id == normalized_quest_id:
                continue
            sources = self.quest_service.binding_sources(other_id)
            if any(conversation_identity_key(source) == conversation_key for source in sources):
                conflicts.append(
                    {
                        "quest_id": other_id,
                        "title": titles.get(other_id),
                        "reason": "quest_binding",
                    }
                )
        deduped_conflicts: list[dict[str, object]] = []
        seen_conflict_ids: set[str] = set()
        for item in conflicts:
            candidate = str(item.get("quest_id") or "").strip()
            if not candidate or candidate in seen_conflict_ids:
                continue
            seen_conflict_ids.add(candidate)
            deduped_conflicts.append(item)
        return deduped_conflicts

    def _unbind_quest_connector_bindings(
        self,
        quest_id: str,
        connector_name: str,
        *,
        preserve: set[str] | None = None,
    ) -> list[str]:
        normalized_connector = str(connector_name or "").strip().lower()
        preserve_keys = {conversation_identity_key(item) for item in (preserve or set()) if item}
        removed: list[str] = []
        if not normalized_connector or normalized_connector == "local":
            return removed
        try:
            channel = self._channel_with_bindings(normalized_connector)
        except Exception:
            return removed
        for item in channel.list_bindings():
            if str(item.get("quest_id") or "").strip() != quest_id:
                continue
            conversation_id = str(item.get("conversation_id") or "").strip()
            if not conversation_id:
                continue
            if preserve_keys and conversation_identity_key(conversation_id) in preserve_keys:
                continue
            if channel.unbind_conversation(conversation_id, quest_id=quest_id):
                removed.append(conversation_id)
                self.sessions.unbind(quest_id, conversation_id)
        for conversation_id in removed:
            self.quest_service.unbind_source(quest_id, conversation_id)
        return removed

    def _apply_conversation_binding(
        self,
        quest_id: str,
        conversation_id: str,
        *,
        force: bool = False,
        clear_scope: str = "connector",
    ) -> dict | tuple[int, dict]:
        quest_root = self.home / "quests" / quest_id
        if not quest_root.joinpath("quest.yaml").exists():
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}
        normalized = normalize_conversation_id(conversation_id)
        parsed = parse_conversation_id(normalized)
        if parsed is None:
            return 400, {"ok": False, "message": f"Invalid connector conversation `{conversation_id}`."}
        connector_name = str(parsed.get("connector") or "").strip().lower()
        if not connector_name or connector_name == "local" or connector_name not in self.channels:
            return 400, {"ok": False, "message": f"Unknown connector `{connector_name}` for conversation `{normalized}`."}
        binding_conversation_id = self._logical_connector_binding_conversation(connector_name, normalized)
        channel = self._channel_with_bindings(connector_name)
        conflicts = self._inspect_connector_binding_conflicts(quest_id, binding_conversation_id)
        if conflicts and not force:
            return 409, {
                "ok": False,
                "conflict": True,
                "message": "Conversation is already bound to another quest.",
                "quest_id": quest_id,
                "connector": connector_name,
                "conversation_id": binding_conversation_id,
                "conflicts": conflicts,
            }
        existing_bound = channel.resolve_bound_quest(binding_conversation_id)
        for item in conflicts:
            other_id = str(item.get("quest_id") or "").strip()
            if other_id and other_id != quest_id:
                self.quest_service.unbind_source(other_id, binding_conversation_id)
                self.sessions.unbind(other_id, binding_conversation_id)
        channel.bind_conversation(binding_conversation_id, quest_id)
        self.sessions.bind(quest_id, binding_conversation_id)
        self.quest_service.bind_source(quest_id, "local:default")
        self.quest_service.bind_source(quest_id, binding_conversation_id)
        if clear_scope == "all_external":
            removed = self._unbind_external_bindings(quest_id, preserve={binding_conversation_id})
        elif clear_scope == "connector":
            removed = self._unbind_quest_connector_bindings(quest_id, connector_name, preserve={binding_conversation_id})
        else:
            removed = []
        snapshot = self.quest_service.snapshot(quest_id)
        previous_quest_id = str(existing_bound or "").strip() or None
        if previous_quest_id == quest_id:
            previous_quest_id = None
        if previous_quest_id is None:
            for item in conflicts:
                candidate = str(item.get("quest_id") or "").strip()
                if candidate and candidate != quest_id:
                    previous_quest_id = candidate
                    break
        return {
            "ok": True,
            "quest_id": quest_id,
            "connector": connector_name,
            "conversation_id": binding_conversation_id,
            "snapshot": snapshot,
            "removed_conversations": removed,
            "conflicts_resolved": [item.get("quest_id") for item in conflicts if item.get("quest_id")],
            "previous_quest_id": previous_quest_id,
        }

    def update_quest_connector_binding(
        self,
        quest_id: str,
        connector_name: str,
        conversation_id: str | None,
        *,
        force: bool = False,
    ) -> dict | tuple[int, dict]:
        quest_root = self.home / "quests" / quest_id
        if not quest_root.joinpath("quest.yaml").exists():
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}
        normalized_connector = str(connector_name or "").strip().lower()
        if not normalized_connector or normalized_connector == "local":
            return 400, {"ok": False, "message": "A non-local connector name is required."}
        if normalized_connector not in self.channels:
            return 400, {"ok": False, "message": f"Unknown connector `{normalized_connector}`."}

        normalized = normalize_conversation_id(conversation_id)
        if not normalized:
            removed = self._unbind_quest_connector_bindings(quest_id, normalized_connector)
            self.quest_service.bind_source(quest_id, "local:default")
            snapshot = self.quest_service.snapshot(quest_id)
            return {
                "ok": True,
                "quest_id": quest_id,
                "connector": normalized_connector,
                "conversation_id": None,
                "snapshot": snapshot,
                "removed_conversations": removed,
            }

        parsed = parse_conversation_id(normalized)
        if parsed is None:
            return 400, {"ok": False, "message": f"Invalid connector conversation `{normalized}`."}
        if str(parsed.get("connector") or "").strip().lower() != normalized_connector:
            return 400, {
                "ok": False,
                "message": f"Conversation `{normalized}` does not belong to connector `{normalized_connector}`.",
            }

        return self._apply_conversation_binding(quest_id, normalized, force=force, clear_scope="all_external")

    def update_quest_bindings(
        self,
        quest_id: str,
        requested_bindings: list[dict[str, object]] | None,
        *,
        force: bool = False,
    ) -> dict | tuple[int, dict]:
        quest_root = self.home / "quests" / quest_id
        if not quest_root.joinpath("quest.yaml").exists():
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}
        normalized_bindings = self._normalize_requested_connector_bindings(requested_bindings)
        if len(normalized_bindings) > 1:
            return 400, {
                "ok": False,
                "message": "A quest may bind at most one external connector target.",
                "quest_id": quest_id,
            }
        conflicts = self.preview_connector_binding_conflicts(normalized_bindings, quest_id=quest_id)
        if conflicts and not force:
            return 409, {
                "ok": False,
                "conflict": True,
                "message": "One or more connector targets are already bound to another quest.",
                "quest_id": quest_id,
                "conflicts": conflicts,
            }
        results: list[dict[str, object]] = []
        for item in normalized_bindings:
            connector_name = str(item.get("connector") or "").strip().lower()
            result = self.update_quest_connector_binding(
                quest_id,
                connector_name,
                str(item.get("conversation_id") or "").strip() or None,
                force=True if force or conflicts else False,
            )
            if isinstance(result, tuple):
                return result
            results.append(result)
        snapshot = self.quest_service.snapshot(quest_id)
        return {
            "ok": True,
            "quest_id": quest_id,
            "snapshot": snapshot,
            "results": results,
        }

    def update_quest_binding(
        self,
        quest_id: str,
        conversation_id: str | None,
        *,
        force: bool = False,
    ) -> dict | tuple[int, dict]:
        normalized = normalize_conversation_id(conversation_id)
        parsed = parse_conversation_id(normalized)

        if parsed is None or parsed.get("connector", "").lower() == "local":
            removed = self._unbind_external_bindings(quest_id)
            self.quest_service.set_binding_sources(quest_id, ["local:default"])
            snapshot = self.quest_service.snapshot(quest_id)
            return {
                "ok": True,
                "quest_id": quest_id,
                "conversation_id": None,
                "snapshot": snapshot,
                "removed_conversations": removed,
            }

        connector_name = str(parsed.get("connector") or "").strip().lower()
        if connector_name not in self.channels or connector_name == "local":
            return 400, {"ok": False, "message": f"Unknown connector `{connector_name}` for conversation `{normalized}`."}
        return self._apply_conversation_binding(quest_id, normalized, force=force, clear_scope="all_external")

    def delete_quest(self, quest_id: str, *, source: str = "web") -> dict | tuple[int, dict]:
        quests_root = self.home / "quests"
        try:
            quest_root = resolve_within(quests_root, quest_id)
        except ValueError:
            return 400, {"ok": False, "message": "Invalid quest id."}
        if not quest_root.joinpath("quest.yaml").exists():
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}

        snapshot = self.quest_service.snapshot(quest_id)
        runtime_status = str(snapshot.get("runtime_status") or snapshot.get("status") or "").strip().lower()
        if runtime_status == "running" or snapshot.get("active_run_id"):
            try:
                self.stop_quest(quest_id, source=source)
            except Exception:
                pass

        stopped_bash_sessions: list[str] = []
        try:
            for session in self.bash_exec_service.list_sessions(quest_root, limit=500):
                status = str(session.get("status") or "").strip().lower()
                if status in {"completed", "failed", "terminated"}:
                    continue
                bash_id = str(session.get("bash_id") or "").strip()
                if not bash_id:
                    continue
                try:
                    self.bash_exec_service.request_stop(
                        quest_root,
                        bash_id,
                        reason="quest_deleted",
                        user_id=source,
                    )
                    stopped_bash_sessions.append(bash_id)
                except Exception:
                    continue
        except Exception:
            stopped_bash_sessions = []

        removed_conversations = self._unbind_external_bindings(quest_id)
        self.sessions.forget(quest_id)

        try:
            shutil.rmtree(quest_root)
        except FileNotFoundError:
            return {"ok": True, "quest_id": quest_id, "deleted": False}

        self.logger.log(
            "info",
            "quest.deleted",
            quest_id=quest_id,
            source=source,
            removed_conversations=removed_conversations,
            stopped_bash_sessions=stopped_bash_sessions,
        )
        return {
            "ok": True,
            "quest_id": quest_id,
            "deleted": True,
            "removed_conversations": removed_conversations,
            "stopped_bash_sessions": stopped_bash_sessions,
        }

    def handle_connector_inbound(self, connector_name: str, body: dict) -> dict:
        if not self._is_connector_system_enabled(connector_name):
            return {
                "ok": True,
                "accepted": False,
                "reason": "system_disabled",
                "message": f"Connector `{connector_name}` is disabled at the system level.",
            }
        channel = self._channel_with_bindings(connector_name)
        ingested = channel.ingest(body)
        if not ingested.get("accepted", False):
            return {
                "ok": True,
                "accepted": False,
                "reason": ingested.get("normalized", {}).get("reason"),
                "normalized": ingested.get("normalized"),
            }
        normalized = ingested["normalized"]
        if connector_name == "qq":
            qq_binding = self._maybe_bind_qq_main_chat(normalized)
            if qq_binding is not None:
                normalized = {
                    **normalized,
                    "_qq_main_chat_binding": qq_binding,
                }
        if connector_name == "weixin":
            replay = self._maybe_replay_weixin_pending_outbox(normalized)
            if replay is not None:
                normalized = {
                    **normalized,
                    "_weixin_replay": replay,
                }
        reply = self._route_connector_message(connector_name, normalized)
        return {
            "ok": True,
            "accepted": True,
            "normalized": normalized,
            "reply": reply,
        }

    def _route_connector_message(self, connector_name: str, message: dict) -> dict:
        channel = self._channel_with_bindings(connector_name)
        connector_label = self._connector_label(connector_name)
        conversation_id = str(message.get("conversation_id") or "")
        binding_conversation_id = self._logical_connector_binding_conversation(connector_name, conversation_id)
        text = str(message.get("text") or "").strip()
        command_prefix = channel.command_prefix()
        quest_id = channel.resolve_bound_quest(conversation_id)
        if quest_id is None and str(connector_name or "").strip().lower() == "lingzhu":
            quest_id = self._resolve_lingzhu_bound_quest(conversation_id)
        command_name = ""
        args: list[str] = []
        if text.startswith(command_prefix):
            command_name, args = self._parse_prefixed_command(text, command_prefix)
        elif str(connector_name or "").strip().lower() == "lingzhu":
            parsed_lingzhu_command = self._parse_lingzhu_short_command(text)
            if parsed_lingzhu_command is not None:
                command_name, args = parsed_lingzhu_command

        if command_name:
            if command_name == "help":
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "kind": "help",
                        "message": self._connector_home_help(connector_name, message=message),
                    }
                )
            if command_name in {"projects", "quests", "list"}:
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "kind": "projects",
                        "message": self._format_projects_list(),
                    }
                )
            if command_name == "new":
                if not args:
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": self._polite_copy(
                                zh="老师您好，请先提供研究目标，例如 `/new 复现一个图神经网络基线`。",
                                en="Please provide a quest goal first, for example `/new reproduce a graph baseline`.",
                            ),
                        }
                    )
                previous_quest_id = quest_id
                goal_text = " ".join(args).strip()
                created = self.create_quest(
                    goal=goal_text,
                    source=f"{connector_name}:connector",
                    announce_connector_binding=True,
                    exclude_conversation_id=conversation_id,
                )
                self.update_quest_binding(created["quest_id"], binding_conversation_id, force=True)
                startup = self.submit_user_message(
                    created["quest_id"],
                    text=goal_text,
                    source=conversation_id,
                )
                created_snapshot = self.quest_service.snapshot(created["quest_id"])
                startup_message = self._connector_turn_start_message(
                    quest_id=created["quest_id"],
                    startup=startup,
                    snapshot=created_snapshot,
                )
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "quest_id": created["quest_id"],
                        "kind": "ack",
                        "message": self._with_qq_main_chat_notice(
                            message,
                            self._quest_created_connector_message(
                                connector_name,
                                quest_id=created["quest_id"],
                                goal=goal_text,
                                previous_quest_id=previous_quest_id,
                            )
                            + "\n"
                            + startup_message,
                        ),
                    }
                )
            if command_name == "use":
                if not args:
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": self._polite_copy(
                                zh="老师您好，请先提供 quest id，例如 `/use 001`。",
                                en="Please provide a quest id first, for example `/use 001`.",
                            ),
                        }
                    )
                requested_quest_ref = str(args[0] or "").strip()
                target_quest = self._resolve_quest_reference(requested_quest_ref) or requested_quest_ref
                if not (self.home / "quests" / target_quest / "quest.yaml").exists():
                    available = ", ".join(item["quest_id"] for item in self.quest_service.list_quests()[:6]) or "none"
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": self._polite_copy(
                                zh=f"老师，目前没有找到 quest `{requested_quest_ref}`。可用 quest 包括：{available}。",
                                en=f"I could not find quest `{requested_quest_ref}`. Available quests: {available}.",
                            ),
                        }
                    )
                previous_external = self._quest_external_binding(target_quest)
                binding_result = self.update_quest_binding(target_quest, binding_conversation_id, force=True)
                if isinstance(binding_result, tuple):
                    _status, payload = binding_result
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": str(payload.get("message") or "Unable to switch connector binding."),
                        }
                    )
                transition = self._binding_transition_summary(
                    quest_id=target_quest,
                    previous_conversation_id=previous_external,
                    current_conversation_id=self._quest_external_binding(target_quest),
                )
                self._announce_binding_transition(transition, notify_new=False, notify_old=True)
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "quest_id": target_quest,
                        "kind": "ack",
                        "message": self._polite_copy(
                            zh=f"收到啦！这里已经切到 Quest `{target_quest}` 了，接下来我会直接在这个 {connector_label} 里继续同步进展。",
                            en=f"Got it. This {connector_label} is now on Quest `{target_quest}`, and I’ll keep the next updates here. ✨",
                        ),
                    }
                )
            if command_name == "delete":
                if not args:
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": self._polite_copy(
                                zh="老师您好，请先提供 quest id，例如 `/delete 001 --yes`（删除是危险操作，需要确认）。",
                                en="Please provide a quest id, for example `/delete 001 --yes` (destructive; requires confirmation).",
                            ),
                        }
                    )
                requested_quest_ref = str(args[0] or "").strip()
                target_quest = self._resolve_quest_reference(requested_quest_ref) or requested_quest_ref
                confirmed = any(str(item).strip().lower() in {"--yes", "--force", "-y"} for item in args[1:])
                if not confirmed:
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": self._polite_copy(
                                zh=f"即将删除 quest `{target_quest}`（不可恢复）。如确认，请发送：`/delete {target_quest} --yes`。",
                                en=f"About to delete quest `{target_quest}` (irreversible). To confirm, send: `/delete {target_quest} --yes`.",
                            ),
                        }
                    )
                if not target_quest:
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": self._polite_copy(
                                zh="老师您好，请先提供 quest id，例如 `/delete 001 --yes`。",
                                en="Please provide a quest id, for example `/delete 001 --yes`.",
                            ),
                        }
                    )
                if not (self.home / "quests" / target_quest / "quest.yaml").exists():
                    available = ", ".join(item["quest_id"] for item in self.quest_service.list_quests()[:6]) or "none"
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": self._polite_copy(
                                zh=f"老师，目前没有找到 quest `{requested_quest_ref}`。可用 quest 包括：{available}。",
                                en=f"I could not find quest `{requested_quest_ref}`. Available quests: {available}.",
                            ),
                        }
                    )
                delete_result = self.delete_quest(target_quest, source=f"{connector_name}:connector")
                if isinstance(delete_result, tuple):
                    _, payload = delete_result
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": str(payload.get("message") or "Failed to delete quest."),
                        }
                    )
                follow_hint = self._polite_copy(
                    zh="如需继续，请使用 `/projects` 查看列表，或 `/use latest` 绑定最新 quest。",
                    en="To continue, use `/projects` to list quests, or `/use latest` to bind the newest quest.",
                )
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "kind": "quest_deleted",
                        "message": self._polite_copy(
                            zh=f"老师，已删除 quest `{target_quest}`。\n{follow_hint}",
                            en=f"Deleted quest `{target_quest}`.\n{follow_hint}",
                        ),
                    }
                )

            if quest_id is None and command_name not in {"help", "projects", "quests", "list", "new", "use", "delete"}:
                auto_bound = self._maybe_auto_bind_connector_conversation(connector_name, conversation_id)
                if auto_bound is not None:
                    if bool(auto_bound.get("blocked")):
                        return channel.send(
                            {
                                "conversation_id": conversation_id,
                                "kind": "ack",
                                "message": self._connector_switch_required_message(
                                    connector_name=connector_name,
                                    quest_id=str(auto_bound.get("quest_id") or "").strip(),
                                    current_conversation_id=str(auto_bound.get("current_conversation_id") or "").strip(),
                                    requested_conversation_id=str(auto_bound.get("requested_conversation_id") or "").strip(),
                                ),
                            }
                        )
                    quest_id = str(auto_bound.get("quest_id") or "").strip() or None

            if command_name in {"stop", "resume"}:
                target_quest_id = quest_id
                if args:
                    target_quest_id = self._resolve_quest_reference(args[0])
                if not self._quest_exists(target_quest_id):
                    if args:
                        requested = str(args[0] or "").strip() or "<quest_id>"
                        available = ", ".join(item["quest_id"] for item in self.quest_service.list_quests()[:6]) or "none"
                        return channel.send(
                            {
                                "conversation_id": conversation_id,
                                "kind": "ack",
                                "message": self._polite_copy(
                                    zh=f"老师，目前没有找到 quest `{requested}`。可用 quest 包括：{available}。",
                                    en=f"I could not find quest `{requested}`. Available quests: {available}.",
                                ),
                            }
                        )
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": self._connector_home_help(connector_name, message=message),
                        }
                    )
                target_quest_id = str(target_quest_id or "").strip()
                bound_quest_id = str(channel.resolve_bound_quest(conversation_id) or "").strip() or None
                self.sessions.bind(target_quest_id, conversation_id)
                self.quest_service.bind_source(target_quest_id, binding_conversation_id)
                result = self.control_quest(
                    target_quest_id,
                    action=command_name,
                    source=f"{connector_name}:connector",
                )
                return self._connector_control_reply(
                    connector_name,
                    conversation_id=conversation_id,
                    quest_id=target_quest_id,
                    action=command_name,
                    result=result,
                    deliver_directly=bound_quest_id != target_quest_id,
                )

            if quest_id is None:
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "kind": "ack",
                        "message": self._connector_home_help(connector_name, message=message),
                    }
                )

            self.sessions.bind(quest_id, conversation_id)
            self.quest_service.bind_source(quest_id, binding_conversation_id)
            if command_name == "status":
                snapshot = self.quest_service.snapshot(quest_id)
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "quest_id": quest_id,
                        "kind": "status",
                        "message": self._format_status(snapshot),
                    }
                )
            if command_name == "summary":
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "quest_id": quest_id,
                        "kind": "summary",
                        "message": self._format_summary(quest_id),
                    }
                )
            if command_name == "metrics":
                run_id = args[0] if args else None
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "quest_id": quest_id,
                        "kind": "metrics",
                        "message": self._format_metrics(quest_id, run_id=run_id),
                    }
                )
            if command_name == "graph":
                graph = self.artifact_service.render_git_graph(self.home / "quests" / quest_id)
                attachments = [
                    {"kind": "path", "path": graph["graph"].get("png_path") or graph["graph"].get("svg_path")},
                    {"kind": "path", "path": graph["graph"].get("json_path")},
                ]
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "quest_id": quest_id,
                        "kind": "graph",
                        "message": self._format_graph_reply(quest_id, graph["graph"]),
                        "attachments": [item for item in attachments if item.get("path")],
                    }
                )
            if command_name == "terminal":
                quest_root = self.home / "quests" / quest_id
                workspace_root = self.quest_service.active_workspace_root(quest_root)
                session = self.bash_exec_service.ensure_terminal_session(
                    quest_root,
                    quest_id=quest_id,
                    cwd=workspace_root,
                    source=f"{connector_name}:connector",
                    conversation_id=conversation_id,
                    user_id=f"user:{connector_name}",
                )
                if args and args[0] == "-R":
                    restored = self.bash_exec_service.terminal_restore_payload(
                        quest_root,
                        str(session.get("bash_id") or ""),
                        command_limit=10,
                        output_limit=40,
                    )
                    commands = [
                        str(item.get("command") or "").strip()
                        for item in restored.get("latest_commands") or []
                        if str(item.get("command") or "").strip()
                    ]
                    tail_preview = [
                        str(item.get("line") or "").strip()
                        for item in (restored.get("tail") or [])[-4:]
                        if str(item.get("line") or "").strip()
                    ]
                    lines = [
                        f"Terminal `{restored.get('session_id')}`",
                        f"status: {restored.get('status') or 'unknown'}",
                        f"cwd: {restored.get('cwd') or session.get('cwd') or quest_root}",
                    ]
                    if commands:
                        lines.append("latest commands:")
                        lines.extend(f"- {item}" for item in reversed(commands[-10:]))
                    if tail_preview:
                        lines.append("recent output:")
                        lines.extend(f"- {item}" for item in tail_preview)
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "quest_id": quest_id,
                            "kind": "terminal_restore",
                            "message": "\n".join(lines),
                        }
                    )
                if args:
                    command_text = " ".join(args).rstrip()
                    result = self.bash_exec_service.append_terminal_input(
                        quest_root,
                        str(session.get("bash_id") or ""),
                        data=f"{command_text}\n",
                        source=f"{connector_name}:connector",
                        user_id=f"user:{connector_name}",
                        conversation_id=conversation_id,
                    )
                    cwd_value = str(result.get("session", {}).get("cwd") or session.get("cwd") or quest_root)
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "quest_id": quest_id,
                            "kind": "terminal",
                            "message": self._polite_copy(
                                zh=f"已发送到终端 `{session.get('bash_id')}`，当前路径：`{cwd_value}`。\n命令：`{command_text}`",
                                en=f"Sent to terminal `{session.get('bash_id')}` at `{cwd_value}`.\nCommand: `{command_text}`",
                            ),
                        }
                    )
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "quest_id": quest_id,
                        "kind": "terminal",
                        "message": self._polite_copy(
                            zh=f"终端 `{session.get('bash_id')}` 已就绪。\n状态：{session.get('status')}\n当前路径：`{session.get('cwd')}`",
                            en=f"Terminal `{session.get('bash_id')}` is ready.\nstatus: {session.get('status')}\ncwd: `{session.get('cwd')}`",
                        ),
                    }
                )
            if command_name == "approve":
                if not args:
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "quest_id": quest_id,
                            "kind": "ack",
                            "message": self._polite_copy(
                                zh="老师您好，请先提供决策 id，例如 `/approve decision-001`。",
                                en="Please provide a decision id, for example `/approve decision-001`.",
                            ),
                        }
                    )
                decision_id = args[0]
                reason = " ".join(args[1:]).strip() or self._polite_copy(
                    zh=f"由 {connector_label} 侧确认通过。",
                    en=f"Approved from {connector_label}.",
                )
                result = self.artifact_service.record(
                    self.home / "quests" / quest_id,
                    {
                        "kind": "approval",
                        "decision_id": decision_id,
                        "reason": reason,
                        "source": {
                            "kind": "user",
                            "conversation_id": conversation_id,
                            "user_id": message.get("sender_id"),
                        },
                        "raw_text": text,
                    },
                )
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "quest_id": quest_id,
                        "kind": "approval_result",
                        "message": self._polite_copy(
                            zh=f"Approval recorded for `{decision_id}`. 老师，已记录通过决定。原因：{reason}",
                            en=f"Approval recorded for `{decision_id}`. Reason: {reason}",
                        ),
                        "attachments": [{"kind": "path", "path": result.get("path")}],
                    }
                )

        if quest_id is None:
            auto_bound = self._maybe_auto_bind_connector_conversation(connector_name, conversation_id)
            if auto_bound is not None:
                if bool(auto_bound.get("blocked")):
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": self._connector_switch_required_message(
                                connector_name=connector_name,
                                quest_id=str(auto_bound.get("quest_id") or "").strip(),
                                current_conversation_id=str(auto_bound.get("current_conversation_id") or "").strip(),
                                requested_conversation_id=str(auto_bound.get("requested_conversation_id") or "").strip(),
                            ),
                        }
                    )
                quest_id = str(auto_bound.get("quest_id") or "").strip() or None

        if quest_id is None:
            return channel.send(
                {
                    "conversation_id": conversation_id,
                    "kind": "ack",
                    "message": self._connector_home_help(connector_name, message=message),
                }
            )

        self.sessions.bind(quest_id, conversation_id)
        self.quest_service.bind_source(quest_id, binding_conversation_id)
        materialized_attachments = self._materialize_connector_attachments(
            quest_id=quest_id,
            connector_name=connector_name,
            conversation_id=conversation_id,
            message_id=str(message.get("message_id") or "").strip() or None,
            attachments=[dict(item) for item in (message.get("attachments") or []) if isinstance(item, dict)],
        )
        startup = self.submit_user_message(
            quest_id,
            text=self._connector_message_text_with_attachment_notice(
                original_text=text,
                attachments=materialized_attachments,
            ),
            source=conversation_id,
            attachments=materialized_attachments,
        )
        snapshot = self.quest_service.snapshot(quest_id)
        startup_message = self._connector_turn_start_message(
            quest_id=quest_id,
            startup=startup,
            snapshot=snapshot,
        )
        return channel.send(
            {
                "conversation_id": conversation_id,
                "quest_id": quest_id,
                "kind": "ack",
                "message": self._with_qq_main_chat_notice(message, startup_message),
            }
        )

    def _connector_message_text_with_attachment_notice(
        self,
        *,
        original_text: str,
        attachments: list[dict[str, object]],
    ) -> str:
        base = str(original_text or "").strip()
        if not attachments:
            return base
        lines: list[str] = []
        if base:
            lines.extend([base, ""])
        lines.append(
            self._polite_copy(
                zh="系统提示：用户刚刚发送了附件。请优先阅读这些 quest 本地文件，再继续处理这条请求：",
                en="System note: the user just sent attachments. Read these quest-local files first before continuing this request:",
            )
        )
        for index, item in enumerate(attachments, start=1):
            label = str(
                item.get("name")
                or item.get("quest_relative_path")
                or item.get("path")
                or item.get("url")
                or f"attachment-{index}"
            ).strip()
            content_type = str(item.get("content_type") or "").strip()
            location = str(item.get("path") or item.get("url") or "unavailable").strip()
            error = str(item.get("download_error") or "").strip()
            suffix = f" ({content_type})" if content_type else ""
            if error:
                lines.append(f"- {label}{suffix}: {location} | download_error={error}")
            else:
                lines.append(f"- {label}{suffix}: {location}")
        return "\n".join(lines).strip()

    def _materialize_connector_attachments(
        self,
        *,
        quest_id: str,
        connector_name: str,
        conversation_id: str,
        message_id: str | None,
        attachments: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        if not attachments:
            return []
        quest_root = self.home / "quests" / quest_id
        batch_slug = slugify(message_id or generate_id("userfile"), default=generate_id("userfile"))
        batch_root = ensure_dir(quest_root / "userfiles" / connector_name / batch_slug)
        materialized: list[dict[str, object]] = []
        for index, raw_item in enumerate(attachments, start=1):
            materialized.append(
                self._materialize_single_connector_attachment(
                    connector_name=connector_name,
                    quest_root=quest_root,
                    batch_root=batch_root,
                    index=index,
                    attachment=dict(raw_item),
                )
            )
        write_json(
            batch_root / "manifest.json",
            {
                "connector": connector_name,
                "quest_id": quest_id,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "materialized_at": utc_now(),
                "attachments": materialized,
            },
        )
        return materialized

    def _materialize_single_connector_attachment(
        self,
        *,
        connector_name: str,
        quest_root: Path,
        batch_root: Path,
        index: int,
        attachment: dict[str, object],
    ) -> dict[str, object]:
        resolved = dict(attachment)
        name = str(resolved.get("name") or "").strip()
        content_type = str(resolved.get("content_type") or "").strip()
        url = str(resolved.get("url") or "").strip()
        path = str(resolved.get("path") or "").strip()
        target_path = batch_root / self._connector_attachment_filename(index=index, name=name, content_type=content_type)
        resolved["manifest_path"] = str(batch_root / "manifest.json")
        resolved["batch_path"] = str(batch_root)
        if path:
            try:
                source_path = Path(path).expanduser()
                if not source_path.is_absolute():
                    source_path = (quest_root / source_path).resolve()
                else:
                    source_path = source_path.resolve()
                if not source_path.exists():
                    raise FileNotFoundError(f"attachment local path does not exist: {source_path}")
                size_bytes = self._copy_connector_attachment(
                    source_path=source_path,
                    target_path=target_path,
                )
                resolved["path"] = str(target_path)
                resolved["source_path"] = str(source_path)
                resolved["quest_relative_path"] = str(target_path.relative_to(quest_root))
                resolved["size_bytes"] = int(size_bytes)
                resolved["materialized"] = True
                resolved["downloaded_at"] = utc_now()
                return resolved
            except Exception as exc:
                if not url:
                    resolved["materialized"] = False
                    resolved["download_error"] = str(exc)
                    return resolved
        try:
            size_bytes = self._download_connector_attachment(
                connector_name=connector_name,
                url=url,
                target_path=target_path,
            )
            resolved["path"] = str(target_path)
            resolved["quest_relative_path"] = str(target_path.relative_to(quest_root))
            resolved["size_bytes"] = int(size_bytes)
            resolved["materialized"] = True
            resolved["downloaded_at"] = utc_now()
            return resolved
        except Exception as exc:
            if target_path.exists():
                target_path.unlink(missing_ok=True)
            resolved["materialized"] = False
            resolved["download_error"] = str(exc)
            return resolved

    def _copy_connector_attachment(
        self,
        *,
        source_path: Path,
        target_path: Path,
    ) -> int:
        ensure_dir(target_path.parent)
        total = 0
        with source_path.open("rb") as source_handle:
            with target_path.open("wb") as target_handle:
                while True:
                    chunk = source_handle.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > self._MAX_INBOUND_ATTACHMENT_BYTES:
                        raise ValueError(
                            f"attachment exceeds max inbound size limit ({self._MAX_INBOUND_ATTACHMENT_BYTES} bytes)"
                        )
                    target_handle.write(chunk)
        return total

    def _download_connector_attachment(
        self,
        *,
        connector_name: str,
        url: str,
        target_path: Path,
    ) -> int:
        request = Request(url)
        for key, value in self._connector_attachment_headers(connector_name).items():
            request.add_header(key, value)
        ensure_dir(target_path.parent)
        total = 0
        with urlopen(request, timeout=20) as response:  # noqa: S310
            with target_path.open("wb") as handle:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > self._MAX_INBOUND_ATTACHMENT_BYTES:
                        raise ValueError(
                            f"attachment exceeds max inbound size limit ({self._MAX_INBOUND_ATTACHMENT_BYTES} bytes)"
                        )
                    handle.write(chunk)
        return total

    def _connector_attachment_headers(self, connector_name: str) -> dict[str, str]:
        if str(connector_name or "").strip().lower() != "qq":
            return {}
        config = self.connectors_config.get("qq", {})
        if not isinstance(config, dict):
            return {}
        app_id = str(config.get("app_id") or "").strip()
        app_secret = QQConnectorBridge.read_secret(config, "app_secret", "app_secret_env")
        if not app_id or not app_secret:
            return {}
        return {
            "Authorization": f"QQBot {QQConnectorBridge._access_token(app_id, app_secret)}",
        }

    @staticmethod
    def _connector_attachment_filename(*, index: int, name: str, content_type: str) -> str:
        raw_name = str(name or "").strip()
        suffix = Path(raw_name).suffix if raw_name else ""
        if not suffix and content_type:
            suffix = mimetypes.guess_extension(content_type, strict=False) or ""
        if suffix and not suffix.startswith("."):
            suffix = f".{suffix}"
        stem_source = Path(raw_name).stem if raw_name else f"attachment-{index:03d}"
        stem = slugify(stem_source, default=f"attachment-{index:03d}")
        return f"{stem}{suffix or '.bin'}"

    def _qq_channel(self) -> QQRelayChannel:
        return self.channels["qq"]  # type: ignore[return-value]

    def _auto_bind_connectors_to_latest_quest(
        self,
        quest_id: str,
        *,
        goal: str,
        source: str,
        announce: bool,
        exclude_conversation_id: str | None = None,
    ) -> list[str]:
        candidates: list[tuple[str, str]] = []
        for connector_name, channel in self.channels.items():
            if connector_name == "local":
                continue
            if not self._is_connector_system_enabled(connector_name):
                continue
            connector_config = self.connectors_config.get(connector_name, {})
            if not isinstance(connector_config, dict):
                continue
            if not connector_config.get("enabled", False):
                continue
            if not connector_config.get("auto_bind_dm_to_active_quest", False):
                continue
            for conversation_id in self._latest_connector_conversation_ids(connector_name):
                if not conversation_id or conversation_id == exclude_conversation_id:
                    continue
                candidates.append((connector_name, conversation_id))

        if not candidates:
            return []

        preferred_conversation_id = str(self.connector_availability_summary().get("preferred_conversation_id") or "").strip()
        selected: tuple[str, str] | None = None
        if preferred_conversation_id:
            for item in candidates:
                if conversation_identity_key(item[1]) == conversation_identity_key(preferred_conversation_id):
                    selected = item
                    break
        if selected is None:
            selected = candidates[0]

        connector_name, conversation_id = selected
        result = self._apply_conversation_binding(quest_id, conversation_id, force=True, clear_scope="none")
        if isinstance(result, tuple):
            return []
        bound_conversation = str(result.get("conversation_id") or "").strip() or conversation_id
        if announce:
            channel = self._channel_with_bindings(connector_name)
            channel.send(
                {
                    "conversation_id": bound_conversation,
                    "quest_id": quest_id,
                    "kind": "ack",
                    "message": self._quest_created_connector_message(
                        connector_name,
                        quest_id=quest_id,
                        goal=goal,
                        previous_quest_id=str(result.get("previous_quest_id") or "").strip() or None,
                    ),
                }
            )
        return [bound_conversation]

    def _latest_connector_conversation_id(self, connector_name: str) -> str:
        candidates = self._latest_connector_conversation_ids(connector_name)
        return candidates[0] if candidates else ""

    def _latest_connector_conversation_ids(self, connector_name: str) -> list[str]:
        conversation_ids: list[str] = []
        if connector_name == "qq":
            qq_config = self.connectors_config.get("qq", {})
            if isinstance(qq_config, dict):
                profiles = list_qq_profiles(qq_config)
                encode_profile_id = len(profiles) > 1
                for profile in profiles:
                    main_chat_id = str(profile.get("main_chat_id") or "").strip()
                    profile_id = str(profile.get("profile_id") or "").strip()
                    if main_chat_id:
                        conversation_ids.append(
                            format_conversation_id(
                                "qq",
                                "direct",
                                main_chat_id,
                                profile_id=profile_id if encode_profile_id else None,
                            )
                        )
        elif connector_name in PROFILEABLE_CONNECTOR_NAMES:
            connector_config = self.connectors_config.get(connector_name, {})
            if isinstance(connector_config, dict):
                for profile in list_connector_profiles(connector_name, connector_config):
                    profile_id = str(profile.get("profile_id") or "").strip()
                    if not profile_id:
                        continue
                    runtime_state = read_json(
                        self.home / "logs" / "connectors" / connector_name / "profiles" / profile_id / "runtime.json",
                        {},
                    )
                    if isinstance(runtime_state, dict):
                        runtime_last_conversation_id = str(runtime_state.get("last_conversation_id") or "").strip()
                        if runtime_last_conversation_id:
                            conversation_ids.append(runtime_last_conversation_id)
        state_path = self.home / "logs" / "connectors" / connector_name / "state.json"
        state = read_json(state_path, {})
        if isinstance(state, dict):
            last_conversation_id = str(state.get("last_conversation_id") or "").strip()
            if last_conversation_id:
                conversation_ids.append(last_conversation_id)
            for item in state.get("recent_conversations") or []:
                if not isinstance(item, dict):
                    continue
                conversation_id = str(item.get("conversation_id") or "").strip()
                if conversation_id:
                    conversation_ids.append(conversation_id)
        runtime_state = read_json(self.home / "logs" / "connectors" / connector_name / "runtime.json", {})
        if isinstance(runtime_state, dict):
            runtime_last_conversation_id = str(runtime_state.get("last_conversation_id") or "").strip()
            if runtime_last_conversation_id:
                conversation_ids.append(runtime_last_conversation_id)
        try:
            channel = self._channel_with_bindings(connector_name)
            for item in channel.list_bindings():
                conversation_id = str(item.get("conversation_id") or "").strip()
                if conversation_id:
                    conversation_ids.append(conversation_id)
        except Exception:
            pass
        ordered: list[str] = []
        seen: set[str] = set()
        for conversation_id in conversation_ids:
            identity = conversation_identity_key(conversation_id)
            if not conversation_id or identity in seen:
                continue
            seen.add(identity)
            ordered.append(conversation_id)
        return ordered

    def _latest_quest_id(self) -> str | None:
        quests = self.quest_service.list_quests()
        if not quests:
            return None
        quest_id = str(quests[0].get("quest_id") or "").strip()
        return quest_id or None

    @staticmethod
    def _strip_quest_reference_noise(value: str | None) -> str:
        normalized = lingzhu_normalize_command_text(value)
        if not normalized:
            return ""
        normalized = re.sub(r"^(?:第|quest|Quest|任务|项目)\s*", "", normalized).strip()
        normalized = re.sub(r"\s*(?:号|个|个任务|任务)\s*$", "", normalized).strip()
        return normalized

    @staticmethod
    def _parse_chinese_numeric_reference(value: str) -> str | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        if all(char in _CHINESE_DIGIT_MAP for char in normalized):
            return "".join(str(_CHINESE_DIGIT_MAP[char]) for char in normalized)
        if not all(char in _CHINESE_DIGIT_MAP or char in _CHINESE_UNIT_MAP for char in normalized):
            return None
        total = 0
        current = 0
        for char in normalized:
            if char in _CHINESE_DIGIT_MAP:
                current = _CHINESE_DIGIT_MAP[char]
                continue
            unit = _CHINESE_UNIT_MAP.get(char)
            if unit is None:
                return None
            total += (current or 1) * unit
            current = 0
        total += current
        return str(total) if total > 0 else None

    def _resolve_numeric_quest_id(self, value: str | None) -> str | None:
        normalized = str(value or "").strip()
        if not normalized or not normalized.isdigit():
            return None
        if self._quest_exists(normalized):
            return normalized
        target_numeric = int(normalized)
        for item in self.quest_service.list_quests():
            quest_id = str(item.get("quest_id") or "").strip()
            if not quest_id.isdigit():
                continue
            if int(quest_id) == target_numeric:
                return quest_id
        return None

    def _quest_exists(self, quest_id: str | None) -> bool:
        normalized = str(quest_id or "").strip()
        if not normalized:
            return False
        return (self.home / "quests" / normalized / "quest.yaml").exists()

    def _resolve_quest_reference(self, value: str | None) -> str | None:
        normalized = self._strip_quest_reference_noise(value)
        if not normalized:
            return None
        if normalized in {"latest", "newest"}:
            return self._latest_quest_id()
        literal_match = normalized if self._quest_exists(normalized) else None
        if literal_match:
            return literal_match
        numeric_match = self._resolve_numeric_quest_id(normalized)
        if numeric_match:
            return numeric_match
        chinese_numeric = self._parse_chinese_numeric_reference(normalized)
        if chinese_numeric:
            numeric_match = self._resolve_numeric_quest_id(chinese_numeric)
            if numeric_match:
                return numeric_match
        return normalized

    def _connector_control_reply(
        self,
        connector_name: str,
        *,
        conversation_id: str,
        quest_id: str,
        action: str,
        result: dict[str, Any],
        deliver_directly: bool,
    ) -> dict:
        channel = self._channel_with_bindings(connector_name)
        snapshot = result.get("snapshot") or {}
        event = result.get("event") or {}
        payload = {
            "conversation_id": conversation_id,
            "quest_id": quest_id,
            "kind": "progress",
            "message": str((result.get("notice") or {}).get("message") or result.get("message") or "").strip(),
            "response_phase": "control",
            "importance": "warning" if action in {"pause", "stop"} else "info",
            "attachments": [
                {
                    "kind": "quest_control",
                    "action": action,
                    "status": snapshot.get("status"),
                    "source": event.get("source"),
                    "branch": snapshot.get("branch"),
                    "workspace_root": snapshot.get("current_workspace_root") or snapshot.get("quest_root"),
                    "interrupted": bool(result.get("interrupted")),
                    "cancelled_pending_user_message_count": int(
                        result.get("cancelled_pending_user_message_count") or 0
                    ),
                    "stop_reason": snapshot.get("stop_reason"),
                }
            ],
        }
        if deliver_directly:
            return channel.send(payload)
        formatted = channel._format_outbound(payload) if hasattr(channel, "_format_outbound") else payload
        return {
            "ok": True,
            "queued": False,
            "channel": connector_name,
            "payload": formatted,
            "delivery": {
                "ok": True,
                "queued": False,
                "transport": f"{connector_name}-control",
            },
        }

    def _maybe_auto_bind_connector_conversation(self, connector_name: str, conversation_id: str) -> dict | None:
        if not self._is_connector_system_enabled(connector_name):
            return None
        connector_config = self.connectors_config.get(connector_name, {})
        if not isinstance(connector_config, dict):
            return None
        if not connector_config.get("enabled", False):
            return None
        if not connector_config.get("auto_bind_dm_to_active_quest", False):
            return None
        latest_quest_id = self._latest_quest_id()
        if latest_quest_id is None:
            return None
        normalized_conversation_id = self._logical_connector_binding_conversation(connector_name, conversation_id)
        current_external = self._quest_external_binding(latest_quest_id)
        if current_external and conversation_identity_key(current_external) != conversation_identity_key(normalized_conversation_id):
            return {
                "ok": False,
                "blocked": True,
                "quest_id": latest_quest_id,
                "current_conversation_id": current_external,
                "requested_conversation_id": normalized_conversation_id,
            }
        result = self.update_quest_binding(latest_quest_id, normalized_conversation_id, force=True)
        if isinstance(result, tuple):
            return None
        return result

    def _connector_home_help(self, connector_name: str, *, message: dict) -> str:
        if str(connector_name or "").strip().lower() == "lingzhu":
            return self._with_qq_main_chat_notice(message, self._lingzhu_unbound_help_text())
        quests = self.quest_service.list_quests()
        latest = str(quests[0]["quest_id"]) if quests else "none"
        body = self._polite_copy(
            zh=(
                "当前这个 connector 会话还没有绑定 quest。\n"
                "在创建或绑定 quest 之前，仅支持以下关键字：\n"
                "- `/help`：查看帮助\n"
                f"- `/projects` 或 `/list`：查看最近的 quest（当前最新：`{latest}`）\n"
                "- `/use <quest_id>`：绑定指定 quest\n"
                "- `/use latest`：直接绑定当前最新 quest\n"
                "- `/new <goal>`：新建一个 quest 并自动绑定当前会话\n"
                "- `/stop [quest_id|latest]`：停止当前或指定 quest\n"
                "- `/resume [quest_id|latest]`：恢复当前或指定 quest\n"
                "- `/delete <quest_id> --yes`：删除指定 quest（危险操作，需要确认）\n"
                "如果当前已经存在最新 quest，除上述 home 命令外的普通文本或工作命令会自动绑定到最新 quest 并继续执行；如果当前还没有任何 quest，普通文本会先返回这份帮助。"
            ),
            en=(
                "This connector conversation is not bound to any quest yet.\n"
                "Before a quest is created or selected, only these commands are available:\n"
                "- `/help`: show help\n"
                f"- `/projects` or `/list`: list recent quests (latest: `{latest}`)\n"
                "- `/use <quest_id>`: bind a specific quest\n"
                "- `/use latest`: bind the latest quest\n"
                "- `/new <goal>`: create a new quest and bind this conversation\n"
                "- `/stop [quest_id|latest]`: stop the current or selected quest\n"
                "- `/resume [quest_id|latest]`: resume the current or selected quest\n"
                "- `/delete <quest_id> --yes`: delete a quest (destructive; requires confirmation)\n"
                "If a latest quest already exists, plain text or quest commands will auto-bind this conversation to it; if no quest exists yet, plain text will return this help instead of going to the agent."
            ),
        )
        return self._with_qq_main_chat_notice(message, body)

    def _quest_external_binding(self, quest_id: str | None) -> str | None:
        normalized_quest_id = str(quest_id or "").strip()
        if not normalized_quest_id:
            return None
        for source in self.quest_service.binding_sources(normalized_quest_id):
            parsed = parse_conversation_id(source)
            if parsed is None:
                continue
            if str(parsed.get("connector") or "").strip().lower() == "local":
                continue
            return normalize_conversation_id(source)
        return None

    def _lingzhu_passive_conversation_id(self) -> str | None:
        lingzhu_config = self.connectors_config.get("lingzhu")
        resolved = dict(lingzhu_config) if isinstance(lingzhu_config, dict) else {}
        auth_ak = self.config_manager._secret(resolved, "auth_ak", "auth_ak_env")
        if not auth_ak:
            return None
        return lingzhu_passive_conversation_id(resolved)

    def _logical_connector_binding_conversation(self, connector_name: str, conversation_id: str | None) -> str:
        normalized_connector = str(connector_name or "").strip().lower()
        if normalized_connector == "lingzhu":
            passive_conversation_id = self._lingzhu_passive_conversation_id()
            if passive_conversation_id:
                return passive_conversation_id
        return normalize_conversation_id(conversation_id)

    def _remove_connector_sources_from_quest(self, quest_id: str, connector_name: str) -> None:
        normalized_connector = str(connector_name or "").strip().lower()
        if not normalized_connector:
            return
        current_sources = self.quest_service.binding_sources(quest_id)
        filtered_sources = []
        for source in current_sources:
            parsed = parse_conversation_id(source)
            if parsed is not None and str(parsed.get("connector") or "").strip().lower() == normalized_connector:
                continue
            filtered_sources.append(source)
        self.quest_service.set_binding_sources(quest_id, filtered_sources or ["local:default"])

    def _canonicalize_lingzhu_binding_state(self) -> None:
        passive_conversation_id = self._lingzhu_passive_conversation_id()
        if not passive_conversation_id:
            return
        try:
            channel = self._channel_with_bindings("lingzhu")
        except Exception:
            return
        bindings = [dict(item) for item in channel.list_bindings() if isinstance(item, dict)]
        selected_quest_id: str | None = None
        selected_updated_at = ""
        quests_with_lingzhu_sources: set[str] = set()

        for item in bindings:
            quest_id = str(item.get("quest_id") or "").strip()
            updated_at = str(item.get("updated_at") or "").strip()
            if quest_id and (updated_at, quest_id) >= (selected_updated_at, str(selected_quest_id or "")):
                selected_quest_id = quest_id
                selected_updated_at = updated_at

        for quest in self.quest_service.list_quests():
            quest_id = str(quest.get("quest_id") or "").strip()
            if not quest_id:
                continue
            sources = self.quest_service.binding_sources(quest_id)
            if any(
                (
                    parsed := parse_conversation_id(source)
                ) is not None and str(parsed.get("connector") or "").strip().lower() == "lingzhu"
                for source in sources
            ):
                quests_with_lingzhu_sources.add(quest_id)
                if not selected_quest_id:
                    selected_quest_id = quest_id

        for item in bindings:
            conversation_id = str(item.get("conversation_id") or "").strip()
            quest_id = str(item.get("quest_id") or "").strip() or None
            if not conversation_id:
                continue
            channel.unbind_conversation(conversation_id, quest_id=quest_id)
            if quest_id:
                self.sessions.unbind(quest_id, conversation_id)

        for quest_id in quests_with_lingzhu_sources:
            self._remove_connector_sources_from_quest(quest_id, "lingzhu")

        if selected_quest_id:
            channel.bind_conversation(passive_conversation_id, selected_quest_id)
            self.quest_service.bind_source(selected_quest_id, "local:default")
            self.quest_service.bind_source(selected_quest_id, passive_conversation_id)

    def _resolve_lingzhu_bound_quest(self, conversation_id: str) -> str | None:
        normalized_conversation_id = normalize_conversation_id(conversation_id)
        channel = self._channel_with_bindings("lingzhu")
        known_quest_id = str(channel.resolve_bound_quest(normalized_conversation_id) or "").strip() or None
        if known_quest_id:
            return known_quest_id
        passive_conversation_id = self._lingzhu_passive_conversation_id()
        passive_quest_id = str(channel.resolve_bound_quest(passive_conversation_id) or "").strip() or None
        if not passive_quest_id:
            return None
        return passive_quest_id

    def _connector_target_label(self, conversation_id: str | None) -> str:
        normalized = normalize_conversation_id(conversation_id)
        parsed = parse_conversation_id(normalized)
        if parsed is None:
            return str(conversation_id or "unknown").strip() or "unknown"
        connector_label = self._connector_label(str(parsed.get("connector") or "").strip())
        profile_id = str(parsed.get("profile_id") or "").strip()
        if lingzhu_is_passive_conversation_id(normalized):
            agent_id = str(parsed.get("chat_id_raw") or parsed.get("chat_id") or "").strip() or "main"
            return f"{connector_label} · passive · {agent_id}"
        chat_id = str(parsed.get("chat_id_raw") or parsed.get("chat_id") or normalized).strip()
        if profile_id:
            return f"{connector_label} · {profile_id} · {chat_id}"
        return f"{connector_label} · {chat_id}"

    def _binding_transition_summary(
        self,
        *,
        quest_id: str,
        previous_conversation_id: str | None,
        current_conversation_id: str | None,
    ) -> dict[str, Any]:
        previous = normalize_conversation_id(previous_conversation_id)
        current = normalize_conversation_id(current_conversation_id)
        if conversation_identity_key(previous) == conversation_identity_key(current):
            mode = "unchanged"
        elif previous and current:
            mode = "switch"
        elif current:
            mode = "bind"
        elif previous:
            mode = "disconnect"
        else:
            mode = "unchanged"
        return {
            "quest_id": quest_id,
            "mode": mode,
            "previous_conversation_id": previous or None,
            "previous_label": self._connector_target_label(previous) if previous else None,
            "current_conversation_id": current or None,
            "current_label": self._connector_target_label(current) if current else None,
            "changed": mode != "unchanged",
        }

    def _announce_binding_transition(
        self,
        summary: dict[str, Any] | None,
        *,
        notify_new: bool,
        notify_old: bool,
    ) -> None:
        if not isinstance(summary, dict) or not bool(summary.get("changed")):
            return
        quest_id = str(summary.get("quest_id") or "").strip()
        previous_conversation_id = str(summary.get("previous_conversation_id") or "").strip() or None
        current_conversation_id = str(summary.get("current_conversation_id") or "").strip() or None
        previous_label = str(summary.get("previous_label") or "").strip() or None
        current_label = str(summary.get("current_label") or "").strip() or None
        mode = str(summary.get("mode") or "").strip()

        if notify_old and previous_conversation_id and conversation_identity_key(previous_conversation_id) != conversation_identity_key(current_conversation_id):
            old_connector = str((parse_conversation_id(previous_conversation_id) or {}).get("connector") or "").strip().lower()
            if old_connector and old_connector in self.channels:
                channel = self._channel_with_bindings(old_connector)
                if mode == "disconnect":
                    message = self._polite_copy(
                        zh=f"Quest `{quest_id}` 已经从这里解绑啦，后面会只在本地继续推进。",
                        en=f"Quest `{quest_id}` is no longer bound here. It will continue locally only. 📌",
                    )
                else:
                    message = self._polite_copy(
                        zh=f"Quest `{quest_id}` 已经从这里切走啦，后面的进展请在 {current_label} 查看。",
                        en=f"Quest `{quest_id}` has moved away from this conversation. Continue from {current_label}. 🔁",
                    )
                channel.send(
                    {
                        "conversation_id": previous_conversation_id,
                        "quest_id": quest_id,
                        "kind": "binding_notice",
                        "message": message,
                    }
                )

        if notify_new and current_conversation_id:
            new_connector = str((parse_conversation_id(current_conversation_id) or {}).get("connector") or "").strip().lower()
            if new_connector and new_connector in self.channels:
                channel = self._channel_with_bindings(new_connector)
                if mode == "bind":
                    message = self._polite_copy(
                        zh=f"收到！Quest `{quest_id}` 已经接上啦，后面的进展我都会直接在这里同步给您。",
                        en=f"Quest `{quest_id}` is now connected here, and I’ll keep the next updates in this conversation. ✨",
                    )
                elif mode == "switch":
                    message = self._polite_copy(
                        zh=f"收到！Quest `{quest_id}` 已经切到这里啦，后面的进展我都会直接在这里同步给您。",
                        en=f"Quest `{quest_id}` has switched over here, and I’ll keep the next updates in this conversation. 🔄",
                    )
                else:
                    message = ""
                if message:
                    channel.send(
                        {
                            "conversation_id": current_conversation_id,
                            "quest_id": quest_id,
                            "kind": "binding_notice",
                            "message": message,
                        }
                    )

    def _connector_switch_required_message(
        self,
        *,
        connector_name: str,
        quest_id: str,
        current_conversation_id: str,
        requested_conversation_id: str,
    ) -> str:
        switch_command = f"绑定{quest_id}" if str(connector_name or "").strip().lower() == "lingzhu" else f"/use {quest_id}"
        return self._polite_copy(
            zh=(
                f"当前 Quest `{quest_id}` 已绑定 {self._connector_target_label(current_conversation_id)}。\n"
                f"如需切换到 {self._connector_target_label(requested_conversation_id)}，请发送 `{switch_command}`，或在项目设置里保存切换。"
            ),
            en=(
                f"Quest `{quest_id}` is already bound to {self._connector_target_label(current_conversation_id)}.\n"
                f"To switch to {self._connector_target_label(requested_conversation_id)}, send `{switch_command}` or save the change from project settings."
            ),
        )

    def _unbind_external_bindings(self, quest_id: str, *, preserve: set[str] | None = None) -> list[str]:
        preserve_keys = {conversation_identity_key(item) for item in (preserve or set()) if item}
        removed: list[str] = []
        for connector_name in sorted(self.channels.keys()):
            if connector_name == "local":
                continue
            try:
                channel = self._channel_with_bindings(connector_name)
            except Exception:
                continue
            for item in channel.list_bindings():
                if str(item.get("quest_id") or "").strip() != quest_id:
                    continue
                conversation_id = str(item.get("conversation_id") or "").strip()
                if not conversation_id:
                    continue
                if preserve_keys and conversation_identity_key(conversation_id) in preserve_keys:
                    continue
                if channel.unbind_conversation(conversation_id, quest_id=quest_id):
                    removed.append(conversation_id)
                    self.sessions.unbind(quest_id, conversation_id)
        for conversation_id in removed:
            self.quest_service.unbind_source(quest_id, conversation_id)
        return removed

    def _format_projects_list(self) -> str:
        quests = self.quest_service.list_quests()
        if not quests:
            return self._polite_copy(
                zh="当前还没有 quest。可以发送 `/new <goal>` 来创建一个新的 quest。",
                en="There is no quest yet. Use `/new <goal>` to create one.",
            )
        lines = [
            self._polite_copy(
                zh="最近的 quest 如下：",
                en="Recent quests:",
            )
        ]
        for item in quests[:6]:
            lines.append(
                f"- `{item['quest_id']}` · {item.get('title') or item['quest_id']} · {item.get('status') or 'active'}"
            )
        lines.append(
            self._polite_copy(
                zh="发送 `/use <quest_id>`、`/use latest`、`/projects` 或 `/list` 可以继续。",
                en="Use `/use <quest_id>`, `/use latest`, `/projects`, or `/list` to continue.",
            )
        )
        return "\n".join(lines)

    def _channel_with_bindings(self, name: str):
        channel = self.channels.get(name)
        if channel is None:
            raise KeyError(f"Unknown connector `{name}`.")
        for attr in (
            "ingest",
            "bind_conversation",
            "unbind_conversation",
            "resolve_bound_quest",
            "list_bindings",
            "command_prefix",
        ):
            if not hasattr(channel, attr):
                raise TypeError(f"Connector `{name}` does not implement `{attr}`.")
        return channel

    @staticmethod
    def _connector_label(name: str) -> str:
        normalized = (name or "").strip().lower()
        if normalized == "qq":
            return "QQ"
        if normalized == "feishu":
            return "Feishu"
        if normalized == "whatsapp":
            return "WhatsApp"
        return normalized.title() or "Connector"

    @staticmethod
    def _parse_prefixed_command(text: str, prefix: str) -> tuple[str, list[str]]:
        stripped = text[len(prefix):].strip()
        if not stripped:
            return "", []
        parts = stripped.split()
        return parts[0].lower(), parts[1:]

    @staticmethod
    def _parse_lingzhu_short_command(text: str) -> tuple[str, list[str]] | None:
        normalized = lingzhu_normalize_command_text(text)
        if not normalized or normalized.startswith("/"):
            return None
        direct = _LINGZHU_SHORT_COMMAND_DIRECT_MAP.get(normalized)
        if direct:
            return direct, []
        for prefix, command_name in _LINGZHU_SHORT_COMMAND_PREFIX_MAP.items():
            if not normalized.startswith(prefix):
                continue
            remainder = normalized[len(prefix) :].strip().lstrip("：:，,。.;；!！?？ ")
            if command_name == "new":
                return command_name, [remainder] if remainder else []
            if command_name == "delete":
                matched = re.match(r"^(?P<target>\S+)?(?:\s+(?P<confirm>\S+))?$", remainder)
                target = str((matched.group("target") if matched else "") or "").strip()
                confirm = str((matched.group("confirm") if matched else "") or "").strip()
                args: list[str] = []
                if target:
                    args.append("latest" if target in _LINGZHU_SHORT_LATEST_ALIASES else target)
                if confirm in _LINGZHU_DELETE_CONFIRM_ALIASES:
                    args.append("--yes")
                return command_name, args
            if remainder:
                return command_name, ["latest" if remainder in _LINGZHU_SHORT_LATEST_ALIASES else remainder]
            return command_name, []
        return None

    def _lingzhu_status_hint_text(self, quest_id: str | None) -> str:
        if not quest_id:
            latest = str(self._latest_quest_id() or "").strip()
            bind_hint = f"绑定{latest}" if latest else "绑定最新"
            return f"未绑定。可说：{bind_hint}/列表/帮助"
        snapshot = self.quest_service.snapshot(quest_id)
        runtime_status = str(snapshot.get("runtime_status") or snapshot.get("status") or "").strip().lower()
        latest = str(self._latest_quest_id() or "").strip()
        bind_hint = f"绑定{latest}" if latest and latest != quest_id else "绑定最新"
        if runtime_status in {"running", "active"}:
            return f"绑{quest_id}，进行中。可说：状态/总结/{bind_hint}"
        if runtime_status == "waiting_for_user":
            return f"绑{quest_id}，等你确认。可说：状态/总结/{bind_hint}"
        if runtime_status in {"paused", "stopped"}:
            return f"绑{quest_id}，已暂停。可说：恢复/{bind_hint}/列表"
        if runtime_status == "completed":
            return f"绑{quest_id}，已完成。可说：总结/{bind_hint}/列表"
        if runtime_status == "error":
            return f"绑{quest_id}，出错了。可说：状态/恢复/{bind_hint}"
        return f"绑{quest_id}，暂无新进展。可说：状态/总结/{bind_hint}"

    def _lingzhu_unbound_help_text(self) -> str:
        latest = str(self._latest_quest_id() or "none")
        return (
            "当前还没绑定 Quest。\n"
            "可直接说：帮助、列表、绑定025、绑定最新、新建 复现一个 baseline。\n"
            f"当前最新 Quest：`{latest}`。\n"
            "绑定后再说：我现在的任务是 ……\n"
            "查看进展可说：继续 或 汇报。\n"
            "快捷指令：状态、总结、暂停、恢复、删除025。"
        )

    def _maybe_bind_qq_main_chat(self, message: dict) -> dict | None:
        chat_type = str(message.get("chat_type") or "").strip().lower()
        if chat_type != "direct":
            return None
        profile_id = str(message.get("profile_id") or "").strip() or None
        chat_id = str(message.get("chat_id") or message.get("direct_id") or "").strip()
        if not chat_id:
            parsed = parse_conversation_id(message.get("conversation_id"))
            if parsed is not None and str(parsed.get("connector") or "").strip().lower() == "qq":
                chat_id = str(parsed.get("chat_id") or "").strip()
                profile_id = str(parsed.get("profile_id") or "").strip() or profile_id
        if not chat_id:
            return None
        result = self.config_manager.bind_qq_main_chat(profile_id=profile_id, chat_id=chat_id)
        if not result.get("ok"):
            self.logger.log(
                "warning",
                "connector.qq_main_chat_bind_failed",
                chat_id=chat_id,
                profile_id=profile_id,
                errors=result.get("errors") or [],
            )
            return None
        if not result.get("saved"):
            return None
        self.reload_connectors_config(restart_background=False)
        return {
            "chat_id": chat_id,
            "profile_id": result.get("profile_id"),
            "profile_label": result.get("profile_label"),
            "saved_at": result.get("saved_at"),
        }

    def _with_qq_main_chat_notice(self, message: dict, base: str) -> str:
        binding = message.get("_qq_main_chat_binding")
        if not isinstance(binding, dict):
            return base
        chat_id = str(binding.get("chat_id") or "").strip()
        if not chat_id:
            return base
        profile_label = str(binding.get("profile_label") or "").strip()
        notice = self._polite_copy(
            zh=(
                f"已自动检测并保存当前 QQ openid：`{chat_id}`。"
                f"{f'当前 bot：{profile_label}。' if profile_label else ''}您现在可以在 settings 页面看到这个绑定结果。"
            ),
            en=(
                f"I automatically detected and saved this QQ openid: `{chat_id}`. "
                f"{f'Current bot: {profile_label}. ' if profile_label else ''}"
                "You can now see the binding in settings."
            ),
        )
        return f"{notice}\n\n{base}"

    def _connector_goal_preview(self, goal: str, *, limit: int = 88) -> str:
        for raw_line in str(goal or "").replace("\r", "\n").split("\n"):
            line = re.sub(r"^[#>*\-\d\.)\s]+", "", raw_line).strip()
            if not line:
                continue
            normalized = re.sub(r"\s+", " ", line).strip()
            if len(normalized) <= limit:
                return normalized
            return normalized[: max(0, limit - 3)].rstrip() + "..."
        return self._polite_copy(
            zh="我会先把当前任务整理清楚，再继续推进。",
            en="I will clarify the current task first, then keep moving. ✨",
        )

    def _connector_runner_label(self, runner_name: str) -> str:
        normalized = str(runner_name or "codex").strip().lower() or "codex"
        if normalized == "claude":
            return "Claude Code"
        if normalized == "opencode":
            return "Open Code"
        try:
            metadata = get_runner_metadata(normalized)
        except Exception:
            return runner_name or "Codex"
        return str(metadata.label or runner_name or "Codex")

    def _connector_runner_readiness(self, runner_name: str) -> dict[str, Any]:
        try:
            state = self.config_manager.runner_bootstrap_state(runner_name)
        except Exception:
            return {"runner": runner_name, "ready": True, "last_result": {}}
        if not isinstance(state, dict):
            return {"runner": runner_name, "ready": True, "last_result": {}}
        return state

    def _connector_turn_start_message(
        self,
        *,
        quest_id: str,
        startup: dict[str, Any],
        snapshot: dict[str, Any],
    ) -> str:
        runner_name = self._runner_name_for(snapshot)
        runner_label = self._connector_runner_label(runner_name)
        readiness = self._connector_runner_readiness(runner_name)
        readiness_result = readiness.get("last_result") if isinstance(readiness.get("last_result"), dict) else {}
        readiness_summary = str(readiness_result.get("summary") or "").strip()
        readiness_errors = [str(item).strip() for item in (readiness_result.get("errors") or []) if str(item).strip()]
        readiness_guidance = [str(item).strip() for item in (readiness_result.get("guidance") or []) if str(item).strip()]
        ready = bool(readiness.get("ready", True))
        reason = str(startup.get("reason") or "").strip().lower()
        started = bool(startup.get("started"))
        queued = bool(startup.get("queued"))
        auto_resumed = bool(startup.get("auto_resumed"))
        has_explicit_runner_failure = bool(readiness_summary or readiness_errors or readiness_guidance)
        if reason == "stalled_turn_recovery_pending":
            return self._polite_copy(
                zh=f"正在启动 DeepScientist，当前会先恢复 `{quest_id}` 里停滞的运行，再继续处理您的新消息。",
                en=f"DeepScientist is starting up. I’m recovering the stalled run in `{quest_id}` first, then I’ll continue with your new message.",
            )
        if not ready and has_explicit_runner_failure:
            status_line = f" 当前状态：{readiness_summary}" if readiness_summary else ""
            return self._polite_copy(
                zh=(
                    f"DeepScientist 仍然不在线哟，请检查你所绑定的{runner_label}是否能够顺利连接。{status_line}"
                ),
                en=(
                    f"DeepScientist is still offline. Please check whether the bound {runner_label} can connect normally."
                    f"{(' Current status: ' + readiness_summary) if readiness_summary else ''}"
                ),
            )
        if started or auto_resumed:
            return self._polite_copy(
                zh=f"已经成功收到消息，DeepScientist 已经启动并开始处理 `{quest_id}` 啦。",
                en=f"Message received successfully. DeepScientist has started and is now processing `{quest_id}`.",
            )
        if queued:
            return self._polite_copy(
                zh=f"已经成功收到消息，`{quest_id}` 当前正在运行中，这条消息也已经排进队列了。",
                en=f"Message received successfully. `{quest_id}` is already running, and this message has been queued.",
            )
        return self._polite_copy(
            zh=f"已经成功收到消息，我会继续推进 `{quest_id}` 并同步后续进展。",
            en=f"Message received successfully. I’ll continue `{quest_id}` and keep you updated.",
        )

    def _quest_created_connector_message(
        self,
        connector_name: str,
        *,
        quest_id: str,
        goal: str,
        previous_quest_id: str | None = None,
    ) -> str:
        previous = str(previous_quest_id or "").strip()
        goal_preview = self._connector_goal_preview(goal)
        restore_zh = (
            f"\n如果想切回原先的 Quest `{previous}`，给我发 `/use {previous}` 就行。"
            if previous and previous != quest_id
            else ""
        )
        restore_en = (
            f"\nIf you want to switch back to Quest `{previous}`, send `/use {previous}`. 🔁"
            if previous and previous != quest_id
            else ""
        )
        return self._polite_copy(
            zh=(
                f"开工啦！新的 Quest `{quest_id}` 已经建好啦。\n"
                f"这轮我先做这件事：{goal_preview}\n"
                f"后面的进展我都会直接在这里同步给您。"
            )
            + restore_zh,
            en=(
                f"Quest `{quest_id}` is ready, and I’m starting now. 🚀\n"
                f"Current focus: {goal_preview}\n"
                f"I’ll keep the next updates right here."
            )
            + restore_en,
        )

    def _profiled_connector_configs(self, connector_name: str) -> list[tuple[str, str | None, dict[str, Any]]]:
        if not self._is_connector_system_enabled(connector_name):
            return []
        connector_config = self.connectors_config.get(connector_name, {})
        if not isinstance(connector_config, dict):
            return []
        profiles = list_connector_profiles(connector_name, connector_config)
        encode_profile_id = len(profiles) > 1
        items: list[tuple[str, str | None, dict[str, Any]]] = []
        for profile in profiles:
            profile_id = str(profile.get("profile_id") or "").strip()
            if not profile_id:
                continue
            merged = merge_connector_profile_config(connector_name, connector_config, profile)
            merged["encode_profile_id"] = encode_profile_id
            items.append((profile_id, connector_profile_label(connector_name, profile), merged))
        return items

    def _start_background_connectors(self) -> None:
        qq_config = self.connectors_config.get("qq", {})
        if self._is_connector_system_enabled("qq") and isinstance(qq_config, dict) and not self._qq_gateways:
            profiles = list_qq_profiles(qq_config)
            encode_profile_id = len(profiles) > 1
            for profile in profiles:
                profile_id = str(profile.get("profile_id") or "").strip()
                profile_config = merge_qq_profile_config(qq_config, profile)
                profile_config["encode_profile_id"] = encode_profile_id
                gateway = QQGatewayService(
                    home=self.home,
                    config=profile_config,
                    on_event=lambda event: self.handle_connector_inbound("qq", event),
                    log=lambda level, message, _profile_id=profile_id: self.logger.log(
                        level,
                        "connector.qq_gateway",
                        profile_id=_profile_id,
                        message=message,
                    ),
                )
                if gateway.start():
                    self._qq_gateways[profile_id] = gateway
        weixin_config = self.connectors_config.get("weixin", {})
        if self._is_connector_system_enabled("weixin") and isinstance(weixin_config, dict) and self._weixin_ilink is None:
            weixin = WeixinIlinkService(
                home=self.home,
                config=weixin_config,
                on_event=lambda event: self.handle_connector_inbound("weixin", event),
                log=lambda level, message: self.logger.log(
                    level,
                    "connector.weixin_ilink",
                    message=message,
                ),
            )
            if weixin.start():
                self._weixin_ilink = weixin
        if self._is_connector_system_enabled("telegram") and not self._telegram_polling:
            for profile_id, profile_label, profile_config in self._profiled_connector_configs("telegram"):
                polling = TelegramPollingService(
                    home=self.home,
                    config=profile_config,
                    on_event=lambda event: self.handle_connector_inbound("telegram", event),
                    log=lambda level, message, _profile_id=profile_id: self.logger.log(
                        level,
                        "connector.telegram_polling",
                        profile_id=_profile_id,
                        message=message,
                    ),
                    profile_id=profile_id,
                    profile_label=profile_label,
                    encode_profile_id=bool(profile_config.get("encode_profile_id")),
                )
                if polling.start():
                    self._telegram_polling[profile_id] = polling
        if self._is_connector_system_enabled("slack") and not self._slack_socket:
            for profile_id, profile_label, profile_config in self._profiled_connector_configs("slack"):
                slack = SlackSocketModeService(
                    home=self.home,
                    config=profile_config,
                    on_event=lambda event: self.handle_connector_inbound("slack", event),
                    log=lambda level, message, _profile_id=profile_id: self.logger.log(
                        level,
                        "connector.slack_socket",
                        profile_id=_profile_id,
                        message=message,
                    ),
                    profile_id=profile_id,
                    profile_label=profile_label,
                    encode_profile_id=bool(profile_config.get("encode_profile_id")),
                )
                if slack.start():
                    self._slack_socket[profile_id] = slack
        if self._is_connector_system_enabled("discord") and not self._discord_gateway:
            for profile_id, profile_label, profile_config in self._profiled_connector_configs("discord"):
                discord = DiscordGatewayService(
                    home=self.home,
                    config=profile_config,
                    on_event=lambda event: self.handle_connector_inbound("discord", event),
                    log=lambda level, message, _profile_id=profile_id: self.logger.log(
                        level,
                        "connector.discord_gateway",
                        profile_id=_profile_id,
                        message=message,
                    ),
                    profile_id=profile_id,
                    profile_label=profile_label,
                    encode_profile_id=bool(profile_config.get("encode_profile_id")),
                )
                if discord.start():
                    self._discord_gateway[profile_id] = discord
        if self._is_connector_system_enabled("feishu") and not self._feishu_long_connection:
            for profile_id, profile_label, profile_config in self._profiled_connector_configs("feishu"):
                feishu = FeishuLongConnectionService(
                    home=self.home,
                    config=profile_config,
                    on_event=lambda event: self.handle_connector_inbound("feishu", event),
                    log=lambda level, message, _profile_id=profile_id: self.logger.log(
                        level,
                        "connector.feishu_long_connection",
                        profile_id=_profile_id,
                        message=message,
                    ),
                    profile_id=profile_id,
                    profile_label=profile_label,
                    encode_profile_id=bool(profile_config.get("encode_profile_id")),
                )
                if feishu.start():
                    self._feishu_long_connection[profile_id] = feishu
        if self._is_connector_system_enabled("whatsapp") and not self._whatsapp_local_session:
            for profile_id, profile_label, profile_config in self._profiled_connector_configs("whatsapp"):
                whatsapp = WhatsAppLocalSessionService(
                    home=self.home,
                    config=profile_config,
                    on_event=lambda event: self.handle_connector_inbound("whatsapp", event),
                    log=lambda level, message, _profile_id=profile_id: self.logger.log(
                        level,
                        "connector.whatsapp_local_session",
                        profile_id=_profile_id,
                        message=message,
                    ),
                    profile_id=profile_id,
                    profile_label=profile_label,
                    encode_profile_id=bool(profile_config.get("encode_profile_id")),
                )
                if whatsapp.start():
                    self._whatsapp_local_session[profile_id] = whatsapp

    def _stop_background_connectors(self) -> None:
        gateways = list(self._qq_gateways.values())
        self._qq_gateways = {}
        for gateway in gateways:
            gateway.stop()
        weixin = self._weixin_ilink
        self._weixin_ilink = None
        if weixin is not None:
            weixin.stop()
        polling = list(self._telegram_polling.values())
        self._telegram_polling = {}
        for item in polling:
            item.stop()
        slack = list(self._slack_socket.values())
        self._slack_socket = {}
        for item in slack:
            item.stop()
        discord = list(self._discord_gateway.values())
        self._discord_gateway = {}
        for item in discord:
            item.stop()
        feishu = list(self._feishu_long_connection.values())
        self._feishu_long_connection = {}
        for item in feishu:
            item.stop()
        whatsapp = list(self._whatsapp_local_session.values())
        self._whatsapp_local_session = {}
        for item in whatsapp:
            item.stop()

    @staticmethod
    def _format_status(snapshot: dict) -> str:
        latest_metric = (snapshot.get("summary") or {}).get("latest_metric")
        pending = snapshot.get("pending_decisions") or []
        counts = snapshot.get("counts") or {}
        bound_conversations = snapshot.get("bound_conversations") or []
        lines = [
            f"Quest {snapshot.get('quest_id')}",
            "Quest Status",
            f"- quest_id: {snapshot.get('quest_id')}",
            f"- title: {snapshot.get('title')}",
            f"- status: {snapshot.get('status')}",
            f"- anchor: {snapshot.get('active_anchor')}",
            f"- runner: {snapshot.get('runner')}",
            f"- branch: {snapshot.get('branch')}",
            f"- active_run_id: {snapshot.get('active_run_id') or 'none'}",
            f"- quest_root: {snapshot.get('quest_root')}",
            f"- updated_at: {snapshot.get('updated_at')}",
            f"- history_count: {snapshot.get('history_count')}",
            f"- artifact_count: {snapshot.get('artifact_count')}",
            f"- memory_cards: {counts.get('memory_cards', 0)}",
            f"- pending_decisions: {len(pending)}",
            f"- bound_conversations: {', '.join(str(item) for item in bound_conversations) if bound_conversations else 'none'}",
        ]
        status_line = ((snapshot.get("summary") or {}).get("status_line") or "").strip()
        if status_line:
            lines.append(f"- summary: {status_line}")
        if isinstance(latest_metric, dict) and latest_metric.get("key"):
            lines.append(f"- latest_metric: {latest_metric.get('key')} = {latest_metric.get('value')}")
        if pending:
            lines.append(f"- pending_decision_ids: {', '.join(str(item) for item in pending[:8])}")
        return "\n".join(lines)

    def _format_summary(self, quest_id: str) -> str:
        snapshot = self.quest_service.snapshot(quest_id)
        title = str(snapshot.get("title") or "").strip()
        status = str(snapshot.get("runtime_status") or snapshot.get("status") or "").strip()
        summary = read_text(self.home / "quests" / quest_id / "SUMMARY.md").strip()
        header_lines = [f"quest_id: {quest_id}"]
        if title and title != quest_id:
            header_lines.append(f"title: {title}")
        if status:
            header_lines.append(f"status: {status}")
        if not summary:
            header_lines.append("summary: No summary has been written yet.")
            return "\n".join(header_lines)
        header = "\n".join(header_lines)
        remaining = max(0, 1800 - len(header) - 2)
        return f"{header}\n\n{summary[:remaining]}"

    def _format_metrics(self, quest_id: str, *, run_id: str | None = None) -> str:
        quest_root = self.home / "quests" / quest_id
        run_paths = sorted((quest_root / "artifacts" / "runs").glob("*.json"))
        if not run_paths:
            snapshot = self.quest_service.snapshot(quest_id)
            latest_metric = (snapshot.get("summary") or {}).get("latest_metric")
            if isinstance(latest_metric, dict) and latest_metric.get("key"):
                return f"{latest_metric.get('key')} = {latest_metric.get('value')}"
            return "No metrics are available yet."
        matches = []
        for path in run_paths:
            payload = read_json(path, {})
            if run_id and payload.get("run_id") != run_id:
                continue
            matches.append(payload)
        if not matches:
            return f"No run metrics found for `{run_id}`."
        latest = matches[-1]
        metrics = latest.get("metrics") or latest.get("metrics_summary") or {}
        if isinstance(metrics, dict) and metrics:
            compact = ", ".join(f"{key}={value}" for key, value in list(metrics.items())[:6])
            return f"{latest.get('run_id') or latest.get('artifact_id')}: {compact}"
        summary = str(latest.get("summary") or "No structured metrics were recorded.")
        return f"{latest.get('run_id') or latest.get('artifact_id')}: {summary}"

    @staticmethod
    def _format_graph_reply(quest_id: str, graph: dict) -> str:
        branch = graph.get("branch")
        head = graph.get("head")
        lines = graph.get("lines") or []
        return (
            f"Git graph refreshed for {quest_id}.\n"
            f"Branch: {branch}\n"
            f"Head: {head}\n"
            f"Recent commits: {min(len(lines), 8)} shown in the attached graph."
        )

    def _wants_event_stream(self, path: str, headers: dict[str, str]) -> bool:
        query = self.handlers.parse_query(path)
        stream_value = ((query.get("stream") or [""])[0] or "").strip().lower()
        accept = str(headers.get("Accept") or headers.get("accept") or "").lower()
        return stream_value in {"1", "true", "yes", "stream"} or "text/event-stream" in accept

    def lingzhu_health_payload(self) -> dict[str, Any]:
        config = self.connectors_config.get("lingzhu")
        resolved = dict(config) if isinstance(config, dict) else {}
        return lingzhu_health_payload(resolved, chat_completions_enabled=True)

    @staticmethod
    def _weixin_replay_limit(config: dict[str, Any]) -> int:
        try:
            limit = int(config.get("stale_replay_latest_limit") or _WEIXIN_STALE_REPLAY_LIMIT_DEFAULT)
        except (TypeError, ValueError):
            limit = _WEIXIN_STALE_REPLAY_LIMIT_DEFAULT
        return max(0, min(limit, 20))

    @staticmethod
    def _weixin_replay_interval_seconds(config: dict[str, Any]) -> float:
        try:
            interval = float(
                config.get("stale_replay_interval_seconds") or _WEIXIN_STALE_REPLAY_INTERVAL_SECONDS_DEFAULT
            )
        except (TypeError, ValueError):
            interval = _WEIXIN_STALE_REPLAY_INTERVAL_SECONDS_DEFAULT
        return max(0.0, min(interval, 30.0))

    def _weixin_connector_root(self) -> Path:
        return self.home / "logs" / "connectors" / "weixin"

    def _weixin_queued_outbox_records(self, conversation_id: str) -> list[dict[str, Any]]:
        outbox_path = self._weixin_connector_root() / "outbox.jsonl"
        target_key = conversation_identity_key(conversation_id)
        items: list[dict[str, Any]] = []
        for record in read_jsonl(outbox_path):
            if not isinstance(record, dict):
                continue
            current_conversation_id = str(record.get("conversation_id") or "").strip()
            if not current_conversation_id:
                continue
            if conversation_identity_key(current_conversation_id) != target_key:
                continue
            delivery = record.get("delivery") if isinstance(record.get("delivery"), dict) else {}
            if not bool(delivery.get("queued", False)):
                continue
            attachments = [dict(item) for item in (record.get("attachments") or []) if isinstance(item, dict)]
            if not str(record.get("text") or "").strip() and not attachments:
                continue
            items.append(
                {
                    **dict(record),
                    "attachments": attachments,
                }
            )
        return items

    def _weixin_pending_outbox_records(self, conversation_id: str, *, user_id: str) -> tuple[list[dict[str, Any]], int]:
        records = self._weixin_queued_outbox_records(conversation_id)
        baseline = get_weixin_replay_cursor(self._weixin_connector_root(), user_id)
        applied_baseline = max(0, min(int(baseline), len(records)))
        return records[applied_baseline:], len(records)

    @staticmethod
    def _weixin_replay_payload(record: dict[str, Any]) -> dict[str, Any]:
        attachments = [dict(item) for item in (record.get("attachments") or []) if isinstance(item, dict)]
        surface_actions = [dict(item) for item in (record.get("surface_actions") or []) if isinstance(item, dict)]
        connector_hints = dict(record.get("connector_hints")) if isinstance(record.get("connector_hints"), dict) else {}
        return {
            "conversation_id": record.get("conversation_id"),
            "reply_to_message_id": record.get("reply_to_message_id"),
            "kind": record.get("kind"),
            "message": str(record.get("text") or ""),
            "attachments": attachments,
            "surface_actions": surface_actions,
            "connector_hints": connector_hints,
            "quest_id": record.get("quest_id"),
            "quest_root": record.get("quest_root"),
            "importance": record.get("importance"),
            "response_phase": record.get("response_phase"),
        }

    def _maybe_replay_weixin_pending_outbox(self, message: dict[str, Any]) -> dict[str, Any] | None:
        conversation_id = str(message.get("conversation_id") or "").strip()
        sender_id = str(message.get("sender_id") or message.get("direct_id") or "").strip()
        if not conversation_id or not sender_id:
            return None
        config = self.connectors_config.get("weixin", {})
        resolved = dict(config) if isinstance(config, dict) else {}
        limit = self._weixin_replay_limit(resolved)
        if limit <= 0:
            return {"replayed_count": 0, "dropped_count": 0, "total_pending": 0}
        pending_records, total_count = self._weixin_pending_outbox_records(conversation_id, user_id=sender_id)
        if not pending_records:
            return {"replayed_count": 0, "dropped_count": 0, "total_pending": 0}
        selected_records = pending_records[-limit:]
        dropped_count = max(0, len(pending_records) - len(selected_records))
        update_weixin_replay_cursor(
            self._weixin_connector_root(),
            user_id=sender_id,
            queued_replay_cursor=total_count,
            last_replay_trigger_message_id=str(message.get("message_id") or "").strip() or None,
            last_replayed_count=len(selected_records),
            last_replay_dropped_count=dropped_count,
        )
        channel = self._channel_with_bindings("weixin")
        interval_seconds = self._weixin_replay_interval_seconds(resolved)
        for index, record in enumerate(selected_records):
            channel.send(self._weixin_replay_payload(record))
            if index + 1 < len(selected_records) and interval_seconds > 0:
                time.sleep(interval_seconds)
        self.logger.log(
            "info",
            "connector.weixin_replay",
            conversation_id=conversation_id,
            replayed_count=len(selected_records),
            dropped_count=dropped_count,
            trigger_message_id=str(message.get("message_id") or "").strip() or None,
        )
        return {
            "replayed_count": len(selected_records),
            "dropped_count": dropped_count,
            "total_pending": len(pending_records),
        }

    def _lingzhu_state_path(self) -> Path:
        return self.home / "logs" / "connectors" / "lingzhu" / "metis_state.json"

    def _read_lingzhu_state(self) -> dict[str, Any]:
        payload = read_json(self._lingzhu_state_path(), {"delivered_counts": {}})
        if not isinstance(payload, dict):
            payload = {}
        delivered_counts = payload.get("delivered_counts")
        if not isinstance(delivered_counts, dict):
            delivered_counts = {}
        return {"delivered_counts": delivered_counts}

    def _write_lingzhu_state(self, payload: dict[str, Any]) -> None:
        path = self._lingzhu_state_path()
        ensure_dir(path.parent)
        write_json(path, payload)

    def _lingzhu_delivered_count(self, conversation_id: str) -> int:
        delivered_counts = self._read_lingzhu_state().get("delivered_counts") or {}
        raw_value = delivered_counts.get(conversation_identity_key(conversation_id))
        try:
            return max(0, int(raw_value))
        except (TypeError, ValueError):
            return 0

    def _set_lingzhu_delivered_count(self, conversation_id: str, delivered_count: int) -> None:
        state = self._read_lingzhu_state()
        counts = dict(state.get("delivered_counts") or {})
        counts[conversation_identity_key(conversation_id)] = max(0, int(delivered_count))
        state["delivered_counts"] = counts
        self._write_lingzhu_state(state)

    def _lingzhu_outbox_records(self, conversation_id: str) -> list[dict[str, Any]]:
        outbox_path = self.home / "logs" / "connectors" / "lingzhu" / "outbox.jsonl"
        target_key = conversation_identity_key(conversation_id)
        items: list[dict[str, Any]] = []
        for record in read_jsonl(outbox_path):
            if not isinstance(record, dict):
                continue
            current_conversation_id = str(record.get("conversation_id") or "").strip()
            if not current_conversation_id:
                continue
            if conversation_identity_key(current_conversation_id) != target_key:
                continue
            text = str(record.get("text") or "").strip()
            if not text:
                continue
            items.append(dict(record))
        return items

    def _lingzhu_pending_outbox_records(
        self,
        conversation_id: str,
        *,
        delivered_count: int | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        records = self._lingzhu_outbox_records(conversation_id)
        baseline = self._lingzhu_delivered_count(conversation_id) if delivered_count is None else delivered_count
        applied_baseline = max(0, min(int(baseline), len(records)))
        return records[applied_baseline:], len(records)

    @staticmethod
    def _lingzhu_wait_timeout_seconds(config: dict[str, Any]) -> float:
        try:
            timeout_ms = int(config.get("request_timeout_ms") or 60000)
        except (TypeError, ValueError):
            timeout_ms = 60000
        timeout_ms = max(15000, min(timeout_ms, 120000))
        return timeout_ms / 1000.0

    def _lingzhu_wait_for_outbox_records(
        self,
        conversation_id: str,
        *,
        delivered_count: int,
        timeout_seconds: float,
    ) -> tuple[list[dict[str, Any]], int]:
        deadline = time.monotonic() + max(0.1, timeout_seconds)
        while time.monotonic() < deadline:
            pending_records, total_count = self._lingzhu_pending_outbox_records(
                conversation_id,
                delivered_count=delivered_count,
            )
            if pending_records:
                return pending_records, total_count
            time.sleep(0.25)
        return self._lingzhu_pending_outbox_records(conversation_id, delivered_count=delivered_count)

    def _lingzhu_emit_outbox_records(
        self,
        handler: BaseHTTPRequestHandler,
        *,
        message_id: str,
        agent_id: str,
        records: list[dict[str, Any]],
        config: dict[str, Any] | None = None,
    ) -> int:
        emitted = 0
        resolved = dict(config or {})
        default_navigation_mode = str(resolved.get("default_navigation_mode") or "0").strip() or "0"
        experimental_enabled = bool(resolved.get("enable_experimental_native_actions", False))
        for record in records:
            raw_text = str(record.get("text") or "").strip()
            detected_tool_call = None
            text = raw_text
            if raw_text:
                detected_tool_call, text = lingzhu_detect_tool_call_from_text(
                    raw_text,
                    default_navigation_mode=default_navigation_mode,
                    experimental_enabled=experimental_enabled,
                )
            if text:
                self._write_sse_event(
                    handler,
                    event="message",
                    data=lingzhu_sse_answer(
                        message_id=message_id,
                        agent_id=agent_id,
                        answer_stream=text,
                        is_finish=True,
                    ),
                )
                emitted += 1
            emitted_tool_call = False
            for action in record.get("surface_actions") or []:
                tool_call = lingzhu_surface_action_tool_call(
                    action,
                    default_navigation_mode=default_navigation_mode,
                    experimental_enabled=experimental_enabled,
                )
                if not tool_call:
                    continue
                self._write_sse_event(
                    handler,
                    event="message",
                    data=lingzhu_sse_tool_call(
                        message_id=message_id,
                        agent_id=agent_id,
                        tool_call=tool_call,
                        is_finish=True,
                    ),
                )
                emitted += 1
                emitted_tool_call = True
            if not emitted_tool_call and detected_tool_call:
                self._write_sse_event(
                    handler,
                    event="message",
                    data=lingzhu_sse_tool_call(
                        message_id=message_id,
                        agent_id=agent_id,
                        tool_call=detected_tool_call,
                        is_finish=True,
                    ),
                )
                emitted += 1
        return emitted

    def _lingzhu_short_status_text(self, quest_id: str | None) -> str:
        normalized_quest_id = str(quest_id or "").strip()
        if normalized_quest_id:
            snapshot = self.quest_service.snapshot_fast(normalized_quest_id)
            runtime_status = str(snapshot.get("runtime_status") or snapshot.get("status") or "").strip().lower()
            if runtime_status in {"running", "active"}:
                return "进行中"
            return self._lingzhu_status_hint_text(normalized_quest_id)
        return self._lingzhu_status_hint_text(quest_id)

    @staticmethod
    def _lingzhu_reply_payload(result: dict[str, Any]) -> tuple[str, str | None, str]:
        if not isinstance(result, dict):
            return "", None, ""
        reply = result.get("reply")
        if not isinstance(reply, dict):
            return "", None, ""
        payload = reply.get("payload")
        if not isinstance(payload, dict):
            return "", None, ""
        text = str(payload.get("text") or payload.get("message") or "").strip()
        quest_id = str(payload.get("quest_id") or "").strip() or None
        kind = str(payload.get("kind") or "").strip()
        return text, quest_id, kind

    def stream_lingzhu_sse(
        self,
        handler: BaseHTTPRequestHandler,
        *,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> None:
        config = self.connectors_config.get("lingzhu")
        resolved = dict(config) if isinstance(config, dict) else {}
        if resolved.get("enabled") is False:
            handler.send_response(503)
            handler.send_header("Content-Type", "application/json; charset=utf-8")
            handler.end_headers()
            handler.wfile.write(json.dumps({"error": "Lingzhu connector is disabled"}, ensure_ascii=False).encode("utf-8"))
            return

        auth_ak = self.config_manager._secret(resolved, "auth_ak", "auth_ak_env")
        auth_header = headers.get("Authorization") or headers.get("authorization") or ""
        if not lingzhu_verify_auth_header(auth_header, auth_ak):
            handler.send_response(401)
            handler.send_header("Content-Type", "application/json; charset=utf-8")
            handler.end_headers()
            handler.wfile.write(json.dumps({"error": "Unauthorized"}, ensure_ascii=False).encode("utf-8"))
            return

        try:
            body = self.handlers.parse_body(raw_body)
        except Exception:
            handler.send_response(400)
            handler.send_header("Content-Type", "application/json; charset=utf-8")
            handler.end_headers()
            handler.wfile.write(json.dumps({"error": "Invalid JSON body"}, ensure_ascii=False).encode("utf-8"))
            return

        if not isinstance(body, dict):
            handler.send_response(400)
            handler.send_header("Content-Type", "application/json; charset=utf-8")
            handler.end_headers()
            handler.wfile.write(json.dumps({"error": "Request body must be a JSON object"}, ensure_ascii=False).encode("utf-8"))
            return

        message_id = str(body.get("message_id") or body.get("request_id") or generate_id("lingzhu")).strip()
        agent_id = str(body.get("agent_id") or resolved.get("agent_id") or "main").strip() or "main"
        messages = body.get("message")
        if not isinstance(messages, list):
            messages = body.get("messages")
        if not isinstance(messages, list):
            text = str(body.get("text") or body.get("content") or "").strip()
            messages = [{"role": "user", "type": "text", "text": text}] if text else None
        if not isinstance(messages, list):
            handler.send_response(400)
            handler.send_header("Content-Type", "application/json; charset=utf-8")
            handler.end_headers()
            handler.wfile.write(
                json.dumps({"error": "Missing required fields: message or messages"}, ensure_ascii=False).encode("utf-8")
            )
            return

        conversation_id = lingzhu_request_conversation_id(body)
        binding_conversation_id = self._logical_connector_binding_conversation("lingzhu", conversation_id)
        sender_id = lingzhu_request_sender_id(body)
        inbound_text = lingzhu_extract_user_text(messages) or self._polite_copy(
            zh="你好，请继续。",
            en="Hello, please continue.",
        )
        channel = self._channel_with_bindings("lingzhu")
        known_quest_id = self._resolve_lingzhu_bound_quest(conversation_id)
        delivered_count = self._lingzhu_delivered_count(conversation_id)
        task_text = lingzhu_extract_task_text(inbound_text)
        is_command = inbound_text.startswith(channel.command_prefix()) or self._parse_lingzhu_short_command(inbound_text) is not None

        inbound_payload = {
            "conversation_id": conversation_id,
            "chat_type": "direct",
            "message_id": message_id,
            "sender_id": sender_id,
            "sender_name": sender_id,
            "user_id": sender_id,
            "direct_id": sender_id,
            "text": inbound_text,
            "message": inbound_text,
            "content": inbound_text,
            "raw_event": body,
            "metadata": body.get("metadata"),
        }

        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "close")
        handler.send_header("X-Accel-Buffering", "no")
        handler.end_headers()

        try:
            handler.wfile.write(b": keepalive\n\n")
            handler.wfile.flush()

            if is_command:
                result = self.handle_connector_inbound("lingzhu", inbound_payload)
                reply_text, _, _ = self._lingzhu_reply_payload(result)
                pending_records, total_count = self._lingzhu_pending_outbox_records(
                    conversation_id,
                    delivered_count=delivered_count,
                )
                emitted = self._lingzhu_emit_outbox_records(
                    handler,
                    message_id=message_id,
                    agent_id=agent_id,
                    records=pending_records,
                    config=resolved,
                )
                if emitted:
                    self._set_lingzhu_delivered_count(conversation_id, total_count)
                else:
                    answer_text = reply_text
                    if not answer_text:
                        if not bool(result.get("accepted", False)):
                            reason = str(result.get("reason") or (result.get("normalized") or {}).get("reason") or "").strip()
                            answer_text = reason or "请求未接受"
                        else:
                            answer_text = "已收到"
                    self._write_sse_event(
                        handler,
                        event="message",
                        data=lingzhu_sse_answer(
                            message_id=message_id,
                            agent_id=agent_id,
                            answer_stream=answer_text,
                            is_finish=True,
                        ),
                    )
                handler.close_connection = True
                return

            if task_text is not None:
                target_quest_id = known_quest_id
                if target_quest_id:
                    self.sessions.bind(target_quest_id, conversation_id)
                    self.quest_service.bind_source(target_quest_id, binding_conversation_id)
                pending_before, total_before = self._lingzhu_pending_outbox_records(
                    conversation_id,
                    delivered_count=delivered_count,
                )
                emitted_before = self._lingzhu_emit_outbox_records(
                    handler,
                    message_id=message_id,
                    agent_id=agent_id,
                    records=pending_before,
                    config=resolved,
                )
                if emitted_before:
                    delivered_count = total_before
                    self._set_lingzhu_delivered_count(conversation_id, total_before)

                if not target_quest_id:
                    self._write_sse_event(
                        handler,
                        event="message",
                        data=lingzhu_sse_answer(
                            message_id=message_id,
                            agent_id=agent_id,
                            answer_stream=self._lingzhu_unbound_help_text(),
                            is_finish=True,
                        ),
                    )
                    handler.close_connection = True
                    return

                self.submit_user_message(
                    target_quest_id,
                    text=task_text,
                    source=conversation_id,
                    client_message_id=message_id,
                )
                pending_after, total_after = self._lingzhu_wait_for_outbox_records(
                    conversation_id,
                    delivered_count=delivered_count,
                    timeout_seconds=self._lingzhu_wait_timeout_seconds(resolved),
                )
                emitted_after = self._lingzhu_emit_outbox_records(
                    handler,
                    message_id=message_id,
                    agent_id=agent_id,
                    records=pending_after,
                    config=resolved,
                )
                if emitted_after:
                    self._set_lingzhu_delivered_count(conversation_id, total_after)
                else:
                    self._write_sse_event(
                        handler,
                        event="message",
                        data=lingzhu_sse_answer(
                            message_id=message_id,
                            agent_id=agent_id,
                            answer_stream="已开始" if emitted_before else self._lingzhu_short_status_text(target_quest_id),
                            is_finish=True,
                        ),
                    )
                handler.close_connection = True
                return

            if known_quest_id:
                self.sessions.bind(known_quest_id, conversation_id)
                self.quest_service.bind_source(known_quest_id, binding_conversation_id)

            pending_records, total_count = self._lingzhu_pending_outbox_records(
                conversation_id,
                delivered_count=delivered_count,
            )
            emitted = self._lingzhu_emit_outbox_records(
                handler,
                message_id=message_id,
                agent_id=agent_id,
                records=pending_records,
                config=resolved,
            )
            if emitted:
                self._set_lingzhu_delivered_count(conversation_id, total_count)
            else:
                self._write_sse_event(
                    handler,
                    event="message",
                    data=lingzhu_sse_answer(
                        message_id=message_id,
                        agent_id=agent_id,
                        answer_stream=self._lingzhu_short_status_text(known_quest_id),
                        is_finish=True,
                    ),
                )
            handler.close_connection = True
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    @staticmethod
    def _write_sse_event(
        handler: BaseHTTPRequestHandler,
        *,
        event: str,
        data: dict,
        event_id: str | None = None,
    ) -> None:
        if event_id:
            handler.wfile.write(f"id: {event_id}\n".encode("utf-8"))
        handler.wfile.write(f"event: {event}\n".encode("utf-8"))
        rendered = json.dumps(data, ensure_ascii=False)
        for line in rendered.splitlines() or ["{}"]:
            handler.wfile.write(f"data: {line}\n".encode("utf-8"))
        handler.wfile.write(b"\n")
        handler.wfile.flush()

    @staticmethod
    def _write_handler_response(
        handler: BaseHTTPRequestHandler,
        *,
        code: int,
        content: bytes,
        content_type: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> bool:
        try:
            handler.send_response(code)
            if content_type:
                handler.send_header("Content-Type", content_type)
            handler.send_header("Content-Length", str(len(content)))
            for key, value in (extra_headers or {}).items():
                handler.send_header(key, value)
            handler.end_headers()
            if content:
                handler.wfile.write(content)
            return True
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            try:
                handler.close_connection = True
            except Exception:
                pass
            return False

    @staticmethod
    def _parse_bash_log_jsonl_line(raw_line: bytes) -> dict[str, Any] | None:
        stripped = raw_line.strip()
        if not stripped:
            return None
        try:
            payload = json.loads(stripped.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    @staticmethod
    def _parse_quest_event_jsonl_line(raw_line: bytes) -> dict[str, Any] | None:
        stripped = raw_line.strip()
        if not stripped:
            return None
        try:
            payload = json.loads(stripped.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    @classmethod
    def _read_bash_log_delta(
        cls,
        log_path: Path,
        *,
        offset: int,
        pending: bytes,
        min_seq: int,
    ) -> tuple[list[dict[str, Any]], int, bytes]:
        if not log_path.exists():
            return [], 0, pending

        current_size = log_path.stat().st_size
        safe_offset = max(0, min(offset, current_size))
        with log_path.open("rb") as handle:
            handle.seek(safe_offset)
            chunk = handle.read()
            next_offset = handle.tell()

        if not chunk:
            return [], next_offset, pending

        payload = pending + chunk
        lines = payload.split(b"\n")
        remainder = b""
        if payload and not payload.endswith(b"\n"):
            remainder = lines.pop()

        fresh_entries: list[dict[str, Any]] = []
        for raw_line in lines:
            entry = cls._parse_bash_log_jsonl_line(raw_line.rstrip(b"\r"))
            if not entry:
                continue
            try:
                seq = int(entry.get("seq") or 0)
            except (TypeError, ValueError):
                seq = 0
            if seq <= min_seq:
                continue
            fresh_entries.append(entry)

        return fresh_entries, next_offset, remainder

    @classmethod
    def _read_quest_event_delta(
        cls,
        event_path: Path,
        *,
        offset: int,
        pending: bytes,
    ) -> tuple[list[dict[str, Any]], int, bytes]:
        if not event_path.exists():
            return [], 0, pending

        current_size = event_path.stat().st_size
        safe_offset = max(0, min(offset, current_size))
        with event_path.open("rb") as handle:
            handle.seek(safe_offset)
            chunk = handle.read()
            next_offset = handle.tell()

        if not chunk:
            return [], next_offset, pending

        payload = pending + chunk
        lines = payload.split(b"\n")
        remainder = b""
        if payload and not payload.endswith(b"\n"):
            remainder = lines.pop()

        fresh_entries: list[dict[str, Any]] = []
        for raw_line in lines:
            entry = cls._parse_quest_event_jsonl_line(raw_line.rstrip(b"\r"))
            if not entry:
                continue
            fresh_entries.append(entry)

        return fresh_entries, next_offset, remainder

    def stream_quest_events(
        self,
        handler: BaseHTTPRequestHandler,
        *,
        quest_id: str,
        path: str,
        headers: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        query = self.handlers.parse_query(path)
        after = int((query.get("after") or ["0"])[0] or "0")
        limit = max(1, min(int((query.get("limit") or ["200"])[0] or "200"), 200))
        format_name = ((query.get("format") or ["acp"])[0] or "acp").lower()
        session_id = ((query.get("session_id") or [f"quest:{quest_id}"])[0] or f"quest:{quest_id}")
        last_event_id = str((headers or {}).get("Last-Event-ID") or (headers or {}).get("last-event-id") or "").strip()
        current_cursor = max(after, int(last_event_id)) if last_event_id.isdigit() else after
        heartbeat_at = time.monotonic()
        idle_sleep_seconds = 0.08
        force_fetch = True
        event_path = self.quest_service._quest_root(quest_id) / ".ds" / "events.jsonl"
        previous_event_state = None
        cached_tail = self.quest_service.jsonl_tail_cache_entry(event_path) or {}
        cached_tail_state = cached_tail.get("state") if isinstance(cached_tail.get("state"), (list, tuple)) else None
        cached_tail_total = int(cached_tail.get("total") or 0) if isinstance(cached_tail, dict) else 0
        event_offset = int(cached_tail_state[2]) if cached_tail_state and cached_tail_total == current_cursor else 0
        pending_bytes = b""

        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache, no-transform")
        handler.send_header("Connection", "keep-alive")
        handler.send_header("X-Accel-Buffering", "no")
        for key, value in (extra_headers or {}).items():
            handler.send_header(key, value)
        handler.end_headers()
        handler.wfile.write(b"retry: 1000\n\n")
        handler.wfile.flush()

        try:
            while True:
                current_event_state = self.quest_service._path_state(event_path)
                if force_fetch or current_event_state != previous_event_state:
                    used_incremental_delta = False
                    delta_base_state = previous_event_state or cached_tail_state
                    can_read_incremental = (
                        current_cursor > 0
                        and event_offset > 0
                        and current_event_state is not None
                        and delta_base_state is not None
                        and tuple(delta_base_state)[0] == current_event_state[0]
                        and current_event_state[2] >= int(tuple(delta_base_state)[2])
                    )
                    if can_read_incremental:
                        fresh_events, event_offset, pending_bytes = self._read_quest_event_delta(
                            event_path,
                            offset=event_offset,
                            pending=pending_bytes,
                        )
                        previous_event_state = current_event_state
                        if fresh_events:
                            for event in fresh_events:
                                current_cursor += 1
                                enriched_event = {
                                    "cursor": current_cursor,
                                    "event_id": event.get("event_id") or f"evt-{quest_id}-{current_cursor}",
                                    **event,
                                }
                                enriched_event = self.quest_service.enrich_conversation_message_event(
                                    quest_id,
                                    enriched_event,
                                )
                                update = build_session_update(
                                    enriched_event,
                                    quest_id=quest_id,
                                    cursor=current_cursor,
                                    session_id=session_id,
                                )
                                self._write_sse_event(
                                    handler,
                                    event="acp_update",
                                    data=update,
                                    event_id=str(current_cursor),
                                )
                            self._write_sse_event(
                                handler,
                                event="cursor",
                                data={"cursor": current_cursor, "quest_id": quest_id},
                            )
                            heartbeat_at = time.monotonic()
                            used_incremental_delta = True
                            force_fetch = False
                            idle_sleep_seconds = 0.03
                        else:
                            force_fetch = False
                            now = time.monotonic()
                            if now - heartbeat_at >= 10:
                                handler.wfile.write(b": keep-alive\n\n")
                                handler.wfile.flush()
                                heartbeat_at = now
                    if used_incremental_delta:
                        time.sleep(idle_sleep_seconds)
                        continue
                    stream_path = f"/api/quests/{quest_id}/events?{urlencode({'after': current_cursor, 'limit': limit, 'format': format_name, 'session_id': session_id})}"
                    payload = self.handlers.quest_events(quest_id, path=stream_path)
                    previous_event_state = current_event_state
                    updates = payload.get("acp_updates") or []
                    if updates:
                        for update in updates:
                            update_cursor = str(((update.get("params") or {}).get("update") or {}).get("cursor") or "")
                            self._write_sse_event(
                                handler,
                                event="acp_update",
                                data=update,
                                event_id=update_cursor or None,
                            )
                        current_cursor = int(payload.get("cursor") or current_cursor)
                        if current_event_state is not None and not payload.get("has_more"):
                            event_offset = int(current_event_state[2])
                            pending_bytes = b""
                            cached_tail_state = current_event_state
                            cached_tail_total = current_cursor
                        self._write_sse_event(
                            handler,
                            event="cursor",
                            data={"cursor": current_cursor, "quest_id": quest_id},
                        )
                        heartbeat_at = time.monotonic()
                        force_fetch = bool(payload.get("has_more"))
                        idle_sleep_seconds = 0.03 if force_fetch else 0.08
                    else:
                        if current_event_state is not None:
                            event_offset = int(current_event_state[2])
                            cached_tail_state = current_event_state
                        force_fetch = False
                        now = time.monotonic()
                        if now - heartbeat_at >= 10:
                            handler.wfile.write(b": keep-alive\n\n")
                            handler.wfile.flush()
                            heartbeat_at = now
                        idle_sleep_seconds = min(0.9, idle_sleep_seconds * 1.25)
                else:
                    now = time.monotonic()
                    if now - heartbeat_at >= 10:
                        handler.wfile.write(b": keep-alive\n\n")
                        handler.wfile.flush()
                        heartbeat_at = now
                    idle_sleep_seconds = min(0.9, idle_sleep_seconds * 1.25)
                time.sleep(idle_sleep_seconds)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def stream_admin_task(
        self,
        handler: BaseHTTPRequestHandler,
        *,
        task_id: str,
        headers: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        try:
            task = self.admin_task_service.get_task(task_id)
        except FileNotFoundError:
            self._write_handler_response(
                handler,
                code=404,
                content=json.dumps(
                    {"ok": False, "message": f"Unknown admin task `{task_id}`."},
                    ensure_ascii=False,
                ).encode("utf-8"),
                content_type="application/json; charset=utf-8",
                extra_headers=extra_headers,
            )
            return

        last_event_raw = str((headers or {}).get("Last-Event-ID") or (headers or {}).get("last-event-id") or "").strip()
        cursor = int(last_event_raw) if last_event_raw.isdigit() else 0

        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache, no-transform")
        handler.send_header("Connection", "keep-alive")
        handler.send_header("X-Accel-Buffering", "no")
        for key, value in (extra_headers or {}).items():
            handler.send_header(key, value)
        handler.end_headers()
        handler.wfile.write(b"retry: 1000\n\n")
        handler.wfile.flush()

        self._write_sse_event(
            handler,
            event="task.snapshot",
            data={"task": task},
        )
        heartbeat_at = time.monotonic()
        terminal_statuses = {"completed", "failed", "cancelled"}
        try:
            while True:
                current_task = self.admin_task_service.get_task(task_id)
                events = self.admin_task_service.read_events(task_id, after=cursor, limit=200)
                if events:
                    for item in events:
                        cursor = max(cursor, int(item.get("seq") or 0))
                        self._write_sse_event(
                            handler,
                            event=str(item.get("event") or "task.log"),
                            data=item,
                            event_id=str(cursor),
                        )
                    heartbeat_at = time.monotonic()
                elif time.monotonic() - heartbeat_at >= 10:
                    handler.wfile.write(b": keep-alive\n\n")
                    handler.wfile.flush()
                    heartbeat_at = time.monotonic()
                current_status = str(current_task.get("status") or "").strip().lower()
                if current_status in terminal_statuses and cursor >= int(current_task.get("last_event_seq") or 0):
                    return
                time.sleep(0.2 if current_status == "running" else 0.6)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def stream_bash_sessions(
        self,
        handler: BaseHTTPRequestHandler,
        *,
        quest_id: str,
        path: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        quest_root = self.quest_service._quest_root(quest_id)
        query = self.handlers.parse_query(path)
        status = ((query.get("status") or [""])[0] or "").strip() or None
        limit_raw = ((query.get("limit") or ["200"])[0] or "200").strip()
        chat_session_id = ((query.get("chat_session_id") or [""])[0] or "").strip() or None
        try:
            limit = max(1, min(int(limit_raw), 500))
        except ValueError:
            limit = 200
        agent_ids = [
            item.strip()
            for item in (((query.get("agent_ids") or [""])[0] or "").split(","))
            if item.strip()
        ]
        agent_instance_ids = [
            item.strip()
            for item in (((query.get("agent_instance_ids") or [""])[0] or "").split(","))
            if item.strip()
        ]

        def list_payload() -> list[dict[str, object]]:
            return self.bash_exec_service.list_sessions(
                quest_root,
                status=status,
                agent_ids=agent_ids or None,
                agent_instance_ids=agent_instance_ids or None,
                chat_session_id=chat_session_id,
                limit=limit,
            )

        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache, no-transform")
        handler.send_header("Connection", "keep-alive")
        handler.send_header("X-Accel-Buffering", "no")
        for key, value in (extra_headers or {}).items():
            handler.send_header(key, value)
        handler.end_headers()
        handler.wfile.write(b"retry: 1000\n\n")
        handler.wfile.flush()

        previous_snapshot: dict[str, dict[str, object]] = {}
        heartbeat_at = time.monotonic()
        summary_path = self.bash_exec_service.summary_path(quest_root)
        index_path = self.bash_exec_service.index_path(quest_root)
        previous_summary_state = None
        previous_index_state = None
        has_active_sessions = False
        last_full_refresh_at = 0.0
        try:
            while True:
                current_summary_state = self.quest_service._path_state(summary_path)
                current_index_state = self.quest_service._path_state(index_path)
                should_refresh = (
                    not previous_snapshot
                    or current_summary_state != previous_summary_state
                    or current_index_state != previous_index_state
                    or (has_active_sessions and time.monotonic() - last_full_refresh_at >= 3.0)
                )
                if should_refresh:
                    sessions = list_payload()
                    current_snapshot = {
                        str(item.get("bash_id") or ""): item
                        for item in sessions
                        if item.get("bash_id")
                    }
                    has_active_sessions = any(
                        str(item.get("status") or "").strip().lower() in {"running", "terminating"}
                        for item in current_snapshot.values()
                    )
                    previous_summary_state = self.quest_service._path_state(summary_path)
                    previous_index_state = self.quest_service._path_state(index_path)
                    last_full_refresh_at = time.monotonic()
                    if not previous_snapshot:
                        self._write_sse_event(
                            handler,
                            event="snapshot",
                            data={"sessions": sessions},
                        )
                        previous_snapshot = current_snapshot
                        heartbeat_at = time.monotonic()
                    else:
                        changed = [
                            session
                            for bash_id, session in current_snapshot.items()
                            if previous_snapshot.get(bash_id) != session
                        ]
                        removed = set(previous_snapshot) - set(current_snapshot)
                        for session in changed:
                            self._write_sse_event(
                                handler,
                                event="session",
                                data={"session": session},
                            )
                        for bash_id in removed:
                            self._write_sse_event(
                                handler,
                                event="session",
                                data={"session": {"bash_id": bash_id, "status": "terminated"}},
                            )
                        if changed or removed:
                            previous_snapshot = current_snapshot
                            heartbeat_at = time.monotonic()
                        elif time.monotonic() - heartbeat_at >= 10:
                            handler.wfile.write(b": keep-alive\n\n")
                            handler.wfile.flush()
                            heartbeat_at = time.monotonic()
                elif time.monotonic() - heartbeat_at >= 10:
                    handler.wfile.write(b": keep-alive\n\n")
                    handler.wfile.flush()
                    heartbeat_at = time.monotonic()
                time.sleep(0.5 if has_active_sessions else 2.0)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def stream_bash_logs(
        self,
        handler: BaseHTTPRequestHandler,
        *,
        quest_id: str,
        bash_id: str,
        headers: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        quest_root = self.quest_service._quest_root(quest_id)
        last_event_raw = str((headers or {}).get("Last-Event-ID") or (headers or {}).get("last-event-id") or "").strip()
        last_event_id = int(last_event_raw) if last_event_raw.isdigit() else None

        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache, no-transform")
        handler.send_header("Connection", "keep-alive")
        handler.send_header("X-Accel-Buffering", "no")
        for key, value in (extra_headers or {}).items():
            handler.send_header(key, value)
        handler.end_headers()
        handler.wfile.write(b"retry: 1000\n\n")
        handler.wfile.flush()

        previous_progress = None
        previous_status = None
        previous_exit_code = None
        cursor = last_event_id or 0
        initialized = False
        heartbeat_at = time.monotonic()
        log_path = self.bash_exec_service.log_path(quest_root, bash_id)
        log_offset = 0
        pending_bytes = b""
        try:
            while True:
                session = self.bash_exec_service.get_session(quest_root, bash_id)
                latest_status = str(session.get("status") or "")
                latest_exit_code = session.get("exit_code")

                if not initialized:
                    if last_event_id is None:
                        entries, meta = self.bash_exec_service.read_log_entries(
                            quest_root,
                            bash_id,
                            limit=200,
                            before_seq=None,
                            order="asc",
                        )
                        latest_seq = int(meta.get("latest_seq") or 0)
                        self._write_sse_event(
                            handler,
                            event="snapshot",
                            event_id=str(latest_seq) if latest_seq else None,
                            data={
                                "bash_id": bash_id,
                                "tail_limit": meta.get("tail_limit"),
                                "tail_start_seq": meta.get("tail_start_seq"),
                                "latest_seq": meta.get("latest_seq"),
                                "lines": [
                                    {
                                        "seq": entry.get("seq"),
                                        "stream": entry.get("stream"),
                                        "line": entry.get("line"),
                                        "timestamp": entry.get("timestamp"),
                                    }
                                    for entry in entries
                                ],
                                "progress": session.get("last_progress"),
                            },
                        )
                        cursor = latest_seq
                        heartbeat_at = time.monotonic()

                    fresh_entries, log_offset, pending_bytes = self._read_bash_log_delta(
                        log_path,
                        offset=0,
                        pending=b"",
                        min_seq=cursor,
                    )
                    for entry in fresh_entries:
                        cursor = int(entry.get("seq") or cursor)
                        self._write_sse_event(
                            handler,
                            event="log",
                            event_id=str(cursor),
                            data={
                                "bash_id": bash_id,
                                "seq": entry.get("seq"),
                                "stream": entry.get("stream"),
                                "line": entry.get("line"),
                                "timestamp": entry.get("timestamp"),
                            },
                        )
                        heartbeat_at = time.monotonic()

                    previous_progress = session.get("last_progress")
                    previous_status = latest_status
                    previous_exit_code = latest_exit_code
                    initialized = True

                    if latest_status in {"completed", "failed", "terminated"}:
                        self._write_sse_event(
                            handler,
                            event="done",
                            data={
                                "bash_id": bash_id,
                                "status": latest_status,
                                "exit_code": latest_exit_code,
                                "finished_at": session.get("finished_at"),
                            },
                        )
                        return
                else:
                    if log_path.exists() and log_path.stat().st_size < log_offset:
                        self._write_sse_event(
                            handler,
                            event="gap",
                            data={
                                "bash_id": bash_id,
                                "from_seq": cursor or None,
                                "to_seq": None,
                                "tail_limit": 200,
                            },
                        )
                        log_offset = 0
                        pending_bytes = b""
                        heartbeat_at = time.monotonic()

                    fresh_entries, log_offset, pending_bytes = self._read_bash_log_delta(
                        log_path,
                        offset=log_offset,
                        pending=pending_bytes,
                        min_seq=cursor,
                    )
                    for entry in fresh_entries:
                        cursor = int(entry.get("seq") or cursor)
                        self._write_sse_event(
                            handler,
                            event="log",
                            event_id=str(cursor),
                            data={
                                "bash_id": bash_id,
                                "seq": entry.get("seq"),
                                "stream": entry.get("stream"),
                                "line": entry.get("line"),
                                "timestamp": entry.get("timestamp"),
                            },
                        )
                        heartbeat_at = time.monotonic()

                    if session.get("last_progress") != previous_progress and session.get("last_progress") is not None:
                        previous_progress = session.get("last_progress")
                        self._write_sse_event(
                            handler,
                            event="progress",
                            data={
                                "bash_id": bash_id,
                                **dict(session.get("last_progress") or {}),
                            },
                        )
                        heartbeat_at = time.monotonic()

                    if latest_status in {"completed", "failed", "terminated"} and (
                        latest_status != previous_status or latest_exit_code != previous_exit_code
                    ):
                        previous_status = latest_status
                        previous_exit_code = latest_exit_code
                        self._write_sse_event(
                            handler,
                            event="done",
                            data={
                                "bash_id": bash_id,
                                "status": latest_status,
                                "exit_code": latest_exit_code,
                                "finished_at": session.get("finished_at"),
                            },
                        )
                        heartbeat_at = time.monotonic()
                        return

                    previous_status = latest_status
                    previous_exit_code = latest_exit_code

                    if time.monotonic() - heartbeat_at >= 10:
                        handler.wfile.write(b": keep-alive\n\n")
                        handler.wfile.flush()
                        heartbeat_at = time.monotonic()
                time.sleep(TERMINAL_STREAM_IDLE_SLEEP_SECONDS)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def serve(self, host: str, port: int) -> None:
        self._install_process_observability()
        app = self

        class RequestHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                self._dispatch("GET")

            def do_POST(self) -> None:  # noqa: N802
                self._dispatch("POST")

            def do_PUT(self) -> None:  # noqa: N802
                self._dispatch("PUT")

            def do_PATCH(self) -> None:  # noqa: N802
                self._dispatch("PATCH")

            def do_DELETE(self) -> None:  # noqa: N802
                self._dispatch("DELETE")

            def _dispatch(self, method: str) -> None:
                parsed = urlparse(self.path)
                route_name, params = match_route(method, parsed.path)
                if route_name is None:
                    self._write_json(404, {"ok": False, "message": "Not Found"})
                    return
                request_headers = dict(self.headers.items())
                auth_state = app.browser_auth_state_for_request(self.path, request_headers)
                auth_headers = app._auth_response_headers(auth_state)
                if app._route_requires_browser_auth(route_name) and not auth_state.authenticated:
                    self._write_json(
                        401,
                        {
                            "ok": False,
                            "message": "Authentication required.",
                            "auth_required": True,
                            "auth_enabled": True,
                        },
                        extra_headers={
                            **auth_headers,
                            "WWW-Authenticate": f'Bearer realm="{_BROWSER_AUTH_REALM}"',
                            "Cache-Control": "no-store, max-age=0, must-revalidate",
                        },
                    )
                    return
                if route_name in {"admin_task_stream", "system_task_stream"}:
                    try:
                        app.stream_admin_task(self, **params, headers=request_headers, extra_headers=auth_headers)
                    except Exception as exc:
                        app.logger.log(
                            "error",
                            "http.stream_admin_task_failed",
                            path=self.path,
                            error=str(exc),
                        )
                        self.close_connection = True
                    return
                if route_name == "quest_events" and app._wants_event_stream(self.path, request_headers):
                    try:
                        app.stream_quest_events(self, **params, path=self.path, headers=request_headers, extra_headers=auth_headers)
                    except Exception as exc:
                        app.logger.log(
                            "error",
                            "http.stream_quest_events_failed",
                            path=self.path,
                            error=str(exc),
                        )
                        self.close_connection = True
                    return
                if route_name == "bash_sessions_stream":
                    try:
                        app.stream_bash_sessions(self, **params, path=self.path, extra_headers=auth_headers)
                    except Exception as exc:
                        app.logger.log(
                            "error",
                            "http.stream_bash_sessions_failed",
                            path=self.path,
                            error=str(exc),
                        )
                        self.close_connection = True
                    return
                if route_name == "bash_log_stream":
                    try:
                        app.stream_bash_logs(self, **params, headers=request_headers, extra_headers=auth_headers)
                    except Exception as exc:
                        app.logger.log(
                            "error",
                            "http.stream_bash_logs_failed",
                            path=self.path,
                            error=str(exc),
                        )
                        self.close_connection = True
                    return
                if route_name == "terminal_stream":
                    try:
                        app.stream_bash_logs(
                            self,
                            quest_id=params["quest_id"],
                            bash_id=params["session_id"],
                            headers=request_headers,
                            extra_headers=auth_headers,
                        )
                    except Exception as exc:
                        app.logger.log(
                            "error",
                            "http.stream_terminal_logs_failed",
                            path=self.path,
                            error=str(exc),
                        )
                        self.close_connection = True
                    return
                if route_name == "lingzhu_sse":
                    content_length = int(self.headers.get("Content-Length", "0"))
                    raw_body = self.rfile.read(content_length) if content_length else b""
                    try:
                        app.stream_lingzhu_sse(self, raw_body=raw_body, headers=request_headers)
                    except Exception as exc:
                        self._write_json(500, {"ok": False, "message": str(exc)})
                    return

                content_length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_length) if content_length else b""
                body = {}
                if raw_body and self.headers.get("Content-Type", "").startswith("application/json"):
                    body = app.handlers.parse_body(raw_body)

                try:
                    result = getattr(app.handlers, route_name)
                    route_alias = route_name.removeprefix("admin_").removeprefix("system_")
                    if route_name == "asset":
                        status, headers, content = result(**params)
                        app._write_handler_response(
                            self,
                            code=status,
                            content=content,
                            extra_headers=app._merge_response_headers(headers, auth_headers),
                        )
                        return
                    if route_alias in {
                        "quests",
                        "runtime_sessions",
                        "log_tail",
                        "failures",
                        "errors",
                        "audit",
                        "search",
                        "repairs",
                        "tasks",
                    } or route_name in {
                        "quest_events",
                        "bash_sessions",
                        "bash_logs",
                        "git_log",
                        "git_compare",
                        "git_commit",
                        "git_diff_file",
                        "git_commit_file",
                        "file_change_diff",
                        "explorer",
                        "quest_search",
                        "node_traces",
                        "node_trace",
                        "document_asset",
                        "terminal_restore",
                        "terminal_history",
                        "latex_builds",
                        "arxiv_list",
                        "annotations_file",
                        "annotations_project",
                    }:
                        payload = result(**params, path=self.path)
                    elif route_name in {
                        "benchstore_entries",
                        "benchstore_entry",
                        "benchstore_entry_image",
                        "benchstore_entry_setup_packet",
                    }:
                        payload = result(**params, path=self.path) if params else result(self.path)
                    elif method == "GET":
                        payload = result(**params) if params else result()
                    elif route_alias in {
                        "shutdown",
                        "chart_query",
                        "task_doctor_start",
                        "task_system_update_check_start",
                        "task_system_update_action_start",
                        "issue_draft",
                        "controller_run",
                        "controller_toggle",
                        "repair_create",
                        "repair_close",
                        "hardware_update",
                    } or route_name in {"document_open", "document_asset_upload", "quest_file_create_folder", "quest_file_upload", "quest_file_rename", "quest_file_move", "quest_file_delete", "chat_upload_create", "chat_upload_delete", "chat", "command", "quest_control", "quest_message_read_now", "quest_message_withdraw", "config_save", "quest_create", "quest_baseline_binding", "run_create", "qq_inbound", "connector_inbound", "docs_open", "bash_stop", "quest_settings", "quest_bindings", "quest_delete", "quest_layout_update", "terminal_session_ensure", "terminal_attach", "terminal_input", "stage_view", "latex_init", "latex_compile", "system_update_action", "weixin_login_qr_start", "weixin_login_qr_wait", "arxiv_import", "annotation_create", "auth_login", "auth_rotate"}:
                        payload = result(**params, body=body)
                    elif route_name == "config_validate":
                        payload = result(body)
                    elif route_name == "config_test":
                        payload = result(body)
                    elif method in {"PUT", "PATCH"}:
                        payload = result(**params, body=body)
                    elif route_name == "memory":
                        payload = result(app.handlers.parse_query(self.path))
                    elif route_name == "benchstore_entry_launch":
                        payload = result(**params, path=self.path, body=body)
                    else:
                        payload = result(**params) if params else result()
                except Exception as exc:
                    self._write_json(500, {"ok": False, "message": str(exc)}, extra_headers=auth_headers)
                    return

                if isinstance(payload, tuple) and len(payload) == 2:
                    status, body = payload
                    self._write_json(status, body, extra_headers=auth_headers)
                    return
                if isinstance(payload, tuple) and len(payload) == 3:
                    status, headers, content = payload
                    if isinstance(content, str):
                        encoded = content.encode("utf-8")
                    else:
                        encoded = content
                    app._write_handler_response(
                        self,
                        code=status,
                        content=encoded,
                        extra_headers=app._merge_response_headers(headers, auth_headers),
                    )
                    return
                self._write_json(200, payload, extra_headers=auth_headers)

            def _write_json(
                self,
                code: int,
                payload: dict | list,
                *,
                extra_headers: dict[str, str] | None = None,
            ) -> None:
                encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
                app._write_handler_response(
                    self,
                    code=code,
                    content=encoded,
                    content_type="application/json; charset=utf-8",
                    extra_headers=extra_headers,
                )

        server = ThreadingHTTPServer((host, port), RequestHandler)
        server.daemon_threads = True
        self._server = server
        self._serve_host = host
        self._serve_port = port
        self._shutdown_requested.clear()
        self.admin_service.system_monitor.start()
        self.admin_service.metrics_collector.start()
        self._start_terminal_attach_server(host, port)
        self._start_background_connectors()
        self._resume_reconciled_quests()
        print(f"DeepScientist daemon listening on http://{host}:{port}")
        if self.browser_auth_enabled and self.browser_auth_token:
            print(f"DeepScientist auth token: {self.browser_auth_token}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            self.logger.log("warning", "daemon.keyboard_interrupt", pid=os.getpid())
        except BaseException as exc:
            self._log_unhandled_exception(
                event_type="daemon.serve_crashed",
                exc_type=type(exc),
                exc_value=exc,
                exc_traceback=exc.__traceback__,
            )
            raise
        finally:
            self._stop_background_connectors()
            self._stop_terminal_attach_server()
            self.admin_service.metrics_collector.stop()
            self.admin_service.system_monitor.stop()
            self.bash_exec_service.shutdown()
            self._server = None
            self._serve_host = None
            self._serve_port = None
            server.server_close()
