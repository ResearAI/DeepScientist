# Analysis Evidence Gate Checklist

Use this as a compact acceptance-boundary checklist when it helps.
It is optional; the hard requirement is that launched slices, evidence boundaries, blockers, and next routes are durable and unambiguous.

## Identity

- parent object:
- parent claim or gap:
- route:
- campaign id:

## Current Frontier

- [ ] next slice, aggregation, blocker, or route decision is explicit
- [ ] active uncertainty is written as a concrete question
- [ ] next route is known if this gate clears or fails

## Resource Gate

- [ ] current device, memory, storage, and wall-clock limits are explicit when they affect campaign design
- [ ] planned slices have been screened as runnable-now, runnable-with-downscope, or blocked-by-resources
- [ ] blocked high-value slices are recorded explicitly rather than silently dropped
- [ ] the current frontier is prioritized by soundness gain under the real resource budget

## Evidence Gate

- [ ] parent claim, paper gap, reviewer item, or decision being tested is explicit
- [ ] each launched slice has a durable outcome or active monitoring path
- [ ] evidence-bearing slices record question, intervention or inspection target, fixed conditions, metric or observable, and evidence path
- [ ] claim update and comparability verdict are explicit
- [ ] null, negative, partial, failed, blocked, or contradictory findings are visible
- [ ] campaign-level interpretation is backed by per-slice evidence

## Comparability Gate

- [ ] baseline or main comparison contract is preserved, or deviation is recorded
- [ ] new dataset / split / metric / protocol changes are labeled as generalization, stress-test, boundary, or non-comparable
- [ ] additional comparators do not overwrite the canonical quest baseline gate

## Paper / Review Gate

- [ ] paper-ready slices map to outline, paper matrix, evidence ledger, section, claim, table, reviewer item, or rebuttal item
- [ ] if a paper-facing slice is complete, the write-back target is updated or the stale contract is recorded as a blocker

## Blocked Boundary

- [ ] if blocked, the failure class is explicit
- [ ] if blocked, tried steps and evidence paths are recorded
- [ ] if blocked, next best move is continue, redesign, return to experiment, return to idea, write, decision, stop, or reset

## Closeout

- [ ] strongest evidence boundary is summarized
- [ ] main claim is classified as strengthened, weakened, narrowed, abandoned, or still ambiguous
- [ ] next route recorded explicitly
