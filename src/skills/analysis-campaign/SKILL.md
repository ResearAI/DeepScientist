---
name: analysis-campaign
description: Use when a quest needs one or more follow-up runs such as ablations, robustness checks, error analysis, or failure analysis after a main experiment.
skill_role: stage
---

# Analysis Campaign

Use this skill when follow-up evidence is needed after a durable result.
The goal is to answer a bounded, resource-aware evidence question, not to keep opening more slices just because they are imaginable.

## Match signals

Use `analysis-campaign` when:

- a durable main result already exists and follow-up evidence is needed
- the quest needs ablations, robustness checks, sensitivity checks, failure analysis, error analysis, efficiency or cost checks, or limitation-boundary checks
- writing, review, or rebuttal pressure exposed an evidence gap that should be answered by bounded follow-up slices

Do not use `analysis-campaign` when:

- the quest still lacks a credible main run or accepted baseline and the proposed work depends on that missing reference
- the next step is obviously another main experiment rather than follow-up evidence work
- the proposed slice does not connect to a parent claim, parent result, paper gap, reviewer item, or route decision

## One-sentence summary

Answer the smallest evidence question that changes, confirms, or blocks a parent claim, then stop when the next route is clear.

## Control workflow

1. Lock the parent object, evidence question, comparison target, and stop condition.
   Make explicit what claim, failure mode, or route decision is actually being tested.
2. Audit the real execution envelope before designing the slice set.
   Make explicit the current device and runtime limits: available GPU or CPU class, memory, wall-clock budget, storage, concurrency, required dependencies, and any queue or service constraints that materially limit what can run now.
3. Choose the lightest analysis route and the smallest slice set that can answer the question within that envelope.
   Prefer slices with the highest soundness gain per unit of compute, time, or engineering effort.
   Run claim-critical slices first and mark infeasible slices explicitly instead of quietly keeping them in scope.
4. Keep slices isolated and comparable.
   Record exactly what changed, what stayed fixed, and whether apples-to-apples comparison still holds.
5. Record slice-level evidence before making any campaign-level claim.
   Every meaningful slice should leave a durable outcome and a claim update.
6. Aggregate only the decision-relevant findings and route the next step.
   End in continue, write, experiment, idea, decision, blocker, or stop.

## AVOID / pitfalls

- Do not disguise a new main experiment as an analysis slice.
- Do not hide null, negative, partial, failed, or contradictory slices.
- Do not change many factors at once and then interpret the result as isolating one factor.
- Do not widen the campaign after the next route is already clear.
- Do not use subjective or manual inspection to support a claim without rubric, sample, prompt, trace, and caveat.
- Do not design a slice frontier that ignores current hardware, memory, runtime, or storage limits.
- Do not keep infeasible slices as silent assumptions; either downscope them, replace them with runnable proxies, or record them as blocked.

## Constraints

- Every meaningful slice must map to a parent claim, parent result, paper gap, reviewer item, or route decision.
- Every evidence-bearing slice must record question, intervention or inspection target, fixed conditions, metric or observable, evidence path, claim update, comparability verdict, and next action.
- Keep the same evaluation contract unless the variation itself is the point.
- When baseline comparison matters, keep slice comparisons aligned with the active baseline metric contract unless the deviation is explicit.
- Campaign-level conclusions must be derived from per-slice evidence rather than impressions.
- Campaign design must be conditioned on the current execution envelope, not an idealized future machine.
- If a slice would materially improve soundness but is infeasible now, record the blocker and choose the best runnable lower-cost alternative or narrower proxy.
- If a slice is paper-relevant, its result must be bound back into the current paper contract rather than left only in `experiments/analysis-results/*` or chat.

## Validation

Before `analysis-campaign` can end, all applicable checks should be true:

- the parent object is explicit
- the current execution envelope and its binding constraints are explicit when they affect slice design or ordering
- every launched slice has a durable outcome: completed, partial, failed, blocked, infeasible, or superseded
- launched and deferred slices were screened against the current device or resource limits
- null, negative, failed, partial, and contradictory findings remain visible
- the campaign changed or confirmed the evidence boundary of the parent claim with traceable slice-level evidence
- the next route is explicit: continue campaign, return to `experiment`, return to `idea`, move to `write`, route through `decision`, stop, reset, or record a blocker

## Interaction discipline

Follow the shared interaction contract injected by the system prompt.
Keep campaign updates brief unless the evidence boundary, blocker state, cost, or next route changed materially.
For ordinary active work, prefer a concise progress update once work has crossed roughly 6 tool calls with a human-meaningful delta, and do not drift beyond roughly 12 tool calls or about 8 minutes without a user-visible update.
For meaningful long-running slices, include the estimated next reply time or next check-in window whenever it is defensible.

## Authority and freedom

The agent owns the analysis path.
It may choose a one-slice check, a lightweight durable report, an artifact-backed one-slice campaign, a full multi-slice campaign, or a writing-facing campaign.
It may choose slice order, workspace layout, filenames, monitoring strategy, and whether a smoke test, direct verification, or full run is the right first move.
It may also shrink, reorder, or replace slices to fit the real hardware and runtime envelope, as long as the resulting campaign still answers the parent evidence question honestly.

Do not treat `PLAN.md`, `CHECKLIST.md`, `artifact.create_analysis_campaign(...)`, one-slice campaigns, returned worktrees, `evaluation_summary`, smoke tests, detached runs, paper-matrix files, `tqdm`, or a fixed phase order as required paths.
They are tactics.
The hard requirement is traceable evidence that changes, confirms, or blocks the evidence boundary of the parent claim and leaves an explicit next route.

Use the artifact-backed campaign path when durable lineage, branch or worktree isolation, Canvas visibility, paper or rebuttal traceability, or multiple slices matter.
Use a lighter durable report when one bounded answer is enough and extra campaign overhead would not improve trust, routing, or auditability.

For campaign prioritization and writing-facing slice design, read `references/campaign-design.md`.
When the campaign is writing-facing and the mapping fields are not obvious, also read `references/writing-facing-slice-examples.md`.
For artifact examples and edge-case examples, also read `references/artifact-flow-examples.md` and `references/boundary-cases.md`.

## Hard success gates

An analysis campaign succeeds when it changes or confirms the evidence boundary of a parent claim with traceable slice-level evidence, preserves comparability or records why comparability broke, and leaves a durable next-route decision.

Before treating analysis as successful, all applicable gates must be true:

- the parent object is explicit, such as a main run, accepted idea line, paper gap, reviewer item, or rebuttal item
- the claim, question, failure mode, or decision being tested is explicit
- the slice frontier was screened against current compute, memory, storage, dependency, and runtime limits
- every launched slice has a durable outcome: completed, partial, failed, blocked, infeasible, or superseded
- every evidence-bearing slice records the question, intervention or inspection target, fixed conditions, metric or observable, evidence path, claim update, comparability verdict, and next action
- null, negative, failed, partial, and contradictory findings remain visible
- campaign-level interpretation is derived from per-slice evidence rather than impressions
- the next route is explicit: continue campaign, return to `experiment`, return to `idea`, move to `write`, route through `decision`, stop, reset, or record a blocker

## Analysis routes

Use the lightest route that preserves trust and downstream utility.

- `analysis-lite`: one clear follow-up question, one slice or very small slice set, and a compact durable result
- `artifact-backed campaign`: one or more slices that need durable lineage, branch/worktree isolation, Canvas visibility, or later replay
- `writing-facing campaign`: evidence directly supports a selected outline, paper experiment matrix, evidence ledger, section, claim, or table
- `review/rebuttal campaign`: evidence directly answers reviewer pressure or audit findings
- `failure-analysis route`: evidence explains why a result failed, diverged, or became non-comparable

