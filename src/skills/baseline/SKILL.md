---
name: baseline
description: Use when a quest needs to attach, import, reproduce, repair, verify, compare, or publish a baseline and its metrics.
skill_role: stage
---

# Baseline

This skill establishes the reference system the quest will compare against.
The target is one trustworthy baseline line, not an endless reproduction diary.

## Interaction discipline

- Follow the shared interaction contract injected by the system prompt.
- Keep ordinary setup and debugging updates concise.
- Use richer milestone updates only when the baseline becomes trusted, caveated, blocked, waived, or route-changing.
- Hard execution rule: every terminal command in this stage must go through `bash_exec`; do not use any other terminal path for setup, reproduction, monitoring, verification, Git, Python, package-manager, or file-inspection commands.
- Prefer `bash_exec` for setup, reproduction, monitoring, and verification commands so the baseline line stays durable and auditable.

## Tool discipline

- **Do not use native `shell_command` / `command_execution` in this skill.**
- **All shell, CLI, Python, bash, node, git, npm, uv, and environment work must go through `bash_exec(...)`.**
- **For git work inside the current quest repository or worktree, prefer `artifact.git(...)` before raw shell git commands.**
- **If a generic git smoke test is needed outside the quest repo, use `bash_exec(...)` in an isolated scratch repository.**

## Non-negotiable rules

- no fabricated metrics, logs, run status, or success claims
- do not skip baseline steps or silently simplify the route when that would change trust or comparability
- do not claim a baseline is ready before verification is complete
- do not infer missing commands, scripts, or parameters when the uncertainty could change the result
- any unavoidable guess must be written down explicitly with expected impact
- use web search for discovering papers or repos, but use `artifact.arxiv(paper_id=..., full_text=False)` for actually reading a source arXiv paper when it exists
- set `full_text=True` only when the short form is insufficient
- for Python baselines, environment setup should be standardized around `uv`

## Stage purpose

The baseline stage should produce a usable reference point through one of four routes:

1. attach an existing reusable baseline
2. import a reusable baseline package
3. reproduce a baseline from source
4. repair a broken or stale baseline

Keep the classic control flow:

1. analysis
2. setup
3. execution
4. verification

These are control gates, not paperwork walls.

## Quick workflow

1. Read the source paper and source repo first, or record exactly what is missing and why.
2. Choose the lightest trustworthy route: attach, import, reproduce, or repair.
3. Start with the fast path whenever the current baseline object, command path, and acceptance target are already clear enough to validate cheaply.
4. Before substantial baseline setup, code edits, or a real baseline run, create `PLAN.md` and `CHECKLIST.md`; short-form files are enough for simple fast-path work.
5. Keep one dominant phase visible: analysis -> setup -> execution -> verification.
6. Prefer one clean implementation pass, one smoke test, and then one normal baseline run.
7. Retry only when smoke, verification, or runtime evidence shows a concrete failure or incompatibility.
8. Close the stage by confirming or waiving the gate, then hand off with a concise `1-2` sentence summary of trust status and next anchor.

## Fast-path first

Default to the lightest baseline path that can still establish a trustworthy comparison.
Default to a fast path when it can establish trust with less work.

Fast path is the default when any of the following is true:

- `requested_baseline_ref` or `confirmed_baseline_ref` already points to the active baseline object
- the route is clearly `attach` or `import`
- the repo entrypoint, dataset or split, and metric contract are already concrete enough to validate cheaply
- reproduction requires no meaningful code changes and the main uncertainty is only whether the command still runs

Fast path means:

- do not restart broad baseline discovery by default
- do not front-load a full codebase audit when the entrypoint is already concrete
- use a minimal `PLAN.md`, a minimal `CHECKLIST.md`, one bounded smoke test when needed, and then one real validation or run
- default to reuse-and-verify when runtime already attached a concrete baseline

Escalate from fast path to fuller audit only when:

