from __future__ import annotations

import argparse
import json
from pathlib import Path

from deepscientist.artifact import ArtifactService
from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.quest import QuestService
from deepscientist.shared import write_text
from deepscientist.skills import SkillInstaller


FIXTURE_QUEST_ID = "e2e-copilot-workspace"
FIRST_SUBJECT = "seed copilot workspace fixture"
LATEST_SUBJECT = "copilot fixture second commit"
CHANGED_PATH = "copilot_notes.md"
SECOND_PATH = "analysis_outline.md"
SNAPSHOT_HEADING = "Copilot Workspace Fixture"

BASE_CONTENT = f"""# {SNAPSHOT_HEADING}

This file exists so the Copilot git canvas can open a real commit snapshot.
"""

UPDATED_CONTENT = f"""# {SNAPSHOT_HEADING}

This file exists so the Copilot git canvas can open a real commit snapshot.

- Added a second durable note for the commit viewer.
- Explorer scope should resolve against this commit snapshot.
"""

SECOND_CONTENT = """# Analysis Outline

1. Compare baseline.
2. Inspect regression cases.
3. Record the next user-approved action.
"""


def build_fixture(home: Path) -> dict[str, object]:
    ensure_home_layout(home)
    config_manager = ConfigManager(home)
    config_manager.ensure_files()

    installer = SkillInstaller(repo_root(), home)
    quest_service = QuestService(home, skill_installer=installer)
    quest = quest_service.create(
        "Copilot workspace E2E fixture",
        quest_id=FIXTURE_QUEST_ID,
        startup_contract={
            "workspace_mode": "copilot",
            "decision_policy": "user_gated",
            "launch_mode": "custom",
            "custom_profile": "freeform",
        },
    )
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(home)

    quest_service.update_research_state(quest_root, workspace_mode="copilot")
    quest_service.set_continuation_state(
        quest_root,
        policy="wait_for_user_or_resume",
        anchor="decision",
        reason="copilot_mode",
    )

    write_text(quest_root / CHANGED_PATH, BASE_CONTENT)
    artifact.checkpoint(quest_root, FIRST_SUBJECT)

    write_text(quest_root / CHANGED_PATH, UPDATED_CONTENT)
    write_text(quest_root / SECOND_PATH, SECOND_CONTENT)
    artifact.checkpoint(quest_root, LATEST_SUBJECT)

    return {
        "quest_id": quest["quest_id"],
        "quest_root": str(quest_root),
        "latest_subject": LATEST_SUBJECT,
        "changed_path": CHANGED_PATH,
        "snapshot_heading": SNAPSHOT_HEADING,
        "home": str(home),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an isolated Copilot workspace E2E fixture quest.")
    parser.add_argument("--home", required=True, help="DeepScientist home for the temporary fixture runtime.")
    parser.add_argument("--output", required=True, help="Path to write the fixture JSON.")
    args = parser.parse_args()

    home = Path(args.home).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    fixture = build_fixture(home)
    output.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(fixture, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
