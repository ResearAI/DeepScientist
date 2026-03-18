---
name: baseline
description: Use when a quest needs to attach, import, reproduce, repair, verify, compare, or publish a baseline and its metrics.
---

# Baseline

This skill establishes the reference system the quest will compare against.
It absorbs the essential old DeepScientist reproducer discipline into one stage skill.

## Interaction discipline

- Treat `artifact.interact(...)` as the main long-lived communication thread across TUI, web, and bound connectors.
- If `artifact.interact(...)` returns queued user requirements, treat them as the highest-priority user instruction bundle before continuing baseline work.
- Immediately follow any non-empty mailbox poll with another `artifact.interact(...)` update that confirms receipt; if the request is directly answerable, answer there, otherwise say the current subtask is paused, give a short plan plus nearest report-back point, and handle that request first.
- Emit `artifact.interact(kind='progress', reply_mode='threaded', ...)` when there is real user-visible progress: the first meaningful signal of long work, a meaningful checkpoint, or a concise keepalive if active work has drifted beyond roughly 10 to 30 tool calls without a user-visible update.
- Keep progress updates chat-like and easy to understand: say what changed, what it means, and what happens next.
- Default to plain-language summaries. Do not mention file paths, artifact ids, branch/worktree ids, session ids, raw commands, or raw logs unless the user asks or needs them to act.
- Message templates are references only. Adapt to the actual context and vary wording so updates feel natural and non-robotic.
- Use `reply_mode='blocking'` only for real user decisions that cannot be resolved from local evidence.
- For any blocking decision request, provide 1 to 3 concrete options, put the recommended option first, explain each option's actual content plus pros and cons, and wait up to 1 day when feasible. If the blocker is a missing external credential or secret that only the user can provide, keep the quest waiting, ask the user to supply it or choose an alternative, and do not self-resolve; if resumed without that credential and no other work is possible, a long low-frequency wait such as `bash_exec(command='sleep 3600', mode='await', timeout_seconds=3700)` is acceptable. Otherwise choose the best option yourself and notify the user of the chosen option if the timeout expires.
- If a threaded user reply arrives, interpret it relative to the latest baseline progress update before assuming the task changed completely.
- Prefer `bash_exec` for setup, reproduction, and verification commands so each baseline action keeps a durable quest-local session id and log trail.
- When the baseline route is durably chosen, confirmed, waived, or blocked with a clear next action, send one richer `artifact.interact(kind='milestone', reply_mode='threaded', ...)` update that says whether the baseline is trusted, blocked, or waived, why that matters, and what the next stage is.

## Non-negotiable rules

- no fabrication of metrics, logs, run status, or success claims
- do not skip baseline steps or silently simplify the reproduction path without explicit approval
- do not claim a baseline is ready before verification is complete
- do not infer missing commands, scripts, or parameters when the uncertainty would change the result
- any unavoidable guess must be written down explicitly with expected impact
- use web search for discovering papers or repos, but use `artifact.arxiv(paper_id=..., full_text=False)` for actually reading a source arXiv paper when it exists
- set `full_text=True` only when the summary/abstract view is insufficient for the needed detail; do not default to the raw PDF

## Language and interaction rules

- match the user's language in all visible outputs
- keep updates concise but concrete
- if a structured user decision is required, ask only for decisions that the system cannot safely derive locally
- do not ask speculative or premature questions when local analysis can narrow the choices first

## Priority workflow

Default to the lightest baseline path that can still establish a trustworthy comparison.
Do not front-load a full reproduction dossier when a faster truth-finding step would tell you whether the route is even viable.

The ordinary baseline order is:

1. confirm quest binding and current baseline state
2. look for the cheapest trustworthy route in order: attach, import, reproduce, repair
3. capture the minimum viable contract: task, dataset or split, metric, source identity, expected command path, and main risks
4. run a bounded smoke test as soon as that contract is concrete enough
5. only after the smoke test is credible, expand setup notes and launch the real run
6. verify before accepting
7. archive, publish, or attach the result when appropriate

Escalate to the heavier baseline path only when the baseline is ambiguous, broken, multi-variant, paper-to-repo mismatched, or likely to be reused beyond the current quest.

If the quest is not yet bound to a stable baseline context, do not pretend the stage is ready just because some code exists locally.

## Stage purpose

The baseline stage should produce a usable reference point through one of four routes:

- attach an existing reusable baseline
- import a reusable baseline package
- reproduce a baseline from source
- repair a broken or stale baseline

The stage must preserve the classic four-part reproducer flow:

1. analysis
2. setup
3. execution
4. verification

Do not casually skip these gates.

## Phase routing rule

