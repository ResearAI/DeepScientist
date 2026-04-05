# 01 Settings Reference: Configure DeepScientist

This manual documents the current DeepScientist `Settings` surface and the YAML files it actually edits. The structure intentionally follows a PyTorch-style reference pattern: short summary, schema, parameters, defaults, allowed values, runtime effect, and practical notes.

Implementation sources:

- `src/ui/src/components/settings/settingsFormCatalog.ts`
- `src/ui/src/components/settings/connectorCatalog.ts`
- `src/ui/src/components/settings/RegistrySettingsForm.tsx`
- `src/deepscientist/config/models.py`
- `src/deepscientist/config/service.py`

## Overview

The `Settings` page writes directly to the following files:

| File | UI category | Purpose |
| --- | --- | --- |
| `~/DeepScientist/config/config.yaml` | Runtime | Main runtime config: home path, daemon, UI, logging, Git, skill sync, cloud, ACP |
| `~/DeepScientist/config/runners.yaml` | Models | Runner config: `codex` / `claude` binary path, model defaults, approval policy, sandbox, retries |
| `~/DeepScientist/config/connectors.yaml` | Connectors | QQ, Telegram, Discord, Slack, Feishu, WhatsApp, Lingzhu connector config |
| `~/DeepScientist/config/plugins.yaml` | Extensions | Plugin discovery, enable/disable overrides, trust policy |
| `~/DeepScientist/config/mcp_servers.yaml` | MCP | External MCP servers only; not built-in `memory`, `artifact`, or `bash_exec` |

Button semantics:

- `Save`: write the current structured form back to YAML.
- `Check` / `Validate`: local schema validation only.
- `Test`: run a lightweight readiness probe. The exact behavior depends on the file type and is described later in this document.

Connector-specific setup guides:

- `docs/en/03_QQ_CONNECTOR_GUIDE.md`
- `docs/en/04_LINGZHU_CONNECTOR_GUIDE.md`

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
- Allowed values: currently `codex`, `claude`
- UI label: `Default runner`
- Meaning: runner used when a project does not override it.
- Notes: in the current branch, `codex` is the primary path and `claude` remains a reserved slot.

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

`runners.yaml` defines which runner executes projects and what its default model, approval policy, sandbox, and retry behavior should be. In the current open-source release:

- `codex`: primary path, enabled by default
- `claude`: TODO / reserved slot, disabled by default, not runnable yet

### Schema

```yaml
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: ""
  model: gpt-5.4
  model_reasoning_effort: xhigh
  approval_policy: never
  sandbox_mode: danger-full-access
  retry_on_failure: true
  retry_max_attempts: 5
  retry_initial_backoff_sec: 1.0
  retry_backoff_multiplier: 2.0
  retry_max_backoff_sec: 8.0
  mcp_tool_timeout_sec: 180000
  env: {}
claude:
  enabled: false
  binary: claude
  config_dir: ~/.claude
  model: inherit
  model_reasoning_effort: ""
  env: {}
  status: reserved_todo
```

### Editable fields

**`enabled`**

- Type: `boolean`
- Default: `codex=true`, `claude=false`
- UI label: `Enabled`
- Meaning: whether this runner can be selected and used.

**`binary`**

- Type: `string`
- Default: `codex` or `claude`
- UI label: `Binary`
- Meaning: command name or absolute path used to launch the runner.
- `Test` behavior: checks whether the binary is on `PATH`.
- Resolution order for `codex`: env override, explicit path, local `PATH`, then bundled fallback.
- One-off note: you can temporarily override this with `ds --codex /absolute/path/to/codex`.
- First-run note: DeepScientist does not finish Codex authentication for you. Before the first `ds`, make sure `codex --login` (or `codex`) has completed successfully.
- Repair note: if the bundled dependency is missing after `npm install -g @researai/deepscientist`, install Codex explicitly with `npm install -g @openai/codex`.

**`config_dir`**

- Type: `string`
- Default: `~/.codex` or `~/.claude`
- UI label: `Config directory`
- Meaning: global runner home for auth and global config.

**`profile`**

- Type: `string`
- Default: `""`
- UI label: `Codex profile`
- Meaning: optional Codex profile name passed through as `codex --profile <name>`.
- Use this when your Codex CLI is already configured for a provider-backed setup such as MiniMax, GLM, Volcengine Ark, or Alibaba Bailian.
- One-off note: you can also leave this field empty and launch with `ds --codex-profile <name>`.
- Combined note: one-off profile and binary overrides can be combined as `ds --codex /absolute/path/to/codex --codex-profile <name>`.