- the paper and repo disagree materially
- the real run or eval entrypoint is unclear
- code changes are likely required
- the contract spans multiple metrics, datasets, subtasks, or splits that still need interpretation
- the same failure class reappears after one documented autonomous fix
- the quest is trying to publish a reusable global baseline rather than only clear the current gate

## Use when

- no credible baseline exists yet
- the current baseline is unverified or stale
- the user already has a baseline package that should be attached or imported
- a reproduction failed earlier and now needs repair
- the quest resumed and the baseline trust state is unclear

## Do not use when

- the quest already has a verified active baseline and the next move is ideation or execution
- the user explicitly waived the baseline gate and that waiver is durably recorded

## Stage gate

Do not proceed to comparison-heavy downstream work unless one of the following is durably true:

- a baseline has been attached and accepted
- a baseline has been imported and accepted
- a baseline reproduction has completed and been verified
- an explicit waiver decision exists with a clear reason

Operationally:

- call `artifact.confirm_baseline(...)` once the accepted baseline root and trusted comparison contract are clear
- call `artifact.waive_baseline(...)` when the quest must continue without a baseline
- attach, import, or publish alone do not open the downstream gate

## Required plan and checklist

Before substantial baseline setup, code edits, or a real baseline run, create a quest-visible `PLAN.md` and `CHECKLIST.md`.

- Use `references/baseline-plan-template.md` as the canonical structure for `PLAN.md`.
- Use `references/baseline-checklist-template.md` as the canonical structure for `CHECKLIST.md`.
- `analysis_plan.md` and `REPRO_CHECKLIST.md` remain acceptable compatibility alias files when an older quest already depends on them.
- For fast-path attach/import/prebound validation or a simple reproduce path with no expected code changes, short-form `PLAN.md` and `CHECKLIST.md` are enough.
- The plan should put the user's explicit requirements and non-negotiable constraints first.
- Then record the chosen route, source identity, command path, expected outputs, acceptance condition, safe efficiency levers, main risks, and fallback.
- If the route, commands, source package, fallback path, or trust judgment changes materially, revise `PLAN.md` before continuing.
- Once the route is concrete, stop reshaping code and commands speculatively.

Default retry discipline:

- do not rerun the same unchanged smoke command just to reconfirm the same fact
- treat one autonomous retry for the same failure class as the normal upper bound
- if the same failure class appears again, switch explicitly into `repair`, record `blocked`, or route through `decision`

## Required durable outputs

The baseline stage should usually leave behind:

- a baseline directory under `baselines/local/` or `baselines/imported/`
- `PLAN.md` and `CHECKLIST.md`
- a verification note or report
- command, config, environment, and metrics pointers
- a baseline artifact
- a confirmed baseline gate via `artifact.confirm_baseline(...)`, or an explicit waiver via `artifact.waive_baseline(...)`
- an optional registry publication if the baseline is reusable beyond this quest

For simple attach/import flows or a straightforward reproduce flow, do not stall just to precreate every optional note file.

Useful optional notes:

- `setup.md`
- `execution.md`
- `verification.md`
- `STRUCTURE.md` when the layout is non-obvious

## File-by-file contract

- `PLAN.md` or compatibility alias `analysis_plan.md` is the required route contract before substantial setup, code edits, or a real run; it should state the route, source identity, command path, expected outputs, acceptance condition, main risks, and fallback.
- `CHECKLIST.md` or compatibility alias `REPRO_CHECKLIST.md` is the required living state tracker; it should show whether the baseline object, smoke decision, real run decision, and final accept / block / waive outcome are explicit.
- `setup.md` is optional unless environment or layout choices are non-trivial; if used, record the working directory, environment route, important config paths, source revision, and notable setup deviations.
- `execution.md` is optional unless the run is long, multi-step, or rerun-heavy; if used, record the launched commands, durable log paths, checkpoints, exit state, and any reruns or repairs.
- `verification.md` is optional as a filename but required in substance before acceptance or blocked closeout; either this file or an equivalent report should record trusted metrics, expected-versus-observed comparison, caveats, canonical output paths, and the next anchor.
- `STRUCTURE.md` becomes required when the workspace layout, mounts, symlinks, or generated outputs are non-obvious or meant for reuse; it should map the important directories and say which paths are canonical.
- `attachment.yaml` is required for attached or imported baselines under `baselines/imported/`; preserve source identity, selected variant when relevant, and attachment provenance there.
- `<baseline_root>/json/metric_contract.json` is the canonical accepted comparison contract; once the baseline is accepted, do not leave the authoritative metric surface only in chat, memory, or prose.
- `Result/metric.md` is scratch-only; it may help during execution, but it is never the final source of truth.

