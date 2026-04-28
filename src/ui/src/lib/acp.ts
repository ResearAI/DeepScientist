import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { refreshAccessToken } from '@/lib/api/auth'
import { client } from '@/lib/api'
import { extractArtifactComment, extractOperationComment, extractOperationMonitorFields } from '@/lib/agentComment'
import { authHeaders, handleUnauthorizedAuth, readRequestAuthContext } from '@/lib/auth'
import type { QuestMessageAttachmentDraft } from '@/lib/hooks/useQuestMessageAttachments'
import { countActiveRenderedOperations } from '@/lib/feedOperations'
import { deriveMcpIdentity } from '@/lib/mcpIdentity'
import { buildToolOperationContent, extractToolSubject } from '@/lib/toolOperations'
import type {
  ExplorerPayload,
  FeedEnvelope,
  FeedItem,
  GraphPayload,
  MemoryCard,
  OpenDocumentPayload,
  QuestDocument,
  QuestSummary,
  SessionPayload,
  WorkflowPayload,
} from '@/types'

const MAX_PENDING_ITEMS = 18
const INITIAL_EVENT_LIMIT = 120
const OLDER_HISTORY_PAGE_LIMIT = 80
const MAX_FEED_HISTORY = 2400
const LOCAL_USER_SOURCE = 'web-local'
const DETAILS_MEMORY_CACHE_MS = 2_500
const DETAILS_DOCUMENTS_CACHE_MS = 5_000

type ParsedEvent = {
  id?: string
  event: string
  data: string
}

function safeRandomUUID() {
  if (typeof globalThis !== 'undefined') {
    const cryptoApi = globalThis.crypto as Crypto | undefined
    if (cryptoApi && typeof cryptoApi.randomUUID === 'function') {
      return cryptoApi.randomUUID()
    }
  }

  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
    const rand = (Math.random() * 16) | 0
    const value = char === 'x' ? rand : (rand & 0x3) | 0x8
    return value.toString(16)
  })
}

function buildId(prefix: string, value?: string) {
  return `${prefix}:${value || safeRandomUUID()}`
}

