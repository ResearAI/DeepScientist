from __future__ import annotations

from pathlib import Path

from ..shared import utc_now


def default_active_anchor(startup_contract: dict | None = None) -> str:
    workspace_mode = (
        str((startup_contract or {}).get("workspace_mode") or "").strip().lower()
        if isinstance(startup_contract, dict)
        else ""
    )
    return "scout" if workspace_mode == "copilot" else "baseline"


QUEST_DIRECTORIES = (
    "artifacts/approvals",
    "artifacts/baselines",
    "artifacts/decisions",
    "artifacts/graphs",
    "artifacts/ideas",
    "artifacts/milestones",
    "artifacts/progress",
    "artifacts/reports",
    "artifacts/runs",
    "baselines/imported",
    "baselines/local",
    "experiments/analysis",
    "experiments/main",
    "handoffs",
    "literature",
    "userfiles",
    "tmp",
    "memory/decisions",
    "memory/episodes",
    "memory/ideas",
    "memory/knowledge",
    "memory/papers",
    "paper",
    "release/open_source",
    "design/scene",
    "design/preview/app",
    "design/preview/snapshots",
    "design/exports",
    ".codex/prompts",
    ".codex/skills",
    ".claude/agents",
    ".opencode/skills",
    ".ds/bash_exec",
    ".ds/conversations",
    ".ds/codex_history",
    ".ds/runs",
    ".ds/worktrees",
)


def initial_quest_yaml(
    quest_id: str,
    goal: str,
    quest_root: Path,
    runner: str,
    title: str | None = None,
    *,
    requested_baseline_ref: dict | None = None,
    startup_contract: dict | None = None,
) -> dict:
    timestamp = utc_now()
    workspace_mode = (
        str((startup_contract or {}).get("workspace_mode") or "").strip().lower()
        if isinstance(startup_contract, dict)
        else ""
    )
    initial_status_value = "idle" if workspace_mode == "copilot" else "active"
    return {
        "quest_id": quest_id,
        "title": title or goal,
        "quest_root": str(quest_root.resolve()),
        "status": initial_status_value,
        "active_anchor": default_active_anchor(startup_contract),
        "baseline_gate": "pending",
        "confirmed_baseline_ref": None,
        "requested_baseline_ref": requested_baseline_ref,
        "startup_contract": startup_contract,
        "default_runner": runner,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def initial_brief(goal: str) -> str:
    return "\n".join(
        [
            f"# Quest Brief",
            "",
            f"## Goal",
            "",
            goal,
            "",
            "## Initial Notes",
            "",
            "- Establish or attach a baseline.",
            "- Capture the first concrete decision with explicit reasons.",
            "",
        ]
    )


def initial_plan() -> str:
    return "\n".join(
        [
            "# Plan",
            "",
            "- [ ] Establish or attach a reusable baseline",
            "- [ ] Record at least one candidate idea",
            "- [ ] Write a decision artifact with explicit reason",
            "- [ ] Run the first experiment or decide to stop",
            "",
        ]
    )


def initial_status(startup_contract: dict | None = None) -> str:
    workspace_mode = (
        str((startup_contract or {}).get("workspace_mode") or "").strip().lower()
        if isinstance(startup_contract, dict)
        else ""
    )
    if workspace_mode == "copilot":
        return "# Status\n\nReady for your first instruction.\n"
    return "# Status\n\nQuest created. Waiting for baseline setup or reuse.\n"


def initial_summary() -> str:
    return "# Summary\n\nNo completed milestones yet.\n"


def gitignore() -> str:
    return "\n".join(
        [
            ".ds/*.pid",
            ".ds/*.sock",
            ".ds/*.tmp",
            ".ds/worktrees/",
            "tmp/",
            "__pycache__/",
            ".pytest_cache/",
            "",
        ]
    )