Minimum stability rules:

- before the first real run, leave one durable note with the chosen route, expected command path, target outputs, and main risks
- after each smoke test or real run, record what actually happened and whether the route still looks viable
- before acceptance, leave a clear verification note and baseline gate decision
- every accepted baseline should leave one accepted baseline artifact
- every blocked baseline line should leave one blocked report and one next-step decision
- if one rolling note is enough for a simple baseline line, use it

## Durable path contract

Use the real runtime paths consistently.

Quest-local paths:

- reproduced baseline root: `<quest_root>/baselines/local/<baseline_id>/`
- attached or imported baseline root: `<quest_root>/baselines/imported/<baseline_id>/`
- attachment record: `<quest_root>/baselines/imported/<baseline_id>/attachment.yaml`
- canonical baseline metric contract JSON: `<baseline_root>/json/metric_contract.json`
- baseline artifact record: `<quest_root>/artifacts/baselines/<artifact_id>.json`
- baseline reports: `<quest_root>/artifacts/reports/<artifact_id>.json`
- confirmed baseline reference: `quest.yaml -> confirmed_baseline_ref`

Global reusable registry paths:

- baseline registry index: `~/DeepScientist/config/baselines/index.jsonl`
- canonical baseline entry: `~/DeepScientist/config/baselines/entries/<baseline_id>.yaml`

## Baseline id and variant rules

- `baseline_id` should be short, stable, and filesystem-safe
- use letters, digits, `.`, `_`, or `-`
- do not use spaces, `/`, `\\`, or `..`
- if one codebase contains multiple comparable baselines, prefer one `baseline_id` with structured variants instead of inventing many near-duplicate entries
- when variants exist, keep `default_variant_id`, `baseline_variants`, and per-variant metric summaries stable enough that later `experiment` and `write` stages can cite them directly

Do not invent parallel durable locations when these runtime contracts already exist.
Do not leave the authoritative metric contract only in chat, memory, or prose once the baseline is accepted.

If a baseline is reproduced only because an analysis campaign needs an extra comparator:

- still place it under the normal baseline roots
- treat it as a supplementary analysis baseline unless the quest explicitly promotes it into the canonical gate
- do not call `artifact.confirm_baseline(...)` for that supplementary case unless the quest truly intends to replace the canonical baseline

## Multi-baseline policy

One quest may legitimately need more than one baseline.

- explicitly mark which baseline is the primary downstream comparator
- distinguish primary comparison baselines from fallback or infrastructure baselines
- if several baselines are credible, record why the chosen primary baseline is the fairest paper-facing comparator
- do not leave later stages guessing which baseline is authoritative

## Route order

Prefer this order:

1. attach
2. import
3. reproduce
4. repair

Prefer reuse over redundant reproduction.

## Workflow

### Phase 1. Analysis

Before running anything substantial, determine:

- exact task
- dataset and split contract
- metric contract
- source baseline identity
- source code path
- expected run command or evaluation path
- expected paper or repo numbers when they exist
- local resource constraints

Default analysis discipline:

- read the source paper and source repo first
- if runtime already exposes a matching `requested_baseline_ref` or `confirmed_baseline_ref`, validate that concrete object before restarting broad discovery
- identify the real run or evaluation entrypoint
- identify the dataset or split and metric contract
- identify likely environment blockers
- define the cheapest credible smoke test

