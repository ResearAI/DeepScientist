from __future__ import annotations

import argparse
import json
from pathlib import Path

from deepscientist.artifact import ArtifactService
from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.quest import QuestService
from deepscientist.shared import append_jsonl, write_text, write_yaml
from deepscientist.skills import SkillInstaller


FIXTURE_QUEST_ID = "e2e-copilot-workspace"
READNOW_FIXTURE_QUEST_ID = "e2e-copilot-workspace-readnow"
WITHDRAW_FIXTURE_QUEST_ID = "e2e-copilot-workspace-withdraw"
AGENT_READNOW_FIXTURE_QUEST_ID = "e2e-copilot-agent-readnow"
AGENT_WITHDRAW_FIXTURE_QUEST_ID = "e2e-copilot-agent-withdraw"
FIRST_SUBJECT = "seed copilot workspace fixture"
LATEST_SUBJECT = "copilot fixture second commit"
CHANGED_PATH = "copilot_notes.md"
SECOND_PATH = "analysis_outline.md"
STUDIO_LINK_PATH = "studio_link_target.txt"
SNAPSHOT_HEADING = "Copilot Workspace Fixture"
STUDIO_LINK_TEXT = "studio_link_target.txt"
JUMP_TARGET_PATH = "zz-jump-targets/alpha/beta/gamma/final-note.md"
JUMP_TARGET_FOLDER = "zz-jump-targets/alpha/beta/gamma"
HIDDEN_JUMP_TARGET_PATH = ".jump-hidden/secret-note.md"
STUDIO_LINK_CONTENT = """Studio link target E2E content.

This line confirms the workspace opened the linked file in a center tab.
"""
STUDIO_LINK_MESSAGE = (
    "The durable note is available at "
    f"[{STUDIO_LINK_TEXT}]({STUDIO_LINK_PATH}). "
    "Open it from Studio."
)
UNREAD_MESSAGE = "Please inspect this queued note immediately."

BASE_CONTENT = f"""# {SNAPSHOT_HEADING}

This file exists so the Copilot git canvas can open a real commit snapshot.
"""

UPDATED_CONTENT = f"""# {SNAPSHOT_HEADING}

This file exists so the Copilot git canvas can open a real commit snapshot.

- Added a second durable note for the commit viewer.
- Explorer scope should resolve against this commit snapshot.
"""

SECOND_CONTENT = """# Analysis Outline

1. Compare baseline.
2. Inspect regression cases.
3. Record the next user-approved action.
"""
JUMP_TARGET_CONTENT = """# Final Note

This file exists so the Explorer path bar can reveal a deep nested file and force the tree to scroll.
"""
HIDDEN_JUMP_TARGET_CONTENT = """# Hidden Note

This path exists so the Explorer reveal flow can unhide dotfiles when needed.
"""
AGENT_START_MESSAGE = "Start active agent e2e."
AGENT_REPLY_TEXT = "Queued note inspected."
TOOL_FIXTURE_RUN_ID = "run-copilot-tools"


