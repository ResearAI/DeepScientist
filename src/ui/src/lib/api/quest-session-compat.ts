import { apiClient, getApiBaseUrl } from '@/lib/api/client'
import { isQuestRuntimeSurface, shouldUseQuestProject } from '@/lib/runtime/quest-runtime'
import type {
  AgentSSEEvent,
  DoneEventData,
  ErrorEventData,
  EventMetadata,
  MessageEventData,
  ReasoningEventData,
  StatusEventData,
  ToolEventData,
} from '@/lib/types/chat-events'
import { deriveMcpIdentity } from '@/lib/mcpIdentity'
import type { FeedEnvelope, SessionPayload } from '@/types'

const QUEST_SESSION_PREFIX = 'quest:'
const QUEST_HISTORY_PAGE_SIZE = 200
const QUEST_HISTORY_MAX_BATCHES = 25
const QUEST_DEFAULT_LIMIT = 400
const QUEST_HEAVY_REQUEST_TIMEOUT_MS = 180000

type QuestSessionLike = {
  session_id: string
  status?: string | null
  title?: string | null
  is_active?: boolean
  is_shared?: boolean
  latest_message?: string | null
  latest_message_at?: number | null
  updated_at?: number | null
  events?: AgentSSEEvent[]
  events_truncated?: boolean
  event_limit?: number | null
  plan_history?: []
  execution_target?: string | null
  cli_server_id?: string | null
  session_metadata?: Record<string, unknown>
  agents?: Array<Record<string, unknown>>
  event_metadata_mode?: 'compact' | 'full' | string
}

type QuestSnapshot = SessionPayload['snapshot'] & Record<string, unknown>
type QuestAcpUpdateEnvelope = FeedEnvelope['acp_updates'][number]

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value : null
}

function asLowerString(value: unknown): string {
  return typeof value === 'string' ? value.trim().toLowerCase() : ''
}

function toUnixSeconds(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value > 1_000_000_000_000 ? Math.floor(value / 1000) : Math.floor(value)
  }
  if (typeof value === 'string') {
    const numeric = Number(value)
    if (Number.isFinite(numeric)) {
      return numeric > 1_000_000_000_000 ? Math.floor(numeric / 1000) : Math.floor(numeric)
    }
    const parsed = Date.parse(value)
    if (!Number.isNaN(parsed)) {
      return Math.floor(parsed / 1000)
    }
  }
  return Math.floor(Date.now() / 1000)
}

function normalizeToolSegment(value?: string | null) {
  if (!value) return ''
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
}

function parseStructuredValue(value: unknown) {
  if (typeof value === 'string' && value.trim()) {
    try {
      return JSON.parse(value) as unknown
    } catch {
      return null
    }
  }
  if (value && typeof value === 'object') return value
  return null
}

export function buildQuestSessionId(questId: string) {
  return `${QUEST_SESSION_PREFIX}${questId}`
}

function canonicalToolFunction(
  toolName?: string | null,
  mcpServer?: string | null,
  mcpTool?: string | null
) {
  if (mcpServer && mcpTool) {
    return `mcp__${normalizeToolSegment(mcpServer)}__${normalizeToolSegment(mcpTool)}`
  }
  const normalized = normalizeToolSegment(toolName)
  if (toolName) {
    const raw = toolName.trim().toLowerCase()
    for (const prefix of ['memory', 'artifact', 'bash_exec']) {
      if (raw.startsWith(`${prefix}.`)) {
        const suffix = raw.slice(prefix.length + 1)
        return `mcp__${normalizeToolSegment(prefix)}__${normalizeToolSegment(suffix)}`
      }
    }
  }
  if (normalized === 'shell_command') return 'shell_exec'
  if (normalized === 'web_fetch') return 'webfetch'
  if (normalized === 'web_search' || normalized === 'websearch') return 'web_search'
  return normalized || toolName || 'tool'
}

function snapshotBashRunningCount(snapshot: QuestSnapshot): number {
  const counts = asRecord(snapshot.counts)
  const raw = counts?.bash_running_count
  if (typeof raw === 'number' && Number.isFinite(raw)) {
    return Math.max(0, Math.floor(raw))
  }
  if (typeof raw === 'string') {
    const parsed = Number(raw)
    if (Number.isFinite(parsed)) {
      return Math.max(0, Math.floor(parsed))
    }
  }
  return 0
}

