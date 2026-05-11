#!/usr/bin/env python3
"""Generate the DeepScientist science skill package catalog.

The input is FermiLink's curated skilled-scipkg channel metadata. The output is
DeepScientist-native routing material: compact package indexes and one package
card per curated package. The generated cards intentionally keep package
knowledge as URLs and routing metadata; they do not vendor package source trees
or imply solver runtime availability.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_UPSTREAM_COMMIT = "93f089a333a43089fb1a08a73c37d05fd6683214"
DEFAULT_SOURCE = Path("/tmp/FermiLink/src/fermilink/data/curated_channels/skilled-scipkg.json")
DEFAULT_OUTPUT = Path("src/skills/science/references")

DOMAIN_TAG_MAP: dict[str, tuple[str, ...]] = {
    "quantum_chemistry": (
        "quantum-chemistry",
        "electronic-structure",
        "ab-initio",
        "dft",
        "density-functional-theory",
        "first-principles",
        "semiempirical",
        "tight-binding",
    ),
    "computational_chemistry": (
        "computational-chemistry",
        "cheminformatics",
        "force-fields",
        "molecular-mechanics",
        "molecular-modeling",
        "molecular-fingerprints",
        "drug-discovery",
        "parameterization",
    ),
    "molecular_dynamics": ("molecular-dynamics", "classical-md", "molecular-simulation", "atomistic-simulation"),
    "materials_science": ("materials-science", "materials-simulation", "phonons", "lattice-dynamics", "thermal-transport"),
    "electromagnetics": ("electromagnetics", "fdtd", "photonics", "maxwell", "wave-optics"),
    "bioinformatics": ("bioinformatics", "genomics", "singlecell", "transcriptomics", "omics", "cheminformatics"),
    "astronomy_astrophysics": ("astronomy", "astrophysics", "cosmology", "exoplanets", "astroinformatics"),
    "computational_fluid_dynamics": ("cfd", "fluid-dynamics", "hydrodynamics", "openfoam", "pde"),
    "finite_element_engineering": ("finite-element", "fea", "structural-mechanics", "geomechanics"),
    "high_energy_physics": ("hep", "high-energy-physics", "particle-physics", "detector", "monte-carlo"),
    "computational_neuroscience": ("computational-neuroscience", "neuron-simulation", "spiking-networks"),
    "plasma_particle_simulation": ("plasma-physics", "particle-in-cell", "pic", "accelerator-physics"),
    "workflow_provenance": ("workflow", "provenance", "hpc", "scientific-automation", "reproducibility"),
    "robotics_physics": ("robotics", "physics-engine", "robotics-simulation", "rigidbody", "rigid-body", "multibody"),
}

PYTHON_HINT_TAGS = {
    "python",
    "bioinformatics",
    "singlecell",
    "transcriptomics",
    "astronomy",
    "astrophysics",
    "quantum-chemistry",
    "cheminformatics",
}

CLI_HINT_TAGS = {
    "hpc",
    "cfd",
    "finite-element",
    "molecular-dynamics",
    "electromagnetics",
    "materials-science",
    "plasma-physics",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower())
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "package"


def source_archive(item: dict[str, Any]) -> str | None:
    versions = item.get("versions") if isinstance(item.get("versions"), list) else []
    default_version = str(item.get("default_version") or "").strip()
    for version in versions:
        if not isinstance(version, dict):
            continue
        if default_version and str(version.get("version_id") or "") != default_version:
            continue
        url = str(version.get("source_archive_url") or "").strip()
        if url:
            return url
    for version in versions:
        if not isinstance(version, dict):
            continue
        url = str(version.get("source_archive_url") or "").strip()
        if url:
            return url
    return str(item.get("zip_url") or "").strip() or None


def knowledge_url(item: dict[str, Any]) -> str | None:
    archive = source_archive(item) or ""
    match = re.match(r"https://github\.com/([^/]+)/([^/]+)/archive/", archive)
    if match:
        return f"https://github.com/{match.group(1)}/{match.group(2)}"
    return str(item.get("upstream_repo_url") or item.get("homepage_url") or "").strip() or None


def infer_domains(tags: list[str], text: str) -> list[str]:
    normalized_tags = {tag.lower() for tag in tags}
    haystack = " ".join([text.lower(), *normalized_tags])
    domains: list[str] = []
    for domain, needles in DOMAIN_TAG_MAP.items():
        if any(needle in normalized_tags or needle.replace("-", " ") in haystack for needle in needles):
            domains.append(domain)
    if not domains:
        domains.append("computational_science")
    return domains


def package_check_pattern(tags: list[str]) -> str:
    tag_set = {tag.lower() for tag in tags}
    if tag_set & PYTHON_HINT_TAGS:
        return "python_import_or_cli"
    if tag_set & CLI_HINT_TAGS:
        return "cli_executable_or_module"
    return "package_specific"


def card_text(item: dict[str, Any], *, upstream_commit: str) -> str:
    package_id = str(item.get("package_id") or "").strip()
    title = str(item.get("title") or package_id).strip()
    description = str(item.get("description") or "").strip()
    tags = [str(tag).strip() for tag in (item.get("tags") or []) if str(tag).strip()]
    domains = infer_domains(tags, f"{title} {description}")
    archive = source_archive(item) or ""
    k_url = knowledge_url(item) or ""
    upstream = str(item.get("upstream_repo_url") or "").strip()
    homepage = str(item.get("homepage_url") or "").strip()
    check_pattern = package_check_pattern(tags)
    tag_text = ", ".join(f"`{tag}`" for tag in tags) or "none recorded"
    domain_text = ", ".join(f"`{domain}`" for domain in domains)
    suggested_check = ""
    if check_pattern == "python_import_or_cli":
        suggested_check = f"""
