from __future__ import annotations

import json
from pathlib import Path
from urllib.error import URLError

import pytest

from deepscientist.bridges.connectors import FeishuConnectorBridge
from deepscientist.config import ConfigManager
from deepscientist.config.models import default_connectors
from deepscientist.connector.connector_profiles import (
    connector_profile_label,
    list_connector_profiles,
    merge_connector_profile_config,
    normalize_connector_config,
)
from deepscientist.connector_runtime import conversation_identity_key, format_conversation_id, parse_conversation_id
from deepscientist.channels.qq import QQRelayChannel
from deepscientist.channels.relay import GenericRelayChannel
from deepscientist.daemon.app import DaemonApp
from deepscientist.home import ensure_home_layout
from deepscientist.connector.qq_profiles import normalize_qq_connector_config
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


def test_normalize_qq_connector_config_prefers_direct_secret_and_clears_env_placeholder() -> None:
    connectors = default_connectors()
    qq = connectors["qq"]
    qq["enabled"] = True
    qq["app_id"] = "1903299925"
    qq["app_secret"] = "qq-secret"
    qq["app_secret_env"] = "QQ_APP_SECRET"

    normalized = normalize_qq_connector_config(qq)
    profiles = normalized["profiles"]

    assert len(profiles) == 1
    assert normalized["app_secret"] == "qq-secret"
    assert normalized["app_secret_env"] is None
    assert profiles[0]["app_secret"] == "qq-secret"
    assert profiles[0]["app_secret_env"] is None


def test_normalize_connector_config_prefers_direct_secret_and_clears_env_placeholder() -> None:
    connectors = default_connectors()
    slack = connectors["slack"]
    slack["enabled"] = True
    slack["bot_name"] = "Alpha Slack"
    slack["bot_token"] = "xoxb-alpha"
    slack["bot_token_env"] = "SLACK_BOT_TOKEN"
    slack["app_token"] = "xapp-alpha"
    slack["app_token_env"] = "SLACK_APP_TOKEN"

    normalized = normalize_connector_config("slack", slack)
    profile = normalized["profiles"][0]

    assert normalized["bot_token"] == "xoxb-alpha"
    assert normalized["bot_token_env"] is None
    assert normalized["app_token"] == "xapp-alpha"
    assert normalized["app_token_env"] is None
    assert profile["bot_token"] == "xoxb-alpha"
    assert profile["bot_token_env"] is None
    assert profile["app_token"] == "xapp-alpha"
    assert profile["app_token_env"] is None


def test_normalize_connector_config_preserves_env_only_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connectors = default_connectors()
    telegram = connectors["telegram"]
    telegram["enabled"] = True
    telegram["bot_name"] = "Research Bot"
    telegram["bot_token"] = None
    telegram["bot_token_env"] = "TELEGRAM_BOT_TOKEN"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-secret")

    normalized = normalize_connector_config("telegram", telegram)
    profile = normalized["profiles"][0]

    assert normalized["bot_token"] is None
    assert normalized["bot_token_env"] == "TELEGRAM_BOT_TOKEN"
    assert profile["bot_token"] is None
    assert profile["bot_token_env"] == "TELEGRAM_BOT_TOKEN"


def test_normalize_connector_config_auto_enables_ready_env_only_profile_when_env_secret_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connectors = default_connectors()
    slack = connectors["slack"]
    slack["enabled"] = False
    slack["bot_name"] = "Alpha Slack"
    slack["bot_token_env"] = "SLACK_BOT_TOKEN"
    slack["app_token_env"] = "SLACK_APP_TOKEN"
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-alpha")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-alpha")

    normalized = normalize_connector_config("slack", slack)

    assert normalized["enabled"] is True
    assert len(normalized["profiles"]) == 1
    assert normalized["profiles"][0]["enabled"] is True


def test_normalize_connector_config_drops_default_placeholder_profiles_without_resolved_runtime_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
    connectors = default_connectors()
    connectors["telegram"]["profiles"] = [
        {
            "profile_id": "telegram-deepscientist",
            "enabled": False,
            "transport": "polling",
            "bot_name": "DeepScientist",
            "bot_token": None,
            "bot_token_env": "TELEGRAM_BOT_TOKEN",
        }
    ]
    connectors["slack"]["profiles"] = [
        {
            "profile_id": "slack-deepscientist",
            "enabled": False,
            "transport": "socket_mode",
            "bot_name": "DeepScientist",
            "bot_token": None,
            "bot_token_env": "SLACK_BOT_TOKEN",
            "bot_user_id": None,
            "app_token": None,
            "app_token_env": "SLACK_APP_TOKEN",
        }
    ]
    connectors["whatsapp"]["profiles"] = [
        {
            "profile_id": "whatsapp-deepscientist",
            "enabled": False,
            "transport": "local_session",
            "bot_name": "DeepScientist",
            "auth_method": "qr_browser",
            "session_dir": "~/.deepscientist/connectors/whatsapp",
        }
    ]

    telegram = normalize_connector_config("telegram", connectors["telegram"])
    slack = normalize_connector_config("slack", connectors["slack"])
    whatsapp = normalize_connector_config("whatsapp", connectors["whatsapp"])

    assert telegram["enabled"] is False
    assert telegram["profiles"] == []
    assert slack["enabled"] is False
    assert slack["profiles"] == []
    assert whatsapp["enabled"] is False
    assert whatsapp["profiles"] == []


