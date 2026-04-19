import * as React from 'react'
import { Loader2, Save, ShieldCheck, TestTube2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { client } from '@/lib/api'
import { RUNNER_BRANDING, normalizeBuiltinRunnerName, type BuiltinRunnerName } from '@/lib/runnerBranding'
import { cn } from '@/lib/utils'
import type { ConfigTestPayload, ConfigValidationPayload, Locale, OpenDocumentPayload } from '@/types'

type StructuredConfig = Record<string, unknown>

type RunnerField = {
  key: string
  label: string
  kind: 'text' | 'number' | 'boolean' | 'select'
  description: string
  options?: Array<{ label: string; value: string }>
}

const RUNNER_ORDER: BuiltinRunnerName[] = ['codex', 'claude', 'opencode']

const RUNNER_DEFAULTS: Record<BuiltinRunnerName, StructuredConfig> = {
  codex: {
    enabled: true,
    binary: 'codex',
    config_dir: '~/.codex',
    profile: '',
    model: 'inherit',
    model_reasoning_effort: 'xhigh',
    approval_policy: 'never',
    sandbox_mode: 'danger-full-access',
    retry_on_failure: true,
    retry_max_attempts: 7,
    retry_initial_backoff_sec: 10,
    retry_backoff_multiplier: 6,
    retry_max_backoff_sec: 1800,
    mcp_tool_timeout_sec: 180000,
    env: {},
  },
  claude: {
    enabled: false,
    binary: 'claude',
    config_dir: '~/.claude',
    model: 'inherit',
    permission_mode: 'bypassPermissions',
    retry_on_failure: true,
    retry_max_attempts: 4,
    retry_initial_backoff_sec: 10,
    retry_backoff_multiplier: 4,
    retry_max_backoff_sec: 600,
    env: {},
  },
  opencode: {
    enabled: false,
    binary: 'opencode',
    config_dir: '~/.config/opencode',
    model: 'inherit',
    permission_mode: 'allow',
    default_agent: '',
    variant: '',
    retry_on_failure: true,
    retry_max_attempts: 4,
    retry_initial_backoff_sec: 10,
    retry_backoff_multiplier: 4,
    retry_max_backoff_sec: 600,
    env: {},
  },
}

const RUNNER_FIELDS: Record<BuiltinRunnerName, RunnerField[]> = {
  codex: [
    { key: 'binary', label: 'Binary', kind: 'text', description: 'Codex CLI binary name or absolute path.' },
    { key: 'config_dir', label: 'Config directory', kind: 'text', description: 'Codex home used for auth and profiles.' },
    { key: 'profile', label: 'Profile', kind: 'text', description: 'Optional Codex profile name.' },
    { key: 'model', label: 'Model', kind: 'text', description: 'Default model id used by Codex.' },
    {
      key: 'model_reasoning_effort',
      label: 'Reasoning effort',
      kind: 'select',
      description: 'Default Codex reasoning effort.',
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
      label: 'Approval policy',
      kind: 'select',
      description: 'Default Codex approval policy.',
      options: [
        { label: 'Never', value: 'never' },
        { label: 'On failure', value: 'on-failure' },
        { label: 'On request', value: 'on-request' },
        { label: 'Untrusted', value: 'untrusted' },
      ],
    },
    {
      key: 'sandbox_mode',
      label: 'Sandbox mode',
      kind: 'select',
      description: 'Filesystem / process sandbox for Codex.',
      options: [
        { label: 'Read only', value: 'read-only' },
        { label: 'Workspace write', value: 'workspace-write' },
        { label: 'Danger full access', value: 'danger-full-access' },
      ],
    },
    { key: 'mcp_tool_timeout_sec', label: 'MCP timeout (ms)', kind: 'number', description: 'Timeout for long Codex MCP calls.' },
  ],
  claude: [
    { key: 'binary', label: 'Binary', kind: 'text', description: 'Claude Code CLI binary name or absolute path.' },
    { key: 'config_dir', label: 'Config directory', kind: 'text', description: 'Claude Code home used for auth and config.' },
    { key: 'model', label: 'Model', kind: 'text', description: 'Default Claude model id.' },
    {
      key: 'permission_mode',
      label: 'Permission mode',
      kind: 'select',
      description: 'Dangerous no-confirm mode is `bypassPermissions`.',
      options: [
        { label: 'Dangerously skip permissions', value: 'bypassPermissions' },
        { label: 'Default', value: 'default' },
        { label: 'Dont ask', value: 'dontAsk' },
        { label: 'Accept edits', value: 'acceptEdits' },
        { label: 'Delegate', value: 'delegate' },
        { label: 'Plan', value: 'plan' },
      ],
    },
  ],
  opencode: [
    { key: 'binary', label: 'Binary', kind: 'text', description: 'OpenCode CLI binary name or absolute path.' },
    { key: 'config_dir', label: 'Config directory', kind: 'text', description: 'OpenCode home used for config and cache.' },
    { key: 'model', label: 'Model', kind: 'text', description: 'Default OpenCode model id.' },
    {
      key: 'permission_mode',
      label: 'Permission mode',
      kind: 'select',
      description: 'Official no-confirm mode is `allow`.',
      options: [
        { label: 'Allow everything', value: 'allow' },
        { label: 'Ask', value: 'ask' },
        { label: 'Deny', value: 'deny' },
      ],
    },
    { key: 'default_agent', label: 'Default agent', kind: 'text', description: 'Optional `opencode run --agent` value.' },
    { key: 'variant', label: 'Variant', kind: 'text', description: 'Optional `opencode run --variant` value.' },
  ],
}

const COMMON_FIELDS: RunnerField[] = [
  { key: 'retry_on_failure', label: 'Retry on failure', kind: 'boolean', description: 'Retry failed turns automatically.' },
  { key: 'retry_max_attempts', label: 'Max attempts', kind: 'number', description: 'Maximum total attempts for one turn.' },
  { key: 'retry_initial_backoff_sec', label: 'Initial backoff (s)', kind: 'number', description: 'Delay before the first retry.' },
  { key: 'retry_backoff_multiplier', label: 'Backoff multiplier', kind: 'number', description: 'Exponential retry multiplier.' },
  { key: 'retry_max_backoff_sec', label: 'Max backoff (s)', kind: 'number', description: 'Maximum retry delay.' },
]

const copy = {
  en: {
    selectionTitle: 'Global runner',
    selectionBody: 'Choose exactly one active runner for the whole local product. This changes the default runner and disables the others for new work.',
    active: 'Active',
    ready: 'Ready',
    save: 'Save',
    saving: 'Saving…',
    validate: 'Check',
    validating: 'Checking…',
    test: 'Test',
    testing: 'Testing…',
    envTitle: 'Environment variables',
    envEmptyKey: 'KEY',
    envEmptyValue: 'value',
    addEnv: 'Add variable',
    saved: 'Runner selection saved.',
    validation: 'Validation',
    testResult: 'Test',
    noIssues: 'No issues.',
    selectedConfig: 'Selected runner config',
    runtimeScope: 'Affects Settings agent, BenchStore SetupAgent, and standard DeepScientist quests.',
  },
  zh: {
    selectionTitle: '全局 Runner',
    selectionBody: '整个本地产品只保留一个激活中的 runner。这里的选择会同时修改默认 runner，并把另外两个置为非激活状态。',
    active: '当前使用',
    ready: '已就绪',
    save: '保存',
    saving: '保存中…',
    validate: '校验',
    validating: '校验中…',
    test: '测试',
    testing: '测试中…',
    envTitle: '环境变量',
    envEmptyKey: 'KEY',
    envEmptyValue: '值',
    addEnv: '新增变量',
    saved: 'Runner 选择已保存。',
    validation: '校验',
    testResult: '测试',
    noIssues: '没有问题。',
    selectedConfig: '当前 Runner 配置',
    runtimeScope: '会同时影响 Settings agent、BenchStore SetupAgent，以及普通 DeepScientist quest。',
  },
} satisfies Record<Locale, Record<string, string>>

function asObject(value: unknown): StructuredConfig {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as StructuredConfig) : {}
}

