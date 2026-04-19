import { ChevronDown, Loader2, Search } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { MarkdownDocument } from '@/components/plugins/MarkdownDocument'
import { ProjectsAppBar } from '@/components/projects/ProjectsAppBar'
import { BaselineSettingsPanel } from '@/components/settings/BaselineSettingsPanel'
import { ConnectorSettingsForm } from '@/components/settings/ConnectorSettingsForm'
import { DeepXivSettingsPanel } from '@/components/settings/DeepXivSettingsPanel'
import { connectorCatalog, type ConnectorName } from '@/components/settings/connectorCatalog'
import { connectorConfigAutoEnabled } from '@/components/settings/connectorSettingsHelpers'
// TODO(upstream ea21104): the following sections were imported but never added
// to the tree. Re-enable once the component files land.
// import { SettingsConnectorHealthSection } from '@/components/settings/SettingsConnectorHealthSection'
// import { SettingsControllersSection } from '@/components/settings/SettingsControllersSection'
// import { SettingsDiagnosticsSection } from '@/components/settings/SettingsDiagnosticsSection'
// import { SettingsErrorsSection } from '@/components/settings/SettingsErrorsSection'
// import { SettingsIssueReportSection } from '@/components/settings/SettingsIssueReportSection'
// import { SettingsLogsSection } from '@/components/settings/SettingsLogsSection'
// import { SettingsOpsLauncher, SettingsOpsRail } from '@/components/settings/SettingsOpsRail'
// import { SettingsQuestDetailSection } from '@/components/settings/SettingsQuestDetailSection'
// import { SettingsQuestsSection } from '@/components/settings/SettingsQuestsSection'
// import { SettingsRepairsSection } from '@/components/settings/SettingsRepairsSection'
// import { SettingsRuntimeSection } from '@/components/settings/SettingsRuntimeSection'
// import { SettingsSearchSection } from '@/components/settings/SettingsSearchSection'
// import { SettingsSummarySection } from '@/components/settings/SettingsSummarySection'
// import { SettingsStatsSection } from '@/components/settings/SettingsStatsSection'
import { RunnerSettingsPanel } from '@/components/settings/RunnerSettingsPanel'
import { RegistrySettingsForm } from '@/components/settings/RegistrySettingsForm'
import { translateSettingsCatalogText, translateSettingsHelpMarkdown } from '@/components/settings/settingsCatalogI18n'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { HintDot } from '@/components/ui/hint-dot'
import { Input } from '@/components/ui/input'
import { client } from '@/lib/api'
import { useAdminOpsStore } from '@/lib/stores/admin-ops'
import { cn } from '@/lib/utils'
import type {
  BaselineRegistryEntry,
  ConfigFileEntry,
  ConfigTestPayload,
  ConfigValidationPayload,
  ConnectorSnapshot,
  Locale,
  OpenDocumentPayload,
  QuestSummary,
} from '@/types'

export type ConfigDocumentName = 'config' | 'runners' | 'connectors' | 'baselines' | 'plugins' | 'mcp_servers'
export type SettingsSectionName =
  | ConfigDocumentName
  | 'summary'
  | 'runtime'
  | 'deepxiv'
  | 'connectors_health'
  | 'diagnostics'
  | 'errors'
  | 'issues'
  | 'logs'
  | 'quests'
  | 'repairs'
  | 'controllers'
  | 'stats'
  | 'search'

const CONFIG_ORDER: ConfigDocumentName[] = ['config', 'runners', 'connectors', 'baselines', 'plugins', 'mcp_servers']
const OPERATIONS_ORDER: Array<
  Extract<
    SettingsSectionName,
    'summary' | 'runtime' | 'connectors_health' | 'diagnostics' | 'errors' | 'issues' | 'logs' | 'quests' | 'repairs' | 'controllers' | 'stats' | 'search'
  >
> = ['summary', 'runtime', 'connectors_health', 'diagnostics', 'errors', 'issues', 'logs', 'quests', 'repairs', 'controllers', 'stats', 'search']

const CONFIG_META = {
  config: {
    label: { en: 'Runtime', zh: '运行时' },
    hint: { en: 'Home paths, git, logging, and daemon defaults.', zh: '主目录路径、git、日志与 daemon 默认设置。' },
  },
  runners: {
    label: { en: 'Models', zh: '运行器' },
    hint: { en: 'Runner selection, model defaults, and execution policy.', zh: '运行器选择、模型默认值与执行策略。' },
  },
  connectors: {
    label: { en: 'Connectors', zh: '连接器' },
    hint: {
      en: 'Native connector transports, discovered runtime targets, and legacy callback fallbacks.',
      zh: '原生连接器传输方式、运行时发现目标，以及旧式回调兜底配置。',
    },
  },
  baselines: {
    label: { en: 'Baselines', zh: '基线' },
    hint: {
      en: 'Reusable baseline registry entries and lifecycle management.',
      zh: '可复用基线条目及其生命周期管理。',
    },
  },
  plugins: {
    label: { en: 'Extensions', zh: '扩展' },
    hint: { en: 'Optional plugins and local extension discovery.', zh: '可选插件与本地扩展发现。' },
  },
  mcp_servers: {
    label: { en: 'MCP', zh: 'MCP' },
    hint: { en: 'External MCP servers and access policy.', zh: '外部 MCP 服务与访问策略。' },
  },
} satisfies Record<ConfigDocumentName, { label: Record<Locale, string>; hint: Record<Locale, string> }>

