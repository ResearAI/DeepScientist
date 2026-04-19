from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..home import default_home


@dataclass(frozen=True)
class McpContext:
    home: Path
    quest_id: str | None
    quest_root: Path | None
    run_id: str | None
    active_anchor: str | None
    conversation_id: str | None
    agent_role: str | None
    worker_id: str | None
    worktree_root: Path | None
    team_mode: str | None
    custom_profile: str | None = None

    @classmethod
    def from_env(cls) -> "McpContext":
        def _path(name: str) -> Path | None:
            value = os.environ.get(name, "").strip()
            return Path(value).expanduser() if value else None

        home = _path("DEEPSCIENTIST_HOME") or _path("DS_HOME") or default_home()
        return cls(
            home=home,
            quest_id=os.environ.get("DS_QUEST_ID") or None,
            quest_root=_path("DS_QUEST_ROOT"),
            run_id=os.environ.get("DS_RUN_ID") or None,
            active_anchor=os.environ.get("DS_ACTIVE_ANCHOR") or None,
            conversation_id=os.environ.get("DS_CONVERSATION_ID") or None,
            agent_role=os.environ.get("DS_AGENT_ROLE") or None,
            worker_id=os.environ.get("DS_WORKER_ID") or None,
            worktree_root=_path("DS_WORKTREE_ROOT"),
            team_mode=os.environ.get("DS_TEAM_MODE") or None,
            custom_profile=os.environ.get("DS_CUSTOM_PROFILE") or None,
        )

    def require_quest_root(self) -> Path:
        if self.quest_root is None:
            raise ValueError("Quest-local MCP call requires DS_QUEST_ROOT in the environment.")
        return self.quest_root
