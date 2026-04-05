'use client'

import * as React from 'react'

import { useToast } from '@/components/ui/toast'
import { useI18n } from '@/lib/i18n/useI18n'
import type { CopilotPrefill } from '@/lib/plugins/ai-manus/view-types'
import type { FeedItem, QuestSummary } from '@/types'
import { QuestCopilotComposer } from './QuestCopilotComposer'
import { QuestCopilotPaneLayout } from './QuestCopilotPaneLayout'
import { QuestStudioDirectTimeline } from './QuestStudioDirectTimeline'

type ConnectorCommand = {
  name: string
  description?: string
}

type QuestStudioTraceViewProps = {
  questId: string
  feed: FeedItem[]
  snapshot?: QuestSummary | null
  loading: boolean
  restoring: boolean
  streaming: boolean
  activeToolCount: number
  connectionState: 'connecting' | 'connected' | 'reconnecting' | 'error'
  error?: string | null
  stopping?: boolean
  showStopButton?: boolean
  slashCommands?: ConnectorCommand[]
  hasOlderHistory?: boolean
  loadingOlderHistory?: boolean
  onLoadOlderHistory?: () => Promise<void>
  onSubmit: (message: string) => Promise<void>
  onStopRun: () => Promise<void>
  prefill?: CopilotPrefill | null
}

export function QuestStudioTraceView({
  questId,
  feed,
  snapshot,
  loading,
  restoring,
  streaming,
  activeToolCount,
  connectionState,
  error,
  stopping = false,
  showStopButton = false,
  slashCommands = [],
  hasOlderHistory = false,
  loadingOlderHistory = false,
  onLoadOlderHistory,
  onSubmit,
  onStopRun,
  prefill = null,
}: QuestStudioTraceViewProps) {
  const { t } = useI18n('workspace')
  const { addToast } = useToast()
  const [input, setInput] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const statusLine = React.useMemo(() => {
    if (error) {
      return error
    }
    if (restoring || loading) {
      return t('copilot_trace_restoring', undefined, 'Restoring recent Studio trace…')
    }
    if (connectionState === 'connecting') {
      return t('copilot_trace_connecting', undefined, 'Connecting to Studio trace…')
    }
    if (connectionState === 'reconnecting') {
      return t('copilot_trace_reconnecting', undefined, 'Reconnecting to Studio trace…')
    }
    if (streaming) {
      return activeToolCount > 0
        ? t('copilot_trace_streaming_tools', { count: activeToolCount }, 'Streaming reply · {count} tools running')
        : t('copilot_trace_streaming', undefined, 'Streaming reply')
    }
    if (activeToolCount > 0) {
      return t('copilot_trace_tools_running', { count: activeToolCount }, '{count} tools running')
    }
    return t('copilot_trace_ready', undefined, 'Studio trace ready')
  }, [activeToolCount, connectionState, error, loading, restoring, streaming, t])

  const handleSubmit = React.useCallback(async () => {
    const trimmed = input.trim()
    if (!trimmed || submitting) return
    setSubmitting(true)
    try {
      await onSubmit(trimmed)
      setInput('')
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught)
      addToast({
        title: t('copilot_send_failed_title', undefined, 'Send failed'),
        message,
        variant: 'error',
      })
    } finally {
      setSubmitting(false)
    }
  }, [addToast, input, onSubmit, submitting, t])

  const handleStop = React.useCallback(async () => {
    if (stopping) return
    try {
      await onStopRun()
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught)
      addToast({
        title: t('copilot_stop', undefined, 'Stop'),
        message,
        variant: 'error',
      })
    }
  }, [addToast, onStopRun, stopping, t])

  React.useEffect(() => {
    if (!prefill?.text) return
    setInput((current) => {
      const trimmed = current.trim()
      if (!trimmed) return prefill.text
      if (trimmed.includes(prefill.text)) return current
      return `${current.replace(/\s*$/, '')}\n\n${prefill.text}`
    })
  }, [prefill])

  return (
    <QuestCopilotPaneLayout
      statusLine={statusLine}
      footer={
        <QuestCopilotComposer
          value={input}
          onValueChange={setInput}
          onSubmit={handleSubmit}
          onStop={handleStop}
          submitting={submitting}
          stopping={stopping}
          showStopButton={showStopButton}
          slashCommands={slashCommands}
          placeholder={t('copilot_connector_placeholder')}
          enterHint={t('copilot_connector_enter_hint')}
          sendLabel={t('copilot_send')}
          stopLabel={t('copilot_stop')}
          focusToken={prefill?.focus ? prefill.token : null}
        />
      }
    >
      {({ bottomInset }) => (
        <QuestStudioDirectTimeline
          questId={questId}
          feed={feed}
          loading={loading}
          restoring={restoring}
          streaming={streaming}
          activeToolCount={activeToolCount}
          connectionState={connectionState}
          error={error}
          snapshot={snapshot}
          hasOlderHistory={hasOlderHistory}
          loadingOlderHistory={loadingOlderHistory}
          onLoadOlderHistory={onLoadOlderHistory}
          emptyLabel={t('copilot_studio_empty', undefined, 'Copilot trace appears here.')}
          bottomInset={bottomInset}
        />
      )}
    </QuestCopilotPaneLayout>
  )
}

export default QuestStudioTraceView
