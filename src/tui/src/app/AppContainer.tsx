import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import fs from 'node:fs'
import { useApp, useInput } from 'ink'
import { spawn } from 'node:child_process'

import type {
  ConfigPanel,
  ConfigRootEntry,
  ConfigScreenItem,
  ConnectorDetailItem,
  ConnectorFieldKind,
  ConnectorGuideSection,
  ConnectorMenuEntry,
} from '../components/ConfigScreen.js'
import { client } from '../lib/api.js'
import {
  CONNECTOR_ORDER,
  connectorLabel,
  connectorSubtitle,
  createLingzhuAk,
  looksLikeWeixinQrImageUrl,
  resolveLingzhuAuthAk,
  supportsGuidedConnector,
  type ManagedConnectorName,
} from '../lib/connectorConfig.js'
import {
  connectorTargetLabel,
  normalizeConnectorTargets,
  qqProfileDisplayLabel,
  qqProfileStatus,
  selectQqProfileTarget,
} from '../lib/connectors.js'
import { renderQrAscii } from '../lib/qr.js'
import { buildToolOperationContent, extractToolSubject } from '../lib/toolOperations.js'
import { DefaultAppLayout } from '../layouts/DefaultAppLayout.js'
import type {
  ConfigFileEntry,
  ConnectorSnapshot,
  ConnectorTargetSnapshot,
  FeedItem,
  OpenDocumentPayload,
  QuestSummary,
  SessionPayload,
} from '../types.js'

type QuestPanelMode = 'projects' | 'pause' | 'stop' | 'resume'
type ConfigMode = 'browse' | 'edit'
type ConfigView = 'root' | 'files' | 'connector-list' | 'connector-detail' | 'weixin-qr'
type MessageFeedItem = Extract<FeedItem, { type: 'message' }>
type ConfigEditState =
  | {
      kind: 'document'
      item: ConfigScreenItem
      revision?: string
      content: string
    }
  | {
      kind: 'connector-field'
      connectorName: ManagedConnectorName
      fieldKey: string
      fieldLabel: string
      description: string
      fieldKind: Exclude<ConnectorFieldKind, 'boolean'>
      content: string
    }
type ConnectorsDocumentState = {
  item: ConfigScreenItem
  revision?: string
  savedStructured: Record<string, unknown>
  structured: Record<string, unknown>
}

type QqProfileStateSummary = {
  profileId: string
  label: string
  appId: string
  mainChatId: string
  lastConversationId: string
  targetCount: number
  selectedTarget: ConnectorTargetSnapshot | null
  status: 'waiting' | 'ready' | 'bound'
}

const LOCAL_USER_SOURCE = 'tui-local'
const CONFIG_ROOT_ENTRIES: ConfigRootEntry[] = [
  {
    id: 'connectors',
    title: 'Connectors',
    description: 'Choose QQ, Weixin, Lingzhu, or another connector and configure it with arrows plus Enter.',
  },
  {
    id: 'global-files',
    title: 'Global Config Files',
    description: 'Open raw runtime config files such as config.yaml, runners.yaml, and connectors.yaml.',
  },
  {
    id: 'quest-files',
    title: 'Current Quest Files',
    description: 'Open quest-local config files for the currently selected quest.',
  },
]

const buildId = (prefix: string, raw: string) => `${prefix}:${raw}`

const stringifyStructured = (value: unknown) => {
  if (typeof value === 'string') {
    return value
  }
  if (value == null) {
    return undefined
  }
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

const parseSlashCommand = (text: string): { name: string; arg: string } | null => {
  const trimmed = text.trim()
  if (!trimmed.startsWith('/')) {
    return null
  }
  const firstSpace = trimmed.indexOf(' ')
  if (firstSpace === -1) {
    return { name: trimmed.toLowerCase(), arg: '' }
  }
  return {
    name: trimmed.slice(0, firstSpace).toLowerCase(),
    arg: trimmed.slice(firstSpace + 1).trim(),
  }
}

const getPanelQuests = (mode: QuestPanelMode, quests: QuestSummary[]): QuestSummary[] => {
  if (mode === 'pause') {
    return quests.filter((quest) => !['stopped', 'paused'].includes(String(quest.status || '')))
  }
  if (mode === 'stop') {
    return quests.filter((quest) => !['stopped'].includes(String(quest.status || '')))
  }
  if (mode === 'resume') {
    return quests.filter((quest) => ['stopped', 'paused'].includes(String(quest.status || '')))
  }
  return quests
}

const resolveQuestToken = (token: string, quests: QuestSummary[]): QuestSummary | null => {
  const trimmed = token.trim()
  if (!trimmed) {
    return null
  }
  const numeric = Number(trimmed)
  if (Number.isInteger(numeric) && numeric > 0) {
    return quests[numeric - 1] ?? null
  }
  return quests.find((quest) => quest.quest_id === trimmed) ?? null
}

const buildQuestConfigItems = (
  questId: string | null,
  questRoot: string | undefined
): ConfigScreenItem[] => {
  if (!questId || !questRoot) {
    return []
  }
  const items: ConfigScreenItem[] = [
    {
      id: `quest:${questId}:quest.yaml`,
      scope: 'quest',
      name: 'quest.yaml',
      title: 'quest.yaml',
      path: `${questRoot}/quest.yaml`,
      writable: true,
      documentId: 'path::quest.yaml',
    },
  ]
  const codexPath = `${questRoot}/.codex/config.toml`
  if (fs.existsSync(codexPath)) {
    items.push({
      id: `quest:${questId}:.codex/config.toml`,
      scope: 'quest',
      name: '.codex/config.toml',
      title: '.codex/config.toml',
      path: codexPath,
      writable: true,
      documentId: 'path::.codex/config.toml',
    })
  }
  return items
}

const buildGlobalConfigItems = (entries: ConfigFileEntry[]): ConfigScreenItem[] =>
  entries.map((entry) => ({
    id: `global:${entry.name}`,
    scope: 'global',
    name: entry.name,
    title: `${entry.name}.yaml`,
    path: entry.path,
    writable: true,
    configName: entry.name,
  }))

const resolveConfigTarget = (token: string, items: ConfigScreenItem[]): ConfigScreenItem | null => {
  const trimmed = token.trim()
  if (!trimmed) {
    return null
  }
  const numeric = Number(trimmed)
  if (Number.isInteger(numeric) && numeric > 0) {
    return items[numeric - 1] ?? null
  }
  return (
    items.find((item) => item.name === trimmed || item.title === trimmed || item.configName === trimmed) ?? null
  )
}

const resolveManagedConnectorName = (token: string): ManagedConnectorName | null => {
  const normalized = String(token || '').trim().toLowerCase()
  if (!normalized) {
    return null
  }
  if (CONNECTOR_ORDER.includes(normalized as ManagedConnectorName)) {
    return normalized as ManagedConnectorName
  }
  if (normalized === 'wechat') {
    return 'weixin'
  }
  return null
}

const connectorNamesFromStructuredConfig = (structured: Record<string, unknown> | null): ManagedConnectorName[] => {
  const known = new Set<ManagedConnectorName>()
  for (const name of CONNECTOR_ORDER) {
    if (structured && typeof structured[name] === 'object') {
      known.add(name)
    }
  }
  return CONNECTOR_ORDER.filter((name) => known.has(name))
}

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}

const cloneStructured = (value: Record<string, unknown>): Record<string, unknown> => {
  try {
    return JSON.parse(JSON.stringify(value)) as Record<string, unknown>
  } catch {
    return { ...value }
  }
}

const displayBoolean = (value: unknown): string => (Boolean(value) ? 'on' : 'off')

const displayMaybeString = (value: unknown): string => {
  const text = String(value ?? '').trim()
  return text || '—'
}

const CONNECTOR_BIND_ACTION_PREFIX = 'bind-target:'
const CONNECTOR_UNBIND_ACTION_PREFIX = 'unbind-target:'
const LINGZHU_PUBLIC_AGENT_ID = 'DeepScientist'
const LINGZHU_PLATFORM_AGENT_NAME = 'DeepScientist'
const LINGZHU_PLATFORM_CATEGORY = 'Work'
const LINGZHU_PLATFORM_INPUT_TYPE = 'Text'
const LINGZHU_PLATFORM_CAPABILITY_SUMMARY =
  'DeepScientist is a local-first research agent for planning, experiments, analysis, writing, and execution follow-up.'
const LINGZHU_PLATFORM_OPENING_MESSAGE =
  'Hello, I am DeepScientist. Tell me the research goal, experiment question, or task you want to move forward.'
const LINGZHU_PLATFORM_LOGO_PATH = '/assets/branding/logo-rokid.png'

const normalizedText = (value: unknown) => String(value ?? '').trim()

const normalizeBaseUrl = (value: unknown) => {
  const text = normalizedText(value)
  return text ? text.replace(/\/+$/, '') : ''
}

const looksLikePublicBaseUrl = (value: unknown) => {
  const text = normalizeBaseUrl(value)
  if (!text) {
    return false
  }
  try {
    const url = new URL(text)
    if (!['http:', 'https:'].includes(url.protocol)) {
      return false
    }
    const host = url.hostname.trim().toLowerCase()
    if (!host || ['localhost', '0.0.0.0', '127.0.0.1', '::1'].includes(host) || host.endsWith('.local')) {
      return false
    }
    if (/^10\./.test(host) || /^192\.168\./.test(host) || /^172\.(1[6-9]|2\d|3[0-1])\./.test(host)) {
      return false
    }
    return true
  } catch {
    return false
  }
}

const lingzhuPublicSseUrl = (config: Record<string, unknown>, details: Record<string, unknown>) => {
  const detailValue = normalizeBaseUrl(details.public_endpoint_url)
  if (detailValue) {
    return detailValue
  }
  const base = normalizeBaseUrl(config.public_base_url)
  return base ? `${base}/metis/agent/api/sse` : ''
}

const lingzhuPublicHealthUrl = (config: Record<string, unknown>, details: Record<string, unknown>) => {
  const detailValue = normalizeBaseUrl(details.public_health_url)
  if (detailValue) {
    return detailValue
  }
  const base = normalizeBaseUrl(config.public_base_url)
  return base ? `${base}/metis/agent/api/health` : ''
}

const lingzhuPlatformLogoUrl = (baseUrl: string) => {
  try {
    const url = new URL(baseUrl)
    if (url.hostname === '0.0.0.0') {
      url.hostname = '127.0.0.1'
    }
    return new URL(LINGZHU_PLATFORM_LOGO_PATH, url.origin).toString()
  } catch {
    return LINGZHU_PLATFORM_LOGO_PATH
  }
}

const buildConnectorBindActionId = (connectorName: string, conversationId: string) =>
  `${CONNECTOR_BIND_ACTION_PREFIX}${connectorName}:${encodeURIComponent(conversationId)}`

const parseConnectorBindActionId = (actionId: string) => {
  if (!actionId.startsWith(CONNECTOR_BIND_ACTION_PREFIX)) {
    return null
  }
  const payload = actionId.slice(CONNECTOR_BIND_ACTION_PREFIX.length)
  const separator = payload.indexOf(':')
  if (separator < 0) {
    return null
  }
  return {
    connectorName: payload.slice(0, separator),
    conversationId: decodeURIComponent(payload.slice(separator + 1)),
  }
}

const buildConnectorUnbindActionId = (connectorName: string) => `${CONNECTOR_UNBIND_ACTION_PREFIX}${connectorName}`

const parseConnectorUnbindActionId = (actionId: string) => {
  if (!actionId.startsWith(CONNECTOR_UNBIND_ACTION_PREFIX)) {
    return null
  }
  const connectorName = actionId.slice(CONNECTOR_UNBIND_ACTION_PREFIX.length).trim()
  return connectorName ? connectorName : null
}

