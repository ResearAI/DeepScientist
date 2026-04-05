import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getApiBaseUrl } from '@/lib/api/client'
import { getMyToken, refreshAccessToken } from '@/lib/api/auth'
import { handleUnauthorizedAuth, readRequestAuthContext, type RequestAuthMode } from '@/lib/auth'
import { recordRequestEvent } from '@/lib/bugbash/repro-recorder'
import { redactSensitive, sanitizeUrl } from '@/lib/bugbash/sanitize'
import { useChatSessionStore } from '@/lib/stores/session'
import { appendCachedSessionEvent } from '@/lib/stores/chat-event-cache'
import type {
  AgentSSEEvent,
  AttachmentContextPayload,
  AttachmentInfo,
  ChatSurface,
  ExecutionTarget,
} from '@/lib/types/chat-events'
import { getSession } from '@/lib/api/sessions'
import {
  buildQuestStreamUrl,
  getQuestIdFromSessionId,
  normalizeQuestAcpUpdateEnvelope,
  resolveQuestResumeToken,
} from '@/lib/api/quest-session-compat'

const isCopilotDebugEnabled = () => {
  if (typeof window === 'undefined') return false
  return process.env.NODE_ENV !== 'production' || window.localStorage.getItem('ds_debug_copilot') === '1'
}

export type SSEConnectionStatus =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'closed'
  | 'error'
  | 'rate_limited'

export interface SSEConnectionState {
  status: SSEConnectionStatus
  error?: string
  retryAt?: number
}

export interface SSEEventContext {
  runId: number
  sessionId: string
}

export interface SendChatOptions {
  sessionId?: string | null
  message: string
  attachments?: AttachmentInfo[]
  attachmentsSelected?: string[]
  attachmentsAll?: AttachmentContextPayload[]
  recentFiles?: string[]
  surface: ChatSurface
  executionTarget?: ExecutionTarget
  cliServerId?: string | null
  metadata?: Record<string, unknown>
  mentionTargets?: string[]
  replayFromLastEvent?: boolean
  questMessagePosted?: boolean
}

type RuntimeListener = () => void

interface SessionStreamRuntime {
  sessionId: string
  projectId: string | null
  connection: SSEConnectionState
  isStreaming: boolean
  abortController: AbortController | null
  runId: number
  abortedRunId: number | null
  eventSeq: number
  listeners: Set<RuntimeListener>
  eventSubscribers: Set<(event: AgentSSEEvent, context: SSEEventContext) => void>
  connectionSubscribers: Set<(state: SSEConnectionState) => void>
}

const runtimes = new Map<string, SessionStreamRuntime>()

const getRuntime = (sessionId: string) => runtimes.get(sessionId) ?? null

const getOrCreateRuntime = (sessionId: string) => {
  const existing = runtimes.get(sessionId)
  if (existing) return existing
  const runtime: SessionStreamRuntime = {
    sessionId,
    projectId: null,
    connection: { status: 'idle' },
    isStreaming: false,
    abortController: null,
    runId: 0,
    abortedRunId: null,
    eventSeq: 0,
    listeners: new Set(),
    eventSubscribers: new Set(),
    connectionSubscribers: new Set(),
  }
  runtimes.set(sessionId, runtime)
  return runtime
}

const maybeCleanupRuntime = (sessionId: string) => {
  const runtime = runtimes.get(sessionId)
  if (!runtime) return
  if (runtime.isStreaming) return
  if (runtime.abortController) return
  if (runtime.listeners.size > 0) return
  if (runtime.eventSubscribers.size > 0) return
  if (runtime.connectionSubscribers.size > 0) return
  runtimes.delete(sessionId)
}

const hasRuntimeObservers = (runtime: SessionStreamRuntime) => {
  return (
    runtime.listeners.size > 0 ||
    runtime.eventSubscribers.size > 0 ||
    runtime.connectionSubscribers.size > 0
  )
}

let ownerToken: string | null = null
let ownerTokenPromise: Promise<string | null> | null = null

