import { ChevronDown, Loader2, PanelRightOpen } from 'lucide-react'
import * as React from 'react'
import { useNavigate } from 'react-router-dom'

import { ConnectorTargetRadioGroup, type ConnectorTargetRadioItem } from '@/components/connectors/ConnectorTargetRadioGroup'
import { ProjectDisplayPreviewCard } from '@/components/projects/ProjectDisplayPreviewCard'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { client } from '@/lib/api'
import { connectorTargetLabel, normalizeConnectorTargets } from '@/lib/connectors'
import { useI18n } from '@/lib/i18n'
import {
  PROJECT_ACCENT_OPTIONS,
  PROJECT_BACKGROUND_STYLE_OPTIONS,
  PROJECT_TEMPLATE_OPTIONS,
  resolveProjectAccent,
  type ProjectAccentId,
  type ProjectBackgroundStyleId,
  type ProjectTemplateId,
} from '@/lib/projectDisplayCatalog'
import { cn } from '@/lib/utils'
import type { ConnectorSnapshot } from '@/types'

type CopilotLocale = 'en' | 'zh'

const copy = {
  en: {
    eyebrow: 'Copilot Workspace',
    title: 'Create a quieter workspace first',
    body: 'Pick a starter card, optionally bind one connector, and open a copilot project that waits for your first instruction.',
    titleLabel: 'Project title',
    titleHint: 'Optional. If left empty, a default title will be generated from the selected card.',
    titlePlaceholder: 'Optional custom title',
    templateLabel: 'Starter card',
    templateHint: 'Choose the default card surface. The preview updates immediately.',
    backgroundLabel: 'Card background',
    accentLabel: 'Accent color',
    connectorLabel: 'Connector binding',
    connectorHint: 'Optional. Bind one connector target now, or keep this project local-only.',
    localOnly: 'Local only',
    localOnlyBody: 'Keep this workspace local for now. You can bind an external connector later.',
    create: 'Create selected project',
    creating: 'Creating…',
    cancel: 'Back',
    required: 'Unable to resolve a project title.',
    loadingConnectors: 'Loading connector targets…',
    noConnectors: 'No connector target is available yet. The project will stay local-only until you bind one later.',
    advancedTitle: 'Advanced options',
    advancedHint: 'Background and accent stay here.',
    advancedShow: 'Show advanced options',
    advancedHide: 'Hide advanced options',
    selectedBadge: 'Selected',
    previewMeta: 'Idle by default',
    previewSubtitle: 'DeepScientist waits for your first message instead of auto-running after creation.',
    previewAsideTitle: 'Live preview',
    previewAsideBody: 'You can create with just the selected starter card. Title and accent are optional refinements.',
  },
  zh: {
    eyebrow: 'Copilot 工作区',
    title: '先创建一个安静待命的工作区',
    body: '先选一个默认卡片，可选绑定一个 connector，然后进入一个等待你第一条指令的 copilot 项目。',
    titleLabel: '项目标题',
    titleHint: '可选。不填写时，会根据当前选中的卡片自动生成默认标题。',
    titlePlaceholder: '可选的自定义标题',
    templateLabel: '默认卡片',
    templateHint: '先选一个默认卡片表面，右侧预览会立刻跟随变化。',
    backgroundLabel: '卡片背景',
    accentLabel: '强调色',
    connectorLabel: '绑定 Connector',
    connectorHint: '可选。现在绑定一个目标，或者先保持本地模式。',
    localOnly: '仅本地',
    localOnlyBody: '先保持在本地工作区里。之后需要时，再绑定外部 connector 即可。',
    create: '创建当前项目',
    creating: '创建中…',
    cancel: '返回',
    required: '无法生成项目标题。',
    loadingConnectors: '正在加载可绑定目标…',
    noConnectors: '暂时没有可绑定目标。项目会先保持本地模式，之后也可以再绑定。',
    advancedTitle: '高级设置',
    advancedHint: '背景和强调色都放在这里。',
    advancedShow: '展开高级设置',
    advancedHide: '收起高级设置',
    selectedBadge: '已选中',
    previewMeta: '默认待命',
    previewSubtitle: 'DeepScientist 会等待你的第一条消息，而不是创建后立刻自动运行。',
    previewAsideTitle: '即时预览',
    previewAsideBody: '只选默认卡片就可以创建。标题和强调色只是可选微调，不再强迫一开始填太多。',
  },
} as const

