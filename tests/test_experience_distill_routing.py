from __future__ import annotations

from pathlib import Path

import pytest

from deepscientist.artifact.experience_distill import maybe_inject_distill_routing


def _quest(tmp_path: Path, *, distill_on: bool) -> Path:
    qr = tmp_path / "q_demo"
    qr.mkdir()
    yaml_body = (
        "startup_contract:\n  experience_distill:\n    mode: on\n"
        if distill_on
        else "startup_contract: {}\n"
    )
    (qr / "quest.yaml").write_text(yaml_body, encoding="utf-8")
    return qr


def _baseline_guidance() -> dict:
    return {
        "schema_version": 1,
        "recommended_skill": "scout",
        "recommended_action": "Continue exploration",
        "alternative_routes": [],
        "careful_mode": False,
    }


def test_returns_original_when_distill_off(tmp_path: Path):
    qr = _quest(tmp_path, distill_on=False)
    gvm = _baseline_guidance()
    record = {"kind": "run", "run_kind": "analysis.slice", "artifact_id": "a1", "run_id": "c:s"}
    out = maybe_inject_distill_routing(qr, record, gvm)
    assert out is gvm


def test_returns_original_when_record_is_not_analysis_slice(tmp_path: Path):
    qr = _quest(tmp_path, distill_on=True)
    gvm = _baseline_guidance()
    record = {"kind": "run", "run_kind": "main.experiment", "artifact_id": "a1"}
    out = maybe_inject_distill_routing(qr, record, gvm)
    assert out is gvm


def test_returns_original_when_slice_status_not_completed(tmp_path: Path):
    qr = _quest(tmp_path, distill_on=True)
    gvm = _baseline_guidance()
    record = {"kind": "run", "run_kind": "analysis.slice", "status": "running", "artifact_id": "a1"}
    out = maybe_inject_distill_routing(qr, record, gvm)
    assert out is gvm


def test_redirects_to_distill_on_completed_analysis_slice(tmp_path: Path):
    qr = _quest(tmp_path, distill_on=True)
    gvm = _baseline_guidance()
    record = {
        "kind": "run",
        "run_kind": "analysis.slice",
        "status": "completed",
        "artifact_id": "a1",
        "run_id": "cmp_1:s_1",
        "campaign_id": "cmp_1",
        "slice_id": "s_1",
    }
    out = maybe_inject_distill_routing(qr, record, gvm)
    assert out is not gvm  # new dict
    assert out["recommended_skill"] == "distill"
    assert out["previous_recommended_skill"] == "scout"
    assert out["experience_distill"] is True
    assert any(route.get("recommended_skill") == "scout" for route in out["alternative_routes"])
    assert "cmp_1:s_1" in out.get("source_artifact_id", "") or out.get("source_artifact_id") == "a1"


def test_handles_none_guidance_vm(tmp_path: Path):
    qr = _quest(tmp_path, distill_on=True)
    record = {
        "kind": "run",
        "run_kind": "analysis.slice",
        "status": "completed",
        "artifact_id": "a1",
    }
    out = maybe_inject_distill_routing(qr, record, None)
    assert out is not None
    assert out["recommended_skill"] == "distill"


def test_does_not_mutate_input(tmp_path: Path):
    qr = _quest(tmp_path, distill_on=True)
    gvm = _baseline_guidance()
    gvm_snapshot = dict(gvm)
    record = {"kind": "run", "run_kind": "analysis.slice", "status": "completed", "artifact_id": "a1"}
    maybe_inject_distill_routing(qr, record, gvm)
    assert gvm == gvm_snapshot
