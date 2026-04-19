'use client'

import * as React from 'react'
import {
  AlertCircle,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  Database,
  FileCode2,
  GitBranch,
  Globe2,
  Loader2,
  Search,
  Square,
  TerminalSquare,
  Wrench,
} from 'lucide-react'

import { WebSearchQueryPills, WebSearchResults } from '@/components/chat/toolViews/WebSearchCards'
import { deriveMcpIdentity } from '@/lib/mcpIdentity'
import { useI18n } from '@/lib/i18n/useI18n'
import type { RenderOperationFeedItem } from '@/lib/feedOperations'
import { useTabsStore } from '@/lib/stores/tabs'
import { BUILTIN_PLUGINS } from '@/lib/types/plugin'
import { extractFileChangeEntries } from '@/lib/toolOperations'
import { cn } from '@/lib/utils'
import {
  asRecord,
  asString,
  asStringArray,
  extractPathEntries,
  truncateText,
} from '@/components/chat/toolViews/mcp-view-utils'
import {
  normalizeWebSearchPayload,
  type NormalizedWebSearchPayload,
} from '@/components/chat/toolViews/web-search-view-utils'

function formatTime(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function parseStructuredValue(value?: string) {
  if (!value) return null
  try {
    return JSON.parse(value) as unknown
  } catch {
    return null
  }
}

function unwrapToolResult(value: unknown): unknown {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value
  const record = value as Record<string, unknown>
  if (record.structured_content && record.structured_content !== value) {
    return unwrapToolResult(record.structured_content)
  }
  if (record.structured_result && record.structured_result !== value) {
    return unwrapToolResult(record.structured_result)
  }
  if (record.result && record.result !== value) {
    return unwrapToolResult(record.result)
  }
  if (Array.isArray(record.content)) {
    for (const entry of record.content) {
      const contentRecord = asRecord(entry)
      if (!contentRecord) continue
      const nested = unwrapToolResult(contentRecord)
      if (nested && nested !== contentRecord) {
        return nested
      }
      if (typeof contentRecord.text === 'string') {
        const parsedText = parseStructuredValue(contentRecord.text)
        const parsedNested = unwrapToolResult(parsedText)
        if (parsedNested) {
          return parsedNested
        }
      }
    }
  }
  return value
}

function formatFileChangePath(path: string, questId: string) {
  const normalized = String(path || '').trim().replace(/\\/g, '/')
  if (!normalized) return 'Untitled file'
  if (!normalized.startsWith('/')) {
    return normalized
  }
  const worktreeToken = `/quests/${questId}/.ds/worktrees/`
  const questToken = `/quests/${questId}/`
  const worktreeIndex = normalized.indexOf(worktreeToken)
  if (worktreeIndex >= 0) {
    const relative = normalized.slice(worktreeIndex + worktreeToken.length)
    const [worktreeRoot, ...parts] = relative.split('/').filter(Boolean)
    if (worktreeRoot) {
      return parts.length > 0 ? `${worktreeRoot}/${parts.join('/')}` : worktreeRoot
    }
  }
  const questIndex = normalized.indexOf(questToken)
  if (questIndex >= 0) {
    return normalized.slice(questIndex + questToken.length)
  }
  return normalized
}

function formatFileChangeKind(kind?: string) {
  const normalized = String(kind || 'update').trim().toLowerCase()
  if (normalized === 'add' || normalized === 'added' || normalized === 'create' || normalized === 'new') {
    return {
      label: 'Added',
      className:
        'border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:border-emerald-300/20 dark:bg-emerald-300/10 dark:text-emerald-200',
    }
  }
  if (normalized === 'delete' || normalized === 'deleted' || normalized === 'remove' || normalized === 'removed') {
    return {
      label: 'Deleted',
      className:
        'border-rose-500/20 bg-rose-500/10 text-rose-700 dark:border-rose-300/20 dark:bg-rose-300/10 dark:text-rose-200',
    }
  }
  return {
    label: 'Updated',
    className:
      'border-amber-500/20 bg-amber-500/10 text-amber-700 dark:border-amber-300/20 dark:bg-amber-300/10 dark:text-amber-200',
  }
}

type StudioFileChangeEntry = {
  path: string
  displayPath: string
  kind?: string
}

function normalizeStatus(value?: string, active = false) {
  const raw = String(value || '').trim().toLowerCase()
  if (
    raw === 'failed' ||
    raw === 'error' ||
    raw === 'terminated' ||
    raw === 'cancelled'
  ) {
    return {
      label: raw || 'failed',
      Icon: AlertCircle,
      chipClassName:
        'border-rose-500/18 bg-rose-500/10 text-rose-700 dark:border-rose-300/18 dark:bg-rose-300/10 dark:text-rose-200',
      spinning: false,
    }
  }
  if (
    active ||
    raw === 'calling' ||
    raw === 'running' ||
    raw === 'pending' ||
    raw === 'queued' ||
    raw === 'starting'
  ) {
    return {
      label: raw || 'running',
      Icon: Loader2,
      chipClassName:
        'border-black/[0.08] bg-black/[0.04] text-foreground dark:border-white/[0.10] dark:bg-white/[0.06]',
      spinning: true,
    }
  }
  if (raw === 'stopped') {
    return {
      label: raw,
      Icon: Square,
      chipClassName:
        'border-amber-500/18 bg-amber-500/10 text-amber-700 dark:border-amber-300/18 dark:bg-amber-300/10 dark:text-amber-200',
      spinning: false,
    }
  }
  return {
    label: raw || 'completed',
    Icon: CheckCircle2,
    chipClassName:
      'border-emerald-500/18 bg-emerald-500/10 text-emerald-700 dark:border-emerald-300/18 dark:bg-emerald-300/10 dark:text-emerald-200',
    spinning: false,
  }
}

function normalizeComparableText(value?: string | null) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
}

