import type { FeedItem } from '@/types'
import { mergeFeedItemsForRender, type RenderOperationFeedItem } from '@/lib/feedOperations'

export type QuestTranscriptMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  attachments?: Array<Record<string, unknown>>
  createdAt?: string
  streaming?: boolean
  badge?: string | null
  deliveryState?: string | null
  readState?: string | null
  readReason?: string | null
  readAt?: string | null
  messageId?: string | null
  emphasis?: 'message' | 'artifact'
}

export type QuestTranscriptEntry =
  | ({ kind: 'message' } & QuestTranscriptMessage)
  | {
      kind: 'operation'
      id: string
      item: RenderOperationFeedItem
    }

function normalizeEventType(value?: string | null) {
  return String(value || '').trim().toLowerCase()
}

function isVisibleAssistantMessage(item: Extract<FeedItem, { type: 'message' }>) {
  if (item.role !== 'assistant') return false
  if (item.reasoning) return false
  if (!item.content.trim()) return false
  const eventType = normalizeEventType(item.eventType)
  if (!eventType) return true
  return (
    eventType === 'conversation.message' ||
    eventType === 'runner.agent_message' ||
    eventType === 'runner.delta'
  )
}

function isVisibleUserMessage(item: Extract<FeedItem, { type: 'message' }>) {
  return item.role === 'user' && (item.content.trim().length > 0 || (item.attachments?.length || 0) > 0)
}

function isVisibleInteractiveArtifact(item: Extract<FeedItem, { type: 'artifact' }>) {
  return Boolean(item.interactionId && item.content.trim())
}

function buildArtifactBadge(item: Extract<FeedItem, { type: 'artifact' }>) {
  const parts = [item.kind, item.status].filter(Boolean)
  return parts.length ? parts.join(' · ') : null
}

export function buildQuestTranscriptItems(feed: FeedItem[]): QuestTranscriptEntry[] {
  return mergeFeedItemsForRender(feed).flatMap((item) => {
    if (item.type === 'operation') {
      return [
        {
          kind: 'operation',
          id: item.renderId,
          item,
        } satisfies QuestTranscriptEntry,
      ]
    }

    if (item.type === 'message') {
      if (isVisibleUserMessage(item)) {
        return [
          {
            kind: 'message',
            id: item.id,
            role: 'user',
            content: item.content.trim(),
            attachments: item.attachments,
            createdAt: item.createdAt,
            streaming: false,
            deliveryState: item.deliveryState ?? null,
            readState: item.readState ?? null,
            readReason: item.readReason ?? null,
            readAt: item.readAt ?? null,
            messageId: item.messageId ?? null,
            emphasis: 'message',
          } satisfies QuestTranscriptEntry,
        ]
      }
      if (isVisibleAssistantMessage(item)) {
        return [
          {
            kind: 'message',
            id: item.id,
            role: 'assistant',
            content: item.content.trim(),
            createdAt: item.createdAt,
            streaming: Boolean(item.stream),
            emphasis: 'message',
          } satisfies QuestTranscriptEntry,
        ]
      }
      return []
    }

    if (item.type === 'artifact' && isVisibleInteractiveArtifact(item)) {
      return [
        {
          kind: 'message',
          id: item.id,
          role: 'assistant',
          content: item.content.trim(),
          createdAt: item.createdAt,
          badge: buildArtifactBadge(item),
          streaming: false,
          emphasis: 'artifact',
        } satisfies QuestTranscriptEntry,
      ]
    }

    return []
  })
}

export function buildQuestTranscriptMessages(feed: FeedItem[]): QuestTranscriptMessage[] {
  return buildQuestTranscriptItems(feed)
    .filter((item): item is Extract<QuestTranscriptEntry, { kind: 'message' }> => item.kind === 'message')
    .map(({ kind: _kind, ...message }) => message)
}
