from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from deepscientist.artifact import ArtifactService
from deepscientist.config import ConfigManager
from deepscientist.diagnostics.runner_failures import diagnose_runner_failure
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.quest import QuestService
from deepscientist.runners import ClaudeRunner, CodexRunner, OpenCodeRunner, RunRequest
from deepscientist.runners.codex import (
    _compact_tool_event_payload,
    _message_events,
    _sanitize_text_for_windows_gbk,
    _tool_event,
)
from deepscientist.runners.runtime_overrides import apply_claude_runtime_overrides
from deepscientist.shared import read_json, read_jsonl, read_yaml, write_yaml
from deepscientist.skills import SkillInstaller


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


def test_sanitize_text_for_windows_gbk_replaces_unencodable_symbols_only() -> None:
    original = "Keep Chinese 中文, but replace bullet • and sparkles ✨ and kaomoji (•̀ᴗ•́)و."

    sanitized, replacements = _sanitize_text_for_windows_gbk(original)

    sanitized.encode("gbk")
    assert "中文" in sanitized
    assert "•" not in sanitized
    assert "✨" not in sanitized
    assert replacements["•"] == "-"
    assert replacements["✨"] == "*"


def test_diagnose_runner_failure_recognizes_windows_gbk_prompt_encoding_error() -> None:
    diagnosis = diagnose_runner_failure(
        runner_name="codex",
        summary=(
            "Runner codex failed on attempt 5/5: "
            "'gbk' codec can't encode character '\\u2022' in position 18706: illegal multibyte sequence"
        ),
    )

    assert diagnosis is not None
    assert diagnosis.code == "windows_gbk_prompt_encoding_error"
    assert diagnosis.retriable is False


def test_diagnose_runner_failure_recognizes_claude_authentication_failure() -> None:
    diagnosis = diagnose_runner_failure(
        runner_name="claude",
        summary=(
            "Failed to authenticate. API Error: 401 "
            '{"type":"error","error":{"type":"authentication_error",'
            '"message":"Invalid authentication credentials"},"request_id":"req_abc"}'
        ),
    )

    assert diagnosis is not None
    assert diagnosis.code == "claude_authentication_failed"
    assert diagnosis.retriable is False
    # Guidance should mention both recovery paths.
    joined_guidance = "\n".join(diagnosis.guidance).lower()
    assert "claude login" in joined_guidance
    assert "anthropic_api_key" in joined_guidance


def test_diagnose_runner_failure_does_not_match_codex_401() -> None:
    # Make sure the claude-scoped pattern does not pull in unrelated codex 401s.
    diagnosis = diagnose_runner_failure(
        runner_name="codex",
        summary="HTTP 401 Unauthorized when calling provider X",
    )

    assert diagnosis is None or diagnosis.code != "claude_authentication_failed"


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
    assert f'DEEPSCIENTIST_REPO_ROOT = "{str(temp_home)}"' in config_text
    assert 'PYTHONIOENCODING = "utf-8"' in config_text
    assert 'PYTHONUTF8 = "1"' in config_text
    assert "[mcp_servers.bash_exec.tools.bash_exec]" in config_text
    assert config_text.count('approval_mode = "approve"') >= 3


def test_codex_runner_restricts_settings_issue_profile_to_issue_tool_and_bash_exec_only(temp_home) -> None:  # type: ignore[no-untyped-def]
    source_codex_home = temp_home / "source-codex-home"
    source_codex_home.mkdir(parents=True, exist_ok=True)
    (source_codex_home / "config.toml").write_text('model_provider = "ananapi"\n', encoding="utf-8")
    (source_codex_home / "auth.json").write_text("{}\n", encoding="utf-8")

    quest_root = temp_home / "quest-settings-issue"
    quest_root.mkdir(parents=True, exist_ok=True)
    write_yaml(
        quest_root / "quest.yaml",
        {
            "quest_id": "q-settings-issue",
            "title": "Settings issue quest",
            "startup_contract": {
                "launch_mode": "custom",
                "custom_profile": "settings_issue",
            },
        },
    )
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
        quest_id="q-settings-issue",
        run_id="run-settings-issue",
        runner_config={"config_dir": str(source_codex_home)},
    )

    config_text = (codex_home / "config.toml").read_text(encoding="utf-8")
    assert "[mcp_servers.artifact]" in config_text
    assert "[mcp_servers.artifact.tools.prepare_github_issue]" in config_text
    assert "[mcp_servers.bash_exec]" in config_text
    assert "[mcp_servers.bash_exec.tools.bash_exec]" in config_text
    assert 'DS_CUSTOM_PROFILE = "settings_issue"' in config_text
    assert "[mcp_servers.memory]" not in config_text