def test_default_connector_normalization_does_not_create_spurious_profiles() -> None:
    connectors = default_connectors()

    assert normalize_qq_connector_config(connectors["qq"])["profiles"] == []
    assert normalize_connector_config("telegram", connectors["telegram"])["profiles"] == []


def test_normalize_qq_connector_config_auto_enables_ready_profile_even_when_enabled_is_false() -> None:
    connectors = default_connectors()
    qq = connectors["qq"]
    qq["enabled"] = False
    qq["app_id"] = "1903299925"
    qq["app_secret_env"] = "QQ_APP_SECRET"

    normalized = normalize_qq_connector_config(qq)

    assert normalized["enabled"] is True
    assert len(normalized["profiles"]) == 1
    assert normalized["profiles"][0]["enabled"] is True


def test_config_save_persists_direct_connector_secrets_without_env_placeholders(temp_home: Path) -> None:
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
            "app_secret": "qq-secret",
            "app_secret_env": "QQ_APP_SECRET",
            "bot_name": "DeepScientist",
        }
    ]
    connectors["slack"]["enabled"] = True
    connectors["slack"]["profiles"] = [
        {
            "profile_id": "slack-alpha",
            "enabled": True,
            "bot_name": "Alpha Slack",
            "bot_token": "xoxb-alpha",
            "bot_token_env": "SLACK_BOT_TOKEN",
            "app_token": "xapp-alpha",
            "app_token_env": "SLACK_APP_TOKEN",
        }
    ]

    result = manager.save_named_payload("connectors", connectors)

    assert result["ok"] is True
    saved = manager.path_for("connectors").read_text(encoding="utf-8")
    assert "qq-secret" in saved
    assert "xoxb-alpha" in saved
    assert "xapp-alpha" in saved
    assert "QQ_APP_SECRET" not in saved
    assert "SLACK_BOT_TOKEN" not in saved
    assert "SLACK_APP_TOKEN" not in saved


