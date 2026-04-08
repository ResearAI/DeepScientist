# Baseline Plan Template

Use this when the `baseline` stage becomes concrete enough to act.
Keep it short when the route is simple. For fast-path attach/import/prebound validation, a one-screen plan is enough if it preserves the route, command path, outputs, acceptance condition, and fallback.
Expand the optional sections only when the route is ambiguous, code-touching, broken, multi-variant, or intended for reuse beyond the current quest.

## 1. Map Link

- parent_map_node:
- loop_id:
- node_objective:
- node_deliverable:
- success_condition:
- abandonment_condition:
- next_on_success:
- next_on_failure:

## 2. Core Contract

- quest goal:
- user's core requirements:
- non-negotiable user constraints:
- chosen baseline route:
  - attach / import / reproduce / repair
- baseline id:
- variant id:
- source paper:
- source repo:
- source commit / version / tag:
- task:
- dataset / split:
- metric contract:
- expected command path:
- expected outputs:
- acceptance condition:
- cheapest fallback:

## 3. Current Node Tasks

- [ ] sync the active research-map node and status
- [ ] confirm the concrete baseline route
- [ ] validate the command path or justify skipping smoke
- [ ] launch or verify the real validation path
- [ ] classify the node outcome and update the next edge

## 4. Execution Path

- working directory:
- environment plan:
- required downloads:
- hardware assumptions:
- smoke test needed:
  - yes / no
- smoke command:
- main validation or run command:
- expected runtime / budget:
- durable log path:
- verification targets:
- fastest failure signal:

## 5. Risks And Revision

- main risks:
- when to escalate from fast path to full audit:
- revision note:

## 6. Optional Expansion

Fill this only when the route is no longer simple.

- fallback repo or mirror:
- checkpoints / models:
- likely external blockers:
- safe efficiency levers to try first:
- health signals that justify continued monitoring rather than intervention:
- conditions that require plan revision or kill-and-relaunch:
- paper summary in `1-3` bullets:
- repo summary in `1-3` bullets:
- what the baseline actually does:
- what the likely bottlenecks or brittle points are:
- what still needs verification:

## 7. Optional Code Touchpoints

List the main files or modules only when you expect real inspection or edits.

| Path | Role | Why it matters now | Expected action | Notes |
|---|---|---|---|---|
| | | | inspect / modify / leave alone | |

## 8. Optional Verification Plan

- required result files:
- required metric keys:
- comparability checks:
- acceptance condition:
- downgrade / blocked condition:

## 9. Checklist Link

- checklist path:
- which item should move next:

## 10. Revision Log

| Time | What changed | Why it changed | Impact on execution |
|---|---|---|---|
| | | | |