const OPERATIONS_META = {
  summary: {
    label: { en: 'Summary', zh: '摘要' },
    hint: { en: 'System summary, hardware state, and quick operator actions.', zh: '系统摘要、硬件状态与快捷运维动作。' },
  },
  runtime: {
    label: { en: 'Sessions & Hardware', zh: '会话与硬件' },
    hint: { en: 'Hardware details, GPU selection, and bash_exec session evidence.', zh: '硬件详情、GPU 选择，以及 bash_exec 会话证据。' },
  },
  connectors_health: {
    label: { en: 'Connector Health', zh: '连接器健康' },
    hint: { en: 'Inspect runtime connector state, bindings, and discovered targets.', zh: '检查运行时连接器状态、绑定关系与已发现目标。' },
  },
  diagnostics: {
    label: { en: 'Diagnostics', zh: '诊断' },
    hint: { en: 'Manual diagnosis, failures, and runtime tool visibility.', zh: '手动诊断、失败信息与运行时工具可见性。' },
  },
  errors: {
    label: { en: 'Errors', zh: '错误' },
    hint: { en: 'Merged runtime failures, daemon errors, and degraded connector state.', zh: '汇总运行时失败、daemon 错误与连接器退化状态。' },
  },
  issues: {
    label: { en: 'Issue Report', zh: '问题报告' },
    hint: { en: 'Generate a prefilled GitHub issue from local runtime evidence and submit it quickly.', zh: '基于本地运行时证据生成预填好的 GitHub issue，并快速提交。' },
  },
  logs: {
    label: { en: 'Logs', zh: '日志' },
    hint: { en: 'Inspect whitelisted daemon, connector, and quest log tails.', zh: '查看白名单 daemon、connector 与 quest 日志 tail。' },
  },
  quests: {
    label: { en: 'Quests', zh: 'Quests' },
    hint: { en: 'Filter, inspect, and control quests from one system table.', zh: '在统一系统表里筛选、检查并控制 quests。' },
  },
  repairs: {
    label: { en: 'Repairs', zh: '修复' },
    hint: { en: 'Manage repair sessions and reopen them in Copilot.', zh: '管理修复会话，并在 Copilot 中重新打开。' },
  },
  controllers: {
    label: { en: 'Controllers', zh: '控制器' },
    hint: { en: 'Run and enable built-in governance controllers.', zh: '运行并启用内建治理控制器。' },
  },
  stats: {
    label: { en: 'Stats', zh: '统计' },
    hint: { en: 'Compact distributions for quests, anchors, modes, and runners.', zh: '查看 quests、阶段、模式与 runner 的分布。' },
  },
  search: {
    label: { en: 'Search', zh: '搜索' },
    hint: { en: 'Search across quest summaries and recent event summaries.', zh: '跨 quest 摘要与最近事件摘要搜索。' },
  },
} satisfies Record<
  Exclude<SettingsSectionName, ConfigDocumentName>,
  { label: Record<Locale, string>; hint: Record<Locale, string> }
>

const SPECIAL_META = {
  deepxiv: {
    label: { en: 'DeepXiv', zh: 'DeepXiv' },
    hint: {
      en: 'Configure the DeepXiv literature provider, guided registration screenshot, and prompt gating behavior.',
      zh: '配置 DeepXiv 文献能力、引导式注册截图，以及 prompt 的启用 / 禁用规则。',
    },
  },
} satisfies Record<'deepxiv', { label: Record<Locale, string>; hint: Record<Locale, string> }>

const copy = {
  en: {
    title: 'Settings',
    files: 'Settings',
    admin: 'Admin',
    adminHint: 'Operational diagnostics, supervision, and repair surfaces.',
    copilot: 'Admin Copilot',
    openCopilot: 'Open Fresh Copilot',
    closeCopilot: 'Close Copilot',
    search: 'Search',
    noFile: 'Pick a category.',
    saved: 'Saved.',
    noHealth: 'No connector snapshot.',
    daemon: 'Daemon',
    connectors: 'Connectors',
    enabled: 'Enabled',
    idle: 'Idle',
    dirty: 'Dirty',
    check: 'Check',
    reference: 'Notes',
    loading: 'Loading',
    qqAutoBound: 'QQ openid detected and saved automatically.',
    connectorDeleted: 'Connector profile deleted.',
    connectorBindingSaved: 'Connector binding updated.',
    baselineDeleted: 'Baseline deleted.',
    literatureTools: 'Literature tools',
  },
  zh: {
    title: '设置',
    files: '设置',
    admin: '管理',
    adminHint: '运维诊断、监管与修复相关页面。',
    copilot: 'Admin Copilot',
    openCopilot: '打开全新 Copilot',
    closeCopilot: '关闭 Copilot',
    search: '搜索',
    noFile: '选择一个分类。',
    saved: '已保存。',
    noHealth: '暂无连接器快照。',
    daemon: '守护进程',
    connectors: '连接器',
    enabled: '已启用',
    idle: '空闲',
    dirty: '未保存',
    check: '校验',
    reference: '说明',
    loading: '加载中',
    qqAutoBound: '已自动检测并保存 QQ openid。',
    connectorDeleted: '已删除该 Connector。',
    connectorBindingSaved: '已更新该 Connector 绑定。',
    baselineDeleted: '已删除该 baseline。',
    literatureTools: '文献工具',
  },
} satisfies Record<Locale, Record<string, string>>

const SYNTHETIC_BASELINE_FILE: ConfigFileEntry = {
  name: 'baselines',
  path: 'config/baselines',
  required: false,
  exists: true,
}

function compareConfig(a: ConfigFileEntry, b: ConfigFileEntry) {
  return CONFIG_ORDER.indexOf(a.name as ConfigDocumentName) - CONFIG_ORDER.indexOf(b.name as ConfigDocumentName)
}

function configLabel(name: ConfigDocumentName, locale: Locale) {
  return CONFIG_META[name].label[locale]
}

function sectionLabel(name: SettingsSectionName, locale: Locale) {
  if (name in OPERATIONS_META) {
    return OPERATIONS_META[name as keyof typeof OPERATIONS_META].label[locale]
  }
  if (name in SPECIAL_META) {
    return SPECIAL_META[name as keyof typeof SPECIAL_META].label[locale]
  }
  return configLabel(name as ConfigDocumentName, locale)
}