function selectSecondaryText(primaryText: string, candidates: Array<string | null | undefined>) {
  const normalizedPrimary = normalizeComparableText(primaryText)
  for (const candidate of candidates) {
    const value = String(candidate || '').trim()
    if (!value) continue
    if (normalizeComparableText(value) === normalizedPrimary) continue
    return value
  }
  return ''
}

type StudioToolCardModel = {
  label: string
  tooltip: string
  title: string
  subtitle?: string | null
  Icon: React.ComponentType<{ className?: string }>
  accentClassName: string
  statusLabel: string
  statusChipClassName: string
  statusIcon: React.ComponentType<{ className?: string }>
  statusSpinning: boolean
  badges: string[]
  lines: string[]
  paths: Array<{ label: string; path: string }>
  rawArgs?: string
  rawOutput?: string
  webSearch?: NormalizedWebSearchPayload | null
  fileChanges?: StudioFileChangeEntry[]
}

function extractArtifactRecord(resultRecord: Record<string, unknown> | null) {
  const direct = asRecord(resultRecord?.record)
  if (direct) return direct
  const artifact = asRecord(resultRecord?.artifact)
  return asRecord(artifact?.record) ?? artifact
}

function summarizeMetricEntries(value: unknown) {
  const record = asRecord(value)
  if (!record) return []
  return Object.entries(record)
    .filter(([, metricValue]) => metricValue != null && metricValue !== '')
    .slice(0, 4)
    .map(([metricKey, metricValue]) => `${metricKey}: ${String(metricValue)}`)
}

