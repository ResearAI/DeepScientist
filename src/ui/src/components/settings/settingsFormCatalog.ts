export type SettingsFieldKind = 'text' | 'password' | 'url' | 'boolean' | 'select' | 'list' | 'number'

export type SettingsField = {
  key: string
  label: string
  kind: SettingsFieldKind
  placeholder?: string
  description: string
  whereToGet: string
  options?: Array<{ label: string; value: string }>
  runners?: string[]
}

export type SettingsSection = {
  id: string
  title: string
  description: string
  fields: SettingsField[]
}

export type RunnerCatalogEntry = {
  name: string
  label: string
  description: string
}

export const configSections: SettingsSection[] = [
  {
    id: 'identity',
    title: 'Core identity',
    description: 'Global runtime identity and locale defaults.',
    fields: [
      {
        key: 'home',
        label: 'Home path',
        kind: 'text',
        placeholder: '/home/you/DeepScientist',
        description: 'Root directory for config, projects, memory, logs, and caches.',
        whereToGet: 'Use your installed DeepScientist home directory. Usually keep the generated path.',
      },
      {
        key: 'default_runner',
        label: 'Default runner',
        kind: 'select',
        description: 'Runner used by default when a project does not override it.',
        whereToGet: 'Choose the runner id that should execute projects most of the time.',
        options: [
          { label: 'Codex', value: 'codex' },
          { label: 'Claude', value: 'claude' },
          { label: 'OpenCode', value: 'opencode' },
        ],
      },
      {
        key: 'default_locale',
        label: 'Default locale',
        kind: 'select',
        description: 'Primary language used by system prompts and runtime defaults. On the first web launch, DeepScientist initializes this from your browser language.',
        whereToGet: 'Leave it as initialized, or override it here if you want the runtime to always prefer a specific language.',
        options: [
          { label: '中文 (zh-CN)', value: 'zh-CN' },
          { label: 'English (en-US)', value: 'en-US' },
        ],
      },
    ],
  },
  {
    id: 'daemon',
    title: 'Daemon policy',
    description: 'Lifecycle and concurrency behavior of the local daemon.',
    fields: [
      {
        key: 'daemon.session_restore_on_start',
        label: 'Restore sessions on start',
        kind: 'boolean',
        description: 'Reopen previous project sessions when the daemon starts.',
        whereToGet: 'Enable when you want the daemon to resume previous working state automatically.',
      },
      {
        key: 'daemon.max_concurrent_quests',
        label: 'Max concurrent projects',
        kind: 'number',
        placeholder: '1',
        description: 'Upper bound on how many projects the daemon may run at the same time.',
        whereToGet: 'Keep `1` unless you intentionally want parallel project execution.',
      },
      {
        key: 'daemon.ack_timeout_ms',
        label: 'Ack timeout (ms)',
        kind: 'number',
        placeholder: '1000',
        description: 'Timeout budget for short acknowledgment operations and connector feedback.',
        whereToGet: 'Increase only if your deployment has consistently slower local I/O or bridges.',
      },
    ],
  },
  {
    id: 'ui',
    title: 'Web / TUI runtime',
    description: 'How the local UI process binds and starts.',
    fields: [
      {
        key: 'ui.host',
        label: 'UI host',
        kind: 'text',
        placeholder: '0.0.0.0',
        description: 'Network interface used by the local web UI server.',
        whereToGet: 'Use `0.0.0.0` for LAN/container access or `127.0.0.1` for local-only use.',
      },
      {
        key: 'ui.port',
        label: 'UI port',
        kind: 'number',
        placeholder: '20999',
        description: 'Port used by the local UI server.',
        whereToGet: 'Choose a free local port; keep the default unless it conflicts with another service.',
      },
      {
        key: 'ui.auto_open_browser',
        label: 'Auto-open browser',
        kind: 'boolean',
        description: 'Open the browser automatically when the UI starts.',
        whereToGet: 'Disable this on remote servers or headless environments.',
      },
      {
        key: 'ui.default_mode',
        label: 'Default start mode',
        kind: 'select',
        description: 'Preferred startup surface when launching DeepScientist.',
        whereToGet: 'Choose `both` to keep current web + TUI behavior, or narrow it for a focused workflow.',
        options: [
          { label: 'Both', value: 'both' },
          { label: 'Web', value: 'web' },
          { label: 'TUI', value: 'tui' },
        ],
      },
    ],
  },
  {
    id: 'logging',
    title: 'Logging',
    description: 'Daemon log verbosity and retention.',
    fields: [
      {
        key: 'logging.level',
        label: 'Log level',
        kind: 'select',
        description: 'Controls how verbose daemon and runner logs should be.',
        whereToGet: 'Use `info` normally; switch to `debug` only during troubleshooting.',
        options: [
          { label: 'Debug', value: 'debug' },
          { label: 'Info', value: 'info' },
          { label: 'Warning', value: 'warning' },
          { label: 'Error', value: 'error' },
        ],
      },
      {
        key: 'logging.console',
        label: 'Log to console',
        kind: 'boolean',
        description: 'Mirror runtime logs to the active terminal in addition to file logs.',
        whereToGet: 'Keep enabled for local debugging; disable only if you want quieter terminals.',
      },
      {
        key: 'logging.keep_days',
        label: 'Retention days',
        kind: 'number',
        placeholder: '30',
        description: 'How long local runtime logs should be kept before cleanup.',
        whereToGet: 'Use a larger value if you keep long-running audits or reproducibility trails.',
      },
    ],
  },
  {
    id: 'hardware',
    title: 'Hardware preferences',
    description: 'Operator-selected device boundaries and prompt-visible hardware hints.',
    fields: [
      {
        key: 'hardware.gpu_selection_mode',
        label: 'GPU selection mode',
        kind: 'select',
        description: 'Choose whether local GPU execution should treat all detected GPUs as available or only a selected subset.',
        whereToGet: 'Use `all` by default. Switch to `selected` only when the admin operator wants to reserve or isolate GPUs.',
        options: [
          { label: 'All detected GPUs', value: 'all' },
          { label: 'Selected GPU subset', value: 'selected' },
        ],
      },
      {
        key: 'hardware.selected_gpu_ids',
        label: 'Selected GPU ids',
        kind: 'list',
        placeholder: '0, 1',
        description: 'GPU ids allowed for local compute when selection mode is `selected`.',
        whereToGet: 'Use the ids shown on the Admin runtime hardware panel. Leave empty when selection mode stays `all`.',
      },
      {
        key: 'hardware.include_system_hardware_in_prompt',
        label: 'Inject hardware summary into prompt',
        kind: 'boolean',
        description: 'Include the detected local hardware summary and effective GPU boundary in the runtime prompt.',
        whereToGet: 'Keep enabled unless you intentionally want prompts to hide local hardware details.',
      },
    ],
  },
  {
    id: 'git',
    title: 'Git behavior',
    description: 'How DeepScientist checkpoints and exports project state.',
    fields: [
      {
        key: 'git.auto_checkpoint',
        label: 'Auto-checkpoint',
        kind: 'boolean',
        description: 'Create Git checkpoints automatically during project progress.',
        whereToGet: 'Keep enabled unless you want to manage commits entirely by hand.',
      },
      {
        key: 'git.auto_push',
        label: 'Auto-push',
        kind: 'boolean',
        description: 'Push checkpoint commits to the default remote automatically.',
        whereToGet: 'Enable only when the remote is trusted and project repos are safe to push.',
      },
      {
        key: 'git.default_remote',
        label: 'Default remote',
        kind: 'text',
        placeholder: 'origin',
        description: 'Remote name used when auto-push or export actions need a destination.',
        whereToGet: 'Use the Git remote name configured in your project repositories.',
      },
      {
        key: 'git.graph_formats',
        label: 'Graph export formats',
        kind: 'list',
        placeholder: 'svg, png, json',
        description: 'Formats generated for Git / project graph exports.',
        whereToGet: 'Keep the default trio unless you intentionally want fewer export artifacts.',
      },
    ],
  },
  {
    id: 'skills',
    title: 'Skill synchronization',
    description: 'How global and project-local skills are mirrored into runner homes.',
    fields: [
      {
        key: 'skills.sync_global_on_init',
        label: 'Sync global skills on init',
        kind: 'boolean',
        description: 'Install project-provided skills into the global runner home during initialization.',
        whereToGet: 'Enable when you want the machine-wide runner environment kept in sync automatically.',
      },
      {
        key: 'skills.sync_quest_on_create',
        label: 'Sync project skills on create',
        kind: 'boolean',
        description: 'Mirror skills into a project-local runner home when a new project is created.',
        whereToGet: 'Keep enabled so new projects start with the expected skills immediately available.',
      },
      {
        key: 'skills.sync_quest_on_open',
        label: 'Sync project skills on open',
        kind: 'boolean',
        description: 'Refresh the project-local skill mirror when an existing project is opened.',
        whereToGet: 'Enable if you update repo skills frequently and want open projects to pick them up.',
      },
    ],
  },
  {
    id: 'bootstrap',
    title: 'Codex bootstrap',
    description: 'First-start Codex readiness gate. DeepScientist flips this to ready after the startup hello probe succeeds once.',
    fields: [
      {
        key: 'bootstrap.codex_ready',
        label: 'Codex ready',
        kind: 'boolean',
        description: 'Whether the startup Codex hello probe has already succeeded on this home directory.',
        whereToGet: 'Keep this false if you want DeepScientist to re-check Codex login on the next daemon start. It flips to true automatically after a successful startup probe.',
      },
      {
        key: 'bootstrap.codex_last_checked_at',
        label: 'Last checked at',
        kind: 'text',
        placeholder: '2026-03-15T10:00:00Z',
        description: 'Timestamp of the latest startup Codex readiness probe.',
        whereToGet: 'This is written automatically after each startup probe. You normally do not need to edit it by hand.',
      },
      {
        key: 'bootstrap.codex_last_result.summary',
        label: 'Last probe summary',
        kind: 'text',
        placeholder: 'Codex startup probe completed.',
        description: 'Short summary of the last startup Codex probe result.',
        whereToGet: 'DeepScientist writes this automatically. Use it to understand why startup was blocked last time.',
      },
    ],
  },
  {
    id: 'connector-behavior',
    title: 'Connector policy',
    description: 'Global delivery behavior shared across connector integrations.',
    fields: [
      {
        key: 'connectors.auto_ack',
        label: 'Auto-ack incoming messages',
        kind: 'boolean',
        description: 'Send immediate short acknowledgments before the full project work completes.',
        whereToGet: 'Enable for chat-first operators who expect a quick “received” response.',
      },
      {
        key: 'connectors.milestone_push',
        label: 'Push milestones',
        kind: 'boolean',
        description: 'Allow milestone and decision updates to fan out through enabled connectors.',
        whereToGet: 'Disable only when you want connectors to stay passive and poll-based.',
      },
      {
        key: 'connectors.direct_chat_enabled',
        label: 'Enable direct chat',
        kind: 'boolean',
        description: 'Allow connectors to start or continue projects from direct messages.',
        whereToGet: 'Disable if all connector traffic should be funneled through approved group chats only.',
      },
    ],
  },
  {
    id: 'connector-visibility',
    title: 'System connector visibility',
    description: 'System-level gate for which connectors are exposed in Settings, Start Research, project settings, and background runtime startup.',
    fields: [
      {
        key: 'connectors.system_enabled.qq',
        label: 'Show QQ connector',
        kind: 'boolean',
        description: 'If disabled, QQ is hidden from the product UI and DeepScientist will not start its background runtime.',
        whereToGet: 'Keep this enabled for the default install path.',
      },
      {
        key: 'connectors.system_enabled.telegram',
        label: 'Show Telegram connector',
        kind: 'boolean',
        description: 'If disabled, Telegram is hidden from the product UI and DeepScientist will not start its background runtime.',
        whereToGet: 'Enable this only when you plan to configure Telegram on this machine.',
      },
      {
        key: 'connectors.system_enabled.discord',
        label: 'Show Discord connector',
        kind: 'boolean',
        description: 'If disabled, Discord is hidden from the product UI and DeepScientist will not start its background runtime.',
        whereToGet: 'Enable this only when you plan to configure Discord on this machine.',
      },
      {
        key: 'connectors.system_enabled.slack',
        label: 'Show Slack connector',
        kind: 'boolean',
        description: 'If disabled, Slack is hidden from the product UI and DeepScientist will not start its background runtime.',
        whereToGet: 'Enable this only when you plan to configure Slack on this machine.',
      },
      {
        key: 'connectors.system_enabled.feishu',
        label: 'Show Feishu connector',
        kind: 'boolean',
        description: 'If disabled, Feishu is hidden from the product UI and DeepScientist will not start its background runtime.',
        whereToGet: 'Enable this only when you plan to configure Feishu on this machine.',
      },
      {
        key: 'connectors.system_enabled.whatsapp',
        label: 'Show WhatsApp connector',
        kind: 'boolean',
        description: 'If disabled, WhatsApp is hidden from the product UI and DeepScientist will not start its background runtime.',
        whereToGet: 'Enable this only when you plan to configure WhatsApp on this machine.',
      },
      {
        key: 'connectors.system_enabled.lingzhu',
        label: 'Show Lingzhu (Rokid Glasses) connector',
        kind: 'boolean',
        description: 'Compatibility flag for the Lingzhu companion path. Lingzhu settings remain visible so Rokid binding values can always be configured.',
        whereToGet: 'You usually do not need to change this. Lingzhu setup is now always exposed in Settings.',
      },
    ],
  },
  {
    id: 'cloud',
    title: 'Cloud link',
    description: 'Optional remote coordination or account binding.',
    fields: [
      {
        key: 'cloud.enabled',
        label: 'Enable cloud link',
        kind: 'boolean',
        description: 'Turn on the optional DeepScientist cloud link path.',
        whereToGet: 'Leave disabled for fully local-first deployments.',
      },
      {
        key: 'cloud.base_url',
        label: 'Cloud base URL',
        kind: 'url',
        placeholder: 'https://deepscientist.cc',
        description: 'Base URL of the cloud service used for optional sync or token verification.',
        whereToGet: 'Set this only if you operate against a custom or self-hosted cloud endpoint.',
      },
      {
        key: 'cloud.token',
        label: 'Cloud token',
        kind: 'password',
        placeholder: 'token',
        description: 'Direct token used for cloud authentication when not sourced from an environment variable.',
        whereToGet: 'Prefer `token_env` in shared or production environments.',
      },
      {
        key: 'cloud.token_env',
        label: 'Cloud token env var',
        kind: 'text',
        placeholder: 'DEEPSCIENTIST_TOKEN',
        description: 'Environment variable name that holds the cloud token.',
        whereToGet: 'Use the env var name you export in your shell, service unit, or container.',
      },
      {
        key: 'cloud.verify_token_on_start',
        label: 'Verify token on start',
        kind: 'boolean',
        description: 'Validate the configured cloud token when the daemon starts.',
        whereToGet: 'Enable only if you want startup to fail fast on invalid cloud credentials.',
      },
      {
        key: 'cloud.sync_mode',
        label: 'Cloud sync mode',
        kind: 'select',
        description: 'Overall cloud synchronization mode.',
        whereToGet: 'Keep `disabled` unless you have a specific cloud sync workflow.',
        options: [
          { label: 'Disabled', value: 'disabled' },
          { label: 'Pull', value: 'pull' },
          { label: 'Push', value: 'push' },
          { label: 'Bidirectional', value: 'bidirectional' },
        ],
      },
    ],
  },
  {
    id: 'acp',
    title: 'ACP bridge',
    description: 'Compatibility knobs for ACP-style session envelopes.',
    fields: [
      {
        key: 'acp.compatibility_profile',
        label: 'Compatibility profile',
        kind: 'text',
        placeholder: 'deepscientist-acp-compat/v1',
        description: 'Named ACP compatibility profile used when exposing project sessions to external consumers.',
        whereToGet: 'Keep the built-in profile unless you are intentionally matching another ACP consumer.',
      },
      {
        key: 'acp.events_transport',
        label: 'Events transport',
        kind: 'select',
        description: 'Transport used for ACP-style event delivery.',
        whereToGet: 'Use `rest-poll` unless you have implemented another ACP bridge transport.',
        options: [
          { label: 'REST poll', value: 'rest-poll' },
          { label: 'SSE', value: 'sse' },
        ],
      },
      {
        key: 'acp.sdk_bridge_enabled',
        label: 'Enable SDK bridge',
        kind: 'boolean',
        description: 'Allow the runtime to bridge through an ACP SDK module.',
        whereToGet: 'Enable only when you have an ACP SDK integration in your environment.',
      },
      {
        key: 'acp.sdk_module',
        label: 'SDK module',
        kind: 'text',
        placeholder: 'acp',
        description: 'Python module name used when ACP SDK bridging is enabled.',
        whereToGet: 'Set this to the importable module that exposes your ACP bridge implementation.',
      },
    ],
  },
]

