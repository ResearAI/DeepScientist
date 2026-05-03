# 01 Settings Reference: Configure DeepScientist

This manual documents the current DeepScientist `Settings` surface and the YAML files it actually edits. The structure intentionally follows a PyTorch-style reference pattern: short summary, schema, parameters, defaults, allowed values, runtime effect, and practical notes.

If DeepScientist is already running, this should be your first stop. The intended path is:

1. start DeepScientist
2. open the web `Settings` page
3. use the structured UI first
4. edit raw YAML only when you are headless, automating setup, or doing bulk changes

Implementation sources:

- `src/ui/src/components/settings/settingsFormCatalog.ts`
- `src/ui/src/components/settings/connectorCatalog.ts`
- `src/ui/src/components/settings/RegistrySettingsForm.tsx`
- `src/deepscientist/config/models.py`
- `src/deepscientist/config/service.py`

## Overview

This guide works best if you use it in two passes:

1. first read the page-level sections in this document to find the right `Settings` page
2. then read the field reference only for the page you are actually using

If you try to read the entire file from top to bottom as one long schema, it will feel heavier than it needs to.

The `Settings` page writes directly to the following files:

| File | UI category | Purpose |
| --- | --- | --- |
| `~/DeepScientist/config/config.yaml` | Runtime | Main runtime config: home path, daemon, UI, logging, Git, skill sync, cloud, ACP |
| `~/DeepScientist/config/runners.yaml` | Models | Runner config for `codex` / `claude` / `kimi` / `opencode`: binary path, model defaults, permissions, sandbox, retries, env |
| `~/DeepScientist/config/connectors.yaml` | Connectors | QQ, Telegram, Discord, Slack, Feishu, WhatsApp, Lingzhu connector config |
| `~/DeepScientist/config/plugins.yaml` | Extensions | Plugin discovery, enable/disable overrides, trust policy |
| `~/DeepScientist/config/mcp_servers.yaml` | MCP | External MCP servers only; not built-in `memory`, `artifact`, or `bash_exec` |

Button semantics:

- `Save`: write the current structured form back to YAML.
- `Check` / `Validate`: local schema validation only.
- `Test`: run a lightweight readiness probe. The exact behavior depends on the file type and is described later in this document.

## Most Common Jobs After First Launch

If you are new to the `Settings` page, start from the task you actually want to complete:

| What you want to do | Open this page first |
| --- | --- |
| Change the default language, home path, daemon defaults, web port, or Git policy | `Runtime` |
| Switch the default runner or configure Claude / Kimi / OpenCode after launch | `Models` |
| Bind a chat platform or inspect connector state | `Connectors` |
| Reuse or publish baselines | `Baselines` |
| Enable and test DeepXiv | `DeepXiv` |
| Add plugins or plugin load paths | `Extensions` |
| Register external MCP servers | `MCP` |

Connector-specific setup guides:

- `docs/en/03_QQ_CONNECTOR_GUIDE.md`
- `docs/en/04_LINGZHU_CONNECTOR_GUIDE.md`
- `docs/en/10_WEIXIN_CONNECTOR_GUIDE.md`
- `docs/en/16_TELEGRAM_CONNECTOR_GUIDE.md`
- `docs/en/17_WHATSAPP_CONNECTOR_GUIDE.md`
- `docs/en/18_FEISHU_CONNECTOR_GUIDE.md`
- `docs/en/28_DISCORD_CONNECTOR_GUIDE.md`
- `docs/en/29_SLACK_CONNECTOR_GUIDE.md`

## Visual Tour Of The Core Settings Pages

The pages below cover the main configuration surfaces you should use after launch.

### Runtime

Route:

- `/settings/config`

This page edits:

- `~/DeepScientist/config/config.yaml`

Use this page when you need to change:

- home path, default locale, and default runner
- daemon policy, web binding, logging, Git, and skill sync defaults
- hardware prompt policy and cloud / ACP compatibility knobs

How to use it:

1. open the page
2. change only the fields related to the task you are doing right now
3. click `Save`
4. use `Check` or `Test` if you want confirmation before leaving

Good first tasks here:

- switch `default_locale`
- change the web port
- adjust `default_runner`
- review Git and logging defaults

Do not start here when:

- you are trying to bind one specific connector
- you are trying to configure one specific runner in detail
- you need runtime diagnostics rather than configuration

![Runtime settings page](../images/settings/settings-config-en.png)

### Models

Route:

- `/settings/runners`

This page edits:

- `~/DeepScientist/config/runners.yaml`

Use this page when you need to:

- switch the global default runner
- confirm which runner is currently active
- configure Codex / Claude Code / Kimi Code / OpenCode without editing `runners.yaml` by hand

How to use it:

1. decide which runner you want to use by default
2. enable only the runner you actually want active
3. fill the runner-specific path, config dir, model, and runtime knobs
4. click `Save`
5. click `Check` and then `Test`

Good first tasks here:

- enable Claude after `claude` already works in the terminal
- enable Kimi after `kimi` already works in the terminal
- reuse an existing OpenCode install

Do not start here when:

- the real problem is a connector delivery issue
- the real problem is that DeepScientist is unhealthy before any runner even starts

![Models settings page](../images/settings/settings-runners-en.png)

### Connectors

Route:

- `/settings/connector`

This page edits:

- `~/DeepScientist/config/connectors.yaml`

Use this page when you need to:

- choose which connector to configure next
- jump from the connector catalog into a specific platform page
- keep connector setup visual-first instead of opening `connectors.yaml` immediately

