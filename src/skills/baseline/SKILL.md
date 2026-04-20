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

Follow the shared interaction contract injected by the system prompt.
Follow the shared interaction contract and keep baseline updates brief unless trust state, blocker state, route, cost, or user-facing risk changed materially.

## Tool discipline

- **Do not use native `shell_command` / `command_execution` in this skill.**
- **All shell, CLI, Python, bash, node, git, npm, uv, and environment work must go through `bash_exec(...)`.**
- **For git work inside the current quest repository or worktree, prefer `artifact.git(...)` before raw shell git commands.**
- **If a generic git smoke test is needed outside the quest repo, use `bash_exec(...)` in an isolated scratch repository.**
- Use web search for discovering papers or repos, but use `artifact.arxiv(paper_id=..., full_text=False)` for actually reading a source arXiv paper when it exists.
- Set `full_text=True` only when the short form is insufficient.

## Authority and freedom

The agent owns the execution path.
It may choose the workspace layout, environment manager, command order, debugging route, smoke strategy, local paths, and whether the best route is attach, import, verify-local-existing, reproduce, or repair.

Do not treat templates, filenames, `uv`, smoke tests, detached runs, or the phase order as required paths.
They are tactics.
The hard requirement is objective evidence sufficient to accept, block, waive, or switch the baseline route.

Ask the user only when the next move depends on a real scope, cost, permission, data-access, or scientific-preference decision that cannot be inferred from the quest contract.
Ordinary route, path, environment, and debugging choices are autonomous unless they change the accepted comparison meaning.

## Comparator-first rule

The baseline stage is comparator-first, not reproduction-first.
For `comparison_ready`, the default question is:

- what is the lightest trustworthy comparator?

not:

- how do I reproduce the whole source package most completely?

Default to the lightest baseline path that can still support a fair downstream comparison.
Default to a fast path when it can establish trust with less work.
Do not escalate from attach / import / verify-local-existing into full source reproduction unless the lighter route cannot support a fair comparison.
A more complete baseline package is only the default when the acceptance target is explicitly `paper_repro_ready` or `registry_publishable`.

- Attach/import/publish alone do not open the downstream gate.
- If reusing a registry baseline, first materialize it with `artifact.attach_baseline(...)` when available, then verify the comparator and metric contract, then call `artifact.confirm_baseline(...)`.
- If publishing a quest-local baseline for reuse, call `artifact.publish_baseline(...)` only after verification is complete and provenance, metrics, and caveats are trustworthy.
- Once the accepted baseline root and trusted comparison contract are clear, call `artifact.confirm_baseline(...)`.
- If the quest must continue without a baseline, call `artifact.waive_baseline(...)` with the reason.
- Do not treat chat, memory, `attachment.yaml`, `PLAN.md`, local files, or published registry entries as a substitute for `artifact.confirm_baseline(...)` or `artifact.waive_baseline(...)`.

- do not restart broad baseline discovery by default
- do not front-load a full codebase audit
- do not require a fresh memory pass for every fast-path validation
- fast-path exception: if you are resuming a previously blocked or ambiguous route, recover the relevant memory before trusting the old path again
- use `memory.list_recent(...)` or `memory.search(...)` when resuming, reopening old command paths, or avoiding repeated failures
- if runtime already exposes `requested_baseline_ref` or a matching `confirmed_baseline_ref`, default to reuse-and-verify
- escalate to fuller audit, reproduction, or repair only when no concrete comparator, command path, or core comparability surface can be trusted yet

For route examples and artifact examples, read `references/route-selection.md`, `references/artifact-flow-examples.md`, and `references/boundary-cases.md`.

