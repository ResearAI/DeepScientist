---
name: baseline
description: Use when a quest needs to attach, import, reproduce, repair, verify, compare, or publish a baseline and its metrics.
skill_role: stage
---

# Baseline

This skill establishes the reference system the quest will compare against.
The real goal is to secure one trustworthy comparator and then get out of the way so the next scientific step can begin.
The target is one trustworthy baseline line, not an endless reproduction diary.

## Interaction discipline

Follow the shared interaction contract and keep baseline updates brief unless trust state, blocker state, or route changed materially.

## Tool discipline

- **Do not use native `shell_command` / `command_execution` in this skill.**
- **All shell, CLI, Python, bash, node, git, npm, uv, and environment work must go through `bash_exec(...)`.**
- **For git work inside the current quest repository or worktree, prefer `artifact.git(...)` before raw shell git commands.**
- **If a generic git smoke test is needed outside the quest repo, use `bash_exec(...)` in an isolated scratch repository.**
- Use web search for discovering papers or repos, but use `artifact.arxiv(paper_id=..., full_text=False)` for actually reading a source arXiv paper when it exists.
- Set `full_text=True` only when the short form is insufficient.

## Planning surfaces

Use quest/workspace planning files only when the baseline route is multi-step, expensive, or genuinely unclear; otherwise keep moving with the current route.

## Comparator-first rule

The baseline stage is comparator-first, not reproduction-first.
For `comparison_ready`, the default question is:

- what is the lightest trustworthy comparator?

not:

- how do I reproduce the whole source package most completely?

Unless the acceptance target explicitly requires a stronger package, prefer the lightest route that still makes the downstream comparison honest.
Do not escalate from attach / import / verify-local-existing into full source reproduction unless the lighter route cannot support a fair comparison.
A more complete baseline package is only the default when the acceptance target is explicitly `paper_repro_ready` or `registry_publishable`.
For `comparison_ready`, `verify-local-existing`, attach, or import should usually beat full reproduction.

## Non-negotiable rules

- no fabricated metrics, logs, run status, or success claims
- do not skip baseline steps or silently simplify the route when that would change trust or comparability
- do not claim a baseline is ready before verification is complete
- do not infer missing commands, scripts, or parameters when the uncertainty could change the result
- record any guess that could affect comparison in a brief caveat
- once a baseline is accepted, leave the authoritative comparison contract in `<baseline_root>/json/metric_contract.json`
- for Python baselines, prefer `uv`, but follow a repo-native environment route when it is clearly more trustworthy or required
- if the same failure class appears again without new evidence, code changes, or a route change, stop looping and route through `repair`, `decision`, `blocked`, or one bounded clarification

## Stage purpose

The baseline stage should produce a usable reference point through one of five routes:

1. attach an existing reusable baseline
2. import a reusable baseline package
3. verify an existing local code path or local service as the comparator
4. reproduce a baseline from source
5. repair a broken or stale baseline

Keep the classic control flow:

1. analysis
2. setup
3. execution
4. verification

These are control gates, not paperwork walls.

Default outcomes:

- `comparison_ready`: the default target; one comparator is trustworthy enough for downstream comparison, and the core metric contract is durably recorded
- `reproduction_complete`: a fuller paper-grade or reuse-grade baseline package is ready because the quest explicitly needs it
- `blocked` or `waived`: the current route cannot clear the gate cleanly, and the next move is explicit

Not every baseline needs a paper-grade exact reproduction.
Once one comparator is trustworthy enough and the core contract is durable, prefer leaving baseline and advancing.

## Quick workflow

1. identify the route and acceptance target
2. gather the minimum evidence needed to trust the provided or local comparator
3. set up only the environment and command path the current route actually needs
4. run a bounded smoke only if needed, then do the real validation path
5. verify, confirm or block, and leave a concise `1-2` sentence summary

Keep one dominant baseline route active at a time.
If source reproduction or repair is the chosen route, read the source paper and source repo before spending real setup or compute.
For attach, import, or verify-local-existing, gather only the minimum evidence needed to trust the provided or local comparator.

## Fast-path first

Default to the lightest baseline path that can still support a fair downstream comparison.
Default to a fast path when it can establish trust with less work.

