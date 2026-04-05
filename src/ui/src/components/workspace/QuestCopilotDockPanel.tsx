'use client'

import * as React from 'react'

import { SegmentedControl, type SegmentedItem } from '@/components/ui/segmented-control'
import { useQuestWorkspace } from '@/lib/acp'
import type {
  AiManusChatMeta,
  CopilotPrefill,
} from '@/lib/plugins/ai-manus/view-types'
import { useI18n } from '@/lib/i18n/useI18n'

import { QuestConnectorChatView } from './QuestConnectorChatView'
import { useCopilotDockCallbacks } from './CopilotDockOverlay'
import { QuestStudioTraceView } from './QuestStudioTraceView'
import type { QuestWorkspaceState } from './QuestWorkspaceSurface'

type QuestCopilotDockPanelProps = {
  questId: string
  title: string
  readOnly?: boolean
  prefill?: CopilotPrefill | null
  workspace?: QuestWorkspaceState
}

type QuestCopilotMode = 'chat' | 'studio'

function isParkedCopilotWorkspace(workspace: QuestWorkspaceState) {
  const snapshot = workspace.snapshot
  const workspaceMode = String(snapshot?.workspace_mode || '').trim().toLowerCase()
  const continuationPolicy = String(snapshot?.continuation_policy || '').trim().toLowerCase()
  const activeRunId = String(snapshot?.active_run_id || '').trim()
  const bashRunningCount = Number(snapshot?.counts?.bash_running_count || 0)
  const latestBashSession =
    snapshot?.summary?.latest_bash_session &&
    typeof snapshot.summary.latest_bash_session === 'object' &&
    !Array.isArray(snapshot.summary.latest_bash_session)
      ? snapshot.summary.latest_bash_session
      : null
  const latestBashKind = String((latestBashSession as Record<string, unknown> | null)?.kind || '')
    .trim()
    .toLowerCase()
  const latestBashId = String((latestBashSession as Record<string, unknown> | null)?.bash_id || '')
    .trim()
  return (
    workspaceMode === 'copilot' &&
    continuationPolicy === 'wait_for_user_or_resume' &&
    !activeRunId &&
    !workspace.loading &&
    !workspace.restoring &&
    !workspace.error &&
    (bashRunningCount === 0 ||
      (bashRunningCount === 1 &&
        latestBashKind === 'terminal' &&
        (latestBashId === '' || latestBashId === 'terminal-main')))
  )
}

function resolveStatusText(args: {
  loading: boolean
  restoring: boolean
  stopping: boolean
  hasLiveRun: boolean
  error?: string | null
  activeToolCount: number
  connectionState: 'connecting' | 'connected' | 'reconnecting' | 'error'
  snapshotStatus?: string | null
  readyLabel?: string | null
  t: (key: string, variables?: Record<string, string | number>, fallback?: string) => string
}) {
  const { loading, restoring, stopping, hasLiveRun, error, activeToolCount, connectionState, snapshotStatus, readyLabel, t } = args
  if (stopping) return t('copilot_quest_status_stopping')
  if (restoring) return t('copilot_quest_status_restoring')
  if (loading) return t('copilot_quest_status_loading')
  if (connectionState === 'reconnecting') return t('copilot_quest_status_reconnecting')
  if (connectionState === 'connecting') return t('copilot_quest_status_connecting')
  if (hasLiveRun || activeToolCount > 0) {
    return activeToolCount > 0
      ? t('copilot_quest_status_working_tools', { count: activeToolCount })
      : t('copilot_quest_status_working')
  }
  if (error || connectionState === 'error') return t('copilot_quest_status_interrupted')
  if (snapshotStatus) return snapshotStatus
  return readyLabel || t('copilot_quest_status_ready')
}