Treat `analysis`, `setup`, `execution`, and `verification` as logical control gates, not paperwork walls.
At any moment, the work should have one dominant phase among:

- `analysis`
- `setup`
- `execution`
- `verification`

Keep the dominant phase explicit, but allow small backtracks and lightweight overlap when they reduce wasted work.
Do not delay an early smoke test just because a fuller write-up is not done yet.
Before a real long run, make sure the minimum viable contract is explicit and the active phase is still easy to reconstruct.

## Use when

- no credible baseline exists yet
- the current baseline is unverified or stale
- the user already has a baseline package that should be attached or imported
- a reproduction failed earlier and now needs repair
- the quest was resumed and the baseline trust state is unclear

## Do not use when

- the quest already has a verified active baseline and the next move is ideation or execution
- the user explicitly waived the baseline gate and that waiver is durably recorded

## Stage gate

Do not proceed to `idea` or `experiment` unless one of the following is durably true:

- a baseline has been attached and accepted
- a baseline has been imported and accepted
- a baseline reproduction has completed and been verified
- an explicit waiver decision exists with a clear reason

Operationally, the canonical exit is stricter:

- after the accepted baseline root is clear, call `artifact.confirm_baseline(...)`
- if the quest must continue without a baseline, call `artifact.waive_baseline(...)`

`attach`, `import`, `publish`, or a plain `baseline` artifact alone do not open the downstream gate.

## Truth sources

Use the following as baseline truth sources:

- user objective and task framing
- source paper and official repo when available
- existing baseline registry entries
- local baseline directories under `quest_root`
- repo code, configs, and scripts
- device and environment constraints detected locally
- logs, metrics, and summaries from actual runs

Do not treat memory alone as sufficient evidence for baseline readiness.

## Baseline workspace rules

- treat the baseline workspace as a system-managed reproduction surface, not an unrelated sandbox
- avoid creating nested Git workflows inside the baseline workspace
- keep the authoritative quest history in the quest repo
- if papers are converted or notes are generated during baseline work, keep the durable copies under the quest-visible artifacts area unless there is a strong reason to keep a baseline-side copy
- if runtime environment variables or secrets are provided by the runner, use them as authoritative but never echo or persist secret values

The baseline line should also maintain a durable working-record area outside the execution surface.
Recommended quest-visible records include:

- `analysis_plan.md` or a compact equivalent section in `execution.md`
- `setup.md`
- `execution.md`
- `verification.md`
- `STRUCTURE.md` only when the workspace layout is non-obvious or later reuse depends on it
- `REPRO_CHECKLIST.md` only when the route is complex, repair-heavy, multi-variant, or publication-facing

For a simple attach/import flow or a straightforward reproduce flow, do not stall just to precreate every one of these files.
Start with the smallest durable note that preserves the route, command path, target outputs, and main risks; expand it only after the route proves real.

## Required durable outputs

The baseline stage should usually leave behind:

- a baseline directory under `baselines/local/` or `baselines/imported/`
- a verification note or report under the quest
- command, config, environment, and metrics pointers
- a baseline artifact
- a confirmed baseline gate via `artifact.confirm_baseline(...)`, or an explicit waiver via `artifact.waive_baseline(...)`
- an optional registry publication if the baseline is reusable beyond this quest

## Stable execution contract

To keep baseline work stable across different quests, do not stop at loose prose.
But also do not confuse stability with ceremony.
Use the lightest durable structure that keeps the baseline auditable and reusable.

Minimum stability rules:

- before the first real run, leave one durable note with the chosen route, expected command path, target outputs, and main risks
- after each smoke test or real run, record what actually happened and whether the route still looks viable
- before acceptance, leave a clear verification note and baseline gate decision
- every route selection should leave one explicit reasoned decision record
- every accepted baseline should leave one accepted baseline artifact
- every blocked baseline line should leave one blocked report and one next-step decision
- every handoff should name the active baseline reference and trusted metric set explicitly
- do not require every optional checklist or template before the first smoke test
- if one rolling note is enough for a simple baseline line, use it

Recommended phase-to-output mapping:

- `analysis` -> a brief `analysis_plan.md` or equivalent compact route note, plus optional route decision artifact
- `setup` -> `setup.md` when setup choices are non-trivial
- `execution` -> `execution.md` plus progress artifacts when long-running
- `verification` -> `verification.md` plus accepted baseline artifact and `artifact.confirm_baseline(...)`, or a blocked report plus `artifact.waive_baseline(...)` when skipping is intentional

If the work skips one of these durable outputs, explain why the baseline remains interpretable without it.

## Durable path contract

The baseline stage should use the real runtime paths consistently.

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

