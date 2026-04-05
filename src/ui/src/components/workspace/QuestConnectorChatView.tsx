'use client'

import * as React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Check, CheckCheck, Loader2, TriangleAlert } from 'lucide-react'

import { useToast } from '@/components/ui/toast'
import { useI18n } from '@/lib/i18n/useI18n'
import type { CopilotPrefill } from '@/lib/plugins/ai-manus/view-types'
import { useTokenStream } from '@/lib/plugins/ai-manus/hooks/useTokenStream'
import { ChatScrollProvider } from '@/lib/plugins/ai-manus/lib/chat-scroll-context'
import { buildQuestTranscriptMessages } from '@/lib/questTranscript'
import { useAutoFollowScroll } from '@/lib/useAutoFollowScroll'
import { cn } from '@/lib/utils'
import type { FeedItem } from '@/types'
import { QuestCopilotComposer } from './QuestCopilotComposer'
import { QuestCopilotPaneLayout } from './QuestCopilotPaneLayout'

type ConnectorCommand = {
  name: string
  description?: string
}

type QuestConnectorChatViewProps = {
  feed: FeedItem[]
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

type ConnectorMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt?: string
  streaming?: boolean
  badge?: string | null
  emphasis?: 'message' | 'artifact'
  deliveryState?: string | null
}

function formatTime(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    month: 'short',
    day: 'numeric',
  }).format(date)
}

export function buildQuestConnectorMessages(feed: FeedItem[]): ConnectorMessage[] {
  return buildQuestTranscriptMessages(feed)
}

function DeliveryIndicator({ state }: { state?: string | null }) {
  if (!state) return null
  const normalized = state.trim().toLowerCase()
  if (!normalized) return null
  if (normalized === 'sending') {
    return <Loader2 className="h-3 w-3 animate-spin text-white/70" />
  }
  if (normalized === 'sent') {
    return <Check className="h-3 w-3 text-white/70" />
  }
  if (normalized === 'delivered') {
    return <CheckCheck className="h-3 w-3 text-white/70" />
  }
  if (normalized === 'failed') {
    return <TriangleAlert className="h-3 w-3 text-rose-300" />
  }
  return (
    <span className="text-[10px] leading-none text-white/60">{normalized}</span>
  )
}

function MessageBubble({
  item,
  animateText,
}: {
  item: ConnectorMessage
  animateText: boolean
}) {
  const isUser = item.role === 'user'
  const isAssistant = item.role === 'assistant'
  const contentRef = React.useRef<HTMLDivElement | null>(null)

  useTokenStream({
    ref: contentRef,
    active: animateText,
    contentKey: `${item.id}:${item.content}`,
    mode: item.emphasis === 'artifact' ? 'status' : 'assistant',
  })

  return (
    <div
      className={cn(
        'flex w-full flex-col gap-1',
        isUser ? 'items-end' : 'items-start'
      )}
    >
      <div
        className={cn(
          'min-w-0 max-w-[92%] overflow-hidden rounded-2xl px-3.5 py-2.5 text-sm leading-6',
          isUser
            ? 'bg-[#2F3437] text-white'
            : item.emphasis === 'artifact'
              ? 'border border-black/[0.05] bg-[rgba(159,177,194,0.12)] text-foreground dark:border-white/[0.08] dark:bg-white/[0.06] dark:text-white/90'
              : 'border border-black/[0.05] bg-[rgba(255,251,246,0.9)] text-foreground dark:border-white/[0.08] dark:bg-white/[0.06] dark:text-white/90'
        )}
      >
        {item.badge && isAssistant ? (
          <div className="mb-1 text-[11px] font-medium text-muted-foreground dark:text-white/60">
            {item.badge}
          </div>
        ) : null}
        <div
          ref={contentRef}
          className={cn(
            'ds-copilot-markdown prose prose-sm max-w-none whitespace-pre-wrap break-words text-[12.5px] leading-[1.68] [overflow-wrap:anywhere]',
            isUser ? 'prose-invert text-white' : 'text-foreground dark:prose-invert'
          )}
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.content}</ReactMarkdown>
        </div>
      </div>
      {(item.createdAt || (isUser && item.deliveryState)) ? (
        <div className={cn('flex items-center gap-2 text-[10px]', isUser ? 'text-white/55' : 'text-muted-foreground')}>
          {isUser ? <DeliveryIndicator state={item.deliveryState} /> : null}
          {item.createdAt ? <span>{formatTime(item.createdAt)}</span> : null}
        </div>
      ) : null}
    </div>
  )
}

