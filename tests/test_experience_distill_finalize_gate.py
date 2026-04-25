from __future__ import annotations

import json
from pathlib import Path

from deepscientist.artifact.experience_distill import maybe_inject_distill_finalize_gate


def _make_quest(tmp_path: Path) -> Path:
    qr = tmp_path / "q"
    qr.mkdir()
    (qr / "quest.yaml").write_text(
        "startup_contract:\n  experience_distill:\n    mode: on\n",
        encoding="utf-8",
    )
    return qr


def _seed_runs(artifacts_dir: Path, runs: list[dict]) -> None:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = artifacts_dir / "runs"
    runs_dir.mkdir(exist_ok=True)
    index = []
    for r in runs:
        path = runs_dir / f"{r['artifact_id']}.json"
        path.write_text(json.dumps(r), encoding="utf-8")
        index.append(json.dumps({"artifact_id": r["artifact_id"], "kind": "run", "status": r.get("status", "completed"), "path": str(path)}))
    (artifacts_dir / "_index.jsonl").write_text("\n".join(index) + "\n", encoding="utf-8")


def _decision_record(action: str) -> dict:
    return {
        "kind": "decision",
        "action": action,
        "artifact_id": "decision-zzz",
        "reason": "test",
    }


def _baseline_guidance() -> dict:
    return {
        "schema_version": 1,
        "recommended_skill": "write",
        "recommended_action": "write",
        "alternative_routes": [],
    }


def test_no_change_for_non_decision_record(tmp_path: Path):
    qr = _make_quest(tmp_path)
    artifacts = qr / "artifacts"
    _seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    record = {"kind": "run", "run_kind": "main_experiment", "status": "completed"}
    gvm = _baseline_guidance()
    out = maybe_inject_distill_finalize_gate(qr, artifacts, record, gvm)
    assert out is gvm


def test_no_change_for_unrelated_decision_action(tmp_path: Path):
    qr = _make_quest(tmp_path)
    artifacts = qr / "artifacts"
    _seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    gvm = _baseline_guidance()
    out = maybe_inject_distill_finalize_gate(qr, artifacts, _decision_record("launch_experiment"), gvm)
    assert out is gvm


def test_no_change_when_gate_clear(tmp_path: Path):
    qr = _make_quest(tmp_path)
    artifacts = qr / "artifacts"
    _seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "idea", "status": "completed"}])
    gvm = _baseline_guidance()
    out = maybe_inject_distill_finalize_gate(qr, artifacts, _decision_record("write"), gvm)
    assert out is gvm


def test_redirect_when_decision_write_with_pending_candidates(tmp_path: Path):
    qr = _make_quest(tmp_path)
    artifacts = qr / "artifacts"
    _seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    gvm = _baseline_guidance()
    out = maybe_inject_distill_finalize_gate(qr, artifacts, _decision_record("write"), gvm)
    assert out is not gvm
    assert out["recommended_skill"] == "distill"
    assert out["previous_recommended_skill"] == "write"
    assert out["pending_distill_count"] == 1
    assert "run-1" in out["pending_distill_ids"]
    assert out["experience_distill"] is True
    assert out["gate"] == "finalize"
    assert any(r.get("recommended_skill") == "write" for r in out["alternative_routes"])


def test_redirect_when_decision_finalize_with_pending_candidates(tmp_path: Path):
    qr = _make_quest(tmp_path)
    artifacts = qr / "artifacts"
    _seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    base = _baseline_guidance()
    base["recommended_skill"] = "finalize"
    base["recommended_action"] = "finalize"
    out = maybe_inject_distill_finalize_gate(qr, artifacts, _decision_record("finalize"), base)
    assert out is not base
    assert out["recommended_skill"] == "distill"
    assert out["previous_recommended_skill"] == "finalize"


def test_does_not_mutate_input_guidance(tmp_path: Path):
    qr = _make_quest(tmp_path)
    artifacts = qr / "artifacts"
    _seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    gvm = _baseline_guidance()
    snapshot = json.loads(json.dumps(gvm))
    maybe_inject_distill_finalize_gate(qr, artifacts, _decision_record("write"), gvm)
    assert gvm == snapshot


def test_handles_none_guidance_vm(tmp_path: Path):
    qr = _make_quest(tmp_path)
    artifacts = qr / "artifacts"
    _seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    out = maybe_inject_distill_finalize_gate(qr, artifacts, _decision_record("write"), None)
    assert out is not None
    assert out["recommended_skill"] == "distill"


def test_redirect_when_decision_action_has_uppercase_or_whitespace(tmp_path: Path):
    qr = _make_quest(tmp_path)
    artifacts = qr / "artifacts"
    _seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    record = _decision_record("  Write  ")  # whitespace + capitalized
    out = maybe_inject_distill_finalize_gate(qr, artifacts, record, _baseline_guidance())
    assert out["recommended_skill"] == "distill"
    assert out["pending_distill_count"] == 1


def test_clear_branch_strips_all_injected_keys(tmp_path: Path):
    """Re-evaluating a previously gate-injected guidance with no pending candidates restores the previous skill."""
    qr = _make_quest(tmp_path)
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
    out = maybe_inject_distill_finalize_gate(qr, artifacts, _decision_record("write"), inbound)
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


def test_clear_branch_drops_gate_appended_alternative_route(tmp_path: Path):
    """The clear branch should remove the fire branch's appended fallback route."""
    qr = _make_quest(tmp_path)
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
            {
                "recommended_skill": "write",
                "recommended_action": "write",
                "reason": "Original next step before the finalize gate fired.",
            },
        ],
        "gate": "finalize",
    }
    out = maybe_inject_distill_finalize_gate(qr, artifacts, _decision_record("write"), inbound)
    # Pre-existing route preserved; gate-appended route dropped.
    reasons = [r.get("reason") for r in out.get("alternative_routes", [])]
    assert "Pre-existing route from upstream." in reasons
    assert "Original next step before the finalize gate fired." not in reasons