Start the smallest route that can answer the current follow-up question.
Run claim-critical slices first, weighted by soundness gain under the current resource budget, and stop widening once the next route is already clear.

Useful slice classes:

- `auxiliary`: helps understand settings, thresholds, or mechanisms but does not carry the main claim by itself
- `claim-carrying`: directly affects whether the main narrative or route decision is justified
- `supporting`: broadens confidence or interpretability after the main claim is already credible

## Slice evidence contract

For each meaningful slice, define and record enough of the following to make the evidence reusable:

- research question
- hypothesis, expected pattern, or decision-relevant expectation
- intervention, ablation, variation, inspection target, or failure bucket
- controls or fixed conditions
- metric, observable, table, qualitative artifact, or rubric
- comparison target
- expected resource class or major execution constraint when it affects feasibility
- stop condition or completion condition
- evidence path expectations
- claim update
- comparability verdict
- next action

Code-based, fully automatable analysis is preferred when it is the most faithful and repeatable path.
But not every valid analysis must be fully automatable: failure-bucket inspection, qualitative artifact review, extracted-text audits, reviewer-linked example checks, or table/figure consistency checks can be valid when the evidence is concrete, sampled or scoped, and reproducible enough for the claim being made.

Do not present subjective judgment as objective measurement.
If human, model, or qualitative judgment is used, record the rubric, sample, prompt or inspection basis, caveats, and why it is sufficient for the route decision.

## Comparability contract

Comparability is a hard boundary.

- keep the same evaluation contract unless the variation is the point
- when `active_baseline_metric_contract_json` exists, read it before defining slice success criteria or comparison tables when baseline comparison matters
- when `active_baseline_metric_contract_json` exists, keep slice comparisons aligned with it unless the slice explicitly records why it differs
- state exactly what changed
- state exactly what stayed fixed
- keep naming and output paths clean enough that multiple runs can coexist

If the variation itself changes the evaluation setup, record that explicitly and do not present the run as a direct apples-to-apples comparison.

Do not bring in a new dataset as if it were the same comparison contract.
A new dataset can be valid as a generalization, external-validity, stress-test, or limitation-boundary slice, but it must be labeled that way and must not replace the accepted baseline or main comparison contract.

If a slice needs an extra comparator baseline, place it under the normal baseline roots, do not overwrite the canonical quest baseline gate, and record it back through `record_analysis_slice(..., comparison_baselines=[...])`.

## Writing-facing boundary

If analysis directly supports a paper or paper-like report, the evidence must be write-backable.
That does not always mean a selected outline must exist before any pre-outline evidence check, but paper-ready slices must map cleanly back to a selected outline, paper experiment matrix, evidence ledger, section, claim, table, or reviewer item.

For concrete paper-facing cases:

- if the slice is the only thing keeping a main-text section unsupported, make it `main_required` or `main_text`
- if the slice is useful but non-blocking, make it `appendix`
- if the slice is informative but not meant for the manuscript, keep it durable and mark it `reference_only` with a reason
- if a selected outline exists, map paper-ready slices to named `research_question` and `experimental_design` fields when those fields exist
- if `paper/paper_experiment_matrix.md` exists and the campaign is directly supporting the paper, read it before launching or reordering the slice set
- for writing-facing campaigns, prefer stable ids such as `exp_id`, `todo_id`, or `slice_id` over free-form notes
- paper-ready slices should carry the available write-back fields such as `paper_role`, `section_id`, `item_id`, and `claim_links` when those fields exist in the paper contract
- after every completed paper-ready slice, update or verify the relevant paper experiment matrix, section notes, evidence ledger, or active paper-line summary

Do not leave a slice "completed" while the paper contract still looks stale and that slice is meant to unblock the paper.
If no selected outline exists yet but the evidence question is needed to decide whether writing is worthwhile, run it as pre-outline analysis and route to `write` or `decision` afterward.

## Durable route records

