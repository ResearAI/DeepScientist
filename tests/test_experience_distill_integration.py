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


def test_decision_write_record_includes_finalize_gate_when_pending(home_with_quest):
    home, quest_id = home_with_quest
    quest_root = _enable_distill(home, quest_id)
    service = ArtifactService(home)
    # First seed a completed main_experiment so the gate has a candidate.
    service.record(
        quest_root,
        {
            "kind": "run",
            "run_kind": "main_experiment",
            "status": "completed",
            "run_id": "main:1",
            "summary": "Main experiment done",
        },
    )
    # Now record decision(write); the gate should fire.
    decision_record = service.record(
        quest_root,
        {
            "kind": "decision",
            "action": "write",
            "verdict": "accept_positive_result",
            "reason": "Sufficient evidence for a paper",
        },
    )
    gvm = decision_record["guidance_vm"]
    assert gvm["recommended_skill"] == "distill"
    assert gvm["gate"] == "finalize"
    assert gvm["pending_distill_count"] >= 1
    assert gvm["experience_distill"] is True


def test_decision_write_record_skips_gate_when_distill_off(home_with_quest):
    home, quest_id = home_with_quest
    quest_root = home / "quests" / quest_id  # NOT enabled
    service = ArtifactService(home)
    # Seed a completed main_experiment regardless.
    service.record(
        quest_root,
        {
            "kind": "run",
            "run_kind": "main_experiment",
            "status": "completed",
            "run_id": "main:1",
            "summary": "Main experiment done",
        },
    )
    decision_record = service.record(
        quest_root,
        {
            "kind": "decision",
            "action": "write",
            "verdict": "accept_positive_result",
            "reason": "Sufficient evidence for a paper",
        },
    )
    # When distill is off, the gate must not redirect — recommendation stays on the original target.
    assert decision_record["guidance_vm"]["recommended_skill"] != "distill"


def test_finalize_gate_clears_after_distill_review(home_with_quest):
    home, quest_id = home_with_quest
    quest_root = _enable_distill(home, quest_id)
    service = ArtifactService(home)
    main_run = service.record(
        quest_root,
        {
            "kind": "run",
            "run_kind": "main_experiment",
            "status": "completed",
            "run_id": "main:1",
            "summary": "Main experiment done",
        },
    )
    main_run_id = main_run["artifact_id"]
    # First decision(write) — gate fires.
    first_decision = service.record(
        quest_root,
        {
            "kind": "decision",
            "action": "write",
            "verdict": "accept_positive_result",
            "reason": "First attempt",
        },
    )
    assert first_decision["guidance_vm"]["recommended_skill"] == "distill"
    # Agent records a distill_review covering the run.
    service.record(
        quest_root,
        {
            "kind": "distill_review",
            "reviewed_run_ids": [main_run_id],
            "cards_written": [],
            "reason_if_empty": "smoke test only",
        },
    )
    # Second decision(write) — gate clears, recommendation flips back to write.
    second_decision = service.record(
        quest_root,
        {
            "kind": "decision",
            "action": "write",
            "verdict": "accept_positive_result",
            "reason": "Second attempt after distill",
        },
    )
    second_gvm = second_decision["guidance_vm"]
    assert second_gvm["recommended_skill"] != "distill"