const resolveOwnerToken = async (authMode: RequestAuthMode) => {
  if (authMode !== 'user') return null
  if (typeof window === 'undefined') return null
  if (ownerToken) return ownerToken

  const stored =
    window.localStorage.getItem('ds_owner_token') ||
    window.localStorage.getItem('deepscientist_api_token')
  if (stored) {
    ownerToken = stored
    return stored
  }

  if (ownerTokenPromise) return ownerTokenPromise

  ownerTokenPromise = (async () => {
    try {
      const response = await getMyToken()
      const token = response?.api_token
      if (token && typeof window !== 'undefined') {
        window.localStorage.setItem('ds_owner_token', token)
        ownerToken = token
      }
      return token || null
    } catch {
      return null
    } finally {
      ownerTokenPromise = null
    }
  })()

  return ownerTokenPromise
}

const buildAuthContext = () => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  const { token, mode } = readRequestAuthContext()
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  return { headers, authMode: mode }
}

const handleUnauthorized = (authMode: RequestAuthMode) => {
  handleUnauthorizedAuth(authMode, 'session_expired')
}

const parseEventBlock = (block: string) => {
  const lines = block.split(/\n/)
  let eventType = ''
  let eventId = ''
  const dataLines: string[] = []

  for (const line of lines) {
    if (!line) continue
    if (line.startsWith('event:')) {
      eventType = line.slice(6).trim()
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
      continue
    }
    if (line.startsWith('id:')) {
      eventId = line.slice(3).trim()
    }
  }

  if (dataLines.length === 0) return null
  return {
    event: eventType || 'message',
    data: dataLines.join('\n'),
    id: eventId || undefined,
  }
}

const buildHttpError = async (response: Response) => {
  let detailMessage = ''
  try {
    const contentType = (response.headers.get('content-type') || '').toLowerCase()
    if (contentType.includes('application/json')) {
      const payload = (await response.json()) as {
        detail?: unknown
        message?: unknown
      }
      const detail = payload?.detail
      if (typeof detail === 'string') {
        detailMessage = detail
      } else if (detail && typeof detail === 'object') {
        const detailRecord = detail as Record<string, unknown>
        const message = detailRecord.message
        const requiredMinimum = Number(detailRecord.required_minimum ?? 0)
        const balance = Number(detailRecord.balance ?? 0)
        if (typeof message === 'string' && message.trim()) {
          detailMessage = message
          if (requiredMinimum > 0) {
            detailMessage += ` Required: ${requiredMinimum}, balance: ${balance}.`
          }
        } else if (requiredMinimum > 0) {
          detailMessage = `Insufficient points. Required: ${requiredMinimum}, balance: ${balance}.`
        }
      } else if (typeof payload?.message === 'string' && payload.message.trim()) {
        detailMessage = payload.message
      }
    } else {
      const raw = (await response.text()).trim()
      if (raw) detailMessage = raw
    }
  } catch {
    // ignore body parse errors and fallback to status text.
  }

  const fallback = `HTTP ${response.status}: ${response.statusText}`
  return new Error(detailMessage || fallback)
}

const describeEvent = (event: AgentSSEEvent) => {
  const data = event.data as unknown as Partial<Record<string, unknown>>
  const delta = typeof data.delta === 'string' ? data.delta : ''
  const status = typeof data.status === 'string' ? data.status : undefined
  const eventId = typeof data.event_id === 'string' ? data.event_id : undefined
  const toolCallId = typeof data.tool_call_id === 'string' ? data.tool_call_id : undefined
  const timestamp = typeof data.timestamp === 'number' ? data.timestamp : undefined
  const seq =
    typeof data.seq === 'number'
      ? data.seq
      : typeof (data as { _seq?: unknown })._seq === 'number'
        ? (data as { _seq?: unknown })._seq
        : undefined
  let kind = event.event
  if (event.event === 'message' && delta) {
    kind = 'text_delta'
  } else if (event.event === 'reasoning' && delta) {
    kind = 'reasoning_delta'
  } else if (event.event === 'tool') {
    kind = status === 'calling' ? 'tool_call' : 'tool_result'
  }
  return {
    event: event.event,
    kind,
    eventId,
    toolCallId,
    status,
    timestamp,
    seq,
    deltaLen: delta.length,
  }
}

