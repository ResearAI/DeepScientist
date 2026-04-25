# Distill Finalize Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a finalize-stage gate that routes the agent to the `distill` companion skill before write/finalize whenever completed runs (analysis.slice / main_experiment / experiment) have not yet been distilled.

**Architecture:** Implement as an overlay function in `experience_distill.py` (mirrors existing `maybe_inject_distill_routing`), wired from `service.py` after `build_guidance_for_record`. State derives from a new `distill_review` artifact stream (set-difference cursor — no stored cursor field). New `artifact.list_distill_candidates` MCP tool returns the diffed candidate list directly so the skill does not have to assemble it.

**Tech Stack:** Python 3 (pytest), FastMCP, existing artifact/guidance/service stack in `src/deepscientist/`.

**Spec:** [docs/superpowers/specs/2026-04-25-distill-finalize-gate-design.md](../specs/2026-04-25-distill-finalize-gate-design.md)

**Implementation deviation from spec § 1:** Spec said "Hook location: guidance.py decision branch". Actual location is `experience_distill.py` overlay + `service.py` wire-in, because `build_guidance_for_record(record)` is a pure record→guidance function with no quest_root parameter; existing distill routing already uses this overlay pattern (`service.py:7416-7418`). Same intent, cleaner separation.

---

## File Structure

| File | Role | Action |
|---|---|---|
| `src/deepscientist/artifact/schemas.py` | Artifact kind registry + payload validation | Modify: register `distill_review` kind, add validation |
| `src/deepscientist/artifact/experience_distill.py` | Distill helpers (existing) | Modify: add `iter_distill_candidate_records`, `evaluate_distill_gate`, `maybe_inject_distill_finalize_gate` |
| `src/deepscientist/artifact/service.py` | Artifact recording + service methods | Modify: wire the overlay (`record_artifact`), add `list_distill_candidates` |
| `src/deepscientist/mcp/server.py` | MCP tool surface | Modify: register `artifact.list_distill_candidates` |
| `src/skills/distill/SKILL.md` | Distill companion skill prompt | Modify: rewrite to per-batch flow, replace null-episode path with `distill_review` |
| `src/deepscientist/cli.py` | Retroactive CLI helper | Modify: extend candidate range and respect `distill_review` history |
| `tests/test_artifact_schemas.py` | Schema tests | Modify: add `distill_review` validation cases (file may not yet exist — see Task 1) |
| `tests/test_experience_distill_routing.py` | Routing tests | Modify: add finalize-gate cases |
| `tests/test_experience_distill_integration.py` | End-to-end integration | Modify: add gate→distill_review→cleared cycle |
| `tests/test_mcp_servers.py` | MCP tool tests | Modify: add `list_distill_candidates` cases |

---

## Task 1: Register `distill_review` artifact kind

**Files:**
- Modify: `src/deepscientist/artifact/schemas.py`
- Test: `tests/test_artifact_schemas_distill_review.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_artifact_schemas_distill_review.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_artifact_schemas_distill_review.py -v`
Expected: All seven tests FAIL — `KeyError: 'distill_review'` in the first, validation pass-through in the others.

- [ ] **Step 3: Implement schema**

Edit `src/deepscientist/artifact/schemas.py`:

```python
ARTIFACT_DIRS = {
    "baseline": "baselines",
    "idea": "ideas",
    "decision": "decisions",
    "progress": "progress",
    "answer": "answers",
    "milestone": "milestones",
    "run": "runs",
    "report": "reports",
    "approval": "approvals",
    "graph": "graphs",
    "distill_review": "distill_reviews",
}
```

Then in `validate_artifact_payload`, add this block before the trailing `return errors`:

```python
    if kind == "distill_review":
        reviewed = payload.get("reviewed_run_ids") or []
        if not isinstance(reviewed, list) or not reviewed:
            errors.append("distill_review artifact requires non-empty `reviewed_run_ids`.")
            return errors
        cards = payload.get("cards_written")
        if cards is None or not isinstance(cards, list):
            errors.append("distill_review artifact requires `cards_written` (may be empty list).")
            return errors
        if not cards and not str(payload.get("reason_if_empty") or "").strip():
            errors.append(
                "distill_review with empty `cards_written` requires `reason_if_empty`."
            )
        reviewed_set = set(str(rid) for rid in reviewed)
        allowed_actions = {"new", "patch"}
        allowed_scopes = {"global", "quest"}
        for idx, card in enumerate(cards):
            if not isinstance(card, dict):
                errors.append(f"distill_review.cards_written[{idx}] must be an object.")
                continue
            target = str(card.get("target_run_id") or "")
            if target not in reviewed_set:
                errors.append(
                    f"distill_review.cards_written[{idx}].target_run_id `{target}` "
                    f"must be present in `reviewed_run_ids`."
                )
            action = str(card.get("action") or "")
            if action not in allowed_actions:
                errors.append(
                    f"distill_review.cards_written[{idx}].action `{action}` "
                    f"must be one of {sorted(allowed_actions)}."
                )
            scope = str(card.get("scope") or "")
            if scope not in allowed_scopes:
                errors.append(
                    f"distill_review.cards_written[{idx}].scope `{scope}` "
                    f"must be one of {sorted(allowed_scopes)}."
                )
```