function isCopilotSnapshotParkedForUser(snapshot: QuestSnapshot): boolean {
  const workspaceMode = asLowerString(snapshot.workspace_mode)
  const continuationPolicy = asLowerString((snapshot as Record<string, unknown>).continuation_policy)
  const activeRunId = asString(snapshot.active_run_id)
  const runtimeStatus = asLowerString(snapshot.runtime_status) || asLowerString(snapshot.status)
  if (workspaceMode !== 'copilot') return false
  if (continuationPolicy !== 'wait_for_user_or_resume') return false
  if (activeRunId) return false
  if (snapshotBashRunningCount(snapshot) > 0) return false
  if (runtimeStatus === 'failed' || runtimeStatus === 'error') return false
  return true
}

function buildEventMetadata(
  questId: string,
  sessionId: string,
  extra?: Partial<EventMetadata>
): EventMetadata {
  return {
    surface: 'copilot',
    quest_id: questId,
    session_id: sessionId,
    sender_type: 'agent',
    sender_label: 'DeepScientist',
    sender_name: 'DeepScientist',
    ...extra,
  }
}

function buildToolArgs(functionName: string, rawArgs: unknown, metadata: Record<string, unknown>) {
  const structuredArgs = parseStructuredValue(rawArgs)
  const recordArgs = asRecord(structuredArgs)
  if (recordArgs) return recordArgs
  const raw = typeof rawArgs === 'string' ? rawArgs : ''
  if (!raw) {
    if (functionName === 'web_search') {
      const searchPayload = asRecord(metadata.search)
      const queries = Array.isArray(searchPayload?.queries)
        ? searchPayload?.queries.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
        : []
      if (queries.length > 0) {
        return { query: queries[0], queries }
      }
    }
    return {}
  }
  if (functionName === 'shell_exec') {
    return { command: raw, raw }
  }
  if (functionName === 'web_search') {
    const searchPayload = asRecord(metadata.search)
    const queries = Array.isArray(searchPayload?.queries)
      ? searchPayload?.queries.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
      : []
    return {
      query: queries[0] ?? raw,
      ...(queries.length > 0 ? { queries } : {}),
      raw,
    }
  }
  return { raw }
}

function buildToolContent(
  functionName: string,
  rawStatus: string | null,
  rawOutput: unknown,
  metadata: Record<string, unknown>
) {
  const parsedOutput = parseStructuredValue(rawOutput)
  const parsedRecord = asRecord(parsedOutput)
  if (functionName === 'web_search') {
    const searchPayload = asRecord(metadata.search) ?? parsedRecord
    const result: Record<string, unknown> = {
      status: rawStatus || 'completed',
    }
    if (searchPayload) {
      Object.assign(result, searchPayload)
    } else if (typeof rawOutput === 'string' && rawOutput.trim()) {
      result.output = rawOutput
    }
    return {
      status: rawStatus || 'completed',
      result,
    }
  }

  if (parsedRecord) {
    const result = { ...parsedRecord }
    if (rawStatus && typeof result.status !== 'string') {
      result.status = rawStatus
    }
    return {
      status: rawStatus || (typeof result.status === 'string' ? result.status : 'completed'),
      result,
    }
  }

  const result: Record<string, unknown> = {}
  if (rawStatus) {
    result.status = rawStatus
  }
  if (typeof rawOutput === 'string' && rawOutput.trim()) {
    result.output = rawOutput
  }

  if (
    metadata.mcp_server === 'bash_exec' &&
    metadata.mcp_tool === 'bash_exec'
  ) {
    for (const key of [
      'bash_id',
      'status',
      'started_at',
      'finished_at',
      'exit_code',
      'stop_reason',
      'last_progress',
      'log_path',
    ]) {
      if (metadata[key] != null && result[key] == null) {
        result[key] = metadata[key]
      }
    }
  }

  return {
    status: rawStatus || 'completed',
    result,
  }
}

