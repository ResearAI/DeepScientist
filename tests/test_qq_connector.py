from __future__ import annotations

from pathlib import Path

from deepscientist.channels.qq import QQRelayChannel
from deepscientist.config import ConfigManager
from deepscientist.connector_runtime import format_conversation_id
from deepscientist.daemon import DaemonApp
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.quest import QuestService
from deepscientist.shared import read_json, read_jsonl, write_json
from deepscientist.shared import write_yaml
from deepscientist.skills import SkillInstaller


def test_qq_auto_bind_is_enabled_by_default(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    connectors = manager.load_named("connectors")

    assert connectors["qq"]["auto_bind_dm_to_active_quest"] is True


def test_qq_status_normalizes_legacy_multi_profile_targets_and_labels(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["profiles"] = [
        {
            "profile_id": "qq-1903299925",
            "enabled": True,
            "app_id": "1903299925",
            "app_secret": "secret-a",
            "bot_name": "DeepScientist",
            "main_chat_id": "CF8D2D559AA956B48751539ADFB98865",
        },
        {
            "profile_id": "qq-profile-d7iuv7wx",
            "enabled": True,
            "app_id": "1903577099",
            "app_secret": "secret-b",
            "bot_name": "DeepScientist",
            "main_chat_id": "1725C581B930B7EA3585250DCB5DA509",
        },
    ]
    write_yaml(manager.path_for("connectors"), connectors)
    write_json(
        temp_home / "logs" / "connectors" / "qq" / "state.json",
        {
            "last_conversation_id": "qq:direct:qq-profile-d7iuv7wx::1725C581B930B7EA3585250DCB5DA509",
            "recent_conversations": [
                {
                    "conversation_id": "qq:direct:CF8D2D559AA956B48751539ADFB98865",
                    "label": "DeepScientist · 1903299925 · direct · CF8D2D559AA956B48751539ADFB98865",
                    "updated_at": "2026-03-18T04:02:07+00:00",
                    "source": "outbound_delivery",
                    "sender_id": "CF8D2D559AA956B48751539ADFB98865",
                    "sender_name": "CF8D2D559AA956B48751539ADFB98865",
                },
                {
                    "conversation_id": "qq:direct:qq-profile-d7iuv7wx::1725C581B930B7EA3585250DCB5DA509",
                    "label": "DeepScientist · 1903577099 · DeepScientist · 1903577099 · direct · 1725C581B930B7EA3585250DCB5DA509",
                    "updated_at": "2026-03-18T11:41:02+00:00",
                    "source": "outbound_delivery",
                    "profile_id": "qq-profile-d7iuv7wx",
                    "profile_label": "DeepScientist · 1903577099",
                    "sender_id": "1725C581B930B7EA3585250DCB5DA509",
                    "sender_name": "1725C581B930B7EA3585250DCB5DA509",
                },
            ],
            "known_targets": [
                {
                    "conversation_id": "qq:direct:CF8D2D559AA956B48751539ADFB98865",
                    "label": "DeepScientist · 1903299925 · direct · CF8D2D559AA956B48751539ADFB98865",
                    "updated_at": "2026-03-18T04:02:07+00:00",
                    "source": "outbound_delivery",
                    "first_seen_at": "2026-03-18T04:00:00+00:00",
                },
                {
                    "conversation_id": "qq:direct:qq-profile-d7iuv7wx::1725C581B930B7EA3585250DCB5DA509",
                    "label": "DeepScientist · 1903577099 · direct · 1725C581B930B7EA3585250DCB5DA509",
                    "updated_at": "2026-03-18T11:41:02+00:00",
                    "source": "outbound_delivery",
                    "profile_id": "qq-profile-d7iuv7wx",
                    "profile_label": "DeepScientist · 1903577099",
                    "first_seen_at": "2026-03-18T11:40:12+00:00",
                },
            ],
        },
    )

    channel = QQRelayChannel(temp_home, connectors["qq"])
    snapshot = channel.status()

    discovered_by_id = {item["conversation_id"]: item for item in snapshot["discovered_targets"]}
    encoded_first = format_conversation_id(
        "qq",
        "direct",
        "CF8D2D559AA956B48751539ADFB98865",
        profile_id="qq-1903299925",
    )
    encoded_second = format_conversation_id(
        "qq",
        "direct",
        "1725C581B930B7EA3585250DCB5DA509",
        profile_id="qq-profile-d7iuv7wx",
    )

    assert "qq:direct:CF8D2D559AA956B48751539ADFB98865" not in discovered_by_id
    assert encoded_first in discovered_by_id
    assert encoded_second in discovered_by_id
    assert discovered_by_id[encoded_first]["label"] == "direct · CF8D2D559AA956B48751539ADFB98865"
    assert discovered_by_id[encoded_first]["profile_label"] == "DeepScientist · 1903299925"
    assert discovered_by_id[encoded_second]["label"] == "direct · 1725C581B930B7EA3585250DCB5DA509"
    assert discovered_by_id[encoded_second]["profile_label"] == "DeepScientist · 1903577099"


def test_qq_group_requires_binding_and_supports_commands(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("qq quest")
    quest_id = quest["quest_id"]
    app = DaemonApp(temp_home)

    ignored = app.handle_qq_inbound(
        {
            "chat_type": "group",
            "group_id": "group-001",
            "sender_id": "user-1",
            "text": "hello team",
        }
    )
    assert ignored["accepted"] is False
    assert ignored["reason"] == "group_requires_mention_or_prefix"

    bound = app.handle_qq_inbound(
        {
            "chat_type": "group",
            "group_id": "group-001",
            "sender_id": "user-1",
            "text": f"/use {quest_id}",
        }
    )
    assert bound["accepted"] is True
    assert quest_id in bound["reply"]["payload"]["text"]
    bindings = app.list_qq_bindings()
    assert any(item["quest_id"] == quest_id for item in bindings)
    quest_bindings = read_json(Path(quest["quest_root"]) / ".ds" / "bindings.json", {"sources": []})
    assert f"qq:group:group-001" in (quest_bindings.get("sources") or [])

    status = app.handle_qq_inbound(
        {
            "chat_type": "group",
            "group_id": "group-001",
            "sender_id": "user-1",
            "text": "@DeepScientist /status",
        }
    )
    assert status["accepted"] is True
    assert quest_id in status["reply"]["payload"]["text"]

    graph = app.handle_qq_inbound(
        {
            "chat_type": "group",
            "group_id": "group-001",
            "sender_id": "user-1",
            "text": "/graph",
        }
    )
    attachments = graph["reply"]["payload"]["attachments"]
    assert attachments
    assert any(Path(item["path"]).exists() for item in attachments if item.get("path"))

    approval = app.handle_qq_inbound(
        {
            "chat_type": "group",
            "group_id": "group-001",
            "sender_id": "user-1",
            "text": "/approve decision-001 Looks good to proceed",
        }
    )
    assert "Approval recorded" in approval["reply"]["payload"]["text"]


def test_qq_direct_message_auto_binds_to_latest_existing_quest_and_rebinds_to_newest_quest(
    temp_home: Path,
    monkeypatch,
) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["app_id"] = "1903299925"
    connectors["qq"]["app_secret"] = "qq-secret"
    connectors["qq"]["auto_bind_dm_to_active_quest"] = True
    write_yaml(manager.path_for("connectors"), connectors)
    older_quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("older qq quest")

    deliveries: list[dict] = []

    def fake_deliver(_self, payload, _config):  # noqa: ANN001
        deliveries.append(dict(payload))
        return {"ok": True, "transport": "qq-http"}

    monkeypatch.setattr("deepscientist.bridges.connectors.QQConnectorBridge.deliver", fake_deliver)
    app = DaemonApp(temp_home)

    first = app.handle_qq_inbound(
        {
            "chat_type": "direct",
            "sender_id": "user-2",
            "sender_name": "Tester",
            "text": "请先更新当前研究计划。",
        }
    )
    assert first["accepted"] is True
    assert older_quest["quest_id"] in first["reply"]["payload"]["text"]
    first_history = app.quest_service.history(older_quest["quest_id"])
    assert first_history
    assert first_history[-1]["content"] == "请先更新当前研究计划。"
    assert first_history[-1]["source"] == "qq:direct:user-2"
    assert any(
        item["conversation_id"] == "qq:direct:user-2" and item["quest_id"] == older_quest["quest_id"]
        for item in app.list_qq_bindings()
    )
    first_outbox = read_jsonl(temp_home / "logs" / "connectors" / "qq" / "outbox.jsonl")
    assert first_outbox
    assert first_outbox[-1]["delivery"]["ok"] is True

    latest = app.create_quest(goal="qq latest quest", source="web")
    latest_id = latest["quest_id"]

    bindings = app.list_qq_bindings()
    assert any(item["conversation_id"] == "qq:direct:user-2" and item["quest_id"] == latest_id for item in bindings)

    sessions = app.sessions.snapshot()
    assert sessions
    assert sessions[0]["quest_id"] == latest_id
    assert any(source.startswith("qq:direct:") for source in sessions[0]["bound_sources"])

    second = app.handle_qq_inbound(
        {
            "chat_type": "direct",
            "sender_id": "user-2",
            "sender_name": "Tester",
            "text": "请先更新当前研究计划。",
        }
    )
    assert second["accepted"] is True
    assert latest_id in second["reply"]["payload"]["text"]

    history = app.quest_service.history(latest_id)
    assert history
    assert history[-1]["content"] == "请先更新当前研究计划。"
    assert history[-1]["source"].startswith("qq:direct:")

    refreshed_connectors = manager.load_named("connectors")
    assert refreshed_connectors["qq"]["main_chat_id"] == "user-2"

    connector_statuses = {item["name"]: item for item in app.handlers.connectors()}
    assert connector_statuses["qq"]["main_chat_id"] == "user-2"
    assert connector_statuses["qq"]["last_conversation_id"] == "qq:direct:user-2"
    assert connector_statuses["qq"]["transport"] == "gateway_direct"
    assert connector_statuses["qq"]["connection_state"] == "ready"
    assert connector_statuses["qq"]["default_target"]["conversation_id"] == "qq:direct:user-2"
    assert any(item["conversation_id"] == "qq:direct:user-2" for item in connector_statuses["qq"]["discovered_targets"])
    assert any(item["conversation_id"] == "qq:direct:user-2" for item in connector_statuses["qq"]["recent_conversations"])
    assert any(item["event_type"] == "outbound" for item in connector_statuses["qq"]["recent_events"])
    assert any(item["text"].startswith("已自动检测并保存当前 QQ openid") for item in deliveries)
    assert any(older_quest["quest_id"] in item["text"] for item in deliveries)
    assert any(latest_id in item["text"] for item in deliveries)
    assert any("我即将为您完成以下任务：qq latest quest" in item["text"] for item in deliveries)
    assert any(f"/use {older_quest['quest_id']}" in item["text"] for item in deliveries)
    assert not any(f"/use {latest_id}" in item["text"] for item in deliveries)
    assert any("自动使用这个新 quest 保持连接" in item["text"] for item in deliveries)


def test_qq_auto_bind_to_latest_quest_still_happens_when_another_connector_is_primary(
    temp_home: Path,
    monkeypatch,
) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["_routing"]["primary_connector"] = "telegram"
    connectors["qq"]["enabled"] = True
    connectors["qq"]["app_id"] = "1903299925"
    connectors["qq"]["app_secret"] = "qq-secret"
    connectors["qq"]["auto_bind_dm_to_active_quest"] = True
    connectors["telegram"]["enabled"] = True
    connectors["telegram"]["auto_bind_dm_to_active_quest"] = True
    write_yaml(manager.path_for("connectors"), connectors)
    write_json(
        temp_home / "logs" / "connectors" / "telegram" / "state.json",
        {"last_conversation_id": "telegram:direct:alice", "updated_at": "2026-03-12T00:00:00+00:00"},
    )

    deliveries: list[dict] = []

    def fake_deliver(_self, payload, _config):  # noqa: ANN001
        deliveries.append(dict(payload))
        return {"ok": True, "transport": "qq-http"}

    monkeypatch.setattr("deepscientist.bridges.connectors.QQConnectorBridge.deliver", fake_deliver)
    app = DaemonApp(temp_home)

    first = app.handle_qq_inbound(
        {
            "chat_type": "direct",
            "sender_id": "user-9",
            "sender_name": "Tester",
            "text": "先看看现在的任务。",
        }
    )

    assert first["accepted"] is True
    assert app.list_qq_bindings() == []

    latest = app.create_quest(goal="multi connector latest quest", source="web")

    assert any(
        item["conversation_id"] == "qq:direct:user-9" and item["quest_id"] == latest["quest_id"]
        for item in app.list_qq_bindings()
    )
    assert any(
        item["conversation_id"] == "telegram:direct:alice" and item["quest_id"] == latest["quest_id"]
        for item in app.list_connector_bindings("telegram")
    )
    assert any("我即将为您完成以下任务：multi connector latest quest" in item["text"] for item in deliveries)


def test_qq_direct_message_does_not_overwrite_existing_main_chat_id(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["app_id"] = "1903299925"
    connectors["qq"]["app_secret"] = "qq-secret"
    connectors["qq"]["main_chat_id"] = "existing-openid"
    write_yaml(manager.path_for("connectors"), connectors)

    def fake_deliver(_self, _payload, _config):  # noqa: ANN001
        return {"ok": True, "transport": "qq-http"}

    monkeypatch.setattr("deepscientist.bridges.connectors.QQConnectorBridge.deliver", fake_deliver)
    app = DaemonApp(temp_home)

    response = app.handle_qq_inbound(
        {
            "chat_type": "direct",
            "sender_id": "user-3",
            "sender_name": "Tester",
            "text": "你好",
        }
    )

    assert response["accepted"] is True
    assert "existing-openid" == manager.load_named("connectors")["qq"]["main_chat_id"]
    assert "自动检测并保存当前 QQ openid" not in response["reply"]["payload"]["text"]


def test_qq_multiple_profiles_keep_separate_openids_and_conversation_ids(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"] = {
        **connectors["qq"],
        "enabled": True,
        "profiles": [
            {
                "profile_id": "qq-a",
                "app_id": "1903299925",
                "app_secret": "qq-secret-a",
                "bot_name": "DeepScientist A",
            },
            {
                "profile_id": "qq-b",
                "app_id": "2903299925",
                "app_secret": "qq-secret-b",
                "bot_name": "DeepScientist B",
            },
        ],
    }
    write_yaml(manager.path_for("connectors"), connectors)
    QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("multi profile qq quest")

    def fake_deliver(_self, _payload, _config):  # noqa: ANN001
        return {"ok": True, "transport": "qq-http"}

    monkeypatch.setattr("deepscientist.bridges.connectors.QQConnectorBridge.deliver", fake_deliver)
    app = DaemonApp(temp_home)

    first = app.handle_qq_inbound(
        {
            "chat_type": "direct",
            "profile_id": "qq-a",
            "sender_id": "user-a",
            "sender_name": "Tester A",
            "text": "你好 A",
        }
    )
    second = app.handle_qq_inbound(
        {
            "chat_type": "direct",
            "profile_id": "qq-b",
            "sender_id": "user-b",
            "sender_name": "Tester B",
            "text": "你好 B",
        }
    )

    assert first["accepted"] is True
    assert second["accepted"] is True
    assert first["normalized"]["conversation_id"] == "qq:direct:qq-a::user-a"
    assert second["normalized"]["conversation_id"] == "qq:direct:qq-b::user-b"

    refreshed_connectors = manager.load_named("connectors")
    profiles = {item["profile_id"]: item for item in refreshed_connectors["qq"]["profiles"]}
    assert profiles["qq-a"]["main_chat_id"] == "user-a"
    assert profiles["qq-b"]["main_chat_id"] == "user-b"

    statuses = {item["name"]: item for item in app.handlers.connectors()}
    qq_status = statuses["qq"]
    assert any(item["profile_id"] == "qq-a" and item["main_chat_id"] == "user-a" for item in qq_status["profiles"])
    assert any(item["profile_id"] == "qq-b" and item["main_chat_id"] == "user-b" for item in qq_status["profiles"])


def test_qq_new_command_replies_with_actual_goal(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["app_id"] = "1903299925"
    connectors["qq"]["app_secret"] = "qq-secret"
    write_yaml(manager.path_for("connectors"), connectors)

    deliveries: list[dict] = []

    def fake_deliver(_self, payload, _config):  # noqa: ANN001
        deliveries.append(dict(payload))
        return {"ok": True, "transport": "qq-http"}

    monkeypatch.setattr("deepscientist.bridges.connectors.QQConnectorBridge.deliver", fake_deliver)
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

    response = app.handle_qq_inbound(
        {
            "chat_type": "direct",
            "sender_id": "user-6",
            "sender_name": "Tester",
            "text": "/new 复现一个图神经网络基线",
        }
    )

    assert response["accepted"] is True
    assert "我即将为您完成以下任务：复现一个图神经网络基线" in response["reply"]["payload"]["text"]
    created_quest_id = str(response["reply"]["payload"]["quest_id"])
    assert created_quest_id
    assert "自动使用这个新 quest 保持连接" in response["reply"]["payload"]["text"]
    assert any("我即将为您完成以下任务：复现一个图神经网络基线" in item["text"] for item in deliveries)
    history = app.quest_service.history(created_quest_id)
    assert history
    assert history[-1]["content"] == "复现一个图神经网络基线"
    assert history[-1]["source"] == "qq:direct:user-6"