function connectorBindingTransitionMessage(transition: unknown, questId?: string | null, locale: Locale = 'en') {
  if (!transition || typeof transition !== 'object') {
    return locale === 'zh' ? copy.zh.connectorBindingSaved : copy.en.connectorBindingSaved
  }
  const payload = transition as Record<string, unknown>
  const mode = String(payload.mode || '').trim().toLowerCase()
  const previousLabel = String(payload.previous_label || '').trim()
  const currentLabel = String(payload.current_label || '').trim()
  const resolvedQuestId = String(questId || payload.quest_id || '').trim()
  if (locale === 'zh') {
    if (mode === 'switch' && previousLabel && currentLabel && resolvedQuestId) {
      return `已将 ${resolvedQuestId} 从 ${previousLabel} 切换到 ${currentLabel}。`
    }
    if (mode === 'bind' && currentLabel && resolvedQuestId) {
      return `已将 ${resolvedQuestId} 绑定到 ${currentLabel}。`
    }
    if (mode === 'disconnect' && resolvedQuestId) {
      return `${resolvedQuestId} 已切换为仅本地。`
    }
    return copy.zh.connectorBindingSaved
  }
  if (mode === 'switch' && previousLabel && currentLabel && resolvedQuestId) {
    return `Switched ${resolvedQuestId} from ${previousLabel} to ${currentLabel}.`
  }
  if (mode === 'bind' && currentLabel && resolvedQuestId) {
    return `Bound ${resolvedQuestId} to ${currentLabel}.`
  }
  if (mode === 'disconnect' && resolvedQuestId) {
    return `${resolvedQuestId} is now local only.`
  }
  return copy.en.connectorBindingSaved
}

function configHint(name: ConfigDocumentName, locale: Locale) {
  return CONFIG_META[name].hint[locale]
}

function sectionHint(name: SettingsSectionName, locale: Locale) {
  if (name in OPERATIONS_META) {
    return OPERATIONS_META[name as keyof typeof OPERATIONS_META].hint[locale]
  }
  if (name in SPECIAL_META) {
    return SPECIAL_META[name as keyof typeof SPECIAL_META].hint[locale]
  }
  return configHint(name as ConfigDocumentName, locale)
}

