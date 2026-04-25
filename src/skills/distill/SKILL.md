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
- `candidates`: undistilled run records (`artifact_id`, `run_id`, `run_kind`, `status`, `summary`, `branch`, `created_at`, `path`)
- `reviewed_run_ids`: already covered, do not redo
- `cursor_run_created_at`: timestamp of the last `distill_review`

If `candidates` is empty, you should not have been routed here — record a minimal `distill_review` with `reviewed_run_ids=[]` is **not** valid (schema rejects it). Instead, exit the skill and record a `decision(action='continue')` noting that the gate was already clear.

### 1. For each candidate, decide one of three outcomes

For each `candidate`, look at the run record (`path`) and any related artifacts the run references.

**A. Patch an existing global card (default when a neighbor is found)**

**Search for neighbors via the keyword summary index.**

```json
{"tool": "memory.list_knowledge_summaries", "arguments": {"scope": "global"}}
```

The tool returns one row per global knowledge card with
`card_id / title / claim / keywords / tags / subtype / updated_at`. Scan
the rows for any card whose `task:` tag, `claim`, or `keywords` overlap
the candidate run you are processing.

For each row that looks like a plausible neighbor, fetch the full card:

```json
{"tool": "memory.read_card", "arguments": {"card_id": "knowledge-..."}}
```

For each inspection, decide one of:

- **patch** — the existing card and the candidate run share a causal
  mechanism. Append a `lineage` entry, possibly downgrade `confidence`,
  narrow `conditions`, and append (do not delete) `keywords`. The
  `claim` text is immutable across quests.
- **new** — no existing card covers the candidate's mechanism; write a
  fresh card with `memory.write_card`.
- **neighbor_but_separate** — a related card exists but the candidate's
  mechanism is genuinely different. Note the relationship in `notes`
  and write a new card anyway.

Record one `neighbor_decisions` entry per inspected neighbor in the
final `distill_review` (see step 3) — including the negative cases
(`new`, `neighbor_but_separate`).

If the decision is **patch**, `memory.write_card` to patch:
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
keywords:
  - <kw 1>            # 3..8 short noun phrases or compound tokens; lowercased
  - <kw 2>
confidence: <0.0..1.0; 0.4 is a fine starting value>
tags:
  - task:<short-id>   # required
  - stage:<stage>     # optional
  - domain:<domain>   # optional
  - method:<method>   # optional
lineage:
  - quest: <quest_id>
    run: <candidate.run_id or candidate.artifact_id>
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
- Every new or patched card must include a `task:<short-id>` tag in
  the top-level `tags:` list. The `<short-id>` is a stable
  low-cardinality slug for the task family the experience belongs to
  (e.g. `task:snake-10x10`, `task:cifar10-classification`,
  `task:gsm8k`). Reuse existing slugs when patching; coin a new slug
  only when no neighbor card uses one.
- Every new card must include a top-level `keywords` list of 3–8 short
  noun phrases (lowercased, hyphenated). Cross-quest patches may
  *append* keywords but must not delete existing ones; same-quest
  patches may freely edit.

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
    "notes": "<optional free text>",
    "neighbor_decisions": [
      {"candidate_card_id": "knowledge-...", "decision": "patch",  "reason": "same mechanism", "target_run_id": "run-..."},
      {"candidate_card_id": "knowledge-...", "decision": "neighbor_but_separate", "reason": "different conditions", "target_run_id": "run-..."}
    ]
  }
}
```

> `neighbor_decisions` is optional but strongly recommended: record one
> entry per neighbor card you inspected, including the negative cases
> (where the decision was `new` or `neighbor_but_separate`). This makes
> the review log show what you considered, not just what you wrote.

`reviewed_run_ids` MUST list every candidate you actually inspected (not skipped). The cursor advances based on this list.

### 4. Resume the original route

After the `distill_review` lands, the finalize gate clears (the cursor advances past your reviewed runs). The agent's previous intent — `write` or `finalize` — is preserved in the guidance payload as `previous_recommended_skill`. Resume that route by recording a fresh `decision(action='write'|'finalize')` or proceeding to the corresponding skill directly.

## Output

End with one JSON line for downstream tooling:

```json
{"outcome": "patch_only" | "new_only" | "mixed" | "no_cards", "review_id": "distill-review-...", "card_ids": ["..."]}
```
