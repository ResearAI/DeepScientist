# Analysis Campaign Artifact Flow Examples

Use this reference when the evidence question is clear but the exact artifact sequence is not.
These are examples, not the only legal routes.
The hard rule is: once a supplementary slice is launched as campaign work, its state must be recorded through `artifact.record_analysis_slice(...)`.

## 1. One launched supplementary slice

Use when one extra experiment is enough but lineage or reviewability matters.

Typical sequence:

1. `artifact.resolve_runtime_refs(...)` if ids are unclear
2. `artifact.create_analysis_campaign(...)` with one slice
3. run the returned slice in its returned workspace
4. `artifact.record_analysis_slice(...)`
5. record the route implication

Good:

- one-slice campaign still gives durable lineage and Canvas visibility

Bad:

- running the slice locally and only mentioning the result in chat

## 2. Multi-slice evidence package

Use when several slices together answer one evidence question.

Typical sequence:

1. define the currently justified slice frontier
2. `artifact.create_analysis_campaign(...)`
3. execute slices one by one in returned workspaces
4. after each launched slice, call `artifact.record_analysis_slice(...)`
5. aggregate only after slice-level evidence exists

Good:

- summary comes after slice records, not before

Bad:

- pretending planned slices count as evidence before they run

## 3. Writing-facing slice

Use when the slice directly supports the paper contract.

Typical sequence:

1. recover or inspect `selected_outline_ref` and paper matrix state when relevant
2. `artifact.create_analysis_campaign(...)` with available paper-mapping fields
3. run the slice
4. `artifact.record_analysis_slice(...)`
5. write back to matrix / ledger / section notes

Good:

- slice is durable and also write-backable

Bad:

- slice is completed but the paper contract still looks missing

## 4. Failed or infeasible slice

Use when the slice cannot complete honestly.

Typical sequence:

1. stop or mark the slice when blocked
2. keep the real blocker visible
3. `artifact.record_analysis_slice(...)` with non-success status
4. route to redesign, `decision`, `experiment`, or stop

Good:

- non-success still becomes durable evidence

Bad:

- silently replacing a failed slice with a different slice and only reporting the later success

## 5. Read-only bounded audit

Use when no slice is launched and the answer comes from existing outputs, tables, logs, artifacts, or files.

Typical sequence:

1. inspect the existing evidence
2. leave a durable report or decision
3. do not pretend this was a launched campaign slice

Good:

- this avoids unnecessary campaign overhead

Bad:

- skipping `artifact.create_analysis_campaign(...)` for a real launched supplementary run and calling it a read-only audit afterward
