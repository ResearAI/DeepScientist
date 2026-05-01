---
name: decision
description: Use when the quest needs an explicit go, stop, branch, reuse-baseline, write, finalize, reset, or user-decision transition with reasons and evidence.
skill_role: stage
---

# Decision

Use this skill whenever continuation is non-trivial.
Use it to make one route judgment from durable evidence and then get the quest moving again.

## Match signals

Use `decision` when:

- the next stage is not obvious
- the evidence is mixed
- the current line may need to stop
- the quest needs a branch, reset, or reuse-baseline judgment
- a user preference-sensitive choice remains
- a blocker needs an explicit route

Do not use `decision` when:

- the active mainline is still too ambiguous for a real route judgment and should first be reconciled through `intake-audit`
- the next move is already obvious from durable evidence and can proceed directly
- the task is really baseline recovery, scouting, ideation, or execution rather than a route judgment

## One-sentence summary

Make one route judgment from durable evidence, record the verdict and smallest valid action, then keep the quest moving.

## Control workflow

1. Check whether the board is decision-ready.
   If the current mainline, latest decisive result, or stale-route state is unclear, route through `intake-audit` first.
2. State the real question and gather only decision-relevant evidence.
   Compress the strongest support, strongest contradiction, main risk, main cost, and what is genuinely new.
3. Choose the smallest canonical action that resolves the current state.
   Make the winner, main rejected alternatives, and the decisive reason explicit.
4. Record the decision durably.
   Include verdict, action, reason, evidence paths, and next stage or next direction.
5. Ask the user only when local evidence cannot safely resolve a real preference, scope, or cost choice.

## AVOID / pitfalls

- Do not repeat the same decision without new evidence.
- Do not decide from vibe, momentum, or optimism.
- Do not hide a blocked state behind a vague “continue”.
- Do not launch analysis campaigns casually when the expected information gain is weak.
- Do not choose among candidate packages without naming why the alternatives lost.
- Do not imply baseline reuse is resolved unless the concrete attachment and confirmation path is clear.
- Do not choose `finalize` for a paper line unless manuscript coverage reports `submission_ready=true`; a draft checkpoint routes back to `write`, and a review package routes to `review`.
- Do not keep a paper route alive after a publishability stop-loss finding. If durable evidence shows that novelty, evidence sufficiency, or reader value has collapsed beyond reasonable narrowing, recommend `stop` or `branch`, and record any narrowed non-paper objective as the next direction rather than as a new action. Do not execute `stop` for a low-quality paper judgment without asking the user to confirm that route.

## Constraints

- Use durable evidence, not impressions, as the basis for route judgment.
- Use the smallest canonical action that genuinely resolves the state.
- When baseline reuse or attachment is selected, land it concretely and leave an explicit blocker or waiver if the baseline gate still cannot clear.
- Use blocking user requests only when the user truly must choose.
- Later stages must not need to guess what was decided, why it was decided, or what happens next.

## Validation

Before `decision` can end, all applicable checks should be true:

- the route question is explicit
- the decisive evidence is explicit
- the chosen action matches the actual state
- the main rejected alternative or blocker is visible
- the decision is durably recorded with verdict, action, reason, evidence paths, and next direction
- the next stage or next action is explicit

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

## Truth sources

Make decisions from durable evidence:

- the current board packet when one exists
- recent run artifacts
- report artifacts
- baseline state
- quest documents
- memory only as supporting context

Do not make major decisions from vibe or momentum.
Do not treat `decision` as a substitute for state reconciliation when the active mainline is still ambiguous.

When the quest is algorithm-first, add one extra truth-source rule before non-trivial route choices:

- read `artifact.get_optimization_frontier(...)`
- treat the frontier as the primary optimize-state summary
- only override it when newer durable evidence clearly dominates
- if the frontier says `explore`, do not collapse immediately to exploit unless the latest durable result clearly changes the frontier
- if the frontier says `fusion`, judge whether complementary lines can be merged before launching another isolated candidate

## Required decision record

Every consequential decision should make clear:

- verdict
- action
- reason
- evidence paths
- next stage or next direction

Keep the verdict simple and legible, and make sure the chosen action matches the actual state rather than sounding optimistic by default.

## Canonical actions

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
- `review`
- `finalize`
- `iterate`
- `reset`
- `stop`
- `request_user_decision`

Choose the smallest action that genuinely resolves the current state.

For paper-outline decisions, use `artifact.submit_paper_outline(mode='select', ...)` when selecting an existing candidate and `artifact.submit_paper_outline(mode='revise', ...)` when the selected outline needs repair.
For paper-bundle decisions, use `artifact.submit_paper_bundle(...)` only when the draft or package state is durable enough for that package type.
When deciding whether a paper line can advance, judge method fidelity and story coherence as well as metric coverage.
For paper routes, apply the publishability stop-loss rule before choosing `write`, `review`, or `finalize`: if the line cannot plausibly become a useful and defensible paper, recommend stopping the paper objective or branching to a stronger route instead of adding another writing pass. If the proposed action is `stop` because paper quality is too low, first ask for a user decision with the evidence and the branch/narrow alternatives. If the user has given publication, scope, cost, or non-paper preferences, consider them explicitly; if those preferences are unclear and materially affect the stop/branch choice, ask for a user decision.

Apply the symmetric **exploration-depth gate before recommending `close_round_write_paper` for an all-negative-result paper** (every attempted idea has been falsified or family-bounded, no positive lift survives). Before routing to `write`, answer all of these in the decision artifact:

- Have you tested at least two structurally distinct idea families from `idea/references/idea-thinking-flow.md` (mechanism, objective, measurement, infrastructure, or model-architecture / ensemble / multi-agent), or only multiple variants inside one family?
- Have you challenged the bottleneck framing itself — is "X is the locus of the residual gap" a conclusion or just an artefact of where you stopped looking?
- Has the literature surfaced a structurally different route the current attempts did not cover (cross-domain mechanism transfer, different evaluator regime, different training-data composition, etc.)?
- How much of the quest's `time_budget_hours` is unused, and could a third structurally distinct family fit inside the remainder?

If any answer is "no" or "unsure" and the time budget allows, route back to `idea` for a re-ideation pass focused on a structurally different family before concluding. The negative-result paper is still the right outcome when the gate is honestly cleared; this gate just prevents premature closure when only one corner of the design space has been ruled out. Positive-result papers are not blocked by this gate.
For resume-changing route decisions, write one compact checkpoint-style quest memory card so later turns know the current active node, node history, what not to reopen by default, and the first files to read.
Use `type:checkpoint-memory` and `references/checkpoint-memory-template.md` for that card.

## Operational guidance

The main skill keeps the control surface in front.
For the longer judgment and route-shaping notes, read:

- `references/strategic-decision-template.md`
- `references/research-route-criteria.md`
- `references/operational-guidance.md`
- `references/checkpoint-memory-template.md`

Use them when:

- a richer route-change rationale is needed
- research-route selection among candidate packages is the main difficulty
- memory should preserve the new authoritative resume point

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
