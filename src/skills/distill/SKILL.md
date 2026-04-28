---
name: distill
description: "Use when the finalize gate fires. Inspect the batch of undistilled completed runs, then write 0..N reusable knowledge cards and one bookkeeping `decision(action='distill_review')` artifact."
skill_role: companion
---

# Distill

Run this skill when the finalize gate routes you here — before write/finalize when the quest has undistilled completed runs.

Your job is **not** to write a lab notebook entry — it is to decide whether the batch produced reusable, mechanism-bearing intuition, persist it as global knowledge cards, and record one `decision(action='distill_review')` artifact summarizing what was inspected.

## Protocol

### 0. Pull the batch

```json
{"tool": "artifact.list_distill_candidates", "arguments": {}}
```

Returns `experience_distill_on` (skip if false), `candidates` (undistilled run records), `reviewed_run_ids` (already covered), and `cursor_run_created_at`.

If `candidates` is empty you should not have been routed here — exit and record a `decision(action='continue')` instead.

### 1. For each candidate, decide one of three outcomes

Look at the run record (`path`) and any artifacts it references. Search for neighbor cards via the keyword summary index:

```json
{"tool": "memory.list_knowledge_summaries", "arguments": {"scope": "global"}}
```

Each row carries `card_id / title / claim / keywords / tags / subtype / updated_at`. Scan for cards whose `task:` tag, `claim`, or `keywords` overlap the candidate; fetch full bodies via `memory.read` for plausible neighbors. Then decide one of:

- **patch** — existing card and candidate share a causal mechanism. Append a `lineage` entry; `claim` is immutable across quests (same-quest patches may edit it).
- **new** — no existing card covers the mechanism; write a fresh card with `memory.write`.
- **neighbor_but_separate** — a related card exists but the mechanism is genuinely different. Note the relationship in the body and write a new card anyway.

Record one `neighbor_decisions` entry per inspected neighbor in the final `decision(action='distill_review')` — including the negative cases.

For **new** cards, `memory.write` with `scope="global"`, `kind="knowledge"`. Only two frontmatter fields are validated: `claim` (non-empty) and `lineage` (non-empty list, each entry has at least `quest` + `run`). Other fields are conventional, not enforced:

```yaml
claim: <one sentence, mechanism-bearing, falsifiable>     # required
lineage:                                                   # required, non-empty
  - quest: <quest_id>
    run: <candidate.run_id or candidate.artifact_id>
    direction: <direction or goal id>
    note: <one-phrase takeaway>
# optional, conventional — not validated:
keywords: [...]
tags: [task:<short-id>, stage:<stage>, ...]
```

Body: 3–8 lines of prose explaining the reasoning. No experiment-log dumps.

Skipping a candidate (no card written) is acceptable for smoke tests, inconclusive runs, or duplicates of prior cards. `reason_if_empty` in the review artifact is only required when the entire batch produces zero cards.

### 2. Cross-quest patch invariants

- `claim` must name a **mechanism**, not just an outcome.
- `lineage[*]` must cite a real `quest` and `run`. Forge nothing.
- No numeric forecasts in the card body.
- Cross-quest patches may *append* optional fields (`keywords`, `tags`) but must not delete them; same-quest patches may freely edit.

### 3. Record the batch summary

After processing all candidates, write exactly one `decision(action='distill_review')`:

```json
{
  "tool": "artifact.record",
  "arguments": {
    "kind": "decision",
    "action": "distill_review",
    "verdict": "covered",
    "reason": "<one-line summary of the batch outcome>",
    "reviewed_run_ids": ["<candidate.artifact_id>", "..."],
    "cards_written": [
      {"card_id": "knowledge-...", "scope": "global", "action": "new",   "target_run_id": "run-..."},
      {"card_id": "knowledge-...", "scope": "global", "action": "patch", "target_run_id": "run-..."}
    ],
    "reason_if_empty": "<required iff cards_written is empty>",
    "notes": "<optional free text>",
    "neighbor_decisions": [
      {"candidate_card_id": "knowledge-...", "decision": "patch", "reason": "same mechanism", "target_run_id": "run-..."},
      {"candidate_card_id": "knowledge-...", "decision": "neighbor_but_separate", "reason": "different conditions", "target_run_id": "run-..."}
    ]
  }
}
```

`kind`, `action`, `verdict`, and `reason` are the standard `decision` fields. The rest (`reviewed_run_ids`, `cards_written`, `reason_if_empty`, `neighbor_decisions`) are review-specific and only validated when `action == 'distill_review'`.

`reviewed_run_ids` MUST list every candidate you actually inspected (not skipped). The cursor advances based on this list.

### 4. Resume the original route

After the `decision(action='distill_review')` lands, the finalize gate clears. The agent's previous intent — `write` or `finalize` — is preserved in the guidance payload as `previous_recommended_skill`. Resume that route by recording a fresh `decision(action='write'|'finalize')` or proceeding to the corresponding skill directly.

## Output

End with one JSON line for downstream tooling:

```json
{"outcome": "patch_only" | "new_only" | "mixed" | "no_cards", "review_id": "decision-...", "card_ids": ["..."]}
```
