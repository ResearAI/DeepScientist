from __future__ import annotations

import argparse
import json
from pathlib import Path

from deepscientist.artifact import ArtifactService
from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.quest import QuestService
from deepscientist.shared import append_jsonl, utc_now, write_json, write_text
from datetime import UTC, datetime, timedelta
from deepscientist.skills import SkillInstaller


FIXTURE_QUEST_ID = "e2e-admin-quest"
FIXTURE_TITLE = "Admin E2E Quest"


def build_fixture(home: Path) -> dict[str, object]:
    ensure_home_layout(home)
    ConfigManager(home).ensure_files()

    installer = SkillInstaller(repo_root(), home)
    quest_service = QuestService(home, skill_installer=installer)
    artifact = ArtifactService(home)

    quest = quest_service.create(
        "Admin e2e fixture quest",
        quest_id=FIXTURE_QUEST_ID,
        title=FIXTURE_TITLE,
        startup_contract={
            "workspace_mode": "copilot",
            "decision_policy": "user_gated",
            "launch_mode": "custom",
            "custom_profile": "freeform",
        },
    )
    quest_root = Path(quest["quest_root"])

    quest_service.update_research_state(quest_root, workspace_mode="copilot")
    quest_service.set_continuation_state(
        quest_root,
        policy="wait_for_user_or_resume",
        anchor="decision",
        reason="copilot_mode",
    )

    baseline_root = quest_root / "baselines" / "local" / "baseline-admin-e2e"
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Baseline\n", encoding="utf-8")
    artifact.confirm_baseline(
        quest_root,
        baseline_path=str(baseline_root),
        baseline_id="baseline-admin-e2e",
        summary="Admin E2E baseline.",
        metrics_summary={"acc": 0.81, "loss": 0.42},
        primary_metric={"metric_id": "acc", "value": 0.81},
        metric_contract={
            "primary_metric_id": "acc",
            "metrics": [
                {"metric_id": "acc", "direction": "higher", "label": "Accuracy"},
                {"metric_id": "loss", "direction": "lower", "label": "Loss"},
            ],
        },
    )

    artifact.submit_idea(
        quest_root,
        mode="create",
        title="Admin e2e line",
        problem="Need an admin detail surface with real metrics.",
        hypothesis="A seeded quest will make the admin detail page verifiable.",
        mechanism="Seed one baseline and one main run.",
        decision_reason="Create a realistic admin fixture.",
        next_target="experiment",
    )

    artifact.record_main_experiment(
        quest_root,
        run_id="admin-e2e-main-001",
        title="Admin E2E run",
        hypothesis="The seeded run should be visible in admin details.",
        setup="Synthetic local fixture.",
        execution="Recorded a compact main experiment.",
        results="Accuracy improved and loss decreased.",
        conclusion="Admin details should show a baseline compare and metrics overview.",
        metric_rows=[
            {"metric_id": "acc", "value": 0.87},
            {"metric_id": "loss", "value": 0.34},
        ],
        metric_contract={
            "primary_metric_id": "acc",
            "metrics": [
                {"metric_id": "acc", "direction": "higher", "label": "Accuracy"},
                {"metric_id": "loss", "direction": "lower", "label": "Loss"},
            ],
        },
        evaluation_summary={
            "takeaway": "The seeded run beats baseline.",
            "claim_update": "strengthens",
            "baseline_relation": "better",
        },
        strict_metric_contract=True,
    )

    quest_service.append_message(
        FIXTURE_QUEST_ID,
        role="user",
        content="Please keep this quest available for admin inspection.",
        source="web-react",
    )
    quest_service.append_message(
        FIXTURE_QUEST_ID,
        role="assistant",
        content="Fixture quest is ready for admin inspection.",
        source="codex",
        run_id="admin-e2e-main-001",
        skill_id="decision",
    )

    append_jsonl(
        home / "logs" / "daemon.jsonl",
        {
            "timestamp": utc_now(),
            "level": "info",
            "event": "admin.e2e.seeded",
            "payload": {"quest_id": FIXTURE_QUEST_ID},
        },
    )

    now = datetime.now(UTC)
    tool_events = [
        ("evt-tool-call-1", "runner.tool_call", "artifact.search_docs", "artifact", "search_docs", now - timedelta(hours=1)),
        ("evt-tool-result-1", "runner.tool_result", "artifact.search_docs", "artifact", "search_docs", now - timedelta(hours=1) + timedelta(minutes=1)),
        ("evt-tool-call-2", "runner.tool_call", "bash_exec.bash_exec", "bash_exec", "bash_exec", now - timedelta(hours=5)),
        ("evt-tool-result-2", "runner.tool_result", "bash_exec.bash_exec", "bash_exec", "bash_exec", now - timedelta(hours=5) + timedelta(minutes=2)),
        ("evt-tool-call-3", "runner.tool_call", "memory.list_recent", "memory", "list_recent", now - timedelta(days=2, hours=3)),
        ("evt-tool-result-3", "runner.tool_result", "memory.list_recent", "memory", "list_recent", now - timedelta(days=2, hours=3) + timedelta(minutes=1)),
        ("evt-tool-call-4", "runner.tool_call", "artifact.search_docs", "artifact", "search_docs", now - timedelta(days=4, hours=7)),
        ("evt-tool-result-4", "runner.tool_result", "artifact.search_docs", "artifact", "search_docs", now - timedelta(days=4, hours=7) + timedelta(minutes=1)),
    ]
    events_path = quest_root / ".ds" / "events.jsonl"
    for event_id, event_type, tool_name, mcp_server, mcp_tool, created_at in tool_events:
        append_jsonl(
            events_path,
            {
                "event_id": event_id,
                "type": event_type,
                "quest_id": FIXTURE_QUEST_ID,
                "run_id": "admin-e2e-main-001",
                "tool_call_id": event_id.replace("evt-", "tool-"),
                "tool_name": tool_name,
                "mcp_server": mcp_server,
                "mcp_tool": mcp_tool,
                "status": "completed" if event_type == "runner.tool_result" else "calling",
                "created_at": created_at.isoformat(),
            },
        )

    write_json(
        home / "runtime" / "admin" / "controllers.json",
        {
            "controllers": {
                "stale_running_quest_guard": {"enabled": True, "updated_at": utc_now()},
                "repeated_runner_error_guard": {"enabled": False, "updated_at": utc_now()},
                "connector_degraded_guard": {"enabled": True, "updated_at": utc_now()},
            }
        },
    )

    return {
        "quest_id": FIXTURE_QUEST_ID,
        "title": FIXTURE_TITLE,
        "home": str(home),
        "repair_message": "Please audit the current runtime state from the admin dock.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an isolated admin E2E fixture runtime.")
    parser.add_argument("--home", required=True, help="DeepScientist home for the temporary fixture runtime.")
    parser.add_argument("--output", required=True, help="Path to write fixture JSON.")
    args = parser.parse_args()

    home = Path(args.home).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    fixture = build_fixture(home)
    output.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(fixture, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