- the comparator identity is explicit and stable enough for later stages to cite
- the task, dataset, split, evaluation path, required metric ids, metric directions, source identity, and known deviations are durably recorded
- trusted metric values or trusted output pointers are traceable to real files, logs, service responses, source artifacts, or an accepted registry/package record
- verification checked that the evidence came from the intended dataset/split and metric definitions
- `<baseline_root>/json/metric_contract.json` exists as the canonical accepted comparison contract
- `artifact.confirm_baseline(...)` opened the gate, or `artifact.waive_baseline(...)` explicitly bypassed it

- no credible baseline exists yet
- the current baseline is unverified or stale
- the user already has a baseline package that should be attached or imported
- a local code path or local service should be verified as the comparator
- a reproduction failed earlier and now needs repair
- the quest resumed and the baseline trust state is unclear

## Acceptance targets

- `comparison_ready`: the default target; one comparator is trustworthy enough for downstream comparison
- `paper_repro_ready`: the baseline supports paper-facing reproduction or comparison claims
- `registry_publishable`: the package is reusable enough to publish as a durable baseline package
- `blocked`: the route cannot clear the gate cleanly and the next move is explicit
- `waived`: the quest continues without a baseline for a recorded reason

## Hard acceptance gates

Baseline success means later stages can compare against one accepted comparator without guessing task, data, split, metric, source, command or evaluation path, provenance, or caveats.

A baseline is successful only when all applicable gates are true:

- the comparator identity is explicit and stable enough for later stages to cite
- the task, dataset, split, evaluation path, required metric ids, metric directions, source identity, and known deviations are durably recorded
- trusted metric values or trusted output pointers are traceable to real files, logs, service responses, source artifacts, or an accepted registry/package record
- verification has checked that the evidence came from the intended dataset/split and metric definitions
- the accepted comparison contract is written to `<baseline_root>/json/metric_contract.json`
- the baseline gate is opened with `artifact.confirm_baseline(...)`, or intentionally bypassed with `artifact.waive_baseline(...)`

Attach, import, or publish alone do not open the downstream gate.
The comparison-ready minimum still requires `<baseline_root>/json/metric_contract.json`.
Once a comparison-ready baseline is durably confirmed, baseline should usually stop immediately and hand off to the next scientific step.
Any extra baseline work after that must name one explicit unresolved comparison risk it is meant to remove.

## Acceptance targets

- `comparison_ready`: the default target; one comparator is trustworthy enough for downstream comparison, and the core metric contract is durably recorded
- `paper_repro_ready`: the baseline is strong enough to support paper-facing reproduction or comparison claims
- `registry_publishable`: the baseline package is reusable and clean enough to publish as a durable baseline package
- `blocked`: the current route cannot clear the gate cleanly, and the next move is explicit
- `waived`: the quest must continue without a baseline, and the reason is durably recorded

Not every baseline needs a paper-grade exact reproduction.
A verified attached/imported/local-existing comparator can be enough when the acceptance target is only `comparison_ready`.

## Route success criteria

Choose the route that maximizes trust per unit time and compute; do not follow a fixed ritual.
Keep one dominant baseline route active at a time.
If a lighter route already satisfies the current acceptance target, stop there.

- `attach` succeeds when baseline identity, provenance, trusted outputs pointer, core metric contract, and accepted baseline artifact are explicit
- `import` succeeds when the package is materialized/readable inside the quest, `attachment.yaml` or equivalent provenance exists, and trusted outputs or metrics are traceable
- `verify-local-existing` succeeds when the concrete local path or service, exact command or evaluation endpoint, output location, required metrics, and core metric contract are verified
- `reproduce` succeeds when source identity, command or evaluation path, expected outputs, verification evidence, deviations, and metric contract are explicit
- `repair` succeeds when the broken point is identified, a bounded fix or route change is made, rerun or re-read evidence supports the new trust state, and the result is accepted or blocked

Prefer reuse over redundant reproduction, but prefer reproduction or repair when reuse would still leave the baseline incomparable.
Do not replace a working comparison-ready comparator with a heavier route merely because the heavier route feels cleaner or more complete.

## Objective evidence requirements