const debugLog = (runtime: SessionStreamRuntime, scope: string, payload?: Record<string, unknown>) => {
  if (!isCopilotDebugEnabled()) return
  const base = {
    projectId: runtime.projectId ?? null,
    sessionId: runtime.sessionId ?? null,
  }
  if (payload) {
    console.info(`[SSE][${scope}]`, { ...base, ...payload })
    return
  }
  console.info(`[SSE][${scope}]`, base)
}

const notifyRuntime = (runtime: SessionStreamRuntime) => {
  for (const listener of runtime.listeners) {
    try {
      listener()
    } catch {
      // ignore
    }
  }
}

const updateConnection = (runtime: SessionStreamRuntime, next: SSEConnectionState, runId?: number) => {
  if (typeof runId === 'number' && runtime.runId !== runId) return
  runtime.connection = next
  for (const subscriber of runtime.connectionSubscribers) {
    try {
      subscriber(next)
    } catch {
      // ignore
    }
  }
  debugLog(runtime, 'connection', next as unknown as Record<string, unknown>)
  notifyRuntime(runtime)
}

const setStreaming = (runtime: SessionStreamRuntime, next: boolean, runId?: number) => {
  if (typeof runId === 'number' && runtime.runId !== runId) return
  runtime.isStreaming = next
  notifyRuntime(runtime)
}

const coerceEventSeq = (event: AgentSSEEvent) => {
  const data = event.data as unknown as Partial<Record<string, unknown>> | undefined
  if (!data) return null
  const rawSeq = data.seq ?? (data as { sequence?: unknown }).sequence ?? (data as { _seq?: unknown })._seq
  if (typeof rawSeq === 'number' && Number.isFinite(rawSeq)) return rawSeq
  if (typeof rawSeq === 'string') {
    const numeric = Number(rawSeq)
    if (Number.isFinite(numeric)) return numeric
  }
  return null
}

const assignEventSeq = (runtime: SessionStreamRuntime, event: AgentSSEEvent) => {
  const data = event.data as unknown as Record<string, unknown>
  if (!data || typeof data !== 'object') return
  const existing = coerceEventSeq(event)
  if (existing != null) {
    if (existing > runtime.eventSeq) {
      runtime.eventSeq = existing
    }
    if (typeof data.seq !== 'number') {
      data.seq = existing
    }
    return
  }
  runtime.eventSeq += 1
  data.seq = runtime.eventSeq
}

const dispatchEvent = (runtime: SessionStreamRuntime, event: AgentSSEEvent, runId: number) => {
  if (runtime.runId !== runId || runtime.abortedRunId === runId) return
  assignEventSeq(runtime, event)
  appendCachedSessionEvent(runtime.sessionId, event)
  for (const subscriber of runtime.eventSubscribers) {
    try {
      subscriber(event, { runId, sessionId: runtime.sessionId })
    } catch {
      // ignore
    }
  }
}

const buildChatMetadata = (payload: SendChatOptions) => {
  const metadata: Record<string, unknown> = {
    surface: payload.surface,
    execution_target: payload.executionTarget,
    cli_server_id: payload.cliServerId ?? null,
    ...(payload.metadata ?? {}),
  }
  return metadata
}

