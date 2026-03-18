from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover
    yaml = None
    YAML_IMPORT_ERROR = exc
else:
    YAML_IMPORT_ERROR = None


def require_yaml() -> None:
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required for DeepScientist Core. Install it with `pip install pyyaml`."
        ) from YAML_IMPORT_ERROR


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(text: str, default: str = "item") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return cleaned or default


def generate_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8")


def _atomic_write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    temp_path = path.with_suffix(f"{path.suffix}.{uuid4().hex}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(
        path,
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
    )


def read_json(path: Path | str, default: Any = None) -> Any:
    path = Path(path)
    if not path.exists():
        return default
    payload = path.read_text(encoding="utf-8").strip()
    if not payload:
        return default
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return default


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def read_yaml(path: Path, default: Any = None) -> Any:
    require_yaml()
    if not path.exists():
        return default
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return default
    return data


def write_yaml(path: Path, payload: Any) -> None:
    require_yaml()
    _atomic_write_text(
        path,
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
    )


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def resolve_within(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise ValueError(f"Path escapes root: {relative}")
    return candidate


def run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        check=check,
        text=True,
        capture_output=True,
    )


def which(binary: str) -> str | None:
    return shutil.which(binary)


def _resolve_executable_reference(reference: str) -> str | None:
    normalized = str(reference or "").strip()
    if not normalized:
        return None

    candidate = Path(normalized).expanduser()
    if candidate.is_absolute() or os.path.sep in normalized or (os.path.altsep and os.path.altsep in normalized):
        return str(candidate) if candidate.exists() else None
    return shutil.which(normalized)


def _codex_repo_roots() -> list[Path]:
    roots: list[Path] = []
    configured = str(os.environ.get("DEEPSCIENTIST_REPO_ROOT") or "").strip()
    if configured:
        roots.append(Path(configured).expanduser().resolve())
    roots.append(Path(__file__).resolve().parents[2])

    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return deduped


def resolve_runner_binary(binary: str, *, runner_name: str | None = None) -> str | None:
    normalized = str(binary or "").strip()
    if not normalized:
        return None

    resolved_reference = _resolve_executable_reference(normalized)
    candidate = Path(normalized).expanduser()
    if candidate.is_absolute() or os.path.sep in normalized or (os.path.altsep and os.path.altsep in normalized):
        return resolved_reference

    normalized_runner = str(runner_name or candidate.name or normalized).strip().lower()
    if normalized_runner != "codex":
        return resolved_reference

    for env_name in ("DEEPSCIENTIST_CODEX_BINARY", "DS_CODEX_BINARY"):
        override = os.environ.get(env_name)
        if override:
            resolved_override = _resolve_executable_reference(override)
            if resolved_override:
                return resolved_override

    names = ["codex.cmd", "codex.exe", "codex"] if sys.platform.startswith("win") else ["codex"]
    for root in _codex_repo_roots():
        node_bin_root = root / "node_modules" / ".bin"
        for name in names:
            package_local = node_bin_root / name
            if package_local.exists():
                return str(package_local)
    return resolved_reference