function normalizeQuestMessageEvent(
  update: Record<string, unknown>,
  questId: string,
  sessionId: string,
  eventId: string,
  timestamp: number,
  seq?: number
): AgentSSEEvent | null {
  const eventType = asString(update.event_type) || ''
  const message = asRecord(update.message)
  const content = asString(message?.content) ?? ''
  if (eventType === 'runner.reasoning') {
    const data: ReasoningEventData = {
      event_id: eventId,
      timestamp,
      ...(typeof seq === 'number' ? { seq } : {}),
      created_at: typeof update.created_at === 'string' ? update.created_at : undefined,
      reasoning_id: asString(message?.run_id) || eventId,
      status: 'completed',
      content,
      kind: 'full',
      metadata: buildEventMetadata(questId, sessionId),
    }
    return { event: 'reasoning', data }
  }

  const role = message?.role === 'user' ? 'user' : 'assistant'
  const metadata = buildEventMetadata(
    questId,
    sessionId,
    role === 'user'
      ? {
          sender_type: 'user',
          sender_label: 'You',
          sender_name: 'You',
          delivery_state:
            typeof message?.delivery_state === 'string' ? message.delivery_state : undefined,
        }
      : {
          sender_type: 'agent',
          sender_label: 'DeepScientist',
          sender_name: 'DeepScientist',
          agent_label: 'DeepScientist',
        }
  )
  if (role === 'assistant') {
    const runId =
      typeof message?.run_id === 'string' && message.run_id.trim().length > 0
        ? message.run_id
        : null
    const skillId =
      typeof message?.skill_id === 'string' && message.skill_id.trim().length > 0
        ? message.skill_id
        : null
    metadata.quest_event_type = eventType || undefined
    metadata.quest_run_id = runId ?? undefined
    metadata.quest_skill_id = skillId ?? undefined
  }
  const data: MessageEventData = {
    event_id: eventId,
    timestamp,
    ...(typeof seq === 'number' ? { seq } : {}),
    created_at: typeof update.created_at === 'string' ? update.created_at : undefined,
    role,
    ...(eventType === 'runner.delta' ? { delta: content } : { content }),
    metadata,
  }
  return { event: 'message', data }
}

function normalizeQuestToolEvent(
  update: Record<string, unknown>,
  questId: string,
  sessionId: string,
  eventId: string,
  timestamp: number,
  seq?: number
): AgentSSEEvent | null {
  const dataRecord = asRecord(update.data)
  const rawToolName = asString(dataRecord?.tool_name)
  const derivedIdentity = deriveMcpIdentity(
    rawToolName,
    asString(dataRecord?.mcp_server),
    asString(dataRecord?.mcp_tool)
  )
  const mcpServer = derivedIdentity.server
  const mcpTool = derivedIdentity.tool
  const rawMetadata = asRecord(dataRecord?.metadata) ?? {}
  const metadata: EventMetadata = buildEventMetadata(questId, sessionId, {
    ...rawMetadata,
    ...(mcpServer ? { mcp_server: mcpServer } : {}),
    ...(mcpTool ? { mcp_tool: mcpTool } : {}),
    bash_id:
      typeof rawMetadata.bash_id === 'string'
        ? rawMetadata.bash_id
        : typeof rawMetadata.bashId === 'string'
          ? rawMetadata.bashId
          : undefined,
    bash_status:
      typeof rawMetadata.status === 'string'
        ? rawMetadata.status
        : typeof dataRecord?.status === 'string'
          ? dataRecord.status
          : undefined,
    bash_mode:
      typeof rawMetadata.mode === 'string'
        ? rawMetadata.mode
        : typeof rawMetadata.bash_mode === 'string'
          ? rawMetadata.bash_mode
          : undefined,
    bash_command:
      typeof rawMetadata.command === 'string'
        ? rawMetadata.command
        : typeof rawMetadata.bash_command === 'string'
          ? rawMetadata.bash_command
          : undefined,
    bash_workdir:
      typeof rawMetadata.workdir === 'string'
        ? rawMetadata.workdir
        : typeof rawMetadata.bash_workdir === 'string'
          ? rawMetadata.bash_workdir
          : undefined,
  })
  const functionName = canonicalToolFunction(rawToolName, mcpServer, mcpTool)
  const eventType = asString(update.event_type)
  const backendStatus = asString(dataRecord?.status).toLowerCase()
  const toolStatus: ToolEventData['status'] =
    eventType === 'runner.tool_call'
      ? 'calling'
      : backendStatus === 'failed' || backendStatus === 'error'
        ? 'failed'
        : 'called'
  const toolData: ToolEventData = {
    event_id: eventId,
    timestamp,
    ...(typeof seq === 'number' ? { seq } : {}),
    created_at: typeof update.created_at === 'string' ? update.created_at : undefined,
    tool_call_id: asString(dataRecord?.tool_call_id) || eventId,
    name: mcpTool || rawToolName || mcpServer || 'tool',
    function: functionName,
    status: toolStatus,
    args: buildToolArgs(functionName, dataRecord?.args, rawMetadata),
    metadata,
    ...(eventType === 'runner.tool_result'
      ? { content: buildToolContent(functionName, asString(dataRecord?.status), dataRecord?.output, rawMetadata) }
      : {}),
  }
  return { event: 'tool', data: toolData }
}

