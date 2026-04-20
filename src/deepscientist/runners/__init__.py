from __future__ import annotations

from .base import RunRequest, RunResult
from .metadata import get_runner_metadata, list_builtin_runner_names
from .registry import get_runner_factory, list_runner_names, register_runner

__all__ = [
    "ClaudeRunner",
    "CodexRunner",
    "KimiRunner",
    "OpenCodeRunner",
    "RunRequest",
    "RunResult",
    "get_runner_factory",
    "get_runner_metadata",
    "list_builtin_runner_names",
    "list_runner_names",
    "register_builtin_runners",
    "register_runner",
]


def __getattr__(name: str):
    if name == "CodexRunner":
        from .codex import CodexRunner

        return CodexRunner
    if name == "ClaudeRunner":
        from .claude import ClaudeRunner

        return ClaudeRunner
    if name == "OpenCodeRunner":
        from .opencode import OpenCodeRunner

        return OpenCodeRunner
    if name == "KimiRunner":
        from .kimi import KimiRunner

        return KimiRunner
    if name == "register_builtin_runners":
        from .builtins import register_builtin_runners

        return register_builtin_runners
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