const postChat = async (payload: SendChatOptions, projectId: string | null, attempt = 0) => {
  const activeSessionId = payload.sessionId
  if (!activeSessionId) return
  const questId = getQuestIdFromSessionId(activeSessionId)

  const { headers, authMode } = buildAuthContext()
  const owner = await resolveOwnerToken(authMode)
  if (owner) {
    headers['X-DS-Owner-Token'] = owner
  }

  if (questId) {
    const message = payload.message ?? ''
    if (isCopilotDebugEnabled()) {
      console.info('[CopilotAudit][stream] quest postChat', {
        projectId,
        sessionId: activeSessionId,
        questId,
        messageLength: message.length,
        attempt,
      })
    }
    if (!message.trim()) return
    const url = `${getApiBaseUrl()}/api/quests/${questId}/chat`
    const method = 'POST'
    const startedAt = Date.now()
    let response: Response
    try {
      response = await fetch(url, {
        method,
        headers,
        body: JSON.stringify({
          text: message,
          source: 'web-react',
        }),
      })
    } catch (error) {
      recordRequestEvent({
        method,
        url: sanitizeUrl(url),
        duration_ms: Date.now() - startedAt,
        error: redactSensitive(error instanceof Error ? error.message : 'request_failed'),
      })
      throw error
    }
    recordRequestEvent({
      method,
      url: sanitizeUrl(url),
      status: response.status,
      duration_ms: Date.now() - startedAt,
    })
    if (response.status === 401) {
      if (authMode === 'user' && attempt < 1) {
        const refreshed = await refreshAccessToken()
        if (refreshed) {
          await postChat(payload, projectId, attempt + 1)
          return
        }
      }
      handleUnauthorized(authMode)
      return
    }
    if (!response.ok) {
      throw await buildHttpError(response)
    }
    return
  }

  const body = {
    message: payload.message ?? '',
    timestamp: Math.floor(Date.now() / 1000),
    attachments: payload.attachments ?? [],
    ...(payload.attachmentsSelected && payload.attachmentsSelected.length > 0
      ? { attachments_selected: payload.attachmentsSelected }
      : {}),
    ...(payload.attachmentsAll && payload.attachmentsAll.length > 0
      ? { attachments_all: payload.attachmentsAll }
      : {}),
    ...(payload.mentionTargets && payload.mentionTargets.length > 0
      ? { mention_targets: payload.mentionTargets }
      : {}),
    metadata: buildChatMetadata(payload),
  }

  const url = `${getApiBaseUrl()}/api/v1/sessions/${activeSessionId}/chat`
  const method = 'POST'
  const startedAt = Date.now()
  let response: Response
  try {
    response = await fetch(url, {
      method,
      headers,
      body: JSON.stringify(body),
    })
  } catch (error) {
    recordRequestEvent({
      method,
      url: sanitizeUrl(url),
      duration_ms: Date.now() - startedAt,
      error: redactSensitive(error instanceof Error ? error.message : 'request_failed'),
    })
    throw error
  }
  recordRequestEvent({
    method,
    url: sanitizeUrl(url),
    status: response.status,
    duration_ms: Date.now() - startedAt,
  })

  if (response.status === 401) {
    if (authMode === 'user' && attempt < 1) {
      const refreshed = await refreshAccessToken()
      if (refreshed) {
        await postChat(payload, projectId, attempt + 1)
        return
      }
    }
    handleUnauthorized(authMode)
    return
  }

  if (!response.ok) {
    throw await buildHttpError(response)
  }
}