def append_tool_fixture_events(quest_root: Path) -> None:
    events_path = quest_root / ".ds" / "events.jsonl"
    artifact_args = json.dumps({"detail": "summary"}, ensure_ascii=False)
    artifact_output = json.dumps(
        {
            "quest_id": FIXTURE_QUEST_ID,
            "status": "idle",
            "active_anchor": "decision",
        },
        ensure_ascii=False,
    )
    bash_args = json.dumps({"command": "pwd", "workdir": "."}, ensure_ascii=False)
    bash_output = json.dumps(
        {
            "bash_id": "bash-e2e-1",
            "status": "completed",
            "command": "pwd",
            "cwd": "/tmp/e2e-copilot-workspace",
            "log": "/tmp/e2e-copilot-workspace",
            "exit_code": 0,
        },
        ensure_ascii=False,
    )
    append_jsonl(
        events_path,
        {
            "event_id": "evt-reasoning-1",
            "type": "runner.reasoning",
            "quest_id": FIXTURE_QUEST_ID,
            "run_id": TOOL_FIXTURE_RUN_ID,
            "source": "claude",
            "skill_id": "decision",
            "text": "Thinking through the benchmark handoff before using tools.",
            "created_at": "2026-04-14T11:59:59Z",
        },
    )
    for event in (
        {
            "event_id": "evt-tool-call-artifact",
            "type": "runner.tool_call",
            "quest_id": FIXTURE_QUEST_ID,
            "run_id": TOOL_FIXTURE_RUN_ID,
            "source": "claude",
            "skill_id": "decision",
            "tool_call_id": "tool-artifact-1",
            "tool_name": "mcp__artifact__get_quest_state",
            "mcp_server": "artifact",
            "mcp_tool": "get_quest_state",
            "status": "calling",
            "args": artifact_args,
            "created_at": "2026-04-14T12:00:00Z",
        },
        {
            "event_id": "evt-tool-result-artifact",
            "type": "runner.tool_result",
            "quest_id": FIXTURE_QUEST_ID,
            "run_id": TOOL_FIXTURE_RUN_ID,
            "source": "claude",
            "skill_id": "decision",
            "tool_call_id": "tool-artifact-1",
            "tool_name": "mcp__artifact__get_quest_state",
            "mcp_server": "artifact",
            "mcp_tool": "get_quest_state",
            "status": "completed",
            "args": artifact_args,
            "output": artifact_output,
            "created_at": "2026-04-14T12:00:01Z",
        },
        {
            "event_id": "evt-tool-call-bash",
            "type": "runner.tool_call",
            "quest_id": FIXTURE_QUEST_ID,
            "run_id": TOOL_FIXTURE_RUN_ID,
            "source": "claude",
            "skill_id": "decision",
            "tool_call_id": "tool-bash-1",
            "tool_name": "mcp__bash_exec__bash_exec",
            "mcp_server": "bash_exec",
            "mcp_tool": "bash_exec",
            "status": "calling",
            "args": bash_args,
            "created_at": "2026-04-14T12:00:02Z",
        },
        {
            "event_id": "evt-tool-result-bash",
            "type": "runner.tool_result",
            "quest_id": FIXTURE_QUEST_ID,
            "run_id": TOOL_FIXTURE_RUN_ID,
            "source": "claude",
            "skill_id": "decision",
            "tool_call_id": "tool-bash-1",
            "tool_name": "mcp__bash_exec__bash_exec",
            "mcp_server": "bash_exec",
            "mcp_tool": "bash_exec",
            "status": "completed",
            "args": bash_args,
            "output": bash_output,
            "created_at": "2026-04-14T12:00:03Z",
        },
    ):
        append_jsonl(events_path, event)


def install_fake_codex(home: Path, config_manager: ConfigManager) -> Path:
    bin_dir = home / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake_codex = bin_dir / "codex"
    fake_codex.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json",
                "import sys",
                "import time",
                "",
                "prompt = sys.stdin.read()",
                "if 'turn_reason: immediate_read' in prompt:",
                "    print(json.dumps({'type': 'item.completed', 'item_type': 'agent_message', 'item': {'type': 'agent_message', 'id': 'msg-queued-note', 'content': [{'type': 'output_text', 'text': 'Queued note inspected.'}]}}), flush=True)",
                "    sys.exit(0)",
                "if 'Start active agent e2e.' in prompt and 'turn_reason: user_message' in prompt:",
                "    print(json.dumps({'type': 'response.output_text.delta', 'item_id': 'msg-long-run', 'delta': 'Working through the queued task.'}), flush=True)",
                "    time.sleep(60)",
                "    sys.exit(0)",
                "if 'Please inspect this queued note immediately.' in prompt:",
                "    print(json.dumps({'type': 'item.completed', 'item_type': 'agent_message', 'item': {'type': 'agent_message', 'id': 'msg-queued-note-fallback', 'content': [{'type': 'output_text', 'text': 'Queued note inspected.'}]}}), flush=True)",
                "    sys.exit(0)",
                "print(json.dumps({'type': 'item.completed', 'item_type': 'agent_message', 'item': {'type': 'agent_message', 'id': 'msg-generic', 'content': [{'type': 'output_text', 'text': 'Generic completion.'}]}}), flush=True)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)

    runners = config_manager.load_named("runners")
    codex = dict(runners.get("codex") or {})
    codex["binary"] = str(fake_codex)
    codex["retry_on_failure"] = False
    runners["codex"] = codex
    write_yaml(config_manager.path_for("runners"), runners)
    return fake_codex


