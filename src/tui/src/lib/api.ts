import type {
  BashLogEntry,
  BashProgress,
  BashSession,
  ConfigFileEntry,
  ConnectorAvailabilitySnapshot,
  ConnectorSnapshot,
  FeedEnvelope,
  OpenDocumentPayload,
  QuestSummary,
  SessionPayload,
  WeixinQrLoginStartPayload,
  WeixinQrLoginWaitPayload,
} from '../types.js'

let daemonAuthToken: string | null = null

function toHeaderRecord(headers?: HeadersInit): Record<string, string> {
  if (!headers) return {}
  if (headers instanceof Headers) {
    return Object.fromEntries(headers.entries())
  }
  if (Array.isArray(headers)) {
    return Object.fromEntries(headers)
  }
  return { ...headers }
}

function authHeaders(headers?: HeadersInit): HeadersInit {
  const normalizedToken = typeof daemonAuthToken === 'string' ? daemonAuthToken.trim() : ''
  if (!normalizedToken) {
    return toHeaderRecord(headers)
  }
  return {
    ...toHeaderRecord(headers),
    Authorization: `Bearer ${normalizedToken}`,
  }
}

export function setDaemonAuthToken(value: string | null | undefined) {
  const normalized = typeof value === 'string' ? value.trim() : ''
  daemonAuthToken = normalized || null
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(await response.text())
  }
  return (await response.json()) as T
}

export async function api<T>(baseUrl: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(authHeaders(init?.headers) as Record<string, string>),
    },
  })
  return parseResponse<T>(response)
}

function parseSseChunk(block: string) {
  let event = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (!line || line.startsWith(':')) {
      continue
    }
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
      continue
    }
    if (line.startsWith('data:')) {
      data.push(line.slice(5).trimStart())
    }
  }
  return {
    event,
    data: data.join('\n'),
  }
}

type BashLogSnapshotEvent = {
  bash_id: string
  latest_seq?: number | null
  lines?: BashLogEntry[]
  progress?: BashProgress | null
}

type BashLogBatchEvent = {
  bash_id: string
  from_seq?: number | null
  to_seq?: number | null
  lines?: BashLogEntry[]
}

type BashLogDoneEvent = {
  bash_id: string
  status?: string
  exit_code?: number | null
  finished_at?: string | null
}