const templateLocaleCopy: Record<CopilotLocale, Record<ProjectTemplateId, { label: string; description: string; defaultTitle: string }>> = {
  en: {
    blank: {
      label: 'Blank workspace',
      description: 'A quiet general-purpose copilot surface. Decide the flow later.',
      defaultTitle: 'New Copilot Workspace',
    },
    experiment: {
      label: 'Experiment board',
      description: 'A good default for implementation, debugging, and running experiments from chat.',
      defaultTitle: 'Experiment Copilot',
    },
    literature: {
      label: 'Literature desk',
      description: 'A reading-first surface for paper comparison, note taking, and collecting evidence.',
      defaultTitle: 'Literature Copilot',
    },
    analysis: {
      label: 'Analysis deck',
      description: 'A log- and result-oriented surface for review, diagnosis, and follow-up checks.',
      defaultTitle: 'Analysis Copilot',
    },
  },
  zh: {
    blank: {
      label: '空白工作区',
      description: '一个安静的通用 copilot 表面，先进入工作区，后面再决定具体路线。',
      defaultTitle: '新的 Copilot 工作区',
    },
    experiment: {
      label: '实验面板',
      description: '更适合实现、调试、跑实验，以及在聊天里持续推进执行。',
      defaultTitle: '实验 Copilot',
    },
    literature: {
      label: '文献桌面',
      description: '更适合读论文、对比 baseline、做摘录和整理证据。',
      defaultTitle: '文献 Copilot',
    },
    analysis: {
      label: '分析视图',
      description: '更适合看日志、结果、trace 和后续检查。',
      defaultTitle: '分析 Copilot',
    },
  },
}

const accentLocaleLabels: Record<CopilotLocale, Record<ProjectAccentId, string>> = {
  en: {
    graphite: 'Graphite',
    sage: 'Sage',
    clay: 'Clay',
    mist: 'Mist',
    rose: 'Rose',
  },
  zh: {
    graphite: '石墨',
    sage: '鼠尾草',
    clay: '陶土',
    mist: '薄雾',
    rose: '玫瑰',
  },
}

function defaultCopilotProjectTitle(locale: CopilotLocale, template: ProjectTemplateId) {
  return templateLocaleCopy[locale][template].defaultTitle
}

function formatBoundQuestLabel(snapshot: ConnectorSnapshot, targetConversationId: string | null, locale: CopilotLocale) {
  const matchingBinding = (snapshot.bindings || []).find((item) => {
    return String(item.conversation_id || '').trim() === String(targetConversationId || '').trim()
  })
  const boundQuestId = String(matchingBinding?.quest_id || '').trim()
  if (!boundQuestId) return ''
  return locale === 'zh' ? `当前绑定到 ${boundQuestId}` : `Currently bound to ${boundQuestId}`
}

function buildConnectorItems(connectors: ConnectorSnapshot[], locale: CopilotLocale, localOnlyBody: string): ConnectorTargetRadioItem[] {
  const items: ConnectorTargetRadioItem[] = [
    {
      value: '__local__',
      connectorName: 'local',
      connectorLabel: locale === 'zh' ? '仅本地' : 'Local only',
      targetId: '',
      boundQuestLabel: localOnlyBody,
      localOnly: true,
    },
  ]

  for (const snapshot of connectors) {
    if (!snapshot.enabled) continue
    for (const target of normalizeConnectorTargets(snapshot)) {
      const conversationId = String(target.conversation_id || '').trim()
      if (!conversationId) continue
      items.push({
        value: `${snapshot.name}::${conversationId}`,
        connectorName: snapshot.name,
        connectorLabel: connectorTargetLabel(target) || snapshot.name,
        targetId: conversationId,
        boundQuestLabel: formatBoundQuestLabel(snapshot, conversationId, locale),
      })
    }
  }

  return items
}