Also extend `guidance_for_kind`:

```python
    if kind == "distill_review":
        return "Distill review recorded. The finalize gate cursor advances; resume the original write/finalize route."
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_artifact_schemas_distill_review.py -v`
Expected: all seven PASS.

- [ ] **Step 5: Commit**

```bash
git add src/deepscientist/artifact/schemas.py tests/test_artifact_schemas_distill_review.py
git commit -m "feat(artifact): add distill_review kind + payload validation"
```

---

## Task 2: Add `iter_distill_candidate_records` helper

**Files:**
- Modify: `src/deepscientist/artifact/experience_distill.py`
- Test: `tests/test_experience_distill_candidates.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_experience_distill_candidates.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_experience_distill_candidates.py -v`
Expected: ImportError on `DISTILL_CANDIDATE_RUN_KINDS` and `iter_distill_candidate_records`.

- [ ] **Step 3: Implement helper**

Edit `src/deepscientist/artifact/experience_distill.py`. Locate the existing `iter_analysis_slice_records` function (around line 206) and add the following next to it:

```python
DISTILL_CANDIDATE_RUN_KINDS: frozenset[str] = frozenset(
    {"analysis.slice", "main_experiment", "experiment"}
)


def _is_distill_candidate(record: dict[str, Any], allowed_kinds: frozenset[str]) -> bool:
    if str(record.get("kind") or "") != "run":
        return False
    if str(record.get("run_kind") or "") not in allowed_kinds:
        return False
    status = str(record.get("status") or "").strip().lower()
    return status in {"completed", "success", "succeeded", "done"}


def iter_distill_candidate_records(
    artifacts_dir: Path,
    *,
    run_kinds: frozenset[str] | set[str] | None = None,
) -> Iterable[dict[str, Any]]:
    """Yield completed run records eligible for distillation.

    Default kinds cover analysis.slice, main_experiment, and experiment.
    Pass `run_kinds` to narrow or widen the scope.
    """
    import json

    allowed = frozenset(run_kinds) if run_kinds else DISTILL_CANDIDATE_RUN_KINDS
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
        if _is_distill_candidate(record, allowed):
            yield record
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_experience_distill_candidates.py -v`
Expected: all five PASS.

- [ ] **Step 5: Commit**

```bash
git add src/deepscientist/artifact/experience_distill.py tests/test_experience_distill_candidates.py
git commit -m "feat(distill): add iter_distill_candidate_records helper"
```

---

## Task 3: Add `evaluate_distill_gate` core function

**Files:**
- Modify: `src/deepscientist/artifact/experience_distill.py`
- Test: `tests/test_experience_distill_gate.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_experience_distill_gate.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_experience_distill_gate.py -v`
Expected: ImportError on `evaluate_distill_gate`.

- [ ] **Step 3: Implement function**

Edit `src/deepscientist/artifact/experience_distill.py`. Add at end of file:

```python
def _read_distill_reviews(artifacts_dir: Path) -> list[dict[str, Any]]:
    import json
    index_path = artifacts_dir / "_index.jsonl"
    if not index_path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if entry.get("kind") != "distill_review":
            continue
        record_path = Path(str(entry.get("path") or ""))
        if not record_path.exists():
            continue
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append(record)
    return out


def evaluate_distill_gate(
    quest_root: Path,
    artifacts_dir: Path,
) -> dict[str, Any] | None:
    """Return a gate payload if the agent should be routed to distill, else None.

    Returned dict shape:
      {
        "pending_distill_count": int,        # total candidates past the reviewed set
        "pending_distill_ids": list[str],    # first 5 candidate artifact_ids
        "cursor_run_created_at": str | None, # latest review timestamp, if any
      }
    """
    if not is_distill_on(quest_root):
        return None
    reviews = _read_distill_reviews(artifacts_dir)
    reviewed_set: set[str] = set()
    cursor_created_at: str | None = None
    for rec in reviews:
        for rid in rec.get("reviewed_run_ids") or []:
            reviewed_set.add(str(rid))
        ts = str(rec.get("created_at") or "")
        if ts and (cursor_created_at is None or ts > cursor_created_at):
            cursor_created_at = ts
    candidates = [
        rec for rec in iter_distill_candidate_records(artifacts_dir)
        if str(rec.get("artifact_id") or "") not in reviewed_set
    ]
    if not candidates:
        return None
    ids = [str(rec.get("artifact_id") or "") for rec in candidates]
    return {
        "pending_distill_count": len(candidates),
        "pending_distill_ids": ids[:5],
        "cursor_run_created_at": cursor_created_at,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_experience_distill_gate.py -v`
