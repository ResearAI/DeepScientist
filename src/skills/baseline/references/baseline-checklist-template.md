# Baseline Checklist Template

Use this as a living checklist.
Keep it short by default. For a fast path, complete the core checklist first and expand only if the route becomes complex or unstable.

## Identity

- parent_map_node:
- loop_id:
- baseline id:
- route:
- owner stage:

## In Progress

- [ ] one concrete baseline item is actively in progress

## Next

- [ ] next baseline route check is explicit
- [ ] next execution or verification step is explicit
- [ ] next map transition is explicit

## Later

- [ ] optional deeper audit items live here instead of crowding `Next`

## Blocked

- [ ] blockers or unresolved dependencies are recorded here

## Core Gate

- [ ] baseline object and route are explicit
- [ ] dataset / split and metric contract are explicit enough to judge comparability
- [ ] `PLAN.md` captures the command path, expected outputs, acceptance condition, and fallback
- [ ] smoke decision is explicit:
  - skipped for a justified reason, or run once with outputs checked
- [ ] real validation/run decision is explicit:
  - skipped for a justified reason, or launched/read with durable evidence
- [ ] expected result files and required metrics are checked
- [ ] baseline is accepted, blocked, or waived with a durable note

## Done

- [ ] completed frontier items are moved here instead of remaining mixed into `Next`

## Closeout

- [ ] concise `1-2` sentence baseline summary written
- [ ] next stage named explicitly

## Optional Expansion

Fill this only when the route becomes full-audit, repair-heavy, or publication-oriented.

- [ ] paper source identified
- [ ] repo source identified
- [ ] paper read enough to restate the core method faithfully
- [ ] repo read enough to identify the real entrypoints
- [ ] main files to inspect or modify listed
- [ ] working directory confirmed
- [ ] environment route chosen
- [ ] key dependencies checked
- [ ] model / data download path confirmed
- [ ] fallback source recorded for critical downloads
- [ ] monitoring cadence started
- [ ] health signals confirmed
- [ ] any execution deviation reflected back into `PLAN.md`
- [ ] verification note written
