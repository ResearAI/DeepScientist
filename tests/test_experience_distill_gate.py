from __future__ import annotations

import json
from pathlib import Path

from deepscientist.artifact.experience_distill import evaluate_distill_gate


def _make_quest(tmp_path: Path, *, distill_on: bool) -> Path:
    qr = tmp_path / "q"
    qr.mkdir()
    yaml_body = (
        "startup_contract:\n  experience_distill:\n    mode: on\n"
        if distill_on
        else "startup_contract: {}\n"
    )
    (qr / "quest.yaml").write_text(yaml_body, encoding="utf-8")
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


def _seed_distill_review(artifacts_dir: Path, review_id: str, reviewed_run_ids: list[str]) -> None:
    reviews_dir = artifacts_dir / "distill_reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "artifact_id": review_id,
        "kind": "distill_review",
        "reviewed_run_ids": reviewed_run_ids,
        "cards_written": [],
        "reason_if_empty": "test",
        "created_at": "2026-04-25T00:00:00+00:00",
    }
    record_path = reviews_dir / f"{review_id}.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    index_path = artifacts_dir / "_index.jsonl"
    existing = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    line = json.dumps({"artifact_id": review_id, "kind": "distill_review", "status": "completed", "path": str(record_path)})
    index_path.write_text(existing + line + "\n", encoding="utf-8")


def test_returns_none_when_distill_off(tmp_path: Path):
    qr = _make_quest(tmp_path, distill_on=False)
    artifacts = qr / "artifacts"
    _seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    assert evaluate_distill_gate(qr, artifacts) is None


def test_returns_none_when_no_candidates(tmp_path: Path):
    qr = _make_quest(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    _seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "idea", "status": "completed"}])
    assert evaluate_distill_gate(qr, artifacts) is None


def test_returns_payload_when_candidates_pending(tmp_path: Path):
    qr = _make_quest(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    _seed_runs(
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
    qr = _make_quest(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    _seed_runs(
        artifacts,
        [
            {"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"},
            {"artifact_id": "run-2", "kind": "run", "run_kind": "experiment", "status": "completed"},
        ],
    )
    _seed_distill_review(artifacts, "distill-review-1", ["run-1"])
    out = evaluate_distill_gate(qr, artifacts)
    assert out is not None
    assert out["pending_distill_count"] == 1
    assert out["pending_distill_ids"] == ["run-2"]


def test_returns_none_when_all_candidates_reviewed(tmp_path: Path):
    qr = _make_quest(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    _seed_runs(
        artifacts,
        [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}],
    )
    _seed_distill_review(artifacts, "distill-review-1", ["run-1"])
    assert evaluate_distill_gate(qr, artifacts) is None


def test_pending_distill_ids_capped_at_five(tmp_path: Path):
    qr = _make_quest(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    _seed_runs(
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
