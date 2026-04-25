from __future__ import annotations

import json
from pathlib import Path

from deepscientist.artifact.experience_distill import (
    DISTILL_CANDIDATE_RUN_KINDS,
    iter_distill_candidate_records,
)


def _write_index(artifacts_dir: Path, lines: list[dict]) -> None:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = artifacts_dir / "runs"
    runs_dir.mkdir(exist_ok=True)
    index_lines = []
    for line in lines:
        record_path = runs_dir / f"{line['artifact_id']}.json"
        record_path.write_text(json.dumps(line), encoding="utf-8")
        index_entry = {
            "artifact_id": line["artifact_id"],
            "kind": line.get("kind", "run"),
            "status": line.get("status", "completed"),
            "path": str(record_path),
        }
        index_lines.append(json.dumps(index_entry))
    (artifacts_dir / "_index.jsonl").write_text("\n".join(index_lines) + "\n", encoding="utf-8")


def test_default_candidate_kinds_cover_three_run_kinds():
    assert DISTILL_CANDIDATE_RUN_KINDS == frozenset(
        {"analysis.slice", "main_experiment", "experiment"}
    )


def test_iter_returns_completed_runs_in_default_kinds(tmp_path: Path):
    _write_index(
        tmp_path,
        [
            {"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"},
            {"artifact_id": "run-2", "kind": "run", "run_kind": "experiment", "status": "succeeded"},
            {"artifact_id": "run-3", "kind": "run", "run_kind": "analysis.slice", "status": "done"},
            {"artifact_id": "run-4", "kind": "run", "run_kind": "idea", "status": "completed"},        # excluded by kind
            {"artifact_id": "run-5", "kind": "run", "run_kind": "main_experiment", "status": "running"},  # excluded by status
        ],
    )
    out = list(iter_distill_candidate_records(tmp_path))
    ids = {r["artifact_id"] for r in out}
    assert ids == {"run-1", "run-2", "run-3"}


def test_iter_respects_explicit_run_kinds(tmp_path: Path):
    _write_index(
        tmp_path,
        [
            {"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"},
            {"artifact_id": "run-2", "kind": "run", "run_kind": "analysis.slice", "status": "done"},
        ],
    )
    out = list(iter_distill_candidate_records(tmp_path, run_kinds={"analysis.slice"}))
    ids = {r["artifact_id"] for r in out}
    assert ids == {"run-2"}


def test_iter_skips_missing_record_paths(tmp_path: Path):
    artifacts_dir = tmp_path
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "_index.jsonl").write_text(
        json.dumps({"artifact_id": "run-x", "kind": "run", "status": "completed", "path": "/nope"}) + "\n",
        encoding="utf-8",
    )
    assert list(iter_distill_candidate_records(artifacts_dir)) == []


def test_iter_returns_empty_when_index_missing(tmp_path: Path):
    assert list(iter_distill_candidate_records(tmp_path)) == []


def test_iter_skips_malformed_record_json(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True)
    bad = runs_dir / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    (tmp_path / "_index.jsonl").write_text(
        json.dumps({"artifact_id": "bad", "kind": "run", "path": str(bad)}) + "\n",
        encoding="utf-8",
    )
    assert list(iter_distill_candidate_records(tmp_path)) == []
