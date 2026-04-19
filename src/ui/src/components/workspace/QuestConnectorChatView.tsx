'use client'

import * as React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Check, CheckCheck, Loader2, TriangleAlert } from 'lucide-react'

import { useToast } from '@/components/ui/toast'
import { useI18n } from '@/lib/i18n/useI18n'
import { useQuestMessageAttachments, type QuestMessageAttachmentDraft } from '@/lib/hooks/useQuestMessageAttachments'
import type { CopilotPrefill } from '@/lib/plugins/ai-manus/view-types'
import { useTokenStream } from '@/lib/plugins/ai-manus/hooks/useTokenStream'
import { ChatScrollProvider } from '@/lib/plugins/ai-manus/lib/chat-scroll-context'
import { buildQuestTranscriptItems, type QuestTranscriptEntry } from '@/lib/questTranscript'
import { deriveMcpIdentity } from '@/lib/mcpIdentity'
import type { RenderOperationFeedItem } from '@/lib/feedOperations'
import { useAutoFollowScroll } from '@/lib/useAutoFollowScroll'
import { cn } from '@/lib/utils'
import type { FeedItem } from '@/types'
import { QuestCopilotComposer } from './QuestCopilotComposer'
import { QuestMessageAttachments } from './QuestMessageAttachments'
import { QuestCopilotPaneLayout } from './QuestCopilotPaneLayout'
import { QuestUserReadStateMeta } from './QuestUserReadStateMeta'
import { QuestBashExecOperation } from './QuestBashExecOperation'
import { QuestMcpOperation } from './QuestMcpOperation'

type ConnectorCommand = {
  name: string
  description?: string
}

type MessageQueueActionResult = {
  ok?: boolean
  status?: string
  message?: string
}

type QuestConnectorChatViewProps = {
  questId: string
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
  onSubmit: (message: string, attachments?: QuestMessageAttachmentDraft[]) => Promise<void>
  onReadNow?: (messageId: string) => Promise<MessageQueueActionResult | void>
  onWithdraw?: (messageId: string) => Promise<MessageQueueActionResult | void>
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
  readState?: string | null
  readReason?: string | null
  messageId?: string | null
  attachments?: Array<Record<string, unknown>>
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
  return buildQuestTranscriptItems(feed)
    .filter((item): item is Extract<QuestTranscriptEntry, { kind: 'message' }> => item.kind === 'message')
    .map(({ kind: _kind, ...message }) => message)
}

function isBashExecOperation(item: RenderOperationFeedItem) {
  const identity = deriveMcpIdentity(item.toolName, item.mcpServer, item.mcpTool)
  return identity.server === 'bash_exec'
}

function ToolBubble({ questId, item }: { questId: string; item: RenderOperationFeedItem }) {
  const identity = deriveMcpIdentity(item.toolName, item.mcpServer, item.mcpTool)

  return (
    <div
      className="flex w-full flex-col items-start gap-1"
      data-copilot-tool-surface="chat"
      data-copilot-tool-server={identity.server || undefined}
      data-copilot-tool-name={identity.tool || item.toolName || undefined}
    >
      <div className="min-w-0 max-w-[94%]">
        {isBashExecOperation(item) ? (
          <QuestBashExecOperation
            questId={questId}
            itemId={item.id}
            toolCallId={item.toolCallId}
            toolName={item.toolName}
            label={item.label}
            status={item.status}
            args={item.args}
            output={item.output}
            createdAt={item.createdAt}
            metadata={item.metadata}
            comment={item.comment}
            isLatest={!item.hasResult}
            expandBehavior="latest_or_running"
          />
        ) : (
          <QuestMcpOperation
            questId={questId}
            itemId={item.id}
            toolCallId={item.toolCallId}
            toolName={item.toolName}
            label={item.label}
            status={item.status}
            args={item.args}
            output={item.output}
            createdAt={item.createdAt}
            metadata={item.metadata}
            mcpServer={item.mcpServer}
            mcpTool={item.mcpTool}
            comment={item.comment}
          />
        )}
      </div>
    </div>
  )
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
  busyAction,
  onReadNow,
  onWithdraw,
}: {
  item: ConnectorMessage
  animateText: boolean
  busyAction: 'read_now' | 'withdraw' | null
  onReadNow?: ((messageId: string) => void | Promise<void>) | null
  onWithdraw?: ((messageId: string) => void | Promise<void>) | null
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
        <QuestMessageAttachments
          attachments={item.attachments}
          className={cn(isUser ? '[&_*]:text-white' : '')}
        />
      </div>
      {(item.createdAt || (isUser && item.deliveryState)) ? (
        <div className={cn('flex items-center gap-2 text-[10px]', isUser ? 'text-white/55' : 'text-muted-foreground')}>
          {isUser ? <DeliveryIndicator state={item.deliveryState} /> : null}
          {item.createdAt ? <span>{formatTime(item.createdAt)}</span> : null}
          {isUser ? (
            <QuestUserReadStateMeta
              readState={item.readState}
              readReason={item.readReason}
              messageId={item.messageId}
              busyAction={busyAction}
              onReadNow={onReadNow}
              onWithdraw={onWithdraw}
              className="text-white/70"
            />
          ) : null}
        </div>
      ) : isUser ? (
        <QuestUserReadStateMeta
          readState={item.readState}
          readReason={item.readReason}
          messageId={item.messageId}
          busyAction={busyAction}
          onReadNow={onReadNow}
          onWithdraw={onWithdraw}
          className="text-white/70"
        />
      ) : null}
    </div>
  )
}

