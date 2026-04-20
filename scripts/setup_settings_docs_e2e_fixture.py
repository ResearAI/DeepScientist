from __future__ import annotations

import argparse
import json
from pathlib import Path

from deepscientist.config import ConfigManager
from deepscientist.shared import write_yaml
from setup_admin_e2e_fixture import build_fixture as build_admin_fixture


def build_fixture(home: Path) -> dict[str, object]:
    fixture = build_admin_fixture(home)
    manager = ConfigManager(home)

    config = manager.load_named("config")
    config["default_locale"] = "en-US"
    connectors_meta = config.get("connectors") if isinstance(config.get("connectors"), dict) else {}
    system_enabled = {
        "qq": True,
        "weixin": True,
        "telegram": True,
        "discord": True,
        "slack": True,
        "feishu": True,
        "whatsapp": True,
        "lingzhu": True,
    }
    config["connectors"] = {
        **connectors_meta,
        "system_enabled": system_enabled,
    }
    write_yaml(manager.path_for("config"), config)

    connectors = manager.load_named("connectors")
    for connector_name in system_enabled:
        connector_payload = connectors.get(connector_name)
        if not isinstance(connector_payload, dict):
            connector_payload = {}
        connector_payload["enabled"] = False
        if connector_name == "qq":
            connector_payload.setdefault("app_id", "docs-qq-app")
            connector_payload.setdefault("app_secret", "docs-qq-secret")
        elif connector_name == "weixin":
            connector_payload.setdefault("bot_token", "docs-wechat-token")
            connector_payload.setdefault("account_id", "wx-docs-account")
            connector_payload.setdefault("login_user_id", "wx-docs-user")
        elif connector_name == "telegram":
            connector_payload.setdefault("bot_token", "123456:docs-telegram-token")
        elif connector_name == "discord":
            connector_payload.setdefault("bot_token", "docs-discord-token")
            connector_payload.setdefault("application_id", "123456789012345678")
        elif connector_name == "slack":
            connector_payload.setdefault("bot_token", "xoxb-docs-slack-token")
            connector_payload.setdefault("app_token", "xapp-docs-slack-token")
        elif connector_name == "feishu":
            connector_payload.setdefault("app_id", "cli_docs_feishu")
            connector_payload.setdefault("app_secret", "docs-feishu-secret")
        elif connector_name == "whatsapp":
            connector_payload.setdefault("session_dir", str(home / "runtime" / "docs-whatsapp-session"))
        elif connector_name == "lingzhu":
            connector_payload.setdefault("auth_ak", "docs-lingzhu-ak")
            connector_payload.setdefault("public_base_url", "https://docs.example.com")
        connectors[connector_name] = connector_payload

    write_yaml(manager.path_for("connectors"), connectors)
    return fixture


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an isolated settings docs E2E fixture runtime.")
    parser.add_argument("--home", required=True, help="DeepScientist home for the temporary docs runtime.")
    parser.add_argument("--output", required=True, help="Path to write fixture JSON.")
    args = parser.parse_args()

    home = Path(args.home).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    fixture = build_fixture(home)
    output.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(fixture, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
