import type { MutableRefObject } from 'react'
import type {
  AgentSSEEvent,
  AttachmentInfo,
  AttachmentsEventData,
  MessageEventData,
  ReceiptEventData,
} from '@/lib/types/chat-events'
import { buildCopilotFilePath } from './file-operations'
import type { AttachmentsContent, ChatMessageItem, MessageContent } from '../types'

export type PendingUserMessage = {
  content: string
  attachments: AttachmentInfo[]
}

export type ChatEventReducerContext = {
  sessionId?: string | null
  messagesRef: MutableRefObject<ChatMessageItem[]>
  assistantMessageIndexRef: MutableRefObject<Map<string, string>>
  lastAssistantSegmentIdRef?: MutableRefObject<string | null>
  attachmentsSeenRef: MutableRefObject<Set<string>>
  pendingUserRef?: MutableRefObject<PendingUserMessage | null>
  resolveTimelineSeq: (seq?: number | null) => number
  buildTextDeltaId: (eventId: string, seq: number) => string
  appendMessage: (message: ChatMessageItem) => void
  updateMessages: (messages: ChatMessageItem[]) => void
  queueMessages?: (messages: ChatMessageItem[]) => void
  closeAssistantSegment?: () => void
  startDisplayLock?: (id: string) => void
  setCopilotStatus?: (status: string | null) => void
  onSessionUpdate?: (content: string, timestamp: number) => void
  shouldDeferAttachments?: () => boolean
  onDeferAttachments?: (event: AgentSSEEvent) => void
}

export function createMessageId(prefix: string) {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function coerceRole(value: unknown): 'user' | 'assistant' {
  return value === 'assistant' ? 'assistant' : 'user'
}

export function coerceTimestamp(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const numeric = Number(value)
    if (Number.isFinite(numeric)) return numeric
    const parsed = Date.parse(value)
    if (!Number.isNaN(parsed)) return Math.floor(parsed / 1000)
  }
  return Math.floor(Date.now() / 1000)
}

export function getEventSequence(event: AgentSSEEvent): number | null {
  const data = event.data as unknown as Record<string, unknown>
  const seq = data.seq
  if (typeof seq === 'number' && Number.isFinite(seq)) return seq
  const fallback = (data as { _seq?: unknown })._seq
  if (typeof fallback === 'number' && Number.isFinite(fallback)) return fallback
  return null
}

export function normalizeAttachments(
  attachments: AttachmentInfo[] | undefined,
  sessionId?: string | null
): AttachmentInfo[] {
  if (!Array.isArray(attachments) || attachments.length === 0) return []
  return attachments.map((file) => ({
    ...file,
    status: file.status ?? 'success',
    file_path: file.file_path || (sessionId ? buildCopilotFilePath(sessionId, file.filename) : file.file_path),
  }))
}

export function buildAttachmentKey(
  role: 'user' | 'assistant',
  timestamp: number,
  attachments: AttachmentInfo[]
) {
  const ids = attachments
    .map((file) => file.file_id || file.filename)
    .filter(Boolean)
    .sort()
    .join('|')
  return `${role}:${timestamp}:${ids}`
}

const getMessageContent = (messageData: Partial<MessageEventData> & { message?: unknown; text?: unknown }) => {
  if (typeof messageData.content === 'string') return messageData.content
  if (typeof messageData.message === 'string') return messageData.message
  if (typeof messageData.text === 'string') return messageData.text
  if (messageData.content != null) return String(messageData.content)
  return ''
}

const findQuestConversationDuplicateIndex = (
  contentValue: string,
  messageData: Partial<MessageEventData>,
  messages: ChatMessageItem[]
) => {
  const metadata = messageData.metadata
  const rawEventType =
    typeof metadata?.quest_event_type === 'string' ? metadata.quest_event_type : ''
  if (rawEventType !== 'conversation.message') return -1
  const runId = typeof metadata?.quest_run_id === 'string' ? metadata.quest_run_id : ''
  const skillId = typeof metadata?.quest_skill_id === 'string' ? metadata.quest_skill_id : ''
  const normalizedContent = contentValue.trim()
  if (!normalizedContent || !runId) return -1
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const candidate = messages[index]
    if (candidate.type !== 'text_delta') continue
    const candidateContent = candidate.content as MessageContent
    if (candidateContent.role !== 'assistant') continue
    const candidateMeta = candidateContent.metadata
    if ((candidateContent.content || '').trim() !== normalizedContent) continue
    if ((candidateMeta?.quest_event_type || '') !== 'runner.agent_message') continue
    if ((candidateMeta?.quest_run_id || '') !== runId) continue
    if (skillId && (candidateMeta?.quest_skill_id || '') !== skillId) continue
    return index
  }
  return -1
}

