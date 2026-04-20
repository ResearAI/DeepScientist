from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import ConfigManager
from ..mcp.context import McpContext
from ..process_control import is_process_alive, process_session_popen_kwargs, terminate_process_ids
from ..shared import append_jsonl, ensure_dir, generate_id, iter_jsonl, read_json, read_jsonl, read_jsonl_tail, utc_now
from .shells import build_exec_shell_launch, build_terminal_shell_launch
from .runtime import TerminalRuntimeManager

BASH_STATUS_MARKER_PREFIX = "__DS_BASH_STATUS__"
BASH_CARRIAGE_RETURN_PREFIX = "__DS_BASH_CR__"
BASH_PROGRESS_PREFIX = "__DS_PROGRESS__"
BASH_TERMINAL_PROMPT_PREFIX = "__DS_TERMINAL_PROMPT__"
DEFAULT_LOG_TAIL_LIMIT = 200
DEFAULT_INLINE_BASH_LOG_LINE_LIMIT = 2000
DEFAULT_INLINE_BASH_LOG_HEAD_LINES = 500
DEFAULT_INLINE_BASH_LOG_TAIL_LINES = 1500
DEFAULT_POLL_INTERVAL_SECONDS = 0.35
TERMINAL_STATUSES = {"completed", "failed", "terminated"}
DEFAULT_TERMINAL_SESSION_ID = "terminal-main"
BASH_WATCHDOG_AFTER_SECONDS = 1800
SUMMARY_RECENT_SESSION_LIMIT = 256
SUMMARY_RUNNING_SESSION_LIMIT = 64
INPUT_ESCAPE_SEQUENCE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-_]")


def _atomic_write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f"{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _count_jsonl_records(path: Path) -> int:
    return sum(1 for _ in iter_jsonl(path))


def _build_terminal_log_preview_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "log": "",
            "log_line_count": 0,
            "log_truncated": False,
        }

    head_lines: list[str] = []
    tail_lines: deque[str] = deque(maxlen=DEFAULT_INLINE_BASH_LOG_TAIL_LINES)
    total = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            total += 1
            if total <= DEFAULT_INLINE_BASH_LOG_HEAD_LINES:
                head_lines.append(line)
            tail_lines.append(line)

    if total <= DEFAULT_INLINE_BASH_LOG_LINE_LIMIT:
        return {
            "log": "\n".join(list(tail_lines)),
            "log_line_count": total,
            "log_truncated": False,
        }

    omitted = max(0, total - DEFAULT_INLINE_BASH_LOG_HEAD_LINES - DEFAULT_INLINE_BASH_LOG_TAIL_LINES)
    marker = (
        "[... omitted "
        f"{omitted} lines from the middle of this log. "
        "Use bash_exec(mode='read', id=..., start=..., tail=...) for a specific window.]"
    )
    return {
        "log": "\n".join(head_lines + [marker] + list(tail_lines)),
        "log_line_count": total,
        "log_truncated": True,
        "log_preview_head_lines": DEFAULT_INLINE_BASH_LOG_HEAD_LINES,
        "log_preview_tail_lines": DEFAULT_INLINE_BASH_LOG_TAIL_LINES,
        "log_preview_omitted_lines": omitted,
    }


def _normalize_string(value: object) -> str:
    return str(value or "").strip()


def _coerce_session_status(value: object) -> str:
    normalized = _normalize_string(value).lower()
    if normalized in TERMINAL_STATUSES | {"running", "terminating"}:
        return normalized
    return "failed"


def _session_sort_key(session: dict[str, Any]) -> tuple[str, str]:
    return (
        str(session.get("started_at") or ""),
        str(session.get("updated_at") or ""),
    )


def _parse_progress_marker(line: str) -> dict[str, Any] | None:
    if not line.startswith(BASH_PROGRESS_PREFIX):
        return None
    raw = line[len(BASH_PROGRESS_PREFIX) :].strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _parse_timestamp(value: object) -> datetime | None:
    normalized = _normalize_string(value)
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _age_seconds(value: object, *, now: datetime | None = None) -> int | None:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return None
    current = now or datetime.now(UTC)
    return max(0, int((current - parsed).total_seconds()))


def _latest_timestamp(*values: object) -> str | None:
    latest_raw: str | None = None
    latest_dt: datetime | None = None
    for value in values:
        normalized = _normalize_string(value)
        parsed = _parse_timestamp(normalized)
        if parsed is None:
            continue
        if latest_dt is None or parsed >= latest_dt:
            latest_dt = parsed
            latest_raw = normalized
    return latest_raw


def _compact_command(command: object, *, max_length: int = 140) -> str:
    normalized = " ".join(str(command or "").split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max(0, max_length - 3)].rstrip() + "..."


