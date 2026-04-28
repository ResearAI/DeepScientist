from __future__ import annotations

import json
from pathlib import Path

import pytest

from deepscientist.artifact import ArtifactService
from deepscientist.artifact.experience_distill import maybe_inject_distill_finalize_gate
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
    quest_root = tmp_path / "quest-e2e"
    quest_root.mkdir()
    (quest_root / "quest.yaml").write_text(
        "startup_contract:\n"
        "  experience_distill: on\n"
        "  recall_priors: on\n",
        encoding="utf-8",
    )
    artifacts_dir = quest_root / "artifacts"
    artifacts_dir.mkdir()
    run_path = artifacts_dir / "runs" / "run-main.json"
    run_path.parent.mkdir(parents=True)
    run_path.write_text(
        json.dumps({
            "kind": "run", "run_kind": "main_experiment",
            "status": "completed", "artifact_id": "run-main",
            "summary": "main experiment ok",
        }),
        encoding="utf-8",
    )
    (artifacts_dir / "_index.jsonl").write_text(
        json.dumps({"kind": "run", "path": str(run_path)}) + "\n", encoding="utf-8"
    )

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
