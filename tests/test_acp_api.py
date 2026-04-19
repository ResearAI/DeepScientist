from __future__ import annotations

from pathlib import Path

from deepscientist.config import ConfigManager
from deepscientist.daemon import DaemonApp
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.quest import QuestService
from deepscientist.shared import append_jsonl
from deepscientist.skills import SkillInstaller


def test_acp_session_descriptor_exposes_quest_root_and_commands(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("acp quest")
    quest_id = quest["quest_id"]
    app = DaemonApp(temp_home)

    payload = app.handlers.quest_session(quest_id)

    assert payload["ok"] is True
    assert payload["acp_session"]["protocol"] == "agent-client-protocol"
    assert payload["acp_session"]["quest_id"] == quest_id
    assert payload["acp_session"]["cwd"] == payload["snapshot"]["quest_root"]
    assert {item["name"] for item in payload["acp_session"]["mcp_servers"]} == {"memory", "artifact", "bash_exec"}
    assert any(command["name"] == "/status" for command in payload["acp_session"]["slash_commands"])


def test_acp_event_polling_returns_session_updates(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("acp event quest")
    quest_id = quest["quest_id"]
    app = DaemonApp(temp_home)
    app.quest_service.append_message(
        quest_id,
        role="user",
        content="请给出当前实验总结。",
        source="local:default",
    )

    payload = app.handlers.quest_events(
        quest_id,
        path=f"/api/quests/{quest_id}/events?format=acp&session_id=session:test",
    )

    assert payload["quest_id"] == quest_id
    assert payload["format"] == "acp"
    assert payload["events"] == []
    assert payload["acp_updates"]
    update = payload["acp_updates"][-1]
    assert update["method"] == "session/update"
    assert update["params"]["sessionId"] == "session:test"
    assert update["params"]["update"]["kind"] == "message"
    assert update["params"]["update"]["message"]["role"] == "user"
    assert update["params"]["update"]["message"]["content"] == "请给出当前实验总结。"


def test_acp_event_message_preserves_run_metadata(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("acp metadata quest")
    quest_id = quest["quest_id"]
    app = DaemonApp(temp_home)
    app.quest_service.append_message(
        quest_id,
        role="assistant",
        content="Streaming run finished.",
        source="codex",
        run_id="run-123",
        skill_id="decision",
    )

    payload = app.handlers.quest_events(
        quest_id,
        path=f"/api/quests/{quest_id}/events?format=acp&session_id=session:test",
    )

    update = payload["acp_updates"][-1]["params"]["update"]["message"]
    assert update["run_id"] == "run-123"
    assert update["skill_id"] == "decision"


def test_acp_event_polling_supports_loading_older_pages(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("acp older quest")
    quest_id = quest["quest_id"]
    app = DaemonApp(temp_home)

    for index in range(1, 8):
        app.quest_service.append_message(
            quest_id,
            role="assistant" if index % 2 == 0 else "user",
            content=f"message-{index}",
            source="local:default",
        )

    latest_payload = app.handlers.quest_events(
        quest_id,
        path=f"/api/quests/{quest_id}/events?format=acp&session_id=session:test&limit=3&tail=1",
    )
    assert latest_payload["direction"] == "tail"
    assert latest_payload["has_more"] is True
    assert latest_payload["oldest_cursor"] == 5
    assert latest_payload["newest_cursor"] == 7

    older_payload = app.handlers.quest_events(
        quest_id,
        path=f"/api/quests/{quest_id}/events?format=acp&session_id=session:test&limit=2&before=5",
    )
    assert older_payload["direction"] == "before"
    assert older_payload["has_more"] is True
    assert older_payload["oldest_cursor"] == 3
    assert older_payload["newest_cursor"] == 4

    older_messages = [
        update["params"]["update"]["message"]["content"]
        for update in older_payload["acp_updates"]
        if update["params"]["update"]["kind"] == "message"
    ]
    assert older_messages == ["message-3", "message-4"]


def test_acp_event_polling_skips_corrupted_older_history_lines(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("acp corrupted older quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    app = DaemonApp(temp_home)

    for index in range(1, 8):
        app.quest_service.append_message(
            quest_id,
            role="assistant" if index % 2 == 0 else "user",
            content=f"message-{index}",
            source="local:default",
        )

    events_path = quest_root / ".ds" / "events.jsonl"
    lines = events_path.read_bytes().splitlines()
    corrupted_line = b"\x00\x00\xfe\xff\x00\x11\x00\x00"
    events_path.write_bytes(b"\n".join(lines[:4] + [corrupted_line] + lines[4:]) + b"\n")

    latest_payload = app.handlers.quest_events(
        quest_id,
        path=f"/api/quests/{quest_id}/events?format=acp&session_id=session:test&limit=3&tail=1",
    )
    assert latest_payload["direction"] == "tail"
    assert latest_payload["oldest_cursor"] == 6
    assert latest_payload["newest_cursor"] == 8
    assert latest_payload["has_more"] is True

    older_payload = app.handlers.quest_events(
        quest_id,
        path=f"/api/quests/{quest_id}/events?format=acp&session_id=session:test&limit=2&before=6",
    )
    older_messages = [
        update["params"]["update"]["message"]["content"]
        for update in older_payload["acp_updates"]
        if update["params"]["update"]["kind"] == "message"
    ]
    assert older_messages == ["message-3", "message-4"]
    assert older_payload["oldest_cursor"] == 3
    assert older_payload["newest_cursor"] == 4
    assert older_payload["has_more"] is True

    app.quest_service.append_message(
        quest_id,
        role="assistant",
        content="message-8",
        source="local:default",
    )
    after_payload = app.handlers.quest_events(
        quest_id,
        path=f"/api/quests/{quest_id}/events?format=acp&session_id=session:test&after=8",
    )
    after_messages = [
        update["params"]["update"]["message"]["content"]
        for update in after_payload["acp_updates"]
        if update["params"]["update"]["kind"] == "message"
    ]
    assert after_messages == ["message-8"]
    assert after_payload["cursor"] == 9


def test_acp_artifact_update_exposes_interaction_metadata(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("acp interaction quest")
    quest_id = quest["quest_id"]
    app = DaemonApp(temp_home)
    quest_root = Path(quest["quest_root"])

    app.artifact_service.interact(
        quest_root,
        kind="decision_request",
        message="Choose the next route.",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=False,
        options=[{"id": "go", "label": "Go", "description": "Proceed now."}],
    )

    payload = app.handlers.quest_events(
        quest_id,
        path=f"/api/quests/{quest_id}/events?format=acp&session_id=session:test",
    )

    update = payload["acp_updates"][-1]["params"]["update"]
    assert update["kind"] == "artifact"
    assert update["artifact"]["interaction_id"]
    assert update["artifact"]["expects_reply"] is True
    assert update["artifact"]["options"][0]["id"] == "go"


def test_acp_artifact_update_exposes_flow_metadata(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("acp flow quest")
    quest_id = quest["quest_id"]
    app = DaemonApp(temp_home)
    quest_root = Path(quest["quest_root"])
    baseline_root = quest_root / "baselines" / "local" / "acp-baseline"
    baseline_root.mkdir(parents=True, exist_ok=True)
    app.artifact_service.confirm_baseline(
        quest_root,
        baseline_path=str(baseline_root),
        baseline_id="acp-baseline",
        summary="ACP baseline confirmed",
        metrics_summary={"acc": 0.8},
        primary_metric={"name": "acc", "value": 0.8},
        metric_contract={
            "primary_metric_id": "acc",
            "metrics": [{"metric_id": "acc", "direction": "higher"}],
        },
    )

    result = app.artifact_service.submit_idea(
        quest_root,
        mode="create",
        title="Adapter route",
        problem="Baseline saturates.",
        hypothesis="A small adapter helps.",
        mechanism="Insert a residual adapter.",
        decision_reason="Promote the strongest next route.",
    )

    payload = app.handlers.quest_events(
        quest_id,
        path=f"/api/quests/{quest_id}/events?format=acp&session_id=session:test",
    )

    update = next(
        item["params"]["update"]
        for item in reversed(payload["acp_updates"])
        if item["params"]["update"].get("kind") == "artifact"
        and (item["params"]["update"].get("artifact") or {}).get("flow_type") == "idea_submission"
    )
    assert update["kind"] == "artifact"
    assert update["artifact"]["flow_type"] == "idea_submission"
    assert update["artifact"]["protocol_step"] == "create"
    assert update["artifact"]["branch"] == result["branch"]
    assert update["artifact"]["workspace_root"] == result["worktree_root"]
    assert update["artifact"]["artifact_path"]
    assert update["artifact"]["details"]["title"] == "Adapter route"


def test_api_command_status_and_graph_append_assistant_messages(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("acp command quest")
    quest_id = quest["quest_id"]
    app = DaemonApp(temp_home)

    status_payload = app.handlers.command(quest_id, {"command": "/status", "source": "web-react"})
    graph_payload = app.handlers.command(quest_id, {"command": "/graph", "source": "tui-ink"})

    assert status_payload["ok"] is True
    assert status_payload["type"] == "status"
    assert status_payload["message_record"]["role"] == "assistant"
    assert status_payload["message_record"]["source"] == "command"

    assert graph_payload["ok"] is True
    assert graph_payload["type"] == "graph"
    assert graph_payload["graph"]["branch"] == "main"

    events_payload = app.handlers.quest_events(
        quest_id,
        path=f"/api/quests/{quest_id}/events?format=acp&session_id=session:test",
    )
    assistant_messages = [
        update["params"]["update"]["message"]["content"]
        for update in events_payload["acp_updates"]
        if update["params"]["update"]["kind"] == "message"
        and update["params"]["update"]["message"]["role"] == "assistant"
    ]

    assert any(message.startswith(f"Quest {quest_id}") for message in assistant_messages)
    assert any(message.startswith(f"Git graph refreshed for {quest_id}.") for message in assistant_messages)


def test_acp_tool_updates_include_args_for_tool_results(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("acp tool quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    app = DaemonApp(temp_home)

    append_jsonl(
        quest_root / ".ds" / "events.jsonl",
        {
            "event_id": "evt-tool-call",
            "type": "runner.tool_call",
            "quest_id": quest_id,
            "run_id": "run-123",
            "source": "codex",
            "skill_id": "decision",
            "tool_call_id": "ws_1",
            "tool_name": "mcp__artifact__search_docs",
            "status": "calling",
            "args": "OpenAI homepage official",
            "mcp_server": "artifact",
            "mcp_tool": "search_docs",
            "created_at": "2026-03-09T00:00:00Z",
        },
    )
    append_jsonl(
        quest_root / ".ds" / "events.jsonl",
        {
            "event_id": "evt-tool-result",
            "type": "runner.tool_result",
            "quest_id": quest_id,
            "run_id": "run-123",
            "source": "codex",
            "skill_id": "decision",
            "tool_call_id": "ws_1",
            "tool_name": "mcp__artifact__search_docs",
            "status": "completed",
            "args": "OpenAI homepage official",
            "output": '{"results": 3}',
            "mcp_server": "artifact",
            "mcp_tool": "search_docs",
            "created_at": "2026-03-09T00:00:01Z",
        },
    )

    payload = app.handlers.quest_events(
        quest_id,
        path=f"/api/quests/{quest_id}/events?format=acp&session_id=session:test",
    )

    tool_updates = [
        update["params"]["update"]["data"]
        for update in payload["acp_updates"]
        if update["params"]["update"]["kind"] == "event"
        and update["params"]["update"].get("data", {}).get("label") in {"tool_call", "tool_result"}
    ]

    call_update = next(item for item in tool_updates if item["label"] == "tool_call")
    result_update = next(item for item in tool_updates if item["label"] == "tool_result")

    assert call_update["args"] == "OpenAI homepage official"
    assert call_update["mcp_server"] == "artifact"
    assert call_update["mcp_tool"] == "search_docs"
    assert result_update["args"] == "OpenAI homepage official"
    assert result_update["output"] == '{"results": 3}'
    assert result_update["mcp_server"] == "artifact"
    assert result_update["mcp_tool"] == "search_docs"
