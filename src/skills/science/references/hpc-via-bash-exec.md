# HPC Via `bash_exec`

DeepScientist does not embed an HPC scheduler. The agent operates HPC through
`bash_exec(...)` just like any other terminal action.

## Pattern

1. Verify remote access or local scheduler availability.
2. Write a small job script or command file in the workspace.
3. Submit through `bash_exec(...)`, for example `ssh cluster sbatch job.sh`.
4. Capture job id, queue state, and log paths.
5. Record a science node with `status="queued"` or `status="running"`.
6. Monitor with low-frequency `bash_exec` reads:
   - `squeue` / `sacct`
   - `tail` or `sed -n` on logs
   - file existence and output JSON checks
7. On completion, record a success/failed update and validation node.

## Evidence Fields

Use `metadata` for scheduler facts:

```python
artifact.science(
    action="record_node",
    node_type="science.computational_run",
    node_id="run_lammps_water_viscosity",
    status="queued",
    package_id="lammps",
    input_paths=["simulations/inputs/water_viscosity.in"],
    log_paths=["simulations/logs/water_viscosity.slurm.out"],
    metadata={"scheduler": "slurm", "job_id": "123456"},
)
```

## Cautions

- Do not claim a queued job has produced results.
- Do not infer global completion from a truncated log window.
- Do not poll rapidly for multi-hour jobs. Use durable job ids and saved logs.
- If the cluster requires modules, licenses, or allocations, treat missing
  setup as a blocker and record the failed/blocked package check.
