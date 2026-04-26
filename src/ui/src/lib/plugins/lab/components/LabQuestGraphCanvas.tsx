'use client'

import * as React from 'react'
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  MarkerType,
  Position as FlowPosition,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useNodesInitialized,
  useReactFlow,
  type Node,
  type Edge,
  type NodeProps,
  type NodeTypes,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import '@/lib/plugins/lab/lab.css'
import dagre from '@dagrejs/dagre'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ChevronDown, Clock, FileText, GitBranch, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { isDemoProjectId } from '@/demo/projects'
import {
  getLabQuestGraph,
  listLabQuestEvents,
  listLabAgents,
  listLabMemory,
  listLabPapers,
  updateLabQuestLayout,
  type LabQuestGraphResponse,
  type LabQuestGraphNode,
  type LabQuestGraphEdge,
  type LabQuestEventItem,
  type LabPaper,
  type LabMemoryEntry,
  type LabCanvasPreferences,
  type LabMetricObjective,
  type LabMetricCurve,
  type LabMetricCurvePoint,
  type LabQuestSelectionContext,
} from '@/lib/api/lab'
import { cn } from '@/lib/utils'
import { formatRelativeTime, resolveAgentDisplayName, resolveAgentMentionLabel } from './lab-helpers'
import { useOpenFile } from '@/hooks/useOpenFile'
import { useFileTreeStore } from '@/lib/stores/file-tree'
import { useI18n } from '@/lib/i18n/useI18n'
import { useLabGraphSelectionStore } from '@/lib/stores/lab-graph-selection'
import { useThemeStore } from '@/lib/stores/theme'
import {
  LAB_CANVAS_SEMANTIC_TONE_META,
  resolveLabCanvasViewSemantic,
} from './lab-semantics'

type LabQuestGraphCanvasProps = {
  projectId: string
  questId: string
  readOnly?: boolean
  liveRun?: boolean
  fetchGraph?: (
    projectId: string,
    questId: string,
    params?: { view?: string; search?: string; atEventId?: string | null }
  ) => Promise<LabQuestGraphResponse>
  fetchEvents?: (
    projectId: string,
    questId: string,
    params?: {
      branch?: string
      eventIds?: string[]
      eventTypes?: string[]
      eventPrefixes?: string[]
      cursor?: string
      limit?: number
      includePayload?: boolean
    }
  ) => Promise<{ items: LabQuestEventItem[]; next_cursor?: string | null; has_more?: boolean }>
  highlightNodeId?: string | null
  highlightBranch?: string | null
  atEventId?: string | null
  preferredViewMode?: 'branch' | 'event' | 'stage'
  activeBranch?: string | null
  onBranchSelect?: (branch: string) => void
  onEventSelect?: (eventId: string, branchName?: string) => void
  onSelectionChange?: (selection: LabQuestSelectionContext | null) => void
  onStageOpen?: (selection: LabQuestSelectionContext & { label?: string | null; summary?: string | null }) => void
  showFloatingPanels?: boolean
  minimalChrome?: boolean
}

type QuestNodeData = {
  label: string
  subtitle?: string | null
  branchNo?: string | null
  parentBranch?: string | null
  ideaTitle?: string | null
  foundationLabel?: string | null
  foundationReason?: string | null
  foundationRef?: Record<string, unknown> | null
  status?: string | null
  metric?: string | null
  verdict?: string | null
  summary?: string | null
  deltaLabel?: string | null
  trend?: Array<number>
  isHead?: boolean
  isSelected?: boolean
  isEvent?: boolean
  branchName?: string | null
  decisionType?: string | null
  decisionTarget?: string | null
  stageKey?: string | null
  stageTitle?: string | null
  eventCount?: number | null
  eventIds?: string[] | null
  isAgent?: boolean
  agentInstanceId?: string | null
  isRoot?: boolean
  isPlaceholder?: boolean
  stageLabel?: string | null
  nowDoing?: string | null
  decisionReason?: string | null
  evidenceStatus?: string | null
  branchClass?: string | null
  nodeKind?: string | null
  scopePaths?: string[] | null
  compareBase?: string | null
  compareHead?: string | null
  worktreeRelPath?: string | null
  memoryLabel?: string | null
  memorySummary?: string | null
  memoryCount?: number | null
  baselineState?: string | null
  pushState?: string | null
  writerState?: string | null
  runtimeState?: string | null
  protectedState?: string | null
  divergenceState?: string | null
  reconcileState?: string | null
  proofState?: string | null
  submissionState?: string | null
  retireState?: string | null
  claimEvidenceState?: string | null
  baselineGate?: string | null
  displayMode?: 'summary' | 'metric'
  metricKey?: string | null
  metricLabel?: string | null
  metricValueLabel?: string | null
  metricDeltaLabel?: string | null
  metricDirection?: 'higher' | 'lower' | null
  metricTone?: 'good' | 'bad' | 'neutral' | null
  metricEmptyReason?: string | null
  isCurrentWorkspace?: boolean
  isCurrentPath?: boolean
}

type AgentNodeData = {
  label: string
  subtitle?: string | null
  status?: string | null
  branchName?: string | null
  agentInstanceId?: string | null
  isAgent?: boolean
}

type Position = { x: number; y: number }

type QuestFlowNodeData = QuestNodeData | AgentNodeData
type QuestFlowNode = Node<QuestFlowNodeData>
type GraphHoverLine = {
  label: string
  value: string
}

type GraphHoverCardState = {
  x: number
  y: number
  title: string
  subtitle?: string | null
  badge?: string | null
  tone?: 'neutral' | 'positive' | 'overlay' | 'replay'
  lines: GraphHoverLine[]
  footer?: string | null
}

type QuestLayoutMap = Record<string, Position>

type QuestLayoutJson = {
  branch?: QuestLayoutMap
  event?: QuestLayoutMap
  stage?: QuestLayoutMap
  preferences?: LabCanvasPreferences
  [key: string]: unknown
}

type PathFilterMode = 'all' | 'current' | 'selected'

type BranchStage =
  | 'scout'
  | 'baseline'
  | 'idea'
  | 'experiment'
  | 'analysis-campaign'
  | 'write'
  | 'finalize'
  | 'completed'

type BranchInsight = {
  branchName: string
  stage: BranchStage
  stageLabel: string
  nowDoing: string | null
  decisionReason: string | null
  evidenceStatus: string | null
  verdict: string | null
  writingEligible: boolean
  writingActive: boolean
  completed: boolean
  updatedAt: string | null
  stale: boolean
  workflowState: LabQuestGraphNode['workflow_state'] | null
}

type BranchMemorySnapshot = {
  count: number
  latestTitle: string | null
  latestSummary: string | null
  latestStamp: string | null
}

type PipelineStepStatus = 'done' | 'active' | 'pending'

const GRID_X = 240
const GRID_Y = 170
const DEPTH_SPREAD = 28
const DAGRE_NODE_WIDTH = 228
const DAGRE_NODE_HEIGHT = 144
const DAGRE_BRANCH_NODE_BASE_HEIGHT = 96
const DAGRE_BRANCH_NODE_MIN_HEIGHT = 160
const DAGRE_BRANCH_NODE_TEXT_ROW_HEIGHT = 16
const DAGRE_BRANCH_NODE_SUMMARY_HEIGHT = 36
const DAGRE_BRANCH_NODE_METRIC_HEIGHT = 84
const DAGRE_BRANCH_NODE_MEMORY_HEIGHT = 56
const DAGRE_BRANCH_NODE_TREND_HEIGHT = 48
const DAGRE_STAGE_NODE_HEIGHT = 132
const DAGRE_EVENT_NODE_HEIGHT = 140
const DAGRE_LAYOUT_BUFFER_HEIGHT = 16
const AUTO_LAYOUT_GAP_X = 36
const AUTO_LAYOUT_GAP_Y = 32
const AUTO_LAYOUT_MAX_PASSES = 8
const DAY_MS = 24 * 60 * 60 * 1000
const STALE_BRANCH_MS = 3 * DAY_MS
const EMPTY_GRAPH_NODES: LabQuestGraphNode[] = []
const EMPTY_GRAPH_EDGES: LabQuestGraphEdge[] = []
const FLOATING_PANEL_MARGIN = 14
const ORB_SIZE = 44
const ORB_STEP = ORB_SIZE + 12
const CANVAS_EXTENT = 200000
const BRANCH_PANEL_WIDTH = 320
const BRANCH_PANEL_HEIGHT = 520
const EVENTS_PANEL_WIDTH = 340
const EVENTS_PANEL_HEIGHT = 460
const PAPERS_PANEL_WIDTH = 320
const PAPERS_PANEL_HEIGHT = 420
const GRAPH_POLL_MS = 30000
const PANEL_POLL_MS = 30000
const BACKGROUND_POLL_MS = 45000
const DEMO_POLL_MS = 1200
const PROJECTION_POLL_MS = 1000

const projectionState = (payload?: { projection_status?: { state?: string | null } | null } | null) =>
  String(payload?.projection_status?.state || '')
    .trim()
    .toLowerCase()

const projectionPending = (payload?: { projection_status?: { state?: string | null } | null } | null) => {
  const state = projectionState(payload)
  return Boolean(state) && state !== 'ready'
}

const projectionProgress = (
  payload?: {
    projection_status?: {
      progress_current?: number | null
      progress_total?: number | null
      current_step?: string | null
    } | null
  } | null
) => {
  const status = payload?.projection_status
  const current =
    typeof status?.progress_current === 'number' && Number.isFinite(status.progress_current)
      ? Math.max(0, status.progress_current)
      : 0
  const total =
    typeof status?.progress_total === 'number' && Number.isFinite(status.progress_total)
      ? Math.max(0, status.progress_total)
      : 0
  if (total <= 0) {
    return null
  }
  return {
    current,
    total,
    percent: Math.min(100, Math.max(0, (current / total) * 100)),
    step: status?.current_step?.trim() || null,
  }
}

const isAnalysisBranch = (branch?: string | null) => {
  if (!branch) return false
  return branch.includes('/analysis/') || branch.startsWith('analysis/')
}

const isKeyEventType = (raw?: string | null) => {
  const value = String(raw || '').toLowerCase()
  if (!value) return false
  return (
    value === 'artifact.recorded' ||
    value === 'quest.control' ||
    value === 'runner.tool_result' ||
    value === 'decision' ||
    value === 'approval' ||
    value === 'baseline' ||
    value === 'idea' ||
    value === 'run' ||
    value === 'report'
  )
}

const pickPrimaryMetric = (metrics?: Record<string, unknown> | null) => {
  if (!metrics || typeof metrics !== 'object') return null
  const entry = Object.entries(metrics).find(([, value]) => typeof value === 'number')
  if (!entry) return null
  const [key, value] = entry
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) return null
  return `${key}: ${numeric.toFixed(3)}`
}

const pickMetricValue = (metrics?: Record<string, unknown> | null, metricKey?: string | null) => {
  if (!metrics || typeof metrics !== 'object') return null
  if (metricKey) {
    const candidate = metrics[metricKey]
    if (typeof candidate === 'number' && Number.isFinite(candidate)) {
      return { key: metricKey, value: candidate }
    }
  }
  const entry = Object.entries(metrics).find(([, value]) => typeof value === 'number')
  if (!entry) return null
  const [key, value] = entry
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return { key, value }
}

const formatMetricLabel = (key: string, value: number) => `${key}: ${value.toFixed(3)}`

type NodeMetricMeta = {
  key: string
  label: string
  direction: 'higher' | 'lower' | null
  unit?: string | null
  decimals?: number | null
}

type NodeMetricSnapshot = {
  metrics: Record<string, number>
  deltas: Record<string, number>
  meta: Map<string, NodeMetricMeta>
}

const normalizeMetricDirection = (value: unknown): 'higher' | 'lower' | null => {
  const text = String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[- ]+/g, '_')
  if (text === 'higher' || text === 'maximize' || text === 'higher_better' || text === 'more_is_better') {
    return 'higher'
  }
  if (text === 'lower' || text === 'minimize' || text === 'lower_better' || text === 'less_is_better') {
    return 'lower'
  }
  return null
}

const buildNodeMetricSnapshot = (node: LabQuestGraphNode): NodeMetricSnapshot => {
  const metrics: Record<string, number> = {}
  const deltas: Record<string, number> = {}
  const meta = new Map<string, NodeMetricMeta>()

  const upsertMeta = (
    key: string,
    patch: Partial<NodeMetricMeta> & {
      label?: string | null
      direction?: 'higher' | 'lower' | null
      unit?: string | null
      decimals?: number | null
    }
  ) => {
    if (!key) return
    const current = meta.get(key)
    meta.set(key, {
      key,
      label: patch.label || current?.label || key,
      direction: patch.direction ?? current?.direction ?? null,
      unit: patch.unit ?? current?.unit ?? null,
      decimals: patch.decimals ?? current?.decimals ?? null,
    })
  }

  ;(node.latest_result?.metric_contract?.metrics ?? []).forEach((item) => {
    if (!item?.metric_id) return
    const key = String(item.metric_id).trim()
    if (!key) return
    upsertMeta(key, {
      label: String(item.label || key).trim() || key,
      direction: normalizeMetricDirection(item.direction),
      unit: item.unit ?? null,
      decimals: typeof item.decimals === 'number' ? item.decimals : null,
    })
  })

  ;(node.latest_result?.baseline_comparisons?.items ?? []).forEach((item) => {
    if (!item?.metric_id) return
    const key = String(item.metric_id).trim()
    if (!key) return
    upsertMeta(key, {
      label: String(item.label || key).trim() || key,
      direction: normalizeMetricDirection(item.direction),
      unit: item.unit ?? null,
      decimals: typeof item.decimals === 'number' ? item.decimals : null,
    })
    if (typeof item.delta === 'number' && Number.isFinite(item.delta)) {
      deltas[key] = Number(item.delta)
    }
  })

  ;(node.latest_result?.metric_rows ?? []).forEach((row) => {
    if (!row || typeof row !== 'object' || Array.isArray(row)) return
    const record = row as Record<string, unknown>
    const key = String(record.metric_id || record.name || record.metric || '').trim()
    const numeric =
      typeof record.numeric_value === 'number' && Number.isFinite(record.numeric_value)
        ? Number(record.numeric_value)
        : typeof record.value === 'number' && Number.isFinite(record.value)
          ? Number(record.value)
          : null
    if (!key) return
    upsertMeta(key, {
      label: String(record.label || record.name || key).trim() || key,
      direction: normalizeMetricDirection(record.direction),
      unit: typeof record.unit === 'string' ? record.unit : null,
      decimals: typeof record.decimals === 'number' ? record.decimals : null,
    })
    if (numeric !== null) {
      metrics[key] = numeric
    }
    if (!(key in deltas) && typeof record.delta === 'number' && Number.isFinite(record.delta)) {
      deltas[key] = Number(record.delta)
    }
  })

  Object.entries(node.metrics_json ?? {}).forEach(([key, value]) => {
    if (typeof value === 'number' && Number.isFinite(value)) {
      metrics[key] = Number(value)
      upsertMeta(key, {})
    }
  })

  Object.entries((node.node_summary?.metrics_delta as Record<string, unknown> | null) ?? {}).forEach(([key, value]) => {
    if (key in deltas) return
    if (typeof value !== 'number' || !Number.isFinite(value)) return
    deltas[key] = Number(value)
  })

  return { metrics, deltas, meta }
}

const buildBaselineMetricSnapshot = (nodes: LabQuestGraphNode[]): NodeMetricSnapshot => {
  const baselineNode = nodes.find((node) => node.node_kind === 'baseline_root')
  const fromNode = baselineNode ? buildNodeMetricSnapshot(baselineNode) : null
  if (fromNode && Object.keys(fromNode.metrics).length) return fromNode

  const metrics: Record<string, number> = {}
  const deltas: Record<string, number> = {}
  const meta = new Map<string, NodeMetricMeta>()
  nodes.forEach((node) => {
    ;(node.latest_result?.baseline_comparisons?.items ?? []).forEach((item) => {
      if (!item?.metric_id || typeof item.baseline_value !== 'number' || !Number.isFinite(item.baseline_value)) return
      metrics[item.metric_id] = Number(item.baseline_value)
      const current = meta.get(item.metric_id)
      meta.set(item.metric_id, {
        key: item.metric_id,
        label: String(item.label || current?.label || item.metric_id).trim() || item.metric_id,
        direction: normalizeMetricDirection(item.direction) || current?.direction || null,
        unit: item.unit ?? current?.unit ?? null,
        decimals: typeof item.decimals === 'number' ? item.decimals : current?.decimals ?? null,
      })
    })
  })
  return { metrics, deltas, meta }
}

const formatMetricValueDisplay = (value: number, meta?: NodeMetricMeta | null) => {
  const decimals =
    typeof meta?.decimals === 'number'
      ? meta.decimals
      : Math.abs(value) < 1
        ? 4
        : Math.abs(value) < 10
          ? 3
          : 2
  const rendered = value.toFixed(Math.max(0, Math.min(6, decimals)))
  return meta?.unit ? `${rendered} ${meta.unit}` : rendered
}

const resolveMetricTone = (
  delta: number | null | undefined,
  direction: 'higher' | 'lower' | null | undefined
): 'good' | 'bad' | 'neutral' => {
  if (typeof delta !== 'number' || !Number.isFinite(delta) || delta === 0) return 'neutral'
  if (direction === 'lower') {
    return delta < 0 ? 'good' : 'bad'
  }
  if (direction === 'higher') {
    return delta > 0 ? 'good' : 'bad'
  }
  return delta > 0 ? 'good' : 'bad'
}

const formatMetricDeltaDisplay = (delta: number, meta?: NodeMetricMeta | null) => {
  const sign = delta >= 0 ? '+' : ''
  return `Δ ${sign}${formatMetricValueDisplay(delta, meta)} vs baseline`
}

const clampCanvasText = (value?: string | null, limit = 84) => {
  const text = String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
  if (!text) return null
  if (text.length <= limit) return text
  return `${text.slice(0, Math.max(0, limit - 1)).trimEnd()}…`
}

const formatDeltaLabel = (delta?: Record<string, unknown> | number | null) => {
  if (!delta) return null
  if (typeof delta === 'number' && Number.isFinite(delta)) {
    const sign = delta >= 0 ? '+' : ''
    return `${sign}${delta.toFixed(3)}`
  }
  if (typeof delta === 'object') {
    const entry = Object.entries(delta).find(([, value]) => typeof value === 'number')
    if (!entry) return null
    const [key, value] = entry
    const numeric = typeof value === 'number' ? value : Number(value)
    if (!Number.isFinite(numeric)) return null
    const sign = numeric >= 0 ? '+' : ''
    return `${key} ${sign}${numeric.toFixed(3)}`
  }
  return null
}

const formatStateLabel = (value?: string | null) => {
  const normalized = String(value || '')
    .trim()
    .replace(/[_-]+/g, ' ')
  if (!normalized) return 'N/A'
  return normalized.replace(/\b\w/g, (char) => char.toUpperCase())
}

const semanticToneBadgeClass = (tone: 'truth' | 'abstraction' | 'runtime' | 'overlay') => {
  if (tone === 'truth') {
    return 'border-[rgba(64,113,175,0.24)] bg-[rgba(64,113,175,0.1)] text-[#315c97] dark:text-[#9ec5ff]'
  }
  if (tone === 'runtime') {
    return 'border-[rgba(99,102,241,0.24)] bg-[rgba(99,102,241,0.1)] text-[#4f46e5] dark:text-[#c7d2fe]'
  }
  if (tone === 'overlay') {
    return 'border-[rgba(83,176,174,0.26)] bg-[rgba(83,176,174,0.12)] text-[#0f766e] dark:text-[#8be4db]'
  }
  return 'border-[rgba(148,163,184,0.26)] bg-[rgba(148,163,184,0.12)] text-[var(--lab-text-secondary)]'
}

const normalizeMetricCatalog = (raw: unknown) => {
  if (!Array.isArray(raw)) return []
  const seen = new Set<string>()
  const catalog: LabMetricObjective[] = []
  raw.forEach((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return
    const record = item as Record<string, unknown>
    const key = String(record.key || '').trim()
    if (!key || seen.has(key)) return
    seen.add(key)
    const label = String(record.label || '').trim() || key
    const direction = String(record.direction || '').trim().toLowerCase()
    const normalizedDirection = direction === 'lower' || direction === 'higher' ? direction : null
    const importanceRaw = record.importance
    const importance =
      typeof importanceRaw === 'number' && Number.isFinite(importanceRaw) ? Number(importanceRaw) : null
    const unit = String(record.unit || '').trim() || null
    const targetRaw = record.target
    const target = typeof targetRaw === 'number' && Number.isFinite(targetRaw) ? Number(targetRaw) : null
    catalog.push({
      key,
      label,
      direction: normalizedDirection,
      importance,
      unit,
      target,
    })
  })
  return catalog
}

const normalizeMetricCurveMap = (raw: unknown) => {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null

  const normalizePoints = (pointsRaw: unknown): LabMetricCurvePoint[] => {
    if (!Array.isArray(pointsRaw)) return []
    const points: LabMetricCurvePoint[] = []
    pointsRaw.forEach((item, index) => {
      if (typeof item === 'number' && Number.isFinite(item)) {
        points.push({ seq: index + 1, value: Number(item) })
        return
      }
      if (!item || typeof item !== 'object' || Array.isArray(item)) return
      const record = item as Record<string, unknown>
      const valueRaw = record.value
      if (typeof valueRaw !== 'number' || !Number.isFinite(valueRaw)) return
      const seqRaw = record.seq
      const seq =
        typeof seqRaw === 'number' && Number.isFinite(seqRaw) && seqRaw > 0
          ? Math.floor(seqRaw)
          : index + 1
      const ts = typeof record.ts === 'string' && record.ts.trim() ? record.ts.trim() : null
      const runId = typeof record.run_id === 'string' && record.run_id.trim() ? record.run_id.trim() : null
      const eventId = typeof record.event_id === 'string' && record.event_id.trim() ? record.event_id.trim() : null
      const isSota = record.is_sota === true
      points.push({
        seq,
        ts,
        value: Number(valueRaw),
        run_id: runId,
        event_id: eventId,
        is_sota: isSota,
      })
    })
    return points
  }

  const normalizeDirection = (value: unknown) => {
    const text = String(value || '').trim().toLowerCase()
    if (text === 'higher' || text === 'lower') return text
    return null
  }

  const result: Record<string, LabMetricCurve> = {}
  Object.entries(raw as Record<string, unknown>).forEach(([key, curveRaw]) => {
    const keyText = String(key || '').trim()
    if (!keyText) return

    if (Array.isArray(curveRaw)) {
      const full = normalizePoints(curveRaw)
      if (!full.length) return
      result[keyText] = { full, sota: full }
      return
    }
    if (!curveRaw || typeof curveRaw !== 'object') return

    const record = curveRaw as Record<string, unknown>
    const full = normalizePoints(record.full)
    const legacySeries = normalizePoints(record.series)
    const fallback = normalizePoints(record.points)
    const mergedFull = full.length ? full : legacySeries.length ? legacySeries : fallback
    const rawSota = normalizePoints(record.sota)
    const sota = rawSota.length ? rawSota : mergedFull
    if (!mergedFull.length && !sota.length) return

    const normalized: LabMetricCurve = {
      full: mergedFull,
      sota,
    }
    const direction = normalizeDirection(record.direction)
    if (direction) normalized.direction = direction
    const label = String(record.label || '').trim()
    if (label) normalized.label = label
    const importance = record.importance
    if (typeof importance === 'number' && Number.isFinite(importance)) {
      normalized.importance = Number(importance)
    }
    result[keyText] = normalized
  })

  return Object.keys(result).length ? result : null
}

const resolveNodeMetricCurves = (node: LabQuestGraphNode) => {
  const fromSummary = normalizeMetricCurveMap(node.node_summary?.metric_curves)
  if (fromSummary) return fromSummary
  const fromMetrics = normalizeMetricCurveMap((node.metrics_json as Record<string, unknown> | null)?.metric_curves)
  if (fromMetrics) return fromMetrics
  return null
}

const extractTrend = (
  node: LabQuestGraphNode,
  options?: {
    metricKey?: string | null
    mode?: 'sota' | 'full'
  }
) => {
  const curves = resolveNodeMetricCurves(node)
  const mode = options?.mode === 'full' ? 'full' : 'sota'
  const metricKey = options?.metricKey
  if (curves) {
    let curve = metricKey ? curves[metricKey] : undefined
    if (!curve) {
      const firstKey = Object.keys(curves)[0]
      if (firstKey) curve = curves[firstKey]
    }
    if (curve && typeof curve === 'object') {
      const series = mode === 'full' ? curve.full : curve.sota
      if (Array.isArray(series) && series.length) {
        const values = series
          .map((point) => {
            if (point && typeof point === 'object' && typeof point.value === 'number') return point.value
            return null
          })
          .filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
        if (values.length) return values
      }
    }
  }
  const summaryTrend = node.node_summary?.trend_preview
  const rawTrend = Array.isArray(summaryTrend)
    ? summaryTrend
    : Array.isArray((node.metrics_json as any)?.trend)
      ? ((node.metrics_json as any).trend as Array<any>)
      : []
  const values = rawTrend
    .map((point) => {
      if (typeof point === 'number') return point
      if (point && typeof point === 'object' && typeof point.value === 'number') return point.value
      return null
    })
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
  return values.length ? values : null
}

const formatCurveTimestamp = (ts?: string | null) => {
  if (!ts) return 'n/a'
  const date = new Date(ts)
  if (Number.isNaN(date.getTime())) return ts
  return date.toLocaleString()
}

function extractEventPayload(raw?: Record<string, unknown> | null) {
  if (!raw || typeof raw !== 'object') return null
  const payload = (raw as any).payload
  if (payload && typeof payload === 'object') return payload as Record<string, unknown>
  return null
}

function extractEmbeddedRawEvent(raw?: Record<string, unknown> | null) {
  if (!raw || typeof raw !== 'object') return null
  const event = (raw as any).event
  if (event && typeof event === 'object') return event as Record<string, unknown>
  return null
}

const asString = (value: unknown) => {
  if (typeof value === 'string') return value.trim() || null
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
}

const asRecord = (value: unknown) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

const asArray = (value: unknown) => (Array.isArray(value) ? value : [])

const resolveEventStageKey = (event: LabQuestEventItem) => {
  const payload = extractEventPayload(event.payload_json as Record<string, unknown> | null)
  const explicit = String(
    event.stage_key || payload?.stage_key || payload?.protocol_step || payload?.flow_type || payload?.run_kind || ''
  )
    .trim()
    .toLowerCase()
  if (!explicit) return null
  if (explicit.includes('analysis')) return 'analysis-campaign'
  if (explicit.includes('write') || explicit.includes('paper')) return 'write'
  if (explicit.includes('baseline') || explicit.includes('reproduce')) return 'baseline'
  if (explicit.includes('scout') || explicit.includes('research') || explicit.includes('literature')) return 'scout'
  if (explicit.includes('experiment')) return 'experiment'
  if (explicit.includes('final')) return 'finalize'
  if (explicit.includes('idea')) return 'idea'
  if (explicit.includes('decision')) return 'decision'
  return explicit
}

const resolveEventArtifactKind = (event: LabQuestEventItem) => {
  const payload = extractEventPayload(event.payload_json as Record<string, unknown> | null)
  return String(payload?.kind || '').trim().toLowerCase() || null
}

const isDecisionEvent = (event: LabQuestEventItem) => {
  const kind = resolveEventArtifactKind(event)
  const stage = resolveEventStageKey(event)
  return event.event_type === 'quest.control' || kind === 'decision' || kind === 'approval' || stage === 'decision'
}

const isWritingEvent = (event: LabQuestEventItem) => {
  const kind = resolveEventArtifactKind(event)
  const stage = resolveEventStageKey(event)
  return kind === 'report' || stage === 'write' || stage === 'finalize'
}

const isExperimentEvent = (event: LabQuestEventItem) => {
  const kind = resolveEventArtifactKind(event)
  const stage = resolveEventStageKey(event)
  return kind === 'run' || stage === 'experiment' || stage === 'analysis-campaign'
}

const isIdeaEvent = (event: LabQuestEventItem) => {
  const kind = resolveEventArtifactKind(event)
  const stage = resolveEventStageKey(event)
  return kind === 'idea' || stage === 'idea'
}

const isBaselineEvent = (event: LabQuestEventItem) => {
  const kind = resolveEventArtifactKind(event)
  const stage = resolveEventStageKey(event)
  return kind === 'baseline' || stage === 'baseline'
}

const isErrorEvent = (event: LabQuestEventItem) => {
  const payload = extractEventPayload(event.payload_json as Record<string, unknown> | null)
  const rawEvent = asRecord((event.payload_json as Record<string, unknown> | null)?.event)
  const status = String(payload?.status || rawEvent?.status || '').trim().toLowerCase()
  return status === 'failed' || status === 'error'
}

const isConversationEvent = (event: LabQuestEventItem) =>
  event.event_type === 'conversation.message' || event.event_type === 'interaction.reply_received'

const isToolLifecycleEvent = (event: LabQuestEventItem) =>
  event.event_type === 'runner.tool_call' || event.event_type === 'runner.tool_result'

const STAGE_ORDER: BranchStage[] = [
  'scout',
  'baseline',
  'idea',
  'experiment',
  'analysis-campaign',
  'write',
  'finalize',
  'completed',
]

const BRANCH_STAGE_LABELS: Record<BranchStage, string> = {
  scout: 'Scout',
  baseline: 'Baseline',
  idea: 'Idea',
  experiment: 'Experiment',
  'analysis-campaign': 'Analysis',
  write: 'Write',
  finalize: 'Finalize',
  completed: 'Completed',
}

