---
name: intake-audit
description: Use when a quest does not start from a blank state and the agent must first audit, trust-rank, and reconcile existing baselines, results, drafts, or review materials before choosing the next anchor.
skill_role: companion
---

# Intake Audit

Use this skill when the quest already has meaningful state and the first job is to normalize that state instead of restarting the canonical research loop from zero.

## Interaction discipline

- Follow the shared interaction contract injected by the system prompt.
- For ordinary active work, prefer a concise progress update once work has crossed roughly 6 tool calls with a human-meaningful delta, and do not drift beyond roughly 12 tool calls or about 8 minutes without a user-visible update.
- Message templates are references only. Adapt to the actual context and vary wording so updates feel natural and non-robotic.
- If a threaded user reply arrives, interpret it relative to the latest intake-audit progress update before assuming the task changed completely.
- When the audit reaches a durable route recommendation, send one richer `artifact.interact(kind='milestone', reply_mode='threaded', ...)` update that says what state is trusted, what still needs work, and which anchor should run next.

## Tool discipline

- **Do not use native `shell_command` / `command_execution` in this skill.**
- **Any shell, CLI, Python, bash, node, git, npm, uv, or repo-audit execution must go through `bash_exec(...)`.**
- **For git inspection or maintenance inside the current quest repository or worktree, prefer `artifact.git(...)` before raw shell git commands.**
- **Use shell execution only when durable quest files, artifacts, and memory are insufficient; do not bypass durable state just because shell feels faster.**

## Three-layer todo contract

- treat quest-root `plan.md` as the top-level research map whose next active node must become explicit after intake
- if the audit is multi-step, use workspace `PLAN.md` as the current intake-node contract and `CHECKLIST.md` as the execution frontier
- when the audit resolves the route, update quest-root `plan.md` instead of leaving the recommendation only in a report artifact

## Purpose

`intake-audit` is an auxiliary entry skill, not a normal long-running anchor.

Its purpose is to answer four questions before deeper work begins:

1. what already exists?
2. what is trustworthy?
3. what can be reused directly?
4. which skill should take over next?

This skill exists because many quests do **not** start from a clean slate.
Common non-blank starts include:

- a baseline already exists and may already be confirmed
- a main experiment has already finished and only needs durable recording or interpretation
- analysis results already exist across child branches or worktrees
- a draft or paper bundle already exists
- reviewer comments already exist and the quest is really a revision/rebuttal task
- the user explicitly says not to rerun from scratch

Do not treat these as edge cases.
They are common research entry states.

## Use when

- `startup_contract.launch_mode = custom` and the profile implies existing work
- the quest root already contains meaningful baseline, experiment, analysis, or paper assets
- the user says:
  - “baseline 已经有了”
  - “不要重新复现”
  - “先整理现有结果”
  - “已有论文/草稿，先基于现有状态继续”
- review materials exist but the current paper/result state is still unclear

## Do not use when

- the quest is genuinely blank and should start with ordinary `scout` or `baseline`
- the active state is already well-normalized and the next anchor is obvious
- the task is a pure non-research request

## Non-negotiable rules

- Do not rerun expensive work just because files exist. First decide whether a trust gap actually requires rerunning.
- Do not fabricate missing durable records in order to make the quest look cleaner.
- Do not mark an existing baseline as trusted unless the metric contract, source, and comparability are clear enough.
- Do not mark an existing experiment as a durable main result unless it is genuinely the main run for an accepted idea line.
- Do not silently import old drafts, plots, or notes as the active contract if they belong to a different idea line or branch line.
- Do not lose provenance. If an artifact is reused, record where it came from and why it is trusted enough.
- If the quest is really a review/revision task, route to `rebuttal` instead of pretending this is a normal fresh paper-writing pass.

## Typical intake states

Classify the current quest into one or more of these buckets:

- `baseline_ready`
- `baseline_partial`
- `main_result_ready`
- `analysis_ready`
- `draft_ready`
- `paper_bundle_ready`
- `review_package_ready`
- `unclear_state`

Also classify every important asset by trust:

- `trusted`
- `usable_with_verification`
- `reference_only`
- `stale_or_conflicting`
- `missing_context`

## Primary truth sources

Use, in roughly this order:

- `startup_contract`
  - especially `launch_mode`, `custom_profile`, `entry_state_summary`, `review_summary`, and `custom_brief` when present
- quest continuity files:
  - `brief.md`
  - `plan.md`
  - `status.md`
  - `SUMMARY.md`
- recent durable artifact state and quest snapshot
- current workspace tree and visible quest files
- prior memory cards and decisions
- git history and current branch topology when needed
- user messages

Do not trust chat recollection over durable state.

