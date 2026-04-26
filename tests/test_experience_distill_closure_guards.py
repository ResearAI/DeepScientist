from __future__ import annotations

import json
from pathlib import Path

import pytest

from deepscientist.artifact import ArtifactService
from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.quest import QuestService
from deepscientist.skills import SkillInstaller


def _seed_pending_run(
    quest_root: Path, *, run_id: str = "run-pending-1", workspace: Path | None = None
) -> None:
    target = workspace if workspace is not None else quest_root
    artifacts = target / "artifacts"
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


def _seed_worktree_pending_run(quest_root: Path, *, worktree_name: str, run_id: str) -> Path:
    worktree = quest_root / ".ds" / "worktrees" / worktree_name
    worktree.mkdir(parents=True, exist_ok=True)
    _seed_pending_run(quest_root, run_id=run_id, workspace=worktree)
    return worktree


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


# --- Multi-workspace aggregation -----------------------------------------
# Records often live only in an active worktree's artifacts dir until the
# git-graph merge promotes them. The closure guards must look across every
# workspace_root (quest_root + .ds/worktrees/*) so a candidate sitting in a
# worktree still trips the gate.


def test_submit_paper_bundle_detects_pending_run_in_worktree(temp_home: Path) -> None:
    _, artifact, _, quest_root = _make_quest(temp_home, distill_on=True)
    _seed_worktree_pending_run(quest_root, worktree_name="idea-foo", run_id="run-in-worktree")

    with pytest.raises(ValueError) as excinfo:
        artifact.submit_paper_bundle(
            quest_root,
            title="Bundle",
            summary="Should still be blocked.",
        )

    msg = str(excinfo.value)
    assert "submit_paper_bundle blocked" in msg
    assert "run-in-worktree" in msg


def test_complete_quest_detects_pending_run_in_worktree(temp_home: Path) -> None:
    _, artifact, _, quest_root = _make_quest(temp_home, distill_on=True)
    _seed_worktree_pending_run(quest_root, worktree_name="idea-bar", run_id="run-in-worktree-2")

    result = artifact.complete_quest(quest_root, summary="Should be blocked.")

    assert result["ok"] is False
    assert result["status"] == "distill_required"
    assert "run-in-worktree-2" in result["pending_distill_ids"]


def test_complete_quest_dedupes_candidates_across_workspaces(temp_home: Path) -> None:
    _, artifact, _, quest_root = _make_quest(temp_home, distill_on=True)
    # Same artifact_id seeded in BOTH the canonical artifacts dir and a worktree
    # (mimics post-merge state where the worktree record was promoted but the
    # worktree copy was not pruned).
    _seed_pending_run(quest_root, run_id="run-shared")
    _seed_worktree_pending_run(quest_root, worktree_name="idea-baz", run_id="run-shared")

    result = artifact.complete_quest(quest_root, summary="Should count once.")

    assert result["ok"] is False
    assert result["status"] == "distill_required"
    assert result["pending_distill_count"] == 1
    assert result["pending_distill_ids"] == ["run-shared"]


def test_complete_quest_clears_when_review_in_quest_root_covers_worktree_run(
    temp_home: Path,
) -> None:
    _, artifact, _, quest_root = _make_quest(temp_home, distill_on=True)
    _seed_worktree_pending_run(quest_root, worktree_name="idea-qux", run_id="run-cross")
    _seed_distill_review(quest_root, reviewed_run_ids=["run-cross"])

    result = artifact.complete_quest(quest_root, summary="Distill review in main artifacts covers worktree run.")

    assert result["ok"] is False
    # No longer the distill block; falls through to approval logic.
    assert result["status"] != "distill_required"


# --- record(distill_review) workspace_root resolution --------------------
# Mirror of quest-012 bug: the MCP wrapper sets DS_WORKTREE_ROOT once at server
# start (= quest root). When activate_branch switches the active worktree, the
# env var is not refreshed, so record(...) is invoked with workspace_root=quest_root
# even though the run actually lives in the active worktree's artifacts/. The
# validator must aggregate across every workspace's artifacts dir, just like
# evaluate_distill_gate_for_quest already does — otherwise list_distill_candidates
# returns the run as a candidate yet record(distill_review, reviewed_run_ids=[run])
# fails with 'unknown run artifact_ids'.


def test_distill_review_accepts_run_recorded_only_in_worktree(temp_home: Path) -> None:
    _, artifact, _, quest_root = _make_quest(temp_home, distill_on=True)
    _seed_worktree_pending_run(
        quest_root, worktree_name="idea-w", run_id="run-only-in-worktree"
    )

    review = artifact.record(
        quest_root,
        {
            "kind": "distill_review",
            "reviewed_run_ids": ["run-only-in-worktree"],
            "cards_written": [
                {
                    "card_id": "knowledge-x",
                    "scope": "global",
                    "action": "new",
                    "target_run_id": "run-only-in-worktree",
                }
            ],
            "neighbor_decisions": [],
            "notes": "worktree-resident run",
        },
        workspace_root=quest_root,
    )
    assert review.get("ok", True) is not False
    assert str(review.get("artifact_id") or "").startswith("distill_review")
