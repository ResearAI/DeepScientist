---
title: Phase 4 — Distill finalize gate coverage
date: 2026-04-26
status: draft
---

# Background

Quest 011 validation (run-7990a619) showed the Phase 3 finalize gate has a real coverage hole. The gate at [`maybe_inject_distill_finalize_gate`](../../src/deepscientist/artifact/experience_distill.py) only fires when the agent records `decision(action ∈ {'write','finalize'})`. Real finalize paths bypass it entirely:

- `submit_paper_bundle` records a `report` kind, not a `decision`. Gate is silent.
- `complete_quest` is a separate MCP tool that does not flow through `record(kind='decision')`. Gate is silent.

Net effect: an agent with `experience_distill: on` and pending un-reviewed runs can ship a paper and complete the quest without ever invoking the distill skill.

# Goal

Make the gate visible *before* the agent acts (advisory cue) and binding *at* the closure entry points (hard guards), so the runtime cannot bypass distill on the actual closure paths regardless of which artifact route the agent picks.

# Non-goals

- Do not extend the gate to every artifact kind — only the two known finalize entry points (`submit_paper_bundle`, `complete_quest`).
- Do not change `evaluate_distill_gate` semantics. Reuse it as-is.
- Do not add a per-quest override flag. Hard means hard. (User can still flip `experience_distill: off` in `quest.yaml` to disable.)

# Design

## B — `distill_required_rule` prompt cue

Mirror the existing `recall_priors_rule` injection in [`prompts/builder.py::_priority_memory_block`](../../src/deepscientist/prompts/builder.py).

Trigger: `is_distill_on(quest_root) AND evaluate_distill_gate(quest_root, artifacts_dir) is not None AND skill_id ∈ STANDARD_SKILLS`.

Cue text (one line, parallel to recall_priors_rule):
```
- distill_required_rule: there are N completed run(s) without a distill_review (ids: a, b, ...).
  Before calling `submit_paper_bundle` or `complete_quest`, run the distill skill and
  `artifact.record(kind='distill_review', ...)` covering the pending runs. The closure
  gate will hard-reject those tools until the review lands.
```

Pending count + ids come from `evaluate_distill_gate` return value (already capped at 5 ids).

## C-1 — `submit_paper_bundle` hard guard

Insert at the top of [`ArtifactService.submit_paper_bundle`](../../src/deepscientist/artifact/service.py) (before any other gate / state work).

```python
gate_payload = evaluate_distill_gate(quest_root, write_root / "artifacts")
# write_root resolved earlier — actually we need to resolve it first; see plan
if gate_payload is not None:
    raise ValueError(
        f"submit_paper_bundle blocked: experience_distill is on and {gate_payload['pending_distill_count']} "
        f"completed run(s) lack a distill_review (pending: {', '.join(gate_payload['pending_distill_ids'])}). "
        "Run the distill skill and record an artifact.record(kind='distill_review', ...) before resubmitting."
    )
```

Failure surface: `ValueError` propagates to MCP layer which already wraps service errors into `{ok: false, errors: [...]}` — same shape as the existing `submit_paper_bundle blocked because the paper evidence contract is incomplete` rejection.

## C-2 — `complete_quest` hard guard

Insert in [`ArtifactService.complete_quest`](../../src/deepscientist/artifact/service.py) right after the `already_completed` short-circuit and before the approval-request lookup.

```python
gate_payload = evaluate_distill_gate(quest_root, write_root / "artifacts")
if gate_payload is not None:
    return {
        "ok": False,
        "status": "distill_required",
        "quest_id": snapshot.get("quest_id"),
        "pending_distill_count": gate_payload["pending_distill_count"],
        "pending_distill_ids": gate_payload["pending_distill_ids"],
        "message": (
            "Quest completion blocked: experience_distill is on and "
            f"{gate_payload['pending_distill_count']} completed run(s) lack a distill_review. "
            "Run the distill skill and artifact.record(kind='distill_review', ...) covering the pending runs."
        ),
    }
```

Returns dict with `ok: false` (matching existing patterns like `approval_required`, `waiting_for_user`, `approval_not_explicit`) — does NOT raise. The `complete_quest` service intentionally returns soft errors instead of raising, and we follow that convention.

`write_root`: resolve via `self._workspace_root_for(quest_root)` (already used inside the function or computable at the top).

# Test coverage

## `tests/test_prompt_builder.py`
- `test_priority_memory_block_includes_distill_required_when_pending`: distill on + completed run without review → cue appears, names `submit_paper_bundle` and `complete_quest`, lists the pending id.
- `test_priority_memory_block_omits_distill_required_when_no_pending`: distill on but every run is reviewed → no cue.
- `test_priority_memory_block_omits_distill_required_when_distill_off`: distill off + completed run → no cue (regardless of state).

## `tests/test_experience_distill_finalize_gate.py` (or new sibling file if cleaner)
- `test_submit_paper_bundle_rejects_when_pending_distill`: distill on + completed run, agent calls `submit_paper_bundle` → raises ValueError mentioning pending count + ids.
- `test_submit_paper_bundle_passes_when_distill_clear`: distill on + reviewed run → original logic runs (still hits some other rejection later but does not hit our new one).
- `test_submit_paper_bundle_passes_when_distill_off`: distill off → never checked.
- `test_complete_quest_returns_distill_required_when_pending`: distill on + completed run → returns `{ok: false, status: 'distill_required', ...}`.
- `test_complete_quest_passes_distill_when_clear`: distill on + reviewed → falls through to existing approval logic.
- `test_complete_quest_passes_distill_when_off`: distill off → falls through.
- `test_complete_quest_already_completed_skips_distill_check`: status=completed → returns `already_completed`, does not check distill.

# File-by-file changes

| File | Change |
|---|---|
| `src/deepscientist/prompts/builder.py` | Import `evaluate_distill_gate`; add cue branch in `_priority_memory_block` parallel to recall_priors_rule. |
| `src/deepscientist/artifact/service.py` | Insert hard guard at top of `submit_paper_bundle` (raise) and after `already_completed` in `complete_quest` (return dict). |
| `tests/test_prompt_builder.py` | 3 cue tests. |
| `tests/test_experience_distill_finalize_gate.py` | 7 hard-guard tests (or split into a new file if it grows the file too much). |

No schema changes. No UI changes. No new MCP tools.
