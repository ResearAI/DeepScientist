from __future__ import annotations

import copy
from collections import deque
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import hashlib
import json
import mimetypes
import re
import shutil
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

try:
    import fcntl  # pragma: no cover - exercised on POSIX
except ImportError:  # pragma: no cover - exercised on Windows
    fcntl = None

from ..artifact.metrics import build_baseline_compare_payload, build_metrics_timeline, extract_latest_metric
from ..config import ConfigManager
from ..connector_runtime import conversation_identity_key, normalize_conversation_id, parse_conversation_id
from ..file_lock import advisory_file_lock
from ..gitops import current_branch, export_git_graph, head_commit, init_repo, list_branch_canvas, list_commit_canvas
from ..home import repo_root
from ..registries import BaselineRegistry
from ..shared import append_jsonl, ensure_dir, generate_id, iter_jsonl, read_json, read_jsonl, read_jsonl_tail, read_text, read_yaml, resolve_within, run_command, run_command_bytes, sha256_text, slugify, utc_now, write_json, write_text, write_yaml
from ..skills import SkillInstaller
from ..web_search import extract_web_search_payload
from .layout import (
    QUEST_DIRECTORIES,
    default_active_anchor,
    gitignore,
    initial_brief,
    initial_plan,
    initial_quest_yaml,
    initial_status,
    initial_summary,
)
from .node_traces import QuestNodeTraceManager
from .stage_views import QuestStageViewBuilder

_UNSET = object()
_NUMERIC_QUEST_ID_PATTERN = re.compile(r"^\d{1,10}$")
_SYSTEM_NUMERIC_QUEST_ID_PATTERN = re.compile(r"^(?P<prefix>[SB])-(?P<number>\d{1,10})$", re.IGNORECASE)
_MAX_NUMERIC_QUEST_ID_VALUE = 9_999_999_999
_NUMERIC_QUEST_ID_PAD_WIDTH = 3
_CRASH_AUTO_RESUME_WINDOW = timedelta(hours=24)
_JSONL_CACHE_MAX_BYTES = 4 * 1024 * 1024
_CODEX_HISTORY_TAIL_LIMIT = 400
_JSONL_STREAM_CHUNK_BYTES = 64 * 1024
_JSONL_LINE_COUNT_CACHE_SUFFIX = ".linecount.json"
_EVENTS_OVERSIZED_LINE_BYTES = 8 * 1024 * 1024
_OVERSIZED_EVENT_PREFIX_BYTES = 4096
_PROJECTION_SCHEMA_VERSION = 1
_PROJECTION_BUILD_TOTAL_STEPS = 3
_PROJECTION_REFRESH_THROTTLE_SECONDS = 1.0
_SHARED_MEMORY_DOCUMENT_PREFIX = "sharedmemory::"
_EVENT_TYPE_BYTES_RE = re.compile(rb'"(?:type|event_type)"\s*:\s*"([^"]+)"')
_EVENT_TOOL_NAME_BYTES_RE = re.compile(rb'"tool_name"\s*:\s*"([^"]+)"')
_EVENT_RUN_ID_BYTES_RE = re.compile(rb'"run_id"\s*:\s*"([^"]+)"')
CONTINUATION_POLICIES = {"auto", "when_external_progress", "wait_for_user_or_resume", "none"}
_CHAT_ATTACHMENT_TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".mdx", ".json", ".csv", ".log", ".yaml", ".yml"}
_CHAT_ATTACHMENT_TEXT_MIME_PREFIXES = ("text/",)
_CHAT_ATTACHMENT_TEXT_MIME_TYPES = {"application/json", "application/x-yaml", "text/csv"}


def _oversized_event_placeholder(*, prefix: bytes, line_bytes: int) -> dict[str, Any]:
    def _extract(pattern: re.Pattern[bytes]) -> str | None:
        match = pattern.search(prefix)
        if match is None:
            return None
        try:
            return match.group(1).decode("utf-8", errors="ignore").strip() or None
        except Exception:
            return None

    event_type = _extract(_EVENT_TYPE_BYTES_RE) or "runner.tool_result"
    tool_name = _extract(_EVENT_TOOL_NAME_BYTES_RE)
    run_id = _extract(_EVENT_RUN_ID_BYTES_RE)
    summary = f"Omitted oversized quest event payload ({line_bytes} bytes) while reading event history."
    payload: dict[str, Any] = {
        "type": event_type,
        "status": "omitted",
        "summary": summary,
        "oversized_event": True,
        "oversized_bytes": line_bytes,
    }
    if tool_name:
        payload["tool_name"] = tool_name
    if run_id:
        payload["run_id"] = run_id
    return payload


def _iter_jsonl_records_safely(
    path: Path,
    *,
    oversized_line_bytes: int = _EVENTS_OVERSIZED_LINE_BYTES,
):
    if not path.exists():
        return
    with path.open("rb") as handle:
        buffer = bytearray()
        prefix = bytearray()
        current_bytes = 0
        oversized = False
        cursor = 0
        while True:
            chunk = handle.read(_JSONL_STREAM_CHUNK_BYTES)
            if not chunk:
                break
            start = 0
            while start <= len(chunk):
                newline_index = chunk.find(b"\n", start)
                has_newline = newline_index >= 0
                segment = chunk[start:newline_index] if has_newline else chunk[start:]

                if oversized:
                    current_bytes += len(segment)
                    if has_newline:
                        cursor += 1
                        yield cursor, _oversized_event_placeholder(prefix=bytes(prefix), line_bytes=current_bytes)
                        prefix = bytearray()
                        current_bytes = 0
                        oversized = False
                        start = newline_index + 1
                        continue
                    break

                next_bytes = current_bytes + len(segment)
                if next_bytes > oversized_line_bytes:
                    combined_prefix = bytes(buffer)
                    remaining = max(0, _OVERSIZED_EVENT_PREFIX_BYTES - len(combined_prefix))
                    if remaining:
                        combined_prefix += segment[:remaining]
                    prefix = bytearray(combined_prefix)
                    buffer.clear()
                    current_bytes = next_bytes
                    oversized = True
                    if has_newline:
                        cursor += 1
                        yield cursor, _oversized_event_placeholder(prefix=bytes(prefix), line_bytes=current_bytes)
                        prefix = bytearray()
                        current_bytes = 0
                        oversized = False
                        start = newline_index + 1
                        continue
                    break

                buffer.extend(segment)
                current_bytes = next_bytes
                if has_newline:
                    raw = bytes(buffer).strip()
                    buffer.clear()
                    line_bytes = current_bytes
                    current_bytes = 0
                    cursor += 1
                    payload = _parse_jsonl_record_line_safely(
                        raw,
                        oversized_line_bytes=oversized_line_bytes,
                    )
                    yield cursor, payload
                    start = newline_index + 1
                    continue
                break

        if oversized:
            cursor += 1
            yield cursor, _oversized_event_placeholder(prefix=bytes(prefix), line_bytes=current_bytes)
        elif buffer:
            raw = bytes(buffer).strip()
            cursor += 1
            payload = _parse_jsonl_record_line_safely(
                raw,
                oversized_line_bytes=oversized_line_bytes,
            )
            yield cursor, payload


def _parse_jsonl_record_line_safely(
    raw_line: bytes,
    *,
    oversized_line_bytes: int = _EVENTS_OVERSIZED_LINE_BYTES,
) -> dict[str, Any] | None:
    raw = bytes(raw_line).strip()
    if not raw:
        return None
    line_bytes = len(raw)
    if line_bytes > oversized_line_bytes:
        return _oversized_event_placeholder(
            prefix=raw[:_OVERSIZED_EVENT_PREFIX_BYTES],
            line_bytes=line_bytes,
        )
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _jsonl_line_count_cache_path(path: Path) -> Path:
    return path.with_name(f".{path.name}{_JSONL_LINE_COUNT_CACHE_SUFFIX}")


def _jsonl_path_state(path: Path) -> tuple[int, int, int] | None:
    if not path.exists():
        return None
    stat = path.stat()
    return (
        stat.st_ino,
        getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)),
        stat.st_size,
    )


def _jsonl_line_count_from_cache(path: Path) -> int | None:
    current_state = _jsonl_path_state(path)
    if current_state is None:
        return 0

    cache_path = _jsonl_line_count_cache_path(path)
    payload = read_json(cache_path, {})
    if not isinstance(payload, dict):
        payload = {}
    raw_state = payload.get("state")
    raw_total = payload.get("total")
    if not isinstance(raw_state, (list, tuple)) or len(raw_state) != 3:
        return None
    try:
        cached_state = tuple(int(item) for item in raw_state)
        cached_total = int(raw_total)
    except (TypeError, ValueError):
        return None
    if cached_total < 0:
        return None
    if cached_state == current_state:
        return cached_total

    # If the file only grew through append-only writes, count just the delta.
    if cached_state[0] == current_state[0] and current_state[2] > cached_state[2]:
        appended_count = 0
        for relative_cursor, _payload in _iter_jsonl_records_from_offset_safely(
            path,
            start_offset=cached_state[2],
        ):
            appended_count = relative_cursor
        total = cached_total + appended_count
        write_json(
            cache_path,
            {
                "state": list(current_state),
                "total": total,
            },
        )
        return total
    return None


def _tail_jsonl_records_safely(
    path: Path,
    *,
    limit: int,
    oversized_line_bytes: int = _EVENTS_OVERSIZED_LINE_BYTES,
) -> tuple[list[tuple[int, dict[str, Any]]], int]:
    normalized_limit = max(int(limit or 0), 0)
    if normalized_limit <= 0 or not path.exists():
        return [], 0
    total = _count_jsonl_lines_fast(path)
    if total <= 0:
        return [], 0

    raw_tail = _read_jsonl_tail_lines_fast(path, normalized_limit)
    if not raw_tail:
        return [], total

    cursor_start = max(total - len(raw_tail) + 1, 1)
    parsed: list[tuple[int, dict[str, Any]]] = []
    for cursor, raw_line in enumerate(raw_tail, start=cursor_start):
        payload = _parse_jsonl_record_line_safely(
            raw_line,
            oversized_line_bytes=oversized_line_bytes,
        )
        if isinstance(payload, dict):
            parsed.append((cursor, payload))
    return parsed, total


def _count_jsonl_lines_fast(path: Path, *, chunk_size: int = 1024 * 1024) -> int:
    if not path.exists():
        return 0
    cached_total = _jsonl_line_count_from_cache(path)
    if cached_total is not None:
        return cached_total
    total = 0
    last_byte = b""
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            total += chunk.count(b"\n")
            last_byte = chunk[-1:]
    if total == 0 and last_byte:
        total = 1
    elif last_byte not in {b"", b"\n"}:
        total += 1
    state = _jsonl_path_state(path)
    if state is not None:
        write_json(
            _jsonl_line_count_cache_path(path),
            {
                "state": list(state),
                "total": total,
            },
        )
    return total


def _read_jsonl_tail_lines_fast(path: Path, limit: int, *, chunk_size: int = 1024 * 1024) -> list[bytes]:
    normalized_limit = max(int(limit or 0), 0)
    if normalized_limit <= 0 or not path.exists():
        return []

    size = path.stat().st_size
    if size <= 0:
        return []

    lines: deque[bytes] = deque()
    remainder = b""
    with path.open("rb") as handle:
        position = size
        while position > 0 and len(lines) < normalized_limit:
            read_size = min(chunk_size, position)
            position -= read_size
            handle.seek(position)
            chunk = handle.read(read_size)
            payload = chunk + remainder
            parts = payload.split(b"\n")
            remainder = parts[0]
            for raw_line in reversed(parts[1:]):
                stripped = raw_line.rstrip(b"\r")
                if not stripped.strip():
                    continue
                lines.appendleft(stripped)
                if len(lines) >= normalized_limit:
                    break
        if len(lines) < normalized_limit and remainder.strip():
            lines.appendleft(remainder.rstrip(b"\r"))
    return list(lines)[-normalized_limit:]


def _iter_jsonl_records_from_offset_safely(
    path: Path,
    *,
    start_offset: int,
    oversized_line_bytes: int = _EVENTS_OVERSIZED_LINE_BYTES,
):
    if not path.exists():
        return
    with path.open("rb") as handle:
        handle.seek(max(int(start_offset or 0), 0))
        for relative_cursor, raw_line in enumerate(handle, start=1):
            payload = _parse_jsonl_record_line_safely(
                raw_line,
                oversized_line_bytes=oversized_line_bytes,
            )
            yield relative_cursor, payload


