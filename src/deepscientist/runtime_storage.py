from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


EVENT_ID_RE = re.compile(rb'"event_id"\s*:\s*"([^"]+)"')
TYPE_RE = re.compile(rb'"(?:type|event_type)"\s*:\s*"([^"]+)"')
RUN_ID_RE = re.compile(rb'"run_id"\s*:\s*"([^"]+)"')
TOOL_NAME_RE = re.compile(rb'"tool_name"\s*:\s*"([^"]+)"')
TIMESTAMP_RE = re.compile(rb'"timestamp"\s*:\s*"([^"]+)"')
SEQ_RE = re.compile(rb'"seq"\s*:\s*(\d+)')
STREAM_RE = re.compile(rb'"stream"\s*:\s*"([^"]+)"')


def _extract(pattern: re.Pattern[bytes], raw: bytes) -> str | None:
    match = pattern.search(raw)
    if match is None:
        return None
    try:
        return match.group(1).decode("utf-8", errors="ignore").strip() or None
    except Exception:
        return None


def _replace_file(path: Path, lines: list[bytes]) -> None:
    with NamedTemporaryFile("wb", delete=False, dir=path.parent, prefix=f"{path.name}.", suffix=".tmp") as handle:
        temp_path = Path(handle.name)
        for line in lines:
            handle.write(line)
    temp_path.replace(path)


def _backup_raw_line(backup_root: Path, *, file_rel: str, line_no: int, raw: bytes) -> Path:
    digest = hashlib.sha256(raw).hexdigest()[:16]
    safe_rel = file_rel.replace("/", "__")
    backup_name = f"{safe_rel}__line_{line_no:06d}__{digest}.jsonl.gz"
    backup_path = backup_root / backup_name
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(backup_path, "wb") as handle:
        handle.write(raw)
    return backup_path


def _event_placeholder(raw: bytes, *, original_bytes: int, backup_ref: str, line_no: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event_id": _extract(EVENT_ID_RE, raw) or f"evt-slim-{line_no}",
        "type": _extract(TYPE_RE, raw) or "runner.tool_result",
        "run_id": _extract(RUN_ID_RE, raw),
        "tool_name": _extract(TOOL_NAME_RE, raw),
        "status": "compacted",
        "summary": f"Oversized quest event payload ({original_bytes} bytes) was compacted into a quest-local backup.",
        "oversized_event": True,
        "original_bytes": original_bytes,
        "backup_ref": backup_ref,
        "created_at": datetime.now(UTC).isoformat(),
    }
    return {key: value for key, value in payload.items() if value is not None}


def _bash_log_placeholder(raw: bytes, *, original_bytes: int, backup_ref: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "seq": int(_extract(SEQ_RE, raw) or 0),
        "stream": _extract(STREAM_RE, raw) or "stdout",
        "timestamp": _extract(TIMESTAMP_RE, raw),
        "line": f"[compacted oversized bash log entry: {original_bytes} bytes -> {backup_ref}]",
        "oversized_payload": True,
        "original_bytes": original_bytes,
        "backup_ref": backup_ref,
    }
    return {key: value for key, value in payload.items() if value is not None}


def _stdout_placeholder(raw: bytes, *, original_bytes: int, backup_ref: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "timestamp": _extract(TIMESTAMP_RE, raw),
        "line": f"[compacted oversized stdout entry: {original_bytes} bytes -> {backup_ref}]",
        "oversized_payload": True,
        "original_bytes": original_bytes,
        "backup_ref": backup_ref,
    }
    return {key: value for key, value in payload.items() if value is not None}


def _codex_history_placeholder(raw: bytes, *, original_bytes: int, backup_ref: str) -> dict[str, Any]:
    return {
        "timestamp": _extract(TIMESTAMP_RE, raw),
        "event": {
            "type": "oversized_payload",
            "summary": f"Oversized codex history entry ({original_bytes} bytes) was compacted into a quest-local backup.",
            "backup_ref": backup_ref,
            "original_bytes": original_bytes,
        },
    }


def _placeholder_for(
    path: Path,
    raw: bytes,
    *,
    original_bytes: int,
    backup_ref: str,
    file_rel: str,
    line_no: int,
) -> dict[str, Any]:
    normalized = file_rel.replace("\\", "/")
    if normalized == ".ds/events.jsonl":
        return _event_placeholder(raw, original_bytes=original_bytes, backup_ref=backup_ref, line_no=line_no)
    if normalized.startswith(".ds/bash_exec/") and normalized.endswith("/log.jsonl"):
        return _bash_log_placeholder(raw, original_bytes=original_bytes, backup_ref=backup_ref)
    if normalized.startswith(".ds/runs/") and normalized.endswith("/stdout.jsonl"):
        return _stdout_placeholder(raw, original_bytes=original_bytes, backup_ref=backup_ref)
    if normalized.startswith(".ds/codex_history/") and normalized.endswith("/events.jsonl"):
        return _codex_history_placeholder(raw, original_bytes=original_bytes, backup_ref=backup_ref)
    return {
        "oversized_payload": True,
        "original_bytes": original_bytes,
        "backup_ref": backup_ref,
    }


def _iter_jsonl_slim_targets(ds_root: Path) -> list[Path]:
    files: list[Path] = []
    direct_events = ds_root / "events.jsonl"
    if direct_events.exists():
        files.append(direct_events)
    files.extend(sorted((ds_root / "bash_exec").glob("**/log.jsonl")))
    files.extend(sorted((ds_root / "codex_history").glob("**/events.jsonl")))
    files.extend(sorted((ds_root / "runs").glob("**/stdout.jsonl")))
    return [path for path in files if path.is_file()]


