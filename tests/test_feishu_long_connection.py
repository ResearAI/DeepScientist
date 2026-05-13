from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from pathlib import Path

from deepscientist.channels.feishu_long_connection import FeishuLongConnectionService
from deepscientist.config import ConfigManager
from deepscientist.daemon.app import DaemonApp
from deepscientist.home import ensure_home_layout
from deepscientist.shared import read_json, write_yaml


def test_feishu_sdk_bundle_installs_thread_loop_proxy(monkeypatch) -> None:
    client_module = SimpleNamespace(loop=object(), Client=object)
    enum_module = SimpleNamespace(LogLevel=SimpleNamespace(INFO="info"))
    monkeypatch.setitem(sys.modules, "lark_oapi.ws.client", client_module)
    monkeypatch.setitem(sys.modules, "lark_oapi.core.enum", enum_module)

    bundle = FeishuLongConnectionService._sdk_bundle()

    assert bundle is not None
    assert bundle["client_module"] is client_module
    assert client_module.loop.__class__.__name__ == "_ThreadLoopProxy"
    assert hasattr(client_module.loop, "create_task")


def test_feishu_long_connection_reports_missing_sdk_dependency(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    config = manager.load_named("config")
    config["connectors"]["system_enabled"]["feishu"] = True
    write_yaml(manager.path_for("config"), config)
    connectors = manager.load_named("connectors")
    connectors["feishu"]["enabled"] = True
    connectors["feishu"]["transport"] = "long_connection"
    connectors["feishu"]["app_id"] = "cli_xxx"
    connectors["feishu"]["app_secret"] = "secret"
    write_yaml(manager.path_for("connectors"), connectors)

    monkeypatch.setattr(FeishuLongConnectionService, "_sdk_bundle", staticmethod(lambda: None))
    service = FeishuLongConnectionService(home=temp_home, config=connectors["feishu"], on_event=lambda _event: None)

    started = service.start()

    assert started is False
    runtime_state = read_json(temp_home / "logs" / "connectors" / "feishu" / "runtime.json", {})
    assert runtime_state["connection_state"] == "needs_dependency"
    assert runtime_state["auth_state"] == "missing_dependency"


def test_feishu_long_connection_payload_routes_via_existing_parser(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    config = manager.load_named("config")
    config["connectors"]["system_enabled"]["feishu"] = True
    write_yaml(manager.path_for("config"), config)
    connectors = manager.load_named("connectors")
    connectors["feishu"]["enabled"] = True
    connectors["feishu"]["transport"] = "long_connection"
    connectors["feishu"]["app_id"] = "cli_xxx"
    connectors["feishu"]["app_secret"] = "secret"
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)

    def on_event(event: dict) -> None:
        app.handle_connector_inbound("feishu", event)

    service = FeishuLongConnectionService(home=temp_home, config=connectors["feishu"], on_event=on_event)
    service._write_state(enabled=True, transport="long_connection")
    service._handle_sdk_payload(
        json.dumps(
            {
                "event": {
                    "sender": {
                        "sender_type": "user",
                        "sender_id": {"open_id": "ou_123"},
                    },
                    "message": {
                        "message_id": "om_123",
                        "chat_id": "oc_123",
                        "chat_type": "p2p",
                        "content": json.dumps({"text": "/help"}, ensure_ascii=False),
                    },
                }
            },
            ensure_ascii=False,
        ).encode("utf-8")
    )

    runtime_state = read_json(temp_home / "logs" / "connectors" / "feishu" / "runtime.json", {})
    assert runtime_state["connection_state"] == "connected"
    assert runtime_state["last_conversation_id"] == "feishu:direct:oc_123"

    connector_statuses = {item["name"]: item for item in app.handlers.connectors()}
    feishu_status = connector_statuses["feishu"]
    assert feishu_status["transport"] == "long_connection"
    assert feishu_status["connection_state"] == "connected"
    assert feishu_status["last_conversation_id"] == "feishu:direct:oc_123"
