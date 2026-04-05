import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getApiBaseUrl } from '@/lib/api/client'
import { refreshAccessToken } from '@/lib/api/auth'
import { handleUnauthorizedAuth, readRequestAuthContext, type RequestAuthMode } from '@/lib/auth'
import { listBashSessions } from '@/lib/api/bash'
import type { BashSession } from '@/lib/types/bash'

export type BashSessionStreamState = {
  status: 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed' | 'error'
  error?: string
}

const normalizeList = (values?: string[]) => {
  if (!values || values.length === 0) {
    return { key: '', list: undefined as string[] | undefined }
  }
  const unique = Array.from(new Set(values.filter(Boolean)))
  unique.sort()
  return { key: unique.join(','), list: unique }
}

type StreamOptions = {
  projectId?: string | null
  agentInstanceIds?: string[]
  agentIds?: string[]
  status?: string
  chatSessionId?: string | null
  limit?: number
  enabled?: boolean
  stream?: boolean
}

type ParsedEvent = {
  event: string
  data: string
}

const parseEventBlock = (block: string): ParsedEvent | null => {
  const lines = block.split(/\n/)
  let eventType = ''
  const dataLines: string[] = []
  for (const line of lines) {
    if (!line || line.startsWith(':')) continue
    if (line.startsWith('event:')) {
      eventType = line.slice(6).trim()
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }
  if (dataLines.length === 0) return null
  return { event: eventType || 'message', data: dataLines.join('\n') }
}

const isLikelyNetworkStreamError = (error: unknown) => {
  const message = error instanceof Error ? error.message : String(error ?? '')
  return /failed to fetch|fetch failed|networkerror|err_connection_refused|load failed/i.test(message)
}

const sortSessions = (sessions: BashSession[]) =>
  [...sessions].sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at))

