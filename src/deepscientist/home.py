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

    framework_quirks = home / "framework_quirks.md"
    if not framework_quirks.exists():
        framework_quirks.write_text(
            "# Framework Quirks\n\n"
            "Append-only durable file for framework-layer pitfalls (validator path quirks, "
            "closure-protocol gotchas, anything that cannot or will not be fixed in code "
            "and that future quests should know about before exercising the same surfaces).\n\n"
            "Each entry should name the surface, the symptom, and the workaround in 2-5 lines. "
            "Stage skills (idea, decision, finalize) instruct agents to read this file before "
            "committing to a route that would touch the relevant surface. If the file is empty, "
            "missing in an older home, or unrelated to the active route, the agent should skip it "
            "and continue rather than treating it as a required artifact.\n\n"
            "If a quirk should instead be fixed at the framework level, file an issue and fix the code; "
            "do not add it here as a permanent shim.\n",
            encoding="utf-8",
        )

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
