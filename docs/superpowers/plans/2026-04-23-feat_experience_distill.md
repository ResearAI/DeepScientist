# Experience Distill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After each analysis-campaign run lands, give DS the chance to distill reusable causal intuition into a `knowledge` memory card (`subtype: experience`), patching existing entries when possible. A retroactive CLI produces human-reviewable drafts for past quests.

**Architecture:** Add an opt-in companion skill `distill` plus a post-record routing hook in `ArtifactService.record()` (mirrors the `maybe_inject_*` pattern from the abandoned careful_mode branch). The hook runs only when `startup_contract.experience_distill.mode == "on"` and the record is an analysis-slice run, and rewrites `guidance_vm.recommended_skill = "distill"` so the next agent turn invokes the skill. The skill itself is a prompt — it uses existing `memory.search` / `memory.write_card` tools to decide between patching an existing experience, creating a new one, or writing a null+reason episode card. No new memory kinds, no new DB, no tool-level cross-quest guard in v1 (prompt-level only).

**Tech Stack:** Python 3.11+, pytest, PyYAML, argparse. Existing modules: `deepscientist.memory.service`, `deepscientist.memory.frontmatter`, `deepscientist.artifact.service`, `deepscientist.artifact.guidance`, `deepscientist.skills.registry`.

---

## File Structure

**Create:**
- `src/deepscientist/artifact/experience_distill.py` — config reader, frontmatter validator, routing hook, draft emitter (~180 LOC)
- `src/skills/distill/SKILL.md` — companion skill prompt (~120 LOC markdown)
- `tests/test_experience_distill_schema.py` — frontmatter validator unit tests
- `tests/test_experience_distill_config.py` — mode reader unit tests
- `tests/test_experience_distill_routing.py` — injection hook unit tests
- `tests/test_experience_distill_cli.py` — draft emitter + CLI integration
- `tests/test_experience_distill_skill_bundle.py` — skill registration test

**Modify:**
- `src/deepscientist/artifact/service.py` — invoke hook after `build_guidance_for_record` at line 7414
- `src/deepscientist/skills/registry.py` — add `"distill"` to `_DEFAULT_COMPANION_SKILLS`
- `src/deepscientist/cli.py` — register `distill-quest` subparser + dispatcher branch + handler

**Rationale for one module over several:** the four concerns (config, validation, routing, drafts) all operate on the same domain object (experience entry) and share helpers (`_canonical_lineage_entry`, `_experience_frontmatter_template`). DRY wins over layered directories at this size.

---

## Task 1: Experience frontmatter validator

**Files:**
- Create: `src/deepscientist/artifact/experience_distill.py`
- Create: `tests/test_experience_distill_schema.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_experience_distill_schema.py`:

```python
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
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
cd /home/ds/DeepScientist-distill
pytest tests/test_experience_distill_schema.py -v
```

Expected: `ModuleNotFoundError: No module named 'deepscientist.artifact.experience_distill'`

- [ ] **Step 3: Create module with the helpers**

Create `src/deepscientist/artifact/experience_distill.py`:

```python
"""Experience distillation helpers.

Experience is a `subtype` of the `knowledge` memory kind — not a new kind.
Frontmatter schema enforced here:

    subtype: experience
    claim: <one-sentence mechanism-bearing claim>
    mechanism: <why the claim plausibly holds>
    conditions: [<scoping tags>, ...]
    confidence: 0.0..1.0
    lineage: [{quest, run, direction, note}, ...]

Cross-quest patches may append lineage and downgrade confidence only;
the `claim` text is locked once the card spans more than one quest.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


_REQUIRED_LINEAGE_KEYS = ("quest", "run", "direction", "note")


def build_experience_metadata(
    *,
    claim: str,
    mechanism: str,
    conditions: list[str],
    confidence: float,
    lineage: list[dict[str, str]],
) -> dict[str, Any]:
    """Construct a well-formed experience frontmatter dict."""
    return {
        "subtype": "experience",
        "claim": str(claim).strip(),
        "mechanism": str(mechanism).strip(),
        "conditions": [str(item).strip() for item in (conditions or []) if str(item).strip()],
        "confidence": float(confidence),
        "lineage": [_canonical_lineage_entry(item) for item in (lineage or [])],
    }


def _canonical_lineage_entry(entry: dict[str, Any]) -> dict[str, str]:
    return {key: str(entry.get(key) or "").strip() for key in _REQUIRED_LINEAGE_KEYS}


def validate_experience_metadata(meta: dict[str, Any]) -> None:
    """Raise ValueError if the frontmatter does not satisfy the experience contract."""
    if str(meta.get("subtype") or "").strip() != "experience":
        raise ValueError("Experience frontmatter must have subtype: experience")
    for field in ("claim", "mechanism"):
        if not str(meta.get(field) or "").strip():
            raise ValueError(f"Experience frontmatter missing required field `{field}`")
    conditions = meta.get("conditions") or []
    if not isinstance(conditions, list) or not any(str(item).strip() for item in conditions):
        raise ValueError("Experience frontmatter `conditions` must be a non-empty list of scoping tags")
    confidence = meta.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
        raise ValueError("Experience frontmatter `confidence` must be a float in [0.0, 1.0]")
    lineage = meta.get("lineage") or []
    if not isinstance(lineage, list) or not lineage:
        raise ValueError("Experience frontmatter `lineage` must be a non-empty list")
    for idx, entry in enumerate(lineage):
        if not isinstance(entry, dict):
            raise ValueError(f"Experience lineage[{idx}] must be a dict")
        for key in ("quest", "run"):
            if not str(entry.get(key) or "").strip():
                raise ValueError(f"Experience lineage[{idx}] missing required key `{key}`")


def validate_cross_quest_patch(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    patching_quest: str,
) -> None:
    """Enforce cross-quest patch permissions (prompt-level contract, enforced in tests/CLI).

    Same quest -> free edit. Cross-quest -> claim locked, confidence non-increasing,
    lineage may only grow.
    """
    validate_experience_metadata(after)
    owning_quests = {str(entry.get("quest") or "").strip() for entry in (before.get("lineage") or [])}
    is_same_quest = owning_quests == {patching_quest} or not owning_quests
    if is_same_quest:
        return
    if str(before.get("claim") or "").strip() != str(after.get("claim") or "").strip():
        raise ValueError("Cross-quest patch may not change `claim` text; claim is locked across quests")
    if float(after.get("confidence", 0.0)) > float(before.get("confidence", 0.0)):
        raise ValueError("Cross-quest patch may only downgrade `confidence`, not increase it")
    before_lineage = before.get("lineage") or []
    after_lineage = after.get("lineage") or []
    if len(after_lineage) < len(before_lineage):
        raise ValueError("Cross-quest patch may not shrink lineage")
    if after_lineage[: len(before_lineage)] != before_lineage:
        raise ValueError("Cross-quest patch may not rewrite existing lineage entries, only append")
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/test_experience_distill_schema.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/deepscientist/artifact/experience_distill.py tests/test_experience_distill_schema.py
git commit -m "distill: add experience frontmatter validator and cross-quest patch check"
```

---

## Task 2: Distill mode config reader

**Files:**
- Modify: `src/deepscientist/artifact/experience_distill.py`
- Create: `tests/test_experience_distill_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_experience_distill_config.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from deepscientist.artifact.experience_distill import (
    coerce_distill_mode,
    is_distill_on,
    read_distill_mode,
)


def _write_quest_yaml(quest_root: Path, body: str) -> None:
    quest_root.mkdir(parents=True, exist_ok=True)
    (quest_root / "quest.yaml").write_text(body, encoding="utf-8")


def test_coerce_string_on_off():
    assert coerce_distill_mode("on") == {"mode": "on"}
    assert coerce_distill_mode("OFF") == {"mode": "off"}
    assert coerce_distill_mode("") == {"mode": "off"}
    assert coerce_distill_mode(None) == {"mode": "off"}


def test_coerce_dict_passthrough():
    assert coerce_distill_mode({"mode": "on"}) == {"mode": "on"}
    assert coerce_distill_mode({"mode": "bogus"}) == {"mode": "off"}
    assert coerce_distill_mode({}) == {"mode": "off"}


def test_read_distill_mode_defaults_off(tmp_path: Path):
    qr = tmp_path / "q_demo"
    _write_quest_yaml(qr, "startup_contract: {}\n")
    assert read_distill_mode(qr) == {"mode": "off"}
    assert is_distill_on(qr) is False


def test_read_distill_mode_on(tmp_path: Path):
    qr = tmp_path / "q_demo"
    _write_quest_yaml(
        qr,
        "startup_contract:\n  experience_distill:\n    mode: on\n",
    )
    assert read_distill_mode(qr) == {"mode": "on"}
    assert is_distill_on(qr) is True


def test_read_distill_mode_accepts_bare_string(tmp_path: Path):
    qr = tmp_path / "q_demo"
    _write_quest_yaml(
        qr,
        "startup_contract:\n  experience_distill: on\n",
    )
    assert is_distill_on(qr) is True


def test_read_distill_mode_missing_quest_yaml_defaults_off(tmp_path: Path):
    qr = tmp_path / "q_demo"
    qr.mkdir()
    assert is_distill_on(qr) is False


def test_is_distill_on_accepts_none_quest_root():
    assert is_distill_on(None) is False
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/test_experience_distill_config.py -v
```