export function QuestCopilotDockPanel({
  questId,
  title,
  readOnly: _readOnly,
  prefill,
  workspace: providedWorkspace,
}: QuestCopilotDockPanelProps) {
  const { t } = useI18n('workspace')
  const dockCallbacks = useCopilotDockCallbacks()
  const internalWorkspace = useQuestWorkspace(providedWorkspace ? null : questId)
  const workspace = providedWorkspace ?? internalWorkspace
  const [stopping, setStopping] = React.useState(false)
  const [statusTransition, setStatusTransition] = React.useState<{
    current: string | null
    previous: string | null
    key: number
  }>({
    current: null,
      previous: null,
      key: 0,
  })
  const [mode, setMode] = React.useState<QuestCopilotMode>('studio')

  React.useEffect(() => {
    setMode('studio')
  }, [questId])

  React.useEffect(() => {
    setStopping(false)
    setStatusTransition({
      current: null,
      previous: null,
      key: 0,
    })
  }, [mode, questId])

  React.useEffect(() => {
    dockCallbacks?.onActionsChange(null)
  }, [dockCallbacks, mode])

  const parkedCopilot = React.useMemo(() => isParkedCopilotWorkspace(workspace), [workspace])
  const effectiveHasLiveRun = parkedCopilot ? false : workspace.hasLiveRun
  const effectiveStreaming = parkedCopilot ? false : workspace.streaming
  const effectiveActiveToolCount = parkedCopilot ? 0 : workspace.activeToolCount

  const isResponding = React.useMemo(
    () =>
      stopping ||
      workspace.loading ||
      workspace.restoring ||
      workspace.connectionState === 'connecting' ||
      workspace.connectionState === 'reconnecting' ||
      effectiveHasLiveRun ||
      effectiveActiveToolCount > 0 ||
      effectiveStreaming,
    [
      effectiveActiveToolCount,
      effectiveHasLiveRun,
      effectiveStreaming,
      stopping,
      workspace.connectionState,
      workspace.loading,
      workspace.restoring,
    ]
  )

  const statusText = React.useMemo(
    () =>
      resolveStatusText({
        loading: workspace.loading,
        restoring: workspace.restoring,
        stopping,
        hasLiveRun: effectiveHasLiveRun || effectiveStreaming,
        error: workspace.error,
        activeToolCount: effectiveActiveToolCount,
        connectionState: workspace.connectionState,
        snapshotStatus: workspace.snapshot?.summary?.status_line ?? null,
        readyLabel:
          mode === 'studio'
            ? t('copilot_trace_ready', undefined, 'Studio trace ready')
            : t('copilot_quest_status_ready'),
        t,
      }),
    [
      stopping,
      effectiveActiveToolCount,
      effectiveHasLiveRun,
      effectiveStreaming,
      isResponding,
      workspace.connectionState,
      workspace.error,
      workspace.loading,
      workspace.restoring,
      workspace.snapshot?.summary?.status_line,
      t,
    ]
  )

  React.useEffect(() => {
    setStatusTransition((prev) => {
      if (prev.current === statusText) {
        return prev
      }
      return {
        current: statusText,
        previous: prev.current,
        key: prev.key + 1,
      }
    })
  }, [statusText])

  const handleStopRun = React.useCallback(async () => {
    if (stopping) return
    setStopping(true)
    try {
      await workspace.stopRun()
    } finally {
      setStopping(false)
    }
  }, [stopping, workspace])

  const showStopButton = React.useMemo(
    () => stopping || effectiveHasLiveRun || effectiveActiveToolCount > 0 || effectiveStreaming,
    [effectiveActiveToolCount, effectiveHasLiveRun, effectiveStreaming, stopping]
  )

  React.useEffect(() => {
    const meta: AiManusChatMeta = {
      threadId: `quest:${questId}:${mode}`,
      historyOpen: false,
      isResponding,
      toolCount: effectiveActiveToolCount,
      ready: !workspace.loading,
      isRestoring: workspace.restoring,
      restoreAttempted: true,
      hasHistory: workspace.feed.length > 0,
      error: workspace.error ?? null,
      title,
      statusText: statusTransition.current ?? statusText,
      statusPrevText: statusTransition.previous,
      statusKey: statusTransition.key,
      toolPanelVisible: false,
      toolToggleVisible: false,
      attachmentsDrawerOpen: false,
      fixWithAiRunning: false,
    }
    dockCallbacks?.onMetaChange(meta)
  }, [
    dockCallbacks,
    mode,
    questId,
    statusText,
    title,
    workspace.error,
    workspace.feed.length,
    effectiveActiveToolCount,
    effectiveHasLiveRun,
    effectiveStreaming,
    workspace.loading,
    workspace.restoring,
    statusTransition.current,
    statusTransition.key,
    statusTransition.previous,
    isResponding,
    statusText,
    stopping,
  ])

  const tabItems = React.useMemo<SegmentedItem<QuestCopilotMode>[]>(
    () => [
      { value: 'chat', label: t('copilot_chat_tab') },
      { value: 'studio', label: t('copilot_studio_tab') },
    ],
    [t]
  )

  React.useEffect(() => {
    dockCallbacks?.onHeaderExtraChange(
      <div data-onboarding-id="quest-copilot-mode-tabs">
        <SegmentedControl
          value={mode}
          onValueChange={setMode}
          items={tabItems}
          size="sm"
          ariaLabel={t('copilot_mode_tabs')}
          className="quest-copilot-mode-tabs border-black/[0.08] bg-white/[0.62] backdrop-blur-sm dark:border-white/[0.10] dark:bg-white/[0.06]"
        />
      </div>
    )
    return () => {
      dockCallbacks?.onHeaderExtraChange(null)
    }
  }, [dockCallbacks, mode, t, tabItems])

  return (
    <div className="flex h-full min-h-0 flex-col" data-onboarding-id="workspace-copilot-panel">
      {mode === 'chat' ? (
        <QuestConnectorChatView
          feed={workspace.feed}
          loading={workspace.loading}
          restoring={workspace.restoring}
          streaming={effectiveStreaming}
          activeToolCount={effectiveActiveToolCount}
          connectionState={workspace.connectionState}
          error={workspace.error}
          stopping={stopping}
          showStopButton={showStopButton}
          slashCommands={workspace.slashCommands}
          hasOlderHistory={workspace.hasOlderHistory}
          loadingOlderHistory={workspace.loadingOlderHistory}
          onLoadOlderHistory={workspace.loadOlderHistory}
          onSubmit={workspace.submit}
          onStopRun={handleStopRun}
          prefill={prefill}
        />
      ) : (
        <QuestStudioTraceView
          questId={questId}
          feed={workspace.feed}
          snapshot={workspace.snapshot}
          loading={workspace.loading}
          restoring={workspace.restoring}
          streaming={effectiveStreaming}
          activeToolCount={effectiveActiveToolCount}
          connectionState={workspace.connectionState}
          error={workspace.error}
          stopping={stopping}
          showStopButton={showStopButton}
          slashCommands={workspace.slashCommands}
          hasOlderHistory={workspace.hasOlderHistory}
          loadingOlderHistory={workspace.loadingOlderHistory}
          onLoadOlderHistory={workspace.loadOlderHistory}
          onSubmit={workspace.submit}
          onStopRun={handleStopRun}
          prefill={prefill}
        />
      )}
    </div>
  )
}

export default QuestCopilotDockPanel
