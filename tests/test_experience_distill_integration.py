"""End-to-end tests for experience-distill.

Folds in:
- (was) tests/test_experience_distill_integration.py — full guidance_vm
  lifecycle through ArtifactService.record().
- (was) tests/test_experience_distill_candidates.py —
  iter_distill_candidate_records / DISTILL_CANDIDATE_RUN_KINDS unit tests.

Both exercise the candidate-discovery surface; the unit tests pin shape
on the iterator the integration tests rely on.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from deepscientist.artifact import ArtifactService
from deepscientist.artifact.experience_distill import (
    DISTILL_CANDIDATE_RUN_KINDS,
    iter_distill_candidate_records,
    maybe_inject_distill_finalize_gate,
)
from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.quest import QuestService
from deepscientist.skills import SkillInstaller

from tests._distill_fixtures import enable_distill_in_quest


# ===== iter_distill_candidate_records (unit) =============================


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


# ===== integration tests through ArtifactService =========================


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
    return enable_distill_in_quest(home, quest_id)


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
            "kind": "decision",
            "action": "distill_review",
            "verdict": "covered",
            "reason": "smoke test only",
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


def test_full_finalize_gate_lifecycle(home_with_quest):
    """Walk the full distill gate lifecycle through ArtifactService:
    seed run → decision(write) gate fires → list_distill_candidates surfaces it
    → distill_review lands → decision(write) gate clears → candidates empty.
    """
    home, quest_id = home_with_quest
    quest_root = _enable_distill(home, quest_id)
    service = ArtifactService(home)

    # Step 2: Record a completed main_experiment.
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

    # Step 3: First decision(write) → gate fires.
    first_decision = service.record(
        quest_root,
        {
            "kind": "decision",
            "action": "write",
            "verdict": "accept_positive_result",
            "reason": "Sufficient evidence for a paper",
        },
    )
    first_gvm = first_decision["guidance_vm"]
    assert first_gvm["recommended_skill"] == "distill"
    assert first_gvm["gate"] == "finalize"
    assert first_gvm["pending_distill_count"] == 1
    assert main_run_id in first_gvm["pending_distill_ids"]

    # Step 4: list_distill_candidates surfaces the candidate.
    candidates_before = service.list_distill_candidates(quest_root)
    assert candidates_before["experience_distill_on"] is True
    assert len(candidates_before["candidates"]) == 1
    assert candidates_before["candidates"][0]["artifact_id"] == main_run_id
    assert candidates_before["candidates"][0]["run_id"] == "main:1"
    assert candidates_before["candidates"][0]["run_kind"] == "main_experiment"
    assert main_run_id not in candidates_before["reviewed_run_ids"]

    # Step 5: Record distill_review covering the run.
    review = service.record(
        quest_root,
        {
            "kind": "decision",
            "action": "distill_review",
            "verdict": "covered",
            "reason": "smoke test",
            "reviewed_run_ids": [main_run_id],
            "cards_written": [],
            "reason_if_empty": "smoke test",
        },
    )
    assert review["artifact_id"].startswith("decision")

    # Step 6: Second decision(write) — gate clears.
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
    assert second_gvm["recommended_skill"] == "write"
    # Gate metadata should be absent (the clear branch strips it)
    assert "gate" not in second_gvm or second_gvm.get("gate") != "finalize"

    # Step 7: list_distill_candidates after review.
    candidates_after = service.list_distill_candidates(quest_root)
    assert candidates_after["experience_distill_on"] is True
    assert candidates_after["candidates"] == []
    assert main_run_id in candidates_after["reviewed_run_ids"]


def test_distill_review_rejects_fabricated_reviewed_run_ids(home_with_quest):
    home, quest_id = home_with_quest
    quest_root = _enable_distill(home, quest_id)
    service = ArtifactService(home)
    with pytest.raises(Exception) as exc_info:
        service.record(
            quest_root,
            {
                "kind": "decision",
                "action": "distill_review",
                "verdict": "covered",
                "reason": "test",
                "reviewed_run_ids": ["run-does-not-exist"],
                "cards_written": [],
                "reason_if_empty": "test",
            },
        )
    assert "unknown" in str(exc_info.value).lower() or "run-does-not-exist" in str(exc_info.value)


def test_e2e_finalize_gate_uses_imperative_routing_no_fallback(tmp_path: Path) -> None:
    """End-to-end: from quest with one completed run + recall_priors=on,
    a write decision routes to distill with the new imperative wording and
    no write fallback in alternative_routes."""
    from tests._distill_fixtures import seed_runs, write_quest_yaml

    quest_root = tmp_path / "quest-e2e"
    quest_root.mkdir()
    write_quest_yaml(quest_root, distill_on=True, recall_priors=True, bare_string=True)
    artifacts_dir = quest_root / "artifacts"
    seed_runs(artifacts_dir, [{
        "artifact_id": "run-main", "kind": "run", "run_kind": "main_experiment",
        "status": "completed", "summary": "main experiment ok",
    }])

    decision = {"kind": "decision", "action": "write", "artifact_id": "decision-write-1"}
    inbound = {"recommended_skill": "write", "recommended_action": "Draft paper."}
    fired = maybe_inject_distill_finalize_gate(quest_root, artifacts_dir, decision, inbound)

    assert fired is not None
    assert fired["recommended_skill"] == "distill"
    assert "Distill required" in fired["recommended_action"]
    assert fired["pending_distill_count"] == 1
    assert fired["pending_distill_ids"] == ["run-main"]
    routes = fired.get("alternative_routes") or []
    assert not any(
        isinstance(r, dict) and r.get("recommended_skill") == "write"
        for r in routes
    )

    # Now the agent records a distill_review with neighbor_decisions covering the run.
    review_path = artifacts_dir / "decisions" / "decision-distill-review-1.json"
    review_path.parent.mkdir(parents=True)
    review_payload = {
        "kind": "decision",
        "action": "distill_review",
        "verdict": "covered",
        "reason": "single run reviewed",
        "artifact_id": "decision-distill-review-1",
        "created_at": "2026-04-25T10:00:00+00:00",
        "reviewed_run_ids": ["run-main"],
        "cards_written": [
            {
                "card_id": "knowledge-fresh",
                "scope": "global",
                "action": "new",
                "target_run_id": "run-main",
            }
        ],
        "neighbor_decisions": [
            {
                "candidate_card_id": "knowledge-existing",
                "decision": "neighbor_but_separate",
                "reason": "different mechanism",
                "target_run_id": "run-main",
            }
        ],
    }
    review_path.write_text(json.dumps(review_payload), encoding="utf-8")
    with (artifacts_dir / "_index.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": "decision", "path": str(review_path)}) + "\n")

    # Schema check passes.
    from deepscientist.artifact.schemas import validate_artifact_payload
    assert validate_artifact_payload(review_payload) == []

    # Re-evaluate the same write decision: gate clears, original route restored.
    cleared = maybe_inject_distill_finalize_gate(
        quest_root, artifacts_dir, decision, fired
    )
    assert cleared is not None
    assert cleared["recommended_skill"] == "write"
    assert cleared.get("gate") != "finalize"