def create_workspace_fixture_quest(
    *,
    quest_service: QuestService,
    artifact: ArtifactService,
    quest_id: str,
    title: str,
    unread_message: str | None = None,
) -> dict[str, object]:
    quest = quest_service.create(
        title,
        quest_id=quest_id,
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

    write_text(quest_root / CHANGED_PATH, BASE_CONTENT)
    artifact.checkpoint(quest_root, FIRST_SUBJECT)

    write_text(quest_root / CHANGED_PATH, UPDATED_CONTENT)
    write_text(quest_root / SECOND_PATH, SECOND_CONTENT)
    write_text(quest_root / STUDIO_LINK_PATH, STUDIO_LINK_CONTENT)
    for index in range(28):
        write_text(
            quest_root / f"aa-jump-pad-{index:02d}" / "README.md",
            f"# Jump Pad {index:02d}\n",
        )
    write_text(quest_root / JUMP_TARGET_PATH, JUMP_TARGET_CONTENT)
    write_text(quest_root / HIDDEN_JUMP_TARGET_PATH, HIDDEN_JUMP_TARGET_CONTENT)
    artifact.checkpoint(quest_root, LATEST_SUBJECT)
    quest_service.append_message(
        quest["quest_id"],
        role="assistant",
        content=STUDIO_LINK_MESSAGE,
        source="fixture",
    )
    if quest["quest_id"] == FIXTURE_QUEST_ID:
        append_tool_fixture_events(quest_root)
    if unread_message:
        quest_service.append_message(
            quest["quest_id"],
            role="user",
            content=unread_message,
            source="web-react",
            client_message_id=f"{quest_id}-unread-message",
        )

    return {
        "quest_id": quest["quest_id"],
        "quest_root": str(quest_root),
    }


def build_fixture(home: Path) -> dict[str, object]:
    ensure_home_layout(home)
    config_manager = ConfigManager(home)
    config_manager.ensure_files()
    config = config_manager.load_named("config")
    config["default_locale"] = "en-US"
    write_yaml(config_manager.path_for("config"), config)
    fake_codex_path = install_fake_codex(home, config_manager)

    installer = SkillInstaller(repo_root(), home)
    quest_service = QuestService(home, skill_installer=installer)
    artifact = ArtifactService(home)

    route_fixture = create_workspace_fixture_quest(
        quest_service=quest_service,
        artifact=artifact,
        quest_id=FIXTURE_QUEST_ID,
        title="Copilot workspace E2E fixture",
    )
    readnow_fixture = create_workspace_fixture_quest(
        quest_service=quest_service,
        artifact=artifact,
        quest_id=READNOW_FIXTURE_QUEST_ID,
        title="Copilot workspace read-now E2E fixture",
        unread_message=UNREAD_MESSAGE,
    )
    withdraw_fixture = create_workspace_fixture_quest(
        quest_service=quest_service,
        artifact=artifact,
        quest_id=WITHDRAW_FIXTURE_QUEST_ID,
        title="Copilot workspace withdraw E2E fixture",
        unread_message=UNREAD_MESSAGE,
    )
    agent_readnow_fixture = create_workspace_fixture_quest(
        quest_service=quest_service,
        artifact=artifact,
        quest_id=AGENT_READNOW_FIXTURE_QUEST_ID,
        title="Copilot agent read-now E2E fixture",
    )
    agent_withdraw_fixture = create_workspace_fixture_quest(
        quest_service=quest_service,
        artifact=artifact,
        quest_id=AGENT_WITHDRAW_FIXTURE_QUEST_ID,
        title="Copilot agent withdraw E2E fixture",
    )

    return {
        "quest_id": route_fixture["quest_id"],
        "quest_root": route_fixture["quest_root"],
        "readnow_quest_id": readnow_fixture["quest_id"],
        "withdraw_quest_id": withdraw_fixture["quest_id"],
        "agent_readnow_quest_id": agent_readnow_fixture["quest_id"],
        "agent_withdraw_quest_id": agent_withdraw_fixture["quest_id"],
        "agent_start_message": AGENT_START_MESSAGE,
        "agent_reply_text": AGENT_REPLY_TEXT,
        "latest_subject": LATEST_SUBJECT,
        "changed_path": CHANGED_PATH,
        "snapshot_heading": SNAPSHOT_HEADING,
        "jump_target_path": JUMP_TARGET_PATH,
        "jump_target_folder": JUMP_TARGET_FOLDER,
        "hidden_jump_target_path": HIDDEN_JUMP_TARGET_PATH,
        "studio_link_path": STUDIO_LINK_PATH,
        "studio_link_text": STUDIO_LINK_TEXT,
        "studio_link_content": STUDIO_LINK_CONTENT.strip(),
        "unread_message": UNREAD_MESSAGE,
        "fake_codex_path": str(fake_codex_path),
        "home": str(home),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an isolated Copilot workspace E2E fixture quest.")
    parser.add_argument("--home", required=True, help="DeepScientist home for the temporary fixture runtime.")
    parser.add_argument("--output", required=True, help="Path to write the fixture JSON.")
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
