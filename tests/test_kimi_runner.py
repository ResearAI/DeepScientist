from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from deepscientist.config import ConfigManager
from deepscientist.runners import KimiRunner, RunRequest


def _runner(*, binary: str = "kimi") -> KimiRunner:
    return KimiRunner(
        home=Path("/tmp"),
        repo_root=Path("/tmp"),
        binary=binary,
        logger=SimpleNamespace(),
        prompt_builder=SimpleNamespace(),
        artifact_service=SimpleNamespace(),
    )


def test_kimi_runner_command_uses_stdin_print_mode(temp_home: Path) -> None:
    runner = KimiRunner(
        home=temp_home,
        repo_root=temp_home,
        binary="kimi",
        logger=SimpleNamespace(),
        prompt_builder=SimpleNamespace(),
        artifact_service=SimpleNamespace(),
    )
    request = RunRequest(
        quest_id="q-001",
        quest_root=temp_home,
        worktree_root=temp_home,
        run_id="run-001",
        skill_id="decision",
        message="hello",
        model="inherit",
        approval_policy="never",
        sandbox_mode="danger-full-access",
    )

    command = runner._build_command(
        request,
        "prompt",
        runner_config={"agent": "research", "thinking": True, "yolo": True},
    )

    assert command[0].endswith("kimi")
    assert "--print" in command
    assert "--input-format" in command and command[command.index("--input-format") + 1] == "text"
    assert "--output-format" in command and command[command.index("--output-format") + 1] == "stream-json"
    assert "--yolo" in command
    assert "--agent" in command and command[command.index("--agent") + 1] == "research"
    assert "--thinking" in command


def test_kimi_runner_prepare_runtime_materializes_home_and_mcp_config(temp_home: Path) -> None:
    quest_root = temp_home / "quest"
    source_home = temp_home / "source-kimi-home"
    (source_home / "skills" / "global-skill").mkdir(parents=True, exist_ok=True)
    (source_home / "skills" / "global-skill" / "SKILL.md").write_text("GLOBAL\n", encoding="utf-8")
    (quest_root / ".kimi" / "skills" / "quest-skill").mkdir(parents=True, exist_ok=True)
    (quest_root / ".kimi" / "skills" / "quest-skill" / "SKILL.md").write_text("QUEST\n", encoding="utf-8")

    runner = KimiRunner(
        home=temp_home,
        repo_root=temp_home,
        binary="kimi",
        logger=SimpleNamespace(),
        prompt_builder=SimpleNamespace(),
        artifact_service=SimpleNamespace(),
    )

    env, meta = runner._prepare_runtime(
        workspace_root=quest_root,
        quest_root=quest_root,
        quest_id="q-001",
        run_id="run-001",
        runner_config={"config_dir": str(source_home)},
    )

    mcp_config = Path(str(meta["kimi_mcp_config"]))
    payload = json.loads(mcp_config.read_text(encoding="utf-8"))
    assert env["HOME"].endswith("/runtime/runners/kimi/q-001/run-001")
    assert (Path(env["HOME"]) / ".kimi" / "skills" / "global-skill" / "SKILL.md").exists()
    assert (Path(env["HOME"]) / ".kimi" / "skills" / "quest-skill" / "SKILL.md").exists()
    assert not (Path(env["HOME"]) / ".kimi" / "sessions").exists()
    assert sorted(payload["mcpServers"]) == ["artifact", "bash_exec", "memory"]


def test_kimi_runner_translates_assistant_and_tool_messages() -> None:
    runner = _runner()
    state: dict[str, object] = {}

    assistant_events, texts = runner._translate_event(
        {
            "role": "assistant",
            "content": "DONE: hello",
            "tool_calls": [
                {
                    "id": "tool-1",
                    "function": {
                        "name": "mcp__artifact__get_quest_state",
                        "arguments": '{"detail":"summary"}',
                    },
                }
            ],
        },
        raw_line="",
        quest_id="q-001",
        run_id="run-001",
        skill_id="decision",
        created_at="2026-04-20T00:00:00Z",
        translation_state=state,
    )
    result_events, _ = runner._translate_event(
        {
            "role": "tool",
            "tool_call_id": "tool-1",
            "content": '{"quest_id":"q-001"}',
        },
        raw_line="",
        quest_id="q-001",
        run_id="run-001",
        skill_id="decision",
        created_at="2026-04-20T00:00:01Z",
        translation_state=state,
    )

    assert [event["type"] for event in assistant_events] == ["runner.agent_message", "runner.tool_call"]
    assert assistant_events[1]["tool_name"] == "mcp__artifact__get_quest_state"
    assert assistant_events[1]["mcp_server"] == "artifact"
    assert assistant_events[1]["mcp_tool"] == "get_quest_state"
    assert result_events[0]["tool_name"] == "mcp__artifact__get_quest_state"
    assert result_events[0]["mcp_server"] == "artifact"
    assert result_events[0]["mcp_tool"] == "get_quest_state"
    assert result_events[0]["output"] == '{"quest_id":"q-001"}'
    assert texts == ["DONE: hello"]


def test_kimi_probe_missing_binary_includes_login_guidance(monkeypatch, temp_home: Path) -> None:  # type: ignore[no-untyped-def]
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    monkeypatch.setattr("deepscientist.config.service.resolve_runner_binary", lambda binary, runner_name=None: None)

    result = manager._probe_kimi_runner({"binary": "kimi", "config_dir": "~/.kimi"})

    guidance_text = "\n".join(result["guidance"])
    assert result["ok"] is False
    assert "kimi login" in guidance_text
    assert "~/.kimi" in guidance_text