def slim_quest_jsonl(quest_root: Path, *, threshold_bytes: int) -> dict[str, Any]:
    resolved_root = Path(quest_root).expanduser().resolve()
    ds_root = resolved_root / ".ds"
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_root = ds_root / "slim_backups" / timestamp
    manifest: dict[str, Any] = {
        "quest_root": str(resolved_root),
        "threshold_bytes": threshold_bytes,
        "backup_root": str(backup_root),
        "processed_at": datetime.now(UTC).isoformat(),
        "files": [],
        "compacted_line_count": 0,
        "compacted_bytes_total": 0,
    }
    if threshold_bytes <= 0 or not ds_root.exists():
        return manifest

    for path in _iter_jsonl_slim_targets(ds_root):
        rel = path.relative_to(resolved_root).as_posix()
        line_no = 0
        compacted_lines = 0
        compacted_bytes = 0
        rewritten: list[bytes] = []
        with path.open("rb") as handle:
            for raw in handle:
                line_no += 1
                line_bytes = len(raw)
                if line_bytes <= threshold_bytes:
                    rewritten.append(raw)
                    continue
                backup_path = _backup_raw_line(backup_root, file_rel=rel, line_no=line_no, raw=raw)
                backup_ref = backup_path.relative_to(resolved_root).as_posix()
                placeholder = _placeholder_for(
                    path,
                    raw,
                    original_bytes=line_bytes,
                    backup_ref=backup_ref,
                    file_rel=rel,
                    line_no=line_no,
                )
                rewritten.append((json.dumps(placeholder, ensure_ascii=False) + "\n").encode("utf-8"))
                compacted_lines += 1
                compacted_bytes += line_bytes
        if compacted_lines:
            _replace_file(path, rewritten)
            manifest["files"].append(
                {
                    "path": rel,
                    "compacted_lines": compacted_lines,
                    "compacted_bytes": compacted_bytes,
                }
            )
            manifest["compacted_line_count"] += compacted_lines
            manifest["compacted_bytes_total"] += compacted_bytes

    if manifest["compacted_line_count"]:
        backup_root.mkdir(parents=True, exist_ok=True)
        manifest_path = backup_root / "manifest.json"
        manifest["manifest_path"] = str(manifest_path)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _iter_dedupe_targets(worktrees_root: Path, *, min_bytes: int) -> list[Path]:
    patterns = [
        "**/.codex/sessions/**/*.jsonl",
        "**/experiments/**/*.json",
    ]
    files: list[Path] = []
    for pattern in patterns:
        for path in worktrees_root.glob(pattern):
            if not path.is_file():
                continue
            try:
                if path.stat().st_size < min_bytes:
                    continue
            except OSError:
                continue
            files.append(path)
    return sorted(files)


def _replace_with_hardlink(target: Path, source: Path) -> None:
    with NamedTemporaryFile("wb", delete=False, dir=target.parent, prefix=f"{target.name}.", suffix=".linktmp") as handle:
        temp_path = Path(handle.name)
    try:
        temp_path.unlink(missing_ok=True)
        os.link(source, temp_path)
        temp_path.replace(target)
    finally:
        temp_path.unlink(missing_ok=True)


def dedupe_worktree_files(quest_root: Path, *, min_bytes: int) -> dict[str, Any]:
    resolved_root = Path(quest_root).expanduser().resolve()
    worktrees_root = resolved_root / ".ds" / "worktrees"
    manifest: dict[str, Any] = {
        "quest_root": str(resolved_root),
        "worktrees_root": str(worktrees_root),
        "min_bytes": min_bytes,
        "groups_examined": 0,
        "files_relinked": 0,
        "bytes_deduped": 0,
        "groups": [],
    }
    if min_bytes <= 0 or not worktrees_root.exists():
        return manifest

    size_buckets: dict[int, list[Path]] = {}
    for path in _iter_dedupe_targets(worktrees_root, min_bytes=min_bytes):
        try:
            size_buckets.setdefault(path.stat().st_size, []).append(path)
        except OSError:
            continue

    for size, paths in sorted(size_buckets.items(), key=lambda item: -item[0]):
        if len(paths) < 2:
            continue
        manifest["groups_examined"] += 1
        hash_buckets: dict[str, list[Path]] = {}
        for path in paths:
            try:
                hash_buckets.setdefault(_sha256(path), []).append(path)
            except OSError:
                continue
        for digest, dupes in hash_buckets.items():
            if len(dupes) < 2:
                continue
            canonical = dupes[0]
            relinked: list[str] = []
            for duplicate in dupes[1:]:
                try:
                    if canonical.stat().st_ino == duplicate.stat().st_ino:
                        continue
                except OSError:
                    continue
                _replace_with_hardlink(duplicate, canonical)
                manifest["files_relinked"] += 1
                manifest["bytes_deduped"] += size
                relinked.append(str(duplicate.relative_to(resolved_root)))
            if relinked:
                manifest["groups"].append(
                    {
                        "sha256": digest,
                        "size_bytes": size,
                        "canonical": str(canonical.relative_to(resolved_root)),
                        "relinked": relinked,
                    }
                )
    return manifest


__all__ = ["dedupe_worktree_files", "slim_quest_jsonl"]
