# Admin Ops Knowledge Base

Use this knowledge base as the compact system map for administrator diagnosis and repair work.

## Source Of Truth Paths

- repository overview: `README.md`
- docs index: `docs/en/README.md`, `docs/zh/README.md`
- quick start and common FAQ: `docs/en/00_QUICK_START.md`, `docs/zh/00_QUICK_START.md`
- settings and runtime config: `docs/en/01_SETTINGS_REFERENCE.md`, `docs/zh/01_SETTINGS_REFERENCE.md`
- doctor and common startup/runtime failures: `docs/en/09_DOCTOR.md`, `docs/zh/09_DOCTOR.md`
- user-facing architecture: `docs/en/13_CORE_ARCHITECTURE_GUIDE.md`, `docs/zh/13_CORE_ARCHITECTURE_GUIDE.md`
- prompt / skills / MCP behavior: `docs/en/14_PROMPT_SKILLS_AND_MCP_GUIDE.md`, `docs/zh/14_PROMPT_SKILLS_AND_MCP_GUIDE.md`
- maintainer architecture: `docs/en/90_ARCHITECTURE.md`
- maintainer development guide: `docs/en/91_DEVELOPMENT.md`

## Runtime Code Paths

- CLI entry: `src/deepscientist/cli.py`
- npm / node launcher: `bin/ds.js`
- daemon app: `src/deepscientist/daemon/app.py`
- daemon API router: `src/deepscientist/daemon/api/router.py`
- daemon API handlers: `src/deepscientist/daemon/api/handlers.py`
- prompt builder: `src/deepscientist/prompts/builder.py`
- prompt sources: `src/prompts/system.md`, `src/prompts/system_copilot.md`, `src/prompts/contracts/`
- admin backend: `src/deepscientist/admin/`
- managed local tools: `src/deepscientist/runtime_tools/`
- settings control center UI: `src/ui/src/components/settings/SettingsPage.tsx`, `src/ui/src/components/settings/`
- admin copilot rail UI: `src/ui/src/components/settings/SettingsOpsRail.tsx`

## Runtime Directories

- DeepScientist home: `~/DeepScientist/`
- runtime: `~/DeepScientist/runtime/`
- config: `~/DeepScientist/config/`
- memory: `~/DeepScientist/memory/`
- quests: `~/DeepScientist/quests/`
- logs: `~/DeepScientist/logs/`
- cache: `~/DeepScientist/cache/`

## Quest Layout

- one quest = one Git repository
- key files: `quest.yaml`, `brief.md`, `plan.md`, `status.md`, `SUMMARY.md`
- key runtime dirs: `artifacts/`, `baselines/`, `experiments/`, `literature/`, `handoffs/`, `paper/`, `memory/`, `.ds/`

## Install And Checkout Paths

- the live session packet should provide absolute `local_repo_root`, launcher, Python runtime, web UI, and TUI paths
- treat that `local_repo_root` as the primary editable installation / checkout for this admin session unless runtime evidence proves a different deployed copy is active
- if local state is missing, drifted, or not trustworthy enough for diagnosis, you may compare against `https://github.com/ResearAI/DeepScientist`

## System Control Surface Map

Preferred settings-facing aliases live under `/api/system/*`. Legacy `/api/admin/*` routes remain as compatibility aliases for older automation and repair sessions.

- overview: preferred `/api/system/overview`; compatibility `/api/admin/overview`
- quests: preferred `/api/system/quests`, `/api/system/quests/:quest_id/summary`; compatibility `/api/admin/quests`, `/api/admin/quests/:quest_id/summary`
- runtime sessions: preferred `/api/system/runtime/sessions`; compatibility `/api/admin/runtime/sessions`
- logs: preferred `/api/system/logs/sources`, `/api/system/logs/tail`; compatibility `/api/admin/logs/sources`, `/api/admin/logs/tail`
- failures/errors: preferred `/api/system/failures`, `/api/system/errors`; compatibility `/api/admin/failures`, `/api/admin/errors`
- diagnostics/tasks: preferred `/api/system/doctor`, `/api/system/tasks*`, `/api/system/runtime-tools`; compatibility `/api/admin/doctor`, `/api/admin/tasks*`, `/api/admin/runtime-tools`
- controllers: preferred `/api/system/controllers*`; compatibility `/api/admin/controllers*`
- repairs: preferred `/api/system/repairs*`; compatibility `/api/admin/repairs*`
- hardware: preferred `/api/system/hardware`; compatibility `/api/admin/system/hardware`
- search/stats/issues: preferred `/api/system/search`, `/api/system/stats/summary`, `/api/system/issues/draft`; compatibility `/api/admin/search`, `/api/admin/stats/summary`, `/api/admin/issues/draft`

## Wider Daemon API Surface

If the repair goes beyond `/api/system/*`, the same daemon also exposes broader local APIs. Use `src/deepscientist/daemon/api/router.py` as the final authority.

