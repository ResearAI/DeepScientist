export type AdminFrontendLogLevel = 'log' | 'info' | 'warn' | 'error' | 'pageerror' | 'rejection'

export type AdminFrontendLogEntry = {
  id: string
  level: AdminFrontendLogLevel
  message: string
  source: 'console' | 'window'
  created_at: string
}

const STORAGE_KEY = 'ds:admin:frontend-logs'
const MAX_ENTRIES = 200
let installed = false
let memoryLogs: AdminFrontendLogEntry[] = []

function nowIso() {
  return new Date().toISOString()
}

function nextId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

function normalizeMessage(args: unknown[]) {
  return args
    .map((item) => {
      if (typeof item === 'string') return item
      if (item instanceof Error) return item.stack || item.message
      try {
        return JSON.stringify(item)
      } catch {
        return String(item)
      }
    })
    .join(' ')
    .trim()
}

function persist() {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(memoryLogs))
  } catch {
    return
  }
}

function loadPersisted() {
  if (typeof window === 'undefined') return
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return
    memoryLogs = parsed.filter(Boolean).slice(-MAX_ENTRIES)
  } catch {
    return
  }
}

function pushEntry(entry: Omit<AdminFrontendLogEntry, 'id' | 'created_at'>) {
  memoryLogs = [
    ...memoryLogs,
    {
      id: nextId(),
      created_at: nowIso(),
      ...entry,
    },
  ].slice(-MAX_ENTRIES)
  persist()
}

export function listAdminFrontendLogs() {
  return [...memoryLogs].reverse()
}

export function clearAdminFrontendLogs() {
  memoryLogs = []
  persist()
}

export function installAdminFrontendLogCapture() {
  if (installed || typeof window === 'undefined') return
  installed = true
  loadPersisted()

  const consoleLevels: Array<Extract<AdminFrontendLogLevel, 'log' | 'info' | 'warn' | 'error'>> = ['log', 'info', 'warn', 'error']
  for (const level of consoleLevels) {
    const original = console[level]
    console[level] = (...args: unknown[]) => {
      pushEntry({
        level,
        source: 'console',
        message: normalizeMessage(args),
      })
      original(...args)
    }
  }

  window.addEventListener('error', (event) => {
    pushEntry({
      level: 'pageerror',
      source: 'window',
      message: [event.message, event.filename ? `@ ${event.filename}:${event.lineno}:${event.colno}` : '']
        .filter(Boolean)
        .join(' '),
    })
  })

  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason
    pushEntry({
      level: 'rejection',
      source: 'window',
      message: reason instanceof Error ? reason.stack || reason.message : String(reason),
    })
  })
}
