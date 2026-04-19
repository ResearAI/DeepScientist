'use client'

import * as React from 'react'
import { AlertTriangle, ChevronDown, ChevronUp, Link2, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'

import { ConnectorTargetRadioGroup, type ConnectorTargetRadioItem } from '@/components/connectors/ConnectorTargetRadioGroup'
import { EnhancedCard } from '@/components/ui/enhanced-card'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import { ConfirmModal } from '@/components/ui/modal'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Separator } from '@/components/ui/separator'
import { useToast } from '@/components/ui/toast'
import { client } from '@/lib/api'
import { conversationIdentityKey, normalizeConnectorTargets, parseConversationId } from '@/lib/connectors'
import { useI18n } from '@/lib/i18n/useI18n'
import type { ConnectorSnapshot, ConnectorTargetSnapshot, QuestSummary } from '@/types'

type ConflictItem = {
  quest_id: string
  title?: string | null
  reason?: string | null
}

type RunnerEnvRow = {
  key: string
  value: string
}

type WorkspaceMode = 'copilot' | 'autonomous'

const DEFAULT_RUNNER_ENV_KEYS: Record<string, readonly string[]> = {
  codex: ['OPENAI_BASE_URL', 'OPENAI_API_KEY'],
  claude: ['ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL', 'CLAUDE_CODE_MAX_OUTPUT_TOKENS'],
  opencode: [],
}

function normalizeRunnerEnvRows(raw: unknown, runnerName: string = 'codex'): RunnerEnvRow[] {
  const source = raw && typeof raw === 'object' && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {}
  const rows: RunnerEnvRow[] = []
  const seen = new Set<string>()
  const defaultKeys = DEFAULT_RUNNER_ENV_KEYS[runnerName] || []
  for (const key of defaultKeys) {
    rows.push({
      key,
      value: typeof source[key] === 'string' ? source[key] : '',
    })
    seen.add(key)
  }
  for (const [rawKey, rawValue] of Object.entries(source)) {
    const key = String(rawKey || '').trim()
    if (!key || seen.has(key)) continue
    rows.push({
      key,
      value: rawValue == null ? '' : String(rawValue),
    })
  }
  return rows
}

function runnerEnvRowsToPayload(rows: RunnerEnvRow[]): Record<string, string> {
  const payload: Record<string, string> = {}
  for (const row of rows) {
    const key = String(row.key || '').trim()
    const value = String(row.value || '')
    if (!key) continue
    payload[key] = value
  }
  return payload
}

function normalizeWorkspaceMode(value: unknown): WorkspaceMode {
  return String(value || '').trim().toLowerCase() === 'copilot' ? 'copilot' : 'autonomous'
}

function connectorLabel(connector: ConnectorSnapshot, fallbackConnectorLabel: string) {
  const name = String(connector.name || '').trim()
  if (!name) return fallbackConnectorLabel
  if (name.toLowerCase() === 'qq') return 'QQ'
  return name[0].toUpperCase() + name.slice(1)
}

function bindingTargetLabel(
  conversationId: string | null | undefined,
  labels: {
    localOnly: string
    passive: string
  }
) {
  const parsed = parseConversationId(conversationId || '')
  if (!parsed?.connector) return labels.localOnly
  const connector = parsed.connector.toLowerCase() === 'qq' ? 'QQ' : `${parsed.connector[0].toUpperCase()}${parsed.connector.slice(1)}`
  const chatId =
    parsed.chat_type === 'passive'
      ? `${labels.passive} · ${String(parsed.chat_id || parsed.chat_id_raw || conversationId || '').trim()}`
      : String(parsed.chat_id || parsed.chat_id_raw || conversationId || '').trim()
  return [connector, chatId].filter(Boolean).join(' · ')
}

function connectorTargetId(
  target: ConnectorTargetSnapshot,
  labels: {
    passive: string
    unknown: string
  }
) {
  const parsed = parseConversationId(target.conversation_id)
  const profileLabel = String(target.profile_label || target.profile_id || '').trim()
  const chatId =
    parsed?.chat_type === 'passive'
      ? `${labels.passive} · ${String(parsed?.chat_id || target.chat_id || target.chat_id_raw || target.conversation_id || '').trim()}`
      : String(parsed?.chat_id || target.chat_id || target.chat_id_raw || target.conversation_id || '').trim()
  return [profileLabel, chatId].filter(Boolean).join(' · ') || labels.unknown
}