## Workflow

### 1. Read startup intent first

Before touching the workspace, inspect:

- `startup_contract`
- the latest user message
- recent quest status

Interpret these fields specially when present:

- `launch_mode = custom`
  - do not force the standard full-research route
- `custom_profile = continue_existing_state`
  - expect reusable assets and state normalization
- `custom_profile = revision_rebuttal`
  - expect a paper/review package and likely handoff to `rebuttal`
- `custom_profile = freeform`
  - prefer the custom brief over the default stage ordering

### 2. Retrieve memory before filesystem triage

Stage-start requirement:

- run `memory.list_recent(scope='quest', limit=5)`
- run at least one `memory.search(...)` using:
  - the quest title or central topic
  - any known baseline id or method name
  - any known paper title or venue short name
  - any known review keyword such as `rebuttal`, `review`, or `revision`

The point is to reuse prior route knowledge before re-auditing the same state from scratch.

### 3. Inventory the quest state

Create or refresh a durable audit note using `references/state-audit-template.md`.

The inventory should cover:

- baseline assets
- main experiment assets
- analysis assets
- writing assets
- review assets
- git / branch / worktree state
- missing or conflicting state

Useful places to inspect include:

- `artifacts/`
- `baselines/`
- `experiments/main/`
- `experiments/analysis/`
- `paper/`
- `reviews/` or equivalent user-provided review folders

Do not over-read the entire tree.
Read enough to classify the state and locate the likely trust anchors.

### 4. Trust-rank and reconcile

For each major asset, decide:

- can it be trusted as-is?
- does it need a light verification pass?
- is it only reference material?
- is it stale or conflicting?

Then reconcile it with the durable artifact layer:

- existing reusable baseline:
  - `artifact.attach_baseline(...)`
  - then `artifact.confirm_baseline(...)` when trust is justified
- existing main result:
  - `artifact.record_main_experiment(...)` only if the run is genuinely the accepted main run and the required fields can be filled honestly
- existing analysis results:
  - if the campaign already exists, use `artifact.record_analysis_slice(...)` for each real finished slice that needs durable registration
- existing outline:
  - `artifact.submit_paper_outline(mode='select'|'revise', ...)` when there is a real durable outline contract
- existing paper bundle:
  - `artifact.submit_paper_bundle(...)` when the draft/package state is genuinely ready

If the evidence is insufficient for a durable backfill, record that insufficiency explicitly instead of inventing a cleaned-up history.

### 5. Choose the next anchor

After reconciliation, write one durable route decision with `artifact.record(payload={'kind': 'decision', ...})`.

Typical next anchors:

- baseline exists but trust is incomplete -> `baseline`
- baseline and route are ready, but no durable main result exists -> `experiment`
- main result exists, but follow-up evidence is missing -> `analysis-campaign`
- evidence is strong and writing should begin -> `write`
- review package is active -> `rebuttal`
- the quest is effectively complete or should pause -> `finalize`

### 6. Report and hand off

At the end of the intake pass, send one threaded `artifact.interact(kind='milestone', ...)` update that says:

- what already exists and is trusted
- what remains untrusted or incomplete
- which next skill should take over
- whether the user needs to provide anything else

## Recommended durable outputs

- `artifacts/intake/state_audit.md`
- `artifacts/intake/recommended_next_step.md`
- one `decision` artifact for the post-audit route
- one or more repair/backfill artifact calls when justified

## Companion skill routing

Open additional skills only when the audit indicates they are necessary:

- `baseline`
  - when an existing baseline must be validated, repaired, confirmed, or waived
- `experiment`
  - when the accepted route lacks a durably recorded main result
- `analysis-campaign`
  - when the main result exists but the evidence boundary is still weak
- `write`
  - when a trustworthy draft or outline should become the active writing line
- `rebuttal`
  - when reviewer comments, revision requests, or meta-review materials define the real task
- `decision`
  - when more than one next anchor remains plausible

## Memory discipline

Stage-end requirement:

- if the intake pass produced a durable route choice, trust judgment, or asset-reuse rule, write at least one `memory.write(...)`

Useful tags include:

- `stage:intake-audit`
- `type:state-audit`
- `type:route-handoff`
- `type:reuse-rule`
- `state:trusted`
- `state:needs-verification`

When the audit concerns a specific existing line, include identifiers when known:

- `baseline_id`
- `idea_id`
- `run_id`
- `branch`
- `paper_state`

## Success condition

`intake-audit` is successful when:

- the quest's current state is understandable
- the trustworthy reusable assets are explicit
- the untrusted gaps are explicit
- the next anchor is explicit
- the system can continue without pretending the quest started from zero
