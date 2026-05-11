# deal.II Finite Element Library

## Catalog

- Package id: `dealii`
- Domains: `computational_fluid_dynamics`, `finite_element_engineering`, `workflow_provenance`
- Tags: `finite-elements`, `pde`, `adaptive-mesh`, `computational-mechanics`, `multiphysics`, `hpc`
- Knowledge URL: https://github.com/skilled-scipkg/dealii
- Source archive URL: https://github.com/skilled-scipkg/dealii/archive/refs/heads/master.zip
- Upstream project URL: https://github.com/dealii/dealii
- Homepage: https://dealii.org
- Catalog source: FermiLink skilled-scipkg, commit `93f089a333a43089fb1a08a73c37d05fd6683214`

## When To Consider

deal.II is a C++ library for solving partial differential equations with adaptive finite elements, supporting scalable multiphysics simulations on serial and distributed-memory architectures.

## DeepScientist Runtime Rule

This card is package knowledge and routing context only. It does not mean the
solver, Python module, CLI binary, compiled backend, license server, dataset, or
HPC module is installed in the active environment. Before computed work, use
`bash_exec(...)` to perform an import, executable, version, and smoke-test check
appropriate for `dealii`.

## Package Check

For CLI/HPC-oriented environments, check the executable or loaded module before
running any expensive job:

```bash
command -v dealii || true
dealii --version || true
```

If the package is available only through environment modules, record the module
state and the exact executable path in `validation/environment/dealii_doctor.json`.

Record the result with `artifact.science(...)` as `science.package_check`. Use
`status="passed"` only when the environment can run at least a minimal smoke
path. Use `status="failed"` or `status="blocked"` when the check explains why
execution cannot proceed.

Generated import or executable names are starting points. If `dealii` uses
a different Python module, CLI binary, environment module, container, or wrapper
script, adjust the check before concluding the solver is unavailable.

## Expected Science Nodes

- `science.package_check` for import/executable/version/smoke-test evidence
- `science.computational_run` for solver execution, simulation, fitting, or numerical computation
- `science.dataset_analysis` when the task primarily analyzes existing data
- `science.parameter_sweep` when varying parameters, inputs, models, or solver settings
- `science.validation_result` for convergence, units, schema, controls, or correctness checks
- `science.claim` only after evidence paths or related nodes support the claim

## Evidence Path Conventions

- `simulations/inputs/` for generated or selected solver inputs
- `simulations/logs/` for stdout, stderr, scheduler logs, or solver logs
- `simulations/outputs/` for structured run outputs
- `analyses/scripts/`, `analyses/logs/`, and `analyses/outputs/` for dataset analysis
- `validation/environment/` for package checks
- `validation/runs/` for convergence, unit, schema, or correctness sidecars
- `figures/` for derived visualizations

## Validation Checklist

- Record package version, executable path, backend, module state, or container image when relevant.
- Preserve input files and parameters that define the scientific state.
- Capture units, coordinate conventions, timestep/mesh/basis/model settings, seeds, and convergence criteria when applicable.
- Validate output schema and important physical or statistical invariants before recording a computed claim.
- Link claims to run, analysis, sweep, and validation nodes rather than relying on prose.

## Common Pitfalls

- Do not treat the package card or knowledge URL as runtime availability.
- Do not weaken solver tolerances, physical models, dataset filters, or convergence criteria to make a run pass unless the change is explicitly part of the scientific question.
- Do not call a value `computed` unless the corresponding run or analysis happened in the current quest and evidence paths are recorded.
- Do not copy package knowledge-base material into the quest without preserving its source and license context.
