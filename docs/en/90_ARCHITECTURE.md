# 90 Architecture: Maintainer Architecture Reference

This document is the maintainer-facing architecture reference for the current open-source repository.

It describes the implementation that actually exists in this checkout. When code and docs diverge, fix the docs in the same change.

## Goals

DeepScientist is a small, local-first research operating system with these stable constraints:

- the authoritative runtime is Python
- `npm` is the install and launch path
- one quest equals one Git repository
- durable state stays in files plus Git
- the public built-in MCP surface stays limited to `memory`, `artifact`, and `bash_exec`
- the workflow remains prompt-led and skill-led instead of stage-scheduler-heavy

## Top-Level Layout

Important repository areas:

- `bin/`
  - npm launcher entrypoint
- `src/deepscientist/`
  - authoritative runtime, daemon, CLI, registries, quest state, connectors
- `src/prompts/`
  - system prompt source
- `src/skills/`
  - first-party stage skills
- `src/ui/`
  - web workspace
- `src/tui/`
  - local TUI
- `docs/`
  - user docs and maintainer docs
- `tests/`
  - runtime, API, prompt, connector, packaging, and UI contract tests

## Launch Chain

The normal user path is:

1. `npm install -g @researai/deepscientist`
2. run `ds`
3. `bin/ds.js` ensures a locked uv-managed Python runtime is ready under `~/DeepScientist/runtime/python-env`
4. the launcher starts the Python daemon
5. the daemon serves the web workspace and shared API surface
6. the TUI and web UI both consume the same daemon contracts

`bin/ds.js` should stay thin. Product behavior belongs in Python services, prompts, and skills.

## Runtime Home

The default runtime home is `~/DeepScientist/`.

Key directories:

- `runtime/`
  - launcher-managed runtime state
  - uv-managed Python environment
  - uv-managed Python installs
  - uv cache
  - built bundle helpers
  - managed local tool installs under `runtime/tools/`
- `config/`
  - YAML configuration and baseline registry data
- `memory/`
  - global memory cards
- `quests/`
  - one quest per Git repository
- `logs/`
  - daemon and runtime logs
- `cache/`
  - reusable caches such as synced skills

## Quest Model

Each quest lives under `~/DeepScientist/quests/<quest_id>/` and is its own Git repository.

Important quest state lives in:

- `quest.yaml`
- `brief.md`
- `plan.md`
- `status.md`
- `SUMMARY.md`
- `.ds/runtime_state.json`
- `.ds/user_message_queue.json`
- `.ds/events.jsonl`
- `.ds/interaction_journal.jsonl`

The quest layout contract is defined in `src/deepscientist/quest/layout.py`. If it changes, update quest services, daemon handlers, UI/TUI consumers, and tests together.

## Core Runtime Boundaries

### CLI

- file: `src/deepscientist/cli.py`
- responsibility: thin Python command surface over quest, config, doctor, and runtime services

### Daemon

- files:
  - `src/deepscientist/daemon/app.py`
  - `src/deepscientist/daemon/api/router.py`
  - `src/deepscientist/daemon/api/handlers.py`
- responsibility:
  - serve the local web workspace
  - expose shared API routes
  - coordinate quest turn execution, inbox delivery, connectors, and run control

### Quest

- files under `src/deepscientist/quest/`
- responsibility:
  - create quests
  - maintain quest snapshots
  - persist runtime state
  - derive explorer and canvas state

Quest readers cache canonical projections rather than every JSON artifact in historical worktrees. Rebuilding a projection reads and deduplicates those source files without pinning all of their parsed copies.

Each `QuestService` reader cache has a 64 MiB object-graph byte budget and a 2,048-entry LRU limit. This covers file reads, full JSONL reads, JSONL tails, snapshots, and parsed Codex history; existing locks still serialize cache access. Oversized entries remain readable but bypass retention, and inode/mtime/size checks still invalidate changed files. The budgets bound retained reader data, not total process memory or transient response-building allocations. Callers must not mutate cached entry graphs after insertion.

Public history/event windows and exposed tail-cache entries return owned nested records. Mutating a returned result must not change a later read or enlarge the cached graph outside its byte accounting.

### Artifact

- files under `src/deepscientist/artifact/`
- responsibility:
  - durable structured artifacts
  - Git-backed quest operations
  - baselines, approvals, progress, reports, interactions

### Memory

- files under `src/deepscientist/memory/`
- responsibility:
  - global and quest-scoped Markdown memory

### Bash Execution

- files under `src/deepscientist/bash_exec/`
- responsibility:
  - managed, stoppable, durable shell sessions

## Public MCP Boundary

The public built-in MCP surface must remain:

- `memory`
- `artifact`
- `bash_exec`

Do not introduce public `git`, `connector`, or `runtime_tool` MCP namespaces.

Git behavior stays inside `artifact`. Managed local tooling is a daemon/runtime concern, not a public MCP surface.

## Registry-First Extension Points

DeepScientist prefers small explicit registries over large dispatch branches.

Current registry-backed areas include:

- runners
- channels
- connector bridges
- skill discovery
- managed local runtime tools

Patterns should stay close to:

- `register_*()`
- `get_*()`
- `list_*()`

## Managed Local Runtime Tools

Managed local tools are optional helper runtimes installed under `~/DeepScientist/runtime/tools/`.

Examples:

- TinyTeX for local `pdflatex`
- future candidates such as `pandoc`, `graphviz`, or `ffmpeg`

The runtime-tool layer lives under `src/deepscientist/runtime_tools/` and exists to:

- keep install logic out of unrelated subsystems
- let the daemon and CLI inspect tool health in one place
- resolve binaries consistently
- make new managed tools register the same way as runners or channels

Current pieces:

- `runtime_tools/registry.py`
  - `register_runtime_tool()`, `get_runtime_tool_factory()`, `list_runtime_tool_names()`
- `runtime_tools/service.py`
  - high-level access for status, install, and binary resolution
- `runtime_tools/builtins.py`
  - built-in registrations
- `runtime_tools/tinytex.py`
  - TinyTeX provider adapter

Low-level TinyTeX implementation remains in `src/deepscientist/tinytex.py`.

## Prompt And Skill Flow

Research workflow behavior should primarily live in:

- `src/prompts/system.md`
- `src/deepscientist/prompts/builder.py`
- `src/skills/*/SKILL.md`

The daemon should persist and route state, but avoid becoming a rigid workflow scheduler.

## UI Contract

The web UI and TUI share the same daemon API contract.

If an API route changes:

- update daemon handlers/router
- update `src/ui/src/lib/api.ts`
- update `src/tui/src/lib/api.ts`
- update tests that enforce the contract

Preserve `/projects` and `/projects/:quest_id` as the main web workspace routes.

## Documentation Contract

Maintainer docs:

- this file: `docs/en/90_ARCHITECTURE.md`
- `docs/en/91_DEVELOPMENT.md`

User docs:

- `docs/en/*.md`
- `docs/zh/*.md`

Do not put temporary implementation checklists or planning drafts under `docs/`.

## Testing Layers

Typical validation layers:

- Python unit and integration tests under `tests/`
- API contract tests
- prompt and skill tests
- web/TUI bundle builds
- packaging checks such as `npm pack --dry-run --ignore-scripts`

When changing registries, quest layout, API contracts, prompts, or packaging, update the corresponding tests in the same change.
