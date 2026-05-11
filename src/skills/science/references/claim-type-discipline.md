# Claim Type Discipline

Science claims must say how the assertion was obtained.

## `computed`

Use when the value or conclusion was produced by real execution in the current
quest.

Required support:

- `science.computational_run`, `science.dataset_analysis`, or
  `science.parameter_sweep` node
- output/log/evidence paths or related node ids
- validation when convergence, correctness, units, or schema matter

## `parsed`

Use when the claim comes from user-provided data, existing files, tables, or
metadata parsing.

Required support:

- input data path
- parser/script path or command log
- schema/count checks when relevant

## `digitized`

Use when the claim comes from a paper figure, image, PDF plot, OCR, or manual
digitization.

Required support:

- source figure/image/PDF path
- digitization method or script path
- uncertainty note

Never relabel digitized evidence as computed unless the underlying computation
was actually rerun.

## `hypothesis`

Use when the statement is plausible but not verified by current computation or
data.

Required support:

- rationale and intended validation path
- no phrasing that implies the result already happened

## Upgrade Path

To upgrade `hypothesis` to `computed`, run the needed package check and
computation, record run/validation nodes, then append a new computed claim or
supersede the old claim.