The stage may use any efficient path, but the final evidence must cover these facts before acceptance:

- comparator candidate and baseline id
- source paper, source repo, source commit/version/tag, local service identity, or registry/package identity as applicable
- task identity
- dataset identity and split contract
- evaluation script, evaluation endpoint, or evaluation path
- required metric keys for the current downstream comparison
- metric directions
- metric values or trusted output pointers
- environment and hardware facts that materially affect comparability
- known deviations from the paper, source package, local reference, or selected target
- verification verdict and caveats

Unless the user explicitly specifies otherwise, treat the original paper's evaluation protocol as the canonical starting point.
If later `experiment` work would still have to guess the comparison contract, the baseline is not ready.
For a compact verdict rubric, read `references/comparability-contract.md`.

## Verification

Verification is mandatory before baseline acceptance.

Verify:

- the run, service call, package import, or trusted-output inspection actually finished
- the reported metrics came from the intended dataset and split
- metric definitions and directions match the quest contract
- the result is comparable to the paper, source repo, local comparator, registry package, or selected target
- deviations are explicitly stated rather than silently normalized away

Classify the outcome as one of:

- `verified_match`
- `verified_close`
- `verified_diverged`
- `trusted_with_caveats`
- `broken`

Verification should explicitly separate likely implementation mismatch, environment mismatch, data or split mismatch, expected stochastic variance, and unexplained divergence when those distinctions matter.

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

`<baseline_root>/json/metric_contract.json` is the canonical accepted comparison contract.
A core contract is enough to confirm a `comparison_ready` baseline; expand it later when paper claims, registry publication, or variant-heavy comparison need more coverage.

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
- submit canonical `metrics_summary` as a flat top-level dictionary keyed by the paper-facing metric ids
- every canonical baseline metric entry should include `description`, either `derivation` or `origin_path`, and `source_ref`
- mark only the currently required canonical metrics as required; additional metrics can be added later or kept supplementary
- if the accepted baseline contract already needs multiple metrics, datasets, subtasks, or splits, record them in `<baseline_root>/json/metric_contract.json`
- if the paper reports both aggregate and per-dataset or per-task results, preserve both whenever feasible through `metrics_summary` plus structured rows rather than one cherry-picked scalar
- if the source package already has a richer leaderboard table, structured result file, or `json/metric_contract.json`, reuse that richer contract instead of hand-writing a thinner one that keeps only one averaged scalar
- `Result/metric.md` is optional temporary scratch memory only; reconcile against it before calling `artifact.confirm_baseline(...)`, but do not treat it as a required durable file
- for stable accepted payload shapes, read `references/artifact-payload-examples.md`

## Durable route records

Durable records are required in substance, not in fixed filenames.
The agent may choose the shortest durable form that lets a later turn resume without guessing.

For non-trivial, code-touching, expensive, unstable, or long-running baseline work, leave a route record that states:

- chosen route and acceptance target
- comparator identity and source identity
- command or evaluation path if one exists
- expected outputs or trusted-output pointers
- acceptance condition
- current blocker or fallback
- verification verdict

`PLAN.md`, `CHECKLIST.md`, `setup.md`, `execution.md`, `verification.md`, `analysis_plan.md`, and `REPRO_CHECKLIST.md` are allowed compatibility surfaces, not mandatory success paths.
Use `references/baseline-plan-template.md` and `references/baseline-checklist-template.md` when they help, but do not expand them as paperwork.

`attachment.yaml` or equivalent provenance is required for attached or imported baselines.
`<baseline_root>/json/metric_contract.json` as the canonical accepted comparison contract is required for accepted baselines.

## Execution tactics

Use whatever route is most faithful, observable, and efficient while preserving the hard gates.