class BashExecService:
    def __init__(self, home: Path) -> None:
        self.home = home
        self._summary_cache_lock = threading.Lock()
        self._summary_cache: dict[str, dict[str, Any]] = {}
        self._terminal_runtime_manager = TerminalRuntimeManager(home)

    def _quest_root(self, quest_id: str) -> Path:
        return self.home / "quests" / quest_id

    def _hardware_env_overrides(self) -> dict[str, str]:
        config = ConfigManager(self.home).load_runtime_config()
        hardware = config.get("hardware") if isinstance(config.get("hardware"), dict) else {}
        mode = str(hardware.get("gpu_selection_mode") or "all").strip().lower() or "all"
        if mode != "selected":
            return {}
        selected_gpu_ids = [str(item).strip() for item in (hardware.get("selected_gpu_ids") or []) if str(item).strip()]
        value = ",".join(selected_gpu_ids)
        return {
            "CUDA_VISIBLE_DEVICES": value,
            "NVIDIA_VISIBLE_DEVICES": value,
            "ROCR_VISIBLE_DEVICES": value,
        }

    def sessions_root(self, quest_root: Path) -> Path:
        return ensure_dir(quest_root / ".ds" / "bash_exec")

    def index_path(self, quest_root: Path) -> Path:
        return self.sessions_root(quest_root) / "index.jsonl"

    def summary_path(self, quest_root: Path) -> Path:
        return self.sessions_root(quest_root) / "summary.json"

    def session_dir(self, quest_root: Path, bash_id: str) -> Path:
        return self.sessions_root(quest_root) / bash_id

    def meta_path(self, quest_root: Path, bash_id: str) -> Path:
        return self.session_dir(quest_root, bash_id) / "meta.json"

    def log_path(self, quest_root: Path, bash_id: str) -> Path:
        return self.session_dir(quest_root, bash_id) / "log.jsonl"

    def terminal_log_path(self, quest_root: Path, bash_id: str) -> Path:
        return self.session_dir(quest_root, bash_id) / "terminal.log"

    def progress_path(self, quest_root: Path, bash_id: str) -> Path:
        return self.session_dir(quest_root, bash_id) / "progress.json"

    def input_path(self, quest_root: Path, bash_id: str) -> Path:
        return self.session_dir(quest_root, bash_id) / "input.jsonl"

    def input_cursor_path(self, quest_root: Path, bash_id: str) -> Path:
        return self.session_dir(quest_root, bash_id) / "input.cursor.json"

    def history_path(self, quest_root: Path, bash_id: str) -> Path:
        return self.session_dir(quest_root, bash_id) / "history.jsonl"

    def line_buffer_path(self, quest_root: Path, bash_id: str) -> Path:
        return self.session_dir(quest_root, bash_id) / "line_buffer.json"

    def terminal_rc_path(self, quest_root: Path, bash_id: str) -> Path:
        return self.session_dir(quest_root, bash_id) / "terminal.rc"

    def prompt_events_path(self, quest_root: Path, bash_id: str) -> Path:
        return self.session_dir(quest_root, bash_id) / "prompt-events.log"

    def monitor_log_path(self, quest_root: Path, bash_id: str) -> Path:
        return self.session_dir(quest_root, bash_id) / "monitor.log"

    def stop_request_path(self, quest_root: Path, bash_id: str) -> Path:
        return self.session_dir(quest_root, bash_id) / "stop_request.json"

    def _allowed_roots(self, context: McpContext) -> list[Path]:
        roots: list[Path] = []
        quest_root = context.require_quest_root().resolve()
        roots.append(quest_root)
        if context.worktree_root is not None:
            worktree_root = context.worktree_root.resolve()
            if worktree_root not in roots:
                roots.append(worktree_root)
        return roots

    def resolve_workdir(self, context: McpContext, workdir: str | None) -> tuple[Path, str]:
        roots = self._allowed_roots(context)
        quest_root = context.require_quest_root().resolve()
        requested = _normalize_string(workdir)
        if not requested and context.worktree_root is not None:
            cwd = context.worktree_root.resolve()
        elif not requested:
            cwd = quest_root
        else:
            candidate = Path(requested).expanduser()
            if candidate.is_absolute():
                cwd = candidate.resolve()
            else:
                base = context.worktree_root.resolve() if context.worktree_root is not None else quest_root
                cwd = (base / candidate).resolve()
        if not any(cwd == root or root in cwd.parents for root in roots):
            raise ValueError("workdir_outside_quest")
        if not cwd.exists() or not cwd.is_dir():
            raise ValueError("workdir_not_found")
        try:
            display = cwd.relative_to(quest_root).as_posix()
        except ValueError:
            display = str(cwd)
        return cwd, "" if display == "." else display

    def _export_log(
        self,
        *,
        quest_root: Path,
        cwd: Path,
        bash_id: str,
        export_log: bool,
        export_log_to: str | None,
    ) -> dict[str, Any]:
        target = _normalize_string(export_log_to)
        if not target and not export_log:
            return {}
        if not target:
            target = f"artifacts/runs/{bash_id}/bash.log"
        destination = Path(target).expanduser()
        if destination.is_absolute():
            resolved = destination.resolve()
        else:
            resolved = (cwd / destination).resolve()
        quest_root_resolved = quest_root.resolve()
        if resolved != quest_root_resolved and quest_root_resolved not in resolved.parents:
            raise ValueError("export_log_outside_quest")
        if resolved.exists() and resolved.is_symlink():
            raise ValueError("export_log_symlink_denied")
        source = self.terminal_log_path(quest_root, bash_id)
        ensure_dir(resolved.parent)
        shutil.copy2(source, resolved)
        return {
            "exported_log_path": str(resolved.relative_to(quest_root_resolved)),
        }

    def _session_log_relative_path(self, quest_root: Path, bash_id: str) -> str:
        return str(self.terminal_log_path(quest_root, bash_id).relative_to(quest_root))

    def _session_payload(self, quest_root: Path, meta: dict[str, Any]) -> dict[str, Any]:
        payload = dict(meta)
        payload["project_id"] = payload.get("project_id") or payload.get("quest_id")
        payload["chat_session_id"] = payload.get("chat_session_id") or payload.get("session_id")
        payload["log_path"] = payload.get("log_path") or self._session_log_relative_path(quest_root, str(payload.get("bash_id") or ""))
        payload["status"] = _coerce_session_status(payload.get("status"))
        payload["last_progress"] = payload.get("last_progress") or read_json(self.progress_path(quest_root, str(payload.get("bash_id") or "")), None)
        payload["kind"] = str(payload.get("kind") or "exec")
        payload = self._enrich_watchdog_fields(payload)
        return payload

    @staticmethod
    def _enrich_watchdog_fields(payload: dict[str, Any]) -> dict[str, Any]:
        current = datetime.now(UTC)
        last_progress = payload.get("last_progress")
        last_progress_at = None
        if isinstance(last_progress, dict):
            last_progress_at = _normalize_string(last_progress.get("ts")) or None
        last_output_at = _normalize_string(payload.get("last_output_at")) or None
        latest_signal_at = _latest_timestamp(last_output_at, last_progress_at, payload.get("started_at"))
        payload["last_progress_at"] = last_progress_at
        payload["run_age_seconds"] = _age_seconds(payload.get("started_at"), now=current)
        payload["status_age_seconds"] = _age_seconds(payload.get("updated_at"), now=current)
        payload["silent_seconds"] = _age_seconds(last_output_at or payload.get("started_at"), now=current)
        payload["progress_age_seconds"] = _age_seconds(last_progress_at, now=current)
        payload["latest_signal_at"] = latest_signal_at
        payload["signal_age_seconds"] = _age_seconds(latest_signal_at, now=current)
        payload["watchdog_after_seconds"] = BASH_WATCHDOG_AFTER_SECONDS
        payload["watchdog_overdue"] = (
            payload.get("status") in {"running", "terminating"}
            and isinstance(payload.get("signal_age_seconds"), int)
            and int(payload["signal_age_seconds"]) >= BASH_WATCHDOG_AFTER_SECONDS
        )
        return payload

    @staticmethod
    def format_history_line(session: dict[str, Any]) -> str:
        timestamp = (
            _normalize_string(session.get("started_at"))
            or _normalize_string(session.get("updated_at"))
            or _normalize_string(session.get("finished_at"))
            or "unknown-time"
        )
        command = _compact_command(session.get("command"))
        bash_id = _normalize_string(session.get("bash_id") or session.get("id")) or "unknown-id"
        return f"{timestamp} | {command} | {bash_id}"

    @staticmethod
    def _summary_session_payload(meta: dict[str, Any]) -> dict[str, Any]:
        return {
            "bash_id": meta.get("bash_id") or meta.get("id"),
            "command": meta.get("command"),
            "kind": meta.get("kind") or "exec",
            "label": meta.get("label"),
            "comment": meta.get("comment"),
            "workdir": meta.get("workdir"),
            "status": _coerce_session_status(meta.get("status")),
            "exit_code": meta.get("exit_code"),
            "stop_reason": meta.get("stop_reason"),
            "started_at": meta.get("started_at"),
            "finished_at": meta.get("finished_at"),
            "updated_at": meta.get("updated_at"),
            "last_progress": meta.get("last_progress"),
            "last_output_at": meta.get("last_output_at"),
            "last_output_seq": meta.get("last_output_seq"),
        }

    @staticmethod
    def _summary_sort_key(session: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(session.get("updated_at") or ""),
            str(session.get("started_at") or ""),
            str(session.get("bash_id") or ""),
        )

    @classmethod
    def _normalize_summary_session_list(
        cls,
        sessions: Any,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        max_items = max(0, int(limit or 0))
        if max_items <= 0:
            return []
        normalized: dict[str, dict[str, Any]] = {}
        for raw in sessions or []:
            if not isinstance(raw, dict):
                continue
            compact = cls._summary_session_payload(raw)
            bash_id = _normalize_string(compact.get("bash_id"))
            if not bash_id:
                continue
            normalized[bash_id] = compact
        ordered = sorted(normalized.values(), key=cls._summary_sort_key, reverse=True)
        return ordered[:max_items]

    @classmethod
    def _merge_summary_session_list(
        cls,
        sessions: Any,
        compact: dict[str, Any],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        bash_id = _normalize_string(compact.get("bash_id"))
        merged = cls._normalize_summary_session_list(sessions, limit=max(1, int(limit or 0)) + 1)
        merged = [
            item
            for item in merged
            if _normalize_string(item.get("bash_id")) != bash_id
        ]
        if bash_id:
            merged.append(cls._summary_session_payload(compact))
        merged.sort(key=cls._summary_sort_key, reverse=True)
        return merged[: max(1, int(limit or 0))]

    @classmethod
    def _remove_summary_session(
        cls,
        sessions: Any,
        bash_id: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        normalized_bash_id = _normalize_string(bash_id)
        if not normalized_bash_id:
            return cls._normalize_summary_session_list(sessions, limit=limit)
        return [
            item
            for item in cls._normalize_summary_session_list(sessions, limit=limit)
            if _normalize_string(item.get("bash_id")) != normalized_bash_id
        ][: max(1, int(limit or 0))]

    @staticmethod
    def _is_active_status(value: object) -> bool:
        return _coerce_session_status(value) in {"running", "terminating"}

    def _default_summary(self) -> dict[str, Any]:
        return {
            "session_count": 0,
            "running_count": 0,
            "latest_session": None,
            "recent_sessions": [],
            "running_sessions": [],
            "updated_at": utc_now(),
        }

    def _normalize_summary_payload(self, summary: Any) -> dict[str, Any]:
        merged = {**self._default_summary(), **(summary if isinstance(summary, dict) else {})}
        latest_session = merged.get("latest_session")
        if isinstance(latest_session, dict):
            compact_latest = self._summary_session_payload(latest_session)
            merged["latest_session"] = compact_latest if _normalize_string(compact_latest.get("bash_id")) else None
        else:
            merged["latest_session"] = None
        merged["session_count"] = max(0, int(merged.get("session_count") or 0))
        merged["running_count"] = max(0, int(merged.get("running_count") or 0))
        merged["recent_sessions"] = self._normalize_summary_session_list(
            merged.get("recent_sessions"),
            limit=SUMMARY_RECENT_SESSION_LIMIT,
        )
        merged["running_sessions"] = self._normalize_summary_session_list(
            merged.get("running_sessions"),
            limit=SUMMARY_RUNNING_SESSION_LIMIT,
        )
        return merged

    def _refresh_summary_cache(self, quest_root: Path, summary: dict[str, Any]) -> dict[str, Any]:
        path = self.summary_path(quest_root)
        cache_key = str(path.resolve())
        if path.exists():
            stat = path.stat()
            state = (
                stat.st_ino,
                getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)),
                stat.st_size,
            )
        else:
            state = None
        payload = self._normalize_summary_payload(summary)
        with self._summary_cache_lock:
            self._summary_cache[cache_key] = {
                "state": state,
                "summary": payload,
            }
        return payload

    def _load_summary_from_disk(self, quest_root: Path) -> dict[str, Any] | None:
        path = self.summary_path(quest_root)
        if not path.exists():
            return None
        cache_key = str(path.resolve())
        stat = path.stat()
        state = (
            stat.st_ino,
            getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)),
            stat.st_size,
        )
        with self._summary_cache_lock:
            cached = self._summary_cache.get(cache_key)
            if cached and cached.get("state") == state:
                return dict(cached.get("summary") or self._default_summary())
        summary = read_json(path, None)
        if not isinstance(summary, dict):
            return None
        merged = self._normalize_summary_payload(summary)
        return self._refresh_summary_cache(quest_root, merged)

    def _write_summary(self, quest_root: Path, summary: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_summary_payload(summary)
        normalized["updated_at"] = utc_now()
        _atomic_write_json(self.summary_path(quest_root), normalized)
        return self._refresh_summary_cache(quest_root, normalized)

    def _hydrate_summary_from_index(
        self,
        quest_root: Path,
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        needs_recent_sessions = not bool(summary.get("recent_sessions"))
        needs_running_sessions = int(summary.get("running_count") or 0) > 0 and not bool(summary.get("running_sessions"))
        if not needs_recent_sessions and not needs_running_sessions:
            return summary

        index_path = self.index_path(quest_root)
        if not index_path.exists():
            return summary

        candidate_ids: list[str] = []
        seen_ids: set[str] = set()
        max_candidates = max(SUMMARY_RECENT_SESSION_LIMIT, SUMMARY_RUNNING_SESSION_LIMIT * 4)
        for entry in reversed(read_jsonl(index_path)):
            bash_id = _normalize_string((entry or {}).get("bash_id") if isinstance(entry, dict) else "")
            if not bash_id or bash_id in seen_ids:
                continue
            seen_ids.add(bash_id)
            candidate_ids.append(bash_id)
            if len(candidate_ids) >= max_candidates:
                break

        if not candidate_ids:
            return summary

        recent_sessions: list[dict[str, Any]] = []
        running_sessions: list[dict[str, Any]] = []
        for bash_id in candidate_ids:
            meta = read_json(self.meta_path(quest_root, bash_id), {})
            if not isinstance(meta, dict) or not meta:
                continue
            compact = self._summary_session_payload(meta)
            recent_sessions.append(compact)
            if self._is_active_status(meta.get("status")):
                running_sessions.append(compact)

        if not recent_sessions and not running_sessions:
            return summary

        updated_summary = dict(summary)
        if needs_recent_sessions and recent_sessions:
            updated_summary["recent_sessions"] = self._normalize_summary_session_list(
                recent_sessions,
                limit=SUMMARY_RECENT_SESSION_LIMIT,
            )
            if updated_summary["recent_sessions"] and not isinstance(updated_summary.get("latest_session"), dict):
                updated_summary["latest_session"] = updated_summary["recent_sessions"][0]
        if needs_running_sessions:
            updated_summary["running_sessions"] = self._normalize_summary_session_list(
                running_sessions,
                limit=SUMMARY_RUNNING_SESSION_LIMIT,
            )
        return self._write_summary(quest_root, updated_summary)

    def _rebuild_summary(self, quest_root: Path) -> dict[str, Any]:
        summary = self._default_summary()
        latest_session: dict[str, Any] | None = None
        session_count = 0
        running_count = 0
        recent_sessions: list[dict[str, Any]] = []
        running_sessions: list[dict[str, Any]] = []
        for meta_path in self.sessions_root(quest_root).glob("*/meta.json"):
            meta = read_json(meta_path, {})
            if not isinstance(meta, dict) or not meta:
                continue
            session_count += 1
            compact = self._summary_session_payload(meta)
            recent_sessions.append(compact)
            if self._is_active_status(meta.get("status")):
                running_count += 1
                running_sessions.append(compact)
            if latest_session is None or self._summary_sort_key(compact) >= self._summary_sort_key(latest_session):
                latest_session = compact
        summary["session_count"] = session_count
        summary["running_count"] = running_count
        summary["latest_session"] = latest_session
        summary["recent_sessions"] = self._normalize_summary_session_list(
            recent_sessions,
            limit=SUMMARY_RECENT_SESSION_LIMIT,
        )
        summary["running_sessions"] = self._normalize_summary_session_list(
            running_sessions,
            limit=SUMMARY_RUNNING_SESSION_LIMIT,
        )
        return self._write_summary(quest_root, summary)

    def summary(self, quest_root: Path) -> dict[str, Any]:
        loaded = self._load_summary_from_disk(quest_root)
        if loaded is not None:
            return self._hydrate_summary_from_index(quest_root, loaded)
        return self._rebuild_summary(quest_root)

    def _write_meta(self, quest_root: Path, bash_id: str, meta: dict[str, Any]) -> dict[str, Any]:
        path = self.meta_path(quest_root, bash_id)
        previous = read_json(path, {}) if path.exists() else {}
        _atomic_write_json(path, meta)

        summary = self.summary(quest_root)
        old_exists = isinstance(previous, dict) and bool(previous)
        old_running = self._is_active_status(previous.get("status")) if old_exists else False
        new_running = self._is_active_status(meta.get("status"))
        if not old_exists:
            summary["session_count"] = int(summary.get("session_count") or 0) + 1
        if old_running != new_running:
            running_count = int(summary.get("running_count") or 0)
            running_count += 1 if new_running else -1
            summary["running_count"] = max(0, running_count)

        latest_session = summary.get("latest_session")
        compact = self._summary_session_payload(meta)
        if (
            not isinstance(latest_session, dict)
            or str(latest_session.get("bash_id") or "") == str(compact.get("bash_id") or "")
            or self._summary_sort_key(compact) >= self._summary_sort_key(latest_session)
        ):
            summary["latest_session"] = compact
        summary["recent_sessions"] = self._merge_summary_session_list(
            summary.get("recent_sessions"),
            compact,
            limit=SUMMARY_RECENT_SESSION_LIMIT,
        )
        if new_running:
            summary["running_sessions"] = self._merge_summary_session_list(
                summary.get("running_sessions"),
                compact,
                limit=SUMMARY_RUNNING_SESSION_LIMIT,
            )
        else:
            summary["running_sessions"] = self._remove_summary_session(
                summary.get("running_sessions"),
                str(compact.get("bash_id") or ""),
                limit=SUMMARY_RUNNING_SESSION_LIMIT,
            )
        return self._write_summary(quest_root, summary)

    def reconcile_session(self, quest_root: Path, bash_id: str) -> dict[str, Any]:
        meta_path = self.meta_path(quest_root, bash_id)
        meta = read_json(meta_path, {})
        if not meta:
            raise FileNotFoundError(f"Unknown bash session `{bash_id}`.")
        status = _coerce_session_status(meta.get("status"))
        if status in TERMINAL_STATUSES:
            return self._session_payload(quest_root, meta)
        kind = _normalize_string(meta.get("kind")).lower()
        if kind == "terminal":
            runtime = self._terminal_runtime_manager.get_runtime(quest_root, bash_id)
            if runtime is not None:
                return self._session_payload(quest_root, read_json(meta_path, meta) or meta)
        monitor_pid = meta.get("monitor_pid")
        process_pid = meta.get("process_pid")
        if kind == "terminal" and is_process_alive(process_pid):
            terminate_process_ids(
                process_pid=process_pid if isinstance(process_pid, int) else None,
                process_group_id=meta.get("process_group_id") if isinstance(meta.get("process_group_id"), int) else None,
                force=False,
            )
            time.sleep(0.05)
        if kind != "terminal" and (is_process_alive(process_pid) or is_process_alive(monitor_pid)):
            return self._session_payload(quest_root, meta)
        stop_reason = _normalize_string(meta.get("stop_reason"))
        meta["status"] = "terminated" if stop_reason else "failed"
        meta.setdefault("finished_at", utc_now())
        meta["updated_at"] = utc_now()
        self._write_meta(quest_root, bash_id, meta)
        return self._session_payload(quest_root, meta)

    def get_session(self, quest_root: Path, bash_id: str) -> dict[str, Any]:
        return self.reconcile_session(quest_root, bash_id)

    def _list_session_ids(self, quest_root: Path) -> list[str]:
        root = self.sessions_root(quest_root)
        ids: list[str] = []
        for meta_path in root.glob("*/meta.json"):
            ids.append(meta_path.parent.name)
        return sorted(ids)

    def list_sessions(
        self,
        quest_root: Path,
        *,
        status: str | None = None,
        kind: str | None = None,
        agent_instance_ids: list[str] | None = None,
        agent_ids: list[str] | None = None,
        chat_session_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        normalized_status = _normalize_string(status).lower()
        normalized_kind = _normalize_string(kind).lower()
        normalized_agent_instance_ids = {item for item in (agent_instance_ids or []) if item}
        normalized_agent_ids = {item for item in (agent_ids or []) if item}
        normalized_chat_session = _normalize_string(chat_session_id)
        summary = self.summary(quest_root)
        if normalized_status in {"running", "terminating"} and int(summary.get("running_count") or 0) <= 0:
            return []
        can_use_summary_fast_path = (
            not normalized_agent_instance_ids
            and not normalized_agent_ids
            and not normalized_chat_session
        )
        if can_use_summary_fast_path:
            candidate_compacts: list[dict[str, Any]] | None = None
            if normalized_status in {"running", "terminating"}:
                running_sessions = self._normalize_summary_session_list(
                    summary.get("running_sessions"),
                    limit=SUMMARY_RUNNING_SESSION_LIMIT,
                )
                filtered_running = [
                    item
                    for item in running_sessions
                    if (not normalized_kind or _normalize_string(item.get("kind")).lower() == normalized_kind)
                    and (not normalized_status or _normalize_string(item.get("status")).lower() == normalized_status)
                ]
                running_count = int(summary.get("running_count") or 0)
                if len(filtered_running) >= max(1, limit) or running_count <= len(running_sessions):
                    candidate_compacts = filtered_running
            elif not normalized_status:
                recent_sessions = self._normalize_summary_session_list(
                    summary.get("recent_sessions"),
                    limit=SUMMARY_RECENT_SESSION_LIMIT,
                )
                if not normalized_kind:
                    if len(recent_sessions) >= max(1, limit) or int(summary.get("session_count") or 0) <= len(recent_sessions):
                        candidate_compacts = recent_sessions
                else:
                    filtered_recent = [
                        item
                        for item in recent_sessions
                        if _normalize_string(item.get("kind")).lower() == normalized_kind
                    ]
                    if len(filtered_recent) >= max(1, limit) or int(summary.get("session_count") or 0) <= len(recent_sessions):
                        candidate_compacts = filtered_recent
            if candidate_compacts is not None:
                resolved_sessions: list[dict[str, Any]] = []
                for compact in candidate_compacts:
                    bash_id = _normalize_string(compact.get("bash_id"))
                    if not bash_id:
                        continue
                    try:
                        resolved_sessions.append(self.reconcile_session(quest_root, bash_id))
                    except FileNotFoundError:
                        continue
                    if len(resolved_sessions) >= max(1, limit):
                        break
                return resolved_sessions[: max(1, limit)]
        sessions: list[dict[str, Any]] = []
        for bash_id in self._list_session_ids(quest_root):
            try:
                session = self.reconcile_session(quest_root, bash_id)
            except FileNotFoundError:
                continue
            session_status = _normalize_string(session.get("status")).lower()
            if normalized_status and session_status != normalized_status:
                continue
            if normalized_kind and _normalize_string(session.get("kind")).lower() != normalized_kind:
                continue
            if normalized_agent_instance_ids and str(session.get("agent_instance_id") or "") not in normalized_agent_instance_ids:
                continue
            if normalized_agent_ids and str(session.get("agent_id") or "") not in normalized_agent_ids:
                continue
            if normalized_chat_session and str(session.get("chat_session_id") or "") != normalized_chat_session:
                continue
            sessions.append(session)
        sessions.sort(key=_session_sort_key, reverse=True)
        return sessions[: max(1, limit)]

    def resolve_session_id(self, quest_root: Path, session_ref: str | None = None) -> str:
        normalized = _normalize_string(session_ref)
        if normalized:
            if self.meta_path(quest_root, normalized).exists():
                return normalized
            raise FileNotFoundError(f"Unknown bash session `{normalized}`.")
        summary = self.summary(quest_root)
        latest_session = summary.get("latest_session")
        latest_bash_id = _normalize_string((latest_session or {}).get("bash_id") if isinstance(latest_session, dict) else "")
        if latest_bash_id and self.meta_path(quest_root, latest_bash_id).exists():
            return latest_bash_id
        sessions = self.list_sessions(quest_root, limit=1)
        if not sessions:
            raise FileNotFoundError("No bash session found.")
        return str(sessions[0]["bash_id"])

    def read_terminal_log(self, quest_root: Path, bash_id: str) -> str:
        path = self.terminal_log_path(quest_root, bash_id)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")

    def read_log_entries(
        self,
        quest_root: Path,
        bash_id: str,
        *,
        limit: int = DEFAULT_LOG_TAIL_LIMIT,
        before_seq: int | None = None,
        after_seq: int | None = None,
        order: str = "asc",
        prefer_visible: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not self.meta_path(quest_root, bash_id).exists():
            raise FileNotFoundError(f"Unknown bash session `{bash_id}`.")
        deadline = time.monotonic() + 0.6
        path = self.log_path(quest_root, bash_id)
        entries = read_jsonl_tail(path, max(1, limit))
        while time.monotonic() < deadline:
            if any(str(entry.get("stream") or "") not in {"system", "prompt"} for entry in entries):
                break
            session = read_json(self.meta_path(quest_root, bash_id), {}) or {}
            status = _coerce_session_status(session.get("status"))
            if status in TERMINAL_STATUSES:
                break
            if entries:
                time.sleep(0.05)
            else:
                time.sleep(0.03)
            entries = read_jsonl_tail(path, max(1, limit))
        latest_seq = int(entries[-1].get("seq") or 0) if entries else 0
        normalized_before = before_seq if isinstance(before_seq, int) and before_seq > 0 else None
        normalized_after = after_seq if isinstance(after_seq, int) and after_seq >= 0 else None
        normalized_limit = max(1, limit)
        selection_pool: deque[dict[str, Any]] = deque(maxlen=normalized_limit)
        visible_pool: deque[dict[str, Any]] = deque(maxlen=normalized_limit)
        total_filtered = 0
        for entry in iter_jsonl(path):
            seq = int(entry.get("seq") or 0)
            latest_seq = max(latest_seq, seq)
            if normalized_after is not None and seq <= normalized_after:
                continue
            if normalized_before is not None and seq >= normalized_before:
                continue
            total_filtered += 1
            selection_pool.append(entry)
            if str(entry.get("stream") or "") not in {"system", "prompt"}:
                visible_pool.append(entry)
        selected_source: list[dict[str, Any]]
        if prefer_visible and visible_pool:
            selected_source = list(visible_pool)
            truncated = total_filtered > len(visible_pool)
        else:
            selected_source = list(selection_pool)
            truncated = total_filtered > len(selection_pool)
        selected = selected_source[-normalized_limit:]
        if order == "desc":
            selected = list(reversed(selected))
        tail_start_seq = int(selected[0].get("seq") or 0) if selected else None
        meta = {
            "tail_limit": normalized_limit,
            "tail_start_seq": tail_start_seq if truncated else tail_start_seq,
            "latest_seq": latest_seq or None,
            "after_seq": normalized_after,
            "before_seq": normalized_before,
        }
        return selected, meta

    def wait_for_session(
        self,
        quest_root: Path,
        bash_id: str,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds if timeout_seconds and timeout_seconds > 0 else None
        while True:
            session = self.get_session(quest_root, bash_id)
            if _normalize_string(session.get("status")).lower() in TERMINAL_STATUSES:
                return session
            if deadline is not None and time.monotonic() >= deadline:
                return session
            time.sleep(max(0.1, poll_interval))

    def request_stop(
        self,
        quest_root: Path,
        bash_id: str,
        *,
        reason: str | None = None,
        user_id: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        session = self.get_session(quest_root, bash_id)
        status = _normalize_string(session.get("status")).lower()
        if status in TERMINAL_STATUSES:
            return session
        request_payload = {
            "reason": _normalize_string(reason) or "user_stop",
            "user_id": _normalize_string(user_id) or _normalize_string(session.get("agent_id")) or "agent",
            "requested_at": utc_now(),
            "force": bool(force),
        }
        _atomic_write_json(self.stop_request_path(quest_root, bash_id), request_payload)
        meta = read_json(self.meta_path(quest_root, bash_id), {})
        meta["status"] = "terminating"
        meta["stop_reason"] = request_payload["reason"]
        meta["stopped_by_user_id"] = request_payload["user_id"]
        meta["updated_at"] = utc_now()
        self._write_meta(quest_root, bash_id, meta)
        runtime = self._terminal_runtime_manager.get_runtime(quest_root, bash_id)
        if runtime is not None:
            runtime.stop(reason=request_payload["reason"], force=bool(force))
        else:
            terminate_process_ids(
                process_pid=meta.get("process_pid") if isinstance(meta.get("process_pid"), int) else None,
                process_group_id=meta.get("process_group_id") if isinstance(meta.get("process_group_id"), int) else None,
                force=bool(force),
            )
        return self._session_payload(quest_root, meta)

    def _build_initial_meta(
        self,
        *,
        context: McpContext,
        bash_id: str,
        command: str,
        launch_argv: list[str] | None,
        mode: str,
        cwd: Path,
        workdir_display: str,
        timeout_seconds: int | None,
        env_keys: list[str],
        comment: str | dict[str, Any] | None = None,
        kind: str = "exec",
        shell_family: str | None = None,
        shell_name: str | None = None,
    ) -> dict[str, Any]:
        quest_root = context.require_quest_root().resolve()
        session_id = _normalize_string(context.conversation_id) or f"quest:{context.quest_id or quest_root.name}"
        agent_id = _normalize_string(context.agent_role) or "pi"
        agent_instance_id = _normalize_string(context.worker_id) or _normalize_string(context.run_id) or session_id
        started_by_user_id = f"agent:{agent_id}"
        timestamp = utc_now()
        return {
            "id": bash_id,
            "bash_id": bash_id,
            "quest_id": context.quest_id or quest_root.name,
            "project_id": context.quest_id or quest_root.name,
            "session_id": session_id,
            "chat_session_id": session_id,
            "task_id": _normalize_string(context.run_id) or session_id,
            "cli_server_id": "deepscientist-local",
            "agent_id": agent_id,
            "agent_instance_id": agent_instance_id,
            "started_by_user_id": started_by_user_id,
            "stopped_by_user_id": None,
            "comment": comment,
            "command": command,
            "launch_argv": list(launch_argv or []),
            "shell_family": shell_family,
            "shell_name": shell_name,
            "workdir": workdir_display,
            "cwd": str(cwd),
            "kind": kind,
            "log_path": self._session_log_relative_path(quest_root, bash_id),
            "mode": mode,
            "status": "running",
            "exit_code": None,
            "stop_reason": None,
            "last_progress": None,
            "last_output_at": None,
            "last_output_seq": None,
            "started_at": timestamp,
            "finished_at": None,
            "updated_at": timestamp,
            "latest_seq": 0,
            "timeout_seconds": timeout_seconds,
            "env_keys": env_keys,
            "quest_root": str(quest_root),
            "monitor_pid": None,
            "process_pid": None,
            "process_group_id": None,
        }

    def _start_monitor_process(
        self,
        *,
        quest_root: Path,
        bash_id: str,
        env_payload: dict[str, str] | None = None,
    ) -> int:
        monitor_env = os.environ.copy()
        if env_payload:
            monitor_env["DS_BASH_EXEC_TOOL_ENV"] = json.dumps(env_payload, ensure_ascii=False)
        monitor_log_handle = self.monitor_log_path(quest_root, bash_id).open("a", encoding="utf-8")
        try:
            monitor_process = subprocess.Popen(
                [sys.executable, "-m", "deepscientist.bash_exec.monitor", str(self.session_dir(quest_root, bash_id))],
                stdin=subprocess.DEVNULL,
                stdout=monitor_log_handle,
                stderr=monitor_log_handle,
                cwd=str(quest_root),
                env=monitor_env,
                **process_session_popen_kwargs(hide_window=True),
            )
        finally:
            monitor_log_handle.close()
        return monitor_process.pid

    def start_session(
        self,
        context: McpContext,
        *,
        command: str,
        mode: str,
        workdir: str | None = None,
        env: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not _normalize_string(command):
            raise ValueError("command_required")
        quest_root = context.require_quest_root().resolve()
        cwd, workdir_display = self.resolve_workdir(context, workdir)
        bash_id = generate_id("bash")
        session_dir = self.session_dir(quest_root, bash_id)
        ensure_dir(session_dir)
        env_payload = {str(key): str(value) for key, value in (env or {}).items() if value is not None}
        env_payload.update(self._hardware_env_overrides())
        launch = build_exec_shell_launch(command)
        meta = self._build_initial_meta(
            context=context,
            bash_id=bash_id,
            command=command,
            launch_argv=launch.argv,
            mode=mode,
            cwd=cwd,
            workdir_display=workdir_display,
            timeout_seconds=timeout_seconds,
            env_keys=sorted(env_payload),
            comment=comment,
            kind="exec",
            shell_family=launch.family,
            shell_name=launch.shell_name,
        )
        self.terminal_log_path(quest_root, bash_id).touch()
        self.log_path(quest_root, bash_id).touch()
        self._write_meta(quest_root, bash_id, meta)
        append_jsonl(
            self.index_path(quest_root),
            {
                "event": "created",
                "bash_id": bash_id,
                "quest_id": meta["quest_id"],
                "command": command,
                "comment": comment,
                "workdir": workdir_display,
                "mode": mode,
                "started_at": meta["started_at"],
            },
        )
        meta["monitor_pid"] = self._start_monitor_process(
            quest_root=quest_root,
            bash_id=bash_id,
            env_payload=env_payload,
        )
        meta["updated_at"] = utc_now()
        _atomic_write_json(self.meta_path(quest_root, bash_id), meta)
        return self._session_payload(quest_root, meta)

    def _build_terminal_meta(
        self,
        *,
        quest_root: Path,
        quest_id: str,
        bash_id: str,
        label: str | None,
        cwd: Path,
        workdir_display: str,
        command: str,
        launch_argv: list[str] | None,
        source: str,
        conversation_id: str | None,
        user_id: str | None,
        env_keys: list[str],
        shell_family: str | None = None,
        shell_name: str | None = None,
        transport_preference: str | None = None,
    ) -> dict[str, Any]:
        timestamp = utc_now()
        session_id = _normalize_string(conversation_id) or f"quest:{quest_id}:terminal"
        started_by_user_id = _normalize_string(user_id) or f"user:{source or 'web'}"
        return {
            "id": bash_id,
            "bash_id": bash_id,
            "quest_id": quest_id,
            "project_id": quest_id,
            "session_id": session_id,
            "chat_session_id": session_id,
            "task_id": bash_id,
            "cli_server_id": "deepscientist-local",
            "agent_id": "user",
            "agent_instance_id": None,
            "started_by_user_id": started_by_user_id,
            "stopped_by_user_id": None,
            "label": label,
            "command": command,
            "launch_argv": list(launch_argv or []),
            "shell_family": shell_family,
            "shell_name": shell_name,
            "transport_preference": transport_preference,
            "workdir": workdir_display,
            "cwd": str(cwd),
            "kind": "terminal",
            "source": {"surface": source, "conversation_id": _normalize_string(conversation_id) or None},
            "log_path": self._session_log_relative_path(quest_root, bash_id),
            "mode": "detach",
            "status": "running",
            "exit_code": None,
            "stop_reason": None,
            "last_progress": None,
            "last_output_at": None,
            "last_output_seq": None,
            "started_at": timestamp,
            "finished_at": None,
            "updated_at": timestamp,
            "latest_seq": 0,
            "timeout_seconds": None,
            "env_keys": env_keys,
            "quest_root": str(quest_root),
            "monitor_pid": None,
            "process_pid": None,
            "process_group_id": None,
            "last_input_at": None,
            "last_prompt_at": None,
            "last_command": None,
            "history_count": _count_jsonl_records(self.history_path(quest_root, bash_id)),
        }

    def ensure_terminal_session(
        self,
        quest_root: Path,
        *,
        quest_id: str | None = None,
        bash_id: str = DEFAULT_TERMINAL_SESSION_ID,
        label: str | None = None,
        cwd: Path | None = None,
        source: str = "web",
        conversation_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_quest_root = quest_root.resolve()
        resolved_quest_id = _normalize_string(quest_id) or resolved_quest_root.name
        try:
            session = self.reconcile_session(resolved_quest_root, bash_id)
            runtime = self._terminal_runtime_manager.get_runtime(resolved_quest_root, bash_id)
            if (
                _normalize_string(session.get("kind")).lower() == "terminal"
                and _normalize_string(session.get("status")).lower() not in TERMINAL_STATUSES
                and runtime is not None
            ):
                return session
        except FileNotFoundError:
            session = None

        previous_meta = read_json(self.meta_path(resolved_quest_root, bash_id), {}) if self.meta_path(resolved_quest_root, bash_id).exists() else {}
        previous_cwd = Path(str(previous_meta.get("cwd") or "")).expanduser().resolve() if previous_meta.get("cwd") else None
        previous_label = _normalize_string(previous_meta.get("label") or "") or None
        target_cwd = (cwd or previous_cwd or resolved_quest_root).resolve()
        if not target_cwd.exists() or not target_cwd.is_dir() or not (target_cwd == resolved_quest_root or resolved_quest_root in target_cwd.parents):
            target_cwd = resolved_quest_root
        try:
            workdir_display = target_cwd.relative_to(resolved_quest_root).as_posix()
        except ValueError:
            workdir_display = str(target_cwd)
        workdir_display = "" if workdir_display == "." else workdir_display

        session_dir = self.session_dir(resolved_quest_root, bash_id)
        ensure_dir(session_dir)
        self.terminal_log_path(resolved_quest_root, bash_id).touch()
        self.log_path(resolved_quest_root, bash_id).touch()
        self.input_path(resolved_quest_root, bash_id).touch()
        self.history_path(resolved_quest_root, bash_id).touch()
        self.prompt_events_path(resolved_quest_root, bash_id).touch()
        _atomic_write_json(
            self.input_cursor_path(resolved_quest_root, bash_id),
            {"offset": _count_jsonl_records(self.input_path(resolved_quest_root, bash_id)), "updated_at": utc_now()},
        )
        _atomic_write_json(
            self.line_buffer_path(resolved_quest_root, bash_id),
            {"buffer": "", "updated_at": utc_now()},
        )
        terminal_script_path = session_dir / ("terminal.ps1" if os.name == "nt" else "terminal.rc")
        stop_request = self.stop_request_path(resolved_quest_root, bash_id)
        if stop_request.exists():
            stop_request.unlink()

        env_payload = {
            "DS_TERMINAL_PROMPT_PATH": str(self.prompt_events_path(resolved_quest_root, bash_id)),
        }
        env_payload.update(self._hardware_env_overrides())
        if os.name != "nt":
            terminal_script_path.write_text(
                "\n".join(
                    [
                        "PS1='\\w$ '",
                        "PS2='> '",
                        'PROMPT_COMMAND=\'printf "__DS_TERMINAL_PROMPT__ cwd_b64=%s ts=%s\\n" "$(printf "%s" "$PWD" | base64 | tr -d "\\n")" "$(date -u +%FT%TZ)" >> "${DS_TERMINAL_PROMPT_PATH}"\'',
                        "bind 'set enable-bracketed-paste off' >/dev/null 2>&1 || true",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            env_payload["TERM"] = "xterm-256color"
            env_payload["COLORTERM"] = "truecolor"
        else:
            terminal_script_path.write_text(
                "\n".join(
                    [
                        "$global:__dsPromptPath = $env:DS_TERMINAL_PROMPT_PATH",
                        "function global:prompt {",
                        "    $cwdBytes = [System.Text.Encoding]::UTF8.GetBytes((Get-Location).Path)",
                        "    $cwdB64 = [Convert]::ToBase64String($cwdBytes)",
                        '    $ts = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")',
                        '    Add-Content -LiteralPath $global:__dsPromptPath -Value "__DS_TERMINAL_PROMPT__ cwd_b64=$cwdB64 ts=$ts"',
                        '    return "PS $((Get-Location).Path)> "',
                        "}",
                        "try { Set-PSReadLineOption -BellStyle None | Out-Null } catch {}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
        launch = build_terminal_shell_launch(terminal_script_path)
        command = " ".join(launch.argv)
        resolved_label = _normalize_string(label) or previous_label
        meta = self._build_terminal_meta(
            quest_root=resolved_quest_root,
            quest_id=resolved_quest_id,
            bash_id=bash_id,
            label=resolved_label,
            cwd=target_cwd,
            workdir_display=workdir_display,
            command=command,
            launch_argv=launch.argv,
            source=source,
            conversation_id=conversation_id,
            user_id=user_id,
            env_keys=sorted(env_payload),
            shell_family=launch.family,
            shell_name=launch.shell_name,
            transport_preference="pipe" if os.name == "nt" else "pty",
        )
        self._write_meta(resolved_quest_root, bash_id, meta)
        append_jsonl(
            self.index_path(resolved_quest_root),
            {
                "event": "terminal_ensured",
                "bash_id": bash_id,
                "quest_id": resolved_quest_id,
                "workdir": workdir_display,
                "source": source,
                "started_at": meta["started_at"],
            },
        )
        meta = self._terminal_runtime_manager.ensure_runtime(
            quest_root=resolved_quest_root,
            bash_id=bash_id,
            meta_path=self.meta_path(resolved_quest_root, bash_id),
            log_path=self.log_path(resolved_quest_root, bash_id),
            terminal_log_path=self.terminal_log_path(resolved_quest_root, bash_id),
            prompt_events_path=self.prompt_events_path(resolved_quest_root, bash_id),
            env_payload=env_payload,
            command=command,
            launch_argv=launch.argv,
            cwd=target_cwd,
            transport_preference="pipe" if os.name == "nt" else "pty",
        )
        meta["updated_at"] = utc_now()
        self._write_meta(resolved_quest_root, bash_id, meta)
        return self._session_payload(resolved_quest_root, meta)

    def _update_terminal_line_buffer(
        self,
        quest_root: Path,
        bash_id: str,
        *,
        data: str,
        source: str,
        user_id: str | None,
        conversation_id: str | None,
    ) -> list[dict[str, Any]]:
        path = self.line_buffer_path(quest_root, bash_id)
        payload = read_json(path, {}) or {}
        buffer = str(payload.get("buffer") or "")
        sanitized = INPUT_ESCAPE_SEQUENCE_RE.sub("", data.replace("\r\n", "\n"))
        completed: list[dict[str, Any]] = []
        for char in sanitized:
            if char in {"\r", "\n"}:
                command = buffer.strip()
                if command:
                    entry = {
                        "command_id": generate_id("cmd"),
                        "command": command,
                        "source": source,
                        "user_id": _normalize_string(user_id) or None,
                        "conversation_id": _normalize_string(conversation_id) or None,
                        "submitted_at": utc_now(),
                    }
                    completed.append(entry)
                buffer = ""
                continue
            if char in {"\b", "\x7f"}:
                buffer = buffer[:-1]
                continue
            if ord(char) < 32 and char not in {"\t"}:
                continue
            buffer += char
        _atomic_write_json(path, {"buffer": buffer, "updated_at": utc_now()})
        return completed

    def append_terminal_input(
        self,
        quest_root: Path,
        bash_id: str,
        *,
        data: str,
        source: str = "web",
        user_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_data = str(data or "")
        if not normalized_data:
            raise ValueError("terminal_input_required")
        session = self.reconcile_session(quest_root, bash_id)
        status = _normalize_string(session.get("status")).lower()
        if status in TERMINAL_STATUSES:
            raise ValueError("terminal_session_inactive")
        runtime = self._terminal_runtime_manager.get_runtime(quest_root, bash_id)
        if runtime is None and _normalize_string(session.get("kind")).lower() == "terminal":
            raise ValueError("terminal_runtime_inactive")
        if runtime is not None:
            runtime.write_input(normalized_data)

        entry = {
            "input_id": generate_id("tin"),
            "data": normalized_data,
            "source": source,
            "user_id": _normalize_string(user_id) or None,
            "conversation_id": _normalize_string(conversation_id) or None,
            "submitted_at": utc_now(),
        }
        append_jsonl(self.input_path(quest_root, bash_id), entry)
        completed = self._update_terminal_line_buffer(
            quest_root,
            bash_id,
            data=normalized_data,
            source=source,
            user_id=user_id,
            conversation_id=conversation_id,
        )
        if completed:
            for item in completed:
                append_jsonl(self.history_path(quest_root, bash_id), item)
            meta = read_json(self.meta_path(quest_root, bash_id), {})
            meta["last_command"] = completed[-1]["command"]
            meta["history_count"] = _count_jsonl_records(self.history_path(quest_root, bash_id))
            meta["updated_at"] = utc_now()
            meta["last_input_at"] = utc_now()
            self._write_meta(quest_root, bash_id, meta)
        else:
            meta = read_json(self.meta_path(quest_root, bash_id), {})
            meta["updated_at"] = utc_now()
            meta["last_input_at"] = utc_now()
            self._write_meta(quest_root, bash_id, meta)
        return {
            "ok": True,
            "session": self._session_payload(quest_root, read_json(self.meta_path(quest_root, bash_id), {})),
            "accepted_input": entry,
            "completed_commands": completed,
        }

    def resize_terminal_session(self, quest_root: Path, bash_id: str, *, cols: int, rows: int) -> bool:
        runtime = self._terminal_runtime_manager.get_runtime(quest_root, bash_id)
        if runtime is None:
            return False
        runtime.resize(cols, rows)
        return True

    def issue_terminal_attach_token(self, quest_root: Path, bash_id: str, *, ttl_seconds: int = 60) -> dict[str, Any]:
        session = self.reconcile_session(quest_root, bash_id)
        status = _normalize_string(session.get("status")).lower()
        if status in TERMINAL_STATUSES:
            raise ValueError("terminal_session_inactive")
        token = self._terminal_runtime_manager.issue_attach_token(
            quest_root,
            bash_id,
            ttl_seconds=ttl_seconds,
        )
        return {
            "token": token.token,
            "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(token.expires_at)),
        }

    def get_terminal_runtime(self, quest_root: Path, bash_id: str):
        return self._terminal_runtime_manager.get_runtime(quest_root, bash_id)

    def consume_terminal_attach_token(self, token: str):
        return self._terminal_runtime_manager.consume_attach_token(token)

    def resolve_terminal_attach_token(self, token: str):
        return self._terminal_runtime_manager.resolve_attach_token(token)

    def shutdown(self) -> None:
        self._terminal_runtime_manager.shutdown()

    def terminal_restore_payload(
        self,
        quest_root: Path,
        bash_id: str = DEFAULT_TERMINAL_SESSION_ID,
        *,
        command_limit: int = 10,
        output_limit: int = 80,
    ) -> dict[str, Any]:
        session = self.reconcile_session(quest_root, bash_id)
        entries, meta = self.read_log_entries(
            quest_root,
            bash_id,
            limit=max(1, output_limit),
            before_seq=None,
            order="asc",
        )
        history = read_jsonl_tail(self.history_path(quest_root, bash_id), max(1, command_limit))
        latest_commands = [
            {
                "command_id": item.get("command_id"),
                "command": item.get("command"),
                "source": item.get("source"),
                "submitted_at": item.get("submitted_at"),
            }
            for item in history[-max(1, command_limit):]
        ]
        tail = [
            {
                "seq": entry.get("seq"),
                "stream": entry.get("stream"),
                "line": entry.get("line"),
                "timestamp": entry.get("timestamp"),
            }
            for entry in entries
        ]
        return {
            "ok": True,
            "session_id": bash_id,
            "status": session.get("status"),
            "cwd": session.get("cwd"),
            "latest_commands": latest_commands,
            "tail": tail,
            "latest_seq": meta.get("latest_seq"),
            "tail_start_seq": meta.get("tail_start_seq"),
            "session": session,
        }

    def build_tool_result(
        self,
        context: McpContext,
        *,
        session: dict[str, Any],
        include_log: bool = False,
        export_log: bool = False,
        export_log_to: str | None = None,
    ) -> dict[str, Any]:
        quest_root = context.require_quest_root().resolve()
        result = {
            "id": session["bash_id"],
            "bash_id": session["bash_id"],
            "log_path": session.get("log_path"),
            "status": session.get("status"),
            "kind": session.get("kind"),
            "comment": session.get("comment"),
            "label": session.get("label"),
            "command": session.get("command"),
            "workdir": session.get("workdir"),
            "cwd": session.get("cwd"),
            "started_at": session.get("started_at"),
            "finished_at": session.get("finished_at"),
            "exit_code": session.get("exit_code"),
            "stop_reason": session.get("stop_reason"),
            "last_progress": session.get("last_progress"),
            "last_progress_at": session.get("last_progress_at"),
            "last_output_at": session.get("last_output_at"),
            "last_output_seq": session.get("last_output_seq"),
            "run_age_seconds": session.get("run_age_seconds"),
            "status_age_seconds": session.get("status_age_seconds"),
            "silent_seconds": session.get("silent_seconds"),
            "progress_age_seconds": session.get("progress_age_seconds"),
            "latest_signal_at": session.get("latest_signal_at"),
            "signal_age_seconds": session.get("signal_age_seconds"),
            "watchdog_after_seconds": session.get("watchdog_after_seconds"),
            "watchdog_overdue": session.get("watchdog_overdue"),
        }
        if include_log:
            result.update(self._log_preview_payload(quest_root, str(session["bash_id"])))
        if export_log or _normalize_string(export_log_to):
            cwd, _ = self.resolve_workdir(context, str(session.get("workdir") or ""))
            result.update(
                self._export_log(
                    quest_root=quest_root,
                    cwd=cwd,
                    bash_id=str(session["bash_id"]),
                    export_log=export_log,
                    export_log_to=export_log_to,
                )
            )
        return result

    def _log_preview_payload(self, quest_root: Path, bash_id: str) -> dict[str, Any]:
        return _build_terminal_log_preview_payload(self.terminal_log_path(quest_root, bash_id))