Do not invent parallel durable locations when these runtime contracts already exist.
Do not leave the authoritative metric contract only in chat, memory, or prose once the baseline is accepted.

If a baseline is reproduced only because an analysis campaign needs an extra comparator:

- still place it under `<quest_root>/baselines/local/<baseline_id>/` or `<quest_root>/baselines/imported/<baseline_id>/`
- treat it as a supplementary analysis baseline unless the quest explicitly promotes it into the canonical gate
- do not call `artifact.confirm_baseline(...)` for that supplementary case unless the quest truly intends to replace the canonical baseline

## Baseline id and variant rules

Baseline identity should be stable and path-safe.

- `baseline_id` should be short, stable, and filesystem-safe
- use letters, digits, `.`, `_`, or `-`
- do not use spaces, `/`, `\\`, or `..`
- if one codebase contains multiple comparable baselines, use one `baseline_id` with structured variants instead of inventing many unrelated entries

When variants exist, maintain at least:

- `default_variant_id`
- `baseline_variants`
- per-variant metric summaries when available

The baseline stage should treat `baseline_id` and `variant_id` as durable references that later `idea`, `experiment`, and `write` stages can cite directly.

## Baseline route order

Prefer this order:

1. attach
2. import
3. reproduce
4. repair

Prefer reuse over redundant reproduction.

## Route selection rules

Choose the route explicitly rather than by habit.

- choose `attach` when a published baseline already exists in the registry and its metrics or provenance are trustworthy enough for the quest
- choose `import` when the user or repo provides a reusable baseline package or bundle that is not yet attached to the current quest
- choose `reproduce` when no trustworthy reusable baseline is available but the source repo, paper, and evaluation path are concrete enough to establish one
- choose `repair` when a baseline route already exists but failed, drifted, or is only partially complete and the broken point is bounded enough to diagnose directly

Do not default to reproduction if attach or import would establish an equally trustworthy reference with less risk and cost.

Before locking the route, explicitly answer:

- what object is being reused or established
- what makes it trustworthy enough for downstream comparison
- what evidence is missing
- what the cheapest credible next step is

For a more explicit route-selection rubric, read `references/route-selection.md`.

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

If any of these are still materially unknown, do not pretend the baseline is a clean downstream reference.

Use `references/comparability-contract.md` for the full checklist.

## Feasibility and acceptance classes

Before accepting a baseline, classify feasibility as one of:

- `full_reproducible`
- `degraded_but_acceptable`
- `blocked`

And classify downstream trust as one of:

- `verified`
- `partially_verified`
- `operational_but_incomparable`
- `failed`

Rules:

- `full_reproducible` means the baseline can be reproduced within the agreed contract
- `degraded_but_acceptable` means the quest explicitly allows a bounded degraded gate
- `blocked` means insufficient assets, compute, or environment to produce an acceptable baseline
- `verified` means trusted for downstream comparison
- `partially_verified` means useful but still caveated
- `operational_but_incomparable` means it runs, but the comparison contract is not stable enough yet
- `failed` means it should not be used downstream

Do not silently upgrade a degraded or only operational result into a normal trusted baseline.

## Multi-baseline policy

One quest may legitimately need more than one baseline reference.

Common roles include:

- primary comparison baseline
- strongest literature baseline
- cheapest operational fallback baseline

If more than one baseline exists, explicitly record:

- which one is the primary downstream comparison
- which one is only a fallback or infrastructure reference
- why the primary choice is the fairest or strongest comparison

Do not leave later stages guessing which baseline is authoritative.

When useful, record the route choice as a decision artifact with action such as:

- `attach_baseline`
- `reuse_baseline`
- `publish_baseline`
- `continue`
- `request_user_decision`

## Workflow

### Phase 1. Analysis

Before running anything substantial, determine:

- exact task
- dataset and split contract
- metric contract
- source baseline identity
- source code path
- expected run command or evaluation path
- expected paper or repo numbers, if any
- local resource constraints

For straightforward baseline work, start with a quick viability pass:

- find the real run or evaluation entrypoint
- identify the dataset/split and metric contract
- identify likely environment blockers
- define the cheapest credible smoke test

Escalate from that quick pass to a fuller baseline codebase audit when the command path is unclear, the repo is large or confusing, the paper and code diverge materially, repair mode is active, or custom code changes look likely.

When the fuller audit is necessary, capture at least:

- major modules and files
- end-to-end data flow
- key classes, functions, or scripts
- external dependencies and environment assumptions
- computational hotspots or obvious bottlenecks
- current evaluation pipeline and metric computation path
- coupling, maintainability, or scalability issues that may slow later iterations

When the source paper is available, also record:

- read it through `artifact.arxiv(paper_id=..., full_text=False)` first, and only switch to `full_text=True` when the shorter view is insufficient
- the core algorithm in compact, implementation-faithful form
- the main reported numbers
- the main weaknesses or bottlenecks likely to matter on the current quest task or dataset

If helpful, restate the core algorithm using two of the following:

- short pseudocode
- a compact equation or objective
- a code-level sketch tied to real files

The goal is not academic polish.
The goal is that later `idea`, `experiment`, and `write` stages can understand what the baseline actually does without reopening the whole repo from scratch.

You should inspect local feasibility with shell-based checks when needed, including:

- OS
- GPU availability
- CPU and RAM
- free disk
- Python or conda environment availability

Use the collected constraints to choose a realistic baseline route and runtime plan.

The analysis phase should leave behind a concrete baseline plan rather than only conversational intent.
At minimum, the plan should capture:

- chosen route
- source identity
- expected commands
- expected outputs
- feasibility notes
- key risks
- verification targets

When the analysis note becomes substantial, structure `analysis_plan.md` with headings close to:

- executive summary
- codebase analysis
- limitations or bottlenecks
- KPI and metric contract
- route choice
- risks and mitigations

Analysis-phase questioning rules:

- ask the user only after the analysis is concrete enough to expose real choices
- the early exception is when code access, paper access, source identity, or execution permission is missing and that absence blocks even baseline analysis
- do not ask generic “how should I set up the environment” questions before you inspect the device and code requirements
- do not repeat already confirmed decisions unless the plan materially changed

If a user decision is required, make it structured and compact:

- usually `1-6` questions total
- each question should contain concrete options
- options should reflect actual hardware/code feasibility
- options should include tradeoffs
- the recommended option should be explicit
- free-form input should be requested only where a preset choice is genuinely insufficient

If parallel execution is proposed, it must be explicitly confirmed rather than silently enabled.

Avoid asking the user to design the environment for you.
Instead, analyze the environment first, then present the recommended path and tradeoffs only if a user decision is actually required.

If the code, paper, or baseline source is missing and the missing piece changes the route materially, stop and ask for a structured decision rather than guessing.

For a denser audit checklist, read `references/codebase-audit-checklist.md`.

### Phase 2. Setup

Prepare the selected route:

- attach: validate the selected baseline id and variant
- import: place the imported baseline metadata under the quest
- reproduce: prepare the baseline work directory, commands, config pointers, and environment notes
- repair: identify the precise broken point before rerunning blindly

For a fast-path reproduction, setup can stay lightweight.
Confirm the working directory, environment, config, output paths, smoke command, and long-run command, then move forward.
Do not manufacture a fresh workspace tree or copy the repo just to satisfy a template if the existing layout is already workable and auditable.

Capture:

- baseline identifier
- source and provenance
- working directory
- config files
- command template
- expected outputs
- risks and known deviations from the paper or source

Setup should also confirm:

- the intended working directory is correct
- the output paths are durable and quest-visible
- required dependencies or environments are known
- the execution plan is realistic for the detected hardware

If a dedicated baseline workspace is needed, establish a clear layout.
One workable structure is:

```text
<baseline_root>/
  src/
  scripts/
  logs/
    cache/
  results/
  exports/
    latest/
    <run_id>/
```

If the baseline becomes long-lived, shared, or non-obvious, the quest-visible audit area may contain:

```text
<quest_root>/
  baselines/
    local/
      <baseline_id>/
        analysis_plan.md
        setup.md
        execution.md
        verification.md
        STRUCTURE.md
        REPRO_CHECKLIST.md
```

Setup should record:

- how the source was obtained: attach/import/copy/clone
- upstream URL when known
- upstream commit hash when known
- key environment variables by name only, with sensitive values redacted
- the directory tree and key files expected to matter later

If a local source repo was copied into the workspace, preserve provenance but do not keep a nested authoritative Git lifecycle inside the baseline execution root.

If setup reveals that the chosen route is infeasible on the current device, do not brute-force ahead.
Either downgrade scope explicitly, switch route, or request a structured decision.

### Phase 3. Execution

Run only the work required to establish the baseline credibly.

Execution rules:

- keep commands auditable
- keep logs durable
- avoid uncontrolled side experiments during baseline establishment
- if a run is long, emit progress artifacts at meaningful checkpoints
- if setup required code changes, checkpoint only explainable, minimal changes

Execution should rely on existing explicit scripts or command paths where possible.
Prefer the smallest runnable command that proves the baseline route.
Do not build a new wrapper, registry, or result-export scaffold unless existing commands are missing, repeated reruns justify it, or later automation clearly needs it.
If a wrapper or entry script is truly needed, it should support most of the following:

- run mode for missing combinations
- print-only mode that summarizes existing results without rerunning everything
- result registry or skip logic so old baseline results are not re-executed unnecessarily
- export of per-run results and a `latest/` snapshot
- final Markdown and/or JSON summary output
- cache and debug logs
- environment checks when relevant
- throttled structured progress markers for long loops
- `--new-only` or equivalent incremental mode
- `--rerun` or equivalent force-rerun mode when needed
- scope flags such as minimal/full/custom when the analysis plan distinguishes them
- speed flags such as parallelism, batch size, epochs, or steps when relevant
- optional evaluation and postprocess steps when the repo separates them

If adding this scaffolding would require large assumptions about missing scripts, stop and return to analysis rather than creating a misleading opaque wrapper.

Recommended result structures to maintain:

- per-combination result records
- an aggregated `result.json`
- a registry or JSONL index mapping each combination to its stored result
- exported snapshots in both run-specific and `latest/` locations
- run metadata capturing the environment and command context

Recommended run metadata includes:

- config snapshot
- relevant Git or source snapshot identifiers
- package/environment summary
- machine summary such as GPU visibility when relevant

If a result backup is useful for audit or recovery, create it explicitly rather than assuming the latest export is enough.

Long-running execution rules:

- before a substantial baseline reproduction, run a bounded smoke test first so command paths, output locations, and metric plumbing are validated cheaply
- once the smoke test passes, launch the real baseline reproduction with `bash_exec(mode='detach', ...)` and normally leave `timeout_seconds` unset for the long run itself
- when monitoring that detached run, prefer `bash_exec(mode='read', id=..., tail_limit=..., order='desc')` so you inspect the newest log evidence first
- after the first read, prefer incremental checks with `bash_exec(mode='read', id=..., after_seq=last_seen_seq, tail_limit=..., order='asc')` so you only inspect newly appended evidence
- if you need to recover ids or confirm the newest session quickly, use `bash_exec(mode='history')` or `bash_exec(mode='list')` rather than guessing
- include a structured `comment` on long-running bash sessions with fields such as `stage`, `goal`, `action`, `expected_signal`, and `next_check`
- use `silent_seconds`, `progress_age_seconds`, `signal_age_seconds`, and `watchdog_overdue` from `bash_exec(mode='list'|'read', ...)` as the default staleness checks
- when the reproduction code is under your control, prefer a throttled `tqdm` progress reporter and, when feasible, pair it with periodic `__DS_PROGRESS__` JSON lines carrying phase and ETA
- if a command is expected to run for a long time, monitor it as a real background task rather than assuming success
- do not write final summaries or accepted metrics until the command has actually completed
- verify that the expected result files exist before treating the run as finished
- if a task is invalid, wedged, or failed, stop it with `bash_exec(mode='kill', id=..., wait=true, timeout_seconds=...)`; if it must die immediately, add `force=true`, then diagnose the reason and either retry with a documented fix or record the failure durably

Recommended monitoring cadence for long-running work:

- first check after about 60 seconds
- second check after about 120 seconds
- third check after about 300 seconds
- fourth check after about 600 seconds
- fifth check after about 1800 seconds
- after that, keep checking about every 1800 seconds while the run is still active

The exact mechanism should prefer `bash_exec(mode='await' | 'detach' | 'read' | 'list' | 'history' | 'kill', ...)`, with `read` usually using a tailed or incremental window during monitoring, but the behavioral rule stays the same:
do not report completion until the run is actually done and the outputs are real.
After each meaningful check, notify the user through `artifact.interact(kind='progress', ...)` with current status, latest evidence, and the next monitoring point.
Do this after every completed wait cycle for important long-running work; do not skip several sleep windows without reporting.
When structured progress markers are available, include `eta` and preferably `next_reply_at` or `next_check_at` so the UI can show the next expected update time.

Do not silently widen scope from “baseline reproduction” into “new method exploration”.

### Phase 4. Verification

Verification is mandatory before baseline acceptance.

Verify:

- the run actually finished
- the reported metrics came from the intended dataset and split
- the metric definitions match the quest contract
- the result is comparable to the paper, source repo, or selected baseline target
- any deviations are explicitly stated

Classify the outcome:

- `verified_match`
- `verified_close`
- `verified_diverged`
- `broken`

Verification must be evidence-first.
Do not accept any of the following without explanation:

- missing result files
- metrics that cannot be traced to an actual run
- metric definitions that do not match the quest contract
- unexplained mismatch versus the intended paper or source repo setup

Verification-phase interaction rules:

- do not ask new questions during verification unless the stage has genuinely fallen back to analysis
- if requirements, scope, or permissions changed materially, stop verification and return to the analysis phase explicitly
- verification should summarize real progress milestones rather than quoting raw internal progress markers
- structured progress markers are for runtime monitoring, not for final verification prose

If the reproduced result differs materially from the source reference, verification should explicitly separate:

- likely implementation mismatch
- environment mismatch
- data or split mismatch
- expected stochastic variance
- unexplained divergence

Verification should also answer:

- whether the baseline is trustworthy enough for downstream comparison
- whether the result is reusable beyond this quest
- whether another repair or rerun is justified
- whether the baseline line should stop here and hand off to another stage

Verification checklist before accepting results:

- logs show command completion rather than only task start
- final result files exist
- exported latest snapshot exists when the workflow expects it
- metrics are non-empty, non-placeholder, and non-NaN
- execution notes document the actual commands and outcomes
- the baseline phase state is ready to hand off
- the infrastructure needed for reproduction is actually present and usable
- any closed-loop or key-metric steps expected by the plan were completed or their omission was explicitly documented

If the workflow uses both result files and export files, they should agree or the mismatch must be explained.

Verification should also test the reporting surface itself when the baseline workflow includes one.
For example, if the baseline uses a main driver script with a print-only mode, verify that:

- summary mode runs successfully
- exported Markdown and/or JSON summaries are actually generated
- incremental flags such as `--new-only` behave as documented when they are part of the workflow

Then record:

- trusted metrics
- important caveats
- exact paths for logs, configs, and outputs
- whether the baseline is reusable and should be published

## Minimum baseline artifact content

The baseline artifact should clearly include at least:

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

## Durable note templates

Use compact but structured notes so later stages do not need to reconstruct baseline state from chat history.
The templates below are references, not prerequisites for the first smoke test.
For simple baseline lines, keep them short and fill only the sections that matter.

### `analysis_plan.md`

Recommended shape:

```md
# Baseline Analysis Plan

- quest_id:
- baseline_id:
- requested_route: attach | import | reproduce | repair
- recommended_route:
- source_identity:
- task:
- dataset_and_split:
- metric_contract:
- expected_reference:
- feasibility_summary:

## Existing evidence
- published registry entries:
- local baseline roots:
- relevant repo paths:

## Planned commands
- inspect:
- setup:
- run:
- verify:

## Expected outputs
- baseline_root:
- metrics_path:
- logs_path:
- export_paths:

## Risks
- risk:

## Gate to next phase
- what must be true before setup starts
```

### `setup.md`

Recommended shape:

```md
# Baseline Setup

- baseline_id:
- route:
- working_directory:
- source_origin:
- source_commit:
- environment_summary:
- config_paths:
- command_template:

## Directory contract
- baseline_root:
- logs_root:
- results_root:
- exports_root:

## Known deviations
- deviation:

## Ready-for-execution check
- dependencies_known: yes/no
- outputs_defined: yes/no
- feasible_on_current_machine: yes/no
```

### `execution.md`

Recommended shape:

```md
# Baseline Execution

- baseline_id:
- route:
- run_scope:
- command_started:
- started_at:
- monitoring_plan:

## Runtime log pointers
- stdout_or_main_log:
- stderr_or_error_log:
- result_index:

## Checkpoints
- checkpoint:

## Final execution state
- completed_at:
- exit_status:
- produced_outputs:
- reruns_or_repairs:
```

### `verification.md`

Recommended shape:

```md
# Baseline Verification

- baseline_id:
- route:
- verification_outcome: verified_match | verified_close | verified_diverged | broken
- trusted_for_downstream: yes/no
- reusable_beyond_quest: yes/no
- publish_recommended: yes/no

## Trusted metrics
- metric:

## Reference comparison
- expected_reference:
- observed_result:
- delta_or_gap:

## Evidence paths
- final_metrics:
- logs:
- exports:
- config_snapshot:

## Caveats
- caveat:

## Next recommendation
- next_anchor:
- next_action:
```

These notes do not need to be verbose.
They do need to be complete enough that another stage can read them without replaying the full baseline process.

## Artifact payload templates

When writing artifacts, prefer a stable field shape.

### Route or blocked decision artifact template

```json
{
  "kind": "decision",
  "verdict": "neutral",
  "action": "attach_baseline",
  "reason": "A published baseline already matches the quest task and metric contract.",
  "baseline_id": "baseline-demo",
  "baseline_variant_id": "main",
  "evidence_paths": [
    "<quest_root>/artifacts/reports/report-....json"
  ],
  "next_direction": "Attach the baseline and move to verification or idea selection."
}
```

If blocked, keep the same structure but use a blocked-appropriate action and reason.

### Accepted baseline artifact template