- quest lifecycle: `/api/quests`, `/api/quest-id/next`, `/api/quests/:quest_id`, `/api/quests/:quest_id/settings`, `/api/quests/:quest_id/control`
- quest bindings and baselines: `/api/quests/:quest_id/bindings`, `/api/quests/:quest_id/baseline-binding`
- quest session and event stream: `/api/quests/:quest_id/session`, `/api/quests/:quest_id/events`, `/api/quests/:quest_id/workflow`
- quest layout and graph: `/api/quests/:quest_id/layout`, `/api/quests/:quest_id/graph`, `/api/quests/:quest_id/graph/svg`
- quest artifacts and traces: `/api/quests/:quest_id/artifacts`, `/api/quests/:quest_id/node-traces`, `/api/quests/:quest_id/stage-view`
- quest files and documents: `/api/quests/:quest_id/files/*`, `/api/quests/:quest_id/documents`, `/api/quests/:quest_id/documents/open`, `/api/quests/:quest_id/documents/assets`, `/api/quests/:quest_id/documents/asset`
- quest memory and explorer: `/api/quests/:quest_id/memory`, `/api/quests/:quest_id/explorer`
- quest chat and commands: `/api/quests/:quest_id/chat`, `/api/quests/:quest_id/chat/uploads`, `/api/quests/:quest_id/commands`
- quest runs and shell execution: `/api/quests/:quest_id/runs`, `/api/quests/:quest_id/bash/sessions*`, `/api/quests/:quest_id/terminal/sessions/*/attach`
- git and compare surfaces: `/api/quests/:quest_id/git/branches`, `/api/quests/:quest_id/git/canvas`, `/api/quests/:quest_id/git/log`, `/api/quests/:quest_id/git/compare`, `/api/quests/:quest_id/git/commit`, `/api/quests/:quest_id/git/diff-file`, `/api/quests/:quest_id/git/commit-file`
- config and registries: `/api/config/files`, `/api/config/:name`, `/api/baselines`, `/api/connectors`, `/api/connectors/availability`, `/api/connectors/weixin/login/qr/*`
- benchstore and setup: `/api/benchstore/entries*`
- literature and paper helpers: `/api/v1/arxiv/*`, `/api/v1/annotations/*`, `/api/v1/projects/:project_id/latex/*`

## Command Recipes

Map operator requests into these recipes before acting.

- `INSPECT <surface>`
  - start with `/api/system/overview`, `/api/system/hardware`, and the current `source_page`
  - if code paths are implicated, cite the most relevant files under `local_repo_root`
- `LOGS <source or symptom>`
  - use `/api/system/logs/sources` to choose a source, then `/api/system/logs/tail`
  - when the page context already names one source, prefer that source first and cite its file path when available
- `SEARCH <query>`
  - search repo code with `rg` under `local_repo_root`
  - search bounded quest/admin summaries with `/api/system/search`
  - return ranked hits with exact paths such as `src/ui/src/components/settings/...` or `src/deepscientist/...`
- `REPRO <bug or mismatch>`
  - name the page, route, inputs, and expected vs actual behavior first
  - prefer minimal local commands, minimal config changes, and the smallest quest or page scope that still reproduces the bug
- `PATCH <goal>`
  - identify exact files before editing
  - for settings/admin frontend work, check `src/ui/src/components/settings/`, `src/ui/src/lib/api/admin.ts`, `src/ui/src/lib/types/admin.ts`
  - for daemon/admin backend work, check `src/deepscientist/admin/`, `src/deepscientist/daemon/api/`, and `src/deepscientist/prompts/`
- `VERIFY <change or claim>`
  - list the commands or API reads to run, report pass/fail per check, and mention residual risk explicitly
- `ISSUE <summary>`
  - use `/api/system/issues/draft` as the base, then add repro steps, affected files, and evidence links/paths
- `PR <summary>`
  - prepare repo status, diff scope, changed-file list, test plan, PR title, and PR body
  - before any commit, push, compare publication, PR creation, or issue filing, ask the user for approval

## Common Triage Routes

- startup, config, runner, connector weirdness:
  - read `docs/en/09_DOCTOR.md` or `docs/zh/09_DOCTOR.md`
  - then inspect config through `docs/en/01_SETTINGS_REFERENCE.md` or `docs/zh/01_SETTINGS_REFERENCE.md`
- Codex profile, provider endpoint, API key, model mismatch:
  - read `docs/en/15_CODEX_PROVIDER_SETUP.md`
  - check local-model behavior with `docs/en/21_LOCAL_MODEL_BACKENDS_GUIDE.md`
- prompt / skill / MCP confusion:
  - read `docs/en/14_PROMPT_SKILLS_AND_MCP_GUIDE.md` or `docs/zh/14_PROMPT_SKILLS_AND_MCP_GUIDE.md`
- daemon, canvas, workspace, quest runtime confusion:
  - read `docs/en/06_RUNTIME_AND_CANVAS.md` or `docs/zh/06_RUNTIME_AND_CANVAS.md`
- connector-specific delivery/runtime failures:
  - read the connector guide in `docs/en/` or `docs/zh/`

## Admin Repair Ground Rules

- prefer daemon APIs, quest files, config files, runtime logs, and bounded `bash_exec(...)` inspection
- do not guess file layout when `AGENTS.md`, docs, or code already define it
- avoid direct mutation of undocumented `.ds/*` internals when a safer public path exists
- for runtime-shell work, use `bash_exec(...)`, not native shell tools
- every repair should leave a durable report under `artifacts/reports/admin/`
- you may prepare a comparison checkout with `git clone https://github.com/ResearAI/DeepScientist` when a clean upstream reference is operationally useful
- you may prepare local commits, PR drafts, or issue drafts, but always ask the user before running the exact clone / commit / publish / filing action