function normalizeRunnersDraft(source: StructuredConfig): StructuredConfig {
  const next: StructuredConfig = { ...source }
  for (const runnerName of RUNNER_ORDER) {
    next[runnerName] = { ...RUNNER_DEFAULTS[runnerName], ...asObject(next[runnerName]) }
  }
  return next
}

function normalizeNumber(value: string) {
  const numeric = Number(String(value).trim())
  return Number.isFinite(numeric) ? numeric : value
}

function setRunnerField(config: StructuredConfig, field: RunnerField, rawValue: string | boolean): StructuredConfig {
  const next = { ...config }
  if (field.kind === 'boolean') {
    next[field.key] = Boolean(rawValue)
    return next
  }
  if (field.kind === 'number') {
    next[field.key] = normalizeNumber(String(rawValue))
    return next
  }
  next[field.key] = String(rawValue)
  return next
}

function fieldValue(config: StructuredConfig, field: RunnerField): string | boolean {
  const raw = config[field.key]
  if (field.kind === 'boolean') return Boolean(raw)
  if (field.kind === 'number') return typeof raw === 'number' ? String(raw) : typeof raw === 'string' ? raw : ''
  return typeof raw === 'string' ? raw : raw == null ? '' : String(raw)
}

function resultItemByName(payload: ConfigTestPayload | null) {
  const items = new Map<string, NonNullable<ConfigTestPayload['items'][number]>>()
  for (const item of payload?.items || []) {
    items.set(item.name, item)
  }
  return items
}

