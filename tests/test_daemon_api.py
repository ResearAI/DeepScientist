from __future__ import annotations

import base64
from http.cookiejar import CookieJar
import io
import json
import os
import socket
import shutil
import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

import pytest
from websockets.sync.client import connect as websocket_connect

from deepscientist.artifact import ArtifactService
from deepscientist.config import ConfigManager
from deepscientist.connector.connector_profiles import list_connector_profiles
from deepscientist.connector_runtime import format_conversation_id
from deepscientist.daemon.api import handlers as daemon_api_handlers
from deepscientist.daemon.api.router import match_route
from deepscientist.daemon.app import DaemonApp, _STALLED_RUNNING_TURN_INACTIVITY_SECONDS
from deepscientist.prompts.builder import classify_turn_intent
from deepscientist.home import ensure_home_layout
from deepscientist.connector.lingzhu_support import generate_lingzhu_auth_ak, lingzhu_passive_conversation_id
from deepscientist.mcp.context import McpContext
from deepscientist.connector.qq_profiles import list_qq_profiles
from deepscientist.runners import RunResult
from deepscientist.shared import append_jsonl, ensure_dir, generate_id, read_json, read_jsonl, read_yaml, utc_now, write_json, write_yaml


def _get_json(url: str):
    with urlopen(url) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _open_json_with_opener(opener, request):  # noqa: ANN001
    with opener.open(request) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _wait_for_http_ready(url: str, *, timeout_seconds: float = 5.0) -> int:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url) as response:  # noqa: S310
                return int(response.status)
        except HTTPError as exc:
            return int(exc.code)
        except URLError:
            time.sleep(0.05)
    raise AssertionError(url)


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _FakeSseHandler:
    def __init__(self) -> None:
        self.status_code: int | None = None
        self.headers: dict[str, str] = {}
        self.wfile = io.BytesIO()
        self.close_connection = False

    def send_response(self, code: int) -> None:
        self.status_code = code

    def send_header(self, key: str, value: str) -> None:
        self.headers[key] = value

    def end_headers(self) -> None:
        return


class _BrokenPipeWriter:
    def write(self, _payload: bytes) -> None:
        raise BrokenPipeError(32, "Broken pipe")


class _BrokenPipeHandler(_FakeSseHandler):
    def __init__(self) -> None:
        super().__init__()
        self.wfile = _BrokenPipeWriter()


class _ClosableCaptureWriter:
    def __init__(self) -> None:
        self.buffer = io.BytesIO()
        self.closed = False

    def write(self, payload: bytes) -> int:
        if self.closed:
            raise BrokenPipeError(32, "closed")
        return self.buffer.write(payload)

    def flush(self) -> None:
        return

    def close_stream(self) -> None:
        self.closed = True

    def getvalue(self) -> bytes:
        return self.buffer.getvalue()


class _ClosableSseHandler(_FakeSseHandler):
    def __init__(self) -> None:
        super().__init__()
        self.wfile = _ClosableCaptureWriter()


def _parse_sse_events(raw: bytes) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for block in raw.decode("utf-8").split("\n\n"):
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if lines[0].startswith(":"):
            continue
        event_name = ""
        data_lines: list[str] = []
        for line in lines:
            if line.startswith("event: "):
                event_name = line[len("event: ") :].strip()
            elif line.startswith("data: "):
                data_lines.append(line[len("data: ") :])
        if not event_name or not data_lines:
            continue
        events.append(
            {
                "event": event_name,
                "data": json.loads("".join(data_lines)),
            }
        )
    return events


class _FakeHeaders:
    def __init__(self, charset: str = "utf-8") -> None:
        self._charset = charset

    def get_content_charset(self) -> str:
        return self._charset


class _FakeUrlopenResponse:
    def __init__(self, body: str, *, charset: str = "utf-8") -> None:
        self._body = body.encode(charset)
        self.headers = _FakeHeaders(charset)

    def __enter__(self) -> "_FakeUrlopenResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def test_daemon_browser_auth_query_token_bootstraps_cookie_session(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=True, browser_auth_token="0123456789abcdef")
    app._start_background_connectors = lambda: None  # type: ignore[method-assign]
    app._stop_background_connectors = lambda: None  # type: ignore[method-assign]
    app._start_terminal_attach_server = lambda host, port: None  # type: ignore[method-assign]
    app._stop_terminal_attach_server = lambda: None  # type: ignore[method-assign]

    port = _pick_free_port()
    base_url = f"http://127.0.0.1:{port}"
    server_thread = threading.Thread(target=app.serve, args=("127.0.0.1", port), daemon=True)
    server_thread.start()
    try:
        _wait_for_http_ready(f"{base_url}/")
        with pytest.raises(HTTPError) as exc_info:
            urlopen(f"{base_url}/api/health")  # noqa: S310
        assert exc_info.value.code == 401

        cookie_jar = CookieJar()
        opener = build_opener(HTTPCookieProcessor(cookie_jar))
        with opener.open(f"{base_url}/?token=0123456789abcdef") as response:  # noqa: S310
            html = response.read().decode("utf-8")
        assert "DeepScientist UI bundle is not built yet" in html or "window.__DEEPSCIENTIST_RUNTIME__" in html
        assert any(cookie.name == "ds_local_auth" for cookie in cookie_jar)

        health = _open_json_with_opener(opener, f"{base_url}/api/health")
        assert health["status"] == "ok"
        assert health["auth_enabled"] is True

        token_payload = _open_json_with_opener(opener, f"{base_url}/api/auth/token")
        assert token_payload["token"] == "0123456789abcdef"
        assert token_payload["auth_enabled"] is True
    finally:
        app.request_shutdown(source="test-browser-auth-query-token")
        server_thread.join(timeout=10)
        assert not server_thread.is_alive()