const applyMessageEvent = (
  event: AgentSSEEvent,
  context: ChatEventReducerContext
) => {
  const messageData = event.data as Partial<MessageEventData> & { message?: unknown; text?: unknown }
  const role = coerceRole(messageData.role)
  const delta = typeof messageData.delta === 'string' ? messageData.delta : ''
  const timestamp = coerceTimestamp(messageData.timestamp)
  const eventId = typeof messageData.event_id === 'string' ? messageData.event_id : ''
  const messageKey = eventId || createMessageId(role)
  const eventSeq = context.resolveTimelineSeq(getEventSequence(event))
  const queueMessages = context.queueMessages ?? context.updateMessages

  if (
    role === 'user' &&
    messageData.metadata &&
    typeof messageData.metadata === 'object' &&
    (messageData.metadata as Record<string, unknown>).question_tool
  ) {
    return true
  }

  if (role === 'assistant' && delta) {
    const existingId = context.assistantMessageIndexRef.current.get(messageKey)
    if (existingId) {
      const existingIndex = context.messagesRef.current.findIndex((item) => item.id === existingId)
      if (existingIndex >= 0) {
        const existing = context.messagesRef.current[existingIndex]
        if (existing.type === 'text_delta') {
          const existingContent = existing.content as MessageContent
          if (existingContent.status === 'in_progress') {
            const next = [...context.messagesRef.current]
            next[existingIndex] = {
              ...existing,
              content: {
                ...existingContent,
                role,
                timestamp,
                metadata: messageData.metadata ?? existingContent.metadata,
                content: `${existingContent.content}${delta}`,
                status: 'in_progress',
              },
            }
            queueMessages(next)
            if (context.lastAssistantSegmentIdRef) {
              context.lastAssistantSegmentIdRef.current = existingId
            }
            if (context.startDisplayLock) {
              context.startDisplayLock(existingId)
            }
            if (context.setCopilotStatus) {
              context.setCopilotStatus(null)
            }
            return true
          }
        }
      }
    }

    if (context.closeAssistantSegment) {
      context.closeAssistantSegment()
    }
    const deltaId = context.buildTextDeltaId(messageKey, eventSeq)
    context.appendMessage({
      id: deltaId,
      type: 'text_delta',
      seq: eventSeq,
      ts: timestamp,
      content: {
        ...messageData,
        role,
        content: delta,
        timestamp,
        status: 'in_progress',
      } as MessageContent,
    })
    context.assistantMessageIndexRef.current.set(messageKey, deltaId)
    if (context.lastAssistantSegmentIdRef) {
      context.lastAssistantSegmentIdRef.current = deltaId
    }
    if (context.startDisplayLock) {
      context.startDisplayLock(deltaId)
    }
    if (context.setCopilotStatus) {
      context.setCopilotStatus(null)
    }
    return true
  }

  const contentValue = getMessageContent(messageData)
  const normalizedAttachments = normalizeAttachments(
    Array.isArray(messageData.attachments) ? messageData.attachments : undefined,
    context.sessionId
  )

  if (
    role === 'assistant' &&
    messageData.metadata &&
    typeof messageData.metadata === 'object' &&
    typeof (messageData.metadata as Record<string, unknown>).moment_id === 'string'
  ) {
    const momentId = String((messageData.metadata as Record<string, unknown>).moment_id || '')
    if (momentId) {
      const existingIndex = context.messagesRef.current.findIndex((item) => {
        if (item.type !== 'text_delta') return false
        const content = item.content as MessageContent
        const metadata = content.metadata as Record<string, unknown> | undefined
        return typeof metadata?.moment_id === 'string' && metadata.moment_id === momentId
      })
      if (existingIndex >= 0) {
        const next = [...context.messagesRef.current]
        const existing = next[existingIndex]
        const existingContent = existing.content as MessageContent
        const mergedMeta = {
          ...(existingContent.metadata ?? {}),
          ...(messageData.metadata as Record<string, unknown>),
        }
        next[existingIndex] = {
          ...existing,
          content: {
            ...existingContent,
            role,
            timestamp,
            content: contentValue || existingContent.content,
            status: existingContent.status ?? 'completed',
            metadata: mergedMeta,
          } as MessageContent,
        }
        context.updateMessages(next)
        if (messageKey) {
          context.assistantMessageIndexRef.current.set(messageKey, existing.id)
        }
        if (context.lastAssistantSegmentIdRef) {
          context.lastAssistantSegmentIdRef.current = existing.id
        }
        if (context.startDisplayLock) {
          context.startDisplayLock(existing.id)
        }
        if (context.setCopilotStatus) {
          context.setCopilotStatus(null)
        }
        return true
      }
    }
  }

  if (role === 'user' && context.pendingUserRef?.current) {
    const pending = context.pendingUserRef.current
    const pendingMatches =
      contentValue.trim() === pending.content.trim() &&
      normalizedAttachments.length === pending.attachments.length &&
      normalizedAttachments.every((file) =>
        pending.attachments.some((pendingFile) => pendingFile.filename === file.filename)
      )
    if (pendingMatches) {
      context.pendingUserRef.current = null
      return true
    }
  }

  if (role === 'assistant' && context.closeAssistantSegment) {
    context.closeAssistantSegment()
  }

  let updatedExisting = false
  if (role === 'assistant') {
    const duplicateIndex = findQuestConversationDuplicateIndex(
      contentValue,
      messageData,
      context.messagesRef.current
    )
    if (duplicateIndex >= 0) {
      const next = [...context.messagesRef.current]
      const existing = next[duplicateIndex]
      if (existing.type === 'text_delta') {
        const existingContent = existing.content as MessageContent
        const nextContent: MessageContent = {
          ...existingContent,
          role,
          timestamp,
          status: 'completed',
          metadata: {
            ...(existingContent.metadata ?? {}),
            ...(messageData.metadata ?? {}),
          },
          content: contentValue || existingContent.content,
        }
        next[duplicateIndex] = { ...existing, seq: eventSeq, ts: timestamp, content: nextContent }
        context.updateMessages(next)
        if (messageKey) {
          context.assistantMessageIndexRef.current.set(messageKey, existing.id)
        }
        if (context.lastAssistantSegmentIdRef) {
          context.lastAssistantSegmentIdRef.current = existing.id
        }
        if (context.startDisplayLock) {
          context.startDisplayLock(existing.id)
        }
        updatedExisting = true
      }
    }
  }

  if (role === 'assistant' && !updatedExisting) {
    const existingId = context.assistantMessageIndexRef.current.get(messageKey)
    if (existingId) {
      const existingIndex = context.messagesRef.current.findIndex((item) => item.id === existingId)
      if (existingIndex >= 0) {
        const next = [...context.messagesRef.current]
        const existing = next[existingIndex]
        if (existing.type === 'text_delta') {
          const existingContent = existing.content as MessageContent
          const nextContent: MessageContent = {
            ...existingContent,
            role,
            timestamp,
            status: 'completed',
            metadata: messageData.metadata ?? existingContent.metadata,
            content: contentValue || existingContent.content,
          }
          next[existingIndex] = { ...existing, content: nextContent }
          context.updateMessages(next)
          if (context.lastAssistantSegmentIdRef) {
            context.lastAssistantSegmentIdRef.current = existingId
          }
          if (context.startDisplayLock) {
            context.startDisplayLock(existingId)
          }
          updatedExisting = true
        }
      }
    }
  }

  if (!updatedExisting) {
    const textId = context.buildTextDeltaId(messageKey, eventSeq)
    context.appendMessage({
      id: textId,
      type: 'text_delta',
      seq: eventSeq,
      ts: timestamp,
      content: {
        ...messageData,
        role,
        content: contentValue,
        timestamp,
        ...(role === 'assistant' ? { status: 'completed' } : {}),
      } as MessageContent,
    })
    if (role === 'assistant') {
      context.assistantMessageIndexRef.current.set(messageKey, textId)
      if (context.lastAssistantSegmentIdRef) {
        context.lastAssistantSegmentIdRef.current = textId
      }
      if (context.startDisplayLock) {
        context.startDisplayLock(textId)
      }
    }
  }

  if (context.onSessionUpdate) {
    context.onSessionUpdate(contentValue, timestamp)
  }

  if (normalizedAttachments.length > 0) {
    const key = buildAttachmentKey(role, timestamp, normalizedAttachments)
    if (!context.attachmentsSeenRef.current.has(key)) {
      context.attachmentsSeenRef.current.add(key)
      const shouldDefer = context.shouldDeferAttachments?.() ?? false
      if (shouldDefer && context.onDeferAttachments) {
        context.onDeferAttachments({
          event: 'attachments',
          data: {
            event_id: createMessageId('attachments'),
            timestamp,
            role,
            attachments: normalizedAttachments,
            metadata: { context: { __deferred: true } },
          },
        })
      } else {
        const attachmentSeq = context.resolveTimelineSeq(null)
        context.appendMessage({
          id: createMessageId('attachments'),
          type: 'attachments',
          seq: attachmentSeq,
          ts: timestamp,
          content: {
            role,
            attachments: normalizedAttachments,
            timestamp,
          } as AttachmentsContent,
        })
      }
    }
  }

  if (context.setCopilotStatus) {
    context.setCopilotStatus(null)
  }

  return true
}

