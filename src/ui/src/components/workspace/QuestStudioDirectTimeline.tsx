'use client'

import * as React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Brain,
  ChevronDown,
  User2,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { LogoIcon } from '@/components/ui/workspace-icons'
import { findLatestRenderedOperationId, mergeFeedItemsForRender } from '@/lib/feedOperations'
import { useI18n } from '@/lib/i18n/useI18n'
import { deriveMcpIdentity } from '@/lib/mcpIdentity'
import OrbitLogoStatus from '@/lib/plugins/ai-manus/components/OrbitLogoStatus'
import { ThinkingIndicator } from '@/lib/plugins/ai-manus/components/ThinkingIndicator'
import { ChatScrollProvider } from '@/lib/plugins/ai-manus/lib/chat-scroll-context'
import { buildStudioTurns, type StudioTurn, type StudioTurnBlock } from '@/lib/studioTurns'
import { useAutoFollowScroll } from '@/lib/useAutoFollowScroll'
import { cn } from '@/lib/utils'
import type { AgentComment, FeedItem, QuestSummary } from '@/types'
import { QuestBashExecOperation } from './QuestBashExecOperation'
import { StudioToolCard } from './StudioToolCards'

type QuestStudioDirectTimelineProps = {
  questId: string
  feed: FeedItem[]
  loading: boolean
  restoring: boolean
  streaming: boolean
  activeToolCount: number
  connectionState: 'connecting' | 'connected' | 'reconnecting' | 'error'
  error?: string | null
  snapshot?: QuestSummary | null
  hasOlderHistory?: boolean
  loadingOlderHistory?: boolean
  onLoadOlderHistory?: () => Promise<void>
  emptyLabel?: string
  bottomInset?: number
}

