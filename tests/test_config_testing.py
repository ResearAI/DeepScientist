from __future__ import annotations

import json
from pathlib import Path

from deepscientist.bridges import register_builtin_connector_bridges
from deepscientist.config import ConfigManager
from deepscientist.daemon.app import DaemonApp
from deepscientist.home import ensure_home_layout
from deepscientist.connector.lingzhu_support import generate_lingzhu_auth_ak


def test_config_show_includes_help_markdown_and_testability(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    app = DaemonApp(temp_home)

    payload = app.handlers.config_show("connectors")

    assert payload["document_id"] == "connectors"
    assert payload["meta"]["system_testable"] is True
    assert "Connector Settings Guide" in payload["meta"]["help_markdown"]
    assert isinstance(payload["meta"]["structured_config"], dict)
    assert "telegram" in payload["meta"]["structured_config"]


def test_default_config_removes_report_palette_settings_and_keeps_qq_media_policy(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    config_payload = manager.load_named("config")
    connectors_payload = manager.load_named("connectors")

    assert "reports" not in config_payload

    assert connectors_payload["qq"]["auto_send_main_experiment_png"] is True
    assert connectors_payload["qq"]["auto_send_analysis_summary_png"] is True
    assert connectors_payload["qq"]["auto_send_slice_png"] is True
    assert connectors_payload["qq"]["auto_send_paper_pdf"] is True
    assert connectors_payload["qq"]["enable_file_upload_experimental"] is False
    assert connectors_payload["weixin"]["auto_send_main_experiment_png"] is True


def test_default_runtime_config_enables_telegram_feishu_and_whatsapp_system_gates(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    gates = manager.system_connector_gates()

    assert gates["qq"] is True
    assert gates["weixin"] is True
    assert gates["telegram"] is True
    assert gates["feishu"] is True
    assert gates["whatsapp"] is True
    assert gates["lingzhu"] is True


def test_daemon_app_exposes_telegram_feishu_and_whatsapp_as_system_enabled(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    app = DaemonApp(temp_home)

    assert app._is_connector_system_enabled("telegram") is True
    assert app._is_connector_system_enabled("feishu") is True
    assert app._is_connector_system_enabled("whatsapp") is True


def test_config_normalization_strips_legacy_report_palette_block(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    normalized = manager._normalize_named_payload(
        "config",
        {
            **manager.load_named("config"),
            "reports": {
                "default_palette": "mist-stone",
                "qq_summary_palette": "sage-clay",
                "paper_figure_palette": "mist-stone",
            },
        },
    )

    assert "reports" not in normalized


def test_config_normalization_infers_user_locale_source_for_legacy_manual_override(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    normalized = manager._normalize_named_payload(
        "config",
        {
            **manager.load_named("config"),
            "default_locale": "en-US",
            "bootstrap": {
                "codex_ready": False,
                "codex_last_checked_at": None,
                "codex_last_result": {},
            },
        },
    )

    assert normalized["default_locale"] == "en-US"
    assert normalized["bootstrap"]["locale_source"] == "user"
    assert normalized["bootstrap"]["locale_initialized_from_browser"] is False


def test_config_normalization_preserves_browser_locale_bootstrap_metadata(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    normalized = manager._normalize_named_payload(
        "config",
        {
            **manager.load_named("config"),
            "default_locale": "en-US",
            "bootstrap": {
                "codex_ready": False,
                "codex_last_checked_at": None,
                "codex_last_result": {},
                "locale_source": "browser",
                "locale_initialized_from_browser": True,
                "locale_initialized_at": "2026-03-18T00:00:00+00:00",
                "locale_initialized_browser_locale": "en-US",
            },
        },
    )

    assert normalized["bootstrap"]["locale_source"] == "browser"
    assert normalized["bootstrap"]["locale_initialized_from_browser"] is True
    assert normalized["bootstrap"]["locale_initialized_at"] == "2026-03-18T00:00:00+00:00"
    assert normalized["bootstrap"]["locale_initialized_browser_locale"] == "en-US"


def test_connectors_config_test_uses_system_probe(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["telegram"]["enabled"] = True
    connectors["telegram"]["bot_token"] = "telegram-token"

    def fake_http_json(url: str, **kwargs):  # noqa: ANN001
        assert "getMe" in url
        return {"ok": True, "result": {"username": "DeepScientistBot"}}

    monkeypatch.setattr("deepscientist.config.service.ConfigManager._http_json", staticmethod(fake_http_json))

    import yaml

    result = manager.test_named_text("connectors", yaml.safe_dump(connectors, sort_keys=False), live=True)

    assert result["ok"] is True
    assert result["items"]
    item = result["items"][0]
    assert item["name"] == "telegram"
    assert item["details"]["identity"] == "DeepScientistBot"


def test_connectors_config_validate_lingzhu_requires_auth_ak_after_public_url_is_filled(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["lingzhu"]["public_base_url"] = "https://deepscientist.example.com"

    result = manager.validate_named_payload("connectors", connectors)

    assert result["ok"] is False
    assert any("requires `auth_ak`" in item for item in result["errors"])


def test_connectors_config_validate_weixin_requires_bot_token_after_partial_qr_fill(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["weixin"]["account_id"] = "wx-account"

    result = manager.validate_named_payload("connectors", connectors)

    assert result["ok"] is False
    assert any("requires `bot_token`" in item for item in result["errors"])


def test_connectors_normalization_auto_enables_ready_weixin_and_lingzhu(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["weixin"]["enabled"] = False
    connectors["weixin"]["bot_token"] = "weixin-token"
    connectors["weixin"]["account_id"] = "wx-account"
    connectors["lingzhu"]["enabled"] = False
    connectors["lingzhu"]["auth_ak"] = generate_lingzhu_auth_ak()
    connectors["lingzhu"]["public_base_url"] = "https://deepscientist.example.com"

    normalized = manager._normalize_named_payload("connectors", connectors)

    assert normalized["weixin"]["enabled"] is True
    assert normalized["lingzhu"]["enabled"] is True


def test_connectors_config_save_generates_and_persists_lingzhu_auth_ak(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["public_base_url"] = "https://deepscientist.example.com"

    result = manager.save_named_payload("connectors", connectors)

    assert result["ok"] is True
    saved = manager.load_named("connectors")
    assert str(saved["lingzhu"]["auth_ak"]).strip()


def test_connectors_config_save_rotates_example_lingzhu_auth_ak(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["public_base_url"] = "https://deepscientist.example.com"
    connectors["lingzhu"]["auth_ak"] = "abcd1234-abcd-abcd-abcd-abcdefghijkl"

    result = manager.save_named_payload("connectors", connectors)

    assert result["ok"] is True
    saved = manager.load_named("connectors")
    assert str(saved["lingzhu"]["auth_ak"]).strip()
    assert saved["lingzhu"]["auth_ak"] != "abcd1234-abcd-abcd-abcd-abcdefghijkl"


def test_connectors_config_validate_lingzhu_rejects_local_public_base_url(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["public_base_url"] = "http://127.0.0.1:20999"

    result = manager.validate_named_payload("connectors", connectors)

    assert result["ok"] is False
    assert any("public IP or public domain" in item for item in result["errors"])


def test_connectors_config_validate_lingzhu_rejects_example_auth_ak(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["public_base_url"] = "https://deepscientist.example.com"
    connectors["lingzhu"]["auth_ak"] = "abcd1234-abcd-abcd-abcd-abcdefghijkl"

    result = manager.validate_named_payload("connectors", connectors)

    assert result["ok"] is False
    assert any("bundled example token" in item for item in result["errors"])


def test_config_test_api_route_returns_items(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    app = DaemonApp(temp_home)

    def fake_test_named_text(name: str, content: str, *, live: bool = True):  # noqa: ANN001
        return {
            "ok": True,
            "name": name,
            "summary": "Config test completed.",
            "warnings": [],
            "errors": [],
            "items": [{"name": "git", "ok": True, "warnings": [], "errors": [], "details": {"installed": True}}],
        }

    monkeypatch.setattr(app.config_manager, "test_named_text", fake_test_named_text)

    payload = app.handlers.config_test({"name": "config", "content": json.dumps({}), "live": True})

    assert payload["ok"] is True
    assert payload["items"][0]["name"] == "git"


def test_connectors_config_test_supports_lingzhu_probe(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    auth_ak = generate_lingzhu_auth_ak()
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = auth_ak
    connectors["lingzhu"]["gateway_port"] = 18789
    connectors["lingzhu"]["public_base_url"] = "http://203.0.113.10:18789"

    monkeypatch.setattr(
        manager,
        "_probe_lingzhu_health",
        lambda config, timeout=5.0: {"ok": True, "status": "ok", "payload": {"status": "ok"}},
    )
    monkeypatch.setattr(
        manager,
        "_probe_lingzhu_sse",
        lambda config, timeout=8.0: {"ok": True, "content_type": "text/event-stream", "preview": "event: message\\ndata: {}"},
    )

    result = manager.test_named_payload("connectors", connectors, live=True)

    assert result["ok"] is True
    item = next(entry for entry in result["items"] if entry["name"] == "lingzhu")
    assert item["details"]["transport"] == "openclaw_sse"
    assert item["details"]["endpoint_url"] == "http://127.0.0.1:18789/metis/agent/api/sse"
    assert item["details"]["public_endpoint_url"] == "http://203.0.113.10:18789/metis/agent/api/sse"
    assert "authAk" in str(item["details"]["generated_openclaw_config"])
    assert "autoReceiptAck" in str(item["details"]["generated_openclaw_config"])
    assert "visibleProgressHeartbeat" in str(item["details"]["generated_openclaw_config"])
    assert "Authorization: Bearer" in str(item["details"]["generated_curl"])


def test_config_save_validate_and_test_accept_structured_connectors(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    app = DaemonApp(temp_home)

    structured = manager.load_named("connectors")
    structured["telegram"]["enabled"] = True
    structured["telegram"]["bot_token"] = "telegram-token"

    def fake_http_json(url: str, **kwargs):  # noqa: ANN001
        assert "getMe" in url
        return {"ok": True, "result": {"username": "DeepScientistBot"}}

    monkeypatch.setattr("deepscientist.config.service.ConfigManager._http_json", staticmethod(fake_http_json))

    save_payload = app.handlers.config_save("connectors", {"structured": structured})
    assert save_payload["ok"] is True

    validate_payload = app.handlers.config_validate({"name": "connectors", "structured": structured})
    assert validate_payload["ok"] is True

    test_payload = app.handlers.config_test({"name": "connectors", "structured": structured, "live": True})
    assert test_payload["ok"] is True
    assert test_payload["items"][0]["name"] == "telegram"


def test_config_save_reloads_system_connector_visibility(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    app = DaemonApp(temp_home)

    assert "telegram" not in {item["name"] for item in app.handlers.connectors()}

    structured = manager.load_named("config")
    structured["connectors"]["system_enabled"]["telegram"] = True

    payload = app.handlers.config_save("config", {"structured": structured})

    assert payload["ok"] is True
    assert payload["runtime_reload"]["ok"] is True
    assert "telegram" in payload["runtime_reload"]["system_enabled_connectors"]
    assert "telegram" in {item["name"] for item in app.handlers.connectors()}


def test_structured_connector_test_passes_delivery_targets(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    app = DaemonApp(temp_home)

    structured = manager.load_named("connectors")
    structured["telegram"]["enabled"] = True
    structured["telegram"]["bot_token"] = "telegram-token"

    def fake_http_json(url: str, **kwargs):  # noqa: ANN001
        return {"ok": True, "result": {"username": "DeepScientistBot"}}

    monkeypatch.setattr("deepscientist.config.service.ConfigManager._http_json", staticmethod(fake_http_json))

    deliveries: list[tuple[dict, dict]] = []

    class FakeBridge:
        def deliver(self, outbound: dict, config: dict) -> dict:  # noqa: ANN001
            deliveries.append((outbound, config))
            return {"ok": True, "transport": "direct"}

    monkeypatch.setattr("deepscientist.bridges.get_connector_bridge", lambda name: FakeBridge())

    payload = app.handlers.config_test(
        {
            "name": "connectors",
            "structured": structured,
            "live": True,
            "delivery_targets": {
                "telegram": {
                    "chat_type": "direct",
                    "chat_id": "12345",
                    "text": "老师您好，这是一条主动发送测试。",
                }
            },
        }
    )

    assert payload["ok"] is True
    assert deliveries
    outbound, config = deliveries[0]
    assert outbound["conversation_id"] == "telegram:direct:12345"
    assert outbound["text"] == "老师您好，这是一条主动发送测试。"
    assert config["bot_token"] == "telegram-token"


def test_connectors_config_test_supports_qq_direct_without_callback_url(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["app_id"] = "1903299925"
    connectors["qq"]["app_secret"] = "qq-secret"

    def fake_http_json(url: str, **kwargs):  # noqa: ANN001
        if url == "https://bots.qq.com/app/getAppAccessToken":
            assert kwargs["method"] == "POST"
            assert kwargs["body"] == {"appId": "1903299925", "clientSecret": "qq-secret"}
            return {"access_token": "qq-access-token", "expires_in": 7200}
        if url == "https://api.sgroup.qq.com/gateway":
            assert kwargs["headers"]["Authorization"] == "QQBot qq-access-token"
            return {"url": "wss://api.sgroup.qq.com/websocket"}
        raise AssertionError(url)

    monkeypatch.setattr("deepscientist.config.service.ConfigManager._http_json", staticmethod(fake_http_json))

    import yaml

    result = manager.test_named_text(
        "connectors",
        yaml.safe_dump(connectors, sort_keys=False),
        live=True,
        delivery_targets={"qq": {"chat_type": "direct", "chat_id": "", "text": ""}},
    )

    assert result["ok"] is True
    item = result["items"][0]
    assert item["name"] == "qq"
    assert item["details"]["transport"] == "gateway_direct"
    assert item["details"]["gateway_url"] == "wss://api.sgroup.qq.com/websocket"
    assert not any("public_callback_url" in warning for warning in item["warnings"])
    assert not any("target chat id is empty" in warning for warning in item["warnings"])


def test_connectors_config_test_uses_recent_qq_conversation_as_default_target(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["app_id"] = "1903299925"
    connectors["qq"]["app_secret"] = "qq-secret"

    qq_state_root = temp_home / "logs" / "connectors" / "qq"
    qq_state_root.mkdir(parents=True, exist_ok=True)
    (qq_state_root / "state.json").write_text('{"last_conversation_id":"qq:direct:openid-123"}', encoding="utf-8")

    def fake_http_json(url: str, **kwargs):  # noqa: ANN001
        if url == "https://bots.qq.com/app/getAppAccessToken":
            return {"access_token": "qq-access-token", "expires_in": 7200}
        if url == "https://api.sgroup.qq.com/gateway":
            return {"url": "wss://api.sgroup.qq.com/websocket"}
        raise AssertionError(url)

    monkeypatch.setattr("deepscientist.config.service.ConfigManager._http_json", staticmethod(fake_http_json))

    deliveries: list[tuple[dict, dict]] = []

    class FakeBridge:
        def deliver(self, outbound: dict, config: dict) -> dict:  # noqa: ANN001
            deliveries.append((outbound, config))
            return {"ok": True, "transport": "qq-gateway-direct"}

    monkeypatch.setattr("deepscientist.bridges.get_connector_bridge", lambda name: FakeBridge())

    import yaml

    result = manager.test_named_text(
        "connectors",
        yaml.safe_dump(connectors, sort_keys=False),
        live=True,
        delivery_targets={"qq": {"chat_type": "direct", "chat_id": "", "text": "测试消息"}},
    )

    assert result["ok"] is True
    assert deliveries
    outbound, _config = deliveries[0]
    assert outbound["conversation_id"] == "qq:direct:openid-123"
    item = result["items"][0]
    assert item["details"]["delivery_target"]["used_default_target"] is True
    assert not any("target is empty" in warning for warning in item["warnings"])


def test_connectors_config_test_queues_whatsapp_local_session_delivery(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    session_dir = temp_home / "whatsapp-session"
    connectors["whatsapp"]["enabled"] = True
    connectors["whatsapp"]["transport"] = "local_session"
    connectors["whatsapp"]["session_dir"] = str(session_dir)
    connectors["whatsapp"]["group_policy"] = "open"
    register_builtin_connector_bridges()

    import yaml

    result = manager.test_named_text(
        "connectors",
        yaml.safe_dump(connectors, sort_keys=False),
        live=True,
        delivery_targets={
            "whatsapp": {
                "chat_type": "direct",
                "chat_id": "15550001111@s.whatsapp.net",
                "text": "老师您好，这是一条本地 session 测试消息。",
            }
        },
    )

    assert result["ok"] is True
    item = next(entry for entry in result["items"] if entry["name"] == "whatsapp")
    assert item["details"]["delivery"]["transport"] == "whatsapp-local-session"
    outbox_path = session_dir / "outbox.jsonl"
    assert outbox_path.exists()


def test_plugins_structured_config_normalizes_legacy_search_paths(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)

    payload = manager.validate_named_payload(
        "plugins",
        {
            "search_paths": ["/tmp/plugins"],
            "enabled": ["plugin-a"],
        },
    )

    assert payload["ok"] is True
    normalized = payload["parsed"]
    assert normalized["load_paths"] == ["/tmp/plugins"]
    assert normalized["enabled"] == ["plugin-a"]
    assert normalized["disabled"] == []
    assert normalized["allow_unsigned"] is False


def test_mcp_structured_config_normalizes_list_and_validates_required_fields(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)

    payload = manager.validate_named_payload(
        "mcp_servers",
        {
            "servers": [
                {
                    "name": "browser",
                    "enabled": True,
                    "transport": "stdio",
                    "command": ["npx", "@example/browser-mcp"],
                    "env": {"TOKEN": "secret"},
                },
                {
                    "name": "papers",
                    "enabled": True,
                    "transport": "streamable_http",
                    "url": "https://example.com/mcp",
                },
            ]
        },
    )

    assert payload["ok"] is True
    normalized = payload["parsed"]
    assert normalized["servers"]["browser"]["command"] == ["npx", "@example/browser-mcp"]
    assert normalized["servers"]["papers"]["url"] == "https://example.com/mcp"


def test_runners_config_test_executes_live_codex_probe(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    runners = manager.load_named("runners")
    runners["codex"]["enabled"] = True
    runners["codex"]["binary"] = "codex"

    monkeypatch.setattr("deepscientist.config.service.resolve_runner_binary", lambda binary, runner_name=None: "/tmp/fake-codex")
    monkeypatch.setattr(
        manager,
        "_probe_codex_runner",
        lambda config: {
            "ok": True,
            "summary": "Codex startup probe completed.",
            "warnings": [],
            "errors": [],
            "details": {
                "resolved_binary": "/tmp/fake-codex",
                "stdout_excerpt": '{"item":{"text":"HELLO"}}',
            },
        },
    )

    result = manager.test_named_payload("runners", runners, live=True)

    assert result["ok"] is True
    codex = next(item for item in result["items"] if item["name"] == "codex")
    assert codex["details"]["resolved_binary"] == "/tmp/fake-codex"
    assert codex["details"]["live_probe_executed"] is True
    assert codex["details"]["stdout_excerpt"]


def test_codex_probe_omits_reasoning_effort_flag_when_runner_sets_none(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    captured: dict[str, object] = {}

    monkeypatch.setattr("deepscientist.config.service.resolve_runner_binary", lambda binary, runner_name=None: "/tmp/fake-codex")

    def fake_run(command, **kwargs):  # noqa: ANN001
        captured["command"] = list(command)

        class Result:
            returncode = 0
            stdout = '{"type":"item.completed","item":{"text":"HELLO"}}'
            stderr = ""

        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    result = manager._probe_codex_runner(
        {
            "binary": "codex",
            "config_dir": "~/.codex",
            "model": "gpt-5.4",
            "approval_policy": "on-request",
            "sandbox_mode": "workspace-write",
            "model_reasoning_effort": "",
        }
    )

    command = [str(part) for part in captured["command"]]
    assert result["ok"] is True
    assert result["details"]["reasoning_effort"] is None
    assert not any("model_reasoning_effort=" in part for part in command)


def test_codex_probe_downgrades_xhigh_for_legacy_codex_cli(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    captured: dict[str, object] = {}

    monkeypatch.setattr("deepscientist.config.service.resolve_runner_binary", lambda binary, runner_name=None: "/tmp/fake-codex")
    monkeypatch.setattr(
        "deepscientist.config.service.normalize_codex_reasoning_effort",
        lambda reasoning_effort, *, resolved_binary: ("high", "downgraded to high"),
    )

    def fake_run(command, **kwargs):  # noqa: ANN001
        captured["command"] = list(command)

        class Result:
            returncode = 0
            stdout = '{"type":"item.completed","item":{"text":"HELLO"}}'
            stderr = ""

        return Result()

    monkeypatch.setattr("deepscientist.config.service.subprocess.run", fake_run)

    result = manager._probe_codex_runner({"binary": "codex", "model": "inherit"})

    command = [str(part) for part in captured["command"]]
    assert result["ok"] is True
    assert result["details"]["requested_reasoning_effort"] == "xhigh"
    assert result["details"]["reasoning_effort"] == "high"
    assert "downgraded to high" in "\n".join(result["warnings"])
    assert any('model_reasoning_effort="high"' in part for part in command)
    assert not any('model_reasoning_effort="xhigh"' in part for part in command)


def test_codex_probe_missing_binary_includes_explicit_install_guidance(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    monkeypatch.setattr("deepscientist.config.service.resolve_runner_binary", lambda binary, runner_name=None: None)

    result = manager._probe_codex_runner({"binary": "codex", "model": "gpt-5.4"})

    assert result["ok"] is False
    assert "npm install -g @openai/codex" in "\n".join(result["guidance"])
    assert "codex --login" in "\n".join(result["guidance"])


def test_codex_probe_passes_profile_and_runner_env_to_subprocess(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    monkeypatch.setattr("deepscientist.config.service.resolve_runner_binary", lambda binary, runner_name=None: "/tmp/fake-codex")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        if list(command) == ["/tmp/fake-codex", "--version"]:
            class VersionResult:
                returncode = 0
                stdout = "codex-cli 0.116.0"
                stderr = ""

            return VersionResult()
        captured["command"] = list(command)
        captured["env"] = dict(kwargs.get("env") or {})

        class Result:
            returncode = 0
            stdout = '{"type":"item.completed","item":{"text":"HELLO"}}'
            stderr = ""

        return Result()

    monkeypatch.setattr("deepscientist.config.service.subprocess.run", fake_run)

    result = manager._probe_codex_runner(
        {
            "binary": "codex",
            "profile": "m27",
            "model": "inherit",
            "env": {"MINIMAX_API_KEY": "secret-value"},
        }
    )

    assert result["ok"] is True
    assert result["details"]["profile"] == "m27"
    assert captured["command"][:4] == ["/tmp/fake-codex", "--search", "--profile", "m27"]
    assert captured["env"]["MINIMAX_API_KEY"] == "secret-value"


def test_codex_probe_omits_empty_runner_env_values(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("deepscientist.config.service.resolve_runner_binary", lambda binary, runner_name=None: "/tmp/fake-codex")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        if list(command) == ["/tmp/fake-codex", "--version"]:
            class VersionResult:
                returncode = 0
                stdout = "codex-cli 0.116.0"
                stderr = ""

            return VersionResult()
        captured["env"] = dict(kwargs.get("env") or {})

        class Result:
            returncode = 0
            stdout = '{"type":"item.completed","item":{"text":"HELLO"}}'
            stderr = ""

        return Result()

    monkeypatch.setattr("deepscientist.config.service.subprocess.run", fake_run)

    result = manager._probe_codex_runner(
        {
            "binary": "codex",
            "model": "inherit",
            "env": {
                "OPENAI_BASE_URL": "",
                "OPENAI_API_KEY": "",
                "MINIMAX_API_KEY": "secret-value",
            },
        }
    )

    assert result["ok"] is True
    assert "MINIMAX_API_KEY" in captured["env"]
    assert "OPENAI_BASE_URL" not in captured["env"]
    assert "OPENAI_API_KEY" not in captured["env"]


def test_codex_probe_adapts_profile_only_provider_config_for_legacy_minimax_shape(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    source_codex_home = temp_home / "provider-codex-home"
    source_codex_home.mkdir(parents=True, exist_ok=True)
    (source_codex_home / "config.toml").write_text(
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
    (source_codex_home / "skills" / "global-skill").mkdir(parents=True, exist_ok=True)
    (source_codex_home / "skills" / "global-skill" / "SKILL.md").write_text("GLOBAL\n", encoding="utf-8")
    (source_codex_home / "agents").mkdir(parents=True, exist_ok=True)
    (source_codex_home / "agents" / "global-agent.md").write_text("GLOBAL AGENT\n", encoding="utf-8")
    (source_codex_home / "prompts").mkdir(parents=True, exist_ok=True)
    (source_codex_home / "prompts" / "system.md").write_text("GLOBAL PROMPT\n", encoding="utf-8")

    monkeypatch.setattr("deepscientist.config.service.resolve_runner_binary", lambda binary, runner_name=None: "/tmp/fake-codex")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        if list(command) == ["/tmp/fake-codex", "--version"]:
            class VersionResult:
                returncode = 0
                stdout = "codex-cli 0.116.0"
                stderr = ""

            return VersionResult()
        captured["command"] = list(command)
        captured["env"] = dict(kwargs.get("env") or {})
        prepared_home = Path(str(captured["env"]["CODEX_HOME"]))
        captured["prepared_config"] = (prepared_home / "config.toml").read_text(encoding="utf-8")
        captured["prepared_skill"] = (prepared_home / "skills" / "global-skill" / "SKILL.md").read_text(encoding="utf-8")
        captured["prepared_agent"] = (prepared_home / "agents" / "global-agent.md").read_text(encoding="utf-8")
        captured["prepared_prompt"] = (prepared_home / "prompts" / "system.md").read_text(encoding="utf-8")

        class Result:
            returncode = 0
            stdout = '{"type":"item.completed","item":{"text":"HELLO"}}'
            stderr = ""

        return Result()

    monkeypatch.setattr("deepscientist.config.service.subprocess.run", fake_run)

    result = manager._probe_codex_runner(
        {
            "binary": "codex",
            "profile": "m27",
            "model": "inherit",
            "config_dir": str(source_codex_home),
        }
    )

    assert result["ok"] is True
    assert Path(str(captured["env"]["CODEX_HOME"])) != source_codex_home
    assert 'model_provider = "minimax"' in str(captured["prepared_config"])
    assert 'model = "MiniMax-M2.7"' in str(captured["prepared_config"])
    assert captured["prepared_skill"] == "GLOBAL\n"
    assert captured["prepared_agent"] == "GLOBAL AGENT\n"
    assert captured["prepared_prompt"] == "GLOBAL PROMPT\n"


def test_codex_probe_overrides_conflicting_top_level_model_selection_for_provider_profile(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    source_codex_home = temp_home / "provider-codex-home-conflict"
    source_codex_home.mkdir(parents=True, exist_ok=True)
    (source_codex_home / "config.toml").write_text(
        """model = "gpt-5.4"
model_provider = "OpenAI"
model_reasoning_effort = "xhigh"

[model_providers.minimax]
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

    monkeypatch.setattr("deepscientist.config.service.resolve_runner_binary", lambda binary, runner_name=None: "/tmp/fake-codex")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        if list(command) == ["/tmp/fake-codex", "--version"]:
            class VersionResult:
                returncode = 0
                stdout = "codex-cli 0.57.0"
                stderr = ""

            return VersionResult()
        captured["command"] = list(command)
        captured["env"] = dict(kwargs.get("env") or {})
        prepared_home = Path(str(captured["env"]["CODEX_HOME"]))
        captured["prepared_config"] = (prepared_home / "config.toml").read_text(encoding="utf-8")

        class Result:
            returncode = 0
            stdout = '{"type":"item.completed","item":{"text":"HELLO"}}'
            stderr = ""

        return Result()

    monkeypatch.setattr("deepscientist.config.service.subprocess.run", fake_run)

    result = manager._probe_codex_runner(
        {
            "binary": "codex",
            "profile": "m27",
            "model": "inherit",
            "config_dir": str(source_codex_home),
        }
    )

    assert result["ok"] is True
    assert 'model_provider = "minimax"' in str(captured["prepared_config"])
    assert 'model = "MiniMax-M2.7"' in str(captured["prepared_config"])
    assert 'model_provider = "OpenAI"' not in str(captured["prepared_config"])
    assert 'model = "gpt-5.4"' not in str(captured["prepared_config"])
    assert 'model_reasoning_effort = "xhigh"' in str(captured["prepared_config"])
    assert any("overrode conflicting top-level" in warning for warning in result["warnings"])


def test_codex_probe_forces_inherit_model_for_provider_profile(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    source_codex_home = temp_home / "provider-codex-home"
    source_codex_home.mkdir(parents=True, exist_ok=True)
    (source_codex_home / "config.toml").write_text(
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

    monkeypatch.setattr("deepscientist.config.service.resolve_runner_binary", lambda binary, runner_name=None: "/tmp/fake-codex")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        captured["command"] = list(command)
        captured["env"] = dict(kwargs.get("env") or {})

        class Result:
            returncode = 0
            stdout = '{"item":{"text":"HELLO"}}'
            stderr = ""

        return Result()

    monkeypatch.setattr("deepscientist.config.service.subprocess.run", fake_run)

    result = manager._probe_codex_runner(
        {
            "binary": "codex",
            "profile": "m27",
            "model": "gpt-5.4",
            "config_dir": str(source_codex_home),
        }
    )

    assert result["ok"] is True
    assert result["details"]["requested_model"] == "gpt-5.4"
    assert result["details"]["effective_model"] == "inherit"
    assert "--model" not in captured["command"]


def test_codex_probe_strips_openai_env_for_minimax_provider(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    source_codex_home = temp_home / "provider-codex-home"
    source_codex_home.mkdir(parents=True, exist_ok=True)
    (source_codex_home / "config.toml").write_text(
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

    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setattr("deepscientist.config.service.resolve_runner_binary", lambda binary, runner_name=None: "/tmp/fake-codex")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        captured["env"] = dict(kwargs.get("env") or {})

        class Result:
            returncode = 0
            stdout = '{"item":{"text":"HELLO"}}'
            stderr = ""

        return Result()

    monkeypatch.setattr("deepscientist.config.service.subprocess.run", fake_run)

    result = manager._probe_codex_runner(
        {
            "binary": "codex",
            "profile": "m27",
            "model": "inherit",
            "config_dir": str(source_codex_home),
            "env": {"MINIMAX_API_KEY": "secret-value"},
        }
    )

    assert result["ok"] is True
    assert captured["env"]["MINIMAX_API_KEY"] == "secret-value"
    assert "OPENAI_API_KEY" not in captured["env"]
    assert "OPENAI_BASE_URL" not in captured["env"]
    assert "promoted `m27` profile" in "\n".join(result["warnings"])


def test_codex_probe_profile_guidance_avoids_login_language(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    monkeypatch.setattr("deepscientist.config.service.resolve_runner_binary", lambda binary, runner_name=None: "/tmp/fake-codex")

    def fake_run(command, **kwargs):  # noqa: ANN001
        class Result:
            returncode = 1
            stdout = ""
            stderr = "MiniMax profile failed to initialize"

        return Result()

    monkeypatch.setattr("deepscientist.config.service.subprocess.run", fake_run)

    result = manager._probe_codex_runner({"binary": "codex", "profile": "m27", "model": "inherit"})

    assert result["ok"] is False
    guidance_text = "\n".join(result["guidance"])
    error_text = "\n".join(result["errors"])
    assert "--profile m27" in guidance_text
    assert "codex --login" not in guidance_text
    assert "codex --login" not in error_text


def test_codex_probe_failure_guidance_mentions_login_doctor_and_model(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    monkeypatch.setattr("deepscientist.config.service.resolve_runner_binary", lambda binary, runner_name=None: "/tmp/fake-codex")

    def fake_run(command, **kwargs):  # noqa: ANN001
        class Result:
            returncode = 1
            stdout = ""
            stderr = "Please login first"

        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    result = manager._probe_codex_runner({"binary": "codex", "model": "gpt-5.4"})

    assert result["ok"] is False
    guidance_text = "\n".join(result["guidance"])
    error_text = "\n".join(result["errors"])
    assert "codex --login" in guidance_text
    assert "ds doctor" in guidance_text
    assert "configured model" in guidance_text
    assert "codex --login" in error_text


def test_codex_probe_falls_back_to_codex_default_model_when_configured_model_is_unavailable(
    monkeypatch,
    temp_home: Path,
) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    monkeypatch.setattr("deepscientist.config.service.resolve_runner_binary", lambda binary, runner_name=None: "/tmp/fake-codex")
    seen_commands: list[list[str]] = []

    def fake_run(command, **kwargs):  # noqa: ANN001
        seen_commands.append(list(command))
        if any(str(part) == "--model" for part in command):
            class FirstResult:
                returncode = 1
                stdout = ""
                stderr = "Model not found: gpt-5.4"

            return FirstResult()

        class SecondResult:
            returncode = 0
            stdout = '{"type":"item.completed","item":{"text":"HELLO"}}'
            stderr = ""

        return SecondResult()

    monkeypatch.setattr("subprocess.run", fake_run)

    result = manager._probe_codex_runner({"binary": "codex", "model": "gpt-5.4"})

    assert result["ok"] is True
    assert result["details"]["model_fallback_attempted"] is True
    assert result["details"]["model_fallback_used"] is True
    assert result["details"]["effective_model"] == "inherit"
    assert any("--model" in command for command in seen_commands)
    assert any("--model" not in command for command in seen_commands)


def test_codex_bootstrap_fallback_persists_runner_model_as_inherit(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    monkeypatch.setattr(
        manager,
        "_probe_codex_runner",
        lambda config: {
            "ok": True,
            "summary": "Codex startup probe completed with Codex default model fallback.",
            "warnings": ["Configured Codex model `gpt-5.4` is not available."],
            "errors": [],
            "details": {
                "binary": "codex",
                "resolved_binary": "/tmp/fake-codex",
                "model": "gpt-5.4",
                "requested_model": "gpt-5.4",
                "effective_model": "inherit",
                "model_fallback_attempted": True,
                "model_fallback_used": True,
                "approval_policy": "on-request",
                "sandbox_mode": "workspace-write",
                "reasoning_effort": "xhigh",
                "checked_at": "2026-03-22T00:00:00+00:00",
                "exit_code": 0,
                "stdout_excerpt": '{"item":{"text":"HELLO"}}',
                "stderr_excerpt": "",
            },
            "guidance": [
                "DeepScientist switched the Codex runner model to `inherit` so future runs keep using the current Codex default model."
            ],
        },
    )

    result = manager.probe_codex_bootstrap(persist=True)
    runners = manager.load_named_normalized("runners")

    assert result["ok"] is True
    assert runners["codex"]["model"] == "inherit"


def test_codex_bootstrap_probe_persists_success_state(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    monkeypatch.setattr(
        manager,
        "_probe_codex_runner",
        lambda config: {
            "ok": True,
            "summary": "Codex startup probe completed.",
            "warnings": [],
            "errors": [],
            "details": {
                "binary": "codex",
                "resolved_binary": "/tmp/fake-codex",
                "model": "gpt-5.4",
                "approval_policy": "on-request",
                "sandbox_mode": "workspace-write",
                "reasoning_effort": "xhigh",
                "checked_at": "2026-03-15T10:00:00+00:00",
                "exit_code": 0,
                "stdout_excerpt": '{"item":{"text":"HELLO"}}',
                "stderr_excerpt": "",
            },
            "guidance": [],
        },
    )

    result = manager.probe_codex_bootstrap(persist=True)
    state = manager.codex_bootstrap_state()

    assert result["ok"] is True
    assert state["codex_ready"] is True
    assert state["codex_last_checked_at"]
    assert state["codex_last_result"]["summary"] == "Codex startup probe completed."


def test_codex_bootstrap_probe_persists_failure_state(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    monkeypatch.setattr(
        manager,
        "_probe_codex_runner",
        lambda config: {
            "ok": False,
            "summary": "Codex startup probe failed.",
            "warnings": ["Codex returned stderr during the startup probe."],
            "errors": [
                "Codex did not complete the startup hello probe successfully.",
                "Run `codex` once and complete login before starting DeepScientist.",
            ],
            "details": {
                "binary": "codex",
                "resolved_binary": "/tmp/fake-codex",
                "model": "gpt-5.4",
                "approval_policy": "on-request",
                "sandbox_mode": "workspace-write",
                "reasoning_effort": "xhigh",
                "checked_at": "2026-03-15T10:00:00+00:00",
                "exit_code": 1,
                "stdout_excerpt": "",
                "stderr_excerpt": "Please login first",
            },
            "guidance": ["Run `codex` in a terminal and complete login or first-run setup."],
        },
    )

    result = manager.probe_codex_bootstrap(persist=True)
    state = manager.codex_bootstrap_state()

    assert result["ok"] is False
    assert state["codex_ready"] is False
    assert "Please login first" in state["codex_last_result"]["stderr_excerpt"]


def test_saving_runners_profile_invalidates_cached_codex_bootstrap_state(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    config = manager.load_named("config")
    config["bootstrap"]["codex_ready"] = True
    config["bootstrap"]["codex_last_checked_at"] = "2026-03-24T00:00:00+00:00"
    config["bootstrap"]["codex_last_result"] = {"ok": True, "summary": "ready"}
    manager.save_named_payload("config", config)

    runners = manager.load_named("runners")
    runners["codex"]["profile"] = "m27"
    result = manager.save_named_payload("runners", runners)
    state = manager.codex_bootstrap_state()

    assert result["ok"] is True
    assert state["codex_ready"] is False
    assert state["codex_last_result"]["summary"] == "Codex runner configuration changed. A new startup probe is required."
