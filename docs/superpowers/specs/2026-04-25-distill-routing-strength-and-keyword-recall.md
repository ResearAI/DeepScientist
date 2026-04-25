---
title: Distill routing strength + task tag + recall priors + keyword summaries (Phase 3)
date: 2026-04-25
status: draft-for-review
related:
  - docs/superpowers/specs/2026-04-25-distill-finalize-gate-design.md
  - docs/superpowers/plans/2026-04-23-feat_experience_distill.md
---

# Distill Phase 3 — Design Spec

## Background

Quest 010 (`/home/ds/DeepScientist/quests/010`, Snake DQN) was the first quest
to ship under the finalize gate (Phase 2). The gate fired correctly and the
agent eventually wrote two reusable knowledge cards
(`potential-based-reward-shaping-...md`, `symbolic-features-enable-...md`).
But the run also exposed four gaps that the current implementation does not
cover:

1. **Routing strength is too weak.** The decision log shows the agent
   reasoning twice that distill was "optional" or "could be skipped"
   before reluctantly running it. The finalize gate currently still
   surfaces the original write/finalize as an `alternative_routes` entry
   ([experience_distill.py:488-495](src/deepscientist/artifact/experience_distill.py#L488-L495)),
   and the `recommended_action` text is descriptive ("Review undistilled
   completed runs ... before resuming write/finalize") rather than
   imperative. Together they read as advisory, not gating.

2. **Knowledge cards have no `task:` tag.** Cards from quest 010 carry
   `domain:rl` / `method:dqn` style tags but no field that lets a future
   Snake or grid-game quest pull them by task. The two existing global
   cards under `~/DeepScientist/memory/knowledge/` have
   `tags: [stage:experiment, domain:rl, ...]` — searching for "snake"
   yields nothing useful via `memory.search` (which is pure substring;
   see § P2 below).

3. **Consumer side has no recall step.** Distill (the *writer*) has a
   trigger and a gate, but `scout` / `idea` / `baseline` (the *readers*)
   never get told to look at global knowledge before generating a fresh
   idea. The result is that the cards quest 010 produced cannot
   influence quest 011 unless the user manually drops a hint.

4. **Neighbor selection is keyword-search guesswork.** The current
   distill skill ([SKILL.md:39](src/skills/distill/SKILL.md#L39)) calls
   `memory.search` with "keywords from candidate" text. `memory.search`
   is implemented as **pure substring matching**
   ([memory/service.py:311-336](src/deepscientist/memory/service.py#L311-L336))
   — `query_lower in content`. Long natural-language queries will
   silently miss every card; short single-word queries return broad
   matches with no ranking. The agent has no reliable way to decide
   "does this batch already have a neighbor card I should patch?".

## Goal

A single batch of changes that addresses all four gaps:

- **A. Routing strength.** Drop the `alternative_routes` fallback the
  finalize gate currently appends and tighten the action text so the
  agent reads distill as the only acceptable next step until a
  `distill_review` lands.
- **D. Task tag convention.** Document a `task:<short-id>` tag in the
  distill skill frontmatter contract and backfill the two existing
  quest 010 cards.
- **P1. Recall priors.** Add a new `startup_contract.recall_priors`
  field (parallel to `experience_distill`), surface it in the project
  wizard, and have the prompt builder inject a one-line cue that tells
  stage skills to call `memory.list_knowledge_summaries` before
  starting work.
- **P2. Keyword summaries (N1–N4).** Add a top-level `keywords` field
  to the experience-card frontmatter; expose
  `memory.list_knowledge_summaries` returning compact rows
  (id / title / claim / keywords / tags); rewrite distill skill
  step 1 to be "list summaries → scan → pick neighbor candidates →
  `memory.read_card` for full text → patch / new"; and add an
  optional `neighbor_decisions` array to the `distill_review` schema
  for auditability.

## Non-goals

- No new public MCP namespace; everything lives under existing
  `memory` / `artifact` / `bash_exec`.
- No change to `memory.search` algorithm — keep it as substring; the
  new flow goes through `list_knowledge_summaries` instead.
- No embedding / BM25 / TF-IDF infrastructure; neighbor judgment is
  done by the LLM scanning the summary list.
- No retroactive recompute of historical guidance; the finalize gate
  only evaluates fresh `decision` records as before.
- No change to the workflow graph; `recall_priors` is a prompt cue,
  not a stage anchor.
- No change to `coerce_distill_mode` / `is_distill_on` /
  `read_distill_mode` contracts (Phase 2's contract stays).

## Design

### § A. Routing strength (drop fallback, sharpen wording)

**File**: [src/deepscientist/artifact/experience_distill.py](src/deepscientist/artifact/experience_distill.py)

**Current behaviour** ([experience_distill.py:484-512](src/deepscientist/artifact/experience_distill.py#L484-L512)):
when the gate fires, the function builds an `alternative_routes` entry
that re-advertises the original `recommended_skill` (write/finalize)
with reason `_FINALIZE_GATE_FALLBACK_REASON`. The
`recommended_action` is the soft phrase
"Review undistilled completed runs ... before resuming write/finalize".

**Changes**:

1. **Drop the fallback append.** When the gate fires, `routes` should
   stay as whatever was already on the inbound `guidance_vm`; do not
   append the previous skill back as an alternative. Distill becomes
   the only `recommended_skill` and the only `alternative_routes` are
   pre-existing ones (typically empty at decision time).
2. **Sharpen `recommended_action`** to imperative, gate-explicit
   wording, e.g.:
   > `"Distill required before write/finalize: scan completed runs, write 0..N knowledge cards, record one distill_review. The original write/finalize route is paused until distill_review lands."`
3. **Keep `previous_recommended_skill` / `previous_recommended_action`
   in the payload** — these are how the *clear* branch
   ([experience_distill.py:464-482](src/deepscientist/artifact/experience_distill.py#L464-L482))
   restores the original route, and the distill SKILL.md step 4 still
   uses `previous_recommended_skill` to know what to resume.
4. **Clear branch cleanup.** With no fallback append, the clear branch
   no longer needs the `alternative_routes` filtering for
   `_FINALIZE_GATE_FALLBACK_REASON`. The constant
   `_FINALIZE_GATE_FALLBACK_REASON` and the filtering loop can be
   removed; the clear branch only needs to strip the
   `_FINALIZE_GATE_INJECTED_KEYS` and restore
   `recommended_skill` / `recommended_action` from the saved
   `previous_*` fields.

**Why not stricter (e.g. block the `decision` write entirely)?** The
gate is a guidance-layer redirect, not enforcement. Distill remains
recommendation-strength so the agent can still choose to record
another `decision(action='write')` if the human overrides. The change
here removes the *visible-alternative* that made the agent reason
"either path is fine" — it does not remove the agent's escape hatch.

### § D. `task:<short-id>` tag convention

**File**: [src/skills/distill/SKILL.md](src/skills/distill/SKILL.md)

**Change**: in the "Hard constraints" section (currently § 2 of the
skill), add:

> **Required tag namespace.** Every new or patched card must include a
> `task:<short-id>` tag in the top-level `tags:` list. The `<short-id>`
> is a stable, low-cardinality slug for the task family the experience
> belongs to (e.g. `task:snake-10x10`, `task:cifar10-classification`,
> `task:gsm8k`). Reuse existing slugs when patching; coin a new slug
> only when no neighbor card uses one. The tag is what future quests
> grep for via `list_knowledge_summaries` to find prior task-specific
> experience.

The frontmatter template (§ 1.B) gains an explicit `tags:` block:

```yaml
tags:
  - task:<short-id>          # required
  - stage:<stage>            # optional
  - domain:<domain>          # optional
  - method:<method>          # optional
```

**No code change.** The validation is convention-level (skill
contract), not schema-enforced. Rationale: tags are free-form across
all card kinds and adding hard validation would couple the memory
service to distill semantics. The skill contract is the right
enforcement surface; the existing `distill_review` audit catches
omissions in review.

**Backfill**: rewrite the two existing quest 010 cards under
`/home/ds/DeepScientist/memory/knowledge/`:

- `potential-based-reward-shaping-gives-strong-early-advantage-...md`
- `symbolic-features-enable-100-200x-sample-efficiency-...md`

Add `task:snake-10x10` to each `tags:` list (and the `keywords:`
field from § P2/N1 below).

### § P1. `startup_contract.recall_priors` (option b)

**Behaviour**: when a quest is created with `recall_priors: true`, the
prompt builder injects a one-line cue at the top of every stage skill
turn that reminds the agent to call `memory.list_knowledge_summaries`
once before doing stage work. The agent decides what to actually
recall; the cue is just "look first, then act".

#### § P1.1 Field plumbing

Mirror the existing `experience_distill` plumbing:

| File | Change |
|---|---|
| [src/deepscientist/artifact/experience_distill.py](src/deepscientist/artifact/experience_distill.py) | Add `coerce_recall_priors_mode`, `read_recall_priors_mode`, `is_recall_priors_on` (sibling to the three existing distill helpers at lines 102 / 128 / 150). They read `startup_contract.recall_priors` from `quest.yaml`. |
| [src/deepscientist/mcp/server.py:222-249](src/deepscientist/mcp/server.py#L222-L249) | Add `"recall_priors"` to `START_SETUP_FORM_FIELDS`. |
| [src/deepscientist/mcp/server.py:415-437](src/deepscientist/mcp/server.py#L415-L437) | Add a parallel `if key == "recall_priors":` bool-coercion branch in `_sanitize_start_setup_form_patch`. |
| [src/ui/src/lib/startResearch.ts](src/ui/src/lib/startResearch.ts) | Add `recall_priors: boolean` to the form type; default `false` at lines 198 / 321 / 375; coerce at line 602. |
| [src/ui/src/components/projects/CreateProjectDialog.tsx](src/ui/src/components/projects/CreateProjectDialog.tsx) | Default `recall_priors: false` at lines 1442 / 1484; pass through at lines 2488 / 2575. Add a toggle UI block beside the existing distill toggle (lines 3066-3074), with translation keys `recallPriorsEnabled` / `recallPriorsEnabledBody` / `recallPriorsDisabled` / `recallPriorsDisabledBody` (en + zh) added near the existing `distillEnabled` keys (en lines 239-242, zh lines 635-638). |

`recall_priors` defaults to `false` for parity with `experience_distill`
(opt-in), but the project-creation dialog should suggest enabling it
together with distill so the writer/reader pair operates as a unit.
This is a UI copy choice in the toggle body text, not a default
change.

#### § P1.2 Prompt builder injection

**File**: [src/deepscientist/prompts/builder.py](src/deepscientist/prompts/builder.py)

**Where**: in the existing per-turn cue block that produces
`recent_memory_cues:` ([builder.py:1031-1042](src/deepscientist/prompts/builder.py#L1031-L1042))
— this is the natural place for memory-orientation hints. Before
the `recent_memory_cues:` lines, add a conditional block:

```python
if is_recall_priors_on(quest_root):
    lines.append(
        "- recall_priors_rule: before generating new ideas, baselines, or experiment plans, "
        "call `memory.list_knowledge_summaries(scope='global')` once and scan the returned "
        "rows for any `task:` tag, claim, or keyword that overlaps your current quest. "
        "Read the full card via `memory.read_card` for any candidate that looks relevant. "
        "If nothing matches, say so explicitly in your reasoning and proceed."
    )
```

**Scope guard**: only inject when the active skill is a *stage* skill
(`stage_skill_ids(repo_root())` membership). Companion skills like
`distill` itself, `figure-polish`, etc. should not see the cue —
distill already lists summaries as part of its own protocol (§ P2
below), and figure-polish has no use for it. The check is a single
membership test against the existing `stage_skill_ids` helper already
imported at [builder.py:16](src/deepscientist/prompts/builder.py#L16).

**Why this location, not a step 0 inside each stage SKILL.md?** The
prompt builder is the single point that already gathers per-turn
memory state for every skill turn. Injecting from there:

- requires zero edits to the seven stage skills,
- guarantees the cue fires every turn (not just first turn of a
  stage),
- keeps the rule centralized so future tuning lands in one file,
- mirrors the existing pattern for `recent_memory_cues:` and
  `workspace_checklist_rule` lines (already injected per-turn here).

The cue is a *rule*, not a step — it does not prescribe when in the
turn the call must happen, only that it must happen before stage
output.

### § P2. Keyword summaries (N1–N4)

#### § P2.N1 — `keywords` frontmatter field

**File**: [src/skills/distill/SKILL.md](src/skills/distill/SKILL.md)

Add `keywords` as a top-level frontmatter field (sibling of `claim`,
`mechanism`, `conditions`), required for new cards:

```yaml
keywords:
  - <3..8 short, lowercased noun phrases or compound tokens>
```

Body guidance: keywords are the agent's index into the card. Examples:
`reward-shaping`, `manhattan-distance`, `snake-grid`, `dqn`,
`epsilon-decay`. Avoid full sentences and avoid duplicating tag
content verbatim; tags are for filtering, keywords are for skim
recall. 3–8 items.

**Validation**: convention-level only, not schema-enforced — same
rationale as the `task:` tag (§ D). The distill skill enforces it as
a hard constraint; the `validate_experience_metadata` helper
([experience_distill.py:50-71](src/deepscientist/artifact/experience_distill.py#L50-L71))
is **not** changed. Keeping schema validation narrow avoids breaking
the small set of older cards that exist without keywords.

The frontmatter template (§ 1.B of distill SKILL.md) gains:

```yaml
keywords:
  - <kw-1>
  - <kw-2>
  - ...
```

**Patching rule**: when patching a cross-quest card, the agent may
*append* keywords (broaden the index) but should not delete existing
ones. Same-quest patches are free-edit. This is documented in the
skill, not enforced.

#### § P2.N2 — `memory.list_knowledge_summaries` MCP tool

**Service method**

**File**: [src/deepscientist/memory/service.py](src/deepscientist/memory/service.py)

Add a new method on `MemoryService`:

```python
def list_knowledge_summaries(
    self,
    *,
    scope: str = "global",
    quest_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Return compact summaries of every knowledge-kind card in scope.

    Each row:
      {
        "card_id": "knowledge-...",
        "title": "<frontmatter title>",
        "claim": "<frontmatter claim>",            # may be empty for non-experience cards
        "keywords": ["...", "..."],                 # may be []
        "tags": ["task:...", "stage:...", ...],     # may be []
        "scope": "global" | "quest",
        "quest_id": "<id>",
        "subtype": "experience" | "..." | None,
        "updated_at": "<ISO timestamp>",
      }
    """
```

Behaviour:

- `scope="global"` reads from `~/DeepScientist/memory/knowledge/`.
- `scope="quest"` reads from `<quest_root>/memory/knowledge/`.
- `scope="visible"` reads global + visible quest cards (mirrors
  `list_visible_quest_cards` semantics).
- Returns *all* knowledge cards in scope. **No ranking, no filtering,
  no pagination.** The expectation is that 100 cards × ~300 bytes/row
  = ~30 KB, well within an LLM scan budget.
- Sort: most-recently-updated first, then by `card_id` for stability.

**MCP registration**

**File**: [src/deepscientist/mcp/server.py](src/deepscientist/mcp/server.py)

Register under the `memory` namespace (knowledge cards live in memory,
not artifact). Mirror the read-only annotation pattern used for
`list_distill_candidates`:

```python
@server.tool(
    name="list_knowledge_summaries",
    description=(
        "List compact summaries (id / title / claim / keywords / tags) of every "
        "knowledge-kind card in scope. Use this before generating ideas or starting "
        "distill to find prior experience to recall or patch. Returns all cards "
        "unsorted-by-relevance — scan the rows yourself and `memory.read_card` "
        "anything that looks worth reading in full."
    ),
    annotations=_read_only_tool_annotations(title="List knowledge summaries"),
)
def list_knowledge_summaries(
    scope: str = "global",
    comment: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "scope": scope,
        "summaries": service.memory.list_knowledge_summaries(
            scope=scope,
            quest_root=context.optional_quest_root(),
        ),
    }
```

**Codex approval allowlist**

**File**: [src/deepscientist/runners/codex.py:41-47](src/deepscientist/runners/codex.py#L41-L47)

Add `"list_knowledge_summaries"` to the `"memory"` tuple in
`_BUILTIN_MCP_TOOL_APPROVALS`.

#### § P2.N3 — Distill skill step 1 rewrite

**File**: [src/skills/distill/SKILL.md](src/skills/distill/SKILL.md)

**Current** ([SKILL.md:34-46](src/skills/distill/SKILL.md#L34-L46)):
"Search for neighbors → `memory.search(query=<keywords>, scope=global,
kind=knowledge, limit=10)` → read top 3."

**Replace with**:

```markdown
**Search for neighbors via the keyword summary index.**

```json
{"tool": "memory.list_knowledge_summaries", "arguments": {"scope": "global"}}
```

The tool returns one row per global knowledge card with
`card_id / title / claim / keywords / tags / subtype / updated_at`.
Scan the rows for any card whose `task:` tag, `claim`, or `keywords`
overlap the candidate run you are processing.

For each row that looks like a plausible neighbor, fetch the full
card:

```json
{"tool": "memory.read_card", "arguments": {"card_id": "knowledge-..."}}
```

Decide one of:

- **patch** — the existing card and the candidate run share a
  causal mechanism. Append a `lineage` entry, possibly downgrade
  `confidence`, narrow `conditions`, and append (do not delete)
  `keywords`. The `claim` is immutable across quests.
- **new** — no existing card covers the candidate's mechanism;
  write a fresh card with `memory.write_card`.
- **neighbor_but_separate** — a related card exists but the
  candidate's mechanism is genuinely different. Note the
  relationship in `notes` but write a new card anyway.
```

**Keep the rest of step 1** (the patch / new / no-card structure
in the existing § A / B / C is preserved). The change is purely the
neighbor-discovery mechanism.

**Remove**: the `memory.search` call from step 1. `memory.search`
remains available as a general tool — distill just no longer uses
it for neighbor discovery.

#### § P2.N4 — Optional `neighbor_decisions` in `distill_review`

**File**: [src/deepscientist/artifact/schemas.py:55-90](src/deepscientist/artifact/schemas.py#L55-L90)

Extend the `distill_review` validation block to accept an optional
`neighbor_decisions` array:

```yaml
neighbor_decisions:               # optional, may be omitted entirely
  - candidate_card_id: knowledge-... # the existing card the agent considered
    decision: patch | new | neighbor_but_separate
    reason: <one phrase>
    target_run_id: run-...        # which candidate run this judgment was for
```

**Validation rules** (added to the existing `if kind == "distill_review":`
block):

- If absent or empty list → no validation.
- Each entry must be a dict with the four required fields above.
- `decision` must be one of `{"patch", "new", "neighbor_but_separate"}`.
- `target_run_id` must be in `reviewed_run_ids` (same rule as
  `cards_written[*].target_run_id`).
- `candidate_card_id` is **not** verified against any card index
  (cards may be deleted or renamed; the audit captures the agent's
  reasoning at review time, not a live cross-reference).

Add a constant `DISTILL_NEIGHBOR_DECISIONS = {"patch", "new",
"neighbor_but_separate"}` next to the existing
`DISTILL_CARD_ACTIONS` / `DISTILL_CARD_SCOPES`.

**Skill-side guidance** (in distill SKILL.md step 3, the
`distill_review` recording block): record one `neighbor_decisions`
entry per neighbor candidate the agent inspected, **even when the
final decision was `new` or `neighbor_but_separate`**. This makes the
review log show what the agent considered, not just what it wrote.

The field is **optional** because:

- the `cards_written[*].action` field already records `patch` vs
  `new` for cards that were written;
- `neighbor_decisions` adds the *negative* signal — "I looked at
  card X and decided not to patch it" — which is the part missing
  from the current schema.

A purely additive optional field keeps Phase 2 `distill_review`
records valid.

## File-by-file change summary

| File | Change | Section |
|---|---|---|
| [src/deepscientist/artifact/experience_distill.py](src/deepscientist/artifact/experience_distill.py) | Drop fallback append in `maybe_inject_distill_finalize_gate`; remove `_FINALIZE_GATE_FALLBACK_REASON`; sharpen action wording. Add `coerce_recall_priors_mode` / `read_recall_priors_mode` / `is_recall_priors_on`. | § A, § P1.1 |
| [src/deepscientist/artifact/schemas.py](src/deepscientist/artifact/schemas.py) | Add `DISTILL_NEIGHBOR_DECISIONS` constant; extend `distill_review` validation with optional `neighbor_decisions` block. | § P2.N4 |
| [src/deepscientist/memory/service.py](src/deepscientist/memory/service.py) | Add `list_knowledge_summaries(scope, quest_root)` method on `MemoryService`. | § P2.N2 |
| [src/deepscientist/mcp/server.py](src/deepscientist/mcp/server.py) | Add `"recall_priors"` to `START_SETUP_FORM_FIELDS`; add coerce branch in `_sanitize_start_setup_form_patch`; register `memory.list_knowledge_summaries` MCP tool. | § P1.1, § P2.N2 |
| [src/deepscientist/runners/codex.py](src/deepscientist/runners/codex.py) | Add `"list_knowledge_summaries"` to `_BUILTIN_MCP_TOOL_APPROVALS["memory"]`. | § P2.N2 |
| [src/deepscientist/prompts/builder.py](src/deepscientist/prompts/builder.py) | Inject `recall_priors_rule:` line in per-turn cue block, gated on `is_recall_priors_on(quest_root)` and active stage skill. | § P1.2 |
| [src/skills/distill/SKILL.md](src/skills/distill/SKILL.md) | Rewrite step 1 to summary-scan flow; add `task:` tag requirement; add `keywords` field to template; document `neighbor_decisions` recording in step 3. | § D, § P2.N1, § P2.N3, § P2.N4 |
| [src/ui/src/lib/startResearch.ts](src/ui/src/lib/startResearch.ts) | Add `recall_priors: boolean` to form type; default `false`; coerce in submit. | § P1.1 |
| [src/ui/src/components/projects/CreateProjectDialog.tsx](src/ui/src/components/projects/CreateProjectDialog.tsx) | Add `recall_priors: false` defaults at four sites; add toggle UI block; add four translation keys (en + zh). | § P1.1 |
| `~/DeepScientist/memory/knowledge/potential-based-reward-shaping-...md` | Add `task:snake-10x10` to `tags`; add `keywords` block. | Backfill |
| `~/DeepScientist/memory/knowledge/symbolic-features-enable-...md` | Add `task:snake-10x10` to `tags`; add `keywords` block. | Backfill |

## Test coverage outline

The implementation plan will expand into individual cases.

- **Routing strength** (`tests/test_artifact_guidance.py`):
  - `decision(action='write')` with pending candidates → guidance
    has `recommended_skill="distill"`, `recommended_action` matches
    the new imperative wording, and `alternative_routes` does **not**
    contain a fallback entry pointing back to write.
  - same decision after gate clears → `recommended_skill` restored
    from `previous_recommended_skill`, no stale fallback entries.
- **`recall_priors`** (`tests/test_experience_distill.py` and
  `tests/test_prompt_builder.py`):
  - `coerce_recall_priors_mode` round-trips bool / string / dict.
  - `read_recall_priors_mode` reads `startup_contract.recall_priors`
    correctly; defaults to off when missing or quest.yaml absent.
  - prompt builder injects `recall_priors_rule:` when on + stage
    skill, omits when off, omits for companion skills.
- **`list_knowledge_summaries`** (`tests/test_memory_service.py` and
  `tests/test_mcp_servers.py`):
  - returns rows with all required fields for global scope.
  - empty memory dir → empty list.
  - cards with no `keywords` / no `claim` → fields surface as `[]` /
    `""`, not missing.
  - sort: most-recently-updated first.
  - MCP tool surface: scope param defaults to `global`; tool
    annotation is read-only.
- **`distill_review.neighbor_decisions`** (`tests/test_artifact_schemas.py`):
  - omitted → valid.
  - empty list → valid.
  - entry with unknown `decision` value → rejected.
  - entry with `target_run_id` not in `reviewed_run_ids` → rejected.
  - well-formed entry alongside `cards_written` → accepted.
- **End-to-end** (new fixture in `tests/test_artifact_service.py`
  or extension of the Phase 2 fixture):
  - quest with one completed `main_experiment`,
    `experience_distill: true`, `recall_priors: true`.
  - record `decision(action='write')` → guidance recommends distill
    with the new imperative wording, no fallback route.
  - `memory.list_knowledge_summaries(scope='global')` returns the
    seeded global cards.
  - record `distill_review` with one `cards_written` entry and one
    `neighbor_decisions` entry → both validate; gate clears; next
    `decision(action='write')` is unblocked.

## Out of scope

- Hard schema validation for `task:` tag and `keywords` field
  (convention-enforced via the skill, not the memory service).
- Embedding / BM25 / TF-IDF retrieval infrastructure.
- Promoting `recall_priors` to a hard gate (it remains a prompt cue;
  the agent can ignore it the same way it can ignore `recent_memory_cues:`).
- Migration of historical knowledge cards beyond the two quest 010
  cards (older cards may stay without `keywords` / `task:` tags;
  `list_knowledge_summaries` surfaces them with empty arrays).
- Workflow-graph changes; `recall_priors` does not become a stage
  anchor.
