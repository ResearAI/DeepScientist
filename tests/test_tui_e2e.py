from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import shlex
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

import pytest

# Imported lazily: pexpect is only needed by these TUI end-to-end tests.
# A module-level `import pexpect` runs before the skipif mark below, so on an
# install without it pytest aborts collection of the whole suite instead of
# skipping this one file.
pexpect = pytest.importorskip("pexpect")


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which("script") is None, reason="`script` is required for TUI e2e tests")


@pytest.fixture(scope="session", autouse=True)
def build_tui_bundle() -> None:
    subprocess.run(
        ["npm", "--prefix", "src/tui", "run", "build"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


RouteHandler = Callable[[dict[str, Any], dict[str, Any] | None], Any]


@dataclass
class MockDaemon:
    state: dict[str, Any]
    get_routes: dict[str, RouteHandler] = field(default_factory=dict)
    post_routes: dict[str, RouteHandler] = field(default_factory=dict)
    put_routes: dict[str, RouteHandler] = field(default_factory=dict)
    server: ThreadingHTTPServer | None = None
    thread: threading.Thread | None = None
    base_url: str = ""

    def __enter__(self) -> "MockDaemon":
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            host, port = sock.getsockname()

        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                return

            def _read_json(self) -> dict[str, Any] | None:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0:
                    return None
                raw = self.rfile.read(length).decode("utf-8")
                return json.loads(raw) if raw else None

            def _send_json(self, payload: Any, status: int = 200) -> None:
                encoded = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def _dispatch(self, routes: dict[str, RouteHandler]) -> None:
                handler = routes.get(self.path)
                if handler is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                result = handler(parent.state, self._read_json())
                if isinstance(result, tuple) and len(result) == 2:
                    status, payload = result
                else:
                    status, payload = 200, result
                self._send_json(payload, status=status)

            def do_GET(self) -> None:
                self._dispatch(parent.get_routes)

            def do_POST(self) -> None:
                self._dispatch(parent.post_routes)

            def do_PUT(self) -> None:
                self._dispatch(parent.put_routes)

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{port}"
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2)


@contextmanager
def spawn_tui(base_url: str, args: list[str] | None = None, env_overrides: dict[str, str] | None = None) -> Any:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    env["DEEPSCIENTIST_ALT_BUFFER"] = "0"
    env["DEEPSCIENTIST_INCREMENTAL_RENDER"] = "0"
    env["TERM"] = "xterm-256color"
    env["COLUMNS"] = "120"
    env["LINES"] = "45"
    env["FORCE_COLOR"] = "0"
    env["NO_COLOR"] = "1"
    extra_args = " ".join(shlex.quote(arg) for arg in (args or []))
    command = f"node src/tui/dist/index.js --base-url {shlex.quote(base_url)}{f' {extra_args}' if extra_args else ''}"
    child = pexpect.spawn(
        "script",
        ["-qfec", command, "/dev/null"],
        cwd=str(ROOT),
        env=env,
        encoding="utf-8",
        timeout=20,
    )
    try:
        yield child
    finally:
        if child.isalive():
            child.sendcontrol("c")
            try:
                child.expect(pexpect.EOF, timeout=5)
            except (pexpect.EOF, pexpect.TIMEOUT):
                child.close(force=True)


def press_enter(child: pexpect.spawn) -> None:
    child.send("\r")


def press_down(child: pexpect.spawn, count: int = 1) -> None:
    for _ in range(count):
        child.send("\x1b[B")


def press_up(child: pexpect.spawn, count: int = 1) -> None:
    for _ in range(count):
        child.send("\x1b[A")


def open_config_root(child: pexpect.spawn) -> None:
    child.expect("request mode")
    child.sendcontrol("g")
    child.expect("Choose a config area")


def default_quest_routes() -> dict[str, RouteHandler]:
    return {
        "/api/quests": lambda _state, _body: [],
    }


def default_connector_routes(state: dict[str, Any]) -> dict[str, RouteHandler]:
    return {
        "/api/connectors": lambda current, _body: current.get("connector_snapshots", []),
        "/api/config/files": lambda _current, _body: state.get("config_files", []),
    }


def test_tui_non_tty_does_not_throw_raw_mode_error() -> None:
    process = subprocess.Popen(
        ["node", "src/tui/dist/index.js", "--base-url", "http://127.0.0.1:9"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        time.sleep(1.5)
        process.terminate()
        output, _ = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        output, _ = process.communicate(timeout=5)

    assert "Raw mode is not supported" not in output


def test_tui_new_command_creates_and_auto_starts_quest() -> None:
    state: dict[str, Any] = {
        "quests": [],
        "created_bodies": [],
    }

    def list_quests(current: dict[str, Any], _body: dict[str, Any] | None) -> list[dict[str, Any]]:
        return current["quests"]

    def create_quest(current: dict[str, Any], body: dict[str, Any] | None) -> dict[str, Any]:
        assert body is not None
        current["created_bodies"].append(body)
        snapshot = {
            "quest_id": "q-001",
            "title": body["goal"],
            "status": "running",
            "active_anchor": "decision",
            "branch": "main",
            "quest_root": "/tmp/q-001",
        }
        current["quests"] = [snapshot]
        return {"ok": True, "snapshot": snapshot, "startup": {"ok": True}}

    get_routes = {
        "/api/quests": list_quests,
        **default_connector_routes(state),
        "/api/quests/q-001/session": lambda current, _body: {
            "ok": True,
            "quest_id": "q-001",
            "snapshot": current["quests"][0],
            "acp_session": {"session_id": "quest:q-001", "slash_commands": []},
        },
        "/api/quests/q-001/events?after=0&format=acp&session_id=quest%3Aq-001&limit=160&tail=1": lambda _current, _body: {
            "cursor": 0,
            "acp_updates": [],
        },
    }
    post_routes = {
        "/api/quests": create_quest,
    }

    with MockDaemon(state=state, get_routes=get_routes, post_routes=post_routes) as daemon:
        with spawn_tui(daemon.base_url) as child:
            child.expect("request mode")
            child.send("/new Audit benchmark pipeline")
            press_enter(child)
            child.expect("q-001")

    assert state["created_bodies"] == [
        {
            "goal": "Audit benchmark pipeline",
            "source": "tui-ink",
            "auto_start": True,
            "initial_message": "Audit benchmark pipeline",
        }
    ]


def test_tui_benchstore_command_lists_catalog() -> None:
    state: dict[str, Any] = {}
    get_routes = {
        **default_quest_routes(),
        **default_connector_routes(state),
        "/api/benchstore/entries": lambda _current, _body: {
            "ok": True,
            "total": 1,
            "device_summary": "test device",
            "items": [
                {
                    "id": "toy.bench",
                    "name": "Toy Benchmark",
                    "one_line": "Small benchmark fixture",
                    "snapshot_status": "runnable",
                }
            ],
        },
    }

    with MockDaemon(state=state, get_routes=get_routes) as daemon:
        with spawn_tui(daemon.base_url) as child:
            child.expect("request mode")
            child.send("/benchstore")
            press_enter(child)
            child.expect("BenchStore")
            child.expect("toy.bench")
            child.expect("Small benchmark fixture")


def test_tui_doctor_command_starts_system_task() -> None:
    state: dict[str, Any] = {"doctor_started": 0}

    def start_doctor(current: dict[str, Any], _body: dict[str, Any] | None) -> dict[str, Any]:
        current["doctor_started"] += 1
        return {
            "ok": True,
            "task": {
                "task_id": "admintask-doctor-001",
                "kind": "doctor",
                "status": "running",
                "current_step": "collecting",
                "message": "Doctor is running.",
            },
        }

    with MockDaemon(
        state=state,
        get_routes={**default_quest_routes(), **default_connector_routes(state)},
        post_routes={"/api/system/tasks/doctor": start_doctor},
    ) as daemon:
        with spawn_tui(daemon.base_url) as child:
            child.expect("request mode")
            child.send("/doctor")
            press_enter(child)
            child.expect("Task admintask-doctor-001")
            child.expect("doctor")
            child.expect("running")

    assert state["doctor_started"] == 1


def test_tui_unknown_slash_command_is_blocked_locally() -> None:
    state: dict[str, Any] = {}
    with MockDaemon(state=state, get_routes={**default_quest_routes(), **default_connector_routes(state)}) as daemon:
        with spawn_tui(daemon.base_url) as child:
            child.expect("request mode")
            child.send("/missing-command")
            press_enter(child)
            child.expect("Unknown TUI Command")
            child.expect("blocked locally")


def test_tui_debug_mode_exposes_route_snapshot_and_logs(tmp_path: Path) -> None:
    state: dict[str, Any] = {}
    debug_log = tmp_path / 'tui-debug.jsonl'
    with MockDaemon(state=state, get_routes={**default_quest_routes(), **default_connector_routes(state)}) as daemon:
        with spawn_tui(
            daemon.base_url,
            args=['--debug', '--debug-log', str(debug_log)],
        ) as child:
            child.expect("debug · surface: home")

            child.send("/config")
            press_enter(child)
            child.expect("debug · surface: config:root:browse")
            child.expect("Web Settings")

            child.send("\x1b")
            child.expect("Config browser closed.")

            child.send("/debug")
            press_enter(child)
            child.expect("TUI Debug")
            child.expect("kind: local-debug")
            child.expect("target: debug inspector")
            child.expect("debug · surface: utility:debug")
            child.expect("Web Settings > diagnostics / audit")

    lines = debug_log.read_text(encoding='utf-8').strip().splitlines()
    assert lines, "debug logging should produce at least one snapshot"
    snapshot = json.loads(lines[-1])
    assert snapshot["surface"] == "utility:debug"
    assert snapshot["web_analog"] == "Web Settings > diagnostics / audit"
    assert snapshot["utility_panel_kind"] == "debug"
    assert snapshot["counts"]["utility_lines"] > 0
    assert snapshot["screen"]["main"].startswith("Utility panel")


def test_tui_debug_log_redacts_config_editor_buffers(tmp_path: Path) -> None:
    secret = "SUPERSECRET-TUI-DEBUG-TOKEN"
    state: dict[str, Any] = {
        "config_files": [
            {
                "name": "config",
                "path": "/tmp/config.yaml",
                "required": True,
                "exists": True,
            }
        ],
        "config_document": {
            "document_id": "config::config",
            "title": "config.yaml",
            "path": "/tmp/config.yaml",
            "writable": True,
            "content": f"deepxiv:\n  token: {secret}\n",
            "revision": "cfg-rev-debug-redaction",
        },
    }
    debug_log = tmp_path / "tui-debug-redacted.jsonl"

    get_routes = {
        **default_quest_routes(),
        **default_connector_routes(state),
        "/api/config/config": lambda current, _body: current["config_document"],
    }

    with MockDaemon(state=state, get_routes=get_routes) as daemon:
        with spawn_tui(
            daemon.base_url,
            args=["--debug", "--debug-log", str(debug_log)],
        ) as child:
            open_config_root(child)
            press_down(child)
            press_enter(child)
            child.expect("Global Config Files")
            press_enter(child)
            child.expect("Config Editor")
            child.expect("debug · surface: config:files:edit")
            child.expect("redacted")
            child.sendcontrol("d")
            child.expect("TUI Debug")
            child.expect("raw: \\[redacted:")
            child.expect("input visible: yes")
            child.send("\x1b")
            child.expect("Config Editor")
            child.expect("debug · surface: config:files:edit")

    log_text = debug_log.read_text(encoding="utf-8")
    assert secret not in log_text
    snapshots = [json.loads(line) for line in log_text.strip().splitlines() if line.strip()]
    editor_snapshots = [item for item in snapshots if item.get("surface") == "config:files:edit"]
    assert editor_snapshots, "debug logging should capture the config editor state"
    latest_editor = editor_snapshots[-1]
    assert latest_editor["input"]["redacted"] is True
    assert latest_editor["input"]["raw"].startswith("[redacted:")
    assert latest_editor["route"]["arg"].startswith("[redacted:")
    assert latest_editor["screen"]["input_redacted"] is True


def test_tui_backspace_deletes_input_in_config_editor() -> None:
    state: dict[str, Any] = {
        "config_files": [
            {
                "name": "config",
                "path": "/tmp/config.yaml",
                "required": True,
                "exists": True,
            }
        ],
        "config_document": {
            "document_id": "config::config",
            "title": "config.yaml",
            "path": "/tmp/config.yaml",
            "writable": True,
            "content": "seed: true\n",
            "revision": "cfg-rev-bs-1",
        },
        "saved_requests": [],
    }

    def get_config_document(current: dict[str, Any], _body: dict[str, Any] | None) -> dict[str, Any]:
        return current["config_document"]

    def save_config(current: dict[str, Any], body: dict[str, Any] | None) -> dict[str, Any]:
        assert body is not None
        current["saved_requests"].append(body)
        current["config_document"] = {
            **current["config_document"],
            "content": body["content"],
            "revision": "cfg-rev-bs-2",
        }
        return {"ok": True, "revision": "cfg-rev-bs-2"}

    get_routes = {
        **default_quest_routes(),
        **default_connector_routes(state),
        "/api/config/config": get_config_document,
    }
    put_routes = {
        "/api/config/config": save_config,
    }

    with MockDaemon(state=state, get_routes=get_routes, put_routes=put_routes) as daemon:
        with spawn_tui(daemon.base_url) as child:
            open_config_root(child)
            press_down(child)
            child.expect("> 2. Global Config Files")
            press_enter(child)
            child.expect("Global Config Files")
            press_enter(child)
            child.expect("Config Editor")

            child.send("ABCDE")
            child.send("\x7f" * 2)
            child.send("\r")
            child.expect("Saved config.yaml")

    assert len(state["saved_requests"]) == 1
    assert state["saved_requests"][0]["content"] == "seed: true\nABC"



def test_tui_can_edit_and_save_global_config_files() -> None:
    state: dict[str, Any] = {
        "config_files": [
            {
                "name": "config",
                "path": "/tmp/config.yaml",
                "required": True,
                "exists": True,
            }
        ],
        "config_document": {
            "document_id": "config::config",
            "title": "config.yaml",
            "path": "/tmp/config.yaml",
            "writable": True,
            "content": "foo: old\nbar: 1\n",
            "revision": "cfg-rev-1",
        },
        "saved_requests": [],
    }

    def get_config_document(current: dict[str, Any], _body: dict[str, Any] | None) -> dict[str, Any]:
        return current["config_document"]

    def save_config(current: dict[str, Any], body: dict[str, Any] | None) -> dict[str, Any]:
        assert body is not None
        current["saved_requests"].append(body)
        current["config_document"] = {
            **current["config_document"],
            "content": body["content"],
            "revision": "cfg-rev-2",
        }
        return {"ok": True, "revision": "cfg-rev-2"}

    get_routes = {
        **default_quest_routes(),
        **default_connector_routes(state),
        "/api/config/config": get_config_document,
    }
    put_routes = {
        "/api/config/config": save_config,
    }

    with MockDaemon(state=state, get_routes=get_routes, put_routes=put_routes) as daemon:
        with spawn_tui(daemon.base_url) as child:
            open_config_root(child)
            press_down(child)
            child.expect("> 2. Global Config Files")
            press_enter(child)
            child.expect("Global Config Files")
            press_enter(child)
            child.expect("Config Editor")

            child.send("\x7f" * 50)
            child.send("foo: new")
            child.sendcontrol("j")
            child.send("bar: 2")
            press_enter(child)

            child.expect("Saved config.yaml")

    assert state["saved_requests"] == [{"content": "foo: new\nbar: 2", "revision": "cfg-rev-1"}]


def test_tui_bracketed_paste_preserves_multiline_content() -> None:
    state: dict[str, Any] = {
        "config_files": [
            {
                "name": "config",
                "path": "/tmp/config.yaml",
                "required": True,
                "exists": True,
            }
        ],
        "config_document": {
            "document_id": "config::config",
            "title": "config.yaml",
            "path": "/tmp/config.yaml",
            "writable": True,
            "content": "seed: true\n",
            "revision": "cfg-rev-paste-1",
        },
        "saved_requests": [],
    }

    def get_config_document(current: dict[str, Any], _body: dict[str, Any] | None) -> dict[str, Any]:
        return current["config_document"]

    def save_config(current: dict[str, Any], body: dict[str, Any] | None) -> dict[str, Any]:
        assert body is not None
        current["saved_requests"].append(body)
        current["config_document"] = {
            **current["config_document"],
            "content": body["content"],
            "revision": "cfg-rev-paste-2",
        }
        return {"ok": True, "revision": "cfg-rev-paste-2"}

    get_routes = {
        **default_quest_routes(),
        **default_connector_routes(state),
        "/api/config/config": get_config_document,
    }
    put_routes = {
        "/api/config/config": save_config,
    }

    with MockDaemon(state=state, get_routes=get_routes, put_routes=put_routes) as daemon:
        with spawn_tui(daemon.base_url) as child:
            open_config_root(child)
            press_down(child)
            child.expect("> 2. Global Config Files")
            press_enter(child)
            child.expect("Global Config Files")
            press_enter(child)
            child.expect("Config Editor")

            child.send("\x7f" * 40)
            child.send("\x1b[200~alpha: 1\r\nbeta: 2\r\ngamma: 3\x1b[201~")
            child.expect("   1 alpha: 1")
            child.expect("   2 beta: 2")
            child.expect("   3 gamma: 3")
            press_enter(child)
            child.expect("Saved config.yaml")

    assert state["saved_requests"] == [{"content": "alpha: 1\nbeta: 2\ngamma: 3", "revision": "cfg-rev-paste-1"}]


def test_tui_fragmented_bracketed_paste_preserves_multiline_content() -> None:
    state: dict[str, Any] = {
        "config_files": [
            {
                "name": "config",
                "path": "/tmp/config.yaml",
                "required": True,
                "exists": True,
            }
        ],
        "config_document": {
            "document_id": "config::config",
            "title": "config.yaml",
            "path": "/tmp/config.yaml",
            "writable": True,
            "content": "seed: true\n",
            "revision": "cfg-rev-fragmented-paste-1",
        },
        "saved_requests": [],
    }

    def get_config_document(current: dict[str, Any], _body: dict[str, Any] | None) -> dict[str, Any]:
        return current["config_document"]

    def save_config(current: dict[str, Any], body: dict[str, Any] | None) -> dict[str, Any]:
        assert body is not None
        current["saved_requests"].append(body)
        current["config_document"] = {
            **current["config_document"],
            "content": body["content"],
            "revision": "cfg-rev-fragmented-paste-2",
        }
        return {"ok": True, "revision": "cfg-rev-fragmented-paste-2"}

    get_routes = {
        **default_quest_routes(),
        **default_connector_routes(state),
        "/api/config/config": get_config_document,
    }
    put_routes = {
        "/api/config/config": save_config,
    }

    with MockDaemon(state=state, get_routes=get_routes, put_routes=put_routes) as daemon:
        with spawn_tui(daemon.base_url) as child:
            open_config_root(child)
            press_down(child)
            child.expect("> 2. Global Config Files")
            press_enter(child)
            child.expect("Global Config Files")
            press_enter(child)
            child.expect("Config Editor")

            child.send("\x7f" * 40)
            child.send("[20")
            child.send("0~alpha: 1\r")
            child.send("\n")
            child.send("beta: 2\r\n")
            child.send("gamma: 3")
            child.send("[201")
            child.send("~")
            child.expect("   1 alpha: 1")
            child.expect("   2 beta: 2")
            child.expect("   3 gamma: 3")
            press_enter(child)
            child.expect("Saved config.yaml")

    assert state["saved_requests"] == [{"content": "alpha: 1\nbeta: 2\ngamma: 3", "revision": "cfg-rev-fragmented-paste-1"}]


def test_tui_lingzhu_connector_edit_generates_ak_and_saves_selected_connector() -> None:
    state: dict[str, Any] = {
        "connector_structured": {
            "qq": {
                "bot_name": "QQ Bot",
                "app_id": "qq-app-1",
                "command_prefix": "/",
            },
            "weixin": {
                "enabled": False,
            },
            "lingzhu": {},
        },
        "connector_revision": "connector-rev-1",
        "connector_saves": [],
    }

    def connector_snapshots(current: dict[str, Any]) -> list[dict[str, Any]]:
        lingzhu = current["connector_structured"].get("lingzhu", {})
        return [
            {
                "name": "qq",
                "enabled": True,
                "connection_state": "idle",
                "binding_count": 0,
                "target_count": 0,
            },
            {
                "name": "weixin",
                "enabled": bool(current["connector_structured"].get("weixin", {}).get("enabled")),
                "connection_state": "idle",
                "binding_count": 0,
                "target_count": 0,
            },
            {
                "name": "lingzhu",
                "enabled": bool(lingzhu),
                "connection_state": "idle",
                "binding_count": 0,
                "target_count": 0,
                "details": {
                    "public_endpoint_url": "https://demo.example/sse",
                    "public_health_url": "https://demo.example/health",
                    "endpoint_url": "http://127.0.0.1:20999/connectors/lingzhu/sse",
                    "health_url": "http://127.0.0.1:20999/connectors/lingzhu/health",
                },
            },
        ]

    def get_connectors_document(current: dict[str, Any], _body: dict[str, Any] | None) -> dict[str, Any]:
        current["connector_snapshots"] = connector_snapshots(current)
        return {
            "document_id": "config::connectors",
            "title": "connectors.yaml",
            "path": "/tmp/connectors.yaml",
            "writable": True,
            "content": "connectors:\n",
            "revision": current["connector_revision"],
            "meta": {
                "structured_config": current["connector_structured"],
            },
        }

    def save_connectors(current: dict[str, Any], body: dict[str, Any] | None) -> dict[str, Any]:
        assert body is not None
        current["connector_saves"].append(body)
        current["connector_structured"] = body["structured"]
        current["connector_revision"] = "connector-rev-2"
        current["connector_snapshots"] = connector_snapshots(current)
        return {"ok": True, "revision": "connector-rev-2"}

    state["connector_snapshots"] = connector_snapshots(state)

    get_routes = {
        **default_quest_routes(),
        **default_connector_routes(state),
        "/api/config/connectors": get_connectors_document,
    }
    put_routes = {
        "/api/config/connectors": save_connectors,
    }

    with MockDaemon(state=state, get_routes=get_routes, put_routes=put_routes) as daemon:
        with spawn_tui(daemon.base_url) as child:
            open_config_root(child)
            press_enter(child)
            child.expect("Choose a connector")
            press_down(child, 2)
            child.expect("> 3. Lingzhu")
            press_enter(child)
            child.expect("Lingzhu")

            ak_match = child.expect(
                [re.compile(r"Custom agent AK: ([a-z0-9]{8}(?:-[a-z0-9]{4}){3}-[a-z0-9]{12})"), pexpect.TIMEOUT],
                timeout=10,
            )
            assert ak_match == 0
            generated_ak = child.match.group(1)
            assert generated_ak != "abcd1234-abcd-abcd-abcd-abcdefghijkl"

            press_down(child, 3)
            child.expect("> 4. Public base URL:")
            press_enter(child)
            child.expect("Connector Field Editor")
            child.send("\x7f" * 48)
            child.send("https://demo.example")
            press_enter(child)
            child.expect("Updated Public base URL in draft")

            press_up(child, 3)
            child.expect_exact("> 1. [Action] Save Connector")
            press_enter(child)
            child.expect("Saved Lingzhu settings.")

    assert len(state["connector_saves"]) == 1
    saved_structured = state["connector_saves"][0]["structured"]
    assert saved_structured["qq"] == {
        "bot_name": "QQ Bot",
        "app_id": "qq-app-1",
        "command_prefix": "/",
    }
    assert saved_structured["weixin"] == {"enabled": False}
    assert saved_structured["lingzhu"]["public_base_url"] == "https://demo.example"
    assert re.fullmatch(r"[a-z0-9]{8}(?:-[a-z0-9]{4}){3}-[a-z0-9]{12}", saved_structured["lingzhu"]["auth_ak"])


def test_tui_weixin_qr_login_renders_qr_and_returns_to_detail() -> None:
    state: dict[str, Any] = {
        "connector_structured": {
            "weixin": {
                "enabled": False,
            }
        },
        "connector_revision": "weixin-rev-1",
        "weixin_polls": 0,
    }

    def connector_snapshots(current: dict[str, Any]) -> list[dict[str, Any]]:
        weixin = current["connector_structured"]["weixin"]
        return [
            {
                "name": "weixin",
                "enabled": bool(weixin.get("enabled")),
                "connection_state": "connected" if weixin.get("enabled") else "idle",
                "binding_count": 0,
                "target_count": 1 if weixin.get("enabled") else 0,
                "details": {
                    "account_id": weixin.get("account_id"),
                },
            }
        ]

    def get_connectors_document(current: dict[str, Any], _body: dict[str, Any] | None) -> dict[str, Any]:
        current["connector_snapshots"] = connector_snapshots(current)
        return {
            "document_id": "config::connectors",
            "title": "connectors.yaml",
            "path": "/tmp/connectors.yaml",
            "writable": True,
            "content": "weixin:\n",
            "revision": current["connector_revision"],
            "meta": {
                "structured_config": current["connector_structured"],
            },
        }

    def start_weixin_login(_current: dict[str, Any], _body: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "ok": True,
            "session_key": "weixin-session-1",
            "qrcode_content": "https://wx.example/qr-login",
            "message": "scan",
        }

    def wait_weixin_login(current: dict[str, Any], _body: dict[str, Any] | None) -> dict[str, Any]:
        current["weixin_polls"] += 1
        if current["weixin_polls"] < 2:
            return {
                "ok": True,
                "connected": False,
                "status": "wait",
                "session_key": "weixin-session-1",
                "qrcode_content": "https://wx.example/qr-login",
                "message": "waiting",
            }
        current["connector_structured"]["weixin"] = {
            "enabled": True,
            "account_id": "wx-bot-1",
            "login_user_id": "owner-1",
            "base_url": "http://127.0.0.1:20999",
        }
        current["connector_revision"] = "weixin-rev-2"
        current["connector_snapshots"] = connector_snapshots(current)
        return {
            "ok": True,
            "connected": True,
            "status": "connected",
            "session_key": "weixin-session-1",
            "message": "Weixin login succeeded and the connector config was saved.",
        }

    state["connector_snapshots"] = connector_snapshots(state)

    get_routes = {
        **default_quest_routes(),
        **default_connector_routes(state),
        "/api/config/connectors": get_connectors_document,
    }
    post_routes = {
        "/api/connectors/weixin/login/qr/start": start_weixin_login,
        "/api/connectors/weixin/login/qr/wait": wait_weixin_login,
    }

    with MockDaemon(state=state, get_routes=get_routes, post_routes=post_routes) as daemon:
        with spawn_tui(daemon.base_url) as child:
            open_config_root(child)
            press_enter(child)
            child.expect("Choose a connector")
            press_enter(child)
            child.expect_exact("[Action] Bind Weixin")
            press_enter(child)

            child.expect("Weixin QR Login")
            child.expect("█▀▀▀▀▀█")
            child.expect("Weixin login succeeded and the connector config was saved.", timeout=10)
            child.expect("Bot account: wx-bot-1", timeout=10)
            child.expect("Owner account: owner-1", timeout=10)

    assert state["weixin_polls"] >= 2