- If source reproduction or repair is actually the active route, read the source paper and source repo before substantial setup.
- For attach, import, or verify-local-existing, inspect only the minimum evidence needed to trust the provided or local comparator.
- A bounded smoke test is usually helpful only when command path, environment viability, evaluator wiring, or output schema is still unclear.
- If the path is already concrete, go straight to real verification or the real run.
- Treat smoke/pilot work as a `0-2` default budget, but the real rule is not to repeat an unchanged check without new evidence, a code/environment change, or a route change.
- If runtime is uncertain or likely long, prefer `bash_exec(mode='detach', ...)` plus managed monitoring instead of pretending a short foreground timeout is enough.
- If a run is clearly invalid, wedged, or superseded, stop it cleanly and relaunch with the new route rather than stacking more retries.

## Environment tactics

For Python baselines, prefer a reproducible isolated environment, but choose the route that is most faithful to the source package and most likely to produce comparable evidence.

`uv` is a useful default tactic when the repo does not require a stronger native route.
Examples include `uv sync`, `uv venv`, `uv pip install ...`, and `uv run ...`.
Switch to repo-native conda, docker, poetry, shell scripts, service startup, or another local environment route when that is clearly more trustworthy, required by the source, or necessary to match the paper/package behavior.

Record only environment facts that affect trust or comparability.
Do not force a global `uv` route when it would make the reproduced baseline less faithful.

## Negative cases and stop rules

Do not accept a baseline when:

- metrics are fabricated, copied, or paraphrased without provenance
- metrics are copied from a paper while the acceptance target requires local verification
- dataset, split, metric direction, or evaluation path is materially unknown
- outputs exist but cannot be tied to the intended command, source, comparator, package, or service
- a local run completed but used a materially different protocol without a recorded caveat
- source code was modified in a way that changes baseline scope without recording the deviation
- a package imports but trusted metrics or outputs are not traceable
- later experiment work would still need to guess the required baseline metric ids
- the same failure class reappears without new evidence, code changes, environment changes, or a route change

If the same failure class appears again without new evidence, code changes, environment changes, or a route change, stop looping and route through `repair`, `decision`, `blocked`, `waive`, or one bounded clarification.
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
- whether the next best move is attach, import, retry, repair, reset, waive, or ask the user

Bounded autonomous fixes are acceptable only when they do not change confirmed scope, metrics, permissions, resource assumptions, or scientific meaning.
Reasonable bounded fixes include missing dependency installs, wrong dataset paths, permission fixes on scripts, obvious environment activation mistakes, and conservative batch-size reductions for OOM.

## Reuse and memory

Reuse or publish a baseline only after verification is complete and the current quest no longer depends on guesswork about provenance or comparability.
Do not publish a baseline for reuse if verification is incomplete, metrics are untrusted, or provenance is still weak.

Use memory only to avoid repeating known failures or to preserve reusable baseline lessons, not as a required step before every validation pass.
Write quest memory for route rationale, setup failures, paper-to-code mismatch notes, and accepted caveats that later stages must carry forward.
Promote to global memory only when another quest is likely to benefit from the lesson.

## Baseline id and variant rules

Keep baseline identifiers and variant names stable enough that later stages can cite the same comparator without guesswork.

- keep `baseline_id` short, stable, and filesystem-safe
- prefer one baseline id with stable variant names over many near-duplicate ids
- if multiple comparators exist, mark which one is the primary downstream baseline

## Exit criteria

Exit once one of these is durably true:

- a baseline is attached and accepted
- an imported baseline is accepted
- a verified local-existing comparator is accepted
- a reproduced baseline is verified and accepted
- a repaired baseline is verified and accepted
- a broken route has been declared blocked and a next decision is recorded
- a waiver decision explicitly leaves the baseline gate
- a route change is recorded because the previous route is no longer the best trust-per-cost path

Typical next anchors:

- `idea`
- `experiment` in tightly scoped follow-on cases
- `decision` if the baseline line remains contested

A good baseline pass leaves one trusted comparator, one explicit blocker, or one explicit route change, not a vague promise to keep rechecking baseline.
