from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..shared import read_yaml


DEFAULT_BUILTIN_MCP_SERVER_NAMES: tuple[str, ...] = ("memory", "artifact", "bash_exec")
SETTINGS_ISSUE_CUSTOM_PROFILE = "settings_issue"
START_SETUP_PREPARE_PROFILE = "start_setup_prepare"
_START_SETUP_PATCH_BLOCK_RE = re.compile(r"```start_setup_patch\s*([\s\S]*?)```", re.IGNORECASE)


def resolve_custom_profile_for_quest(quest_root: Path) -> str | None:
    quest_yaml = read_yaml(quest_root / "quest.yaml", {})
    startup_contract = quest_yaml.get("startup_contract") if isinstance(quest_yaml, dict) else None
    if not isinstance(startup_contract, dict):
        return None
    value = str(startup_contract.get("custom_profile") or "").strip().lower()
    return value or None


def resolve_mcp_tool_profile_for_quest(quest_root: Path) -> str | None:
    quest_yaml = read_yaml(quest_root / "quest.yaml", {})
    startup_contract = quest_yaml.get("startup_contract") if isinstance(quest_yaml, dict) else None
    if not isinstance(startup_contract, dict):
        return None
    custom_profile = str(startup_contract.get("custom_profile") or "").strip().lower()
    if custom_profile == SETTINGS_ISSUE_CUSTOM_PROFILE:
        return SETTINGS_ISSUE_CUSTOM_PROFILE
    if isinstance(startup_contract.get("start_setup_session"), dict):
        return START_SETUP_PREPARE_PROFILE
    return None


def builtin_mcp_server_names_for_custom_profile(custom_profile: str | None) -> tuple[str, ...]:
    normalized = str(custom_profile or "").strip().lower()
    if normalized in {SETTINGS_ISSUE_CUSTOM_PROFILE, START_SETUP_PREPARE_PROFILE}:
        return ("artifact", "bash_exec")
    return DEFAULT_BUILTIN_MCP_SERVER_NAMES


def extract_start_setup_patch_from_text(text: str) -> dict[str, Any] | None:
    source = str(text or "").strip()
    if not source:
        return None
    match = _START_SETUP_PATCH_BLOCK_RE.search(source)
    if not match:
        return None
    candidate = match.group(1).strip()
    if not candidate:
        return None
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("form_patch"), dict):
        return dict(payload.get("form_patch") or {})
    if isinstance(payload.get("suggested_form"), dict):
        suggested_form = payload.get("suggested_form") or {}
        if isinstance(suggested_form.get("form_patch"), dict):
            return dict(suggested_form.get("form_patch") or {})
    return dict(payload)


def extract_start_setup_session_patch_from_text(text: str) -> dict[str, Any] | None:
    source = str(text or "").strip()
    if not source:
        return None
    match = _START_SETUP_PATCH_BLOCK_RE.search(source)
    if not match:
        return None
    candidate = match.group(1).strip()
    if not candidate:
        return None
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("session_patch"), dict):
        return dict(payload.get("session_patch") or {})
    suggested_form = payload.get("suggested_form")
    if isinstance(suggested_form, dict) and isinstance(suggested_form.get("session_patch"), dict):
        return dict(suggested_form.get("session_patch") or {})
    return None


@dataclass(frozen=True)
class RunRequest:
    quest_id: str
    quest_root: Path
    worktree_root: Path | None
    run_id: str
    skill_id: str
    message: str
    model: str
    approval_policy: str
    sandbox_mode: str
    turn_reason: str = "user_message"
    turn_intent: str = "continue_stage"
    turn_mode: str = "stage_execution"
    reasoning_effort: str | None = None
    turn_id: str | None = None
    attempt_index: int = 1
    max_attempts: int = 1
    retry_context: dict[str, Any] | None = None


@dataclass(frozen=True)
class RunResult:
    ok: bool
    run_id: str
    model: str
    output_text: str
    exit_code: int
    history_root: Path
    run_root: Path
    stderr_text: str
