from __future__ import annotations

import json
from pathlib import Path

from deepscientist.claude_cli_compat import materialize_claude_runtime_home
from deepscientist.runners import ClaudeRunner, RunRequest
from deepscientist.runners.claude import _claude_events


def test_claude_runner_build_command_includes_mcp_config_and_allowed_tools(temp_home: Path) -> None:  # type: ignore[no-untyped-def]
    runner = ClaudeRunner(
        home=temp_home,
        repo_root=temp_home,
        binary="claude",
        logger=object(),  # type: ignore[arg-type]
        prompt_builder=object(),  # type: ignore[arg-type]
        artifact_service=object(),  # type: ignore[arg-type]
    )
    request = RunRequest(
        quest_id="q-001",
        quest_root=temp_home,
        worktree_root=None,
        run_id="run-001",
        skill_id="baseline",
        message="hello",
        model="inherit",
        approval_policy="never",
        sandbox_mode="danger-full-access",
    )

    command = runner._build_command(
        request,
        "prompt",
        mcp_config_path=temp_home / "claude-mcp.json",
        runner_config={},
    )

    assert Path(command[0]).name.lower() in {"claude", "claude.exe", "claude.cmd"}
    assert command[1] == "-p"
    assert "--tools" in command
    assert command[command.index("--tools") + 1] == ""
    assert "--mcp-config" in command
    assert "--strict-mcp-config" in command
    assert "mcp__memory,mcp__artifact,mcp__bash_exec" in command
    assert "--model" not in command


def test_claude_runner_writes_project_scoped_mcp_config(temp_home: Path) -> None:  # type: ignore[no-untyped-def]
    quest_root = temp_home / "quest"
    quest_root.mkdir(parents=True, exist_ok=True)
    (quest_root / "quest.yaml").write_text("active_anchor: baseline\n", encoding="utf-8")
    runner = ClaudeRunner(
        home=temp_home,
        repo_root=temp_home,
        binary="claude",
        logger=object(),  # type: ignore[arg-type]
        prompt_builder=object(),  # type: ignore[arg-type]
        artifact_service=object(),  # type: ignore[arg-type]
    )

    path = runner._write_mcp_config(
        temp_home / "claude-mcp.json",
        quest_root=quest_root,
        workspace_root=quest_root,
        quest_id="q-001",
        run_id="run-001",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert sorted(payload["mcpServers"]) == ["artifact", "bash_exec", "memory"]
    assert payload["mcpServers"]["artifact"]["args"] == ["-m", "deepscientist.mcp.server", "--namespace", "artifact"]
    assert payload["mcpServers"]["memory"]["env"]["DS_QUEST_ID"] == "q-001"


def test_claude_events_map_mcp_tool_use_and_result() -> None:
    assistant_payload = {
        "type": "assistant",
        "message": {
            "id": "msg-001",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "mcp__bash_exec__bash_exec",
                    "input": {"mode": "read", "id": "bash-123"},
                }
            ],
        },
    }
    user_payload = {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_123",
                    "content": json.dumps({"bash_id": "bash-123", "status": "completed", "exit_code": 0}),
                }
            ]
        },
    }
    known_tool_names: dict[str, str] = {}

    assistant_events, _ = _claude_events(
        assistant_payload,
        quest_id="q-001",
        run_id="run-001",
        skill_id="baseline",
        known_tool_names=known_tool_names,
        created_at="2026-04-13T00:00:00Z",
    )
    result_events, _ = _claude_events(
        user_payload,
        quest_id="q-001",
        run_id="run-001",
        skill_id="baseline",
        known_tool_names=known_tool_names,
        created_at="2026-04-13T00:00:01Z",
    )

    assert assistant_events[0]["type"] == "runner.tool_call"
    assert assistant_events[0]["metadata"]["bash_id"] == "bash-123"
    assert result_events[0]["type"] == "runner.tool_result"
    assert result_events[0]["metadata"]["bash_id"] == "bash-123"
    assert '"status": "completed"' in result_events[0]["output"]


def test_claude_events_emit_agent_message_from_text_blocks() -> None:
    payload = {
        "type": "assistant",
        "message": {
            "id": "msg-002",
            "content": [
                {"type": "text", "text": "Hello from Claude."},
                {"type": "text", "text": "Second line."},
            ],
        },
    }

    events, outputs = _claude_events(
        payload,
        quest_id="q-001",
        run_id="run-001",
        skill_id="write",
        known_tool_names={},
        created_at="2026-04-13T00:00:00Z",
    )

    assert outputs == ["Hello from Claude.\nSecond line."]
    assert events[0]["type"] == "runner.agent_message"
    assert events[0]["stream_id"] == "msg-002"


def test_materialize_claude_runtime_home_bootstraps_onboarding_json(tmp_path: Path) -> None:
    source_home = tmp_path / "source-home" / ".claude"
    source_home.mkdir(parents=True, exist_ok=True)
    materialize_claude_runtime_home(
        source_home=source_home,
        target_home=tmp_path / "target-home",
    )

    payload = json.loads((tmp_path / "target-home" / ".claude.json").read_text(encoding="utf-8"))
    assert payload["hasCompletedOnboarding"] is True