export function QuestConnectorChatView({
  questId,
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
  onReadNow,
  onWithdraw,
  onStopRun,
  prefill = null,
}: QuestConnectorChatViewProps) {
  const { t } = useI18n('workspace')
  const { addToast } = useToast()
  const [input, setInput] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [messageAction, setMessageAction] = React.useState<{
    messageId: string
    kind: 'read_now' | 'withdraw'
  } | null>(null)
  const listRef = React.useRef<HTMLDivElement | null>(null)
  const contentRef = React.useRef<HTMLDivElement | null>(null)
  const attachmentState = useQuestMessageAttachments(questId)
  const transcriptItems = React.useMemo(() => buildQuestTranscriptItems(feed), [feed])
  const chatMessages = React.useMemo(
    () => transcriptItems.filter((item): item is Extract<QuestTranscriptEntry, { kind: 'message' }> => item.kind === 'message'),
    [transcriptItems]
  )
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
    deps: [transcriptItems.length, streaming, activeToolCount],
  })
  const prependAnchorRef = React.useRef<{ active: boolean; scrollHeight: number; scrollTop: number }>({
    active: false,
    scrollHeight: 0,
    scrollTop: 0,
  })

  const handleSubmit = React.useCallback(async () => {
    const trimmed = input.trim()
    if (submitting) return
    if (!trimmed && attachmentState.successfulAttachments.length === 0) return
    if (attachmentState.hasUploading || attachmentState.hasFailures) return
    setSubmitting(true)
    try {
      await onSubmit(trimmed, attachmentState.successfulAttachments)
      setInput('')
      await attachmentState.clearAll()
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
  }, [addToast, attachmentState, input, onSubmit, submitting, t])

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

  const handleReadNow = React.useCallback(
    async (messageId: string) => {
      if (!onReadNow || !messageId || messageAction) return
      setMessageAction({ messageId, kind: 'read_now' })
      try {
        const result = await onReadNow(messageId)
        if (result?.status === 'already_read') {
          addToast({
            type: 'success',
            title: t('copilot_message_read_now_already_sent', undefined, 'Already sent'),
            description: t('copilot_message_read_now_already_sent_desc', undefined, 'This message was already sent to the agent.'),
          })
        } else if (result?.ok === false) {
          addToast({
            type: 'error',
            title: t('copilot_message_read_now_failed', undefined, 'Read now failed'),
            description:
              result.message ||
              t('copilot_message_read_now_failed_desc', undefined, 'Unable to force immediate read for this message.'),
          })
        }
      } catch (caught) {
        const message = caught instanceof Error ? caught.message : String(caught)
        addToast({
          title: t('copilot_message_read_now_failed', undefined, 'Read now failed'),
          description: message,
          type: 'error',
        })
      } finally {
        setMessageAction(null)
      }
    },
    [addToast, messageAction, onReadNow, t]
  )

  const handleWithdraw = React.useCallback(
    async (messageId: string) => {
      if (!onWithdraw || !messageId || messageAction) return
      setMessageAction({ messageId, kind: 'withdraw' })
      try {
        const result = await onWithdraw(messageId)
        if (result?.status === 'already_withdrawn') {
          addToast({
            type: 'info',
            title: t('copilot_message_withdrawn', undefined, 'Withdrawn'),
            description: t('copilot_message_withdraw_already_done', undefined, 'This message was already withdrawn.'),
          })
        } else if (result?.ok === false) {
          addToast({
            type: 'error',
            title: t('copilot_message_withdraw_failed', undefined, 'Withdraw failed'),
            description:
              result.status === 'already_read'
                ? t('copilot_message_withdraw_failed_already_read_desc', undefined, 'Withdrawal failed because this message was already sent to the agent.')
                : result.message || t('copilot_message_withdraw_failed_desc', undefined, 'Unable to withdraw this message.'),
          })
        }
      } catch (caught) {
        const message = caught instanceof Error ? caught.message : String(caught)
        addToast({
          type: 'error',
          title: t('copilot_message_withdraw_failed', undefined, 'Withdraw failed'),
          description: message,
        })
      } finally {
        setMessageAction(null)
      }
    },
    [addToast, messageAction, onWithdraw, t]
  )

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
  }, [transcriptItems.length, loadingOlderHistory])

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
          attachments={attachmentState.attachments}
          onQueueFiles={attachmentState.queueFiles}
          onRemoveAttachment={attachmentState.removeAttachment}
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
              {transcriptItems.map((item) =>
                item.kind === 'message' ? (
                  <MessageBubble
                    key={item.id}
                    item={item}
                    animateText={
                      item.role === 'assistant' &&
                      latestAnimatedMessageId === item.id &&
                      Boolean(item.streaming || streaming)
                    }
                    busyAction={
                      messageAction && messageAction.messageId === item.messageId
                        ? messageAction.kind
                        : null
                    }
                    onReadNow={handleReadNow}
                    onWithdraw={handleWithdraw}
                  />
                ) : (
                  <ToolBubble key={item.id} questId={questId} item={item.item} />
                )
              )}

              {transcriptItems.length === 0 ? (
                <div className="pl-1 text-xs text-muted-foreground">
                  {restoring || loading ? t('copilot_connector_restoring') : t('copilot_connector_ready')}
                </div>
              ) : null}

              {(loading || restoring) && transcriptItems.length === 0 ? (
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
