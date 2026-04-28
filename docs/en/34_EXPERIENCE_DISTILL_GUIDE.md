# 34 Experience Distillation Guide

This page explains the opt-in cross-quest experience-distillation pipeline: how a quest reviews its own completed runs, writes reusable knowledge cards into global memory, and surfaces those cards as priors to future quests.

Use this when:

- you want a quest's hard-won lessons to become available to later quests instead of staying locked inside one repo
- you want `submit_paper_bundle` / `complete_quest` to refuse to close a quest until its runs have been distilled
- you are debugging a quest that was rerouted to the `distill` skill and want to know what the gate looks for

For the conceptual layout of memory and MCP tools see [07 Memory and MCP](./07_MEMORY_AND_MCP.md). For the broader prompt/skill/MCP architecture see [14 Prompt, Skills and MCP Guide](./14_PROMPT_SKILLS_AND_MCP_GUIDE.md).

## 1. Toggles

Two toggles live in the project-creation form (advanced section) and end up under `quest.yaml.startup_contract`:

- `experience_distill` — accepts `on` / `off`, or `{mode: on|off}`. Default: off. When on, a quest must convert each completed run into a `decision(action='distill_review')` artifact (and any knowledge cards it cites) before paper-bundle submission or quest completion will succeed.
- `recall_priors` — accepts `on` / `off`. Default: off. When on, stage prompts cue the agent to browse cards from prior quests before committing to an idea or experiment design.

Existing quests with neither toggle set are unaffected.

## 2. The cross-quest knowledge loop

1. Quest runs experiments. Each completed run is a candidate for distillation.
2. When the agent attempts `decision(action='write'|'finalize')`, the **finalize gate** intercepts: if any completed runs are not yet covered by a `decision(action='distill_review')`, guidance is rerouted to the `distill` skill.
3. The `distill` skill reviews the candidate batch, writes/patches global knowledge cards, and records one `decision(action='distill_review')` artifact citing the run ids and explicit `neighbor_decisions` against existing cards.
4. Cards land under `~/DeepScientist/memory/knowledge/` as global memory.
5. The next quest, if `recall_priors: on`, sees a stage-prompt cue and the `memory.list_knowledge_summaries` MCP tool, and can browse prior cards before idea selection / experiment design.

## 3. The finalize gate

The gate fires on `artifact.record(kind='decision', action='write'|'finalize')`. It runs `evaluate_distill_gate_for_quest(quest_root)`, which scans `quest_root/artifacts/` and every `quest_root/.ds/worktrees/*/artifacts/`. Candidates and reviews are deduped by `artifact_id`. If any completed run lacks a covering `decision(action='distill_review')`, the gate swaps `guidance_vm.recommended_skill` to `distill`, drops the `write` / `finalize` route from `alternative_routes`, and exposes `pending_distill_count` and `pending_distill_ids[:5]` in the guidance payload. When the gate is clear, `guidance_vm` passes through unchanged.

## 4. Hard guards on closure

The same multi-workspace check is enforced on the closure entry points so a runner cannot bypass the gate by skipping the `decision` record:

- `artifact.submit_paper_bundle` — raises `ValueError` with `submit_paper_bundle blocked: experience_distill is on and N completed run(s) lack a distill_review (pending: ...)`.
- `artifact.complete_quest` — returns `{ok: false, status: "distill_required", pending_distill_count, pending_distill_ids, message}` instead of completing.

Both no-op when `experience_distill` is off, when no candidates exist, or when the quest is already in a terminal status.

## 5. The `distill` skill and `decision(action='distill_review')` artifact

The `distill` skill processes the batch returned by `artifact.list_distill_candidates`. For each candidate it either writes a new global card under `memory/knowledge/`, patches an existing one, or skips. It then records exactly one `decision(action='distill_review')` artifact for the batch:

```yaml
kind: decision
action: distill_review
verdict: covered
reason: "<one-line summary of the batch>"
reviewed_run_ids: [run-..., ...]
cards_written:
  - {card_id: knowledge-..., scope: global, action: new|patch, target_run_id: run-...}
neighbor_decisions:
  - {candidate_card_id: knowledge-..., decision: patch|neighbor_but_separate,
     target_run_id: run-..., reason: "..."}
notes: "free-form summary"
```

`kind`, `action`, `verdict`, and `reason` are the standard `decision` fields. `reviewed_run_ids`, `cards_written`, `neighbor_decisions`, `reason_if_empty`, and `notes` are review-specific and only validated when `action == 'distill_review'`. The validator checks that every `target_run_id` appears in `reviewed_run_ids`, and that every `reviewed_run_ids` entry references a known run somewhere in the quest's workspace dirs (worktrees included).

The card-frontmatter validator only requires two fields: a non-empty `claim` and a non-empty `lineage` list whose entries each cite at least `quest:<id>` and `run:<id>` for cross-quest auditability. Cards may carry additional fields (`subtype`, `mechanism`, `conditions`, `confidence`, `keywords`, `tags`) but their presence is not enforced.

## 6. Cross-quest recall

When `recall_priors: on`, a `recall_priors_rule` cue is injected into stage-skill prompts and the `memory.list_knowledge_summaries` MCP tool is exposed under the `memory` namespace. The tool supports keyword and scope filters and returns ranked summaries (id, title, scope, tags, excerpt) without forcing the agent to read every card body. The cue and the tool are independent of `experience_distill` — either toggle can be enabled without the other.

## 7. MCP tools

Under existing `artifact` and `memory` namespaces (no new public namespaces):

- `artifact.list_distill_candidates` — completed runs not yet covered by any `decision(action='distill_review')` under the active workspace.
- `memory.list_knowledge_summaries` — keyword/scope-filtered browse over global `knowledge/` cards from any quest.

Codex auto-approves both. Claude allows them via `--allowedTools mcp__memory,mcp__artifact`. OpenCode allows them under default `permission_mode: allow`.

## 8. The retroactive CLI

```
ds distill-quest <quest_id>
```

Emits one draft per uncovered completed run under `~/DeepScientist/drafts/experiences/<quest_id>/`. The agent (or the user) reviews the drafts and records the `decision(action='distill_review')` through the normal MCP path. Returns `1` and prints `Quest not found: <id>` to stderr if the quest does not exist.

## 9. Operational notes

- **Default off.** Both toggles default off; existing quests are unaffected.
- **Multi-workspace aggregation.** The gate, the validator, and `list_distill_candidates` all scan `quest_root/artifacts` plus every `.ds/worktrees/*/artifacts/`. A run sitting in an idea worktree still trips the gate.
- **No automatic merging.** Two cards from different quests on a similar topic are kept separate by default. Merging is an explicit `action: patch` with an appended `lineage` entry.
- **Cross-quest patch invariant.** When patching across quests, `claim` is immutable and existing optional fields may only be appended to; same-quest patches may freely edit.

## 10. Failure modes and debugging

- **Submission rejected with `lack a distill_review`.** Run the `distill` skill and record `decision(action='distill_review')`; resubmit.
- **`distill_review decision references unknown run artifact_ids`.** The validator scans every workspace artifact dir; if the run is real but the error fires anyway, the run record was never indexed. Check that the run's worktree `_index.jsonl` actually contains the run id.
- **Cards not appearing in the next quest.** Check `~/DeepScientist/memory/knowledge/_index.jsonl` for the right `quest_id` entry, and confirm the next quest has `recall_priors: on`.

## 11. Cross-links

- [07 Memory and MCP](./07_MEMORY_AND_MCP.md) — how memory cards are stored, scoped, and surfaced
- [14 Prompt, Skills and MCP Guide](./14_PROMPT_SKILLS_AND_MCP_GUIDE.md) — how stage skills are wired and how MCP tool approvals work
- [02 Start Research Guide](./02_START_RESEARCH_GUIDE.md) — the form fields that flow into `startup_contract`
