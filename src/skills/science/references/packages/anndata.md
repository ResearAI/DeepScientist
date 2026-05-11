# AnnData Annotated Data Matrices

## Catalog

- Package id: `anndata`
- Domains: `bioinformatics`, `workflow_provenance`
- Tags: `anndata`, `single-cell`, `omics`, `bioinformatics`, `h5ad`
- Knowledge URL: https://github.com/skilled-scipkg/anndata
- Source archive URL: https://github.com/skilled-scipkg/anndata/archive/refs/heads/main.zip
- Upstream project URL: https://github.com/scverse/anndata
- Homepage: http://anndata.readthedocs.io
- Catalog source: FermiLink skilled-scipkg, commit `93f089a333a43089fb1a08a73c37d05fd6683214`

## When To Consider

anndata provides an efficient annotated matrix container for single-cell and spatial omics, supporting metadata-rich observations, variables, sparse storage, and on-disk workflows.

## DeepScientist Runtime Rule

This card is package knowledge and routing context only. It does not mean the
solver, Python module, CLI binary, compiled backend, license server, dataset, or
HPC module is installed in the active environment. Before computed work, use
`bash_exec(...)` to perform an import, executable, version, and smoke-test check
appropriate for `anndata`.

## Package Check

For Python-facing environments, start with an import/version check and then a
minimal package-specific smoke test:

```bash
python - <<'PY'
import importlib, json, pathlib
package_id = 'anndata'
result = {"package_id": package_id, "import": "failed", "version": None, "smoke": "not_run"}
try:
    module = importlib.import_module(package_id.replace('-', '_').split('_jl')[0])
    result["import"] = "passed"
    result["version"] = getattr(module, "__version__", None)
except Exception as exc:
    result["error"] = repr(exc)
pathlib.Path("validation/environment").mkdir(parents=True, exist_ok=True)
pathlib.Path(f"validation/environment/{package_id}_doctor.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
PY
```

Record the result with `artifact.science(...)` as `science.package_check`. Use
`status="passed"` only when the environment can run at least a minimal smoke
path. Use `status="failed"` or `status="blocked"` when the check explains why
execution cannot proceed.

Generated import or executable names are starting points. If `anndata` uses
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
