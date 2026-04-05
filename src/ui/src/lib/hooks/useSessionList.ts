import { useCallback, useEffect, useRef, useState } from 'react'
import { getApiBaseUrl } from '@/lib/api/client'
import { refreshAccessToken } from '@/lib/api/auth'
import { handleUnauthorizedAuth, readRequestAuthContext, type RequestAuthMode } from '@/lib/auth'
import { listSessionSummaries, type SessionListItem } from '@/lib/api/sessions'

export type SessionStreamStatus =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'closed'
  | 'error'

export interface SessionStreamState {
  status: SessionStreamStatus
  error?: string
}

const normalizeTextValue = (value?: string | null) => (typeof value === 'string' ? value.trim() : '')

const mergeSessionItem = (existing: SessionListItem, incoming: SessionListItem): SessionListItem => {
  const incomingTitle = normalizeTextValue(incoming.title)
  const incomingLatest = normalizeTextValue(incoming.latest_message)
  return {
    ...existing,
    ...incoming,
    title: incomingTitle ? incoming.title : existing.title ?? incoming.title ?? null,
    latest_message: incomingLatest ? incoming.latest_message : existing.latest_message ?? incoming.latest_message ?? null,
    latest_message_at: incoming.latest_message_at ?? existing.latest_message_at ?? null,
    updated_at: incoming.updated_at ?? existing.updated_at ?? null,
    status: incoming.status ?? existing.status ?? null,
    is_shared: incoming.is_shared ?? existing.is_shared ?? false,
    is_active: incoming.is_active ?? existing.is_active ?? false,
  }
}

const mergeSessionLists = (previous: SessionListItem[], incoming: SessionListItem[]) => {
  if (incoming.length === 0) return []
  const incomingMap = new Map(incoming.map((item) => [item.session_id, item]))
  const merged: SessionListItem[] = []

  previous.forEach((existing) => {
    const next = incomingMap.get(existing.session_id)
    if (!next) return
    merged.push(mergeSessionItem(existing, next))
    incomingMap.delete(existing.session_id)
  })

  incoming.forEach((item) => {
    if (!incomingMap.has(item.session_id)) return
    merged.push(item)
    incomingMap.delete(item.session_id)
  })

  return merged
}

const isCopilotDebugEnabled = () => {
  if (typeof window === 'undefined') return false
  return process.env.NODE_ENV !== 'production' || window.localStorage.getItem('ds_debug_copilot') === '1'
}

export function useSessionList(options: {
  projectId?: string | null
  enabled?: boolean
  stream?: boolean
}) {
  const { projectId, enabled = true, stream = false } = options
  const [sessions, setSessions] = useState<SessionListItem[]>([])
  const [connection, setConnection] = useState<SessionStreamState>({ status: 'idle' })
  const abortRef = useRef<AbortController | null>(null)

  const updateConnection = useCallback((next: SessionStreamState) => {
    setConnection(next)
  }, [])

  const buildAuthContext = useCallback(() => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    const { token, mode } = readRequestAuthContext()
    if (token) {
      headers.Authorization = `Bearer ${token}`
    }
    return { headers, authMode: mode }
  }, [])

  const handleUnauthorized = useCallback((authMode: RequestAuthMode) => {
    handleUnauthorizedAuth(authMode, 'session_expired')
  }, [])

  const parseEventBlock = (block: string) => {
    const lines = block.split(/\n/)
    let eventType = ''
    const dataLines: string[] = []

    for (const line of lines) {
      if (!line) continue
      if (line.startsWith('event:')) {
        eventType = line.slice(6).trim()
        continue
      }
      if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trimStart())
      }
    }

    if (dataLines.length === 0) return null
    return {
      event: eventType || 'message',
      data: dataLines.join('\n'),
    }
  }

  const reload = useCallback(async () => {
    if (!enabled) {
      if (isCopilotDebugEnabled()) {
        console.info('[Sessions] reload skipped (disabled)')
      }
      setSessions([])
      return
    }
    try {
      const normalizedProjectId =
        typeof projectId === 'string' && projectId.trim().length > 0 ? projectId : undefined
      if (isCopilotDebugEnabled()) {
        console.info('[Sessions] reload start', { projectId: normalizedProjectId ?? null })
      }
      const response = await listSessionSummaries(normalizedProjectId)
      if (isCopilotDebugEnabled()) {
        console.info('[Sessions] reload success', { count: response.sessions?.length ?? 0 })
      }
      setSessions((current) => mergeSessionLists(current, response.sessions ?? []))
    } catch (error) {
      if (isCopilotDebugEnabled()) {
        console.warn('[Sessions] reload failed', error)
      }
      updateConnection({ status: 'error', error: 'fetch_failed' })
    }
  }, [enabled, projectId, updateConnection])

  const runStream = useCallback(
    async (attempt = 0) => {
      if (!enabled) return

      if (abortRef.current) {
        abortRef.current.abort()
        abortRef.current = null
      }

      const controller = new AbortController()
      abortRef.current = controller
      updateConnection({ status: attempt > 0 ? 'reconnecting' : 'connecting' })

      const { headers, authMode } = buildAuthContext()
      delete headers['Content-Type']

      const query = new URLSearchParams()
      const normalizedProjectId =
        typeof projectId === 'string' && projectId.trim().length > 0 ? projectId : undefined
      if (normalizedProjectId) query.set('project_id', normalizedProjectId)

      try {
        const response = await fetch(
          `${getApiBaseUrl()}/api/v1/sessions/stream?${query.toString()}`,
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
            if (parsed && parsed.event === 'sessions') {
              try {
                const data = JSON.parse(parsed.data) as { sessions?: SessionListItem[] }
                if (Array.isArray(data.sessions)) {
                  setSessions((current) => mergeSessionLists(current, data.sessions ?? []))
                }
              } catch (error) {
                console.warn('[Sessions SSE] Failed to parse event data', error)
              }
            }
            boundaryIndex = buffer.indexOf('\n\n')
          }
        }

        const trailing = buffer.replace(/\r\n/g, '\n').trim()
        if (trailing) {
          const parsed = parseEventBlock(trailing)
          if (parsed && parsed.event === 'sessions') {
            try {
              const data = JSON.parse(parsed.data) as { sessions?: SessionListItem[] }
              if (Array.isArray(data.sessions)) {
                setSessions((current) => mergeSessionLists(current, data.sessions ?? []))
              }
            } catch (error) {
              console.warn('[Sessions SSE] Failed to parse trailing event data', error)
            }
          }
        }

        updateConnection({ status: 'closed' })
      } catch (error) {
        if (controller.signal.aborted) {
          updateConnection({ status: 'closed' })
          return
        }
        updateConnection({
          status: 'error',
          error: error instanceof Error ? error.message : 'stream_failed',
        })
        if (attempt < 1) {
          void runStream(attempt + 1)
        }
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null
        }
      }
    },
    [buildAuthContext, enabled, handleUnauthorized, projectId, updateConnection]
  )

  useEffect(() => {
    if (!enabled) {
      updateConnection({ status: 'idle' })
      setSessions([])
      return
    }
    void reload()
    if (stream) {
      void runStream(0)
    }
    return () => {
      if (abortRef.current) {
        abortRef.current.abort()
        abortRef.current = null
      }
    }
  }, [enabled, projectId, reload, runStream, stream, updateConnection])

  return {
    sessions,
    setSessions,
    reload,
    connection,
  }
}
