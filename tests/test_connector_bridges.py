from __future__ import annotations

import json
from pathlib import Path

from deepscientist.bridges.base import BaseConnectorBridge
from deepscientist.bridges.connectors import QQConnectorBridge
from deepscientist.config import ConfigManager
from deepscientist.daemon.app import DaemonApp
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.shared import write_yaml
from deepscientist.skills import SkillInstaller
from deepscientist.quest import QuestService


def test_base_connector_bridge_render_text_ignores_machine_metadata_attachments() -> None:
    rendered = BaseConnectorBridge.render_text(
        "Assistant reply.",
        [
            {
                "kind": "runner_result",
                "run_id": "run-123",
                "history_root": "/tmp/history",
            }
        ],
    )

    assert rendered == "Assistant reply."


def test_base_connector_bridge_render_text_keeps_human_visible_attachment_paths() -> None:
    rendered = BaseConnectorBridge.render_text(
        "Graph refreshed.",
        [
            {"kind": "path", "path": "/tmp/graph.svg"},
            {"kind": "link", "url": "https://example.com/report"},
        ],
    )

    assert "Attachments:" in rendered
    assert "/tmp/graph.svg" in rendered
    assert "https://example.com/report" in rendered


class _FakeResponse:
    def __init__(self, payload: str, status: int = 200) -> None:
        self._payload = payload.encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _setup_app(temp_home: Path, *, connector_name: str, extra: dict | None = None) -> tuple[DaemonApp, str]:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors[connector_name]["enabled"] = True
    connectors[connector_name]["auto_bind_dm_to_active_quest"] = True
    if extra:
        connectors[connector_name].update(extra)
    write_yaml(manager.path_for("connectors"), connectors)
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create(f"{connector_name} bridge quest")
    return DaemonApp(temp_home), quest["quest_id"]


def test_bridge_direct_outbound_telegram(monkeypatch, temp_home: Path) -> None:
    app, _quest_id = _setup_app(
        temp_home,
        connector_name="telegram",
        extra={"bot_token": "telegram-token"},
    )

    captured: list[tuple[str, dict, str]] = []

    def fake_urlopen(request, timeout=8):  # noqa: ANN001
        body = json.loads(request.data.decode("utf-8"))
        captured.append((request.full_url, dict(request.header_items()), body.get("text") if isinstance(body.get("text"), str) else json.dumps(body.get("text", {}), ensure_ascii=False)))
        return _FakeResponse('{"ok":true}', status=200)

    monkeypatch.setattr("deepscientist.bridges.connectors.urlopen", fake_urlopen)

    telegram_result = app.channels["telegram"].send(
        {
            "conversation_id": "telegram:direct:1001",
            "message": "Bridge outbound hello",
        }
    )
    assert telegram_result["delivery"]["transport"] == "telegram-http"
    assert any(url.startswith("https://api.telegram.org/bottelegram-token/sendMessage") for url, _headers, _body in captured)


def test_bridge_direct_outbound_qq_uses_openid_and_group_openid(monkeypatch, temp_home: Path) -> None:
    QQConnectorBridge._token_cache = {}
    _app, _quest_id = _setup_app(
        temp_home,
        connector_name="qq",
        extra={"app_id": "1903299925", "app_secret": "qq-secret"},
    )
    app = DaemonApp(temp_home)

    captured: list[tuple[str, dict, dict]] = []

    def fake_urlopen(request, timeout=8):  # noqa: ANN001
        body = json.loads(request.data.decode("utf-8")) if request.data else {}
        captured.append((request.full_url, dict(request.header_items()), body))
        if request.full_url == "https://bots.qq.com/app/getAppAccessToken":
            return _FakeResponse('{"access_token":"qq-access-token","expires_in":7200}', status=200)
        return _FakeResponse('{"id":"msg-1","timestamp":"1741440000"}', status=200)

    monkeypatch.setattr("deepscientist.bridges.connectors.urlopen", fake_urlopen)

    direct_result = app.channels["qq"].send(
        {
            "conversation_id": "qq:direct:user-openid-1",
            "message": "QQ direct hello",
        }
    )
    group_result = app.channels["qq"].send(
        {
            "conversation_id": "qq:group:group-openid-1",
            "message": "QQ group hello",
        }
    )

    assert direct_result["delivery"]["transport"] == "qq-http"
    assert group_result["delivery"]["transport"] == "qq-http"
    assert sum(1 for url, _headers, _body in captured if url == "https://bots.qq.com/app/getAppAccessToken") == 1
    assert any(url.endswith("/v2/users/user-openid-1/messages") for url, _headers, _body in captured)
    assert any(url.endswith("/v2/groups/group-openid-1/messages") for url, _headers, _body in captured)
    send_headers = [headers for url, headers, _body in captured if url.startswith("https://api.sgroup.qq.com/v2/")]
    assert send_headers
    assert all(headers.get("Authorization") == "QQBot qq-access-token" for headers in send_headers)