class QuestService:
    def __init__(self, home: Path, skill_installer: SkillInstaller | None = None) -> None:
        self.home = home
        self.quests_root = home / "quests"
        self.skill_installer = skill_installer
        self.baseline_registry = BaselineRegistry(home)
        self._file_cache_lock = threading.Lock()
        self._file_cache: dict[str, dict[str, Any]] = {}
        self._jsonl_cache_lock = threading.Lock()
        self._jsonl_cache: dict[str, dict[str, Any]] = {}
        self._jsonl_tail_cache: dict[str, dict[str, Any]] = {}
        self._snapshot_cache_lock = threading.Lock()
        self._snapshot_cache: dict[str, dict[str, Any]] = {}
        self._codex_history_cache_lock = threading.Lock()
        self._codex_history_cache: dict[str, dict[str, Any]] = {}
        self._runtime_state_locks_lock = threading.Lock()
        self._runtime_state_locks: dict[str, threading.Lock] = {}
        self._artifact_projection_locks_lock = threading.Lock()
        self._artifact_projection_locks: dict[str, threading.Lock] = {}
        self._quest_projection_locks_lock = threading.Lock()
        self._quest_projection_locks: dict[str, threading.Lock] = {}
        self._quest_projection_builds_lock = threading.Lock()
        self._quest_projection_builds: dict[str, threading.Thread] = {}
        self._quest_projection_refresh_lock = threading.Lock()
        self._quest_projection_refresh_at: dict[str, float] = {}

    def _configured_default_runner(self) -> str:
        config = ConfigManager(self.home).load_named("config")
        return self._resolve_enabled_runner_name(config.get("default_runner"))

    def _resolve_enabled_runner_name(self, *candidates: Any) -> str:
        runners = ConfigManager(self.home).load_runners_config()
        seen: set[str] = set()
        enabled: list[str] = []
        for name, cfg in runners.items():
            normalized = str(name or "").strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            if isinstance(cfg, dict) and cfg.get("enabled") is not False:
                enabled.append(normalized)

        checked: set[str] = set()
        for raw in [*candidates, "codex"]:
            normalized = str(raw or "").strip().lower()
            if not normalized or normalized in checked:
                continue
            checked.add(normalized)
            cfg = runners.get(normalized)
            if isinstance(cfg, dict) and cfg.get("enabled") is not False:
                return normalized
        return enabled[0] if enabled else "codex"

    def _quest_root(self, quest_id: str) -> Path:
        return self.quests_root / quest_id

    def _require_initialized_quest_root(self, quest_id: str) -> Path:
        quest_root = self._quest_root(quest_id)
        if not quest_root.exists() or not self._quest_yaml_path(quest_root).exists():
            raise FileNotFoundError(f"Unknown quest `{quest_id}`.")
        return quest_root

    def _normalized_binding_sources(self, sources: list[Any] | None) -> list[str]:
        local_present = False
        external_sources: list[str] = []
        external_index: dict[str, int] = {}
        for raw in sources or []:
            normalized = self._normalize_binding_source(raw)
            if not normalized:
                continue
            parsed = parse_conversation_id(normalized)
            connector = str((parsed or {}).get("connector") or "").strip().lower()
            if normalized == "local:default" or connector == "local":
                local_present = True
                continue
            identity = conversation_identity_key(normalized)
            existing_index = external_index.get(identity)
            if existing_index is None:
                external_index[identity] = len(external_sources)
                external_sources.append(normalized)
            else:
                external_sources[existing_index] = normalized
        if local_present:
            return ["local:default", *external_sources]
        return external_sources

    def _binding_sources_payload(self, quest_root: Path) -> dict[str, list[str]]:
        bindings_path = quest_root / ".ds" / "bindings.json"
        payload = read_json(bindings_path, {"sources": []})
        raw_sources = payload.get("sources") if isinstance(payload, dict) else []
        sources = self._normalized_binding_sources(raw_sources if isinstance(raw_sources, list) else [])
        return {"sources": sources}

    def preferred_locale(self, quest_root: Path | None = None) -> str:
        if quest_root is not None:
            try:
                quest_yaml = self.read_quest_yaml(quest_root)
            except Exception:
                quest_yaml = {}
            if isinstance(quest_yaml, dict):
                for key in ("locale", "default_locale", "user_locale", "user_language", "language"):
                    value = str(quest_yaml.get(key) or "").strip()
                    if value:
                        return value.lower()
        config = ConfigManager(self.home).load_named("config")
        return str(config.get("default_locale") or "en-US").lower()

    def localized_copy(self, *, zh: str, en: str, quest_root: Path | None = None) -> str:
        return zh if self.preferred_locale(quest_root).startswith("zh") else en

    @staticmethod
    def _quest_yaml_path(quest_root: Path) -> Path:
        return quest_root / "quest.yaml"

    def _quest_id_state_path(self) -> Path:
        return self.home / "runtime" / "quest_id_state.json"

    def _quest_id_lock_path(self) -> Path:
        return self.home / "runtime" / "quest_id_state.lock"

    @staticmethod
    def _runtime_state_lock_path(quest_root: Path) -> Path:
        return quest_root / ".ds" / "runtime_state.lock"

    @staticmethod
    def _normalize_baseline_gate(value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"pending", "confirmed", "waived"}:
            raise ValueError("`baseline_gate` must be one of: pending, confirmed, waived.")
        return normalized

    def read_quest_yaml(self, quest_root: Path) -> dict[str, Any]:
        payload = self._read_cached_yaml(self._quest_yaml_path(quest_root), {})
        if not isinstance(payload, dict):
            payload = {}
        normalized = dict(payload)
        startup_contract = dict(normalized.get("startup_contract") or {}) if isinstance(normalized.get("startup_contract"), dict) else None
        normalized.setdefault("startup_contract", startup_contract)
        normalized.setdefault("baseline_gate", "pending")
        normalized.setdefault("confirmed_baseline_ref", None)
        normalized.setdefault("requested_baseline_ref", None)
        active_anchor = str(normalized.get("active_anchor") or "").strip()
        if not active_anchor:
            normalized["active_anchor"] = default_active_anchor(startup_contract)
        elif (
            active_anchor == "baseline"
            and str((startup_contract or {}).get("workspace_mode") or "").strip().lower() == "copilot"
            and not isinstance(normalized.get("confirmed_baseline_ref"), dict)
            and not isinstance(normalized.get("requested_baseline_ref"), dict)
        ):
            normalized["active_anchor"] = "scout"
        return normalized

    @staticmethod
    def _research_state_path(quest_root: Path) -> Path:
        return quest_root / ".ds" / "research_state.json"

    @staticmethod
    def _lab_canvas_state_path(quest_root: Path) -> Path:
        return quest_root / ".ds" / "lab_canvas_state.json"

    def _default_research_state(self, quest_root: Path) -> dict[str, Any]:
        quest_yaml = self.read_quest_yaml(quest_root)
        startup_contract = (
            dict(quest_yaml.get("startup_contract") or {})
            if isinstance(quest_yaml.get("startup_contract"), dict)
            else {}
        )
        workspace_mode = str(startup_contract.get("workspace_mode") or "").strip().lower() or "quest"
        return {
            "version": 1,
            "active_idea_id": None,
            "research_head_branch": None,
            "research_head_worktree_root": None,
            "current_workspace_branch": None,
            "current_workspace_root": None,
            "active_idea_md_path": None,
            "active_idea_draft_path": None,
            "active_analysis_campaign_id": None,
            "analysis_parent_branch": None,
            "analysis_parent_worktree_root": None,
            "paper_parent_branch": None,
            "paper_parent_worktree_root": None,
            "paper_parent_run_id": None,
            "next_pending_slice_id": None,
            "workspace_mode": workspace_mode,
            "last_flow_type": None,
            "updated_at": utc_now(),
        }

    def _default_lab_canvas_state(self, quest_root: Path) -> dict[str, Any]:
        return {
            "version": 1,
            "layout_json": {
                "branch": {},
                "event": {},
                "stage": {},
                "preferences": {},
            },
            "updated_at": utc_now(),
        }

    def read_research_state(self, quest_root: Path) -> dict[str, Any]:
        self._initialize_runtime_files(quest_root)
        defaults = self._default_research_state(quest_root)
        payload = self._read_cached_json(self._research_state_path(quest_root), defaults)
        if not isinstance(payload, dict):
            payload = defaults
        merged = {**defaults, **payload}
        worktree_root = str(merged.get("research_head_worktree_root") or "").strip()
        if worktree_root and not Path(worktree_root).exists():
            merged["research_head_worktree_root"] = None
        current_root = str(merged.get("current_workspace_root") or "").strip()
        if current_root and not Path(current_root).exists():
            merged["current_workspace_root"] = None
        parent_root = str(merged.get("analysis_parent_worktree_root") or "").strip()
        if parent_root and not Path(parent_root).exists():
            merged["analysis_parent_worktree_root"] = None
        paper_parent_root = str(merged.get("paper_parent_worktree_root") or "").strip()
        if paper_parent_root and not Path(paper_parent_root).exists():
            merged["paper_parent_worktree_root"] = None
        return merged

    def write_research_state(self, quest_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = {**self._default_research_state(quest_root), **payload, "updated_at": utc_now()}
        write_json(self._research_state_path(quest_root), normalized)
        return normalized

    def update_research_state(self, quest_root: Path, **updates: Any) -> dict[str, Any]:
        current = self.read_research_state(quest_root)
        for key, value in updates.items():
            if value is _UNSET:
                continue
            current[key] = str(value) if isinstance(value, Path) else value
        payload = self.write_research_state(quest_root, current)
        self.schedule_projection_refresh(quest_root, kinds=("details", "canvas", "git_canvas"))
        return payload

    def read_lab_canvas_state(self, quest_root: Path) -> dict[str, Any]:
        self._initialize_runtime_files(quest_root)
        defaults = self._default_lab_canvas_state(quest_root)
        payload = self._read_cached_json(self._lab_canvas_state_path(quest_root), defaults)
        if not isinstance(payload, dict):
            payload = defaults
        merged = {**defaults, **payload}
        layout_json = dict(merged.get("layout_json") or {}) if isinstance(merged.get("layout_json"), dict) else {}
        for key in ("branch", "event", "stage", "preferences"):
            if not isinstance(layout_json.get(key), dict):
                layout_json[key] = {}
        merged["layout_json"] = layout_json
        return merged

    def update_lab_canvas_state(
        self,
        quest_root: Path,
        *,
        layout_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.read_lab_canvas_state(quest_root)
        normalized_layout = dict(layout_json or {}) if isinstance(layout_json, dict) else {}
        for key in ("branch", "event", "stage", "preferences"):
            if not isinstance(normalized_layout.get(key), dict):
                normalized_layout[key] = {}
        payload = {
            **current,
            "layout_json": normalized_layout,
            "updated_at": utc_now(),
        }
        write_json(self._lab_canvas_state_path(quest_root), payload)
        return payload

    def workspace_roots(self, quest_root: Path) -> list[Path]:
        roots: list[Path] = [quest_root]
        state = self.read_research_state(quest_root)
        preferred_raw = str(state.get("research_head_worktree_root") or "").strip()
        if preferred_raw:
            preferred = Path(preferred_raw)
            if preferred.exists():
                roots.append(preferred)
        worktrees_root = quest_root / ".ds" / "worktrees"
        if worktrees_root.exists():
            for path in sorted(worktrees_root.iterdir()):
                if path.is_dir():
                    roots.append(path)
        deduped: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = str(root.resolve())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(root)
        return deduped

    def active_workspace_root(self, quest_root: Path) -> Path:
        state = self.read_research_state(quest_root)
        current_raw = str(state.get("current_workspace_root") or "").strip()
        if current_raw:
            current = Path(current_raw)
            if current.exists():
                return current
        preferred_raw = str(state.get("research_head_worktree_root") or "").strip()
        if preferred_raw:
            preferred = Path(preferred_raw)
            if preferred.exists():
                return preferred
        return quest_root

    def _artifact_roots(self, quest_root: Path) -> list[Path]:
        return [root for root in self.workspace_roots(quest_root) if (root / "artifacts").exists()]

    @staticmethod
    def _artifact_item_identity(path: Path, payload: dict[str, Any], *, kind: str) -> str:
        normalized_kind = str(kind or payload.get("kind") or path.parent.name or "artifact").strip() or "artifact"
        artifact_id = str(payload.get("artifact_id") or payload.get("id") or "").strip()
        if artifact_id:
            return f"{normalized_kind}:artifact:{artifact_id}"
        branch_name = str(payload.get("branch") or "").strip()
        run_id = str(payload.get("run_id") or "").strip()
        if normalized_kind == "runs" and run_id and branch_name:
            return f"{normalized_kind}:branch_run:{branch_name}:{run_id}"
        if normalized_kind == "runs" and run_id:
            return f"{normalized_kind}:run:{run_id}"
        idea_id = str(payload.get("idea_id") or "").strip()
        if normalized_kind == "ideas" and idea_id and branch_name:
            return f"{normalized_kind}:branch_idea:{branch_name}:{idea_id}"
        if normalized_kind == "ideas" and idea_id:
            return f"{normalized_kind}:idea:{idea_id}"
        return f"path:{path.resolve()}"

    @staticmethod
    def _artifact_item_rank(payload: dict[str, Any], *, path: Path, mtime_ns: int) -> tuple[str, str, int, int, str]:
        return (
            str(payload.get("updated_at") or ""),
            str(payload.get("created_at") or ""),
            len(payload),
            mtime_ns,
            str(path),
        )

    @staticmethod
    def _artifact_projection_path(quest_root: Path) -> Path:
        return quest_root / ".ds" / "cache" / "artifact_projection.v2.json"

    @staticmethod
    def _artifact_projection_lock_path(quest_root: Path) -> Path:
        return quest_root / ".ds" / "artifact_projection.lock"

    @staticmethod
    def _metrics_timeline_cache_path(quest_root: Path) -> Path:
        return quest_root / ".ds" / "cache" / "metrics_timeline.v1.json"

    @staticmethod
    def _metrics_timeline_cache_lock_path(quest_root: Path) -> Path:
        return quest_root / ".ds" / "cache" / "metrics_timeline.lock"

    @staticmethod
    def _baseline_compare_cache_path(quest_root: Path) -> Path:
        return quest_root / ".ds" / "cache" / "baseline_compare.v1.json"

    @staticmethod
    def _baseline_compare_cache_lock_path(quest_root: Path) -> Path:
        return quest_root / ".ds" / "cache" / "baseline_compare.lock"

    @staticmethod
    def _json_compatible_state(value: Any) -> Any:
        if isinstance(value, tuple):
            return [QuestService._json_compatible_state(item) for item in value]
        if isinstance(value, list):
            return [QuestService._json_compatible_state(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): QuestService._json_compatible_state(item)
                for key, item in value.items()
            }
        return value

    @contextmanager
    def _artifact_projection_lock(self, quest_root: Path):
        lock_key = str(quest_root.resolve())
        with self._artifact_projection_locks_lock:
            thread_lock = self._artifact_projection_locks.setdefault(lock_key, threading.Lock())
        with thread_lock:
            with advisory_file_lock(self._artifact_projection_lock_path(quest_root)):
                yield

    def _artifact_index_collection_state(self, quest_root: Path) -> list[list[Any]]:
        states: list[list[Any]] = []
        for root in self._artifact_roots(quest_root):
            artifacts_root = root / "artifacts"
            if not artifacts_root.exists():
                continue
            try:
                label = str(root.relative_to(quest_root))
            except ValueError:
                label = str(root)
            states.append(
                [
                    label,
                    self._json_compatible_state(self._path_state(artifacts_root / "_index.jsonl")),
                ]
            )
        return states

    def _metrics_timeline_attachment_state(self, quest_root: Path, workspace_root: Path) -> list[list[Any]]:
        states: list[list[Any]] = []
        seen_paths: set[str] = set()
        for root in (workspace_root, quest_root):
            attachment_root = root / "baselines" / "imported"
            if not attachment_root.exists():
                continue
            for path in sorted(attachment_root.glob("*/attachment.yaml")):
                key = str(path.resolve())
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                try:
                    label = str(path.relative_to(quest_root))
                except ValueError:
                    label = str(path)
                states.append([label, self._json_compatible_state(self._path_state(path))])
        return states

    def _metrics_timeline_state(self, quest_root: Path, workspace_root: Path) -> list[Any]:
        return [
            str(workspace_root.resolve()),
            self._artifact_index_collection_state(quest_root),
            self._metrics_timeline_attachment_state(quest_root, workspace_root),
        ]

    def _baseline_compare_state(self, quest_root: Path, workspace_root: Path) -> list[Any]:
        return [
            str(workspace_root.resolve()),
            self._artifact_index_collection_state(quest_root),
            self._metrics_timeline_attachment_state(quest_root, workspace_root),
            self._json_compatible_state(self._path_state(self._quest_yaml_path(quest_root))),
        ]

    def _baseline_compare_entries(self, quest_root: Path, workspace_root: Path) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for item in self._collect_artifacts_raw(quest_root):
            if str(item.get("kind") or "").strip() != "baselines":
                continue
            payload = item.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            status = str(payload.get("status") or "").strip().lower()
            if status not in {"confirmed", "published", "quest_confirmed"}:
                continue
            entries.append(dict(payload))
        attachment = self._active_baseline_attachment(quest_root, workspace_root)
        attachment_entry = dict(attachment.get("entry") or {}) if isinstance(attachment, dict) else None
        if attachment_entry:
            entries.append(attachment_entry)
        return entries

    def _artifact_projection_state(self, quest_root: Path) -> tuple[str, Any]:
        index_state = self._artifact_index_collection_state(quest_root)
        if index_state and all(item[1] is not None for item in index_state):
            return "index", index_state
        if not index_state:
            return "index", []
        return "raw", self._json_compatible_state(self._artifact_collection_state(quest_root))

    def _projection_artifact_item(
        self,
        *,
        record: dict[str, Any],
        artifact_path: Path,
        workspace_root: Path,
    ) -> dict[str, Any]:
        return {
            "kind": artifact_path.parent.name,
            "path": str(artifact_path),
            "payload": copy.deepcopy(record),
            "workspace_root": str(workspace_root),
        }

    def _write_artifact_projection_locked(
        self,
        quest_root: Path,
        *,
        state_kind: str,
        state: Any,
        artifacts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        projection_path = self._artifact_projection_path(quest_root)
        ensure_dir(projection_path.parent)
        payload = {
            "schema_version": 2,
            "generated_at": utc_now(),
            "state_kind": state_kind,
            "state": self._json_compatible_state(state),
            "artifacts": copy.deepcopy(artifacts),
        }
        write_json(projection_path, payload)
        return copy.deepcopy(artifacts)

    def refresh_artifact_projection(
        self,
        quest_root: Path,
        *,
        state_kind: str | None = None,
        state: Any | None = None,
    ) -> list[dict[str, Any]]:
        resolved_state_kind, resolved_state = (
            (state_kind, state)
            if state_kind is not None and state is not None
            else self._artifact_projection_state(quest_root)
        )
        artifacts = self._collect_artifacts_raw(quest_root)
        return self._write_artifact_projection_locked(
            quest_root,
            state_kind=resolved_state_kind,
            state=resolved_state,
            artifacts=artifacts,
        )

    def update_artifact_projection(
        self,
        quest_root: Path,
        *,
        record: dict[str, Any],
        artifact_path: Path,
        workspace_root: Path,
        previous_state_kind: str | None = None,
        previous_state: Any | None = None,
        current_state_kind: str | None = None,
        current_state: Any | None = None,
    ) -> list[dict[str, Any]]:
        resolved_previous_kind = previous_state_kind
        resolved_previous_state = self._json_compatible_state(previous_state) if previous_state is not None else None
        resolved_current_kind, resolved_current_state = (
            (current_state_kind, self._json_compatible_state(current_state))
            if current_state_kind is not None and current_state is not None
            else self._artifact_projection_state(quest_root)
        )
        projection_path = self._artifact_projection_path(quest_root)
        with self._artifact_projection_lock(quest_root):
            payload = read_json(projection_path, {})
            projected_artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else None
            can_incrementally_update = (
                isinstance(payload, dict)
                and int(payload.get("schema_version") or 0) == 2
                and isinstance(projected_artifacts, list)
                and resolved_previous_kind is not None
                and payload.get("state_kind") == resolved_previous_kind
                and self._json_compatible_state(payload.get("state")) == resolved_previous_state
            )
            if not can_incrementally_update:
                return self.refresh_artifact_projection(
                    quest_root,
                    state_kind=resolved_current_kind,
                    state=resolved_current_state,
                )

            artifacts: list[dict[str, Any]] = [
                dict(item)
                for item in projected_artifacts
                if isinstance(item, dict)
            ]
            next_item = self._projection_artifact_item(
                record=record,
                artifact_path=artifact_path,
                workspace_root=workspace_root,
            )
            next_identity = self._artifact_item_identity(
                artifact_path,
                record,
                kind=str(next_item.get("kind") or ""),
            )
            try:
                next_mtime_ns = artifact_path.stat().st_mtime_ns
            except OSError:
                next_mtime_ns = 0
            replaced = False
            for index, existing in enumerate(artifacts):
                existing_payload = existing.get("payload") if isinstance(existing.get("payload"), dict) else {}
                existing_path = Path(str(existing.get("path") or artifact_path))
                if (
                    self._artifact_item_identity(
                        existing_path,
                        existing_payload,
                        kind=str(existing.get("kind") or existing_path.parent.name or ""),
                    )
                    != next_identity
                ):
                    continue
                try:
                    existing_mtime_ns = existing_path.stat().st_mtime_ns
                except OSError:
                    existing_mtime_ns = 0
                if self._artifact_item_rank(
                    record,
                    path=artifact_path,
                    mtime_ns=next_mtime_ns,
                ) >= self._artifact_item_rank(
                    existing_payload,
                    path=existing_path,
                    mtime_ns=existing_mtime_ns,
                ):
                    artifacts[index] = next_item
                replaced = True
                break
            if not replaced:
                artifacts.append(next_item)
            artifacts.sort(
                key=lambda item: str(
                    ((item.get("payload") or {}).get("updated_at"))
                    or ((item.get("payload") or {}).get("created_at"))
                    or item.get("path")
                    or ""
                )
            )
            return self._write_artifact_projection_locked(
                quest_root,
                state_kind=resolved_current_kind,
                state=resolved_current_state,
                artifacts=artifacts,
            )

    def _collect_artifacts_raw(self, quest_root: Path) -> list[dict[str, Any]]:
        artifacts_by_identity: dict[str, dict[str, Any]] = {}
        for root in self._artifact_roots(quest_root):
            artifacts_root = root / "artifacts"
            if not artifacts_root.exists():
                continue
            for folder in sorted(artifacts_root.iterdir()):
                if not folder.is_dir() or folder.name == "graphs":
                    continue
                for path in sorted(folder.glob("*.json")):
                    item = self._read_cached_json(path, {})
                    payload = item if isinstance(item, dict) else {}
                    try:
                        mtime_ns = path.stat().st_mtime_ns
                    except OSError:
                        mtime_ns = 0
                    artifact = {
                        "kind": folder.name,
                        "path": str(path),
                        "payload": item,
                        "workspace_root": str(root),
                    }
                    identity = self._artifact_item_identity(path, payload, kind=folder.name)
                    existing = artifacts_by_identity.get(identity)
                    existing_payload = existing.get("payload") if isinstance((existing or {}).get("payload"), dict) else {}
                    existing_path = Path(str((existing or {}).get("path") or path))
                    try:
                        existing_mtime_ns = existing_path.stat().st_mtime_ns if existing else 0
                    except OSError:
                        existing_mtime_ns = 0
                    if existing is None or self._artifact_item_rank(
                        payload,
                        path=path,
                        mtime_ns=mtime_ns,
                    ) >= self._artifact_item_rank(
                        existing_payload,
                        path=existing_path,
                        mtime_ns=existing_mtime_ns,
                    ):
                        artifacts_by_identity[identity] = artifact
        artifacts = list(artifacts_by_identity.values())
        artifacts.sort(
            key=lambda item: str(
                ((item.get("payload") or {}).get("updated_at"))
                or ((item.get("payload") or {}).get("created_at"))
                or item.get("path")
                or ""
            )
        )
        return artifacts

    def _collect_artifacts(self, quest_root: Path) -> list[dict[str, Any]]:
        state_kind, state = self._artifact_projection_state(quest_root)
        projection_path = self._artifact_projection_path(quest_root)
        cached_projection = self._read_cached_json(projection_path, {})
        if (
            isinstance(cached_projection, dict)
            and int(cached_projection.get("schema_version") or 0) == 2
            and cached_projection.get("state_kind") == state_kind
            and self._json_compatible_state(cached_projection.get("state")) == self._json_compatible_state(state)
            and isinstance(cached_projection.get("artifacts"), list)
        ):
            return [
                dict(item)
                for item in cached_projection.get("artifacts") or []
                if isinstance(item, dict)
            ]

        with self._artifact_projection_lock(quest_root):
            cached_projection = self._read_cached_json(projection_path, {})
            if (
                isinstance(cached_projection, dict)
                and int(cached_projection.get("schema_version") or 0) == 2
                and cached_projection.get("state_kind") == state_kind
                and self._json_compatible_state(cached_projection.get("state")) == self._json_compatible_state(state)
                and isinstance(cached_projection.get("artifacts"), list)
            ):
                return [
                    dict(item)
                    for item in cached_projection.get("artifacts") or []
                    if isinstance(item, dict)
                ]
            return self.refresh_artifact_projection(
                quest_root,
                state_kind=state_kind,
                state=state,
            )

    def _collect_run_artifacts_raw(
        self,
        quest_root: Path,
        *,
        run_kind: str | None = None,
    ) -> list[dict[str, Any]]:
        artifacts_by_identity: dict[str, dict[str, Any]] = {}
        normalized_run_kind = str(run_kind or "").strip()
        for root in self._artifact_roots(quest_root):
            runs_root = root / "artifacts" / "runs"
            if not runs_root.exists():
                continue
            for path in sorted(runs_root.glob("*.json")):
                item = self._read_cached_json(path, {})
                payload = item if isinstance(item, dict) else {}
                if normalized_run_kind and str(payload.get("run_kind") or "").strip() != normalized_run_kind:
                    continue
                try:
                    mtime_ns = path.stat().st_mtime_ns
                except OSError:
                    mtime_ns = 0
                artifact = {
                    "kind": "run",
                    "path": str(path),
                    "payload": item,
                    "workspace_root": str(root),
                }
                identity = self._artifact_item_identity(path, payload, kind="run")
                existing = artifacts_by_identity.get(identity)
                existing_payload = existing.get("payload") if isinstance((existing or {}).get("payload"), dict) else {}
                existing_path = Path(str((existing or {}).get("path") or path))
                try:
                    existing_mtime_ns = existing_path.stat().st_mtime_ns if existing else 0
                except OSError:
                    existing_mtime_ns = 0
                if existing is None or self._artifact_item_rank(
                    payload,
                    path=path,
                    mtime_ns=mtime_ns,
                ) >= self._artifact_item_rank(
                    existing_payload,
                    path=existing_path,
                    mtime_ns=existing_mtime_ns,
                ):
                    artifacts_by_identity[identity] = artifact
        artifacts = list(artifacts_by_identity.values())
        artifacts.sort(
            key=lambda item: str(
                ((item.get("payload") or {}).get("updated_at"))
                or ((item.get("payload") or {}).get("created_at"))
                or item.get("path")
                or ""
            )
        )
        return artifacts

    @staticmethod
    def _projection_id(kind: str) -> str:
        return f"{kind}.v1"

    @staticmethod
    def _projection_directory(quest_root: Path) -> Path:
        return quest_root / ".ds" / "projections"

    @classmethod
    def _projection_manifest_path(cls, quest_root: Path) -> Path:
        return cls._projection_directory(quest_root) / "manifest.json"

    @classmethod
    def _projection_payload_path(cls, quest_root: Path, kind: str) -> Path:
        return cls._projection_directory(quest_root) / f"{cls._projection_id(kind)}.json"

    @classmethod
    def _projection_lock_path(cls, quest_root: Path, kind: str) -> Path:
        return cls._projection_directory(quest_root) / f"{cls._projection_id(kind)}.lock"

    def _projection_build_key(self, quest_root: Path, kind: str) -> str:
        return f"{quest_root.resolve()}::{kind}"

    def _codex_history_events_state(self, quest_root: Path) -> tuple[tuple[str, tuple[int, int, int] | None], ...]:
        return self._glob_states(quest_root / ".ds" / "codex_history", "*/events.jsonl")

    def _details_projection_state(self, quest_root: Path) -> tuple[Any, ...]:
        workspace_root = self.active_workspace_root(quest_root)
        core_paths = [
            self._quest_yaml_path(quest_root),
            quest_root / "status.md",
            quest_root / ".ds" / "runtime_state.json",
            quest_root / ".ds" / "research_state.json",
            quest_root / ".ds" / "interaction_state.json",
            quest_root / ".ds" / "bindings.json",
            quest_root / ".ds" / "bash_exec" / "summary.json",
            self._artifact_projection_path(quest_root),
            workspace_root / "brief.md",
            workspace_root / "plan.md",
            workspace_root / "status.md",
            workspace_root / "SUMMARY.md",
        ]
        return (
            str(workspace_root.resolve()),
            self._path_states(core_paths),
            self._codex_meta_state(quest_root),
            self._codex_history_events_state(quest_root),
        )

    def _git_branch_projection_state(self, quest_root: Path) -> dict[str, Any]:
        result = run_command(
            [
                "git",
                "for-each-ref",
                "--sort=refname",
                "--format=%(refname:short)%09%(objectname)%09%(committerdate:iso-strict)",
                "refs/heads",
            ],
            cwd=quest_root,
            check=False,
        )
        refs = [line.strip() for line in str(result.stdout or "").splitlines() if line.strip()]
        if result.returncode != 0:
            refs = [f"error:{result.returncode}:{str(result.stderr or '').strip()}"]
        return {
            "current_ref": current_branch(quest_root),
            "head": head_commit(quest_root),
            "refs": refs,
        }

    def _canvas_projection_state(self, quest_root: Path) -> tuple[Any, ...]:
        return (
            self._path_states(
                [
                    self._quest_yaml_path(quest_root),
                    quest_root / ".ds" / "research_state.json",
                    self._artifact_projection_path(quest_root),
                ]
            ),
            self._git_branch_projection_state(quest_root),
        )

    def _projection_state_for_kind(self, quest_root: Path, kind: str) -> Any:
        if kind == "details":
            return self._details_projection_state(quest_root)
        if kind == "canvas":
            return self._canvas_projection_state(quest_root)
        if kind == "git_canvas":
            return self._canvas_projection_state(quest_root)
        raise ValueError(f"Unsupported projection kind `{kind}`.")

    def _projection_source_signature(self, quest_root: Path, kind: str) -> str:
        state = {
            "projection_id": self._projection_id(kind),
            "state": self._json_compatible_state(self._projection_state_for_kind(quest_root, kind)),
        }
        return sha256_text(json.dumps(state, ensure_ascii=False, sort_keys=True))

    def _default_projection_status(self, kind: str) -> dict[str, Any]:
        return {
            "projection_id": self._projection_id(kind),
            "state": "missing",
            "progress_current": 0,
            "progress_total": 0,
            "current_step": None,
            "source_signature": None,
            "generated_at": None,
            "last_success_at": None,
            "error": None,
        }

    def _normalize_projection_status(self, kind: str, raw: Any) -> dict[str, Any]:
        normalized = self._default_projection_status(kind)
        if isinstance(raw, dict):
            normalized.update(
                {
                    "state": str(raw.get("state") or normalized["state"]).strip() or normalized["state"],
                    "progress_current": max(0, int(raw.get("progress_current") or 0)),
                    "progress_total": max(0, int(raw.get("progress_total") or 0)),
                    "current_step": str(raw.get("current_step") or "").strip() or None,
                    "source_signature": str(raw.get("source_signature") or "").strip() or None,
                    "generated_at": str(raw.get("generated_at") or "").strip() or None,
                    "last_success_at": str(raw.get("last_success_at") or "").strip() or None,
                    "error": str(raw.get("error") or "").strip() or None,
                }
            )
        return normalized

    def _read_projection_manifest(self, quest_root: Path) -> dict[str, Any]:
        manifest = self._read_cached_json(
            self._projection_manifest_path(quest_root),
            {
                "schema_version": _PROJECTION_SCHEMA_VERSION,
                "projections": {},
            },
        )
        if not isinstance(manifest, dict):
            return {
                "schema_version": _PROJECTION_SCHEMA_VERSION,
                "projections": {},
            }
        return manifest

    def _read_projection_payload_file(self, quest_root: Path, kind: str) -> dict[str, Any] | None:
        payload = self._read_cached_json(self._projection_payload_path(quest_root, kind), {})
        if not isinstance(payload, dict):
            return None
        if str(payload.get("projection_id") or "").strip() != self._projection_id(kind):
            return None
        if not isinstance(payload.get("payload"), dict):
            return None
        return payload

    def _write_projection_manifest_locked(
        self,
        quest_root: Path,
        kind: str,
        status: dict[str, Any],
    ) -> dict[str, Any]:
        path = self._projection_manifest_path(quest_root)
        ensure_dir(path.parent)
        manifest = read_json(path, {})
        if not isinstance(manifest, dict):
            manifest = {}
        projections = manifest.get("projections") if isinstance(manifest.get("projections"), dict) else {}
        next_status = self._normalize_projection_status(kind, status)
        projections = {
            **projections,
            kind: next_status,
        }
        write_json(
            path,
            {
                "schema_version": _PROJECTION_SCHEMA_VERSION,
                "updated_at": utc_now(),
                "projections": projections,
            },
        )
        return next_status

    def _write_projection_payload_locked(
        self,
        quest_root: Path,
        kind: str,
        *,
        source_signature: str,
        payload: dict[str, Any],
        generated_at: str | None = None,
    ) -> dict[str, Any]:
        path = self._projection_payload_path(quest_root, kind)
        ensure_dir(path.parent)
        resolved_generated_at = generated_at or utc_now()
        wrapper = {
            "schema_version": _PROJECTION_SCHEMA_VERSION,
            "projection_id": self._projection_id(kind),
            "generated_at": resolved_generated_at,
            "source_signature": source_signature,
            "payload": copy.deepcopy(payload),
        }
        write_json(path, wrapper)
        return copy.deepcopy(payload)

    @contextmanager
    def _projection_lock(self, quest_root: Path, kind: str):
        lock_key = self._projection_build_key(quest_root, kind)
        with self._quest_projection_locks_lock:
            thread_lock = self._quest_projection_locks.setdefault(lock_key, threading.Lock())
        with thread_lock:
            with advisory_file_lock(self._projection_lock_path(quest_root, kind)):
                yield

    def _projection_build_active(self, quest_root: Path, kind: str) -> bool:
        build_key = self._projection_build_key(quest_root, kind)
        with self._quest_projection_builds_lock:
            thread = self._quest_projection_builds.get(build_key)
            if thread is not None and not thread.is_alive():
                self._quest_projection_builds.pop(build_key, None)
                thread = None
            return thread is not None

    def _present_projection_status(
        self,
        quest_root: Path,
        kind: str,
        *,
        source_signature: str,
        payload_wrapper: dict[str, Any] | None,
    ) -> dict[str, Any]:
        manifest = self._read_projection_manifest(quest_root)
        projections = manifest.get("projections") if isinstance(manifest.get("projections"), dict) else {}
        status = self._normalize_projection_status(kind, projections.get(kind))
        payload_signature = (
            str(payload_wrapper.get("source_signature") or "").strip()
            if isinstance(payload_wrapper, dict)
            else None
        ) or None
        payload_generated_at = (
            str(payload_wrapper.get("generated_at") or "").strip()
            if isinstance(payload_wrapper, dict)
            else None
        ) or None
        payload_ready = (
            isinstance(payload_wrapper, dict)
            and isinstance(payload_wrapper.get("payload"), dict)
            and payload_signature == source_signature
        )
        if payload_ready:
            status.update(
                {
                    "state": "ready",
                    "source_signature": source_signature,
                    "generated_at": payload_generated_at,
                    "last_success_at": payload_generated_at or status.get("last_success_at"),
                    "progress_current": _PROJECTION_BUILD_TOTAL_STEPS,
                    "progress_total": _PROJECTION_BUILD_TOTAL_STEPS,
                    "current_step": None,
                    "error": None,
                }
            )
            return status
        if self._projection_build_active(quest_root, kind):
            status["state"] = "building" if status.get("state") != "queued" else "queued"
            status["progress_total"] = max(int(status.get("progress_total") or 0), _PROJECTION_BUILD_TOTAL_STEPS)
            status["current_step"] = status.get("current_step") or "Building projection"
            return status
        if isinstance(payload_wrapper, dict) and isinstance(payload_wrapper.get("payload"), dict):
            status.update(
                {
                    "state": "stale",
                    "generated_at": payload_generated_at,
                    "last_success_at": payload_generated_at or status.get("last_success_at"),
                    "progress_current": 0,
                    "progress_total": _PROJECTION_BUILD_TOTAL_STEPS,
                    "current_step": "Queued for refresh",
                }
            )
            return status
        if status.get("state") == "failed":
            status["progress_total"] = max(int(status.get("progress_total") or 0), _PROJECTION_BUILD_TOTAL_STEPS)
            return status
        return self._default_projection_status(kind)

    def _queue_projection_build(self, quest_root: Path, kind: str, *, source_signature: str) -> None:
        if self._projection_build_active(quest_root, kind):
            return

        with self._projection_lock(quest_root, kind):
            payload_wrapper = self._read_projection_payload_file(quest_root, kind)
            if (
                isinstance(payload_wrapper, dict)
                and str(payload_wrapper.get("source_signature") or "").strip() == source_signature
                and isinstance(payload_wrapper.get("payload"), dict)
            ):
                ready_status = self._default_projection_status(kind)
                ready_status.update(
                    {
                        "state": "ready",
                        "source_signature": source_signature,
                        "generated_at": str(payload_wrapper.get("generated_at") or "").strip() or None,
                        "last_success_at": str(payload_wrapper.get("generated_at") or "").strip() or None,
                        "progress_current": _PROJECTION_BUILD_TOTAL_STEPS,
                        "progress_total": _PROJECTION_BUILD_TOTAL_STEPS,
                    }
                )
                self._write_projection_manifest_locked(quest_root, kind, ready_status)
                return
            queued_status = self._default_projection_status(kind)
            queued_status.update(
                {
                    "state": "queued",
                    "source_signature": source_signature,
                    "progress_current": 0,
                    "progress_total": _PROJECTION_BUILD_TOTAL_STEPS,
                    "current_step": "Queued for background rebuild",
                    "error": None,
                }
            )
            self._write_projection_manifest_locked(quest_root, kind, queued_status)

        build_key = self._projection_build_key(quest_root, kind)

        def _update_progress(current: int, step: str | None) -> None:
            with self._projection_lock(quest_root, kind):
                manifest = self._read_projection_manifest(quest_root)
                projections = manifest.get("projections") if isinstance(manifest.get("projections"), dict) else {}
                status = self._normalize_projection_status(kind, projections.get(kind))
                status.update(
                    {
                        "state": "building",
                        "source_signature": source_signature,
                        "progress_current": max(0, min(current, _PROJECTION_BUILD_TOTAL_STEPS)),
                        "progress_total": _PROJECTION_BUILD_TOTAL_STEPS,
                        "current_step": step,
                        "error": None,
                    }
                )
                self._write_projection_manifest_locked(quest_root, kind, status)

        def _worker() -> None:
            try:
                _update_progress(0, "Preparing projection inputs")
                payload = self._build_projection_payload(
                    quest_root,
                    kind,
                    source_signature=source_signature,
                    update_progress=_update_progress,
                )
                _update_progress(_PROJECTION_BUILD_TOTAL_STEPS, "Writing projection")
                generated_at = utc_now()
                with self._projection_lock(quest_root, kind):
                    self._write_projection_payload_locked(
                        quest_root,
                        kind,
                        source_signature=source_signature,
                        payload=payload,
                        generated_at=generated_at,
                    )
                    ready_status = self._default_projection_status(kind)
                    ready_status.update(
                        {
                            "state": "ready",
                            "source_signature": source_signature,
                            "generated_at": generated_at,
                            "last_success_at": generated_at,
                            "progress_current": _PROJECTION_BUILD_TOTAL_STEPS,
                            "progress_total": _PROJECTION_BUILD_TOTAL_STEPS,
                            "current_step": None,
                            "error": None,
                        }
                    )
                    self._write_projection_manifest_locked(quest_root, kind, ready_status)
            except Exception as exc:
                with self._projection_lock(quest_root, kind):
                    failed_status = self._default_projection_status(kind)
                    failed_status.update(
                        {
                            "state": "failed",
                            "source_signature": source_signature,
                            "progress_current": 0,
                            "progress_total": _PROJECTION_BUILD_TOTAL_STEPS,
                            "current_step": None,
                            "error": str(exc),
                        }
                    )
                    self._write_projection_manifest_locked(quest_root, kind, failed_status)
            finally:
                with self._quest_projection_builds_lock:
                    active = self._quest_projection_builds.get(build_key)
                    if active is threading.current_thread():
                        self._quest_projection_builds.pop(build_key, None)

        worker = threading.Thread(
            target=_worker,
            daemon=True,
            name=f"ds-projection-{quest_root.name}-{kind}",
        )
        with self._quest_projection_builds_lock:
            self._quest_projection_builds[build_key] = worker
        worker.start()

    def _recent_codex_runs(self, quest_root: Path, *, limit: int = 5) -> list[dict[str, Any]]:
        history_root = quest_root / ".ds" / "codex_history"
        if not history_root.exists():
            return []
        runs: list[dict[str, Any]] = []
        for meta_path in sorted(history_root.glob("*/meta.json")):
            payload = self._read_cached_json(meta_path, {})
            if not isinstance(payload, dict) or not payload:
                continue
            record = dict(payload)
            record.setdefault("history_root", str(meta_path.parent))
            runs.append(record)
        runs.sort(
            key=lambda item: str(
                item.get("updated_at")
                or item.get("completed_at")
                or item.get("created_at")
                or item.get("run_id")
                or ""
            )
        )
        return runs[-limit:]

    def _build_workflow_payload(
        self,
        quest_id: str,
        quest_root: Path,
        workspace_root: Path,
        *,
        recent_runs: list[dict[str, Any]],
        recent_artifacts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        changed_files: list[dict[str, Any]] = []
        seen_files: set[str] = set()

        def add_file(path: str | None, *, source: str, document_id: str | None = None, writable: bool | None = None) -> None:
            if not path:
                return
            normalized = str(path)
            if normalized in seen_files:
                return
            seen_files.add(normalized)
            resolved_document_id = document_id or self._path_to_document_id(
                normalized,
                quest_root=quest_root,
                workspace_root=workspace_root,
            )
            changed_files.append(
                {
                    "path": normalized,
                    "source": source,
                    "document_id": resolved_document_id,
                    "writable": writable,
                }
            )

        for relative in ("brief.md", "plan.md", "status.md", "SUMMARY.md"):
            add_file(
                str(workspace_root / relative),
                source="document",
                document_id=relative,
                writable=True,
            )

        for run in recent_runs:
            run_id = str(run.get("run_id") or "run")
            entries.append(
                {
                    "id": f"run:{run_id}",
                    "kind": "run",
                    "run_id": run_id,
                    "skill_id": run.get("skill_id"),
                    "title": run_id,
                    "summary": run.get("summary") or "Run completed.",
                    "status": "completed" if run.get("exit_code", 0) == 0 else "failed",
                    "created_at": run.get("completed_at") or run.get("created_at") or run.get("updated_at"),
                    "paths": [item for item in [run.get("history_root"), run.get("run_root"), run.get("output_path")] if item],
                }
            )
            for path in (run.get("history_root"), run.get("run_root"), run.get("output_path")):
                add_file(path, source="run")
            history_root = run.get("history_root")
            if history_root:
                entries.extend(
                    self._parse_codex_history_cached(
                        Path(str(history_root)),
                        quest_id=quest_id,
                        run_id=run_id,
                        skill_id=run.get("skill_id"),
                    )
                )

        for artifact in recent_artifacts:
            payload = artifact.get("payload") if isinstance(artifact.get("payload"), dict) else {}
            artifact_path = artifact.get("path")
            entries.append(
                {
                    "id": f"artifact:{payload.get('artifact_id') or artifact_path}",
                    "kind": "artifact",
                    "title": str(payload.get("artifact_id") or artifact.get("kind") or "artifact"),
                    "summary": payload.get("summary") or payload.get("message") or payload.get("reason") or "Artifact updated.",
                    "status": payload.get("status"),
                    "reason": payload.get("reason"),
                    "created_at": payload.get("updated_at") or payload.get("created_at"),
                    "paths": list((payload.get("paths") or {}).values()) + ([str(artifact_path)] if artifact_path else []),
                }
            )
            add_file(str(artifact_path) if artifact_path else None, source="artifact")
            for path in (payload.get("paths") or {}).values():
                add_file(str(path), source="artifact_path")

        entries.sort(key=lambda item: str(item.get("created_at") or item.get("id") or ""))
        return {
            "quest_id": quest_id,
            "quest_root": str(quest_root.resolve()),
            "entries": entries[-80:],
            "changed_files": changed_files[-30:],
        }

    def _build_details_projection_payload(
        self,
        quest_root: Path,
        *,
        source_signature: str,
        update_progress: Any,
    ) -> dict[str, Any]:
        quest_id = quest_root.name
        workspace_root = self.active_workspace_root(quest_root)
        update_progress(1, "Loading recent workflow sources")
        recent_artifacts = self._collect_artifacts(quest_root)[-8:]
        recent_runs = self._recent_codex_runs(quest_root, limit=5)
        update_progress(2, "Materializing workflow timeline")
        return self._build_workflow_payload(
            quest_id,
            quest_root,
            workspace_root,
            recent_runs=recent_runs,
            recent_artifacts=recent_artifacts,
        )

    def _build_canvas_projection_payload(
        self,
        quest_root: Path,
        *,
        source_signature: str,
        update_progress: Any,
    ) -> dict[str, Any]:
        update_progress(1, "Scanning branch references")
        update_progress(2, "Computing branch canvas")
        return list_branch_canvas(quest_root, quest_id=quest_root.name)

    def _build_git_canvas_projection_payload(
        self,
        quest_root: Path,
        *,
        source_signature: str,
        update_progress: Any,
    ) -> dict[str, Any]:
        update_progress(1, "Scanning commit history")
        update_progress(2, "Computing commit canvas")
        return list_commit_canvas(quest_root, quest_id=quest_root.name)

    def _build_projection_payload(
        self,
        quest_root: Path,
        kind: str,
        *,
        source_signature: str,
        update_progress: Any,
    ) -> dict[str, Any]:
        if kind == "details":
            return self._build_details_projection_payload(
                quest_root,
                source_signature=source_signature,
                update_progress=update_progress,
            )
        if kind == "canvas":
            return self._build_canvas_projection_payload(
                quest_root,
                source_signature=source_signature,
                update_progress=update_progress,
            )
        if kind == "git_canvas":
            return self._build_git_canvas_projection_payload(
                quest_root,
                source_signature=source_signature,
                update_progress=update_progress,
            )
        raise ValueError(f"Unsupported projection kind `{kind}`.")

    def _placeholder_workflow_payload(self, quest_id: str, quest_root: Path) -> dict[str, Any]:
        workspace_root = self.active_workspace_root(quest_root)
        return self._build_workflow_payload(
            quest_id,
            quest_root,
            workspace_root,
            recent_runs=[],
            recent_artifacts=[],
        )

    def _placeholder_canvas_payload(self, quest_id: str, quest_root: Path) -> dict[str, Any]:
        research_state = self.read_research_state(quest_root)
        default_ref = (
            str(research_state.get("research_head_branch") or "").strip()
            or str(research_state.get("current_workspace_branch") or "").strip()
            or current_branch(quest_root)
        )
        return {
            "quest_id": quest_id,
            "default_ref": default_ref,
            "current_ref": default_ref,
            "head": head_commit(quest_root),
            "nodes": [],
            "edges": [],
            "views": {
                "ideas": [],
                "analysis": [],
            },
        }

    def _placeholder_git_canvas_payload(self, quest_id: str, quest_root: Path) -> dict[str, Any]:
        research_state = self.read_research_state(quest_root)
        return {
            "quest_id": quest_id,
            "workspace_mode": str(research_state.get("workspace_mode") or "copilot").strip() or "copilot",
            "head": head_commit(quest_root),
            "current_ref": current_branch(quest_root),
            "nodes": [],
            "edges": [],
        }

    def _projected_payload(self, quest_id: str, kind: str) -> dict[str, Any]:
        quest_root = self._quest_root(quest_id)
        source_signature = self._projection_source_signature(quest_root, kind)
        payload_wrapper = self._read_projection_payload_file(quest_root, kind)
        payload_ready = (
            isinstance(payload_wrapper, dict)
            and str(payload_wrapper.get("source_signature") or "").strip() == source_signature
            and isinstance(payload_wrapper.get("payload"), dict)
        )
        if not payload_ready:
            self._queue_projection_build(quest_root, kind, source_signature=source_signature)
            payload_wrapper = self._read_projection_payload_file(quest_root, kind)
        status = self._present_projection_status(
            quest_root,
            kind,
            source_signature=source_signature,
            payload_wrapper=payload_wrapper,
        )
        payload = (
            copy.deepcopy(payload_wrapper.get("payload"))
            if isinstance(payload_wrapper, dict) and isinstance(payload_wrapper.get("payload"), dict)
            else None
        )
        if payload is None:
            if kind == "details":
                payload = self._placeholder_workflow_payload(quest_id, quest_root)
            elif kind == "git_canvas":
                payload = self._placeholder_git_canvas_payload(quest_id, quest_root)
            else:
                payload = self._placeholder_canvas_payload(quest_id, quest_root)
        payload["projection_status"] = status
        return payload

    def prime_projection(self, quest_id: str, kind: str) -> None:
        quest_root = self._quest_root(quest_id)
        self._queue_projection_build(
            quest_root,
            kind,
            source_signature=self._projection_source_signature(quest_root, kind),
        )

    def schedule_projection_refresh(
        self,
        quest_root: Path,
        *,
        kinds: tuple[str, ...] | list[str] | None = None,
        throttle_seconds: float = _PROJECTION_REFRESH_THROTTLE_SECONDS,
    ) -> None:
        resolved_kinds = [
            str(kind).strip()
            for kind in (kinds or ("details", "canvas", "git_canvas"))
            if str(kind).strip() in {"details", "canvas", "git_canvas"}
        ]
        if not resolved_kinds:
            return
        min_interval = max(0.0, float(throttle_seconds))
        now = time.monotonic()
        for kind in resolved_kinds:
            build_key = self._projection_build_key(quest_root, kind)
            if self._projection_build_active(quest_root, kind):
                continue
            with self._quest_projection_refresh_lock:
                previous = float(self._quest_projection_refresh_at.get(build_key) or 0.0)
                if min_interval > 0 and now - previous < min_interval:
                    continue
                self._quest_projection_refresh_at[build_key] = now
            try:
                self._queue_projection_build(
                    quest_root,
                    kind,
                    source_signature=self._projection_source_signature(quest_root, kind),
                )
            except Exception:
                continue

    def git_branch_canvas(self, quest_id: str) -> dict[str, Any]:
        return self._projected_payload(quest_id, "canvas")

    def git_commit_canvas(self, quest_id: str) -> dict[str, Any]:
        return self._projected_payload(quest_id, "git_canvas")

    def _active_baseline_attachment(self, quest_root: Path, workspace_root: Path) -> dict[str, Any] | None:
        attachments: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for root in (workspace_root, quest_root):
            attachment_root = root / "baselines" / "imported"
            if not attachment_root.exists():
                continue
            for path in sorted(attachment_root.glob("*/attachment.yaml")):
                key = str(path.resolve())
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                payload = self._read_cached_yaml(path, {})
                baseline_id = str(payload.get("source_baseline_id") or "").strip() if isinstance(payload, dict) else ""
                if baseline_id and self.baseline_registry.is_deleted(baseline_id):
                    continue
                if isinstance(payload, dict) and payload:
                    attachments.append(payload)
        if not attachments:
            return None
        return max(
            attachments,
            key=lambda item: (
                str(item.get("attached_at") or ""),
                str(item.get("source_baseline_id") or ""),
            ),
        )

    @staticmethod
    def _markdown_excerpt(path: Path, *, max_lines: int = 8) -> str | None:
        if not path.exists() or not path.is_file():
            return None
        text = read_text(path, "")
        if not text.strip():
            return None
        lines = [line.rstrip() for line in text.splitlines() if line.strip()]
        if not lines:
            return None
        excerpt = "\n".join(lines[:max_lines]).strip()
        return excerpt or None

    def _snapshot_workspace_candidates(self, quest_root: Path, workspace_root: Path) -> list[Path]:
        candidates: list[Path] = []
        seen: set[str] = set()

        def add(path: Path | None) -> None:
            if path is None:
                return
            resolved = path.resolve()
            key = str(resolved)
            if key in seen or not resolved.exists():
                return
            seen.add(key)
            candidates.append(resolved)

        add(workspace_root)
        add(quest_root)
        worktrees_root = quest_root / ".ds" / "worktrees"
        if worktrees_root.exists():
            for item in sorted(worktrees_root.iterdir()):
                if item.is_dir():
                    add(item)
        return candidates

    @staticmethod
    def _path_mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def _best_paper_root(self, quest_root: Path, workspace_root: Path) -> Path | None:
        best_root: Path | None = None
        best_rank: tuple[int, float] = (-1, -1.0)
        for candidate in self._snapshot_workspace_candidates(quest_root, workspace_root):
            paper_root = candidate / "paper"
            if not paper_root.exists() or not paper_root.is_dir():
                continue
            selected_outline = paper_root / "selected_outline.json"
            bundle_manifest = paper_root / "paper_bundle_manifest.json"
            draft = paper_root / "draft.md"
            score = 0
            if selected_outline.exists():
                score += 4
            if bundle_manifest.exists():
                score += 5
            if draft.exists():
                score += 2
            latest = max(
                self._path_mtime(selected_outline),
                self._path_mtime(bundle_manifest),
                self._path_mtime(draft),
                self._path_mtime(paper_root),
            )
            rank = (score, latest)
            if rank > best_rank:
                best_rank = rank
                best_root = paper_root
        return best_root

    @staticmethod
    def _paper_line_state_from_root(paper_root: Path) -> dict[str, Any]:
        path = paper_root / "paper_line_state.json"
        payload = read_json(path, {})
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _filter_paper_evidence_items(
        items: list[dict[str, Any]],
        *,
        selected_outline_ref: str | None = None,
        paper_line_id: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized_outline = str(selected_outline_ref or "").strip() or None
        normalized_line = str(paper_line_id or "").strip() or None
        filtered: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            item_outline = str(item.get("selected_outline_ref") or "").strip() or None
            item_line = str(item.get("paper_line_id") or "").strip() or None
            if normalized_line:
                if item_line and item_line != normalized_line:
                    continue
                if not item_line and normalized_outline and item_outline and item_outline != normalized_outline:
                    continue
            elif normalized_outline and item_outline and item_outline != normalized_outline:
                continue
            filtered.append(dict(item))
        return filtered

    def _outline_record_from_paper_root(self, paper_root: Path) -> dict[str, Any]:
        outline_root = paper_root / "outline"
        manifest_path = outline_root / "manifest.json"
        if manifest_path.exists():
            manifest = read_json(manifest_path, {})
            if isinstance(manifest, dict) and manifest:
                manifest_sections = [
                    dict(item) for item in (manifest.get("sections") or []) if isinstance(item, dict)
                ]
                by_id = {
                    str(item.get("section_id") or "").strip(): dict(item)
                    for item in manifest_sections
                    if str(item.get("section_id") or "").strip()
                }
                section_order = [
                    str(item).strip() for item in (manifest.get("section_order") or []) if str(item).strip()
                ]
                sections_root = outline_root / "sections"
                if sections_root.exists():
                    for section_dir in sorted(sections_root.iterdir()):
                        if not section_dir.is_dir():
                            continue
                        section_id = section_dir.name
                        section = dict(by_id.get(section_id) or {})
                        section.setdefault("section_id", section_id)
                        section.setdefault("title", section_id)
                        result_table_payload = read_json(section_dir / "result_table.json", {})
                        rows = result_table_payload.get("rows") if isinstance(result_table_payload, dict) else []
                        section["result_table"] = rows if isinstance(rows, list) else []
                        by_id[section_id] = section
                ordered_sections: list[dict[str, Any]] = []
                emitted: set[str] = set()
                for section_id in section_order:
                    section = by_id.get(section_id)
                    if section is None:
                        continue
                    ordered_sections.append(section)
                    emitted.add(section_id)
                for section_id, section in by_id.items():
                    if section_id in emitted:
                        continue
                    ordered_sections.append(section)
                return {
                    "schema_version": 1,
                    "outline_id": manifest.get("outline_id"),
                    "status": manifest.get("status"),
                    "title": manifest.get("title"),
                    "note": manifest.get("note"),
                    "story": manifest.get("story"),
                    "ten_questions": manifest.get("ten_questions") if isinstance(manifest.get("ten_questions"), list) else [],
                    "detailed_outline": manifest.get("detailed_outline") if isinstance(manifest.get("detailed_outline"), dict) else {},
                    "sections": ordered_sections,
                    "evidence_contract": manifest.get("evidence_contract") if isinstance(manifest.get("evidence_contract"), dict) else None,
                    "created_at": manifest.get("created_at"),
                    "updated_at": manifest.get("updated_at"),
                }
        selected_outline_path = paper_root / "selected_outline.json"
        payload = read_json(selected_outline_path, {})
        return payload if isinstance(payload, dict) else {}

    def _paper_evidence_payload(self, quest_root: Path, workspace_root: Path) -> dict[str, Any] | None:
        paper_root = self._best_paper_root(quest_root, workspace_root)
        if paper_root is None:
            return None
        ledger_json_path = paper_root / "evidence_ledger.json"
        if not ledger_json_path.exists():
            return None
        payload = read_json(ledger_json_path, {})
        if not isinstance(payload, dict) or not payload:
            return None
        selected_outline_ref = str(payload.get("selected_outline_ref") or "").strip() or None
        line_state = self._paper_line_state_from_root(paper_root)
        paper_line_id = str(line_state.get("paper_line_id") or "").strip() or None
        items = self._filter_paper_evidence_items(
            [dict(item) for item in (payload.get("items") or []) if isinstance(item, dict)],
            selected_outline_ref=selected_outline_ref,
            paper_line_id=paper_line_id,
        )
        return {
            "paper_root": str(paper_root),
            "workspace_root": str(paper_root.parent),
            "selected_outline_ref": selected_outline_ref,
            "paper_line_id": paper_line_id,
            "item_count": len(items),
            "main_text_ready_count": sum(
                1
                for item in items
                if str(item.get("paper_role") or "").strip() == "main_text"
                and str(item.get("status") or "").strip().lower() in {"ready", "completed", "analyzed", "written", "recorded", "supported"}
            ),
            "appendix_item_count": sum(
                1 for item in items if str(item.get("paper_role") or "").strip() == "appendix"
            ),
            "unmapped_item_count": sum(
                1
                for item in items
                if not str(item.get("section_id") or "").strip() or not str(item.get("paper_role") or "").strip()
            ),
            "items": items[:40],
            "paths": {
                "ledger_json": str(ledger_json_path),
                "ledger_md": str(paper_root / "evidence_ledger.md") if (paper_root / "evidence_ledger.md").exists() else None,
            },
        }

    def _paper_contract_payload(self, quest_root: Path, workspace_root: Path) -> dict[str, Any] | None:
        paper_root = self._best_paper_root(quest_root, workspace_root)
        if paper_root is None:
            return None
        selected_outline_path = paper_root / "selected_outline.json"
        selected_outline = self._outline_record_from_paper_root(paper_root)
        selected_outline = selected_outline if isinstance(selected_outline, dict) else {}
        detailed_outline = (
            dict(selected_outline.get("detailed_outline") or {})
            if isinstance(selected_outline.get("detailed_outline"), dict)
            else {}
        )
        outline_manifest_path = paper_root / "outline" / "manifest.json"
        bundle_manifest_path = paper_root / "paper_bundle_manifest.json"
        bundle_manifest = read_json(bundle_manifest_path, {})
        bundle_manifest = bundle_manifest if isinstance(bundle_manifest, dict) else {}
        experiment_matrix_path = paper_root / "paper_experiment_matrix.md"
        experiment_matrix_json_path = paper_root / "paper_experiment_matrix.json"
        manuscript_coverage_path = paper_root / "manuscript_coverage.json"
        claim_map_path = paper_root / "claim_evidence_map.json"
        paper_line_state_path = paper_root / "paper_line_state.json"
        evidence_ledger = self._paper_evidence_payload(quest_root, workspace_root)
        checklist_path = paper_root / "review" / "submission_checklist.json"
        draft_path = paper_root / "draft.md"
        status_path = paper_root.parent / "status.md"
        summary_path = paper_root.parent / "SUMMARY.md"

        raw_sections = selected_outline.get("sections") if isinstance(selected_outline.get("sections"), list) else []
        sections = []
        if raw_sections:
            for index, raw in enumerate(raw_sections, start=1):
                if not isinstance(raw, dict):
                    continue
                title = str(raw.get("title") or raw.get("section_id") or "").strip()
                if not title:
                    title = f"Section {index}"
                sections.append(
                    {
                        "section_id": str(raw.get("section_id") or slugify(title, f"section-{index}")).strip() or slugify(title, f"section-{index}"),
                        "title": title,
                        "paper_role": str(raw.get("paper_role") or "").strip() or None,
                        "status": str(raw.get("status") or "").strip() or None,
                        "claims": raw.get("claims") if isinstance(raw.get("claims"), list) else [],
                        "required_items": raw.get("required_items") if isinstance(raw.get("required_items"), list) else [],
                        "optional_items": raw.get("optional_items") if isinstance(raw.get("optional_items"), list) else [],
                        "result_table": raw.get("result_table") if isinstance(raw.get("result_table"), list) else [],
                    }
                )
        else:
            for item in detailed_outline.get("experimental_designs") or []:
                text = str(item or "").strip()
                if not text:
                    continue
                sections.append(
                    {
                        "section_id": slugify(text, "section"),
                        "title": text,
                        "paper_role": "main_text",
                        "status": "recorded",
                        "claims": [],
                        "required_items": [],
                        "optional_items": [],
                        "result_table": [],
                    }
                )

        return {
            "paper_root": str(paper_root),
            "workspace_root": str(paper_root.parent),
            "paper_line_id": str(self._paper_line_state_from_root(paper_root).get("paper_line_id") or "").strip() or None,
            "paper_branch": str(bundle_manifest.get("paper_branch") or "").strip() or current_branch(paper_root.parent),
            "source_branch": str(bundle_manifest.get("source_branch") or "").strip() or None,
            "selected_outline_ref": str(selected_outline.get("outline_id") or bundle_manifest.get("selected_outline_ref") or "").strip() or None,
            "title": str(selected_outline.get("title") or bundle_manifest.get("title") or "").strip() or None,
            "story": str(selected_outline.get("story") or "").strip() or None,
            "paper_view": selected_outline.get("paper_view") if isinstance(selected_outline.get("paper_view"), dict) else None,
            "evidence_view": selected_outline.get("evidence_view") if isinstance(selected_outline.get("evidence_view"), dict) else None,
            "research_questions": detailed_outline.get("research_questions") if isinstance(detailed_outline.get("research_questions"), list) else [],
            "experimental_designs": detailed_outline.get("experimental_designs") if isinstance(detailed_outline.get("experimental_designs"), list) else [],
            "contributions": detailed_outline.get("contributions") if isinstance(detailed_outline.get("contributions"), list) else [],
            "evidence_contract": selected_outline.get("evidence_contract") if isinstance(selected_outline.get("evidence_contract"), dict) else None,
            "sections": sections,
            "evidence_summary": {
                "item_count": int((evidence_ledger or {}).get("item_count") or 0),
                "main_text_ready_count": int((evidence_ledger or {}).get("main_text_ready_count") or 0),
                "appendix_item_count": int((evidence_ledger or {}).get("appendix_item_count") or 0),
                "unmapped_item_count": int((evidence_ledger or {}).get("unmapped_item_count") or 0),
            },
            "summary": str(bundle_manifest.get("summary") or "").strip() or self._markdown_excerpt(summary_path),
            "paths": {
                "selected_outline": str(selected_outline_path) if selected_outline_path.exists() else None,
                "outline_manifest": str(outline_manifest_path) if outline_manifest_path.exists() else None,
                "experiment_matrix": str(experiment_matrix_path) if experiment_matrix_path.exists() else None,
                "experiment_matrix_json": str(experiment_matrix_json_path) if experiment_matrix_json_path.exists() else None,
                "manuscript_coverage": str(manuscript_coverage_path) if manuscript_coverage_path.exists() else None,
                "bundle_manifest": str(bundle_manifest_path) if bundle_manifest_path.exists() else None,
                "claim_evidence_map": str(claim_map_path) if claim_map_path.exists() else None,
                "paper_line_state": str(paper_line_state_path) if paper_line_state_path.exists() else None,
                "evidence_ledger_json": str(((evidence_ledger or {}).get("paths") or {}).get("ledger_json")) if ((evidence_ledger or {}).get("paths") or {}).get("ledger_json") else None,
                "evidence_ledger_md": str(((evidence_ledger or {}).get("paths") or {}).get("ledger_md")) if ((evidence_ledger or {}).get("paths") or {}).get("ledger_md") else None,
                "submission_checklist": str(checklist_path) if checklist_path.exists() else None,
                "draft": str(draft_path) if draft_path.exists() else None,
                "status": str(status_path) if status_path.exists() else None,
                "summary": str(summary_path) if summary_path.exists() else None,
            },
            "bundle_manifest": bundle_manifest or None,
            "outline_payload": selected_outline or None,
        }

    def _paper_lines_payload(self, quest_root: Path, workspace_root: Path) -> tuple[list[dict[str, Any]], str | None]:
        lines_by_id: dict[str, dict[str, Any]] = {}
        active_ref: str | None = None
        for candidate in self._snapshot_workspace_candidates(quest_root, workspace_root):
            paper_root = candidate / "paper"
            if not paper_root.exists() or not paper_root.is_dir():
                continue
            state_path = paper_root / "paper_line_state.json"
            payload = read_json(state_path, {}) if state_path.exists() else {}
            if not isinstance(payload, dict) or not payload:
                contract = self._paper_contract_payload(quest_root, candidate)
                if not contract:
                    continue
                bundle_manifest = (
                    dict(contract.get("bundle_manifest") or {})
                    if isinstance(contract.get("bundle_manifest"), dict)
                    else {}
                )
                payload = {
                    "paper_line_id": slugify(
                        "::".join(
                            [
                                str(contract.get("paper_branch") or "paper").strip() or "paper",
                                str(contract.get("selected_outline_ref") or "outline").strip() or "outline",
                                str(bundle_manifest.get("source_run_id") or "run").strip() or "run",
                            ]
                        ),
                        "paper-line",
                    ),
                    "paper_branch": contract.get("paper_branch"),
                    "paper_root": str(paper_root),
                    "workspace_root": str(candidate),
                    "source_branch": contract.get("source_branch"),
                    "source_run_id": bundle_manifest.get("source_run_id"),
                    "source_idea_id": bundle_manifest.get("source_idea_id"),
                    "selected_outline_ref": contract.get("selected_outline_ref"),
                    "title": contract.get("title"),
                    "required_count": sum(len(item.get("required_items") or []) for item in (contract.get("sections") or [])),
                    "ready_required_count": int((contract.get("evidence_summary") or {}).get("main_text_ready_count") or 0),
                    "section_count": len(contract.get("sections") or []),
                    "ready_section_count": 0,
                    "unmapped_count": int((contract.get("evidence_summary") or {}).get("unmapped_item_count") or 0),
                    "open_supplementary_count": 0,
                    "draft_status": "present" if (paper_root / "draft.md").exists() else "missing",
                    "bundle_status": "present" if (paper_root / "paper_bundle_manifest.json").exists() else "missing",
                    "updated_at": "",
                }
            paper_line_id = str(payload.get("paper_line_id") or "").strip()
            if not paper_line_id:
                continue
            payload["paths"] = {
                "paper_line_state": str(state_path) if state_path.exists() else None,
                "paper_root": str(paper_root),
            }
            current = lines_by_id.get(paper_line_id)
            if current is None or str(payload.get("updated_at") or "") >= str(current.get("updated_at") or ""):
                lines_by_id[paper_line_id] = payload
            if str(candidate) == str(workspace_root):
                active_ref = paper_line_id
        lines = sorted(lines_by_id.values(), key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        if not active_ref and lines:
            active_ref = str(lines[0].get("paper_line_id") or "").strip() or None
        return lines, active_ref

    def _analysis_inventory_payload(self, quest_root: Path, workspace_root: Path) -> dict[str, Any] | None:
        manifest_by_id: dict[str, dict[str, Any]] = {}
        campaigns_root = quest_root / ".ds" / "analysis_campaigns"
        if campaigns_root.exists():
            for path in sorted(campaigns_root.glob("*.json")):
                payload = read_json(path, {})
                if not isinstance(payload, dict) or not payload:
                    continue
                campaign_id = str(payload.get("campaign_id") or path.stem).strip() or path.stem
                manifest_by_id[campaign_id] = payload
        campaigns_by_id: dict[str, dict[str, Any]] = {}
        for candidate in self._snapshot_workspace_candidates(quest_root, workspace_root):
            analysis_root = candidate / "experiments" / "analysis-results"
            if not analysis_root.exists() or not analysis_root.is_dir():
                continue
            for campaign_dir in sorted(analysis_root.iterdir()):
                if not campaign_dir.is_dir():
                    continue
                campaign_id = campaign_dir.name
                todo_manifest_path = campaign_dir / "todo_manifest.json"
                campaign_md_path = campaign_dir / "campaign.md"
                summary_md_path = campaign_dir / "SUMMARY.md"
                todo_manifest = read_json(todo_manifest_path, {})
                todo_manifest = todo_manifest if isinstance(todo_manifest, dict) else {}
                campaign_manifest = dict(manifest_by_id.get(campaign_id) or {})
                todo_items = todo_manifest.get("todo_items") if isinstance(todo_manifest.get("todo_items"), list) else []
                manifest_slices = {
                    str(item.get("slice_id") or "").strip(): dict(item)
                    for item in (campaign_manifest.get("slices") or [])
                    if isinstance(item, dict) and str(item.get("slice_id") or "").strip()
                }
                slice_files = []
                for path in sorted(campaign_dir.glob("*.md")):
                    if path.name in {"campaign.md", "SUMMARY.md"}:
                        continue
                    slice_files.append(path)
                slices: list[dict[str, Any]] = []
                for index, path in enumerate(slice_files):
                    matched_todo = todo_items[index] if index < len(todo_items) and isinstance(todo_items[index], dict) else {}
                    slice_id = str(matched_todo.get("slice_id") or path.stem).strip() or path.stem
                    title = str(matched_todo.get("title") or path.stem).strip() or path.stem
                    manifest_slice = dict(manifest_slices.get(slice_id) or {})
                    slices.append(
                        {
                            "slice_id": slice_id,
                            "title": title,
                            "status": str(manifest_slice.get("status") or matched_todo.get("status") or "completed").strip() or "completed",
                            "tier": str(matched_todo.get("tier") or "").strip() or None,
                            "exp_id": str(matched_todo.get("exp_id") or "").strip() or None,
                            "paper_role": str(matched_todo.get("paper_placement") or matched_todo.get("paper_role") or "").strip() or None,
                            "section_id": str(matched_todo.get("section_id") or "").strip() or None,
                            "item_id": str(matched_todo.get("item_id") or "").strip() or None,
                            "claim_links": matched_todo.get("claim_links") if isinstance(matched_todo.get("claim_links"), list) else [],
                            "research_question": str(matched_todo.get("research_question") or "").strip() or None,
                            "experimental_design": str(matched_todo.get("experimental_design") or "").strip() or None,
                            "branch": str(manifest_slice.get("branch") or "").strip() or None,
                            "worktree_root": str(manifest_slice.get("worktree_root") or "").strip() or None,
                            "mapped": bool(
                                str(matched_todo.get("section_id") or "").strip()
                                and str(matched_todo.get("item_id") or "").strip()
                                and str(matched_todo.get("paper_placement") or matched_todo.get("paper_role") or "").strip()
                            ),
                            "result_path": str(path),
                            "result_excerpt": self._markdown_excerpt(path, max_lines=6),
                        }
                    )
                record = {
                    "campaign_id": campaign_id,
                    "title": str((todo_manifest.get("campaign_origin") or {}).get("reason") or campaign_id).strip() or campaign_id,
                    "active_idea_id": str(campaign_manifest.get("active_idea_id") or "").strip() or None,
                    "parent_run_id": str(campaign_manifest.get("parent_run_id") or "").strip() or None,
                    "parent_branch": str(campaign_manifest.get("parent_branch") or "").strip() or None,
                    "paper_line_id": str(campaign_manifest.get("paper_line_id") or "").strip() or None,
                    "paper_line_branch": str(campaign_manifest.get("paper_line_branch") or "").strip() or None,
                    "paper_line_root": str(campaign_manifest.get("paper_line_root") or "").strip() or None,
                    "selected_outline_ref": str(campaign_manifest.get("selected_outline_ref") or todo_manifest.get("selected_outline_ref") or "").strip() or None,
                    "todo_manifest_path": str(todo_manifest_path) if todo_manifest_path.exists() else None,
                    "campaign_path": str(campaign_md_path) if campaign_md_path.exists() else None,
                    "summary_path": str(summary_md_path) if summary_md_path.exists() else None,
                    "summary_excerpt": self._markdown_excerpt(summary_md_path, max_lines=10),
                    "updated_at": str(campaign_manifest.get("updated_at") or "").strip() or None,
                    "slice_count": len(slices),
                    "completed_slice_count": sum(1 for item in slices if str(item.get("status") or "") == "completed"),
                    "mapped_slice_count": sum(1 for item in slices if bool(item.get("mapped"))),
                    "pending_slice_count": sum(1 for item in slices if str(item.get("status") or "") != "completed"),
                    "slices": slices,
                    "_rank": (
                        len(slices),
                        max(
                            self._path_mtime(summary_md_path),
                            self._path_mtime(campaign_md_path),
                            self._path_mtime(todo_manifest_path),
                            self._path_mtime(campaigns_root / f"{campaign_id}.json"),
                            self._path_mtime(campaign_dir),
                        ),
                    ),
                }
                current = campaigns_by_id.get(campaign_id)
                if current is None or record["_rank"] >= current["_rank"]:
                    campaigns_by_id[campaign_id] = record

        if not campaigns_by_id:
            return None
        campaigns = []
        total_slices = 0
        total_completed = 0
        total_mapped = 0
        for item in sorted(
            campaigns_by_id.values(),
            key=lambda payload: (payload["_rank"][1], payload["campaign_id"]),
            reverse=True,
        ):
            total_slices += int(item.get("slice_count") or 0)
            total_completed += int(item.get("completed_slice_count") or 0)
            total_mapped += int(item.get("mapped_slice_count") or 0)
            campaigns.append({key: value for key, value in item.items() if key != "_rank"})
        return {
            "campaign_count": len(campaigns),
            "slice_count": total_slices,
            "completed_slice_count": total_completed,
            "mapped_slice_count": total_mapped,
            "campaigns": campaigns,
        }

    def _idea_lines_payload(
        self,
        quest_root: Path,
        *,
        paper_lines: list[dict[str, Any]],
        analysis_inventory: dict[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        artifacts = self._collect_artifacts(quest_root)
        research_state = self.read_research_state(quest_root)
        active_idea_id = str(research_state.get("active_idea_id") or "").strip() or None
        active_ref: str | None = None
        lines_by_id: dict[str, dict[str, Any]] = {}

        def ensure_line(idea_id: str) -> dict[str, Any]:
            current = lines_by_id.get(idea_id)
            if current is None:
                current = {
                    "idea_line_id": idea_id,
                    "idea_id": idea_id,
                    "idea_branch": None,
                    "idea_title": None,
                    "lineage_intent": None,
                    "parent_branch": None,
                    "latest_main_run_id": None,
                    "latest_main_run_branch": None,
                    "paper_line_id": None,
                    "paper_branch": None,
                    "selected_outline_ref": None,
                    "analysis_campaign_count": 0,
                    "analysis_slice_count": 0,
                    "completed_analysis_slice_count": 0,
                    "mapped_analysis_slice_count": 0,
                    "required_count": 0,
                    "ready_required_count": 0,
                    "unmapped_count": 0,
                    "open_supplementary_count": 0,
                    "draft_status": None,
                    "bundle_status": None,
                    "updated_at": "",
                    "paths": {
                        "idea_md": None,
                        "idea_draft": None,
                        "paper_line_state": None,
                    },
                }
                lines_by_id[idea_id] = current
            return current

        def updated_rank(value: object) -> str:
            return str(value or "").strip()

        for artifact in artifacts:
            kind = str(artifact.get("kind") or "").strip()
            payload = artifact.get("payload") if isinstance(artifact.get("payload"), dict) else {}
            if not payload:
                continue
            idea_id = str(payload.get("idea_id") or "").strip()
            if not idea_id:
                continue
            entry = ensure_line(idea_id)
            if kind == "ideas":
                current_rank = updated_rank(entry.get("updated_at"))
                candidate_rank = updated_rank(payload.get("updated_at") or payload.get("created_at"))
                if candidate_rank >= current_rank:
                    details = dict(payload.get("details") or {}) if isinstance(payload.get("details"), dict) else {}
                    paths = dict(payload.get("paths") or {}) if isinstance(payload.get("paths"), dict) else {}
                    entry["idea_branch"] = str(payload.get("branch") or "").strip() or entry.get("idea_branch")
                    entry["idea_title"] = str(details.get("title") or payload.get("title") or "").strip() or entry.get("idea_title")
                    entry["lineage_intent"] = str(payload.get("lineage_intent") or details.get("lineage_intent") or "").strip() or entry.get("lineage_intent")
                    entry["parent_branch"] = str(payload.get("parent_branch") or details.get("parent_branch") or "").strip() or entry.get("parent_branch")
                    entry["updated_at"] = candidate_rank or entry.get("updated_at")
                    entry["paths"] = {
                        **dict(entry.get("paths") or {}),
                        "idea_md": str(paths.get("idea_md") or "").strip() or dict(entry.get("paths") or {}).get("idea_md"),
                        "idea_draft": str(paths.get("idea_draft_md") or details.get("idea_draft_path") or "").strip()
                        or dict(entry.get("paths") or {}).get("idea_draft"),
                    }
            elif kind == "runs":
                branch = str(payload.get("branch") or "").strip()
                run_id = str(payload.get("run_id") or "").strip()
                run_kind = str(payload.get("run_kind") or "").strip().lower()
                if not run_id or branch.startswith("analysis/") or branch.startswith("paper/") or run_kind.startswith("analysis"):
                    continue
                current_rank = updated_rank(entry.get("latest_main_run_updated_at"))
                candidate_rank = updated_rank(payload.get("updated_at") or payload.get("created_at"))
                if candidate_rank >= current_rank:
                    entry["latest_main_run_id"] = run_id
                    entry["latest_main_run_branch"] = branch or entry.get("latest_main_run_branch")
                    entry["latest_main_run_updated_at"] = candidate_rank
                    entry["updated_at"] = max(updated_rank(entry.get("updated_at")), candidate_rank)

        for line in paper_lines:
            idea_id = str(line.get("source_idea_id") or "").strip()
            if not idea_id:
                continue
            entry = ensure_line(idea_id)
            current_rank = updated_rank(entry.get("paper_line_updated_at"))
            candidate_rank = updated_rank(line.get("updated_at"))
            if candidate_rank >= current_rank:
                entry["paper_line_id"] = str(line.get("paper_line_id") or "").strip() or entry.get("paper_line_id")
                entry["paper_branch"] = str(line.get("paper_branch") or "").strip() or entry.get("paper_branch")
                entry["selected_outline_ref"] = str(line.get("selected_outline_ref") or "").strip() or entry.get("selected_outline_ref")
                entry["required_count"] = int(line.get("required_count") or 0)
                entry["ready_required_count"] = int(line.get("ready_required_count") or 0)
                entry["unmapped_count"] = int(line.get("unmapped_count") or 0)
                entry["open_supplementary_count"] = int(line.get("open_supplementary_count") or 0)
                entry["draft_status"] = str(line.get("draft_status") or "").strip() or None
                entry["bundle_status"] = str(line.get("bundle_status") or "").strip() or None
                entry["paper_line_updated_at"] = candidate_rank
                entry["updated_at"] = max(updated_rank(entry.get("updated_at")), candidate_rank)
                entry["paths"] = {
                    **dict(entry.get("paths") or {}),
                    "paper_line_state": str(((line.get("paths") or {}) if isinstance(line.get("paths"), dict) else {}).get("paper_line_state") or "").strip()
                    or dict(entry.get("paths") or {}).get("paper_line_state"),
                }

        campaigns = list((analysis_inventory or {}).get("campaigns") or []) if isinstance(analysis_inventory, dict) else []
        for campaign in campaigns:
            if not isinstance(campaign, dict):
                continue
            matched_idea_id = str(campaign.get("active_idea_id") or "").strip()
            if not matched_idea_id:
                matched_run_id = str(campaign.get("parent_run_id") or "").strip()
                matched_branch = str(campaign.get("parent_branch") or "").strip()
                for candidate in lines_by_id.values():
                    if matched_run_id and matched_run_id == str(candidate.get("latest_main_run_id") or "").strip():
                        matched_idea_id = str(candidate.get("idea_id") or "").strip()
                        break
                    if matched_branch and matched_branch in {
                        str(candidate.get("idea_branch") or "").strip(),
                        str(candidate.get("latest_main_run_branch") or "").strip(),
                    }:
                        matched_idea_id = str(candidate.get("idea_id") or "").strip()
                        break
            if not matched_idea_id:
                continue
            entry = ensure_line(matched_idea_id)
            entry["analysis_campaign_count"] = int(entry.get("analysis_campaign_count") or 0) + 1
            entry["analysis_slice_count"] = int(entry.get("analysis_slice_count") or 0) + int(campaign.get("slice_count") or 0)
            entry["completed_analysis_slice_count"] = int(entry.get("completed_analysis_slice_count") or 0) + int(
                campaign.get("completed_slice_count") or 0
            )
            entry["mapped_analysis_slice_count"] = int(entry.get("mapped_analysis_slice_count") or 0) + int(
                campaign.get("mapped_slice_count") or 0
            )
            if not entry.get("paper_line_id") and str(campaign.get("paper_line_id") or "").strip():
                entry["paper_line_id"] = str(campaign.get("paper_line_id") or "").strip()
                entry["paper_branch"] = str(campaign.get("paper_line_branch") or "").strip() or entry.get("paper_branch")
                entry["selected_outline_ref"] = str(campaign.get("selected_outline_ref") or "").strip() or entry.get("selected_outline_ref")
            entry["updated_at"] = max(
                updated_rank(entry.get("updated_at")),
                updated_rank(campaign.get("updated_at")),
            )

        lines = sorted(
            lines_by_id.values(),
            key=lambda item: (
                0 if str(item.get("idea_id") or "").strip() == active_idea_id else 1,
                str(item.get("updated_at") or ""),
                str(item.get("idea_line_id") or ""),
            ),
        )
        for item in lines:
            if not item.get("open_supplementary_count"):
                pending = max(
                    0,
                    int(item.get("analysis_slice_count") or 0) - int(item.get("completed_analysis_slice_count") or 0),
                )
                item["open_supplementary_count"] = pending
            item.pop("latest_main_run_updated_at", None)
            item.pop("paper_line_updated_at", None)
        if active_idea_id and active_idea_id in lines_by_id:
            active_ref = active_idea_id
        elif lines:
            active_ref = str(lines[0].get("idea_line_id") or "").strip() or None
        return lines, active_ref

    def _paper_contract_health_payload(
        self,
        *,
        paper_contract: dict[str, Any] | None,
        paper_evidence: dict[str, Any] | None,
        analysis_inventory: dict[str, Any] | None,
        paper_lines: list[dict[str, Any]],
        active_paper_line_ref: str | None,
    ) -> dict[str, Any] | None:
        if not isinstance(paper_contract, dict) or not paper_contract:
            return None
        evidence_items = [
            dict(item) for item in ((paper_evidence or {}).get("items") or []) if isinstance(item, dict)
        ]
        ledger_by_item: dict[str, list[dict[str, Any]]] = {}
        for item in evidence_items:
            item_id = str(item.get("item_id") or "").strip()
            if item_id:
                ledger_by_item.setdefault(item_id, []).append(item)

        def ready_ledger_item(item_id: str) -> dict[str, Any] | None:
            candidates = ledger_by_item.get(item_id) or []
            ready_statuses = {"ready", "completed", "analyzed", "written", "recorded", "supported"}
            ready = [
                item
                for item in candidates
                if str(item.get("status") or "").strip().lower() in ready_statuses
            ]
            if ready:
                main = [item for item in ready if str(item.get("paper_role") or "").strip() == "main_text"]
                return main[0] if main else ready[0]
            return candidates[0] if candidates else None

        unresolved_required_items: list[dict[str, Any]] = []
        ready_section_count = 0
        for section in paper_contract.get("sections") or []:
            if not isinstance(section, dict):
                continue
            required_items = [str(item).strip() for item in (section.get("required_items") or []) if str(item).strip()]
            section_ready = True
            for item_id in required_items:
                ledger_item = ready_ledger_item(item_id)
                status = str((ledger_item or {}).get("status") or "").strip().lower()
                if status not in {"ready", "completed", "analyzed", "written", "recorded", "supported"}:
                    unresolved_required_items.append(
                        {
                            "section_id": str(section.get("section_id") or "").strip() or None,
                            "section_title": str(section.get("title") or "").strip() or None,
                            "item_id": item_id,
                            "status": str((ledger_item or {}).get("status") or "").strip() or None,
                        }
                    )
                    section_ready = False
            if required_items and section_ready:
                ready_section_count += 1

        selected_outline_ref = str(paper_contract.get("selected_outline_ref") or "").strip() or None
        active_line = next(
            (
                dict(item)
                for item in paper_lines
                if isinstance(item, dict)
                and str(item.get("paper_line_id") or "").strip()
                and str(item.get("paper_line_id") or "").strip() == str(active_paper_line_ref or "").strip()
            ),
            dict(paper_lines[0]) if paper_lines else {},
        )
        active_line_id = str(active_line.get("paper_line_id") or "").strip() or None
        active_line_branch = str(active_line.get("paper_branch") or "").strip() or None

        campaigns = [dict(item) for item in ((analysis_inventory or {}).get("campaigns") or []) if isinstance(item, dict)]
        relevant_campaigns: list[dict[str, Any]] = []
        for campaign in campaigns:
            campaign_outline = str(campaign.get("selected_outline_ref") or "").strip() or None
            campaign_line_id = str(campaign.get("paper_line_id") or "").strip() or None
            campaign_line_branch = str(campaign.get("paper_line_branch") or "").strip() or None
            if active_line_id and campaign_line_id == active_line_id:
                relevant_campaigns.append(campaign)
                continue
            if active_line_branch and campaign_line_branch == active_line_branch:
                relevant_campaigns.append(campaign)
                continue
            if selected_outline_ref and campaign_outline == selected_outline_ref:
                relevant_campaigns.append(campaign)

        unmapped_completed_items: list[dict[str, Any]] = []
        blocking_pending_slices: list[dict[str, Any]] = []
        for campaign in relevant_campaigns:
            for slice_item in campaign.get("slices") or []:
                if not isinstance(slice_item, dict):
                    continue
                status = str(slice_item.get("status") or "").strip().lower()
                if status == "completed" and not bool(slice_item.get("mapped")):
                    unmapped_completed_items.append(
                        {
                            "campaign_id": str(campaign.get("campaign_id") or "").strip() or None,
                            "slice_id": str(slice_item.get("slice_id") or "").strip() or None,
                            "item_id": str(slice_item.get("item_id") or "").strip() or None,
                            "section_id": str(slice_item.get("section_id") or "").strip() or None,
                            "title": str(slice_item.get("title") or "").strip() or None,
                        }
                    )
                if status in {"", "pending"}:
                    paper_role = str(slice_item.get("paper_role") or "").strip().lower()
                    tier = str(slice_item.get("tier") or "").strip().lower()
                    if paper_role == "main_text" or tier == "main_required":
                        blocking_pending_slices.append(
                            {
                                "campaign_id": str(campaign.get("campaign_id") or "").strip() or None,
                                "slice_id": str(slice_item.get("slice_id") or "").strip() or None,
                                "item_id": str(slice_item.get("item_id") or "").strip() or None,
                                "section_id": str(slice_item.get("section_id") or "").strip() or None,
                                "title": str(slice_item.get("title") or "").strip() or None,
                            }
                        )

        contract_ok = not unresolved_required_items and not unmapped_completed_items
        writing_ready = contract_ok and not blocking_pending_slices
        draft_path = str((paper_contract.get("paths") or {}).get("draft") or "").strip()
        draft_status = str(active_line.get("draft_status") or "").strip() or ("present" if draft_path else "missing")
        bundle_status = str(active_line.get("bundle_status") or "").strip() or (
            "present" if str((paper_contract.get("paths") or {}).get("bundle_manifest") or "").strip() else "missing"
        )
        bundle_manifest = (
            dict(paper_contract.get("bundle_manifest") or {})
            if isinstance(paper_contract.get("bundle_manifest"), dict)
            else {}
        )
        package_type = str(bundle_manifest.get("package_type") or "draft_checkpoint").strip().lower().replace("-", "_")
        if package_type in {"", "draft", "memo", "checkpoint", "paper_memo"}:
            package_type = "draft_checkpoint"
        elif package_type in {"review", "review_bundle"}:
            package_type = "review_package"
        elif package_type in {"final", "final_bundle", "submission", "submission_bundle"}:
            package_type = "submission_package"
        elif package_type not in {"draft_checkpoint", "review_package", "submission_package"}:
            package_type = "draft_checkpoint"
        coverage_path = str(((paper_contract.get("paths") or {}).get("manuscript_coverage") or "")).strip()
        manuscript_coverage = read_json(Path(coverage_path), {}) if coverage_path else {}
        manuscript_coverage = manuscript_coverage if isinstance(manuscript_coverage, dict) else {}
        submission_checklist_path = str(((paper_contract.get("paths") or {}).get("submission_checklist") or "")).strip()
        submission_checklist = read_json(Path(submission_checklist_path), {}) if submission_checklist_path else {}
        submission_checklist = submission_checklist if isinstance(submission_checklist, dict) else {}
        overall_status = str(submission_checklist.get("overall_status") or bundle_manifest.get("status") or "").strip().lower()
        delivered_at = str(
            bundle_manifest.get("paper_delivered_to_user_at")
            or bundle_manifest.get("delivered_at")
            or submission_checklist.get("paper_delivered_to_user_at")
            or ""
        ).strip() or None
        closure_state = "bundle_not_ready"
        delivery_state = "not_ready"
        keep_bundle_fixed_by_default = False
        evidence_ready = contract_ok
        analysis_ready = writing_ready
        academic_outline_ready = bool(manuscript_coverage.get("academic_outline_ready"))
        analysis_plan_ready = bool(manuscript_coverage.get("analysis_plan_ready"))
        language_firewall_ok = bool(manuscript_coverage.get("language_firewall_ok"))
        draft_checkpoint_ready = bool(active_line.get("draft_checkpoint_ready")) or draft_status == "present" or bundle_status == "present"
        manuscript_ready = bool(active_line.get("manuscript_ready")) or bool(manuscript_coverage.get("manuscript_ready"))
        submission_ready = bool(active_line.get("submission_ready")) or bool(manuscript_coverage.get("submission_ready"))
        if submission_ready:
            closure_state = "delivery_ready"
            delivery_state = "submission_ready"
        elif manuscript_ready:
            closure_state = "review_before_submission"
            delivery_state = "manuscript_ready"
        elif draft_checkpoint_ready:
            closure_state = "draft_checkpoint_continue_writing"
            delivery_state = "draft_checkpoint_ready"
        if delivered_at or "delivered" in overall_status:
            delivery_state = "delivered"
            closure_state = "delivered_continue_research" if "continue" in overall_status else "delivered_parked"
            keep_bundle_fixed_by_default = True

        if unmapped_completed_items:
            recommended_next_stage = "write"
            recommended_action = "sync_paper_contract"
        elif manuscript_coverage and not academic_outline_ready:
            recommended_next_stage = "write"
            recommended_action = "repair_academic_outline_with_paper_outline"
        elif manuscript_coverage and not analysis_plan_ready:
            recommended_next_stage = "write"
            recommended_action = "repair_analysis_plan_with_paper_outline"
        elif unresolved_required_items or blocking_pending_slices:
            recommended_next_stage = "analysis-campaign"
            recommended_action = "complete_required_supplementary"
        elif manuscript_coverage and not language_firewall_ok and draft_checkpoint_ready:
            recommended_next_stage = "write"
            recommended_action = "repair_manuscript_language"
        elif draft_status != "present":
            recommended_next_stage = "write"
            recommended_action = "draft_paper"
        elif bundle_status != "present":
            recommended_next_stage = "write"
            recommended_action = "submit_draft_checkpoint"
        elif not manuscript_ready:
            recommended_next_stage = "write"
            recommended_action = "expand_manuscript_and_figures"
        elif not submission_ready:
            recommended_next_stage = "review"
            recommended_action = "prepare_submission_package"
        else:
            recommended_next_stage = "finalize"
            recommended_action = "finalize_paper_line"

        blocking_reasons: list[str] = []
        if unmapped_completed_items:
            blocking_reasons.append("completed analysis remains unmapped into the paper contract")
        if unresolved_required_items:
            blocking_reasons.append("required outline items are still unresolved")
        if blocking_pending_slices:
            blocking_reasons.append("main-text supplementary slices are still pending")

        return {
            "paper_line_id": active_line_id,
            "paper_branch": active_line_branch,
            "selected_outline_ref": selected_outline_ref,
            "contract_ok": contract_ok,
            "writing_ready": writing_ready,
            "evidence_ready": evidence_ready,
            "analysis_ready": analysis_ready,
            "academic_outline_ready": academic_outline_ready,
            "analysis_plan_ready": analysis_plan_ready,
            "language_firewall_ok": language_firewall_ok,
            "draft_checkpoint_ready": draft_checkpoint_ready,
            "manuscript_ready": manuscript_ready,
            "submission_ready": submission_ready,
            "finalize_ready": submission_ready,
            "package_type": package_type,
            "closure_state": closure_state,
            "delivery_state": delivery_state,
            "delivered_at": delivered_at,
            "keep_bundle_fixed_by_default": keep_bundle_fixed_by_default,
            "required_count": sum(
                len(section.get("required_items") or [])
                for section in (paper_contract.get("sections") or [])
                if isinstance(section, dict)
            ),
            "ready_required_count": max(
                0,
                sum(
                    len(section.get("required_items") or [])
                    for section in (paper_contract.get("sections") or [])
                    if isinstance(section, dict)
                )
                - len(unresolved_required_items),
            ),
            "section_count": len([section for section in (paper_contract.get("sections") or []) if isinstance(section, dict)]),
            "ready_section_count": ready_section_count,
            "ledger_item_count": len(evidence_items),
            "unresolved_required_count": len(unresolved_required_items),
            "unmapped_completed_count": len(unmapped_completed_items),
            "open_supplementary_count": int(active_line.get("open_supplementary_count") or 0),
            "blocking_open_supplementary_count": len(blocking_pending_slices),
            "draft_status": draft_status,
            "bundle_status": bundle_status,
            "blocking_reasons": blocking_reasons,
            "manuscript_blocking_reasons": list(
                active_line.get("manuscript_blocking_reasons")
                or manuscript_coverage.get("manuscript_blockers")
                or []
            ),
            "submission_blocking_reasons": list(
                active_line.get("submission_blocking_reasons")
                or manuscript_coverage.get("submission_blockers")
                or []
            ),
            "manuscript_coverage": manuscript_coverage or None,
            "recommended_next_stage": recommended_next_stage,
            "recommended_action": recommended_action,
            "unresolved_required_items": unresolved_required_items[:12],
            "unmapped_completed_items": unmapped_completed_items[:12],
            "blocking_pending_slices": blocking_pending_slices[:12],
        }

    @staticmethod
    def _latest_metric_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
        return extract_latest_metric(payload)

    @staticmethod
    def _parse_numeric_quest_id(value: str | None) -> int | None:
        raw = str(value or "").strip()
        if not _NUMERIC_QUEST_ID_PATTERN.fullmatch(raw):
            return None
        numeric_value = int(raw)
        if numeric_value < 1 or numeric_value > _MAX_NUMERIC_QUEST_ID_VALUE:
            return None
        return numeric_value

    @staticmethod
    def _format_numeric_quest_id(value: int) -> str:
        if value < 1:
            raise ValueError("Sequential quest ids must be positive integers.")
        text = str(value)
        if len(text) > 10:
            raise ValueError("Sequential quest ids support at most 10 digits.")
        if len(text) >= _NUMERIC_QUEST_ID_PAD_WIDTH:
            return text
        return text.zfill(_NUMERIC_QUEST_ID_PAD_WIDTH)

    @staticmethod
    def _parse_reserved_numeric_quest_id(value: str | None) -> int | None:
        numeric_value = QuestService._parse_numeric_quest_id(value)
        if numeric_value is not None:
            return numeric_value
        raw = str(value or "").strip()
        match = _SYSTEM_NUMERIC_QUEST_ID_PATTERN.fullmatch(raw)
        if match is None:
            return None
        return QuestService._parse_numeric_quest_id(match.group("number"))

    @staticmethod
    def _quest_class_for(
        *,
        quest_id: str | None,
        startup_contract: dict[str, Any] | None = None,
    ) -> str:
        normalized_quest_id = str(quest_id or "").strip()
        match = _SYSTEM_NUMERIC_QUEST_ID_PATTERN.fullmatch(normalized_quest_id)
        if match is not None:
            prefix = str(match.group("prefix") or "").strip().upper()
            if prefix == "S":
                return "settings"
            if prefix == "B":
                return "benchstore"

        contract = startup_contract if isinstance(startup_contract, dict) else {}
        custom_profile = str(contract.get("custom_profile") or "").strip().lower()
        if custom_profile in {"admin_ops", "settings_issue"}:
            return "settings"
        if isinstance(contract.get("benchstore_context"), dict) or isinstance(contract.get("start_setup_session"), dict):
            return "benchstore"
        return "research"

    @contextmanager
    def _quest_id_state_lock(self):
        lock_path = self._quest_id_lock_path()
        ensure_dir(lock_path.parent)
        with advisory_file_lock(lock_path):
            yield

    @contextmanager
    def _runtime_state_lock(self, quest_root: Path):
        lock_key = str(quest_root.resolve())
        with self._runtime_state_locks_lock:
            thread_lock = self._runtime_state_locks.setdefault(lock_key, threading.Lock())
        with thread_lock:
            lock_path = self._runtime_state_lock_path(quest_root)
            ensure_dir(lock_path.parent)
            with advisory_file_lock(lock_path):
                yield

    def _scan_next_numeric_quest_id(self) -> int:
        max_numeric_id = 0
        if not self.quests_root.exists():
            return 1
        for quest_root in sorted(self.quests_root.iterdir()):
            if not quest_root.is_dir():
                continue
            numeric_value = self._parse_numeric_quest_id(quest_root.name)
            if numeric_value is None:
                continue
            max_numeric_id = max(max_numeric_id, numeric_value)
        return max_numeric_id + 1

    def _read_quest_id_state_locked(self) -> dict[str, Any]:
        state_path = self._quest_id_state_path()
        scanned_next_numeric_id = self._scan_next_numeric_quest_id()
        payload = read_json(state_path, {})
        should_write = not state_path.exists()
        if not isinstance(payload, dict):
            payload = {}
            should_write = True
        next_numeric_id = payload.get("next_numeric_id")
        if isinstance(next_numeric_id, str) and next_numeric_id.isdigit():
            next_numeric_id = int(next_numeric_id)
        if not isinstance(next_numeric_id, int) or next_numeric_id < 1:
            next_numeric_id = scanned_next_numeric_id
            should_write = True
        elif next_numeric_id < scanned_next_numeric_id:
            next_numeric_id = scanned_next_numeric_id
            should_write = True
        state = {
            "version": 1,
            "next_numeric_id": next_numeric_id,
            "updated_at": str(payload.get("updated_at") or utc_now()),
        }
        if payload.get("version") != 1:
            should_write = True
        if should_write:
            state["updated_at"] = utc_now()
            write_json(state_path, state)
        return state

    def _write_quest_id_state_locked(self, next_numeric_id: int) -> None:
        write_json(
            self._quest_id_state_path(),
            {
                "version": 1,
                "next_numeric_id": next_numeric_id,
                "updated_at": utc_now(),
            },
        )

    def _allocate_next_numeric_quest_id(self) -> str:
        with self._quest_id_state_lock():
            state = self._read_quest_id_state_locked()
            next_numeric_id = int(state.get("next_numeric_id") or 1)
            quest_id = self._format_numeric_quest_id(next_numeric_id)
            self._write_quest_id_state_locked(next_numeric_id + 1)
            return quest_id

    def preview_next_numeric_quest_id(self) -> str:
        with self._quest_id_state_lock():
            state = self._read_quest_id_state_locked()
            next_numeric_id = int(state.get("next_numeric_id") or 1)
            return self._format_numeric_quest_id(next_numeric_id)

    def _reserve_numeric_quest_id(self, quest_id: str) -> None:
        numeric_value = self._parse_reserved_numeric_quest_id(quest_id)
        if numeric_value is None:
            return
        with self._quest_id_state_lock():
            state = self._read_quest_id_state_locked()
            next_numeric_id = max(int(state.get("next_numeric_id") or 1), numeric_value + 1)
            if next_numeric_id != int(state.get("next_numeric_id") or 1):
                self._write_quest_id_state_locked(next_numeric_id)

    def _normalize_quest_id(self, quest_id: str | None) -> tuple[str, bool]:
        raw = str(quest_id or "").strip()
        if not raw:
            return self._allocate_next_numeric_quest_id(), True
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("._-")
        if not slug:
            return self._allocate_next_numeric_quest_id(), True
        system_match = _SYSTEM_NUMERIC_QUEST_ID_PATTERN.fullmatch(slug)
        if system_match is not None:
            slug = f"{str(system_match.group('prefix') or '').upper()}-{system_match.group('number')}"
        return slug[:80], False

    def create(
        self,
        goal: str,
        quest_id: str | None = None,
        runner: str | None = None,
        title: str | None = None,
        *,
        requested_baseline_ref: dict[str, Any] | None = None,
        startup_contract: dict[str, Any] | None = None,
    ) -> dict:
        resolved_runner = str(runner or self._configured_default_runner()).strip().lower() or "codex"
        quest_id, auto_generated = self._normalize_quest_id(quest_id)
        quest_root = self._quest_root(quest_id)
        if quest_root.exists():
            raise FileExistsError(f"Quest already exists: {quest_id}")
        if not auto_generated:
            self._reserve_numeric_quest_id(quest_id)
        ensure_dir(quest_root)
        for relative in QUEST_DIRECTORIES:
            ensure_dir(quest_root / relative)
        write_yaml(
            self._quest_yaml_path(quest_root),
            initial_quest_yaml(
                quest_id,
                goal,
                quest_root,
                resolved_runner,
                title=title,
                requested_baseline_ref=dict(requested_baseline_ref) if isinstance(requested_baseline_ref, dict) else None,
                startup_contract=dict(startup_contract) if isinstance(startup_contract, dict) else None,
            ),
        )
        write_text(quest_root / "brief.md", initial_brief(goal))
        write_text(quest_root / "plan.md", initial_plan())
        write_text(quest_root / "status.md", initial_status(startup_contract))
        write_text(quest_root / "SUMMARY.md", initial_summary())
        write_text(quest_root / ".gitignore", gitignore())
        self._write_active_user_requirements(
            quest_root,
            latest_requirement=None,
        )
        init_repo(quest_root)
        if self.skill_installer is not None:
            self.skill_installer.sync_quest(quest_root)
        from ..gitops import checkpoint_repo

        checkpoint_repo(quest_root, f"quest: initialize {quest_id}", allow_empty=False)
        export_git_graph(quest_root, ensure_dir(quest_root / "artifacts" / "graphs"))
        self._initialize_runtime_files(quest_root)
        return self.snapshot(quest_id)

    def repair_orphaned_quest_scaffold(
        self,
        quest_id: str,
        *,
        title: str | None = None,
        goal: str | None = None,
        runner: str | None = None,
    ) -> dict[str, Any]:
        resolved_runner = str(runner or self._configured_default_runner()).strip().lower() or "codex"
        quest_root = self._quest_root(quest_id)
        if not quest_root.exists():
            raise FileNotFoundError(f"Unknown quest `{quest_id}`.")
        quest_yaml_path = self._quest_yaml_path(quest_root)
        if quest_yaml_path.exists():
            raise FileExistsError(f"Quest `{quest_id}` already has a scaffold.")

        restored_goal = str(goal or f"Recovered quest {quest_id}").strip() or f"Recovered quest {quest_id}"
        restored_title = str(title or quest_id).strip() or quest_id

        for relative in QUEST_DIRECTORIES:
            ensure_dir(quest_root / relative)

        write_yaml(
            quest_yaml_path,
            initial_quest_yaml(
                quest_id,
                restored_goal,
                quest_root,
                resolved_runner,
                title=restored_title,
            ),
        )
        write_text(
            quest_root / "brief.md",
            "\n".join(
                [
                    "# Quest Brief",
                    "",
                    "## Recovery Note",
                    "",
                    "This quest scaffold was recreated because the core quest files were missing.",
                    "Existing runtime traces under `.ds/` were preserved.",
                    "",
                    "## Goal",
                    "",
                    restored_goal,
                    "",
                ]
            ),
        )
        write_text(
            quest_root / "plan.md",
            "\n".join(
                [
                    "# Plan",
                    "",
                    "- [ ] Inspect preserved runtime traces under `.ds/`",
                    "- [ ] Re-establish the baseline context",
                    "- [ ] Recreate any missing durable files or artifacts",
                    "",
                ]
            ),
        )
        write_text(
            quest_root / "status.md",
            "# Status\n\nRecovered scaffold. Review preserved runtime state before continuing.\n",
        )
        write_text(
            quest_root / "SUMMARY.md",
            "# Summary\n\nRecovered quest scaffold. Original top-level quest files were missing.\n",
        )
        write_text(quest_root / ".gitignore", gitignore())
        self._write_active_user_requirements(
            quest_root,
            latest_requirement=None,
        )
        if not (quest_root / ".git").exists():
            init_repo(quest_root)
        self._initialize_runtime_files(quest_root)
        return self.snapshot(quest_id)

    def list_quests(self) -> list[dict]:
        items: list[dict] = []
        if not self.quests_root.exists():
            return items
        for quest_yaml in sorted(self.quests_root.glob("*/quest.yaml")):
            quest_id = quest_yaml.parent.name
            items.append(self.summary_compact(quest_id))
        return sorted(items, key=lambda item: item.get("updated_at", ""), reverse=True)

    def _path_states(self, paths: list[Path]) -> tuple[tuple[str, tuple[int, int, int] | None], ...]:
        states: list[tuple[str, tuple[int, int, int] | None]] = []
        for path in paths:
            try:
                label = str(path.relative_to(self.home))
            except ValueError:
                label = str(path)
            states.append((label, self._path_state(path)))
        return tuple(states)

    def _glob_states(self, root: Path, pattern: str) -> tuple[tuple[str, tuple[int, int, int] | None], ...]:
        if not root.exists():
            return ()
        states: list[tuple[str, tuple[int, int, int] | None]] = []
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            try:
                label = str(path.relative_to(root))
            except ValueError:
                label = path.name
            states.append((label, self._path_state(path)))
        return tuple(states)

    def _artifact_collection_state(self, quest_root: Path) -> tuple[tuple[str, tuple[tuple[str, tuple[int, int, int] | None], ...]], ...]:
        states: list[tuple[str, tuple[tuple[str, tuple[int, int, int] | None], ...]]] = []
        for root in self.workspace_roots(quest_root):
            artifacts_root = root / "artifacts"
            if not artifacts_root.exists():
                continue
            try:
                label = str(root.relative_to(quest_root))
            except ValueError:
                label = str(root)
            states.append((label, self._glob_states(artifacts_root, "*/*.json")))
        return tuple(states)

    def _codex_meta_state(self, quest_root: Path) -> tuple[tuple[str, tuple[int, int, int] | None], ...]:
        return self._glob_states(quest_root / ".ds" / "codex_history", "*/meta.json")

    def _baseline_attachment_state(self, quest_root: Path) -> tuple[tuple[str, tuple[tuple[str, tuple[int, int, int] | None], ...]], ...]:
        states: list[tuple[str, tuple[tuple[str, tuple[int, int, int] | None], ...]]] = []
        for root in self.workspace_roots(quest_root):
            attachment_root = root / "baselines" / "imported"
            if not attachment_root.exists():
                continue
            try:
                label = str(root.relative_to(quest_root))
            except ValueError:
                label = str(root)
            states.append((label, self._glob_states(attachment_root, "*/attachment.yaml")))
        return tuple(states)

    def _snapshot_state(self, quest_root: Path) -> tuple[Any, ...]:
        core_paths = [
            self._quest_yaml_path(quest_root),
            quest_root / "status.md",
            quest_root / ".ds" / "runtime_state.json",
            quest_root / ".ds" / "research_state.json",
            quest_root / ".ds" / "user_message_queue.json",
            quest_root / ".ds" / "interaction_state.json",
            quest_root / ".ds" / "bindings.json",
            quest_root / ".ds" / "conversations" / "main.jsonl",
            quest_root / ".ds" / "bash_exec" / "summary.json",
        ]
        return (
            self._path_states(core_paths),
            self._artifact_collection_state(quest_root),
            self._codex_meta_state(quest_root),
            self._baseline_attachment_state(quest_root),
        )

    def _compact_summary_state(self, quest_root: Path) -> tuple[Any, ...]:
        core_paths = [
            self._quest_yaml_path(quest_root),
            quest_root / "status.md",
            quest_root / ".ds" / "runtime_state.json",
            quest_root / ".ds" / "research_state.json",
            quest_root / ".ds" / "interaction_state.json",
            quest_root / ".ds" / "bindings.json",
            quest_root / ".ds" / "bash_exec" / "summary.json",
        ]
        return (
            self._path_states(core_paths),
            self._baseline_attachment_state(quest_root),
        )

    def summary_compact(self, quest_id: str) -> dict[str, Any]:
        quest_root = self._require_initialized_quest_root(quest_id)
        cache_key = f"compact:{self._cache_key_for_path(quest_root)}"
        state = self._compact_summary_state(quest_root)
        with self._snapshot_cache_lock:
            cached = self._snapshot_cache.get(cache_key)
            if cached and cached.get("state") == state:
                return copy.deepcopy(cached.get("payload"))

        quest_yaml = self.read_quest_yaml(quest_root)
        research_state = self.read_research_state(quest_root)
        workspace_root = self.active_workspace_root(quest_root)
        runtime_state = self._read_runtime_state(quest_root)
        interaction_state = self._read_interaction_state(quest_root)
        open_requests = [
            dict(item)
            for item in (interaction_state.get("open_requests") or [])
            if str(item.get("status") or "") in {"waiting", "answered"}
        ]
        waiting_interaction_id = self._latest_waiting_interaction_id(open_requests)
        default_reply_interaction_id = str(interaction_state.get("default_reply_interaction_id") or "").strip() or None
        recent_threads = [dict(item) for item in (interaction_state.get("recent_threads") or [])][-5:]
        if not default_reply_interaction_id:
            default_reply_interaction_id = self._default_reply_interaction_id(
                open_requests=open_requests,
                recent_threads=recent_threads,
            )
        pending_decisions = [
            str(item.get("artifact_id") or item.get("interaction_id") or "")
            for item in open_requests
            if str(item.get("status") or "") == "waiting"
            and (item.get("artifact_id") or item.get("interaction_id"))
        ]
        attachment = self._active_baseline_attachment(quest_root, workspace_root)
        active_baseline_id = None
        active_baseline_variant_id = None
        if attachment:
            active_baseline_id = attachment.get("source_baseline_id")
            active_baseline_variant_id = attachment.get("source_variant_id")
        elif isinstance(quest_yaml.get("confirmed_baseline_ref"), dict):
            confirmed_ref = dict(quest_yaml.get("confirmed_baseline_ref") or {})
            active_baseline_id = confirmed_ref.get("baseline_id")
            active_baseline_variant_id = confirmed_ref.get("variant_id")

        status_line = "Quest created."
        status_text = self._read_cached_text(quest_root / "status.md").strip().splitlines()
        if status_text:
            for line in status_text:
                line = line.strip().lstrip("#").strip()
                if line and line.lower() not in {"status", "summary"}:
                    status_line = line
                    break

        from ..bash_exec import BashExecService

        bash_summary = BashExecService(self.home).summary(quest_root)
        interaction_watchdog = self.artifact_interaction_watchdog_status(quest_root)
        quest_class = self._quest_class_for(
            quest_id=str(quest_yaml.get("quest_id") or quest_id).strip(),
            startup_contract=quest_yaml.get("startup_contract") if isinstance(quest_yaml.get("startup_contract"), dict) else None,
        )
        workspace_mode = str(research_state.get("workspace_mode") or "quest").strip().lower() or "quest"
        listed_in_projects = quest_class == "research" and workspace_mode in {"copilot", "autonomous"}
        payload = {
            "quest_id": quest_yaml.get("quest_id", quest_id),
            "title": quest_yaml.get("title", quest_id),
            "quest_root": str(quest_root.resolve()),
            "status": runtime_state.get("display_status") or runtime_state.get("status") or quest_yaml.get("status", "idle"),
            "runtime_status": runtime_state.get("status") or quest_yaml.get("status", "idle"),
            "display_status": runtime_state.get("display_status") or runtime_state.get("status") or quest_yaml.get("status", "idle"),
            "active_anchor": quest_yaml.get("active_anchor", "baseline"),
            "baseline_gate": quest_yaml.get("baseline_gate", "pending"),
            "confirmed_baseline_ref": quest_yaml.get("confirmed_baseline_ref"),
            "requested_baseline_ref": quest_yaml.get("requested_baseline_ref"),
            "startup_contract": quest_yaml.get("startup_contract"),
            "runner": quest_yaml.get("default_runner", "codex"),
            "active_workspace_root": str(workspace_root),
            "research_head_branch": research_state.get("research_head_branch"),
            "research_head_worktree_root": research_state.get("research_head_worktree_root"),
            "current_workspace_branch": research_state.get("current_workspace_branch"),
            "current_workspace_root": research_state.get("current_workspace_root"),
            "workspace_mode": workspace_mode,
            "quest_class": quest_class,
            "listed_in_projects": listed_in_projects,
            "active_idea_id": research_state.get("active_idea_id"),
            "active_baseline_id": active_baseline_id,
            "active_baseline_variant_id": active_baseline_variant_id,
            "active_run_id": runtime_state.get("active_run_id"),
            "continuation_policy": runtime_state.get("continuation_policy") or "auto",
            "continuation_anchor": runtime_state.get("continuation_anchor"),
            "continuation_reason": runtime_state.get("continuation_reason"),
            "continuation_updated_at": runtime_state.get("continuation_updated_at"),
            "waiting_notice": runtime_state.get("waiting_notice"),
            "last_resume_source": runtime_state.get("last_resume_source"),
            "last_resume_at": runtime_state.get("last_resume_at"),
            "last_recovery_abandoned_run_id": runtime_state.get("last_recovery_abandoned_run_id"),
            "last_recovery_summary": runtime_state.get("last_recovery_summary"),
            "last_stage_fingerprint": runtime_state.get("last_stage_fingerprint"),
            "last_stage_fingerprint_at": runtime_state.get("last_stage_fingerprint_at"),
            "same_fingerprint_auto_turn_count": int(runtime_state.get("same_fingerprint_auto_turn_count") or 0),
            "pending_decisions": pending_decisions,
            "waiting_interaction_id": waiting_interaction_id,
            "default_reply_interaction_id": default_reply_interaction_id,
            "pending_user_message_count": int(runtime_state.get("pending_user_message_count") or 0),
            "stop_reason": runtime_state.get("stop_reason"),
            "active_interaction_id": runtime_state.get("active_interaction_id"),
            "last_artifact_interact_at": runtime_state.get("last_artifact_interact_at"),
            "last_tool_activity_at": runtime_state.get("last_tool_activity_at"),
            "last_tool_activity_name": runtime_state.get("last_tool_activity_name"),
            "tool_calls_since_last_artifact_interact": int(runtime_state.get("tool_calls_since_last_artifact_interact") or 0),
            "seconds_since_last_artifact_interact": interaction_watchdog.get("seconds_since_last_artifact_interact"),
            "last_delivered_batch_id": runtime_state.get("last_delivered_batch_id"),
            "last_delivered_at": runtime_state.get("last_delivered_at"),
            "bound_conversations": self._binding_sources_payload(quest_root).get("sources") or ["local:default"],
            "created_at": quest_yaml.get("created_at"),
            "updated_at": quest_yaml.get("updated_at"),
            "branch": research_state.get("current_workspace_branch") or research_state.get("research_head_branch"),
            "summary": {
                "status_line": status_line,
                "latest_metric": None,
                "latest_bash_session": bash_summary.get("latest_session"),
            },
            "counts": {
                "memory_cards": 0,
                "artifacts": 0,
                "pending_decision_count": len(pending_decisions),
                "analysis_run_count": 0,
                "pending_user_message_count": int(runtime_state.get("pending_user_message_count") or 0),
                "bash_session_count": int(bash_summary.get("session_count") or 0),
                "bash_running_count": int(bash_summary.get("running_count") or 0),
            },
            "interaction_watchdog": interaction_watchdog,
            "recent_artifacts": [],
            "recent_runs": [],
        }
        with self._snapshot_cache_lock:
            self._snapshot_cache[cache_key] = {
                "state": state,
                "payload": copy.deepcopy(payload),
            }
        return payload

    def _read_cached_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            cache_key = str(path.resolve())
            with self._jsonl_cache_lock:
                self._jsonl_cache.pop(cache_key, None)
            return []
        cache_key = str(path.resolve())
        stat = path.stat()
        state = (
            stat.st_ino,
            getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)),
            stat.st_size,
        )
        if stat.st_size > _JSONL_CACHE_MAX_BYTES:
            with self._jsonl_cache_lock:
                self._jsonl_cache.pop(cache_key, None)
            return read_jsonl(path)
        with self._jsonl_cache_lock:
            cached = self._jsonl_cache.get(cache_key)
            if cached and cached.get("state") == state:
                return cached.get("records") or []
        items = read_jsonl(path)
        with self._jsonl_cache_lock:
            self._jsonl_cache[cache_key] = {
                "state": state,
                "records": items,
            }
        return items

    def _read_jsonl_cursor_slice(
        self,
        path: Path,
        *,
        after: int = 0,
        before: int | None = None,
        limit: int = 200,
        tail: bool = False,
    ) -> tuple[list[tuple[int, dict[str, Any]]], int, bool]:
        normalized_limit = max(int(limit or 0), 0)
        cache_key = self._cache_key_for_path(path)
        if not path.exists():
            with self._jsonl_cache_lock:
                self._jsonl_tail_cache.pop(cache_key, None)
            return [], 0, False
        if normalized_limit <= 0:
            total = _count_jsonl_lines_fast(path)
            return [], total, False

        if before is not None:
            window: deque[tuple[int, dict[str, Any]]] = deque(maxlen=normalized_limit)
            total = 0
            for cursor, payload in _iter_jsonl_records_safely(path):
                total = cursor
                if cursor >= before:
                    break
                if isinstance(payload, dict):
                    window.append((cursor, payload))
            has_more = bool(window and window[0][0] > 1)
            return list(window), total, has_more

        if tail:
            state = self._path_state(path)
            cached_tail: dict[str, Any] | None = None
            with self._jsonl_cache_lock:
                candidate = self._jsonl_tail_cache.get(cache_key)
                if isinstance(candidate, dict):
                    cached_tail = dict(candidate)

            if cached_tail and cached_tail.get("state") == state:
                cached_limit = int(cached_tail.get("limit") or 0)
                cached_records = list(cached_tail.get("records") or [])
                cached_total = int(cached_tail.get("total") or 0)
                if cached_limit >= normalized_limit and cached_records:
                    window = cached_records[-normalized_limit:]
                    has_more = cached_total > len(window)
                    return window, cached_total, has_more
                if cached_limit < normalized_limit:
                    window, total = _tail_jsonl_records_safely(path, limit=normalized_limit)
                    with self._jsonl_cache_lock:
                        self._jsonl_tail_cache[cache_key] = {
                            "state": state,
                            "limit": normalized_limit,
                            "total": total,
                            "records": list(window),
                        }
                    has_more = total > len(window)
                    return list(window), total, has_more

            if (
                cached_tail
                and state is not None
                and cached_tail.get("state")
                and tuple(cached_tail.get("state"))[0] == state[0]
                and state[2] >= tuple(cached_tail.get("state"))[2]
            ):
                cached_state = tuple(cached_tail.get("state"))
                cached_limit = int(cached_tail.get("limit") or 0)
                cached_total = int(cached_tail.get("total") or 0)
                max_limit = max(normalized_limit, cached_limit)
                window = deque(
                    list(cached_tail.get("records") or []),
                    maxlen=max_limit,
                )
                appended_records = list(
                    _iter_jsonl_records_from_offset_safely(
                        path,
                        start_offset=int(cached_state[2]),
                    )
                )
                if appended_records:
                    total = cached_total
                    for relative_cursor, payload in appended_records:
                        total = cached_total + relative_cursor
                        if isinstance(payload, dict):
                            window.append((total, payload))
                else:
                    total = cached_total
                stored_records = list(window)
                with self._jsonl_cache_lock:
                    self._jsonl_tail_cache[cache_key] = {
                        "state": state,
                        "limit": max_limit,
                        "total": total,
                        "records": stored_records,
                    }
                write_json(
                    _jsonl_line_count_cache_path(path),
                    {
                        "state": list(state),
                        "total": total,
                    },
                )
                selected = stored_records[-normalized_limit:]
                has_more = total > len(selected)
                return selected, total, has_more

            window, total = _tail_jsonl_records_safely(path, limit=normalized_limit)
            with self._jsonl_cache_lock:
                self._jsonl_tail_cache[cache_key] = {
                    "state": state,
                    "limit": normalized_limit,
                    "total": total,
                    "records": list(window),
                }
            has_more = total > len(window)
            return list(window), total, has_more

        collected: list[tuple[int, dict[str, Any]]] = []
        total = 0
        saw_more = False
        normalized_after = max(int(after or 0), 0)
        for cursor, payload in _iter_jsonl_records_safely(path):
            total = cursor
            if cursor <= normalized_after:
                continue
            if not isinstance(payload, dict):
                continue
            if len(collected) < normalized_limit:
                collected.append((cursor, payload))
                continue
            saw_more = True
        return collected, total, saw_more

    @staticmethod
    def _path_state(path: Path) -> tuple[int, int, int] | None:
        if not path.exists():
            return None
        stat = path.stat()
        return (
            stat.st_ino,
            getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)),
            stat.st_size,
        )

    @staticmethod
    def _cache_key_for_path(path: Path) -> str:
        try:
            return str(path.resolve())
        except FileNotFoundError:
            return str(path.absolute())

    def jsonl_tail_cache_entry(self, path: Path) -> dict[str, Any] | None:
        cache_key = self._cache_key_for_path(path)
        with self._jsonl_cache_lock:
            candidate = self._jsonl_tail_cache.get(cache_key)
            if isinstance(candidate, dict):
                return dict(candidate)
        return None

    def _read_cached_path(
        self,
        path: Path,
        *,
        default: Any,
        loader: Any,
    ) -> Any:
        cache_key = self._cache_key_for_path(path)
        state = self._path_state(path)
        if state is None:
            with self._file_cache_lock:
                self._file_cache.pop(cache_key, None)
            return copy.deepcopy(default)
        with self._file_cache_lock:
            cached = self._file_cache.get(cache_key)
            if cached and cached.get("state") == state:
                return copy.deepcopy(cached.get("value"))
        value = loader(path, default)
        with self._file_cache_lock:
            self._file_cache[cache_key] = {
                "state": state,
                "value": value,
            }
        return copy.deepcopy(value)

    def _read_cached_json(self, path: Path, default: Any = None) -> Any:
        return self._read_cached_path(path, default=default, loader=read_json)

    def _read_cached_yaml(self, path: Path, default: Any = None) -> Any:
        return self._read_cached_path(path, default=default, loader=read_yaml)

    def _read_cached_text(self, path: Path, default: str = "") -> str:
        value = self._read_cached_path(path, default=default, loader=read_text)
        return str(value) if value is not None else default

    def _parse_codex_history_cached(
        self,
        history_root: Path,
        *,
        quest_id: str,
        run_id: str,
        skill_id: str | None,
    ) -> list[dict[str, Any]]:
        history_path = history_root / "events.jsonl"
        cache_key = f"{self._cache_key_for_path(history_path)}::{quest_id}::{run_id}::{skill_id or ''}"
        state = self._path_state(history_path)
        if state is None:
            with self._codex_history_cache_lock:
                self._codex_history_cache.pop(cache_key, None)
            return []
        with self._codex_history_cache_lock:
            cached = self._codex_history_cache.get(cache_key)
            if cached and cached.get("state") == state:
                return copy.deepcopy(cached.get("entries") or [])
        entries = _parse_codex_history(
            history_root,
            quest_id=quest_id,
            run_id=run_id,
            skill_id=skill_id,
        )
        with self._codex_history_cache_lock:
            self._codex_history_cache[cache_key] = {
                "state": state,
                "entries": copy.deepcopy(entries),
            }
        return entries

    def snapshot_fast(self, quest_id: str) -> dict:
        return self.summary_compact(quest_id)

    def snapshot(self, quest_id: str) -> dict:
        return self._snapshot(quest_id)

    def _snapshot(self, quest_id: str) -> dict:
        quest_root = self._require_initialized_quest_root(quest_id)
        cache_key = f"snapshot:{self._cache_key_for_path(quest_root)}"
        state = self._snapshot_state(quest_root)
        with self._snapshot_cache_lock:
            cached = self._snapshot_cache.get(cache_key)
            if cached and cached.get("state") == state:
                return copy.deepcopy(cached.get("payload"))
        workspace_root = self.active_workspace_root(quest_root)
        research_state = self.read_research_state(quest_root)
        quest_yaml = self.read_quest_yaml(quest_root)
        graph_dir = quest_root / "artifacts" / "graphs"
        graph_svg = graph_dir / "git-graph.svg"
        history = self._read_cached_jsonl(quest_root / ".ds" / "conversations" / "main.jsonl")
        artifacts = []
        recent_runs = []
        memory_cards = list((workspace_root / "memory").glob("**/*.md"))
        pending_decisions = []
        active_interactions = []
        candidate_pending_decisions = []
        approved_decision_ids: set[str] = set()
        latest_metric = None
        active_baseline_id = None
        active_baseline_variant_id = None
        interaction_state = self._read_interaction_state(quest_root)
        open_requests = [
            dict(item)
            for item in (interaction_state.get("open_requests") or [])
            if str(item.get("status") or "") in {"waiting", "answered"}
        ]
        active_interactions = open_requests[-5:]
        recent_reply_threads = [dict(item) for item in (interaction_state.get("recent_threads") or [])][-5:]
        waiting_interaction_id = self._latest_waiting_interaction_id(open_requests)
        latest_thread_interaction_id = str(interaction_state.get("latest_thread_interaction_id") or "").strip() or None
        default_reply_interaction_id = str(interaction_state.get("default_reply_interaction_id") or "").strip() or None
        if not default_reply_interaction_id:
            default_reply_interaction_id = self._default_reply_interaction_id(
                open_requests=open_requests,
                recent_threads=recent_reply_threads,
            )
        answered_interaction_ids = {
            str(item.get("artifact_id") or item.get("interaction_id") or "")
            for item in active_interactions
            if str(item.get("status") or "") == "answered"
        }
        pending_decisions.extend(
            [
                str(item.get("artifact_id") or item.get("interaction_id") or "")
                for item in active_interactions
                if str(item.get("status") or "") == "waiting"
                and (item.get("artifact_id") or item.get("interaction_id"))
            ]
        )
        artifacts = self._collect_artifacts(quest_root)
        for artifact_item in artifacts:
            folder_name = str(artifact_item.get("kind") or "")
            path = Path(str(artifact_item.get("path") or "artifact.json"))
            item = artifact_item.get("payload") or {}
            if folder_name == "approvals":
                decision_id = str(item.get("decision_id") or "").strip()
                if decision_id:
                    approved_decision_ids.add(decision_id)
            if folder_name == "decisions":
                is_pending_user = (
                    str(item.get("verdict") or "") == "pending_user"
                    or str(item.get("action") or "") == "request_user_decision"
                    or str(item.get("interaction_phase") or "") == "request"
                )
                decision_id = str(item.get("id") or path.stem)
                if is_pending_user:
                    candidate_pending_decisions.append(decision_id)
            artifact_metric = self._latest_metric_from_payload(item)
            if artifact_metric is not None:
                latest_metric = artifact_metric
        for decision_id in candidate_pending_decisions:
            if decision_id in pending_decisions:
                continue
            if decision_id in answered_interaction_ids:
                continue
            if decision_id in approved_decision_ids:
                continue
            pending_decisions.append(decision_id)
        codex_history_root = quest_root / ".ds" / "codex_history"
        if codex_history_root.exists():
            for meta_path in sorted(codex_history_root.glob("*/meta.json")):
                run_data = self._read_cached_json(meta_path, {})
                if run_data:
                    recent_runs.append(run_data)
                    if latest_metric is None and run_data.get("summary"):
                        latest_metric = {"key": "summary", "value": run_data.get("summary")}
        attachment = self._active_baseline_attachment(quest_root, workspace_root)
        if attachment:
            active_baseline_id = attachment.get("source_baseline_id")
            active_baseline_variant_id = attachment.get("source_variant_id")
        elif isinstance(quest_yaml.get("confirmed_baseline_ref"), dict):
            confirmed_ref = dict(quest_yaml.get("confirmed_baseline_ref") or {})
            active_baseline_id = confirmed_ref.get("baseline_id")
            active_baseline_variant_id = confirmed_ref.get("variant_id")
        status_line = "Quest created."
        status_text = self._read_cached_text(quest_root / "status.md").strip().splitlines()
        if status_text:
            for line in status_text:
                line = line.strip().lstrip("#").strip()
                if line and line.lower() not in {"status", "summary"}:
                    status_line = line
                    break
        runtime_state = self._read_runtime_state(quest_root)
        from ..bash_exec import BashExecService

        bash_service = BashExecService(self.home)
        bash_summary = bash_service.summary(quest_root)
        latest_bash_session = bash_summary.get("latest_session")
        paper_contract = self._paper_contract_payload(quest_root, workspace_root)
        paper_evidence = self._paper_evidence_payload(quest_root, workspace_root)
        analysis_inventory = self._analysis_inventory_payload(quest_root, workspace_root)
        paper_lines, active_paper_line_ref = self._paper_lines_payload(quest_root, workspace_root)
        idea_lines, active_idea_line_ref = self._idea_lines_payload(
            quest_root,
            paper_lines=paper_lines,
            analysis_inventory=analysis_inventory,
        )
        paper_contract_health = self._paper_contract_health_payload(
            paper_contract=paper_contract,
            paper_evidence=paper_evidence,
            analysis_inventory=analysis_inventory,
            paper_lines=paper_lines,
            active_paper_line_ref=active_paper_line_ref,
        )
        paths = {
            "brief": str(workspace_root / "brief.md"),
            "plan": str(workspace_root / "plan.md"),
            "status": str(workspace_root / "status.md"),
            "summary": str(workspace_root / "SUMMARY.md"),
            "git_graph_svg": str(graph_svg) if graph_svg.exists() else None,
            "runtime_state": str(self._runtime_state_path(quest_root)),
            "research_state": str(self._research_state_path(quest_root)),
            "active_workspace_root": str(workspace_root),
            "user_message_queue": str(self._message_queue_path(quest_root)),
            "interaction_journal": str(self._interaction_journal_path(quest_root)),
            "active_user_requirements": str(self._active_user_requirements_path(quest_root)),
            "bash_exec_root": str(quest_root / ".ds" / "bash_exec"),
        }
        counts = {
            "memory_cards": len(memory_cards),
            "artifacts": len(artifacts),
            "pending_decision_count": len(pending_decisions),
            "analysis_run_count": sum(
                1
                for item in recent_runs
                if str(item.get("run_id", "")).startswith("analysis")
                or item.get("run_kind") == "analysis-campaign"
            ),
            "pending_user_message_count": int(runtime_state.get("pending_user_message_count") or 0),
            "bash_session_count": int(bash_summary.get("session_count") or 0),
            "bash_running_count": int(bash_summary.get("running_count") or 0),
        }
        interaction_watchdog = self.artifact_interaction_watchdog_status(quest_root)
        guidance = None
        try:
            from ..artifact.guidance import build_guidance_for_snapshot

            guidance = build_guidance_for_snapshot(
                {
                    "quest_id": quest_yaml.get("quest_id", quest_id),
                    "active_anchor": quest_yaml.get("active_anchor", "baseline"),
                    "pending_decisions": pending_decisions,
                    "waiting_interaction_id": waiting_interaction_id,
                    "recent_artifacts": artifacts[-5:],
                }
            )
        except Exception:
            guidance = None
        payload = {
            "quest_id": quest_yaml.get("quest_id", quest_id),
            "title": quest_yaml.get("title", quest_id),
            "quest_root": str(quest_root.resolve()),
            "status": runtime_state.get("display_status") or runtime_state.get("status") or quest_yaml.get("status", "idle"),
            "runtime_status": runtime_state.get("status") or quest_yaml.get("status", "idle"),
            "display_status": runtime_state.get("display_status") or runtime_state.get("status") or quest_yaml.get("status", "idle"),
            "active_anchor": quest_yaml.get("active_anchor", "baseline"),
            "baseline_gate": quest_yaml.get("baseline_gate", "pending"),
            "confirmed_baseline_ref": quest_yaml.get("confirmed_baseline_ref"),
            "requested_baseline_ref": quest_yaml.get("requested_baseline_ref"),
            "startup_contract": quest_yaml.get("startup_contract"),
            "runner": quest_yaml.get("default_runner", "codex"),
            "active_workspace_root": str(workspace_root),
            "research_head_branch": research_state.get("research_head_branch"),
            "research_head_worktree_root": research_state.get("research_head_worktree_root"),
            "current_workspace_branch": research_state.get("current_workspace_branch"),
            "current_workspace_root": research_state.get("current_workspace_root"),
            "active_idea_id": research_state.get("active_idea_id"),
            "active_idea_md_path": research_state.get("active_idea_md_path"),
            "active_idea_draft_path": research_state.get("active_idea_draft_path"),
            "active_analysis_campaign_id": research_state.get("active_analysis_campaign_id"),
            "analysis_parent_branch": research_state.get("analysis_parent_branch"),
            "analysis_parent_worktree_root": research_state.get("analysis_parent_worktree_root"),
            "paper_parent_branch": research_state.get("paper_parent_branch"),
            "paper_parent_worktree_root": research_state.get("paper_parent_worktree_root"),
            "paper_parent_run_id": research_state.get("paper_parent_run_id"),
            "idea_lines": idea_lines,
            "active_idea_line_ref": active_idea_line_ref,
            "paper_lines": paper_lines,
            "active_paper_line_ref": active_paper_line_ref,
            "paper_contract_health": paper_contract_health,
            "next_pending_slice_id": research_state.get("next_pending_slice_id"),
            "workspace_mode": research_state.get("workspace_mode") or "quest",
            "active_baseline_id": active_baseline_id,
            "active_baseline_variant_id": active_baseline_variant_id,
            "active_run_id": runtime_state.get("active_run_id"),
            "continuation_policy": runtime_state.get("continuation_policy") or "auto",
            "continuation_anchor": runtime_state.get("continuation_anchor"),
            "continuation_reason": runtime_state.get("continuation_reason"),
            "continuation_updated_at": runtime_state.get("continuation_updated_at"),
            "waiting_notice": runtime_state.get("waiting_notice"),
            "last_resume_source": runtime_state.get("last_resume_source"),
            "last_resume_at": runtime_state.get("last_resume_at"),
            "last_recovery_abandoned_run_id": runtime_state.get("last_recovery_abandoned_run_id"),
            "last_recovery_summary": runtime_state.get("last_recovery_summary"),
            "last_stage_fingerprint": runtime_state.get("last_stage_fingerprint"),
            "last_stage_fingerprint_at": runtime_state.get("last_stage_fingerprint_at"),
            "same_fingerprint_auto_turn_count": int(runtime_state.get("same_fingerprint_auto_turn_count") or 0),
            "pending_decisions": pending_decisions,
            "active_interactions": active_interactions,
            "recent_reply_threads": recent_reply_threads,
            "waiting_interaction_id": waiting_interaction_id,
            "latest_thread_interaction_id": latest_thread_interaction_id,
            "default_reply_interaction_id": default_reply_interaction_id or latest_thread_interaction_id,
            "pending_user_message_count": int(runtime_state.get("pending_user_message_count") or 0),
            "stop_reason": runtime_state.get("stop_reason"),
            "active_interaction_id": runtime_state.get("active_interaction_id"),
            "retry_state": runtime_state.get("retry_state"),
            "last_transition_at": runtime_state.get("last_transition_at"),
            "last_artifact_interact_at": runtime_state.get("last_artifact_interact_at"),
            "last_tool_activity_at": runtime_state.get("last_tool_activity_at"),
            "last_tool_activity_name": runtime_state.get("last_tool_activity_name"),
            "tool_calls_since_last_artifact_interact": int(runtime_state.get("tool_calls_since_last_artifact_interact") or 0),
            "seconds_since_last_artifact_interact": interaction_watchdog.get("seconds_since_last_artifact_interact"),
            "last_delivered_batch_id": runtime_state.get("last_delivered_batch_id"),
            "last_delivered_at": runtime_state.get("last_delivered_at"),
            "bound_conversations": self._binding_sources_payload(quest_root).get("sources") or ["local:default"],
            "created_at": quest_yaml.get("created_at"),
            "updated_at": quest_yaml.get("updated_at"),
            "branch": current_branch(workspace_root),
            "head": head_commit(workspace_root),
            "graph_svg_path": str(graph_svg) if graph_svg.exists() else None,
            "summary": {
                "status_line": status_line,
                "latest_metric": latest_metric,
                "latest_bash_session": latest_bash_session,
            },
            "paths": paths,
            "counts": counts,
            "interaction_watchdog": interaction_watchdog,
            "team": {"mode": "single", "active_workers": []},
            "cloud": {"linked": False, "base_url": "https://deepscientist.cc"},
            "history_count": len(history),
            "artifact_count": len(artifacts),
            "recent_artifacts": artifacts[-5:],
            "recent_runs": recent_runs[-5:],
            "paper_contract": paper_contract,
            "paper_evidence": paper_evidence,
            "analysis_inventory": analysis_inventory,
            "guidance": guidance,
        }
        with self._snapshot_cache_lock:
            self._snapshot_cache[cache_key] = {
                "state": state,
                "payload": copy.deepcopy(payload),
            }
        return payload

    def append_message(
        self,
        quest_id: str,
        role: str,
        content: str,
        source: str = "local",
        *,
        attachments: list[dict[str, Any]] | None = None,
        run_id: str | None = None,
        skill_id: str | None = None,
        reply_to_interaction_id: str | None = None,
        client_message_id: str | None = None,
    ) -> dict:
        quest_root = self._quest_root(quest_id)
        timestamp = utc_now()
        resolved_reply_to_interaction_id = str(reply_to_interaction_id or "").strip() or None
        record = {
            "id": generate_id("msg"),
            "role": role,
            "content": content,
            "source": source,
            "created_at": timestamp,
        }
        if isinstance(attachments, list) and attachments:
            record["attachments"] = [dict(item) for item in attachments if isinstance(item, dict)]
        if run_id:
            record["run_id"] = run_id
        if skill_id:
            record["skill_id"] = skill_id
        if client_message_id:
            record["client_message_id"] = str(client_message_id)
        if role == "user":
            record["delivery_state"] = "sent"
        interaction_state_path = quest_root / ".ds" / "interaction_state.json"
        interaction_state = self._read_interaction_state(quest_root)
        open_requests: list[dict] = []
        waiting_indexes: list[int] = []
        target_index: int | None = None
        target_thread_index: int | None = None
        if role == "user":
            self.bind_source(quest_id, source)
            open_requests = list(interaction_state.get("open_requests") or [])
            recent_threads = [dict(item) for item in (interaction_state.get("recent_threads") or [])]
            waiting_indexes = [index for index, item in enumerate(open_requests) if str(item.get("status") or "") == "waiting"]
            if resolved_reply_to_interaction_id:
                for index in waiting_indexes:
                    item = open_requests[index]
                    if resolved_reply_to_interaction_id in self._interaction_candidate_ids(item):
                        target_index = index
                        break
                for index, item in enumerate(recent_threads):
                    if resolved_reply_to_interaction_id in self._interaction_candidate_ids(item):
                        target_thread_index = index
                        break
            else:
                default_reply_target = str(interaction_state.get("default_reply_interaction_id") or "").strip() or self._default_reply_interaction_id(
                    open_requests=open_requests,
                    recent_threads=recent_threads,
                )
                if default_reply_target:
                    resolved_reply_to_interaction_id = default_reply_target
                    for index in waiting_indexes:
                        if default_reply_target in self._interaction_candidate_ids(open_requests[index]):
                            target_index = index
                            break
                    for index, item in enumerate(recent_threads):
                        if default_reply_target in self._interaction_candidate_ids(item):
                            target_thread_index = index
                            break
        if resolved_reply_to_interaction_id:
            record["reply_to_interaction_id"] = resolved_reply_to_interaction_id
        append_jsonl(quest_root / ".ds" / "conversations" / "main.jsonl", record)
        if role == "user":
            recent_threads = [dict(item) for item in (interaction_state.get("recent_threads") or [])]
            if target_thread_index is None and resolved_reply_to_interaction_id:
                for index, item in enumerate(recent_threads):
                    if resolved_reply_to_interaction_id in self._interaction_candidate_ids(item):
                        target_thread_index = index
                        break
            if target_thread_index is not None:
                thread = dict(recent_threads[target_thread_index])
                thread["reply_count"] = int(thread.get("reply_count") or 0) + 1
                thread["last_reply_message_id"] = record["id"]
                thread["last_reply_preview"] = content[:240]
                thread["last_reply_at"] = timestamp
                thread["updated_at"] = timestamp
                if str(thread.get("reply_mode") or "") == "blocking":
                    thread["status"] = "answered"
                recent_threads[target_thread_index] = thread
            if target_index is not None:
                request = dict(open_requests[target_index])
                request["status"] = "answered"
                request["answered_at"] = timestamp
                request["reply_message_id"] = record["id"]
                request["reply_preview"] = content[:240]
                open_requests[target_index] = request
                interaction_state["open_requests"] = open_requests
                interaction_state["last_reply_message_id"] = record["id"]
                interaction_state["recent_threads"] = recent_threads[-30:]
                interaction_state["default_reply_interaction_id"] = self._default_reply_interaction_id(
                    open_requests=open_requests,
                    recent_threads=interaction_state["recent_threads"],
                )
                if resolved_reply_to_interaction_id:
                    interaction_state["latest_thread_interaction_id"] = resolved_reply_to_interaction_id
                write_json(interaction_state_path, interaction_state)
                append_jsonl(
                    quest_root / ".ds" / "events.jsonl",
                    {
                        "type": "interaction.reply_received",
                        "quest_id": quest_id,
                        "interaction_id": resolved_reply_to_interaction_id,
                        "message_id": record["id"],
                        "reply_to_interaction_id": resolved_reply_to_interaction_id,
                        "source": source,
                        "content": content,
                        "created_at": timestamp,
                    },
                )
            elif waiting_indexes or target_thread_index is not None:
                interaction_state["last_reply_message_id"] = record["id"]
                interaction_state["recent_threads"] = recent_threads[-30:]
                interaction_state["default_reply_interaction_id"] = self._default_reply_interaction_id(
                    open_requests=open_requests,
                    recent_threads=interaction_state["recent_threads"],
                )
                if resolved_reply_to_interaction_id:
                    interaction_state["latest_thread_interaction_id"] = resolved_reply_to_interaction_id
                write_json(interaction_state_path, interaction_state)
            if resolved_reply_to_interaction_id and target_index is None and target_thread_index is not None:
                append_jsonl(
                    quest_root / ".ds" / "events.jsonl",
                    {
                        "type": "interaction.reply_received",
                        "quest_id": quest_id,
                        "interaction_id": resolved_reply_to_interaction_id,
                        "message_id": record["id"],
                        "reply_to_interaction_id": resolved_reply_to_interaction_id,
                        "source": source,
                        "content": content,
                        "created_at": timestamp,
                    },
                )
        append_jsonl(
            quest_root / ".ds" / "events.jsonl",
            {
                "type": "conversation.message",
                "quest_id": quest_id,
                "message_id": record["id"],
                "role": role,
                "source": source,
                "content": content,
                "run_id": run_id,
                "skill_id": skill_id,
                "reply_to_interaction_id": resolved_reply_to_interaction_id,
                "client_message_id": record.get("client_message_id"),
                "delivery_state": record.get("delivery_state"),
                "attachments": record.get("attachments") or [],
                "created_at": timestamp,
            },
        )
        if role == "user":
            self._enqueue_user_message(quest_root, record)
            self._write_active_user_requirements(
                quest_root,
                latest_requirement=record,
            )
            quest_data = read_yaml(quest_root / "quest.yaml", {})
            runtime_state = self._read_runtime_state(quest_root)
            status = str(runtime_state.get("status") or quest_data.get("status") or "")
            next_status = status
            if status == "waiting_for_user":
                interaction_state = read_json(quest_root / ".ds" / "interaction_state.json", {"open_requests": []})
                still_waiting = any(str(item.get("status") or "") == "waiting" for item in (interaction_state.get("open_requests") or []))
                if not still_waiting:
                    next_status = "running"
            elif status in {"stopped", "paused", "completed"}:
                next_status = "active"
            if next_status != status:
                self.update_runtime_state(
                    quest_root=quest_root,
                    status=next_status,
                    stop_reason=None,
                )
            else:
                self.update_runtime_state(
                    quest_root=quest_root,
                    pending_user_message_count=len((self._read_message_queue(quest_root).get("pending") or [])),
                )
        else:
            quest_data = read_yaml(quest_root / "quest.yaml", {})
            quest_data["updated_at"] = timestamp
            write_yaml(quest_root / "quest.yaml", quest_data)
        return record

    def mark_turn_started(self, quest_id: str, *, run_id: str, status: str = "running") -> dict:
        quest_root = self._quest_root(quest_id)
        self.update_runtime_state(
            quest_root=quest_root,
            status=status,
            active_run_id=run_id,
            stop_reason=None,
        )
        return self.snapshot(quest_id)

    def mark_turn_finished(
        self,
        quest_id: str,
        *,
        status: str | None = None,
        stop_reason: str | None | object = _UNSET,
    ) -> dict:
        quest_root = self._quest_root(quest_id)
        self.update_runtime_state(
            quest_root=quest_root,
            active_run_id=None,
            status=status if status is not None else _UNSET,
            stop_reason=stop_reason,
            retry_state=None,
        )
        return self.snapshot(quest_id)

    def mark_completed(
        self,
        quest_id: str,
        *,
        stop_reason: str = "completed_by_user_approval",
    ) -> dict:
        quest_root = self._quest_root(quest_id)
        self.update_runtime_state(
            quest_root=quest_root,
            status="completed",
            active_run_id=None,
            active_interaction_id=None,
            stop_reason=stop_reason,
        )
        return self.snapshot(quest_id)

    def bind_source(self, quest_id: str, source: str) -> dict:
        quest_root = self._quest_root(quest_id)
        bindings_path = quest_root / ".ds" / "bindings.json"
        existing_payload = read_json(bindings_path, {"sources": []})
        existing_sources = existing_payload.get("sources") if isinstance(existing_payload, dict) else []
        bindings = self._binding_sources_payload(quest_root)
        normalized_source = self._normalize_binding_source(source)
        seed_sources = list(existing_sources) if isinstance(existing_sources, list) else list(bindings.get("sources") or [])
        next_sources = self._normalized_binding_sources([*seed_sources, normalized_source])
        changed = list(bindings.get("sources") or []) != next_sources
        if changed:
            bindings["sources"] = next_sources
            write_json(bindings_path, bindings)
        return bindings

    def binding_sources(self, quest_id: str) -> list[str]:
        quest_root = self._quest_root(quest_id)
        return list(self._binding_sources_payload(quest_root).get("sources") or ["local:default"])

    def set_binding_sources(self, quest_id: str, sources: list[str]) -> dict:
        quest_root = self._quest_root(quest_id)
        bindings_path = quest_root / ".ds" / "bindings.json"
        payload = {"sources": self._normalized_binding_sources(sources)}
        write_json(bindings_path, payload)
        return payload

    def unbind_source(self, quest_id: str, source: str) -> dict:
        quest_root = self._quest_root(quest_id)
        bindings_path = quest_root / ".ds" / "bindings.json"
        bindings = self._binding_sources_payload(quest_root)
        normalized_source = self._normalize_binding_source(source)
        normalized_key = conversation_identity_key(normalized_source)
        changed = False
        sources: list[str] = []
        for item in list(bindings.get("sources") or []):
            existing = self._normalize_binding_source(str(item))
            if conversation_identity_key(existing) == normalized_key:
                changed = True
                continue
            sources.append(existing)
            if existing != item:
                changed = True
        normalized_sources = self._normalized_binding_sources(sources)
        if normalized_sources != list(bindings.get("sources") or []):
            changed = True
        if changed:
            bindings["sources"] = normalized_sources
            write_json(bindings_path, bindings)
        return bindings

    def set_status(self, quest_id: str, status: str) -> dict:
        quest_root = self._quest_root(quest_id)
        self.update_runtime_state(
            quest_root=quest_root,
            status=status,
            stop_reason=None if status not in {"stopped", "paused"} else _UNSET,
        )
        return self.snapshot(quest_id)

    def update_settings(
        self,
        quest_id: str,
        *,
        title: str | None = None,
        active_anchor: str | None = None,
        default_runner: str | None = None,
        workspace_mode: str | None = None,
    ) -> dict:
        quest_root = self._quest_root(quest_id)
        quest_yaml_path = self._quest_yaml_path(quest_root)
        if not quest_yaml_path.exists():
            raise FileNotFoundError(f"Unknown quest `{quest_id}`.")

        quest_data = self.read_quest_yaml(quest_root)
        changed = False
        research_state_updates: dict[str, Any] = {}
        runtime_state_updates: dict[str, Any] = {}

        if title is not None:
            normalized_title = str(title).strip()
            if not normalized_title:
                raise ValueError("Quest title cannot be empty.")
            if quest_data.get("title") != normalized_title:
                quest_data["title"] = normalized_title
                changed = True

        if active_anchor is not None:
            normalized_anchor = str(active_anchor).strip()
            if not normalized_anchor:
                raise ValueError("`active_anchor` cannot be empty.")
            from ..prompts.builder import current_standard_skills

            available_stage_skills = current_standard_skills(repo_root())
            if normalized_anchor not in available_stage_skills:
                allowed = ", ".join(available_stage_skills)
                raise ValueError(f"Unsupported active anchor `{normalized_anchor}`. Allowed values: {allowed}.")
            if quest_data.get("active_anchor") != normalized_anchor:
                quest_data["active_anchor"] = normalized_anchor
                changed = True

        if default_runner is not None:
            normalized_runner = str(default_runner).strip().lower()
            if not normalized_runner:
                raise ValueError("`default_runner` cannot be empty.")
            from ..runners import list_runner_names

            available_runners = set(list_runner_names()) or {"codex"}
            if normalized_runner not in available_runners:
                allowed = ", ".join(sorted(available_runners))
                raise ValueError(f"Unsupported runner `{normalized_runner}`. Available runners: {allowed}.")
            runners = ConfigManager(self.home).load_runners_config()
            runner_cfg = runners.get(normalized_runner, {}) if isinstance(runners.get(normalized_runner), dict) else {}
            if runner_cfg.get("enabled") is False:
                fallback = self._resolve_enabled_runner_name(normalized_runner)
                if fallback == normalized_runner:
                    raise ValueError(f"Runner `{normalized_runner}` is disabled and no enabled fallback runner is available.")
                normalized_runner = fallback
            if quest_data.get("default_runner") != normalized_runner:
                quest_data["default_runner"] = normalized_runner
                changed = True

        if workspace_mode is not None:
            normalized_workspace_mode = str(workspace_mode).strip().lower()
            if normalized_workspace_mode not in {"copilot", "autonomous"}:
                raise ValueError("Unsupported workspace mode. Allowed values: copilot, autonomous.")
            startup_contract = (
                dict(quest_data.get("startup_contract") or {})
                if isinstance(quest_data.get("startup_contract"), dict)
                else {}
            )
            if str(startup_contract.get("workspace_mode") or "").strip().lower() != normalized_workspace_mode:
                startup_contract["workspace_mode"] = normalized_workspace_mode
                quest_data["startup_contract"] = startup_contract
                changed = True
            if str(self.read_research_state(quest_root).get("workspace_mode") or "").strip().lower() != normalized_workspace_mode:
                research_state_updates["workspace_mode"] = normalized_workspace_mode
            runtime_state_updates["continuation_policy"] = (
                "wait_for_user_or_resume" if normalized_workspace_mode == "copilot" else "auto"
            )
            runtime_state_updates["continuation_reason"] = (
                "copilot_mode" if normalized_workspace_mode == "copilot" else "autonomous_mode"
            )

        if changed:
            quest_data["updated_at"] = utc_now()
            write_yaml(quest_yaml_path, quest_data)
        if research_state_updates:
            self.update_research_state(quest_root, **research_state_updates)
        if runtime_state_updates:
            self.update_runtime_state(quest_root=quest_root, **runtime_state_updates)

        return self.snapshot(quest_id)

    def update_baseline_state(
        self,
        quest_root: Path,
        *,
        baseline_gate: str | None = None,
        confirmed_baseline_ref: dict[str, Any] | None | object = _UNSET,
        active_anchor: str | None | object = _UNSET,
    ) -> dict[str, Any]:
        quest_yaml_path = self._quest_yaml_path(quest_root)
        if not quest_yaml_path.exists():
            raise FileNotFoundError(f"Unknown quest `{quest_root.name}`.")

        quest_data = self.read_quest_yaml(quest_root)
        changed = False

        if baseline_gate is not None:
            normalized_gate = self._normalize_baseline_gate(baseline_gate)
            if quest_data.get("baseline_gate") != normalized_gate:
                quest_data["baseline_gate"] = normalized_gate
                changed = True

        if confirmed_baseline_ref is not _UNSET:
            normalized_ref = dict(confirmed_baseline_ref) if isinstance(confirmed_baseline_ref, dict) else None
            if quest_data.get("confirmed_baseline_ref") != normalized_ref:
                quest_data["confirmed_baseline_ref"] = normalized_ref
                changed = True

        if active_anchor is not _UNSET:
            normalized_anchor = str(active_anchor or "").strip()
            if not normalized_anchor:
                raise ValueError("`active_anchor` cannot be empty.")
            from ..prompts.builder import current_standard_skills

            available_stage_skills = current_standard_skills(repo_root())
            if normalized_anchor not in available_stage_skills:
                allowed = ", ".join(available_stage_skills)
                raise ValueError(f"Unsupported active anchor `{normalized_anchor}`. Allowed values: {allowed}.")
            if quest_data.get("active_anchor") != normalized_anchor:
                quest_data["active_anchor"] = normalized_anchor
                changed = True

        if changed:
            quest_data["updated_at"] = utc_now()
            write_yaml(quest_yaml_path, quest_data)
        return quest_data

    def update_startup_context(
        self,
        quest_root: Path,
        *,
        requested_baseline_ref: dict[str, Any] | None | object = _UNSET,
        startup_contract: dict[str, Any] | None | object = _UNSET,
    ) -> dict[str, Any]:
        quest_yaml_path = self._quest_yaml_path(quest_root)
        if not quest_yaml_path.exists():
            raise FileNotFoundError(f"Unknown quest `{quest_root.name}`.")

        quest_data = self.read_quest_yaml(quest_root)
        changed = False

        if requested_baseline_ref is not _UNSET:
            normalized_requested = (
                dict(requested_baseline_ref) if isinstance(requested_baseline_ref, dict) else None
            )
            if quest_data.get("requested_baseline_ref") != normalized_requested:
                quest_data["requested_baseline_ref"] = normalized_requested
                changed = True

        if startup_contract is not _UNSET:
            normalized_contract = dict(startup_contract) if isinstance(startup_contract, dict) else None
            if quest_data.get("startup_contract") != normalized_contract:
                quest_data["startup_contract"] = normalized_contract
                changed = True

        if changed:
            quest_data["updated_at"] = utc_now()
            write_yaml(quest_yaml_path, quest_data)
        return quest_data

    def reconcile_runtime_state(self) -> list[dict[str, Any]]:
        reconciled: list[dict[str, Any]] = []
        if not self.quests_root.exists():
            return reconciled
        for quest_yaml_path in sorted(self.quests_root.glob("*/quest.yaml")):
            quest_root = quest_yaml_path.parent
            quest_data = read_yaml(quest_yaml_path, {})
            runtime_state = self._read_runtime_state(quest_root)
            status = str(runtime_state.get("status") or quest_data.get("status") or "").strip()
            active_run_id = str(runtime_state.get("active_run_id") or quest_data.get("active_run_id") or "").strip()
            if not active_run_id and status != "running":
                continue
            previous_status = status or "running"
            last_transition_at = self._runtime_recovery_timestamp(runtime_state, quest_data)
            recoverable = self._runtime_recovery_eligible(
                previous_status=previous_status,
                active_run_id=active_run_id or None,
                last_transition_at=last_transition_at,
            )
            # Reconcile continuation_policy with current workspace_mode so that
            # a mode switch that happened before/during the crash is respected.
            research_state = self.read_research_state(quest_root)
            workspace_mode = str(research_state.get("workspace_mode") or "").strip().lower()
            current_policy = str(runtime_state.get("continuation_policy") or "").strip().lower()
            reconciled_policy_updates: dict[str, Any] = {}
            if workspace_mode == "autonomous" and current_policy == "wait_for_user_or_resume":
                reconciled_policy_updates["continuation_policy"] = "auto"
                reconciled_policy_updates["continuation_reason"] = "autonomous_mode_reconciled"
                reconciled_policy_updates["continuation_updated_at"] = utc_now()
            elif workspace_mode == "copilot" and current_policy == "auto":
                reconciled_policy_updates["continuation_policy"] = "wait_for_user_or_resume"
                reconciled_policy_updates["continuation_reason"] = "copilot_mode_reconciled"
                reconciled_policy_updates["continuation_updated_at"] = utc_now()
            self.update_runtime_state(
                quest_root=quest_root,
                status="stopped",
                active_run_id=None,
                stop_reason="crash_recovered",
                **reconciled_policy_updates,
            )
            summary = (
                f"Recovered quest from stale runtime state; previous status `{previous_status}`"
                + (f", abandoned run `{active_run_id}`." if active_run_id else ".")
            )
            if recoverable:
                summary = f"{summary} Auto-resume is eligible within the 24-hour recovery window."
            append_jsonl(
                quest_root / ".ds" / "events.jsonl",
                {
                    "event_id": generate_id("evt"),
                    "type": "quest.runtime_reconciled",
                    "quest_id": quest_root.name,
                    "previous_status": previous_status,
                    "abandoned_run_id": active_run_id or None,
                    "last_transition_at": last_transition_at,
                    "recoverable": recoverable,
                    "status": "stopped",
                    "summary": summary,
                    "created_at": utc_now(),
                },
            )
            reconciled.append(
                {
                    "quest_id": quest_root.name,
                    "previous_status": previous_status,
                    "abandoned_run_id": active_run_id or None,
                    "last_transition_at": last_transition_at,
                    "recoverable": recoverable,
                    "status": "stopped",
                }
            )
        return reconciled

    @staticmethod
    def _parse_runtime_timestamp(value: Any) -> datetime | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        candidate = normalized.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _runtime_recovery_timestamp(self, runtime_state: dict[str, Any], quest_data: dict[str, Any]) -> str | None:
        for candidate in (
            runtime_state.get("last_transition_at"),
            quest_data.get("updated_at"),
            quest_data.get("created_at"),
        ):
            parsed = self._parse_runtime_timestamp(candidate)
            if parsed is None:
                continue
            return parsed.isoformat()
        return None

    def _runtime_recovery_eligible(
        self,
        *,
        previous_status: str,
        active_run_id: str | None,
        last_transition_at: str | None,
    ) -> bool:
        if previous_status != "running" and not str(active_run_id or "").strip():
            return False
        parsed = self._parse_runtime_timestamp(last_transition_at)
        if parsed is None:
            return False
        return datetime.now(UTC) - parsed <= _CRASH_AUTO_RESUME_WINDOW

    def history(self, quest_id: str, limit: int = 100) -> list[dict]:
        return self._read_cached_jsonl(self._quest_root(quest_id) / ".ds" / "conversations" / "main.jsonl")[-limit:]

    def workflow(self, quest_id: str) -> dict:
        return self._projected_payload(quest_id, "details")

    def events(
        self,
        quest_id: str,
        *,
        after: int = 0,
        before: int | None = None,
        limit: int = 200,
        tail: bool = False,
    ) -> dict:
        event_path = self._quest_root(quest_id) / ".ds" / "events.jsonl"
        normalized_limit = max(limit, 0)
        direction = "after"
        if before is not None:
            direction = "before"
        elif tail and normalized_limit > 0:
            direction = "tail"
        sliced_records, total_records, has_more = self._read_jsonl_cursor_slice(
            event_path,
            after=after,
            before=before,
            limit=normalized_limit,
            tail=tail,
        )
        enriched = []
        for cursor, item in sliced_records:
            enriched.append(
                {
                    "cursor": cursor,
                    "event_id": item.get("event_id") or f"evt-{quest_id}-{cursor}",
                    **item,
                }
            )
        if before is not None:
            next_cursor = enriched[-1]["cursor"] if enriched else max(min(int(before or 0) - 1, total_records), 0)
        elif tail:
            next_cursor = total_records
        else:
            next_cursor = enriched[-1]["cursor"] if enriched else max(int(after or 0), 0)
        oldest_cursor = enriched[0]["cursor"] if enriched else None
        newest_cursor = enriched[-1]["cursor"] if enriched else None
        return {
            "quest_id": quest_id,
            "cursor": next_cursor,
            "has_more": has_more,
            "oldest_cursor": oldest_cursor,
            "newest_cursor": newest_cursor,
            "direction": direction,
            "events": enriched,
        }

    def artifacts(self, quest_id: str) -> dict:
        quest_root = self._quest_root(quest_id)
        return {
            "quest_id": quest_id,
            "items": self._collect_artifacts(quest_root),
        }

    def node_traces(self, quest_id: str, *, selection_type: str | None = None) -> dict:
        quest_root = self._quest_root(quest_id)
        workflow = self.workflow(quest_id)
        snapshot = self.snapshot(quest_id)
        payload = QuestNodeTraceManager(quest_root).materialize(
            quest_id=quest_id,
            workflow=workflow,
            snapshot=snapshot,
        )
        items = list(payload.get("items") or [])
        if selection_type:
            normalized = selection_type.strip()
            items = [item for item in items if str(item.get("selection_type") or "") == normalized]
        return {
            "quest_id": quest_id,
            "generated_at": payload.get("generated_at"),
            "materialized_path": str(QuestNodeTraceManager(quest_root).materialized_path),
            "items": items,
        }

    def node_trace(self, quest_id: str, selection_ref: str, *, selection_type: str | None = None) -> dict:
        payload = self.node_traces(quest_id, selection_type=selection_type)
        normalized_ref = str(selection_ref or "").strip()
        normalized_type = str(selection_type or "").strip()
        for item in payload.get("items") or []:
            item_ref = str(item.get("selection_ref") or "").strip()
            item_type = str(item.get("selection_type") or "").strip()
            if item_ref != normalized_ref:
                continue
            if normalized_type and item_type != normalized_type:
                continue
            return {
                "quest_id": quest_id,
                "generated_at": payload.get("generated_at"),
                "materialized_path": payload.get("materialized_path"),
                "trace": item,
            }
        raise FileNotFoundError(f"Unknown node trace `{selection_ref}`.")

    def stage_view(self, quest_id: str, selection: dict[str, Any] | None = None) -> dict[str, Any]:
        quest_root = self._quest_root(quest_id)
        resolved_selection = dict(selection or {})
        selection_ref = str(resolved_selection.get("selection_ref") or "").strip()
        selection_type = str(resolved_selection.get("selection_type") or "stage_node").strip() or None
        if (
            selection_type == "branch_node"
            and selection_ref
            and not str(resolved_selection.get("branch_name") or "").strip()
        ):
            resolved_selection["branch_name"] = selection_ref
        trace = None
        if selection_ref:
            try:
                trace_payload = self.node_trace(quest_id, selection_ref, selection_type=selection_type)
                trace = trace_payload.get("trace") if isinstance(trace_payload, dict) else None
            except FileNotFoundError:
                trace = None
        return QuestStageViewBuilder(
            self,
            quest_root,
            snapshot=self.snapshot(quest_id),
            selection=resolved_selection,
            trace=trace if isinstance(trace, dict) else None,
        ).build()

    def metrics_timeline(self, quest_id: str) -> dict:
        quest_root = self._quest_root(quest_id)
        workspace_root = self.active_workspace_root(quest_root)
        state = self._json_compatible_state(self._metrics_timeline_state(quest_root, workspace_root))
        cache_path = self._metrics_timeline_cache_path(quest_root)
        cache_schema_version = 2
        cached = self._read_cached_json(cache_path, {})
        if (
            isinstance(cached, dict)
            and int(cached.get("schema_version") or 0) == cache_schema_version
            and self._json_compatible_state(cached.get("state")) == state
            and isinstance(cached.get("payload"), dict)
        ):
            return dict(cached.get("payload") or {})

        with advisory_file_lock(self._metrics_timeline_cache_lock_path(quest_root)):
            cached = read_json(cache_path, {})
            if (
                isinstance(cached, dict)
                and int(cached.get("schema_version") or 0) == cache_schema_version
                and self._json_compatible_state(cached.get("state")) == state
                and isinstance(cached.get("payload"), dict)
            ):
                return dict(cached.get("payload") or {})

            attachment = self._active_baseline_attachment(quest_root, workspace_root)
            baseline_entry = dict(attachment.get("entry") or {}) if isinstance(attachment, dict) else None
            selected_variant_id = (
                str(attachment.get("source_variant_id") or "").strip() or None if isinstance(attachment, dict) else None
            )
            if not baseline_entry:
                latest_baseline_payload = None
                for item in reversed(self._collect_artifacts_raw(quest_root)):
                    if str(item.get("kind") or "").strip() != "baselines":
                        continue
                    payload = item.get("payload") or {}
                    if not isinstance(payload, dict):
                        continue
                    if str(payload.get("status") or "").strip().lower() != "confirmed":
                        continue
                    latest_baseline_payload = payload
                    break
                if isinstance(latest_baseline_payload, dict) and latest_baseline_payload:
                    baseline_entry = dict(latest_baseline_payload)
                    selected_variant_id = (
                        str(latest_baseline_payload.get("baseline_variant_id") or "").strip() or None
                    )
            run_records = [
                item.get("payload") or {}
                for item in self._collect_run_artifacts_raw(quest_root, run_kind="main_experiment")
                if isinstance(item.get("payload"), dict)
            ]
            payload = build_metrics_timeline(
                quest_id=quest_id,
                run_records=run_records,
                baseline_entry=baseline_entry,
                selected_variant_id=selected_variant_id,
            )
            write_json(
                cache_path,
                {
                    "schema_version": cache_schema_version,
                    "generated_at": utc_now(),
                    "state": state,
                    "payload": payload,
                },
            )
            return payload

    def baseline_compare(self, quest_id: str) -> dict:
        quest_root = self._quest_root(quest_id)
        workspace_root = self.active_workspace_root(quest_root)
        state = self._json_compatible_state(self._baseline_compare_state(quest_root, workspace_root))
        cache_path = self._baseline_compare_cache_path(quest_root)
        cache_schema_version = 1
        cached = self._read_cached_json(cache_path, {})
        if (
            isinstance(cached, dict)
            and int(cached.get("schema_version") or 0) == cache_schema_version
            and self._json_compatible_state(cached.get("state")) == state
            and isinstance(cached.get("payload"), dict)
        ):
            return dict(cached.get("payload") or {})

        with advisory_file_lock(self._baseline_compare_cache_lock_path(quest_root)):
            cached = read_json(cache_path, {})
            if (
                isinstance(cached, dict)
                and int(cached.get("schema_version") or 0) == cache_schema_version
                and self._json_compatible_state(cached.get("state")) == state
                and isinstance(cached.get("payload"), dict)
            ):
                return dict(cached.get("payload") or {})

            quest_data = self.read_quest_yaml(quest_root)
            confirmed_ref = (
                dict(quest_data.get("confirmed_baseline_ref") or {})
                if isinstance(quest_data.get("confirmed_baseline_ref"), dict)
                else {}
            )
            attachment = self._active_baseline_attachment(quest_root, workspace_root)
            active_baseline_id = (
                str(confirmed_ref.get("baseline_id") or "").strip()
                or (str(attachment.get("source_baseline_id") or "").strip() if isinstance(attachment, dict) else "")
                or None
            )
            active_variant_id = (
                str(confirmed_ref.get("variant_id") or "").strip()
                or (str(attachment.get("source_variant_id") or "").strip() if isinstance(attachment, dict) else "")
                or None
            )
            payload = build_baseline_compare_payload(
                quest_id=quest_id,
                baseline_entries=self._baseline_compare_entries(quest_root, workspace_root),
                active_baseline_id=active_baseline_id,
                active_variant_id=active_variant_id,
            )
            write_json(
                cache_path,
                {
                    "schema_version": cache_schema_version,
                    "state": state,
                    "payload": payload,
                },
            )
            return payload

    def list_documents(self, quest_id: str) -> list[dict]:
        quest_root = self._require_initialized_quest_root(quest_id)
        workspace_root = self.active_workspace_root(quest_root)
        documents = []
        for relative in ("brief.md", "plan.md", "status.md", "SUMMARY.md"):
            path = workspace_root / relative
            documents.append(
                {
                    "document_id": relative,
                    "title": relative,
                    "path": str(path),
                    "kind": "markdown",
                    "writable": True,
                    "source_scope": "quest",
                }
            )
        for path in sorted((workspace_root / "memory").glob("**/*.md")):
            relative = path.relative_to(workspace_root / "memory").as_posix()
            documents.append(
                {
                    "document_id": f"memory::{relative}",
                    "title": path.name,
                    "path": str(path),
                    "kind": "markdown",
                    "writable": True,
                    "source_scope": "quest_memory",
                }
            )
        skills_root = repo_root() / "src" / "skills"
        for skill_md in sorted(skills_root.glob("*/SKILL.md")):
            if skill_md.parent.name.startswith("."):
                continue
            relative = skill_md.relative_to(skills_root).as_posix()
            documents.append(
                {
                    "document_id": f"skill::{relative}",
                    "title": relative,
                    "path": str(skill_md),
                    "kind": "markdown",
                    "writable": False,
                    "source_scope": "skill",
                }
            )
        return documents

    def explorer(
        self,
        quest_id: str,
        revision: str | None = None,
        mode: str | None = None,
        profile: str | None = None,
    ) -> dict:
        if revision:
            return self._revision_explorer(quest_id, revision=revision, mode=mode or "ref")

        quest_root = self._require_initialized_quest_root(quest_id)
        workspace_root = self.active_workspace_root(quest_root)
        git_status = self._git_status_map(workspace_root)

        root_nodes = self._tree_children(
            workspace_root,
            workspace_root,
            git_status=git_status,
            changed_paths={},
            profile=profile,
        )
        sections = self._group_explorer_sections(root_nodes)

        return {
            "quest_id": quest_id,
            "quest_root": str(workspace_root.resolve()),
            "view": {
                "mode": "live",
                "revision": None,
                "label": "Latest",
                "read_only": False,
                "profile": profile,
            },
            "sections": sections,
        }

    def search_files(self, quest_id: str, term: str, limit: int = 50) -> dict[str, Any]:
        query = self._normalize_explorer_search_query(term)
        normalized_query = query.casefold()
        workspace_root = self.active_workspace_root(self._require_initialized_quest_root(quest_id))
        resolved_limit = max(1, min(limit, 200))
        if not normalized_query:
            return {
                "quest_id": quest_id,
                "query": query,
                "items": [],
                "limit": resolved_limit,
                "truncated": False,
                "files_scanned": 0,
            }

        items: list[dict[str, Any]] = []
        files_scanned = 0
        truncated = False
        max_file_size = 1_000_000

        for path in sorted(workspace_root.rglob("*")):
            try:
                if not path.is_file() or self._skip_explorer_path(workspace_root, path):
                    continue
            except OSError:
                continue

            relative = path.relative_to(workspace_root).as_posix()
            scope, writable = self._classify_path_scope(workspace_root, path)
            path_haystack = relative.casefold()
            name_haystack = path.name.casefold()
            if normalized_query in path_haystack or normalized_query in name_haystack:
                haystack = path_haystack
                match_spans: list[dict[str, int]] = []
                start = 0
                while True:
                    found = haystack.find(normalized_query, start)
                    if found < 0:
                        break
                    match_spans.append({"start": found, "end": found + len(query)})
                    start = found + max(1, len(query))
                renderer_hint, mime_type = self._renderer_hint_for(path)
                items.append(
                    {
                        "id": f"{relative}:path",
                        "document_id": f"path::{relative}",
                        "title": path.name,
                        "path": relative,
                        "scope": scope,
                        "writable": writable,
                        "line_number": 0,
                        "line_text": relative,
                        "snippet": relative[:320],
                        "match_spans": match_spans,
                        "open_kind": renderer_hint,
                        "mime_type": mime_type,
                    }
                )
                if len(items) >= resolved_limit:
                    truncated = True
                    break

            renderer_hint, mime_type = self._renderer_hint_for(path)
            if not self._is_text_document(path, mime_type, renderer_hint):
                continue

            try:
                size_bytes = path.stat().st_size
            except OSError:
                continue
            if size_bytes > max_file_size:
                continue

            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
            except OSError:
                continue

            files_scanned += 1

            for line_index, line in enumerate(content.splitlines(), start=1):
                haystack = line.casefold()
                if normalized_query not in haystack:
                    continue
                match_spans: list[dict[str, int]] = []
                start = 0
                while True:
                    found = haystack.find(normalized_query, start)
                    if found < 0:
                        break
                    match_spans.append({"start": found, "end": found + len(query)})
                    start = found + max(1, len(query))

                snippet = line.strip() or line
                items.append(
                    {
                        "id": f"{relative}:{line_index}",
                        "document_id": f"path::{relative}",
                        "title": path.name,
                        "path": relative,
                        "scope": scope,
                        "writable": writable,
                        "line_number": line_index,
                        "line_text": line,
                        "snippet": snippet[:320],
                        "match_spans": match_spans,
                        "open_kind": renderer_hint,
                        "mime_type": mime_type,
                    }
                )
                if len(items) >= resolved_limit:
                    truncated = True
                    break
            if truncated:
                break

        return {
            "quest_id": quest_id,
            "query": query,
            "items": items,
            "limit": resolved_limit,
            "truncated": truncated,
            "files_scanned": files_scanned,
        }

    @staticmethod
    def _normalize_explorer_search_query(term: str) -> str:
        query = str(term or "").strip()
        if len(query) >= 2 and query.startswith("*") and query.endswith("*"):
            inner = query.strip("*").strip()
            if inner and not any(marker in inner for marker in "*?[]"):
                return inner
        return query

    def open_document(self, quest_id: str, document_id: str) -> dict:
        quest_root = self._require_initialized_quest_root(quest_id)
        workspace_root = self.active_workspace_root(quest_root)
        if document_id.startswith("git::"):
            revision, relative = self._parse_git_document_id(document_id)
            if not self._git_revision_exists(quest_root, revision):
                raise FileNotFoundError(f"Unknown git revision `{revision}`.")
            renderer_hint, mime_type = self._renderer_hint_for(Path(relative))
            is_text = self._is_text_document(Path(relative), mime_type, renderer_hint)
            content = self._read_git_text(quest_root, revision, relative) if is_text else ""
            blob_id = self._git_blob_id(quest_root, revision, relative)
            size_bytes = self._git_blob_size(quest_root, revision, relative)
            return {
                "document_id": document_id,
                "quest_id": quest_id,
                "title": Path(relative).name,
                "path": relative,
                "kind": "markdown" if renderer_hint == "markdown" else renderer_hint,
                "scope": "git_snapshot",
                "writable": False,
                "encoding": "utf-8" if is_text else None,
                "source_scope": "git_snapshot",
                "content": content,
                "revision": f"git:{revision}:{blob_id or sha256_text(content)}",
                "updated_at": utc_now(),
                "mime_type": mime_type,
                "size_bytes": size_bytes,
                "asset_url": f"/api/quests/{quest_id}/documents/asset?document_id={quote(document_id, safe='')}",
                "meta": {
                    "tags": [Path(relative).stem],
                    "source_kind": "git_snapshot",
                    "renderer_hint": renderer_hint,
                    "git_revision": revision,
                    "git_path": relative,
                },
            }

        shared_source_quest_id = None
        parsed_shared_memory = self._parse_shared_memory_document_id(document_id)
        if parsed_shared_memory is not None:
            shared_source_quest_id = parsed_shared_memory[0]
        path, writable, scope, source_kind = self.resolve_document(quest_id, document_id)
        renderer_hint, mime_type = self._renderer_hint_for(path)
        is_text = self._is_text_document(path, mime_type, renderer_hint)
        content = read_text(path) if is_text else ""
        revision = f"sha256:{sha256_text(content)}" if is_text else f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
        payload = {
            "document_id": document_id,
            "quest_id": quest_id,
            "title": path.name if "::" in document_id else document_id,
            "path": str(path),
            "kind": "markdown" if renderer_hint == "markdown" else renderer_hint,
            "scope": scope,
            "writable": writable,
            "encoding": "utf-8" if is_text else None,
            "source_scope": source_kind,
            "content": content,
            "revision": revision,
            "updated_at": utc_now(),
            "mime_type": mime_type,
            "size_bytes": path.stat().st_size,
            "asset_url": f"/api/quests/{quest_id}/documents/asset?document_id={quote(document_id, safe='')}",
            "meta": {
                "tags": [path.stem],
                "source_kind": source_kind,
                "renderer_hint": renderer_hint,
            },
        }
        if shared_source_quest_id:
            payload["source_quest_id"] = shared_source_quest_id
            if isinstance(payload.get("meta"), dict):
                payload["meta"]["source_quest_id"] = shared_source_quest_id
                payload["meta"]["shared"] = True
        return payload

    def resolve_document(self, quest_id: str, document_id: str) -> tuple[Path, bool, str, str]:
        quest_root = self._require_initialized_quest_root(quest_id)
        if document_id.startswith(_SHARED_MEMORY_DOCUMENT_PREFIX):
            return self._resolve_shared_memory_document(document_id)
        workspace_root = self.active_workspace_root(quest_root)
        resolution_root = self._document_resolution_root(
            quest_root=quest_root,
            workspace_root=workspace_root,
            document_id=document_id,
        )
        try:
            return self._resolve_document(resolution_root, document_id)
        except FileNotFoundError:
            legacy_relative = None
            if document_id.startswith("path::"):
                legacy_relative = document_id.split("::", 1)[1].lstrip("/")
            if legacy_relative and legacy_relative.startswith("literature/arxiv/"):
                return self._resolve_document(quest_root, f"questpath::{legacy_relative}")
            raise

    def _resolve_shared_memory_document(self, document_id: str) -> tuple[Path, bool, str, str]:
        parsed = self._parse_shared_memory_document_id(document_id)
        if parsed is None:
            raise FileNotFoundError(f"Unknown shared memory document `{document_id}`.")
        source_quest_id, relative = parsed
        source_quest_root = self._require_initialized_quest_root(source_quest_id)
        root = (source_quest_root / "memory").resolve()
        path = (root / relative).resolve()
        if path != root and root not in path.parents:
            raise ValueError("Document ID escapes shared quest memory.")
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Unknown shared quest memory `{source_quest_id}:{relative}`.")
        return path, False, "shared_quest_memory", "shared_quest_memory"

    @staticmethod
    def _parse_shared_memory_document_id(document_id: str) -> tuple[str, str] | None:
        raw = str(document_id or "").strip()
        if not raw.startswith(_SHARED_MEMORY_DOCUMENT_PREFIX):
            return None
        _prefix, source_quest_id, relative = (raw.split("::", 2) + ["", "", ""])[:3]
        source_quest_id = source_quest_id.strip()
        relative = relative.lstrip("/")
        if not source_quest_id or not relative:
            return None
        return source_quest_id, relative

    def save_document(self, quest_id: str, document_id: str, content: str, previous_revision: str | None = None) -> dict:
        current = self.open_document(quest_id, document_id)
        if not current.get("writable", False):
            return {
                "ok": False,
                "conflict": False,
                "message": "Document is read-only.",
                "document_id": document_id,
                "saved_at": utc_now(),
                "updated_payload": current,
            }
        current_revision = current["revision"]
        if previous_revision and previous_revision != current_revision:
            return {
                "ok": False,
                "conflict": True,
                "message": "Document changed since it was opened.",
                "current_revision": current_revision,
                "document_id": document_id,
                "saved_at": utc_now(),
                "updated_payload": current,
            }
        path = Path(current["path"])
        write_text(path, content)
        new_revision = f"sha256:{sha256_text(content)}"
        return {
            "ok": True,
            "document_id": document_id,
            "quest_id": quest_id,
            "conflict": False,
            "path": str(path),
            "saved_at": utc_now(),
            "revision": new_revision,
            "updated_payload": self.open_document(quest_id, document_id),
        }

    @staticmethod
    def _document_relative_path(document_id: str) -> tuple[str | None, str | None]:
        if document_id.startswith("git::"):
            _prefix, revision, relative = (document_id.split("::", 2) + ["", "", ""])[:3]
            return relative.lstrip("/") or None, revision or None
        if document_id.startswith("path::"):
            return document_id.split("::", 1)[1].lstrip("/") or None, None
        if document_id.startswith("questpath::"):
            return document_id.split("::", 1)[1].lstrip("/") or None, None
        if document_id.startswith("memory::"):
            relative = document_id.split("::", 1)[1].lstrip("/")
            return f"memory/{relative}" if relative else None, None
        if document_id.startswith("skill::"):
            return None, None
        if "/" in document_id or document_id.startswith("."):
            return None, None
        return document_id, None

    @staticmethod
    def _path_to_document_id(
        path: str | Path | None,
        *,
        quest_root: Path,
        workspace_root: Path,
    ) -> str | None:
        if not path:
            return None
        try:
            candidate = Path(path).expanduser()
            if not candidate.is_absolute():
                candidate = (workspace_root / candidate).resolve()
            else:
                candidate = candidate.resolve()
        except OSError:
            return None

        try:
            relative_to_workspace = candidate.relative_to(workspace_root.resolve()).as_posix()
            return f"path::{relative_to_workspace}"
        except ValueError:
            pass

        try:
            relative_to_quest = candidate.relative_to(quest_root.resolve()).as_posix()
            return f"questpath::{relative_to_quest}"
        except ValueError:
            return None

    @staticmethod
    def _markdown_asset_directory(relative_path: str) -> PurePosixPath:
        base_path = PurePosixPath(relative_path)
        return base_path.parent / f"{base_path.stem}.assets"

    @staticmethod
    def _relative_path_from_base(base_file: str, target_path: str) -> str:
        base_dir_parts = PurePosixPath(base_file).parent.parts
        target_parts = PurePosixPath(target_path).parts
        common = 0
        max_common = min(len(base_dir_parts), len(target_parts))
        while common < max_common and base_dir_parts[common] == target_parts[common]:
            common += 1
        up_parts = [".."] * (len(base_dir_parts) - common)
        down_parts = list(target_parts[common:])
        joined = "/".join([*up_parts, *down_parts]).strip("/")
        return joined or PurePosixPath(target_path).name

    def save_document_asset(
        self,
        quest_id: str,
        document_id: str,
        *,
        file_name: str,
        mime_type: str | None,
        content: bytes,
        kind: str = "image",
    ) -> dict:
        quest_root = self._quest_root(quest_id)
        workspace_root = self.active_workspace_root(quest_root)
        current = self.open_document(quest_id, document_id)
        if not current.get("writable", False):
            return {
                "ok": False,
                "message": "Document is read-only.",
                "document_id": document_id,
            }
        base_relative, revision = self._document_relative_path(document_id)
        if revision:
            return {
                "ok": False,
                "message": "Cannot upload assets into a git snapshot document.",
                "document_id": document_id,
            }
        if not base_relative:
            return {
                "ok": False,
                "message": "Document path is required for asset uploads.",
                "document_id": document_id,
            }
        base_path = Path(str(current.get("path") or ""))
        suffix = base_path.suffix.lower()
        if suffix not in {".md", ".markdown", ".mdx"}:
            return {
                "ok": False,
                "message": "Assets can only be attached to markdown documents.",
                "document_id": document_id,
            }
        original_name = Path(file_name).name
        original_suffix = Path(original_name).suffix.lower()
        guessed_suffix = mimetypes.guess_extension(mime_type or "") or ""
        asset_suffix = original_suffix or guessed_suffix or ".bin"
        if asset_suffix == ".jpe":
            asset_suffix = ".jpg"
        safe_stem = slugify(Path(original_name).stem or kind, default=kind)
        asset_name = f"{safe_stem}-{generate_id('asset').split('-', 1)[1]}{asset_suffix}"
        asset_relative_dir = self._markdown_asset_directory(base_relative)
        asset_relative = (asset_relative_dir / asset_name).as_posix()
        asset_root = (
            quest_root
            if document_id.startswith(("questpath::", "memory::"))
            else workspace_root
        )
        asset_path = resolve_within(asset_root, asset_relative)
        ensure_dir(asset_path.parent)
        asset_path.write_bytes(content)
        asset_document_scope = "questpath" if document_id.startswith(("questpath::", "memory::")) else "path"
        asset_document_id = f"{asset_document_scope}::{asset_relative}"
        relative_markdown_path = self._relative_path_from_base(base_relative, asset_relative)
        return {
            "ok": True,
            "quest_id": quest_id,
            "document_id": document_id,
            "asset_document_id": asset_document_id,
            "asset_path": str(asset_path),
            "relative_path": relative_markdown_path,
            "asset_url": f"/api/quests/{quest_id}/documents/asset?document_id={quote(asset_document_id, safe='')}",
            "mime_type": mimetypes.guess_type(asset_path.name)[0] or mime_type or "application/octet-stream",
            "kind": kind,
            "saved_at": utc_now(),
        }

    def save_chat_attachment_draft(
        self,
        quest_id: str,
        *,
        file_name: str,
        mime_type: str | None,
        content: bytes,
        draft_id: str | None = None,
    ) -> dict[str, Any]:
        quest_root = self._quest_root(quest_id)
        normalized_draft_id = slugify(str(draft_id or generate_id("draft")), default=generate_id("draft"))
        draft_root = self._chat_attachment_draft_root(quest_root, normalized_draft_id)
        original_name = Path(file_name).name or "attachment.bin"
        suffix = Path(original_name).suffix.lower()
        if not suffix:
            guessed_suffix = mimetypes.guess_extension(mime_type or "", strict=False) or ""
            suffix = ".jpg" if guessed_suffix == ".jpe" else guessed_suffix
        safe_stem = slugify(Path(original_name).stem or "attachment", default="attachment")
        stored_name = f"{safe_stem}{suffix or '.bin'}"
        asset_path = resolve_within(draft_root, stored_name)
        if draft_root.exists():
            for child in draft_root.iterdir():
                if child.is_file():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
        ensure_dir(draft_root)
        asset_path.write_bytes(content)
        quest_relative_path = asset_path.relative_to(quest_root).as_posix()
        asset_document_id = f"path::{quest_relative_path}"
        attachment = self._chat_attachment_payload(
            quest_id=quest_id,
            name=original_name,
            stored_name=stored_name,
            mime_type=mime_type,
            asset_path=asset_path,
            draft_id=normalized_draft_id,
        )
        attachment["status"] = "success"
        write_json(
            draft_root / "manifest.json",
            {
                "draft_id": normalized_draft_id,
                "quest_id": quest_id,
                "created_at": utc_now(),
                "attachment": attachment,
                "asset_document_id": asset_document_id,
            },
        )
        return {
            "ok": True,
            "quest_id": quest_id,
            "draft_id": normalized_draft_id,
            **attachment,
        }

    def delete_chat_attachment_draft(self, quest_id: str, *, draft_id: str) -> dict[str, Any]:
        self._quest_root(quest_id)
        normalized_draft_id = slugify(str(draft_id or "").strip(), default="")
        if not normalized_draft_id:
            return {"ok": False, "message": "`draft_id` is required."}
        draft_root = self._chat_attachment_draft_root(self._quest_root(quest_id), normalized_draft_id)
        if not draft_root.exists():
            return {
                "ok": True,
                "status": "already_deleted",
                "quest_id": quest_id,
                "draft_id": normalized_draft_id,
            }
        shutil.rmtree(draft_root, ignore_errors=True)
        return {
            "ok": True,
            "status": "deleted",
            "quest_id": quest_id,
            "draft_id": normalized_draft_id,
        }

    def import_chat_attachment_drafts(
        self,
        target_quest_id: str,
        *,
        source_quest_id: str,
        attachments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        target_quest_root = self._quest_root(target_quest_id)
        source_quest_root = self._quest_root(source_quest_id)
        imported: list[dict[str, Any]] = []
        for index, raw_attachment in enumerate(attachments, start=1):
            if not isinstance(raw_attachment, dict):
                continue
            quest_relative_path = str(raw_attachment.get("quest_relative_path") or "").strip()
            absolute_path = str(raw_attachment.get("path") or "").strip()
            source_path: Path | None = None
            if quest_relative_path:
                source_path = resolve_within(source_quest_root, quest_relative_path)
            elif absolute_path:
                candidate = Path(absolute_path).resolve()
                if candidate == source_quest_root or source_quest_root in candidate.parents:
                    source_path = candidate
            if source_path is None or not source_path.exists() or not source_path.is_file():
                continue
            file_name = str(
                raw_attachment.get("name")
                or raw_attachment.get("file_name")
                or source_path.name
                or f"attachment-{index:03d}"
            ).strip() or f"attachment-{index:03d}"
            mime_type = str(raw_attachment.get("content_type") or raw_attachment.get("mime_type") or "").strip() or None
            created = self.save_chat_attachment_draft(
                target_quest_root.name,
                file_name=file_name,
                mime_type=mime_type,
                content=source_path.read_bytes(),
            )
            imported.append(created)
        return {
            "ok": True,
            "quest_id": target_quest_id,
            "source_quest_id": source_quest_id,
            "imported_count": len(imported),
            "attachments": imported,
        }

    def finalize_chat_attachment_drafts(
        self,
        quest_id: str,
        *,
        draft_ids: list[str],
        client_message_id: str | None,
    ) -> list[dict[str, Any]]:
        quest_root = self._quest_root(quest_id)
        normalized_draft_ids = [
            slugify(str(item or "").strip(), default="")
            for item in draft_ids
            if str(item or "").strip()
        ]
        if not normalized_draft_ids:
            return []
        batch_slug = slugify(
            str(client_message_id or generate_id("userfile")).strip(),
            default=generate_id("userfile"),
        )
        batch_root = ensure_dir(quest_root / "userfiles" / "web" / batch_slug)
        materialized: list[dict[str, Any]] = []
        for index, normalized_draft_id in enumerate(normalized_draft_ids, start=1):
            draft_root = self._chat_attachment_draft_root(quest_root, normalized_draft_id)
            manifest = read_json(draft_root / "manifest.json", {})
            attachment = dict(manifest.get("attachment") or {})
            source_path = Path(str(attachment.get("path") or "").strip())
            if not draft_root.exists() or not source_path.exists():
                raise FileNotFoundError(f"Unknown chat attachment draft `{normalized_draft_id}`.")
            target_name = self._dedupe_attachment_filename(
                batch_root,
                str(attachment.get("stored_name") or source_path.name or f"attachment-{index:03d}.bin"),
            )
            target_path = resolve_within(batch_root, target_name)
            ensure_dir(target_path.parent)
            shutil.move(str(source_path), str(target_path))
            finalized = self._chat_attachment_payload(
                quest_id=quest_id,
                name=str(attachment.get("name") or target_name),
                stored_name=target_name,
                mime_type=str(attachment.get("content_type") or "").strip() or None,
                asset_path=target_path,
                draft_id=None,
            )
            finalized["source_path"] = str(source_path)
            finalized["materialized"] = True
            finalized["uploaded_at"] = str(attachment.get("uploaded_at") or utc_now())
            materialized.append(finalized)
            shutil.rmtree(draft_root, ignore_errors=True)
        write_json(
            batch_root / "manifest.json",
            {
                "quest_id": quest_id,
                "client_message_id": str(client_message_id or "").strip() or None,
                "materialized_at": utc_now(),
                "attachments": materialized,
            },
        )
        return materialized

    @staticmethod
    def _chat_attachment_draft_root(quest_root: Path, draft_id: str) -> Path:
        return quest_root / "userfiles" / "web" / "_staging" / draft_id

    @staticmethod
    def _dedupe_attachment_filename(batch_root: Path, file_name: str) -> str:
        base_name = Path(file_name).name or "attachment.bin"
        stem = Path(base_name).stem or "attachment"
        suffix = Path(base_name).suffix
        candidate = base_name
        counter = 2
        while (batch_root / candidate).exists():
            candidate = f"{stem}-{counter}{suffix}"
            counter += 1
        return candidate

    @staticmethod
    def _is_readable_chat_attachment(path: Path, mime_type: str | None) -> bool:
        normalized_mime = str(mime_type or "").strip().lower()
        if any(normalized_mime.startswith(prefix) for prefix in _CHAT_ATTACHMENT_TEXT_MIME_PREFIXES):
            return True
        if normalized_mime in _CHAT_ATTACHMENT_TEXT_MIME_TYPES:
            return True
        return path.suffix.lower() in _CHAT_ATTACHMENT_TEXT_EXTENSIONS

    def _chat_attachment_payload(
        self,
        *,
        quest_id: str,
        name: str,
        stored_name: str,
        mime_type: str | None,
        asset_path: Path,
        draft_id: str | None,
    ) -> dict[str, Any]:
        quest_root = self._quest_root(quest_id)
        resolved_path = asset_path.resolve()
        content_type = mimetypes.guess_type(resolved_path.name)[0] or mime_type or "application/octet-stream"
        quest_relative_path = resolved_path.relative_to(quest_root).as_posix()
        payload: dict[str, Any] = {
            "kind": "image" if str(content_type).startswith("image/") else "path",
            "name": name,
            "file_name": stored_name,
            "content_type": content_type,
            "path": str(resolved_path),
            "quest_relative_path": quest_relative_path,
            "asset_document_id": f"path::{quest_relative_path}",
            "asset_url": f"/api/quests/{quest_id}/documents/asset?document_id={quote(f'path::{quest_relative_path}', safe='')}",
            "size_bytes": resolved_path.stat().st_size if resolved_path.exists() else 0,
            "uploaded_at": utc_now(),
            "upload_origin": "web",
        }
        if draft_id:
            payload["draft_id"] = draft_id
        if self._is_readable_chat_attachment(resolved_path, content_type):
            payload["extracted_text_path"] = quest_relative_path
        return payload

    @staticmethod
    def _normalize_workspace_relative_path(
        relative: str | None,
        *,
        field_name: str,
        allow_root: bool = True,
    ) -> str | None:
        if relative is None:
            if allow_root:
                return None
            raise ValueError(f"`{field_name}` is required.")
        raw = str(relative).strip().replace("\\", "/")
        if not raw:
            if allow_root:
                return None
            raise ValueError(f"`{field_name}` is required.")
        normalized = raw.lstrip("/").rstrip("/")
        if normalized in {"", "."}:
            if allow_root:
                return None
            raise ValueError(f"`{field_name}` must point to a workspace entry.")
        return normalized

    @staticmethod
    def _normalize_workspace_entry_name(name: str | None, *, field_name: str) -> str:
        raw = str(name or "").strip().replace("\\", "/")
        if not raw:
            raise ValueError(f"`{field_name}` is required.")
        if "/" in raw:
            raise ValueError(f"`{field_name}` must be a single path segment.")
        candidate = Path(raw).name
        if candidate != raw or candidate in {"", ".", ".."}:
            raise ValueError(f"`{field_name}` must be a valid file or folder name.")
        if candidate == ".git":
            raise ValueError("`.git` cannot be created or renamed from the explorer.")
        return candidate

    @staticmethod
    def _normalize_workspace_path_list(paths: Any, *, field_name: str) -> list[str]:
        if not isinstance(paths, list) or not paths:
            raise ValueError(f"`{field_name}` must be a non-empty list.")
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in paths:
            item = QuestService._normalize_workspace_relative_path(
                raw,
                field_name=field_name,
                allow_root=False,
            )
            if not item or item in seen:
                continue
            seen.add(item)
            normalized.append(item)
        if not normalized:
            raise ValueError(f"`{field_name}` must include at least one valid path.")
        return normalized

    @staticmethod
    def _filter_nested_workspace_paths(paths: list[str]) -> list[str]:
        kept: list[str] = []
        for path in paths:
            if any(path == parent or path.startswith(f"{parent}/") for parent in kept):
                continue
            kept.append(path)
        return kept

    def _workspace_entry_payload(self, workspace_root: Path, path: Path) -> dict:
        if path.is_dir():
            return self._directory_node(
                workspace_root,
                path=path,
                children=[],
                git_status={},
                changed_paths={},
            )
        payload = self._file_node(
            workspace_root,
            path=path,
            git_status={},
            changed_paths={},
        )
        if payload is None:
            raise FileNotFoundError(f"Unknown workspace entry `{path}`.")
        return payload

    def create_workspace_folder(
        self,
        quest_id: str,
        *,
        name: str | None,
        parent_path: str | None = None,
    ) -> dict:
        workspace_root = self.active_workspace_root(self._require_initialized_quest_root(quest_id))
        normalized_parent = self._normalize_workspace_relative_path(
            parent_path,
            field_name="parent_path",
            allow_root=True,
        )
        folder_name = self._normalize_workspace_entry_name(name, field_name="name")
        parent = resolve_within(workspace_root, normalized_parent) if normalized_parent else workspace_root
        if not parent.exists() or not parent.is_dir():
            raise FileNotFoundError(
                f"Unknown destination folder `{normalized_parent or '.'}`."
            )
        target = resolve_within(parent, folder_name)
        if target.exists():
            raise FileExistsError(
                f"`{target.relative_to(workspace_root).as_posix()}` already exists."
            )
        ensure_dir(target)
        return {
            "ok": True,
            "quest_id": quest_id,
            "parent_path": normalized_parent,
            "item": self._workspace_entry_payload(workspace_root, target),
            "saved_at": utc_now(),
        }

    def upload_workspace_file(
        self,
        quest_id: str,
        *,
        file_name: str | None,
        content: bytes,
        mime_type: str | None = None,
        parent_path: str | None = None,
    ) -> dict:
        workspace_root = self.active_workspace_root(self._require_initialized_quest_root(quest_id))
        normalized_parent = self._normalize_workspace_relative_path(
            parent_path,
            field_name="parent_path",
            allow_root=True,
        )
        safe_name = self._normalize_workspace_entry_name(file_name, field_name="file_name")
        parent = resolve_within(workspace_root, normalized_parent) if normalized_parent else workspace_root
        if not parent.exists() or not parent.is_dir():
            raise FileNotFoundError(
                f"Unknown destination folder `{normalized_parent or '.'}`."
            )
        target = resolve_within(parent, safe_name)
        if target.exists():
            raise FileExistsError(
                f"`{target.relative_to(workspace_root).as_posix()}` already exists."
            )
        ensure_dir(target.parent)
        target.write_bytes(content)
        payload = self._workspace_entry_payload(workspace_root, target)
        guessed_mime = mimetypes.guess_type(target.name)[0] or mime_type or "application/octet-stream"
        payload["mime_type"] = guessed_mime
        return {
            "ok": True,
            "quest_id": quest_id,
            "parent_path": normalized_parent,
            "item": payload,
            "saved_at": utc_now(),
        }

    def rename_workspace_entry(
        self,
        quest_id: str,
        *,
        path: str | None,
        new_name: str | None,
    ) -> dict:
        workspace_root = self.active_workspace_root(self._require_initialized_quest_root(quest_id))
        normalized_path = self._normalize_workspace_relative_path(
            path,
            field_name="path",
            allow_root=False,
        )
        source = resolve_within(workspace_root, normalized_path)
        if not source.exists():
            raise FileNotFoundError(f"Unknown workspace entry `{normalized_path}`.")
        safe_name = self._normalize_workspace_entry_name(new_name, field_name="new_name")
        target = resolve_within(source.parent, safe_name)
        if target.exists() and target != source:
            raise FileExistsError(
                f"`{target.relative_to(workspace_root).as_posix()}` already exists."
            )
        if target != source:
            source.rename(target)
        payload = self._workspace_entry_payload(workspace_root, target)
        return {
            "ok": True,
            "quest_id": quest_id,
            "previous_path": normalized_path,
            "item": payload,
            "saved_at": utc_now(),
        }

    def move_workspace_entries(
        self,
        quest_id: str,
        *,
        paths: Any,
        target_parent_path: str | None = None,
    ) -> dict:
        workspace_root = self.active_workspace_root(self._require_initialized_quest_root(quest_id))
        normalized_paths = self._filter_nested_workspace_paths(
            self._normalize_workspace_path_list(paths, field_name="paths")
        )
        normalized_target_parent = self._normalize_workspace_relative_path(
            target_parent_path,
            field_name="target_parent_path",
            allow_root=True,
        )
        target_parent = (
            resolve_within(workspace_root, normalized_target_parent)
            if normalized_target_parent
            else workspace_root
        )
        if not target_parent.exists() or not target_parent.is_dir():
            raise FileNotFoundError(
                f"Unknown destination folder `{normalized_target_parent or '.'}`."
            )

        moves: list[tuple[str, Path, Path]] = []
        destination_keys: set[str] = set()
        target_parent_resolved = target_parent.resolve()
        for normalized_path in normalized_paths:
            source = resolve_within(workspace_root, normalized_path)
            if not source.exists():
                raise FileNotFoundError(f"Unknown workspace entry `{normalized_path}`.")
            source_resolved = source.resolve()
            if source_resolved == target_parent_resolved or source_resolved in target_parent_resolved.parents:
                raise ValueError(
                    f"`{normalized_path}` cannot be moved into itself or one of its descendants."
                )
            destination = resolve_within(target_parent, source.name)
            if destination.exists() and destination.resolve() != source_resolved:
                raise FileExistsError(
                    f"`{destination.relative_to(workspace_root).as_posix()}` already exists."
                )
            destination_key = str(destination.resolve())
            if destination_key in destination_keys and destination != source:
                raise FileExistsError(
                    f"`{destination.relative_to(workspace_root).as_posix()}` would conflict with another moved entry."
                )
            destination_keys.add(destination_key)
            moves.append((normalized_path, source, destination))

        items: list[dict] = []
        for _normalized_path, source, destination in moves:
            if destination != source:
                source.rename(destination)
            items.append(self._workspace_entry_payload(workspace_root, destination))
        return {
            "ok": True,
            "quest_id": quest_id,
            "target_parent_path": normalized_target_parent,
            "items": items,
            "saved_at": utc_now(),
        }

    def delete_workspace_entries(
        self,
        quest_id: str,
        *,
        paths: Any,
    ) -> dict:
        workspace_root = self.active_workspace_root(self._require_initialized_quest_root(quest_id))
        normalized_paths = self._filter_nested_workspace_paths(
            self._normalize_workspace_path_list(paths, field_name="paths")
        )
        sources: list[Path] = []
        items: list[dict] = []
        for normalized_path in normalized_paths:
            source = resolve_within(workspace_root, normalized_path)
            if not source.exists():
                raise FileNotFoundError(f"Unknown workspace entry `{normalized_path}`.")
            sources.append(source)
            items.append(self._workspace_entry_payload(workspace_root, source))

        for source in sorted(sources, key=lambda item: len(item.parts), reverse=True):
            if source.is_dir():
                shutil.rmtree(source)
            else:
                source.unlink()
        return {
            "ok": True,
            "quest_id": quest_id,
            "items": items,
            "saved_at": utc_now(),
        }

    def _revision_explorer(self, quest_id: str, *, revision: str, mode: str) -> dict:
        quest_root = self._quest_root(quest_id)
        if not self._git_revision_exists(quest_root, revision):
            raise FileNotFoundError(f"Unknown git revision `{revision}`.")

        snapshot_paths = self._git_snapshot_paths(quest_root, revision)
        snapshot_tree = self._build_snapshot_tree(snapshot_paths)
        root_nodes = self._snapshot_children(snapshot_tree, revision=revision, prefix="")
        sections = self._group_explorer_sections(root_nodes)

        return {
            "quest_id": quest_id,
            "quest_root": str(quest_root.resolve()),
            "view": {
                "mode": mode,
                "revision": revision,
                "label": revision,
                "read_only": True,
            },
            "sections": sections,
        }

    @staticmethod
    def _group_explorer_sections(nodes: list[dict]) -> list[dict]:
        section_titles = {
            "core": "Core",
            "memory": "Memory",
            "research": "Research",
            "artifacts": "Artifacts",
            "runtime": "Runtime",
            "runner_history": "Runner History",
            "quest": "Quest",
        }
        order = ["core", "memory", "research", "artifacts", "quest", "runtime", "runner_history"]
        grouped: dict[str, list[dict]] = {key: [] for key in order}
        extra_order: list[str] = []

        for node in nodes:
            section_id = str(node.get("scope") or "quest")
            if section_id not in grouped:
                grouped[section_id] = []
                extra_order.append(section_id)
            grouped[section_id].append(node)

        sections: list[dict] = []
        for section_id in [*order, *extra_order]:
            bucket = [item for item in grouped.get(section_id, []) if item is not None]
            if not bucket:
                continue
            sections.append(
                {
                    "id": section_id,
                    "title": section_titles.get(section_id, section_id.replace("_", " ").title()),
                    "nodes": bucket,
                }
            )
        return sections

    @staticmethod
    def _normalize_binding_source(source: str) -> str:
        return normalize_conversation_id(source)

    @staticmethod
    def _interaction_candidate_ids(item: dict[str, Any]) -> set[str]:
        return {
            str(item.get("interaction_id") or "").strip(),
            str(item.get("artifact_id") or "").strip(),
        } - {""}

    @staticmethod
    def _default_reply_interaction_id(
        *,
        open_requests: list[dict[str, Any]],
        recent_threads: list[dict[str, Any]],
    ) -> str | None:
        for item in reversed(open_requests):
            if str(item.get("status") or "") != "waiting":
                continue
            interaction_id = str(item.get("interaction_id") or item.get("artifact_id") or "").strip()
            if interaction_id:
                return interaction_id
        for item in reversed(recent_threads):
            if str(item.get("reply_mode") or "") not in {"threaded", "blocking"}:
                continue
            if str(item.get("status") or "") in {"closed", "superseded"}:
                continue
            interaction_id = str(item.get("interaction_id") or item.get("artifact_id") or "").strip()
            if interaction_id:
                return interaction_id
        return None

    @staticmethod
    def _latest_waiting_interaction_id(open_requests: list[dict[str, Any]]) -> str | None:
        for item in reversed(open_requests):
            if str(item.get("status") or "") != "waiting":
                continue
            interaction_id = str(item.get("interaction_id") or item.get("artifact_id") or "").strip()
            if interaction_id:
                return interaction_id
        return None

    def _read_interaction_state(self, quest_root: Path) -> dict[str, Any]:
        state = self._read_cached_json(quest_root / ".ds" / "interaction_state.json", {})
        state.setdefault("open_requests", [])
        state.setdefault("recent_threads", [])
        return state

    @staticmethod
    def _runtime_state_path(quest_root: Path) -> Path:
        return quest_root / ".ds" / "runtime_state.json"

    @staticmethod
    def _agent_status_path(quest_root: Path) -> Path:
        return quest_root / ".ds" / "agent_status.json"

    @staticmethod
    def _message_queue_path(quest_root: Path) -> Path:
        return quest_root / ".ds" / "user_message_queue.json"

    @staticmethod
    def _interaction_journal_path(quest_root: Path) -> Path:
        return quest_root / ".ds" / "interaction_journal.jsonl"

    @staticmethod
    def _active_user_requirements_path(quest_root: Path) -> Path:
        return quest_root / "memory" / "knowledge" / "active-user-requirements.md"

    @staticmethod
    def _default_message_queue() -> dict[str, Any]:
        return {
            "version": 2,
            "pending": [],
            "completed": [],
            "message_states": {},
        }

    def _default_runtime_state(
        self,
        quest_root: Path,
        *,
        quest_yaml: dict[str, Any] | None = None,
        queue_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        quest_yaml = dict(quest_yaml or self.read_quest_yaml(quest_root))
        queue_payload = dict(queue_payload or self._read_message_queue(quest_root))
        pending_count = len((queue_payload or {}).get("pending") or [])
        timestamp = quest_yaml.get("updated_at") or quest_yaml.get("created_at") or utc_now()
        status = str(quest_yaml.get("status") or "idle")
        return {
            "quest_id": str(quest_yaml.get("quest_id") or quest_root.name),
            "status": status,
            "display_status": status,
            "active_run_id": quest_yaml.get("active_run_id"),
            "active_interaction_id": None,
            "stop_reason": None,
            "last_transition_at": timestamp,
            "last_artifact_interact_at": None,
            "last_tool_activity_at": None,
            "last_tool_activity_name": None,
            "tool_calls_since_last_artifact_interact": 0,
            "continuation_policy": "auto",
            "continuation_anchor": None,
            "continuation_reason": None,
            "continuation_updated_at": None,
            "waiting_notice": None,
            "last_resume_source": None,
            "last_resume_at": None,
            "last_recovery_abandoned_run_id": None,
            "last_recovery_summary": None,
            "last_stage_fingerprint": None,
            "last_stage_fingerprint_at": None,
            "same_fingerprint_auto_turn_count": 0,
            "pending_user_message_count": pending_count,
            "last_delivered_batch_id": None,
            "last_delivered_at": None,
            "retry_state": None,
            "turn_message_override": None,
        }

    def _default_agent_status(self, quest_root: Path) -> dict[str, Any]:
        quest_yaml = self.read_quest_yaml(quest_root)
        timestamp = quest_yaml.get("updated_at") or quest_yaml.get("created_at") or utc_now()
        return {
            "version": 1,
            "quest_id": str(quest_yaml.get("quest_id") or quest_root.name),
            "state": "idle",
            "comment": "",
            "current_focus": "",
            "next_action": "",
            "plan_items": [],
            "related_paths": [],
            "updated_at": timestamp,
        }

    def _initialize_runtime_files(self, quest_root: Path) -> None:
        if not self._quest_yaml_path(quest_root).exists():
            raise FileNotFoundError(f"Unknown quest `{quest_root.name}`.")
        queue_path = self._message_queue_path(quest_root)
        if not queue_path.exists():
            write_json(queue_path, self._default_message_queue())
        runtime_path = self._runtime_state_path(quest_root)
        if not runtime_path.exists():
            write_json(runtime_path, self._default_runtime_state(quest_root))
        research_state_path = self._research_state_path(quest_root)
        if not research_state_path.exists():
            write_json(research_state_path, self._default_research_state(quest_root))
        lab_canvas_state_path = self._lab_canvas_state_path(quest_root)
        if not lab_canvas_state_path.exists():
            write_json(lab_canvas_state_path, self._default_lab_canvas_state(quest_root))
        agent_status_path = self._agent_status_path(quest_root)
        if not agent_status_path.exists():
            write_json(agent_status_path, self._default_agent_status(quest_root))

    def _read_message_queue(self, quest_root: Path) -> dict[str, Any]:
        payload = self._read_cached_json(self._message_queue_path(quest_root), self._default_message_queue())
        if not isinstance(payload, dict):
            payload = self._default_message_queue()
        payload.setdefault("version", 2)
        payload.setdefault("pending", [])
        payload.setdefault("completed", [])
        message_states = payload.get("message_states")
        payload["message_states"] = dict(message_states) if isinstance(message_states, dict) else {}
        return payload

    def _write_message_queue(self, quest_root: Path, payload: dict[str, Any]) -> None:
        write_json(self._message_queue_path(quest_root), payload)

    def _read_runtime_state(self, quest_root: Path) -> dict[str, Any]:
        self._initialize_runtime_files(quest_root)
        quest_yaml = self.read_quest_yaml(quest_root)
        queue_payload = self._read_message_queue(quest_root)
        defaults = self._default_runtime_state(
            quest_root,
            quest_yaml=quest_yaml,
            queue_payload=queue_payload,
        )
        payload = self._read_cached_json(self._runtime_state_path(quest_root), defaults)
        if not isinstance(payload, dict):
            payload = defaults
        merged = {**defaults, **payload}
        merged["pending_user_message_count"] = int(merged.get("pending_user_message_count") or 0)
        merged["tool_calls_since_last_artifact_interact"] = int(merged.get("tool_calls_since_last_artifact_interact") or 0)
        merged["continuation_policy"] = self._normalize_continuation_policy(
            merged.get("continuation_policy"),
            default=str(defaults.get("continuation_policy") or "auto"),
        )
        merged["continuation_anchor"] = str(merged.get("continuation_anchor") or "").strip() or None
        merged["continuation_reason"] = str(merged.get("continuation_reason") or "").strip() or None
        merged["continuation_updated_at"] = str(merged.get("continuation_updated_at") or "").strip() or None
        merged["waiting_notice"] = dict(merged.get("waiting_notice") or {}) if isinstance(merged.get("waiting_notice"), dict) else None
        merged["last_resume_source"] = str(merged.get("last_resume_source") or "").strip() or None
        merged["last_resume_at"] = str(merged.get("last_resume_at") or "").strip() or None
        merged["last_recovery_abandoned_run_id"] = str(merged.get("last_recovery_abandoned_run_id") or "").strip() or None
        merged["last_recovery_summary"] = str(merged.get("last_recovery_summary") or "").strip() or None
        merged["last_stage_fingerprint"] = str(merged.get("last_stage_fingerprint") or "").strip() or None
        merged["last_stage_fingerprint_at"] = str(merged.get("last_stage_fingerprint_at") or "").strip() or None
        merged["same_fingerprint_auto_turn_count"] = int(merged.get("same_fingerprint_auto_turn_count") or 0)
        merged["retry_state"] = dict(merged.get("retry_state") or {}) if isinstance(merged.get("retry_state"), dict) else None
        merged["turn_message_override"] = (
            dict(merged.get("turn_message_override") or {})
            if isinstance(merged.get("turn_message_override"), dict)
            else None
        )
        return merged

    def _write_runtime_state(self, quest_root: Path, payload: dict[str, Any]) -> None:
        write_json(self._runtime_state_path(quest_root), payload)

    def update_runtime_state(
        self,
        *,
        quest_root: Path,
        status: str | object = _UNSET,
        active_run_id: str | None | object = _UNSET,
        stop_reason: str | None | object = _UNSET,
        active_interaction_id: str | None | object = _UNSET,
        last_transition_at: str | None | object = _UNSET,
        last_artifact_interact_at: str | None | object = _UNSET,
        last_tool_activity_at: str | None | object = _UNSET,
        last_tool_activity_name: str | None | object = _UNSET,
        tool_calls_since_last_artifact_interact: int | object = _UNSET,
        continuation_policy: str | object = _UNSET,
        continuation_anchor: str | None | object = _UNSET,
        continuation_reason: str | None | object = _UNSET,
        continuation_updated_at: str | None | object = _UNSET,
        waiting_notice: dict[str, Any] | None | object = _UNSET,
        last_resume_source: str | None | object = _UNSET,
        last_resume_at: str | None | object = _UNSET,
        last_recovery_abandoned_run_id: str | None | object = _UNSET,
        last_recovery_summary: str | None | object = _UNSET,
        last_stage_fingerprint: str | None | object = _UNSET,
        last_stage_fingerprint_at: str | None | object = _UNSET,
        same_fingerprint_auto_turn_count: int | object = _UNSET,
        pending_user_message_count: int | object = _UNSET,
        last_delivered_batch_id: str | None | object = _UNSET,
        last_delivered_at: str | None | object = _UNSET,
        display_status: str | None | object = _UNSET,
        retry_state: dict[str, Any] | None | object = _UNSET,
        turn_message_override: dict[str, Any] | None | object = _UNSET,
    ) -> dict[str, Any]:
        with self._runtime_state_lock(quest_root):
            state = self._read_runtime_state(quest_root)
            now = utc_now()
            status_changed = False
            run_changed = False

            if status is not _UNSET:
                normalized_status = str(status or state.get("status") or "idle")
                state["status"] = normalized_status
                status_changed = True
                if display_status is _UNSET:
                    state["display_status"] = normalized_status
            if display_status is not _UNSET:
                state["display_status"] = str(display_status or state.get("status") or "idle")
            if active_run_id is not _UNSET:
                state["active_run_id"] = str(active_run_id).strip() if active_run_id else None
                run_changed = True
            if stop_reason is not _UNSET:
                state["stop_reason"] = str(stop_reason).strip() if stop_reason else None
            elif status is not _UNSET and str(state.get("status") or "") not in {"stopped", "paused", "error", "completed"}:
                state["stop_reason"] = None
            if active_interaction_id is not _UNSET:
                state["active_interaction_id"] = str(active_interaction_id).strip() if active_interaction_id else None
            if last_artifact_interact_at is not _UNSET:
                state["last_artifact_interact_at"] = last_artifact_interact_at
            if last_tool_activity_at is not _UNSET:
                state["last_tool_activity_at"] = last_tool_activity_at
            if last_tool_activity_name is not _UNSET:
                state["last_tool_activity_name"] = str(last_tool_activity_name).strip() if last_tool_activity_name else None
            if tool_calls_since_last_artifact_interact is not _UNSET:
                state["tool_calls_since_last_artifact_interact"] = max(0, int(tool_calls_since_last_artifact_interact))
            continuation_changed = False
            if continuation_policy is not _UNSET:
                state["continuation_policy"] = self._normalize_continuation_policy(continuation_policy)
                continuation_changed = True
            if continuation_anchor is not _UNSET:
                normalized_anchor = str(continuation_anchor or "").strip() or None
                if normalized_anchor is not None:
                    from ..prompts.builder import current_standard_skills

                    available_stage_skills = current_standard_skills(repo_root())
                    if normalized_anchor not in available_stage_skills:
                        allowed = ", ".join(available_stage_skills)
                        raise ValueError(
                            f"Unsupported continuation anchor `{normalized_anchor}`. Allowed values: {allowed}."
                        )
                state["continuation_anchor"] = normalized_anchor
                continuation_changed = True
            if continuation_reason is not _UNSET:
                state["continuation_reason"] = str(continuation_reason or "").strip() or None
                continuation_changed = True
            if continuation_updated_at is not _UNSET:
                state["continuation_updated_at"] = str(continuation_updated_at or "").strip() or None
            elif continuation_changed:
                state["continuation_updated_at"] = now
            if waiting_notice is not _UNSET:
                state["waiting_notice"] = dict(waiting_notice) if isinstance(waiting_notice, dict) else None
            if last_resume_source is not _UNSET:
                state["last_resume_source"] = str(last_resume_source or "").strip() or None
            if last_resume_at is not _UNSET:
                state["last_resume_at"] = str(last_resume_at or "").strip() or None
            if last_recovery_abandoned_run_id is not _UNSET:
                state["last_recovery_abandoned_run_id"] = str(last_recovery_abandoned_run_id or "").strip() or None
            if last_recovery_summary is not _UNSET:
                state["last_recovery_summary"] = str(last_recovery_summary or "").strip() or None
            if last_stage_fingerprint is not _UNSET:
                state["last_stage_fingerprint"] = str(last_stage_fingerprint or "").strip() or None
            if last_stage_fingerprint_at is not _UNSET:
                state["last_stage_fingerprint_at"] = str(last_stage_fingerprint_at or "").strip() or None
            if same_fingerprint_auto_turn_count is not _UNSET:
                state["same_fingerprint_auto_turn_count"] = max(0, int(same_fingerprint_auto_turn_count or 0))
            if pending_user_message_count is not _UNSET:
                state["pending_user_message_count"] = max(0, int(pending_user_message_count))
            if last_delivered_batch_id is not _UNSET:
                state["last_delivered_batch_id"] = str(last_delivered_batch_id).strip() if last_delivered_batch_id else None
            if last_delivered_at is not _UNSET:
                state["last_delivered_at"] = last_delivered_at
            if retry_state is not _UNSET:
                state["retry_state"] = dict(retry_state) if isinstance(retry_state, dict) else None
            if turn_message_override is not _UNSET:
                state["turn_message_override"] = (
                    dict(turn_message_override)
                    if isinstance(turn_message_override, dict)
                    else None
                )
            if last_transition_at is not _UNSET:
                state["last_transition_at"] = last_transition_at
            elif status_changed or run_changed:
                state["last_transition_at"] = now

            self._write_runtime_state(quest_root, state)

            if status_changed or run_changed:
                quest_data = read_yaml(quest_root / "quest.yaml", {})
                if status is not _UNSET:
                    quest_data["status"] = state["status"]
                if active_run_id is not _UNSET:
                    if state.get("active_run_id"):
                        quest_data["active_run_id"] = state["active_run_id"]
                    else:
                        quest_data.pop("active_run_id", None)
                quest_data["updated_at"] = now
                write_yaml(quest_root / "quest.yaml", quest_data)
            self.schedule_projection_refresh(quest_root, kinds=("details",))
            return state

    @staticmethod
    def _normalize_continuation_policy(value: object, *, default: str = "auto") -> str:
        normalized = str(value or "").strip().lower() or default
        return normalized if normalized in CONTINUATION_POLICIES else default

    def set_continuation_state(
        self,
        quest_root: Path,
        *,
        policy: str,
        anchor: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return self.update_runtime_state(
            quest_root=quest_root,
            continuation_policy=policy,
            continuation_anchor=anchor,
            continuation_reason=reason,
        )

    @staticmethod
    def _normalize_message_read_state(value: object, *, default: str = "read") -> str:
        normalized = str(value or "").strip().lower() or default
        return normalized if normalized in {"read", "unread"} else default

    def _update_message_read_state(
        self,
        queue_payload: dict[str, Any],
        *,
        message_id: str | None,
        client_message_id: str | None = None,
        source: str | None = None,
        conversation_id: str | None = None,
        created_at: str | None = None,
        read_state: str,
        read_reason: str | None = None,
        read_at: str | None = None,
        read_interaction_id: str | None = None,
        read_run_id: str | None = None,
    ) -> dict[str, Any] | None:
        normalized_message_id = str(message_id or "").strip()
        normalized_client_message_id = str(client_message_id or "").strip() or None
        if not normalized_message_id and not normalized_client_message_id:
            return None
        states = dict(queue_payload.get("message_states") or {})
        key = normalized_message_id or f"client:{normalized_client_message_id}"
        current = dict(states.get(key) or {})
        current["message_id"] = normalized_message_id or current.get("message_id")
        if normalized_client_message_id:
            current["client_message_id"] = normalized_client_message_id
        if source:
            current["source"] = str(source)
        if conversation_id:
            current["conversation_id"] = str(conversation_id)
        if created_at:
            current["created_at"] = str(created_at)
        current["read_state"] = self._normalize_message_read_state(read_state)
        current["read_reason"] = str(read_reason or "").strip() or None
        current["read_at"] = str(read_at or "").strip() or None
        current["read_interaction_id"] = str(read_interaction_id or "").strip() or None
        current["read_run_id"] = str(read_run_id or "").strip() or None
        current["updated_at"] = utc_now()
        states[key] = current
        if normalized_message_id:
            for existing_key, item in list(states.items()):
                if existing_key == key or not isinstance(item, dict):
                    continue
                if str(item.get("message_id") or "").strip() == normalized_message_id:
                    states.pop(existing_key, None)
            if normalized_client_message_id:
                states[normalized_message_id] = current
                if key != normalized_message_id:
                    states.pop(key, None)
                key = normalized_message_id
        queue_payload["message_states"] = states
        return dict(states.get(key) or current)

    def _message_read_state(
        self,
        quest_root: Path,
        *,
        message_id: str | None = None,
        client_message_id: str | None = None,
    ) -> dict[str, Any] | None:
        queue_payload = self._read_message_queue(quest_root)
        states = queue_payload.get("message_states")
        if not isinstance(states, dict):
            return None
        normalized_message_id = str(message_id or "").strip()
        normalized_client_message_id = str(client_message_id or "").strip()
        if normalized_message_id:
            direct = states.get(normalized_message_id)
            if isinstance(direct, dict):
                return dict(direct)
        for item in states.values():
            if not isinstance(item, dict):
                continue
            if normalized_message_id and str(item.get("message_id") or "").strip() == normalized_message_id:
                return dict(item)
            if normalized_client_message_id and str(item.get("client_message_id") or "").strip() == normalized_client_message_id:
                return dict(item)
        return None

    @staticmethod
    def _find_message_queue_entry(
        items: list[dict[str, Any]],
        *,
        message_id: str | None = None,
        client_message_id: str | None = None,
    ) -> tuple[int, dict[str, Any]] | tuple[None, None]:
        normalized_message_id = str(message_id or "").strip()
        normalized_client_message_id = str(client_message_id or "").strip()
        if not normalized_message_id and not normalized_client_message_id:
            return None, None
        for index in range(len(items) - 1, -1, -1):
            item = items[index]
            if normalized_message_id and str(item.get("message_id") or "").strip() == normalized_message_id:
                return index, dict(item)
            if normalized_client_message_id and str(item.get("client_message_id") or "").strip() == normalized_client_message_id:
                return index, dict(item)
        return None, None

    def pending_user_message_status(
        self,
        quest_root: Path,
        *,
        message_id: str | None = None,
        client_message_id: str | None = None,
    ) -> dict[str, Any]:
        queue_payload = self._read_message_queue(quest_root)
        pending = [dict(item) for item in (queue_payload.get("pending") or []) if isinstance(item, dict)]
        completed = [dict(item) for item in (queue_payload.get("completed") or []) if isinstance(item, dict)]
        pending_index, pending_item = self._find_message_queue_entry(
            pending,
            message_id=message_id,
            client_message_id=client_message_id,
        )
        state_record = self._message_read_state(
            quest_root,
            message_id=message_id,
            client_message_id=client_message_id,
        )
        completed_index, completed_item = self._find_message_queue_entry(
            completed,
            message_id=message_id,
            client_message_id=client_message_id,
        )
        queue_state = "missing"
        if pending_index is not None and pending_item is not None:
            queue_state = "pending"
        elif state_record:
            read_reason = str(state_record.get("read_reason") or "").strip()
            queue_state = "withdrawn" if read_reason == "withdrawn_by_user" else "read"
        elif completed_index is not None and completed_item is not None:
            completed_status = str(completed_item.get("status") or "").strip()
            queue_state = "withdrawn" if completed_status == "withdrawn_by_user" else "read"
        return {
            "queue_state": queue_state,
            "pending_index": pending_index,
            "pending_item": pending_item,
            "completed_index": completed_index,
            "completed_item": completed_item,
            "message_state": state_record,
        }

    def latest_pending_user_message(self, quest_id: str) -> dict[str, Any] | None:
        quest_root = self._quest_root(quest_id)
        queue_payload = self._read_message_queue(quest_root)
        pending = [dict(item) for item in (queue_payload.get("pending") or []) if isinstance(item, dict)]
        if not pending:
            return None
        latest = dict(pending[-1])
        return {
            "id": latest.get("message_id"),
            "message_id": latest.get("message_id"),
            "client_message_id": latest.get("client_message_id"),
            "role": "user",
            "source": latest.get("source"),
            "content": latest.get("content") or "",
            "created_at": latest.get("created_at"),
            "reply_to_interaction_id": latest.get("reply_to_interaction_id"),
            "attachments": [dict(item) for item in (latest.get("attachments") or []) if isinstance(item, dict)],
        }

    def withdraw_pending_user_message(
        self,
        quest_id: str,
        *,
        message_id: str | None,
        source: str,
    ) -> dict[str, Any]:
        normalized_message_id = str(message_id or "").strip()
        if not normalized_message_id:
            return {
                "ok": False,
                "status": "invalid_request",
                "message": "Message id is required.",
            }
        quest_root = self._quest_root(quest_id)
        queue_payload = self._read_message_queue(quest_root)
        status_payload = self.pending_user_message_status(
            quest_root,
            message_id=normalized_message_id,
        )
        pending_index = status_payload.get("pending_index")
        pending_item = dict(status_payload.get("pending_item") or {}) if isinstance(status_payload.get("pending_item"), dict) else None
        if pending_index is None or pending_item is None:
            queue_state = str(status_payload.get("queue_state") or "missing")
            message_state = (
                dict(status_payload.get("message_state") or {})
                if isinstance(status_payload.get("message_state"), dict)
                else None
            )
            if queue_state == "read":
                return {
                    "ok": False,
                    "status": "already_read",
                    "message": "Withdrawal failed because this message was already sent to the agent.",
                    "message_id": normalized_message_id,
                    "current_message_state": message_state,
                }
            if queue_state == "withdrawn":
                return {
                    "ok": True,
                    "status": "already_withdrawn",
                    "message": "This message was already withdrawn from the waiting queue.",
                    "message_id": normalized_message_id,
                    "current_message_state": message_state,
                }
            return {
                "ok": False,
                "status": "missing",
                "message": f"Message `{normalized_message_id}` is not waiting in the queue.",
                "message_id": normalized_message_id,
                "current_message_state": message_state,
            }

        pending = [dict(item) for item in (queue_payload.get("pending") or []) if isinstance(item, dict)]
        completed = [dict(item) for item in (queue_payload.get("completed") or []) if isinstance(item, dict)]
        withdrawn_at = utc_now()
        withdrawn = {
            **pending.pop(int(pending_index)),
            "status": "withdrawn_by_user",
            "withdrawn_at": withdrawn_at,
            "withdrawn_by_source": source,
        }
        queue_payload["pending"] = pending
        queue_payload["completed"] = [*completed, withdrawn][-200:]
        state_record = self._update_message_read_state(
            queue_payload,
            message_id=str(withdrawn.get("message_id") or "").strip() or None,
            client_message_id=str(withdrawn.get("client_message_id") or "").strip() or None,
            source=str(withdrawn.get("source") or "").strip() or None,
            conversation_id=str(withdrawn.get("conversation_id") or "").strip() or None,
            created_at=str(withdrawn.get("created_at") or "").strip() or None,
            read_state="read",
            read_reason="withdrawn_by_user",
            read_at=withdrawn_at,
        )
        self._write_message_queue(quest_root, queue_payload)
        self.update_runtime_state(
            quest_root=quest_root,
            pending_user_message_count=len(pending),
        )
        self.append_message_read_state_event(
            quest_id,
            message_id=str(withdrawn.get("message_id") or "").strip() or None,
            client_message_id=str(withdrawn.get("client_message_id") or "").strip() or None,
            read_state=str((state_record or {}).get("read_state") or "read"),
            read_reason=str((state_record or {}).get("read_reason") or "withdrawn_by_user"),
            read_at=str((state_record or {}).get("read_at") or withdrawn_at),
        )
        append_jsonl(
            self._interaction_journal_path(quest_root),
            {
                "event_id": generate_id("evt"),
                "type": "user_message_withdrawn",
                "quest_id": quest_id,
                "message_id": normalized_message_id,
                "source": source,
                "created_at": withdrawn_at,
            },
        )
        self._write_active_user_requirements(quest_root, latest_requirement=None)
        return {
            "ok": True,
            "status": "withdrawn",
            "message": "The message was removed from the waiting queue.",
            "message_id": normalized_message_id,
            "pending_user_message_count": len(pending),
            "current_message_state": state_record,
        }

    def enrich_conversation_message_event(self, quest_id: str, event: dict[str, Any]) -> dict[str, Any]:
        if str(event.get("type") or "").strip() != "conversation.message":
            return dict(event)
        quest_root = self._quest_root(quest_id)
        read_state = self._message_read_state(
            quest_root,
            message_id=str(event.get("message_id") or "").strip() or None,
            client_message_id=str(event.get("client_message_id") or "").strip() or None,
        )
        enriched = dict(event)
        if read_state:
            enriched["read_state"] = read_state.get("read_state")
            enriched["read_reason"] = read_state.get("read_reason")
            enriched["read_at"] = read_state.get("read_at")
        return enriched

    def append_message_read_state_event(
        self,
        quest_id: str,
        *,
        message_id: str | None,
        client_message_id: str | None = None,
        read_state: str,
        read_reason: str | None = None,
        read_at: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "event_id": generate_id("evt"),
            "type": "conversation.message_state",
            "quest_id": quest_id,
            "message_id": str(message_id or "").strip() or None,
            "client_message_id": str(client_message_id or "").strip() or None,
            "read_state": self._normalize_message_read_state(read_state),
            "read_reason": str(read_reason or "").strip() or None,
            "read_at": str(read_at or "").strip() or None,
            "created_at": utc_now(),
        }
        append_jsonl(self._quest_root(quest_id) / ".ds" / "events.jsonl", payload)
        return payload

    def set_turn_message_override(
        self,
        quest_root: Path,
        *,
        turn_reason: str,
        message: str,
        message_ids: list[str] | None = None,
        delivery_batch_id: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "turn_reason": str(turn_reason or "").strip() or "user_message",
            "message": str(message or "").strip(),
            "message_ids": [str(item).strip() for item in (message_ids or []) if str(item).strip()],
            "delivery_batch_id": str(delivery_batch_id or "").strip() or None,
            "source": str(source or "").strip() or None,
            "created_at": utc_now(),
        }
        self.update_runtime_state(
            quest_root=quest_root,
            turn_message_override=payload,
        )
        return payload

    def consume_turn_message_override(
        self,
        quest_root: Path,
        *,
        expected_turn_reason: str | None = None,
    ) -> dict[str, Any] | None:
        with self._runtime_state_lock(quest_root):
            state = self._read_runtime_state(quest_root)
            override = dict(state.get("turn_message_override") or {}) if isinstance(state.get("turn_message_override"), dict) else None
            if not override:
                return None
            if expected_turn_reason:
                normalized_expected = str(expected_turn_reason or "").strip()
                normalized_actual = str(override.get("turn_reason") or "").strip()
                if normalized_expected and normalized_actual != normalized_expected:
                    return None
            state["turn_message_override"] = None
            self._write_runtime_state(quest_root, state)
            return override

    def _enqueue_user_message(self, quest_root: Path, record: dict[str, Any]) -> dict[str, Any]:
        queue_payload = self._read_message_queue(quest_root)
        source = str(record.get("source") or "local")
        queue_record = {
            "message_id": record.get("id"),
            "client_message_id": str(record.get("client_message_id") or "").strip() or None,
            "source": source,
            "conversation_id": self._normalize_binding_source(source),
            "content": record.get("content") or "",
            "created_at": record.get("created_at"),
            "reply_to_interaction_id": record.get("reply_to_interaction_id"),
            "attachments": [dict(item) for item in (record.get("attachments") or []) if isinstance(item, dict)],
            "status": "queued",
        }
        queue_payload["pending"] = [*list(queue_payload.get("pending") or []), queue_record]
        self._update_message_read_state(
            queue_payload,
            message_id=str(queue_record.get("message_id") or "").strip() or None,
            client_message_id=str(queue_record.get("client_message_id") or "").strip() or None,
            source=source,
            conversation_id=str(queue_record.get("conversation_id") or "").strip() or None,
            created_at=str(queue_record.get("created_at") or "").strip() or None,
            read_state="unread",
            read_reason="queued",
            read_at=None,
        )
        self._write_message_queue(quest_root, queue_payload)
        self.update_runtime_state(
            quest_root=quest_root,
            pending_user_message_count=len(queue_payload["pending"]),
        )
        append_jsonl(
            self._interaction_journal_path(quest_root),
            {
                "event_id": generate_id("evt"),
                "type": "user_inbound",
                "quest_id": quest_root.name,
                **queue_record,
            },
        )
        return queue_record

    def _write_active_user_requirements(
        self,
        quest_root: Path,
        *,
        latest_requirement: dict[str, Any] | None,
    ) -> Path:
        quest_yaml = self.read_quest_yaml(quest_root)
        quest_goal = str(quest_yaml.get("title") or quest_yaml.get("quest_id") or quest_root.name).strip()
        user_messages = [
            item
            for item in read_jsonl(quest_root / ".ds" / "conversations" / "main.jsonl")
            if str(item.get("role") or "") == "user"
        ]
        filtered_user_messages = []
        for item in user_messages:
            state = self._message_read_state(
                quest_root,
                message_id=str(item.get("id") or "").strip() or None,
                client_message_id=str(item.get("client_message_id") or "").strip() or None,
            )
            if str((state or {}).get("read_reason") or "").strip() == "withdrawn_by_user":
                continue
            filtered_user_messages.append(item)
        latest = latest_requirement
        if latest is not None:
            latest_state = self._message_read_state(
                quest_root,
                message_id=str(latest.get("id") or "").strip() or None,
                client_message_id=str(latest.get("client_message_id") or "").strip() or None,
            )
            if str((latest_state or {}).get("read_reason") or "").strip() == "withdrawn_by_user":
                latest = None
        if latest is None:
            latest = filtered_user_messages[-1] if filtered_user_messages else None
        lines = [
            "# Active User Requirements",
            "",
            f"- updated_at: {utc_now()}",
            f"- quest_id: {quest_yaml.get('quest_id') or quest_root.name}",
            "",
            "## Long-Term Goal",
            "",
            quest_goal or "No long-term goal recorded yet.",
            "",
            "## Working Rule",
            "",
            "Treat the requirements in this file as higher priority than stale background plans.",
            "",
            "## Latest Added Requirement",
            "",
        ]
        if latest:
            latest_rendered = self._agent_visible_user_message_content(
                quest_root,
                content=str(latest.get("content") or ""),
                attachments=[dict(item) for item in (latest.get("attachments") or []) if isinstance(item, dict)],
            )
            lines.extend(
                [
                    f"- source: {latest.get('source') or 'local'}",
                    f"- created_at: {latest.get('created_at') or utc_now()}",
                    "",
                    latest_rendered or "No latest requirement text was captured.",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "No explicit user requirement has been recorded yet.",
                    "",
                ]
            )
        lines.extend(
            [
                "## Active Requirement History",
                "",
            ]
        )
        if filtered_user_messages:
            for index, item in enumerate(filtered_user_messages[-12:], start=1):
                source = str(item.get("source") or "local").strip() or "local"
                created_at = str(item.get("created_at") or "").strip() or "unknown"
                content = self._agent_visible_user_message_content(
                    quest_root,
                    content=str(item.get("content") or ""),
                    attachments=[dict(value) for value in (item.get("attachments") or []) if isinstance(value, dict)],
                ) or "(empty)"
                lines.append(f"{index}. [{source}] [{created_at}] {content}")
        else:
            lines.append("1. No user messages yet.")
        path = self._active_user_requirements_path(quest_root)
        write_text(path, "\n".join(lines).rstrip() + "\n")
        return path

    def claim_pending_user_message_for_turn(
        self,
        quest_id: str,
        *,
        message_id: str | None,
        run_id: str,
    ) -> dict[str, Any] | None:
        normalized_message_id = str(message_id or "").strip()
        if not normalized_message_id:
            return None
        quest_root = self._quest_root(quest_id)
        queue_payload = self._read_message_queue(quest_root)
        pending = [dict(item) for item in (queue_payload.get("pending") or [])]
        target_index: int | None = None
        for index in range(len(pending) - 1, -1, -1):
            if str(pending[index].get("message_id") or "").strip() == normalized_message_id:
                target_index = index
                break
        if target_index is None:
            self.update_runtime_state(
                quest_root=quest_root,
                pending_user_message_count=len(pending),
            )
            return None

        now = utc_now()
        claimed = {
            **pending.pop(target_index),
            "status": "accepted_by_run",
            "claimed_by_run_id": run_id,
            "claimed_at": now,
        }
        queue_payload["pending"] = pending
        queue_payload["completed"] = [*list(queue_payload.get("completed") or []), claimed][-200:]
        state_record = self._update_message_read_state(
            queue_payload,
            message_id=str(claimed.get("message_id") or "").strip() or None,
            client_message_id=str(claimed.get("client_message_id") or "").strip() or None,
            source=str(claimed.get("source") or "").strip() or None,
            conversation_id=str(claimed.get("conversation_id") or "").strip() or None,
            created_at=str(claimed.get("created_at") or "").strip() or None,
            read_state="read",
            read_reason="accepted_by_run",
            read_at=now,
            read_run_id=run_id,
        )
        self._write_message_queue(quest_root, queue_payload)
        self.update_runtime_state(
            quest_root=quest_root,
            pending_user_message_count=len(pending),
        )
        self.append_message_read_state_event(
            quest_id,
            message_id=str(claimed.get("message_id") or "").strip() or None,
            client_message_id=str(claimed.get("client_message_id") or "").strip() or None,
            read_state=str((state_record or {}).get("read_state") or "read"),
            read_reason=str((state_record or {}).get("read_reason") or "accepted_by_run"),
            read_at=str((state_record or {}).get("read_at") or now),
        )
        append_jsonl(
            self._interaction_journal_path(quest_root),
            {
                "event_id": generate_id("evt"),
                "type": "user_claimed_for_turn",
                "quest_id": quest_id,
                "message_id": normalized_message_id,
                "run_id": run_id,
                "created_at": now,
            },
        )
        return claimed

    def cancel_pending_user_messages(
        self,
        quest_id: str,
        *,
        reason: str,
        action: str,
        source: str,
    ) -> dict[str, Any]:
        quest_root = self._quest_root(quest_id)
        queue_payload = self._read_message_queue(quest_root)
        pending = [dict(item) for item in (queue_payload.get("pending") or [])]
        if not pending:
            self.update_runtime_state(
                quest_root=quest_root,
                pending_user_message_count=0,
            )
            return {
                "batch_id": None,
                "cancelled_count": 0,
                "cancelled": [],
            }

        now = utc_now()
        batch_id = generate_id("cancel")
        cancelled = [
            {
                **item,
                "status": reason,
                "cancelled_at": now,
                "cancelled_by_action": action,
                "cancelled_by_source": source,
            }
            for item in pending
        ]
        queue_payload["pending"] = []
        queue_payload["completed"] = [*list(queue_payload.get("completed") or []), *cancelled][-200:]
        for item in cancelled:
            self._update_message_read_state(
                queue_payload,
                message_id=str(item.get("message_id") or "").strip() or None,
                client_message_id=str(item.get("client_message_id") or "").strip() or None,
                source=str(item.get("source") or "").strip() or None,
                conversation_id=str(item.get("conversation_id") or "").strip() or None,
                created_at=str(item.get("created_at") or "").strip() or None,
                read_state="read",
                read_reason=reason,
                read_at=now,
            )
            self.append_message_read_state_event(
                quest_id,
                message_id=str(item.get("message_id") or "").strip() or None,
                client_message_id=str(item.get("client_message_id") or "").strip() or None,
                read_state="read",
                read_reason=reason,
                read_at=now,
            )
        self._write_message_queue(quest_root, queue_payload)
        append_jsonl(
            self._interaction_journal_path(quest_root),
            {
                "event_id": generate_id("evt"),
                "type": "user_queue_cancelled",
                "quest_id": quest_id,
                "batch_id": batch_id,
                "reason": reason,
                "action": action,
                "source": source,
                "message_ids": [item.get("message_id") for item in cancelled],
                "created_at": now,
            },
        )
        self.update_runtime_state(
            quest_root=quest_root,
            pending_user_message_count=0,
        )
        return {
            "batch_id": batch_id,
            "cancelled_count": len(cancelled),
            "cancelled": cancelled,
        }

    def record_artifact_interaction(
        self,
        quest_root: Path,
        *,
        interaction_id: str | None,
        artifact_id: str | None,
        kind: str,
        message: str,
        summary_preview: str | None = None,
        dedupe_key: str | None = None,
        response_phase: str | None = None,
        reply_mode: str | None = None,
        surface_actions: list[dict[str, Any]] | None = None,
        connector_hints: dict[str, Any] | None = None,
        created_at: str | None = None,
        counts_as_visible: bool = True,
        deliver_to_bound_conversations: bool | None = None,
    ) -> dict[str, Any]:
        timestamp = created_at or utc_now()
        payload = {
            "event_id": generate_id("evt"),
            "type": "artifact_outbound",
            "quest_id": quest_root.name,
            "interaction_id": interaction_id,
            "artifact_id": artifact_id,
            "kind": kind,
            "message": message,
            "summary_preview": str(summary_preview or "").strip() or None,
            "dedupe_key": str(dedupe_key or "").strip() or None,
            "response_phase": response_phase,
            "reply_mode": reply_mode,
            "surface_actions": [dict(item) for item in (surface_actions or []) if isinstance(item, dict)],
            "connector_hints": dict(connector_hints) if isinstance(connector_hints, dict) else {},
            "deliver_to_bound_conversations": (
                bool(deliver_to_bound_conversations)
                if deliver_to_bound_conversations is not None
                else None
            ),
            "created_at": timestamp,
        }
        append_jsonl(self._interaction_journal_path(quest_root), payload)
        runtime_updates: dict[str, Any] = {
            "quest_root": quest_root,
            "active_interaction_id": interaction_id or artifact_id,
            "last_tool_activity_at": timestamp,
            "last_tool_activity_name": "artifact.interact",
            "tool_calls_since_last_artifact_interact": 0,
            "pending_user_message_count": len((self._read_message_queue(quest_root).get("pending") or [])),
        }
        if counts_as_visible:
            runtime_updates["last_artifact_interact_at"] = timestamp
        self.update_runtime_state(**runtime_updates)
        return payload

    def record_tool_activity(
        self,
        quest_root: Path,
        *,
        tool_name: str,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        timestamp = created_at or utc_now()
        current_state = self._read_runtime_state(quest_root)
        next_count = int(current_state.get("tool_calls_since_last_artifact_interact") or 0) + 1
        payload = {
            "event_id": generate_id("evt"),
            "type": "tool_activity",
            "quest_id": quest_root.name,
            "tool_name": str(tool_name or "").strip() or "tool",
            "tool_calls_since_last_artifact_interact": next_count,
            "created_at": timestamp,
        }
        append_jsonl(self._interaction_journal_path(quest_root), payload)
        self.update_runtime_state(
            quest_root=quest_root,
            last_tool_activity_at=timestamp,
            last_tool_activity_name=payload["tool_name"],
            tool_calls_since_last_artifact_interact=next_count,
        )
        return payload

    @staticmethod
    def _seconds_since_iso_timestamp(value: str | None) -> int | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        candidate = normalized.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return max(int((datetime.now(UTC) - parsed.astimezone(UTC)).total_seconds()), 0)

    def artifact_interaction_watchdog_status(self, quest_root: Path) -> dict[str, Any]:
        runtime_state = self._read_runtime_state(quest_root)
        last_artifact_interact_at = str(runtime_state.get("last_artifact_interact_at") or "").strip() or None
        last_tool_activity_at = str(runtime_state.get("last_tool_activity_at") or "").strip() or None
        tool_count = int(runtime_state.get("tool_calls_since_last_artifact_interact") or 0)
        silence_seconds = self._seconds_since_iso_timestamp(last_artifact_interact_at)
        inspection_due = bool(
            tool_count >= 25
            or (
                tool_count > 0
                and silence_seconds is not None
                and silence_seconds >= 30 * 60
            )
        )
        return {
            "last_artifact_interact_at": last_artifact_interact_at,
            "seconds_since_last_artifact_interact": silence_seconds,
            "tool_calls_since_last_artifact_interact": tool_count,
            "last_tool_activity_at": last_tool_activity_at,
            "seconds_since_last_tool_activity": self._seconds_since_iso_timestamp(last_tool_activity_at),
            "last_tool_activity_name": str(runtime_state.get("last_tool_activity_name") or "").strip() or None,
            "inspection_due": inspection_due,
            "user_update_due": False,
        }

    def latest_artifact_interaction_records(self, quest_root: Path, limit: int = 10) -> list[dict[str, Any]]:
        items = [
            item
            for item in read_jsonl(self._interaction_journal_path(quest_root))
            if str(item.get("type") or "") in {"user_inbound", "artifact_outbound"}
        ]
        return items[-max(limit, 0):]

    def consume_pending_user_messages(
        self,
        quest_root: Path,
        *,
        interaction_id: str | None,
        limit: int = 10,
        delivery_reason: str = "artifact_mailbox",
    ) -> dict[str, Any]:
        queue_payload = self._read_message_queue(quest_root)
        pending = [dict(item) for item in (queue_payload.get("pending") or [])]
        recent_records = self.latest_artifact_interaction_records(quest_root, limit=max(limit, 10))
        delivered_messages: list[dict[str, Any]] = []
        delivered_state_records: list[dict[str, Any]] = []
        delivery_batch = None
        now = utc_now()

        if pending:
            batch_id = generate_id("delivery")
            for item in pending:
                delivered = {
                    **item,
                    "status": "completed",
                    "delivered_batch_id": batch_id,
                    "delivered_at": now,
                    "delivered_to_interaction_id": interaction_id,
                }
                delivered_messages.append(delivered)
            queue_payload["pending"] = []
            queue_payload["completed"] = [*list(queue_payload.get("completed") or []), *delivered_messages][-200:]
            for item in delivered_messages:
                state_record = self._update_message_read_state(
                    queue_payload,
                    message_id=str(item.get("message_id") or "").strip() or None,
                    client_message_id=str(item.get("client_message_id") or "").strip() or None,
                    source=str(item.get("source") or "").strip() or None,
                    conversation_id=str(item.get("conversation_id") or "").strip() or None,
                    created_at=str(item.get("created_at") or "").strip() or None,
                    read_state="read",
                    read_reason=delivery_reason,
                    read_at=now,
                    read_interaction_id=interaction_id,
                )
                self.append_message_read_state_event(
                    quest_root.name,
                    message_id=str(item.get("message_id") or "").strip() or None,
                    client_message_id=str(item.get("client_message_id") or "").strip() or None,
                    read_state=str((state_record or {}).get("read_state") or "read"),
                    read_reason=str((state_record or {}).get("read_reason") or delivery_reason),
                    read_at=str((state_record or {}).get("read_at") or now),
                )
                if state_record:
                    delivered_state_records.append(dict(state_record))
            self._write_message_queue(quest_root, queue_payload)
            append_jsonl(
                self._interaction_journal_path(quest_root),
                {
                    "event_id": generate_id("evt"),
                    "type": "user_delivery",
                    "quest_id": quest_root.name,
                    "batch_id": batch_id,
                    "interaction_id": interaction_id,
                    "message_ids": [item.get("message_id") for item in delivered_messages],
                    "created_at": now,
                },
            )
            self.update_runtime_state(
                quest_root=quest_root,
                pending_user_message_count=0,
                last_delivered_batch_id=batch_id,
                last_delivered_at=now,
            )
            delivery_batch = {
                "batch_id": batch_id,
                "message_ids": [item.get("message_id") for item in delivered_messages],
                "client_message_ids": [item.get("client_message_id") for item in delivered_messages],
                "delivered_at": now,
            }
        else:
            self.update_runtime_state(
                quest_root=quest_root,
                pending_user_message_count=0,
            )

        state_by_message_id = {
            str(item.get("message_id") or "").strip(): dict(item)
            for item in delivered_state_records
            if str(item.get("message_id") or "").strip()
        }
        state_by_client_message_id = {
            str(item.get("client_message_id") or "").strip(): dict(item)
            for item in delivered_state_records
            if str(item.get("client_message_id") or "").strip()
        }
        recent_inbound_messages = [
            {
                "message_id": item.get("message_id"),
                "client_message_id": item.get("client_message_id"),
                "source": str(item.get("conversation_id") or item.get("source") or "local").split(":", 1)[0],
                "conversation_id": item.get("conversation_id") or self._normalize_binding_source(str(item.get("source") or "local")),
                "sender": "user",
                "created_at": item.get("created_at"),
                "read_state": (
                    state_by_message_id.get(str(item.get("message_id") or "").strip())
                    or state_by_client_message_id.get(str(item.get("client_message_id") or "").strip())
                    or {}
                ).get("read_state") or "read",
                "read_reason": (
                    state_by_message_id.get(str(item.get("message_id") or "").strip())
                    or state_by_client_message_id.get(str(item.get("client_message_id") or "").strip())
                    or {}
                ).get("read_reason") or delivery_reason,
                "read_at": (
                    state_by_message_id.get(str(item.get("message_id") or "").strip())
                    or state_by_client_message_id.get(str(item.get("client_message_id") or "").strip())
                    or {}
                ).get("read_at") or now,
                "text": item.get("content") or "",
                "content": self._agent_visible_user_message_content(
                    quest_root,
                    content=str(item.get("content") or ""),
                    attachments=[dict(attachment) for attachment in (item.get("attachments") or []) if isinstance(attachment, dict)],
                ),
                "attachments": [dict(attachment) for attachment in (item.get("attachments") or []) if isinstance(attachment, dict)],
                "reply_to_interaction_id": item.get("reply_to_interaction_id"),
            }
            for item in delivered_messages
        ]
        if delivered_messages:
            lines = [
                self.localized_copy(
                    quest_root=quest_root,
                    zh="这是最新用户的要求（按时间顺序拼接）。这些消息优先于当前后台子任务：",
                    en="These are the latest user requirements in chronological order. They take priority over the current background subtask:",
                ),
                "",
                self.localized_copy(
                    quest_root=quest_root,
                    zh="- 先暂停当前非必要子任务，不要继续沿着旧计划埋头推进。",
                    en="- Pause any non-essential current subtask instead of continuing the stale plan blindly.",
                ),
                self.localized_copy(
                    quest_root=quest_root,
                    zh="- 立即发送一条有实际内容的 follow-up artifact.interact(...)；如果当前 connector 的运行时已经替你发过即时回执，就不要再重复发送一条只有“已收到/处理中”的确认。",
                    en="- Immediately send one substantive follow-up artifact.interact(...); if the active connector runtime already sent the transport-level receipt acknowledgement, do not send a redundant receipt-only message such as 'received' or 'processing'.",
                ),
                self.localized_copy(
                    quest_root=quest_root,
                    zh="- 如果可以直接回答，就在这次 follow-up artifact.interact(...) 里直接完整回答。",
                    en="- If you can answer directly, give the full answer in that follow-up artifact.interact(...).",
                ),
                self.localized_copy(
                    quest_root=quest_root,
                    zh="- 如果暂时不能直接回答，就在这次 follow-up artifact.interact(...) 里说明你将先处理该用户请求，给出简短计划、最近回传点与预计输出。",
                    en="- If you cannot answer directly yet, explain in that follow-up artifact.interact(...) that you will handle this user request first, and include a short plan, nearest report-back point, and expected output.",
                ),
                self.localized_copy(
                    quest_root=quest_root,
                    zh="- 完成该用户请求后，再立刻调用 artifact.interact(...) 汇报完整结果。",
                    en="- After completing that user request, immediately call artifact.interact(...) again with the full result.",
                ),
                self.localized_copy(
                    quest_root=quest_root,
                    zh="- 只有在用户新消息没有改变任务主线时，才恢复原来的后台任务。",
                    en="- Resume the older background task only if the new user message did not change the main objective.",
                ),
                "",
            ]
            for index, item in enumerate(delivered_messages, start=1):
                source = str(item.get("conversation_id") or item.get("source") or "local")
                rendered_content = self._agent_visible_user_message_content(
                    quest_root,
                    content=str(item.get("content") or ""),
                    attachments=[dict(attachment) for attachment in (item.get("attachments") or []) if isinstance(attachment, dict)],
                )
                lines.append(f"{index}. [{source}] {rendered_content}")
            agent_instruction = "\n".join(lines).strip()
        else:
            lines = [
                self.localized_copy(
                    quest_root=quest_root,
                    zh="当前用户并没有发送任何消息，请按照用户的要求继续进行任务。",
                    en="No new user message has arrived. Continue the task according to the user's requirements.",
                ),
                "",
                self.localized_copy(
                    quest_root=quest_root,
                    zh="以下是最近 10 次与 artifact 交互相关的记录：",
                    en="Here are the latest 10 artifact-related interaction records:",
                ),
            ]
            if recent_records:
                for index, item in enumerate(recent_records[-10:], start=1):
                    kind = str(item.get("type") or "")
                    created_at = str(item.get("created_at") or "")
                    if kind == "artifact_outbound":
                        lines.append(
                            f"{index}. [artifact][{item.get('kind') or 'progress'}][{created_at}] {item.get('message') or ''}"
                        )
                    else:
                        lines.append(
                            f"{index}. [user][{item.get('conversation_id') or item.get('source') or 'local'}][{created_at}] {item.get('content') or ''}"
                        )
            else:
                lines.append(
                    self.localized_copy(
                        quest_root=quest_root,
                        zh="1. 暂无历史交互记录。",
                        en="1. No recent interaction records.",
                    )
                )
            agent_instruction = "\n".join(lines).strip()

        return {
            "delivery_batch": delivery_batch,
            "recent_inbound_messages": recent_inbound_messages,
            "message_states": delivered_state_records,
            "recent_interaction_records": recent_records[-10:],
            "agent_instruction": agent_instruction,
            "queued_message_count_before_delivery": len(pending),
            "queued_message_count_after_delivery": len(queue_payload.get("pending") or []),
        }

    def _agent_visible_user_message_content(
        self,
        quest_root: Path,
        *,
        content: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> str:
        base = str(content or "").strip()
        normalized_attachments = [dict(item) for item in (attachments or []) if isinstance(item, dict)]
        if not normalized_attachments:
            return base
        lines: list[str] = []
        if base:
            lines.extend([base, ""])
        lines.append(
            self.localized_copy(
                quest_root=quest_root,
                zh="系统提示：用户刚刚发送了附件。请优先阅读这些 quest 本地文件，再继续处理这条请求：",
                en="System note: the user just sent attachments. Read these quest-local files first before continuing this request:",
            )
        )
        for index, item in enumerate(normalized_attachments, start=1):
            label = str(
                item.get("name")
                or item.get("file_name")
                or item.get("quest_relative_path")
                or item.get("path")
                or item.get("url")
                or f"attachment-{index}"
            ).strip()
            content_type = str(item.get("content_type") or item.get("mime_type") or "").strip()
            location = str(
                item.get("extracted_text_path")
                or item.get("ocr_text_path")
                or item.get("archive_manifest_path")
                or item.get("quest_relative_path")
                or item.get("url")
                or ("hidden" if str(item.get("path") or "").strip() else "unavailable")
            ).strip()
            error = str(item.get("download_error") or item.get("path_error") or "").strip()
            suffix = f" ({content_type})" if content_type else ""
            if error:
                lines.append(f"- {label}{suffix}: {location} | attachment_error={error}")
            else:
                lines.append(f"- {label}{suffix}: {location}")
        return "\n".join(lines).strip()

    @staticmethod
    def _document_resolution_root(quest_root: Path, workspace_root: Path, document_id: str) -> Path:
        if document_id.startswith(("questpath::", "memory::")):
            return quest_root
        return workspace_root

    @staticmethod
    def _resolve_document(quest_root: Path, document_id: str) -> tuple[Path, bool, str, str]:
        if document_id.startswith("memory::"):
            relative = document_id.split("::", 1)[1]
            if relative.startswith("."):
                raise ValueError("Document ID must stay within quest memory.")
            root = (quest_root / "memory").resolve()
            path = (root / relative).resolve()
            if path != root and root not in path.parents:
                raise ValueError("Document ID escapes quest memory.")
            return path, True, "quest_memory", "quest_memory"
        if document_id.startswith("skill::"):
            relative = document_id.split("::", 1)[1]
            root = (repo_root() / "src" / "skills").resolve()
            path = (root / relative).resolve()
            if path != root and root not in path.parents:
                raise ValueError("Document ID escapes skills root.")
            return path, False, "skill", "skill"
        if document_id.startswith("path::"):
            relative = document_id.split("::", 1)[1]
            path = resolve_within(quest_root, relative)
            if not path.exists() or not path.is_file():
                raise FileNotFoundError(f"Unknown quest file `{relative}`.")
            scope, writable = QuestService._classify_path_scope(quest_root, path)
            return path, writable, scope, scope
        if document_id.startswith("questpath::"):
            relative = document_id.split("::", 1)[1]
            path = resolve_within(quest_root, relative)
            if not path.exists() or not path.is_file():
                raise FileNotFoundError(f"Unknown quest file `{relative}`.")
            scope, writable = QuestService._classify_path_scope(quest_root, path)
            return path, writable, scope, scope
        if "/" in document_id or document_id.startswith("."):
            raise ValueError("Document ID must be a simple curated file name.")
        return quest_root / document_id, True, "quest", "quest_file"

    def _collect_nodes(
        self,
        quest_root: Path,
        *,
        roots: list[str],
        git_status: dict[str, str],
        changed_paths: dict[str, dict],
    ) -> list[dict]:
        nodes: list[dict] = []
        for relative in roots:
            root = quest_root / relative
            if not root.exists():
                continue
            if root.is_file():
                node = self._file_node(quest_root, path=root, git_status=git_status, changed_paths=changed_paths)
                if node is not None:
                    nodes.append(node)
                continue
            nodes.extend(self._tree_children(quest_root, root, git_status=git_status, changed_paths=changed_paths))
        return nodes

    def _snapshot_children(
        self,
        tree: dict[str, dict | None],
        *,
        revision: str,
        prefix: str,
    ) -> list[dict]:
        prefix_parts = PurePosixPath(prefix).parts
        subtree = tree
        for part in prefix_parts:
            child = subtree.get(part)
            if not isinstance(child, dict):
                return []
            subtree = child
        return self._snapshot_tree_nodes(subtree, revision=revision, prefix=prefix)

    def _snapshot_tree_nodes(
        self,
        tree: dict[str, dict | None],
        *,
        revision: str,
        prefix: str,
    ) -> list[dict]:
        nodes: list[dict] = []
        for name, child in sorted(tree.items(), key=lambda item: (item[1] is None, item[0].lower())):
            relative = f"{prefix}/{name}" if prefix else name
            if child is None:
                nodes.append(self._snapshot_file_node(revision, relative))
                continue
            nodes.append(
                {
                    "id": f"git-dir::{revision}::{relative}",
                    "name": name,
                    "path": relative,
                    "kind": "directory",
                    "scope": self._classify_relative_scope(relative)[0],
                    "folder_kind": self._snapshot_folder_kind(child, relative),
                    "children": self._snapshot_tree_nodes(child, revision=revision, prefix=relative),
                    "git_status": None,
                    "recently_changed": False,
                    "updated_at": utc_now(),
                }
            )
        return nodes

    def _snapshot_file_node(self, revision: str, relative: str) -> dict:
        return {
            "id": f"git-file::{revision}::{relative}",
            "name": Path(relative).name,
            "path": relative,
            "kind": "file",
            "scope": self._classify_relative_scope(relative)[0],
            "writable": False,
            "document_id": f"git::{revision}::{relative}",
            "open_kind": self._open_kind_for(Path(relative)),
            "git_status": None,
            "recently_changed": False,
            "updated_at": utc_now(),
            "size": None,
        }

    @staticmethod
    def _build_snapshot_tree(paths: list[str]) -> dict[str, dict | None]:
        tree: dict[str, dict | None] = {}
        for relative in paths:
            parts = PurePosixPath(relative).parts
            if not parts:
                continue
            cursor = tree
            for part in parts[:-1]:
                next_cursor = cursor.setdefault(part, {})
                if not isinstance(next_cursor, dict):
                    next_cursor = {}
                    cursor[part] = next_cursor
                cursor = next_cursor
            cursor[parts[-1]] = None
        return tree

    @staticmethod
    def _snapshot_folder_kind(tree: dict[str, dict | None], relative: str) -> str | None:
        normalized = str(relative or "").strip().replace("\\", "/")
        if not normalized or normalized.startswith(".ds/"):
            return None
        if not isinstance(tree, dict):
            return None
        if tree.get("main.tex") is None and "main.tex" in tree:
            return "latex"
        for name, child in tree.items():
            if child is not None:
                continue
            if Path(name).suffix.lower() == ".tex":
                return "latex"
        return None

    def _git_snapshot_paths(self, quest_root: Path, revision: str) -> list[str]:
        result = run_command(
            ["git", "ls-tree", "-r", "--full-tree", "--name-only", revision],
            cwd=quest_root,
            check=False,
        )
        if result.returncode != 0:
            raise FileNotFoundError(f"Unable to inspect git revision `{revision}`.")
        return [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip() and not self._skip_explorer_relative(line.strip())
        ]

    @staticmethod
    def _parse_git_document_id(document_id: str) -> tuple[str, str]:
        _prefix, revision, relative = (document_id.split("::", 2) + ["", "", ""])[:3]
        if not revision or not relative:
            raise ValueError("Git snapshot document id must include revision and path.")
        return revision, relative.lstrip("/")

    @staticmethod
    def _git_revision_exists(quest_root: Path, revision: str) -> bool:
        result = run_command(["git", "rev-parse", "--verify", revision], cwd=quest_root, check=False)
        return result.returncode == 0

    @staticmethod
    def _read_git_text(quest_root: Path, revision: str, relative: str) -> str:
        result = run_command(["git", "show", f"{revision}:{relative}"], cwd=quest_root, check=False)
        if result.returncode != 0:
            raise FileNotFoundError(f"File `{relative}` does not exist at `{revision}`.")
        return result.stdout

    @staticmethod
    def _read_git_bytes(quest_root: Path, revision: str, relative: str) -> bytes:
        result = run_command_bytes(
            ["git", "show", f"{revision}:{relative}"],
            cwd=quest_root,
            check=False,
        )
        if result.returncode != 0:
            raise FileNotFoundError(f"File `{relative}` does not exist at `{revision}`.")
        return bytes(result.stdout)

    @staticmethod
    def _git_blob_id(quest_root: Path, revision: str, relative: str) -> str | None:
        result = run_command(["git", "rev-parse", f"{revision}:{relative}"], cwd=quest_root, check=False)
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    @staticmethod
    def _git_blob_size(quest_root: Path, revision: str, relative: str) -> int | None:
        object_id_result = run_command(["git", "rev-parse", f"{revision}:{relative}"], cwd=quest_root, check=False)
        object_id = object_id_result.stdout.strip() if object_id_result.returncode == 0 else ""
        if not object_id:
            return None
        size_result = run_command(["git", "cat-file", "-s", object_id], cwd=quest_root, check=False)
        if size_result.returncode != 0:
            return None
        try:
            return int(size_result.stdout.strip())
        except ValueError:
            return None

    def _tree_children(
        self,
        quest_root: Path,
        root: Path,
        *,
        git_status: dict[str, str],
        changed_paths: dict[str, dict],
        profile: str | None = None,
        depth: int = 0,
    ) -> list[dict]:
        if not root.exists():
            return []
        try:
            entries = list(root.iterdir())
        except OSError:
            return []

        def _sort_key(item: Path) -> tuple[bool, str]:
            try:
                return item.is_file(), item.name.lower()
            except OSError:
                return True, item.name.lower()

        nodes: list[dict] = []
        for path in sorted(entries, key=_sort_key):
            try:
                if self._skip_explorer_path(quest_root, path):
                    continue
                relative = path.relative_to(quest_root).as_posix()
                if self._skip_explorer_profile_relative(relative, profile):
                    continue
            except OSError:
                continue
            try:
                is_dir = path.is_dir()
            except OSError:
                continue
            if is_dir:
                truncate_children = self._truncate_explorer_directory(relative, profile=profile, depth=depth)
                children = (
                    []
                    if truncate_children
                    else self._tree_children(
                        quest_root,
                        path,
                        git_status=git_status,
                        changed_paths=changed_paths,
                        profile=profile,
                        depth=depth + 1,
                    )
                )
                nodes.append(
                    self._directory_node(
                        quest_root,
                        path=path,
                        children=children,
                        git_status=git_status,
                        changed_paths=changed_paths,
                    )
                )
            else:
                node = self._file_node(quest_root, path=path, git_status=git_status, changed_paths=changed_paths)
                if node is not None:
                    nodes.append(node)
        return nodes

    def _directory_node(
        self,
        quest_root: Path,
        *,
        path: Path,
        children: list[dict],
        git_status: dict[str, str],
        changed_paths: dict[str, dict],
    ) -> dict:
        try:
            relative = path.relative_to(quest_root).as_posix()
            scope = self._classify_path_scope(quest_root, path)[0]
        except (OSError, ValueError):
            relative = path.name
            scope = "quest"
        folder_kind = self._folder_kind_for(path, relative)
        return {
            "id": f"dir::{relative}",
            "name": path.name,
            "path": relative,
            "kind": "directory",
            "scope": scope,
            "folder_kind": folder_kind,
            "children": children,
            "git_status": git_status.get(relative),
            "recently_changed": relative in changed_paths,
            "updated_at": utc_now(),
        }

    def _file_node(
        self,
        quest_root: Path,
        *,
        path: Path,
        git_status: dict[str, str],
        changed_paths: dict[str, dict],
    ) -> dict | None:
        try:
            if not path.exists() or not path.is_file() or self._skip_explorer_path(quest_root, path):
                return None
            relative = path.relative_to(quest_root).as_posix()
            scope, writable = self._classify_path_scope(quest_root, path)
            size = path.stat().st_size
        except (OSError, ValueError):
            return None
        changed_meta = changed_paths.get(str(path)) or changed_paths.get(relative)
        open_kind = self._open_kind_for(path)
        return {
            "id": f"file::{relative}",
            "name": path.name,
            "path": relative,
            "kind": "file",
            "scope": scope,
            "writable": writable,
            "document_id": f"path::{relative}",
            "open_kind": open_kind,
            "git_status": git_status.get(relative),
            "recently_changed": changed_meta is not None,
            "updated_at": utc_now(),
            "size": size,
        }

    @staticmethod
    def _skip_explorer_path(quest_root: Path, path: Path) -> bool:
        relative = path.relative_to(quest_root).as_posix()
        return QuestService._skip_explorer_relative(relative)

    @staticmethod
    def _skip_explorer_relative(relative: str) -> bool:
        if relative.startswith(".git/") or relative == ".git":
            return True
        if relative.startswith(".ds/worktrees/"):
            return True
        heavy_runtime_roots = {
            ".ds/bash_exec",
            ".ds/runs",
            ".ds/codex_history",
            ".ds/codex_homes",
            ".ds/claude-home",
            ".ds/opencode-home",
            ".ds/evidence_packets",
            ".ds/slim_backups",
            ".ds/cold_archive",
        }
        normalized = relative.strip("/")
        if any(normalized == root or normalized.startswith(f"{root}/") for root in heavy_runtime_roots):
            return True
        parts = PurePosixPath(relative).parts
        return "__pycache__" in parts or ".pytest_cache" in parts

    @staticmethod
    def _skip_explorer_profile_relative(relative: str, profile: str | None) -> bool:
        if profile != "mobile":
            return False
        normalized = relative.strip("/")
        if not normalized:
            return False
        parts = PurePosixPath(normalized).parts
        top = parts[0] if parts else normalized
        if top in {".codex", ".claude", ".kimi", ".opencode", ".ds", "tmp", "userfiles", "artifacts"}:
            return True
        if top.startswith(".") and normalized not in {".gitignore"}:
            return True
        return False

    @staticmethod
    def _truncate_explorer_directory(relative: str, *, profile: str | None, depth: int) -> bool:
        if profile != "mobile":
            return False
        normalized = relative.strip("/")
        if not normalized:
            return False
        parts = PurePosixPath(normalized).parts
        top = parts[0] if parts else normalized
        if top == "memory":
            return False
        if top == "baselines":
            return depth >= 1
        if top in {"literature", "paper", "experiments", "handoffs"}:
            return depth >= 2
        return depth >= 1

    @staticmethod
    def _classify_path_scope(quest_root: Path, path: Path) -> tuple[str, bool]:
        relative = path.relative_to(quest_root).as_posix()
        return QuestService._classify_relative_scope(relative)

    @staticmethod
    def _classify_relative_scope(relative: str) -> tuple[str, bool]:
        top = PurePosixPath(relative).parts[0] if PurePosixPath(relative).parts else relative
        if relative in {"brief.md", "plan.md", "status.md", "SUMMARY.md"}:
            return "core", True
        if top == "memory":
            return "memory", True
        if top in {"literature", "baselines", "experiments", "paper", "handoffs"}:
            return "research", True
        if top == "artifacts":
            return "artifacts", False
        if relative.startswith(".ds/codex_history/"):
            return "runner_history", False
        if relative.startswith(".ds/"):
            return "runtime", False
        return "quest", True

    @staticmethod
    def _open_kind_for(path: Path) -> str:
        return QuestService._renderer_hint_for(path)[0]

    @staticmethod
    def _folder_kind_for(path: Path, relative: str) -> str | None:
        try:
            if not path.exists() or not path.is_dir():
                return None
        except OSError:
            return None
        if QuestService._looks_like_latex_folder(path, relative):
            return "latex"
        return None

    @staticmethod
    def _looks_like_latex_folder(path: Path, relative: str) -> bool:
        normalized = str(relative or "").strip().replace("\\", "/")
        if not normalized:
            return False
        try:
            if (path / "main.tex").is_file():
                return True
        except OSError:
            return False
        if normalized.startswith(".ds/"):
            return False
        try:
            return any(item.is_file() and item.suffix.lower() == ".tex" for item in path.iterdir())
        except OSError:
            return False

    @staticmethod
    def _renderer_hint_for(path: Path) -> tuple[str, str]:
        suffix = path.suffix.lower()
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if suffix in {".md", ".markdown"}:
            return "markdown", mime_type or "text/markdown"
        if suffix in {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".yml", ".toml", ".sh", ".txt", ".log", ".ini", ".cfg"}:
            return "code", mime_type
        if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"} or mime_type.startswith("image/"):
            return "image", mime_type
        if suffix == ".pdf" or mime_type == "application/pdf":
            return "pdf", "application/pdf"
        if mime_type.startswith("text/"):
            return "text", mime_type
        return "binary", mime_type

    @staticmethod
    def _is_text_document(path: Path, mime_type: str, renderer_hint: str) -> bool:
        if renderer_hint in {"markdown", "code", "text"}:
            return True
        if mime_type.startswith("text/"):
            return True
        return path.suffix.lower() in {".jsonl", ".csv", ".tsv"}

    @staticmethod
    def _git_status_map(quest_root: Path) -> dict[str, str]:
        result = run_command(["git", "status", "--porcelain"], cwd=quest_root, check=False)
        mapping: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if len(line) < 4:
                continue
            status = line[:2].strip() or "??"
            relative = line[3:].strip()
            if " -> " in relative:
                relative = relative.split(" -> ", 1)[1].strip()
            if relative:
                mapping[relative] = status
        return mapping


def _compact_text(value: object, *, limit: int = 1200) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, indent=2)
        except TypeError:
            text = str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _extract_history_texts(event: dict) -> list[str]:
    texts: list[str] = []
    for key in ("text", "content", "message", "summary"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            texts.append(value.strip())
    item = event.get("item")
    if isinstance(item, dict):
        for key in ("text", "content", "message", "summary"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                texts.append(value.strip())
        content = item.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    value = block.get("text") or block.get("content")
                    if isinstance(value, str) and value.strip():
                        texts.append(value.strip())
    delta = event.get("delta")
    if isinstance(delta, dict):
        for key in ("text", "content", "arguments"):
            value = delta.get(key)
            if isinstance(value, str) and value.strip():
                texts.append(value.strip())
    return texts


def _dedupe_history_texts(values: list[object]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _tool_call_id(event: dict, item: dict) -> str:
    for value in (
        item.get("call_id"),
        item.get("tool_call_id"),
        item.get("id"),
        event.get("call_id"),
        event.get("tool_call_id"),
        event.get("id"),
    ):
        if value:
            return str(value)
    return generate_id("tool")


def _tool_name(event: dict, item: dict) -> str:
    for value in (
        item.get("name"),
        item.get("function"),
        event.get("name"),
        event.get("function"),
    ):
        if isinstance(value, dict):
            nested = value.get("name")
            if nested:
                return str(nested)
        elif value:
            return str(value)
    return "tool"


def _structured_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except TypeError:
        return str(value)


def _is_bash_exec_item(event: dict, item: dict) -> bool:
    server = str(item.get("server") or event.get("server") or "").strip()
    tool = str(item.get("tool") or event.get("tool") or "").strip()
    return server == "bash_exec" and tool == "bash_exec"


def _tool_args(event: dict, item: dict) -> str:
    if _is_bash_exec_item(event, item):
        for value in (
            item.get("arguments"),
            event.get("arguments"),
            item.get("input"),
            event.get("input"),
        ):
            text = _structured_text(value)
            if text:
                return text
        return ""
    for value in (
        item.get("command"),
        item.get("query"),
        item.get("action"),
        item.get("arguments"),
        item.get("input"),
        event.get("arguments"),
        event.get("input"),
        event.get("query"),
        event.get("action"),
        event.get("delta"),
    ):
        text = _compact_text(value, limit=1200)
        if text:
            return text
    return ""


def _tool_output(event: dict, item: dict) -> str:
    if _is_bash_exec_item(event, item):
        for value in (
            item.get("result"),
            item.get("output"),
            item.get("content"),
            item.get("error"),
            event.get("result"),
            event.get("output"),
            event.get("content"),
            event.get("error"),
            item.get("aggregated_output"),
            event.get("aggregated_output"),
        ):
            text = _structured_text(value)
            if text:
                return text
        return ""
    for value in (
        item.get("aggregated_output"),
        item.get("changes"),
        item.get("output"),
        item.get("result"),
        item.get("content"),
        item.get("error"),
        event.get("aggregated_output"),
        event.get("changes"),
        event.get("output"),
        event.get("result"),
        event.get("content"),
        event.get("error"),
    ):
        text = _compact_text(value, limit=1200)
        if text:
            return text
    return ""


def _mcp_result_payload(item: dict) -> dict:
    result = item.get("result")
    if isinstance(result, dict):
        structured = result.get("structured_content") or result.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        return result
    return {}


def _mcp_tool_metadata(*, quest_id: str, run_id: str, server: str, tool: str, item: dict) -> dict:
    metadata: dict[str, Any] = {
        "mcp_server": server,
        "mcp_tool": tool,
        "session_id": f"quest:{quest_id}",
        "agent_id": "pi",
        "agent_instance_id": run_id,
        "quest_id": quest_id,
    }
    arguments = item.get("arguments")
    if isinstance(arguments, dict):
        for key in ("command", "workdir", "mode", "timeout_seconds", "comment"):
            if key in arguments:
                metadata[key] = arguments.get(key)
        if server == "bash_exec" and tool == "bash_exec" and isinstance(arguments.get("id"), str):
            metadata["bash_id"] = arguments.get("id")
    result_payload = _mcp_result_payload(item)
    if server == "bash_exec" and tool == "bash_exec":
        for key in (
            "bash_id",
            "status",
            "command",
            "workdir",
            "cwd",
            "kind",
            "comment",
            "started_at",
            "finished_at",
            "exit_code",
            "stop_reason",
            "last_progress",
            "log_path",
            "watchdog_after_seconds",
        ):
            if key in result_payload:
                metadata[key] = result_payload.get(key)
    return metadata


def _parse_codex_history(history_root: Path, *, quest_id: str, run_id: str, skill_id: str | None) -> list[dict]:
    history_path = history_root / "events.jsonl"
    if not history_path.exists():
        return []

    entries: list[dict] = []
    known_tool_names: dict[str, str] = {}

    for raw in read_jsonl_tail(history_path, _CODEX_HISTORY_TAIL_LIMIT):
        timestamp = raw.get("timestamp")
        event = raw.get("event")
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "")
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        item_type = str(item.get("type") or event.get("item_type") or "")

        if item_type == "command_execution":
            tool_call_id = _tool_call_id(event, item)
            tool_name = "shell_command"
            known_tool_names[tool_call_id] = tool_name
            if event_type == "item.started" or str(item.get("status") or "") == "in_progress":
                entries.append(
                    {
                        "id": f"tool:{run_id}:{tool_call_id}:{len(entries)}",
                        "kind": "tool_call",
                        "run_id": run_id,
                        "skill_id": skill_id,
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "title": tool_name,
                        "summary": "Command execution started.",
                        "status": "calling",
                        "created_at": timestamp,
                        "args": _tool_args(event, item),
                        "raw_event_type": event_type,
                    }
                )
            else:
                entries.append(
                    {
                        "id": f"tool-result:{run_id}:{tool_call_id}:{len(entries)}",
                        "kind": "tool_result",
                        "run_id": run_id,
                        "skill_id": skill_id,
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "title": tool_name,
                        "summary": "Command execution completed.",
                        "status": str(item.get("status") or "completed"),
                        "created_at": timestamp,
                        "args": _tool_args(event, item),
                        "output": _tool_output(event, item),
                        "raw_event_type": event_type,
                    }
                )
            continue

        if item_type == "web_search":
            tool_call_id = _tool_call_id(event, item)
            tool_name = "web_search"
            search_payload = extract_web_search_payload(item)
            known_tool_names[tool_call_id] = tool_name
            if event_type == "item.started":
                entries.append(
                    {
                        "id": f"tool:{run_id}:{tool_call_id}:{len(entries)}",
                        "kind": "tool_call",
                        "run_id": run_id,
                        "skill_id": skill_id,
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "title": tool_name,
                        "summary": "Web search started.",
                        "status": "calling",
                        "created_at": timestamp,
                        "args": _compact_text(search_payload, limit=2400),
                        "metadata": {"search": search_payload},
                        "raw_event_type": event_type,
                    }
                )
            else:
                entries.append(
                    {
                        "id": f"tool-result:{run_id}:{tool_call_id}:{len(entries)}",
                        "kind": "tool_result",
                        "run_id": run_id,
                        "skill_id": skill_id,
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "title": tool_name,
                        "summary": "Web search completed.",
                        "status": "completed",
                        "created_at": timestamp,
                        "args": _compact_text(search_payload, limit=2400),
                        "output": _compact_text(search_payload, limit=2400),
                        "metadata": {"search": search_payload},
                        "raw_event_type": event_type,
                    }
                )
            continue

        if item_type == "file_change":
            tool_call_id = _tool_call_id(event, item)
            tool_name = "file_change"
            known_tool_names[tool_call_id] = tool_name
            entries.append(
                {
                    "id": f"tool-result:{run_id}:{tool_call_id}:{len(entries)}",
                    "kind": "tool_result",
                    "run_id": run_id,
                    "skill_id": skill_id,
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "title": tool_name,
                    "summary": "File change recorded.",
                    "status": str(item.get("status") or "completed"),
                    "created_at": timestamp,
                    "output": _tool_output(event, item),
                    "raw_event_type": event_type,
                }
            )
            continue

        if item_type == "mcp_tool_call":
            tool_call_id = _tool_call_id(event, item)
            server = str(item.get("server") or "").strip()
            tool = str(item.get("tool") or "").strip()
            tool_name = f"{server}.{tool}" if server and tool else tool or server or "mcp_tool"
            metadata = _mcp_tool_metadata(
                quest_id=quest_id,
                run_id=run_id,
                server=server,
                tool=tool,
                item=item,
            )
            known_tool_names[tool_call_id] = tool_name
            if event_type == "item.started" or str(item.get("status") or "") == "in_progress":
                entries.append(
                    {
                        "id": f"tool:{run_id}:{tool_call_id}:{len(entries)}",
                        "kind": "tool_call",
                        "run_id": run_id,
                        "skill_id": skill_id,
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "title": tool_name,
                        "summary": "MCP tool invocation started.",
                        "status": "calling",
                        "created_at": timestamp,
                        "args": _tool_args(event, item),
                        "mcp_server": server,
                        "mcp_tool": tool,
                        "metadata": metadata,
                        "raw_event_type": event_type,
                    }
                )
            else:
                entries.append(
                    {
                        "id": f"tool-result:{run_id}:{tool_call_id}:{len(entries)}",
                        "kind": "tool_result",
                        "run_id": run_id,
                        "skill_id": skill_id,
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "title": tool_name,
                        "summary": "MCP tool invocation completed.",
                        "status": str(item.get("status") or "completed"),
                        "created_at": timestamp,
                        "args": _tool_args(event, item),
                        "output": _tool_output(event, item),
                        "mcp_server": server,
                        "mcp_tool": tool,
                        "metadata": metadata,
                        "raw_event_type": event_type,
                    }
                )
            continue

        if item_type in {"function_call", "custom_tool_call", "tool_call"} or "function_call" in event_type or "tool_call" in event_type:
            tool_call_id = _tool_call_id(event, item)
            tool_name = _tool_name(event, item)
            known_tool_names[tool_call_id] = tool_name
            entries.append(
                {
                    "id": f"tool:{run_id}:{tool_call_id}:{len(entries)}",
                    "kind": "tool_call",
                    "run_id": run_id,
                    "skill_id": skill_id,
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "title": tool_name,
                    "summary": "Tool invocation started.",
                    "status": "calling" if "delta" in event_type or "added" in event_type else "completed",
                    "created_at": timestamp,
                    "args": _tool_args(event, item),
                    "raw_event_type": event_type,
                }
            )
            continue

        if item_type in {"function_call_output", "custom_tool_call_output", "tool_result", "tool_call_output"} or "function_call_output" in event_type or "tool_result" in event_type:
            tool_call_id = _tool_call_id(event, item)
            tool_name = known_tool_names.get(tool_call_id) or _tool_name(event, item)
            entries.append(
                {
                    "id": f"tool-result:{run_id}:{tool_call_id}:{len(entries)}",
                    "kind": "tool_result",
                    "run_id": run_id,
                    "skill_id": skill_id,
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "title": tool_name,
                    "summary": "Tool result received.",
                    "status": "completed",
                    "created_at": timestamp,
                    "args": _tool_args(event, item),
                    "output": _tool_output(event, item),
                    "raw_event_type": event_type,
                }
            )
            continue

        if item_type in {"reasoning", "reasoning_summary"} or "reasoning" in event_type:
            texts = "\n".join(_extract_history_texts(event)).strip()
            if texts:
                entries.append(
                    {
                        "id": f"thought:{run_id}:{len(entries)}",
                        "kind": "thought",
                        "run_id": run_id,
                        "skill_id": skill_id,
                        "title": "Reasoning",
                        "summary": texts,
                        "created_at": timestamp,
                        "raw_event_type": event_type,
                    }
                )
            continue

        if item_type == "agent_message":
            texts = _dedupe_history_texts(_extract_history_texts(event))
            for text in texts:
                entries.append(
                    {
                        "id": f"thought:{run_id}:{len(entries)}",
                        "kind": "thought",
                        "run_id": run_id,
                        "skill_id": skill_id,
                        "title": "Agent message",
                        "summary": text,
                        "created_at": timestamp,
                        "raw_event_type": event_type,
                    }
                )

    return entries[-60:]
