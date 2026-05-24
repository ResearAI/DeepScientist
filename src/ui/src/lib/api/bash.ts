import { apiClient } from '@/lib/api/client'
import type {
  BashLogEntry,
  BashLogMeta,
  BashSession,
  BashStopResponse,
} from '@/lib/types/bash'

function normalizeBashSessionsPayload(payload: unknown): BashSession[] {
  if (Array.isArray(payload)) return payload as BashSession[]
  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>
    if (Array.isArray(record.items)) return record.items as BashSession[]
    if (Array.isArray(record.sessions)) return record.sessions as BashSession[]
  }
  return []
}

export async function listBashSessions(
  projectId: string,
  params?: {
    status?: string
    kind?: string
    agentInstanceIds?: string[]
    agentIds?: string[]
    chatSessionId?: string
    limit?: number
  }
) {
  const response = await apiClient.get(`/api/quests/${projectId}/bash/sessions`, {
    params: {
      status: params?.status,
      kind: params?.kind,
      agent_instance_ids: params?.agentInstanceIds?.length
        ? params.agentInstanceIds.join(',')
        : undefined,
      agent_ids: params?.agentIds?.length ? params.agentIds.join(',') : undefined,
      chat_session_id: params?.chatSessionId,
      limit: params?.limit,
    },
  })
  return normalizeBashSessionsPayload(response.data)
}

export async function getBashSession(projectId: string, bashId: string) {
  const response = await apiClient.get(`/api/quests/${projectId}/bash/sessions/${bashId}`)
  return response.data as BashSession
}

export async function getBashLogs(
  projectId: string,
  bashId: string,
  params?: {
    limit?: number
    beforeSeq?: number | null
    afterSeq?: number | null
    order?: 'asc' | 'desc'
  }
) {
  const response = await apiClient.get(`/api/quests/${projectId}/bash/sessions/${bashId}/logs`, {
    params: {
      limit: params?.limit,
      before_seq: params?.beforeSeq ?? undefined,
      after_seq: params?.afterSeq ?? undefined,
      order: params?.order ?? undefined,
    },
  })
  const parseHeaderNumber = (value: string | undefined) => {
    if (!value) return null
    const parsed = Number.parseInt(value, 10)
    return Number.isFinite(parsed) ? parsed : null
  }
  const headers = response.headers ?? {}
  const meta: BashLogMeta = {
    tailLimit: parseHeaderNumber(headers['x-bash-log-tail-limit']),
    tailStartSeq: parseHeaderNumber(headers['x-bash-log-tail-start-seq']),
    latestSeq: parseHeaderNumber(headers['x-bash-log-latest-seq']),
    afterSeq: params?.afterSeq ?? null,
    beforeSeq: params?.beforeSeq ?? null,
  }
  return { entries: response.data as BashLogEntry[], meta }
}

export async function stopBashSession(
  projectId: string,
  bashId: string,
  input?: {
    reason?: string
    wait?: boolean
    force?: boolean
    timeoutSeconds?: number
  }
) {
  const response = await apiClient.post(`/api/quests/${projectId}/bash/sessions/${bashId}/stop`, {
    reason: input?.reason,
    wait: input?.wait,
    force: input?.force,
    timeout_seconds: input?.timeoutSeconds,
  })
  return response.data as BashStopResponse
}
