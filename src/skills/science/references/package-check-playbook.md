# Package Check Playbook

Package knowledge and solver installation are separate.

Before any computed result:

1. Check import or executable existence.
2. Capture version and important backend details.
3. Run a minimal smoke test when the package supports it.
4. Save the check result to a durable file, usually under
   `validation/environment/`.
5. Record a `science.package_check` node.

## Python Package Pattern

Use `bash_exec(...)` to run a short script that writes JSON:

```bash
python - <<'PY'
import json, pathlib
result = {"package_id": "pyscf", "import": "failed", "version": None, "smoke": "not_run"}
try:
    import pyscf
    result["import"] = "passed"
    result["version"] = getattr(pyscf, "__version__", None)
    result["smoke"] = "passed"
except Exception as exc:
    result["error"] = repr(exc)
pathlib.Path("validation/environment").mkdir(parents=True, exist_ok=True)
pathlib.Path("validation/environment/pyscf_doctor.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
PY
```

Then record:

```python
artifact.science(
    action="record_node",
    node_type="science.package_check",
    node_id="pkg_pyscf_check",
    status="passed",
    package_id="pyscf",
    evidence_paths=["validation/environment/pyscf_doctor.json"],
)
```

## CLI Solver Pattern

Check:

- executable path
- version output
- module/environment state if on HPC
- a minimal dry run or example input if available

Record failed checks too when they explain a blocker. Use `status="failed"` or
`status="blocked"` and include the log path.

## Interpretation

- `passed` means the current environment can run at least the smoke path.
- `failed` means the package was attempted and did not work.
- `blocked` means the agent could not check because credentials, data, modules,
  license, network, or user confirmation are missing.
