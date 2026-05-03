# 91 Development Guide: Maintainer Workflow and Repository Guide

This guide is for maintainers and contributors working inside the repository.

For architecture, read [90_ARCHITECTURE.md](90_ARCHITECTURE.md) first.

## Local Prerequisites

Recommended baseline:

- Node.js `>=18.18`
- npm `>=9`
- Python `>=3.11`
- Git on `PATH`

Optional local toolchains:

- Codex CLI for the runnable agent path
- TinyTeX or another LaTeX distribution if you want local PDF compilation

## Common Local Flows

### Install into a separate local runtime tree

```bash
bash install.sh
```

### Install plus a managed TinyTeX runtime

```bash
bash install.sh --with-tinytex
```

### Start the product

```bash
ds
```

### Check local health

```bash
ds doctor
```

### Check or install the managed LaTeX runtime

```bash
ds latex status
ds latex install-runtime
```

## Build Commands

Build the web UI:

```bash
npm --prefix src/ui install
npm --prefix src/ui run build
```

Build the TUI:

```bash
npm --prefix src/tui install
npm --prefix src/tui run build
```

Run the TUI with route/render diagnostics:

```bash
ds --tui --debug --debug-log /tmp/deepscientist_tui_debug.jsonl
```

Use this when validating command routing, config editor behavior, or Web/TUI parity. Debug JSONL must stay redacted for config editor buffers and secret-like fields; if a TUI change adds a new input surface, add or update an E2E assertion for that redaction boundary.

Run Web Settings with the browser debug inspector:

```text
/settings/connector/qq?debug=1
```

or:

```js
localStorage.setItem('deepscientist.debug', '1')
localStorage.setItem('deepscientist.debug.log', '1')
```

The Web inspector must stay hidden unless debug is enabled. It must not include raw config document content or secret-like structured config fields in the snapshot. Focused regression check:

```bash
cd src/ui && E2E_BASE_URL=http://127.0.0.1:21888/ui npx playwright test e2e/web-debug.spec.ts --project=chromium
```

## Test Commands

Quick Python test run:

```bash
pytest
```

Useful focused checks:

```bash
python3 -m compileall src/deepscientist
node -c bin/ds.js
npm pack --dry-run --ignore-scripts
```

## Release-Oriented Checks

Before publishing or cutting a release, verify:

1. Python tests pass.
2. Web and TUI bundles build cleanly.
3. `npm pack --dry-run --ignore-scripts` succeeds.
4. README and linked docs match the current runtime behavior.
5. Any new config, route, or quest-state fields have matching tests.
6. Any TUI command or surface change updates the debug snapshot mapping and keeps `--debug-log` free of raw secrets.

## Managed Runtime Tools

Managed local tools live under `src/deepscientist/runtime_tools/`.

The goal is to keep optional local helper runtimes consistent and easy to extend.

### Current structure

- `models.py`
  - provider protocol and shared types
- `registry.py`
  - registration and lookup
- `builtins.py`
  - built-in registrations
- `service.py`
  - high-level access for runtime code
- `tinytex.py`
  - TinyTeX adapter

### Registration flow

Every managed tool should follow the same pattern:

1. Add a provider module under `src/deepscientist/runtime_tools/`.
2. Expose a provider object with:
   - `tool_name`
   - `status()`
   - `install()`
   - `resolve_binary(binary)`
3. Register it in `runtime_tools/builtins.py`.
4. Access it through `RuntimeToolService`, not by scattering direct imports across the repo.
5. Document it if it changes user-visible install or troubleshooting behavior.

### Minimal provider example

```python
from pathlib import Path


class ExampleRuntimeTool:
    tool_name = "example"

    def __init__(self, home: Path) -> None:
        self.home = home

    def status(self) -> dict:
        return {"ok": True, "summary": "Example tool is healthy."}

    def install(self) -> dict:
        return {"ok": True, "changed": False, "summary": "Nothing to install."}

    def resolve_binary(self, binary: str) -> dict:
        return {"binary": binary, "path": None, "source": None, "root": None, "bin_dir": None}
```

Register it in `runtime_tools/builtins.py`:

```python
from .registry import register_runtime_tool
from .example import ExampleRuntimeTool


def register_builtin_runtime_tools(*, home=None) -> None:
    register_runtime_tool("example", lambda **kwargs: ExampleRuntimeTool(kwargs["home"]))
```

Use it from runtime code:

```python
from deepscientist.runtime_tools import RuntimeToolService


service = RuntimeToolService(home)
status = service.status("example")
match = service.resolve_binary("example-binary", preferred_tools=("example",))
```

### Rules for adding a new managed tool

- keep the tool optional unless it is absolutely required for the core product
- do not add a public MCP namespace for it
- do not wire it directly into unrelated modules when `RuntimeToolService` is enough
- prefer install locations under `~/DeepScientist/runtime/tools/`
- keep clear source reporting such as `tinytex` versus `path`
- add tests for registration, status, and binary resolution