function buildSelectionUpdate(currentConfig: StructuredConfig, currentRunners: StructuredConfig, runnerName: BuiltinRunnerName) {
  const nextConfig = {
    ...currentConfig,
    default_runner: runnerName,
  }
  const nextRunners = normalizeRunnersDraft(currentRunners)
  for (const candidate of RUNNER_ORDER) {
    const current = asObject(nextRunners[candidate])
    nextRunners[candidate] = {
      ...current,
      enabled: candidate == runnerName,
      ...(candidate == 'claude' ? { permission_mode: String(current.permission_mode || 'bypassPermissions') || 'bypassPermissions' } : {}),
      ...(candidate == 'opencode' ? { permission_mode: String(current.permission_mode || 'allow') || 'allow' } : {}),
    }
  }
  return { nextConfig, nextRunners }
}

function EnvEditor({ value, locale, onChange }: { value: StructuredConfig; locale: Locale; onChange: (next: StructuredConfig) => void }) {
  const t = copy[locale]
  const rows = React.useMemo(() => {
    const entries = Object.entries(value)
    return entries.length > 0 ? entries : [['', '']]
  }, [value])

  return (
    <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
      <div className="mb-3 text-sm font-medium">{t.envTitle}</div>
      <div className="space-y-3">
        {rows.map(([key, rowValue], index) => (
          <div key={`${key}-${index}`} className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <Input
              value={key}
              onChange={(event) => {
                const nextRows = rows.map((entry, rowIndex) => (rowIndex === index ? [event.target.value, entry[1]] : entry))
                onChange(Object.fromEntries(nextRows.filter(([nextKey]) => nextKey.trim())))
              }}
              placeholder={t.envEmptyKey}
              className="rounded-[18px] border-black/[0.08] bg-white/[0.44] shadow-none dark:bg-white/[0.03]"
            />
            <Input
              value={String(rowValue ?? '')}
              onChange={(event) => {
                const nextRows = rows.map((entry, rowIndex) => (rowIndex === index ? [entry[0], event.target.value] : entry))
                onChange(Object.fromEntries(nextRows.filter(([nextKey]) => nextKey.trim())))
              }}
              placeholder={t.envEmptyValue}
              className="rounded-[18px] border-black/[0.08] bg-white/[0.44] shadow-none dark:bg-white/[0.03]"
            />
          </div>
        ))}
        <Button variant="secondary" onClick={() => onChange({ ...Object.fromEntries(rows), '': '' })}>
          {t.addEnv}
        </Button>
      </div>
    </div>
  )
}