def test_codex_runner_restricts_start_setup_session_to_prepare_form_and_bash_exec_only(temp_home) -> None:  # type: ignore[no-untyped-def]
    source_codex_home = temp_home / "source-codex-home"
    source_codex_home.mkdir(parents=True, exist_ok=True)
    (source_codex_home / "config.toml").write_text('model_provider = "ananapi"\n', encoding="utf-8")
    (source_codex_home / "auth.json").write_text("{}\n", encoding="utf-8")

    quest_root = temp_home / "quest-start-setup"
    quest_root.mkdir(parents=True, exist_ok=True)
    write_yaml(
        quest_root / "quest.yaml",
        {
            "quest_id": "q-start-setup",
            "title": "Start setup quest",
            "startup_contract": {
                "launch_mode": "custom",
                "custom_profile": "freeform",
                "start_setup_session": {
                    "source": "benchstore",
                    "locale": "zh",
                },
            },
        },
    )

    runner = CodexRunner(
        home=temp_home,
        repo_root=temp_home,
        binary="codex",
        logger=object(),  # type: ignore[arg-type]
        prompt_builder=object(),  # type: ignore[arg-type]
        artifact_service=object(),  # type: ignore[arg-type]
    )

    codex_home = runner._prepare_project_codex_home(
        quest_root,
        quest_root=quest_root,
        quest_id="q-start-setup",
        run_id="run-start-setup",
        runner_config={"config_dir": str(source_codex_home)},
    )

    config_text = (codex_home / "config.toml").read_text(encoding="utf-8")
    assert "[mcp_servers.artifact]" in config_text
    assert "[mcp_servers.artifact.tools.prepare_start_setup_form]" in config_text
    assert "[mcp_servers.bash_exec]" in config_text
    assert 'DS_CUSTOM_PROFILE = "start_setup_prepare"' in config_text
    assert "[mcp_servers.memory]" not in config_text


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


def test_codex_runner_limits_timeout_overrides_to_active_builtin_servers_for_start_setup(temp_home) -> None:  # type: ignore[no-untyped-def]
    quest_root = temp_home / "quest"
    quest_root.mkdir(parents=True, exist_ok=True)
    write_yaml(
        quest_root / "quest.yaml",
        {
            "quest_id": "q-start-setup",
            "title": "start setup",
            "startup_contract": {
                "custom_profile": "freeform",
                "start_setup_session": {"source": "benchstore"},
            },
        },
    )
    runner = CodexRunner(
        home=temp_home,
        repo_root=temp_home,
        binary="codex",
        logger=object(),  # type: ignore[arg-type]
        prompt_builder=object(),  # type: ignore[arg-type]
        artifact_service=object(),  # type: ignore[arg-type]
    )
    request = RunRequest(
        quest_id="q-start-setup",
        quest_root=quest_root,
        worktree_root=None,
        run_id="run-start-setup",
        skill_id="scout",
        message="hello",
        model="gpt-5.4",
        approval_policy="never",
        sandbox_mode="danger-full-access",
        reasoning_effort="xhigh",
    )

    command = runner._build_command(request, "prompt", runner_config={"mcp_tool_timeout_sec": 180000})
    rendered = " ".join(command)

    assert "mcp_servers.artifact.tool_timeout_sec=180000" in rendered
    assert "mcp_servers.bash_exec.tool_timeout_sec=180000" in rendered
    assert "mcp_servers.memory.tool_timeout_sec=180000" not in rendered


