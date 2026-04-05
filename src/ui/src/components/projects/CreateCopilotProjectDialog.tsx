import * as React from 'react'
import { ArrowLeft, Loader2, PanelRightOpen } from 'lucide-react'

import { ConnectorTargetRadioGroup, type ConnectorTargetRadioItem } from '@/components/connectors/ConnectorTargetRadioGroup'
import { OverlayDialog } from '@/components/home/OverlayDialog'
import { LAUNCH_DIALOG_SHELL_CLASS } from '@/components/projects/LaunchModeVisuals'
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
  type ProjectAccentId,
  type ProjectBackgroundStyleId,
  type ProjectTemplateId,
} from '@/lib/projectDisplayCatalog'
import { cn } from '@/lib/utils'
import type { ConnectorSnapshot } from '@/types'

const copy = {
  en: {
    title: 'Copilot Setup',
    body: 'Create first. Start later.',
    essentialsTitle: 'Essentials',
    essentialsHint: 'A title and one connector are enough.',
    advancedTitle: 'Advanced options',
    advancedHint: 'Background, card type, and accent.',
    advancedShow: 'Show advanced options',
    advancedHide: 'Hide advanced options',
    titleLabel: 'Title',
    titlePlaceholder: 'A short project title',
    templateLabel: 'Card type',
    backgroundLabel: 'Card background',
    accentLabel: 'Accent color',
    connectorLabel: 'Connector binding',
    connectorHint: 'Optional. Bind one connector target now, or keep this project local-only.',
    localOnly: 'Local only',
    create: 'Create project',
    creating: 'Creating…',
    cancel: 'Cancel',
    back: 'Back',
    required: 'Title is required.',
    loadingConnectors: 'Loading connector targets…',
    noConnectors: 'No connector target available yet. The project will stay local-only until you bind one later.',
    previewTitle: 'Copilot',
    previewSubtitle: 'Waits for your first message.',
  },
  zh: {
    title: 'Copilot 配置',
    body: '先创建，稍后再开始。',
    essentialsTitle: '必要信息',
    essentialsHint: '标题和一个 connector 就够了。',
    advancedTitle: '高级设置',
    advancedHint: '背景、卡片类型和强调色都在这里。',
    advancedShow: '展开高级设置',
    advancedHide: '收起高级设置',
    titleLabel: '标题',
    titlePlaceholder: '输入一个简短项目标题',
    templateLabel: '卡片类型',
    backgroundLabel: '卡片背景',
    accentLabel: '强调色',
    connectorLabel: '绑定 Connector',
    connectorHint: '可选。现在绑定一个目标，或者先保持本地模式。',
    localOnly: '仅本地',
    create: '一键新建',
    creating: '创建中…',
    cancel: '取消',
    back: '返回',
    required: '标题不能为空。',
    loadingConnectors: '正在加载可绑定目标…',
    noConnectors: '暂时没有可绑定目标。项目会先保持本地模式，之后也可以再绑定。',
    previewTitle: '协作模式',
    previewSubtitle: '等待你的第一条消息。',
  },
} as const

function formatBoundQuestLabel(snapshot: ConnectorSnapshot, targetConversationId: string | null, locale: 'en' | 'zh') {
  const matchingBinding = (snapshot.bindings || []).find((item) => {
    return String(item.conversation_id || '').trim() === String(targetConversationId || '').trim()
  })
  const boundQuestId = String(matchingBinding?.quest_id || '').trim()
  if (!boundQuestId) return ''
  return locale === 'zh' ? `当前绑定到 ${boundQuestId}` : `Currently bound to ${boundQuestId}`
}

