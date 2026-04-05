import { useCallback, useEffect, useRef, useState } from 'react'
import type { BashProgress } from '@/lib/types/bash'
import { getApiBaseUrl } from '@/lib/api/client'
import { refreshAccessToken } from '@/lib/api/auth'
import { handleUnauthorizedAuth, readRequestAuthContext, type RequestAuthMode } from '@/lib/auth'

export type BashStreamConnectionState = {
  status: 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed' | 'error'
  error?: string
}

export type BashStreamLogEvent = {
  bash_id: string
  seq: number
  stream: string
  line: string
  timestamp: string
}

export type BashStreamLine = {
  seq: number
  stream?: string | null
  line: string
  timestamp?: string | null
}

export type BashStreamSnapshotEvent = {
  bash_id: string
  tail_limit?: number | null
  latest_seq?: number | null
  lines: BashStreamLine[]
  progress?: BashProgress | null
}

export type BashStreamLogBatchEvent = {
  bash_id: string
  from_seq?: number | null
  to_seq?: number | null
  lines: BashStreamLine[]
}

export type BashStreamDoneEvent = {
  bash_id: string
  status: string
  exit_code?: number | null
  finished_at?: string
}

export type BashStreamGapEvent = {
  bash_id: string
  from_seq?: number | null
  to_seq?: number | null
  tail_limit?: number | null
}

export type BashStreamProgressEvent = BashProgress & {
  bash_id: string
}

type StreamOptions = {
  projectId?: string | null
  bashId?: string | null
  enabled?: boolean
  lastEventId?: number | null
  onSnapshot?: (event: BashStreamSnapshotEvent) => void
  onLogBatch?: (event: BashStreamLogBatchEvent) => void
  onLog?: (event: BashStreamLogEvent) => void
  onDone?: (event: BashStreamDoneEvent) => void
  onGap?: (event: BashStreamGapEvent) => void
  onProgress?: (event: BashStreamProgressEvent) => void
  onError?: (error: Error) => void
}

type ParsedEvent = {
  event: string
  data: string
  id?: string
}

