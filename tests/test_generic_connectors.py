from __future__ import annotations

from pathlib import Path

import pytest

from deepscientist.config import ConfigManager
from deepscientist.connector.lingzhu_support import lingzhu_passive_conversation_id
from deepscientist.daemon.app import DaemonApp
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.quest import QuestService
from deepscientist.shared import write_yaml
from deepscientist.skills import SkillInstaller


def _enable_system_connectors(home: Path, *names: str) -> None:
    manager = ConfigManager(home)
    config = manager.load_named("config")
    connectors = config.get("connectors") if isinstance(config.get("connectors"), dict) else {}
    system_enabled = connectors.get("system_enabled") if isinstance(connectors.get("system_enabled"), dict) else {}
    for name in names:
        system_enabled[str(name).strip().lower()] = True
    connectors["system_enabled"] = system_enabled
    config["connectors"] = connectors
    write_yaml(manager.path_for("config"), config)


def test_default_connectors_include_telegram_weixin_feishu_whatsapp_and_lingzhu(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")

    assert "telegram" in connectors
    assert "weixin" in connectors
    assert "whatsapp" in connectors
    assert "feishu" in connectors
    assert "lingzhu" in connectors
    assert connectors["telegram"]["transport"] == "polling"
    assert connectors["telegram"]["bot_token"] is None
    assert connectors["weixin"]["transport"] == "ilink_long_poll"
    assert connectors["weixin"]["base_url"] == "https://ilinkai.weixin.qq.com"
    assert connectors["weixin"]["cdn_base_url"] == "https://novac2c.cdn.weixin.qq.com/c2c"
    assert connectors["whatsapp"]["dm_policy"] == "pairing"
    assert connectors["whatsapp"]["transport"] == "local_session"
    assert connectors["feishu"]["transport"] == "long_connection"
    assert connectors["feishu"]["app_id"] is None
    assert connectors["lingzhu"]["transport"] == "openclaw_sse"
    assert connectors["lingzhu"]["gateway_port"] == 18789
    assert connectors["lingzhu"]["auto_receipt_ack"] is True
    assert connectors["lingzhu"]["visible_progress_heartbeat"] is True
    assert connectors["lingzhu"]["visible_progress_heartbeat_sec"] == 10


@pytest.mark.parametrize("connector_name", ["weixin", "telegram", "discord", "slack", "feishu", "whatsapp"])
def test_generic_new_command_replies_with_bound_quest_and_restore_hint(
    temp_home: Path,
    connector_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    _enable_system_connectors(temp_home, connector_name)
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


@pytest.mark.parametrize("connector_name", ["weixin", "telegram", "discord", "slack", "feishu", "whatsapp"])
def test_generic_new_command_uses_previous_bound_quest_id_in_restore_hint(
    temp_home: Path,
    connector_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    _enable_system_connectors(temp_home, connector_name)
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
    _enable_system_connectors(temp_home, "whatsapp")
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
    assert "feishu" not in connector_statuses
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


def test_system_disabled_connectors_are_hidden_from_statuses_and_availability(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["telegram"]["enabled"] = True
    connectors["telegram"]["bot_token"] = "telegram-token"
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = "abcd1234-abcd-abcd-abcd-abcdefghijkl"
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    connector_statuses = {item["name"]: item for item in app.handlers.connectors()}
    availability_names = {item["name"] for item in app.handlers.connectors_availability()["available_connectors"]}

    assert "qq" in connector_statuses
    assert "telegram" not in connector_statuses
    assert "lingzhu" in connector_statuses
    assert "telegram" not in availability_names
    assert "lingzhu" in availability_names


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


def test_lingzhu_snapshot_exposes_passive_target_after_auth_ak_save(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = "abcd1234-abcd-abcd-abcd-abcdefghijkl"
    connectors["lingzhu"]["agent_id"] = "DeepScientist"
    connectors["lingzhu"]["public_base_url"] = "http://example.com:20999"
    save_result = manager.save_named_payload("connectors", connectors)
    assert save_result["ok"] is True
    app = DaemonApp(temp_home)
    monkeypatch.setattr(
        app.config_manager,
        "_probe_lingzhu_health",
        lambda config, timeout=1.5: {"ok": True, "status": "ok", "payload": {"status": "ok"}},
    )

    connector_statuses = {item["name"]: item for item in app.handlers.connectors()}
    passive_conversation_id = lingzhu_passive_conversation_id(connectors["lingzhu"])
    lingzhu_status = connector_statuses["lingzhu"]

    assert lingzhu_status["target_count"] >= 1
    assert lingzhu_status["default_target"]["conversation_id"] == passive_conversation_id
    assert any(item["conversation_id"] == passive_conversation_id for item in lingzhu_status["discovered_targets"])


def test_lingzhu_passive_binding_routes_real_messages_without_creating_extra_targets(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = "abcd1234-abcd-abcd-abcd-abcdefghijkl"
    connectors["lingzhu"]["agent_id"] = "DeepScientist"
    connectors["lingzhu"]["public_base_url"] = "http://example.com:20999"
    save_result = manager.save_named_payload("connectors", connectors)
    assert save_result["ok"] is True
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("lingzhu passive binding quest")
    quest_id = quest["quest_id"]
    passive_conversation_id = lingzhu_passive_conversation_id(connectors["lingzhu"])

    bound = app.update_quest_binding(quest_id, passive_conversation_id, force=True)
    assert isinstance(bound, dict)
    assert bound["ok"] is True

    response = app.handle_connector_inbound(
        "lingzhu",
        {
            "chat_type": "direct",
            "sender_id": "glass-passive-1",
            "sender_name": "Rokid Glasses",
            "text": "状态",
        },
    )

    assert response["accepted"] is True
    assert response["reply"]["payload"]["quest_id"] == quest_id
    bindings = app.list_connector_bindings("lingzhu")
    assert bindings == [
        {
            "conversation_id": passive_conversation_id,
            "profile_id": None,
            "profile_label": None,
            "quest_id": quest_id,
            "updated_at": bindings[0]["updated_at"],
        }
    ]
    assert app.quest_service.binding_sources(quest_id) == ["local:default", passive_conversation_id]


def test_lingzhu_connector_inbound_is_allowed_by_default(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = "abcd1234-abcd-abcd-abcd-abcdefghijkl"
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    response = app.handle_connector_inbound(
        "lingzhu",
        {
            "chat_type": "direct",
            "sender_id": "glass-1",
            "sender_name": "Rokid Glasses",
            "text": "/new capture notes from the device",
        },
    )

    assert response["accepted"] is True
    assert response["normalized"]["conversation_id"] == "lingzhu:direct:glass-1"
    assert response["reply"]["payload"]["quest_id"]


def test_lingzhu_connector_inbound_is_allowed_even_if_system_gate_is_false(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    config = manager.load_named("config")
    runtime_connectors = config.get("connectors") if isinstance(config.get("connectors"), dict) else {}
    system_enabled = runtime_connectors.get("system_enabled") if isinstance(runtime_connectors.get("system_enabled"), dict) else {}
    system_enabled["lingzhu"] = False
    runtime_connectors["system_enabled"] = system_enabled
    config["connectors"] = runtime_connectors
    write_yaml(manager.path_for("config"), config)

    connectors = manager.load_named("connectors")
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = "abcd1234-abcd-abcd-abcd-abcdefghijkl"
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    response = app.handle_connector_inbound(
        "lingzhu",
        {
            "chat_type": "direct",
            "sender_id": "glass-1",
            "sender_name": "Rokid Glasses",
            "text": "/new continue from glasses",
        },
    )

    assert response["accepted"] is True
    assert response["normalized"]["conversation_id"] == "lingzhu:direct:glass-1"


def test_generic_connector_persists_multiple_recent_conversations_for_latest_quest_rebind(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    _enable_system_connectors(temp_home, "whatsapp")
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
    rebound = [
        item["conversation_id"]
        for item in bindings
        if item["quest_id"] == latest_id
    ]
    assert rebound == ["whatsapp:direct:+15550002222"]


def test_create_quest_with_preferred_connector_conversation_binds_only_selected_target(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    _enable_system_connectors(temp_home, "whatsapp", "telegram")
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


def test_create_quest_with_requested_connector_bindings_rejects_multiple_external_targets(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    _enable_system_connectors(temp_home, "whatsapp", "telegram")
    connectors = manager.load_named("connectors")
    connectors["whatsapp"]["enabled"] = True
    connectors["telegram"]["enabled"] = True
    write_yaml(manager.path_for("connectors"), connectors)
    app = DaemonApp(temp_home)

    with pytest.raises(ValueError, match="A quest may bind at most one external connector target."):
        app.create_quest(
            goal="requested connector bindings quest",
            source="web",
            requested_connector_bindings=[
                {"connector": "whatsapp", "conversation_id": "whatsapp:direct:+15550003333"},
                {"connector": "telegram", "conversation_id": "telegram:direct:tg-user-1"},
            ],
        )


def test_generic_connector_supports_terminal_command_and_restore(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    _enable_system_connectors(temp_home, "whatsapp")
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
    _enable_system_connectors(temp_home, "whatsapp")
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
    _enable_system_connectors(temp_home, "whatsapp")
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
    _enable_system_connectors(temp_home, "whatsapp")
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


def test_generic_connector_ack_reports_started_state(temp_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    _enable_system_connectors(temp_home, "whatsapp")
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("started ack quest")
    quest_id = quest["quest_id"]
    app = DaemonApp(temp_home)
    conversation_id = "whatsapp:direct:+15550006666"
    channel = app._channel_with_bindings("whatsapp")
    channel.bind_conversation(conversation_id, quest_id)
    app.sessions.bind(quest_id, conversation_id)
    app.quest_service.bind_source(quest_id, conversation_id)
    monkeypatch.setattr(
        app,
        "submit_user_message",
        lambda *args, **kwargs: {
            "scheduled": True,
            "started": True,
            "queued": False,
            "reason": "user_message",
            "auto_resumed": False,
        },
    )
    monkeypatch.setattr(
        app.config_manager,
        "runner_bootstrap_state",
        lambda runner_name: {"runner": runner_name, "ready": True, "last_result": {"summary": "Codex startup probe completed."}},
    )

    response = app.handle_connector_inbound(
        "whatsapp",
        {
            "chat_type": "direct",
            "sender_id": "+15550006666",
            "sender_name": "Researcher",
            "text": "Please continue.",
        },
    )

    assert response["accepted"] is True
    assert "已经成功收到消息" in str(response["reply"]["payload"]["text"] or "")


def test_generic_connector_ack_reports_stalled_startup(temp_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    _enable_system_connectors(temp_home, "whatsapp")
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("stalled ack quest")
    quest_id = quest["quest_id"]
    app = DaemonApp(temp_home)
    conversation_id = "whatsapp:direct:+15550007777"
    channel = app._channel_with_bindings("whatsapp")
    channel.bind_conversation(conversation_id, quest_id)
    app.sessions.bind(quest_id, conversation_id)
    app.quest_service.bind_source(quest_id, conversation_id)
    monkeypatch.setattr(
        app,
        "submit_user_message",
        lambda *args, **kwargs: {
            "scheduled": True,
            "started": False,
            "queued": True,
            "reason": "stalled_turn_recovery_pending",
            "auto_resumed": False,
        },
    )
    monkeypatch.setattr(
        app.config_manager,
        "runner_bootstrap_state",
        lambda runner_name: {"runner": runner_name, "ready": True, "last_result": {"summary": "Codex startup probe completed."}},
    )

    response = app.handle_connector_inbound(
        "whatsapp",
        {
            "chat_type": "direct",
            "sender_id": "+15550007777",
            "sender_name": "Researcher",
            "text": "Please continue.",
        },
    )

    assert response["accepted"] is True
    assert "正在启动 DeepScientist" in str(response["reply"]["payload"]["text"] or "")


def test_generic_connector_ack_reports_runner_offline(temp_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    _enable_system_connectors(temp_home, "whatsapp")
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("offline ack quest")
    quest_id = quest["quest_id"]
    app = DaemonApp(temp_home)
    conversation_id = "whatsapp:direct:+15550008888"
    channel = app._channel_with_bindings("whatsapp")
    channel.bind_conversation(conversation_id, quest_id)
    app.sessions.bind(quest_id, conversation_id)
    app.quest_service.bind_source(quest_id, conversation_id)
    monkeypatch.setattr(
        app,
        "submit_user_message",
        lambda *args, **kwargs: {
            "scheduled": True,
            "started": False,
            "queued": False,
            "reason": "user_message",
            "auto_resumed": False,
        },
    )
    monkeypatch.setattr(app, "_runner_name_for", lambda snapshot: "claude")
    monkeypatch.setattr(
        app.config_manager,
        "runner_bootstrap_state",
        lambda runner_name: {
            "runner": runner_name,
            "ready": False,
            "last_result": {"summary": "Claude Code startup probe failed."},
        },
    )

    response = app.handle_connector_inbound(
        "whatsapp",
        {
            "chat_type": "direct",
            "sender_id": "+15550008888",
            "sender_name": "Researcher",
            "text": "Please continue.",
        },
    )

    text_payload = str(response["reply"]["payload"]["text"] or "")
    assert response["accepted"] is True
    assert "DeepScientist 仍然不在线哟" in text_payload
    assert "Claude Code" in text_payload


def test_runner_turn_error_notifies_bound_connector_about_unexpected_stop(temp_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("runner stop notice quest")
    quest_id = quest["quest_id"]
    app = DaemonApp(temp_home)
    captured: list[dict] = []

    monkeypatch.setattr(
        app,
        "_relay_quest_message_to_bound_connectors",
        lambda quest_id, message, **kwargs: captured.append({"quest_id": quest_id, "message": message, **kwargs}),
    )

    app._record_turn_error(
        quest_id=quest_id,
        runner_name="codex",
        run_id="run-stop-connector-1",
        skill_id="experiment",
        model="gpt-5",
        summary="Codex process exited unexpectedly.",
        guidance=["Check the bound Codex runner connection."],
    )

    assert captured
    message = str(captured[-1]["message"] or "")
    assert "DeepScientist 意外停止运行" in message or "unexpectedly" in message.lower()
    assert "Codex" in message