function buildArtifactModel(item: RenderOperationFeedItem): StudioToolCardModel {
  const active = item.label === 'tool_call'
  const tool = item.mcpTool || deriveMcpIdentity(item.toolName, item.mcpServer, item.mcpTool).tool || 'artifact'
  const args = asRecord(parseStructuredValue(item.args))
  const resultRecord = asRecord(unwrapToolResult(parseStructuredValue(item.output)))
  const artifactRecord = extractArtifactRecord(resultRecord)
  const interactionRecord = asRecord(resultRecord?.interaction)
  const titleMap: Record<string, string> = {
    record: active ? 'Recording artifact' : 'Recorded artifact',
    checkpoint: active ? 'Creating checkpoint' : 'Created checkpoint',
    prepare_branch: active ? 'Preparing branch' : 'Prepared branch',
    activate_branch: active ? 'Activating branch' : 'Activated branch',
    publish_baseline: active ? 'Publishing baseline' : 'Published baseline',
    attach_baseline: active ? 'Attaching baseline' : 'Attached baseline',
    confirm_baseline: active ? 'Confirming baseline' : 'Confirmed baseline',
    waive_baseline: active ? 'Waiving baseline' : 'Waived baseline',
    submit_idea: active ? 'Submitting idea' : 'Submitted idea',
    record_main_experiment: active ? 'Recording main experiment' : 'Recorded main experiment',
    create_analysis_campaign: active ? 'Creating analysis campaign' : 'Created analysis campaign',
    record_analysis_slice: active ? 'Recording analysis slice' : 'Recorded analysis slice',
    arxiv: active ? 'Reading arXiv paper' : 'Read arXiv paper',
    refresh_summary: active ? 'Refreshing summary' : 'Refreshed summary',
    render_git_graph: active ? 'Rendering git graph' : 'Rendered git graph',
    interact: active ? 'Sending interaction' : 'Sent interaction',
  }

  const paperTitle = asString(resultRecord?.title)
  const baselineId =
    asString(asRecord(resultRecord?.attachment)?.source_baseline_id) ||
    asString(asRecord(asRecord(resultRecord?.attachment)?.entry)?.baseline_id) ||
    asString(resultRecord?.baseline_id) ||
    asString(args?.baseline_id)
  const branch =
    asString(resultRecord?.branch) ||
    asString(asRecord(resultRecord?.graph)?.branch) ||
    asString(asRecord(resultRecord?.branch_record)?.branch) ||
    asString(args?.branch)
  const worktreeRoot = asString(resultRecord?.worktree_root)
  const ideaId = asString(resultRecord?.idea_id)
  const latestMainRunId = asString(resultRecord?.latest_main_run_id)
  const nextAnchor = asString(resultRecord?.next_anchor)
  const workspaceMode = asString(resultRecord?.workspace_mode)
  const interactionReplyMode =
    asString(tool === 'interact' ? resultRecord?.reply_mode : interactionRecord?.reply_mode)
  const interactionOpenRequestCount =
    tool === 'interact' ? resultRecord?.open_request_count : interactionRecord?.open_request_count
  const deliveryTargets = asStringArray(
    tool === 'interact' ? resultRecord?.delivery_targets : interactionRecord?.delivery_targets
  )
  const title =
    tool === 'activate_branch'
      ? [active ? 'Activating' : 'Activated', branch || 'branch'].filter(Boolean).join(' ')
      : paperTitle ||
        asString(resultRecord?.summary) ||
        asString(resultRecord?.guidance) ||
        asString(artifactRecord?.summary) ||
        asString(artifactRecord?.reason) ||
        asString(resultRecord?.agent_instruction) ||
        item.subject ||
        titleMap[tool] ||
        'Artifact update'
  const subtitle =
    tool === 'arxiv'
      ? [
          asString(resultRecord?.paper_id) || asString(args?.paper_id),
          asString(resultRecord?.content_mode),
          asString(resultRecord?.source),
        ]
          .filter(Boolean)
          .join(' · ')
      : tool === 'attach_baseline' || tool === 'confirm_baseline' || tool === 'waive_baseline'
        ? [baselineId, asString(resultRecord?.variant_id), asString(resultRecord?.status)]
            .filter(Boolean)
            .join(' · ')
        : tool === 'activate_branch'
          ? [
              workspaceMode ? `${workspaceMode} workspace` : '',
              ideaId ? `idea ${ideaId}` : '',
              nextAnchor ? `next: ${nextAnchor}` : '',
              deliveryTargets.length > 0 ? 'connector notified' : '',
            ]
              .filter(Boolean)
              .join(' · ')
        : tool === 'prepare_branch'
          ? [branch, worktreeRoot].filter(Boolean).join(' · ')
          : asString(resultRecord?.reason) ||
            asString(resultRecord?.summary) ||
            asString(resultRecord?.guidance) ||
            asString(artifactRecord?.summary) ||
            asString(artifactRecord?.guidance) ||
            null

  const lines = [
    ...summarizeMetricEntries(resultRecord?.metrics_summary),
    ...summarizeMetricEntries(artifactRecord?.metrics_summary),
    ...(tool === 'interact' || interactionRecord
      ? [
          interactionReplyMode
            ? `reply mode: ${interactionReplyMode}`
            : '',
          typeof interactionOpenRequestCount === 'number'
            ? `open requests: ${String(interactionOpenRequestCount)}`
            : '',
          ...deliveryTargets.slice(0, 2).map((target) => `delivered to: ${target}`),
        ]
      : []),
    ...(tool === 'arxiv' && asString(resultRecord?.content)
      ? [truncateText(String(resultRecord?.content), 220)]
      : []),
    ...(tool === 'activate_branch'
      ? [
          ideaId ? `active idea: ${ideaId}` : '',
          latestMainRunId ? `latest main run: ${latestMainRunId}` : '',
          nextAnchor ? `next anchor: ${nextAnchor}` : '',
          workspaceMode ? `workspace mode: ${workspaceMode}` : '',
          typeof resultRecord?.promote_to_head === 'boolean'
            ? `promoted to head: ${resultRecord.promote_to_head ? 'yes' : 'no'}`
            : '',
          typeof resultRecord?.worktree_created === 'boolean'
            ? `worktree created: ${resultRecord.worktree_created ? 'yes' : 'no'}`
            : '',
        ].filter(Boolean)
      : []),
    ...(branch ? [`branch: ${branch}`] : []),
    ...(worktreeRoot ? [`worktree: ${worktreeRoot}`] : []),
    ...(baselineId ? [`baseline: ${baselineId}`] : []),
  ].filter(Boolean) as string[]

  const badges = [
    tool,
    asString(resultRecord?.status) || item.status || '',
    asString(artifactRecord?.kind) || '',
  ].filter(Boolean) as string[]

  return {
    label: 'artifact',
    tooltip: tool,
    title: truncateText(title, 180),
    subtitle: subtitle ? truncateText(subtitle, 200) : null,
    Icon: tool === 'arxiv' ? BrainCircuit : GitBranch,
    accentClassName: 'bg-[rgba(186,160,140,0.12)] text-[#8c7240] dark:bg-[rgba(186,160,140,0.14)]',
    statusLabel: normalizeStatus(item.status, active).label,
    statusChipClassName: normalizeStatus(item.status, active).chipClassName,
    statusIcon: normalizeStatus(item.status, active).Icon,
    statusSpinning: normalizeStatus(item.status, active).spinning,
    badges,
    lines,
    paths: extractPathEntries(resultRecord ?? artifactRecord ?? args),
    rawArgs: item.args,
    rawOutput: item.output,
    webSearch: null,
  }
}

