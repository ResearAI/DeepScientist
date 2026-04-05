import { redirectToLanding } from '@/lib/navigation'

type RuntimeAuthConfig = {
  enabled: boolean
  tokenQueryParam: string
  storageKey: string
}

export type RequestAuthMode = 'browser' | 'user' | 'none'

const FALLBACK_STORAGE_KEY = 'ds_local_auth_token'
const LEGACY_STORAGE_KEY = 'ds_access_token'
const FALLBACK_QUERY_PARAM = 'token'

function storageKeys(config: RuntimeAuthConfig) {
  return [config.storageKey || FALLBACK_STORAGE_KEY, LEGACY_STORAGE_KEY]
}

function toRecord(headers?: HeadersInit): Record<string, string> {
  if (!headers) return {}
  if (headers instanceof Headers) {
    return Object.fromEntries(headers.entries())
  }
  if (Array.isArray(headers)) {
    return Object.fromEntries(headers)
  }
  return { ...headers }
}

export function runtimeAuthConfig(): RuntimeAuthConfig {
  if (typeof window === 'undefined') {
    return {
      enabled: false,
      tokenQueryParam: FALLBACK_QUERY_PARAM,
      storageKey: FALLBACK_STORAGE_KEY,
    }
  }
  const auth = window.__DEEPSCIENTIST_RUNTIME__?.auth
  return {
    enabled: auth?.enabled === true,
    tokenQueryParam:
      typeof auth?.tokenQueryParam === 'string' && auth.tokenQueryParam.trim()
        ? auth.tokenQueryParam.trim()
        : FALLBACK_QUERY_PARAM,
    storageKey:
      typeof auth?.storageKey === 'string' && auth.storageKey.trim()
        ? auth.storageKey.trim()
        : FALLBACK_STORAGE_KEY,
  }
}

export function readStoredBrowserAuthToken(): string | null {
  if (typeof window === 'undefined') return null
  const config = runtimeAuthConfig()
  if (!config.enabled) return null
  for (const key of storageKeys(config)) {
    const token = window.localStorage.getItem(key)?.trim()
    if (token) return token
  }
  return null
}

export function readLegacyUserAccessToken(): string | null {
  if (typeof window === 'undefined') return null
  const token = window.localStorage.getItem(LEGACY_STORAGE_KEY)?.trim()
  return token || null
}

export function readRequestAuthContext(): { token: string | null; mode: RequestAuthMode } {
  const browserToken = readStoredBrowserAuthToken()
  if (browserToken) {
    return { token: browserToken, mode: 'browser' }
  }
  const userToken = readLegacyUserAccessToken()
  if (userToken) {
    return { token: userToken, mode: 'user' }
  }
  return { token: null, mode: 'none' }
}

export function storeBrowserAuthToken(token: string | null | undefined) {
  if (typeof window === 'undefined') return
  const config = runtimeAuthConfig()
  const normalized = typeof token === 'string' ? token.trim() : ''
  for (const key of storageKeys(config)) {
    if (normalized) {
      window.localStorage.setItem(key, normalized)
    } else {
      window.localStorage.removeItem(key)
    }
  }
}

export function authHeaders(headers?: HeadersInit): Record<string, string> {
  const { token } = readRequestAuthContext()
  if (!token) {
    return toRecord(headers)
  }
  return {
    ...toRecord(headers),
    Authorization: `Bearer ${token}`,
  }
}

export function readUrlBrowserAuthToken(url?: string): string | null {
  if (typeof window === 'undefined') return null
  const config = runtimeAuthConfig()
  const target = new URL(url || window.location.href, window.location.origin)
  const token = target.searchParams.get(config.tokenQueryParam)?.trim()
  return token || null
}

export function clearBrowserAuthTokenFromLocation() {
  if (typeof window === 'undefined') return
  const config = runtimeAuthConfig()
  const target = new URL(window.location.href)
  if (!target.searchParams.has(config.tokenQueryParam)) {
    return
  }
  target.searchParams.delete(config.tokenQueryParam)
  const suffix = `${target.pathname}${target.search}${target.hash}`
  window.history.replaceState(window.history.state, '', suffix)
}

export async function fetchBrowserAuthToken(): Promise<string | null> {
  const response = await fetch('/api/auth/token', {
    headers: authHeaders(),
    cache: 'no-store',
  })
  if (!response.ok) {
    return null
  }
  const payload = (await response.json()) as { token?: string | null }
  const token = typeof payload.token === 'string' ? payload.token.trim() : ''
  return token || null
}

export function clearRequestAuth(mode: RequestAuthMode) {
  if (typeof window === 'undefined') return
  if (mode === 'browser') {
    storeBrowserAuthToken(null)
    return
  }
  if (mode === 'user') {
    window.localStorage.removeItem(LEGACY_STORAGE_KEY)
  }
}

export function handleUnauthorizedAuth(mode: RequestAuthMode, error: string = 'session_expired') {
  if (mode === 'none') return
  clearRequestAuth(mode)
  redirectToLanding(error)
}