Expected: `ImportError: cannot import name 'coerce_distill_mode'`

- [ ] **Step 3: Append config helpers to the module**

Append to `src/deepscientist/artifact/experience_distill.py`:

```python
def coerce_distill_mode(value: Any, *, field_name: str = "experience_distill") -> dict[str, str]:
    """Normalize user-supplied value into {"mode": "on"|"off"}.

    Accepts:
      - bool True/False
      - string "on"/"off" (case-insensitive)
      - dict {"mode": "on"|"off"}
    Anything else collapses to {"mode": "off"}.
    """
    if value is True:
        return {"mode": "on"}
    if value is False or value is None:
        return {"mode": "off"}
    if isinstance(value, str):
        return {"mode": "on" if value.strip().lower() == "on" else "off"}
    if isinstance(value, dict):
        raw = str(value.get("mode") or "").strip().lower()
        return {"mode": "on" if raw == "on" else "off"}
    return {"mode": "off"}


def read_distill_mode(quest_root: Path | None) -> dict[str, str]:
    """Read `startup_contract.experience_distill` from quest.yaml; return normalized dict."""
    if quest_root is None:
        return {"mode": "off"}
    quest_yaml = quest_root / "quest.yaml"
    if not quest_yaml.exists():
        return {"mode": "off"}
    try:
        from ..shared import require_yaml
        require_yaml()
        import yaml  # type: ignore
        payload = yaml.safe_load(quest_yaml.read_text(encoding="utf-8")) or {}
    except Exception:
        return {"mode": "off"}
    if not isinstance(payload, dict):
        return {"mode": "off"}
    contract = payload.get("startup_contract") or {}
    if not isinstance(contract, dict):
        return {"mode": "off"}
    return coerce_distill_mode(contract.get("experience_distill"))


def is_distill_on(quest_root: Path | None) -> bool:
    return read_distill_mode(quest_root)["mode"] == "on"
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/test_experience_distill_config.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/deepscientist/artifact/experience_distill.py tests/test_experience_distill_config.py
git commit -m "distill: add opt-in mode reader for quest.yaml.startup_contract.experience_distill"
```

---

## Task 3: Distill guidance routing hook

**Files:**
- Modify: `src/deepscientist/artifact/experience_distill.py`
- Create: `tests/test_experience_distill_routing.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_experience_distill_routing.py`:

```python
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
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/test_experience_distill_routing.py -v
```

Expected: `ImportError: cannot import name 'maybe_inject_distill_routing'`

- [ ] **Step 3: Append hook to the module**

Append to `src/deepscientist/artifact/experience_distill.py`:

```python
def _is_analysis_slice_terminal(record: dict[str, Any]) -> bool:
    if str(record.get("kind") or "") != "run":
        return False
    run_kind = str(record.get("run_kind") or "")
    if run_kind != "analysis.slice":
        return False
    status = str(record.get("status") or "").strip().lower()
    if status and status not in {"completed", "success", "succeeded", "done"}:
        return False
    return True


def maybe_inject_distill_routing(
    quest_root: Path,
    record: dict[str, Any],
    guidance_vm: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """When distill is on and the record is a completed analysis-slice run,
    return a new guidance_vm recommending the `distill` companion skill.

    Otherwise return guidance_vm unchanged (same object identity).
    Never raises; callers should still wrap in try/except for defense.
    """
    if not is_distill_on(quest_root):
        return guidance_vm
    if not _is_analysis_slice_terminal(record):
        return guidance_vm
    base = dict(guidance_vm) if isinstance(guidance_vm, dict) else {}
    previous_skill = str(base.get("recommended_skill") or "").strip() or None
    previous_action = str(base.get("recommended_action") or "").strip() or None
    routes = list(base.get("alternative_routes") or []) if isinstance(base.get("alternative_routes"), list) else []
    if previous_skill and previous_skill != "distill":
        routes.append(
            {
                "recommended_skill": previous_skill,
                "recommended_action": previous_action or f"Fall back to `{previous_skill}` if nothing to distill.",
                "reason": "Original next step before distill redirect.",
            }
        )
    out = {
        **base,
        "recommended_skill": "distill",
        "recommended_action": "Inspect this analysis slice and distill reusable experience if warranted.",
        "previous_recommended_skill": previous_skill,
        "previous_recommended_action": previous_action,
        "alternative_routes": routes,
        "experience_distill": True,
        "source_artifact_id": str(record.get("artifact_id") or ""),
    }
    return out
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/test_experience_distill_routing.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/deepscientist/artifact/experience_distill.py tests/test_experience_distill_routing.py
git commit -m "distill: add guidance routing hook for analysis-slice runs"
```

---

## Task 4: Wire hook into `ArtifactService.record()`

**Files:**
- Modify: `src/deepscientist/artifact/service.py` at line 7414–7415
- Create: `tests/test_experience_distill_integration.py`

- [ ] **Step 1: Write failing integration test**

Create `tests/test_experience_distill_integration.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from deepscientist.artifact import ArtifactService
from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout
from deepscientist.quest import QuestService


@pytest.fixture
def home_with_quest(tmp_path: Path) -> tuple[Path, str]:
    home = tmp_path / "DeepScientistHome"
    ensure_home_layout(home)
    ConfigManager(home).ensure_defaults()
    quest_id = QuestService(home).create_quest(title="Distill demo", brief="test").get("quest_id")
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


def test_completed_analysis_slice_redirects_guidance_to_distill(home_with_quest):
    home, quest_id = home_with_quest
    quest_root = _enable_distill(home, quest_id)
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
    gvm = record["guidance_vm"]
    assert gvm["recommended_skill"] == "distill"
    assert gvm["experience_distill"] is True


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
```

- [ ] **Step 2: Run integration test, verify redirect tests fail**

```bash
pytest tests/test_experience_distill_integration.py -v
```

Expected: `test_completed_analysis_slice_redirects_guidance_to_distill` FAILS (recommended_skill is whatever `build_guidance_for_record` returned, not `"distill"`). The `off` and `main_experiment` tests should still pass.

- [ ] **Step 3: Modify `record()` in `src/deepscientist/artifact/service.py`**

Find the block at lines 7414–7415:

```python
        guidance_vm = build_guidance_for_record(record)
        record["guidance_vm"] = guidance_vm
```

Replace with:

```python
        guidance_vm = build_guidance_for_record(record)
        try:
            from .experience_distill import maybe_inject_distill_routing

            guidance_vm = maybe_inject_distill_routing(quest_root, record, guidance_vm)
        except Exception:
            pass
        record["guidance_vm"] = guidance_vm
```

Rationale: match the exact shape of the abandoned `careful_mode` injection — defensive `try/except` so a bug in distill helpers never blocks an artifact record.

- [ ] **Step 4: Run integration tests, verify all pass**

```bash
pytest tests/test_experience_distill_integration.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Run full artifact test suite to catch regressions**

```bash
pytest tests/test_memory_and_artifact.py tests/test_artifact_guidance.py -x
```

Expected: all pre-existing tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/deepscientist/artifact/service.py tests/test_experience_distill_integration.py
git commit -m "distill: wire routing hook into ArtifactService.record()"
```

---

## Task 5: Register `distill` as a companion skill

**Files:**
- Modify: `src/deepscientist/skills/registry.py:21–27`
- Create: `tests/test_experience_distill_skill_bundle.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_experience_distill_skill_bundle.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from deepscientist.home import repo_root
from deepscientist.skills.registry import (
    _DEFAULT_COMPANION_SKILLS,
    discover_skill_bundles,
)


def test_distill_in_default_companions():
    assert "distill" in _DEFAULT_COMPANION_SKILLS


def test_distill_skill_bundle_is_discoverable():
    root = repo_root()
    bundles = discover_skill_bundles(root)
    ids = {bundle.skill_id for bundle in bundles}
    assert "distill" in ids, f"Expected distill skill; got {sorted(ids)}"
    distill = next(bundle for bundle in bundles if bundle.skill_id == "distill")
    assert distill.skill_md.exists()
    assert distill.metadata.get("name") == "distill"
    assert "experience" in (distill.metadata.get("description") or "").lower()
    assert distill.metadata.get("skill_role") == "companion"
```