export function CreateCopilotProjectPage() {
  const navigate = useNavigate()
  const { locale } = useI18n()
  const uiLocale: CopilotLocale = locale === 'zh' ? 'zh' : 'en'
  const t = copy[uiLocale]
  const [title, setTitle] = React.useState('')
  const [template, setTemplate] = React.useState<ProjectTemplateId>('blank')
  const [accentColor, setAccentColor] = React.useState<ProjectAccentId>('graphite')
  const [backgroundStyle, setBackgroundStyle] = React.useState<ProjectBackgroundStyleId>('paper')
  const [connectorItems, setConnectorItems] = React.useState<ConnectorTargetRadioItem[]>([
    {
      value: '__local__',
      connectorName: 'local',
      connectorLabel: t.localOnly,
      targetId: '',
      boundQuestLabel: t.localOnlyBody,
      localOnly: true,
    },
  ])
  const [selectedConnector, setSelectedConnector] = React.useState('__local__')
  const [connectorsLoading, setConnectorsLoading] = React.useState(true)
  const [showAdvanced, setShowAdvanced] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [creating, setCreating] = React.useState(false)

  const localizedTemplateOptions = React.useMemo(
    () =>
      PROJECT_TEMPLATE_OPTIONS.map((item) => ({
        ...item,
        label: templateLocaleCopy[uiLocale][item.id].label,
        description: templateLocaleCopy[uiLocale][item.id].description,
      })),
    [uiLocale]
  )

  const localizedAccentOptions = React.useMemo(
    () =>
      PROJECT_ACCENT_OPTIONS.map((item) => ({
        ...item,
        label: accentLocaleLabels[uiLocale][item.id],
      })),
    [uiLocale]
  )

  React.useEffect(() => {
    let active = true
    setConnectorsLoading(true)
    void client
      .connectors()
      .then((payload) => {
        if (!active) return
        setConnectorItems(buildConnectorItems(payload, uiLocale, t.localOnlyBody))
      })
      .catch((caught) => {
        if (!active) return
        console.error('Failed to load connectors for Copilot project creation:', caught)
      })
      .finally(() => {
        if (active) setConnectorsLoading(false)
      })
    return () => {
      active = false
    }
  }, [t.localOnlyBody, uiLocale])

  const selectedConnectorBinding = React.useMemo(() => {
    if (!selectedConnector || selectedConnector === '__local__') return []
    const [connector, conversationId] = selectedConnector.split('::')
    if (!connector || !conversationId) return []
    return [{ connector, conversation_id: conversationId }]
  }, [selectedConnector])

  const selectedConnectorLabel = React.useMemo(() => {
    return connectorItems.find((item) => item.value === selectedConnector)?.connectorLabel || t.localOnly
  }, [connectorItems, selectedConnector, t.localOnly])

  const resolvedTitle = React.useMemo(() => {
    return title.trim() || defaultCopilotProjectTitle(uiLocale, template)
  }, [template, title, uiLocale])

  const accent = resolveProjectAccent(accentColor)

  const handleCreate = React.useCallback(async () => {
    const normalizedTitle = resolvedTitle.trim()
    if (!normalizedTitle) {
      setError(t.required)
      return
    }
    setCreating(true)
    setError(null)
    try {
      const result = await client.createQuestWithOptions({
        goal: normalizedTitle,
        title: normalizedTitle,
        source: 'web-react',
        auto_start: false,
        auto_bind_latest_connectors: false,
        requested_connector_bindings: selectedConnectorBinding,
        startup_contract: {
          schema_version: 4,
          workspace_mode: 'copilot',
          decision_policy: 'user_gated',
          launch_mode: 'custom',
          custom_profile: 'freeform',
          project_display: {
            template,
            accent_color: accentColor,
            background_style: backgroundStyle,
          },
        },
      })
      navigate(`/projects/${result.snapshot.quest_id}`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to create project.')
    } finally {
      setCreating(false)
    }
  }, [accentColor, backgroundStyle, navigate, resolvedTitle, selectedConnectorBinding, t.required, template])

  return (
    <div className="min-h-screen bg-[#F4EFE8] font-project text-[#2D2A26]">
      <div
        className="feed-scrollbar min-h-screen overflow-y-auto px-5 py-6 sm:px-6 sm:py-8"
        style={{
          backgroundImage:
            'radial-gradient(880px circle at 10% 12%, rgba(217, 202, 186, 0.28), transparent 58%), radial-gradient(760px circle at 88% 0%, rgba(173, 189, 201, 0.22), transparent 52%), linear-gradient(180deg, #F7F3ED 0%, #F0E9DF 100%)',
        }}
      >
        <div className="mx-auto max-w-7xl">
          <div className="flex flex-wrap items-start justify-between gap-4 pb-6">
            <div className="min-w-0">
              <div className="text-xs uppercase tracking-[0.22em] text-[#8A8278]">{t.eyebrow}</div>
              <h1 className="mt-2 text-3xl font-semibold tracking-[-0.03em]">{t.title}</h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-[#5D5A55]">{t.body}</p>
            </div>
            <Button
              variant="outline"
              className="rounded-full border-black/10 bg-white/72 px-5"
              onClick={() => navigate('/projects')}
            >
              {t.cancel}
            </Button>
          </div>

          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px] lg:items-start">
            <div className="rounded-[32px] border border-white/10 bg-[rgba(252,248,242,0.96)] p-5 shadow-[0_36px_100px_-56px_rgba(15,23,42,0.34)] backdrop-blur-xl sm:p-6">
              <div className="grid gap-6">
                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-[#8A8278]">
                    {t.templateLabel}
                  </div>
                  <div className="mb-4 text-sm leading-6 text-[#5D5A55]">{t.templateHint}</div>
                  <div className="grid gap-3 md:grid-cols-2">
                    {localizedTemplateOptions.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => setTemplate(item.id)}
                        className={cn(
                          'rounded-[22px] border px-4 py-4 text-left transition',
                          template === item.id
                            ? 'border-black/15 bg-[#F4EEE6] shadow-[0_16px_34px_-24px_rgba(42,38,33,0.3)]'
                            : 'border-black/8 bg-white/72 hover:border-black/12 hover:bg-white'
                        )}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-semibold">{item.label}</div>
                            <div className="mt-2 text-xs leading-5 text-[#5D5A55]">{item.description}</div>
                          </div>
                          {template === item.id ? (
                            <span className="rounded-full border border-black/10 bg-white/86 px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.16em] text-[#6D5946]">
                              {t.selectedBadge}
                            </span>
                          ) : null}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-[#8A8278]">
                    {t.connectorLabel}
                  </div>
                  <div className="mb-4 text-sm leading-6 text-[#5D5A55]">{t.connectorHint}</div>
                  {connectorsLoading ? (
                    <div className="flex items-center gap-3 rounded-[22px] border border-black/8 bg-white/72 px-4 py-4 text-sm text-[#5D5A55]">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      {t.loadingConnectors}
                    </div>
                  ) : connectorItems.length <= 1 ? (
                    <div className="rounded-[22px] border border-black/8 bg-white/72 px-4 py-4 text-sm leading-6 text-[#5D5A55]">
                      {t.noConnectors}
                    </div>
                  ) : (
                    <div className="max-h-[320px] overflow-y-auto pr-1">
                      <ConnectorTargetRadioGroup
                        items={connectorItems}
                        value={selectedConnector}
                        onChange={setSelectedConnector}
                        ariaLabel={t.connectorLabel}
                      />
                    </div>
                  )}
                </div>

                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-[#8A8278]">
                    {t.titleLabel}
                  </div>
                  <Input
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder={t.titlePlaceholder}
                    className="h-12 rounded-[18px] border-black/10 bg-white/80 text-base"
                  />
                  <div className="mt-2 text-sm leading-6 text-[#5D5A55]">{t.titleHint}</div>
                </div>

                <button
                  type="button"
                  onClick={() => setShowAdvanced((current) => !current)}
                  className="flex items-center justify-between rounded-[20px] border border-[rgba(126,108,82,0.12)] bg-[rgba(244,239,233,0.72)] px-4 py-3 text-left transition hover:bg-white"
                >
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#7A746C]">{t.advancedTitle}</div>
                    <div className="mt-1 text-sm leading-6 text-[#5D5A55]">{showAdvanced ? t.advancedHide : t.advancedHint}</div>
                  </div>
                  <div className="inline-flex items-center gap-2 text-sm font-medium text-[#4A4742]">
                    <span>{showAdvanced ? t.advancedHide : t.advancedShow}</span>
                    <ChevronDown className={cn('h-4 w-4 transition', showAdvanced && 'rotate-180')} />
                  </div>
                </button>

                {showAdvanced ? (
                  <div className="grid gap-5">
                    <div>
                      <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-[#8A8278]">
                        {t.backgroundLabel}
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2">
                        {PROJECT_BACKGROUND_STYLE_OPTIONS.map((item) => (
                          <button
                            key={item.id}
                            type="button"
                            onClick={() => setBackgroundStyle(item.id)}
                            className={cn(
                              'rounded-[18px] border px-4 py-3 text-left transition',
                              backgroundStyle === item.id
                                ? 'border-black/15 bg-[#F4EEE6] shadow-[0_16px_34px_-24px_rgba(42,38,33,0.3)]'
                                : 'border-black/8 bg-white/72 hover:border-black/12 hover:bg-white'
                            )}
                          >
                            <div className="text-sm font-semibold">{item.label}</div>
                            <div className="mt-1 text-xs leading-5 text-[#5D5A55]">{item.description}</div>
                          </button>
                        ))}
                      </div>
                    </div>
                    <div>
                      <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-[#8A8278]">
                        {t.accentLabel}
                      </div>
                      <div className="flex flex-wrap gap-3">
                        {localizedAccentOptions.map((item) => (
                          <button
                            key={item.id}
                            type="button"
                            onClick={() => setAccentColor(item.id)}
                            className={cn(
                              'flex items-center gap-3 rounded-full border px-4 py-2.5 text-sm transition',
                              accentColor === item.id
                                ? 'border-black/15 bg-white shadow-[0_14px_28px_-24px_rgba(42,38,33,0.4)]'
                                : 'border-black/8 bg-white/70 hover:border-black/12 hover:bg-white/90'
                            )}
                          >
                            <span className={cn('h-3 w-3 rounded-full', item.dotClassName)} />
                            {item.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : null}

                {error ? (
                  <div className="rounded-[18px] border border-rose-400/25 bg-rose-50/80 px-4 py-3 text-sm text-rose-700">
                    {error}
                  </div>
                ) : null}

                <div className="flex flex-wrap items-center justify-between gap-3 rounded-[22px] border border-[rgba(126,108,82,0.12)] bg-[rgba(244,239,233,0.62)] px-4 py-4">
                  <div className="text-sm leading-6 text-[#5D5A55]">
                    <div className="font-medium text-[#2D2A26]">{selectedConnectorLabel}</div>
                    <div>{resolvedTitle}</div>
                  </div>
                  <Button
                    onClick={() => void handleCreate()}
                    disabled={creating}
                    className="h-12 rounded-full bg-[#C7AD96] px-6 text-[#2D2A26] hover:bg-[#D7C6AE]"
                  >
                    {creating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PanelRightOpen className="mr-2 h-4 w-4" />}
                    {creating ? t.creating : t.create}
                  </Button>
                </div>
              </div>
            </div>

            <div className="space-y-4 lg:sticky lg:top-8">
              <ProjectDisplayPreviewCard
                title={resolvedTitle}
                subtitle={t.previewSubtitle}
                template={template}
                accentColor={accent.id}
                backgroundStyle={backgroundStyle}
                meta={t.previewMeta}
                modeLabel="Copilot"
              />
              <div className="rounded-[28px] border border-white/10 bg-[rgba(252,248,242,0.94)] p-5 text-sm leading-6 text-[#5D5A55] shadow-[0_28px_82px_-54px_rgba(15,23,42,0.24)] backdrop-blur-xl">
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-[#8A8278]">
                  <PanelRightOpen className="h-4 w-4" />
                  {t.previewAsideTitle}
                </div>
                <div className="mt-4">{t.previewAsideBody}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default CreateCopilotProjectPage
