# Campaign Design

Use this reference when an analysis campaign exists to strengthen writing-facing evidence rather than to accumulate miscellaneous extra runs.

## Goal

A strong campaign should move the evidence boundary from:

- fragile -> interpretable
- minimum -> solid
- solid -> broader confidence

It should do so with the highest soundness gain that still fits the current execution envelope.

Do not treat every available follow-up as equally valuable.

## Priority order

Prefer this order:

1. claim-critical contradiction checks
2. strongest robustness or sensitivity checks
3. failure-mode explanation
4. efficiency or secondary support

Within the same priority tier, prefer the slice that is both runnable now and most likely to change the claim boundary.

## Slice classes

- `auxiliary`
  - helps understand settings, thresholds, or mechanisms
  - does not itself carry the main paper claim
- `claim-carrying`
  - directly affects whether the main narrative is justified
- `supporting`
  - broadens confidence or interpretability after the main claim is already credible

## Writing-facing policy

If the campaign is tied to a selected outline:

- run the claim-carrying slices first
- only then run supporting slices that deepen interpretation
- route back to `write` once the evidence is strong enough for the selected narrative

## Resource-aware design gate

Before you expand a slice set, write down the current practical limits:

- available machine class or devices
- expected wall-clock budget
- memory and storage limits
- concurrency limits
- environment or dependency risk

Then tag each candidate slice as one of:

- `runnable-now`
- `runnable-with-downscope`
- `blocked-by-resources`

When resources are tight, optimize for soundness-per-cost:

- prefer one decisive, runnable contradiction or robustness slice over several speculative expensive slices
- use narrower sweeps, fewer seeds, shorter horizons, smaller held-out subsets, or cheaper diagnostics when they still answer the question honestly
- record blocked high-value slices explicitly instead of letting them disappear