const runStream = async (
  runtime: SessionStreamRuntime,
  payload: SendChatOptions,
  runId: number,
  attempt = 0
) => {
  const activeSessionId = payload.sessionId
  if (!activeSessionId) return
  if (runtime.runId !== runId) return
  const questId = getQuestIdFromSessionId(activeSessionId)
  const isQuestSession = Boolean(questId)

  const shouldReplay = Boolean(payload.replayFromLastEvent || attempt > 0)
  const controller = new AbortController()
  runtime.abortController = controller

  setStreaming(runtime, true, runId)
  updateConnection(runtime, { status: attempt > 0 ? 'reconnecting' : 'connecting' }, runId)

  const { headers, authMode } = buildAuthContext()
  const owner = await resolveOwnerToken(authMode)
  if (owner) {
    headers['X-DS-Owner-Token'] = owner
  }

  const message = payload.message ?? ''
  const hasMessage = message.trim().length > 0
  const hasAttachments = (payload.attachments ?? []).length > 0
  const streamOnly = !hasMessage && !hasAttachments
  if (streamOnly) {
    delete headers['Content-Type']
  }

  let currentLastEventId = useChatSessionStore.getState().getLastEventId(activeSessionId)
  const shouldSeedQuestResumeToken =
    isQuestSession && !currentLastEventId && (shouldReplay || streamOnly)
  if (shouldSeedQuestResumeToken) {
    try {
      const seedSession = await getSession(activeSessionId, { limit: 1 })
      const seedToken = resolveQuestResumeToken(seedSession.events ?? [])
      if (seedToken) {
        currentLastEventId = seedToken
        useChatSessionStore.getState().setLastEventId(activeSessionId, seedToken)
      }
    } catch {
      // ignore seed failures and fall back to fresh stream.
    }
  }
  const shouldSendResumeToken =
    Boolean(currentLastEventId) &&
    (shouldReplay || (isQuestSession && (hasMessage || hasAttachments)))
  if (shouldSendResumeToken && currentLastEventId) {
    headers['Last-Event-ID'] = currentLastEventId
  }

  const body = streamOnly
    ? undefined
    : {
        message,
        timestamp: Math.floor(Date.now() / 1000),
        event_id: shouldReplay ? currentLastEventId || undefined : undefined,
        attachments: payload.attachments ?? [],
        ...(payload.attachmentsSelected && payload.attachmentsSelected.length > 0
          ? { attachments_selected: payload.attachmentsSelected }
          : {}),
        ...(payload.attachmentsAll && payload.attachmentsAll.length > 0
          ? { attachments_all: payload.attachmentsAll }
          : {}),
        ...(payload.mentionTargets && payload.mentionTargets.length > 0
          ? { mention_targets: payload.mentionTargets }
          : {}),
        ...(payload.recentFiles && payload.recentFiles.length > 0 ? { recent_files: payload.recentFiles } : {}),
        metadata: buildChatMetadata(payload),
      }

  let cancelReader: (() => void) | null = null
  let handleAbort: (() => void) | null = null
  try {
    let endpoint = streamOnly ? 'stream' : 'chat'
    let url = `${getApiBaseUrl()}/api/v1/sessions/${activeSessionId}/${endpoint}`
    let method: 'GET' | 'POST' = streamOnly ? 'GET' : 'POST'
    let requestBody = body
    if (isQuestSession && questId) {
      endpoint = 'quest_stream'
      url = buildQuestStreamUrl(questId)
      method = 'GET'
      requestBody = undefined
      delete headers['Content-Type']
      if (!streamOnly && (hasMessage || hasAttachments) && !payload.questMessagePosted) {
        await postChat(payload, runtime.projectId ?? projectId ?? null, attempt)
        payload.questMessagePosted = true
      }
    }
    debugLog(runtime, 'start', {
      activeSessionId,
      endpoint,
      attempt,
      streamOnly,
      shouldReplay,
      hasMessage,
      hasAttachments,
      lastEventId: currentLastEventId,
    })

    const startedAt = Date.now()
    let response: Response
    try {
      response = await fetch(url, {
        method,
        headers,
        body: requestBody ? JSON.stringify(requestBody) : undefined,
        signal: controller.signal,
      })
    } catch (error) {
      recordRequestEvent({
        method,
        url: sanitizeUrl(url),
        duration_ms: Date.now() - startedAt,
        error: redactSensitive(error instanceof Error ? error.message : 'request_failed'),
      })
      throw error
    }
    recordRequestEvent({
      method,
      url: sanitizeUrl(url),
      status: response.status,
      duration_ms: Date.now() - startedAt,
    })

    if (runtime.runId !== runId) return

    if (response.status === 429) {
      const retryAfter = Number(response.headers.get('Retry-After') ?? '3')
      const retryMs = Number.isFinite(retryAfter) ? retryAfter * 1000 : 3000
      const retryAt = Date.now() + retryMs
      updateConnection(runtime, { status: 'rate_limited', retryAt, error: 'rate_limited' }, runId)
      setStreaming(runtime, false, runId)
      if (attempt < 3) {
        window.setTimeout(() => {
          if (runtime.runId !== runId) return
          if (runtime.abortController?.signal.aborted) return
          void runStream(runtime, payload, runId, attempt + 1)
        }, retryMs)
      }
      return
    }

    if (response.status === 401) {
      if (authMode === 'user' && attempt < 1) {
        const refreshed = await refreshAccessToken()
        if (refreshed) {
          setStreaming(runtime, false, runId)
          void runStream(runtime, payload, runId, attempt + 1)
          return
        }
      }
      updateConnection(runtime, { status: 'error', error: 'unauthorized' }, runId)
      setStreaming(runtime, false, runId)
      handleUnauthorized(authMode)
      return
    }

    if (!response.ok) {
      throw await buildHttpError(response)
    }

    const contentType = response.headers.get('content-type') || ''
    if (contentType.includes('application/json')) {
      debugLog(runtime, 'closed', { activeSessionId, endpoint, reason: 'json_response' })
      await response.json()
      setStreaming(runtime, false, runId)
      updateConnection(runtime, { status: 'closed' }, runId)
      return
    }

    updateConnection(runtime, { status: 'open' }, runId)

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('No response body')
    }

    const decoder = new TextDecoder()
    let buffer = ''
    let readerCancelled = false
    cancelReader = () => {
      if (readerCancelled) return
      readerCancelled = true
      reader.cancel().catch(() => {})
    }
    handleAbort = () => {
      cancelReader?.()
    }
    if (controller.signal.aborted) {
      handleAbort()
    } else {
      controller.signal.addEventListener('abort', handleAbort, { once: true })
    }

    const dispatchParsedSsePayload = (parsed: { event: string; data: string; id?: string }) => {
      const parsedPayload = JSON.parse(parsed.data) as unknown
      if (isQuestSession) {
        if (parsed.event === 'cursor') {
          const cursorPayload =
            parsedPayload && typeof parsedPayload === 'object' && !Array.isArray(parsedPayload)
              ? (parsedPayload as Record<string, unknown>)
              : null
          const cursor = cursorPayload?.cursor
          if (
            activeSessionId &&
            (typeof cursor === 'number' || (typeof cursor === 'string' && cursor.trim().length > 0))
          ) {
            useChatSessionStore.getState().setLastEventId(activeSessionId, String(cursor))
          }
          return
        }
        const events = normalizeQuestAcpUpdateEnvelope(parsedPayload as Record<string, unknown>)
        if (parsed.id && activeSessionId) {
          useChatSessionStore.getState().setLastEventId(activeSessionId, parsed.id)
        }
        for (const event of events) {
          debugLog(runtime, 'event', describeEvent(event))
          dispatchEvent(runtime, event, runId)
        }
        return
      }

      const data = parsedPayload as AgentSSEEvent['data']
      const event = {
        event: parsed.event as AgentSSEEvent['event'],
        data,
      }
      debugLog(runtime, 'event', describeEvent(event))
      const isTransientDelta =
        (event.event === 'message' || event.event === 'reasoning') &&
        typeof (data as { delta?: string })?.delta === 'string' &&
        Boolean((data as { delta?: string }).delta)
      const resumeToken =
        typeof parsed.id === 'string' && parsed.id.trim().length > 0
          ? parsed.id.trim()
          : data?.event_id && !isTransientDelta
            ? data.event_id
            : null
      if (resumeToken && activeSessionId) {
        useChatSessionStore.getState().setLastEventId(activeSessionId, resumeToken)
      }
      dispatchEvent(runtime, event, runId)
    }

    while (true) {
      if (controller.signal.aborted || runtime.runId !== runId || runtime.abortedRunId === runId) {
        break
      }
      const { done, value } = await reader.read()
      if (done) break
      if (controller.signal.aborted || runtime.runId !== runId || runtime.abortedRunId === runId) {
        break
      }
      buffer += decoder.decode(value, { stream: true })
      if (value && value.length > 0) {
        debugLog(runtime, 'chunk', { bytes: value.length, bufferSize: buffer.length })
      }
      if (buffer.includes('\r')) {
        buffer = buffer.replace(/\r\n/g, '\n')
      }

      let boundaryIndex = buffer.indexOf('\n\n')
      while (boundaryIndex !== -1) {
        if (runtime.runId !== runId) break
        const raw = buffer.slice(0, boundaryIndex)
        buffer = buffer.slice(boundaryIndex + 2)
        const normalized = raw.replace(/\r\n/g, '\n').trim()
        const parsed = parseEventBlock(normalized)
        const shouldDispatch =
          runtime.runId === runId && runtime.abortedRunId !== runId && !controller.signal.aborted
        if (parsed && shouldDispatch) {
          try {
            dispatchParsedSsePayload(parsed)
          } catch (error) {
            console.warn('[SSE] Failed to parse event data', error)
          }
        }
        boundaryIndex = buffer.indexOf('\n\n')
      }
    }

    const trailing = buffer.replace(/\r\n/g, '\n').trim()
    if (
      trailing &&
      runtime.runId === runId &&
      runtime.abortedRunId !== runId &&
      !controller.signal.aborted
    ) {
      const parsed = parseEventBlock(trailing)
      if (parsed) {
        try {
          dispatchParsedSsePayload(parsed)
        } catch (error) {
          console.warn('[SSE] Failed to parse trailing event data', error)
        }
      }
    }

    setStreaming(runtime, false, runId)
    debugLog(runtime, 'closed', { activeSessionId, reason: 'eof' })
    updateConnection(runtime, { status: 'closed' }, runId)
  } catch (error) {
    if (controller.signal.aborted) {
      setStreaming(runtime, false, runId)
      debugLog(runtime, 'closed', { activeSessionId, reason: 'aborted' })
      updateConnection(runtime, { status: 'closed' }, runId)
      return
    }
    const message = error instanceof Error ? error.message : 'SSE error'
    debugLog(runtime, 'error', { activeSessionId, message, attempt })
    updateConnection(runtime, { status: 'error', error: message }, runId)
    setStreaming(runtime, false, runId)
    if (attempt < 1 && runtime.runId === runId) {
      void runStream(runtime, payload, runId, attempt + 1)
    }
  } finally {
    if (cancelReader && !controller.signal.aborted && runtime.abortedRunId === runId) {
      cancelReader()
    }
    if (handleAbort) {
      controller.signal.removeEventListener('abort', handleAbort)
    }
    if (runtime.abortController === controller) {
      runtime.abortController = null
    }
    maybeCleanupRuntime(runtime.sessionId)
  }
}

