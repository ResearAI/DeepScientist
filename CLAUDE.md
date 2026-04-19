# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DeepScientist is a local-first autonomous research studio that manages long-horizon research workflows. It's a Python-based system with a Node.js launcher, web UI, and TUI, designed to keep research projects moving through baselines, experiments, and paper outputs.

**Core principle**: One quest = one Git repository. All durable state lives in files and Git.

## Quick Start Commands

### Installation and Setup

```bash
# Install from repository
bash install.sh

# Install with LaTeX runtime
bash install.sh --with-tinytex

# Start DeepScientist
ds

# Check system health
ds doctor

# Check specific runner
ds doctor --runner codex
ds doctor --runner claude
ds doctor --runner opencode
```

### Development Commands

```bash
# Run tests
pytest

# Build web UI
npm --prefix src/ui install
npm --prefix src/ui run build

# Build TUI
npm --prefix src/tui install
npm --prefix src/tui run build

# Validate Python syntax
python3 -m compileall src/deepscientist

# Validate packaging
npm pack --dry-run --ignore-scripts
```

### Runtime Commands

```bash
# Quest management
ds init                    # Create new quest
ds status                  # Show quest status
ds pause                   # Pause quest
ds resume                  # Resume quest

# LaTeX runtime
ds latex status
ds latex install-runtime

# Configuration
ds config                  # Manage configuration

# Memory and baselines
ds memory                  # Memory operations
ds baseline                # Baseline registry operations
```

## Architecture

### Launch Chain

1. User runs `ds` (npm global bin)
2. `bin/ds.js` ensures uv-managed Python runtime exists at `~/DeepScientist/runtime/python-env`
3. Launcher starts Python daemon
4. Daemon serves web workspace at `http://127.0.0.1:20999`
5. Web UI and TUI consume same daemon API

### Runtime Home: `~/DeepScientist/`

```
~/DeepScientist/
├── runtime/          # Launcher-managed runtime (uv Python env, tools)
├── config/           # YAML configuration and baseline registry
├── memory/           # Global memory cards
├── quests/           # One quest per Git repository
├── logs/             # Daemon and runtime logs
└── cache/            # Reusable caches (synced skills)
```

### Quest Structure

Each quest lives at `~/DeepScientist/quests/<quest_id>/` as a Git repository:

```
quest_id/
├── quest.yaml                        # Quest metadata
├── brief.md                          # Research brief
├── plan.md                           # Implementation plan
├── status.md                         # Current status
├── SUMMARY.md                        # Quest summary
└── .ds/
    ├── runtime_state.json            # Runtime state
    ├── user_message_queue.json       # User message queue
    ├── events.jsonl                  # Event log
    └── interaction_journal.jsonl     # Interaction history
```

### Core Subsystems

**Python Runtime** (`src/deepscientist/`)
- `cli.py` - CLI commands
- `daemon/` - Web server, API routes, quest execution coordination
- `quest/` - Quest creation, snapshots, state persistence
- `artifact/` - Git-backed structured artifacts
- `memory/` - Global and quest-scoped memory
- `bash_exec/` - Managed shell sessions
- `mcp/` - MCP server implementation
- `runners/` - Runner implementations (Codex, Claude, OpenCode)
- `bridges/` - Connector transport adaptation
- `channels/` - Connector delivery and runtime
- `skills/` - Skill discovery and installation
- `prompts/` - Prompt builder
- `runtime_tools/` - Managed local tools (TinyTeX, etc.)

**Prompts** (`src/prompts/`)
- `system.md` - Core system prompt
- `system_copilot.md` - Copilot mode prompt
- `connectors/` - Connector-specific prompts
- `contracts/` - Contract definitions
- `benchstore/` - BenchStore prompts
- `start_setup/` - Setup prompts

**Skills** (`src/skills/`)
Stage skills that define research workflow:
- `intake-audit/` - Initial quest setup
- `scout/` - Literature review
- `baseline/` - Baseline reproduction
- `idea/` - Idea generation
- `experiment/` - Experiment execution
- `analysis-campaign/` - Analysis
- `write/` - Paper writing
- `figure-polish/` - Figure refinement
- `review/` - Paper review
- `rebuttal/` - Rebuttal generation
- `finalize/` - Final deliverables

**Web UI** (`src/ui/`) - React-based workspace
**TUI** (`src/tui/`) - Terminal interface

## Key Contracts

### Public MCP Surface

Only three public MCP namespaces exist:
- `memory` - Memory operations
- `artifact` - Git-backed artifacts and quest operations
- `bash_exec` - Managed shell execution

**Do not add** new public namespaces like `git`, `connector`, or `runtime_tool`.

### Bash Execution Contract

