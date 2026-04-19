from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from ..doctor import run_doctor
from ..shared import append_jsonl, ensure_dir, generate_id, iter_jsonl, read_json, utc_now, write_json


AdminTaskRunner = Callable[..., dict[str, Any]]


class AdminTaskReporter:
    def __init__(self, service: "AdminTaskService", task_id: str) -> None:
        self.service = service
        self.task_id = task_id

    def start(
        self,
        *,
        total: int | None = None,
        current_step: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        updates: dict[str, Any] = {
            "status": "running",
            "started_at": utc_now(),
        }
        if isinstance(total, int) and total > 0:
            updates["progress_total"] = total
            updates["progress_current"] = 0
            updates["progress_percent"] = 0
        if current_step:
            updates["current_step"] = current_step
        if message:
            updates["message"] = message
        payload = self.service._update_task(self.task_id, **updates)
        self.service._append_event(
            self.task_id,
            event="task.started",
            message=message or "Task started.",
            data={
                "task": payload,
            },
        )
        return payload

    def progress(
        self,
        *,
        current: int | None = None,
        total: int | None = None,
        current_step: str | None = None,
        message: str | None = None,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing = self.service.get_task(self.task_id)
        resolved_total = total if isinstance(total, int) and total > 0 else int(existing.get("progress_total") or 0)
        resolved_current = current if isinstance(current, int) and current >= 0 else int(existing.get("progress_current") or 0)
        progress_percent = 0
        if resolved_total > 0:
            progress_percent = max(0, min(100, round((resolved_current / resolved_total) * 100)))
        updates: dict[str, Any] = {
            "status": "running",
            "progress_total": resolved_total or None,
            "progress_current": resolved_current,
            "progress_percent": progress_percent,
        }
        if current_step:
            updates["current_step"] = current_step
        if message:
            updates["message"] = message
        if metadata is not None:
            existing_metadata = dict(existing.get("metadata") or {}) if isinstance(existing.get("metadata"), dict) else {}
            existing_metadata.update(dict(metadata))
            updates["metadata"] = existing_metadata
        payload = self.service._update_task(self.task_id, **updates)
        self.service._append_event(
            self.task_id,
            event="task.progress",
            message=message or payload.get("message") or "Task progress updated.",
            data={
                "task": payload,
                **(dict(data or {})),
            },
        )
        return payload

    def log(self, message: str, **data: Any) -> dict[str, Any]:
        return self.service._append_event(
            self.task_id,
            event="task.log",
            message=message,
            data=data,
        )

    def complete(
        self,
        *,
        message: str | None = None,
        result_path: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing = self.service.get_task(self.task_id)
        updates: dict[str, Any] = {
            "status": "completed",
            "finished_at": utc_now(),
            "progress_current": int(existing.get("progress_total") or existing.get("progress_current") or 0),
            "progress_percent": 100,
        }
        if result_path:
            updates["result_path"] = result_path
        if message:
            updates["message"] = message
        payload = self.service._update_task(self.task_id, **updates)
        self.service._append_event(
            self.task_id,
            event="task.result",
            message=message or "Task result recorded.",
            data={
                "task": payload,
                **(dict(data or {})),
            },
        )
        self.service._append_event(
            self.task_id,
            event="task.finished",
            message=message or "Task finished.",
            data={"task": payload},
        )
        return payload

    def fail(
        self,
        error: str,
        *,
        message: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self.service._update_task(
            self.task_id,
            status="failed",
            finished_at=utc_now(),
            error=str(error),
            message=message or str(error),
        )
        self.service._append_event(
            self.task_id,
            event="task.error",
            message=message or str(error),
            data={
                "task": payload,
                "error": str(error),
                **(dict(data or {})),
            },
        )
        self.service._append_event(
            self.task_id,
            event="task.finished",
            message=message or "Task failed.",
            data={"task": payload},
        )
        return payload


class AdminTaskService:
    def __init__(
        self,
        home: Path,
        *,
        repo_root: Path,
        logger: Any | None = None,
        system_update_status_fn: AdminTaskRunner | None = None,
        system_update_action_fn: AdminTaskRunner | None = None,
    ) -> None:
        self.home = Path(home)
        self.repo_root = Path(repo_root)
        self.logger = logger
        self.system_update_status_fn = system_update_status_fn
        self.system_update_action_fn = system_update_action_fn
        self._lock = threading.Lock()

    @property
    def tasks_root(self) -> Path:
        return ensure_dir(self.home / "runtime" / "admin" / "tasks")

    @property
    def cache_root(self) -> Path:
        return ensure_dir(self.home / "runtime" / "admin" / "cache")

    def record_path(self, task_id: str) -> Path:
        return self.tasks_root / f"{task_id}.json"

    def events_path(self, task_id: str) -> Path:
        return self.tasks_root / f"{task_id}.jsonl"

    def result_path(self, task_id: str) -> Path:
        return self.tasks_root / f"{task_id}.result.json"

    def cache_path(self, name: str) -> Path:
        normalized = str(name or "").strip() or "cache"
        return self.cache_root / normalized

    def list_tasks(self, *, kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        normalized_kind = str(kind or "").strip().lower() or None
        items: list[dict[str, Any]] = []
        for path in sorted(self.tasks_root.glob("*.json"), reverse=True):
            if path.name.endswith(".result.json"):
                continue
            payload = read_json(path, default=None)
            if not isinstance(payload, dict):
                continue
            if normalized_kind and str(payload.get("kind") or "").strip().lower() != normalized_kind:
                continue
            items.append(payload)
        items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return items[: max(1, limit)]

    def get_task(self, task_id: str) -> dict[str, Any]:
        payload = read_json(self.record_path(task_id), default=None)
        if not isinstance(payload, dict):
            raise FileNotFoundError(f"Unknown admin task `{task_id}`.")
        return payload

    def read_events(
        self,
        task_id: str,
        *,
        after: int = 0,
        limit: int = 200,
        tail: bool = False,
    ) -> list[dict[str, Any]]:
        path = self.events_path(task_id)
        if not path.exists():
            return []
        records = [
            dict(item)
            for item in iter_jsonl(path)
            if int(item.get("seq") or 0) > max(0, int(after or 0))
        ]
        if tail:
            return records[-max(1, limit) :]
        return records[: max(1, limit)]

    def cached_result(self, name: str) -> dict[str, Any] | None:
        payload = read_json(self.cache_path(name), default=None)
        return payload if isinstance(payload, dict) else None

    def _write_cache(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        write_json(self.cache_path(name), payload)
        return payload

    def _base_task_payload(
        self,
        *,
        task_id: str,
        kind: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "kind": kind,
            "status": "queued",
            "progress_current": 0,
            "progress_total": None,
            "progress_percent": 0,
            "current_step": "queued",
            "message": "Task queued.",
            "created_at": utc_now(),
            "started_at": None,
            "finished_at": None,
            "result_path": None,
            "error": None,
            "last_event_seq": 0,
            "metadata": dict(metadata or {}),
        }

    def _create_task(self, kind: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = self._base_task_payload(
            task_id=generate_id("admintask"),
            kind=str(kind or "").strip() or "task",
            metadata=metadata,
        )
        with self._lock:
            write_json(self.record_path(payload["task_id"]), payload)
        return payload

    def _update_task(self, task_id: str, **updates: Any) -> dict[str, Any]:
        with self._lock:
            payload = self.get_task(task_id)
            payload.update({key: value for key, value in updates.items()})
            write_json(self.record_path(task_id), payload)
            return payload

    def _append_event(
        self,
        task_id: str,
        *,
        event: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            payload = self.get_task(task_id)
            seq = int(payload.get("last_event_seq") or 0) + 1
            payload["last_event_seq"] = seq
            write_json(self.record_path(task_id), payload)
            entry = {
                "seq": seq,
                "event": str(event or "task.log"),
                "message": str(message or "").strip(),
                "data": dict(data or {}),
                "created_at": utc_now(),
            }
            append_jsonl(self.events_path(task_id), entry)
            return entry

    def _log_internal(self, level: str, event: str, **payload: Any) -> None:
        if self.logger is None or not hasattr(self.logger, "log"):
            return
        try:
            self.logger.log(level, event, **payload)
        except Exception:
            return

    def _start_background(
        self,
        task: dict[str, Any],
        *,
        target: Callable[[AdminTaskReporter, dict[str, Any]], None],
    ) -> dict[str, Any]:
        task_id = str(task.get("task_id") or "").strip()
        reporter = AdminTaskReporter(self, task_id)

        def _runner() -> None:
            try:
                target(reporter, task)
            except Exception as exc:
                self._log_internal(
                    "error",
                    "admin.task_failed",
                    task_id=task_id,
                    kind=task.get("kind"),
                    error=str(exc),
                )
                reporter.fail(str(exc))

        thread = threading.Thread(
            target=_runner,
            daemon=True,
            name=f"admin-task-{task_id}",
        )
        thread.start()
        return self.get_task(task_id)

    def start_task(
        self,
        kind: str,
        *,
        metadata: dict[str, Any] | None = None,
        target: Callable[[AdminTaskReporter, dict[str, Any]], None],
    ) -> dict[str, Any]:
        task = self._create_task(kind, metadata=metadata)
        return self._start_background(task, target=target)

    def start_doctor_task(self) -> dict[str, Any]:
        task = self._create_task("doctor")

        def _run(reporter: AdminTaskReporter, current_task: dict[str, Any]) -> None:
            reporter.start(total=12, current_step="queued", message="Doctor task started.")

            def _on_check(item: dict[str, Any]) -> None:
                check = dict(item.get("check") or {})
                index = int(item.get("index") or 0)
                total = int(item.get("total") or 0)
                reporter.progress(
                    current=index,
                    total=total,
                    current_step=str(item.get("check_id") or check.get("id") or "check"),
                    message=str(check.get("summary") or check.get("label") or "Doctor check completed."),
                    data={"check": check},
                )

            report = run_doctor(self.home, repo_root=self.repo_root, on_check=_on_check)
            result_path = str(self.result_path(str(current_task["task_id"])))
            write_json(Path(result_path), report)
            self._write_cache(
                "doctor.json",
                {
                    "task_id": current_task["task_id"],
                    "generated_at": utc_now(),
                    "report": report,
                },
            )
            reporter.complete(
                message="Doctor completed.",
                result_path=result_path,
                data={"report": report},
            )

        return self._start_background(task, target=_run)

    def start_system_update_check_task(self) -> dict[str, Any]:
        if self.system_update_status_fn is None:
            raise RuntimeError("System update check function is not configured.")
        task = self._create_task("system_update_check")

        def _run(reporter: AdminTaskReporter, current_task: dict[str, Any]) -> None:
            reporter.start(total=4, current_step="launch_subprocess", message="Starting system update check.")
            reporter.progress(current=1, total=4, current_step="launch_subprocess", message="Launching update check subprocess.")
            payload = self.system_update_status_fn()
            reporter.progress(current=2, total=4, current_step="parse_json", message="Parsing update check result.")
            result_path = str(self.result_path(str(current_task["task_id"])))
            write_json(Path(result_path), payload)
            reporter.progress(current=3, total=4, current_step="cache_result", message="Caching update status.")
            self._write_cache(
                "system_update.json",
                {
                    "task_id": current_task["task_id"],
                    "generated_at": utc_now(),
                    "status": payload,
                },
            )
            reporter.complete(
                message="System update check completed.",
                result_path=result_path,
                data={"status": payload},
            )

        return self._start_background(task, target=_run)

    def start_system_update_action_task(self, *, action: str) -> dict[str, Any]:
        if self.system_update_action_fn is None:
            raise RuntimeError("System update action function is not configured.")
        normalized_action = str(action or "").strip().lower()
        if not normalized_action:
            raise ValueError("System update action is required.")
        task = self._create_task("system_update_action", metadata={"action": normalized_action})

        def _run(reporter: AdminTaskReporter, current_task: dict[str, Any]) -> None:
            reporter.start(total=4, current_step="launch_subprocess", message=f"Starting system update action `{normalized_action}`.")
            reporter.progress(current=1, total=4, current_step="launch_subprocess", message="Launching system update action.")
            payload = self.system_update_action_fn(action=normalized_action)
            reporter.progress(current=2, total=4, current_step="parse_json", message="Parsing system update action result.")
            result_path = str(self.result_path(str(current_task["task_id"])))
            write_json(Path(result_path), payload)
            reporter.progress(current=3, total=4, current_step="cache_result", message="Caching system update action result.")
            self._write_cache(
                "system_update_action.json",
                {
                    "task_id": current_task["task_id"],
                    "generated_at": utc_now(),
                    "action": normalized_action,
                    "result": payload,
                },
            )
            reporter.complete(
                message=f"System update action `{normalized_action}` completed.",
                result_path=result_path,
                data={"result": payload, "action": normalized_action},
            )

        return self._start_background(task, target=_run)
