import type {
  BaselineComparePayload,
  BaselineRegistryEntry,
  ConfigFileEntry,
  ConfigTestPayload,
  ConfigValidationPayload,
  ConnectorSnapshot,
  ConnectorAvailabilitySnapshot,
  ExplorerPayload,
  FileChangeDiffPayload,
  FeedEnvelope,
  GitBranchesPayload,
  GitCommitDetailPayload,
  GitComparePayload,
  GitDiffPayload,
  GitLogPayload,
  GraphPayload,
  MemoryCard,
  MetricsTimelinePayload,
  OpenDocumentPayload,
  QuestSearchPayload,
  QuestDocumentAssetUploadPayload,
  QuestNodeTraceDetailPayload,
  QuestNodeTraceListPayload,
  QuestStageViewPayload,
  QuestArtifactListPayload,
  QuestRawEventListPayload,
  QuestDocument,
  QuestSummary,
  SessionPayload,
  SystemUpdateStatus,
  WeixinQrLoginStartPayload,
  WeixinQrLoginWaitPayload,
  WorkflowPayload,
} from '@/types'
import {
  getDemoGitCompare,
  getDemoExplorerPayload,
  getDemoBaselineCompare,
  getDemoGitBranches,
  getDemoGitDiffFile,
  getDemoMetricsTimeline,
  getDemoStageView,
  listDemoDocuments,
  listDemoMemory,
  openDemoDocument,
} from '@/demo/adapter'
import { isDemoProjectId } from '@/demo/projects'
import { authHeaders } from '@/lib/auth'

type ConfigStructuredPayload = Record<string, unknown>

type ConfigSaveInput =
  | { content: string; revision?: string }
  | { structured: ConfigStructuredPayload; revision?: string }

type ConfigValidateInput =
  | { content: string }
  | { structured: ConfigStructuredPayload }

type ConfigTestInput =
  | { content: string; live?: boolean; delivery_targets?: Record<string, unknown> }
  | { structured: ConfigStructuredPayload; live?: boolean; delivery_targets?: Record<string, unknown> }

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await parseResponseBody(response)
    const message = typeof body.message === 'string' && body.message.trim() ? body.message.trim() : null
    throw new Error(message || JSON.stringify(body))
  }
  return (await response.json()) as T
}

async function parseResponseBody(response: Response): Promise<Record<string, unknown>> {
  const text = await response.text()
  if (!text) return {}
  try {
    const payload = JSON.parse(text)
    if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
      return payload as Record<string, unknown>
    }
    return { value: payload }
  } catch {
    return { message: text }
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(init?.headers),
    },
  })
  return parseResponse<T>(response)
}

