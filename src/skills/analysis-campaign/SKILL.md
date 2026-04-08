---
name: analysis-campaign
description: Use when a quest needs one or more follow-up runs such as ablations, robustness checks, error analysis, or failure analysis after a main experiment.
skill_role: stage
---

# Analysis Campaign

Use this skill when one or more follow-up runs are needed and the quest needs a coordinated evidence campaign.

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

- Follow the shared interaction contract injected by the system prompt.
- For ordinary active work, prefer a concise progress update once work has crossed roughly 6 tool calls with a human-meaningful delta, and do not drift beyond roughly 12 tool calls or about 8 minutes without a user-visible update.
- Hard execution rule: every terminal command in this stage must go through `bash_exec`; do not use any other terminal path for slice execution, smoke tests, Git, Python, package-manager, or file-inspection commands.
- Prefer `bash_exec` for campaign slice commands so each run has a durable session id, quest-local log folder, and later `read/list/kill` control.
- Keep ordinary subtask completions concise. When an analysis campaign or a stage-significant campaign checkpoint is complete, upgrade to a richer `artifact.interact(kind='milestone', reply_mode='threaded', ...)` report.
- That richer campaign milestone report should normally cover: which slices completed, the main takeaway, whether the claim got stronger or weaker, and the exact recommended next route.
- That richer milestone report is still normally non-blocking. If the post-campaign route is already clear, continue automatically after reporting instead of waiting for explicit acknowledgment.
- If the active communication surface is QQ and QQ milestone media is enabled in config, prefer at most one aggregated campaign summary PNG on a meaningful campaign milestone.
- That attachment should summarize the campaign as a whole; do not auto-send one image per slice.
- Treat connector-facing campaign PNGs as report charts, not draft paper figures.
- Preferred connector-chart palettes are Morandi-like and restrained:
  - `sage-clay`: `#E7E1D6`, `#B7A99A`, `#7F8F84` for the default aggregated campaign summary
  - `mist-stone`: `#F3EEE8`, `#D8D1C7`, `#8A9199` for conservative or uncertainty-heavy summaries
  - `dust-rose`: `#F2E9E6`, `#D8C3BC`, `#B88C8C` only as a secondary accent when an extra comparison is necessary
- Connector-facing campaign chart requirements:
  - one campaign-level message, not a crowded slice dashboard
  - low saturation and limited color count
  - clear aggregation labels and direct comparison against the main run or baseline
  - prefer one summary figure that communicates the boundary change honestly
- Preferred campaign summaries are:
  - point-range or bar summaries for slice-to-slice endpoint comparisons
  - line plots only when the x-axis is truly ordered and comparable across slices
  - small multiples instead of one rainbow figure when slices answer different questions
- If a campaign view uses continuous color, keep it sequential for ordered magnitude and diverging only for signed deltas around a meaningful center.
- Avoid rainbow / jet-like maps and decorative heatmaps when a simpler comparison plot would communicate the result better.
- Keep the same muted palette semantics across the full campaign so the same color means the same role in every slice summary.
- If a campaign figure is milestone-facing, paper-facing, or otherwise durable, open `figure-polish/SKILL.md` and complete its render-inspect-revise pass before treating the figure as final.
- If plotting in Python, reuse the fixed Morandi plotting starter from the system prompt and keep the same palette discipline across the whole campaign.
- If the runtime starts an auto-continue turn with no new user message, resume from the current campaign state and active requirements instead of replaying the previous user turn.
- Progress message templates are references only. Adapt to the actual context and vary wording so messages feel human, respectful, and non-robotic.
- If a threaded user reply arrives, interpret it relative to the latest campaign progress update before assuming the task changed completely.

## Three-layer todo contract

- keep quest-root `plan.md` as the quest-level research map and parent loop tracker
- keep workspace `PLAN.md` as the current campaign-node charter
- keep workspace `CHECKLIST.md` as the campaign execution frontier; when writing-facing `todo_items` exist, treat them as the bottom-layer frontier rather than as a second parallel planning system
- if the frontier stops changing across repeated passes, revise the campaign node or route instead of opening nested slice subtrees in chat

## Research-map role

- an analysis campaign is a subordinate evidence node under a parent experiment or paper-facing loop state
- finishing or blocking a campaign should update quest-root `plan.md` with the next edge back to write, decision, another experiment node, or stop

## Stage purpose

The analysis-campaign stage exists to test the strength, boundaries, and failure modes of a result.
It preserves the core old DeepScientist analysis-experimenter discipline:

- each analysis run should correspond to one clear question
- campaign runs should stay isolated and comparable
- negative results must remain visible
- campaign-level conclusions should be aggregated explicitly

The campaign should behave like a disciplined evidence program, not an unstructured pile of extra runs.

For campaign prioritization and writing-facing slice design, read `references/campaign-design.md`.
When the campaign is paper-facing and the mapping fields are not obvious, also read `references/writing-facing-slice-examples.md`.

## Quick workflow

Treat this as the compressed campaign map. The authoritative slice protocol and aggregation rules remain in `Workflow`.

1. Bind the campaign to the parent run or idea and, when writing-facing, to the selected outline.
2. When the campaign is writing-facing, refresh `paper/paper_experiment_matrix.*` before freezing the slice frontier.
3. Before launching slices, create `PLAN.md` and `CHECKLIST.md`.
4. Use `PLAN.md` as the durable charter and `CHECKLIST.md` as the living execution surface while launching, monitoring, recording, and aggregating slices.
5. Run claim-critical slices first and smoke-test long slices before their real runs.
6. Revise the plan and matrix if slice feasibility, ordering, comparators, or campaign interpretation changes materially, and record every slice durably, including honest non-success states.
7. Close meaningful campaign milestones with a concise `1-2` sentence summary that says whether the claim gained stable support, partial support, contradiction, or unresolved ambiguity, what the matrix frontier now looks like, and what happens next.

## Non-negotiable rules

- Every analysis run must be code-based and fully automatable.
- Do not introduce human evaluation or subjective assessment into a campaign.
- Do not bring in a new dataset unless the quest scope explicitly changed.
- Every analysis slice must have a specific research question and a falsifiable or at least decision-relevant expectation.
- If the campaign is supporting a paper or paper-like report, do not launch it until a selected outline exists.
- When a selected outline exists, every slice should map to a named `research_question` and `experimental_design` from that outline.
- When the campaign is supporting a paper or paper-like report, do not launch or reorder the slice set without first reading `paper/paper_experiment_matrix.md` when it exists.
- For writing-facing campaigns, every slice should correspond to a stable matrix row such as `exp_id`, not just a free-form note.
- For writing-facing campaigns, every todo item must also carry `section_id`, `item_id`, `claim_links`, and `paper_role`; otherwise the slice is not paper-ready.
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

## Required plan and checklist

Before launching any real campaign slice, create a quest-visible `PLAN.md` and `CHECKLIST.md`.

- Use `references/campaign-plan-template.md` as the canonical structure for `PLAN.md`.
- Use `references/campaign-checklist-template.md` as the canonical structure for `CHECKLIST.md`.
- keep quest-root `plan.md` synced with the parent experiment or paper-facing node and the campaign's actual next edge
- `PLAN.md` is the durable campaign charter and should cover the claim under test, slice table, comparability boundary, available assets, required comparators, smoke and main-run strategy, monitoring and sleep rules, reporting expectations, and a revision log.
- `CHECKLIST.md` is the living campaign execution list; update it during launch, asset preparation, slice execution, aggregation, and route changes.
- If slice ordering, feasibility, required baselines, campaign interpretation, or the writing-facing outline mapping changes materially, revise `PLAN.md` before continuing.
- The later charter report, slice artifacts, and aggregate report remain required, but `PLAN.md` and `CHECKLIST.md` should be the canonical campaign-control surface during execution.

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

## Required durable outputs

A campaign should usually leave behind:

- a campaign identifier
- a selected outline reference when the campaign is writing-facing
- a refreshed `paper/paper_experiment_matrix.md`
- a refreshed `paper/paper_experiment_matrix.json`
- one directory per analysis run
- any supplementary baseline reproduced for analysis under `baselines/local/<baseline_id>/` or attached under `baselines/imported/<baseline_id>/`
- one quest-level supplementary baseline inventory at `artifacts/baselines/analysis_inventory.json`
- one run artifact per analysis slice
- one outline-bound todo manifest when the campaign is writing-facing
- an aggregated campaign report
- a decision about the next move

In the current runtime, represent that with existing artifact actions only:

- one `decision` artifact with `action='launch_analysis_campaign'`
- one charter `report`
- one `run` artifact per slice
- optional `progress` artifacts during execution
- one aggregated `report`
- one closing `decision`

## Workflow

### 0. Launch the campaign durably

Before launching any slice, record the campaign start through artifacts:

1. write a `decision` artifact with:
   - `action='launch_analysis_campaign'`
   - `campaign_id`
   - `parent_run_id` or `parent_idea_id`
   - why the campaign is needed now
