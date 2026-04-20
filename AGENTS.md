# DeepScientist Repository Guide

This `AGENTS.md` applies to the entire repository.

It is the repository-level guide for coding agents and maintainers working in this checkout.
It should describe the code and docs that actually exist here today.

When code and docs diverge, prefer the current runtime behavior and tests, then update the docs in the same change.

## Mission

Build DeepScientist as a small, local-first research operating system that:

- runs on the user's machine by default
- installs cleanly through npm
- keeps the authoritative runtime in Python
- uses prompt-led and skill-led workflow control
- stores durable state in files plus Git
- keeps one quest as one Git repository
- supports the full research loop inside one quest workspace

The target is a focused core runtime, not a large platform.

## Read First

Do not start from memory. Start from the files that actually exist.

Recommended reading order for coding agents:

1. `README.md`
2. `docs/en/README.md`
3. `docs/en/90_ARCHITECTURE.md`
4. `docs/en/91_DEVELOPMENT.md`
5. the smallest subsystem-specific doc set that matches the task
6. the actual implementation under `src/`
7. the relevant tests under `tests/`

Important current docs by topic:

- product and docs index:
  - `README.md`
  - `docs/en/README.md`
  - `docs/zh/README.md`
- maintainer architecture and workflow:
  - `docs/en/90_ARCHITECTURE.md`
  - `docs/en/91_DEVELOPMENT.md`
- user-facing architecture and workflow:
  - `docs/en/13_CORE_ARCHITECTURE_GUIDE.md`
  - `docs/en/14_PROMPT_SKILLS_AND_MCP_GUIDE.md`
  - `docs/en/06_RUNTIME_AND_CANVAS.md`
  - `docs/en/07_MEMORY_AND_MCP.md`
- runtime and settings:
  - `docs/en/00_QUICK_START.md`
  - `docs/en/01_SETTINGS_REFERENCE.md`
  - `docs/en/05_TUI_GUIDE.md`
  - `docs/en/09_DOCTOR.md`
  - `docs/en/31_LOCAL_BROWSER_AUTH.md`
  - `docs/en/20_WORKSPACE_MODES_GUIDE.md`
- runner/provider setup:
  - `docs/en/15_CODEX_PROVIDER_SETUP.md`
  - `docs/en/24_CLAUDE_CODE_PROVIDER_SETUP.md`
  - `docs/en/25_OPENCODE_PROVIDER_SETUP.md`
  - `docs/en/27_KIMI_CODE_PROVIDER_SETUP.md`
  - `docs/en/21_LOCAL_MODEL_BACKENDS_GUIDE.md`
- connectors:
  - `docs/en/03_QQ_CONNECTOR_GUIDE.md`
  - `docs/en/04_LINGZHU_CONNECTOR_GUIDE.md`
  - `docs/en/10_WEIXIN_CONNECTOR_GUIDE.md`
  - `docs/en/16_TELEGRAM_CONNECTOR_GUIDE.md`
  - `docs/en/17_WHATSAPP_CONNECTOR_GUIDE.md`
  - `docs/en/18_FEISHU_CONNECTOR_GUIDE.md`
  - `docs/en/19_EXTERNAL_CONTROLLER_GUIDE.md`
- BenchStore:
  - `docs/en/22_BENCHSTORE_YAML_REFERENCE.md`
  - `docs/en/23_BENCHSTORE_GITHUB_RELEASES_SPEC.md`

Supplementary contributor notes:

- `CONTRIBUTING.md`
- `CLAUDE.md`

If a supplementary doc conflicts with this file, current code, or the maintainer docs in `docs/en/90_*` and `docs/en/91_*`, follow:

1. current code and tests
2. this `AGENTS.md`
3. `docs/en/90_ARCHITECTURE.md` and `docs/en/91_DEVELOPMENT.md`
4. supplementary contributor docs

## Scope Boundary For Coding Agents

Do not confuse repository contribution rules with the in-product DeepScientist agent contract.

Examples:

- files under `src/prompts/` and `src/skills/` often tell the runtime agent to use `bash_exec`
- that is a product/runtime behavior contract
- it is not a rule that repository contributors must avoid normal local shell commands while editing this repo

When changing prompt or skill behavior, preserve that distinction explicitly.

## Non-Negotiable Contracts

### 1. One quest = one Git repository

- Every quest has one absolute `quest_root`.
- All durable quest content stays inside that quest root.
- Branches and worktrees express divergence inside that quest repository.

### 2. Python runtime, npm launcher

- The authoritative runtime lives under `src/deepscientist/`.
- `bin/ds.js` remains a thin launcher over the Python daemon and built UI bundles.
- The public npm package publishes as `@researai/deepscientist`.
- Public npm installs must ship prebuilt `src/ui/dist/` and `src/tui/dist/` bundles.
- Do not rely on end-user `postinstall` builds for the public npm path.

### 3. Only three public built-in MCP namespaces

Keep the public built-in MCP surface limited to:

- `memory`
- `artifact`
- `bash_exec`

Git behavior belongs inside `artifact`.
Durable shell execution belongs inside `bash_exec`.
Do not add new public MCP namespaces such as `git`, `connector`, or `runtime_tool`.

### 4. Prompt-led, skill-led workflow

- The prompt defines workflow expectations and filesystem contract.
- Skills provide specialized execution behavior.
- The daemon persists, restores, and routes state, but should stay thin.
- Avoid hard-coding a large central stage scheduler when prompt plus skills are enough.

### 5. Registry-first extension points

Prefer small registries for:

- runners
- channels
- connector bridges
- skill discovery
- managed local runtime tools
- optional plugin adapters

Prefer `register_*()`, `get_*()`, and `list_*()` APIs over large dispatch branches.

### 6. Shared web and TUI contract

- The web UI and TUI must consume the same daemon API and event model.
- If an API route changes, update the daemon, web client, TUI client, and tests together.
- Preserve `/projects` and `/projects/:questId` style routing in the web workspace.

### 7. QQ is first-class, but still generic

- QQ support is part of the core product shape.
- It should still fit the generic channel and bridge model instead of becoming a separate one-off runtime.

## Actual Repository Structure

Important top-level directories:

- `assets/`
- `bin/`
- `docs/`
- `AISB/`
- `src/deepscientist/`
- `src/prompts/`
- `src/skills/`
- `src/ui/`
- `src/tui/`
- `tests/`

Important runtime entry points:

- launcher: `bin/ds.js`
- CLI: `src/deepscientist/cli.py`
- daemon: `src/deepscientist/daemon/app.py`
- API router: `src/deepscientist/daemon/api/router.py`
- API handlers: `src/deepscientist/daemon/api/handlers.py`
- prompt builder: `src/deepscientist/prompts/builder.py`
- system prompt: `src/prompts/system.md`

Important subsystem areas:

- quest state: `src/deepscientist/quest/`
- artifacts and Git-backed durable state: `src/deepscientist/artifact/`
- memory: `src/deepscientist/memory/`
- MCP: `src/deepscientist/mcp/`
- bash execution: `src/deepscientist/bash_exec/`
- runners: `src/deepscientist/runners/`
- connectors and bridges:
  - `src/deepscientist/channels/`
  - `src/deepscientist/bridges/`
  - `src/deepscientist/connector/`
- config and validation:
  - `src/deepscientist/config/models.py`
  - `src/deepscientist/config/service.py`
- managed local tools: `src/deepscientist/runtime_tools/`
- BenchStore:
  - `src/deepscientist/benchstore/`
  - `AISB/catalog/`

## Runtime Home And Quest Layout

The default runtime home is usually `~/DeepScientist/`, but do not assume that in local debugging.

This repository may be operated against any explicit `--home`, including non-default trees such as:

- `~/DeepScientist`
- `/ssdwork/DeepScientist`
- temporary test homes

Before restarting or modifying a live system, inspect:

- the running daemon process
- the actual `config.yaml`
- any existing supervisor or launcher process
- the effective home path returned by `/api/health`

Default runtime directories:

- `runtime/`
- `config/`
- `memory/`
- `quests/`
- `plugins/`
- `logs/`
- `cache/`

Each quest under `quests/<quest_id>/` is its own Git repository.

Important quest files:

- `quest.yaml`
- `brief.md`
- `plan.md`
- `status.md`
- `SUMMARY.md`

Important quest runtime directories:

- `artifacts/`
- `baselines/`
- `experiments/`
- `literature/`
- `handoffs/`
- `paper/`
- `memory/`
- `.ds/`

The quest layout contract is defined in `src/deepscientist/quest/layout.py`.
If it changes, update the services, API consumers, UI/TUI, and tests together.

## Skills, Anchors, And Prompt Reality

First-party skills live under `src/skills/`.

Canonical stage anchors today are:

- `scout`
- `baseline`
- `idea`
- `experiment`
- `analysis-campaign`
- `write`
- `finalize`

Important nuance:

- `decision` is cross-cutting and important, but it is not a canonical stage anchor
- `intake-audit`, `figure-polish`, `review`, and `rebuttal` exist and may be used, but do not treat them as the default linear anchor chain unless the code actually does so

Workflow behavior should primarily live in:

- `src/prompts/system.md`
- `src/prompts/contracts/`
- `src/prompts/connectors/`
- `src/deepscientist/prompts/builder.py`
- `src/skills/*/SKILL.md`

## Built-In Runners

Current built-in runner surface in this checkout includes:

- `codex`
- `claude`
- `kimi`
- `opencode`

Do not describe a runner as implemented until all of these are wired where relevant:

- runner implementation
- registry / metadata
- config defaults and validation
- daemon and CLI integration
- user-visible docs
- tests

## Documentation Rules

- User-facing docs belong in `docs/en/` and `docs/zh/`.
- Maintainer-facing docs live in:
  - `docs/en/90_ARCHITECTURE.md`
  - `docs/en/91_DEVELOPMENT.md`
- Do not add internal planning notes, temporary specs, or scratch checklists under `docs/`.
- Keep doc names stable when they are linked from the UI or README.
- Do not reference deleted or private local files.
- If a user-facing behavior changes, update the relevant English docs and the matching Chinese docs in the same change when a translation exists.
- If a maintainer-only behavior changes, update `docs/en/90_ARCHITECTURE.md` and/or `docs/en/91_DEVELOPMENT.md` as needed.

## Public Repository Hygiene

- Do not commit workstation-specific absolute paths.
- Do not commit generated artifacts such as:
  - `node_modules/`
  - `dist/`
  - `.turbo/`
  - `__pycache__/`
  - `.pytest_cache/`
- Do not commit local secrets or tokens.
- Do not add references to deleted docs or old file names.

## Coding-Agent Workflow Rules

- Inspect the existing code before proposing a new abstraction.
- Prefer small, coherent changes over broad mixed refactors.
- Optimize for clarity, correctness, and maintainability over feature volume.
- Use the smallest relevant doc set first, then verify against code and tests.
- Do not preserve stale documentation references just because they existed before.
- When code and docs diverge, update the docs in the same change.
- Keep repository rules and runtime prompt rules separate.
- When debugging live installs, identify the actual runtime home and actual Python runtime before restarting anything.

## Common Commands

Repository install and local development:

```bash
bash install.sh
python -m pip install -e .
npm install
npm --prefix src/ui install
npm --prefix src/tui install
```

Build commands:

```bash
npm --prefix src/ui run build
npm --prefix src/tui run build
npm pack --dry-run --ignore-scripts
```

Python validation:

```bash
pytest
python -m compileall src/deepscientist
```

Start the product through the public path:

```bash
ds
ds doctor
```

Start the daemon directly:

```bash
python -m deepscientist.cli --home <HOME> daemon --host 0.0.0.0 --port 20999 --auth false
```

Run the web UI dev server against a daemon:

```bash
VITE_PROXY_TARGET='http://127.0.0.1:20999' npm --prefix src/ui run dev
```

## Change Checklists

When changing quest layout or durable quest state:

- update `src/deepscientist/quest/layout.py`
- update `src/deepscientist/quest/service.py`
- update snapshot consumers if fields changed
- update `tests/test_init_and_quest.py`
- update `tests/test_daemon_api.py`

When changing prompts or stage skills:

- update the relevant files under `src/prompts/`
- update `src/deepscientist/prompts/builder.py` if prompt assembly changed
- update `src/skills/<skill_id>/SKILL.md`
- keep installer and mirrored skill behavior in sync
- update `tests/test_stage_skills.py`
- update `tests/test_prompt_builder.py`
- update user docs such as:
  - `docs/en/14_PROMPT_SKILLS_AND_MCP_GUIDE.md`
  - `docs/en/06_RUNTIME_AND_CANVAS.md`

When changing MCP, memory, artifact, or bash-exec behavior:

- update the relevant files under:
  - `src/deepscientist/mcp/`
  - `src/deepscientist/memory/`
  - `src/deepscientist/artifact/`
  - `src/deepscientist/bash_exec/`
- keep the public namespace boundary at `memory`, `artifact`, `bash_exec`
- update `tests/test_mcp_servers.py`
- update `tests/test_memory_and_artifact.py`
- update `tests/test_daemon_api.py`
- update docs such as:
  - `docs/en/07_MEMORY_AND_MCP.md`
  - `docs/en/14_PROMPT_SKILLS_AND_MCP_GUIDE.md`

When changing runners:

- update `src/deepscientist/runners/`
- update built-in registration and metadata
- update config defaults in `src/deepscientist/config/models.py`
- update validation and help text in `src/deepscientist/config/service.py`
- update daemon / CLI wiring if needed
- update runner docs:
  - `docs/en/15_CODEX_PROVIDER_SETUP.md`
  - `docs/en/24_CLAUDE_CODE_PROVIDER_SETUP.md`
  - `docs/en/25_OPENCODE_PROVIDER_SETUP.md`
  - `docs/en/27_KIMI_CODE_PROVIDER_SETUP.md`
- update tests for runner behavior and API surface

When changing connectors or bridges:

- update defaults in `src/deepscientist/config/models.py`
- update validation/help text in `src/deepscientist/config/service.py`
- update `src/deepscientist/channels/`
- update `src/deepscientist/bridges/`
- update connector docs under `docs/en/` and `docs/zh/`
- update connector tests and relevant daemon/API tests

When changing managed local runtime tools:

- update `src/deepscientist/runtime_tools/`
- update any concrete helper adapter such as `src/deepscientist/tinytex.py` if needed
- access new tooling through the runtime-tool registry and service
- update maintainer docs:
  - `docs/en/90_ARCHITECTURE.md`
  - `docs/en/91_DEVELOPMENT.md`
- update user docs if install or troubleshooting behavior is user-visible
- update tests for registration, status, install, and binary resolution

When changing BenchStore catalog or packaging behavior:

- update `AISB/catalog/` entries or BenchStore runtime code together
- follow `docs/en/22_BENCHSTORE_YAML_REFERENCE.md`
- follow `docs/en/23_BENCHSTORE_GITHUB_RELEASES_SPEC.md` for downloadable bundles
- update BenchStore API/UI tests when behavior changes

When changing API surface used by web and TUI:

- update `src/deepscientist/daemon/api/router.py`
- update `src/deepscientist/daemon/api/handlers.py`
- update `src/ui/src/lib/api.ts`
- update TUI client code under `src/tui/src/`
- update contract tests such as `tests/test_api_contract_surface.py`

When changing packaging and release behavior:

- keep `package.json`, `pyproject.toml`, `README.md`, and bundle expectations aligned
- remember that the public package ships:
  - `AGENTS.md`
  - docs
  - prompts
  - skills
  - `src/ui/dist/`
  - `src/tui/dist/`
- run `npm pack --dry-run --ignore-scripts` before treating packaging work as done

## Final Rule

Use the actual checkout as the source of truth.
If a file path in an older note does not exist anymore, fix the note rather than preserving the mistake.
