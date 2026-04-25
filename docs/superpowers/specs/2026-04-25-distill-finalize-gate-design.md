---
title: Distill finalize gate (Phase 2)
date: 2026-04-25
status: draft-for-review
related: docs/superpowers/plans/2026-04-23-feat_experience_distill.md
---

# Distill Finalize Gate — Design Spec

## Background

Phase 1 of `experience_distill` shipped with a single trigger:
`maybe_inject_distill_routing` injects the `distill` companion skill only when a
completed `analysis.slice` run is recorded (see
`src/deepscientist/artifact/experience_distill.py:166` and the call site at
`src/deepscientist/artifact/service.py:7416`).

Empirical check on quest 009 (`/home/ds/DeepScientist/quests/009`) shows this
trigger is too narrow:

- `experience_distill: true` was correctly persisted in
  `quest.yaml` → `startup_contract.experience_distill`.
- The `deepscientist-distill` skill was correctly synced into all four runner
  surfaces (codex / claude / opencode / kimi).
- But the agent's path was: `idea → 2 main_experiment → 3 ablation experiment →
  decision(action=write) → paper PDF`. Zero `analysis.slice` runs were ever
  created (the `decision-9d1f624e.json` reasoned that evidence was already
  sufficient and chose `write` over `launch_analysis_campaign`).
- Result: the distill skill was never invoked. Both global memory
  (`~/DeepScientist/memory/knowledge/`) and quest memory
  (`memory/knowledge/`, `memory/ideas/`, etc.) ended the quest empty of
  any distilled experience cards.

The structural problem is that distill is gated on the agent voluntarily
opening an analysis campaign (an expensive route the agent often skips when
the main result already justifies writing). Per-record routing on the rare
`analysis.slice` event is the wrong contract for "make sure something is
distilled before writing".

## Goal

Add a second trigger — the **finalize gate** — that runs whenever the agent
records a `decision(action='write' | 'finalize')`. The gate scans completed
runs that have not yet been distilled, and routes the agent to the `distill`
skill before allowing write/finalize to proceed. State is derived from a
new `distill_review` artifact stream so that the gate is idempotent and
auditable.

## Non-goals

- Do not change the workflow graph (no new stage anchor for distill).
- Do not modify `finalize` or `write` SKILL.md content.
- Do not change `coerce_distill_mode` / `is_distill_on` /
  `read_distill_mode` contracts.
- Do not retroactively re-trigger on historical decisions (gate evaluates
  fresh `decision` records only).
- No UI work; the new artifact appears in existing artifact lists naturally.

## Design

### § 1. Gate evaluation

**Hook location**: `src/deepscientist/artifact/guidance.py`, the `decision`
handling branch.

**New helper** (`src/deepscientist/artifact/experience_distill.py`):
```
def evaluate_distill_gate(
    quest_root: Path,
    artifacts_dir: Path,
) -> dict[str, Any] | None:
    """Return a gate dict if the agent should be routed to distill,
    else None.

    Output dict shape (when non-empty):
      {
        "pending_distill_count": int,        # total candidates past cursor
        "pending_distill_ids": list[str],    # first 5 artifact_ids
        "cursor_run_created_at": str | None, # ISO timestamp or None
      }
    """
