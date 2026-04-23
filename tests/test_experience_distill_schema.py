from __future__ import annotations

import pytest

from deepscientist.artifact.experience_distill import (
    build_experience_metadata,
    validate_cross_quest_patch,
    validate_experience_metadata,
)


def test_build_experience_metadata_sets_required_fields():
    meta = build_experience_metadata(
        claim="Warm-up helps Adam on small-batch CNNs",
        mechanism="Damps large gradient noise in the first few hundred steps",
        conditions=["batch<=64", "optimizer=Adam", "arch=CNN"],
        confidence=0.6,
        lineage=[{"quest": "q_alpha", "run": "run_7", "direction": "optim_sweep", "note": "first sighting"}],
    )
    assert meta["subtype"] == "experience"
    assert meta["claim"].startswith("Warm-up")
    assert meta["mechanism"].startswith("Damps")
    assert meta["confidence"] == 0.6
    assert len(meta["conditions"]) == 3
    assert meta["lineage"][0]["quest"] == "q_alpha"


def test_validate_accepts_well_formed_metadata():
    meta = build_experience_metadata(
        claim="X",
        mechanism="Y",
        conditions=["Z"],
        confidence=0.5,
        lineage=[{"quest": "q", "run": "r", "direction": "d", "note": "n"}],
    )
    validate_experience_metadata(meta)  # no raise


@pytest.mark.parametrize(
    "missing_field, expected_error_fragment",
    [
        ("mechanism", "mechanism"),
        ("conditions", "conditions"),
        ("lineage", "lineage"),
        ("claim", "claim"),
    ],
)
def test_validate_rejects_missing_required_field(missing_field, expected_error_fragment):
    meta = {
        "subtype": "experience",
        "claim": "X",
        "mechanism": "Y",
        "conditions": ["Z"],
        "confidence": 0.5,
        "lineage": [{"quest": "q", "run": "r", "direction": "d", "note": "n"}],
    }
    if missing_field == "conditions":
        meta[missing_field] = []
    elif missing_field == "lineage":
        meta[missing_field] = []
    else:
        meta[missing_field] = ""
    with pytest.raises(ValueError, match=expected_error_fragment):
        validate_experience_metadata(meta)


def test_validate_rejects_lineage_entry_missing_quest_or_run():
    meta = build_experience_metadata(
        claim="X",
        mechanism="Y",
        conditions=["Z"],
        confidence=0.5,
        lineage=[{"quest": "q", "direction": "d", "note": "n"}],  # no run
    )
    with pytest.raises(ValueError, match="run"):
        validate_experience_metadata(meta)


def test_validate_confidence_bounds():
    meta = build_experience_metadata(
        claim="X", mechanism="Y", conditions=["Z"], confidence=1.5,
        lineage=[{"quest": "q", "run": "r", "direction": "d", "note": "n"}],
    )
    with pytest.raises(ValueError, match="confidence"):
        validate_experience_metadata(meta)


def test_validate_cross_quest_patch_locks_claim():
    before = build_experience_metadata(
        claim="Warm-up helps Adam",
        mechanism="Damps noise",
        conditions=["Adam"],
        confidence=0.6,
        lineage=[{"quest": "q1", "run": "r1", "direction": "d", "note": "n"}],
    )
    after = dict(before)
    after["claim"] = "Warm-up helps Adam a lot"  # tampered
    after["lineage"] = before["lineage"] + [{"quest": "q2", "run": "r9", "direction": "d", "note": "n2"}]
    with pytest.raises(ValueError, match="claim"):
        validate_cross_quest_patch(before, after, patching_quest="q2")


def test_validate_cross_quest_patch_forbids_confidence_increase():
    before = build_experience_metadata(
        claim="X", mechanism="Y", conditions=["Z"], confidence=0.4,
        lineage=[{"quest": "q1", "run": "r1", "direction": "d", "note": "n"}],
    )
    after = dict(before)
    after["confidence"] = 0.7  # increase not allowed cross-quest
    after["lineage"] = before["lineage"] + [{"quest": "q2", "run": "r9", "direction": "d", "note": "n2"}]
    with pytest.raises(ValueError, match="confidence"):
        validate_cross_quest_patch(before, after, patching_quest="q2")


def test_validate_cross_quest_patch_accepts_lineage_append_and_confidence_downgrade():
    before = build_experience_metadata(
        claim="X", mechanism="Y", conditions=["Z"], confidence=0.6,
        lineage=[{"quest": "q1", "run": "r1", "direction": "d", "note": "n"}],
    )
    after = dict(before)
    after["confidence"] = 0.4  # downgrade OK
    after["lineage"] = before["lineage"] + [{"quest": "q2", "run": "r9", "direction": "d", "note": "n2"}]
    validate_cross_quest_patch(before, after, patching_quest="q2")  # no raise


def test_same_quest_patch_allows_claim_edit():
    before = build_experience_metadata(
        claim="X", mechanism="Y", conditions=["Z"], confidence=0.6,
        lineage=[{"quest": "q1", "run": "r1", "direction": "d", "note": "n"}],
    )
    after = dict(before)
    after["claim"] = "X (refined)"
    validate_cross_quest_patch(before, after, patching_quest="q1")  # same quest — OK
