# Analysis Campaign Boundary Cases

Use this reference when the evidence route is plausible but the success boundary, comparability boundary, or stage boundary is still fuzzy.

## 1. This is really a new main experiment, not analysis

Do not hide a new main experiment inside analysis-campaign when:

- the proposed change defines a new main method
- the comparison target itself is being replaced
- the result would become the new primary measured line rather than a follow-up check

Route back to `experiment` or `idea` instead.

## 2. Non-comparable but still useful

A slice can still be useful when it is not apples-to-apples comparable.

Examples:

- external dataset stress test
- different metric family used only for failure analysis
- altered protocol used to expose a limitation boundary

Required behavior:

- label the slice as non-comparable
- do not mix it into the main comparison table as if it were direct support

## 3. Qualitative or reviewer-example evidence

This can be valid when:

- the claim is about failure buckets, behavior, or explanation
- the sample is concrete and scoped
- the rubric or inspection basis is explicit
- the evidence is used honestly as supporting or boundary evidence rather than fake objective measurement

This is not valid when:

- subjective inspection is presented as if it were a benchmark metric

## 4. One slice is enough

Stop after one slice when:

- the claim boundary is already clear
- the next route is obvious
- extra slices would only add polish, not change the decision

Do not widen the campaign just because more follow-ups are imaginable.

## 5. Repeated failure with no new evidence

Stop widening when:

- the same failure class appears again
- no route changed
- no evidence changed
- no execution environment changed

At that point:

- record the blocker
- redesign the slice
- route through `decision`
- or return to `experiment`

## 6. Writing-facing but pre-outline

This can still be legitimate when:

- the evidence question determines whether writing is even worth pursuing
- no paper-ready claim is being finalized yet

This becomes paper-ready only after it is mapped back to outline / matrix / ledger / section / claim artifacts.

## 7. Extra comparator baseline inside analysis

This is allowed when:

- a slice genuinely needs an extra comparator
- that comparator is analysis-local support rather than the new canonical quest baseline

Required behavior:

- keep the canonical quest baseline gate unchanged
- record the extra comparator through `comparison_baselines`

## 8. Stable support vs contradiction vs ambiguity

Use these rough meanings:

- stable support: slice materially strengthens the parent claim
- contradiction: slice materially weakens or breaks the parent claim
- unresolved ambiguity: slice leaves the decision unclear

Do not blur these together in one optimistic summary.