def test_codex_runner_applies_start_setup_patch_fallback_block(temp_home) -> None:  # type: ignore[no-untyped-def]
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create(
        "start setup fallback patch quest",
        startup_contract={
            "workspace_mode": "copilot",
            "launch_mode": "custom",
            "custom_profile": "freeform",
            "start_setup_session": {
                "source": "benchstore",
                "locale": "zh",
                "suggested_form": {
                    "title": "Original title",
                },
            },
        },
    )
    quest_root = Path(quest["quest_root"])
    runner = CodexRunner(
        home=temp_home,
        repo_root=temp_home,
        binary="codex",
        logger=SimpleNamespace(log=lambda *args, **kwargs: None),
        prompt_builder=object(),  # type: ignore[arg-type]
        artifact_service=ArtifactService(temp_home),
    )
    request = RunRequest(
        quest_id=quest["quest_id"],
        quest_root=quest_root,
        worktree_root=None,
        run_id="run-fallback-patch",
        skill_id="scout",
        message="help",
        model="gpt-5.4",
        approval_policy="never",
        sandbox_mode="danger-full-access",
    )

    runner._apply_start_setup_patch_fallback_if_present(
        request=request,
        output_text=(
            "我先整理出一版草案。\n\n```start_setup_patch\n"
            "{\"title\":\"Patched title\",\"goal\":\"Patched goal\"}\n```"
        ),
        quest_events=quest_root / ".ds" / "events.jsonl",
    )

    quest_yaml = read_yaml(quest_root / "quest.yaml", {})
    startup_contract = quest_yaml.get("startup_contract") if isinstance(quest_yaml.get("startup_contract"), dict) else {}
    start_setup_session = startup_contract.get("start_setup_session") if isinstance(startup_contract.get("start_setup_session"), dict) else {}
    suggested_form = start_setup_session.get("suggested_form") if isinstance(start_setup_session.get("suggested_form"), dict) else {}

    assert suggested_form["title"] == "Patched title"
    assert suggested_form["goal"] == "Patched goal"


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
    (source_home / "skills" / "global-skill").mkdir(parents=True, exist_ok=True)
    (source_home / "skills" / "global-skill" / "SKILL.md").write_text("GLOBAL\n", encoding="utf-8")
    (source_home / "agents").mkdir(parents=True, exist_ok=True)
    (source_home / "agents" / "global-agent.md").write_text("GLOBAL AGENT\n", encoding="utf-8")
    (source_home / "prompts").mkdir(parents=True, exist_ok=True)
    (source_home / "prompts" / "system.md").write_text("GLOBAL PROMPT\n", encoding="utf-8")
    (source_home / "prompts" / "extra.md").write_text("GLOBAL EXTRA\n", encoding="utf-8")

    quest_root = temp_home / "quest"
    quest_root.mkdir(parents=True, exist_ok=True)
    (quest_root / ".codex" / "skills" / "quest-skill").mkdir(parents=True, exist_ok=True)
    (quest_root / ".codex" / "skills" / "quest-skill" / "SKILL.md").write_text("QUEST\n", encoding="utf-8")
    (quest_root / ".codex" / "prompts").mkdir(parents=True, exist_ok=True)
    (quest_root / ".codex" / "prompts" / "system.md").write_text("QUEST PROMPT\n", encoding="utf-8")
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

    assert Path(target) == workspace_root / ".ds" / "codex-home"
    config_text = (Path(target) / "config.toml").read_text(encoding="utf-8")
    assert config_text.startswith("[profiles.m27]\n")
    assert "# BEGIN DEEPSCIENTIST BUILTINS" in config_text
    assert (Path(target) / "auth.json").read_text(encoding="utf-8") == '{"provider":"custom"}'
    assert (Path(target) / "skills" / "global-skill" / "SKILL.md").read_text(encoding="utf-8") == "GLOBAL\n"
    assert (Path(target) / "skills" / "quest-skill" / "SKILL.md").read_text(encoding="utf-8") == "QUEST\n"
    assert (Path(target) / "agents" / "global-agent.md").read_text(encoding="utf-8") == "GLOBAL AGENT\n"
    assert (Path(target) / "prompts" / "system.md").read_text(encoding="utf-8") == "QUEST PROMPT\n"
    assert (Path(target) / "prompts" / "extra.md").read_text(encoding="utf-8") == "GLOBAL EXTRA\n"


def test_codex_runner_prepares_project_home_overwrites_existing_provider_files(temp_home) -> None:  # type: ignore[no-untyped-def]
    source_home = temp_home / "provider-codex-home"
    source_home.mkdir(parents=True, exist_ok=True)
    (source_home / "config.toml").write_text("[profiles.m27]\nmodel = \"new-profile\"\n", encoding="utf-8")
    (source_home / "auth.json").write_text('{"provider":"new-auth"}', encoding="utf-8")

    quest_root = temp_home / "quest"
    quest_root.mkdir(parents=True, exist_ok=True)
    workspace_root = quest_root / "workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)
    target_home = workspace_root / ".ds" / "codex-home"
    target_home.mkdir(parents=True, exist_ok=True)
    (target_home / "config.toml").write_text("[profiles.old]\nmodel = \"old-profile\"\n", encoding="utf-8")
    (target_home / "auth.json").write_text('{"provider":"old-auth"}', encoding="utf-8")
    (target_home / "agents").mkdir(parents=True, exist_ok=True)
    (target_home / "agents" / "stale-agent.md").write_text("stale\n", encoding="utf-8")

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
    assert not (Path(target) / "agents").exists()


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