def test_bridge_direct_outbound_qq_supports_markdown_mode(monkeypatch, temp_home: Path) -> None:
    QQConnectorBridge._token_cache = {}
    _app, _quest_id = _setup_app(
        temp_home,
        connector_name="qq",
        extra={
            "app_id": "1903299925",
            "app_secret": "qq-secret",
            "enable_markdown_send": True,
        },
    )
    app = DaemonApp(temp_home)

    captured: list[tuple[str, dict, dict]] = []

    def fake_urlopen(request, timeout=8):  # noqa: ANN001
        body = json.loads(request.data.decode("utf-8")) if request.data else {}
        captured.append((request.full_url, dict(request.header_items()), body))
        if request.full_url == "https://bots.qq.com/app/getAppAccessToken":
            return _FakeResponse('{"access_token":"qq-access-token","expires_in":7200}', status=200)
        return _FakeResponse('{"id":"msg-markdown","timestamp":"1741440001"}', status=200)

    monkeypatch.setattr("deepscientist.bridges.connectors.urlopen", fake_urlopen)

    result = app.channels["qq"].send(
        {
            "conversation_id": "qq:direct:user-openid-2",
            "message": "## Title\n- item",
            "connector_hints": {"qq": {"render_mode": "markdown"}},
        }
    )

    assert result["delivery"]["ok"] is True
    markdown_requests = [
        body
        for url, _headers, body in captured
        if url.endswith("/v2/users/user-openid-2/messages")
    ]
    assert markdown_requests
    assert markdown_requests[-1]["msg_type"] == 2
    assert markdown_requests[-1]["markdown"]["content"] == "## Title\n- item"


def test_bridge_direct_outbound_qq_supports_image_and_file_upload(monkeypatch, temp_home: Path) -> None:
    QQConnectorBridge._token_cache = {}
    _app, _quest_id = _setup_app(
        temp_home,
        connector_name="qq",
        extra={
            "app_id": "1903299925",
            "app_secret": "qq-secret",
            "enable_file_upload_experimental": True,
        },
    )
    app = DaemonApp(temp_home)

    image_path = temp_home / "image.png"
    file_path = temp_home / "report.pdf"
    image_path.write_bytes(b"png-data")
    file_path.write_bytes(b"%PDF-1.7")

    captured: list[tuple[str, dict, dict]] = []

    def fake_urlopen(request, timeout=8):  # noqa: ANN001
        body = json.loads(request.data.decode("utf-8")) if request.data else {}
        captured.append((request.full_url, dict(request.header_items()), body))
        if request.full_url == "https://bots.qq.com/app/getAppAccessToken":
            return _FakeResponse('{"access_token":"qq-access-token","expires_in":7200}', status=200)
        if request.full_url.endswith("/files"):
            return _FakeResponse('{"file_info":"FILE_INFO_123","ttl":3600}', status=200)
        return _FakeResponse('{"id":"msg-media","timestamp":"1741440002"}', status=200)

    monkeypatch.setattr("deepscientist.bridges.connectors.urlopen", fake_urlopen)

    image_result = app.channels["qq"].send(
        {
            "conversation_id": "qq:direct:user-openid-3",
            "message": "Image upload test",
            "attachments": [
                {
                    "kind": "path",
                    "path": str(image_path),
                    "content_type": "image/png",
                    "connector_delivery": {"qq": {"media_kind": "image"}},
                }
            ],
        }
    )
    file_result = app.channels["qq"].send(
        {
            "conversation_id": "qq:direct:user-openid-4",
            "message": "File upload test",
            "attachments": [
                {
                    "kind": "path",
                    "path": str(file_path),
                    "content_type": "application/pdf",
                    "connector_delivery": {"qq": {"media_kind": "file"}},
                }
            ],
        }
    )

    assert image_result["delivery"]["ok"] is True
    assert file_result["delivery"]["ok"] is True
    image_uploads = [body for url, _headers, body in captured if url.endswith("/v2/users/user-openid-3/files")]
    file_uploads = [body for url, _headers, body in captured if url.endswith("/v2/users/user-openid-4/files")]
    image_media_messages = [body for url, _headers, body in captured if url.endswith("/v2/users/user-openid-3/messages")]
    file_media_messages = [body for url, _headers, body in captured if url.endswith("/v2/users/user-openid-4/messages")]
    assert image_uploads and file_uploads
    assert image_uploads[-1]["file_type"] == 1
    assert file_uploads[-1]["file_type"] == 4
    assert file_uploads[-1]["file_name"] == "report.pdf"
    assert any(body.get("msg_type") == 7 for body in image_media_messages)
    assert any(body.get("msg_type") == 7 for body in file_media_messages)


def test_qq_channel_auto_uses_recent_inbound_message_as_reply_target(monkeypatch, temp_home: Path) -> None:
    QQConnectorBridge._token_cache = {}
    _app, _quest_id = _setup_app(
        temp_home,
        connector_name="qq",
        extra={"app_id": "1903299925", "app_secret": "qq-secret"},
    )
    app = DaemonApp(temp_home)

    app.channels["qq"].ingest(
        {
            "chat_type": "direct",
            "sender_id": "user-openid-5",
            "sender_name": "Tester",
            "message_id": "inbound-msg-5",
            "text": "Hello from QQ",
        }
    )

    captured: list[tuple[str, dict, dict]] = []

    def fake_urlopen(request, timeout=8):  # noqa: ANN001
        body = json.loads(request.data.decode("utf-8")) if request.data else {}
        captured.append((request.full_url, dict(request.header_items()), body))
        if request.full_url == "https://bots.qq.com/app/getAppAccessToken":
            return _FakeResponse('{"access_token":"qq-access-token","expires_in":7200}', status=200)
        return _FakeResponse('{"id":"msg-reply","timestamp":"1741440003"}', status=200)

    monkeypatch.setattr("deepscientist.bridges.connectors.urlopen", fake_urlopen)

    result = app.channels["qq"].send(
        {
            "conversation_id": "qq:direct:user-openid-5",
            "message": "Reply target test",
        }
    )

    assert result["delivery"]["ok"] is True
    message_requests = [body for url, _headers, body in captured if url.endswith("/v2/users/user-openid-5/messages")]
    assert message_requests
    assert message_requests[-1]["msg_id"] == "inbound-msg-5"