Expected: all six PASS.

- [ ] **Step 5: Commit**

```bash
git add src/deepscientist/artifact/experience_distill.py tests/test_experience_distill_gate.py
git commit -m "feat(distill): add evaluate_distill_gate set-difference cursor"
```

---

## Task 4: Add `maybe_inject_distill_finalize_gate` overlay

**Files:**
- Modify: `src/deepscientist/artifact/experience_distill.py`
- Test: `tests/test_experience_distill_finalize_gate.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_experience_distill_finalize_gate.py`. Reuse the seeding helpers — copy them to top of file (DRY note: keep helpers local; importing from another test file is fragile).

```python
from __future__ import annotations

import json
from pathlib import Path

from deepscientist.artifact.experience_distill import maybe_inject_distill_finalize_gate


def _make_quest(tmp_path: Path) -> Path:
    qr = tmp_path / "q"
    qr.mkdir()
    (qr / "quest.yaml").write_text(
        "startup_contract:\n  experience_distill:\n    mode: on\n",
        encoding="utf-8",
    )
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


def _decision_record(action: str) -> dict:
    return {
        "kind": "decision",
        "action": action,
        "artifact_id": "decision-zzz",
        "reason": "test",
    }


def _baseline_guidance() -> dict:
    return {
        "schema_version": 1,
        "recommended_skill": "write",
        "recommended_action": "write",
        "alternative_routes": [],
    }


def test_no_change_for_non_decision_record(tmp_path: Path):
    qr = _make_quest(tmp_path)
    artifacts = qr / "artifacts"
    _seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    record = {"kind": "run", "run_kind": "main_experiment", "status": "completed"}
    gvm = _baseline_guidance()
    out = maybe_inject_distill_finalize_gate(qr, artifacts, record, gvm)
    assert out is gvm


def test_no_change_for_unrelated_decision_action(tmp_path: Path):
    qr = _make_quest(tmp_path)
    artifacts = qr / "artifacts"
    _seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    gvm = _baseline_guidance()
    out = maybe_inject_distill_finalize_gate(qr, artifacts, _decision_record("launch_experiment"), gvm)
    assert out is gvm


def test_no_change_when_gate_clear(tmp_path: Path):
    qr = _make_quest(tmp_path)
    artifacts = qr / "artifacts"
    _seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "idea", "status": "completed"}])
    gvm = _baseline_guidance()
    out = maybe_inject_distill_finalize_gate(qr, artifacts, _decision_record("write"), gvm)
    assert out is gvm


def test_redirect_when_decision_write_with_pending_candidates(tmp_path: Path):
    qr = _make_quest(tmp_path)
    artifacts = qr / "artifacts"
    _seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    gvm = _baseline_guidance()
    out = maybe_inject_distill_finalize_gate(qr, artifacts, _decision_record("write"), gvm)
    assert out is not gvm
    assert out["recommended_skill"] == "distill"
    assert out["previous_recommended_skill"] == "write"
    assert out["pending_distill_count"] == 1
    assert "run-1" in out["pending_distill_ids"]
    assert out["experience_distill"] is True
    assert out["gate"] == "finalize"
    assert any(r.get("recommended_skill") == "write" for r in out["alternative_routes"])


def test_redirect_when_decision_finalize_with_pending_candidates(tmp_path: Path):
    qr = _make_quest(tmp_path)
    artifacts = qr / "artifacts"
    _seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    base = _baseline_guidance()
    base["recommended_skill"] = "finalize"
    base["recommended_action"] = "finalize"
    out = maybe_inject_distill_finalize_gate(qr, artifacts, _decision_record("finalize"), base)
    assert out is not base
    assert out["recommended_skill"] == "distill"
    assert out["previous_recommended_skill"] == "finalize"


def test_does_not_mutate_input_guidance(tmp_path: Path):
    qr = _make_quest(tmp_path)
    artifacts = qr / "artifacts"
    _seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    gvm = _baseline_guidance()
    snapshot = json.loads(json.dumps(gvm))
    maybe_inject_distill_finalize_gate(qr, artifacts, _decision_record("write"), gvm)
    assert gvm == snapshot


def test_handles_none_guidance_vm(tmp_path: Path):
    qr = _make_quest(tmp_path)
    artifacts = qr / "artifacts"
    _seed_runs(artifacts, [{"artifact_id": "run-1", "kind": "run", "run_kind": "main_experiment", "status": "completed"}])
    out = maybe_inject_distill_finalize_gate(qr, artifacts, _decision_record("write"), None)
    assert out is not None
    assert out["recommended_skill"] == "distill"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_experience_distill_finalize_gate.py -v`
