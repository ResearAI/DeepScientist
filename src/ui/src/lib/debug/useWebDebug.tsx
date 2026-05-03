import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

import {
  WEB_DEBUG_STORAGE_KEY,
  buildDebugSignature,
  buildWebDebugSnapshot,
  isWebDebugLogEnabled,
  isWebDebugEnabledFromSearch,
  shouldDisableWebDebugFromSearch,
  shouldPersistWebDebugFromSearch,
  webDebugSnapshotToJson,
  type WebDebugApiEvent,
  type WebDebugRouteSnapshot,
  type WebDebugSnapshot,
  type WebDebugSnapshotPatch,
} from '@/lib/debug/debugSnapshot'

type WebDebugContextValue = {
  enabled: boolean
  snapshot: WebDebugSnapshot
  logEnabled: boolean
  logLines: string[]
  clearLog: () => void
  publishSnapshot: (snapshot: WebDebugSnapshotPatch | null) => void
}

const WebDebugContext = createContext<WebDebugContextValue | null>(null)

function readStoredDebugPreference(): string | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(WEB_DEBUG_STORAGE_KEY)
  } catch {
    return null
  }
}

function writeStoredDebugPreference(enabled: boolean) {
  if (typeof window === 'undefined') return
  try {
    if (enabled) {
      window.localStorage.setItem(WEB_DEBUG_STORAGE_KEY, '1')
    } else {
      window.localStorage.removeItem(WEB_DEBUG_STORAGE_KEY)
    }
  } catch {
    return
  }
}

function requestToPath(input: RequestInfo | URL): string {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
  try {
    const url = new URL(raw, window.location.origin)
    return `${url.pathname}${url.search}`
  } catch {
    return raw
  }
}

function requestToMethod(input: RequestInfo | URL, init?: RequestInit): string {
  if (init?.method) return init.method.toUpperCase()
  if (typeof input !== 'string' && !(input instanceof URL) && input.method) return input.method.toUpperCase()
  return 'GET'
}

export function WebDebugProvider({ children }: { children: ReactNode }) {
  const location = useLocation()
  const [enabled, setEnabled] = useState(() => isWebDebugEnabledFromSearch(location.search, readStoredDebugPreference()))
  const [publishedSnapshot, setPublishedSnapshot] = useState<WebDebugSnapshotPatch | null>(null)
  const [apiEvents, setApiEvents] = useState<WebDebugApiEvent[]>([])
  const [logLines, setLogLines] = useState<string[]>([])
  const [logEnabled, setLogEnabled] = useState(() => isWebDebugLogEnabled())
  const apiEventIdRef = useRef(0)
  const lastLoggedSignatureRef = useRef('')

  useEffect(() => {
    const nextEnabled = isWebDebugEnabledFromSearch(location.search, readStoredDebugPreference())
    setEnabled(nextEnabled)
    setLogEnabled(isWebDebugLogEnabled())
    if (shouldPersistWebDebugFromSearch(location.search)) {
      writeStoredDebugPreference(true)
    } else if (shouldDisableWebDebugFromSearch(location.search)) {
      writeStoredDebugPreference(false)
    }
  }, [location.search])

  useEffect(() => {
    if (!enabled || typeof window === 'undefined') {
      return
    }
    const originalFetch = window.fetch
    const debugFetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const startedAt = new Date().toISOString()
      const start = performance.now()
      const method = requestToMethod(input, init)
      const path = requestToPath(input)
      try {
        const response = await originalFetch(input, init)
        const event: WebDebugApiEvent = {
          id: ++apiEventIdRef.current,
          method,
          path,
          status: response.status,
          ok: response.ok,
          duration_ms: Math.round(performance.now() - start),
          error: null,
          started_at: startedAt,
        }
        setApiEvents((items) => [event, ...items].slice(0, 12))
        return response
      } catch (error) {
        const event: WebDebugApiEvent = {
          id: ++apiEventIdRef.current,
          method,
          path,
          status: null,
          ok: false,
          duration_ms: Math.round(performance.now() - start),
          error: error instanceof Error ? error.message : String(error || 'fetch failed'),
          started_at: startedAt,
        }
        setApiEvents((items) => [event, ...items].slice(0, 12))
        throw error
      }
    }
    window.fetch = debugFetch
    return () => {
      if (window.fetch !== debugFetch) {
        return
      }
      window.fetch = originalFetch
    }
  }, [enabled])

  const route = useMemo<WebDebugRouteSnapshot>(
    () => ({
      pathname: location.pathname,
      search: location.search,
      hash: location.hash,
    }),
    [location.hash, location.pathname, location.search]
  )

  const snapshot = useMemo(
    () =>
      buildWebDebugSnapshot({
        patch: publishedSnapshot,
        route,
        apiEvents,
      }),
    [apiEvents, publishedSnapshot, route]
  )

  const publishSnapshot = useCallback((nextSnapshot: WebDebugSnapshotPatch | null) => {
    setPublishedSnapshot(nextSnapshot)
  }, [])

  const clearLog = useCallback(() => {
    lastLoggedSignatureRef.current = ''
    setLogLines([])
  }, [])

  useEffect(() => {
    if (!enabled || !logEnabled) {
      return
    }
    const signature = buildDebugSignature(snapshot)
    if (signature === lastLoggedSignatureRef.current) {
      return
    }
    lastLoggedSignatureRef.current = signature
    setLogLines((items) => [...items.slice(-99), webDebugSnapshotToJson(snapshot)])
  }, [enabled, logEnabled, snapshot])

  const value = useMemo<WebDebugContextValue>(
    () => ({
      enabled,
      snapshot,
      logEnabled,
      logLines,
      clearLog,
      publishSnapshot,
    }),
    [clearLog, enabled, logEnabled, logLines, publishSnapshot, snapshot]
  )

  return <WebDebugContext.Provider value={value}>{children}</WebDebugContext.Provider>
}

export function useWebDebug() {
  const value = useContext(WebDebugContext)
  if (value) return value
  return {
    enabled: false,
    snapshot: buildWebDebugSnapshot({
      patch: null,
      route: { pathname: '', search: '', hash: '' },
      apiEvents: [],
    }),
    logEnabled: false,
    logLines: [],
    clearLog: () => undefined,
    publishSnapshot: () => undefined,
  } satisfies WebDebugContextValue
}

export function usePublishWebDebugSnapshot(snapshot: WebDebugSnapshotPatch | null) {
  const { enabled, publishSnapshot } = useWebDebug()
  const lastSignatureRef = useRef('')

  useEffect(() => {
    if (!enabled || !snapshot) {
      if (lastSignatureRef.current) {
        publishSnapshot(null)
        lastSignatureRef.current = ''
      }
      return
    }
    const signature = buildDebugSignature(snapshot)
    if (signature === lastSignatureRef.current) {
      return
    }
    lastSignatureRef.current = signature
    publishSnapshot(snapshot)
  }, [enabled, publishSnapshot, snapshot])
}