How to use it:

1. start from the catalog page
2. open one connector at a time
3. save that connector before sending real test traffic
4. only after the first real inbound message, expect discovered targets and runtime state to become useful

Do not start here when:

- you need system-wide diagnosis before touching any connector
- the runtime itself is not healthy enough to host connectors at all

![Connectors overview page](../images/settings/settings-connectors-overview-en.png)

### Baselines

Route:

- `/settings/baselines`

This page edits:

- the baseline registry under the DeepScientist home rather than one raw config file

Use this page when you need to:

- inspect reusable published baselines
- attach an existing baseline before launch
- publish a confirmed quest baseline into the shared registry

How to use it:

1. open this page before launch if you already have a reusable baseline
2. open it after a quest succeeds if you want to publish that baseline for future reuse
3. stay here for registry-level baseline work; go back to quest pages for quest-specific work

![Baselines settings page](../images/settings/settings-baselines-en.png)

### DeepXiv

Route:

- `/settings/deepxiv`

This page edits:

- the `literature.deepxiv` block in `~/DeepScientist/config/config.yaml`

Use this page when you need to:

- enable or disable DeepXiv
- configure the literature token and timeout defaults
- use the guided setup flow instead of editing `config.yaml` manually

How to use it:

1. open the page
2. start the guided setup flow if you do not already know the exact fields
3. save the token and defaults
4. test the route from the same page before relying on it in real work

![DeepXiv settings page](../images/settings/settings-deepxiv-en.png)

### Extensions

Route:

- `/settings/plugins`

This page edits:

- `~/DeepScientist/config/plugins.yaml`

Use this page when you need to:

- configure plugin discovery paths
- enable or disable optional local extensions
- adjust plugin trust policy

How to use it:

1. keep the default path if you are not actively using local plugins
2. add plugin paths only when you actually have plugins to load
3. treat this page as a plugin registry page, not a general runtime diagnosis page

![Extensions settings page](../images/settings/settings-plugins-en.png)

### MCP

Route:

- `/settings/mcp_servers`

This page edits:

- `~/DeepScientist/config/mcp_servers.yaml`

Use this page when you need to:

- register or edit external MCP servers
- review MCP connection settings without touching the built-in MCP namespaces
- validate external MCP integration before using it in quests

How to use it:

1. add one external MCP server at a time
2. keep built-in MCP expectations separate from external MCP setup
3. validate the external MCP server before using it in a real quest

![MCP settings page](../images/settings/settings-mcp-servers-en.png)

## How To Read The Rest Of This Document

From this point onward, the file switches into field-level reference mode.

The fastest way to use the remaining sections is:

1. find the page you actually need
2. skim its screenshot and operational notes above
3. jump to the field reference below only for the fields you are about to change

## `config.yaml`

### Summary

`config.yaml` is the main runtime configuration file. It controls the DeepScientist home directory, default locale, daemon policy, Web/TUI binding, logging, Git behavior, skill mirroring, and optional cloud / ACP compatibility settings.

### Schema

```yaml
home: ~/DeepScientist
default_runner: codex
default_locale: en-US # or zh-CN, initialized from the browser on first web launch
daemon:
  session_restore_on_start: true
  max_concurrent_quests: 1
  ack_timeout_ms: 1000
ui:
  host: 0.0.0.0
  port: 20999
  auth_enabled: false
  auto_open_browser: true
  default_mode: both
logging:
  level: info
  console: true
  keep_days: 30
git:
  auto_checkpoint: true
  auto_push: false
  default_remote: origin
  graph_formats: [svg, png, json]
skills:
  sync_global_on_init: true
  sync_quest_on_create: true
  sync_quest_on_open: true
bootstrap:
  codex_ready: false
  codex_last_checked_at: null
  codex_last_result: {}
  locale_source: browser
  locale_initialized_from_browser: true
  locale_initialized_at: 2026-03-18T00:00:00+00:00
  locale_initialized_browser_locale: en-US
connectors:
  auto_ack: true
  milestone_push: true
  direct_chat_enabled: true
cloud:
  enabled: false
  base_url: https://deepscientist.cc
  token: null
  token_env: DEEPSCIENTIST_TOKEN
  verify_token_on_start: false
  sync_mode: disabled
acp:
  compatibility_profile: deepscientist-acp-compat/v1
  events_transport: rest-poll
  sdk_bridge_enabled: false
  sdk_module: acp
```

### Core identity

**`home`**

- Type: `string`
- Default: the installed DeepScientist home, usually `~/DeepScientist`
- UI label: `Home path`
- Meaning: root directory for config, projects, memory, plugins, logs, and cache.
- When to change: only when you intentionally installed DeepScientist somewhere else.
- Notes: this is not a single project path; it is the runtime root.

**`default_runner`**

- Type: `string`
- Default: `codex`
- Allowed values: `codex`, `claude`, `kimi`, `opencode`
- UI label: `Default runner`
- Meaning: runner used when a project does not override it.
- Notes: new quests inherit this default; existing quests may override it in project settings. Switch only to a runner that is enabled and already passes `ds doctor`.

**`default_locale`**

- Type: `string`
- Default: initialized from the browser language on the first web launch, then persisted as `zh-CN` or `en-US`
- Allowed values: `zh-CN`, `en-US`
- UI label: `Default locale`
- Meaning: default language preference used by prompts and runtime copy.
- Notes: after the first browser-driven initialization, changing this field in `Settings` makes it a manual override and DeepScientist will not auto-follow the browser again.