function normalizeUpdate(raw: Record<string, unknown>): FeedItem {
  const eventType = String(raw.event_type ?? '')
  const data = (raw.data ?? {}) as Record<string, unknown>
  const toolLabel =
    eventType === 'runner.tool_call' || data.label === 'tool_call'
      ? 'tool_call'
      : eventType === 'runner.tool_result' || data.label === 'tool_result'
        ? 'tool_result'
        : null
  if (toolLabel) {
    const toolName = typeof data.tool_name === 'string' ? data.tool_name : undefined
    const args = stringifyStructured(data.args)
    const output = stringifyStructured(data.output)
    const subject = extractToolSubject(toolName, args, output)
    const metadata =
      data.metadata && typeof data.metadata === 'object' && !Array.isArray(data.metadata)
        ? (data.metadata as Record<string, unknown>)
        : undefined
    return {
      id: buildId('operation', String(raw.event_id ?? raw.created_at ?? crypto.randomUUID())),
      type: 'operation',
      label: toolLabel,
      content: buildToolOperationContent(toolLabel, toolName, args, output),
      toolName,
      toolCallId: typeof data.tool_call_id === 'string' ? data.tool_call_id : undefined,
      status: typeof data.status === 'string' ? data.status : undefined,
      subject,
      args,
      output,
      mcpServer: typeof data.mcp_server === 'string' ? data.mcp_server : undefined,
      mcpTool: typeof data.mcp_tool === 'string' ? data.mcp_tool : undefined,
      metadata,
      createdAt: raw.created_at ? String(raw.created_at) : undefined,
    }
  }
  const kind = String(raw.kind ?? 'event')
  if (kind === 'message') {
    const message = (raw.message ?? {}) as Record<string, unknown>
    return {
      id: buildId('message', String(raw.event_id ?? raw.created_at ?? crypto.randomUUID())),
      type: 'message',
      role: String(message.role ?? 'assistant') === 'user' ? 'user' : 'assistant',
      content: String(message.content ?? ''),
      source: message.source ? String(message.source) : undefined,
      createdAt: raw.created_at ? String(raw.created_at) : undefined,
      stream: Boolean(message.stream),
      runId: message.run_id ? String(message.run_id) : null,
      skillId: message.skill_id ? String(message.skill_id) : null,
    }
  }
  if (kind === 'artifact') {
    const artifact = (raw.artifact ?? {}) as Record<string, unknown>
    return {
      id: buildId('artifact', String(raw.event_id ?? raw.created_at ?? crypto.randomUUID())),
      type: 'artifact',
      artifactId: artifact.artifact_id ? String(artifact.artifact_id) : undefined,
      kind: String(artifact.kind ?? 'artifact'),
      status: artifact.status ? String(artifact.status) : undefined,
      content: String(artifact.summary ?? artifact.reason ?? artifact.guidance ?? artifact.kind ?? 'Artifact updated.'),
      reason: artifact.reason ? String(artifact.reason) : undefined,
      guidance: artifact.guidance ? String(artifact.guidance) : undefined,
      createdAt: raw.created_at ? String(raw.created_at) : undefined,
      paths: (artifact.paths as Record<string, string> | undefined) ?? {},
      artifactPath: artifact.artifact_path ? String(artifact.artifact_path) : undefined,
      workspaceRoot: artifact.workspace_root ? String(artifact.workspace_root) : undefined,
      branch: artifact.branch ? String(artifact.branch) : undefined,
      headCommit: artifact.head_commit ? String(artifact.head_commit) : undefined,
      flowType: artifact.flow_type ? String(artifact.flow_type) : undefined,
      protocolStep: artifact.protocol_step ? String(artifact.protocol_step) : undefined,
      ideaId: artifact.idea_id ? String(artifact.idea_id) : null,
      campaignId: artifact.campaign_id ? String(artifact.campaign_id) : null,
      sliceId: artifact.slice_id ? String(artifact.slice_id) : null,
      details:
        artifact.details && typeof artifact.details === 'object' && !Array.isArray(artifact.details)
          ? (artifact.details as Record<string, unknown>)
          : undefined,
      checkpoint:
        artifact.checkpoint && typeof artifact.checkpoint === 'object' && !Array.isArray(artifact.checkpoint)
          ? (artifact.checkpoint as Record<string, unknown>)
          : null,
      attachments: Array.isArray(artifact.attachments)
        ? (artifact.attachments.filter(
            (item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item)
          ) as Array<Record<string, unknown>>)
        : [],
    }
  }
  return {
    id: buildId('event', String(raw.event_id ?? raw.created_at ?? crypto.randomUUID())),
    type: 'event',
    label: String(data.label ?? raw.event_type ?? 'event'),
    content: String(data.summary ?? data.run_id ?? raw.event_type ?? 'Event updated.'),
    createdAt: raw.created_at ? String(raw.created_at) : undefined,
  }
}

type FeedState = {
  history: FeedItem[]
  pending: FeedItem[]
}

function appendHistoryItem(history: FeedItem[], item: FeedItem): FeedItem[] {
  if (history.some((existing) => existing.id === item.id)) {
    return history
  }
  return [...history, item].slice(-160)
}

function removeMatchingLocalPendingUser(pending: FeedItem[], item: MessageFeedItem): FeedItem[] {
  if (item.role !== 'user') {
    return pending
  }
  let removed = false
  return pending.filter((candidate) => {
    if (removed) {
      return true
    }
    if (
      candidate.type === 'message' &&
      candidate.role === 'user' &&
      candidate.source === LOCAL_USER_SOURCE &&
      candidate.content === item.content
    ) {
      removed = true
      return false
    }
    return true
  })
}

function upsertPendingAssistant(pending: FeedItem[], item: MessageFeedItem): FeedItem[] {
  const next = [...pending]
  const matchIndex = next.findIndex(
    (candidate) =>
      candidate.type === 'message' &&
      candidate.role === 'assistant' &&
      candidate.stream &&
      candidate.runId &&
      candidate.runId === item.runId
  )
  if (matchIndex >= 0) {
    const current = next[matchIndex]
    if (current.type === 'message') {
      next[matchIndex] = {
        ...current,
        content: `${current.content}${item.content}`,
        createdAt: item.createdAt || current.createdAt,
        skillId: item.skillId || current.skillId,
        source: item.source || current.source,
      }
    }
    return next.slice(-12)
  }
  return [...next, item].slice(-12)
}

function flushPendingAssistant(
  pending: FeedItem[],
  item: MessageFeedItem
): { pending: FeedItem[]; finalized: MessageFeedItem } {
  if (item.role !== 'assistant' || !item.runId) {
    return { pending, finalized: item }
  }
  let pendingText = ''
  const nextPending = pending.filter((candidate) => {
    if (
      candidate.type === 'message' &&
      candidate.role === 'assistant' &&
      candidate.runId &&
      candidate.runId === item.runId
    ) {
      pendingText = candidate.content
      return false
    }
    return true
  })
  return {
    pending: nextPending,
    finalized: item.content
      ? item
      : {
          ...item,
          content: pendingText,
        },
  }
}

function applyIncomingFeedUpdates(state: FeedState, incoming: FeedItem[]): FeedState {
  let nextHistory = [...state.history]
  let nextPending = [...state.pending]
  for (const item of incoming) {
    if (item.type === 'message' && item.role === 'assistant' && item.stream) {
      nextPending = upsertPendingAssistant(nextPending, item)
      continue
    }
    if (item.type === 'message' && item.role === 'assistant' && item.runId) {
      const flushed = flushPendingAssistant(nextPending, item)
      nextPending = flushed.pending
      nextHistory = appendHistoryItem(nextHistory, flushed.finalized)
      continue
    }
    if (item.type === 'message' && item.role === 'user') {
      nextPending = removeMatchingLocalPendingUser(nextPending, item)
      nextHistory = appendHistoryItem(nextHistory, item)
      continue
    }
    nextHistory = appendHistoryItem(nextHistory, item)
  }
  return {
    history: nextHistory,
    pending: nextPending,
  }
}

function createLocalUserFeedItem(content: string): FeedItem {
  return {
    id: buildId('local-user', `${Date.now()}-${crypto.randomUUID()}`),
    type: 'message',
    role: 'user',
    content,
    source: LOCAL_USER_SOURCE,
    createdAt: new Date().toISOString(),
  }
}

function shouldRefreshForUpdate(raw: Record<string, unknown>): boolean {
  const eventType = String(raw.event_type ?? '')
  if (
    eventType === 'runner.turn_finish' ||
    eventType === 'runner.turn_error' ||
    eventType === 'runner.turn_retry_started' ||
    eventType === 'runner.turn_retry_scheduled' ||
    eventType === 'runner.turn_retry_aborted' ||
    eventType === 'runner.turn_retry_exhausted' ||
    eventType === 'quest.control'
  ) {
    return true
  }
  if (String(raw.kind ?? '') !== 'artifact') {
    return false
  }
  const artifact = (raw.artifact ?? {}) as Record<string, unknown>
  return (
    Boolean(artifact.expects_reply) ||
    ['threaded', 'blocking'].includes(String(artifact.reply_mode ?? '')) ||
    Boolean(artifact.reply_to_interaction_id) ||
    String(artifact.kind ?? '') === 'decision_request'
  )
}

function openBrowser(url: string) {
  const platform = process.platform
  if (platform === 'darwin') {
    spawn('open', [url], { detached: true, stdio: 'ignore' }).unref()
    return
  }
  if (platform === 'win32') {
    spawn('cmd', ['/c', 'start', '', url], { detached: true, stdio: 'ignore' }).unref()
    return
  }
  spawn('xdg-open', [url], { detached: true, stdio: 'ignore' }).unref()
}

function buildProjectsUrl(baseUrl: string, authToken?: string | null) {
  const target = new URL(baseUrl)
  if (target.hostname === '0.0.0.0') {
    target.hostname = '127.0.0.1'
  }
  target.pathname = '/projects'
  target.search = ''
  if (authToken) {
    target.searchParams.set('token', authToken)
  }
  return target.toString()
}

function buildProjectUrl(baseUrl: string, questId: string | null, authToken?: string | null) {
  if (!questId) {
    return buildProjectsUrl(baseUrl, authToken)
  }
  const target = new URL(baseUrl)
  if (target.hostname === '0.0.0.0') {
    target.hostname = '127.0.0.1'
  }
  target.pathname = `/projects/${questId}`
  target.search = ''
  if (authToken) {
    target.searchParams.set('token', authToken)
  }
  return target.toString()
}