function normalizeQuestStatusEvent(
  update: Record<string, unknown>,
  questId: string,
  sessionId: string,
  eventId: string,
  timestamp: number,
  seq?: number
): AgentSSEEvent | null {
  const eventType = asString(update.event_type) || ''
  const dataRecord = asRecord(update.data)
  if (eventType === 'runner.turn_finish') {
    const data: DoneEventData = {
      event_id: eventId,
      timestamp,
      ...(typeof seq === 'number' ? { seq } : {}),
      created_at: typeof update.created_at === 'string' ? update.created_at : undefined,
      metadata: buildEventMetadata(questId, sessionId),
    }
    return { event: 'done', data }
  }

  if (eventType === 'runner.turn_error') {
    const data: ErrorEventData = {
      event_id: eventId,
      timestamp,
      ...(typeof seq === 'number' ? { seq } : {}),
      created_at: typeof update.created_at === 'string' ? update.created_at : undefined,
      error: asString(dataRecord?.summary) || 'Quest run failed.',
      metadata: buildEventMetadata(questId, sessionId),
    }
    return { event: 'error', data }
  }

  if (eventType === 'quest.control') {
    const action = asString(dataRecord?.action) || asString((update as Record<string, unknown>).action) || ''
    if (action === 'pause' || action === 'stop') {
      return {
        event: 'wait',
        data: {
          event_id: eventId,
          timestamp,
          ...(typeof seq === 'number' ? { seq } : {}),
          created_at: typeof update.created_at === 'string' ? update.created_at : undefined,
          metadata: buildEventMetadata(questId, sessionId),
        },
      }
    }
  }

  if (eventType === 'artifact.recorded') {
    const artifact = asRecord(update.artifact)
    const pathsRecord = asRecord(artifact?.paths) ?? {}
    const relatedFiles = Object.values(pathsRecord).filter(
      (value): value is string => typeof value === 'string' && value.trim().length > 0
    )
    const message =
      asString(artifact?.summary) ||
      asString(artifact?.guidance) ||
      asString(artifact?.reason) ||
      `Artifact recorded: ${asString(artifact?.kind) || 'artifact'}`
    const data: StatusEventData = {
      event_id: eventId,
      timestamp,
      ...(typeof seq === 'number' ? { seq } : {}),
      created_at: typeof update.created_at === 'string' ? update.created_at : undefined,
      message,
      status: 'artifact',
      event_type: eventType,
      ...(relatedFiles.length > 0 ? { related_files: relatedFiles } : {}),
      ...(asString(artifact?.artifact_path) ? { artifacts: [String(artifact?.artifact_path)] } : {}),
      metadata: buildEventMetadata(questId, sessionId),
    }
    return { event: 'status', data }
  }

  const label = asString(dataRecord?.label) || eventType || 'event'
  const summary =
    asString(dataRecord?.summary) ||
    asString(dataRecord?.message) ||
    asString(dataRecord?.text) ||
    label.replace(/_/g, ' ')
  const status: StatusEventData = {
    event_id: eventId,
    timestamp,
    ...(typeof seq === 'number' ? { seq } : {}),
    created_at: typeof update.created_at === 'string' ? update.created_at : undefined,
    message: summary,
    status:
      label === 'run_started'
        ? 'running'
        : label === 'run_failed'
          ? 'failed'
          : label === 'run_finished'
            ? 'completed'
            : label,
    event_type: eventType,
    metadata: buildEventMetadata(questId, sessionId),
  }
  return { event: 'status', data: status }
}