function buildMemoryModel(item: RenderOperationFeedItem): StudioToolCardModel {
  const active = item.label === 'tool_call'
  const tool = item.mcpTool || deriveMcpIdentity(item.toolName, item.mcpServer, item.mcpTool).tool || 'memory'
  const args = asRecord(parseStructuredValue(item.args))
  const resultRecord = asRecord(unwrapToolResult(parseStructuredValue(item.output)))
  const memoryCard = asRecord(resultRecord?.record) ?? resultRecord
  const items = Array.isArray(resultRecord?.items)
    ? resultRecord.items.map((entry) => asRecord(entry)).filter(Boolean)
    : []
  const count =
    typeof resultRecord?.count === 'number'
      ? resultRecord.count
      : items.length
  const query = asString(args?.query) || asString(resultRecord?.query)
  const titleMap: Record<string, string> = {
    write: active ? 'Saving memory' : 'Saved memory',
    read: active ? 'Reading memory' : 'Loaded memory',
    search: active ? 'Searching memory' : 'Searched memory',
    list_recent: active ? 'Loading recent memory' : 'Loaded recent memory',
    promote_to_global: active ? 'Promoting memory' : 'Promoted memory',
  }
  const title =
    query ||
    asString(memoryCard?.title) ||
    asString(args?.title) ||
    item.subject ||
    titleMap[tool] ||
    'Memory update'
  const subtitle =
    tool === 'search'
      ? [query, typeof count === 'number' ? `${count} results` : ''].filter(Boolean).join(' · ')
      : tool === 'list_recent'
        ? typeof count === 'number'
          ? `${count} recent cards`
          : 'Recent project memory'
        : [
            asString(memoryCard?.type) || asString(memoryCard?.kind) || asString(args?.kind),
            asString(memoryCard?.scope) || asString(args?.scope),
          ]
            .filter(Boolean)
            .join(' · ')
  const lines = (
    tool === 'search' || tool === 'list_recent'
      ? items.slice(0, 3).map((entry, index) => {
          const titleText =
            asString(entry?.title) ||
            asString(entry?.id) ||
            `Memory ${index + 1}`
          const excerpt = asString(entry?.excerpt)
          return excerpt ? `${titleText}: ${truncateText(excerpt, 120)}` : titleText
        })
      : [
          asString(memoryCard?.excerpt) || asString(memoryCard?.body) || '',
          ...asStringArray(asRecord(memoryCard?.metadata)?.tags)
            .slice(0, 3)
            .map((tag) => `#${tag}`),
        ]
  ).filter(Boolean) as string[]

  const badges = [
    tool,
    typeof count === 'number' && (tool === 'search' || tool === 'list_recent') ? `${count} results` : '',
    asString(memoryCard?.type) || asString(memoryCard?.kind) || '',
    asString(memoryCard?.scope) || '',
  ].filter(Boolean) as string[]

  return {
    label: 'memory',
    tooltip: tool,
    title: truncateText(title, 180),
    subtitle: subtitle ? truncateText(subtitle, 200) : null,
    Icon: tool === 'search' ? Search : Database,
    accentClassName: 'bg-[rgba(139,164,149,0.12)] text-[#66816f] dark:bg-[rgba(139,164,149,0.14)]',
    statusLabel: normalizeStatus(item.status, active).label,
    statusChipClassName: normalizeStatus(item.status, active).chipClassName,
    statusIcon: normalizeStatus(item.status, active).Icon,
    statusSpinning: normalizeStatus(item.status, active).spinning,
    badges,
    lines,
    paths: extractPathEntries(resultRecord ?? memoryCard ?? args),
    rawArgs: item.args,
    rawOutput: item.output,
    webSearch: null,
  }
}

