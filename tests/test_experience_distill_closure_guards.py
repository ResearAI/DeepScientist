from __future__ import annotations

import json
from pathlib import Path

import pytest

from deepscientist.artifact import ArtifactService
from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.quest import QuestService
from deepscientist.skills import SkillInstaller


def _seed_pending_run(quest_root: Path, *, run_id: str = "run-pending-1") -> None:
    artifacts = quest_root / "artifacts"
    runs_dir = artifacts / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "artifact_id": run_id,
        "kind": "run",
        "run_kind": "main_experiment",
        "status": "completed",
    }
    (runs_dir / f"{run_id}.json").write_text(json.dumps(record), encoding="utf-8")
    line = json.dumps({
        "artifact_id": run_id,
        "kind": "run",
        "status": "completed",
        "path": str(runs_dir / f"{run_id}.json"),
    })
    index_path = artifacts / "_index.jsonl"
    if index_path.exists():
        existing = index_path.read_text(encoding="utf-8")
        if not existing.endswith("\n"):
            existing += "\n"
        index_path.write_text(existing + line + "\n", encoding="utf-8")
    else:
        index_path.write_text(line + "\n", encoding="utf-8")


def _seed_distill_review(quest_root: Path, *, reviewed_run_ids: list[str]) -> None:
    artifacts = quest_root / "artifacts"
    reviews_dir = artifacts / "distill_reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    review_id = "distill-review-1"
    record = {
        "artifact_id": review_id,
        "kind": "distill_review",
        "reviewed_run_ids": reviewed_run_ids,
        "created_at": "2026-04-26T00:00:00+00:00",
    }
    (reviews_dir / f"{review_id}.json").write_text(json.dumps(record), encoding="utf-8")
    line = json.dumps({
        "artifact_id": review_id,
        "kind": "distill_review",
        "status": "completed",
        "path": str(reviews_dir / f"{review_id}.json"),
    })
    index_path = artifacts / "_index.jsonl"
    if index_path.exists():
        existing = index_path.read_text(encoding="utf-8")
        if not existing.endswith("\n"):
            existing += "\n"
        index_path.write_text(existing + line + "\n", encoding="utf-8")
    else:
        index_path.write_text(line + "\n", encoding="utf-8")


def _make_quest(temp_home: Path, *, distill_on: bool = True) -> tuple[QuestService, ArtifactService, dict, Path]:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    contract = {"experience_distill": "on" if distill_on else "off"}
    quest = quest_service.create("closure guard quest", startup_contract=contract)
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    return quest_service, artifact, quest, quest_root


# --- submit_paper_bundle hard guard ---------------------------------------


def test_submit_paper_bundle_rejects_when_pending_distill(temp_home: Path) -> None:
    _, artifact, _, quest_root = _make_quest(temp_home, distill_on=True)
    _seed_pending_run(quest_root, run_id="run-needs-distill")

    with pytest.raises(ValueError) as excinfo:
        artifact.submit_paper_bundle(
            quest_root,
            title="Bundle",
            summary="Should be blocked.",
        )

    msg = str(excinfo.value)
    assert "submit_paper_bundle blocked" in msg
    assert "experience_distill" in msg
    assert "run-needs-distill" in msg
    assert "distill_review" in msg


def test_submit_paper_bundle_passes_distill_check_when_review_landed(temp_home: Path) -> None:
    _, artifact, _, quest_root = _make_quest(temp_home, distill_on=True)
    _seed_pending_run(quest_root, run_id="run-reviewed")
    _seed_distill_review(quest_root, reviewed_run_ids=["run-reviewed"])

    # Distill gate now clear. The call still fails on a different gate (no
    # selected outline yet) — but the failure must NOT be the distill block.
    with pytest.raises(ValueError) as excinfo:
        artifact.submit_paper_bundle(
            quest_root,
            title="Bundle",
            summary="Should pass distill check.",
        )

    msg = str(excinfo.value)
    assert "submit_paper_bundle blocked" not in msg or "distill" not in msg
    assert "selected outline" in msg or "outline_path" in msg


def test_submit_paper_bundle_skips_distill_check_when_distill_off(temp_home: Path) -> None:
    _, artifact, _, quest_root = _make_quest(temp_home, distill_on=False)
    _seed_pending_run(quest_root, run_id="run-no-distill")

    # Distill is off → guard must not fire. Call still fails on missing outline.
    with pytest.raises(ValueError) as excinfo:
        artifact.submit_paper_bundle(
            quest_root,
            title="Bundle",
            summary="Distill off; guard skipped.",
        )

    msg = str(excinfo.value)
    assert "distill" not in msg.lower()


# --- complete_quest hard guard --------------------------------------------


def test_complete_quest_returns_distill_required_when_pending(temp_home: Path) -> None:
    _, artifact, quest, quest_root = _make_quest(temp_home, distill_on=True)
    _seed_pending_run(quest_root, run_id="run-needs-distill-2")

    result = artifact.complete_quest(quest_root, summary="Tries to skip distill.")

    assert result["ok"] is False
    assert result["status"] == "distill_required"
    assert result["pending_distill_count"] == 1
    assert "run-needs-distill-2" in result["pending_distill_ids"]
    assert "distill" in result["message"].lower()


def test_complete_quest_falls_through_when_distill_clear(temp_home: Path) -> None:
    _, artifact, quest, quest_root = _make_quest(temp_home, distill_on=True)
    _seed_pending_run(quest_root, run_id="run-reviewed-2")
    _seed_distill_review(quest_root, reviewed_run_ids=["run-reviewed-2"])

    result = artifact.complete_quest(quest_root, summary="Distill cleared.")

    assert result["ok"] is False
    # Distill no longer the blocker — the next layer (approval) takes over.
    assert result["status"] != "distill_required"
    assert result["status"] in {"approval_required", "waiting_for_user", "approval_not_explicit"}


def test_complete_quest_skips_distill_check_when_distill_off(temp_home: Path) -> None:
    _, artifact, quest, quest_root = _make_quest(temp_home, distill_on=False)
    _seed_pending_run(quest_root, run_id="run-no-distill-2")

    result = artifact.complete_quest(quest_root, summary="Distill off.")

    assert result["ok"] is False
    assert result["status"] != "distill_required"


def test_complete_quest_skips_distill_check_when_already_completed(temp_home: Path) -> None:
    quest_service, artifact, quest, quest_root = _make_quest(temp_home, distill_on=True)
    _seed_pending_run(quest_root, run_id="run-needs-distill-3")
    quest_service.update_runtime_state(quest_root=quest_root, status="completed")

    result = artifact.complete_quest(quest_root, summary="Already done.")

    assert result["ok"] is True
    assert result["status"] == "already_completed"
