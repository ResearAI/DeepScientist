# 34 Experience Distillation Guide

This page explains the opt-in cross-quest experience-distillation pipeline: how a quest reviews its own completed runs, writes reusable knowledge cards into global memory, and surfaces those cards as priors to future quests.

Use this when:

- you want a quest's hard-won lessons to become available to later quests instead of staying locked inside one repo
- you want `submit_paper_bundle` / `complete_quest` to refuse to close a quest until the runs have been distilled
- you are debugging a quest that was rerouted to the `distill` skill and want to know what the gate looks for

If you only need the conceptual layout of memory and MCP tools, read [07 Memory and MCP](./07_MEMORY_AND_MCP.md) first. For the broader prompt/skill/MCP architecture see [14 Prompt, Skills and MCP Guide](./14_PROMPT_SKILLS_AND_MCP_GUIDE.md).

## 1. One-sentence summary

When `experience_distill` is on, a quest must convert each completed run into a `decision(action='distill_review')` artifact (and the knowledge cards it cites) before paper-bundle submission or quest completion will succeed. When `recall_priors` is on, stage prompts cue the agent to browse those cards from prior quests before committing to an idea or experiment design.

## 2. Where you choose this

Both toggles live in the project-creation form (advanced section of the start dialog) and end up under `quest.yaml.startup_contract`:

- `experience_distill` — accepts `on` / `off`, or the structured form `{mode: on|off}`. Default: off.
- `recall_priors` — accepts `on` / `off`. Default: off.

Existing quests with neither toggle set are unaffected by anything on this page.

## 3. The cross-quest knowledge loop

The end-to-end shape is:

1. Quest runs experiments. Each `main_experiment` / `experiment` / `analysis.slice` run is a candidate for distillation once `status: completed`.
2. After completion, when the agent attempts `decision(action='write'|'finalize')`, the **finalize gate** intercepts: if there are completed runs not yet covered by any `decision(action='distill_review')`, guidance is rerouted to the `distill` skill.
3. The `distill` skill reviews the candidate batch, decides whether to write a new global knowledge card or patch an existing one, and records a `decision(action='distill_review')` artifact citing the run ids and explicit `neighbor_decisions` against existing cards.
4. The cards land under `~/DeepScientist/memory/knowledge/` as global memory.
5. The next quest, if `recall_priors: on`, sees a stage-prompt cue and the `memory.list_knowledge_summaries` MCP tool, and can browse the prior cards before idea selection / experiment design.

## 4. The finalize gate

The gate fires on `artifact.record(kind='decision', action='write'|'finalize')`. It runs `evaluate_distill_gate_for_quest(quest_root)`, which scans:

- `quest_root/artifacts/`
- every `quest_root/.ds/worktrees/*/artifacts/`

Candidates and reviews are deduped by `artifact_id`. If any completed run lacks a `decision(action='distill_review')` covering it, the gate:

- swaps `guidance_vm.recommended_skill` to `distill`
- drops the `write` / `finalize` route from `alternative_routes` (no fallback)
- exposes `pending_distill_count` and `pending_distill_ids[:5]` in the guidance payload

When the gate is clear (no pending candidates), it returns `guidance_vm` unchanged and the original `write` recommendation passes through.

## 5. Hard guards on closure

Independent of the soft routing above, the same multi-workspace check is enforced on the closure entry points so a runner cannot bypass the gate by skipping the `decision` record:

- `artifact.submit_paper_bundle` — raises `ValueError` with `submit_paper_bundle blocked: experience_distill is on and N completed run(s) lack a distill_review (pending: ...)`.
- `artifact.complete_quest` — returns `{ok: false, status: "distill_required", pending_distill_count, pending_distill_ids, message}` instead of completing.

Both guards no-op when `experience_distill` is off, when no candidates exist, or when the quest is already in a terminal status.

## 6. The `distill` skill and `decision(action='distill_review')` artifact

The `distill` skill follows a per-batch summary-scan pattern:

1. Call `artifact.list_distill_candidates` to enumerate undistilled completed runs visible under the active workspace.
2. For each candidate, summary-scan: open the run record, identify the durable lesson, and either write a new global card under `memory/knowledge/` or patch an existing one (using `memory.write` / `memory.patch`).
3. For each card touched, record a `neighbor_decision` against any existing global card on a similar topic. Decision values:
   - `merge` — the candidate's lesson is the same as the existing card; merge in-place
   - `neighbor_but_separate` — related but a different mechanism / direction; keep both
   - `skip` — the candidate adds nothing the existing card doesn't already say
4. Record one `decision(action='distill_review')` artifact for the batch:

```yaml
kind: decision
action: distill_review
verdict: covered
reason: "<one-line summary of the batch>"
reviewed_run_ids: [run-..., ...]
cards_written:
  - {card_id: knowledge-..., scope: global, action: new|patch, target_run_id: run-...}
neighbor_decisions:
  - {candidate_card_id: knowledge-..., scope: global, decision: merge|neighbor_but_separate|skip,
     target_run_id: run-..., reason: "..."}
notes: "free-form summary"
```

`kind`, `action`, `verdict`, and `reason` are the standard `decision`
artifact fields. The remaining fields (`reviewed_run_ids`,
`cards_written`, `neighbor_decisions`, `reason_if_empty`, `notes`) are
review-specific and only validated when `action == 'distill_review'`.
The validator checks that every `target_run_id` in `cards_written` and
`neighbor_decisions` appears in `reviewed_run_ids`, and that every
`reviewed_run_ids` entry references a known run somewhere in the
quest's workspace dirs (worktrees included). The card-frontmatter
validator additionally requires `subtype: experience` plus a `lineage`
block citing `quest:<id>` and `run:<id>` for cross-quest auditability.

## 7. Cross-quest recall

When `recall_priors: on`:

- A `recall_priors_rule` cue is injected into stage-skill prompts (idea, experiment, decision, write, finalize…). The cue tells the agent to browse global knowledge cards before committing to an idea or experiment design.
- The `memory.list_knowledge_summaries` MCP tool is exposed under the `memory` namespace. It supports keyword and scope filters and returns ranked summaries (id, title, scope, tags, excerpt) without forcing the agent to read every card body.

The cue and the tool are independent of `experience_distill` — you can turn priors-recall on for a quest that itself does not distill, and vice versa.

## 8. MCP tools

Under existing `artifact` and `memory` namespaces (no new public namespaces):

- `artifact.list_distill_candidates` — completed runs not yet covered by any `decision(action='distill_review')` under the active workspace.
- `memory.list_knowledge_summaries` — keyword/scope-filtered browse over global `knowledge/` cards from any quest.

Codex auto-approves both. Claude allows them via `--allowedTools mcp__memory,mcp__artifact` (server-namespace allowlist). OpenCode allows them under default `permission_mode: allow`.

## 9. The retroactive CLI

For quests that finished before the gate existed, you can re-emit the distill draft offline:

```bash
ds distill-quest <quest_id>
```

This emits one draft per uncovered completed run under `~/DeepScientist/drafts/experiences/<quest_id>/`. The agent (or the user) can then review the drafts and record the `decision(action='distill_review')` artifact through the normal MCP path. The CLI returns `1` and prints `Quest not found: <id>` to stderr if the quest does not exist.

## 10. Operational notes

- **Default off.** Both toggles default off. Existing quests are unaffected.
- **Multi-workspace aggregation.** The gate, the validator, and `list_distill_candidates` all scan `quest_root/artifacts` plus every `.ds/worktrees/*/artifacts/`. A run sitting in an idea worktree still trips the gate.
- **Gate clears on equivalent re-records.** Recording a semantically equivalent `decision` reuses the existing artifact id; the gate evaluates against the canonical record, not the duplicate.
- **No automatic merging.** Two cards from different quests on a similar topic are kept as separate cards by default. The agent records a `neighbor_decision` saying so; merging is an explicit `action: patch`.
- **Quest 011 → 012 example.** Quest 011 wrote a card on safety masking (negative result). Quest 012's distill_review chose `neighbor_but_separate` against it because the new card documents the inverse-direction (inference-time vs training-time) placement of the same notion — pos/neg pair preserved.

## 11. Failure modes and debugging

- **Submission rejected with `lack a distill_review`.** Run the `distill` skill and record `decision(action='distill_review')`; resubmit. Confirm the run id in the error message exists somewhere under the workspace tree.
- **`distill_review decision references unknown run artifact_ids`.** The validator scans every workspace artifact dir; if the run is real but the error fires anyway, the run record was never indexed. Check that the run's worktree `_index.jsonl` actually contains the run id.
- **Cards not appearing in the next quest.** Check `~/DeepScientist/memory/knowledge/_index.jsonl` for an entry with the right `quest_id`. Then check that the next quest has `recall_priors: on` and that stage prompts mention `recall_priors_rule`.
- **`ds doctor`** does not currently surface distill state explicitly; inspect `quest_root/artifacts/decisions/` (filter for `action: distill_review`) and the canonical `_index.jsonl` directly.

## 12. Cross-links

- [07 Memory and MCP](./07_MEMORY_AND_MCP.md) — how memory cards are stored, scoped, and surfaced
- [14 Prompt, Skills and MCP Guide](./14_PROMPT_SKILLS_AND_MCP_GUIDE.md) — how stage skills are wired and how MCP tool approvals work
- [02 Start Research Guide](./02_START_RESEARCH_GUIDE.md) — the form fields that flow into `startup_contract`