function buildFileChangeModel(item: RenderOperationFeedItem, questId: string): StudioToolCardModel {
  const active = item.label === 'tool_call'
  const entries = extractFileChangeEntries(parseStructuredValue(item.args), parseStructuredValue(item.output))
  const deduped = new Map<string, StudioFileChangeEntry>()
  for (const entry of entries) {
    const normalizedPath = String(entry.path || '').trim()
    if (!normalizedPath) continue
    const key = `${normalizedPath}:${entry.kind || ''}`
    if (!deduped.has(key)) {
      deduped.set(key, {
        path: normalizedPath,
        displayPath: formatFileChangePath(normalizedPath, questId),
        kind: entry.kind,
      })
    }
  }
  const fileChanges = Array.from(deduped.values())
  const title =
    fileChanges.length === 0
      ? active
        ? 'Updating files'
        : item.subject || 'Updated files'
      : fileChanges.length === 1
        ? `${active ? 'Updating' : 'Updated'} ${fileChanges[0].displayPath}`
        : `${active ? 'Updating' : 'Updated'} ${fileChanges.length || 0} files`
  const subtitle =
    fileChanges.length > 1
      ? `${fileChanges.length} file changes recorded`
      : fileChanges.length === 1
        ? `${formatFileChangeKind(fileChanges[0].kind).label} file`
        : null

  return {
    label: 'code edit',
    tooltip: 'file_change',
    title,
    subtitle,
    Icon: FileCode2,
    accentClassName: 'bg-[rgba(151,164,179,0.16)] text-[var(--text-primary)] dark:bg-[rgba(231,223,210,0.08)]',
    statusLabel: normalizeStatus(item.status, active).label,
    statusChipClassName: normalizeStatus(item.status, active).chipClassName,
    statusIcon: normalizeStatus(item.status, active).Icon,
    statusSpinning: normalizeStatus(item.status, active).spinning,
    badges: ['file_change', fileChanges.length > 0 ? `${fileChanges.length} files` : ''].filter(Boolean) as string[],
    lines: [],
    paths: [],
    rawArgs: item.args,
    rawOutput: item.output,
    webSearch: null,
    fileChanges,
  }
}

function buildBashModel(item: RenderOperationFeedItem): StudioToolCardModel {
  const active = item.label === 'tool_call'
  const args = asRecord(parseStructuredValue(item.args))
  const resultRecord = asRecord(unwrapToolResult(parseStructuredValue(item.output)))
  const mode = asString(resultRecord?.mode) || asString(args?.mode)
  const command =
    asString(args?.command) ||
    asString(args?.cmd) ||
    asString(resultRecord?.command) ||
    asString(item.metadata?.command) ||
    item.subject ||
    'bash command'
  const workdir = asString(args?.workdir) || asString(item.metadata?.workdir)
  const bashId = asString(resultRecord?.bash_id) || asString(item.metadata?.bash_id)
  const logPath = asString(resultRecord?.log_path) || asString(item.metadata?.log_path)
  const listItems = Array.isArray(resultRecord?.items)
    ? resultRecord.items.map((entry) => asRecord(entry)).filter(Boolean)
    : []
  const historyLines = asStringArray(resultRecord?.lines)
  const listCount =
    typeof resultRecord?.count === 'number'
      ? resultRecord.count
      : listItems.length
  const title =
    mode === 'list'
      ? active
        ? 'Checking background terminals'
        : 'Checked background terminals'
      : mode === 'history'
        ? active
          ? 'Reading terminal history'
          : 'Read terminal history'
        : `${active ? 'Running' : 'Ran'} ${truncateText(command, 180)}`
  const subtitle =
    mode === 'list'
      ? [typeof listCount === 'number' ? `${listCount} sessions` : '', workdir].filter(Boolean).join(' · ') || null
      : mode === 'history'
        ? [typeof resultRecord?.count === 'number' ? `${resultRecord.count} entries` : '', asString(args?.comment)]
            .filter(Boolean)
            .join(' · ') || null
        : workdir
          ? truncateText(workdir, 160)
          : null
  const lines =
    mode === 'list'
      ? listItems.slice(0, 3).map((entry) => {
          const statusText = asString(entry?.status)
          const sessionCommand = truncateText(asString(entry?.command) || asString(entry?.id) || 'bash session', 140)
          return [statusText, sessionCommand].filter(Boolean).join(' · ')
        })
      : mode === 'history'
        ? historyLines.slice(0, 3).map((line) => truncateText(line, 180))
        : ([
            workdir ? `workdir: ${workdir}` : '',
            bashId ? `bash id: ${bashId}` : '',
            typeof resultRecord?.exit_code === 'number' ? `exit code: ${String(resultRecord?.exit_code)}` : '',
            resultRecord?.last_progress != null ? truncateText(JSON.stringify(resultRecord.last_progress), 160) : '',
            asString(resultRecord?.stop_reason) ? `stop: ${String(resultRecord?.stop_reason)}` : '',
          ].filter(Boolean) as string[])

  return {
    label: 'bash exec',
    tooltip: 'bash_exec',
    title,
    subtitle,
    Icon: TerminalSquare,
    accentClassName: 'bg-[rgba(151,164,179,0.14)] text-[var(--text-primary)] dark:bg-[rgba(231,223,210,0.08)]',
    statusLabel: normalizeStatus(
      asString(resultRecord?.status) || item.status,
      active
    ).label,
    statusChipClassName: normalizeStatus(
      asString(resultRecord?.status) || item.status,
      active
    ).chipClassName,
    statusIcon: normalizeStatus(
      asString(resultRecord?.status) || item.status,
      active
    ).Icon,
    statusSpinning: normalizeStatus(
      asString(resultRecord?.status) || item.status,
      active
    ).spinning,
    badges: ['bash_exec', mode || ''].filter(Boolean) as string[],
    lines,
    paths: logPath ? [{ label: 'log', path: logPath }] : [],
    rawArgs: item.args,
    rawOutput: item.output,
    webSearch: null,
  }
}

