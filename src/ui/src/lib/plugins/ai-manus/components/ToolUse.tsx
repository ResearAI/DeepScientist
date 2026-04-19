'use client'

import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import { ChevronDown } from 'lucide-react'
import type { ToolContent } from '../types'
import {
  extractMcpErrorMessage,
  extractMcpListResult,
  extractMcpReadFileResult,
  getMcpToolKind,
  getMcpToolPath,
} from '../lib/mcp-tools'
import { getToolInfo, resolveToolActorLabel } from '../lib/tool-map'
import { formatRelativeTime } from '../lib/time'
import { decodeHtmlEntities } from '../lib/markdown'
import { LoadingIndicator } from './LoadingIndicator'
import { PatchPreviewPanel } from '@/components/ui/patch-preview-panel'
import RotatingText from '@/components/RotatingText'
import { cn } from '@/lib/utils'
import { redactSensitive, truncateText } from '@/lib/bugbash/sanitize'
import { LabToolCard } from './LabToolCard'
import { useI18n } from '@/lib/i18n/useI18n'

const VOWELS = new Set(['a', 'e', 'i', 'o', 'u'])
const FINAL_REPORT_SECTION_LABEL_KEYS: Record<string, string> = {
  summary: 'detail_final_report_section_summary',
  strengths: 'detail_final_report_section_strengths',
  weaknesses: 'detail_final_report_section_weaknesses',
  key_issues: 'detail_final_report_section_key_issues',
  actionable_suggestions: 'detail_final_report_section_actionable_suggestions',
  storyline_options_writing_outlines: 'detail_final_report_section_storyline_options_writing_outlines',
  priority_revision_plan: 'detail_final_report_section_priority_revision_plan',
  experiment_inventory_research_experiment_plan:
    'detail_final_report_section_experiment_inventory_research_experiment_plan',
  novelty_verification_related_work_matrix:
    'detail_final_report_section_novelty_verification_related_work_matrix',
  scores: 'detail_final_report_section_scores',
  overview_revision_strategy: 'detail_final_report_section_overview_revision_strategy',
  point_to_point_triage_table: 'detail_final_report_section_point_to_point_triage_table',
  evidence_mapping_table: 'detail_final_report_section_evidence_mapping_table',
  draft_responses_to_reviewers: 'detail_final_report_section_draft_responses_to_reviewers',
  manuscript_revision_suggestions: 'detail_final_report_section_manuscript_revision_suggestions',
  optional_experiment_plans: 'detail_final_report_section_optional_experiment_plans',
  unresolved_items_risk_notes: 'detail_final_report_section_unresolved_items_risk_notes',
  references: 'detail_final_report_section_references',
}

type TranslateT = (key: string, variables?: Record<string, string | number>, fallback?: string) => string

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  return value as Record<string, unknown>
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function resolveFinalReportSectionLabel(section: unknown, tWorkspace: TranslateT): string | null {
  if (typeof section === 'string') {
    const normalized = section.trim().toLowerCase()
    if (!normalized) return null
    const labelKey = FINAL_REPORT_SECTION_LABEL_KEYS[normalized]
    if (labelKey) return tWorkspace(labelKey, undefined, section)
    return section.trim()
  }

  const descriptor = asRecord(section)
  const rawId = asString(descriptor.id) || ''
  const normalizedId = rawId.trim().toLowerCase()
  if (normalizedId) {
    const labelKey = FINAL_REPORT_SECTION_LABEL_KEYS[normalizedId]
    if (labelKey) {
      return tWorkspace(labelKey, undefined, asString(descriptor.title) || normalizedId)
    }
  }

  const title = asString(descriptor.title)
  if (title) return title
  if (rawId) return rawId
  return null
}

function compactFinalReportWriteDetail(raw: string | null | undefined): string | null {
  if (!raw) return null
  const normalized = raw.replace(/\s+/g, ' ')
  if (!normalized) return null
  if (normalized.length <= 220) return normalized
  return `${normalized.slice(0, 217).trimEnd()}...`
}

const isDsSystemFunction = (functionName: string) => {
  const normalized = functionName.trim().toLowerCase()
  if (!normalized) return false
  if (normalized.startsWith('ds_system_')) return true
  return normalized.includes('__ds_system_')
}

const splitLeadingVerb = (label: string) => {
  const trimmed = label.trim()
  if (!trimmed) return { verb: '', rest: '' }
  const [verb, ...restParts] = trimmed.split(/\s+/)
  return { verb, rest: restParts.join(' ') }
}

const toEdForm = (word: string) => {
  if (!word) return word
  const lower = word.toLowerCase()
  if (!lower.endsWith('ing')) return word
  const base = lower.slice(0, -3)
  if (!base) return word
  let past = ''
  if (base.endsWith('y')) {
    const beforeY = base[base.length - 2]
    if (beforeY && !VOWELS.has(beforeY)) {
      past = `${base.slice(0, -1)}ied`
    } else {
      past = `${base}ed`
    }
  } else {
    past = `${base}ed`
  }
  if (word[0] === word[0].toUpperCase()) {
    past = past.charAt(0).toUpperCase() + past.slice(1)
  }
  return past
}

export function ToolUse({
  tool,
  onClick,
  compact,
  collapsible,
  projectId,
}: {
  tool: ToolContent
  onClick?: () => void
  compact?: boolean
  collapsible?: boolean
  projectId?: string
}) {
  // Hook safety: decide whether this is a Lab card *before* running any hooks.
  const labToolKind = getMcpToolKind(tool.function || '')
  const isLabSurface =
    typeof tool.metadata?.surface === 'string' && tool.metadata.surface.startsWith('lab-')
  const isLabToolCard =
    labToolKind === 'lab_quests' ||
    labToolKind === 'lab_pi_sleep' ||
    labToolKind === 'lab_baseline' ||
    labToolKind === 'write_memory'
  if (isLabToolCard && isLabSurface) {
    return <LabToolCard tool={tool} compact={compact} projectId={projectId} />
  }
  return (
    <ToolUseDefault
      tool={tool}
      onClick={onClick}
      compact={compact}
      collapsible={collapsible}
      projectId={projectId}
    />
  )
}