Fast path means:

- do not restart broad baseline discovery by default
- do not front-load a full codebase audit
- do not require a fresh memory pass for every fast-path validation
- use `memory.list_recent(...)` or `memory.search(...)` when resuming, not as ceremony before every direct verification
- if runtime already exposes `requested_baseline_ref` or a matching `confirmed_baseline_ref`, default to reuse-and-verify
- fast-path exception: if no concrete comparator, command path, or core comparability surface exists yet, escalate to fuller audit, reproduction, or repair deliberately

When the baseline object, command path, and acceptance target are already clear, prefer the lightest direct validation path over broader planning or audit work.
A bounded smoke test is usually helpful only when command wiring, environment setup, evaluator behavior, or output paths are still uncertain.

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

For comparison-heavy downstream work, the default expectation is that one of the following is durably true:

- a baseline has been attached and accepted
- a baseline has been imported and accepted
- a verified local-existing comparator has been accepted
- a baseline reproduction has completed and been verified
- an explicit waiver decision exists with a clear reason

Operationally:

- call `artifact.confirm_baseline(...)` once the accepted baseline root and core trusted comparison contract are clear
- call `artifact.waive_baseline(...)` when the quest must continue without a baseline
- attach, import, or publish alone do not open the downstream gate
- a full exact reproduction is not always required: if the acceptance target is only comparison-ready, a verified attached/imported/local-existing comparator can be enough to confirm the baseline
- the comparison-ready minimum still requires `<baseline_root>/json/metric_contract.json`
- once a comparison-ready baseline is durably confirmed, baseline should usually stop immediately and hand off to the next scientific step
- any extra baseline work after that must name one explicit unresolved comparison risk it is meant to remove

## Minimum proof package by route

- `attach`:
  - baseline identity, provenance, trusted outputs pointer, and core metric contract are explicit
- `import`:
  - imported package is readable, `attachment.yaml` is durable, and trusted outputs or metrics are traceable
- `verify-local-existing`:
  - concrete local path or service, exact command or evaluation endpoint, output location, and core metric contract are explicit
- `reproduce`:
  - source identity, command path, expected outputs, and verification evidence are explicit
- `repair`:
  - broken point, bounded fix, rerun or re-read evidence, and resulting trust state are explicit

If a lighter route already satisfies the current acceptance target, stop there.

## Required plan and checklist

Use `references/baseline-plan-template.md` as the canonical structure for `PLAN.md`.
Use `references/baseline-checklist-template.md` as the canonical structure for `CHECKLIST.md`.

`PLAN.md` and `CHECKLIST.md` are required when the route is non-trivial, code-touching, expensive, or unstable.
For a simple fast path, a concise `CHECKLIST.md` is usually enough, and `PLAN.md` can stay one-screen and route-focused.
If the route, command path, fallback, or trust judgment changes materially, revise the plan before spending more compute.
If a quest already depends on `analysis_plan.md` or `REPRO_CHECKLIST.md`, keep that compatibility alias explicit rather than splitting truth across two active plans.

## Durable outputs and paths

The stage should leave one accepted baseline or one explicit blocker.

- `PLAN.md` and `CHECKLIST.md` when the route is non-trivial
- `setup.md` when environment or layout choices are non-trivial
- `execution.md` is optional unless the run is long, multi-step, or rerun-heavy
- `verification.md` is optional as a filename but required in substance
- `attachment.yaml` is required for attached or imported baselines
- `<baseline_root>/json/metric_contract.json` is the canonical accepted comparison contract
- one accepted baseline artifact or one explicit blocked report
- one concise `1-2` sentence summary naming trust state and next anchor

## File-by-file contract

- `PLAN.md` or compatibility alias `analysis_plan.md` is the route contract for non-trivial baseline work
- `CHECKLIST.md` or compatibility alias `REPRO_CHECKLIST.md` is the living baseline frontier
- `setup.md` is optional unless environment or layout choices are non-trivial
- `execution.md` when the run is long, multi-step, or rerun-heavy
- `verification.md` as a filename when a separate verification note is clearer
- `attachment.yaml` for attached or imported baselines
- `<baseline_root>/json/metric_contract.json` as the canonical accepted comparison contract

