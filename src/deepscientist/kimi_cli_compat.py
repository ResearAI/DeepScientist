from __future__ import annotations

import shutil
from pathlib import Path

from .shared import ensure_dir

_RUNTIME_COPY_ALLOWLIST = (
    "config.toml",
    "device_id",
    "credentials",
    "plugins",
)


def _remove_tree_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def materialize_kimi_runtime_home(
    *,
    source_home: str | Path,
    target_home: str | Path,
) -> Path:
    source_root = Path(source_home).expanduser()
    target_root = ensure_dir(Path(target_home))
    target_kimi_root = target_root / ".kimi"

    if target_kimi_root.exists() or target_kimi_root.is_symlink():
        _remove_tree_path(target_kimi_root)

    ensure_dir(target_kimi_root)
    if source_root.exists() and source_root.is_dir():
        for relative_name in _RUNTIME_COPY_ALLOWLIST:
            source_path = source_root / relative_name
            target_path = target_kimi_root / relative_name
            if not source_path.exists() and not source_path.is_symlink():
                continue
            if source_path.is_symlink() or source_path.is_file():
                ensure_dir(target_path.parent)
                shutil.copy2(source_path, target_path)
                continue
            shutil.copytree(source_path, target_path, dirs_exist_ok=True)

    return target_kimi_root