function formatTime(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function EmptyState({
  loading,
  restoring,
  connectionState,
  emptyLabel,
}: {
  loading: boolean
  restoring: boolean
  connectionState: QuestStudioDirectTimelineProps['connectionState']
  emptyLabel: string
}) {
  const { t } = useI18n('workspace')
  const statusLabel =
    restoring || loading
      ? t('copilot_trace_restoring')
      : connectionState === 'reconnecting'
        ? t('copilot_trace_reconnecting')
        : connectionState === 'connecting'
          ? t('copilot_trace_connecting')
          : connectionState === 'error'
            ? t('copilot_trace_unavailable')
            : emptyLabel

  return (
    <div className="flex min-h-[240px] items-center justify-center rounded-[16px] border border-dashed border-black/[0.08] px-6 py-10 dark:border-white/[0.10]">
      <div className="max-w-sm text-center">
        <div className="mx-auto mb-4 flex h-10 w-10 items-center justify-center rounded-[12px] border border-black/10 bg-white/[0.85] dark:border-white/[0.12] dark:bg-white/[0.05]">
          <OrbitLogoStatus compact sizePx={28} toolCount={0} resetKey={statusLabel} />
        </div>
        <div className="text-sm font-medium text-foreground">{statusLabel}</div>
        {loading || restoring || connectionState === 'connecting' || connectionState === 'reconnecting' ? (
          <div className="mt-3 flex justify-center">
            <ThinkingIndicator compact />
          </div>
        ) : (
          <div className="mt-2 text-xs text-muted-foreground">
            {t('copilot_trace_empty_description')}
          </div>
        )}
      </div>
    </div>
  )
}

function normalizeInlinePreview(value: string) {
  return value.replace(/\s+/g, ' ').trim()
}

function humanizeEventLabel(value: string) {
  const normalized = String(value || '')
    .replace(/[._]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (!normalized) return ''
  return normalized.charAt(0).toUpperCase() + normalized.slice(1)
}

function InlineCommentDetails({
  comment,
  className,
}: {
  comment?: AgentComment | null
  className?: string
}) {
  const { t } = useI18n('workspace')
  if (!comment) {
    return null
  }

  const entries = [
    comment.summary ? { label: t('copilot_trace_summary'), value: comment.summary } : null,
    comment.whyNow ? { label: t('copilot_trace_why_now'), value: comment.whyNow } : null,
    comment.next ? { label: t('copilot_trace_next'), value: comment.next } : null,
  ].filter(Boolean) as Array<{ label: string; value: string }>
  const risks = Array.isArray(comment.risks) ? comment.risks.filter(Boolean) : []
  const monitorLabel = [comment.checkStage, comment.checkAfterSeconds ? `next ${comment.checkAfterSeconds}s` : '']
    .filter(Boolean)
    .join(' · ')

  if (entries.length === 0 && risks.length === 0 && !monitorLabel) {
    return null
  }

  return (
    <div
      className={cn(
        'border-l border-black/[0.08] pl-3 text-[11px] leading-5 text-muted-foreground dark:border-white/[0.10]',
        className
      )}
    >
      {entries.length > 0 ? (
        <div className="space-y-1">
          {entries.map((entry) => (
            <div key={entry.label} className="break-words [overflow-wrap:anywhere]">
              <span className="font-medium text-foreground">{entry.label}:</span> {entry.value}
            </div>
          ))}
        </div>
      ) : null}
      {monitorLabel ? <div className={cn(entries.length > 0 && 'mt-1.5')}>{monitorLabel}</div> : null}
      {risks.length > 0 ? (
        <div
          className={cn(
            'flex flex-wrap gap-2 text-[10px] uppercase tracking-[0.08em]',
            (entries.length > 0 || monitorLabel) && 'mt-1.5'
          )}
        >
          {risks.map((risk) => (
            <span key={risk} className="rounded-full border border-black/[0.08] px-2 py-0.5 dark:border-white/[0.10]">
              {risk}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function StreamMarkdownBlock({
  content,
  streaming,
  className,
}: {
  content: string
  streaming: boolean
  className: string
}) {
  if (streaming) {
    return <div className={cn(className, 'whitespace-pre-wrap font-normal')}>{content}</div>
  }

  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  )
}

function StudioMessageBlock({
  block,
}: {
  block: Extract<StudioTurnBlock, { kind: 'message' }>
}) {
  return (
    <div className="min-w-0 overflow-hidden pl-0.5">
      <StreamMarkdownBlock
        content={block.item.content || ''}
        streaming={Boolean(block.item.stream)}
        className="ds-copilot-markdown prose prose-sm prose-p:my-0 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1 prose-li:my-0 prose-pre:my-1.5 prose-pre:rounded-md prose-pre:px-3 prose-pre:py-2 prose-code:text-[12px] max-w-none break-words text-[12.5px] leading-[1.72] [overflow-wrap:anywhere] text-foreground dark:prose-invert"
      />
    </div>
  )
}

function StudioReasoningBlock({
  block,
}: {
  block: Extract<StudioTurnBlock, { kind: 'reasoning' }>
}) {
  const { t } = useI18n('workspace')
  if (!block.item.content.trim()) {
    return null
  }
  const preview = normalizeInlinePreview(block.item.content).slice(0, 132)
  return (
    <details
      className="group min-w-0 overflow-hidden border-l border-[rgba(165,146,132,0.45)] pl-3 dark:border-[rgba(183,165,154,0.32)]"
    >
      <summary className="flex cursor-pointer list-none items-start gap-2 py-0.5 text-[12px] text-foreground [&::-webkit-details-marker]:hidden">
        <div className="mt-0.5 flex h-[18px] w-[18px] items-center justify-center rounded-sm bg-[rgba(183,165,154,0.12)] dark:bg-[rgba(183,165,154,0.16)]">
          <Brain className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="font-medium leading-4">
            {t('copilot_trace_thinking')}
            {block.item.stream ? (
              <span className="ml-2 text-[10.5px] font-normal text-muted-foreground">
                {t('copilot_trace_streaming')}
              </span>
            ) : null}
          </div>
          <div className="truncate pt-0.5 text-[11px] font-normal text-muted-foreground">
            {preview || t('copilot_trace_reasoning')}
          </div>
        </div>
        <ChevronDown className="mt-0.5 h-4 w-4 transition-transform group-open:rotate-180" />
      </summary>
      <div className="pt-2">
        <StreamMarkdownBlock
          content={block.item.content}
          streaming={Boolean(block.item.stream)}
          className="ds-copilot-markdown prose prose-sm prose-p:my-0 prose-ul:my-1 prose-ol:my-1 prose-li:my-0 prose-pre:my-1.5 prose-pre:rounded-md prose-pre:px-3 prose-pre:py-2 prose-code:text-[11px] max-w-none break-words text-[12px] leading-[1.65] [overflow-wrap:anywhere] text-foreground dark:prose-invert"
        />
      </div>
    </details>
  )
}

function isBashExecOperation(block: Extract<StudioTurnBlock, { kind: 'operation' }>) {
  const identity = deriveMcpIdentity(
    block.item.toolName,
    block.item.mcpServer,
    block.item.mcpTool
  )
  return identity.server === 'bash_exec'
}

function StudioOperationBlock({
  questId,
  block,
  isLatestOperation,
}: {
  questId: string
  block: Extract<StudioTurnBlock, { kind: 'operation' }>
  isLatestOperation: boolean
}) {
  if (isBashExecOperation(block)) {
    return (
      <QuestBashExecOperation
        questId={questId}
        itemId={block.item.id}
        toolCallId={block.item.toolCallId}
        toolName={block.item.toolName}
        label={block.item.label}
        status={block.item.status}
        args={block.item.args}
        output={block.item.output}
        createdAt={block.item.createdAt}
        metadata={block.item.metadata}
        comment={block.item.comment}
        monitorPlanSeconds={block.item.monitorPlanSeconds}
        monitorStepIndex={block.item.monitorStepIndex}
        nextCheckAfterSeconds={block.item.nextCheckAfterSeconds}
        isLatest={isLatestOperation}
        expandBehavior="latest_only"
      />
    )
  }
  return <StudioToolCard questId={questId} item={block.item} isLatest={isLatestOperation} />
}

function StudioArtifactBlock({ block }: { block: Extract<StudioTurnBlock, { kind: 'artifact' }> }) {
  const { t } = useI18n('workspace')
  const item = block.item
  const detailEntries = Object.entries(item.details ?? {}).filter(([, value]) => value != null && value !== '')

  return (
    <div className="min-w-0 overflow-hidden border-l border-[rgba(121,145,182,0.45)] pl-3 dark:border-[rgba(121,145,182,0.34)]">
      <div className="flex flex-wrap items-center gap-2 text-[11px] leading-4 text-muted-foreground">
        <span className="font-medium uppercase tracking-[0.08em] text-foreground">{item.kind}</span>
        {item.status ? <span>{item.status}</span> : null}
        {item.flowType ? <span>{item.flowType}</span> : null}
        {item.createdAt ? <span className="ml-auto">{formatTime(item.createdAt)}</span> : null}
      </div>

      <div className="mt-1 break-words text-[12.5px] leading-[1.72] text-foreground [overflow-wrap:anywhere]">
        {item.content}
      </div>

      {item.reason ? (
        <div className="mt-1 break-words text-[12px] leading-[1.6] text-muted-foreground [overflow-wrap:anywhere]">
          <span className="font-medium text-foreground">{t('copilot_connector_reason')}:</span> {item.reason}
        </div>
      ) : null}

      {item.guidance ? (
        <div className="mt-1 break-words text-[12px] leading-[1.6] text-muted-foreground [overflow-wrap:anywhere]">
          <span className="font-medium text-foreground">{t('copilot_trace_next')}:</span> {item.guidance}
        </div>
      ) : null}

      <InlineCommentDetails comment={item.comment} className="mt-2" />

      {detailEntries.length > 0 ? (
        <div className="mt-2 border-l border-black/[0.08] pl-3 text-[12px] leading-[1.6] text-muted-foreground dark:border-white/[0.10]">
          <div className="font-medium text-foreground">{t('copilot_trace_details')}</div>
          <div className="mt-1 space-y-1">
            {detailEntries.slice(0, 8).map(([key, value]) => (
              <div key={key} className="break-words [overflow-wrap:anywhere]">
                <span className="font-medium text-foreground">{key}:</span>{' '}
                {typeof value === 'string' ? value : JSON.stringify(value)}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}

function StudioEventBlock({ block }: { block: Extract<StudioTurnBlock, { kind: 'event' }> }) {
  const item = block.item
  const label = humanizeEventLabel(item.label)
  const text = [label, item.content ? item.content.trim() : ''].filter(Boolean).join(' · ')
  return (
    <div className="inline-flex max-w-full items-center gap-2 rounded-full border border-black/[0.06] px-3 py-1 text-[11px] text-muted-foreground dark:border-white/[0.10]">
      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-black/[0.35] dark:bg-white/[0.35]" />
      <span className="truncate">{text}</span>
    </div>
  )
}

function AssistantTurn({
  questId,
  turn,
  latestOperationId,
}: {
  questId: string
  turn: StudioTurn
  latestOperationId: string | null
}) {
  const hasStreamingMessage = turn.blocks.some(
    (block) =>
      (block.kind === 'message' || block.kind === 'reasoning') &&
      Boolean(block.item.stream)
  )

  return (
    <div className="flex min-w-0 items-start gap-3">
      <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-sm border border-black/10 bg-white/[0.90] dark:border-white/[0.12] dark:bg-white/[0.05]">
        <LogoIcon size={14} />
      </div>

      <div className="min-w-0 flex-1 space-y-2.5">
        <div className="flex flex-wrap items-center gap-2 text-[11px] leading-4 text-muted-foreground">
          <span className="font-medium text-foreground">@DeepScientist</span>
          {turn.skillId ? <Badge className="bg-black/[0.03] dark:bg-white/[0.04]">{turn.skillId}</Badge> : null}
          {hasStreamingMessage ? (
            <span className="inline-flex h-2 w-2 rounded-full bg-[#2F3437] animate-caret dark:bg-[#E7DFD2]" />
          ) : null}
          {turn.createdAt ? <span className="ml-auto">{formatTime(turn.createdAt)}</span> : null}
        </div>

        {turn.blocks.map((block) => {
          if (block.kind === 'message') {
            return <StudioMessageBlock key={block.id} block={block} />
          }
          if (block.kind === 'reasoning') {
            return <StudioReasoningBlock key={block.id} block={block} />
          }
          if (block.kind === 'operation') {
            return (
              <StudioOperationBlock
                key={block.id}
                questId={questId}
                block={block}
                isLatestOperation={Boolean(
                  latestOperationId && block.item.renderId === latestOperationId
                )}
              />
            )
          }
          if (block.kind === 'artifact') {
            return <StudioArtifactBlock key={block.id} block={block} />
          }
          return <StudioEventBlock key={block.id} block={block} />
        })}
      </div>
    </div>
  )
}

function UserTurn({ turn }: { turn: StudioTurn }) {
  const { t } = useI18n('workspace')
  const messageBlock = turn.blocks.find((block) => block.kind === 'message')
  if (!messageBlock || messageBlock.kind !== 'message') {
    return null
  }

  return (
    <div className="flex min-w-0 items-start gap-3 border-l border-[#2F3437]/18 pl-3 dark:border-white/[0.10]">
      <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-sm border border-black/10 bg-white/[0.90] dark:border-white/[0.12] dark:bg-white/[0.05]">
        <User2 className="h-3.5 w-3.5" />
      </div>

      <div className="min-w-0 flex-1">
        <div className="mb-1.5 flex items-center gap-2 text-[11px] text-muted-foreground">
          <span className="font-medium text-foreground">{t('copilot_connector_you')}</span>
          {turn.createdAt ? <span>{formatTime(turn.createdAt)}</span> : null}
        </div>
        <div className="ds-copilot-markdown prose prose-sm prose-p:my-0 prose-ul:my-1 prose-ol:my-1 prose-li:my-0 prose-pre:my-1.5 prose-pre:rounded-md prose-pre:px-3 prose-pre:py-2 prose-code:text-[12px] max-w-none whitespace-pre-wrap break-words text-[12.5px] leading-[1.72] [overflow-wrap:anywhere] text-foreground dark:prose-invert">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{messageBlock.item.content || ''}</ReactMarkdown>
        </div>
      </div>
    </div>
  )
}

function SystemTurn({ turn }: { turn: StudioTurn }) {
  return (
    <div className="flex justify-center">
      <div className="space-y-2">
        {turn.blocks.map((block) => (
          <StudioEventBlock key={block.id} block={block as Extract<StudioTurnBlock, { kind: 'event' }>} />
        ))}
      </div>
    </div>
  )
}

export function QuestStudioDirectTimeline({
  questId,
  feed,
  loading,
  restoring,
  streaming,
  activeToolCount,
  connectionState,
  error,
  snapshot,
  hasOlderHistory = false,
  loadingOlderHistory = false,
  onLoadOlderHistory,
  emptyLabel = 'Copilot trace appears here.',
  bottomInset = 28,
}: QuestStudioDirectTimelineProps) {
  const { t } = useI18n('workspace')
  const turns = React.useMemo(() => buildStudioTurns(feed), [feed])
  const latestOperationId = React.useMemo(
    () => findLatestRenderedOperationId(mergeFeedItemsForRender(feed)),
    [feed]
  )
  const listRef = React.useRef<HTMLDivElement | null>(null)
  const contentRef = React.useRef<HTMLDivElement | null>(null)
  const prependAnchorRef = React.useRef<{ active: boolean; scrollHeight: number; scrollTop: number }>({
    active: false,
    scrollHeight: 0,
    scrollTop: 0,
  })
  const { isNearBottom } = useAutoFollowScroll({
    scrollRef: listRef,
    contentRef,
    deps: [turns.length, streaming, activeToolCount, latestOperationId],
  })

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
  }, [loadingOlderHistory, turns.length])

  return (
    <div className="flex min-h-0 flex-1 flex-col px-4 pt-4">
      <ChatScrollProvider value={{ isNearBottom }}>
        <div
          ref={listRef}
          className="feed-scrollbar flex min-h-0 flex-1 flex-col gap-5 overflow-x-hidden overflow-y-auto pr-1"
          style={{ paddingBottom: bottomInset }}
          onWheel={(event) => {
            const root = listRef.current
            if (!root || event.deltaY >= 0 || root.scrollTop > 24) {
              return
            }
            void handleLoadOlderHistory()
          }}
        >
          <div ref={contentRef} className="flex min-w-0 flex-col gap-5">
            {hasOlderHistory ? (
              <div className="flex justify-center">
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
            {turns.length === 0 ? (
              <EmptyState
                loading={loading}
                restoring={restoring}
                connectionState={connectionState}
                emptyLabel={emptyLabel || t('copilot_studio_empty', undefined, 'Copilot trace appears here.')}
              />
            ) : (
              turns.map((turn) => {
                if (turn.role === 'user') {
                  return <UserTurn key={turn.id} turn={turn} />
                }
                if (turn.role === 'system') {
                  return <SystemTurn key={turn.id} turn={turn} />
                }
                return (
                  <AssistantTurn
                    key={turn.id}
                    questId={questId}
                    turn={turn}
                    latestOperationId={latestOperationId}
                  />
                )
              })
            )}
          </div>
        </div>
      </ChatScrollProvider>
    </div>
  )
}

export default QuestStudioDirectTimeline