function ToolUseDefault({
  tool,
  onClick,
  compact,
  collapsible,
  projectId,
}: {
  tool: ToolContent
  onClick?: () => void
  compact?: boolean
  collapsible?: boolean
  projectId?: string
}) {
  const toolInfo = useMemo(() => getToolInfo(tool), [tool])
  const actorLabel = useMemo(() => resolveToolActorLabel(tool), [tool])
  const { t: tWorkspace } = useI18n('workspace')
  const Icon = toolInfo.icon
  const isCompact = Boolean(compact)
  const [expanded, setExpanded] = useState(false)
  const formatDuration = (value?: number) => {
    if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return ''
    if (value < 1000) return `${Math.round(value)}ms`
    const seconds = value / 1000
    if (seconds >= 60) {
      const minutes = Math.floor(seconds / 60)
      const remainder = Math.round(seconds % 60)
      return `${minutes}m${remainder.toString().padStart(2, '0')}s`
    }
    const precision = seconds >= 10 ? 0 : 1
    return `${seconds.toFixed(precision)}s`
  }
  const formatPayload = (payload: unknown, limit = 1800) => {
    if (payload == null) return ''
    try {
      return truncateText(redactSensitive(JSON.stringify(payload, null, 2)), limit)
    } catch {
      return truncateText(redactSensitive(String(payload)), limit)
    }
  }
  const stringifyValue = (value: unknown) => {
    if (value == null) return ''
    if (typeof value === 'string') return value
    try {
      return JSON.stringify(value, null, 2)
    } catch {
      return String(value)
    }
  }
  const formatListLines = (lines: string[], limit = 40) => {
    if (lines.length === 0) return ''
    const trimmed = lines.slice(0, limit)
    const suffix = lines.length > limit ? `\n... (${lines.length - limit} more)` : ''
    return trimmed.join('\n') + suffix
  }
  const toolArgs =
    tool.args && typeof tool.args === 'object' && !Array.isArray(tool.args)
      ? (tool.args as Record<string, unknown>)
      : {}
  const toolResult = tool.content as Record<string, unknown> | undefined
  const resultPayload = toolResult?.result
  const resultStatus =
    resultPayload && typeof resultPayload === 'object'
      ? typeof (resultPayload as Record<string, unknown>).status === 'string'
        ? String((resultPayload as Record<string, unknown>).status)
        : ''
      : typeof toolResult?.status === 'string'
        ? String(toolResult.status)
        : ''
  const hasFailureFlag =
    typeof toolResult?.success === 'boolean' ? !toolResult.success : false
  const hasError = typeof toolResult?.error === 'string' && toolResult.error.trim().length > 0
  const hasFailedStatus =
    resultStatus.trim().length > 0 &&
    !['ok', 'success', 'completed'].includes(resultStatus.trim().toLowerCase())
  const isFailed = hasError || hasFailureFlag || hasFailedStatus
  const statusTone = 'text-[var(--ds-morandi-red)]'
  const durationLabel = formatDuration(tool.duration_ms)
  const isInteractive =
    toolInfo.category === 'shell' ||
    toolInfo.category === 'bash' ||
    toolInfo.category === 'search' ||
    toolInfo.category === 'paper_search' ||
    toolInfo.category === 'file' ||
    toolInfo.category === 'mcp'
  const statusTextRaw =
    tool.function === 'mcp_status_update'
      ? typeof toolArgs.message === 'string'
        ? toolArgs.message
        : typeof toolArgs.text === 'string'
          ? toolArgs.text
          : ''
      : ''
  const statusText = decodeHtmlEntities(statusTextRaw)
  const statusTodoRaw = tool.function === 'mcp_status_update' ? (toolArgs.todo ?? toolArgs.next) : undefined
  const statusTodoItems = Array.isArray(statusTodoRaw)
    ? statusTodoRaw
    : typeof statusTodoRaw === 'string'
      ? [statusTodoRaw]
      : []
  const statusTodo = statusTodoItems
    .map((item) => decodeHtmlEntities(String(item)).trim())
    .filter(Boolean)
    .join(' / ')
  const statusTodoLine = statusTodo ? `TODO: ${statusTodo}` : ''
  const showActorLabel = toolInfo.category === 'file'
  const labelName = tool.function === 'mcp_status_update' ? 'Status' : toolInfo.name
  const labelFunction =
    tool.function === 'mcp_status_update' && statusText ? statusText : toolInfo.function
  const displayName = showActorLabel ? actorLabel : labelName
  const displayFunction = showActorLabel ? toolInfo.function : labelFunction
  const isDsSystemTool = isDsSystemFunction(tool.function || '')
  const verbSwap = useMemo(() => {
    if (!isDsSystemTool || !displayFunction) return null
    const { verb, rest } = splitLeadingVerb(displayFunction)
    if (!verb || !/ing$/i.test(verb)) return null
    const verbEd = toEdForm(verb)
    if (!verbEd || verbEd === verb) return null
    return { verbIng: verb, verbEd, rest }
  }, [displayFunction, isDsSystemTool])
  const [verbSwapActive, setVerbSwapActive] = useState(false)
  const verbStatusRef = useRef<string | null>(null)
  const didJustComplete =
    Boolean(verbSwap) && tool.status !== 'calling' && verbStatusRef.current === 'calling'

  useEffect(() => {
    if (!verbSwap) return
    const status = tool.status
    if (!status) return
    if (didJustComplete) {
      setVerbSwapActive(true)
    } else if (status === 'calling') {
      setVerbSwapActive(false)
    }
    verbStatusRef.current = status
  }, [didJustComplete, tool.status, verbSwap])

  const shouldAnimateVerb = Boolean(verbSwap) && (verbSwapActive || didJustComplete)
  const verbCurrent = verbSwap
    ? tool.status !== 'calling'
      ? verbSwap.verbEd
      : verbSwap.verbIng
    : ''
  const verbLabel = verbSwap
    ? shouldAnimateVerb
      ? (
        <RotatingText
          texts={[verbSwap.verbIng, verbSwap.verbEd]}
          auto
          loop={false}
          rotationInterval={1200}
          staggerFrom="last"
          staggerDuration={0.02}
          initial={{ y: '90%', opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: '-120%', opacity: 0 }}
          animatePresenceInitial
          maxWords={14}
          mainClassName="ds-copilot-status-text"
          splitLevelClassName="ds-copilot-status-text-split"
          elementLevelClassName="ds-copilot-status-text-element"
          style={{ color: 'inherit', fontWeight: 'inherit' }}
        />
      )
      : verbCurrent
    : displayFunction
  const displayFunctionNode = verbSwap
    ? (
      <>
        {verbLabel}
        {verbSwap.rest ? ` ${verbSwap.rest}` : ''}
      </>
    )
    : displayFunction
  const rawError =
    typeof tool.error === 'string' && tool.error.trim().length > 0
      ? tool.error
      : typeof toolResult?.error === 'string' && toolResult.error.trim().length > 0
        ? toolResult.error
        : ''
  const errorPreview = rawError ? truncateText(redactSensitive(rawError), 240) : ''
  const argsPreview = (() => {
    if (Object.keys(toolArgs).length === 0) return ''
    return formatPayload(toolArgs)
  })()
  const resultPreview = (() => {
    if (!toolResult) return ''
    const payload = toolResult?.result ?? toolResult
    if (typeof payload === 'object' && payload && !Array.isArray(payload) && Object.keys(payload).length === 0) {
      return ''
    }
    return formatPayload(payload)
  })()
  const canShowDetails =
    collapsible !== false && Boolean(argsPreview || resultPreview || errorPreview)
  const detailsOpen = expanded && canShowDetails
  const handleToggleDetails = (event: MouseEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    if (!canShowDetails) return
    setExpanded((value) => !value)
  }
  const statusContent =
    tool.status === 'calling' ? (
      <LoadingIndicator text="Running" compact={isCompact} />
    ) : durationLabel ? (
      <span className={`text-[10px] ${statusTone}`}>{durationLabel}</span>
    ) : null
  const statusLineElement = (
    <div
      onClick={canShowDetails ? handleToggleDetails : undefined}
      className={cn(
        'mt-1 inline-flex min-w-0 max-w-full items-center gap-2 text-[10px] text-[var(--ds-morandi-red)]',
        canShowDetails && 'cursor-pointer text-left transition hover:text-[var(--ds-morandi-red-strong)]'
      )}
      aria-label={canShowDetails ? (expanded ? 'Hide details' : 'Show details') : undefined}
      aria-expanded={canShowDetails ? detailsOpen : undefined}
    >
      {statusContent}
    </div>
  )
  const detailsSection = detailsOpen ? (
    <div className="ai-manus-tool-details mt-2 rounded-[10px] border border-[var(--border-light)] bg-[var(--fill-tsp-white-light)] p-2">
      {errorPreview ? (
        <div className="ai-manus-tool-detail">
          <div className="ai-manus-tool-detail-label text-[10px] text-[var(--soft-danger)]">
            Error
          </div>
          <pre className="ai-manus-tool-detail-body">{errorPreview}</pre>
        </div>
      ) : null}
      {argsPreview ? (
        <div className="ai-manus-tool-detail">
          <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
            Args
          </div>
          <pre className="ai-manus-tool-detail-body">{argsPreview}</pre>
        </div>
      ) : null}
      {resultPreview ? (
        <div className="ai-manus-tool-detail">
          <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
            Result
          </div>
          <pre className="ai-manus-tool-detail-body">{resultPreview}</pre>
        </div>
      ) : null}
    </div>
  ) : null

  const mcpKind = getMcpToolKind(tool.function)
  const isMcpReadFile = mcpKind === 'read_file'
  const isMcpAppendFile = mcpKind === 'append_file'
  const isMcpTaskPlan = mcpKind === 'write_task_plan'
  const isMcpPullFile = mcpKind === 'pull_file'
  const isMcpListFile = mcpKind === 'list_file'
  const isMcpListDir = mcpKind === 'list_dir'
  const isMcpGrepText = mcpKind === 'grep_text'
  const isMcpGrepFiles = mcpKind === 'grep_files'
  const isMcpGlobFiles = mcpKind === 'glob_files'
  const isMcpWriteMemory = mcpKind === 'write_memory'
  const isMcpRequestPatch = mcpKind === 'request_patch'
  const isMcpBashExec = mcpKind === 'bash_exec'
  const isMcpTemplate =
    isMcpReadFile ||
    isMcpAppendFile ||
    isMcpTaskPlan ||
    isMcpPullFile ||
    isMcpListFile ||
    isMcpListDir ||
    isMcpGrepText ||
    isMcpGrepFiles ||
    isMcpGlobFiles ||
    isMcpWriteMemory ||
    isMcpRequestPatch ||
    isMcpBashExec
  const mcpDetailsAvailable =
    !isMcpTaskPlan &&
    (isMcpReadFile ||
      isMcpAppendFile ||
      isMcpPullFile ||
      isMcpListFile ||
      isMcpListDir ||
      isMcpGrepText ||
      isMcpGrepFiles ||
      isMcpGlobFiles ||
      isMcpWriteMemory ||
      isMcpRequestPatch ||
      isMcpBashExec)
  const mcpDetailsEnabled = mcpDetailsAvailable && collapsible !== false
  const mcpPath = getMcpToolPath(toolArgs)
  const mcpTitle = mcpPath || 'a file'
  const mcpDetailTitle = mcpPath || 'Unknown file'
  const mcpReason = typeof toolArgs.reason === 'string' ? toolArgs.reason : ''
  const mcpContent = stringifyValue(toolArgs.content)
  const mcpResultValue = toolResult?.result
  const mcpResultRecord =
    mcpResultValue && typeof mcpResultValue === 'object' && !Array.isArray(mcpResultValue)
      ? (mcpResultValue as Record<string, unknown>)
      : null
  const mcpErrorMessage = extractMcpErrorMessage(mcpResultRecord ?? mcpResultValue) || rawError
  const mcpReadResult = extractMcpReadFileResult(mcpResultValue ?? toolResult)
  const mcpReadText = mcpReadResult.text
  const mcpReadMessage = mcpReadResult.message
  const mcpAppendMessage = (() => {
    if (!mcpResultRecord) return ''
    const message = mcpResultRecord.message
    return typeof message === 'string' ? message : ''
  })()
  const mcpReadError = mcpReadMessage || rawError
  const mcpAppendError = mcpAppendMessage || rawError
  const mcpDetailsHint =
    mcpDetailsEnabled && !statusContent ? (
      <span className="text-[10px] text-[var(--text-tertiary)]">Details</span>
    ) : null
  const mcpPullContent =
    typeof mcpResultValue === 'string'
      ? mcpResultValue
      : mcpResultRecord && typeof mcpResultRecord.content === 'string'
        ? mcpResultRecord.content
        : ''
  const mcpListResult = extractMcpListResult(mcpResultValue ?? toolResult)
  const mcpListItems = mcpListResult.items
  const mcpListLines = formatListLines(
    mcpListItems.map((item) => {
      if (!item || typeof item !== 'object') return String(item)
      const record = item as Record<string, unknown>
      const itemPath =
        typeof record.path === 'string'
          ? record.path
          : typeof record.name === 'string'
            ? record.name
            : 'Unknown'
      const itemType = typeof record.type === 'string' ? record.type : ''
      const itemSize = typeof record.size === 'number' ? `${record.size}b` : ''
      const extra = [itemType, itemSize].filter(Boolean).join(' · ')
      return extra ? `${itemPath} (${extra})` : itemPath
    })
  )
  const mcpListContent = mcpListResult.content
  const mcpListTruncated = mcpListResult.truncated
  const mcpSearchQuery =
    typeof toolArgs.query === 'string'
      ? toolArgs.query
      : mcpResultRecord && typeof mcpResultRecord.query === 'string'
        ? mcpResultRecord.query
        : ''
  const mcpSearchMatches = Array.isArray(mcpResultRecord?.matches) ? (mcpResultRecord?.matches as unknown[]) : []
  const mcpGrepFilesContent =
    mcpResultRecord && typeof mcpResultRecord.content === 'string'
      ? mcpResultRecord.content
      : typeof mcpResultValue === 'string'
        ? mcpResultValue
        : ''
  const mcpGrepFilesLines = formatListLines(
    mcpGrepFilesContent
      ? mcpGrepFilesContent.split(/\r?\n/).filter(Boolean)
      : []
  )
  const mcpSearchLines = formatListLines(
    mcpSearchMatches.map((match) => {
      if (!match || typeof match !== 'object') return String(match)
      const record = match as Record<string, unknown>
      const filePath = typeof record.file_path === 'string' ? record.file_path : 'Unknown'
      const lineNumber = typeof record.line === 'number' ? record.line : undefined
      const text = typeof record.text === 'string' ? record.text : ''
      const head = lineNumber ? `${filePath}:${lineNumber}` : filePath
      return text ? `${head} ${text}` : head
    })
  )
  const mcpSearchFileLines = formatListLines(
    mcpSearchMatches.map((match) => {
      if (!match || typeof match !== 'object') return String(match)
      const record = match as Record<string, unknown>
      const path =
        typeof record.path === 'string'
          ? record.path
          : typeof record.file_path === 'string'
            ? record.file_path
            : 'Unknown'
      const scoreValue =
        typeof record.score === 'number' || typeof record.score === 'string' ? String(record.score) : ''
      const score = scoreValue ? `score ${scoreValue}` : ''
      const size = typeof record.size === 'number' ? `${record.size}b` : ''
      const extra = [score, size].filter(Boolean).join(' · ')
      return extra ? `${path} (${extra})` : path
    })
  )
  const mcpSearchTruncated = Boolean(mcpResultRecord?.truncated)
  const mcpSearchPattern =
    typeof toolArgs.pattern === 'string'
      ? toolArgs.pattern
      : mcpResultRecord && typeof mcpResultRecord.pattern === 'string'
        ? mcpResultRecord.pattern
        : ''
  const mcpMemoryTitle = typeof toolArgs.title === 'string' ? toolArgs.title : ''
  const mcpMemoryKind =
    typeof toolArgs.kind === 'string'
      ? toolArgs.kind
      : mcpResultRecord && typeof mcpResultRecord.kind === 'string'
        ? mcpResultRecord.kind
        : ''
  const mcpMemoryTags = Array.isArray(toolArgs.tags) ? toolArgs.tags.map((tag) => String(tag)) : []
  const mcpMemoryConfidence =
    typeof toolArgs.confidence === 'number' ? toolArgs.confidence : undefined
  const mcpMemoryId = mcpResultRecord && typeof mcpResultRecord.id === 'string' ? mcpResultRecord.id : ''
  const mcpMemoryPath =
    mcpResultRecord && typeof mcpResultRecord.path === 'string' ? mcpResultRecord.path : ''
  const mcpMemoryIndexPath =
    mcpResultRecord && typeof mcpResultRecord.index_path === 'string' ? mcpResultRecord.index_path : ''
  const mcpMemoryWarnings = Array.isArray(mcpResultRecord?.warnings)
    ? (mcpResultRecord?.warnings as unknown[]).map((item) => String(item))
    : []
  const mcpMemoryErrors = Array.isArray(mcpResultRecord?.errors)
    ? (mcpResultRecord?.errors as unknown[]).map((item) => String(item))
    : []
  const mcpPatchTarget =
    typeof toolArgs.target_path === 'string' ? toolArgs.target_path : mcpPath || 'Unknown target'
  const mcpPatchRationale = typeof toolArgs.rationale === 'string' ? toolArgs.rationale : ''
  const mcpPatchBody = typeof toolArgs.patch === 'string' ? toolArgs.patch : ''
  const mcpPatchEvidence = Array.isArray(toolArgs.evidence_refs)
    ? toolArgs.evidence_refs.map((item) => String(item))
    : []
  const mcpPatchApplied = Array.isArray(mcpResultRecord?.applied)
    ? (mcpResultRecord?.applied as unknown[]).map((item) => String(item))
    : []
  const mcpPatchAppliedLines = formatListLines(mcpPatchApplied)
  const mcpBashCommand =
    typeof toolArgs.command === 'string'
      ? toolArgs.command
      : typeof toolArgs.cmd === 'string'
        ? toolArgs.cmd
        : ''
  const mcpBashWorkdir = typeof toolArgs.workdir === 'string' ? toolArgs.workdir : ''
  const mcpBashMode = typeof toolArgs.mode === 'string' ? toolArgs.mode : ''
  const mcpBashTimeout =
    typeof toolArgs.timeout_seconds === 'number'
      ? `${toolArgs.timeout_seconds}s`
      : typeof toolArgs.timeout === 'number'
        ? `${toolArgs.timeout}ms`
        : ''
  const mcpDetailsOpen = expanded && mcpDetailsEnabled
  const handleMcpDetailsToggle = (event: MouseEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    if (!mcpDetailsEnabled) return
    setExpanded((value) => !value)
  }
  const handleMcpChipClick = (event: MouseEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    if (!mcpDetailsEnabled) return
    setExpanded((value) => !value)
    if (onClick) onClick()
  }
  const mcpDetailsSection = mcpDetailsOpen ? (
    <div className="ai-manus-tool-details mt-2 rounded-[10px] border border-[var(--border-light)] bg-[var(--fill-tsp-white-light)] p-2">
      {isMcpReadFile || isMcpAppendFile || isMcpPullFile || isMcpListFile || isMcpListDir ? (
        <div className="ai-manus-tool-detail">
          <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">Title</div>
          <div className="mt-1 text-[11px] text-[var(--text-secondary)]">{mcpDetailTitle}</div>
        </div>
      ) : null}
      {isMcpGrepText ? (
        <div className="ai-manus-tool-detail">
          <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">Query</div>
          <div className="mt-1 text-[11px] text-[var(--text-secondary)]">{mcpSearchQuery || '—'}</div>
        </div>
      ) : null}
      {isMcpGlobFiles || isMcpGrepFiles ? (
        <div className="ai-manus-tool-detail">
          <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">Pattern</div>
          <div className="mt-1 text-[11px] text-[var(--text-secondary)]">{mcpSearchPattern || '—'}</div>
        </div>
      ) : null}
      {isMcpWriteMemory ? (
        <div className="ai-manus-tool-detail">
          <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
            Memory title
          </div>
          <div className="mt-1 text-[11px] text-[var(--text-secondary)]">{mcpMemoryTitle || '—'}</div>
        </div>
      ) : null}
      {isMcpBashExec ? (
        <div className="ai-manus-tool-detail">
          <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
            Command
          </div>
          <pre className="ai-manus-tool-detail-body">{mcpBashCommand || '—'}</pre>
        </div>
      ) : null}
      {isMcpBashExec && mcpBashWorkdir ? (
        <div className="ai-manus-tool-detail">
          <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
            Workdir
          </div>
          <div className="mt-1 text-[11px] text-[var(--text-secondary)]">{mcpBashWorkdir}</div>
        </div>
      ) : null}
      {isMcpBashExec && mcpBashMode ? (
        <div className="ai-manus-tool-detail">
          <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
            Mode
          </div>
          <div className="mt-1 text-[11px] text-[var(--text-secondary)]">{mcpBashMode}</div>
        </div>
      ) : null}
      {isMcpBashExec && mcpBashTimeout ? (
        <div className="ai-manus-tool-detail">
          <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
            Timeout
          </div>
          <div className="mt-1 text-[11px] text-[var(--text-secondary)]">{mcpBashTimeout}</div>
        </div>
      ) : null}
      {isMcpRequestPatch ? (
        <div className="ai-manus-tool-detail">
          <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
            Target path
          </div>
          <div className="mt-1 text-[11px] text-[var(--text-secondary)]">{mcpPatchTarget}</div>
        </div>
      ) : null}
      {isMcpReadFile ? (
        mcpReadError ? (
          <div className="ai-manus-tool-detail">
            <div className="ai-manus-tool-detail-label text-[10px] text-[var(--soft-danger)]">
              Error
            </div>
            <pre className="ai-manus-tool-detail-body text-[var(--soft-danger)]">{mcpReadError}</pre>
          </div>
        ) : (
          <div className="ai-manus-tool-detail">
            <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
              Content
            </div>
            <pre className="ai-manus-tool-detail-body">{mcpReadText}</pre>
          </div>
        )
      ) : null}
      {isMcpAppendFile ? (
        <>
          {mcpAppendError ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--soft-danger)]">
                Error
              </div>
              <pre className="ai-manus-tool-detail-body text-[var(--soft-danger)]">{mcpAppendError}</pre>
            </div>
          ) : null}
          <div className="ai-manus-tool-detail">
            <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
              Reason
            </div>
            <pre className="ai-manus-tool-detail-body">{mcpReason}</pre>
          </div>
          <div className="ai-manus-tool-detail">
            <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
              Content
            </div>
            <pre className="ai-manus-tool-detail-body">{mcpContent}</pre>
          </div>
        </>
      ) : null}
      {isMcpPullFile ? (
        mcpErrorMessage ? (
          <div className="ai-manus-tool-detail">
            <div className="ai-manus-tool-detail-label text-[10px] text-[var(--soft-danger)]">
              Error
            </div>
            <pre className="ai-manus-tool-detail-body text-[var(--soft-danger)]">{mcpErrorMessage}</pre>
          </div>
        ) : (
          <div className="ai-manus-tool-detail">
            <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
              Content
            </div>
            <pre className="ai-manus-tool-detail-body">{mcpPullContent}</pre>
          </div>
        )
      ) : null}
      {isMcpListFile || isMcpListDir ? (
        <>
          {mcpErrorMessage ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--soft-danger)]">
                Error
              </div>
              <pre className="ai-manus-tool-detail-body text-[var(--soft-danger)]">{mcpErrorMessage}</pre>
            </div>
          ) : null}
          <div className="ai-manus-tool-detail">
            <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
              Items
            </div>
            <pre className="ai-manus-tool-detail-body">
              {mcpListContent || mcpListLines || 'No items returned.'}
            </pre>
          </div>
          {mcpListTruncated ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
                Truncated
              </div>
              <div className="mt-1 text-[11px] text-[var(--text-secondary)]">Yes</div>
            </div>
          ) : null}
        </>
      ) : null}
      {isMcpGrepText || isMcpGrepFiles || isMcpGlobFiles ? (
        <>
          {mcpErrorMessage ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--soft-danger)]">
                Error
              </div>
              <pre className="ai-manus-tool-detail-body text-[var(--soft-danger)]">{mcpErrorMessage}</pre>
            </div>
          ) : null}
          <div className="ai-manus-tool-detail">
            <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
              Matches
            </div>
            <pre className="ai-manus-tool-detail-body">
              {(isMcpGrepText
                ? mcpSearchLines
                : isMcpGrepFiles
                  ? mcpGrepFilesLines
                  : mcpSearchFileLines) || 'No matches returned.'}
            </pre>
          </div>
          {mcpSearchTruncated ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
                Truncated
              </div>
              <div className="mt-1 text-[11px] text-[var(--text-secondary)]">Yes</div>
            </div>
          ) : null}
        </>
      ) : null}
      {isMcpWriteMemory ? (
        <>
          {mcpErrorMessage ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--soft-danger)]">
                Error
              </div>
              <pre className="ai-manus-tool-detail-body text-[var(--soft-danger)]">{mcpErrorMessage}</pre>
            </div>
          ) : null}
          {mcpMemoryKind ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
                Kind
              </div>
              <div className="mt-1 text-[11px] text-[var(--text-secondary)]">{mcpMemoryKind}</div>
            </div>
          ) : null}
          {mcpMemoryTags.length > 0 ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
                Tags
              </div>
              <pre className="ai-manus-tool-detail-body">{mcpMemoryTags.join(', ')}</pre>
            </div>
          ) : null}
          {mcpMemoryConfidence != null ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
                Confidence
              </div>
              <div className="mt-1 text-[11px] text-[var(--text-secondary)]">
                {mcpMemoryConfidence}
              </div>
            </div>
          ) : null}
          {mcpMemoryId ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
                Memory ID
              </div>
              <div className="mt-1 text-[11px] text-[var(--text-secondary)]">{mcpMemoryId}</div>
            </div>
          ) : null}
          {mcpMemoryPath ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
                Path
              </div>
              <div className="mt-1 text-[11px] text-[var(--text-secondary)]">{mcpMemoryPath}</div>
            </div>
          ) : null}
          {mcpMemoryIndexPath ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
                Index path
              </div>
              <div className="mt-1 text-[11px] text-[var(--text-secondary)]">{mcpMemoryIndexPath}</div>
            </div>
          ) : null}
          {mcpMemoryWarnings.length > 0 ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
                Warnings
              </div>
              <pre className="ai-manus-tool-detail-body">{mcpMemoryWarnings.join(', ')}</pre>
            </div>
          ) : null}
          {mcpMemoryErrors.length > 0 ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--soft-danger)]">
                Errors
              </div>
              <pre className="ai-manus-tool-detail-body text-[var(--soft-danger)]">
                {mcpMemoryErrors.join(', ')}
              </pre>
            </div>
          ) : null}
        </>
      ) : null}
      {isMcpRequestPatch ? (
        <>
          {mcpErrorMessage ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--soft-danger)]">
                Error
              </div>
              <pre className="ai-manus-tool-detail-body text-[var(--soft-danger)]">{mcpErrorMessage}</pre>
            </div>
          ) : null}
          {mcpPatchRationale ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
                Rationale
              </div>
              <pre className="ai-manus-tool-detail-body">{mcpPatchRationale}</pre>
            </div>
          ) : null}
          {mcpPatchBody ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
                Patch
              </div>
              <PatchPreviewPanel patch={mcpPatchBody} showHeader={false} compact className="mt-1" />
            </div>
          ) : null}
          {mcpPatchEvidence.length > 0 ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
                Evidence refs
              </div>
              <pre className="ai-manus-tool-detail-body">{mcpPatchEvidence.join(', ')}</pre>
            </div>
          ) : null}
          {mcpPatchAppliedLines ? (
            <div className="ai-manus-tool-detail">
              <div className="ai-manus-tool-detail-label text-[10px] text-[var(--text-tertiary)]">
                Applied
              </div>
              <pre className="ai-manus-tool-detail-body">{mcpPatchAppliedLines}</pre>
            </div>
          ) : null}
        </>
      ) : null}
      {isMcpBashExec && mcpErrorMessage ? (
        <div className="ai-manus-tool-detail">
          <div className="ai-manus-tool-detail-label text-[10px] text-[var(--soft-danger)]">
            Error
          </div>
          <pre className="ai-manus-tool-detail-body text-[var(--soft-danger)]">
            {mcpErrorMessage}
          </pre>
        </div>
      ) : null}
    </div>
  ) : null

  const mcpLabel = isMcpReadFile
    ? `DeepScientist is reading ${mcpTitle}...`
    : isMcpAppendFile
      ? `DeepScientist is writing ${mcpTitle}`
      : isMcpPullFile
        ? `DeepScientist is pulling ${mcpTitle}...`
        : isMcpListFile || isMcpListDir
          ? `DeepScientist is listing ${mcpTitle}...`
          : isMcpGrepText
          ? `DeepScientist is grepping for "${mcpSearchQuery || '...'}"...`
          : isMcpGrepFiles
            ? `DeepScientist is finding files for "${mcpSearchPattern || '...'}"...`
            : isMcpGlobFiles
        ? `DeepScientist is matching files for "${mcpSearchPattern || '...'}"...`
        : isMcpWriteMemory
          ? `DeepScientist is saving memory "${mcpMemoryTitle || 'Untitled'}"...`
          : isMcpRequestPatch
              ? `DeepScientist is applying a patch to ${mcpPatchTarget}...`
              : isMcpBashExec
                ? 'DeepScientist is executing a bash command...'
                : 'DeepScientist is planning...'
  const mcpSecondaryLine = isMcpAppendFile ? mcpReason : isMcpBashExec ? mcpBashCommand : ''
  const mcpStatusLineElement = (
    <div
      onClick={mcpDetailsEnabled ? handleMcpDetailsToggle : undefined}
      className={cn(
        'mt-1 inline-flex min-w-0 max-w-full items-center gap-2 text-[10px] text-[var(--text-tertiary)]',
        mcpDetailsEnabled && 'cursor-pointer text-left transition hover:text-[var(--text-secondary)]'
      )}
      aria-label={mcpDetailsEnabled ? (expanded ? 'Hide details' : 'Show details') : undefined}
      aria-expanded={mcpDetailsEnabled ? mcpDetailsOpen : undefined}
    >
      {statusContent}
      {mcpDetailsHint}
    </div>
  )
  const normalizedToolFunction = String(tool.function || '').trim().toLowerCase()
  const normalizedToolName = String(tool.name || '').trim().toLowerCase()
  const isFinalReportWrite =
    normalizedToolFunction === 'review_final_markdown_write' ||
    normalizedToolName === 'review_final_markdown_write' ||
    normalizedToolFunction === 'rebuttal_final_markdown_write' ||
    normalizedToolName === 'rebuttal_final_markdown_write'
  const finalReportWriteProgress = useMemo(() => {
    if (!isFinalReportWrite) return null

    const toolStatus = String(tool.status || '').trim().toLowerCase()
    const content = asRecord(toolResult)
    const nestedResult = asRecord(content.result)
    const normalizedContent = Object.keys(nestedResult).length > 0 ? nestedResult : content
    const resultStatus = String(
      asString(normalizedContent.status) || asString(content.status) || ''
    ).trim().toLowerCase()
    const reason = String(
      asString(normalizedContent.reason) || asString(content.reason) || ''
    ).trim().toLowerCase()
    const retryRequired = normalizedContent.retry_required === true || content.retry_required === true
    const currentSectionLabel =
      resolveFinalReportSectionLabel(normalizedContent.current_section, tWorkspace) ||
      resolveFinalReportSectionLabel(content.current_section, tWorkspace) ||
      resolveFinalReportSectionLabel(asString(toolArgs.section_id) || asString(toolArgs.section), tWorkspace)
    const nextSectionLabel =
      resolveFinalReportSectionLabel(normalizedContent.next_required_section, tWorkspace) ||
      resolveFinalReportSectionLabel(content.next_required_section, tWorkspace)
    const missingSections = Array.isArray(normalizedContent.missing_sections)
      ? normalizedContent.missing_sections
      : Array.isArray(content.missing_sections)
        ? content.missing_sections
        : []
    const missingCount = missingSections.length
    const detail = compactFinalReportWriteDetail(
      asString(normalizedContent.message) ||
        asString(content.message) ||
        asString(normalizedContent.details) ||
        asString(content.details) ||
        asString(normalizedContent.error) ||
        asString(content.error) ||
        (typeof content.result === 'string' ? String(content.result) : '')
    )

    if (toolStatus === 'calling') {
      return {
        headline: currentSectionLabel
          ? tWorkspace('detail_final_report_tool_writing_section', { section: currentSectionLabel })
          : tWorkspace('detail_final_report_tool_writing_generic'),
        detail: null as string | null,
        tone: 'active' as const,
      }
    }

    if (['ok', 'success', 'completed'].includes(resultStatus)) {
      return {
        headline: tWorkspace('detail_final_report_tool_completed'),
        detail,
        tone: 'success' as const,
      }
    }

    if (resultStatus === 'partial' || reason === 'required_sections_missing') {
      return {
        headline: nextSectionLabel
          ? tWorkspace('detail_final_report_tool_partial_next', { section: nextSectionLabel })
          : missingCount > 0
            ? tWorkspace('detail_final_report_tool_partial_generic')
            : tWorkspace('detail_final_report_tool_writing_generic'),
        detail,
        tone: 'active' as const,
      }
    }

    if (
      resultStatus === 'error' ||
      retryRequired ||
      Boolean(asString(normalizedContent.error) || asString(content.error))
    ) {
      const headline =
        reason === 'paper_search_calls_not_met' || reason === 'paper_search_distinct_queries_not_met'
          ? tWorkspace('detail_final_report_tool_gate_paper_search')
          : reason === 'annotation_count_not_met'
            ? tWorkspace('detail_final_report_tool_gate_annotation')
            : tWorkspace('detail_final_report_tool_retry_required')
      return {
        headline,
        detail,
        tone: 'warning' as const,
      }
    }

    if (detail) {
      return {
        headline: detail,
        detail: null as string | null,
        tone: 'active' as const,
      }
    }

    return {
      headline: currentSectionLabel
        ? tWorkspace('detail_final_report_tool_writing_section', { section: currentSectionLabel })
        : tWorkspace('detail_final_report_tool_writing_generic'),
      detail: null as string | null,
      tone: 'active' as const,
    }
  }, [isFinalReportWrite, tWorkspace, tool.status, toolArgs.section, toolArgs.section_id, toolResult])

  if (isMcpTemplate) {
    const chipClasses = cn(
      'ai-manus-tool-chip flex w-full items-start gap-2 rounded-[12px] border border-[var(--border-light)] px-3 py-2 text-left',
      isCompact ? 'text-[10px]' : 'text-[11px]',
      mcpDetailsAvailable
        ? 'bg-[var(--fill-tsp-white-light)] text-[var(--text-secondary)] transition hover:bg-[var(--fill-tsp-gray-dark)]'
        : 'bg-[var(--fill-tsp-white-light)] text-[var(--text-secondary)]'
    )
    const chipContent = (
      <>
        <span className="mt-[2px] inline-flex h-4 w-4 items-center justify-center text-[var(--icon-primary)]">
          <Icon className="h-4 w-4" />
        </span>
        <span className="min-w-0 flex-1 break-words">
          <span
            className={cn(
              'block break-words font-medium text-[var(--text-secondary)]',
              isCompact ? 'text-[10px]' : 'text-[11px]'
            )}
          >
            {mcpLabel}
          </span>
          {mcpSecondaryLine ? (
            <span
              className={cn(
                'mt-0.5 block break-words text-[var(--text-tertiary)]',
                isCompact ? 'text-[9px]' : 'text-[10px]'
              )}
            >
              {mcpSecondaryLine}
            </span>
          ) : null}
        </span>
        {mcpDetailsAvailable ? (
          <ChevronDown
            size={14}
            className={cn(
              'mt-0.5 text-[var(--icon-tertiary)] transition-transform',
              expanded && 'rotate-180'
            )}
          />
        ) : null}
      </>
    )

    return (
      <div
        className="group flex items-start gap-2"
        data-tool-status={
          tool.status === 'calling'
            ? 'calling'
            : tool.status === 'failed'
              ? 'failed'
              : undefined
        }
      >
        <div className="min-w-0 flex-1">
          {mcpDetailsEnabled ? (
            <div
              onClick={handleMcpChipClick}
              className={cn(chipClasses, 'cursor-pointer')}
              aria-label={expanded ? 'Hide details' : 'Show details'}
              aria-expanded={mcpDetailsOpen}
            >
              {chipContent}
            </div>
          ) : (
            <div className={cn(chipClasses, 'cursor-default')}>{chipContent}</div>
          )}
          {mcpStatusLineElement}
          {mcpDetailsSection}
        </div>
        {!isCompact ? (
          <div className="text-[9px] text-[var(--text-tertiary)] opacity-0 transition group-hover:opacity-100">
            {formatRelativeTime(tool.timestamp)}
          </div>
        ) : null}
      </div>
    )
  }

  if (finalReportWriteProgress) {
    const chipClasses = cn(
      'ai-manus-tool-chip flex w-full items-start gap-2 rounded-[12px] border px-3 py-2 text-left',
      isCompact ? 'text-[10px]' : 'text-[11px]',
      finalReportWriteProgress.tone === 'warning'
        ? 'border-[#B86B77]/35 bg-[#B86B77]/10 text-[#8D4C58]'
        : finalReportWriteProgress.tone === 'success'
          ? 'border-[#4F6B5A]/35 bg-[#4F6B5A]/10 text-[#4F6B5A]'
          : 'border-[var(--border-light)] bg-[var(--fill-tsp-white-light)] text-[var(--text-secondary)]'
    )

    return (
      <div
        className="group flex items-start gap-2"
        data-tool-status={
          tool.status === 'calling'
            ? 'calling'
            : tool.status === 'failed'
              ? 'failed'
              : undefined
        }
      >
        <div className="min-w-0 flex-1">
          <div className={chipClasses}>
            <span className="mt-[2px] inline-flex h-4 w-4 items-center justify-center text-[currentColor]">
              <Icon className="h-4 w-4" />
            </span>
            <span className="min-w-0 flex-1 break-words">
              <span
                className={cn(
                  'block break-words font-medium',
                  isCompact ? 'text-[10px]' : 'text-[11px]'
                )}
              >
                {finalReportWriteProgress.headline}
              </span>
              {finalReportWriteProgress.detail ? (
                <span
                  className={cn(
                    'mt-0.5 block break-words opacity-90',
                    isCompact ? 'text-[9px]' : 'text-[10px]'
                  )}
                >
                  {finalReportWriteProgress.detail}
                </span>
              ) : null}
            </span>
          </div>
          {statusLineElement}
          {detailsSection}
        </div>
        {!isCompact ? (
          <div className="text-[9px] text-[var(--text-tertiary)] opacity-0 transition group-hover:opacity-100">
            {formatRelativeTime(tool.timestamp)}
          </div>
        ) : null}
      </div>
    )
  }

  if (tool.name === 'message' && typeof tool.args?.text === 'string') {
    const messageText = decodeHtmlEntities(tool.args.text)
    return (
      <p
        className={
          isCompact
            ? 'text-[11px] text-[var(--text-secondary)]'
            : 'text-[11px] text-[var(--text-secondary)]'
        }
      >
        {messageText}
      </p>
    )
  }

  if (!isInteractive) {
    return (
      <div
        className="group flex items-start gap-2"
        data-tool-status={
          tool.status === 'calling'
            ? 'calling'
            : tool.status === 'failed'
              ? 'failed'
              : undefined
        }
      >
        <div className="min-w-0 flex-1">
          <div
            className={
              isCompact
                ? 'ai-manus-tool-chip inline-flex max-w-full items-center gap-2 text-[10px] text-[var(--text-tertiary)]'
                : 'ai-manus-tool-chip inline-flex max-w-full items-center gap-2 text-[11px] text-[var(--text-tertiary)]'
            }
          >
            <span
              className={
                showActorLabel
                  ? isCompact
                    ? 'shrink-0 text-[9px] font-semibold text-[var(--text-secondary)]'
                  : 'shrink-0 text-[9px] font-semibold text-[var(--text-secondary)]'
                : isCompact
                  ? 'shrink-0 text-[9px] uppercase tracking-wide text-[var(--text-disable)]'
                  : 'shrink-0 text-[9px] uppercase tracking-wide text-[var(--text-disable)]'
              }
            >
              {displayName}
            </span>
            <span
              className={
                tool.function === 'mcp_status_update' ? 'min-w-0 break-words' : 'min-w-0 truncate'
              }
            >
              {displayFunctionNode}
            </span>
          </div>
          {statusTodoLine ? (
            <div className="mt-1 break-words text-[10px] text-[var(--text-tertiary)]">
              {statusTodoLine}
            </div>
          ) : null}
          {statusLineElement}
          {detailsSection}
        </div>
      </div>
    )
  }

  return (
    <div
      className="group flex items-start gap-2"
      data-tool-status={
        tool.status === 'calling'
          ? 'calling'
          : tool.status === 'failed'
            ? 'failed'
            : undefined
      }
    >
      <div className="min-w-0 flex-1">
        <button
          type="button"
          onClick={onClick}
          className={
            isCompact
              ? 'ai-manus-tool-chip inline-flex max-w-full items-center gap-2 rounded-[10px] border border-[var(--border-light)] bg-[var(--fill-tsp-white-light)] px-[10px] py-[3px] text-[11px] text-[var(--text-secondary)] hover:bg-[var(--fill-tsp-gray-dark)]'
              : 'ai-manus-tool-chip inline-flex max-w-full items-center gap-2 rounded-[10px] border border-[var(--border-light)] bg-[var(--fill-tsp-white-light)] px-[10px] py-[3px] text-[11px] text-[var(--text-secondary)] hover:bg-[var(--fill-tsp-gray-dark)]'
          }
        >
          <span className="inline-flex w-[16px] items-center text-[var(--text-primary)]">
            <Icon className="h-4 w-4" />
          </span>
          <span className="flex min-w-0 items-center gap-1">
            {showActorLabel ? (
              <span className={isCompact ? 'truncate text-[10px]' : 'truncate text-[10px]'}>
                {actorLabel} {toolInfo.function}
              </span>
            ) : (
              <span className={isCompact ? 'truncate text-[10px]' : 'truncate text-[10px]'}>
                {toolInfo.function}
              </span>
            )}
            {toolInfo.functionArg ? (
              <code
                className={
                  isCompact
                    ? 'truncate rounded-[6px] bg-[var(--fill-tsp-gray-main)] px-1 text-[10px] text-[var(--text-tertiary)]'
                    : 'truncate rounded-[6px] bg-[var(--fill-tsp-gray-main)] px-1 text-[9px] text-[var(--text-tertiary)]'
                }
              >
                {toolInfo.functionArg}
              </code>
            ) : null}
          </span>
        </button>
        {statusLineElement}
        {detailsSection}
      </div>
      {!isCompact ? (
        <div className="text-[9px] text-[var(--text-tertiary)] opacity-0 transition group-hover:opacity-100">
          {formatRelativeTime(tool.timestamp)}
        </div>
      ) : null}
    </div>
  )
}

export default ToolUse