## Baseline identity note

Keep baseline identifiers and variant names stable enough that later stages can cite the same comparator without guesswork.

## Baseline id and variant rules

- keep `baseline_id` short, stable, and filesystem-safe
- prefer one baseline id with stable variant names over many near-duplicate ids
- if multiple comparators exist, mark which one is the primary downstream baseline

## Route choice

Choose the route that maximizes trust per unit time and compute; do not follow a fixed ritual.

- attach when a trustworthy reusable baseline already exists
- import when a package or bundle is already available and readable
- verify local existing when a local code path or service is already concrete enough to validate cheaply
- reproduce when reuse would leave too much ambiguity in the comparison contract
- repair when an existing baseline line is close enough that bounded fixes are cheaper than a clean restart

Prefer reuse over redundant reproduction, but prefer reproduction or repair only when reuse would still leave the baseline incomparable.
Do not replace a working comparison-ready comparator with a heavier route merely because the heavier route feels cleaner or more complete.

## Workflow

### Phase 1. Analysis

Before running anything substantial, determine:

- exact task
- dataset and split contract
- metric contract scope
- source baseline identity or concrete local comparator
- expected run command or evaluation path

Default analysis discipline:

- If source reproduction or repair is the chosen route, read the source paper and source repo first.
- if the user or runtime already points to a credible comparator candidate, validate that object before broad source reproduction
- identify the real run or evaluation entrypoint
- define the cheapest credible proof step, which may be a smoke test, direct verification, or the real run

Escalate to a fuller audit only when the command path is unclear, the repo is large or confusing, repair mode is active, or custom code changes look likely.

### Phase 2. Setup

Prepare the selected route:

- attach: validate the selected baseline identity
- import: place the imported baseline metadata under the quest and confirm the package is readable
- reproduce: prepare the baseline work directory, commands, config pointers, and environment notes
- repair: identify the precise broken point before rerunning blindly

For Python baselines, prefer `uv` unless a repo-native route is clearly more trustworthy or required.

### Python environment rule: prefer `uv`

### Python environment rule: use `uv`

For Python baselines, environment setup should be standardized around `uv` unless a repo-native route is concretely more trustworthy or required.

- use `uv sync` when the repo already ships a trustworthy `pyproject.toml` or lockfile
- otherwise create an isolated environment with `uv venv`
- install extra dependencies with `uv pip install ...`
- run setup, smoke, and validation commands with `uv run ...`
- prefer `uv run python ...` or `uv run bash ...` over relying on shell activation state
- prefer a quest-local or baseline-local environment over global shell state
- switch only when a repo-native conda, docker, or poetry route is concretely more trustworthy or required
- only accept a non-`uv` route when there is a concrete blocker or a clearly more trustworthy repo-native path

Setup should record:

- baseline id and source identity
- working directory and config files
- command template and expected outputs
- chosen `uv` route and Python version
- known deviations from the paper or source package

### Phase 3. Execution

Run only the work required to establish the baseline credibly.

Execution rules:

- keep commands auditable and avoid uncontrolled side experiments
- use one bounded smoke test only when command, environment, or evaluator risk is still unresolved
- once the path is trusted enough, launch the real run with `bash_exec(mode='detach', ...)` and inspect managed sessions instead of rerunning blindly
- do not report final success until the command actually finished and the expected result files exist

Long-running execution discipline:

- once the smoke passes, prefer one real detached run over repeated foreground retries
- if you need the active job ids or saved sessions, use `bash_exec(mode='history')` or `bash_exec(mode='list')`
- for monitoring, prefer `bash_exec(mode='read', id=..., tail_limit=..., order='desc')` and then incremental checks instead of rereading the whole log
- if a run is clearly invalid, wedged, or superseded, stop it cleanly and relaunch with the new route rather than stacking more retries
- do not let more than the `30-minute visibility bound` pass without one real inspection and one explicit next expected update time

Retry discipline:

- treat baseline smoke work as a `0-2` budget
- allow a second smoke only after a real change in code, command path, environment, or evaluator wiring
- if the same failure class returns, stop looping
- do not rerun the same unchanged smoke command just to reconfirm the same fact

