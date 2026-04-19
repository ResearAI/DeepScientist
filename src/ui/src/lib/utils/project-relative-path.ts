function safeDecodePathSegment(value: string): string {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

export function normalizeProjectRelativePath(value: string): string {
  let normalized = String(value || '').trim()
  if (!normalized) return ''

  normalized = normalized.replace(/\\/g, '/')
  if (/^\/?FILES(?:\/|$)/i.test(normalized)) {
    normalized = normalized.replace(/^\/?FILES(?:\/|$)/i, '')
  }

  const segments = safeDecodePathSegment(normalized).split('/')
  const resolved: string[] = []

  for (const segment of segments) {
    if (!segment || segment === '.') continue
    if (segment === '..') {
      if (resolved.length > 0) {
        resolved.pop()
      }
      continue
    }
    resolved.push(segment)
  }

  return resolved.join('/')
}

export function toProjectRelativeDisplayPath(value?: string | null): string {
  const normalized = normalizeProjectRelativePath(String(value || ''))
  return normalized ? `/${normalized}` : '/'
}

export function isHiddenProjectRelativePath(value?: string | null): boolean {
  const normalized = normalizeProjectRelativePath(String(value || ''))
  if (!normalized) return false
  return normalized.split('/').some((segment) => segment.startsWith('.'))
}