- [ ] **Step 2: Run test, verify it fails**

```bash
pytest tests/test_experience_distill_skill_bundle.py -v
```

Expected: FAIL — `"distill" not in _DEFAULT_COMPANION_SKILLS`.

- [ ] **Step 3: Add `"distill"` to the tuple**

Edit `src/deepscientist/skills/registry.py`. Find:

```python
_DEFAULT_COMPANION_SKILLS = (
    "paper-plot",
    "figure-polish",
    "intake-audit",
    "review",
    "rebuttal",
)
```

Replace with:

```python
_DEFAULT_COMPANION_SKILLS = (
    "paper-plot",
    "figure-polish",
    "intake-audit",
    "review",
    "rebuttal",
    "distill",
)
```

- [ ] **Step 4: Run test — first assertion passes, second still fails**

```bash
pytest tests/test_experience_distill_skill_bundle.py::test_distill_in_default_companions -v
```

Expected: PASS.

The second test needs `src/skills/distill/SKILL.md` — covered in Task 6.

- [ ] **Step 5: Commit (partial — registry only)**

```bash
git add src/deepscientist/skills/registry.py tests/test_experience_distill_skill_bundle.py
git commit -m "skills: reserve 'distill' slot in default companions (SKILL.md lands next)"
```

---

## Task 6: Write `src/skills/distill/SKILL.md`

**Files:**
- Create: `src/skills/distill/SKILL.md`

- [ ] **Step 1: Write the skill markdown**

Create `src/skills/distill/SKILL.md`:

```markdown
---
name: distill
description: Use right after an analysis-slice run lands to extract reusable causal intuition into a `knowledge` memory card (`subtype: experience`). Default to patching an existing entry; create a new one only when no similar claim exists; write a null+reason episode when nothing is worth distilling.
skill_role: companion
---

# Distill

Run this skill after an analysis-slice completes. Your job is **not** to write a lab notebook entry — it is to decide whether this slice produced a reusable, mechanism-bearing piece of intuition, and if so, to persist it in a form that will actually help future quests.

## When to distill

Distill when **at least one** of the following holds:

- **Non-obvious success**: a method worked in a way that could not have been predicted from the paper abstract alone. The "why it worked" is the payload.
- **Informative failure**: a method broke in a way that teaches about the mechanism, not just about a bad hyperparameter.
- **Contradiction with existing experience**: a prior experience card implied X; this run shows X does not hold under these conditions.
- **Condition refinement**: a prior experience card made a claim; this run sharpens the *conditions* under which it holds.

If none of the above apply, **output a null+reason episode** (see below) rather than inventing a new entry. Token-cost without signal is the worst outcome.

## Protocol

### 1. Search for neighbors

Before writing anything, search global experience entries for similar claims:

```json
{"tool": "memory.search", "arguments": {"query": "<keywords from this slice>", "scope": "global", "kind": "knowledge", "limit": 10}}
```

Read the top 3 matches. Ask: is any of them making a claim in the same causal neighborhood as what I just observed?

### 2. Decide one of three outcomes

**A. Patch an existing entry (default when a neighbor is found)**

Read the target card, then `memory.write_card` with `markdown=` containing the original frontmatter plus:
- one new lineage entry `{quest, run, direction, note}` appended to `lineage:`
- `confidence:` adjusted (see rules below)
- `conditions:` narrowed if this slice revealed a scoping limit
- `claim:` **locked** if the target card already has lineage entries from another quest. Only same-quest patches may edit claim text.

Cross-quest patch rules (prompt-enforced, validated by the retroactive CLI):
- `claim` is immutable.
- `confidence` is monotone non-increasing — you may lower it, never raise it.
- `lineage` grows only; existing entries are never rewritten.
- `mechanism` may be clarified but the core causal direction must match.

**B. Create a new entry (only when no neighbor exists)**

Use `memory.write_card` with `scope="global"`, `kind="knowledge"`, and a frontmatter that includes:

```yaml
subtype: experience
claim: <one sentence, mechanism-bearing, falsifiable>
mechanism: <why this plausibly holds — the causal chain>
conditions:
  - <scoping tag 1>
  - <scoping tag 2>
