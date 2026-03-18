from __future__ import annotations

from pathlib import Path

from deepscientist.config.models import default_connectors
from deepscientist.connector_profiles import (
    connector_profile_label,
    list_connector_profiles,
    merge_connector_profile_config,
    normalize_connector_config,
)
from deepscientist.connector_runtime import conversation_identity_key, format_conversation_id, parse_conversation_id
from deepscientist.channels.relay import GenericRelayChannel
from deepscientist.daemon.app import DaemonApp
from deepscientist.home import ensure_home_layout
from deepscientist.shared import write_json, write_yaml


def test_normalize_connector_config_migrates_legacy_telegram_fields_into_single_profile_and_strips_old_entry_fields() -> None:
    connectors = default_connectors()
    telegram = connectors["telegram"]
    telegram["enabled"] = True
    telegram["bot_name"] = "Research Bot"
    telegram["bot_token"] = "telegram-secret"
    telegram["transport"] = "legacy_webhook"
    telegram["relay_url"] = "https://relay.example.com/telegram"
    telegram["public_callback_url"] = "https://public.example.com/api/connectors/telegram/webhook"

    normalized = normalize_connector_config("telegram", telegram)
    profiles = list_connector_profiles("telegram", normalized)

    assert len(profiles) == 1
    assert profiles[0]["bot_name"] == "Research Bot"
    assert profiles[0]["bot_token"] == "telegram-secret"
    assert profiles[0]["transport"] == "polling"
    assert "relay_url" not in profiles[0]
    assert "public_callback_url" not in profiles[0]
    assert profiles[0]["profile_id"].startswith("telegram-")
    assert normalized["bot_name"] == "Research Bot"
    assert normalized["transport"] == "polling"
    assert "relay_url" not in normalized
    assert "public_callback_url" not in normalized
    assert normalized["profiles"][0]["profile_id"] == profiles[0]["profile_id"]


def test_merge_connector_profile_config_keeps_shared_policies_and_profile_credentials() -> None:
    connectors = default_connectors()
    slack = connectors["slack"]
    slack["enabled"] = True
    slack["require_mention_in_groups"] = False
    slack["profiles"] = [
        {
            "profile_id": "slack-alpha",
            "enabled": True,
            "bot_name": "Alpha Slack",
            "bot_token": "xoxb-alpha",
            "app_token": "xapp-alpha",
        }
    ]

    profile = list_connector_profiles("slack", slack)[0]
    merged = merge_connector_profile_config("slack", slack, profile)

    assert merged["profile_id"] == "slack-alpha"
    assert merged["bot_name"] == "Alpha Slack"
    assert merged["bot_token"] == "xoxb-alpha"
    assert merged["app_token"] == "xapp-alpha"
    assert merged["require_mention_in_groups"] is False
    assert merged["enabled"] is True
    assert connector_profile_label("slack", profile) == "Alpha Slack"


def test_profile_aware_conversation_identity_round_trips_for_non_qq_connector() -> None:
    conversation_id = format_conversation_id("telegram", "direct", "12345", profile_id="telegram-main")
    parsed = parse_conversation_id(conversation_id)

    assert conversation_id == "telegram:direct:telegram-main::12345"
    assert parsed is not None
    assert parsed["connector"] == "telegram"
    assert parsed["chat_type"] == "direct"
    assert parsed["chat_id"] == "12345"
    assert parsed["chat_id_raw"] == "telegram-main::12345"
    assert parsed["profile_id"] == "telegram-main"
    assert conversation_identity_key(conversation_id) == "telegram:telegram-main:direct:12345"


