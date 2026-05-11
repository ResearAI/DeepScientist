# Science Task Brief Template

SetupAgent may use this shape as startup context for natural-science tasks.
It is inspired by FermiLink's `goal.md` discipline, but DeepScientist should
not require the main agent to materialize a `goal.md` file.

```markdown
# Science Task Brief: <title>

## Objective
What scientific or engineering result should be produced.

## What To Compute Or Analyze
- Concrete calculations, simulations, dataset analyses, reproductions, or
  optimizations.

## Setup And Constraints
- Physical parameters, package preferences, datasets, hardware, SSH/HPC,
  privacy, units, budget, and runtime constraints.

## Success Criteria
- Quantitative convergence, correctness, reproducibility, comparison, or
  validation checks.

## Deliverables
- Expected scripts, logs, outputs, figures, tables, reports, or data files.

## Evidence Recording Plan
- Expected `science.package_check`, `science.computational_run`,
  `science.dataset_analysis`, `science.parameter_sweep`,
  `science.validation_result`, and `science.claim` nodes.
```

## Scientific Code Optimization Brief

Use this format when the task is performance optimization of scientific code:

```markdown
# Optimization Goal

## Package
<package_id or repo name>

## Language
<python|c|cpp|fortran|mixed>

## Target
Specific hot path and scientific semantics that must remain unchanged.

## Editable Scope
- explicit/path/to/file.py

## Performance Metric
Primary runtime or throughput metric and aggregation rule.

## Correctness Constraints
- numeric scientific invariants and tolerances
- forbidden shortcuts or weakened solver settings

## Representative Workloads
- train-case: meaningful workload
- test-case: held-out workload

## Build
```bash
deterministic build or install commands
```

## Notes
- deterministic thread, seed, MPI, launcher, and input-file constraints
```