const formatStageBadge = (stageKey?: string | null) => {
  const normalized = String(stageKey || '').trim().toLowerCase()
  if (!normalized) return null
  if (normalized in BRANCH_STAGE_LABELS) {
    return BRANCH_STAGE_LABELS[normalized as BranchStage]
  }
  return formatStateLabel(normalized)
}

const resolveStageRank = (stage: BranchStage) => STAGE_ORDER.indexOf(stage)

const elevateBranchStage = (current: BranchStage, next: BranchStage) => {
  return resolveStageRank(next) > resolveStageRank(current) ? next : current
}

const parseEventTime = (value?: string | null) => {
  if (!value) return 0
  const parsed = new Date(value).getTime()
  return Number.isFinite(parsed) ? parsed : 0
}

const resolveDecisionReason = (event: LabQuestEventItem) => {
  const payload = extractEventPayload(event.payload_json as Record<string, unknown> | null)
  if (!payload) return event.reply_to_pi || event.payload_summary || null
  if (isDecisionEvent(event)) {
    return (
      asString(payload.reason) ||
      asString(payload.justification) ||
      asString(payload.action) ||
      asString(payload.verdict) ||
      event.reply_to_pi ||
      event.payload_summary ||
      null
    )
  }
  return event.reply_to_pi || event.payload_summary || null
}

const normalizeOutcomeVerdictValue = (value: unknown) => {
  const raw = asString(value)?.toLowerCase().trim() || ''
  if (!raw) return null
  if (['good', 'support', 'go', 'positive'].includes(raw)) return 'good'
  if (['bad', 'refute', 'stop', 'negative', 'failed', 'fail'].includes(raw)) return 'bad'
  if (['mixed', 'inconclusive', 'uncertain', 'partial'].includes(raw)) return 'mixed'
  if (raw.includes('good') || raw.includes('support') || raw.includes('promising')) return 'good'
  if (raw.includes('bad') || raw.includes('refute') || raw.includes('stop') || raw.includes('fail')) return 'bad'
  if (raw.includes('mixed') || raw.includes('inconclusive') || raw.includes('uncertain')) return 'mixed'
  return null
}

const resolveOutcomeVerdict = (event: LabQuestEventItem) => {
  const payload = extractEventPayload(event.payload_json as Record<string, unknown> | null)
  return normalizeOutcomeVerdictValue(payload?.verdict || payload?.status)
}

const resolveDecisionLabel = (event: LabQuestEventItem) => {
  const payload = extractEventPayload(event.payload_json as Record<string, unknown> | null)
  if (isDecisionEvent(event)) {
    return (
      asString(payload?.action)?.toUpperCase() ||
      asString(payload?.verdict)?.toUpperCase() ||
      asString(payload?.status)?.toUpperCase() ||
      'DECISION'
    )
  }
  return event.event_type
}

const summarizeEvent = (event?: LabQuestEventItem | null) => {
  if (!event) return null
  const payload = extractEventPayload(event.payload_json as Record<string, unknown> | null)
  return (
    event.reply_to_pi ||
    asString(payload?.summary) ||
    asString(payload?.reason) ||
    event.payload_summary ||
    resolveDecisionLabel(event) ||
    event.event_type ||
    null
  )
}

const resolveEventToolName = (event: LabQuestEventItem) => {
  const rawEvent = extractEmbeddedRawEvent(event.payload_json as Record<string, unknown> | null)
  return (
    asString(rawEvent?.tool_name) ||
    asString(rawEvent?.mcp_tool) ||
    asString(rawEvent?.tool) ||
    null
  )
}

const resolveEventHeadline = (event: LabQuestEventItem) => {
  const payload = extractEventPayload(event.payload_json as Record<string, unknown> | null)
  const rawEvent = extractEmbeddedRawEvent(event.payload_json as Record<string, unknown> | null)
  if (isDecisionEvent(event)) {
    return resolveDecisionLabel(event)
  }
  if (event.event_type === 'artifact.recorded') {
    const kind = asString(payload?.kind) || resolveEventArtifactKind(event) || 'artifact'
    const artifactId = asString(payload?.artifact_id) || asString(payload?.id)
    return artifactId ? `${formatStateLabel(kind)} · ${artifactId}` : `${formatStateLabel(kind)} artifact`
  }
  if (event.event_type === 'conversation.message') {
    const role = String(rawEvent?.role || '').trim().toLowerCase()
    return role === 'user' ? 'User message' : `${formatStateLabel(role || 'message')}`
  }
  if (event.event_type === 'interaction.reply_received') {
    return 'Queued reply'
  }
  if (isToolLifecycleEvent(event)) {
    const toolName = resolveEventToolName(event) || event.event_type
    const status =
      event.event_type === 'runner.tool_call'
        ? 'calling'
        : asString(rawEvent?.status) || asString(payload?.status) || 'completed'
    return `${toolName} · ${formatStateLabel(status)}`
  }
  if (event.event_type === 'quest.control') {
    const action = asString(payload?.action)
    return action ? `Control · ${formatStateLabel(action)}` : 'Quest control'
  }
  return event.event_type
}

const resolveEventSummaryText = (event: LabQuestEventItem) => {
  const payload = extractEventPayload(event.payload_json as Record<string, unknown> | null)
  const rawEvent = extractEmbeddedRawEvent(event.payload_json as Record<string, unknown> | null)
  if (event.event_type === 'artifact.recorded') {
    return (
      clampCanvasText(asString(payload?.summary) || asString(payload?.reason) || event.payload_summary, 120) ||
      'Artifact recorded.'
    )
  }
  if (isConversationEvent(event)) {
    return (
      clampCanvasText(
        asString(rawEvent?.content) || event.reply_to_pi || event.payload_summary || asString(payload?.summary),
        120
      ) || 'Conversation update.'
    )
  }
  if (isToolLifecycleEvent(event)) {
    return (
      clampCanvasText(
        asString(rawEvent?.output) ||
          asString(rawEvent?.args) ||
          asString(payload?.summary) ||
          event.payload_summary ||
          event.reply_to_pi,
        120
      ) || 'Tool activity recorded.'
    )
  }
  if (event.event_type === 'quest.control') {
    return (
      clampCanvasText(asString(payload?.summary) || asString(payload?.reason) || event.payload_summary, 120) ||
      'Control event recorded.'
    )
  }
  return clampCanvasText(summarizeEvent(event), 120) || 'Event recorded.'
}

const isActiveAgentStatus = (status?: string | null) => {
  const raw = String(status || '').toLowerCase()
  if (!raw) return false
  return raw.includes('running') || raw.includes('waiting') || raw.includes('busy') || raw.includes('active')
}

type LabEdgePalette = {
  defaultStroke: string
  stageStroke: string
  agentStroke: string
}

const resolveEdgePalette = (resolvedTheme: 'light' | 'dark'): LabEdgePalette => {
  if (resolvedTheme === 'dark') {
    return {
      defaultStroke: 'rgba(241, 233, 222, 0.42)',
      stageStroke: '#e0bf88',
      agentStroke: 'rgba(241, 233, 222, 0.54)',
    }
  }
  return {
    defaultStroke: 'rgba(71, 63, 52, 0.38)',
    stageStroke: '#b48d4f',
    agentStroke: 'rgba(71, 63, 52, 0.48)',
  }
}

const resolveEdgeStyle = (edgeType: string | null | undefined, palette: LabEdgePalette) => {
  const normalized = String(edgeType || '').toLowerCase()
  if (normalized === 'sequence') {
    return {
      stroke: palette.defaultStroke,
      strokeWidth: 1.7,
      strokeDasharray: '5 4',
    }
  }
  if (normalized === 'stage') {
    return {
      stroke: palette.stageStroke,
      strokeWidth: 2.2,
    }
  }
  return {
    stroke: palette.defaultStroke,
    strokeWidth: 1.85,
  }
}

const buildSelectionContext = (
  questId: string,
  payload: {
    selectionType: string
    selectionRef: string
    branchName?: string | null
    branchNo?: string | null
    parentBranch?: string | null
    foundationRef?: Record<string, unknown> | null
    foundationReason?: string | null
    foundationLabel?: string | null
    ideaTitle?: string | null
    stageKey?: string | null
    edgeId?: string | null
    agentInstanceId?: string | null
    worktreeRelPath?: string | null
    traceNodeId?: string | null
    label?: string | null
    summary?: string | null
    compareBase?: string | null
    compareHead?: string | null
    scopePaths?: string[] | null
    nodeKind?: string | null
    baselineGate?: string | null
  }
): LabQuestSelectionContext & { label?: string | null; summary?: string | null } => ({
  selection_type: payload.selectionType,
  selection_ref: payload.selectionRef,
  quest_id: questId,
  branch_name: payload.branchName ?? null,
  branch_no: payload.branchNo ?? null,
  parent_branch: payload.parentBranch ?? null,
  foundation_ref: payload.foundationRef ?? null,
  foundation_reason: payload.foundationReason ?? null,
  foundation_label: payload.foundationLabel ?? null,
  idea_title: payload.ideaTitle ?? null,
  stage_key: payload.stageKey ?? null,
  edge_id: payload.edgeId ?? null,
  agent_instance_id: payload.agentInstanceId ?? null,
  worktree_rel_path: payload.worktreeRelPath ?? null,
  trace_node_id: payload.traceNodeId ?? null,
  compare_base: payload.compareBase ?? null,
  compare_head: payload.compareHead ?? null,
  scope_paths: payload.scopePaths ?? null,
  node_kind: payload.nodeKind ?? null,
  baseline_gate: payload.baselineGate ?? null,
  label: payload.label ?? null,
  summary: payload.summary ?? null,
})

const shouldOpenCanonicalStage = (stageKey?: string | null) => {
  const normalized = String(stageKey || '').trim().toLowerCase()
  return normalized === 'idea' || normalized === 'experiment' || normalized === 'analysis-campaign' || normalized === 'analysis' || normalized === 'write' || normalized === 'paper'
}

type BucketCounts = {
  ideasOnly: number
  experimenting: number
  writingEligible: number
  writingActive: number
  completed: number
  stale: number
}

type EventFilterMode = 'all' | 'activity' | 'decision' | 'error'

type ClaimVerdict = 'support' | 'refute' | 'inconclusive'
type GoDecision = 'go' | 'no-go'

const normalizeClaimVerdict = (value: unknown): ClaimVerdict | null => {
  const text = String(value ?? '').trim().toLowerCase()
  if (text === 'support' || text === 'refute' || text === 'inconclusive') return text
  return null
}

const normalizeGoDecision = (value: unknown): GoDecision | null => {
  const text = String(value ?? '').trim().toLowerCase()
  if (text === 'go' || text === 'no-go') return text
  return null
}

const extractBranchClaimVerdict = (node: LabQuestGraphNode): ClaimVerdict | null => {
  const topLevel = normalizeClaimVerdict(node.claim_verdict)
  if (topLevel) return topLevel
  const summary = normalizeClaimVerdict(node.node_summary?.claim_verdict)
  if (summary) return summary
  const metrics = asRecord(node.metrics_json)
  return normalizeClaimVerdict(metrics?.claim_verdict)
}

const extractBranchGoDecision = (node: LabQuestGraphNode): GoDecision | null => {
  const topLevel = normalizeGoDecision(node.go_decision)
  if (topLevel) return topLevel
  const summary = normalizeGoDecision(node.node_summary?.go_decision)
  if (summary) return summary
  const metrics = asRecord(node.metrics_json)
  return normalizeGoDecision(metrics?.go_decision)
}

const toneForClaimVerdict = (value: ClaimVerdict): 'good' | 'bad' | 'neutral' => {
  if (value === 'support') return 'good'
  if (value === 'refute') return 'bad'
  return 'neutral'
}

const toneForGoDecision = (value: GoDecision): 'good' | 'bad' => {
  return value === 'go' ? 'good' : 'bad'
}

const renderRow = (label: string, value: React.ReactNode | null) => {
  if (value === null || value === undefined || value === '') return null
  return (
    <div className="text-xs text-[var(--lab-text-secondary)]">
      <span className="font-semibold text-[var(--lab-text-primary)]">{label}:</span> {value}
    </div>
  )
}

const renderMetrics = (metrics: unknown) => {
  const record = asRecord(metrics)
  if (!record) return null
  const entries = Object.entries(record).filter(([, value]) => value !== null && value !== undefined)
  if (!entries.length) return null
  return (
    <div className="mt-2 grid gap-1 text-xs text-[var(--lab-text-secondary)]">
      {entries.slice(0, 10).map(([key, value]) => (
        <div key={key}>
          <span className="font-semibold text-[var(--lab-text-primary)]">{key}:</span>{' '}
          {typeof value === 'number' ? value.toFixed(4) : String(value)}
        </div>
      ))}
    </div>
  )
}

const renderPaperList = (items: unknown) => {
  const list = asArray(items)
  if (!list.length) return null
  return (
    <div className="mt-2 space-y-2 text-xs text-[var(--lab-text-secondary)]">
      {list.slice(0, 5).map((item, index) => {
        const record = asRecord(item)
        if (!record) return null
        const title =
          asString(record.title) || asString(record.paper_title) || asString(record.name) || 'Untitled'
        const arxivId = asString(record.arxiv_id) || asString(record.id)
        const authors = asArray(record.authors)
          .map((entry) => asString(entry))
          .filter((entry): entry is string => Boolean(entry))
        const summary = asString(record.abstract) || asString(record.summary)
        return (
          <div key={`${title}-${index}`}>
            <div className="font-semibold text-[var(--lab-text-primary)]">{title}</div>
            {arxivId ? <div>arXiv: {arxivId}</div> : null}
            {authors.length ? <div>Authors: {authors.slice(0, 4).join(', ')}</div> : null}
            {summary ? <div className="line-clamp-3">{summary}</div> : null}
          </div>
        )
      })}
    </div>
  )
}