function parseEventBlock(block: string): ParsedEvent | null {
  const lines = block.split(/\n/)
  let eventType = ''
  let eventId = ''
  const dataLines: string[] = []
  for (const line of lines) {
    if (!line || line.startsWith(':')) continue
    if (line.startsWith('id:')) {
      eventId = line.slice(3).trim()
      continue
    }
    if (line.startsWith('event:')) {
      eventType = line.slice(6).trim()
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }
  if (dataLines.length === 0) return null
  return { id: eventId || undefined, event: eventType || 'message', data: dataLines.join('\n') }
}

async function fetchQuestEventsEnvelope(
  questId: string,
  after: number,
  options?: { before?: number | null; limit?: number; tail?: boolean; signal?: AbortSignal }
) {
  const params = new URLSearchParams()
  if (typeof options?.before === 'number' && Number.isFinite(options.before) && options.before > 0) {
    params.set('before', String(Math.floor(options.before)))
  } else {
    params.set('after', String(after))
  }
  params.set('format', 'acp')
  params.set('session_id', `quest:${questId}`)
  if (typeof options?.limit === 'number' && Number.isFinite(options.limit) && options.limit > 0) {
    params.set('limit', String(Math.floor(options.limit)))
  }
  if (options?.tail) {
    params.set('tail', '1')
  }

  const response = await fetch(`/api/quests/${questId}/events?${params.toString()}`, {
    headers: authHeaders({
      'Content-Type': 'application/json',
    }),
    signal: options?.signal,
  })
  if (!response.ok) {
    const message = await response.text().catch(() => '')
    throw new Error(message || `HTTP ${response.status}: ${response.statusText}`)
  }
  return (await response.json()) as FeedEnvelope
}

function stringifyToolPayload(value: unknown) {
  if (value == null) return undefined
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function normalizeMetadata(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined
  return value as Record<string, unknown>
}

function normalizeMessageAttachments(value: unknown) {
  if (!Array.isArray(value)) return undefined
  const items = value.filter(
    (item): item is Record<string, unknown> =>
      Boolean(item) && typeof item === 'object' && !Array.isArray(item)
  )
  return items.length > 0 ? items : undefined
}

function normalizeUpdate(raw: Record<string, unknown>): FeedItem {
  const eventType = String(raw.event_type ?? '')
  const data = (raw.data ?? {}) as Record<string, unknown>
  const toolLabel =
    eventType === 'runner.tool_call' || data.label === 'tool_call'
      ? 'tool_call'
      : eventType === 'runner.tool_result' || data.label === 'tool_result'
        ? 'tool_result'
        : null

  if (toolLabel) {
    const toolName = typeof data.tool_name === 'string' ? data.tool_name : undefined
    const args = stringifyToolPayload(data.args)
    const output = stringifyToolPayload(data.output)
    const metadata = normalizeMetadata(data.metadata)
    const mcpIdentity = deriveMcpIdentity(
      toolName,
      typeof data.mcp_server === 'string' ? data.mcp_server : undefined,
      typeof data.mcp_tool === 'string' ? data.mcp_tool : undefined
    )
    const mcpServer = mcpIdentity.server
    const mcpTool = mcpIdentity.tool
    const subject = extractToolSubject(toolName, args, output)
    const comment = extractOperationComment({ args, output, metadata })
    const monitorFields = extractOperationMonitorFields({ metadata, comment })
    const eventId = String(raw.event_id ?? '').trim() || undefined
    const runId = String((raw.run_id ?? data.run_id ?? metadata?.agent_instance_id ?? '') || '').trim() || null
    return {
      id: buildId('operation', String(raw.event_id ?? raw.created_at ?? safeRandomUUID())),
      type: 'operation',
      eventId,
      runId,
      label: toolLabel,
      content: buildToolOperationContent(toolLabel, toolName, args, output),
      toolName,
      toolCallId: typeof data.tool_call_id === 'string' ? data.tool_call_id : undefined,
      status: typeof data.status === 'string' ? data.status : undefined,
      subject,
      args,
      output,
      createdAt: String(raw.created_at ?? ''),
      mcpServer,
      mcpTool,
      comment,
      monitorPlanSeconds: monitorFields.monitorPlanSeconds,
      monitorStepIndex: monitorFields.monitorStepIndex,
      nextCheckAfterSeconds: monitorFields.nextCheckAfterSeconds,
      metadata: metadata
        ? {
            ...metadata,
            ...(mcpServer ? { mcp_server: mcpServer } : {}),
            ...(mcpTool ? { mcp_tool: mcpTool } : {}),
          }
        : mcpServer || mcpTool
          ? {
              ...(mcpServer ? { mcp_server: mcpServer } : {}),
              ...(mcpTool ? { mcp_tool: mcpTool } : {}),
            }
          : undefined,
    }
  }

  const kind = raw.kind
  if (kind === 'message') {
    const message = (raw.message ?? {}) as Record<string, unknown>
    const isReasoning = eventType === 'runner.reasoning'
    return {
      id: buildId('message', String(raw.event_id ?? raw.created_at ?? safeRandomUUID())),
      type: 'message',
      role: String(message.role ?? 'assistant') === 'user' ? 'user' : 'assistant',
      source: message.source ? String(message.source) : undefined,
      content: String(message.content ?? ''),
      createdAt: String(raw.created_at ?? ''),
      stream: isReasoning ? false : Boolean(message.stream),
      streamId:
        typeof message.stream_id === 'string'
          ? String(message.stream_id)
          : typeof raw.stream_id === 'string'
            ? String(raw.stream_id)
            : null,
      messageId:
        typeof message.message_id === 'string'
          ? String(message.message_id)
          : typeof raw.message_id === 'string'
            ? String(raw.message_id)
            : null,
      runId: message.run_id ? String(message.run_id) : null,
      skillId: message.skill_id ? String(message.skill_id) : null,
      reasoning: isReasoning,
      eventType: eventType || null,
      clientMessageId: message.client_message_id ? String(message.client_message_id) : null,
      deliveryState: message.delivery_state ? String(message.delivery_state) : null,
      readState: message.read_state ? String(message.read_state) : null,
      readReason: message.read_reason ? String(message.read_reason) : null,
      readAt: message.read_at ? String(message.read_at) : null,
      attachments: normalizeMessageAttachments(message.attachments),
    }
  }

  if (kind === 'message_state') {
    const messageState = (raw.message_state ?? {}) as Record<string, unknown>
    return {
      id: buildId('message-state', String(raw.event_id ?? raw.created_at ?? safeRandomUUID())),
      type: 'message_state',
      messageId:
        typeof messageState.message_id === 'string'
          ? String(messageState.message_id)
          : typeof raw.message_id === 'string'
            ? String(raw.message_id)
            : null,
      clientMessageId:
        typeof messageState.client_message_id === 'string'
          ? String(messageState.client_message_id)
          : null,
      readState: messageState.read_state ? String(messageState.read_state) : null,
      readReason: messageState.read_reason ? String(messageState.read_reason) : null,
      readAt: messageState.read_at ? String(messageState.read_at) : null,
      createdAt: String(raw.created_at ?? ''),
    }
  }

  if (kind === 'artifact') {
    const artifact = (raw.artifact ?? {}) as Record<string, unknown>
    return {
      id: buildId('artifact', String(raw.event_id ?? raw.created_at ?? safeRandomUUID())),
      type: 'artifact',
      artifactId: artifact.artifact_id ? String(artifact.artifact_id) : undefined,
      kind: String(artifact.kind ?? 'artifact'),
      status: artifact.status ? String(artifact.status) : undefined,
      content: String(
        artifact.summary ?? artifact.reason ?? artifact.guidance ?? artifact.kind ?? 'Artifact updated.'
      ),
      reason: artifact.reason ? String(artifact.reason) : undefined,
      guidance: artifact.guidance ? String(artifact.guidance) : undefined,
      createdAt: String(raw.created_at ?? ''),
      paths: (artifact.paths as Record<string, string> | undefined) ?? {},
      artifactPath: artifact.artifact_path ? String(artifact.artifact_path) : undefined,
      workspaceRoot: artifact.workspace_root ? String(artifact.workspace_root) : undefined,
      branch: artifact.branch ? String(artifact.branch) : undefined,
      headCommit: artifact.head_commit ? String(artifact.head_commit) : undefined,
      flowType: artifact.flow_type ? String(artifact.flow_type) : undefined,
      protocolStep: artifact.protocol_step ? String(artifact.protocol_step) : undefined,
      ideaId: artifact.idea_id ? String(artifact.idea_id) : null,
      campaignId: artifact.campaign_id ? String(artifact.campaign_id) : null,
      sliceId: artifact.slice_id ? String(artifact.slice_id) : null,
      details:
        artifact.details && typeof artifact.details === 'object' && !Array.isArray(artifact.details)
          ? (artifact.details as Record<string, unknown>)
          : undefined,
      checkpoint:
        artifact.checkpoint && typeof artifact.checkpoint === 'object' && !Array.isArray(artifact.checkpoint)
          ? (artifact.checkpoint as Record<string, unknown>)
          : null,
      attachments: Array.isArray(artifact.attachments)
        ? (artifact.attachments.filter(
            (item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item)
          ) as Array<Record<string, unknown>>)
        : [],
      interactionId: artifact.interaction_id ? String(artifact.interaction_id) : null,
      expectsReply: Boolean(artifact.expects_reply),
      replyMode: artifact.reply_mode ? String(artifact.reply_mode) : null,
      comment: extractArtifactComment(artifact),
    }
  }

  return {
    id: buildId('event', String(raw.event_id ?? raw.created_at ?? safeRandomUUID())),
    type: 'event',
    label: String(data.label ?? raw.event_type ?? 'event'),
    content: String(data.summary ?? data.run_id ?? raw.event_type ?? 'Event updated.'),
    createdAt: String(raw.created_at ?? ''),
  }
}

type MessageFeedItem = Extract<FeedItem, { type: 'message' }>
type MessageStateFeedItem = Extract<FeedItem, { type: 'message_state' }>

type FeedState = {
  history: FeedItem[]
  pending: FeedItem[]
}

type QuestWorkspaceDataView = 'canvas' | 'details' | 'memory' | 'terminal' | 'settings' | 'stage'

export type QuestConnectionState = 'connecting' | 'connected' | 'reconnecting' | 'error'

function appendHistoryItem(history: FeedItem[], item: FeedItem): FeedItem[] {
  if (history.some((existing) => existing.id === item.id)) {
    return history
  }
  const equivalentIndex = findEquivalentAssistantHistoryIndex(history, item)
  if (equivalentIndex >= 0) {
    const next = [...history]
    const existing = next[equivalentIndex]
    if (existing.type === 'message' && item.type === 'message') {
      next[equivalentIndex] = mergeEquivalentAssistantHistoryItem(existing, item)
    }
    return next.slice(-MAX_FEED_HISTORY)
  }
  return [...history, item].slice(-MAX_FEED_HISTORY)
}

function parseFeedItemTimestamp(item: FeedItem) {
  const raw = typeof item.createdAt === 'string' ? item.createdAt : ''
  if (!raw) return null
  const parsed = Date.parse(raw)
  return Number.isFinite(parsed) ? parsed : null
}

function normalizeComparableMessageText(value: string | undefined | null) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
}

function assistantMessagesLookEquivalent(
  left: Extract<FeedItem, { type: 'message' }>,
  right: Extract<FeedItem, { type: 'message' }>
) {
  const leftText = normalizeComparableMessageText(left.content)
  const rightText = normalizeComparableMessageText(right.content)
  if (!leftText || !rightText) return false
  if (leftText === rightText) return true
  const [shorter, longer] =
    leftText.length <= rightText.length ? [leftText, rightText] : [rightText, leftText]
  return shorter.length >= 48 && longer.includes(shorter)
}

function findEquivalentAssistantHistoryIndex(history: FeedItem[], item: FeedItem) {
  if (!(item.type === 'message' && item.role === 'assistant' && !item.reasoning)) {
    return -1
  }
  const itemTs = parseFeedItemTimestamp(item)
  for (let index = history.length - 1; index >= 0; index -= 1) {
    const candidate = history[index]
    if (!(candidate.type === 'message' && candidate.role === 'assistant' && !candidate.reasoning)) {
      continue
    }
    if (item.runId && candidate.runId && item.runId !== candidate.runId) {
      continue
    }
    if (!assistantMessagesLookEquivalent(candidate, item)) {
      continue
    }
    const candidateTs = parseFeedItemTimestamp(candidate)
    if (
      itemTs != null &&
      candidateTs != null &&
      Math.abs(itemTs - candidateTs) > 30_000
    ) {
      continue
    }
    return index
  }
  return -1
}

function mergeEquivalentAssistantHistoryItem(
  existing: Extract<FeedItem, { type: 'message' }>,
  incoming: Extract<FeedItem, { type: 'message' }>
): Extract<FeedItem, { type: 'message' }> {
  const existingEventType = String(existing.eventType || '').trim().toLowerCase()
  const incomingEventType = String(incoming.eventType || '').trim().toLowerCase()
  const preferIncoming = incomingEventType === 'conversation.message' || existingEventType !== 'conversation.message'
  return preferIncoming
    ? {
        ...existing,
        ...incoming,
        content: incoming.content || existing.content,
        createdAt: incoming.createdAt || existing.createdAt,
        source: incoming.source || existing.source,
        runId: incoming.runId || existing.runId || null,
        skillId: incoming.skillId || existing.skillId || null,
        messageId: incoming.messageId || existing.messageId || null,
        streamId: incoming.streamId || existing.streamId || null,
        stream: false,
        reasoning: false,
      }
    : existing
}

function shouldInsertHistoryItemBefore(existing: FeedItem, incoming: FeedItem) {
  const existingTs = parseFeedItemTimestamp(existing)
  const incomingTs = parseFeedItemTimestamp(incoming)
  if (existingTs == null || incomingTs == null) {
    return false
  }
  if (existingTs > incomingTs) {
    return true
  }
  if (existingTs < incomingTs) {
    return false
  }
  return incoming.type === 'message' && incoming.role === 'assistant' && existing.type !== 'message'
}

function insertHistoryItemChronologically(history: FeedItem[], item: FeedItem): FeedItem[] {
  if (history.some((existing) => existing.id === item.id)) {
    return history
  }
  const equivalentIndex = findEquivalentAssistantHistoryIndex(history, item)
  if (equivalentIndex >= 0) {
    const next = [...history]
    const existing = next[equivalentIndex]
    if (existing.type === 'message' && item.type === 'message') {
      next[equivalentIndex] = mergeEquivalentAssistantHistoryItem(existing, item)
    }
    return next.slice(-MAX_FEED_HISTORY)
  }
  const insertIndex = history.findIndex((existing) => shouldInsertHistoryItemBefore(existing, item))
  if (insertIndex < 0) {
    return [...history, item].slice(-MAX_FEED_HISTORY)
  }
  const next = [...history.slice(0, insertIndex), item, ...history.slice(insertIndex)]
  return next.slice(-MAX_FEED_HISTORY)
}

function prependHistoryItems(history: FeedItem[], incoming: FeedItem[]): FeedItem[] {
  if (incoming.length === 0) {
    return history
  }
  const existingIds = new Set(history.map((item) => item.id))
  let nextHistory = [...history]
  let prefix: FeedItem[] = []
  for (const item of incoming) {
    if (item.type === 'message_state') {
      nextHistory = applyMessageStatePatch(nextHistory, item)
      prefix = applyMessageStatePatch(prefix, item)
      continue
    }
    if (existingIds.has(item.id)) {
      continue
    }
    existingIds.add(item.id)
    prefix.push(item)
  }
  return prefix.length > 0 ? [...prefix, ...nextHistory] : nextHistory
}

function parseCursorValue(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
    return Math.floor(value)
  }
  if (typeof value === 'string') {
    const parsed = Number(value)
    if (Number.isFinite(parsed) && parsed > 0) {
      return Math.floor(parsed)
    }
  }
  return null
}