function buildConnectorItems(connectors: ConnectorSnapshot[], locale: 'en' | 'zh'): ConnectorTargetRadioItem[] {
  const items: ConnectorTargetRadioItem[] = [
    {
      value: '__local__',
      connectorName: 'local',
      connectorLabel: locale === 'zh' ? '仅本地' : 'Local only',
      targetId: '',
      boundQuestLabel:
        locale === 'zh'
          ? '创建后先停驻在本地工作区，后续可以随时再绑定外部连接。'
          : 'Keep the project local-only for now. You can bind an external connector later.',
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

export function CreateCopilotProjectDialog(props: {
  open: boolean
  onClose: () => void
  onBack?: () => void
  onCreated: (questId: string) => void
}) {
  const { locale } = useI18n()
  const t = locale === 'zh' ? copy.zh : copy.en
  const [title, setTitle] = React.useState('')
  const [template, setTemplate] = React.useState<ProjectTemplateId>('blank')
  const [backgroundStyle, setBackgroundStyle] = React.useState<ProjectBackgroundStyleId>('paper')
  const [accentColor, setAccentColor] = React.useState<ProjectAccentId>('graphite')
  const [connectorItems, setConnectorItems] = React.useState<ConnectorTargetRadioItem[]>([
    {
      value: '__local__',
      connectorName: 'local',
      connectorLabel: t.localOnly,
      targetId: '',
      boundQuestLabel:
        locale === 'zh'
          ? '创建后先停驻在本地工作区，后续可以随时再绑定外部连接。'
          : 'Keep the project local-only for now. You can bind an external connector later.',
      localOnly: true,
    },
  ])
  const [selectedConnector, setSelectedConnector] = React.useState('__local__')
  const [connectorsLoading, setConnectorsLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [creating, setCreating] = React.useState(false)
  const [showAdvanced, setShowAdvanced] = React.useState(false)

  React.useEffect(() => {
    if (!props.open) {
      return
    }
    let active = true
    setConnectorsLoading(true)
    void client
      .connectors()
      .then((payload) => {
        if (!active) return
        setConnectorItems(buildConnectorItems(payload, locale))
      })
      .catch((caught) => {
        if (!active) return
        console.error('Failed to load connectors for Copilot project creation:', caught)
      })
      .finally(() => {
        if (active) {
          setConnectorsLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [locale, props.open])

  React.useEffect(() => {
    if (!props.open) {
      setError(null)
      setCreating(false)
      setShowAdvanced(false)
    }
  }, [props.open])

  const selectedConnectorBinding = React.useMemo(() => {
    if (!selectedConnector || selectedConnector === '__local__') return []
    const [connector, conversationId] = selectedConnector.split('::')
    if (!connector || !conversationId) return []
    return [{ connector, conversation_id: conversationId }]
  }, [selectedConnector])

  const selectedConnectorLabel = React.useMemo(() => {
    return connectorItems.find((item) => item.value === selectedConnector)?.connectorLabel || t.localOnly
  }, [connectorItems, selectedConnector, t.localOnly])

  const handleCreate = React.useCallback(async () => {
    const normalizedTitle = title.trim()
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
      props.onCreated(result.snapshot.quest_id)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to create project.')
    } finally {
      setCreating(false)
    }
  }, [accentColor, backgroundStyle, props, selectedConnectorBinding, t.required, template, title])

  return (
    <OverlayDialog
      open={props.open}
      title={t.title}
      description={t.body}
      onClose={props.onClose}
      className={LAUNCH_DIALOG_SHELL_CLASS}
    >
      <div className="feed-scrollbar grid h-full min-h-0 gap-5 overflow-y-auto p-4 lg:grid-cols-[minmax(0,1fr)_420px] lg:p-5">
        <div className="rounded-[22px] border border-black/10 bg-white/78 p-5 shadow-[0_20px_64px_-48px_rgba(42,38,33,0.28)] backdrop-blur-xl">
          <div className="grid gap-6">
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-[#8A8278]">{t.titleLabel}</div>
              <Input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder={t.titlePlaceholder}
                className="h-12 rounded-[18px] border-black/10 bg-white/80 text-base"
              />
            </div>

            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-[#8A8278]">{t.connectorLabel}</div>
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
                <ConnectorTargetRadioGroup
                  items={connectorItems}
                  value={selectedConnector}
                  onChange={setSelectedConnector}
                  ariaLabel={t.connectorLabel}
                />
              )}
            </div>

            <button
              type="button"
              onClick={() => setShowAdvanced((current) => !current)}
              className="flex items-center justify-between rounded-[16px] border border-[rgba(45,42,38,0.08)] bg-[rgba(244,239,233,0.54)] px-4 py-3 text-left transition hover:bg-[rgba(244,239,233,0.72)]"
            >
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#6B6761]">{t.advancedTitle}</div>
                <div className="mt-1 text-[11px] leading-5 text-[#7A746C]">{showAdvanced ? t.advancedHide : t.advancedHint}</div>
              </div>
              <div className="text-[12px] font-medium text-[#4A4742]">{showAdvanced ? t.advancedHide : t.advancedShow}</div>
            </button>

            {showAdvanced ? (
              <>
                <div>
                  <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-[#8A8278]">{t.backgroundLabel}</div>
                  <div className="grid gap-3 md:grid-cols-2">
                    {PROJECT_BACKGROUND_STYLE_OPTIONS.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => setBackgroundStyle(item.id)}
                        className={cn(
                          'rounded-[22px] border px-4 py-4 text-left transition',
                          backgroundStyle === item.id
                            ? 'border-black/15 bg-[#F4EEE6] shadow-[0_16px_34px_-24px_rgba(42,38,33,0.3)]'
                            : 'border-black/8 bg-white/72 hover:border-black/12 hover:bg-white'
                        )}
                      >
                        <div className="text-sm font-semibold">{item.label}</div>
                        <div className="mt-2 text-xs leading-5 text-[#5D5A55]">{item.description}</div>
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-[#8A8278]">{t.templateLabel}</div>
                  <div className="grid gap-3 md:grid-cols-2">
                    {PROJECT_TEMPLATE_OPTIONS.map((item) => (
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
                        <div className="text-sm font-semibold">{item.label}</div>
                        <div className="mt-2 text-xs leading-5 text-[#5D5A55]">{item.description}</div>
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-[#8A8278]">{t.accentLabel}</div>
                  <div className="flex flex-wrap gap-3">
                    {PROJECT_ACCENT_OPTIONS.map((item) => (
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
              </>
            ) : null}

            {error ? (
              <div className="rounded-[18px] border border-rose-400/25 bg-rose-50/80 px-4 py-3 text-sm text-rose-700">
                {error}
              </div>
            ) : null}

            <div className="flex flex-wrap items-center gap-3">
              {props.onBack ? (
                <Button
                  variant="outline"
                  className="rounded-full border-black/10 bg-white/70 px-5"
                  onClick={props.onBack}
                  disabled={creating}
                >
                  <ArrowLeft className="mr-2 h-4 w-4" />
                  {t.back}
                </Button>
              ) : null}
              <Button
                variant="ghost"
                className="rounded-full px-5"
                onClick={props.onClose}
                disabled={creating}
              >
                {t.cancel}
              </Button>
              <Button
                className="rounded-full bg-[#C7AD96] px-5 text-[#2D2A26] hover:bg-[#D7C6AE]"
                onClick={() => void handleCreate()}
                disabled={creating}
              >
                {creating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PanelRightOpen className="mr-2 h-4 w-4" />}
                {creating ? t.creating : t.create}
              </Button>
            </div>
          </div>
        </div>

        <div className="flex min-h-0 flex-col gap-4 rounded-[22px] border border-black/10 bg-white/76 p-5 shadow-[0_20px_64px_-48px_rgba(42,38,33,0.24)] backdrop-blur-xl">
          <ProjectDisplayPreviewCard
            title={title.trim() || t.titlePlaceholder}
            subtitle={t.previewSubtitle}
            template={template}
            accentColor={accentColor}
            backgroundStyle={backgroundStyle}
            modeLabel={t.previewTitle}
          />
          <div className="rounded-[22px] border border-black/8 bg-white/72 px-4 py-4 text-sm leading-6 text-[#5D5A55]">
            <div className="font-medium text-[#2D2A26]">{title.trim() || t.titlePlaceholder}</div>
            <div className="mt-2">{selectedConnectorLabel}</div>
          </div>
        </div>
      </div>
    </OverlayDialog>
  )
}