## Extending Core Runtime

This section is the maintainer checklist for adding one new built-in MCP tool, one new skill, or one new connector.

Keep the extension shape close to the repository's existing registries and contracts. Do not invent a parallel path when the current registry or prompt system already covers the need.

### Add a built-in MCP tool

Public MCP surface must stay limited to:

- `memory`
- `artifact`
- `bash_exec`

Do not add a new public namespace such as `git`, `connector`, or `runtime_tool`.

If you need new Git behavior, add it under `artifact`.
If you need new durable shell behavior, add it under `bash_exec`.

#### Files to change

- `src/deepscientist/mcp/server.py`
  - add the new `@server.tool(...)` handler under `build_memory_server(...)`, `build_artifact_server(...)`, or `build_bash_exec_server(...)`
- `src/deepscientist/mcp/context.py`
  - only if the new tool needs extra quest/runtime context wiring
- `src/deepscientist/runners/codex.py`
  - if the tool should appear in built-in MCP approval policy defaults, add it under `_BUILTIN_MCP_TOOL_APPROVALS`
- `docs/en/07_MEMORY_AND_MCP.md`
  - update user-visible semantics if the tool changes how the namespace should be used
- `docs/en/14_PROMPT_SKILLS_AND_MCP_GUIDE.md`
  - update the built-in MCP description if the tool meaning materially changes

#### Implementation rules

1. Keep the handler thin. Put durable state changes in the underlying service layer such as `ArtifactService`, `MemoryService`, or `BashExecService`.
2. Use `McpContext` for quest-local paths instead of reconstructing runtime state ad hoc.
3. Use read-only annotations for non-mutating tools.
4. If the tool changes durable quest state but does not itself send a user-visible message, follow the existing artifact watchdog pattern in `mcp/server.py`.
5. Do not bypass the current namespace meaning. Example: do not hide shell execution inside `artifact`.

#### Minimum test checklist

- `tests/test_mcp_servers.py`
  - namespace wiring and tool call behavior
- `tests/test_memory_and_artifact.py`
  - if the tool changes artifact or memory semantics
- `tests/test_daemon_api.py`
  - if API payloads or quest projections depend on the new tool's outputs

### Add a skill

Skills are discovered from disk. The canonical location is:

- `src/skills/<skill_id>/SKILL.md`

The runtime discovers skills through:

- `src/deepscientist/skills/registry.py`

The prompt builder projects them through:

- `src/deepscientist/prompts/builder.py`
- `src/deepscientist/skills/installer.py`

#### Minimal skill shape

Create a directory:

```text
src/skills/<skill_id>/
```

and add:

```md
---
name: my-skill
description: One-line purpose statement.
skill_role: stage
skill_order: 60
---

# My Skill
...
```

Supported `skill_role` values are:

- `stage`
- `companion`
- `custom`

Optional projected agent files:

- `src/skills/<skill_id>/agents/openai.yaml`
- `src/skills/<skill_id>/agents/claude.md`

#### Files to change

- `src/skills/<skill_id>/SKILL.md`
  - required
- `src/deepscientist/skills/registry.py`
  - update `_DEFAULT_STAGE_SKILLS` or `_DEFAULT_COMPANION_SKILLS` if this is a canonical built-in stage or companion skill rather than an ad hoc custom one
- `src/deepscientist/prompts/builder.py`
  - update `STAGE_MEMORY_PLAN` if the skill is a real stage that needs a first-class memory retrieval plan
- `docs/en/14_PROMPT_SKILLS_AND_MCP_GUIDE.md`
  - update the skill guide if the public workflow shape changed

#### Skill rules

1. Put execution discipline inside `SKILL.md`, not inside a central Python stage scheduler.
2. Reuse the existing prompt contract language:
   - interaction discipline
   - tool discipline
   - stage purpose
   - completion or handoff rules
3. If the skill is a canonical stage, give it a stable place in the stage order and memory plan.
4. If the skill is only auxiliary, prefer `skill_role: companion` or `custom` rather than bloating the canonical stage chain.
5. Remember that `SkillInstaller` mirrors skills into the active Codex/Claude projection trees. Keep paths and file names stable.

#### Minimum test checklist

- `tests/test_stage_skills.py`
  - stage ordering and canonical skill availability
- `tests/test_skill_contracts.py`
  - frontmatter and skill contract expectations
- `tests/test_prompt_builder.py`
  - prompt builder output and visible skill path blocks

### Add a connector

Connectors have three distinct layers:

1. config and validation
2. inbound / outbound transport adaptation
3. optional background runtime lifecycle

For a simple connector, changing only one layer is usually not enough.

#### Core files to inspect first

- config defaults:
  - `src/deepscientist/config/models.py`