2. write a charter `report` with the planned slice list
3. update `plan.md` if the campaign materially changes the quest path

Do not start a multi-slice campaign from chat-only intent.
Do not start it from chat-only intent plus vague notes either: write `PLAN.md` and `CHECKLIST.md` first, using `references/campaign-plan-template.md` and `references/campaign-checklist-template.md` as the default structures.

After the charter and launch decision are durably recorded, send one threaded `artifact.interact(kind='milestone', ...)` update naming:

- why the campaign exists now
- the claim-critical slices that will run first
- the first thing the user should expect from the campaign
- the first real checkpoint for the user
- if the active surface is QQ, keep that campaign-launch milestone text-first unless a single summary image is already genuinely useful

### 0.1 Bind the campaign to the selected outline when writing-facing

If the campaign exists to support a paper or paper-like report:

- do not proceed until one selected outline exists
- if no selected outline exists yet, route to `write` or `decision` first so the outline can be created and selected durably
- before deciding the slice list, create or refresh `paper/paper_experiment_matrix.md` when it is missing or stale
- treat that matrix as the upstream paper experiment contract, not `todo_items` alone
- use the matrix to decide:
  - which rows are `main_required`
  - which are `main_optional`
  - which are appendix-only
  - which are optional or should be dropped
- do not start stable experiments-section drafting while currently feasible non-optional matrix rows remain unresolved
- call `artifact.create_analysis_campaign(...)` with:
  - `selected_outline_ref`
  - `research_questions`
  - `experimental_designs`
  - `todo_items`
- ensure each todo item names at least:
  - `exp_id`
  - `todo_id`
  - `slice_id`
  - `title`
  - `research_question`
  - `experimental_design`
  - `tier`
  - `paper_placement`
  - `completion_condition`

For writing-facing campaigns, every slice should also carry paper-contract identity, not just free-form text:

- `section_id`
- `item_id`
- `claim_links`
- `paper_role`

Do not treat a completed analysis slice as paper-ready until those fields exist and the slice is mappable back into the selected outline or paper experiment matrix.
Use `references/writing-facing-slice-examples.md` when the correct field values are not obvious.

This keeps the analysis campaign aligned with the paper plan instead of becoming a free-floating batch of slices.

### 1. Define the campaign charter

State:

- campaign id
- parent run or parent idea
- main claim under test
- list of analysis questions
- what will be held fixed
- what may vary

The charter should also include:

- campaign type priority order
- expected slice count
- dependency structure between slices
- the matrix path and current execution frontier
- whether any slice requires isolated code changes or only reruns/config changes
- the top-level success condition for ending the campaign
- the top-level abandonment condition for stopping it early

Prefer to keep this charter in `PLAN.md` first and mirror the execution frontier in `CHECKLIST.md`.

For each analysis question, also state:

- why it matters to the main claim
- whether it exists mainly to support a core claim, validate a highlight, answer an efficiency or cost concern, or bound a limitation
- what result would strengthen the claim
- what result would weaken or complicate the claim
- whether the run is:
  - ablation
  - robustness
  - sensitivity
  - error analysis
  - efficiency
  - environment variation

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

Recommended extra per-slice fields:

- `exp_id`
- `slice_id`
- `run_kind`
- `slice_class`, such as `auxiliary`, `claim-carrying`, or `supporting`
- `tier`, such as `main_required`, `main_optional`, `appendix`, or `optional`
- `paper_placement`
- `highlight_ids`
- `required_baselines`, where each item records at least `baseline_id` plus the reason, benchmark, and split when known

If a slice needs an extra comparator baseline:

- reproduce it under `baselines/local/<baseline_id>/` unless it is attached under `baselines/imported/<baseline_id>/`
- keep the usual durable baseline notes there, including `analysis_plan.md`, `setup.md`, `execution.md`, and `verification.md`
- do not overwrite the canonical quest baseline gate just because an analysis slice needed a supplementary baseline
- after the comparator is ready, record it back through `record_analysis_slice(..., comparison_baselines=[...])` with its `baseline_id`, path, benchmark/split, and metrics summary
- `parent_run_id`
- whether a code diff is required
- whether an isolated branch/worktree is required
- quantitative success criteria
- quantitative abandonment criteria
- contingency trigger for the next slice

Recommended `run_kind` naming in the current runtime:

- `analysis.ablation`
- `analysis.robustness`
- `analysis.sensitivity`
- `analysis.error`
- `analysis.efficiency`
- `analysis.environment`