const startNewRun = (runtime: SessionStreamRuntime) => {
  runtime.runId += 1
  runtime.abortedRunId = null
  const runId = runtime.runId

  if (runtime.abortController) {
    debugLog(runtime, 'abort', { reason: 'new_stream', runId })
    runtime.abortController.abort()
    runtime.abortController = null
  }

  return runId
}

const stopRuntime = (runtime: SessionStreamRuntime) => {
  const abortedRunId = runtime.runId
  runtime.runId += 1
  runtime.abortedRunId = abortedRunId
  if (runtime.abortController) {
    debugLog(runtime, 'stop', { reason: 'user_or_caller' })
    runtime.abortController.abort()
    runtime.abortController = null
  }
  runtime.isStreaming = false
  runtime.connection = { status: 'closed' }
  notifyRuntime(runtime)
  for (const subscriber of runtime.connectionSubscribers) {
    try {
      subscriber(runtime.connection)
    } catch {
      // ignore
    }
  }
  maybeCleanupRuntime(runtime.sessionId)
  return abortedRunId
}

export function useSSESession(options: {
  sessionId?: string | null
  projectId?: string | null
  onEvent?: (event: AgentSSEEvent, context: SSEEventContext) => void
  onConnectionChange?: (state: SSEConnectionState) => void
  autoStopWhenUnobserved?: boolean
}) {
  const {
    sessionId,
    projectId,
    onEvent,
    onConnectionChange,
    autoStopWhenUnobserved = false,
  } = options
  const onEventRef = useRef<typeof onEvent>(onEvent)
  const onConnectionChangeRef = useRef<typeof onConnectionChange>(onConnectionChange)

  useEffect(() => {
    onEventRef.current = onEvent
  }, [onEvent])

  useEffect(() => {
    onConnectionChangeRef.current = onConnectionChange
  }, [onConnectionChange])

  const runtimeSnapshot = useMemo(() => {
    if (!sessionId) {
      return { connection: { status: 'idle' } as SSEConnectionState, isStreaming: false, runId: 0 }
    }
    const runtime = getRuntime(sessionId)
    if (!runtime) {
      return { connection: { status: 'idle' } as SSEConnectionState, isStreaming: false, runId: 0 }
    }
    return { connection: runtime.connection, isStreaming: runtime.isStreaming, runId: runtime.runId }
  }, [sessionId])

  const [connection, setConnectionState] = useState<SSEConnectionState>(runtimeSnapshot.connection)
  const [isStreaming, setIsStreamingState] = useState(runtimeSnapshot.isStreaming)
  const [runId, setRunId] = useState(runtimeSnapshot.runId)

  useEffect(() => {
    if (!sessionId) {
      setConnectionState({ status: 'idle' })
      setIsStreamingState(false)
      setRunId(0)
      return
    }

    const runtime = getOrCreateRuntime(sessionId)
    if (projectId) {
      runtime.projectId = projectId
    }

    const sync = () => {
      const latest = getRuntime(sessionId)
      if (!latest) return
      setConnectionState(latest.connection)
      setIsStreamingState(latest.isStreaming)
      setRunId(latest.runId)
    }

    sync()

    const stateListener: RuntimeListener = () => {
      sync()
    }
    runtime.listeners.add(stateListener)

    const eventListener = (event: AgentSSEEvent, context: SSEEventContext) => {
      onEventRef.current?.(event, context)
    }
    runtime.eventSubscribers.add(eventListener)

    const connectionListener = (next: SSEConnectionState) => {
      onConnectionChangeRef.current?.(next)
    }
    runtime.connectionSubscribers.add(connectionListener)

    return () => {
      runtime.listeners.delete(stateListener)
      runtime.eventSubscribers.delete(eventListener)
      runtime.connectionSubscribers.delete(connectionListener)
      if (
        autoStopWhenUnobserved &&
        !hasRuntimeObservers(runtime) &&
        (runtime.isStreaming || runtime.abortController)
      ) {
        stopRuntime(runtime)
        return
      }
      maybeCleanupRuntime(sessionId)
    }
  }, [autoStopWhenUnobserved, projectId, sessionId])

  const sendMessage = useCallback(
    async (payload: SendChatOptions) => {
      const targetSessionId = payload.sessionId ?? sessionId
      if (!targetSessionId) return
      if (isCopilotDebugEnabled()) {
        console.info('[CopilotAudit][stream] sendMessage', {
          targetSessionId,
          projectId,
          hasMessage: (payload.message ?? '').trim().length > 0,
          attachmentCount: (payload.attachments ?? []).length,
          replayFromLastEvent: Boolean(payload.replayFromLastEvent),
        })
      }

      const runtime = getOrCreateRuntime(targetSessionId)
      if (projectId && !runtime.projectId) {
        runtime.projectId = projectId
      }

      const message = payload.message ?? ''
      const hasMessage = message.trim().length > 0
      const hasAttachments = (payload.attachments ?? []).length > 0
      const streamOnly = !hasMessage && !hasAttachments
      if (streamOnly) {
        const status = runtime.connection.status
        const hasActiveStream =
          runtime.isStreaming ||
          runtime.abortController != null ||
          status === 'connecting' ||
          status === 'open' ||
          status === 'reconnecting' ||
          status === 'rate_limited'
        if (hasActiveStream) return
      }

      const request: SendChatOptions = {
        ...payload,
        sessionId: targetSessionId,
      }

      if (runtime.isStreaming) {
        if (isCopilotDebugEnabled()) {
          console.info('[CopilotAudit][stream] runtime already streaming', {
            targetSessionId,
            streamOnly,
          })
        }
        if (streamOnly) return
        await postChat(request, projectId ?? null, 0)
        return
      }

      const runId = startNewRun(runtime)
      await runStream(runtime, request, runId, 0)
    },
    [projectId, sessionId]
  )

  const stop = useCallback((sessionIdOverride?: string | null) => {
    const targetSessionId = sessionIdOverride ?? sessionId
    if (!targetSessionId) return null
    const runtime = getRuntime(targetSessionId)
    if (!runtime) return null
    return stopRuntime(runtime)
  }, [sessionId])

  const restoreSession = useCallback(
    async (options?: { full?: boolean; limit?: number }) => {
      if (!sessionId) return null
      return getSession(sessionId, options)
    },
    [sessionId]
  )

  return {
    sendMessage,
    stop,
    restoreSession,
    connection,
    isStreaming,
    runId,
  }
}

export const __resetSSESessionManagerForTests = () => {
  runtimes.clear()
  ownerToken = null
  ownerTokenPromise = null
}
