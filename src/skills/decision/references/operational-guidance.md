# Operational Guidance

Use this reference when the decision route needs the longer tactical notes rather than the short control surface in `SKILL.md`.

## Planning note

Use quest or workspace planning files only as supporting state for the decision, not as a reason to open another planning loop when the real need is a route judgment.

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

## Baseline reuse note

When the route judgment lands on baseline reuse or attachment:

- use `artifact.attach_baseline(...)` to land on the concrete reusable baseline
- use `artifact.confirm_baseline(...)` once the attached baseline is accepted as the active comparator
- if baseline reuse still cannot clear the gate, leave an explicit blocker or waiver instead of implying the route is resolved

## Selection among candidate packages

When choosing among multiple candidate outputs, do not decide implicitly.
Record the candidates, the criteria, the winner, and why the main alternatives lost.

When the choice is paper-facing, prefer the option that best preserves:

- method fidelity
- evidence support
- story coherence
- experiment ordering that later `write` or `finalize` can defend

## Research-route selection heuristic

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

## User-input note

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

## Memory note

Write memory only when the decision created a reusable lesson or changed the authoritative resume point for later turns.

When the authoritative resume point changes, write one compact checkpoint-style quest memory card with `memory.write(scope='quest', ...)`.
Mark it with `type:checkpoint-memory`.
The card should include:

- current active node
- node history
- what not to reopen by default
- first files to read

Use `references/checkpoint-memory-template.md`.
