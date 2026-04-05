from __future__ import annotations

from pathlib import Path

from ..shared import ensure_dir, run_command, slugify


def init_repo(repo: Path) -> None:
    run_command(["git", "init"], cwd=repo)
    run_command(["git", "branch", "-M", "main"], cwd=repo, check=False)


def current_branch(repo: Path) -> str:
    result = run_command(["git", "branch", "--show-current"], cwd=repo, check=False)
    branch = result.stdout.strip()
    return branch or "main"


def head_commit(repo: Path) -> str | None:
    result = run_command(["git", "rev-parse", "HEAD"], cwd=repo, check=False)
    commit = result.stdout.strip()
    return commit or None


def has_changes(repo: Path) -> bool:
    result = run_command(["git", "status", "--porcelain"], cwd=repo, check=False)
    return bool(result.stdout.strip())


def branch_exists(repo: Path, branch: str) -> bool:
    result = run_command(["git", "rev-parse", "--verify", branch], cwd=repo, check=False)
    return result.returncode == 0


def ensure_branch(repo: Path, branch: str, *, start_point: str | None = None, checkout: bool = False) -> dict:
    start = start_point or current_branch(repo)
    if not branch_exists(repo, branch):
        result = run_command(["git", "branch", branch, start], cwd=repo, check=False)
        created = result.returncode == 0
    else:
        result = run_command(["git", "rev-parse", "--verify", branch], cwd=repo, check=False)
        created = False
    if checkout:
        run_command(["git", "checkout", branch], cwd=repo, check=False)
    return {
        "branch": branch,
        "created": created,
        "head": head_commit(repo),
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def create_worktree(
    repo: Path,
    *,
    branch: str,
    worktree_root: Path,
    start_point: str | None = None,
) -> dict:
    ensure_dir(worktree_root.parent)
    if worktree_root.exists() and any(worktree_root.iterdir()):
        return {
            "ok": True,
            "branch": branch,
            "worktree_root": str(worktree_root),
            "created": False,
            "head": head_commit(repo),
        }

    if branch_exists(repo, branch):
        result = run_command(["git", "worktree", "add", str(worktree_root), branch], cwd=repo, check=False)
    else:
        start = start_point or current_branch(repo)
        result = run_command(
            ["git", "worktree", "add", "-b", branch, str(worktree_root), start],
            cwd=repo,
            check=False,
        )
    return {
        "ok": result.returncode == 0,
        "branch": branch,
        "worktree_root": str(worktree_root),
        "created": result.returncode == 0,
        "head": head_commit(repo),
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def canonical_worktree_root(repo: Path, run_id: str) -> Path:
    return repo / ".ds" / "worktrees" / slugify(run_id, "run")


def checkpoint_repo(repo: Path, message: str, allow_empty: bool = False) -> dict:
    run_command(["git", "add", "-A"], cwd=repo, check=False)
    if not allow_empty and not has_changes(repo):
        return {
            "committed": False,
            "branch": current_branch(repo),
            "head": head_commit(repo),
        }
    command = ["git", "commit", "-m", message]
    if allow_empty:
        command.insert(2, "--allow-empty")
    result = run_command(command, cwd=repo, check=False)
    return {
        "committed": result.returncode == 0,
        "branch": current_branch(repo),
        "head": head_commit(repo),
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def log_graph_lines(repo: Path, limit: int = 40) -> list[str]:
    result = run_command(
        [
            "git",
            "log",
            "--graph",
            "--decorate",
            "--oneline",
            "--all",
            f"-n{limit}",
        ],
        cwd=repo,
        check=False,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]