export const pluginSections: SettingsSection[] = [
  {
    id: 'plugins',
    title: 'Plugin discovery',
    description: 'External plugin loading and trust policy.',
    fields: [
      {
        key: 'load_paths',
        label: 'Load paths',
        kind: 'list',
        placeholder: '/home/you/DeepScientist/plugins',
        description: 'Directories scanned for installable or locally linked plugin bundles.',
        whereToGet: 'List one directory per line or comma-separated. Keep the default plugin directory in the list.',
      },
      {
        key: 'enabled',
        label: 'Force-enable plugin ids',
        kind: 'list',
        placeholder: 'plugin-a, plugin-b',
        description: 'Optional plugin ids that should be enabled explicitly.',
        whereToGet: 'Fill only when you want to override normal auto-discovery behavior.',
      },
      {
        key: 'disabled',
        label: 'Force-disable plugin ids',
        kind: 'list',
        placeholder: 'plugin-x, plugin-y',
        description: 'Optional plugin ids that should stay disabled even if discovered.',
        whereToGet: 'Use for temporary rollbacks or local blocklists.',
      },
      {
        key: 'allow_unsigned',
        label: 'Allow unsigned plugins',
        kind: 'boolean',
        description: 'Permit loading plugins that do not pass signature / trust checks.',
        whereToGet: 'Only enable if you fully trust the plugin source and local machine.',
      },
    ],
  },
]