```json
{
  "kind": "baseline",
  "publish_global": true,
  "baseline_id": "baseline-demo",
  "name": "Demo baseline",
  "baseline_kind": "reproduced",
  "task": "image-classification",
  "dataset": "CIFAR-10/test",
  "primary_metric": {
    "name": "accuracy",
    "value": 0.943
  },
  "metrics_summary": {
    "accuracy": 0.943
  },
  "default_variant_id": "main",
  "baseline_variants": [
    {
      "variant_id": "main",
      "label": "Main",
      "metrics_summary": {
        "accuracy": 0.943
      }
    }
  ],
  "environment": {
    "python": "3.11"
  },
  "summary": "Verified reproduced baseline accepted for downstream comparison.",
  "path": "<quest_root>/baselines/local/baseline-demo",
  "source": {
    "kind": "artifact_publish",
    "quest_id": "<quest_id>",
    "quest_root": "<quest_root>"
  }
}
```

Only set `publish_global: true` when verification is complete and reuse is justified.

## Registry publication and attachment contract

The baseline skill should use the durable registry deliberately, not as an afterthought.

If the result is reusable beyond the current quest:

- publish it through `artifact.publish_baseline(...)`
- ensure the payload includes the baseline identity, provenance, trusted metrics, and any variant structure
- prefer `publish_global: true` only when the baseline is actually reusable and verification is complete

If the current quest should reuse an existing baseline:

- attach it through `artifact.attach_baseline(...)`
- preserve the selected `baseline_id`
- preserve the selected `variant_id` when one is used
- ensure the resulting attachment record is durable under `baselines/imported/`

If runtime state already includes `requested_baseline_ref` or a matching `confirmed_baseline_ref`:

- default to reuse-and-verify, not rediscovery
- treat a creation-time pre-bound baseline as the active starting point unless you find a concrete incompatibility
- do not rerun broad baseline scouting or full reproduction just because the stage name is `baseline`

Do not publish a baseline that is still blocked, speculative, or verification-incomplete.
Do not attach a baseline without explaining why it is the right reference for the quest.

## Verification report expectations

A baseline verification report should answer:

- what baseline was used
- how it was obtained: attach, import, reproduce, or repair
- what commands and configs were used
- what metrics are trusted
- how the result compares with the expected reference
- what caveats remain

The report should also include:

- whether the run should be trusted for downstream comparison
- whether the baseline is reusable beyond this quest
- whether another repair or rerun is justified

The verification report should be strong enough that later `idea`, `experiment`, and `write` stages can cite the baseline setup without reconstructing it from scratch.

It should ideally also function as a self-contained reproduction note describing:

- baseline identity
- source provenance
- key commands
- environment assumptions
- result locations
- trusted interpretation of the outcome

If the baseline line is meant to be reused later, the final report should be self-contained enough that another stage can answer:

- what to run
- where to run it
- what outputs should appear
- how to interpret those outputs

without reopening the whole reproduction process from scratch.

When useful, generate a single merged reproduction report that includes:

- structure overview
- modification summary
- testing commands
- device and environment summary
- baseline status and blockers
- redacted configuration inventory
- key implementation measures
- core method equations or mathematical notes when they matter for later understanding
- results table
- export paths

For a reusable baseline package checklist, read `references/publishable-baseline-package.md`.

## Branch and worktree rules

- Use the quest branch unless isolation is genuinely needed.
- If baseline setup is risky or intrusive, prepare an isolated branch or worktree first.
- Do not proliferate branches without a reason.
- If a branch was used, record why the baseline needed isolation.

The baseline stage should not build a parallel Git lifecycle of its own.
Branching and promotion remain quest-level concerns.

However, if baseline setup materially changed code or scripts, preserve at least:

- an initial snapshot of the baseline workspace state
- a final snapshot after setup/execution changes

so the quest can later audit what changed during reproduction.

If the workflow uses a baseline-local Git snapshot for audit, treat it as an execution snapshot only.
The quest repo remains the durable authority for promotion and narrative state.

## Memory rules

Stage-start requirement:

- begin every baseline pass with `memory.list_recent(scope='quest', limit=5)`
- then run at least one baseline-relevant `memory.search(...)` before new baseline analysis, repair, or rerun work
- if several baseline or idea lines exist, narrow retrieval to the active baseline route instead of mixing notes from unrelated lines

Write to memory only when the lesson is reusable, such as:

- baseline pitfalls
- environment gotchas
- dataset quirks
- paper-to-code mismatch notes

Do not use memory as a substitute for the baseline artifact itself.

Preferred memory usage:

- quest `papers`:
  - paper-to-code mismatch notes
  - baseline paper caveats