```

Algorithm:
1. If `is_distill_on(quest_root)` is `False`, return `None`.
2. Read all `distill_review` artifacts from `artifacts/_index.jsonl`.
3. Build `reviewed_set = union(r.reviewed_run_ids for r in reviews)`.
   Empty set if no review yet.
4. Enumerate `kind="run"` records with `run_kind ∈ {analysis.slice,
   main_experiment, experiment}` and `status ∈ {completed, success,
   succeeded, done}`. Compute
   `candidates = [run for run in runs if run.artifact_id not in reviewed_set]`.
5. If `candidates == []`, return `None` (gate clear).
6. Otherwise return the dict above. `cursor_run_created_at` is the
   `max(r.created_at for r in reviews)` (or `None`) — surfaced only as
   a hint for the skill's MCP query window; correctness uses
   set-difference, not the timestamp.

**Wire-in**: in `guidance.py`, the `decision` branch where `action ∈
{write, finalize}`, call `evaluate_distill_gate`. If non-`None`, override
the guidance:
- `recommended_skill = "distill"`
- `recommended_action = "Review undistilled completed runs before writing"`
- merge gate dict fields into the returned guidance (`pending_distill_count`,
  `pending_distill_ids`, `experience_distill: True`, `gate: "finalize"`)
- `alternative_routes` retains the original write/finalize target so the
  agent (and downstream UI) can still see what the eventual next step is

**Idempotence**: after the agent runs distill and records a `distill_review`
covering the candidates, the cursor advances and re-evaluating the same
`decision(write)` record yields a clear gate. No state is mutated by the
gate itself; it is a pure derivation over the artifact stream.

**Coexistence with `maybe_inject_distill_routing`**: the existing per-slice
trigger remains. If the agent distills an `analysis.slice` immediately when
it lands, the resulting `distill_review` covers that slice, and the
finalize gate naturally noops for that record at decision time.

### § 2. New artifact kind: `distill_review`

**Schema** (added to `src/deepscientist/artifact/schemas.py`):
```yaml
kind: distill_review
schema_version: 1
artifact_id: distill-review-<uuid>
quest_id: <id>
created_at: <ISO timestamp>
source:
  kind: agent
  role: pi | ...
  run_id: <distill skill run id>
reviewed_run_ids:        # required, non-empty
  - run-<id>
  - run-<id>
cards_written:           # required, may be empty
  - card_id: knowledge-<id>
    scope: global | quest
    action: new | patch
    target_run_id: run-<id>   # which candidate produced this card
