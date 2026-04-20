---
name: decision
description: Use when the quest needs an explicit go, stop, branch, reuse-baseline, write, finalize, reset, or user-decision transition with reasons and evidence.
skill_role: stage
---

# Decision

Use this skill whenever continuation is non-trivial.
Use it to make one route judgment from durable evidence and then get the quest moving again.

## Interaction discipline

Follow the shared interaction contract injected by the system prompt.
Avoid repeating the same decision without new evidence, and use blocking requests only when the user truly must choose.
For ordinary active work, prefer a concise progress update once work has crossed roughly 6 tool calls with a human-meaningful delta, and do not drift beyond roughly 12 tool calls or about 8 minutes without a user-visible update.
When a decision materially resolves ambiguity and the quest can continue automatically, follow the durable record with `artifact.interact(kind='milestone', reply_mode='threaded', ...)` so the user can see the chosen route, the decisive evidence, and the next checkpoint.

## Tool discipline

- **Do not use native `shell_command` / `command_execution` in this skill.**
- **If decision-making needs shell, CLI, Python, bash, node, git, npm, uv, or environment evidence, gather it through `bash_exec(...)`.**
- **For git state inside the current quest repository or worktree, prefer `artifact.git(...)` before raw shell git commands.**
- **Use `decision` to judge the route, not as an excuse to bypass the `bash_exec(...)` / `artifact.git(...)` tool contract.**

## Planning note

Use quest/workspace planning files only as supporting state for the decision, not as a reason to open another planning loop when the real need is a route judgment.

## Stage purpose

`decision` is not a normal anchor.
It is a cross-cutting control skill that should be used whenever the quest must decide:

- whether to continue
- whether to branch
- whether to attach or reuse a baseline
- whether to launch an experiment
- whether to launch an analysis campaign
- whether to move to writing
- whether to finalize
- whether to reset
- whether to stop
- whether to ask the user for a structured decision

## Use when

- the next stage is not obvious
- the evidence is mixed
- the current line may need to stop
- the quest needs a branch or reset
- a user preference-sensitive choice remains
- a blocker needs an explicit route

## Required decision record

Every consequential decision should make clear:

- verdict
- action
- reason
- evidence paths
- next stage or next direction

## Verdict note

Keep the verdict simple and legible, and make sure the chosen action matches the actual state rather than sounding optimistic by default.

## Allowed actions

Use the following canonical actions:

- `continue`
- `launch_experiment`
- `launch_analysis_campaign`
- `branch`
- `prepare_branch`
- `activate_branch`
- `reuse_baseline`
- `attach_baseline`
- `publish_baseline`
- `write`
- `finalize`
- `iterate`
- `reset`
- `stop`
- `request_user_decision`

Choose the smallest action that genuinely resolves the current state.

## Action note

Prefer the smallest canonical action that resolves the route cleanly, and keep runtime-specific branching details out of the default decision payload unless they matter now.

Use these concrete actions when the route actually requires them:

- revisit an older durable research line with `artifact.activate_branch(...)`
- land baseline reuse with `artifact.attach_baseline(...)`
- accepted idea -> `artifact.submit_idea(mode='create', lineage_intent='continue_line'|'branch_alternative', ...)`
- open paper-outline selection with `artifact.submit_paper_outline(mode='select', ...)`
- close writing into a durable paper-facing bundle with `artifact.submit_paper_bundle(...)`

Do not approve `launch_analysis_campaign` casually.
Analysis usually carries extra resource cost and should require clear academic or claim-level value before spending that budget.

## Truth sources

Make decisions from durable evidence:

- recent run artifacts
- report artifacts
- baseline state
- quest documents
- memory only as supporting context

Do not make major decisions from vibe or momentum.

When the quest is algorithm-first, add one extra truth-source rule before non-trivial route choices:

- read `artifact.get_optimization_frontier(...)`
- treat the frontier as the primary optimize-state summary
- only override it when newer durable evidence clearly dominates

## Workflow

### 1. State the question

Write the real question explicitly, such as:

- is the current idea promising enough to continue?
- is baseline reuse sufficient?
- is more analysis needed before writing?
- is the draft good enough to finalize?

### 2. Collect the evidence

Summarize only the decision-relevant evidence:

- strongest support
- strongest contradiction
- missing dependency
- known cost or risk
- what is genuinely new since the last route judgment

### 3. Choose verdict and action

Typical mapping:

- `good`
  - continue, branch, launch experiment, write, finalize
- `neutral`
  - branch, activate branch, launch analysis campaign, request user decision
- `bad`
  - reset, stop
- `blocked`
  - reuse baseline, attach baseline, request user decision, stop

The action must match the actual state.

When the route judgment lands on baseline reuse or attachment:

- use `artifact.attach_baseline(...)` to land on the concrete reusable baseline
- use `artifact.confirm_baseline(...)` once the attached baseline is accepted as the active comparator
- if baseline reuse still cannot clear the gate, leave an explicit blocker or waiver instead of implying the route is resolved

### 3.1 Selection among candidate packages

When choosing among multiple candidate outputs, do not decide implicitly.
Record the candidates, the criteria, the winner, and why the main alternatives lost.

When the choice is paper-facing, prefer the option that best preserves:

- method fidelity
- evidence support
- story coherence
- experiment ordering that later `write` or `finalize` can defend

### 3.2 Research-route selection heuristic

When the decision is about a research direction, experiment route, or branch:

- identify the core insufficiency being targeted
- prefer a small serious frontier over many weak alternatives
- prefer careful judgment from durable evidence over launching tie-break runs by reflex
- record why the winner won, why the main alternatives lost, and what residual risk remains

The route heuristic is intentionally lightweight: compare the incumbent against a small serious frontier and choose one dominant next move.
For algorithm-first routing, prefer this compact mapping:

- frontier says `explore` -> widen or refine candidate briefs before new branch creation
- frontier says `exploit` -> keep the strongest line active and advance the best implementation candidates
- frontier says `fusion` -> open at most one bounded fusion candidate
- frontier says `stop` -> record the stop decision and explicit reopen condition

For a compact research-route rubric, read `references/research-route-criteria.md`.

### 4. State the reason

The reason should be concrete and evidence-backed.
Avoid generic wording like “seems better”.

When the decision is stage-shaping, prefer a richer structure that later stages can execute directly.
Use `references/strategic-decision-template.md` when a richer shape would clarify why the route changed and how the next stage should proceed.

If a route change is material, make the reason explicit enough that the next stage can continue without reconstructing hidden intent.

### 5. Request user input only when needed

Ask the user only when:

- multiple options are all plausible
- the choice depends on preference, cost, or scope
- the missing information cannot be derived locally

When asking, use a structured decision request with:

- concise question
- 1 to 3 concrete options
- tradeoffs, including the main pros and cons for each option
- recommended option first
- explicit reply format

Keep decision requests narrow; if local evidence can resolve the route safely, do not hand routine ambiguity back to the user.

### 6. Record the decision durably

Use `artifact.record(payload={'kind': 'decision', ...})` for the final decision.

If user input is needed, also use `artifact.interact(kind='decision_request', ...)`.

## Memory note

Write memory only when the decision created a reusable lesson or changed the authoritative resume point for later turns.

When the authoritative resume point changes, write one compact checkpoint-style quest memory card.
Mark it with `type:checkpoint-memory`.
The card should include:

- current active node
- node history
- what not to reopen by default
- first files to read

Use `references/checkpoint-memory-template.md`.

## Decision-quality rules

Good decisions:

- are evidence-backed
- name tradeoffs
- say what happens next
- say why the alternative was not chosen
- explicitly identify the winning candidate when choosing among multiple packages
- do not launch analysis campaigns unless the expected information gain clearly justifies the extra resource cost

Weak decisions:

- hide uncertainty
- lack evidence paths
- give vague approvals
- pretend blocked states are progress
- choose a winner without naming the rejected alternatives or criteria

## Exit criteria

Exit once the decision is durably recorded and the next stage or action is explicit.

A good decision pass changes the route once; it does not keep re-explaining the same route without new evidence.