function ResultBlock({ title, payload, empty }: { title: string; payload: { warnings?: string[]; errors?: string[] } | null; empty: string }) {
  const warnings = payload?.warnings || []
  const errors = payload?.errors || []
  return (
    <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
      <div className="mb-3 text-sm font-medium">{title}</div>
      {warnings.length === 0 && errors.length === 0 ? (
        <div className="text-sm text-muted-foreground">{empty}</div>
      ) : (
        <div className="space-y-2">
          {errors.map((item) => (
            <div key={item} className="border-l-2 border-rose-500/60 pl-3 text-sm text-rose-700 dark:text-rose-300">{item}</div>
          ))}
          {warnings.map((item) => (
            <div key={item} className="border-l-2 border-amber-500/60 pl-3 text-sm text-amber-700 dark:text-amber-200">{item}</div>
          ))}
        </div>
      )}
    </div>
  )
}

export function RunnerSettingsPanel({ locale }: { locale: Locale }) {
  const t = copy[locale]
  const [configDoc, setConfigDoc] = React.useState<OpenDocumentPayload | null>(null)
  const [runnersDoc, setRunnersDoc] = React.useState<OpenDocumentPayload | null>(null)
  const [configDraft, setConfigDraft] = React.useState<StructuredConfig>({})
  const [runnersDraft, setRunnersDraft] = React.useState<StructuredConfig>({})
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [validating, setValidating] = React.useState(false)
  const [testing, setTesting] = React.useState(false)
  const [message, setMessage] = React.useState('')
  const [validation, setValidation] = React.useState<ConfigValidationPayload | null>(null)
  const [testResult, setTestResult] = React.useState<ConfigTestPayload | null>(null)

  const load = React.useCallback(async () => {
    setLoading(true)
    try {
      const [configPayload, runnersPayload] = await Promise.all([
        client.configDocument('config'),
        client.configDocument('runners'),
      ])
      setConfigDoc(configPayload)
      setRunnersDoc(runnersPayload)
      setConfigDraft(asObject(configPayload.meta?.structured_config))
      setRunnersDraft(normalizeRunnersDraft(asObject(runnersPayload.meta?.structured_config)))
      setValidation(null)
      setTestResult(null)
      setMessage('')
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    void load()
  }, [load])

  const selectedRunner = normalizeBuiltinRunnerName(configDraft.default_runner)
  const selectedBranding = RUNNER_BRANDING[selectedRunner]
  const selectedConfig = asObject(runnersDraft[selectedRunner])
  const selectedFields = [...RUNNER_FIELDS[selectedRunner], ...COMMON_FIELDS]
  const testItems = React.useMemo(() => resultItemByName(testResult), [testResult])
  const selectedTestItem = testItems.get(selectedRunner)

  const persist = React.useCallback(async (nextConfigDraft: StructuredConfig, nextRunnersDraft: StructuredConfig, savedMessage: string) => {
    if (!configDoc || !runnersDoc) return
    setSaving(true)
    try {
      const configResult = await client.saveConfig('config', {
        structured: nextConfigDraft,
        revision: configDoc.revision,
      })
      if (!configResult.ok) {
        setMessage(configResult.message || '')
        return
      }
      const runnersResult = await client.saveConfig('runners', {
        structured: nextRunnersDraft,
        revision: runnersDoc.revision,
      })
      if (!runnersResult.ok) {
        setMessage(runnersResult.message || '')
        return
      }
      const selectedRunner = normalizeBuiltinRunnerName(nextConfigDraft.default_runner)
      try {
        const questsPayload = await client.quests()
        for (const quest of questsPayload || []) {
          const questId = String(quest.quest_id || '').trim()
          if (!questId) continue
          const startupContract = quest.startup_contract && typeof quest.startup_contract === 'object'
            ? (quest.startup_contract as Record<string, unknown>)
            : null
          const workspaceMode = String(quest.workspace_mode || startupContract?.workspace_mode || '').trim().toLowerCase()
          const title = String(quest.title || '').trim()
          const isAdminRepair = title.startsWith('Admin Repair ')
          const isSetupAgent = title.startsWith('SetupAgent ·')
          if (!isAdminRepair && !isSetupAgent && workspaceMode !== 'copilot' && workspaceMode !== 'autonomous') {
            continue
          }
          const currentRunner = String(quest.default_runner || quest.runner || '').trim().toLowerCase()
          if (currentRunner === selectedRunner) continue
          await client.updateQuestSettings(questId, { default_runner: selectedRunner })
        }
      } catch {
        // Best-effort propagation only.
      }
      setMessage(savedMessage)
      await load()
    } finally {
      setSaving(false)
    }
  }, [configDoc, runnersDoc, load])

  const handleSelectRunner = async (runnerName: BuiltinRunnerName) => {
    const { nextConfig, nextRunners } = buildSelectionUpdate(configDraft, runnersDraft, runnerName)
    setConfigDraft(nextConfig)
    setRunnersDraft(nextRunners)
    await persist(nextConfig, nextRunners, t.saved)
  }

  const handleSave = async () => {
    await persist(configDraft, runnersDraft, t.saved)
  }

  const handleValidate = async () => {
    setValidating(true)
    try {
      setValidation(await client.validateConfig('runners', { structured: runnersDraft }))
    } finally {
      setValidating(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    try {
      setTestResult(await client.testConfig('runners', { structured: runnersDraft, live: true }))
    } finally {
      setTesting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-3 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading runners...
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <section className="rounded-[26px] border border-black/[0.08] bg-[linear-gradient(145deg,rgba(253,247,241,0.94),rgba(239,229,220,0.84)_42%,rgba(226,235,239,0.82))] p-5 shadow-[0_24px_80px_-60px_rgba(44,39,34,0.28)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.selectionTitle}</div>
            <div className="mt-2 max-w-[820px] text-sm leading-7 text-muted-foreground">{t.selectionBody}</div>
            <div className="mt-2 text-xs text-muted-foreground">{t.runtimeScope}</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void handleSave()} disabled={saving}>
              <Save className="h-4 w-4" />
              {saving ? t.saving : t.save}
            </Button>
            <Button variant="secondary" onClick={() => void handleValidate()} disabled={validating}>
              <ShieldCheck className="h-4 w-4" />
              {validating ? t.validating : t.validate}
            </Button>
            <Button variant="secondary" onClick={() => void handleTest()} disabled={testing}>
              <TestTube2 className="h-4 w-4" />
              {testing ? t.testing : t.test}
            </Button>
          </div>
        </div>

        <div className="mt-5 grid gap-4 lg:grid-cols-3">
          {RUNNER_ORDER.map((runnerName) => {
            const branding = RUNNER_BRANDING[runnerName]
            const runnerConfig = asObject(runnersDraft[runnerName])
            const isSelected = selectedRunner === runnerName
            const isReady = Boolean(testItems.get(runnerName)?.ok)
            return (
              <button
                key={runnerName}
                type="button"
                data-runner-card={runnerName}
                data-runner-selected={isSelected ? 'true' : 'false'}
                onClick={() => void handleSelectRunner(runnerName)}
                className={cn(
                  'group overflow-hidden rounded-[24px] border p-0 text-left transition',
                  isSelected
                    ? 'border-black/[0.24] shadow-[0_18px_40px_-28px_rgba(18,24,32,0.34)]'
                    : 'border-black/[0.08] hover:border-black/[0.18]'
                )}
              >
                <div className={cn('flex min-h-[140px] flex-col justify-between bg-gradient-to-br p-5', branding.accentClassName)}>
                  <div className="flex items-start justify-between gap-3">
                    <img src={branding.logoSrc} alt={branding.label} className="h-14 w-14 rounded-[18px] bg-white/20 p-2.5 shadow-sm" />
                    {isSelected ? <Badge className="bg-white/80 text-[#111827]">{t.active}</Badge> : null}
                  </div>
                  <div>
                    <div className="text-xl font-semibold tracking-tight">{branding.label}</div>
                    <div className="mt-2 text-sm leading-6 opacity-90">{branding.description}</div>
                  </div>
                </div>
                <div className="flex items-center justify-between gap-3 bg-white/[0.84] px-5 py-4 dark:bg-white/[0.03]">
                  <div className="text-sm text-muted-foreground">{String(runnerConfig.model || 'inherit')}</div>
                  {isReady ? <Badge className={branding.chipClassName}>{t.ready}</Badge> : null}
                </div>
              </button>
            )
          })}
        </div>
      </section>

      {message ? <div className="text-sm text-emerald-700 dark:text-emerald-300">{message}</div> : null}

      <section className="space-y-5 rounded-[24px] border border-black/[0.08] bg-white/[0.52] p-5 dark:border-white/[0.12] dark:bg-white/[0.04]">
        <div className="flex items-center gap-3">
          <img src={selectedBranding.logoSrc} alt={selectedBranding.label} className="h-12 w-12 rounded-[16px] border border-black/[0.08] bg-white/70 p-2 shadow-sm dark:border-white/[0.12] dark:bg-white/[0.08]" />
          <div>
            <div className="text-lg font-semibold tracking-tight">{selectedBranding.label}</div>
            <div className="text-sm text-muted-foreground">{t.selectedConfig}</div>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          {selectedFields.map((field) => (
            <div key={`${selectedRunner}-${field.key}`} className={cn('rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]', field.kind === 'boolean' && 'md:col-span-2')}>
              <label className="flex items-start justify-between gap-4">
                <span className="min-w-0">
                  <span className="block text-sm font-medium">{field.label}</span>
                  <span className="mt-2 block text-xs leading-6 text-muted-foreground">{field.description}</span>
                </span>
                {field.kind === 'boolean' ? (
                  <input
                    type="checkbox"
                    checked={Boolean(fieldValue(selectedConfig, field))}
                    onChange={(event) => setRunnersDraft({ ...runnersDraft, [selectedRunner]: setRunnerField(selectedConfig, field, event.target.checked) })}
                    className="mt-0.5 h-4 w-4 rounded border-black/20 text-foreground"
                  />
                ) : null}
              </label>
              {field.kind !== 'boolean' ? (
                <div className="mt-3">
                  {field.kind === 'select' ? (
                    <select
                      value={String(fieldValue(selectedConfig, field) || '')}
                      onChange={(event) => setRunnersDraft({ ...runnersDraft, [selectedRunner]: setRunnerField(selectedConfig, field, event.target.value) })}
                      className="flex h-11 w-full rounded-[18px] border border-black/[0.08] bg-white/[0.44] px-3 py-2 text-sm dark:border-white/[0.12] dark:bg-white/[0.03]"
                    >
                      {(field.options || []).map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  ) : (
                    <Input
                      value={String(fieldValue(selectedConfig, field) || '')}
                      onChange={(event) => setRunnersDraft({ ...runnersDraft, [selectedRunner]: setRunnerField(selectedConfig, field, event.target.value) })}
                      className="rounded-[18px] border-black/[0.08] bg-white/[0.44] shadow-none dark:bg-white/[0.03]"
                    />
                  )}
                </div>
              ) : null}
            </div>
          ))}
          <div className="md:col-span-2">
            <EnvEditor
              value={asObject(selectedConfig.env)}
              locale={locale}
              onChange={(nextEnv) => setRunnersDraft({ ...runnersDraft, [selectedRunner]: { ...selectedConfig, env: nextEnv } })}
            />
          </div>
          <div className="md:col-span-2">
            <ResultBlock title={t.validation} payload={validation} empty={t.noIssues} />
          </div>
          <div className="md:col-span-2">
            <ResultBlock title={t.testResult} payload={selectedTestItem ? { warnings: selectedTestItem.warnings, errors: selectedTestItem.errors } : null} empty={t.noIssues} />
          </div>
        </div>
      </section>
    </div>
  )
}

export default RunnerSettingsPanel
