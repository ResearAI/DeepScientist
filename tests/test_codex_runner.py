from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

from deepscientist.artifact import ArtifactService
from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.prompts import PromptBuilder
from deepscientist.quest import QuestService
from deepscientist.runners import CodexRunner, RunRequest
from deepscientist.runtime_logs import JsonlLogger
from deepscientist.shared import read_jsonl, resolve_runner_binary
from deepscientist.skills import SkillInstaller


def test_codex_runner_creates_history_and_run_outputs(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("runner quest")
    quest_root = Path(quest["quest_root"])

    fake_bin_root = temp_home / "bin"
    fake_bin_root.mkdir(parents=True, exist_ok=True)
    fake_codex = fake_bin_root / "codex"
    fake_codex.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "sys.stdin.read()",
                "print(json.dumps({'item': {'text': 'fake codex response'}}))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    import os

    monkeypatch.setenv("PATH", f"{fake_bin_root}:{os.environ.get('PATH', '')}")

    runner = CodexRunner(
        home=temp_home,
        repo_root=repo_root(),
        binary="codex",
        logger=JsonlLogger(temp_home / "logs", level="debug"),
        prompt_builder=PromptBuilder(repo_root(), temp_home),
        artifact_service=ArtifactService(temp_home),
    )
    result = runner.run(
        RunRequest(
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            worktree_root=None,
            run_id="run-test-001",
            skill_id="decision",
            message="Respond briefly.",
            model="gpt-5.4",
            approval_policy="never",
            sandbox_mode="workspace-write",
        )
    )
    assert result.ok is True
    assert "fake codex response" in result.output_text
    assert (result.history_root / "assistant.md").exists()
    assert (result.run_root / "prompt.md").exists()
    assert (result.run_root / "result.json").exists()
    config_text = (quest_root / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert "[mcp_servers.memory]" in config_text
    assert "[mcp_servers.artifact]" in config_text
    assert "[mcp_servers.bash_exec]" in config_text
    assert "tool_timeout_sec" in config_text
    command_payload = json.loads((result.run_root / "command.json").read_text(encoding="utf-8"))
    assert "--search" in command_payload["command"]
    assert "-c" in command_payload["command"]
    assert 'approval_policy="never"' in command_payload["command"]
    assert 'model_reasoning_effort="xhigh"' in command_payload["command"]
    assert "--ask-for-approval" not in command_payload["command"]
    event_log = (quest_root / ".ds" / "events.jsonl").read_text(encoding="utf-8")
    assert "runner.turn_start" in event_log
    assert "runner.delta" in event_log
    assert "runner.turn_finish" in event_log


def test_resolve_runner_binary_supports_env_override_for_codex(monkeypatch, temp_home: Path) -> None:
    temp_home.mkdir(parents=True, exist_ok=True)
    fake_codex = temp_home / "codex"
    fake_codex.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_codex.chmod(0o755)

    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("DEEPSCIENTIST_CODEX_BINARY", str(fake_codex))

    assert resolve_runner_binary("codex", runner_name="codex") == str(fake_codex)


def test_resolve_runner_binary_prefers_package_local_codex_before_path(monkeypatch, temp_home: Path) -> None:
    repo_root = temp_home / "repo"
    package_bin = repo_root / "node_modules" / ".bin"
    package_bin.mkdir(parents=True, exist_ok=True)
    package_name = "codex.cmd" if sys.platform.startswith("win") else "codex"
    package_codex = package_bin / package_name
    package_codex.write_text("@echo off\r\nexit /b 0\r\n" if sys.platform.startswith("win") else "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    package_codex.chmod(0o755)

    path_bin = temp_home / "path-bin"
    path_bin.mkdir(parents=True, exist_ok=True)
    path_codex = path_bin / package_name
    path_codex.write_text("@echo off\r\nexit /b 0\r\n" if sys.platform.startswith("win") else "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    path_codex.chmod(0o755)

    monkeypatch.setenv("DEEPSCIENTIST_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("PATH", str(path_bin))
    monkeypatch.delenv("DEEPSCIENTIST_CODEX_BINARY", raising=False)
    monkeypatch.delenv("DS_CODEX_BINARY", raising=False)

    assert resolve_runner_binary("codex", runner_name="codex") == str(package_codex)


def test_codex_runner_build_command_uses_resolved_codex_binary(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("runner binary quest")
    quest_root = Path(quest["quest_root"])

    fake_codex = temp_home / "codex"
    fake_codex.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_codex.chmod(0o755)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("DEEPSCIENTIST_CODEX_BINARY", str(fake_codex))

    runner = CodexRunner(
        home=temp_home,
        repo_root=repo_root(),
        binary="codex",
        logger=JsonlLogger(temp_home / "logs", level="debug"),
        prompt_builder=PromptBuilder(repo_root(), temp_home),
        artifact_service=ArtifactService(temp_home),
    )
    command = runner._build_command(
        RunRequest(
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            worktree_root=None,
            run_id="run-binary-001",
            skill_id="decision",
            message="Respond briefly.",
            model="gpt-5.4",
            approval_policy="never",
            sandbox_mode="workspace-write",
        ),
        "Reply with exactly HELLO.",
    )

    assert command[0] == str(fake_codex)


def test_codex_runner_maps_real_json_item_types_to_tool_events(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("runner event quest")
    quest_root = Path(quest["quest_root"])
    note_path = quest_root / "note.txt"
    note_path.write_text("alpha\nbeta\n", encoding="utf-8")

    fake_bin_root = temp_home / "bin"
    fake_bin_root.mkdir(parents=True, exist_ok=True)
    fake_codex = fake_bin_root / "codex"
    fake_codex.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "sys.stdin.read()",
                f"print(json.dumps({{'type': 'item.started', 'item': {{'id': 'cmd_1', 'type': 'command_execution', 'command': '/bin/bash -lc \\\"sed -n \\'2p\\' {note_path}\\\"', 'aggregated_output': '', 'exit_code': None, 'status': 'in_progress'}}}}))",
                f"print(json.dumps({{'type': 'item.completed', 'item': {{'id': 'cmd_1', 'type': 'command_execution', 'command': '/bin/bash -lc \\\"sed -n \\'2p\\' {note_path}\\\"', 'aggregated_output': 'beta\\\\n', 'exit_code': 0, 'status': 'completed'}}}}))",
                "print(json.dumps({'type': 'item.started', 'item': {'id': 'ws_1', 'type': 'web_search', 'query': '', 'action': {'type': 'other'}}}))",
                "print(json.dumps({'type': 'item.completed', 'item': {'id': 'ws_1', 'type': 'web_search', 'query': 'OpenAI homepage official', 'action': {'type': 'search', 'query': 'OpenAI homepage official', 'queries': ['OpenAI homepage official']}, 'results': [{'title': 'OpenAI', 'link': 'https://openai.com', 'snippet': 'Official homepage'}], 'summary': 'Found the official homepage.', 'status': 'completed'}}))",
                "print(json.dumps({'type': 'item.started', 'item': {'id': 'mcp_1', 'type': 'mcp_tool_call', 'server': 'memory', 'tool': 'list_recent', 'arguments': {'scope': 'quest', 'limit': 5, 'comment': {'summary': 'Check recent memory', 'next': 'Use the result to decide the next step'}}, 'status': 'in_progress'}}))",
                "print(json.dumps({'type': 'item.completed', 'item': {'id': 'mcp_1', 'type': 'mcp_tool_call', 'server': 'memory', 'tool': 'list_recent', 'arguments': {'scope': 'quest', 'limit': 5, 'comment': {'summary': 'Check recent memory', 'next': 'Use the result to decide the next step'}}, 'result': {'content': [{'type': 'text', 'text': '{\"ok\": true, \"count\": 0, \"items\": []}'}], 'structured_content': {'ok': True, 'count': 0, 'items': []}}, 'status': 'completed'}}))",
                f"print(json.dumps({{'type': 'item.completed', 'item': {{'id': 'fc_1', 'type': 'file_change', 'changes': [{{'path': '{note_path}', 'kind': 'update'}}], 'status': 'completed'}}}}))",
                "print(json.dumps({'item': {'text': 'tool flow finished'}}))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    import os

    monkeypatch.setenv("PATH", f"{fake_bin_root}:{os.environ.get('PATH', '')}")

    runner = CodexRunner(
        home=temp_home,
        repo_root=repo_root(),
        binary="codex",
        logger=JsonlLogger(temp_home / "logs", level="debug"),
        prompt_builder=PromptBuilder(repo_root(), temp_home),
        artifact_service=ArtifactService(temp_home),
    )
    result = runner.run(
        RunRequest(
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            worktree_root=None,
            run_id="run-tool-events-001",
            skill_id="decision",
            message="Inspect the note and search the web.",
            model="gpt-5.4",
            approval_policy="never",
            sandbox_mode="workspace-write",
        )
    )

    assert result.ok is True
    events = read_jsonl(quest_root / ".ds" / "events.jsonl")
    tool_calls = [event for event in events if event.get("type") == "runner.tool_call"]
    tool_results = [event for event in events if event.get("type") == "runner.tool_result"]

    assert any(event.get("tool_name") == "shell_command" and "sed -n" in str(event.get("args") or "") for event in tool_calls)
    assert any(event.get("tool_name") == "shell_command" and "beta" in str(event.get("output") or "") for event in tool_results)
    assert any(event.get("tool_name") == "web_search" for event in tool_calls)
    assert any(event.get("tool_name") == "web_search" and "OpenAI homepage official" in str(event.get("args") or "") for event in tool_results)
    assert any(
        event.get("tool_name") == "web_search"
        and isinstance(event.get("metadata"), dict)
        and isinstance(event["metadata"].get("search"), dict)
        and isinstance(event["metadata"]["search"].get("results"), list)
        and event["metadata"]["search"]["results"][0].get("title") == "OpenAI"
        for event in tool_results
    )
    assert any(event.get("tool_name") == "memory.list_recent" for event in tool_calls)
    assert any(event.get("tool_name") == "memory.list_recent" and "scope" in str(event.get("args") or "") for event in tool_results)
    assert any(event.get("tool_name") == "file_change" and str(note_path) in str(event.get("output") or "") for event in tool_results)
    assert any(event.get("mcp_server") == "memory" and event.get("mcp_tool") == "list_recent" for event in tool_calls)
    assert any(
        event.get("mcp_server") == "memory"
        and event.get("mcp_tool") == "list_recent"
        and isinstance(event.get("metadata"), dict)
        for event in tool_results
    )
    assert any(
        event.get("tool_name") == "memory.list_recent"
        and isinstance(event.get("metadata"), dict)
        and isinstance(event["metadata"].get("comment"), dict)
        and event["metadata"]["comment"].get("summary") == "Check recent memory"
        for event in tool_results
    )

    workflow = quest_service.workflow(quest["quest_id"])
    assert any(entry.get("kind") == "tool_call" and entry.get("tool_name") == "shell_command" for entry in workflow["entries"])
    assert any(entry.get("kind") == "tool_call" and entry.get("tool_name") == "memory.list_recent" for entry in workflow["entries"])
    assert any(entry.get("kind") == "tool_result" and entry.get("tool_name") == "file_change" for entry in workflow["entries"])


def test_codex_runner_uses_last_agent_message_as_final_output(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("runner final output quest")
    quest_root = Path(quest["quest_root"])

    fake_bin_root = temp_home / "bin"
    fake_bin_root.mkdir(parents=True, exist_ok=True)
    fake_codex = fake_bin_root / "codex"
    fake_codex.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "sys.stdin.read()",
                "print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'step one'}}))",
                "print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'final answer only'}}))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    import os

    monkeypatch.setenv("PATH", f"{fake_bin_root}:{os.environ.get('PATH', '')}")

    runner = CodexRunner(
        home=temp_home,
        repo_root=repo_root(),
        binary="codex",
        logger=JsonlLogger(temp_home / "logs", level="debug"),
        prompt_builder=PromptBuilder(repo_root(), temp_home),
        artifact_service=ArtifactService(temp_home),
    )
    result = runner.run(
        RunRequest(
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            worktree_root=None,
            run_id="run-final-output-001",
            skill_id="decision",
            message="Respond briefly.",
            model="gpt-5.4",
            approval_policy="never",
            sandbox_mode="workspace-write",
        )
    )

    assert result.output_text == "final answer only"
    assert (result.history_root / "assistant.md").read_text(encoding="utf-8").strip() == "final answer only"


def test_codex_runner_executes_inside_active_worktree_and_sets_env(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("runner worktree quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    baseline_root = quest_root / "baselines" / "local" / "runner-baseline"
    baseline_root.mkdir(parents=True, exist_ok=True)
    artifact.confirm_baseline(
        quest_root,
        baseline_path=str(baseline_root),
        baseline_id="runner-baseline",
        summary="Runner baseline confirmed",
        metrics_summary={"acc": 0.8},
        primary_metric={"name": "acc", "value": 0.8},
        metric_contract={
            "primary_metric_id": "acc",
            "metrics": [{"metric_id": "acc", "direction": "higher"}],
        },
    )
    idea_result = artifact.submit_idea(
        quest_root,
        mode="create",
        title="Adapter route",
        problem="Baseline saturates.",
        hypothesis="A small adapter helps.",
        mechanism="Insert a lightweight adapter.",
        decision_reason="Promote the best current idea.",
    )
    worktree_root = Path(idea_result["worktree_root"])

    fake_bin_root = temp_home / "bin"
    fake_bin_root.mkdir(parents=True, exist_ok=True)
    fake_output = temp_home / "runner-worktree.json"
    fake_codex = fake_bin_root / "codex"
    fake_codex.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, os, pathlib, sys",
                "sys.stdin.read()",
                f"path = pathlib.Path({str(fake_output)!r})",
                "path.write_text(json.dumps({'cwd': os.getcwd(), 'worktree': os.environ.get('DS_WORKTREE_ROOT'), 'quest_root': os.environ.get('DS_QUEST_ROOT')}), encoding='utf-8')",
                "print(json.dumps({'item': {'text': 'worktree run ok'}}))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    import os

    monkeypatch.setenv("PATH", f"{fake_bin_root}:{os.environ.get('PATH', '')}")

    runner = CodexRunner(
        home=temp_home,
        repo_root=repo_root(),
        binary="codex",
        logger=JsonlLogger(temp_home / "logs", level="debug"),
        prompt_builder=PromptBuilder(repo_root(), temp_home),
        artifact_service=artifact,
    )
    result = runner.run(
        RunRequest(
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            worktree_root=worktree_root,
            run_id="run-worktree-001",
            skill_id="experiment",
            message="Run inside the active worktree.",
            model="gpt-5.4",
            approval_policy="never",
            sandbox_mode="workspace-write",
        )
    )

    payload = json.loads(fake_output.read_text(encoding="utf-8"))
    command_payload = json.loads((result.run_root / "command.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert payload["cwd"] == str(worktree_root)
    assert payload["worktree"] == str(worktree_root)
    assert payload["quest_root"] == str(quest_root)
    assert command_payload["workspace_root"] == str(worktree_root)
    assert command_payload["cwd"] == str(worktree_root)
    assert (worktree_root / ".codex" / "config.toml").exists()


def test_codex_runner_interrupt_stops_spawned_process_group(temp_home: Path, monkeypatch) -> None:
    if os.name == "nt":
        return

    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("runner interrupt quest")
    quest_root = Path(quest["quest_root"])

    fake_bin_root = temp_home / "bin"
    fake_bin_root.mkdir(parents=True, exist_ok=True)
    child_state_path = temp_home / "codex-child-state.txt"
    fake_codex = fake_bin_root / "codex"
    fake_codex.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, subprocess, sys, textwrap, time",
                "sys.stdin.read()",
                f"child_state_path = {str(child_state_path)!r}",
                "child_code = textwrap.dedent('''",
                "import pathlib, signal, sys, time",
                "path = pathlib.Path(sys.argv[1])",
                "path.write_text(\"alive\", encoding=\"utf-8\")",
                "def _stop(*_args):",
                "    path.write_text(\"stopped\", encoding=\"utf-8\")",
                "    raise SystemExit(0)",
                "signal.signal(signal.SIGTERM, _stop)",
                "signal.signal(signal.SIGINT, _stop)",
                "while True:",
                "    time.sleep(0.2)",
                "''')",
                "subprocess.Popen([sys.executable, '-c', child_code, child_state_path])",
                "print(json.dumps({'item': {'type': 'agent_message', 'text': 'interrupt test ready'}}), flush=True)",
                "while True:",
                "    time.sleep(0.5)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin_root}:{os.environ.get('PATH', '')}")

    runner = CodexRunner(
        home=temp_home,
        repo_root=repo_root(),
        binary="codex",
        logger=JsonlLogger(temp_home / "logs", level="debug"),
        prompt_builder=PromptBuilder(repo_root(), temp_home),
        artifact_service=ArtifactService(temp_home),
    )

    holder: dict[str, object] = {}

    def _run() -> None:
        holder["result"] = runner.run(
            RunRequest(
                quest_id=quest["quest_id"],
                quest_root=quest_root,
                worktree_root=None,
                run_id="run-interrupt-001",
                skill_id="decision",
                message="Start and wait.",
                model="gpt-5.4",
                approval_policy="never",
                sandbox_mode="workspace-write",
            )
        )

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    deadline = time.time() + 5
    while time.time() < deadline:
        if child_state_path.exists() and child_state_path.read_text(encoding="utf-8").strip() == "alive":
            break
        time.sleep(0.05)
    else:
        raise AssertionError("fake codex child process did not start")

    assert runner.interrupt(quest["quest_id"]) is True

    thread.join(timeout=5)
    assert not thread.is_alive()

    deadline = time.time() + 3
    while time.time() < deadline:
        if child_state_path.read_text(encoding="utf-8").strip() == "stopped":
            break
        time.sleep(0.05)
    else:
        raise AssertionError("interrupt did not stop the spawned child process")


def test_codex_runner_injects_retry_recovery_packet_into_prompt(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("runner retry packet quest")
    quest_root = Path(quest["quest_root"])

    fake_bin_root = temp_home / "bin"
    fake_bin_root.mkdir(parents=True, exist_ok=True)
    stdin_dump = temp_home / "retry-stdin.txt"
    fake_codex = fake_bin_root / "codex"
    fake_codex.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, pathlib, sys",
                "payload = sys.stdin.read()",
                f"path = pathlib.Path({str(stdin_dump)!r})",
                "path.write_text(payload, encoding='utf-8')",
                "print(json.dumps({'item': {'text': 'retry prompt ok'}}))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin_root}:{os.environ.get('PATH', '')}")

    runner = CodexRunner(
        home=temp_home,
        repo_root=repo_root(),
        binary="codex",
        logger=JsonlLogger(temp_home / "logs", level="debug"),
        prompt_builder=PromptBuilder(repo_root(), temp_home),
        artifact_service=ArtifactService(temp_home),
    )
    result = runner.run(
        RunRequest(
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            worktree_root=None,
            run_id="run-retry-prompt-001",
            skill_id="decision",
            message="Continue after a transport failure.",
            model="gpt-5.4",
            approval_policy="never",
            sandbox_mode="workspace-write",
            turn_id="turn-retry-001",
            attempt_index=2,
            max_attempts=5,
            retry_context={
                "attempt_index": 1,
                "max_attempts": 5,
                "previous_run_id": "run-failed-001",
                "previous_exit_code": 1,
                "failure_kind": "exit_code",
                "failure_summary": "Runner `codex` exited with code 1 on attempt 1/5.",
                "previous_output_text": "Partial answer before the crash.",
                "stderr_tail": "transport disconnected",
                "recent_messages": ["Observed a partial result."],
                "tool_progress": [
                    {
                        "tool_name": "web_search",
                        "status": "completed",
                        "args": "query=adapter paper",
                        "output": "3 results collected",
                    }
                ],
                "workspace_summary": {
                    "branch": "main",
                    "git_status": ["M status.md"],
                    "bash_sessions": [],
                },
                "recent_artifacts": ["run -> run-failed-001 -> Partial answer before the crash."],
            },
        )
    )

    prompt_text = (result.run_root / "prompt.md").read_text(encoding="utf-8")
    stdin_text = stdin_dump.read_text(encoding="utf-8")

    assert result.ok is True
    assert "## Retry Recovery Packet" in prompt_text
    assert "run-failed-001" in prompt_text
    assert "Partial answer before the crash." in prompt_text
    assert "web_search" in prompt_text
    assert prompt_text == stdin_text