def test_codex_runner_appends_single_tool_guard_for_chat_wire_profile(temp_home) -> None:  # type: ignore[no-untyped-def]
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

    runner = CodexRunner(
        home=temp_home,
        repo_root=temp_home,
        binary="codex",
        logger=object(),  # type: ignore[arg-type]
        prompt_builder=object(),  # type: ignore[arg-type]
        artifact_service=object(),  # type: ignore[arg-type]
    )

    prompt = runner._apply_chat_wire_tool_call_guard(
        "BASE PROMPT",
        runner_config={"config_dir": str(source_home), "profile": "m27"},
    )

    assert "BASE PROMPT" in prompt
    assert "## Codex Chat-Wire Tool Call Compatibility" in prompt
    assert "active_provider_profile: m27" in prompt
    assert "single_tool_call_per_turn_rule" in prompt
    assert "no_batched_mcp_rule" in prompt
    assert "no_immediate_repeat_rule" in prompt
    assert "state_recovery_preference_rule" in prompt
    assert "bash_exec_after_context_rule" in prompt


def test_codex_runner_skips_single_tool_guard_for_non_chat_profile(temp_home) -> None:  # type: ignore[no-untyped-def]
    source_home = temp_home / "provider-codex-home"
    source_home.mkdir(parents=True, exist_ok=True)
    (source_home / "config.toml").write_text(
        """[model_providers.local]
name = "Local Responses"
base_url = "http://127.0.0.1:8004/v1"
env_key = "LOCAL_API_KEY"
wire_api = "responses"
requires_openai_auth = false

[profiles.local]
model = "gpt-oss"
model_provider = "local"
""",
        encoding="utf-8",
    )

    runner = CodexRunner(
        home=temp_home,
        repo_root=temp_home,
        binary="codex",
        logger=object(),  # type: ignore[arg-type]
        prompt_builder=object(),  # type: ignore[arg-type]
        artifact_service=object(),  # type: ignore[arg-type]
    )

    prompt = runner._apply_chat_wire_tool_call_guard(
        "BASE PROMPT",
        runner_config={"config_dir": str(source_home), "profile": "local"},
    )

    assert prompt == "BASE PROMPT"


def test_codex_runner_subprocess_popen_kwargs_hide_windows_console(monkeypatch, temp_home) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, object] = {}

    def fake_process_session_popen_kwargs(*, hide_window: bool = False, new_process_group: bool = True):  # noqa: ANN001
        captured["hide_window"] = hide_window
        captured["new_process_group"] = new_process_group
        return {"creationflags": 1536, "startupinfo": object()}

    monkeypatch.setattr("deepscientist.runners.codex.process_session_popen_kwargs", fake_process_session_popen_kwargs)

    kwargs = CodexRunner._subprocess_popen_kwargs(
        workspace_root=Path(temp_home),
        env={"TEST_ENV": "1"},
    )

    assert captured["hide_window"] is True
    assert captured["new_process_group"] is True
    assert kwargs["cwd"] == str(temp_home)
    assert kwargs["env"] == {"TEST_ENV": "1"}
    assert kwargs["text"] is True
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["creationflags"] == 1536
    assert "startupinfo" in kwargs