function mergeAssistantMessageContent(left: string, right: string) {
  const base = left || ''
  const next = right || ''
  if (!base) return next
  if (!next) return base
  if (next.startsWith(base)) return next
  if (base.endsWith(next)) return base
  const maxOverlap = Math.min(base.length, next.length)
  for (let size = maxOverlap; size > 0; size -= 1) {
    if (base.slice(-size) === next.slice(0, size)) {
      return `${base}${next.slice(size)}`
    }
  }
  return `${base}${next}`
}

function messageMatchesStatePatch(
  candidate: Extract<FeedItem, { type: 'message' }>,
  patch: MessageStateFeedItem
) {
  if (candidate.role !== 'user') {
    return false
  }
  const patchMessageId = String(patch.messageId || '').trim()
  if (patchMessageId && String(candidate.messageId || '').trim() === patchMessageId) {
    return true
  }
  const patchClientMessageId = String(patch.clientMessageId || '').trim()
  return Boolean(
    patchClientMessageId &&
      String(candidate.clientMessageId || '').trim() === patchClientMessageId
  )
}

function applyMessageStatePatch(items: FeedItem[], patch: MessageStateFeedItem): FeedItem[] {
  let changed = false
  const next = items.map((candidate) => {
    if (candidate.type !== 'message' || !messageMatchesStatePatch(candidate, patch)) {
      return candidate
    }
    changed = true
    return {
      ...candidate,
      readState: patch.readState ?? candidate.readState ?? null,
      readReason: patch.readReason ?? candidate.readReason ?? null,
      readAt: patch.readAt ?? candidate.readAt ?? null,
    }
  })
  return changed ? next : items
}

function removeMatchingLocalPendingUser(pending: FeedItem[], item: MessageFeedItem): FeedItem[] {
  if (item.role !== 'user') {
    return pending
  }
  let removed = false
  return pending.filter((candidate) => {
    if (removed) {
      return true
    }
    if (
      candidate.type === 'message' &&
      candidate.role === 'user' &&
      candidate.source === LOCAL_USER_SOURCE &&
      ((item.clientMessageId &&
        candidate.clientMessageId &&
        item.clientMessageId === candidate.clientMessageId) ||
        candidate.content === item.content)
    ) {
      removed = true
      return false
    }
    return true
  })
}

function upsertPendingAssistant(pending: FeedItem[], item: MessageFeedItem): FeedItem[] {
  const next = [...pending]
  const streamId = String(item.streamId || '').trim()
  const messageId = String(item.messageId || '').trim()
  const runId = String(item.runId || '').trim()
  const matchIndex = next.findIndex(
    (candidate) => {
      if (!(candidate.type === 'message' && candidate.role === 'assistant' && candidate.stream)) {
        return false
      }
      const candidateStreamId = String(candidate.streamId || '').trim()
      const candidateMessageId = String(candidate.messageId || '').trim()
      const candidateRunId = String(candidate.runId || '').trim()
      if (streamId && candidateStreamId) {
        return candidateStreamId === streamId
      }
      if (messageId && candidateMessageId) {
        return candidateMessageId === messageId
      }
      return Boolean(runId && candidateRunId && candidateRunId === runId)
    }
  )
  if (matchIndex >= 0) {
    const current = next[matchIndex]
    if (current.type === 'message') {
      next[matchIndex] = {
        ...current,
        content: mergeAssistantMessageContent(current.content, item.content),
        createdAt: item.createdAt || current.createdAt,
        streamId: item.streamId || current.streamId || null,
        messageId: item.messageId || current.messageId || null,
        skillId: item.skillId || current.skillId,
        source: item.source || current.source,
      }
    }
    return next.slice(-MAX_PENDING_ITEMS)
  }
  return [...next, item].slice(-MAX_PENDING_ITEMS)
}

function flushPendingAssistant(
  pending: FeedItem[],
  item: MessageFeedItem
): { pending: FeedItem[]; finalized: MessageFeedItem } {
  if (item.role !== 'assistant') {
    return { pending, finalized: item }
  }
  const streamId = String(item.streamId || '').trim()
  const messageId = String(item.messageId || '').trim()
  const runId = String(item.runId || '').trim()
  let pendingText = ''
  const nextPending = pending.filter((candidate) => {
    if (!(candidate.type === 'message' && candidate.role === 'assistant' && candidate.stream)) {
      return true
    }
    const candidateStreamId = String(candidate.streamId || '').trim()
    const candidateMessageId = String(candidate.messageId || '').trim()
    const candidateRunId = String(candidate.runId || '').trim()
    const matches =
      (streamId && candidateStreamId && candidateStreamId === streamId) ||
      (messageId && candidateMessageId && candidateMessageId === messageId) ||
      (runId && candidateRunId && candidateRunId === runId)
    if (!matches) {
      return true
    }
    pendingText = candidate.content
    return false
  })
  const matchedPending = pending.find((candidate) => {
    if (!(candidate.type === 'message' && candidate.role === 'assistant' && candidate.stream)) {
      return false
    }
    const candidateStreamId = String(candidate.streamId || '').trim()
    const candidateMessageId = String(candidate.messageId || '').trim()
    const candidateRunId = String(candidate.runId || '').trim()
    return (
      (streamId && candidateStreamId && candidateStreamId === streamId) ||
      (messageId && candidateMessageId && candidateMessageId === messageId) ||
      (runId && candidateRunId && candidateRunId === runId)
    )
  })
  return {
    pending: nextPending,
    finalized: item.content
      ? {
          ...item,
          streamId: item.streamId || matchedPending?.streamId || null,
          messageId: item.messageId || matchedPending?.messageId || null,
        }
      : {
          ...item,
          content: pendingText,
          streamId: item.streamId || matchedPending?.streamId || null,
          messageId: item.messageId || matchedPending?.messageId || null,
        },
  }
}

function shouldKeepPendingAssistantStream(candidate: FeedItem, allowedRunIds: Set<string> | null) {
  if (!(candidate.type === 'message' && candidate.role === 'assistant' && candidate.stream)) {
    return true
  }
  if (!allowedRunIds) {
    return false
  }
  return !candidate.runId || !allowedRunIds.has(candidate.runId)
}

function sealPendingAssistantStreams(
  state: FeedState,
  runIds?: Iterable<string>
): FeedState {
  const allowedRunIds = runIds ? new Set(Array.from(runIds).filter(Boolean)) : null
  let nextHistory = [...state.history]
  const nextPending = state.pending.filter((item) => {
    if (shouldKeepPendingAssistantStream(item, allowedRunIds)) {
      return true
    }
    nextHistory = insertHistoryItemChronologically(nextHistory, {
      ...item,
      stream: false,
    })
    return false
  })
  return {
    history: nextHistory,
    pending: nextPending,
  }
}

function applyIncomingFeedUpdates(state: FeedState, incoming: FeedItem[]): FeedState {
  let nextHistory = [...state.history]
  let nextPending = [...state.pending]
  for (const item of incoming) {
    if (item.type === 'message_state') {
      nextHistory = applyMessageStatePatch(nextHistory, item)
      nextPending = applyMessageStatePatch(nextPending, item)
      continue
    }
    if (item.type === 'message' && item.reasoning) {
      nextHistory = appendHistoryItem(nextHistory, item)
      continue
    }
    if (item.type === 'message' && item.role === 'assistant' && item.stream) {
      nextPending = upsertPendingAssistant(nextPending, item)
      continue
    }
    if (
      item.type === 'message' &&
      item.role === 'assistant' &&
      (item.runId || item.streamId || item.messageId)
    ) {
      const flushed = flushPendingAssistant(nextPending, item)
      nextPending = flushed.pending
      nextHistory = insertHistoryItemChronologically(nextHistory, flushed.finalized)
      continue
    }
    if (item.type === 'message' && item.role === 'user') {
      nextPending = removeMatchingLocalPendingUser(nextPending, item)
      nextHistory = appendHistoryItem(nextHistory, item)
      continue
    }
    nextHistory = appendHistoryItem(nextHistory, item)
  }
  return {
    history: nextHistory,
    pending: nextPending,
  }
}

function draftAttachmentToFeedRecord(attachment: QuestMessageAttachmentDraft): Record<string, unknown> {
  return {
    kind: attachment.kind || (String(attachment.contentType || '').startsWith('image/') ? 'image' : 'path'),
    name: attachment.name,
    file_name: attachment.name,
    content_type: attachment.contentType ?? null,
    size_bytes: attachment.sizeBytes,
    asset_url: attachment.assetUrl ?? null,
    quest_relative_path: attachment.questRelativePath ?? null,
    path: attachment.path ?? null,
    extracted_text_path: attachment.extractedTextPath ?? null,
    preview_url: attachment.previewUrl ?? null,
    draft_id: attachment.draftId,
    status: attachment.status,
  }
}

