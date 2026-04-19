# Baseline Artifact Flow Examples

Use this reference when the baseline route is clear but the exact artifact sequence is not.
These are examples, not the only legal paths.
The hard rule is still: attach/import/publish does not open the baseline gate by itself.

## 1. Reuse an existing registry baseline

Use when a trustworthy reusable baseline already exists in the registry and can support the current comparison contract.

Typical sequence:

1. `artifact.attach_baseline(...)`
2. inspect the attached package, outputs, provenance, and metric contract
3. run only the minimum extra verification needed for current trust
4. write or reuse `<baseline_root>/json/metric_contract.json`
5. `artifact.confirm_baseline(...)`

Good:

- the registry entry is materialized into the quest
- the attached outputs are traceable
- caveats are carried into confirmation if needed

Bad:

- treating `artifact.attach_baseline(...)` as if it already opened the gate
- attaching one package and then comparing against a different local path without recording it

## 2. Import a local package or bundle

Use when the user already provided a prepared baseline package, bundle, or snapshot.

Typical sequence:

1. materialize the imported package under the quest baseline roots
2. keep `attachment.yaml` or equivalent provenance durable
3. inspect outputs / metrics / provenance
4. write or reuse `<baseline_root>/json/metric_contract.json`
5. `artifact.confirm_baseline(...)`

Good:

- imported package is readable and traceable
- imported metrics are tied to real files, not only copied prose

Bad:

- importing a bundle and calling it accepted before checking what task / split / metric it actually used

## 3. Verify a local-existing comparator

Use when a local code path or local service already exists and can be evaluated cheaply.

Typical sequence:

1. identify the concrete path or endpoint
2. identify the real evaluation command or endpoint
3. verify outputs or metrics under the intended contract
4. write `<baseline_root>/json/metric_contract.json`
5. `artifact.confirm_baseline(...)`

Good:

- the local comparator is cheaper and more faithful than a full clean-room reproduction

Bad:

- assuming the local implementation matches the paper without checking split / metric / protocol

## 4. Publish a quest-local baseline for reuse

Use when the current quest already contains a verified reusable baseline and you want to publish it.

Typical sequence:

1. finish verification first
2. make sure provenance, caveats, and metrics are trustworthy
3. `artifact.confirm_baseline(...)` if the current quest gate is still unresolved
4. `artifact.publish_baseline(...)`

Good:

- publish only after the local quest already trusts the baseline

Bad:

- publishing a half-verified line just because the files look complete

## 5. Waive the baseline gate

Use only when the quest must continue without a baseline and the reason is real, explicit, and durable.

Typical sequence:

1. record why the baseline cannot be cleared now
2. record what was tried and what remains missing
3. `artifact.waive_baseline(...)`

Good:

- the waiver reason is clear enough that a later turn can revisit it

Bad:

- waiving because reproduction is annoying rather than because the route is genuinely blocked or out of scope