export function normalizeQuestAcpUpdateEnvelope(
  envelope: QuestAcpUpdateEnvelope | Record<string, unknown>
): AgentSSEEvent[] {
  const params = asRecord((envelope as QuestAcpUpdateEnvelope).params ?? asRecord(envelope)?.params)
  const update = asRecord(params?.update)
  const sessionId =
    asString(params?.sessionId) ||
    asString(update?.session_id) ||
    buildQuestSessionId(asString(update?.quest_id) || '')
  const questId =
    asString(update?.quest_id) ||
    getQuestIdFromSessionId(sessionId) ||
    ''
  if (!update || !sessionId || !questId) return []
  const eventId = asString(update.event_id) || `quest-${questId}-${String(update.cursor ?? Date.now())}`
  const timestamp = toUnixSeconds(update.created_at)
  const seq = typeof update.cursor === 'number' ? update.cursor : undefined
  const eventType = asString(update.event_type) || ''

  if (update.kind === 'message' || eventType === 'conversation.message' || eventType.startsWith('runner.')) {
    if (
      eventType === 'conversation.message' ||
      eventType === 'runner.delta' ||
      eventType === 'runner.agent_message' ||
      eventType === 'runner.reasoning'
    ) {
      const messageEvent = normalizeQuestMessageEvent(update, questId, sessionId, eventId, timestamp, seq)
      return messageEvent ? [messageEvent] : []
    }
    if (eventType === 'runner.tool_call' || eventType === 'runner.tool_result') {
      const toolEvent = normalizeQuestToolEvent(update, questId, sessionId, eventId, timestamp, seq)
      return toolEvent ? [toolEvent] : []
    }
    const statusEvent = normalizeQuestStatusEvent(update, questId, sessionId, eventId, timestamp, seq)
    return statusEvent ? [statusEvent] : []
  }

  if (update.kind === 'artifact' || eventType === 'artifact.recorded' || eventType === 'quest.control') {
    const statusEvent = normalizeQuestStatusEvent(update, questId, sessionId, eventId, timestamp, seq)
    return statusEvent ? [statusEvent] : []
  }

  const statusEvent = normalizeQuestStatusEvent(update, questId, sessionId, eventId, timestamp, seq)
  return statusEvent ? [statusEvent] : []
}

function resolveMessagePreview(events: AgentSSEEvent[]) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index]
    if (event.event === 'message') {
      const data = event.data as MessageEventData
      const text =
        typeof data.content === 'string' && data.content.trim().length > 0
          ? data.content.trim()
          : typeof data.delta === 'string' && data.delta.trim().length > 0
            ? data.delta.trim()
            : ''
      if (text) {
        return {
          text,
          timestamp: typeof data.timestamp === 'number' ? data.timestamp : null,
        }
      }
    }
    if (event.event === 'status') {
      const data = event.data as StatusEventData
      const text =
        typeof data.message === 'string' && data.message.trim().length > 0
          ? data.message.trim()
          : typeof data.text === 'string' && data.text.trim().length > 0
            ? data.text.trim()
            : ''
      if (text) {
        return {
          text,
          timestamp: typeof data.timestamp === 'number' ? data.timestamp : null,
        }
      }
    }
  }
  return { text: null, timestamp: null }
}

function inferQuestSessionActive(snapshot: QuestSnapshot, events: AgentSSEEvent[]) {
  // Copilot quests deliberately park after creation and after user-approved stops.
  // Trust the snapshot over stale tail events so the UI doesn't show a fake running state.
  if (isCopilotSnapshotParkedForUser(snapshot)) return false
  if (snapshot.active_run_id) return true
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index]
    if (event.event === 'done' || event.event === 'wait' || event.event === 'error') return false
    if (event.event === 'tool') {
      const data = event.data as ToolEventData
      if (data.status === 'calling') return true
    }
    if (event.event === 'reasoning') {
      const data = event.data as ReasoningEventData
      if (data.status === 'in_progress') return true
    }
    if (event.event === 'message') {
      const data = event.data as MessageEventData
      if (data.role === 'assistant' && typeof data.delta === 'string' && data.delta.length > 0) {
        return true
      }
    }
  }
  return false
}