function buildWebSearchModel(item: RenderOperationFeedItem): StudioToolCardModel {
  const active = item.label === 'tool_call'
  const payload = normalizeWebSearchPayload({
    args: parseStructuredValue(item.args),
    metadataSearch: item.metadata?.search,
    output: item.output,
    fallbackQuery: item.subject || '',
  })
  const query = payload.query || item.subject || 'web search'
  const countLabel = payload.results.length > 0 ? `${payload.results.length} results` : ''
  const queryCountLabel = payload.queries.length > 1 ? `${payload.queries.length} queries` : ''
  const subtitle = [payload.actionType, countLabel, queryCountLabel].filter(Boolean).join(' · ')

  return {
    label: 'web search',
    tooltip: 'web_search',
    title: truncateText(`${active ? 'Searching' : 'Searched'} ${query}`, 180),
    subtitle: subtitle || null,
    Icon: Globe2,
    accentClassName: 'bg-[rgba(121,145,182,0.12)] text-[#58779f] dark:bg-[rgba(121,145,182,0.14)]',
    statusLabel: normalizeStatus(item.status, active).label,
    statusChipClassName: normalizeStatus(item.status, active).chipClassName,
    statusIcon: normalizeStatus(item.status, active).Icon,
    statusSpinning: normalizeStatus(item.status, active).spinning,
    badges: ['web_search', countLabel].filter(Boolean) as string[],
    lines: [
      payload.summary ? truncateText(payload.summary, 180) : '',
      ...payload.queries.slice(1, 3).map((entry) => truncateText(entry, 120)),
    ].filter(Boolean),
    paths: [],
    rawArgs: item.args,
    rawOutput: item.output,
    webSearch: payload,
  }
}

function buildGenericModel(item: RenderOperationFeedItem): StudioToolCardModel {
  const active = item.label === 'tool_call'
  return {
    label: item.toolName || 'tool',
    tooltip: item.toolName || 'tool',
    title: truncateText(
      item.subject ||
        item.content ||
        `${active ? 'Calling' : 'Used'} ${item.toolName || 'tool'}`,
      180
    ),
    subtitle: item.toolName && item.subject ? truncateText(item.toolName, 120) : null,
    Icon: Wrench,
    accentClassName: 'bg-black/[0.05] text-foreground dark:bg-white/[0.06]',
    statusLabel: normalizeStatus(item.status, active).label,
    statusChipClassName: normalizeStatus(item.status, active).chipClassName,
    statusIcon: normalizeStatus(item.status, active).Icon,
    statusSpinning: normalizeStatus(item.status, active).spinning,
    badges: [item.toolName || 'tool'].filter(Boolean) as string[],
    lines: [
      item.content ? truncateText(item.content, 160) : '',
      item.subject ? truncateText(item.subject, 160) : '',
    ].filter(Boolean) as string[],
    paths: [],
    rawArgs: item.args,
    rawOutput: item.output,
    webSearch: null,
  }
}

function buildToolCardModel(item: RenderOperationFeedItem, questId: string) {
  const toolName = String(item.toolName || '').trim().toLowerCase()
  if (toolName === 'file_change') {
    return buildFileChangeModel(item, questId)
  }
  const resolvedIdentity = deriveMcpIdentity(item.toolName, item.mcpServer, item.mcpTool)
  if (resolvedIdentity.server === 'artifact') {
    return buildArtifactModel(item)
  }
  if (resolvedIdentity.server === 'memory') {
    return buildMemoryModel(item)
  }
  if (resolvedIdentity.server === 'bash_exec') {
    return buildBashModel(item)
  }
  if ((item.toolName || '').trim().toLowerCase() === 'web_search') {
    return buildWebSearchModel(item)
  }
  return buildGenericModel(item)
}

function InlinePathList({ paths }: { paths: Array<{ label: string; path: string }> }) {
  if (paths.length === 0) return null
  return (
    <div className="space-y-1.5 text-[11px] leading-5 text-muted-foreground">
      {paths.slice(0, 3).map((entry) => (
        <div key={`${entry.label}:${entry.path}`} className="break-all">
          <span className="font-medium text-foreground">{entry.label}:</span> {entry.path}
        </div>
      ))}
    </div>
  )
}

function FallbackOutput({ value }: { value?: string }) {
  if (!value?.trim()) return null
  return (
    <pre className="feed-scrollbar max-h-[240px] max-w-full overflow-x-hidden overflow-y-auto whitespace-pre-wrap break-words [overflow-wrap:anywhere] rounded-[16px] bg-black/[0.03] px-3 py-3 text-[11px] leading-6 text-muted-foreground dark:bg-white/[0.05]">
      {value}
    </pre>
  )
}