const renderStageEventDetails = (event: LabQuestEventItem, payload: Record<string, unknown> | null) => {
  if (!payload) return null
  const type = event.event_type
  if (type === 'artifact.recorded') {
    const pathValues = Object.values(asRecord(payload.paths) || {})
      .map((entry) => asString(entry))
      .filter((entry): entry is string => Boolean(entry))
    return (
      <div className="mt-2 space-y-1">
        {renderRow('Kind', asString(payload.kind))}
        {renderRow('Artifact ID', asString(payload.artifact_id) || asString(payload.id))}
        {renderRow('Stage', resolveEventStageKey(event))}
        {renderRow('Status', asString(payload.status))}
        {renderRow('Branch', asString(payload.branch))}
        {renderRow('Commit', asString(payload.head_commit))}
        {renderRow('Idea ID', asString(payload.idea_id))}
        {renderRow('Campaign ID', asString(payload.campaign_id))}
        {renderRow('Summary', asString(payload.summary))}
        {renderRow('Reason', asString(payload.reason))}
        {pathValues.length ? renderRow('Paths', pathValues.join(', ')) : null}
      </div>
    )
  }
  if (type === 'conversation.message' || type === 'interaction.reply_received') {
    const rawEvent = asRecord((event.payload_json as Record<string, unknown> | null)?.event)
    return (
      <div className="mt-2 space-y-1">
        {renderRow('Role', asString(rawEvent?.role))}
        {renderRow('Message', asString(rawEvent?.content) || event.reply_to_pi || event.payload_summary)}
      </div>
    )
  }
  if (type === 'runner.tool_call' || type === 'runner.tool_result') {
    const rawEvent = asRecord((event.payload_json as Record<string, unknown> | null)?.event)
    return (
      <div className="mt-2 space-y-1">
        {renderRow('Tool', asString(rawEvent?.tool_name))}
        {renderRow('Status', asString(rawEvent?.status))}
        {renderRow('Args', asString(rawEvent?.args))}
        {renderRow('Output', asString(rawEvent?.output))}
      </div>
    )
  }
  if (type === 'quest.control') {
    return (
      <div className="mt-2 space-y-1">
        {renderRow('Action', asString(payload.action))}
        {renderRow('Status', asString(payload.status))}
        {renderRow('Summary', asString(payload.summary))}
      </div>
    )
  }
  if (type.startsWith('research.')) {
    const query = asString(payload.query)
    const count = payload.count
    const mode = asString(payload.mode)
    const arxivId = asString(payload.arxiv_id)
    const tags = asArray(payload.tags)
      .map((entry) => asString(entry))
      .filter((entry): entry is string => Boolean(entry))
    const papers = payload.papers ?? payload.items
    return (
      <div className="mt-2 space-y-1">
        {renderRow('Query', query)}
        {renderRow('Count', typeof count === 'number' ? String(count) : asString(count))}
        {renderRow('Mode', mode)}
        {renderRow('ArXiv', arxivId)}
        {tags.length ? renderRow('Tags', tags.join(', ')) : null}
        {renderPaperList(papers)}
      </div>
    )
  }
  if (type === 'agent.spawned') {
    return (
      <div className="mt-2 space-y-1">
        {renderRow('Template', asString(payload.template_key))}
        {renderRow('Agent ID', asString(payload.agent_id))}
        {renderRow('Agent instance', asString(payload.agent_instance_id))}
        {renderRow('Stage', asString(payload.stage_key))}
        {renderRow('Branch', asString(payload.branch))}
      </div>
    )
  }
  if (type === 'idea.created') {
    const idea = asRecord(payload.idea_json)
    const sources = asArray(payload.sources)
      .map((entry) => asString(entry))
      .filter((entry): entry is string => Boolean(entry))
    return (
      <div className="mt-2 space-y-1">
        {renderRow('Idea ID', asString(idea?.id))}
        {renderRow('Claim', asString(idea?.claim))}
        {renderRow('Motivation', asString(idea?.motivation))}
        {renderRow('Method', asString(idea?.theory_and_method))}
        {renderRow('Code plan', asString(idea?.code_level_plan))}
        {sources.length ? renderRow('Sources', sources.join(', ')) : null}
        {renderRow('Summary', asString(payload.idea_summary))}
      </div>
    )
  }
  if (type === 'idea.review_ready') {
    const scores = asRecord(payload.scores)
    return (
      <div className="mt-2 space-y-1">
        {renderRow('Utility', asString(scores?.utility_score))}
        {renderRow('Quality', asString(scores?.quality_score))}
        {renderRow('Exploration', asString(scores?.exploration_score))}
        {renderRow('Reasoning', asString(scores?.reasoning))}
      </div>
    )
  }
  if (type === 'decision.validate') {
    return (
      <div className="mt-2 space-y-1">
        {renderRow('Decision', asString(payload.decision))}
        {renderRow('Target idea', asString(payload.target_idea_id))}
        {renderRow('Next direction', asString(payload.next_direction))}
        {renderRow('Expected ROI', asString(payload.expected_roi))}
        {renderRow('Justification', asString(payload.justification))}
        {renderRow('Reflection', asString(payload.reflection))}
      </div>
    )
  }
  if (type === 'experiment.started') {
    return (
      <div className="mt-2 space-y-1">
        {renderRow('Run ID', asString(payload.run_id))}
        {renderRow('Artifacts root', asString(payload.artifacts_root))}
        {renderRow('Plan', asString(payload.plan_md_path))}
      </div>
    )
  }
  if (type === 'experiment.finished') {
    return (
      <div className="mt-2 space-y-1">
        {renderRow('Run ID', asString(payload.run_id))}
        {renderRow('Status', asString(payload.status))}
        {renderMetrics(payload.metrics)}
        {renderRow('Metrics JSON', asString(payload.metrics_json_path))}
        {renderRow('Metrics MD', asString(payload.metrics_md_path))}
        {renderRow('Summary', asString(payload.summary_path))}
        {renderRow('Runlog summary', asString(payload.runlog_summary_path))}
        {renderRow('Artifact manifest', asString(payload.artifact_manifest_path))}
        {renderRow('Run manifest', asString(payload.run_manifest_path))}
        {renderRow('Report', asString(payload.report_md_path))}
      </div>
    )
  }
  if (type === 'pi.limitation_selected') {
    return (
      <div className="mt-2 space-y-1">
        {renderRow('Selected option', asString(payload.selected_option))}
        {renderRow('Branch intent', asString(payload.branch_intent))}
        {renderRow('Resource hint', asString(payload.resource_hint))}
      </div>
    )
  }
  if (type === 'pi.outcome_reviewed') {
    const focus = asRecord(payload.metrics_focus)
    return (
      <div className="mt-2 space-y-1">
        {renderRow('Verdict', asString(payload.verdict))}
        {renderRow('Reason', asString(payload.reason))}
        {renderRow('Action', asString(payload.action))}
        {focus ? (
          <div className="mt-1 text-xs text-[var(--lab-text-secondary)]">
            <span className="font-semibold text-[var(--lab-text-primary)]">Metrics focus:</span>{' '}
            {asString(focus.label) || asString(focus.key)}
            {focus.baseline !== undefined ? ` (baseline ${String(focus.baseline)})` : ''}
          </div>
        ) : null}
      </div>
    )
  }
  if (type === 'branch.promoted') {
    return (
      <div className="mt-2 space-y-1">
        {renderRow('From', asString(payload.from_branch))}
        {renderRow('To', asString(payload.to_branch))}
        {renderRow('Reason', asString(payload.reason))}
      </div>
    )
  }
  if (type === 'error.reported') {
    return (
      <div className="mt-2 space-y-1">
        {renderRow('Stage', asString(payload.stage))}
        {renderRow('Error type', asString(payload.error_type))}
        {renderRow('Error message', asString(payload.error_message))}
        {renderRow('Log path', asString(payload.log_path))}
      </div>
    )
  }
  if (type.startsWith('write.')) {
    if (type === 'write.needs_experiment') {
      const needs = asArray(payload.needs)
        .map((entry) => asRecord(entry))
        .filter((entry): entry is Record<string, unknown> => Boolean(entry))
      return (
        <div className="mt-2 space-y-2 text-xs text-[var(--lab-text-secondary)]">
          {renderRow('Justification', asString(payload.justification))}
          {needs.length ? (
            <div className="space-y-2">
              {needs.slice(0, 5).map((need, index) => (
                <div key={String(need.id || `need-${index}`)}>
                  <div className="font-semibold text-[var(--lab-text-primary)]">
                    {asString(need.id) || 'Need'}
                  </div>
                  {renderRow('Goal', asString(need.goal))}
                  {renderRow('Experiment hint', asString(need.experiment_hint))}
                  {renderRow('Branch hint', asString(need.branch_hint))}
                  {renderRow('Dataset hint', asString(need.dataset_hint))}
                  {renderRow('Resource hint', asString(need.resource_hint))}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )
    }
    const issues = asArray(payload.issues)
      .map((entry) => asString(entry))
      .filter((entry): entry is string => Boolean(entry))
    const reportPaths = asArray(payload.report_paths)
      .map((entry) => asString(entry))
      .filter((entry): entry is string => Boolean(entry))
    const draftTexPaths = asArray(payload.draft_tex_paths)
      .map((entry) => asString(entry))
      .filter((entry): entry is string => Boolean(entry))
    return (
      <div className="mt-2 space-y-1">
        {renderRow('Outline', asString(payload.outline_md_path))}
        {renderRow('Outline JSON', asString(payload.outline_json_path))}
        {renderRow('Draft', asString(payload.draft_md_path))}
        {renderRow('Writing plan', asString(payload.writing_plan_path))}
        {draftTexPaths.length ? renderRow('Draft TeX', draftTexPaths.join(', ')) : null}
        {renderRow('Review', asString(payload.review_path))}
        {issues.length ? renderRow('Issues', issues.join('; ')) : null}
        {renderRow('Claim map', asString(payload.claim_evidence_map_path))}
        {renderRow('Revision round', asString(payload.revision_round))}
        {renderRow('Revision status', asString(payload.status))}
        {reportPaths.length ? renderRow('Reports', reportPaths.join(', ')) : null}
        {renderRow('Paper MD', asString(payload.paper_md_path))}
        {renderRow('Final TeX', asString(payload.final_tex_path))}
        {renderRow('References', asString(payload.references_bib_path))}
        {renderRow('Bundle manifest', asString(payload.paper_bundle_manifest_path))}
      </div>
    )
  }
  return null
}

const STAGE_EVENT_GROUPS: Array<{
  key: string
  label: string
  match: (event: LabQuestEventItem) => boolean
}> = [
  { key: 'scout', label: 'Scout', match: (event) => resolveEventStageKey(event) === 'scout' },
  { key: 'baseline', label: 'Baseline', match: (event) => isBaselineEvent(event) },
  { key: 'ideas', label: 'Ideas', match: (event) => isIdeaEvent(event) },
  { key: 'decisions', label: 'Decisions', match: (event) => isDecisionEvent(event) },
  { key: 'experiments', label: 'Experiments', match: (event) => isExperimentEvent(event) },
  { key: 'writing', label: 'Writing', match: (event) => isWritingEvent(event) },
  { key: 'conversation', label: 'Conversation', match: (event) => isConversationEvent(event) },
  { key: 'errors', label: 'Errors', match: (event) => isErrorEvent(event) },
  { key: 'tools', label: 'Tools', match: (event) => isToolLifecycleEvent(event) },
]

const resolveStageGroupLabel = (event: LabQuestEventItem) => {
  for (const group of STAGE_EVENT_GROUPS) {
    if (group.match(event)) return group.label
  }
  return 'Other'
}

const groupStageEvents = (events: LabQuestEventItem[]) => {
  const buckets = new Map<string, LabQuestEventItem[]>()
  events.forEach((event) => {
    const label = resolveStageGroupLabel(event)
    const bucket = buckets.get(label)
    if (bucket) {
      bucket.push(event)
    } else {
      buckets.set(label, [event])
    }
  })
  const orderedLabels = [...STAGE_EVENT_GROUPS.map((group) => group.label), 'Other']
  const groups: Array<{ label: string; items: LabQuestEventItem[] }> = []
  orderedLabels.forEach((label) => {
    const items = buckets.get(label)
    if (items && items.length) {
      groups.push({ label, items })
    }
  })
  return groups
}

const toFixedPoint = (value: number) => Number(value.toFixed(2))

const buildSmoothPath = (points: Array<{ x: number; y: number }>) => {
  if (points.length < 2) return ''
  let path = `M ${toFixedPoint(points[0].x)} ${toFixedPoint(points[0].y)}`
  for (let index = 0; index < points.length - 1; index += 1) {
    const p0 = points[index - 1] ?? points[index]
    const p1 = points[index]
    const p2 = points[index + 1]
    const p3 = points[index + 2] ?? p2
    const c1x = p1.x + (p2.x - p0.x) / 6
    const c1y = p1.y + (p2.y - p0.y) / 6
    const c2x = p2.x - (p3.x - p1.x) / 6
    const c2y = p2.y - (p3.y - p1.y) / 6
    path += ` C ${toFixedPoint(c1x)} ${toFixedPoint(c1y)} ${toFixedPoint(c2x)} ${toFixedPoint(c2y)} ${toFixedPoint(p2.x)} ${toFixedPoint(p2.y)}`
  }
  return path
}

const buildAreaPath = (points: Array<{ x: number; y: number }>, baselineY: number) => {
  if (points.length < 2) return ''
  const start = points[0]
  const end = points[points.length - 1]
  const segments = points.map((point) => `L ${toFixedPoint(point.x)} ${toFixedPoint(point.y)}`).join(' ')
  return `M ${toFixedPoint(start.x)} ${toFixedPoint(baselineY)} ${segments} L ${toFixedPoint(end.x)} ${toFixedPoint(baselineY)} Z`
}

const normalizeCurveValues = (values?: number[] | null) => {
  if (!Array.isArray(values)) return []
  return values.filter((value) => typeof value === 'number' && Number.isFinite(value))
}

const MetricCurveChart = ({
  values,
  className,
  variant = 'compact',
}: {
  values?: number[] | null
  className?: string
  variant?: 'compact' | 'expanded'
}) => {
  const chartId = React.useId().replace(/:/g, '')
  const normalized = normalizeCurveValues(values)
  if (normalized.length < 2) return null
  const width = variant === 'expanded' ? 248 : 116
  const height = variant === 'expanded' ? 90 : 36
  const padding = variant === 'expanded'
    ? { top: 10, right: 10, bottom: 8, left: 8 }
    : { top: 4, right: 2, bottom: 4, left: 2 }
  const plotWidth = width - padding.left - padding.right
  const plotHeight = height - padding.top - padding.bottom
  const min = Math.min(...normalized)
  const max = Math.max(...normalized)
  const range = max - min || 1
  const points = normalized.map((value, index) => {
    const x = padding.left + (index / (normalized.length - 1)) * plotWidth
    const y = padding.top + plotHeight - ((value - min) / range) * plotHeight
    return { x, y }
  })
  const linePath = buildSmoothPath(points)
  const baselineY = padding.top + plotHeight
  const areaPath = buildAreaPath(points, baselineY)
  const lastPoint = points[points.length - 1]
  const guideRows = variant === 'expanded' ? [0.25, 0.5, 0.75] : []
  return (
    <div className={cn('lab-quest-curve', variant === 'expanded' && 'is-expanded', className)}>
      <svg
        className="lab-quest-curve__svg"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        aria-hidden
      >
        <defs>
          <linearGradient id={`lab-quest-curve-line-${chartId}`} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#66c6bd" />
            <stop offset="100%" stopColor="#4e87d2" />
          </linearGradient>
          <linearGradient id={`lab-quest-curve-fill-${chartId}`} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="rgba(84, 187, 177, 0.35)" />
            <stop offset="100%" stopColor="rgba(84, 187, 177, 0.02)" />
          </linearGradient>
        </defs>
        {guideRows.map((ratio) => {
          const y = padding.top + plotHeight * ratio
          return (
            <line
              key={`${ratio}`}
              x1={padding.left}
              y1={y}
              x2={width - padding.right}
              y2={y}
              className="lab-quest-curve__guide"
            />
          )
        })}
        {areaPath ? (
          <path
            d={areaPath}
            className="lab-quest-curve__area"
            fill={`url(#lab-quest-curve-fill-${chartId})`}
          />
        ) : null}
        {linePath ? (
          <path
            d={linePath}
            className="lab-quest-curve__line"
            stroke={`url(#lab-quest-curve-line-${chartId})`}
          />
        ) : null}
        {lastPoint ? (
          <circle
            className="lab-quest-curve__dot"
            cx={toFixedPoint(lastPoint.x)}
            cy={toFixedPoint(lastPoint.y)}
            r={variant === 'expanded' ? 3.5 : 2.4}
          />
        ) : null}
      </svg>
    </div>
  )
}

const QuestGraphNode = ({ data }: NodeProps) => {
  const { t } = useI18n('lab')
  const nodeData = data as QuestNodeData
  const isMetricMode = nodeData.displayMode === 'metric' && !nodeData.isEvent
  const positive =
    nodeData.metricTone === 'good' ||
    isPositiveDeltaLabel(nodeData.deltaLabel) ||
    ['good', 'support', 'go'].includes(String(nodeData.verdict || '').toLowerCase())
  const compactSummary =
    nodeData.ideaTitle ||
    nodeData.foundationLabel ||
    nodeData.nowDoing ||
    nodeData.summary ||
    nodeData.decisionReason ||
    nodeData.evidenceStatus ||
    nodeData.status ||
    null
  const compactMeta = [
    nodeData.branchNo ? `#${nodeData.branchNo}` : null,
    isMetricMode ? nodeData.metricDeltaLabel : nodeData.deltaLabel,
    !isMetricMode ? nodeData.metric : null,
    isMetricMode && nodeData.metricDirection
      ? nodeData.metricDirection === 'lower'
        ? t('quest_curve_direction_lower', undefined, 'lower is better')
        : t('quest_curve_direction_higher', undefined, 'higher is better')
      : null,
    nodeData.branchClass ? formatStateLabel(nodeData.branchClass) : null,
    nodeData.runtimeState ? formatStateLabel(nodeData.runtimeState) : null,
    nodeData.proofState && nodeData.proofState !== 'not_applicable'
      ? `Proof ${formatStateLabel(nodeData.proofState)}`
      : null,
  ].filter(Boolean)
  const semanticLabel = nodeData.decisionType
    ? formatStateLabel(nodeData.decisionType)
    : nodeData.isEvent
      ? t('quest_semantic_node_event_label', undefined, 'Event / stage marker')
      : nodeData.isPlaceholder
        ? t('quest_semantic_node_placeholder_label', undefined, 'Next step placeholder')
      : nodeData.isRoot
        ? t('quest_hover_badge_baseline', undefined, 'Baseline')
        : t('quest_semantic_node_branch_label', undefined, 'Branch / worktree route')
  const memoryPreview = nodeData.memorySummary ? truncateGraphText(nodeData.memorySummary, 96) : null
  const showMemoryHint = !nodeData.isEvent && Boolean(nodeData.memoryLabel || memoryPreview)
  return (
    <div
      data-onboarding-id={
        nodeData.isHead && !nodeData.isRoot
          ? 'quest-canvas-focus-node'
          : nodeData.isRoot
            ? 'quest-canvas-first-node'
            : undefined
      }
      className={cn(
        'lab-quest-graph-node',
        nodeData.isRoot && 'is-root',
        nodeData.isHead && 'is-head',
        nodeData.isSelected && 'is-selected',
        nodeData.isCurrentPath && 'is-current-path',
        nodeData.isCurrentWorkspace && 'is-current-workspace',
        nodeData.isEvent && 'is-event',
        nodeData.isPlaceholder && 'is-placeholder',
        nodeData.baselineGate === 'waived' && 'is-waived',
        positive && 'is-positive',
        nodeData.decisionType && 'is-decision',
        nodeData.decisionType ? `decision-${nodeData.decisionType}` : null
      )}
      title={compactSummary ? truncateGraphText(compactSummary, 180) : nodeData.label}
    >
      <Handle type="target" position={FlowPosition.Left} className="lab-flow-handle" />
      <Handle type="source" position={FlowPosition.Right} className="lab-flow-handle" />
      <div className="lab-quest-graph-node__eyebrow">
        <span className="lab-quest-graph-node__kind">{semanticLabel}</span>
        {nodeData.isCurrentWorkspace ? (
          <span className="lab-quest-graph-node__location is-current">
            {t('quest_current_workspace_badge', undefined, 'CURRENT')}
          </span>
        ) : null}
        {nodeData.verdict ? (
          <span className={cn('lab-quest-graph-node__verdict', `is-${nodeData.verdict}`)}>
            {nodeData.verdict}
          </span>
        ) : null}
      </div>
      <div className="lab-quest-graph-node__title">
        {nodeData.label}
      </div>
      {nodeData.subtitle ? (
        <div className="lab-quest-graph-node__subtitle">{nodeData.subtitle}</div>
      ) : null}
      {nodeData.parentBranch || nodeData.foundationLabel ? (
        <div className="lab-quest-graph-node__subtitle">
          {nodeData.foundationLabel || nodeData.parentBranch}
        </div>
      ) : null}
      {nodeData.decisionTarget ? (
        <div className="lab-quest-graph-node__decision-target">{nodeData.decisionTarget}</div>
      ) : null}
      <div className="lab-quest-graph-node__meta">
        {positive ? (
          <span className="lab-quest-graph-node__signal">
            {t('quest_hover_badge_promising', undefined, 'Promising')}
          </span>
        ) : null}
        {compactMeta.slice(0, 3).map((item) => (
          <span key={String(item)} className={String(item).startsWith('+') ? 'lab-quest-graph-node__delta' : undefined}>
            {item}
          </span>
        ))}
      </div>
      {isMetricMode ? (
        <div
          className={cn(
            'lab-quest-graph-node__metric-block',
            nodeData.metricTone === 'good' && 'is-good',
            nodeData.metricTone === 'bad' && 'is-bad'
          )}
        >
          <div className="lab-quest-graph-node__metric-label">
            {nodeData.metricLabel || t('quest_curve_metric_label', undefined, 'Focus metric')}
          </div>
          <div className="lab-quest-graph-node__metric-value">
            {nodeData.metricValueLabel || nodeData.metricEmptyReason || t('quest_metric_empty', undefined, 'No metric available')}
          </div>
          {nodeData.metricDeltaLabel ? (
            <div className="lab-quest-graph-node__metric-delta">{nodeData.metricDeltaLabel}</div>
          ) : nodeData.metricEmptyReason && nodeData.metricValueLabel ? (
            <div className="lab-quest-graph-node__metric-delta">{nodeData.metricEmptyReason}</div>
          ) : null}
        </div>
      ) : compactSummary ? (
        <div className="lab-quest-graph-node__summary">{truncateGraphText(compactSummary, 88)}</div>
      ) : null}
      {showMemoryHint ? (
        <div
          className="lab-quest-graph-node__memory"
          title={nodeData.memorySummary || nodeData.memoryLabel || undefined}
        >
          <div className="lab-quest-graph-node__memory-header">
            <span className="lab-quest-graph-node__memory-dot" />
            <span className="lab-quest-graph-node__memory-label">
              {nodeData.memoryLabel || t('quest_hover_line_memory', undefined, 'Memory')}
            </span>
          </div>
          {memoryPreview ? (
            <div className="lab-quest-graph-node__memory-summary">{memoryPreview}</div>
          ) : null}
        </div>
      ) : null}
      {nodeData.trend && !nodeData.isEvent ? (
        <MetricCurveChart values={nodeData.trend} className="lab-quest-sparkline" />
      ) : null}
    </div>
  )
}

const AgentGraphNode = ({ data }: NodeProps) => {
  const nodeData = data as AgentNodeData
  return (
    <div className="lab-quest-agent-node">
      <Handle type="target" position={FlowPosition.Left} className="lab-flow-handle" />
      <Handle type="source" position={FlowPosition.Right} className="lab-flow-handle" />
      <div className="lab-quest-agent-node__title">{nodeData.label}</div>
      {nodeData.subtitle ? (
        <div className="lab-quest-agent-node__meta">{nodeData.subtitle}</div>
      ) : null}
      {nodeData.status ? (
        <div className="lab-quest-agent-node__status">{nodeData.status}</div>
      ) : null}
    </div>
  )
}

const nodeTypes: NodeTypes = {
  questNode: QuestGraphNode,
  agentNode: AgentGraphNode,
}

const GraphHoverCard = ({ card }: { card: GraphHoverCardState | null }) => {
  if (!card) return null
  return (
    <div
      className={cn(
        'lab-quest-hover-card',
        card.tone ? `is-${card.tone}` : null
      )}
      style={{ left: card.x, top: card.y }}
      role="tooltip"
      aria-hidden={!card}
    >
      <div className="lab-quest-hover-card__header">
        <div className="lab-quest-hover-card__title">{card.title}</div>
        {card.badge ? <div className="lab-quest-hover-card__badge">{card.badge}</div> : null}
      </div>
      {card.subtitle ? <div className="lab-quest-hover-card__subtitle">{card.subtitle}</div> : null}
      <div className="lab-quest-hover-card__lines">
        {card.lines.map((line) => (
          <div key={`${line.label}-${line.value}`} className="lab-quest-hover-card__line">
            <span>{line.label}</span>
            <span>{line.value}</span>
          </div>
        ))}
      </div>
      {card.footer ? <div className="lab-quest-hover-card__footer">{card.footer}</div> : null}
    </div>
  )
}

const buildDagreLayout = (
  nodes: LabQuestGraphNode[],
  edges: LabQuestGraphEdge[],
  options?: {
    rankdir?: 'LR' | 'TB'
    nodesep?: number
    ranksep?: number
    getNodeSize?: (node: LabQuestGraphNode) => DagreNodeSize
  }
) => {
  const graph = new dagre.graphlib.Graph()
  graph.setDefaultEdgeLabel(() => ({}))
  graph.setGraph({
    rankdir: options?.rankdir ?? 'LR',
    nodesep: options?.nodesep ?? 70,
    ranksep: options?.ranksep ?? 120,
  })
  const nodeSizes = new Map<string, DagreNodeSize>()
  nodes.forEach((node) => {
    const size = options?.getNodeSize?.(node) ?? DEFAULT_DAGRE_NODE_SIZE
    nodeSizes.set(node.node_id, size)
    graph.setNode(node.node_id, size)
  })
  edges.forEach((edge) => {
    graph.setEdge(edge.source, edge.target)
  })
  dagre.layout(graph)
  const positions: Record<string, Position> = {}
  nodes.forEach((node) => {
    const layoutNode = graph.node(node.node_id)
    if (!layoutNode) {
      positions[node.node_id] = { x: 0, y: 0 }
      return
    }
    const size = nodeSizes.get(node.node_id) ?? DEFAULT_DAGRE_NODE_SIZE
    positions[node.node_id] = {
      x: layoutNode.x - size.width / 2,
      y: layoutNode.y - size.height / 2,
    }
  })
  return positions
}

const LAYOUT_TEXT_COLLATOR = new Intl.Collator('en', { numeric: true, sensitivity: 'base' })

const compareLayoutText = (left?: string | null, right?: string | null) =>
  LAYOUT_TEXT_COLLATOR.compare(String(left || ''), String(right || ''))

const compareLayoutTime = (left?: string | null, right?: string | null) => {
  const leftTime = parseEventTime(left)
  const rightTime = parseEventTime(right)
  if (leftTime && rightTime && leftTime !== rightTime) return leftTime - rightTime
  if (leftTime && !rightTime) return -1
  if (!leftTime && rightTime) return 1
  return 0
}

const resolveNodeKindRank = (node: LabQuestGraphNode) => {
  if (node.node_kind === 'baseline_root') return 0
  if (node.node_kind === 'placeholder' || node.placeholder) return 9
  return 1
}

const resolveBranchClassRank = (node: LabQuestGraphNode) => {
  const branchClass = String(node.branch_class || '').toLowerCase()
  if (branchClass === 'main') return 0
  if (branchClass === 'idea') return 1
  if (branchClass === 'analysis') return 2
  if (branchClass === 'paper') return 3
  return 4
}

const resolveStageLayoutRank = (node: LabQuestGraphNode) => {
  const stageKey = String(node.stage_key || '').toLowerCase()
  const index = STAGE_ORDER.indexOf(stageKey as BranchStage)
  return index >= 0 ? index : STAGE_ORDER.length
}

const compareLayoutNodes = (
  left: LabQuestGraphNode,
  right: LabQuestGraphNode,
  viewMode: 'branch' | 'event' | 'stage'
) => {
  if (viewMode === 'event') {
    return (
      compareLayoutTime(left.created_at, right.created_at) ||
      resolveStageLayoutRank(left) - resolveStageLayoutRank(right) ||
      compareLayoutText(left.branch_name, right.branch_name) ||
      compareLayoutText(left.node_id, right.node_id)
    )
  }

  if (viewMode === 'stage') {
    return (
      resolveStageLayoutRank(left) - resolveStageLayoutRank(right) ||
      compareLayoutTime(left.created_at, right.created_at) ||
      compareLayoutText(left.stage_key, right.stage_key) ||
      compareLayoutText(left.node_id, right.node_id)
    )
  }

  return (
    resolveNodeKindRank(left) - resolveNodeKindRank(right) ||
    resolveBranchClassRank(left) - resolveBranchClassRank(right) ||
    compareLayoutTime(left.created_at, right.created_at) ||
    compareLayoutText(left.branch_no, right.branch_no) ||
    compareLayoutText(left.branch_name, right.branch_name) ||
    compareLayoutText(left.node_id, right.node_id)
  )
}

const sortNodesForLayout = (
  nodes: LabQuestGraphNode[],
  viewMode: 'branch' | 'event' | 'stage'
) => [...nodes].sort((left, right) => compareLayoutNodes(left, right, viewMode))

const sortEdgesForLayout = (
  edges: LabQuestGraphEdge[],
  orderedNodes: LabQuestGraphNode[]
) => {
  const nodeOrder = new Map(orderedNodes.map((node, index) => [node.node_id, index]))
  return [...edges].sort((left, right) => {
    const leftSource = nodeOrder.get(left.source) ?? Number.MAX_SAFE_INTEGER
    const rightSource = nodeOrder.get(right.source) ?? Number.MAX_SAFE_INTEGER
    if (leftSource !== rightSource) return leftSource - rightSource
    const leftTarget = nodeOrder.get(left.target) ?? Number.MAX_SAFE_INTEGER
    const rightTarget = nodeOrder.get(right.target) ?? Number.MAX_SAFE_INTEGER
    if (leftTarget !== rightTarget) return leftTarget - rightTarget
    return (
      compareLayoutText(left.edge_type, right.edge_type) ||
      compareLayoutText(left.edge_id, right.edge_id) ||
      compareLayoutText(left.source, right.source) ||
      compareLayoutText(left.target, right.target)
    )
  })
}

const buildBranchLayout = (
  nodes: LabQuestGraphNode[],
  edges: LabQuestGraphEdge[],
  options: {
    nodeDisplayMode: 'summary' | 'metric'
    curveMetric: string | null
    curveMode: 'sota' | 'full'
    branchInsights: Map<string, BranchInsight>
    memoryByBranch: Map<string, BranchMemorySnapshot>
  }
) => {
  if (nodes.length === 0) return {}
  return buildDagreLayout(nodes, edges, {
    rankdir: 'LR',
    nodesep: nodes.length > 60 ? 44 : nodes.length > 24 ? 56 : 78,
    ranksep: nodes.length > 100 ? 96 : nodes.length > 60 ? 112 : 136,
    getNodeSize: (node) => estimateBranchNodeSize(node, options),
  })
}

const buildEventLayout = (nodes: LabQuestGraphNode[], _edges: LabQuestGraphEdge[]) => {
  if (nodes.length === 0) return {}
  const positions: Record<string, Position> = {}
  const laneByKey = new Map<string, number>()
  nodes.forEach((node, index) => {
    const laneKey = node.branch_name || node.stage_key || 'default'
    if (!laneByKey.has(laneKey)) {
      laneByKey.set(laneKey, laneByKey.size)
    }
    positions[node.node_id] = {
      x: index * (DAGRE_NODE_WIDTH + 92),
      y: (laneByKey.get(laneKey) ?? 0) * (DAGRE_EVENT_NODE_HEIGHT + 76),
    }
  })
  return positions
}

const buildStageLayout = (nodes: LabQuestGraphNode[], edges: LabQuestGraphEdge[]) =>
  buildDagreLayout(nodes, edges, {
    rankdir: 'LR',
    nodesep: 120,
    ranksep: 160,
    getNodeSize: () => ({ width: DAGRE_NODE_WIDTH, height: DAGRE_STAGE_NODE_HEIGHT }),
  })

function resolveLayoutMap(layoutJson: QuestLayoutJson | null, viewMode: 'branch' | 'event' | 'stage') {
  if (!layoutJson) return {}
  const candidate = layoutJson[viewMode]
  if (candidate && typeof candidate === 'object') {
    return candidate as QuestLayoutMap
  }
  return {}
}

function normalizePathFilterMode(value: unknown): PathFilterMode {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'current' || normalized === 'selected') {
    return normalized
  }
  return 'all'
}

function resolveCanvasPreferences(layoutJson: QuestLayoutJson | null): LabCanvasPreferences {
  if (!layoutJson || typeof layoutJson.preferences !== 'object' || !layoutJson.preferences) {
    return {}
  }
  const raw = layoutJson.preferences
  const curveMode = raw.curveMode === 'full' || raw.curveMode === 'sota' ? raw.curveMode : null
  const nodeDisplayMode =
    raw.nodeDisplayMode === 'metric' || raw.nodeDisplayMode === 'summary' ? raw.nodeDisplayMode : null
  return {
    curveMetric: typeof raw.curveMetric === 'string' && raw.curveMetric.trim() ? raw.curveMetric.trim() : null,
    curveMode,
    nodeDisplayMode,
    showAnalysis: typeof raw.showAnalysis === 'boolean' ? raw.showAnalysis : null,
    pathFilterMode: normalizePathFilterMode(raw.pathFilterMode),
  }
}

function buildCanvasPreferences(preferences: {
  curveMetric: string
  curveMode: 'sota' | 'full'
  nodeDisplayMode: 'summary' | 'metric'
  showAnalysis: boolean
  pathFilterMode: PathFilterMode
}): LabCanvasPreferences {
  return {
    curveMetric: preferences.curveMetric || null,
    curveMode: preferences.curveMode,
    nodeDisplayMode: preferences.nodeDisplayMode,
    showAnalysis: preferences.showAnalysis,
    pathFilterMode: preferences.pathFilterMode,
  }
}

function resolveWorkflowBranchStage(
  workflowState: LabQuestGraphNode['workflow_state'],
  fallbackStage: BranchStage
): BranchStage {
  if (!workflowState || typeof workflowState !== 'object') return fallbackStage
  const writingState = String(workflowState.writing_state || '').trim().toLowerCase()
  if (writingState === 'completed') return 'finalize'
  if (writingState === 'active') return 'write'
  if (writingState === 'blocked_by_analysis') return 'analysis-campaign'
  const analysisState = String(workflowState.analysis_state || '').trim().toLowerCase()
  if (analysisState === 'pending' || analysisState === 'active' || analysisState === 'completed') {
    return 'analysis-campaign'
  }
  return fallbackStage
}

function resolveWorkflowEvidenceStatus(workflowState: LabQuestGraphNode['workflow_state']): string | null {
  if (!workflowState || typeof workflowState !== 'object') return null
  const reason = String(workflowState.status_reason || '').trim()
  if (reason) return reason
  const total =
    typeof workflowState.total_slices === 'number' && Number.isFinite(workflowState.total_slices)
      ? workflowState.total_slices
      : null
  const completed =
    typeof workflowState.completed_slices === 'number' && Number.isFinite(workflowState.completed_slices)
      ? workflowState.completed_slices
      : null
  const nextPending = String(workflowState.next_pending_slice_id || '').trim()
  const writingState = String(workflowState.writing_state || '').trim().toLowerCase()
  if (writingState === 'blocked_by_analysis') {
    return total != null
      ? `Analysis ${completed ?? 0}/${total} done${nextPending ? ` · next: ${nextPending}` : ''}`
      : 'Writing blocked by analysis.'
  }
  if (writingState === 'active') return 'Writing workspace active.'
  if (writingState === 'ready') return 'Ready for writing.'
  if (writingState === 'completed') return 'Writing finalized.'
  const analysisState = String(workflowState.analysis_state || '').trim().toLowerCase()
  if (analysisState === 'active') {
    return total != null ? `Analysis ${completed ?? 0}/${total} done` : 'Analysis active.'
  }
  if (analysisState === 'completed') return 'Analysis complete.'
  if (analysisState === 'pending') return 'Analysis pending.'
  return null
}

function buildBranchLineageSet(nodes: LabQuestGraphNode[], branchName?: string | null): Set<string> {
  const lineage = new Set<string>()
  const target = String(branchName || '').trim()
  if (!target) return lineage
  const nodeByBranch = new Map<string, LabQuestGraphNode>()
  nodes.forEach((node) => {
    if (node.node_kind === 'baseline_root' || node.node_kind === 'placeholder') return
    if (node.branch_name && !nodeByBranch.has(node.branch_name)) {
      nodeByBranch.set(node.branch_name, node)
    }
  })
  let current: string | null = target
  const seen = new Set<string>()
  while (current && !seen.has(current)) {
    seen.add(current)
    lineage.add(current)
    const parentBranch = String(nodeByBranch.get(current)?.parent_branch || '').trim() || null
    current = parentBranch
  }
  return lineage
}

function filterNodesByBranchLineage(nodes: LabQuestGraphNode[], lineage: Set<string>): LabQuestGraphNode[] {
  if (!lineage.size) return nodes
  const visibleNodeIds = new Set(
    nodes
      .filter((node) => node.node_kind !== 'baseline_root' && node.node_kind !== 'placeholder')
      .filter((node) => node.branch_name && lineage.has(node.branch_name))
      .map((node) => node.node_id)
  )
  return nodes.filter((node) => {
    if (node.node_kind === 'baseline_root') return true
    if (node.node_kind === 'placeholder') {
      return !node.parent_branch || visibleNodeIds.has(node.parent_branch)
    }
    return Boolean(node.branch_name && lineage.has(node.branch_name))
  })
}

type FloatingPanelState = {
  x: number
  y: number
  collapsed: boolean
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

const truncateGraphText = (value?: string | null, maxLength = 92) => {
  const text = String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
  if (!text) return ''
  if (text.length <= maxLength) return text
  return `${text.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`
}

const isPositiveDeltaLabel = (value?: string | null) => {
  const text = String(value || '').trim()
  return text.startsWith('+')
}

type Rect = { x: number; y: number; width: number; height: number }

const rectsOverlap = (a: Rect, b: Rect) => {
  return !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  )
}

const POSITION_EPS = 0.5

const sanitizePosition = (pos: Position, fallback: Position) => {
  const x = Number.isFinite(pos.x) ? pos.x : fallback.x
  const y = Number.isFinite(pos.y) ? pos.y : fallback.y
  return { x, y }
}

const isPositionDifferent = (a: Position, b: Position) => {
  return Math.abs(a.x - b.x) > POSITION_EPS || Math.abs(a.y - b.y) > POSITION_EPS
}

const resolveOrbPosition = (current: Position, bounds: DOMRect, blockers: Rect[]) => {
  const leftX = FLOATING_PANEL_MARGIN
  const rightX = Math.max(FLOATING_PANEL_MARGIN, bounds.width - ORB_SIZE - FLOATING_PANEL_MARGIN)
  const topY = FLOATING_PANEL_MARGIN
  const bottomY = Math.max(FLOATING_PANEL_MARGIN, bounds.height - ORB_SIZE - FLOATING_PANEL_MARGIN)

  const clampedX = clamp(current.x, leftX, rightX)
  const clampedY = clamp(current.y, topY, bottomY)

  const distances = [
    { edge: 'left', dist: Math.abs(clampedX - leftX) },
    { edge: 'right', dist: Math.abs(clampedX - rightX) },
    { edge: 'top', dist: Math.abs(clampedY - topY) },
    { edge: 'bottom', dist: Math.abs(clampedY - bottomY) },
  ].sort((a, b) => a.dist - b.dist)
  const primary = distances[0]?.edge ?? 'left'

  const candidates: Position[] = []
  const pushCandidate = (x: number, y: number) => {
    candidates.push({
      x: clamp(x, leftX, rightX),
      y: clamp(y, topY, bottomY),
    })
  }

  if (primary === 'left' || primary === 'right') {
    const edgeX = primary === 'left' ? leftX : rightX
    pushCandidate(edgeX, clampedY)
    pushCandidate(edgeX, clampedY + ORB_STEP)
    pushCandidate(edgeX, clampedY - ORB_STEP)
    pushCandidate(primary === 'left' ? rightX : leftX, clampedY)
  } else {
    const edgeY = primary === 'top' ? topY : bottomY
    pushCandidate(clampedX, edgeY)
    pushCandidate(clampedX + ORB_STEP, edgeY)
    pushCandidate(clampedX - ORB_STEP, edgeY)
    pushCandidate(clampedX, primary === 'top' ? bottomY : topY)
  }

  pushCandidate(leftX, topY)
  pushCandidate(rightX, topY)
  pushCandidate(leftX, bottomY)
  pushCandidate(rightX, bottomY)

  const seen = new Set<string>()
  const uniqueCandidates = candidates.filter((candidate) => {
    const key = `${candidate.x}:${candidate.y}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })

  for (const candidate of uniqueCandidates) {
    const orbRect = { x: candidate.x, y: candidate.y, width: ORB_SIZE, height: ORB_SIZE }
    if (!blockers.some((block) => rectsOverlap(orbRect, block))) {
      return candidate
    }
  }

  return uniqueCandidates[0] ?? { x: leftX, y: topY }
}

const resolvePanelSize = (
  kind: 'branches' | 'events' | 'papers',
  collapsed: boolean,
  bounds: DOMRect
) => {
  if (collapsed) {
    return { width: ORB_SIZE, height: ORB_SIZE }
  }
  let baseWidth = BRANCH_PANEL_WIDTH
  let baseHeight = BRANCH_PANEL_HEIGHT
  if (kind === 'events') {
    baseWidth = EVENTS_PANEL_WIDTH
    baseHeight = EVENTS_PANEL_HEIGHT
  }
  if (kind === 'papers') {
    baseWidth = PAPERS_PANEL_WIDTH
    baseHeight = PAPERS_PANEL_HEIGHT
  }
  return {
    width: Math.min(baseWidth, Math.max(ORB_SIZE, bounds.width - 24)),
    height: Math.min(baseHeight, Math.max(ORB_SIZE, bounds.height - 24)),
  }
}

const shallowArrayEqual = (a?: unknown[] | null, b?: unknown[] | null) => {
  if (a === b) return true
  if (!a || !b) return false
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false
  }
  return true
}

type DagreNodeSize = {
  width: number
  height: number
}

const DEFAULT_DAGRE_NODE_SIZE: DagreNodeSize = {
  width: DAGRE_NODE_WIDTH,
  height: DAGRE_NODE_HEIGHT,
}

const estimateBranchNodeSize = (
  node: LabQuestGraphNode,
  options: {
    nodeDisplayMode: 'summary' | 'metric'
    curveMetric: string | null
    curveMode: 'sota' | 'full'
    branchInsights: Map<string, BranchInsight>
    memoryByBranch: Map<string, BranchMemorySnapshot>
  }
): DagreNodeSize => {
  const isPlaceholder = Boolean(node.placeholder || node.node_kind === 'placeholder')
  const isBaselineRoot = node.node_kind === 'baseline_root'
  const branchInsight = node.branch_name ? options.branchInsights.get(node.branch_name) ?? null : null
  const branchMemory = node.branch_name ? options.memoryByBranch.get(node.branch_name) ?? null : null
  const fallbackSummary =
    clampCanvasText(node.node_summary?.last_error, 96) ||
    clampCanvasText(node.node_summary?.last_reply, 96) ||
    clampCanvasText(node.node_summary?.last_event_type, 96) ||
    null
  let height = DAGRE_BRANCH_NODE_BASE_HEIGHT
  const hasPrimarySubtitle = isBaselineRoot
    ? Boolean(node.status)
    : Boolean(node.idea_title || branchInsight?.stageLabel || node.idea_id)
  if (hasPrimarySubtitle) {
    height += DAGRE_BRANCH_NODE_TEXT_ROW_HEIGHT
  }
  if (node.parent_branch || node.foundation_label) {
    height += DAGRE_BRANCH_NODE_TEXT_ROW_HEIGHT
  }
  if (options.nodeDisplayMode === 'metric') {
    height += DAGRE_BRANCH_NODE_METRIC_HEIGHT
  } else if (branchInsight?.nowDoing || node.idea_problem || fallbackSummary) {
    height += DAGRE_BRANCH_NODE_SUMMARY_HEIGHT
  }
  if (!isPlaceholder && !isBaselineRoot && branchMemory) {
    height += DAGRE_BRANCH_NODE_MEMORY_HEIGHT
  }
  if (
    (extractTrend(node, {
      metricKey: options.curveMetric || null,
      mode: options.curveMode,
    }) || []).length > 0
  ) {
    height += DAGRE_BRANCH_NODE_TREND_HEIGHT
  }
  if (isBaselineRoot) {
    height += 10
  }
  return {
    width: DAGRE_NODE_WIDTH,
    height: Math.max(DAGRE_BRANCH_NODE_MIN_HEIGHT, height + DAGRE_LAYOUT_BUFFER_HEIGHT),
  }
}

const resolveNodeMeasuredSize = (
  node: QuestFlowNode,
  getMeasuredSize?: (id: string) => DagreNodeSize | null
): DagreNodeSize => {
  const measured = getMeasuredSize?.(node.id)
  return {
    width: measured?.width ?? node.measured?.width ?? node.width ?? DAGRE_NODE_WIDTH,
    height: measured?.height ?? node.measured?.height ?? node.height ?? DAGRE_NODE_HEIGHT,
  }
}

const resolveNodeSpacingCollisions = (
  nodes: QuestFlowNode[],
  options: {
    viewMode: 'branch' | 'event' | 'stage'
    getMeasuredSize?: (id: string) => DagreNodeSize | null
    gapX?: number
    gapY?: number
  }
): QuestFlowNode[] => {
  if (nodes.length <= 1) return nodes

  const gapX = options.gapX ?? AUTO_LAYOUT_GAP_X
  const gapY = options.gapY ?? AUTO_LAYOUT_GAP_Y
  const trackedNodes = nodes.filter((node) => !isAgentNode(node))
  if (trackedNodes.length <= 1) return nodes

  const positions = new Map<string, Position>(
    nodes.map((node) => [node.id, { x: node.position.x, y: node.position.y }])
  )
  const sizeById = new Map<string, DagreNodeSize>(
    trackedNodes.map((node) => [node.id, resolveNodeMeasuredSize(node, options.getMeasuredSize)])
  )

  let moved = false
  for (let pass = 0; pass < AUTO_LAYOUT_MAX_PASSES; pass += 1) {
    let passMoved = false
    const ordered = [...trackedNodes].sort((left, right) => {
      const leftPos = positions.get(left.id) ?? left.position
      const rightPos = positions.get(right.id) ?? right.position
      if (options.viewMode === 'event') {
        return leftPos.y - rightPos.y || leftPos.x - rightPos.x
      }
      return leftPos.x - rightPos.x || leftPos.y - rightPos.y
    })

    for (let index = 0; index < ordered.length; index += 1) {
      const current = ordered[index]
      const currentPos = positions.get(current.id) ?? current.position
      const currentSize = sizeById.get(current.id) ?? resolveNodeMeasuredSize(current, options.getMeasuredSize)
      for (let nextIndex = index + 1; nextIndex < ordered.length; nextIndex += 1) {
        const target = ordered[nextIndex]
        const targetPos = positions.get(target.id) ?? target.position
        const targetSize = sizeById.get(target.id) ?? resolveNodeMeasuredSize(target, options.getMeasuredSize)

        const overlapsHorizontally =
          currentPos.x < targetPos.x + targetSize.width + gapX &&
          targetPos.x < currentPos.x + currentSize.width + gapX
        const overlapsVertically =
          currentPos.y < targetPos.y + targetSize.height + gapY &&
          targetPos.y < currentPos.y + currentSize.height + gapY

        if (!overlapsHorizontally || !overlapsVertically) {
          continue
        }

        const verticalShift = currentPos.y + currentSize.height + gapY - targetPos.y
        const horizontalShift = currentPos.x + currentSize.width + gapX - targetPos.x
        const preferVertical = options.viewMode !== 'event'
        const verticalCost = verticalShift * (preferVertical ? 0.88 : 1.12)
        const horizontalCost = horizontalShift * (preferVertical ? 1.12 : 0.88)
        const targetPosition = positions.get(target.id) ?? { x: target.position.x, y: target.position.y }

        if (verticalCost <= horizontalCost) {
          targetPosition.y += Math.max(0, verticalShift)
        } else {
          targetPosition.x += Math.max(0, horizontalShift)
        }

        positions.set(target.id, targetPosition)
        passMoved = true
        moved = true
      }
    }

    if (!passMoved) {
      break
    }
  }

  if (!moved) return nodes

  const resolved = nodes.map((node) => {
    const nextPosition = positions.get(node.id)
    if (!nextPosition) return node
    if (
      Math.abs(nextPosition.x - node.position.x) < 0.5 &&
      Math.abs(nextPosition.y - node.position.y) < 0.5
    ) {
      return node
    }
    return {
      ...node,
      position: nextPosition,
    }
  })

  return areNodesEquivalent(nodes, resolved) ? nodes : resolved
}

const isAgentNode = (node?: QuestFlowNode | null) => {
  if (!node) return false
  return node.type === 'agentNode' || Boolean((node.data as AgentNodeData | QuestNodeData)?.isAgent)
}

const areNodesEquivalent = (prev: QuestFlowNode[], next: QuestFlowNode[]) => {
  if (prev === next) return true
  if (prev.length !== next.length) return false
  for (let i = 0; i < next.length; i += 1) {
    const left = prev[i]
    const right = next[i]
    if (!left || !right) return false
    if (left.id !== right.id) return false
    if (left.type !== right.type) return false
    if (left.position?.x !== right.position?.x || left.position?.y !== right.position?.y) return false
    if (Boolean(left.draggable) !== Boolean(right.draggable)) return false

    if (isAgentNode(left) || isAgentNode(right)) {
      if (!isAgentNode(left) || !isAgentNode(right)) return false
      const a = left.data as AgentNodeData
      const b = right.data as AgentNodeData
      if (!a || !b) return false
      if (a.label !== b.label) return false
      if ((a.subtitle ?? null) !== (b.subtitle ?? null)) return false
      if ((a.status ?? null) !== (b.status ?? null)) return false
      if ((a.branchName ?? null) !== (b.branchName ?? null)) return false
      if ((a.agentInstanceId ?? null) !== (b.agentInstanceId ?? null)) return false
      continue
    }
    const a = left.data as QuestNodeData
    const b = right.data as QuestNodeData
    if (!a || !b) return false
    if (a.label !== b.label) return false
    if ((a.subtitle ?? null) !== (b.subtitle ?? null)) return false
    if ((a.status ?? null) !== (b.status ?? null)) return false
    if ((a.metric ?? null) !== (b.metric ?? null)) return false
    if ((a.verdict ?? null) !== (b.verdict ?? null)) return false
    if ((a.summary ?? null) !== (b.summary ?? null)) return false
    if ((a.deltaLabel ?? null) !== (b.deltaLabel ?? null)) return false
    if ((a.stageLabel ?? null) !== (b.stageLabel ?? null)) return false
    if ((a.nowDoing ?? null) !== (b.nowDoing ?? null)) return false
    if ((a.decisionReason ?? null) !== (b.decisionReason ?? null)) return false
    if ((a.evidenceStatus ?? null) !== (b.evidenceStatus ?? null)) return false
    if ((a.branchClass ?? null) !== (b.branchClass ?? null)) return false
    if ((a.nodeKind ?? null) !== (b.nodeKind ?? null)) return false
    if ((a.compareBase ?? null) !== (b.compareBase ?? null)) return false
    if ((a.compareHead ?? null) !== (b.compareHead ?? null)) return false
    if ((a.worktreeRelPath ?? null) !== (b.worktreeRelPath ?? null)) return false
    if ((a.baselineGate ?? null) !== (b.baselineGate ?? null)) return false
    if ((a.baselineState ?? null) !== (b.baselineState ?? null)) return false
    if ((a.pushState ?? null) !== (b.pushState ?? null)) return false
    if ((a.writerState ?? null) !== (b.writerState ?? null)) return false
    if ((a.runtimeState ?? null) !== (b.runtimeState ?? null)) return false
    if ((a.protectedState ?? null) !== (b.protectedState ?? null)) return false
    if ((a.divergenceState ?? null) !== (b.divergenceState ?? null)) return false
    if ((a.reconcileState ?? null) !== (b.reconcileState ?? null)) return false
    if ((a.proofState ?? null) !== (b.proofState ?? null)) return false
    if ((a.submissionState ?? null) !== (b.submissionState ?? null)) return false
    if ((a.retireState ?? null) !== (b.retireState ?? null)) return false
    if ((a.claimEvidenceState ?? null) !== (b.claimEvidenceState ?? null)) return false
    if (Boolean(a.isHead) !== Boolean(b.isHead)) return false
    if (Boolean(a.isSelected) !== Boolean(b.isSelected)) return false
    if (Boolean(a.isEvent) !== Boolean(b.isEvent)) return false
    if (Boolean(a.isPlaceholder) !== Boolean(b.isPlaceholder)) return false
    if ((a.branchName ?? null) !== (b.branchName ?? null)) return false
    if ((a.decisionType ?? null) !== (b.decisionType ?? null)) return false
    if ((a.decisionTarget ?? null) !== (b.decisionTarget ?? null)) return false
    if (!shallowArrayEqual(a.trend as unknown[] | null, b.trend as unknown[] | null)) return false
    if (!shallowArrayEqual(a.scopePaths as unknown[] | null, b.scopePaths as unknown[] | null)) return false
  }
  return true
}

const areEdgesEquivalent = (prev: Edge[], next: Edge[]) => {
  if (prev === next) return true
  if (prev.length !== next.length) return false
  for (let i = 0; i < next.length; i += 1) {
    const left = prev[i]
    const right = next[i]
    if (!left || !right) return false
    if (left.id !== right.id) return false
    if (left.source !== right.source || left.target !== right.target) return false
    if ((left.type ?? null) !== (right.type ?? null)) return false
    const a = left.style as Record<string, unknown> | undefined
    const b = right.style as Record<string, unknown> | undefined
    const strokeA = a?.stroke ?? null
    const strokeB = b?.stroke ?? null
    const widthA = a?.strokeWidth ?? null
    const widthB = b?.strokeWidth ?? null
    const dashA = a?.strokeDasharray ?? null
    const dashB = b?.strokeDasharray ?? null
    if (strokeA !== strokeB || widthA !== widthB || dashA !== dashB) return false
  }
  return true
}

const GraphViewport = React.memo(function GraphViewport({
  nodes,
  edges,
  readOnly,
  onNodeClick,
  onNodeMouseEnter,
  onNodeMouseLeave,
  onEdgeClick,
  onEdgeMouseEnter,
  onEdgeMouseLeave,
  onNodeDragStop,
  onNodesChange,
  onEdgesChange,
  onViewportMoveStart,
  isLoading,
  isError,
  statusMessage,
  statusProgress,
  showStatusOverlay,
  hoverCard,
  toolbar,
  minimalChrome,
}: {
  nodes: Node<QuestFlowNodeData>[]
  edges: Edge[]
  readOnly?: boolean
  onNodeClick: (event: React.MouseEvent, node: Node<QuestFlowNodeData>) => void
  onNodeMouseEnter: (event: React.MouseEvent, node: Node<QuestFlowNodeData>) => void
  onNodeMouseLeave: (event: React.MouseEvent, node: Node<QuestFlowNodeData>) => void
  onEdgeClick: (event: React.MouseEvent, edge: Edge) => void
  onEdgeMouseEnter: (event: React.MouseEvent, edge: Edge) => void
  onEdgeMouseLeave: (event: React.MouseEvent, edge: Edge) => void
  onNodeDragStop: (event: React.MouseEvent, node: Node<QuestFlowNodeData>) => void
  onNodesChange: (changes: any) => void
  onEdgesChange: (changes: any) => void
  onViewportMoveStart?: () => void
  isLoading: boolean
  isError: boolean
  statusMessage?: string | null
  statusProgress?: { current: number; total: number; percent: number; step?: string | null } | null
  showStatusOverlay?: boolean
  hoverCard: GraphHoverCardState | null
  toolbar?: React.ReactNode
  minimalChrome?: boolean
}) {
  return (
    <div
      className={cn(
        'relative lab-quest-graph-shell lab-quest-graph-shell--full',
        minimalChrome && 'lab-quest-graph-shell--minimal'
      )}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        onNodeMouseEnter={onNodeMouseEnter}
        onNodeMouseLeave={onNodeMouseLeave}
        onEdgeClick={onEdgeClick}
        onEdgeMouseEnter={onEdgeMouseEnter}
        onEdgeMouseLeave={onEdgeMouseLeave}
        onNodeDragStop={onNodeDragStop}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onMoveStart={onViewportMoveStart}
        nodesDraggable={!readOnly}
        // Explicitly enable "infinite canvas" interactions (pan + wheel zoom).
        // We keep this explicit to avoid surprises if @xyflow/react defaults change.
        panOnDrag
        zoomOnScroll
        zoomOnPinch
        minZoom={0.15}
        maxZoom={3}
        translateExtent={[
          [-CANVAS_EXTENT, -CANVAS_EXTENT],
          [CANVAS_EXTENT, CANVAS_EXTENT],
        ]}
        // Avoid prop-driven fitView loops; we trigger one-time fit in the parent after nodes load.
        fitView={false}
      >
        <Background color="var(--lab-border)" gap={28} size={1} variant={'dots' as any} />
        {!minimalChrome ? <Controls showInteractive={!readOnly} /> : null}
        {!minimalChrome ? (
          <MiniMap zoomable pannable className="lab-quest-minimap" />
        ) : null}
      </ReactFlow>
      {toolbar ? <div className="lab-quest-graph-toolbar">{toolbar}</div> : null}
      {isLoading ? (
        <div className="lab-quest-graph-overlay" aria-label="Loading graph">
          <div className="lab-quest-graph-overlay-card">
            <div className="lab-quest-graph-overlay-title">Loading branch canvas…</div>
            <div className="lab-quest-graph-overlay-body">
              {statusMessage || 'Quest graph state is being rebuilt from durable branch and artifact records.'}
            </div>
            {statusProgress ? (
              <div className="mt-3">
                <div className="h-2 overflow-hidden rounded-full bg-black/[0.08] dark:bg-white/[0.08]">
                  <div
                    className="h-full rounded-full bg-[#b48d4f] transition-[width] duration-300 ease-out"
                    style={{ width: `${Math.max(0, statusProgress.percent)}%` }}
                  />
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                  {statusProgress.current}/{statusProgress.total}
                  {statusProgress.step ? ` · ${statusProgress.step}` : ''}
                </div>
              </div>
            ) : null}
            <div className="lab-quest-graph-overlay-skeletons" aria-hidden="true">
              <Skeleton className="h-3 w-40" />
              <Skeleton className="h-3 w-56" />
            </div>
          </div>
        </div>
      ) : null}
      {isError ? (
        <div className="lab-quest-graph-overlay" aria-label="Graph error">
          <div className="lab-quest-graph-overlay-card is-error">
            <div className="lab-quest-graph-overlay-title">Graph data unavailable.</div>
            <div className="lab-quest-graph-overlay-body">
              The branch canvas could not be reconstructed from the current quest state.
            </div>
          </div>
        </div>
      ) : null}
      {!isLoading && !isError && showStatusOverlay && statusMessage ? (
        <div className="pointer-events-none absolute left-4 bottom-4 z-20 max-w-[28rem] rounded-[18px] border border-black/[0.08] bg-white/[0.88] px-4 py-3 text-sm text-muted-foreground shadow-sm backdrop-blur dark:border-white/[0.10] dark:bg-[rgba(18,18,18,0.82)]">
          <div>{statusMessage}</div>
          {statusProgress ? (
            <div className="mt-3">
              <div className="h-2 overflow-hidden rounded-full bg-black/[0.08] dark:bg-white/[0.08]">
                <div
                  className="h-full rounded-full bg-[#b48d4f] transition-[width] duration-300 ease-out"
                  style={{ width: `${Math.max(0, statusProgress.percent)}%` }}
                />
              </div>
              <div className="mt-2 text-[11px] text-muted-foreground">
                {statusProgress.current}/{statusProgress.total}
                {statusProgress.step ? ` · ${statusProgress.step}` : ''}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
      <GraphHoverCard card={hoverCard} />
    </div>
  )
})

function FloatingPanel({
  boundsRef,
  title,
  icon,
  state,
  zIndex,
  onChange,
  onActivate,
  className,
  children,
}: {
  boundsRef: React.RefObject<HTMLDivElement | null>
  title: string
  icon: React.ReactNode
  state: FloatingPanelState
  zIndex: number
  onChange: (next: FloatingPanelState) => void
  onActivate?: () => void
  className?: string
  children: React.ReactNode
}) {
  const rootRef = React.useRef<HTMLDivElement | HTMLButtonElement | null>(null)
  const dragRef = React.useRef<{
    pointerId: number
    startX: number
    startY: number
    originX: number
    originY: number
    moved: boolean
  } | null>(null)
  const cleanupRef = React.useRef<(() => void) | null>(null)
  const lastDragMovedRef = React.useRef(false)

  React.useEffect(() => {
    return () => {
      cleanupRef.current?.()
    }
  }, [])

  const startDrag = React.useCallback(
    (event: React.PointerEvent) => {
      event.stopPropagation()
      if (typeof event.button === 'number' && event.button !== 0) return
      const bounds = boundsRef.current
      const root = rootRef.current
      if (!bounds || !root) return
      onActivate?.()
      lastDragMovedRef.current = false
      cleanupRef.current?.()
      dragRef.current = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        originX: state.x,
        originY: state.y,
        moved: false,
      }

      const handleMove = (nextEvent: PointerEvent) => {
        if (!dragRef.current) return
        if (nextEvent.pointerId !== dragRef.current.pointerId) return
        const dx = nextEvent.clientX - dragRef.current.startX
        const dy = nextEvent.clientY - dragRef.current.startY
        if (!dragRef.current.moved && (Math.abs(dx) > 4 || Math.abs(dy) > 4)) {
          dragRef.current.moved = true
        }

        const boundsRect = bounds.getBoundingClientRect()
        const rootRect = root.getBoundingClientRect()
        const maxX = Math.max(
          FLOATING_PANEL_MARGIN,
          boundsRect.width - rootRect.width - FLOATING_PANEL_MARGIN
        )
        const maxY = Math.max(
          FLOATING_PANEL_MARGIN,
          boundsRect.height - rootRect.height - FLOATING_PANEL_MARGIN
        )
        const nextX = clamp(
          dragRef.current.originX + dx,
          FLOATING_PANEL_MARGIN,
          maxX
        )
        const nextY = clamp(dragRef.current.originY + dy, FLOATING_PANEL_MARGIN, maxY)
        onChange({ ...state, x: nextX, y: nextY })
      }

      const handleUp = (nextEvent: PointerEvent) => {
        if (!dragRef.current) return
        if (nextEvent.pointerId !== dragRef.current.pointerId) return
        lastDragMovedRef.current = dragRef.current.moved
        dragRef.current = null
        cleanupRef.current?.()
        cleanupRef.current = null
      }

      window.addEventListener('pointermove', handleMove)
      window.addEventListener('pointerup', handleUp)
      cleanupRef.current = () => {
        window.removeEventListener('pointermove', handleMove)
        window.removeEventListener('pointerup', handleUp)
      }
    },
    [boundsRef, onActivate, onChange, state]
  )

  const collapse = React.useCallback(
    (event: React.MouseEvent) => {
      event.stopPropagation()
      onChange({ ...state, collapsed: true })
    },
    [onChange, state]
  )

  const expand = React.useCallback(() => {
    if (lastDragMovedRef.current) {
      lastDragMovedRef.current = false
      return
    }
    onActivate?.()
    onChange({ ...state, collapsed: false })
  }, [onActivate, onChange, state])

  if (state.collapsed) {
    return (
      <button
        ref={rootRef as React.RefObject<HTMLButtonElement>}
        type="button"
        className={cn('lab-floating-orb nowheel nopan', className)}
        style={{ transform: `translate3d(${state.x}px, ${state.y}px, 0)`, zIndex }}
        onPointerDown={startDrag}
        onClick={(event) => {
          event.stopPropagation()
          expand()
        }}
        aria-label={`Show ${title}`}
      >
        {icon}
      </button>
    )
  }

  return (
    <div
      ref={rootRef as React.RefObject<HTMLDivElement>}
      className={cn('lab-floating-panel nowheel nopan', className)}
      style={{ transform: `translate3d(${state.x}px, ${state.y}px, 0)`, zIndex }}
      onPointerDown={(event) => {
        event.stopPropagation()
        onActivate?.()
      }}
    >
      <div className="lab-floating-panel__header" onPointerDown={startDrag}>
        <div className="lab-floating-panel__title">
          <span className="lab-floating-panel__icon">{icon}</span>
          <span>{title}</span>
        </div>
        <button
          type="button"
          className="lab-floating-panel__collapse"
          onPointerDown={(event) => event.stopPropagation()}
          onClick={collapse}
          aria-label={`Collapse ${title}`}
        >
          <ChevronDown size={16} />
        </button>
      </div>
      <div className="lab-floating-panel__content">{children}</div>
    </div>
  )
}

function LabQuestGraphCanvasInner({
  projectId,
  questId,
  readOnly,
  liveRun = false,
  highlightNodeId,
  highlightBranch,
  atEventId,
  preferredViewMode,
  activeBranch,
  onBranchSelect,
  onEventSelect,
  onSelectionChange,
  onStageOpen,
  showFloatingPanels = true,
  minimalChrome = false,
  fetchGraph,
  fetchEvents,
}: LabQuestGraphCanvasProps) {
  const graphFetcher = fetchGraph ?? getLabQuestGraph
  const eventFetcher = fetchEvents ?? listLabQuestEvents
  const isDemoProject = isDemoProjectId(projectId)
  const graphPollMs = isDemoProject ? DEMO_POLL_MS : liveRun ? 5000 : GRAPH_POLL_MS
  const panelPollMs = isDemoProject ? DEMO_POLL_MS : liveRun ? 8000 : PANEL_POLL_MS
  const backgroundPollMs = isDemoProject ? DEMO_POLL_MS : liveRun ? 12000 : BACKGROUND_POLL_MS
  const { t } = useI18n('lab')
  const resolvedTheme = useThemeStore((state) => state.resolvedTheme)
  const edgePalette = React.useMemo(() => resolveEdgePalette(resolvedTheme), [resolvedTheme])
  const interactionLocked = Boolean(readOnly || atEventId)
  const setSelectionStore = useLabGraphSelectionStore((state) => state.setSelection)
  const flow = useReactFlow()
  const nodesInitialized = useNodesInitialized()
  const boundsRef = React.useRef<HTMLDivElement | null>(null)
  const fittedViewportRef = React.useRef(new Set<string>())
  const resizeFitSignatureRef = React.useRef<string | null>(null)
  const userMovedViewportRef = React.useRef(false)
  const programmaticViewportMoveRef = React.useRef(false)
  const programmaticViewportTimerRef = React.useRef<number | null>(null)
  const lastAutoLayoutSignatureRef = React.useRef<string | null>(null)
  const collisionLayoutSignatureRef = React.useRef<string | null>(null)
  const [nodes, setNodes, onNodesChange] = useNodesState<QuestFlowNode>([])
  const [edgesState, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [viewMode, setViewMode] = React.useState<'branch' | 'event' | 'stage'>(
    preferredViewMode ?? 'branch'
  )
  const [eventTraceMode, setEventTraceMode] = React.useState<'compact' | 'detailed'>('compact')
  const [curveMode, setCurveMode] = React.useState<'sota' | 'full'>('sota')
  const [curveMetric, setCurveMetric] = React.useState<string>('')
  const [nodeDisplayMode, setNodeDisplayMode] = React.useState<'summary' | 'metric'>('summary')
  const [search, setSearch] = React.useState('')
  const [timeRange, setTimeRange] = React.useState<'all' | '7d' | '30d' | '90d'>('all')
  const [showAnalysis, setShowAnalysis] = React.useState(false)
  const [pathFilterMode, setPathFilterMode] = React.useState<PathFilterMode>('all')
  const analysisVisibilityTouchedRef = React.useRef(false)
  const canvasStateHydratedRef = React.useRef(false)
  const [eventFilter, setEventFilter] = React.useState<EventFilterMode>('activity')
  const [hoverCard, setHoverCard] = React.useState<GraphHoverCardState | null>(null)
  const hoverClearTimerRef = React.useRef<number | null>(null)
  const { openFileInTab } = useOpenFile()
  const findNode = useFileTreeStore((state) => state.findNode)
  const findNodeByPath = useFileTreeStore((state) => state.findNodeByPath)
  const [layoutOverride, setLayoutOverride] = React.useState<Record<string, Position>>({})
  const currentViewSemantic = React.useMemo(
    () => resolveLabCanvasViewSemantic(viewMode),
    [viewMode]
  )
  const canvasStateKey = React.useMemo(() => `${projectId}:${questId}`, [projectId, questId])

  React.useEffect(() => {
    return () => {
      if (hoverClearTimerRef.current) {
        window.clearTimeout(hoverClearTimerRef.current)
      }
      if (programmaticViewportTimerRef.current) {
        window.clearTimeout(programmaticViewportTimerRef.current)
      }
    }
  }, [])
  const saveTimeoutRef = React.useRef<number | null>(null)
  const viewModeRef = React.useRef(viewMode)
  const zCounterRef = React.useRef(2)
  const [panelZ, setPanelZ] = React.useState<Record<'branches' | 'events' | 'papers', number>>({
    branches: 1,
    events: 2,
    papers: 3,
  })
  const [branchesPanel, setBranchesPanel] = React.useState<FloatingPanelState>({
    x: 16,
    y: 16,
    collapsed: true,
  })
  const [eventsPanel, setEventsPanel] = React.useState<FloatingPanelState>({
    x: 16,
    y: 72,
    collapsed: true,
  })
  const [papersPanel, setPapersPanel] = React.useState<FloatingPanelState>({
    x: 16,
    y: 128,
    collapsed: true,
  })
  const [isPageVisible, setIsPageVisible] = React.useState(() => {
    if (typeof document === 'undefined') return true
    return document.visibilityState === 'visible'
  })

  React.useEffect(() => {
    if (typeof document === 'undefined') return
    const handleVisibility = () => {
      setIsPageVisible(document.visibilityState === 'visible')
    }
    handleVisibility()
    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [])

  const bringToFront = React.useCallback((key: 'branches' | 'events' | 'papers') => {
    zCounterRef.current += 1
    const nextZ = zCounterRef.current
    setPanelZ((prev) => ({ ...prev, [key]: nextZ }))
  }, [])

  React.useLayoutEffect(() => {
    const bounds = boundsRef.current
    if (!bounds) return
    setEventsPanel((prev) => {
      if (prev.x !== 16) return prev
      const rect = bounds.getBoundingClientRect()
      const nextX = Math.max(16, rect.width - EVENTS_PANEL_WIDTH - 16)
      return { ...prev, x: nextX }
    })
  }, [])

  React.useLayoutEffect(() => {
    const bounds = boundsRef.current
    if (!bounds) return
    const rect = bounds.getBoundingClientRect()

    const blockers: Rect[] = []
    const branchSize = resolvePanelSize('branches', branchesPanel.collapsed, rect)
    const eventsSize = resolvePanelSize('events', eventsPanel.collapsed, rect)
    const papersSize = resolvePanelSize('papers', papersPanel.collapsed, rect)
    if (!branchesPanel.collapsed) {
      blockers.push({ x: branchesPanel.x, y: branchesPanel.y, ...branchSize })
    }
    if (!eventsPanel.collapsed) {
      blockers.push({ x: eventsPanel.x, y: eventsPanel.y, ...eventsSize })
    }
    if (!papersPanel.collapsed) {
      blockers.push({ x: papersPanel.x, y: papersPanel.y, ...papersSize })
    }

    let nextBranches = branchesPanel
    if (branchesPanel.collapsed) {
      const pos = sanitizePosition(resolveOrbPosition(branchesPanel, rect, blockers), branchesPanel)
      nextBranches = { ...branchesPanel, ...pos }
      blockers.push({ x: pos.x, y: pos.y, width: ORB_SIZE, height: ORB_SIZE })
    }

    let nextEvents = eventsPanel
    if (eventsPanel.collapsed) {
      const pos = sanitizePosition(resolveOrbPosition(eventsPanel, rect, blockers), eventsPanel)
      nextEvents = { ...eventsPanel, ...pos }
      blockers.push({ x: pos.x, y: pos.y, width: ORB_SIZE, height: ORB_SIZE })
    }

    let nextPapers = papersPanel
    if (papersPanel.collapsed) {
      const pos = sanitizePosition(resolveOrbPosition(papersPanel, rect, blockers), papersPanel)
      nextPapers = { ...papersPanel, ...pos }
      blockers.push({ x: pos.x, y: pos.y, width: ORB_SIZE, height: ORB_SIZE })
    }

    if (branchesPanel.collapsed && isPositionDifferent(nextBranches, branchesPanel)) {
      setBranchesPanel(nextBranches)
    }
    if (eventsPanel.collapsed && isPositionDifferent(nextEvents, eventsPanel)) {
      setEventsPanel(nextEvents)
    }
    if (papersPanel.collapsed && isPositionDifferent(nextPapers, papersPanel)) {
      setPapersPanel(nextPapers)
    }
  }, [branchesPanel, eventsPanel, papersPanel])

  React.useEffect(() => {
    if (!preferredViewMode) return
    if (preferredViewMode === viewMode) return
    setViewMode(preferredViewMode)
  }, [preferredViewMode, viewMode])

  React.useEffect(() => {
    analysisVisibilityTouchedRef.current = false
    canvasStateHydratedRef.current = false
    setShowAnalysis(false)
    setPathFilterMode('all')
    setCurveMode('sota')
    setCurveMetric('')
    setNodeDisplayMode('summary')
    setLayoutOverride({})
    userMovedViewportRef.current = false
    lastAutoLayoutSignatureRef.current = null
    collisionLayoutSignatureRef.current = null
    resizeFitSignatureRef.current = null
  }, [projectId, questId])

  React.useEffect(() => {
    userMovedViewportRef.current = false
    collisionLayoutSignatureRef.current = null
    resizeFitSignatureRef.current = null
  }, [viewMode])

  const markProgrammaticViewportMove = React.useCallback((durationMs: number) => {
    programmaticViewportMoveRef.current = true
    if (programmaticViewportTimerRef.current) {
      window.clearTimeout(programmaticViewportTimerRef.current)
    }
    programmaticViewportTimerRef.current = window.setTimeout(() => {
      programmaticViewportMoveRef.current = false
      programmaticViewportTimerRef.current = null
    }, Math.max(0, durationMs) + 120)
  }, [])

  const livePollingEnabled = isPageVisible && !atEventId
  const shouldPollGraph = livePollingEnabled
  const shouldPollBranchData = livePollingEnabled && (viewMode === 'branch' || !branchesPanel.collapsed)
  const shouldPollEventsData = livePollingEnabled && (!eventsPanel.collapsed || viewMode === 'event')
  const shouldPollPapersData = livePollingEnabled && !papersPanel.collapsed
  const shouldPollAgentsData =
    livePollingEnabled && (viewMode !== 'stage' || !branchesPanel.collapsed || !eventsPanel.collapsed)
  const shouldPollDecisionData =
    livePollingEnabled && (!eventsPanel.collapsed || viewMode === 'event' || viewMode === 'stage')
  const shouldPollBranchInsights =
    livePollingEnabled && (viewMode === 'branch' || !branchesPanel.collapsed || !eventsPanel.collapsed)
  const hasQuestScope = Boolean(projectId && questId)
  const branchViewDataEnabled = hasQuestScope && showFloatingPanels
  const eventPanelDataEnabled = hasQuestScope && showFloatingPanels
  const decisionDataEnabled = hasQuestScope && (showFloatingPanels || viewMode === 'event')
  const papersDataEnabled = hasQuestScope && showFloatingPanels
  const piQaDataEnabled = hasQuestScope && showFloatingPanels
  const agentsDataEnabled = Boolean(projectId) && showFloatingPanels
  const branchGraphQueryEnabled = hasQuestScope && viewMode !== 'branch'

  const branchGraphQuery = useQuery({
    queryKey: ['lab-quest-graph', projectId, questId, 'branch', search],
    queryFn: () => graphFetcher(projectId, questId, { view: 'branch', search }),
    enabled: branchGraphQueryEnabled,
    retry: false,
    staleTime: 15000,
    refetchInterval: branchGraphQueryEnabled
      ? (query) => {
          const data = query.state.data as LabQuestGraphResponse | undefined
          if (projectionPending(data)) {
            return PROJECTION_POLL_MS
          }
          return shouldPollBranchData ? backgroundPollMs : false
        }
      : false,
  })

  const graphQuery = useQuery({
    queryKey: ['lab-quest-graph', projectId, questId, viewMode, search, atEventId ?? null],
    queryFn: () => graphFetcher(projectId, questId, { view: viewMode, search, atEventId }),
    enabled: hasQuestScope,
    retry: false,
    staleTime: 15000,
    refetchInterval: hasQuestScope
      ? (query) => {
          const data = query.state.data as LabQuestGraphResponse | undefined
          if (projectionPending(data)) {
            return PROJECTION_POLL_MS
          }
          return shouldPollGraph ? graphPollMs : false
        }
      : false,
  })

  const eventsQuery = useQuery({
    queryKey: ['lab-quest-events', projectId, questId, 'canvas'],
    queryFn: () => eventFetcher(projectId, questId, { limit: 40, includePayload: true }),
    enabled: eventPanelDataEnabled,
    retry: false,
    staleTime: 10000,
    refetchInterval: eventPanelDataEnabled && shouldPollEventsData ? panelPollMs : false,
  })

  const papersQuery = useQuery({
    queryKey: ['lab-papers', projectId, questId],
    queryFn: () => listLabPapers(projectId, { questId }),
    enabled: papersDataEnabled,
    retry: false,
    staleTime: 15000,
    refetchInterval: papersDataEnabled && shouldPollPapersData ? backgroundPollMs : false,
  })

  const memoryQuery = useQuery({
    queryKey: ['lab-memory', projectId, questId, 'canvas-branch-summary', atEventId ?? null],
    queryFn: () =>
      listLabMemory(projectId, {
        questId,
        atEventId,
        limit: 120,
      }),
    enabled: branchViewDataEnabled,
    retry: false,
    staleTime: 10000,
    refetchInterval: branchViewDataEnabled && shouldPollBranchInsights ? panelPollMs : false,
  })

  const agentsQuery = useQuery({
    queryKey: ['lab-agents', projectId],
    queryFn: () => listLabAgents(projectId, { silent: true }),
    enabled: agentsDataEnabled,
    retry: false,
    staleTime: 15000,
    refetchInterval: agentsDataEnabled && shouldPollAgentsData ? backgroundPollMs : false,
  })

  const decisionEventsQuery = useQuery({
    queryKey: ['lab-quest-decision-events', projectId, questId],
    queryFn: () =>
      eventFetcher(projectId, questId, {
        eventTypes: ['artifact.recorded', 'quest.control'],
        limit: 200,
        includePayload: true,
      }),
    enabled: decisionDataEnabled,
    retry: false,
    staleTime: 10000,
    refetchInterval: decisionDataEnabled && shouldPollDecisionData ? panelPollMs : false,
  })

  const piQaEventsQuery = useQuery({
    queryKey: ['lab-quest-pi-qa-events', projectId, questId],
    queryFn: () =>
      eventFetcher(projectId, questId, {
        eventTypes: ['conversation.message', 'interaction.reply_received'],
        limit: 80,
        includePayload: true,
      }),
    enabled: piQaDataEnabled,
    retry: false,
    staleTime: 10000,
    refetchInterval: piQaDataEnabled && shouldPollDecisionData ? panelPollMs : false,
  })

  const branchInsightEventsQuery = useQuery({
    queryKey: ['lab-quest-branch-insights', projectId, questId],
    queryFn: () =>
      eventFetcher(projectId, questId, {
        eventTypes: [
          'artifact.recorded',
          'runner.tool_result',
          'conversation.message',
          'interaction.reply_received',
          'quest.control',
        ],
        limit: 800,
        includePayload: true,
      }),
    enabled: branchViewDataEnabled,
    retry: false,
    staleTime: 10000,
    refetchInterval: branchViewDataEnabled && shouldPollBranchInsights ? panelPollMs : false,
  })

  const layoutMutation = useMutation({
    mutationFn: async (layout: QuestLayoutJson) =>
      updateLabQuestLayout(projectId, questId, layout as Record<string, unknown>),
  })

  const branchGraphData = viewMode === 'branch' ? graphQuery.data : branchGraphQuery.data
  const branchDataIsLoading = viewMode === 'branch' ? graphQuery.isLoading : branchGraphQuery.isLoading
  const branchProjectionPending = projectionPending(branchGraphData)
  const branchProjectionProgress = React.useMemo(
    () => projectionProgress(branchGraphData),
    [branchGraphData?.projection_status]
  )
  const branchProjectionStatusMessage = React.useMemo(() => {
    const status = branchGraphData?.projection_status
    const state = projectionState(branchGraphData)
    if (!state || state === 'ready') return null
    const current = typeof status?.progress_current === 'number' ? status.progress_current : null
    const total = typeof status?.progress_total === 'number' ? status.progress_total : null
    const step = status?.current_step?.trim()
    const suffix =
      current != null && total != null && total > 0 ? ` (${Math.min(current, total)}/${total})` : ''
    if (state === 'queued') {
      return `Branch canvas queued for rebuild${suffix}${step ? ` · ${step}` : ''}.`
    }
    if (state === 'building') {
      return `Branch canvas is rebuilding in the background${suffix}${step ? ` · ${step}` : ''}.`
    }
    if (state === 'stale') {
      return 'Showing the last successful branch canvas while a refresh is queued.'
    }
    if (state === 'failed') {
      return step || status?.error?.trim() || 'Branch canvas rebuild failed.'
    }
    return step || `Branch canvas projection state: ${state}.`
  }, [branchGraphData?.projection_status])
  const baselineMetricSnapshot = React.useMemo(
    () => buildBaselineMetricSnapshot(branchGraphData?.nodes ?? EMPTY_GRAPH_NODES),
    [branchGraphData?.nodes]
  )

  const metricCatalog = React.useMemo(() => {
    const explicit = normalizeMetricCatalog(graphQuery.data?.metric_catalog ?? branchGraphData?.metric_catalog)
    if (explicit.length) return explicit
    const catalog = new Map<string, LabMetricObjective>()
    const upsert = (entry: LabMetricObjective) => {
      if (!entry.key) return
      const current = catalog.get(entry.key)
      catalog.set(entry.key, {
        key: entry.key,
        label: entry.label || current?.label || entry.key,
        direction: entry.direction || current?.direction || null,
        importance: entry.importance ?? current?.importance ?? null,
        unit: entry.unit ?? current?.unit ?? null,
        target: entry.target ?? current?.target ?? null,
      })
    }
    ;(branchGraphData?.nodes ?? []).forEach((node) => {
      const snapshot = buildNodeMetricSnapshot(node)
      snapshot.meta.forEach((entry) =>
        upsert({
          key: entry.key,
          label: entry.label,
          direction: entry.direction,
          importance: null,
          unit: entry.unit ?? null,
          target: null,
        })
      )
      Object.keys(snapshot.metrics).forEach((key) =>
        upsert({
          key,
          label: snapshot.meta.get(key)?.label || key,
          direction: snapshot.meta.get(key)?.direction || null,
          importance: null,
          unit: snapshot.meta.get(key)?.unit ?? null,
          target: null,
        })
      )
      const curves = resolveNodeMetricCurves(node)
      Object.keys(curves || {}).forEach((key) =>
        upsert({
          key,
          label: snapshot.meta.get(key)?.label || key,
          direction: snapshot.meta.get(key)?.direction || null,
          importance: null,
          unit: snapshot.meta.get(key)?.unit ?? null,
          target: null,
        })
      )
    })
    baselineMetricSnapshot.meta.forEach((entry) =>
      upsert({
        key: entry.key,
        label: entry.label,
        direction: entry.direction,
        importance: null,
        unit: entry.unit ?? null,
        target: null,
      })
    )
    return [...catalog.values()].sort((left, right) => {
      const leftImportance = typeof left.importance === 'number' ? left.importance : -1
      const rightImportance = typeof right.importance === 'number' ? right.importance : -1
      if (leftImportance !== rightImportance) return rightImportance - leftImportance
      return left.key.localeCompare(right.key)
    })
  }, [baselineMetricSnapshot, branchGraphData?.metric_catalog, branchGraphData?.nodes, graphQuery.data?.metric_catalog])

  React.useEffect(() => {
    if (!metricCatalog.length) {
      if (curveMetric) setCurveMetric('')
      return
    }
    const exists = metricCatalog.some((item) => item.key === curveMetric)
    if (!exists) {
      setCurveMetric(metricCatalog[0]?.key || '')
    }
  }, [curveMetric, metricCatalog])

  const metricObjectiveMap = React.useMemo(() => {
    const map = new Map<string, LabMetricObjective>()
    metricCatalog.forEach((item) => {
      if (item.key) map.set(item.key, item)
    })
    return map
  }, [metricCatalog])

  const layoutJson = (graphQuery.data?.layout_json ?? branchGraphData?.layout_json ?? null) as
    | QuestLayoutJson
    | null

  React.useEffect(() => {
    if (canvasStateHydratedRef.current) return
    if (graphQuery.isLoading || branchDataIsLoading) return
    const preferences = resolveCanvasPreferences(layoutJson)
    if (preferences.curveMode === 'full' || preferences.curveMode === 'sota') {
      setCurveMode(preferences.curveMode)
    }
    if (preferences.nodeDisplayMode === 'metric' || preferences.nodeDisplayMode === 'summary') {
      setNodeDisplayMode(preferences.nodeDisplayMode)
    }
    if (typeof preferences.curveMetric === 'string' && preferences.curveMetric.trim()) {
      setCurveMetric(preferences.curveMetric.trim())
    }
    if (typeof preferences.showAnalysis === 'boolean') {
      analysisVisibilityTouchedRef.current = true
      setShowAnalysis(preferences.showAnalysis)
    }
    setPathFilterMode(normalizePathFilterMode(preferences.pathFilterMode))
    canvasStateHydratedRef.current = true
  }, [branchDataIsLoading, canvasStateKey, graphQuery.isLoading, layoutJson])

  const headBranch = graphQuery.data?.head_branch ?? branchGraphData?.head_branch

  const branchNodesRaw = branchGraphData?.nodes ?? EMPTY_GRAPH_NODES
  React.useEffect(() => {
    if (analysisVisibilityTouchedRef.current) return
    const hasAnalysisNodes = branchNodesRaw.some((node) => isAnalysisBranch(node.branch_name))
    if (hasAnalysisNodes && !showAnalysis) {
      setShowAnalysis(true)
    }
  }, [branchNodesRaw, showAnalysis])
  const branchNodesFiltered = React.useMemo(() => {
    if (showAnalysis) return branchNodesRaw
    const hiddenNodeIds = new Set(
      branchNodesRaw.filter((node) => isAnalysisBranch(node.branch_name)).map((node) => node.node_id)
    )
    return branchNodesRaw.filter((node) => {
      if (isAnalysisBranch(node.branch_name)) return false
      if (node.node_kind === 'placeholder' && node.parent_branch && hiddenNodeIds.has(node.parent_branch)) {
        return false
      }
      return true
    })
  }, [branchNodesRaw, showAnalysis])

  const viewNodesRaw = graphQuery.data?.nodes ?? EMPTY_GRAPH_NODES
  const viewNodesFiltered = React.useMemo(() => {
    if (showAnalysis) return viewNodesRaw
    const hiddenNodeIds = new Set(
      viewNodesRaw.filter((node) => isAnalysisBranch(node.branch_name)).map((node) => node.node_id)
    )
    return viewNodesRaw.filter((node) => {
      if (isAnalysisBranch(node.branch_name)) return false
      if (node.node_kind === 'placeholder' && node.parent_branch && hiddenNodeIds.has(node.parent_branch)) {
        return false
      }
      return true
    })
  }, [showAnalysis, viewNodesRaw])

  const filterByTime = React.useCallback(
    (node: LabQuestGraphNode) => {
      if (viewMode === 'stage') return true
      if (timeRange === 'all') return true
      if (!node.created_at) return true
      const timestamp = new Date(node.created_at).getTime()
      if (Number.isNaN(timestamp)) return true
      const days = timeRange === '7d' ? 7 : timeRange === '30d' ? 30 : 90
      const cutoff = Date.now() - days * 24 * 60 * 60 * 1000
      return timestamp >= cutoff
    },
    [timeRange, viewMode]
  )

  const branchNodesBase = React.useMemo(
    () => branchNodesFiltered.filter(filterByTime),
    [branchNodesFiltered, filterByTime]
  )

  const visibleBranchLineage = React.useMemo(() => {
    if (pathFilterMode === 'all') return new Set<string>()
    const fallbackBranch =
      branchNodesBase.find((node) => node.node_kind !== 'baseline_root' && node.node_kind !== 'placeholder')?.branch_name ||
      null
    const targetBranch =
      pathFilterMode === 'selected'
        ? activeBranch || headBranch || fallbackBranch
        : activeBranch || headBranch || fallbackBranch
    return buildBranchLineageSet(branchNodesBase, targetBranch)
  }, [activeBranch, branchNodesBase, headBranch, pathFilterMode])

  const currentWorkspaceBranch = React.useMemo(() => {
    const fallbackBranch =
      branchNodesBase.find((node) => node.node_kind !== 'baseline_root' && node.node_kind !== 'placeholder')?.branch_name ||
      null
    return activeBranch || headBranch || fallbackBranch || null
  }, [activeBranch, branchNodesBase, headBranch])

  const currentWorkspaceLineage = React.useMemo(
    () => buildBranchLineageSet(branchNodesBase, currentWorkspaceBranch),
    [branchNodesBase, currentWorkspaceBranch]
  )

  const branchNodes = React.useMemo(() => {
    if (pathFilterMode === 'all') return branchNodesBase
    return filterNodesByBranchLineage(branchNodesBase, visibleBranchLineage)
  }, [branchNodesBase, pathFilterMode, visibleBranchLineage])

  const viewNodesAllBase = React.useMemo(
    () => viewNodesFiltered.filter(filterByTime),
    [filterByTime, viewNodesFiltered]
  )

  const viewNodesAll = React.useMemo(() => {
    if (viewMode !== 'branch' || pathFilterMode === 'all') return viewNodesAllBase
    return filterNodesByBranchLineage(viewNodesAllBase, visibleBranchLineage)
  }, [pathFilterMode, viewMode, viewNodesAllBase, visibleBranchLineage])

  const viewNodes = React.useMemo(() => {
    if (viewMode === 'event' && eventTraceMode === 'compact') {
      return viewNodesAll.filter((node) => isKeyEventType(node.status))
    }
    return viewNodesAll
  }, [eventTraceMode, viewMode, viewNodesAll])

  const questAgents = React.useMemo(() => {
    const agents = agentsQuery.data?.items ?? []
    return agents.filter((agent) => agent.active_quest_id === questId)
  }, [agentsQuery.data?.items, questId])

  const activeAgentByBranch = React.useMemo(() => {
    const map = new Map<string, string>()
    questAgents.forEach((agent) => {
      const branchName = agent.active_quest_branch || 'main'
      const stage = agent.active_quest_stage_key || agent.status || 'working'
      const label = resolveAgentDisplayName(agent)
      if (!map.has(branchName) && (isActiveAgentStatus(agent.status) || Boolean(agent.active_quest_stage_key))) {
        map.set(branchName, `${label}: ${stage}`)
      }
    })
    return map
  }, [questAgents])

  const branchInsights = React.useMemo(() => {
    const groupedEvents = new Map<string, LabQuestEventItem[]>()
    const sourceEvents = branchInsightEventsQuery.data?.items ?? []
    sourceEvents.forEach((event) => {
      const branchName = event.branch_name || 'main'
      if (!showAnalysis && isAnalysisBranch(branchName)) return
      const list = groupedEvents.get(branchName)
      if (list) {
        list.push(event)
      } else {
        groupedEvents.set(branchName, [event])
      }
    })
    groupedEvents.forEach((list) => {
      list.sort((left, right) => parseEventTime(left.created_at) - parseEventTime(right.created_at))
    })

    const branchNames = new Set<string>()
    branchNodesFiltered.forEach((node) => {
      if (node.node_kind === 'baseline_root' || node.node_kind === 'placeholder') return
      if (node.branch_name) {
        branchNames.add(node.branch_name)
      }
    })
    groupedEvents.forEach((_, branchName) => branchNames.add(branchName))
    if (!branchNames.size) {
      branchNames.add('main')
    }

    const branchNodeMap = new Map<string, LabQuestGraphNode>()
    branchNodesFiltered.forEach((node) => {
      if (node.node_kind === 'baseline_root' || node.node_kind === 'placeholder') return
      if (!node.branch_name) return
      if (!branchNodeMap.has(node.branch_name)) {
        branchNodeMap.set(node.branch_name, node)
      }
    })

    const map = new Map<string, BranchInsight>()
    branchNames.forEach((branchName) => {
      const branchEvents = groupedEvents.get(branchName) ?? []
      const fallbackNode = branchNodeMap.get(branchName)
      const fallbackStage = String(fallbackNode?.stage_key || 'baseline') as BranchStage
      const workflowState = fallbackNode?.workflow_state ?? null
      const hasWorkflowState = Boolean(
        workflowState &&
          (String(workflowState.analysis_state || '').trim() ||
            String(workflowState.writing_state || '').trim() ||
            String(workflowState.status_reason || '').trim() ||
            String(workflowState.analysis_campaign_id || '').trim())
      )
      let stage: BranchStage = resolveWorkflowBranchStage(
        workflowState,
        STAGE_ORDER.includes(fallbackStage) ? fallbackStage : 'baseline'
      )
      const workflowWritingState = String(workflowState?.writing_state || '').trim().toLowerCase()
      let writingEligible =
        workflowWritingState === 'ready' ||
        workflowWritingState === 'active' ||
        workflowWritingState === 'completed'
      let writingActive = workflowWritingState === 'active'
      let completed = workflowWritingState === 'completed'
      let verdict: string | null = null
      let latestDecisionEvent: LabQuestEventItem | null = null

      branchEvents.forEach((event) => {
        if (!hasWorkflowState) {
          const stageKey = resolveEventStageKey(event)
          if (
            stageKey &&
            stageKey !== 'decision' &&
            STAGE_ORDER.includes(stageKey as BranchStage)
          ) {
            stage = elevateBranchStage(stage, stageKey as BranchStage)
          }
        }
        if (isDecisionEvent(event)) {
          latestDecisionEvent = event
        }
        const currentVerdict = resolveOutcomeVerdict(event)
        if (currentVerdict) {
          verdict = currentVerdict
        }
        if (!hasWorkflowState) {
          if (currentVerdict === 'good' && (stage === 'experiment' || stage === 'analysis-campaign')) {
            writingEligible = true
          }
          if (isWritingEvent(event)) {
            writingActive = true
          }
        }
      })

      if (!hasWorkflowState) {
        if (stage === 'write' || stage === 'finalize') {
          writingEligible = true
        }
        if (stage === 'finalize') {
          completed = true
          writingActive = false
        } else if (stage === 'write') {
          writingActive = true
        }
      }

      const latestEvent = branchEvents.length ? branchEvents[branchEvents.length - 1] : null
      const updatedAt = latestEvent?.created_at || fallbackNode?.created_at || null
      const nowDoing =
        clampCanvasText(activeAgentByBranch.get(branchName), 88) ||
        clampCanvasText(summarizeEvent(latestEvent), 88) ||
        clampCanvasText(fallbackNode?.node_summary?.last_reply, 88) ||
        null
      const decisionReason = latestDecisionEvent
        ? clampCanvasText(resolveDecisionReason(latestDecisionEvent), 100)
        : null
      const stale = Boolean(updatedAt) && Date.now() - parseEventTime(updatedAt) > STALE_BRANCH_MS
      const workflowEvidence = resolveWorkflowEvidenceStatus(workflowState)
      const evidenceParts = workflowEvidence ? [workflowEvidence] : [`stage ${BRANCH_STAGE_LABELS[stage]}`]
      if (verdict && !workflowEvidence) {
        evidenceParts.push(`verdict ${verdict}`)
      }
      if (decisionReason) {
        evidenceParts.push('decision recorded')
      }
      if (stale) {
        evidenceParts.push('stale')
      }
      map.set(branchName, {
        branchName,
        stage,
        stageLabel: BRANCH_STAGE_LABELS[stage],
        nowDoing,
        decisionReason,
        evidenceStatus: evidenceParts.join(' · '),
        verdict,
        writingEligible,
        writingActive,
        completed,
        updatedAt,
        stale,
        workflowState,
      })
    })

    return map
  }, [activeAgentByBranch, branchInsightEventsQuery.data?.items, branchNodesFiltered, showAnalysis])

  const memoryByBranch = React.useMemo(() => {
    const map = new Map<
      string,
      {
        count: number
        latestTitle: string | null
        latestSummary: string | null
        latestStamp: string | null
      }
    >()
    const items = memoryQuery.data?.items ?? []
    items.forEach((entry: LabMemoryEntry) => {
      const branchName = String(entry.branch_name || 'main').trim() || 'main'
      const current = map.get(branchName)
      const stamp = String(entry.occurred_at || entry.updated_at || entry.created_at || '')
      if (!current) {
        map.set(branchName, {
          count: 1,
          latestTitle: entry.title || entry.entry_id,
          latestSummary: entry.summary || null,
          latestStamp: stamp || null,
        })
        return
      }
      current.count += 1
      const currentStamp = String(current.latestStamp || '')
      if (stamp >= currentStamp) {
        current.latestTitle = entry.title || entry.entry_id
        current.latestSummary = entry.summary || null
        current.latestStamp = stamp || null
      }
      map.set(branchName, current)
    })
    return map
  }, [memoryQuery.data?.items])

  const globalBuckets = React.useMemo<BucketCounts>(() => {
    const counts: BucketCounts = {
      ideasOnly: 0,
      experimenting: 0,
      writingEligible: 0,
      writingActive: 0,
      completed: 0,
      stale: 0,
    }
    const branchNames = new Set<string>()
    branchNodesFiltered.forEach((node) => {
      if (node.branch_name) {
        branchNames.add(node.branch_name)
      }
    })
    branchInsights.forEach((_, branchName) => branchNames.add(branchName))
    if (!branchNames.size) {
      branchNames.add('main')
    }

    branchNames.forEach((branchName) => {
      const insight = branchInsights.get(branchName)
      if (!insight) {
        counts.ideasOnly += 1
        return
      }
      if (insight.completed) {
        counts.completed += 1
      } else if (insight.writingActive) {
        counts.writingActive += 1
      } else if (insight.writingEligible) {
        counts.writingEligible += 1
      } else if (insight.stage === 'experiment' || insight.stage === 'analysis-campaign') {
        counts.experimenting += 1
      } else {
        counts.ideasOnly += 1
      }
      if (insight.stale) {
        counts.stale += 1
      }
    })

    return counts
  }, [branchInsights, branchNodesFiltered])

  const nowDoingItems = React.useMemo(() => {
    return [...branchInsights.values()]
      .sort((left, right) => parseEventTime(right.updatedAt) - parseEventTime(left.updatedAt))
      .filter((item) => Boolean(item.nowDoing))
      .slice(0, 5)
  }, [branchInsights])

  const decisionLogItems = React.useMemo(() => {
    const items = (decisionEventsQuery.data?.items ?? []).filter((event) => isDecisionEvent(event))
    return [...items].sort((left, right) => parseEventTime(right.created_at) - parseEventTime(left.created_at))
  }, [decisionEventsQuery.data?.items])

  const branchNodeIdSet = React.useMemo(
    () => new Set(branchNodes.map((node) => node.node_id)),
    [branchNodes]
  )
  const branchEdgesRaw = branchGraphData?.edges ?? EMPTY_GRAPH_EDGES
  const branchEdges = React.useMemo(
    () =>
      branchEdgesRaw.filter(
        (edge) => branchNodeIdSet.has(edge.source) && branchNodeIdSet.has(edge.target)
      ),
    [branchEdgesRaw, branchNodeIdSet]
  )
  const branchLayoutNodes = React.useMemo(
    () => sortNodesForLayout(branchNodes, 'branch'),
    [branchNodes]
  )
  const branchLayoutEdges = React.useMemo(
    () => sortEdgesForLayout(branchEdges, branchLayoutNodes),
    [branchEdges, branchLayoutNodes]
  )
  const branchLayoutFallback = React.useMemo(
    () =>
      buildBranchLayout(branchLayoutNodes, branchLayoutEdges, {
        nodeDisplayMode,
        curveMetric: curveMetric || null,
        curveMode,
        branchInsights,
        memoryByBranch,
      }),
    [branchInsights, branchLayoutEdges, branchLayoutNodes, curveMetric, curveMode, memoryByBranch, nodeDisplayMode]
  )
  const branchLayoutExplicit = React.useMemo(() => resolveLayoutMap(layoutJson, 'branch'), [layoutJson])
  const branchLayoutMap = React.useMemo(
    () => ({
      ...branchLayoutFallback,
      ...branchLayoutExplicit,
    }),
    [branchLayoutExplicit, branchLayoutFallback]
  )
  const branchNodeByName = React.useMemo(() => {
    const map = new Map<string, LabQuestGraphNode>()
    branchNodes.forEach((node) => {
      if (node.branch_name && !map.has(node.branch_name)) {
        map.set(node.branch_name, node)
      }
    })
    return map
  }, [branchNodes])

  const decisionPayloads = React.useMemo(() => {
    const map = new Map<string, Record<string, unknown>>()
    const items = decisionEventsQuery.data?.items ?? []
    items.forEach((event) => {
      if (!isDecisionEvent(event)) return
      const payload = extractEventPayload(event.payload_json as Record<string, unknown> | null)
      if (payload) {
        map.set(event.event_id, payload)
      }
    })
    return map
  }, [decisionEventsQuery.data])

  const viewNodeIds = React.useMemo(() => new Set(viewNodes.map((node) => node.node_id)), [viewNodes])
  const edgesRaw = graphQuery.data?.edges ?? EMPTY_GRAPH_EDGES
  const viewEdges = React.useMemo(() => {
    return edgesRaw.filter((edge) => viewNodeIds.has(edge.source) && viewNodeIds.has(edge.target))
  }, [edgesRaw, viewNodeIds])
  const layoutNodes = React.useMemo(
    () => sortNodesForLayout(viewNodes, viewMode),
    [viewMode, viewNodes]
  )
  const layoutEdges = React.useMemo(
    () => sortEdgesForLayout(viewEdges, layoutNodes),
    [layoutNodes, viewEdges]
  )
  const fallbackLayout = React.useMemo(
    () =>
      viewMode === 'event'
        ? buildEventLayout(layoutNodes, layoutEdges)
        : viewMode === 'stage'
          ? buildStageLayout(layoutNodes, layoutEdges)
          : buildBranchLayout(layoutNodes, layoutEdges, {
              nodeDisplayMode,
              curveMetric: curveMetric || null,
              curveMode,
              branchInsights,
              memoryByBranch,
            }),
    [branchInsights, curveMetric, curveMode, layoutEdges, layoutNodes, memoryByBranch, nodeDisplayMode, viewMode]
  )
  const autoLayoutSignature = React.useMemo(() => {
    const layoutEntries = Object.entries(fallbackLayout)
      .sort(([left], [right]) => compareLayoutText(left, right))
      .map(([id, position]) => `${id}:${Math.round(position.x * 10) / 10}:${Math.round(position.y * 10) / 10}`)
    return [
      viewMode,
      showAnalysis ? 'analysis:on' : 'analysis:off',
      pathFilterMode,
      timeRange,
      eventTraceMode,
      nodeDisplayMode,
      curveMode,
      curveMetric || '',
      layoutEntries.join('|'),
    ].join('::')
  }, [
    curveMetric,
    curveMode,
    eventTraceMode,
    fallbackLayout,
    nodeDisplayMode,
    pathFilterMode,
    showAnalysis,
    timeRange,
    viewMode,
  ])
  const explicitLayout = React.useMemo(
    () => ({
      ...resolveLayoutMap(layoutJson, viewMode),
      ...layoutOverride,
    }),
    [layoutJson, layoutOverride, viewMode]
  )
  const hasExplicitNodeLayout = React.useMemo(
    () => Object.keys(explicitLayout).length > 0,
    [explicitLayout]
  )
  const layoutMap = React.useMemo(
    () => ({
      ...fallbackLayout,
      ...explicitLayout,
    }),
    [explicitLayout, fallbackLayout]
  )

  const highlightIds = React.useMemo(() => {
    const ids = new Set<string>()
    if (highlightNodeId) ids.add(highlightNodeId)
    if (viewMode === 'branch') {
      let branchName = highlightBranch ?? null
      if (!branchName && highlightNodeId) {
        const node = viewNodes.find((item) => item.node_id === highlightNodeId)
        branchName = node?.branch_name ?? null
      }
      if (branchName) {
        const branchMap = new Map<string, LabQuestGraphNode>()
        viewNodes.forEach((node) => {
          if (node.branch_name) branchMap.set(node.branch_name, node)
        })
        let current: string | null = branchName
        while (current && branchMap.has(current)) {
          const node = branchMap.get(current)
          if (!node) break
          ids.add(node.node_id)
          current = node.parent_branch ?? null
        }
      }
    }
    return ids
  }, [highlightBranch, highlightNodeId, viewMode, viewNodes])

  const currentPathNodeIds = React.useMemo(() => {
    if (viewMode !== 'branch' || !currentWorkspaceLineage.size) return new Set<string>()
    return new Set(
      viewNodes
        .filter((node) => node.branch_name && currentWorkspaceLineage.has(node.branch_name))
        .map((node) => node.node_id)
    )
  }, [currentWorkspaceLineage, viewMode, viewNodes])

  React.useEffect(() => {
    if (viewMode !== 'event') return
    if (eventTraceMode !== 'compact') return
    if (!highlightNodeId) return
    const exists = viewNodesAll.some((node) => node.node_id === highlightNodeId)
    const visible = viewNodeIds.has(highlightNodeId)
    if (exists && !visible) {
      setEventTraceMode('detailed')
    }
  }, [eventTraceMode, highlightNodeId, viewMode, viewNodeIds, viewNodesAll])

  const computedQuestNodes: QuestFlowNode[] = React.useMemo(
    () =>
      viewNodes.map((node) => {
        const nodeMetricSnapshot =
          viewMode === 'branch' && node.node_kind === 'baseline_root'
            ? baselineMetricSnapshot
            : buildNodeMetricSnapshot(node)
        const metricSource =
          Object.keys(nodeMetricSnapshot.metrics).length > 0
            ? nodeMetricSnapshot.metrics
            : ((node.metrics_json as Record<string, unknown> | null) ?? null)
        const selectedMetric = pickMetricValue(metricSource, curveMetric || null)
        const objective = selectedMetric ? metricObjectiveMap.get(selectedMetric.key) ?? null : null
        const snapshotMeta = selectedMetric ? nodeMetricSnapshot.meta.get(selectedMetric.key) ?? null : null
        const metricMeta = selectedMetric
          ? {
              key: selectedMetric.key,
              label: snapshotMeta?.label || objective?.label || selectedMetric.key,
              direction: snapshotMeta?.direction || objective?.direction || null,
              unit: snapshotMeta?.unit || objective?.unit || null,
              decimals: snapshotMeta?.decimals ?? null,
            }
          : null
        const metric = selectedMetric
          ? formatMetricLabel(selectedMetric.key, selectedMetric.value)
          : pickPrimaryMetric(metricSource)
        const metricDelta =
          selectedMetric && typeof nodeMetricSnapshot.deltas[selectedMetric.key] === 'number'
            ? nodeMetricSnapshot.deltas[selectedMetric.key]
            : null
        const metricValueLabel =
          selectedMetric && metricMeta
            ? formatMetricValueDisplay(selectedMetric.value, metricMeta)
            : selectedMetric
              ? formatMetricValueDisplay(selectedMetric.value)
              : null
        const metricDeltaLabel =
          selectedMetric && typeof metricDelta === 'number'
            ? formatMetricDeltaDisplay(metricDelta, metricMeta)
            : null
        const metricTone = resolveMetricTone(metricDelta, metricMeta?.direction)
        const fallbackSummary =
          clampCanvasText(node.node_summary?.last_error, 96) ||
          clampCanvasText(node.node_summary?.last_reply, 96) ||
          clampCanvasText(node.node_summary?.last_event_type, 96) ||
          null
        const deltaLabel = formatDeltaLabel(
          node.node_summary?.metrics_delta as Record<string, unknown> | number | null
        )
        const trend = extractTrend(node, { metricKey: curveMetric || null, mode: curveMode }) || undefined
        const isStage = viewMode === 'stage'
        const isDecision = viewMode === 'event' && String(node.stage_key || '').toLowerCase() === 'decision'
        const decisionPayload = isDecision ? decisionPayloads.get(node.node_id) : null
        const decisionValue =
          decisionPayload?.action || decisionPayload?.verdict || decisionPayload?.status
            ? String(decisionPayload?.action || decisionPayload?.verdict || decisionPayload?.status)
            : ''
        const decisionTarget = decisionPayload?.target_idea_id || decisionPayload?.idea_id
          ? String(decisionPayload?.target_idea_id || decisionPayload?.idea_id)
          : null
        const branchInsight =
          viewMode === 'branch' && node.branch_name ? branchInsights.get(node.branch_name) : null
        const branchMemory =
          viewMode === 'branch' && node.branch_name ? memoryByBranch.get(node.branch_name) : null
        const isPlaceholder = Boolean(node.placeholder || node.node_kind === 'placeholder')
        const isBaselineRoot = node.node_kind === 'baseline_root'
        const label = isStage
          ? node.stage_title || node.stage_key || node.branch_name || 'stage'
          : viewMode === 'event'
            ? isDecision
              ? `DECISION: ${decisionValue || 'recorded'}`
              : node.target_label || node.stage_title || node.status || node.branch_name || 'event'
            : node.target_label || node.branch_name
        const subtitle = isStage
          ? typeof node.event_count === 'number'
            ? `${node.event_count} event${node.event_count === 1 ? '' : 's'}`
            : null
          : viewMode === 'event'
            ? isDecision
              ? decisionPayload?.reason
                ? clampCanvasText(String(decisionPayload.reason), 80)
                : decisionPayload?.justification
                  ? clampCanvasText(String(decisionPayload.justification), 80)
                  : node.branch_name
              : node.stage_title || node.branch_name
              : isBaselineRoot
                ? node.status || null
              : isPlaceholder
                ? t('quest_graph_next_step_placeholder', undefined, 'Next step')
                : node.idea_title || branchInsight?.stageLabel || node.idea_id || 'Branch'
        const nodeStatus =
          viewMode === 'branch'
            ? isPlaceholder
              ? t('quest_process_status_pending', undefined, 'Pending')
              : branchInsight?.updatedAt
              ? `Updated ${formatRelativeTime(branchInsight.updatedAt)}`
              : node.status
            : node.status
        const isSelected =
          highlightIds.size > 0
            ? highlightIds.has(node.node_id)
            : viewMode === 'branch'
              ? Boolean(currentWorkspaceBranch && node.branch_name === currentWorkspaceBranch)
              : false
        const isCurrentWorkspace =
          viewMode === 'branch' && Boolean(currentWorkspaceBranch && node.branch_name === currentWorkspaceBranch)
        const isCurrentPath =
          viewMode === 'branch' && Boolean(node.branch_name && currentWorkspaceLineage.has(node.branch_name))
        return {
          id: node.node_id,
          type: 'questNode',
          position: layoutMap[node.node_id] ?? { x: 0, y: 0 },
          sourcePosition: FlowPosition.Right,
          targetPosition: FlowPosition.Left,
          data: {
            label: label || 'node',
            subtitle,
            branchNo: node.branch_no ?? null,
            parentBranch: node.parent_branch ?? null,
            ideaTitle: node.idea_title ?? null,
            foundationLabel: node.foundation_label ?? null,
            foundationReason: node.foundation_reason ?? null,
            foundationRef: node.foundation_ref ?? null,
            status: nodeStatus,
            metric: viewMode === 'branch' ? null : metric,
            verdict:
              normalizeOutcomeVerdictValue(branchInsight?.verdict) ||
              normalizeOutcomeVerdictValue(node.verdict),
            summary: viewMode === 'branch' ? null : fallbackSummary,
            deltaLabel,
            displayMode: viewMode === 'branch' ? nodeDisplayMode : 'summary',
            metricKey: selectedMetric?.key ?? null,
            metricLabel: metricMeta?.label ?? null,
            metricValueLabel,
            metricDeltaLabel,
            metricDirection: metricMeta?.direction ?? null,
            metricTone,
            metricEmptyReason:
              viewMode !== 'branch'
                ? null
                : node.node_kind === 'baseline_root'
                  ? t('quest_metric_baseline_reference', undefined, 'Baseline reference')
                  : selectedMetric
                    ? null
                    : t('quest_metric_empty', undefined, 'No metric available'),
            trend,
            isHead: viewMode === 'branch' && Boolean(headBranch && node.branch_name === headBranch),
            isRoot: viewMode === 'branch' && isBaselineRoot,
            isPlaceholder: viewMode === 'branch' && isPlaceholder,
            isSelected,
            isCurrentWorkspace,
            isCurrentPath,
            isEvent: viewMode === 'event',
            branchName: node.branch_name,
            decisionType: decisionValue ? decisionValue.toLowerCase() : null,
            decisionTarget,
            stageKey: node.stage_key ?? null,
            stageTitle: node.stage_title ?? null,
            eventCount: node.event_count ?? null,
            eventIds: node.event_ids ?? null,
            stageLabel: branchInsight?.stageLabel ?? null,
            nowDoing:
              viewMode === 'branch'
                ? branchInsight?.nowDoing ?? node.idea_problem ?? fallbackSummary
                : null,
            decisionReason: viewMode === 'branch' ? branchInsight?.decisionReason ?? null : null,
            evidenceStatus:
              viewMode === 'branch'
                ? branchInsight?.evidenceStatus ??
                  clampCanvasText(node.node_summary?.last_reply, 96) ??
                  null
                : null,
            branchClass: node.branch_class ?? null,
            nodeKind: node.node_kind ?? 'branch',
            scopePaths: node.scope_paths ?? null,
            compareBase: node.compare_base ?? null,
            compareHead: node.compare_head ?? null,
            worktreeRelPath: node.worktree_rel_path ?? null,
            memoryLabel:
              viewMode === 'branch' && !isPlaceholder && !isBaselineRoot && branchMemory
                ? `${branchMemory.count} memory ${branchMemory.count === 1 ? 'note' : 'notes'}`
                : null,
            memorySummary:
              viewMode === 'branch' && !isPlaceholder && !isBaselineRoot
                ? branchMemory?.latestSummary ?? null
                : null,
            memoryCount:
              viewMode === 'branch' && !isPlaceholder && !isBaselineRoot
                ? branchMemory?.count ?? null
                : null,
            baselineState: node.baseline_state ?? null,
            pushState: node.push_state ?? null,
            writerState: node.writer_state ?? null,
            runtimeState: node.runtime_state ?? null,
            protectedState: node.protected_state ?? null,
            divergenceState: node.divergence_state ?? null,
            reconcileState: node.reconcile_state ?? null,
            proofState: node.proof_state ?? null,
            submissionState: node.submission_state ?? null,
            retireState: node.retire_state ?? null,
            claimEvidenceState: node.claim_evidence_state ?? null,
            baselineGate: node.baseline_state ?? null,
          },
          draggable: !interactionLocked,
        }
      }),
    [
      baselineMetricSnapshot,
      branchInsights,
      curveMetric,
      curveMode,
      currentWorkspaceBranch,
      currentWorkspaceLineage,
      headBranch,
      highlightIds,
      interactionLocked,
      layoutMap,
      memoryByBranch,
      metricObjectiveMap,
      nodeDisplayMode,
      viewMode,
      viewNodes,
      decisionPayloads,
      t,
    ]
  )

  const runtimeOverlayEnabled = false

  const agentGraph = React.useMemo(() => {
    if (!runtimeOverlayEnabled || questAgents.length === 0 || viewMode === 'stage' || atEventId) {
      return { nodes: [] as QuestFlowNode[], edges: [] as Edge[] }
    }
    const anchorLayout = viewMode === 'branch' ? layoutMap : branchLayoutMap
    const anchorIdSet = viewNodeIds
    const sortedAgents = [...questAgents].sort((a, b) =>
      String(a.created_at || '').localeCompare(String(b.created_at || ''))
    )
    const piAgent = sortedAgents.find(
      (agent) => {
        const agentId = String(agent.agent_id || '').trim().toLowerCase()
        const mention = String(agent.mention_label || '').trim().replace(/^@/, '').toLowerCase()
        return agentId === 'pi' || agentId.endsWith(':pi') || mention === 'pi'
      }
    )
    const piAgentInstanceId = piAgent?.instance_id ?? null
    const piAgentNodeId = piAgentInstanceId ? `agent:${piAgentInstanceId}` : null
    const groupCounts = new Map<string, number>()
    const nodes: QuestFlowNode[] = []
    const edges: Edge[] = []
    const fallbackBaseX = -GRID_X * 2
    sortedAgents.forEach((agent, index) => {
      const normalizedAgentId = String(agent.agent_id || '').trim().toLowerCase()
      const normalizedMention = String(agent.mention_label || '').trim().replace(/^@/, '').toLowerCase()
      const isPiAgent = normalizedAgentId === 'pi' || normalizedAgentId.endsWith(':pi') || normalizedMention === 'pi'
      const piAnchorBranch =
        headBranch && branchNodeByName.has(headBranch)
          ? headBranch
          : branchNodeByName.has('main')
            ? 'main'
            : null
      const displayName = resolveAgentDisplayName(agent) || agent.agent_id
      const mentionLabel = resolveAgentMentionLabel(agent)
      const branchName = isPiAgent
        ? agent.active_quest_branch ?? piAnchorBranch ?? null
        : agent.active_quest_branch ?? null
      const branchNode = branchName ? branchNodeByName.get(branchName) : null
      const piAnchorNode = isPiAgent && piAnchorBranch ? branchNodeByName.get(piAnchorBranch) : null
      const anchorId = piAnchorNode?.node_id ?? agent.active_quest_node_id ?? branchNode?.node_id ?? null
      const anchorPos = anchorId ? anchorLayout[anchorId] : null
      const groupKey = anchorId || branchName || 'unassigned'
      const order = groupCounts.get(groupKey) ?? 0
      groupCounts.set(groupKey, order + 1)
      const baseX = anchorPos ? anchorPos.x + DAGRE_NODE_WIDTH + 90 : fallbackBaseX
      const baseY = anchorPos ? anchorPos.y : index * 70
      const position = { x: baseX, y: baseY + order * 72 }
      const subtitle =
        mentionLabel && mentionLabel.replace(/^@/, '') !== displayName ? mentionLabel : branchName
      const status = agent.active_quest_stage_key ?? agent.status ?? undefined
      const agentNodeId = `agent:${agent.instance_id}`
      nodes.push({
        id: agentNodeId,
        type: 'agentNode',
        position,
        sourcePosition: FlowPosition.Right,
        targetPosition: FlowPosition.Left,
        data: {
          label: displayName,
          subtitle: subtitle || undefined,
          status,
          branchName,
          agentInstanceId: agent.instance_id,
          isAgent: true,
        },
        draggable: false,
      })
      if (anchorId && anchorIdSet.has(anchorId)) {
        const edgeStroke = isPiAgent ? edgePalette.stageStroke : edgePalette.agentStroke
        const edgeWidth = isPiAgent ? 2.4 : 1.5
        edges.push({
          id: `${anchorId}-${agentNodeId}`,
          source: anchorId,
          target: agentNodeId,
          type: 'smoothstep',
          style: isPiAgent
            ? { stroke: edgeStroke, strokeWidth: edgeWidth }
            : { stroke: edgeStroke, strokeWidth: edgeWidth, strokeDasharray: '4 4' },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: isPiAgent ? 14 : 12,
            height: isPiAgent ? 14 : 12,
            color: edgeStroke,
          },
        })
      }
      const createdByPi =
        Boolean(piAgentInstanceId) &&
        agent.created_by_agent_instance_id === piAgentInstanceId &&
        piAgentNodeId &&
        piAgentNodeId !== agentNodeId
      if (createdByPi) {
        edges.push({
          id: `${piAgentNodeId}-${agentNodeId}-created`,
          source: piAgentNodeId!,
          target: agentNodeId,
          type: 'smoothstep',
          style: { stroke: edgePalette.stageStroke, strokeWidth: 2.5 },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 14,
            height: 14,
            color: edgePalette.stageStroke,
          },
        })
      }
    })
    return { nodes, edges }
  }, [atEventId, branchLayoutMap, branchNodeByName, edgePalette.agentStroke, edgePalette.stageStroke, headBranch, layoutMap, questAgents, runtimeOverlayEnabled, viewMode, viewNodeIds])

  const overlayGraph = React.useMemo(() => {
    return { nodes: [] as QuestFlowNode[], edges: [] as Edge[] }
  }, [])

  const combinedNodes = React.useMemo(
    () => [...computedQuestNodes, ...agentGraph.nodes, ...overlayGraph.nodes],
    [agentGraph.nodes, computedQuestNodes, overlayGraph.nodes]
  )

  const computedEdges: Edge[] = React.useMemo(() => {
    const questEdges = layoutEdges.map((edge, index) => {
      const baseStyle = resolveEdgeStyle(edge.edge_type, edgePalette)
      const isHighlighted = highlightIds.has(edge.source) && highlightIds.has(edge.target)
      const isCurrentPathEdge =
        viewMode === 'branch' && currentPathNodeIds.has(edge.source) && currentPathNodeIds.has(edge.target)
      const style = isHighlighted
        ? {
            ...baseStyle,
            stroke: '#53b0ae',
            strokeWidth:
              typeof baseStyle.strokeWidth === 'number'
                ? Math.max(baseStyle.strokeWidth + 0.6, 2)
                : 2,
          }
        : isCurrentPathEdge
          ? {
              ...baseStyle,
              stroke: 'rgba(83, 176, 174, 0.82)',
              strokeWidth:
                typeof baseStyle.strokeWidth === 'number'
                  ? Math.max(baseStyle.strokeWidth + 0.3, 1.8)
                  : 1.8,
            }
          : baseStyle
      const color = String(style.stroke || 'var(--lab-border-strong)')
      return {
        id: edge.edge_id || `${edge.source}-${edge.target}-${index}`,
        source: edge.source,
        target: edge.target,
        type: 'smoothstep',
        style,
        data: {
          edge_id: edge.edge_id || `${edge.source}-${edge.target}-${index}`,
          edge_type: edge.edge_type || undefined,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 14,
          height: 14,
          color,
        },
      }
    })
    return [...questEdges, ...agentGraph.edges, ...overlayGraph.edges]
  }, [agentGraph.edges, currentPathNodeIds, edgePalette, highlightIds, layoutEdges, overlayGraph.edges, viewMode])

  React.useEffect(() => {
    const forceLayout = viewModeRef.current !== viewMode
    const autoLayoutChanged = lastAutoLayoutSignatureRef.current !== autoLayoutSignature
    lastAutoLayoutSignatureRef.current = autoLayoutSignature
    setNodes((prev) => {
      const prevMap = new Map(prev.map((node) => [node.id, node]))
      const next = combinedNodes.map((node) => {
        if (node.type === 'agentNode') return node
        const existing = prevMap.get(node.id)
        if (!existing || forceLayout || autoLayoutChanged) return node
        if (!explicitLayout[node.id]) {
          const existingPositionAbsolute = (existing as { positionAbsolute?: Position }).positionAbsolute
          return {
            ...node,
            position: existing.position,
            ...(existingPositionAbsolute ? { positionAbsolute: existingPositionAbsolute } : {}),
          } as QuestFlowNode
        }
        return node
      })
      return areNodesEquivalent(prev, next) ? prev : next
    })
    setEdges((prev) => (areEdgesEquivalent(prev as Edge[], computedEdges) ? prev : computedEdges))
  }, [autoLayoutSignature, combinedNodes, computedEdges, explicitLayout, setEdges, setNodes, viewMode])

  React.useEffect(() => {
    if (!nodesInitialized) return
    if (nodes.length <= 1) return
    if (nodes.some((node) => node.dragging)) return
    if (hasExplicitNodeLayout) return
    if (collisionLayoutSignatureRef.current === autoLayoutSignature) return

    const resolved = resolveNodeSpacingCollisions(nodes, {
      viewMode,
      getMeasuredSize: (id) => {
        const internal = flow.getInternalNode(id)
        if (!internal) return null
        return {
          width: internal.measured?.width ?? internal.width ?? DAGRE_NODE_WIDTH,
          height: internal.measured?.height ?? internal.height ?? DAGRE_NODE_HEIGHT,
        }
      },
    })

    collisionLayoutSignatureRef.current = autoLayoutSignature
    if (!areNodesEquivalent(nodes, resolved)) {
      setNodes(resolved)
    }
  }, [autoLayoutSignature, flow, hasExplicitNodeLayout, nodes, nodesInitialized, setNodes, viewMode])

  React.useEffect(() => {
    viewModeRef.current = viewMode
  }, [viewMode])

  React.useEffect(() => {
    if (nodes.length === 0) return
    const key = `${questId}:${viewMode}`
    if (fittedViewportRef.current.has(key)) return
    if (userMovedViewportRef.current) return
    try {
      markProgrammaticViewportMove(450)
      flow.fitView({ padding: 0.2, duration: 450 })
      fittedViewportRef.current.add(key)
    } catch {
      // ignore fit errors if flow not ready
    }
  }, [flow, markProgrammaticViewportMove, nodes.length, questId, viewMode])

  React.useEffect(() => {
    if (nodes.length === 0) return
    if (userMovedViewportRef.current) return
    if (typeof ResizeObserver === 'undefined') return
    const bounds = boundsRef.current
    if (!bounds) return

    let timer: number | null = null

    const runFit = () => {
      const rect = bounds.getBoundingClientRect()
      if (rect.width < 240 || rect.height < 180) {
        return
      }
      const signature = [
        questId,
        viewMode,
        nodes.length,
        Math.round(rect.width),
        Math.round(rect.height),
      ].join(':')
      if (resizeFitSignatureRef.current === signature) {
        return
      }
      resizeFitSignatureRef.current = signature
      try {
        markProgrammaticViewportMove(320)
        flow.fitView({ padding: viewMode === 'branch' ? 0.22 : 0.2, duration: 320 })
      } catch {
        // ignore fit errors if flow not ready
      }
    }

    const scheduleFit = () => {
      if (timer !== null) {
        window.clearTimeout(timer)
      }
      timer = window.setTimeout(runFit, 140)
    }

    scheduleFit()
    const observer = new ResizeObserver(() => {
      scheduleFit()
    })
    observer.observe(bounds)

    return () => {
      observer.disconnect()
      if (timer !== null) {
        window.clearTimeout(timer)
      }
    }
  }, [boundsRef, flow, markProgrammaticViewportMove, nodes.length, questId, viewMode])

  const questNodeCountRef = React.useRef<Record<string, number>>({})

  React.useEffect(() => {
    if (viewMode !== 'branch') return
    const key = `${questId}:${viewMode}`
    const previous = questNodeCountRef.current[key] ?? 0
    const current = computedQuestNodes.length
    questNodeCountRef.current[key] = current
    if (previous <= 0 || current <= previous) return
    if (userMovedViewportRef.current) return
    if (highlightNodeId || highlightBranch) return
    try {
      markProgrammaticViewportMove(320)
      flow.fitView({ padding: 0.22, duration: 320 })
    } catch {
      // ignore fit errors if flow not ready
    }
  }, [computedQuestNodes.length, flow, highlightBranch, highlightNodeId, markProgrammaticViewportMove, questId, viewMode])

  const lastFocusedKeyRef = React.useRef<string | null>(null)

  React.useEffect(() => {
    const focusKey = highlightNodeId
      ? `node:${highlightNodeId}`
      : highlightBranch
        ? `branch:${highlightBranch}`
        : null

    if (!focusKey) {
      lastFocusedKeyRef.current = null
      return
    }
    if (lastFocusedKeyRef.current === focusKey) return

    const targetId =
      highlightNodeId ||
      (highlightBranch ? nodes.find((node) => node.data.branchName === highlightBranch)?.id : null)
    if (!targetId) return
    const target = nodes.find((node) => node.id === targetId)
    if (!target) return
    const internal = flow.getInternalNode(targetId)
    const targetWidth = internal?.measured?.width ?? target.measured?.width ?? target.width ?? DAGRE_NODE_WIDTH
    const targetHeight = internal?.measured?.height ?? target.measured?.height ?? target.height ?? DAGRE_NODE_HEIGHT
    const centerX = target.position.x + targetWidth / 2
    const centerY = target.position.y + targetHeight / 2
    try {
      // Center the viewport, but do not force a zoom level.
      // Forcing zoom makes wheel zoom feel broken/locked.
      markProgrammaticViewportMove(500)
      flow.setCenter(centerX, centerY, { duration: 500 })
      lastFocusedKeyRef.current = focusKey
    } catch {
      // ignore focus errors if flow not ready
    }
  }, [flow, highlightBranch, highlightNodeId, markProgrammaticViewportMove, nodes])

  const sortBranches = React.useCallback(
    (nodes: LabQuestGraphNode[]) =>
      nodes
        .filter((node) => node.node_kind !== 'baseline_root' && node.node_kind !== 'placeholder')
        .sort((left, right) => {
          const leftName = String(left.branch_name || '')
          const rightName = String(right.branch_name || '')
          if (headBranch && leftName === headBranch && rightName !== headBranch) return -1
          if (headBranch && rightName === headBranch && leftName !== headBranch) return 1
          if (leftName === 'main' && rightName !== 'main') return -1
          if (rightName === 'main' && leftName !== 'main') return 1
          const leftInsight = left.branch_name ? branchInsights.get(left.branch_name) : null
          const rightInsight = right.branch_name ? branchInsights.get(right.branch_name) : null
          const leftTime = parseEventTime(leftInsight?.updatedAt || left.created_at)
          const rightTime = parseEventTime(rightInsight?.updatedAt || right.created_at)
          if (leftTime !== rightTime) return rightTime - leftTime
          return leftName.localeCompare(rightName)
        }),
    [branchInsights, headBranch]
  )

  const sortedBranchesAll = React.useMemo(() => sortBranches(branchNodesBase), [branchNodesBase, sortBranches])
  const sortedBranches = React.useMemo(() => sortBranches(branchNodes), [branchNodes, sortBranches])

  const recentEvents = eventsQuery.data?.items ?? []
  const papers = papersQuery.data?.items ?? []
  const latestWriteEvent = React.useMemo(
    () => recentEvents.find((event) => isWritingEvent(event)) ?? null,
    [recentEvents]
  )
  const writingBranch = latestWriteEvent?.branch_name || activeBranch || 'main'
  const filteredEvents = React.useMemo(() => {
    if (eventFilter === 'all') return recentEvents
    return recentEvents.filter((event) => {
      if (eventFilter === 'error') return isErrorEvent(event)
      if (eventFilter === 'decision') return isDecisionEvent(event)
      if (eventFilter === 'activity') {
        return (
          event.event_type === 'artifact.recorded' ||
          isBaselineEvent(event) ||
          isIdeaEvent(event) ||
          isExperimentEvent(event) ||
          isWritingEvent(event) ||
          isConversationEvent(event) ||
          isToolLifecycleEvent(event)
        )
      }
      return true
    })
  }, [eventFilter, recentEvents])

  const groupedFilteredEvents = React.useMemo(
    () => groupStageEvents(filteredEvents),
    [filteredEvents]
  )

  const piQaPairs = React.useMemo(() => {
    const sourceEvents =
      piQaEventsQuery.data?.items && piQaEventsQuery.data.items.length
        ? piQaEventsQuery.data.items
        : recentEvents.filter(
            (event) =>
              event.event_type === 'conversation.message' || event.event_type === 'interaction.reply_received'
          )

    const ordered = [...sourceEvents].sort((a, b) => {
      const aTime = a.created_at ? new Date(a.created_at).getTime() : 0
      const bTime = b.created_at ? new Date(b.created_at).getTime() : 0
      return aTime - bTime
    })

    const pairs: Array<{
      questionId: string
      question: string | null
      answer: string | null
      branchName: string | null
      updatedAt: string | null
    }> = []
    let pendingQuestion: {
      questionId: string
      question: string | null
      branchName: string | null
      updatedAt: string | null
    } | null = null

    ordered.forEach((event) => {
      const rawPayload = event.payload_json as Record<string, unknown> | null
      const payload = extractEventPayload(rawPayload)
      const rawEvent = asRecord(rawPayload?.event)
      const role = String(rawEvent?.role || '').trim().toLowerCase()
      const content =
        event.reply_to_pi ||
        event.payload_summary ||
        asString(payload?.content) ||
        asString(rawEvent?.content) ||
        null
      if (!content) return

      if (event.event_type === 'conversation.message' && role === 'user') {
        pendingQuestion = {
          questionId: event.event_id,
          question: content,
          branchName: event.branch_name || null,
          updatedAt: event.created_at || null,
        }
        return
      }

      if (!pendingQuestion) {
        pairs.push({
          questionId: event.event_id,
          question: null,
          answer: content,
          branchName: event.branch_name || null,
          updatedAt: event.created_at || null,
        })
        return
      }

      pairs.push({
        questionId: pendingQuestion.questionId,
        question: pendingQuestion.question,
        answer: content,
        branchName: pendingQuestion.branchName || event.branch_name || null,
        updatedAt: event.created_at || pendingQuestion.updatedAt,
      })
      pendingQuestion = null
    })

    if (pendingQuestion) {
      pairs.push({
        questionId: pendingQuestion.questionId,
        question: pendingQuestion.question,
        answer: null,
        branchName: pendingQuestion.branchName,
        updatedAt: pendingQuestion.updatedAt,
      })
    }

    return pairs.sort((a, b) => {
      const aTime = a.updatedAt ? new Date(a.updatedAt).getTime() : 0
      const bTime = b.updatedAt ? new Date(b.updatedAt).getTime() : 0
      return bTime - aTime
    })
  }, [piQaEventsQuery.data?.items, recentEvents])

  const selectEventFilter = React.useCallback((filter: EventFilterMode) => {
    setEventFilter(filter)
  }, [])

  const openPaperTex = React.useCallback(
    (paper: LabPaper) => {
      const latest = paper.latest_version
      const fileId = latest?.main_tex_file_id ?? null
      const rawPath = latest?.main_tex_path ?? null
      let node = fileId ? findNode(fileId) : null
      if (!node && rawPath) {
        const normalized = rawPath.replace(/^\/FILES\//i, '')
        node = findNodeByPath(normalized)
      }
      if (!node) {
        return
      }
      openFileInTab(node, { customData: { projectId } })
    },
    [findNode, findNodeByPath, openFileInTab, projectId]
  )

  const applySelection = React.useCallback(
    (selection: (LabQuestSelectionContext & { label?: string | null; summary?: string | null }) | null) => {
      setSelectionStore(selection)
      onSelectionChange?.(selection)
    },
    [onSelectionChange, setSelectionStore]
  )

  const combinedNodeLookup = React.useMemo(() => {
    const lookup = new Map<string, QuestFlowNode>()
    combinedNodes.forEach((node) => {
      lookup.set(node.id, node)
    })
    return lookup
  }, [combinedNodes])

  const positionHoverCard = React.useCallback(
    (event: React.MouseEvent, draft: Omit<GraphHoverCardState, 'x' | 'y'>) => {
      if (hoverClearTimerRef.current) {
        window.clearTimeout(hoverClearTimerRef.current)
        hoverClearTimerRef.current = null
      }
      const bounds = boundsRef.current?.getBoundingClientRect()
      if (!bounds) {
        setHoverCard({ ...draft, x: 16, y: 16 })
        return
      }
      const cardWidth = 320
      const cardHeight = Math.min(240, 92 + draft.lines.length * 24)
      const relativeX = event.clientX - bounds.left + 14
      const relativeY = event.clientY - bounds.top + 14
      setHoverCard({
        ...draft,
        x: clamp(relativeX, 16, Math.max(16, bounds.width - cardWidth - 16)),
        y: clamp(relativeY, 16, Math.max(16, bounds.height - cardHeight - 16)),
      })
    },
    []
  )

  const clearHoverCard = React.useCallback(() => {
    if (hoverClearTimerRef.current) {
      window.clearTimeout(hoverClearTimerRef.current)
    }
    hoverClearTimerRef.current = window.setTimeout(() => {
      setHoverCard(null)
      hoverClearTimerRef.current = null
    }, 90)
  }, [])

  const buildNodeHoverCard = React.useCallback(
    (node: Node<QuestFlowNodeData>): Omit<GraphHoverCardState, 'x' | 'y'> | null => {
      const data = node.data as AgentNodeData | QuestNodeData
      if ((data as AgentNodeData | QuestNodeData)?.isAgent) {
        const agentData = data as AgentNodeData
        const agent = questAgents.find((item) => item.instance_id === agentData.agentInstanceId) ?? null
        return {
          title: agentData.label,
          subtitle: truncateGraphText(resolveAgentMentionLabel(agent || { mention_label: agentData.subtitle } as any) || agentData.subtitle || ''),
          badge: t('quest_hover_badge_agent', undefined, 'Agent'),
          tone: 'neutral',
          lines: [
            {
              label: t('quest_hover_line_status', undefined, 'Status'),
              value: formatStateLabel(agent?.status || agentData.status || 'idle'),
            },
            ...(agentData.branchName
              ? [
                  {
                    label: t('quest_hover_line_branch', undefined, 'Branch'),
                    value: agentData.branchName,
                  },
                ]
              : []),
            ...(agent?.active_quest_stage_key
              ? [
                  {
                    label: t('quest_hover_line_stage', undefined, 'Stage'),
                    value: formatStateLabel(agent.active_quest_stage_key),
                  },
                ]
              : []),
          ],
          footer: t('quest_hover_footer_click_agent', undefined, 'Click to inspect agent'),
        }
      }
      const questData = data as QuestNodeData
      const positive =
        isPositiveDeltaLabel(questData.deltaLabel) ||
        ['good', 'support', 'go'].includes(String(questData.verdict || '').toLowerCase())
      const lines: GraphHoverLine[] = []
      if (questData.nowDoing) {
        lines.push({
          label: t('quest_hover_line_now', undefined, 'Now'),
          value: truncateGraphText(questData.nowDoing),
        })
      }
      if (questData.decisionReason) {
        lines.push({
          label: t('quest_hover_line_decision', undefined, 'Decision'),
          value: truncateGraphText(questData.decisionReason),
        })
      }
      if (questData.evidenceStatus) {
        lines.push({
          label: t('quest_hover_line_evidence', undefined, 'Evidence'),
          value: formatStateLabel(questData.evidenceStatus),
        })
      }
      if (questData.deltaLabel || questData.metric) {
        lines.push({
          label: t('quest_hover_line_metric', undefined, 'Metric'),
          value: questData.deltaLabel || questData.metric || t('quest_hover_metric_pending', undefined, 'Pending'),
        })
      }
      if (questData.memoryLabel) {
        lines.push({
          label: t('quest_hover_line_memory', undefined, 'Memory'),
          value: questData.memoryLabel,
        })
      }
      if (questData.memorySummary) {
        lines.push({
          label: t('quest_hover_line_learning', undefined, 'Learned'),
          value: truncateGraphText(questData.memorySummary, 72),
        })
      }
      if (questData.worktreeRelPath) {
        lines.push({
          label: t('quest_hover_line_worktree', undefined, 'Worktree'),
          value: truncateGraphText(questData.worktreeRelPath, 56),
        })
      }
      if (questData.status) {
        lines.push({
          label: t('quest_hover_line_updated', undefined, 'Updated'),
          value: truncateGraphText(questData.status, 48),
        })
      }
      return {
        title: questData.label,
        subtitle: truncateGraphText(
          questData.subtitle ||
            questData.summary ||
            questData.memorySummary ||
            questData.stageTitle ||
            questData.branchName ||
            ''
        ),
        badge: positive
          ? t('quest_hover_badge_promising', undefined, 'Promising')
          : questData.isHead
            ? t('quest_hover_badge_head', undefined, 'Head')
            : questData.isRoot
              ? t('quest_hover_badge_baseline', undefined, 'Baseline')
              : questData.isEvent
                ? t('quest_hover_badge_event', undefined, 'Event')
                : formatStateLabel(questData.branchClass || questData.stageLabel || 'branch'),
        tone: positive ? 'positive' : 'neutral',
        lines: lines.slice(0, 5),
        footer: t('quest_hover_footer_click_branch', undefined, 'Click to inspect this route'),
      }
    },
    [questAgents, t]
  )

  const handleNodeMouseEnter = React.useCallback(
    (event: React.MouseEvent, node: Node<QuestFlowNodeData>) => {
      const card = buildNodeHoverCard(node)
      if (!card) return
      positionHoverCard(event, card)
    },
    [buildNodeHoverCard, positionHoverCard]
  )

  const handleEdgeMouseEnter = React.useCallback(
    (event: React.MouseEvent, edge: Edge) => {
      const sourceLabel = truncateGraphText(
        String((combinedNodeLookup.get(edge.source)?.data as QuestFlowNodeData | undefined)?.label || edge.source),
        36
      )
      const targetLabel = truncateGraphText(
        String((combinedNodeLookup.get(edge.target)?.data as QuestFlowNodeData | undefined)?.label || edge.target),
        36
      )
      positionHoverCard(event, {
        title: `${sourceLabel} → ${targetLabel}`,
        subtitle: t('quest_hover_edge_truth', undefined, 'Truth edge from the worktree graph'),
        badge: t('quest_hover_badge_truth', undefined, 'Truth'),
        tone: 'neutral',
        lines: [
          {
            label: t('quest_hover_line_edge_type', undefined, 'Type'),
            value: formatStateLabel(
              String((edge.data as Record<string, unknown> | undefined)?.edge_type || edge.type || 'link')
            ),
          },
          {
            label: t('quest_hover_line_relation', undefined, 'Relation'),
            value: `${sourceLabel} → ${targetLabel}`,
          },
        ],
        footer: t('quest_hover_footer_truth', undefined, 'Worktree truth relationship'),
      })
    },
    [combinedNodeLookup, positionHoverCard, t]
  )

  const handleNodeClick = React.useCallback(
    (_: React.MouseEvent, node: Node<QuestFlowNodeData>) => {
      const data = node.data as AgentNodeData | QuestNodeData
      if ((data as AgentNodeData | QuestNodeData)?.isAgent) {
        const agentData = data as AgentNodeData
        const selection = buildSelectionContext(questId, {
          selectionType: 'agent_node',
          selectionRef: agentData.agentInstanceId || node.id,
          branchName: agentData.branchName ?? null,
          agentInstanceId: agentData.agentInstanceId ?? null,
          label: agentData.label,
          summary: agentData.status ?? null,
        })
        applySelection(selection)
        return
      }
      if (viewMode === 'event') {
        const eventData = data as QuestNodeData
        applySelection(
          buildSelectionContext(questId, {
            selectionType: 'event_node',
            selectionRef: node.id,
            branchName: eventData.branchName ?? null,
            stageKey: eventData.stageKey ?? null,
            traceNodeId: node.id,
            label: eventData.label,
            summary: eventData.summary ?? null,
          })
        )
        if (onEventSelect) {
          onEventSelect(node.id, eventData.branchName || undefined)
        }
        return
      }
      if (viewMode === 'stage') {
        const stageData = data as QuestNodeData
        const selection = buildSelectionContext(questId, {
          selectionType: 'stage_node',
          selectionRef: node.id,
          branchName: stageData.branchName ?? null,
          branchNo: stageData.branchNo ?? null,
          parentBranch: stageData.parentBranch ?? null,
          foundationRef: stageData.foundationRef ?? null,
          foundationReason: stageData.foundationReason ?? null,
          foundationLabel: stageData.foundationLabel ?? null,
          ideaTitle: stageData.ideaTitle ?? null,
          stageKey: stageData.stageKey ?? null,
          worktreeRelPath: stageData.worktreeRelPath ?? null,
          traceNodeId: node.id,
          label: stageData.stageTitle || stageData.label,
          summary: stageData.summary ?? null,
          compareBase: stageData.compareBase ?? null,
          compareHead: stageData.compareHead ?? null,
          scopePaths: stageData.scopePaths ?? null,
          nodeKind: stageData.nodeKind ?? null,
          baselineGate: stageData.baselineGate ?? null,
        })
        applySelection(selection)
        if (stageData.nodeKind !== 'placeholder' && onStageOpen) {
          onStageOpen(selection)
        }
        return
      }
      const questData = data as QuestNodeData
      const preferStageNode =
        questData.nodeKind !== 'baseline_root' &&
        questData.nodeKind !== 'placeholder' &&
        shouldOpenCanonicalStage(questData.stageKey)
      const selectionType =
        preferStageNode
          ? 'stage_node'
          : questData.nodeKind === 'baseline_root'
            ? 'baseline_node'
            : questData.nodeKind === 'placeholder'
              ? 'workflow_placeholder'
              : 'branch_node'
      if (questData.branchName) {
        const selectionRef =
          selectionType === 'branch_node'
            ? questData.branchName
            : selectionType === 'stage_node'
              ? `stage:${questData.branchName}:${questData.stageKey}`
              : node.id
        const selection = buildSelectionContext(questId, {
          selectionType,
          selectionRef,
          branchName: questData.branchName,
          branchNo: questData.branchNo ?? null,
          parentBranch: questData.parentBranch ?? null,
          foundationRef: questData.foundationRef ?? null,
          foundationReason: questData.foundationReason ?? null,
          foundationLabel: questData.foundationLabel ?? null,
          ideaTitle: questData.ideaTitle ?? null,
          stageKey: questData.stageKey ?? null,
          worktreeRelPath: questData.worktreeRelPath ?? null,
          traceNodeId: node.id,
          label: questData.label,
          summary: questData.summary ?? questData.nowDoing ?? null,
          compareBase: questData.compareBase ?? null,
          compareHead: questData.compareHead ?? null,
          scopePaths: questData.scopePaths ?? null,
          nodeKind: questData.nodeKind ?? null,
          baselineGate: questData.baselineGate ?? null,
        })
        applySelection(selection)
        if (selectionType !== 'workflow_placeholder' && onStageOpen) {
          onStageOpen(selection)
        }
      }
      if (selectionType === 'branch_node' && questData.branchName && onBranchSelect) {
        onBranchSelect(questData.branchName as string)
      }
    },
    [applySelection, onBranchSelect, onEventSelect, onStageOpen, questId, viewMode]
  )

  const handleEdgeClick = React.useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      const edgeId =
        typeof edge.data?.edge_id === 'string'
          ? edge.data.edge_id
          : typeof edge.id === 'string'
            ? edge.id
            : ''
      if (!edgeId) return
      const sourceNode = viewNodes.find((node) => node.node_id === edge.source) ?? null
      const targetNode = viewNodes.find((node) => node.node_id === edge.target) ?? null
      applySelection(
        buildSelectionContext(questId, {
          selectionType: 'edge',
          selectionRef: edgeId,
          branchName: targetNode?.branch_name ?? sourceNode?.branch_name ?? null,
          edgeId,
          worktreeRelPath: targetNode?.worktree_rel_path ?? sourceNode?.worktree_rel_path ?? null,
          label: `${sourceNode?.branch_name || edge.source} → ${targetNode?.branch_name || edge.target}`,
          summary: typeof edge.data?.edge_type === 'string' ? edge.data.edge_type : null,
        })
      )
    },
    [applySelection, questId, viewNodes]
  )

  const handleDragStop = React.useCallback(
    (_: React.MouseEvent, node: Node<QuestFlowNodeData>) => {
      if (interactionLocked) return
      if ((node.data as AgentNodeData | QuestNodeData)?.isAgent) return
      setLayoutOverride((prev) => ({
        ...prev,
        [node.id]: { x: node.position.x, y: node.position.y },
      }))
    },
    [interactionLocked]
  )

  const handleViewportMoveStart = React.useCallback(() => {
    if (programmaticViewportMoveRef.current) return
    userMovedViewportRef.current = true
  }, [])

  const handleRelayoutCanvas = React.useCallback(() => {
    if (interactionLocked) return
    setLayoutOverride({})
    userMovedViewportRef.current = false
    lastAutoLayoutSignatureRef.current = null
    collisionLayoutSignatureRef.current = null
    resizeFitSignatureRef.current = null
    const preferences = buildCanvasPreferences({
      curveMetric,
      curveMode,
      nodeDisplayMode,
      showAnalysis,
      pathFilterMode,
    })
    const nextLayout: QuestLayoutJson = {
      ...(layoutJson ?? {}),
      preferences,
      [viewMode]: {},
    }
    layoutMutation.mutate(nextLayout, {
      onSuccess: () => {
        const key = `${questId}:${viewMode}`
        fittedViewportRef.current.delete(key)
        try {
          markProgrammaticViewportMove(320)
          flow.fitView({ padding: viewMode === 'branch' ? 0.22 : 0.2, duration: 320 })
        } catch {
          // ignore fit errors if flow not ready
        }
      },
    })
  }, [
    curveMetric,
    curveMode,
    flow,
    interactionLocked,
    layoutJson,
    layoutMutation,
    markProgrammaticViewportMove,
    nodeDisplayMode,
    pathFilterMode,
    questId,
    showAnalysis,
    viewMode,
  ])

  React.useEffect(() => {
    if (interactionLocked) return
    if (!canvasStateHydratedRef.current) return
    if (saveTimeoutRef.current) {
      window.clearTimeout(saveTimeoutRef.current)
    }
    saveTimeoutRef.current = window.setTimeout(() => {
      const currentLayout = resolveLayoutMap(layoutJson, viewMode)
      const preferences = buildCanvasPreferences({
        curveMetric,
        curveMode,
        nodeDisplayMode,
        showAnalysis,
        pathFilterMode,
      })
      const nextLayout: QuestLayoutJson = {
        ...(layoutJson ?? {}),
        preferences,
        [viewMode]: { ...currentLayout, ...layoutOverride },
      }
      if (JSON.stringify(nextLayout) === JSON.stringify(layoutJson ?? {})) {
        return
      }
      layoutMutation.mutate(nextLayout)
    }, 800)
    return () => {
      if (saveTimeoutRef.current) {
        window.clearTimeout(saveTimeoutRef.current)
      }
    }
  }, [
    curveMetric,
    curveMode,
    interactionLocked,
    layoutJson,
    layoutMutation,
    layoutOverride,
    nodeDisplayMode,
    pathFilterMode,
    showAnalysis,
    viewMode,
  ])

  const baselineGateState = React.useMemo(() => {
    const fromGovernance = String(graphQuery.data?.governance_vm?.governance?.formalBaselineState || '').trim().toLowerCase()
    if (fromGovernance === 'confirmed' || fromGovernance === 'waived' || fromGovernance === 'pending') {
      return fromGovernance
    }
    const baselineNode = branchNodes.find((node) => node.node_kind === 'baseline_root')
    const fromNode = String(baselineNode?.baseline_state || '').trim().toLowerCase()
    if (fromNode === 'confirmed' || fromNode === 'waived' || fromNode === 'pending') {
      return fromNode
    }
    return 'pending'
  }, [branchNodes, graphQuery.data?.governance_vm?.governance?.formalBaselineState])
  const baselineReady = baselineGateState === 'confirmed' || baselineGateState === 'waived'
  const visibleBranchNameSet = React.useMemo(
    () =>
      new Set(
        sortedBranches
          .map((node) => String(node.branch_name || '').trim())
          .filter((branchName): branchName is string => Boolean(branchName))
      ),
    [sortedBranches]
  )
  const selectedBranchName =
    (activeBranch && (pathFilterMode !== 'current' || visibleBranchNameSet.has(activeBranch)) ? activeBranch : null) ||
    (headBranch && visibleBranchNameSet.has(headBranch) ? headBranch : null) ||
    sortedBranches.find((node) => node.node_kind !== 'baseline_root' && node.node_kind !== 'placeholder')?.branch_name ||
    null
  const selectedBranchInsight = selectedBranchName ? branchInsights.get(selectedBranchName) ?? null : null
  const selectedBranchHasDecision = React.useMemo(() => {
    const targetBranch = selectedBranchName || 'main'
    return decisionLogItems.some((item) => (item.branch_name || 'main') === targetBranch)
  }, [decisionLogItems, selectedBranchName])
  const processStatusLabelMap = React.useMemo<Record<PipelineStepStatus, string>>(
    () => ({
      done: t('quest_process_status_done', undefined, 'Done'),
      active: t('quest_process_status_active', undefined, 'Active'),
      pending: t('quest_process_status_pending', undefined, 'Pending'),
    }),
    [t]
  )
  const selectedBranchPipelineSteps = React.useMemo(() => {
    const stageRank = selectedBranchInsight ? resolveStageRank(selectedBranchInsight.stage) : -1
    const analysisState = String(selectedBranchInsight?.workflowState?.analysis_state || '').trim().toLowerCase()
    const writingState = String(selectedBranchInsight?.workflowState?.writing_state || '').trim().toLowerCase()
    const workflowReason = String(selectedBranchInsight?.workflowState?.status_reason || '').trim()
    const statusForStage = (target: BranchStage, dependsOnReady = false): PipelineStepStatus => {
      const targetRank = resolveStageRank(target)
      if (stageRank > targetRank) return 'done'
      if (stageRank === targetRank) return 'active'
      if (dependsOnReady && baselineReady) return 'pending'
      return 'pending'
    }
    const finalizeStatus: PipelineStepStatus =
      selectedBranchInsight?.completed || stageRank >= resolveStageRank('finalize')
        ? stageRank > resolveStageRank('finalize') || selectedBranchInsight?.completed
          ? 'done'
          : 'active'
        : selectedBranchHasDecision && stageRank >= resolveStageRank('write')
          ? 'pending'
          : 'pending'

    return [
      {
        key: 'baseline',
        status:
          baselineGateState === 'pending'
            ? 'active'
            : stageRank > resolveStageRank('baseline')
              ? 'done'
              : 'active',
        label: t('quest_process_step_baseline', undefined, 'Baseline'),
        description: t(
          'quest_process_step_baseline_desc',
          undefined,
          baselineGateState === 'waived'
            ? 'Baseline was explicitly waived for this route.'
            : 'Bind baseline, define metric objectives, and confirm the gate.'
        ),
      },
      {
        key: 'idea',
        status: statusForStage('idea', true),
        label: t('quest_process_step_idea', undefined, 'Idea'),
        description: t(
          'quest_process_step_idea_desc',
          undefined,
          'Formulate and refine the branch hypothesis.'
        ),
      },
      {
        key: 'experiment',
        status: statusForStage('experiment'),
        label: t('quest_process_step_experiment', undefined, 'Experiment'),
        description: t(
          'quest_process_step_experiment_desc',
          undefined,
          'Run experiments and submit metric results.'
        ),
      },
      {
        key: 'analysis',
        status: statusForStage('analysis-campaign'),
        label: t('quest_process_step_outcome', undefined, 'Analysis'),
        description: t(
          'quest_process_step_outcome_desc',
          undefined,
          workflowReason && (analysisState === 'active' || analysisState === 'completed' || writingState === 'blocked_by_analysis')
            ? workflowReason
            : 'Run follow-up analyses and verify claims.'
        ),
      },
      {
        key: 'write',
        status: statusForStage('write'),
        label: t('quest_process_step_writing', undefined, 'Writing'),
        description: t(
          'quest_process_step_writing_desc',
          undefined,
          workflowReason && (writingState === 'blocked_by_analysis' || writingState === 'active' || writingState === 'ready')
            ? workflowReason
            : 'Draft and finalize paper artifacts.'
        ),
      },
      {
        key: 'finalize',
        status: finalizeStatus,
        label: t('quest_process_step_writing', undefined, 'Finalize'),
        description: t(
          'quest_process_step_writing_desc',
          undefined,
          'Freeze the final claim set, summary, and graph exports.'
        ),
      },
    ] as Array<{
      key: string
      status: PipelineStepStatus
      label: string
      description: string
    }>
  }, [baselineGateState, baselineReady, selectedBranchHasDecision, selectedBranchInsight, t])
  const selectedBranchNode = selectedBranchName
    ? sortedBranchesAll.find((node) => node.branch_name === selectedBranchName) || null
    : null
  const recommendedBranchName = React.useMemo(() => {
    const candidates = sortedBranchesAll
      .map((node) => {
        const branchName = node.branch_name || ''
        if (!branchName) return null
        const insight = branchInsights.get(branchName)
        const stageRank = insight ? resolveStageRank(insight.stage) : 0
        const completedBonus = insight?.completed ? 3 : 0
        const writingBonus = insight?.writingActive ? 2 : insight?.writingEligible ? 1 : 0
        const updatedAt = insight?.updatedAt ? parseEventTime(insight.updatedAt) : parseEventTime(node.created_at)
        return {
          branchName,
          score: stageRank * 1_000_000_000 + completedBonus * 10_000_000 + writingBonus * 1_000_000 + updatedAt,
          updatedAt,
        }
      })
      .filter((item): item is { branchName: string; score: number; updatedAt: number } => Boolean(item))
      .sort((a, b) => {
        if (a.score !== b.score) return b.score - a.score
        return b.updatedAt - a.updatedAt
      })
    if (!candidates.length) return null
    return candidates[0].branchName
  }, [branchInsights, sortedBranchesAll])
  const recommendedPath = React.useMemo(() => {
    if (!recommendedBranchName) return []
    const nodeByBranch = new Map<string, LabQuestGraphNode>()
    sortedBranchesAll.forEach((node) => {
      if (node.branch_name) nodeByBranch.set(node.branch_name, node)
    })
    const path: string[] = []
    const seen = new Set<string>()
    let current: string | null = recommendedBranchName
    while (current && !seen.has(current)) {
      seen.add(current)
      path.push(current)
      const parentBranch: string | null = nodeByBranch.get(current)?.parent_branch || null
      current = parentBranch
    }
    return path.reverse()
  }, [recommendedBranchName, sortedBranchesAll])
  const selectedBranchCurves = selectedBranchNode ? resolveNodeMetricCurves(selectedBranchNode) : null
  const selectedBranchMetricTables = React.useMemo(() => {
    const keys = new Set<string>()
    metricCatalog.forEach((item) => {
      if (item.key) keys.add(item.key)
    })
    Object.keys(selectedBranchCurves || {}).forEach((key) => keys.add(key))

    const toPoints = (seriesRaw: unknown) => {
      if (!Array.isArray(seriesRaw)) return []
      const points: Array<{
        seq: number
        ts: string | null
        runId: string | null
        eventId: string | null
        value: number
        isSota: boolean
      }> = []
      seriesRaw.forEach((item, index) => {
        if (typeof item === 'number' && Number.isFinite(item)) {
          points.push({
            seq: index + 1,
            ts: null,
            runId: null,
            eventId: null,
            value: Number(item),
            isSota: curveMode === 'sota',
          })
          return
        }
        if (!item || typeof item !== 'object' || Array.isArray(item)) return
        const record = item as Record<string, unknown>
        const valueRaw = record.value
        if (typeof valueRaw !== 'number' || !Number.isFinite(valueRaw)) return
        const seqRaw = record.seq
        const seq =
          typeof seqRaw === 'number' && Number.isFinite(seqRaw) && seqRaw > 0
            ? Math.floor(seqRaw)
            : index + 1
        const ts = typeof record.ts === 'string' && record.ts.trim() ? record.ts.trim() : null
        const runId = typeof record.run_id === 'string' && record.run_id.trim() ? record.run_id.trim() : null
        const eventId = typeof record.event_id === 'string' && record.event_id.trim() ? record.event_id.trim() : null
        points.push({
          seq,
          ts,
          runId,
          eventId,
          value: Number(valueRaw),
          isSota: record.is_sota === true,
        })
      })
      return points
    }

    const tables = [...keys]
      .map((key) => {
        const objective = metricObjectiveMap.get(key)
        const curve = selectedBranchCurves?.[key]
        const activeSeries = curveMode === 'full' ? curve?.full : curve?.sota
        const points = toPoints(activeSeries)
        if (!points.length && selectedBranchNode) {
          const fallbackMetric = pickMetricValue(
            selectedBranchNode.metrics_json as Record<string, unknown> | null,
            key
          )
          if (fallbackMetric && fallbackMetric.key === key) {
            points.push({
              seq: 1,
              ts: selectedBranchNode.created_at || null,
              runId: null,
              eventId: null,
              value: fallbackMetric.value,
              isSota: true,
            })
          }
        }
        if (!points.length) return null
        const label = String(objective?.label || curve?.label || key).trim() || key
        const directionText = String(objective?.direction || curve?.direction || '').trim().toLowerCase()
        const direction =
          directionText === 'higher' || directionText === 'lower'
            ? (directionText as 'higher' | 'lower')
            : null
        const importance =
          typeof objective?.importance === 'number' && Number.isFinite(objective.importance)
            ? Number(objective.importance)
            : typeof curve?.importance === 'number' && Number.isFinite(curve.importance)
              ? Number(curve.importance)
              : null
        const unit = String(objective?.unit || '').trim() || null
        const target =
          typeof objective?.target === 'number' && Number.isFinite(objective.target)
            ? Number(objective.target)
            : null
        const sortedPoints = [...points].sort((a, b) => a.seq - b.seq)
        const clipped = sortedPoints.length > 60 ? sortedPoints.slice(-60) : sortedPoints
        return {
          key,
          label,
          direction,
          importance,
          unit,
          target,
          points: clipped,
          totalPoints: sortedPoints.length,
        }
      })
      .filter(
        (
          item
        ): item is {
          key: string
          label: string
          direction: 'higher' | 'lower' | null
          importance: number | null
          unit: string | null
          target: number | null
          points: Array<{
            seq: number
            ts: string | null
            runId: string | null
            eventId: string | null
            value: number
            isSota: boolean
          }>
          totalPoints: number
        } => Boolean(item)
      )

    tables.sort((a, b) => {
      const aImportance = a.importance ?? 0
      const bImportance = b.importance ?? 0
      if (aImportance !== bImportance) return bImportance - aImportance
      return a.key.localeCompare(b.key)
    })
    return tables
  }, [curveMode, metricCatalog, metricObjectiveMap, selectedBranchCurves, selectedBranchNode])
  const curveModeLabel =
    curveMode === 'sota'
      ? t('quest_curve_mode_sota', undefined, 'SoTA only')
      : t('quest_curve_mode_full', undefined, 'Full trace')
  const graphToolbar =
    viewMode === 'branch' ? (
      <div className="lab-quest-graph-toolbar__group nowheel nopan">
        <div className="lab-quest-graph-toolbar__segmented" aria-label="Canvas node display mode">
          <Button
            type="button"
            size="sm"
            variant={nodeDisplayMode === 'summary' ? 'secondary' : 'ghost'}
            onClick={() => setNodeDisplayMode('summary')}
          >
            {t('quest_node_display_summary', undefined, 'Summary')}
          </Button>
          <Button
            type="button"
            size="sm"
            variant={nodeDisplayMode === 'metric' ? 'secondary' : 'ghost'}
            onClick={() => setNodeDisplayMode('metric')}
          >
            {t('quest_node_display_metric', undefined, 'Metric')}
          </Button>
        </div>
        {nodeDisplayMode === 'metric' ? (
          <div className="lab-quest-graph-toolbar__controls">
            <span className="lab-quest-graph-toolbar__caption">
              {t('quest_curve_metric_label', undefined, 'Focus metric')}
            </span>
            <select
              className="lab-quest-time-filter"
              value={curveMetric}
              onChange={(event) => setCurveMetric(event.target.value)}
            >
              {!metricCatalog.length ? (
                <option value="">
                  {t('quest_curve_metric_unavailable', undefined, 'No metric available')}
                </option>
              ) : null}
              {metricCatalog.map((metric) => (
                <option key={metric.key} value={metric.key}>
                  {metric.label || metric.key}
                </option>
              ))}
            </select>
            <span className="lab-quest-graph-toolbar__caption">{curveModeLabel}</span>
          </div>
        ) : null}
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={handleRelayoutCanvas}
          disabled={interactionLocked || layoutMutation.isPending}
          title={t('quest_canvas_relayout_title', undefined, 'Recompute the canvas layout')}
        >
          <RefreshCw size={14} />
          {t('quest_canvas_relayout', undefined, 'Relayout')}
        </Button>
      </div>
    ) : null

  return (
    <div
      ref={boundsRef}
      className={cn('lab-quest-canvas', minimalChrome && 'lab-quest-canvas--minimal')}
    >
      <GraphViewport
        nodes={nodes}
        edges={edgesState}
        readOnly={interactionLocked}
        onNodeClick={handleNodeClick}
        onNodeMouseEnter={handleNodeMouseEnter}
        onNodeMouseLeave={() => clearHoverCard()}
        onEdgeClick={handleEdgeClick}
        onEdgeMouseEnter={handleEdgeMouseEnter}
        onEdgeMouseLeave={() => clearHoverCard()}
        onNodeDragStop={handleDragStop}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onViewportMoveStart={handleViewportMoveStart}
        isLoading={graphQuery.isLoading || (branchProjectionPending && nodes.length === 0)}
        isError={graphQuery.isError}
        statusMessage={branchProjectionStatusMessage}
        statusProgress={branchProjectionProgress}
        showStatusOverlay={branchProjectionPending && nodes.length > 0}
        hoverCard={hoverCard}
        toolbar={graphToolbar}
        minimalChrome={minimalChrome}
      />

      {showFloatingPanels ? (
        <FloatingPanel
          boundsRef={boundsRef}
          title="Branches"
          icon={<GitBranch size={16} />}
          state={branchesPanel}
          zIndex={panelZ.branches}
          onChange={setBranchesPanel}
          onActivate={() => bringToFront('branches')}
        >
        <div className="lab-quest-panel__header">
          <div>
            <div className="lab-quest-panel__subtitle">
              {pathFilterMode === 'all' ? `${branchNodes.length} total` : `${branchNodes.length}/${branchNodesBase.length} shown`}
            </div>
          </div>
          <button
            type="button"
            className="lab-quest-panel__toggle"
            onClick={() => {
              analysisVisibilityTouchedRef.current = true
              setShowAnalysis((prev) => !prev)
            }}
          >
            {showAnalysis ? 'Hide analysis' : 'Show analysis'}
          </button>
        </div>
        {viewMode === 'stage' ? (
          <div className="mt-2 text-xs text-[var(--lab-text-secondary)]">
            Branch filters are disabled in stage view.
          </div>
        ) : (
          <>
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--lab-text-muted)]">
                {t('quest_path_filter_label', undefined, 'Path filter')}
              </span>
              <div className="flex items-center gap-1">
                <Button
                  variant={pathFilterMode === 'all' ? 'secondary' : 'ghost'}
                  size="sm"
                  onClick={() => setPathFilterMode('all')}
                >
                  {t('quest_path_filter_all', undefined, 'All')}
                </Button>
                <Button
                  variant={pathFilterMode === 'current' ? 'secondary' : 'ghost'}
                  size="sm"
                  onClick={() => setPathFilterMode('current')}
                >
                  {t('quest_path_filter_current', undefined, 'Current path')}
                </Button>
                <Button
                  variant={pathFilterMode === 'selected' ? 'secondary' : 'ghost'}
                  size="sm"
                  onClick={() => setPathFilterMode('selected')}
                >
                  {t('quest_path_filter_selected', undefined, 'Selected path')}
                </Button>
              </div>
            </div>
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search branches"
              className="lab-quest-search"
            />
          </>
        )}
        <div className="mt-2 space-y-2 border-y border-dashed border-[var(--lab-border)] py-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--lab-text-muted)]">
              {t('quest_curve_mode_label', undefined, 'Curve mode')}
            </span>
            <div className="flex items-center gap-1">
              <Button
                variant={curveMode === 'sota' ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setCurveMode('sota')}
              >
                {t('quest_curve_mode_sota', undefined, 'SoTA only')}
              </Button>
              <Button
                variant={curveMode === 'full' ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setCurveMode('full')}
              >
                {t('quest_curve_mode_full', undefined, 'Full trace')}
              </Button>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="whitespace-nowrap text-[11px] font-semibold uppercase tracking-wide text-[var(--lab-text-muted)]">
              {t('quest_curve_metric_label', undefined, 'Focus metric')}
            </span>
            <select
              className="lab-quest-time-filter flex-1"
              value={curveMetric}
              onChange={(event) => setCurveMetric(event.target.value)}
            >
              {!metricCatalog.length ? (
                <option value="">
                  {t('quest_curve_metric_unavailable', undefined, 'No metric available')}
                </option>
              ) : null}
              {metricCatalog.map((metric) => {
                const directionText =
                  metric.direction === 'lower'
                    ? t('quest_curve_direction_lower', undefined, 'lower is better')
                    : metric.direction === 'higher'
                      ? t('quest_curve_direction_higher', undefined, 'higher is better')
                      : null
                const importanceText =
                  typeof metric.importance === 'number' && Number.isFinite(metric.importance)
                    ? ` · ${t('quest_curve_importance_short', { value: metric.importance.toFixed(2) }, 'w={value}')}`
                    : ''
                const label = metric.label || metric.key
                return (
                  <option key={metric.key} value={metric.key}>
                    {directionText
                      ? `${label} (${directionText}${importanceText})`
                      : `${label}${importanceText}`}
                  </option>
                )
              })}
            </select>
          </div>
        </div>
        <div className="lab-quest-buckets" aria-label="Research buckets">
          <div className="lab-quest-bucket-item">
            <span>Ideas</span>
            <strong>{globalBuckets.ideasOnly}</strong>
          </div>
          <div className="lab-quest-bucket-item">
            <span>Experimenting</span>
            <strong>{globalBuckets.experimenting}</strong>
          </div>
          <div className="lab-quest-bucket-item">
            <span>Write eligible</span>
            <strong>{globalBuckets.writingEligible}</strong>
          </div>
          <div className="lab-quest-bucket-item">
            <span>Writing</span>
            <strong>{globalBuckets.writingActive}</strong>
          </div>
          <div className="lab-quest-bucket-item">
            <span>Completed</span>
            <strong>{globalBuckets.completed}</strong>
          </div>
          <div className="lab-quest-bucket-item">
            <span>Stale (&gt;72h)</span>
            <strong>{globalBuckets.stale}</strong>
          </div>
        </div>
        <div className="lab-quest-process-rail">
          <div className="lab-quest-process-rail__header">
            <div>
              <div className="lab-quest-process-rail__title">
                {t('quest_process_title', undefined, 'Research pipeline')}
              </div>
              <div className="lab-quest-process-rail__subtitle">
                {t(
                  'quest_process_subtitle',
                  { branch: selectedBranchName || 'main' },
                  '{branch} branch'
                )}
              </div>
            </div>
            <div className="lab-quest-process-rail__stage">
              {selectedBranchInsight?.stageLabel ||
                t('quest_process_stage_idle', undefined, 'Not started')}
            </div>
          </div>
          <div className="lab-quest-process-rail__steps">
            {selectedBranchPipelineSteps.map((step, index) => (
              <div
                key={`${selectedBranchName || 'main'}-${step.key}`}
                className={cn('lab-quest-process-rail__step', `is-${step.status}`)}
              >
                <div className="lab-quest-process-rail__step-head">
                  <span className="lab-quest-process-rail__step-index">{index + 1}</span>
                  <span className="lab-quest-process-rail__step-title">{step.label}</span>
                </div>
                <div className="lab-quest-process-rail__step-desc">{step.description}</div>
                <div className="lab-quest-process-rail__step-status">
                  {processStatusLabelMap[step.status]}
                </div>
              </div>
            ))}
          </div>
          {recommendedPath.length ? (
            <div className="lab-quest-process-rail__recommended">
              <div className="lab-quest-process-rail__recommended-head">
                <span className="lab-quest-process-rail__recommended-title">
                  {t('quest_recommended_path_title', undefined, 'Recommended path')}
                </span>
                {recommendedBranchName && onBranchSelect ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onBranchSelect(recommendedBranchName)}
                  >
                    {t('quest_recommended_path_open', undefined, 'Open')}
                  </Button>
                ) : null}
              </div>
              <div className="lab-quest-process-rail__recommended-trail">
                {recommendedPath.map((branchName, index) => (
                  <React.Fragment key={`recommended-path-${branchName}-${index}`}>
                    <button
                      type="button"
                      className={cn(
                        'lab-quest-process-rail__recommended-chip',
                        branchName === selectedBranchName && 'is-active'
                      )}
                      onClick={() => onBranchSelect?.(branchName)}
                    >
                      {branchName}
                    </button>
                    {index < recommendedPath.length - 1 ? (
                      <span className="lab-quest-process-rail__recommended-arrow">→</span>
                    ) : null}
                  </React.Fragment>
                ))}
              </div>
            </div>
          ) : null}
        </div>
        <div className="lab-quest-branch-list">
          {branchDataIsLoading || (branchProjectionPending && (branchGraphData?.nodes?.length ?? 0) === 0) ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, index) => (
                <Skeleton key={`branch-skel-${index}`} className="h-10 w-full" />
              ))}
            </div>
          ) : null}
          {!branchDataIsLoading && !branchProjectionPending && sortedBranches.length === 0 ? (
            <div className="lab-quest-empty">No branches yet.</div>
          ) : null}
          {sortedBranches.map((node) => {
            const isActive = node.branch_name === activeBranch
            const insight = node.branch_name ? branchInsights.get(node.branch_name) : null
            const fromLabel =
              (typeof node.foundation_label === 'string' && node.foundation_label) ||
              (typeof node.parent_branch === 'string' && node.parent_branch) ||
              null
            const statusLabel =
              (typeof insight?.stageLabel === 'string' && insight.stageLabel) ||
              (typeof node.next_target === 'string' && node.next_target) ||
              'idea'
            return (
              <button
                key={node.node_id}
                type="button"
                className={cn('lab-quest-branch-item', isActive && 'is-active')}
                onClick={() => {
                  if (node.branch_name) {
                    onBranchSelect?.(node.branch_name)
                  }
                }}
              >
                <div className="lab-quest-branch-item__title">
                  {node.branch_no ? `#${node.branch_no} · ` : ''}
                  {node.idea_title || node.branch_name}
                </div>
                <div className="lab-quest-branch-item__meta">
                  <span>{node.branch_name}</span>
                  <span>·</span>
                  <span>{statusLabel}</span>
                </div>
                {fromLabel ? (
                  <div className="lab-quest-branch-item__line">
                    <span className="lab-quest-branch-item__label">From</span>
                    <span>{fromLabel}</span>
                  </div>
                ) : null}
                <div className="lab-quest-branch-item__line">
                  <span className="lab-quest-branch-item__label">Next</span>
                  <span>{node.next_target || insight?.nowDoing || 'Waiting for next step'}</span>
                </div>
                <div className="lab-quest-branch-item__line lab-quest-branch-item__line--meta">
                  <span>{insight?.updatedAt ? formatRelativeTime(insight.updatedAt) : formatRelativeTime(node.created_at)}</span>
                </div>
              </button>
            )
          })}
        </div>
        <div className="mt-3 border-t border-dashed border-[var(--lab-border)] pt-3">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-semibold text-[var(--lab-text-primary)]">
              {t(
                'quest_curve_tables_title',
                { branch: selectedBranchName || 'main' },
                'Metric tables · {branch}'
              )}
            </div>
            <div className="text-[11px] text-[var(--lab-text-secondary)]">{curveModeLabel}</div>
          </div>
          {selectedBranchMetricTables.length === 0 ? (
            <div className="mt-2 text-xs text-[var(--lab-text-secondary)]">
              {t('quest_curve_tables_empty', undefined, 'No metric curve data for this branch yet.')}
            </div>
          ) : (
            <div className="mt-2 max-h-72 space-y-2 overflow-auto pr-1">
              {selectedBranchMetricTables.map((table) => {
                const directionLabel =
                  table.direction === 'lower'
                    ? t('quest_curve_direction_lower', undefined, 'lower is better')
                    : table.direction === 'higher'
                      ? t('quest_curve_direction_higher', undefined, 'higher is better')
                      : null
                const importanceLabel =
                  typeof table.importance === 'number' && Number.isFinite(table.importance)
                    ? t('quest_curve_importance', { value: table.importance.toFixed(2) }, 'Importance {value}')
                    : null
                return (
                  <div
                    key={`${selectedBranchName || 'branch'}-${table.key}`}
                    className="rounded border border-dashed border-[var(--lab-border)] bg-[var(--lab-surface)] p-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <div className="text-xs font-semibold text-[var(--lab-text-primary)]">
                          {table.label}
                        </div>
                        <div className="text-[10px] text-[var(--lab-text-muted)]">{table.key}</div>
                      </div>
                      {table.target !== null ? (
                        <div className="text-[10px] text-[var(--lab-text-secondary)]">
                          {t('quest_curve_target', { value: table.target.toFixed(4) }, 'Target {value}')}
                        </div>
                      ) : null}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-[var(--lab-text-secondary)]">
                      {directionLabel ? <span>{directionLabel}</span> : null}
                      {importanceLabel ? <span>{importanceLabel}</span> : null}
                    </div>
                    <MetricCurveChart
                      values={table.points.map((point) => point.value)}
                      variant="expanded"
                      className="mt-2"
                    />
                    <div className="mt-2 overflow-x-auto">
                      <table className="min-w-full border-collapse text-[11px] text-[var(--lab-text-secondary)]">
                        <thead>
                          <tr className="border-b border-dashed border-[var(--lab-border)] text-[10px] uppercase tracking-wide text-[var(--lab-text-muted)]">
                            <th className="py-1 pr-2 text-left">
                              {t('quest_curve_table_col_seq', undefined, '#')}
                            </th>
                            <th className="py-1 pr-2 text-left">
                              {t('quest_curve_table_col_run', undefined, 'Run')}
                            </th>
                            <th className="py-1 pr-2 text-left">
                              {t('quest_curve_table_col_time', undefined, 'Time')}
                            </th>
                            <th className="py-1 text-right">
                              {t('quest_curve_table_col_value', undefined, 'Value')}
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {table.points.map((point, index) => (
                            <tr
                              key={`${table.key}-${point.seq}-${index}`}
                              className="border-b border-dashed border-[var(--lab-border)] last:border-b-0"
                            >
                              <td className="py-1 pr-2">{point.seq}</td>
                              <td className="max-w-[120px] truncate py-1 pr-2">
                                {point.runId || point.eventId || 'n/a'}
                              </td>
                              <td className="max-w-[170px] truncate py-1 pr-2">
                                {formatCurveTimestamp(point.ts)}
                              </td>
                              <td className="py-1 text-right font-semibold text-[var(--lab-text-primary)]">
                                {table.unit
                                  ? `${point.value.toFixed(4)} ${table.unit}`
                                  : point.value.toFixed(4)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {table.totalPoints > table.points.length ? (
                      <div className="mt-1 text-[10px] text-[var(--lab-text-muted)]">
                        {t(
                          'quest_curve_table_truncated',
                          { shown: table.points.length, total: table.totalPoints },
                          'Showing latest {shown} / {total} points'
                        )}
                      </div>
                    ) : null}
                  </div>
                )
              })}
            </div>
          )}
        </div>
        <div className="lab-floating-panel__footer">
          <div className="lab-quest-graph-controls">
            <Button
              variant={viewMode === 'branch' ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => setViewMode('branch')}
            >
              Branch map
            </Button>
            <Button
              variant={viewMode === 'event' ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => setViewMode('event')}
            >
              Event trace
            </Button>
            <Button
              variant={viewMode === 'stage' ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => setViewMode('stage')}
            >
              Stage flow
            </Button>
            {viewMode === 'event' ? (
              <>
                <Button
                  variant={eventTraceMode === 'compact' ? 'secondary' : 'ghost'}
                  size="sm"
                  onClick={() => setEventTraceMode('compact')}
                >
                  Compact
                </Button>
                <Button
                  variant={eventTraceMode === 'detailed' ? 'secondary' : 'ghost'}
                  size="sm"
                  onClick={() => setEventTraceMode('detailed')}
                >
                  Detailed
                </Button>
              </>
            ) : null}
            {viewMode !== 'stage' ? (
              <select
                className="lab-quest-time-filter"
                value={timeRange}
                onChange={(event) => setTimeRange(event.target.value as typeof timeRange)}
              >
                <option value="all">All time</option>
                <option value="7d">Last 7 days</option>
                <option value="30d">Last 30 days</option>
                <option value="90d">Last 90 days</option>
              </select>
            ) : null}
          </div>
          <div className="mt-3 rounded-[12px] border border-[var(--lab-border)] bg-[var(--lab-surface)] px-3 py-2.5">
            <div className="flex items-start gap-2">
              <span
                className={cn(
                  'inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold',
                  semanticToneBadgeClass(currentViewSemantic.tone)
                )}
              >
                {t(
                  LAB_CANVAS_SEMANTIC_TONE_META[currentViewSemantic.tone].labelKey,
                  undefined,
                  LAB_CANVAS_SEMANTIC_TONE_META[currentViewSemantic.tone].labelDefault
                )}
              </span>
              <div className="min-w-0">
                <div className="text-[11px] font-semibold text-[var(--lab-text-primary)]">
                  {t('quest_semantic_current_view', undefined, 'Current view')} ·{' '}
                  {t(currentViewSemantic.labelKey, undefined, currentViewSemantic.labelDefault)}
                </div>
                <div className="mt-1 text-[11px] leading-5 text-[var(--lab-text-secondary)]">
                  {t(
                    currentViewSemantic.descriptionKey,
                    undefined,
                    currentViewSemantic.descriptionDefault
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
        </FloatingPanel>
      ) : null}

      {showFloatingPanels ? (
        <FloatingPanel
          boundsRef={boundsRef}
          title="Recent events"
          icon={<Clock size={16} />}
          state={eventsPanel}
          zIndex={panelZ.events}
          onChange={setEventsPanel}
          onActivate={() => bringToFront('events')}
          className="lab-floating-panel--events"
        >
        <div className="lab-quest-panel__header">
          <div>
            <div className="lab-quest-panel__subtitle">Latest updates</div>
          </div>
          <div className="lab-decision-filter" aria-label="Event filters">
            <button
              type="button"
              className={cn('lab-decision-filter__chip', eventFilter === 'all' && 'is-active')}
              onClick={() => selectEventFilter('all')}
              aria-pressed={eventFilter === 'all'}
            >
              All
            </button>
            <button
              type="button"
              className={cn('lab-decision-filter__chip', eventFilter === 'activity' && 'is-active')}
              onClick={() => selectEventFilter('activity')}
              aria-pressed={eventFilter === 'activity'}
            >
              Activity
            </button>
            <button
              type="button"
              className={cn('lab-decision-filter__chip', eventFilter === 'decision' && 'is-active')}
              onClick={() => selectEventFilter('decision')}
              aria-pressed={eventFilter === 'decision'}
            >
              Decisions
            </button>
            <button
              type="button"
              className={cn('lab-decision-filter__chip', eventFilter === 'error' && 'is-active')}
              onClick={() => selectEventFilter('error')}
              aria-pressed={eventFilter === 'error'}
            >
              Errors
            </button>
          </div>
        </div>
        <div className="lab-quest-event-list">
          {eventsQuery.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, index) => (
                <Skeleton key={`event-skel-${index}`} className="h-12 w-full" />
              ))}
            </div>
          ) : null}
          {!eventsQuery.isLoading ? (
            <>
              <div className="lab-quest-section">
                <div className="lab-quest-section__title">Now doing</div>
                {nowDoingItems.length === 0 ? (
                  <div className="lab-quest-empty">No active branch updates.</div>
                ) : (
                  <div className="space-y-2">
                    {nowDoingItems.map((item) => (
                      <button
                        key={`now-doing-${item.branchName}`}
                        type="button"
                        className="lab-quest-event-item"
                        onClick={() => item.branchName && onBranchSelect?.(item.branchName)}
                      >
                        <div className="lab-quest-event-item__title">{item.branchName}</div>
                        <div className="lab-quest-event-item__meta">
                          <span>{item.stageLabel}</span>
                          <span>{formatRelativeTime(item.updatedAt)}</span>
                        </div>
                        <div className="lab-quest-event-item__summary">{item.nowDoing}</div>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="lab-quest-section">
                <div className="lab-quest-section__title">Decision log</div>
                {decisionLogItems.length === 0 ? (
                  <div className="lab-quest-empty">No decisions yet.</div>
                ) : (
                  <div className="space-y-2">
                    {decisionLogItems.slice(0, 8).map((event) => (
                      <button
                        key={`decision-log-${event.event_id}`}
                        type="button"
                        className="lab-quest-event-item"
                        onClick={() => {
                          if (onEventSelect) {
                            onEventSelect(event.event_id, event.branch_name || undefined)
                            return
                          }
                          if (event.branch_name && onBranchSelect) {
                            onBranchSelect(event.branch_name)
                          }
                        }}
                      >
                        <div className="lab-quest-event-item__title">
                          {resolveDecisionLabel(event)} · {event.branch_name || 'main'}
                        </div>
                        <div className="lab-quest-event-item__meta">
                          <span>{event.event_type}</span>
                          <span>{formatRelativeTime(event.created_at)}</span>
                        </div>
                        <div className="lab-quest-event-item__summary">
                          {resolveDecisionReason(event) || 'No reason provided.'}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="lab-quest-section">
                <div className="lab-quest-section__title">Events</div>
                {recentEvents.length === 0 ? (
                  <div className="lab-quest-empty">No events yet.</div>
                ) : filteredEvents.length === 0 ? (
                  <div className="lab-quest-empty">No matching events.</div>
                ) : (
                  <div className="space-y-3">
                    {groupedFilteredEvents.map((group) => (
                      <div key={`event-group-${group.label}`} className="space-y-2">
                        <div className="px-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--lab-text-secondary)]">
                          {group.label}
                        </div>
                        <div className="space-y-2">
                          {group.items.map((event) => {
                            const stageBadge = formatStageBadge(resolveEventStageKey(event))
                            return (
                              <button
                                key={event.event_id}
                                type="button"
                                className="lab-quest-event-item"
                                onClick={() => {
                                  if (onEventSelect) {
                                    onEventSelect(event.event_id, event.branch_name || undefined)
                                    return
                                  }
                                  if (event.branch_name && onBranchSelect) {
                                    onBranchSelect(event.branch_name)
                                  }
                                }}
                              >
                                <div className="lab-quest-event-item__title">{resolveEventHeadline(event)}</div>
                                <div className="lab-quest-event-item__meta">
                                  <span>{event.branch_name || 'main'}</span>
                                  {stageBadge ? <span>{stageBadge}</span> : null}
                                  <span>{formatRelativeTime(event.created_at)}</span>
                                </div>
                                <div className="lab-quest-event-item__summary">{resolveEventSummaryText(event)}</div>
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="mt-1 rounded-[12px] border border-[var(--lab-border)] bg-[var(--lab-surface)] p-2">
                <div className="mb-2 text-[11px] font-semibold text-[var(--lab-text-secondary)]">PI Q&amp;A</div>
                {piQaPairs.length === 0 ? (
                  <div className="lab-quest-empty">No PI Q&amp;A yet.</div>
                ) : (
                  <div className="space-y-2">
                    {piQaPairs.slice(0, 8).map((pair) => (
                      <button
                        key={`pi-qa-${pair.questionId}`}
                        type="button"
                        className="w-full rounded-[10px] border border-[var(--lab-border)] bg-[var(--lab-surface-muted)] px-2 py-1.5 text-left"
                        onClick={() => {
                          if (pair.branchName && onBranchSelect) {
                            onBranchSelect(pair.branchName)
                          }
                        }}
                      >
                        <div className="text-[10px] uppercase tracking-wide text-[var(--lab-text-secondary)]">
                          {pair.branchName || 'main'} · {pair.questionId}
                        </div>
                        <div className="mt-1 text-[12px] text-[var(--lab-text-primary)]">
                          Q: {pair.question || '...'}
                        </div>
                        <div className="mt-1 text-[11px] text-[var(--lab-text-secondary)]">
                          A: {pair.answer || 'Pending'}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : null}
        </div>
        </FloatingPanel>
      ) : null}

      {showFloatingPanels ? (
        <FloatingPanel
          boundsRef={boundsRef}
          title="Papers"
          icon={<FileText size={16} />}
          state={papersPanel}
          zIndex={panelZ.papers}
          onChange={setPapersPanel}
          onActivate={() => bringToFront('papers')}
          className="lab-floating-panel--papers"
        >
        <div className="lab-quest-panel__header">
          <div>
            <div className="lab-quest-panel__subtitle">{papers.length} total</div>
          </div>
          {onBranchSelect ? (
            <button
              type="button"
              className="lab-quest-panel__toggle"
              onClick={() => onBranchSelect(writingBranch)}
            >
              Open writing
            </button>
          ) : null}
        </div>
        <div className="lab-quest-event-list">
          {papersQuery.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={`paper-skel-${index}`} className="h-12 w-full" />
              ))}
            </div>
          ) : null}
          {!papersQuery.isLoading && papers.length === 0 ? (
            <div className="lab-quest-empty">No papers yet.</div>
          ) : null}
          {papers.map((paper) => {
            const latest = paper.latest_version
            const versionLabel =
              latest?.version_index != null ? `v${latest.version_index}` : '—'
            const mainTex = latest?.main_tex_path ?? '—'
            const versionStatus = String(latest?.status || '').trim() || 'unknown'
            const archiveErrorCode = String(latest?.archive_error_code || '').trim()
            const archiveErrorDetail = String(latest?.archive_error_detail || '').trim()
            return (
              <div key={paper.paper_root_id} className="lab-quest-event-item">
                <div className="lab-quest-event-item__title">
                  {paper.title || paper.paper_root_id.slice(0, 8)}
                </div>
                <div className="lab-quest-event-item__meta">
                  <span>{versionLabel}</span>
                  <span>{versionStatus}</span>
                  <span>{formatRelativeTime(latest?.created_at)}</span>
                </div>
                <div className="lab-quest-event-item__summary">{mainTex}</div>
                {archiveErrorCode ? (
                  <div className="mt-1 text-xs text-[var(--lab-danger,#b42318)]">
                    {t(
                      'quest_paper_archive_failed',
                      { code: archiveErrorCode },
                      'Archive failed: {code}'
                    )}
                    {archiveErrorDetail ? ` · ${archiveErrorDetail}` : ''}
                  </div>
                ) : null}
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="min-h-[36px] px-3 text-xs"
                    disabled={!latest?.main_tex_path && !latest?.main_tex_file_id}
                    onClick={() => openPaperTex(paper)}
                  >
                    Open
                  </Button>
                  {onBranchSelect ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="min-h-[36px] px-3 text-xs"
                      onClick={() => onBranchSelect(writingBranch)}
                    >
                      Writing
                    </Button>
                  ) : null}
                </div>
              </div>
            )
          })}
        </div>
        </FloatingPanel>
      ) : null}

    </div>
  )
}

export default function LabQuestGraphCanvas(props: LabQuestGraphCanvasProps) {
  return (
    <ReactFlowProvider>
      <LabQuestGraphCanvasInner {...props} />
    </ReactFlowProvider>
  )
}
