from __future__ import annotations

import pytest

from deepscientist.artifact.schemas import ARTIFACT_DIRS, validate_artifact_payload


def test_distill_review_kind_is_registered():
    assert ARTIFACT_DIRS["distill_review"] == "distill_reviews"


def test_distill_review_accepts_valid_payload_with_cards():
    errors = validate_artifact_payload(
        {
            "kind": "distill_review",
            "reviewed_run_ids": ["run-aaa", "run-bbb"],
            "cards_written": [
                {
                    "card_id": "knowledge-1",
                    "scope": "global",
                    "action": "new",
                    "target_run_id": "run-aaa",
                }
            ],
        }
    )
    assert errors == []


def test_distill_review_accepts_empty_cards_with_reason():
    errors = validate_artifact_payload(
        {
            "kind": "distill_review",
            "reviewed_run_ids": ["run-aaa"],
            "cards_written": [],
            "reason_if_empty": "all candidates were null-result smoke tests",
        }
    )
    assert errors == []


def test_distill_review_rejects_empty_reviewed_run_ids():
    errors = validate_artifact_payload(
        {
            "kind": "distill_review",
            "reviewed_run_ids": [],
            "cards_written": [],
            "reason_if_empty": "n/a",
        }
    )
    assert any("reviewed_run_ids" in e for e in errors)


def test_distill_review_rejects_missing_reason_when_no_cards():
    errors = validate_artifact_payload(
        {
            "kind": "distill_review",
            "reviewed_run_ids": ["run-aaa"],
            "cards_written": [],
        }
    )
    assert any("reason_if_empty" in e for e in errors)


def test_distill_review_rejects_card_target_run_outside_reviewed():
    errors = validate_artifact_payload(
        {
            "kind": "distill_review",
            "reviewed_run_ids": ["run-aaa"],
            "cards_written": [
                {
                    "card_id": "knowledge-1",
                    "scope": "global",
                    "action": "new",
                    "target_run_id": "run-zzz",
                }
            ],
        }
    )
    assert any("target_run_id" in e for e in errors)


def test_distill_review_rejects_card_invalid_action():
    errors = validate_artifact_payload(
        {
            "kind": "distill_review",
            "reviewed_run_ids": ["run-aaa"],
            "cards_written": [
                {
                    "card_id": "knowledge-1",
                    "scope": "global",
                    "action": "delete",  # not allowed
                    "target_run_id": "run-aaa",
                }
            ],
        }
    )
    assert any("action" in e for e in errors)