def test_daemon_browser_auth_login_route_sets_cookie_for_subsequent_api_calls(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=True, browser_auth_token="fedcba9876543210")
    app._start_background_connectors = lambda: None  # type: ignore[method-assign]
    app._stop_background_connectors = lambda: None  # type: ignore[method-assign]
    app._start_terminal_attach_server = lambda host, port: None  # type: ignore[method-assign]
    app._stop_terminal_attach_server = lambda: None  # type: ignore[method-assign]
    created = app.quest_service.create("browser auth login quest")

    port = _pick_free_port()
    base_url = f"http://127.0.0.1:{port}"
    server_thread = threading.Thread(target=app.serve, args=("127.0.0.1", port), daemon=True)
    server_thread.start()
    try:
        _wait_for_http_ready(f"{base_url}/")
        with pytest.raises(HTTPError) as exc_info:
            urlopen(f"{base_url}/api/quests")  # noqa: S310
        assert exc_info.value.code == 401

        cookie_jar = CookieJar()
        opener = build_opener(HTTPCookieProcessor(cookie_jar))
        login_request = Request(
            f"{base_url}/api/auth/login",
            data=json.dumps({"token": "fedcba9876543210"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        login_payload = _open_json_with_opener(opener, login_request)
        assert login_payload["ok"] is True
        assert login_payload["authenticated"] is True
        assert any(cookie.name == "ds_local_auth" for cookie in cookie_jar)

        quests = _open_json_with_opener(opener, f"{base_url}/api/quests")
        assert any(item["quest_id"] == created["quest_id"] for item in quests)
    finally:
        app.request_shutdown(source="test-browser-auth-login")
        server_thread.join(timeout=10)
        assert not server_thread.is_alive()


def test_stream_quest_events_emits_acp_update_for_new_message(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=False)
    app._start_background_connectors = lambda: None  # type: ignore[method-assign]
    app._stop_background_connectors = lambda: None  # type: ignore[method-assign]
    app._start_terminal_attach_server = lambda host, port: None  # type: ignore[method-assign]
    app._stop_terminal_attach_server = lambda: None  # type: ignore[method-assign]
    quest = app.quest_service.create("stream quest events quest")
    quest_id = quest["quest_id"]

    seed_payload = app.handlers.quest_events(
        quest_id,
        path=f"/api/quests/{quest_id}/events?format=raw&limit=1&tail=1",
    )
    after = int(seed_payload.get("cursor") or 0)
    handler = _ClosableSseHandler()
    thread = threading.Thread(
        target=app.stream_quest_events,
        args=(handler,),
        kwargs={
            "quest_id": quest_id,
            "path": f"/api/quests/{quest_id}/events?after={after}&format=acp&session_id=quest:{quest_id}&stream=1",
        },
        daemon=True,
    )
    thread.start()
    time.sleep(0.2)
    app.quest_service.append_message(
        quest_id,
        role="user",
        content="stream test message",
        source="web-react",
        client_message_id="stream-test-001",
    )
    deadline = time.time() + 5.0
    raw_payload = b""
    while time.time() < deadline:
        raw_payload = handler.wfile.getvalue()
        if b"event: acp_update" in raw_payload:
            break
        time.sleep(0.05)
    handler.wfile.close_stream()
    thread.join(timeout=2)

    parsed = _parse_sse_events(raw_payload)
    assert any(item["event"] == "acp_update" for item in parsed)
    acp_updates = [item["data"] for item in parsed if item["event"] == "acp_update"]
    assert any(
        ((update.get("params") or {}).get("update") or {}).get("kind") == "message"
        and (((update.get("params") or {}).get("update") or {}).get("message") or {}).get("content") == "stream test message"
        for update in acp_updates
    )


def test_daemon_browser_auth_rotate_invalidates_previous_token_and_refreshes_cookie(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=True, browser_auth_token="1111222233334444")
    app._start_background_connectors = lambda: None  # type: ignore[method-assign]
    app._stop_background_connectors = lambda: None  # type: ignore[method-assign]
    app._start_terminal_attach_server = lambda host, port: None  # type: ignore[method-assign]
    app._stop_terminal_attach_server = lambda: None  # type: ignore[method-assign]

    port = _pick_free_port()
    base_url = f"http://127.0.0.1:{port}"
    server_thread = threading.Thread(target=app.serve, args=("127.0.0.1", port), daemon=True)
    server_thread.start()
    try:
        _wait_for_http_ready(f"{base_url}/")
        cookie_jar = CookieJar()
        opener = build_opener(HTTPCookieProcessor(cookie_jar))
        rotate_request = Request(
            f"{base_url}/api/auth/rotate",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer 1111222233334444",
            },
            method="POST",
        )
        rotate_payload = _open_json_with_opener(opener, rotate_request)
        rotated_token = str(rotate_payload["token"])
        assert rotate_payload["ok"] is True
        assert rotate_payload["rotated"] is True
        assert rotated_token != "1111222233334444"
        assert any(cookie.name == "ds_local_auth" and cookie.value == rotated_token for cookie in cookie_jar)

        with pytest.raises(HTTPError) as exc_info:
            urlopen(Request(f"{base_url}/api/health", headers={"Authorization": "Bearer 1111222233334444"}))  # noqa: S310
        assert exc_info.value.code == 401

        health_with_cookie = _open_json_with_opener(opener, f"{base_url}/api/health")
        assert health_with_cookie["status"] == "ok"

        with urlopen(Request(f"{base_url}/api/health", headers={"Authorization": f"Bearer {rotated_token}"})) as response:  # noqa: S310
            health_with_rotated_token = json.loads(response.read().decode("utf-8"))
        assert health_with_rotated_token["status"] == "ok"
    finally:
        app.request_shutdown(source="test-browser-auth-rotate")
        server_thread.join(timeout=10)
        assert not server_thread.is_alive()


def test_daemon_defaults_browser_auth_to_false(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)

    assert app.browser_auth_enabled is False
    assert app.browser_auth_token is None


def test_write_handler_response_swallows_client_disconnects(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=False)
    handler = _BrokenPipeHandler()

    written = app._write_handler_response(
        handler,
        code=200,
        content=b'{"ok":true}',
        content_type="application/json; charset=utf-8",
    )

    assert written is False
    assert handler.status_code == 200
    assert handler.close_connection is True


def test_handlers_quest_layout_roundtrip(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=False)
    quest = app.quest_service.create("layout roundtrip quest")
    quest_id = quest["quest_id"]

    initial = app.handlers.quest_layout(quest_id)
    assert initial["layout_json"]["branch"] == {}
    assert initial["layout_json"]["preferences"] == {}

    updated = app.handlers.quest_layout_update(
        quest_id,
        {
            "layout_json": {
                "branch": {"main": {"x": 120, "y": 80}},
                "preferences": {
                    "curveMode": "full",
                    "nodeDisplayMode": "metric",
                    "showAnalysis": True,
                    "pathFilterMode": "current",
                },
            }
        },
    )
    assert updated["layout_json"]["branch"]["main"] == {"x": 120, "y": 80}
    assert updated["layout_json"]["preferences"]["pathFilterMode"] == "current"

    refreshed = app.handlers.quest_layout(quest_id)
    assert refreshed["layout_json"]["branch"]["main"] == {"x": 120, "y": 80}
    assert refreshed["layout_json"]["preferences"]["curveMode"] == "full"


@pytest.mark.parametrize(
    ("relative_path", "expected_mime", "content"),
    [
        ("paper/figures/generated/figure2.svg", "image/svg+xml", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"),
        ("paper/figures/generated/figure2.png", "image/png", b"\x89PNG\r\n\x1a\nworktree-preview"),
        ("paper/figures/generated/figure2.pdf", "application/pdf", b"%PDF-1.4\nworktree-preview"),
    ],
)
def test_document_asset_resolves_path_documents_from_active_worktree(
    temp_home: Path,
    relative_path: str,
    expected_mime: str,
    content: bytes,
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("worktree binary preview quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    worktree_root = quest_root / ".ds" / "worktrees" / "analysis-branch-001"
    asset_path = worktree_root / relative_path
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(content)
    (worktree_root / "brief.md").write_text("# Worktree brief\n", encoding="utf-8")
    app.quest_service.update_research_state(
        quest_root,
        current_workspace_root=str(worktree_root),
        research_head_worktree_root=str(worktree_root),
    )

    opened = app.handlers.document_open(quest_id, {"document_id": f"path::{relative_path}"})

    assert opened["path"] == str(asset_path)

    status, headers, body = app.handlers.document_asset(quest_id, opened["asset_url"])

    assert status == 200
    assert headers["Content-Type"] == expected_mime
    assert body == content


def test_handlers_workflow_includes_optimization_frontier_when_available(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=False)
    quest = app.quest_service.create(
        "workflow frontier quest",
        startup_contract={"need_research_paper": False},
    )
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    baseline_root = quest_root / "baselines" / "local" / "workflow-frontier-baseline"
    baseline_root.mkdir(parents=True, exist_ok=True)
    write_json(
        baseline_root / "RESULT.json",
        {
            "metrics_summary": {"acc": 0.81},
            "metric_contract": {
                "primary_metric_id": "acc",
                "metrics": [{"metric_id": "acc", "direction": "maximize", "required": True}],
            },
            "primary_metric": {"metric_id": "acc", "value": 0.81, "direction": "maximize"},
        },
    )
    app.artifact_service.confirm_baseline(
        quest_root,
        baseline_path="baselines/local/workflow-frontier-baseline",
        baseline_id="workflow-frontier-baseline",
        summary="Workflow frontier baseline",
    )
    app.artifact_service.submit_idea(
        quest_root,
        mode="create",
        submission_mode="candidate",
        title="Workflow candidate",
        problem="Need a branchless optimization brief.",
        hypothesis="A candidate brief should surface in workflow.",
        mechanism="Delay promotion until ranking is finished.",
        decision_reason="Keep the brief in the frontier.",
        next_target="optimize",
    )

    workflow = _wait_for_projection_ready(lambda: app.handlers.workflow(quest_id))
    assert workflow["optimization_frontier"]["mode"] in {"explore", "exploit", "fusion", "stop"}
    assert workflow["optimization_frontier"]["candidate_backlog"]["candidate_brief_count"] == 1


def test_classify_turn_intent_prefers_continue_stage_for_structured_bootstrap() -> None:
    message = """
Project Bootstrap
- Project title: AMD

Primary Research Request
Please optimize the current system.

Research Goals
- Improve the result.

Research Contract
- What matters most is reaching rank 1.

Mandatory Working Rules
- Keep progressing automatically.
""".strip()

    assert classify_turn_intent(message) == "continue_stage"


def test_turn_skill_for_rejects_experiment_without_durable_idea_in_algorithm_first() -> None:
    snapshot = {
        "active_anchor": "experiment",
        "baseline_gate": "confirmed",
        "active_idea_id": None,
        "startup_contract": {
            "need_research_paper": False,
        },
    }

    assert DaemonApp._turn_skill_for(snapshot, None, turn_reason="auto_continue", turn_mode="stage_execution") == "optimize"


def test_turn_skill_for_rejects_experiment_without_durable_idea_in_paper_mode() -> None:
    snapshot = {
        "active_anchor": "experiment",
        "baseline_gate": "confirmed",
        "active_idea_id": None,
        "startup_contract": {
            "need_research_paper": True,
        },
    }

    assert DaemonApp._turn_skill_for(snapshot, None, turn_reason="auto_continue", turn_mode="stage_execution") == "idea"


def test_turn_skill_for_copilot_direct_question_does_not_default_to_decision() -> None:
    snapshot = {
        "workspace_mode": "copilot",
        "active_anchor": "scout",
        "continuation_anchor": "decision",
        "baseline_gate": "pending",
        "startup_contract": {
            "workspace_mode": "copilot",
        },
    }
    latest_user_message = {
        "role": "user",
        "content": "Can you inspect this repo and tell me what changed?",
        "source": "web-react",
    }

    assert (
        DaemonApp._turn_skill_for(
            snapshot,
            latest_user_message,
            turn_reason="user_message",
            turn_mode="answering",
        )
        == "scout"
    )


def test_turn_skill_for_copilot_direct_command_does_not_default_to_decision() -> None:
    snapshot = {
        "workspace_mode": "copilot",
        "active_anchor": "scout",
        "continuation_anchor": "decision",
        "baseline_gate": "pending",
        "startup_contract": {
            "workspace_mode": "copilot",
        },
    }
    latest_user_message = {
        "role": "user",
        "content": "Please test git in this workspace.",
        "source": "web-react",
    }

    assert (
        DaemonApp._turn_skill_for(
            snapshot,
            latest_user_message,
            turn_reason="user_message",
            turn_mode="command_execution",
        )
        == "scout"
    )


def test_turn_skill_for_legacy_copilot_baseline_anchor_falls_back_to_scout_without_explicit_baseline_context() -> None:
    snapshot = {
        "workspace_mode": "copilot",
        "active_anchor": "baseline",
        "continuation_anchor": "decision",
        "baseline_gate": "pending",
        "startup_contract": {
            "workspace_mode": "copilot",
        },
    }
    latest_user_message = {
        "role": "user",
        "content": "Please inspect this setup agent session.",
        "source": "web-react",
    }

    assert (
        DaemonApp._turn_skill_for(
            snapshot,
            latest_user_message,
            turn_reason="user_message",
            turn_mode="answering",
        )
        == "scout"
    )


def test_turn_skill_for_copilot_explicit_baseline_context_still_allows_baseline() -> None:
    snapshot = {
        "workspace_mode": "copilot",
        "active_anchor": "baseline",
        "continuation_anchor": "decision",
        "baseline_gate": "pending",
        "requested_baseline_ref": {"baseline_id": "baseline-001"},
        "startup_contract": {
            "workspace_mode": "copilot",
        },
    }
    latest_user_message = {
        "role": "user",
        "content": "Please help me inspect the imported baseline before branching.",
        "source": "web-react",
    }

    assert (
        DaemonApp._turn_skill_for(
            snapshot,
            latest_user_message,
            turn_reason="user_message",
            turn_mode="answering",
        )
        == "baseline"
    )


def test_turn_skill_for_autonomous_direct_question_uses_stage_skill_by_default() -> None:
    snapshot = {
        "active_anchor": "baseline",
        "continuation_anchor": "decision",
        "baseline_gate": "pending",
        "startup_contract": {},
    }
    latest_user_message = {
        "role": "user",
        "content": "你是谁？",
        "source": "web-react",
    }

    assert (
        DaemonApp._turn_skill_for(
            snapshot,
            latest_user_message,
            turn_reason="user_message",
            turn_mode="answering",
        )
        == "baseline"
    )


def test_turn_skill_for_autonomous_direct_command_uses_stage_skill_by_default() -> None:
    snapshot = {
        "active_anchor": "baseline",
        "continuation_anchor": "decision",
        "baseline_gate": "pending",
        "startup_contract": {},
    }
    latest_user_message = {
        "role": "user",
        "content": "请帮我检查一下当前 workspace。",
        "source": "web-react",
    }

    assert (
        DaemonApp._turn_skill_for(
            snapshot,
            latest_user_message,
            turn_reason="user_message",
            turn_mode="command_execution",
        )
        == "baseline"
    )


def test_turn_skill_for_blocking_reply_still_routes_to_decision() -> None:
    snapshot = {
        "active_anchor": "baseline",
        "continuation_anchor": "baseline",
        "baseline_gate": "pending",
        "startup_contract": {},
        "active_interactions": [
            {
                "interaction_id": "decision-001",
                "artifact_id": "decision-001",
                "status": "waiting",
                "reply_mode": "blocking",
                "kind": "decision_request",
            }
        ],
    }
    latest_user_message = {
        "role": "user",
        "content": "选 A。",
        "source": "web-react",
        "reply_to_interaction_id": "decision-001",
    }

    assert (
        DaemonApp._turn_skill_for(
            snapshot,
            latest_user_message,
            turn_reason="user_message",
            turn_mode="answering",
        )
        == "decision"
    )


def test_user_turn_prompt_flow_e2e_keeps_warm_style_first_guidance(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    created = app.quest_service.create(
        "warm style prompt flow quest",
        startup_contract={
            "workspace_mode": "copilot",
            "decision_policy": "user_gated",
            "launch_mode": "custom",
            "custom_profile": "freeform",
        },
    )
    snapshot = app.quest_service.snapshot(created["quest_id"])
    latest_user_message = {
        "role": "user",
        "content": "现在情况怎么样？",
        "source": "web-react",
    }

    turn_mode = app._turn_mode_for(snapshot, latest_user_message, turn_reason="user_message")
    skill_id = app._turn_skill_for(
        snapshot,
        latest_user_message,
        turn_reason="user_message",
        turn_mode=turn_mode,
    )
    prompt = app.prompt_builder.build(
        quest_id=created["quest_id"],
        skill_id=skill_id,
        user_message=str(latest_user_message["content"]),
        model="gpt-5.4",
        turn_reason="user_message",
        turn_mode=turn_mode,
    )

    top_block = "\n".join(prompt.splitlines()[:50])
    assert turn_mode == "answering"
    assert skill_id == "scout"
    assert "# DeepScientist Copilot System Prompt" in top_block
    assert "request-scoped help" in top_block
    assert "turn_self_routing_rule" in prompt
    assert "micro_task_stop_rule" in prompt


def _wait_for_json(url: str, *, timeout: float = 10.0) -> dict | list:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            return _get_json(url)
        except (ConnectionError, TimeoutError, URLError, ValueError, HTTPError) as exc:
            last_error = exc
            time.sleep(0.1)
    if last_error is not None:
        raise last_error
    raise TimeoutError(f"Timed out waiting for JSON response from {url}")


def _wait_for_projection_ready(loader, *, timeout: float = 5.0):
    deadline = time.time() + timeout
    last_payload = None
    while time.time() < deadline:
        last_payload = loader()
        state = str(((last_payload or {}).get("projection_status") or {}).get("state") or "").strip().lower()
        if not state or state == "ready":
            return last_payload
        time.sleep(0.05)
    if last_payload is not None:
        return last_payload
    return loader()


def test_workflow_projection_returns_placeholder_then_ready(temp_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=False)
    quest = app.quest_service.create("workflow projection quest")
    quest_id = quest["quest_id"]
    service = app.quest_service

    started = threading.Event()
    release = threading.Event()
    original = service._build_details_projection_payload

    def _blocked_details_builder(*args, **kwargs):
        started.set()
        release.wait(timeout=5.0)
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "_build_details_projection_payload", _blocked_details_builder)

    initial = service.workflow(quest_id)
    initial_state = str(((initial or {}).get("projection_status") or {}).get("state") or "").strip().lower()
    assert initial_state in {"queued", "building", "stale", "missing"}
    assert isinstance(initial.get("changed_files"), list)
    assert started.wait(timeout=2.0)

    release.set()
    ready = _wait_for_projection_ready(lambda: service.workflow(quest_id))
    assert str(((ready or {}).get("projection_status") or {}).get("state") or "").strip().lower() == "ready"
    changed_paths = [str(item.get("path") or "") for item in ready.get("changed_files") or []]
    assert any(path.endswith("/brief.md") for path in changed_paths)


def test_git_commit_canvas_returns_commits_and_projection_status(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=False)
    quest = app.quest_service.create(
        "git canvas quest",
        startup_contract={"workspace_mode": "copilot"},
    )
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    app.quest_service.update_research_state(quest_root, workspace_mode="copilot")
    artifact = ArtifactService(temp_home)

    write_json(quest_root / "artifacts" / "reports" / "git-canvas-report.json", {"ok": True})
    artifact.checkpoint(quest_root, "git canvas first commit")

    write_json(quest_root / "memory" / "notes" / "git-canvas-note.json", {"status": "updated"})
    artifact.checkpoint(quest_root, "git canvas second commit")

    payload = _wait_for_projection_ready(lambda: app.handlers.git_canvas(quest_id))
    assert payload["quest_id"] == quest_id
    assert payload["workspace_mode"] == "copilot"
    assert str(((payload or {}).get("projection_status") or {}).get("state") or "").strip().lower() == "ready"
    assert len(payload["nodes"]) >= 2
    assert payload["nodes"][0]["selection_type"] == "git_commit_node"
    assert payload["nodes"][0]["compare_head"]
    assert any(node["subject"] == "git canvas second commit" for node in payload["nodes"])


def test_quest_session_prewarms_details_and_canvas_projections(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=False)
    quest = app.quest_service.create("session prewarm quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    session = app.handlers.quest_session(quest_id)
    assert session["ok"] is True

    manifest_path = quest_root / ".ds" / "projections" / "manifest.json"
    deadline = time.time() + 5.0
    manifest = {}
    while time.time() < deadline:
        manifest = read_json(manifest_path, {})
        projections = manifest.get("projections") if isinstance(manifest, dict) else {}
        if isinstance(projections, dict) and {"details", "canvas", "git_canvas"}.issubset(projections.keys()):
            break
        time.sleep(0.05)

    projections = manifest.get("projections") if isinstance(manifest, dict) else {}
    assert isinstance(projections, dict)
    assert "details" in projections
    assert "canvas" in projections
    assert "git_canvas" in projections


def test_quest_session_snapshot_preserves_copilot_workspace_mode(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=False)
    quest = app.quest_service.create(
        "copilot session quest",
        startup_contract={"workspace_mode": "copilot"},
    )

    session = app.handlers.quest_session(quest["quest_id"])

    assert session["ok"] is True
    assert session["snapshot"]["workspace_mode"] == "copilot"


def test_runtime_state_update_schedules_details_projection_refresh(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=False)
    quest = app.quest_service.create("runtime projection refresh quest")
    quest_root = Path(quest["quest_root"])
    queued: list[str] = []

    def _capture_queue(target_root: Path, kind: str, *, source_signature: str) -> None:
        assert target_root == quest_root
        assert source_signature
        queued.append(kind)

    monkeypatch.setattr(app.quest_service, "_queue_projection_build", _capture_queue)

    app.quest_service.update_runtime_state(
        quest_root=quest_root,
        status="running",
        active_run_id="run-projection-refresh",
    )

    assert queued == ["details"]


def test_research_state_update_schedules_details_and_canvas_projection_refresh(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=False)
    quest = app.quest_service.create("research projection refresh quest")
    quest_root = Path(quest["quest_root"])
    queued: list[str] = []

    def _capture_queue(target_root: Path, kind: str, *, source_signature: str) -> None:
        assert target_root == quest_root
        assert source_signature
        queued.append(kind)

    monkeypatch.setattr(app.quest_service, "_queue_projection_build", _capture_queue)

    app.quest_service.update_research_state(
        quest_root,
        current_workspace_branch="ideas/projection-refresh",
    )

    assert queued == ["details", "canvas"]


def test_runtime_state_updates_do_not_revert_status_on_concurrent_writes(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    service = DaemonApp(temp_home).quest_service
    snapshot = service.create("concurrent runtime state quest")
    quest_root = Path(snapshot["quest_root"])
    service.update_runtime_state(quest_root=quest_root, status="stopped", stop_reason="crash_recovered")

    original_write = service._write_runtime_state
    slow_write_entered = threading.Event()
    release_slow_write = threading.Event()
    run_update_done = threading.Event()

    def _write_runtime_state_with_pause(target_root: Path, payload: dict[str, object]) -> None:
        if (
            target_root == quest_root
            and payload.get("active_interaction_id") == "milestone-1"
            and payload.get("status") == "stopped"
        ):
            slow_write_entered.set()
            assert release_slow_write.wait(timeout=5), "timed out waiting to release slow runtime_state write"
        original_write(target_root, payload)

    service._write_runtime_state = _write_runtime_state_with_pause  # type: ignore[method-assign]

    def _set_interaction() -> None:
        service.update_runtime_state(
            quest_root=quest_root,
            active_interaction_id="milestone-1",
            last_artifact_interact_at="2026-03-15T10:51:08+00:00",
        )

    interaction_thread = threading.Thread(target=_set_interaction)
    interaction_thread.start()
    assert slow_write_entered.wait(timeout=2), "runtime_state interaction write never entered paused section"

    def _set_running() -> None:
        service.update_runtime_state(quest_root=quest_root, status="running", active_run_id="run-123")
        run_update_done.set()

    run_thread = threading.Thread(target=_set_running)
    run_thread.start()
    assert not run_update_done.wait(timeout=0.2), "second runtime_state update should block until the lock is released"
    release_slow_write.set()
    interaction_thread.join(timeout=2)
    run_thread.join(timeout=2)
    assert not interaction_thread.is_alive()
    assert not run_thread.is_alive()

    state = json.loads((quest_root / ".ds" / "runtime_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "running"
    assert state["display_status"] == "running"
    assert state["active_run_id"] == "run-123"
    assert state["active_interaction_id"] == "milestone-1"


def test_daemon_update_status_uses_launcher_json_contract(
    temp_home: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    monkeypatch.setenv("DEEPSCIENTIST_NODE_BINARY", "node")
    monkeypatch.setenv("DEEPSCIENTIST_LAUNCHER_PATH", str(project_root / "bin" / "ds.js"))

    captured: dict[str, object] = {}

    def _fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "current_version": "1.5.6",
                    "latest_version": "1.5.3",
                    "update_available": True,
                    "can_self_update": True,
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("deepscientist.daemon.app.subprocess.run", _fake_run)

    app = DaemonApp(temp_home, browser_auth_enabled=False)
    payload = app.system_update_status()

    assert payload["latest_version"] == "1.5.3"
    assert "--check" in captured["command"]
    assert "--json" in captured["command"]


def test_daemon_update_request_starts_background_worker_with_restart(
    temp_home: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    monkeypatch.setenv("DEEPSCIENTIST_NODE_BINARY", "node")
    monkeypatch.setenv("DEEPSCIENTIST_LAUNCHER_PATH", str(project_root / "bin" / "ds.js"))

    captured: dict[str, object] = {}

    def _fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "started": True,
                    "message": "DeepScientist update worker started.",
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("deepscientist.daemon.app.subprocess.run", _fake_run)

    app = DaemonApp(temp_home, browser_auth_enabled=False)
    app._serve_host = "0.0.0.0"
    app._serve_port = 20999
    payload = app.request_system_update(action="install_latest")

    assert payload["started"] is True
    assert "--background" in captured["command"]
    assert "--restart-daemon" in captured["command"]
    assert "0.0.0.0" in captured["command"]
    assert "20999" in captured["command"]


def test_weixin_qr_login_handlers_persist_connector_config(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
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
    write_yaml(manager.path_for("connectors"), connectors)
    app = DaemonApp(temp_home)

    monkeypatch.setattr(
        "deepscientist.daemon.app.fetch_weixin_qrcode",
        lambda **kwargs: {
            "qrcode": "wx-qr-1",
            "qrcode_img_content": "https://example.com/wx-qr-1.png",
        },
    )
    monkeypatch.setattr(
        "deepscientist.daemon.app.poll_weixin_qrcode_status",
        lambda **kwargs: {
            "status": "confirmed",
            "bot_token": "wx-bot-token",
            "ilink_bot_id": "wx-bot-1@im.bot",
            "baseurl": "https://ilinkai.weixin.qq.com",
            "ilink_user_id": "wx-owner@im.wechat",
        },
    )

    start_payload = app.handlers.weixin_login_qr_start({})
    assert start_payload["ok"] is True
    assert start_payload["qrcode_content"] == "https://example.com/wx-qr-1.png"
    assert start_payload["qrcode_url"] == "https://example.com/wx-qr-1.png"

    wait_payload = app.handlers.weixin_login_qr_wait({"session_key": start_payload["session_key"], "timeout_ms": 500})
    assert wait_payload["ok"] is True
    assert wait_payload["connected"] is True
    assert wait_payload["account_id"] == "wx-bot-1@im.bot"

    saved = manager.load_named("connectors")
    assert saved["weixin"]["enabled"] is True
    assert saved["weixin"]["bot_token"] == "wx-bot-token"
    assert saved["weixin"]["account_id"] == "wx-bot-1@im.bot"
    assert saved["weixin"]["login_user_id"] == "wx-owner@im.wechat"


def test_daemon_http_weixin_qr_wait_accepts_json_body(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=False)
    app._start_background_connectors = lambda: None  # type: ignore[method-assign]
    app._stop_background_connectors = lambda: None  # type: ignore[method-assign]
    app._start_terminal_attach_server = lambda host, port: None  # type: ignore[method-assign]
    app._stop_terminal_attach_server = lambda: None  # type: ignore[method-assign]

    captured: dict[str, object] = {}

    def _fake_wait(*, session_key: str, timeout_ms: int = 1_500) -> dict[str, object]:
        captured["session_key"] = session_key
        captured["timeout_ms"] = timeout_ms
        return {
            "ok": True,
            "connected": False,
            "session_key": session_key,
            "timeout_ms": timeout_ms,
        }

    monkeypatch.setattr(app, "wait_weixin_login_qr", _fake_wait)

    port = _pick_free_port()
    server_thread = threading.Thread(target=app.serve, args=("127.0.0.1", port), daemon=True)
    server_thread.start()
    try:
        _wait_for_json(f"http://127.0.0.1:{port}/api/health")
        request = Request(
            f"http://127.0.0.1:{port}/api/connectors/weixin/login/qr/wait",
            data=json.dumps({"session_key": "wxqr-http-1", "timeout_ms": 3210}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["ok"] is True
        assert payload["session_key"] == "wxqr-http-1"
        assert payload["timeout_ms"] == 3210
        assert captured == {
            "session_key": "wxqr-http-1",
            "timeout_ms": 3210,
        }
    finally:
        app.request_shutdown(source="test-daemon-http-weixin")
        server_thread.join(timeout=10)
        assert not server_thread.is_alive()


def test_weixin_qr_wait_treats_poll_timeout_as_pending(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    app = DaemonApp(temp_home)

    monkeypatch.setattr(
        "deepscientist.daemon.app.fetch_weixin_qrcode",
        lambda **kwargs: {
            "qrcode": "wx-qr-timeout",
            "qrcode_img_content": "https://example.com/wx-qr-timeout.png",
        },
    )
    monkeypatch.setattr(
        "deepscientist.daemon.app.poll_weixin_qrcode_status",
        lambda **kwargs: (_ for _ in ()).throw(TimeoutError("The read operation timed out")),
    )

    start_payload = app.handlers.weixin_login_qr_start({})
    wait_payload = app.handlers.weixin_login_qr_wait({"session_key": start_payload["session_key"], "timeout_ms": 500})

    assert wait_payload["ok"] is True
    assert wait_payload["connected"] is False
    assert wait_payload["status"] == "wait"
    assert wait_payload["session_key"] == start_payload["session_key"]
    assert wait_payload["qrcode_url"] == "https://example.com/wx-qr-timeout.png"


def test_daemon_serves_health_and_ui(temp_home: Path, project_root: Path, pythonpath_env) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    new_process = subprocess.run(
        [
            "python3",
            "-m",
            "deepscientist.cli",
            "--home",
            str(temp_home),
            "new",
            "daemon api quest",
        ],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    quest_id = json.loads(new_process.stdout)["quest_id"]
    quest_root = temp_home / "quests" / quest_id
    (quest_root / "docs").mkdir(parents=True, exist_ok=True)
    (quest_root / "figures").mkdir(parents=True, exist_ok=True)
    (quest_root / "paper" / "latex").mkdir(parents=True, exist_ok=True)
    (quest_root / "docs" / "appendix.pdf").write_bytes(b"%PDF-1.4\n%quest-pdf\n")
    (quest_root / "figures" / "plot.png").write_bytes(b"\x89PNG\r\n\x1a\nquest-plot")
    (quest_root / "paper" / "latex" / "main.tex").write_text(
        "\n".join(
            [
                r"\documentclass{article}",
                r"\title{Daemon API Paper}",
                r"\author{DeepScientist}",
                r"\date{}",
                r"\begin{document}",
                r"\maketitle",
                "Hello from daemon API test.",
                r"\end{document}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    server = subprocess.Popen(
        [
            "python3",
            "-m",
            "deepscientist.cli",
            "--home",
            str(temp_home),
            "daemon",
            "--host",
            "127.0.0.1",
            "--port",
            "20901",
            "--auth",
            "false",
        ],
        cwd=project_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        time.sleep(2)
        health = _get_json("http://127.0.0.1:20901/api/health")
        assert health["status"] == "ok"
        quest = _get_json(f"http://127.0.0.1:20901/api/quests/{quest_id}")
        assert quest["quest_id"] == quest_id
        workflow = _get_json(f"http://127.0.0.1:20901/api/quests/{quest_id}/workflow")
        assert workflow["quest_id"] == quest_id
        assert "entries" in workflow
        node_traces = _get_json(f"http://127.0.0.1:20901/api/quests/{quest_id}/node-traces")
        assert node_traces["quest_id"] == quest_id
        assert "items" in node_traces
        stage_view_request = Request(
            f"http://127.0.0.1:20901/api/quests/{quest_id}/stage-view",
            data=json.dumps(
                {
                    "selection_ref": "stage:main:baseline",
                    "selection_type": "stage_node",
                    "branch_name": "main",
                    "stage_key": "baseline",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(stage_view_request) as response:  # noqa: S310
            stage_view = json.loads(response.read().decode("utf-8"))
        assert stage_view["quest_id"] == quest_id
        assert stage_view["stage_key"] == "baseline"
        assert "sections" in stage_view
        explorer = _get_json(f"http://127.0.0.1:20901/api/quests/{quest_id}/explorer")
        assert explorer["view"]["mode"] == "live"
        search = _get_json(
            f"http://127.0.0.1:20901/api/quests/{quest_id}/search?q={quote('daemon api quest')}&limit=10"
        )
        assert search["quest_id"] == quest_id
        assert search["items"]
        assert any(item["path"] == "brief.md" for item in search["items"])
        graph = _get_json(f"http://127.0.0.1:20901/api/quests/{quest_id}/graph")
        assert "lines" in graph
        branches = _get_json(f"http://127.0.0.1:20901/api/quests/{quest_id}/git/branches")
        assert branches["default_ref"] == "main"
        explorer_snapshot = _get_json(f"http://127.0.0.1:20901/api/quests/{quest_id}/explorer?revision=HEAD&mode=commit")
        assert explorer_snapshot["view"]["mode"] == "commit"
        assert explorer_snapshot["view"]["revision"] == "HEAD"
        assert explorer_snapshot["view"]["read_only"] is True
        log_payload = _get_json(f"http://127.0.0.1:20901/api/quests/{quest_id}/git/log?ref=main&limit=5")
        assert log_payload["ok"] is True
        assert log_payload["commits"]
        latest_sha = log_payload["commits"][0]["sha"]
        compare = _get_json(f"http://127.0.0.1:20901/api/quests/{quest_id}/git/compare?base=main&head=main")
        assert compare["ok"] is True
        commit_payload = _get_json(f"http://127.0.0.1:20901/api/quests/{quest_id}/git/commit?sha={latest_sha}")
        assert commit_payload["ok"] is True
        assert commit_payload["sha"] == latest_sha
        docs_index = _get_json("http://127.0.0.1:20901/api/docs")
        assert docs_index
        docs_open_request = Request(
            "http://127.0.0.1:20901/api/docs/open",
            data=json.dumps({"document_id": docs_index[0]["document_id"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(docs_open_request) as response:  # noqa: S310
            docs_open = json.loads(response.read().decode("utf-8"))
        assert docs_open["source_scope"] == "system_docs"
        assert docs_open["content"]
        diff = _get_json(
            f"http://127.0.0.1:20901/api/quests/{quest_id}/git/diff-file?base=main&head=main&path={quote('plan.md')}"
        )
        assert diff["ok"] is True
        assert diff["path"] == "plan.md"
        commit_diff = _get_json(
            f"http://127.0.0.1:20901/api/quests/{quest_id}/git/commit-file?sha={latest_sha}&path={quote('plan.md')}"
        )
        assert commit_diff["ok"] is True
        assert commit_diff["path"] == "plan.md"
        with urlopen(  # noqa: S310
            Request(
                f"http://127.0.0.1:20901/api/quests/{quest_id}/documents/open",
                data=json.dumps({"document_id": "path::docs/appendix.pdf"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ) as response:
            pdf_doc = json.loads(response.read().decode("utf-8"))
        assert pdf_doc["meta"]["renderer_hint"] == "pdf"
        with urlopen(f"http://127.0.0.1:20901{pdf_doc['asset_url']}") as response:  # noqa: S310
            assert response.headers["Content-Type"] == "application/pdf"
            assert response.read().startswith(b"%PDF-1.4")
        if shutil.which("pdflatex"):
            folder_id = f"quest-dir::{quest_id}::paper%2Flatex"
            compile_request = Request(
                f"http://127.0.0.1:20901/api/v1/projects/{quest_id}/latex/{folder_id}/compile",
                data=json.dumps({"compiler": "pdflatex"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(compile_request) as response:  # noqa: S310
                compile_payload = json.loads(response.read().decode("utf-8"))
            assert compile_payload["project_id"] == quest_id
            assert compile_payload["folder_id"] == folder_id
            assert compile_payload["status"] == "success"
            assert compile_payload["pdf_ready"] is True
            build_id = compile_payload["build_id"]
            builds = _get_json(
                f"http://127.0.0.1:20901/api/v1/projects/{quest_id}/latex/{folder_id}/builds?limit=5"
            )
            assert any(item["build_id"] == build_id for item in builds)
            build = _get_json(
                f"http://127.0.0.1:20901/api/v1/projects/{quest_id}/latex/{folder_id}/builds/{build_id}"
            )
            assert build["status"] == "success"
            with urlopen(  # noqa: S310
                f"http://127.0.0.1:20901/api/v1/projects/{quest_id}/latex/{folder_id}/builds/{build_id}/log"
            ) as response:
                log_text = response.read().decode("utf-8")
            assert "pdflatex" in log_text
            with urlopen(  # noqa: S310
                f"http://127.0.0.1:20901/api/v1/projects/{quest_id}/latex/{folder_id}/builds/{build_id}/pdf"
            ) as response:
                assert response.headers["Content-Type"] == "application/pdf"
                assert response.read().startswith(b"%PDF-")
            with urlopen(  # noqa: S310
                f"http://127.0.0.1:20901/api/v1/projects/{quest_id}/latex/{folder_id}/archive"
            ) as response:
                assert response.headers["Content-Type"] == "application/zip"
                archive_bytes = response.read()
            assert archive_bytes.startswith(b"PK")
        with urlopen(  # noqa: S310
            Request(
                f"http://127.0.0.1:20901/api/quests/{quest_id}/documents/open",
                data=json.dumps({"document_id": "questpath::docs/appendix.pdf"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ) as response:
            pdf_doc_from_questpath = json.loads(response.read().decode("utf-8"))
        assert pdf_doc_from_questpath["meta"]["renderer_hint"] == "pdf"
        with urlopen(  # noqa: S310
            Request(
                f"http://127.0.0.1:20901/api/quests/{quest_id}/documents/open",
                data=json.dumps({"document_id": "path::figures/plot.png"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ) as response:
            image_doc = json.loads(response.read().decode("utf-8"))
        assert image_doc["meta"]["renderer_hint"] == "image"
        with urlopen(f"http://127.0.0.1:20901{image_doc['asset_url']}") as response:  # noqa: S310
            assert response.headers["Content-Type"] == "image/png"
            assert response.read().startswith(b"\x89PNG")
        upload_asset_request = Request(
            f"http://127.0.0.1:20901/api/quests/{quest_id}/documents/assets",
            data=json.dumps(
                {
                    "document_id": "brief.md",
                    "file_name": "diagram.png",
                    "mime_type": "image/png",
                    "kind": "image",
                    "content_base64": base64.b64encode(b"\x89PNG\r\n\x1a\ndaemon-upload").decode("ascii"),
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(upload_asset_request) as response:  # noqa: S310
            uploaded_asset = json.loads(response.read().decode("utf-8"))
        assert uploaded_asset["ok"] is True
        assert uploaded_asset["relative_path"].startswith("brief.assets/")
        with urlopen(f"http://127.0.0.1:20901{uploaded_asset['asset_url']}") as response:  # noqa: S310
            assert response.headers["Content-Type"] == "image/png"
            assert response.read().startswith(b"\x89PNG")
        with urlopen(f"http://127.0.0.1:20901/api/quests/{quest_id}/graph/svg") as response:  # noqa: S310
            svg = response.read().decode("utf-8")
        assert "<svg" in svg
        root_request = Request("http://127.0.0.1:20901/")
        with urlopen(root_request) as response:  # noqa: S310
            html = response.read().decode("utf-8")
        assert "DeepScientist" in html
        assert "Copilot" in html
        assert "/assets/fonts/ds-fonts.css" in html
        with urlopen(f"http://127.0.0.1:20901/projects/{quest_id}") as response:  # noqa: S310
            project_html = response.read().decode("utf-8")
        assert "DeepScientist" in project_html
        assert "Copilot" in project_html

        with urlopen("http://127.0.0.1:20901/assets/fonts/ds-fonts.css") as response:  # noqa: S310
            stylesheet = response.read().decode("utf-8")
            assert response.headers["Content-Type"] == "text/css"
        assert "font-family: 'DS-Project';" in stylesheet
        assert "NotoSerifSC-Regular-C94HN_ZN.ttf" in stylesheet

        with urlopen("http://127.0.0.1:20901/assets/fonts/Satoshi-Medium-ByP-Zb-9.woff2") as response:  # noqa: S310
            font_payload = response.read(16)
            assert response.headers["Content-Type"] == "font/woff2"
        assert font_payload
    finally:
        server.terminate()
        server.wait(timeout=10)


def test_daemon_serves_lingzhu_metis_routes(temp_home: Path, project_root: Path, pythonpath_env) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named_normalized("connectors")
    auth_ak = generate_lingzhu_auth_ak()
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = auth_ak
    connectors["lingzhu"]["local_host"] = "127.0.0.1"
    connectors["lingzhu"]["gateway_port"] = 20902
    connectors["lingzhu"]["public_base_url"] = "http://example.com:20902"
    save_result = manager.save_named_payload("connectors", connectors)
    assert save_result["ok"] is True

    app = DaemonApp(temp_home)
    snapshot = app.quest_service.create("lingzhu metis route quest")
    app.update_quest_binding(snapshot["quest_id"], "lingzhu:direct:glass-1", force=True)

    server = subprocess.Popen(
        [
            "python3",
            "-m",
            "deepscientist.cli",
            "--home",
            str(temp_home),
            "daemon",
            "--host",
            "127.0.0.1",
            "--port",
            "20902",
            "--auth",
            "false",
        ],
        cwd=project_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        health = _wait_for_json("http://127.0.0.1:20902/metis/agent/api/health")
        assert health["status"] == "ok"
        assert health["endpoint"] == "/metis/agent/api/sse"
        assert health["agentId"] == "main"

        sse_request = Request(
            "http://127.0.0.1:20902/metis/agent/api/sse",
            data=json.dumps(
                {
                    "message_id": "lingzhu-test-001",
                    "agent_id": "main",
                    "user_id": "glass-1",
                    "message": [{"role": "user", "type": "text", "text": "/status"}],
                }
            ).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "Authorization": f"Bearer {auth_ak}",
            },
            method="POST",
        )
        with urlopen(sse_request) as response:  # noqa: S310
            content_type = str(response.headers.get("Content-Type") or "")
            body = response.read().decode("utf-8")
        assert "text/event-stream" in content_type
        assert "event: message" in body
        data_lines = [line[len("data: "):] for line in body.splitlines() if line.startswith("data: ")]
        assert data_lines
        payload = json.loads("".join(data_lines))
        assert payload["message_id"] == "lingzhu-test-001"
        assert payload["agent_id"] == "main"
        assert payload["is_finish"] is True
        assert snapshot["quest_id"] in payload["answer_stream"]

        unauthorized_request = Request(
            "http://127.0.0.1:20902/metis/agent/api/sse",
            data=json.dumps(
                {
                    "message_id": "lingzhu-test-unauthorized",
                    "agent_id": "main",
                    "message": [{"role": "user", "type": "text", "text": "hello"}],
                }
            ).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer wrong-token",
            },
            method="POST",
        )
        with pytest.raises(HTTPError) as exc_info:
            urlopen(unauthorized_request)  # noqa: S310
        assert exc_info.value.code == 401
    finally:
        server.terminate()
        server.wait(timeout=10)


def test_lingzhu_sse_submits_only_prefixed_task_text(temp_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    auth_ak = generate_lingzhu_auth_ak()
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = auth_ak
    connectors["lingzhu"]["public_base_url"] = "http://example.com:20999"
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("lingzhu prefix gate quest")
    quest_id = quest["quest_id"]
    app.update_quest_binding(quest_id, "lingzhu:direct:glass-1", force=True)
    monkeypatch.setattr(
        app,
        "schedule_turn",
        lambda quest_id, reason="user_message": {
            "scheduled": True,
            "started": False,
            "queued": False,
            "reason": reason,
        },
    )

    first_handler = _FakeSseHandler()
    app.stream_lingzhu_sse(
        first_handler,
        raw_body=json.dumps(
            {
                "message_id": "lingzhu-prefix-001",
                "agent_id": "main",
                "user_id": "glass-1",
                "message": [{"role": "user", "type": "text", "text": "我现在的任务是 复现 baseline"}],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Authorization": f"Bearer {auth_ak}"},
    )

    assert first_handler.status_code == 200
    first_events = _parse_sse_events(first_handler.wfile.getvalue())
    assert first_events
    assert "进行中" in str(first_events[-1]["data"]["answer_stream"])

    history = app.quest_service.history(quest_id)
    assert history
    assert history[-1]["role"] == "user"
    assert history[-1]["content"] == "复现 baseline"

    channel = app._channel_with_bindings("lingzhu")
    channel.send(
        {
            "conversation_id": "lingzhu:direct:glass-1",
            "quest_id": quest_id,
            "kind": "progress",
            "message": "阶段一完成",
        }
    )

    second_handler = _FakeSseHandler()
    app.stream_lingzhu_sse(
        second_handler,
        raw_body=json.dumps(
            {
                "message_id": "lingzhu-prefix-002",
                "agent_id": "main",
                "user_id": "glass-1",
                "message": [{"role": "user", "type": "text", "text": "汇报"}],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Authorization": f"Bearer {auth_ak}"},
    )

    second_events = _parse_sse_events(second_handler.wfile.getvalue())
    assert second_events
    assert second_events[-1]["data"]["answer_stream"] == "阶段一完成"

    history_after_poll = app.quest_service.history(quest_id)
    user_messages = [item for item in history_after_poll if str(item.get("role") or "") == "user"]
    assert len(user_messages) == 1
    assert user_messages[-1]["content"] == "复现 baseline"


def test_lingzhu_sse_accepts_messages_alias_and_missing_ids(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    auth_ak = generate_lingzhu_auth_ak()
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = auth_ak
    connectors["lingzhu"]["agent_id"] = "DeepScientist"
    connectors["lingzhu"]["public_base_url"] = "http://example.com:20999"
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    handler = _FakeSseHandler()
    app.stream_lingzhu_sse(
        handler,
        raw_body=json.dumps(
            {
                "user_id": "glass-alias",
                "messages": [{"role": "user", "type": "text", "text": "汇报"}],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Authorization": f"Bearer {auth_ak}"},
    )

    assert handler.status_code == 200
    events = _parse_sse_events(handler.wfile.getvalue())
    assert events
    payload = events[-1]["data"]
    assert payload["agent_id"] == "DeepScientist"
    assert str(payload["message_id"]).startswith("lingzhu-")


def test_lingzhu_short_bind_command_binds_target_quest(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    auth_ak = generate_lingzhu_auth_ak()
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = auth_ak
    connectors["lingzhu"]["public_base_url"] = "http://example.com:20999"
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("lingzhu bind target quest")
    quest_id = quest["quest_id"]

    handler = _FakeSseHandler()
    app.stream_lingzhu_sse(
        handler,
        raw_body=json.dumps(
            {
                "message_id": "lingzhu-bind-001",
                "agent_id": "DeepScientist",
                "user_id": "glass-bind",
                "message": [{"role": "user", "type": "text", "text": f"绑定{quest_id}"}],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Authorization": f"Bearer {auth_ak}"},
    )

    assert handler.status_code == 200
    events = _parse_sse_events(handler.wfile.getvalue())
    assert events
    assert quest_id in str(events[-1]["data"]["answer_stream"])
    channel = app._channel_with_bindings("lingzhu")
    assert channel.resolve_bound_quest(lingzhu_passive_conversation_id(connectors["lingzhu"])) == quest_id


def test_lingzhu_short_bind_command_accepts_punctuation_and_chinese_numeric_target(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    auth_ak = generate_lingzhu_auth_ak()
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = auth_ak
    connectors["lingzhu"]["public_base_url"] = "http://example.com:20999"
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("lingzhu chinese bind target quest", quest_id="025")
    quest_id = quest["quest_id"]

    handler = _FakeSseHandler()
    app.stream_lingzhu_sse(
        handler,
        raw_body=json.dumps(
            {
                "message_id": "lingzhu-bind-cn-001",
                "agent_id": "DeepScientist",
                "user_id": "glass-bind-cn",
                "message": [{"role": "user", "type": "text", "text": "绑定：零二五。"}],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Authorization": f"Bearer {auth_ak}"},
    )

    assert handler.status_code == 200
    events = _parse_sse_events(handler.wfile.getvalue())
    assert quest_id in str(events[-1]["data"]["answer_stream"])
    channel = app._channel_with_bindings("lingzhu")
    assert channel.resolve_bound_quest(lingzhu_passive_conversation_id(connectors["lingzhu"])) == quest_id


def test_lingzhu_short_resume_command_accepts_punctuation(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    auth_ak = generate_lingzhu_auth_ak()
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = auth_ak
    connectors["lingzhu"]["public_base_url"] = "http://example.com:20999"
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("lingzhu punctuation resume quest", quest_id="025")
    quest_id = quest["quest_id"]
    app.update_quest_binding(quest_id, "lingzhu:direct:glass-resume-punc", force=True)
    app.quest_service.mark_turn_finished(quest_id, status="stopped", stop_reason="test_stop")

    handler = _FakeSseHandler()
    app.stream_lingzhu_sse(
        handler,
        raw_body=json.dumps(
            {
                "message_id": "lingzhu-resume-cn-001",
                "agent_id": "DeepScientist",
                "user_id": "glass-resume-punc",
                "message": [{"role": "user", "type": "text", "text": "恢复。"}],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Authorization": f"Bearer {auth_ak}"},
    )

    assert handler.status_code == 200
    snapshot = app.quest_service.snapshot(quest_id)
    assert str(snapshot.get("status") or snapshot.get("runtime_status") or "") == "active"


def test_lingzhu_unbound_help_mentions_chinese_shortcuts(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    auth_ak = generate_lingzhu_auth_ak()
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = auth_ak
    connectors["lingzhu"]["public_base_url"] = "http://example.com:20999"
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    handler = _FakeSseHandler()
    app.stream_lingzhu_sse(
        handler,
        raw_body=json.dumps(
            {
                "message_id": "lingzhu-help-001",
                "agent_id": "DeepScientist",
                "user_id": "glass-help",
                "message": [{"role": "user", "type": "text", "text": "我现在的任务是 复现 baseline"}],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Authorization": f"Bearer {auth_ak}"},
    )

    assert handler.status_code == 200
    events = _parse_sse_events(handler.wfile.getvalue())
    assert events
    answer_text = str(events[-1]["data"]["answer_stream"])
    assert "绑定" in answer_text
    assert "帮助" in answer_text
    assert "新建" in answer_text


def test_lingzhu_stopped_poll_reply_includes_action_hint(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    auth_ak = generate_lingzhu_auth_ak()
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = auth_ak
    connectors["lingzhu"]["public_base_url"] = "http://example.com:20999"
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("lingzhu stopped hint quest", quest_id="026")
    quest_id = quest["quest_id"]
    app.update_quest_binding(quest_id, "lingzhu:direct:glass-stop-hint", force=True)
    app.quest_service.mark_turn_finished(quest_id, status="stopped", stop_reason="test_stop")

    handler = _FakeSseHandler()
    app.stream_lingzhu_sse(
        handler,
        raw_body=json.dumps(
            {
                "message_id": "lingzhu-stop-hint-001",
                "agent_id": "DeepScientist",
                "user_id": "glass-stop-hint",
                "message": [{"role": "user", "type": "text", "text": "你好。"}],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Authorization": f"Bearer {auth_ak}"},
    )

    assert handler.status_code == 200
    events = _parse_sse_events(handler.wfile.getvalue())
    answer_text = str(events[-1]["data"]["answer_stream"])
    assert "恢复" in answer_text
    assert quest_id in answer_text


def test_lingzhu_task_prefix_allows_leading_punctuation(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    auth_ak = generate_lingzhu_auth_ak()
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = auth_ak
    connectors["lingzhu"]["public_base_url"] = "http://example.com:20999"
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("lingzhu task punctuation quest")
    quest_id = quest["quest_id"]
    app.update_quest_binding(quest_id, "lingzhu:direct:glass-task-punc", force=True)

    captured: dict[str, str] = {}

    def fake_submit_user_message(target_quest_id: str, *, text: str, source: str, attachments=None, reply_to_interaction_id=None, client_message_id=None):  # noqa: ANN001
        captured["quest_id"] = target_quest_id
        captured["text"] = text
        return {"scheduled": True, "started": True, "queued": False, "reason": "user_message"}

    app.submit_user_message = fake_submit_user_message  # type: ignore[method-assign]
    app._lingzhu_wait_for_outbox_records = lambda conversation_id, delivered_count, timeout_seconds: ([], delivered_count)  # type: ignore[method-assign]

    handler = _FakeSseHandler()
    app.stream_lingzhu_sse(
        handler,
        raw_body=json.dumps(
            {
                "message_id": "lingzhu-task-punc-001",
                "agent_id": "DeepScientist",
                "user_id": "glass-task-punc",
                "message": [{"role": "user", "type": "text", "text": "！我现在的任务是：复现 baseline。"}],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Authorization": f"Bearer {auth_ak}"},
    )

    assert handler.status_code == 200
    assert captured["quest_id"] == quest_id
    assert captured["text"] == "复现 baseline。"


def test_lingzhu_sse_replays_buffered_outbox_messages_only_once(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    auth_ak = generate_lingzhu_auth_ak()
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = auth_ak
    connectors["lingzhu"]["public_base_url"] = "http://example.com:20999"
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("lingzhu replay quest")
    quest_id = quest["quest_id"]
    app.update_quest_binding(quest_id, "lingzhu:direct:glass-2", force=True)
    channel = app._channel_with_bindings("lingzhu")
    channel.send(
        {
            "conversation_id": "lingzhu:direct:glass-2",
            "quest_id": quest_id,
            "kind": "progress",
            "message": "第一条",
        }
    )
    channel.send(
        {
            "conversation_id": "lingzhu:direct:glass-2",
            "quest_id": quest_id,
            "kind": "progress",
            "message": "第二条",
        }
    )

    first_handler = _FakeSseHandler()
    app.stream_lingzhu_sse(
        first_handler,
        raw_body=json.dumps(
            {
                "message_id": "lingzhu-replay-001",
                "agent_id": "main",
                "user_id": "glass-2",
                "message": [{"role": "user", "type": "text", "text": "继续"}],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Authorization": f"Bearer {auth_ak}"},
    )

    first_events = _parse_sse_events(first_handler.wfile.getvalue())
    assert [event["data"]["answer_stream"] for event in first_events] == ["第一条", "第二条"]

    second_handler = _FakeSseHandler()
    app.stream_lingzhu_sse(
        second_handler,
        raw_body=json.dumps(
            {
                "message_id": "lingzhu-replay-002",
                "agent_id": "main",
                "user_id": "glass-2",
                "message": [{"role": "user", "type": "text", "text": "继续"}],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Authorization": f"Bearer {auth_ak}"},
    )

    second_events = _parse_sse_events(second_handler.wfile.getvalue())
    assert second_events
    assert [event["data"]["answer_stream"] for event in second_events] == ["进行中"]


def test_lingzhu_sse_replays_surface_actions_as_tool_calls(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    auth_ak = generate_lingzhu_auth_ak()
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = auth_ak
    connectors["lingzhu"]["public_base_url"] = "http://example.com:20999"
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("lingzhu surface action replay quest")
    quest_id = quest["quest_id"]
    app.update_quest_binding(quest_id, "lingzhu:direct:glass-3", force=True)
    channel = app._channel_with_bindings("lingzhu")
    channel.send(
        {
            "conversation_id": "lingzhu:direct:glass-3",
            "quest_id": quest_id,
            "kind": "progress",
            "message": "准备拍照",
            "surface_actions": [{"type": "take_photo"}],
        }
    )

    handler = _FakeSseHandler()
    app.stream_lingzhu_sse(
        handler,
        raw_body=json.dumps(
            {
                "message_id": "lingzhu-surface-001",
                "agent_id": "main",
                "user_id": "glass-3",
                "message": [{"role": "user", "type": "text", "text": "继续"}],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Authorization": f"Bearer {auth_ak}"},
    )

    events = _parse_sse_events(handler.wfile.getvalue())
    assert len(events) == 2
    assert events[0]["data"]["type"] == "answer"
    assert events[0]["data"]["answer_stream"] == "准备拍照"
    assert events[1]["data"]["type"] == "tool_call"
    assert events[1]["data"]["tool_call"]["command"] == "take_photo"
    assert events[1]["data"]["tool_call"]["handling_required"] is True


def test_lingzhu_sse_detects_tool_call_from_marker_text(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    auth_ak = generate_lingzhu_auth_ak()
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = auth_ak
    connectors["lingzhu"]["public_base_url"] = "http://example.com:20999"
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("lingzhu marker fallback quest")
    quest_id = quest["quest_id"]
    app.update_quest_binding(quest_id, "lingzhu:direct:glass-4", force=True)
    channel = app._channel_with_bindings("lingzhu")
    channel.send(
        {
            "conversation_id": "lingzhu:direct:glass-4",
            "quest_id": quest_id,
            "kind": "progress",
            "message": "<LINGZHU_TOOL_CALL:take_photo:{}>",
        }
    )

    handler = _FakeSseHandler()
    app.stream_lingzhu_sse(
        handler,
        raw_body=json.dumps(
            {
                "message_id": "lingzhu-marker-001",
                "agent_id": "main",
                "user_id": "glass-4",
                "message": [{"role": "user", "type": "text", "text": "继续"}],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Authorization": f"Bearer {auth_ak}"},
    )

    events = _parse_sse_events(handler.wfile.getvalue())
    assert len(events) == 1
    assert events[0]["data"]["type"] == "tool_call"
    assert events[0]["data"]["tool_call"]["command"] == "take_photo"


def test_lingzhu_sse_detects_tool_call_from_plain_text_instruction(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    auth_ak = generate_lingzhu_auth_ak()
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = auth_ak
    connectors["lingzhu"]["public_base_url"] = "http://example.com:20999"
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("lingzhu plain text fallback quest")
    quest_id = quest["quest_id"]
    app.update_quest_binding(quest_id, "lingzhu:direct:glass-plain", force=True)
    channel = app._channel_with_bindings("lingzhu")
    channel.send(
        {
            "conversation_id": "lingzhu:direct:glass-plain",
            "quest_id": quest_id,
            "kind": "progress",
            "message": "请拍照记录当前白板",
        }
    )

    handler = _FakeSseHandler()
    app.stream_lingzhu_sse(
        handler,
        raw_body=json.dumps(
            {
                "message_id": "lingzhu-plain-001",
                "agent_id": "main",
                "user_id": "glass-plain",
                "message": [{"role": "user", "type": "text", "text": "继续"}],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Authorization": f"Bearer {auth_ak}"},
    )

    events = _parse_sse_events(handler.wfile.getvalue())
    assert len(events) == 2
    assert events[0]["data"]["type"] == "answer"
    assert events[0]["data"]["answer_stream"] == "请拍照记录当前白板"
    assert events[1]["data"]["type"] == "tool_call"
    assert events[1]["data"]["tool_call"]["command"] == "take_photo"


def test_lingzhu_sse_normalizes_surface_action_aliases(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    auth_ak = generate_lingzhu_auth_ak()
    connectors["lingzhu"]["enabled"] = True
    connectors["lingzhu"]["auth_ak"] = auth_ak
    connectors["lingzhu"]["enable_experimental_native_actions"] = True
    connectors["lingzhu"]["public_base_url"] = "http://example.com:20999"
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("lingzhu alias normalization quest")
    quest_id = quest["quest_id"]
    app.update_quest_binding(quest_id, "lingzhu:direct:glass-5", force=True)
    channel = app._channel_with_bindings("lingzhu")
    channel.send(
        {
            "conversation_id": "lingzhu:direct:glass-5",
            "quest_id": quest_id,
            "kind": "progress",
            "message": "发送通知",
            "surface_actions": [{"type": "notification", "title": "阶段完成", "body": "可以继续"}],
        }
    )

    handler = _FakeSseHandler()
    app.stream_lingzhu_sse(
        handler,
        raw_body=json.dumps(
            {
                "message_id": "lingzhu-alias-001",
                "agent_id": "main",
                "user_id": "glass-5",
                "message": [{"role": "user", "type": "text", "text": "继续"}],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Authorization": f"Bearer {auth_ak}"},
    )

    events = _parse_sse_events(handler.wfile.getvalue())
    assert len(events) == 2
    assert events[0]["data"]["type"] == "answer"
    assert events[1]["data"]["type"] == "tool_call"
    assert events[1]["data"]["tool_call"]["command"] == "send_notification"
    assert events[1]["data"]["tool_call"]["content"] == "阶段完成\n可以继续"


def test_daemon_serves_docs_assets(temp_home: Path, project_root: Path, pythonpath_env) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    port = _pick_free_port()
    base_url = f"http://127.0.0.1:{port}"

    server = subprocess.Popen(
        [
            "python3",
            "-m",
            "deepscientist.cli",
            "--home",
            str(temp_home),
            "daemon",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--auth",
            "false",
        ],
        cwd=project_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        _wait_for_json(f"{base_url}/api/health")
        docs_index = _get_json(f"{base_url}/api/docs")
        assert any(item["document_id"] == "zh/03_QQ_CONNECTOR_GUIDE.md" for item in docs_index)
        with urlopen(f"{base_url}/api/v1/docs/assets/images/qq/tencent-cloud-qq-register.png") as response:  # noqa: S310
            asset_payload = response.read()
            asset_content_type = response.info().get_content_type()
        assert asset_content_type == "image/png"
        assert asset_payload.startswith(b"\x89PNG")
    finally:
        server.terminate()
        server.wait(timeout=10)


def test_handlers_arxiv_import_and_list_roundtrip(temp_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("arxiv api quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    def fake_urlopen(request, timeout=8):  # noqa: ANN001
        url = request.full_url
        if "export.arxiv.org/api/query" in url:
            return _FakeUrlopenResponse(
                """
                <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
                  <entry>
                    <id>http://arxiv.org/abs/2010.11929</id>
                    <published>2020-10-23T17:54:00Z</published>
                    <title>Vision Transformers</title>
                    <summary>Vision Transformers apply pure transformer layers directly to image patches.</summary>
                    <author><name>Dosovitskiy, Alexey</name></author>
                    <arxiv:primary_category term="cs.CV" />
                    <category term="cs.CV" />
                  </entry>
                </feed>
                """
            )
        if url.endswith("/overview/2010.11929.md"):
            return _FakeUrlopenResponse("# Vision Transformers\n\nA concise AlphaXiv summary.")
        if url.endswith("/pdf/2010.11929.pdf"):
            return _FakeUrlopenResponse("%PDF-1.7\nfake pdf body")
        if url.endswith("/abs/2010.11929"):
            return _FakeUrlopenResponse(
                """
                <html>
                  <head>
                    <meta name="citation_title" content="Vision Transformers" />
                    <meta name="citation_author" content="Dosovitskiy, Alexey" />
                  </head>
                  <body>
                    <blockquote class="abstract mathjax">
                      <span class="descriptor">Abstract:</span>
                      Vision Transformers apply pure transformer layers directly to image patches.
                    </blockquote>
                  </body>
                </html>
                """
            )
        raise AssertionError(url)

    monkeypatch.setattr("deepscientist.artifact.arxiv.urlopen", fake_urlopen)
    monkeypatch.setattr("deepscientist.arxiv_library.urlopen", fake_urlopen)

    imported = app.handlers.arxiv_import({"project_id": quest_id, "arxiv_id": "2010.11929"})
    assert imported["arxiv_id"] == "2010.11929"
    assert imported["status"] in {"processing", "ready"}

    pdf_path = quest_root / "literature" / "arxiv" / "pdfs" / "2010.11929.pdf"
    for _ in range(40):
        if pdf_path.exists():
            break
        time.sleep(0.05)
    assert pdf_path.exists()

    listed = app.handlers.arxiv_list(f"/api/v1/arxiv/list?project_id={quest_id}")
    assert listed["ok"] is True
    assert listed["count"] == 1
    assert listed["items"][0]["arxiv_id"] == "2010.11929"
    assert listed["items"][0]["overview_markdown"].startswith("# Vision Transformers")
    assert listed["items"][0]["document_id"] == "questpath::literature/arxiv/pdfs/2010.11929.pdf"


def test_daemon_http_arxiv_list_route_passes_request_path(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=False)
    app._start_background_connectors = lambda: None  # type: ignore[method-assign]
    app._stop_background_connectors = lambda: None  # type: ignore[method-assign]
    app._start_terminal_attach_server = lambda host, port: None  # type: ignore[method-assign]
    app._stop_terminal_attach_server = lambda: None  # type: ignore[method-assign]

    quest = app.quest_service.create("arxiv http api quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    pdf_path = quest_root / "literature" / "arxiv" / "pdfs" / "2010.11929.pdf"
    ensure_dir(pdf_path.parent)
    pdf_path.write_bytes(b"%PDF-1.7\nhttp arxiv route test")
    app.artifact_service.arxiv_library.upsert_item(
        quest_root,
        {
            "arxiv_id": "2010.11929",
            "title": "Vision Transformers",
            "display_name": "2010.11929",
            "abstract": "A saved abstract.",
            "status": "ready",
            "pdf_rel_path": "literature/arxiv/pdfs/2010.11929.pdf",
        },
    )

    port = _pick_free_port()
    server_thread = threading.Thread(target=app.serve, args=("127.0.0.1", port), daemon=True)
    server_thread.start()
    try:
        _wait_for_json(f"http://127.0.0.1:{port}/api/health")
        payload = _get_json(f"http://127.0.0.1:{port}/api/v1/arxiv/list?project_id={quest_id}")
        assert payload["ok"] is True
        assert payload["count"] == 1
        assert payload["items"][0]["arxiv_id"] == "2010.11929"
        assert payload["items"][0]["document_id"] == "questpath::literature/arxiv/pdfs/2010.11929.pdf"
    finally:
        app.request_shutdown(source="test-daemon-http-arxiv-list")
        server_thread.join(timeout=10)
        assert not server_thread.is_alive()


def test_daemon_http_arxiv_import_route_passes_json_body(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=False)
    app._start_background_connectors = lambda: None  # type: ignore[method-assign]
    app._stop_background_connectors = lambda: None  # type: ignore[method-assign]
    app._start_terminal_attach_server = lambda host, port: None  # type: ignore[method-assign]
    app._stop_terminal_attach_server = lambda: None  # type: ignore[method-assign]

    quest = app.quest_service.create("arxiv http import quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    def fake_urlopen(request, timeout=8):  # noqa: ANN001
        url = request.full_url
        if "export.arxiv.org/api/query" in url:
            return _FakeUrlopenResponse(
                """
                <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
                  <entry>
                    <id>http://arxiv.org/abs/2010.11929</id>
                    <published>2020-10-23T17:54:00Z</published>
                    <title>Vision Transformers</title>
                    <summary>Vision Transformers apply pure transformer layers directly to image patches.</summary>
                    <author><name>Dosovitskiy, Alexey</name></author>
                    <arxiv:primary_category term="cs.CV" />
                    <category term="cs.CV" />
                  </entry>
                </feed>
                """
            )
        if url.endswith("/pdf/2010.11929.pdf"):
            return _FakeUrlopenResponse("%PDF-1.7\nfake pdf body")
        if url.endswith("/abs/2010.11929"):
            return _FakeUrlopenResponse(
                """
                <html>
                  <head>
                    <meta name="citation_title" content="Vision Transformers" />
                    <meta name="citation_author" content="Dosovitskiy, Alexey" />
                  </head>
                  <body>
                    <blockquote class="abstract mathjax">
                      <span class="descriptor">Abstract:</span>
                      Vision Transformers apply pure transformer layers directly to image patches.
                    </blockquote>
                  </body>
                </html>
                """
            )
        raise AssertionError(url)

    monkeypatch.setattr("deepscientist.artifact.arxiv.urlopen", fake_urlopen)
    monkeypatch.setattr("deepscientist.arxiv_library.urlopen", fake_urlopen)

    port = _pick_free_port()
    server_thread = threading.Thread(target=app.serve, args=("127.0.0.1", port), daemon=True)
    server_thread.start()
    try:
        _wait_for_json(f"http://127.0.0.1:{port}/api/health")
        request = Request(
            f"http://127.0.0.1:{port}/api/v1/arxiv/import",
            data=json.dumps({"project_id": quest_id, "arxiv_id": "2010.11929"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["arxiv_id"] == "2010.11929"
        assert payload["status"] in {"processing", "ready"}
        pdf_path = quest_root / "literature" / "arxiv" / "pdfs" / "2010.11929.pdf"
        for _ in range(40):
            if pdf_path.exists():
                break
            time.sleep(0.05)
        assert pdf_path.exists()
    finally:
        app.request_shutdown(source="test-daemon-http-arxiv-import")
        server_thread.join(timeout=10)
        assert not server_thread.is_alive()


def test_daemon_http_quest_file_mutation_routes(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=False)
    app._start_background_connectors = lambda: None  # type: ignore[method-assign]
    app._stop_background_connectors = lambda: None  # type: ignore[method-assign]
    app._start_terminal_attach_server = lambda host, port: None  # type: ignore[method-assign]
    app._stop_terminal_attach_server = lambda: None  # type: ignore[method-assign]

    quest = app.quest_service.create("http quest file mutations")
    quest_id = quest["quest_id"]

    port = _pick_free_port()
    server_thread = threading.Thread(target=app.serve, args=("127.0.0.1", port), daemon=True)
    server_thread.start()
    try:
        _wait_for_json(f"http://127.0.0.1:{port}/api/health")

        create_folder_request = Request(
            f"http://127.0.0.1:{port}/api/quests/{quest_id}/files/folder",
            data=json.dumps({"name": "uploads", "parent_path": "literature"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(create_folder_request) as response:  # noqa: S310
            created_folder = json.loads(response.read().decode("utf-8"))
        assert created_folder["ok"] is True
        assert created_folder["item"]["path"] == "literature/uploads"

        upload_request = Request(
            f"http://127.0.0.1:{port}/api/quests/{quest_id}/files/upload",
            data=json.dumps(
                {
                    "file_name": "notes.txt",
                    "parent_path": "literature/uploads",
                    "mime_type": "text/plain",
                    "content_base64": base64.b64encode(b"http upload\n").decode("ascii"),
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(upload_request) as response:  # noqa: S310
            uploaded = json.loads(response.read().decode("utf-8"))
        assert uploaded["ok"] is True
        assert uploaded["item"]["document_id"] == "path::literature/uploads/notes.txt"

        rename_request = Request(
            f"http://127.0.0.1:{port}/api/quests/{quest_id}/files/rename",
            data=json.dumps(
                {
                    "path": "literature/uploads/notes.txt",
                    "new_name": "renamed.md",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(rename_request) as response:  # noqa: S310
            renamed = json.loads(response.read().decode("utf-8"))
        assert renamed["ok"] is True
        assert renamed["item"]["path"] == "literature/uploads/renamed.md"

        move_request = Request(
            f"http://127.0.0.1:{port}/api/quests/{quest_id}/files/move",
            data=json.dumps(
                {
                    "paths": ["literature/uploads/renamed.md"],
                    "target_parent_path": "artifacts",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(move_request) as response:  # noqa: S310
            moved = json.loads(response.read().decode("utf-8"))
        assert moved["ok"] is True
        assert moved["items"][0]["path"] == "artifacts/renamed.md"

        delete_request = Request(
            f"http://127.0.0.1:{port}/api/quests/{quest_id}/files/delete",
            data=json.dumps({"paths": ["artifacts/renamed.md", "literature/uploads"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(delete_request) as response:  # noqa: S310
            deleted = json.loads(response.read().decode("utf-8"))
        assert deleted["ok"] is True
        assert sorted(item["path"] for item in deleted["items"]) == [
            "artifacts/renamed.md",
            "literature/uploads",
        ]

        explorer = _get_json(f"http://127.0.0.1:{port}/api/quests/{quest_id}/explorer")

        def flatten(nodes):  # noqa: ANN001
            items = []
            for node in nodes:
                items.append(node)
                items.extend(flatten(node.get("children") or []))
            return items

        flattened = []
        for section in explorer["sections"]:
            flattened.extend(flatten(section["nodes"]))
        paths = {item.get("path") for item in flattened}
        assert "artifacts/renamed.md" not in paths
        assert "literature/uploads" not in paths
    finally:
        app.request_shutdown(source="test-daemon-http-quest-file-mutations")
        server_thread.join(timeout=10)
        assert not server_thread.is_alive()


def test_handlers_unknown_quest_routes_return_404_without_materializing_dirs(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)

    quest_payload = app.handlers.quest("046")
    assert isinstance(quest_payload, tuple)
    assert quest_payload[0] == 404

    session_payload = app.handlers.quest_session("046")
    assert isinstance(session_payload, tuple)
    assert session_payload[0] == 404

    explorer_payload = app.handlers.explorer("046", "/api/quests/046/explorer")
    assert isinstance(explorer_payload, tuple)
    assert explorer_payload[0] == 404

    ghost_root = temp_home / "quests" / "046"
    assert not ghost_root.exists()


def test_handlers_annotations_roundtrip_for_quest_file(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("annotation roundtrip quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    pdf_path = quest_root / "docs" / "annotated.pdf"
    ensure_dir(pdf_path.parent)
    pdf_path.write_bytes(b"%PDF-1.7\nannotation test")

    document_id = "questpath::docs/annotated.pdf"
    file_id = f"quest-file::{quest_id}::{quote(document_id, safe='')}::{quote('docs/annotated.pdf', safe='')}"
    created = app.handlers.annotation_create(
        {
            "file_id": file_id,
            "position": {
                "pageNumber": 1,
                "boundingRect": {"x1": 10, "y1": 12, "x2": 34, "y2": 18, "width": 100, "height": 100},
                "rects": [{"x1": 10, "y1": 12, "x2": 34, "y2": 18, "width": 100, "height": 100}],
            },
            "content": {"text": "Vision Transformer"},
            "comment": "Key citation",
            "kind": "note",
            "tags": ["arxiv", "important"],
        }
    )
    assert created["file_id"] == file_id
    assert created["project_id"] == quest_id
    assert created["comment"] == "Key citation"

    listed = app.handlers.annotations_file(file_id)
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == created["id"]

    updated = app.handlers.annotation_update(created["id"], {"comment": "Updated note", "kind": "task"})
    assert updated["comment"] == "Updated note"
    assert updated["kind"] == "task"

    fetched = app.handlers.annotation_detail(created["id"])
    assert fetched["id"] == created["id"]
    assert fetched["comment"] == "Updated note"

    searched = app.handlers.annotations_project(quest_id, f"/api/v1/annotations/project/{quest_id}?q=updated")
    assert searched["total"] == 1
    assert searched["items"][0]["id"] == created["id"]

    deleted = app.handlers.annotation_delete(created["id"])
    assert deleted["ok"] is True

    empty = app.handlers.annotations_file(file_id)
    assert empty["total"] == 0


def test_daemon_http_annotations_routes_support_quest_file_ids(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=False)
    app._start_background_connectors = lambda: None  # type: ignore[method-assign]
    app._stop_background_connectors = lambda: None  # type: ignore[method-assign]
    app._start_terminal_attach_server = lambda host, port: None  # type: ignore[method-assign]
    app._stop_terminal_attach_server = lambda: None  # type: ignore[method-assign]

    quest = app.quest_service.create("annotation http quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    pdf_path = quest_root / "docs" / "annotated.pdf"
    ensure_dir(pdf_path.parent)
    pdf_path.write_bytes(b"%PDF-1.7\nannotation http test")
    document_id = "questpath::docs/annotated.pdf"
    file_id = f"quest-file::{quest_id}::{quote(document_id, safe='')}::{quote('docs/annotated.pdf', safe='')}"

    port = _pick_free_port()
    server_thread = threading.Thread(target=app.serve, args=("127.0.0.1", port), daemon=True)
    server_thread.start()
    try:
        _wait_for_json(f"http://127.0.0.1:{port}/api/health")
        create_request = Request(
            f"http://127.0.0.1:{port}/api/v1/annotations/",
            data=json.dumps(
                {
                    "file_id": file_id,
                    "position": {
                        "pageNumber": 1,
                        "boundingRect": {"x1": 1, "y1": 2, "x2": 20, "y2": 8, "width": 100, "height": 100},
                        "rects": [{"x1": 1, "y1": 2, "x2": 20, "y2": 8, "width": 100, "height": 100}],
                    },
                    "content": {"text": "HTTP annotation"},
                    "comment": "from http",
                    "kind": "question",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(create_request) as response:  # noqa: S310
            created = json.loads(response.read().decode("utf-8"))

        list_url = f"http://127.0.0.1:{port}/api/v1/annotations/file/{file_id}"
        listed = _get_json(list_url)
        assert listed["total"] == 1
        assert listed["items"][0]["id"] == created["id"]

        patch_request = Request(
            f"http://127.0.0.1:{port}/api/v1/annotations/{created['id']}",
            data=json.dumps({"comment": "patched"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PATCH",
        )
        with urlopen(patch_request) as response:  # noqa: S310
            patched = json.loads(response.read().decode("utf-8"))
        assert patched["comment"] == "patched"

        delete_request = Request(
            f"http://127.0.0.1:{port}/api/v1/annotations/{created['id']}",
            method="DELETE",
        )
        with urlopen(delete_request) as response:  # noqa: S310
            deleted = json.loads(response.read().decode("utf-8"))
        assert deleted["ok"] is True
    finally:
        app.request_shutdown(source="test-daemon-http-annotations")
        server_thread.join(timeout=10)
        assert not server_thread.is_alive()


def test_ui_root_shows_build_instructions_when_bundle_missing(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    monkeypatch.setattr(app.handlers, "_ui_dist_root", lambda: None)

    status, headers, html = app.handlers.root()

    assert status == 200
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert "DeepScientist UI bundle is not built yet" in html
    assert "npm --prefix src/ui run build" in html


def test_ui_asset_prefers_explicit_javascript_mime_over_platform_guess(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)

    dist_root = temp_home / "fake-ui-dist"
    assets_root = dist_root / "assets"
    assets_root.mkdir(parents=True, exist_ok=True)
    (dist_root / "index.html").write_text("<!doctype html><html><body>ok</body></html>", encoding="utf-8")
    (assets_root / "index-test.js").write_text("console.log('ok')\n", encoding="utf-8")
    (assets_root / "worker-test.mjs").write_text("export const value = 1\n", encoding="utf-8")

    original_guess_type = daemon_api_handlers.mimetypes.guess_type

    def _fake_guess_type(url: str, strict: bool = True):
        normalized = str(url)
        if normalized.endswith(".js") or normalized.endswith(".mjs"):
            return ("text/plain", None)
        return original_guess_type(url, strict=strict)

    monkeypatch.setattr(app.handlers, "_ui_dist_root", lambda: dist_root)
    monkeypatch.setattr(daemon_api_handlers.mimetypes, "guess_type", _fake_guess_type)

    status, headers, body = app.handlers.ui_asset("assets/index-test.js")
    assert status == 200
    assert headers["Content-Type"] == "text/javascript"
    assert body.startswith(b"console.log")

    status, headers, body = app.handlers.ui_asset("assets/worker-test.mjs")
    assert status == 200
    assert headers["Content-Type"] == "text/javascript"
    assert body.startswith(b"export const")


def test_health_reports_daemon_identity(monkeypatch: pytest.MonkeyPatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    monkeypatch.setenv("DS_DAEMON_ID", "daemon-test-001")
    monkeypatch.setenv("DS_DAEMON_MANAGED_BY", "ds-launcher")
    app = DaemonApp(temp_home)

    payload = app.handlers.health()

    assert payload["status"] == "ok"
    assert payload["home"] == str(temp_home.resolve())
    assert payload["daemon_id"] == "daemon-test-001"
    assert payload["managed_by"] == "ds-launcher"
    assert isinstance(payload["pid"], int)


def test_admin_shutdown_rejects_daemon_identity_mismatch(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)

    payload = app.handlers.admin_shutdown({"source": "pytest", "daemon_id": "wrong-daemon-id"})

    assert payload["ok"] is False
    assert "identity mismatch" in str(payload["message"]).lower()
    assert app._shutdown_requested.is_set() is False


def test_router_matches_spa_project_paths() -> None:
    route_name, params = match_route("GET", "/projects/q-123456")

    assert route_name == "spa_root"
    assert params["spa_path"] == "projects/q-123456"


def test_router_matches_quest_search_path() -> None:
    route_name, params = match_route("GET", "/api/quests/q-123456/search")

    assert route_name == "quest_search"
    assert params["quest_id"] == "q-123456"


def test_quest_create_handler_auto_binds_recent_connector_to_newest_quest(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    config = manager.load_named("config")
    config["connectors"]["system_enabled"]["whatsapp"] = True
    write_yaml(manager.path_for("config"), config)
    connectors = manager.load_named("connectors")
    connectors["whatsapp"]["enabled"] = True
    connectors["whatsapp"]["auto_bind_dm_to_active_quest"] = True
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
    assert "/use" in first["reply"]["payload"]["text"]
    assert app.list_connector_bindings("whatsapp") == []

    payload = app.handlers.quest_create({"goal": "daemon api connector bind quest", "source": "web", "auto_start": True})

    assert payload["ok"] is True
    quest_id = payload["snapshot"]["quest_id"]
    bindings = app.list_connector_bindings("whatsapp")
    assert any(item["conversation_id"] == "whatsapp:direct:+15550001111" and item["quest_id"] == quest_id for item in bindings)
    outbox = read_jsonl(temp_home / "logs" / "connectors" / "whatsapp" / "outbox.jsonl")
    assert outbox
    assert outbox[-1]["conversation_id"] == "whatsapp:direct:+15550001111"
    assert quest_id in str(outbox[-1]["text"] or "")
    assert "自动使用这个新 quest 保持连接" in str(outbox[-1]["text"] or "")
    history = app.quest_service.history(quest_id)
    assert history
    assert history[-1]["content"] == "daemon api connector bind quest"
    assert history[-1]["source"] == "web"


def test_quest_create_handler_can_disable_auto_binding_recent_connector(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    config = manager.load_named("config")
    config["connectors"]["system_enabled"]["whatsapp"] = True
    write_yaml(manager.path_for("config"), config)
    connectors = manager.load_named("connectors")
    connectors["whatsapp"]["enabled"] = True
    connectors["whatsapp"]["auto_bind_dm_to_active_quest"] = True
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

    first = app.handle_connector_inbound(
        "whatsapp",
        {
            "chat_type": "direct",
            "sender_id": "+15550001112",
            "sender_name": "Researcher",
            "text": "Please summarize the latest result.",
        },
    )
    assert first["accepted"] is True
    assert app.list_connector_bindings("whatsapp") == []

    payload = app.handlers.quest_create(
        {
            "goal": "daemon api quest without auto connector binding",
            "source": "web",
            "auto_start": True,
            "auto_bind_latest_connectors": False,
        }
    )

    assert payload["ok"] is True
    quest_id = payload["snapshot"]["quest_id"]
    assert app.list_connector_bindings("whatsapp") == []
    history = app.quest_service.history(quest_id)
    assert history
    assert history[-1]["content"] == "daemon api quest without auto connector binding"
    assert history[-1]["source"] == "web"


def test_quest_create_handler_summary_includes_visible_quest_metadata(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)

    payload = app.handlers.quest_create(
        {
            "goal": "Summarize this quest.",
            "title": "Summary visible metadata quest",
            "quest_id": "summary-visible-metadata",
        }
    )

    assert isinstance(payload, dict)
    assert payload["ok"] is True
    summary = app._format_summary("summary-visible-metadata")
    assert "quest_id: summary-visible-metadata" in summary
    assert "title: Summary visible metadata quest" in summary


def test_quest_create_handler_copilot_workspace_starts_idle_and_waits_for_user(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)

    payload = app.handlers.quest_create(
        {
            "goal": "Copilot workspace quest",
            "title": "Copilot workspace quest",
            "startup_contract": {
                "workspace_mode": "copilot",
                "decision_policy": "user_gated",
                "launch_mode": "custom",
                "custom_profile": "freeform",
            },
            "auto_start": False,
        }
    )

    assert payload["ok"] is True
    snapshot = payload["snapshot"]
    assert snapshot["workspace_mode"] == "copilot"
    assert snapshot["continuation_policy"] == "wait_for_user_or_resume"
    assert snapshot["continuation_anchor"] == "decision"
    assert snapshot["continuation_reason"] == "copilot_mode"
    assert snapshot["runtime_status"] == "idle"
    assert snapshot["status"] == "idle"
    status_md = (temp_home / "quests" / snapshot["quest_id"] / "status.md").read_text(encoding="utf-8")
    assert "Ready for your first instruction." in status_md


def test_quest_settings_handler_updates_quest_yaml(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("settings quest")
    quest_id = quest["quest_id"]

    payload = app.handlers.quest_settings(
        quest_id,
        {
            "title": "Updated Quest Title",
            "active_anchor": "experiment",
            "default_runner": "codex",
        },
    )

    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert payload["snapshot"]["title"] == "Updated Quest Title"
    assert payload["snapshot"]["active_anchor"] == "experiment"
    assert payload["snapshot"]["runner"] == "codex"

    quest_yaml = read_yaml(temp_home / "quests" / quest_id / "quest.yaml", {})
    assert quest_yaml["title"] == "Updated Quest Title"
    assert quest_yaml["active_anchor"] == "experiment"
    assert quest_yaml["default_runner"] == "codex"


def test_quest_settings_handler_updates_workspace_mode_and_research_state(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("workspace mode settings quest")
    quest_id = quest["quest_id"]

    payload = app.handlers.quest_settings(
        quest_id,
        {
            "workspace_mode": "copilot",
        },
    )

    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert payload["snapshot"]["workspace_mode"] == "copilot"
    assert payload["snapshot"]["continuation_policy"] == "wait_for_user_or_resume"
    assert payload["snapshot"]["continuation_reason"] == "copilot_mode"

    quest_yaml = read_yaml(temp_home / "quests" / quest_id / "quest.yaml", {})
    startup_contract = dict(quest_yaml.get("startup_contract") or {})
    assert startup_contract["workspace_mode"] == "copilot"

    research_state = read_json(temp_home / "quests" / quest_id / ".ds" / "research_state.json", {})
    assert research_state["workspace_mode"] == "copilot"

    runtime_state = read_json(temp_home / "quests" / quest_id / ".ds" / "runtime_state.json", {})
    assert runtime_state["continuation_policy"] == "wait_for_user_or_resume"
    assert runtime_state["continuation_reason"] == "copilot_mode"


def test_quest_settings_switch_to_autonomous_injects_continue_without_replaying_stale_user_message(
    temp_home: Path,
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("workspace mode continue quest", startup_contract={"workspace_mode": "copilot"})
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    app.quest_service.update_research_state(quest_root, workspace_mode="copilot")
    app.quest_service.update_runtime_state(
        quest_root=quest_root,
        status="active",
        continuation_policy="wait_for_user_or_resume",
        continuation_reason="copilot_mode",
    )
    previous_message = app.quest_service.append_message(
        quest_id,
        role="user",
        content="Original task",
        source="web-react",
    )
    app.quest_service.claim_pending_user_message_for_turn(
        quest_id,
        message_id=str(previous_message.get("id") or ""),
        run_id="run-previous",
    )

    class ContinueRunner:
        binary = ""

        def __init__(self) -> None:
            self.requests: list[dict[str, str]] = []

        def run(self, request):
            self.requests.append(
                {
                    "message": request.message,
                    "turn_reason": request.turn_reason,
                }
            )
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text="continue ok",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    runner = ContinueRunner()
    app.runners["codex"] = runner

    payload = app.handlers.quest_settings(
        quest_id,
        {
            "workspace_mode": "autonomous",
        },
    )

    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert payload["snapshot"]["workspace_mode"] == "autonomous"
    assert payload["snapshot"]["continuation_policy"] == "auto"

    deadline = time.time() + 5
    while time.time() < deadline:
        if runner.requests:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("workspace mode switch did not schedule a continuation turn")

    assert runner.requests[0]["turn_reason"] == "user_message"
    assert runner.requests[0]["message"] == "Continue"
    assert runner.requests[0]["message"] != "Original task"

    history = app.quest_service.history(quest_id)
    assert any(item.get("role") == "user" and item.get("content") == "Continue" for item in history)


def test_quest_settings_handler_rejects_invalid_workspace_mode(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("invalid workspace mode quest")

    status_code, payload = app.handlers.quest_settings(
        quest["quest_id"],
        {
            "workspace_mode": "invalid-mode",
        },
    )

    assert status_code == 400
    assert payload["ok"] is False
    assert "workspace mode" in str(payload["message"]).lower()


def test_quest_settings_handler_rejects_invalid_anchor(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("invalid anchor quest")

    status_code, payload = app.handlers.quest_settings(
        quest["quest_id"],
        {
            "active_anchor": "not-a-skill",
        },
    )

    assert status_code == 400
    assert payload["ok"] is False
    assert "active anchor" in str(payload["message"]).lower()


def test_quest_next_id_handler_returns_next_sequential_numeric_id(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)

    assert app.handlers.quest_next_id() == {"quest_id": "001"}

    app.quest_service.create("first quest")

    assert app.handlers.quest_next_id() == {"quest_id": "002"}


def test_quest_bindings_handler_detects_conflicts_and_forces_rebind(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    first = app.quest_service.create("binding quest one")
    second = app.quest_service.create("binding quest two")
    first_id = first["quest_id"]
    second_id = second["quest_id"]
    conversation_id = "qq:direct:OPENID123"

    payload = app.handlers.quest_bindings(first_id, {"conversation_id": conversation_id, "force": True})
    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert payload["conversation_id"] == conversation_id

    status_code, conflict_payload = app.handlers.quest_bindings(second_id, {"conversation_id": conversation_id})
    assert status_code == 409
    assert conflict_payload["ok"] is False
    assert conflict_payload["conflict"] is True
    assert any(item["quest_id"] == first_id for item in conflict_payload["conflicts"])

    resolved = app.handlers.quest_bindings(second_id, {"conversation_id": conversation_id, "force": True})
    assert isinstance(resolved, dict)
    assert resolved["ok"] is True
    assert resolved["quest_id"] == second_id
    assert resolved["conversation_id"] == conversation_id

    first_sources = app.quest_service.binding_sources(first_id)
    assert conversation_id not in first_sources
    bindings = app.list_connector_bindings("qq")
    assert any(item["conversation_id"] == conversation_id and item["quest_id"] == second_id for item in bindings)


def test_quest_create_handler_rebinds_requested_connector_target_by_default(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    older = app.quest_service.create("older binding quest")
    older_id = older["quest_id"]
    conversation_id = "qq:direct:OPENID_REBIND_DEFAULT"

    initial = app.update_quest_binding(older_id, conversation_id, force=True)
    assert isinstance(initial, dict)
    assert initial["ok"] is True

    payload = app.handlers.quest_create(
        {
            "goal": "new quest should inherit requested qq binding",
            "source": "web",
            "requested_connector_bindings": [
                {
                    "connector": "qq",
                    "conversation_id": conversation_id,
                }
            ],
        }
    )

    assert isinstance(payload, dict)
    assert payload["ok"] is True
    newest_id = payload["snapshot"]["quest_id"]
    assert newest_id != older_id
    bindings = app.list_connector_bindings("qq")
    assert any(item["conversation_id"] == conversation_id and item["quest_id"] == newest_id for item in bindings)
    assert conversation_id not in app.quest_service.binding_sources(older_id)
    assert conversation_id in app.quest_service.binding_sources(newest_id)


def test_quest_delete_handler_removes_repo_and_unbinds_connectors(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("delete quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    conversation_id = "qq:direct:OPENID_DELETE"
    bound = app.update_quest_binding(quest_id, conversation_id, force=True)
    assert isinstance(bound, dict)
    assert bound["ok"] is True
    assert quest_root.exists()

    payload = app.handlers.quest_delete(quest_id, {"source": "pytest"})

    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert payload["deleted"] is True
    assert not quest_root.exists()
    assert all(item["conversation_id"] != conversation_id for item in app.list_connector_bindings("qq"))


def test_update_quest_binding_keeps_only_one_external_connector_per_quest(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("single external connector quest")
    quest_id = quest["quest_id"]

    first = app.update_quest_binding(quest_id, "qq:direct:OPENID_SINGLE", force=True)
    assert isinstance(first, dict)
    assert first["ok"] is True
    assert first["removed_conversations"] == []

    second = app.update_quest_binding(quest_id, "telegram:direct:tg-single", force=True)
    assert isinstance(second, dict)
    assert second["ok"] is True
    assert second["conversation_id"] == "telegram:direct:tg-single"
    assert second["removed_conversations"] == ["qq:direct:OPENID_SINGLE"]

    sources = app.quest_service.binding_sources(quest_id)
    assert sources == ["local:default", "telegram:direct:tg-single"]
    assert not any(item["conversation_id"] == "qq:direct:OPENID_SINGLE" for item in app.list_connector_bindings("qq"))
    assert any(item["conversation_id"] == "telegram:direct:tg-single" for item in app.list_connector_bindings("telegram"))


def test_quest_bindings_handler_announces_switch_to_old_and_new_connectors(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    config = manager.load_named("config")
    config["connectors"]["system_enabled"]["telegram"] = True
    write_yaml(manager.path_for("config"), config)
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["telegram"]["enabled"] = True
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("binding switch notifications")
    quest_id = quest["quest_id"]
    first = app.update_quest_binding(quest_id, "qq:direct:OPENID_SWITCH", force=True)
    assert isinstance(first, dict) and first["ok"] is True

    payload = app.handlers.quest_bindings(
        quest_id,
        {
            "connector": "telegram",
            "conversation_id": "telegram:direct:tg-switch",
            "force": True,
        },
    )

    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert payload["binding_transition"]["mode"] == "switch"
    qq_outbox = read_jsonl(temp_home / "logs" / "connectors" / "qq" / "outbox.jsonl")
    telegram_outbox = read_jsonl(temp_home / "logs" / "connectors" / "telegram" / "outbox.jsonl")
    assert any("已经从这里切走啦" in str(item.get("text") or "") for item in qq_outbox)
    assert any("已经切到这里啦" in str(item.get("text") or "") for item in telegram_outbox)


def test_auto_bind_does_not_override_existing_external_connector_without_explicit_switch(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    config = manager.load_named("config")
    config["connectors"]["system_enabled"]["telegram"] = True
    config["connectors"]["system_enabled"]["whatsapp"] = True
    write_yaml(manager.path_for("config"), config)
    connectors = manager.load_named("connectors")
    connectors["whatsapp"]["enabled"] = True
    connectors["whatsapp"]["auto_bind_dm_to_active_quest"] = True
    connectors["telegram"]["enabled"] = True
    connectors["telegram"]["auto_bind_dm_to_active_quest"] = True
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("no silent connector override")
    quest_id = quest["quest_id"]
    bound = app.update_quest_binding(quest_id, "whatsapp:direct:+15550001111", force=True)
    assert isinstance(bound, dict) and bound["ok"] is True

    response = app.handle_connector_inbound(
        "telegram",
        {
            "chat_type": "direct",
            "sender_id": "tg-user-1",
            "sender_name": "Telegram User",
            "text": "Please continue the current quest.",
        },
    )

    assert response["accepted"] is True
    assert app.quest_service.binding_sources(quest_id) == ["local:default", "whatsapp:direct:+15550001111"]
    assert app.list_connector_bindings("telegram") == []
    assert "/use" in str(response["reply"]["payload"]["text"] or "")


def test_update_quest_bindings_rejects_multiple_external_targets(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    config = manager.load_named("config")
    config["connectors"]["system_enabled"]["telegram"] = True
    write_yaml(manager.path_for("config"), config)
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("batch connector binding quest")
    quest_id = quest["quest_id"]

    result = app.update_quest_bindings(
        quest_id,
        [
            {"connector": "qq", "conversation_id": "qq:direct:OPENID_BATCH"},
            {"connector": "telegram", "conversation_id": "telegram:direct:tg-batch"},
        ],
        force=True,
    )
    assert isinstance(result, tuple)
    status, payload = result
    assert status == 400
    assert payload["ok"] is False
    assert payload["message"] == "A quest may bind at most one external connector target."
    assert app.quest_service.binding_sources(quest_id) == ["local:default"]


def test_bash_exec_handlers_expose_sessions_logs_and_stop(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("bash api quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    context = McpContext(
        home=temp_home,
        quest_id=quest_id,
        quest_root=quest_root,
        run_id="run-bash-api-001",
        active_anchor="experiment",
        conversation_id=f"quest:{quest_id}",
        agent_role="pi",
        worker_id="worker-main",
        worktree_root=None,
        team_mode="single",
    )

    session = app.bash_exec_service.start_session(
        context,
        command="printf 'alpha\\n'; sleep 5; printf 'omega\\n'",
        mode="detach",
    )
    bash_id = session["bash_id"]
    time.sleep(0.8)

    sessions = app.handlers.bash_sessions(quest_id, f"/api/quests/{quest_id}/bash/sessions")
    assert any(item["bash_id"] == bash_id for item in sessions)
    exec_sessions = app.handlers.bash_sessions(quest_id, f"/api/quests/{quest_id}/bash/sessions?kind=exec")
    assert any(item["bash_id"] == bash_id for item in exec_sessions)

    detail = app.handlers.bash_session(quest_id, bash_id)
    assert isinstance(detail, dict)
    assert detail["bash_id"] == bash_id

    status, headers, payload = app.handlers.bash_logs(
        quest_id,
        bash_id,
        f"/api/quests/{quest_id}/bash/sessions/{bash_id}/logs?limit=20",
    )
    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    entries = json.loads(payload.decode("utf-8"))
    assert any("alpha" in str(entry.get("line") or "") for entry in entries)
    latest_seq = int(headers["X-Bash-Log-Latest-Seq"] or 0)
    status2, _headers2, payload2 = app.handlers.bash_logs(
        quest_id,
        bash_id,
        f"/api/quests/{quest_id}/bash/sessions/{bash_id}/logs?limit=20&after_seq={latest_seq}",
    )
    assert status2 == 200
    assert isinstance(json.loads(payload2.decode("utf-8")), list)

    stop_payload = app.handlers.bash_stop(quest_id, bash_id, {"reason": "pytest-stop", "force": True, "wait": True, "timeout_seconds": 10})
    assert isinstance(stop_payload, dict)
    assert stop_payload["success"] is True
    assert stop_payload["status"] == "terminated"

    final = app.bash_exec_service.wait_for_session(quest_root, bash_id, timeout_seconds=10)
    assert final["status"] == "terminated"


def test_terminal_handlers_ensure_input_restore_and_stop(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("terminal api quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    ensured = app.handlers.terminal_session_ensure(
        quest_id,
        {
            "source": "pytest",
            "conversation_id": f"quest:{quest_id}:pytest",
            "user_id": "user:pytest",
        },
    )
    assert ensured["ok"] is True
    session = ensured["session"]
    assert session["bash_id"] == "terminal-main"
    assert session["kind"] == "terminal"
    assert session["status"] == "running"

    deadline = time.time() + 6
    saw_prompt = False
    while time.time() < deadline:
        entries, _meta = app.bash_exec_service.read_log_entries(quest_root, "terminal-main", limit=200, order="asc")
        if any(
            entry.get("stream") == "partial"
            and str(quest_root) in str(entry.get("line") or "")
            and str(entry.get("line") or "").endswith("$ ")
            for entry in entries
        ):
            saw_prompt = True
            assert not any(str(entry.get("line") or "").startswith("bash-") for entry in entries)
            break
        time.sleep(0.2)
    assert saw_prompt is True

    partial_input = app.handlers.terminal_input(
        quest_id,
        "terminal-main",
        {
            "data": "abc",
            "source": "pytest",
            "conversation_id": f"quest:{quest_id}:pytest",
            "user_id": "user:pytest",
        },
    )
    assert isinstance(partial_input, dict)
    assert partial_input["ok"] is True
    assert partial_input["completed_commands"] == []

    deadline = time.time() + 6
    saw_partial_echo = False
    while time.time() < deadline:
        entries, _meta = app.bash_exec_service.read_log_entries(quest_root, "terminal-main", limit=200, order="asc")
        if any(entry.get("stream") == "partial" and "abc" in str(entry.get("line") or "") for entry in entries):
            saw_partial_echo = True
            break
        time.sleep(0.1)
    assert saw_partial_echo is True

    clear_input = app.handlers.terminal_input(
        quest_id,
        "terminal-main",
        {
            "data": "\x7f\x7f\x7f",
            "source": "pytest",
            "conversation_id": f"quest:{quest_id}:pytest",
            "user_id": "user:pytest",
        },
    )
    assert isinstance(clear_input, dict)
    assert clear_input["ok"] is True
    assert clear_input["completed_commands"] == []

    accepted = app.handlers.terminal_input(
        quest_id,
        "terminal-main",
        {
            "data": "pwd\n",
            "source": "pytest",
            "conversation_id": f"quest:{quest_id}:pytest",
            "user_id": "user:pytest",
        },
    )
    assert isinstance(accepted, dict)
    assert accepted["ok"] is True
    assert accepted["completed_commands"][-1]["command"] == "pwd"

    deadline = time.time() + 6
    saw_pwd = False
    while time.time() < deadline:
        entries, _meta = app.bash_exec_service.read_log_entries(quest_root, "terminal-main", limit=200, order="asc")
        if any(str(entry.get("line") or "").strip() == str(quest_root) for entry in entries):
            saw_pwd = True
            break
        time.sleep(0.2)
    assert saw_pwd is True

    restored = app.handlers.terminal_restore(
        quest_id,
        "terminal-main",
        f"/api/quests/{quest_id}/terminal/sessions/terminal-main/restore?commands=10&output=40",
    )
    assert isinstance(restored, dict)
    assert restored["ok"] is True
    assert restored["session_id"] == "terminal-main"
    assert restored["cwd"] == str(quest_root)
    assert any(item["command"] == "pwd" for item in restored["latest_commands"])

    history_payload = app.handlers.terminal_history(quest_id, f"/api/quests/{quest_id}/terminal/history?limit=20")
    assert history_payload["ok"] is True
    assert history_payload["default_session_id"] == "terminal-main"
    assert any(item["bash_id"] == "terminal-main" for item in history_payload["terminal_sessions"])

    stop_payload = app.handlers.bash_stop(quest_id, "terminal-main", {"reason": "pytest-stop"})
    assert isinstance(stop_payload, dict)
    assert stop_payload["success"] is True

    final = app.bash_exec_service.wait_for_session(quest_root, "terminal-main", timeout_seconds=10)
    assert final["status"] == "terminated"


def test_terminal_handlers_create_new_terminal_session(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("multi terminal api quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    ensured_main = app.handlers.terminal_session_ensure(
        quest_id,
        {
            "source": "pytest",
            "conversation_id": f"quest:{quest_id}:pytest",
            "user_id": "user:pytest",
        },
    )
    assert ensured_main["ok"] is True
    assert ensured_main["session"]["bash_id"] == "terminal-main"

    created = app.handlers.terminal_session_ensure(
        quest_id,
        {
            "source": "pytest",
            "conversation_id": f"quest:{quest_id}:pytest",
            "user_id": "user:pytest",
            "create_new": True,
            "label": "Scratch",
        },
    )
    assert created["ok"] is True
    created_session = created["session"]
    created_id = str(created_session.get("bash_id") or "")
    assert created_id
    assert created_id != "terminal-main"
    assert created_session.get("kind") == "terminal"
    assert created_session.get("label") == "Scratch"

    accepted = app.handlers.terminal_input(
        quest_id,
        created_id,
        {
            "data": "echo hello\n",
            "source": "pytest",
            "conversation_id": f"quest:{quest_id}:pytest",
            "user_id": "user:pytest",
        },
    )
    assert isinstance(accepted, dict)
    assert accepted["ok"] is True

    deadline = time.time() + 6
    saw_hello = False
    while time.time() < deadline:
        entries, _meta = app.bash_exec_service.read_log_entries(quest_root, created_id, limit=200, order="asc")
        if any("hello" in str(entry.get("line") or "") for entry in entries):
            saw_hello = True
            break
        time.sleep(0.2)
    assert saw_hello is True

    history_payload = app.handlers.terminal_history(quest_id, f"/api/quests/{quest_id}/terminal/history?limit=50")
    assert history_payload["ok"] is True
    assert any(item["bash_id"] == created_id for item in history_payload["terminal_sessions"])

    stop_created = app.handlers.bash_stop(quest_id, created_id, {"reason": "pytest-stop"})
    assert isinstance(stop_created, dict)
    assert stop_created["success"] is True
    stop_main = app.handlers.bash_stop(quest_id, "terminal-main", {"reason": "pytest-stop"})
    assert isinstance(stop_main, dict)
    assert stop_main["success"] is True

    final_created = app.bash_exec_service.wait_for_session(quest_root, created_id, timeout_seconds=10)
    assert final_created["status"] == "terminated"
    final_main = app.bash_exec_service.wait_for_session(quest_root, "terminal-main", timeout_seconds=10)
    assert final_main["status"] == "terminated"


def test_terminal_attach_websocket_smoke_supports_live_python_io(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    app._start_terminal_attach_server("127.0.0.1", 0)
    quest_root: Path | None = None
    try:
        quest = app.quest_service.create("terminal attach smoke")
        quest_id = quest["quest_id"]
        quest_root = Path(quest["quest_root"])
        ensured = app.handlers.terminal_session_ensure(
            quest_id,
            {
                "source": "pytest",
                "conversation_id": f"quest:{quest_id}:pytest",
                "user_id": "user:pytest",
            },
        )
        assert ensured["ok"] is True
        attach = app.handlers.terminal_attach(quest_id, "terminal-main", {})
        assert isinstance(attach, dict)
        assert attach["ok"] is True
        ws_url = f"ws://127.0.0.1:{attach['port']}{attach['path']}?token={attach['token']}"
        with websocket_connect(ws_url, open_timeout=5, close_timeout=2, max_size=None) as websocket:
            def _read_until_ready(*, timeout: float = 5.0) -> dict[str, object]:
                deadline = time.time() + timeout
                while time.time() < deadline:
                    try:
                        message = websocket.recv(timeout=1)
                    except TimeoutError:
                        continue
                    if isinstance(message, bytes):
                        continue
                    try:
                        payload = json.loads(message)
                    except Exception:
                        continue
                    if isinstance(payload, dict) and payload.get("type") == "ready":
                        return payload
                raise AssertionError("Timed out waiting for terminal ready frame.")

            ready = _read_until_ready()
            assert ready["type"] == "ready"

            def _read_until_contains(needle: str, *, timeout: float = 10.0) -> str:
                deadline = time.time() + timeout
                chunks: list[str] = []
                while time.time() < deadline:
                    try:
                        message = websocket.recv(timeout=1)
                    except TimeoutError:
                        continue
                    if isinstance(message, bytes):
                        chunks.append(message.decode("utf-8", errors="replace"))
                    else:
                        try:
                            payload = json.loads(message)
                        except Exception:
                            chunks.append(str(message))
                            if needle in "".join(chunks):
                                return "".join(chunks)
                            continue
                        if payload.get("type") == "exit":
                            break
                        continue
                    joined = "".join(chunks)
                    if needle in joined:
                        return joined
                raise AssertionError(
                    f"Timed out waiting for terminal output containing {needle!r}. Collected: {''.join(chunks)!r}"
                )

            websocket.send(json.dumps({"type": "input", "data": "python\n"}))
            _read_until_contains("Type \"help\"")
            websocket.send(json.dumps({"type": "input", "data": "print(123)\n"}))
            _read_until_contains("123")
            websocket.send(json.dumps({"type": "input", "data": "exit()\n"}))
            _read_until_contains("$ ")
            websocket.send(json.dumps({"type": "input", "data": "nano ds_smoke.txt\n"}))
            _read_until_contains("GNU nano", timeout=8)
            websocket.send(json.dumps({"type": "input", "data": "hello nano"}))
            websocket.send(json.dumps({"type": "input", "data": "\u0018"}))
            _read_until_contains("Save modified buffer", timeout=8)

        history = read_jsonl(app.bash_exec_service.history_path(quest_root, "terminal-main"))
        commands = [str(item.get("command") or "") for item in history]
        assert "python" in commands
        assert "print(123)" in commands
        assert "exit()" in commands
        assert "nano ds_smoke.txt" in commands
    finally:
        try:
            if quest_root is not None:
                app.bash_exec_service.request_stop(quest_root, "terminal-main", reason="pytest-stop")
        except Exception:
            pass
        app._stop_terminal_attach_server()
        app.bash_exec_service.shutdown()


def test_exec_bash_session_attach_websocket_supports_live_input_and_output(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    app._start_terminal_attach_server("127.0.0.1", 0)
    quest_root: Path | None = None
    bash_id: str | None = None
    try:
        quest = app.quest_service.create("exec attach smoke")
        quest_id = quest["quest_id"]
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest_id,
            quest_root=quest_root,
            run_id="run-exec-attach",
            active_anchor="experiment",
            conversation_id=f"quest:{quest_id}:pytest",
            agent_role="pi",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )

        session = app.bash_exec_service.start_session(
            context,
            command="python -i",
            mode="detach",
        )
        bash_id = session["bash_id"]

        deadline = time.time() + 5
        attach: dict | tuple[int, dict] | None = None
        while time.time() < deadline:
            attach = app.handlers.terminal_attach(quest_id, bash_id, {})
            if isinstance(attach, dict) and attach.get("ok") is True:
                break
            time.sleep(0.1)
        assert isinstance(attach, dict)
        assert attach["ok"] is True
        assert attach["session"]["kind"] == "exec"

        ws_url = f"ws://127.0.0.1:{attach['port']}{attach['path']}?token={attach['token']}"
        with websocket_connect(ws_url, open_timeout=5, close_timeout=2, max_size=None) as websocket:
            ready = json.loads(websocket.recv())
            assert ready["type"] == "ready"
            assert ready["bash_id"] == bash_id

            def _read_until_contains(needle: str, *, timeout: float = 10.0) -> str:
                deadline = time.time() + timeout
                chunks: list[str] = []
                while time.time() < deadline:
                    try:
                        message = websocket.recv(timeout=1)
                    except TimeoutError:
                        continue
                    if isinstance(message, bytes):
                        chunks.append(message.decode("utf-8", errors="replace"))
                    else:
                        try:
                            payload = json.loads(message)
                        except Exception:
                            chunks.append(str(message))
                            if needle in "".join(chunks):
                                return "".join(chunks)
                            continue
                        if payload.get("type") == "exit":
                            break
                        continue
                    joined = "".join(chunks)
                    if needle in joined:
                        return joined
                raise AssertionError(
                    f"Timed out waiting for exec attach output containing {needle!r}. Collected: {''.join(chunks)!r}"
                )

            _read_until_contains("Type \"help\"")
            websocket.send(json.dumps({"type": "input", "data": "print(123)\n"}))
            _read_until_contains("123")
            websocket.send(json.dumps({"type": "input", "data": "exit()\n"}))

        final = app.bash_exec_service.wait_for_session(quest_root, bash_id, timeout_seconds=10)
        assert final["status"] == "completed"
    finally:
        try:
            if quest_root is not None and bash_id:
                app.bash_exec_service.request_stop(quest_root, bash_id, reason="pytest-stop")
        except Exception:
            pass
        app._stop_terminal_attach_server()
        app.bash_exec_service.shutdown()


def test_chat_endpoint_schedules_background_runner(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("background run quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    class FakeRunner:
        binary = ""

        def run(self, request):
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            append_jsonl(
                request.quest_root / ".ds" / "events.jsonl",
                {
                    "event_id": generate_id("evt"),
                    "type": "runner.delta",
                    "quest_id": request.quest_id,
                    "run_id": request.run_id,
                    "source": "codex",
                    "skill_id": request.skill_id,
                    "text": "Drafting response…",
                    "created_at": utc_now(),
                },
            )
            append_jsonl(
                request.quest_root / ".ds" / "events.jsonl",
                {
                    "event_id": generate_id("evt"),
                    "type": "runner.turn_finish",
                    "quest_id": request.quest_id,
                    "run_id": request.run_id,
                    "source": "codex",
                    "skill_id": request.skill_id,
                    "model": request.model,
                    "exit_code": 0,
                    "summary": "Auto reply from background runner.",
                    "created_at": utc_now(),
                },
            )
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text="Auto reply from background runner.",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    app.runners["codex"] = FakeRunner()

    payload = app.handlers.chat(quest_id, {"text": "Please continue.", "source": "tui-ink"})

    assert payload["ok"] is True
    assert payload["scheduled"] is True
    assert payload["started"] is True

    deadline = time.time() + 3
    while time.time() < deadline:
        history = app.quest_service.history(quest_id)
        if any(item.get("role") == "assistant" and item.get("content") == "Auto reply from background runner." for item in history):
            break
        time.sleep(0.05)
    else:
        raise AssertionError("assistant reply was not appended after chat submission")

    events = app.handlers.quest_events(
        quest_id,
        path=f"/api/quests/{quest_id}/events?format=acp&session_id=session:test",
    )
    updates = [item["params"]["update"] for item in events["acp_updates"]]

    assert any(
        update["kind"] == "message" and (update.get("message") or {}).get("content") == "Please continue."
        for update in updates
    )
    assert any(
        update["kind"] == "message" and (update.get("message") or {}).get("content") == "Auto reply from background runner."
        for update in updates
    )
    assert any(
        update["kind"] == "event" and (update.get("data") or {}).get("label") == "run_finished"
        for update in updates
    )
    deadline = time.time() + 3
    while time.time() < deadline:
        if app.quest_service.snapshot(quest_id)["status"] == "active":
            break
        time.sleep(0.05)
    else:
        raise AssertionError("quest status did not settle back to active after the background turn")
    assert quest_root.exists()


def test_quest_events_stream_large_jsonl_without_full_cache(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("large events quest")
    quest_id = quest["quest_id"]
    events_path = Path(quest["quest_root"]) / ".ds" / "events.jsonl"
    events_path.write_text("", encoding="utf-8")
    monkeypatch.setattr("deepscientist.quest.service._JSONL_CACHE_MAX_BYTES", 512)

    for index in range(30):
        append_jsonl(
            events_path,
            {
                "event_id": f"evt-large-{index}",
                "type": "runner.delta",
                "quest_id": quest_id,
                "run_id": f"run-{index // 5}",
                "text": f"payload-{index}-" + ("x" * 300),
                "created_at": utc_now(),
            },
        )

    tail_payload = app.quest_service.events(quest_id, tail=True, limit=5)
    assert [item["event_id"] for item in tail_payload["events"]] == [
        "evt-large-25",
        "evt-large-26",
        "evt-large-27",
        "evt-large-28",
        "evt-large-29",
    ]

    after_payload = app.quest_service.events(quest_id, after=27, limit=2)
    assert [item["event_id"] for item in after_payload["events"]] == [
        "evt-large-27",
        "evt-large-28",
    ]

    cache_key = str(events_path.resolve())
    assert cache_key not in app.quest_service._jsonl_cache


def test_start_setup_session_turn_finish_settles_snapshot_and_session_even_without_form_patch(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create(
        "setup session finish quest",
        startup_contract={
            "workspace_mode": "copilot",
            "launch_mode": "custom",
            "custom_profile": "freeform",
            "start_setup_session": {
                "source": "benchstore",
                "locale": "zh",
                "suggested_form": {
                    "title": "Setup draft title",
                    "goal": "Prepare the launch form.",
                },
            },
        },
    )
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    class FakeRunner:
        binary = ""

        def run(self, request):
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            append_jsonl(
                request.quest_root / ".ds" / "events.jsonl",
                {
                    "event_id": generate_id("evt"),
                    "type": "runner.agent_message",
                    "quest_id": request.quest_id,
                    "run_id": request.run_id,
                    "source": "codex",
                    "skill_id": request.skill_id,
                    "text": "已经判断完毕：当前信息足够，但这次不再提交新的表单 patch。",
                    "created_at": utc_now(),
                },
            )
            append_jsonl(
                request.quest_root / ".ds" / "events.jsonl",
                {
                    "event_id": generate_id("evt"),
                    "type": "runner.turn_finish",
                    "quest_id": request.quest_id,
                    "run_id": request.run_id,
                    "source": "codex",
                    "skill_id": request.skill_id,
                    "model": request.model,
                    "exit_code": 0,
                    "summary": "SetupAgent finished without emitting a new form patch.",
                    "created_at": utc_now(),
                },
            )
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text="SetupAgent finished without emitting a new form patch.",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    app.runners["codex"] = FakeRunner()

    payload = app.handlers.chat(
        quest_id,
        {
            "text": "请继续整理 setup，必要时可以只回答，不用提交新的 patch。",
            "source": "web-react",
        },
    )

    assert payload["ok"] is True
    assert payload["started"] is True

    deadline = time.time() + 3
    while time.time() < deadline:
        snapshot = app.quest_service.snapshot(quest_id)
        if snapshot["status"] == "active" and snapshot["active_run_id"] is None:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("setup session did not settle back to active after finishing")

    events = app.handlers.quest_events(
        quest_id,
        path=f"/api/quests/{quest_id}/events?format=acp&session_id=session:test",
    )
    updates = [item["params"]["update"] for item in events["acp_updates"]]
    assert any(
        update["kind"] == "event" and (update.get("data") or {}).get("label") == "run_finished"
        for update in updates
    )

    session = app.handlers.quest_session(quest_id)
    assert session["snapshot"]["active_run_id"] is None
    assert session["snapshot"]["runtime_status"] == "active"
    assert session["snapshot"]["status"] == "active"

    quest_yaml = read_yaml(quest_root / "quest.yaml", {})
    assert quest_yaml.get("active_run_id") is None
    runtime_state = read_json(quest_root / ".ds" / "runtime_state.json", {})
    assert runtime_state["active_run_id"] is None
    assert runtime_state["status"] == "active"


def test_start_setup_session_http_session_and_events_expose_finish_without_form_patch(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=False)
    app._start_background_connectors = lambda: None  # type: ignore[method-assign]
    app._stop_background_connectors = lambda: None  # type: ignore[method-assign]
    app._start_terminal_attach_server = lambda host, port: None  # type: ignore[method-assign]
    app._stop_terminal_attach_server = lambda: None  # type: ignore[method-assign]
    quest = app.quest_service.create(
        "setup session http finish quest",
        startup_contract={
            "workspace_mode": "copilot",
            "launch_mode": "custom",
            "custom_profile": "freeform",
            "start_setup_session": {
                "source": "benchstore",
                "locale": "zh",
                "suggested_form": {
                    "title": "HTTP setup draft title",
                    "goal": "Prepare the launch form over HTTP.",
                },
            },
        },
    )
    quest_id = quest["quest_id"]

    class FakeRunner:
        binary = ""

        def run(self, request):
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            append_jsonl(
                request.quest_root / ".ds" / "events.jsonl",
                {
                    "event_id": generate_id("evt"),
                    "type": "runner.agent_message",
                    "quest_id": request.quest_id,
                    "run_id": request.run_id,
                    "source": "codex",
                    "skill_id": request.skill_id,
                    "text": "HTTP setup agent concluded without emitting a new form patch.",
                    "created_at": utc_now(),
                },
            )
            append_jsonl(
                request.quest_root / ".ds" / "events.jsonl",
                {
                    "event_id": generate_id("evt"),
                    "type": "runner.turn_finish",
                    "quest_id": request.quest_id,
                    "run_id": request.run_id,
                    "source": "codex",
                    "skill_id": request.skill_id,
                    "model": request.model,
                    "exit_code": 0,
                    "summary": "HTTP setup turn finished without form patch.",
                    "created_at": utc_now(),
                },
            )
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text="HTTP setup turn finished without form patch.",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    app.runners["codex"] = FakeRunner()

    port = _pick_free_port()
    base_url = f"http://127.0.0.1:{port}"
    server_thread = threading.Thread(target=app.serve, args=("127.0.0.1", port), daemon=True)
    server_thread.start()
    try:
        _wait_for_http_ready(f"{base_url}/api/health")
        chat_request = Request(
            f"{base_url}/api/quests/{quest_id}/chat",
            data=json.dumps(
                {
                    "text": "请继续整理 setup，可以只回答不用补 patch。",
                    "source": "web-react",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        chat_payload = json.loads(urlopen(chat_request).read().decode("utf-8"))  # noqa: S310
        assert chat_payload["ok"] is True
        assert chat_payload["started"] is True

        deadline = time.time() + 3
        session_payload = None
        while time.time() < deadline:
            candidate = _get_json(f"{base_url}/api/quests/{quest_id}/session")
            if candidate["snapshot"]["status"] == "active" and candidate["snapshot"]["active_run_id"] is None:
                session_payload = candidate
                break
            time.sleep(0.05)
        assert session_payload is not None
        assert session_payload["snapshot"]["runtime_status"] == "active"
        assert session_payload["snapshot"]["active_run_id"] is None

        events_payload = _get_json(f"{base_url}/api/quests/{quest_id}/events?format=acp&session_id=quest:{quest_id}")
        updates = [item["params"]["update"] for item in events_payload["acp_updates"]]
        assert any(
            update["kind"] == "event" and (update.get("data") or {}).get("label") == "run_finished"
            for update in updates
        )
    finally:
        app.request_shutdown(source="test-start-setup-http-finish")
        server_thread.join(timeout=10)


def test_quest_create_with_requested_baseline_attaches_materializes_and_confirms(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    source = app.quest_service.create("source baseline quest")
    source_root = Path(source["quest_root"])
    baseline_root = source_root / "baselines" / "local" / "demo-baseline"
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Demo baseline\n", encoding="utf-8")

    ArtifactService(temp_home).confirm_baseline(
        source_root,
        baseline_path=str(baseline_root),
        baseline_id="demo-baseline",
        summary="Source baseline confirmed",
        metric_contract={
            "primary_metric_id": "acc",
            "metrics": [{"metric_id": "acc", "direction": "higher"}],
        },
        metrics_summary={"acc": 0.91},
        primary_metric={"name": "acc", "value": 0.91},
    )

    payload = app.handlers.quest_create(
        {
            "goal": "Reuse the confirmed baseline and continue from there.",
            "title": "Baseline reuse quest",
            "quest_id": "quest-with-bound-baseline",
            "requested_baseline_ref": {
                "baseline_id": "demo-baseline",
            },
            "startup_contract": {
                "scope": "baseline_only",
                "baseline_mode": "existing",
            },
        }
    )

    assert isinstance(payload, dict)
    assert payload["ok"] is True
    snapshot = payload["snapshot"]
    assert snapshot["quest_id"] == "quest-with-bound-baseline"
    assert snapshot["baseline_gate"] == "confirmed"
    assert snapshot["requested_baseline_ref"]["baseline_id"] == "demo-baseline"
    assert snapshot["startup_contract"]["scope"] == "baseline_only"
    assert snapshot["confirmed_baseline_ref"]["baseline_id"] == "demo-baseline"
    assert snapshot["confirmed_baseline_ref"]["baseline_root_rel_path"] == "baselines/imported/demo-baseline"
    assert (Path(snapshot["quest_root"]) / "baselines" / "imported" / "demo-baseline" / "README.md").exists()


def test_quest_create_fails_fast_when_requested_baseline_cannot_materialize(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    app.artifact_service.baselines.publish(
        {
            "baseline_id": "missing-baseline",
            "summary": "Broken baseline entry",
            "path": str(temp_home / "missing-baseline-root"),
        }
    )

    payload = app.handlers.quest_create(
        {
            "goal": "Try to reuse a missing baseline.",
            "title": "Should fail",
            "quest_id": "quest-should-fail-baseline-bootstrap",
            "requested_baseline_ref": {
                "baseline_id": "missing-baseline",
            },
        }
    )

    assert isinstance(payload, tuple)
    status, body = payload
    assert status == 409
    assert body["ok"] is False
    assert "requested baseline `missing-baseline`" in str(body["message"])
    assert not (temp_home / "quests" / "quest-should-fail-baseline-bootstrap").exists()


def test_baseline_delete_handler_clears_registry_and_bound_quests(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    source = app.quest_service.create("source baseline quest")
    source_root = Path(source["quest_root"])
    baseline_root = source_root / "baselines" / "local" / "demo-baseline"
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Demo baseline\n", encoding="utf-8")

    ArtifactService(temp_home).confirm_baseline(
        source_root,
        baseline_path=str(baseline_root),
        baseline_id="demo-baseline",
        summary="Source baseline confirmed",
        metrics_summary={"acc": 0.91},
        primary_metric={"name": "acc", "value": 0.91},
    )

    created = app.handlers.quest_create(
        {
            "goal": "Reuse the confirmed baseline and continue from there.",
            "title": "Baseline reuse quest",
            "quest_id": "quest-with-bound-baseline",
            "requested_baseline_ref": {
                "baseline_id": "demo-baseline",
            },
        }
    )
    assert isinstance(created, dict)
    target_root = Path(created["snapshot"]["quest_root"])
    assert baseline_root.exists()
    assert (target_root / "baselines" / "imported" / "demo-baseline").exists()

    deleted = app.handlers.baseline_delete("demo-baseline")

    assert isinstance(deleted, dict)
    assert deleted["ok"] is True
    assert deleted["baseline_id"] == "demo-baseline"
    assert sorted(deleted["affected_quest_ids"]) == sorted([source["quest_id"], "quest-with-bound-baseline"])
    assert deleted["cleared_requested_refs"] == 1
    assert deleted["cleared_confirmed_refs"] == 2
    assert app.handlers.baselines() == []
    assert not baseline_root.exists()
    assert not (target_root / "baselines" / "imported" / "demo-baseline").exists()

    source_snapshot = app.quest_service.snapshot(source["quest_id"])
    assert source_snapshot["baseline_gate"] == "pending"
    assert source_snapshot["confirmed_baseline_ref"] is None
    assert source_snapshot["active_baseline_id"] is None

    target_snapshot = app.quest_service.snapshot("quest-with-bound-baseline")
    assert target_snapshot["baseline_gate"] == "pending"
    assert target_snapshot["requested_baseline_ref"] is None
    assert target_snapshot["confirmed_baseline_ref"] is None
    assert target_snapshot["active_baseline_id"] is None

    payload = app.handlers.quest_create(
        {
            "goal": "Try to reuse a deleted baseline.",
            "title": "Should fail after deletion",
            "quest_id": "quest-after-baseline-delete",
            "requested_baseline_ref": {
                "baseline_id": "demo-baseline",
            },
        }
    )

    assert isinstance(payload, tuple)
    status, body = payload
    assert status == 409
    assert body["ok"] is False
    assert "requested baseline `demo-baseline`" in str(body["message"])
    assert not (temp_home / "quests" / "quest-after-baseline-delete").exists()


def test_chat_endpoint_relays_assistant_reply_to_bound_connector(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    config = manager.load_named("config")
    config["connectors"]["system_enabled"]["telegram"] = True
    write_yaml(manager.path_for("config"), config)
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["profiles"] = [
        {
            "profile_id": "qq-1903299925",
            "enabled": True,
            "app_id": "1903299925",
            "app_secret": "qq-secret",
            "bot_name": "DeepScientist",
            "main_chat_id": "CF8D2D559AA956B48751539ADFB98865",
        }
    ]
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("background relay quest")
    quest_id = quest["quest_id"]
    app.quest_service.bind_source(quest_id, "qq:direct:UserABC123")

    class FakeRunner:
        binary = ""

        def run(self, request):
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text="Assistant relay payload.",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    app.runners["codex"] = FakeRunner()

    sent: list[tuple[str, dict]] = []

    def fake_send_to_channel(channel_name, payload, *, connectors=None):  # noqa: ANN001
        sent.append((channel_name, dict(payload)))
        return True

    app.artifact_service._send_to_channel = fake_send_to_channel  # type: ignore[method-assign]

    payload = app.handlers.chat(quest_id, {"text": "Please continue.", "source": "tui-ink"})
    assert payload["ok"] is True

    deadline = time.time() + 3
    while time.time() < deadline:
        qq_payloads = [item for item in sent if item[0] == "qq"]
        if qq_payloads:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("assistant reply was not relayed to the bound QQ connector")

    channel_name, outbound = qq_payloads[-1]
    assert channel_name == "qq"
    assert outbound["conversation_id"] == "qq:direct:UserABC123"
    assert outbound["kind"] == "assistant"
    assert outbound["message"] == "Assistant relay payload."


def test_run_create_allows_explicit_none_reasoning_effort(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    runners = manager.load_named("runners")
    runners["codex"]["model_reasoning_effort"] = "xhigh"
    write_yaml(manager.path_for("runners"), runners)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("run create none reasoning effort quest")
    quest_id = quest["quest_id"]
    captured: dict[str, object] = {}

    class FakeRunner:
        binary = ""

        def run(self, request):
            captured["reasoning_effort"] = request.reasoning_effort
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text="Handled explicit none reasoning effort.",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    app.runners["codex"] = FakeRunner()

    payload = app.handlers.run_create(
        quest_id,
        {
            "message": "Run once.",
            "skill_id": "decision",
            "model_reasoning_effort": "",
        },
    )

    assert payload["ok"] is True
    assert captured["reasoning_effort"] is None


def test_connector_outbound_events_are_persisted_to_quest_stream(temp_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["app_id"] = "1903299925"
    connectors["qq"]["app_secret"] = "qq-secret"
    write_yaml(manager.path_for("connectors"), connectors)

    def fake_deliver(_self, _payload, _config):  # noqa: ANN001
        return {"ok": True, "queued": False, "transport": "qq-http"}

    monkeypatch.setattr("deepscientist.bridges.connectors.QQConnectorBridge.deliver", fake_deliver)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("connector outbound event quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    result = app.artifact_service._deliver_to_channel(
        "qq",
        {
            "quest_root": str(quest_root),
            "quest_id": quest_id,
            "conversation_id": "qq:direct:UserABC123",
            "kind": "progress",
            "message": "Connector outbound payload.",
            "response_phase": "control",
            "importance": "info",
        },
        connectors=app.artifact_service._connectors_config(),
    )

    assert result["ok"] is True
    events = read_jsonl(quest_root / ".ds" / "events.jsonl")
    outbound_event = next(item for item in events if item.get("type") == "connector.outbound")
    assert outbound_event["quest_id"] == quest_id
    assert outbound_event["conversation_id"] == "qq:direct:UserABC123"
    assert outbound_event["channel"] == "qq"
    assert outbound_event["kind"] == "progress"
    assert outbound_event["ok"] is True
    assert outbound_event["queued"] is False
    assert outbound_event["transport"] == "qq-http"


def test_qq_inbound_reply_auto_links_to_latest_threaded_interaction(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
            "bot_name": "DeepScientist",
            "main_chat_id": "CF8D2D559AA956B48751539ADFB98865",
        }
    ]
    write_yaml(manager.path_for("connectors"), connectors)

    deliveries: list[dict] = []

    def fake_deliver(_self, payload, _config):  # noqa: ANN001
        deliveries.append(dict(payload))
        return {"ok": True, "transport": "qq-http"}

    monkeypatch.setattr("deepscientist.bridges.connectors.QQConnectorBridge.deliver", fake_deliver)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("qq threaded reply quest")
    quest_root = Path(quest["quest_root"])
    conversation_id = "qq:direct:CF8D2D559AA956B48751539ADFB98865"
    app.update_quest_binding(quest["quest_id"], conversation_id, force=True)

    progress = app.artifact_service.interact(
        quest_root,
        kind="progress",
        message="老师，我已经完成第一轮审计，正在继续核对依赖入口。",
        deliver_to_bound_conversations=True,
        include_recent_inbound_messages=False,
    )

    assert progress["status"] == "ok"
    assert progress["delivered"] is True
    assert progress["interaction_id"]
    assert deliveries
    assert deliveries[-1]["conversation_id"] == conversation_id

    response = app.handle_qq_inbound(
        {
            "chat_type": "direct",
            "sender_id": "CF8D2D559AA956B48751539ADFB98865",
            "sender_name": "Tester",
            "text": "继续，把数据入口也一起核对。",
        }
    )

    assert response["accepted"] is True
    history = app.quest_service.history(quest["quest_id"])
    assert history
    latest = history[-1]
    assert latest["role"] == "user"
    assert latest["source"] == conversation_id
    assert latest["content"] == "继续，把数据入口也一起核对。"
    assert latest["reply_to_interaction_id"] == progress["interaction_id"]


def test_chat_endpoint_persists_client_message_delivery_state(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("client message id quest")
    quest_id = quest["quest_id"]

    payload = app.handlers.chat(
        quest_id,
        {
            "text": "Track this message.",
            "source": "web-react",
            "client_message_id": "client-msg-001",
        },
    )

    assert payload["ok"] is True
    assert payload["message"]["client_message_id"] == "client-msg-001"
    assert payload["message"]["delivery_state"] == "sent"

    history = app.quest_service.history(quest_id)
    record = next(item for item in history if item.get("role") == "user" and item.get("content") == "Track this message.")
    assert record["client_message_id"] == "client-msg-001"
    assert record["delivery_state"] == "sent"

    events = app.quest_service.events(quest_id)["events"]
    event = next(item for item in events if item.get("type") == "conversation.message" and item.get("content") == "Track this message.")
    assert event["client_message_id"] == "client-msg-001"
    assert event["delivery_state"] == "sent"

    enriched = app.quest_service.enrich_conversation_message_event(quest_id, event)
    assert enriched["read_state"] == "unread"
    assert enriched["read_reason"] == "queued"

    acp_events = app.handlers.quest_events(quest_id, f"/api/quests/{quest_id}/events?format=acp")
    message_update = next(
        item["params"]["update"]
        for item in acp_events["acp_updates"]
        if (item["params"]["update"].get("event_type") or "") == "conversation.message"
        and ((item["params"]["update"].get("message") or {}).get("content") or "") == "Track this message."
    )
    assert message_update["message"]["read_state"] == "unread"
    assert message_update["message"]["read_reason"] == "queued"


def test_chat_upload_and_send_materializes_web_attachment_into_userfiles(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("web attachment quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    uploaded = app.handlers.chat_upload_create(
        quest_id,
        {
            "draft_id": "draft-web-001",
            "file_name": "figure.png",
            "mime_type": "image/png",
            "content_base64": base64.b64encode(b"\x89PNG\r\n\x1a\nquest-chat-upload").decode("ascii"),
        },
    )

    assert uploaded["ok"] is True
    assert uploaded["draft_id"] == "draft-web-001"
    assert uploaded["quest_relative_path"].startswith("userfiles/web/_staging/")
    staged_path = Path(uploaded["path"])
    assert staged_path.exists()

    payload = app.handlers.chat(
        quest_id,
        {
            "text": "Please inspect this uploaded figure.",
            "source": "web-react",
            "client_message_id": "client-msg-attach-001",
            "attachment_draft_ids": ["draft-web-001"],
        },
    )

    assert payload["ok"] is True
    message = payload["message"]
    attachments = list(message.get("attachments") or [])
    assert len(attachments) == 1
    attachment = dict(attachments[0])
    assert attachment["name"] == "figure.png"
    assert str(attachment["quest_relative_path"]).startswith("userfiles/web/client-msg-attach-001/")
    final_path = Path(str(attachment["path"]))
    assert final_path.exists()
    assert not staged_path.exists()
    assert (final_path.parent / "manifest.json").exists()

    history = app.quest_service.history(quest_id)
    record = next(item for item in history if item.get("client_message_id") == "client-msg-attach-001")
    assert len(record.get("attachments") or []) == 1
    assert str((record.get("attachments") or [])[0].get("path") or "") == str(final_path)

    queue_payload = read_json(quest_root / ".ds" / "user_message_queue.json", {})
    pending = list(queue_payload.get("pending") or [])
    assert len(pending) == 1
    assert str((pending[0].get("attachments") or [])[0].get("path") or "") == str(final_path)


def test_read_now_endpoint_consumes_unread_queue_and_restarts_quiet_turn(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    config = manager.load_named("config")
    config["default_locale"] = "en-US"
    write_yaml(manager.path_for("config"), config)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("immediate read quest")
    quest_id = quest["quest_id"]

    class ImmediateReadRunner:
        binary = ""

        def __init__(self) -> None:
            self.requests: list[dict[str, str]] = []
            self.started = threading.Event()
            self.interrupted = threading.Event()

        def run(self, request):
            self.requests.append(
                {
                    "message": request.message,
                    "turn_reason": request.turn_reason,
                }
            )
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            if request.message == "Run the long task first.":
                self.started.set()
                while not self.interrupted.is_set():
                    time.sleep(0.05)
                return RunResult(
                    ok=False,
                    run_id=request.run_id,
                    model=request.model,
                    output_text="Interrupted.",
                    exit_code=130,
                    history_root=history_root,
                    run_root=run_root,
                    stderr_text="stopped by immediate read",
                )
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text="Immediate read handled.",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

        def interrupt(self, target_quest_id: str) -> bool:
            self.interrupted.set()
            return True

    runner = ImmediateReadRunner()
    app.runners["codex"] = runner

    start_payload = app.handlers.chat(
        quest_id,
        {"text": "Run the long task first.", "source": "tui-ink"},
    )
    assert start_payload["ok"] is True
    assert runner.started.wait(timeout=3)

    first = app.quest_service.append_message(
        quest_id,
        role="user",
        content="Please inspect config first.",
        source="web-react",
        client_message_id="msg-read-now-001",
    )
    second = app.quest_service.append_message(
        quest_id,
        role="user",
        content="Then verify the entrypoint.",
        source="qq:group:e2e",
        client_message_id="msg-read-now-002",
    )

    payload = app.handlers.quest_message_read_now(
        quest_id,
        {
            "message_id": second["id"],
            "source": "web-react",
        },
    )

    assert payload["ok"] is True
    assert payload["interrupted"] is True
    assert payload["reason"] == "immediate_read"
    assert payload["message_ids"] == [first["id"], second["id"]]

    deadline = time.time() + 5
    while time.time() < deadline:
        if len(runner.requests) >= 2:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("Immediate read did not restart the agent turn.")

    assert runner.requests[1]["turn_reason"] == "immediate_read"
    assert "Please inspect config first." in runner.requests[1]["message"]
    assert "Then verify the entrypoint." in runner.requests[1]["message"]
    assert "Immediately send one substantive follow-up artifact.interact" in runner.requests[1]["message"]

    snapshot = app.quest_service.snapshot(quest_id)
    assert snapshot["pending_user_message_count"] == 0

    queue_payload = read_json(Path(snapshot["paths"]["user_message_queue"]), {})
    first_state = queue_payload["message_states"][first["id"]]
    second_state = queue_payload["message_states"][second["id"]]
    assert first_state["read_state"] == "read"
    assert first_state["read_reason"] == "immediate_read"
    assert second_state["read_state"] == "read"
    assert second_state["read_reason"] == "immediate_read"

    events = read_jsonl(Path(snapshot["quest_root"]) / ".ds" / "events.jsonl")
    assert not any(str(item.get("type") or "") == "quest.control" for item in events)
    state_events = [item for item in events if str(item.get("type") or "") == "conversation.message_state"]
    assert {item.get("message_id") for item in state_events[-2:]} == {first["id"], second["id"]}


def test_read_now_endpoint_reports_success_when_message_was_already_read(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("already read immediate read quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    message = app.quest_service.append_message(
        quest_id,
        role="user",
        content="Please inspect the config.",
        source="web-react",
        client_message_id="already-read-001",
    )
    app.quest_service.consume_pending_user_messages(
        quest_root,
        interaction_id="interaction-read-001",
        delivery_reason="artifact_mailbox",
    )

    payload = app.handlers.quest_message_read_now(
        quest_id,
        {
            "message_id": message["id"],
            "source": "web-react",
        },
    )

    assert payload["ok"] is True
    assert payload["status"] == "already_read"


def test_read_now_endpoint_surfaces_interrupt_failure_details(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("immediate read interrupt failure quest")
    quest_id = quest["quest_id"]

    class StuckImmediateReadRunner:
        binary = ""

        def __init__(self) -> None:
            self.started = threading.Event()

        def run(self, request):
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            self.started.set()
            time.sleep(6.0)
            return RunResult(
                ok=False,
                run_id=request.run_id,
                model=request.model,
                output_text="Still running.",
                exit_code=130,
                history_root=history_root,
                run_root=run_root,
                stderr_text="stuck worker",
            )

        def interrupt(self, target_quest_id: str) -> bool:
            return False

    runner = StuckImmediateReadRunner()
    app.runners["codex"] = runner

    start_payload = app.handlers.chat(
        quest_id,
        {"text": "Start the stuck task.", "source": "tui-ink"},
    )
    assert start_payload["ok"] is True
    assert runner.started.wait(timeout=3)

    queued = app.quest_service.append_message(
        quest_id,
        role="user",
        content="Please read now.",
        source="web-react",
        client_message_id="msg-read-now-stuck-001",
    )

    payload = app.handlers.quest_message_read_now(
        quest_id,
        {
            "message_id": queued["id"],
            "source": "web-react",
        },
    )

    assert payload["ok"] is False
    assert payload["status"] == "interrupt_failed"
    assert "interrupt_returned=False" in payload["message"]
    assert "reason=runner_interrupt_returned_false" in payload["message"]
    assert payload["message_ids"] == [queued["id"]]


def test_withdraw_endpoint_removes_unread_message_from_queue(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("withdraw unread quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    message = app.quest_service.append_message(
        quest_id,
        role="user",
        content="Please withdraw this queued note.",
        source="web-react",
        client_message_id="withdraw-001",
    )

    payload = app.handlers.quest_message_withdraw(
        quest_id,
        {
            "message_id": message["id"],
            "source": "web-react",
        },
    )

    assert payload["ok"] is True
    assert payload["status"] == "withdrawn"
    assert payload["current_message_state"]["read_reason"] == "withdrawn_by_user"
    assert payload["snapshot"]["pending_user_message_count"] == 0

    queue_payload = read_json(quest_root / ".ds" / "user_message_queue.json", {})
    assert queue_payload["pending"] == []
    assert queue_payload["message_states"][message["id"]]["read_reason"] == "withdrawn_by_user"
    assert any(
        str(item.get("status") or "") == "withdrawn_by_user"
        and str(item.get("message_id") or "") == message["id"]
        for item in queue_payload["completed"]
    )
    requirements_text = (quest_root / "memory" / "knowledge" / "active-user-requirements.md").read_text(encoding="utf-8")
    assert "Please withdraw this queued note." not in requirements_text


def test_withdraw_endpoint_fails_when_message_was_already_read(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("withdraw read quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    message = app.quest_service.append_message(
        quest_id,
        role="user",
        content="This message will be read first.",
        source="web-react",
        client_message_id="withdraw-read-001",
    )
    app.quest_service.consume_pending_user_messages(
        quest_root,
        interaction_id="interaction-read-002",
        delivery_reason="artifact_mailbox",
    )

    payload = app.handlers.quest_message_withdraw(
        quest_id,
        {
            "message_id": message["id"],
            "source": "web-react",
        },
    )

    assert payload["ok"] is False
    assert payload["status"] == "already_read"
    assert payload["current_message_state"]["read_reason"] == "artifact_mailbox"


def test_quest_events_acp_message_updates_preserve_stream_identity(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("stream identity quest")
    quest_id = quest["quest_id"]
    events_path = Path(quest["quest_root"]) / ".ds" / "events.jsonl"

    append_jsonl(
        events_path,
        {
            "event_id": "evt-stream-001",
            "type": "runner.delta",
            "quest_id": quest_id,
            "run_id": "run-001",
            "source": "codex",
            "skill_id": "baseline",
            "text": "Streaming draft",
            "stream_id": "msg-001",
            "message_id": "msg-001",
            "created_at": utc_now(),
        },
    )
    append_jsonl(
        events_path,
        {
            "event_id": "evt-stream-002",
            "type": "runner.agent_message",
            "quest_id": quest_id,
            "run_id": "run-001",
            "source": "codex",
            "skill_id": "baseline",
            "text": "Streaming draft",
            "stream_id": "msg-001",
            "message_id": "msg-001",
            "created_at": utc_now(),
        },
    )

    payload = app.handlers.quest_events(
        quest_id,
        path=f"/api/quests/{quest_id}/events?format=acp&session_id=session:test",
    )
    updates = [item["params"]["update"] for item in payload["acp_updates"]]
    delta_update = next(item for item in updates if item["event_type"] == "runner.delta")
    final_update = next(item for item in updates if item["event_type"] == "runner.agent_message")

    assert delta_update["message"]["stream_id"] == "msg-001"
    assert delta_update["message"]["message_id"] == "msg-001"
    assert final_update["message"]["stream_id"] == "msg-001"
    assert final_update["message"]["message_id"] == "msg-001"


def test_chat_endpoint_passes_user_text_into_codex_prompt(temp_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("prompt delivery quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    fake_bin_root = temp_home / "bin"
    fake_bin_root.mkdir(parents=True, exist_ok=True)
    capture_path = temp_home / "captured-prompt.md"
    fake_codex = fake_bin_root / "codex"
    fake_codex.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, os, sys",
                "prompt = sys.stdin.read()",
                "with open(os.environ['FAKE_CODEX_CAPTURE'], 'w', encoding='utf-8') as handle:",
                "    handle.write(prompt)",
                "print(json.dumps({'item': {'text': 'captured prompt ok'}}))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin_root}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_CODEX_CAPTURE", str(capture_path))
    app.codex_runner.binary = "codex"
    app.runners["codex"] = app.codex_runner

    user_text = "Please confirm this user text reaches the Codex prompt."
    payload = app.handlers.chat(quest_id, {"text": user_text, "source": "tui-ink"})

    assert payload["ok"] is True

    deadline = time.time() + 5
    while time.time() < deadline:
        if capture_path.exists():
            history = app.quest_service.history(quest_id)
            if any(item.get("role") == "assistant" and item.get("content") == "captured prompt ok" for item in history):
                break
        time.sleep(0.05)
    else:
        raise AssertionError("codex prompt was not captured from the background chat run")

    captured_prompt = capture_path.read_text(encoding="utf-8")
    assert "## Current User Message" in captured_prompt
    assert user_text in captured_prompt

    prompt_files = sorted((quest_root / ".ds" / "runs").glob("*/prompt.md"))
    assert prompt_files
    prompt_text = prompt_files[-1].read_text(encoding="utf-8")
    assert user_text in prompt_text


def test_quest_control_resume_marks_quest_active(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("resume quest")
    quest_id = quest["quest_id"]

    app.quest_service.set_status(quest_id, "stopped")

    payload = app.handlers.quest_control(quest_id, {"action": "resume", "source": "tui-ink"})

    assert payload["ok"] is True
    assert payload["action"] == "resume"
    assert payload["snapshot"]["status"] == "active"
    notice_message = str((payload.get("notice") or {}).get("message") or "")
    assert notice_message
    assert "恢复" in notice_message or "resumed" in notice_message.lower()
    outbox_path = temp_home / "logs" / "connectors" / "local" / "outbox.jsonl"
    outbox = [json.loads(line) for line in outbox_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(
        ("恢复" in str(item.get("message") or "") or "resumed" in str(item.get("message") or "").lower())
        for item in outbox
    )


def test_quest_control_resume_schedules_new_turn_without_new_user_message(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("resume schedules turn quest")
    quest_id = quest["quest_id"]

    class ResumeRunner:
        binary = ""

        def __init__(self) -> None:
            self.requests: list[dict[str, str]] = []

        def run(self, request):
            self.requests.append(
                {
                    "message": request.message,
                    "turn_reason": request.turn_reason,
                    "skill_id": request.skill_id,
                }
            )
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text="resumed auto-continue turn",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    runner = ResumeRunner()
    app.runners["codex"] = runner
    app.quest_service.set_status(quest_id, "stopped")

    payload = app.handlers.quest_control(quest_id, {"action": "resume", "source": "tui-ink"})

    assert payload["ok"] is True
    assert payload["action"] == "resume"
    assert payload["snapshot"]["status"] == "active"
    assert payload["scheduled"] is True
    assert str((payload.get("resume_trigger_message") or {}).get("content") or "") == "Continue"

    deadline = time.time() + 5
    while time.time() < deadline:
        if runner.requests:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("resume did not schedule a new runner turn")

    assert runner.requests[0]["turn_reason"] == "user_message"
    assert runner.requests[0]["message"] == "Continue"

    history = app.quest_service.history(quest_id)
    assert any(item.get("role") == "user" and item.get("content") == "Continue" for item in history)


def test_quest_control_resume_consumes_queued_user_messages_after_stop(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("resume queued mailbox quest")
    quest_id = quest["quest_id"]

    class InterruptibleResumeRunner:
        binary = ""

        def __init__(self) -> None:
            self.requests: list[dict[str, str]] = []
            self.started = threading.Event()
            self.interrupted = threading.Event()

        def run(self, request):
            self.requests.append(
                {
                    "message": request.message,
                    "turn_reason": request.turn_reason,
                }
            )
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            if request.message == "Run the primary task.":
                self.started.set()
                while not self.interrupted.is_set():
                    time.sleep(0.05)
                return RunResult(
                    ok=False,
                    run_id=request.run_id,
                    model=request.model,
                    output_text="Interrupted.",
                    exit_code=130,
                    history_root=history_root,
                    run_root=run_root,
                    stderr_text="stopped by user",
                )
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text=f"Echo: {request.message}",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

        def interrupt(self, target_quest_id: str) -> bool:
            self.interrupted.set()
            return True

    runner = InterruptibleResumeRunner()
    app.runners["codex"] = runner

    initial_payload = app.handlers.chat(quest_id, {"text": "Run the primary task.", "source": "tui-ink"})
    assert initial_payload["ok"] is True
    assert runner.started.wait(timeout=2)

    queued_payload = app.handlers.chat(
        quest_id,
        {"text": "Please also inspect config.", "source": "web-react"},
    )
    assert queued_payload["ok"] is True
    assert queued_payload["queued"] is True

    stop_payload = app.handlers.quest_control(quest_id, {"action": "stop", "source": "tui-ink"})
    assert stop_payload["ok"] is True
    assert stop_payload["snapshot"]["status"] == "stopped"
    assert stop_payload["snapshot"]["pending_user_message_count"] == 1

    resume_payload = app.handlers.quest_control(quest_id, {"action": "resume", "source": "tui-ink"})
    assert resume_payload["ok"] is True
    assert resume_payload["snapshot"]["status"] == "active"
    assert resume_payload["scheduled"] is True
    assert resume_payload["reason"] == "queued_user_messages"

    deadline = time.time() + 5
    while time.time() < deadline:
        if len(runner.requests) >= 2:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("resume did not restart the queued user message turn")

    assert runner.requests[1]["turn_reason"] == "queued_user_messages"
    assert runner.requests[1]["message"] == "Please also inspect config."

    deadline = time.time() + 3
    while time.time() < deadline:
        snapshot = app.quest_service.snapshot(quest_id)
        if snapshot["pending_user_message_count"] == 0:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("queued user message was not consumed after resume")

    queue_payload = read_json(Path(snapshot["paths"]["user_message_queue"]), {})
    state_records = list((queue_payload.get("message_states") or {}).values())
    assert any(
        str(item.get("read_state") or "") == "read"
        and str(item.get("read_reason") or "") == "accepted_by_run"
        for item in state_records
    )


def test_resume_queued_messages_uses_latest_pending_message_after_withdraw(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("resume skips withdrawn queued message quest")
    quest_id = quest["quest_id"]

    class InterruptibleResumeRunner:
        binary = ""

        def __init__(self) -> None:
            self.requests: list[dict[str, str]] = []
            self.started = threading.Event()
            self.interrupted = threading.Event()

        def run(self, request):
            self.requests.append(
                {
                    "message": request.message,
                    "turn_reason": request.turn_reason,
                }
            )
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            if request.message == "Run the primary task.":
                self.started.set()
                while not self.interrupted.is_set():
                    time.sleep(0.05)
                return RunResult(
                    ok=False,
                    run_id=request.run_id,
                    model=request.model,
                    output_text="Interrupted.",
                    exit_code=130,
                    history_root=history_root,
                    run_root=run_root,
                    stderr_text="stopped by user",
                )
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text=f"Echo: {request.message}",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

        def interrupt(self, target_quest_id: str) -> bool:
            self.interrupted.set()
            return True

    runner = InterruptibleResumeRunner()
    app.runners["codex"] = runner

    initial_payload = app.handlers.chat(quest_id, {"text": "Run the primary task.", "source": "tui-ink"})
    assert initial_payload["ok"] is True
    assert runner.started.wait(timeout=2)

    first = app.handlers.chat(
        quest_id,
        {"text": "Inspect config first.", "source": "web-react"},
    )
    assert first["ok"] is True
    assert first["queued"] is True

    second = app.handlers.chat(
        quest_id,
        {"text": "Inspect the entrypoint second.", "source": "web-react"},
    )
    assert second["ok"] is True
    assert second["queued"] is True

    withdrawn_message_id = str((second.get("message") or {}).get("id") or "")
    withdraw_payload = app.handlers.quest_message_withdraw(
        quest_id,
        {
            "message_id": withdrawn_message_id,
            "source": "web-react",
        },
    )
    assert withdraw_payload["ok"] is True
    assert withdraw_payload["status"] == "withdrawn"

    stop_payload = app.handlers.quest_control(quest_id, {"action": "stop", "source": "tui-ink"})
    assert stop_payload["ok"] is True
    assert stop_payload["snapshot"]["pending_user_message_count"] == 1

    resume_payload = app.handlers.quest_control(quest_id, {"action": "resume", "source": "tui-ink"})
    assert resume_payload["ok"] is True
    assert resume_payload["reason"] == "queued_user_messages"

    deadline = time.time() + 5
    while time.time() < deadline:
        if len(runner.requests) >= 2:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("resume did not restart the queued user message turn")

    assert runner.requests[1]["turn_reason"] == "queued_user_messages"
    assert runner.requests[1]["message"] == "Inspect config first."


def test_quest_control_pause_marks_quest_paused_and_interrupts_runner(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("pause quest")
    quest_id = quest["quest_id"]

    class InterruptibleRunner:
        binary = ""

        def __init__(self) -> None:
            self.started = threading.Event()
            self.interrupted = threading.Event()

        def run(self, request):
            self.started.set()
            while not self.interrupted.is_set():
                time.sleep(0.05)
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            return RunResult(
                ok=False,
                run_id=request.run_id,
                model=request.model,
                output_text="Interrupted.",
                exit_code=130,
                history_root=history_root,
                run_root=run_root,
                stderr_text="paused by user",
            )

        def interrupt(self, quest_id: str) -> bool:
            self.interrupted.set()
            return True

    runner = InterruptibleRunner()
    app.runners["codex"] = runner

    payload = app.handlers.chat(quest_id, {"text": "Pause this long task.", "source": "tui-ink"})
    assert payload["ok"] is True
    assert runner.started.wait(timeout=2)
    running_snapshot = app.quest_service.snapshot(quest_id)
    assert running_snapshot["status"] == "running"
    assert running_snapshot["active_run_id"]

    pause_payload = app.handlers.quest_control(quest_id, {"action": "pause", "source": "tui-ink"})

    assert pause_payload["ok"] is True
    assert pause_payload["action"] == "pause"
    assert pause_payload["interrupted"] is True
    assert pause_payload["snapshot"]["status"] == "paused"
    assert "发送任意新指令" in str(pause_payload["notice"]["message"])

    deadline = time.time() + 3
    while time.time() < deadline:
        paused_snapshot = app.quest_service.snapshot(quest_id)
        if paused_snapshot["status"] == "paused" and paused_snapshot["active_run_id"] is None:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("paused quest did not clear active_run_id after the runner exited")


def test_quest_control_stop_stops_runner_owned_bash_exec_sessions(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("stop quest with bash")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    class InterruptibleRunner:
        binary = ""

        def __init__(self) -> None:
            self.started = threading.Event()
            self.interrupted = threading.Event()

        def run(self, request):
            self.started.set()
            while not self.interrupted.is_set():
                time.sleep(0.05)
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            return RunResult(
                ok=False,
                run_id=request.run_id,
                model=request.model,
                output_text="Interrupted.",
                exit_code=130,
                history_root=history_root,
                run_root=run_root,
                stderr_text="stopped by user",
            )

        def interrupt(self, quest_id: str) -> bool:
            self.interrupted.set()
            return True

    runner = InterruptibleRunner()
    app.runners["codex"] = runner

    payload = app.handlers.chat(quest_id, {"text": "Stop this long task.", "source": "web-react"})
    assert payload["ok"] is True
    assert runner.started.wait(timeout=2)

    running_snapshot = app.quest_service.snapshot(quest_id)
    active_run_id = str(running_snapshot["active_run_id"] or "")
    assert active_run_id

    context = McpContext(
        home=temp_home,
        quest_id=quest_id,
        quest_root=quest_root,
        run_id=active_run_id,
        active_anchor="experiment",
        conversation_id=f"quest:{quest_id}",
        agent_role="pi",
        worker_id=None,
        worktree_root=None,
        team_mode="single",
    )
    session = app.bash_exec_service.start_session(
        context,
        command="printf 'alpha\\n'; sleep 5; printf 'omega\\n'",
        mode="detach",
    )
    bash_id = session["bash_id"]
    time.sleep(0.6)

    stop_payload = app.handlers.quest_control(quest_id, {"action": "stop", "source": "web-react"})

    assert stop_payload["ok"] is True
    assert stop_payload["action"] == "stop"
    assert stop_payload["interrupted"] is True
    assert stop_payload["snapshot"]["status"] == "stopped"
    assert bash_id in stop_payload["stopped_bash_session_ids"]
    assert "发送任意新指令" in str(stop_payload["notice"]["message"])

    final = app.bash_exec_service.wait_for_session(quest_root, bash_id, timeout_seconds=10)
    assert final["status"] == "terminated"

    deadline = time.time() + 3
    while time.time() < deadline:
        stopped_snapshot = app.quest_service.snapshot(quest_id)
        if stopped_snapshot["status"] == "stopped" and stopped_snapshot["active_run_id"] is None:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("stopped quest did not clear active_run_id after the runner exited")


def test_admin_shutdown_endpoint_requests_daemon_shutdown(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)

    payload = app.handlers.admin_shutdown({"source": "pytest"})

    assert payload["ok"] is True
    assert "shutdown requested" in payload["message"].lower()
    assert app._shutdown_requested.is_set() is True


def test_admin_shutdown_interrupts_running_quest_and_clears_active_run(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("shutdown interrupt quest")
    quest_id = quest["quest_id"]

    class InterruptOnlyRunner:
        binary = ""

        def __init__(self) -> None:
            self.interrupt_calls: list[str] = []

        def interrupt(self, target_quest_id: str) -> bool:
            self.interrupt_calls.append(target_quest_id)
            return True

    runner = InterruptOnlyRunner()
    app.runners["codex"] = runner
    app.quest_service.mark_turn_started(quest_id, run_id="run-stale-001", status="running")

    payload = app.handlers.admin_shutdown({"source": "pytest"})

    assert payload["ok"] is True
    assert quest_id in payload["interrupted_quests"]
    assert runner.interrupt_calls == [quest_id]

    snapshot = app.quest_service.snapshot(quest_id)
    assert snapshot["status"] == "stopped"
    assert snapshot["active_run_id"] is None


def test_daemon_startup_reconciles_stale_running_quest(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    first_app = DaemonApp(temp_home)
    quest = first_app.quest_service.create("reconcile stale runtime quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    quest_yaml = read_yaml(quest_root / "quest.yaml", {})
    quest_yaml["status"] = "running"
    quest_yaml["active_run_id"] = "run-crashed-001"
    write_yaml(quest_root / "quest.yaml", quest_yaml)
    runtime_state = read_json(quest_root / ".ds" / "runtime_state.json", {})
    runtime_state["status"] = "running"
    runtime_state["active_run_id"] = "run-crashed-001"
    runtime_state["last_transition_at"] = utc_now()
    write_json(quest_root / ".ds" / "runtime_state.json", runtime_state)

    app = DaemonApp(temp_home)

    snapshot = app.quest_service.snapshot(quest_id)
    assert snapshot["status"] == "stopped"
    assert snapshot["active_run_id"] is None
    assert any(item["quest_id"] == quest_id for item in app.reconciled_quests)
    assert any(item["quest_id"] == quest_id and item.get("recoverable") is True for item in app.reconciled_quests)

    events = app.quest_service.events(quest_id)["events"]
    assert any(
        item.get("type") == "quest.runtime_reconciled"
        and item.get("abandoned_run_id") == "run-crashed-001"
        for item in events
    )


def test_submit_user_message_reconciles_stale_active_turn_and_starts_new_run(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("stale active turn submit quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    app.quest_service.set_continuation_state(quest_root, policy="none")

    stale_run_id = "run-stale-submit-001"
    app.quest_service.mark_turn_started(quest_id, run_id=stale_run_id, status="running")
    stale_run_root = ensure_dir(quest_root / ".ds" / "runs" / stale_run_id)
    write_json(
        stale_run_root / "result.json",
        {
            "ok": True,
            "run_id": stale_run_id,
            "model": "gpt-5.4",
            "exit_code": 0,
            "output_text": "stale result",
            "stderr_text": "",
            "completed_at": utc_now(),
        },
    )

    class RecoveryRunner:
        binary = ""

        def __init__(self) -> None:
            self.requests: list[str] = []

        def run(self, request):
            self.requests.append(request.message)
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text=f"Recovered: {request.message}",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    runner = RecoveryRunner()
    app.runners["codex"] = runner

    payload = app.submit_user_message(
        quest_id,
        text="Please continue after stale state.",
        source="web-react",
    )

    assert payload["started"] is True
    assert payload["queued"] is False

    deadline = time.time() + 3
    while time.time() < deadline:
        if runner.requests:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("stale active turn was not reconciled into a fresh run")

    assert runner.requests[0] == "Please continue after stale state."
    deadline = time.time() + 3
    while time.time() < deadline:
        snapshot = app.quest_service.snapshot(quest_id)
        if snapshot["active_run_id"] is None:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("fresh run did not clear active_run_id after completing")

    events = app.quest_service.events(quest_id)["events"]
    assert any(
        item.get("type") == "quest.turn_state_reconciled"
        and item.get("abandoned_run_id") == stale_run_id
        for item in events
    )


def _mark_turn_started_with_retry(
    app: DaemonApp,
    quest_id: str,
    *,
    run_id: str,
    status: str,
    retries: int = 20,
    delay_seconds: float = 0.05,
) -> None:
    last_error: PermissionError | None = None
    for _ in range(max(1, retries)):
        try:
            app.quest_service.mark_turn_started(quest_id, run_id=run_id, status=status)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(delay_seconds)
    if last_error is not None:
        raise last_error
    raise AssertionError("mark_turn_started retry helper exhausted without raising a PermissionError")


def test_submit_user_message_recovers_stalled_live_turn_and_starts_new_run(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("stalled live turn recovery quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    app.quest_service.set_continuation_state(quest_root, policy="none")

    stale_run_id = "run-stalled-live-001"
    _mark_turn_started_with_retry(app, quest_id, run_id=stale_run_id, status="running")

    interrupt_requested = threading.Event()

    def _old_worker() -> None:
        while not interrupt_requested.is_set():
            time.sleep(0.02)

    old_worker = threading.Thread(target=_old_worker, daemon=True, name=f"pytest-stalled-worker-{quest_id}")
    old_worker.start()

    class RecoveryRunner:
        binary = ""

        def __init__(self) -> None:
            self.interrupt_calls: list[str] = []
            self.requests: list[str] = []

        def run(self, request):
            self.requests.append(request.message)
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text=f"Recovered stalled turn: {request.message}",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

        def interrupt(self, target_quest_id: str) -> bool:
            self.interrupt_calls.append(target_quest_id)
            interrupt_requested.set()
            return True

    runner = RecoveryRunner()
    app.runners["codex"] = runner
    app._turn_state[quest_id] = {
        "running": True,
        "pending": False,
        "stop_requested": False,
        "reason": "user_message",
        "worker": old_worker,
    }

    def _fake_stalled_running_turn_details(
        target_quest_id: str,
        *,
        snapshot: dict | None = None,
        turn_state: dict[str, object] | None = None,
        turn_reason: str,
    ) -> dict[str, int] | None:
        if target_quest_id != quest_id or turn_reason != "user_message":
            return None
        if not dict(turn_state or {}).get("running"):
            return None
        return {
            "pending_user_count": int((snapshot or {}).get("pending_user_message_count") or 1),
            "silent_seconds": _STALLED_RUNNING_TURN_INACTIVITY_SECONDS,
        }

    monkeypatch.setattr(app, "_stalled_running_turn_details", _fake_stalled_running_turn_details)

    payload = app.submit_user_message(
        quest_id,
        text="Please recover the stalled worker.",
        source="web-react",
    )

    assert payload["started"] is True
    assert payload["queued"] is False

    deadline = time.time() + 3
    while time.time() < deadline:
        if not old_worker.is_alive() and runner.requests:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("stalled live turn was not recovered into a fresh run")

    assert runner.interrupt_calls == [quest_id]
    assert runner.requests == ["Please recover the stalled worker."]

    deadline = time.time() + 3
    while time.time() < deadline:
        try:
            snapshot = app.quest_service.snapshot(quest_id)
        except PermissionError:
            time.sleep(0.05)
            continue
        if snapshot["active_run_id"] is None:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("recovered run did not clear active_run_id after completing")

    events = app.quest_service.events(quest_id)["events"]
    assert any(
        item.get("type") == "quest.turn_state_reconciled"
        and item.get("abandoned_run_id") == stale_run_id
        and item.get("recovery_kind") == "stalled_live_turn"
        for item in events
    )


def test_stalled_live_turn_recovery_pending_does_not_reinterrupt_or_clear_stop_requested(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("stalled recovery pending quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    app.quest_service.set_continuation_state(quest_root, policy="none")

    stale_run_id = "run-stalled-live-pending-001"
    _mark_turn_started_with_retry(app, quest_id, run_id=stale_run_id, status="running")

    release_worker = threading.Event()

    def _old_worker() -> None:
        while not release_worker.is_set():
            time.sleep(0.02)

    old_worker = threading.Thread(target=_old_worker, daemon=True, name=f"pytest-stalled-pending-{quest_id}")
    old_worker.start()

    class PendingRecoveryRunner:
        binary = ""

        def __init__(self) -> None:
            self.interrupt_calls: list[str] = []
            self.requests: list[str] = []

        def run(self, request):
            self.requests.append(request.message)
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text=f"Recovered after wait: {request.message}",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

        def interrupt(self, target_quest_id: str) -> bool:
            self.interrupt_calls.append(target_quest_id)
            return True

    runner = PendingRecoveryRunner()
    app.runners["codex"] = runner
    app._turn_state[quest_id] = {
        "running": True,
        "pending": False,
        "stop_requested": False,
        "reason": "user_message",
        "worker": old_worker,
    }

    def _fake_stalled_running_turn_details(
        target_quest_id: str,
        *,
        snapshot: dict | None = None,
        turn_state: dict[str, object] | None = None,
        turn_reason: str,
    ) -> dict[str, int] | None:
        if target_quest_id != quest_id or turn_reason != "user_message":
            return None
        if not dict(turn_state or {}).get("running"):
            return None
        return {
            "pending_user_count": int((snapshot or {}).get("pending_user_message_count") or 1),
            "silent_seconds": _STALLED_RUNNING_TURN_INACTIVITY_SECONDS,
        }

    monkeypatch.setattr(app, "_stalled_running_turn_details", _fake_stalled_running_turn_details)
    monkeypatch.setattr(
        app,
        "_wait_for_turn_worker_exit",
        lambda target_quest_id, timeout_seconds: app._refresh_turn_worker_state(target_quest_id),
    )

    payload = app.submit_user_message(
        quest_id,
        text="Please recover once the stale worker exits.",
        source="web-react",
    )

    assert payload["started"] is False
    assert payload["queued"] is True
    assert payload["reason"] == "stalled_turn_recovery_pending"
    assert runner.interrupt_calls == [quest_id]

    state = dict(app._turn_state.get(quest_id) or {})
    assert state["running"] is True
    assert state["stop_requested"] is True
    assert state["pending"] is False
    assert state["recovery_pending"] is True
    assert state["recovery_watch_active"] is True

    second_payload = app.schedule_turn(quest_id, reason="user_message")

    assert second_payload["started"] is False
    assert second_payload["queued"] is True
    assert second_payload["reason"] == "stalled_turn_recovery_pending"
    assert runner.interrupt_calls == [quest_id]

    state = dict(app._turn_state.get(quest_id) or {})
    assert state["stop_requested"] is True
    assert state["recovery_pending"] is True
    assert runner.requests == []

    release_worker.set()
    old_worker.join(timeout=2)
    assert old_worker.is_alive() is False

    deadline = time.time() + 3
    while time.time() < deadline:
        if runner.requests:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("queued user message was not automatically processed after the stale worker exited")

    assert runner.requests == ["Please recover once the stale worker exits."]
    assert runner.interrupt_calls == [quest_id]

    deadline = time.time() + 3
    while time.time() < deadline:
        state = dict(app._turn_state.get(quest_id) or {})
        if not state.get("recovery_pending") and not state.get("recovery_watch_active"):
            break
        time.sleep(0.05)
    else:
        raise AssertionError("recovery watch state was not cleared after automatic reschedule")


@pytest.mark.parametrize(
    ("action", "expected_status"),
    [
        ("pause", "paused"),
        ("stop", "stopped"),
    ],
)
def test_stalled_live_turn_recovery_pending_respects_later_control_action(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    expected_status: str,
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create(f"stalled recovery {action} quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    app.quest_service.set_continuation_state(quest_root, policy="none")

    stale_run_id = f"run-stalled-live-{action}-001"
    _mark_turn_started_with_retry(app, quest_id, run_id=stale_run_id, status="running")

    release_worker = threading.Event()

    def _old_worker() -> None:
        while not release_worker.is_set():
            time.sleep(0.02)

    old_worker = threading.Thread(target=_old_worker, daemon=True, name=f"pytest-stalled-{action}-{quest_id}")
    old_worker.start()

    class RecoveryRunner:
        binary = ""

        def __init__(self) -> None:
            self.interrupt_calls: list[str] = []
            self.requests: list[str] = []

        def run(self, request):
            self.requests.append(request.message)
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text=f"Unexpected recovery: {request.message}",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

        def interrupt(self, target_quest_id: str) -> bool:
            self.interrupt_calls.append(target_quest_id)
            return True

    runner = RecoveryRunner()
    app.runners["codex"] = runner
    app._turn_state[quest_id] = {
        "running": True,
        "pending": False,
        "stop_requested": False,
        "reason": "user_message",
        "worker": old_worker,
    }

    def _fake_stalled_running_turn_details(
        target_quest_id: str,
        *,
        snapshot: dict | None = None,
        turn_state: dict[str, object] | None = None,
        turn_reason: str,
    ) -> dict[str, int] | None:
        if target_quest_id != quest_id or turn_reason != "user_message":
            return None
        if not dict(turn_state or {}).get("running"):
            return None
        return {
            "pending_user_count": int((snapshot or {}).get("pending_user_message_count") or 1),
            "silent_seconds": _STALLED_RUNNING_TURN_INACTIVITY_SECONDS,
        }

    monkeypatch.setattr(app, "_stalled_running_turn_details", _fake_stalled_running_turn_details)
    monkeypatch.setattr(
        app,
        "_wait_for_turn_worker_exit",
        lambda target_quest_id, timeout_seconds: app._refresh_turn_worker_state(target_quest_id),
    )

    payload = app.submit_user_message(
        quest_id,
        text=f"Please recover unless I {action}.",
        source="web-react",
    )

    assert payload["started"] is False
    assert payload["queued"] is True
    assert payload["reason"] == "stalled_turn_recovery_pending"

    control_payload = app.handlers.quest_control(quest_id, {"action": action, "source": "web-react"})
    assert control_payload["ok"] is True
    assert control_payload["snapshot"]["status"] == expected_status

    release_worker.set()
    old_worker.join(timeout=2)
    assert old_worker.is_alive() is False

    deadline = time.time() + 3
    while time.time() < deadline:
        state = dict(app._turn_state.get(quest_id) or {})
        if not state.get("running") and not state.get("recovery_pending") and not state.get("recovery_watch_active"):
            break
        time.sleep(0.05)
    else:
        raise AssertionError("recovery state was not cleared after the later control action")

    snapshot = app.quest_service.snapshot(quest_id)
    assert snapshot["status"] == expected_status
    assert snapshot["pending_user_message_count"] == 1

    state = dict(app._turn_state.get(quest_id) or {})
    assert state.get("stop_requested") is True
    assert state.get("pending") is False
    assert runner.requests == []


def test_schedule_turn_recovers_stalled_live_turn_only_once_under_concurrency(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("concurrent stalled live turn recovery schedule quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    app.quest_service.set_continuation_state(quest_root, policy="none")
    app.quest_service.append_message(
        quest_id,
        role="user",
        content="Recover the queued message once the stalled turn is cleared.",
        source="web-react",
    )

    stale_run_id = "run-stalled-live-concurrent-001"
    _mark_turn_started_with_retry(app, quest_id, run_id=stale_run_id, status="running")

    release_worker = threading.Event()

    def _old_worker() -> None:
        while not release_worker.is_set():
            time.sleep(0.02)

    old_worker = threading.Thread(target=_old_worker, daemon=True, name=f"pytest-stalled-concurrent-{quest_id}")
    old_worker.start()

    class RecoveryRunner:
        binary = ""

        def __init__(self) -> None:
            self.interrupt_calls: list[str] = []

        def interrupt(self, target_quest_id: str) -> bool:
            self.interrupt_calls.append(target_quest_id)
            release_worker.set()
            time.sleep(0.2)
            return True

    runner = RecoveryRunner()
    app.runners["codex"] = runner
    app._turn_state[quest_id] = {
        "running": True,
        "pending": False,
        "stop_requested": False,
        "reason": "user_message",
        "worker": old_worker,
    }

    def _fake_stalled_running_turn_details(
        target_quest_id: str,
        *,
        snapshot: dict | None = None,
        turn_state: dict[str, object] | None = None,
        turn_reason: str,
    ) -> dict[str, int] | None:
        if target_quest_id != quest_id or turn_reason != "user_message":
            return None
        if not dict(turn_state or {}).get("running"):
            return None
        return {
            "pending_user_count": int((snapshot or {}).get("pending_user_message_count") or 1),
            "silent_seconds": _STALLED_RUNNING_TURN_INACTIVITY_SECONDS,
        }

    monkeypatch.setattr(app, "_stalled_running_turn_details", _fake_stalled_running_turn_details)

    barrier = threading.Barrier(3)
    payloads: list[dict[str, object]] = []
    errors: list[Exception] = []
    run_turn_calls: list[str] = []

    def _fake_run_quest_turn(target_quest_id: str) -> None:
        run_turn_calls.append(target_quest_id)

    monkeypatch.setattr(app, "_run_quest_turn", _fake_run_quest_turn)

    def _schedule_turn() -> None:
        barrier.wait()
        try:
            payloads.append(app.schedule_turn(quest_id, reason="user_message"))
        except Exception as exc:  # pragma: no cover - exercised only on failure
            errors.append(exc)

    workers = [threading.Thread(target=_schedule_turn, daemon=True) for _ in range(2)]
    for worker in workers:
        worker.start()
    barrier.wait()
    for worker in workers:
        worker.join(timeout=2)

    assert errors == []
    assert len(payloads) == 2
    assert sum(1 for item in payloads if item["started"] is True) == 1
    assert sum(1 for item in payloads if item["reason"] == "stalled_turn_recovery_pending") == 1

    deadline = time.time() + 5
    while time.time() < deadline:
        if len(run_turn_calls) == 1 and not old_worker.is_alive():
            break
        time.sleep(0.05)
    else:
        raise AssertionError("concurrent stalled live turn recovery did not finish exactly one replacement turn")

    assert runner.interrupt_calls == [quest_id]
    assert run_turn_calls == [quest_id]

    events = [
        item
        for item in app.quest_service.events(quest_id)["events"]
        if item.get("type") == "quest.turn_state_reconciled"
        and item.get("abandoned_run_id") == stale_run_id
        and item.get("recovery_kind") == "stalled_live_turn"
    ]
    assert len(events) == 1

    state = dict(app._turn_state.get(quest_id) or {})
    assert state.get("recovery_pending") is None
    assert state.get("recovery_watch_active") is None

def test_run_quest_turn_clears_active_run_when_assistant_append_fails(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("append failure cleanup quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    app.quest_service.set_continuation_state(quest_root, policy="none")

    app.quest_service.append_message(
        quest_id,
        role="user",
        content="Please inspect the failure path.",
        source="web-react",
    )

    class SuccessfulRunner:
        binary = ""

        def run(self, request):
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text="Assistant output should still clear runtime state.",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    app.runners["codex"] = SuccessfulRunner()

    original_append_message = app.quest_service.append_message

    def _broken_append_message(target_quest_id, role, content, source="local", **kwargs):  # noqa: ANN001
        if role == "assistant":
            raise RuntimeError("assistant append exploded")
        return original_append_message(target_quest_id, role, content, source=source, **kwargs)

    monkeypatch.setattr(app.quest_service, "append_message", _broken_append_message)

    app._turn_state[quest_id] = {"running": True, "pending": False, "reason": "user_message"}
    app._run_quest_turn(quest_id)

    snapshot = app.quest_service.snapshot(quest_id)
    assert snapshot["active_run_id"] is None
    assert snapshot["status"] == "active"

    events = app.quest_service.events(quest_id)["events"]
    assert any(
        item.get("type") == "runner.turn_postprocess_warning"
        and item.get("stage") == "append_message"
        for item in events
    )


def test_drain_turns_clears_running_state_after_worker_exception(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("turn drain exception quest")
    quest_id = quest["quest_id"]

    def _boom(_quest_id: str) -> None:
        raise RuntimeError("turn exploded")

    monkeypatch.setattr(app, "_run_quest_turn", _boom)

    app._turn_state[quest_id] = {"running": True, "pending": True, "reason": "user_message"}
    app._drain_turns(quest_id)

    state = dict(app._turn_state.get(quest_id) or {})
    assert state["running"] is False
    assert "worker" not in state


def test_daemon_auto_resumes_recent_reconciled_quest(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    first_app = DaemonApp(temp_home)
    quest = first_app.quest_service.create("auto recover recent quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    quest_yaml = read_yaml(quest_root / "quest.yaml", {})
    quest_yaml["status"] = "running"
    quest_yaml["active_run_id"] = "run-crashed-002"
    quest_yaml["updated_at"] = utc_now()
    write_yaml(quest_root / "quest.yaml", quest_yaml)
    runtime_state = read_json(quest_root / ".ds" / "runtime_state.json", {})
    runtime_state["status"] = "running"
    runtime_state["active_run_id"] = "run-crashed-002"
    runtime_state["last_transition_at"] = utc_now()
    write_json(quest_root / ".ds" / "runtime_state.json", runtime_state)

    app = DaemonApp(temp_home)

    class RecoveryRunner:
        binary = ""

        def __init__(self) -> None:
            self.requests: list[dict[str, str]] = []

        def run(self, request):
            self.requests.append(
                {
                    "run_id": request.run_id,
                    "message": request.message,
                    "turn_reason": request.turn_reason,
                }
            )
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            app.quest_service.mark_completed(request.quest_id)
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text="recovered",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    runner = RecoveryRunner()
    app.runners["codex"] = runner

    recovered = app._resume_reconciled_quests()
    assert any(item["quest_id"] == quest_id for item in recovered)

    deadline = time.time() + 3
    while time.time() < deadline:
        snapshot = app.quest_service.snapshot(quest_id)
        if snapshot["status"] == "completed" and runner.requests:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("auto recovery did not resume the stale quest")

    assert runner.requests[0]["turn_reason"] == "auto_continue"
    assert runner.requests[0]["message"] == ""

    history = app.quest_service.history(quest_id)
    assert any(
        "自动恢复" in str(item.get("content") or "")
        or "recovered automatically" in str(item.get("content") or "").lower()
        for item in history
        if str(item.get("source") or "") == "system-control"
    )
    events = app.quest_service.events(quest_id)["events"]
    assert any(item.get("type") == "quest.runtime_auto_resumed" for item in events)


def test_daemon_auto_resume_notifies_bound_connector(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    first_app = DaemonApp(temp_home)
    quest = first_app.quest_service.create("auto recover bound connector quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    first_app.quest_service.bind_source(quest_id, "qq:direct:RECOVER-USER-001")

    quest_yaml = read_yaml(quest_root / "quest.yaml", {})
    quest_yaml["status"] = "running"
    quest_yaml["active_run_id"] = "run-crashed-004"
    quest_yaml["updated_at"] = utc_now()
    write_yaml(quest_root / "quest.yaml", quest_yaml)
    runtime_state = read_json(quest_root / ".ds" / "runtime_state.json", {})
    runtime_state["status"] = "running"
    runtime_state["active_run_id"] = "run-crashed-004"
    runtime_state["last_transition_at"] = utc_now()
    write_json(quest_root / ".ds" / "runtime_state.json", runtime_state)

    app = DaemonApp(temp_home)

    class RecoveryRunner:
        binary = ""

        def run(self, request):
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            app.quest_service.mark_completed(request.quest_id)
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text="connector recovered",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    app.runners["codex"] = RecoveryRunner()

    sent: list[tuple[str, dict]] = []

    def fake_send_to_channel(channel_name, payload, *, connectors=None):  # noqa: ANN001
        sent.append((channel_name, dict(payload)))
        return True

    app.artifact_service._send_to_channel = fake_send_to_channel  # type: ignore[method-assign]

    recovered = app._resume_reconciled_quests()
    assert any(item["quest_id"] == quest_id for item in recovered)

    deadline = time.time() + 3
    while time.time() < deadline:
        qq_payloads = [item for item in sent if item[0] == "qq"]
        if qq_payloads:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("auto recovery did not notify the bound connector")

    _, outbound = qq_payloads[0]
    assert outbound["conversation_id"] == "qq:direct:RECOVER-USER-001"
    assert outbound["response_phase"] == "control"
    assert outbound["kind"] == "progress"
    assert "自动恢复" in str(outbound["message"] or "") or "recovered automatically" in str(outbound["message"] or "").lower()


def test_daemon_does_not_auto_resume_old_reconciled_quest(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    first_app = DaemonApp(temp_home)
    quest = first_app.quest_service.create("auto recover old quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    quest_yaml = read_yaml(quest_root / "quest.yaml", {})
    quest_yaml["status"] = "running"
    quest_yaml["active_run_id"] = "run-crashed-003"
    quest_yaml["updated_at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    write_yaml(quest_root / "quest.yaml", quest_yaml)
    runtime_state = read_json(quest_root / ".ds" / "runtime_state.json", {})
    runtime_state["status"] = "running"
    runtime_state["active_run_id"] = "run-crashed-003"
    runtime_state["last_transition_at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    write_json(quest_root / ".ds" / "runtime_state.json", runtime_state)

    app = DaemonApp(temp_home)

    assert any(item["quest_id"] == quest_id and item.get("recoverable") is False for item in app.reconciled_quests)
    assert app._resume_reconciled_quests() == []

    snapshot = app.quest_service.snapshot(quest_id)
    assert snapshot["status"] == "stopped"
    assert snapshot["active_run_id"] is None


def test_daemon_suppresses_auto_resume_after_repeated_crash_loop(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    first_app = DaemonApp(temp_home)
    quest = first_app.quest_service.create("auto recover suppression quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    first_app.quest_service.bind_source(quest_id, "qq:direct:RECOVER-SUPPRESS-001")

    quest_yaml = read_yaml(quest_root / "quest.yaml", {})
    quest_yaml["status"] = "running"
    quest_yaml["active_run_id"] = "run-crashed-005"
    quest_yaml["updated_at"] = utc_now()
    write_yaml(quest_root / "quest.yaml", quest_yaml)
    runtime_state = read_json(quest_root / ".ds" / "runtime_state.json", {})
    runtime_state["status"] = "running"
    runtime_state["active_run_id"] = "run-crashed-005"
    runtime_state["last_transition_at"] = utc_now()
    write_json(quest_root / ".ds" / "runtime_state.json", runtime_state)

    app = DaemonApp(temp_home)

    recent_auto_resume = {
        "event_id": "evt-recent-auto-resume",
        "type": "quest.runtime_auto_resumed",
        "quest_id": quest_id,
        "previous_status": "running",
        "abandoned_run_id": "run-old-auto-resume",
        "last_transition_at": utc_now(),
        "reason": "auto_continue",
        "scheduled": True,
        "started": True,
        "queued": False,
        "created_at": utc_now(),
    }
    append_jsonl(quest_root / ".ds" / "events.jsonl", recent_auto_resume)
    append_jsonl(quest_root / ".ds" / "events.jsonl", {**recent_auto_resume, "event_id": "evt-recent-auto-resume-2"})

    sent: list[tuple[str, dict]] = []

    def fake_send_to_channel(channel_name, payload, *, connectors=None):  # noqa: ANN001
        sent.append((channel_name, dict(payload)))
        return True

    app.artifact_service._send_to_channel = fake_send_to_channel  # type: ignore[method-assign]

    recovered = app._resume_reconciled_quests()
    assert recovered == []

    snapshot = app.quest_service.snapshot(quest_id)
    assert snapshot["status"] == "stopped"
    assert snapshot["active_run_id"] is None

    events = app.quest_service.events(quest_id)["events"]
    assert any(item.get("type") == "quest.runtime_auto_resume_suppressed" for item in events)
    assert any(channel == "qq" for channel, _payload in sent)
    assert any(
        "crash loop" in str(payload.get("message") or "").lower()
        or "重复崩溃" in str(payload.get("message") or "")
        for _channel, payload in sent
    )


def test_daemon_auto_resume_respects_persisted_retry_backoff_and_attempt_index(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    first_app = DaemonApp(temp_home)
    quest = first_app.quest_service.create("auto recover persisted retry backoff quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    quest_yaml = read_yaml(quest_root / "quest.yaml", {})
    quest_yaml["status"] = "running"
    quest_yaml["active_run_id"] = "run-crashed-retry-001"
    quest_yaml["updated_at"] = utc_now()
    write_yaml(quest_root / "quest.yaml", quest_yaml)
    runtime_state = read_json(quest_root / ".ds" / "runtime_state.json", {})
    runtime_state["status"] = "running"
    runtime_state["active_run_id"] = "run-crashed-retry-001"
    runtime_state["last_transition_at"] = utc_now()
    runtime_state["retry_state"] = {
        "turn_id": "turn-retry-recovery-001",
        "attempt_index": 2,
        "max_attempts": 5,
        "last_run_id": "run-failed-retry-002",
        "last_error": "previous retry failed",
        "next_retry_at": (datetime.now(UTC) + timedelta(seconds=0.35)).isoformat(),
    }
    write_json(quest_root / ".ds" / "runtime_state.json", runtime_state)

    app = DaemonApp(temp_home)

    class RecoveryRunner:
        binary = ""

        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def run(self, request):
            self.requests.append(
                {
                    "attempt_index": request.attempt_index,
                    "turn_id": request.turn_id,
                    "message": request.message,
                }
            )
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            app.quest_service.mark_completed(request.quest_id)
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text="recovered after persisted retry backoff",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    runner = RecoveryRunner()
    app.runners["codex"] = runner

    recovered = app._resume_reconciled_quests()
    assert any(item["quest_id"] == quest_id for item in recovered)
    recovered_item = next(item for item in recovered if item["quest_id"] == quest_id)
    assert recovered_item["scheduled"]["delayed"] is True
    assert float(recovered_item["scheduled"]["delay_seconds"]) > 0

    time.sleep(0.12)
    assert runner.requests == []

    deadline = time.time() + 3
    while time.time() < deadline:
        if runner.requests:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("persisted retry backoff did not resume after the stored delay")

    assert runner.requests[0]["attempt_index"] == 3
    assert runner.requests[0]["turn_id"] == "turn-retry-recovery-001"
    assert runner.requests[0]["message"] == ""


def test_daemon_auto_resume_keeps_in_progress_retry_attempt_index(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    first_app = DaemonApp(temp_home)
    quest = first_app.quest_service.create("auto recover in-progress retry quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    quest_yaml = read_yaml(quest_root / "quest.yaml", {})
    quest_yaml["status"] = "running"
    quest_yaml["active_run_id"] = "run-crashed-retry-ongoing-001"
    quest_yaml["updated_at"] = utc_now()
    write_yaml(quest_root / "quest.yaml", quest_yaml)
    runtime_state = read_json(quest_root / ".ds" / "runtime_state.json", {})
    runtime_state["status"] = "running"
    runtime_state["active_run_id"] = "run-crashed-retry-ongoing-001"
    runtime_state["last_transition_at"] = utc_now()
    runtime_state["retry_state"] = {
        "turn_id": "turn-retry-recovery-ongoing-001",
        "attempt_index": 3,
        "max_attempts": 5,
        "last_run_id": "run-retry-ongoing-003",
        "last_error": "runner crashed mid retry attempt",
        "next_retry_at": None,
    }
    write_json(quest_root / ".ds" / "runtime_state.json", runtime_state)

    app = DaemonApp(temp_home)

    class RecoveryRunner:
        binary = ""

        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def run(self, request):
            self.requests.append(
                {
                    "attempt_index": request.attempt_index,
                    "turn_id": request.turn_id,
                }
            )
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            app.quest_service.mark_completed(request.quest_id)
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text="recovered ongoing retry attempt",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    runner = RecoveryRunner()
    app.runners["codex"] = runner

    recovered = app._resume_reconciled_quests()
    assert any(item["quest_id"] == quest_id for item in recovered)
    recovered_item = next(item for item in recovered if item["quest_id"] == quest_id)
    assert recovered_item["scheduled"].get("delayed") in {None, False}

    deadline = time.time() + 3
    while time.time() < deadline:
        if runner.requests:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("in-progress retry recovery did not resume immediately")

    assert runner.requests[0]["attempt_index"] == 3
    assert runner.requests[0]["turn_id"] == "turn-retry-recovery-ongoing-001"


def test_daemon_reconcile_runtime_state_preserves_external_progress_policy_in_copilot(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("reconcile external progress quest", startup_contract={"workspace_mode": "copilot"})
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    app.quest_service.update_research_state(quest_root, workspace_mode="copilot")
    app.quest_service.update_runtime_state(
        quest_root=quest_root,
        status="running",
        active_run_id="run-external-progress",
        continuation_policy="when_external_progress",
        continuation_reason="background_external_progress_active",
    )

    reconciled = app.quest_service.reconcile_runtime_state()

    assert reconciled
    snapshot = app.quest_service.snapshot(quest_id)
    assert snapshot["status"] == "stopped"
    assert snapshot["continuation_policy"] == "when_external_progress"
    assert snapshot["continuation_reason"] == "background_external_progress_active"


def test_auto_continue_parks_after_repeated_unchanged_finalize_state(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("finalize auto park quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    app.quest_service.update_settings(quest_id, active_anchor="finalize")
    app.quest_service.set_continuation_state(
        quest_root,
        policy="auto",
        anchor="finalize",
        reason="finalize_loop_test",
    )

    app._normalize_status_after_turn(quest_id, turn_reason="auto_continue")
    first_snapshot = app.quest_service.snapshot(quest_id)
    assert first_snapshot["same_fingerprint_auto_turn_count"] == 1
    assert first_snapshot["continuation_policy"] == "auto"
    assert first_snapshot["continuation_reason"] == "autonomous_prepare_or_launch_long_run"

    app._normalize_status_after_turn(quest_id, turn_reason="auto_continue")
    second_snapshot = app.quest_service.snapshot(quest_id)
    assert second_snapshot["continuation_policy"] == "wait_for_user_or_resume"
    assert second_snapshot["continuation_reason"] == "unchanged_finalize_state"


def test_autonomous_auto_continue_keeps_running_without_external_progress(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("autonomous auto continue without external progress quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    app.quest_service.set_continuation_state(
        quest_root,
        policy="auto",
        anchor="experiment",
        reason="auto_loop_test",
    )

    app._normalize_status_after_turn(quest_id, turn_reason="user_message")
    snapshot = app.quest_service.snapshot(quest_id)

    assert snapshot["continuation_policy"] == "auto"
    assert snapshot["continuation_reason"] == "autonomous_prepare_or_launch_long_run"


def test_copilot_auto_continue_parks_without_external_progress(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create(
        "copilot auto continue without external progress quest",
        startup_contract={
            "workspace_mode": "copilot",
            "decision_policy": "user_gated",
            "launch_mode": "custom",
            "custom_profile": "freeform",
        },
    )
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    app.quest_service.set_continuation_state(
        quest_root,
        policy="auto",
        anchor="decision",
        reason="copilot_auto_loop_test",
    )

    app._normalize_status_after_turn(quest_id, turn_reason="user_message")
    snapshot = app.quest_service.snapshot(quest_id)

    assert snapshot["continuation_policy"] == "wait_for_user_or_resume"
    assert snapshot["continuation_reason"] == "copilot_mode"


def test_auto_continue_switches_to_external_progress_monitoring_when_bash_runs_exist(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("auto continue with bash progress quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    app.quest_service.set_continuation_state(
        quest_root,
        policy="auto",
        anchor="experiment",
        reason="external_progress_test",
    )
    context = McpContext(
        home=temp_home,
        quest_root=quest_root,
        quest_id=quest_id,
        run_id="run-external-progress",
        active_anchor="experiment",
        conversation_id=f"quest:{quest_id}",
        agent_role="pi",
        worker_id="worker-main",
        worktree_root=None,
        team_mode="single",
    )
    session = app.bash_exec_service.start_session(
        context,
        command="sleep 30",
        mode="detach",
    )
    assert session["status"] == "running"

    app._normalize_status_after_turn(quest_id, turn_reason="user_message")
    snapshot = app.quest_service.snapshot(quest_id)

    assert snapshot["continuation_policy"] == "when_external_progress"
    assert snapshot["continuation_reason"] == "background_external_progress_active"
    app.bash_exec_service.request_stop(quest_root, str(session["bash_id"]))


def test_daemon_retries_failed_runner_attempt_and_continues_with_retry_context(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    app.runners_config["codex"].update(
        {
            "retry_on_failure": True,
            "retry_max_attempts": 5,
            "retry_initial_backoff_sec": 0,
            "retry_backoff_multiplier": 2,
            "retry_max_backoff_sec": 0,
        }
    )
    quest = app.quest_service.create("retry success quest")
    quest_id = quest["quest_id"]

    class FlakyRunner:
        binary = ""

        def __init__(self) -> None:
            self.requests = []

        def run(self, request):
            self.requests.append(request)
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            if len(self.requests) == 1:
                return RunResult(
                    ok=False,
                    run_id=request.run_id,
                    model=request.model,
                    output_text="Partial answer before failure.",
                    exit_code=1,
                    history_root=history_root,
                    run_root=run_root,
                    stderr_text="temporary transport failure",
                )
            assert request.attempt_index == 2
            assert request.max_attempts == 5
            assert isinstance(request.retry_context, dict)
            assert request.retry_context["previous_run_id"] == self.requests[0].run_id
            assert "temporary transport failure" in str(request.retry_context["failure_summary"])
            assert "Partial answer before failure." in str(request.retry_context["previous_output_text"])
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text="Recovered answer after retry.",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    runner = FlakyRunner()
    app.runners["codex"] = runner

    payload = app.handlers.chat(quest_id, {"text": "Please continue reliably.", "source": "tui-ink"})
    assert payload["ok"] is True

    deadline = time.time() + 5
    while time.time() < deadline:
        history = app.quest_service.history(quest_id, limit=20)
        if any(
            str(item.get("role") or "") == "assistant"
            and str(item.get("content") or "") == "Recovered answer after retry."
            for item in history
        ):
            break
        time.sleep(0.05)
    else:
        raise AssertionError("retrying runner did not produce a recovered answer")

    assert len(runner.requests) == 2
    events = read_jsonl(Path(quest["quest_root"]) / ".ds" / "events.jsonl")
    assert any(item.get("type") == "runner.turn_retry_scheduled" for item in events)
    assert any(item.get("type") == "runner.turn_retry_started" for item in events)
    assert not any(
        str(item.get("role") or "") == "assistant"
        and str(item.get("content") or "") == "Partial answer before failure."
        for item in app.quest_service.history(quest_id, limit=20)
    )


def test_daemon_retry_policy_upgrades_legacy_codex_backoff_profile(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)

    policy = app._runner_retry_policy(
        "codex",
        {
            "retry_on_failure": True,
            "retry_max_attempts": 5,
            "retry_initial_backoff_sec": 1,
            "retry_backoff_multiplier": 2,
            "retry_max_backoff_sec": 8,
        },
    )

    assert policy["max_attempts"] == 7
    assert policy["initial_backoff_sec"] == 10.0
    assert policy["backoff_multiplier"] == 6.0
    assert policy["max_backoff_sec"] == 1800.0
    assert app._retry_delay_seconds(policy, attempt_index=2) == 10.0
    assert app._retry_delay_seconds(policy, attempt_index=3) == 60.0
    assert app._retry_delay_seconds(policy, attempt_index=4) == 360.0
    assert app._retry_delay_seconds(policy, attempt_index=5) == 1800.0
    assert app._retry_delay_seconds(policy, attempt_index=6) == 1800.0
    assert app._retry_delay_seconds(policy, attempt_index=7) == 1800.0


def test_daemon_retry_policy_upgrades_previous_default_codex_attempt_limit(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)

    policy = app._runner_retry_policy(
        "codex",
        {
            "retry_on_failure": True,
            "retry_max_attempts": 5,
            "retry_initial_backoff_sec": 10,
            "retry_backoff_multiplier": 6,
            "retry_max_backoff_sec": 1800,
        },
    )

    assert policy["max_attempts"] == 7
    assert policy["initial_backoff_sec"] == 10.0
    assert policy["backoff_multiplier"] == 6.0
    assert policy["max_backoff_sec"] == 1800.0


def test_daemon_retry_policy_preserves_custom_codex_backoff_profile(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)

    policy = app._runner_retry_policy(
        "codex",
        {
            "retry_on_failure": True,
            "retry_max_attempts": 4,
            "retry_initial_backoff_sec": 3,
            "retry_backoff_multiplier": 3,
            "retry_max_backoff_sec": 90,
        },
    )

    assert policy["max_attempts"] == 4
    assert policy["initial_backoff_sec"] == 3.0
    assert policy["backoff_multiplier"] == 3.0
    assert policy["max_backoff_sec"] == 90.0


def test_daemon_retry_exhausts_after_five_attempts(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    app.runners_config["codex"].update(
        {
            "retry_on_failure": True,
            "retry_max_attempts": 5,
            "retry_initial_backoff_sec": 0,
            "retry_backoff_multiplier": 2,
            "retry_max_backoff_sec": 0,
        }
    )
    quest = app.quest_service.create("retry exhausted quest")
    quest_id = quest["quest_id"]

    class AlwaysFailRunner:
        binary = ""

        def __init__(self) -> None:
            self.requests = []

        def run(self, request):
            self.requests.append(request)
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            return RunResult(
                ok=False,
                run_id=request.run_id,
                model=request.model,
                output_text="Partial failed output.",
                exit_code=1,
                history_root=history_root,
                run_root=run_root,
                stderr_text="persistent upstream failure",
            )

    runner = AlwaysFailRunner()
    app.runners["codex"] = runner

    payload = app.handlers.chat(quest_id, {"text": "Keep going until exhausted.", "source": "tui-ink"})
    assert payload["ok"] is True

    deadline = time.time() + 5
    while time.time() < deadline:
        snapshot = app.quest_service.snapshot(quest_id)
        events = read_jsonl(Path(quest["quest_root"]) / ".ds" / "events.jsonl")
        if (
            any(item.get("type") == "runner.turn_error" for item in events)
            and snapshot.get("retry_state") is None
            and str(snapshot.get("runtime_status") or "").strip() != "running"
        ):
            break
        time.sleep(0.05)
    else:
        raise AssertionError("retry sequence did not settle into a final error within the expected time")

    snapshot = app.quest_service.snapshot(quest_id)
    events = read_jsonl(Path(quest["quest_root"]) / ".ds" / "events.jsonl")

    assert len(runner.requests) == 5
    assert snapshot["runtime_status"] == "active"
    assert snapshot["status"] == "error"
    assert snapshot["retry_state"] is None
    assert any(item.get("type") == "runner.turn_error" for item in events)
    assert any(item.get("type") == "runner.turn_retry_exhausted" for item in events)
    assert not any(
        str(item.get("role") or "") == "assistant"
        and str(item.get("content") or "") == "Partial failed output."
        for item in app.quest_service.history(quest_id, limit=20)
    )


def test_daemon_skips_retry_for_non_retryable_minimax_protocol_error(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    app.runners_config["codex"].update(
        {
            "retry_on_failure": True,
            "retry_max_attempts": 5,
            "retry_initial_backoff_sec": 0,
            "retry_backoff_multiplier": 2,
            "retry_max_backoff_sec": 0,
        }
    )
    quest = app.quest_service.create("non retryable minimax protocol error quest")
    quest_id = quest["quest_id"]

    class DeterministicFailRunner:
        binary = ""

        def __init__(self) -> None:
            self.requests = []

        def run(self, request):
            self.requests.append(request)
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            return RunResult(
                ok=False,
                run_id=request.run_id,
                model=request.model,
                output_text="",
                exit_code=1,
                history_root=history_root,
                run_root=run_root,
                stderr_text='{"type":"error","error":{"type":"bad_request_error","message":"invalid params, tool call result does not follow tool call (2013)","http_code":"400"}}',
            )

    runner = DeterministicFailRunner()
    app.runners["codex"] = runner

    payload = app.handlers.chat(quest_id, {"text": "Please continue.", "source": "tui-ink"})
    assert payload["ok"] is True

    deadline = time.time() + 5
    while time.time() < deadline:
        snapshot = app.quest_service.snapshot(quest_id)
        events = read_jsonl(Path(quest["quest_root"]) / ".ds" / "events.jsonl")
        if any(item.get("type") == "runner.turn_error" for item in events):
            if snapshot.get("retry_state") is None and str(snapshot.get("display_status") or "").strip() == "error":
                break
        time.sleep(0.05)
    else:
        raise AssertionError("non-retryable failure did not settle into an immediate error state")

    snapshot = app.quest_service.snapshot(quest_id)
    events = read_jsonl(Path(quest["quest_root"]) / ".ds" / "events.jsonl")
    turn_errors = [item for item in events if item.get("type") == "runner.turn_error"]

    assert len(runner.requests) == 1
    assert snapshot["retry_state"] is None
    assert snapshot["continuation_policy"] == "wait_for_user_or_resume"
    assert snapshot["continuation_reason"] == "non_retryable_runner_error"
    assert snapshot["status"] == "error"
    assert snapshot["display_status"] == "error"
    assert not any(item.get("type") == "runner.turn_retry_scheduled" for item in events)
    assert turn_errors
    assert turn_errors[-1].get("diagnosis_code") == "minimax_tool_result_sequence_error"


def test_daemon_skips_retry_for_unknown_binary_attachment_extension_error(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    app.runners_config["codex"].update(
        {
            "retry_on_failure": True,
            "retry_max_attempts": 5,
            "retry_initial_backoff_sec": 0,
            "retry_backoff_multiplier": 2,
            "retry_max_backoff_sec": 0,
        }
    )
    quest = app.quest_service.create("non retryable binary attachment extension quest")
    quest_id = quest["quest_id"]

    class DeterministicBinaryExtensionRunner:
        binary = ""

        def __init__(self) -> None:
            self.requests = []

        def run(self, request):
            self.requests.append(request)
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            return RunResult(
                ok=False,
                run_id=request.run_id,
                model=request.model,
                output_text="",
                exit_code=1,
                history_root=history_root,
                run_root=run_root,
                stderr_text="unknown file extension: .png",
            )

    runner = DeterministicBinaryExtensionRunner()
    app.runners["codex"] = runner

    payload = app.handlers.chat(quest_id, {"text": "Please continue.", "source": "tui-ink"})
    assert payload["ok"] is True

    deadline = time.time() + 5
    while time.time() < deadline:
        snapshot = app.quest_service.snapshot(quest_id)
        events = read_jsonl(Path(quest["quest_root"]) / ".ds" / "events.jsonl")
        if any(item.get("type") == "runner.turn_error" for item in events):
            if snapshot.get("retry_state") is None and str(snapshot.get("display_status") or "").strip() == "error":
                break
        time.sleep(0.05)
    else:
        raise AssertionError("binary attachment extension failure did not settle into an immediate error state")

    snapshot = app.quest_service.snapshot(quest_id)
    events = read_jsonl(Path(quest["quest_root"]) / ".ds" / "events.jsonl")
    turn_errors = [item for item in events if item.get("type") == "runner.turn_error"]

    assert len(runner.requests) == 1
    assert snapshot["retry_state"] is None
    assert snapshot["continuation_policy"] == "wait_for_user_or_resume"
    assert snapshot["continuation_reason"] == "non_retryable_runner_error"
    assert snapshot["status"] == "error"
    assert snapshot["display_status"] == "error"
    assert not any(item.get("type") == "runner.turn_retry_scheduled" for item in events)
    assert turn_errors
    assert turn_errors[-1].get("diagnosis_code") == "runner_binary_attachment_path_unsupported"


def test_chat_reply_auto_links_interaction_and_resumes_with_decision_skill(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("artifact reply quest")
    quest_id = quest["quest_id"]

    class InteractiveRunner:
        binary = ""

        def __init__(self, artifact_service) -> None:
            self.artifact_service = artifact_service
            self.requests: list[dict[str, str]] = []

        def run(self, request):
            self.requests.append(
                {
                    "run_id": request.run_id,
                    "message": request.message,
                    "skill_id": request.skill_id,
                }
            )
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            if request.message == "Ask me A or B.":
                self.artifact_service.interact(
                    request.quest_root,
                    kind="decision_request",
                    message="先做A还是先做B？",
                    deliver_to_bound_conversations=False,
                    include_recent_inbound_messages=False,
                    options=[
                        {"id": "a", "label": "A"},
                        {"id": "b", "label": "B"},
                    ],
                    allow_free_text=False,
                )
                return RunResult(
                    ok=True,
                    run_id=request.run_id,
                    model=request.model,
                    output_text="Question sent.",
                    exit_code=0,
                    history_root=history_root,
                    run_root=run_root,
                    stderr_text="",
                )
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text=f"收到选择：{request.message}",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    runner = InteractiveRunner(app.artifact_service)
    app.runners["codex"] = runner

    initial_payload = app.handlers.chat(quest_id, {"text": "Ask me A or B.", "source": "tui-ink"})
    assert initial_payload["ok"] is True

    interaction_id = None
    deadline = time.time() + 3
    while time.time() < deadline:
        snapshot = app.quest_service.snapshot(quest_id)
        interactions = snapshot.get("active_interactions") or []
        if snapshot["status"] == "waiting_for_user" and interactions:
            interaction_id = interactions[-1]["interaction_id"]
            break
        time.sleep(0.05)
    else:
        raise AssertionError("decision_request was not persisted as a waiting interaction")

    reply_payload = app.handlers.chat(quest_id, {"text": "我选A。", "source": "tui-ink"})
    assert reply_payload["ok"] is True
    assert reply_payload["message"]["reply_to_interaction_id"] == interaction_id

    deadline = time.time() + 3
    while time.time() < deadline:
        history = app.quest_service.history(quest_id)
        if any(item.get("role") == "assistant" and item.get("content") == "收到选择：我选A。" for item in history):
            break
        time.sleep(0.05)
    else:
        raise AssertionError("assistant follow-up was not appended after the interaction reply")

    history = app.quest_service.history(quest_id)
    reply_record = next(item for item in history if item.get("role") == "user" and item.get("content") == "我选A。")
    assert reply_record["reply_to_interaction_id"] == interaction_id
    assert runner.requests[-1]["skill_id"] == "decision"

    deadline = time.time() + 3
    while time.time() < deadline:
        snapshot = app.quest_service.snapshot(quest_id)
        if snapshot["status"] == "active" and snapshot["active_run_id"] is None:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("quest did not settle back to active after handling the interaction reply")

    events = app.quest_service.events(quest_id)["events"]
    assert any(
        item.get("type") == "interaction.reply_received"
        and item.get("reply_to_interaction_id") == interaction_id
        for item in events
    )


def test_new_user_message_restarts_turn_after_error_display_status(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("resume after error")
    quest_id = quest["quest_id"]

    class OneShotFailRunner:
        binary = ""

        def __init__(self) -> None:
            self.requests = []

        def run(self, request):
            self.requests.append(request)
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            return RunResult(
                ok=False,
                run_id=request.run_id,
                model=request.model,
                output_text="forced upstream 403",
                exit_code=1,
                history_root=history_root,
                run_root=run_root,
                stderr_text="subscription missing",
            )

    runner = OneShotFailRunner()
    app.runners["codex"] = runner
    app.runners_config["codex"]["retry_on_failure"] = False
    app.runners_config["codex"]["retry_max_attempts"] = 1

    payload = app.handlers.chat(quest_id, {"text": "first try", "source": "web-react"})
    assert payload["ok"] is True

    deadline = time.time() + 5
    while time.time() < deadline:
        snapshot = app.quest_service.snapshot(quest_id)
        if len(runner.requests) == 1 and snapshot["runtime_status"] == "active" and snapshot["status"] == "error":
            break
        time.sleep(0.05)
    else:
        raise AssertionError("initial failing turn did not finish as expected")

    payload = app.handlers.chat(quest_id, {"text": "second try", "source": "web-react"})
    assert payload["ok"] is True

    deadline = time.time() + 5
    while time.time() < deadline:
        if len(runner.requests) >= 2:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("new user message did not restart the turn after error display status")

    assert runner.requests[0].message == "first try"
    assert runner.requests[1].message == "second try"


def test_daemon_auto_continue_starts_next_turn_without_replaying_last_user_message(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("auto continue quest")
    quest_id = quest["quest_id"]

    class AutoContinueRunner:
        binary = ""

        def __init__(self, app: DaemonApp) -> None:
            self.app = app
            self.requests: list[dict[str, str]] = []

        def run(self, request):
            self.requests.append(
                {
                    "run_id": request.run_id,
                    "message": request.message,
                    "skill_id": request.skill_id,
                    "turn_reason": request.turn_reason,
                }
            )
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            output_text = f"turn:{request.turn_reason or 'user_message'}"
            if len(self.requests) >= 2:
                self.app.quest_service.mark_completed(request.quest_id)
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text=output_text,
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    runner = AutoContinueRunner(app)
    app.runners["codex"] = runner

    app.handlers.chat(quest_id, {"text": "Keep going until the quest is done.", "source": "tui-ink"})

    deadline = time.time() + 3
    while time.time() < deadline:
        snapshot = app.quest_service.snapshot(quest_id)
        if snapshot["status"] == "completed" and len(runner.requests) >= 2:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("quest did not auto-continue into a second turn")

    assert runner.requests[0]["turn_reason"] == "user_message"
    assert runner.requests[0]["message"] == "Keep going until the quest is done."
    assert runner.requests[1]["turn_reason"] == "auto_continue"
    assert runner.requests[1]["message"] == ""


def test_daemon_does_not_auto_continue_while_waiting_for_blocking_user_decision(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("waiting quest")
    quest_id = quest["quest_id"]

    class WaitingRunner:
        binary = ""

        def __init__(self, artifact_service: ArtifactService) -> None:
            self.artifact_service = artifact_service
            self.requests: list[dict[str, str]] = []

        def run(self, request):
            self.requests.append(
                {
                    "run_id": request.run_id,
                    "message": request.message,
                    "skill_id": request.skill_id,
                    "turn_reason": request.turn_reason,
                }
            )
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            self.artifact_service.interact(
                request.quest_root,
                kind="decision_request",
                message="Please confirm whether I should stop here.",
                deliver_to_bound_conversations=False,
                include_recent_inbound_messages=False,
                reply_mode="blocking",
                reply_schema={"decision_type": "quest_completion_approval"},
            )
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text="Waiting for approval.",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    runner = WaitingRunner(app.artifact_service)
    app.runners["codex"] = runner

    app.handlers.chat(quest_id, {"text": "Finish if everything is done.", "source": "tui-ink"})

    deadline = time.time() + 3
    while time.time() < deadline:
        snapshot = app.quest_service.snapshot(quest_id)
        if snapshot["status"] == "waiting_for_user":
            break
        time.sleep(0.05)
    else:
        raise AssertionError("quest never entered waiting_for_user")

    time.sleep(0.25)
    assert len(runner.requests) == 1
    assert runner.requests[0]["turn_reason"] == "user_message"


def test_chat_reply_auto_links_latest_threaded_progress_without_forcing_decision_skill(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("threaded progress chat quest")
    quest_id = quest["quest_id"]

    class ThreadedRunner:
        binary = ""

        def __init__(self, artifact_service) -> None:
            self.artifact_service = artifact_service
            self.requests: list[dict[str, str]] = []

        def run(self, request):
            self.requests.append(
                {
                    "run_id": request.run_id,
                    "message": request.message,
                    "skill_id": request.skill_id,
                }
            )
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            if request.message == "Start the audit.":
                self.artifact_service.interact(
                    request.quest_root,
                    kind="progress",
                    message="老师，我已经开始审计仓库结构，下一步会确认依赖入口。",
                    deliver_to_bound_conversations=False,
                    include_recent_inbound_messages=False,
                )
                return RunResult(
                    ok=True,
                    run_id=request.run_id,
                    model=request.model,
                    output_text="Audit started.",
                    exit_code=0,
                    history_root=history_root,
                    run_root=run_root,
                    stderr_text="",
                )
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text=f"继续执行：{request.message}",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    runner = ThreadedRunner(app.artifact_service)
    app.runners["codex"] = runner

    initial_payload = app.handlers.chat(quest_id, {"text": "Start the audit.", "source": "tui-ink"})
    assert initial_payload["ok"] is True

    threaded_interaction_id = None
    deadline = time.time() + 3
    while time.time() < deadline:
        snapshot = app.quest_service.snapshot(quest_id)
        threaded_interaction_id = snapshot.get("default_reply_interaction_id")
        if threaded_interaction_id:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("threaded progress interaction was not persisted")

    reply_payload = app.handlers.chat(quest_id, {"text": "继续，先确认 requirements 和入口脚本。", "source": "web-react"})
    assert reply_payload["ok"] is True
    assert reply_payload["message"]["reply_to_interaction_id"] == threaded_interaction_id

    deadline = time.time() + 3
    while time.time() < deadline:
        history = app.quest_service.history(quest_id)
        if any(item.get("role") == "assistant" and item.get("content") == "继续执行：继续，先确认 requirements 和入口脚本。" for item in history):
            break
        time.sleep(0.05)
    else:
        raise AssertionError("assistant follow-up was not appended after threaded progress reply")

    assert runner.requests[-1]["skill_id"] != "decision"


def test_running_turn_consumes_queued_user_messages_via_artifact_without_duplicate_follow_up_turn(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("running mailbox quest")
    quest_id = quest["quest_id"]

    class MailboxRunner:
        binary = ""

        def __init__(self, artifact_service) -> None:
            self.artifact_service = artifact_service
            self.requests: list[str] = []
            self.started = threading.Event()
            self.mailbox_ready = threading.Event()
            self.mailbox_payloads: list[dict] = []

        def run(self, request):
            self.requests.append(request.message)
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            if request.message == "Start long task.":
                self.started.set()
                assert self.mailbox_ready.wait(timeout=3)
                mailbox = self.artifact_service.interact(
                    request.quest_root,
                    kind="progress",
                    message="老师，我先检查运行中的邮箱。",
                    deliver_to_bound_conversations=False,
                    include_recent_inbound_messages=True,
                )
                self.mailbox_payloads.append(mailbox)
                return RunResult(
                    ok=True,
                    run_id=request.run_id,
                    model=request.model,
                    output_text=mailbox["agent_instruction"],
                    exit_code=0,
                    history_root=history_root,
                    run_root=run_root,
                    stderr_text="",
                )
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text=f"unexpected extra turn: {request.message}",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

    runner = MailboxRunner(app.artifact_service)
    app.runners["codex"] = runner

    initial_payload = app.handlers.chat(quest_id, {"text": "Start long task.", "source": "tui-ink"})
    assert initial_payload["ok"] is True
    assert runner.started.wait(timeout=3)

    queued_payload = app.handlers.chat(
        quest_id,
        {"text": "Please also inspect config.", "source": "web-react"},
    )
    assert queued_payload["ok"] is True
    assert queued_payload["started"] is False
    assert queued_payload["queued"] is True

    runner.mailbox_ready.set()

    deadline = time.time() + 3
    while time.time() < deadline:
        history = app.quest_service.history(quest_id)
        if any(
            item.get("role") == "assistant"
            and "这是最新用户的要求" in str(item.get("content") or "")
            for item in history
        ):
            break
        time.sleep(0.05)
    else:
        raise AssertionError("mailbox delivery was not surfaced in the assistant output")

    assert runner.requests == ["Start long task."]
    assert len(runner.mailbox_payloads) == 1
    assert [item["text"] for item in runner.mailbox_payloads[0]["recent_inbound_messages"]] == [
        "Please also inspect config."
    ]
    snapshot = app.quest_service.snapshot(quest_id)
    assert snapshot["pending_user_message_count"] == 0


def test_status_formatter_includes_detailed_runtime_state(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("status detail quest")

    rendered = app._format_status(app.quest_service.snapshot(quest["quest_id"]))

    assert "Quest Status" in rendered
    assert "- quest_id:" in rendered
    assert "- quest_root:" in rendered
    assert "- runner:" in rendered
    assert "- history_count:" in rendered


def test_stop_then_user_text_continues_same_quest_context(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("stop and continue quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    class InterruptibleRunner:
        binary = ""

        def __init__(self) -> None:
            self.started = threading.Event()
            self.interrupted = threading.Event()
            self.seen_messages: list[str] = []

        def run(self, request):
            self.seen_messages.append(request.message)
            self.started.set()
            if request.message == "First long task.":
                while not self.interrupted.is_set():
                    time.sleep(0.05)
                history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
                run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
                return RunResult(
                    ok=False,
                    run_id=request.run_id,
                    model=request.model,
                    output_text="Interrupted.",
                    exit_code=130,
                    history_root=history_root,
                    run_root=run_root,
                    stderr_text="stopped by user",
                )
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text=f"Echo: {request.message}",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

        def interrupt(self, quest_id: str) -> bool:
            self.interrupted.set()
            return True

    runner = InterruptibleRunner()
    app.runners["codex"] = runner

    first_payload = app.handlers.chat(quest_id, {"text": "First long task.", "source": "tui-ink"})

    assert first_payload["ok"] is True
    assert runner.started.wait(timeout=2)

    stop_payload = app.handlers.quest_control(quest_id, {"action": "stop", "source": "tui-ink"})

    assert stop_payload["ok"] is True
    assert stop_payload["action"] == "stop"
    assert stop_payload["interrupted"] is True
    assert stop_payload["snapshot"]["status"] == "stopped"
    assert stop_payload["snapshot"]["pending_user_message_count"] == 0
    assert "DeepScientist" in str(stop_payload["notice"]["message"])
    assert "停止状态" in str(stop_payload["notice"]["message"])
    assert "发送任意新指令" in str(stop_payload["notice"]["message"])
    queue_after_stop = json.loads((quest_root / ".ds" / "user_message_queue.json").read_text(encoding="utf-8"))
    assert queue_after_stop["pending"] == []
    completed_status_by_id = {
        str(item.get("message_id") or ""): str(item.get("status") or "")
        for item in queue_after_stop["completed"]
    }
    assert completed_status_by_id[first_payload["message"]["id"]] == "accepted_by_run"

    follow_up = "Continue from the same quest context."
    next_payload = app.handlers.chat(quest_id, {"text": follow_up, "source": "tui-ink"})

    assert next_payload["ok"] is True
    assert next_payload["auto_resumed"] is True
    assert next_payload["previous_status"] == "stopped"

    deadline = time.time() + 3
    while time.time() < deadline:
        if follow_up in runner.seen_messages:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("follow-up user text was not delivered to the same quest runner")

    history = app.quest_service.history(quest_id)
    assert any(item.get("role") == "user" and item.get("content") == follow_up for item in history)
    assert any(
        item.get("role") == "assistant"
        and "DeepScientist" in str(item.get("content") or "")
        and "停止状态" in str(item.get("content") or "")
        for item in history
    )
    outbox_path = temp_home / "logs" / "connectors" / "local" / "outbox.jsonl"
    outbox = [json.loads(line) for line in outbox_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(
        "DeepScientist" in str(item.get("message") or "")
        and "停止状态" in str(item.get("message") or "")
        and "发送任意新指令" in str(item.get("message") or "")
        for item in outbox
    )


def test_stop_cancels_queued_mailbox_messages_and_preserves_audit(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home)
    quest = app.quest_service.create("stop queue cleanup quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    class InterruptibleRunner:
        binary = ""

        def __init__(self) -> None:
            self.started = threading.Event()
            self.interrupted = threading.Event()
            self.seen_messages: list[str] = []

        def run(self, request):
            self.seen_messages.append(request.message)
            self.started.set()
            history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
            run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
            if request.message == "Run the primary task.":
                while not self.interrupted.is_set():
                    time.sleep(0.05)
                return RunResult(
                    ok=False,
                    run_id=request.run_id,
                    model=request.model,
                    output_text="Interrupted.",
                    exit_code=130,
                    history_root=history_root,
                    run_root=run_root,
                    stderr_text="stopped by user",
                )
            return RunResult(
                ok=True,
                run_id=request.run_id,
                model=request.model,
                output_text=f"Echo: {request.message}",
                exit_code=0,
                history_root=history_root,
                run_root=run_root,
                stderr_text="",
            )

        def interrupt(self, target_quest_id: str) -> bool:
            self.interrupted.set()
            return True

    runner = InterruptibleRunner()
    app.runners["codex"] = runner

    initial_payload = app.handlers.chat(quest_id, {"text": "Run the primary task.", "source": "tui-ink"})
    assert initial_payload["ok"] is True
    assert runner.started.wait(timeout=2)

    queued_payload = app.handlers.chat(
        quest_id,
        {"text": "Please also inspect config.", "source": "web-react"},
    )
    assert queued_payload["ok"] is True
    assert queued_payload["queued"] is True

    stop_payload = app.handlers.quest_control(quest_id, {"action": "stop", "source": "tui-ink"})
    assert stop_payload["ok"] is True
    assert stop_payload["snapshot"]["status"] == "stopped"
    assert stop_payload["snapshot"]["pending_user_message_count"] == 1
    assert stop_payload["cancelled_pending_user_message_count"] == 0

    queue_after_stop = json.loads((quest_root / ".ds" / "user_message_queue.json").read_text(encoding="utf-8"))
    assert [item["message_id"] for item in queue_after_stop["pending"]] == [queued_payload["message"]["id"]]
    completed_status_by_id = {
        str(item.get("message_id") or ""): str(item.get("status") or "")
        for item in queue_after_stop["completed"]
    }
    assert completed_status_by_id[initial_payload["message"]["id"]] == "accepted_by_run"
    assert queued_payload["message"]["id"] not in completed_status_by_id

    follow_up = app.handlers.chat(quest_id, {"text": "Continue cleanly.", "source": "tui-ink"})
    assert follow_up["ok"] is True

    deadline = time.time() + 3
    while time.time() < deadline:
        if "Continue cleanly." in runner.seen_messages:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("fresh post-stop turn was not started")

    assert runner.seen_messages == ["Run the primary task.", "Continue cleanly."]


def test_delete_qq_connector_profile_removes_profile_and_unbinds_related_quest(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["profiles"] = [
        {
            "profile_id": "qq-alpha",
            "bot_name": "DeepScientist",
            "app_id": "1903299925",
            "app_secret": "qq-secret",
            "main_chat_id": "OPENID-ALPHA",
        }
    ]
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("qq profile delete quest")
    result = app.update_quest_connector_binding(quest["quest_id"], "qq", "qq:direct:OPENID-ALPHA")
    assert not isinstance(result, tuple)

    profile_root = temp_home / "logs" / "connectors" / "qq" / "profiles" / "qq-alpha"
    profile_root.mkdir(parents=True, exist_ok=True)
    (profile_root / "gateway.json").write_text('{"last_conversation_id":"qq:direct:OPENID-ALPHA"}', encoding="utf-8")
    (temp_home / "logs" / "connectors" / "qq" / "state.json").write_text(
        json.dumps(
            {
                "last_conversation_id": "qq:direct:OPENID-ALPHA",
                "recent_conversations": [
                    {
                        "conversation_id": "qq:direct:OPENID-ALPHA",
                        "profile_id": "qq-alpha",
                    }
                ],
                "known_targets": [
                    {
                        "conversation_id": "qq:direct:OPENID-ALPHA",
                        "profile_id": "qq-alpha",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    deleted = app.delete_connector_profile("qq", "qq-alpha")
    assert not isinstance(deleted, tuple)
    assert deleted["ok"] is True
    assert deleted["deleted"] is True
    assert deleted["deleted_bound_conversations"] == ["qq:direct:OPENID-ALPHA"]

    connectors_after = manager.load_named_normalized("connectors")
    assert list_qq_profiles(connectors_after["qq"]) == []
    assert connectors_after["qq"]["enabled"] is False
    assert app.list_connector_bindings("qq") == []
    assert app.quest_service.binding_sources(quest["quest_id"]) == ["local:default"]
    assert not profile_root.exists()


def test_delete_generic_connector_profile_keeps_other_profiles_and_cleans_bindings(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["telegram"]["enabled"] = True
    connectors["telegram"]["profiles"] = [
        {
            "profile_id": "telegram-alpha",
            "bot_name": "Alpha",
            "bot_token": "token-alpha",
        },
        {
            "profile_id": "telegram-beta",
            "bot_name": "Beta",
            "bot_token": "token-beta",
        },
    ]
    write_yaml(manager.path_for("connectors"), connectors)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create("telegram profile delete quest")
    conversation_id = format_conversation_id("telegram", "direct", "123456", profile_id="telegram-beta")
    result = app.update_quest_connector_binding(quest["quest_id"], "telegram", conversation_id)
    assert not isinstance(result, tuple)

    profile_root = temp_home / "logs" / "connectors" / "telegram" / "profiles" / "telegram-beta"
    profile_root.mkdir(parents=True, exist_ok=True)
    (profile_root / "runtime.json").write_text(f'{{"last_conversation_id":"{conversation_id}"}}', encoding="utf-8")

    deleted = app.delete_connector_profile("telegram", "telegram-beta")
    assert not isinstance(deleted, tuple)
    assert deleted["ok"] is True
    assert deleted["remaining_profile_count"] == 1

    connectors_after = manager.load_named_normalized("connectors")
    profiles_after = list_connector_profiles("telegram", connectors_after["telegram"])
    assert [str(item.get("profile_id")) for item in profiles_after] == ["telegram-alpha"]
    assert connectors_after["telegram"]["enabled"] is True
    assert app.list_connector_bindings("telegram") == []
    assert app.quest_service.binding_sources(quest["quest_id"]) == ["local:default"]
    assert not profile_root.exists()



def test_run_create_falls_back_to_enabled_default_runner_when_snapshot_runner_disabled(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    config = manager.load_named('config')
    config['default_runner'] = 'claude'
    write_yaml(manager.path_for('config'), config)

    runners = manager.load_named('runners')
    runners['codex']['enabled'] = False
    runners['claude']['enabled'] = True
    write_yaml(manager.path_for('runners'), runners)

    app = DaemonApp(temp_home)
    quest = app.quest_service.create('runner fallback quest', runner='codex')
    quest_id = quest['quest_id']

    captured: dict[str, object] = {}

    class _StubRunner:
        def run(self, request):
            captured['model'] = request.model
            captured['message'] = request.message
            return type('Result', (), {
                'ok': True,
                'run_id': request.run_id,
                'model': request.model,
                'exit_code': 0,
                'history_root': temp_home,
                'run_root': temp_home,
                'output_text': 'HELLO',
                'stderr_text': '',
            })()

    monkeypatch.setattr(app, 'get_runner', lambda name: captured.setdefault('runner_name', name) or _StubRunner())

    payload = app.handlers.run_create(
        quest_id,
        {
            'message': 'Reply with exactly HELLO.',
            'skill_id': 'decision',
        },
    )

    assert payload['ok'] is True
    assert payload['runner'] == 'claude'
    assert captured['runner_name'] == 'claude'



def test_create_quest_uses_current_global_default_runner(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    config = manager.load_named('config')
    config['default_runner'] = 'claude'
    write_yaml(manager.path_for('config'), config)

    app = DaemonApp(temp_home)
    snapshot = app.create_quest(goal='create quest runner check', source='web')

    assert snapshot['runner'] == 'claude'
    quest_yaml = read_yaml(temp_home / 'quests' / snapshot['quest_id'] / 'quest.yaml', {})
    assert quest_yaml['default_runner'] == 'claude'