function inferQuestSessionStatus(snapshot: QuestSnapshot, events: AgentSSEEvent[]) {
  if (isCopilotSnapshotParkedForUser(snapshot)) {
    return events.length > 0 ? 'completed' : 'pending'
  }
  const active = inferQuestSessionActive(snapshot, events)
  if (active) return 'running'
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index]
    if (event.event === 'error') return 'failed'
    if (event.event === 'wait') return 'waiting'
    if (event.event === 'done') return 'completed'
  }
  const runtimeStatus = asString(snapshot.runtime_status) || asString(snapshot.status) || ''
  if (runtimeStatus === 'failed' || runtimeStatus === 'error') return 'failed'
  if (runtimeStatus === 'paused' || runtimeStatus === 'waiting') return 'waiting'
  if (runtimeStatus === 'running') return 'running'
  if (snapshot.stop_reason) return 'completed'
  return events.length > 0 ? 'completed' : 'pending'
}

async function fetchQuestSessionPayload(questId: string) {
  const response = await apiClient.get<SessionPayload>(`/api/quests/${questId}/session`, {
    timeout: QUEST_HEAVY_REQUEST_TIMEOUT_MS,
  })
  return response.data
}

async function fetchQuestEventEnvelope(
  questId: string,
  after: number
): Promise<FeedEnvelope> {
  const response = await apiClient.get<FeedEnvelope>(`/api/quests/${questId}/events`, {
    params: {
      after,
      limit: QUEST_HISTORY_PAGE_SIZE,
      format: 'acp',
      session_id: buildQuestSessionId(questId),
    },
    timeout: QUEST_HEAVY_REQUEST_TIMEOUT_MS,
  })
  return response.data
}

async function fetchQuestNormalizedEvents(
  questId: string,
  options?: { full?: boolean; limit?: number }
) {
  const full = options?.full === true
  const requestedLimit =
    typeof options?.limit === 'number' && Number.isFinite(options.limit) && options.limit > 0
      ? Math.floor(options.limit)
      : QUEST_DEFAULT_LIMIT
  const events: AgentSSEEvent[] = []
  let cursor = 0
  let batches = 0
  let hasMore = true

  while (hasMore && batches < QUEST_HISTORY_MAX_BATCHES) {
    const payload = await fetchQuestEventEnvelope(questId, cursor)
    const nextBatch = (payload.acp_updates ?? []).flatMap((item) => normalizeQuestAcpUpdateEnvelope(item))
    events.push(...nextBatch)
    if (!full && events.length > requestedLimit) {
      events.splice(0, events.length - requestedLimit)
    }
    cursor = typeof payload.cursor === 'number' ? payload.cursor : cursor
    hasMore = Boolean(payload.has_more)
    batches += 1
  }

  return {
    events,
    cursor,
    fetchedAll: !hasMore,
    requestedLimit,
  }
}

function buildQuestSessionLike(
  payload: SessionPayload,
  events: AgentSSEEvent[],
  options?: { full?: boolean; limit?: number; fetchedAll?: boolean }
): QuestSessionLike {
  const snapshot = payload.snapshot
  const status = inferQuestSessionStatus(snapshot, events)
  const isActive = inferQuestSessionActive(snapshot, events)
  const preview = resolveMessagePreview(events)
  const updatedAt = toUnixSeconds(snapshot.updated_at)
  const historyCount =
    typeof snapshot.history_count === 'number' && Number.isFinite(snapshot.history_count)
      ? snapshot.history_count
      : null
  const limit =
    typeof options?.limit === 'number' && Number.isFinite(options.limit) && options.limit > 0
      ? Math.floor(options.limit)
      : QUEST_DEFAULT_LIMIT
  return {
    session_id: buildQuestSessionId(payload.quest_id),
    status,
    title: asString(snapshot.title) || payload.quest_id,
    is_active: isActive,
    is_shared: false,
    latest_message:
      preview.text ||
      asString(asRecord(snapshot.summary)?.status_line) ||
      null,
    latest_message_at: preview.timestamp ?? updatedAt,
    updated_at: updatedAt,
    events,
    events_truncated:
      options?.full === true
        ? false
        : historyCount != null
          ? historyCount > events.length
          : !Boolean(options?.fetchedAll),
    event_limit: options?.full === true ? null : limit,
    plan_history: [],
    execution_target: 'sandbox',
    cli_server_id: null,
    session_metadata: {
      quest_id: payload.quest_id,
      quest_root: snapshot.quest_root,
      active_anchor: snapshot.active_anchor,
      runner: snapshot.runner,
      workspace_mode: snapshot.workspace_mode,
      continuation_policy:
        typeof (snapshot as Record<string, unknown>).continuation_policy === 'string'
          ? (snapshot as Record<string, unknown>).continuation_policy
          : null,
      active_run_id: snapshot.active_run_id,
      runtime_status: snapshot.runtime_status,
      stop_reason: snapshot.stop_reason,
      updated_at: snapshot.updated_at,
      bound_conversations: snapshot.bound_conversations,
    },
    agents: [
      {
        agent_id: 'deepscientist',
        agent_label: 'DeepScientist',
        agent_display_name: 'DeepScientist',
        agent_source: snapshot.runner ?? 'codex',
        agent_engine: snapshot.runner ?? 'codex',
      },
    ],
    event_metadata_mode: 'full',
  }
}