confidence: <0.0..1.0; be honest — 0.4 is a fine starting value>
lineage:
  - quest: <quest_id>
    run: <run_id, e.g. cmp_1:s_1>
    direction: <direction or goal id>
    note: <one-phrase takeaway>
```

The body of the card should be 3–8 lines of prose explaining the reasoning. Do not dump the full experiment log — future readers do not need it.

**C. Null + reason (write to quest-scoped episode, not global)**

If no trigger fires, `memory.write_card` with `scope="quest"`, `kind="episodes"`, title like `"distill: no experience extracted from <slice_id>"`, and a two-sentence body naming what was examined and why it did not meet the threshold. This prevents silent drops and gives the next retroactive CLI pass a clear record.

### 3. Hard constraints on new/patched entries

A rejection reviewer will apply these:

- `claim` must name a **mechanism**, not just an outcome. "X improved accuracy" is rejected; "X helps because it shortens the gradient path through Y" is accepted.
- `conditions` must name at least one scoping tag. If a claim holds "always", you are not being specific enough.
- `lineage[*]` must cite a real `quest` and `run`. Forge nothing.
- No numeric forecasts. Do not write "method will improve metric by 3%". Write *why* it might improve, under what conditions.

### 4. What not to do

- Do not invoke this skill if the slice was inconclusive — output a null episode.
- Do not create a new entry when a neighbor exists; patching is the default.
- Do not remove other quests' lineage entries. Ever.
- Do not promote confidence across quests. Only the original quest may raise confidence on a card.

## Output

End with a single JSON summary line for downstream tooling:

```json
{"outcome": "patch" | "new" | "null", "card_id": "<id or null>", "reason": "<short>"}
```
```

- [ ] **Step 2: Run skill bundle test, verify full pass**

```bash
pytest tests/test_experience_distill_skill_bundle.py -v
```

Expected: both tests PASS.

- [ ] **Step 3: Commit**

```bash
git add src/skills/distill/SKILL.md
git commit -m "skills: add distill companion skill prompt"
```

---

## Task 7: CLI `distill-quest` retroactive draft emission