**Critical**: All terminal operations MUST use `bash_exec(...)`. Native `shell_command` is forbidden.

This includes: `ls`, `cat`, `git`, `python`, `npm`, `uv`, file inspection, package management, etc.

### Quest Layout Contract

Defined in `src/deepscientist/quest/layout.py`. Changes require updating:
- Quest services
- Daemon handlers
- UI/TUI consumers
- Tests

### Skill Contract

Skills are discovered from `src/skills/<skill_id>/SKILL.md` with frontmatter:

```markdown
---
name: skill-name
description: One-line purpose
skill_role: stage|companion|custom
skill_order: 60
---
```

### Runner Contract

Three built-in runners:
- `codex` (primary, battle-tested)
- `claude` (experimental)
- `opencode` (experimental)

Runners are registered in `src/deepscientist/runners/` and discovered via registry.

## Development Workflow

### Adding a New MCP Tool

1. Add handler in `src/deepscientist/mcp/server.py` under appropriate namespace
2. Update `src/deepscientist/runners/codex.py` approval policy if needed
3. Update docs: `docs/en/07_MEMORY_AND_MCP.md`, `docs/en/14_PROMPT_SKILLS_AND_MCP_GUIDE.md`
4. Add tests in `tests/test_mcp_servers.py`

### Adding a New Skill

1. Create `src/skills/<skill_id>/SKILL.md` with frontmatter
2. Update `src/deepscientist/skills/registry.py` if canonical stage/companion
3. Update `src/deepscientist/prompts/builder.py` if stage needs memory plan
4. Add tests in `tests/test_stage_skills.py`, `tests/test_skill_contracts.py`

### Adding a New Connector

1. Add config in `src/deepscientist/config/models.py`
2. Add validation in `src/deepscientist/config/service.py`
3. Add bridge in `src/deepscientist/bridges/connectors.py`
4. Register in `src/deepscientist/bridges/builtins.py`
5. Register channel in `src/deepscientist/channels/builtins.py`
6. Wire daemon lifecycle in `src/deepscientist/daemon/app.py` if needed
7. Add prompt in `src/prompts/connectors/<connector>.md` if needed
8. Add tests for config, bridge, and API

### Adding a Managed Runtime Tool

1. Create provider in `src/deepscientist/runtime_tools/<tool>.py`
2. Implement: `tool_name`, `status()`, `install()`, `resolve_binary()`
3. Register in `src/deepscientist/runtime_tools/builtins.py`
4. Access via `RuntimeToolService`, not direct imports
5. Install under `~/DeepScientist/runtime/tools/`

## Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_daemon_api.py

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=src/deepscientist
```

Key test files:
- `tests/test_daemon_api.py` - API contract tests
- `tests/test_mcp_servers.py` - MCP tool tests
- `tests/test_stage_skills.py` - Skill tests
- `tests/test_codex_runner.py` - Runner tests
- `tests/test_connector_bridges.py` - Connector tests
- `tests/test_benchstore.py` - BenchStore tests

## Code Style and Principles

- Keep files simple with direct control flow
- Avoid unnecessary abstraction layers
- Use small, explicit registries
- Prefer file- and Git-based state over hidden runtime state
- One quest = one Git repository (never violate this)
- Python is authoritative runtime, npm is launcher
- Prompts and skills carry workflow behavior, not rigid schedulers

## Documentation

- User docs: `docs/en/` and `docs/zh/`
- Architecture: `docs/en/90_ARCHITECTURE.md`
- Development: `docs/en/91_DEVELOPMENT.md`
- Contributing: `CONTRIBUTING.md`

Update docs when behavior or architecture changes.

## Common Pitfalls

1. **Do not** use native `shell_command` - always use `bash_exec(...)`
2. **Do not** add new public MCP namespaces beyond `memory`, `artifact`, `bash_exec`
3. **Do not** bypass quest layout contracts - update all consumers together
4. **Do not** commit `node_modules/`, `dist/`, `__pycache__/`, or local secrets
5. **Do not** make quests anything other than Git repositories
6. **Do not** add connector-specific logic to unrelated quest code
7. **Do not** put workflow logic in daemon schedulers - use prompts and skills

## Release Checklist

Before publishing:
1. Python tests pass (`pytest`)
2. Web and TUI bundles build (`npm run ui:build`, `npm run tui:build`)
3. Packaging validates (`npm pack --dry-run --ignore-scripts`)
4. README and docs match current behavior
5. New config/route/state fields have tests

## Support

- Issues: https://github.com/ResearAI/DeepScientist/issues
- Docs: https://github.com/ResearAI/DeepScientist/tree/main/docs/en
- Paper: https://openreview.net/forum?id=cZFgsLq8Gs
