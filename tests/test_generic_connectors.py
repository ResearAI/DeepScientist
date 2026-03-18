from __future__ import annotations

from pathlib import Path

import pytest

from deepscientist.config import ConfigManager
from deepscientist.daemon.app import DaemonApp
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.quest import QuestService
from deepscientist.shared import write_yaml
from deepscientist.skills import SkillInstaller


def test_default_connectors_include_feishu_whatsapp_and_lingzhu(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")

    assert "whatsapp" in connectors
    assert "feishu" in connectors
    assert "lingzhu" in connectors
    assert connectors["whatsapp"]["dm_policy"] == "pairing"
    assert connectors["whatsapp"]["transport"] == "local_session"
    assert connectors["feishu"]["transport"] == "long_connection"
    assert connectors["feishu"]["app_id"] is None
    assert connectors["lingzhu"]["transport"] == "openclaw_sse"
    assert connectors["lingzhu"]["gateway_port"] == 18789
    assert connectors["lingzhu"]["auto_receipt_ack"] is True
    assert connectors["lingzhu"]["visible_progress_heartbeat"] is True
    assert connectors["lingzhu"]["visible_progress_heartbeat_sec"] == 10


@pytest.mark.parametrize("connector_name", ["telegram", "discord", "slack", "feishu", "whatsapp"])
def test_generic_new_command_replies_with_bound_quest_and_restore_hint(
    temp_home: Path,
    connector_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors[connector_name]["enabled"] = True
    connectors[connector_name]["auto_bind_dm_to_active_quest"] = True
    write_yaml(manager.path_for("connectors"), connectors)
    app = DaemonApp(temp_home)
    monkeypatch.setattr(
        app,
        "schedule_turn",
        lambda quest_id, reason="user_message": {
            "scheduled": True,
            "started": True,
            "queued": False,
            "reason": reason,
        },
    )

    response = app.handle_connector_inbound(
        connector_name,
        {
            "chat_type": "direct",
            "sender_id": f"{connector_name}-user-1",
            "sender_name": "Researcher",
            "text": "/new prepare a baseline audit",
        },
    )

    assert response["accepted"] is True
    payload = response["reply"]["payload"]
    quest_id = str(payload["quest_id"])
    assert quest_id
    assert "prepare a baseline audit" in str(payload["text"] or "")
    assert "自动使用这个新 quest 保持连接" in str(payload["text"] or "")
    history = app.quest_service.history(quest_id)
    assert history
    assert history[-1]["content"] == "prepare a baseline audit"
    assert history[-1]["source"] == f"{connector_name}:direct:{connector_name}-user-1"


@pytest.mark.parametrize("connector_name", ["telegram", "discord", "slack", "feishu", "whatsapp"])
def test_generic_new_command_uses_previous_bound_quest_id_in_restore_hint(
    temp_home: Path,
    connector_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors[connector_name]["enabled"] = True
    connectors[connector_name]["auto_bind_dm_to_active_quest"] = True
    write_yaml(manager.path_for("connectors"), connectors)
    app = DaemonApp(temp_home)
    monkeypatch.setattr(
        app,
        "schedule_turn",
        lambda quest_id, reason="user_message": {
            "scheduled": True,
            "started": True,
            "queued": False,
            "reason": reason,
        },
    )
    previous = app.quest_service.create("previous quest")
    conversation_id = f"{connector_name}:direct:{connector_name}-user-1"
    app.update_quest_binding(previous["quest_id"], conversation_id, force=True)

    response = app.handle_connector_inbound(
        connector_name,
        {
            "chat_type": "direct",
            "sender_id": f"{connector_name}-user-1",
            "sender_name": "Researcher",
            "text": "/new prepare a baseline audit",
        },
    )

    payload = response["reply"]["payload"]
    quest_id = str(payload["quest_id"])
    assert quest_id != previous["quest_id"]
    assert f"/use {previous['quest_id']}" in str(payload["text"] or "")
    assert f"/use {quest_id}" not in str(payload["text"] or "")


def test_generic_connector_auto_binds_to_latest_existing_quest_and_rebinds_to_newest_quest(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["whatsapp"]["enabled"] = True
    connectors["whatsapp"]["auto_bind_dm_to_active_quest"] = True
    write_yaml(manager.path_for("connectors"), connectors)

    older_quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("whatsapp older quest")
    app = DaemonApp(temp_home)

    first = app.handle_connector_inbound(
        "whatsapp",
        {
            "chat_type": "direct",
            "sender_id": "+15550001111",
            "sender_name": "Researcher",
            "text": "Please summarize the latest result.",
        },
    )
    assert first["accepted"] is True
    assert older_quest["quest_id"] in first["reply"]["payload"]["text"]
    first_history = app.quest_service.history(older_quest["quest_id"])
    assert first_history
    assert first_history[-1]["content"] == "Please summarize the latest result."
    assert first_history[-1]["source"] == "whatsapp:direct:+15550001111"
    assert any(
        item["conversation_id"] == "whatsapp:direct:+15550001111" and item["quest_id"] == older_quest["quest_id"]
        for item in app.list_connector_bindings("whatsapp")
    )

    latest = app.create_quest(goal="whatsapp latest quest", source="web")
    latest_id = latest["quest_id"]

    bindings = app.list_connector_bindings("whatsapp")
    assert any(item["conversation_id"] == "whatsapp:direct:+15550001111" and item["quest_id"] == latest_id for item in bindings)

    second = app.handle_connector_inbound(
        "whatsapp",
        {
            "chat_type": "direct",
            "sender_id": "+15550001111",
            "sender_name": "Researcher",
            "text": "Please summarize the latest result.",
        },
    )
    assert second["accepted"] is True
    assert latest_id in second["reply"]["payload"]["text"]

    history = app.quest_service.history(latest_id)
    assert history
    assert history[-1]["content"] == "Please summarize the latest result."
    assert history[-1]["source"].startswith("whatsapp:")

    connector_statuses = {item["name"]: item for item in app.handlers.connectors()}
    assert "whatsapp" in connector_statuses
    assert "feishu" in connector_statuses
    assert connector_statuses["whatsapp"]["last_conversation_id"] == "whatsapp:direct:+15550001111"
    assert connector_statuses["whatsapp"]["transport"] == "local_session"
    assert connector_statuses["whatsapp"]["connection_state"] in {"configured", "ready"}
    assert connector_statuses["whatsapp"]["target_count"] >= 1
    assert any(
        item["conversation_id"] == "whatsapp:direct:+15550001111"
        for item in connector_statuses["whatsapp"]["discovered_targets"]
    )
    assert any(
        item["conversation_id"] == "whatsapp:direct:+15550001111"
        for item in connector_statuses["whatsapp"]["recent_conversations"]
    )
    assert any(item["event_type"] == "inbound" for item in connector_statuses["whatsapp"]["recent_events"])


def test_connector_availability_summary_prefers_enabled_bound_connector(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["main_chat_id"] = "user-1"
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    summary = app.handlers.connectors_availability()

    assert summary["has_enabled_external_connector"] is True
    assert summary["has_bound_external_connector"] is True
    assert summary["should_recommend_binding"] is False
    assert summary["preferred_connector_name"] == "qq"
    assert summary["preferred_conversation_id"] == "qq:direct:user-1"


def test_handlers_connectors_include_lingzhu_snapshot(temp_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = "abcd1234-abcd-abcd-abcd-abcdefghijkl"
    connectors["lingzhu"]["public_base_url"] = "http://203.0.113.10:18789"
    write_yaml(manager.path_for("connectors"), connectors)
    app = DaemonApp(temp_home)
    monkeypatch.setattr(
        app.config_manager,
        "_probe_lingzhu_health",
        lambda config, timeout=1.5: {"ok": True, "status": "ok", "payload": {"status": "ok"}},
    )

    connector_statuses = {item["name"]: item for item in app.handlers.connectors()}

    assert "lingzhu" in connector_statuses
    assert connector_statuses["lingzhu"]["transport"] == "openclaw_sse"
    assert connector_statuses["lingzhu"]["connection_state"] == "reachable"
    assert connector_statuses["lingzhu"]["auth_state"] == "ready"
    assert connector_statuses["lingzhu"]["details"]["public_endpoint_url"] == "http://203.0.113.10:18789/metis/agent/api/sse"


def test_generic_connector_persists_multiple_recent_conversations_for_latest_quest_rebind(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["whatsapp"]["enabled"] = True
    connectors["whatsapp"]["auto_bind_dm_to_active_quest"] = True
    write_yaml(manager.path_for("connectors"), connectors)

    older_quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("whatsapp many users")
    app = DaemonApp(temp_home)

    for sender_id, sender_name in (("+15550001111", "Alice"), ("+15550002222", "Bob")):
        response = app.handle_connector_inbound(
            "whatsapp",
            {
                "chat_type": "direct",
                "sender_id": sender_id,
                "sender_name": sender_name,
                "text": "Please summarize the latest result.",
            },
        )
        assert response["accepted"] is True
        assert older_quest["quest_id"] in response["reply"]["payload"]["text"]

    connector_statuses = {item["name"]: item for item in app.handlers.connectors()}
    recent_conversations = connector_statuses["whatsapp"]["recent_conversations"]
    assert any(item["conversation_id"] == "whatsapp:direct:+15550001111" for item in recent_conversations)
    assert any(item["conversation_id"] == "whatsapp:direct:+15550002222" for item in recent_conversations)

    latest = app.create_quest(goal="whatsapp newest quest with many users", source="web")
    latest_id = latest["quest_id"]
    bindings = app.list_connector_bindings("whatsapp")
    assert any(item["conversation_id"] == "whatsapp:direct:+15550001111" and item["quest_id"] == latest_id for item in bindings)
    assert any(item["conversation_id"] == "whatsapp:direct:+15550002222" and item["quest_id"] == latest_id for item in bindings)


def test_create_quest_with_preferred_connector_conversation_binds_only_selected_target(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["whatsapp"]["enabled"] = True
    connectors["whatsapp"]["auto_bind_dm_to_active_quest"] = True
    write_yaml(manager.path_for("connectors"), connectors)

    older_quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create(
        "whatsapp manual target selection"
    )
    older_id = older_quest["quest_id"]
    app = DaemonApp(temp_home)

    for sender_id, sender_name in (("+15550001111", "Alice"), ("+15550002222", "Bob")):
        response = app.handle_connector_inbound(
            "whatsapp",
            {
                "chat_type": "direct",
                "sender_id": sender_id,
                "sender_name": sender_name,
                "text": "Please keep this conversation available.",
            },
        )
        assert response["accepted"] is True
        assert older_id in response["reply"]["payload"]["text"]

    latest = app.create_quest(
        goal="whatsapp newest quest with manual connector selection",
        source="web",
        preferred_connector_conversation_id="whatsapp:direct:+15550002222",
    )
    latest_id = latest["quest_id"]
    bindings = app.list_connector_bindings("whatsapp")

    assert any(
        item["conversation_id"] == "whatsapp:direct:+15550002222" and item["quest_id"] == latest_id
        for item in bindings
    )
    assert not any(
        item["conversation_id"] == "whatsapp:direct:+15550001111" and item["quest_id"] == latest_id
        for item in bindings
    )
    latest_sources = app.quest_service.binding_sources(latest_id)
    assert "whatsapp:direct:+15550002222" in latest_sources
    assert "whatsapp:direct:+15550001111" not in latest_sources


def test_create_quest_with_requested_connector_bindings_binds_selected_targets_per_connector(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["whatsapp"]["enabled"] = True
    connectors["telegram"]["enabled"] = True
    connectors["whatsapp"]["auto_bind_dm_to_active_quest"] = True
    connectors["telegram"]["auto_bind_dm_to_active_quest"] = True
    write_yaml(manager.path_for("connectors"), connectors)

    older_quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create(
        "multi connector requested binding"
    )
    app = DaemonApp(temp_home)

    whatsapp_reply = app.handle_connector_inbound(
        "whatsapp",
        {
            "chat_type": "direct",
            "sender_id": "+15550003333",
            "sender_name": "Carol",
            "text": "Keep this conversation available.",
        },
    )
    assert whatsapp_reply["accepted"] is True
    assert older_quest["quest_id"] in whatsapp_reply["reply"]["payload"]["text"]

    telegram_reply = app.handle_connector_inbound(
        "telegram",
        {
            "chat_type": "direct",
            "sender_id": "tg-user-1",
            "sender_name": "Dave",
            "text": "Keep this conversation available.",
        },
    )
    assert telegram_reply["accepted"] is True
    assert older_quest["quest_id"] in telegram_reply["reply"]["payload"]["text"]

    latest = app.create_quest(
        goal="requested connector bindings quest",
        source="web",
        requested_connector_bindings=[
            {"connector": "whatsapp", "conversation_id": "whatsapp:direct:+15550003333"},
            {"connector": "telegram", "conversation_id": "telegram:direct:tg-user-1"},
        ],
        force_connector_rebind=True,
    )
    latest_sources = app.quest_service.binding_sources(latest["quest_id"])
    assert "whatsapp:direct:+15550003333" in latest_sources
    assert "telegram:direct:tg-user-1" in latest_sources


def test_generic_connector_supports_terminal_command_and_restore(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["whatsapp"]["enabled"] = True
    connectors["whatsapp"]["auto_bind_dm_to_active_quest"] = True
    write_yaml(manager.path_for("connectors"), connectors)

    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("whatsapp terminal quest")
    quest_id = quest["quest_id"]
    app = DaemonApp(temp_home)
    conversation_id = "whatsapp:direct:+15550002222"
    channel = app._channel_with_bindings("whatsapp")
    channel.bind_conversation(conversation_id, quest_id)
    app.sessions.bind(quest_id, conversation_id)
    app.quest_service.bind_source(quest_id, conversation_id)

    command_reply = app.handle_connector_inbound(
        "whatsapp",
        {
            "chat_type": "direct",
            "sender_id": "+15550002222",
            "sender_name": "Researcher",
            "text": "/terminal pwd",
        },
    )
    assert command_reply["accepted"] is True
    assert "terminal-main" in command_reply["reply"]["payload"]["text"]

    restore_reply = app.handle_connector_inbound(
        "whatsapp",
        {
            "chat_type": "direct",
            "sender_id": "+15550002222",
            "sender_name": "Researcher",
            "text": "/terminal -R",
        },
    )
    assert restore_reply["accepted"] is True
    assert "Terminal `terminal-main`" in restore_reply["reply"]["payload"]["text"]
    assert "latest commands:" in restore_reply["reply"]["payload"]["text"]


def test_generic_connector_supports_delete_command_with_confirmation(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    first = quest_service.create("connector delete quest one")
    second = quest_service.create("connector delete quest two")
    first_id = first["quest_id"]
    second_id = second["quest_id"]
    first_root = Path(first["quest_root"])
    second_root = Path(second["quest_root"])
    assert first_root.exists()
    assert second_root.exists()

    app = DaemonApp(temp_home)

    confirm_reply = app.handle_connector_inbound(
        "whatsapp",
        {
            "chat_type": "direct",
            "sender_id": "+15550003333",
            "sender_name": "Researcher",
            "text": f"/delete {first_id}",
        },
    )
    assert confirm_reply["accepted"] is True
    assert first_id in confirm_reply["reply"]["payload"]["text"]
    assert "--yes" in confirm_reply["reply"]["payload"]["text"]
    assert first_root.exists()

    delete_reply = app.handle_connector_inbound(
        "whatsapp",
        {
            "chat_type": "direct",
            "sender_id": "+15550003333",
            "sender_name": "Researcher",
            "text": f"/delete {first_id} --yes",
        },
    )
    assert delete_reply["accepted"] is True
    assert first_id in delete_reply["reply"]["payload"]["text"]
    assert not first_root.exists()
    assert second_root.exists()


def test_generic_connector_stop_command_stops_bound_quest_without_forwarding_to_agent(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("connector stop quest")
    quest_id = quest["quest_id"]
    app = DaemonApp(temp_home)
    conversation_id = "whatsapp:direct:+15550004444"
    channel = app._channel_with_bindings("whatsapp")
    channel.bind_conversation(conversation_id, quest_id)
    app.sessions.bind(quest_id, conversation_id)
    app.quest_service.bind_source(quest_id, conversation_id)
    app.quest_service.mark_turn_started(quest_id, run_id="run-stop-001")

    stop_reply = app.handle_connector_inbound(
        "whatsapp",
        {
            "chat_type": "direct",
            "sender_id": "+15550004444",
            "sender_name": "Researcher",
            "text": "/stop",
        },
    )

    assert stop_reply["accepted"] is True
    snapshot = app.quest_service.snapshot(quest_id)
    assert str(snapshot.get("status") or snapshot.get("runtime_status") or "") == "stopped"
    history = app.quest_service.history(quest_id)
    assert history
    assert history[-1]["source"] == "system-control"
    assert history[-1]["role"] == "assistant"
    assert history[-1]["content"] != "/stop"
    assert "/stop" not in [str(item.get("content") or "") for item in history if item.get("role") == "user"]
    assert "Quest: " in str(stop_reply["reply"]["payload"]["text"] or "")


def test_generic_connector_resume_command_resumes_bound_quest_without_forwarding_to_agent(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("connector resume quest")
    quest_id = quest["quest_id"]
    app = DaemonApp(temp_home)
    conversation_id = "whatsapp:direct:+15550005555"
    channel = app._channel_with_bindings("whatsapp")
    channel.bind_conversation(conversation_id, quest_id)
    app.sessions.bind(quest_id, conversation_id)
    app.quest_service.bind_source(quest_id, conversation_id)
    app.quest_service.mark_turn_finished(quest_id, status="stopped", stop_reason="test_stop")

    resume_reply = app.handle_connector_inbound(
        "whatsapp",
        {
            "chat_type": "direct",
            "sender_id": "+15550005555",
            "sender_name": "Researcher",
            "text": "/resume",
        },
    )

    assert resume_reply["accepted"] is True
    snapshot = app.quest_service.snapshot(quest_id)
    assert str(snapshot.get("status") or snapshot.get("runtime_status") or "") == "active"
    history = app.quest_service.history(quest_id)
    assert history
    assert history[-1]["source"] == "system-control"
    assert history[-1]["role"] == "assistant"
    assert history[-1]["content"] != "/resume"
    assert "/resume" not in [str(item.get("content") or "") for item in history if item.get("role") == "user"]
    assert "Quest: " in str(resume_reply["reply"]["payload"]["text"] or "")
