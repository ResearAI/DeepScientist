from __future__ import annotations

import io
import json
import threading
import time
from pathlib import Path

from deepscientist.config import ConfigManager
from deepscientist.daemon.app import DaemonApp
from deepscientist.home import ensure_home_layout, repo_root


class _CaptureSseHandler:
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


def _parse_sse_events(raw: bytes) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for block in raw.decode("utf-8").split("\n\n"):
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if lines[0].startswith(":") or lines[0].startswith("retry:"):
            continue
        event_name = ""
        event_id = ""
        data_lines: list[str] = []
        for line in lines:
            if line.startswith("id: "):
                event_id = line[len("id: ") :].strip()
            elif line.startswith("event: "):
                event_name = line[len("event: ") :].strip()
            elif line.startswith("data: "):
                data_lines.append(line[len("data: ") :])
        if not event_name or not data_lines:
            continue
        events.append(
            {
                "id": event_id,
                "event": event_name,
                "data": json.loads("".join(data_lines)),
            }
        )
    return events


def _build_app(temp_home: Path) -> DaemonApp:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=False)
    app._start_background_connectors = lambda: None  # type: ignore[method-assign]
    app._stop_background_connectors = lambda: None  # type: ignore[method-assign]
    app._start_terminal_attach_server = lambda host, port: None  # type: ignore[method-assign]
    app._stop_terminal_attach_server = lambda: None  # type: ignore[method-assign]
    return app


def test_admin_doctor_task_completes_and_caches_report(temp_home: Path, monkeypatch) -> None:
    app = _build_app(temp_home)

    def _fake_run_doctor(home: Path, *, repo_root: Path, on_check=None):  # noqa: ANN001
        for index, check_id in enumerate(["python_runtime", "git"], start=1):
            if on_check is not None:
                on_check(
                    {
                        "check_id": check_id,
                        "index": index,
                        "total": 2,
                        "check": {
                            "id": check_id,
                            "label": check_id,
                            "ok": True,
                            "summary": f"{check_id} ok",
                        },
                    }
                )
        return {
            "ok": True,
            "timestamp": "2026-04-08T00:00:00+00:00",
            "home": str(home),
            "browser_url": "http://127.0.0.1:20999",
            "checks": [
                {"id": "python_runtime", "ok": True, "summary": "python_runtime ok"},
                {"id": "git", "ok": True, "summary": "git ok"},
            ],
        }

    monkeypatch.setattr("deepscientist.admin.tasks.run_doctor", _fake_run_doctor)

    started = app.handlers.admin_task_doctor_start({})
    task_id = str(((started.get("task") or {}) if isinstance(started, dict) else {}).get("task_id") or "")
    assert task_id

    deadline = time.time() + 2.0
    task_payload = None
    while time.time() < deadline:
        response = app.handlers.admin_task_detail(task_id)
        assert not isinstance(response, tuple)
        task_payload = response["task"]
        if task_payload["status"] == "completed":
            break
        time.sleep(0.05)

    assert task_payload is not None
    assert task_payload["status"] == "completed"
    assert Path(str(task_payload["result_path"])).exists()

    cached = app.handlers.admin_doctor()
    assert cached["ok"] is True
    assert cached["cached"]["task_id"] == task_id
    assert cached["cached"]["report"]["ok"] is True


def test_admin_task_stream_emits_snapshot_progress_and_finish(temp_home: Path, monkeypatch) -> None:
    app = _build_app(temp_home)

    def _fake_run_doctor(home: Path, *, repo_root: Path, on_check=None):  # noqa: ANN001
        for index, check_id in enumerate(["python_runtime", "git"], start=1):
            if on_check is not None:
                on_check(
                    {
                        "check_id": check_id,
                        "index": index,
                        "total": 2,
                        "check": {
                            "id": check_id,
                            "label": check_id,
                            "ok": True,
                            "summary": f"{check_id} ok",
                        },
                    }
                )
        return {
            "ok": True,
            "timestamp": "2026-04-08T00:00:00+00:00",
            "home": str(home),
            "browser_url": "http://127.0.0.1:20999",
            "checks": [],
        }

    monkeypatch.setattr("deepscientist.admin.tasks.run_doctor", _fake_run_doctor)

    started = app.handlers.admin_task_doctor_start({})
    task_id = str(started["task"]["task_id"])
    deadline = time.time() + 2.0
    while time.time() < deadline:
        payload = app.admin_task_service.get_task(task_id)
        if payload["status"] == "completed":
            break
        time.sleep(0.05)

    handler = _CaptureSseHandler()
    thread = threading.Thread(
        target=app.stream_admin_task,
        kwargs={
            "handler": handler,
            "task_id": task_id,
            "headers": {"Accept": "text/event-stream"},
            "extra_headers": {},
        },
        daemon=True,
    )
    thread.start()
    thread.join(timeout=2.0)
    assert not thread.is_alive()

    events = _parse_sse_events(handler.wfile.getvalue())
    event_names = [str(item["event"]) for item in events]
    assert "task.snapshot" in event_names
    assert "task.progress" in event_names
    assert "task.finished" in event_names


def test_admin_system_update_tasks_use_background_records(temp_home: Path) -> None:
    app = _build_app(temp_home)
    app.admin_task_service.system_update_status_fn = lambda: {"ok": True, "update_available": False}
    app.admin_task_service.system_update_action_fn = lambda *, action: {"ok": True, "action": action}

    check_task = app.handlers.admin_task_system_update_check_start({})
    action_task = app.handlers.admin_task_system_update_action_start({"action": "remind_later"})

    check_id = str(check_task["task"]["task_id"])
    action_id = str(action_task["task"]["task_id"])

    deadline = time.time() + 2.0
    completed: set[str] = set()
    while time.time() < deadline and len(completed) < 2:
        for task_id in (check_id, action_id):
            payload = app.admin_task_service.get_task(task_id)
            if payload["status"] == "completed":
                completed.add(task_id)
        time.sleep(0.05)

    assert completed == {check_id, action_id}
    action_payload = app.admin_task_service.get_task(action_id)
    assert action_payload["metadata"]["action"] == "remind_later"
    assert Path(str(action_payload["result_path"])).exists()
