from __future__ import annotations

import pytest

from deepscientist.artifact.schemas import (
    ARTIFACT_DIRS,
    DECISION_ACTIONS,
    validate_artifact_payload,
)


def test_distill_review_kind_is_not_a_separate_artifact_kind():
    """Per RFC #64 slim: distill_review is no longer its own artifact kind.
    It lives under `decision` with action='distill_review'."""
    assert "distill_review" not in ARTIFACT_DIRS


def test_distill_review_is_a_decision_action():
    assert "distill_review" in DECISION_ACTIONS


def _base_payload(**overrides):
    payload = {
        "kind": "decision",
        "action": "distill_review",
        "verdict": "covered",
        "reason": "batch reviewed",
    }
    payload.update(overrides)
    return payload


def test_decision_without_distill_review_action_skips_review_validation():
    """A plain decision payload (action != 'distill_review') must NOT trigger
    review-specific validation — no reviewed_run_ids, cards_written needed."""
    errors = validate_artifact_payload(
        {
            "kind": "decision",
            "action": "continue",
            "verdict": "ok",
            "reason": "no-op",
        }
    )
    assert errors == []


def test_decision_distill_review_missing_reviewed_run_ids_fails():
    """A decision payload WITH action='distill_review' but missing
    reviewed_run_ids must fail review-specific validation."""
    errors = validate_artifact_payload(
        {
            "kind": "decision",
            "action": "distill_review",
            "verdict": "covered",
            "reason": "missing reviewed",
        }
    )
    assert any("reviewed_run_ids" in e for e in errors), errors


def test_distill_review_accepts_valid_payload_with_cards():
    errors = validate_artifact_payload(
        _base_payload(
            reviewed_run_ids=["run-aaa", "run-bbb"],
            cards_written=[
                {
                    "card_id": "knowledge-1",
                    "scope": "global",
                    "action": "new",
                    "target_run_id": "run-aaa",
                }
            ],
        )
    )
    assert errors == []


def test_distill_review_accepts_empty_cards_with_reason():
    errors = validate_artifact_payload(
        _base_payload(
            reviewed_run_ids=["run-aaa"],
            cards_written=[],
            reason_if_empty="all candidates were null-result smoke tests",
        )
    )
    assert errors == []


def test_distill_review_rejects_empty_reviewed_run_ids():
    errors = validate_artifact_payload(
        _base_payload(
            reviewed_run_ids=[],
            cards_written=[],
            reason_if_empty="n/a",
        )
    )
    assert any("reviewed_run_ids" in e for e in errors)


def test_distill_review_rejects_missing_reason_when_no_cards():
    errors = validate_artifact_payload(
        _base_payload(
            reviewed_run_ids=["run-aaa"],
            cards_written=[],
        )
    )
    assert any("reason_if_empty" in e for e in errors)


def test_distill_review_rejects_card_target_run_outside_reviewed():
    errors = validate_artifact_payload(
        _base_payload(
            reviewed_run_ids=["run-aaa"],
            cards_written=[
                {
                    "card_id": "knowledge-1",
                    "scope": "global",
                    "action": "new",
                    "target_run_id": "run-zzz",
                }
            ],
        )
    )
    assert any("target_run_id" in e for e in errors)


def test_distill_review_rejects_card_invalid_action():
    errors = validate_artifact_payload(
        _base_payload(
            reviewed_run_ids=["run-aaa"],
            cards_written=[
                {
                    "card_id": "knowledge-1",
                    "scope": "global",
                    "action": "delete",  # not allowed
                    "target_run_id": "run-aaa",
                }
            ],
        )
    )
    # The card-level "action" validation message references action.
    # (Decision-level "action" is valid here because it's "distill_review".)
    assert any(
        "cards_written" in e and "action" in e for e in errors
    ), errors