- config validation and live test behavior:
  - `src/deepscientist/config/service.py`
- connector profile support:
  - `src/deepscientist/connector/connector_profiles.py`
- inbound/outbound adaptation:
  - `src/deepscientist/bridges/base.py`
  - `src/deepscientist/bridges/connectors.py`
  - `src/deepscientist/bridges/builtins.py`
- channel delivery:
  - `src/deepscientist/channels/base.py`
  - `src/deepscientist/channels/builtins.py`
- daemon lifecycle:
  - `src/deepscientist/daemon/app.py`
- API endpoints:
  - `src/deepscientist/daemon/api/router.py`
  - `src/deepscientist/daemon/api/handlers.py`
- optional prompt fragment:
  - `src/prompts/connectors/<connector>.md`

#### Step-by-step connector checklist

1. Add default config in `src/deepscientist/config/models.py`.
   - If it is a system connector, add it to `SYSTEM_CONNECTOR_NAMES`.
   - Add its default payload under `default_connectors()`.
2. Add validation and config test behavior in `src/deepscientist/config/service.py`.
   - validate required tokens, ids, transport, and live probe behavior
3. Decide whether it is profileable.
   - If yes, add a spec in `src/deepscientist/connector/connector_profiles.py`
4. Add or extend a bridge in `src/deepscientist/bridges/connectors.py`.
   - subclass `BaseConnectorBridge`
   - implement inbound parsing and outbound formatting / delivery as needed
5. Register the bridge in `src/deepscientist/bridges/builtins.py`.
6. Register a channel in `src/deepscientist/channels/builtins.py`.
   - use `GenericRelayChannel` when the standard relay flow is enough
   - add a dedicated channel class only when the connector needs special outbound behavior
7. If the connector needs a long-running runtime such as polling, gateway, QR session, or long connection:
   - add the service class under `src/deepscientist/channels/`
   - add daemon state fields in `DaemonApp.__init__`
   - wire startup in `DaemonApp._start_background_connectors()`
   - wire shutdown in `DaemonApp._stop_background_connectors()`
8. If the connector needs custom web/API flows beyond the generic inbound route:
   - update `src/deepscientist/daemon/api/router.py`
   - update `src/deepscientist/daemon/api/handlers.py`
9. If the connector needs connector-specific prompt behavior:
   - add `src/prompts/connectors/<connector>.md`
   - the prompt builder will load it automatically when the connector is active or bound
10. Add user docs if it is a public connector.

#### Connector rules

1. Prefer the generic bridge/channel model. Do not special-case a connector inside unrelated quest logic.
2. Keep transport adaptation in bridges and delivery/runtime behavior in channels.
3. Do not add a connector-specific public MCP namespace.
4. If the connector is public, keep route and status behavior consistent with the existing `/api/connectors/...` surface.
5. If it is only a relay connector, try `GenericRelayChannel` first before writing a bespoke channel class.

#### Minimum test checklist

- `tests/test_connector_config_validation.py`
  - config shape and required fields
- `tests/test_connector_bridges.py`
  - inbound parse and outbound formatting
- connector-specific tests such as:
  - `tests/test_telegram_connector.py`
  - `tests/test_weixin_connector.py`
  - `tests/test_qq_connector.py`
  - `tests/test_whatsapp_local_session.py`
  - or a new connector-specific test file
- `tests/test_daemon_api.py`
  - if new routes, status payloads, or connector availability behavior changed

### Quick extension map

Use this when you only need the shortest file-level reminder:

- new MCP tool:
  - `src/deepscientist/mcp/server.py`
  - maybe `src/deepscientist/runners/codex.py`
  - tests: `test_mcp_servers.py`
- new skill:
  - `src/skills/<skill_id>/SKILL.md`
  - maybe `src/deepscientist/skills/registry.py`
  - maybe `src/deepscientist/prompts/builder.py`
  - tests: `test_stage_skills.py`, `test_skill_contracts.py`, `test_prompt_builder.py`
- new connector:
  - `src/deepscientist/config/models.py`
  - `src/deepscientist/config/service.py`
  - maybe `src/deepscientist/connector/connector_profiles.py`
  - `src/deepscientist/bridges/*`
  - `src/deepscientist/channels/*`
  - maybe `src/deepscientist/daemon/app.py`
  - maybe `src/prompts/connectors/<connector>.md`
  - tests: connector validation + bridge + daemon/API coverage

## Documentation Rules

When behavior changes:

- update user docs in `docs/en/` and `docs/zh/` if the user-facing workflow changed
- update `90_ARCHITECTURE.md` if subsystem structure or ownership changed
- update this file if development or registration workflow changed

## Repository Hygiene

- do not commit `node_modules/`, build output, caches, or local secrets
- do not commit workstation-specific absolute paths
- keep changes coherent and narrowly scoped
- prefer current runtime behavior and tests over stale comments or deleted historical docs