Expected: ImportError on `maybe_inject_distill_finalize_gate`.

- [ ] **Step 3: Implement overlay**

Append to `src/deepscientist/artifact/experience_distill.py`:

```python
_FINALIZE_GATE_ACTIONS: frozenset[str] = frozenset({"write", "finalize"})


def maybe_inject_distill_finalize_gate(
    quest_root: Path,
    artifacts_dir: Path,
    record: dict[str, Any],
    guidance_vm: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Pre-write/pre-finalize sweep.

    When the agent records `decision(action='write'|'finalize')` and the quest
    has completed runs not yet covered by any `distill_review`, swap the
    recommended_skill to `distill` and surface the candidate count. Returns
    `guidance_vm` unchanged (same identity) when the gate does not fire.
    """
    if str(record.get("kind") or "") != "decision":
        return guidance_vm
    if str(record.get("action") or "") not in _FINALIZE_GATE_ACTIONS:
        return guidance_vm
    gate = evaluate_distill_gate(quest_root, artifacts_dir)
    if gate is None:
        return guidance_vm
    base = dict(guidance_vm) if isinstance(guidance_vm, dict) else {}
    previous_skill = str(base.get("recommended_skill") or "").strip() or None
    previous_action = str(base.get("recommended_action") or "").strip() or None
    routes = list(base.get("alternative_routes") or []) if isinstance(base.get("alternative_routes"), list) else []
    if previous_skill and previous_skill != "distill":
        routes.append(
            {
                "recommended_skill": previous_skill,
                "recommended_action": previous_action or f"Resume `{previous_skill}` after distill_review is recorded.",
                "reason": "Original next step before the finalize gate fired.",
            }
        )
    return {
        **base,
        "recommended_skill": "distill",
        "recommended_action": (
            "Review undistilled completed runs and record a `distill_review` "
            "before resuming write/finalize."
        ),
        "previous_recommended_skill": previous_skill,
        "previous_recommended_action": previous_action,
        "alternative_routes": routes,
        "experience_distill": True,
        "gate": "finalize",
        "pending_distill_count": gate["pending_distill_count"],
        "pending_distill_ids": gate["pending_distill_ids"],
        "cursor_run_created_at": gate.get("cursor_run_created_at"),
        "source_artifact_id": str(record.get("artifact_id") or ""),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_experience_distill_finalize_gate.py -v`
Expected: all seven PASS.

- [ ] **Step 5: Commit**

```bash
git add src/deepscientist/artifact/experience_distill.py tests/test_experience_distill_finalize_gate.py
git commit -m "feat(distill): add maybe_inject_distill_finalize_gate overlay"
```

---

## Task 5: Wire overlay into service.record_artifact

**Files:**
- Modify: `src/deepscientist/artifact/service.py:7414-7420`
- Test: extend `tests/test_experience_distill_integration.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_experience_distill_integration.py` a fixture-based test that walks through `ArtifactService.record_artifact`. First scan the existing file to learn its setup pattern:

```bash
grep -nE "ArtifactService|record_artifact|class Test|def test_" tests/test_experience_distill_integration.py | head -30
```

Use the existing fixture style. Add this test (adapt setup helpers to whatever is already there):

```python
def test_decision_write_record_includes_finalize_gate_when_pending(tmp_path: Path, ...):
    # Bootstrap a quest with experience_distill on and one completed main_experiment run.
    # Record decision(action='write') via ArtifactService.record_artifact.
    # Assert the returned record's guidance_vm has:
    #   recommended_skill == 'distill'
    #   gate == 'finalize'
    #   pending_distill_count >= 1
    ...


def test_decision_write_record_skips_gate_when_distill_off(tmp_path: Path, ...):
    # Same setup but quest.yaml has experience_distill: off.
    # Record decision(action='write').
    # Assert recommended_skill == 'write' (no swap).
    ...


def test_finalize_gate_clears_after_distill_review(tmp_path: Path, ...):
    # Setup with one completed main_experiment.
    # Record decision(write) -> assert gate fires.
    # Record distill_review covering that run.
    # Record decision(write) again -> assert recommended_skill == 'write' (gate cleared).
    ...
```

