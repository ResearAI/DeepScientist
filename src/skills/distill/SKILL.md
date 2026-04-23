---
name: distill
description: "Use right after an analysis-slice run lands to extract reusable causal intuition into a `knowledge` memory card (`subtype: experience`). Default to patching an existing entry; create a new one only when no similar claim exists; write a null+reason episode when nothing is worth distilling."
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
