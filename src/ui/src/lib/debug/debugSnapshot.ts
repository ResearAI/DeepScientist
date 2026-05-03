export const WEB_DEBUG_STORAGE_KEY = 'deepscientist.debug'
export const WEB_DEBUG_LOG_STORAGE_KEY = 'deepscientist.debug.log'

export const DEBUG_REDACTION_PATTERNS = [
  'token',
  'secret',
  'password',
  'api_key',
  'auth_ak',
  'credential',
  'app_secret',
] as const

const SECRET_KEY_PATTERN = /(token|secret|password|api[_-]?key|auth[_-]?ak|credential|app[_-]?secret)/i
const MAX_REDACTION_DEPTH = 6

export type WebDebugRouteSnapshot = {
  pathname: string
  search: string
  hash: string
}

export type WebDebugInputSnapshot = {
  source: string
  raw: string | null
  parsed: string | null
  preview: string | null
  redacted: boolean
  redaction_reason: string | null
  length: number
}

export type WebDebugScreenSnapshot = {
  main: string
  composer: string
  selected: string | null
  input_visible: boolean
  input_redacted: boolean
  debug_strip_visible: boolean
}

export type WebDebugApiEvent = {
  id: number
  method: string
  path: string
  status: number | null
  ok: boolean
  duration_ms: number
  error: string | null
  started_at: string
}

export type WebDebugActionSnapshot = {
  enabled: boolean
  reason: string | null
}

export type WebDebugRedactionSnapshot = {
  applied: boolean
  fields: string[]
  policy: string[]
}

export type WebDebugSnapshot = {
  version: 1
  generated_at: string
  surface: string
  web_analog: string
  route: WebDebugRouteSnapshot
  input: WebDebugInputSnapshot
  screen: WebDebugScreenSnapshot
  status_line: string | null
  connection_state: string
  selected: Record<string, string | null>
  counts: Record<string, number>
  flags: Record<string, boolean>
  messages: Record<string, string | null>
  actions: Record<string, WebDebugActionSnapshot>
  redaction: WebDebugRedactionSnapshot
  api: {
    recent: WebDebugApiEvent[]
    last_error: string | null
  }
}

export type WebDebugSnapshotPatch = Partial<Omit<WebDebugSnapshot, 'version' | 'generated_at' | 'route' | 'api'>> & {
  surface: string
  route?: Partial<WebDebugRouteSnapshot>
  api?: Partial<WebDebugSnapshot['api']>
}

export function isSecretLikeDebugKey(key: string): boolean {
  return SECRET_KEY_PATTERN.test(key)
}

export function isWebDebugEnabledFromSearch(search: string, storedValue?: string | null): boolean {
  const params = new URLSearchParams(search || '')
  const queryValue = params.get('debug')
  if (queryValue !== null) {
    const normalized = queryValue.trim().toLowerCase()
    return normalized === '' || normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on'
  }
  const normalizedStored = String(storedValue || '').trim().toLowerCase()
  return normalizedStored === '1' || normalizedStored === 'true' || normalizedStored === 'yes' || normalizedStored === 'on'
}

export function shouldDisableWebDebugFromSearch(search: string): boolean {
  const params = new URLSearchParams(search || '')
  const queryValue = params.get('debug')
  if (queryValue === null) return false
  const normalized = queryValue.trim().toLowerCase()
  return normalized === '0' || normalized === 'false' || normalized === 'no' || normalized === 'off'
}

export function shouldPersistWebDebugFromSearch(search: string): boolean {
  const params = new URLSearchParams(search || '')
  const queryValue = params.get('debug')
  if (queryValue === null) return false
  const normalized = queryValue.trim().toLowerCase()
  return normalized === '' || normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on'
}

export function isWebDebugLogEnabled(): boolean {
  if (typeof window === 'undefined') return false
  try {
    const value = window.localStorage.getItem(WEB_DEBUG_LOG_STORAGE_KEY)
    const normalized = String(value || '').trim().toLowerCase()
    return normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on'
  } catch {
    return false
  }
}

export function redactDebugValue(value: unknown, path: string[] = [], redactedFields: string[] = [], depth = 0): unknown {
  const key = path[path.length - 1] || ''
  if (key && isSecretLikeDebugKey(key)) {
    redactedFields.push(path.join('.') || key)
    if (typeof value === 'string') {
      return `[redacted: ${key}; ${value.length} chars]`
    }
    return `[redacted: ${key}]`
  }
  if (value === null || typeof value !== 'object') {
    return value
  }
  if (depth >= MAX_REDACTION_DEPTH) {
    return '[redacted: max debug depth]'
  }
  if (Array.isArray(value)) {
    return value.map((item, index) => redactDebugValue(item, [...path, String(index)], redactedFields, depth + 1))
  }
  const output: Record<string, unknown> = {}
  for (const [entryKey, entryValue] of Object.entries(value as Record<string, unknown>)) {
    output[entryKey] = redactDebugValue(entryValue, [...path, entryKey], redactedFields, depth + 1)
  }
  return output
}

export function emptyWebDebugInput(source = 'none'): WebDebugInputSnapshot {
  return {
    source,
    raw: null,
    parsed: null,
    preview: null,
    redacted: false,
    redaction_reason: null,
    length: 0,
  }
}

export function buildWebDebugSnapshot(args: {
  patch: WebDebugSnapshotPatch | null
  route: WebDebugRouteSnapshot
  apiEvents: WebDebugApiEvent[]
}): WebDebugSnapshot {
  const patch = args.patch
  const route = {
    pathname: patch?.route?.pathname ?? args.route.pathname,
    search: patch?.route?.search ?? args.route.search,
    hash: patch?.route?.hash ?? args.route.hash,
  }
  const apiRecent = patch?.api?.recent ?? args.apiEvents
  const lastApiError =
    patch?.api?.last_error ??
    [...apiRecent].reverse().find((event) => event.error || !event.ok)?.error ??
    null

  return {
    version: 1,
    generated_at: new Date().toISOString(),
    surface: patch?.surface ?? 'app',
    web_analog: patch?.web_analog ?? route.pathname,
    route,
    input: patch?.input ?? emptyWebDebugInput(),
    screen:
      patch?.screen ??
      {
        main: 'App',
        composer: 'none',
        selected: null,
        input_visible: false,
        input_redacted: false,
        debug_strip_visible: true,
      },
    status_line: patch?.status_line ?? null,
    connection_state: patch?.connection_state ?? 'unknown',
    selected: patch?.selected ?? {},
    counts: patch?.counts ?? {},
    flags: patch?.flags ?? {},
    messages: patch?.messages ?? {},
    actions: patch?.actions ?? {},
    redaction:
      patch?.redaction ??
      {
        applied: false,
        fields: [],
        policy: [...DEBUG_REDACTION_PATTERNS],
      },
    api: {
      recent: apiRecent,
      last_error: lastApiError,
    },
  }
}

export function buildDebugSignature(value: unknown): string {
  return JSON.stringify(value, (_key, entryValue) => {
    if (_key === 'generated_at') return undefined
    return entryValue
  })
}

export function webDebugSnapshotToJson(snapshot: WebDebugSnapshot): string {
  return JSON.stringify(snapshot, null, 2)
}