const mergeSessions = (previous: BashSession[], incoming: BashSession) => {
  if (!incoming?.bash_id) return previous
  const map = new Map(previous.map((session) => [session.bash_id, session]))
  const existing = map.get(incoming.bash_id)
  const merged = existing ? { ...existing, ...incoming } : incoming
  map.set(incoming.bash_id, merged)
  return sortSessions(Array.from(map.values()))
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

export function useBashSessionStream({
  projectId,
  agentInstanceIds,
  agentIds,
  status,
  chatSessionId,
  limit = 200,
  enabled = true,
  stream = true,
}: StreamOptions) {
  const normalizedAgentInstanceIds = useMemo(
    () => normalizeList(agentInstanceIds),
    [agentInstanceIds]
  )
  const normalizedAgentIds = useMemo(() => normalizeList(agentIds), [agentIds])
  const [sessions, setSessions] = useState<BashSession[]>([])
  const [connection, setConnection] = useState<BashSessionStreamState>({ status: 'idle' })
  const abortRef = useRef<AbortController | null>(null)
  const reconnectRef = useRef<number | null>(null)
  const hasSnapshotRef = useRef(false)

  const queryKey = useMemo(() => {
    return [
      projectId ?? '',
      status ?? '',
      chatSessionId ?? '',
      normalizedAgentInstanceIds.key,
      normalizedAgentIds.key,
      String(limit),
    ].join('|')
  }, [
    chatSessionId,
    limit,
    normalizedAgentIds.key,
    normalizedAgentInstanceIds.key,
    projectId,
    status,
  ])

  const updateConnection = useCallback((next: BashSessionStreamState) => {
    setConnection(next)
  }, [])

  const stopStream = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    if (reconnectRef.current) {
      window.clearTimeout(reconnectRef.current)
      reconnectRef.current = null
    }
  }, [])

  const reload = useCallback(async () => {
    if (!enabled || !projectId) {
      setSessions([])
      return
    }
    try {
      const response = await listBashSessions(projectId, {
        status,
        agentInstanceIds: normalizedAgentInstanceIds.list,
        agentIds: normalizedAgentIds.list,
        chatSessionId: chatSessionId ?? undefined,
        limit,
      })
      setSessions(sortSessions(response))
    } catch (error) {
      updateConnection({
        status: 'error',
        error: error instanceof Error ? error.message : 'fetch_failed',
      })
    }
  }, [
    chatSessionId,
    enabled,
    limit,
    normalizedAgentIds.key,
    normalizedAgentInstanceIds.key,
    projectId,
    status,
    updateConnection,
  ])

  const runStream = useCallback(
    async (attempt = 0) => {
      if (!enabled || !projectId) return

      stopStream()
      const controller = new AbortController()
      abortRef.current = controller
      updateConnection({ status: attempt > 0 ? 'reconnecting' : 'connecting' })

      const { headers, authMode } = buildAuthContext()
      delete headers['Content-Type']

      const query = new URLSearchParams()
      query.set('limit', String(limit))
      if (status) query.set('status', status)
      if (chatSessionId) query.set('chat_session_id', chatSessionId)
      if (normalizedAgentInstanceIds.key) {
        query.set('agent_instance_ids', normalizedAgentInstanceIds.key)
      }
      if (normalizedAgentIds.key) {
        query.set('agent_ids', normalizedAgentIds.key)
      }

      try {
        const response = await fetch(
          `${getApiBaseUrl()}/api/quests/${projectId}/bash/sessions/stream?${query.toString()}`,
          {
            method: 'GET',
            headers,
            signal: controller.signal,
          }
        )

        if (response.status === 401) {
          if (authMode === 'user' && attempt < 1) {
            const refreshed = await refreshAccessToken()
            if (refreshed) {
              updateConnection({ status: 'reconnecting' })
              await runStream(attempt + 1)
              return
            }
          }
          updateConnection({ status: 'error', error: 'unauthorized' })
          handleUnauthorized(authMode)
          return
        }

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }

        updateConnection({ status: 'open' })
        const reader = response.body?.getReader()
        if (!reader) {
          throw new Error('No response body')
        }

        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          if (buffer.includes('\r')) {
            buffer = buffer.replace(/\r\n/g, '\n')
          }

          let boundaryIndex = buffer.indexOf('\n\n')
          while (boundaryIndex !== -1) {
            const raw = buffer.slice(0, boundaryIndex)
            buffer = buffer.slice(boundaryIndex + 2)
            const normalized = raw.replace(/\r\n/g, '\n').trim()
            const parsed = parseEventBlock(normalized)
            if (parsed) {
              try {
                if (parsed.event === 'snapshot') {
                  const data = JSON.parse(parsed.data) as { sessions?: BashSession[] }
                  if (Array.isArray(data.sessions)) {
                    hasSnapshotRef.current = true
                    setSessions(sortSessions(data.sessions))
                  }
                }
                if (parsed.event === 'session') {
                  const data = JSON.parse(parsed.data) as { session?: BashSession }
                  if (data.session) {
                    setSessions((current) => mergeSessions(current, data.session as BashSession))
                  }
                }
              } catch (error) {
                console.warn('[Bash sessions SSE] Failed to parse event data', error)
              }
            }
            boundaryIndex = buffer.indexOf('\n\n')
          }
        }

        const trailing = buffer.replace(/\r\n/g, '\n').trim()
        if (trailing) {
          const parsed = parseEventBlock(trailing)
          if (parsed) {
            try {
              if (parsed.event === 'snapshot') {
                const data = JSON.parse(parsed.data) as { sessions?: BashSession[] }
                if (Array.isArray(data.sessions)) {
                  hasSnapshotRef.current = true
                  setSessions(sortSessions(data.sessions))
                }
              }
              if (parsed.event === 'session') {
                const data = JSON.parse(parsed.data) as { session?: BashSession }
                if (data.session) {
                  setSessions((current) => mergeSessions(current, data.session as BashSession))
                }
              }
            } catch (error) {
              console.warn('[Bash sessions SSE] Failed to parse trailing event data', error)
            }
          }
        }
        if (!controller.signal.aborted) {
          const nextAttempt = 1
          const delay = Math.min(1000 * 2 ** Math.min(nextAttempt, 5), 30000)
          if (hasSnapshotRef.current && nextAttempt % 3 === 0) {
            void reload()
          }
          updateConnection({ status: 'reconnecting' })
          reconnectRef.current = window.setTimeout(() => {
            void runStream(nextAttempt)
          }, delay)
        }
      } catch (error) {
        if (controller.signal.aborted) {
          updateConnection({ status: 'closed' })
          return
        }
        const nextAttempt = attempt + 1
        const delay = Math.min(1000 * 2 ** Math.min(nextAttempt, 5), 30000)
        updateConnection({
          status: 'error',
          error: error instanceof Error ? error.message : 'stream_failed',
        })
        if ((!isLikelyNetworkStreamError(error) && !hasSnapshotRef.current) || (hasSnapshotRef.current && nextAttempt % 3 === 0)) {
          void reload()
        }
        reconnectRef.current = window.setTimeout(() => {
          void runStream(nextAttempt)
        }, delay)
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null
        }
      }
    },
    [
      chatSessionId,
      enabled,
      limit,
      normalizedAgentIds.key,
      normalizedAgentInstanceIds.key,
      projectId,
      reload,
      stopStream,
      status,
      updateConnection,
    ]
  )

  useEffect(() => {
    if (!enabled || !projectId) {
      stopStream()
      updateConnection({ status: 'idle' })
      setSessions([])
      hasSnapshotRef.current = false
      return
    }
    hasSnapshotRef.current = false
    if (stream) {
      void reload()
      void runStream(0)
      return () => {
        stopStream()
      }
    }
    void reload()
    return () => {
      stopStream()
    }
  }, [enabled, projectId, queryKey, reload, runStream, stopStream, stream, updateConnection])

  return {
    sessions,
    connection,
    reload,
  }
}
