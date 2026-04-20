from __future__ import annotations

import os
from pathlib import Path

from .shared import ensure_dir


def _candidate_repo_root_from_launcher() -> Path | None:
    launcher_path = str(os.environ.get("DEEPSCIENTIST_LAUNCHER_PATH") or "").strip()
    if not launcher_path:
        return None
    launcher = Path(launcher_path).expanduser().resolve()
    for candidate in (launcher.parent.parent, *launcher.parents):
        if _looks_like_repo_root(candidate):
            return candidate
    return None


def _looks_like_repo_root(path: Path) -> bool:
    return (
        (path / "pyproject.toml").exists()
        and (path / "src" / "deepscientist").exists()
        and (path / "src" / "skills").exists()
    )


def repo_root() -> Path:
    configured = str(os.environ.get("DEEPSCIENTIST_REPO_ROOT") or "").strip()
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if _looks_like_repo_root(candidate):
            return candidate

    launcher_candidate = _candidate_repo_root_from_launcher()
    if launcher_candidate is not None:
        return launcher_candidate

    cwd = Path.cwd().resolve()
    if _looks_like_repo_root(cwd):
        return cwd

    module_path = Path(__file__).resolve()
    for candidate in module_path.parents:
        if _looks_like_repo_root(candidate):
            return candidate

    return module_path.parents[2]


def default_home() -> Path:
    return Path.home() / "DeepScientist"


def ensure_home_layout(home: Path) -> dict[str, Path]:
    runtime = ensure_dir(home / "runtime")
    ensure_dir(runtime / "bundle")
    ensure_dir(runtime / "tools")
    ensure_dir(runtime / "python")
    ensure_dir(runtime / "uv-cache")

    config = ensure_dir(home / "config")
    ensure_dir(config / "baselines")
    ensure_dir(config / "baselines" / "entries")

    memory = ensure_dir(home / "memory")
    for kind in ("papers", "ideas", "decisions", "episodes", "knowledge", "templates"):
        ensure_dir(memory / kind)

    quests = ensure_dir(home / "quests")
    plugins = ensure_dir(home / "plugins")
    logs = ensure_dir(home / "logs")
    cache = ensure_dir(home / "cache")
    ensure_dir(cache / "skills")

    return {
        "home": home,
        "runtime": runtime,
        "config": config,
        "memory": memory,
        "quests": quests,
        "plugins": plugins,
        "logs": logs,
        "cache": cache,
    }