reason_if_empty: <str>   # required iff cards_written == []
notes: <str>             # optional, free text
```

**Validation rules**:
- `reviewed_run_ids` must be non-empty.
- Each `reviewed_run_ids[*]` must reference an artifact_id that exists in
  `_index.jsonl` with `kind="run"` (validated at record time).
- If `cards_written == []`, `reason_if_empty` must be non-empty.
- Each `cards_written[*].target_run_id` must be in `reviewed_run_ids`.

**Storage**: `quests/<id>/artifacts/distill_reviews/distill-review-<id>.json`,
indexed in `_index.jsonl` like other artifact kinds.

**Write channel**: existing `artifact.record(kind="distill_review", ...)` MCP
tool — no new MCP namespace.

### § 3. Distill skill rewrite

`src/skills/distill/SKILL.md` is currently per-slice ("Run this skill after
an analysis-slice completes"). It is reframed to per-batch:

**Changes**:
1. **Framing**: "Run this skill when the distill gate fires; you have a
   batch of completed runs to inspect."
2. **New step 0 — Pull candidates**:
   ```
   artifact.list_runs(filter={
     kind_in: ["analysis.slice", "main_experiment", "experiment"],
     since_created_at: <cursor from guidance>,
     status_terminal: true,
   })
   ```
   The cursor value comes either from the guidance payload or from the
   skill's own `distill_review` history scan.
3. **Existing steps 1–3** (search neighbors / patch-or-new-or-null
   decision / hard constraints) apply per candidate, iterated.
4. **End-of-skill output replaces the old "null+reason episode"**:
   record exactly one `distill_review` artifact summarizing this batch.
   The patch/new knowledge cards continue to be written via
   `memory.write_card` as before; `distill_review` is the batch
   bookkeeping that advances the cursor.
5. **Remove**: the existing "C. Null + reason → quest-scoped episode"
   path. All "no card written" outcomes go through
   `distill_review.reason_if_empty` instead.

### § 4. `artifact.list_runs` filter extensions

Add to `src/deepscientist/mcp/server.py` and `artifact/service.py`:

| Param | Type | Semantics |
|---|---|---|
| `kind_in` | `list[str]` | Whitelist of `run_kind` values |
| `since_created_at` | `str` (ISO) | Return only records with `created_at > value`. Time-window optimization for large quests; correctness still relies on the skill diffing against `reviewed_set` returned via `list_distill_reviews` (or by reading the artifact stream). |
| `status_terminal` | `bool` | When `True`, restrict to status ∈ {completed, success, succeeded, done} |

Existing filters and pagination stay unchanged. New filters are additive
and default to "no filter" if absent.

The skill's typical query is:
```
artifact.list_runs(filter={
  kind_in: ["analysis.slice", "main_experiment", "experiment"],
  since_created_at: <cursor_run_created_at from guidance>,  # optimization
  status_terminal: true,
})
```
Then locally drop any candidate whose `artifact_id ∈ reviewed_set` (the
gate-side definition of truth).

### § 5. Edge cases

- **`experience_distill: false`** → gate short-circuits at step 1, no
  scanning, no payload.
- **Empty candidate list** → gate returns `None`, original write/finalize
  guidance stands.
- **Multiple `decision(write)` records over a quest's lifetime** → cursor
  derivation is monotonic; once a `distill_review` covers the latest run,
  subsequent decisions clear the gate naturally. No marker needed.
- **Agent records `distill_review` with stale `reviewed_run_ids`** → cursor
  may not advance past newer runs; the gate fires again with the
  remaining candidates. Acceptable — the audit shows the agent reviewed
  the older subset, and the new candidates remain pending.
- **Quest 009-style historical quests** → the gate evaluates only
  newly-recorded `decision` artifacts; existing decision records are not
  re-scored. Manual catch-up is via the retroactive CLI (see § 7).

### § 6. Retroactive CLI alignment

`src/deepscientist/cli.py:495` (`emit_experience_drafts` /
`iter_analysis_slice_records`) currently filters to `analysis.slice`
only. To keep the manual batch path consistent with the gate's scan:

- Extend `iter_analysis_slice_records` (rename or add a sibling
  `iter_distill_candidate_records`) to accept the same `run_kind`
  whitelist as the gate.
- The CLI should also respect existing `distill_review` artifacts when
  computing what is still pending.

This is in-scope for the implementation plan but kept as a focused change
behind the same helper.

### § 7. Test coverage

Spec listed; the implementation plan will expand into individual cases.

- `tests/test_artifact_guidance.py`:
  - `decision(action='write')` with non-empty pending candidates → guidance
    swaps to `recommended_skill='distill'` and includes
    `pending_distill_count` / `pending_distill_ids`
  - same decision with cursor already covering all runs → guidance keeps
    its original `write` recommendation
  - same decision with `experience_distill: false` → no gate, original
    guidance unchanged
- `tests/test_artifact_schemas.py`:
  - `distill_review` accepts valid payload
  - rejects empty `reviewed_run_ids`
  - rejects `cards_written=[]` without `reason_if_empty`
  - rejects `cards_written[*].target_run_id` not in `reviewed_run_ids`
- `tests/test_mcp_servers.py`:
  - `artifact.list_runs(kind_in=...)` filters correctly
  - `since_created_at` filter is strict-greater-than
  - `status_terminal=True` includes all four terminal statuses
- End-to-end fixture (in
  `tests/test_artifact_service.py` or a new file):
  - simulate quest with one completed `main_experiment`
  - record `decision(action='write')` → assert guidance recommends distill
  - record `distill_review` covering the run, with empty `cards_written`
    and `reason_if_empty="smoke test only"`
  - re-record (or re-evaluate guidance for) `decision(action='write')` →
    assert guidance recommends `write`

## Out of scope

- Workflow-graph changes (no new stage anchor for distill).
- `finalize` / `write` SKILL.md changes.
- UI-side work for the new artifact (lists are generic and pick it up
  automatically).
- Promoting distill to a hard gate that can block a quest (gate is
  recommendation-strength, not enforcement).