function createLocalUserFeedItem(
  content: string,
  clientMessageId: string,
  attachments: QuestMessageAttachmentDraft[] = []
): FeedItem {
  return {
    id: buildId('local-user', `${Date.now()}-${safeRandomUUID()}`),
    type: 'message',
    role: 'user',
    content,
    source: LOCAL_USER_SOURCE,
    createdAt: new Date().toISOString(),
    clientMessageId,
    deliveryState: 'sending',
    readState: 'unread',
    readReason: 'queued',
    attachments: attachments.map(draftAttachmentToFeedRecord),
  }
}

function shouldRefreshWorkflow(item: FeedItem) {
  return item.type === 'artifact' || item.type === 'event' || item.type === 'operation'
}

function shouldRefreshSessionSnapshot(item: FeedItem) {
  if (item.type === 'artifact') return true
  if (item.type !== 'event') return false
  return (
    item.label === 'run_started' ||
    item.label === 'run_finished' ||
    item.label === 'run_failed' ||
    item.label === 'quest.control' ||
    item.label === 'artifact.recorded'
  )
}

function collectSealedAssistantRunIds(updates: Array<Record<string, unknown>>) {
  const sealed = new Set<string>()
  for (const update of updates) {
    const eventType = String(update.event_type ?? '').trim()
    const data = update.data
    if (!data || typeof data !== 'object' || Array.isArray(data)) {
      continue
    }
    const record = data as Record<string, unknown>
    const runId = String(record.run_id ?? '').trim()
    const previousRunId = String(record.previous_run_id ?? '').trim()
    if (
      eventType === 'runner.turn_finish' ||
      eventType === 'runner.turn_error' ||
      eventType === 'runner.turn_retry_scheduled' ||
      eventType === 'runner.turn_retry_aborted' ||
      eventType === 'runner.turn_retry_exhausted'
    ) {
      if (runId) {
        sealed.add(runId)
      }
      continue
    }
    if (eventType === 'runner.turn_retry_started' && previousRunId) {
      sealed.add(previousRunId)
    }
  }
  return Array.from(sealed)
}

export function findReplyTargetId(feed: FeedItem[]) {
  // Prefer the most recent unresolved blocking interaction (decision_request,
  // approval, blocking question) so that a free-text reply like "同意" lands on
  // the artifact actually waiting for a user verdict — not on a `progress`
  // heartbeat that happens to be more recent in the feed. Only when no such
  // blocking interaction exists do we fall back to the latest threaded one.
  for (let index = feed.length - 1; index >= 0; index -= 1) {
    const item = feed[index]
    if (item.type !== 'artifact') continue
    if (item.replyMode === 'blocking' || item.expectsReply) {
      return item.interactionId || item.id
    }
  }
  for (let index = feed.length - 1; index >= 0; index -= 1) {
    const item = feed[index]
    if (item.type !== 'artifact') continue
    if (item.replyMode === 'threaded' && item.interactionId) {
      return item.interactionId
    }
  }
  return null
}

function snapshotIndicatesLiveRun(snapshot?: QuestSummary | null) {
  if (!snapshot) return false
  const workspaceMode = String(snapshot.workspace_mode ?? '')
    .trim()
    .toLowerCase()
  const continuationPolicy = String(snapshot.continuation_policy ?? '')
    .trim()
    .toLowerCase()
  const runtimeStatus = String(snapshot.runtime_status ?? snapshot.status ?? '')
    .trim()
    .toLowerCase()
  if (runtimeStatus === 'stopped' || runtimeStatus === 'paused') return false
  const activeRunId = String(snapshot.active_run_id ?? '').trim()
  const bashRunningCount =
    typeof snapshot.counts?.bash_running_count === 'number'
      ? snapshot.counts.bash_running_count
      : 0
  const latestBashSession =
    snapshot.summary?.latest_bash_session &&
    typeof snapshot.summary.latest_bash_session === 'object' &&
    !Array.isArray(snapshot.summary.latest_bash_session)
      ? snapshot.summary.latest_bash_session
      : null
  const latestBashKind = String((latestBashSession as Record<string, unknown> | null)?.kind ?? '')
    .trim()
    .toLowerCase()
  const latestBashId = String((latestBashSession as Record<string, unknown> | null)?.bash_id ?? '')
    .trim()
  const latestActivityRaw = String(snapshot.last_tool_activity_at ?? snapshot.updated_at ?? '')
    .trim()
  const latestActivityMs = latestActivityRaw ? Date.parse(latestActivityRaw) : Number.NaN
  const staleRunningWithoutSignals =
    runtimeStatus === 'running' &&
    !activeRunId &&
    bashRunningCount === 0 &&
    Number.isFinite(latestActivityMs) &&
    Date.now() - latestActivityMs > 90_000

  const isParkedCopilot =
    workspaceMode === 'copilot' &&
    continuationPolicy === 'wait_for_user_or_resume' &&
    !activeRunId &&
    runtimeStatus !== 'running' &&
    (bashRunningCount === 0 ||
      (bashRunningCount === 1 &&
        latestBashKind === 'terminal' &&
        (latestBashId === '' || latestBashId === 'terminal-main')))
  if (isParkedCopilot) return false
  if (staleRunningWithoutSignals) return false
  if (activeRunId) return true
  if (runtimeStatus === 'running') return true
  return bashRunningCount > 0
}

function cacheWindowFresh(lastFetchedAt: number, maxAgeMs: number) {
  return lastFetchedAt > 0 && Date.now() - lastFetchedAt < maxAgeMs
}

function projectionNeedsRefresh(
  payload?: { projection_status?: { state?: string | null } | null } | null
) {
  const state = String(payload?.projection_status?.state || '')
    .trim()
    .toLowerCase()
  return Boolean(state) && state !== 'ready'
}

