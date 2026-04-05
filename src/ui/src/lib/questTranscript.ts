import type { FeedItem } from '@/types'
import { dedupeVisibleFeedItems } from '@/lib/feedOperations'

export type QuestTranscriptMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt?: string
  streaming?: boolean
  badge?: string | null
  deliveryState?: string | null
  emphasis?: 'message' | 'artifact'
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
  return item.role === 'user' && item.content.trim().length > 0
}

function isVisibleInteractiveArtifact(item: Extract<FeedItem, { type: 'artifact' }>) {
  return Boolean(item.interactionId && item.content.trim())
}

function buildArtifactBadge(item: Extract<FeedItem, { type: 'artifact' }>) {
  const parts = [item.kind, item.status].filter(Boolean)
  return parts.length ? parts.join(' · ') : null
}

export function buildQuestTranscriptMessages(feed: FeedItem[]): QuestTranscriptMessage[] {
  return dedupeVisibleFeedItems(feed).flatMap((item) => {
    if (item.type === 'message') {
      if (isVisibleUserMessage(item)) {
        return [
          {
            id: item.id,
            role: 'user',
            content: item.content.trim(),
            createdAt: item.createdAt,
            streaming: false,
            deliveryState: item.deliveryState ?? null,
            emphasis: 'message',
          } satisfies QuestTranscriptMessage,
        ]
      }
      if (isVisibleAssistantMessage(item)) {
        return [
          {
            id: item.id,
            role: 'assistant',
            content: item.content.trim(),
            createdAt: item.createdAt,
            streaming: Boolean(item.stream),
            emphasis: 'message',
          } satisfies QuestTranscriptMessage,
        ]
      }
      return []
    }

    if (item.type === 'artifact' && isVisibleInteractiveArtifact(item)) {
      return [
        {
          id: item.id,
          role: 'assistant',
          content: item.content.trim(),
          createdAt: item.createdAt,
          badge: buildArtifactBadge(item),
          streaming: false,
          emphasis: 'artifact',
        } satisfies QuestTranscriptMessage,
      ]
    }

    return []
  })
}
