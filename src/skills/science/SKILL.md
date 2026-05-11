---
name: science
description: Use for natural-science or engineering tasks, scientific software routing, simulation, dataset analysis, model fitting, package checks, HPC-through-shell work, validation, and evidence-backed scientific claims using DeepScientist's `artifact.science(...)` Science Evidence Graph. Includes a progressive-disclosure catalog of FermiLink skilled-scipkg package cards.
skill_role: companion
skill_order: 160
---

# Science

## One-Sentence Summary

Use `bash_exec(...)` to do the real scientific work, use this skill to choose
the right package/reference path, and use `artifact.science(...)` to record the
durable Science Evidence Graph.

## Match Signals

Use this skill when the task includes any of these signals:

- natural science, engineering, simulation, scientific software, numerical solver, HPC, SLURM, SSH, model fitting, or dataset analysis
- package names such as PySCF, LAMMPS, OpenMM, GROMACS, MEEP, Scanpy, Astropy, Geant4, OpenFOAM, CP2K, ABINIT, or similar scientific packages
- requests to verify an environment, run a solver, reproduce a computational result, analyze scientific data, validate units/convergence/schema, or make a scientific claim
- SetupAgent needs to organize a science task into a Copilot handoff or autonomous startup brief

## Control Surface

- Real execution: always `bash_exec(...)`.
- Evidence records: `artifact.science(...)` under the existing `artifact` MCP namespace.
- User-visible milestones or blockers: `artifact.interact(...)`.
- Package knowledge: this skill's references and package cards.
- Do not create a top-level `science` MCP namespace.
- Do not migrate FermiLink runner, HPC profile manager, CLI workflow, FastAPI backend, Chainlit UI, or source implementation into DeepScientist runtime.

## Progressive Disclosure

Read only the references needed for the active task:

- `references/package-index.min.json`: compact index of the 169 package cards; search this first when a package/domain is unclear.
- `references/domain-index.md`: human-readable grouping by inferred scientific domain.
- `references/packages/<package_id>.md`: package-specific routing card with knowledge URL, source URL, package-check pattern, expected science nodes, evidence paths, and pitfalls.
- `references/package-check-playbook.md`: package availability checks before treating a solver as usable.
- `references/artifact-science-tool.md`: exact `artifact.science(...)` contract and examples.
- `references/hpc-via-bash-exec.md`: SSH, scheduler, queue, and remote-log discipline through `bash_exec(...)`.
- `references/claim-type-discipline.md`: computed / parsed / digitized / hypothesis claim discipline.
- `references/science-task-brief-template.md`: SetupAgent and startup brief shape; use as context, not as a required `goal.md` file.

## Workflow

1. Classify the task: package check, computational run, dataset analysis, parameter sweep, validation, claim, or startup brief.
2. If a package/domain is involved, search `references/package-index.min.json` and open only the relevant `references/packages/<package_id>.md` cards.
3. Treat package cards as knowledge pointers only. They do not prove the solver, Python module, executable, license server, dataset, GPU backend, or HPC module exists.
4. Before computed work, use `bash_exec(...)` for import, executable, version, environment-module, and small smoke-test checks when relevant.
5. Record package checks with `artifact.science(..., node_type="science.package_check", ...)`.
6. Run solver commands, scripts, SSH, sbatch/squeue, log reads, and data analysis through `bash_exec(...)`.
7. Record scientific execution as `science.computational_run`, `science.dataset_analysis`, or `science.parameter_sweep` with concrete input, log, output, and evidence paths.
8. Validate convergence, units, schema, controls, tolerances, seeds, or physical/statistical invariants, then record `science.validation_result`.
9. Record `science.claim` only after evidence paths or related science nodes support it.
10. Use `artifact.interact(...)` for decisions or milestones that the user should see, but never as the only scientific evidence.

Science node ids are stable logical ids, not mutable file slots. Call
`record_node` once for a new node id. If status, evidence, or interpretation
changes later, call `update_node` so the graph remains append-only. If a package
check fails or is blocked and that fact affects the route, record it as
`science.package_check` with `status="failed"` or `status="blocked"` and point to
the log or diagnostic file.

## Science Node Types

Use only these v1 node types unless the runtime contract changes:

- `science.package_check`
- `science.computational_run`
- `science.dataset_analysis`
- `science.parameter_sweep`
- `science.validation_result`
- `science.claim`

Prefer `science.computational_run` over a narrower simulation-only term when
the work is solver execution, numerical computation, model fitting, or
engineering computation.

## Claim Discipline

Every `science.claim` needs `claim_type`:

- `computed`: produced by real execution in the current quest
- `parsed`: read from supplied or existing data
- `digitized`: extracted from a paper figure, image, or PDF figure
- `hypothesis`: plausible but not yet verified by computation or data

Computed claims must link to evidence paths or related computed/validation
nodes. If that evidence does not exist yet, record a `hypothesis`, blocker, or
validation need instead.

## SetupAgent Usage

For natural-science or engineering startup sessions, SetupAgent should decide
whether the task is actually suited to autonomous work:

- Ordinary bounded tasks such as one package check, one local calculation, one dataset inspection, or one result explanation should usually route to Copilot mode.
- Long simulation campaigns, HPC campaigns, paper reproduction, or idea-driven scientific research can route to autonomous mode only when compute, data, privacy, network, and success criteria are clear enough.
- When routing to Copilot, fill `session_patch.copilot_handoff.startup_message` with the organized science brief and set `create_and_send=true` so the collaboration workspace starts directly.
- When routing to autonomous, fill `session_patch.science_task` and `session_patch.science_task_brief`; use the brief shape from `references/science-task-brief-template.md` without requiring a `goal.md` file.
- Include expected packages, package-check requirement, expected science node types, HPC expectation, and whether solver installation is unknown.

## Package Catalog Provenance

The package catalog is generated from FermiLink's skilled-scipkg channel and is
stored as DeepScientist-native routing material. The cards preserve package ids,
descriptions, tags, knowledge URLs, source archive URLs, and upstream project
URLs. They do not vendor package source trees and do not install runtimes.

If deeper package knowledge must be downloaded during a quest, preserve the
source URL and license context in the quest evidence. Do not paste large
knowledge-base text into reports without attribution.

## AVOID / Pitfalls

- Do not treat this skill as a solver installation or package manager.
- Do not call a result `computed` from a plot redraw, paper figure reading, or guess.
- Do not weaken tolerances, filters, physical models, convergence criteria, or validation checks merely to make a run pass.
- Do not submit remote/HPC jobs without a log path and status-reading plan.
- Do not create science evidence only in chat.
- Do not let package-card metadata override task-specific evidence.
- Do not use FermiLink as a runtime dependency; use the DeepScientist-native
  package cards as routing references and keep real execution in
  `bash_exec(...)`.

## Validation

A science task is ready to report when these are true:

- package availability is checked or explicitly blocked
- each run or analysis has concrete input/log/output/evidence paths when applicable
- validation status is recorded separately from raw execution status when correctness matters
- claims are typed as computed, parsed, digitized, or hypothesis
- evidence nodes are linked so Canvas can reconstruct the Science Evidence Graph
