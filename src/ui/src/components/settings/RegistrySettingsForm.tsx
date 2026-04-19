import {
  AlertCircle,
  CheckCircle2,
  Cpu,
  Plus,
  Save,
  ServerCog,
  ShieldCheck,
  TestTube2,
  Trash2,
} from 'lucide-react'
import { useMemo } from 'react'

import { Button } from '@/components/ui/button'
import { HintDot } from '@/components/ui/hint-dot'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import type { ConfigTestPayload, ConfigValidationPayload, Locale } from '@/types'

import {
  configSections,
  mcpTransportOptions,
  pluginSections,
  runnerCatalog,
  runnerFields,
  type SettingsField,
  type SettingsFieldKind,
  type SettingsSection,
} from './settingsFormCatalog'
import { translateSettingsCatalogText } from './settingsCatalogI18n'

type ConfigDocumentName = 'config' | 'runners' | 'plugins' | 'mcp_servers'
type StructuredConfig = Record<string, unknown>

const copy = {
  en: {
    save: 'Save',
    saving: 'Saving…',
    validate: 'Check',
    validating: 'Checking…',
    test: 'Test',
    testing: 'Testing…',
    validation: 'Check',
    testResult: 'Test',
    emptyValidation: 'No issues.',
    emptyTest: 'No issues.',
    probeSummary: 'Probe summary',
    resolvedBinary: 'Resolved binary',
    exitCode: 'Exit code',
    stdout: 'Stdout',
    stderr: 'Stderr',
    runnerId: 'Runner ID',
    serverId: 'Server ID',
    connectorsTitle: 'Connectors',
    addRunner: 'Add runner',
    addServer: 'Add server',
    remove: 'Remove',
    ok: 'Ready',
    needsWork: 'Needs work',
    envTitle: 'Environment variables',
    envSubtitle: 'Optional per-entry env overrides.',
    envKey: 'Key',
    envValue: 'Value',
    noServers: 'No external MCP servers yet. Add one card when you need an external namespace.',
    commandList: 'Command',
    argsHint: 'One item per line or comma-separated.',
    stdioNote: 'For `stdio`, fill the command list. For HTTP transports, fill the URL.',
    howToFill: 'How to fill',
    structuredFormHint: 'Structured form editing. Each item explains what it controls and how to fill it.',
    runnerIdHint: 'Stable runner id used in `config.default_runner` and runtime selection.',
    customRunnerEntry: 'Custom runner entry.',
    serverIdHint: 'Stable external MCP namespace id. This is what the runner will see.',
    mcpEnabled: 'Enabled',
    mcpEnabledDesc: 'Only enabled external MCP servers should be exposed to projects or runners.',
    mcpTransport: 'Transport',
    mcpTransportDesc: 'Use `stdio` for local processes and `streamable_http` for remote MCP services.',
    mcpUrl: 'URL',
    mcpUrlDesc: 'Required for HTTP-based transports. Leave empty for pure `stdio` processes.',
    mcpWorkingDirectory: 'Working directory',
    mcpWorkingDirectoryDesc: 'Optional process working directory used when starting a local `stdio` MCP server.',
  },
  zh: {
    save: '保存',
    saving: '保存中…',
    validate: '校验',
    validating: '校验中…',
    test: '测试',
    testing: '测试中…',
    validation: '校验',
    testResult: '测试',
    emptyValidation: '没有问题。',
    emptyTest: '没有问题。',
    probeSummary: '探测摘要',
    resolvedBinary: '实际二进制',
    exitCode: '退出码',
    stdout: '标准输出',
    stderr: '标准错误',
    runnerId: '运行器 ID',
    serverId: '服务 ID',
    connectorsTitle: '连接器',
    addRunner: '新增运行器',
    addServer: '新增服务',
    remove: '删除',
    ok: '就绪',
    needsWork: '需处理',
    envTitle: '环境变量',
    envSubtitle: '按条目覆盖的可选环境变量。',
    envKey: '键',
    envValue: '值',
    noServers: '当前还没有外部 MCP 服务，需要时再新增卡片。',
    commandList: '命令',
    argsHint: '每行一个，或用逗号分隔。',
    stdioNote: '`stdio` 填命令列表；HTTP 类传输填写 URL。',
    howToFill: '填写方式',
    structuredFormHint: '使用结构化表单编辑。每一项都会说明它控制什么，以及应如何填写。',
    runnerIdHint: '稳定的 runner 标识，会被 `config.default_runner` 与运行时选择逻辑使用。',
    customRunnerEntry: '自定义运行器条目。',
    serverIdHint: '稳定的外部 MCP 命名空间 ID。这会是 runner 实际看到的服务标识。',
    mcpEnabled: '启用',
    mcpEnabledDesc: '只有已启用的外部 MCP 服务才会暴露给项目或 runner。',
    mcpTransport: '传输方式',
    mcpTransportDesc: '本地进程使用 `stdio`；远程 MCP 服务使用 `streamable_http`。',
    mcpUrl: '服务 URL',
    mcpUrlDesc: 'HTTP 类传输必须填写；纯 `stdio` 进程可留空。',
    mcpWorkingDirectory: '工作目录',
    mcpWorkingDirectoryDesc: '启动本地 `stdio` MCP 服务时可选使用的进程工作目录。',
  },
} satisfies Record<Locale, Record<string, string>>