export const client = {
  authLogin: (token: string) =>
    api<{ ok: boolean; authenticated: boolean; auth_enabled: boolean; token_masked?: string | null }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ token }),
    }),
  authToken: () =>
    api<{ ok: boolean; auth_enabled: boolean; token?: string | null; token_masked?: string | null }>('/api/auth/token'),
  systemUpdateStatus: () => api<SystemUpdateStatus>('/api/system/update'),
  systemUpdateAction: (action: 'install_latest' | 'remind_later' | 'skip_version') =>
    api<Record<string, unknown>>('/api/system/update', {
      method: 'POST',
      body: JSON.stringify({ action }),
    }),
  quests: () => api<QuestSummary[]>('/api/quests'),
  nextQuestId: () => api<{ quest_id: string }>('/api/quest-id/next'),
  baselines: () => api<BaselineRegistryEntry[]>('/api/baselines'),
  deleteBaseline: (baselineId: string) =>
    api<{
      ok: boolean
      baseline_id: string
      deleted?: boolean
      already_deleted?: boolean
      affected_quest_ids?: string[]
      cleared_requested_refs?: number
      cleared_confirmed_refs?: number
      deleted_paths?: string[]
      warnings?: string[]
      message?: string
    }>(`/api/baselines/${encodeURIComponent(baselineId)}`, {
      method: 'DELETE',
    }),
  connectorsAvailability: () => api<ConnectorAvailabilitySnapshot>('/api/connectors/availability'),
  session: (questId: string) => api<SessionPayload>(`/api/quests/${questId}/session`),
  layout: (questId: string) =>
    api<{
      layout_json?: Record<string, unknown> | null
      updated_at?: string | null
    }>(`/api/quests/${questId}/layout`),
  updateLayout: (questId: string, payload: { layout_json?: Record<string, unknown> | null }) =>
    api<{
      layout_json?: Record<string, unknown> | null
      updated_at?: string | null
    }>(`/api/quests/${questId}/layout`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateQuestSettings: (
    questId: string,
    payload: {
      title?: string
      active_anchor?: string
      default_runner?: string
    }
  ) =>
    api<{ ok: boolean; snapshot: QuestSummary }>(`/api/quests/${questId}/settings`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  updateQuestBindings: async (
    questId: string,
    payload: {
      connector?: string | null
      conversation_id?: string | null
      bindings?: Array<{
        connector: string
        conversation_id?: string | null
      }>
      force?: boolean
    }
  ) => {
    const response = await fetch(`/api/quests/${questId}/bindings`, {
      method: Array.isArray(payload.bindings) ? 'PUT' : 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })
    const body = await parseResponseBody(response)
    return {
      status: response.status,
      ...body,
    } as Record<string, unknown>
  },
  events: (
    questId: string,
    after: number,
    options?: { before?: number | null; limit?: number; tail?: boolean }
  ) => {
    const params = new URLSearchParams()
    if (typeof options?.before === 'number' && Number.isFinite(options.before) && options.before > 0) {
      params.set('before', String(Math.floor(options.before)))
    } else {
      params.set('after', String(after))
    }
    params.set('format', 'acp')
    params.set('session_id', `quest:${questId}`)
    if (typeof options?.limit === 'number' && Number.isFinite(options.limit) && options.limit > 0) {
      params.set('limit', String(Math.floor(options.limit)))
    }
    if (options?.tail) {
      params.set('tail', '1')
    }
    return api<FeedEnvelope>(`/api/quests/${questId}/events?${params.toString()}`)
  },
  eventsStreamUrl: (questId: string, after = 0) =>
    `/api/quests/${questId}/events?after=${after}&format=acp&session_id=quest:${questId}&stream=1`,
  workflow: (questId: string) => api<WorkflowPayload>(`/api/quests/${questId}/workflow`),
  rawEvents: (
    questId: string,
    options?: {
      after?: number
      limit?: number
      tail?: boolean
    }
  ) => {
    const params = new URLSearchParams()
    params.set('format', 'raw')
    if (typeof options?.after === 'number' && Number.isFinite(options.after) && options.after >= 0) {
      params.set('after', String(Math.floor(options.after)))
    }
    if (typeof options?.limit === 'number' && Number.isFinite(options.limit) && options.limit > 0) {
      params.set('limit', String(Math.floor(options.limit)))
    }
    if (options?.tail) {
      params.set('tail', '1')
    }
    const suffix = params.toString()
    return api<QuestRawEventListPayload>(`/api/quests/${questId}/events${suffix ? `?${suffix}` : ''}`)
  },
  artifacts: (questId: string) => api<QuestArtifactListPayload>(`/api/quests/${questId}/artifacts`),
  nodeTraces: (questId: string, selectionType?: string | null) =>
    api<QuestNodeTraceListPayload>(
      `/api/quests/${questId}/node-traces${
        selectionType ? `?selection_type=${encodeURIComponent(selectionType)}` : ''
      }`
    ),
  nodeTrace: (questId: string, selectionRef: string, selectionType?: string | null) =>
    api<QuestNodeTraceDetailPayload>(
      `/api/quests/${questId}/node-traces/${encodeURIComponent(selectionRef)}${
        selectionType ? `?selection_type=${encodeURIComponent(selectionType)}` : ''
      }`
    ),
  stageView: (
    questId: string,
    payload: {
      selection_ref?: string | null
      selection_type?: string | null
      branch_name?: string | null
      stage_key?: string | null
      worktree_rel_path?: string | null
      scope_paths?: string[] | null
      compare_base?: string | null
      compare_head?: string | null
      label?: string | null
      summary?: string | null
      baseline_gate?: string | null
    }
  ) => {
    if (isDemoProjectId(questId)) {
      const demoPayload = getDemoStageView(questId, payload)
      if (!demoPayload) {
        throw new Error(`Unknown demo stage view for ${questId}`)
      }
      return Promise.resolve(demoPayload)
    }
    return api<QuestStageViewPayload>(`/api/quests/${questId}/stage-view`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  explorer: (
    questId: string,
    options?: { revision?: string | null; mode?: string | null; profile?: string | null }
  ) => {
    if (isDemoProjectId(questId)) {
      const payload = getDemoExplorerPayload(questId)
      if (!payload) {
        throw new Error(`Unknown demo explorer payload for ${questId}`)
      }
      return Promise.resolve(payload)
    }
    const params = new URLSearchParams()
    if (options?.revision) {
      params.set('revision', options.revision)
    }
    if (options?.mode) {
      params.set('mode', options.mode)
    }
    if (options?.profile) {
      params.set('profile', options.profile)
    }
    const suffix = params.toString()
    return api<ExplorerPayload>(`/api/quests/${questId}/explorer${suffix ? `?${suffix}` : ''}`)
  },
  search: (questId: string, query: string, limit = 50) =>
    api<QuestSearchPayload>(
      `/api/quests/${questId}/search?q=${encodeURIComponent(query)}&limit=${Math.max(1, Math.floor(limit))}`
    ),
  memory: (questId: string) => {
    if (isDemoProjectId(questId)) {
      const payload = listDemoMemory(questId)
      if (!payload) {
        throw new Error(`Unknown demo memory payload for ${questId}`)
      }
      return Promise.resolve(payload)
    }
    return api<MemoryCard[]>(`/api/quests/${questId}/memory`)
  },
  documents: (questId: string) => {
    if (isDemoProjectId(questId)) {
      const payload = listDemoDocuments(questId)
      if (!payload) {
        throw new Error(`Unknown demo documents payload for ${questId}`)
      }
      return Promise.resolve(payload)
    }
    return api<QuestDocument[]>(`/api/quests/${questId}/documents`)
  },
  graph: (questId: string) => api<GraphPayload>(`/api/quests/${questId}/graph`),
  metricsTimeline: (questId: string) => {
    if (isDemoProjectId(questId)) {
      const payload = getDemoMetricsTimeline(questId)
      if (!payload) {
        throw new Error(`Unknown demo metrics timeline for ${questId}`)
      }
      return Promise.resolve(payload)
    }
    return api<MetricsTimelinePayload>(`/api/quests/${questId}/metrics/timeline`)
  },
  baselineCompare: (questId: string) => {
    if (isDemoProjectId(questId)) {
      const payload = getDemoBaselineCompare(questId)
      if (!payload) {
        throw new Error(`Unknown demo baseline compare payload for ${questId}`)
      }
      return Promise.resolve(payload)
    }
    return api<BaselineComparePayload>(`/api/quests/${questId}/baselines/compare`)
  },
  gitBranches: (questId: string) => {
    if (isDemoProjectId(questId)) {
      const payload = getDemoGitBranches(questId)
      if (!payload) {
        throw new Error(`Unknown demo git branches for ${questId}`)
      }
      return Promise.resolve(payload)
    }
    return api<GitBranchesPayload>(`/api/quests/${questId}/git/branches`)
  },
  gitLog: (questId: string, ref: string, base?: string, limit = 30) =>
    api<GitLogPayload>(
      `/api/quests/${questId}/git/log?ref=${encodeURIComponent(ref)}${base ? `&base=${encodeURIComponent(base)}` : ''}&limit=${limit}`
    ),
  gitCompare: (questId: string, base: string, head: string) => {
    if (isDemoProjectId(questId)) {
      const payload = getDemoGitCompare(questId, base, head)
      if (!payload) {
        throw new Error(`Unknown demo git compare ${base} -> ${head}`)
      }
      return Promise.resolve(payload)
    }
    return api<GitComparePayload>(
      `/api/quests/${questId}/git/compare?base=${encodeURIComponent(base)}&head=${encodeURIComponent(head)}`
    )
  },
  gitCommit: (questId: string, sha: string) =>
    api<GitCommitDetailPayload>(`/api/quests/${questId}/git/commit?sha=${encodeURIComponent(sha)}`),
  gitDiffFile: (questId: string, base: string, head: string, path: string) => {
    if (isDemoProjectId(questId)) {
      const payload = getDemoGitDiffFile(questId, base, head, path)
      if (!payload) {
        throw new Error(`Unknown demo git diff ${base} -> ${head} for ${path}`)
      }
      return Promise.resolve(payload)
    }
    return api<GitDiffPayload>(
      `/api/quests/${questId}/git/diff-file?base=${encodeURIComponent(base)}&head=${encodeURIComponent(head)}&path=${encodeURIComponent(path)}`
    )
  },
  fileChangeDiff: (questId: string, runId: string, path: string, eventId?: string) =>
    api<FileChangeDiffPayload>(
      `/api/quests/${questId}/operations/file-change-diff?run_id=${encodeURIComponent(runId)}&path=${encodeURIComponent(path)}${
        eventId ? `&event_id=${encodeURIComponent(eventId)}` : ''
      }`
    ),
  gitCommitFile: (questId: string, sha: string, path: string) =>
    api<GitDiffPayload>(`/api/quests/${questId}/git/commit-file?sha=${encodeURIComponent(sha)}&path=${encodeURIComponent(path)}`),
  openDocument: (questId: string, documentId: string) => {
    if (isDemoProjectId(questId)) {
      const payload = openDemoDocument(questId, documentId)
      if (!payload) {
        throw new Error(`Unknown demo document ${documentId}`)
      }
      return Promise.resolve(payload)
    }
    return api<OpenDocumentPayload>(`/api/quests/${questId}/documents/open`, {
      method: 'POST',
      body: JSON.stringify({ document_id: documentId }),
    })
  },
  saveDocument: (questId: string, documentId: string, content: string, revision?: string) =>
    api<{
      ok: boolean
      conflict?: boolean
      message?: string
      revision?: string
      updated_payload?: OpenDocumentPayload
    }>(`/api/quests/${questId}/documents/${documentId}`, {
      method: 'PUT',
      body: JSON.stringify({ content, revision }),
    }),
  uploadDocumentAsset: (
    questId: string,
    payload: {
      document_id: string
      file_name: string
      mime_type?: string
      kind?: string
      content_base64: string
    }
  ) =>
    api<QuestDocumentAssetUploadPayload>(`/api/quests/${questId}/documents/assets`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  sendChat: (
    questId: string,
    text: string,
    replyToInteractionId?: string | null,
    clientMessageId?: string | null
  ) =>
    api<{
      ok: boolean
      message?: {
        id?: string
        role?: string
        content?: string
        source?: string
        created_at?: string
        delivery_state?: string
        client_message_id?: string
      }
    }>(`/api/quests/${questId}/chat`, {
      method: 'POST',
      body: JSON.stringify({
        text,
        source: 'web-react',
        reply_to_interaction_id: replyToInteractionId || undefined,
        client_message_id: clientMessageId || undefined,
      }),
    }),
  sendCommand: (questId: string, command: string) =>
    api<Record<string, unknown>>(`/api/quests/${questId}/commands`, {
      method: 'POST',
      body: JSON.stringify({ command, source: 'web-react' }),
    }),
  controlQuest: (questId: string, action: 'pause' | 'stop' | 'resume') =>
    api<Record<string, unknown>>(`/api/quests/${questId}/control`, {
      method: 'POST',
      body: JSON.stringify({ action, source: 'web-react' }),
    }),
  runSkill: (questId: string, payload: { skill_id: string; model?: string; message: string }) =>
    api<Record<string, unknown>>(`/api/quests/${questId}/runs`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  createQuest: (goal: string) =>
    api<{ ok: boolean; snapshot: QuestSummary }>('/api/quests', {
      method: 'POST',
      body: JSON.stringify({ goal }),
    }),
  createQuestWithOptions: (payload: {
    goal: string
    title?: string
    quest_id?: string
    source?: string
    auto_start?: boolean
    initial_message?: string
    preferred_connector_conversation_id?: string
    auto_bind_latest_connectors?: boolean
    requested_connector_bindings?: Array<{
      connector: string
      conversation_id?: string | null
    }>
    force_connector_rebind?: boolean
    requested_baseline_ref?: { baseline_id: string; variant_id?: string | null } | null
    startup_contract?: Record<string, unknown> | null
  }) =>
    api<{ ok: boolean; snapshot: QuestSummary }>('/api/quests', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteQuest: (questId: string) =>
    api<{ ok: boolean; quest_id: string; deleted?: boolean }>(`/api/quests/${questId}`, {
      method: 'DELETE',
      body: JSON.stringify({ source: 'web-react' }),
    }),
  docsIndex: () => api<QuestDocument[]>('/api/docs'),
  openSystemDoc: (documentId: string) =>
    api<OpenDocumentPayload>('/api/docs/open', {
      method: 'POST',
      body: JSON.stringify({ document_id: documentId }),
    }),
  connectors: () => api<ConnectorSnapshot[]>('/api/connectors'),
  startWeixinQrLogin: (payload?: { force?: boolean }) =>
    api<WeixinQrLoginStartPayload>('/api/connectors/weixin/login/qr/start', {
      method: 'POST',
      body: JSON.stringify(payload || {}),
    }),
  waitWeixinQrLogin: (payload: { session_key: string; timeout_ms?: number }) =>
    api<WeixinQrLoginWaitPayload>('/api/connectors/weixin/login/qr/wait', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteConnectorProfile: (connectorName: string, profileId: string) =>
    api<{
      ok: boolean
      connector: string
      profile_id: string
      deleted?: boolean
      deleted_bound_conversations?: string[]
      remaining_profile_count?: number
      snapshot?: ConnectorSnapshot | null
      message?: string
    }>(`/api/connectors/${encodeURIComponent(connectorName)}/profiles/${encodeURIComponent(profileId)}`, {
      method: 'DELETE',
    }),
  configFiles: () => api<ConfigFileEntry[]>('/api/config/files'),
  configDocument: (name: string) => api<OpenDocumentPayload>(`/api/config/${name}`),
  saveConfig: (name: string, input: ConfigSaveInput) =>
    api<{
      ok: boolean
      conflict?: boolean
      message?: string
      revision?: string
      warnings?: string[]
      errors?: string[]
    }>(`/api/config/${name}`, {
      method: 'PUT',
      body: JSON.stringify({ ...input }),
    }),
  validateConfig: (name: string, input: ConfigValidateInput) =>
    api<ConfigValidationPayload>('/api/config/validate', {
      method: 'POST',
      body: JSON.stringify({ name, ...input }),
    }),
  testConfig: (name: string, input: ConfigTestInput) =>
    api<ConfigTestPayload>('/api/config/test', {
      method: 'POST',
      body: JSON.stringify({ name, ...input }),
    }),
}
