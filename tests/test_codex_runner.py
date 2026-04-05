from __future__ import annotations

import json
from pathlib import Path

from deepscientist.runners import CodexRunner, RunRequest
from deepscientist.runners.codex import _compact_tool_event_payload, _message_events, _tool_event


def test_codex_message_events_preserve_stream_identity() -> None:
    delta_events, _ = _message_events(
        {
            "type": "response.output_text.delta",
            "item_id": "msg-123",
            "delta": "Working through the plan.",
        },
        quest_id="q-001",
        run_id="run-001",
        skill_id="baseline",
        created_at="2026-03-21T00:00:00Z",
    )
    final_events, _ = _message_events(
        {
            "type": "item.completed",
            "item_type": "agent_message",
            "item": {
                "type": "agent_message",
                "id": "msg-123",
                "content": [{"type": "output_text", "text": "Working through the plan."}],
            },
        },
        quest_id="q-001",
        run_id="run-001",
        skill_id="baseline",
        created_at="2026-03-21T00:00:01Z",
    )

    assert len(delta_events) == 1
    assert len(final_events) == 1
    assert delta_events[0]["type"] == "runner.delta"
    assert final_events[0]["type"] == "runner.agent_message"
    assert delta_events[0]["stream_id"] == "msg-123"
    assert final_events[0]["stream_id"] == "msg-123"
    assert delta_events[0]["message_id"] == "msg-123"
    assert final_events[0]["message_id"] == "msg-123"


def test_codex_tool_event_preserves_parseable_bash_exec_payload_and_metadata() -> None:
    long_log = "\n".join(f"line {index}" for index in range(600))
    result_payload = {
        "bash_id": "bash-123",
        "status": "completed",
        "command": "sed -n '1,220p' /tmp/example.txt",
        "workdir": "",
        "cwd": "/tmp/quest",
        "log": long_log,
        "exit_code": 0,
    }
    event = {
        "type": "item.completed",
        "item_type": "mcp_tool_call",
        "item": {
            "type": "mcp_tool_call",
            "id": "tool-123",
            "server": "bash_exec",
            "tool": "bash_exec",
            "status": "completed",
            "arguments": {
                "mode": "read",
                "id": "bash-123",
                "workdir": "/tmp/quest",
            },
            "result": {
                "structured_content": result_payload,
                "content": [{"type": "text", "text": json.dumps(result_payload, ensure_ascii=False)}],
            },
        },
    }

    rendered = _tool_event(
        event,
        quest_id="q-001",
        run_id="run-001",
        skill_id="baseline",
        known_tool_names={},
        created_at="2026-03-21T00:00:00Z",
    )

    assert rendered is not None
    assert rendered["type"] == "runner.tool_result"
    assert len(rendered["output"]) > 1200
    parsed_output = json.loads(rendered["output"])
    assert parsed_output["structured_content"]["bash_id"] == "bash-123"
    assert parsed_output["structured_content"]["log"] == long_log
    assert rendered["metadata"]["bash_id"] == "bash-123"
    assert rendered["metadata"]["command"] == "sed -n '1,220p' /tmp/example.txt"
    assert rendered["metadata"]["cwd"] == "/tmp/quest"


def test_codex_tool_event_truncates_oversized_bash_exec_log_but_keeps_json_parseable() -> None:
    long_log = "\n".join(f"line {index}: {'x' * 200}" for index in range(5000))
    result_payload = {
        "bash_id": "bash-oversized",
        "status": "completed",
        "command": "cat huge.log",
        "cwd": "/tmp/quest",
        "log": long_log,
        "exit_code": 0,
    }
    event = {
        "type": "item.completed",
        "item_type": "mcp_tool_call",
        "item": {
            "type": "mcp_tool_call",
            "id": "tool-oversized",
            "server": "bash_exec",
            "tool": "bash_exec",
            "status": "completed",
            "arguments": {"mode": "read", "id": "bash-oversized"},
            "result": {
                "structured_content": result_payload,
                "content": [{"type": "text", "text": json.dumps(result_payload, ensure_ascii=False)}],
            },
        },
    }

    rendered = _tool_event(
        event,
        quest_id="q-001",
        run_id="run-001",
        skill_id="baseline",
        known_tool_names={},
        created_at="2026-03-21T00:00:00Z",
    )

    assert rendered is not None
    parsed_output = json.loads(rendered["output"])
    truncated_log = parsed_output["structured_content"]["log"]
    assert len(truncated_log) < len(long_log)
    assert "[truncated " in truncated_log


def test_codex_compacts_extreme_tool_result_payload_before_event_write() -> None:
    huge_output = "x" * (3 * 1024 * 1024)
    payload = {
        "event_id": "evt-1",
        "type": "runner.tool_result",
        "quest_id": "q-001",
        "run_id": "run-001",
        "tool_name": "bash_exec.bash_exec",
        "output": huge_output,
        "metadata": {"bash_id": "bash-extreme", "command": "cat extreme.log"},
    }

    rendered = _compact_tool_event_payload(payload)

    assert rendered["type"] == "runner.tool_result"
    assert rendered["output_truncated"] is True
    assert rendered["output_bytes"] > 2_000_000
    assert len(str(rendered["output"])) < 20_000
    assert rendered["metadata"]["bash_id"] == "bash-extreme"


