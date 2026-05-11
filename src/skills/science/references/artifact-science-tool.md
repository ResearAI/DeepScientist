# `artifact.science(...)` Reference

`artifact.science(...)` records Science Evidence Graph nodes. It does not run
anything.

## Actions

- `record_node`: create a new science node artifact
- `update_node`: append an update artifact for an existing node id
- `link_nodes`: append relationship metadata between nodes
- `status`: summarize existing science artifacts
- `focus`: ask Canvas to focus a science node

`record_node` is for the first record of a stable `node_id`. Do not call
`record_node` twice for the same `node_id`; the runtime rejects duplicates to
protect append-only evidence. Use `update_node` for later status, evidence,
validation, or interpretation changes.

## Common Fields

```python
artifact.science(
    action="record_node",
    node_type="science.computational_run",
    node_id="run_short_stable_id",
    title="Human title",
    summary="What happened and what evidence exists.",
    status="success",
    domain="quantum_chemistry",
    package_id="pyscf",
    task_type="scf_energy",
    key_results=[{"label": "Total energy", "value": -74.96, "unit": "Hartree"}],
    input_paths=["simulations/inputs/run.py"],
    log_paths=["simulations/logs/run.out"],
    output_paths=["simulations/outputs/run/result.json"],
    evidence_paths=["simulations/inputs/run.py", "simulations/logs/run.out"],
    parent_node_ids=["pkg_pyscf_check"],
    related_node_ids=["val_run_short_stable_id"],
    canvas={"focus": True, "open_detail": True},
)
```

## Required Evidence Rules

- `science.package_check` with `status="passed"` needs environment-check
  evidence.
- Failed or blocked package checks should also be recorded when they determine
  the route, with diagnostic evidence explaining the failure or blocker.
- `science.computational_run` with `status="success"` needs at least one input,
  log, output, or evidence path.
- `science.validation_result` must reference a run, analysis, or sweep through
  `related_node_ids` or `parent_node_ids`.
- `science.claim` needs `claim_type`.
- `science.claim` with `claim_type="computed"` needs evidence paths or related
  computed/validation nodes.

## Status Values

Use: `planned`, `ready`, `queued`, `running`, `success`, `failed`, `blocked`,
`warning`, `passed`, `active`, or `superseded`.

## Package Check Example

```python
artifact.science(
    action="record_node",
    node_type="science.package_check",
    node_id="pkg_pyscf_check",
    title="PySCF environment check",
    status="passed",
    domain="quantum_chemistry",
    package_id="pyscf",
    summary="PySCF import and minimal smoke test passed.",
    key_results=[
        {"label": "import", "value": "passed"},
        {"label": "version", "value": "2.x"},
    ],
    evidence_paths=["validation/environment/pyscf_doctor.json"],
)
```

## Claim Example

```python
artifact.science(
    action="record_node",
    node_type="science.claim",
    node_id="claim_basis_comparison",
    title="cc-pVDZ gives lower total energy than STO-3G",
    status="active",
    domain="quantum_chemistry",
    claim_type="computed",
    trust="medium",
    summary="For the same water geometry, HF/cc-pVDZ produced a lower total energy than HF/STO-3G.",
    related_node_ids=[
        "run_water_hf_sto3g",
        "run_water_hf_ccpvdz",
        "val_run_water_hf_sto3g",
        "val_run_water_hf_ccpvdz",
    ],
    evidence_paths=[
        "simulations/outputs/run_water_hf_sto3g/energy.json",
        "simulations/outputs/run_water_hf_ccpvdz/energy.json",
        "validation/run_water_hf_sto3g.json",
        "validation/run_water_hf_ccpvdz.json",
    ],
    canvas={"focus": True, "open_detail": True},
    notify=True,
)
```