Create the campaign with `artifact.create_analysis_campaign(...)` before starting any slice.
Even one extra experiment should still be represented as a one-slice campaign so Git and Canvas show a real child node.
Branch that campaign from the current workspace/result node rather than mutating the completed parent node in place.
That tool should receive the full slice list, and each returned slice worktree becomes the required execution location for that slice.
Only create the campaign after you have verified that the listed slices are actually executable with the current quest assets and runtime.
When the campaign is writing-facing, the same call should also carry `selected_outline_ref`, `research_questions`, `experimental_designs`, and `todo_items`.
If ids or refs are unclear, recover them first with `artifact.resolve_runtime_refs(...)`, `artifact.get_analysis_campaign(...)`, or `artifact.list_paper_outlines(...)` instead of guessing.
Treat `campaign_id` as system-owned, and treat `slice_id` / `todo_id` as agent-authored semantic ids.
Do not replace the normal campaign flow with repeated manual `artifact.prepare_branch(...)` calls.
After each slice finishes, call `artifact.record_analysis_slice(...)` immediately so the result is mirrored back to the parent branch and the next slice can be activated.
If a slice fails or becomes infeasible, still call `artifact.record_analysis_slice(...)` with an honest non-success status plus the real blocker and next recommendation; do not leave the campaign state ambiguous.
After every completed, excluded, or blocked writing-facing slice:

- reopen `paper/paper_experiment_matrix.md`
- update the row status, feasibility, and result artifacts
- update whether the row now belongs in main text, appendix, or omission
- update the remaining execution frontier before choosing the next slice

Do not keep launching writing-facing slices from stale memory when the matrix has changed.
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

For slices that run longer than a quick smoke check:

- first run a bounded smoke test so the slice command, outputs, and metric path are validated cheaply
- once the smoke test passes, launch the real slice with `bash_exec(mode='detach', ...)` and normally leave `timeout_seconds` unset for that long run
- `bash_exec(mode='read', id=...)` returns the full rendered log when it is 2000 lines or fewer; for longer logs it returns the first 500 lines plus the last 1500 lines and a hint to inspect omitted sections with `start` and `tail`
- if you need a middle section that was omitted from that default preview, use `bash_exec(mode='read', id=..., start=..., tail=...)`
- monitor them with `bash_exec(mode='list')` and `bash_exec(mode='read', id=..., tail_limit=..., order='desc')`
- after the first read, prefer `bash_exec(mode='read', id=..., after_seq=last_seen_seq, tail_limit=..., order='asc')` for incremental monitoring
- if ids become unclear, recover them through `bash_exec(mode='history')`
- launch long slices with a structured `comment` such as `{stage, goal, action, expected_signal, next_check}`
- use `silent_seconds`, `progress_age_seconds`, `signal_age_seconds`, and `watchdog_overdue` from `bash_exec(mode='list'|'read', ...)` as the default stall checks
- use an explicit wait-and-check cadence of about `60s`, `120s`, `300s`, `600s`, `1800s`, then every `1800s` while still running
- if needed, use an explicit bounded wait such as `bash_exec(command='sleep 60', mode='await', timeout_seconds=70)` or `bash_exec(mode='await', id=..., timeout_seconds=...)` between checks
- canonical sleep choice:
  - if you only need wall-clock waiting between checks, use `bash_exec(command='sleep N', mode='await', timeout_seconds=N+buffer, ...)`
  - keep a real buffer on that sleep timeout; do not set `timeout_seconds` exactly equal to `N`
  - if you are waiting on an already running managed session, prefer `bash_exec(mode='await', id=..., timeout_seconds=...)` instead of starting a new sleep command
- after the first meaningful signal and then at real checkpoints (e.g., completion, blocker, recovery, or a materially changed evidence frontier), send `artifact.interact(kind='progress', ...)` so the user sees the newest real state
- after each completed sleep / await monitoring cycle for an active slice, inspect state first; only send another `artifact.interact(kind='progress', ...)` update if the user-visible state materially changed
- include the estimated next reply time or next check time in those monitoring updates
- stop them with `bash_exec(mode='kill', id=..., wait=true, timeout_seconds=...)` if the slice is invalid, wedged, or superseded; add `force=true` when immediate termination is required
- when you control the slice code, prefer a throttled `tqdm` progress reporter and, when feasible, pair it with concise `__DS_PROGRESS__` lines carrying phase and ETA
- do not mark a slice complete until the managed log and outputs both confirm completion

### 3. Keep comparability

Comparability rules:

- keep the same evaluation contract unless the variation is the point
- when `active_baseline_metric_contract_json` exists, keep slice comparisons aligned with it unless the slice explicitly records why it differs
- state exactly what changed
- state exactly what stayed fixed
- keep naming and output paths clean so multiple runs can coexist