export function QuestConnectorChatView({
  feed,
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
}: QuestConnectorChatViewProps) {
  const { t } = useI18n('workspace')
  const { addToast } = useToast()
  const [input, setInput] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const listRef = React.useRef<HTMLDivElement | null>(null)
  const contentRef = React.useRef<HTMLDivElement | null>(null)
  const chatMessages = React.useMemo(() => buildQuestConnectorMessages(feed), [feed])
  const displayMessages = chatMessages
  const latestAnimatedMessageId = React.useMemo(() => {
    for (let index = chatMessages.length - 1; index >= 0; index -= 1) {
      const item = chatMessages[index]
      if (item.role === 'assistant' && item.content.trim()) {
        return item.id
      }
    }
    return null
  }, [chatMessages])
  const { isNearBottom } = useAutoFollowScroll({
    scrollRef: listRef,
    contentRef,
    deps: [chatMessages.length, streaming, activeToolCount],
  })
  const prependAnchorRef = React.useRef<{ active: boolean; scrollHeight: number; scrollTop: number }>({
    active: false,
    scrollHeight: 0,
    scrollTop: 0,
  })

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

  const handleLoadOlderHistory = React.useCallback(async () => {
    if (!hasOlderHistory || loadingOlderHistory || !onLoadOlderHistory) return
    const root = listRef.current
    if (root) {
      prependAnchorRef.current = {
        active: true,
        scrollHeight: root.scrollHeight,
        scrollTop: root.scrollTop,
      }
    }
    await onLoadOlderHistory()
  }, [hasOlderHistory, loadingOlderHistory, onLoadOlderHistory])

  React.useEffect(() => {
    if (!prependAnchorRef.current.active || loadingOlderHistory) {
      return
    }
    const root = listRef.current
    if (!root) {
      prependAnchorRef.current.active = false
      return
    }
    const delta = root.scrollHeight - prependAnchorRef.current.scrollHeight
    root.scrollTop = prependAnchorRef.current.scrollTop + Math.max(delta, 0)
    prependAnchorRef.current.active = false
  }, [chatMessages.length, loadingOlderHistory])

  const statusLine = React.useMemo(() => {
    if (error) {
      return error
    }
    if (restoring || loading) {
      return t('copilot_quest_status_restoring')
    }
    if (connectionState === 'connecting') {
      return t('copilot_quest_status_connecting')
    }
    if (connectionState === 'reconnecting') {
      return t('copilot_quest_status_reconnecting')
    }
    if (streaming || activeToolCount > 0) {
      return activeToolCount > 0
        ? t('copilot_quest_status_working_tools', { count: activeToolCount })
        : t('copilot_quest_status_working')
    }
    return undefined
  }, [activeToolCount, connectionState, error, loading, restoring, streaming, t])

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
        <ChatScrollProvider value={{ isNearBottom }}>
          <div
            ref={listRef}
            className="feed-scrollbar flex-1 min-h-0 overflow-x-hidden overflow-y-auto px-4 pt-4"
            style={{
              paddingBottom: bottomInset,
              scrollPaddingBottom: bottomInset,
            }}
            onWheel={(event) => {
              const root = listRef.current
              if (!root || event.deltaY >= 0 || root.scrollTop > 24) {
                return
              }
              void handleLoadOlderHistory()
            }}
          >
            <div ref={contentRef} className="flex min-w-0 flex-col gap-3">
              {hasOlderHistory ? (
                <div className="flex justify-center pb-1">
                  <button
                    type="button"
                    className="rounded-full border border-black/[0.08] bg-white/[0.88] px-3 py-1 text-[11px] text-muted-foreground transition hover:bg-white dark:border-white/[0.10] dark:bg-white/[0.05] dark:hover:bg-white/[0.08]"
                    disabled={loadingOlderHistory}
                    onClick={() => void handleLoadOlderHistory()}
                  >
                    {loadingOlderHistory
                      ? t('copilot_trace_loading_older', undefined, 'Loading older updates...')
                      : t('copilot_trace_load_older', undefined, 'Load older updates')}
                  </button>
                </div>
              ) : null}
              {displayMessages.map((item) => (
                <MessageBubble
                  key={item.id}
                  item={item}
                  animateText={
                    item.role === 'assistant' &&
                    latestAnimatedMessageId === item.id &&
                    Boolean(item.streaming || streaming)
                  }
                />
              ))}

              {chatMessages.length === 0 ? (
                <div className="pl-1 text-xs text-muted-foreground">
                  {restoring || loading ? t('copilot_connector_restoring') : t('copilot_connector_ready')}
                </div>
              ) : null}

              {(loading || restoring) && chatMessages.length === 0 ? (
                <div className="flex justify-start py-1 pl-1">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              ) : null}
            </div>
          </div>
        </ChatScrollProvider>
      )}
    </QuestCopilotPaneLayout>
  )
}

export default QuestConnectorChatView