### Daemon policy

**`daemon.session_restore_on_start`**

- Type: `boolean`
- Default: `true`
- UI label: `Restore sessions on start`
- Meaning: restore previous project sessions when the daemon starts.

**`daemon.max_concurrent_quests`**

- Type: `number`
- Default: `1`
- UI label: `Max concurrent projects`
- Meaning: upper bound on how many projects may run at the same time.
- Recommendation: keep `1` unless you intentionally want parallel project execution.

**`daemon.ack_timeout_ms`**

- Type: `number`
- Default: `1000`
- UI label: `Ack timeout (ms)`
- Meaning: timeout budget for short acknowledgments and lightweight connector feedback.

### Web / TUI runtime

**`ui.host`**

- Type: `string`
- Default: `0.0.0.0`
- UI label: `UI host`
- Meaning: bind address for the local web UI server.
- Common values:
  - `0.0.0.0`: LAN, container, reverse-proxy friendly
  - `127.0.0.1`: local-only

**`ui.port`**

- Type: `number`
- Default: `20999`
- UI label: `UI port`
- Meaning: listening port for the local UI server.

**`ui.auth_enabled`**

- Type: `boolean`
- Default: `false`
- UI label: `Require local password`
- Meaning: require a locally generated 16-character browser password for the web workspace and all `/api/*` routes.
- Behavior:
  - `true`: `ds` prints the generated password in the terminal, the browser prompts for the password if no valid local login exists, and successful login persists in the browser.
  - `false`: disable the local password gate and keep the plain local URL behavior.
- CLI override: `ds --auth true` or `ds --auth false`

**`ui.auto_open_browser`**

- Type: `boolean`
- Default: `true`
- UI label: `Auto-open browser`
- Meaning: open the browser automatically when the UI starts.

**`ui.default_mode`**

- Type: `string`
- Default: `both`
- Allowed values: `both`, `web`, `tui`
- UI label: `Default start mode`
- Meaning: preferred startup surface when launching DeepScientist.

### TUI debug launch switches

TUI debug is not a persistent config field. It is a per-launch diagnostic switch for inspecting the current TUI surface, input route, Web analog, and render summary.

Start with:

```bash
ds --tui --debug
ds --tui --debug --debug-log /tmp/deepscientist_tui_debug.jsonl
```

Environment variables:

- `TUI_DEBUG=1`
- `DEEPSCIENTIST_TUI_DEBUG=1`
- `TUI_DEBUG_LOG=/tmp/deepscientist_tui_debug.jsonl`
- `DEEPSCIENTIST_TUI_DEBUG_LOG=/tmp/deepscientist_tui_debug.jsonl`

Default log path:

```text
/tmp/deepscientist_tui_debug.jsonl
```

Safety requirements:

- Config editor buffers and password/secret/token fields are redacted in debug JSONL.
- Debug JSONL can be attached to issue reports or regression notes, but search it for real tokens first.
- Terminal recordings, tmux logs, and `script` transcripts capture the real screen; they are outside the JSONL redaction boundary.
- Web does not yet have an equivalent `?debug=1` inspector; TUI currently provides only the `web_analog` mapping.

### Logging

**`logging.level`**

- Type: `string`
- Default: `info`
- Allowed values: `debug`, `info`, `warning`, `error`
- UI label: `Log level`
- Meaning: daemon and runner log verbosity.

**`logging.console`**

- Type: `boolean`
- Default: `true`
- UI label: `Log to console`
- Meaning: mirror logs to the active terminal in addition to file logs.

**`logging.keep_days`**

- Type: `number`
- Default: `30`
- UI label: `Retention days`
- Meaning: log retention window before cleanup.

### Git behavior

**`git.auto_checkpoint`**

- Type: `boolean`
- Default: `true`
- UI label: `Auto-checkpoint`
- Meaning: create Git checkpoints automatically during project progress.

**`git.auto_push`**

- Type: `boolean`
- Default: `false`
- UI label: `Auto-push`
- Meaning: push checkpoint commits to the default remote automatically.
- Risk: once enabled, intermediate research artifacts may leave the machine earlier.

**`git.default_remote`**

- Type: `string`
- Default: `origin`
- UI label: `Default remote`
- Meaning: remote name used for auto-push and export.

**`git.graph_formats`**

- Type: `list[string]`
- Default: `["svg", "png", "json"]`
- UI label: `Graph export formats`
- Meaning: formats generated for graph export.

### Reports & visuals

Palette selection is no longer exposed in `Settings` or `config.yaml`.

- Chart and figure color discipline now lives in:
  - `src/prompts/system.md`
  - `src/skills/experiment/SKILL.md`
  - `src/skills/analysis-campaign/SKILL.md`
  - `src/skills/write/SKILL.md`
- DeepScientist uses a fixed Morandi palette guide instead of per-install color settings.
- The durable reference page is `docs/en/08_FIGURE_STYLE_GUIDE.md`.
- Edit the prompt / skill contract if you need to change the default visual language.

### Skill synchronization

**`skills.sync_global_on_init`**

- Type: `boolean`
- Default: `true`
- UI label: `Sync global skills on init`
- Meaning: install project-provided skills into the global runner home during initialization.

**`skills.sync_quest_on_create`**

- Type: `boolean`
- Default: `true`
- UI label: `Sync project skills on create`
- Meaning: mirror skills into project-local runner homes when a project is created.
- Prompt note: this also seeds the managed quest-local prompt mirror under `.codex/prompts/`.