Escalate to a fuller audit only when the command path is unclear, the repo is large or confusing, repair mode is active, or custom code changes look likely.

When the fuller audit is necessary, capture only what later stages truly need:

- major entry scripts, configs, and modules
- end-to-end data flow
- evaluation path and metric computation path
- obvious environment assumptions
- obvious bottlenecks or incompatibilities

If the source paper is available, record:

- the core algorithm in compact, implementation-faithful form
- the main reported numbers
- the main weaknesses or bottlenecks likely to matter for this quest

You may inspect local feasibility with shell-based checks for OS, GPU, CPU, RAM, disk, Python version, and whether `uv` is available.

The analysis phase should leave behind a concrete plan rather than only conversational intent.

## Phase 2. Setup

Prepare the selected route:

- attach: validate the selected baseline id and variant
- import: place the imported baseline metadata under the quest and confirm the package is readable
- reproduce: prepare the baseline work directory, commands, config pointers, and environment notes
- repair: identify the precise broken point before rerunning blindly

For Python baselines, standardize environment setup around `uv`.

### Python environment rule: use `uv`

- if the repo already contains `uv.lock` or a solid `pyproject.toml`, use `uv sync`
- otherwise create a local virtual environment with `uv venv`
- install dependencies with `uv pip install ...`
- run setup, smoke tests, and real commands through `uv run ...`

Practical rules:

- prefer a quest-local or baseline-local `.venv`
- prefer `uv run python ...` or `uv run bash ...` over relying on shell activation state
- if a specific interpreter is required, make it explicit with `uv venv --python 3.11` or `uv run --python 3.11 ...`
- if CUDA, PyTorch, JAX, or custom wheels require a special index URL, keep that install under `uv pip`
- only accept a non-`uv` route when there is a concrete blocker that cannot be resolved locally

Common `uv` patterns:

- `uv sync`
- `uv venv --python 3.11`
- `uv pip install -r requirements.txt`
- `uv run python scripts/smoke_test.py`
- `uv run python train.py --config ...`

Setup should record:

- baseline id and source identity
- working directory
- config files
- command template
- expected outputs
- known deviations from paper or source
- the chosen `uv` route and Python version

Fallbacks:

- if Hugging Face access is blocked, record and try an approved local mirror such as ModelScope when that does not change the comparison meaning
- if a quest already depends on `analysis_plan.md` or `REPRO_CHECKLIST.md`, keep the compatibility alias explicit rather than splitting truth across two active plans

## Phase 3. Execution

Run only the work required to establish the baseline credibly.

Execution rules:

- keep commands auditable
- keep logs durable
- avoid uncontrolled side experiments during baseline establishment
- checkpoint only explainable, minimal code changes
- prefer equivalence-preserving efficiency gains such as larger safe batch size, cache reuse, checkpoint resume, and parallel downloads or workers
- do not use an efficiency lever if it changes accepted baseline meaning, effective evaluation contract, or trust judgment

Long-running execution discipline:

- run one bounded smoke test before a substantial baseline reproduction
- once the smoke test passes, launch the real baseline reproduction with `bash_exec(mode='detach', ...)`
- monitor by forward progress instead of by short-window completion anxiety
- do not report final success until the command actually finished and the expected result files exist
- if you need to recover ids or inspect session state, use `bash_exec(mode='history')` or `bash_exec(mode='list')`
- `bash_exec(mode='read', id=...)` returns the full saved log when it is `2000 lines or fewer`; for longer logs, inspect omitted middle windows with `start` and `tail`
- during monitoring, prefer `bash_exec(mode='read', id=..., tail_limit=..., order='desc')`, and after the first read prefer incremental checks with `after_seq=last_seen_seq`
- use `silent_seconds`, `progress_age_seconds`, `signal_age_seconds`, and `watchdog_overdue` as the default staleness clues
- if a run is clearly invalid, wedged, or superseded, stop it with `bash_exec(mode='kill', id=..., wait=true, timeout_seconds=...)`, document why, and relaunch cleanly
- do not let more than the `30-minute visibility bound` pass without a real inspection and a `next expected update time`
- when the baseline code is under your control, prefer a throttled `tqdm` progress reporter and periodic `__DS_PROGRESS__` markers when feasible

