import { client as questClient } from '@/lib/api'

type RuntimeFlags = {
  surface?: string
  version?: string
  homePath?: string
  supports?: {
    productApis?: boolean
    socketIo?: boolean
    notifications?: boolean
    points?: boolean
    arxiv?: boolean
    cliFrontend?: boolean
  }
}

const questProjectProbeCache = new Map<string, Promise<boolean>>()
let questApiProbe: Promise<boolean> | null = null

function readInjectedRuntime(): RuntimeFlags | null {
  if (typeof window === 'undefined') return null
  const runtime = window.__DEEPSCIENTIST_RUNTIME__
  if (!runtime || typeof runtime !== 'object') return null
  return runtime
}

function fallbackQuestSurfaceGuess(): boolean {
  if (typeof window === 'undefined') return false
  const { pathname, port } = window.location
  if (port === '20999') return true
  const normalizedPath =
    pathname === '/ui'
      ? '/'
      : pathname.startsWith('/ui/')
        ? pathname.slice('/ui'.length)
        : pathname
  if (normalizedPath.startsWith('/projects/')) return true
  if (normalizedPath === '/') return true
  if (normalizedPath.startsWith('/docs') || normalizedPath.startsWith('/settings')) return true
  return false
}

export function isQuestRuntimeSurface(): boolean {
  const injected = readInjectedRuntime()
  if (injected?.surface === 'quest') {
    return true
  }
  return fallbackQuestSurfaceGuess()
}

export function supportsProductApis(): boolean {
  const injected = readInjectedRuntime()
  if (typeof injected?.supports?.productApis === 'boolean') {
    return injected.supports.productApis
  }
  return !isQuestRuntimeSurface()
}

export function supportsSocketIo(): boolean {
  const injected = readInjectedRuntime()
  if (typeof injected?.supports?.socketIo === 'boolean') {
    return injected.supports.socketIo
  }
  return !isQuestRuntimeSurface()
}

export function supportsPoints(): boolean {
  const injected = readInjectedRuntime()
  if (typeof injected?.supports?.points === 'boolean') {
    return injected.supports.points
  }
  return supportsProductApis()
}

export function supportsNotifications(): boolean {
  const injected = readInjectedRuntime()
  if (typeof injected?.supports?.notifications === 'boolean') {
    return injected.supports.notifications
  }
  return supportsProductApis()
}

export function supportsArxiv(): boolean {
  const injected = readInjectedRuntime()
  if (typeof injected?.supports?.arxiv === 'boolean') {
    return injected.supports.arxiv
  }
  return supportsProductApis()
}

export function supportsCliFrontend(): boolean {
  const injected = readInjectedRuntime()
  if (typeof injected?.supports?.cliFrontend === 'boolean') {
    return injected.supports.cliFrontend
  }
  return supportsProductApis()
}

export function runtimeVersion(): string | null {
  const injected = readInjectedRuntime()
  const version = typeof injected?.version === 'string' ? injected.version.trim() : ''
  return version || null
}

export function runtimeHomePath(): string | null {
  const injected = readInjectedRuntime()
  const homePath = typeof injected?.homePath === 'string' ? injected.homePath.trim() : ''
  return homePath || null
}

export async function hasQuestApi(): Promise<boolean> {
  if (!questApiProbe) {
    questApiProbe = questClient
      .quests()
      .then(() => true)
      .catch(() => false)
  }
  return questApiProbe
}

export async function shouldUseQuestProject(projectId: string): Promise<boolean> {
  const cachedProbe = questProjectProbeCache.get(projectId)
  if (cachedProbe) {
    return cachedProbe
  }
  const probe = questClient
    .session(projectId)
    .then(() => true)
    .catch(() => false)
  questProjectProbeCache.set(projectId, probe)
  return probe
}
