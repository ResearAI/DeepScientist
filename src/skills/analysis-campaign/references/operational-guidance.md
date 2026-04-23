# Operational Guidance

Use this reference when the analysis route needs the longer operational notes rather than the main control surface.

## Artifact tactics

Use `artifact.create_analysis_campaign(...)` when durable lineage or slice-level branch/worktree state matters.
Even one extra experiment can still be represented as a one-slice campaign when durable lineage matters.
Use a one-slice campaign when the slice should appear as a real child node in Git or Canvas, or when review, rebuttal, or paper traceability benefits from the campaign object.

If `artifact.create_analysis_campaign(...)` returns slice worktrees, run each returned slice in its returned workspace unless there is a concrete reason to switch and record that reason.
Branch that campaign from the current workspace or result node rather than mutating the completed parent node in place when lineage matters.
Only create the campaign after you have verified that the listed slices are executable with the current quest assets and runtime, or explicitly mark infeasible slices as such.

When the campaign is writing-facing, the create call should carry available paper-mapping fields such as `selected_outline_ref`, `research_questions`, `experimental_designs`, and `todo_items` when they exist and matter.
If ids or refs are unclear, recover them first with `artifact.resolve_runtime_refs(...)`, `artifact.get_analysis_campaign(...)`, `artifact.get_quest_state(...)`, or `artifact.list_paper_outlines(...)` instead of guessing.
Treat `campaign_id` as system-owned, and treat `slice_id` or `todo_id` as agent-authored semantic ids.

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

## Resource gate

Before launching a multi-slice campaign or any expensive slice, record the current execution envelope in the durable route record:

- available GPUs, CPUs, memory, and storage
- expected wall-clock budget
- concurrency or queue limits
- services, credentials, or dependencies that may block execution

For each planned slice, decide explicitly:

- runnable as written
- runnable only after downscoping
- infeasible in the current environment

Do not keep an infeasible slice as if it were still on equal footing with runnable slices.
Either replace it with a lower-cost proxy, defer it with a blocker note, or drop it.

## Execution tactics

Use whatever execution route is most faithful, observable, and efficient while preserving the hard gates.

- A bounded smoke test is useful when the slice command, outputs, metric path, or evaluator wiring is uncertain.
- Treat smoke work as a `0-2` default budget, not as an automatic mandatory phase.
- If the path is already concrete, go straight to direct verification or the real slice.
- If two candidate slices answer the same evidence question, prefer the one that preserves the most soundness under the current hardware and time budget.
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
- if the same slice repeatedly fails because the environment cannot support it, stop retrying and redesign the slice set around the real resource envelope

## Memory note

Use memory only to avoid repeating known failures or to preserve reusable campaign lessons, not as a required step before every slice.

Stage-start requirement:

- begin an analysis campaign pass with `memory.list_recent(scope='quest', limit=5)` when resuming, reopening old command paths, or prior campaign lessons are likely to matter
- run targeted `memory.search(...)` before launching or resuming slices when repeated failures, prior slice outcomes, or comparability caveats may affect the route

Stage-end requirement:

- if the campaign produced a durable cross-slice lesson, failure pattern, or comparability caveat, write at least one `memory.write(...)` before leaving the stage

## Connector-facing campaign chart requirements

- When a campaign result is promoted into a connector-facing chart, prefer restrained palettes such as `sage-clay` and `mist-stone`.
- A useful `sage-clay` anchor for campaign visuals is `#7F8F84`.
- Use color to separate campaign-critical slices from background slices, not to decorate every slice equally.
- Keep the palette consistent with the system prompt instead of improvising a fresh theme per campaign.
- Campaign visuals should make the main boundary change obvious even in compressed connector previews.