def test_claude_runner_preserves_mcp_identity_on_tool_results() -> None:
    runner = ClaudeRunner(
        home=Path('/tmp'),
        repo_root=Path('/tmp'),
        binary='claude',
        logger=SimpleNamespace(),
        prompt_builder=SimpleNamespace(),
        artifact_service=SimpleNamespace(),
    )
    state: dict[str, object] = {}

    tool_call_events, _ = runner._translate_event(
        {
            'type': 'assistant',
            'message': {
                'id': 'msg-1',
                'content': [
                    {
                        'type': 'tool_use',
                        'id': 'tool-1',
                        'name': 'mcp__artifact__get_quest_state',
                        'input': {'detail': 'summary'},
                    }
                ],
            },
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:00Z',
        translation_state=state,
    )
    tool_result_events, _ = runner._translate_event(
        {
            'type': 'user',
            'message': {
                'content': [
                    {
                        'type': 'tool_result',
                        'tool_use_id': 'tool-1',
                        'content': [{'type': 'text', 'text': '{"ok": true}'}],
                    }
                ],
            },
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:01Z',
        translation_state=state,
    )

    assert tool_call_events[0]['mcp_server'] == 'artifact'
    assert tool_call_events[0]['mcp_tool'] == 'get_quest_state'
    assert tool_result_events[0]['tool_name'] == 'mcp__artifact__get_quest_state'
    assert tool_result_events[0]['mcp_server'] == 'artifact'
    assert tool_result_events[0]['mcp_tool'] == 'get_quest_state'


def test_claude_runner_emits_reasoning_for_thinking_blocks() -> None:
    runner = ClaudeRunner(
        home=Path('/tmp'),
        repo_root=Path('/tmp'),
        binary='claude',
        logger=SimpleNamespace(),
        prompt_builder=SimpleNamespace(),
        artifact_service=SimpleNamespace(),
    )
    events, texts = runner._translate_event(
        {
            'type': 'assistant',
            'message': {
                'id': 'msg-thinking',
                'content': [
                    {'type': 'thinking', 'thinking': 'Let me reason this through.'},
                    {'type': 'text', 'text': 'Final answer.'},
                ],
            },
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:00Z',
        translation_state={},
    )

    assert [event['type'] for event in events] == ['runner.reasoning', 'runner.agent_message']
    assert events[0]['kind'] == 'thinking'
    assert 'reason this through' in events[0]['text']
    assert texts == ['Final answer.']


def test_claude_runner_compacts_extreme_tool_results() -> None:
    runner = ClaudeRunner(
        home=Path('/tmp'),
        repo_root=Path('/tmp'),
        binary='claude',
        logger=SimpleNamespace(),
        prompt_builder=SimpleNamespace(),
        artifact_service=SimpleNamespace(),
    )
    huge_text = 'x' * (3 * 1024 * 1024)
    state: dict[str, object] = {
        'known_tools': {
            'tool-big': {
                'tool_name': 'mcp__artifact__get_quest_state',
                'mcp_server': 'artifact',
                'mcp_tool': 'get_quest_state',
            }
        }
    }
    events, _ = runner._translate_event(
        {
            'type': 'user',
            'message': {
                'content': [
                    {
                        'type': 'tool_result',
                        'tool_use_id': 'tool-big',
                        'content': huge_text,
                    }
                ],
            },
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:01Z',
        translation_state=state,
    )

    assert events[0]['type'] == 'runner.tool_result'
    assert events[0]['output_truncated'] is True
    assert events[0]['output_bytes'] > 2_000_000
    assert len(str(events[0]['output'])) < 20_000


def test_apply_claude_runtime_overrides_maps_yolo_and_model(monkeypatch) -> None:
    monkeypatch.setenv('DEEPSCIENTIST_CLAUDE_MODEL', 'claude-sonnet-4-5')
    monkeypatch.setenv('DEEPSCIENTIST_CLAUDE_YOLO', 'true')
    monkeypatch.setenv('DEEPSCIENTIST_CLAUDE_MAX_TURNS', '88')

    rendered = apply_claude_runtime_overrides({'permission_mode': 'default'})

    assert rendered['model'] == 'claude-sonnet-4-5'
    assert rendered['permission_mode'] == 'bypassPermissions'
    assert rendered['max_turns'] == '88'



def test_opencode_runner_preserves_mcp_identity_on_tool_results() -> None:
    runner = OpenCodeRunner(
        home=Path('/tmp'),
        repo_root=Path('/tmp'),
        binary='opencode',
        logger=SimpleNamespace(),
        prompt_builder=SimpleNamespace(),
        artifact_service=SimpleNamespace(),
    )
    state: dict[str, object] = {}

    tool_call_events, _ = runner._translate_event(
        {
            'type': 'tool_call',
            'id': 'tool-2',
            'tool': 'mcp__bash_exec__bash_exec',
            'input': {'command': 'pwd'},
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='experiment',
        created_at='2026-04-14T00:00:00Z',
        translation_state=state,
    )
    tool_result_events, _ = runner._translate_event(
        {
            'type': 'tool_result',
            'toolCallID': 'tool-2',
            'output': {'status': 'completed', 'cwd': '/tmp/quest'},
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='experiment',
        created_at='2026-04-14T00:00:01Z',
        translation_state=state,
    )

    assert tool_call_events[0]['mcp_server'] == 'bash_exec'
    assert tool_call_events[0]['mcp_tool'] == 'bash_exec'
    assert tool_result_events[0]['tool_name'] == 'mcp__bash_exec__bash_exec'
    assert tool_result_events[0]['mcp_server'] == 'bash_exec'
    assert tool_result_events[0]['mcp_tool'] == 'bash_exec'



def test_opencode_runner_translates_real_tool_use_payload_into_call_and_result() -> None:
    runner = OpenCodeRunner(
        home=Path('/tmp'),
        repo_root=Path('/tmp'),
        binary='opencode',
        logger=SimpleNamespace(),
        prompt_builder=SimpleNamespace(),
        artifact_service=SimpleNamespace(),
    )
    state: dict[str, object] = {}

    events, _ = runner._translate_event(
        {
            'type': 'tool_use',
            'sessionID': 'ses-1',
            'part': {
                'type': 'tool',
                'tool': 'artifact_get_quest_state',
                'callID': 'call-1',
                'messageID': 'msg-1',
                'state': {
                    'status': 'completed',
                    'input': {'detail': 'summary'},
                    'output': '{"quest_id":"q-001"}',
                },
            },
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:00Z',
        translation_state=state,
    )
    message_events, texts = runner._translate_event(
        {
            'type': 'text',
            'sessionID': 'ses-1',
            'part': {
                'type': 'text',
                'messageID': 'msg-2',
                'text': 'DONE: hello',
            },
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:01Z',
        translation_state=state,
    )

    assert [event['type'] for event in events] == ['runner.tool_call', 'runner.tool_result']
    assert events[0]['tool_name'] == 'mcp__artifact__get_quest_state'
    assert events[0]['mcp_server'] == 'artifact'
    assert events[0]['mcp_tool'] == 'get_quest_state'
    assert events[1]['tool_name'] == 'mcp__artifact__get_quest_state'
    assert events[1]['mcp_server'] == 'artifact'
    assert events[1]['mcp_tool'] == 'get_quest_state'
    assert events[1]['output'] == '{"quest_id":"q-001"}'
    assert message_events[0]['type'] == 'runner.agent_message'
    assert message_events[0]['text'] == 'DONE: hello'
    assert texts == ['DONE: hello']



def test_opencode_runner_does_not_emit_result_for_running_tool_use() -> None:
    runner = OpenCodeRunner(
        home=Path('/tmp'),
        repo_root=Path('/tmp'),
        binary='opencode',
        logger=SimpleNamespace(),
        prompt_builder=SimpleNamespace(),
        artifact_service=SimpleNamespace(),
    )
    state: dict[str, object] = {}

    events, _ = runner._translate_event(
        {
            'type': 'tool_use',
            'sessionID': 'ses-1',
            'part': {
                'type': 'tool',
                'tool': 'artifact_get_quest_state',
                'callID': 'call-running',
                'messageID': 'msg-1',
                'state': {
                    'status': 'running',
                    'input': {'detail': 'summary'},
                },
            },
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:00Z',
        translation_state=state,
    )

    assert [event['type'] for event in events] == ['runner.tool_call']


def test_opencode_runner_dedups_separate_tool_result_after_inline_terminal() -> None:
    runner = OpenCodeRunner(
        home=Path('/tmp'),
        repo_root=Path('/tmp'),
        binary='opencode',
        logger=SimpleNamespace(),
        prompt_builder=SimpleNamespace(),
        artifact_service=SimpleNamespace(),
    )
    state: dict[str, object] = {}

    inline_events, _ = runner._translate_event(
        {
            'type': 'tool_use',
            'sessionID': 'ses-1',
            'part': {
                'type': 'tool',
                'tool': 'artifact_get_quest_state',
                'callID': 'call-dup',
                'state': {'status': 'completed', 'output': 'inline-result'},
            },
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:00Z',
        translation_state=state,
    )
    separate_events, _ = runner._translate_event(
        {
            'type': 'tool_result',
            'toolCallID': 'call-dup',
            'output': 'separate-result',
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:01Z',
        translation_state=state,
    )

    assert [event['type'] for event in inline_events] == ['runner.tool_call', 'runner.tool_result']
    assert inline_events[1]['output'] == 'inline-result'
    assert separate_events == []


def test_opencode_runner_tool_result_empty_output_does_not_leak_record() -> None:
    runner = OpenCodeRunner(
        home=Path('/tmp'),
        repo_root=Path('/tmp'),
        binary='opencode',
        logger=SimpleNamespace(),
        prompt_builder=SimpleNamespace(),
        artifact_service=SimpleNamespace(),
    )
    state: dict[str, object] = {}

    runner._translate_event(
        {'type': 'tool_call', 'id': 'call-empty', 'tool': 'artifact_x', 'input': {'k': 'v'}},
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:00Z',
        translation_state=state,
    )
    result_events, _ = runner._translate_event(
        {'type': 'tool_result', 'toolCallID': 'call-empty', 'output': None, 'sensitive_input': 'secret'},
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:01Z',
        translation_state=state,
    )

    assert len(result_events) == 1
    assert result_events[0]['output'] == ''
    assert 'secret' not in result_events[0]['output']


def test_opencode_runner_inline_terminal_empty_output_does_not_leak_state() -> None:
    runner = OpenCodeRunner(
        home=Path('/tmp'),
        repo_root=Path('/tmp'),
        binary='opencode',
        logger=SimpleNamespace(),
        prompt_builder=SimpleNamespace(),
        artifact_service=SimpleNamespace(),
    )
    state: dict[str, object] = {}

    events, _ = runner._translate_event(
        {
            'type': 'tool_use',
            'part': {
                'type': 'tool',
                'tool': 'artifact_x',
                'callID': 'call-inline-empty',
                'state': {
                    'status': 'completed',
                    'input': {'very_long_secret_input': 'hunter2' * 100},
                },
            },
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:00Z',
        translation_state=state,
    )

    assert [event['type'] for event in events] == ['runner.tool_call', 'runner.tool_result']
    assert events[1]['output'] == ''


def test_opencode_runner_retries_with_filesystem_reference_prompt_on_e2big(temp_home, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    quest_root = temp_home / 'quest-e2big'
    quest_root.mkdir(parents=True, exist_ok=True)
    (quest_root / 'brief.md').write_text('# Brief\nUse the quest brief as the task requirement.\n', encoding='utf-8')
    write_yaml(
        quest_root / 'quest.yaml',
        {
            'quest_id': 'q-e2big',
            'title': 'E2BIG quest',
            'active_anchor': 'baseline',
        },
    )

    class _DummyWritable:
        def __init__(self) -> None:
            self.writes: list[str] = []

        def write(self, text: str) -> None:
            self.writes.append(text)

        def close(self) -> None:
            return None

    class _DummyReadable:
        def __iter__(self):
            return iter(())

    class _DummyProcess:
        def __init__(self) -> None:
            self.stdin = _DummyWritable()
            self.stdout = _DummyReadable()
            self.stderr = _DummyReadable()
            self._returncode: int | None = None

        def wait(self, timeout: float | None = None) -> int:
            self._returncode = 0
            return 0

        def poll(self) -> int | None:
            return self._returncode

        def terminate(self) -> None:
            self._returncode = 0

        def kill(self) -> None:
            self._returncode = 0

    popen_commands: list[list[str]] = []

    def fake_popen(command, **kwargs):  # noqa: ANN001
        popen_commands.append(list(command))
        if len(popen_commands) == 1:
            raise OSError(7, 'Argument list too long')
        return _DummyProcess()

    monkeypatch.setattr('deepscientist.runners.simple_cli.subprocess.Popen', fake_popen)
    monkeypatch.setattr('deepscientist.runners.simple_cli.export_git_graph', lambda *args, **kwargs: None)

    artifact_service = SimpleNamespace(
        quest_service=SimpleNamespace(schedule_projection_refresh=lambda *args, **kwargs: None),
        record=lambda *args, **kwargs: {'ok': True},
    )
    runner = OpenCodeRunner(
        home=temp_home,
        repo_root=temp_home,
        binary='opencode',
        logger=SimpleNamespace(log=lambda *args, **kwargs: None),
        prompt_builder=SimpleNamespace(build=lambda **kwargs: 'PROMPT\n' + ('x' * 500_000)),
        artifact_service=artifact_service,
    )

    result = runner.run(
        RunRequest(
            quest_id='q-e2big',
            quest_root=quest_root,
            worktree_root=None,
            run_id='run-e2big',
            skill_id='experiment',
            message='continue',
            model='inherit',
            approval_policy='never',
            sandbox_mode='danger-full-access',
        )
    )

    assert result.ok is True
    assert len(popen_commands) == 2
    assert popen_commands[0][-1] != popen_commands[1][-1]
    assert 'brief.md' in popen_commands[1][-1]
    assert 'prompt.md' in popen_commands[1][-1]

    command_payload = read_json(quest_root / '.ds' / 'runs' / 'run-e2big' / 'command.json', {})
    assert command_payload['prompt_strategy'] == 'argument_list_too_long'
    assert str(command_payload['prompt_reference_path']).endswith('prompt.argv-fallback.md')

    fallback_prompt = (quest_root / '.ds' / 'runs' / 'run-e2big' / 'prompt.argv-fallback.md').read_text(encoding='utf-8')
    assert 'brief.md' in fallback_prompt
    assert 'Do not ask the user to repeat the brief' in fallback_prompt


def test_opencode_runner_prepare_runtime_uses_allow_permission_mode_by_default(temp_home) -> None:  # type: ignore[no-untyped-def]
    quest_root = temp_home / 'quest'
    quest_root.mkdir(parents=True, exist_ok=True)
    runner = OpenCodeRunner(
        home=temp_home,
        repo_root=temp_home,
        binary='opencode',
        logger=SimpleNamespace(),
        prompt_builder=SimpleNamespace(),
        artifact_service=SimpleNamespace(),
    )

    env, meta = runner._prepare_runtime(
        workspace_root=quest_root,
        quest_root=quest_root,
        quest_id='q-001',
        run_id='run-001',
        runner_config={'config_dir': str(temp_home / 'missing-opencode-home'), 'mcp_timeout_ms': 45000},
    )

    config_path = Path(str(meta['opencode_config']))
    payload = json.loads(config_path.read_text(encoding='utf-8'))
    assert env['XDG_CONFIG_HOME'].endswith('.config')
    assert payload['permission'] == 'allow'
    assert payload['mcp']['artifact']['enabled'] is True
    assert payload['mcp']['artifact']['timeout'] == 45000
    assert payload['mcp']['artifact']['environment']['PYTHONIOENCODING'] == 'utf-8'
    assert payload['mcp']['artifact']['environment']['PYTHONUTF8'] == '1'


def test_runner_emits_warning_when_setup_output_falsely_claims_form_patch_missing(temp_home) -> None:  # type: ignore[no-untyped-def]
    quest_root = temp_home / 'quest-start-setup-warning'
    quest_root.mkdir(parents=True, exist_ok=True)
    write_yaml(
        quest_root / 'quest.yaml',
        {
            'quest_id': 'q-start-setup-warning',
            'title': 'Start setup warning quest',
            'startup_contract': {
                'launch_mode': 'custom',
                'custom_profile': 'freeform',
                'start_setup_session': {
                    'source': 'benchstore',
                    'locale': 'zh',
                },
            },
        },
    )
    runner = OpenCodeRunner(
        home=temp_home,
        repo_root=temp_home,
        binary='opencode',
        logger=SimpleNamespace(),
        prompt_builder=SimpleNamespace(),
        artifact_service=SimpleNamespace(),
    )
    quest_events = quest_root / '.ds' / 'events.jsonl'
    quest_events.parent.mkdir(parents=True, exist_ok=True)

    request = RunRequest(
        quest_id='q-start-setup-warning',
        quest_root=quest_root,
        worktree_root=None,
        run_id='run-warning-001',
        skill_id='scout',
        message='setup session',
        model='inherit',
        approval_policy='never',
        sandbox_mode='danger-full-access',
    )

    runner._emit_setup_tool_schema_warning_if_needed(
        request=request,
        output_text='由于当前表单回写工具没有暴露要求的 `form_patch` 参数，我先给出可直接应用的表单补丁。',
        quest_events=quest_events,
    )

    events = read_jsonl(quest_events)
    assert any(
        item.get('type') == 'runner.turn_postprocess_warning'
        and ((item.get('details') or {}) if isinstance(item.get('details'), dict) else {}).get('warning_code')
        == 'start_setup_false_missing_form_patch_claim'
        for item in events
    )


def test_list_distill_candidates_is_codex_auto_approved() -> None:
    from deepscientist.runners.codex import _BUILTIN_MCP_TOOL_APPROVALS
    assert "list_distill_candidates" in _BUILTIN_MCP_TOOL_APPROVALS["artifact"]
