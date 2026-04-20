from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..shared import read_yaml


DEFAULT_BUILTIN_MCP_SERVER_NAMES: tuple[str, ...] = ("memory", "artifact", "bash_exec")
SETTINGS_ISSUE_CUSTOM_PROFILE = "settings_issue"
START_SETUP_PREPARE_PROFILE = "start_setup_prepare"


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