def test_codex_tool_event_carries_bash_id_from_id_only_monitor_call() -> None:
    event = {
        "type": "item.started",
        "item_type": "mcp_tool_call",
        "item": {
            "type": "mcp_tool_call",
            "id": "tool-456",
            "server": "bash_exec",
            "tool": "bash_exec",
            "status": "in_progress",
            "arguments": {
                "mode": "await",
                "id": "bash-456",
                "workdir": "/tmp/quest",
                "timeout_seconds": 75,
            },
        },
    }

    rendered = _tool_event(
        event,
        quest_id="q-001",
        run_id="run-001",
        skill_id="baseline",
        known_tool_names={},
        created_at="2026-03-21T00:00:00Z",
    )

    assert rendered is not None
    assert rendered["type"] == "runner.tool_call"
    assert json.loads(rendered["args"])["id"] == "bash-456"
    assert rendered["metadata"]["bash_id"] == "bash-456"
    assert rendered["metadata"]["mode"] == "await"
    assert rendered["metadata"]["timeout_seconds"] == 75


def test_codex_tool_event_surfaces_failed_mcp_error_message() -> None:
    event = {
        "type": "item.completed",
        "item_type": "mcp_tool_call",
        "item": {
            "type": "mcp_tool_call",
            "id": "tool-failed",
            "server": "artifact",
            "tool": "get_quest_state",
            "status": "failed",
            "arguments": {"detail": "summary"},
            "error": {"message": "user cancelled MCP tool call"},
        },
    }

    rendered = _tool_event(
        event,
        quest_id="q-001",
        run_id="run-001",
        skill_id="idea",
        known_tool_names={},
        created_at="2026-03-21T00:00:00Z",
    )

    assert rendered is not None
    assert rendered["type"] == "runner.tool_result"
    assert rendered["status"] == "failed"
    assert "user cancelled MCP tool call" in rendered["output"]


def test_codex_runner_injects_builtin_mcp_tool_approval_overrides(temp_home) -> None:  # type: ignore[no-untyped-def]
    source_codex_home = temp_home / "source-codex-home"
    source_codex_home.mkdir(parents=True, exist_ok=True)
    (source_codex_home / "config.toml").write_text('model_provider = "ananapi"\n', encoding="utf-8")
    (source_codex_home / "auth.json").write_text("{}\n", encoding="utf-8")

    quest_root = temp_home / "quest"
    quest_root.mkdir(parents=True, exist_ok=True)
    workspace_root = quest_root

    runner = CodexRunner(
        home=temp_home,
        repo_root=temp_home,
        binary="codex",
        logger=object(),  # type: ignore[arg-type]
        prompt_builder=object(),  # type: ignore[arg-type]
        artifact_service=object(),  # type: ignore[arg-type]
    )

    codex_home = runner._prepare_project_codex_home(
        workspace_root,
        quest_root=quest_root,
        quest_id="q-001",
        run_id="run-001",
        runner_config={"config_dir": str(source_codex_home)},
    )

    config_text = (codex_home / "config.toml").read_text(encoding="utf-8")
    assert 'transport = "stdio"' in config_text
    assert "[mcp_servers.artifact.tools.get_quest_state]" in config_text
    assert "[mcp_servers.memory.tools.list_recent]" in config_text
    assert "[mcp_servers.bash_exec.tools.bash_exec]" in config_text
    assert config_text.count('approval_mode = "approve"') >= 3


def test_codex_runner_omits_model_flag_when_request_uses_inherit(temp_home) -> None:  # type: ignore[no-untyped-def]
    runner = CodexRunner(
        home=temp_home,
        repo_root=temp_home,
        binary="codex",
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
        approval_policy="on-request",
        sandbox_mode="workspace-write",
        reasoning_effort="xhigh",
    )

    command = runner._build_command(request, "prompt", runner_config={})

    assert "--model" not in command


def test_codex_runner_includes_profile_when_runner_config_requests_it(temp_home) -> None:  # type: ignore[no-untyped-def]
    runner = CodexRunner(
        home=temp_home,
        repo_root=temp_home,
        binary="codex",
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
        approval_policy="on-request",
        sandbox_mode="workspace-write",
        reasoning_effort="xhigh",
    )

    command = runner._build_command(request, "prompt", runner_config={"profile": "m27"})

    assert command[1:4] == ["--search", "--profile", "m27"]


def test_codex_runner_downgrades_xhigh_for_legacy_codex_cli(monkeypatch, temp_home) -> None:  # type: ignore[no-untyped-def]
    runner = CodexRunner(
        home=temp_home,
        repo_root=temp_home,
        binary="codex",
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
        approval_policy="on-request",
        sandbox_mode="workspace-write",
        reasoning_effort="xhigh",
    )

    monkeypatch.setattr("deepscientist.runners.codex.resolve_runner_binary", lambda binary, runner_name=None: "/tmp/fake-codex")
    monkeypatch.setattr(
        "deepscientist.runners.codex.normalize_codex_reasoning_effort",
        lambda reasoning_effort, *, resolved_binary: ("high", "downgraded"),
    )

    command = runner._build_command(request, "prompt", runner_config={"profile": "m27"})

    assert '-c' in command
    assert 'model_reasoning_effort="high"' in command
    assert 'model_reasoning_effort="xhigh"' not in command


