"""Gate tests for experience-distill.

Folds in:
- (was) tests/test_experience_distill_gate.py — evaluate_distill_gate +
  collect_reviewed_run_ids on a quest_root.
- (was) tests/test_experience_distill_finalize_gate.py —
  maybe_inject_distill_finalize_gate on decision(write|finalize) records.
- (was) tests/test_experience_distill_closure_guards.py —
  submit_paper_bundle / complete_quest hard guards (multi-workspace).

All three layers gate the same fact ("are there pending distill candidates?")
and naturally belong together.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from deepscientist.artifact.experience_distill import (
    evaluate_distill_gate,
    maybe_inject_distill_finalize_gate,
)

from tests._distill_fixtures import (
    make_artifact_quest,
    make_decision_record,
    make_baseline_guidance,
    make_quest_root,
    seed_distill_review,
    seed_distill_review_in_quest,
    seed_pending_run,
    seed_runs,
    seed_worktree_pending_run,
    write_quest_yaml,
)


# ===== evaluate_distill_gate (low-level on a quest_root) =================


def test_returns_none_when_distill_off(tmp_path: Path):
    qr = make_quest_root(tmp_path, distill_on=False)
    artifacts = qr / "artifacts"
    seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    assert evaluate_distill_gate(qr, artifacts) is None


def test_returns_none_when_no_candidates(tmp_path: Path):
    qr = make_quest_root(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "idea", "status": "completed"}])
    assert evaluate_distill_gate(qr, artifacts) is None


def test_returns_payload_when_candidates_pending(tmp_path: Path):
    qr = make_quest_root(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    seed_runs(
        artifacts,
        [
            {"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed", "created_at": "2026-04-25T01:00:00+00:00"},
            {"artifact_id": "run-2", "kind": "run", "run_kind": "experiment", "status": "completed", "created_at": "2026-04-25T02:00:00+00:00"},
        ],
    )
    out = evaluate_distill_gate(qr, artifacts)
    assert out is not None
    assert out["pending_distill_count"] == 2
    assert set(out["pending_distill_ids"]) == {"run-1", "run-2"}


def test_excludes_already_reviewed_runs(tmp_path: Path):
    qr = make_quest_root(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    seed_runs(
        artifacts,
        [
            {"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"},
            {"artifact_id": "run-2", "kind": "run", "run_kind": "experiment", "status": "completed"},
        ],
    )
    seed_distill_review(artifacts, "distill-review-1", ["run-1"])
    out = evaluate_distill_gate(qr, artifacts)
    assert out is not None
    assert out["pending_distill_count"] == 1
    assert out["pending_distill_ids"] == ["run-2"]


def test_returns_none_when_all_candidates_reviewed(tmp_path: Path):
    qr = make_quest_root(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    seed_runs(
        artifacts,
        [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}],
    )
    seed_distill_review(artifacts, "distill-review-1", ["run-1"])
    assert evaluate_distill_gate(qr, artifacts) is None


def test_pending_distill_ids_capped_at_five(tmp_path: Path):
    qr = make_quest_root(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    seed_runs(
        artifacts,
        [
            {"artifact_id": f"run-{i}", "kind": "run", "run_kind": "experiment", "status": "completed"}
            for i in range(8)
        ],
    )
    out = evaluate_distill_gate(qr, artifacts)
    assert out is not None
    assert out["pending_distill_count"] == 8
    assert len(out["pending_distill_ids"]) == 5


def test_cursor_run_created_at_returns_latest_review_timestamp(tmp_path: Path):
    qr = make_quest_root(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    seed_runs(artifacts, [{"artifact_id": "run-pending", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    # Two reviews with different timestamps; cursor must reflect the later one.
    old_path = seed_distill_review(artifacts, "distill-review-old", ["run-old"])
    new_path = seed_distill_review(artifacts, "distill-review-new", ["run-new"])
    # Manually overwrite created_at after seeding because seed_distill_review pins a fixed timestamp.
    old = json.loads(old_path.read_text(encoding="utf-8"))
    old["created_at"] = "2026-04-25T00:00:00+00:00"
    old_path.write_text(json.dumps(old), encoding="utf-8")
    new = json.loads(new_path.read_text(encoding="utf-8"))
    new["created_at"] = "2026-04-25T05:00:00+00:00"
    new_path.write_text(json.dumps(new), encoding="utf-8")
    out = evaluate_distill_gate(qr, artifacts)
    assert out is not None
    assert out["cursor_run_created_at"] == "2026-04-25T05:00:00+00:00"


def test_multiple_reviews_aggregate_into_reviewed_set(tmp_path: Path):
    qr = make_quest_root(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    seed_runs(
        artifacts,
        [
            {"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"},
            {"artifact_id": "run-2", "kind": "run", "run_kind": "experiment", "status": "completed"},
            {"artifact_id": "run-3", "kind": "run", "run_kind": "experiment", "status": "completed"},
        ],
    )
    # Two separate reviews each cover one run; the third remains pending.
    seed_distill_review(artifacts, "distill-review-1", ["run-1"])
    seed_distill_review(artifacts, "distill-review-2", ["run-2"])
    out = evaluate_distill_gate(qr, artifacts)
    assert out is not None
    assert out["pending_distill_count"] == 1
    assert out["pending_distill_ids"] == ["run-3"]


def test_pending_distill_ids_preserves_index_order_when_truncated(tmp_path: Path):
    qr = make_quest_root(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    seed_runs(
        artifacts,
        [
            {"artifact_id": f"run-{i}", "kind": "run", "run_kind": "experiment", "status": "completed"}
            for i in range(8)
        ],
    )
    out = evaluate_distill_gate(qr, artifacts)
    assert out is not None
    assert out["pending_distill_ids"] == ["run-0", "run-1", "run-2", "run-3", "run-4"]


def test_collect_reviewed_run_ids_handles_empty_reviews():
    from deepscientist.artifact.experience_distill import collect_reviewed_run_ids
    reviewed, cursor = collect_reviewed_run_ids([])
    assert reviewed == set()
    assert cursor is None


def test_collect_reviewed_run_ids_aggregates_and_picks_latest_timestamp():
    from deepscientist.artifact.experience_distill import collect_reviewed_run_ids
    reviews = [
        {"reviewed_run_ids": ["a", "b"], "created_at": "2026-04-25T01:00:00+00:00"},
        {"reviewed_run_ids": ["c"], "created_at": "2026-04-25T03:00:00+00:00"},
        {"reviewed_run_ids": ["d"], "created_at": "2026-04-25T02:00:00+00:00"},
    ]
    reviewed, cursor = collect_reviewed_run_ids(reviews)
    assert reviewed == {"a", "b", "c", "d"}
    assert cursor == "2026-04-25T03:00:00+00:00"


# ===== maybe_inject_distill_finalize_gate (decision(write|finalize)) =====


def test_no_change_for_non_decision_record(tmp_path: Path):
    qr = make_quest_root(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    record = {"kind": "run", "run_kind": "main_experiment", "status": "completed"}
    gvm = make_baseline_guidance()
    out = maybe_inject_distill_finalize_gate(qr, artifacts, record, gvm)
    assert out is gvm


def test_no_change_for_unrelated_decision_action(tmp_path: Path):
    qr = make_quest_root(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    gvm = make_baseline_guidance()
    out = maybe_inject_distill_finalize_gate(qr, artifacts, make_decision_record("launch_experiment"), gvm)
    assert out is gvm


def test_no_change_when_gate_clear(tmp_path: Path):
    qr = make_quest_root(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "idea", "status": "completed"}])
    gvm = make_baseline_guidance()
    out = maybe_inject_distill_finalize_gate(qr, artifacts, make_decision_record("write"), gvm)
    assert out is gvm


def test_redirect_when_decision_write_with_pending_candidates(tmp_path: Path):
    qr = make_quest_root(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    gvm = make_baseline_guidance()
    out = maybe_inject_distill_finalize_gate(qr, artifacts, make_decision_record("write"), gvm)
    assert out is not gvm
    assert out["recommended_skill"] == "distill"
    assert out["previous_recommended_skill"] == "write"
    assert out["pending_distill_count"] == 1
    assert "run-1" in out["pending_distill_ids"]
    assert out["experience_distill"] is True
    assert out["gate"] == "finalize"
    # Phase 3 Task 1: fire branch no longer appends a write/finalize fallback route.
    assert not any(r.get("recommended_skill") == "write" for r in out["alternative_routes"])


def test_redirect_when_decision_finalize_with_pending_candidates(tmp_path: Path):
    qr = make_quest_root(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    base = make_baseline_guidance()
    base["recommended_skill"] = "finalize"
    base["recommended_action"] = "finalize"
    out = maybe_inject_distill_finalize_gate(qr, artifacts, make_decision_record("finalize"), base)
    assert out is not base
    assert out["recommended_skill"] == "distill"
    assert out["previous_recommended_skill"] == "finalize"


def test_does_not_mutate_input_guidance(tmp_path: Path):
    qr = make_quest_root(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    gvm = make_baseline_guidance()
    snapshot = json.loads(json.dumps(gvm))
    maybe_inject_distill_finalize_gate(qr, artifacts, make_decision_record("write"), gvm)
    assert gvm == snapshot


def test_handles_none_guidance_vm(tmp_path: Path):
    qr = make_quest_root(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    out = maybe_inject_distill_finalize_gate(qr, artifacts, make_decision_record("write"), None)
    assert out is not None
    assert out["recommended_skill"] == "distill"


def test_redirect_when_decision_action_has_uppercase_or_whitespace(tmp_path: Path):
    qr = make_quest_root(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    record = make_decision_record("  Write  ")  # whitespace + capitalized
    out = maybe_inject_distill_finalize_gate(qr, artifacts, record, make_baseline_guidance())
    assert out["recommended_skill"] == "distill"
    assert out["pending_distill_count"] == 1


def test_clear_branch_strips_all_injected_keys(tmp_path: Path):
    """Re-evaluating a previously gate-injected guidance with no pending candidates restores the previous skill."""
    qr = make_quest_root(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    # No pending candidates — gate is None — but inbound guidance was previously gate-injected.
    inbound = {
        "schema_version": 1,
        "recommended_skill": "distill",
        "recommended_action": "Review undistilled completed runs and record a `distill_review` before resuming write/finalize.",
        "previous_recommended_skill": "write",
        "previous_recommended_action": "write",
        "alternative_routes": [
            {
                "recommended_skill": "write",
                "recommended_action": "write",
                "reason": "Original next step before the finalize gate fired.",
            }
        ],
        "experience_distill": True,
        "gate": "finalize",
        "pending_distill_count": 1,
        "pending_distill_ids": ["run-old"],
        "cursor_run_created_at": "2026-04-25T00:00:00+00:00",
        "source_artifact_id": "decision-old",
    }
    out = maybe_inject_distill_finalize_gate(qr, artifacts, make_decision_record("write"), inbound)
    # Restored to write
    assert out["recommended_skill"] == "write"
    assert out["recommended_action"] == "write"
    # All gate metadata stripped
    for key in (
        "gate", "pending_distill_count", "pending_distill_ids",
        "cursor_run_created_at", "previous_recommended_skill",
        "previous_recommended_action", "experience_distill",
        "source_artifact_id",
    ):
        assert key not in out, f"clear branch should strip `{key}`"


def test_clear_branch_preserves_alternative_routes(tmp_path: Path):
    """The clear branch passes alternative_routes through untouched (Phase 3 Task 1: no
    longer filters the obsolete fire-branch fallback entry, since fire no longer appends one)."""
    qr = make_quest_root(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    inbound = {
        "schema_version": 1,
        "recommended_skill": "distill",
        "previous_recommended_skill": "write",
        "previous_recommended_action": "write",
        "alternative_routes": [
            {
                "recommended_skill": "scout",
                "recommended_action": "scout literature",
                "reason": "Pre-existing route from upstream.",
            },
        ],
        "gate": "finalize",
    }
    out = maybe_inject_distill_finalize_gate(qr, artifacts, make_decision_record("write"), inbound)
    # Pre-existing route preserved.
    reasons = [r.get("reason") for r in out.get("alternative_routes", [])]
    assert "Pre-existing route from upstream." in reasons


def test_finalize_gate_fire_does_not_append_write_fallback(tmp_path: Path) -> None:
    """When the gate fires, alternative_routes must NOT contain a write/finalize fallback entry."""
    quest_root = tmp_path / "quest"
    quest_root.mkdir()
    write_quest_yaml(quest_root, distill_on=True, bare_string=True)
    artifacts_dir = quest_root / "artifacts"
    seed_runs(artifacts_dir, [{"artifact_id": "run-x", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])

    decision = {"kind": "decision", "action": "write", "artifact_id": "decision-1"}
    inbound = {"recommended_skill": "write", "recommended_action": "Draft the paper."}
    out = maybe_inject_distill_finalize_gate(quest_root, artifacts_dir, decision, inbound)

    assert out is not None
    assert out["recommended_skill"] == "distill"
    assert out["gate"] == "finalize"
    routes = out.get("alternative_routes") or []
    fallback_entries = [r for r in routes if isinstance(r, dict) and r.get("recommended_skill") == "write"]
    assert fallback_entries == [], f"Expected no write-fallback in alternative_routes, got: {fallback_entries}"


def test_finalize_gate_fire_uses_imperative_action_wording(tmp_path: Path) -> None:
    quest_root = tmp_path / "quest"
    quest_root.mkdir()
    write_quest_yaml(quest_root, distill_on=True, bare_string=True)
    artifacts_dir = quest_root / "artifacts"
    seed_runs(artifacts_dir, [{"artifact_id": "run-x", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])

    decision = {"kind": "decision", "action": "write", "artifact_id": "decision-1"}
    out = maybe_inject_distill_finalize_gate(quest_root, artifacts_dir, decision, None)

    assert out is not None
    action = str(out["recommended_action"])
    assert "Distill required" in action
    assert "distill_review" in action
    assert "paused" in action


# ===== submit_paper_bundle / complete_quest hard guards ==================


def test_submit_paper_bundle_rejects_when_pending_distill(temp_home: Path) -> None:
    _, artifact, _, quest_root = make_artifact_quest(temp_home, distill_on=True)
    seed_pending_run(quest_root, run_id="run-needs-distill")

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
    _, artifact, _, quest_root = make_artifact_quest(temp_home, distill_on=True)
    seed_pending_run(quest_root, run_id="run-reviewed")
    seed_distill_review_in_quest(quest_root, reviewed_run_ids=["run-reviewed"])

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
    _, artifact, _, quest_root = make_artifact_quest(temp_home, distill_on=False)
    seed_pending_run(quest_root, run_id="run-no-distill")

    # Distill is off → guard must not fire. Call still fails on missing outline.
    with pytest.raises(ValueError) as excinfo:
        artifact.submit_paper_bundle(
            quest_root,
            title="Bundle",
            summary="Distill off; guard skipped.",
        )

    msg = str(excinfo.value)
    assert "distill" not in msg.lower()


def test_complete_quest_returns_distill_required_when_pending(temp_home: Path) -> None:
    _, artifact, quest, quest_root = make_artifact_quest(temp_home, distill_on=True)
    seed_pending_run(quest_root, run_id="run-needs-distill-2")

    result = artifact.complete_quest(quest_root, summary="Tries to skip distill.")

    assert result["ok"] is False
    assert result["status"] == "distill_required"
    assert result["pending_distill_count"] == 1
    assert "run-needs-distill-2" in result["pending_distill_ids"]
    assert "distill" in result["message"].lower()


def test_complete_quest_falls_through_when_distill_clear(temp_home: Path) -> None:
    _, artifact, quest, quest_root = make_artifact_quest(temp_home, distill_on=True)
    seed_pending_run(quest_root, run_id="run-reviewed-2")
    seed_distill_review_in_quest(quest_root, reviewed_run_ids=["run-reviewed-2"])

    result = artifact.complete_quest(quest_root, summary="Distill cleared.")

    assert result["ok"] is False
    # Distill no longer the blocker — the next layer (approval) takes over.
    assert result["status"] != "distill_required"
    assert result["status"] in {"approval_required", "waiting_for_user", "approval_not_explicit"}


def test_complete_quest_skips_distill_check_when_distill_off(temp_home: Path) -> None:
    _, artifact, quest, quest_root = make_artifact_quest(temp_home, distill_on=False)
    seed_pending_run(quest_root, run_id="run-no-distill-2")

    result = artifact.complete_quest(quest_root, summary="Distill off.")

    assert result["ok"] is False
    assert result["status"] != "distill_required"


def test_complete_quest_skips_distill_check_when_already_completed(temp_home: Path) -> None:
    quest_service, artifact, quest, quest_root = make_artifact_quest(temp_home, distill_on=True)
    seed_pending_run(quest_root, run_id="run-needs-distill-3")
    quest_service.update_runtime_state(quest_root=quest_root, status="completed")

    result = artifact.complete_quest(quest_root, summary="Already done.")

    assert result["ok"] is True
    assert result["status"] == "already_completed"


# Multi-workspace aggregation: records often live only in an active worktree's
# artifacts dir until the git-graph merge promotes them. The closure guards
# must look across every workspace_root (quest_root + .ds/worktrees/*) so a
# candidate sitting in a worktree still trips the gate.


def test_submit_paper_bundle_detects_pending_run_in_worktree(temp_home: Path) -> None:
    _, artifact, _, quest_root = make_artifact_quest(temp_home, distill_on=True)
    seed_worktree_pending_run(quest_root, worktree_name="idea-foo", run_id="run-in-worktree")

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
    _, artifact, _, quest_root = make_artifact_quest(temp_home, distill_on=True)
    seed_worktree_pending_run(quest_root, worktree_name="idea-bar", run_id="run-in-worktree-2")

    result = artifact.complete_quest(quest_root, summary="Should be blocked.")

    assert result["ok"] is False
    assert result["status"] == "distill_required"
    assert "run-in-worktree-2" in result["pending_distill_ids"]


def test_complete_quest_dedupes_candidates_across_workspaces(temp_home: Path) -> None:
    _, artifact, _, quest_root = make_artifact_quest(temp_home, distill_on=True)
    # Same artifact_id seeded in BOTH the canonical artifacts dir and a worktree
    # (mimics post-merge state where the worktree record was promoted but the
    # worktree copy was not pruned).
    seed_pending_run(quest_root, run_id="run-shared")
    seed_worktree_pending_run(quest_root, worktree_name="idea-baz", run_id="run-shared")

    result = artifact.complete_quest(quest_root, summary="Should count once.")

    assert result["ok"] is False
    assert result["status"] == "distill_required"
    assert result["pending_distill_count"] == 1
    assert result["pending_distill_ids"] == ["run-shared"]


def test_complete_quest_clears_when_review_in_quest_root_covers_worktree_run(
    temp_home: Path,
) -> None:
    _, artifact, _, quest_root = make_artifact_quest(temp_home, distill_on=True)
    seed_worktree_pending_run(quest_root, worktree_name="idea-qux", run_id="run-cross")
    seed_distill_review_in_quest(quest_root, reviewed_run_ids=["run-cross"])

    result = artifact.complete_quest(quest_root, summary="Distill review in main artifacts covers worktree run.")

    assert result["ok"] is False
    # No longer the distill block; falls through to approval logic.
    assert result["status"] != "distill_required"


# record(distill_review) workspace_root resolution: mirror of quest-012 bug.
# The MCP wrapper sets DS_WORKTREE_ROOT once at server start (= quest root).
# When activate_branch switches the active worktree, the env var is not
# refreshed, so record(...) is invoked with workspace_root=quest_root even
# though the run actually lives in the active worktree's artifacts/. The
# validator must aggregate across every workspace's artifacts dir, just like
# evaluate_distill_gate_for_quest already does — otherwise list_distill_candidates
# returns the run as a candidate yet record(distill_review, reviewed_run_ids=[run])
# fails with 'unknown run artifact_ids'.


def test_distill_review_accepts_run_recorded_only_in_worktree(temp_home: Path) -> None:
    _, artifact, _, quest_root = make_artifact_quest(temp_home, distill_on=True)
    seed_worktree_pending_run(
        quest_root, worktree_name="idea-w", run_id="run-only-in-worktree"
    )

    review = artifact.record(
        quest_root,
        {
            "kind": "decision",
            "action": "distill_review",
            "verdict": "covered",
            "reason": "worktree-resident run reviewed",
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
    assert str(review.get("artifact_id") or "").startswith("decision")