Keep retries bounded:

- one smoke test is the default
- one autonomous fix-and-retry for the same failure class is the normal upper bound
- if the same failure class returns, stop looping

## Phase 4. Verification

Verification is mandatory before baseline acceptance.

Verify:

- the run actually finished
- the reported metrics came from the intended dataset and split
- the metric definitions match the quest contract
- the result is comparable to the paper, source repo, or selected target
- any deviations are explicitly stated

Classify the outcome as one of:

- `verified_match`
- `verified_close`
- `verified_diverged`
- `broken`

Verification must explicitly separate:

- likely implementation mismatch
- environment mismatch
- data or split mismatch
- expected stochastic variance
- unexplained divergence

Verification should answer:

- whether the baseline is trustworthy enough for downstream comparison
- whether the result is reusable beyond this quest
- whether another repair or rerun is justified
- whether the line should stop here and hand off

A verification report should be self-contained enough that a later stage can answer:

- what was used
- how it was obtained: attach, import, reproduce, or repair
- what commands and configs were used
- what metrics are trusted
- what caveats remain
- whether the result is reusable beyond this quest

## Baseline comparability contract

The baseline stage is not complete just because something ran.
It is complete when later stages can compare against it fairly.

Before declaring a baseline usable, make the comparability contract explicit:

- task identity
- dataset identity and version
- split contract
- preprocessing boundary
- evaluation script or evaluation path
- required metric keys
- metric directions
- seed policy when relevant
- source commit or source package identity
- known deviations from the source reference

Unless the user explicitly specifies otherwise, treat the original paper's evaluation protocol as the canonical baseline contract.
If any of these fields are still materially unknown, do not pretend the baseline is a clean downstream reference.
For the fuller checklist and verdict meanings, read `references/comparability-contract.md`.

## Feasibility and trust classes

Before acceptance, classify feasibility as one of:

- `full_reproducible`
- `degraded_but_acceptable`
- `blocked`

And classify downstream trust as one of:

- `verified`
- `partially_verified`
- `operational_but_incomparable`
- `failed`

Do not silently upgrade a degraded or merely operational result into a normal trusted baseline.

## Minimum baseline artifact content

The accepted baseline artifact should include at least:

- `baseline_id`
- `baseline_kind`
- `path`
- `task`
- `dataset`
- `primary_metric`
- `metrics_summary`
- `environment`
- `source`
- `summary`

If variants exist, also include:

- `default_variant_id`
- `baseline_variants`

Metric-contract rules:

- if the accepted baseline contract includes multiple metrics, datasets, subtasks, or splits, record all of them in `<baseline_root>/json/metric_contract.json`
- keep `primary_metric` as the headline metric only; do not let it erase the rest of the comparison surface
- when confirming a baseline, submit the canonical `metrics_summary` as a flat top-level dictionary keyed by the paper-facing metric ids
- every canonical baseline metric entry should include `description`, either `derivation` or `origin_path`, and `source_ref`
- if the paper reports both aggregate and per-dataset or per-task results, preserve both whenever feasible through `metrics_summary` plus structured rows rather than one cherry-picked scalar
- if the source package already has a richer leaderboard table, structured result file, or `json/metric_contract.json`, reuse that richer contract instead of hand-writing a thinner one that keeps only one averaged scalar
- `Result/metric.md` is optional temporary scratch memory only; reconcile against it before calling `artifact.confirm_baseline(...)`, but do not treat it as a required durable file

## Publication and reuse

Use the registry deliberately, not as an afterthought.

If the result is reusable beyond the current quest:

- publish it through `artifact.publish_baseline(...)`
- ensure the payload includes identity, provenance, trusted metrics, and any variant structure
- set `publish_global: true` only when verification is complete and reuse is justified

If the current quest should reuse an existing baseline:

- attach it through `artifact.attach_baseline(...)`
- preserve the selected `baseline_id`
- preserve the selected `variant_id` when one is used
- keep the attachment durable under `baselines/imported/`

If runtime state already includes `requested_baseline_ref` or a matching `confirmed_baseline_ref`:

- default to reuse-and-verify, not rediscovery
- treat a creation-time pre-bound baseline as the active starting point unless you find a concrete incompatibility
- do not rerun broad baseline scouting or full reproduction just because the stage name is `baseline`

For a clearer attach/import/reproduce/repair rubric, read `references/route-selection.md`.
For reusable-package expectations, read `references/publishable-baseline-package.md`.

## Workspace and branch rules

- treat the baseline workspace as a system-managed reproduction surface, not an unrelated sandbox
- avoid creating a nested authoritative Git lifecycle inside the baseline workspace
- use the quest branch unless isolation is genuinely needed
- if baseline setup is risky or intrusive, prepare an isolated branch or worktree first and record why
- do not proliferate branches without a reason

## Memory rules

Stage-start requirement:

- by default, begin every baseline pass with `memory.list_recent(scope='quest', limit=5)`
- then run at least one baseline-relevant `memory.search(...)` before new baseline analysis, repair, or rerun work
- fast-path exception: if the quest already exposes a clear `requested_baseline_ref` or `confirmed_baseline_ref` and the immediate task is only to validate or reattach that concrete baseline, you may skip broad retrieval

Write memory only for reusable lessons such as:

- paper-to-code mismatch notes
- environment incidents
- dataset quirks
- verification caveats
- attach vs import vs reproduce vs repair rationale

When calling `memory.write(...)`, pass `tags` as an array like `["stage:baseline", "baseline:<baseline_id>", "type:repro-lesson"]`, not as one comma-joined string.

Stage-end requirement:

- if baseline work produced a durable reproduction lesson, verification caveat, environment incident, or route rationale, write at least one `memory.write(...)` before leaving the stage

## Artifact rules

Typical artifact sequence:

- `progress` for long-running setup or execution checkpoints
- `report` for analysis notes or verification notes
- `decision` for route choice, blocked routing, or accept/reject/rerun/repair calls
- `baseline` only for an accepted baseline record

For stable field shapes, read `references/artifact-payload-examples.md`.

The baseline handoff should make these items obvious:

- `baseline_id`
- `baseline_variant_id` when relevant
- route used: attach, import, reproduce, or repair
- trusted metrics
- canonical metric contract JSON path
- verification outcome
- reusable or quest-local only
- canonical output paths
- main caveats
- recommended next anchor

If this packet is not obvious from the accepted artifact plus verification note, the baseline line is not stable enough yet.

## Failure and blocked handling

Do not hide failures.

If blocked, record the class explicitly:

- `missing_source`
- `missing_code`
- `missing_metric_contract`
- `environment_infeasible`
- `command_unknown`
- `run_failed`
- `verification_failed`

A blocked result must state:

- what failed
- what was tried
- which paths or logs show the issue
- whether the next best move is attach, import, retry, repair, reset, or ask the user

Reasonable autonomous fixes before escalation:

- missing module or dependency
- wrong dataset path
- permission errors on scripts
- reasonable batch-size reductions for OOM
- obvious environment activation mistakes

If a fix would change confirmed scope, metrics, permissions, or resource assumptions, stop and return to analysis rather than applying it silently.

## Exit criteria

Exit the baseline stage once one of the following is durably true:

- a baseline is attached and accepted
- an imported baseline is accepted
- a reproduced baseline is verified and accepted
- a broken route has been declared blocked and a next decision is recorded

Typical next anchors:

- `idea`
- `experiment` in tightly scoped follow-on cases
- `decision` if the baseline line remains contested