export const runnerCatalog: RunnerCatalogEntry[] = [
  {
    name: 'codex',
    label: 'Codex',
    description: 'Primary DeepScientist runner. Controls the CLI binary, model defaults, and sandbox policy.',
  },
  {
    name: 'claude',
    label: 'Claude',
    description: 'Anthropic Claude Code runner. Uses headless Claude Code CLI with DeepScientist MCP injection and dangerous bypassPermissions defaults.',
  },
  {
    name: 'opencode',
    label: 'OpenCode',
    description: 'OpenCode runner. Uses the OpenCode CLI / JSON event path with DeepScientist MCP injection and permission allow defaults.',
  },
]

export const runnerFields: SettingsField[] = [
  {
    key: 'enabled',
    label: 'Enabled',
    kind: 'boolean',
    description: 'Whether this runner is available for selection and execution.',
    whereToGet: 'Disable a runner if the binary or environment is not installed on this machine.',
  },
  {
    key: 'binary',
    label: 'Binary',
    kind: 'text',
    placeholder: 'codex',
    description: 'Command name or absolute path used to launch the runner.',
    whereToGet: 'Use the executable name on PATH or an absolute binary path for custom installs.',
  },
  {
    key: 'config_dir',
    label: 'Config directory',
    kind: 'text',
    placeholder: '~/.codex',
    description: 'Global runner home used for auth and global configuration.',
    whereToGet: 'Point this to the runner home directory that stores auth and global config files.',
  },
  {
    key: 'profile',
    label: 'Codex profile',
    kind: 'text',
    placeholder: 'm27',
    description: 'Optional Codex profile passed through as `codex --profile <name>`.',
    whereToGet: 'Use this for provider-specific Codex setups such as MiniMax or other custom profiles. Leave it empty for the default login-based Codex path.',
    runners: ['codex'],
  },
  {
    key: 'model',
    label: 'Default model',
    kind: 'text',
    placeholder: 'gpt-5.4',
    description: 'Default model used when the project or request does not override it.',
    whereToGet: 'Use the model id accepted by the selected runner.',
  },
  {
    key: 'model_reasoning_effort',
    runners: ['codex'],
    label: 'Reasoning effort',
    kind: 'select',
    description: 'Default reasoning intensity used by the runner when the request does not override it. `None` omits this parameter entirely.',
    whereToGet: 'Use the effort level accepted by the selected runner; choose `None` when you want DeepScientist to avoid sending the reasoning-effort parameter.',
    options: [
      { label: 'None', value: '' },
      { label: 'Minimal', value: 'minimal' },
      { label: 'Low', value: 'low' },
      { label: 'Medium', value: 'medium' },
      { label: 'High', value: 'high' },
      { label: 'XHigh', value: 'xhigh' },
    ],
  },
  {
    key: 'approval_policy',
    runners: ['codex'],
    label: 'Approval policy',
    kind: 'select',
    description: 'How the runner should request permission for privileged actions.',
    whereToGet: 'Pick the policy that matches your local trust and automation level.',
    options: [
      { label: 'Never', value: 'never' },
      { label: 'On failure', value: 'on-failure' },
      { label: 'On request', value: 'on-request' },
      { label: 'Untrusted', value: 'untrusted' },
    ],
  },
  {
    key: 'sandbox_mode',
    runners: ['codex'],
    label: 'Sandbox mode',
    kind: 'select',
    description: 'Filesystem / process sandbox applied to runner actions.',
    whereToGet: 'Use the most restrictive mode that still allows your expected workflow.',
    options: [
      { label: 'Read only', value: 'read-only' },
      { label: 'Workspace write', value: 'workspace-write' },
      { label: 'Danger full access', value: 'danger-full-access' },
    ],
  },
  {
    key: 'permission_mode',
    label: 'Permission mode',
    kind: 'select',
    description: 'Claude Code permission mode used for headless execution.',
    whereToGet: 'Use `bypassPermissions` for Codex-like local automation, or choose a stricter mode when you want Claude Code to stop for permission decisions.',
    options: [
      { label: 'Default', value: 'default' },
      { label: 'Bypass permissions', value: 'bypassPermissions' },
      { label: 'Dont ask', value: 'dontAsk' },
      { label: 'Accept edits', value: 'acceptEdits' },
      { label: 'Delegate', value: 'delegate' },
      { label: 'Plan', value: 'plan' },
    ],
    runners: ['claude'],
  },
  {
    key: 'default_agent',
    label: 'Default agent',
    kind: 'text',
    placeholder: 'research',
    description: 'Optional OpenCode agent name passed through as `opencode run --agent <name>`.',
    whereToGet: 'Leave empty to use the OpenCode default agent. Fill this when you want a specific OpenCode agent profile for DeepScientist turns.',
    runners: ['opencode'],
  },
  {
    key: 'variant',
    label: 'Variant',
    kind: 'text',
    placeholder: 'high',
    description: 'Optional OpenCode model variant such as provider-specific reasoning tiers.',
    whereToGet: 'Use this only when your OpenCode provider documents a variant flag; otherwise leave it empty.',
    runners: ['opencode'],
  },
  {
    key: 'retry_on_failure',
    label: 'Retry on failure',
    kind: 'boolean',
    description: 'Automatically retry a failed runner turn instead of immediately ending the project turn as an error.',
    whereToGet: 'Keep enabled for Codex so transient CLI or transport failures can recover automatically.',
  },
  {
    key: 'retry_max_attempts',
    label: 'Max attempts',
    kind: 'number',
    placeholder: '7',
    description: 'Upper bound on total attempts for one project turn, including the first run.',
    whereToGet: 'Use a small number; DeepScientist hard-caps this at `7` even if a larger value is entered.',
  },
  {
    key: 'retry_initial_backoff_sec',
    label: 'Initial backoff (s)',
    kind: 'number',
    placeholder: '10',
    description: 'Delay before the first retry after a failed attempt.',
    whereToGet: 'Use `10` for the default Codex ladder of 10s → 60s → 360s → 1800s, then hold the 30-minute cap for the last two retries.',
  },
  {
    key: 'retry_backoff_multiplier',
    label: 'Backoff multiplier',
    kind: 'number',
    placeholder: '6',
    description: 'Multiplier applied to each later retry delay to form exponential backoff.',
    whereToGet: 'Use `6` to keep the default Codex retries exponential until they hit the 30-minute cap.',
  },
  {
    key: 'retry_max_backoff_sec',
    label: 'Max backoff (s)',
    kind: 'number',
    placeholder: '1800',
    description: 'Maximum delay allowed between retries after exponential growth is applied.',
    whereToGet: 'Use `1800` so the final retry phase waits about 30 minutes between attempts.',
  },
  {
    key: 'mcp_tool_timeout_sec',
    label: 'MCP timeout (s)',
    kind: 'number',
    placeholder: '180000',
    description: 'Codex MCP tool timeout for long-running `bash_exec(mode=await)` and other durable MCP calls.',
    whereToGet: 'Keep the large default unless you explicitly want Codex to fail faster on long MCP operations.',
    runners: ['codex'],
  },
  {
    key: 'status',
    label: 'Status note',
    kind: 'text',
    placeholder: 'supported_experimental',
    description: 'Optional operator note about the state of this runner integration.',
    whereToGet: 'Use this for reminders like reserved, experimental, or pending setup.',
  },
]

export const mcpTransportOptions = [
  { label: 'Stdio', value: 'stdio' },
  { label: 'Streamable HTTP', value: 'streamable_http' },
  { label: 'HTTP', value: 'http' },
  { label: 'SSE', value: 'sse' },
]
