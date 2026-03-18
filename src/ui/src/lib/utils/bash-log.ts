import type { BashProgress } from '@/lib/types/bash'

export type BashStatusValue = 'running' | 'completed' | 'failed' | 'terminated'

export type BashStatusMarker = {
  status: BashStatusValue
  bashId: string
  timestamp: string
  userId: string
  sessionId?: string | null
  agentId?: string | null
  agentInstanceId?: string | null
  exitCode: number | null
  reason: string
}

const MARKER_PREFIX = '__DS_BASH_STATUS__'
const CARRIAGE_RETURN_PREFIX = '__DS_BASH_CR__'
const PROGRESS_PREFIX = '__DS_PROGRESS__'
const MARKER_FIELD_REGEX = /(\w+)=("([^"\\]*(\\.[^"\\]*)*)"|[^\s]+)/g

function unescapeReason(value: string) {
  return value.replace(/\\n/g, '\n').replace(/\\"/g, '"')
}

export const BASH_CARRIAGE_RETURN_PREFIX = CARRIAGE_RETURN_PREFIX
export const BASH_PROGRESS_PREFIX = PROGRESS_PREFIX

export function isBashProgressMarker(line: string): boolean {
  return Boolean(line && line.startsWith(PROGRESS_PREFIX))
}

export function parseBashProgressMarker(line: string): BashProgress | null {
  if (!isBashProgressMarker(line)) return null
  const raw = line.slice(PROGRESS_PREFIX.length).trim()
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return null
    }
    return parsed as BashProgress
  } catch {
    return null
  }
}

export function splitBashLogLine(line: string): { kind: 'line' | 'carriage'; text: string } {
  if (line.startsWith(CARRIAGE_RETURN_PREFIX)) {
    return { kind: 'carriage', text: line.slice(CARRIAGE_RETURN_PREFIX.length) }
  }
  return { kind: 'line', text: line }
}

export function parseBashStatusMarker(line: string): BashStatusMarker | null {
  if (!line || !line.startsWith(MARKER_PREFIX)) return null
  const raw = line.trim().slice(MARKER_PREFIX.length).trim()
  const fields: Record<string, string> = {}
  MARKER_FIELD_REGEX.lastIndex = 0
  let match = MARKER_FIELD_REGEX.exec(raw)
  while (match) {
    const key = match[1]
    const rawValue = match[2]
    const cleaned =
      rawValue.startsWith('"') && rawValue.endsWith('"')
        ? unescapeReason(rawValue.slice(1, -1))
        : rawValue
    fields[key] = cleaned
    match = MARKER_FIELD_REGEX.exec(raw)
  }
  const status = fields.status as BashStatusValue
  if (!status || !fields.bash_id || !fields.ts || !fields.user_id) return null
  const exitRaw = fields.exit_code
  let exitCode: number | null = null
  if (exitRaw && exitRaw !== 'none') {
    const parsed = Number(exitRaw)
    exitCode = Number.isFinite(parsed) ? parsed : null
  }
  const normalizeOptional = (value?: string) => {
    if (!value || value === 'none') return null
    return value
  }
  return {
    status,
    bashId: fields.bash_id,
    timestamp: fields.ts,
    userId: fields.user_id,
    sessionId: normalizeOptional(fields.session_id),
    agentId: normalizeOptional(fields.agent_id),
    agentInstanceId: normalizeOptional(fields.agent_instance_id),
    exitCode,
    reason: normalizeOptional(fields.reason) ?? '',
  }
}