function bindingTransitionDescription(
  transition: unknown,
  questId: string,
  t: (key: string, variables?: Record<string, string | number>) => string,
) {
  if (!transition || typeof transition !== 'object') return t('connector_bindings_saved')
  const payload = transition as Record<string, unknown>
  const mode = String(payload.mode || '').trim().toLowerCase()
  const previousLabel = String(payload.previous_label || '').trim()
  const currentLabel = String(payload.current_label || '').trim()
  if (mode === 'switch' && previousLabel && currentLabel) {
    return t('connector_bindings_switched', {
      questId,
      previous: previousLabel,
      current: currentLabel,
    })
  }
  if (mode === 'bind' && currentLabel) {
    return t('connector_bindings_bound', {
      questId,
      current: currentLabel,
    })
  }
  if (mode === 'disconnect') {
    return t('connector_bindings_local_only', { questId })
  }
  return t('connector_bindings_saved')
}

export function QuestSettingsSurface({
  questId,
  snapshot,
  onRefresh,
  layout = 'bounded',
}: {
  questId: string
  snapshot: QuestSummary | null
  onRefresh: () => Promise<void>
  layout?: 'bounded' | 'document'
}) {
  const { toast } = useToast()
  const { t, language } = useI18n('workspace')
  const currentExternalBinding = React.useMemo(() => {
    for (const raw of snapshot?.bound_conversations || []) {
      const parsed = parseConversationId(raw)
      if (!parsed || parsed.connector === 'local') continue
      return {
        connector: parsed.connector,
        conversation_id: parsed.conversation_id,
      }
    }
    return null
  }, [snapshot?.bound_conversations])

  const [connectors, setConnectors] = React.useState<ConnectorSnapshot[]>([])
  const [loadingConnectors, setLoadingConnectors] = React.useState(true)
  const [binding, setBinding] = React.useState(false)
  const [selection, setSelection] = React.useState<Record<string, string>>({})
  const [activeConnectorName, setActiveConnectorName] = React.useState<string | null>(null)
  const [selectionDirty, setSelectionDirty] = React.useState(false)

  const [confirmOpen, setConfirmOpen] = React.useState(false)
  const [confirmPayload, setConfirmPayload] = React.useState<Array<{ connector: string; conversation_id?: string | null }>>([])
  const [conflicts, setConflicts] = React.useState<ConflictItem[]>([])
  const [runnerEnvRows, setRunnerEnvRows] = React.useState<RunnerEnvRow[]>(() =>
    normalizeRunnerEnvRows({})
  )
  const [runnerEnvSaving, setRunnerEnvSaving] = React.useState(false)
  const [runnerConfigRevision, setRunnerConfigRevision] = React.useState<string | null>(null)
  const [savedRunnerEnvRows, setSavedRunnerEnvRows] = React.useState<RunnerEnvRow[]>(() =>
    normalizeRunnerEnvRows({})
  )
  const [workspaceMode, setWorkspaceMode] = React.useState<WorkspaceMode>(() =>
    normalizeWorkspaceMode(snapshot?.workspace_mode)
  )
  const [savedWorkspaceMode, setSavedWorkspaceMode] = React.useState<WorkspaceMode>(() =>
    normalizeWorkspaceMode(snapshot?.workspace_mode)
  )
  const [workspaceModeSaving, setWorkspaceModeSaving] = React.useState(false)
  const [runnerEnvOpen, setRunnerEnvOpen] = React.useState(false)

  const reloadConnectors = React.useCallback(async () => {
    setLoadingConnectors(true)
    try {
      const payload = await client.connectors()
      setConnectors(payload.filter((item) => item.name !== 'local'))
    } finally {
      setLoadingConnectors(false)
    }
  }, [snapshot?.default_runner, snapshot?.runner])

  React.useEffect(() => {
    void reloadConnectors()
    const timer = window.setInterval(() => {
      void reloadConnectors()
    }, 4000)
    return () => {
      window.clearInterval(timer)
    }
  }, [reloadConnectors])

  const reloadRunnerEnv = React.useCallback(async () => {
    const document = await client.configDocument('runners')
    const structured =
      document.meta?.structured_config && typeof document.meta.structured_config === 'object'
        ? (document.meta.structured_config as Record<string, unknown>)
        : {}
    const activeRunnerName = String(snapshot?.runner || snapshot?.default_runner || 'codex').trim().toLowerCase() || 'codex'
    const runnerConfig =
      structured[activeRunnerName] && typeof structured[activeRunnerName] === 'object'
        ? (structured[activeRunnerName] as Record<string, unknown>)
        : {}
    const rows = normalizeRunnerEnvRows(runnerConfig.env, activeRunnerName)
    setRunnerEnvRows(rows)
    setSavedRunnerEnvRows(rows)
    setRunnerConfigRevision(document.revision || null)
  }, [snapshot?.default_runner, snapshot?.runner])

  React.useEffect(() => {
    void reloadRunnerEnv()
  }, [reloadRunnerEnv])

  React.useEffect(() => {
    const nextMode = normalizeWorkspaceMode(snapshot?.workspace_mode)
    setWorkspaceMode(nextMode)
    setSavedWorkspaceMode(nextMode)
  }, [questId, snapshot?.workspace_mode])

  React.useEffect(() => {
    if (!connectors.length) {
      setSelection({})
      if (!selectionDirty) {
        setActiveConnectorName(null)
      }
      return
    }

    setSelection((current) => {
      const next: Record<string, string> = {}
      for (const connector of connectors) {
        const targets = normalizeConnectorTargets(connector)
        const currentValue = current[connector.name] || ''
        const currentValid = targets.some(
          (target) => conversationIdentityKey(target.conversation_id) === conversationIdentityKey(currentValue)
        )
        const boundConversation =
          currentExternalBinding?.connector === connector.name.toLowerCase() ? currentExternalBinding.conversation_id : ''
        next[connector.name] =
          (currentValid ? currentValue : '') ||
          boundConversation ||
          connector.default_target?.conversation_id ||
          targets[0]?.conversation_id ||
          ''
      }
      return next
    })

    if (!selectionDirty) {
      const nextActiveConnectorName = currentExternalBinding
        ? connectors.find((connector) => connector.name.toLowerCase() === currentExternalBinding.connector)?.name || null
        : null
      setActiveConnectorName(nextActiveConnectorName)
    } else {
      setActiveConnectorName((current) =>
        current && connectors.some((connector) => connector.name === current) ? current : null
      )
    }
  }, [connectors, currentExternalBinding, selectionDirty])

  const saveBindings = React.useCallback(
    async (bindings: Array<{ connector: string; conversation_id?: string | null }>, { force }: { force: boolean }) => {
      setBinding(true)
      try {
        const result = (await client.updateQuestBindings(questId, {
          bindings,
          force,
        })) as Record<string, unknown>
        const ok = Boolean(result.ok)
        const status = Number(result.status || 200)
        if (!ok && status === 409) {
          const items = Array.isArray(result.conflicts)
            ? (result.conflicts.filter(
                (item): item is ConflictItem =>
                  Boolean(item) && typeof item === 'object' && !Array.isArray(item) && typeof (item as any).quest_id === 'string'
              ) as ConflictItem[])
            : []
          setConflicts(items)
          setConfirmPayload(bindings)
          setConfirmOpen(true)
          return
        }
        if (!ok) {
          toast({
            title: 'Binding failed',
            description: String(result.message || 'Unable to update connector bindings.'),
            variant: 'destructive',
          })
          return
        }

        toast({
          title: 'Saved',
          description: bindingTransitionDescription(result.binding_transition, questId, t),
        })
        await Promise.all([onRefresh(), reloadConnectors()])
        setSelectionDirty(false)
      } finally {
        setBinding(false)
      }
    },
    [onRefresh, questId, reloadConnectors, t, toast]
  )

  const pendingBinding = React.useMemo(() => {
    if (!activeConnectorName) return null
    const conversationId = String(selection[activeConnectorName] || '').trim()
    if (!conversationId) return null
    return {
      connector: activeConnectorName,
      conversation_id: conversationId,
    }
  }, [activeConnectorName, selection])
  const pendingBindings = React.useMemo(
    () => (pendingBinding ? [pendingBinding] : []),
    [pendingBinding]
  )

  const hasPendingChanges = React.useMemo(
    () =>
      conversationIdentityKey(currentExternalBinding?.conversation_id || '') !== conversationIdentityKey(pendingBinding?.conversation_id || '') ||
      String(currentExternalBinding?.connector || '') !== String(pendingBinding?.connector || '').toLowerCase(),
    [currentExternalBinding, pendingBinding]
  )
  const pendingSwitchDescription = React.useMemo(() => {
    if (!hasPendingChanges) return ''
    const previousLabel = bindingTargetLabel(currentExternalBinding?.conversation_id, {
      localOnly: t('connector_target_local_only'),
      passive: t('connector_target_passive'),
    })
    const nextLabel = pendingBinding
      ? bindingTargetLabel(pendingBinding.conversation_id, {
          localOnly: t('connector_target_local_only'),
          passive: t('connector_target_passive'),
        })
      : t('connector_target_local_only')
    return t('connector_bindings_switched', {
      questId,
      previous: previousLabel,
      current: nextLabel,
    })
  }, [currentExternalBinding, hasPendingChanges, pendingBinding, questId, t])
  const cardItems = React.useMemo<ConnectorTargetRadioItem[]>(() => {
    const items: ConnectorTargetRadioItem[] = [
      {
        value: '__none__',
        connectorName: 'local',
        connectorLabel: t('connector_target_local_only'),
        targetId: t('connector_target_none'),
        boundQuestLabel: t('connector_target_local_access'),
        localOnly: true,
      },
      ...connectors.flatMap((connector) =>
        normalizeConnectorTargets(connector).map((target) => ({
          value: target.conversation_id,
          connectorName: connector.name,
          connectorLabel: connectorLabel(connector, t('connector_bindings_title')),
          targetId: connectorTargetId(target, {
            passive: t('connector_target_passive'),
            unknown: t('connector_target_unknown'),
          }),
          boundQuestLabel: target.bound_quest_id ? `Quest ${target.bound_quest_id}` : t('connector_target_unbound'),
        }))
      ),
    ]
    return items
  }, [connectors, t])
  const selectableTargets = React.useMemo(
    () =>
      connectors.flatMap((connector) =>
        normalizeConnectorTargets(connector).map((target) => ({
          connector,
          target,
        }))
      ),
    [connectors]
  )
  const unavailableConnectors = React.useMemo(
    () => connectors.filter((connector) => normalizeConnectorTargets(connector).length === 0),
    [connectors]
  )
  const selectedTargetOption = React.useMemo(() => {
    if (!pendingBinding) return null
    return (
      selectableTargets.find(
        (item) =>
          item.connector.name === pendingBinding.connector &&
          conversationIdentityKey(item.target.conversation_id) === conversationIdentityKey(pendingBinding.conversation_id)
      ) || null
    )
  }, [pendingBinding, selectableTargets])
  const selectedCardValue = pendingBinding?.conversation_id || '__none__'

  const saveRunnerEnv = React.useCallback(async () => {
    setRunnerEnvSaving(true)
    try {
      const document = await client.configDocument('runners')
      const structured =
        document.meta?.structured_config && typeof document.meta.structured_config === 'object'
          ? ({ ...(document.meta.structured_config as Record<string, unknown>) } as Record<string, unknown>)
          : {}
      const activeRunnerName = String(snapshot?.runner || snapshot?.default_runner || 'codex').trim().toLowerCase() || 'codex'
      const currentRunnerConfig =
        structured[activeRunnerName] && typeof structured[activeRunnerName] === 'object'
          ? ({ ...(structured[activeRunnerName] as Record<string, unknown>) } as Record<string, unknown>)
          : {}
      currentRunnerConfig.env = runnerEnvRowsToPayload(runnerEnvRows)
      structured[activeRunnerName] = currentRunnerConfig
      const result = await client.saveConfig('runners', {
        structured,
        revision: document.revision || runnerConfigRevision || undefined,
      })
      if (!result.ok) {
        toast({
          title: 'Save failed',
          description: String(result.message || 'Unable to update runner environment variables.'),
          variant: 'destructive',
        })
        return
      }
      await Promise.all([reloadRunnerEnv(), onRefresh()])
      toast({
        title: 'Saved',
        description: 'Runner environment variables will be injected automatically on the next run.',
      })
    } finally {
      setRunnerEnvSaving(false)
    }
  }, [onRefresh, reloadRunnerEnv, runnerConfigRevision, runnerEnvRows, snapshot?.default_runner, snapshot?.runner, toast])

  const runnerEnvDirty = React.useMemo(
    () => JSON.stringify(runnerEnvRows) !== JSON.stringify(savedRunnerEnvRows),
    [runnerEnvRows, savedRunnerEnvRows]
  )
  const workspaceModeDirty = workspaceMode !== savedWorkspaceMode
  const activeRunnerName = String(snapshot?.runner || snapshot?.default_runner || 'codex').trim().toLowerCase() || 'codex'
  const activeRunnerDefaultEnvKeys = DEFAULT_RUNNER_ENV_KEYS[activeRunnerName] || []

  const workspaceModeItems = React.useMemo(
    () => [
      { value: 'copilot' as WorkspaceMode, label: t('quest_settings_mode_copilot') },
      { value: 'autonomous' as WorkspaceMode, label: t('quest_settings_mode_autonomous') },
    ],
    [t]
  )

  const saveWorkspaceMode = React.useCallback(async () => {
    setWorkspaceModeSaving(true)
    try {
      const result = await client.updateQuestSettings(questId, {
        workspace_mode: workspaceMode,
      })
      if (!result.ok) {
        toast({
          title: 'Save failed',
          description: 'Unable to update workspace mode.',
          variant: 'destructive',
        })
        return
      }
      setSavedWorkspaceMode(workspaceMode)
      await onRefresh()
      toast({
        title: t('quest_settings_mode_saved_title'),
        description:
          workspaceMode === 'copilot'
            ? t('quest_settings_mode_saved_desc_copilot')
            : t('quest_settings_mode_saved_desc_autonomous'),
      })
    } catch (error) {
      toast({
        title: 'Save failed',
        description: error instanceof Error ? error.message : 'Unable to update workspace mode.',
        variant: 'destructive',
      })
    } finally {
      setWorkspaceModeSaving(false)
    }
  }, [onRefresh, questId, t, toast, workspaceMode])

  return (
    <div className={layout === 'document' ? 'p-4 sm:p-5' : 'feed-scrollbar h-full min-h-0 overflow-y-auto p-4 sm:p-5'}>
      <div className="space-y-5 rounded-[28px] border border-black/[0.06] bg-white/[0.42] p-4 shadow-card backdrop-blur-xl dark:border-white/[0.08] dark:bg-white/[0.03] sm:p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-foreground">
              {language === 'zh' ? 'Quest 配置' : 'Quest Configuration'}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {language === 'zh'
                ? `配置 ${questId} 的工作模式、环境变量和通知目标`
                : `Configure workspace mode, environment variables, and notification target for ${questId}`
              }
            </div>
          </div>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => void reloadConnectors()}
            disabled={loadingConnectors}
            className="shrink-0"
          >
            <RefreshCw className={cn('mr-2 h-4 w-4', loadingConnectors && 'animate-spin')} />
            {language === 'zh' ? '刷新' : 'Refresh'}
          </Button>
        </div>

        <div className="space-y-5">
          <EnhancedCard
            enableSpotlight={false}
            className="border border-border/60 bg-[var(--ds-panel-elevated)]/70 backdrop-blur-xl shadow-[var(--ds-shadow-md)]"
          >
            <div className="p-4 space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-foreground">{t('quest_settings_mode_title')}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {t('quest_settings_mode_desc')}
                  </div>
                  {workspaceModeDirty ? (
                    <div className="mt-2 text-xs font-medium text-[var(--ds-brand)]">
                      {t('quest_settings_mode_unsaved')}
                    </div>
                  ) : null}
                </div>
                <Button
                  type="button"
                  size="sm"
                  onClick={() => void saveWorkspaceMode()}
                  disabled={workspaceModeSaving || !workspaceModeDirty}
                >
                  {t('quest_settings_mode_save')}
                </Button>
              </div>

              <Separator className="bg-border/50" />

              <div className="flex items-center justify-between gap-3">
                <div className="text-xs text-muted-foreground">
                  {questId}
                </div>
                <SegmentedControl
                  value={workspaceMode}
                  onValueChange={(value) => setWorkspaceMode(value)}
                  items={workspaceModeItems}
                  size="sm"
                  ariaLabel={t('quest_settings_mode_title')}
                />
              </div>
            </div>
          </EnhancedCard>

          <Collapsible open={runnerEnvOpen} onOpenChange={setRunnerEnvOpen}>
            <EnhancedCard
              enableSpotlight={false}
              className="border border-border/60 bg-[var(--ds-panel-elevated)]/70 backdrop-blur-xl shadow-[var(--ds-shadow-md)]"
            >
              <div className="p-4 space-y-4">
                <CollapsibleTrigger asChild>
                  <button className="flex w-full items-start justify-between gap-3 text-left">
                    <div className="flex-1">
                      <div className="text-sm font-medium text-foreground">
                        {language === 'zh' ? '环境变量' : 'Environment Variables'}
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {language === 'zh'
                          ? '为这个 quest 设置自定义环境变量。空值将被忽略。'
                          : 'Set custom environment variables for this quest. Empty values are ignored.'
                        }
                      </div>
                      {runnerEnvDirty ? (
                        <div className="mt-2 text-xs font-medium text-[var(--ds-brand)]">
                          {language === 'zh' ? '有未保存的更改。点击"保存环境变量"以应用。' : 'Unsaved changes. Click "Save variables" to apply.'}
                        </div>
                      ) : null}
                    </div>
                    {runnerEnvOpen ? (
                      <ChevronUp className="h-5 w-5 text-muted-foreground shrink-0 mt-0.5" />
                    ) : (
                      <ChevronDown className="h-5 w-5 text-muted-foreground shrink-0 mt-0.5" />
                    )}
                  </button>
                </CollapsibleTrigger>

                <CollapsibleContent>
                  {runnerEnvOpen && (
                    <>
                      <div className="flex items-center gap-2 pt-2">
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          onClick={() =>
                            setRunnerEnvRows((current) => [...current, { key: '', value: '' }])
                          }
                        >
                          <Plus className="mr-2 h-4 w-4" />
                          {language === 'zh' ? '添加' : 'Add'}
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          onClick={() => void saveRunnerEnv()}
                          disabled={runnerEnvSaving || !runnerEnvDirty}
                        >
                          <Link2 className="mr-2 h-4 w-4" />
                          {language === 'zh' ? '保存环境变量' : 'Save variables'}
                        </Button>
                      </div>

                      <Separator className="bg-border/50" />

                      <div className="space-y-3">
                        {runnerEnvRows.map((row, index) => (
                          <div key={`${row.key || 'env'}-${index}`} className="grid gap-3 md:grid-cols-[minmax(0,0.95fr)_minmax(0,1.35fr)_auto]">
                            <Input
                              value={row.key}
                              onChange={(event) =>
                                setRunnerEnvRows((current) =>
                                  current.map((item, itemIndex) =>
                                    itemIndex === index ? { ...item, key: event.target.value } : item
                                  )
                                )
                              }
                              placeholder={index < activeRunnerDefaultEnvKeys.length ? activeRunnerDefaultEnvKeys[index] : 'ENV_NAME'}
                            />
                            <Input
                              value={row.value}
                              onChange={(event) =>
                                setRunnerEnvRows((current) =>
                                  current.map((item, itemIndex) =>
                                    itemIndex === index ? { ...item, value: event.target.value } : item
                                  )
                                )
                              }
                              placeholder={language === 'zh' ? '值' : 'value'}
                            />
                            <Button
                              type="button"
                              size="icon"
                              variant="ghost"
                              className="shrink-0"
                              onClick={() =>
                                setRunnerEnvRows((current) => {
                                  if (index < activeRunnerDefaultEnvKeys.length) {
                                    return current.map((item, itemIndex) =>
                                      itemIndex === index ? { ...item, value: '' } : item
                                    )
                                  }
                                  return current.filter((_, itemIndex) => itemIndex !== index)
                                })
                              }
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </CollapsibleContent>
              </div>
            </EnhancedCard>
          </Collapsible>

          <EnhancedCard
            enableSpotlight={false}
            className="border border-border/60 bg-[var(--ds-panel-elevated)]/70 backdrop-blur-xl shadow-[var(--ds-shadow-md)]"
          >
            <div className="p-4 space-y-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-foreground">{t('connector_bindings_title')}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {t('connector_bindings_subtitle', { questId })}
                  </div>
                  {pendingSwitchDescription ? <div className="mt-2 text-xs text-[var(--ds-brand)]">{pendingSwitchDescription}</div> : null}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => void saveBindings(pendingBindings, { force: false })}
                    disabled={binding || !hasPendingChanges}
                  >
                    <Link2 className="mr-2 h-4 w-4" />
                    {t('connector_bindings_save')}
                  </Button>
                </div>
              </div>

              <Separator className="bg-border/50" />

              {connectors.length === 0 ? (
                <div className="text-sm text-muted-foreground">
                  {loadingConnectors ? t('connector_bindings_loading') : t('connector_bindings_empty')}
                </div>
              ) : (
                <div className="space-y-3">
                  <ConnectorTargetRadioGroup
                    ariaLabel={`Connector target selection for ${questId}`}
                    items={cardItems}
                    value={selectedCardValue}
                    onChange={(value) => {
                      setSelectionDirty(true)
                      if (value === '__none__') {
                        setActiveConnectorName(null)
                        return
                      }
                      const parsed = parseConversationId(value)
                      if (!parsed?.connector) {
                        return
                      }
                      const connectorName =
                        connectors.find((item) => item.name.toLowerCase() === parsed.connector)?.name || null
                      if (!connectorName) {
                        return
                      }
                      setSelection((current) => ({
                        ...current,
                        [connectorName]: value,
                      }))
                      setActiveConnectorName(connectorName)
                    }}
                  />

                  {selectedTargetOption?.target.bound_quest_id && selectedTargetOption.target.bound_quest_id !== questId ? (
                    <div className="flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2">
                      <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-600" />
                      <div className="text-xs text-amber-800 dark:text-amber-200">
                        {t('connector_bindings_reassign', {
                          questId: String(selectedTargetOption.target.bound_quest_id || ''),
                        })}
                      </div>
                    </div>
                  ) : null}

                  {unavailableConnectors.length > 0 ? (
                    <div className="rounded-xl border border-dashed border-border/50 bg-background/20 px-3 py-3 text-xs text-muted-foreground">
                      {t('connector_bindings_waiting', {
                        connectors: unavailableConnectors.map((connector) => connectorLabel(connector, t('connector_bindings_title'))).join(' · '),
                      })}
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          </EnhancedCard>

          <EnhancedCard
            enableSpotlight={false}
            className="border border-border/60 bg-[var(--ds-panel-elevated)]/70 backdrop-blur-xl shadow-[var(--ds-shadow-md)]"
          >
            <div className="p-4 space-y-3">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <div className="text-sm font-medium text-foreground">
                    {language === 'zh' ? '最近活动已移到单独页面' : 'Recent activity now lives on its own page'}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {language === 'zh'
                      ? '设置页只保留会影响这个 quest 行为的选项。最近活动、错误趋势和工具分布请到 Activity 页面查看。'
                      : 'Settings now stays focused on options that change this quest. Open Activity when you want trends, tool mix, or recent movement.'}
                  </div>
                </div>
                <Button size="sm" variant="outline" asChild>
                  <Link to={`/settings/quests/${encodeURIComponent(questId)}?view=activity`}>
                    {language === 'zh' ? '打开 Activity' : 'Open Activity'}
                  </Link>
                </Button>
              </div>
            </div>
          </EnhancedCard>
        </div>
      </div>

      <ConfirmModal
        open={confirmOpen}
        onClose={() => {
          if (binding) return
          setConfirmOpen(false)
        }}
        onConfirm={() => {
          if (!confirmPayload.length) return
          setConfirmOpen(false)
          void saveBindings(confirmPayload, { force: true })
        }}
        loading={binding}
        title="Rebind connector?"
        description={
          conflicts.length
            ? `${pendingSwitchDescription || 'This connector target is already bound elsewhere.'} It will be unbound from: ${conflicts
                .map((item) => item.quest_id)
                .filter(Boolean)
                .join(', ')}`
            : pendingSwitchDescription || 'This connector target is already bound elsewhere.'
        }
        confirmText="Rebind"
        cancelText="Cancel"
        variant="warning"
      />
    </div>
  )
}

export default QuestSettingsSurface