For Python-facing environments, start with an import/version check and then a
minimal package-specific smoke test:

```bash
python - <<'PY'
import importlib, json, pathlib
package_id = {package_id!r}
result = {{"package_id": package_id, "import": "failed", "version": None, "smoke": "not_run"}}
try:
    module = importlib.import_module(package_id.replace('-', '_').split('_jl')[0])
    result["import"] = "passed"
    result["version"] = getattr(module, "__version__", None)
except Exception as exc:
    result["error"] = repr(exc)
pathlib.Path("validation/environment").mkdir(parents=True, exist_ok=True)
pathlib.Path(f"validation/environment/{{package_id}}_doctor.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
PY
```
""".strip()
    elif check_pattern == "cli_executable_or_module":
        suggested_check = f"""
For CLI/HPC-oriented environments, check the executable or loaded module before
running any expensive job:

```bash
command -v {package_id} || true
{package_id} --version || true
```

If the package is available only through environment modules, record the module
state and the exact executable path in `validation/environment/{package_id}_doctor.json`.
""".strip()
    else:
        suggested_check = f"""
Use a package-specific import, executable, or module check and save the result
under `validation/environment/{package_id}_doctor.json` before treating the
runtime as usable.
""".strip()

    return f"""# {title}

## Catalog

- Package id: `{package_id}`
- Domains: {domain_text}
- Tags: {tag_text}
- Knowledge URL: {k_url or 'not recorded'}
- Source archive URL: {archive or 'not recorded'}
- Upstream project URL: {upstream or 'not recorded'}
- Homepage: {homepage or 'not recorded'}
- Catalog source: FermiLink skilled-scipkg, commit `{upstream_commit}`

## When To Consider

{description or f'Use `{package_id}` when the scientific task matches the catalog tags above.'}

## DeepScientist Runtime Rule

This card is package knowledge and routing context only. It does not mean the
solver, Python module, CLI binary, compiled backend, license server, dataset, or
HPC module is installed in the active environment. Before computed work, use
`bash_exec(...)` to perform an import, executable, version, and smoke-test check
appropriate for `{package_id}`.