const parseEventBlock = (block: string): ParsedEvent | null => {
  const lines = block.split(/\n/)
  let eventType = ''
  let eventId = ''
  const dataLines: string[] = []
  for (const line of lines) {
    if (!line || line.startsWith(':')) continue
    if (line.startsWith('event:')) {
      eventType = line.slice(6).trim()
      continue
    }
    if (line.startsWith('id:')) {
      eventId = line.slice(3).trim()
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }
  if (dataLines.length === 0) return null
  return { event: eventType || 'message', data: dataLines.join('\n'), id: eventId || undefined }
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

export function useBashLogStream({
  projectId,
  bashId,
  enabled = true,
  lastEventId,
  onSnapshot,
  onLogBatch,
  onLog,
  onDone,
  onProgress,
  onError,
  onGap,
}: StreamOptions) {
  const [connection, setConnection] = useState<BashStreamConnectionState>({ status: 'idle' })
  const abortRef = useRef<AbortController | null>(null)
  const reconnectRef = useRef<number | null>(null)
  const lastEventIdRef = useRef<number | null>(lastEventId ?? null)
  const onSnapshotRef = useRef(onSnapshot)
  const onLogBatchRef = useRef(onLogBatch)
  const onLogRef = useRef(onLog)
  const onDoneRef = useRef(onDone)
  const onGapRef = useRef(onGap)
  const onProgressRef = useRef(onProgress)
  const onErrorRef = useRef(onError)

  useEffect(() => {
    if (typeof lastEventId === 'number') {
      lastEventIdRef.current = lastEventId
      return
    }
    lastEventIdRef.current = null
  }, [bashId, lastEventId])

  useEffect(() => {
    onSnapshotRef.current = onSnapshot
  }, [onSnapshot])

  useEffect(() => {
    onLogBatchRef.current = onLogBatch
  }, [onLogBatch])

  useEffect(() => {
    onLogRef.current = onLog
  }, [onLog])

  useEffect(() => {
    onDoneRef.current = onDone
  }, [onDone])

  useEffect(() => {
    onGapRef.current = onGap
  }, [onGap])

  useEffect(() => {
    onProgressRef.current = onProgress
  }, [onProgress])

  useEffect(() => {
    onErrorRef.current = onError
  }, [onError])

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

  const runStream = useCallback(
    async (attempt = 0) => {
      if (!enabled || !projectId || !bashId) return
      stopStream()
      const controller = new AbortController()
      abortRef.current = controller
      setConnection({ status: attempt > 0 ? 'reconnecting' : 'connecting' })
      const { headers, authMode } = buildAuthContext()
      delete headers['Content-Type']
      if (lastEventIdRef.current != null) {
        headers['Last-Event-ID'] = String(lastEventIdRef.current)
      }

      try {
        const response = await fetch(
          `${getApiBaseUrl()}/api/quests/${projectId}/bash/sessions/${bashId}/stream`,
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
              setConnection({ status: 'reconnecting' })
              await runStream(attempt + 1)
              return
            }
          }
          setConnection({ status: 'error', error: 'unauthorized' })
          handleUnauthorized(authMode)
          return
        }

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }

        setConnection({ status: 'open' })
        const reader = response.body?.getReader()
        if (!reader) {
          throw new Error('No response body')
        }
        const decoder = new TextDecoder()
        let buffer = ''
        let sawDone = false

        const handleParsedEvent = (parsed: ParsedEvent) => {
          if (parsed.id) {
            const parsedId = Number(parsed.id)
            if (Number.isFinite(parsedId)) {
              lastEventIdRef.current = parsedId
            }
          }
          if (parsed.event === 'snapshot') {
            try {
              const data = JSON.parse(parsed.data) as BashStreamSnapshotEvent
              if (typeof data?.latest_seq === 'number') {
                lastEventIdRef.current = data.latest_seq
              }
              onSnapshotRef.current?.(data)
            } catch (error) {
              onErrorRef.current?.(
                error instanceof Error ? error : new Error('invalid_snapshot_event')
              )
            }
            return false
          }
          if (parsed.event === 'log_batch') {
            try {
              const data = JSON.parse(parsed.data) as BashStreamLogBatchEvent
              if (typeof data?.to_seq === 'number') {
                lastEventIdRef.current = data.to_seq
              }
              if (onLogBatchRef.current) {
                onLogBatchRef.current(data)
              } else if (onLogRef.current) {
                data.lines?.forEach((line) => {
                  if (typeof line?.seq !== 'number') return
                  onLogRef.current?.({
                    bash_id: data.bash_id,
                    seq: line.seq,
                    stream: line.stream ?? 'stdout',
                    line: line.line ?? '',
                    timestamp: line.timestamp ?? '',
                  })
                })
              }
            } catch (error) {
              onErrorRef.current?.(
                error instanceof Error ? error : new Error('invalid_log_batch_event')
              )
            }
            return false
          }
          if (parsed.event === 'log') {
            try {
              const data = JSON.parse(parsed.data) as BashStreamLogEvent
              if (typeof data?.seq === 'number') {
                lastEventIdRef.current = data.seq
              }
              if (onLogBatchRef.current) {
                onLogBatchRef.current({
                  bash_id: data.bash_id,
                  from_seq: data.seq,
                  to_seq: data.seq,
                  lines: [
                    {
                      seq: data.seq,
                      stream: data.stream,
                      line: data.line,
                      timestamp: data.timestamp,
                    },
                  ],
                })
              } else {
                onLogRef.current?.(data)
              }
            } catch (error) {
              onErrorRef.current?.(
                error instanceof Error ? error : new Error('invalid_log_event')
              )
            }
            return false
          }
          if (parsed.event === 'gap') {
            try {
              const data = JSON.parse(parsed.data) as BashStreamGapEvent
              onGapRef.current?.(data)
            } catch (error) {
              onErrorRef.current?.(
                error instanceof Error ? error : new Error('invalid_gap_event')
              )
            }
            return false
          }
          if (parsed.event === 'progress') {
            try {
              const data = JSON.parse(parsed.data) as BashStreamProgressEvent
              onProgressRef.current?.(data)
            } catch (error) {
              onErrorRef.current?.(
                error instanceof Error ? error : new Error('invalid_progress_event')
              )
            }
            return false
          }
          if (parsed.event === 'done') {
            try {
              const data = JSON.parse(parsed.data) as BashStreamDoneEvent
              onDoneRef.current?.(data)
            } catch (error) {
              onErrorRef.current?.(
                error instanceof Error ? error : new Error('invalid_done_event')
              )
            }
            sawDone = true
            return true
          }
          return false
        }

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
            if (parsed && handleParsedEvent(parsed)) {
              setConnection({ status: 'closed' })
              stopStream()
              return
            }
            boundaryIndex = buffer.indexOf('\n\n')
          }
        }

        const trailing = buffer.replace(/\r\n/g, '\n').trim()
        if (trailing) {
          const parsed = parseEventBlock(trailing)
          if (parsed && handleParsedEvent(parsed)) {
            setConnection({ status: 'closed' })
            stopStream()
            return
          }
        }

        if (!controller.signal.aborted && !sawDone) {
          const delay = Math.min(2000 * (attempt + 1), 10000)
          setConnection({ status: 'reconnecting' })
          reconnectRef.current = window.setTimeout(() => {
            void runStream(attempt + 1)
          }, delay)
          return
        }

        setConnection({ status: 'closed' })
      } catch (error) {
        if (controller.signal.aborted) {
          setConnection({ status: 'closed' })
          return
        }
        const err = error instanceof Error ? error : new Error('stream_failed')
        onErrorRef.current?.(err)
        setConnection({ status: 'error', error: err.message })
        const delay = Math.min(2000 * (attempt + 1), 10000)
        reconnectRef.current = window.setTimeout(() => {
          void runStream(attempt + 1)
        }, delay)
      }
    },
    [bashId, enabled, projectId, stopStream]
  )

  useEffect(() => {
    if (!enabled || !projectId || !bashId) {
      stopStream()
      setConnection({ status: 'idle' })
      return
    }
    void runStream(0)
    return () => {
      stopStream()
    }
  }, [bashId, enabled, projectId, runStream, stopStream])

  return connection
}