export function useQuestWorkspace(questId: string | null) {
  const [snapshot, setSnapshot] = useState<QuestSummary | null>(null)
  const [session, setSession] = useState<SessionPayload | null>(null)
  const [memory, setMemory] = useState<MemoryCard[]>([])
  const [documents, setDocuments] = useState<QuestDocument[]>([])
  const [graph, setGraph] = useState<GraphPayload | null>(null)
  const [workflow, setWorkflow] = useState<WorkflowPayload | null>(null)
  const [explorer, setExplorer] = useState<ExplorerPayload | null>(null)
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [detailsReady, setDetailsReady] = useState(false)
  const [history, setHistory] = useState<FeedItem[]>([])
  const [pendingFeed, setPendingFeed] = useState<FeedItem[]>([])
  const [loading, setLoading] = useState(Boolean(questId))
  const [restoring, setRestoring] = useState(Boolean(questId))
  const [historySeeded, setHistorySeeded] = useState(!questId)
  const [hasOlderHistory, setHasOlderHistory] = useState(false)
  const [loadingOlderHistory, setLoadingOlderHistory] = useState(false)
  const [oldestLoadedCursor, setOldestLoadedCursor] = useState<number | null>(null)
  const [newestLoadedCursor, setNewestLoadedCursor] = useState<number | null>(null)
  const [connectionState, setConnectionState] = useState<QuestConnectionState>('connecting')
  const [error, setError] = useState<string | null>(null)
  const [activeDocument, setActiveDocument] = useState<OpenDocumentPayload | null>(null)
  const cursorRef = useRef(0)
  const questIdRef = useRef<string | null>(questId)
  const streamAbortRef = useRef<AbortController | null>(null)
  const streamReconnectRef = useRef<number | null>(null)
  const historyRef = useRef<FeedItem[]>([])
  const pendingFeedRef = useRef<FeedItem[]>([])
  const detailsEnabledRef = useRef(false)
  const sessionInFlightRef = useRef<{
    questId: string
    promise: Promise<SessionPayload | null>
  } | null>(null)
  const detailsInFlightRef = useRef<{
    questId: string
    force: boolean
    promise: Promise<WorkflowPayload | null>
  } | null>(null)
  const detailsMemoryFetchedAtRef = useRef(0)
  const detailsDocumentsFetchedAtRef = useRef(0)
  const detailsRefreshTimerRef = useRef<number | null>(null)
  const detailsRefreshInFlightRef = useRef(false)
  const detailsRefreshPendingRef = useRef(false)
  const sessionRefreshTimerRef = useRef<number | null>(null)
  const sessionRefreshInFlightRef = useRef(false)
  const sessionRefreshPendingRef = useRef(false)
  const pendingStreamCleanupTimerRef = useRef<number | null>(null)
  const lastEventIdRef = useRef<string | null>(null)
  const oldestLoadedCursorRef = useRef<number | null>(null)
  const newestLoadedCursorRef = useRef<number | null>(null)
  const hasLiveRunRef = useRef(false)

  const feed = useMemo(() => [...history, ...pendingFeed], [history, pendingFeed])
  const slashCommands = useMemo(() => session?.acp_session?.slash_commands ?? [], [session])
  const replyTargetId = useMemo(() => {
    const snapshotTarget =
      snapshot?.default_reply_interaction_id ||
      session?.acp_session?.meta?.default_reply_interaction_id
    return snapshotTarget || findReplyTargetId(feed)
  }, [feed, session, snapshot])
  const hasLiveRun = useMemo(() => {
    const currentSnapshot = session?.snapshot ?? snapshot
    return snapshotIndicatesLiveRun(currentSnapshot)
  }, [session, snapshot])
  const streaming = useMemo(
    () =>
      hasLiveRun &&
      pendingFeed.some(
        (item) => item.type === 'message' && item.role === 'assistant' && item.stream
      ),
    [hasLiveRun, pendingFeed]
  )
  const activeToolCount = useMemo(
    () => (hasLiveRun ? countActiveRenderedOperations(feed.slice(-180)) : 0),
    [feed, hasLiveRun]
  )

  useEffect(() => {
    hasLiveRunRef.current = hasLiveRun
  }, [hasLiveRun])

  const updateFeedState = useCallback((nextState: FeedState) => {
    historyRef.current = nextState.history
    pendingFeedRef.current = nextState.pending
    setHistory(nextState.history)
    setPendingFeed(nextState.pending)
  }, [])

  const updateHistoryWindow = useCallback((args: {
    oldestCursor?: number | null
    newestCursor?: number | null
    hasOlder?: boolean
  }) => {
    if ('oldestCursor' in args) {
      const nextOldest = args.oldestCursor ?? null
      oldestLoadedCursorRef.current = nextOldest
      setOldestLoadedCursor(nextOldest)
    }
    if ('newestCursor' in args) {
      const nextNewest = args.newestCursor ?? null
      newestLoadedCursorRef.current = nextNewest
      setNewestLoadedCursor(nextNewest)
    }
    if ('hasOlder' in args && typeof args.hasOlder === 'boolean') {
      setHasOlderHistory(args.hasOlder)
    }
  }, [])

  const fetchSessionState = useCallback(async (targetQuestId: string) => {
    const inFlight = sessionInFlightRef.current
    if (inFlight && inFlight.questId === targetQuestId) {
      return inFlight.promise
    }

    const promise = client
      .session(targetQuestId)
      .then((nextSession) => {
        if (questIdRef.current !== targetQuestId) {
          return null
        }
        setSession(nextSession)
        setSnapshot(nextSession.snapshot)
        return nextSession
      })
      .finally(() => {
        if (sessionInFlightRef.current?.promise === promise) {
          sessionInFlightRef.current = null
        }
      })

    sessionInFlightRef.current = {
      questId: targetQuestId,
      promise,
    }
    return promise
  }, [])

  const hydrateState = useCallback(
    async (targetQuestId: string) => fetchSessionState(targetQuestId),
    [fetchSessionState]
  )

  const hydrateDetailsState = useCallback(async (targetQuestId: string, options?: { force?: boolean }) => {
    const force = Boolean(options?.force)
    const inFlight = detailsInFlightRef.current
    if (inFlight && inFlight.questId === targetQuestId && (!force || inFlight.force)) {
      return inFlight.promise
    }

    const shouldFetchMemory =
      force ||
      !detailsReady ||
      !cacheWindowFresh(detailsMemoryFetchedAtRef.current, DETAILS_MEMORY_CACHE_MS)
    const shouldFetchDocuments =
      force ||
      !detailsReady ||
      !cacheWindowFresh(detailsDocumentsFetchedAtRef.current, DETAILS_DOCUMENTS_CACHE_MS)

    const workflowPromise = client.workflow(targetQuestId).then((nextWorkflow) => {
      if (questIdRef.current === targetQuestId) {
        setWorkflow(nextWorkflow)
      }
      return nextWorkflow
    })
    const memoryPromise = shouldFetchMemory
      ? client.memory(targetQuestId).then((nextMemory) => {
          if (questIdRef.current === targetQuestId) {
            detailsMemoryFetchedAtRef.current = Date.now()
            setMemory(nextMemory)
          }
          return nextMemory
        })
      : Promise.resolve<MemoryCard[] | null>(null)
    const documentsPromise = shouldFetchDocuments
      ? client.documents(targetQuestId).then((nextDocuments) => {
          if (questIdRef.current === targetQuestId) {
            detailsDocumentsFetchedAtRef.current = Date.now()
            setDocuments(nextDocuments)
          }
          return nextDocuments
        })
      : Promise.resolve<QuestDocument[] | null>(null)

    const promise = Promise.allSettled([
      workflowPromise,
      memoryPromise,
      documentsPromise,
    ])
      .then(([workflowResult, memoryResult, documentsResult]) => {
        if (workflowResult.status !== 'fulfilled') {
          throw workflowResult.reason
        }
        if (memoryResult.status === 'rejected') {
          console.warn('[useQuestWorkspace] Failed to refresh quest memory.', memoryResult.reason)
        }
        if (documentsResult.status === 'rejected') {
          console.warn('[useQuestWorkspace] Failed to refresh quest documents.', documentsResult.reason)
        }
        if (questIdRef.current !== targetQuestId) {
          return null
        }
        setDetailsReady(true)
        return workflowResult.value
      })
      .finally(() => {
        if (detailsInFlightRef.current?.promise === promise) {
          detailsInFlightRef.current = null
        }
      })

    detailsInFlightRef.current = {
      questId: targetQuestId,
      force,
      promise,
    }
    return promise
  }, [detailsReady])

  const syncSessionSnapshot = useCallback(
    async (targetQuestId: string) => fetchSessionState(targetQuestId),
    [fetchSessionState]
  )

  const clearDetailsRefresh = useCallback(() => {
    if (detailsRefreshTimerRef.current) {
      window.clearTimeout(detailsRefreshTimerRef.current)
      detailsRefreshTimerRef.current = null
    }
    detailsRefreshPendingRef.current = false
  }, [])

  const clearSessionRefresh = useCallback(() => {
    if (sessionRefreshTimerRef.current) {
      window.clearTimeout(sessionRefreshTimerRef.current)
      sessionRefreshTimerRef.current = null
    }
    sessionRefreshPendingRef.current = false
  }, [])

  const clearPendingStreamCleanup = useCallback(() => {
    if (pendingStreamCleanupTimerRef.current) {
      window.clearTimeout(pendingStreamCleanupTimerRef.current)
      pendingStreamCleanupTimerRef.current = null
    }
  }, [])

  const schedulePendingStreamCleanup = useCallback(() => {
    clearPendingStreamCleanup()
    pendingStreamCleanupTimerRef.current = window.setTimeout(() => {
      pendingStreamCleanupTimerRef.current = null
      const nextState = sealPendingAssistantStreams({
        history: historyRef.current,
        pending: pendingFeedRef.current,
      })
      if (
        nextState.pending.length === pendingFeedRef.current.length &&
        nextState.history.length === historyRef.current.length
      ) {
        return
      }
      updateFeedState(nextState)
    }, 800)
  }, [clearPendingStreamCleanup, updateFeedState])

  const stopEventStream = useCallback(() => {
    if (streamAbortRef.current) {
      streamAbortRef.current.abort()
      streamAbortRef.current = null
    }
    if (streamReconnectRef.current) {
      window.clearTimeout(streamReconnectRef.current)
      streamReconnectRef.current = null
    }
  }, [])

  const flushDetailsRefresh = useCallback(
    async (targetQuestId: string, options?: { force?: boolean }) => {
      if (questIdRef.current !== targetQuestId || !detailsEnabledRef.current) {
        return
      }
      if (detailsRefreshInFlightRef.current) {
        detailsRefreshPendingRef.current = true
        return
      }
      detailsRefreshInFlightRef.current = true
      setDetailsLoading(true)
      try {
        const nextWorkflow = await hydrateDetailsState(targetQuestId, options)
        const shouldContinuePolling =
          questIdRef.current === targetQuestId &&
          detailsEnabledRef.current &&
          (projectionNeedsRefresh(nextWorkflow) || hasLiveRunRef.current)
        if (shouldContinuePolling && !detailsRefreshTimerRef.current) {
          const delay = projectionNeedsRefresh(nextWorkflow) ? 900 : 1500
          detailsRefreshTimerRef.current = window.setTimeout(() => {
            detailsRefreshTimerRef.current = null
            void flushDetailsRefresh(targetQuestId)
          }, delay)
        }
      } catch (caught) {
        if (questIdRef.current === targetQuestId) {
          setError(caught instanceof Error ? caught.message : String(caught))
        }
      } finally {
        detailsRefreshInFlightRef.current = false
        if (questIdRef.current === targetQuestId) {
          setDetailsLoading(false)
        }
        if (detailsRefreshPendingRef.current && questIdRef.current === targetQuestId) {
          detailsRefreshPendingRef.current = false
          window.setTimeout(() => {
            void flushDetailsRefresh(targetQuestId)
          }, 180)
        }
      }
    },
    [hydrateDetailsState]
  )

  const flushSessionRefresh = useCallback(
    async (targetQuestId: string) => {
      if (questIdRef.current !== targetQuestId) {
        return
      }
      if (sessionRefreshInFlightRef.current) {
        sessionRefreshPendingRef.current = true
        return
      }
      sessionRefreshInFlightRef.current = true
      try {
        await syncSessionSnapshot(targetQuestId)
      } catch (caught) {
        if (questIdRef.current === targetQuestId) {
          console.warn('[useQuestWorkspace] Failed to refresh quest session.', caught)
          setConnectionState((current) => (current === 'connected' ? 'reconnecting' : current))
          setError('Session refresh failed; retrying...')
        }
      } finally {
        sessionRefreshInFlightRef.current = false
        if (sessionRefreshPendingRef.current && questIdRef.current === targetQuestId) {
          sessionRefreshPendingRef.current = false
          window.setTimeout(() => {
            void flushSessionRefresh(targetQuestId)
          }, 120)
        }
      }
    },
    [syncSessionSnapshot]
  )

  const queueDetailsRefresh = useCallback(
    (targetQuestId: string, delay = 180) => {
      if (questIdRef.current !== targetQuestId || !detailsEnabledRef.current) {
        return
      }
      if (detailsRefreshTimerRef.current) {
        detailsRefreshPendingRef.current = true
        return
      }
      detailsRefreshTimerRef.current = window.setTimeout(() => {
        detailsRefreshTimerRef.current = null
        void flushDetailsRefresh(targetQuestId)
      }, delay)
    },
    [flushDetailsRefresh]
  )

  const queueSessionRefresh = useCallback(
    (targetQuestId: string, delay = 240) => {
      if (questIdRef.current !== targetQuestId) {
        return
      }
      if (sessionRefreshTimerRef.current) {
        sessionRefreshPendingRef.current = true
        return
      }
      sessionRefreshTimerRef.current = window.setTimeout(() => {
        sessionRefreshTimerRef.current = null
        void flushSessionRefresh(targetQuestId)
      }, delay)
    },
    [flushSessionRefresh]
  )

  const applyUpdates = useCallback(
    async (targetQuestId: string, updates: Array<Record<string, unknown>>) => {
      if (questIdRef.current !== targetQuestId || updates.length === 0) {
        return
      }
      const highestCursor = updates.reduce<number | null>((current, item) => {
        const nextValue = parseCursorValue(item.cursor)
        if (nextValue == null) {
          return current
        }
        return current == null ? nextValue : Math.max(current, nextValue)
      }, null)
      const normalized = updates.map((item) => normalizeUpdate(item))
      const sealedRunIds = collectSealedAssistantRunIds(updates)
      let nextState = applyIncomingFeedUpdates(
        {
          history: historyRef.current,
          pending: pendingFeedRef.current,
        },
        normalized
      )
      if (sealedRunIds.length > 0) {
        nextState = sealPendingAssistantStreams(nextState, sealedRunIds)
      }
      updateFeedState(nextState)
      if (highestCursor != null) {
        updateHistoryWindow({
          newestCursor: Math.max(newestLoadedCursorRef.current ?? 0, highestCursor),
        })
      }
      if (normalized.some((item) => shouldRefreshSessionSnapshot(item))) {
        const nextSession = await syncSessionSnapshot(targetQuestId)
        if (snapshotIndicatesLiveRun(nextSession?.snapshot ?? null)) {
          clearPendingStreamCleanup()
        } else {
          clearPendingStreamCleanup()
          const sealedState = sealPendingAssistantStreams({
            history: historyRef.current,
            pending: pendingFeedRef.current,
          })
          if (
            sealedState.pending.length !== pendingFeedRef.current.length ||
            sealedState.history.length !== historyRef.current.length
          ) {
            updateFeedState(sealedState)
          }
        }
      }
      if (normalized.some((item) => item.type === 'message' && item.role === 'assistant' && item.stream)) {
        schedulePendingStreamCleanup()
      }
      if (normalized.some((item) => item.type === 'message' && item.role === 'assistant' && !item.stream)) {
        clearPendingStreamCleanup()
      }
      if (
        detailsEnabledRef.current &&
        normalized.some(
          (item) =>
            item.type === 'artifact' ||
            (shouldRefreshWorkflow(item) &&
              item.type === 'event' &&
              ['run_finished', 'run_failed', 'quest.control', 'artifact.recorded'].includes(item.label || ''))
        )
      ) {
        queueDetailsRefresh(targetQuestId)
      }
      if (normalized.some((item) => shouldRefreshSessionSnapshot(item))) {
        queueSessionRefresh(targetQuestId)
      }
    },
    [
      clearPendingStreamCleanup,
      queueDetailsRefresh,
      queueSessionRefresh,
      schedulePendingStreamCleanup,
      syncSessionSnapshot,
      updateFeedState,
      updateHistoryWindow,
    ]
  )

  const bootstrap = useCallback(
    async (reset = false) => {
      if (!questId) {
        return
      }
      const targetQuestId = questId
      setLoading(true)
      if (reset) {
        setRestoring(true)
        setHistorySeeded(false)
        setConnectionState('connecting')
        cursorRef.current = 0
        lastEventIdRef.current = null
        updateHistoryWindow({
          oldestCursor: null,
          newestCursor: null,
          hasOlder: false,
        })
        setLoadingOlderHistory(false)
        updateFeedState({ history: [], pending: [] })
      }
      try {
        const after = reset ? 0 : cursorRef.current
        const nextSession = await client.session(targetQuestId)
        if (!nextSession || questIdRef.current !== targetQuestId) {
          return
        }
        setSession(nextSession)
        setSnapshot(nextSession.snapshot)
        setError(null)
        setConnectionState('connected')

        const loadInitialFeed = async (attempt = 0) => {
          const controller = new AbortController()
          const timeoutMs = attempt === 0 ? 12000 : 20000
          const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs)
          try {
            const nextFeed = reset
              ? await fetchQuestEventsEnvelope(targetQuestId, 0, {
                  limit: INITIAL_EVENT_LIMIT,
                  tail: true,
                  signal: controller.signal,
                })
              : await fetchQuestEventsEnvelope(targetQuestId, after, {
                  signal: controller.signal,
                })
            if (questIdRef.current !== targetQuestId) {
              return
            }

            const initialUpdates = (nextFeed.acp_updates ?? []).map((item) => item.params.update)
            const normalized = initialUpdates.map((item) => normalizeUpdate(item))
            const sealedRunIds = collectSealedAssistantRunIds(initialUpdates)
            const baseState: FeedState = {
              history: historyRef.current,
              pending: pendingFeedRef.current,
            }
            let nextState = applyIncomingFeedUpdates(baseState, normalized)

            if (sealedRunIds.length > 0) {
              nextState = sealPendingAssistantStreams(nextState, sealedRunIds)
            }

            if (nextSession.snapshot?.status && nextSession.snapshot.status !== 'running') {
              nextState = sealPendingAssistantStreams(nextState)
            }

            updateFeedState(nextState)
            cursorRef.current = typeof nextFeed.cursor === 'number' ? nextFeed.cursor : after
            lastEventIdRef.current = String(cursorRef.current)
            if (reset) {
              updateHistoryWindow({
                oldestCursor: parseCursorValue(nextFeed.oldest_cursor),
                newestCursor:
                  parseCursorValue(nextFeed.newest_cursor) ??
                  parseCursorValue(nextFeed.cursor),
                hasOlder: Boolean(nextFeed.has_more),
              })
            } else {
              const nextNewestCursor =
                parseCursorValue(nextFeed.newest_cursor) ??
                parseCursorValue(nextFeed.cursor)
              if (nextNewestCursor != null) {
                updateHistoryWindow({
                  newestCursor: Math.max(newestLoadedCursorRef.current ?? 0, nextNewestCursor),
                })
              }
            }
            setHistorySeeded(true)
          } catch (caught) {
            if (questIdRef.current !== targetQuestId) {
              return
            }
            if (attempt < 2) {
              window.setTimeout(() => {
                void loadInitialFeed(attempt + 1)
              }, 900 * (attempt + 1))
              return
            }
            if (historyRef.current.length === 0 && pendingFeedRef.current.length === 0) {
              setError(caught instanceof Error ? caught.message : String(caught))
              setConnectionState('error')
            }
          } finally {
            window.clearTimeout(timeoutId)
          }
        }

        window.setTimeout(() => {
          void loadInitialFeed(0)
        }, reset ? 120 : 0)
      } catch (caught) {
        if (questIdRef.current === targetQuestId) {
          setError(caught instanceof Error ? caught.message : String(caught))
          setConnectionState('error')
        }
      } finally {
        if (questIdRef.current === targetQuestId) {
          setLoading(false)
          setRestoring(false)
        }
      }
    },
    [questId, updateFeedState, updateHistoryWindow]
  )

  const loadOlderHistory = useCallback(async () => {
    if (!questId || loadingOlderHistory || !hasOlderHistory) {
      return
    }
    const before = oldestLoadedCursorRef.current
    if (!before || before <= 1) {
      updateHistoryWindow({ hasOlder: false })
      return
    }
    const targetQuestId = questId
    setLoadingOlderHistory(true)
    setError(null)
    try {
      const response = await client.events(targetQuestId, 0, {
        before,
        limit: OLDER_HISTORY_PAGE_LIMIT,
      })
      if (questIdRef.current !== targetQuestId) {
        return
      }
      const normalized = (response.acp_updates ?? []).map((item) => normalizeUpdate(item.params.update))
      updateFeedState({
        history: prependHistoryItems(historyRef.current, normalized),
        pending: pendingFeedRef.current,
      })
      updateHistoryWindow({
        oldestCursor: parseCursorValue(response.oldest_cursor) ?? oldestLoadedCursorRef.current,
        hasOlder: Boolean(response.has_more),
      })
    } catch (caught) {
      if (questIdRef.current === targetQuestId) {
        setError(caught instanceof Error ? caught.message : String(caught))
      }
    } finally {
      if (questIdRef.current === targetQuestId) {
        setLoadingOlderHistory(false)
      }
    }
  }, [hasOlderHistory, loadingOlderHistory, questId, updateFeedState, updateHistoryWindow])

  const patchQueuedMessageState = useCallback(
    (args: {
      messageId?: string | null
      clientMessageId?: string | null
      readState?: string | null
      readReason?: string | null
      readAt?: string | null
    }) => {
      const normalizedMessageId = String(args.messageId || '').trim()
      const normalizedClientMessageId = String(args.clientMessageId || '').trim()
      if (!normalizedMessageId && !normalizedClientMessageId) {
        return
      }
      const patchItem = (item: FeedItem) => {
        if (item.type !== 'message' || item.role !== 'user') {
          return item
        }
        const matches =
          (normalizedMessageId && String(item.messageId || '').trim() === normalizedMessageId) ||
          (normalizedClientMessageId && String(item.clientMessageId || '').trim() === normalizedClientMessageId)
        if (!matches) {
          return item
        }
        return {
          ...item,
          readState: args.readState ?? item.readState ?? null,
          readReason: args.readReason ?? item.readReason ?? null,
          readAt: args.readAt ?? item.readAt ?? null,
        }
      }
      updateFeedState({
        history: historyRef.current.map(patchItem),
        pending: pendingFeedRef.current.map(patchItem),
      })
    },
    [updateFeedState]
  )

  const submit = useCallback(
    async (
      value: string,
      attachments: QuestMessageAttachmentDraft[] = [],
      options: { displayValue?: string | null } = {}
    ) => {
      const trimmed = value.trim()
      const displayTrimmed = String(options.displayValue ?? value).trim()
      const successfulAttachments = attachments.filter((item) => item.status === 'success')
      if ((!trimmed && successfulAttachments.length === 0) || !questId) {
        return
      }
      setError(null)
      if (trimmed.startsWith('/') && successfulAttachments.length === 0) {
        await client.sendCommand(questId, trimmed)
        await bootstrap(false)
        return
      }

      const clientMessageId = safeRandomUUID()
      const cursorBeforeSend = cursorRef.current
      const localUserItem = createLocalUserFeedItem(displayTrimmed || trimmed, clientMessageId, successfulAttachments)
      updateFeedState({
        history: historyRef.current,
        pending: [...pendingFeedRef.current, localUserItem].slice(-MAX_PENDING_ITEMS),
      })
      clearPendingStreamCleanup()

      try {
        const response = await client.sendChat(
          questId,
          trimmed,
          replyTargetId,
          clientMessageId,
          successfulAttachments.map((item) => item.draftId)
        )
        const nextDeliveryState =
          response?.message?.delivery_state ? String(response.message.delivery_state) : 'sent'
        const serverMessageId = response?.message?.id ? String(response.message.id) : null
        const serverClientMessageId = response?.message?.client_message_id
          ? String(response.message.client_message_id)
          : clientMessageId
        updateFeedState({
          history: historyRef.current,
          pending: pendingFeedRef.current.map((item) =>
            item.id === localUserItem.id && item.type === 'message'
              ? {
                  ...item,
                  messageId: serverMessageId || item.messageId || null,
                  clientMessageId: serverClientMessageId || item.clientMessageId || null,
                  deliveryState: nextDeliveryState,
                  createdAt: response?.message?.created_at
                    ? String(response.message.created_at)
                    : item.createdAt,
                  readState: response?.message?.read_state
                    ? String(response.message.read_state)
                    : item.readState,
                  readReason: response?.message?.read_reason
                    ? String(response.message.read_reason)
                    : item.readReason,
                  readAt: response?.message?.read_at ? String(response.message.read_at) : item.readAt,
                  attachments:
                    normalizeMessageAttachments(response?.message?.attachments) || item.attachments,
                }
              : item
          ),
        })
        queueSessionRefresh(questId, 300)
        const ensureReplyVisible = (delay: number) => {
          window.setTimeout(() => {
            if (questIdRef.current !== questId) return
            if (cursorRef.current > cursorBeforeSend) return
            void bootstrap(false)
          }, delay)
        }
        ensureReplyVisible(connectionState === 'connected' ? 1800 : 600)
        ensureReplyVisible(9000)
      } catch (caught) {
        updateFeedState({
          history: historyRef.current,
          pending: pendingFeedRef.current.map((item) =>
            item.id === localUserItem.id && item.type === 'message'
              ? { ...item, deliveryState: 'failed' }
              : item
          ),
        })
        throw caught
      }
    },
    [
      bootstrap,
      clearPendingStreamCleanup,
      connectionState,
      questId,
      queueSessionRefresh,
      replyTargetId,
      updateFeedState,
    ]
  )

  const readNow = useCallback(
    async (messageId: string) => {
      const normalizedMessageId = messageId.trim()
      if (!normalizedMessageId || !questId) {
        return
      }
      setError(null)
      const response = await client.readQueuedMessagesNow(questId, normalizedMessageId)
      const currentMessageState = response?.current_message_state
      const messageStates = [
        ...(Array.isArray(response?.message_states) ? response.message_states : []),
        ...(currentMessageState ? [currentMessageState] : []),
      ]
      const deliveredAt =
        (response?.delivery_batch?.delivered_at ? String(response.delivery_batch.delivered_at) : '') ||
        new Date().toISOString()
      const recentInboundMessages = Array.isArray(response?.recent_inbound_messages)
        ? response.recent_inbound_messages
        : []
      for (const messageState of messageStates) {
        patchQueuedMessageState({
          messageId: messageState.message_id,
          clientMessageId: messageState.client_message_id,
          readState: messageState.read_state,
          readReason: messageState.read_reason,
          readAt: messageState.read_at,
        })
      }
      for (const inboundMessage of recentInboundMessages) {
        patchQueuedMessageState({
          messageId: inboundMessage.message_id,
          clientMessageId: inboundMessage.client_message_id,
          readState: inboundMessage.read_state || 'read',
          readReason: inboundMessage.read_reason || 'immediate_read',
          readAt: inboundMessage.read_at || deliveredAt,
        })
      }
      const resolvedMessageIds = new Set(
        (response.message_ids || []).map((item) => String(item || '').trim()).filter(Boolean)
      )
      const resolvedClientMessageIds = new Set(
        [
          ...(response.client_message_ids || []),
          ...recentInboundMessages.map((item) => item.client_message_id),
          ...messageStates.map((item) => item.client_message_id),
        ]
          .map((item) => String(item || '').trim())
          .filter(Boolean)
      )
      if (resolvedMessageIds.size > 0 || resolvedClientMessageIds.size > 0) {
        const patchMessage = (item: FeedItem) => {
          const itemMessageId = String(item.type === 'message' ? item.messageId || '' : '').trim()
          const itemClientMessageId = String(item.type === 'message' ? item.clientMessageId || '' : '').trim()
          if (
            item.type === 'message' &&
            item.role === 'user' &&
            ((itemMessageId && resolvedMessageIds.has(itemMessageId)) ||
              (itemClientMessageId && resolvedClientMessageIds.has(itemClientMessageId)))
          ) {
            return {
              ...item,
              messageId:
                item.messageId ||
                recentInboundMessages.find(
                  (candidate) =>
                    String(candidate.client_message_id || '').trim() === itemClientMessageId
                )?.message_id ||
                null,
              readState: 'read' as const,
              readReason:
                String(response?.status || '').trim() === 'already_read'
                  ? (currentMessageState?.read_reason || item.readReason || 'accepted_by_run')
                  : 'immediate_read',
              readAt: deliveredAt,
            }
          }
          return item
        }
        updateFeedState({
          history: historyRef.current.map(patchMessage),
          pending: pendingFeedRef.current.map(patchMessage),
        })
      }
      if (!response?.ok) {
        return response
      }
      queueSessionRefresh(questId, 300)
      const confirmationRefreshDelays = [900, 2500, 9000]
      confirmationRefreshDelays.forEach((delay) => {
        window.setTimeout(() => {
          if (questIdRef.current !== questId) return
          void bootstrap(false)
        }, delay)
      })
      return response
    },
    [bootstrap, patchQueuedMessageState, questId, queueSessionRefresh, updateFeedState]
  )

  const withdraw = useCallback(
    async (messageId: string) => {
      const normalizedMessageId = messageId.trim()
      if (!normalizedMessageId || !questId) {
        return
      }
      setError(null)
      const response = await client.withdrawQueuedMessage(questId, normalizedMessageId)
      const currentMessageState = response?.current_message_state
      if (currentMessageState) {
        patchQueuedMessageState({
          messageId: currentMessageState.message_id,
          clientMessageId: currentMessageState.client_message_id,
          readState: currentMessageState.read_state,
          readReason: currentMessageState.read_reason,
          readAt: currentMessageState.read_at,
        })
      } else if (response?.ok && response.status === 'withdrawn') {
        patchQueuedMessageState({
          messageId: response.message_id || normalizedMessageId,
          readState: 'read',
          readReason: 'withdrawn_by_user',
          readAt: new Date().toISOString(),
        })
      }
      if (response?.ok) {
        queueSessionRefresh(questId, 300)
      }
      return response
    },
    [patchQueuedMessageState, questId, queueSessionRefresh]
  )

  const stopRun = useCallback(async () => {
    if (!questId) return
    await client.controlQuest(questId, 'stop')
    await bootstrap(false)
  }, [bootstrap, questId])

  const ensureViewData = useCallback(
    async (view: QuestWorkspaceDataView, options?: { force?: boolean }) => {
      if (!questId) {
        return
      }
      detailsEnabledRef.current = true
      if (detailsReady && !options?.force) {
        return
      }
      clearDetailsRefresh()
      await flushDetailsRefresh(questId, options)
    },
    [clearDetailsRefresh, detailsReady, flushDetailsRefresh, questId]
  )

  useEffect(() => {
    questIdRef.current = questId
  }, [questId])

  useEffect(() => {
    setSnapshot(null)
    setSession(null)
    setMemory([])
    setDocuments([])
    setGraph(null)
    setWorkflow(null)
    setExplorer(null)
    setDetailsLoading(false)
    setDetailsReady(false)
    setHistory([])
    setPendingFeed([])
    historyRef.current = []
    pendingFeedRef.current = []
    cursorRef.current = 0
    oldestLoadedCursorRef.current = null
    newestLoadedCursorRef.current = null
    setHasOlderHistory(false)
    setLoadingOlderHistory(false)
    setOldestLoadedCursor(null)
    setNewestLoadedCursor(null)
    setConnectionState(questId ? 'connecting' : 'connected')
    setHistorySeeded(!questId)
    setError(null)
    detailsEnabledRef.current = false
    sessionInFlightRef.current = null
    detailsInFlightRef.current = null
    detailsMemoryFetchedAtRef.current = 0
    detailsDocumentsFetchedAtRef.current = 0
    detailsRefreshInFlightRef.current = false
    clearDetailsRefresh()
    clearSessionRefresh()
    clearPendingStreamCleanup()
    stopEventStream()
    lastEventIdRef.current = null
    if (!questId) {
      return
    }
    setRestoring(true)
    void bootstrap(true)
  }, [bootstrap, clearDetailsRefresh, clearPendingStreamCleanup, clearSessionRefresh, questId, stopEventStream])

  const runEventStream = useCallback(
    async (targetQuestId: string, attempt = 0) => {
      if (!targetQuestId || questIdRef.current !== targetQuestId) {
        return
      }
      stopEventStream()
      const controller = new AbortController()
      streamAbortRef.current = controller
      setConnectionState(attempt > 0 ? 'reconnecting' : 'connecting')

      try {
        const { mode: authMode } = readRequestAuthContext()
        const headers = authHeaders({
          Accept: 'text/event-stream',
        })
        if (lastEventIdRef.current) {
          headers['Last-Event-ID'] = lastEventIdRef.current
        }
        const response = await fetch(client.eventsStreamUrl(targetQuestId, cursorRef.current), {
          method: 'GET',
          headers,
          signal: controller.signal,
        })

        if (response.status === 401) {
          if (authMode === 'user' && attempt < 1) {
            const refreshed = await refreshAccessToken()
            if (refreshed) {
              setConnectionState('reconnecting')
              void runEventStream(targetQuestId, attempt + 1)
              return
            }
          }
          if (questIdRef.current === targetQuestId) {
            setConnectionState('error')
            setError('unauthorized')
            handleUnauthorizedAuth(authMode, 'session_expired')
          }
          return
        }

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }
        if (!response.body) {
          throw new Error('No event stream body')
        }

        if (questIdRef.current === targetQuestId) {
          setError(null)
          setConnectionState('connected')
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')

          let boundaryIndex = buffer.indexOf('\n\n')
          while (boundaryIndex !== -1) {
            const raw = buffer.slice(0, boundaryIndex)
            buffer = buffer.slice(boundaryIndex + 2)
            const parsed = parseEventBlock(raw.trim())
            if (parsed?.id) {
              lastEventIdRef.current = parsed.id
            }
            if (parsed?.event === 'acp_update') {
              const payload = JSON.parse(parsed.data) as { params?: { update?: Record<string, unknown> } }
              const update = payload.params?.update
              if (update) {
                const nextCursor = Number(update.cursor ?? cursorRef.current)
                if (Number.isFinite(nextCursor)) {
                  cursorRef.current = nextCursor
                  lastEventIdRef.current = String(nextCursor)
                }
                await applyUpdates(targetQuestId, [update])
              }
            } else if (parsed?.event === 'cursor') {
              const payload = JSON.parse(parsed.data) as { cursor?: number }
              if (typeof payload.cursor === 'number') {
                cursorRef.current = payload.cursor
                lastEventIdRef.current = String(payload.cursor)
              }
            }
            boundaryIndex = buffer.indexOf('\n\n')
          }
        }

        if (!controller.signal.aborted && questIdRef.current === targetQuestId) {
          const nextAttempt = 1
          const delay = Math.min(1000 * 2 ** Math.min(nextAttempt, 5), 30000)
          setConnectionState('reconnecting')
          setError('Event stream reconnecting…')
          streamReconnectRef.current = window.setTimeout(() => {
            void runEventStream(targetQuestId, nextAttempt)
          }, delay)
        }
      } catch (caught) {
        if (controller.signal.aborted) {
          return
        }
        if (questIdRef.current === targetQuestId) {
          setConnectionState(attempt > 0 ? 'reconnecting' : 'error')
          setError('Event stream reconnecting…')
          const nextAttempt = attempt + 1
          const delay = Math.min(1000 * 2 ** Math.min(nextAttempt, 5), 30000)
          streamReconnectRef.current = window.setTimeout(() => {
            void runEventStream(targetQuestId, nextAttempt)
          }, delay)
        }
      } finally {
        if (streamAbortRef.current === controller) {
          streamAbortRef.current = null
        }
      }
    },
    [applyUpdates, stopEventStream]
  )

  useEffect(() => {
    if (!questId || restoring || !historySeeded) {
      return
    }
    const targetQuestId = questId
    void runEventStream(targetQuestId, 0)
    return () => {
      stopEventStream()
      clearDetailsRefresh()
      clearSessionRefresh()
      clearPendingStreamCleanup()
    }
  }, [clearDetailsRefresh, clearPendingStreamCleanup, clearSessionRefresh, historySeeded, questId, restoring, runEventStream, stopEventStream])

  const refreshWorkspace = useCallback(
    async (reset = true) => {
      await bootstrap(reset)
      if (!reset && detailsEnabledRef.current) {
        await ensureViewData('details', { force: true })
      }
    },
    [bootstrap, ensureViewData]
  )

  return {
    snapshot,
    session,
    memory,
    documents,
    graph,
    workflow,
    explorer,
    detailsLoading,
    detailsReady,
    feed,
    history,
    pendingFeed,
    loading,
    restoring,
    hasOlderHistory,
    loadingOlderHistory,
    oldestLoadedCursor,
    newestLoadedCursor,
    historyTruncated: hasOlderHistory,
    historyLimit: history.length,
    historyExpanded: !hasOlderHistory,
    historyLoadingFull: loadingOlderHistory,
    historySeeded,
    hasLiveRun,
    streaming,
    activeToolCount,
    connectionState,
    error,
    slashCommands,
    activeDocument,
    replyTargetId,
    setActiveDocument,
    refresh: refreshWorkspace,
    ensureViewData,
    loadOlderHistory,
    loadFullHistory: loadOlderHistory,
    submit,
    readNow,
    withdraw,
    stopRun,
  }
}