**`skills.sync_quest_on_open`**

- Type: `boolean`
- Default: `true`
- UI label: `Sync project skills on open`
- Meaning: refresh project-local skill mirrors when an existing project is opened.
- Prompt note: this refreshes quest-local skill and prompt mirrors for quests discovered under the configured DeepScientist home.

Managed prompt behavior:

- DeepScientist now treats `.codex/prompts/` as a managed active prompt tree rather than as a permanent hand-edited override.
- Before each real runner turn, it compares the active quest-local prompt tree against the current repository `src/prompts/` tree and automatically repairs drift.
- If the active prompt tree differs, the previous tree is backed up under `.codex/prompt_versions/<backup_id>/` before the new active copy is written.
- This run-time prompt sync happens against the actual quest root used for the turn, so it still works even when a quest lives outside the default `home/quests` path.
- Runtime override: `ds daemon --prompt-version latest` uses the managed active tree, while `ds daemon --prompt-version <official_version>` runs that daemon session against the newest backup recorded for that formal DeepScientist version.
- If you need one exact historical backup rather than the newest backup for that version, you may still pass the exact backup directory name from `.codex/prompt_versions/`.
- The same override also exists for one-off CLI runs: `ds run --prompt-version <official_version> ...`.

Managed auto-continue behavior:

- `workspace_mode = copilot`
  - after the current requested unit, DeepScientist normally parks and waits for the next user message or `/resume`
- `workspace_mode = autonomous`
  - if no real external long-running task exists yet, DeepScientist keeps using the next turns to prepare, launch, or durably route that real task
  - once a real external long-running task exists, auto-continue becomes low-frequency monitoring, roughly every `240` seconds by default
- Auto-continue prompts now also carry a compact resume spine: latest user message, latest assistant checkpoint, latest run summary, recent memory cues, and current `bash_exec` state

### Connector policy

These fields are global connector behaviors, not per-platform credentials.

**`connectors.auto_ack`**

- Type: `boolean`
- Default: `true`
- UI label: `Auto-ack incoming messages`
- Meaning: send a short acknowledgment before the full project response completes.

**`connectors.milestone_push`**

- Type: `boolean`
- Default: `true`
- UI label: `Push milestones`
- Meaning: allow milestone and decision updates to fan out through enabled connectors.

**`connectors.direct_chat_enabled`**

- Type: `boolean`
- Default: `true`
- UI label: `Enable direct chat`
- Meaning: allow connectors to continue projects from direct messages.

### Cloud link

This block is optional and not part of the local-first core path.

**`cloud.enabled`**

- Type: `boolean`
- Default: `false`
- UI label: `Enable cloud link`
- Meaning: turn on the optional cloud-link path.

**`cloud.base_url`**

- Type: `string`
- Default: `https://deepscientist.cc`
- UI label: `Cloud base URL`
- Meaning: base URL of the cloud endpoint.

**`cloud.token`**

- Type: `string | null`
- Default: `null`
- UI label: `Cloud token`
- Meaning: direct token value for cloud authentication.

**`cloud.token_env`**

- Type: `string`
- Default: `DEEPSCIENTIST_TOKEN`
- UI label: `Cloud token env var`
- Meaning: environment variable name used to source the token.

**`cloud.verify_token_on_start`**

- Type: `boolean`
- Default: `false`
- UI label: `Verify token on start`
- Meaning: fail fast if the configured cloud token is invalid.

**`cloud.sync_mode`**

- Type: `string`
- Default: `disabled`
- Allowed values: `disabled`, `pull`, `push`, `bidirectional`
- UI label: `Cloud sync mode`
- Meaning: overall cloud synchronization direction.

### ACP bridge

These settings are compatibility knobs for ACP-style external consumers.

**`acp.compatibility_profile`**

- Type: `string`
- Default: `deepscientist-acp-compat/v1`
- UI label: `Compatibility profile`
- Meaning: named ACP compatibility profile exposed to external consumers.

**`acp.events_transport`**

- Type: `string`
- Default: `rest-poll`
- Allowed values: `rest-poll`, `sse`
- UI label: `Events transport`
- Meaning: transport used for ACP-style event delivery.

**`acp.sdk_bridge_enabled`**

- Type: `boolean`
- Default: `false`
- UI label: `Enable SDK bridge`
- Meaning: allow the runtime to bridge through an ACP SDK module.

**`acp.sdk_module`**

- Type: `string`
- Default: `acp`
- UI label: `SDK module`
- Meaning: Python module name imported when ACP SDK bridging is enabled.

## `runners.yaml`

### Summary

`runners.yaml` defines which CLI runner DeepScientist can launch, which model defaults it should use, how retries behave, and which runner-specific flags should be passed through.

Current built-in runners:

- `codex`
  - OpenAI Codex CLI path, including Codex-compatible provider profiles
- `claude`
  - Claude Code CLI path, including Anthropic or compatible gateway setups that already work in Claude Code
- `kimi`
  - Official Kimi Code CLI path, including login state and config already working in `~/.kimi`
- `opencode`
  - OpenCode CLI path, including provider/model configurations managed directly by OpenCode

The Settings page maps DeepScientist to an already-working CLI runner. Gemini, Ollama, MiniMax, GLM, Bailian, and other providers still need to be configured in the corresponding CLI first:

- Codex provider / profile: see [15 Codex Provider Setup](./15_CODEX_PROVIDER_SETUP.md)
- Claude Code / Anthropic-compatible / Ollama: see [24 Claude Code Setup](./24_CLAUDE_CODE_PROVIDER_SETUP.md)
- OpenCode / Gemini / Ollama: see [25 OpenCode Setup](./25_OPENCODE_PROVIDER_SETUP.md)
- vLLM, Ollama, SGLang, and local backend overview: see [21 Local Model Backends Guide](./21_LOCAL_MODEL_BACKENDS_GUIDE.md)

Recommended validation order:

1. make the underlying CLI work first, such as `codex exec ...`, `claude -p ...`, or `opencode run ...`
2. fill `binary`, `config_dir`, `profile` / `model`, and `env` in Settings
3. click `Test` or run `ds doctor --runner <name>`
4. only then start a real quest

### Schema

```yaml
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: ""
  model: inherit
  model_reasoning_effort: xhigh
  approval_policy: never
  sandbox_mode: danger-full-access
  retry_on_failure: true
  retry_max_attempts: 7
  retry_initial_backoff_sec: 10.0
  retry_backoff_multiplier: 6.0
  retry_max_backoff_sec: 1800.0
  mcp_tool_timeout_sec: 172800
  env: {}
claude:
  enabled: false
  binary: claude
  config_dir: ~/.claude
  model: inherit
  permission_mode: bypassPermissions
  mcp_timeout_ms: 172800000
  mcp_tool_timeout_ms: 172800000
  retry_on_failure: true
  retry_max_attempts: 4
  retry_initial_backoff_sec: 10.0
  retry_backoff_multiplier: 4.0
  retry_max_backoff_sec: 600.0
  env: {}
  status: supported
kimi:
  enabled: false
  binary: kimi
  config_dir: ~/.kimi
  model: inherit
  agent: ""
  thinking: false
  yolo: true
  mcp_tool_timeout_ms: 172800000
  retry_on_failure: true
  retry_max_attempts: 4
  retry_initial_backoff_sec: 10.0
  retry_backoff_multiplier: 4.0
  retry_max_backoff_sec: 600.0
  env: {}
  status: supported
opencode:
  enabled: false
  binary: opencode
  config_dir: ~/.config/opencode
  model: inherit
  default_agent: ""
  variant: ""
  mcp_timeout_ms: 172800000
  retry_on_failure: true
  retry_max_attempts: 4
  retry_initial_backoff_sec: 10.0
  retry_backoff_multiplier: 4.0
  retry_max_backoff_sec: 600.0
  env: {}
  status: supported
```

### Editable fields

**`enabled`**

- Type: `boolean`
- UI label: `Enabled`
- Meaning: whether the runner can be selected and executed.
- Practical rule: enable only the runners whose CLI binary and auth path already work on this machine.

**`binary`**

- Type: `string`
- UI label: `Binary`
- Meaning: command name or absolute path used to launch the runner.
- Defaults:
  - `codex -> codex`
  - `claude -> claude`
  - `opencode -> opencode`
- `Test` behavior: checks whether the binary is available on `PATH` or at the configured path.

**`config_dir`**

- Type: `string`
- UI label: `Config directory`
- Meaning: global runner home used for auth and global settings.
- Defaults:
  - `codex -> ~/.codex`
  - `claude -> ~/.claude`
  - `opencode -> ~/.config/opencode`

**`profile`**

- Type: `string`
- UI label: `Codex profile`
- Runners: `codex`
- Meaning: optional Codex profile passed as `codex --profile <name>`.
- Use this when Codex itself is already configured for a provider-backed profile.

**`model`**

- Type: `string`
- UI label: `Default model`
- Meaning: default runner model when a quest or request does not override it.
- Default: `inherit` for all four runners.
- Recommended rule:
  - keep `inherit` when the CLI should decide the provider/model itself
  - set a fixed model only when you want DeepScientist to override every turn

**`model_reasoning_effort`**

- Type: `string`
- UI label: `Reasoning effort`
- Runners: `codex`
- Meaning: default Codex reasoning effort.
- Allowed values: `""`, `minimal`, `low`, `medium`, `high`, `xhigh`

**`approval_policy`**

- Type: `string`
- UI label: `Approval policy`
- Runners: `codex`
- Meaning: Codex approval behavior for privileged actions.
- Allowed values: `never`, `on-failure`, `on-request`, `untrusted`

**`sandbox_mode`**

- Type: `string`
- UI label: `Sandbox mode`
- Runners: `codex`
- Meaning: Codex filesystem / process sandbox mode.
- Allowed values: `read-only`, `workspace-write`, `danger-full-access`

**`permission_mode`**

- Type: `string`
- UI label: `Permission mode`
- Runners: `claude`
- Meaning: Claude Code permission mode passed through as `--permission-mode`.
- Common values: `default`, `bypassPermissions`, `dontAsk`, `acceptEdits`, `delegate`, `plan`
- Recommended local automation default: `bypassPermissions`

**`mcp_timeout_ms`**

- Type: `number`
- Runners: `claude`, `opencode`
- Meaning:
  - `claude`: MCP server startup timeout forwarded as `MCP_TIMEOUT`
  - `opencode`: timeout for fetching tools from each MCP server during startup
- Note: OpenCode's `mcp_timeout_ms` is not tool execution timeout.

**`mcp_tool_timeout_ms`**