The actual fixture wiring depends on what `ArtifactService` requires (home dir, quest setup, baseline gate). Read existing tests to match — likely you need to use `make_quest_with_baseline` or an equivalent helper from `conftest.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_experience_distill_integration.py -v -k "finalize_gate"`
Expected: tests fail because the wiring is not in place yet.

- [ ] **Step 3: Wire the overlay into service.py**

Edit `src/deepscientist/artifact/service.py` around line 7414-7420. Current code:

```python
        guidance_vm = build_guidance_for_record(record)
        try:
            from .experience_distill import maybe_inject_distill_routing

            guidance_vm = maybe_inject_distill_routing(quest_root, record, guidance_vm)
        except Exception:
            pass
```

Change to:

```python
        guidance_vm = build_guidance_for_record(record)
        try:
            from .experience_distill import (
                maybe_inject_distill_finalize_gate,
                maybe_inject_distill_routing,
            )

            guidance_vm = maybe_inject_distill_routing(quest_root, record, guidance_vm)
            guidance_vm = maybe_inject_distill_finalize_gate(
                quest_root, write_root / "artifacts", record, guidance_vm,
            )
        except Exception:
            pass
```

(The order — routing first, then finalize-gate — is intentional: per-slice routing already runs at the moment the slice lands; the finalize-gate triggers later on a `decision` record. They never operate on the same record.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_experience_distill_integration.py -v -k "finalize_gate"`
Expected: all three new tests PASS.

- [ ] **Step 5: Run the existing distill suites — guard against regressions**

Run: `pytest tests/test_experience_distill_routing.py tests/test_experience_distill_schema.py tests/test_experience_distill_config.py tests/test_experience_distill_cli.py tests/test_experience_distill_integration.py tests/test_experience_distill_skill_bundle.py -v`
Expected: all PASS, no regression on existing per-slice routing.

- [ ] **Step 6: Commit**

```bash
git add src/deepscientist/artifact/service.py tests/test_experience_distill_integration.py
git commit -m "feat(distill): wire finalize-gate overlay into record_artifact"
```

---

## Task 6: Add `list_distill_candidates` service method + MCP tool

**Files:**
- Modify: `src/deepscientist/artifact/service.py` — add service method
- Modify: `src/deepscientist/mcp/server.py` — register MCP tool
- Test: extend `tests/test_mcp_servers.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_mcp_servers.py`. First locate an existing artifact-tool test to match style:

```bash
grep -nE "def test_.*artifact|build_artifact_server|artifact\." tests/test_mcp_servers.py | head -10
```

Add tests modeled on whatever pattern is used. The tests should cover:

```python
def test_list_distill_candidates_returns_pending_only(...):
    # Quest with two completed main_experiments and one already-reviewed.
    # Expect: candidates list contains exactly the unreviewed run; reviewed_set has the other.

def test_list_distill_candidates_distill_off_returns_empty(...):
    # Quest with experience_distill: false.
    # Expect: empty candidates regardless of run state.

def test_list_distill_candidates_includes_summary_metadata(...):
    # Expect: each candidate dict carries artifact_id, run_kind, status, summary, branch, created_at.
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mcp_servers.py -v -k "list_distill_candidates"`
Expected: AttributeError on `list_distill_candidates`.

- [ ] **Step 3: Add service method**

Edit `src/deepscientist/artifact/service.py`. Add method on `ArtifactService` (near other list/get helpers around line 6932):

```python
    def list_distill_candidates(self, quest_root: Path) -> dict[str, Any]:
        """Return undistilled completed-run candidates for the active quest.

        Result shape:
          {
            "ok": True,
            "experience_distill_on": bool,
            "reviewed_run_ids": list[str],
            "candidates": [
              {artifact_id, run_kind, status, summary, branch, created_at, path},
              ...
            ],
          }
        """
        from .experience_distill import (
            DISTILL_CANDIDATE_RUN_KINDS,
            _read_distill_reviews,
            is_distill_on,
            iter_distill_candidate_records,
        )

        artifacts_dir = quest_root / "artifacts"
        if not is_distill_on(quest_root):
            return {
                "ok": True,
                "experience_distill_on": False,
                "reviewed_run_ids": [],
                "candidates": [],
            }
        reviews = _read_distill_reviews(artifacts_dir)
        reviewed_set: set[str] = set()
        for r in reviews:
            for rid in r.get("reviewed_run_ids") or []:
                reviewed_set.add(str(rid))
        candidates = []
        for record in iter_distill_candidate_records(artifacts_dir):
            aid = str(record.get("artifact_id") or "")
            if aid in reviewed_set:
                continue
            candidates.append(
                {
                    "artifact_id": aid,
                    "run_kind": str(record.get("run_kind") or ""),
                    "status": str(record.get("status") or ""),
                    "summary": str(record.get("summary") or "")[:400],
                    "branch": str(record.get("branch") or ""),
                    "created_at": str(record.get("created_at") or ""),
                    "path": str(record.get("path") or ""),
                }
            )
        return {
            "ok": True,
            "experience_distill_on": True,
            "reviewed_run_ids": sorted(reviewed_set),
            "candidates": candidates,
            "candidate_run_kinds": sorted(DISTILL_CANDIDATE_RUN_KINDS),
        }
```

- [ ] **Step 4: Register MCP tool**

Edit `src/deepscientist/mcp/server.py`. Locate a nearby read-only artifact tool (e.g., `get_analysis_campaign` near line 1340 has a clean shape). Add this tool inside `build_artifact_server`:

```python
    @server.tool(
        name="list_distill_candidates",
        description=(
            "List completed-run records (analysis.slice / main_experiment / experiment) "
            "that have not yet been distilled. Use this at the start of the `distill` skill "
            "to enumerate the batch."
        ),
        annotations=_read_only_tool_annotations(title="List distill candidates"),
    )
    def list_distill_candidates(
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.list_distill_candidates(context.require_quest_root())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_mcp_servers.py -v -k "list_distill_candidates"`
Expected: all three PASS.

- [ ] **Step 6: Commit**

```bash
git add src/deepscientist/artifact/service.py src/deepscientist/mcp/server.py tests/test_mcp_servers.py
git commit -m "feat(distill): expose list_distill_candidates as MCP tool"
```

---

## Task 7: Rewrite distill SKILL.md to per-batch flow

**Files:**
- Modify: `src/skills/distill/SKILL.md`
- Test: `tests/test_experience_distill_skill_bundle.py` if it asserts SKILL.md content

- [ ] **Step 1: Audit existing skill-bundle test for content assertions**

Run:
```bash
grep -nE "SKILL\.md|distill skill|reviewed_run_ids|distill_review" tests/test_experience_distill_skill_bundle.py
```

If any assertion checks specific phrases ("after an analysis-slice"), note them — they will need updating.

- [ ] **Step 2: Rewrite SKILL.md**

Replace `src/skills/distill/SKILL.md` entirely with:

```markdown
---
name: distill
description: "Use when the finalize gate fires (or when an analysis-slice just landed). Inspect the batch of undistilled completed runs, then write 0..N reusable knowledge cards (`subtype: experience`) and one bookkeeping `distill_review` artifact."
skill_role: companion
---

# Distill

Run this skill when the distill gate routes you here — either immediately after an `analysis.slice` lands (per-slice trigger) or before write/finalize when the quest has undistilled completed runs (finalize gate).

Your job is **not** to write a lab notebook entry — it is to decide whether the batch produced reusable, mechanism-bearing intuition, persist it as global knowledge cards, and record one `distill_review` artifact summarizing what was inspected.

## Protocol

### 0. Pull the batch

```json
{"tool": "artifact.list_distill_candidates", "arguments": {}}
```

The tool returns:
- `experience_distill_on`: skip the skill if `false`
- `candidates`: undistilled run records (`artifact_id`, `run_kind`, `status`, `summary`, `branch`, `created_at`, `path`)
- `reviewed_run_ids`: already covered, do not redo

If `candidates` is empty, you should not have been routed here — record a minimal `distill_review` with `reviewed_run_ids=[]` is **not** valid (schema rejects it). Instead, exit the skill and record a `decision(action='continue')` noting that the gate was already clear.

### 1. For each candidate, decide one of three outcomes

For each `candidate`, look at the run record (`path`) and any related artifacts the run references.

**A. Patch an existing global card (default when a neighbor is found)**

Search for neighbors:

```json
{"tool": "memory.search", "arguments": {"query": "<keywords from candidate>", "scope": "global", "kind": "knowledge", "limit": 10}}
```

Read the top 3 matches. If any is in the same causal neighborhood as what this candidate observed, `memory.write_card` to patch:
- append one `lineage` entry `{quest, run, direction, note}`
- adjust `confidence` (monotone non-increasing across quests)
- narrow `conditions` if this candidate revealed a scoping limit
- `claim` is **immutable** when patching across quests; only same-quest patches may edit it

**B. Create a new global card (only when no neighbor exists)**

`memory.write_card` with `scope="global"`, `kind="knowledge"`, frontmatter:

```yaml
subtype: experience
claim: <one sentence, mechanism-bearing, falsifiable>
mechanism: <causal chain — why this plausibly holds>
conditions:
  - <scoping tag 1>
  - <scoping tag 2>
confidence: <0.0..1.0; 0.4 is a fine starting value>
lineage:
  - quest: <quest_id>
    run: <candidate.artifact_id or candidate.run_id>
    direction: <direction or goal id>
    note: <one-phrase takeaway>
```

Body: 3–8 lines of prose explaining the reasoning. No experiment-log dumps.

**C. No card from this candidate**

Acceptable when the run was a smoke test, the result was inconclusive, or it duplicated a prior card with no new condition. Just skip writing a card for this entry. The `distill_review` (Step 2) records *which* candidates were skipped via `reason_if_empty` (only required when the entire batch produces zero cards).

### 2. Hard constraints on new/patched cards

- `claim` must name a **mechanism**, not just an outcome. ("X improved accuracy" → reject; "X helps because it shortens the gradient path through Y" → accept.)
- `conditions` must name at least one scoping tag.
- `lineage[*]` must cite a real `quest` and `run`. Forge nothing.
- No numeric forecasts in the card body.

### 3. Record the batch summary

After processing all candidates, write exactly one `distill_review`:

```json
{
  "tool": "artifact.record",
  "arguments": {
    "kind": "distill_review",
    "reviewed_run_ids": ["<candidate.artifact_id>", "..."],
    "cards_written": [
      {"card_id": "knowledge-...", "scope": "global", "action": "new",   "target_run_id": "run-..."},
      {"card_id": "knowledge-...", "scope": "global", "action": "patch", "target_run_id": "run-..."}
    ],
    "reason_if_empty": "<required iff cards_written is empty>",
    "notes": "<optional free text>"
  }
}
```

`reviewed_run_ids` MUST list every candidate you actually inspected (not skipped). The cursor advances based on this list.

### 4. Resume the original route

After the `distill_review` lands, the finalize gate clears (the cursor advances past your reviewed runs). The agent's previous intent — `write` or `finalize` — is preserved in the guidance payload as `previous_recommended_skill`. Resume that route by recording a fresh `decision(action='write'|'finalize')` or proceeding to the corresponding skill directly.

## Output

End with one JSON line for downstream tooling:

```json
{"outcome": "patch_only" | "new_only" | "mixed" | "no_cards", "review_id": "distill-review-...", "card_ids": ["..."]}
```
```

- [ ] **Step 3: Re-run skill-bundle tests**

Run: `pytest tests/test_experience_distill_skill_bundle.py -v`
Expected: PASS. If any assertion broke on legacy phrasing, update it to match the new SKILL.md.

- [ ] **Step 4: Commit**

```bash
git add src/skills/distill/SKILL.md tests/test_experience_distill_skill_bundle.py
git commit -m "feat(distill): rewrite SKILL.md for per-batch flow + distill_review"
```

---

## Task 8: Extend retroactive CLI helper

**Files:**
- Modify: `src/deepscientist/cli.py:495-510` (the `iter_analysis_slice_records` call site)
- Modify: `src/deepscientist/artifact/experience_distill.py` (`emit_experience_drafts` may need to accept the wider candidate iterator)
- Test: `tests/test_experience_distill_cli.py`

- [ ] **Step 1: Read the current CLI shape**

Run:
```bash
sed -n '480,540p' src/deepscientist/cli.py
```

Identify the function that uses `iter_analysis_slice_records`. It is a CLI entry that emits "experience drafts" — one .md per candidate.

- [ ] **Step 2: Write the failing test**

Add to `tests/test_experience_distill_cli.py`:

```python
def test_cli_retroactive_uses_distill_candidate_kinds(tmp_path: Path):
    # Seed a quest with one main_experiment + one analysis.slice + one experiment.
    # Run the CLI emit (function-level, not subprocess).
    # Expect: drafts are produced for ALL THREE, not only analysis.slice.

def test_cli_retroactive_excludes_already_reviewed_runs(tmp_path: Path):
    # Same seed plus one distill_review covering the main_experiment.
    # Run the CLI emit.
    # Expect: drafts produced only for the two unreviewed candidates.
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_experience_distill_cli.py -v -k "retroactive"`
Expected: tests fail because retroactive only sees `analysis.slice`.

- [ ] **Step 4: Update CLI to use `iter_distill_candidate_records` and skip reviewed**

Edit the function in `src/deepscientist/cli.py` (around lines 495-510). Replace the `iter_analysis_slice_records(artifacts_dir)` call with:

```python
from .artifact.experience_distill import (
    _read_distill_reviews,
    iter_distill_candidate_records,
)

reviews = _read_distill_reviews(artifacts_dir)
reviewed_set: set[str] = set()
for r in reviews:
    for rid in r.get("reviewed_run_ids") or []:
        reviewed_set.add(str(rid))
records = [
    r for r in iter_distill_candidate_records(artifacts_dir)
    if str(r.get("artifact_id") or "") not in reviewed_set
]
```

If `_read_distill_reviews` is private (prefixed `_`), promote it to a public helper in this same task — rename to `read_distill_reviews` everywhere it is used (gate, service, CLI). Run a grep first:

```bash
grep -rn "_read_distill_reviews" src/ tests/
```

If the rename touches more than ~3 files, do it as part of this task — keep it one logical change.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_experience_distill_cli.py -v`
Expected: all PASS, including the two new ones.

- [ ] **Step 6: Commit**

```bash
git add src/deepscientist/cli.py src/deepscientist/artifact/experience_distill.py tests/test_experience_distill_cli.py
git commit -m "feat(distill): align retroactive CLI with finalize-gate scope"
```

---

## Task 9: End-to-end integration test

**Files:**
- Test: extend `tests/test_experience_distill_integration.py`

- [ ] **Step 1: Write the integration test**

Add a single test that walks the full lifecycle. Use the fixture pattern from existing tests in this file.

```python
def test_full_finalize_gate_lifecycle(tmp_path: Path, ...):
    # 1. Create a quest with experience_distill: on, baseline confirmed.
    # 2. Record a completed main_experiment run.
    # 3. Record decision(action='write')
    #    -> Expect guidance.recommended_skill == 'distill'
    #    -> Expect guidance.gate == 'finalize'
    #    -> Expect guidance.pending_distill_count == 1
    # 4. Call list_distill_candidates via service
    #    -> Expect one candidate matching the run's artifact_id.
    # 5. Record a distill_review covering the run, with cards_written=[] and reason_if_empty.
    # 6. Re-record decision(action='write')
    #    -> Expect guidance.recommended_skill == 'write' (gate cleared).
    # 7. Call list_distill_candidates again
    #    -> Expect zero candidates, reviewed_run_ids contains the run.
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_experience_distill_integration.py -v -k "full_finalize_gate_lifecycle"`
Expected: PASS.

- [ ] **Step 3: Run the full test suite — final regression sweep**

Run: `pytest`
Expected: all PASS. If any unrelated test breaks because the new artifact kind appears in fixtures or counts, update those tests to include `distill_review` in their expected sets.

- [ ] **Step 4: Commit**

```bash
git add tests/test_experience_distill_integration.py
git commit -m "test(distill): add end-to-end finalize-gate lifecycle"
```

---

## Self-Review (post-plan checklist)

Done as part of plan authoring:

1. **Spec coverage** — every spec section is covered:
   - § 1 gate evaluation → Tasks 3, 4, 5
   - § 2 distill_review schema → Task 1
   - § 3 distill skill rewrite → Task 7
   - § 4 list helper (revised: dedicated `list_distill_candidates` MCP tool instead of generic `list_runs` filter — see plan deviation note in Task 6 prologue) → Task 6
   - § 5 edge cases → Tasks 4 + 9
   - § 6 retroactive CLI → Task 8
   - § 7 test coverage → Tasks 1, 4, 6, 9

2. **Placeholder scan** — no TBDs; one Task 8 step asks the engineer to grep before deciding scope of a refactor (this is concrete enough — the grep tells them what to do).

3. **Type consistency** — `evaluate_distill_gate` returns the same dict in both gate code (Task 3) and overlay code (Task 4) and integration tests (Task 9). `distill_review` field names (`reviewed_run_ids`, `cards_written`, `reason_if_empty`) are identical across schema (Task 1), gate (Task 3), overlay (Task 4), service (Task 6), and skill (Task 7).

4. **Spec → plan deviations**:
   - **Hook location** (spec § 1): moved from `guidance.py` to `experience_distill.py` overlay + `service.py` wire-in (cleaner — preserves `build_guidance_for_record` purity).
   - **MCP filter shape** (spec § 4): replaced "extend `artifact.list_runs` with three filter params" with a new dedicated `artifact.list_distill_candidates` tool. Reason: `list_runs` does not exist in the current MCP surface; adding one would inflate scope; a purpose-built tool returns the diffed result without round-tripping the reviewed-set through the agent.

Both deviations are net simplifications — call them out in PR description, not the spec.