export function isQuestSessionId(sessionId?: string | null): boolean {
  return typeof sessionId === 'string' && sessionId.startsWith(QUEST_SESSION_PREFIX)
}

export function getQuestIdFromSessionId(sessionId?: string | null): string | null {
  if (!isQuestSessionId(sessionId)) return null
  const questId = sessionId.slice(QUEST_SESSION_PREFIX.length).trim()
  return questId || null
}

export async function shouldUseQuestSessionCompat(projectId?: string | null) {
  if (!projectId || projectId.trim().length === 0) return false
  if (isQuestRuntimeSurface()) return true
  return shouldUseQuestProject(projectId)
}

export async function createQuestSession(projectId: string): Promise<QuestSessionLike> {
  const payload = await fetchQuestSessionPayload(projectId)
  return buildQuestSessionLike(payload, [], { limit: QUEST_DEFAULT_LIMIT, fetchedAll: false })
}

export async function getQuestSession(
  sessionId: string,
  options?: { full?: boolean; limit?: number }
): Promise<QuestSessionLike> {
  const questId = getQuestIdFromSessionId(sessionId)
  if (!questId) {
    throw new Error(`Invalid quest session id: ${sessionId}`)
  }
  const [payload, history] = await Promise.all([
    fetchQuestSessionPayload(questId),
    fetchQuestNormalizedEvents(questId, options),
  ])
  return buildQuestSessionLike(payload, history.events, {
    full: options?.full,
    limit: history.requestedLimit,
    fetchedAll: history.fetchedAll,
  })
}

export async function getQuestSessionEventsOnly(
  sessionId: string,
  options?: { full?: boolean; limit?: number }
): Promise<AgentSSEEvent[]> {
  const questId = getQuestIdFromSessionId(sessionId)
  if (!questId) {
    throw new Error(`Invalid quest session id: ${sessionId}`)
  }
  const history = await fetchQuestNormalizedEvents(questId, options)
  return history.events
}

export async function getQuestLatestSession(
  projectId: string,
  limit?: number
): Promise<QuestSessionLike> {
  const payload = await fetchQuestSessionPayload(projectId)
  const history = await fetchQuestNormalizedEvents(projectId, { limit })
  return buildQuestSessionLike(payload, history.events, {
    limit: history.requestedLimit,
    fetchedAll: history.fetchedAll,
  })
}

export async function listQuestSessionSummaries(projectId: string) {
  const latest = await getQuestLatestSession(projectId, 80)
  return {
    sessions: [
      {
        session_id: latest.session_id,
        status: latest.status ?? null,
        title: latest.title ?? null,
        latest_message: latest.latest_message ?? null,
        latest_message_at: latest.latest_message_at ?? null,
        updated_at: latest.updated_at ?? null,
        is_shared: false,
        is_active: latest.is_active ?? false,
        agent_engine:
          typeof latest.session_metadata?.runner === 'string'
            ? latest.session_metadata.runner
            : 'codex',
        execution_target: 'sandbox',
        cli_server_id: null,
      },
    ],
  }
}

export function buildQuestStreamUrl(questId: string) {
  const params = new URLSearchParams({
    format: 'acp',
    session_id: buildQuestSessionId(questId),
    stream: '1',
  })
  return `${getApiBaseUrl()}/api/quests/${questId}/events?${params.toString()}`
}

export function resolveQuestResumeToken(events: AgentSSEEvent[]): string | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index]
    const seq = (event.data as { seq?: unknown } | undefined)?.seq
    if (typeof seq === 'number' && Number.isFinite(seq)) {
      return String(seq)
    }
  }
  return null
}