function asObject(value: unknown): StructuredConfig {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as StructuredConfig) : {}
}

function fieldValue(config: StructuredConfig, field: SettingsField) {
  const raw = getNestedValue(config, field.key)
  if (field.kind === 'boolean') {
    return Boolean(raw)
  }
  if (field.kind === 'list') {
    return Array.isArray(raw) ? raw.join('\n') : typeof raw === 'string' ? raw : ''
  }
  if (field.kind === 'number') {
    return typeof raw === 'number' ? String(raw) : typeof raw === 'string' ? raw : ''
  }
  return typeof raw === 'string' || typeof raw === 'number' ? String(raw) : ''
}

function normalizeFieldValue(field: SettingsField, value: string | boolean) {
  if (field.kind === 'boolean') {
    return Boolean(value)
  }
  if (field.kind === 'list') {
    return String(value)
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean)
  }
  if (field.kind === 'number') {
    const trimmed = String(value).trim()
    if (!trimmed) {
      return null
    }
    const numeric = Number(trimmed)
    return Number.isFinite(numeric) ? numeric : trimmed
  }
  return String(value)
}

function getNestedValue(source: StructuredConfig, path: string): unknown {
  return path.split('.').reduce<unknown>((current, key) => {
    if (!current || typeof current !== 'object' || Array.isArray(current)) {
      return undefined
    }
    return (current as StructuredConfig)[key]
  }, source)
}

function setNestedValue(source: StructuredConfig, path: string, value: unknown): StructuredConfig {
  const keys = path.split('.')
  const next = { ...source }
  let cursor: StructuredConfig = next
  keys.forEach((key, index) => {
    if (index === keys.length - 1) {
      cursor[key] = value
      return
    }
    const child = asObject(cursor[key])
    cursor[key] = { ...child }
    cursor = cursor[key] as StructuredConfig
  })
  return next
}

function renameMapEntry(source: StructuredConfig, from: string, to: string): StructuredConfig {
  const nextName = to.trim()
  if (!nextName || from === nextName || source[nextName] !== undefined) {
    return source
  }
  const next = { ...source }
  next[nextName] = next[from]
  delete next[from]
  return next
}

function removeMapEntry(source: StructuredConfig, key: string): StructuredConfig {
  const next = { ...source }
  delete next[key]
  return next
}

function nextEntryName(prefix: string, existingKeys: string[]) {
  let index = 1
  let candidate = `${prefix}-${index}`
  while (existingKeys.includes(candidate)) {
    index += 1
    candidate = `${prefix}-${index}`
  }
  return candidate
}