export const client = {
  quests: (baseUrl: string) => api<QuestSummary[]>(baseUrl, '/api/quests'),
  createQuest: (baseUrl: string, goal: string) =>
    api<{ ok: boolean; snapshot: QuestSummary }>(baseUrl, '/api/quests', {
      method: 'POST',
      body: JSON.stringify({ goal }),
    }),
  deleteQuest: (baseUrl: string, questId: string) =>
    api<{ ok: boolean; quest_id: string; deleted?: boolean }>(baseUrl, `/api/quests/${questId}`, {
      method: 'DELETE',
      body: JSON.stringify({ source: 'tui-ink' }),
    }),
  connectors: (baseUrl: string) => api<ConnectorSnapshot[]>(baseUrl, '/api/connectors'),
  connectorsAvailability: (baseUrl: string) =>
    api<ConnectorAvailabilitySnapshot>(baseUrl, '/api/connectors/availability'),
  startWeixinQrLogin: (baseUrl: string, force = false) =>
    api<WeixinQrLoginStartPayload>(baseUrl, '/api/connectors/weixin/login/qr/start', {
      method: 'POST',
      body: JSON.stringify({ force }),
    }),
  waitWeixinQrLogin: (baseUrl: string, sessionKey: string, timeoutMs = 1500) =>
    api<WeixinQrLoginWaitPayload>(baseUrl, '/api/connectors/weixin/login/qr/wait', {
      method: 'POST',
      body: JSON.stringify({ session_key: sessionKey, timeout_ms: timeoutMs }),
    }),
  session: (baseUrl: string, questId: string) => api<SessionPayload>(baseUrl, `/api/quests/${questId}/session`),
  openDocument: (baseUrl: string, questId: string, documentId: string) =>
    api<OpenDocumentPayload>(baseUrl, `/api/quests/${questId}/documents/open`, {
      method: 'POST',
      body: JSON.stringify({ document_id: documentId }),
    }),
  saveDocument: (baseUrl: string, questId: string, documentId: string, content: string, revision?: string) =>
    api<{
      ok: boolean
      conflict?: boolean
      message?: string
      revision?: string
      updated_payload?: OpenDocumentPayload
    }>(baseUrl, `/api/quests/${questId}/documents/${documentId}`, {
      method: 'PUT',
      body: JSON.stringify({ content, revision }),
    }),
  events: (baseUrl: string, questId: string, cursor: number) =>
    api<FeedEnvelope>(baseUrl, `/api/quests/${questId}/events?after=${cursor}&format=acp&session_id=quest:${questId}`),
  eventsStreamUrl: (baseUrl: string, questId: string, cursor = 0) =>
    `${baseUrl}/api/quests/${questId}/events?after=${cursor}&format=acp&session_id=quest:${questId}&stream=1`,
  streamEvents: async (
    baseUrl: string,
    questId: string,
    cursor: number,
    callbacks: {
      onUpdate: (payload: Record<string, unknown>) => void
      onCursor?: (cursor: number) => void
      signal: AbortSignal
    }
  ) => {
    const response = await fetch(client.eventsStreamUrl(baseUrl, questId, cursor), {
      headers: {
        Accept: 'text/event-stream',
        ...(authHeaders() as Record<string, string>),
      },
      signal: callbacks.signal,
    })
    if (!response.ok || !response.body) {
      throw new Error(await response.text())
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { value, done } = await reader.read()
      if (done) {
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() ?? ''
      for (const block of blocks) {
        const parsed = parseSseChunk(block)
        if (!parsed.data) {
          continue
        }
        if (parsed.event === 'acp_update') {
          callbacks.onUpdate(JSON.parse(parsed.data) as Record<string, unknown>)
          continue
        }
        if (parsed.event === 'cursor' && callbacks.onCursor) {
          const payload = JSON.parse(parsed.data) as { cursor?: number }
          if (typeof payload.cursor === 'number') {
            callbacks.onCursor(payload.cursor)
          }
        }
      }
    }
  },
  sendChat: (baseUrl: string, questId: string, text: string, replyToInteractionId?: string | null) =>
    api<{ ok: boolean; ack?: string }>(baseUrl, `/api/quests/${questId}/chat`, {
      method: 'POST',
      body: JSON.stringify({ text, source: 'tui-ink', reply_to_interaction_id: replyToInteractionId || undefined }),
    }),
  sendCommand: (baseUrl: string, questId: string, command: string) =>
    api<Record<string, unknown>>(baseUrl, `/api/quests/${questId}/commands`, {
      method: 'POST',
      body: JSON.stringify({ command, source: 'tui-ink' }),
    }),
  controlQuest: (baseUrl: string, questId: string, action: 'pause' | 'stop' | 'resume') =>
    api<Record<string, unknown>>(baseUrl, `/api/quests/${questId}/control`, {
      method: 'POST',
      body: JSON.stringify({ action, source: 'tui-ink' }),
    }),
  getBashSession: (baseUrl: string, questId: string, bashId: string) =>
    api<BashSession>(baseUrl, `/api/quests/${questId}/bash/sessions/${bashId}`),
  getBashLogs: async (
    baseUrl: string,
    questId: string,
    bashId: string,
    params?: {
      limit?: number
      beforeSeq?: number
      order?: 'asc' | 'desc'
    }
  ) => {
    const search = new URLSearchParams()
    if (typeof params?.limit === 'number') {
      search.set('limit', String(params.limit))
    }
    if (typeof params?.beforeSeq === 'number') {
      search.set('before_seq', String(params.beforeSeq))
    }
    if (params?.order) {
      search.set('order', params.order)
    }
    const suffix = search.toString() ? `?${search.toString()}` : ''
    const response = await fetch(`${baseUrl}/api/quests/${questId}/bash/sessions/${bashId}/logs${suffix}`, {
      headers: authHeaders(),
    })
    if (!response.ok) {
      throw new Error(await response.text())
    }
    const entries = (await response.json()) as BashLogEntry[]
    return {
      entries,
      meta: {
        tailLimit: response.headers.get('X-Bash-Log-Tail-Limit'),
        tailStartSeq: response.headers.get('X-Bash-Log-Tail-Start-Seq'),
        latestSeq: response.headers.get('X-Bash-Log-Latest-Seq'),
      },
    }
  },
  streamBashLogs: async (
    baseUrl: string,
    questId: string,
    bashId: string,
    callbacks: {
      signal: AbortSignal
      lastEventId?: number | null
      onSnapshot?: (payload: BashLogSnapshotEvent) => void
      onLogBatch?: (payload: BashLogBatchEvent) => void
      onProgress?: (payload: BashProgress & { bash_id: string }) => void
      onDone?: (payload: BashLogDoneEvent) => void
    }
  ) => {
    const headers: Record<string, string> = {
      Accept: 'text/event-stream',
    }
    if (typeof callbacks.lastEventId === 'number') {
      headers['Last-Event-ID'] = String(callbacks.lastEventId)
    }
    const response = await fetch(`${baseUrl}/api/quests/${questId}/bash/sessions/${bashId}/stream`, {
      method: 'GET',
      headers: authHeaders(headers),
      signal: callbacks.signal,
    })
    if (!response.ok || !response.body) {
      throw new Error(await response.text())
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { value, done } = await reader.read()
      if (done) {
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() ?? ''
      for (const block of blocks) {
        const parsed = parseSseChunk(block)
        if (!parsed.data) {
          continue
        }
        if (parsed.event === 'snapshot') {
          callbacks.onSnapshot?.(JSON.parse(parsed.data) as BashLogSnapshotEvent)
          continue
        }
        if (parsed.event === 'log_batch') {
          callbacks.onLogBatch?.(JSON.parse(parsed.data) as BashLogBatchEvent)
          continue
        }
        if (parsed.event === 'progress') {
          callbacks.onProgress?.(JSON.parse(parsed.data) as BashProgress & { bash_id: string })
          continue
        }
        if (parsed.event === 'done') {
          callbacks.onDone?.(JSON.parse(parsed.data) as BashLogDoneEvent)
        }
      }
    }
  },
  configFiles: (baseUrl: string) => api<ConfigFileEntry[]>(baseUrl, '/api/config/files'),
  configDocument: (baseUrl: string, name: string) => api<OpenDocumentPayload>(baseUrl, `/api/config/${name}`),
  saveConfig: (baseUrl: string, name: string, content: string, revision?: string) =>
    api<{
      ok: boolean
      conflict?: boolean
      message?: string
      revision?: string
      warnings?: string[]
      errors?: string[]
    }>(baseUrl, `/api/config/${name}`, {
      method: 'PUT',
      body: JSON.stringify({ content, revision }),
    }),
  saveStructuredConfig: (baseUrl: string, name: string, structured: Record<string, unknown>, revision?: string) =>
    api<{
      ok: boolean
      conflict?: boolean
      message?: string
      revision?: string
      warnings?: string[]
      errors?: string[]
    }>(baseUrl, `/api/config/${name}`, {
      method: 'PUT',
      body: JSON.stringify({ structured, revision }),
    }),
  updateQuestBindings: (
    baseUrl: string,
    questId: string,
    payload: {
      connector?: string | null
      conversation_id?: string | null
      bindings?: Array<{
        connector: string
        conversation_id?: string | null
      }>
      force?: boolean
    }
  ) =>
    api<Record<string, unknown>>(baseUrl, `/api/quests/${questId}/bindings`, {
      method: Array.isArray(payload.bindings) ? 'PUT' : 'POST',
      body: JSON.stringify(payload),
    }),
}
