export type StudioFileLinkTarget =
  | {
      kind: 'file_id'
      fileId: string
    }
  | {
      kind: 'file_path'
      filePath: string
    }

const INTERNAL_FILE_PREFIXES = ['dsfile://', 'ds://file/']
const FILE_API_PATH_RE = /(?:^|\/)api\/v1\/files\/([^/?#]+)(?:\/content)?\/?$/i
const ABSOLUTE_URL_RE = /^[a-zA-Z][a-zA-Z\d+.-]*:/

function safeDecode(value: string): string {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

function stripQueryAndHash(value: string): string {
  return value.split('#', 1)[0]?.split('?', 1)[0] ?? ''
}

function normalizeProjectRelativePath(value: string): string {
  const segments = safeDecode(value)
    .replace(/\\/g, '/')
    .split('/')
  const normalized: string[] = []

  for (const segment of segments) {
    if (!segment || segment === '.') continue
    if (segment === '..') {
      if (normalized.length > 0) {
        normalized.pop()
      }
      continue
    }
    normalized.push(segment)
  }

  return normalized.join('/')
}

function extractFileIdFromApiPath(pathname: string): string | null {
  const match = pathname.match(FILE_API_PATH_RE)
  if (!match) return null
  return safeDecode(match[1] || '').trim() || null
}

export function resolveStudioFileLinkTarget(
  href: string,
  options?: { currentOrigin?: string | null }
): StudioFileLinkTarget | null {
  const rawHref = String(href || '').trim()
  if (!rawHref || rawHref.startsWith('#')) {
    return null
  }

  const loweredHref = rawHref.toLowerCase()
  for (const prefix of INTERNAL_FILE_PREFIXES) {
    if (!loweredHref.startsWith(prefix)) continue
    const fileId = safeDecode(rawHref.slice(prefix.length)).trim()
    if (!fileId) return null
    return { kind: 'file_id', fileId }
  }

  if (rawHref.startsWith('/')) {
    const pathname = stripQueryAndHash(rawHref)
    const fileId = extractFileIdFromApiPath(pathname)
    if (fileId) {
      return { kind: 'file_id', fileId }
    }
    if (!pathname.startsWith('/FILES')) {
      return null
    }
    const normalized = normalizeProjectRelativePath(pathname.slice('/FILES'.length))
    return normalized ? { kind: 'file_path', filePath: normalized } : null
  }

  if (ABSOLUTE_URL_RE.test(rawHref) || rawHref.startsWith('//')) {
    let parsed: URL
    try {
      parsed = options?.currentOrigin ? new URL(rawHref, options.currentOrigin) : new URL(rawHref)
    } catch {
      return null
    }

    const protocol = parsed.protocol.toLowerCase()
    if (protocol !== 'http:' && protocol !== 'https:') {
      return null
    }

    if (options?.currentOrigin) {
      try {
        if (parsed.origin !== new URL(options.currentOrigin).origin) {
          return null
        }
      } catch {
        return null
      }
    }

    const fileId = extractFileIdFromApiPath(parsed.pathname)
    if (fileId) {
      return { kind: 'file_id', fileId }
    }
    if (!parsed.pathname.startsWith('/FILES')) {
      return null
    }
    const normalized = normalizeProjectRelativePath(parsed.pathname.slice('/FILES'.length))
    return normalized ? { kind: 'file_path', filePath: normalized } : null
  }

  const normalized = normalizeProjectRelativePath(stripQueryAndHash(rawHref))
  return normalized ? { kind: 'file_path', filePath: normalized } : null
}