function resultItemByName(payload: ConfigTestPayload | null) {
  const result = new Map<string, NonNullable<ConfigTestPayload['items'][number]>>()
  for (const item of payload?.items || []) {
    result.set(item.name, item)
  }
  return result
}

function ResultNotice({
  title,
  ok,
  warnings,
  errors,
  empty,
}: {
  title: string
  ok: boolean
  warnings: string[]
  errors: string[]
  empty: string
}) {
  return (
    <section className="border-t border-black/[0.08] pt-4 dark:border-white/[0.08]">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium">
        {ok ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <AlertCircle className="h-4 w-4 text-amber-600" />}
        <span>{title}</span>
      </div>
      {errors.length === 0 && warnings.length === 0 ? (
        <div className="text-sm text-muted-foreground">{empty}</div>
      ) : (
        <div className="space-y-2">
          {errors.map((item) => (
            <div key={item} className="border-l-2 border-rose-500/60 pl-3 text-sm text-rose-700 dark:text-rose-300">
              {item}
            </div>
          ))}
          {warnings.map((item) => (
            <div key={item} className="border-l-2 border-amber-500/60 pl-3 text-sm text-amber-700 dark:text-amber-200">
              {item}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function FieldHelp({ field, locale }: { field: SettingsField; locale: Locale }) {
  const t = copy[locale]
  return (
    <div className="space-y-1 text-xs leading-5 text-muted-foreground">
      <div>{translateSettingsCatalogText(locale, field.description)}</div>
      <div>
        <span className="font-medium text-foreground/80">{t.howToFill}:</span>{' '}
        {translateSettingsCatalogText(locale, field.whereToGet)}
      </div>
    </div>
  )
}

function StructuredFieldControl({
  field,
  config,
  locale,
  onChange,
}: {
  field: SettingsField
  config: StructuredConfig
  locale: Locale
  onChange: (key: string, value: unknown) => void
}) {
  const value = fieldValue(config, field)
  const controlClass = 'rounded-[18px] border-black/[0.08] bg-white/[0.44] shadow-none dark:bg-white/[0.03]'

  if (field.kind === 'boolean') {
    return (
      <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
        <label className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-2 text-sm font-medium">
            <span>{translateSettingsCatalogText(locale, field.label)}</span>
            <HintDot
              label={`${translateSettingsCatalogText(locale, field.description)} ${translateSettingsCatalogText(locale, field.whereToGet)}`.trim()}
            />
          </span>
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(event) => onChange(field.key, event.target.checked)}
            className="h-4 w-4 rounded border-black/20 text-foreground"
          />
        </label>
        <div className="mt-3">
          <FieldHelp field={field} locale={locale} />
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
      <label className="mb-2 flex items-center gap-2 text-sm font-medium">
        <span>{translateSettingsCatalogText(locale, field.label)}</span>
        <HintDot
          label={`${translateSettingsCatalogText(locale, field.description)} ${translateSettingsCatalogText(locale, field.whereToGet)}`.trim()}
        />
      </label>
      {field.kind === 'select' ? (
        <select
          value={String(value || '')}
          onChange={(event) => onChange(field.key, normalizeFieldValue(field, event.target.value))}
          className={cn(
            'flex h-11 w-full rounded-[18px] border px-3 py-2 text-sm ring-offset-background transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            controlClass
          )}
        >
          {(field.options || []).map((option) => (
            <option key={option.value} value={option.value}>
              {translateSettingsCatalogText(locale, option.label)}
            </option>
          ))}
        </select>
      ) : field.kind === 'list' ? (
        <Textarea
          value={String(value || '')}
          onChange={(event) => onChange(field.key, normalizeFieldValue(field, event.target.value))}
          placeholder={translateSettingsCatalogText(locale, field.placeholder)}
          className={cn('min-h-[92px] resize-y', controlClass)}
        />
      ) : (
        <Input
          type={field.kind === 'password' ? 'password' : field.kind === 'url' ? 'url' : field.kind === 'number' ? 'number' : 'text'}
          value={String(value || '')}
          onChange={(event) => onChange(field.key, normalizeFieldValue(field, event.target.value))}
          placeholder={translateSettingsCatalogText(locale, field.placeholder)}
          className={controlClass}
        />
      )}
      <div className="mt-3">
        <FieldHelp field={field} locale={locale} />
      </div>
    </div>
  )
}

function SectionBlock({
  section,
  value,
  locale,
  onChange,
}: {
  section: SettingsSection
  value: StructuredConfig
  locale: Locale
  onChange: (key: string, nextValue: unknown) => void
}) {
  return (
    <section className="border-t border-black/[0.08] pt-6 first:border-t-0 first:pt-0 dark:border-white/[0.08]">
      <div className="mb-4">
        <div className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          <span>{translateSettingsCatalogText(locale, section.title)}</span>
          <HintDot label={translateSettingsCatalogText(locale, section.description)} />
        </div>
        <div className="text-sm text-muted-foreground">{translateSettingsCatalogText(locale, section.description)}</div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {section.fields.map((field) => (
          <StructuredFieldControl
            key={field.key}
            field={field}
            config={value}
            locale={locale}
            onChange={onChange}
          />
        ))}
      </div>
    </section>
  )
}

function KeyValueEditor({
  value,
  locale,
  onChange,
}: {
  value: Record<string, unknown>
  locale: Locale
  onChange: (next: Record<string, string>) => void
}) {
  const t = copy[locale]
  const rows = Object.entries(value || {})

  const updateKey = (index: number, nextKey: string) => {
    const nextRows = rows.map(([key, rowValue], rowIndex) =>
      rowIndex === index ? [nextKey, String(rowValue ?? '')] : [key, String(rowValue ?? '')]
    )
    onChange(
      Object.fromEntries(nextRows.filter(([key]) => key.trim()))
    )
  }

  const updateValue = (index: number, nextValue: string) => {
    const nextRows = rows.map(([key, rowValue], rowIndex) =>
      rowIndex === index ? [key, nextValue] : [key, String(rowValue ?? '')]
    )
    onChange(
      Object.fromEntries(nextRows.filter(([key]) => key.trim()))
    )
  }

  const removeRow = (index: number) => {
    const nextRows = rows.filter((_, rowIndex) => rowIndex !== index)
    onChange(Object.fromEntries(nextRows))
  }

  return (
    <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium">
        <span>{t.envTitle}</span>
        <HintDot label={t.envSubtitle} />
      </div>
      <div className="space-y-3">
        {rows.map(([key, rowValue], index) => (
          <div key={`${key}-${index}`} className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
            <Input
              value={key}
              onChange={(event) => updateKey(index, event.target.value)}
              placeholder={t.envKey}
              className="rounded-[18px] border-black/[0.08] bg-white/[0.44] shadow-none dark:bg-white/[0.03]"
            />
            <Input
              value={String(rowValue ?? '')}
              onChange={(event) => updateValue(index, event.target.value)}
              placeholder={t.envValue}
              className="rounded-[18px] border-black/[0.08] bg-white/[0.44] shadow-none dark:bg-white/[0.03]"
            />
            <Button variant="ghost" size="icon" onClick={() => removeRow(index)} aria-label={t.remove}>
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        ))}
        <Button
          variant="secondary"
          onClick={() => onChange({ ...Object.fromEntries(rows), '': '' })}
        >
          <Plus className="h-4 w-4" />
          {t.envTitle}
        </Button>
      </div>
    </div>
  )
}

function RunnerCard({
  runnerName,
  config,
  locale,
  testItem,
  removable,
  onRename,
  onChange,
  onRemove,
}: {
  runnerName: string
  config: StructuredConfig
  locale: Locale
  testItem?: ConfigTestPayload['items'][number]
  removable: boolean
  onRename: (nextName: string) => void
  onChange: (next: StructuredConfig) => void
  onRemove: () => void
}) {
  const t = copy[locale]
  const catalogEntry = runnerCatalog.find((entry) => entry.name === runnerName)

  return (
    <section className="border-t border-black/[0.08] pt-6 dark:border-white/[0.08]">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-[16px] border border-black/[0.08] bg-white/[0.44] dark:border-white/[0.12] dark:bg-white/[0.03]">
              <Cpu className="h-4.5 w-4.5" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-xl font-semibold tracking-tight">{catalogEntry?.label || runnerName}</h3>
                {testItem ? (
                  <span className="text-xs text-muted-foreground">{testItem.ok ? t.ok : t.needsWork}</span>
                ) : null}
              </div>
              <div className="text-sm text-muted-foreground">
                {translateSettingsCatalogText(locale, catalogEntry?.description || t.customRunnerEntry)}
              </div>
            </div>
          </div>
        </div>
        {removable ? (
          <Button variant="ghost" onClick={onRemove}>
            <Trash2 className="h-4 w-4" />
            {t.remove}
          </Button>
        ) : null}
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
          <label className="mb-2 block text-sm font-medium">{t.runnerId}</label>
          <Input
            value={runnerName}
            onChange={(event) => onRename(event.target.value)}
            disabled={!removable}
            className="rounded-[18px] border-black/[0.08] bg-white/[0.44] shadow-none dark:bg-white/[0.03]"
          />
          <div className="mt-3 text-xs text-muted-foreground">{t.runnerIdHint}</div>
        </div>
        {runnerFields.filter((field) => !field.runners || field.runners.includes(runnerName)).map((field) => (
          <StructuredFieldControl
            key={`${runnerName}-${field.key}`}
            field={field}
            config={config}
            locale={locale}
            onChange={(key, value) => onChange({ ...config, [key]: value })}
          />
        ))}
        <div className="md:col-span-2">
          <KeyValueEditor
            value={asObject(config.env)}
            locale={locale}
            onChange={(nextEnv) => onChange({ ...config, env: nextEnv })}
          />
        </div>
        {testItem ? (
          <div className="md:col-span-2 rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
            <div className="mb-3 text-sm font-medium">{t.testResult}</div>
            {testItem.errors.length === 0 && testItem.warnings.length === 0 ? (
              <div className="text-sm text-muted-foreground">{t.emptyTest}</div>
            ) : (
              <div className="space-y-2">
                {testItem.errors.map((item) => (
                  <div key={item} className="border-l-2 border-rose-500/60 pl-3 text-sm text-rose-700 dark:text-rose-300">
                    {item}
                  </div>
                ))}
                {testItem.warnings.map((item) => (
                  <div key={item} className="border-l-2 border-amber-500/60 pl-3 text-sm text-amber-700 dark:text-amber-200">
                    {item}
                  </div>
                ))}
              </div>
            )}
            {typeof testItem.details?.summary === 'string' && testItem.details.summary ? (
              <div className="mt-4 text-sm text-muted-foreground">
                <span className="font-medium text-foreground/80">{t.probeSummary}:</span> {String(testItem.details.summary)}
              </div>
            ) : null}
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              {typeof testItem.details?.resolved_binary === 'string' && testItem.details.resolved_binary ? (
                <div className="text-xs leading-6 text-muted-foreground">
                  <div className="font-medium text-foreground/80">{t.resolvedBinary}</div>
                  <div className="break-all">{String(testItem.details.resolved_binary)}</div>
                </div>
              ) : null}
              {testItem.details?.exit_code !== undefined ? (
                <div className="text-xs leading-6 text-muted-foreground">
                  <div className="font-medium text-foreground/80">{t.exitCode}</div>
                  <div>{String(testItem.details.exit_code)}</div>
                </div>
              ) : null}
              {typeof testItem.details?.stdout_excerpt === 'string' && testItem.details.stdout_excerpt ? (
                <div className="md:col-span-2 text-xs leading-6 text-muted-foreground">
                  <div className="font-medium text-foreground/80">{t.stdout}</div>
                  <pre className="mt-1 overflow-x-auto whitespace-pre-wrap rounded-[16px] border border-black/[0.06] bg-white/[0.4] p-3 dark:border-white/[0.08] dark:bg-white/[0.03]">{String(testItem.details.stdout_excerpt)}</pre>
                </div>
              ) : null}
              {typeof testItem.details?.stderr_excerpt === 'string' && testItem.details.stderr_excerpt ? (
                <div className="md:col-span-2 text-xs leading-6 text-muted-foreground">
                  <div className="font-medium text-foreground/80">{t.stderr}</div>
                  <pre className="mt-1 overflow-x-auto whitespace-pre-wrap rounded-[16px] border border-black/[0.06] bg-white/[0.4] p-3 dark:border-white/[0.08] dark:bg-white/[0.03]">{String(testItem.details.stderr_excerpt)}</pre>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  )
}

function McpServerCard({
  serverName,
  config,
  locale,
  onRename,
  onChange,
  onRemove,
}: {
  serverName: string
  config: StructuredConfig
  locale: Locale
  onRename: (nextName: string) => void
  onChange: (next: StructuredConfig) => void
  onRemove: () => void
}) {
  const t = copy[locale]
  const current = {
    enabled: Boolean(config.enabled),
    transport: typeof config.transport === 'string' && config.transport ? config.transport : 'stdio',
    command: Array.isArray(config.command) ? config.command.join('\n') : typeof config.command === 'string' ? config.command : '',
    url: typeof config.url === 'string' ? config.url : '',
    cwd: typeof config.cwd === 'string' ? config.cwd : '',
  }

  return (
    <section className="border-t border-black/[0.08] pt-6 dark:border-white/[0.08]">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-[16px] border border-black/[0.08] bg-white/[0.44] dark:border-white/[0.12] dark:bg-white/[0.03]">
              <ServerCog className="h-4.5 w-4.5" />
            </div>
            <div className="min-w-0">
              <h3 className="text-xl font-semibold tracking-tight">{serverName}</h3>
              <div className="text-sm text-muted-foreground">{t.stdioNote}</div>
            </div>
          </div>
        </div>
        <Button variant="ghost" onClick={onRemove}>
          <Trash2 className="h-4 w-4" />
          {t.remove}
        </Button>
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
          <label className="mb-2 block text-sm font-medium">{t.serverId}</label>
          <Input
            value={serverName}
            onChange={(event) => onRename(event.target.value)}
            className="rounded-[18px] border-black/[0.08] bg-white/[0.44] shadow-none dark:bg-white/[0.03]"
          />
          <div className="mt-3 text-xs text-muted-foreground">
            {t.serverIdHint}
          </div>
        </div>
        <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
          <label className="flex items-center justify-between gap-4">
            <span className="text-sm font-medium">{t.mcpEnabled}</span>
            <input
              type="checkbox"
              checked={current.enabled}
              onChange={(event) => onChange({ ...config, enabled: event.target.checked })}
              className="h-4 w-4 rounded border-black/20 text-foreground"
            />
          </label>
          <div className="mt-3 text-xs text-muted-foreground">{t.mcpEnabledDesc}</div>
        </div>
        <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
          <label className="mb-2 block text-sm font-medium">{t.mcpTransport}</label>
          <select
            value={current.transport}
            onChange={(event) => onChange({ ...config, transport: event.target.value })}
            className="flex h-11 w-full rounded-[18px] border border-black/[0.08] bg-white/[0.44] px-3 py-2 text-sm dark:border-white/[0.12] dark:bg-white/[0.03]"
          >
            {mcpTransportOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {translateSettingsCatalogText(locale, option.label)}
              </option>
            ))}
          </select>
          <div className="mt-3 text-xs text-muted-foreground">{t.mcpTransportDesc}</div>
        </div>
        <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
          <label className="mb-2 block text-sm font-medium">{t.mcpUrl}</label>
          <Input
            value={current.url}
            onChange={(event) => onChange({ ...config, url: event.target.value })}
            placeholder="https://example.com/mcp"
            className="rounded-[18px] border-black/[0.08] bg-white/[0.44] shadow-none dark:bg-white/[0.03]"
          />
          <div className="mt-3 text-xs text-muted-foreground">{t.mcpUrlDesc}</div>
        </div>
        <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 md:col-span-2 dark:border-white/[0.12] dark:bg-white/[0.04]">
          <label className="mb-2 block text-sm font-medium">{t.commandList}</label>
          <Textarea
            value={current.command}
            onChange={(event) =>
              onChange({
                ...config,
                command: event.target.value
                  .split(/[\n,]/)
                  .map((item) => item.trim())
                  .filter(Boolean),
              })
            }
            placeholder="npx\n@example/browser-mcp"
            className="min-h-[110px] rounded-[18px] border-black/[0.08] bg-white/[0.44] shadow-none dark:bg-white/[0.03]"
          />
          <div className="mt-3 text-xs text-muted-foreground">{t.argsHint}</div>
        </div>
        <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 md:col-span-2 dark:border-white/[0.12] dark:bg-white/[0.04]">
          <label className="mb-2 block text-sm font-medium">{t.mcpWorkingDirectory}</label>
          <Input
            value={current.cwd}
            onChange={(event) => onChange({ ...config, cwd: event.target.value })}
            placeholder="/path/to/working-dir"
            className="rounded-[18px] border-black/[0.08] bg-white/[0.44] shadow-none dark:bg-white/[0.03]"
          />
          <div className="mt-3 text-xs text-muted-foreground">{t.mcpWorkingDirectoryDesc}</div>
        </div>
        <div className="md:col-span-2">
          <KeyValueEditor
            value={asObject(config.env)}
            locale={locale}
            onChange={(nextEnv) => onChange({ ...config, env: nextEnv })}
          />
        </div>
      </div>
    </section>
  )
}

export function RegistrySettingsForm({
  documentName,
  locale,
  value,
  validation,
  testResult,
  saving,
  validating,
  testingAll,
  systemTestable,
  onChange,
  onSave,
  onValidate,
  onTestAll,
}: {
  documentName: ConfigDocumentName
  locale: Locale
  value: StructuredConfig
  validation: ConfigValidationPayload | null
  testResult: ConfigTestPayload | null
  saving: boolean
  validating: boolean
  testingAll: boolean
  systemTestable: boolean
  onChange: (next: StructuredConfig) => void
  onSave: () => void
  onValidate: () => void
  onTestAll: () => void
}) {
  const t = copy[locale]
  const testItems = useMemo(() => resultItemByName(testResult), [testResult])
  const runners = useMemo(() => Object.entries(value).filter(([, entry]) => entry && typeof entry === 'object'), [value])
  const mcpServers = useMemo(() => Object.entries(asObject(value.servers)), [value])

  const renderBody = () => {
    if (documentName === 'config') {
      return configSections.map((section) => (
        <SectionBlock
          key={section.id}
          section={section}
          value={value}
          locale={locale}
          onChange={(key, nextValue) => onChange(setNestedValue(value, key, nextValue))}
        />
      ))
    }

    if (documentName === 'plugins') {
      return pluginSections.map((section) => (
        <SectionBlock
          key={section.id}
          section={section}
          value={value}
          locale={locale}
          onChange={(key, nextValue) => onChange(setNestedValue(value, key, nextValue))}
        />
      ))
    }

    if (documentName === 'runners') {
      return (
        <>
          <div className="flex justify-end">
            <Button
              variant="secondary"
              onClick={() => {
                const nextName = nextEntryName('runner', runners.map(([name]) => name))
                onChange({
                  ...value,
                  [nextName]: {
                    enabled: false,
                    binary: nextName,
                    config_dir: '',
                    model: '',
                    model_reasoning_effort: '',
                    approval_policy: 'never',
                    sandbox_mode: 'danger-full-access',
                    retry_on_failure: true,
                    retry_max_attempts: 7,
                    retry_initial_backoff_sec: 10,
                    retry_backoff_multiplier: 6,
                    retry_max_backoff_sec: 1800,
                    env: {},
                  },
                })
              }}
            >
              <Plus className="h-4 w-4" />
              {t.addRunner}
            </Button>
          </div>
          {runners.map(([runnerName, runnerConfig]) => (
            <RunnerCard
              key={runnerName}
              runnerName={runnerName}
              config={asObject(runnerConfig)}
              locale={locale}
              testItem={testItems.get(runnerName)}
              removable={!runnerCatalog.some((entry) => entry.name === runnerName)}
              onRename={(nextName) => onChange(renameMapEntry(value, runnerName, nextName))}
              onChange={(nextConfig) => onChange({ ...value, [runnerName]: nextConfig })}
              onRemove={() => onChange(removeMapEntry(value, runnerName))}
            />
          ))}
        </>
      )
    }

    if (documentName === 'mcp_servers') {
      return (
        <>
          <div className="flex justify-end">
            <Button
              variant="secondary"
              onClick={() => {
                const servers = asObject(value.servers)
                const nextName = nextEntryName('server', Object.keys(servers))
                onChange({
                  ...value,
                  servers: {
                    ...servers,
                    [nextName]: {
                      enabled: false,
                      transport: 'stdio',
                      command: [],
                      url: '',
                      cwd: '',
                      env: {},
                    },
                  },
                })
              }}
            >
              <Plus className="h-4 w-4" />
              {t.addServer}
            </Button>
          </div>
          {mcpServers.length === 0 ? <div className="text-sm text-muted-foreground">{t.noServers}</div> : null}
          {mcpServers.map(([serverName, serverConfig]) => (
            <McpServerCard
              key={serverName}
              serverName={serverName}
              config={asObject(serverConfig)}
              locale={locale}
              onRename={(nextName) =>
                onChange({
                  ...value,
                  servers: renameMapEntry(asObject(value.servers), serverName, nextName),
                })
              }
              onChange={(nextConfig) =>
                onChange({
                  ...value,
                  servers: {
                    ...asObject(value.servers),
                    [serverName]: nextConfig,
                  },
                })
              }
              onRemove={() =>
                onChange({
                  ...value,
                  servers: removeMapEntry(asObject(value.servers), serverName),
                })
              }
            />
          ))}
        </>
      )
    }

    return null
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-4 border-b border-black/[0.08] pb-5 lg:flex-row lg:items-start lg:justify-between dark:border-white/[0.08]">
        <div className="text-sm text-muted-foreground">{t.structuredFormHint}</div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={onSave} disabled={saving}>
            <Save className="h-4 w-4" />
            {saving ? t.saving : t.save}
          </Button>
          <Button variant="secondary" onClick={onValidate} disabled={validating}>
            <ShieldCheck className="h-4 w-4" />
            {validating ? t.validating : t.validate}
          </Button>
          {systemTestable ? (
            <Button variant="secondary" onClick={onTestAll} disabled={testingAll}>
              <TestTube2 className="h-4 w-4" />
              {testingAll ? t.testing : t.test}
            </Button>
          ) : null}
        </div>
      </header>

      <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_260px]">
        <div className="space-y-8">{renderBody()}</div>

        <aside className="space-y-0 xl:border-l xl:border-black/[0.08] xl:pl-6 xl:dark:border-white/[0.08]">
          <ResultNotice
            title={t.validation}
            ok={validation?.ok ?? true}
            warnings={validation?.warnings || []}
            errors={validation?.errors || []}
            empty={t.emptyValidation}
          />
          {systemTestable ? (
            <ResultNotice
              title={t.testResult}
              ok={testResult?.ok ?? true}
              warnings={testResult?.warnings || []}
              errors={testResult?.errors || []}
              empty={t.emptyTest}
            />
          ) : null}
        </aside>
      </div>
    </div>
  )
}