function ToolCommentPanel({
  summary,
  whyNow,
  next,
}: {
  summary?: string | null
  whyNow?: string | null
  next?: string | null
}) {
  const { t } = useI18n('workspace')
  const entries = [
    summary ? { label: t('copilot_trace_summary'), value: summary } : null,
    whyNow ? { label: t('copilot_trace_why_now'), value: whyNow } : null,
    next ? { label: t('copilot_trace_next'), value: next } : null,
  ].filter(Boolean) as Array<{ label: string; value: string }>

  if (entries.length === 0) return null

  return (
    <div className="border-l-2 border-black/[0.08] pl-3 text-[11px] leading-5 text-muted-foreground dark:border-white/[0.10]">
      <div className="space-y-1">
        {entries.map((entry) => (
          <div key={entry.label} className="break-words [overflow-wrap:anywhere]">
            <span className="font-medium text-foreground">{entry.label}:</span> {entry.value}
          </div>
        ))}
      </div>
    </div>
  )
}

function StudioWebSearchPanel({
  payload,
  isSearching,
}: {
  payload: NormalizedWebSearchPayload
  isSearching: boolean
}) {
  const { t } = useI18n('workspace')
  return (
    <div className="space-y-2.5">
      {payload.queries.length > 0 ? (
        <div className="space-y-1.5">
          <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
            {t('copilot_trace_queries')}
          </div>
          <WebSearchQueryPills queries={payload.queries} activeQuery={payload.query} compact />
        </div>
      ) : null}

      {payload.summary ? (
        <div className="rounded-[14px] border border-black/[0.06] bg-white/[0.68] px-3 py-2.5 text-[12px] leading-5 text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.03]">
          {payload.summary}
        </div>
      ) : null}

      <WebSearchResults
        payload={payload}
        compact
        maxItems={5}
        emptyMessage={
          isSearching
            ? t('copilot_trace_searching_web', undefined, 'Searching the web...')
            : payload.queries.length > 0
              ? t('copilot_trace_no_search_cards', undefined, 'No structured result cards were returned for this search.')
              : t('copilot_trace_no_search_results', undefined, 'No search results.')
        }
      />
    </div>
  )
}

