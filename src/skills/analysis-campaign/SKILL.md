---
name: analysis-campaign
description: Use when a quest needs one or more follow-up runs such as ablations, robustness checks, error analysis, or failure analysis after a main experiment.
skill_role: stage
---

# Analysis Campaign

Use this skill when one or more follow-up runs are needed and the quest needs a coordinated evidence campaign.
The goal is to answer a bounded follow-up evidence question, not to keep opening more slices just because they are imaginable.

This is the shared DeepScientist protocol for supplementary experiments after a durable result.
Use the same route for:

- ordinary ablations / robustness / sensitivity work
- review-driven evidence gaps
- rebuttal-driven extra experiments
- writing-driven evidence gaps

For paper-facing work, treat “analysis campaign” broadly:

- not only post-hoc interpretation
- also ablations, sensitivity checks, robustness checks, efficiency or cost checks, highlight-validation runs, and limitation-boundary work beyond the main result

Do not assume a writing-facing campaign means “analysis only”.

Do not invent a separate experiment system for those cases.

## Interaction discipline

Follow the shared interaction contract injected by the system prompt.
Keep campaign updates brief unless the evidence boundary, blocker state, or next route changed materially.
For ordinary active work, prefer a concise progress update once work has crossed roughly 6 tool calls with a human-meaningful delta, and do not drift beyond roughly 12 tool calls or about 8 minutes without a user-visible update.
For meaningful long-running slices, include the estimated next reply time or next check-in window whenever it is defensible.

## Planning surfaces

Use quest/workspace planning files only when the campaign is genuinely multi-slice, writing-facing, or route-changing; otherwise keep the active frontier small and concrete.

## Stage purpose

The analysis-campaign stage exists to test the strength, boundaries, and failure modes of a result.
It preserves the core old DeepScientist analysis-experimenter discipline:

- each analysis run should correspond to one clear question
- campaign runs should stay isolated and comparable
- negative results must remain visible
- campaign-level conclusions should be aggregated explicitly

The campaign should behave like a disciplined evidence program, not an unstructured pile of extra runs.

For campaign prioritization and writing-facing slice design, read `references/campaign-design.md`.
When the campaign is writing-facing and the mapping fields are not obvious, also read `references/writing-facing-slice-examples.md`.

## Campaign note

Start the smallest campaign that can answer the current follow-up question, run claim-critical slices first, and stop widening once the next route is already clear.

## Quick workflow

1. bind the campaign to the parent run or idea and, when writing-facing, to the selected outline
2. before launching any real slice, create `PLAN.md` and `CHECKLIST.md`
3. use `PLAN.md` as the durable charter and `CHECKLIST.md` as the living execution surface
4. run claim-critical slices first and use a bounded smoke test before long real slice runs
5. after each slice, record the result durably, including honest non-success states
6. revise the plan if slice feasibility, ordering, comparators, or campaign interpretation changes materially
7. close meaningful campaign milestones with a concise `1-2` sentence summary

## Non-negotiable rules

- Every analysis run must be code-based and fully automatable.
- Do not introduce human evaluation or subjective assessment into a campaign.
- Do not bring in a new dataset unless the quest scope explicitly changed.
- Every analysis slice must have a specific research question and a falsifiable or at least decision-relevant expectation.
- If the campaign is directly supporting a paper or paper-like report section, do not launch it until a selected outline exists.
- When a selected outline exists, every slice should map to a named `research_question` and `experimental_design` from that outline.
- When the campaign is directly supporting a paper or paper-like report, do not launch or reorder the slice set without first reading `paper/paper_experiment_matrix.md` when it exists.
- For writing-facing campaigns, every slice should correspond to a stable matrix row such as `exp_id`, not just a free-form note.
- For writing-facing campaigns, every todo item must at least carry `paper_role`, and paper-ready slices should also carry `section_id`, `item_id`, and `claim_links`.
- Do not aggregate campaign conclusions without per-run evidence.
- Do not bury null or contradictory findings.

## Use when

- writing reveals evidence gaps
- a main result needs ablations
- robustness or sensitivity needs to be checked
- a failure mode needs explanation
- efficiency or environment variation matters to the claim

## Do not use when

- the quest still lacks a credible main run or accepted baseline
- the next step is obviously another main experiment rather than follow-up evidence work

## Preconditions and gate

Before launching a campaign, confirm:

- the reference main run or accepted idea line
- the claim or question being tested
- the comparison target
- the metric or observable of interest
- the list of specific analysis questions
- the current quest / user-provided assets that each planned slice will actually use
- whether each slice is executable with the current assets, tooling, and available credentials
- for paper-facing campaigns, the current paper experiment matrix frontier and which rows are actually feasible now
- if durable state exposes `active_baseline_metric_contract_json`, read that JSON file before defining slice success criteria or comparison tables
- treat `active_baseline_metric_contract_json` as the default baseline comparison contract unless a slice is explicitly testing a different evaluation contract

If the question list is fuzzy, sharpen it before running anything.
Treat quest files, attached user assets, checkpoints, configs, extracted texts, baselines, and existing code paths as the first-choice asset pool.
Do not design slices around hypothetical resources that the current system cannot actually access or run.
If a slice cannot be executed with the current system, redesign it around available assets or explicitly report that the task cannot currently be completed.
If infeasibility appears mid-run, attempt bounded recovery first; if still blocked, record the slice with a non-success status and explain why.
If ids, active refs, or current quest state are unclear after restart, call `artifact.get_quest_state(detail='summary')` and `artifact.resolve_runtime_refs(...)` before launching or recording slices.
If the exact quest brief / plan / status wording matters for campaign scope, call `artifact.read_quest_documents(...)`.
If earlier user instructions materially affect campaign scope or ordering, call `artifact.get_conversation_context(...)` before changing the slice set.

For concrete paper-facing cases:

- if the slice is the only thing keeping a main-text section unsupported, make it `main_required` / `main_text`
- if the slice is useful but non-blocking, make it `appendix`
- if the slice is informative but not meant for the manuscript, keep it durable and mark it `reference_only` with a reason
- after every completed paper-facing slice, verify the return path immediately:
  - the matching outline `result_table` row is updated
  - the section notes are updated when the outline folder exists
  - `paper/evidence_ledger.json` reflects the new mapping
  - the active paper line summary no longer treats that slice as missing

Do not leave a slice "completed" while the paper contract still looks stale.

Two follow-up tiers are acceptable:

- `analysis-lite`
  - one clear follow-up question
  - one slice or a very small slice set
  - no heavy charter beyond a compact control-surface update unless the route changes
- `full campaign`
  - multiple slices, writing-facing evidence, or a result that genuinely changes the parent route
  - use the fuller `PLAN.md` / `CHECKLIST.md` / matrix contract

## Required plan and checklist

Before launching any real campaign slice, create a quest-visible `PLAN.md` and `CHECKLIST.md`.

- Use `references/campaign-plan-template.md` as the canonical structure for `PLAN.md`.
- Use `references/campaign-checklist-template.md` as the canonical structure for `CHECKLIST.md`.
- `PLAN.md` and `CHECKLIST.md` should be the canonical campaign-control surface during execution.
- `PLAN.md` should cover the claim under test, slice table, comparability boundary, available assets, required comparators, smoke and main-run strategy, monitoring and sleep rules, reporting expectations, and a revision log.
- If slice feasibility, ordering, comparators, or campaign interpretation changes materially, revise `PLAN.md` before continuing.

## Truth sources

Use:

- main experiment artifacts
- baseline artifacts
- `active_baseline_metric_contract_json` when available
- recent decisions and milestone reports
- code and configs used in the accepted main line
- actual analysis outputs and logs
- `bash_exec` session ids and managed shell logs for campaign runs

Do not summarize a campaign from impressions alone.

## Durable outputs note

The campaign should leave behind durable slice results, one campaign-level summary, and one explicit next-step decision.

## Workflow

### 0. Launch the campaign durably

Before launching any slice, record the campaign start durably and make the first slice or slice set explicit.

### 0.1 Bind the campaign to the selected outline when writing-facing

If the campaign exists to support a paper or paper-like report:

- do not proceed until one selected outline exists
- if no selected outline exists yet, route to `write` or `decision` first so the outline can be created and selected durably
- before deciding the slice list, create or refresh `paper/paper_experiment_matrix.md` when it is missing or stale
- treat that matrix as the upstream paper experiment contract, not `todo_items` alone
- do not start stable experiments-section drafting while currently feasible non-optional matrix rows remain unresolved
- make every writing-facing slice mappable back into the selected outline or paper experiment matrix before treating it as paper-ready

### 1. Define the campaign charter

State:

- campaign id
- parent run or parent idea
- main claim under test
- list of analysis questions
- what will be held fixed
- what may vary