## Package Check

{suggested_check}

Record the result with `artifact.science(...)` as `science.package_check`. Use
`status="passed"` only when the environment can run at least a minimal smoke
path. Use `status="failed"` or `status="blocked"` when the check explains why
execution cannot proceed.

Generated import or executable names are starting points. If `{package_id}` uses
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
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--upstream-commit", default=DEFAULT_UPSTREAM_COMMIT)
    args = parser.parse_args()

    root = repo_root()
    source = args.source if args.source.is_absolute() else root / args.source
    output = args.output if args.output.is_absolute() else root / args.output
    payload = read_json(source)
    packages = payload.get("packages")
    if not isinstance(packages, list) or not packages:
        raise SystemExit(f"No packages found in {source}")
    packages = sorted((item for item in packages if isinstance(item, dict)), key=lambda item: str(item.get("package_id") or ""))

    generated_at = datetime.now(UTC).isoformat()
    provenance = {
        "name": "FermiLink skilled-scipkg catalog",
        "repository": "https://github.com/TaoELi/FermiLink",
        "upstream_commit": args.upstream_commit,
        "channel_id": payload.get("channel_id"),
        "generated_at": generated_at,
        "notes": [
            "DeepScientist uses this as package routing metadata and knowledge URLs.",
            "Package source trees are not vendored by this generated catalog.",
            "Package cards do not prove solver runtime availability.",
        ],
    }

    compact_packages = []
    domain_map: dict[str, list[str]] = defaultdict(list)
    tag_counter: Counter[str] = Counter()
    for item in packages:
        package_id = str(item.get("package_id") or "").strip()
        title = str(item.get("title") or package_id).strip()
        description = str(item.get("description") or "").strip()
        tags = [str(tag).strip() for tag in (item.get("tags") or []) if str(tag).strip()]
        domains = infer_domains(tags, f"{title} {description}")
        for domain in domains:
            domain_map[domain].append(package_id)
        tag_counter.update(tags)
        archive = source_archive(item)
        compact_packages.append(
            {
                "package_id": package_id,
                "title": title,
                "description": description,
                "domains": domains,
                "tags": tags,
                "knowledge_url": knowledge_url(item),
                "source_archive_url": archive,
                "upstream_repo_url": str(item.get("upstream_repo_url") or "").strip() or None,
                "homepage_url": str(item.get("homepage_url") or "").strip() or None,
                "card": f"references/packages/{slug(package_id)}.md",
            }
        )
        write_text(output / "packages" / f"{slug(package_id)}.md", card_text(item, upstream_commit=args.upstream_commit))

    write_json(
        output / "package-index.min.json",
        {
            "schema_version": 1,
            "source": provenance,
            "package_count": len(compact_packages),
            "packages": compact_packages,
        },
    )

    lines = [
        "# Science Package Domain Index",
        "",
        "This generated index groups FermiLink skilled-scipkg package cards for DeepScientist routing.",
        "Package cards are knowledge pointers only; run package checks before computed work.",
        "",
        f"- Package count: `{len(compact_packages)}`",
        f"- Upstream commit: `{args.upstream_commit}`",
        "",
        "## Domains",
        "",
    ]
    for domain in sorted(domain_map):
        package_ids = sorted(set(domain_map[domain]))
        lines.append(f"### {domain.replace('_', ' ').title()}")
        lines.append("")
        for package_id in package_ids:
            item = next(entry for entry in compact_packages if entry["package_id"] == package_id)
            lines.append(f"- [`{package_id}`](packages/{slug(package_id)}.md): {item['title']}")
        lines.append("")
    lines.extend(["## Common Tags", ""])
    for tag, count in tag_counter.most_common(80):
        lines.append(f"- `{tag}`: {count}")
    write_text(output / "domain-index.md", "\n".join(lines))

    print(f"Generated {len(compact_packages)} science package cards under {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
