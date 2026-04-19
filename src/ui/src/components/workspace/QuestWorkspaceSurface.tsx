'use client'

import * as React from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Clock3,
  FileCode2,
  FlaskConical,
  GitBranch,
  Lightbulb,
  Plus,
  RefreshCw,
  Sparkles,
  Square,
  Terminal,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/toast'
import { client } from '@/lib/api'
import { getBashLogs, stopBashSession } from '@/lib/api/bash'
import {
  attachTerminalSession,
  ensureTerminalSession,
  restoreTerminalSession,
  type TerminalRestoreCommand,
  type TerminalRestoreTailEntry,
} from '@/lib/api/terminal'
import { useQuestWorkspace } from '@/lib/acp'
import { openQuestDocumentAsFileNode } from '@/lib/api/quest-files'
import { useOpenFile } from '@/hooks/useOpenFile'
import { useBashLogStream } from '@/lib/hooks/useBashLogStream'
import { useBashSessionStream } from '@/lib/hooks/useBashSessionStream'
import { EnhancedTerminal } from '@/lib/plugins/cli/components/EnhancedTerminal'
import LabQuestGraphCanvas from '@/lib/plugins/lab/components/LabQuestGraphCanvas'
import { useI18n } from '@/lib/i18n/useI18n'
import { useLabCopilotStore } from '@/lib/stores/lab-copilot'
import { useLabGraphSelectionStore } from '@/lib/stores/lab-graph-selection'
import { cn } from '@/lib/utils'
import { getProgressPercent } from '@/lib/utils/bash-progress'
import { QuestSettingsSurface } from '@/components/workspace/QuestSettingsSurface'
import { QuestMemorySurface } from '@/components/workspace/QuestMemorySurface'
import { QuestStageSurface } from '@/components/workspace/QuestStageSurface'
import type { BashLogEntry, BashProgress, BashSession } from '@/lib/types/bash'
import {
  isBashProgressMarker,
  parseBashProgressMarker,
  parseBashStatusMarker,
  splitBashLogLine,
} from '@/lib/utils/bash-log'
import type {
  BaselineComparePayload,
  BaselineCompareSeries,
  FeedItem,
  GitBranchesPayload,
  GuidanceVm,
  MetricsTimelinePayload,
  MetricTimelineSeries,
  WorkflowEntry,
} from '@/types'
import {
  QUEST_WORKSPACE_VIEW_EVENT,
  type QuestStageSelection,
  type QuestWorkspaceView,
  type QuestWorkspaceViewDetail,
} from '@/components/workspace/workspace-events'
import '@/lib/plugins/cli/styles/terminal.css'

type LinkItem = {
  key: string
  title: string
  subtitle?: string | null
  badge?: string | null
  documentId?: string | null
  stageSelection?: QuestStageSelection | null
}

export type QuestWorkspaceState = ReturnType<typeof useQuestWorkspace>

type QuestWorkspaceSurfaceInnerProps = {
  questId: string
  safePaddingLeft: number
  safePaddingRight: number
  view?: QuestWorkspaceView
  stageSelection?: QuestStageSelection | null
  settingsFocusTarget?: string | null
  onViewChange?: (view: QuestWorkspaceView, stageSelection?: QuestStageSelection | null) => void
  workspace: QuestWorkspaceState
}

function projectionState(payload?: { projection_status?: { state?: string | null } | null } | null) {
  return String(payload?.projection_status?.state || '')
    .trim()
    .toLowerCase()
}

function projectionPending(payload?: { projection_status?: { state?: string | null } | null } | null) {
  const state = projectionState(payload)
  return Boolean(state) && state !== 'ready'
}

function projectionStatusLabel(payload?: { projection_status?: { state?: string | null } | null } | null) {
  const status = payload?.projection_status
  const state = projectionState(payload)
  if (!state || state === 'ready') return null
  const current = typeof status?.progress_current === 'number' ? status.progress_current : null
  const total = typeof status?.progress_total === 'number' ? status.progress_total : null
  const step = status?.current_step?.trim()
  const suffix =
    current != null && total != null && total > 0 ? ` (${Math.min(current, total)}/${total})` : ''
  switch (state) {
    case 'queued':
      return `Background rebuild queued${suffix}${step ? ` · ${step}` : ''}`
    case 'building':
      return `Background rebuild in progress${suffix}${step ? ` · ${step}` : ''}`
    case 'stale':
      return 'Showing the last successful snapshot while a refresh is queued'
    case 'failed':
      return step || status?.error?.trim() || 'Background rebuild failed'
    default:
      return step || `Projection state: ${state}`
  }
}

function projectionProgressValue(payload?: { projection_status?: { progress_current?: number | null; progress_total?: number | null } | null } | null) {
  const status = payload?.projection_status
  const current =
    typeof status?.progress_current === 'number' && Number.isFinite(status.progress_current)
      ? Math.max(0, status.progress_current)
      : 0
  const total =
    typeof status?.progress_total === 'number' && Number.isFinite(status.progress_total)
      ? Math.max(0, status.progress_total)
      : 0
  if (total <= 0) return null
  return Math.min(100, Math.max(0, (current / total) * 100))
}

function ProjectionProgressBar({
  percent,
  className,
  indicatorClassName,
}: {
  percent?: number | null
  className?: string
  indicatorClassName?: string
}) {
  const width = Number.isFinite(percent ?? NaN) ? Math.max(0, Math.min(100, percent ?? 0)) : 0
  return (
    <div
      className={cn(
        'h-2.5 overflow-hidden rounded-full bg-black/[0.06] dark:bg-white/[0.08]',
        className
      )}
      aria-hidden="true"
    >
      <div
        className={cn(
          'h-full rounded-full bg-[#9b8352] transition-[width] duration-300 ease-out dark:bg-[#d7b676]',
          indicatorClassName
        )}
        style={{ width: `${width}%` }}
      />
    </div>
  )
}

function flattenText(value?: string | null) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
}

function clampText(value?: string | null, limit = 180) {
  const normalized = flattenText(value)
  if (!normalized) return '—'
  if (normalized.length <= limit) return normalized
  return `${normalized.slice(0, Math.max(0, limit - 1)).trimEnd()}…`
}

function formatRelativeTime(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function formatDuration(value?: string | null) {
  if (!value) return '—'
  const start = new Date(value)
  if (Number.isNaN(start.getTime())) return '—'
  const diffMs = Math.max(0, Date.now() - start.getTime())
  const totalMinutes = Math.floor(diffMs / 60000)
  const days = Math.floor(totalMinutes / (60 * 24))
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60)
  const minutes = totalMinutes % 60
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

function resolveQuestDocumentIdFromPath(
  path: string | null | undefined,
  snapshot?: {
    quest_root?: string | null
    active_workspace_root?: string | null
  } | null
) {
  const raw = String(path || '').trim()
  if (!raw) return null
  if (
    raw.startsWith('path::') ||
    raw.startsWith('questpath::') ||
    raw.startsWith('memory::') ||
    raw.startsWith('skill::') ||
    raw.startsWith('git::')
  ) {
    return raw
  }

  const normalized = raw.replace(/\\/g, '/')
  if (!normalized.startsWith('/')) {
    return `path::${normalized.replace(/^\.?\//, '')}`
  }

  const normalizedQuestRoot = String(snapshot?.quest_root || '')
    .trim()
    .replace(/\\/g, '/')
    .replace(/\/$/, '')
  const normalizedWorkspaceRoot = String(snapshot?.active_workspace_root || '')
    .trim()
    .replace(/\\/g, '/')
    .replace(/\/$/, '')

  if (normalizedWorkspaceRoot && normalized.startsWith(`${normalizedWorkspaceRoot}/`)) {
    return `path::${normalized.slice(normalizedWorkspaceRoot.length + 1)}`
  }
  if (normalizedQuestRoot && normalized.startsWith(`${normalizedQuestRoot}/`)) {
    return `questpath::${normalized.slice(normalizedQuestRoot.length + 1)}`
  }
  return null
}

const ANSI_ESCAPE_SEQUENCE_REGEX = /\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])/g
const LEGACY_BASH_PROMPT_REGEX = /^bash-\d+(?:\.\d+)*\$\s*$/

function stripAnsiSequences(value?: string | null) {
  return String(value || '').replace(ANSI_ESCAPE_SEQUENCE_REGEX, '')
}

function formatBashSessionStatus(status?: string | null) {
  if (!status) return 'idle'
  return status.replace(/_/g, ' ')
}

function isActiveBashSession(status?: string | null) {
  const normalized = String(status || '').trim().toLowerCase()
  return normalized === 'running' || normalized === 'terminating'
}

function summarizeBashCommand(command?: string | null, limit = 84) {
  const normalized = String(command || '').replace(/\s+/g, ' ').trim()
  if (!normalized) return 'bash_exec'
  if (normalized.length <= limit) return normalized
  return `${normalized.slice(0, Math.max(0, limit - 1)).trimEnd()}…`
}

function formatCompactDurationSeconds(value?: number | null) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return '—'
  if (value < 60) return `${Math.round(value)}s`
  if (value < 3600) {
    const minutes = Math.floor(value / 60)
    const seconds = Math.floor(value % 60)
    return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`
  }
  const hours = Math.floor(value / 3600)
  const minutes = Math.floor((value % 3600) / 60)
  return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`
}

function summarizeBashComment(comment?: BashSession['comment']) {
  if (typeof comment === 'string') {
    const normalized = flattenText(comment)
    return normalized ? clampText(normalized, 140) : null
  }
  if (!comment || typeof comment !== 'object' || Array.isArray(comment)) {
    return null
  }
  const record = comment as Record<string, unknown>
  const preferredKeys = ['summary', 'note', 'reason', 'task', 'goal', 'label', 'description']
  for (const key of preferredKeys) {
    const value = record[key]
    if (typeof value !== 'string') continue
    const normalized = flattenText(value)
    if (normalized) return clampText(normalized, 140)
  }
  return null
}

function RunningTag({ label = 'Running' }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-emerald-700 dark:border-emerald-400/25 dark:bg-emerald-400/10 dark:text-emerald-200">
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {label}
    </span>
  )
}

function TerminalModeButton({
  active,
  icon,
  label,
  running,
  onClick,
}: {
  active: boolean
  icon: React.ReactNode
  label: string
  running?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-2 rounded-full border px-3 py-2 text-[11px] font-semibold transition',
        active
          ? 'border-[#9b8352]/50 bg-[#9b8352]/[0.10] text-foreground shadow-sm'
          : 'border-black/[0.08] bg-white/[0.84] text-muted-foreground hover:bg-white dark:border-white/[0.10] dark:bg-[rgba(18,18,18,0.72)] dark:hover:bg-[rgba(24,24,24,0.9)]'
      )}
      aria-pressed={active}
    >
      <span className="inline-flex h-4 w-4 items-center justify-center">{icon}</span>
      <span>{label}</span>
      {running ? <RunningTag /> : null}
    </button>
  )
}

function sortBashLogEntries(entries: BashLogEntry[]) {
  return [...entries].sort((a, b) => a.seq - b.seq)
}

function mergeBashLogEntries(current: BashLogEntry[], incoming: BashLogEntry[]) {
  const map = new Map<number, BashLogEntry>()
  current.forEach((entry) => {
    map.set(entry.seq, entry)
  })
  incoming.forEach((entry) => {
    map.set(entry.seq, entry)
  })
  return sortBashLogEntries(Array.from(map.values()))
}

type LocalTerminalInputState = {
  buffer: string
  cursor: number
  active: boolean
}

type PendingTerminalEcho = {
  remaining: string
  submittedAt: number
}

type TerminalRestorePreview = {
  latestCommands: TerminalRestoreCommand[]
  visibleLines: Array<{ line: string; stream: string }>
}

const TERMINAL_ESCAPE_UP = '\x1b[A'
const TERMINAL_ESCAPE_DOWN = '\x1b[B'
const TERMINAL_ESCAPE_RIGHT = '\x1b[C'
const TERMINAL_ESCAPE_LEFT = '\x1b[D'
const TERMINAL_ESCAPE_DELETE = '\x1b[3~'
const TERMINAL_ESCAPE_HOME = '\x1b[H'
const TERMINAL_ESCAPE_END = '\x1b[F'
const TERMINAL_ESCAPE_ALT_HOME = '\x1bOH'
const TERMINAL_ESCAPE_ALT_END = '\x1bOF'
const TERMINAL_ESCAPE_ALT_HOME_TILDE = '\x1b[1~'
const TERMINAL_ESCAPE_ALT_END_TILDE = '\x1b[4~'
const TERMINAL_RAW_INPUT_BATCH_MS = 12

function normalizeTerminalCommandHistory(values: Array<string | null | undefined>) {
  return values
    .map((value) => String(value || '').trim())
    .filter(Boolean)
    .slice(-200)
}

function commonPrefixLength(left: string, right: string) {
  const limit = Math.min(left.length, right.length)
  let index = 0
  while (index < limit && left[index] === right[index]) {
    index += 1
  }
  return index
}

function stripLeadingTerminalBreaks(value: string) {
  return value.replace(/^[\r\n]+/, '')
}

function buildTerminalRestorePreview(
  payload: {
    latest_commands?: TerminalRestoreCommand[]
    tail?: TerminalRestoreTailEntry[]
  } | null | undefined
): TerminalRestorePreview {
  const latestCommands = Array.isArray(payload?.latest_commands)
    ? payload!.latest_commands.filter((item) => item && typeof item === 'object')
    : []
  const visibleLines = Array.isArray(payload?.tail)
    ? payload!.tail
        .map((entry) => ({
          line: String(entry?.line || ''),
          stream: String(entry?.stream || ''),
        }))
        .filter((entry) => {
          if (!entry.line.trim()) return false
          if (entry.stream === 'prompt' || entry.stream === 'carriage' || entry.stream === 'partial' || entry.stream === 'system') {
            return false
          }
          return true
        })
        .slice(-6)
    : []
  return {
    latestCommands,
    visibleLines,
  }
}

function formatConnectionState(
  value?: ReturnType<typeof useQuestWorkspace>['connectionState']
) {
  if (!value || value === 'connected') return 'live'
  return value.replace(/_/g, ' ')
}

function formatMetricValue(
  value?: number | string | null,
  decimals?: number | null
) {
  if (value == null || value === '') return '—'
  if (typeof value === 'number') {
    if (typeof decimals === 'number') {
      return value.toFixed(decimals)
    }
    return value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
  }
  return String(value)
}

function formatSelectionScoreSummary(value?: Record<string, unknown> | null) {
  if (!value || typeof value !== 'object') return null
  const entries = Object.entries(value)
    .map(([key, raw]) => {
      const label = String(key || '').trim()
      if (!label) return null
      if (typeof raw === 'number' && Number.isFinite(raw)) {
        return `${label}=${raw.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')}`
      }
      const rendered = String(raw ?? '').trim()
      return rendered ? `${label}=${rendered}` : null
    })
    .filter(Boolean)
    .slice(0, 3) as string[]
  return entries.length ? entries.join(' · ') : null
}

type MetricTimelineChartDatum = {
  slotIndex: number
  slotKey: string
  seq?: number | null
  value?: number | null
  delta?: number | null
  breakthrough?: boolean
  isBaselineSlot?: boolean
  beatsBaseline?: boolean
}

const METRIC_TIMELINE_CHART_WIDTH = 360
const METRIC_TIMELINE_CHART_HEIGHT = 220
const METRIC_TIMELINE_CHART_PADDING = {
  top: 14,
  right: 16,
  bottom: 32,
  left: 24,
} as const

function normalizeTimelineDirection(value?: string | null): 'maximize' | 'minimize' {
  const text = String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[- ]+/g, '_')
  if (text === 'lower' || text === 'minimize' || text === 'lower_better' || text === 'less_is_better') {
    return 'minimize'
  }
  return 'maximize'
}

function metricBeatsBaseline({
  value,
  baselineValue,
  delta,
  direction,
}: {
  value?: number | null
  baselineValue?: number | null
  delta?: number | null
  direction: 'maximize' | 'minimize'
}) {
  if (typeof value === 'number' && Number.isFinite(value) && typeof baselineValue === 'number' && Number.isFinite(baselineValue)) {
    return direction === 'minimize' ? value < baselineValue : value > baselineValue
  }
  if (typeof delta === 'number' && Number.isFinite(delta)) {
    return direction === 'minimize' ? delta < 0 : delta > 0
  }
  return false
}

function buildStarPoints(cx: number, cy: number, outerRadius: number, innerRadius: number) {
  const points: string[] = []
  for (let index = 0; index < 10; index += 1) {
    const angle = -Math.PI / 2 + (index * Math.PI) / 5
    const radius = index % 2 === 0 ? outerRadius : innerRadius
    const x = cx + Math.cos(angle) * radius
    const y = cy + Math.sin(angle) * radius
    points.push(`${x.toFixed(2)},${y.toFixed(2)}`)
  }
  return points.join(' ')
}

function clampMetricTimelineValue(value: number, minValue: number, maxValue: number) {
  if (!Number.isFinite(value)) return minValue
  return Math.min(maxValue, Math.max(minValue, value))
}

function buildMetricTimelineChartGeometry(chartData: MetricTimelineChartDatum[], baselineValue?: number | null) {
  const width = METRIC_TIMELINE_CHART_WIDTH
  const height = METRIC_TIMELINE_CHART_HEIGHT
  const innerWidth = width - METRIC_TIMELINE_CHART_PADDING.left - METRIC_TIMELINE_CHART_PADDING.right
  const innerHeight = height - METRIC_TIMELINE_CHART_PADDING.top - METRIC_TIMELINE_CHART_PADDING.bottom
  const yValues = [
    ...chartData
      .map((item) => item.value)
      .filter((item): item is number => typeof item === 'number' && Number.isFinite(item)),
    ...(typeof baselineValue === 'number' && Number.isFinite(baselineValue) ? [baselineValue] : []),
  ]
  const rawMin = yValues.length ? Math.min(...yValues) : 0
  const rawMax = yValues.length ? Math.max(...yValues) : 1
  const spread = rawMax - rawMin
  const padding = spread > 0 ? spread * 0.14 : Math.max(Math.abs(rawMax || 1) * 0.18, 1)
  const minValue = rawMin - padding
  const maxValue = rawMax + padding
  const slotCount = Math.max(chartData.length - 1, 1)
  const xForSlot = (slotIndex: number) =>
    METRIC_TIMELINE_CHART_PADDING.left + (slotIndex / slotCount) * innerWidth
  const yForValue = (value: number) =>
    METRIC_TIMELINE_CHART_PADDING.top +
    ((maxValue - clampMetricTimelineValue(value, minValue, maxValue)) / Math.max(maxValue - minValue, 1e-9)) *
      innerHeight
  const plottedPoints = chartData
    .filter((item): item is MetricTimelineChartDatum & { value: number } => typeof item.value === 'number' && Number.isFinite(item.value))
    .map((item) => ({
      ...item,
      x: xForSlot(item.slotIndex),
      y: yForValue(item.value),
    }))
  const linePath = plottedPoints
    .map((item, index) => `${index === 0 ? 'M' : 'L'}${item.x.toFixed(2)} ${item.y.toFixed(2)}`)
    .join(' ')
  const areaPath = plottedPoints.length
    ? `${linePath} L${plottedPoints[plottedPoints.length - 1].x.toFixed(2)} ${(height - METRIC_TIMELINE_CHART_PADDING.bottom).toFixed(2)} L${plottedPoints[0].x.toFixed(2)} ${(height - METRIC_TIMELINE_CHART_PADDING.bottom).toFixed(2)} Z`
    : ''
  const baselineY =
    typeof baselineValue === 'number' && Number.isFinite(baselineValue) ? yForValue(baselineValue) : null
  const tickSlots = Array.from(
    new Set(
      chartData
        .map((item) => item.slotIndex)
        .filter(
          (slotIndex, index, all) =>
            slotIndex === 0 ||
            slotIndex === all[all.length - 1] ||
            chartData.length <= 5 ||
            index % Math.ceil(chartData.length / 4) === 0
        )
    )
  )
  return {
    width,
    height,
    plottedPoints,
    linePath,
    areaPath,
    baselineY,
    tickSlots,
    xForSlot,
  }
}

function formatMetricTimelineSlotLabel(slotKey?: string | null) {
  if (slotKey === 'baseline') return 'Baseline'
  const match = /^run-(\d+)$/.exec(String(slotKey || ''))
  return match ? match[1] : String(slotKey || '')
}

function formatMetricTimelineTickLabel(slotIndex?: number | string | null) {
  if (typeof slotIndex === 'number') {
    if (slotIndex === 0) return 'Baseline'
    return String(slotIndex)
  }
  return formatMetricTimelineSlotLabel(typeof slotIndex === 'string' ? slotIndex : null)
}

function formatMetricTimelineTooltipLabel(slotKey?: string | null) {
  if (slotKey === 'baseline') return 'Baseline'
  const match = /^run-(\d+)$/.exec(String(slotKey || ''))
  return match ? `Run #${match[1]}` : String(slotKey || '')
}