def test_config_save_accepts_disabled_placeholder_profiles_without_blocking_other_connector_changes(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["telegram"]["profiles"] = [
        {
            "profile_id": "telegram-deepscientist",
            "enabled": False,
            "transport": "polling",
            "bot_name": "DeepScientist",
            "bot_token": None,
            "bot_token_env": "TELEGRAM_BOT_TOKEN",
        }
    ]
    connectors["discord"]["profiles"] = [
        {
            "profile_id": "discord-deepscientist",
            "enabled": False,
            "transport": "gateway",
            "bot_name": "DeepScientist",
            "bot_token": None,
            "bot_token_env": "DISCORD_BOT_TOKEN",
            "application_id": None,
        }
    ]
    connectors["slack"]["profiles"] = [
        {
            "profile_id": "slack-deepscientist",
            "enabled": False,
            "transport": "socket_mode",
            "bot_name": "DeepScientist",
            "bot_token": None,
            "bot_token_env": "SLACK_BOT_TOKEN",
            "bot_user_id": None,
            "app_token": None,
            "app_token_env": "SLACK_APP_TOKEN",
        }
    ]
    connectors["feishu"]["profiles"] = [
        {
            "profile_id": "feishu-deepscientist",
            "enabled": False,
            "transport": "long_connection",
            "bot_name": "DeepScientist",
            "app_id": None,
            "app_secret": None,
            "app_secret_env": "FEISHU_APP_SECRET",
            "api_base_url": "https://open.feishu.cn",
        }
    ]
    connectors["whatsapp"]["profiles"] = [
        {
            "profile_id": "whatsapp-deepscientist",
            "enabled": False,
            "transport": "local_session",
            "bot_name": "DeepScientist",
            "auth_method": "qr_browser",
            "session_dir": "~/.deepscientist/connectors/whatsapp",
        }
    ]
    connectors["weixin"]["bot_token"] = "wx-bot-token"
    connectors["weixin"]["account_id"] = "wx-bot-1@im.bot"
    connectors["weixin"]["login_user_id"] = "wx-owner@im.wechat"

    result = manager.save_named_payload("connectors", connectors)

    assert result["ok"] is True
    parsed = manager.load_named_normalized("connectors")
    assert parsed["weixin"]["enabled"] is True
    assert parsed["telegram"]["enabled"] is False
    assert parsed["telegram"]["profiles"] == []
    assert parsed["discord"]["profiles"] == []
    assert parsed["slack"]["profiles"] == []
    assert parsed["feishu"]["profiles"] == []
    assert parsed["whatsapp"]["profiles"] == []


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
    channel.send(
        {
            "conversation_id": alpha_conversation_id,
            "message": "milestone sent to alpha",
        }
    )
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
    assert by_profile["telegram-alpha"]["inbox_count"] == 1
    assert by_profile["telegram-alpha"]["outbox_count"] == 1
    assert by_profile["telegram-beta"]["binding_count"] == 0
    assert by_profile["telegram-beta"]["inbox_count"] == 1
    assert by_profile["telegram-beta"]["outbox_count"] == 0
    assert any(item["conversation_id"] == alpha_conversation_id for item in by_profile["telegram-alpha"]["discovered_targets"])
    assert any(item["conversation_id"] == beta_conversation_id for item in by_profile["telegram-beta"]["discovered_targets"])


def test_qq_status_exposes_profile_scoped_message_counts(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    connectors = default_connectors()
    connectors["qq"]["enabled"] = True
    connectors["qq"]["profiles"] = [
        {
            "profile_id": "qq-alpha",
            "enabled": True,
            "bot_name": "Alpha QQ",
            "app_id": "1903299925",
            "app_secret": "qq-secret-alpha",
            "main_chat_id": "OPENID-ALPHA",
        },
        {
            "profile_id": "qq-beta",
            "enabled": True,
            "bot_name": "Beta QQ",
            "app_id": "1903299926",
            "app_secret": "qq-secret-beta",
        },
    ]
    channel = QQRelayChannel(temp_home, connectors["qq"])

    alpha_conversation_id = format_conversation_id("qq", "direct", "OPENID-ALPHA", profile_id="qq-alpha")
    beta_conversation_id = format_conversation_id("qq", "direct", "OPENID-BETA", profile_id="qq-beta")
    channel.ingest(
        {
            "conversation_id": alpha_conversation_id,
            "chat_type": "direct",
            "sender_id": "OPENID-ALPHA",
            "sender_name": "Alice",
            "text": "/help",
            "profile_id": "qq-alpha",
            "profile_label": "Alpha QQ",
        }
    )
    channel.ingest(
        {
            "conversation_id": beta_conversation_id,
            "chat_type": "direct",
            "sender_id": "OPENID-BETA",
            "sender_name": "Bob",
            "text": "/help",
            "profile_id": "qq-beta",
            "profile_label": "Beta QQ",
        }
    )
    channel.send(
        {
            "conversation_id": alpha_conversation_id,
            "message": "alpha outbound",
        }
    )

    snapshot = channel.status()

    by_profile = {item["profile_id"]: item for item in snapshot["profiles"]}
    assert by_profile["qq-alpha"]["inbox_count"] == 1
    assert by_profile["qq-alpha"]["outbox_count"] == 1
    assert by_profile["qq-beta"]["inbox_count"] == 1
    assert by_profile["qq-beta"]["outbox_count"] == 0


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


def test_feishu_delivery_retries_transient_urlopen_error(monkeypatch) -> None:
    calls: list[str] = []

    class _Response:
        def __init__(self, status: int, payload: dict) -> None:
            self.status = status
            self._payload = payload

        def __enter__(self):  # noqa: ANN001
            return self

        def __exit__(self, exc_type, exc, traceback):  # noqa: ANN001
            return False

        def read(self) -> bytes:
            return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")

    def fake_urlopen(request, timeout=8):  # noqa: ANN001
        url = str(getattr(request, "full_url", ""))
        calls.append(url)
        if len(calls) == 1:
            raise URLError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol")
        if "tenant_access_token" in url:
            return _Response(200, {"tenant_access_token": "tenant-token"})
        return _Response(200, {"code": 0, "msg": "success"})

    monkeypatch.setattr("deepscientist.bridges.connectors.urlopen", fake_urlopen)

    result = FeishuConnectorBridge().deliver_direct(
        {
            "conversation_id": "feishu:direct:oc_123",
            "text": "hello",
            "attachments": [],
        },
        {
            "app_id": "cli_xxx",
            "app_secret": "secret",
        },
    )

    assert result is not None
    assert result["ok"] is True
    assert result["retry_count"] == 1
    assert len(calls) == 3


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