function StudioFileChangePanel({
  questId,
  item,
  entries,
}: {
  questId: string
  item: RenderOperationFeedItem
  entries: StudioFileChangeEntry[]
}) {
  const { t } = useI18n('workspace')
  const openTab = useTabsStore((state) => state.openTab)
  const canOpenDiff = Boolean(questId && item.runId)

  const handleOpenDiff = React.useCallback(
    (entry: StudioFileChangeEntry) => {
      if (!questId || !item.runId) return
      openTab({
        pluginId: BUILTIN_PLUGINS.GIT_DIFF_VIEWER,
        context: {
          type: 'custom',
          customData: {
            resolver: 'file_change',
            projectId: questId,
            runId: item.runId,
            eventId: item.eventId || null,
            queryPath: entry.path,
            displayPath: entry.displayPath,
            initialMode: 'diff',
            allowSnapshot: false,
            allowDiff: true,
          },
        },
        title: entry.displayPath,
      })
    },
    [item.eventId, item.runId, openTab, questId]
  )

  if (entries.length === 0) {
    return (
      <div className="text-[12px] leading-6 text-muted-foreground">
        {t('copilot_trace_no_file_changes', undefined, 'No structured file changes were recorded for this edit.')}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {entries.map((entry) => {
        const kindMeta = formatFileChangeKind(entry.kind)
        return (
          <div
            key={`${entry.path}:${entry.kind || ''}`}
            className="flex flex-wrap items-center gap-2 border-l-2 border-black/[0.08] py-1 pl-3 dark:border-white/[0.10]"
          >
            <span
              className={cn(
                'inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.08em]',
                kindMeta.className
              )}
            >
              {kindMeta.label}
            </span>
            <div className="min-w-0 flex-1 break-all text-[12px] leading-6 text-foreground">
              {entry.displayPath}
            </div>
            <button
              type="button"
              disabled={!canOpenDiff}
              onClick={() => handleOpenDiff(entry)}
              className="inline-flex h-7 items-center rounded-md border border-black/[0.08] bg-white/[0.86] px-2.5 text-[11px] font-medium text-foreground transition hover:bg-black/[0.03] disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/[0.10] dark:bg-white/[0.04] dark:hover:bg-white/[0.08]"
            >
              {t('copilot_trace_open_diff', undefined, 'Open Diff')}
            </button>
          </div>
        )
      })}
    </div>
  )
}

export function StudioToolCard({
  questId,
  item,
  isLatest = false,
}: {
  questId: string
  item: RenderOperationFeedItem
  isLatest?: boolean
}) {
  const model = React.useMemo(() => buildToolCardModel(item, questId), [item, questId])
  const identity = React.useMemo(() => deriveMcpIdentity(item.toolName, item.mcpServer, item.mcpTool), [item.mcpServer, item.mcpTool, item.toolName])
  const [expanded, setExpanded] = React.useState(() => isLatest)
  const expandModeRef = React.useRef<'auto' | 'manual-open' | 'manual-close'>('auto')
  const StatusIcon = model.statusIcon
  const fallbackOutput = model.rawOutput?.trim() || ''
  const commentPreview =
    item.comment?.summary?.trim() ||
    item.comment?.whyNow?.trim() ||
    item.comment?.next?.trim() ||
    ''
  const commentSummary = item.comment?.summary?.trim() || ''
  const commentWhyNow = item.comment?.whyNow?.trim() || ''
  const commentNext = item.comment?.next?.trim() || ''
  const showSubtitle = Boolean(model.subtitle && model.subtitle !== model.title)
  const hasStructuredBody = Boolean(
    showSubtitle ||
      commentPreview ||
      model.webSearch ||
      model.fileChanges ||
      model.lines.length > 0 ||
      model.paths.length > 0
  )

  React.useEffect(() => {
    if (isLatest) {
      if (expandModeRef.current !== 'manual-close') {
        setExpanded(true)
      }
      return
    }
    if (expandModeRef.current === 'auto') {
      setExpanded(false)
    }
  }, [isLatest])

  const handleToggle = React.useCallback(() => {
    setExpanded((current) => {
      const next = !current
      expandModeRef.current = next ? 'manual-open' : 'manual-close'
      return next
    })
  }, [])

  const summaryText = commentSummary || model.title || model.subtitle || model.lines[0] || model.label
  const secondaryText = selectSecondaryText(summaryText, [
    commentSummary ? model.title : '',
    showSubtitle ? model.subtitle : '',
    commentWhyNow,
    commentNext,
    model.lines[0],
  ])

  return (
    <div
      className="min-w-0 overflow-hidden border-l border-black/[0.08] py-1 pl-3 dark:border-white/[0.10]"
      data-copilot-tool-surface="studio"
      data-copilot-tool-server={identity.server || undefined}
      data-copilot-tool-name={identity.tool || item.toolName || undefined}
    >
      <button
        type="button"
        className="flex w-full min-w-0 items-start gap-2.5 py-1 text-left"
        onClick={handleToggle}
      >
        <div
          title={model.tooltip}
          aria-label={model.tooltip}
          className={cn(
            'mt-0.5 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-sm',
            model.accentClassName
          )}
        >
          <model.Icon className="h-3.5 w-3.5" />
        </div>

        <div className="min-w-0 flex-1 space-y-0.5">
          <div
            className="break-words text-[12.5px] font-medium leading-[1.65] text-foreground [overflow-wrap:anywhere]"
            title={summaryText}
          >
            {summaryText}
          </div>
          {secondaryText ? (
            <div
              className="break-words text-[12px] leading-[1.5] text-muted-foreground [overflow-wrap:anywhere]"
              title={secondaryText}
            >
              {secondaryText}
            </div>
          ) : null}
        </div>

        <div className="ml-auto flex shrink-0 flex-col items-end gap-0.5 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1 font-medium text-muted-foreground">
            <StatusIcon className={cn('h-3.5 w-3.5', model.statusSpinning && 'animate-spin')} />
            {model.statusLabel}
          </span>
          <div className="flex items-center gap-1.5">
            {item.createdAt ? <span>{formatTime(item.createdAt)}</span> : null}
            <ChevronDown
              className={cn(
                'h-4 w-4 transition-transform',
                expanded && 'rotate-180'
              )}
            />
          </div>
        </div>
      </button>

      {expanded ? (
        <div className="ml-[20px] mt-2 space-y-2 border-l border-black/[0.06] pl-3 dark:border-white/[0.08]">
          <ToolCommentPanel
            summary={item.comment?.summary ?? null}
            whyNow={item.comment?.whyNow ?? null}
            next={item.comment?.next ?? null}
          />

          {showSubtitle ? (
            <div className="break-words text-[12px] leading-[1.6] text-muted-foreground [overflow-wrap:anywhere]">
              {model.subtitle}
            </div>
          ) : null}

          {model.webSearch ? (
            <StudioWebSearchPanel payload={model.webSearch} isSearching={item.label === 'tool_call'} />
          ) : model.fileChanges ? (
            <StudioFileChangePanel questId={questId} item={item} entries={model.fileChanges} />
          ) : model.lines.length > 0 ? (
            <div className="space-y-1.5 text-[12px] leading-[1.6] text-muted-foreground">
              {model.lines.slice(0, 3).map((line, index) => (
                <div key={`${index}:${line}`} className="break-words [overflow-wrap:anywhere]">
                  {line}
                </div>
              ))}
            </div>
          ) : null}

          <InlinePathList paths={model.paths} />

          {!hasStructuredBody ? <FallbackOutput value={fallbackOutput || model.rawArgs} /> : null}
        </div>
      ) : null}
    </div>
  )
}

export default StudioToolCard
