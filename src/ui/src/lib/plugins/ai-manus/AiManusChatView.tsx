'use client'

import {
  type CSSProperties,
  type HTMLAttributes,
  type Ref,
  type ReactNode,
  forwardRef,
  memo,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { createPortal } from 'react-dom'
import dynamic from 'next/dynamic'
import { useSearchParams } from 'next/navigation'
import type { PanelImperativeHandle, PanelSize } from 'react-resizable-panels'
import { LayoutGroup, motion, useReducedMotion } from 'framer-motion'
import axios from 'axios'
import {
  ArrowDown,
  FileSearch,
  Loader2,
  PanelLeft,
  Sparkles,
  Terminal,
  Server,
} from 'lucide-react'
import { VariableSizeList, type ListChildComponentProps } from 'react-window'
import { cn } from '@/lib/utils'
import { assetUrl } from '@/lib/assets'
import { useChatSessionStore } from '@/lib/stores/session'
import { useAgentRegistryStore } from '@/lib/stores/agent-registry'
import { useSSESession, type SSEEventContext } from '@/lib/hooks/useSSESession'
import { getCachedSessionEvents, replaceCachedSessionEvents } from '@/lib/stores/chat-event-cache'
import { getApiBaseUrl } from '@/lib/api/client'
import { refreshCliServerStatus } from '@/lib/api/cli'
import {
  runCopilotFixWithAi,
  type CopilotFixWithAIErrorResponse,
  type CopilotPatchResponse,
  type CopilotToolEvent,
} from '@/lib/api/copilot'
import { getProject, type AgentDescriptor } from '@/lib/api/projects'
import { getFile } from '@/lib/api/files'
import { compileLatex, getLatexBuildLogText, listLatexBuilds, type LatexBuildError } from '@/lib/api/latex'
import {
  createSession,
  deleteSession,
  getLatestSession,
  getSession,
  getSessionFiles,
  applySessionPatch,
  stopSession,
  submitClarifySelection,
  submitToolOutput,
  type SessionListItem,
  type SessionFileResponse,
  type SessionStatus,
  type SessionAgentSummary,
} from '@/lib/api/sessions'
import {
  buildQuestSessionId,
  getQuestLatestSession,
  getQuestSessionEventsOnly,
  isQuestSessionId,
  resolveQuestResumeToken,
  shouldUseQuestSessionCompat,
} from '@/lib/api/quest-session-compat'
import { isQuestRuntimeSurface } from '@/lib/runtime/quest-runtime'
import { useTabsStore } from '@/lib/stores/tabs'
import { useFileTreeStore } from '@/lib/stores/file-tree'
import { useFileContentStore } from '@/lib/stores/file-content'
import { useOpenFile } from '@/hooks/useOpenFile'
import { useCliStore } from '@/lib/plugins/cli/stores/cli-store'
import { applyLabCliToolEffect } from '@/lib/plugins/lab/lib/cli-effect-dispatcher'
import { parseCliFileId } from '@/lib/api/cli-file-id'
import { toCliResourcePath, toFilesResourcePath } from '@/lib/utils/resource-paths'
import { useAuthStore } from '@/lib/stores/auth'
import { useI18n } from '@/lib/i18n/useI18n'
import { useToast } from '@/components/ui/toast'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { SpotlightCard } from '@/components/react-bits'
import { useSessionList } from '@/lib/hooks/useSessionList'
import { copyToClipboard } from '@/lib/clipboard'
import { handleUIEffect, previewPdfToolEffect } from '@/lib/ai/effect-dispatcher'
import { COPILOT_FILES_ENABLED } from '@/lib/feature-flags'
import { decodeHtmlEntities } from './lib/markdown'
import {
  LAB_QUESTION_ANSWERED_EVENT,
  type LabQuestionAnsweredDetail,
} from './lib/question-events'
import {
  applyChatEvent,
  coerceRole,
  coerceTimestamp,
  createMessageId,
  getEventSequence,
  normalizeAttachments,
} from './lib/chat-event-reducer'
import type {
  AgentSSEEvent,
  AttachmentInfo,
  AttachmentsEventData,
  ChatSurface,
  EventMetadata,
  ErrorEventData,
  ExecutionTarget,
  MessageEventData,
  PlanEventData,
  RecoveryEventData,
  ReasoningEventData,
  StepEventData,
  TaskPlanItem,
  TitleEventData,
  ToolEventData,
} from '@/lib/types/chat-events'
import { buildCopilotFilePath } from './lib/file-operations'
import { buildChatTurns, type ChatTurn, type ChatTurnBlock } from './lib/chat-turns'
import { getMcpToolKind } from './lib/mcp-tools'
import { mergeApplyPatchChanges, parseApplyPatchFiles } from './lib/patch-utils'
import { resolveToolCategory } from './lib/tool-map'
import { ChatScrollProvider } from './lib/chat-scroll-context'
import { ensureDefaultAgent, resolveAgentMention } from '@/lib/utils/agent-mentions'
import type {
  AttachmentsContent,
  ChatMessageItem,
  ClarifyQuestionContent,
  ClarifyQuestionOption,
  MessageContent,
  PatchReviewContent,
  PatchReviewFile,
  QuestionPromptAnswerMap,
  QuestionPromptContent,
  ReasoningContent,
  StatusContent,
  StepContent,
  ToolContent,
} from './types'
import { ChatBox } from './components/ChatBox'
import { ChatMessage } from './components/ChatMessage'
import { ThinkingIndicator } from './components/ThinkingIndicator'
import OrbitLogoStatus from './components/OrbitLogoStatus'
import { PlanPanel } from './components/PlanPanel'
import { SessionFilesDialog } from './components/SessionFilesDialog'
import { SessionListPanel } from './components/SessionListPanel'
import { ToolPanel } from './components/ToolPanel'
import { CopilotContextTray } from './components/CopilotContextTray'
import type {
  AiManusChatActions,
  AiManusChatMeta,
  CopilotFocusedIssue,
  CopilotPrefill,
  CopilotSuggestionItem,
  CopilotSuggestionPayload,
} from './view-types'
import {
  useWorkspaceSurfaceStore,
  type WorkspaceSelectionReference,
} from '@/lib/stores/workspace-surface'

const MAX_RENDERED_MESSAGES = 120
// Keep scroll behavior aligned across surfaces.
const COPILOT_VIRTUALIZE_THRESHOLD = Number.MAX_SAFE_INTEGER
const DEFAULT_MESSAGE_HEIGHT = 120
const AUTO_FOLLOW_THRESHOLD_PX = 120
const APPEND_STAGGER_MS = 50
const APPEND_STAGGER_MAX = 6
const TOOL_PANEL_BREAKPOINT = 1024
const TOOL_PANEL_DEFAULT_SIZE = 40
const TOOL_PANEL_MIN_SIZE = 26
const TOOL_PANEL_MAX_SIZE = 62
const DISPLAY_LOCK_TIMEOUT_MS = 8000
const MAX_DISPLAY_LOCK_MS = 60000
const REASONING_STALL_TIMEOUT_MS = 8000
const MESSAGE_FLUSH_MS = 26
const MAX_RECENT_FILES = 64
const THINKING_TURN_ID = '__thinking__'
const LOAD_FULL_HISTORY_TURN_ID = '__load_full_history__'

const CLI_OFFLINE_MESSAGE = 'CLI server offline. Please ensure the CLI is running.'

type VirtualTurnRowData = {
  items: ChatTurn[]
  setSize: (rowIndex: number, size: number) => void
  render: (turn: ChatTurn) => ReactNode
  messageMaxWidthClass: string
}

type WorkspaceFocusedIssueSnapshot = {
  kind: 'latex_error'
  resourcePath?: string
  resourceName?: string
  line?: number
  message: string
  severity: 'error' | 'warning'
}

type WorkspaceOpenTabSnapshot = {
  tabId: string
  title: string
  type: string
  pluginId?: string
  resourceId?: string | null
  resourcePath?: string
  resourceName?: string
  mimeType?: string | null
  isActive: boolean
  contentKind?: string
  documentMode?: string
  pageNumber?: number
  status?: string[]
  focusedIssue?: WorkspaceFocusedIssueSnapshot
}

const VirtualTurnRow = memo(function VirtualTurnRow({
  index,
  style,
  data,
}: ListChildComponentProps<VirtualTurnRowData>) {
  const rowRef = useRef<HTMLDivElement | null>(null)
  const { items, render, setSize, messageMaxWidthClass } = data
  const turn = items[index]

  useEffect(() => {
    const node = rowRef.current
    if (!node) return
    const update = () => setSize(index, node.getBoundingClientRect().height)
    update()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(update)
    observer.observe(node)
    return () => observer.disconnect()
  }, [index, setSize, turn.id])

  return (
    <div style={style}>
      <div ref={rowRef} className={cn('mx-auto w-full pb-3', messageMaxWidthClass)}>
        {render(turn)}
      </div>
    </div>
  )
})

VirtualTurnRow.displayName = 'VirtualTurnRow'

const normalizeCliErrorMessage = (message: string) => {
  const lower = message.toLowerCase()
  if (
    (lower.includes('cli server') && (lower.includes('not connected') || lower.includes('offline'))) ||
    lower.includes('cli_server_not_connected') ||
    lower.includes('cli_server_offline')
  ) {
    return CLI_OFFLINE_MESSAGE
  }
  return message
}

function buildMcpStatusMessageId(
  eventId?: string | null,
  toolCallId?: string | null,
  timestamp?: number | null
) {
  const trimmedToolCallId = toolCallId?.trim()
  if (trimmedToolCallId) return `mcp-status-${trimmedToolCallId}`
  const trimmedEventId = eventId?.trim()
  if (trimmedEventId) return `mcp-status-${trimmedEventId}`
  if (typeof timestamp === 'number' && !Number.isNaN(timestamp)) {
    return `mcp-status-${timestamp}`
  }
  return `mcp-status-${createMessageId('status')}`
}
const BUFFER_PASSTHROUGH_EVENTS = new Set([
  'recovery',
  'wait',
  'title',
  'done',
  'attachments',
  'plan',
  'step',
  'receipt',
  'status',
])

type DisplayLockKind = 'assistant' | 'reasoning' | 'tool' | 'status'

const WELCOME_INTRO_CARDS = [
  { title: 'Plan', icon: Sparkles },
  { title: 'Terminal', icon: Terminal },
  { title: 'Sessions', icon: PanelLeft },
] as const

const GREETING_TEMPLATES = [
  'Hello, {name}',
  '{name} is thinking...',
  'Welcome back, {name}',
  'Good to see you, {name}',
  'Ready when you are, {name}',
  "Let's explore, {name}",
  'What should we build, {name}?',
  'Your lab is ready, {name}',
  'Tell me your idea, {name}',
  'New task? I am listening, {name}',
] as const

const CLARIFY_FALLBACK_OPTIONS: ClarifyQuestionOption[] = [
  { id: '1', label: 'Concise bullets' },
  { id: '2', label: 'Detailed steps' },
  { id: '3', label: 'Include examples' },
  { id: '4', label: 'Provide code snippets' },
  { id: '5', label: 'Focus on tradeoffs' },
]

const CLARIFY_TEMPLATE_PATTERN = /\[\[clarify\]\]/i

type SessionPreferences = {
  pinned: string[]
  renamed: Record<string, string>
}

const EMPTY_SESSION_PREFERENCES: SessionPreferences = {
  pinned: [],
  renamed: {},
}

function normalizeSessionPreferences(raw: unknown): SessionPreferences {
  if (!raw || typeof raw !== 'object') return EMPTY_SESSION_PREFERENCES
  const record = raw as Partial<SessionPreferences>
  const pinned =
    Array.isArray(record.pinned) && record.pinned.length > 0
      ? record.pinned.filter((id) => typeof id === 'string' && id.trim())
      : []
  const renamed: Record<string, string> = {}
  if (record.renamed && typeof record.renamed === 'object') {
    Object.entries(record.renamed).forEach(([key, value]) => {
      if (typeof value !== 'string') return
      const trimmed = value.trim()
      if (!trimmed) return
      renamed[key] = trimmed
    })
  }
  return {
    pinned: Array.from(new Set(pinned)),
    renamed,
  }
}

function loadSessionPreferences(key: string | null): SessionPreferences {
  if (!key || typeof window === 'undefined') return EMPTY_SESSION_PREFERENCES
  const raw = window.localStorage.getItem(key)
  if (!raw) return EMPTY_SESSION_PREFERENCES
  try {
    return normalizeSessionPreferences(JSON.parse(raw))
  } catch {
    return EMPTY_SESSION_PREFERENCES
  }
}

function saveSessionPreferences(key: string | null, prefs: SessionPreferences) {
  if (!key || typeof window === 'undefined') return
  window.localStorage.setItem(key, JSON.stringify(prefs))
}

function pickGreetingTemplate() {
  const index = Math.floor(Math.random() * GREETING_TEMPLATES.length)
  return GREETING_TEMPLATES[index]
}

type ClarifyFallbackPrompt = {
  question: string
  options: ClarifyQuestionOption[]
  multi: boolean
  defaultSelected: string[]
  missingFields: string[]
}

type ClarifyPromptState = ClarifyFallbackPrompt & {
  messageId: string
  toolCallId?: string
  source: 'backend' | 'local'
  originMessageId?: string
  originMessage?: string
  originMetadata?: Record<string, unknown>
  originAttachments?: AttachmentInfo[]
  sessionId?: string
}

function mergeClarifyQuery(
  message: string,
  selectedLabels: string[],
  missingFields?: string[]
) {
  if (selectedLabels.length === 0) return message
  const fields = (missingFields ?? []).filter((field) => typeof field === 'string' && field.trim())
  const labelText = selectedLabels.join(', ')
  if (fields.length > 0) {
    return `${message}\n\nConstraints for ${fields.join(', ')}: ${labelText}.`
  }
  return `${message}\n\nAdditional constraints: ${labelText}.`
}

function buildFallbackClarifyPrompt(message: string): ClarifyFallbackPrompt | null {
  const trimmed = message.trim()
  if (!trimmed) return null
  if (CLARIFY_TEMPLATE_PATTERN.test(trimmed)) {
    return {
      question: 'Pick constraints to refine your request.',
      options: CLARIFY_FALLBACK_OPTIONS,
      multi: true,
      defaultSelected: [],
      missingFields: [],
    }
  }
  const hasMarkers = /[0-9]/.test(trimmed) || /[\\/:._#]/.test(trimmed)
  const wordCount = trimmed.split(/\s+/).filter(Boolean).length
  const tooShort = wordCount <= 3 || trimmed.length <= 10
  if (tooShort && !hasMarkers) {
    return {
      question: 'Pick constraints to refine your request.',
      options: CLARIFY_FALLBACK_OPTIONS,
      multi: true,
      defaultSelected: [],
      missingFields: [],
    }
  }
  return null
}

const VNCViewer = dynamic(
  () => import('@/components/chat/toolViews/VNCViewer').then((mod) => mod.VNCViewer),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full w-full items-center justify-center text-sm text-[var(--text-tertiary)]">
        Loading sandbox view...
      </div>
    ),
  }
)

const NotebookChatBox = dynamic(
  () => import('./components/NotebookChatBox').then((mod) => mod.NotebookChatBox),
  {
    ssr: false,
    loading: () => null,
  }
)

function normalizeTimestampMs(timestamp?: number) {
  if (!timestamp) return 0
  return timestamp < 1e12 ? timestamp * 1000 : timestamp
}

function normalizeRecentPath(value: string) {
  if (!value) return ''
  return value.trim().replace(/\\/g, '/').replace(/\/+$/, '')
}

function extractCustomString(
  customData: Record<string, unknown> | undefined,
  keys: string[]
): string | null {
  if (!customData) return null
  for (const key of keys) {
    const value = customData[key]
    if (typeof value !== 'string') continue
    const trimmed = value.trim()
    if (trimmed) return trimmed
  }
  return null
}

function extractCustomFileId(customData: Record<string, unknown> | undefined): string | null {
  return extractCustomString(customData, ['fileId', 'file_id', 'openFileId', 'mainFileId'])
}

function extractCustomFilePath(customData: Record<string, unknown> | undefined): string | null {
  return extractCustomString(customData, ['filePath', 'file_path', 'path', 'resourcePath'])
}

function hasConcreteResourcePath(value?: string | null) {
  const normalized = normalizeRecentPath(value ?? '')
  return Boolean(normalized) && normalized !== '/FILES' && normalized !== '/CLIFILES'
}

function normalizeSessionStatus(status?: string | null): SessionStatus | null {
  if (!status) return null
  if (
    status === 'pending' ||
    status === 'running' ||
    status === 'waiting' ||
    status === 'completed' ||
    status === 'failed'
  ) {
    return status
  }
  return null
}

function isSessionStatusRunning(status?: SessionStatus | null): boolean {
  return status === 'running'
}

function isSessionStatusActive(status?: SessionStatus | null): boolean {
  return isSessionStatusRunning(status) || status === 'waiting'
}

function normalizeToolFunctionName(value: string): string {
  const raw = value.trim().toLowerCase()
  if (!raw) return ''
  if (!raw.startsWith('mcp__')) return raw
  const parts = raw.split('__')
  return parts[parts.length - 1] || raw
}

function coerceBoolean(value: unknown): boolean {
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return value !== 0
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase()
    if (['true', '1', 'yes', 'y'].includes(normalized)) return true
    if (['false', '0', 'no', 'n'].includes(normalized)) return false
  }
  return false
}

function coerceStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter((item) => item.length > 0)
  }
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (!trimmed) return []
    try {
      const parsed = JSON.parse(trimmed)
      if (Array.isArray(parsed)) {
        return parsed.map((item) => String(item).trim()).filter((item) => item.length > 0)
      }
    } catch {
      // fall through
    }
    if (trimmed.includes(',')) {
      return trimmed
        .split(',')
        .map((item) => item.trim())
        .filter((item) => item.length > 0)
    }
    return [trimmed]
  }
  if (value == null) return []
  const normalized = String(value).trim()
  return normalized ? [normalized] : []
}

function normalizeClarifyOptions(raw: unknown): ClarifyQuestionOption[] {
  if (!Array.isArray(raw)) return []
  const options: ClarifyQuestionOption[] = []
  raw.forEach((entry, index) => {
    if (typeof entry === 'string' || typeof entry === 'number') {
      const label = String(entry).trim()
      if (!label) return
      options.push({ id: String(index + 1), label })
      return
    }
    if (!entry || typeof entry !== 'object') return
    const record = entry as Record<string, unknown>
    const rawId = record.id ?? record.value ?? record.name ?? record.label ?? index + 1
    const rawLabel = record.label ?? record.name ?? record.value ?? record.id ?? rawId
    const id = String(rawId ?? index + 1).trim()
    const label = String(rawLabel ?? id).trim()
    if (!id || !label) return
    options.push({ id, label })
  })
  return options
}

function resolveClarifySelections(
  answerValue: unknown,
  options: ClarifyQuestionOption[]
): { selections: string[]; selectedLabels: string[] } {
  const rawSelections = Array.isArray(answerValue)
    ? answerValue
    : answerValue != null
      ? [answerValue]
      : []
  const optionIdSet = new Set(options.map((option) => option.id))
  const labelLookup = new Map(options.map((option) => [option.label.toLowerCase(), option.id]))
  const selectedSet = new Set<string>()
  const selections: string[] = []

  rawSelections.forEach((item) => {
    const normalized = typeof item === 'string' ? item.trim() : String(item).trim()
    if (!normalized) return
    if (optionIdSet.has(normalized)) {
      if (!selectedSet.has(normalized)) {
        selectedSet.add(normalized)
        selections.push(normalized)
      }
      return
    }
    const numeric = Number(normalized)
    if (!Number.isNaN(numeric) && Number.isFinite(numeric)) {
      const index = Math.max(0, Math.floor(numeric) - 1)
      const option = options[index]
      if (option && !selectedSet.has(option.id)) {
        selectedSet.add(option.id)
        selections.push(option.id)
      }
      return
    }
    const labelMatch = labelLookup.get(normalized.toLowerCase())
    if (labelMatch && !selectedSet.has(labelMatch)) {
      selectedSet.add(labelMatch)
      selections.push(labelMatch)
    }
  })

  const labelMap = new Map(options.map((option) => [option.id, option.label]))
  const selectedLabels = selections
    .map((id) => labelMap.get(id))
    .filter((label): label is string => Boolean(label))
  return { selections, selectedLabels }
}

function getEventOrderTimestamp(event: AgentSSEEvent): number | null {
  const data = event.data as unknown as Record<string, unknown>
  if (typeof data.timestamp === 'number' && Number.isFinite(data.timestamp)) return data.timestamp
  if (typeof data.created_at === 'string' && data.created_at) {
    return coerceTimestamp(data.created_at)
  }
  return null
}

function sortHydratedEvents(events: AgentSSEEvent[]): AgentSSEEvent[] {
  const items = events.map((event, index) => ({
    event,
    index,
    seq: getEventSequence(event),
    timestamp: getEventOrderTimestamp(event),
  }))
  const hasSeq = items.some((item) => item.seq != null)
  const hasTimestamp = items.some((item) => item.timestamp != null)
  if (!hasSeq && !hasTimestamp) return events
  items.sort((a, b) => {
    if (hasSeq) {
      if (a.seq != null && b.seq != null && a.seq !== b.seq) return a.seq - b.seq
      if (a.seq != null && b.seq == null) return -1
      if (a.seq == null && b.seq != null) return 1
    }
    if (a.timestamp != null && b.timestamp != null && a.timestamp !== b.timestamp) {
      return a.timestamp - b.timestamp
    }
    if (a.timestamp != null && b.timestamp == null) return -1
    if (a.timestamp == null && b.timestamp != null) return 1
    return a.index - b.index
  })
  return items.map((item) => item.event)
}

function coerceReasoningKind(value: unknown): 'summary' | 'full' {
  return value === 'summary' ? 'summary' : 'full'
}

const STEP_STATUS_VALUES = new Set([
  'pending',
  'running',
  'completed',
  'failed',
  'blocked',
  'paused',
])

function coerceStepStatus(value: unknown): StepEventData['status'] {
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase()
    if (STEP_STATUS_VALUES.has(normalized)) {
      return normalized as StepEventData['status']
    }
  }
  return 'pending'
}

function buildReasoningKey(reasoningId: string, kind: 'summary' | 'full') {
  return `${reasoningId}:${kind}`
}

function buildReasoningStreamKey(
  reasoningId: string,
  kind: 'summary' | 'full',
  streamId: unknown
) {
  const streamValue = typeof streamId === 'string' ? streamId.trim() : ''
  if (streamValue) {
    return `stream:${streamValue}`
  }
  return `reasoning:${buildReasoningKey(reasoningId, kind)}`
}

function extractFileEffectData(toolData: Partial<ToolEventData>) {
  const args =
    toolData.args && typeof toolData.args === 'object' && !Array.isArray(toolData.args)
      ? (toolData.args as Record<string, unknown>)
      : {}
  const content =
    toolData.content && typeof toolData.content === 'object' && !Array.isArray(toolData.content)
      ? (toolData.content as Record<string, unknown>)
      : {}

  const fileId =
    (typeof args.file_id === 'string' && args.file_id) ||
    (typeof args.fileId === 'string' && args.fileId) ||
    (typeof content.file_id === 'string' && content.file_id) ||
    (typeof content.fileId === 'string' && content.fileId) ||
    undefined
  const filePath =
    (typeof args.file === 'string' && args.file) ||
    (typeof args.file_path === 'string' && args.file_path) ||
    (typeof args.path === 'string' && args.path) ||
    (typeof args.filePath === 'string' && args.filePath) ||
    (typeof content.file === 'string' && content.file) ||
    (typeof content.file_path === 'string' && content.file_path) ||
    (typeof content.filePath === 'string' && content.filePath) ||
    undefined
  const fileName =
    (typeof args.file_name === 'string' && args.file_name) ||
    (typeof args.fileName === 'string' && args.fileName) ||
    (typeof content.file_name === 'string' && content.file_name) ||
    (typeof content.fileName === 'string' && content.fileName) ||
    undefined

  const diff =
    typeof content.diff === 'object' && content.diff ? (content.diff as Record<string, unknown>) : undefined
  const changeType =
    typeof content.changeType === 'string' ? (content.changeType as 'create' | 'update' | 'delete') : undefined

  return { fileId, filePath, fileName, content, diff, changeType }
}

function coerceOptionalNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return undefined
}

function buildPdfToolPreview(toolData: Partial<ToolEventData>) {
  const functionName = typeof toolData.function === 'string' ? toolData.function : ''
  const normalizedFunctionName = functionName.startsWith('rebuttal_pdf_')
    ? `pdf_${functionName.slice('rebuttal_pdf_'.length)}`
    : functionName
  if (!normalizedFunctionName.startsWith('pdf_')) return null
  const args =
    toolData.args && typeof toolData.args === 'object' && !Array.isArray(toolData.args)
      ? (toolData.args as Record<string, unknown>)
      : {}
  const { fileId, filePath, fileName } = extractFileEffectData(toolData)
  if (!fileId && !filePath && !fileName) return null

  const rawPage =
    coerceOptionalNumber(args.page) ??
    coerceOptionalNumber(args.page_number) ??
    coerceOptionalNumber(args.pageNumber)
  const page = rawPage && rawPage > 0 ? Math.floor(rawPage) : undefined
  const annotationId =
    typeof args.annotation_id === 'string'
      ? args.annotation_id
      : typeof args.annotationId === 'string'
        ? args.annotationId
        : undefined
  const mode: 'guide' | 'annotate' | undefined =
    normalizedFunctionName === 'pdf_guide'
      ? 'guide'
      : normalizedFunctionName === 'pdf_annotate'
        ? 'annotate'
        : undefined

  return {
    fileId,
    filePath,
    fileName,
    page,
    annotationId,
    mode,
  }
}

function buildFallbackEffects(toolData: Partial<ToolEventData>, status: string) {
  if (status !== 'called') return []
  const functionName = typeof toolData.function === 'string' ? toolData.function : ''
  const { fileId, filePath, fileName, content, diff, changeType } = extractFileEffectData(toolData)
  if (!fileId && !filePath) return []

  if (functionName === 'file_read' || functionName === 'file_info') {
    return [
      {
        name: 'file:read',
        data: {
          fileId,
          filePath,
          fileName,
        },
      },
    ]
  }

  if (functionName === 'file_write' || functionName === 'file_patch') {
    const created = typeof content?.created === 'boolean' ? content.created : undefined
    const derivedChangeType = changeType ?? (created ? 'create' : 'update')
    return [
      {
        name: 'file:write',
        data: {
          fileId,
          filePath,
          fileName,
          ...(created !== undefined ? { created } : {}),
          ...(derivedChangeType ? { changeType: derivedChangeType } : {}),
          ...(diff ? { diff } : {}),
        },
      },
    ]
  }

  if (functionName === 'file_delete') {
    return [
      {
        name: 'file:delete',
        data: {
          fileId,
          filePath,
          fileName,
          changeType: changeType ?? 'delete',
          ...(diff ? { diff } : {}),
        },
      },
    ]
  }

  return []
}

function isPushFileTool(toolData: Partial<ToolEventData>) {
  const functionName =
    typeof toolData.function === 'string' ? toolData.function.toLowerCase() : ''
  if (functionName !== 'file_write') return false
  const args =
    toolData.args && typeof toolData.args === 'object' && !Array.isArray(toolData.args)
      ? (toolData.args as Record<string, unknown>)
      : {}
  const sourcePath = args.source_path ?? args.sourcePath
  return typeof sourcePath === 'string' && sourcePath.trim().length > 0
}

function buildPatchReviewContent(
  toolData: Partial<ToolEventData>,
  toolCallId: string
): PatchReviewContent | null {
  const args =
    toolData.args && typeof toolData.args === 'object' && !Array.isArray(toolData.args)
      ? (toolData.args as Record<string, unknown>)
      : {}
  const patch =
    typeof args.patch === 'string'
      ? args.patch
      : typeof (toolData.content as Record<string, unknown>)?.patch === 'string'
        ? ((toolData.content as Record<string, unknown>).patch as string)
        : ''
  if (!patch.trim()) return null
  const files = parseApplyPatchFiles(patch)
  const targetPath =
    typeof args.target_path === 'string'
      ? args.target_path
      : typeof args.targetPath === 'string'
        ? args.targetPath
        : undefined
  const rationale = typeof args.rationale === 'string' ? args.rationale : undefined
  const timestamp = coerceTimestamp(toolData.timestamp)
  return {
    timestamp,
    metadata: toolData.metadata,
    patch,
    files,
    status: 'pending',
    toolCallId,
    targetPath,
    rationale,
  }
}

function buildPatchReviewFromCopilotPatch(
  patch: CopilotPatchResponse,
  timestamp: number,
  toolCallId?: string
): PatchReviewContent | null {
  const changes = Array.isArray(patch?.changes) ? patch.changes : []
  const mergedPatch = mergeApplyPatchChanges(changes)
  if (!mergedPatch.trim()) return null
  const files = parseApplyPatchFiles(mergedPatch)
  if (files.length === 0) return null
  const rationaleParts: string[] = []
  if (typeof patch.title === 'string' && patch.title.trim()) {
    rationaleParts.push(patch.title.trim())
  }
  if (Array.isArray(patch.explanations)) {
    patch.explanations.forEach((item) => {
      if (typeof item === 'string' && item.trim()) {
        rationaleParts.push(item.trim())
      }
    })
  }
  const rationale = rationaleParts.length > 0 ? rationaleParts.join(' · ') : undefined
  return {
    timestamp,
    patch: mergedPatch,
    files,
    status: 'pending',
    toolCallId,
    rationale,
  }
}

const RESTORE_EVENT_TYPES = new Set([
  'message',
  'tool',
  'step',
  'status',
  'reasoning',
  'plan',
  'recovery',
  'error',
  'done',
  'title',
  'wait',
  'attachments',
  'receipt',
])

function normalizeRestoredEvent(raw: unknown): AgentSSEEvent | null {
  if (!raw || typeof raw !== 'object') return null
  const record = raw as {
    event?: unknown
    event_type?: unknown
    type?: unknown
    data?: unknown
    event_json?: unknown
    payload?: unknown
    event_id?: unknown
    timestamp?: unknown
    seq?: unknown
    created_at?: unknown
  }

  const eventType =
    typeof record.event === 'string'
      ? record.event
      : typeof record.event_type === 'string'
        ? record.event_type
        : typeof record.type === 'string'
          ? record.type
          : null

  if (!eventType || !RESTORE_EVENT_TYPES.has(eventType)) return null

  let data = record.data ?? record.event_json ?? record.payload ?? {}
  if (typeof data === 'string') {
    try {
      data = JSON.parse(data)
    } catch {
      data = {}
    }
  }

  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    data = {}
  }

  const normalized = { ...(data as Record<string, unknown>) }
  if (!('event_id' in normalized) && typeof record.event_id === 'string') {
    normalized.event_id = record.event_id
  }
  if (!('timestamp' in normalized) && record.timestamp != null) {
    normalized.timestamp = record.timestamp
  }
  if (!('seq' in normalized) && typeof record.seq === 'number') {
    normalized.seq = record.seq
  }
  if (!('created_at' in normalized) && record.created_at != null) {
    normalized.created_at = String(record.created_at)
  }

  return {
    event: eventType as AgentSSEEvent['event'],
    data: normalized as unknown as AgentSSEEvent['data'],
  }
}

function coerceRestoredEvent(raw: unknown): AgentSSEEvent | null {
  const normalized = normalizeRestoredEvent(raw)
  if (normalized) return normalized

  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw)
      return normalizeRestoredEvent(parsed)
    } catch {
      return null
    }
  }

  if (!raw || typeof raw !== 'object') return null
  const record = raw as {
    event?: unknown
    event_type?: unknown
    type?: unknown
    data?: unknown
    event_json?: unknown
    payload?: unknown
  }

  const eventType =
    typeof record.event === 'string'
      ? record.event
      : typeof record.event_type === 'string'
        ? record.event_type
        : typeof record.type === 'string'
          ? record.type
          : null
  const dataCandidate = record.data ?? record.event_json ?? record.payload ?? null

  if (
    eventType &&
    RESTORE_EVENT_TYPES.has(eventType) &&
    dataCandidate &&
    typeof dataCandidate === 'object' &&
    !Array.isArray(dataCandidate)
  ) {
    return {
      event: eventType as AgentSSEEvent['event'],
      data: dataCandidate as AgentSSEEvent['data'],
    }
  }

  if (dataCandidate && typeof dataCandidate === 'string') {
    try {
      const parsed = JSON.parse(dataCandidate)
      if (
        parsed &&
        typeof parsed === 'object' &&
        !Array.isArray(parsed) &&
        eventType &&
        RESTORE_EVENT_TYPES.has(eventType)
      ) {
        return {
          event: eventType as AgentSSEEvent['event'],
          data: parsed as AgentSSEEvent['data'],
        }
      }
    } catch {
      return null
    }
  }

  if (record.data && typeof record.data === 'object' && !Array.isArray(record.data)) {
    const nested = record.data as {
      event?: unknown
      event_type?: unknown
      type?: unknown
      data?: unknown
      event_json?: unknown
      payload?: unknown
    }
    const nestedType =
      typeof nested.event === 'string'
        ? nested.event
        : typeof nested.event_type === 'string'
          ? nested.event_type
          : typeof nested.type === 'string'
            ? nested.type
            : null
    const nestedData = nested.data ?? nested.event_json ?? nested.payload ?? null
    if (
      nestedType &&
      RESTORE_EVENT_TYPES.has(nestedType) &&
      nestedData &&
      typeof nestedData === 'object' &&
      !Array.isArray(nestedData)
    ) {
      return {
        event: nestedType as AgentSSEEvent['event'],
        data: nestedData as AgentSSEEvent['data'],
      }
    }
  }

  return null
}

type SessionAgentIndex = {
  byInstanceId: Map<string, SessionAgentSummary>
  byAgentId: Map<string, SessionAgentSummary>
  fallback: SessionAgentSummary | null
}

const SESSION_METADATA_KEYS: Array<keyof EventMetadata> = [
  'surface',
  'reply_to_surface',
  'execution_target',
  'cli_server_id',
  'lab_mode',
  'quest_id',
  'quest_node_id',
]

const buildSessionAgentIndex = (agents?: SessionAgentSummary[] | null): SessionAgentIndex => {
  const byInstanceId = new Map<string, SessionAgentSummary>()
  const byAgentId = new Map<string, SessionAgentSummary>()
  const list = Array.isArray(agents) ? agents : []
  list.forEach((agent) => {
    if (agent?.agent_instance_id) {
      byInstanceId.set(String(agent.agent_instance_id), agent)
    }
    if (agent?.agent_id) {
      byAgentId.set(String(agent.agent_id), agent)
    }
  })
  return {
    byInstanceId,
    byAgentId,
    fallback: list.length === 1 ? list[0] : null,
  }
}

const hydrateEventMetadata = (
  event: AgentSSEEvent,
  sessionMetadata?: Record<string, unknown> | null,
  agentIndex?: SessionAgentIndex
) => {
  if (!event?.data || typeof event.data !== 'object') return event
  const data = { ...(event.data as unknown as Record<string, unknown>) }
  const rawMetadata = data.metadata
  const metadata =
    rawMetadata && typeof rawMetadata === 'object' && !Array.isArray(rawMetadata)
      ? { ...(rawMetadata as Record<string, unknown>) }
      : {}
  const role = typeof (data as { role?: unknown }).role === 'string' ? String((data as { role?: unknown }).role) : ''
  const senderType = typeof metadata.sender_type === 'string' ? metadata.sender_type.toLowerCase() : ''
  const isMessageEvent = event.event === 'message' || event.event === 'attachments'
  const roleValue = role.toLowerCase()
  const isAgentEvent =
    senderType === 'agent' ||
    Boolean(metadata.agent_id || metadata.agent_instance_id) ||
    (isMessageEvent ? roleValue === 'assistant' : true)

  if (sessionMetadata && typeof sessionMetadata === 'object') {
    SESSION_METADATA_KEYS.forEach((key) => {
      if (metadata[key] != null) return
      const value = (sessionMetadata as Record<string, unknown>)[key]
      if (value != null) {
        metadata[key] = value
      }
    })
  }

  if (isAgentEvent && agentIndex) {
    const instanceId =
      typeof metadata.agent_instance_id === 'string' ? metadata.agent_instance_id : null
    const agentId = typeof metadata.agent_id === 'string' ? metadata.agent_id : null
    const agent =
      (instanceId ? agentIndex.byInstanceId.get(instanceId) : null) ||
      (agentId ? agentIndex.byAgentId.get(agentId) : null) ||
      agentIndex.fallback
    if (agent) {
      if (metadata.agent_instance_id == null && agent.agent_instance_id) {
        metadata.agent_instance_id = agent.agent_instance_id
      }
      if (metadata.agent_id == null && agent.agent_id) {
        metadata.agent_id = agent.agent_id
      }
      if (metadata.agent_label == null && agent.agent_label) {
        metadata.agent_label = agent.agent_label
      }
      if (metadata.agent_display_name == null && agent.agent_display_name) {
        metadata.agent_display_name = agent.agent_display_name
      }
      if (metadata.agent_logo == null && agent.agent_logo) {
        metadata.agent_logo = agent.agent_logo
      }
      if (metadata.agent_avatar_color == null && agent.agent_avatar_color) {
        metadata.agent_avatar_color = agent.agent_avatar_color
      }
      if (metadata.agent_role == null && agent.agent_role) {
        metadata.agent_role = agent.agent_role
      }
      if (metadata.agent_source == null && agent.agent_source) {
        metadata.agent_source = agent.agent_source
      }
      if (metadata.agent_engine == null && agent.agent_engine) {
        metadata.agent_engine = agent.agent_engine
      }
    }
  }

  if (Object.keys(metadata).length > 0) {
    data.metadata = metadata
  } else {
    delete data.metadata
  }

  return { ...event, data } as unknown as AgentSSEEvent
}

function normalizePlanHistory(raw: unknown): PlanEventData[] {
  let source = raw
  if (typeof source === 'string') {
    try {
      source = JSON.parse(source)
    } catch {
      source = null
    }
  }
  if (!Array.isArray(source)) return []
  return source
    .map((entry) => normalizePlanEntry(entry))
    .filter((entry): entry is PlanEventData => Boolean(entry))
}

function normalizePlanEntry(raw: unknown): PlanEventData | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const plan = raw as Partial<PlanEventData>
  const eventId =
    typeof plan.event_id === 'string' && plan.event_id ? plan.event_id : createMessageId('plan')
  const steps = normalizePlanSteps(plan.steps)
  const normalizedTaskPlan = normalizeTaskPlan(plan.task_plan)
  const hasSteps = steps.length > 0
  const hasTasks = Boolean(normalizedTaskPlan?.tasks?.length)
  if (!hasSteps && !hasTasks) return null
  return {
    ...(plan as PlanEventData),
    event_id: eventId,
    steps,
    timestamp: coerceTimestamp(plan.timestamp),
    ...(normalizedTaskPlan ? { task_plan: normalizedTaskPlan } : {}),
  }
}

function normalizePlanSteps(raw: unknown): StepEventData[] {
  let source = raw
  if (source && typeof source === 'object' && !Array.isArray(source)) {
    source = Object.values(source as Record<string, unknown>)
  }
  if (!Array.isArray(source)) return []
  return source
    .map((step, index) => {
      if (!step) return null
      if (typeof step === 'string') {
        const description = step.trim()
        if (!description) return null
        return {
          id: `step-${index + 1}`,
          status: 'pending',
          description,
        }
      }
      if (typeof step !== 'object' || Array.isArray(step)) return null
      const record = step as Record<string, unknown>
      const description =
        typeof record.description === 'string'
          ? record.description
          : typeof record.task === 'string'
            ? record.task
            : typeof record.title === 'string'
              ? record.title
              : typeof record.label === 'string'
                ? record.label
                : typeof record.text === 'string'
                  ? record.text
                  : ''
      const trimmed = description.trim()
      if (!trimmed) return null
      const id =
        typeof record.id === 'string' && record.id.trim()
          ? record.id.trim()
          : typeof record.step_id === 'string' && record.step_id.trim()
            ? record.step_id.trim()
            : `step-${index + 1}`
      const status = coerceStepStatus(record.status)
      return {
        ...(record as unknown as StepEventData),
        id,
        status,
        description: trimmed,
      }
    })
    .filter((step): step is StepEventData => Boolean(step))
}

function normalizeTaskPlan(raw: unknown): PlanEventData['task_plan'] | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined
  const taskPlan = raw as PlanEventData['task_plan']
  if (!taskPlan) return undefined
  let tasksSource: unknown = taskPlan.tasks
  if (tasksSource && typeof tasksSource === 'object' && !Array.isArray(tasksSource)) {
    tasksSource = Object.values(tasksSource as Record<string, unknown>)
  }
  if (typeof tasksSource === 'string') {
    try {
      tasksSource = JSON.parse(tasksSource)
    } catch {
      tasksSource = []
    }
  }
  const tasks = Array.isArray(tasksSource) ? tasksSource : []
  const normalizedTasks = tasks
    .map((task) => {
      if (!task || typeof task !== 'object') return null
      const record = task as Record<string, unknown>
      const rawTask =
        typeof record.task === 'string'
          ? record.task
          : typeof record.title === 'string'
            ? record.title
            : typeof record.name === 'string'
              ? record.name
              : ''
      const taskLabel = rawTask.trim()
      if (!taskLabel) return null
      const changeReason =
        typeof record.change_reason === 'string'
          ? record.change_reason
          : typeof record.changeReason === 'string'
            ? record.changeReason
            : typeof record.reason === 'string'
              ? record.reason
              : ''
      const detail =
        typeof record.detail === 'string'
          ? record.detail
          : typeof record.description === 'string'
            ? record.description
            : typeof record.details === 'string'
              ? record.details
              : ''
      const subTasksRaw = Array.isArray(record.sub_tasks)
        ? record.sub_tasks
        : Array.isArray(record.subtasks)
          ? record.subtasks
          : Array.isArray(record.subTasks)
            ? record.subTasks
            : []
      const subTasks = subTasksRaw
        .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
        .map((item) => item.trim())
      return {
        ...(task as TaskPlanItem),
        task: taskLabel,
        change_reason: changeReason ?? '',
        detail: detail ?? '',
        sub_tasks: subTasks,
      }
    })
    .filter(
      (task): task is TaskPlanItem => Boolean(task && typeof task.task === 'string')
    )
  return {
    ...(taskPlan as PlanEventData['task_plan']),
    tasks: normalizedTasks,
  }
}

function buildAttachmentKey(
  role: 'user' | 'assistant',
  timestamp: number,
  attachments: AttachmentInfo[]
) {
  const ids = attachments
    .map((file) => file.file_id || file.filename)
    .filter(Boolean)
    .sort()
    .join('|')
  return `${role}:${timestamp}:${ids}`
}

export function AiManusChatView({
  mode,
  projectId,
  readOnly,
  visible,
  prefill,
  suggestions,
  suggestionsDisabled,
  onSuggestionSelect,
  onActionsChange,
  onMetaChange,
  openToolPanel,
  hideCopilotGreeting,
  embedded,
  toolPanelMountId,
  sessionListMountId,
  sessionListEnabled,
  deferSessionList,
  uiMode,
  historyMode,
  historyPanelId,
  historyOpenOverride,
  onHistoryOpenChange,
  mentionablesOverride,
  defaultAgentOverride,
  mentionsEnabledOverride,
  enforcedMentionPrefix,
  lockedMentionPrefix,
  lockLeadingMentionSpace,
  messageMetadata,
  runtimeToggleEnabled,
  composerMode,
  composerFooter,
  leadMessage,
  onUserSubmit,
  layoutPadding,
  busyOverride,
}: {
  mode: ChatSurface
  projectId?: string | null
  readOnly?: boolean
  visible?: boolean
  prefill?: CopilotPrefill | null
  suggestions?: CopilotSuggestionPayload | null
  suggestionsDisabled?: boolean
  onSuggestionSelect?: (item: CopilotSuggestionItem) => void
  onActionsChange?: (actions: AiManusChatActions | null) => void
  onMetaChange?: (meta: AiManusChatMeta) => void
  openToolPanel?: boolean
  hideCopilotGreeting?: boolean
  embedded?: boolean
  toolPanelMountId?: string
  sessionListMountId?: string
  sessionListEnabled?: boolean
  deferSessionList?: boolean
  uiMode?: ChatSurface
  historyMode?: 'inline' | 'overlay'
  historyPanelId?: string
  historyOpenOverride?: boolean
  onHistoryOpenChange?: (open: boolean) => void
  mentionablesOverride?: AgentDescriptor[]
  defaultAgentOverride?: AgentDescriptor
  mentionsEnabledOverride?: boolean
  enforcedMentionPrefix?: string
  lockedMentionPrefix?: string
  lockLeadingMentionSpace?: boolean
  messageMetadata?: Record<string, unknown>
  runtimeToggleEnabled?: boolean
  composerMode?: 'text' | 'notebook'
  composerFooter?: ReactNode
  leadMessage?: ChatMessageItem | null
  onUserSubmit?: (message: string) => void
  layoutPadding?: 'default' | 'flush'
  busyOverride?: boolean
}) {
  const { addToast } = useToast()
  const { t } = useI18n('ai_manus')
  const { openFileInTab } = useOpenFile()
  const findNode = useFileTreeStore((state) => state.findNode)
  const findNodeByPath = useFileTreeStore((state) => state.findNodeByPath)
  const fileContentEntries = useFileContentStore((state) => state.entries)
  const tabs = useTabsStore((state) => state.tabs)
  const activeTab = useTabsStore((state) => state.tabs.find((tab) => tab.id === state.activeTabId))
  const setActiveTab = useTabsStore((state) => state.setActiveTab)
  const workspaceTabState = useWorkspaceSurfaceStore((state) => state.tabState)
  const activeTabReference = useWorkspaceSurfaceStore((state) => {
    if (!activeTab?.id) return null
    const referenceId = state.activeReferenceByTabId[activeTab.id]
    return referenceId ? state.references[referenceId] || null : null
  })
  const activeTabReferences = useWorkspaceSurfaceStore((state) => {
    if (!activeTab?.id) return []
    const ids = state.referencesByTabId[activeTab.id] || []
    return ids
      .map((id) => state.references[id])
      .filter((item): item is WorkspaceSelectionReference => Boolean(item))
  })
  const workspaceActiveIssues = useWorkspaceSurfaceStore((state) => state.activeIssueByTabId)
  const removeWorkspaceReference = useWorkspaceSurfaceStore((state) => state.removeReference)
  const cliServers = useCliStore((state) => state.servers)
  const loadCliServers = useCliStore((state) => state.loadServers)
  const refreshCliServers = useCliStore((state) => state.refreshServers)
  const activeCliServerId = useCliStore((state) => state.activeServerId)
  const cliStoreProjectId = useCliStore((state) => state.projectId)
  const cliLoading = useCliStore((state) => state.isLoading)
  const user = useAuthStore((state) => state.user)
  const onlineCliServers = useMemo(
    () => cliServers.filter((server) => server.status !== 'offline' && server.status !== 'error'),
    [cliServers]
  )

  const searchParams = useSearchParams()
  const requestedSessionId = searchParams?.get('copilotSession') ?? null

  const debugEnabled = useMemo(() => {
    if (typeof window === 'undefined') return false
    return process.env.NODE_ENV !== 'production' || window.localStorage.getItem('ds_debug_copilot') === '1'
  }, [])

  const uiSurface = uiMode ?? mode
  const fallbackHistoryPanelId = useId()
  const historyPanelIdValue = historyPanelId ?? fallbackHistoryPanelId
  const resolvedLayoutPadding = layoutPadding ?? 'default'
  const flushLayoutPadding = resolvedLayoutPadding === 'flush'
  const sessionSurface: ChatSurface =
    mode === 'welcome' && uiSurface === 'copilot' ? 'copilot' : mode
  const allowSurfaceFallback = sessionSurface === 'welcome' || sessionSurface === 'copilot'
  const surfaceSessionId = useChatSessionStore((state) =>
    projectId ? state.sessionIdsByProjectSurface[projectId]?.[sessionSurface] ?? null : null
  )
  const welcomeSessionId = useChatSessionStore((state) =>
    projectId ? state.sessionIdsByProjectSurface[projectId]?.welcome ?? null : null
  )
  const copilotSessionId = useChatSessionStore((state) =>
    projectId ? state.sessionIdsByProjectSurface[projectId]?.copilot ?? null : null
  )
  const legacySessionId = useChatSessionStore((state) =>
    projectId ? state.sessionIdsByProject[projectId] ?? null : null
  )
  const storedSessionId = allowSurfaceFallback
    ? surfaceSessionId ?? (sessionSurface === 'welcome' ? null : welcomeSessionId) ?? legacySessionId
    : surfaceSessionId
  const setSessionIdForSurface = useChatSessionStore((state) => state.setSessionIdForSurface)
  const clearSessionIdForSurface = useChatSessionStore((state) => state.clearSessionIdForSurface)
  const setLastEventId = useChatSessionStore((state) => state.setLastEventId)
  const executionTarget = useChatSessionStore((state) =>
    projectId ? state.executionTargetsByProject[projectId] ?? 'sandbox' : 'sandbox'
  )
  const cliServerId = useChatSessionStore((state) =>
    projectId ? state.cliServerIdsByProject[projectId] ?? null : null
  )
  const executionTargetRef = useRef<ExecutionTarget>(executionTarget)
  const cliServerIdRef = useRef<string | null>(cliServerId)
  const setExecutionTarget = useChatSessionStore((state) => state.setExecutionTarget)
  const setCliServerId = useChatSessionStore((state) => state.setCliServerId)
  const setAgentsForProject = useAgentRegistryStore((state) => state.setAgentsForProject)
  const projectAgents = useAgentRegistryStore((state) =>
    projectId ? state.agentsByProject[projectId] ?? [] : []
  )
  const mentionables = useMemo(
    () => ensureDefaultAgent(mentionablesOverride ?? projectAgents),
    [mentionablesOverride, projectAgents]
  )
  const hasCliAgent = useMemo(
    () =>
      projectAgents.some((agent) => {
        const source = agent.source?.toLowerCase()
        const target = agent.execution_target?.toLowerCase()
        return source === 'cli' || target === 'cli'
      }),
    [projectAgents]
  )
  useEffect(() => {
    executionTargetRef.current = executionTarget
  }, [executionTarget])

  useEffect(() => {
    cliServerIdRef.current = cliServerId
  }, [cliServerId])
  const mentionEnabled = useMemo(() => {
    if (typeof mentionsEnabledOverride === 'boolean') return mentionsEnabledOverride
    return onlineCliServers.length > 0
  }, [mentionsEnabledOverride, onlineCliServers.length])
  const syncRuntimeFromSession = useCallback(
    (payload?: { execution_target?: string | null; cli_server_id?: string | null }) => {
      if (!projectId || !payload) return
      const rawTarget =
        typeof payload.execution_target === 'string' ? payload.execution_target.trim().toLowerCase() : ''
      const normalizedTarget =
        rawTarget === 'cli' || rawTarget === 'cli_server' ? 'cli' : rawTarget === 'sandbox' ? 'sandbox' : ''
      const rawCliId =
        typeof payload.cli_server_id === 'string' ? payload.cli_server_id.trim() : ''
      const cliId = rawCliId || null

      if (normalizedTarget === 'cli') {
        setExecutionTarget(projectId, 'cli', cliId ?? undefined)
        return
      }
      if (normalizedTarget === 'sandbox') {
        setExecutionTarget(projectId, 'sandbox')
        if (cliId) {
          setCliServerId(projectId, cliId)
        }
        return
      }
      if (cliId) {
        setCliServerId(projectId, cliId)
      }
    },
    [projectId, setCliServerId, setExecutionTarget]
  )

  const readOnlyMode = Boolean(readOnly)
  const sessionListEnabledValue = (sessionListEnabled ?? true) && !deferSessionList
  const resolvedHistoryMode = historyMode ?? 'inline'
  const historyPanelEnabled =
    sessionListEnabledValue &&
    (mode === 'welcome' || resolvedHistoryMode === 'overlay')
  const historyPanelInline =
    historyPanelEnabled && resolvedHistoryMode !== 'overlay' && mode === 'welcome'
  const historyPanelOverlay = historyPanelEnabled && resolvedHistoryMode === 'overlay'
  const sessionListReadOnly = readOnlyMode || !projectId
  const toolPanelSizeKey = projectId
    ? `ds:ai-manus:tool-panel-size:${projectId}`
    : 'ds:ai-manus:tool-panel-size'
  const sessionPrefsKey = projectId
    ? `ds:ai-manus:session-preferences:${user?.id ?? 'anon'}:${projectId}:${sessionSurface}`
    : null
  const runtimeLabel = useMemo(() => {
    if (executionTarget === 'cli' && cliServerId) {
      const server = cliServers.find((item) => item.id === cliServerId)
      return `CLI: ${server?.name || server?.hostname || cliServerId.slice(0, 6)}`
    }
    return 'Backend Sandbox'
  }, [cliServerId, cliServers, executionTarget])
  const labRuntimeLocked = useMemo(() => {
    if (!messageMetadata || typeof messageMetadata !== 'object') return false
    const metadata = messageMetadata as Record<string, unknown>
    return Boolean(metadata.agent_instance_id || metadata.lab_mode || metadata.agent_source === 'lab')
  }, [messageMetadata])

  const { sessions, setSessions, reload: reloadSessionSummaries } = useSessionList({
    projectId,
    enabled: historyPanelEnabled,
    stream: false,
  })
  const sessionsRef = useRef<SessionListItem[]>([])
  const [sessionPreferences, setSessionPreferences] = useState<SessionPreferences>(() =>
    loadSessionPreferences(sessionPrefsKey)
  )

  const [messages, setMessages] = useState<ChatMessageItem[]>([])
  const messagesRef = useRef<ChatMessageItem[]>([])
  const appendOrderRef = useRef<Map<string, number>>(new Map())
  const appendPendingRef = useRef<Set<string>>(new Set())
  const [plan, setPlan] = useState<PlanEventData | null>(null)
  const [planHistory, setPlanHistory] = useState<PlanEventData[]>([])
  const [title, setTitle] = useState('New Chat')
  const [sessionStatus, setSessionStatus] = useState<SessionStatus | null>(null)
  const [inputMessage, setInputMessage] = useState('')
  const [attachments, setAttachments] = useState<AttachmentInfo[]>([])
  const [recentFilesEnabled, setRecentFilesEnabled] = useState(false)
  const [restoreToken, setRestoreToken] = useState(0)
  const forceRestoreRef = useRef(false)
  const lastVisibleRef = useRef(false)
  const lastModeRef = useRef<ChatSurface | null>(null)
  const [realTime, setRealTime] = useState(true)
  const realTimeRef = useRef(true)
  const [toolPanelOpen, setToolPanelOpen] = useState(false)
  const [toolPanelLive, setToolPanelLive] = useState(false)
  const [toolPanelView, setToolPanelView] = useState<'tool' | 'terminal'>(() =>
    mode === 'welcome' ? 'terminal' : 'tool'
  )
  const [activeTool, setActiveTool] = useState<ToolContent | null>(null)
  const [toolPanelSize, setToolPanelSize] = useState(TOOL_PANEL_DEFAULT_SIZE)
  const [statusTodoText, setStatusTodoText] = useState<string | null>(null)
  const [statusTodoPrev, setStatusTodoPrev] = useState<string | null>(null)
  const [statusTodoKey, setStatusTodoKey] = useState(0)
  const statusTodoRef = useRef<string | null>(null)
  const [toolCallCount, setToolCallCount] = useState(0)
  const [runtimeSwitching, setRuntimeSwitching] = useState(false)
  const [copilotStatus, setCopilotStatus] = useState<string | null>(null)
  const [pauseState, setPauseState] = useState<{ runId: number; reason: 'paused' | 'cancelled' } | null>(null)
  const pauseStateRef = useRef<typeof pauseState>(null)
  const abortedRunIdRef = useRef<number | null>(null)
  const [pendingRun, setPendingRun] = useState(false)
  const [fixWithAiRunning, setFixWithAiRunning] = useState(false)
  const [sessionActive, setSessionActive] = useState(false)
  const [recoveryBanner, setRecoveryBanner] = useState<{
    status: 'recovering' | 'recovered' | 'failed'
    message: string
  } | null>(null)
  const recoveryTimeoutRef = useRef<number | null>(null)
  const autoResumeTimerRef = useRef<number | null>(null)
  const sessionQuiescenceReconcileTimerRef = useRef<number | null>(null)
  const refreshingAgentsRef = useRef(false)
  const lastOnlineServersKeyRef = useRef<string | null>(null)
  const lastMentionRefreshRef = useRef<string | null>(null)
  const [historyOpen, setHistoryOpen] = useState(() => {
    if (typeof historyOpenOverride === 'boolean') return historyOpenOverride
    if (resolvedHistoryMode === 'overlay') return false
    if (embedded) return false
    return mode === 'welcome' && sessionListEnabledValue
  })
  const [fileListOpen, setFileListOpen] = useState(false)
  const [sessionFiles, setSessionFiles] = useState<SessionFileResponse[]>([])
  const [sessionFilesLoading, setSessionFilesLoading] = useState(false)
  const [isCompactView, setIsCompactView] = useState(false)
  const [highlightSessionId, setHighlightSessionId] = useState<string | null>(null)
  const [isRestoring, setIsRestoring] = useState(false)
  const isRestoringRef = useRef(false)
  const [greetingTemplate, setGreetingTemplate] = useState(() => pickGreetingTemplate())
  const [draftSessionId, setDraftSessionId] = useState<string | null>(null)
  const [renameDialogOpen, setRenameDialogOpen] = useState(false)
  const [renameTargetId, setRenameTargetId] = useState<string | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const renameInputRef = useRef<HTMLInputElement | null>(null)
  const sessionId = draftSessionId ? null : storedSessionId
  const draftSessionIdRef = useRef<string | null>(draftSessionId)
  const newSessionRequestRef = useRef<string | null>(null)
  const manualSessionSelectionRef = useRef(false)
  const appliedSessionFromUrlRef = useRef<string | null>(null)
  const [questionPrompt, setQuestionPrompt] = useState<{
    toolCallId: string
    args: Record<string, unknown>
  } | null>(null)
  const questionPromptRef = useRef<typeof questionPrompt>(null)
  const [clarifyPrompt, setClarifyPrompt] = useState<ClarifyPromptState | null>(null)
  const clarifyPromptRef = useRef<typeof clarifyPrompt>(null)
  const focusComposer = useCallback(() => {
    if (composerFocusRef.current) {
      composerFocusRef.current()
      return
    }
    composerRef.current?.focus()
  }, [])
  const [takeoverActive, setTakeoverActive] = useState(false)
  const [takeoverSessionId, setTakeoverSessionId] = useState('')
  const skipRestoreRef = useRef(false)
  const previousSessionRef = useRef<string | null>(null)
  const sessionIdRef = useRef<string | null>(sessionId)
  const ensureSessionPromiseRef = useRef<{
    projectId: string | null
    promise: Promise<string | null>
  } | null>(null)
  const autoEnsureKeyRef = useRef<string | null>(null)
  const historyOpenPreferenceRef = useRef(true)
  const historyOpenControlled = typeof historyOpenOverride === 'boolean'
  const historyOpenValue = historyPanelEnabled
    ? historyOpenControlled
      ? historyOpenOverride
      : historyOpen
    : false
  const setHistoryOpenValue = useCallback(
    (next: boolean) => {
      if (!historyPanelEnabled) return
      if (historyOpenControlled) {
        onHistoryOpenChange?.(next)
        return
      }
      setHistoryOpen(next)
    },
    [historyOpenControlled, historyPanelEnabled, onHistoryOpenChange]
  )

  useEffect(() => {
    if (!sessionPrefsKey) {
      setSessionPreferences(EMPTY_SESSION_PREFERENCES)
      return
    }
    setSessionPreferences(loadSessionPreferences(sessionPrefsKey))
  }, [sessionPrefsKey])

  useEffect(() => {
    saveSessionPreferences(sessionPrefsKey, sessionPreferences)
  }, [sessionPreferences, sessionPrefsKey])

  useEffect(() => {
    if (!historyPanelEnabled) return
    if (!historyOpenControlled || typeof historyOpenOverride !== 'boolean') return
    setHistoryOpen(historyOpenOverride)
  }, [historyOpenControlled, historyOpenOverride, historyPanelEnabled])

  const isVisible = visible ?? true
  const debugLog = useCallback(
    (scope: string, payload?: Record<string, unknown>) => {
      if (!debugEnabled) return
      const base = {
        projectId: projectId ?? null,
        mode,
        uiSurface,
        visible: isVisible,
        sessionId: sessionIdRef.current,
        draftSessionId: draftSessionIdRef.current,
      }
      if (payload) {
        console.info(`[AiManus][${scope}]`, { ...base, ...payload })
        return
      }
      console.info(`[AiManus][${scope}]`, base)
    },
    [debugEnabled, isVisible, mode, projectId, uiSurface]
  )
  const traceEnabled = useMemo(() => {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem('ds_debug_copilot') === '1'
  }, [])
  const traceLog = useCallback(
    (scope: string, payload?: Record<string, unknown>) => {
      if (!traceEnabled) return
      const base = {
        projectId: projectId ?? null,
        mode,
        uiSurface,
        sessionId: sessionIdRef.current,
      }
      console.warn(`[AiManusTrace][${scope}]`, payload ? { ...base, ...payload } : base)
    },
    [mode, projectId, traceEnabled, uiSurface]
  )

  useEffect(() => {
    debugLog('history:state', {
      open: historyOpenValue,
      enabled: historyPanelEnabled,
      overlay: historyPanelOverlay,
      inline: historyPanelInline,
    })
  }, [debugLog, historyOpenValue, historyPanelEnabled, historyPanelInline, historyPanelOverlay])

  const lastToolRef = useRef<ToolContent | null>(null)
  const lastNoMessageToolRef = useRef<ToolContent | null>(null)
  const lastStepRef = useRef<StepContent | null>(null)
  const lastReasoningRef = useRef<ReasoningContent | null>(null)
  const reasoningByIdRef = useRef<Map<string, ChatMessageItem>>(new Map())
  const reasoningLocksRef = useRef<Set<string>>(new Set())
  const reasoningSegmentIndexRef = useRef<Map<string, number>>(new Map())
  const reasoningStallTimerRef = useRef<number | null>(null)
  const reasoningLastUpdateRef = useRef<number | null>(null)
  const activeReasoningStreamRef = useRef<string | null>(null)
  const assistantSegmentIndexRef = useRef<Map<string, number>>(new Map())
  const assistantSegmentPendingRef = useRef<Set<string>>(new Set())
  const assistantMessageOpenRef = useRef<Set<string>>(new Set())
  const activeAssistantMessageIdRef = useRef<string | null>(null)
  const timelineSeqRef = useRef(0)
  const assistantMessageIndexRef = useRef<Map<string, string>>(new Map())
  const toolCallMessageIdRef = useRef<Map<string, string>>(new Map())
  const toolResultMessageIdRef = useRef<Map<string, string>>(new Map())
  const lastAssistantSegmentIdRef = useRef<string | null>(null)
  const toolBoundarySeenRef = useRef<Set<string>>(new Set())
  const displayLockRef = useRef<{ id: string; kind: DisplayLockKind } | null>(null)
  const displayLockTimerRef = useRef<number | null>(null)
  const [displayLockState, setDisplayLockState] = useState<{ id: string; kind: DisplayLockKind } | null>(null)
  const displayPendingRef = useRef<Map<string, number>>(new Map())
  const bufferedEventsRef = useRef<AgentSSEEvent[]>([])
  const restoreStreamQueueRef = useRef<AgentSSEEvent[]>([])
  const restoreEventIdsRef = useRef<Set<string>>(new Set())
  const toolPanelAutoOpenRef = useRef(false)
  const toolCallSeenRef = useRef<Set<string>>(new Set())
  const statusToolSeenRef = useRef<Set<string>>(new Set())
  const patchReviewSeenRef = useRef<Set<string>>(new Set())
  const patchRecompileTargetsRef = useRef<Map<string, { projectId: string; folderId: string }>>(new Map())
  const fixWithAiRunningRef = useRef(false)
  const pendingUserRef = useRef<{ content: string; attachments: AttachmentInfo[] } | null>(null)
  const attachmentsSeenRef = useRef<Set<string>>(new Set())
  const restoringRef = useRef(false)
  const restoringSessionIdRef = useRef<string | null>(null)
  const restoredSessionRef = useRef<string | null>(null)
  const latestSessionLoadedRef = useRef<string | null>(null)
  const restoreRetryRef = useRef<string | null>(null)
  const fullHistoryModeRef = useRef(false)
  const fullHistoryRequestRef = useRef(false)
  const restoredStatusRef = useRef<'pending' | 'running' | 'waiting' | 'completed' | 'failed' | null>(null)
  const cacheReplayRef = useRef(false)
  const highlightTimerRef = useRef<number | null>(null)
  const introTimerRef = useRef<number | null>(null)
  const [welcomeIntroState, setWelcomeIntroState] = useState<'center' | 'dropping' | 'done'>('center')
  const restoreFallbackRef = useRef<{ projectId: string; sessionId: string } | null>(null)
  const virtualizeRestoreRef = useRef(false)

  const scrollRef = useRef<HTMLDivElement | null>(null)
  const listWrapperRef = useRef<HTMLDivElement | null>(null)
  const listOuterRef = useRef<HTMLDivElement | null>(null)
  const listInnerRef = useRef<HTMLDivElement | null>(null)
  const listRef = useRef<VariableSizeList | null>(null)
  const sizeMapRef = useRef<Map<number, number>>(new Map())
  const listResetIndexRef = useRef<number | null>(null)
  const listResetRafRef = useRef<number | null>(null)
  const [listHeight, setListHeight] = useState(0)
  const [hasHistory, setHasHistory] = useState(false)
  const [historyTruncated, setHistoryTruncated] = useState(false)
  const [historyLimit, setHistoryLimit] = useState<number | null>(null)
  const [historyLoadingFull, setHistoryLoadingFull] = useState(false)
  const [showFullHistory, setShowFullHistory] = useState(false)
  const hasHistoryRef = useRef(false)
  const [restoreAttempted, setRestoreAttempted] = useState(false)
  const [hasNewMessages, setHasNewMessages] = useState(false)
  const hasNewMessagesRef = useRef(false)
  const [isNearBottom, setIsNearBottom] = useState(true)
  const isNearBottomRef = useRef(true)
  const initialScrollDoneRef = useRef(false)
  const lastMessageIdRef = useRef<string | null>(null)
  const composerRef = useRef<HTMLTextAreaElement | null>(null)
  const composerFocusRef = useRef<(() => void) | null>(null)
  const toolPanelRef = useRef<PanelImperativeHandle | null>(null)
  const historyOverlayRef = useRef<HTMLDivElement | null>(null)
  const [toolPanelMount, setToolPanelMount] = useState<HTMLElement | null>(null)
  const [sessionListMount, setSessionListMount] = useState<HTMLElement | null>(null)

  const layoutSurface = historyPanelInline ? 'welcome' : uiSurface
  const toolPanelMountActive = mode === 'welcome' && Boolean(toolPanelMountId)
  const sessionListMountActive = historyPanelInline && Boolean(sessionListMountId)
  const toolPanelMountReady = toolPanelMountActive && Boolean(toolPanelMount)
  const sessionListMountReady = sessionListMountActive && Boolean(sessionListMount)
  const toolPanelEnabled = mode === 'welcome' && (toolPanelMountActive || !isCompactView)
  const toolPanelOpenValue = toolPanelMountReady ? true : toolPanelOpen
  const shellToolContent = useMemo<ToolContent | null>(() => {
    if (!activeTool) return null
    return resolveToolCategory(activeTool) === 'shell' ? activeTool : null
  }, [activeTool])
  const terminalShellSessionId = sessionId ? `terminal-${sessionId}` : ''
  const terminalToolContent = useMemo<ToolContent | null>(() => {
    if (executionTarget === 'cli' && cliServerId && sessionId) {
      const terminalEventId = terminalShellSessionId || 'terminal-new'
      return {
        event_id: terminalEventId,
        timestamp: Math.floor(Date.now() / 1000),
        tool_call_id: terminalEventId,
        name: 'shell',
        status: 'called',
        function: 'shell_view',
        args: terminalShellSessionId ? { id: terminalShellSessionId } : {},
        content: {
          session_id: terminalShellSessionId || undefined,
          runtime: executionTarget,
          execution_target: executionTarget,
          cli_server_id: cliServerId ?? undefined,
        },
      }
    }
    return shellToolContent
  }, [cliServerId, executionTarget, sessionId, shellToolContent, terminalShellSessionId])
  const canOpenTerminal = useMemo(() => {
    if (executionTarget === 'cli') {
      return Boolean(cliServerId)
    }
    return Boolean(shellToolContent)
  }, [cliServerId, executionTarget, shellToolContent])
  const panelToolContent = toolPanelView === 'terminal' ? terminalToolContent : activeTool
  const showToolPanelInline =
    toolPanelEnabled && !toolPanelMountReady && toolPanelOpenValue && Boolean(panelToolContent)
  const toolPanelVisible = toolPanelEnabled && toolPanelOpenValue && Boolean(panelToolContent)
  const hasToolHistory = Boolean(lastNoMessageToolRef.current)
  const toolToggleVisible = toolPanelEnabled && (toolPanelVisible || hasToolHistory)
  const messageMaxWidthClass = showToolPanelInline
    ? 'max-w-[680px] xl:max-w-[720px]'
    : 'max-w-[768px]'
  const isCopilotSurface = uiSurface === 'copilot'
  const virtualizeThreshold = COPILOT_VIRTUALIZE_THRESHOLD
  const listPaddingClass = flushLayoutPadding
    ? 'px-0'
    : isCopilotSurface
      ? 'px-4'
      : 'px-5'
  const listTopPaddingClass = flushLayoutPadding ? 'pt-0' : 'pt-[12px]'
  const composerPaddingClass = flushLayoutPadding
    ? 'mt-auto px-0 pb-0 pt-0'
    : isCopilotSurface
      ? 'mt-auto px-3 pb-1 pt-3'
      : 'mt-auto px-5 pb-5 pt-4'
  const composerGutterClass = flushLayoutPadding
    ? 'px-0'
    : isCopilotSurface
      ? 'px-3'
      : 'px-5'
  const orbitOffsetClass = flushLayoutPadding
    ? 'right-0'
    : isCopilotSurface
      ? 'right-3'
      : 'right-5'
  const auditContextRef = useRef<{ projectId: string | null; mode: ChatSurface; uiSurface: ChatSurface }>({
    projectId: projectId ?? null,
    mode,
    uiSurface,
  })

  useEffect(() => {
    auditContextRef.current = { projectId: projectId ?? null, mode, uiSurface }
  }, [mode, projectId, uiSurface])

  useEffect(() => {
    console.info('[CopilotAudit][lifecycle] mount', auditContextRef.current)
    return () => {
      console.info('[CopilotAudit][lifecycle] unmount', auditContextRef.current)
    }
  }, [])

  useEffect(() => {
    console.info('[CopilotAudit][visibility] changed', {
      projectId: auditContextRef.current.projectId,
      visible: isVisible,
    })
    debugLog('visibility:changed', { visible: isVisible })
  }, [debugLog, isVisible])

  useEffect(() => {
    if (!projectId) return
    if (isQuestRuntimeSurface()) return
    if (!allowSurfaceFallback) return
    if (draftSessionId) return
    if (surfaceSessionId) return
    const fallbackSessionId =
      sessionSurface === 'welcome' ? legacySessionId : welcomeSessionId ?? legacySessionId
    if (!fallbackSessionId) return
    setSessionIdForSurface(projectId, sessionSurface, fallbackSessionId)
  }, [
    allowSurfaceFallback,
    draftSessionId,
    legacySessionId,
    projectId,
    sessionSurface,
    setSessionIdForSurface,
    surfaceSessionId,
    welcomeSessionId,
  ])

  useEffect(() => {
    if (!projectId) return
    if (draftSessionId) return
    if (surfaceSessionId) return
    let cancelled = false
    const adoptQuestSession = async () => {
      if (!(await shouldUseQuestSessionCompat(projectId))) return
      if (cancelled) return
      setSessionIdForSurface(projectId, sessionSurface, buildQuestSessionId(projectId))
    }
    void adoptQuestSession()
    return () => {
      cancelled = true
    }
  }, [draftSessionId, projectId, sessionSurface, setSessionIdForSurface, surfaceSessionId])

  useEffect(() => {
    if (!projectId) return
    if (isQuestRuntimeSurface()) return
    if (mode !== 'welcome') return
    if (!surfaceSessionId || surfaceSessionId === copilotSessionId) return
    setSessionIdForSurface(projectId, 'copilot', surfaceSessionId)
  }, [copilotSessionId, mode, projectId, setSessionIdForSurface, surfaceSessionId])

  useEffect(() => {
    if (!projectId) return
    if (isQuestRuntimeSurface()) return
    if (mode !== 'welcome' || uiSurface !== 'copilot') return
    if (!surfaceSessionId || surfaceSessionId === welcomeSessionId) return
    setSessionIdForSurface(projectId, 'welcome', surfaceSessionId)
  }, [mode, projectId, setSessionIdForSurface, surfaceSessionId, uiSurface, welcomeSessionId])
  const hideCompactMeta = isCopilotSurface || isCompactView
  const resolvedComposerMode = composerMode ?? 'text'
  const useNotebookComposer = resolvedComposerMode === 'notebook'
  const prefersReducedMotion = useReducedMotion()
  const composerLayoutId = useId()
  const composerLayoutGroupId = `ai-manus-layout-${composerLayoutId}`
  const composerLayoutKey = `ai-manus-composer-${composerLayoutId}`
  const isEmptyState = messages.length === 0 && !isRestoring
  const showHistoryLoadingOverlay = isRestoring && messages.length === 0
  const introEnabled = uiSurface === 'welcome' || (uiSurface === 'copilot' && !hideCopilotGreeting)
  const showIntro = introEnabled && welcomeIntroState !== 'done'
  const showHistoryOverlay = historyPanelOverlay && historyOpenValue
  const hideMessagesForIntro =
    introEnabled && welcomeIntroState === 'center' && !showHistoryOverlay
  const showIntroCenter = introEnabled && welcomeIntroState === 'center'
  const [historyOverlayPaddingLeft, setHistoryOverlayPaddingLeft] = useState<number | null>(null)
  const welcomeIntroCards = sessionListEnabledValue
    ? WELCOME_INTRO_CARDS
    : WELCOME_INTRO_CARDS.filter((card) => card.title !== 'Sessions')
  const greetingName = user?.username?.trim() ? user.username.trim() : 'there'
  const greetingLabel = greetingTemplate.replace('{name}', greetingName)
  const introSubtitle = 'What can I do for you?'
  const isWelcomeLayout = mode === 'welcome'
  const showWelcomeCards = isWelcomeLayout && welcomeIntroCards.length > 0 && uiSurface !== 'copilot'
  const introComposerWidthStyle = isWelcomeLayout ? { width: '61.8%' } : undefined
  const introComposerWidthClass = isWelcomeLayout
    ? 'min-w-[min(260px,100%)]'
    : 'w-[80%] max-w-[820px] min-w-[min(260px,100%)]'
  const dockedComposerWidthStyle = isWelcomeLayout ? { width: '61.8%' } : undefined
  const dockedComposerWidthClass = isWelcomeLayout ? 'mx-auto min-w-[min(260px,100%)]' : 'w-full'
  const mentionLabels = useMemo(() => {
    const labels = new Set<string>()
    mentionables.forEach((agent) => {
      if (agent.label) {
        const raw = agent.label.trim()
        if (raw) {
          labels.add(raw.startsWith('@') ? raw : `@${raw}`)
        }
      }
      if (agent.id) {
        labels.add(`@${agent.id}`)
      }
    })
    if (lockedMentionPrefix) {
      const raw = lockedMentionPrefix.trim()
      if (raw) {
        labels.add(raw.startsWith('@') ? raw : `@${raw}`)
      }
    }
    return Array.from(labels).sort((a, b) => b.length - a.length)
  }, [lockedMentionPrefix, mentionables])
  const ensureLeadingMentionSpace = useCallback(
    (text: string) => {
      if (!lockLeadingMentionSpace) return text
      const raw = text ?? ''
      if (!raw.startsWith('@')) return raw
      const rawLower = raw.toLowerCase()
      let end: number | null = null
      for (const label of mentionLabels) {
        const labelLower = label.toLowerCase()
        if (rawLower.startsWith(labelLower)) {
          end = label.length
          break
        }
      }
      if (end == null) {
        const match = raw.match(/^@([^\s]+)/)
        if (!match) return raw
        end = match[0].length
      }
      if (raw[end] === ' ') return raw
      return `${raw.slice(0, end)} ${raw.slice(end)}`
    },
    [lockLeadingMentionSpace, mentionLabels]
  )
  const dropTransition = prefersReducedMotion
    ? { duration: 0 }
    : ({ type: 'spring', stiffness: 220, damping: 20, mass: 0.9 } as const)
  const introFadeTransition = prefersReducedMotion
    ? { duration: 0 }
    : ({ duration: 0.5, ease: [0.16, 1, 0.3, 1] as const } as const)
  const listBottomPadding = useMemo(() => {
    return isCopilotSurface ? 120 : 144
  }, [isCopilotSurface])
  const ListInnerElement = useMemo(
    () =>
      forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(function ListInnerElement(props, ref) {
        return (
          <div ref={ref} {...props} style={{ ...props.style, paddingBottom: listBottomPadding }} />
        )
      }),
    [listBottomPadding]
  )

  useEffect(() => {
    if (!lockLeadingMentionSpace) return
    const normalized = ensureLeadingMentionSpace(inputMessage)
    if (normalized !== inputMessage) {
      setInputMessage(normalized)
    }
  }, [ensureLeadingMentionSpace, inputMessage, lockLeadingMentionSpace])

  useLayoutEffect(() => {
    if (!showHistoryOverlay) {
      setHistoryOverlayPaddingLeft(null)
      return
    }
    if (typeof window === 'undefined') return
    const container = historyOverlayRef.current
    if (!container) return

    let raf: number | null = null
    const update = () => {
      if (raf) return
      raf = window.requestAnimationFrame(() => {
        raf = null
        const panel = container.querySelector<HTMLElement>('[data-ai-manus-history-overlay="true"]')
        if (!panel) return
        const rect = panel.getBoundingClientRect()
        const style = window.getComputedStyle(panel)
        const marginLeft = Number.parseFloat(style.marginLeft) || 0
        const marginRight = Number.parseFloat(style.marginRight) || 0
        const next = Math.ceil(rect.width + marginLeft + marginRight)
        setHistoryOverlayPaddingLeft((prev) => (prev === next ? prev : next))
      })
    }

    update()

    if (typeof ResizeObserver === 'undefined') {
      return () => {
        if (raf) window.cancelAnimationFrame(raf)
      }
    }

    const observer = new ResizeObserver(() => update())
    observer.observe(container)

    return () => {
      observer.disconnect()
      if (raf) window.cancelAnimationFrame(raf)
    }
  }, [showHistoryOverlay])

  useEffect(() => {
    if (toolPanelView === 'terminal' && !terminalToolContent) {
      setToolPanelView('tool')
    }
  }, [setToolPanelView, terminalToolContent, toolPanelView])

  const pendingMessagesRef = useRef<ChatMessageItem[] | null>(null)
  const pendingMessagesTimerRef = useRef<number | null>(null)

  const commitMessages = useCallback(
    (next: ChatMessageItem[]) => {
      const previous = messagesRef.current
      if (next.length === 0) {
        appendOrderRef.current.clear()
        appendPendingRef.current.clear()
      } else if (next.length > previous.length) {
        const isAppend =
          previous.length === 0 ||
          next[previous.length - 1]?.id === previous[previous.length - 1]?.id
        if (!isAppend) {
          appendOrderRef.current.clear()
          appendPendingRef.current.clear()
        } else if (!restoringRef.current && realTimeRef.current) {
          const appended = next.slice(previous.length)
          appended.forEach((message, index) => {
            if (appendPendingRef.current.has(message.id)) return
            appendPendingRef.current.add(message.id)
            appendOrderRef.current.set(message.id, index)
          })
        }
      } else if (next.length < previous.length) {
        appendOrderRef.current.clear()
        appendPendingRef.current.clear()
      } else if (
        next.length === previous.length &&
        next.length > 0 &&
        next[0]?.id !== previous[0]?.id
      ) {
        appendOrderRef.current.clear()
        appendPendingRef.current.clear()
      }
      messagesRef.current = next
      setMessages(next)
      if (!debugEnabled) return
      const tail = next.slice(-6).map((item) => {
        const content = item.content as { timestamp?: number }
        const timestamp = typeof content?.timestamp === 'number' ? content.timestamp : 'na'
        const shortId = item.id.length > 8 ? item.id.slice(0, 8) : item.id
        return `${item.type}:${shortId}:${timestamp}`
      })
      debugLog('state:messages', { count: next.length, tail })
    },
    [debugEnabled, debugLog]
  )

  const cancelPendingMessages = useCallback(() => {
    if (pendingMessagesTimerRef.current) {
      window.clearTimeout(pendingMessagesTimerRef.current)
      pendingMessagesTimerRef.current = null
    }
    pendingMessagesRef.current = null
  }, [])

  const flushPendingMessages = useCallback(() => {
    if (!pendingMessagesRef.current) return
    const next = pendingMessagesRef.current
    pendingMessagesRef.current = null
    if (pendingMessagesTimerRef.current) {
      window.clearTimeout(pendingMessagesTimerRef.current)
      pendingMessagesTimerRef.current = null
    }
    commitMessages(next)
  }, [commitMessages])

  const queueMessages = useCallback(
    (next: ChatMessageItem[]) => {
      messagesRef.current = next
      pendingMessagesRef.current = next
      if (pendingMessagesTimerRef.current) return
      pendingMessagesTimerRef.current = window.setTimeout(() => {
        flushPendingMessages()
      }, MESSAGE_FLUSH_MS)
    },
    [flushPendingMessages]
  )

  const updateMessages = useCallback(
    (next: ChatMessageItem[], options?: { throttle?: boolean }) => {
      const shouldThrottle =
        typeof options?.throttle === 'boolean'
          ? options.throttle
          : restoringRef.current || cacheReplayRef.current
      if (shouldThrottle) {
        queueMessages(next)
        return
      }
      cancelPendingMessages()
      commitMessages(next)
    },
    [cancelPendingMessages, commitMessages, queueMessages]
  )

  const markAppendSeen = useCallback((id: string) => {
    if (!appendPendingRef.current.has(id)) return
    appendPendingRef.current.delete(id)
    appendOrderRef.current.delete(id)
  }, [])

  const appendMessage = useCallback(
    (message: ChatMessageItem) => {
      const existingIndex = messagesRef.current.findIndex((item) => item.id === message.id)
      if (existingIndex >= 0) {
        const next = [...messagesRef.current]
        next[existingIndex] = message
        updateMessages(next)
        return
      }
      updateMessages([...messagesRef.current, message])
    },
    [updateMessages]
  )

  const replaceMessageById = useCallback(
    (message: ChatMessageItem, options?: { throttle?: boolean }) => {
      const existingIndex = messagesRef.current.findIndex((item) => item.id === message.id)
      if (existingIndex < 0) return false
      const next = [...messagesRef.current]
      next[existingIndex] = message
      updateMessages(next, options)
      return true
    },
    [updateMessages]
  )

  const replaceReasoningMessage = useCallback(
    (message: ChatMessageItem) => {
      const updated = replaceMessageById(message)
      if (!updated) return false
      for (const [key, value] of reasoningByIdRef.current.entries()) {
        if (value.id === message.id) {
          reasoningByIdRef.current.set(key, message)
          break
        }
      }
      return true
    },
    [replaceMessageById]
  )

  const updateStatusTodo = useCallback(
    (nextText: string | null) => {
      if (!nextText || nextText.trim().length === 0) {
        statusTodoRef.current = null
        setStatusTodoText(null)
        setStatusTodoPrev(null)
        return
      }
      if (statusTodoRef.current === nextText) return
      setStatusTodoPrev(statusTodoRef.current)
      statusTodoRef.current = nextText
      setStatusTodoText(nextText)
      setStatusTodoKey((value) => value + 1)
    },
    [setStatusTodoKey]
  )

  const resolveStatusTodoText = useCallback((rawTodo: unknown, rawNext: unknown): string | null => {
    const raw = rawTodo ?? rawNext
    const items = Array.isArray(raw)
      ? raw
      : typeof raw === 'string'
        ? [raw]
        : []
    const text = items
      .map((item) => decodeHtmlEntities(String(item)))
      .map((item) => item.trim())
      .filter((item) => item.length > 0)
      .join(' / ')
    return text || null
  }, [])

  const getReasoningMessageKey = useCallback((streamKey: string) => {
    const segmentIndex = reasoningSegmentIndexRef.current.get(streamKey) ?? 0
    return `${streamKey}::${segmentIndex}`
  }, [])

  const closeReasoningSegment = useCallback((force = false) => {
    const activeStream = activeReasoningStreamRef.current
    if (!activeStream) return
    if (!force && reasoningLocksRef.current.has(activeStream)) return
    const currentIndex = reasoningSegmentIndexRef.current.get(activeStream) ?? 0
    reasoningSegmentIndexRef.current.set(activeStream, currentIndex + 1)
    activeReasoningStreamRef.current = null
  }, [])

  const sealActiveReasoningSegment = useCallback(() => {
    const activeStream = activeReasoningStreamRef.current
    let updated = false
    const completeMessage = (message: ChatMessageItem | undefined) => {
      if (!message || message.type !== 'reasoning') return false
      const content = message.content as ReasoningContent
      if (content.status !== 'in_progress') return false
      const nextContent: ReasoningContent = { ...content, status: 'completed' }
      const nextMessage: ChatMessageItem = { ...message, content: nextContent }
      replaceReasoningMessage(nextMessage)
      lastReasoningRef.current = nextContent
      return true
    }
    if (activeStream) {
      const messageKey = getReasoningMessageKey(activeStream)
      const message = reasoningByIdRef.current.get(messageKey)
      updated = completeMessage(message)
      reasoningLocksRef.current.delete(activeStream)
    }
    if (!updated) {
      const lockId = displayLockRef.current?.id
      if (lockId) {
        const index = messagesRef.current.findIndex((item) => item.id === lockId)
        if (index >= 0) {
          updated = completeMessage(messagesRef.current[index])
        }
      }
    }
    closeReasoningSegment(true)
    traceLog('reasoning:seal', {
      activeStream,
      updated,
      lock: displayLockRef.current,
      buffered: bufferedEventsRef.current.length,
    })
  }, [closeReasoningSegment, getReasoningMessageKey, replaceReasoningMessage, traceLog])

  const requestRestore = useCallback(() => {
    forceRestoreRef.current = true
    setRestoreToken((value) => value + 1)
  }, [])

  // On page entry (or project switch), restore latest history when no session is selected
  // and avoid overriding a user-selected session on other surfaces.
  useEffect(() => {
    if (!projectId || readOnlyMode) return
    if (typeof window === 'undefined') return

    let cancelled = false
    const apiBaseUrl = getApiBaseUrl()

    const run = async () => {
      const storedSessionId = sessionIdRef.current
      const draft = draftSessionIdRef.current

      if (isQuestRuntimeSurface()) {
        const questSessionId = buildQuestSessionId(projectId)
        if (storedSessionId !== questSessionId) {
          console.info('[CopilotAudit][entry] adopt quest session', {
            projectId,
            sessionId: questSessionId,
          })
          setSessionIdForSurface(projectId, sessionSurface, questSessionId)
        } else if (messagesRef.current.length === 0) {
          console.info('[CopilotAudit][entry] restore quest session', {
            projectId,
            sessionId: questSessionId,
          })
          requestRestore()
        }
        return
      }

      console.info('[CopilotAudit][entry]', {
        projectId,
        apiBaseUrl,
        storedSessionId,
        draftSessionId: draft,
      })

      if (draft) {
        console.info('[CopilotAudit][entry] skip restore (draft session active)', {
          projectId,
          draftSessionId: draft,
        })
        return
      }

      if (storedSessionId) {
        if (messagesRef.current.length === 0) {
          console.info('[CopilotAudit][entry] restore stored session', {
            projectId,
            sessionId: storedSessionId,
            url: `${apiBaseUrl}/api/v1/sessions/${storedSessionId}`,
          })
          requestRestore()
        }
        return
      }

      if (!allowSurfaceFallback) {
        return
      }

      console.info('[CopilotAudit][entry] request product latest session', {
        projectId,
        url: `${apiBaseUrl}/api/v1/sessions/latest`,
      })

      try {
        let latest = await getLatestSession(projectId, undefined, sessionSurface)
        let latestId = latest?.session_id ?? null
        let usedFallback = false
        if (!latestId) {
          latest = await getLatestSession(projectId)
          latestId = latest?.session_id ?? null
          usedFallback = Boolean(latestId)
        }
        if (cancelled) return
        syncRuntimeFromSession(latest ?? undefined)

        console.info('[CopilotAudit][entry] latest session resolved', {
          projectId,
          sessionId: latestId,
          events: latest?.events?.length ?? 0,
          usedFallback,
        })

        if (!latestId) {
          const currentSessionId = storedSessionId ?? sessionIdRef.current
          if (currentSessionId && messagesRef.current.length === 0) {
            console.info('[CopilotAudit][entry] restore stored session', {
              projectId,
              sessionId: currentSessionId,
              url: `${apiBaseUrl}/api/v1/sessions/${currentSessionId}`,
            })
            requestRestore()
          }
          return
        }

        if (storedSessionId && storedSessionId === latestId) {
          if (messagesRef.current.length === 0) {
            console.info('[CopilotAudit][entry] restore latest session', {
              projectId,
              sessionId: latestId,
              url: `${apiBaseUrl}/api/v1/sessions/${latestId}`,
            })
            requestRestore()
          }
          return
        }

        if ((latest?.events?.length ?? 0) === 0) {
          skipRestoreRef.current = true
        }
        setSessionIdForSurface(projectId, sessionSurface, latestId)
        console.info('[CopilotAudit][entry] adopt latest session', {
          projectId,
          sessionId: latestId,
          url: `${apiBaseUrl}/api/v1/sessions/${latestId}`,
        })
      } catch (error) {
        if (cancelled) return
        console.warn('[CopilotAudit][entry] latest session request failed', error)
        if (storedSessionId && messagesRef.current.length === 0) {
          console.info('[CopilotAudit][entry] restore stored session', {
            projectId,
            sessionId: storedSessionId,
            url: `${apiBaseUrl}/api/v1/sessions/${storedSessionId}`,
          })
          requestRestore()
        }
      }
    }

    void run()

    return () => {
      cancelled = true
    }
  }, [
    isCopilotSurface,
    projectId,
    readOnlyMode,
    requestRestore,
    sessionSurface,
    setSessionIdForSurface,
    syncRuntimeFromSession,
    allowSurfaceFallback,
  ])

  const resetConversation = useCallback((options?: { title?: string }) => {
    messagesRef.current = []
    setMessages([])
    appendOrderRef.current = new Map()
    appendPendingRef.current = new Set()
    patchReviewSeenRef.current = new Set()
    patchRecompileTargetsRef.current = new Map()
    fixWithAiRunningRef.current = false
    setFixWithAiRunning(false)
    setPlan(null)
    setPlanHistory([])
    setTitle(options?.title ?? 'New Chat')
    setSessionStatus(null)
    setInputMessage('')
    setAttachments([])
    setRecentFilesEnabled(false)
    setCopilotStatus(null)
    setPauseState(null)
    pauseStateRef.current = null
    abortedRunIdRef.current = null
    setPendingRun(false)
    setSessionActive(false)
    setActiveTool(null)
    setToolPanelLive(false)
    setStatusTodoText(null)
    setStatusTodoPrev(null)
    setStatusTodoKey(0)
    statusTodoRef.current = null
    setQuestionPrompt(null)
    questionPromptRef.current = null
    setClarifyPrompt(null)
    clarifyPromptRef.current = null
    lastToolRef.current = null
    lastNoMessageToolRef.current = null
    lastStepRef.current = null
    lastReasoningRef.current = null
    timelineSeqRef.current = 0
    assistantMessageIndexRef.current = new Map()
    toolCallMessageIdRef.current = new Map()
    toolResultMessageIdRef.current = new Map()
    lastAssistantSegmentIdRef.current = null
    reasoningByIdRef.current = new Map()
    reasoningLocksRef.current = new Set()
    reasoningSegmentIndexRef.current = new Map()
    if (reasoningStallTimerRef.current) {
      window.clearTimeout(reasoningStallTimerRef.current)
      reasoningStallTimerRef.current = null
      reasoningLastUpdateRef.current = null
    }
    activeReasoningStreamRef.current = null
    displayLockRef.current = null
    displayPendingRef.current.clear()
    if (displayLockTimerRef.current) {
      window.clearTimeout(displayLockTimerRef.current)
      displayLockTimerRef.current = null
    }
    setDisplayLockState(null)
    bufferedEventsRef.current = []
    restoreStreamQueueRef.current = []
    restoreEventIdsRef.current.clear()
    toolPanelAutoOpenRef.current = false
    pendingUserRef.current = null
    attachmentsSeenRef.current = new Set()
    sizeMapRef.current.clear()
    listResetIndexRef.current = null
    if (listResetRafRef.current) {
      window.cancelAnimationFrame(listResetRafRef.current)
      listResetRafRef.current = null
    }
    virtualizeRestoreRef.current = false
    pendingMessagesRef.current = null
    if (pendingMessagesTimerRef.current) {
      window.clearTimeout(pendingMessagesTimerRef.current)
      pendingMessagesTimerRef.current = null
    }
    if (introTimerRef.current) {
      window.clearTimeout(introTimerRef.current)
      introTimerRef.current = null
    }
    setGreetingTemplate(pickGreetingTemplate())
    setWelcomeIntroState('center')
    setRealTime(true)
    realTimeRef.current = true
  }, [])

  useEffect(() => {
    return () => {
      if (highlightTimerRef.current) {
        window.clearTimeout(highlightTimerRef.current)
      }
      if (listResetRafRef.current) {
        window.cancelAnimationFrame(listResetRafRef.current)
        listResetRafRef.current = null
        listResetIndexRef.current = null
      }
      if (pendingMessagesTimerRef.current) {
        window.clearTimeout(pendingMessagesTimerRef.current)
        pendingMessagesTimerRef.current = null
        pendingMessagesRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    sessionsRef.current = sessions
  }, [sessions])

  useEffect(() => {
    if (!sessionId) return
    const meta = sessions.find((item) => item.session_id === sessionId)
    if (!meta) return
    const normalizedStatus = normalizeSessionStatus(meta.status ?? null)
    const nextActive = Boolean(meta.is_active) || isSessionStatusRunning(normalizedStatus)
    setSessionActive(nextActive)
    setSessionStatus(normalizedStatus)
    if (normalizedStatus === 'completed') {
      setStatusTodoText(null)
      setStatusTodoPrev(null)
      statusTodoRef.current = null
    }
  }, [sessionId, sessions])

  useEffect(() => {
    sessionIdRef.current = sessionId ?? null
    autoEnsureKeyRef.current = null
  }, [sessionId])

  useEffect(() => {
    hasHistoryRef.current = false
    setHasHistory(false)
    setRestoreAttempted(false)
    fullHistoryModeRef.current = false
    fullHistoryRequestRef.current = false
    setHistoryTruncated(false)
    setHistoryLimit(null)
    setHistoryLoadingFull(false)
    setShowFullHistory(false)
  }, [sessionId])

  useEffect(() => {
    if (messages.length === 0 || hasHistoryRef.current) return
    hasHistoryRef.current = true
    setHasHistory(true)
  }, [messages])

  useEffect(() => {
    isRestoringRef.current = isRestoring
  }, [isRestoring])

  useEffect(() => {
    statusTodoRef.current = null
    setStatusTodoText(null)
    setStatusTodoPrev(null)
    setStatusTodoKey(0)
  }, [sessionId])

  useEffect(() => {
    questionPromptRef.current = questionPrompt
  }, [questionPrompt])

  useEffect(() => {
    clarifyPromptRef.current = clarifyPrompt
  }, [clarifyPrompt])

  const applyExternalQuestionAnswer = useCallback(
    (detail: LabQuestionAnsweredDetail | null | undefined) => {
      if (!detail) return
      const activeSessionId = sessionIdRef.current ?? sessionId ?? null
      if (!activeSessionId || detail.sessionId !== activeSessionId) return
      const toolCallId = detail.toolCallId?.trim()
      if (!toolCallId) return

      const nextMessages = [...messagesRef.current]
      let updated = false

      const questionMessageId = `question_prompt-${toolCallId}`
      const questionIndex = nextMessages.findIndex((item) => item.id === questionMessageId)
      if (questionIndex >= 0) {
        const existing = nextMessages[questionIndex]
        if (existing.type === 'question_prompt') {
          const nextContent: QuestionPromptContent = {
            ...(existing.content as QuestionPromptContent),
            status: 'called',
          }
          if (detail.answers) {
            nextContent.answers = detail.answers
          }
          nextMessages[questionIndex] = { ...existing, content: nextContent }
          updated = true
        }
      } else {
        const clarifyMessageId = `clarify_question-${toolCallId}`
        const clarifyIndex = nextMessages.findIndex((item) => {
          if (item.id === clarifyMessageId) return true
          if (item.type !== 'clarify_question') return false
          return (item.content as ClarifyQuestionContent).toolCallId === toolCallId
        })
        if (clarifyIndex >= 0) {
          const existing = nextMessages[clarifyIndex]
          if (existing.type === 'clarify_question') {
            const content = existing.content as ClarifyQuestionContent
            const nextContent: ClarifyQuestionContent = {
              ...content,
              status: 'answered',
            }
            if (detail.answers && content.options?.length) {
              const selections: string[] = []
              const optionByLabel = new Map(
                content.options.map((option) => [option.label.toLowerCase(), option.id])
              )
              const optionById = new Map(content.options.map((option) => [option.id, option.id]))
              const values: Array<string | number> = []
              Object.values(detail.answers).forEach((value) => {
                if (Array.isArray(value)) {
                  value.forEach((entry) => {
                    if (typeof entry === 'string' || typeof entry === 'number') {
                      values.push(entry)
                    }
                  })
                  return
                }
                if (typeof value === 'string' || typeof value === 'number') {
                  values.push(value)
                }
              })
              values.forEach((raw) => {
                if (typeof raw === 'number') {
                  const index =
                    raw >= 1 && raw <= content.options.length ? raw - 1 : raw >= 0 ? raw : null
                  const option = index != null ? content.options[index] : null
                  if (option && !selections.includes(option.id)) selections.push(option.id)
                  return
                }
                const normalized = raw.trim().toLowerCase()
                if (!normalized) return
                const matched =
                  optionById.get(raw) ||
                  optionByLabel.get(normalized) ||
                  optionByLabel.get(raw.toLowerCase())
                if (matched && !selections.includes(matched)) selections.push(matched)
              })
              if (selections.length) {
                nextContent.selections = selections
              }
            }
            nextMessages[clarifyIndex] = { ...existing, content: nextContent }
            updated = true
          }
        }
      }

      if (updated) {
        updateMessages(nextMessages)
      }

      let cleared = false
      if (questionPromptRef.current?.toolCallId === toolCallId) {
        setQuestionPrompt(null)
        questionPromptRef.current = null
        cleared = true
      }
      if (clarifyPromptRef.current?.toolCallId === toolCallId) {
        setClarifyPrompt(null)
        clarifyPromptRef.current = null
        cleared = true
      }
      if (cleared && isCopilotSurface) {
        setCopilotStatus(null)
      }
    },
    [isCopilotSurface, sessionId, updateMessages]
  )

  useEffect(() => {
    if (typeof window === 'undefined') return
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<LabQuestionAnsweredDetail>).detail
      applyExternalQuestionAnswer(detail)
    }
    window.addEventListener(LAB_QUESTION_ANSWERED_EVENT, handler as EventListener)
    return () => window.removeEventListener(LAB_QUESTION_ANSWERED_EVENT, handler as EventListener)
  }, [applyExternalQuestionAnswer])

  useEffect(() => {
    draftSessionIdRef.current = draftSessionId
  }, [draftSessionId])

  useEffect(() => {
    manualSessionSelectionRef.current = false
  }, [projectId])

  useEffect(() => {
    if (!projectId || !requestedSessionId) return
    if (appliedSessionFromUrlRef.current === requestedSessionId) return
    appliedSessionFromUrlRef.current = requestedSessionId
    if (sessionIdRef.current === requestedSessionId) return
    manualSessionSelectionRef.current = true
    setDraftSessionId(null)
    setSessionIdForSurface(projectId, sessionSurface, requestedSessionId)
  }, [projectId, requestedSessionId, sessionSurface, setDraftSessionId, setSessionIdForSurface])

  const upsertSession = useCallback(
    (sessionIdValue: string, patch: Partial<SessionListItem>, options?: { forceTop?: boolean }) => {
      setSessions((current) => {
        const next = [...current]
        const index = next.findIndex((item) => item.session_id === sessionIdValue)
        const existing = index >= 0 ? next[index] : null
        const updated = {
          ...(existing ?? {}),
          session_id: sessionIdValue,
          title: patch.title ?? existing?.title ?? null,
          latest_message: patch.latest_message ?? existing?.latest_message ?? null,
          latest_message_at: patch.latest_message_at ?? existing?.latest_message_at ?? null,
          updated_at: patch.updated_at ?? existing?.updated_at ?? null,
          status: patch.status ?? existing?.status ?? null,
          is_shared: patch.is_shared ?? existing?.is_shared ?? false,
          is_active: patch.is_active ?? existing?.is_active ?? false,
          ...patch,
        }
        if (index >= 0) {
          next[index] = updated
          if (!options?.forceTop) {
            sessionsRef.current = next
            return next
          }
          next.splice(index, 1)
          next.unshift(updated)
          sessionsRef.current = next
          return next
        }
        if (options?.forceTop) {
          next.unshift(updated)
          sessionsRef.current = next
          return next
        }
        next.push(updated)
        sessionsRef.current = next
        return next
      })
    },
    [setSessions]
  )

  const getRenamedTitle = useCallback(
    (sessionIdValue: string) => {
      const value = sessionPreferences.renamed[sessionIdValue]
      return typeof value === 'string' ? value.trim() : ''
    },
    [sessionPreferences.renamed]
  )

  const resolveSessionTitle = useCallback(
    (session: SessionListItem | null | undefined, sessionIdValue?: string) => {
      if (sessionIdValue) {
        const renamed = getRenamedTitle(sessionIdValue)
        if (renamed) return renamed
      }
      const raw = typeof session?.title === 'string' ? session.title.trim() : ''
      return raw || 'New Chat'
    },
    [getRenamedTitle]
  )

  const pinnedSessionRank = useMemo(() => {
    const rank = new Map<string, number>()
    sessionPreferences.pinned.forEach((id, index) => {
      rank.set(id, index)
    })
    return rank
  }, [sessionPreferences.pinned])

  const pinnedSessionSet = useMemo(
    () => new Set(sessionPreferences.pinned),
    [sessionPreferences.pinned]
  )

  const loadLatestSession = useCallback(
    async (options?: { force?: boolean; limit?: number; adopt?: boolean }) => {
      debugLog('latest:request', {
        force: Boolean(options?.force),
        limit: typeof options?.limit === 'number' ? options.limit : null,
        adopt: Boolean(options?.adopt),
        loadedProjectId: latestSessionLoadedRef.current,
      })

      if (!projectId || readOnlyMode) {
        debugLog('latest:skip', { reason: 'no_project_or_readonly' })
        return null
      }
      if (!allowSurfaceFallback) {
        debugLog('latest:skip', { reason: 'surface_managed_externally' })
        return null
      }
      const loadedKey = `${projectId}:${sessionSurface}`
      if (!options?.force && latestSessionLoadedRef.current === loadedKey) {
        debugLog('latest:skip', { reason: 'already_loaded' })
        return null
      }
      try {
        let latest = null
        let usedFallback = false
        if (isQuestRuntimeSurface()) {
          latest = await getQuestLatestSession(projectId, options?.limit)
        } else {
          latest = await getLatestSession(projectId, options?.limit, sessionSurface)
          if (!latest?.session_id) {
            latest = await getLatestSession(projectId, options?.limit)
            usedFallback = Boolean(latest?.session_id)
          }
        }
        if (!latest?.session_id) {
          debugLog('latest:none', { usedFallback })
          return null
        }
        latestSessionLoadedRef.current = loadedKey
        syncRuntimeFromSession(latest)

        const latestId = latest.session_id
        const normalizedStatus = normalizeSessionStatus(latest.status ?? null)
        const latestIsActive = Boolean(latest.is_active) || isSessionStatusRunning(normalizedStatus)
        upsertSession(
          latestId,
          {
            title: latest.title ?? 'New Chat',
            status: normalizedStatus,
            latest_message: latest.latest_message ?? null,
            latest_message_at: latest.latest_message_at ?? null,
            updated_at: latest.updated_at ?? null,
            is_active: latestIsActive,
          },
          { forceTop: true }
        )

        if (sessionIdRef.current === latestId) {
          setSessionActive(latestIsActive)
        }

        const normalizedEvents: AgentSSEEvent[] = []
        const agentIndex = buildSessionAgentIndex(latest.agents)
        const sessionMeta =
          latest.session_metadata && typeof latest.session_metadata === 'object'
            ? (latest.session_metadata as Record<string, unknown>)
            : null
        for (const rawEvent of latest.events ?? []) {
          const normalized = coerceRestoredEvent(rawEvent)
          if (!normalized) continue
          normalizedEvents.push(hydrateEventMetadata(normalized, sessionMeta, agentIndex))
        }
        const orderedEvents = sortHydratedEvents(normalizedEvents)
        replaceCachedSessionEvents(latestId, orderedEvents)
        if (orderedEvents.length > 0) {
          const lastEvent = orderedEvents[orderedEvents.length - 1]
          const lastEventId = (lastEvent.data as { event_id?: string }).event_id
          if (typeof lastEventId === 'string') {
            setLastEventId(latestId, lastEventId)
          }
        } else {
          setLastEventId(latestId, null)
        }

        const draftActive = Boolean(draftSessionIdRef.current)
        const currentSessionId = sessionIdRef.current
        const shouldAdopt = Boolean(options?.adopt) && !draftActive
        const shouldSkipRestore = orderedEvents.length === 0
        if (shouldAdopt) {
          if (shouldSkipRestore) {
            skipRestoreRef.current = true
          }
          if (currentSessionId !== latestId) {
            setSessionIdForSurface(projectId, sessionSurface, latestId)
          } else if (!isRestoring) {
            requestRestore()
          }
        } else if (!currentSessionId && !draftActive) {
          if (shouldSkipRestore) {
            skipRestoreRef.current = true
          }
          setSessionIdForSurface(projectId, sessionSurface, latestId)
        }

        debugLog('latest:loaded', {
          sessionId: latestId,
          events: normalizedEvents.length,
          title: latest.title ?? null,
          status: latest.status ?? null,
          usedFallback,
        })

        return latestId
      } catch (error) {
        debugLog('latest:error', { message: error instanceof Error ? error.message : String(error) })
        return null
      }
    },
    [
      debugLog,
      draftSessionIdRef,
      allowSurfaceFallback,
      isRestoring,
      sessionSurface,
      projectId,
      readOnlyMode,
      requestRestore,
      setLastEventId,
      setSessionIdForSurface,
      syncRuntimeFromSession,
      upsertSession,
    ]
  )

  // Handle visibility and mode changes - must be after loadLatestSession is defined
  useEffect(() => {
    const wasVisible = lastVisibleRef.current
    const modeChanged = lastModeRef.current != null && lastModeRef.current !== mode
    const isFirstMount = !wasVisible && lastModeRef.current === null
    lastVisibleRef.current = isVisible
    lastModeRef.current = mode

    const currentSessionId = sessionIdRef.current
    const shouldAutoAdoptLatest =
      allowSurfaceFallback &&
      Boolean(projectId) &&
      !readOnlyMode &&
      !draftSessionIdRef.current &&
      isCopilotSurface &&
      !manualSessionSelectionRef.current &&
      !currentSessionId

    // Handle visible state changes
    if (isVisible && (!wasVisible || modeChanged)) {
      debugLog('visibility:enter', { wasVisible, modeChanged, isFirstMount })
      if (mode === 'welcome') {
        debugLog('sessions:reload', { reason: 'visible_or_mode_changed' })
        void reloadSessionSummaries()
      }
      if (!projectId || readOnlyMode) return
      if (draftSessionIdRef.current) return
      if (currentSessionId && messagesRef.current.length === 0 && !isRestoring) {
        debugLog('restore:request', { reason: 'visible_restore_existing_session' })
        requestRestore()
        return
      }
      const adoptLatest = shouldAutoAdoptLatest || (mode === 'welcome' && !currentSessionId)
      debugLog('latest:trigger', {
        reason: adoptLatest ? 'visible_enter_adopt_latest' : 'visible_enter_load_latest',
      })
      if ((!currentSessionId || adoptLatest) && allowSurfaceFallback) {
        void loadLatestSession({ force: true, adopt: adoptLatest }).then((latestId) => {
          if (!latestId && sessionIdRef.current && !isRestoring) {
            debugLog('restore:request', { reason: 'visible_latest_failed_restore_stored' })
            requestRestore()
          }
        })
      }
      return
    }

    // Improved: On first mount, even if not visible, fetch the latest session so the
    // Copilot conversation history is hydrated after a hard refresh.
    if (isFirstMount && !currentSessionId && !draftSessionIdRef.current) {
      if (!projectId || readOnlyMode) return
      debugLog('latest:trigger', { reason: 'first_mount_no_session' })
      if (allowSurfaceFallback) {
        void loadLatestSession({ force: true, adopt: shouldAutoAdoptLatest })
      }
      return
    }

    // Improved: On first mount, even if not visible, trigger restore if we have a sessionId
    // but no messages loaded. This ensures session content loads after page refresh.
    if (isFirstMount && currentSessionId && messagesRef.current.length === 0) {
      if (!projectId || readOnlyMode) return
      if (!isRestoring) {
        debugLog('restore:request', { reason: 'first_mount_session_no_messages' })
        requestRestore()
      }
    }
  }, [
    debugLog,
    allowSurfaceFallback,
    isRestoring,
    loadLatestSession,
    mode,
    projectId,
    readOnlyMode,
    reloadSessionSummaries,
    requestRestore,
    visible,
    isCopilotSurface,
  ])

  useEffect(() => {
    if (mode !== 'welcome') return
    // Force load when no session is selected to ensure content is displayed after refresh
    const hasNoSession = !sessionIdRef.current && !draftSessionIdRef.current
    debugLog('latest:trigger', { reason: 'welcome_mode_effect', force: hasNoSession })
    void loadLatestSession({ force: hasNoSession })
  }, [debugLog, loadLatestSession, mode])

  useEffect(() => {
    if (!sessionId) return
    const renamed = getRenamedTitle(sessionId)
    if (renamed) {
      if (title !== renamed) setTitle(renamed)
      return
    }
    if (title !== 'New Chat') return
    const session = sessions.find((item) => item.session_id === sessionId)
    if (session?.title) {
      setTitle(session.title)
    }
  }, [getRenamedTitle, sessionId, sessions, title])

  const isEmptySession = useCallback((session: SessionListItem) => {
    const renamed = getRenamedTitle(session.session_id)
    if (renamed) return false
    const titleValue = typeof session.title === 'string' ? session.title.trim() : ''
    const messageValue =
      typeof session.latest_message === 'string' ? session.latest_message.trim() : ''
    const normalizedTitle = titleValue.toLowerCase()
    const isPlaceholderTitle = normalizedTitle === 'new chat' || normalizedTitle === 'new task'
    return !messageValue && (!titleValue || isPlaceholderTitle)
  }, [getRenamedTitle])

  const filteredSessions = useMemo(
    () =>
      sessions.filter((session) => {
        if (!isEmptySession(session)) return true
        return session.session_id === sessionId
      }),
    [isEmptySession, sessionId, sessions]
  )

  const draftSession = useMemo<SessionListItem | null>(() => {
    if (!draftSessionId) return null
    return {
      session_id: draftSessionId,
      title: 'New Chat',
      latest_message: null,
      latest_message_at: null,
      updated_at: Math.floor(Date.now() / 1000),
      status: null,
      is_shared: false,
    }
  }, [draftSessionId])

  const visibleSessions = useMemo(() => {
    if (pinnedSessionSet.size === 0) {
      return draftSession ? [draftSession, ...filteredSessions] : filteredSessions
    }
    const pinned: SessionListItem[] = []
    const rest: SessionListItem[] = []
    filteredSessions.forEach((session) => {
      if (pinnedSessionSet.has(session.session_id)) {
        pinned.push(session)
      } else {
        rest.push(session)
      }
    })
    pinned.sort((a, b) => {
      const rankA = pinnedSessionRank.get(a.session_id) ?? 0
      const rankB = pinnedSessionRank.get(b.session_id) ?? 0
      return rankA - rankB
    })
    const combined = [...pinned, ...rest]
    return draftSession ? [draftSession, ...combined] : combined
  }, [draftSession, filteredSessions, pinnedSessionRank, pinnedSessionSet])

  const activeSessionIdForList = sessionId ?? draftSessionId ?? null
  const triggerSessionHighlight = useCallback((sessionIdValue: string) => {
    setHighlightSessionId(sessionIdValue)
    if (highlightTimerRef.current) {
      window.clearTimeout(highlightTimerRef.current)
    }
    highlightTimerRef.current = window.setTimeout(() => {
      setHighlightSessionId((current) => (current === sessionIdValue ? null : current))
    }, 900)
  }, [])

  const handleWelcomeSessionsOpen = useCallback(() => {
    if (!historyPanelInline) return
    console.info('[CopilotAudit][welcome] open sessions list + reload summaries', {
      projectId: projectId ?? null,
    })
    debugLog('welcome:sessions:open')
    setHistoryOpenValue(true)
    void reloadSessionSummaries()
  }, [debugLog, historyPanelInline, reloadSessionSummaries, setHistoryOpenValue])

  useEffect(() => {
    if (!historyPanelInline) return
    historyOpenPreferenceRef.current = historyOpenValue
  }, [historyOpenValue, historyPanelInline])

  useEffect(() => {
    if (!renameDialogOpen) return
    window.setTimeout(() => renameInputRef.current?.focus(), 0)
  }, [renameDialogOpen])

  useEffect(() => {
    if (!historyPanelEnabled) {
      if (historyOpenValue) {
        setHistoryOpenValue(false)
      }
      return
    }
    if (!historyPanelInline) return
    const preferred = historyOpenPreferenceRef.current
    if (historyOpenValue !== preferred) {
      setHistoryOpenValue(preferred)
    }
  }, [historyOpenValue, historyPanelEnabled, historyPanelInline, setHistoryOpenValue])

  useEffect(() => {
    if (!historyPanelOverlay || !historyOpenValue) return
    void reloadSessionSummaries()
  }, [historyOpenValue, historyPanelOverlay, reloadSessionSummaries])

  useEffect(() => {
    if (!introEnabled) {
      if (welcomeIntroState !== 'done') {
        setWelcomeIntroState('done')
      }
      return
    }
    if (welcomeIntroState === 'dropping') return
    if (!isRestoring && messages.length === 0) {
      if (welcomeIntroState !== 'center') {
        setWelcomeIntroState('center')
      }
      return
    }
    if (welcomeIntroState !== 'done') {
      setWelcomeIntroState('done')
    }
  }, [introEnabled, isRestoring, messages.length, welcomeIntroState])

  useEffect(() => {
    return () => {
      if (introTimerRef.current) {
        window.clearTimeout(introTimerRef.current)
        introTimerRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    toolCallSeenRef.current = new Set()
    statusToolSeenRef.current = new Set()
    setToolCallCount(0)
  }, [sessionId])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const stored = window.localStorage.getItem(toolPanelSizeKey)
    if (!stored) return
    const parsed = Number(stored)
    if (!Number.isFinite(parsed)) return
    const clamped = Math.min(TOOL_PANEL_MAX_SIZE, Math.max(TOOL_PANEL_MIN_SIZE, parsed))
    setToolPanelSize(clamped)
  }, [toolPanelSizeKey])

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(toolPanelSizeKey, String(toolPanelSize))
  }, [toolPanelSize, toolPanelSizeKey])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const media = window.matchMedia(`(max-width: ${TOOL_PANEL_BREAKPOINT}px)`)
    const update = () => setIsCompactView(media.matches)
    update()
    if (media.addEventListener) {
      media.addEventListener('change', update)
      return () => media.removeEventListener('change', update)
    }
    media.addListener(update)
    return () => media.removeListener(update)
  }, [])

  useLayoutEffect(() => {
    if (typeof document === 'undefined') return
    if (!toolPanelMountId) {
      setToolPanelMount(null)
      debugLog('portal:toolpanel:disabled')
      return
    }

    let cancelled = false

    const resolve = (source: 'initial' | 'observer') => {
      const node = document.getElementById(toolPanelMountId)
      if (!node) return false
      if (!cancelled) setToolPanelMount(node)
      debugLog('portal:toolpanel:found', { mountId: toolPanelMountId, source })
      return true
    }

    if (resolve('initial')) {
      return () => {
        cancelled = true
      }
    }

    setToolPanelMount(null)
    debugLog('portal:toolpanel:waiting', { mountId: toolPanelMountId })
    const observer = new MutationObserver(() => {
      if (resolve('observer')) observer.disconnect()
    })
    observer.observe(document.body, { childList: true, subtree: true })
    const timeout =
      typeof window !== 'undefined'
        ? window.setTimeout(() => observer.disconnect(), 5000)
        : null

    return () => {
      cancelled = true
      observer.disconnect()
      if (timeout && typeof window !== 'undefined') {
        window.clearTimeout(timeout)
      }
    }
  }, [debugLog, toolPanelMountId])

  useLayoutEffect(() => {
    if (typeof document === 'undefined') return
    if (!sessionListMountId) {
      setSessionListMount(null)
      debugLog('portal:sessions:disabled')
      return
    }

    let cancelled = false

    const resolve = (source: 'initial' | 'observer') => {
      const node = document.getElementById(sessionListMountId)
      if (!node) return false
      if (!cancelled) setSessionListMount(node)
      debugLog('portal:sessions:found', { mountId: sessionListMountId, source })
      return true
    }

    if (resolve('initial')) {
      return () => {
        cancelled = true
      }
    }

    setSessionListMount(null)
    debugLog('portal:sessions:waiting', { mountId: sessionListMountId })
    const observer = new MutationObserver(() => {
      if (resolve('observer')) observer.disconnect()
    })
    observer.observe(document.body, { childList: true, subtree: true })
    const timeout =
      typeof window !== 'undefined'
        ? window.setTimeout(() => observer.disconnect(), 5000)
        : null

    return () => {
      cancelled = true
      observer.disconnect()
      if (timeout && typeof window !== 'undefined') {
        window.clearTimeout(timeout)
      }
    }
  }, [debugLog, sessionListMountId])

  useEffect(() => {
    const handleTakeoverEvent = (event: Event) => {
      const customEvent = event as CustomEvent<{
        sessionId?: string
        active?: boolean
      }>
      const detail = customEvent.detail || {}
      if (typeof detail.active === 'boolean') {
        setTakeoverActive(detail.active)
        if (!detail.active) {
          setTakeoverSessionId('')
        }
      }
      if (typeof detail.sessionId === 'string') {
        setTakeoverSessionId(detail.sessionId)
      }
    }

    window.addEventListener('takeover', handleTakeoverEvent as EventListener)
    window.addEventListener('ai-manus:browser:takeover', handleTakeoverEvent as EventListener)

    return () => {
      window.removeEventListener('takeover', handleTakeoverEvent as EventListener)
      window.removeEventListener('ai-manus:browser:takeover', handleTakeoverEvent as EventListener)
    }
  }, [])

  const startNewSession = useCallback(async () => {
    if (!projectId || readOnlyMode) return
    if (newSessionRequestRef.current) return
    const draftId = `draft-${Date.now()}`
    newSessionRequestRef.current = draftId
    clearSessionIdForSurface(projectId, sessionSurface)
    setDraftSessionId(draftId)
    setToolPanelView('tool')
    setToolPanelOpen(true)
    resetConversation()
    setExecutionTarget(projectId, 'sandbox')

    try {
      const created = await createSession(projectId)
      if (!created?.session_id) {
        throw new Error('session_create_failed')
      }
      if (newSessionRequestRef.current !== draftId || draftSessionIdRef.current !== draftId) {
        return
      }
      skipRestoreRef.current = true
      setDraftSessionId(null)
      setSessionIdForSurface(projectId, sessionSurface, created.session_id)
      setLastEventId(created.session_id, null)
      upsertSession(
        created.session_id,
        {
          title: created.title ?? 'New Chat',
          status: normalizeSessionStatus(created.status) ?? 'pending',
          latest_message: null,
          latest_message_at: Math.floor(Date.now() / 1000),
          updated_at: Math.floor(Date.now() / 1000),
          is_active: typeof created.is_active === 'boolean' ? created.is_active : false,
        },
        { forceTop: true }
      )
      triggerSessionHighlight(created.session_id)
    } catch (error) {
      if (newSessionRequestRef.current === draftId) {
        addToast({
          type: 'error',
          title: 'Unable to create session',
          description: 'Please try again in a moment.',
        })
      }
    } finally {
      if (newSessionRequestRef.current === draftId) {
        newSessionRequestRef.current = null
      }
    }
  }, [
    addToast,
    clearSessionIdForSurface,
    projectId,
    readOnlyMode,
    resetConversation,
    sessionSurface,
    setDraftSessionId,
    setExecutionTarget,
    setLastEventId,
    setSessionIdForSurface,
    setToolPanelOpen,
    setToolPanelView,
    triggerSessionHighlight,
    upsertSession,
  ])

  useEffect(() => {
    if (!historyPanelInline || readOnlyMode) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        void startNewSession()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [historyPanelInline, readOnlyMode, startNewSession])

  const activeResource = useMemo(() => {
    if (!activeTab) return null
    const context = activeTab.context
    const surfaceState = workspaceTabState[activeTab.id]
    const customFileId = extractCustomFileId(context.customData)
    const customPathHint = extractCustomFilePath(context.customData)
    const rawResourceId = context.resourceId
    const resourceId =
      context.type === 'custom' ? customFileId ?? rawResourceId : rawResourceId ?? customFileId
    const resourcePathHint = context.resourcePath?.trim() || customPathHint || surfaceState?.resourcePath || ''
    const hasFilePathHint = hasConcreteResourcePath(resourcePathHint)
    const cliRef = resourceId ? parseCliFileId(resourceId) : null
    const node = resourceId ? findNode(resourceId) : null
    const nodeIsFile = node?.type === 'file' || node?.type === 'notebook'
    const isFileContext =
      context.type === 'file' ||
      context.type === 'notebook' ||
      hasFilePathHint ||
      Boolean(customFileId) ||
      nodeIsFile ||
      Boolean(cliRef)
    const serverRoot =
      cliRef != null
        ? cliServers.find((server) => server.id === cliRef.serverId)?.server_root ?? undefined
        : undefined

    let resourcePath = resourcePathHint
    let resourceName = context.resourceName || surfaceState?.resourceName

    if (!cliRef && nodeIsFile && node?.path) {
      resourcePath = toFilesResourcePath(node.path)
      if (!resourceName && node?.name) {
        resourceName = node.name
      }
    }

    if (!resourcePath && isFileContext && resourceId) {
      if (cliRef) {
        resourcePath = toCliResourcePath({
          serverId: cliRef.serverId,
          path: cliRef.path,
          serverRoot,
        })
        } else {
          if (nodeIsFile && node?.path) {
            resourcePath = toFilesResourcePath(node.path)
          }
          if (!resourceName && nodeIsFile && node?.name) {
            resourceName = node.name
          }
        }
    }

    if (resourcePath && isFileContext) {
      if (cliRef) {
        if (!resourcePath.startsWith('/CLIFILES')) {
          resourcePath = toCliResourcePath({
            serverId: cliRef.serverId,
            path: cliRef.path,
            serverRoot,
          })
        }
      } else if (!resourcePath.startsWith('/FILES')) {
        resourcePath = toFilesResourcePath(resourcePath)
      }
    }

    return {
      tabId: activeTab.id,
      type: activeTab.context.type,
      resourceId,
      resourcePath,
      resourceName,
      mimeType: activeTab.context.mimeType,
      title: activeTab.title,
      pluginId: activeTab.pluginId,
    }
  }, [activeTab, cliServers, findNode, workspaceTabState])

  const [recentFileIdPaths, setRecentFileIdPaths] = useState<Record<string, string>>({})

  const activeRecentFilePath = useMemo(() => {
    if (!activeResource) return ''
    const resourcePathRaw = activeResource.resourcePath ?? ''
    const isFileResource =
      activeResource.type === 'file' ||
      activeResource.type === 'notebook' ||
      resourcePathRaw.startsWith('/FILES') ||
      resourcePathRaw.startsWith('/CLIFILES') ||
      Boolean(activeResource.resourceId && recentFileIdPaths[activeResource.resourceId])
    if (!isFileResource) return ''
    const fallbackPath =
      activeResource.resourceId && recentFileIdPaths[activeResource.resourceId]
        ? recentFileIdPaths[activeResource.resourceId]
        : ''
    const normalizedRaw = normalizeRecentPath(resourcePathRaw)
    const resourcePath = hasConcreteResourcePath(normalizedRaw)
      ? normalizedRaw
      : fallbackPath
        ? normalizeRecentPath(fallbackPath)
        : ''
    if (!resourcePath) return ''
    if (resourcePath === '/FILES' || resourcePath === '/CLIFILES') return ''
    return resourcePath
  }, [activeResource, recentFileIdPaths])

  const cachedRecentFiles = useMemo(() => {
    if (!projectId) return []
    const entries = Object.values(fileContentEntries).filter(
      (entry) => entry.projectId === projectId
    )
    if (entries.length === 0) return []
    entries.sort((a, b) => b.lastAccessedAt - a.lastAccessedAt)
    const paths: string[] = []
    for (const entry of entries) {
      const node = findNode(entry.fileId)
      if (!node?.path) continue
      const normalized = normalizeRecentPath(toFilesResourcePath(node.path))
      if (!normalized || normalized === '/FILES') continue
      paths.push(normalized)
      if (paths.length >= MAX_RECENT_FILES) break
    }
    return paths
  }, [fileContentEntries, findNode, projectId])

  useEffect(() => {
    if (!recentFilesEnabled || tabs.length === 0) return
    const missingIds = new Set<string>()
    for (const tab of tabs) {
      const context = tab.context
      const customFileId = extractCustomFileId(context.customData)
      const customPathHint = extractCustomFilePath(context.customData)
      const rawResourceId = context.resourceId
      const resourceId =
        context.type === 'custom' ? customFileId ?? rawResourceId : rawResourceId ?? customFileId
      if (!resourceId) continue
      if (parseCliFileId(resourceId)) continue
      if (recentFileIdPaths[resourceId]) continue
      const resourcePathHint = context.resourcePath?.trim() || customPathHint || ''
      const hasPathHint = hasConcreteResourcePath(resourcePathHint)
      const node = findNode(resourceId)
      const nodeIsFile = node?.type === 'file' || node?.type === 'notebook'
      if (node && !nodeIsFile) continue
      if (hasPathHint || (nodeIsFile && node?.path)) continue
      missingIds.add(resourceId)
      if (missingIds.size >= MAX_RECENT_FILES) break
    }
    if (missingIds.size === 0) return
    let active = true
    const ids = Array.from(missingIds)
    void Promise.allSettled(ids.map((id) => getFile(id))).then((results) => {
      if (!active) return
      const updates: Record<string, string> = {}
      results.forEach((result, index) => {
        if (result.status !== 'fulfilled') return
        const file = result.value
        if (!file?.path) return
        const normalized = normalizeRecentPath(toFilesResourcePath(file.path))
        if (!normalized || normalized === '/FILES') return
        updates[ids[index]] = normalized
      })
      if (Object.keys(updates).length === 0) return
      setRecentFileIdPaths((prev) => ({ ...prev, ...updates }))
    })
    return () => {
      active = false
    }
  }, [findNode, recentFileIdPaths, recentFilesEnabled, tabs])

  const recentFiles = useMemo(() => {
    const seen = new Set<string>()
    const files: string[] = []
    const normalizedActive = activeRecentFilePath
      ? normalizeRecentPath(activeRecentFilePath)
      : ''
    for (const tab of tabs) {
      const context = tab.context
      const customFileId = extractCustomFileId(context.customData)
      const customPathHint = extractCustomFilePath(context.customData)
      const rawResourceId = context.resourceId
      const resourceId =
        context.type === 'custom' ? customFileId ?? rawResourceId : rawResourceId ?? customFileId
      const resourcePathHint = context.resourcePath?.trim() || customPathHint || ''
      const hasFilePathHint = hasConcreteResourcePath(resourcePathHint)
      const node = resourceId ? findNode(resourceId) : null
      const nodeIsFile = node?.type === 'file' || node?.type === 'notebook'
      const isFileContext =
        context.type === 'file' ||
        context.type === 'notebook' ||
        hasFilePathHint ||
        Boolean(customFileId) ||
        nodeIsFile
      let resourcePath = resourcePathHint
      const cliRef = resourceId ? parseCliFileId(resourceId) : null
      if (!isFileContext && !cliRef) continue
      const serverRoot = cliRef
        ? cliServers.find((server) => server.id === cliRef.serverId)?.server_root ?? undefined
        : undefined

      if (!resourcePath && resourceId && !hasFilePathHint) {
        if (cliRef) {
          resourcePath = toCliResourcePath({
            serverId: cliRef.serverId,
            path: cliRef.path,
            serverRoot,
          })
        } else {
          if (nodeIsFile && node?.path) {
            resourcePath = toFilesResourcePath(node.path)
          } else if (resourceId && recentFileIdPaths[resourceId]) {
            resourcePath = recentFileIdPaths[resourceId]
          }
        }
      } else if (!resourcePath && resourceId && recentFileIdPaths[resourceId]) {
        resourcePath = recentFileIdPaths[resourceId]
      }

      if (resourcePath) {
        const isCliPath = resourcePath.startsWith('/CLIFILES')
        if (cliRef || isCliPath) {
          if (!resourcePath.startsWith('/CLIFILES') && cliRef) {
            resourcePath = toCliResourcePath({
              serverId: cliRef.serverId,
              path: cliRef.path,
              serverRoot,
            })
          }
        } else if (!resourcePath.startsWith('/FILES')) {
          resourcePath = toFilesResourcePath(resourcePath)
        }
      }

      resourcePath = normalizeRecentPath(resourcePath)
      if (!resourcePath) continue
      if (resourcePath === '/FILES' || resourcePath === '/CLIFILES') continue
      if (seen.has(resourcePath)) continue
      seen.add(resourcePath)
      files.push(resourcePath)
    }
    const hasFilesPath = files.some((path) => path.startsWith('/FILES'))
    if (!hasFilesPath && cachedRecentFiles.length > 0) {
      for (const path of cachedRecentFiles) {
        if (seen.has(path)) continue
        seen.add(path)
        files.push(path)
        if (files.length >= MAX_RECENT_FILES) break
      }
    }
    if (normalizedActive) {
      const existingIndex = files.indexOf(normalizedActive)
      if (existingIndex === -1) {
        files.unshift(normalizedActive)
      } else if (existingIndex > 0) {
        files.splice(existingIndex, 1)
        files.unshift(normalizedActive)
      }
    }
    return files
  }, [activeRecentFilePath, cachedRecentFiles, cliServers, findNode, recentFileIdPaths, tabs])

  const recentFilesPrompt = useMemo(() => {
    if (recentFiles.length === 0) return ''
    const lines = recentFiles.map((path) => {
      const normalizedPath = normalizeRecentPath(path)
      const isActive =
        activeRecentFilePath && normalizeRecentPath(activeRecentFilePath) === normalizedPath
      return isActive ? `- [active] ${path}` : `- ${path}`
    })
    return `Recent files (active first):\n${lines.join('\n')}`
  }, [activeRecentFilePath, recentFiles])

  const openTabs = useMemo(() => {
    if (!tabs.length) return []
    const snapshots: WorkspaceOpenTabSnapshot[] = []
    const activeId = activeTab?.id ?? null
    for (const tab of tabs) {
      const context = tab.context
      const surfaceState = workspaceTabState[tab.id]
      const isFileContext = context.type === 'file' || context.type === 'notebook'
      const resourceId = context.resourceId
      const cliRef = isFileContext && resourceId ? parseCliFileId(resourceId) : null
      const node = isFileContext && resourceId ? findNode(resourceId) : null
      const serverRoot =
        cliRef != null
          ? cliServers.find((server) => server.id === cliRef.serverId)?.server_root ?? undefined
          : undefined

      let resourcePath = context.resourcePath?.trim() || surfaceState?.resourcePath || ''
      let resourceName = context.resourceName || surfaceState?.resourceName

      if (!cliRef && node?.path) {
        resourcePath = toFilesResourcePath(node.path)
        if (!resourceName && node?.name) {
          resourceName = node.name
        }
      }

      if (!resourcePath && isFileContext && resourceId) {
        if (cliRef) {
          resourcePath = toCliResourcePath({
            serverId: cliRef.serverId,
            path: cliRef.path,
            serverRoot,
          })
        } else {
          if (node?.path) {
            resourcePath = toFilesResourcePath(node.path)
          }
          if (!resourceName && node?.name) {
            resourceName = node.name
          }
        }
      }

      if (resourcePath && isFileContext) {
        if (cliRef) {
          if (!resourcePath.startsWith('/CLIFILES')) {
            resourcePath = toCliResourcePath({
              serverId: cliRef.serverId,
              path: cliRef.path,
              serverRoot,
            })
          }
        } else if (!resourcePath.startsWith('/FILES')) {
          resourcePath = toFilesResourcePath(resourcePath)
        }
      }

      if (resourcePath === '/FILES' || resourcePath === '/CLIFILES') {
        resourcePath = ''
      }

      const tabIssue = workspaceActiveIssues[tab.id]
      const status: string[] = []
      if (surfaceState?.documentMode) status.push(surfaceState.documentMode)
      if (surfaceState?.isReadOnly) status.push('read_only')
      if (surfaceState?.compileState === 'compiling') status.push('compiling')
      if ((surfaceState?.selectionCount || 0) > 0) status.push('quote')
      if ((surfaceState?.diagnostics?.errors || 0) > 0) status.push('error')
      else if ((surfaceState?.diagnostics?.warnings || 0) > 0) status.push('warning')
      if (tabIssue?.kind === 'latex_error') {
        status.push(tabIssue.severity === 'warning' ? 'focused_warning' : 'focused_error')
      }

      snapshots.push({
        tabId: tab.id,
        title: tab.title,
        type: context.type,
        pluginId: tab.pluginId,
        resourceId,
        resourcePath: resourcePath || undefined,
        resourceName: resourceName || undefined,
        mimeType: context.mimeType,
        isActive: tab.id === activeId,
        contentKind: surfaceState?.contentKind,
        documentMode: surfaceState?.documentMode,
        pageNumber: surfaceState?.pageNumber,
        status: status.length > 0 ? status : undefined,
        focusedIssue:
          tabIssue?.kind === 'latex_error'
            ? {
                kind: tabIssue.kind,
                resourcePath: tabIssue.resourcePath,
                resourceName: tabIssue.resourceName,
                line: tabIssue.line,
                message: tabIssue.message,
                severity: tabIssue.severity,
              }
            : undefined,
      })
    }
    return snapshots
  }, [activeTab?.id, cliServers, findNode, tabs, workspaceActiveIssues, workspaceTabState])

  const recentFilesAvailable = recentFiles.length > 0
  const activeCliServerLabel = useMemo(() => {
    if (!cliServerId) return ''
    const server = cliServers.find((item) => item.id === cliServerId)
    return server?.name || server?.hostname || cliServerId.slice(0, 6)
  }, [cliServerId, cliServers])
  const terminalRuntimeSuffix = activeCliServerLabel || cliServerId?.slice(0, 6) || ''
  const terminalRuntimeLabel =
    executionTarget === 'cli'
      ? terminalRuntimeSuffix
        ? `CLI Server: ${terminalRuntimeSuffix}`
        : 'CLI Server'
      : 'Copilot'
  const runtimeLocked = mode === 'welcome' && messages.length > 0
  const hasCliServerSupport = cliServers.length > 0 || Boolean(cliServerId)
  const canSwitchToCli = onlineCliServers.length > 0
  const showTerminalRuntimeToggle = Boolean(
    (runtimeToggleEnabled ?? true) && projectId && hasCliServerSupport
  )
  const terminalRuntimeToggleDisabled =
    runtimeSwitching ||
    runtimeLocked ||
    (!canSwitchToCli && executionTarget !== 'cli') ||
    (labRuntimeLocked && executionTarget === 'cli')

  useEffect(() => {
    if (recentFilesEnabled && !recentFilesAvailable) {
      setRecentFilesEnabled(false)
    }
  }, [recentFilesAvailable, recentFilesEnabled])

  const handleRecentFilesToggle = useCallback(() => {
    if (!recentFilesAvailable || readOnlyMode) return
    setRecentFilesEnabled((prev) => !prev)
  }, [readOnlyMode, recentFilesAvailable])

  const handleRecentFilesRemove = useCallback(() => {
    setRecentFilesEnabled(false)
  }, [])

  const buildContext = useCallback(() => {
    const locationHref = typeof window !== 'undefined' ? window.location.href : null
    const locationPathname = typeof window !== 'undefined' ? window.location.pathname : null
    const pageTitle = typeof document !== 'undefined' ? document.title : null
    // Avoid pulling the full plugin registry here to prevent circular imports.
    const pluginName = activeResource?.pluginId ?? null
    const workspaceSurfaceState = useWorkspaceSurfaceStore.getState()
    const activeSurfaceState =
      activeResource?.tabId != null
        ? workspaceSurfaceState.tabState[activeResource.tabId] ?? workspaceTabState[activeResource.tabId]
        : undefined
    const liveReferenceIds =
      activeResource?.tabId != null
        ? workspaceSurfaceState.referencesByTabId[activeResource.tabId] || []
        : []
    const liveActiveReferenceId =
      activeResource?.tabId != null
        ? workspaceSurfaceState.activeReferenceByTabId[activeResource.tabId]
        : null
    const liveActiveTabReference =
      liveActiveReferenceId ? workspaceSurfaceState.references[liveActiveReferenceId] || null : null
    const liveActiveTabReferences =
      liveReferenceIds.length > 0
        ? liveReferenceIds
            .map((referenceId) => workspaceSurfaceState.references[referenceId])
            .filter((item): item is WorkspaceSelectionReference => Boolean(item))
        : []
    const liveActiveIssue =
      activeResource?.tabId != null ? workspaceSurfaceState.activeIssueByTabId[activeResource.tabId] : null
    const selection = liveActiveTabReference
      ? {
          id: liveActiveTabReference.id,
          kind: liveActiveTabReference.kind,
          fileId: liveActiveTabReference.fileId,
          resourceId: liveActiveTabReference.resourceId,
          resourcePath: liveActiveTabReference.resourcePath,
          resourceName: liveActiveTabReference.resourceName,
          pageNumber: liveActiveTabReference.pageNumber,
          selectedText: liveActiveTabReference.selectedText,
          markdownExcerpt: liveActiveTabReference.markdownExcerpt,
          excerptStatus: liveActiveTabReference.excerptStatus,
          rects: liveActiveTabReference.rects,
          createdAt: liveActiveTabReference.createdAt,
        }
      : null
    const anchors =
      liveActiveTabReferences.length > 0
        ? liveActiveTabReferences.map((reference) => ({
            id: reference.id,
            kind: reference.kind,
            resourcePath: reference.resourcePath,
            resourceName: reference.resourceName,
            pageNumber: reference.pageNumber,
            selectedText: reference.selectedText,
            markdownExcerpt: reference.markdownExcerpt,
          }))
        : undefined
    const focusedIssue =
      liveActiveIssue?.kind === 'latex_error'
        ? {
            kind: liveActiveIssue.kind,
            fileId: liveActiveIssue.fileId,
            resourceId: liveActiveIssue.resourceId,
            resourcePath: liveActiveIssue.resourcePath,
            resourceName: liveActiveIssue.resourceName,
            line: liveActiveIssue.line,
            message: liveActiveIssue.message,
            severity: liveActiveIssue.severity,
            excerpt: liveActiveIssue.excerpt,
            createdAt: liveActiveIssue.createdAt,
          }
        : null

    const indexedDocuments =
      openTabs.length > 0
        ? [...openTabs]
            .sort((left, right) => {
              const leftActive = left.isActive ? 1 : 0
              const rightActive = right.isActive ? 1 : 0
              return rightActive - leftActive
            })
            .map((tab, index) => ({
              docIndex: index + 1,
              tabId: tab.tabId,
              title: tab.title,
              resourceId: tab.resourceId,
              resourcePath: tab.resourcePath,
              resourceName: tab.resourceName,
              mimeType: tab.mimeType,
              pluginId: tab.pluginId,
              type: tab.type,
              contentKind: tab.contentKind,
              documentMode: tab.documentMode,
              pageNumber: tab.pageNumber,
              status: Array.isArray(tab.status) ? tab.status : undefined,
              isActive: Boolean(tab.isActive),
              focusedIssue:
                tab.focusedIssue && typeof tab.focusedIssue === 'object' ? tab.focusedIssue : undefined,
            }))
        : []

    const activeIndexedDocument =
      indexedDocuments.find((item) => item.isActive) ||
      (activeResource
        ? {
            docIndex: 1,
            tabId: activeResource.tabId,
            title: activeResource.title,
            resourceId: activeResource.resourceId,
            resourcePath: activeResource.resourcePath,
            resourceName: activeResource.resourceName,
            mimeType: activeResource.mimeType,
            pluginId: activeResource.pluginId,
            type: activeResource.type,
            contentKind: activeSurfaceState?.contentKind,
            documentMode: activeSurfaceState?.documentMode,
            pageNumber: activeSurfaceState?.pageNumber,
            isActive: true,
          }
        : null)

    const focusItems: Array<Record<string, unknown>> = []
    if (selection) {
      const selectionDocIndex =
        indexedDocuments.find((item) => item.tabId === activeResource?.tabId)?.docIndex ??
        activeIndexedDocument?.docIndex
      focusItems.push({
        type: 'pdf_selection',
        docIndex: selectionDocIndex,
        tabId: activeResource?.tabId,
        resourceId: selection.resourceId,
        resourcePath: selection.resourcePath,
        resourceName: selection.resourceName,
        pageNumber: selection.pageNumber,
        selectedText: selection.selectedText,
        markdownExcerpt: selection.markdownExcerpt,
      })
    }
    if (focusedIssue) {
      const issueDocIndex =
        indexedDocuments.find((item) => item.tabId === activeResource?.tabId)?.docIndex ??
        activeIndexedDocument?.docIndex
      focusItems.push({
        type: 'latex_error',
        docIndex: issueDocIndex,
        tabId: activeResource?.tabId,
        fileId: focusedIssue.fileId,
        resourceId: focusedIssue.resourceId,
        resourcePath: focusedIssue.resourcePath,
        resourceName: focusedIssue.resourceName,
        line: focusedIssue.line,
        message: focusedIssue.message,
        severity: focusedIssue.severity,
        excerpt: focusedIssue.excerpt,
      })
    }

    const memoryLayers =
      activeIndexedDocument || indexedDocuments.length > 0 || focusItems.length > 0
        ? {
            activeDocument: activeIndexedDocument || undefined,
            tabIndex: indexedDocuments.length > 0 ? indexedDocuments : undefined,
            focusItems: focusItems.length > 0 ? focusItems : undefined,
          }
        : undefined

    if (!activeResource && !locationHref && !locationPathname && !pageTitle && openTabs.length === 0) {
      return null
    }

    return {
      activeTabId: activeResource?.tabId,
      selection,
      resourceId: activeResource?.resourceId,
      resourcePath: activeResource?.resourcePath,
      resourceName: activeResource?.resourceName,
      mimeType: activeResource?.mimeType,
      title: activeResource?.title,
      pluginId: activeResource?.pluginId,
      pluginName: pluginName || undefined,
      type: activeResource?.type,
      contentKind: activeSurfaceState?.contentKind,
      documentMode: activeSurfaceState?.documentMode,
      pageNumber: activeSurfaceState?.pageNumber,
      anchors,
      focusedIssue: focusedIssue || undefined,
      memoryLayers,
      pageUrl: locationHref || undefined,
      pagePath: locationPathname || undefined,
      pageTitle: pageTitle || undefined,
      openTabs: openTabs.length > 0 ? openTabs : undefined,
    }
  }, [activeResource, openTabs, workspaceTabState])

  const waitForReferenceContext = useCallback(async (referenceIds: string[], timeoutMs = 1600) => {
    if (referenceIds.length === 0) return
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
      const references = useWorkspaceSurfaceStore.getState().references
      const pending = referenceIds.some((referenceId) => {
        const reference = references[referenceId]
        return reference?.excerptStatus === 'loading'
      })
      if (!pending) return
      await new Promise((resolve) => window.setTimeout(resolve, 40))
    }
  }, [])

  const handleEventRef = useRef<((event: AgentSSEEvent) => void) | null>(null)
  const handleStreamEvent = useCallback((event: AgentSSEEvent, context: SSEEventContext) => {
    const pauseState = pauseStateRef.current
    if (pauseState && context.runId === pauseState.runId) {
      return
    }
    if (abortedRunIdRef.current != null && context.runId === abortedRunIdRef.current) {
      return
    }
    if (isRestoringRef.current) {
      restoreStreamQueueRef.current.push(event)
      return
    }
    handleEventRef.current?.(event)
  }, [])
  const { sendMessage, stop, connection, isStreaming, runId } = useSSESession({
    sessionId,
    projectId,
    onEvent: handleStreamEvent,
  })
  const streamRunIdRef = useRef(runId)
  useEffect(() => {
    streamRunIdRef.current = runId
  }, [runId])
  const isPaused = Boolean(pauseState)
  const isDisplayStreaming = Boolean(displayLockState) && !isPaused
  const isStreamActive = !isPaused && (isStreaming || isDisplayStreaming)

  const hasActiveRun = useMemo(() => {
    return messages.some((message) => {
      if (message.type === 'text_delta') {
        const content = message.content as MessageContent
        return content.role === 'assistant' && content.status === 'in_progress'
      }
      if (message.type === 'reasoning') {
        return (message.content as ReasoningContent).status === 'in_progress'
      }
      if (message.type === 'tool_call') {
        return (message.content as ToolContent).status === 'calling'
      }
      if (message.type === 'step') {
        return (message.content as StepContent).status === 'running'
      }
      return false
    })
  }, [messages])
  const externalBusy = Boolean(busyOverride)
  const isAgentBusy =
    !isPaused &&
    (externalBusy ||
      hasActiveRun ||
      Boolean(questionPrompt) ||
      Boolean(clarifyPrompt) ||
      pendingRun ||
      sessionActive)
  const showThinking = isAgentBusy && !questionPrompt && !clarifyPrompt
  const cliInputLocked = false

  useEffect(() => {
    pauseStateRef.current = pauseState
  }, [pauseState])

  useEffect(() => {
    if (!pendingRun) return
    updateStatusTodo(null)
  }, [pendingRun, updateStatusTodo])

  useEffect(() => {
    if (sessionQuiescenceReconcileTimerRef.current) {
      window.clearTimeout(sessionQuiescenceReconcileTimerRef.current)
      sessionQuiescenceReconcileTimerRef.current = null
    }
    if (!sessionId || !sessionActive) return
    if (pendingRun || questionPrompt || clarifyPrompt || hasActiveRun) return

    sessionQuiescenceReconcileTimerRef.current = window.setTimeout(() => {
      sessionQuiescenceReconcileTimerRef.current = null
      const targetSessionId = sessionIdRef.current ?? sessionId
      if (!targetSessionId) return

      void (async () => {
        try {
          const reconciled = await getSession(
            targetSessionId,
            isQuestSessionId(targetSessionId) ? { limit: 80 } : { limit: 40 }
          )
          if ((sessionIdRef.current ?? sessionId) !== targetSessionId) return

          syncRuntimeFromSession(reconciled)
          const normalizedStatus = normalizeSessionStatus(reconciled.status ?? null)
          const nextActive =
            Boolean(reconciled.is_active) || isSessionStatusRunning(normalizedStatus)

          upsertSession(targetSessionId, {
            status: normalizedStatus,
            latest_message: reconciled.latest_message ?? undefined,
            latest_message_at: reconciled.latest_message_at ?? undefined,
            updated_at:
              reconciled.updated_at ?? Math.floor(Date.now() / 1000),
            is_active: nextActive,
          })
          setSessionStatus(normalizedStatus)
          setSessionActive(nextActive)

          if (!nextActive) {
            if (isCopilotSurface) {
              setCopilotStatus(null)
            }
            updateStatusTodo(null)
            finalizeActiveMessages(normalizedStatus === 'failed' ? 'failed' : 'completed')
          }
        } catch (error) {
          debugLog('session:reconcile:error', {
            sessionId: targetSessionId,
            message: error instanceof Error ? error.message : String(error),
          })
        }
      })()
    }, 1200)

    return () => {
      if (sessionQuiescenceReconcileTimerRef.current) {
        window.clearTimeout(sessionQuiescenceReconcileTimerRef.current)
        sessionQuiescenceReconcileTimerRef.current = null
      }
    }
  }, [
    clarifyPrompt,
    debugLog,
    finalizeActiveMessages,
    hasActiveRun,
    isCopilotSurface,
    pendingRun,
    questionPrompt,
    sessionActive,
    sessionId,
    syncRuntimeFromSession,
    updateStatusTodo,
    upsertSession,
  ])


  useEffect(() => {
    if (mode !== 'welcome' || !openToolPanel) return
    toolPanelAutoOpenRef.current = true
    setToolPanelOpen(true)
    setToolPanelView('tool')
  }, [mode, openToolPanel, sessionId])

  const resolveTimelineSeq = useCallback((candidate?: number | null) => {
    if (typeof candidate === 'number' && Number.isFinite(candidate)) {
      if (candidate > timelineSeqRef.current) {
        timelineSeqRef.current = candidate
      }
      return candidate
    }
    timelineSeqRef.current += 1
    return timelineSeqRef.current
  }, [])

  const buildTextDeltaId = useCallback((eventId: string, seq: number) => {
    const base = eventId.trim() ? eventId.trim() : 'text'
    return `text-${base}-${seq}`
  }, [])

  const closeAssistantSegment = useCallback(() => {
    const lastId = lastAssistantSegmentIdRef.current
    if (!lastId) return
    const index = messagesRef.current.findIndex((item) => item.id === lastId)
    if (index < 0) {
      lastAssistantSegmentIdRef.current = null
      return
    }
    const message = messagesRef.current[index]
    if (message.type !== 'text_delta') return
    const content = message.content as MessageContent
    if (content.role !== 'assistant' || content.status !== 'in_progress') return
    const nextMessages = [...messagesRef.current]
    nextMessages[index] = {
      ...message,
      content: { ...content, status: 'completed' },
    }
    updateMessages(nextMessages)
  }, [updateMessages])

  const assignEventSequences = useCallback((events: AgentSSEEvent[]) => {
    let seq = timelineSeqRef.current
    for (const event of events) {
      const existing = getEventSequence(event)
      if (existing != null) {
        if (existing > seq) {
          seq = existing
        }
        continue
      }
      seq += 1
      const data = event.data as unknown as Record<string, unknown>
      if (data && typeof data === 'object') {
        data.seq = seq
      }
    }
    timelineSeqRef.current = seq
  }, [])

  const shouldBufferEvent = useCallback((event: AgentSSEEvent) => {
    if (restoringRef.current) return false
    const displayLock = displayLockRef.current
    if (!displayLock) return false
    if (event.event === 'error') return false
    if (BUFFER_PASSTHROUGH_EVENTS.has(event.event)) {
      return false
    }
    if (event.event === 'message') {
      return false
    }
    if (event.event === 'reasoning') {
      if (displayLock.kind !== 'reasoning') return false
      const reasoningData = event.data as Partial<ReasoningEventData>
      const reasoningId = typeof reasoningData.reasoning_id === 'string' ? reasoningData.reasoning_id : ''
      const kind = coerceReasoningKind(reasoningData.kind)
      const streamKey = buildReasoningStreamKey(reasoningId, kind, reasoningData.reasoning_stream_id)
      const messageKey = getReasoningMessageKey(streamKey)
      const message = reasoningByIdRef.current.get(messageKey)
      if (displayLock.kind === 'reasoning' && message?.id === displayLock.id) return false
      return true
    }
    if (event.event === 'tool') {
      const toolData = event.data as Partial<ToolEventData>
      const functionName = normalizeToolFunctionName(
        typeof toolData.function === 'string' ? toolData.function : ''
      )
      if (functionName === 'question_prompt' || functionName === 'clarify_question') return false
      if (displayLock.kind !== 'tool') return false
      const toolCallId = typeof toolData.tool_call_id === 'string' ? toolData.tool_call_id : ''
      let messageId = toolCallId
      if (functionName === 'mcp_status_update') {
        const eventId = typeof toolData.event_id === 'string' ? toolData.event_id : ''
        const timestamp = coerceTimestamp(toolData.timestamp)
        messageId = buildMcpStatusMessageId(eventId, toolCallId, timestamp)
      }
      if (messageId && messageId === displayLock.id) return false
      return false
    }
    return true
  }, [])

  const flushBufferedEvents = useCallback(() => {
    if (pauseStateRef.current) {
      bufferedEventsRef.current = []
      return
    }
    if (bufferedEventsRef.current.length === 0) return
    const queued = bufferedEventsRef.current
    bufferedEventsRef.current = []
    window.setTimeout(() => {
      if (pauseStateRef.current) {
        queued.length = 0
        return
      }
      const handler = handleEventRef.current
      if (!handler) return
      const drainNext = () => {
        if (queued.length === 0) return
        if (pauseStateRef.current) {
          queued.length = 0
          return
        }
        const nextEvent = queued[0]
        if (shouldBufferEvent(nextEvent)) {
          bufferedEventsRef.current = queued.concat(bufferedEventsRef.current)
          return
        }
        queued.shift()
        handler(nextEvent)
        if (queued.length > 0) {
          window.setTimeout(drainNext, 0)
        }
      }
      drainNext()
    }, 0)
  }, [shouldBufferEvent])

  const flushRestoreStreamQueue = useCallback(() => {
    if (isRestoringRef.current) return
    if (restoreStreamQueueRef.current.length === 0) return
    const handler = handleEventRef.current
    if (!handler) {
      restoreStreamQueueRef.current = []
      return
    }
    const queued = restoreStreamQueueRef.current
    restoreStreamQueueRef.current = []
    const baselineSeq = timelineSeqRef.current
    const restoredIds = restoreEventIdsRef.current
    const filtered = queued.filter((event) => {
      const data = event.data as unknown as Record<string, unknown> | undefined
      const eventId = data && typeof data.event_id === 'string' ? data.event_id : null
      if (eventId && restoredIds.has(eventId)) return false
      const seq = getEventSequence(event)
      if (baselineSeq != null && seq != null && seq <= baselineSeq) return false
      return true
    })
    if (filtered.length === 0) return
    const ordered = sortHydratedEvents(filtered)
    ordered.forEach((event) => {
      handler(event)
    })
  }, [])

  useEffect(() => {
    realTimeRef.current = realTime
  }, [realTime])

  useEffect(() => {
    if (!projectId) return
    void loadCliServers(projectId)
  }, [loadCliServers, projectId])

  useEffect(() => {
    if (!projectId || !isVisible) return
    if (typeof window === 'undefined') return

    const interval = window.setInterval(() => {
      if (document.hidden) return
      if (cliLoading) return
      if (cliStoreProjectId && cliStoreProjectId === projectId) {
        void refreshCliServers()
        return
      }
      void loadCliServers(projectId)
    }, 15000)

    return () => {
      window.clearInterval(interval)
    }
  }, [cliLoading, cliStoreProjectId, isVisible, loadCliServers, projectId, refreshCliServers])

  const refreshProjectAgents = useCallback(async () => {
    if (!projectId || refreshingAgentsRef.current) return
    refreshingAgentsRef.current = true
    try {
      const project = await getProject(projectId)
      setAgentsForProject(project.id, project.agents ?? [])
    } finally {
      refreshingAgentsRef.current = false
    }
  }, [projectId, setAgentsForProject])

  const refreshAgentsFromServer = useCallback(
    async (serverId: string) => {
      if (!projectId) return
      try {
        await refreshCliServerStatus(projectId, serverId)
      } catch {
        // Ignore refresh errors; the periodic polling will reconcile status.
      }
      if (cliStoreProjectId && cliStoreProjectId === projectId) {
        await refreshCliServers()
      } else {
        await loadCliServers(projectId)
      }
      if (typeof window !== 'undefined') {
        window.setTimeout(() => {
          void refreshProjectAgents()
        }, 700)
      } else {
        void refreshProjectAgents()
      }
    },
    [cliStoreProjectId, loadCliServers, projectId, refreshCliServers, refreshProjectAgents]
  )

  const onlineServersKey = useMemo(
    () => onlineCliServers.map((server) => server.id).sort().join('|'),
    [onlineCliServers]
  )

  useEffect(() => {
    if (!projectId) return
    if (!cliStoreProjectId || cliStoreProjectId !== projectId) return
    if (onlineServersKey === lastOnlineServersKeyRef.current) return
    lastOnlineServersKeyRef.current = onlineServersKey
    if (!onlineServersKey && !hasCliAgent) return
    void refreshProjectAgents()
  }, [cliStoreProjectId, hasCliAgent, onlineServersKey, projectId, refreshProjectAgents])

  const refreshServerId = cliServerId ?? activeCliServerId ?? null

  useEffect(() => {
    if (!projectId || !refreshServerId) return
    if (!cliStoreProjectId || cliStoreProjectId !== projectId) return
    if (lastMentionRefreshRef.current === refreshServerId) return
    lastMentionRefreshRef.current = refreshServerId
    void refreshAgentsFromServer(refreshServerId)
  }, [cliStoreProjectId, projectId, refreshAgentsFromServer, refreshServerId])

  useEffect(() => {
    if (!projectId) return
    if (!cliStoreProjectId || cliStoreProjectId !== projectId) return
    if (cliLoading) return
    const hasKnownCliServer =
      Boolean(cliServerId && cliServers.some((server) => server.id === cliServerId))
    if (
      executionTarget === 'cli' &&
      onlineCliServers.length > 0 &&
      (!cliServerId || !onlineCliServers.some((server) => server.id === cliServerId))
    ) {
      setCliServerId(projectId, onlineCliServers[0].id)
    }
    if (executionTarget === 'cli' && onlineCliServers.length === 0 && !hasKnownCliServer) {
      setExecutionTarget(projectId, 'sandbox')
    }
  }, [
    cliLoading,
    cliServerId,
    cliServers,
    cliStoreProjectId,
    executionTarget,
    onlineCliServers,
    projectId,
    setCliServerId,
    setExecutionTarget,
  ])

  const ensureSession = useCallback(async (options?: { openToolPanel?: boolean }) => {
    if (!projectId) {
      debugLog('ensure:skip', { reason: 'no_project' })
      addToast({
        type: 'error',
        title: 'No project selected',
        description: 'Open a project before starting a conversation.',
      })
      return null
    }
    if (sessionIdRef.current) {
      debugLog('ensure:reuse', { sessionId: sessionIdRef.current })
      return sessionIdRef.current
    }
    if (ensureSessionPromiseRef.current?.projectId === projectId) {
      debugLog('ensure:inflight')
      return ensureSessionPromiseRef.current.promise
    }

    const openToolPanelOnCreate = options?.openToolPanel !== false
    if (await shouldUseQuestSessionCompat(projectId)) {
      const questSessionId = buildQuestSessionId(projectId)
      debugLog('ensure:quest:adopt', { sessionId: questSessionId })
      skipRestoreRef.current = true
      setDraftSessionId(null)
      setSessionIdForSurface(projectId, sessionSurface, questSessionId)
      setLastEventId(questSessionId, null)
      upsertSession(
        questSessionId,
        {
          title: 'New Chat',
          status: 'pending',
          latest_message: null,
          latest_message_at: Math.floor(Date.now() / 1000),
          updated_at: Math.floor(Date.now() / 1000),
          is_active: false,
        },
        { forceTop: true }
      )
      triggerSessionHighlight(questSessionId)
      if (openToolPanelOnCreate) {
        setToolPanelOpen(true)
      }
      return questSessionId
    }
    debugLog('ensure:create:start')
    const createPromise = createSession(projectId)
      .then((created) => {
        const activeSessionId = sessionIdRef.current
        const shouldAdopt = !activeSessionId
        debugLog('ensure:create:done', { sessionId: created.session_id, adopted: shouldAdopt })

        if (shouldAdopt) {
          skipRestoreRef.current = true
          setDraftSessionId(null)
          setSessionIdForSurface(projectId, sessionSurface, created.session_id)
          setLastEventId(created.session_id, null)
        }

        upsertSession(
          created.session_id,
          {
            title: created.title ?? 'New Chat',
            status: normalizeSessionStatus(created.status) ?? 'pending',
            latest_message: null,
            latest_message_at: Math.floor(Date.now() / 1000),
            updated_at: Math.floor(Date.now() / 1000),
            is_active: typeof created.is_active === 'boolean' ? created.is_active : false,
          },
          { forceTop: true }
        )

        if (shouldAdopt) {
          triggerSessionHighlight(created.session_id)
          if (openToolPanelOnCreate) {
            setToolPanelOpen(true)
          }
        }

        return activeSessionId ?? created.session_id
      })
      .catch((error) => {
        debugLog('ensure:create:error', { message: error instanceof Error ? error.message : String(error) })
        addToast({
          type: 'error',
          title: 'Unable to create session',
          description: 'Please try again in a moment.',
        })
        return null
      })
      .finally(() => {
        ensureSessionPromiseRef.current = null
      })

    ensureSessionPromiseRef.current = { projectId, promise: createPromise }
    return createPromise
  }, [
    addToast,
    debugLog,
    projectId,
    setDraftSessionId,
    setLastEventId,
    setSessionIdForSurface,
    setToolPanelOpen,
    sessionSurface,
    triggerSessionHighlight,
    upsertSession,
  ])

  useEffect(() => {
    if (mode !== 'welcome' || !toolPanelEnabled || readOnlyMode) return
    if (!projectId) {
      autoEnsureKeyRef.current = null
      return
    }
    if (!toolPanelOpenValue || toolPanelView !== 'terminal') {
      autoEnsureKeyRef.current = null
      return
    }
    if (sessionId) {
      autoEnsureKeyRef.current = null
      return
    }
    const autoKey = `${projectId ?? 'project'}:${draftSessionId ?? 'draft'}`
    if (autoEnsureKeyRef.current === autoKey) return
    autoEnsureKeyRef.current = autoKey
    void ensureSession()
  }, [
    draftSessionId,
    ensureSession,
    mode,
    projectId,
    readOnlyMode,
    sessionId,
    toolPanelEnabled,
    toolPanelOpenValue,
    toolPanelView,
  ])

  function clearPauseState() {
    pauseStateRef.current = null
    setPauseState(null)
    abortedRunIdRef.current = null
    setCopilotStatus((current) => {
      if (current === 'Paused' || current === 'Cancelled') {
        return null
      }
      return current
    })
  }

  const handleSubmit = useCallback(async () => {
    const ensurePrefix = (message: string, prefix: string) => {
      const trimmedPrefix = prefix.trim()
      if (!trimmedPrefix) return message
      const normalizedPrefix = trimmedPrefix.startsWith('@') ? trimmedPrefix : `@${trimmedPrefix}`
      const trimmedMessage = (message || '').trim()
      if (!trimmedMessage) return trimmedMessage
      const normalizedLower = normalizedPrefix.toLowerCase()
      const messageLower = trimmedMessage.toLowerCase()
      if (messageLower.startsWith(normalizedLower)) {
        const remainder = trimmedMessage.slice(normalizedPrefix.length)
        if (!remainder) return normalizedPrefix
        if (/^\s/.test(remainder)) return trimmedMessage
        return `${normalizedPrefix} ${remainder}`
      }
      let remainder = trimmedMessage
      if (trimmedMessage.startsWith('@')) {
        const match = trimmedMessage.match(/^@([^\s]+)(?:\s+|$)/)
        if (match) {
          remainder = trimmedMessage.slice(match[0].length).trim()
        }
      }
      return remainder ? `${normalizedPrefix} ${remainder}` : normalizedPrefix
    }

    clearPauseState()

    const resolvedMessage = enforcedMentionPrefix
      ? ensurePrefix(inputMessage, enforcedMentionPrefix)
      : inputMessage

    const resolution = resolveAgentMention(resolvedMessage, mentionables, {
      enabled: mentionEnabled,
      defaultAgent: defaultAgentOverride,
    })
    const displayText = resolution.displayMessage.trim()
    if (debugEnabled) {
      console.info('[CopilotAudit][submit] start', {
        projectId,
        sessionId: sessionIdRef.current,
        inputLength: inputMessage.length,
        displayLength: displayText.length,
        readOnlyMode,
        isRestoring: isRestoringRef.current,
        pendingRun,
      })
    }
    if (!displayText || readOnlyMode) return
    const agentMessage = resolution.agentMessage.trim()
    if (resolution.matched && !agentMessage) {
      addToast({
        type: 'warning',
        title: 'Add a message',
        description: 'Provide a message after the agent mention.',
      })
      return
    }
    const sendText = resolution.matched ? agentMessage : displayText
    const label = resolution.agent.label?.trim()
    const agentLabel = label ? (label.startsWith('@') ? label : `@${label}`) : `@${resolution.agent.id}`
    const agentMetadata: Record<string, unknown> = {
      agent_id: resolution.agent.id,
      agent_label: agentLabel,
      agent_role: resolution.agent.role ?? resolution.agent.id,
      agent_source: resolution.agent.source ?? 'backend',
    }
    if (resolution.agent.agent_engine) {
      agentMetadata.agent_engine = resolution.agent.agent_engine
    }
    const mergedMetadata = messageMetadata
      ? { ...agentMetadata, ...messageMetadata }
      : agentMetadata
    const metadataWithRecentFiles =
      recentFilesEnabled && recentFilesPrompt
        ? { ...mergedMetadata, recent_files_prompt: recentFilesPrompt }
        : mergedMetadata
    const agentTarget =
      typeof resolution.agent.execution_target === 'string'
        ? resolution.agent.execution_target.toLowerCase()
        : ''
    let resolvedExecutionTarget = agentTarget === 'cli' ? 'cli' : executionTarget
    let resolvedCliServerId =
      resolvedExecutionTarget === 'cli'
        ? cliServerId ?? onlineCliServers[0]?.id ?? null
        : null
    if (resolvedExecutionTarget === 'cli' && !resolvedCliServerId) {
      addToast({
        type: 'warning',
        title: 'CLI unavailable',
        description: 'No online CLI server is available for this agent.',
      })
      if (projectId && !labRuntimeLocked) {
        resolvedExecutionTarget = 'sandbox'
        resolvedCliServerId = null
        setExecutionTarget(projectId, 'sandbox')
      } else {
        return
      }
    }
    if (resolvedExecutionTarget === 'cli' && projectId && executionTarget !== 'cli') {
      setExecutionTarget(projectId, 'cli', resolvedCliServerId ?? undefined)
    }

    if (introEnabled && welcomeIntroState === 'center') {
      if (introTimerRef.current) {
        window.clearTimeout(introTimerRef.current)
        introTimerRef.current = null
      }
      if (prefersReducedMotion) {
        setWelcomeIntroState('done')
      } else {
        setWelcomeIntroState('dropping')
        introTimerRef.current = window.setTimeout(() => {
          setWelcomeIntroState('done')
          introTimerRef.current = null
        }, 520)
      }
    }

    setPendingRun(true)
    setSessionActive(true)
    const resolvedSessionId = await ensureSession()
    if (debugEnabled) {
      console.info('[CopilotAudit][submit] ensureSession resolved', {
        projectId,
        requestedSessionId: sessionIdRef.current,
        resolvedSessionId,
      })
    }
    if (!resolvedSessionId) {
      setPendingRun(false)
      setSessionActive(false)
      return
    }

    const preparedAttachments = normalizeAttachments(attachments, resolvedSessionId).filter(
      (file) => file.status === 'success'
    )
    const now = Math.floor(Date.now() / 1000)

    upsertSession(resolvedSessionId, {
      latest_message: displayText,
      latest_message_at: now,
      updated_at: now,
      status: 'running',
      is_active: true,
    })

    pendingUserRef.current = {
      content: sendText,
      attachments: preparedAttachments,
    }

    const userSeq = resolveTimelineSeq()
    appendMessage({
      id: createMessageId('user'),
      type: 'user',
      seq: userSeq,
      ts: now,
      content: {
        content: displayText,
        timestamp: now,
        role: 'user',
        metadata: metadataWithRecentFiles,
      },
    })

    if (preparedAttachments.length > 0) {
      const attachmentSeq = resolveTimelineSeq()
      appendMessage({
        id: createMessageId('attachments'),
        type: 'attachments',
        seq: attachmentSeq,
        ts: now,
        content: {
          role: 'user',
          attachments: preparedAttachments,
          timestamp: now,
        },
      })
    }

    onUserSubmit?.(sendText)

    setInputMessage('')
    setAttachments([])
    setRecentFilesEnabled(false)

    const activeTabIdForContext = activeResource?.tabId
    const pendingReferenceIds =
      activeTabIdForContext != null
        ? (useWorkspaceSurfaceStore.getState().referencesByTabId[activeTabIdForContext] || []).filter(
            (referenceId) =>
              useWorkspaceSurfaceStore.getState().references[referenceId]?.excerptStatus === 'loading'
          )
        : []
    if (pendingReferenceIds.length > 0) {
      await waitForReferenceContext(pendingReferenceIds)
    }

    const contextSnapshot = buildContext()
    const payloadMetadata = contextSnapshot
      ? { context: contextSnapshot, ...metadataWithRecentFiles }
      : metadataWithRecentFiles
    try {
      if (debugEnabled) {
        console.info('[CopilotAudit][submit] sendMessage', {
          projectId,
          sessionId: resolvedSessionId,
          messageLength: sendText.length,
          attachmentCount: preparedAttachments.length,
        })
      }
      await sendMessage({
        sessionId: resolvedSessionId,
        message: sendText,
        attachments: preparedAttachments,
        recentFiles: recentFilesEnabled ? recentFiles : undefined,
        surface: sessionSurface,
        executionTarget: resolvedExecutionTarget,
        cliServerId: resolvedCliServerId,
        metadata: payloadMetadata,
      })
    } catch (error) {
      setPendingRun(false)
      setSessionActive(false)
      const message =
        error instanceof Error && error.message
          ? error.message
          : 'Unable to send message. Please try again.'
      const insufficient = /insufficient points|required:\s*\d+/i.test(message)
      addToast({
        type: 'error',
        title: insufficient ? 'Insufficient points' : 'Message failed',
        description: message,
      })
    }
  }, [
    addToast,
    appendMessage,
    attachments,
    buildContext,
    clearPauseState,
    cliServerId,
    ensureSession,
    executionTarget,
    inputMessage,
    enforcedMentionPrefix,
    mentionables,
    mentionEnabled,
    defaultAgentOverride,
    messageMetadata,
    onlineCliServers,
    projectId,
    sessionSurface,
    prefersReducedMotion,
    readOnlyMode,
    recentFiles,
    recentFilesEnabled,
    recentFilesPrompt,
    resolveTimelineSeq,
    onUserSubmit,
    setPendingRun,
    setExecutionTarget,
    setWelcomeIntroState,
    sendMessage,
    upsertSession,
    introEnabled,
    activeResource?.tabId,
    waitForReferenceContext,
    welcomeIntroState,
  ])

  const handleStop = async () => {
    const targetSessionId = sessionId ?? sessionIdRef.current
    if (!targetSessionId) return
    setPendingRun(false)
    setSessionActive(false)
    const activeRunId = runId > 0 ? runId : streamRunIdRef.current
    stop(targetSessionId)
    pauseActiveStream('paused', activeRunId)
    upsertSession(targetSessionId, {
      status: 'waiting',
      updated_at: Math.floor(Date.now() / 1000),
      is_active: false,
    })
    try {
      await stopSession(targetSessionId)
    } catch (error) {
      console.warn('[AiManus] stopSession failed', error)
    }
  }

  const handleResume = useCallback(async () => {
    const targetSessionId = sessionId ?? sessionIdRef.current
    if (!targetSessionId || readOnlyMode) return
    clearPauseState()
    setPendingRun(true)
    setSessionActive(true)
    upsertSession(targetSessionId, { is_active: true })
    try {
      await sendMessage({
        sessionId: targetSessionId,
        message: '',
        surface: sessionSurface,
        executionTarget,
        cliServerId,
        replayFromLastEvent: true,
      })
    } catch (error) {
      setPendingRun(false)
      setSessionActive(false)
      addToast({
        type: 'error',
        title: 'Resume failed',
        description: 'Unable to resume the session. Please try again.',
      })
    }
  }, [
    addToast,
    clearPauseState,
    cliServerId,
    executionTarget,
    readOnlyMode,
    sendMessage,
    sessionId,
    sessionSurface,
    upsertSession,
  ])

  const handleSessionSelect = useCallback(
    (nextId: string) => {
      if (!projectId) return
      if (draftSessionId && nextId === draftSessionId) return
      manualSessionSelectionRef.current = true
      const selected = sessionsRef.current.find((item) => item.session_id === nextId)
      if (selected) {
        syncRuntimeFromSession(selected)
      }
      setDraftSessionId(null)
      setSessionIdForSurface(projectId, sessionSurface, nextId)
    },
    [draftSessionId, projectId, sessionSurface, setDraftSessionId, setSessionIdForSurface, syncRuntimeFromSession]
  )

  const handleSessionTogglePin = useCallback((targetId: string) => {
    setSessionPreferences((current) => {
      const isPinned = current.pinned.includes(targetId)
      const nextPinned = isPinned
        ? current.pinned.filter((id) => id !== targetId)
        : [targetId, ...current.pinned.filter((id) => id !== targetId)]
      return {
        ...current,
        pinned: nextPinned,
      }
    })
  }, [])

  const openRenameDialog = useCallback(
    (targetId: string) => {
      const session = sessionsRef.current.find((item) => item.session_id === targetId)
      const currentTitle = resolveSessionTitle(session ?? null, targetId)
      setRenameTargetId(targetId)
      setRenameDraft(currentTitle)
      setRenameDialogOpen(true)
    },
    [resolveSessionTitle]
  )

  const closeRenameDialog = useCallback(() => {
    setRenameDialogOpen(false)
    setRenameTargetId(null)
    setRenameDraft('')
  }, [])

  const commitRenameDialog = useCallback(() => {
    if (!renameTargetId) return
    const trimmed = renameDraft.trim()
    const session = sessionsRef.current.find((item) => item.session_id === renameTargetId)
    setSessionPreferences((current) => {
      const nextRenamed = { ...current.renamed }
      if (trimmed) {
        nextRenamed[renameTargetId] = trimmed
      } else {
        delete nextRenamed[renameTargetId]
      }
      return {
        ...current,
        renamed: nextRenamed,
      }
    })
    if (sessionIdRef.current === renameTargetId) {
      const fallbackTitle =
        typeof session?.title === 'string' && session.title.trim() ? session.title.trim() : 'New Chat'
      setTitle(trimmed || fallbackTitle)
    }
    closeRenameDialog()
  }, [closeRenameDialog, renameDraft, renameTargetId])

  const handleSessionRename = useCallback(
    (targetId: string) => {
      openRenameDialog(targetId)
    },
    [openRenameDialog]
  )

  const buildSessionShareUrl = useCallback(
    (targetId: string) => {
      if (!projectId || typeof window === 'undefined') return ''
      const url = new URL(window.location.origin)
      url.pathname = `/projects/${projectId}`
      url.searchParams.set('copilotSession', targetId)
      return url.toString()
    },
    [projectId]
  )

  const handleSessionShare = useCallback(
    async (targetId: string) => {
      const url = buildSessionShareUrl(targetId)
      if (!url) return
      const ok = await copyToClipboard(url)
      addToast({
        type: ok ? 'success' : 'error',
        title: ok ? 'Link copied' : 'Unable to copy link',
        description: ok ? 'Share this session with teammates.' : 'Please try again.',
      })
    },
    [addToast, buildSessionShareUrl]
  )

  const handleSessionDelete = useCallback(
    async (targetId: string) => {
      if (!projectId || readOnlyMode) return
      if (draftSessionId && targetId === draftSessionId) {
        setDraftSessionId(null)
        resetConversation()
        return
      }
      const confirmDelete = window.confirm('Delete this session? This cannot be undone.')
      if (!confirmDelete) return
      try {
        await deleteSession(targetId)
        setSessions((current) => current.filter((item) => item.session_id !== targetId))
        setSessionPreferences((current) => {
          const { [targetId]: _removed, ...nextRenamed } = current.renamed
          return {
            ...current,
            pinned: current.pinned.filter((id) => id !== targetId),
            renamed: nextRenamed,
          }
        })
        if (sessionId === targetId) {
          clearSessionIdForSurface(projectId, sessionSurface)
          setLastEventId(targetId, null)
          resetConversation()
        }
      } catch (error) {
        addToast({
          type: 'error',
          title: 'Unable to delete session',
          description: 'Please try again in a moment.',
        })
      }
    },
    [
      addToast,
      clearSessionIdForSurface,
      draftSessionId,
      projectId,
      readOnlyMode,
      resetConversation,
      sessionSurface,
      sessionId,
      setLastEventId,
      setDraftSessionId,
      setSessions,
    ]
  )

  useEffect(() => {
    if (!COPILOT_FILES_ENABLED) return
    if (!fileListOpen || !sessionId) return
    let active = true
    setSessionFilesLoading(true)
    getSessionFiles(sessionId)
      .then((files) => {
        if (!active) return
        setSessionFiles(files)
      })
      .catch(() => {
        if (!active) return
        addToast({
          type: 'error',
          title: 'Unable to load session files',
          description: 'Please try again later.',
        })
      })
      .finally(() => {
        if (active) {
          setSessionFilesLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [addToast, fileListOpen, sessionId])

  const lastMetaRef = useRef<AiManusChatMeta | null>(null)
  const syncMeta = useCallback(() => {
    const meta: AiManusChatMeta = {
      threadId: sessionId ?? null,
      historyOpen: historyOpenValue,
      isResponding: isAgentBusy,
      toolCount: toolCallCount,
      ready: Boolean(sessionId),
      isRestoring,
      restoreAttempted,
      hasHistory,
      error: connection.error ?? null,
      title,
      statusText: statusTodoText,
      statusPrevText: statusTodoPrev,
      statusKey: statusTodoKey,
      toolPanelVisible,
      toolToggleVisible,
      fixWithAiRunning,
    }
    const prev = lastMetaRef.current
    if (
      prev &&
      prev.threadId === meta.threadId &&
      prev.historyOpen === meta.historyOpen &&
      prev.isResponding === meta.isResponding &&
      prev.toolCount === meta.toolCount &&
      prev.ready === meta.ready &&
      prev.isRestoring === meta.isRestoring &&
      prev.restoreAttempted === meta.restoreAttempted &&
      prev.hasHistory === meta.hasHistory &&
      prev.error === meta.error &&
      prev.title === meta.title &&
      prev.statusText === meta.statusText &&
      prev.statusPrevText === meta.statusPrevText &&
      prev.statusKey === meta.statusKey &&
      prev.toolPanelVisible === meta.toolPanelVisible &&
      prev.toolToggleVisible === meta.toolToggleVisible &&
      prev.attachmentsDrawerOpen === meta.attachmentsDrawerOpen &&
      prev.fixWithAiRunning === meta.fixWithAiRunning
    ) {
      return
    }
    lastMetaRef.current = meta
    onMetaChange?.(meta)
  }, [
    connection.error,
    fixWithAiRunning,
    historyOpenValue,
    hasHistory,
    isAgentBusy,
    isRestoring,
    onMetaChange,
    restoreAttempted,
    sessionId,
    statusTodoKey,
    statusTodoPrev,
    statusTodoText,
    title,
    toolPanelVisible,
    toolToggleVisible,
  ])

  useEffect(() => {
    syncMeta()
  }, [syncMeta])

  const actionsStateRef = useRef({
    historyPanelEnabled,
    historyOpenValue,
    toolPanelEnabled,
    toolPanelOpenValue,
    mode,
    projectId,
    sessionSurface,
    activeTool,
  })
  const startDisplayLockRef = useRef<(id: string, kind: DisplayLockKind) => void>(() => {})
  const runFixWithAiRef = useRef<
    (payload: {
      folderId: string
      buildId?: string | null
      focusedError?: CopilotFocusedIssue | null
      promptText?: string | null
    }) => Promise<void>
  >(async () => {})
  type ActionsFns = {
    setHistoryOpenValue: (next: boolean) => void
    startNewSession: () => void
    clearSessionIdForSurface: (projectId: string, surface: ChatSurface) => void
    resetConversation: (options?: { title?: string }) => void
    setSessionIdForSurface: (projectId: string, surface: ChatSurface, sessionId: string) => void
    setDraftSessionId: (id: string | null) => void
    focusComposer: () => void
    setInputMessage: (text: string) => void
    handleSubmit: () => Promise<void> | void
    ensureSession: (options?: { openToolPanel?: boolean }) => Promise<string | null>
    setToolPanelView: (view: 'tool' | 'terminal') => void
    setToolPanelOpen: (open: boolean) => void
    setActiveTool: (tool: ToolContent | null) => void
    setToolPanelLive: (live: boolean) => void
    runFixWithAi: (payload: {
      folderId: string
      buildId?: string | null
      focusedError?: CopilotFocusedIssue | null
      promptText?: string | null
    }) => Promise<void>
  }

  const actionsFnsRef = useRef<ActionsFns>({
    setHistoryOpenValue: () => {},
    startNewSession: () => {},
    clearSessionIdForSurface: () => {},
    resetConversation: () => {},
    setSessionIdForSurface: () => {},
    setDraftSessionId: () => {},
    focusComposer: () => {},
    setInputMessage: () => {},
    handleSubmit: () => {},
    ensureSession: async () => null,
    setToolPanelView: () => {},
    setToolPanelOpen: () => {},
    setActiveTool: () => {},
    setToolPanelLive: () => {},
    runFixWithAi: (payload: {
      folderId: string
      buildId?: string | null
      focusedError?: CopilotFocusedIssue | null
      promptText?: string | null
    }) =>
      runFixWithAiRef.current(payload),
  })
  useEffect(() => {
    actionsStateRef.current = {
      historyPanelEnabled,
      historyOpenValue,
      toolPanelEnabled,
      toolPanelOpenValue,
      mode,
      projectId,
      sessionSurface,
      activeTool,
    }
  }, [
    activeTool,
    historyOpenValue,
    historyPanelEnabled,
    mode,
    projectId,
    sessionSurface,
    toolPanelEnabled,
    toolPanelOpenValue,
  ])
  useEffect(() => {
    actionsFnsRef.current = {
      setHistoryOpenValue,
      startNewSession,
      clearSessionIdForSurface,
      resetConversation,
      setSessionIdForSurface,
      setDraftSessionId,
      focusComposer,
      setInputMessage,
      handleSubmit,
      ensureSession,
      setToolPanelView,
      setToolPanelOpen,
      setActiveTool,
      setToolPanelLive,
      runFixWithAi: (payload: {
        folderId: string
        buildId?: string | null
        focusedError?: CopilotFocusedIssue | null
        promptText?: string | null
      }) =>
        runFixWithAiRef.current(payload),
    }
  }, [
    clearSessionIdForSurface,
    ensureSession,
    focusComposer,
    handleSubmit,
    resetConversation,
    setActiveTool,
    setDraftSessionId,
    setHistoryOpenValue,
    setInputMessage,
    setSessionIdForSurface,
    setToolPanelLive,
    setToolPanelOpen,
    setToolPanelView,
    startNewSession,
  ])
  const actionsRef = useRef<AiManusChatActions | null>(null)
  if (!actionsRef.current) {
    actionsRef.current = {
      toggleHistory: () => {
        const { historyPanelEnabled, historyOpenValue } = actionsStateRef.current
        if (!historyPanelEnabled) return
        actionsFnsRef.current.setHistoryOpenValue(!historyOpenValue)
      },
      startNewThread: () => {
        actionsFnsRef.current.startNewSession()
      },
      setThreadId: (threadId) => {
        const { projectId, sessionSurface } = actionsStateRef.current
        if (!projectId) return
        actionsFnsRef.current.setDraftSessionId(null)
        if (!threadId) {
          actionsFnsRef.current.clearSessionIdForSurface(projectId, sessionSurface)
          actionsFnsRef.current.resetConversation()
          return
        }
        actionsFnsRef.current.setSessionIdForSurface(projectId, sessionSurface, threadId)
      },
      clearThread: () => {
        actionsFnsRef.current.resetConversation()
      },
      focusComposer: () => {
        actionsFnsRef.current.focusComposer()
      },
      setComposerValue: (text, focus = false) => {
        actionsFnsRef.current.setInputMessage(text)
        if (focus) {
          window.setTimeout(() => actionsFnsRef.current.focusComposer(), 0)
        }
      },
      submitComposer: () => {
        actionsFnsRef.current.handleSubmit()
      },
      runFixWithAi: (payload) => {
        actionsFnsRef.current.runFixWithAi(payload)
      },
      openToolPanel: () => {
        const { mode, toolPanelEnabled, activeTool } = actionsStateRef.current
        if (mode !== 'welcome' || !toolPanelEnabled) return
        if (activeTool) {
          actionsFnsRef.current.setToolPanelView('tool')
          actionsFnsRef.current.setToolPanelOpen(true)
          return
        }
        const lastTool = lastNoMessageToolRef.current
        if (lastTool) {
          actionsFnsRef.current.setActiveTool(lastTool)
          actionsFnsRef.current.setToolPanelLive(lastTool.status === 'calling')
          actionsFnsRef.current.setToolPanelView('tool')
          actionsFnsRef.current.setToolPanelOpen(true)
          return
        }
        const openTerminal = async () => {
          const resolvedSessionId = await actionsFnsRef.current.ensureSession()
          if (!resolvedSessionId) return
          actionsFnsRef.current.setToolPanelView('terminal')
          actionsFnsRef.current.setToolPanelOpen(true)
        }
        void openTerminal()
      },
      toggleToolPanel: () => {
        const { mode, toolPanelEnabled, toolPanelOpenValue, activeTool } = actionsStateRef.current
        if (mode !== 'welcome' || !toolPanelEnabled) return
        if (toolPanelOpenValue) {
          actionsFnsRef.current.setToolPanelOpen(false)
          return
        }
        if (activeTool) {
          actionsFnsRef.current.setToolPanelView('tool')
          actionsFnsRef.current.setToolPanelOpen(true)
          return
        }
        const lastTool = lastNoMessageToolRef.current
        if (lastTool) {
          actionsFnsRef.current.setActiveTool(lastTool)
          actionsFnsRef.current.setToolPanelLive(lastTool.status === 'calling')
          actionsFnsRef.current.setToolPanelView('tool')
          actionsFnsRef.current.setToolPanelOpen(true)
          return
        }
        const openTerminal = async () => {
          const resolvedSessionId = await actionsFnsRef.current.ensureSession()
          if (!resolvedSessionId) return
          actionsFnsRef.current.setToolPanelView('terminal')
          actionsFnsRef.current.setToolPanelOpen(true)
        }
        void openTerminal()
      },
    }
  }
  useEffect(() => {
    if (!onActionsChange) return
    onActionsChange(actionsRef.current)
    return () => {
      onActionsChange(null)
    }
  }, [onActionsChange])

  useEffect(() => {
    if (!prefill) return
    setInputMessage(ensureLeadingMentionSpace(prefill.text))
    if (prefill.focus) {
      window.setTimeout(() => focusComposer(), 0)
    }
  }, [ensureLeadingMentionSpace, focusComposer, prefill])

  useEffect(() => {
    if (toolPanelEnabled) return
    setToolPanelLive(false)
  }, [toolPanelEnabled])

  const isLastNoMessageTool = useCallback((tool: ToolContent) => {
    return tool.tool_call_id === lastNoMessageToolRef.current?.tool_call_id
  }, [])

  const canAutoOpenToolPanel = useCallback((tool: ToolContent) => {
    if (isPushFileTool(tool)) return false
    const category = resolveToolCategory(tool)
    return category === 'shell' || category === 'bash' || category === 'search' || category === 'file'
  }, [])

  const isLiveTool = useCallback(
    (tool: ToolContent) => {
      if (tool.status === 'calling') return true
      if (!isLastNoMessageTool(tool)) return false
      const timestampMs = normalizeTimestampMs(tool.timestamp)
      if (!timestampMs) return false
      return timestampMs > Date.now() - 5 * 60 * 1000
    },
    [isLastNoMessageTool]
  )

  const handleToolPanelOpen = useCallback(
    (tool: ToolContent, live: boolean, forceOpen = false) => {
      setActiveTool(tool)
      setToolPanelLive(live)
      setToolPanelView('tool')
      if (!toolPanelEnabled) return
      if (forceOpen) {
        setToolPanelOpen(true)
      }
    },
    [toolPanelEnabled, setToolPanelView]
  )

  useEffect(() => {
    if (mode !== 'welcome' || !openToolPanel) return
    if (!toolPanelAutoOpenRef.current) return
    if (restoringRef.current) return
    const lastTool = lastNoMessageToolRef.current
    if (lastTool) {
      if (canAutoOpenToolPanel(lastTool)) {
        handleToolPanelOpen(lastTool, isLiveTool(lastTool), true)
      }
      toolPanelAutoOpenRef.current = false
      return
    }
    const openTerminal = async () => {
      const resolvedSessionId =
        sessionId ?? (await ensureSession({ openToolPanel: mode !== 'welcome' }))
      if (!resolvedSessionId) return
      setToolPanelView('terminal')
      setToolPanelOpen(true)
    }
    void openTerminal()
    toolPanelAutoOpenRef.current = false
  }, [canAutoOpenToolPanel, ensureSession, handleToolPanelOpen, isLiveTool, mode, openToolPanel, sessionId])

  const collapseActiveReasoning = useCallback(() => {
    if (isCopilotSurface) return
    const active = lastReasoningRef.current
    if (!active || active.collapsed) return
    const index = messagesRef.current.findIndex(
      (item) => item.type === 'reasoning' && item.content === active
    )
    if (index < 0) return
    const message = messagesRef.current[index]
    const nextContent: ReasoningContent = { ...active, collapsed: true }
    const nextMessage: ChatMessageItem = { ...message, content: nextContent }
    replaceReasoningMessage(nextMessage)
    lastReasoningRef.current = nextContent
  }, [isCopilotSurface, replaceReasoningMessage])

  const handleQuestionSubmit = useCallback(
    async (toolCallId: string, answers: QuestionPromptAnswerMap) => {
      if (!sessionId) {
        addToast({
          type: 'error',
          title: 'Session unavailable',
          description: 'Unable to submit answers. Please try again.',
        })
        return
      }
      const timestamp = Math.floor(Date.now() / 1000)
      setPendingRun(true)
      setSessionActive(true)
      upsertSession(sessionId, { status: 'running', updated_at: timestamp, is_active: true })
      try {
        const response = await submitToolOutput(sessionId, toolCallId, { answers })
        const queued = Boolean((response as { queued?: boolean } | undefined)?.queued)
        const messageId = `question_prompt-${toolCallId}`
        const existingIndex = messagesRef.current.findIndex((item) => item.id === messageId)
        if (existingIndex >= 0) {
          const nextMessages = [...messagesRef.current]
          const existing = nextMessages[existingIndex]
          if (existing.type === 'question_prompt') {
            nextMessages[existingIndex] = {
              ...existing,
              content: {
                ...(existing.content as QuestionPromptContent),
                status: 'called',
                answers,
              },
            }
            updateMessages(nextMessages)
          }
        }
        setQuestionPrompt(null)
        questionPromptRef.current = null
        if (isCopilotSurface) {
          setCopilotStatus(null)
        }
        if (queued) {
          addToast({
            type: 'info',
            title: 'Answer saved',
            description: 'Agent is offline. Your answer will be delivered once it reconnects.',
          })
        }
      } catch (error) {
        setPendingRun(false)
        setSessionActive(false)
        upsertSession(sessionId, { is_active: false })
        addToast({
          type: 'error',
          title: 'Failed to submit answers',
          description: 'Please try again.',
        })
      }
    },
    [addToast, isCopilotSurface, sessionId, updateMessages, upsertSession]
  )

  const handleClarifySubmit = useCallback(
    async (toolCallId: string | undefined, selections: string[]) => {
      if (!sessionId || !toolCallId) {
        addToast({
          type: 'error',
          title: 'Session unavailable',
          description: 'Unable to submit answers. Please try again.',
        })
        return
      }
      const timestamp = Math.floor(Date.now() / 1000)
      const normalizedSelections = selections.map((item) => String(item).trim()).filter(Boolean)
      setPendingRun(true)
      setSessionActive(true)
      upsertSession(sessionId, { status: 'running', updated_at: timestamp, is_active: true })
      try {
        const response = await submitClarifySelection(sessionId, toolCallId, normalizedSelections)
        const messageId = `clarify_question-${toolCallId}`
        const existingIndex = messagesRef.current.findIndex((item) => {
          if (item.id === messageId) return true
          if (item.type !== 'clarify_question') return false
          return (item.content as ClarifyQuestionContent).toolCallId === toolCallId
        })
        if (existingIndex >= 0) {
          const nextMessages = [...messagesRef.current]
          const existing = nextMessages[existingIndex]
          if (existing.type === 'clarify_question') {
            nextMessages[existingIndex] = {
              ...existing,
              content: {
                ...(existing.content as ClarifyQuestionContent),
                status: 'answered',
                selections: normalizedSelections,
                selectedLabels: response?.selected ?? [],
              },
            }
            updateMessages(nextMessages)
          }
        }
        setClarifyPrompt(null)
        clarifyPromptRef.current = null
        if (isCopilotSurface) {
          setCopilotStatus(null)
        }
      } catch (error) {
        setPendingRun(false)
        setSessionActive(false)
        upsertSession(sessionId, { is_active: false })
        addToast({
          type: 'error',
          title: 'Failed to submit answers',
          description: 'Please try again.',
        })
      }
    },
    [addToast, isCopilotSurface, sessionId, updateMessages, upsertSession]
  )

  const appendTimelineStatus = useCallback(
    (content: string) => {
      const timestamp = Math.floor(Date.now() / 1000)
      appendMessage({
        id: createMessageId('status'),
        type: 'status',
        seq: resolveTimelineSeq(),
        ts: timestamp,
        content: {
          content,
          timestamp,
        } as StatusContent,
      })
    },
    [appendMessage, resolveTimelineSeq]
  )

  const upsertToolMessage = useCallback(
    (toolCallId: string, toolContent: ToolContent) => {
      const existingIndex = messagesRef.current.findIndex((item) => {
        if (item.type !== 'tool') return false
        const existing = item.content as ToolContent
        return existing.tool_call_id === toolCallId
      })
      const existing = existingIndex >= 0 ? messagesRef.current[existingIndex] : null
      const seq =
        existing && typeof existing.seq === 'number' ? existing.seq : resolveTimelineSeq()
      const ts =
        existing && typeof existing.ts === 'number'
          ? existing.ts
          : toolContent.timestamp ?? Math.floor(Date.now() / 1000)
      const message: ChatMessageItem = {
        id: toolCallId || createMessageId('tool'),
        type: 'tool',
        seq,
        ts,
        content: toolContent,
      }
      if (existingIndex >= 0) {
        const nextMessages = [...messagesRef.current]
        nextMessages[existingIndex] = message
        updateMessages(nextMessages)
      } else {
        appendMessage(message)
      }
      lastToolRef.current = toolContent
      if (toolContent.name !== 'message') {
        lastNoMessageToolRef.current = toolContent
      }
    },
    [appendMessage, resolveTimelineSeq, updateMessages]
  )

  const handleFixWithAi = useCallback(
    async (payload: {
      folderId: string
      buildId?: string | null
      focusedError?: CopilotFocusedIssue | null
      promptText?: string | null
    }) => {
      const folderId = payload?.folderId?.trim()
      if (!projectId) {
        addToast({
          type: 'error',
          title: t('fix_with_ai_project_unavailable_title'),
          description: t('fix_with_ai_project_unavailable_desc'),
        })
        return
      }
      if (!folderId) {
        addToast({
          type: 'warning',
          title: t('fix_with_ai_open_latex_title'),
          description: t('fix_with_ai_open_latex_desc'),
        })
        return
      }
      if (readOnlyMode) return
      if (fixWithAiRunningRef.current) return

      fixWithAiRunningRef.current = true
      setFixWithAiRunning(true)

      const resolvedSessionId = await ensureSession()
      if (!resolvedSessionId) {
        fixWithAiRunningRef.current = false
        setFixWithAiRunning(false)
        addToast({
          type: 'error',
          title: t('fix_with_ai_session_unavailable_title'),
          description: t('fix_with_ai_session_unavailable_desc'),
        })
        return
      }

      const toolCallId = `fix-with-ai-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const timestamp = Math.floor(Date.now() / 1000)
      const baseArgs: Record<string, unknown> = {
        project_id: projectId,
        folder_id: folderId,
      }
      const workspaceSurfaceState = useWorkspaceSurfaceStore.getState()
      const focusedErrorFromStore =
        activeResource?.tabId != null ? workspaceSurfaceState.activeIssueByTabId[activeResource.tabId] : null
      const focusedError =
        payload.focusedError && payload.focusedError.kind === 'latex_error'
          ? payload.focusedError
          : focusedErrorFromStore?.kind === 'latex_error'
            ? {
                kind: focusedErrorFromStore.kind,
                tabId: focusedErrorFromStore.tabId,
                fileId: focusedErrorFromStore.fileId,
                resourceId: focusedErrorFromStore.resourceId,
                resourcePath: focusedErrorFromStore.resourcePath,
                resourceName: focusedErrorFromStore.resourceName,
                line: focusedErrorFromStore.line,
                message: focusedErrorFromStore.message,
                severity: focusedErrorFromStore.severity,
                excerpt: focusedErrorFromStore.excerpt,
              }
            : null
      const defaultPromptText = focusedError
        ? `Fix the current LaTeX ${focusedError.severity} in ${
            focusedError.resourceName || focusedError.resourcePath || 'the active document'
          }${focusedError.line ? `:${focusedError.line}` : ''}. Focused issue: ${focusedError.message}`
        : 'Fix the current LaTeX compile issues in the active project with the smallest safe patch.'
      let resolvedBuildId = payload.buildId ?? null
      let resolvedLogItems: LatexBuildError[] = []
      let resolvedLogText: string | null = null
      if (!resolvedBuildId) {
        try {
          const builds = await listLatexBuilds(projectId, folderId, 1)
          const latest = builds?.[0]
          if (latest?.build_id) {
            resolvedBuildId = latest.build_id
            if (Array.isArray(latest.errors) && latest.errors.length > 0) {
              resolvedLogItems = latest.errors.map((item) => ({
                path: item.path ?? null,
                line: typeof item.line === 'number' ? item.line : null,
                message: item.message,
                severity: item.severity === 'warning' ? 'warning' : 'error',
              }))
            } else if (latest.log_ready) {
              try {
                resolvedLogText = await getLatexBuildLogText(projectId, folderId, latest.build_id)
              } catch (error) {
                console.warn('[CopilotAudit][fix-with-ai] Failed to load LaTeX log text', error)
              }
            }
          }
        } catch (error) {
          console.warn('[CopilotAudit][fix-with-ai] Failed to load latest LaTeX build', error)
        }
      }
      if (resolvedBuildId) {
        baseArgs.build_id = resolvedBuildId
      }
      if (focusedError) {
        baseArgs.focused_error = focusedError
      }
      if (resolvedLogItems.length > 0) {
        baseArgs.log_items = resolvedLogItems
      } else if (resolvedLogText) {
        baseArgs.log_text = resolvedLogText
      }
      const contextSnapshot = buildContext()
      const repairMode = focusedError ? 'focused_error' : 'compile_log'
      const metadata = contextSnapshot
        ? {
            context: contextSnapshot,
            task_intent: 'latex_fix',
            repair_mode: repairMode,
          }
        : {
            task_intent: 'latex_fix',
            repair_mode: repairMode,
          }
      const baseToolContent: ToolContent = {
        event_id: toolCallId || createMessageId('tool'),
        tool_call_id: toolCallId,
        name: 'copilot_fix_with_ai',
        status: 'calling',
        function: 'fix_with_ai',
        args: baseArgs,
        timestamp,
      }
      upsertToolMessage(toolCallId, baseToolContent)
      startDisplayLockRef.current(toolCallId, 'tool')

      try {
        const events = await runCopilotFixWithAi(projectId, {
          folder_id: folderId,
          ...(resolvedBuildId ? { build_id: resolvedBuildId } : {}),
          ...(resolvedLogItems.length > 0 ? { log_items: resolvedLogItems } : {}),
          ...(resolvedLogItems.length === 0 && resolvedLogText ? { log_text: resolvedLogText } : {}),
          ...(focusedError ? { focused_error: focusedError } : {}),
          message: payload.promptText?.trim() || defaultPromptText,
          metadata,
          recent_files: recentFiles,
        })
        const timelineEvents = Array.isArray(events) ? events : []
        if (timelineEvents.length === 0) {
          upsertToolMessage(toolCallId, {
            ...baseToolContent,
            status: 'called',
            error: 'no_timeline_events',
          })
          appendTimelineStatus('Fix with AI returned no patch.')
          return
        }

        let toolUpdated = false
        timelineEvents.forEach((event) => {
          if (!event || typeof event !== 'object') return
          if (event.type === 'tool_call' || event.type === 'tool_result') {
            const data = event.data as CopilotToolEvent
            const status =
              data.status === 'calling' || data.status === 'called'
                ? data.status
                : event.type === 'tool_call'
                  ? 'calling'
                  : 'called'
            const args =
              data.args && typeof data.args === 'object' && !Array.isArray(data.args)
                ? data.args
                : baseToolContent.args
            const nextToolContent: ToolContent = {
              ...baseToolContent,
              tool_call_id: toolCallId,
              name: typeof data.name === 'string' && data.name ? data.name : baseToolContent.name,
              function:
                typeof data.function === 'string' && data.function
                  ? data.function
                  : baseToolContent.function,
              status,
              args,
              content:
                data.content && typeof data.content === 'object' && !Array.isArray(data.content)
                  ? data.content
                  : baseToolContent.content,
            }
            upsertToolMessage(toolCallId, nextToolContent)
            toolUpdated = true
            return
          }

          if (event.type === 'patch') {
            const patchData = event.data as CopilotPatchResponse
            const patchTimestamp = Math.floor(Date.now() / 1000)
            const patchContent = buildPatchReviewFromCopilotPatch(patchData, patchTimestamp, toolCallId)
            if (!patchContent) {
              const rationaleParts: string[] = []
              if (typeof patchData.title === 'string' && patchData.title.trim()) {
                rationaleParts.push(patchData.title.trim())
              }
              if (Array.isArray(patchData.explanations)) {
                patchData.explanations.forEach((item) => {
                  if (typeof item === 'string' && item.trim()) {
                    rationaleParts.push(item.trim())
                  }
                })
              }
              if (rationaleParts.length > 0) {
                appendTimelineStatus(rationaleParts.join(' · '))
              }
              return
            }
            const patchMessageId = `patch-review-${patchData.patch_id || toolCallId}`
            const existingIndex = messagesRef.current.findIndex((item) => item.id === patchMessageId)
            if (existingIndex >= 0) {
              const nextMessages = [...messagesRef.current]
              const existing = nextMessages[existingIndex]
              if (existing.type === 'patch_review') {
                nextMessages[existingIndex] = { ...existing, content: patchContent }
                updateMessages(nextMessages)
              }
            } else if (!patchReviewSeenRef.current.has(patchMessageId)) {
              patchReviewSeenRef.current.add(patchMessageId)
              appendMessage({
                id: patchMessageId,
                type: 'patch_review',
                seq: resolveTimelineSeq(),
                ts: patchTimestamp,
                content: patchContent,
              })
            }
            patchRecompileTargetsRef.current.set(patchMessageId, {
              projectId,
              folderId,
            })
          }
        })

        if (!toolUpdated) {
          upsertToolMessage(toolCallId, { ...baseToolContent, status: 'called' })
        }
      } catch (error) {
        const errorPayload: CopilotFixWithAIErrorResponse | null =
          axios.isAxiosError(error) && error.response?.data?.ok === false
            ? (error.response?.data as CopilotFixWithAIErrorResponse)
            : null
        const message =
          errorPayload?.message ||
          (error instanceof Error ? error.message : 'fix_with_ai_failed')
        const requestId = errorPayload?.request_id
        const suggestion = errorPayload?.suggestion
        const timelineMessage = requestId
          ? `${message} (request_id: ${requestId})`
          : message

        upsertToolMessage(toolCallId, {
          ...baseToolContent,
          status: 'called',
          error: errorPayload?.code || message,
          content: {
            error: errorPayload?.code || message,
            message,
            request_id: requestId,
            suggestion,
          },
        })
        appendTimelineStatus(timelineMessage)
        addToast({
          type: 'error',
          title: 'Fix with AI failed',
          description: [message, suggestion, requestId ? `request_id: ${requestId}` : null]
            .filter(Boolean)
            .join(' '),
        })
      } finally {
        fixWithAiRunningRef.current = false
        setFixWithAiRunning(false)
      }
    },
    [
      activeResource?.tabId,
      addToast,
      appendMessage,
      appendTimelineStatus,
      buildContext,
      ensureSession,
      projectId,
      readOnlyMode,
      recentFiles,
      resolveTimelineSeq,
      t,
      updateMessages,
      upsertToolMessage,
    ]
  )

  useEffect(() => {
    runFixWithAiRef.current = handleFixWithAi
  }, [handleFixWithAi])

  const updatePatchReviewMessage = useCallback(
    (
      messageId: string,
      updater: PatchReviewContent | ((content: PatchReviewContent) => PatchReviewContent)
    ) => {
      const index = messagesRef.current.findIndex((item) => item.id === messageId)
      if (index < 0) return null
      const message = messagesRef.current[index]
      if (message.type !== 'patch_review') return null
      const current = message.content as PatchReviewContent
      const nextContent = typeof updater === 'function' ? updater(current) : updater
      const nextMessage: ChatMessageItem = { ...message, content: nextContent }
      const nextMessages = [...messagesRef.current]
      nextMessages[index] = nextMessage
      updateMessages(nextMessages)
      return nextContent
    },
    [updateMessages]
  )

  const handlePatchDecision = useCallback(
    async (messageId: string, action: 'accept' | 'reject') => {
      const existing = messagesRef.current.find((item) => item.id === messageId)
      if (!existing || existing.type !== 'patch_review') return
      const patchContent = existing.content as PatchReviewContent
      if (patchContent.status === 'applying') return

      if (action === 'reject') {
        updatePatchReviewMessage(messageId, {
          ...patchContent,
          status: 'rejected',
        })
        appendTimelineStatus('Patch rejected.')
        patchRecompileTargetsRef.current.delete(messageId)
        return
      }

      if (!sessionId) {
        updatePatchReviewMessage(messageId, {
          ...patchContent,
          status: 'failed',
          error: 'Session unavailable.',
        })
        appendTimelineStatus('Patch failed: session unavailable.')
        return
      }

      updatePatchReviewMessage(messageId, {
        ...patchContent,
        status: 'applying',
        error: undefined,
      })

      try {
        const recompileTarget = patchRecompileTargetsRef.current.get(messageId)
        const shouldRecompile = Boolean(recompileTarget)
        const response = await applySessionPatch(sessionId, {
          patch: patchContent.patch,
          recompile: shouldRecompile,
        })
        if (!response?.success) {
          throw new Error(response?.error || 'apply_patch_failed')
        }
        const effects = Array.isArray(response.effects) ? response.effects : []
        effects.forEach((effect) => {
          if (!effect || typeof effect !== 'object') return
          if (effect.name) {
            handleUIEffect(effect, { surface: sessionSurface })
          }
        })
        if (projectId) {
          const fileStore = useFileContentStore.getState()
          effects.forEach((effect) => {
            const data = (effect as { data?: Record<string, unknown> }).data || {}
            const fileId = typeof data.fileId === 'string' ? data.fileId : undefined
            if (!fileId) return
            void fileStore.reload({ projectId, fileId }).catch(() => undefined)
            if (typeof window !== 'undefined') {
              window.dispatchEvent(
                new CustomEvent('ds:file:reload', {
                  detail: {
                    projectId,
                    fileId,
                    filePath: typeof data.filePath === 'string' ? data.filePath : undefined,
                    source: 'patch-review',
                  },
                })
              )
            }
          })
        }
        updatePatchReviewMessage(messageId, (current) => ({
          ...current,
          status: 'accepted',
          summary: response.summary ?? current.summary,
        }))
        let recompileStarted = false
        let recompileError: string | null = null
        if (recompileTarget) {
          try {
            const build = await compileLatex(recompileTarget.projectId, recompileTarget.folderId, {
              auto: false,
              stop_on_first_error: false,
            })
            recompileStarted = true
            if (typeof window !== 'undefined') {
              window.dispatchEvent(
                new CustomEvent('ds:latex-build', {
                  detail: {
                    projectId: recompileTarget.projectId,
                    folderId: recompileTarget.folderId,
                    buildId: build.build_id,
                    status: build.status,
                    errorMessage: build.error_message ?? null,
                  },
                })
              )
            }
          } catch (error) {
            recompileError = error instanceof Error ? error.message : 'recompile_failed'
          }
        }
        if (recompileTarget) {
          appendTimelineStatus(
            recompileStarted
              ? 'Patch applied. Recompile started.'
              : 'Patch applied. Recompile failed to start.'
          )
          if (recompileError) {
            addToast({
              type: 'error',
              title: 'Recompile failed',
              description: 'Unable to start a new LaTeX build. Please retry.',
            })
          }
        } else {
          appendTimelineStatus('Patch applied.')
        }
        patchRecompileTargetsRef.current.delete(messageId)
      } catch (error) {
        const detail =
          axios.isAxiosError(error) && error.response?.data?.detail
            ? String(error.response.data.detail)
            : null
        const message = detail || (error instanceof Error ? error.message : 'apply_patch_failed')
        updatePatchReviewMessage(messageId, (current) => ({
          ...current,
          status: 'failed',
          error: message,
        }))
        appendTimelineStatus(`Patch failed to apply: ${message}`)
        addToast({
          type: 'error',
          title: 'Patch failed',
          description: message,
        })
      }
    },
    [
      addToast,
      appendTimelineStatus,
      projectId,
      sessionId,
      sessionSurface,
      updatePatchReviewMessage,
    ]
  )

  const isDisplayLockActive = useCallback((lock: { id: string; kind: DisplayLockKind }) => {
    const message = messagesRef.current.find((item) => item.id === lock.id)
    if (!message) return false
    if (lock.kind === 'assistant') {
      if (message.type !== 'text_delta') return false
      return (message.content as MessageContent).status === 'in_progress'
    }
    if (lock.kind === 'reasoning') {
      if (message.type !== 'reasoning') return false
      return (message.content as ReasoningContent).status === 'in_progress'
    }
    if (lock.kind === 'tool') {
      if (message.type !== 'tool' && message.type !== 'tool_call' && message.type !== 'tool_result') {
        return false
      }
      return (message.content as ToolContent).status === 'calling'
    }
    if (lock.kind === 'status') {
      if (message.type !== 'status') return false
      return (message.content as StatusContent).status === 'in_progress'
    }
    return false
  }, [])

  const startDisplayLock = useCallback(
    (id: string, kind: DisplayLockKind) => {
      if (restoringRef.current) return
      const current = displayLockRef.current
      if (current && current.id === id && current.kind === kind) {
        displayPendingRef.current.set(id, Date.now())
        return
      }
      if (current && current.id !== id) {
        displayPendingRef.current.delete(current.id)
      }
      displayPendingRef.current.set(id, Date.now())
      displayLockRef.current = { id, kind }
      setDisplayLockState({ id, kind })
      traceLog('display:lock:start', {
        id,
        kind,
        activeStream: activeReasoningStreamRef.current,
        buffered: bufferedEventsRef.current.length,
      })
      if (displayLockTimerRef.current) {
        window.clearTimeout(displayLockTimerRef.current)
      }
      const scheduleTimeout = () => {
        displayLockTimerRef.current = window.setTimeout(() => {
          const activeLock = displayLockRef.current
          if (!activeLock) return
          if (activeLock.id !== id || activeLock.kind !== kind) return
          const pendingSince = displayPendingRef.current.get(id)
          if (pendingSince != null) {
            if (Date.now() - pendingSince < MAX_DISPLAY_LOCK_MS) {
              scheduleTimeout()
              return
            }
            displayPendingRef.current.delete(id)
          }
          if (isDisplayLockActive(activeLock)) {
            scheduleTimeout()
            return
          }
          displayLockRef.current = null
          displayPendingRef.current.delete(id)
          setDisplayLockState(null)
          displayLockTimerRef.current = null
          flushBufferedEvents()
        }, DISPLAY_LOCK_TIMEOUT_MS)
      }
      scheduleTimeout()
    },
    [flushBufferedEvents, isDisplayLockActive]
  )

  useEffect(() => {
    startDisplayLockRef.current = startDisplayLock
  }, [startDisplayLock])

  const endDisplayLock = useCallback(
    (payload: { id: string; kind: DisplayLockKind }) => {
      const { id, kind } = payload
      const current = displayLockRef.current
      if (!current || current.id !== id || current.kind !== kind) return
      displayLockRef.current = null
      if (kind === 'reasoning' && reasoningStallTimerRef.current) {
        window.clearTimeout(reasoningStallTimerRef.current)
        reasoningStallTimerRef.current = null
        reasoningLastUpdateRef.current = null
      }
      displayPendingRef.current.delete(id)
      setDisplayLockState(null)
      if (displayLockTimerRef.current) {
        window.clearTimeout(displayLockTimerRef.current)
        displayLockTimerRef.current = null
      }
      traceLog('display:lock:end', {
        id,
        kind,
        activeStream: activeReasoningStreamRef.current,
        buffered: bufferedEventsRef.current.length,
      })
      flushBufferedEvents()
    },
    [debugLog, flushBufferedEvents]
  )

  useEffect(() => {
    if (isPaused || isStreaming) return
    if (connection.status !== 'closed' && connection.status !== 'error') return
    const activeLock = displayLockRef.current
    if (activeLock) {
      endDisplayLock(activeLock)
      return
    }
    if (bufferedEventsRef.current.length > 0) {
      flushBufferedEvents()
    }
  }, [connection.status, endDisplayLock, flushBufferedEvents, isPaused, isStreaming])

  useEffect(() => {
    if (readOnlyMode) return
    if (!sessionId) return
    if (isPaused) return
    if (isRestoringRef.current) return
    if (connection.status !== 'closed' && connection.status !== 'error') return
    const shouldResume =
      sessionActive ||
      pendingRun ||
      hasActiveRun ||
      isSessionStatusActive(sessionStatus)
    if (!shouldResume) return
    if (autoResumeTimerRef.current) return
    autoResumeTimerRef.current = window.setTimeout(() => {
      autoResumeTimerRef.current = null
      void sendMessage({
        sessionId,
        message: '',
        surface: sessionSurface,
        executionTarget: executionTargetRef.current,
        cliServerId: cliServerIdRef.current,
        replayFromLastEvent: true,
      }).catch((error) => {
        console.warn('[AiManus] Auto-resume stream failed', error)
      })
    }, 800)
  }, [
    connection.status,
    hasActiveRun,
    isPaused,
    pendingRun,
    readOnlyMode,
    sendMessage,
    sessionActive,
    sessionId,
    sessionStatus,
    sessionSurface,
  ])

  const scheduleReasoningStallCheck = useCallback(() => {
    if (reasoningStallTimerRef.current) {
      window.clearTimeout(reasoningStallTimerRef.current)
    }
    reasoningStallTimerRef.current = window.setTimeout(() => {
      const activeLock = displayLockRef.current
      const lastUpdate = reasoningLastUpdateRef.current
      if (!activeLock || activeLock.kind !== 'reasoning' || !lastUpdate) {
        reasoningStallTimerRef.current = null
        return
      }
      if (Date.now() - lastUpdate < REASONING_STALL_TIMEOUT_MS) {
        scheduleReasoningStallCheck()
        return
      }
      sealActiveReasoningSegment()
      const currentLock = displayLockRef.current
      if (currentLock?.kind === 'reasoning') {
        endDisplayLock({ id: currentLock.id, kind: 'reasoning' })
      }
      reasoningLastUpdateRef.current = null
      reasoningStallTimerRef.current = null
    }, REASONING_STALL_TIMEOUT_MS)
  }, [endDisplayLock, sealActiveReasoningSegment])

  const finalizeActiveMessages = useCallback(
    (finalStatus: 'completed' | 'failed' | 'paused', options?: { flushBuffered?: boolean }) => {
      const resolvedStepStatus =
        finalStatus === 'failed' ? 'failed' : finalStatus === 'paused' ? 'paused' : 'completed'
      let updated = false
      const nextMessages = messagesRef.current.map((message) => {
        if (message.type === 'text_delta') {
          const content = message.content as MessageContent
          if (content.role === 'assistant' && content.status === 'in_progress') {
            updated = true
            return { ...message, content: { ...content, status: 'completed' } }
          }
        } else if (message.type === 'reasoning') {
          const content = message.content as ReasoningContent
          if (content.status === 'in_progress') {
            updated = true
            return { ...message, content: { ...content, status: 'completed' } }
          }
        } else if (message.type === 'tool_call') {
          const content = message.content as ToolContent
          if (content.status === 'calling') {
            updated = true
            return { ...message, content: { ...content, status: 'called' } }
          }
        } else if (message.type === 'step') {
          const content = message.content as StepContent
          if (content.status === 'running') {
            updated = true
            return { ...message, content: { ...content, status: resolvedStepStatus } }
          }
        } else if (message.type === 'question_prompt') {
          const content = message.content as QuestionPromptContent
          if (content.status === 'calling') {
            updated = true
            return { ...message, content: { ...content, status: 'called' } }
          }
        } else if (message.type === 'clarify_question') {
          const content = message.content as ClarifyQuestionContent
          if (content.status === 'calling') {
            updated = true
            return { ...message, content: { ...content, status: 'called' } }
          }
        }
        return message
      }) as ChatMessageItem[]

      if (updated) {
        updateMessages(nextMessages)
        for (const [key, value] of reasoningByIdRef.current.entries()) {
          const replacement = nextMessages.find((item) => item.id === value.id)
          if (replacement && replacement !== value) {
            reasoningByIdRef.current.set(key, replacement)
          }
        }
        for (let i = nextMessages.length - 1; i >= 0; i -= 1) {
          const message = nextMessages[i]
          if (message.type === 'reasoning') {
            lastReasoningRef.current = message.content as ReasoningContent
            break
          }
        }
      }

      if (questionPromptRef.current) {
        setQuestionPrompt(null)
        questionPromptRef.current = null
      }
      if (clarifyPromptRef.current) {
        setClarifyPrompt(null)
        clarifyPromptRef.current = null
      }

      if (lastStepRef.current?.status === 'running') {
        lastStepRef.current.status = resolvedStepStatus
      }
      if (lastToolRef.current?.status === 'calling') {
        lastToolRef.current.status = 'called'
      }
      if (lastNoMessageToolRef.current?.status === 'calling') {
        lastNoMessageToolRef.current.status = 'called'
      }
      setToolPanelLive(false)

      if (displayLockRef.current) {
        displayLockRef.current = null
        displayPendingRef.current.clear()
        setDisplayLockState(null)
      }
      if (displayLockTimerRef.current) {
        window.clearTimeout(displayLockTimerRef.current)
        displayLockTimerRef.current = null
      }
      if (options?.flushBuffered === false) {
        bufferedEventsRef.current = []
      } else {
        flushBufferedEvents()
      }
    },
    [flushBufferedEvents, updateMessages, setToolPanelLive]
  )

  const pauseActiveStream = useCallback(
    (reason: 'paused' | 'cancelled', runIdOverride?: number) => {
      const activeRunId = runIdOverride ?? streamRunIdRef.current
      const nextPause = { runId: activeRunId, reason }
      pauseStateRef.current = nextPause
      setPauseState(nextPause)
      if (activeRunId > 0) {
        abortedRunIdRef.current = activeRunId
      }
      setCopilotStatus(reason === 'paused' ? 'Paused' : 'Cancelled')
      finalizeActiveMessages('paused', { flushBuffered: false })
      reasoningLocksRef.current.clear()
      activeReasoningStreamRef.current = null
      if (displayLockTimerRef.current) {
        window.clearTimeout(displayLockTimerRef.current)
        displayLockTimerRef.current = null
      }
      displayLockRef.current = null
      displayPendingRef.current.clear()
      setDisplayLockState(null)
    },
    [finalizeActiveMessages]
  )

  const abortActiveStreamForClarify = useCallback(() => {
    const activeRunId = streamRunIdRef.current
    if (activeRunId > 0) {
      abortedRunIdRef.current = activeRunId
    }
    stop()
    finalizeActiveMessages('paused', { flushBuffered: false })
    reasoningLocksRef.current.clear()
    activeReasoningStreamRef.current = null
    if (displayLockTimerRef.current) {
      window.clearTimeout(displayLockTimerRef.current)
      displayLockTimerRef.current = null
    }
    displayLockRef.current = null
    displayPendingRef.current.clear()
    setDisplayLockState(null)
  }, [finalizeActiveMessages, stop])

  const handleEvent = useCallback(
    (event: AgentSSEEvent) => {
      if (!event?.data || typeof event.data !== 'object') return
      if (restoringRef.current) {
        const data = event.data as unknown as Record<string, unknown>
        const eventId = typeof data.event_id === 'string' ? data.event_id : null
        if (eventId) {
          restoreEventIdsRef.current.add(eventId)
        }
      }
      const metadata = event.data?.metadata
      if (
        !restoringRef.current &&
        isCopilotSurface &&
        (metadata?.surface || metadata?.reply_to_surface) &&
        (event.event === 'message' || event.event === 'attachments')
      ) {
        const role = (event.data as MessageEventData).role
        const targetSurface =
          role === 'assistant'
            ? metadata.reply_to_surface ?? metadata.surface
            : metadata.surface ?? metadata.reply_to_surface
        if (targetSurface === 'welcome' || targetSurface === 'copilot') {
          const surfaceMatches =
            targetSurface === sessionSurface ||
            (sessionSurface === 'copilot' && targetSurface === 'welcome') ||
            (sessionSurface === 'welcome' && targetSurface === 'copilot')
          if (!surfaceMatches) return
        }
      }

      const questionPromptActive = Boolean(questionPromptRef.current)
      const clarifyPromptActive = Boolean(clarifyPromptRef.current)
      if ((questionPromptActive || clarifyPromptActive) && !restoringRef.current) {
        if (event.event === 'reasoning') {
          return
        }
        if (event.event === 'message') {
          const messageData = event.data as Partial<MessageEventData>
          const role = coerceRole(messageData.role)
          if (role === 'assistant') return
        }
        if (event.event === 'tool') {
          const toolData = event.data as Partial<ToolEventData>
          const functionName = normalizeToolFunctionName(
            typeof toolData.function === 'string' ? toolData.function : ''
          )
          if (functionName !== 'question_prompt' && functionName !== 'clarify_question') return
        }
        if (event.event === 'plan' || event.event === 'step') {
          return
        }
      }

      const shouldClearPending =
        event.event === 'message' ||
        event.event === 'tool' ||
        event.event === 'step' ||
        event.event === 'status' ||
        event.event === 'reasoning' ||
        event.event === 'attachments' ||
        event.event === 'plan' ||
        event.event === 'wait' ||
        event.event === 'error' ||
        event.event === 'done'
      if (pendingRun && shouldClearPending) {
        setPendingRun(false)
      }

      if (displayLockRef.current?.kind === 'reasoning' && event.event !== 'reasoning') {
        sealActiveReasoningSegment()
      }

      const eventId = event.data?.event_id
      const isTransientDeltaEvent =
        (event.event === 'message' || event.event === 'reasoning') &&
        typeof (event.data as Partial<MessageEventData>)?.delta === 'string' &&
        Boolean((event.data as Partial<MessageEventData>).delta)
      if (eventId && sessionId && !isTransientDeltaEvent) {
        setLastEventId(sessionId, eventId)
      }

      if (shouldBufferEvent(event)) {
        const wasEmpty = bufferedEventsRef.current.length === 0
        bufferedEventsRef.current.push(event)
        if (wasEmpty) {
          traceLog('buffer:start', {
            event: event.event,
            eventId: event.data?.event_id ?? null,
            lock: displayLockRef.current,
            activeStream: activeReasoningStreamRef.current,
          })
        }
        return
      }

      if (
        event.event === 'message' ||
        event.event === 'tool' ||
        event.event === 'step' ||
        event.event === 'attachments'
      ) {
        closeReasoningSegment(true)
      } else if (event.event !== 'reasoning') {
        closeReasoningSegment()
      }

      if (
        event.event === 'message' ||
        event.event === 'attachments' ||
        event.event === 'receipt'
      ) {
        const handled = applyChatEvent(event, {
          sessionId,
          messagesRef,
          assistantMessageIndexRef,
          lastAssistantSegmentIdRef,
          attachmentsSeenRef,
          pendingUserRef,
          resolveTimelineSeq,
          buildTextDeltaId,
          appendMessage,
          updateMessages,
          queueMessages,
          closeAssistantSegment: () => {
            closeAssistantSegment()
            collapseActiveReasoning()
          },
          startDisplayLock: (id) => startDisplayLock(id, 'assistant'),
          setCopilotStatus: isCopilotSurface ? setCopilotStatus : undefined,
          onSessionUpdate: sessionId
            ? (content, timestamp) => {
                upsertSession(sessionId, {
                  latest_message: content,
                  latest_message_at: timestamp,
                  updated_at: timestamp,
                  status: restoredStatusRef.current ?? null,
                })
              }
            : undefined,
          shouldDeferAttachments: () => Boolean(displayLockRef.current) && !restoringRef.current,
          onDeferAttachments: (attachmentEvent) => {
            bufferedEventsRef.current.push(attachmentEvent)
          },
        })
        if (handled) return
      }

      if (event.event === 'reasoning') {
        const reasoningData = event.data as Partial<ReasoningEventData>
        const reasoningId =
          typeof reasoningData.reasoning_id === 'string' && reasoningData.reasoning_id
            ? reasoningData.reasoning_id
            : ''
        if (!reasoningId) return
        const eventSeq = resolveTimelineSeq(getEventSequence(event))
        const status = reasoningData.status === 'completed' ? 'completed' : 'in_progress'
        const delta = typeof reasoningData.delta === 'string' ? reasoningData.delta : ''
        const contentValue =
          typeof reasoningData.content === 'string' ? reasoningData.content : ''
        const shouldMarkReasoningUpdate =
          Boolean(contentValue || delta) || reasoningLastUpdateRef.current == null
        if (shouldMarkReasoningUpdate) {
          reasoningLastUpdateRef.current = Date.now()
          scheduleReasoningStallCheck()
        }
        const kind = coerceReasoningKind(reasoningData.kind)
        const timestamp = coerceTimestamp(reasoningData.timestamp)
        const streamKey = buildReasoningStreamKey(
          reasoningId,
          kind,
          reasoningData.reasoning_stream_id
        )
        if (activeReasoningStreamRef.current && activeReasoningStreamRef.current !== streamKey) {
          closeReasoningSegment(true)
        }
        const messageKey = getReasoningMessageKey(streamKey)
        const existing = reasoningByIdRef.current.get(messageKey)
        if (existing && existing.type === 'reasoning') {
          const reasoningContent = existing.content as ReasoningContent
          const baseText = typeof reasoningContent.content === 'string' ? reasoningContent.content : ''
          let nextText = baseText
          if (contentValue) {
            nextText = contentValue
          } else if (delta) {
            nextText = `${baseText}${delta}`
          }
          const nextContent: ReasoningContent = {
            ...reasoningContent,
            content: nextText,
            status,
            kind,
            timestamp,
          }
          const nextMessage: ChatMessageItem = { ...existing, content: nextContent }
          const throttleUpdate = status === 'in_progress' && Boolean(delta)
          if (!replaceMessageById(nextMessage, { throttle: throttleUpdate })) {
            updateMessages([...messagesRef.current, nextMessage])
          }
          reasoningByIdRef.current.set(messageKey, nextMessage)
          lastReasoningRef.current = nextContent
          activeReasoningStreamRef.current = streamKey
          startDisplayLock(existing.id, 'reasoning')
          if (status === 'completed') {
            reasoningLocksRef.current.delete(streamKey)
            if (!restoringRef.current && reasoningLocksRef.current.size === 0) {
              flushBufferedEvents()
            }
          } else {
            reasoningLocksRef.current.add(streamKey)
          }
          return
        }
        if (!contentValue && !delta) return

        const message: ChatMessageItem = {
          id: typeof reasoningData.event_id === 'string' ? reasoningData.event_id : createMessageId('reasoning'),
          type: 'reasoning',
          seq: eventSeq,
          ts: timestamp,
          content: {
            reasoning_id: reasoningId,
            status,
            content: contentValue || delta,
            kind,
            timestamp,
            collapsed: false,
          } as ReasoningContent,
        }
        appendMessage(message)
        reasoningByIdRef.current.set(messageKey, message)
        lastReasoningRef.current = message.content as ReasoningContent
        activeReasoningStreamRef.current = streamKey
        startDisplayLock(message.id, 'reasoning')
        if (status === 'completed') {
          reasoningLocksRef.current.delete(streamKey)
          if (!restoringRef.current && reasoningLocksRef.current.size === 0) {
            flushBufferedEvents()
          }
        } else {
          reasoningLocksRef.current.add(streamKey)
        }
        return
      }

      if (event.event === 'tool') {
        const toolData = event.data as Partial<ToolEventData>
        const eventSeq = resolveTimelineSeq(getEventSequence(event))
        const toolTimestamp = coerceTimestamp(toolData.timestamp)
        const functionNameRaw = typeof toolData.function === 'string' ? toolData.function : ''
        const functionName = normalizeToolFunctionName(functionNameRaw)
        const toolCallId =
          typeof toolData.tool_call_id === 'string' && toolData.tool_call_id
            ? toolData.tool_call_id
            : createMessageId('tool')
        const status =
          toolData.status === 'calling' || toolData.status === 'called' ? toolData.status : 'called'
        const toolName = typeof toolData.name === 'string' ? toolData.name : ''
        const activeLock = displayLockRef.current
        closeAssistantSegment()
        if (activeLock?.kind === 'assistant') {
          endDisplayLock(activeLock)
        }

        if (!restoringRef.current && status === 'calling' && toolName !== 'message') {
          const seen = toolCallSeenRef.current
          if (!seen.has(toolCallId)) {
            seen.add(toolCallId)
            setToolCallCount((count) => count + 1)
          }
        }

        if (status === 'calling') {
          collapseActiveReasoning()
          if (!restoringRef.current && typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent('ds:tool:call', {
                detail: {
                  toolCallId,
                  function: functionName,
                  name: toolName,
                  status,
                },
              })
            )
          }
        }

        if (!restoringRef.current && status === 'calling') {
          const preview = buildPdfToolPreview(toolData)
          if (preview) {
            previewPdfToolEffect(preview)
          }
        }

        if (functionName === 'context_read' && status === 'calling' && sessionId) {
          if (!restoringRef.current) {
            const context = buildContext()
            if (context) {
              void submitToolOutput(sessionId, toolCallId, { context })
            }
          }
          return
        }

        if (functionName === 'question_prompt') {
          const timestamp = toolTimestamp
          const messageId = `question_prompt-${toolCallId}`
          const existingIndex = messagesRef.current.findIndex((item) => item.id === messageId)
          const baseArgs =
            toolData.args && typeof toolData.args === 'object' && !Array.isArray(toolData.args)
              ? (toolData.args as Record<string, unknown>)
              : {}

          const nextContent: QuestionPromptContent = {
            timestamp,
            metadata: toolData.metadata,
            toolCallId,
            args: baseArgs,
            status,
          }

          if (status === 'called') {
            const content =
              toolData.content && typeof toolData.content === 'object' && !Array.isArray(toolData.content)
                ? (toolData.content as Record<string, unknown>)
                : {}
            const contentError = typeof content.error === 'string' ? content.error : ''
            const result =
              content.result && typeof content.result === 'object' && !Array.isArray(content.result)
                ? (content.result as Record<string, unknown>)
                : null
            const resultStatus = typeof result?.status === 'string' ? result.status.toLowerCase() : ''
            const resultAnswers =
              result && typeof result.answers === 'object' && result.answers && !Array.isArray(result.answers)
                ? (result.answers as QuestionPromptAnswerMap)
                : undefined
            const resultReason = result && typeof result.reason === 'string' ? result.reason : ''
            const errors = Array.isArray(result?.errors) ? (result?.errors as string[]) : []
            const errorMessage =
              contentError ||
              (resultStatus && resultStatus !== 'ok' && resultStatus !== 'success'
                ? [resultReason || 'Tool error', errors.length ? `(${errors.join(', ')})` : '']
                    .filter(Boolean)
                    .join(' ')
                : '') ||
              ''

            if (resultAnswers) {
              nextContent.answers = resultAnswers
            }
            if (errorMessage) {
              nextContent.error = errorMessage
            }
          }

          if (existingIndex >= 0) {
            const nextMessages = [...messagesRef.current]
            const existing = nextMessages[existingIndex]
            if (existing.type === 'question_prompt') {
              nextMessages[existingIndex] = {
                ...existing,
                content: { ...(existing.content as QuestionPromptContent), ...nextContent },
              }
              updateMessages(nextMessages)
            }
          } else {
            appendMessage({
              id: messageId,
              type: 'question_prompt',
              seq: eventSeq,
              ts: timestamp,
              content: nextContent,
            })
          }

          const restoredStatus = restoredStatusRef.current
          if (readOnlyMode) {
            setQuestionPrompt(null)
            questionPromptRef.current = null
            return
          }
          if (status === 'calling') {
            if (!cacheReplayRef.current || restoredStatus === 'waiting') {
              const nextPrompt = {
                toolCallId,
                args: baseArgs,
              }
              setQuestionPrompt(nextPrompt)
              questionPromptRef.current = nextPrompt
            }
            if (isCopilotSurface) {
              setCopilotStatus('Waiting for your input')
            }
          } else if (status === 'called') {
            setQuestionPrompt(null)
            questionPromptRef.current = null
            if (isCopilotSurface) {
              setCopilotStatus(null)
            }
          }
          return
        }

        if (functionName === 'clarify_question') {
          const timestamp = toolTimestamp
          const messageId = `clarify_question-${toolCallId}`
          const existingIndex = messagesRef.current.findIndex((item) => item.id === messageId)
          const baseArgs =
            toolData.args && typeof toolData.args === 'object' && !Array.isArray(toolData.args)
              ? (toolData.args as Record<string, unknown>)
              : {}
          const question =
            typeof baseArgs.question === 'string'
              ? baseArgs.question
              : typeof baseArgs.title === 'string'
                ? baseArgs.title
                : 'Clarify request'
          const options = normalizeClarifyOptions(baseArgs.options ?? baseArgs.choices ?? baseArgs.values)
          const multi = coerceBoolean(baseArgs.multi ?? baseArgs.multiple)
          const defaultSelected = coerceStringArray(
            baseArgs.default_selected ?? baseArgs.defaultSelected
          )
          const missingFields = coerceStringArray(baseArgs.missing_fields ?? baseArgs.missingFields)
          const questionId =
            typeof baseArgs.question_id === 'string'
              ? baseArgs.question_id
              : typeof baseArgs.questionId === 'string'
                ? baseArgs.questionId
                : typeof baseArgs.id === 'string'
                  ? baseArgs.id
                  : ''

          const nextContent: ClarifyQuestionContent = {
            timestamp,
            metadata: toolData.metadata,
            toolCallId,
            question,
            options,
            multi,
            status: status === 'calling' ? 'calling' : 'called',
            defaultSelected,
            missingFields,
            source: 'backend',
          }

          if (status === 'called') {
            const content =
              toolData.content && typeof toolData.content === 'object' && !Array.isArray(toolData.content)
                ? (toolData.content as Record<string, unknown>)
                : {}
            const contentError = typeof content.error === 'string' ? content.error : ''
            const result =
              content.result && typeof content.result === 'object' && !Array.isArray(content.result)
                ? (content.result as Record<string, unknown>)
                : null
            const resultStatus = typeof result?.status === 'string' ? result.status.toLowerCase() : ''
            const resultAnswers =
              result && typeof result.answers === 'object' && result.answers && !Array.isArray(result.answers)
                ? (result.answers as Record<string, unknown>)
                : undefined
            const resultReason = result && typeof result.reason === 'string' ? result.reason : ''
            const errors = Array.isArray(result?.errors) ? (result?.errors as string[]) : []
            const errorMessage =
              contentError ||
              (resultStatus && resultStatus !== 'ok' && resultStatus !== 'success'
                ? [resultReason || 'Tool error', errors.length ? `(${errors.join(', ')})` : '']
                    .filter(Boolean)
                    .join(' ')
                : '') ||
              ''

            if (resultAnswers) {
              const answerValue =
                questionId && resultAnswers[questionId] !== undefined
                  ? resultAnswers[questionId]
                  : Object.values(resultAnswers)[0]
              const resolved = resolveClarifySelections(answerValue, options)
              if (resolved.selections.length > 0) {
                nextContent.selections = resolved.selections
                nextContent.selectedLabels = resolved.selectedLabels
              }
            }
            if (errorMessage) {
              nextContent.error = errorMessage
            }
          }

          if (existingIndex >= 0) {
            const nextMessages = [...messagesRef.current]
            const existing = nextMessages[existingIndex]
            if (existing.type === 'clarify_question') {
              nextMessages[existingIndex] = {
                ...existing,
                content: { ...(existing.content as ClarifyQuestionContent), ...nextContent },
              }
              updateMessages(nextMessages)
            }
          } else {
            appendMessage({
              id: messageId,
              type: 'clarify_question',
              seq: eventSeq,
              ts: timestamp,
              content: nextContent,
            })
          }

          const restoredStatus = restoredStatusRef.current
          if (readOnlyMode) {
            setClarifyPrompt(null)
            clarifyPromptRef.current = null
            return
          }
          if (status === 'calling') {
            if (!cacheReplayRef.current || restoredStatus === 'waiting') {
              const nextPrompt = {
                messageId,
                toolCallId,
                source: 'backend' as const,
                question,
                options,
                multi,
                defaultSelected,
                missingFields,
              }
              setClarifyPrompt(nextPrompt)
              clarifyPromptRef.current = nextPrompt
            }
            if (isCopilotSurface) {
              setCopilotStatus('Waiting for your input')
            }
          } else if (status === 'called') {
            setClarifyPrompt(null)
            clarifyPromptRef.current = null
            if (isCopilotSurface) {
              setCopilotStatus(null)
            }
          }
          return
        }

        if (functionName === 'mcp_status_update') {
          const baseArgs =
            toolData.args && typeof toolData.args === 'object' && !Array.isArray(toolData.args)
              ? (toolData.args as Record<string, unknown>)
              : {}
          updateStatusTodo(resolveStatusTodoText(baseArgs.todo, baseArgs.next))
          const statusMessage =
            typeof baseArgs.message === 'string'
              ? baseArgs.message
              : typeof baseArgs.text === 'string'
                ? baseArgs.text
                : ''
          const status =
            toolData.status === 'calling' || toolData.status === 'called' ? toolData.status : 'called'
          const shouldRender = status === 'calling' || toolData.status == null
          if (!shouldRender || !statusMessage) {
            if (isCopilotSurface) {
              setCopilotStatus(null)
            }
            return
          }
          const timestamp = toolTimestamp
          const eventId =
            typeof toolData.event_id === 'string' && toolData.event_id ? toolData.event_id : ''
          const messageId = buildMcpStatusMessageId(eventId, toolCallId, timestamp)
          const seen = statusToolSeenRef.current
          const toolContent: ToolContent = {
            ...(toolData as ToolEventData),
            event_id: eventId || createMessageId('tool'),
            tool_call_id: toolCallId,
            function: functionNameRaw || functionName,
            name: typeof toolData.name === 'string' && toolData.name ? toolData.name : 'message',
            status: 'called',
            args: {
              ...baseArgs,
              message: statusMessage,
            },
            timestamp,
          }
          const existingIndex = messagesRef.current.findIndex((item) => item.id === messageId)
          if (existingIndex >= 0) {
            const next = [...messagesRef.current]
            const existing = next[existingIndex]
            if (existing.type === 'tool') {
              next[existingIndex] = { ...existing, content: toolContent }
              updateMessages(next)
            }
          } else if (!seen.has(messageId)) {
            appendMessage({
              id: messageId,
              type: 'tool',
              seq: eventSeq,
              ts: timestamp,
              content: toolContent,
            })
          }
          startDisplayLock(messageId, 'tool')
          if (isCopilotSurface) {
            setCopilotStatus(null)
          }
          seen.add(messageId)
          return
        }

        const metadata = toolData.metadata
        const rawTarget =
          typeof metadata?.execution_target === 'string'
            ? metadata.execution_target.trim().toLowerCase()
            : ''
        const isCliToolEvent =
          rawTarget === 'cli' ||
          rawTarget === 'cli_server' ||
          Boolean(metadata?.cli_server_id) ||
          (!rawTarget && executionTarget === 'cli')
        const isLabSurface = sessionSurface.startsWith('lab-')

        const effects = [
          ...(toolData.ui_effect ? [toolData.ui_effect] : []),
          ...(toolData.ui_effects ?? []),
        ]
        const resolvedEffects =
          effects.length > 0 ? effects : buildFallbackEffects(toolData, status)
        if (resolvedEffects.length > 0 && !restoringRef.current) {
          const skipFileEffects = isLabSurface && isCliToolEvent
          resolvedEffects.forEach((effect) => {
            const isFileEffect =
              typeof effect?.name === 'string' && effect.name.startsWith('file:')
            if (skipFileEffects && isFileEffect) return
            handleUIEffect(effect, { surface: sessionSurface })
          })
        }

        if (isLabSurface && isCliToolEvent && !restoringRef.current) {
          applyLabCliToolEffect({
            toolData,
            functionName: functionNameRaw || functionName,
            status,
            projectId: projectId ?? null,
            sessionId,
            cliServerId:
              typeof metadata?.cli_server_id === 'string' ? metadata.cli_server_id : cliServerId,
            readOnly: readOnlyMode,
          })
        }

        if (isCopilotSurface) {
          if (isCliToolEvent && status === 'calling') {
            setCopilotStatus(null)
          } else {
            const summary = `${toolData.name ?? 'tool'} · ${functionName}`
            setCopilotStatus(status === 'calling' ? summary : null)
          }
        }

        const toolContent: ToolContent = {
          ...(toolData as ToolEventData),
          event_id:
            typeof toolData.event_id === 'string' && toolData.event_id
              ? toolData.event_id
              : createMessageId('tool'),
          tool_call_id: toolCallId,
          function: functionNameRaw || functionName,
          name: typeof toolData.name === 'string' && toolData.name ? toolData.name : 'tool',
          status,
          args:
            toolData.args && typeof toolData.args === 'object' && !Array.isArray(toolData.args)
              ? (toolData.args as Record<string, unknown>)
              : {},
          timestamp: toolTimestamp,
        }

        const mcpKind = getMcpToolKind(functionNameRaw || functionName)
        if (mcpKind === 'request_patch' && status === 'called') {
          const patchContent = buildPatchReviewContent(toolData, toolCallId)
          if (patchContent) {
            const patchMessageId = `patch-review-${toolCallId}`
            const existingIndex = messagesRef.current.findIndex((item) => item.id === patchMessageId)
            if (existingIndex >= 0) {
              const next = [...messagesRef.current]
              const existing = next[existingIndex]
              if (existing.type === 'patch_review') {
                const existingContent = existing.content as PatchReviewContent
                const nextContent: PatchReviewContent = {
                  ...patchContent,
                  status: existingContent.status ?? patchContent.status,
                  error: existingContent.error ?? patchContent.error,
                  summary: existingContent.summary ?? patchContent.summary,
                }
                next[existingIndex] = { ...existing, content: nextContent }
                updateMessages(next)
              }
            } else if (!patchReviewSeenRef.current.has(patchMessageId)) {
              patchReviewSeenRef.current.add(patchMessageId)
              appendMessage({
                id: patchMessageId,
                type: 'patch_review',
                seq: eventSeq,
                ts: patchContent.timestamp ?? toolTimestamp,
                content: patchContent,
              })
            }
          }
        }

        if (functionName === 'sandbox_switch' && status === 'called' && !restoringRef.current) {
          const args = toolContent.args as Record<string, unknown>
          const target =
            typeof args?.target === 'string' ? args.target.toLowerCase() : ''
          const resultTarget =
            typeof toolContent.content?.result === 'object' && toolContent.content?.result
              ? String((toolContent.content?.result as Record<string, unknown>).provider_type ?? '')
              : ''
          const cliId =
            typeof args?.cli_server_id === 'string' ? args.cli_server_id : ''
          const errorRaw = toolContent.content?.error as string | undefined
          const error = errorRaw ? normalizeCliErrorMessage(errorRaw) : undefined
          const title = error ? 'Runtime switch failed' : 'Runtime switched'
          const targetLabel =
            target === 'cli' || target === 'cli_server' || resultTarget === 'cli' ? 'CLI' : 'Sandbox'
          const description = error
            ? error
            : targetLabel === 'CLI' && cliId
              ? `Now using CLI server ${cliId.slice(0, 6)}`
              : `Now using ${targetLabel}`
          addToast({
            type: error ? 'error' : 'info',
            title,
            description,
            duration: 6000,
          })
        }
        const hasExistingTool = (toolCallId: string) => {
          if (!toolCallId) return false
          const currentMessages = messagesRef.current
          const toolIndex = currentMessages.findIndex((message) => {
            if (message.type !== 'tool') return false
            return (message.content as ToolContent).tool_call_id === toolCallId
          })
          if (toolIndex >= 0) return true
          const stepIndex = currentMessages.findIndex((message) => {
            if (message.type !== 'step') return false
            const stepContent = message.content as StepContent
            return stepContent.tools.some((tool) => tool.tool_call_id === toolCallId)
          })
          return stepIndex >= 0
        }

        const updateExistingTool = (nextToolContent: ToolContent) => {
          const toolCallId = nextToolContent.tool_call_id
          if (!toolCallId) return false
          const currentMessages = messagesRef.current
          const toolIndex = currentMessages.findIndex((message) => {
            if (message.type !== 'tool') return false
            return (message.content as ToolContent).tool_call_id === toolCallId
          })
          if (toolIndex >= 0) {
            const next = [...currentMessages]
            const existing = next[toolIndex]
            if (existing.type === 'tool') {
              next[toolIndex] = { ...existing, content: nextToolContent }
              updateMessages(next)
              return true
            }
          }
          const stepIndex = currentMessages.findIndex((message) => {
            if (message.type !== 'step') return false
            const stepContent = message.content as StepContent
            return stepContent.tools.some((tool) => tool.tool_call_id === toolCallId)
          })
          if (stepIndex >= 0) {
            const next = [...currentMessages]
            const stepMessage = next[stepIndex]
            if (stepMessage.type === 'step') {
              const stepContent = stepMessage.content as StepContent
              const nextTools = stepContent.tools.map((tool) =>
                tool.tool_call_id === toolCallId ? nextToolContent : tool
              )
              const nextStep = { ...stepContent, tools: nextTools }
              next[stepIndex] = { ...stepMessage, content: nextStep }
              updateMessages(next)
              if (lastStepRef.current?.id === stepContent.id) {
                lastStepRef.current = nextStep
              }
              return true
            }
          }
          return false
        }

        const applyToolUpdate = (
          nextToolContent: ToolContent,
          options?: { skipRefs?: boolean }
        ) => {
          const updated = updateExistingTool(nextToolContent)
          if (!updated) {
            let attachedToRunningStep = false
            if (
              !isCopilotSurface &&
              lastStepRef.current &&
              lastStepRef.current.status === 'running'
            ) {
              const runningStepId = lastStepRef.current.id
              const next = [...messagesRef.current]
              const stepIndex = next.findIndex((message) => {
                if (message.type !== 'step') return false
                return (message.content as StepContent).id === runningStepId
              })
              if (stepIndex >= 0) {
                const stepMessage = next[stepIndex]
                if (stepMessage.type === 'step') {
                  const stepContent = stepMessage.content as StepContent
                  const existingTools = Array.isArray(stepContent.tools) ? stepContent.tools : []
                  const toolCallId = nextToolContent.tool_call_id
                  const existingIndex = toolCallId
                    ? existingTools.findIndex((tool) => tool.tool_call_id === toolCallId)
                    : -1
                  const nextTools =
                    existingIndex >= 0
                      ? existingTools.map((tool, index) =>
                          index === existingIndex ? nextToolContent : tool
                        )
                      : [...existingTools, nextToolContent]
                  const nextStep = { ...stepContent, tools: nextTools }
                  next[stepIndex] = { ...stepMessage, content: nextStep }
                  updateMessages(next)
                  lastStepRef.current = nextStep
                  attachedToRunningStep = true
                }
              }
            }
            if (!attachedToRunningStep) {
              appendMessage({
                id: nextToolContent.tool_call_id || createMessageId('tool'),
                type: 'tool',
                seq: eventSeq,
                ts: nextToolContent.timestamp ?? toolTimestamp,
                content: nextToolContent,
              })
            }
          }
          if (options?.skipRefs) return
          lastToolRef.current = nextToolContent
          if (nextToolContent.name !== 'message') {
            startDisplayLock(nextToolContent.tool_call_id, 'tool')
          }

          if (nextToolContent.name !== 'message') {
            lastNoMessageToolRef.current = nextToolContent
            if (
              !restoringRef.current &&
              (realTimeRef.current || nextToolContent.status === 'calling')
            ) {
              if (canAutoOpenToolPanel(nextToolContent)) {
                handleToolPanelOpen(nextToolContent, isLiveTool(nextToolContent))
              }
            }
          }
        }

        applyToolUpdate(toolContent)
        return
      }

      if (event.event === 'status') {
        const statusData = event.data as unknown as Record<string, unknown>
        const statusMessage =
          typeof statusData.message === 'string'
            ? statusData.message
            : typeof statusData.text === 'string'
              ? statusData.text
              : ''
        if (!statusMessage) return
        const timestamp = coerceTimestamp(statusData.timestamp)
        const eventSeq = resolveTimelineSeq(getEventSequence(event))
        const eventId = typeof statusData.event_id === 'string' ? statusData.event_id : ''
        const toolCallId = typeof statusData.tool_call_id === 'string' ? statusData.tool_call_id : ''
        const messageId = buildMcpStatusMessageId(eventId, toolCallId, timestamp)
        updateStatusTodo(resolveStatusTodoText(statusData.todo, statusData.next))
        const seen = statusToolSeenRef.current
        const {
          metadata,
          event_id: _eventId,
          timestamp: _timestamp,
          seq,
          created_at,
          tool_call_id: _toolCallId,
          ...rest
        } = statusData as Record<string, unknown>
        const toolContent: ToolContent = {
          event_id: eventId || createMessageId('tool'),
          tool_call_id: toolCallId || createMessageId('tool'),
          name: 'message',
          status: 'called',
          function: 'mcp_status_update',
          args: {
            ...rest,
            message: statusMessage,
          },
          timestamp,
          metadata: metadata as EventMetadata | undefined,
        }
        const existingIndex = messagesRef.current.findIndex((item) => item.id === messageId)
        if (existingIndex >= 0) {
          const next = [...messagesRef.current]
          const existing = next[existingIndex]
          if (existing.type === 'tool') {
            next[existingIndex] = { ...existing, content: toolContent }
            updateMessages(next)
          }
        } else if (!seen.has(messageId)) {
          appendMessage({
            id: messageId,
            type: 'tool',
            seq: eventSeq,
            ts: timestamp,
            content: toolContent,
          })
        }
        startDisplayLock(messageId, 'tool')
        if (isCopilotSurface) {
          setCopilotStatus(null)
        }
        seen.add(messageId)
        return
      }

      if (event.event === 'step') {
        const stepData = event.data as Partial<StepEventData>
        const status = stepData.status
        if (!status) return
        const description = typeof stepData.description === 'string' ? stepData.description : ''
        const timestamp = coerceTimestamp(stepData.timestamp)
        const eventSeq = resolveTimelineSeq(getEventSequence(event))
        const stepId = typeof stepData.id === 'string' && stepData.id ? stepData.id : createMessageId('step')
        if (isCopilotSurface) {
          if (status === 'completed') {
            setCopilotStatus(null)
          } else if (status === 'failed') {
            setCopilotStatus('Step failed')
          } else {
            setCopilotStatus(`Step ${status}: ${description}`)
          }
        }
        if (status === 'running') {
          const toolCallId = stepId.startsWith('step-') ? stepId.slice(5) : null
          let nestedTool: ToolContent | null = null
          const nextMessages = [...messagesRef.current]
          if (toolCallId) {
            const toolIndex = nextMessages.findIndex((message) => {
              if (message.type !== 'tool') return false
              return (message.content as ToolContent).tool_call_id === toolCallId
            })
            if (toolIndex >= 0) {
              const toolMessage = nextMessages[toolIndex]
              if (toolMessage.type === 'tool') {
                nestedTool = toolMessage.content as ToolContent
                nextMessages.splice(toolIndex, 1)
              }
            }
          }
          const stepContent: StepContent = {
            ...(stepData as StepEventData),
            id: stepId,
            status,
            description,
            timestamp,
            tools: nestedTool ? [nestedTool] : [],
          }
          nextMessages.push({
            id: stepId,
            type: 'step',
            seq: eventSeq,
            ts: timestamp,
            content: stepContent,
          })
          updateMessages(nextMessages)
          lastStepRef.current = stepContent
        } else if (status === 'completed') {
          if (lastStepRef.current) {
            const stepId = lastStepRef.current.id
            const next = [...messagesRef.current]
            const stepIndex = next.findIndex((message) => {
              if (message.type !== 'step') return false
              return (message.content as StepContent).id === stepId
            })
            if (stepIndex >= 0) {
              const stepMessage = next[stepIndex]
              if (stepMessage.type === 'step') {
                const stepContent = stepMessage.content as StepContent
                const nextStep = { ...stepContent, status }
                next[stepIndex] = { ...stepMessage, content: nextStep }
                updateMessages(next)
                lastStepRef.current = nextStep
              }
            } else {
              lastStepRef.current = { ...lastStepRef.current, status }
            }
          }
        } else if (status === 'failed') {
          if (isCopilotSurface) {
            setCopilotStatus('Step failed')
          }
        }
        setPlan((current) => {
          if (current?.task_plan?.tasks?.length) {
            return current
          }
          const steps = current?.steps ? [...current.steps] : []
          const index = steps.findIndex((step) => step.id === stepId)
          if (index >= 0) {
            steps[index] = {
              ...steps[index],
              ...(stepData as StepEventData),
              id: stepId,
              status,
              description,
              timestamp,
            }
          } else {
            steps.push({
              ...(stepData as StepEventData),
              id: stepId,
              status,
              description,
              timestamp,
            })
          }
          return {
            event_id: current?.event_id || stepData.event_id || createMessageId('plan'),
            timestamp,
            metadata: stepData.metadata,
            steps,
          }
        })
        return
      }

      if (event.event === 'error') {
        const errorData = event.data as Partial<ErrorEventData>
        const rawErrorMessage =
          typeof errorData.error === 'string' && errorData.error ? errorData.error : 'Unexpected error'
        const errorMessage = normalizeCliErrorMessage(rawErrorMessage)
        const timestamp = coerceTimestamp(errorData.timestamp)
        const eventSeq = resolveTimelineSeq(getEventSequence(event))
        appendMessage({
          id: createMessageId('error'),
          type: 'assistant',
          seq: eventSeq,
          ts: timestamp,
          content: {
            content: errorMessage,
            timestamp,
            role: 'assistant',
          },
        })
        setCopilotStatus('Error')
        setSessionActive(false)
        if (sessionId) {
          upsertSession(sessionId, {
            status: 'failed',
            updated_at: timestamp,
            is_active: false,
          })
        }
        reasoningLocksRef.current.clear()
        if (!restoringRef.current) {
          if (displayLockRef.current) {
            displayLockRef.current = null
            displayPendingRef.current.clear()
            setDisplayLockState(null)
          }
          if (displayLockTimerRef.current) {
            window.clearTimeout(displayLockTimerRef.current)
            displayLockTimerRef.current = null
          }
          flushBufferedEvents()
        }
        return
      }

      if (event.event === 'title') {
        const titleData = event.data as Partial<TitleEventData>
        const nextTitle = typeof titleData.title === 'string' ? titleData.title : ''
        if (!nextTitle) return
        const renamed = sessionId ? getRenamedTitle(sessionId) : ''
        if (!renamed) {
          setTitle(nextTitle)
        }
        if (sessionId) {
          upsertSession(sessionId, { title: nextTitle })
        }
        return
      }

      if (event.event === 'plan') {
        const planData = event.data as Partial<PlanEventData>
        const normalizedPlan = normalizePlanEntry(planData)
        if (!normalizedPlan) return
        const hasSteps = normalizedPlan.steps.length > 0
        const hasTasks = Boolean(normalizedPlan.task_plan?.tasks?.length)
        setPlan(normalizedPlan)
        setPlanHistory((current) => {
          if (!hasSteps && !hasTasks) {
            return current
          }
          const next = [...current]
          const existingIndex = next.findIndex((entry) => entry.event_id === normalizedPlan.event_id)
          if (existingIndex >= 0) {
            next[existingIndex] = normalizedPlan
            return next
          }
          const last = next[next.length - 1]
          const lastHash = last?.task_plan?.hash
          const nextHash = normalizedPlan.task_plan?.hash
          if (lastHash && nextHash && lastHash === nextHash) {
            if (next.length > 0) {
              next[next.length - 1] = normalizedPlan
            }
            return next
          }
          next.push(normalizedPlan)
          return next
        })
        return
      }

      if (event.event === 'wait') {
        if (isCopilotSurface) {
          setCopilotStatus('Waiting for your input')
        }
        setSessionActive(false)
        if (sessionId) {
          upsertSession(sessionId, {
            status: 'waiting',
            updated_at: coerceTimestamp(event.data?.timestamp),
            is_active: false,
          })
        }
        return
      }

      if (event.event === 'recovery') {
        if (restoringRef.current) return
        const recoveryData = event.data as Partial<RecoveryEventData>
        const status =
          recoveryData.status === 'recovered' || recoveryData.status === 'failed'
            ? recoveryData.status
            : 'recovering'
        const missedCount =
          typeof recoveryData.missed_event_count === 'number' ? recoveryData.missed_event_count : null
        const message =
          status === 'recovering'
            ? 'Recovering CLI stream...'
            : status === 'recovered'
              ? missedCount != null
                ? `Recovered ${missedCount} events`
                : 'Recovery completed'
              : 'Recovery failed. Please retry.'
        setRecoveryBanner({ status, message })
        if (recoveryTimeoutRef.current) {
          window.clearTimeout(recoveryTimeoutRef.current)
          recoveryTimeoutRef.current = null
        }
        if (status !== 'recovering') {
          recoveryTimeoutRef.current = window.setTimeout(() => {
            setRecoveryBanner(null)
            recoveryTimeoutRef.current = null
          }, 4000)
        }
        return
      }

      if (event.event === 'done') {
        if (isCopilotSurface) {
          setCopilotStatus(null)
        }
        setSessionStatus('completed')
        updateStatusTodo(null)
        setSessionActive(false)
        finalizeActiveMessages('completed')
        if (sessionId) {
          upsertSession(sessionId, {
            status: 'completed',
            updated_at: Math.floor(Date.now() / 1000),
            is_active: false,
          })
        }
        if (reasoningLocksRef.current.size > 0) {
          reasoningLocksRef.current.clear()
          if (!restoringRef.current) {
            flushBufferedEvents()
          }
        }
      }
    },
    [
      appendMessage,
      buildContext,
      canAutoOpenToolPanel,
      finalizeActiveMessages,
      closeAssistantSegment,
      closeReasoningSegment,
      collapseActiveReasoning,
      endDisplayLock,
      flushBufferedEvents,
      getRenamedTitle,
      getReasoningMessageKey,
      handleToolPanelOpen,
      isLiveTool,
      mode,
      pendingRun,
      sessionSurface,
      readOnlyMode,
      replaceMessageById,
      sessionId,
      scheduleReasoningStallCheck,
      shouldBufferEvent,
      setPendingRun,
      startDisplayLock,
      setLastEventId,
      upsertSession,
      updateMessages,
      updateStatusTodo,
      resolveStatusTodoText,
    ]
  )

  useEffect(() => {
    handleEventRef.current = handleEvent
  }, [handleEvent])

  useEffect(() => {
    return () => {
      if (recoveryTimeoutRef.current) {
        window.clearTimeout(recoveryTimeoutRef.current)
        recoveryTimeoutRef.current = null
      }
      if (autoResumeTimerRef.current) {
        window.clearTimeout(autoResumeTimerRef.current)
        autoResumeTimerRef.current = null
      }
      if (sessionQuiescenceReconcileTimerRef.current) {
        window.clearTimeout(sessionQuiescenceReconcileTimerRef.current)
        sessionQuiescenceReconcileTimerRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    if (previousSessionRef.current && previousSessionRef.current !== sessionId) {
      restoredSessionRef.current = null
      restoreRetryRef.current = null
      restoringSessionIdRef.current = null
    }
    previousSessionRef.current = sessionId ?? null
  }, [sessionId])

  useEffect(() => {
    if (!sessionId) {
      restoredSessionRef.current = null
      restoreRetryRef.current = null
      restoringSessionIdRef.current = null
      setIsRestoring(false)
      isRestoringRef.current = false
      setSessionActive(false)
      return
    }
    if (isRestoring && restoringSessionIdRef.current === sessionId) return
    const forceRestore = forceRestoreRef.current
    if (forceRestore) {
      forceRestoreRef.current = false
    }
    const sessionMeta = sessionsRef.current.find((item) => item.session_id === sessionId)
    const hasMessages = messagesRef.current.length > 0
    // Improved: retry restore when no messages are loaded, regardless of sessionMeta availability
    // This fixes the issue where Copilot mode doesn't have sessions list loaded
    const shouldRetry = !hasMessages && restoreRetryRef.current !== sessionId
    if (restoredSessionRef.current === sessionId && !shouldRetry && !forceRestore) return
    restoreRetryRef.current = shouldRetry ? sessionId : null
    restoredSessionRef.current = sessionId
    setRestoreAttempted(true)
    let active = true
    const skipRestore = skipRestoreRef.current
    skipRestoreRef.current = false
    if (skipRestore) {
      debugLog('restore:skip', { sessionId, reason: 'skip_restore_ref' })
      restoringSessionIdRef.current = null
      setIsRestoring(false)
      isRestoringRef.current = false
      if (fullHistoryRequestRef.current) {
        fullHistoryRequestRef.current = false
        setHistoryLoadingFull(false)
      }
      flushRestoreStreamQueue()
      return () => {
        active = false
      }
    }
    restoringSessionIdRef.current = sessionId
    const seededTitle = resolveSessionTitle(sessionMeta ?? null, sessionId)
    const cachedEvents = getCachedSessionEvents(sessionId)
    const cachedEventsSnapshot = cachedEvents ? sortHydratedEvents([...cachedEvents]) : null
    if (cachedEventsSnapshot) {
      replaceCachedSessionEvents(sessionId, cachedEventsSnapshot)
      if (isQuestSessionId(sessionId)) {
        const questResumeToken = resolveQuestResumeToken(cachedEventsSnapshot)
        if (questResumeToken) {
          setLastEventId(sessionId, questResumeToken)
        }
      }
    }
    const hasCachedEvents = Boolean(cachedEventsSnapshot && cachedEventsSnapshot.length > 0)
    debugLog('restore:start', {
      sessionId,
      forceRestore,
      shouldRetry,
      hasMessages,
      hasCachedEvents,
      hasSessionMeta: Boolean(sessionMeta),
      cachedEvents: cachedEventsSnapshot?.length ?? 0,
    })
    resetConversation({ title: seededTitle })
    setIsRestoring(true)
    isRestoringRef.current = true
    if (sessionMeta) {
      const normalizedStatus = normalizeSessionStatus(sessionMeta.status ?? null)
      const nextActive = Boolean(sessionMeta.is_active) || isSessionStatusRunning(normalizedStatus)
      setSessionActive(nextActive)
    }

    if (hasCachedEvents) {
      setRealTime(false)
      realTimeRef.current = false
      restoringRef.current = true
      restoredStatusRef.current = normalizeSessionStatus(sessionMeta?.status ?? null)
      cacheReplayRef.current = true
      try {
        const handler = handleEventRef.current ?? handleEvent
        if (handler) {
          for (const cachedEvent of cachedEventsSnapshot ?? []) {
            try {
              handler(cachedEvent)
            } catch (error) {
              console.warn('[AiManus] Failed to replay cached event', error)
            }
          }
        }
      } finally {
        cacheReplayRef.current = false
        restoringRef.current = false
        restoredStatusRef.current = null
        flushPendingMessages()
        flushRestoreStreamQueue()
      }
      setRealTime(true)
      realTimeRef.current = true

      const replayedSessionMeta = sessionsRef.current.find((item) => item.session_id === sessionId)
      const replayedIsActive =
        typeof replayedSessionMeta?.is_active === 'boolean'
          ? replayedSessionMeta.is_active
          : typeof sessionMeta?.is_active === 'boolean'
            ? sessionMeta.is_active
            : null
      const replayedSessionStatus = replayedSessionMeta?.status ?? sessionMeta?.status ?? null
      const normalizedReplayStatus = normalizeSessionStatus(replayedSessionStatus)
      const statusSuggestsActive =
        Boolean(replayedIsActive) || isSessionStatusActive(normalizedReplayStatus)
      const resumeActive =
        Boolean(replayedIsActive) || isSessionStatusRunning(normalizedReplayStatus)
      const hasInProgressAssistant = messagesRef.current.some((message) => {
        if (message.type !== 'assistant') return false
        return (message.content as MessageContent).status === 'in_progress'
      })
      const hasActiveToolCall = lastNoMessageToolRef.current?.status === 'calling'
      const hasActiveStep = lastStepRef.current?.status === 'running'
      const shouldResume = statusSuggestsActive || hasInProgressAssistant || hasActiveToolCall || hasActiveStep

      if (resumeActive) {
        setSessionActive(true)
      }
      if (shouldResume) {
        void sendMessage({
          sessionId,
          message: '',
          surface: sessionSurface,
          executionTarget: executionTargetRef.current,
          cliServerId: cliServerIdRef.current,
          replayFromLastEvent: true,
        }).catch((error) => {
          console.warn('[AiManus] Failed to resume stream', error)
        })
        const lastTool = lastNoMessageToolRef.current
        if (lastTool && (lastTool.status === 'calling' || isLiveTool(lastTool))) {
          if (canAutoOpenToolPanel(lastTool)) {
            handleToolPanelOpen(lastTool, isLiveTool(lastTool))
          }
        }
      }
      if (isQuestSessionId(sessionId) && !forceRestore && !fullHistoryRequestRef.current) {
        debugLog('restore:skip', { sessionId, reason: 'quest_cache_replay' })
        setIsRestoring(false)
        isRestoringRef.current = false
        if (restoringSessionIdRef.current === sessionId) {
          restoringSessionIdRef.current = null
        }
        return () => {
          active = false
        }
      }
    }

    const restore = async () => {
      virtualizeRestoreRef.current = false
      const startedAt = typeof performance !== 'undefined' ? performance.now() : Date.now()
      let fullHistoryRequest = false
      let wantsFullHistory = false
      try {
        debugLog('restore:fetch', { sessionId })
        if (typeof window !== 'undefined') {
          const apiBaseUrl = getApiBaseUrl()
          const hasUserToken = Boolean(window.localStorage.getItem('ds_access_token'))
          console.info('[CopilotAudit][restore] GET /api/v1/sessions/{id}', {
            sessionId,
            url: `${apiBaseUrl}/api/v1/sessions/${sessionId}`,
            hasUserToken,
          })
        }
        fullHistoryRequest = fullHistoryRequestRef.current
        wantsFullHistory = fullHistoryModeRef.current || fullHistoryRequest
        if (fullHistoryRequest) {
          fullHistoryRequestRef.current = false
        }
        if (isQuestSessionId(sessionId) && !hasCachedEvents) {
          const questEvents = await getQuestSessionEventsOnly(
            sessionId,
            wantsFullHistory ? { full: true } : undefined
          )
          if (!active) return
          const orderedEvents = sortHydratedEvents(questEvents)
          virtualizeRestoreRef.current = orderedEvents.length >= virtualizeThreshold
          setHistoryTruncated(false)
          setHistoryLimit(wantsFullHistory ? null : orderedEvents.length || null)
          const renamed = getRenamedTitle(sessionId)
          resetConversation({ title: renamed || seededTitle })
          setRealTime(false)
          realTimeRef.current = false
          restoringRef.current = true
          restoredStatusRef.current = normalizeSessionStatus(sessionMeta?.status ?? null)
          try {
            replaceCachedSessionEvents(sessionId, orderedEvents)
            if (orderedEvents.length === 0) {
              setLastEventId(sessionId, null)
            } else {
              const questResumeToken = resolveQuestResumeToken(orderedEvents)
              if (questResumeToken) {
                setLastEventId(sessionId, questResumeToken)
              }
            }
            const handler = handleEventRef.current ?? handleEvent
            if (handler) {
              cacheReplayRef.current = true
              try {
                for (const event of orderedEvents) {
                  handler(event)
                }
              } finally {
                cacheReplayRef.current = false
              }
            }
          } finally {
            restoringRef.current = false
            restoredStatusRef.current = null
            flushPendingMessages()
            flushRestoreStreamQueue()
            setRealTime(true)
            realTimeRef.current = true
          }
          const normalizedQuestStatus = normalizeSessionStatus(sessionMeta?.status ?? null)
          const shouldResumeQuest =
            Boolean(sessionMeta?.is_active) || isSessionStatusActive(normalizedQuestStatus)
          if (shouldResumeQuest) {
            void sendMessage({
              sessionId,
              message: '',
              surface: sessionSurface,
              executionTarget: executionTargetRef.current,
              cliServerId: cliServerIdRef.current,
              replayFromLastEvent: true,
            }).catch((error) => {
              console.warn('[AiManus] Failed to resume quest stream', error)
            })
          }
          return
        }
        const session = await getSession(sessionId, wantsFullHistory ? { full: true } : undefined)
        if (!active || !session) {
          if (active) {
            restoredSessionRef.current = null
            // Allow retry if no messages were loaded and restore returned null
            if (!session && messagesRef.current.length === 0) {
              restoreRetryRef.current = null
            }
          }
          return
        }
        const eventCount = Array.isArray(session.events) ? session.events.length : 0
        virtualizeRestoreRef.current = eventCount >= virtualizeThreshold
        const eventsTruncated = Boolean(session.events_truncated)
        const eventLimit =
          typeof session.event_limit === 'number' ? session.event_limit : null
        setHistoryTruncated(eventsTruncated)
        setHistoryLimit(eventLimit)
        if (wantsFullHistory) {
          if (eventsTruncated) {
            fullHistoryModeRef.current = false
            setShowFullHistory(false)
          } else {
            fullHistoryModeRef.current = true
            setShowFullHistory(true)
          }
        }
        syncRuntimeFromSession(session)
        const normalizedSessionStatus = normalizeSessionStatus(session.status ?? null)
        const nextActive =
          Boolean(session.is_active) || isSessionStatusRunning(normalizedSessionStatus)
        if (nextActive) {
          setSessionActive(true)
        }
        console.info('[CopilotAudit][restore] session fetched', {
          sessionId,
          title: session.title ?? null,
          status: session.status ?? null,
          events: session.events?.length ?? 0,
          durationMs: Math.round(
            (typeof performance !== 'undefined' ? performance.now() : Date.now()) - startedAt
          ),
        })
        debugLog('restore:fetched', {
          sessionId,
          title: session.title ?? null,
          status: session.status ?? null,
          events: session.events?.length ?? 0,
        })
        const nextTitle =
          session.title && session.title.trim().length > 0 ? session.title : seededTitle
        const renamed = getRenamedTitle(sessionId)
        if (hasCachedEvents) {
          resetConversation({ title: renamed || nextTitle })
        } else if (session.title) {
          if (!renamed) {
            setTitle(session.title)
          } else {
            setTitle(renamed)
          }
        }
        const sessionPlanHistory = normalizePlanHistory(session.plan_history)
        let derivedPlanHistory: PlanEventData[] = []
        if (sessionPlanHistory.length === 0 && Array.isArray(session.events)) {
          const planEvents = session.events
            .filter((event) => event?.event === 'plan')
            .map((event) => event.data)
          derivedPlanHistory = normalizePlanHistory(planEvents)
        }
        const resolvedPlanHistory =
          sessionPlanHistory.length > 0 ? sessionPlanHistory : derivedPlanHistory
        if (resolvedPlanHistory.length > 0) {
          setPlanHistory(resolvedPlanHistory)
          setPlan(resolvedPlanHistory[resolvedPlanHistory.length - 1])
        }
        setRealTime(false)
        realTimeRef.current = false
        restoringRef.current = true
        restoredStatusRef.current = normalizeSessionStatus(session.status ?? null)
        try {
          const handler = handleEventRef.current ?? handleEvent
          if (handler) {
            const normalizedEvents: AgentSSEEvent[] = []
            const agentIndex = buildSessionAgentIndex(session.agents)
            const sessionMeta =
              session.session_metadata && typeof session.session_metadata === 'object'
                ? (session.session_metadata as Record<string, unknown>)
                : null
            for (const rawEvent of session.events ?? []) {
              const normalized = coerceRestoredEvent(rawEvent)
              if (!normalized) continue
              normalizedEvents.push(hydrateEventMetadata(normalized, sessionMeta, agentIndex))
            }
            const orderedEvents = sortHydratedEvents(normalizedEvents)
            replaceCachedSessionEvents(sessionId, orderedEvents)
            if (orderedEvents.length === 0) {
              setLastEventId(sessionId, null)
            } else if (isQuestSessionId(sessionId)) {
              const questResumeToken = resolveQuestResumeToken(orderedEvents)
              if (questResumeToken) {
                setLastEventId(sessionId, questResumeToken)
              }
            }
            cacheReplayRef.current = true
            try {
              for (const normalized of orderedEvents) {
                try {
                  handler(normalized)
                } catch (error) {
                  console.warn('[AiManus] Failed to restore event', error)
                }
              }
            } finally {
              cacheReplayRef.current = false
            }
          }
        } finally {
          restoringRef.current = false
          restoredStatusRef.current = null
          flushPendingMessages()
          flushRestoreStreamQueue()
        }
        if (nextActive) {
          setSessionActive(true)
        }
        setRealTime(true)
        realTimeRef.current = true
        const shouldResume =
          Boolean(session.is_active) || isSessionStatusActive(normalizedSessionStatus)
        if (shouldResume) {
          void sendMessage({
            sessionId,
            message: '',
            surface: sessionSurface,
            executionTarget: executionTargetRef.current,
            cliServerId: cliServerIdRef.current,
            replayFromLastEvent: true,
          }).catch((error) => {
            console.warn('[AiManus] Failed to resume stream', error)
          })
          const lastTool = lastNoMessageToolRef.current
          if (lastTool && (lastTool.status === 'calling' || isLiveTool(lastTool))) {
            if (canAutoOpenToolPanel(lastTool)) {
              handleToolPanelOpen(lastTool, isLiveTool(lastTool))
            }
          }
        }
      } catch (error) {
        const durationMs = Math.round(
          (typeof performance !== 'undefined' ? performance.now() : Date.now()) - startedAt
        )
        const apiBaseUrl = typeof window !== 'undefined' ? getApiBaseUrl() : null
        const axiosInfo = axios.isAxiosError(error)
          ? {
              status: error.response?.status ?? null,
              statusText: error.response?.statusText ?? null,
              url: typeof error.config?.url === 'string' ? error.config.url : null,
            }
          : null
        console.warn('[CopilotAudit][restore] failed', {
          sessionId,
          apiBaseUrl,
          durationMs,
          axios: axiosInfo,
          message: error instanceof Error ? error.message : String(error),
        })
        console.error('[AiManus] Failed to restore session', error)
        debugLog('restore:error', {
          sessionId,
          message: error instanceof Error ? error.message : String(error),
        })
        if (active) {
          restoredSessionRef.current = null
          // Allow retry on error
          restoreRetryRef.current = null
        }

        // Auto-recover when the stored session id is stale/invalid by falling back to /latest once.
        if (
          active &&
          projectId &&
          axios.isAxiosError(error) &&
          (error.response?.status === 404 || error.response?.status === 403)
        ) {
          const alreadyAttempted =
            restoreFallbackRef.current?.projectId === projectId &&
            restoreFallbackRef.current?.sessionId === sessionId
          if (!alreadyAttempted) {
            restoreFallbackRef.current = { projectId, sessionId }
            if (isQuestRuntimeSurface()) {
              const questSessionId = buildQuestSessionId(projectId)
              console.info('[CopilotAudit][restore] switch to quest session', {
                projectId,
                failedSessionId: sessionId,
                sessionId: questSessionId,
                status: error.response?.status ?? null,
              })
              clearSessionIdForSurface(projectId, sessionSurface)
              setSessionIdForSurface(projectId, sessionSurface, questSessionId)
              if (sessionIdRef.current === questSessionId) {
                requestRestore()
              }
            } else {
              console.info('[CopilotAudit][restore] fallback to product latest session', {
                projectId,
                failedSessionId: sessionId,
                status: error.response?.status ?? null,
                url: `${getApiBaseUrl()}/api/v1/sessions/latest`,
              })
              clearSessionIdForSurface(projectId, sessionSurface)
              try {
                const latest = await getLatestSession(projectId, undefined, sessionSurface)
                syncRuntimeFromSession(latest ?? undefined)
                const latestId = latest?.session_id ?? null
                console.info('[CopilotAudit][restore] fallback latest resolved', {
                  projectId,
                  sessionId: latestId,
                  events: latest?.events?.length ?? 0,
                })
                if (latestId) {
                  setSessionIdForSurface(projectId, sessionSurface, latestId)
                  requestRestore()
                }
              } catch (latestError) {
                console.warn('[CopilotAudit][restore] fallback latest failed', latestError)
              }
            }
          }
        }
      } finally {
        if (active) {
          setIsRestoring(false)
          isRestoringRef.current = false
          if (fullHistoryRequest) {
            setHistoryLoadingFull(false)
          }
          flushRestoreStreamQueue()
          if (restoringSessionIdRef.current === sessionId) {
            restoringSessionIdRef.current = null
          }
          console.info('[CopilotAudit][restore] done', {
            sessionId,
            messages: messagesRef.current.length,
          })
          debugLog('restore:done', { sessionId })
        }
      }
    }

    void restore()

    return () => {
      active = false
      if (restoringSessionIdRef.current === sessionId) {
        restoringSessionIdRef.current = null
        if (restoredSessionRef.current === sessionId) {
          restoredSessionRef.current = null
        }
        restoreRetryRef.current = null
        restoringRef.current = false
        restoredStatusRef.current = null
        setIsRestoring(false)
        isRestoringRef.current = false
      }
    }
  // NOTE: isRestoring and sessions are intentionally excluded from dependencies:
  // - isRestoring: setting it inside this effect would re-trigger the effect, causing
  //   the cleanup function to set active=false and cancel the in-flight restore request.
  // - sessions: we use sessionsRef.current instead, and sessions array reference changes
  //   frequently (e.g., useSessionList sets [] when disabled), which would cancel restore.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    canAutoOpenToolPanel,
    clearSessionIdForSurface,
    debugLog,
    flushPendingMessages,
    flushRestoreStreamQueue,
    handleToolPanelOpen,
    isLiveTool,
    mode,
    projectId,
    resetConversation,
    restoreToken,
    requestRestore,
    sendMessage,
    sessionSurface,
    sessionId,
    setSessionIdForSurface,
    syncRuntimeFromSession,
    virtualizeThreshold,
  ])

  const handleToolClick = (tool: ToolContent) => {
    if (mode !== 'welcome') return
    setRealTime(false)
    realTimeRef.current = false
    handleToolPanelOpen(tool, isLiveTool(tool), true)
  }

  const handleJumpToRealTime = () => {
    setRealTime(true)
    realTimeRef.current = true
    if (lastNoMessageToolRef.current && !isPushFileTool(lastNoMessageToolRef.current)) {
      handleToolPanelOpen(lastNoMessageToolRef.current, isLiveTool(lastNoMessageToolRef.current))
    }
  }

  const handleAttachmentClick = useCallback(
    async (fileId: string) => {
      const node = findNode(fileId)
      if (!node) {
        addToast({
          type: 'error',
          title: 'File not found',
          description: 'The attachment could not be opened.',
        })
        return
      }
      await openFileInTab(node, { customData: projectId ? { projectId } : undefined })
    },
    [addToast, findNode, openFileInTab, projectId]
  )

  const handleRecentFileOpen = useCallback(
    async (path: string) => {
      const normalizedPath = normalizeRecentPath(path)
      if (!normalizedPath) return

      const existing = tabs.find((tab) => {
        if (tab.context?.type !== 'file' && tab.context?.type !== 'notebook') return false
        const resourcePath = tab.context.resourcePath
        if (!resourcePath) return false
        return normalizeRecentPath(resourcePath) === normalizedPath
      })

      if (existing) {
        setActiveTab(existing.id)
        return
      }

      const node = findNodeByPath(normalizedPath)
      if (!node) {
        addToast({
          type: 'error',
          title: 'File not found',
          description: 'The recent file could not be opened.',
        })
        return
      }

      await openFileInTab(node, { customData: projectId ? { projectId } : undefined })
    },
    [addToast, findNodeByPath, openFileInTab, projectId, setActiveTab, tabs]
  )

  const connectionStatus = useMemo(() => {
    if (connection.status === 'rate_limited') return 'Rate limited. Retrying…'
    if (connection.status === 'reconnecting') return 'Reconnecting…'
    if (connection.status === 'error') return connection.error || 'Connection error'
    return null
  }, [connection.error, connection.status])
  const pauseLabel = pauseState?.reason === 'cancelled' ? 'Cancelled' : 'Paused'
  const showPauseBanner = Boolean(pauseState)
  const showCopilotStatus =
    Boolean(copilotStatus) && !pauseState && (!hideCompactMeta || isCopilotSurface)
  const recoveryToneClass =
    recoveryBanner?.status === 'failed'
      ? 'border-[var(--function-error)] bg-[var(--function-error-tsp)] text-[var(--function-error)]'
      : recoveryBanner?.status === 'recovering'
        ? 'border-[var(--function-warning)] bg-[var(--function-warning-tsp)] text-[var(--function-warning)]'
        : 'border-[var(--border-light)] bg-[var(--background-tsp-menu-white)] text-[var(--text-secondary)]'
  const showConnectionStatus = Boolean(connectionStatus) && (!hideCompactMeta || isCopilotSurface)
  const chatPlaceholder = questionPrompt
    ? 'Answer the questions above to continue...'
    : clarifyPrompt
      ? 'Confirm the clarification above to continue...'
      : 'Give DeepScientist a task to work on...'

  const displayMessages = useMemo(() => {
    if (messages.length === 0) return messages
    return messages.filter((message) => {
      if (message.type !== 'tool') return true
      const tool = message.content as ToolContent
      if (tool.status !== 'calling') return true
      const metadata = tool.metadata
      const rawTarget =
        typeof metadata?.execution_target === 'string' ? metadata.execution_target.trim().toLowerCase() : ''
      const isCliToolEvent =
        rawTarget === 'cli' ||
        rawTarget === 'cli_server' ||
        Boolean(metadata?.cli_server_id) ||
        (!rawTarget && executionTarget === 'cli')
      if (!isCliToolEvent) return true
      const functionName = typeof tool.function === 'string' ? tool.function : ''
      const normalizedFunction = normalizeToolFunctionName(functionName)
      const isMcpTool =
        Boolean(getMcpToolKind(functionName)) || normalizedFunction === 'mcp_status_update'
      return isMcpTool
    })
  }, [executionTarget, messages])

  const showLeadMessage =
    Boolean(leadMessage) && restoreAttempted && !isRestoring && !hasHistory
  const decoratedMessages = useMemo<ChatMessageItem[]>(() => {
    if (showLeadMessage && leadMessage) {
      return [leadMessage, ...displayMessages]
    }
    return displayMessages
  }, [displayMessages, leadMessage, showLeadMessage])
  const isVirtualized =
    virtualizeRestoreRef.current || decoratedMessages.length >= virtualizeThreshold
  const visibleMessages = useMemo(() => {
    if (isVirtualized || showFullHistory) return decoratedMessages
    if (decoratedMessages.length <= MAX_RENDERED_MESSAGES) return decoratedMessages
    return decoratedMessages.slice(-MAX_RENDERED_MESSAGES)
  }, [decoratedMessages, isVirtualized, showFullHistory])
  const groupedTurns = useMemo(() => buildChatTurns(visibleMessages), [visibleMessages])
  const thinkingTurn = useMemo<ChatTurn>(() => ({ id: THINKING_TURN_ID, blocks: [] }), [])
  const virtualTurns = useMemo(() => {
    if (!isVirtualized || !showThinking) return groupedTurns
    return [...groupedTurns, thinkingTurn]
  }, [groupedTurns, isVirtualized, showThinking, thinkingTurn])
  const showLoadFullHistory = historyTruncated && Boolean(sessionId)
  const loadFullHistoryTurn = useMemo<ChatTurn>(
    () => ({ id: LOAD_FULL_HISTORY_TURN_ID, blocks: [] }),
    []
  )
  const displayTurns = useMemo(() => {
    const base = isVirtualized ? virtualTurns : groupedTurns
    if (!showLoadFullHistory) return base
    return [loadFullHistoryTurn, ...base]
  }, [groupedTurns, isVirtualized, loadFullHistoryTurn, showLoadFullHistory, virtualTurns])

  useEffect(() => {
    if (!debugEnabled) return
    const tail = visibleMessages.slice(-6).map((item) => {
      const content = item.content as { timestamp?: number }
      const timestamp = typeof content?.timestamp === 'number' ? content.timestamp : 'na'
      const shortId = item.id.length > 8 ? item.id.slice(0, 8) : item.id
      return `${item.type}:${shortId}:${timestamp}`
    })
    debugLog('ui:order', { count: visibleMessages.length, tail })
  }, [debugEnabled, debugLog, visibleMessages])

  const hiddenCount = isVirtualized ? 0 : decoratedMessages.length - visibleMessages.length

  const showTakeover = takeoverActive && Boolean(takeoverSessionId)

  const scheduleListReset = useCallback(
    (index: number) => {
      if (listResetIndexRef.current == null || index < listResetIndexRef.current) {
        listResetIndexRef.current = index
      }
      if (listResetRafRef.current != null) return
      listResetRafRef.current = window.requestAnimationFrame(() => {
        listResetRafRef.current = null
        const resetIndex = listResetIndexRef.current ?? 0
        listResetIndexRef.current = null
        listRef.current?.resetAfterIndex(resetIndex)
      })
    },
    []
  )

  const setItemSize = useCallback(
    (index: number, size: number) => {
      const current = sizeMapRef.current.get(index)
      if (current != null && Math.abs(current - size) < 1) return
      sizeMapRef.current.set(index, size)
      scheduleListReset(index)
    },
    [scheduleListReset]
  )

  const getItemSize = useCallback((index: number) => {
    return sizeMapRef.current.get(index) ?? DEFAULT_MESSAGE_HEIGHT
  }, [])

  useLayoutEffect(() => {
    if (!isVirtualized || !listWrapperRef.current) return
    const update = () => {
      if (!listWrapperRef.current) return
      setListHeight(listWrapperRef.current.clientHeight)
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(listWrapperRef.current)
    return () => observer.disconnect()
  }, [isVirtualized])

  const setHasNewMessagesSafe = useCallback((next: boolean) => {
    if (hasNewMessagesRef.current === next) return
    hasNewMessagesRef.current = next
    setHasNewMessages(next)
  }, [])

  const updateNearBottom = useCallback(
    (container: HTMLDivElement | null) => {
      if (!container) return
      const distance = container.scrollHeight - container.scrollTop - container.clientHeight
      const isNearBottom = distance <= AUTO_FOLLOW_THRESHOLD_PX
      if (isNearBottom !== isNearBottomRef.current) {
        isNearBottomRef.current = isNearBottom
        setIsNearBottom(isNearBottom)
      }
      if (isNearBottom) {
        setHasNewMessagesSafe(false)
      }
    },
    [setHasNewMessagesSafe, setIsNearBottom]
  )

  const handleScroll = useCallback(() => {
    updateNearBottom(scrollRef.current)
  }, [updateNearBottom])

  const handleVirtualScroll = useCallback(() => {
    updateNearBottom(listOuterRef.current)
  }, [updateNearBottom])

  const scrollToBottom = useCallback(
    (behavior: ScrollBehavior = 'auto') => {
      if (messages.length === 0) return
      if (isVirtualized) {
        if (!listRef.current || !listOuterRef.current || listHeight <= 0) return
        if (displayTurns.length === 0) return
        listRef.current.scrollToItem(displayTurns.length - 1, 'end')
        return
      }
      const container = scrollRef.current
      if (!container) return
      container.scrollTo({ top: container.scrollHeight, behavior })
    },
    [displayTurns.length, isVirtualized, listHeight, messages.length]
  )

  const handleJumpToBottom = useCallback(() => {
    scrollToBottom('smooth')
    isNearBottomRef.current = true
    setIsNearBottom(true)
    setHasNewMessagesSafe(false)
  }, [scrollToBottom, setHasNewMessagesSafe, setIsNearBottom])

  const handleLoadFullHistory = useCallback(() => {
    if (!sessionId || historyLoadingFull || isRestoring) return
    fullHistoryRequestRef.current = true
    setHistoryLoadingFull(true)
    requestRestore()
  }, [historyLoadingFull, isRestoring, requestRestore, sessionId])

  useLayoutEffect(() => {
    if (!isVisible) return
    if (messages.length === 0) {
      initialScrollDoneRef.current = false
      lastMessageIdRef.current = null
      setHasNewMessagesSafe(false)
      isNearBottomRef.current = true
      setIsNearBottom(true)
      return
    }
    if (initialScrollDoneRef.current) return
    const canScroll = isVirtualized
      ? Boolean(listRef.current && listOuterRef.current && listHeight > 0)
      : Boolean(scrollRef.current)
    if (!canScroll) return
    scrollToBottom('auto')
    isNearBottomRef.current = true
    setIsNearBottom(true)
    setHasNewMessagesSafe(false)
    initialScrollDoneRef.current = true
  }, [
    isVisible,
    isVirtualized,
    listHeight,
    messages.length,
    scrollToBottom,
    setHasNewMessagesSafe,
    setIsNearBottom,
  ])

  useEffect(() => {
    if (!isVisible) return
    if (!isNearBottomRef.current) return
    if (messages.length === 0) return
    scrollToBottom('auto')
  }, [displayTurns.length, isVisible, messages, scrollToBottom])

  useEffect(() => {
    if (messages.length === 0) return
    const lastId = messages[messages.length - 1]?.id ?? null
    if (!lastId || lastId === lastMessageIdRef.current) return
    lastMessageIdRef.current = lastId
    if (!isVisible || !isNearBottomRef.current) {
      setHasNewMessagesSafe(true)
    }
  }, [isVisible, messages, setHasNewMessagesSafe])

  const isAssistantBlock = useCallback((block: ChatTurnBlock) => {
    if (block.role === 'assistant') return true
    if (block.role === 'user') return false
    const message = block.message
    if (message.type === 'text_delta') {
      return (message.content as MessageContent).role === 'assistant'
    }
    if (message.type === 'attachments' || message.type === 'attachment') {
      return (message.content as AttachmentsContent).role === 'assistant'
    }
    switch (message.type) {
      case 'assistant':
      case 'tool':
      case 'tool_call':
      case 'tool_result':
      case 'reasoning':
      case 'step':
      case 'question_prompt':
      case 'clarify_question':
      case 'patch_review':
        return true
      default:
        return false
    }
  }, [])

  const renderBlock = useCallback(
    (block: ChatTurnBlock, showAssistantHeader = false) => {
      const message = block.message
      const displayKind =
        message.type === 'assistant' ||
        (message.type === 'text_delta' && (message.content as MessageContent).role === 'assistant')
          ? 'assistant'
          : message.type === 'tool' || message.type === 'tool_call' || message.type === 'tool_result'
            ? 'tool'
            : message.type === 'reasoning'
              ? 'reasoning'
              : message.type === 'status'
                ? 'status'
              : null
      const appendActive = appendPendingRef.current.has(block.id)
      const appendOrder = appendActive ? (appendOrderRef.current.get(block.id) ?? 0) : 0
      const appendDelayMs = appendActive
        ? Math.min(appendOrder, APPEND_STAGGER_MAX) * APPEND_STAGGER_MS
        : 0
      const appendStyle = appendActive
        ? ({ '--ds-append-delay': `${appendDelayMs}ms` } as CSSProperties)
        : undefined
      const lockId = displayLockState?.id
      const displayStreaming = Boolean(
        lockId &&
          displayKind &&
          displayLockState?.kind === displayKind &&
          block.sourceIds.includes(lockId)
      )
      const handleDisplayComplete = (payload: { id: string; kind: DisplayLockKind }) => {
        if (displayLockState && displayStreaming && displayLockState.kind === payload.kind) {
          endDisplayLock({ id: displayLockState.id, kind: payload.kind })
          return
        }
        endDisplayLock(payload)
      }
      return (
        <div
          key={block.id}
          className={cn(appendActive && 'ai-manus-append')}
          data-append={appendActive ? 'pending' : undefined}
          style={appendStyle}
          onAnimationEnd={
            appendActive
              ? (event) => {
                  if (!(event.target instanceof HTMLElement)) return
                  if (event.animationName !== 'aiManusFadeIn') return
                  if (!event.target.classList.contains('ai-manus-fade-in')) return
                  markAppendSeen(block.id)
                }
              : undefined
          }
        >
          <ChatMessage
            message={message}
            sessionId={sessionId ?? undefined}
            projectId={projectId ?? undefined}
            readOnly={readOnlyMode}
            showAssistantHeader={showAssistantHeader}
            compact={isCopilotSurface}
            onToolClick={toolPanelEnabled ? handleToolClick : undefined}
            onFileClick={handleAttachmentClick}
            onQuestionPromptSubmit={readOnlyMode ? undefined : handleQuestionSubmit}
            onClarifyQuestionSubmit={readOnlyMode ? undefined : handleClarifySubmit}
            onPatchAccept={readOnlyMode ? undefined : (id) => handlePatchDecision(id, 'accept')}
            onPatchReject={readOnlyMode ? undefined : (id) => handlePatchDecision(id, 'reject')}
            displayStreaming={displayStreaming}
            streamActive={isStreamActive}
            onDisplayComplete={handleDisplayComplete}
          />
        </div>
      )
    },
    [
      handleAttachmentClick,
      handleClarifySubmit,
      handlePatchDecision,
      handleToolClick,
      handleQuestionSubmit,
      isCopilotSurface,
      displayLockState,
      endDisplayLock,
      markAppendSeen,
      readOnlyMode,
      toolPanelEnabled,
      isStreamActive,
    ]
  )

  const renderTurn = useCallback(
    (turn: ChatTurn) => {
      if (turn.id === LOAD_FULL_HISTORY_TURN_ID) {
        const limitLabel =
          typeof historyLimit === 'number' && historyLimit > 0
            ? `Showing latest ${historyLimit} messages.`
            : 'Showing recent messages.'
        const buttonLabel = historyLoadingFull ? 'Loading full history...' : 'Load full history'
        return (
          <div key={turn.id} className="flex w-full justify-center">
            <div
              className={cn(
                'inline-flex max-w-full items-center gap-2 rounded-full border px-3 py-1 font-medium',
                'border-[var(--border-light)] bg-[var(--background-tsp-menu-white)] text-[var(--text-secondary)]',
                isCopilotSurface ? 'text-[12px]' : 'text-[11px]'
              )}
            >
              <span>{limitLabel}</span>
              <button
                type="button"
                onClick={handleLoadFullHistory}
                disabled={historyLoadingFull}
                className="text-[var(--text-primary)] underline decoration-dotted underline-offset-4 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {buttonLabel}
              </button>
            </div>
          </div>
        )
      }
      if (turn.id === THINKING_TURN_ID) {
        return (
          <div key={turn.id} className="flex w-full">
            <ThinkingIndicator compact={isCopilotSurface} />
          </div>
        )
      }
      const firstAssistantIndex = turn.blocks.findIndex((block) => isAssistantBlock(block))
      return (
        <div key={turn.id} className="flex w-full flex-col gap-[12px]">
          {turn.blocks.map((block, index) => renderBlock(block, index === firstAssistantIndex))}
        </div>
      )
    },
    [handleLoadFullHistory, historyLimit, historyLoadingFull, isCopilotSurface, isAssistantBlock, renderBlock]
  )

  const resolveOnlineCliServerId = useCallback(() => {
    if (cliServerId && onlineCliServers.some((server) => server.id === cliServerId)) {
      return cliServerId
    }
    return onlineCliServers[0]?.id ?? null
  }, [cliServerId, onlineCliServers])

  const handleRuntimeSwitch = useCallback(
    (nextTarget: ExecutionTarget, nextCliServerId?: string | null) => {
      if (!projectId) return
      if (runtimeSwitching) return
      if (runtimeLocked) return
      if (labRuntimeLocked && nextTarget !== 'cli') {
        addToast({
          type: 'info',
          title: 'Lab runtime locked',
          description: 'Lab sessions require a CLI server. Switch to Copilot for sandbox mode.',
          duration: 3500,
        })
        return
      }
      if (nextTarget === 'cli' && onlineCliServers.length === 0) {
        addToast({
          type: 'warning',
          title: 'No CLI server online',
          description: 'Connect a CLI server to switch runtime.',
        })
        return
      }
      if (
        nextTarget === 'cli' &&
        nextCliServerId &&
        !onlineCliServers.some((server) => server.id === nextCliServerId)
      ) {
        addToast({
          type: 'warning',
          title: 'CLI server offline',
          description: 'Select an online CLI server to switch runtime.',
        })
        return
      }
      const resolvedCliServerId =
        nextTarget === 'cli' ? nextCliServerId ?? resolveOnlineCliServerId() : null
      if (nextTarget === 'cli' && !resolvedCliServerId) {
        addToast({
          type: 'error',
          title: 'No CLI server available',
          description: 'Bind and connect a CLI server before switching to CLI.',
        })
        return
      }
      setRuntimeSwitching(true)
      const shouldUpdateToolPanelView = mode !== 'welcome'
      if (nextTarget === 'cli') {
        setExecutionTarget(projectId, 'cli', resolvedCliServerId)
        if (shouldUpdateToolPanelView) {
          setToolPanelView('terminal')
        }
        addToast({
          type: 'info',
          title: 'Connected to CLI',
          description: 'Codex will run on the controlled server with real-time streaming.',
          duration: 4000,
        })
      } else {
        setExecutionTarget(projectId, 'sandbox')
        if (shouldUpdateToolPanelView) {
          setToolPanelView('terminal')
        }
        addToast({
          type: 'info',
          title: 'Switched to Sandbox',
          description: 'Terminal is in read-only preview mode.',
          duration: 3000,
        })
      }
      setRuntimeSwitching(false)
    },
    [
      addToast,
      labRuntimeLocked,
      mode,
      onlineCliServers,
      projectId,
      resolveOnlineCliServerId,
      runtimeLocked,
      runtimeSwitching,
      setExecutionTarget,
      setToolPanelView,
    ]
  )

  const handleRuntimeToggle = useCallback(() => {
    if (runtimeLocked) return
    if (runtimeSwitching) return
    if (onlineCliServers.length === 0) {
      if (executionTarget === 'cli') {
        void handleRuntimeSwitch('sandbox')
      }
      return
    }
    const onlineIds = onlineCliServers.map((server) => server.id)
    const activeId = executionTarget === 'cli' ? cliServerId : null
    if (!activeId) {
      void handleRuntimeSwitch('cli', onlineIds[0])
      return
    }
    const currentIndex = onlineIds.indexOf(activeId)
    if (currentIndex < 0) {
      void handleRuntimeSwitch('cli', onlineIds[0])
      return
    }
    if (onlineIds.length === 1) {
      void handleRuntimeSwitch('sandbox')
      return
    }
    const nextIndex = currentIndex + 1
    if (nextIndex >= onlineIds.length) {
      void handleRuntimeSwitch('sandbox')
      return
    }
    void handleRuntimeSwitch('cli', onlineIds[nextIndex])
  }, [cliServerId, executionTarget, handleRuntimeSwitch, onlineCliServers, runtimeLocked, runtimeSwitching])

  const renderRuntimeSelector = useCallback(() => {
    if (!projectId || !hasCliServerSupport) return null
    if (showTerminalRuntimeToggle && mode !== 'welcome') return null
    return (
      <Select
        value={executionTarget === 'cli' && cliServerId ? `cli:${cliServerId}` : 'sandbox'}
        onValueChange={(value) => {
          if (!projectId) return
          if (runtimeLocked) return
          if (value === 'sandbox') {
            void handleRuntimeSwitch('sandbox')
            return
          }
          if (value.startsWith('cli:')) {
            const nextId = value.replace('cli:', '')
            void handleRuntimeSwitch('cli', nextId)
          }
        }}
      >
        <SelectTrigger
          className="ds-copilot-icon-btn justify-center p-0 [&>svg]:hidden"
          aria-label="Runtime"
          data-tooltip={runtimeLabel}
          disabled={runtimeLocked}
        >
          <span className="flex h-4 w-4 items-center justify-center text-current">
            <Server size={16} />
          </span>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="sandbox" disabled={labRuntimeLocked}>
            Sandbox (view-only)
          </SelectItem>
          {cliServers.length === 0 ? (
              <SelectItem value="cli:none" disabled>
                CLI (bind server)
              </SelectItem>
          ) : (
            cliServers.map((server) => {
              const isOnline = server.status !== 'offline' && server.status !== 'error'
              return (
                <SelectItem key={server.id} value={`cli:${server.id}`} disabled={!isOnline}>
                  CLI (interactive): {server.name || server.hostname || server.id.slice(0, 6)}
                  {!isOnline ? ' (offline)' : ''}
                </SelectItem>
              )
            })
          )}
        </SelectContent>
      </Select>
    )
  }, [
    cliServerId,
    cliServers,
    executionTarget,
    handleRuntimeSwitch,
    hasCliServerSupport,
    labRuntimeLocked,
    mode,
    projectId,
    runtimeLabel,
    runtimeLocked,
    showTerminalRuntimeToggle,
  ])

  const handleToolPanelViewChange = useCallback(
    async (nextView: 'tool' | 'terminal') => {
      if (nextView === 'terminal') {
        if (!toolPanelEnabled || !canOpenTerminal) return
        const resolvedSessionId = sessionId ?? (await ensureSession())
        if (!resolvedSessionId) return
        setToolPanelView('terminal')
        setToolPanelOpen(true)
        return
      }
      if (!activeTool) return
      setToolPanelView('tool')
    },
    [activeTool, canOpenTerminal, ensureSession, sessionId, setToolPanelOpen, setToolPanelView, toolPanelEnabled]
  )

  const handleToolPanelResize = useCallback(
    (size: PanelSize) => {
      if (!Number.isFinite(size.asPercentage) || size.asPercentage < TOOL_PANEL_MIN_SIZE) return
      const next = Math.round(size.asPercentage)
      const clamped = Math.min(TOOL_PANEL_MAX_SIZE, Math.max(TOOL_PANEL_MIN_SIZE, next))
      if (clamped === toolPanelSize) return
      setToolPanelSize(clamped)
    },
    [toolPanelSize]
  )

  const handleOpenToolPanel = useCallback(async () => {
    if (!toolPanelEnabled) return
    if (activeTool) {
      handleToolPanelOpen(activeTool, isLiveTool(activeTool), true)
      return
    }
    const lastTool = lastNoMessageToolRef.current
    if (lastTool) {
      handleToolPanelOpen(lastTool, isLiveTool(lastTool), true)
      return
    }
    const resolvedSessionId = sessionId ?? (await ensureSession())
    if (!resolvedSessionId) return
    setToolPanelView('terminal')
    setToolPanelOpen(true)
  }, [
    activeTool,
    ensureSession,
    handleToolPanelOpen,
    isLiveTool,
    sessionId,
    setToolPanelOpen,
    setToolPanelView,
    toolPanelEnabled,
  ])

  useEffect(() => {
    if (!toolPanelEnabled || toolPanelMountReady) return
    const panel = toolPanelRef.current
    if (!panel) return
    const raf = window.requestAnimationFrame(() => {
      try {
        if (showToolPanelInline) {
          panel.expand()
          panel.resize(`${toolPanelSize}%`)
          return
        }
        panel.collapse()
      } catch {
        // Ignore transient unmount/race issues from the panel registry.
      }
    })
    return () => window.cancelAnimationFrame(raf)
  }, [showToolPanelInline, toolPanelEnabled, toolPanelMountReady, toolPanelSize])

  const renderToolPanelToggle = useCallback(() => {
    if (mode !== 'welcome' || !toolToggleVisible) return null
    const label = toolPanelOpenValue ? 'Hide Tool' : 'Open Tool'
    return (
      <button
        type="button"
        onClick={() => {
          if (toolPanelOpenValue) {
            setToolPanelOpen(false)
            return
          }
          void handleOpenToolPanel()
        }}
        aria-label={label}
        data-tooltip={label}
        className={cn('ai-manus-tool-btn', toolPanelOpenValue && 'is-active')}
      >
        {toolPanelOpenValue ? 'Hide Tool' : 'Open Tool'}
      </button>
    )
  }, [handleOpenToolPanel, mode, setToolPanelOpen, toolPanelOpenValue, toolToggleVisible])

  const renderSessionListPanel = useCallback(
    (open: boolean) => (
      <SessionListPanel
        open={open}
        panelId={historyPanelIdValue}
        sessions={visibleSessions}
        activeSessionId={activeSessionIdForList}
        highlightSessionId={highlightSessionId}
        readOnly={sessionListReadOnly}
        pinnedSessionIds={sessionPreferences.pinned}
        renamedSessions={sessionPreferences.renamed}
        onToggle={setHistoryOpenValue}
        onSelect={handleSessionSelect}
        onNew={startNewSession}
        onDelete={handleSessionDelete}
        onTogglePin={handleSessionTogglePin}
        onRename={handleSessionRename}
        onShare={handleSessionShare}
        floating={historyPanelOverlay}
        draggable={historyPanelOverlay}
        dragConstraintsRef={historyOverlayRef}
      />
    ),
    [
      activeSessionIdForList,
      handleSessionDelete,
      handleSessionSelect,
      handleSessionRename,
      handleSessionShare,
      handleSessionTogglePin,
      historyPanelOverlay,
      historyPanelIdValue,
      highlightSessionId,
      sessionListReadOnly,
      sessionPreferences.pinned,
      sessionPreferences.renamed,
      setHistoryOpenValue,
      startNewSession,
      visibleSessions,
    ]
  )

  const renderComposer = (options: {
    compact?: boolean
    rows?: number
    placeholder?: string
    inputRef?: Ref<HTMLTextAreaElement>
    containerClassName?: string
    panelClassName?: string
    inputClassName?: string
  }) => {
    const activeTabViewState = activeTab?.id ? workspaceTabState[activeTab.id] : undefined
    const focusedIssue = activeTab?.id ? workspaceActiveIssues[activeTab.id] : null
    const referenceTray = (
      <CopilotContextTray
        contentKind={activeTabViewState?.contentKind}
        documentMode={activeTabViewState?.documentMode}
        openTabCount={tabs.length}
        references={activeTabReferences}
        activeReferenceId={activeTabReference?.id}
        focusedIssue={focusedIssue}
        onRemoveReference={removeWorkspaceReference}
      />
    )

    if (useNotebookComposer) {
      return (
        <div>
          {referenceTray}
          <NotebookChatBox
            value={inputMessage}
            onChange={setInputMessage}
            onSubmit={handleSubmit}
            onStop={handleStop}
            isRunning={isAgentBusy}
            attachments={attachments}
            onAttachmentsChange={setAttachments}
            recentFiles={recentFiles}
            recentFilesActivePath={activeRecentFilePath}
            recentFilesEnabled={recentFilesEnabled}
            onRecentFilesToggle={handleRecentFilesToggle}
            onRecentFilesRemove={handleRecentFilesRemove}
            showTerminalToggle={showTerminalRuntimeToggle}
            terminalActive={executionTarget === 'cli'}
            terminalLabel={terminalRuntimeLabel}
            onTerminalToggle={handleRuntimeToggle}
            terminalToggleDisabled={terminalRuntimeToggleDisabled}
            onRecentFileOpen={handleRecentFileOpen}
            recentFilesDisabled={!recentFilesAvailable}
            projectId={projectId}
            sessionId={sessionId}
            ensureSession={ensureSession}
            readOnly={readOnlyMode}
            inputDisabled={isRestoring || Boolean(questionPrompt) || Boolean(clarifyPrompt) || cliInputLocked}
            compact={options.compact}
            placeholder={options.placeholder}
            containerClassName={options.containerClassName}
            panelClassName={options.panelClassName}
            inputClassName={options.inputClassName}
            focusRef={composerFocusRef}
          />
        </div>
      )
    }

    return (
      <div>
        {referenceTray}
        <ChatBox
          value={inputMessage}
          onChange={setInputMessage}
          onSubmit={handleSubmit}
          onStop={handleStop}
          isRunning={isAgentBusy}
          mentionables={mentionables}
          mentionEnabled={mentionEnabled}
          lockedPrefix={lockedMentionPrefix}
          lockLeadingMentionSpace={lockLeadingMentionSpace}
          attachments={attachments}
          onAttachmentsChange={setAttachments}
          recentFiles={recentFiles}
          recentFilesActivePath={activeRecentFilePath}
          recentFilesEnabled={recentFilesEnabled}
          onRecentFilesToggle={handleRecentFilesToggle}
          onRecentFilesRemove={handleRecentFilesRemove}
          showTerminalToggle={showTerminalRuntimeToggle}
          terminalActive={executionTarget === 'cli'}
          terminalLabel={terminalRuntimeLabel}
          onTerminalToggle={handleRuntimeToggle}
          terminalToggleDisabled={terminalRuntimeToggleDisabled}
          onRecentFileOpen={handleRecentFileOpen}
          recentFilesDisabled={!recentFilesAvailable}
          projectId={projectId}
          sessionId={sessionId}
          ensureSession={ensureSession}
          readOnly={readOnlyMode}
          inputDisabled={isRestoring || Boolean(questionPrompt) || Boolean(clarifyPrompt) || cliInputLocked}
          compact={options.compact}
          rows={options.rows}
          placeholder={options.placeholder}
          inputRef={options.inputRef}
          containerClassName={options.containerClassName}
          panelClassName={options.panelClassName}
          inputClassName={options.inputClassName}
        />
      </div>
    )
  }

  const chatPanel = (
    <div className="relative flex h-full min-w-0 flex-1 min-h-0 flex-col overflow-hidden">
      {mode === 'welcome' && !embedded ? (
        showIntroCenter ? (
          <div className="ai-manus-surface sticky top-0 z-10 flex items-center justify-between border-b border-[var(--border-light)] px-5 py-2">
            <div className="flex items-center gap-2">
              {historyPanelInline && !historyOpenValue ? (
                <button
                  type="button"
                  onClick={() => setHistoryOpenValue(true)}
                  aria-expanded={historyOpenValue}
                  aria-controls={historyPanelIdValue}
                  className="flex h-7 w-7 items-center justify-center rounded-md hover:bg-[var(--fill-tsp-gray-main)]"
                >
                  <PanelLeft className="h-4 w-4 text-[var(--icon-secondary)]" />
                </button>
              ) : null}
              <img
                src={assetUrl('icons/welcome/copilot-badge.png')}
                alt="Agent logo"
                className="h-6 w-6"
              />
              <span className="text-[11px] font-semibold text-[var(--text-primary)]">Agent</span>
            </div>
            <div className="flex items-center gap-3">
              {renderRuntimeSelector()}
              {renderToolPanelToggle()}
            </div>
          </div>
        ) : (
          <div className="ai-manus-surface sticky top-0 z-10 border-b border-[var(--border-light)] px-5 py-1.5">
            <div className="flex items-center justify-between gap-2">
              <div className="flex flex-1 items-center">
                {historyPanelInline && !historyOpenValue ? (
                  <button
                    type="button"
                    onClick={() => setHistoryOpenValue(true)}
                    aria-expanded={historyOpenValue}
                    aria-controls={historyPanelIdValue}
                    className="flex h-7 w-7 items-center justify-center rounded-md hover:bg-[var(--fill-tsp-gray-main)]"
                  >
                    <PanelLeft className="h-4 w-4 text-[var(--icon-secondary)]" />
                  </button>
                ) : null}
              </div>
              <div className={cn('flex w-full min-w-0 items-center gap-2', messageMaxWidthClass)}>
                <div
                  className={cn(
                    'min-w-0 flex-1 truncate whitespace-nowrap font-medium text-[var(--text-primary)]',
                    isCopilotSurface ? 'text-[12px]' : 'text-[13px]'
                  )}
                >
                  {title}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {mode === 'welcome' && projectId ? renderRuntimeSelector() : null}
                  {renderToolPanelToggle()}
                  {COPILOT_FILES_ENABLED && mode === 'welcome' && sessionId ? (
                    <button
                      type="button"
                      onClick={() => setFileListOpen(true)}
                      className="ds-copilot-icon-btn"
                      aria-label="Session files"
                      data-tooltip="Session files"
                    >
                      <FileSearch size={16} className="text-current" />
                    </button>
                  ) : null}
                </div>
              </div>
              <div className="flex flex-1" />
            </div>
          </div>
        )
      ) : null}

      <LayoutGroup id={composerLayoutGroupId}>
        <div className="relative flex h-full min-h-0 flex-col">
          <div
            className={cn(
              'relative flex flex-1 min-h-0 flex-col overflow-hidden transition-opacity duration-300 ease-out motion-reduce:transition-none',
              mode === 'welcome' && 'bg-transparent',
              hideMessagesForIntro && 'opacity-0 pointer-events-none'
            )}
          >
            {showHistoryOverlay ? (
              <div ref={historyOverlayRef} className="absolute inset-0 z-30 pointer-events-none">
                {renderSessionListPanel(true)}
              </div>
            ) : null}
            {showHistoryLoadingOverlay ? (
              <div className="absolute inset-0 z-20 flex items-center justify-center pointer-events-none">
                <div
                  className={cn(
                    'flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-medium shadow-sm',
                    'border-[var(--border-light)] bg-[var(--background-white-main)] text-[var(--text-tertiary)]'
                  )}
                >
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Loading...</span>
                </div>
              </div>
            ) : null}
            {isVirtualized ? (
              <div
                ref={listWrapperRef}
                className={cn(
                  'relative flex-1 min-h-0 overflow-hidden',
                  listPaddingClass
                )}
              >
                {listHeight > 0 ? (
                  <VariableSizeList
                    ref={listRef}
                    outerRef={listOuterRef}
                    innerRef={listInnerRef}
                    className="ai-manus-scrollbar"
                    height={listHeight}
                    width="100%"
                    itemCount={displayTurns.length}
                    itemSize={getItemSize}
                    innerElementType={ListInnerElement}
                    overscanCount={6}
                    onScroll={handleVirtualScroll}
                    itemData={{
                      items: displayTurns,
                      setSize: setItemSize,
                      render: renderTurn,
                      messageMaxWidthClass,
                    }}
                  >
                    {VirtualTurnRow}
                  </VariableSizeList>
                ) : null}
              </div>
            ) : (
              <div
                ref={scrollRef}
                className={cn(
                  'ai-manus-scrollbar flex-1 min-h-0 overflow-y-auto',
                  listPaddingClass
                )}
                onScroll={handleScroll}
              >
                <div
                  ref={listInnerRef}
                  className={cn(
                    'mx-auto flex w-full flex-col gap-[12px]',
                    listTopPaddingClass,
                    messageMaxWidthClass
                  )}
                  style={{ paddingBottom: listBottomPadding }}
                >
                  {hiddenCount > 0 && !hideCompactMeta && !showLoadFullHistory ? (
                    <div className="text-center text-[11px] text-[var(--text-tertiary)]">
                      Showing the latest {visibleMessages.length} messages
                    </div>
                  ) : null}
                  {suggestions && !suggestionsDisabled && visibleMessages.length === 0 ? (
                    <div className="rounded-[12px] border border-[var(--border-light)] bg-[var(--background-white-main)] p-4">
                      <div
                        className={cn(
                          'font-medium text-[var(--text-primary)]',
                          isCopilotSurface ? 'text-[11px]' : 'text-[11px]'
                        )}
                      >
                        {suggestions.title}
                      </div>
                      {suggestions.subtitle && !hideCompactMeta ? (
                        <div
                          className={cn(
                            'text-[var(--text-tertiary)]',
                            isCopilotSurface ? 'text-[10px]' : 'text-[10px]'
                          )}
                        >
                          {suggestions.subtitle}
                        </div>
                      ) : null}
                      <div className="mt-3 grid gap-2">
                        {suggestions.items.map((item) => (
                          <button
                            key={item.label}
                            type="button"
                            className={cn(
                              'rounded-[8px] border border-[var(--border-light)] px-3 py-2 text-left text-[var(--text-secondary)] hover:bg-[var(--fill-tsp-white-light)]',
                              isCopilotSurface ? 'text-[11px]' : 'text-[11px]'
                            )}
                            onClick={() => onSuggestionSelect?.(item)}
                          >
                            {item.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  {displayTurns.map((turn) => renderTurn(turn))}
                  {showThinking ? <ThinkingIndicator compact={isCopilotSurface} /> : null}
                </div>
              </div>
            )}
            {hasNewMessages ? (
              <div className="pointer-events-none absolute bottom-4 left-1/2 z-10 -translate-x-1/2">
                <button
                  type="button"
                  onClick={handleJumpToBottom}
                  className={cn(
                    'pointer-events-auto inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-medium',
                    'border-[var(--border-main)] bg-[var(--background-white-main)] text-[var(--text-primary)]',
                    'shadow-[0px_8px_20px_-12px_rgba(0,0,0,0.28)] hover:bg-[var(--background-gray-main)]'
                  )}
                >
                  New messages
                  <ArrowDown className="h-3.5 w-3.5" />
                </button>
              </div>
            ) : null}
          </div>

          {showIntro ? (
            <motion.div
              className={cn(
                'absolute inset-0 z-20 flex items-center justify-center pr-5 transition-opacity duration-300 ease-out motion-reduce:transition-none',
                'pl-5',
                showIntroCenter ? 'pointer-events-auto' : 'pointer-events-none'
              )}
              style={
                showHistoryOverlay && historyOverlayPaddingLeft !== null
                  ? { paddingLeft: historyOverlayPaddingLeft }
                  : undefined
              }
              initial={false}
              animate={{
                opacity: showIntroCenter ? 1 : 0,
                y: showIntroCenter ? 0 : 12,
              }}
              transition={introFadeTransition}
            >
              <div className={cn('mx-auto flex w-full flex-col items-center', messageMaxWidthClass)}>
                <motion.div
                  className="pb-6 text-center"
                  initial={false}
                  animate={{
                    opacity: showIntroCenter ? 1 : 0,
                    y: showIntroCenter ? 0 : -6,
                  }}
                  transition={introFadeTransition}
                >
                  <div
                    className={cn(
                      'ai-manus-greeting font-serif text-[var(--text-primary)]',
                      mode === 'copilot'
                        ? 'text-[70px] leading-[85px]'
                        : isCopilotSurface
                          ? 'text-[28px] leading-[34px]'
                          : 'text-[34px] leading-[42px]'
                    )}
                  >
                    {greetingLabel}
                  </div>
                  <div
                    className={cn(
                      'mt-1 text-[var(--text-tertiary)]',
                      isCopilotSurface ? 'text-[13px]' : 'text-[15px]'
                    )}
                  >
                    {introSubtitle}
                  </div>
                </motion.div>
                {showIntroCenter ? (
                  <motion.div
                    layoutId={composerLayoutKey}
                    transition={dropTransition}
                    style={introComposerWidthStyle}
                    className={introComposerWidthClass}
                  >
                    {renderComposer({
                      rows: 3,
                      placeholder: chatPlaceholder,
                      inputRef: composerRef,
                      containerClassName: 'pb-0',
                      inputClassName: cn(
                        'min-h-[56px]',
                        isCopilotSurface ? 'text-[14px]' : 'text-[15px]'
                      ),
                    })}
                  </motion.div>
                ) : null}
                {showWelcomeCards ? (
                  <motion.div
                    className="mt-5 w-[80%] max-w-[820px] min-w-[min(260px,100%)]"
                    initial={false}
                    animate={{
                      opacity: showIntroCenter ? 1 : 0,
                    }}
                    transition={introFadeTransition}
                  >
                    <div className="grid gap-3 sm:grid-cols-3">
                      {welcomeIntroCards.map((card) => {
                        const Icon = card.icon
                        const isSessionsCard = card.title === 'Sessions'
                        const cardInteractive = isSessionsCard && historyPanelInline
                        return (
                          <SpotlightCard
                            key={card.title}
                            role={cardInteractive ? 'button' : undefined}
                            tabIndex={cardInteractive ? 0 : undefined}
                            onClick={cardInteractive ? handleWelcomeSessionsOpen : undefined}
                            onKeyDown={
                              cardInteractive
                                ? (event) => {
                                    if (event.key === 'Enter' || event.key === ' ') {
                                      event.preventDefault()
                                      handleWelcomeSessionsOpen()
                                    }
                                  }
                                : undefined
                            }
                            className={cn(
                              'ai-manus-surface flex h-full min-h-[68px] items-center gap-3 rounded-xl border border-[var(--border-light)] px-3 py-3',
                              'shadow-[0_14px_30px_-28px_rgba(45,42,38,0.45)]',
                              cardInteractive &&
                                'cursor-pointer hover:border-[var(--border-main)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/10'
                            )}
                          >
                            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--fill-tsp-gray-main)]">
                              <Icon className="h-4 w-4 text-[var(--icon-primary)]" />
                            </div>
                            <div className="text-[12px] font-semibold text-[var(--text-primary)]">
                              {card.title}
                            </div>
                          </SpotlightCard>
                        )
                      })}
                    </div>
                  </motion.div>
                ) : null}
              </div>
            </motion.div>
          ) : null}

          <div
            className={cn(
              'relative sticky bottom-0 z-10 flex-shrink-0 overflow-visible',
              mode === 'welcome' && 'bg-transparent',
              composerPaddingClass
            )}
          >
            {plan ? (
              <div
                className={cn(
                  'pointer-events-none absolute inset-x-0 bottom-full flex justify-center',
                  composerGutterClass
                )}
              >
                <div
                  className={cn(
                    dockedComposerWidthClass,
                    'pointer-events-auto flex justify-center -translate-y-2'
                  )}
                  style={dockedComposerWidthStyle}
                >
                  <PlanPanel
                    plan={plan}
                    sessionId={sessionId}
                    compact={isCopilotSurface}
                    history={planHistory}
                  />
                </div>
              </div>
            ) : null}
            {!showIntroCenter ? (
              mode !== 'welcome' ? (
                <div
                  aria-hidden
                  className="pointer-events-none absolute -top-8 left-0 right-0 h-8 bg-gradient-to-t from-[var(--background-gray-main)] to-transparent"
                />
              ) : null
            ) : null}
            {isAgentBusy && !questionPrompt && !clarifyPrompt ? (
              <div
                className={cn(
                  'pointer-events-none absolute top-0 z-10 -translate-y-1/2',
                  orbitOffsetClass
                )}
              >
                <OrbitLogoStatus
                  toolCount={toolCallCount}
                  resetKey={sessionId ?? 'new'}
                  className="shrink-0"
                  size="lg"
                  compact={isCopilotSurface || isCompactView}
                />
              </div>
            ) : null}
            {showPauseBanner ? (
              <div
                className={cn(
                  'mb-2 inline-flex max-w-full items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-medium shadow-[inset_0px_1px_0px_0px_#FFFFFF]',
                  'border-[var(--border-light)] bg-[var(--background-tsp-menu-white)] text-[var(--text-secondary)]',
                  isCopilotSurface ? 'text-[12px]' : 'text-[11px]'
                )}
              >
                <span>{pauseLabel}</span>
                {!readOnlyMode ? (
                  <button
                    type="button"
                    onClick={handleResume}
                    className="text-[var(--text-primary)] underline decoration-dotted underline-offset-4"
                  >
                    Resume
                  </button>
                ) : null}
              </div>
            ) : null}
            {showCopilotStatus && !hideCompactMeta ? (
              <div
                className={cn(
                  'pb-2 text-[var(--text-tertiary)]',
                  isCopilotSurface ? 'text-[12px]' : 'text-[11px]'
                )}
              >
                {copilotStatus}
              </div>
            ) : null}
            {recoveryBanner ? (
              <div
                className={cn(
                  'mb-2 inline-flex max-w-full items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-medium shadow-[inset_0px_1px_0px_0px_#FFFFFF]',
                  recoveryToneClass,
                  isCopilotSurface ? 'text-[12px]' : 'text-[11px]'
                )}
              >
                {recoveryBanner.message}
              </div>
            ) : null}
            {showIntroCenter ? null : introEnabled ? (
              <motion.div
                layoutId={composerLayoutKey}
                transition={dropTransition}
                style={dockedComposerWidthStyle}
                className={dockedComposerWidthClass}
              >
                {renderComposer({
                  compact: isCopilotSurface,
                  placeholder: chatPlaceholder,
                  inputRef: composerRef,
                })}
              </motion.div>
            ) : (
              renderComposer({
                compact: isCopilotSurface,
                placeholder: chatPlaceholder,
                inputRef: composerRef,
              })
            )}
            {!showIntroCenter && composerFooter ? (
              <div className="mt-2 flex items-center justify-end">{composerFooter}</div>
            ) : null}
            {showConnectionStatus ? (
              <div
                className={cn(
                  'mt-2 text-[var(--text-tertiary)]',
                  isCopilotSurface ? 'text-[12px]' : 'text-[11px]'
                )}
              >
                {connectionStatus}
              </div>
            ) : null}
          {readOnlyMode && !hideCompactMeta ? (
            <div className="mt-1 text-[11px] text-[var(--text-tertiary)]">View only</div>
          ) : null}
        </div>
      </div>
    </LayoutGroup>
  </div>
  )

  const toolPanelPortal =
    toolPanelEnabled && toolPanelMountReady && toolPanelMount && toolPanelOpenValue && panelToolContent
      ? createPortal(
          <div className="ai-manus-tool-portal">
            <ToolPanel
              variant="docked"
              open={toolPanelOpenValue}
              toolContent={panelToolContent ?? undefined}
              live={toolPanelLive}
              sessionId={sessionId ?? undefined}
              realTime={realTime}
              isShare={readOnlyMode}
              projectId={projectId ?? undefined}
              executionTarget={executionTarget}
              cliServerId={cliServerId}
              readOnly={readOnlyMode}
              viewMode={toolPanelView}
              onViewModeChange={canOpenTerminal ? handleToolPanelViewChange : undefined}
              onClose={() => {}}
              onJumpToRealTime={handleJumpToRealTime}
              hideClose
            />
          </div>,
          toolPanelMount
        )
      : null

  const sessionListPortal =
    historyPanelInline && sessionListMountReady && sessionListMount
      ? createPortal(
          <div className="ai-manus-session-portal">
            {renderSessionListPanel(historyOpenValue)}
          </div>,
          sessionListMount
        )
      : null
  const scrollState = useMemo(() => ({ isNearBottom }), [isNearBottom])

  return (
    <ChatScrollProvider value={scrollState}>
      <div
        className={cn(
          'ai-manus-root flex h-full w-full min-h-0 min-w-0',
          embedded && 'ai-manus-embedded',
          embedded && 'flex-1',
          mode === 'welcome' ? 'ai-manus-mode-welcome' : 'ai-manus-mode-copilot',
          uiSurface === 'copilot' ? 'ai-manus-copilot' : 'ai-manus-welcome',
          layoutSurface === 'welcome' ? 'flex-row' : 'flex-col'
        )}
      >
        {mode === 'welcome' && historyPanelInline && !sessionListMountReady ? (
          renderSessionListPanel(historyOpenValue)
        ) : null}

        <div
          className={cn(
            'flex min-w-0 flex-1 min-h-0',
            layoutSurface === 'welcome' ? 'flex-row' : 'flex-col'
          )}
        >
          {mode === 'welcome' && toolPanelEnabled && !toolPanelMountReady && showToolPanelInline ? (
            <ResizablePanelGroup className="flex-1 min-h-0 min-w-0">
              <ResizablePanel minSize="38%" className="min-w-0 min-h-0">
                {chatPanel}
              </ResizablePanel>
              <ResizableHandle
                className={cn(
                  'ai-manus-tool-divider pointer-events-none',
                  showToolPanelInline ? 'is-visible' : 'is-hidden'
                )}
              />
              <ResizablePanel
                panelRef={toolPanelRef}
                defaultSize={`${toolPanelSize}%`}
                minSize={`${TOOL_PANEL_MIN_SIZE}%`}
                maxSize={`${TOOL_PANEL_MAX_SIZE}%`}
                collapsible
                collapsedSize={0}
                onResize={handleToolPanelResize}
                className="min-w-0 min-h-0"
              >
                <div
                  className={cn(
                    'ai-manus-tool-dock relative flex h-full min-w-0 flex-1 flex-col overflow-hidden rounded-[10px]',
                    showToolPanelInline ? 'ai-manus-fade-in' : 'pointer-events-none opacity-0'
                  )}
                >
                  <ToolPanel
                    variant="docked"
                    open={toolPanelOpenValue}
                    toolContent={panelToolContent ?? undefined}
                    live={toolPanelLive}
                    sessionId={sessionId ?? undefined}
                    realTime={realTime}
                    isShare={readOnlyMode}
                    projectId={projectId ?? undefined}
                    executionTarget={executionTarget}
                    cliServerId={cliServerId}
                    readOnly={readOnlyMode}
                    viewMode={toolPanelView}
                    onViewModeChange={canOpenTerminal ? handleToolPanelViewChange : undefined}
                    onClose={() => setToolPanelOpen(false)}
                    onJumpToRealTime={handleJumpToRealTime}
                  />
                </div>
              </ResizablePanel>
            </ResizablePanelGroup>
          ) : (
            chatPanel
          )}
        </div>

        <Dialog
          open={renameDialogOpen}
          onOpenChange={(open) => {
            if (open) {
              setRenameDialogOpen(true)
              return
            }
            closeRenameDialog()
          }}
        >
          <DialogContent
            showCloseButton={false}
            className="w-[min(420px,90vw)] !rounded-[18px] !border-[var(--soft-border)] !bg-[var(--soft-bg-surface)] !p-5 text-[var(--soft-text-primary)] shadow-[0px_30px_80px_-40px_rgba(0,0,0,0.32)]"
          >
            <DialogHeader className="space-y-1">
              <DialogTitle className="text-[15px] font-semibold text-[var(--soft-text-primary)]">
                Rename chat
              </DialogTitle>
              <DialogDescription className="text-xs text-[var(--soft-text-tertiary)]">
                Only visible to you.
              </DialogDescription>
            </DialogHeader>
            <div className="pt-3">
              <input
                ref={renameInputRef}
                value={renameDraft}
                onChange={(event) => setRenameDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    commitRenameDialog()
                  } else if (event.key === 'Escape') {
                    event.preventDefault()
                    closeRenameDialog()
                  }
                }}
                maxLength={80}
                className={cn(
                  'h-10 w-full rounded-xl border border-[var(--border-light)] px-3 text-sm',
                  'border-[var(--soft-border)] bg-[var(--soft-bg-base)] text-[var(--soft-text-primary)]',
                  'shadow-[0px_0px_1px_0px_rgba(0,0,0,0.08)]',
                  'focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary)/0.25)]'
                )}
                placeholder="New chat name"
              />
            </div>
            <DialogFooter className="mt-4 flex flex-row justify-end gap-2">
              <button
                type="button"
                onClick={closeRenameDialog}
                className={cn(
                  'inline-flex h-9 items-center justify-center rounded-[10px] px-3 text-sm',
                  'border border-[var(--soft-border)] bg-[var(--soft-bg-surface)] text-[var(--soft-text-primary)]',
                  'hover:bg-[var(--soft-bg-inset)] transition-colors'
                )}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={commitRenameDialog}
                className={cn(
                  'inline-flex h-9 items-center justify-center rounded-[10px] px-3 text-sm font-medium',
                  'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]',
                  'shadow-[0px_10px_24px_-16px_rgba(0,0,0,0.24)] hover:opacity-90 transition'
                )}
              >
                Save
              </button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {COPILOT_FILES_ENABLED ? (
          <SessionFilesDialog
            open={fileListOpen}
            onOpenChange={setFileListOpen}
            files={sessionFiles}
            loading={sessionFilesLoading}
            onOpenFile={handleAttachmentClick}
          />
        ) : null}
        {toolPanelPortal}
        {sessionListPortal}
        {showTakeover ? (
          <div className="fixed inset-0 z-[60] bg-[var(--background-gray-main)]">
            <div className="h-full w-full">
              <VNCViewer sessionId={takeoverSessionId} enabled={showTakeover} viewOnly={false} />
            </div>
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2">
              <button
                type="button"
                onClick={() => {
                  setTakeoverActive(false)
                  setTakeoverSessionId('')
                }}
                className="inline-flex h-[36px] items-center justify-center gap-[6px] rounded-full border-2 border-[var(--border-dark)] bg-[var(--Button-primary-black)] px-[12px] text-sm font-medium text-[var(--text-onblack)] shadow-[0px_8px_32px_0px_rgba(0,0,0,0.32)] transition hover:opacity-90 active:opacity-80"
              >
                Exit Takeover
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </ChatScrollProvider>
  )
}
export default AiManusChatView