For code-modifying slices, the default durable layout should stay interpretable:

- working surface:
  - `.ds/worktrees/<slice_id>/` when isolated worktrees are used
- experiment surface:
  - `experiments/analysis/<campaign_id>/<slice_id>/`
- artifact surface:
  - `artifacts/runs/<artifact_id>.json`
  - `artifacts/reports/<artifact_id>.json`

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

Each completed slice should also leave a `run` artifact containing at least:

- `campaign_id`
- `slice_id`
- `run_kind`
- `parent_run_id`
- `analysis_question`
- `fixed_conditions`
- `changed_factors`
- `metrics_summary`
- `metric_deltas`
- `success_criteria`
- `abandonment_criteria`
- `verdict`
- `reason`
- `paths`

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
- separate:
  - stable support
  - partial support
  - contradiction
  - unresolved ambiguity

When there are many slices, summarize the top `3-5` most important ones first, then point to the full evidence paths.

The aggregated report should also answer:

- should the main claim be strengthened, weakened, narrowed, or abandoned?
- which slice changed the interpretation most?
- which slice is still worth rerunning, and why?
- which planned slices were intentionally skipped because earlier results made them low value?

When the aggregated campaign report is complete, send a richer threaded `artifact.interact(kind='milestone', ...)` update.
Lead that milestone with a concise `1-2` sentence campaign outcome summary before expanding into slice-level detail.

If QQ milestone media is enabled and the aggregated report materially changes the claim boundary, you may attach one campaign summary PNG to that closing milestone update.
That update should explicitly classify the campaign outcome in the same language as the report:

- stable support
- partial support
- contradiction
- unresolved ambiguity

### 6. Route the next step

A campaign should end with an explicit next move:

- continue the campaign
- return to `experiment`
- move to `write`
- stop or reset the current line

Record the post-campaign route as a `decision` artifact.
When helpful, include a reflection block with:

- `what_worked`
- `what_failed`
- `learned_constraints`

and a `next_direction` block that states:

- objective
- key steps
- success criteria
- abandonment criteria

This makes the next stage executable without guesswork.

## Analysis-quality rules

Good campaign behavior:

- one clear question per run
- one-factor-at-a-time changes when possible
- clear comparison against the accepted reference line
- visibility of null and negative findings
- a logically ordered suite rather than a random batch

Strong campaign ordering usually looks like:

1. most claim-critical ablation or comparison
2. strongest robustness or sensitivity checks
3. failure-mode or error analysis
4. efficiency or secondary analysis

The exact order can vary, but the most claim-relevant evidence should appear first.

Weak campaign behavior:

- hidden scope expansion
- many untracked simultaneous changes
- campaign summary without per-run evidence
- ignoring contradictory analysis results
- reporting every minor slice with equal weight instead of prioritizing the important ones

## Memory rules

Stage-start requirement:

- begin every analysis campaign pass with `memory.list_recent(scope='quest', limit=5)`
- then run at least one analysis-relevant `memory.search(...)` before launching or resuming slices
- if several campaigns, parent runs, or idea lines exist, narrow retrieval to the current `campaign_id`, `parent_run_id`, `idea_id`, or `branch` instead of mixing unrelated slice memory

Write to memory only when the campaign yields reusable lessons, such as:

- robust failure patterns
- evaluation caveats
- reproducible sensitivity findings

Stage-end requirement:

- if the campaign produced a durable cross-slice lesson, failure pattern, or comparability caveat, write at least one `memory.write(...)` before leaving the stage

The campaign’s main record belongs in run artifacts and the aggregated report.
When synthesizing the campaign, read the per-slice `evaluation_summary` fields first, then expand into longer evidence only where the short summaries are still ambiguous.

## Artifact rules

Typical artifact sequence:

- decision artifact to launch the campaign
- report artifact for the charter
- progress artifacts during long campaigns
- run artifacts per analysis slice
- report artifact for the aggregated campaign summary
- decision artifact for the next anchor

## Failure and blocked handling

Record blocked or failed campaign states explicitly, such as:

- missing parent run
- analysis question under-specified
- campaign run failed before evidence was produced
- metrics not comparable
- campaign conclusion still ambiguous

A blocked campaign should still name the next best action.

## Exit criteria

Exit the analysis-campaign stage once one of the following is durably true:

- the campaign produced enough evidence for writing or decision-making
- the campaign exposed a problem that requires returning to `experiment` or `idea`
- the campaign is blocked and the blocker is durably recorded
