# Baseline Gate Checklist Template

Use this as a compact acceptance-boundary checklist when it helps.
It is optional; the hard requirement is that the accepted, blocked, waived, or route-changed state is durable and unambiguous.

## Identity

- baseline id:
- route:
- acceptance target:
- primary comparator:

## Current Frontier

- [ ] next execution, verification, acceptance, blocker, or route-switch step is explicit
- [ ] active uncertainty is written as a concrete question
- [ ] next stage is known if this gate clears

## Core Gate

- [ ] comparator identity and provenance are explicit
- [ ] dataset, split, evaluation path, required metrics, and metric directions are explicit enough to judge comparability
- [ ] trusted outputs or metrics are traceable to concrete files, logs, service responses, source artifacts, or accepted package records
- [ ] smoke was used, skipped, or replaced by direct verification for an explicit reason when that choice matters
- [ ] expected result files or trusted-output pointers have been checked
- [ ] `<baseline_root>/json/metric_contract.json` exists or will be produced before acceptance
- [ ] baseline is accepted, blocked, waived, or route-changed with a durable note

## Blocked Boundary

- [ ] if blocked, the failure class is explicit
- [ ] if blocked, tried steps and evidence paths are recorded
- [ ] if blocked, next best move is attach, import, retry, repair, reset, waive, or ask the user

## Closeout

- [ ] concise baseline summary written
- [ ] next anchor named explicitly
