# Baseline Boundary Cases

Use this reference when the baseline route is not blocked but the success boundary still feels fuzzy.

## 1. Comparison-ready but not paper-repro-ready

This is acceptable when:

- the comparator is trustworthy enough for downstream comparison
- the core metric contract is durable
- later experiment work does not need to guess task / split / metric / comparator identity

This is not yet paper-repro-ready when:

- exact paper-side setup details are still partially unknown
- broader variant tables or extra subtasks are still missing
- the package is not reusable enough to publish

## 2. Trusted with caveats

This is acceptable when:

- the main comparator is still honest and usable
- deviations are explicit
- the caveat does not silently change the comparison meaning

Examples:

- local service path verified, but one optional auxiliary metric is unavailable
- source repo uses a repo-native docker path rather than `uv`, and that change is more faithful, not less

Not acceptable:

- caveat hides a different dataset split or evaluation script

## 3. Imported metrics but weak provenance

Do not accept when:

- the package contains a number but you cannot tie it to a real output or evaluator path
- the user pasted a paper table without local or package-side evidence and the target requires verification

Possible next routes:

- verify local existing
- reproduce from source
- block and record weak provenance

## 4. Local path exists but exact comparator is unclear

Do not default into full reproduction immediately.
First ask:

- is there a real evaluation entrypoint?
- is there a concrete output location?
- can the split and metric contract be identified?

Only escalate to reproduction if those answers stay too ambiguous for honest comparison.

## 5. Route feels cleaner but not more trustworthy

Do not replace a working comparison-ready comparator with a heavier route merely because:

- the source reproduction feels aesthetically cleaner
- the repo-native path is more complicated than you expected
- the existing comparator is already good enough for the next scientific step

The heavier route becomes justified only when it removes a named unresolved comparison risk.

## 6. Repeated failure with no new evidence

Stop looping when:

- same command class fails again
- no code changed
- no environment changed
- no route changed
- no new evidence reduced uncertainty

At that point:

- record the blocker
- switch route
- repair
- waive
- or route through `decision`