function normalizeHashAnchor(value?: string | null) {
  return String(value || '')
    .trim()
    .replace(/^#/, '')
}

function settingsConfigPath(name: SettingsSectionName | null, connectorName?: ConnectorName | null) {
  if (!name) {
    return '/settings'
  }
  if (name === 'summary') {
    return '/settings/summary'
  }
  if (name === 'runtime') {
    return '/settings/runtime'
  }
  if (name === 'deepxiv') {
    return '/settings/deepxiv'
  }
  if (name === 'connectors_health') return '/settings/connectors-health'
  if (name === 'diagnostics') return '/settings/diagnostics'
  if (name === 'errors') return '/settings/errors'
  if (name === 'issues') return '/settings/issues'
  if (name === 'logs') return '/settings/logs'
  if (name === 'quests') return '/settings/quests'
  if (name === 'repairs') return '/settings/repairs'
  if (name === 'controllers') return '/settings/controllers'
  if (name === 'stats') return '/settings/stats'
  if (name === 'search') return '/settings/search'
  if (name === 'connectors') {
    return connectorName ? `/settings/connector/${connectorName}` : '/settings/connector'
  }
  return name ? `/settings/${name}` : '/settings'
}

function connectorNameFromAnchor(anchorId: string): ConnectorName | null {
  const normalized = normalizeHashAnchor(anchorId)
  const match = /^connector-(qq|weixin|telegram|discord|slack|feishu|whatsapp|lingzhu)(?:$|-)/.exec(normalized)
  return (match?.[1] as ConnectorName | undefined) ?? null
}

function scrollSettingsAnchor(root: HTMLElement | null, anchorId: string) {
  if (!root || !anchorId) {
    return false
  }
  const target = root.querySelector<HTMLElement>(`#${CSS.escape(anchorId)}`)
  if (!target) {
    return false
  }
  const top =
    root.scrollTop +
    target.getBoundingClientRect().top -
    root.getBoundingClientRect().top -
    16
  root.scrollTo({ top: Math.max(top, 0), behavior: 'smooth' })
  return true
}

function qqMainChatSignature(value: unknown) {
  if (!value || typeof value !== 'object') {
    return ''
  }
  const payload = value as Record<string, unknown>
  const directMainChatId = String(payload.main_chat_id || '').trim()
  const profileChatIds = Array.isArray(payload.profiles)
    ? payload.profiles
        .filter((item) => item && typeof item === 'object')
        .map((item) => {
          const profile = item as Record<string, unknown>
          return `${String(profile.profile_id || '').trim()}:${String(profile.main_chat_id || '').trim()}`
        })
        .filter((item) => item !== ':')
        .sort()
    : []
  return [directMainChatId, ...profileChatIds].filter(Boolean).join('|')
}

export function SettingsPage({
  requestedConfigName,
  requestedConnectorName,
  requestedQuestId,
  onRequestedConfigConsumed,
  runtimeAddress,
  locale,
}: {
  requestedConfigName?: SettingsSectionName | null
  requestedConnectorName?: ConnectorName | null
  requestedQuestId?: string | null
  onRequestedConfigConsumed?: () => void
  runtimeAddress: string
  locale: Locale
}) {
  const t = copy[locale]
  const location = useLocation()
  const navigate = useNavigate()
  const dockOpen = useAdminOpsStore((state) => state.dockOpen)
  const closeDock = useAdminOpsStore((state) => state.closeDock)
  const startFreshSession = useAdminOpsStore((state) => state.startFreshSession)
  const activeRepair = useAdminOpsStore((state) => state.activeRepair)
  const resetContext = useAdminOpsStore((state) => state.resetContext)
  const [files, setFiles] = useState<ConfigFileEntry[]>([])
  const [connectors, setConnectors] = useState<ConnectorSnapshot[]>([])
  const [baselineEntries, setBaselineEntries] = useState<BaselineRegistryEntry[]>([])
  const [quests, setQuests] = useState<QuestSummary[]>([])
  const [selectedName, setSelectedName] = useState<SettingsSectionName | null>(requestedConfigName || null)
  const [adminExpanded, setAdminExpanded] = useState(Boolean(requestedConfigName && requestedConfigName in OPERATIONS_META))
  const [document, setDocument] = useState<OpenDocumentPayload | null>(null)
  const [structuredDraft, setStructuredDraft] = useState<Record<string, unknown>>({})
  const [loading, setLoading] = useState(true)
  const [documentLoading, setDocumentLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [validating, setValidating] = useState(false)
  const [testingAll, setTestingAll] = useState(false)
  const [deletingProfileKey, setDeletingProfileKey] = useState('')
  const [deletingBaselineId, setDeletingBaselineId] = useState('')
  const [bindingProfileKey, setBindingProfileKey] = useState('')
  const [validation, setValidation] = useState<ConfigValidationPayload | null>(null)
  const [testResult, setTestResult] = useState<ConfigTestPayload | null>(null)
  const [saveMessage, setSaveMessage] = useState('')
  const [search, setSearch] = useState('')
  const lastKnownQqMainChatIdRef = useRef('')
  const contentRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    let mounted = true
    const load = async () => {
      setLoading(true)
      try {
        const [filePayload, connectorPayload, baselinePayload, questPayload] = await Promise.all([
          client.configFiles(),
          client.connectors(),
          client.baselines(),
          client.quests(),
        ])
        if (!mounted) {
          return
        }
        const sorted = [...filePayload].sort(compareConfig)
        setFiles([...sorted, SYNTHETIC_BASELINE_FILE].sort(compareConfig))
        setConnectors(connectorPayload)
        setBaselineEntries(baselinePayload)
        setQuests(questPayload)
        const preferred = requestedConfigName || (sorted[0]?.name as ConfigDocumentName | undefined) || null
        if (preferred) {
          setSelectedName(preferred)
        }
      } finally {
        if (mounted) {
          setLoading(false)
        }
      }
    }
    void load()
    return () => {
      mounted = false
    }
  }, [requestedConfigName])

  useEffect(() => {
    if (!selectedName) {
      setDocument(null)
      setStructuredDraft({})
      setDocumentLoading(false)
      return
    }
    if ((selectedName && selectedName in OPERATIONS_META) || selectedName === 'baselines' || selectedName === 'deepxiv' || selectedName === 'runners') {
      setDocument(null)
      setStructuredDraft({})
      setValidation(null)
      setTestResult(null)
      setSaveMessage('')
      setDocumentLoading(false)
      return
    }
    let mounted = true
    setDocumentLoading(true)
    setDocument(null)
    setStructuredDraft({})
    setValidation(null)
    setTestResult(null)
    setSaveMessage('')
    const load = async () => {
      try {
        const next = await client.configDocument(selectedName)
        if (!mounted) {
          return
        }
        setDocument(next)
        setStructuredDraft(
          next.meta?.structured_config && typeof next.meta.structured_config === 'object'
            ? (next.meta.structured_config as Record<string, unknown>)
            : {}
        )
      } finally {
        if (mounted) {
          setDocumentLoading(false)
        }
      }
    }
    void load()
    return () => {
      mounted = false
    }
  }, [selectedName])

  useEffect(() => {
    if (!requestedConfigName) {
      return
    }
    setSelectedName(requestedConfigName)
    if (requestedConfigName in OPERATIONS_META) {
      setAdminExpanded(true)
    }
    onRequestedConfigConsumed?.()
  }, [onRequestedConfigConsumed, requestedConfigName])

  const isPageLoading = loading || documentLoading
  const isConnectorDocument = selectedName === 'connectors'
  const isBaselineDocument = selectedName === 'baselines'
  const isOperationSection = Boolean(selectedName && selectedName in OPERATIONS_META)
  const visibleConnectorNames = useMemo(
    () => new Set(connectors.filter((item) => item.name !== 'local').map((item) => item.name as ConnectorName)),
    [connectors]
  )
  const visibleConnectorEntries = useMemo(
    () => connectorCatalog.filter((entry) => visibleConnectorNames.has(entry.name)),
    [visibleConnectorNames]
  )
  const selectedConnectorName =
    isConnectorDocument && requestedConnectorName && visibleConnectorNames.has(requestedConnectorName)
      ? requestedConnectorName
      : null
  const isDirty = Boolean(
    document && JSON.stringify(document.meta?.structured_config || {}) !== JSON.stringify(structuredDraft)
  )
  const selectedAnchorId = selectedName ? `settings-${selectedName}` : ''

  useEffect(() => {
    if (activeRepair) {
      return
    }
    resetContext(location.pathname || '/settings')
  }, [activeRepair, location.pathname, resetContext])

  useEffect(() => {
    if (selectedName !== 'connectors' || selectedConnectorName !== 'qq') {
      lastKnownQqMainChatIdRef.current = ''
      return
    }

    let cancelled = false
    const poll = async () => {
      try {
        const connectorPayload = await client.connectors()
        if (cancelled) {
          return
        }
        setConnectors(connectorPayload)

        if (isDirty) {
          return
        }

        const next = await client.configDocument('connectors')
        if (cancelled) {
          return
        }
        const nextStructured =
          next.meta?.structured_config && typeof next.meta.structured_config === 'object'
            ? (next.meta.structured_config as Record<string, unknown>)
            : {}
        const nextQq =
          nextStructured.qq && typeof nextStructured.qq === 'object'
            ? (nextStructured.qq as Record<string, unknown>)
            : {}
        const nextMainChatSignature = qqMainChatSignature(nextQq)

        if (next.revision !== document?.revision || nextMainChatSignature !== lastKnownQqMainChatIdRef.current) {
          setDocument(next)
          setStructuredDraft(nextStructured)
          if (!lastKnownQqMainChatIdRef.current && nextMainChatSignature) {
            setSaveMessage(t.qqAutoBound)
          }
          lastKnownQqMainChatIdRef.current = nextMainChatSignature
        }
      } catch {
        return
      }
    }

    const currentQq =
      structuredDraft.qq && typeof structuredDraft.qq === 'object'
        ? (structuredDraft.qq as Record<string, unknown>)
        : {}
    lastKnownQqMainChatIdRef.current = qqMainChatSignature(currentQq)

    void poll()
    const timer = window.setInterval(() => {
      void poll()
    }, 10000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [document?.revision, isDirty, selectedConnectorName, selectedName, structuredDraft.qq, t.qqAutoBound])

  useEffect(() => {
    const anchorId = normalizeHashAnchor(location.hash)
    if (!anchorId || isPageLoading || !selectedName) {
      return
    }
    let cancelled = false
    const attemptScroll = (attempt: number) => {
      if (cancelled) {
        return
      }
      if (scrollSettingsAnchor(contentRef.current, anchorId)) {
        return
      }
      if (attempt < 12) {
        window.setTimeout(() => attemptScroll(attempt + 1), 80)
      }
    }
    window.setTimeout(() => attemptScroll(0), 0)
    return () => {
      cancelled = true
    }
  }, [document?.revision, isPageLoading, location.hash, selectedName])

  useEffect(() => {
    if (loading) {
      return
    }
    if (!isConnectorDocument || !requestedConnectorName) {
      return
    }
    if (visibleConnectorNames.has(requestedConnectorName)) {
      return
    }
    navigate(
      {
        pathname: settingsConfigPath('connectors'),
        hash: '',
      },
      { replace: true }
    )
  }, [isConnectorDocument, loading, navigate, requestedConnectorName, visibleConnectorNames])

  useEffect(() => {
    if (!isConnectorDocument || selectedConnectorName) {
      return
    }
    const anchorConnectorName = connectorNameFromAnchor(location.hash)
    if (!anchorConnectorName) {
      return
    }
    if (!visibleConnectorNames.has(anchorConnectorName)) {
      navigate(
        {
          pathname: settingsConfigPath('connectors'),
          hash: '',
        },
        { replace: true }
      )
      return
    }
    navigate(
      {
        pathname: settingsConfigPath('connectors', anchorConnectorName),
        hash: location.hash,
      },
      { replace: true }
    )
  }, [isConnectorDocument, location.hash, navigate, selectedConnectorName, visibleConnectorNames])

  const handleSelectSection = (name: SettingsSectionName) => {
    setSelectedName(name)
    setSaveMessage('')
    navigate(
      {
        pathname: settingsConfigPath(name),
        hash: '',
      },
      { replace: location.pathname === settingsConfigPath(name) }
    )
  }

  const filteredFiles = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    if (!keyword) {
      return files
    }
    return files.filter((item) => {
      const name = item.name as ConfigDocumentName
      return `${item.name} ${item.path} ${configLabel(name, locale)} ${configHint(name, locale)}`
        .toLowerCase()
        .includes(keyword)
    })
  }, [files, locale, search])

  const filteredOperations = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    const operations = OPERATIONS_ORDER.map((name) => ({ name, label: sectionLabel(name, locale), hint: sectionHint(name, locale) }))
    if (!keyword) {
      return operations
    }
    return operations.filter((item) => `${item.name} ${item.label} ${item.hint}`.toLowerCase().includes(keyword))
  }, [locale, search])

  useEffect(() => {
    if (isOperationSection || (search.trim() && filteredOperations.length > 0)) {
      setAdminExpanded(true)
    }
  }, [filteredOperations.length, isOperationSection, search])

  const adminNavItems = useMemo(
    () => OPERATIONS_ORDER.map((name) => ({ name, label: sectionLabel(name, locale), hint: sectionHint(name, locale) })),
    [locale]
  )

  const selectedMeta =
    selectedName && selectedName in OPERATIONS_META
      ? OPERATIONS_META[selectedName as keyof typeof OPERATIONS_META]
      : selectedName && selectedName in SPECIAL_META
        ? SPECIAL_META[selectedName as keyof typeof SPECIAL_META]
        : selectedName
          ? CONFIG_META[selectedName as ConfigDocumentName]
          : null
  const helpMarkdown = translateSettingsHelpMarkdown(
    locale,
    typeof document?.meta?.help_markdown === 'string' ? document.meta.help_markdown : ''
  )

  const structuredConnectors = useMemo(
    () => (isConnectorDocument ? (structuredDraft as Record<string, Record<string, unknown>>) : {}),
    [isConnectorDocument, structuredDraft]
  )
  const setStructuredConnectors = (next: Record<string, Record<string, unknown>>) => {
    setStructuredDraft(next as Record<string, unknown>)
  }

  const jumpToAnchor = (anchorId: string) => {
    if (!selectedName || !anchorId) {
      return
    }
    const nextConnectorName =
      selectedName === 'connectors'
        ? selectedConnectorName || connectorNameFromAnchor(anchorId)
        : null
    navigate(
      {
        pathname: settingsConfigPath(selectedName, nextConnectorName),
        hash: `#${anchorId}`,
      },
      { replace: false }
    )
    window.setTimeout(() => {
      scrollSettingsAnchor(contentRef.current, anchorId)
    }, 0)
  }

  const connectorSummary = useMemo(() => {
    const snapshotByName = new Map(connectors.map((item) => [item.name, item]))
    return visibleConnectorEntries.map((entry) => {
      const configured = structuredDraft[entry.name]
      const configEnabled =
        configured && typeof configured === 'object'
          ? connectorConfigAutoEnabled(entry.name, configured as Record<string, unknown>)
          : false
      const snapshot = snapshotByName.get(entry.name)
      return {
        name: entry.name,
        label: translateSettingsCatalogText(locale, entry.label),
        enabled: selectedName === 'connectors' ? configEnabled : Boolean(snapshot?.enabled),
      }
    })
  }, [connectors, locale, selectedName, structuredDraft, visibleConnectorEntries])

  const refreshSelected = async () => {
    if (!selectedName) {
      return
    }
    if (selectedName === 'baselines') {
      setBaselineEntries(await client.baselines())
      return
    }
    const next = await client.configDocument(selectedName)
    setDocument(next)
    setStructuredDraft(
      next.meta?.structured_config && typeof next.meta.structured_config === 'object'
        ? (next.meta.structured_config as Record<string, unknown>)
        : {}
    )
  }

  const runValidate = async () => {
    if (!selectedName) {
      return
    }
    setValidating(true)
    try {
      setValidation(await client.validateConfig(selectedName, { structured: structuredDraft }))
    } finally {
      setValidating(false)
    }
  }

  const runTestAll = async () => {
    if (!selectedName) {
      return
    }
    setTestingAll(true)
    try {
      setTestResult(await client.testConfig(selectedName, { structured: structuredDraft, live: true }))
    } finally {
      setTestingAll(false)
    }
  }

  const handleSave = async (draftOverride?: Record<string, unknown>) => {
    if (!selectedName || !document) {
      return false
    }
    setSaving(true)
    try {
      const effectiveDraft = draftOverride ?? structuredDraft
      const nextStructuredDraft =
        selectedName === 'config'
          ? {
              ...effectiveDraft,
              bootstrap: {
                ...(effectiveDraft.bootstrap && typeof effectiveDraft.bootstrap === 'object'
                  ? (effectiveDraft.bootstrap as Record<string, unknown>)
                  : {}),
                locale_source: 'user',
              },
            }
          : effectiveDraft
      const result = await client.saveConfig(
        selectedName,
        { structured: nextStructuredDraft, revision: document.revision }
      )
      if (result.ok) {
        setSaveMessage(t.saved)
        await refreshSelected()
        setConnectors(await client.connectors())
        return true
      } else {
        setSaveMessage('')
        return false
      }
    } finally {
      setSaving(false)
    }
  }

  const refreshConnectorSettings = async () => {
    await refreshSelected()
    setConnectors(await client.connectors())
  }

  const handleDeleteConnectorProfile = async (connectorName: ConnectorName, profileId: string) => {
    setDeletingProfileKey(`${connectorName}:${profileId}`)
    try {
      await client.deleteConnectorProfile(connectorName, profileId)
      setSaveMessage(t.connectorDeleted)
      await refreshSelected()
      const [connectorPayload, questPayload] = await Promise.all([client.connectors(), client.quests()])
      setConnectors(connectorPayload)
      setQuests(questPayload)
    } catch (error) {
      setSaveMessage(error instanceof Error ? error.message : String(error || 'Failed to delete connector profile.'))
    } finally {
      setDeletingProfileKey('')
    }
  }

  const handleDeleteBaseline = async (baselineId: string) => {
    setDeletingBaselineId(baselineId)
    try {
      await client.deleteBaseline(baselineId)
      setSaveMessage(t.baselineDeleted)
      const [baselinePayload, questPayload] = await Promise.all([client.baselines(), client.quests()])
      setBaselineEntries(baselinePayload)
      setQuests(questPayload)
    } catch (error) {
      setSaveMessage(error instanceof Error ? error.message : String(error || 'Failed to delete baseline.'))
      throw error
    } finally {
      setDeletingBaselineId('')
    }
  }

  const handleManageConnectorBinding = async ({
    connectorName,
    profileId,
    conversationId,
    currentQuestId,
    nextQuestId,
  }: {
    connectorName: ConnectorName
    profileId: string
    conversationId: string
    currentQuestId?: string | null
    nextQuestId?: string | null
  }) => {
    const actionKey = `${connectorName}:${profileId}`
    setBindingProfileKey(actionKey)
    try {
      const normalizedNextQuestId = String(nextQuestId || '').trim() || null
      const normalizedCurrentQuestId = String(currentQuestId || '').trim() || null
      if (!normalizedNextQuestId && !normalizedCurrentQuestId) {
        return
      }
      let result: Record<string, unknown>
      if (normalizedNextQuestId) {
        result = await client.updateQuestBindings(normalizedNextQuestId, {
          connector: connectorName,
          conversation_id: conversationId,
          force: true,
        })
      } else {
        result = await client.updateQuestBindings(normalizedCurrentQuestId as string, {
          connector: connectorName,
          conversation_id: null,
          force: true,
        })
      }
      if (!result.ok) {
        throw new Error(String(result.message || 'Unable to update connector binding.'))
      }
      setSaveMessage(
        connectorBindingTransitionMessage(
          (result as Record<string, unknown>).binding_transition,
          normalizedNextQuestId || normalizedCurrentQuestId,
          locale
        )
      )
      const [connectorPayload, questPayload] = await Promise.all([client.connectors(), client.quests()])
      setConnectors(connectorPayload)
      setQuests(questPayload)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error || 'Unable to update connector binding.')
      setSaveMessage(message)
      throw error
    } finally {
      setBindingProfileKey('')
    }
  }

  return (
    <div className="font-project flex h-screen flex-col overflow-hidden px-4 pb-4 pt-4 sm:px-6 sm:pb-6">
      <ProjectsAppBar title={t.title} />

      <main className="mx-auto mt-5 min-h-0 w-full flex-1 overflow-hidden">
        <div
          className={cn(
            'mx-auto grid h-full min-h-0 w-full max-w-[90vw] grid-rows-[auto_minmax(0,1fr)] gap-0 xl:grid-rows-1',
            dockOpen ? 'xl:grid-cols-[260px_minmax(0,1fr)_420px]' : 'xl:grid-cols-[260px_minmax(0,1fr)]'
          )}
        >
          <aside className="feed-scrollbar flex min-h-0 flex-col overflow-auto border-b border-black/[0.08] pb-6 xl:border-b-0 xl:border-r xl:pb-0 xl:pr-6 dark:border-white/[0.08]">
            <div className="text-sm font-medium">{t.title}</div>

            <div className="relative mt-4">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t.search} className="rounded-[18px] border-black/[0.08] bg-white/[0.44] pl-10 shadow-none dark:bg-white/[0.03]" />
            </div>

            <div className="mt-5">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.files}</div>
              {filteredFiles.map((file, index) => {
                const name = file.name as ConfigDocumentName
                return (
                  <button
                    key={file.name}
                    type="button"
                    onClick={() => handleSelectSection(name)}
                    className={cn(
                      'flex w-full items-center justify-between rounded-[14px] px-3 py-2.5 text-left transition',
                      selectedName === file.name
                        ? 'bg-black/[0.045] text-foreground dark:bg-white/[0.06]'
                        : 'text-muted-foreground hover:bg-black/[0.03] hover:text-foreground dark:hover:bg-white/[0.03]'
                    )}
                    style={{ marginTop: index === 0 ? 0 : undefined }}
                  >
                    <span className="flex items-center gap-2">
                      <span className="text-sm font-medium">{configLabel(name, locale)}</span>
                      <HintDot label={configHint(name, locale)} />
                    </span>
                  </button>
                )
              })}
            </div>

            <div className="mt-8 border-t border-black/[0.08] pt-4 text-xs text-muted-foreground dark:border-white/[0.08]">
              <div className="mb-1 uppercase tracking-[0.18em]">{t.daemon}</div>
              <div className="break-all">{runtimeAddress}</div>
            </div>

            <div className="mt-6 border-t border-black/[0.08] pt-4 dark:border-white/[0.08]">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.connectors}</div>
              {connectorSummary.length === 0 ? (
                <div className="text-xs text-muted-foreground">{t.noHealth}</div>
              ) : (
                <div className="space-y-2">
                  {connectorSummary.map((connector) => {
                    const entry = visibleConnectorEntries.find((item) => item.name === connector.name)
                    const Icon = entry?.icon
                    return (
                      <button
                        key={connector.name}
                        type="button"
                        onClick={() => {
                          setSelectedName('connectors')
                          setSaveMessage('')
                          navigate({
                            pathname: settingsConfigPath('connectors', connector.name),
                            hash: '',
                          })
                        }}
                        className={cn(
                          'flex w-full items-center justify-between gap-3 rounded-[14px] px-3 py-2.5 text-left text-sm transition',
                          selectedName === 'connectors' && selectedConnectorName === connector.name
                            ? 'bg-black/[0.045] text-foreground dark:bg-white/[0.06]'
                            : 'text-muted-foreground hover:bg-black/[0.03] hover:text-foreground dark:hover:bg-white/[0.03]'
                        )}
                      >
                        <span className="flex min-w-0 items-center gap-2">
                          {Icon ? <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" /> : null}
                          <span className="truncate">{connector.label}</span>
                        </span>
                        <span className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
                          <span
                            className={cn(
                              'h-2 w-2 rounded-full',
                              connector.enabled ? 'bg-emerald-500/80' : 'bg-zinc-400/80 dark:bg-zinc-500/80'
                            )}
                          />
                          {connector.enabled ? t.enabled : t.idle}
                        </span>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>

            <div className="mt-6 border-t border-black/[0.08] pt-4 dark:border-white/[0.08]">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.literatureTools}</div>
              <button
                type="button"
                onClick={() => handleSelectSection('deepxiv')}
                className={cn(
                  'flex w-full items-center justify-between rounded-[14px] px-3 py-2.5 text-left transition',
                  selectedName === 'deepxiv'
                    ? 'bg-black/[0.045] text-foreground dark:bg-white/[0.06]'
                    : 'text-muted-foreground hover:bg-black/[0.03] hover:text-foreground dark:hover:bg-white/[0.03]'
                )}
              >
                <span className="flex items-center gap-2">
                  <span className="text-sm font-medium">{sectionLabel('deepxiv', locale)}</span>
                  <HintDot label={sectionHint('deepxiv', locale)} />
                </span>
              </button>
            </div>

            <div className="mt-6 border-t border-black/[0.08] pt-4 dark:border-white/[0.08]">
              <button
                type="button"
                onClick={() => setAdminExpanded((value) => !value)}
                className="flex w-full items-start justify-between gap-3 text-left transition"
              >
                <span className="min-w-0">
                  <span className="block text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.admin}</span>
                  <span className="mt-1 block text-xs leading-5 text-muted-foreground">{t.adminHint}</span>
                </span>
                <ChevronDown className={cn('h-4 w-4 shrink-0 text-muted-foreground transition-transform', adminExpanded ? 'rotate-180' : 'rotate-0')} />
              </button>
              {adminExpanded ? (
                <div className="mt-3 space-y-1">
                  {filteredOperations.map((item) => (
                    <button
                      key={item.name}
                      type="button"
                      onClick={() => handleSelectSection(item.name)}
                      className={cn(
                        'flex w-full items-center justify-between rounded-[16px] px-3 py-2.5 text-left transition',
                        selectedName === item.name
                          ? 'bg-black/[0.045] text-foreground dark:bg-white/[0.06]'
                          : 'text-muted-foreground hover:bg-black/[0.03] hover:text-foreground dark:hover:bg-white/[0.03]'
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <span className="text-sm font-medium">{item.label}</span>
                        <HintDot label={item.hint} />
                      </span>
                    </button>
                  ))}
                </div>
              ) : null}
            </div>

            <div className="mt-6 border-t border-black/[0.08] pt-4 dark:border-white/[0.08]">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.copilot}</div>
              <Button
                type="button"
                variant={dockOpen ? 'secondary' : 'outline'}
                size="sm"
                className="w-full justify-between rounded-[16px]"
                onClick={() => {
                  if (dockOpen) {
                    closeDock()
                    return
                  }
                  startFreshSession(location.pathname || '/settings')
                }}
              >
                <span>{dockOpen ? t.closeCopilot : t.openCopilot}</span>
                {activeRepair ? <Badge variant="warning">{activeRepair.repair_id}</Badge> : null}
              </Button>
            </div>
          </aside>

          <section ref={contentRef} className="feed-scrollbar min-h-0 overflow-y-auto py-6 xl:px-8">
            <div className={cn('mx-auto w-full', dockOpen ? 'max-w-[1010px]' : 'max-w-[1180px]')}>
              {isPageLoading ? (
                <div className="flex items-center gap-3 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {t.loading}...
                </div>
              ) : null}

              {!isPageLoading && !selectedName ? <div className="text-sm text-muted-foreground">{t.noFile}</div> : null}

              {!isPageLoading && selectedName && selectedMeta ? (
                <>
                  <header
                    id={selectedAnchorId || undefined}
                    className="flex scroll-mt-4 flex-col gap-4 border-b border-black/[0.08] pb-5 xl:flex-row xl:items-start xl:justify-between dark:border-white/[0.08]"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <h1 className="text-3xl font-semibold tracking-tight">{selectedMeta.label[locale]}</h1>
                        <HintDot label={selectedMeta.hint[locale]} />
                        {selectedAnchorId && !dockOpen ? (
                          <button
                            type="button"
                            onClick={() => jumpToAnchor(selectedAnchorId)}
                            className="rounded-full border border-black/[0.08] bg-white/[0.44] px-2 py-1 text-[11px] text-muted-foreground transition hover:text-foreground dark:border-white/[0.12] dark:bg-white/[0.03]"
                          >
                            #{selectedAnchorId}
                          </button>
                        ) : null}
                        {isDirty ? <span className="text-xs text-muted-foreground">{t.dirty}</span> : null}
                      </div>
                      {document?.path ? <div className="mt-2 break-all text-xs text-muted-foreground">{document.path}</div> : null}
                    </div>
                  </header>

                  {saveMessage ? <div className="mt-3 text-sm text-emerald-700 dark:text-emerald-300">{saveMessage}</div> : null}

                  {isOperationSection ? (
                    <div className="mt-4 border-b border-black/[0.08] pb-4 dark:border-white/[0.08]">
                      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                        <div>
                          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.admin}</div>
                          <div className="mt-1 text-xs leading-5 text-muted-foreground">{t.adminHint}</div>
                        </div>
                        <Button
                          type="button"
                          size="sm"
                          variant={dockOpen ? 'secondary' : 'outline'}
                          className="rounded-full"
                          onClick={() => {
                            if (dockOpen) {
                              closeDock()
                              return
                            }
                            startFreshSession(location.pathname || '/settings')
                          }}
                        >
                          {dockOpen ? t.closeCopilot : t.openCopilot}
                        </Button>
                      </div>
                      <div className="mt-4 overflow-x-auto pb-1">
                        <div className="flex min-w-max gap-2" role="tablist" aria-label={t.admin}>
                          {adminNavItems.map((item) => (
                            <button
                              key={item.name}
                              type="button"
                              role="tab"
                              aria-selected={selectedName === item.name}
                              onClick={() => handleSelectSection(item.name)}
                              data-onboarding-id={
                                item.name === 'summary'
                                  ? 'settings-admin-summary-tab'
                                  : item.name === 'quests'
                                    ? 'settings-admin-quests-tab'
                                    : undefined
                              }
                              className={cn(
                                'relative inline-flex items-center rounded-full border px-3 py-2 text-sm font-medium transition',
                                selectedName === item.name
                                  ? 'border-[#C7A57A] bg-[linear-gradient(180deg,rgba(222,196,158,0.28),rgba(222,196,158,0.12))] text-foreground shadow-[0_12px_24px_-18px_rgba(145,102,53,0.45)] dark:border-[#C7A57A]/70 dark:bg-[linear-gradient(180deg,rgba(199,165,122,0.18),rgba(199,165,122,0.06))]'
                                  : 'border-black/[0.08] bg-white/65 text-muted-foreground hover:border-black/[0.12] hover:text-foreground dark:border-white/[0.08] dark:bg-white/[0.03] dark:hover:border-white/[0.14]'
                              )}
                              title={item.hint}
                            >
                              {item.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  ) : null}

                  {helpMarkdown && !isConnectorDocument && !isBaselineDocument ? (
                    dockOpen ? (
                      <details className="border-b border-black/[0.08] py-4 dark:border-white/[0.08]">
                        <summary className="cursor-pointer list-none text-sm font-medium text-muted-foreground transition hover:text-foreground">
                          {t.reference}
                        </summary>
                        <div className="pt-4">
                          <MarkdownDocument
                            content={helpMarkdown}
                            hideFrontmatter
                            containerClassName="gap-0"
                            bodyClassName="max-h-none overflow-visible rounded-none bg-transparent px-0 py-0 text-sm leading-7 break-words [overflow-wrap:anywhere]"
                          />
                        </div>
                      </details>
                    ) : (
                      <section className="border-b border-black/[0.08] py-6 dark:border-white/[0.08]">
                        <div className="mb-3 text-sm font-medium">{t.reference}</div>
                        <MarkdownDocument
                          content={helpMarkdown}
                          hideFrontmatter
                          containerClassName="gap-0"
                          bodyClassName="max-h-none overflow-visible rounded-none bg-transparent px-0 py-0 text-sm leading-7 break-words [overflow-wrap:anywhere]"
                        />
                      </section>
                    )
                  ) : null}

                  {selectedName === 'deepxiv' ? (
                    <div className="pt-6">
                      <DeepXivSettingsPanel locale={locale} />
                    </div>
                  ) : null}
                  {/* TODO(upstream ea21104): summary/runtime/connectors_health/diagnostics/errors/
                      issues/logs/quests/repairs/controllers/stats/search sections were imported
                      but never added to the tree; restore JSX once the component files land. */}

                  {document && isConnectorDocument ? (
                    <div className="pt-6">
                      <ConnectorSettingsForm
                        locale={locale}
                        value={structuredConnectors}
                        connectors={connectors}
                        quests={quests}
                        saving={saving}
                        isDirty={isDirty}
                        deletingProfileKey={deletingProfileKey}
                        bindingProfileKey={bindingProfileKey}
                        visibleConnectorNames={visibleConnectorEntries.map((entry) => entry.name)}
                        selectedConnectorName={selectedConnectorName}
                        onChange={setStructuredConnectors}
                        onSave={handleSave}
                        onRefresh={refreshConnectorSettings}
                        onDeleteProfile={(connectorName, profileId) => void handleDeleteConnectorProfile(connectorName, profileId)}
                        onManageProfileBinding={(payload) => handleManageConnectorBinding(payload)}
                        onSelectConnector={(connectorName) =>
                          navigate({
                            pathname: settingsConfigPath('connectors', connectorName),
                            hash: '',
                          })
                        }
                        onBackToConnectorCatalog={() =>
                          navigate({
                            pathname: settingsConfigPath('connectors'),
                            hash: '',
                          })
                        }
                        onJumpToAnchor={jumpToAnchor}
                      />
                    </div>
                  ) : null}

                  {isBaselineDocument ? (
                    <div className="pt-6">
                      <BaselineSettingsPanel
                        locale={locale}
                        entries={baselineEntries}
                        deletingBaselineId={deletingBaselineId}
                        onDeleteBaseline={handleDeleteBaseline}
                      />
                    </div>
                  ) : null}

                  {selectedName === 'runners' ? (
                    <div className="pt-6">
                      <RunnerSettingsPanel locale={locale} />
                    </div>
                  ) : null}

                  {document && !isConnectorDocument && !isBaselineDocument && selectedName !== 'runners' ? (
                    <div className="pt-6">
                      <RegistrySettingsForm
                        documentName={selectedName as Exclude<ConfigDocumentName, 'connectors' | 'baselines'>}
                        locale={locale}
                        value={structuredDraft}
                        validation={validation}
                        testResult={testResult}
                        saving={saving}
                        validating={validating}
                        testingAll={testingAll}
                        systemTestable={Boolean(document.meta?.system_testable)}
                        onChange={setStructuredDraft}
                        onSave={() => void handleSave()}
                        onValidate={() => void runValidate()}
                        onTestAll={() => void runTestAll()}
                      />
                    </div>
                  ) : null}
                </>
              ) : null}
            </div>
          </section>

          {/* TODO(upstream ea21104): <SettingsOpsRail /> — component file missing. */}
        </div>
      </main>
      {/* TODO(upstream ea21104): <SettingsOpsLauncher /> — component file missing. */}
    </div>
  )
}
