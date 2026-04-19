---
name: analysis-campaign
description: Use when a quest needs one or more follow-up runs such as ablations, robustness checks, error analysis, or failure analysis after a main experiment.
skill_role: stage
---

# Analysis Campaign

Use this skill when follow-up evidence is needed after a durable result.
The goal is to answer a bounded evidence question, not to keep opening more slices just because they are imaginable.

This is the shared DeepScientist protocol for supplementary experiments after a durable result.
Use the same route for:

- ordinary ablations / robustness / sensitivity work
- review-driven evidence gaps
- rebuttal-driven extra experiments
- writing-driven evidence gaps

For paper-facing work, treat "analysis campaign" broadly:

- not only post-hoc interpretation
- also ablations, sensitivity checks, robustness checks, efficiency or cost checks, highlight-validation runs, and limitation-boundary work beyond the main result

Do not invent a separate experiment system for those cases.

## Interaction discipline

Follow the shared interaction contract injected by the system prompt.
Keep campaign updates brief unless the evidence boundary, blocker state, cost, or next route changed materially.
For ordinary active work, prefer a concise progress update once work has crossed roughly 6 tool calls with a human-meaningful delta, and do not drift beyond roughly 12 tool calls or about 8 minutes without a user-visible update.
For meaningful long-running slices, include the estimated next reply time or next check-in window whenever it is defensible.

## Authority and freedom

The agent owns the analysis path.
It may choose a one-slice check, a lightweight durable report, an artifact-backed one-slice campaign, a full multi-slice campaign, or a writing-facing campaign.
It may choose slice order, workspace layout, filenames, monitoring strategy, and whether a smoke test, direct verification, or full run is the right first move.

Do not treat `PLAN.md`, `CHECKLIST.md`, `artifact.create_analysis_campaign(...)`, one-slice campaigns, returned worktrees, `evaluation_summary`, smoke tests, detached runs, or paper-matrix updates as universal required paths.
They are tactics.
The hard requirement is traceable evidence that changes, confirms, or blocks the evidence boundary of the parent claim and leaves an explicit next route.

Use the artifact-backed campaign path when durable lineage, branch/worktree isolation, Canvas visibility, paper/rebuttal traceability, or multiple slices matter.
Use a lighter durable report when one bounded answer is enough and extra campaign overhead would not improve trust, routing, or auditability.

Do not treat `PLAN.md`, `CHECKLIST.md`, paper-matrix files, smoke tests, detached runs, `tqdm`, or a fixed phase order as required paths.
They are tactics.
The hard requirement is traceable slice-level evidence that changes, confirms, or blocks the evidence boundary of the parent claim and leaves an explicit next route.

The analysis-campaign stage exists to test the strength, boundaries, and failure modes of a result.
It should answer whether a parent claim should be strengthened, weakened, narrowed, abandoned, or left ambiguous.

Good analysis behavior:

- one clear question per run when possible
- isolated and comparable changes when possible
- explicit visibility of null, negative, partial, failed, and contradictory findings
- campaign-level conclusions aggregated from per-slice evidence
- stopping once the next route is clear

Weak analysis behavior:

- hidden scope expansion
- many untracked simultaneous changes
- campaign summary without per-run evidence
- ignoring contradictory analysis results
- reporting every minor slice with equal weight instead of prioritizing important ones
- continuing only because more slice ideas remain possible

For campaign prioritization and writing-facing slice design, read `references/campaign-design.md`.
When the campaign is writing-facing and the mapping fields are not obvious, also read `references/writing-facing-slice-examples.md`.
For artifact examples and edge-case examples, also read `references/artifact-flow-examples.md` and `references/boundary-cases.md`.

Do not aggregate campaign conclusions without per-run evidence.
Do not bury null or contradictory findings.

- writing reveals evidence gaps
- a main result needs ablations
- robustness or sensitivity needs to be checked
- a failure mode needs explanation
- efficiency or environment variation matters to the claim
- reviewer or rebuttal pressure needs extra evidence

Use the lightest route that preserves trust and downstream utility, including efficiency or cost questions when they affect the claim.

