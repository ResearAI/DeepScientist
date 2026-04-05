---
name: decision
description: Use when the quest needs an explicit go, stop, branch, reuse-baseline, write, finalize, reset, or user-decision transition with reasons and evidence.
skill_role: stage
---

# Decision

Use this skill whenever continuation is non-trivial.

## Interaction discipline

- Follow the shared interaction contract injected by the system prompt.
- For ordinary active work, prefer a concise progress update once work has crossed roughly 6 tool calls with a human-meaningful delta, and do not drift beyond roughly 12 tool calls or about 8 minutes without a user-visible update.
- Message templates are references only. Adapt to context and vary wording so updates feel natural and non-robotic.
- If the runtime starts an auto-continue turn with no new user message, continue from the active requirements and durable quest state instead of replaying the previous user turn.
- If `startup_contract.decision_policy = autonomous`, do not emit ordinary `artifact.interact(kind='decision_request', ...)` calls; decide the route yourself, record the reason, and continue.
- Use `reply_mode='blocking'` for the actual decision request only when the user must choose before safe continuation and the quest contract still allows a user-gated decision.
- If a threaded user reply arrives, interpret it relative to the latest decision or progress interaction before assuming the task changed completely.
- Quest completion is a special terminal decision: first ask for explicit completion approval with `artifact.interact(kind='decision_request', reply_mode='blocking', reply_schema={'decision_type': 'quest_completion_approval'}, ...)`, and only after an explicit approval reply should you call `artifact.complete_quest(...)`.

## Tool discipline

- **Do not use native `shell_command` / `command_execution` in this skill.**
- **If decision-making needs shell, CLI, Python, bash, node, git, npm, uv, or environment evidence, gather it through `bash_exec(...)`.**
- **For git state inside the current quest repository or worktree, prefer `artifact.git(...)` before raw shell git commands.**
- **Use `decision` to judge the route, not as an excuse to bypass the `bash_exec(...)` / `artifact.git(...)` tool contract.**

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

## Recommended verdicts

- `good`
- `bad`
- `neutral`
- `blocked`

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

In the current runtime, prefer these concrete flow actions:

- record a candidate brief before branch promotion -> `artifact.submit_idea(mode='create', submission_mode='candidate', ...)`
- accepted idea -> `artifact.submit_idea(mode='create', lineage_intent='continue_line'|'branch_alternative', ...)`
- promote a candidate brief into a durable optimization line -> `artifact.submit_idea(mode='create', submission_mode='line', source_candidate_id=..., lineage_intent='continue_line'|'branch_alternative', ...)`
- maintenance-only in-place cleanup of the same branch -> `artifact.submit_idea(mode='revise', ...)`
- compare branch foundations before a new round -> `artifact.list_research_branches(...)`
- return to an older durable branch without creating a new node -> `artifact.activate_branch(...)`
- materialize the concrete main-result node when a real main experiment line is about to be or was just durably recorded -> dedicated child `run/*` branch/worktree
- start the next optimization round from a measured result -> `artifact.record(payload={'kind': 'decision', 'action': 'iterate', ...})`
- launch analysis campaign -> `artifact.create_analysis_campaign(...)`
- finish one analysis slice -> `artifact.record_analysis_slice(...)`
- select a paper outline -> `artifact.submit_paper_outline(mode='select', ...)`
- revise the selected paper outline -> `artifact.submit_paper_outline(mode='revise', ...)`
- close writing into a durable bundle -> `artifact.submit_paper_bundle(...)`

If the chosen action is baseline reuse, the decision is not complete until one of these is durably true:

- the reuse landed on `artifact.attach_baseline(...)` plus `artifact.confirm_baseline(...)`
- or the quest recorded an explicit blocker or waiver explaining why reuse could not be completed safely

Treat `prepare_branch` as a compatibility or recovery action, not the normal path.
Treat `activate_branch` as the correct recovery or revisit action when the quest should resume on an existing older durable branch while preserving the newer research head.
Treat each accepted branch as one durable research round.
Treat candidate briefs as branchless pre-promotion objects; they are not yet durable optimization lines.
If a branch already has a durable main-experiment result, a genuinely new optimization round should normally create a child branch from a chosen foundation rather than keep revising that old branch in place.
Treat each durable main experiment as its own child `run/*` branch/node, not as another mutable state on the idea branch.
When paper mode is enabled and the necessary analysis for a strong run is done, the next default route is `write` on a dedicated `paper/*` branch/worktree derived from that run branch.
Do not approve `launch_analysis_campaign` casually; analysis usually carries extra resource cost and should require clear academic or claim-level value before spending that budget.

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

### 3.1 Selection among candidate packages

When the decision is about choosing among multiple candidate outputs, such as:

- experiment groups
- idea branches
- outline drafts
- revision candidates
- competing reports

do not decide implicitly.

Record:

- candidate ids or names
- the explicit selection criteria
- the winner
- why the winner is preferred
- why the main alternatives were not chosen

When the choice is about an experiment package or analysis package, also record:

- implementation priority order
- what you expect to learn from the chosen package

When the choice is about paper outline candidates, also record:

- which outline best matches the actual evidence inventory
- which `research_questions` and `experimental_designs` become the active contract after selection
- whether more analysis is still required before drafting
- whether the winning outline preserves strong:
  - method fidelity
  - evidence support
  - story coherence
  - experiment ordering

Typical criteria include:

- evidence quality
- feasibility
- comparability
- expected information gain
- narrative coherence
- downstream usefulness

For paper outline candidates specifically, prefer a paperagent-like rubric:

- story quality around `motivation -> challenge -> resolution -> validation -> impact`
- faithful method description rather than idealized storytelling
- real experiment coverage rather than speculative placeholders
- comparable baseline usage only where setups truly match
- main-comparison-first ordering when the evidence supports it

If evaluator scores exist, use them.
Do not blindly follow a score if the underlying evidence is weak; explain the override when needed.

### 3.2 Research-route selection heuristic

When the decision is about choosing a research direction, experiment route, or branch to invest in:

- identify the core insufficiency being targeted
- prefer routes that address that insufficiency elegantly rather than only spending more compute, more stages, or more complexity
- prefer routes that respect the current codebase architecture unless there is strong evidence that a deeper break is justified
- balance breakthrough potential against implementation risk and verification cost

Use a light incumbent/frontier discipline for non-trivial route decisions:

- identify the current `incumbent`:
  - the best-supported active line from existing results, prior decisions, and literature
- identify a small `frontier`:
  - usually 2 to 3 serious alternatives worth comparing against the incumbent
- choose the action that best follows from existing evidence:
  - continue the incumbent
  - branch to a frontier alternative
  - stop or downgrade the line
  - move to writing if the core claim is already sufficiently supported

For these decisions, do not default to launching a small exploratory run just to break ties.
Prefer careful judgment from durable evidence already on hand, especially:

- observed result trends
- failure modes and confounders
- baseline-relative position
- related-work saturation or overlap
- implementation surface and verification burden

When recording the decision, make explicit:

- why the incumbent still wins, or why it should be replaced
- which alternatives were serious enough to compare
- which existing evidence was decisive
- what residual risk remains after the choice

For algorithm-first route choices, prefer this default mapping:

- frontier says `explore` -> widen or refine candidate briefs before new branch creation
- frontier says `exploit` -> keep the strongest line active and advance the best implementation candidates
- frontier says `fusion` -> open at most one bounded fusion candidate
- a fixable candidate failure dominates -> run a debug route instead of widening search blindly
- frontier says `stop` -> record the stop decision and explicit reopen condition

Good route-selection criteria often include:

- feasibility
- scientific importance
- methodological rigor
- expected information gain
- architectural fit
- complexity risk
- downstream narrative value

When selecting an experiment package, make the choice as if you must later justify:

- why this package is the best balance of implementability and scientific value
- what order the experiments should be implemented in
- what concrete learning each step is expected to produce

If one option is more novel but much less testable, say that explicitly instead of hiding the tradeoff.

### 4. State the reason

The reason should be concrete and evidence-backed.
Avoid generic wording like “seems better”.

When the decision is stage-shaping, prefer a richer structure that later stages can execute directly.
Useful optional fields include:

- `target_idea_id`
- `target_run_id`
- `campaign_id`
- `reflection`
  - `what_worked`
  - `what_failed`
  - `learned_constraints`
- `next_direction`
  - objective
  - key steps
  - success criteria
  - abandonment criteria
- `expected_roi`
  - `cost_estimate`
  - `confidence`
  - qualitative improvement estimate with justification

When a decision materially changes the route, follow it with the appropriate user-visible `artifact.interact(...)` update:

- use threaded `artifact.interact(kind='milestone', reply_mode='threaded', ...)` when the decision is already durably resolved and the quest can continue automatically
- use `reply_mode='blocking'` only when the user must choose before safe continuation and `startup_contract.decision_policy` is not `autonomous`
- the user-facing update should name the chosen action, the decisive evidence, the rejected alternative, and the next checkpoint

This is especially useful for:

- idea branch selection
- experiment package selection
- launch of an analysis campaign
- reactivation of an older durable branch
- post-campaign routing
- stop / pivot / finalize choices

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
- a stated timeout window; normally wait up to 1 day before self-resolving if no user reply arrives, except when the only blocker is a missing external credential or secret that only the user can provide

### 6. Record the decision durably

Use `artifact.record(payload={'kind': 'decision', ...})` for the final decision.

If user input is needed, also use `artifact.interact(kind='decision_request', ...)`.
If the timeout expires without a user reply, choose the best option yourself, record why, and notify the user of the chosen option before moving on.
This does not apply when the only blocker is a missing external credential or secret that only the user can provide; in that case keep the interaction waiting and, if resumed without the credential, you may park with `bash_exec(command='sleep 3600', mode='await', timeout_seconds=3700)` instead of busy-looping.

If `startup_contract.decision_policy = autonomous`, ordinary route ambiguity is not by itself grounds to request user input.
In that mode, only explicit approval-style exceptions such as quest completion should normally become blocking user decisions.

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

## Memory rules

Write to memory only when the lesson is reusable across future decisions, such as:

- a recurring failure pattern
- a reliable stop condition
- a useful branching heuristic

The canonical record of the decision itself belongs in `artifact`.

## Exit criteria

Exit once the decision is durably recorded and the next stage or action is explicit.