export const AppContainer: React.FC<{ baseUrl: string; initialQuestId?: string | null; authToken?: string | null }> = ({
  baseUrl,
  initialQuestId = null,
  authToken = null,
}) => {
  const { exit } = useApp()
  const [quests, setQuests] = useState<QuestSummary[]>([])
  const [connectors, setConnectors] = useState<ConnectorSnapshot[]>([])
  const [activeQuestId, setActiveQuestId] = useState<string | null>(initialQuestId)
  const [browseQuestId, setBrowseQuestId] = useState<string | null>(initialQuestId)
  const [configView, setConfigView] = useState<ConfigView | null>(null)
  const [configItems, setConfigItems] = useState<ConfigScreenItem[]>([])
  const [configIndex, setConfigIndex] = useState(0)
  const [configSectionTitle, setConfigSectionTitle] = useState('Config')
  const [configSectionDescription, setConfigSectionDescription] = useState('')
  const [configEditor, setConfigEditor] = useState<ConfigEditState | null>(null)
  const [connectorsDocument, setConnectorsDocument] = useState<ConnectorsDocumentState | null>(null)
  const [selectedConnectorName, setSelectedConnectorName] = useState<ManagedConnectorName | null>(null)
  const [weixinQrState, setWeixinQrState] = useState<{
    sessionKey: string
    status: string
    qrContent?: string
    qrUrl?: string
    qrAscii?: string
    message?: string
  } | null>(null)
  const [questPanelMode, setQuestPanelMode] = useState<QuestPanelMode | null>(null)
  const [questPanelIndex, setQuestPanelIndex] = useState(0)
  const [session, setSession] = useState<SessionPayload | null>(null)
  const [history, setHistory] = useState<FeedItem[]>([])
  const [pendingHistoryItems, setPendingHistoryItems] = useState<FeedItem[]>([])
  const [cursor, setCursor] = useState(0)
  const [input, setInput] = useState('')
  const [statusLine, setStatusLine] = useState('Connecting to daemon…')
  const [connectionState, setConnectionState] = useState<'connecting' | 'connected' | 'error'>('connecting')
  const activeQuestIdRef = useRef<string | null>(initialQuestId)
  const browseQuestIdRef = useRef<string | null>(initialQuestId)
  const historyRef = useRef<FeedItem[]>([])
  const pendingHistoryItemsRef = useRef<FeedItem[]>([])
  const cursorRef = useRef(0)
  const refreshRequestRef = useRef(0)
  const streamAbortRef = useRef<AbortController | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const activeQuest = useMemo(
    () => quests.find((quest) => quest.quest_id === activeQuestId) ?? null,
    [quests, activeQuestId]
  )
  const browseQuest = useMemo(
    () => quests.find((quest) => quest.quest_id === browseQuestId) ?? null,
    [quests, browseQuestId]
  )
  const panelQuests = useMemo(
    () => (questPanelMode ? getPanelQuests(questPanelMode, quests) : []),
    [questPanelMode, quests]
  )
  const configMode = useMemo<ConfigMode | null>(
    () => (configView ? (configEditor ? 'edit' : 'browse') : null),
    [configEditor, configView]
  )
  const selectedQuestForConfig = useMemo(
    () => activeQuest ?? browseQuest ?? null,
    [activeQuest, browseQuest]
  )
  const selectedConnectorSnapshot = useMemo(
    () =>
      selectedConnectorName
        ? connectors.find((item) => String(item.name || '').trim().toLowerCase() === selectedConnectorName) ?? null
        : null,
    [connectors, selectedConnectorName]
  )
  const selectedConnectorConfig = useMemo(
    () => (selectedConnectorName ? asRecord(connectorsDocument?.structured?.[selectedConnectorName]) : {}),
    [connectorsDocument?.structured, selectedConnectorName]
  )
  const connectorMenuEntries = useMemo<ConnectorMenuEntry[]>(() => {
    const configuredNames = connectorNamesFromStructuredConfig(connectorsDocument?.structured ?? null)
    const names = configuredNames.length > 0 ? configuredNames : CONNECTOR_ORDER
    return names.map((name) => {
      const snapshot =
        connectors.find((item) => String(item.name || '').trim().toLowerCase() === name) ?? null
      return {
        name,
        label: connectorLabel(name),
        subtitle: connectorSubtitle(name),
        enabled: snapshot?.enabled !== false && Boolean(snapshot?.enabled || asRecord(connectorsDocument?.structured?.[name]).enabled),
        connectionState: snapshot?.connection_state || snapshot?.auth_state || 'idle',
        bindingCount: snapshot?.binding_count,
        targetCount: snapshot?.target_count,
        supportMode: supportsGuidedConnector(name) ? 'guided' : 'raw',
      }
    })
  }, [connectors, connectorsDocument?.structured])
  const qqHasMultipleProfiles = useMemo(() => {
    const profiles = selectedConnectorName === 'qq' ? selectedConnectorConfig.profiles : null
    return Array.isArray(profiles) && profiles.length > 1
  }, [selectedConnectorConfig, selectedConnectorName])
  const selectedConnectorTargets = useMemo<ConnectorTargetSnapshot[]>(
    () => (selectedConnectorSnapshot ? normalizeConnectorTargets(selectedConnectorSnapshot) : []),
    [selectedConnectorSnapshot]
  )
  const qqProfileSummaries = useMemo<QqProfileStateSummary[]>(() => {
    if (selectedConnectorName !== 'qq') {
      return []
    }
    const configuredProfiles = Array.isArray(selectedConnectorConfig.profiles)
      ? selectedConnectorConfig.profiles
          .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item))
          .map((item) => asRecord(item))
      : []
    const runtimeProfiles = Array.isArray(selectedConnectorSnapshot?.profiles) ? selectedConnectorSnapshot.profiles : []
    const runtimeById = new Map(runtimeProfiles.map((profile) => [normalizedText(profile.profile_id), profile]))
    const totalProfiles = configuredProfiles.length
    return configuredProfiles.map((profile, index) => {
      const profileId = normalizedText(profile.profile_id || `qq-profile-${index + 1}`)
      const runtime = runtimeById.get(profileId)
      const profileTargets = selectedConnectorTargets.filter((target) => {
        const targetProfileId = normalizedText(target.profile_id)
        if (targetProfileId) {
          return targetProfileId === profileId
        }
        return totalProfiles === 1
      })
      const mainChatId = normalizedText(profile.main_chat_id || runtime?.main_chat_id)
      const selectedTarget = selectQqProfileTarget(profileTargets, mainChatId)
      return {
        profileId,
        label: qqProfileDisplayLabel(
          {
            profile_id: profileId,
            bot_name: normalizedText(profile.bot_name) || undefined,
            app_id: normalizedText(profile.app_id) || undefined,
          },
          runtime ?? null
        ),
        appId: normalizedText(profile.app_id || runtime?.app_id),
        mainChatId,
        lastConversationId: normalizedText(runtime?.last_conversation_id),
        targetCount: profileTargets.length,
        selectedTarget,
        status: qqProfileStatus(runtime ?? null, profileTargets, mainChatId),
      }
    })
  }, [selectedConnectorConfig.profiles, selectedConnectorName, selectedConnectorSnapshot?.profiles, selectedConnectorTargets])
  const connectorContextLine = useMemo(() => {
    if (selectedQuestForConfig?.quest_id) {
      return `Current quest for binding: ${selectedQuestForConfig.quest_id}`
    }
    return 'No active quest selected yet. You can still save connector settings.'
  }, [selectedQuestForConfig?.quest_id])
  const connectorGuideSections = useMemo<ConnectorGuideSection[]>(() => {
    if (!selectedConnectorName) {
      return []
    }

    if (selectedConnectorName === 'weixin') {
      const accountId = normalizedText(selectedConnectorConfig.account_id || selectedConnectorSnapshot?.details?.account_id)
      const loginUserId = normalizedText(selectedConnectorConfig.login_user_id)
      const hasBinding = Boolean(accountId)
      return [
        {
          id: 'weixin-flow',
          title: 'Top Guide',
          tone: hasBinding ? 'success' : 'info',
          lines: [
            '1. Choose Bind/Rebind Weixin to create a QR code inside TUI.',
            '2. Scan the QR code with the WeChat app on the phone that owns this account, then confirm the login in WeChat.',
            '3. DeepScientist saves the binding automatically and returns here after confirmation.',
          ],
        },
        {
          id: 'weixin-status',
          title: 'Current Status',
          tone: hasBinding ? 'success' : 'warning',
          lines: [
            `Bot account: ${accountId || 'not bound yet'}`,
            `Owner account: ${loginUserId || 'not bound yet'}`,
            `Known targets: ${selectedConnectorTargets.length || selectedConnectorSnapshot?.target_count || 0}`,
          ],
        },
      ]
    }

    if (selectedConnectorName === 'lingzhu') {
      const details = asRecord(selectedConnectorSnapshot?.details)
      const authAk = normalizedText(resolveLingzhuAuthAk(selectedConnectorConfig.auth_ak))
      const publicBaseUrl = normalizeBaseUrl(selectedConnectorConfig.public_base_url)
      const publicSseUrl = normalizedText(lingzhuPublicSseUrl(selectedConnectorConfig, details))
      const publicReady = looksLikePublicBaseUrl(publicBaseUrl)
      const tone = publicReady && authAk ? 'success' : 'warning'
      return [
        {
          id: 'lingzhu-flow',
          title: 'Top Guide',
          tone,
          lines: [
            '1. Set Public base URL to the final public DeepScientist origin before binding a real Rokid device.',
            '2. Copy the generated Rokid fields below into the platform exactly as shown, including Custom agent ID, URL, AK, Agent name, Category, Capability summary, Opening message, and Input type.',
            '3. After the Rokid form is filled on the platform, return here and run Save Connector.',
          ],
        },
        {
          id: 'lingzhu-platform',
          title: 'Generated For Rokid',
          tone,
          lines: [
            `Custom agent ID: ${normalizedText(selectedConnectorConfig.agent_id || LINGZHU_PUBLIC_AGENT_ID) || LINGZHU_PUBLIC_AGENT_ID}`,
            `Custom agent URL: ${publicSseUrl || 'set Public base URL first'}`,
            `Custom agent AK: ${authAk || 'generate or fill Custom agent AK first'}`,
            `Agent name: ${LINGZHU_PLATFORM_AGENT_NAME}`,
            `Category: ${LINGZHU_PLATFORM_CATEGORY}`,
            `Capability summary: ${LINGZHU_PLATFORM_CAPABILITY_SUMMARY}`,
            `Opening message: ${LINGZHU_PLATFORM_OPENING_MESSAGE}`,
            `Input type: ${LINGZHU_PLATFORM_INPUT_TYPE}`,
          ],
        },
        ...(publicReady
          ? []
          : [
              {
                id: 'lingzhu-warning',
                title: 'Public URL Required',
                tone: 'warning' as const,
                lines: ['The current Public base URL is not a public HTTP(S) address yet, so Rokid devices will not be able to reach this bridge.'],
              },
            ]),
      ]
    }

    if (selectedConnectorName === 'qq') {
      const detectedOpenId = normalizedText(selectedConnectorConfig.main_chat_id || selectedConnectorSnapshot?.main_chat_id)
      const lastConversationId = normalizedText(selectedConnectorSnapshot?.last_conversation_id)
      const hasCredentials = Boolean(normalizedText(selectedConnectorConfig.app_id) && normalizedText(selectedConnectorConfig.app_secret))
      const hasDetectedTarget = Boolean(detectedOpenId || selectedConnectorTargets.length)
      const tone = hasDetectedTarget ? 'success' : hasCredentials ? 'warning' : 'info'
      return [
        {
          id: 'qq-flow',
          title: 'Top Guide',
          tone,
          lines: [
            '1. Create the bot in the official QQ Bot Platform and copy App ID plus App Secret.',
            qqHasMultipleProfiles
              ? '2. Multiple QQ profiles are configured. The TUI shows each profile status below, and you can still bind runtime targets here. Use raw connectors.yaml only for adding, deleting, or replacing profile credentials.'
              : '2. Fill Bot name, App ID, and App Secret below, then run Save Connector.',
            hasDetectedTarget
              ? '3. OpenID and conversation targets are already visible below. Bind the current quest to the correct target.'
              : '3. After saving, send one private QQ message to the bot. TUI auto-refreshes Detected OpenID and conversation_id from runtime activity.',
          ],
        },
        {
          id: 'qq-status',
          title: 'Current Status',
          tone,
          lines: [
            `Detected OpenID: ${detectedOpenId || 'waiting for first private message'}`,
            `Last conversation: ${lastConversationId || 'waiting for runtime activity'}`,
            `Configured profiles: ${qqProfileSummaries.length || 0}`,
            `Discovered targets: ${selectedConnectorTargets.length}`,
          ],
        },
        ...(!selectedQuestForConfig?.quest_id && hasDetectedTarget
          ? [
              {
                id: 'qq-bind-warning',
                title: 'Quest Binding Needs A Quest',
                tone: 'warning' as const,
                lines: ['Open a quest with `/use <quest_id>` first, then come back here to bind the detected QQ target to that quest.'],
              },
            ]
          : []),
      ]
    }

    return []
  }, [
    qqProfileSummaries.length,
    qqHasMultipleProfiles,
    selectedConnectorConfig,
    selectedConnectorName,
    selectedConnectorSnapshot,
    selectedConnectorTargets,
    selectedQuestForConfig?.quest_id,
  ])
  const connectorDetailItems = useMemo<ConnectorDetailItem[]>(() => {
    if (!selectedConnectorName) {
      return []
    }
    const activeBindingQuestId = selectedQuestForConfig?.quest_id || null
    const currentQuestTarget = activeBindingQuestId
      ? selectedConnectorTargets.find((item) => normalizedText(item.bound_quest_id) === activeBindingQuestId) || null
      : null
    const bindingActionItems: ConnectorDetailItem[] = []
    if (activeBindingQuestId && currentQuestTarget) {
      bindingActionItems.push({
        type: 'action',
        id: buildConnectorUnbindActionId(selectedConnectorName),
        label: `Unbind ${activeBindingQuestId}`,
        description: `Remove ${activeBindingQuestId} from ${connectorLabel(selectedConnectorName)} and return the quest to local-only binding.`,
      })
    }
    if (activeBindingQuestId) {
      for (const target of selectedConnectorTargets) {
        const targetLabel = connectorTargetLabel(target) || target.conversation_id
        const bindingState =
          normalizedText(target.bound_quest_id) === activeBindingQuestId
            ? `Already bound to ${activeBindingQuestId}.`
            : normalizedText(target.bound_quest_id)
              ? `Currently bound to ${target.bound_quest_id}. Enter will rebind it to ${activeBindingQuestId}.`
              : `Not bound yet. Enter will bind it to ${activeBindingQuestId}.`
        bindingActionItems.push({
          type: 'action',
          id: buildConnectorBindActionId(selectedConnectorName, target.conversation_id),
          label: `Bind ${targetLabel}`,
          description: `${target.conversation_id} · ${bindingState}`,
        })
      }
    }
    if (selectedConnectorName === 'weixin') {
      return [
        {
          type: 'action',
          id: 'weixin-start-login',
          label: selectedConnectorSnapshot?.enabled ? 'Rebind Weixin' : 'Bind Weixin',
          description: 'Start QR login, render a QR code in TUI, and save the connector automatically after confirmation.',
        },
        {
          type: 'action',
          id: 'refresh-connector',
          label: 'Refresh Status',
          description: 'Reload connector runtime snapshot and current structured config.',
        },
        {
          type: 'info',
          id: 'weixin-account-id',
          label: 'Bot account',
          value: displayMaybeString(selectedConnectorConfig.account_id ?? selectedConnectorSnapshot?.details?.account_id),
          description: 'Saved Weixin bot account id.',
        },
        {
          type: 'info',
          id: 'weixin-login-user',
          label: 'Owner account',
          value: displayMaybeString(selectedConnectorConfig.login_user_id),
          description: 'WeChat account that confirmed the QR login.',
        },
        {
          type: 'info',
          id: 'weixin-base-url',
          label: 'Base URL',
          value: displayMaybeString(selectedConnectorConfig.base_url),
          description: 'The iLink API base URL saved in connectors config.',
        },
        {
          type: 'info',
          id: 'weixin-targets',
          label: 'Known targets',
          value: String(selectedConnectorTargets.length || selectedConnectorSnapshot?.target_count || 0),
          description: 'Targets discovered by the Weixin connector.',
        },
        ...bindingActionItems,
      ]
    }
    if (selectedConnectorName === 'lingzhu') {
      const details = asRecord(selectedConnectorSnapshot?.details)
      const authAk = resolveLingzhuAuthAk(selectedConnectorConfig.auth_ak)
      const publicReady = looksLikePublicBaseUrl(selectedConnectorConfig.public_base_url)
      const publicSseUrl = lingzhuPublicSseUrl(selectedConnectorConfig, details)
      const publicHealthUrl = lingzhuPublicHealthUrl(selectedConnectorConfig, details)
      const saveReady = publicReady && Boolean(normalizedText(publicSseUrl)) && Boolean(normalizedText(authAk))
      const generatedAgentId = normalizedText(selectedConnectorConfig.agent_id || LINGZHU_PUBLIC_AGENT_ID) || LINGZHU_PUBLIC_AGENT_ID
      const logoUrl = lingzhuPlatformLogoUrl(baseUrl)
      return [
        {
          type: 'action',
          id: 'save-connector',
          label: 'Save Connector',
          description: saveReady
            ? 'Persist the generated Lingzhu values into connectors.yaml and reload the runtime.'
            : 'Set a public base URL and a Custom agent AK first. The Web Rokid popup applies the same save gate.',
          disabled: !saveReady,
        },
        {
          type: 'action',
          id: 'generate-lingzhu-ak',
          label: 'Generate AK',
          description: 'Create a new random Custom agent AK for the Lingzhu bridge.',
        },
        {
          type: 'action',
          id: 'refresh-connector',
          label: 'Refresh Status',
          description: 'Reload connector runtime snapshot and current structured config.',
        },
        {
          type: 'field',
          key: 'public_base_url',
          label: 'Public base URL',
          value: displayMaybeString(selectedConnectorConfig.public_base_url),
          description: 'Publicly reachable DeepScientist base URL used by Rokid devices.',
          fieldKind: 'url',
          editable: true,
        },
        {
          type: 'field',
          key: 'local_host',
          label: 'Local host',
          value: displayMaybeString(selectedConnectorConfig.local_host),
          description: 'Host used by DeepScientist when probing its own Lingzhu routes locally.',
          fieldKind: 'text',
          editable: true,
        },
        {
          type: 'field',
          key: 'gateway_port',
          label: 'Gateway port',
          value: displayMaybeString(selectedConnectorConfig.gateway_port),
          description: 'Port used when building the health and SSE endpoints.',
          fieldKind: 'text',
          editable: true,
        },
        {
          type: 'field',
          key: 'agent_id',
          label: 'Custom agent ID',
          value: displayMaybeString(selectedConnectorConfig.agent_id || LINGZHU_PUBLIC_AGENT_ID),
          description: 'Public agent id that must match the Rokid custom agent ID field.',
          fieldKind: 'text',
          editable: true,
        },
        {
          type: 'field',
          key: 'auth_ak',
          label: 'Custom agent AK',
          value: displayMaybeString(authAk),
          description: 'Generated token that must match the AK pasted into the Rokid custom agent form.',
          fieldKind: 'password',
          editable: true,
        },
        {
          type: 'info',
          id: 'lingzhu-platform-agent-id',
          label: 'Custom agent ID',
          value: displayMaybeString(generatedAgentId),
          description: 'Paste this exact value into the Rokid custom agent ID field.',
        },
        {
          type: 'info',
          id: 'lingzhu-platform-agent-url',
          label: 'Custom agent URL',
          value: displayMaybeString(publicSseUrl),
          description: 'Paste this exact value into the Rokid custom agent URL field.',
        },
        {
          type: 'info',
          id: 'lingzhu-platform-agent-ak',
          label: 'Custom agent AK',
          value: displayMaybeString(authAk),
          description: 'Paste this exact value into the Rokid custom agent AK field.',
        },
        {
          type: 'info',
          id: 'lingzhu-platform-agent-name',
          label: 'Agent name',
          value: LINGZHU_PLATFORM_AGENT_NAME,
          description: 'Suggested display name for the Rokid custom agent form.',
        },
        {
          type: 'info',
          id: 'lingzhu-platform-category',
          label: 'Category',
          value: LINGZHU_PLATFORM_CATEGORY,
          description: 'Recommended Rokid category for the DeepScientist agent.',
        },
        {
          type: 'info',
          id: 'lingzhu-platform-capability-summary',
          label: 'Capability summary',
          value: LINGZHU_PLATFORM_CAPABILITY_SUMMARY,
          description: 'Paste this capability summary into the Rokid custom agent form.',
          multiline: true,
        },
        {
          type: 'info',
          id: 'lingzhu-platform-opening-message',
          label: 'Opening message',
          value: LINGZHU_PLATFORM_OPENING_MESSAGE,
          description: 'Paste this greeting into the Rokid opening message field.',
          multiline: true,
        },
        {
          type: 'info',
          id: 'lingzhu-platform-input-type',
          label: 'Input type',
          value: LINGZHU_PLATFORM_INPUT_TYPE,
          description: 'Recommended Rokid input type for DeepScientist.',
        },
        {
          type: 'info',
          id: 'lingzhu-platform-logo-url',
          label: 'Icon/logo URL',
          value: displayMaybeString(logoUrl),
          description: 'Optional Rokid icon URL. The Web popup shows the same DeepScientist Rokid logo.',
        },
        {
          type: 'info',
          id: 'lingzhu-public-health',
          label: 'Public health URL',
          value: displayMaybeString(publicHealthUrl),
          description: 'Public health endpoint for debugging.',
        },
        {
          type: 'info',
          id: 'lingzhu-local-sse',
          label: 'Local SSE URL',
          value: displayMaybeString(details.endpoint_url),
          description: 'Local SSE endpoint used by DeepScientist probes.',
        },
        {
          type: 'info',
          id: 'lingzhu-local-health',
          label: 'Local health URL',
          value: displayMaybeString(details.health_url),
          description: 'Local health endpoint used by DeepScientist probes.',
        },
        ...bindingActionItems,
      ]
    }
    if (selectedConnectorName === 'qq') {
      const secretValue = String(selectedConnectorConfig.app_secret ?? '').trim()
      const qqProfileInfoItems: ConnectorDetailItem[] = qqProfileSummaries.map((profile) => {
        const statusText =
          profile.status === 'bound'
            ? 'Bound'
            : profile.status === 'ready'
              ? 'Ready for binding'
              : 'Waiting for first message'
        const targetLabel = profile.selectedTarget ? connectorTargetLabel(profile.selectedTarget) || profile.selectedTarget.conversation_id : 'waiting'
        const boundQuestId = normalizedText(profile.selectedTarget?.bound_quest_id) || 'not bound yet'
        return {
          type: 'info',
          id: `qq-profile:${profile.profileId}`,
          label: `Profile · ${profile.label}`,
          value: [
            `Profile ID: ${profile.profileId}`,
            `App ID: ${profile.appId || '—'}`,
            `Detected OpenID: ${profile.mainChatId || 'waiting for first private message'}`,
            `Last conversation: ${profile.lastConversationId || 'waiting for runtime activity'}`,
            `Targets: ${profile.targetCount}`,
            `Preferred target: ${targetLabel}`,
            `Bound quest: ${boundQuestId}`,
            `Status: ${statusText}`,
          ].join('\n'),
          description: 'Profile-level runtime summary aligned with the Web QQ connector cards.',
          multiline: true,
        }
      })
      return [
        {
          type: 'action',
          id: 'save-connector',
          label: 'Save Connector',
          description: qqHasMultipleProfiles
            ? 'Persist shared QQ settings and reload the runtime. Use raw connectors.yaml for profile add, delete, or credential replacement.'
            : 'Persist the current QQ fields into connectors.yaml and reload the runtime.',
          disabled: false,
        },
        {
          type: 'action',
          id: 'refresh-connector',
          label: 'Refresh Status',
          description: 'Reload connector runtime snapshot and current structured config.',
        },
        {
          type: 'action',
          id: 'open-raw-connectors',
          label: 'Open Raw connectors.yaml',
          description: 'Open the full connectors config file for advanced or multi-profile QQ changes.',
        },
        {
          type: 'field',
          key: 'bot_name',
          label: 'Bot name',
          value: displayMaybeString(selectedConnectorConfig.bot_name),
          description: qqHasMultipleProfiles
            ? 'Default display name for QQ profiles. Add or replace per-profile bot names in raw connectors.yaml.'
            : 'Display name used by the QQ connector.',
          fieldKind: 'text',
          editable: !qqHasMultipleProfiles,
        },
        {
          type: 'field',
          key: 'app_id',
          label: 'App ID',
          value: displayMaybeString(selectedConnectorConfig.app_id),
          description: 'Tencent QQ bot App ID.',
          fieldKind: 'text',
          editable: !qqHasMultipleProfiles,
        },
        {
          type: 'field',
          key: 'app_secret',
          label: 'App secret',
          value: displayMaybeString(secretValue),
          description: 'QQ bot App Secret. Save this first, then send one private QQ message to the bot.',
          fieldKind: 'password',
          editable: !qqHasMultipleProfiles,
        },
        {
          type: 'field',
          key: 'command_prefix',
          label: 'Command prefix',
          value: displayMaybeString(selectedConnectorConfig.command_prefix),
          description: 'Prefix used for slash-style QQ commands.',
          fieldKind: 'text',
          editable: true,
        },
        {
          type: 'field',
          key: 'require_at_in_groups',
          label: 'Require @ mention in groups',
          value: displayBoolean(selectedConnectorConfig.require_at_in_groups),
          description: 'Only process QQ group messages when the bot is explicitly mentioned.',
          fieldKind: 'boolean',
          editable: true,
        },
        {
          type: 'field',
          key: 'gateway_restart_on_config_change',
          label: 'Restart gateway on config change',
          value: displayBoolean(selectedConnectorConfig.gateway_restart_on_config_change),
          description: 'Restart the local gateway worker after QQ settings are changed.',
          fieldKind: 'boolean',
          editable: true,
        },
        {
          type: 'field',
          key: 'auto_bind_dm_to_active_quest',
          label: 'Auto-bind DM to active quest',
          value: displayBoolean(selectedConnectorConfig.auto_bind_dm_to_active_quest),
          description: 'Allow a private QQ chat to auto-bind to the current quest.',
          fieldKind: 'boolean',
          editable: true,
        },
        ...qqProfileInfoItems,
        {
          type: 'info',
          id: 'qq-detected-openid',
          label: 'Detected OpenID',
          value: displayMaybeString(selectedConnectorConfig.main_chat_id || selectedConnectorSnapshot?.main_chat_id),
          description: 'This value is auto-filled after the first private QQ message reaches DeepScientist.',
        },
        {
          type: 'info',
          id: 'qq-last-conversation',
          label: 'Last conversation',
          value: displayMaybeString(selectedConnectorSnapshot?.last_conversation_id),
          description: 'After the first QQ message arrives, the runtime also refreshes the latest conversation id here.',
        },
        {
          type: 'info',
          id: 'qq-targets',
          label: 'Discovered targets',
          value: String(selectedConnectorTargets.length || selectedConnectorSnapshot?.target_count || 0),
          description: 'Targets learned from QQ runtime activity. Bind the current quest to one of them below.',
        },
        ...bindingActionItems,
      ]
    }
    return [
      {
        type: 'action',
        id: 'open-raw-connectors',
        label: 'Open Raw connectors.yaml',
        description: 'Guided setup is not available for this connector yet. Open the raw connectors config instead.',
      },
      {
        type: 'info',
        id: 'connector-mode',
        label: 'Mode',
        value: displayMaybeString(selectedConnectorSnapshot?.mode || selectedConnectorConfig.transport),
        description: 'Current connector runtime mode.',
      },
      ...bindingActionItems,
    ]
  }, [
    baseUrl,
    qqProfileSummaries,
    qqHasMultipleProfiles,
    selectedConnectorConfig,
    selectedConnectorName,
    selectedConnectorSnapshot,
    selectedConnectorTargets,
    selectedQuestForConfig?.quest_id,
  ])
  const connectorDirty = useMemo(() => {
    if (!selectedConnectorName || !connectorsDocument?.structured) {
      return false
    }
    try {
      return (
        JSON.stringify(asRecord(connectorsDocument.structured[selectedConnectorName])) !==
        JSON.stringify(asRecord(connectorsDocument.savedStructured[selectedConnectorName]))
      )
    } catch {
      return true
    }
  }, [connectorsDocument, selectedConnectorName])
  const slashSuggestions = useMemo(() => {
    const slashCommands = session?.acp_session?.slash_commands ?? []
    const localCommands = [
      { name: '/home', description: 'Return to home request mode.' },
      { name: '/projects', description: 'Open the quest browser.' },
      { name: '/use', description: 'Bind a quest, for example `/use 001`.' },
      { name: '/new', description: 'Create a new quest explicitly.' },
      { name: '/delete', description: 'Delete a quest (requires --yes).' },
      { name: '/pause', description: 'Pause a running quest.' },
      { name: '/resume', description: 'Resume a stopped quest.' },
      { name: '/stop', description: 'Stop a running quest.' },
      { name: '/status', description: 'Show the current quest status.' },
      { name: '/graph', description: 'Show the quest graph.' },
      { name: '/config', description: 'Open the local config workspace.' },
      { name: '/config connectors', description: 'Open the connector list inside config.' },
      { name: '/config qq', description: 'Open the QQ connector setup.' },
      { name: '/config weixin', description: 'Open the Weixin connector setup.' },
      { name: '/config lingzhu', description: 'Open the Lingzhu connector setup.' },
    ]
    if (!input.startsWith('/')) {
      return []
    }
    const merged = [
      ...slashCommands,
      ...localCommands.filter((item) => !slashCommands.some((existing) => existing.name === item.name)),
    ]
    return merged.filter((item) => item.name.toLowerCase().includes(input.toLowerCase())).slice(0, 6)
  }, [input, session])
  const replyTargetId = useMemo(() => {
    const snapshotTarget =
      session?.snapshot.default_reply_interaction_id ||
      session?.acp_session?.meta?.default_reply_interaction_id
    return snapshotTarget ? String(snapshotTarget) : null
  }, [session])
  const configPanel = useMemo<ConfigPanel | null>(() => {
    if (!configView) {
      return null
    }
    if (configEditor?.kind === 'document') {
      return {
        kind: 'document-editor',
        item: configEditor.item,
        content: input,
      }
    }
    if (configEditor?.kind === 'connector-field') {
      return {
        kind: 'connector-field-editor',
        connectorName: connectorLabel(configEditor.connectorName),
        fieldLabel: configEditor.fieldLabel,
        content: input,
        description: configEditor.description,
        masked: configEditor.fieldKind === 'password',
      }
    }
    if (configView === 'root') {
      return {
        kind: 'root',
        items: CONFIG_ROOT_ENTRIES,
        selectedIndex: configIndex,
        selectedQuestId: selectedQuestForConfig?.quest_id ?? null,
      }
    }
    if (configView === 'files') {
      return {
        kind: 'files',
        title: configSectionTitle,
        description: configSectionDescription,
        items: configItems,
        selectedIndex: configIndex,
        selectedQuestId: selectedQuestForConfig?.quest_id ?? null,
      }
    }
    if (configView === 'connector-list') {
      return {
        kind: 'connector-list',
        items: connectorMenuEntries,
        selectedIndex: configIndex,
      }
    }
    if (configView === 'connector-detail' && selectedConnectorName) {
      return {
        kind: 'connector-detail',
        connectorName: selectedConnectorName,
        connectorLabel: connectorLabel(selectedConnectorName),
        selectedIndex: configIndex,
        items: connectorDetailItems,
        dirty: connectorDirty,
        snapshot: selectedConnectorSnapshot,
        contextLine: connectorContextLine,
        guideSections: connectorGuideSections,
        warning:
          selectedConnectorName === 'qq' && qqHasMultipleProfiles
            ? 'QQ currently has multiple profiles. TUI supports shared settings and quest binding here, but adding, deleting, or replacing profile credentials still belongs in raw connectors.yaml.'
            : null,
      }
    }
    if (configView === 'weixin-qr') {
      return {
        kind: 'weixin-qr',
        status: weixinQrState?.status || 'waiting',
        sessionKey: weixinQrState?.sessionKey || null,
        qrAscii: weixinQrState?.qrAscii || null,
        qrContent: weixinQrState?.qrContent || null,
        qrUrl: weixinQrState?.qrUrl || null,
        message: weixinQrState?.message || null,
      }
    }
    return null
  }, [
    configEditor,
    configIndex,
    configItems,
    configSectionDescription,
    configSectionTitle,
    connectorContextLine,
    configView,
    connectorDetailItems,
    connectorDirty,
    connectorGuideSections,
    connectorMenuEntries,
    input,
    qqHasMultipleProfiles,
    selectedConnectorName,
    selectedConnectorSnapshot,
    selectedQuestForConfig?.quest_id,
    weixinQrState,
  ])
  const configSelectionCount = useMemo(() => {
    if (!configPanel || configMode !== 'browse') {
      return 0
    }
    if (configPanel.kind === 'root' || configPanel.kind === 'files' || configPanel.kind === 'connector-list') {
      return configPanel.items.length
    }
    if (configPanel.kind === 'connector-detail') {
      return configPanel.items.length
    }
    return 0
  }, [configMode, configPanel])

  useEffect(() => {
    activeQuestIdRef.current = activeQuestId
  }, [activeQuestId])

  useEffect(() => {
    browseQuestIdRef.current = browseQuestId
  }, [browseQuestId])

  useEffect(() => {
    historyRef.current = history
  }, [history])

  useEffect(() => {
    pendingHistoryItemsRef.current = pendingHistoryItems
  }, [pendingHistoryItems])

  const enterQuest = useCallback((questId: string | null) => {
    activeQuestIdRef.current = questId
    setActiveQuestId(questId)
    if (questId) {
      browseQuestIdRef.current = questId
      setBrowseQuestId(questId)
    }
    setConfigView(null)
    setConfigEditor(null)
    setConfigItems([])
    setConfigSectionTitle('Config')
    setConfigSectionDescription('')
    setConfigIndex(0)
    setConnectorsDocument(null)
    setSelectedConnectorName(null)
    setWeixinQrState(null)
    setQuestPanelMode(null)
    historyRef.current = []
    pendingHistoryItemsRef.current = []
    setHistory([])
    setPendingHistoryItems([])
    setCursor(0)
    cursorRef.current = 0
    setSession(null)
  }, [])

  const leaveQuest = useCallback(() => {
    activeQuestIdRef.current = null
    browseQuestIdRef.current = null
    setActiveQuestId(null)
    setConfigView(null)
    setConfigEditor(null)
    setConfigItems([])
    setConfigSectionTitle('Config')
    setConfigSectionDescription('')
    setConfigIndex(0)
    setConnectorsDocument(null)
    setSelectedConnectorName(null)
    setWeixinQrState(null)
    setQuestPanelMode(null)
    setSession(null)
    historyRef.current = []
    pendingHistoryItemsRef.current = []
    setHistory([])
    setPendingHistoryItems([])
    setCursor(0)
    cursorRef.current = 0
  }, [])

  const refresh = useCallback(
    async (hard = false, overrideQuestId?: string | null) => {
      const requestId = refreshRequestRef.current + 1
      refreshRequestRef.current = requestId
      try {
        setConnectionState((current) => (hard ? 'connecting' : current))
        const [nextQuests, nextConnectors] = await Promise.all([
          client.quests(baseUrl),
          client.connectors(baseUrl),
        ])
        if (requestId !== refreshRequestRef.current) {
          return
        }
        setQuests(nextQuests)
        setConnectors(nextConnectors)

        const activeQuestIdAtStart = activeQuestIdRef.current
        const browseQuestIdAtStart = browseQuestIdRef.current
        const requestedQuestId = overrideQuestId !== undefined ? overrideQuestId : activeQuestIdAtStart
        const currentQuestId =
          requestedQuestId && nextQuests.some((quest) => quest.quest_id === requestedQuestId)
            ? requestedQuestId
            : null
        if (currentQuestId !== activeQuestIdRef.current) {
          activeQuestIdRef.current = currentQuestId
          setActiveQuestId(currentQuestId)
        }
        const nextBrowseQuestId =
          browseQuestIdAtStart && nextQuests.some((quest) => quest.quest_id === browseQuestIdAtStart)
            ? browseQuestIdAtStart
            : currentQuestId || nextQuests[0]?.quest_id || null
        if (nextBrowseQuestId !== browseQuestIdRef.current) {
          browseQuestIdRef.current = nextBrowseQuestId
          setBrowseQuestId(nextBrowseQuestId)
        }
        if (!currentQuestId) {
          setSession(null)
          historyRef.current = []
          pendingHistoryItemsRef.current = []
          setHistory([])
          setPendingHistoryItems([])
          setCursor(0)
          cursorRef.current = 0
          setConnectionState('connected')
          if (nextQuests.length === 0) {
            setStatusLine('Home · no quests yet · use `/new <goal>` to create the first quest.')
          } else {
            setStatusLine('Home · selected quest ready · use `/use <quest_id>` to bind or `/new <goal>` to create another.')
          }
          return
        }

        const nextCursor = hard || currentQuestId !== activeQuestIdAtStart ? 0 : cursorRef.current
        const [nextSession, nextEvents] = await Promise.all([
          client.session(baseUrl, currentQuestId),
          client.events(baseUrl, currentQuestId, nextCursor),
        ])
        if (requestId !== refreshRequestRef.current) {
          return
        }
        const normalized = (nextEvents.acp_updates ?? []).map((item) => normalizeUpdate(item.params.update))
        setSession(nextSession)
        const baseState: FeedState =
          hard || currentQuestId !== activeQuestIdAtStart
            ? { history: [], pending: [] }
            : { history: historyRef.current, pending: pendingHistoryItemsRef.current }
        const nextState = applyIncomingFeedUpdates(baseState, normalized)
        historyRef.current = nextState.history
        pendingHistoryItemsRef.current = nextState.pending
        setHistory(nextState.history)
        setPendingHistoryItems(nextState.pending)
        const resolvedCursor = nextEvents.cursor ?? nextCursor
        setCursor(resolvedCursor)
        cursorRef.current = resolvedCursor
        setConnectionState('connected')
        setStatusLine(`Quest mode · ${currentQuestId} · ${baseUrl}`)
        if (nextSession.snapshot?.status && nextSession.snapshot.status !== 'running') {
          const clearedPending = pendingHistoryItemsRef.current.filter(
            (item) => !(item.type === 'message' && item.role === 'assistant' && item.stream)
          )
          pendingHistoryItemsRef.current = clearedPending
          setPendingHistoryItems(clearedPending)
        }
      } catch (error) {
        if (requestId !== refreshRequestRef.current) {
          return
        }
        setConnectionState('error')
        setStatusLine(error instanceof Error ? error.message : String(error))
      }
    },
    [baseUrl]
  )

  const openQuestPanel = useCallback(
    (mode: QuestPanelMode) => {
      setConfigView(null)
      setConfigEditor(null)
      setConnectorsDocument(null)
      setSelectedConnectorName(null)
      setWeixinQrState(null)
      const candidates = getPanelQuests(mode, quests)
      setQuestPanelMode(mode)
      if (candidates.length === 0) {
        setQuestPanelIndex(0)
        setStatusLine(
          mode === 'pause'
            ? 'No quests available to pause.'
            : mode === 'stop'
            ? 'No quests available to stop.'
            : mode === 'resume'
              ? 'No quests available to resume.'
              : 'No quests available.'
        )
        return
      }
      const currentId = activeQuestId || browseQuestId
      const nextIndex = Math.max(0, candidates.findIndex((quest) => quest.quest_id === currentId))
      setQuestPanelIndex(nextIndex)
      setBrowseQuestId(candidates[nextIndex]?.quest_id ?? browseQuestId)
      setStatusLine(
        mode === 'projects'
          ? 'Quest browser · use arrows and Enter to open.'
          : mode === 'pause'
            ? 'Pause quest · use arrows and Enter to pause.'
          : mode === 'stop'
            ? 'Stop quest · use arrows and Enter to stop.'
            : 'Resume quest · use arrows and Enter to resume.'
      )
    },
    [activeQuestId, browseQuestId, quests]
  )

  const closeConfigScreen = useCallback((nextStatus?: string) => {
    setConfigView(null)
    setConfigEditor(null)
    setConfigItems([])
    setConfigSectionTitle('Config')
    setConfigSectionDescription('')
    setConfigIndex(0)
    setConnectorsDocument(null)
    setSelectedConnectorName(null)
    setWeixinQrState(null)
    setInput('')
    if (nextStatus) {
      setStatusLine(nextStatus)
    }
  }, [])

  const loadConnectorsDocument = useCallback(async (): Promise<ConnectorsDocumentState> => {
    const payload = await client.configDocument(baseUrl, 'connectors')
    const structured = asRecord(payload.meta?.structured_config)
    return {
      item: {
        id: 'global:connectors',
        scope: 'global',
        name: 'connectors',
        title: payload.title || 'connectors.yaml',
        path: payload.path,
        writable: true,
        configName: 'connectors',
      },
      revision: payload.revision,
      savedStructured: cloneStructured(structured),
      structured: cloneStructured(structured),
    }
  }, [baseUrl])

  const setWeixinQrPayload = useCallback(
    async (payload: {
      session_key?: string | null
      status?: string | null
      qrcode_content?: string | null
      qrcode_url?: string | null
      message?: string | null
    }) => {
      const qrContent = String(payload.qrcode_content || '').trim()
      const qrUrl = String(payload.qrcode_url || '').trim()
      let qrAscii = ''
      const renderable = qrContent || qrUrl
      if (renderable && !looksLikeWeixinQrImageUrl(qrUrl || qrContent)) {
        try {
          qrAscii = await renderQrAscii(qrContent || qrUrl)
        } catch {
          qrAscii = ''
        }
      }
      setWeixinQrState({
        sessionKey: String(payload.session_key || '').trim(),
        status: String(payload.status || 'wait').trim() || 'wait',
        qrContent: qrContent || undefined,
        qrUrl: qrUrl || undefined,
        qrAscii: qrAscii || undefined,
        message: String(payload.message || '').trim() || undefined,
      })
    },
    []
  )

  const openConfigEditor = useCallback(
    async (item: ConfigScreenItem) => {
      try {
        let payload: OpenDocumentPayload
        if (item.scope === 'global' && item.configName) {
          payload = await client.configDocument(baseUrl, item.configName)
        } else {
          const questId = selectedQuestForConfig?.quest_id
          if (!questId || !item.documentId) {
            setStatusLine('Quest config requires a selected quest.')
            return
          }
          payload = await client.openDocument(baseUrl, questId, item.documentId)
        }
        setQuestPanelMode(null)
        setConfigView('files')
        setConfigEditor({
          kind: 'document',
          item,
          revision: payload.revision,
          content: payload.content,
        })
        setInput(payload.content)
        setStatusLine(`Editing ${item.title} · Enter save · Ctrl+J newline · Esc cancel`)
      } catch (error) {
        setStatusLine(error instanceof Error ? error.message : String(error))
      }
    },
    [baseUrl, selectedQuestForConfig]
  )

  const openConfigFiles = useCallback(
    async (scope: 'global' | 'quest', target?: string) => {
      try {
        const nextItems =
          scope === 'global'
            ? buildGlobalConfigItems(await client.configFiles(baseUrl))
            : buildQuestConfigItems(selectedQuestForConfig?.quest_id ?? null, selectedQuestForConfig?.quest_root)
        setQuestPanelMode(null)
        setConfigView('files')
        setConfigItems(nextItems)
        setConfigSectionTitle(scope === 'global' ? 'Global Config Files' : 'Current Quest Files')
        setConfigSectionDescription(
          scope === 'global'
            ? 'Choose a global config file and press Enter to edit it.'
            : 'Choose a quest-local config file and press Enter to edit it.'
        )
        setConfigEditor(null)
        if (nextItems.length === 0) {
          setConfigIndex(0)
          setStatusLine(scope === 'global' ? 'No global config files available.' : 'No current quest config files available.')
          return
        }
        if (target) {
          const resolved = resolveConfigTarget(target, nextItems)
          if (resolved) {
            setConfigIndex(nextItems.findIndex((item) => item.id === resolved.id))
            await openConfigEditor(resolved)
            return
          }
        }
        setConfigIndex(0)
        setStatusLine(scope === 'global' ? 'Global config files.' : 'Current quest config files.')
      } catch (error) {
        setStatusLine(error instanceof Error ? error.message : String(error))
      }
    },
    [baseUrl, openConfigEditor, selectedQuestForConfig]
  )

  const openConfigRoot = useCallback((nextStatus = 'Config · choose a section with arrows and Enter.') => {
    setQuestPanelMode(null)
    setConfigView('root')
    setConfigEditor(null)
    setConfigItems([])
    setConfigSectionTitle('Config')
    setConfigSectionDescription('')
    setConfigIndex(0)
    setSelectedConnectorName(null)
    setWeixinQrState(null)
    setInput('')
    setStatusLine(nextStatus)
  }, [])

  const openConfigBrowser = useCallback((nextStatus?: string) => {
    openConfigRoot(nextStatus)
  }, [openConfigRoot])

  const openConnectorBrowser = useCallback(
    async (targetConnector?: ManagedConnectorName | null) => {
      try {
        const document = await loadConnectorsDocument()
        const names = connectorNamesFromStructuredConfig(document.structured)
        const browseNames = names.length > 0 ? names : CONNECTOR_ORDER
        setQuestPanelMode(null)
        setConfigView('connector-list')
        setConfigEditor(null)
        setConnectorsDocument(document)
        setSelectedConnectorName(null)
        setWeixinQrState(null)
        setInput('')
        if (targetConnector) {
          const directIndex = browseNames.findIndex((item) => item === targetConnector)
          setConfigIndex(directIndex >= 0 ? directIndex : 0)
          return
        }
        setConfigIndex(0)
        setStatusLine('Connectors · choose a connector with arrows and Enter.')
      } catch (error) {
        setStatusLine(error instanceof Error ? error.message : String(error))
      }
    },
    [loadConnectorsDocument]
  )

  const updateConnectorDraft = useCallback(
    (connectorName: ManagedConnectorName, patch: Record<string, unknown>) => {
      setConnectorsDocument((current) => {
        if (!current) {
          return current
        }
        const nextStructured = cloneStructured(current.structured)
        const currentConnector = asRecord(nextStructured[connectorName])
        nextStructured[connectorName] = {
          ...currentConnector,
          ...patch,
        }
        return {
          ...current,
          structured: nextStructured,
        }
      })
    },
    []
  )

  const openConnectorDetail = useCallback(
    async (connectorName: ManagedConnectorName) => {
      try {
        let currentDocument = connectorsDocument ?? (await loadConnectorsDocument())
        if (connectorName === 'lingzhu') {
          const currentLingzhu = asRecord(currentDocument.structured.lingzhu)
          const patch: Record<string, unknown> = {}
          if (!resolveLingzhuAuthAk(currentLingzhu.auth_ak)) {
            patch.auth_ak = createLingzhuAk()
          }
          if (!String(currentLingzhu.agent_id || '').trim()) {
            patch.agent_id = LINGZHU_PUBLIC_AGENT_ID
          }
          if (!String(currentLingzhu.local_host || '').trim()) {
            patch.local_host = '127.0.0.1'
          }
          if (!String(currentLingzhu.gateway_port || '').trim()) {
            try {
              patch.gateway_port = String(new URL(baseUrl).port || '20999')
            } catch {
              patch.gateway_port = '20999'
            }
          }
          if (!String(currentLingzhu.public_base_url || '').trim()) {
            try {
              const currentBaseUrl = new URL(baseUrl)
              if (currentBaseUrl.hostname === '0.0.0.0') {
                currentBaseUrl.hostname = '127.0.0.1'
              }
              const resolvedBaseUrl = currentBaseUrl.toString().replace(/\/$/, '')
              if (looksLikePublicBaseUrl(resolvedBaseUrl)) {
                patch.public_base_url = resolvedBaseUrl
              }
            } catch {
              // ignore parse failures
            }
          }
          if (Object.keys(patch).length > 0) {
            currentDocument = {
              ...currentDocument,
              structured: {
                ...cloneStructured(currentDocument.structured),
                lingzhu: {
                  ...currentLingzhu,
                  ...patch,
                },
              },
            }
          }
        }
        setConnectorsDocument(currentDocument)
        setSelectedConnectorName(connectorName)
        setConfigView('connector-detail')
        setConfigEditor(null)
        setWeixinQrState(null)
        setConfigIndex(0)
        setInput('')
        setStatusLine(`${connectorLabel(connectorName)} connector · arrows to navigate, Enter to edit or run an action.`)
      } catch (error) {
        setStatusLine(error instanceof Error ? error.message : String(error))
      }
    },
    [baseUrl, connectorsDocument, loadConnectorsDocument]
  )

  const openRawConnectorsEditor = useCallback(async () => {
    const document = connectorsDocument ?? (await loadConnectorsDocument())
    setConnectorsDocument(document)
    await openConfigEditor(document.item)
  }, [connectorsDocument, loadConnectorsDocument, openConfigEditor])

  const saveConnectorDraft = useCallback(async () => {
    if (!connectorsDocument) {
      return
    }
    try {
      const structuredToSave = (() => {
        if (!selectedConnectorName) {
          return connectorsDocument.structured
        }
        const merged = cloneStructured(connectorsDocument.savedStructured)
        merged[selectedConnectorName] = cloneStructured(asRecord(connectorsDocument.structured[selectedConnectorName]))
        return merged
      })()
      const payload = await client.saveStructuredConfig(
        baseUrl,
        'connectors',
        structuredToSave,
        connectorsDocument.revision
      )
      if (!payload.ok) {
        setStatusLine(payload.message || payload.errors?.[0] || 'Connector save failed.')
        return
      }
      const refreshedDocument = await loadConnectorsDocument()
      setConnectorsDocument(refreshedDocument)
      await refresh(true, activeQuestIdRef.current)
      setStatusLine(`Saved ${selectedConnectorName ? connectorLabel(selectedConnectorName) : 'connectors'} settings.`)
    } catch (error) {
      setStatusLine(error instanceof Error ? error.message : String(error))
    }
  }, [baseUrl, connectorsDocument, loadConnectorsDocument, refresh, selectedConnectorName])

  const saveConfigEditor = useCallback(
    async (content: string) => {
      if (!configEditor) {
        return
      }
      try {
        if (configEditor.kind === 'connector-field') {
          updateConnectorDraft(configEditor.connectorName, { [configEditor.fieldKey]: content })
          setInput('')
          setConfigEditor(null)
          setStatusLine(`Updated ${configEditor.fieldLabel} in draft. Save the connector to persist it.`)
          return
        }
        if (configEditor.item.scope === 'global' && configEditor.item.configName) {
          const payload = await client.saveConfig(
            baseUrl,
            configEditor.item.configName,
            content,
            configEditor.revision
          )
          if (payload.ok === false) {
            setStatusLine(payload.message || payload.errors?.[0] || 'Config save failed.')
            return
          }
        } else {
          const questId = selectedQuestForConfig?.quest_id
          if (!questId || !configEditor.item.documentId) {
            setStatusLine('Quest config requires a selected quest.')
            return
          }
          const payload = await client.saveDocument(
            baseUrl,
            questId,
            configEditor.item.documentId,
            content,
            configEditor.revision
          )
          if (payload.ok === false) {
            setStatusLine(payload.message || 'Quest config save failed.')
            return
          }
        }
        setInput('')
        setConfigEditor(null)
        setConfigView('files')
        setStatusLine(`Saved ${configEditor.item.title}`)
        await refresh(true, activeQuestId)
      } catch (error) {
        setStatusLine(error instanceof Error ? error.message : String(error))
      }
    },
    [activeQuestId, baseUrl, configEditor, refresh, selectedQuestForConfig, updateConnectorDraft]
  )

  const openConnectorFieldEditor = useCallback(
    (fieldKey: string, fieldLabel: string, description: string, fieldKind: Exclude<ConnectorFieldKind, 'boolean'>) => {
      if (!selectedConnectorName) {
        return
      }
      const currentValue = String(selectedConnectorConfig[fieldKey] ?? '').trim()
      setConfigEditor({
        kind: 'connector-field',
        connectorName: selectedConnectorName,
        fieldKey,
        fieldLabel,
        description,
        fieldKind,
        content: currentValue,
      })
      setInput(currentValue)
      setStatusLine(`Editing ${fieldLabel} · Enter apply · Esc cancel`)
    },
    [selectedConnectorConfig, selectedConnectorName]
  )

  const toggleConnectorBooleanField = useCallback(
    (fieldKey: string, fieldLabel: string) => {
      if (!selectedConnectorName) {
        return
      }
      const currentValue = Boolean(selectedConnectorConfig[fieldKey])
      updateConnectorDraft(selectedConnectorName, { [fieldKey]: !currentValue })
      setStatusLine(`Updated ${fieldLabel} in draft. Save the connector to persist it.`)
    },
    [selectedConnectorConfig, selectedConnectorName, updateConnectorDraft]
  )

  const handleConnectorAction = useCallback(
    async (actionId: string) => {
      if (!selectedConnectorName) {
        return
      }
      const bindTarget = parseConnectorBindActionId(actionId)
      if (bindTarget) {
        const questId = selectedQuestForConfig?.quest_id
        if (!questId) {
          setStatusLine('Open a quest first, then bind the connector target to that quest.')
          return
        }
        await client.updateQuestBindings(baseUrl, questId, {
          connector: bindTarget.connectorName,
          conversation_id: bindTarget.conversationId,
          force: true,
        })
        await refresh(true, questId)
        setStatusLine(`Bound ${connectorLabel(bindTarget.connectorName)} target to ${questId}.`)
        return
      }
      const unbindConnectorName = parseConnectorUnbindActionId(actionId)
      if (unbindConnectorName) {
        const questId = selectedQuestForConfig?.quest_id
        if (!questId) {
          setStatusLine('Open a quest first, then remove the connector binding from that quest.')
          return
        }
        await client.updateQuestBindings(baseUrl, questId, {
          connector: unbindConnectorName,
          conversation_id: null,
          force: true,
        })
        await refresh(true, questId)
        setStatusLine(`Unbound ${connectorLabel(unbindConnectorName)} from ${questId}.`)
        return
      }
      if (actionId === 'save-connector') {
        await saveConnectorDraft()
        return
      }
      if (actionId === 'refresh-connector') {
        if (selectedConnectorName === 'weixin' || selectedConnectorName === 'qq' || selectedConnectorName === 'lingzhu') {
          const document = await loadConnectorsDocument()
          setConnectorsDocument(document)
        }
        await refresh(true, activeQuestIdRef.current)
        setStatusLine(`${connectorLabel(selectedConnectorName)} connector refreshed.`)
        return
      }
      if (actionId === 'generate-lingzhu-ak') {
        updateConnectorDraft('lingzhu', { auth_ak: createLingzhuAk() })
        setStatusLine('Generated a new Lingzhu Custom agent AK in draft.')
        return
      }
      if (actionId === 'weixin-start-login') {
        const payload = await client.startWeixinQrLogin(baseUrl, Boolean(selectedConnectorSnapshot?.enabled))
        if (!payload.ok || !payload.session_key) {
          setStatusLine(payload.message || 'Failed to start Weixin QR login.')
          return
        }
        setConfigView('weixin-qr')
        setConfigIndex(0)
        await setWeixinQrPayload({
          session_key: payload.session_key,
          status: 'wait',
          qrcode_content: payload.qrcode_content,
          qrcode_url: payload.qrcode_url,
          message: payload.message,
        })
        setStatusLine('Weixin QR login started. Scan the QR code with WeChat.')
        return
      }
      if (actionId === 'open-raw-connectors') {
        await openRawConnectorsEditor()
      }
    },
    [
      baseUrl,
      loadConnectorsDocument,
      openRawConnectorsEditor,
      refresh,
      saveConnectorDraft,
      selectedConnectorName,
      selectedConnectorSnapshot?.enabled,
      selectedQuestForConfig?.quest_id,
      setWeixinQrPayload,
      updateConnectorDraft,
    ]
  )

  const handleConfigBrowseSelection = useCallback(async () => {
    if (!configPanel) {
      return
    }
    if (configPanel.kind === 'root') {
      const selected = configPanel.items[configIndex]
      if (!selected) {
        return
      }
      if (selected.id === 'connectors') {
        await openConnectorBrowser()
        return
      }
      if (selected.id === 'global-files') {
        await openConfigFiles('global')
        return
      }
      if (selected.id === 'quest-files') {
        await openConfigFiles('quest')
      }
      return
    }
    if (configPanel.kind === 'files') {
      const selected = configPanel.items[configIndex] ?? null
      if (!selected) {
        setStatusLine('No config file selected.')
        return
      }
      await openConfigEditor(selected)
      return
    }
    if (configPanel.kind === 'connector-list') {
      const selected = configPanel.items[configIndex] ?? null
      if (!selected) {
        setStatusLine('No connector selected.')
        return
      }
      await openConnectorDetail(selected.name as ManagedConnectorName)
      return
    }
    if (configPanel.kind === 'connector-detail') {
      const selected = configPanel.items[configIndex] ?? null
      if (!selected) {
        return
      }
      if (selected.type === 'action') {
        if (!selected.disabled) {
          await handleConnectorAction(selected.id)
        }
        return
      }
      if (selected.type === 'field') {
        if (!selected.editable) {
          return
        }
        if (selected.fieldKind === 'boolean') {
          toggleConnectorBooleanField(selected.key, selected.label)
          return
        }
        openConnectorFieldEditor(selected.key, selected.label, selected.description, selected.fieldKind)
      }
    }
  }, [
    configIndex,
    configPanel,
    handleConnectorAction,
    openConfigEditor,
    openConfigFiles,
    openConnectorBrowser,
    openConnectorDetail,
    openConnectorFieldEditor,
    toggleConnectorBooleanField,
  ])

  const closeQuestPanel = useCallback((nextStatus?: string) => {
    setQuestPanelMode(null)
    if (nextStatus) {
      setStatusLine(nextStatus)
    }
  }, [])

  const focusQuest = useCallback(
    async (questId: string) => {
      enterQuest(questId)
      await refresh(true, questId)
    },
    [enterQuest, refresh]
  )

  const handleQuestPanelSelection = useCallback(async () => {
    if (!questPanelMode) {
      return
    }
    const selected = panelQuests[questPanelIndex] ?? null
    if (!selected) {
      closeQuestPanel('No quest available for this action.')
      return
    }
    if (questPanelMode === 'projects') {
      await focusQuest(selected.quest_id)
      return
    }
    const action = questPanelMode === 'pause' ? 'pause' : questPanelMode === 'stop' ? 'stop' : 'resume'
    const payload = await client.controlQuest(baseUrl, selected.quest_id, action)
    const fallbackVerb = action === 'pause' ? 'paused' : action === 'stop' ? 'stopped' : 'resumed'
    setStatusLine(String(payload.message ?? `Quest ${selected.quest_id} ${fallbackVerb}.`))
    await focusQuest(selected.quest_id)
  }, [baseUrl, closeQuestPanel, focusQuest, panelQuests, questPanelIndex, questPanelMode])

  const cycleQuest = useCallback(
    (direction: 1 | -1) => {
      if (configMode === 'browse') {
        if (configSelectionCount === 0) {
          return
        }
        setConfigIndex((previous) => (previous + direction + configSelectionCount) % configSelectionCount)
        return
      }
      if (questPanelMode) {
        if (panelQuests.length === 0) {
          return
        }
        setQuestPanelIndex((previous) => {
          const next = (previous + direction + panelQuests.length) % panelQuests.length
          const selected = panelQuests[next]
          if (selected?.quest_id) {
            setBrowseQuestId(selected.quest_id)
          }
          return next
        })
        return
      }
      if (quests.length === 0) {
        return
      }
      if (activeQuestId) {
        return
      }
      const currentId = activeQuestId || browseQuestId
      const index = quests.findIndex((quest) => quest.quest_id === currentId)
      const nextIndex = index < 0 ? 0 : (index + direction + quests.length) % quests.length
      const nextQuestId = quests[nextIndex]?.quest_id ?? null
      setBrowseQuestId(nextQuestId)
    },
    [activeQuestId, browseQuestId, configMode, configSelectionCount, panelQuests, questPanelMode, quests]
  )

  useEffect(() => {
    void refresh(true, initialQuestId)
  }, [initialQuestId, refresh])

  useEffect(() => {
    const timer = setInterval(() => {
      void refresh(false)
    }, 20000)
    return () => clearInterval(timer)
  }, [refresh])

  useEffect(() => {
    if (!questPanelMode) {
      return
    }
    if (panelQuests.length === 0) {
      if (questPanelIndex !== 0) {
        setQuestPanelIndex(0)
      }
      return
    }
    if (questPanelIndex >= panelQuests.length) {
      setQuestPanelIndex(panelQuests.length - 1)
      return
    }
    const selected = panelQuests[questPanelIndex]
    if (selected?.quest_id && selected.quest_id !== browseQuestId) {
      setBrowseQuestId(selected.quest_id)
    }
  }, [browseQuestId, panelQuests, questPanelIndex, questPanelMode])

  useEffect(() => {
    if (!activeQuestId) {
      streamAbortRef.current?.abort()
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      return
    }

    let cancelled = false
    const connect = () => {
      if (cancelled) {
        return
      }
      streamAbortRef.current?.abort()
      const controller = new AbortController()
      streamAbortRef.current = controller
      setConnectionState((current) => (current === 'connected' ? current : 'connecting'))
      void client
        .streamEvents(baseUrl, activeQuestId, cursorRef.current, {
          signal: controller.signal,
          onUpdate: (payload) => {
            if (cancelled) {
              return
            }
            const update = (payload.params as { update?: Record<string, unknown> } | undefined)?.update
            if (!update) {
              return
            }
            const nextCursor = Number(update.cursor ?? cursorRef.current)
            if (Number.isFinite(nextCursor)) {
              cursorRef.current = nextCursor
              setCursor(nextCursor)
            }
            const normalized = normalizeUpdate(update)
            const nextState = applyIncomingFeedUpdates(
              {
                history: historyRef.current,
                pending: pendingHistoryItemsRef.current,
              },
              [normalized]
            )
            historyRef.current = nextState.history
            pendingHistoryItemsRef.current = nextState.pending
            setHistory(nextState.history)
            setPendingHistoryItems(nextState.pending)
            setConnectionState('connected')
            setStatusLine(`Connected · ${activeQuestId} · ${baseUrl}`)
            if (shouldRefreshForUpdate(update)) {
              void refresh(false)
            }
          },
          onCursor: (nextCursor) => {
            cursorRef.current = nextCursor
            setCursor(nextCursor)
          },
        })
        .then(() => {
          if (cancelled || controller.signal.aborted) {
            return
          }
          reconnectTimerRef.current = setTimeout(connect, 800)
        })
        .catch((error) => {
          if (cancelled || controller.signal.aborted) {
            return
          }
          setConnectionState('error')
          setStatusLine(error instanceof Error ? `${error.message} · reconnecting…` : 'Stream reconnecting…')
          reconnectTimerRef.current = setTimeout(connect, 1200)
        })
    }

    connect()

    return () => {
      cancelled = true
      streamAbortRef.current?.abort()
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
    }
  }, [activeQuestId, baseUrl, refresh])

  useEffect(() => {
    if (configView !== 'weixin-qr' || !weixinQrState?.sessionKey) {
      return
    }
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const poll = async () => {
      try {
        const payload = await client.waitWeixinQrLogin(baseUrl, weixinQrState.sessionKey, 1500)
        if (cancelled) {
          return
        }
        await setWeixinQrPayload({
          session_key: payload.session_key || weixinQrState.sessionKey,
          status: payload.status,
          qrcode_content: payload.qrcode_content,
          qrcode_url: payload.qrcode_url,
          message: payload.message,
        })
        if (payload.connected) {
          const document = await loadConnectorsDocument()
          if (cancelled) {
            return
          }
          setConnectorsDocument(document)
          await refresh(true, activeQuestIdRef.current)
          if (cancelled) {
            return
          }
          setSelectedConnectorName('weixin')
          setConfigView('connector-detail')
          setConfigIndex(0)
          setStatusLine(payload.message || 'Weixin login succeeded and the connector config was saved.')
          return
        }
      } catch (error) {
        if (!cancelled) {
          setStatusLine(error instanceof Error ? error.message : String(error))
        }
      }
      if (!cancelled) {
        timer = setTimeout(() => {
          void poll()
        }, 1200)
      }
    }

    timer = setTimeout(() => {
      void poll()
    }, 400)

    return () => {
      cancelled = true
      if (timer) {
        clearTimeout(timer)
      }
    }
  }, [baseUrl, configView, loadConnectorsDocument, refresh, setWeixinQrPayload, weixinQrState?.sessionKey])

  const submit = useCallback(
    async (override?: string) => {
      const rawText = override ?? input
      if (configMode === 'edit' && configEditor) {
        await saveConfigEditor(rawText)
        return
      }
      const text = rawText.trim()
      if (configMode === 'browse' && !text) {
        await handleConfigBrowseSelection()
        return
      }
      if (configMode === 'browse' && !text.startsWith('/')) {
        setStatusLine('Config browser active · use arrows and Enter, or Esc to close.')
        return
      }
      if (questPanelMode && !text) {
        await handleQuestPanelSelection()
        setInput('')
        return
      }
      if (!text) {
        return
      }
      if (questPanelMode && !text.startsWith('/')) {
        setStatusLine('Quest browser active · use arrows and Enter, or Esc to cancel.')
        return
      }

      setInput('')
      try {
        const slash = parseSlashCommand(text)
        if (text === '/home') {
          closeQuestPanel()
          leaveQuest()
          setStatusLine('Home · request mode · quest unbound.')
          return
        }
        if (slash?.name === '/projects') {
          if (!slash.arg) {
            openQuestPanel('projects')
            return
          }
          const target = resolveQuestToken(slash.arg, quests)
          if (!target) {
            setStatusLine(`Unknown quest · ${slash.arg}`)
            return
          }
          await focusQuest(target.quest_id)
          return
        }
        if (slash?.name === '/pause') {
          const target = slash.arg
            ? resolveQuestToken(slash.arg, quests)
            : quests.find((quest) => quest.quest_id === (activeQuestId || browseQuestId)) ?? null
          if (!slash.arg && !target) {
            openQuestPanel('pause')
            return
          }
          if (!target) {
            setStatusLine(`Unknown quest · ${slash.arg}`)
            return
          }
          const payload = await client.controlQuest(baseUrl, target.quest_id, 'pause')
          setStatusLine(String(payload.message ?? `Quest ${target.quest_id} paused.`))
          await focusQuest(target.quest_id)
          return
        }
        if (slash?.name === '/stop') {
          const target = slash.arg
            ? resolveQuestToken(slash.arg, quests)
            : quests.find((quest) => quest.quest_id === (activeQuestId || browseQuestId)) ?? null
          if (!slash.arg && !target) {
            openQuestPanel('stop')
            return
          }
          if (!target) {
            setStatusLine(`Unknown quest · ${slash.arg}`)
            return
          }
          const payload = await client.controlQuest(baseUrl, target.quest_id, 'stop')
          setStatusLine(String(payload.message ?? `Quest ${target.quest_id} stopped.`))
          await focusQuest(target.quest_id)
          return
        }
        if (slash?.name === '/resume') {
          const target = slash.arg
            ? resolveQuestToken(slash.arg, quests)
            : quests.find((quest) => quest.quest_id === (activeQuestId || browseQuestId)) ?? null
          if (!slash.arg && !target) {
            openQuestPanel('resume')
            return
          }
          if (!target) {
            setStatusLine(`Unknown quest · ${slash.arg}`)
            return
          }
          const payload = await client.controlQuest(baseUrl, target.quest_id, 'resume')
          setStatusLine(String(payload.message ?? `Quest ${target.quest_id} resumed.`))
          await focusQuest(target.quest_id)
          return
        }
        if (slash?.name === '/use') {
          if (!slash.arg) {
            setStatusLine('Usage · /use <quest_id>')
            return
          }
          const target = resolveQuestToken(slash.arg, quests)
          if (!target) {
            setStatusLine(`Unknown quest · ${slash.arg}`)
            return
          }
          await focusQuest(target.quest_id)
          return
        }
        if (slash?.name === '/config') {
          const arg = String(slash.arg || '').trim()
          if (!arg) {
            openConfigRoot()
            return
          }
          const tokens = arg.split(/\s+/).filter(Boolean)
          const first = tokens[0]?.toLowerCase() || ''
          const second = tokens[1]?.toLowerCase() || ''
          const directConnector = resolveManagedConnectorName(first)
          const nestedConnector = first === 'connectors' ? resolveManagedConnectorName(second) : null
          if (first === 'connectors' && nestedConnector) {
            await openConnectorBrowser(nestedConnector)
            await openConnectorDetail(nestedConnector)
            return
          }
          if (directConnector) {
            await openConnectorBrowser(directConnector)
            await openConnectorDetail(directConnector)
            return
          }
          if (first === 'connectors') {
            await openConnectorBrowser()
            return
          }
          if (first === 'global') {
            await openConfigFiles('global')
            return
          }
          if (first === 'quest') {
            await openConfigFiles('quest')
            return
          }
          if (first === 'connectors.yaml') {
            await openConfigFiles('global', 'connectors')
            return
          }
          await openConfigFiles('global', arg)
          return
        }
        if (slash?.name === '/new') {
          if (!slash.arg) {
            setStatusLine('Usage · /new <goal>')
            return
          }
          const payload = await client.createQuest(baseUrl, slash.arg)
          setStatusLine(`Created ${payload.snapshot.quest_id}`)
          await focusQuest(payload.snapshot.quest_id)
          return
        }
        if (slash?.name === '/delete') {
          if (!slash.arg) {
            setStatusLine('Usage · /delete <quest_id> [--yes]')
            return
          }
          const tokens = slash.arg.split(/\s+/).filter(Boolean)
          const token = tokens[0]?.trim() ?? ''
          if (!token) {
            setStatusLine('Usage · /delete <quest_id> [--yes]')
            return
          }
          const target =
            token.toLowerCase() === 'latest' || token.toLowerCase() === 'newest'
              ? quests[0] ?? null
              : resolveQuestToken(token, quests)
          if (!target) {
            setStatusLine(`Unknown quest · ${token}`)
            return
          }
          const confirmed = tokens
            .slice(1)
            .some((item) => ['--yes', '--force', '-y'].includes(item.toLowerCase()))
          if (!confirmed) {
            setStatusLine(`Confirm delete · /delete ${target.quest_id} --yes`)
            return
          }
          await client.deleteQuest(baseUrl, target.quest_id)
          if (activeQuestId === target.quest_id) {
            leaveQuest()
          }
          setStatusLine(`Deleted ${target.quest_id}`)
          await refresh(true)
          return
        }

        if (!activeQuestId) {
          if (text.startsWith('/')) {
            setStatusLine('Home mode · use `/projects`, `/use <quest_id>`, or `/new <goal>` first.')
            return
          }
          if (quests.length === 0) {
            setStatusLine('Home mode · use `/new <goal>` to create the first quest.')
            return
          }
          setStatusLine('Home mode · use `/use <quest_id>` to bind a quest before sending messages.')
          return
        }

        if (text.startsWith('/')) {
          const payload = await client.sendCommand(baseUrl, activeQuestId, text)
          const messageRecord = (payload.message_record ?? null) as Record<string, unknown> | null
          const commandItems: FeedItem[] = [
            {
              id: buildId('local-user', `${Date.now()}-command-${text}`),
              type: 'message',
              role: 'user',
              content: text,
              source: 'tui',
            },
            ...(messageRecord
              ? [
                  {
                    id: buildId(
                      'message',
                      typeof messageRecord.id === 'string'
                        ? messageRecord.id
                        : `${Date.now()}-command-response`
                    ),
                    type: 'message' as const,
                    role: (String(messageRecord.role ?? 'assistant') === 'user'
                      ? 'user'
                      : 'assistant') as 'user' | 'assistant',
                    content: String(
                      messageRecord.content ??
                        payload.message ??
                        payload.type ??
                        'command accepted'
                    ),
                    source:
                      typeof messageRecord.source === 'string'
                        ? messageRecord.source
                        : 'command',
                    createdAt:
                      typeof messageRecord.created_at === 'string'
                        ? messageRecord.created_at
                        : undefined,
                  },
                ]
              : []),
          ]
          const nextState = applyIncomingFeedUpdates(
            {
              history: historyRef.current,
              pending: pendingHistoryItemsRef.current,
            },
            commandItems
          )
          historyRef.current = nextState.history
          pendingHistoryItemsRef.current = nextState.pending
          setHistory(nextState.history)
          setPendingHistoryItems(nextState.pending)
          const targetQuestId =
            typeof payload.target_quest_id === 'string' && payload.target_quest_id
              ? payload.target_quest_id
              : activeQuestId
          setStatusLine(
            typeof payload.message === 'string'
              ? payload.message.split('\n')[0]
              : typeof payload.type === 'string'
                ? `command acknowledged: ${payload.type}`
                : 'command accepted'
          )
          await refresh(false, targetQuestId)
          return
        }

        const localUserItem = createLocalUserFeedItem(text)
        const optimisticPending = [...pendingHistoryItemsRef.current, localUserItem].slice(-12)
        pendingHistoryItemsRef.current = optimisticPending
        setPendingHistoryItems(optimisticPending)
        try {
          await client.sendChat(baseUrl, activeQuestId, text, replyTargetId)
          setStatusLine(replyTargetId ? 'Reply sent · continuing current quest.' : 'Message sent · DeepScientist is working.')
        } catch (error) {
          const revertedPending = pendingHistoryItemsRef.current.filter((item) => item.id !== localUserItem.id)
          pendingHistoryItemsRef.current = revertedPending
          setPendingHistoryItems(revertedPending)
          throw error
        }
      } catch (error) {
        setStatusLine(error instanceof Error ? error.message : String(error))
      }
    },
    [
      activeQuestId,
      baseUrl,
      browseQuestId,
      configEditor,
      configIndex,
      configMode,
      closeQuestPanel,
      focusQuest,
      handleConfigBrowseSelection,
      handleQuestPanelSelection,
      input,
      leaveQuest,
      openConfigFiles,
      openConfigRoot,
      openConnectorBrowser,
      openConnectorDetail,
      openQuestPanel,
      questPanelMode,
      quests,
      refresh,
      replyTargetId,
      saveConfigEditor,
    ]
  )

  const backFromConfigBrowse = useCallback(() => {
    if (!configView) {
      return
    }
    if (configView === 'root') {
      closeConfigScreen('Config browser closed.')
      return
    }
    if (configView === 'files' || configView === 'connector-list') {
      openConfigRoot()
      return
    }
    if (configView === 'connector-detail') {
      setConfigView('connector-list')
      setConfigIndex(0)
      setSelectedConnectorName(null)
      setWeixinQrState(null)
      setStatusLine('Connectors · choose a connector with arrows and Enter.')
      return
    }
    if (configView === 'weixin-qr') {
      setConfigView('connector-detail')
      setConfigIndex(0)
      setStatusLine('Back to Weixin connector details.')
    }
  }, [closeConfigScreen, configView, openConfigRoot])

  useInput((value, key) => {
    const canBrowseSelection = configMode === 'browse' || Boolean(questPanelMode)
    const canBrowseHomeQuests = !activeQuestId && input.length === 0
    const submitRequested = key.return || value === '\r' || value === '\n'

    if (key.ctrl && value === 'c') {
      exit()
      return
    }
    if (key.ctrl && value.toLowerCase() === 'r') {
      void refresh(true, activeQuestId)
      return
    }
    if (key.ctrl && value.toLowerCase() === 'o') {
      openBrowser(buildProjectUrl(baseUrl, activeQuestId || browseQuestId, authToken))
      return
    }
    if (key.ctrl && value.toLowerCase() === 'g') {
      openConfigRoot()
      return
    }
    if (key.ctrl && value.toLowerCase() === 'b') {
      if (configMode) {
        closeConfigScreen()
        return
      }
      closeQuestPanel()
      leaveQuest()
      return
    }
    if (key.escape) {
      if (configMode === 'edit') {
        setConfigEditor(null)
        setInput('')
        setStatusLine('Config edit cancelled.')
        return
      }
      if (configMode === 'browse') {
        backFromConfigBrowse()
        return
      }
      if (questPanelMode) {
        closeQuestPanel('Quest browser closed.')
        return
      }
      setInput('')
      return
    }
    if (submitRequested) {
      if (configMode === 'browse' && input.trim().length === 0) {
        void handleConfigBrowseSelection()
        return
      }
    }
    if (key.upArrow && ((configMode === 'browse') || canBrowseHomeQuests)) {
      cycleQuest(-1)
      return
    }
    if ((key.downArrow || key.tab) && ((configMode === 'browse') || canBrowseHomeQuests)) {
      cycleQuest(1)
      return
    }
  })

  return (
    <DefaultAppLayout
      baseUrl={baseUrl}
      quests={quests}
      activeQuestId={activeQuestId}
      browseQuestId={browseQuestId}
      configMode={configMode}
      configPanel={configPanel}
      snapshot={activeQuest}
      session={session}
      connectors={connectors}
      history={history}
      pendingHistoryItems={pendingHistoryItems}
      input={input}
      connectionState={connectionState}
      statusLine={statusLine}
      suggestions={slashSuggestions}
      questPanelMode={questPanelMode}
      questPanelQuests={panelQuests}
      questPanelIndex={questPanelIndex}
      onQuestPanelMove={(direction) => {
        cycleQuest(direction)
      }}
      onQuestPanelConfirm={() => {
        void handleQuestPanelSelection()
      }}
      onQuestPanelCancel={() => {
        closeQuestPanel('Quest browser closed.')
      }}
      onChange={setInput}
      onSubmit={(override) => {
        const submitted = override ?? input
        if (configMode === 'browse' && !String(submitted).trim()) {
          void handleConfigBrowseSelection()
          return
        }
        if (questPanelMode && !String(submitted).trim()) {
          void handleQuestPanelSelection()
          return
        }
        if (!String(submitted).trim() && !activeQuestId && browseQuestId) {
          void focusQuest(browseQuestId)
          return
        }
        void submit(override)
      }}
      onCancel={() => {
        if (configMode === 'edit') {
          setConfigEditor(null)
          setInput('')
          setStatusLine('Config edit cancelled.')
          return
        }
        if (configMode === 'browse') {
          backFromConfigBrowse()
          return
        }
        if (questPanelMode) {
          closeQuestPanel('Quest browser closed.')
          return
        }
        setInput('')
      }}
    />
  )
}