def test_distill_review_rejects_non_list_reviewed_run_ids():
    errors = validate_artifact_payload(
        _base_payload(
            reviewed_run_ids="run-aaa",  # string, not list
            cards_written=[],
            reason_if_empty="n/a",
        )
    )
    assert any("reviewed_run_ids" in e for e in errors)


def test_distill_review_rejects_non_list_cards_written():
    errors = validate_artifact_payload(
        _base_payload(
            reviewed_run_ids=["run-aaa"],
            cards_written={"card_id": "knowledge-1"},  # dict, not list
            reason_if_empty="n/a",
        )
    )
    assert any("cards_written" in e for e in errors)


def test_distill_review_rejects_non_dict_card_entry():
    errors = validate_artifact_payload(
        _base_payload(
            reviewed_run_ids=["run-aaa"],
            cards_written=["not-a-dict"],
        )
    )
    assert any("must be an object" in e for e in errors)


def test_distill_review_rejects_card_invalid_scope():
    errors = validate_artifact_payload(
        _base_payload(
            reviewed_run_ids=["run-aaa"],
            cards_written=[
                {
                    "card_id": "knowledge-1",
                    "scope": "team",  # not allowed
                    "action": "new",
                    "target_run_id": "run-aaa",
                }
            ],
        )
    )
    assert any("scope" in e for e in errors)


def test_distill_review_neighbor_decisions_omitted_is_valid() -> None:
    payload = _base_payload(
        reviewed_run_ids=["run-1"],
        cards_written=[],
        reason_if_empty="smoke run",
    )
    assert validate_artifact_payload(payload) == []


def test_distill_review_neighbor_decisions_empty_list_is_valid() -> None:
    payload = _base_payload(
        reviewed_run_ids=["run-1"],
        cards_written=[],
        reason_if_empty="smoke run",
        neighbor_decisions=[],
    )
    assert validate_artifact_payload(payload) == []


def test_distill_review_neighbor_decisions_well_formed_is_valid() -> None:
    payload = _base_payload(
        reviewed_run_ids=["run-1"],
        cards_written=[
            {
                "card_id": "knowledge-abc",
                "scope": "global",
                "action": "patch",
                "target_run_id": "run-1",
            }
        ],
        neighbor_decisions=[
            {
                "candidate_card_id": "knowledge-xyz",
                "decision": "neighbor_but_separate",
                "reason": "different mechanism",
                "target_run_id": "run-1",
            }
        ],
    )
    assert validate_artifact_payload(payload) == []


def test_distill_review_neighbor_decisions_unknown_decision_rejected() -> None:
    payload = _base_payload(
        reviewed_run_ids=["run-1"],
        cards_written=[],
        reason_if_empty="skipped",
        neighbor_decisions=[
            {
                "candidate_card_id": "knowledge-xyz",
                "decision": "merge",  # not in the allowed set
                "reason": "test",
                "target_run_id": "run-1",
            }
        ],
    )
    errors = validate_artifact_payload(payload)
    assert any("decision" in e.lower() for e in errors), errors


def test_distill_review_neighbor_decisions_target_run_id_must_be_in_reviewed() -> None:
    payload = _base_payload(
        reviewed_run_ids=["run-1"],
        cards_written=[],
        reason_if_empty="skipped",
        neighbor_decisions=[
            {
                "candidate_card_id": "knowledge-xyz",
                "decision": "patch",
                "reason": "test",
                "target_run_id": "run-MISSING",
            }
        ],
    )
    errors = validate_artifact_payload(payload)
    assert any("target_run_id" in e for e in errors), errors


def test_distill_review_neighbor_decisions_missing_required_key_rejected() -> None:
    payload = _base_payload(
        reviewed_run_ids=["run-1"],
        cards_written=[],
        reason_if_empty="skipped",
        neighbor_decisions=[
            {"candidate_card_id": "knowledge-xyz", "decision": "patch"}
        ],
    )
    errors = validate_artifact_payload(payload)
    assert any("neighbor_decisions" in e for e in errors), errors