### Phase 4. Verification

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

Verification should explicitly separate:

- likely implementation mismatch
- environment mismatch
- data or split mismatch
- expected stochastic variance
- unexplained divergence

If later `experiment` work would still have to guess the comparison contract, the baseline is not ready.
For a compact verdict rubric, read `references/comparability-contract.md`.

## Core metric contract

The baseline stage is not complete just because something ran.
It is complete when later stages can compare against it fairly.

Before declaring a baseline usable, make the core comparison contract explicit:

- task identity
- dataset identity and split contract
- evaluation script or evaluation path
- required metric keys for the current downstream comparison
- metric directions
- source commit or source package identity
- known deviations from the source reference

Unless the user explicitly specifies otherwise, treat the original paper's evaluation protocol as the canonical starting point.
If any of these fields are still materially unknown, do not pretend the baseline is a clean downstream reference.
`<baseline_root>/json/metric_contract.json` is the canonical accepted comparison contract.
A core contract is enough to confirm a `comparison_ready` baseline; expand it later when paper claims, registry publication, or variant-heavy comparison need more coverage.

## Trust note

Treat the acceptance verdict conservatively: trusted now, trusted with caveats, or blocked, but never silently upgrade a degraded result.

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

Metric-contract rules:

- keep `primary_metric` as the headline metric only; do not let it erase the rest of the comparison surface
- when confirming a baseline, submit the canonical `metrics_summary` as a flat top-level dictionary keyed by the paper-facing metric ids
- every canonical baseline metric entry should include `description`, either `derivation` or `origin_path`, and `source_ref`
- mark only the currently required canonical metrics as required; additional metrics can be added later or kept supplementary
- if the accepted baseline contract already needs multiple metrics, datasets, subtasks, or splits, record them in `<baseline_root>/json/metric_contract.json`
- if the paper reports both aggregate and per-dataset or per-task results, preserve both whenever feasible through `metrics_summary` plus structured rows rather than one cherry-picked scalar
- if the source package already has a richer leaderboard table, structured result file, or `json/metric_contract.json`, reuse that richer contract instead of hand-writing a thinner one that keeps only one averaged scalar
- `Result/metric.md` is optional temporary scratch memory only; reconcile against it before calling `artifact.confirm_baseline(...)`, but do not treat it as a required durable file
- for stable accepted payload shapes, read `references/artifact-payload-examples.md`

## Reuse note

Reuse or publish a baseline only after verification is complete and the current quest no longer depends on guesswork about provenance or comparability.
Do not publish a baseline for reuse if verification is incomplete, metrics are untrusted, or provenance is still weak.

## Memory note

Use memory only to avoid repeating known failures or to preserve reusable baseline lessons, not as a required step before every validation pass.
Write quest memory for route rationale, setup failures, paper-to-code mismatch notes, and accepted caveats that later stages must carry forward.
Promote to global memory only when another quest is likely to benefit from the lesson.

## Failure and blocked handling

Do not hide failures.

If blocked, record the class explicitly when possible:

- `missing_source`
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

Bounded autonomous fixes are acceptable only when they do not change confirmed scope, metrics, permissions, or resource assumptions.
Reasonable bounded fixes include missing dependency installs, wrong dataset paths, permission fixes on scripts, obvious environment activation mistakes, and conservative batch-size reductions for OOM.

## Exit criteria

Exit the baseline stage once one of the following is durably true:

The default exit rule is simple: once one comparator clears the current acceptance target, baseline should usually end.
Do not continue baseline just because the route could be cleaner, more complete, or more reusable in the abstract.


- a baseline is attached and accepted
- an imported baseline is accepted
- a verified local-existing comparator is accepted
- a reproduced baseline is verified and accepted
- a broken route has been declared blocked and a next decision is recorded
- a waiver decision explicitly leaves the baseline gate

Typical next anchors:

- `idea`
- `experiment` in tightly scoped follow-on cases
- `decision` if the baseline line remains contested

A good baseline pass leaves one trusted comparator, one explicit blocker, or one explicit route change, not a vague promise to keep rechecking baseline.