- Type: `number`
- Runners: `claude`, `kimi`
- Meaning:
  - `claude`: per-tool MCP timeout forwarded as `MCP_TOOL_TIMEOUT`
  - `kimi`: MCP tool execution timeout written to `.kimi/config.toml` as `mcp.client.tool_call_timeout_ms`

**`agent`**

- Type: `string`
- UI label: `Kimi agent`
- Runners: `kimi`
- Meaning: optional Kimi agent name passed through as `kimi --agent <name>`.
- Leave empty unless the same agent profile already works in direct Kimi CLI usage.

**`thinking`**

- Type: `boolean`
- UI label: `Thinking mode`
- Runners: `kimi`
- Meaning: whether DeepScientist should pass `--thinking` to Kimi by default.

**`yolo`**

- Type: `boolean`
- UI label: `Yolo mode`
- Runners: `kimi`
- Meaning: whether DeepScientist should pass `--yolo` so Kimi does not stop for interactive approval prompts.
- Recommended unattended local automation default: `true`

**`default_agent`**

- Type: `string`
- UI label: `Default agent`
- Runners: `opencode`
- Meaning: optional OpenCode agent name passed through as `opencode run --agent <name>`.
- Leave empty unless the same agent name already works in direct OpenCode CLI usage.

**`variant`**

- Type: `string`
- UI label: `Variant`
- Runners: `opencode`
- Meaning: optional OpenCode provider-specific variant passed through as `--variant`.
- Use only when your OpenCode provider documents that flag.

**`env`**

- Type: `mapping<string, string>`
- UI label: `Environment variables`
- Meaning: extra environment variables injected only for this runner.
- Common examples:
  - Codex: `OPENAI_API_KEY`, `OPENAI_BASE_URL`
  - Claude: `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS`
  - Kimi: usually empty unless your local Kimi CLI path requires extra environment variables
  - OpenCode: provider-specific environment variables only if your OpenCode provider setup requires them

**`retry_on_failure` / `retry_max_attempts` / `retry_initial_backoff_sec` / `retry_backoff_multiplier` / `retry_max_backoff_sec`**

- Type: `boolean` / `number`
- Meaning: automatic turn retry policy for the runner.
- Defaults:
  - `codex`: more aggressive retry ladder
  - `claude` / `kimi` / `opencode`: shorter ladder

**`mcp_tool_timeout_sec`**

- Type: `number`
- Runners: `codex`
- Meaning: maximum MCP tool wait time, mainly for long `bash_exec` flows.

**`status`**

- Type: `string`
- Meaning: operator-facing note.
- Current practical meaning:
  - `codex`, `claude`, `kimi`, `opencode`: available built-in paths

### Practical guidance

- Use the runner that already works on your machine and matches the provider path you want.
- Use `claude` when Claude Code already works directly on the machine and you want Anthropic / Claude-native execution.
- Use `kimi` when the official Kimi Code CLI already works directly on the machine and you want a separate Moonshot-native runner path.
- Use `opencode` when your model/provider setup already works best through OpenCode.
- `default_runner` can now be switched away from `codex` safely if the target runner is enabled and passes `ds doctor`.
- New quests follow `config.default_runner`.
- Existing quests can override the runner in project settings.
- Do not lower `mcp_tool_timeout_sec` casually if your workflow uses long-running `bash_exec` sessions.
- For Kimi, the important timeout is `mcp_tool_timeout_ms`, because the upstream default is much shorter than the long-running `bash_exec` waits DeepScientist often needs.
- For Claude, the practical execution cap is already large by default; the more common issue is MCP startup timeout, handled by `mcp_timeout_ms`.
- For OpenCode, `mcp_timeout_ms` only affects MCP tool discovery / startup, not the execution time of one MCP call.


## `connectors.yaml`

### Summary

`connectors.yaml` manages connector enablement, transport, credentials, access control, and top-level routing policy for QQ, Telegram, Discord, Slack, Feishu / Lark, and WhatsApp.

Current design rules:

- prefer no-public-callback transports
- keep webhook / relay fields only as legacy or fallback paths
- treat connectors as alternate project control surfaces, not disconnected notification bots

### Top-level routing

**`_routing.primary_connector`**

- Type: `string | null`
- Default: `null`
- Meaning: preferred connector used by primary-only delivery policies.

**`_routing.artifact_delivery_policy`**

- Type: `string`
- Default: `fanout_all`
- Allowed values: `fanout_all`, `primary_only`, `primary_plus_local`
- Meaning: how `artifact` interaction messages are distributed across connectors.

### Common access-control fields

These fields appear across multiple connectors:

**`dm_policy`**

- Type: `string`
- Typical values: `pairing`, `allowlist`, `open`, `disabled`
- Meaning: whether direct messages auto-pair, require allowlists, or stay disabled.

**`allow_from`**

- Type: `list[string]`
- Meaning: direct-message sender allowlist.

**`group_policy`**

- Type: `string`
- Typical values: `allowlist`, `open`, `disabled`
- Meaning: group / channel access policy.

**`group_allow_from`**

- Type: `list[string]`
- Meaning: sender allowlist within groups.

**`groups`**

- Type: `list[string]`
- Meaning: allowlisted target group or channel ids.

**`auto_bind_dm_to_active_quest`**

- Type: `boolean`
- Default: usually `true`
- Meaning: direct messages automatically follow the current active project.

### `telegram`

Summary: best for direct bot chat; prefer `polling` over public webhooks.

Recommended path:

- `enabled: true`
- `transport: polling`
- provide `bot_token`

Primary fields:

**`transport`**

