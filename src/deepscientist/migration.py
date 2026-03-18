from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any


HOME_SIGNATURES = (
    "runtime",
    "config",
    "memory",
    "quests",
    "plugins",
    "logs",
    "cache",
    "cli",
)


def looks_like_deepscientist_root(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    if (path / "cli" / "bin" / "ds.js").exists():
        return True
    return any((path / name).exists() for name in HOME_SIGNATURES)


def _is_relative_to(candidate: Path, other: Path) -> bool:
    try:
        candidate.relative_to(other)
        return True
    except ValueError:
        return False


def _collect_manifest(root: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = {}
    file_count = 0
    dir_count = 0
    symlink_count = 0
    total_bytes = 0
    stack = [Path("")]
    while stack:
        rel_root = stack.pop()
        current_root = root / rel_root
        for child in sorted(current_root.iterdir(), key=lambda item: item.name):
            rel_path = (rel_root / child.name).as_posix()
            if child.is_symlink():
                manifest[rel_path] = {"kind": "symlink", "target": os.readlink(child)}
                symlink_count += 1
                continue
            if child.is_dir():
                manifest[rel_path] = {"kind": "dir"}
                dir_count += 1
                stack.append(rel_root / child.name)
                continue
            size = child.stat().st_size
            manifest[rel_path] = {"kind": "file", "size": size}
            file_count += 1
            total_bytes += size
    return {
        "entries": manifest,
        "stats": {
            "file_count": file_count,
            "dir_count": dir_count,
            "symlink_count": symlink_count,
            "total_bytes": total_bytes,
            "entry_count": len(manifest),
        },
    }


def migrate_deepscientist_root(source: Path, target: Path) -> dict[str, Any]:
    source = source.expanduser().resolve()
    target = target.expanduser().resolve()
    if not source.exists():
        raise ValueError(f"Source path does not exist: {source}")
    if not source.is_dir():
        raise ValueError(f"Source path is not a directory: {source}")
    if not looks_like_deepscientist_root(source):
        raise ValueError(f"Source path does not look like a DeepScientist home or install root: {source}")
    if source == target:
        raise ValueError("Source path and target path must be different.")
    if _is_relative_to(target, source):
        raise ValueError("Target path cannot be placed inside the current DeepScientist root.")
    if _is_relative_to(source, target):
        raise ValueError("Target path cannot be a parent of the current DeepScientist root.")
    if target.exists():
        raise ValueError(f"Target path already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    staging = target.parent / f".{target.name}.migrating-{uuid.uuid4().hex[:10]}"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    try:
        shutil.copytree(source, staging, symlinks=True, copy_function=shutil.copy2)
        source_manifest = _collect_manifest(source)
        staging_manifest = _collect_manifest(staging)
        if source_manifest["entries"] != staging_manifest["entries"]:
            raise ValueError("Copied tree validation failed: source and target contents do not match.")
        staging.rename(target)
        return {
            "ok": True,
            "source": str(source),
            "target": str(target),
            "staging": str(staging),
            "stats": source_manifest["stats"],
            "summary": "DeepScientist root copied and verified successfully.",
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