**Files:**
- Modify: `src/deepscientist/artifact/experience_distill.py` (add `emit_experience_drafts`)
- Modify: `src/deepscientist/cli.py` at line 141 area (parser) and 637–670 area (dispatcher)
- Create: `tests/test_experience_distill_cli.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_experience_distill_cli.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from deepscientist.artifact import ArtifactService
from deepscientist.artifact.experience_distill import (
    emit_experience_drafts,
    iter_analysis_slice_records,
)
from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout
from deepscientist.quest import QuestService


def test_emit_experience_drafts_writes_one_file_per_slice(tmp_path: Path):
    drafts_root = tmp_path / "drafts_out"
    records = [
        {
            "artifact_id": "a1",
            "kind": "run",
            "run_kind": "analysis.slice",
            "status": "completed",
            "run_id": "cmp_1:s_1",
            "campaign_id": "cmp_1",
            "slice_id": "s_1",
            "details": {"title": "Warm-up effect on CNNs"},
            "summary": "Warm-up helps on small batch",
        },
        {
            "artifact_id": "a2",
            "kind": "run",
            "run_kind": "analysis.slice",
            "status": "completed",
            "run_id": "cmp_1:s_2",
            "campaign_id": "cmp_1",
            "slice_id": "s_2",
            "details": {"title": "Cooldown effect"},
            "summary": "Cooldown mostly neutral",
        },
        {
            "artifact_id": "a3",
            "kind": "run",
            "run_kind": "main.experiment",  # not a slice — must be skipped
        },
    ]
    written = emit_experience_drafts(quest_id="q_demo", records=records, drafts_root=drafts_root)
    assert len(written) == 2
    draft_dir = drafts_root / "q_demo"
    assert (draft_dir / "cmp_1__s_1.md").exists()
    assert (draft_dir / "cmp_1__s_2.md").exists()
    body = (draft_dir / "cmp_1__s_1.md").read_text(encoding="utf-8")
    assert "subtype: experience" in body
    assert "quest: q_demo" in body
    assert "run: cmp_1:s_1" in body
    assert "TODO: claim" in body  # human prompt
    assert "TODO: mechanism" in body
    assert "Warm-up effect on CNNs" in body  # slice title surfaced


def test_iter_analysis_slice_records_filters_index(tmp_path: Path):
    # Minimal synthesized artifact tree: _index.jsonl plus per-kind JSONs
    artifacts = tmp_path / "artifacts"
    run_dir = artifacts / "runs"
    run_dir.mkdir(parents=True)
    index = artifacts / "_index.jsonl"
    a1 = {
        "artifact_id": "a1", "kind": "run", "run_kind": "analysis.slice",
        "status": "completed", "run_id": "c:1", "campaign_id": "c", "slice_id": "s1",
    }
    a2 = {"artifact_id": "a2", "kind": "run", "run_kind": "main.experiment", "status": "completed"}
    (run_dir / "a1.json").write_text(json.dumps(a1), encoding="utf-8")
    (run_dir / "a2.json").write_text(json.dumps(a2), encoding="utf-8")
    index.write_text(
        "\n".join(
            json.dumps({"artifact_id": x["artifact_id"], "kind": x["kind"], "status": x["status"], "path": str(run_dir / f'{x["artifact_id"]}.json')})
            for x in (a1, a2)
        ) + "\n",
        encoding="utf-8",
    )
    records = list(iter_analysis_slice_records(artifacts))
    assert [r["artifact_id"] for r in records] == ["a1"]


def test_distill_quest_cli_end_to_end(tmp_path: Path, capsys):
    # Full CLI path: create quest, plant a completed analysis.slice record, run command.
    home = tmp_path / "DeepScientistHome"
    ensure_home_layout(home)
    ConfigManager(home).ensure_defaults()
    quest = QuestService(home).create_quest(title="Distill retro demo", brief="t")
    quest_id = quest["quest_id"]
    quest_root = home / "quests" / quest_id
    ArtifactService(home).record(
        quest_root,
        {
            "kind": "run",
            "run_kind": "analysis.slice",
            "status": "completed",
            "run_id": "cmp_1:s_1",
            "summary": "Slice 1 recorded",
        },
    )
    from deepscientist.cli import distill_quest_command
    rc = distill_quest_command(home, quest_id)
    assert rc == 0
    drafts_dir = home / "drafts" / "experiences" / quest_id
    files = list(drafts_dir.glob("*.md"))
    assert len(files) == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["quest_id"] == quest_id
    assert payload["drafts"] == 1
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/test_experience_distill_cli.py -v
```

Expected: ImportError on `emit_experience_drafts` / `iter_analysis_slice_records` / `distill_quest_command`.

- [ ] **Step 3: Append draft emission helpers to experience_distill.py**

Append to `src/deepscientist/artifact/experience_distill.py`:

```python
def iter_analysis_slice_records(artifacts_dir: Path) -> Iterable[dict[str, Any]]:
    """Yield full analysis-slice run records by reading the artifact index."""
    import json
    index_path = artifacts_dir / "_index.jsonl"
    if not index_path.exists():
        return
    for line in index_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if entry.get("kind") != "run":
            continue
        record_path = Path(str(entry.get("path") or ""))
        if not record_path.exists():
            continue
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if _is_analysis_slice_terminal(record):
            yield record


def emit_experience_drafts(
    *,
    quest_id: str,
    records: list[dict[str, Any]] | Iterable[dict[str, Any]],
    drafts_root: Path,
) -> list[Path]:
    """Write one draft markdown per analysis-slice record.

    Each draft has experience frontmatter with lineage pre-filled and
    TODO placeholders for claim/mechanism/conditions/confidence. The
    human reviewer edits these and promotes the card to global memory.
    """
    slices = [r for r in records if _is_analysis_slice_terminal(r)]
    quest_dir = drafts_root / quest_id
    quest_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for record in slices:
        campaign_id = str(record.get("campaign_id") or "cmp").strip() or "cmp"
        slice_id = str(record.get("slice_id") or record.get("artifact_id") or "slice").strip() or "slice"
        run_id = str(record.get("run_id") or f"{campaign_id}:{slice_id}")
        title = str((record.get("details") or {}).get("title") or record.get("summary") or slice_id)
        body = _render_experience_draft(
            quest_id=quest_id,
            run_id=run_id,
            campaign_id=campaign_id,
            slice_id=slice_id,
            title=title,
            summary=str(record.get("summary") or ""),
        )
        path = quest_dir / f"{campaign_id}__{slice_id}.md"
        path.write_text(body, encoding="utf-8")
        written.append(path)
    return written


def _render_experience_draft(
    *,
    quest_id: str,
    run_id: str,
    campaign_id: str,
    slice_id: str,
    title: str,
    summary: str,
) -> str:
    return (
        "---\n"
        "subtype: experience\n"
        "claim: \"TODO: claim — one mechanism-bearing sentence.\"\n"
        "mechanism: \"TODO: mechanism — why this plausibly holds.\"\n"
        "conditions:\n"
        "  - \"TODO: at least one scoping tag\"\n"
        "confidence: 0.4\n"
        "lineage:\n"
        f"  - quest: {quest_id}\n"
        f"    run: {run_id}\n"
        f"    direction: {campaign_id}\n"
        f"    note: \"{title}\"\n"
        "---\n"
        f"# Draft experience from {campaign_id}:{slice_id}\n\n"
        f"Source summary: {summary or '(empty)'}\n\n"
        "Write 3–8 lines of prose explaining the causal story. Delete this guidance\n"
        "block when you promote the card to global memory.\n"
    )
```

