from __future__ import annotations

from pathlib import Path

from deepscientist.config import ConfigManager
from deepscientist.daemon.app import DaemonApp
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.quest import QuestService
from deepscientist.shared import write_yaml
from deepscientist.skills import SkillInstaller


def test_connector_validation_accepts_no_callback_first_transport_defaults(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["feishu"]["enabled"] = True
    connectors["feishu"]["transport"] = "long_connection"
    connectors["feishu"]["app_id"] = "cli_a1b2c3"
    connectors["feishu"]["app_secret"] = "secret-value"

    import yaml

    result = manager.validate_named_text("connectors", yaml.safe_dump(connectors, sort_keys=False))
    assert result["ok"] is True
    assert result["parsed"]["feishu"]["transport"] == "long_connection"


def test_connector_validation_normalizes_whatsapp_legacy_transport_back_to_local_session(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["whatsapp"]["enabled"] = True
    connectors["whatsapp"]["transport"] = "legacy_meta_cloud"
    connectors["whatsapp"]["session_dir"] = str(temp_home / "whatsapp-session")
    connectors["whatsapp"]["group_policy"] = "open"

    import yaml

    result = manager.validate_named_text("connectors", yaml.safe_dump(connectors, sort_keys=False))
    assert result["ok"] is True
    assert result["parsed"]["whatsapp"]["transport"] == "local_session"


def test_connector_validation_strips_legacy_qq_mode_fields(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["mode"] = "callback"
    connectors["qq"]["public_callback_url"] = "https://public.example.com/api/connectors/qq/callback"
    connectors["qq"]["app_id"] = "qq-app-id"
    connectors["qq"]["app_secret"] = "qq-app-secret"

    import yaml

    result = manager.validate_named_text("connectors", yaml.safe_dump(connectors, sort_keys=False))
    assert result["ok"] is True
    normalized = result["parsed"]["qq"]
    assert "mode" not in normalized
    assert "public_callback_url" not in normalized
    assert normalized["transport"] == "gateway_direct"


def test_connector_validation_accepts_qq_direct_without_callback_url(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["app_id"] = "qq-app-id"
    connectors["qq"]["app_secret"] = "qq-app-secret"
    connectors["qq"]["public_callback_url"] = None

    import yaml

    result = manager.validate_named_text("connectors", yaml.safe_dump(connectors, sort_keys=False))
    assert result["ok"] is True
    assert not any("public_callback_url" in item for item in result["warnings"])


def test_connector_validation_rejects_qq_direct_without_credentials(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["app_id"] = ""
    connectors["qq"]["app_secret"] = None
    connectors["qq"]["app_secret_env"] = ""

    import yaml

    result = manager.validate_named_text("connectors", yaml.safe_dump(connectors, sort_keys=False))
    assert result["ok"] is False
    assert any("qq: requires `app_id`" in item for item in result["errors"])
    assert any("qq: requires `app_secret`" in item for item in result["errors"])


def test_generic_connector_enforces_dm_allowlist(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["whatsapp"]["enabled"] = True
    connectors["whatsapp"]["transport"] = "local_session"
    connectors["whatsapp"]["dm_policy"] = "allowlist"
    connectors["whatsapp"]["allow_from"] = ["+15550001111"]
    write_yaml(manager.path_for("connectors"), connectors)

    QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("guarded whatsapp connector quest")
    app = DaemonApp(temp_home)

    blocked = app.handle_connector_inbound(
        "whatsapp",
        {
            "chat_type": "direct",
            "sender_id": "+15550002222",
            "sender_name": "Unlisted User",
            "text": "Please continue the experiment.",
        },
    )
    assert blocked["accepted"] is False
    assert blocked["normalized"]["reason"] == "direct_sender_not_allowlisted"

    allowed = app.handle_connector_inbound(
        "whatsapp",
        {
            "chat_type": "direct",
            "sender_id": "+15550001111",
            "sender_name": "Lead Researcher",
            "text": "Please continue the experiment.",
        },
    )
    assert allowed["accepted"] is True