function buildMetricsTimelineRunSignature(entries?: WorkflowEntry[] | null) {
  if (!Array.isArray(entries) || entries.length === 0) return 'none'
  return entries
    .filter((entry) => entry.kind === 'run')
    .map((entry) =>
      [
        entry.run_id || entry.id,
        entry.status || '',
        entry.created_at || '',
        entry.summary || '',
      ].join(':')
    )
    .join('|')
}

const MetricTimelineCard = React.memo(function MetricTimelineCard({
  series,
  primaryMetricId,
}: {
  series: MetricTimelineSeries
  primaryMetricId?: string | null
}) {
  const baseline = React.useMemo(
    () =>
      (series.baselines || []).find(
        (item) => item.selected && typeof item.value === 'number' && Number.isFinite(item.value)
      ) ||
      (series.baselines || []).find((item) => typeof item.value === 'number' && Number.isFinite(item.value)) ||
      null,
    [series.baselines]
  )
  const baselineValue = typeof baseline?.value === 'number' && Number.isFinite(baseline.value) ? baseline.value : null
  const metricDirection = React.useMemo(() => normalizeTimelineDirection(series.direction), [series.direction])
  const chartData = React.useMemo(
    () => [
      {
        slotIndex: 0,
        slotKey: 'baseline',
        seq: null,
        value: baselineValue,
        delta: null,
        breakthrough: false,
        isBaselineSlot: true,
        beatsBaseline: false,
      },
      ...(series.points || []).map((point, index) => ({
        slotIndex: index + 1,
        slotKey: `run-${point.seq ?? index + 1}`,
        seq: point.seq ?? index + 1,
        value: point.value,
        delta: point.delta_vs_baseline,
        breakthrough: point.breakthrough,
        isBaselineSlot: false,
        beatsBaseline: metricBeatsBaseline({
          value: point.value,
          baselineValue,
          delta: point.delta_vs_baseline,
          direction: metricDirection,
        }),
      })),
    ],
    [baselineValue, metricDirection, series.points]
  )
  const lastSlotIndex = chartData[chartData.length - 1]?.slotIndex ?? 0
  const latestPoint = series.points?.length ? series.points[series.points.length - 1] : null
  const chartGeometry = React.useMemo(
    () => buildMetricTimelineChartGeometry(chartData, baselineValue),
    [chartData, baselineValue]
  )
  const chartId = React.useMemo(
    () => `metric-${String(series.metric_id || 'metric').replace(/[^a-zA-Z0-9_-]+/g, '-')}`,
    [series.metric_id]
  )

  return (
    <div
      className="overflow-hidden rounded-[26px] border border-black/[0.08] bg-[linear-gradient(180deg,rgba(255,255,255,0.86),rgba(244,239,233,0.94))] p-4 shadow-card dark:border-white/[0.10] dark:bg-[linear-gradient(180deg,rgba(255,255,255,0.06),rgba(255,255,255,0.03))]"
      style={{ contentVisibility: 'auto', containIntrinsicSize: '320px' }}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-foreground">{series.label || series.metric_id}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            {series.metric_id}
            {series.direction ? ` · ${series.direction}` : ''}
            {series.unit ? ` · ${series.unit}` : ''}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {primaryMetricId === series.metric_id ? <StatusPill>primary</StatusPill> : null}
          {(series.baselines || []).map((baseline) => (
            <StatusPill key={`${baseline.label}:${baseline.metric_id}`}>
              {baseline.selected ? 'selected baseline' : baseline.label}
            </StatusPill>
          ))}
        </div>
      </div>

      <div className="mt-4 h-[220px] w-full">
        <svg
          viewBox={`0 0 ${chartGeometry.width} ${chartGeometry.height}`}
          className="h-full w-full overflow-visible"
          role="img"
          aria-label={`${series.label || series.metric_id} metric timeline`}
        >
          <defs>
            <linearGradient id={`${chartId}-fill`} x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="rgba(91,112,131,0.22)" />
              <stop offset="100%" stopColor="rgba(91,112,131,0.04)" />
            </linearGradient>
          </defs>
          <line
            x1={METRIC_TIMELINE_CHART_PADDING.left}
            y1={METRIC_TIMELINE_CHART_HEIGHT - METRIC_TIMELINE_CHART_PADDING.bottom}
            x2={METRIC_TIMELINE_CHART_WIDTH - METRIC_TIMELINE_CHART_PADDING.right}
            y2={METRIC_TIMELINE_CHART_HEIGHT - METRIC_TIMELINE_CHART_PADDING.bottom}
            stroke="rgba(68,95,125,0.16)"
            strokeWidth="1"
          />
          {chartGeometry.tickSlots.map((slotIndex) => (
            <g key={`tick-${slotIndex}`}>
              <line
                x1={chartGeometry.xForSlot(slotIndex)}
                y1={METRIC_TIMELINE_CHART_HEIGHT - METRIC_TIMELINE_CHART_PADDING.bottom}
                x2={chartGeometry.xForSlot(slotIndex)}
                y2={METRIC_TIMELINE_CHART_HEIGHT - METRIC_TIMELINE_CHART_PADDING.bottom + 4}
                stroke="rgba(68,95,125,0.18)"
                strokeWidth="1"
              />
              <text
                x={chartGeometry.xForSlot(slotIndex)}
                y={METRIC_TIMELINE_CHART_HEIGHT - 6}
                textAnchor="middle"
                className="fill-current text-[10px]"
              >
                {formatMetricTimelineTickLabel(slotIndex)}
              </text>
            </g>
          ))}
          {typeof chartGeometry.baselineY === 'number' ? (
            <line
              x1={METRIC_TIMELINE_CHART_PADDING.left}
              y1={chartGeometry.baselineY}
              x2={chartGeometry.xForSlot(lastSlotIndex)}
              y2={chartGeometry.baselineY}
              stroke="rgba(194,161,92,0.82)"
              strokeDasharray="7 6"
              strokeWidth="1.8"
            />
          ) : null}
          {chartGeometry.areaPath ? (
            <path d={chartGeometry.areaPath} fill={`url(#${chartId}-fill)`} />
          ) : null}
          {chartGeometry.linePath ? (
            <path
              d={chartGeometry.linePath}
              fill="none"
              stroke="rgba(91,112,131,0.82)"
              strokeWidth="2.4"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ) : null}
          {chartGeometry.plottedPoints.map((point) => (
            <g key={point.slotKey}>
              <title>
                {`${formatMetricTimelineTooltipLabel(point.slotKey)} · ${formatMetricValue(point.value, series.decimals)}${
                  point.delta != null ? ` · Δ ${formatMetricValue(point.delta, series.decimals)}` : ''
                }`}
              </title>
              {point.beatsBaseline ? (
                <polygon
                  points={buildStarPoints(point.x, point.y, 6.8, 3.1)}
                  fill="#D0B26E"
                  stroke="#B99654"
                  strokeWidth={1.3}
                />
              ) : (
                <circle
                  cx={point.x}
                  cy={point.y}
                  r={4.1}
                  fill="#445F7D"
                  stroke="rgba(255,255,255,0.96)"
                  strokeWidth={1.4}
                />
              )}
            </g>
          ))}
        </svg>
      </div>

      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
        <span>{series.points?.length || 0} runs</span>
        {latestPoint ? (
          <span>
            latest {formatMetricValue(latestPoint.value, series.decimals)}
          </span>
        ) : (
          <span>No points yet</span>
        )}
      </div>
    </div>
  )
})