def test_codex_runner_prepares_project_home_from_runner_config_dir(temp_home) -> None:  # type: ignore[no-untyped-def]
    source_home = temp_home / "provider-codex-home"
    source_home.mkdir(parents=True, exist_ok=True)
    (source_home / "config.toml").write_text("[profiles.m27]\n", encoding="utf-8")
    (source_home / "auth.json").write_text('{"provider":"custom"}', encoding="utf-8")

    quest_root = temp_home / "quest"
    quest_root.mkdir(parents=True, exist_ok=True)
    workspace_root = quest_root / "workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)

    runner = CodexRunner(
        home=temp_home,
        repo_root=temp_home,
        binary="codex",
        logger=object(),  # type: ignore[arg-type]
        prompt_builder=object(),  # type: ignore[arg-type]
        artifact_service=object(),  # type: ignore[arg-type]
    )

    target = runner._prepare_project_codex_home(
        workspace_root,
        quest_root=quest_root,
        quest_id="q-001",
        run_id="run-001",
        runner_config={"config_dir": str(source_home)},
    )

    config_text = (Path(target) / "config.toml").read_text(encoding="utf-8")
    assert config_text.startswith("[profiles.m27]\n")
    assert "# BEGIN DEEPSCIENTIST BUILTINS" in config_text
    assert (Path(target) / "auth.json").read_text(encoding="utf-8") == '{"provider":"custom"}'


def test_codex_runner_prepares_project_home_overwrites_existing_provider_files(temp_home) -> None:  # type: ignore[no-untyped-def]
    source_home = temp_home / "provider-codex-home"
    source_home.mkdir(parents=True, exist_ok=True)
    (source_home / "config.toml").write_text("[profiles.m27]\nmodel = \"new-profile\"\n", encoding="utf-8")
    (source_home / "auth.json").write_text('{"provider":"new-auth"}', encoding="utf-8")

    quest_root = temp_home / "quest"
    quest_root.mkdir(parents=True, exist_ok=True)
    workspace_root = quest_root / "workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)
    target_home = workspace_root / ".codex"
    target_home.mkdir(parents=True, exist_ok=True)
    (target_home / "config.toml").write_text("[profiles.old]\nmodel = \"old-profile\"\n", encoding="utf-8")
    (target_home / "auth.json").write_text('{"provider":"old-auth"}', encoding="utf-8")

    runner = CodexRunner(
        home=temp_home,
        repo_root=temp_home,
        binary="codex",
        logger=object(),  # type: ignore[arg-type]
        prompt_builder=object(),  # type: ignore[arg-type]
        artifact_service=object(),  # type: ignore[arg-type]
    )

    target = runner._prepare_project_codex_home(
        workspace_root,
        quest_root=quest_root,
        quest_id="q-001",
        run_id="run-001",
        runner_config={"config_dir": str(source_home)},
    )

    config_text = (Path(target) / "config.toml").read_text(encoding="utf-8")
    assert 'model = "new-profile"' in config_text
    assert 'old-profile' not in config_text
    assert (Path(target) / "auth.json").read_text(encoding="utf-8") == '{"provider":"new-auth"}'


def test_codex_runner_prepares_project_home_adapting_profile_only_provider_config(temp_home) -> None:  # type: ignore[no-untyped-def]
    source_home = temp_home / "provider-codex-home"
    source_home.mkdir(parents=True, exist_ok=True)
    (source_home / "config.toml").write_text(
        """[model_providers.minimax]
name = "MiniMax Chat Completions API"
base_url = "https://api.minimaxi.com/v1"
env_key = "MINIMAX_API_KEY"
wire_api = "chat"
requires_openai_auth = false

[profiles.m27]
model = "MiniMax-M2.7"
model_provider = "minimax"
""",
        encoding="utf-8",
    )

    quest_root = temp_home / "quest"
    quest_root.mkdir(parents=True, exist_ok=True)
    workspace_root = quest_root / "workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)

    runner = CodexRunner(
        home=temp_home,
        repo_root=temp_home,
        binary="codex",
        logger=object(),  # type: ignore[arg-type]
        prompt_builder=object(),  # type: ignore[arg-type]
        artifact_service=object(),  # type: ignore[arg-type]
    )

    target = runner._prepare_project_codex_home(
        workspace_root,
        quest_root=quest_root,
        quest_id="q-001",
        run_id="run-001",
        runner_config={"config_dir": str(source_home), "profile": "m27"},
    )

    config_text = (Path(target) / "config.toml").read_text(encoding="utf-8")
    assert 'model_provider = "minimax"' in config_text
    assert 'model = "MiniMax-M2.7"' in config_text