- the quest still lacks a credible main run or accepted baseline and the analysis would depend on that missing reference
- the next step is obviously another main experiment rather than follow-up evidence work
- the proposed slice does not connect to a parent claim, parent result, paper gap, reviewer item, or route decision

## Hard success gates

An analysis campaign succeeds when it changes or confirms the evidence boundary of a parent claim with traceable slice-level evidence, preserves comparability or records why comparability broke, and leaves a durable next-route decision.

Before treating analysis as successful, all applicable gates must be true:

- the parent object is explicit, such as a main run, accepted idea line, paper gap, reviewer item, or rebuttal item
- the claim, question, failure mode, or decision being tested is explicit
- every launched slice has a durable outcome: completed, partial, failed, blocked, infeasible, or superseded
- every evidence-bearing slice records the question, intervention or inspection target, fixed conditions, metric or observable, evidence path, claim update, comparability verdict, and next action
- null, negative, failed, partial, and contradictory findings remain visible
- campaign-level interpretation is derived from per-slice evidence rather than impressions
- the next route is explicit: continue campaign, return to `experiment`, return to `idea`, move to `write`, route through `decision`, stop, reset, or record a blocker

Do not aggregate campaign conclusions without per-run evidence.
Do not bury null or contradictory findings.

## Analysis routes

Use the lightest route that preserves trust and downstream utility.

- `analysis-lite`: one clear follow-up question, one slice or very small slice set, and a compact durable result
- `artifact-backed campaign`: one or more slices that need durable lineage, branch/worktree isolation, Canvas visibility, or later replay
- `writing-facing campaign`: evidence directly supports a selected outline, paper experiment matrix, evidence ledger, section, claim, or table
- `review/rebuttal campaign`: evidence directly answers reviewer pressure or audit findings
- `failure-analysis route`: evidence explains why a result failed, diverged, or became non-comparable

Start the smallest route that can answer the current follow-up question.
Run claim-critical slices first and stop widening once the next route is already clear.

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

- if the slice is the only thing keeping a main-text section unsupported, make it `main_required` / `main_text`
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
- available assets and required comparators
- evidence paths or expected outputs
- current blocker or fallback
- next route after success or failure

`PLAN.md`, `CHECKLIST.md`, `paper/paper_experiment_matrix.md`, and local matrix/checklist files are allowed control surfaces, not mandatory success paths.
Use `references/campaign-plan-template.md` and `references/campaign-checklist-template.md` when they help, but do not expand them as paperwork.

If slice feasibility, ordering, comparators, or campaign interpretation changes materially, revise the durable route record before spending more compute.

## Artifact tactics

Use `artifact.create_analysis_campaign(...)` when durable lineage or slice-level branch/worktree state matters.
Even one extra experiment can still be represented as a one-slice campaign when durable lineage matters.
Use a one-slice campaign when the slice should appear as a real child node in Git or Canvas, or when review/rebuttal/paper traceability benefits from the campaign object.

If `artifact.create_analysis_campaign(...)` returns slice worktrees, run each returned slice in its returned workspace unless there is a concrete reason to switch and record that reason.
Branch that campaign from the current workspace/result node rather than mutating the completed parent node in place when lineage matters.
Only create the campaign after you have verified that the listed slices are executable with the current quest assets and runtime, or explicitly mark infeasible slices as such.

When the campaign is writing-facing, the create call should carry available paper-mapping fields such as `selected_outline_ref`, `research_questions`, `experimental_designs`, and `todo_items` when they exist and matter.
If ids or refs are unclear, recover them first with `artifact.resolve_runtime_refs(...)`, `artifact.get_analysis_campaign(...)`, `artifact.get_quest_state(...)`, or `artifact.list_paper_outlines(...)` instead of guessing.
Treat `campaign_id` as system-owned, and treat `slice_id` / `todo_id` as agent-authored semantic ids.

After each launched slice finishes, fails, or becomes infeasible, call `artifact.record_analysis_slice(...)` or otherwise record the same durable truth through the artifact surface immediately.
If a slice fails or becomes infeasible, still record an honest non-success status plus the real blocker and next recommendation; do not leave the campaign state ambiguous.

