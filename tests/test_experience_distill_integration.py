from __future__ import annotations

from pathlib import Path

import pytest

from deepscientist.artifact import ArtifactService
from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.quest import QuestService
from deepscientist.skills import SkillInstaller


@pytest.fixture
def home_with_quest(tmp_path: Path) -> tuple[Path, str]:
    home = tmp_path / "DeepScientistHome"
    ensure_home_layout(home)
    ConfigManager(home).ensure_files()
    quest_service = QuestService(home, skill_installer=SkillInstaller(repo_root(), home))
    quest = quest_service.create("Distill demo")
    quest_id = quest["quest_id"]
    return home, quest_id


def _enable_distill(home: Path, quest_id: str) -> Path:
    import yaml

    quest_root = home / "quests" / quest_id
    quest_yaml = quest_root / "quest.yaml"
    payload = yaml.safe_load(quest_yaml.read_text(encoding="utf-8")) or {}
    contract = payload.get("startup_contract") if isinstance(payload.get("startup_contract"), dict) else {}
    contract["experience_distill"] = {"mode": "on"}
    payload["startup_contract"] = contract
    quest_yaml.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return quest_root


def test_completed_analysis_slice_redirects_guidance_to_distill(home_with_quest):
    home, quest_id = home_with_quest
    quest_root = _enable_distill(home, quest_id)
    service = ArtifactService(home)
    record = service.record(
        quest_root,
        {
            "kind": "run",
            "run_kind": "analysis.slice",
            "status": "completed",
            "run_id": "cmp_1:s_1",
            "summary": "Slice 1 done",
        },
    )
    gvm = record["guidance_vm"]
    assert gvm["recommended_skill"] == "distill"
    assert gvm["experience_distill"] is True


def test_main_experiment_run_not_redirected(home_with_quest):
    home, quest_id = home_with_quest
    quest_root = _enable_distill(home, quest_id)
    service = ArtifactService(home)
    record = service.record(
        quest_root,
        {
            "kind": "run",
            "run_kind": "main.experiment",
            "status": "completed",
            "run_id": "main:1",
            "summary": "Main done",
        },
    )
    assert record["guidance_vm"]["recommended_skill"] != "distill"


def test_distill_off_leaves_guidance_unchanged(home_with_quest):
    home, quest_id = home_with_quest
    quest_root = home / "quests" / quest_id  # no enable
    service = ArtifactService(home)
    record = service.record(
        quest_root,
        {
            "kind": "run",
            "run_kind": "analysis.slice",
            "status": "completed",
            "run_id": "cmp_1:s_1",
            "summary": "Slice 1 done",
        },
    )
    assert record["guidance_vm"]["recommended_skill"] != "distill"