- quest `decisions`:
  - attach / import / reproduce / repair rationale
  - accepted-versus-rejected baseline route choices
- quest `episodes`:
  - setup failures
  - execution failures
  - environment incidents
  - suspicious or divergent baseline runs
- quest `knowledge`:
  - verified metric contract
  - stable setup rules
  - data and evaluation caveats
  - reproducibility lessons that matter later in this quest
- global `knowledge`:
  - reusable reproduction heuristics
  - stable verification heuristics
  - cross-quest baseline debugging lessons
- global `templates`:
  - setup checklist templates
  - verification checklist templates
  - publishable baseline package templates

Useful tags include:

- `stage:baseline`
- `baseline:<baseline_id>`
- `type:repro-lesson`
- `type:verification-caveat`
- `type:environment-incident`
- `topic:<dataset-or-method>`

When calling `memory.write(...)`, pass `tags` as an array like `["stage:baseline", "baseline:<baseline_id>", "type:repro-lesson"]`, not as one comma-joined string.

Recommended read timing:

- before route selection:
  - consult quest `decisions`, `knowledge`, and relevant `papers`
- before reruns or repairs:
  - search quest `episodes` first
- before acceptance:
  - re-check quest `knowledge` and `decisions`
- before publishing globally:
  - confirm the lesson is truly reusable and not only quest-local

Stage-end requirement:

- if baseline work produced a durable reproduction lesson, verification caveat, environment incident, or route rationale, write at least one `memory.write(...)` before leaving the stage

For a fuller memory strategy, read `references/memory-playbook.md`.

## Artifact rules

Typical artifact sequence:

- progress artifact for long-running setup or execution
- report artifact for analysis or verification notes
- baseline artifact for the accepted result
- decision artifact when choosing attach/import/reproduce/repair or when deciding the next anchor

If a reusable baseline was established, prefer recording it in a form that later stages can attach or reuse directly instead of forcing redundant reproduction.

Use `artifact.attach_baseline(...)` or `artifact.publish_baseline(...)` when appropriate.

Preferred artifact choices:

- use `decision` for:
  - route selection
  - blocked-state routing
  - accept / reject / rerun / repair choices
- use `report` for:
  - analysis notes
  - verification reports
  - merged reproduction reports
  - comparability-contract summaries
- use `progress` during long-running setup or execution
- use `baseline` only for an accepted baseline record
- use `approval` only if an explicit user approval was needed for a costly or degraded baseline gate

## Handoff contract

Before handing the quest to `idea`, `experiment`, or `write`, the baseline stage should make the next stage's life easy.

At minimum, downstream stages should be able to answer all of the following without reopening the full reproduction investigation:

- which baseline is active
- which route produced it: attach, import, reproduce, or repair
- which metrics are trusted
- where the baseline outputs and logs live
- what caveats or deviations still matter
- whether the baseline is quest-local only or globally reusable

## Publication and reuse rules

Publish or attach baselines deliberately.

- attach when a trusted reusable baseline already exists and is the right reference for this quest
- publish when this quest produced a verified reusable baseline that later quests should be able to reuse
- do not publish a blocked, speculative, or verification-incomplete baseline
- do not attach a baseline without explaining why it is the correct downstream reference

If a baseline is accepted but not globally reusable, say that explicitly instead of leaving the reuse status ambiguous.

The baseline stage should normally hand off with:

- one accepted baseline artifact
- one verification-oriented report artifact
- one active baseline reference through attachment or accepted local baseline state
- one concise next-step guidance statement or decision artifact when the next anchor is not obvious

## Final handoff packet

Before leaving the baseline stage, make sure the next stage can read a compact handoff packet from durable state.

The handoff packet should make these items obvious:

- `baseline_id`
- `baseline_variant_id` when relevant
- route used: attach/import/reproduce/repair
- trusted metrics
- canonical metric contract JSON path
- verification outcome
- reusable or quest-local only
- canonical output paths
- main caveats
- recommended next anchor

If this packet is not obvious from the artifact plus verification note, the baseline stage is not yet stable enough.

## Failure and blocked handling

Do not hide baseline failures.

If blocked, record exactly which class applies:

- missing_source
- missing_code
- missing_metric_contract
- environment_infeasible
- command_unknown
- run_failed
- verification_failed

A blocked baseline result must state:

- what failed
- what was tried
- which paths/logs show the issue
- whether the next best move is attach/import/retry/reset/ask user

If the failure happened after a long-running task, include the monitored command/log path rather than only a prose description.

Common autonomous fixes before falling back:

- missing module or dependency
- wrong dataset path
- permission errors on scripts
- reasonable batch-size reductions for OOM
- obvious environment activation issues

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