- Type: `string`
- Default: `polling`
- Allowed values: `polling`, `legacy_webhook`, `relay`

**`bot_name`**

- Type: `string`
- Default: `DeepScientist`

**`bot_token`**

- Type: `string | null`
- Meaning: Telegram Bot API token.
- How to get it: BotFather.
- File-only companion: `bot_token_env`.

**`command_prefix`**

- Type: `string`
- Default: `/`

**`require_mention_in_groups`**

- Type: `boolean`
- Default: `true`

Legacy / relay fields:

- `webhook_secret`
- `public_callback_url`
- `relay_url`
- `relay_auth_token`

### `discord`

Summary: prefer `gateway`; public interaction callbacks are not the primary path.

Primary fields:

**`transport`**

- Type: `string`
- Default: `gateway`
- Allowed values: `gateway`, `legacy_interactions`, `relay`

**`bot_token`**

- Type: `string | null`
- File-only companion: `bot_token_env`

**`application_id`**

- Type: `string | null`
- Meaning: application id used for richer routing and future slash-command support.

**`guild_allowlist`**

- Type: `list[string]`
- Meaning: allowlisted guild ids.

**`require_mention_in_groups`**

- Type: `boolean`
- Default: `true`

Legacy fields:

- `public_key`
- `public_interactions_url`
- `relay_url`
- `relay_auth_token`

### `slack`

Summary: prefer `socket_mode`; this is the main no-callback route.

Primary fields:

**`transport`**

- Type: `string`
- Default: `socket_mode`
- Allowed values: `socket_mode`, `legacy_events_api`, `relay`

**`bot_token`**

- Type: `string | null`
- Meaning: Bot User OAuth Token.
- File-only companion: `bot_token_env`

**`app_token`**

- Type: `string | null`
- Meaning: App-Level token required by Socket Mode.
- File-only companion: `app_token_env`

**`bot_user_id`**

- Type: `string | null`
- Meaning: optional bot user id used for mention filtering or routing.

**`command_prefix`**

- Type: `string`
- Default: `/`

**`require_mention_in_groups`**

- Type: `boolean`
- Default: `true`

Legacy fields:

- `signing_secret`
- `public_callback_url`
- `relay_url`
- `relay_auth_token`

### `feishu`

Summary: prefer `long_connection`; avoid public event callbacks when possible.

Primary fields:

**`transport`**

- Type: `string`
- Default: `long_connection`
- Allowed values: `long_connection`, `legacy_webhook`, `relay`

**`app_id`**

- Type: `string | null`

**`app_secret`**

- Type: `string | null`
- File-only companion: `app_secret_env`

**`api_base_url`**

- Type: `string`
- Default: `https://open.feishu.cn`

**`require_mention_in_groups`**

- Type: `boolean`
- Default: `true`

Legacy fields:

- `verification_token`
- `encrypt_key`
- `public_callback_url`
- `relay_url`
- `relay_auth_token`

### `whatsapp`

Summary: the design target is `local_session`, not Meta Cloud webhook-first operation.

Primary fields:

**`transport`**

- Type: `string`
- Default: `local_session`
- Allowed values: `local_session`, `legacy_meta_cloud`, `relay`

**`auth_method`**

- Type: `string`
- Default: `qr_browser`
- Allowed values: `qr_browser`, `pairing_code`, `qr_terminal`

**`session_dir`**

- Type: `string`
- Default: `~/.deepscientist/connectors/whatsapp`

**`command_prefix`**

- Type: `string`
- Default: `/`

Legacy Meta Cloud fields:

- `provider`
- `access_token`
- `phone_number_id`
- `business_account_id`
- `verify_token`
- `api_base_url`
- `api_version`
- `public_callback_url`
- `relay_url`
- `relay_auth_token`

File-level companions:

- `access_token_env`
- `verify_token_env`

### `qq`

Summary: QQ is first-class in DeepScientist. The primary path is fixed `gateway_direct`, with no public callback URL required.

Quick start: see [QQ Connector Guide](./03_QQ_CONNECTOR_GUIDE.md).

Recommended path:

- `enabled: true`
- `transport: gateway_direct`
- fill `app_id` and `app_secret`
- save first
- ask the user to send one private QQ message to the bot
- let the runtime auto-detect and persist `main_chat_id`

Primary fields:

**`transport`**

- Type: `string`
- Default: `gateway_direct`
- UI state: read-only
- Meaning: fixed built-in QQ gateway direct mode.

**`bot_name`**

- Type: `string`
- Default: `DeepScientist`

**`app_id`**

- Type: `string | null`
- Meaning: Tencent QQ bot app id.

**`app_secret`**

- Type: `string | null`
- Meaning: used for QQ access-token exchange and direct API delivery.
- File-only companion: `app_secret_env`

**`main_chat_id`**

- Type: `string | null`
- UI label: `Detected OpenID`
- UI state: read-only
- Meaning: auto-filled `openid` or `group_openid` discovered from the first inbound QQ message.
- Important: this is runtime-discovered data, not a field you should normally type manually.

**`require_at_in_groups`**

- Type: `boolean`
- Default: `true`

**`gateway_restart_on_config_change`**

- Type: `boolean`
- Default: `true`

**`command_prefix`**

- Type: `string`
- Default: `/`

**`auto_bind_dm_to_active_quest`**

- Type: `boolean`
- Default: `true`

### QQ milestone media policy

The current recommended QQ policy is text-first.
Auto-media should stay rare and milestone-bound:

- main experiment summary PNG: usually `on`
- aggregated analysis summary PNG: usually `on`
- per-slice PNG: usually `off`
- final paper PDF: usually `on`
- experimental file upload path: usually `off`

These settings exist to keep QQ readable and non-spammy.
Do not treat QQ as a file browser by default.

**`auto_send_main_experiment_png`**

- Type: `boolean`
- Default: `true`
- Meaning: allow one milestone summary PNG after a real main experiment finishes.

**`auto_send_analysis_summary_png`**

- Type: `boolean`
- Default: `true`
- Meaning: allow one aggregated analysis-campaign summary PNG at a meaningful campaign milestone.

**`auto_send_slice_png`**

- Type: `boolean`
- Default: `false`
- Meaning: allow per-slice analysis images to auto-send.
- Recommendation: keep this off unless you explicitly want slice-level pushes.

**`auto_send_paper_pdf`**

- Type: `boolean`
- Default: `true`
- Meaning: allow the final paper PDF to be sent once when the bundle is durably ready.

**`enable_file_upload_experimental`**

- Type: `boolean`
- Default: `false`
- Meaning: enable the experimental QQ media/file upload path.
- Recommendation: keep this off unless you are explicitly testing QQ upload support.

## `plugins.yaml`

### Summary

`plugins.yaml` controls plugin discovery and trust policy. It does not store plugin runtime state.

### Schema

```yaml
load_paths:
  - ~/DeepScientist/plugins
enabled: []
disabled: []
allow_unsigned: false
```

### Parameters

**`load_paths`**

- Type: `list[string]`
- Default: `[~/DeepScientist/plugins]`
- UI label: `Load paths`
- Meaning: directories scanned for plugin bundles.

**`enabled`**

- Type: `list[string]`
- Default: `[]`
- UI label: `Force-enable plugin ids`
- Meaning: explicit plugin ids to enable.

**`disabled`**

- Type: `list[string]`
- Default: `[]`
- UI label: `Force-disable plugin ids`
- Meaning: plugin ids that should stay disabled even if discovered.

**`allow_unsigned`**

- Type: `boolean`
- Default: `false`
- UI label: `Allow unsigned plugins`
- Meaning: allow plugins that do not pass trust / signature checks.

## `mcp_servers.yaml`

### Summary

This file configures external MCP servers. It does not configure built-in `memory`, `artifact`, or `bash_exec`, and it does not store project-local MCP state.

### Schema

```yaml
servers:
  browser:
    enabled: true
    transport: stdio
    command:
      - npx
      - "@example/browser-mcp"
    url: ""
    cwd: ""
    env: {}
```

### Parameters per server entry

**`servers.<server_id>.enabled`**

- Type: `boolean`
- Default: new cards start as `false`
- Meaning: only enabled external MCP servers are exposed to projects or runners.

**`servers.<server_id>.transport`**

- Type: `string`
- Default: `stdio`
- Allowed values: `stdio`, `streamable_http`, `http`, `sse`
- Meaning: choose local subprocess mode or remote HTTP/SSE mode.

**`servers.<server_id>.command`**

- Type: `list[string]`
- Default: `[]`
- Meaning: process command used by `stdio`.

**`servers.<server_id>.url`**

- Type: `string`
- Default: `""`
- Meaning: URL used by HTTP / SSE transports.

**`servers.<server_id>.cwd`**

- Type: `string`
- Default: `""`
- Meaning: optional working directory when starting a local `stdio` process.

**`servers.<server_id>.env`**

- Type: `mapping[string, string]`
- Default: `{}`
- Meaning: per-server environment overrides.

## Validation And Test Behavior

### `config.yaml`

`Test` checks:

- whether `git` is installed
- whether `git config user.name` exists
- whether `git config user.email` exists
- whether the configured `home` path exists

### `runners.yaml`

`Test` checks:

- whether enabled runner binaries are on `PATH`
- disabled runners are skipped with an explicit note

### `connectors.yaml`

`Validate` checks:

- required credentials
- transport / field consistency
- `relay_url` presence in relay mode
- platform-specific required and recommended fields

`Test` performs lightweight readiness probes such as:

- Telegram: `getMe`
- Slack: `auth.test`
- Feishu: tenant-token exchange
- QQ: `access_token` exchange plus `/gateway` probe

### `plugins.yaml`

- No complex runtime test; mostly structural validation.

### `mcp_servers.yaml`

- Currently mostly structural validation. Real connectivity depends on whether the target process or endpoint is actually available.

## Recommended Starter Profile

### Local single-machine research

```yaml
# config.yaml
default_runner: codex
default_locale: en-US
ui:
  host: 0.0.0.0
  port: 20999
  default_mode: both
git:
  auto_checkpoint: true
  auto_push: false
connectors:
  auto_ack: true
  milestone_push: true
  direct_chat_enabled: true
```

### No-public-callback connector strategy

- Telegram: `transport: polling`
- Discord: `transport: gateway`
- Slack: `transport: socket_mode`
- Feishu: `transport: long_connection`
- WhatsApp: `transport: local_session`
- QQ: fixed `gateway_direct`

## Related Docs

- [02 Start Research Guide: Fill the Start Research Contract](./02_START_RESEARCH_GUIDE.md)
- [05 TUI Guide: Use the Terminal Interface](./05_TUI_GUIDE.md)
- [06 Runtime and Canvas: Understand Runtime Flow and Canvas](./06_RUNTIME_AND_CANVAS.md)