- [ ] **Step 4: Add CLI handler, parser, dispatcher branch**

Edit `src/deepscientist/cli.py`.

After `note_parser.add_argument("text")` (around line 143), add:

```python
    distill_parser = subparsers.add_parser("distill-quest")
    distill_parser.add_argument("quest_id")
```

After `def note_command(...)` (around line 484), add:

```python
def distill_quest_command(home: Path, quest_id: str) -> int:
    from .artifact.experience_distill import emit_experience_drafts, iter_analysis_slice_records

    quest_root = home / "quests" / quest_id
    artifacts_dir = quest_root / "artifacts"
    drafts_root = home / "drafts" / "experiences"
    records = list(iter_analysis_slice_records(artifacts_dir))
    emit_experience_drafts(quest_id=quest_id, records=records, drafts_root=drafts_root)
    print(
        json.dumps(
            {"quest_id": quest_id, "drafts": len(records), "drafts_root": str(drafts_root / quest_id)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0
```

In the dispatcher (the `if args.command == "note"` chain around line 643), add before `parser.error(...)`:

```python
    if args.command == "distill-quest":
        return distill_quest_command(home, args.quest_id)
```

- [ ] **Step 5: Run tests, verify they pass**

```bash
pytest tests/test_experience_distill_cli.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Smoke-test the CLI**

```bash
python -m deepscientist.cli distill-quest --help
```

Expected: usage line showing `quest_id` positional.

- [ ] **Step 7: Commit**

```bash
git add src/deepscientist/artifact/experience_distill.py src/deepscientist/cli.py tests/test_experience_distill_cli.py
git commit -m "distill: add ds distill-quest CLI for retroactive draft emission"
```

---

## Task 8: Regression sweep + final verification

**Files:** none (validation only)

- [ ] **Step 1: Run the full focused test suite**

```bash
pytest tests/test_experience_distill_schema.py \
       tests/test_experience_distill_config.py \
       tests/test_experience_distill_routing.py \
       tests/test_experience_distill_integration.py \
       tests/test_experience_distill_skill_bundle.py \
       tests/test_experience_distill_cli.py -v
```

Expected: every test PASSES.

- [ ] **Step 2: Run the wider regression set that covers surfaces we touched**

```bash
pytest tests/test_memory_and_artifact.py \
       tests/test_artifact_guidance.py \
       tests/test_prompt_builder.py \
       tests/test_init_and_quest.py -x
```

Expected: all pre-existing tests PASS (no regressions from the `record()` hook).

- [ ] **Step 3: Lint-check the new module**

```bash
python -m compileall src/deepscientist/artifact/experience_distill.py src/deepscientist/cli.py
```

Expected: no errors.

- [ ] **Step 4: Commit any small fixes, else mark plan complete**

If any of steps 1–3 surfaced an issue, fix it with a dedicated commit (`fix(distill): …`) rather than amending.

```bash
git log --oneline origin/main..HEAD
```

Expected: ~7 commits on `feat_experience_distill` covering tasks 1–7, all with `distill:` or `skills:` prefix.
