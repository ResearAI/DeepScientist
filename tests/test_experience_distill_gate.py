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
    reviews_dir = artifacts_dir / "decisions"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "artifact_id": review_id,
        "kind": "decision",
        "action": "distill_review",
        "verdict": "covered",
        "reason": "test",
        "reviewed_run_ids": reviewed_run_ids,
        "cards_written": [],
        "reason_if_empty": "test",
        "created_at": "2026-04-25T00:00:00+00:00",
    }
    record_path = reviews_dir / f"{review_id}.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    index_path = artifacts_dir / "_index.jsonl"
    existing = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    line = json.dumps({"artifact_id": review_id, "kind": "decision", "status": "completed", "path": str(record_path)})
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


def test_cursor_run_created_at_returns_latest_review_timestamp(tmp_path: Path):
    qr = _make_quest(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    _seed_runs(artifacts, [{"artifact_id": "run-pending", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    # Two reviews with different timestamps; cursor must reflect the later one.
    _seed_distill_review(artifacts, "distill-review-old", ["run-old"])
    _seed_distill_review(artifacts, "distill-review-new", ["run-new"])
    # Manually overwrite created_at after seeding because _seed_distill_review pins a fixed timestamp.
    import json
    old_path = artifacts / "decisions" / "distill-review-old.json"
    new_path = artifacts / "decisions" / "distill-review-new.json"
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
    qr = _make_quest(tmp_path, distill_on=True)
    artifacts = qr / "artifacts"
    _seed_runs(
        artifacts,
        [
            {"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"},
            {"artifact_id": "run-2", "kind": "run", "run_kind": "experiment", "status": "completed"},
            {"artifact_id": "run-3", "kind": "run", "run_kind": "experiment", "status": "completed"},
        ],
    )
    # Two separate reviews each cover one run; the third remains pending.
    _seed_distill_review(artifacts, "distill-review-1", ["run-1"])
    _seed_distill_review(artifacts, "distill-review-2", ["run-2"])
    out = evaluate_distill_gate(qr, artifacts)
    assert out is not None
    assert out["pending_distill_count"] == 1
    assert out["pending_distill_ids"] == ["run-3"]


def test_pending_distill_ids_preserves_index_order_when_truncated(tmp_path: Path):
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
