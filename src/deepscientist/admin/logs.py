from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from ..shared import ensure_dir, read_json


_BEARER_RE = re.compile(r"(Bearer\s+)([A-Za-z0-9\-._~+/]+=*)", re.IGNORECASE)
_DS_TOKEN_RE = re.compile(r"\b([a-f0-9]{16})\b", re.IGNORECASE)
_API_KEY_RE = re.compile(r"\b(sk-[A-Za-z0-9]{16,}|AIza[0-9A-Za-z\-_]{20,})\b")
_SYSTEM_BACKEND_SOURCE = "system_backend"
_SYSTEM_SOURCE_ALIASES = {
    _SYSTEM_BACKEND_SOURCE,
    "daemon_jsonl",
    "daemon.log",
    "daemon.jsonl",
    "daemon-supervisor.log",
    "daemon_supervisor",
}


def _sanitize_log_line(line: str) -> str:
    line = _BEARER_RE.sub(r"\1[REDACTED]", line)
    line = _DS_TOKEN_RE.sub("[REDACTED_TOKEN]", line)
    line = _API_KEY_RE.sub("[REDACTED_API_KEY]", line)
    return line


def _tail_lines(path: Path, max_lines: int, max_bytes: int = 250_000) -> tuple[list[str], bool]:
    if max_lines <= 0 or not path.exists():
        return [], False

    block_size = 4096
    data = b""
    read_bytes = 0
    truncated = False

    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        while position > 0 and data.count(b"\n") <= max_lines and read_bytes < max_bytes:
            step = min(block_size, position)
            position -= step
            handle.seek(position)
            chunk = handle.read(step)
            data = chunk + data
            read_bytes += step
        if position > 0:
            truncated = True
        if read_bytes >= max_bytes and data.count(b"\n") > max_lines:
            truncated = True

    raw_lines = data.splitlines()[-max_lines:]
    return [_sanitize_log_line(item.decode("utf-8", errors="replace")) for item in raw_lines], truncated


class AdminLogService:
    def __init__(self, home: Path) -> None:
        self.home = Path(home)

    @property
    def logs_root(self) -> Path:
        return ensure_dir(self.home / "logs")

    def _system_backend_path(self) -> Path:
        preferred = self.logs_root / "daemon.jsonl"
        if preferred.exists() and preferred.is_file():
            return preferred
        for filename in (
            "daemon.log",
            "daemon-supervisor.log",
            "daemon-faulthandler.log",
            "update-worker.log",
        ):
            candidate = self.logs_root / filename
            if candidate.exists() and candidate.is_file():
                return candidate
        return preferred

    def _system_source(self) -> dict[str, Any]:
        return self._source_info(_SYSTEM_BACKEND_SOURCE, self._system_backend_path())

    def _source_info(self, source: str, path: Path) -> dict[str, Any]:
        exists = path.exists() and path.is_file()
        stat = path.stat() if exists else None
        return {
            "source": source,
            "filename": path.name,
            "path": str(path),
            "exists": exists,
            "size_bytes": int(stat.st_size) if stat else None,
            "updated_at": None if stat is None else str(read_json(path, {}).get("updated_at") or "") if path.suffix == ".json" else None,
            "mtime": None if stat is None else int(getattr(stat, "st_mtime", 0)),
        }

    def list_sources(self) -> list[dict[str, Any]]:
        return [self._system_source()]

    def resolve_source(self, source: str) -> Path:
        normalized = str(source or "").strip()
        if normalized in _SYSTEM_SOURCE_ALIASES:
            return self._system_backend_path()
        raise FileNotFoundError(f"Unknown log source `{normalized}`.")

    def tail(self, source: str, *, line_count: int = 200) -> dict[str, Any]:
        path = self.resolve_source(source)
        lines, truncated = _tail_lines(path, max(1, min(int(line_count or 200), 2000)))
        lines.reverse()
        stat = path.stat() if path.exists() else None
        return {
            "source": _SYSTEM_BACKEND_SOURCE,
            "filename": path.name,
            "updated_at": None if stat is None else int(getattr(stat, "st_mtime", 0)),
            "lines": lines,
            "truncated": truncated,
        }