const applyAttachmentsEvent = (event: AgentSSEEvent, context: ChatEventReducerContext) => {
  const attachmentsData = event.data as Partial<AttachmentsEventData>
  const role = coerceRole(attachmentsData.role)
  const timestamp = coerceTimestamp(attachmentsData.timestamp)
  const eventSeq = context.resolveTimelineSeq(getEventSequence(event))
  const normalized = normalizeAttachments(
    Array.isArray(attachmentsData.attachments) ? attachmentsData.attachments : undefined,
    context.sessionId
  )
  if (normalized.length === 0) return true
  const key = buildAttachmentKey(role, timestamp, normalized)
  const skipDedupe = Boolean(attachmentsData.metadata?.context?.__deferred)
  if (context.attachmentsSeenRef.current.has(key) && !skipDedupe) return true
  context.attachmentsSeenRef.current.add(key)
  context.appendMessage({
    id: createMessageId('attachments'),
    type: 'attachments',
    seq: eventSeq,
    ts: timestamp,
    content: {
      role,
      attachments: normalized,
      timestamp,
    } as AttachmentsContent,
  })
  return true
}

const applyReceiptEvent = (event: AgentSSEEvent, context: ChatEventReducerContext) => {
  const receiptData = event.data as Partial<ReceiptEventData>
  const messageRef = typeof receiptData.message_ref === 'string' ? receiptData.message_ref : ''
  const deliveryState =
    typeof receiptData.delivery_state === 'string' ? receiptData.delivery_state : ''
  if (!messageRef || !deliveryState) return true
  const next = [...context.messagesRef.current]
  const targetIndex = next.findIndex((item) => {
    if (item.type !== 'text_delta' && item.type !== 'user') return false
    const content = item.content as MessageContent & { event_id?: string }
    if (typeof content.event_id === 'string' && content.event_id === messageRef) return true
    const metadata = content.metadata
    if (metadata?.group_message_id === messageRef) return true
    return false
  })
  if (targetIndex < 0) return true
  const target = next[targetIndex]
  const content = target.content as MessageContent
  const nextMeta = { ...(content.metadata ?? {}) }
  nextMeta.delivery_state = deliveryState
  if (typeof receiptData.target_count === 'number') {
    nextMeta.delivery_target_count = receiptData.target_count
  }
  if (typeof receiptData.delivered_count === 'number') {
    nextMeta.delivery_delivered_count = receiptData.delivered_count
  }
  if (typeof receiptData.reply_state === 'string' && receiptData.reply_state.trim()) {
    nextMeta.reply_state = receiptData.reply_state.trim()
  }
  next[targetIndex] = {
    ...target,
    content: {
      ...content,
      metadata: nextMeta,
    } as MessageContent,
  }
  context.updateMessages(next)
  return true
}

export const applyChatEvent = (event: AgentSSEEvent, context: ChatEventReducerContext) => {
  if (!event?.data || typeof event.data !== 'object') return false
  if (event.event === 'message') {
    return applyMessageEvent(event, context)
  }
  if (event.event === 'attachments') {
    return applyAttachmentsEvent(event, context)
  }
  if (event.event === 'receipt') {
    return applyReceiptEvent(event, context)
  }
  return false
}
