import { useEffect, useRef, useState } from 'react'

import { authHeaders } from '@/lib/auth'
import type { AdminTask, AdminTaskEvent } from '@/lib/types/admin'

type ParsedEvent = {
  id?: string
  event: string
  data: string
}

function parseEventBlock(block: string): ParsedEvent | null {
  const lines = block.split(/\n/)
  let eventType = ''
  let eventId = ''
  const dataLines: string[] = []
  for (const line of lines) {
    if (!line || line.startsWith(':') || line.startsWith('retry:')) continue
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

export function useAdminTaskStream(taskId: string | null | undefined) {
  const [task, setTask] = useState<AdminTask | null>(null)
  const [events, setEvents] = useState<AdminTaskEvent[]>([])
  const [connectionState, setConnectionState] = useState<'idle' | 'connecting' | 'connected' | 'reconnecting' | 'error'>(
    taskId ? 'connecting' : 'idle'
  )
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const reconnectRef = useRef<number | null>(null)
  const lastEventIdRef = useRef<string | null>(null)
  const latestTaskRef = useRef<AdminTask | null>(null)

  useEffect(() => {
    latestTaskRef.current = task
  }, [task])

  useEffect(() => {
    return () => {
      abortRef.current?.abort()
      if (reconnectRef.current != null) {
        window.clearTimeout(reconnectRef.current)
      }
    }
  }, [])

  useEffect(() => {
    if (!taskId) {
      abortRef.current?.abort()
      if (reconnectRef.current != null) {
        window.clearTimeout(reconnectRef.current)
      }
      setTask(null)
      setEvents([])
      setConnectionState('idle')
      setError(null)
      lastEventIdRef.current = null
      return
    }

    let cancelled = false

    const fetchSnapshot = async (signal: AbortSignal) => {
      const response = await fetch(`/api/system/tasks/${encodeURIComponent(taskId)}`, {
        method: 'GET',
        headers: {
          Accept: 'application/json',
          ...authHeaders(),
        },
        signal,
      })
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const payload = (await response.json()) as { task?: AdminTask | null }
      if (payload?.task && typeof payload.task === 'object') {
        setTask(payload.task)
      }
    }

    const run = async (attempt = 0) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      setConnectionState(attempt > 0 ? 'reconnecting' : 'connecting')
      try {
        await fetchSnapshot(controller.signal)
        const headers: Record<string, string> = {
          Accept: 'text/event-stream',
          ...authHeaders(),
        }
        if (lastEventIdRef.current) {
          headers['Last-Event-ID'] = lastEventIdRef.current
        }
        const response = await fetch(`/api/system/tasks/${encodeURIComponent(taskId)}/stream`, {
          method: 'GET',
          headers,
          signal: controller.signal,
        })
        if (!response.ok || !response.body) {
          throw new Error(`HTTP ${response.status}`)
        }
        setConnectionState('connected')
        setError(null)
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
            if (!parsed) {
              boundaryIndex = buffer.indexOf('\n\n')
              continue
            }
            const payload = JSON.parse(parsed.data) as Record<string, unknown>
            if (parsed.event === 'task.snapshot') {
              const nextTask = payload.task
              if (nextTask && typeof nextTask === 'object' && !Array.isArray(nextTask)) {
                setTask(nextTask as AdminTask)
              }
            } else {
              const entry = payload as unknown as AdminTaskEvent
              setEvents((current) => [...current, entry].slice(-300))
              const nestedTask = payload.data && typeof payload.data === 'object' && !Array.isArray(payload.data)
                ? (payload.data as Record<string, unknown>).task
                : null
              if (nestedTask && typeof nestedTask === 'object' && !Array.isArray(nestedTask)) {
                setTask(nestedTask as AdminTask)
              }
            }
            boundaryIndex = buffer.indexOf('\n\n')
          }
        }
        if (cancelled || controller.signal.aborted) {
          return
        }
        const currentStatus = String(latestTaskRef.current?.status || '').trim().toLowerCase()
        if (!['completed', 'failed', 'cancelled'].includes(currentStatus)) {
          reconnectRef.current = window.setTimeout(() => {
            void run(attempt + 1)
          }, Math.min(1000 * 2 ** Math.min(attempt + 1, 4), 10000))
        }
      } catch (caught) {
        if (cancelled || controller.signal.aborted) return
        setConnectionState('error')
        setError(caught instanceof Error ? caught.message : String(caught))
        reconnectRef.current = window.setTimeout(() => {
          void run(attempt + 1)
        }, Math.min(1000 * 2 ** Math.min(attempt + 1, 4), 10000))
      }
    }

    void run(0)

    return () => {
      cancelled = true
      abortRef.current?.abort()
      if (reconnectRef.current != null) {
        window.clearTimeout(reconnectRef.current)
      }
    }
  }, [taskId])

  return {
    task,
    events,
    connectionState,
    error,
  }
}