Durable records are required in substance, not in fixed filenames.
The agent may choose the shortest durable form that lets a later turn resume without guessing.

For multi-slice, writing-facing, route-changing, expensive, unstable, or long-running analysis, leave a route record that states:

- parent object and parent claim
- acceptance or stop condition
- slice list or first slice frontier
- comparability boundary
- execution envelope and the slices ruled infeasible under it
- available assets and required comparators
- evidence paths or expected outputs
- current blocker or fallback
- next route after success or failure

`PLAN.md`, `CHECKLIST.md`, `paper/paper_experiment_matrix.md`, and local matrix or checklist files are allowed control surfaces, not mandatory success paths.
Use `references/campaign-plan-template.md` and `references/campaign-checklist-template.md` when they help, but do not expand them as paperwork.

If slice feasibility, ordering, comparators, or campaign interpretation changes materially, revise the durable route record before spending more compute.

## Operational guidance

The main skill keeps the control surface in front.
For the longer operational notes, read `references/operational-guidance.md`.

- use it when the route needs the exact artifact-backed campaign tactics
- use it when execution monitoring, stall handling, or slice recording details matter
- use it when memory handling or connector-facing chart notes materially affect the route

## Negative cases and stop rules

Do not treat analysis as successful when:

- slices do not map to a parent claim, parent result, paper gap, reviewer item, or decision
- a summary claims stable support without per-slice evidence
- negative, null, contradictory, failed, or partial slices are hidden
- an ablation changes many factors but is interpreted as isolating one factor
- a robustness slice changes dataset, split, or evaluation protocol but is reported as direct apples-to-apples comparison
- subjective or manual inspection supports a claim without rubric, sample, prompt, trace, or caveat
- a writing-facing slice is called paper-ready but cannot be mapped back to the paper matrix, evidence ledger, outline, claim, section, or reviewer item
- a completed paper-relevant slice remains visible only as a free-floating analysis result and is not bound back into the current paper contract
- a failed slice is silently skipped and replaced by a different slice
- the campaign keeps expanding after the next route is already clear
- the campaign scope assumes hardware, memory, or runtime that is not actually available in the current environment
- a new comparator overwrites the canonical quest baseline gate instead of being recorded as analysis-local comparison evidence
- the underlying main result is still untrusted and the proposed work is really baseline recovery or a new main experiment
- a new main experiment is disguised as an analysis slice to bypass the main-experiment gate

If two slices in a row fail to change the claim boundary, matrix frontier, or next route, stop widening the campaign and route through `decision`, `write`, `experiment`, or an explicit blocker.

Record blocked or failed campaign states explicitly, such as missing parent run, under-specified analysis question, run failure before evidence, non-comparable metrics, missing assets, missing credentials, or still-ambiguous campaign conclusion.
A blocked campaign should still name the next best action.

## Aggregation and reporting

Campaign reporting should explain:

- which findings are stable
- which findings are fragile
- what changed the interpretation of the main result
- which open questions still remain
- whether the main claim should be strengthened, weakened, narrowed, abandoned, or left ambiguous
- which slice changed the interpretation most
- which planned slices were intentionally skipped because earlier results made them low value

Focus on the highest-impact findings first.
Results matter more than process narration.
If using tables, show only the most decision-relevant rows.
Separate stable support, partial support, contradiction, and unresolved ambiguity.
When there are many slices, summarize the top `3-5` most important ones first, then point to the full evidence paths.

## Exit criteria

Exit once one of these is durably true:

- the campaign produced enough evidence for writing or decision-making
- the campaign exposed a problem that requires returning to `experiment`, `idea`, baseline recovery, or `decision`
- the campaign is blocked and the blocker is durably recorded
- the campaign route changed because the original slice set is no longer the best evidence-per-cost path

A good campaign closes when the claim got stronger, weaker, narrower, abandoned, or clearly stuck, not when more slice ideas merely remain possible.