If there are many possible slices, order them by decision value:

1. most claim-critical ablation or contradiction check
2. strongest robustness or sensitivity checks
3. failure-mode explanation
4. efficiency or secondary supporting analyses

Do not spend half the campaign budget on secondary slices before the claim-critical ones run.
When the parent line is still below `solid` evidence quality, use the campaign first to move it from `minimum` to `solid` before chasing broader polish.

### 2. Split into isolated analysis runs

Each analysis run should correspond to one need, such as:

- remove one component
- vary one hyperparameter family
- run additional seeds
- inspect one failure bucket
- test one environment variation
- measure one efficiency or cost dimension
- validate one highlight hypothesis

Avoid changing many factors at once unless the campaign is explicitly exploratory.

For each slice, define at minimum:

- research question
- hypothesis or expected pattern
- intervention
- controls or fixed conditions
- metric or observable
- stop condition
- evidence path expectations
- `required_baselines` when the slice depends on an extra comparator that is not yet available in the quest
- `slice_class`, such as `auxiliary`, `claim-carrying`, or `supporting`

If a slice needs an extra comparator baseline, place it under the normal baseline roots, do not overwrite the canonical quest baseline gate, and record it back through `record_analysis_slice(..., comparison_baselines=[...])`.

Create the campaign with `artifact.create_analysis_campaign(...)` before starting any slice.
Even one extra experiment can still be represented as a one-slice campaign when durable lineage matters.
Use a one-slice campaign when the slice should appear as a real child node in Git or Canvas.
Branch that campaign from the current workspace/result node rather than mutating the completed parent node in place.
That tool should receive the slice list, and each returned slice worktree becomes the required execution location for that slice.
Only create the campaign after you have verified that the listed slices are actually executable with the current quest assets and runtime.
When the campaign is writing-facing, the same call should also carry `selected_outline_ref`, `research_questions`, `experimental_designs`, and `todo_items`.
If ids or refs are unclear, recover them first with `artifact.resolve_runtime_refs(...)`, `artifact.get_analysis_campaign(...)`, or `artifact.list_paper_outlines(...)` instead of guessing.
Treat `campaign_id` as system-owned, and treat `slice_id` / `todo_id` as agent-authored semantic ids.
After each slice finishes, call `artifact.record_analysis_slice(...)` immediately so the result is mirrored back to the parent branch and the next slice can be activated.
If a slice fails or becomes infeasible, still call `artifact.record_analysis_slice(...)` with an honest non-success status plus the real blocker and next recommendation; do not leave the campaign state ambiguous.
For slice recording, `deviations` and `evidence_paths` are optional context fields, not mandatory ceremony; include them only when they materially help explanation or auditability.
Each `artifact.record_analysis_slice(...)` call should also include an `evaluation_summary` with exactly these six fields:

- `takeaway`
- `claim_update`
- `baseline_relation`
- `comparability`
- `failure_mode`
- `next_action`

Use those six fields to keep each slice readable at a glance from Canvas, stage tabs, review, and rebuttal.
The longer prose still matters, but the six-field summary is the stable routing summary.

For writing-facing campaigns, prefer running `claim-carrying` slices before `supporting` slices unless an auxiliary check is required to make the main slice interpretable.
If two slices in a row fail to change the claim boundary, matrix frontier, or next route, stop widening the campaign and route through `decision` or `write`.

For slices that are longer than a quick validation:

- treat smoke work as a `0-2` budget, not as an automatic mandatory phase
- use a smoke test when the slice command, outputs, or metric path are still uncertain
- once the smoke passes, launch the real slice with `bash_exec(mode='detach', ...)`
- `bash_exec(mode='read', id=...)` returns the full rendered log when it is 2000 lines or fewer; for longer logs it returns the first 500 lines plus the last 1500 lines and a hint to inspect omitted sections with `start` and `tail`
- if you need a middle section that was omitted from that default preview, use `bash_exec(mode='read', id=..., start=..., tail=...)`
- monitor with `bash_exec(mode='read', id=..., tail_limit=..., order='desc')`
- after the first read, prefer `bash_exec(mode='read', id=..., after_seq=last_seen_seq, tail_limit=..., order='asc')` for incremental monitoring
- if ids become unclear, recover them through `bash_exec(mode='history')`
- use `silent_seconds`, `progress_age_seconds`, `signal_age_seconds`, and `watchdog_overdue` as the default stall checks
- if a slice is invalid, wedged, or superseded, stop it with `bash_exec(mode='kill', id=..., wait=true, timeout_seconds=...)`
- if you only need wall-clock waiting between checks, use the canonical sleep choice:
  - `bash_exec(command='sleep N', mode='await', timeout_seconds=N+buffer, ...)`
  - do not set `timeout_seconds` exactly equal to `N`
  - if you are waiting on an already running session, prefer `bash_exec(mode='await', id=..., timeout_seconds=...)` instead of starting a new sleep command