**`model`**

- Type: `string`
- Default: `codex=gpt-5.4`, `claude=inherit`
- UI label: `Default model`
- Meaning: default model used when a project does not override it.
- Startup note: DeepScientist's Codex readiness probe uses this configured model first. If your Codex account cannot access it, DeepScientist falls back to the current Codex default model and persists `model: inherit`.
- Provider-profile note: when `profile` is set, `model: inherit` is usually the right choice so the Codex profile itself controls the provider model.

**`model_reasoning_effort`**

- Type: `string`
- Default: `codex=xhigh`
- UI label: `Reasoning effort`
- Allowed values: `""`, `minimal`, `low`, `medium`, `high`, `xhigh`
- Meaning: default reasoning intensity.
- Compatibility note: when DeepScientist detects a Codex CLI older than `0.63.0`, it automatically downgrades `xhigh` to `high` for the startup probe and runner command. This covers MiniMax's currently recommended `@openai/codex@0.57.0` path.

**`approval_policy`**

- Type: `string`
- Default: `never`
- UI label: `Approval policy`
- Allowed values: `never`, `on-failure`, `on-request`, `untrusted`
- Meaning: how the runner should ask for permission on privileged actions.
- Runtime note: the launcher now starts Codex in YOLO mode by default. Passing `ds --yolo false` temporarily restores the non-YOLO pair `approval_policy=on-request` and `sandbox_mode=workspace-write`.

**`sandbox_mode`**

- Type: `string`
- Default: `danger-full-access`
- UI label: `Sandbox mode`
- Allowed values: `read-only`, `workspace-write`, `danger-full-access`
- Meaning: filesystem / process access mode for the runner.

**`env`**

- Type: `mapping<string, string>`
- Default: `{}`
- UI availability:
  - global settings: editable in the `runners` structured form as `env`
  - project settings: `Project settings -> Codex environment`
- Project-settings behavior:
  - click `Add` to create a new variable row
  - `OPENAI_BASE_URL` and `OPENAI_API_KEY` are shown by default
  - changes are not auto-saved; click `Save env vars`
  - empty values are ignored and are not injected into the Codex process
- Meaning: extra environment variables passed to Codex when DeepScientist starts a Codex run.
- Common use: provider-backed Codex setups that need API keys or custom base URLs.

**`retry_on_failure`**

- Type: `boolean`
- Default: `true`
- UI label: `Retry on failure`
- Meaning: retry a failed turn automatically.

**`retry_max_attempts`**

- Type: `number`
- Default: `5`
- UI label: `Max attempts`
- Meaning: total allowed attempts for one turn.
- Notes: runtime hard-caps this at `5`.

**`retry_initial_backoff_sec`**

- Type: `number`
- Default: `1.0`
- UI label: `Initial backoff (s)`
- Meaning: delay before the first retry.

**`retry_backoff_multiplier`**

- Type: `number`
- Default: `2.0`
- UI label: `Backoff multiplier`
- Meaning: exponential backoff multiplier.

**`retry_max_backoff_sec`**

- Type: `number`
- Default: `8.0`
- UI label: `Max backoff (s)`
- Meaning: upper bound on retry delay after exponential growth.

**`status`**

- Type: `string`
- Default: `claude=reserved_todo`
- UI label: `Status note`
- Meaning: operator-facing note such as `reserved_todo` or `experimental`.

### File-level companion fields

**`mcp_tool_timeout_sec`**

- Type: `number`
- Default: `180000`
- Meaning: allow long-running MCP tool calls, especially durable `bash_exec` flows.

**`env`**

- Type: `mapping[string, string]`
- Default: `{}`
- UI location: environment editor at the bottom of each runner card
- Meaning: per-runner environment overrides.

### Practical guidance

- For most installs, keep `codex.enabled: true` and `claude.enabled: false`.
- Do not switch `default_runner` away from `codex` in the current release.
- Do not lower `mcp_tool_timeout_sec` casually if your workflow uses long-running tools.
- Keep retry timing close to `1s / 2x / 8s max` unless you have a specific reason to slow recovery down.

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