def test_generic_relay_status_exposes_profile_scoped_targets_and_bindings(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    connectors = default_connectors()
    connectors["telegram"]["enabled"] = True
    connectors["telegram"]["profiles"] = [
        {
            "profile_id": "telegram-alpha",
            "enabled": True,
            "bot_name": "Alpha Bot",
            "bot_token": "alpha-token",
        },
        {
            "profile_id": "telegram-beta",
            "enabled": True,
            "bot_name": "Beta Bot",
            "bot_token": "beta-token",
        },
    ]
    channel = GenericRelayChannel(temp_home, "telegram", connectors["telegram"])

    alpha_conversation_id = format_conversation_id("telegram", "direct", "10001", profile_id="telegram-alpha")
    beta_conversation_id = format_conversation_id("telegram", "direct", "20002", profile_id="telegram-beta")
    channel.ingest(
        {
            "conversation_id": alpha_conversation_id,
            "chat_type": "direct",
            "direct_id": "10001",
            "sender_id": "10001",
            "sender_name": "Alice",
            "text": "/help",
            "profile_id": "telegram-alpha",
            "profile_label": "Alpha Bot",
        }
    )
    channel.ingest(
        {
            "conversation_id": beta_conversation_id,
            "chat_type": "direct",
            "direct_id": "20002",
            "sender_id": "20002",
            "sender_name": "Bob",
            "text": "/help",
            "profile_id": "telegram-beta",
            "profile_label": "Beta Bot",
        }
    )
    channel.bind_conversation(alpha_conversation_id, "quest-alpha")
    write_json(
        temp_home / "logs" / "connectors" / "telegram" / "profiles" / "telegram-alpha" / "runtime.json",
        {
            "profile_id": "telegram-alpha",
            "profile_label": "Alpha Bot",
            "transport": "polling",
            "connection_state": "connected",
            "auth_state": "ready",
            "last_conversation_id": alpha_conversation_id,
        },
    )
    write_json(
        temp_home / "logs" / "connectors" / "telegram" / "profiles" / "telegram-beta" / "runtime.json",
        {
            "profile_id": "telegram-beta",
            "profile_label": "Beta Bot",
            "transport": "polling",
            "connection_state": "connected",
            "auth_state": "ready",
            "last_conversation_id": beta_conversation_id,
        },
    )

    snapshot = channel.status()

    assert snapshot["connection_state"] == "connected"
    assert snapshot["auth_state"] == "ready"
    assert len(snapshot["profiles"]) == 2
    by_profile = {item["profile_id"]: item for item in snapshot["profiles"]}
    assert by_profile["telegram-alpha"]["binding_count"] == 1
    assert by_profile["telegram-alpha"]["target_count"] >= 1
    assert by_profile["telegram-beta"]["binding_count"] == 0
    assert any(item["conversation_id"] == alpha_conversation_id for item in by_profile["telegram-alpha"]["discovered_targets"])
    assert any(item["conversation_id"] == beta_conversation_id for item in by_profile["telegram-beta"]["discovered_targets"])


def test_generic_relay_send_uses_profile_specific_credentials(
    temp_home: Path,
    monkeypatch,
) -> None:
    ensure_home_layout(temp_home)
    connectors = default_connectors()
    connectors["telegram"]["enabled"] = True
    connectors["telegram"]["profiles"] = [
        {
            "profile_id": "telegram-alpha",
            "enabled": True,
            "bot_name": "Alpha Bot",
            "bot_token": "alpha-token",
        },
        {
            "profile_id": "telegram-beta",
            "enabled": True,
            "bot_name": "Beta Bot",
            "bot_token": "beta-token",
        },
    ]
    channel = GenericRelayChannel(temp_home, "telegram", connectors["telegram"])
    captured_configs: list[dict] = []

    class _FakeBridge:
        def deliver(self, payload, config):  # noqa: ANN001
            captured_configs.append(dict(config))
            return {"ok": True, "queued": False, "transport": "fake"}

    monkeypatch.setattr("deepscientist.channels.relay.get_connector_bridge", lambda _name: _FakeBridge())

    result = channel.send(
        {
            "conversation_id": format_conversation_id("telegram", "direct", "10001", profile_id="telegram-beta"),
            "message": "hello",
        }
    )

    assert result["ok"] is True
    assert captured_configs
    assert captured_configs[-1]["profile_id"] == "telegram-beta"
    assert captured_configs[-1]["bot_token"] == "beta-token"


def test_daemon_latest_connector_conversation_ids_reads_profile_runtime_files(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    connectors = default_connectors()
    connectors["slack"]["enabled"] = True
    connectors["slack"]["profiles"] = [
        {
            "profile_id": "slack-alpha",
            "enabled": True,
            "bot_name": "Alpha Slack",
            "bot_token": "xoxb-alpha",
            "app_token": "xapp-alpha",
        },
        {
            "profile_id": "slack-beta",
            "enabled": True,
            "bot_name": "Beta Slack",
            "bot_token": "xoxb-beta",
            "app_token": "xapp-beta",
        },
    ]
    write_yaml(temp_home / "config" / "connectors.yaml", connectors)

    alpha_conversation_id = format_conversation_id("slack", "group", "C111", profile_id="slack-alpha")
    beta_conversation_id = format_conversation_id("slack", "group", "C222", profile_id="slack-beta")
    write_json(
        temp_home / "logs" / "connectors" / "slack" / "profiles" / "slack-alpha" / "runtime.json",
        {"last_conversation_id": alpha_conversation_id},
    )
    write_json(
        temp_home / "logs" / "connectors" / "slack" / "profiles" / "slack-beta" / "runtime.json",
        {"last_conversation_id": beta_conversation_id},
    )

    app = DaemonApp(temp_home)
    conversation_ids = app._latest_connector_conversation_ids("slack")

    assert alpha_conversation_id in conversation_ids
    assert beta_conversation_id in conversation_ids