- when you control the slice code, prefer a throttled `tqdm` progress reporter and concise structured progress markers when feasible
- if the same failure class appears again without a real route or evidence change, stop widening the campaign and route through `decision`

### 3. Keep comparability

Comparability rules:

- keep the same evaluation contract unless the variation is the point
- when `active_baseline_metric_contract_json` exists, keep slice comparisons aligned with it unless the slice explicitly records why it differs
- state exactly what changed
- state exactly what stayed fixed
- keep naming and output paths clean so multiple runs can coexist

If the variation itself changes the evaluation setup, record that explicitly and do not present the run as a direct apples-to-apples comparison.

### 4. Record each analysis slice

Before a long slice starts, emit a `progress` artifact or `artifact.interact(kind='progress', ...)` update so the quest shows that the slice is active.

For each run, record:

- analysis question
- intervention
- metric or qualitative evidence
- whether the result strengthens, weakens, or complicates the claim
- paths to the evidence

Preferred per-slice summary shape:

- question
- implementation change
- main metric delta
- interpretation
- caveats

If a slice fails before producing evidence, still record it as a failed or partial `run` artifact rather than silently skipping it.

When a slice materially changes the recommended route or weakens the main claim, do not wait until the final synthesis to mention it.
Send a threaded `artifact.interact(kind='milestone', ...)` update at that point with the new boundary or risk.

### 5. Aggregate the campaign

The campaign report should explain:

- which findings are stable
- which findings are fragile
- what changed the interpretation of the main result
- which open questions still remain

Campaign reporting rules:

- focus on the highest-impact findings first
- results matter more than process narration
- if using tables, show only the most decision-relevant rows
- separate stable support, partial support, contradiction, and unresolved ambiguity

When there are many slices, summarize the top `3-5` most important ones first, then point to the full evidence paths.

The aggregated report should also answer whether the main claim should be strengthened, weakened, narrowed, or abandoned, which slice changed the interpretation most, and which planned slices were intentionally skipped because earlier results made them low value.

### 6. Route the next step

A campaign should end with an explicit next move:

- continue the campaign
- return to `experiment`
- move to `write`
- stop or reset the current line

Record the post-campaign route as a `decision` artifact.

## Analysis-quality rules

Good campaign behavior:

- one clear question per run
- one-factor-at-a-time changes when possible
- clear comparison against the accepted reference line
- visibility of null and negative findings
- a logically ordered suite rather than a random batch

Weak campaign behavior:

- hidden scope expansion
- many untracked simultaneous changes
- campaign summary without per-run evidence
- ignoring contradictory analysis results
- reporting every minor slice with equal weight instead of prioritizing the important ones

## Memory note

Use memory only to avoid repeating known failures or to preserve reusable campaign lessons, not as a required step before every slice.

Stage-start requirement:

- begin every analysis campaign pass with `memory.list_recent(scope='quest', limit=5)`
- then run at least one analysis-relevant `memory.search(...)` before launching or resuming slices

Stage-end requirement:

- if the campaign produced a durable cross-slice lesson, failure pattern, or comparability caveat, write at least one `memory.write(...)` before leaving the stage

## Artifact note

Record the campaign launch, each slice result, the campaign-level summary, and the closing route decision through the existing artifact surface.

## Failure and blocked handling

Record blocked or failed campaign states explicitly, such as missing parent run, under-specified analysis question, run failure before evidence, non-comparable metrics, or still-ambiguous campaign conclusion.
A blocked campaign should still name the next best action.

## Exit criteria

Exit the analysis-campaign stage once one of the following is durably true:

- the campaign produced enough evidence for writing or decision-making
- the campaign exposed a problem that requires returning to `experiment` or `idea`
- the campaign is blocked and the blocker is durably recorded

A good campaign closes when the claim got stronger, weaker, or clearly stuck, not when more slice ideas merely remain possible.