For slice recording, `deviations` and `evidence_paths` are context fields, not mandatory ceremony; include them when they materially help explanation or auditability.
An `evaluation_summary` is the preferred stable routing summary for UI, Canvas, review, and rebuttal.
When useful, include these fields:

- `takeaway`
- `claim_update`
- `baseline_relation`
- `comparability`
- `failure_mode`
- `next_action`

The longer prose still matters, but the summary should make the slice readable at a glance.

## Execution tactics

Use whatever execution route is most faithful, observable, and efficient while preserving the hard gates.

- A bounded smoke test is useful when the slice command, outputs, metric path, or evaluator wiring is uncertain.
- Treat smoke work as a `0-2` default budget, not as an automatic mandatory phase.
- If the path is already concrete, go straight to direct verification or the real slice.
- If runtime is uncertain or likely long, prefer `bash_exec(mode='detach', ...)` plus managed monitoring.
- `bash_exec(mode='read', id=...)` returns the full rendered log when it is 2000 lines or fewer; for longer logs it returns the first 500 lines plus the last 1500 lines and a hint to inspect omitted sections with `start` and `tail`.
- If you need a middle section that was omitted from that default preview, use `bash_exec(mode='read', id=..., start=..., tail=...)`.
- Monitor with `bash_exec(mode='read', id=..., tail_limit=..., order='desc')`.
- After the first read, prefer `bash_exec(mode='read', id=..., after_seq=last_seen_seq, tail_limit=..., order='asc')` for incremental monitoring.
- If ids become unclear, recover them through `bash_exec(mode='history')`.
- Use `silent_seconds`, `progress_age_seconds`, `signal_age_seconds`, and `watchdog_overdue` as stall checks when they are available.
- If a slice is invalid, wedged, or superseded, stop it with `bash_exec(mode='kill', id=..., wait=true, timeout_seconds=...)`.
- If you only need wall-clock waiting between checks, use the canonical sleep choice:
  - `bash_exec(command='sleep N', mode='await', timeout_seconds=N+buffer, ...)`
  - do not set `timeout_seconds` exactly equal to `N`
  - if you are waiting on an already running session, prefer `bash_exec(mode='await', id=..., timeout_seconds=...)` instead of starting a new sleep command
- when you control the slice code, prefer a throttled `tqdm` progress reporter and concise structured progress markers when feasible
- if the same failure class appears again without a real route or evidence change, stop widening the campaign and route through `decision`

## Negative cases and stop rules

Do not treat analysis as successful when:

- slices do not map to a parent claim, parent result, paper gap, reviewer item, or decision
- a summary claims stable support without per-slice evidence
- negative, null, contradictory, failed, or partial slices are hidden
- an ablation changes many factors but is interpreted as isolating one factor
- a robustness slice changes dataset, split, or evaluation protocol but is reported as direct apples-to-apples comparison
- subjective or manual inspection supports a claim without rubric, sample, prompt, trace, or caveat
- a writing-facing slice is called paper-ready but cannot be mapped back to the paper matrix, evidence ledger, outline, claim, section, or reviewer item
- a failed slice is silently skipped and replaced by a different slice
- the campaign keeps expanding after the next route is already clear
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

## Memory note

Use memory only to avoid repeating known failures or to preserve reusable campaign lessons, not as a required step before every slice.

Stage-start requirement:

- begin an analysis campaign pass with `memory.list_recent(scope='quest', limit=5)` when resuming, reopening old command paths, or prior campaign lessons are likely to matter
- run targeted `memory.search(...)` before launching or resuming slices when repeated failures, prior slice outcomes, or comparability caveats may affect the route

Stage-end requirement:

- if the campaign produced a durable cross-slice lesson, failure pattern, or comparability caveat, write at least one `memory.write(...)` before leaving the stage

## Exit criteria

Exit once one of these is durably true:

- the campaign produced enough evidence for writing or decision-making
- the campaign exposed a problem that requires returning to `experiment`, `idea`, baseline recovery, or `decision`
- the campaign is blocked and the blocker is durably recorded
- the campaign route changed because the original slice set is no longer the best evidence-per-cost path

A good campaign closes when the claim got stronger, weaker, narrower, abandoned, or clearly stuck, not when more slice ideas merely remain possible.