const BaselineCompareCard = React.memo(function BaselineCompareCard({
  series,
  primaryMetricId,
}: {
  series: BaselineCompareSeries
  primaryMetricId?: string | null
}) {
  const metricDirection = React.useMemo(() => normalizeTimelineDirection(series.direction), [series.direction])
  const numericValues = React.useMemo(
    () =>
      (series.values || [])
        .map((item) => item.value)
        .filter((item): item is number => typeof item === 'number' && Number.isFinite(item)),
    [series.values]
  )
  const minValue = numericValues.length ? Math.min(...numericValues) : null
  const maxValue = numericValues.length ? Math.max(...numericValues) : null

  const barWidth = React.useCallback(
    (value?: number | null) => {
      if (typeof value !== 'number' || !Number.isFinite(value)) return 16
      if (minValue == null || maxValue == null || Math.abs(maxValue - minValue) < 1e-9) return 68
      const ratio =
        metricDirection === 'minimize'
          ? (maxValue - value) / Math.max(maxValue - minValue, 1e-9)
          : (value - minValue) / Math.max(maxValue - minValue, 1e-9)
      return Math.max(18, 28 + ratio * 72)
    },
    [maxValue, metricDirection, minValue]
  )

  return (
    <div
      className="overflow-hidden rounded-[26px] border border-black/[0.08] bg-[linear-gradient(180deg,rgba(255,255,255,0.88),rgba(242,236,228,0.96))] p-4 shadow-card dark:border-white/[0.10] dark:bg-[linear-gradient(180deg,rgba(255,255,255,0.06),rgba(255,255,255,0.03))]"
      style={{ contentVisibility: 'auto', containIntrinsicSize: '280px' }}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-foreground">{series.label || series.metric_id}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            {series.metric_id}
            {series.direction ? ` · ${series.direction}` : ''}
            {series.unit ? ` · ${series.unit}` : ''}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {primaryMetricId === series.metric_id ? <StatusPill>primary</StatusPill> : null}
          <StatusPill>{series.values?.length || 0} baselines</StatusPill>
        </div>
      </div>

      <div className="mt-4 space-y-3">
        {(series.values || []).map((item) => (
          <div
            key={`${item.entry_key}:${series.metric_id}`}
            className={cn(
              'rounded-[20px] border px-3 py-3',
              item.selected
                ? 'border-amber-300/80 bg-amber-50/70 dark:border-amber-300/30 dark:bg-amber-200/10'
                : 'border-black/[0.08] bg-white/70 dark:border-white/[0.10] dark:bg-white/[0.02]'
            )}
          >
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-foreground">{item.label}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {[item.baseline_kind || null, item.selected ? 'active baseline' : null]
                    .filter(Boolean)
                    .join(' · ') || 'baseline'}
                </div>
              </div>
              <div className="shrink-0 text-right">
                <div className="text-sm font-semibold text-foreground">
                  {formatMetricValue(item.value ?? item.raw_value, series.decimals)}
                </div>
              </div>
            </div>
            <div className="mt-3 h-2 rounded-full bg-black/[0.06] dark:bg-white/[0.08]">
              <div
                className={cn(
                  'h-2 rounded-full',
                  item.selected ? 'bg-amber-500/90' : 'bg-slate-500/85'
                )}
                style={{ width: `${barWidth(item.value)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
})

function summarizeFeedItem(item: FeedItem) {
  if (item.type === 'message') {
    return {
      category: item.reasoning ? 'Thinking' : item.role === 'assistant' ? 'Assistant' : 'User',
      title: item.skillId ? `${item.role} · ${item.skillId}` : item.role,
      summary: clampText(item.content, 220),
      createdAt: item.createdAt,
    }
  }

  if (item.type === 'artifact') {
    return {
      category: 'Artifact',
      title: item.kind,
      summary: clampText(item.reason || item.guidance || item.content, 220),
      createdAt: item.createdAt,
    }
  }

  if (item.type === 'operation') {
    const toolLabel =
      item.toolName ||
      [item.mcpServer, item.mcpTool].filter(Boolean).join('.') ||
      item.label
    return {
      category: item.label === 'tool_result' ? 'Tool result' : 'Tool call',
      title: toolLabel,
      summary: clampText(item.subject || item.output || item.args || item.content, 220),
      createdAt: item.createdAt,
    }
  }

  return {
    category: 'Event',
    title: item.label,
    summary: clampText(item.content, 220),
    createdAt: item.createdAt,
  }
}

function StatusPill({
  children,
  mono = false,
}: {
  children: React.ReactNode
  mono?: boolean
}) {
  return (
    <span
      className={cn(
        'inline-flex max-w-full items-center rounded-full border border-black/[0.08] px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground dark:border-white/[0.12]',
        mono && 'font-mono normal-case tracking-[0.02em]'
      )}
    >
      <span className="truncate">{children}</span>
    </span>
  )
}

function WorkspaceRefreshButton({
  onRefresh,
  label = 'Refresh',
}: {
  onRefresh: () => Promise<void> | void
  label?: string
}) {
  const [refreshing, setRefreshing] = React.useState(false)

  const handleClick = React.useCallback(async () => {
    setRefreshing(true)
    try {
      await onRefresh()
    } finally {
      setRefreshing(false)
    }
  }, [onRefresh])

  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      onClick={() => {
        void handleClick()
      }}
      className="h-9 rounded-full border-black/[0.08] bg-white/[0.84] px-3 text-[11px] shadow-sm backdrop-blur hover:bg-white dark:border-white/[0.10] dark:bg-[rgba(18,18,18,0.72)] dark:hover:bg-[rgba(24,24,24,0.9)]"
    >
      <RefreshCw className={cn('mr-1.5 h-3.5 w-3.5', refreshing && 'animate-spin')} />
      {label}
    </Button>
  )
}

function DetailSection({
  title,
  hint,
  actions,
  children,
  first = false,
}: {
  title: string
  hint?: string | null
  actions?: React.ReactNode
  children: React.ReactNode
  first?: boolean
}) {
  return (
    <section
      className={cn(
        'py-6',
        first ? 'pt-0' : 'border-t border-dashed border-black/[0.12] dark:border-white/[0.12]'
      )}
      style={{ contentVisibility: 'auto', containIntrinsicSize: first ? '560px' : '720px' }}
    >
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            {title}
          </div>
          {hint ? (
            <div className="mt-2 max-w-3xl text-sm leading-7 text-muted-foreground">
              {hint}
            </div>
          ) : null}
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </div>
      {children}
    </section>
  )
}

function OverviewMetric({
  icon,
  label,
  value,
  hint,
}: {
  icon: React.ReactNode
  label: string
  value: React.ReactNode
  hint?: string | null
}) {
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
        <span className="shrink-0">{icon}</span>
        <span>{label}</span>
      </div>
      <div className="mt-2 break-words text-[15px] font-semibold leading-6 text-foreground">
        {value}
      </div>
      {hint ? (
        <div className="mt-2 break-words text-sm leading-6 text-muted-foreground">
          {hint}
        </div>
      ) : null}
    </div>
  )
}

function DocumentListBlock({
  title,
  countLabel,
  items,
  emptyLabel,
  onOpen,
  headerAction,
}: {
  title: string
  countLabel?: string | null
  items: LinkItem[]
  emptyLabel: string
  onOpen: (item: LinkItem) => void
  headerAction?: React.ReactNode
}) {
  return (
    <div className="min-w-0">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            {title}
          </div>
          {headerAction}
        </div>
        {countLabel ? <div className="text-[11px] text-muted-foreground">{countLabel}</div> : null}
      </div>
      {items.length === 0 ? (
        <div className="py-3 text-sm leading-7 text-muted-foreground">{emptyLabel}</div>
      ) : (
        <div className="divide-y divide-dashed divide-black/[0.10] dark:divide-white/[0.10]">
          {items.map((item) => {
            const body = (
              <>
                <div className="min-w-0">
                  <div className="break-words text-sm font-medium leading-6 text-foreground">
                    {item.title}
                  </div>
                  {item.subtitle ? (
                    <div className="mt-1 break-words text-sm leading-6 text-muted-foreground">
                      {item.subtitle}
                    </div>
                  ) : null}
                </div>
                {item.badge ? (
                  <div className="shrink-0 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                    {item.badge}
                  </div>
                ) : null}
              </>
            )

            if (!item.documentId) {
              return (
                <div key={item.key} className="flex items-start justify-between gap-3 py-3">
                  {body}
                </div>
              )
            }

            return (
              <button
                key={item.key}
                type="button"
                onClick={() => onOpen(item)}
                className="flex w-full items-start justify-between gap-3 py-3 text-left transition hover:text-foreground"
              >
                {body}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

function ActivityTimeline({
  items,
  loading,
  restoring,
  connectionState,
}: {
  items: FeedItem[]
  loading: boolean
  restoring: boolean
  connectionState: ReturnType<typeof useQuestWorkspace>['connectionState']
}) {
  if (items.length === 0) {
    const label =
      restoring || loading
        ? 'Loading recent project activity…'
        : connectionState === 'reconnecting'
          ? 'Reconnecting to project event stream…'
        : connectionState === 'error'
            ? 'Project event stream is temporarily unavailable.'
            : 'No project activity yet.'

    return <div className="py-3 text-sm leading-7 text-muted-foreground">{label}</div>
  }

  return (
    <div className="divide-y divide-dashed divide-black/[0.10] dark:divide-white/[0.10]">
      {items.map((item) => {
        const summary = summarizeFeedItem(item)
        return (
          <div
            key={item.id}
            className="grid gap-3 py-3 sm:grid-cols-[112px_minmax(0,1fr)]"
          >
            <div className="text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
              {formatRelativeTime(summary.createdAt)}
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-foreground">
                  {summary.category}
                </span>
                <span className="text-[11px] text-muted-foreground">{summary.title}</span>
              </div>
              <div className="mt-2 break-words text-sm leading-7 text-muted-foreground">
                {summary.summary}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function QuestCanvasSurface({
  questId,
  error,
  onRefresh,
  onOpenStageSelection,
  snapshot,
}: {
  questId: string
  error?: string | null
  onRefresh: () => Promise<void>
  onOpenStageSelection?: (selection: QuestStageSelection) => void
  snapshot?: QuestWorkspaceState['snapshot']
}) {
  const queryClient = useQueryClient()
  const clearGraphSelection = useLabGraphSelectionStore((state) => state.clear)
  const selection = useLabGraphSelectionStore((state) => state.selection)
  const setGraphSelection = useLabGraphSelectionStore((state) => state.setSelection)

  React.useEffect(() => {
    clearGraphSelection()
  }, [clearGraphSelection, questId])

  const handleRefresh = React.useCallback(async () => {
    const refreshTasks: Array<Promise<unknown>> = [onRefresh()]
    clearGraphSelection()
    refreshTasks.push(
      queryClient.invalidateQueries({ queryKey: ['lab-quest-graph', questId] }),
      queryClient.invalidateQueries({ queryKey: ['lab-quest-events', questId] }),
      queryClient.invalidateQueries({ queryKey: ['lab-quest-node-trace', questId] }),
      queryClient.invalidateQueries({ queryKey: ['lab-quest-event-payload', questId] }),
      queryClient.invalidateQueries({ queryKey: ['lab-quest-summary', questId] }),
      queryClient.invalidateQueries({ queryKey: ['lab-papers', questId] }),
      queryClient.invalidateQueries({ queryKey: ['lab-agents', questId] })
    )
    await Promise.allSettled(refreshTasks)
  }, [clearGraphSelection, onRefresh, queryClient, questId])

  const canOpenStageOverview = Boolean(
    onOpenStageSelection &&
      selection &&
      ['branch_node', 'stage_node', 'baseline_node'].includes(String(selection.selection_type || ''))
  )
  const canvasLiveRun = React.useMemo(() => {
    const runtimeStatus = String(snapshot?.runtime_status ?? snapshot?.status ?? '')
      .trim()
      .toLowerCase()
    if (runtimeStatus === 'stopped' || runtimeStatus === 'paused') return false
    if (snapshot?.active_run_id) return true
    if (runtimeStatus === 'running') return true
    return (snapshot?.counts?.bash_running_count ?? 0) > 0
  }, [snapshot])

  return (
    <div
      className="relative h-full min-h-0 overflow-hidden bg-[var(--lab-surface-muted)]"
      data-onboarding-id="quest-canvas-surface"
    >
      <div className="absolute left-4 top-4 z-20 flex max-w-[32rem] flex-wrap items-center gap-2">
        {snapshot?.branch ? (
          <div className="rounded-full border border-black/[0.08] bg-white/[0.88] px-3 py-1.5 text-[11px] font-medium text-foreground shadow-sm backdrop-blur dark:border-white/[0.10] dark:bg-[rgba(18,18,18,0.78)]">
            Current path: <span className="font-semibold">{snapshot.branch}</span>
          </div>
        ) : null}
        {snapshot?.active_anchor ? (
          <div className="rounded-full border border-black/[0.08] bg-white/[0.82] px-3 py-1.5 text-[11px] text-muted-foreground shadow-sm backdrop-blur dark:border-white/[0.10] dark:bg-[rgba(18,18,18,0.72)]">
            Stage: <span className="font-medium text-foreground">{snapshot.active_anchor}</span>
          </div>
        ) : null}
      </div>
      <div className="absolute right-4 top-4 z-20 flex max-w-[28rem] flex-col items-end gap-2">
        {error ? (
          <div className="max-w-full rounded-full border border-black/[0.08] bg-white/[0.86] px-3 py-1.5 text-xs text-muted-foreground shadow-sm backdrop-blur dark:border-white/[0.10] dark:bg-[rgba(18,18,18,0.76)]">
            <span className="break-words">{error}</span>
          </div>
        ) : null}
        {canOpenStageOverview && selection ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-9 rounded-full border-black/[0.08] bg-white/[0.88] px-3 text-[11px] shadow-sm backdrop-blur dark:border-white/[0.1] dark:bg-[rgba(18,18,18,0.78)]"
            onClick={() => {
              onOpenStageSelection?.(selection)
            }}
          >
            Open Overview
          </Button>
        ) : null}
      </div>

      <div className="h-full min-h-0 overflow-hidden">
        {/* Keep the lab canvas refresh contract explicit for shared surface tests: onRefresh={handleRefresh}. */}
        <LabQuestGraphCanvas
          projectId={questId}
          questId={questId}
          readOnly
          liveRun={canvasLiveRun}
          preferredViewMode="branch"
          activeBranch={snapshot?.branch || null}
          highlightBranch={selection?.branch_name || null}
          showFloatingPanels={false}
          onStageOpen={onOpenStageSelection}
        />
      </div>
    </div>
  )
}

function QuestTerminalLegacySurface({
  questId,
  onRefresh,
}: {
  questId: string
  onRefresh: () => Promise<void>
}) {
  const {
    sessions,
    connection,
    reload: reloadSessions,
  } = useBashSessionStream({
    projectId: questId,
    enabled: Boolean(questId),
    limit: 40,
  })
  const [selectedBashId, setSelectedBashId] = React.useState<string | null>(null)
  const [logEntries, setLogEntries] = React.useState<BashLogEntry[]>([])
  const [progress, setProgress] = React.useState<BashProgress | null>(null)
  const [logsLoading, setLogsLoading] = React.useState(false)
  const [logsError, setLogsError] = React.useState<string | null>(null)
  const [lastLogSeq, setLastLogSeq] = React.useState<number | null>(null)
  const [stopPending, setStopPending] = React.useState(false)

  const selectedSession = React.useMemo(() => {
    if (!sessions.length) return null
    return sessions.find((session) => session.bash_id === selectedBashId) ?? sessions[0]
  }, [selectedBashId, sessions])

  React.useEffect(() => {
    if (!sessions.length) {
      setSelectedBashId(null)
      return
    }
    if (!selectedBashId || !sessions.some((session) => session.bash_id === selectedBashId)) {
      setSelectedBashId(sessions[0].bash_id)
    }
  }, [selectedBashId, sessions])

  const reloadSelectedLogs = React.useCallback(
    async (bashId: string) => {
      setLogsLoading(true)
      setLogsError(null)
      try {
        const payload = await getBashLogs(questId, bashId, {
          limit: 800,
          order: 'asc',
        })
        setLogEntries(sortBashLogEntries(payload.entries))
        setLastLogSeq(
          payload.meta.latestSeq ??
            payload.entries[payload.entries.length - 1]?.seq ??
            null
        )
      } catch (error) {
        setLogsError(error instanceof Error ? error.message : 'Failed to load terminal logs.')
        setLogEntries([])
        setLastLogSeq(null)
      } finally {
        setLogsLoading(false)
      }
    },
    [questId]
  )

  React.useEffect(() => {
    if (!selectedSession) {
      setProgress(null)
      setLogEntries([])
      setLogsError(null)
      setLastLogSeq(null)
      return
    }
    setProgress(selectedSession.last_progress ?? null)
    void reloadSelectedLogs(selectedSession.bash_id)
  }, [reloadSelectedLogs, selectedSession])

  useBashLogStream({
    projectId: questId,
    bashId: selectedSession?.bash_id ?? null,
    enabled: Boolean(
      selectedSession &&
        (selectedSession.status === 'running' ||
          selectedSession.status === 'terminating')
    ),
    lastEventId: lastLogSeq,
    onSnapshot: (event) => {
      if (!selectedSession || event.bash_id !== selectedSession.bash_id) return
      const nextEntries = (event.lines || []).map((line) => ({
        seq: line.seq,
        stream: line.stream || 'stdout',
        line: line.line || '',
        timestamp: line.timestamp || '',
      }))
      setLogEntries(sortBashLogEntries(nextEntries))
      setLastLogSeq(event.latest_seq ?? nextEntries[nextEntries.length - 1]?.seq ?? null)
      setProgress(event.progress ?? selectedSession.last_progress ?? null)
    },
    onLogBatch: (event) => {
      if (!selectedSession || event.bash_id !== selectedSession.bash_id) return
      const nextEntries = (event.lines || []).map((line) => ({
        seq: line.seq,
        stream: line.stream || 'stdout',
        line: line.line || '',
        timestamp: line.timestamp || '',
      }))
      setLogEntries((current) => mergeBashLogEntries(current, nextEntries))
      setLastLogSeq(event.to_seq ?? nextEntries[nextEntries.length - 1]?.seq ?? null)
    },
    onProgress: (event) => {
      if (!selectedSession || event.bash_id !== selectedSession.bash_id) return
      setProgress(event)
    },
    onGap: (event) => {
      if (!selectedSession || event.bash_id !== selectedSession.bash_id) return
      void reloadSelectedLogs(event.bash_id)
    },
    onDone: async (event) => {
      if (!selectedSession || event.bash_id !== selectedSession.bash_id) return
      await Promise.allSettled([reloadSelectedLogs(event.bash_id), reloadSessions(), onRefresh()])
    },
    onError: (error) => {
      setLogsError(error.message)
    },
  })

  const logText = React.useMemo(() => {
    if (!logEntries.length) return ''
    return logEntries
      .map((entry) => {
        const prefix = entry.stream === 'stderr' ? '! ' : ''
        return `${prefix}${entry.line}`
      })
      .join('\n')
  }, [logEntries])

  const handleRefresh = React.useCallback(async () => {
    await Promise.allSettled([
      reloadSessions(),
      selectedSession ? reloadSelectedLogs(selectedSession.bash_id) : Promise.resolve(),
      onRefresh(),
    ])
  }, [onRefresh, reloadSelectedLogs, reloadSessions, selectedSession])

  const handleStop = React.useCallback(async () => {
    if (!selectedSession) return
    setStopPending(true)
    try {
      await stopBashSession(questId, selectedSession.bash_id, {
        reason: 'Stopped from terminal panel',
      })
      await Promise.allSettled([
        reloadSessions(),
        reloadSelectedLogs(selectedSession.bash_id),
        onRefresh(),
      ])
    } finally {
      setStopPending(false)
    }
  }, [onRefresh, questId, reloadSelectedLogs, reloadSessions, selectedSession])

  return (
    <div className="feed-scrollbar h-full overflow-y-auto overflow-x-hidden">
      <div className="mx-auto flex min-h-full max-w-[1120px] flex-col px-5 pb-10 pt-5 sm:px-6 lg:px-8">
        <DetailSection
          first
          title="Terminal"
          hint="Project-local bash_exec sessions and logs. The latest running session streams here automatically."
          actions={<WorkspaceRefreshButton onRefresh={handleRefresh} label="Refresh terminal" />}
        >
          {!sessions.length ? (
            <div className="rounded-[24px] border border-dashed border-black/[0.10] px-4 py-6 text-sm text-muted-foreground dark:border-white/[0.12]">
              No bash_exec sessions recorded yet.
            </div>
          ) : (
            <div className="grid min-h-[620px] gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
              <div className="rounded-[26px] border border-black/[0.08] bg-[linear-gradient(180deg,rgba(255,255,255,0.86),rgba(244,239,233,0.94))] p-3 shadow-card dark:border-white/[0.10] dark:bg-[linear-gradient(180deg,rgba(255,255,255,0.06),rgba(255,255,255,0.03))]">
                <div className="flex items-center justify-between gap-3 px-1 pb-3">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                    Sessions
                  </div>
                  <StatusPill>{formatBashSessionStatus(connection.status)}</StatusPill>
                </div>
                <div className="space-y-2">
                  {sessions.map((session) => {
                    const sessionProgress =
                      getProgressPercent(session.last_progress) ??
                      session.last_progress?.percent ??
                      null
                    const isActive = session.bash_id === selectedSession?.bash_id
                    return (
                      <button
                        key={session.bash_id}
                        type="button"
                        onClick={() => setSelectedBashId(session.bash_id)}
                        className={cn(
                          'w-full rounded-[20px] border px-3 py-3 text-left transition',
                          isActive
                            ? 'border-[#9b8352]/50 bg-[#9b8352]/[0.08] shadow-sm'
                            : 'border-black/[0.06] bg-white/[0.56] hover:border-black/[0.10] hover:bg-white/[0.78] dark:border-white/[0.08] dark:bg-white/[0.03] dark:hover:bg-white/[0.05]'
                        )}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-semibold text-foreground">
                              {session.command || 'bash_exec'}
                            </div>
                            <div className="mt-1 truncate text-xs text-muted-foreground">
                              {session.workdir || 'project root'}
                            </div>
                          </div>
                          <StatusPill>{formatBashSessionStatus(session.status)}</StatusPill>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                          <span>{formatRelativeTime(session.started_at)}</span>
                          <span>·</span>
                          <span>{session.mode}</span>
                          {typeof sessionProgress === 'number' ? (
                            <>
                              <span>·</span>
                              <span>{sessionProgress.toFixed(0)}%</span>
                            </>
                          ) : null}
                        </div>
                      </button>
                    )
                  })}
                </div>
              </div>

              <div className="min-w-0 rounded-[26px] border border-black/[0.08] bg-[linear-gradient(180deg,rgba(255,255,255,0.86),rgba(244,239,233,0.94))] p-4 shadow-card dark:border-white/[0.10] dark:bg-[linear-gradient(180deg,rgba(255,255,255,0.06),rgba(255,255,255,0.03))]">
                {selectedSession ? (
                  <>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-black/[0.04] text-foreground dark:bg-white/[0.06]">
                            <Terminal className="h-4 w-4" />
                          </div>
                          <div>
                            <div className="break-words text-lg font-semibold text-foreground">
                              {selectedSession.command || 'bash_exec'}
                            </div>
                            <div className="mt-1 break-all text-xs text-muted-foreground">
                              {selectedSession.workdir}
                            </div>
                          </div>
                        </div>
                        <div className="mt-4 flex flex-wrap gap-2">
                          <StatusPill>{formatBashSessionStatus(selectedSession.status)}</StatusPill>
                          <StatusPill mono>{selectedSession.bash_id}</StatusPill>
                          <StatusPill>{selectedSession.mode}</StatusPill>
                          {selectedSession.exit_code != null ? (
                            <StatusPill>exit {selectedSession.exit_code}</StatusPill>
                          ) : null}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {selectedSession.status === 'running' ||
                        selectedSession.status === 'terminating' ? (
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              void handleStop()
                            }}
                            disabled={stopPending}
                            className="h-9 rounded-full border-black/[0.08] bg-white/[0.84] px-3 text-[11px] shadow-sm backdrop-blur hover:bg-white dark:border-white/[0.10] dark:bg-[rgba(18,18,18,0.72)] dark:hover:bg-[rgba(24,24,24,0.9)]"
                          >
                            <Square className="mr-1.5 h-3.5 w-3.5" />
                            {stopPending ? 'Stopping…' : 'Stop'}
                          </Button>
                        ) : null}
                      </div>
                    </div>

                    <div className="mt-6 grid gap-x-10 gap-y-6 sm:grid-cols-2 xl:grid-cols-4">
                      <OverviewMetric
                        icon={<Activity className="h-4 w-4" />}
                        label="State"
                        value={formatBashSessionStatus(selectedSession.status)}
                        hint={connection.status === 'open' ? 'streaming live' : connection.status}
                      />
                      <OverviewMetric
                        icon={<Clock3 className="h-4 w-4" />}
                        label="Started"
                        value={formatRelativeTime(selectedSession.started_at)}
                        hint={selectedSession.finished_at ? `Finished ${formatRelativeTime(selectedSession.finished_at)}` : 'Still active'}
                      />
                      <OverviewMetric
                        icon={<FlaskConical className="h-4 w-4" />}
                        label="Progress"
                        value={
                          progress && (getProgressPercent(progress) ?? progress.percent) != null
                            ? `${(getProgressPercent(progress) ?? progress.percent ?? 0).toFixed(0)}%`
                            : '—'
                        }
                        hint={progress?.desc || progress?.phase || selectedSession.stop_reason || null}
                      />
                      <OverviewMetric
                        icon={<FileCode2 className="h-4 w-4" />}
                        label="Log path"
                        value={selectedSession.log_path.split('/').slice(-3).join('/')}
                        hint={selectedSession.log_path}
                      />
                    </div>

                    <div className="mt-6 overflow-hidden rounded-[24px] border border-black/[0.10] bg-[#0f1115] shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] dark:border-white/[0.10]">
                      <div className="flex items-center justify-between gap-3 border-b border-white/[0.08] px-4 py-3 text-xs text-white/70">
                        <div className="flex items-center gap-2">
                          <div className="flex items-center gap-1.5" aria-hidden="true">
                            <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
                            <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e]" />
                            <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
                          </div>
                          <span>bash_exec</span>
                        </div>
                        <div className="flex items-center gap-2">
                          {logsLoading ? <span>loading…</span> : null}
                          {logsError ? <span className="text-[#ffb4b4]">{logsError}</span> : null}
                        </div>
                      </div>
                      <pre className="feed-scrollbar min-h-[360px] overflow-auto px-4 py-4 text-[12px] leading-6 text-[#d8dee9]">
                        {logText || 'No terminal output yet.'}
                      </pre>
                    </div>
                  </>
                ) : null}
              </div>
            </div>
          )}
        </DetailSection>
      </div>
    </div>
  )
}

type QuestTerminalMode = 'interactive' | 'deepscientist-bash'

type QuestTerminalConnection = {
  status: string
  error?: string
}

function isNativeWindowsBrowser() {
  if (typeof navigator === 'undefined') {
    return false
  }
  return /windows/i.test(navigator.userAgent)
}

function QuestInteractiveTerminalPane({
  questId,
  onRefresh,
  terminalSessions,
  connection,
  reloadSessions,
}: {
  questId: string
  onRefresh: () => Promise<void>
  terminalSessions: BashSession[]
  connection: QuestTerminalConnection
  reloadSessions: () => Promise<void>
}) {
  const { addToast } = useToast()
  const { t } = useI18n('workspace')
  const [selectedSessionId, setSelectedSessionId] = React.useState<string | null>(null)
  const [logsLoading, setLogsLoading] = React.useState(false)
  const [logsError, setLogsError] = React.useState<string | null>(null)
  const [stopPending, setStopPending] = React.useState(false)
  const [sessionStatus, setSessionStatus] = React.useState<string | null>(null)
  const [exitCode, setExitCode] = React.useState<number | null>(null)
  const [stopReason, setStopReason] = React.useState<string | null>(null)
  const [progress, setProgress] = React.useState<BashProgress | null>(null)
  const [liveConnected, setLiveConnected] = React.useState(false)
  const [restorePreview, setRestorePreview] = React.useState<TerminalRestorePreview>({
    latestCommands: [],
    visibleLines: [],
  })
  const restorePreviewRequestRef = React.useRef(0)
  const restorePreviewTimerRef = React.useRef<number | null>(null)

  const selectedSession = React.useMemo<BashSession | null>(() => {
    if (!terminalSessions.length) return null
    return (
      terminalSessions.find((session) => session.bash_id === selectedSessionId) ??
      terminalSessions[0]
    )
  }, [selectedSessionId, terminalSessions])
  const selectedSessionBashId = selectedSession?.bash_id ?? null
  const selectedSessionStatus = selectedSession?.status ?? null

  React.useEffect(() => {
    if (!terminalSessions.length) {
      setSelectedSessionId(null)
      return
    }
    if (
      !selectedSessionId ||
      !terminalSessions.some((session) => session.bash_id === selectedSessionId)
    ) {
      setSelectedSessionId(terminalSessions[0].bash_id)
    }
  }, [selectedSessionId, terminalSessions])

  React.useEffect(() => {
    return () => {
      if (restorePreviewTimerRef.current != null) {
        window.clearTimeout(restorePreviewTimerRef.current)
      }
    }
  }, [])

  const refreshRestorePreview = React.useCallback(
    async (bashId: string) => {
      const requestId = restorePreviewRequestRef.current + 1
      restorePreviewRequestRef.current = requestId
      try {
        const payload = await restoreTerminalSession(questId, bashId, {
          commands: 50,
          output: 1000,
        })
        if (restorePreviewRequestRef.current !== requestId) return
        setRestorePreview(buildTerminalRestorePreview(payload))
      } catch {
        if (restorePreviewRequestRef.current !== requestId) return
        setRestorePreview({ latestCommands: [], visibleLines: [] })
      }
    },
    [questId]
  )

  const ensuredRef = React.useRef(false)
  const shouldAutoEnsureTerminal = React.useMemo(() => !isNativeWindowsBrowser(), [])
  React.useEffect(() => {
    if (!questId || ensuredRef.current || !shouldAutoEnsureTerminal) return
    ensuredRef.current = true
    let cancelled = false
    void ensureTerminalSession(questId, { source: 'web-react' })
      .then(({ session }) => {
        if (cancelled) return
        setSelectedSessionId((prev) => prev ?? session.bash_id)
        void reloadSessions()
      })
      .catch((error) => {
        ensuredRef.current = false
        addToast({
          type: 'error',
          title: t('terminal_unavailable'),
          description: error instanceof Error ? error.message : t('terminal_unavailable'),
        })
      })
    return () => {
      cancelled = true
    }
  }, [addToast, questId, reloadSessions, shouldAutoEnsureTerminal])

  React.useEffect(() => {
    setSessionStatus(selectedSession?.status ?? null)
    setExitCode(selectedSession?.exit_code ?? null)
    setStopReason(selectedSession?.stop_reason ?? null)
    setProgress(selectedSession?.last_progress ?? null)
  }, [
    selectedSession?.bash_id,
    selectedSession?.exit_code,
    selectedSession?.last_progress,
    selectedSession?.status,
    selectedSession?.stop_reason,
  ])

  type TerminalHandlers = {
    write: (data: string, onComplete?: () => void) => void
    clear: () => void
    scrollToBottom: () => void
    focus: () => void
    isScrolledToBottom?: (thresholdPx?: number) => boolean
  }

  const terminalHandlersRef = React.useRef<TerminalHandlers | null>(null)
  const pendingOutputRef = React.useRef<string>('')
  const restoreRequestRef = React.useRef(0)
  const liveConnectRequestRef = React.useRef(0)
  const liveSocketRef = React.useRef<WebSocket | null>(null)
  const liveSocketSessionIdRef = React.useRef<string | null>(null)
  const liveReadyRef = React.useRef(false)
  const intentionalDetachRef = React.useRef(false)
  const pendingLiveMessagesRef = React.useRef<string[]>([])

  const appendToTerminal = React.useCallback((text: string) => {
    if (!text) return
    const handlers = terminalHandlersRef.current
    if (!handlers) {
      pendingOutputRef.current += text
      return
    }
    const shouldAutoScroll = handlers.isScrolledToBottom?.() ?? true
    handlers.write(text, () => {
      if (shouldAutoScroll) {
        handlers.scrollToBottom()
      }
    })
  }, [])

  const resetTerminal = React.useCallback(() => {
    pendingOutputRef.current = ''
    terminalHandlersRef.current?.clear()
  }, [])

  const flushPendingLiveMessages = React.useCallback(() => {
    const ws = liveSocketRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN || !liveReadyRef.current) {
      return
    }
    while (pendingLiveMessagesRef.current.length) {
      const next = pendingLiveMessagesRef.current.shift()
      if (!next) continue
      ws.send(next)
    }
  }, [])

  const detachLiveSocket = React.useCallback((reason = 'detach') => {
    const ws = liveSocketRef.current
    liveSocketRef.current = null
    liveSocketSessionIdRef.current = null
    liveReadyRef.current = false
    pendingLiveMessagesRef.current = []
    setLiveConnected(false)
    if (!ws) return
    intentionalDetachRef.current = true
    try {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'detach', reason }))
      }
    } catch {
      // Ignore detach send errors.
    }
    try {
      ws.close()
    } catch {
      // Ignore close errors.
    }
  }, [])

  React.useEffect(() => {
    return () => {
      detachLiveSocket('unmount')
    }
  }, [detachLiveSocket])

  const replayRestoredEntry = React.useCallback(
    (entry: { line?: string | null; stream?: string | null }) => {
      const line = entry.line ?? ''
      const stream = String(entry.stream || '')
      if (!line && stream !== 'carriage') {
        appendToTerminal('\n')
        return
      }
      const marker = parseBashStatusMarker(line)
      if (marker) {
        setSessionStatus(marker.status)
        setExitCode(marker.exitCode)
        setStopReason(marker.reason)
        return
      }
      if (stream === 'carriage') {
        appendToTerminal(`\r${line}`)
        return
      }
      if (stream === 'partial' || stream === 'prompt') {
        appendToTerminal(line)
        return
      }
      if (stream === 'system' && !line.trim()) {
        return
      }
      appendToTerminal(`${line}\n`)
    },
    [appendToTerminal]
  )

  const reloadSelectedLogs = React.useCallback(
    async (bashId: string) => {
      const requestId = restoreRequestRef.current + 1
      restoreRequestRef.current = requestId
      setLogsLoading(true)
      setLogsError(null)
      try {
        const payload = await restoreTerminalSession(questId, bashId, {
          commands: 50,
          output: 1000,
        })
        if (restoreRequestRef.current !== requestId) return
        restorePreviewRequestRef.current = requestId
        setRestorePreview(buildTerminalRestorePreview(payload))
        resetTerminal()
        payload.tail.forEach((entry) => {
          replayRestoredEntry({ line: entry.line ?? '', stream: entry.stream })
        })
        setSessionStatus(payload.session?.status ?? payload.status ?? null)
        setExitCode(payload.session?.exit_code ?? null)
        setStopReason(payload.session?.stop_reason ?? null)
        setProgress(payload.session?.last_progress ?? null)
      } catch (error) {
        if (restoreRequestRef.current !== requestId) return
        setLogsError(
          error instanceof Error ? error.message : 'Failed to load terminal output.'
        )
        setRestorePreview({ latestCommands: [], visibleLines: [] })
        resetTerminal()
      } finally {
        if (restoreRequestRef.current === requestId) {
          setLogsLoading(false)
        }
      }
    },
    [questId, replayRestoredEntry, resetTerminal]
  )

  const sendLiveEnvelope = React.useCallback(
    (payload: Record<string, unknown>) => {
      const encoded = JSON.stringify(payload)
      const ws = liveSocketRef.current
      if (!selectedSessionBashId) {
        return false
      }
      if (!ws || liveSocketSessionIdRef.current !== selectedSessionBashId) {
        pendingLiveMessagesRef.current.push(encoded)
        return true
      }
      if (ws.readyState !== WebSocket.OPEN || !liveReadyRef.current) {
        pendingLiveMessagesRef.current.push(encoded)
        return true
      }
      ws.send(encoded)
      return true
    },
    [selectedSessionBashId]
  )

  const openLiveSession = React.useCallback(
    async (bashId: string) => {
      const requestId = liveConnectRequestRef.current + 1
      liveConnectRequestRef.current = requestId
      detachLiveSocket('switch')
      resetTerminal()
      setLogsLoading(true)
      setLogsError(null)
      try {
        const payload = await attachTerminalSession(questId, bashId)
        if (liveConnectRequestRef.current !== requestId) return
        const locationUrl = typeof window !== 'undefined' ? new URL(window.location.href) : new URL('http://127.0.0.1:20999')
        const protocol = locationUrl.protocol === 'https:' ? 'wss:' : 'ws:'
        const socketUrl = `${protocol}//${locationUrl.hostname}:${payload.port}${payload.path}?token=${encodeURIComponent(payload.token)}`
        const ws = new WebSocket(socketUrl)
        ws.binaryType = 'arraybuffer'
        intentionalDetachRef.current = false
        liveReadyRef.current = false
        liveSocketRef.current = ws
        liveSocketSessionIdRef.current = bashId
        setSessionStatus(payload.session?.status ?? null)
        setExitCode(payload.session?.exit_code ?? null)
        setStopReason(payload.session?.stop_reason ?? null)
        setProgress(payload.session?.last_progress ?? null)

        ws.onmessage = (event) => {
          if (liveConnectRequestRef.current !== requestId) return
          if (typeof event.data === 'string') {
            try {
              const control = JSON.parse(event.data) as Record<string, unknown>
              const eventType = String(control.type || '')
              if (eventType === 'ready') {
                liveReadyRef.current = true
                setLiveConnected(true)
                setLogsLoading(false)
                setLogsError(null)
                setSessionStatus(String(control.status || payload.session?.status || 'running'))
                flushPendingLiveMessages()
                return
              }
              if (eventType === 'exit') {
                setLiveConnected(false)
                setLogsLoading(false)
                setSessionStatus(String(control.status || 'completed'))
                setExitCode(typeof control.exit_code === 'number' ? control.exit_code : null)
                setStopReason(typeof control.stop_reason === 'string' ? control.stop_reason : null)
                void Promise.allSettled([reloadSessions(), onRefresh()])
                return
              }
              if (eventType === 'error') {
                setLogsLoading(false)
                setLogsError(String(control.message || 'Terminal live connection failed.'))
                return
              }
              if (eventType === 'pong') {
                return
              }
            } catch {
              appendToTerminal(event.data)
              return
            }
            appendToTerminal(event.data)
            return
          }
          if (event.data instanceof ArrayBuffer) {
            const text = new TextDecoder('utf-8').decode(new Uint8Array(event.data))
            appendToTerminal(text)
            return
          }
          if (event.data instanceof Blob) {
            void event.data.arrayBuffer().then((buffer) => {
              if (liveConnectRequestRef.current !== requestId) return
              const text = new TextDecoder('utf-8').decode(new Uint8Array(buffer))
              appendToTerminal(text)
            })
          }
        }

        ws.onerror = () => {
          if (liveConnectRequestRef.current !== requestId) return
          setLogsError('Terminal live connection failed.')
        }

        ws.onclose = () => {
          if (liveSocketRef.current === ws) {
            liveSocketRef.current = null
            liveSocketSessionIdRef.current = null
          }
          liveReadyRef.current = false
          setLiveConnected(false)
          if (intentionalDetachRef.current) {
            intentionalDetachRef.current = false
            return
          }
          if (liveConnectRequestRef.current !== requestId) return
          setLogsLoading(false)
          void Promise.allSettled([reloadSessions(), onRefresh()])
        }
      } catch (error) {
        if (liveConnectRequestRef.current !== requestId) return
        setLiveConnected(false)
        pendingLiveMessagesRef.current = []
        const message = error instanceof Error ? error.message : 'Unable to attach to terminal.'
        setLogsError(message)
        await reloadSelectedLogs(bashId)
      }
    },
    [appendToTerminal, detachLiveSocket, flushPendingLiveMessages, onRefresh, questId, reloadSelectedLogs, reloadSessions, resetTerminal]
  )

  React.useEffect(() => {
    restoreRequestRef.current += 1
    liveConnectRequestRef.current += 1
    detachLiveSocket('session-change')
    if (!selectedSession?.bash_id) {
      setLogsError(null)
      setLogsLoading(false)
      setLiveConnected(false)
      setRestorePreview({ latestCommands: [], visibleLines: [] })
      resetTerminal()
      return
    }
    setLogsError(null)
    setLogsLoading(true)
    if (selectedSession.status === 'running' || selectedSession.status === 'terminating') {
      void refreshRestorePreview(selectedSession.bash_id)
      void openLiveSession(selectedSession.bash_id)
      return
    }
    void reloadSelectedLogs(selectedSession.bash_id)
  }, [detachLiveSocket, openLiveSession, reloadSelectedLogs, resetTerminal, selectedSession?.bash_id, selectedSession?.status])

  const handleRefresh = React.useCallback(async () => {
    await Promise.allSettled([reloadSessions(), onRefresh()])
    if (!selectedSession?.bash_id) return
    if (selectedSession.status === 'running' || selectedSession.status === 'terminating') {
      await openLiveSession(selectedSession.bash_id)
      return
    }
    await reloadSelectedLogs(selectedSession.bash_id)
  }, [onRefresh, openLiveSession, reloadSelectedLogs, reloadSessions, selectedSession?.bash_id, selectedSession?.status])

  const handleStop = React.useCallback(async () => {
    if (!selectedSession) return
    setStopPending(true)
    try {
      await stopBashSession(questId, selectedSession.bash_id, {
        reason: 'Stopped from terminal panel',
      })
      await Promise.allSettled([reloadSessions(), onRefresh()])
    } finally {
      setStopPending(false)
    }
  }, [onRefresh, questId, reloadSessions, selectedSession])

  const handleNewTerminal = React.useCallback(async () => {
    try {
      const response = await ensureTerminalSession(questId, {
        createNew: true,
        label: `terminal-${terminalSessions.length + 1}`,
        source: 'web-react',
      })
      await reloadSessions()
      setSelectedSessionId(response.session.bash_id)
      window.setTimeout(() => {
        terminalHandlersRef.current?.focus()
      }, 80)
    } catch (error) {
      addToast({
        type: 'error',
        title: 'Failed to create terminal',
        description: error instanceof Error ? error.message : 'Unable to create terminal session.',
      })
    }
  }, [addToast, questId, reloadSessions, terminalSessions.length])

  const handleStartDefaultTerminal = React.useCallback(async () => {
    try {
      const response = await ensureTerminalSession(questId, {
        source: 'web-react',
      })
      await reloadSessions()
      setSelectedSessionId(response.session.bash_id)
      window.setTimeout(() => {
        terminalHandlersRef.current?.focus()
      }, 80)
    } catch (error) {
      addToast({
        type: 'error',
        title: t('terminal_start_failed'),
        description: error instanceof Error ? error.message : t('terminal_start_failed'),
      })
    }
  }, [addToast, questId, reloadSessions, t])

  const handleTerminalInput = React.useCallback(
    (data: string) => {
      if (!data || !selectedSessionBashId) return
      if (selectedSessionStatus !== 'running' && selectedSessionStatus !== 'terminating') {
        return
      }
      sendLiveEnvelope({ type: 'input', data })
      if (data.includes('\r') || data.includes('\n')) {
        if (restorePreviewTimerRef.current != null) {
          window.clearTimeout(restorePreviewTimerRef.current)
        }
        restorePreviewTimerRef.current = window.setTimeout(() => {
          void refreshRestorePreview(selectedSessionBashId)
        }, 500)
      }
    },
    [refreshRestorePreview, selectedSessionBashId, selectedSessionStatus, sendLiveEnvelope]
  )

  const handleTerminalBinaryInput = React.useCallback(
    (data: string) => {
      if (!data || !selectedSessionBashId) return
      if (selectedSessionStatus !== 'running' && selectedSessionStatus !== 'terminating') {
        return
      }
      sendLiveEnvelope({ type: 'binary_input', data: btoa(data) })
    },
    [selectedSessionBashId, selectedSessionStatus, sendLiveEnvelope]
  )

  const handleTerminalResize = React.useCallback(
    (cols: number, rows: number) => {
      if (!selectedSessionBashId) return
      if (selectedSessionStatus !== 'running' && selectedSessionStatus !== 'terminating') {
        return
      }
      sendLiveEnvelope({ type: 'resize', cols, rows })
    },
    [selectedSessionBashId, selectedSessionStatus, sendLiveEnvelope]
  )

  return (
    <div className="h-full min-h-0 overflow-hidden bg-[var(--lab-surface-muted)]">
      <div className="flex h-full min-h-0 overflow-hidden">
        <div className="w-[320px] shrink-0 border-r border-black/[0.08] bg-[linear-gradient(180deg,rgba(255,255,255,0.86),rgba(244,239,233,0.94))] p-3 shadow-card dark:border-white/[0.10] dark:bg-[linear-gradient(180deg,rgba(255,255,255,0.06),rgba(255,255,255,0.03))]">
          <div className="flex items-center justify-between gap-3 px-1 pb-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              {t('terminal_panel_list_title')}
            </div>
            <div className="flex items-center gap-2">
              <StatusPill>{formatBashSessionStatus(connection.status)}</StatusPill>
              <Button
                type="button"
                size="icon"
                variant="outline"
                onClick={() => {
                  void handleNewTerminal()
                }}
                className="h-9 w-9 rounded-full border-black/[0.08] bg-white/[0.84] shadow-sm backdrop-blur hover:bg-white dark:border-white/[0.10] dark:bg-[rgba(18,18,18,0.72)]"
                title={t('terminal_new')}
              >
                <Plus className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <div className="feed-scrollbar h-[calc(100%-3.25rem)] space-y-2 overflow-auto pr-1">
            {!terminalSessions.length ? (
              <div className="rounded-[20px] border border-dashed border-black/[0.10] px-3 py-4 text-sm text-muted-foreground dark:border-white/[0.12]">
                <div>{t('terminal_none')}</div>
                {shouldAutoEnsureTerminal ? null : (
                  <div className="mt-3 flex flex-col gap-2">
                    <div className="text-xs leading-5 text-muted-foreground">
                      {t('terminal_windows_manual_start')}
                    </div>
                    <div>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          void handleStartDefaultTerminal()
                        }}
                        className="rounded-full"
                      >
                        {t('terminal_start')}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              terminalSessions.map((session) => {
                const isActive = session.bash_id === selectedSession?.bash_id
                return (
                  <button
                    key={session.bash_id}
                    type="button"
                    onClick={() => setSelectedSessionId(session.bash_id)}
                    className={cn(
                      'w-full rounded-[20px] border px-3 py-3 text-left transition',
                      isActive
                        ? 'border-[#9b8352]/50 bg-[#9b8352]/[0.08] shadow-sm'
                        : 'border-black/[0.06] bg-white/[0.56] hover:border-black/[0.10] hover:bg-white/[0.78] dark:border-white/[0.08] dark:bg-white/[0.03] dark:hover:bg-white/[0.05]'
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="truncate text-sm font-semibold text-foreground">
                            {session.label || session.bash_id}
                          </div>
                          {isActiveBashSession(session.status) ? <RunningTag /> : null}
                        </div>
                        <div className="mt-1 truncate text-xs text-muted-foreground">
                          {session.workdir || 'project root'}
                        </div>
                      </div>
                      <StatusPill>{formatBashSessionStatus(session.status)}</StatusPill>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                      <span>{formatRelativeTime(session.started_at)}</span>
                      <span>·</span>
                      <span>{session.mode}</span>
                    </div>
                  </button>
                )
              })
            )}
          </div>
        </div>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
            <div className="flex items-center justify-between gap-3">
              <WorkspaceRefreshButton onRefresh={handleRefresh} label="Refresh terminal" />
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                {logsLoading ? <span>loading…</span> : null}
                {logsError ? (
                  <span className="text-[#b42318] dark:text-[#ffb4b4]">{logsError}</span>
                ) : null}
              </div>
            </div>
            {selectedSession ? (
              <div className="min-h-0 flex-1 overflow-hidden rounded-[24px] border border-black/[0.10] bg-[#0f1115] shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] dark:border-white/[0.10]">
                <div className="h-full min-h-0 px-4 py-4">
                  <EnhancedTerminal
                    onInput={handleTerminalInput}
                    onBinary={handleTerminalBinaryInput}
                    onResize={handleTerminalResize}
                    resizeKey={selectedSessionBashId}
                    onReady={(handlers) => {
                      terminalHandlersRef.current = handlers
                      if (pendingOutputRef.current) {
                        const payload = pendingOutputRef.current
                        pendingOutputRef.current = ''
                        handlers.write(payload, () => {
                          handlers.scrollToBottom()
                        })
                      }
                      window.setTimeout(() => handlers.focus(), 60)
                    }}
                    searchOpen={false}
                    onSearchOpenChange={() => {}}
                    appearance="terminal"
                    autoFocus={false}
                    showHeader={false}
                    scrollback={20000}
                    convertEol={false}
                  />
                </div>
              </div>
            ) : (
              <div className="flex min-h-0 flex-1 items-center justify-center rounded-[24px] border border-dashed border-black/[0.10] bg-[rgba(255,255,255,0.42)] px-6 py-6 text-sm text-muted-foreground dark:border-white/[0.12] dark:bg-[rgba(255,255,255,0.02)]">
                <div className="max-w-md text-center">
                  <div className="font-medium text-foreground">
                    {shouldAutoEnsureTerminal ? 'Preparing terminal…' : t('terminal_none')}
                  </div>
                  <div className="mt-2 leading-7">
                    {shouldAutoEnsureTerminal
                      ? 'DeepScientist is creating the default interactive terminal session for this workspace.'
                      : t('terminal_windows_manual_start')}
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="flex items-center justify-between gap-3 border-t border-black/[0.08] px-4 py-3 text-xs text-muted-foreground dark:border-white/[0.10]">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <StatusPill>
                {liveConnected
                  ? 'live'
                  : formatBashSessionStatus(sessionStatus ?? selectedSession?.status ?? 'idle')}
              </StatusPill>
              {selectedSession?.bash_id ? <StatusPill mono>{selectedSession.bash_id}</StatusPill> : null}
              {selectedSession?.workdir ? <StatusPill mono>{selectedSession.workdir}</StatusPill> : null}
              {progress && (getProgressPercent(progress) ?? progress.percent) != null ? (
                <StatusPill>{`${(getProgressPercent(progress) ?? progress.percent ?? 0).toFixed(0)}%`}</StatusPill>
              ) : null}
              {exitCode != null ? <StatusPill>exit {exitCode}</StatusPill> : null}
              {stopReason ? <span className="truncate">{stopReason}</span> : null}
            </div>
            {selectedSession &&
            (selectedSession.status === 'running' || selectedSession.status === 'terminating') ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => {
                  void handleStop()
                }}
                disabled={stopPending}
                className="h-8 rounded-full border-black/[0.08] bg-white/[0.84] px-3 text-[11px] shadow-sm backdrop-blur hover:bg-white dark:border-white/[0.10] dark:bg-[rgba(18,18,18,0.72)] dark:hover:bg-[rgba(24,24,24,0.9)]"
              >
                <Square className="mr-1.5 h-3.5 w-3.5" />
                {stopPending ? 'Stopping…' : 'Stop'}
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}

function QuestDeepScientistBashPane({
  questId,
  onRefresh,
  execSessions,
  connection,
  reloadSessions,
}: {
  questId: string
  onRefresh: () => Promise<void>
  execSessions: BashSession[]
  connection: QuestTerminalConnection
  reloadSessions: () => Promise<void>
}) {
  const [selectedSessionId, setSelectedSessionId] = React.useState<string | null>(null)
  const [stopPending, setStopPending] = React.useState(false)
  const [logsLoading, setLogsLoading] = React.useState(false)
  const [logsError, setLogsError] = React.useState<string | null>(null)
  const [liveConnected, setLiveConnected] = React.useState(false)
  const [liveStatus, setLiveStatus] = React.useState<string | null>(null)
  const [liveExitCode, setLiveExitCode] = React.useState<number | null>(null)
  const [liveStopReason, setLiveStopReason] = React.useState<string | null>(null)
  const [liveProgress, setLiveProgress] = React.useState<BashProgress | null>(null)

  const selectedSession = React.useMemo<BashSession | null>(() => {
    if (!execSessions.length) return null
    return execSessions.find((session) => session.bash_id === selectedSessionId) ?? execSessions[0]
  }, [execSessions, selectedSessionId])
  const selectedSessionBashId = selectedSession?.bash_id ?? null
  const selectedSessionStatus = selectedSession?.status ?? null

  React.useEffect(() => {
    if (!execSessions.length) {
      setSelectedSessionId(null)
      return
    }
    if (!selectedSessionId || !execSessions.some((session) => session.bash_id === selectedSessionId)) {
      const runningSession =
        execSessions.find((session) => isActiveBashSession(session.status)) ?? execSessions[0]
      setSelectedSessionId(runningSession.bash_id)
    }
  }, [execSessions, selectedSessionId])

  React.useEffect(() => {
    setLogsLoading(false)
    setLogsError(null)
    setLiveConnected(false)
    setLiveStatus(null)
    setLiveExitCode(null)
    setLiveStopReason(null)
    setLiveProgress(null)
  }, [selectedSession?.bash_id])

  type TerminalHandlers = {
    write: (data: string, onComplete?: () => void) => void
    clear: () => void
    scrollToBottom: () => void
    focus: () => void
    isScrolledToBottom?: (thresholdPx?: number) => boolean
  }

  const terminalHandlersRef = React.useRef<TerminalHandlers | null>(null)
  const pendingOutputRef = React.useRef('')
  const restoreRequestRef = React.useRef(0)
  const liveConnectRequestRef = React.useRef(0)
  const liveSocketRef = React.useRef<WebSocket | null>(null)
  const liveSocketSessionIdRef = React.useRef<string | null>(null)
  const liveReadyRef = React.useRef(false)
  const intentionalDetachRef = React.useRef(false)
  const pendingLiveMessagesRef = React.useRef<string[]>([])

  const appendToTerminal = React.useCallback((text: string) => {
    const handlers = terminalHandlersRef.current
    if (!handlers) {
      pendingOutputRef.current += text
      return
    }
    const shouldAutoScroll = handlers.isScrolledToBottom?.() ?? true
    handlers.write(text, () => {
      if (shouldAutoScroll) {
        handlers.scrollToBottom()
      }
    })
  }, [])

  const resetTerminal = React.useCallback(() => {
    pendingOutputRef.current = ''
    terminalHandlersRef.current?.clear()
  }, [])

  const writeSessionPrelude = React.useCallback(
    (session: BashSession | null) => {
      if (!session) return
      const workdirLabel = String(session.workdir || '').trim() || '~'
      const commandLabel = String(session.command || '').trim() || 'bash_exec'
      appendToTerminal(`${workdirLabel}$ ${commandLabel}\r\n\r\n`)
    },
    [appendToTerminal]
  )

  const flushPendingLiveMessages = React.useCallback(() => {
    const ws = liveSocketRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN || !liveReadyRef.current) {
      return
    }
    while (pendingLiveMessagesRef.current.length) {
      const next = pendingLiveMessagesRef.current.shift()
      if (!next) continue
      ws.send(next)
    }
  }, [])

  const detachLiveSocket = React.useCallback((reason = 'detach') => {
    const ws = liveSocketRef.current
    liveSocketRef.current = null
    liveSocketSessionIdRef.current = null
    liveReadyRef.current = false
    pendingLiveMessagesRef.current = []
    setLiveConnected(false)
    if (!ws) return
    intentionalDetachRef.current = true
    try {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'detach', reason }))
      }
    } catch {
      // Ignore detach send errors.
    }
    try {
      ws.close()
    } catch {
      // Ignore close errors.
    }
  }, [])

  React.useEffect(() => {
    return () => {
      detachLiveSocket('unmount')
    }
  }, [detachLiveSocket])

  const replayExecLogEntry = React.useCallback(
    (entry: { line?: string | null; stream?: string | null }) => {
      const rawLine = entry.line ?? ''
      const stream = String(entry.stream || '')
      if (isBashProgressMarker(rawLine)) {
        const nextProgress = parseBashProgressMarker(rawLine)
        if (nextProgress) {
          setLiveProgress(nextProgress as BashProgress)
        }
        return
      }
      const marker = parseBashStatusMarker(rawLine)
      if (marker) {
        setLiveStatus(marker.status)
        setLiveExitCode(marker.exitCode)
        setLiveStopReason(marker.reason)
        return
      }
      if (!rawLine && stream !== 'carriage') {
        appendToTerminal('\n')
        return
      }
      const parsed = splitBashLogLine(rawLine)
      if (parsed.kind === 'carriage') {
        appendToTerminal(`\r\x1b[K${parsed.text}`)
        return
      }
      if (stream === 'prompt' || stream === 'partial') {
        appendToTerminal(parsed.text)
        return
      }
      if (stream === 'system' && !parsed.text.trim()) {
        return
      }
      appendToTerminal(`${parsed.text}\n`)
    },
    [appendToTerminal]
  )

  const reloadSelectedLogs = React.useCallback(
    async (session: BashSession) => {
      const requestId = restoreRequestRef.current + 1
      restoreRequestRef.current = requestId
      setLogsLoading(true)
      setLogsError(null)
      try {
        const payload = await restoreTerminalSession(questId, session.bash_id, {
          commands: 10,
          output: 1000,
        })
        if (restoreRequestRef.current !== requestId) return
        resetTerminal()
        writeSessionPrelude(session)
        payload.tail.forEach((entry) => {
          replayExecLogEntry({ line: entry.line ?? '', stream: entry.stream })
        })
        setLiveStatus(payload.session?.status ?? payload.status ?? null)
        setLiveExitCode(payload.session?.exit_code ?? null)
        setLiveStopReason(payload.session?.stop_reason ?? null)
        setLiveProgress(payload.session?.last_progress ?? null)
      } catch (error) {
        if (restoreRequestRef.current !== requestId) return
        setLogsError(
          error instanceof Error ? error.message : 'Failed to load bash session output.'
        )
        resetTerminal()
        writeSessionPrelude(session)
      } finally {
        if (restoreRequestRef.current === requestId) {
          setLogsLoading(false)
        }
      }
    },
    [questId, replayExecLogEntry, resetTerminal, writeSessionPrelude]
  )

  const sendLiveEnvelope = React.useCallback(
    (payload: Record<string, unknown>) => {
      const encoded = JSON.stringify(payload)
      const ws = liveSocketRef.current
      if (!selectedSessionBashId) {
        return false
      }
      if (!ws || liveSocketSessionIdRef.current !== selectedSessionBashId) {
        pendingLiveMessagesRef.current.push(encoded)
        return true
      }
      if (ws.readyState !== WebSocket.OPEN || !liveReadyRef.current) {
        pendingLiveMessagesRef.current.push(encoded)
        return true
      }
      ws.send(encoded)
      return true
    },
    [selectedSessionBashId]
  )

  const openLiveSession = React.useCallback(
    async (session: BashSession) => {
      const requestId = liveConnectRequestRef.current + 1
      liveConnectRequestRef.current = requestId
      detachLiveSocket('switch')
      resetTerminal()
      writeSessionPrelude(session)
      setLogsLoading(true)
      setLogsError(null)
      try {
        const payload = await attachTerminalSession(questId, session.bash_id)
        if (liveConnectRequestRef.current !== requestId) return
        const locationUrl =
          typeof window !== 'undefined'
            ? new URL(window.location.href)
            : new URL('http://127.0.0.1:20999')
        const protocol = locationUrl.protocol === 'https:' ? 'wss:' : 'ws:'
        const socketUrl = `${protocol}//${locationUrl.hostname}:${payload.port}${payload.path}?token=${encodeURIComponent(payload.token)}`
        const ws = new WebSocket(socketUrl)
        ws.binaryType = 'arraybuffer'
        intentionalDetachRef.current = false
        liveReadyRef.current = false
        liveSocketRef.current = ws
        liveSocketSessionIdRef.current = session.bash_id
        setLiveStatus(payload.session?.status ?? null)
        setLiveExitCode(payload.session?.exit_code ?? null)
        setLiveStopReason(payload.session?.stop_reason ?? null)
        setLiveProgress(payload.session?.last_progress ?? null)

        ws.onmessage = (event) => {
          if (liveConnectRequestRef.current !== requestId) return
          if (typeof event.data === 'string') {
            try {
              const control = JSON.parse(event.data) as Record<string, unknown>
              const eventType = String(control.type || '')
              if (eventType === 'ready') {
                liveReadyRef.current = true
                setLiveConnected(true)
                setLogsLoading(false)
                setLogsError(null)
                setLiveStatus(String(control.status || payload.session?.status || 'running'))
                flushPendingLiveMessages()
                return
              }
              if (eventType === 'exit') {
                setLiveConnected(false)
                setLogsLoading(false)
                setLiveStatus(String(control.status || 'completed'))
                setLiveExitCode(typeof control.exit_code === 'number' ? control.exit_code : null)
                setLiveStopReason(typeof control.stop_reason === 'string' ? control.stop_reason : null)
                void Promise.allSettled([reloadSessions(), onRefresh()])
                return
              }
              if (eventType === 'error') {
                setLogsLoading(false)
                setLogsError(String(control.message || 'Bash live connection failed.'))
                return
              }
              if (eventType === 'pong') {
                return
              }
            } catch {
              appendToTerminal(event.data)
              return
            }
            appendToTerminal(event.data)
            return
          }
          if (event.data instanceof ArrayBuffer) {
            const text = new TextDecoder('utf-8').decode(new Uint8Array(event.data))
            appendToTerminal(text)
            return
          }
          if (event.data instanceof Blob) {
            void event.data.arrayBuffer().then((buffer) => {
              if (liveConnectRequestRef.current !== requestId) return
              const text = new TextDecoder('utf-8').decode(new Uint8Array(buffer))
              appendToTerminal(text)
            })
          }
        }

        ws.onerror = () => {
          if (liveConnectRequestRef.current !== requestId) return
          setLogsError('Bash live connection failed.')
        }

        ws.onclose = () => {
          if (liveSocketRef.current === ws) {
            liveSocketRef.current = null
            liveSocketSessionIdRef.current = null
          }
          liveReadyRef.current = false
          setLiveConnected(false)
          if (intentionalDetachRef.current) {
            intentionalDetachRef.current = false
            return
          }
          if (liveConnectRequestRef.current !== requestId) return
          setLogsLoading(false)
          void Promise.allSettled([reloadSessions(), onRefresh()])
        }
      } catch (error) {
        if (liveConnectRequestRef.current !== requestId) return
        setLiveConnected(false)
        pendingLiveMessagesRef.current = []
        const message =
          error instanceof Error ? error.message : 'Unable to attach to bash session.'
        setLogsError(message)
        await reloadSelectedLogs(session)
      }
    },
    [
      appendToTerminal,
      detachLiveSocket,
      flushPendingLiveMessages,
      onRefresh,
      questId,
      reloadSelectedLogs,
      reloadSessions,
      resetTerminal,
      writeSessionPrelude,
    ]
  )

  React.useEffect(() => {
    restoreRequestRef.current += 1
    liveConnectRequestRef.current += 1
    detachLiveSocket('session-change')
    if (!selectedSession?.bash_id) {
      setLogsError(null)
      setLogsLoading(false)
      setLiveConnected(false)
      resetTerminal()
      return
    }
    setLogsError(null)
    setLogsLoading(true)
    if (isActiveBashSession(selectedSession.status)) {
      void openLiveSession(selectedSession)
      return
    }
    void reloadSelectedLogs(selectedSession)
  }, [
    detachLiveSocket,
    openLiveSession,
    reloadSelectedLogs,
    resetTerminal,
    selectedSession,
  ])

  const handleRefresh = React.useCallback(async () => {
    await Promise.allSettled([reloadSessions(), onRefresh()])
    if (!selectedSession?.bash_id) return
    if (isActiveBashSession(selectedSession.status)) {
      await openLiveSession(selectedSession)
      return
    }
    await reloadSelectedLogs(selectedSession)
  }, [onRefresh, openLiveSession, reloadSelectedLogs, reloadSessions, selectedSession])

  const handleStop = React.useCallback(async () => {
    if (!selectedSession) return
    setStopPending(true)
    try {
      await stopBashSession(questId, selectedSession.bash_id, {
        reason: 'Stopped from DeepScientist bash panel',
      })
      await Promise.allSettled([reloadSessions(), onRefresh()])
    } finally {
      setStopPending(false)
    }
  }, [onRefresh, questId, reloadSessions, selectedSession])

  const handleTerminalInput = React.useCallback(
    (data: string) => {
      if (!data || !selectedSessionBashId) return
      if (!isActiveBashSession(selectedSessionStatus)) {
        return
      }
      sendLiveEnvelope({ type: 'input', data })
    },
    [selectedSessionBashId, selectedSessionStatus, sendLiveEnvelope]
  )

  const handleTerminalBinaryInput = React.useCallback(
    (data: string) => {
      if (!data || !selectedSessionBashId) return
      if (!isActiveBashSession(selectedSessionStatus)) {
        return
      }
      sendLiveEnvelope({ type: 'binary_input', data: btoa(data) })
    },
    [selectedSessionBashId, selectedSessionStatus, sendLiveEnvelope]
  )

  const handleTerminalResize = React.useCallback(
    (cols: number, rows: number) => {
      if (!selectedSessionBashId) return
      if (!isActiveBashSession(selectedSessionStatus)) {
        return
      }
      sendLiveEnvelope({ type: 'resize', cols, rows })
    },
    [selectedSessionBashId, selectedSessionStatus, sendLiveEnvelope]
  )

  const effectiveStatus = liveStatus ?? selectedSession?.status ?? null
  const effectiveExitCode = liveExitCode ?? selectedSession?.exit_code ?? null
  const effectiveStopReason = liveStopReason ?? selectedSession?.stop_reason ?? null
  const effectiveProgress = liveProgress ?? selectedSession?.last_progress ?? null
  const effectiveProgressPercent =
    getProgressPercent(effectiveProgress) ?? effectiveProgress?.percent ?? null
  const commentSummary = summarizeBashComment(selectedSession?.comment)

  return (
    <div className="h-full min-h-0 overflow-hidden">
      <div className="flex h-full min-h-0 overflow-hidden">
        <div className="w-[320px] shrink-0 border-r border-black/[0.08] bg-[linear-gradient(180deg,rgba(255,255,255,0.86),rgba(244,239,233,0.94))] p-3 shadow-card dark:border-white/[0.10] dark:bg-[linear-gradient(180deg,rgba(255,255,255,0.06),rgba(255,255,255,0.03))]">
          <div className="flex items-center justify-between gap-3 px-1 pb-3">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                DeepScientist Bash
              </div>
              <div className="mt-1 text-[11px] text-muted-foreground">
                All agent `bash_exec` sessions for this project.
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StatusPill>{formatBashSessionStatus(connection.status)}</StatusPill>
              <WorkspaceRefreshButton onRefresh={handleRefresh} label="Refresh" />
            </div>
          </div>

          <div className="feed-scrollbar h-[calc(100%-4rem)] space-y-2 overflow-auto pr-1">
            {!execSessions.length ? (
              <div className="rounded-[20px] border border-dashed border-black/[0.10] px-3 py-4 text-sm text-muted-foreground dark:border-white/[0.12]">
                No DeepScientist bash sessions recorded yet.
              </div>
            ) : (
              execSessions.map((session) => {
                const isActive = session.bash_id === selectedSession?.bash_id
                const progressPercent =
                  getProgressPercent(session.last_progress) ?? session.last_progress?.percent ?? null
                const comment = summarizeBashComment(session.comment)
                return (
                  <button
                    key={session.bash_id}
                    type="button"
                    onClick={() => setSelectedSessionId(session.bash_id)}
                    className={cn(
                      'w-full rounded-[20px] border px-3 py-3 text-left transition',
                      isActive
                        ? 'border-[#9b8352]/50 bg-[#9b8352]/[0.08] shadow-sm'
                        : 'border-black/[0.06] bg-white/[0.56] hover:border-black/[0.10] hover:bg-white/[0.78] dark:border-white/[0.08] dark:bg-white/[0.03] dark:hover:bg-white/[0.05]'
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="truncate text-sm font-semibold text-foreground">
                            {summarizeBashCommand(session.command)}
                          </div>
                          {isActiveBashSession(session.status) ? <RunningTag /> : null}
                        </div>
                        <div className="mt-1 truncate text-xs text-muted-foreground">
                          {session.workdir || 'project root'}
                        </div>
                        {comment ? (
                          <div className="mt-2 line-clamp-2 text-[11px] text-muted-foreground">
                            {comment}
                          </div>
                        ) : null}
                      </div>
                      <StatusPill>{formatBashSessionStatus(session.status)}</StatusPill>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                      <span>{formatRelativeTime(session.started_at)}</span>
                      <span>·</span>
                      <span className="font-mono normal-case tracking-[0.02em]">{session.bash_id}</span>
                      {typeof session.run_age_seconds === 'number' ? (
                        <>
                          <span>·</span>
                          <span>{formatCompactDurationSeconds(session.run_age_seconds)}</span>
                        </>
                      ) : null}
                      {typeof progressPercent === 'number' ? (
                        <>
                          <span>·</span>
                          <span>{progressPercent.toFixed(0)}%</span>
                        </>
                      ) : null}
                    </div>
                  </button>
                )
              })
            )}
          </div>
        </div>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex min-h-0 flex-1 flex-col p-3">
            {selectedSession ? (
              <>
                <div className="min-h-0 flex-1 overflow-hidden rounded-[24px] border border-black/[0.10] bg-[#0f1115] shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] dark:border-white/[0.10]">
                  <div className="h-full min-h-0 p-2">
                    <EnhancedTerminal
                      onInput={handleTerminalInput}
                      onBinary={handleTerminalBinaryInput}
                      onResize={handleTerminalResize}
                      resizeKey={selectedSessionBashId}
                      onReady={(handlers) => {
                        terminalHandlersRef.current = handlers
                        if (pendingOutputRef.current) {
                          const payload = pendingOutputRef.current
                          pendingOutputRef.current = ''
                          handlers.write(payload, () => {
                            handlers.scrollToBottom()
                          })
                        }
                        window.setTimeout(() => handlers.focus(), 60)
                      }}
                      searchOpen={false}
                      onSearchOpenChange={() => {}}
                      appearance="terminal"
                      autoFocus={false}
                      showHeader={false}
                      scrollback={20000}
                      convertEol={false}
                    />
                  </div>
                </div>

                <div className="flex flex-wrap items-start justify-between gap-3 border-t border-black/[0.08] px-1 pb-1 pt-3 text-xs text-muted-foreground dark:border-white/[0.10]">
                  <div className="flex min-w-0 flex-1 flex-col gap-2">
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <StatusPill>
                        {liveConnected ? 'live' : formatBashSessionStatus(effectiveStatus ?? 'idle')}
                      </StatusPill>
                      <StatusPill mono>{selectedSession.bash_id}</StatusPill>
                      {selectedSession.workdir ? (
                        <StatusPill mono>{selectedSession.workdir}</StatusPill>
                      ) : null}
                      <StatusPill>{`started ${formatRelativeTime(selectedSession.started_at)}`}</StatusPill>
                      {typeof selectedSession.run_age_seconds === 'number' ? (
                        <StatusPill>{formatCompactDurationSeconds(selectedSession.run_age_seconds)}</StatusPill>
                      ) : null}
                      {typeof effectiveProgressPercent === 'number' ? (
                        <StatusPill>{`${effectiveProgressPercent.toFixed(0)}%`}</StatusPill>
                      ) : null}
                      {effectiveExitCode != null ? <StatusPill>exit {effectiveExitCode}</StatusPill> : null}
                      <StatusPill>{selectedSession.mode}</StatusPill>
                      {selectedSession.agent_instance_id ? (
                        <StatusPill mono>{selectedSession.agent_instance_id}</StatusPill>
                      ) : null}
                    </div>
                    <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-[11px] leading-5 text-muted-foreground">
                      <span className="max-w-full truncate">
                        {summarizeBashCommand(selectedSession.command, 200)}
                      </span>
                      {commentSummary ? (
                        <span className="max-w-full truncate">{commentSummary}</span>
                      ) : null}
                      {effectiveProgress?.desc ? (
                        <span className="max-w-full truncate">
                          {clampText(String(effectiveProgress.desc), 140)}
                        </span>
                      ) : null}
                      {effectiveStopReason ? (
                        <span className="max-w-full truncate text-[#b42318] dark:text-[#ffb4b4]">
                          {effectiveStopReason}
                        </span>
                      ) : null}
                      {logsLoading ? <span>loading…</span> : null}
                      {logsError ? (
                        <span className="max-w-full truncate text-[#b42318] dark:text-[#ffb4b4]">
                          {logsError}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  {isActiveBashSession(effectiveStatus) ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        void handleStop()
                      }}
                      disabled={stopPending}
                      className="h-9 rounded-full border-black/[0.08] bg-white/[0.84] px-3 text-[11px] shadow-sm backdrop-blur hover:bg-white dark:border-white/[0.10] dark:bg-[rgba(18,18,18,0.72)] dark:hover:bg-[rgba(24,24,24,0.9)]"
                    >
                      <Square className="mr-1.5 h-3.5 w-3.5" />
                      {stopPending ? 'Stopping…' : 'Stop'}
                    </Button>
                  ) : null}
                </div>
              </>
            ) : (
              <div className="flex h-full items-center justify-center rounded-[24px] border border-dashed border-black/[0.10] px-4 py-6 text-sm text-muted-foreground dark:border-white/[0.12]">
                Select a DeepScientist bash session to inspect its output.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function QuestTerminalSurface({
  questId,
  onRefresh,
}: {
  questId: string
  onRefresh: () => Promise<void>
}) {
  const { t } = useI18n('workspace')
  const {
    sessions,
    connection,
    reload: reloadSessions,
  } = useBashSessionStream({
    projectId: questId,
    enabled: Boolean(questId),
    limit: 120,
  })
  const [mode, setMode] = React.useState<QuestTerminalMode>('interactive')

  const terminalSessions = React.useMemo(
    () => sessions.filter((session) => String(session.kind || '').toLowerCase() === 'terminal'),
    [sessions]
  )
  const execSessions = React.useMemo(
    () => sessions.filter((session) => String(session.kind || '').toLowerCase() === 'exec'),
    [sessions]
  )
  const interactiveRunning = React.useMemo(
    () => terminalSessions.some((session) => isActiveBashSession(session.status)),
    [terminalSessions]
  )
  const execRunning = React.useMemo(
    () => execSessions.some((session) => isActiveBashSession(session.status)),
    [execSessions]
  )

  React.useEffect(() => {
    if (mode === 'interactive' && terminalSessions.length === 0 && execSessions.length > 0) {
      setMode('deepscientist-bash')
      return
    }
    if (mode === 'deepscientist-bash' && execSessions.length === 0 && terminalSessions.length > 0) {
      setMode('interactive')
    }
  }, [execSessions.length, mode, terminalSessions.length])

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-[var(--lab-surface-muted)]">
      <div className="flex items-center justify-between gap-3 border-b border-black/[0.08] px-4 py-3 dark:border-white/[0.10]">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-foreground">{t('terminal_panel_title')}</div>
          <div className="text-xs text-muted-foreground">
            {t('terminal_panel_subtitle')}
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <TerminalModeButton
            active={mode === 'interactive'}
            icon={<Terminal className="h-4 w-4" />}
            label={t('quest_workspace_terminal')}
            running={interactiveRunning}
            onClick={() => setMode('interactive')}
          />
          <TerminalModeButton
            active={mode === 'deepscientist-bash'}
            icon={<Sparkles className="h-4 w-4" />}
            label={t('terminal_recorded_sessions')}
            running={execRunning}
            onClick={() => setMode('deepscientist-bash')}
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        {mode === 'interactive' ? (
          <QuestInteractiveTerminalPane
            questId={questId}
            onRefresh={onRefresh}
            terminalSessions={terminalSessions}
            connection={connection}
            reloadSessions={reloadSessions}
          />
        ) : (
          <QuestDeepScientistBashPane
            questId={questId}
            onRefresh={onRefresh}
            execSessions={execSessions}
            connection={connection}
            reloadSessions={reloadSessions}
          />
        )}
      </div>
    </div>
  )
}

function QuestDetails({
  questId,
  snapshot,
  workflow,
  feed,
  documents,
  memory,
  branches,
  loading,
  restoring,
  connectionState,
  onOpenDocument,
  onOpenMemory,
  onRefresh,
  error,
}: {
  questId: string
  snapshot: ReturnType<typeof useQuestWorkspace>['snapshot']
  workflow: ReturnType<typeof useQuestWorkspace>['workflow']
  feed: ReturnType<typeof useQuestWorkspace>['feed']
  documents: ReturnType<typeof useQuestWorkspace>['documents']
  memory: ReturnType<typeof useQuestWorkspace>['memory']
  branches: GitBranchesPayload | null
  loading: boolean
  restoring: boolean
  connectionState: ReturnType<typeof useQuestWorkspace>['connectionState']
  onOpenDocument: (item: LinkItem) => void
  onOpenMemory: () => void
  onRefresh: () => Promise<void>
  error?: string | null
}) {
  const deferredFeed = React.useDeferredValue(feed)
  const deferredDocuments = React.useDeferredValue(documents)
  const deferredMemory = React.useDeferredValue(memory)
  const nodeCount = branches?.nodes.length ?? 0
  const ideaCount =
    branches?.nodes.filter((item) => item.branch_kind === 'idea').length ?? 0
  const analysisCount =
    branches?.nodes.filter(
      (item) => item.branch_kind === 'analysis' || item.mode === 'analysis'
    ).length ?? 0
  const recentFeed = React.useMemo(
    () => [...deferredFeed].slice(-12).reverse(),
    [deferredFeed]
  )
  const { sessions: runningBashSessions } = useBashSessionStream({
    projectId: questId,
    status: 'running',
    enabled: Boolean(questId),
    limit: 50,
  })
  const latestRunningBash = runningBashSessions[0] ?? null
  const [metricsTimeline, setMetricsTimeline] =
    React.useState<MetricsTimelinePayload | null>(null)
  const [baselineCompare, setBaselineCompare] =
    React.useState<BaselineComparePayload | null>(null)
  const latestRunningBashHint = React.useMemo(() => {
    if (!latestRunningBash) {
      return `${snapshot?.counts?.bash_session_count || 0} recorded sessions`
    }
    const progressPercent = getProgressPercent(latestRunningBash.last_progress)
    const command =
      latestRunningBash.command?.trim().replace(/\s+/g, ' ') || 'bash_exec'
    const compactCommand =
      command.length > 52 ? `${command.slice(0, 49).trimEnd()}...` : command
    return progressPercent == null
      ? compactCommand
      : `${compactCommand} · ${progressPercent.toFixed(0)}%`
  }, [latestRunningBash, snapshot?.counts?.bash_session_count])

  const changedFiles = React.useMemo<LinkItem[]>(
    () =>
      (workflow?.changed_files ?? []).slice(0, 12).map((item) => ({
        key: `${item.source}:${item.path}`,
        title: item.path,
        subtitle: item.source,
        badge: item.writable === false ? 'read-only' : 'live',
        documentId:
          item.document_id ||
          resolveQuestDocumentIdFromPath(item.path, snapshot),
      })),
    [snapshot, workflow?.changed_files]
  )

  const coreDocs = React.useMemo<LinkItem[]>(() => {
    const preferred = [
      ['status.md', 'Operational status'],
      ['plan.md', 'Accepted plan'],
      ['SUMMARY.md', 'Project summary'],
      ['brief.md', 'Original brief'],
    ] as const

    return preferred.map(([path, label]) => {
      const existing =
        deferredDocuments.find((item) => (item.path || '').endsWith(path)) ??
        deferredDocuments.find((item) => item.title === path)

      return {
        key: path,
        title: path,
        subtitle: existing?.title && existing.title !== path ? existing.title : label,
        badge: 'core',
        documentId: existing?.document_id || `path::${path}`,
      }
    })
  }, [deferredDocuments])

  const recentDocs = React.useMemo<LinkItem[]>(
    () =>
      deferredDocuments.slice(0, 10).map((item) => ({
        key: item.document_id,
        title: item.title,
        subtitle: item.path || item.source_scope || item.kind,
        badge: item.kind,
        documentId: item.document_id,
      })),
    [deferredDocuments]
  )

  const recentMemory = React.useMemo<LinkItem[]>(
    () =>
      deferredMemory.slice(0, 10).map((item, index) => ({
        key: `${item.document_id || item.path || 'memory'}-${index}`,
        title: item.title || item.path || 'Memory',
        subtitle: item.path || item.excerpt || item.type || null,
        badge: item.type || 'memory',
        documentId: item.document_id || null,
      })),
    [deferredMemory]
  )

  const recentArtifacts = React.useMemo<LinkItem[]>(
    () =>
      (snapshot?.recent_artifacts || []).slice(0, 8).map((item, index) => ({
        key: `${item.kind}:${item.path}:${index}`,
        title: item.payload?.summary || item.payload?.reason || item.kind,
        subtitle: item.path,
        badge: item.kind,
        documentId: resolveQuestDocumentIdFromPath(item.path, snapshot),
      })),
    [snapshot]
  )

  const recentRuns = React.useMemo<LinkItem[]>(
    () =>
      (snapshot?.recent_runs || []).slice(0, 6).map((item, index) => ({
        key: `${item.run_id || item.skill_id || 'run'}-${index}`,
        title: item.summary || item.skill_id || item.run_id || 'Run',
        subtitle: [
          item.status || null,
          item.model || null,
          item.updated_at ? `updated ${formatRelativeTime(item.updated_at)}` : null,
        ]
          .filter(Boolean)
          .join(' · '),
        badge: item.skill_id || 'run',
        documentId: resolveQuestDocumentIdFromPath(item.output_path, snapshot),
      })),
    [snapshot]
  )
  const optimizationFrontier = workflow?.optimization_frontier ?? null
  const workflowProjectionLabel = projectionStatusLabel(workflow)
  const branchProjectionLabel = projectionStatusLabel(branches)
  const projectionError =
    workflow?.projection_status?.error || branches?.projection_status?.error || null
  const projectionStatusCards = React.useMemo(
    () =>
      [
        {
          key: 'workflow',
          title: 'Workflow',
          message: workflowProjectionLabel,
          percent: projectionProgressValue(workflow),
        },
        {
          key: 'canvas',
          title: 'Canvas',
          message: branchProjectionLabel,
          percent: projectionProgressValue(branches),
        },
      ].filter((item) => Boolean(item.message)),
    [branchProjectionLabel, branches, workflow, workflowProjectionLabel]
  )

  const optimizationTopBranchItems = React.useMemo<LinkItem[]>(
    () =>
      (optimizationFrontier?.top_branches || []).map((branch, index) => ({
        key: `opt-branch:${branch.branch_name || index}`,
        title: branch.idea_title || branch.branch_name || 'Optimization line',
        subtitle: [
          branch.branch_no ? `branch #${branch.branch_no}` : null,
          branch.branch_name || null,
          branch.mechanism_family ? `family ${branch.mechanism_family}` : null,
          branch.change_layer ? `layer ${branch.change_layer}` : null,
          branch.source_lens ? `lens ${branch.source_lens}` : null,
          branch.method_brief ? clampText(branch.method_brief, 120) : null,
          formatSelectionScoreSummary(branch.selection_scores || null),
          branch.latest_main_experiment?.run_id ? `run ${branch.latest_main_experiment.run_id}` : null,
          branch.latest_main_experiment?.recommended_next_route
            ? `next ${branch.latest_main_experiment.recommended_next_route}`
            : null,
          branch.latest_main_experiment?.delta_vs_baseline != null
            ? `Δ ${formatMetricValue(branch.latest_main_experiment.delta_vs_baseline as number | null | undefined)}`
            : null,
        ]
          .filter(Boolean)
          .join(' · '),
        badge: branch.has_main_result ? 'line' : 'pre-result',
      })),
    [optimizationFrontier?.top_branches]
  )

  const optimizationCandidateBriefItems = React.useMemo<LinkItem[]>(
    () =>
      (optimizationFrontier?.candidate_briefs || []).map((candidate, index) => ({
        key: `opt-brief:${candidate.idea_id || index}`,
        title: candidate.title || candidate.idea_id || 'Candidate brief',
        subtitle: [
          candidate.mechanism_family ? `family ${candidate.mechanism_family}` : null,
          candidate.change_layer ? `layer ${candidate.change_layer}` : null,
          candidate.source_lens ? `lens ${candidate.source_lens}` : null,
          candidate.method_brief ? clampText(candidate.method_brief, 120) : candidate.problem || null,
          formatSelectionScoreSummary(candidate.selection_scores || null),
          candidate.next_target ? `next ${candidate.next_target}` : null,
          candidate.updated_at ? `updated ${formatRelativeTime(candidate.updated_at)}` : null,
        ]
          .filter(Boolean)
          .join(' · '),
        badge: 'brief',
        documentId: resolveQuestDocumentIdFromPath(
          candidate.idea_draft_path || candidate.idea_md_path || candidate.candidate_root || null,
          snapshot
        ),
        stageSelection: {
          selection_ref: candidate.idea_id || null,
          selection_type: 'idea_candidate',
          branch_name: candidate.parent_branch || snapshot?.branch || null,
          stage_key: 'idea',
          label: candidate.title || candidate.idea_id || 'Candidate brief',
          summary: candidate.method_brief || candidate.problem || null,
        },
      })),
    [optimizationFrontier?.candidate_briefs, snapshot]
  )

  const optimizationImplementationCandidateItems = React.useMemo<LinkItem[]>(
    () =>
      (optimizationFrontier?.implementation_candidates || []).map((candidate, index) => ({
        key: `opt-candidate:${candidate.candidate_id || index}`,
        title: candidate.summary || candidate.candidate_id || 'Implementation candidate',
        subtitle: [
          candidate.branch || null,
          candidate.strategy || null,
          candidate.status || null,
          candidate.linked_run_id ? `run ${candidate.linked_run_id}` : null,
          candidate.updated_at ? `updated ${formatRelativeTime(candidate.updated_at)}` : null,
        ]
          .filter(Boolean)
          .join(' · '),
        badge: candidate.status || 'candidate',
        documentId: resolveQuestDocumentIdFromPath(candidate.artifact_path || null, snapshot),
      })),
    [optimizationFrontier?.implementation_candidates, snapshot]
  )

  const optimizationFusionItems = React.useMemo<LinkItem[]>(
    () =>
      (optimizationFrontier?.fusion_candidates || []).map((candidate, index) => ({
        key: `opt-fusion:${candidate.branch_name || index}`,
        title: candidate.idea_title || candidate.branch_name || 'Fusion candidate',
        subtitle: [
          candidate.branch_name || null,
          candidate.latest_main_run_id ? `run ${candidate.latest_main_run_id}` : null,
        ]
          .filter(Boolean)
          .join(' · '),
        badge: 'fusion',
      })),
    [optimizationFrontier?.fusion_candidates]
  )

  const optimizationStagnantItems = React.useMemo<LinkItem[]>(
    () =>
      (optimizationFrontier?.stagnant_branches || []).map((branch, index) => ({
        key: `opt-stagnant:${branch.branch_name || index}`,
        title: branch.idea_title || branch.branch_name || 'Stagnant line',
        subtitle: [branch.branch_no ? `branch #${branch.branch_no}` : null, branch.branch_name || null]
          .filter(Boolean)
          .join(' · '),
        badge: 'stagnant',
      })),
    [optimizationFrontier?.stagnant_branches]
  )

  const paperContract = snapshot?.paper_contract ?? null
  const paperContractHealth = snapshot?.paper_contract_health ?? null
  const paperEvidence = snapshot?.paper_evidence ?? null
  const analysisInventory = snapshot?.analysis_inventory ?? null
  const ideaLines = snapshot?.idea_lines ?? []
  const activeIdeaLineRef = snapshot?.active_idea_line_ref ?? null
  const paperLines = snapshot?.paper_lines ?? []
  const activePaperLineRef = snapshot?.active_paper_line_ref ?? null

  const paperContractFiles = React.useMemo<LinkItem[]>(() => {
    if (!paperContract?.paths) return []
    const labels: Record<string, string> = {
      selected_outline: 'Selected Outline',
      outline_manifest: 'Outline Manifest',
      experiment_matrix: 'Experiment Matrix',
      experiment_matrix_json: 'Experiment Matrix JSON',
      bundle_manifest: 'Bundle Manifest',
      claim_evidence_map: 'Claim-Evidence Map',
      paper_line_state: 'Paper Line State',
      evidence_ledger_json: 'Evidence Ledger JSON',
      evidence_ledger_md: 'Evidence Ledger MD',
      submission_checklist: 'Submission Checklist',
      draft: 'Draft',
      status: 'Paper Status',
      summary: 'Paper Summary',
    }
    return Object.entries(paperContract.paths)
      .filter(([, path]) => typeof path === 'string' && path.trim().length > 0)
      .map(([key, path]) => ({
        key: `paper-file:${key}:${path}`,
        title: labels[key] || key,
        subtitle: path,
        badge: 'paper',
        documentId: resolveQuestDocumentIdFromPath(path, snapshot),
      }))
  }, [paperContract?.paths, snapshot])

  const paperSectionItems = React.useMemo<LinkItem[]>(
    () =>
      (paperContract?.sections || []).map((section) => ({
        key: `paper-section:${section.section_id}`,
        title: section.title,
        subtitle: [
          `section_id=${section.section_id}`,
          section.paper_role || null,
          typeof section.required_items?.length === 'number'
            ? `${section.required_items.length} required`
            : null,
          typeof section.optional_items?.length === 'number'
            ? `${section.optional_items.length} optional`
            : null,
        ]
          .filter(Boolean)
          .join(' · '),
        badge: section.status || 'recorded',
      })),
    [paperContract?.sections]
  )

  const ideaLineItems = React.useMemo<LinkItem[]>(
    () =>
      ideaLines.map((line) => ({
        key: `idea-line:${line.idea_line_id}`,
        title: line.idea_title || line.idea_id || line.idea_line_id,
        subtitle: [
          line.idea_branch ? `idea ${line.idea_branch}` : null,
          line.latest_main_run_id ? `run ${line.latest_main_run_id}` : null,
          line.paper_line_id ? `paper ${line.paper_line_id}` : null,
          typeof line.required_count === 'number'
            ? `${line.ready_required_count ?? 0}/${line.required_count} required`
            : null,
          typeof line.open_supplementary_count === 'number'
            ? `${line.open_supplementary_count} open supp`
            : null,
          typeof line.unmapped_count === 'number' && line.unmapped_count > 0
            ? `${line.unmapped_count} unmapped`
            : null,
        ]
          .filter(Boolean)
          .join(' · '),
        badge: activeIdeaLineRef === line.idea_line_id ? 'active' : 'idea-line',
        documentId: resolveQuestDocumentIdFromPath(
          line.paths?.paper_line_state || line.paths?.idea_draft || line.paths?.idea_md || null,
          snapshot
        ),
      })),
    [ideaLines, activeIdeaLineRef, snapshot]
  )

  const paperLineItems = React.useMemo<LinkItem[]>(
    () =>
      paperLines.map((line) => ({
        key: `paper-line:${line.paper_line_id}`,
        title: line.title || line.paper_branch || line.paper_line_id,
        subtitle: [
          line.source_idea_id ? `idea ${line.source_idea_id}` : null,
          line.source_run_id ? `run ${line.source_run_id}` : null,
          line.selected_outline_ref ? `outline ${line.selected_outline_ref}` : null,
          typeof line.required_count === 'number'
            ? `${line.ready_required_count ?? 0}/${line.required_count} required`
            : null,
          typeof line.open_supplementary_count === 'number'
            ? `${line.open_supplementary_count} open supp`
            : null,
        ]
          .filter(Boolean)
          .join(' · '),
        badge: activePaperLineRef === line.paper_line_id ? 'active' : 'paper-line',
        documentId: resolveQuestDocumentIdFromPath(line.paths?.paper_line_state || null, snapshot),
      })),
    [paperLines, activePaperLineRef, snapshot]
  )

  const paperHealthBlockingItems = React.useMemo<LinkItem[]>(
    () => [
      ...((paperContractHealth?.unresolved_required_items || []).map((item, index) => ({
        key: `paper-health:required:${item.section_id || item.item_id || index}`,
        title: item.item_id || 'Required item',
        subtitle: [
          item.section_title || item.section_id || null,
          item.status ? `status ${item.status}` : 'not ready',
        ]
          .filter(Boolean)
          .join(' · '),
        badge: 'required',
      })) as LinkItem[]),
      ...((paperContractHealth?.unmapped_completed_items || []).map((item, index) => ({
        key: `paper-health:unmapped:${item.campaign_id || item.slice_id || index}`,
        title: item.title || item.slice_id || item.item_id || 'Completed slice',
        subtitle: [
          item.campaign_id || null,
          item.section_id ? `section ${item.section_id}` : null,
          'completed but unmapped',
        ]
          .filter(Boolean)
          .join(' · '),
        badge: 'unmapped',
      })) as LinkItem[]),
      ...((paperContractHealth?.blocking_pending_slices || []).map((item, index) => ({
        key: `paper-health:pending:${item.campaign_id || item.slice_id || index}`,
        title: item.title || item.slice_id || item.item_id || 'Pending slice',
        subtitle: [
          item.campaign_id || null,
          item.section_id ? `section ${item.section_id}` : null,
          'pending main-text evidence',
        ]
          .filter(Boolean)
          .join(' · '),
        badge: 'pending',
      })) as LinkItem[]),
    ],
    [paperContractHealth]
  )

  const paperEvidenceItems = React.useMemo<LinkItem[]>(
    () =>
      (paperEvidence?.items || []).map((item, index) => ({
        key: `paper-evidence:${item.item_id || index}`,
        title: item.title || item.item_id || 'Evidence item',
        subtitle: [
          item.section_id || null,
          item.paper_role || null,
          item.result_summary || null,
          item.key_metrics?.length
            ? item.key_metrics
                .slice(0, 2)
                .map((metric) => `${metric.metric_id || 'metric'}=${metric.value ?? '—'}`)
                .join(' · ')
            : null,
        ]
          .filter(Boolean)
          .join(' · '),
        badge: item.status || item.kind || 'evidence',
        documentId: resolveQuestDocumentIdFromPath(item.source_paths?.[0] || null, snapshot),
      })),
    [paperEvidence?.items, snapshot]
  )

  const analysisCampaignItems = React.useMemo<LinkItem[]>(
    () =>
      (analysisInventory?.campaigns || []).map((campaign) => ({
        key: `analysis-campaign:${campaign.campaign_id}`,
        title: campaign.title || campaign.campaign_id,
        subtitle: [
          campaign.summary_excerpt || null,
          campaign.selected_outline_ref ? `outline ${campaign.selected_outline_ref}` : null,
          typeof campaign.slice_count === 'number'
            ? `${campaign.completed_slice_count ?? 0}/${campaign.slice_count} slices`
            : null,
          typeof campaign.mapped_slice_count === 'number'
            ? `${campaign.mapped_slice_count} mapped`
            : null,
        ]
          .filter(Boolean)
          .join(' · '),
        badge: 'analysis',
        documentId: resolveQuestDocumentIdFromPath(
          campaign.summary_path || campaign.campaign_path || campaign.todo_manifest_path || null,
          snapshot
        ),
      })),
    [analysisInventory?.campaigns, snapshot]
  )

  const analysisSliceItems = React.useMemo<LinkItem[]>(
    () =>
      (analysisInventory?.campaigns || [])
        .flatMap((campaign) =>
          (campaign.slices || []).map((slice) => ({
            key: `analysis-slice:${campaign.campaign_id}:${slice.slice_id}`,
            title: slice.title || slice.slice_id,
            subtitle: [
              campaign.title || campaign.campaign_id,
              slice.paper_role || null,
              slice.section_id ? `section ${slice.section_id}` : null,
              slice.item_id ? `item ${slice.item_id}` : null,
              slice.experimental_design || slice.research_question || slice.result_excerpt || null,
            ]
              .filter(Boolean)
              .join(' · '),
            badge: slice.status || 'completed',
            documentId: resolveQuestDocumentIdFromPath(slice.result_path || null, snapshot),
          }))
        )
        .slice(0, 24),
    [analysisInventory?.campaigns, snapshot]
  )

  const paperWorkspaceDrift =
    paperContract?.workspace_root &&
    snapshot?.active_workspace_root &&
    paperContract.workspace_root !== snapshot.active_workspace_root
      ? `Active workspace is ${snapshot.active_workspace_root}, but the current paper contract points to ${paperContract.workspace_root}.`
      : null

  const guidance = (snapshot?.guidance ?? null) as GuidanceVm | null
  const latestMetric = snapshot?.summary?.latest_metric ?? null
  const metricsTimelineRunSignature = React.useMemo(
    () => buildMetricsTimelineRunSignature(workflow?.entries),
    [workflow?.entries]
  )
  const baselineCompareSignature = React.useMemo(
    () =>
      [
        snapshot?.updated_at || '',
        snapshot?.active_baseline_id || '',
        snapshot?.active_baseline_variant_id || '',
      ].join(':'),
    [snapshot?.active_baseline_id, snapshot?.active_baseline_variant_id, snapshot?.updated_at]
  )
  const metricsTimelineSeries = metricsTimeline?.series || []
  const baselineCompareSeries = baselineCompare?.series || []
  const hasMetricsOverview = metricsTimelineSeries.length > 0
  const hasBaselineCompare = baselineCompareSeries.length > 0
  const hasMainExperimentMetricPoints = metricsTimelineSeries.some(
    (series) => (series.points?.length || 0) > 0
  )
  const statusLine =
    snapshot?.summary?.status_line || 'Research workspace ready.'
  const pendingDecisionCount = snapshot?.counts?.pending_decision_count || 0
  const pendingUserMessages = snapshot?.counts?.pending_user_message_count || 0
  const runningBashCount =
    runningBashSessions.length || snapshot?.counts?.bash_running_count || 0
  const workspaceMode = String(snapshot?.workspace_mode || '').trim().toLowerCase()
  const isCopilotWorkspace = workspaceMode === 'copilot'
  const runtimeStatusLabel = snapshot?.display_status || snapshot?.runtime_status || snapshot?.status || 'idle'
  const runtimeStatusNormalized = String(runtimeStatusLabel).trim().toLowerCase()
  const continuationPolicy = String(snapshot?.continuation_policy || '').trim().toLowerCase()
  const isIdleCopilotWorkspace =
    isCopilotWorkspace &&
    continuationPolicy === 'wait_for_user_or_resume' &&
    !snapshot?.active_run_id &&
    runningBashCount === 0 &&
    !['paused', 'stopped', 'completed', 'error'].includes(runtimeStatusNormalized)
  const overallHint = isIdleCopilotWorkspace
    ? 'Copilot workspace is idle and waiting for your first message.'
    : statusLine
  const overallStatusLabel = isIdleCopilotWorkspace ? 'Ready for your first instruction' : runtimeStatusLabel
  const pendingWorkLabel =
    isIdleCopilotWorkspace && pendingDecisionCount === 0 && pendingUserMessages === 0
      ? 'No background work. Waiting for your next message.'
      : `${pendingDecisionCount} pending decisions · ${pendingUserMessages} queued user messages`
  const signalValue =
    isIdleCopilotWorkspace && !latestMetric?.key
      ? 'Waiting for first task'
      : latestMetric?.key
        ? `${latestMetric.key} · ${latestMetric.value ?? '—'}`
        : `${pendingDecisionCount} pending decisions`
  const signalHint =
    isIdleCopilotWorkspace && !latestMetric?.key
      ? 'Start a chat to launch planning, coding, experiments, or analysis.'
      : latestMetric?.delta_vs_baseline != null
        ? `Δ ${latestMetric.delta_vs_baseline} vs baseline`
        : 'Awaiting stronger evidence'

  React.useEffect(() => {
    let cancelled = false
    void client
      .metricsTimeline(questId)
      .then((payload) => {
        if (!cancelled) {
          setMetricsTimeline(payload)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setMetricsTimeline(null)
        }
      })
    return () => {
      cancelled = true
    }
  }, [questId, metricsTimelineRunSignature])

  React.useEffect(() => {
    let cancelled = false
    void client
      .baselineCompare(questId)
      .then((payload) => {
        if (!cancelled) {
          setBaselineCompare(payload)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBaselineCompare(null)
        }
      })
    return () => {
      cancelled = true
    }
  }, [baselineCompareSignature, questId])

  return (
    <div
      className="feed-scrollbar h-full overflow-y-auto overflow-x-hidden"
      data-onboarding-id="quest-details-surface"
    >
      <div className="mx-auto flex min-h-full max-w-[1120px] flex-col px-5 pb-10 pt-5 sm:px-6 lg:px-8">
        {projectionStatusCards.length > 0 || projectionError ? (
          <div className="mb-5 rounded-[22px] border border-black/[0.08] bg-white/[0.84] px-4 py-4 shadow-card dark:border-white/[0.10] dark:bg-[rgba(18,18,18,0.78)]">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[#9b8352]" />
              <div className="min-w-0 flex-1">
                <div className="space-y-3 text-sm leading-6 text-muted-foreground">
                  {projectionStatusCards.map((item) => (
                    <div key={item.key}>
                      <div className="flex items-center justify-between gap-3">
                        <div className="font-medium text-foreground">{item.title}</div>
                        {typeof item.percent === 'number' ? (
                          <div className="text-[12px] text-muted-foreground">
                            {Math.round(item.percent)}%
                          </div>
                        ) : null}
                      </div>
                      <div>{item.message}</div>
                      {typeof item.percent === 'number' ? (
                        <ProjectionProgressBar percent={item.percent} className="mt-2" />
                      ) : null}
                    </div>
                  ))}
                </div>
                {projectionError ? <div className="text-[13px] text-foreground">{projectionError}</div> : null}
              </div>
            </div>
          </div>
        ) : null}
        <DetailSection
          first
          title="Metrics Overview"
          hint="Shows baseline metrics immediately and overlays main-experiment traces once recorded."
          actions={<WorkspaceRefreshButton onRefresh={onRefresh} label="Refresh metrics" />}
        >
          {hasMetricsOverview ? (
            <div className="space-y-4">
              {!hasMainExperimentMetricPoints ? (
                <div className="rounded-[22px] border border-dashed border-black/[0.10] bg-black/[0.02] px-4 py-3 text-sm text-muted-foreground dark:border-white/[0.12] dark:bg-white/[0.03]">
                  Showing baseline-only metrics. Main-experiment traces will appear after the first recorded result.
                </div>
              ) : null}
              <div className="grid gap-5 xl:grid-cols-2">
                {metricsTimelineSeries.map((series) => (
                  <MetricTimelineCard
                    key={series.metric_id}
                    series={series}
                    primaryMetricId={metricsTimeline.primary_metric_id}
                  />
                ))}
              </div>
            </div>
          ) : (
            <div className="rounded-[24px] border border-dashed border-black/[0.10] px-4 py-6 text-sm text-muted-foreground dark:border-white/[0.12]">
              Attach a baseline with recorded metrics to populate this section. Main-experiment traces will overlay after the first recorded result.
            </div>
          )}
        </DetailSection>

        <DetailSection
          title="Baseline Compare"
          hint="Lists every confirmed baseline or variant the quest can currently compare, separate from the active baseline timeline."
          actions={<WorkspaceRefreshButton onRefresh={onRefresh} label="Refresh baselines" />}
        >
          {hasBaselineCompare ? (
            <div className="space-y-4">
              <div className="rounded-[22px] border border-dashed border-black/[0.10] bg-black/[0.02] px-4 py-3 text-sm text-muted-foreground dark:border-white/[0.12] dark:bg-white/[0.03]">
                Showing {baselineCompare?.total_entries || baselineCompareSeries[0]?.values?.length || 0} baseline entries across{' '}
                {baselineCompareSeries.length} metric{baselineCompareSeries.length === 1 ? '' : 's'}.
              </div>
              <div className="grid gap-5 xl:grid-cols-2">
                {baselineCompareSeries.map((series) => (
                  <BaselineCompareCard
                    key={series.metric_id}
                    series={series}
                    primaryMetricId={baselineCompare?.primary_metric_id}
                  />
                ))}
              </div>
            </div>
          ) : (
            <div className="rounded-[24px] border border-dashed border-black/[0.10] px-4 py-6 text-sm text-muted-foreground dark:border-white/[0.12]">
              Confirm more than one baseline or variant to populate cross-baseline comparison here.
            </div>
          )}
        </DetailSection>

        <DetailSection
          title="Overall"
          hint={overallHint}
          actions={<WorkspaceRefreshButton onRefresh={onRefresh} />}
        >
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill>{overallStatusLabel}</StatusPill>
            {isCopilotWorkspace ? <StatusPill>Copilot mode</StatusPill> : null}
            <StatusPill>{snapshot?.branch || 'main'}</StatusPill>
            <StatusPill>{snapshot?.active_anchor || 'baseline'}</StatusPill>
            <StatusPill>{formatConnectionState(connectionState)}</StatusPill>
            <StatusPill mono>{questId}</StatusPill>
          </div>

          <div className="mt-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Title
            </div>
            <div className="mt-2 whitespace-normal break-words text-lg font-medium leading-7 tracking-[-0.01em] text-foreground [overflow-wrap:anywhere]">
              {snapshot?.title || questId}
            </div>
          </div>

          <div className="mt-6 grid gap-x-10 gap-y-6 sm:grid-cols-2 xl:grid-cols-3">
            <OverviewMetric
              icon={<Activity className="h-4 w-4" />}
              label="Status"
              value={overallStatusLabel}
              hint={error || `Updated ${formatRelativeTime(snapshot?.updated_at)}`}
            />
            <OverviewMetric
              icon={<Clock3 className="h-4 w-4" />}
              label="Runtime"
              value={formatDuration(snapshot?.created_at)}
              hint={`Created ${formatRelativeTime(snapshot?.created_at)}`}
            />
            <OverviewMetric
              icon={<GitBranch className="h-4 w-4" />}
              label="Graph"
              value={`${nodeCount} nodes`}
              hint={`${ideaCount} ideas · ${analysisCount} analysis branches`}
            />
            <OverviewMetric
              icon={<FlaskConical className="h-4 w-4" />}
              label="Bash"
              value={runningBashCount ? `${runningBashCount} running` : 'idle'}
              hint={latestRunningBashHint}
            />
            <OverviewMetric
              icon={<Sparkles className="h-4 w-4" />}
              label="Signal"
              value={signalValue}
              hint={signalHint}
            />
            <OverviewMetric
              icon={<FileCode2 className="h-4 w-4" />}
              label="Working set"
              value={`${changedFiles.length} changed files`}
              hint={`${recentDocs.length} docs · ${recentMemory.length} memory · ${recentArtifacts.length} artifacts`}
            />
          </div>
        </DetailSection>

        <DetailSection
          title="Operational Status"
          hint="Details concentrates the same high-signal project state that a quick /status-style check should expose."
        >
          <div className="grid gap-8 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,0.85fr)]">
            <div className="min-w-0">
              <div className="divide-y divide-dashed divide-black/[0.10] dark:divide-white/[0.10]">
                <div className="grid gap-2 py-3 sm:grid-cols-[150px_minmax(0,1fr)]">
                  <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                    Runtime state
                  </div>
                  <div className="break-words text-sm leading-7 text-foreground">
                    {overallStatusLabel}
                  </div>
                </div>
                <div className="grid gap-2 py-3 sm:grid-cols-[150px_minmax(0,1fr)]">
                  <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                    Pending work
                  </div>
                  <div className="break-words text-sm leading-7 text-foreground">
                    {pendingWorkLabel}
                  </div>
                </div>
                <div className="grid gap-2 py-3 sm:grid-cols-[150px_minmax(0,1fr)]">
                  <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                    Interaction
                  </div>
                  <div className="break-words text-sm leading-7 text-foreground">
                    {snapshot?.active_interaction_id
                      ? `Active interaction ${snapshot.active_interaction_id}`
                      : snapshot?.waiting_interaction_id
                        ? `Waiting on ${snapshot.waiting_interaction_id}`
                        : 'No blocking interaction'}
                  </div>
                </div>
                <div className="grid gap-2 py-3 sm:grid-cols-[150px_minmax(0,1fr)]">
                  <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                    Latest delivery
                  </div>
                  <div className="break-words text-sm leading-7 text-foreground">
                    {snapshot?.last_delivered_at
                      ? `Delivered ${formatRelativeTime(snapshot.last_delivered_at)}`
                      : 'No mailbox delivery recorded yet'}
                  </div>
                </div>
                {snapshot?.stop_reason ? (
                  <div className="grid gap-2 py-3 sm:grid-cols-[150px_minmax(0,1fr)]">
                    <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                      Stop reason
                    </div>
                    <div className="break-words text-sm leading-7 text-foreground">
                      {snapshot.stop_reason}
                    </div>
                  </div>
                ) : null}
                {snapshot?.pending_decisions?.length ? (
                  <div className="grid gap-2 py-3 sm:grid-cols-[150px_minmax(0,1fr)]">
                    <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                      Decision queue
                    </div>
                    <div className="space-y-1.5">
                      {snapshot.pending_decisions.slice(0, 4).map((item) => (
                        <div
                          key={item}
                          className="break-words text-sm leading-7 text-muted-foreground"
                        >
                          {item}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>

            <div className="min-w-0">
              <DocumentListBlock
                title="Core Docs"
                countLabel={`${coreDocs.length} files`}
                items={coreDocs}
                emptyLabel="Core project files will appear here."
                onOpen={onOpenDocument}
              />
            </div>
          </div>
        </DetailSection>

        <DetailSection
          title="Next Step"
          hint="This section turns the latest durable guidance into a compact execution brief."
        >
          {guidance ? (
            <div className="grid gap-8 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
              <div className="min-w-0">
                <div className="flex items-start gap-3">
                  <div className="mt-1 shrink-0 text-muted-foreground">
                    <Lightbulb className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="break-words text-base font-semibold text-foreground">
                      {guidance.summary}
                    </div>
                    <div className="mt-3 break-words text-sm leading-7 text-muted-foreground">
                      {guidance.why_now}
                    </div>
                  </div>
                </div>

                {guidance.complete_when?.length ? (
                  <div className="mt-5 border-l border-dashed border-black/[0.12] pl-4 dark:border-white/[0.12]">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                      Complete when
                    </div>
                    <div className="mt-3 space-y-2">
                      {guidance.complete_when.slice(0, 4).map((item) => (
                        <div
                          key={item}
                          className="break-words text-sm leading-7 text-muted-foreground"
                        >
                          {item}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="min-w-0">
                <div className="divide-y divide-dashed divide-black/[0.10] dark:divide-white/[0.10]">
                  <div className="grid gap-2 py-3 sm:grid-cols-[132px_minmax(0,1fr)]">
                    <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                      Recommended
                    </div>
                    <div className="break-words text-sm leading-7 text-foreground">
                      {guidance.recommended_skill} · {guidance.recommended_action}
                    </div>
                  </div>
                  <div className="grid gap-2 py-3 sm:grid-cols-[132px_minmax(0,1fr)]">
                    <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                      Stage status
                    </div>
                    <div className="break-words text-sm leading-7 text-foreground">
                      {guidance.stage_status || 'ready'}
                      {guidance.requires_user_decision ? ' · waiting for user approval' : ''}
                    </div>
                  </div>
                  <div className="grid gap-2 py-3 sm:grid-cols-[132px_minmax(0,1fr)]">
                    <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                      Anchor
                    </div>
                    <div className="break-words text-sm leading-7 text-foreground">
                      {guidance.current_anchor || snapshot?.active_anchor || 'baseline'}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="py-3 text-sm leading-7 text-muted-foreground">
              Durable guidance will appear after the next stage-significant update.
            </div>
          )}
        </DetailSection>

        <DetailSection
          title="Idea Lines"
          hint="This is the minimal audit view for each idea line: whether it has reached a main run, whether it owns a paper line, and whether supplementary work is still open."
        >
          <DocumentListBlock
            title="Idea Audit"
            countLabel={ideaLineItems.length ? `${ideaLineItems.length} lines` : null}
            items={ideaLineItems}
            emptyLabel="No durable idea lines are exposed yet."
            onOpen={onOpenDocument}
          />
        </DetailSection>

        <DetailSection
          title="Optimization Frontier"
          hint={
            optimizationFrontier?.frontier_reason ||
            'This is the optimization-mode frontier: candidate briefs, active implementation candidates, line quality, stagnation, and fusion opportunities.'
          }
        >
          {!optimizationFrontier ? (
            <div className="py-3 text-sm leading-7 text-muted-foreground">
              No optimization frontier is exposed in the current workflow payload yet.
            </div>
          ) : (
            <div className="grid gap-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
              <div className="min-w-0 space-y-6">
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  <OverviewMetric
                    icon={<Sparkles className="h-4 w-4" />}
                    label="Mode"
                    value={optimizationFrontier.mode || 'unknown'}
                    hint={optimizationFrontier.frontier_reason || 'No frontier reason recorded.'}
                  />
                  <OverviewMetric
                    icon={<GitBranch className="h-4 w-4" />}
                    label="Best line"
                    value={optimizationFrontier.best_branch?.branch_no || optimizationFrontier.best_branch?.branch_name || 'none'}
                    hint={optimizationFrontier.best_branch?.idea_title || optimizationFrontier.best_branch?.branch_name || 'No leading line yet'}
                  />
                  <OverviewMetric
                    icon={<FlaskConical className="h-4 w-4" />}
                    label="Candidate pool"
                    value={String(optimizationFrontier.candidate_backlog?.implementation_candidate_count ?? 0)}
                    hint={`${optimizationFrontier.candidate_backlog?.active_implementation_candidate_count ?? 0} active · ${optimizationFrontier.candidate_backlog?.candidate_brief_count ?? 0} briefs`}
                  />
                  <OverviewMetric
                    icon={<AlertTriangle className="h-4 w-4" />}
                    label="Stagnant"
                    value={String((optimizationFrontier.stagnant_branches || []).length)}
                    hint={`${(optimizationFrontier.fusion_candidates || []).length} fusion opportunities`}
                  />
                </div>

                <div className="space-y-8">
                  <DocumentListBlock
                    title="Top Lines"
                    countLabel={optimizationTopBranchItems.length ? `${optimizationTopBranchItems.length} lines` : null}
                    items={optimizationTopBranchItems}
                    emptyLabel="No optimization lines are ranked yet."
                    onOpen={onOpenDocument}
                  />

                  <DocumentListBlock
                    title="Candidate Briefs"
                    countLabel={optimizationCandidateBriefItems.length ? `${optimizationCandidateBriefItems.length} briefs` : null}
                    items={optimizationCandidateBriefItems}
                    emptyLabel="No branchless candidate briefs are recorded yet."
                    onOpen={onOpenDocument}
                  />
                </div>
              </div>

              <div className="min-w-0 space-y-8">
                <DocumentListBlock
                  title="Implementation Candidates"
                  countLabel={
                    optimizationImplementationCandidateItems.length
                      ? `${optimizationImplementationCandidateItems.length} candidates`
                      : null
                  }
                  items={optimizationImplementationCandidateItems}
                  emptyLabel="No implementation-level optimization candidates are recorded yet."
                  onOpen={onOpenDocument}
                />

                <DocumentListBlock
                  title="Stagnant Lines"
                  countLabel={optimizationStagnantItems.length ? `${optimizationStagnantItems.length} lines` : null}
                  items={optimizationStagnantItems}
                  emptyLabel="No stagnant lines detected yet."
                  onOpen={onOpenDocument}
                />

                <DocumentListBlock
                  title="Fusion Opportunities"
                  countLabel={optimizationFusionItems.length ? `${optimizationFusionItems.length} lines` : null}
                  items={optimizationFusionItems}
                  emptyLabel="No fusion opportunities are currently exposed."
                  onOpen={onOpenDocument}
                />

                <div className="min-w-0">
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                    Recommended Next Actions
                  </div>
                  {(optimizationFrontier.recommended_next_actions || []).length ? (
                    <div className="space-y-2">
                      {(optimizationFrontier.recommended_next_actions || []).map((item, index) => (
                        <div key={`opt-next:${index}`} className="break-words text-sm leading-7 text-foreground">
                          {item}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="py-3 text-sm leading-7 text-muted-foreground">
                      No frontier-driven next actions are exposed yet.
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </DetailSection>

        <DetailSection
          title="Paper Contract Health"
          hint="This is the minimal blocking surface for the active paper line. If this section is not green, the system should repair the paper contract or complete required supplementary work before treating the paper as settled."
        >
          {!paperContractHealth ? (
            <div className="py-3 text-sm leading-7 text-muted-foreground">
              No paper-contract health summary is exposed yet.
            </div>
          ) : (
            <div className="grid gap-8 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
              <div className="min-w-0 space-y-6">
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  <OverviewMetric
                    icon={<Sparkles className="h-4 w-4" />}
                    label="Contract"
                    value={paperContractHealth.contract_ok ? 'OK' : 'Blocked'}
                    hint="Outline-required and mapping health"
                  />
                  <OverviewMetric
                    icon={<FileCode2 className="h-4 w-4" />}
                    label="Required"
                    value={`${paperContractHealth.ready_required_count ?? 0}/${paperContractHealth.required_count ?? 0}`}
                    hint="Required outline items ready"
                  />
                  <OverviewMetric
                    icon={<AlertTriangle className="h-4 w-4" />}
                    label="Unmapped"
                    value={String(paperContractHealth.unmapped_completed_count ?? 0)}
                    hint="Completed slices not yet mapped"
                  />
                  <OverviewMetric
                    icon={<FlaskConical className="h-4 w-4" />}
                    label="Blocking Supp"
                    value={String(paperContractHealth.blocking_open_supplementary_count ?? 0)}
                    hint="Pending main-text supplementary slices"
                  />
                </div>

                <div className="divide-y divide-dashed divide-black/[0.10] dark:divide-white/[0.10]">
                  <div className="grid gap-2 py-3 sm:grid-cols-[170px_minmax(0,1fr)]">
                    <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                      Writing status
                    </div>
                    <div className="break-words text-sm leading-7 text-foreground">
                      {paperContractHealth.writing_ready ? 'ready' : 'not ready'}
                    </div>
                  </div>
                  <div className="grid gap-2 py-3 sm:grid-cols-[170px_minmax(0,1fr)]">
                    <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                      Recommended
                    </div>
                    <div className="break-words text-sm leading-7 text-foreground">
                      {(paperContractHealth.recommended_next_stage || 'none') +
                        ' · ' +
                        (paperContractHealth.recommended_action || 'none')}
                    </div>
                  </div>
                  <div className="grid gap-2 py-3 sm:grid-cols-[170px_minmax(0,1fr)]">
                    <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                      Blocking reasons
                    </div>
                    <div className="break-words text-sm leading-7 text-foreground">
                      {(paperContractHealth.blocking_reasons || []).length
                        ? (paperContractHealth.blocking_reasons || []).join(' · ')
                        : 'None'}
                    </div>
                  </div>
                </div>
              </div>

              <div className="min-w-0">
                <DocumentListBlock
                  title="Blocking Items"
                  countLabel={paperHealthBlockingItems.length ? `${paperHealthBlockingItems.length} items` : null}
                  items={paperHealthBlockingItems}
                  emptyLabel="No blocking paper-contract items are exposed."
                  onOpen={onOpenDocument}
                />
              </div>
            </div>
          )}
        </DetailSection>

        <DetailSection
          title="Paper Contract"
          hint="This is the current paper-facing contract the quest is actually using: selected outline, experiment matrix, and bundle control files."
        >
          {!paperContract ? (
            <div className="py-3 text-sm leading-7 text-muted-foreground">
              No selected paper contract is exposed in the current quest snapshot yet.
            </div>
          ) : (
            <div className="grid gap-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
              <div className="min-w-0 space-y-5">
                <div className="space-y-2">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                    Outline
                  </div>
                  <div className="break-words text-base font-semibold leading-7 text-foreground">
                    {paperContract.title || 'Untitled paper contract'}
                  </div>
                  <div className="break-words text-sm leading-7 text-muted-foreground">
                    {paperContract.summary || paperContract.story || 'No paper summary recorded.'}
                  </div>
                </div>

                <div className="divide-y divide-dashed divide-black/[0.10] dark:divide-white/[0.10]">
                  <div className="grid gap-2 py-3 sm:grid-cols-[150px_minmax(0,1fr)]">
                    <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                      Outline ref
                    </div>
                    <div className="break-words text-sm leading-7 text-foreground">
                      {paperContract.selected_outline_ref || 'Not selected'}
                    </div>
                  </div>
                  <div className="grid gap-2 py-3 sm:grid-cols-[150px_minmax(0,1fr)]">
                    <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                      Paper branch
                    </div>
                    <div className="break-words text-sm leading-7 text-foreground">
                      {paperContract.paper_branch || 'Not recorded'}
                    </div>
                  </div>
                  <div className="grid gap-2 py-3 sm:grid-cols-[150px_minmax(0,1fr)]">
                    <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                      Source branch
                    </div>
                  <div className="break-words text-sm leading-7 text-foreground">
                      {paperContract.source_branch || 'Not recorded'}
                    </div>
                  </div>
                  <div className="grid gap-2 py-3 sm:grid-cols-[150px_minmax(0,1fr)]">
                    <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                      Evidence status
                    </div>
                    <div className="break-words text-sm leading-7 text-foreground">
                      {(paperContract.evidence_summary?.main_text_ready_count ?? 0)}/
                      {(paperContract.evidence_summary?.item_count ?? 0)} ready ·{' '}
                      {paperContract.evidence_summary?.unmapped_item_count ?? 0} unmapped
                    </div>
                  </div>
                  {paperWorkspaceDrift ? (
                    <div className="grid gap-2 py-3 sm:grid-cols-[150px_minmax(0,1fr)]">
                      <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                        Drift warning
                      </div>
                      <div className="break-words text-sm leading-7 text-[#b42318] dark:text-[#ffb4b4]">
                        {paperWorkspaceDrift}
                      </div>
                    </div>
                  ) : null}
                </div>

                {paperContract.research_questions?.length ? (
                  <div className="space-y-2">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                      Research Questions
                    </div>
                    <div className="space-y-2">
                      {paperContract.research_questions.map((item, index) => (
                        <div key={`rq-${index}`} className="break-words text-sm leading-7 text-foreground">
                          {item}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}

                {paperContract.experimental_designs?.length ? (
                  <div className="space-y-2">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                      Experimental Designs
                    </div>
                    <div className="space-y-2">
                      {paperContract.experimental_designs.map((item, index) => (
                        <div key={`exp-${index}`} className="break-words text-sm leading-7 text-foreground">
                          {item}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="min-w-0 space-y-8">
                <DocumentListBlock
                  title="Paper Files"
                  countLabel={paperContractFiles.length ? `${paperContractFiles.length} files` : null}
                  items={paperContractFiles}
                  emptyLabel="No paper-contract files exposed yet."
                  onOpen={onOpenDocument}
                />
                <DocumentListBlock
                  title="Outline Sections"
                  countLabel={paperSectionItems.length ? `${paperSectionItems.length} sections` : null}
                  items={paperSectionItems}
                  emptyLabel="No paper sections exposed yet."
                  onOpen={onOpenDocument}
                />
              </div>
            </div>
          )}
        </DetailSection>

        <DetailSection
          title="Paper Lines"
          hint="Each serious paper-facing route should become a visible paper line rather than hiding behind one quest-global paper panel."
        >
          <DocumentListBlock
            title="Lines"
            countLabel={paperLineItems.length ? `${paperLineItems.length} lines` : null}
            items={paperLineItems}
            emptyLabel="No paper lines are exposed yet."
            onOpen={onOpenDocument}
          />
        </DetailSection>

        <DetailSection
          title="Evidence Ledger"
          hint="Paper-facing evidence items mirrored from main experiments and analysis slices. This is the contract layer that should keep completed results from disappearing before writing."
        >
          {!paperEvidence ? (
            <div className="py-3 text-sm leading-7 text-muted-foreground">
              No paper evidence ledger is exposed in the current quest snapshot yet.
            </div>
          ) : (
            <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <div className="min-w-0">
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  <OverviewMetric
                    icon={<FileCode2 className="h-4 w-4" />}
                    label="Items"
                    value={String(paperEvidence.item_count ?? 0)}
                    hint="Ledger items detected"
                  />
                  <OverviewMetric
                    icon={<Sparkles className="h-4 w-4" />}
                    label="Main Ready"
                    value={String(paperEvidence.main_text_ready_count ?? 0)}
                    hint="Main-text items marked ready"
                  />
                  <OverviewMetric
                    icon={<BarChart3 className="h-4 w-4" />}
                    label="Appendix"
                    value={String(paperEvidence.appendix_item_count ?? 0)}
                    hint="Appendix-linked items"
                  />
                  <OverviewMetric
                    icon={<AlertTriangle className="h-4 w-4" />}
                    label="Unmapped"
                    value={String(paperEvidence.unmapped_item_count ?? 0)}
                    hint="Items missing section or role mapping"
                  />
                </div>
              </div>

              <div className="min-w-0">
                <DocumentListBlock
                  title="Ledger Items"
                  countLabel={paperEvidenceItems.length ? `${paperEvidenceItems.length} items` : null}
                  items={paperEvidenceItems}
                  emptyLabel="No evidence items exposed yet."
                  onOpen={onOpenDocument}
                />
              </div>
            </div>
          )}
        </DetailSection>

        <DetailSection
          title="Analysis Inventory"
          hint="All detected paper-facing analysis campaigns and slice result mirrors currently available under the quest."
        >
          {!analysisInventory ? (
            <div className="py-3 text-sm leading-7 text-muted-foreground">
              No analysis inventory is exposed in the current quest snapshot yet.
            </div>
          ) : (
            <div className="grid gap-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
              <div className="min-w-0">
                <div className="grid gap-4 sm:grid-cols-3">
                  <OverviewMetric
                    icon={<BarChart3 className="h-4 w-4" />}
                    label="Campaigns"
                    value={String(analysisInventory.campaign_count ?? 0)}
                    hint="Detected analysis campaigns"
                  />
                  <OverviewMetric
                    icon={<FlaskConical className="h-4 w-4" />}
                    label="Slices"
                    value={String(analysisInventory.slice_count ?? 0)}
                    hint="Total analysis slices"
                  />
                  <OverviewMetric
                    icon={<Sparkles className="h-4 w-4" />}
                    label="Completed"
                    value={String(analysisInventory.completed_slice_count ?? 0)}
                    hint="Slices marked completed"
                  />
                  <OverviewMetric
                    icon={<FileCode2 className="h-4 w-4" />}
                    label="Mapped"
                    value={String(analysisInventory.mapped_slice_count ?? 0)}
                    hint="Slices with paper-contract mapping"
                  />
                </div>

                <div className="mt-6">
                  <DocumentListBlock
                    title="Campaigns"
                    countLabel={analysisCampaignItems.length ? `${analysisCampaignItems.length} campaigns` : null}
                    items={analysisCampaignItems}
                    emptyLabel="No analysis campaigns exposed yet."
                    onOpen={onOpenDocument}
                  />
                </div>
              </div>

              <div className="min-w-0">
                <DocumentListBlock
                  title="Slice Results"
                  countLabel={analysisSliceItems.length ? `${analysisSliceItems.length} slices` : null}
                  items={analysisSliceItems}
                  emptyLabel="No slice results exposed yet."
                  onOpen={onOpenDocument}
                />
              </div>
            </div>
          )}
        </DetailSection>

        <DetailSection
          title="Recent Progress"
          hint="Latest project messages, tool calls, artifacts, and runtime runs in one linear view."
        >
          <div className="grid gap-8 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,0.7fr)]">
            <div className="min-w-0">
              <ActivityTimeline
                items={recentFeed}
                loading={loading}
                restoring={restoring}
                connectionState={connectionState}
              />
            </div>

            <div className="min-w-0">
              <DocumentListBlock
                title="Recent Runs"
                countLabel={recentRuns.length ? `${recentRuns.length} runs` : null}
                items={recentRuns}
                emptyLabel="Recent stage runs will appear here."
                onOpen={onOpenDocument}
              />
            </div>
          </div>
        </DetailSection>

        <DetailSection
          title="Working Set"
          hint="High-frequency project materials: changed files, documents, memory, and durable artifact outputs."
        >
          <div className="grid gap-8 lg:grid-cols-2">
            <div className="min-w-0 space-y-8">
              <DocumentListBlock
                title="Changed Files"
                countLabel={changedFiles.length ? `${changedFiles.length} files` : null}
                items={changedFiles}
                emptyLabel="Changed files will appear here."
                onOpen={onOpenDocument}
              />
              <DocumentListBlock
                title="Documents"
                countLabel={recentDocs.length ? `${recentDocs.length} docs` : null}
                items={recentDocs}
                emptyLabel="Project documents will appear here."
                onOpen={onOpenDocument}
              />
            </div>

            <div className="min-w-0 space-y-8">
              <DocumentListBlock
                title="Memory"
                countLabel={recentMemory.length ? `${recentMemory.length} entries` : null}
                items={recentMemory}
                emptyLabel="Memory cards will appear here."
                onOpen={onOpenDocument}
                headerAction={
                  <button
                    type="button"
                    onClick={onOpenMemory}
                    className="rounded-full px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-muted-foreground transition hover:bg-black/[0.04] hover:text-foreground dark:hover:bg-white/[0.06]"
                  >
                    Open Memory
                  </button>
                }
              />
              <DocumentListBlock
                title="Artifacts"
                countLabel={recentArtifacts.length ? `${recentArtifacts.length} items` : null}
                items={recentArtifacts}
                emptyLabel="Artifact summaries will appear here."
                onOpen={onOpenDocument}
              />
            </div>
          </div>
        </DetailSection>
      </div>
    </div>
  )
}

function workspaceLayerClass(active: boolean) {
  return cn(
    'absolute inset-0 min-h-0',
    active ? 'z-10 block' : 'z-0 hidden'
  )
}

export function QuestWorkspaceSurfaceInner({
  questId,
  safePaddingLeft,
  safePaddingRight,
  view: controlledView,
  stageSelection,
  settingsFocusTarget,
  onViewChange,
  workspace,
}: QuestWorkspaceSurfaceInnerProps) {
  const {
    snapshot,
    workflow,
    feed,
    documents,
    memory,
    loading,
    detailsLoading,
    restoring,
    error,
    refresh,
    ensureViewData,
    connectionState,
  } = workspace
  const [uncontrolledView, setUncontrolledView] =
    React.useState<QuestWorkspaceView>(controlledView ?? 'canvas')
  const [branches, setBranches] = React.useState<GitBranchesPayload | null>(null)
  const setActiveQuest = useLabCopilotStore((state) => state.setActiveQuest)
  const { openFileInTab } = useOpenFile()
  const view = controlledView ?? uncontrolledView
  const detailLikeView = view === 'details' || view === 'memory'
  const workspaceMode = String(snapshot?.workspace_mode || '').trim().toLowerCase()

  React.useEffect(() => {
    setActiveQuest(questId)
  }, [questId, setActiveQuest])

  const updateView = React.useCallback(
    (nextView: QuestWorkspaceView, nextStageSelection?: QuestStageSelection | null) => {
      if (onViewChange) {
        onViewChange(nextView, nextStageSelection)
        return
      }
      setUncontrolledView(nextView)
    },
    [onViewChange]
  )

  const openDocumentInTab = React.useCallback(
    async (documentId: string) => {
      const node = await openQuestDocumentAsFileNode(questId, documentId)
      await openFileInTab(node, {
        customData: {
          projectId: questId,
        },
      })
    },
    [openFileInTab, questId]
  )

  const refreshWorkspace = React.useCallback(async () => {
    await refresh(false)
  }, [refresh])

  React.useEffect(() => {
    if (restoring || !workspace.historySeeded) {
      return
    }
    void ensureViewData('details')
  }, [ensureViewData, questId, restoring, workspace.historySeeded])

  React.useEffect(() => {
    if (restoring || !workspace.historySeeded) {
      return
    }
    let cancelled = false
    let retryTimer: number | null = null

    const loadBranches = () => {
      void client
        .gitBranches(questId)
        .then((payload) => {
          if (cancelled) {
            return
          }
          setBranches(payload)
          if (projectionPending(payload)) {
            retryTimer = window.setTimeout(loadBranches, 1000)
          }
        })
        .catch(() => {
          if (!cancelled) {
            setBranches(null)
          }
        })
    }

    loadBranches()
    return () => {
      cancelled = true
      if (retryTimer != null) {
        window.clearTimeout(retryTimer)
      }
    }
  }, [questId, restoring, workflow?.entries.length, workflow?.projection_status?.generated_at, workspace.historySeeded])

  React.useEffect(() => {
    if (typeof window === 'undefined') return
    const handleViewChange = (event: Event) => {
      const detail = (event as CustomEvent<QuestWorkspaceViewDetail>).detail
      if (!detail || detail.projectId !== questId) {
        return
      }
      updateView(detail.view, detail.stageSelection ?? null)
    }
    window.addEventListener(QUEST_WORKSPACE_VIEW_EVENT, handleViewChange as EventListener)
    return () => {
      window.removeEventListener(
        QUEST_WORKSPACE_VIEW_EVENT,
        handleViewChange as EventListener
      )
    }
  }, [questId, updateView])

  const onOpenStageSelection = React.useCallback(
    (selection: QuestStageSelection) => {
      updateView('stage', selection)
    },
    [updateView]
  )

  if (
    (loading || detailsLoading) &&
    !workflow &&
    documents.length === 0 &&
    memory.length === 0 &&
    detailLikeView
  ) {
    return (
      <div className="panel center-panel morandi-glow ds-stage h-full min-h-0" style={{ flex: 1 }}>
        <div
          className="ds-stage-safe flex h-full items-center justify-center"
          style={{ paddingLeft: safePaddingLeft, paddingRight: safePaddingRight }}
        >
          <div className="w-full max-w-xl rounded-[28px] border border-black/[0.08] bg-white/[0.88] px-8 py-8 shadow-[0_24px_64px_rgba(15,23,42,0.08)] backdrop-blur dark:border-white/[0.08] dark:bg-[rgba(18,20,24,0.84)] dark:shadow-[0_28px_72px_rgba(0,0,0,0.32)]">
            <div className="text-base font-semibold text-foreground">
              {restoring ? 'Restoring project workspace…' : 'Loading project workspace…'}
            </div>
            <div className="mt-3 text-sm leading-7 text-muted-foreground">
              {restoring
                ? 'Rehydrating the quest snapshot, documents, memory, and recent workflow state.'
                : 'Fetching the current quest snapshot and preparing the shared workspace surfaces.'}
            </div>
            <div className="mt-5 space-y-3" aria-hidden="true">
              <div className="h-3 w-40 rounded-full bg-black/[0.06] dark:bg-white/[0.08]" />
              <div className="h-3 w-full rounded-full bg-black/[0.05] dark:bg-white/[0.06]" />
              <div className="h-3 w-[82%] rounded-full bg-black/[0.05] dark:bg-white/[0.06]" />
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="panel center-panel morandi-glow ds-stage h-full min-h-0" style={{ flex: 1 }}>
      <div
        className="ds-stage-safe h-full min-h-0 overflow-hidden"
        style={{ paddingLeft: safePaddingLeft, paddingRight: safePaddingRight }}
      >
        <div className="relative h-full min-h-0 overflow-hidden">
          <div className={workspaceLayerClass(view === 'canvas')} aria-hidden={view !== 'canvas'}>
            <QuestCanvasSurface
              questId={questId}
              error={error}
              onRefresh={refreshWorkspace}
              onOpenStageSelection={onOpenStageSelection}
              snapshot={snapshot}
            />
          </div>
          <div className={workspaceLayerClass(view === 'details')} aria-hidden={view !== 'details'}>
            <QuestDetails
              questId={questId}
              snapshot={snapshot}
              workflow={workflow}
              feed={feed}
              documents={documents}
              memory={memory}
              branches={branches}
              loading={loading || detailsLoading}
              restoring={restoring}
              connectionState={connectionState}
              onOpenDocument={(item) => {
                if (item.stageSelection) {
                  updateView('stage', item.stageSelection)
                  return
                }
                if (!item.documentId) return
                void openDocumentInTab(item.documentId)
              }}
              onOpenMemory={() => {
                updateView('memory')
              }}
              onRefresh={refreshWorkspace}
              error={error}
            />
          </div>
          {view === 'memory' ? (
            <div className="absolute inset-0 min-h-0 z-20">
              <QuestMemorySurface
                questId={questId}
                memory={memory}
                loading={loading || detailsLoading}
                onRefresh={refreshWorkspace}
                onOpenDocument={(documentId) => {
                  void openDocumentInTab(documentId)
                }}
              />
            </div>
          ) : null}
          {view === 'terminal' ? (
            <div className="absolute inset-0 min-h-0 z-20">
              <QuestTerminalSurface questId={questId} onRefresh={refreshWorkspace} />
            </div>
          ) : null}
          {view === 'settings' ? (
            <div className="absolute inset-0 min-h-0 z-20">
              <QuestSettingsSurface
                questId={questId}
                snapshot={snapshot}
                onRefresh={refreshWorkspace}
                focusTarget={settingsFocusTarget}
              />
            </div>
          ) : null}
          {view === 'stage' ? (
            <div className="absolute inset-0 min-h-0 z-20">
              <QuestStageSurface
                questId={questId}
                stageSelection={stageSelection ?? null}
                onRefresh={refreshWorkspace}
              />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

export function QuestWorkspaceSurface(
  props: Omit<QuestWorkspaceSurfaceInnerProps, 'workspace'> & {
    workspace?: QuestWorkspaceState
  }
) {
  const internalWorkspace = useQuestWorkspace(props.workspace ? null : props.questId)
  const workspace = props.workspace ?? internalWorkspace
  return <QuestWorkspaceSurfaceInner {...props} workspace={workspace} />
}

export default QuestWorkspaceSurface
