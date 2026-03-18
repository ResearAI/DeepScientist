'use client'

import * as React from 'react'
import { motion } from 'framer-motion'
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Loader2,
  Square,
  TerminalSquare,
} from 'lucide-react'

import { McpBashExecView } from '@/components/chat/toolViews/McpBashExecView'
import type { ToolContent } from '@/lib/plugins/ai-manus/types'
import type { EventMetadata } from '@/lib/types/chat-events'
import type { BashProgress } from '@/lib/types/bash'
import { formatProgressLabel, formatProgressMeta, getProgressPercent } from '@/lib/utils/bash-progress'
import { cn } from '@/lib/utils'
import type { AgentComment } from '@/types'

function parseStructuredValue(value?: string) {
  if (!value) return null
  try {
    return JSON.parse(value) as Record<string, unknown>
  } catch {
    return null
  }
}

function extractBashResult(value?: string) {
  const parsed = parseStructuredValue(value)
  if (!parsed) return null
  const nested = parsed.result
  if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
    return nested as Record<string, unknown>
  }
  return parsed
}

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

function summarizeCommand(value?: string) {
  const normalized = String(value || '').replace(/\s+/g, ' ').trim()
  if (!normalized) return ''
  if (normalized.length <= 160) return normalized
  return `${normalized.slice(0, 120)}…${normalized.slice(-28)}`
}

function formatStatusLabel(value: string) {
  return value.replace(/_/g, ' ')
}

function describeBashActivity(args: {
  isFailed: boolean
  isStopped: boolean
  isRunning: boolean
  workdir: string
}) {
  const location = args.workdir.trim() || '~'
  if (args.isFailed) {
    return 'DeepScientist finished the terminal task with an error.'
  }
  if (args.isStopped) {
    return 'DeepScientist stopped the terminal task.'
  }
  if (args.isRunning) {
    return `DeepScientist is operating the terminal in ${location}.`
  }
  return ''
}

function extractInitialProgress(value: Record<string, unknown> | null): BashProgress | null {
  const candidate = value?.last_progress
  if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) {
    return null
  }
  return candidate as BashProgress
}

function formatPercentLabel(value: number | null) {
  if (value == null) return ''
  const rounded = Math.round(value * 10) / 10
  return Number.isInteger(rounded) ? `${rounded.toFixed(0)}%` : `${rounded.toFixed(1)}%`
}

export function QuestBashExecOperation({
  questId,
  itemId,
  toolCallId,
  toolName,
  label,
  status,
  args,
  output,
  createdAt,
  metadata,
  isLatest = false,
  expandBehavior = 'latest_or_running',
}: {
  questId: string
  itemId: string
  toolCallId?: string
  toolName?: string
  label: 'tool_call' | 'tool_result'
  status?: string
  args?: string
  output?: string
  createdAt?: string
  metadata?: Record<string, unknown>
  comment?: AgentComment | null
  monitorPlanSeconds?: number[]
  monitorStepIndex?: number | null
  nextCheckAfterSeconds?: number | null
  isLatest?: boolean
  expandBehavior?: 'latest_or_running' | 'latest_only'
}) {
  const timestamp = createdAt ? Date.parse(createdAt) : Date.now()
  const resolvedTimestamp = Number.isFinite(timestamp) ? timestamp : Date.now()
  const parsedArgs = parseStructuredValue(args)
  const parsedOutput = extractBashResult(output)
  const initialProgress = extractInitialProgress(parsedOutput)
  const command =
    typeof parsedArgs?.command === 'string'
      ? parsedArgs.command
      : typeof parsedArgs?.cmd === 'string'
        ? parsedArgs.cmd
        : ''
  const workdir = typeof parsedArgs?.workdir === 'string' ? parsedArgs.workdir : ''
  const bashId =
    typeof parsedOutput?.bash_id === 'string'
      ? parsedOutput.bash_id
      : typeof metadata?.bash_id === 'string'
        ? metadata.bash_id
        : ''
  const exitCode = typeof parsedOutput?.exit_code === 'number' ? parsedOutput.exit_code : null
  const [liveProgress, setLiveProgress] = React.useState<BashProgress | null>(initialProgress)
  const [liveStatus, setLiveStatus] = React.useState<string | null>(
    typeof parsedOutput?.status === 'string' ? parsedOutput.status : typeof status === 'string' ? status : null
  )
  const [liveExitCode, setLiveExitCode] = React.useState<number | null>(exitCode)
  const [liveStopReason, setLiveStopReason] = React.useState<string>(
    typeof parsedOutput?.stop_reason === 'string' ? parsedOutput.stop_reason : ''
  )

  React.useEffect(() => {
    setLiveProgress(initialProgress)
  }, [initialProgress, bashId])

  React.useEffect(() => {
    setLiveStatus(
      typeof parsedOutput?.status === 'string' ? parsedOutput.status : typeof status === 'string' ? status : null
    )
    setLiveExitCode(exitCode)
    setLiveStopReason(typeof parsedOutput?.stop_reason === 'string' ? parsedOutput.stop_reason : '')
  }, [bashId, exitCode, parsedOutput, status])

  const rawStatus = String(
    liveStatus ||
    (typeof parsedOutput?.status === 'string' ? parsedOutput.status : status) ||
      (label === 'tool_call' ? 'running' : 'completed')
  )
    .trim()
    .toLowerCase()
  const isFailed =
    rawStatus.includes('fail') ||
    rawStatus.includes('error') ||
    (liveExitCode != null && liveExitCode !== 0)
  const isStopped =
    rawStatus === 'stopped' ||
    rawStatus === 'terminated' ||
    rawStatus === 'cancelled'
  const isRunning =
    !isFailed &&
    !isStopped &&
    (['running', 'calling', 'pending', 'queued', 'starting', 'terminating'].includes(rawStatus) ||
      (!liveStatus && !parsedOutput?.status && !status && label === 'tool_call'))
  const statusLabel = formatStatusLabel(
    isFailed
      ? rawStatus || 'failed'
      : isStopped
        ? rawStatus
        : isRunning
          ? rawStatus || 'running'
          : rawStatus || 'completed'
  )
  const title = describeBashActivity({
    isFailed,
    isStopped,
    isRunning,
    workdir,
  })
  const shouldHideGenericCompletedCard =
    label === 'tool_result' &&
    !command &&
    !isFailed &&
    !isStopped &&
    !isRunning
  const progressPercent = getProgressPercent(liveProgress)
  const progressLabel = formatProgressLabel(liveProgress)
  const progressMeta = formatProgressMeta(liveProgress)
  const progressReason = liveStopReason.trim()
  const summary = summarizeCommand(command) || title || 'bash_exec'
  const compactProgressLabel = formatPercentLabel(progressPercent)
  const progressSummary = [progressLabel, compactProgressLabel, progressMeta || progressReason]
    .filter(Boolean)
    .join(' · ')
  const showProgress = liveProgress != null
  const showProgressSummary = showProgress && Boolean(progressSummary)
  const StatusIcon = isFailed ? AlertCircle : isStopped ? Square : isRunning ? Loader2 : CheckCircle2
  const statusChipClass = isFailed
    ? 'border-rose-500/20 bg-rose-500/10 text-rose-700 dark:border-rose-300/20 dark:bg-rose-300/10 dark:text-rose-200'
    : isStopped
      ? 'border-amber-500/20 bg-amber-500/10 text-amber-700 dark:border-amber-300/20 dark:bg-amber-300/10 dark:text-amber-200'
      : isRunning
      ? 'border-black/[0.08] bg-black/[0.04] text-foreground dark:border-white/[0.10] dark:bg-white/[0.06]'
        : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:border-emerald-300/20 dark:bg-emerald-300/10 dark:text-emerald-200'
  const shouldAutoExpandRunning = expandBehavior === 'latest_or_running'
  const [expanded, setExpanded] = React.useState(
    () => isLatest || (shouldAutoExpandRunning && isRunning)
  )
  const expandModeRef = React.useRef<'auto' | 'manual-open' | 'manual-close'>('auto')

  React.useEffect(() => {
    if (shouldAutoExpandRunning && isRunning) {
      setExpanded(true)
      return
    }
    if (isLatest) {
      if (expandModeRef.current !== 'manual-close') {
        setExpanded(true)
      }
      return
    }
    if (expandModeRef.current === 'auto') {
      setExpanded(false)
    }
  }, [isLatest, isRunning, shouldAutoExpandRunning])

  const eventMetadata: EventMetadata = {
    surface: 'copilot',
    quest_id: questId,
    session_id:
      typeof metadata?.session_id === 'string' && metadata.session_id.trim()
        ? metadata.session_id
        : `quest:${questId}`,
    sender_type: 'agent',
    sender_label: 'DeepScientist',
    sender_name: 'DeepScientist',
    ...(metadata as EventMetadata | undefined),
  }

  const toolContent: ToolContent = {
    event_id: itemId,
    timestamp: resolvedTimestamp,
    tool_call_id: toolCallId || itemId,
    name: toolName || 'bash_exec',
    function: 'mcp__bash_exec__bash_exec',
    status: label === 'tool_call' ? 'calling' : 'called',
    args: parsedArgs ?? (args ? { raw: args } : {}),
    content:
      label === 'tool_result'
        ? {
            ...(parsedOutput ? { result: parsedOutput } : {}),
            ...(output && !parsedOutput ? { text: output } : {}),
            ...(status ? { status } : {}),
          }
        : {},
    metadata: eventMetadata,
  }

  if (shouldHideGenericCompletedCard) {
    return null
  }

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 14, scale: 0.985 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -8, scale: 0.992 }}
      transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        'min-w-0 overflow-hidden rounded-[16px] border border-black/[0.04] bg-black/[0.02] px-3 py-2 dark:border-white/[0.06] dark:bg-white/[0.04]',
        isRunning && 'ring-1 ring-black/[0.05] dark:ring-white/[0.08]'
      )}
    >
      <button
        type="button"
        className="flex w-full min-w-0 flex-col gap-2 text-left"
        onClick={() => {
          setExpanded((current) => {
            const next = !current
            expandModeRef.current = next ? 'manual-open' : 'manual-close'
            return next
          })
        }}
      >
        <div className="flex w-full min-w-0 items-center gap-2.5">
          <div
            title={toolName?.trim() || 'bash_exec'}
            aria-label={toolName?.trim() || 'bash_exec'}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[12px] bg-[rgba(151,164,179,0.14)] text-foreground dark:bg-[rgba(231,223,210,0.08)]"
          >
            {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <TerminalSquare className="h-4 w-4" />}
          </div>

          <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] font-medium leading-5 text-foreground" title={summary}>
              {summary}
            </div>
          </div>

          <div className="ml-auto flex min-w-0 shrink items-center gap-2 text-[11px] text-muted-foreground">
            {showProgressSummary ? (
              <span
                className="max-w-[220px] shrink truncate font-medium text-muted-foreground"
                title={progressSummary}
              >
                {progressSummary}
              </span>
            ) : null}
            <span
              className={cn(
                'inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 font-medium',
                statusChipClass
              )}
            >
              <StatusIcon className={cn('h-3.5 w-3.5', isRunning && 'animate-spin')} />
              {statusLabel}
            </span>
            {createdAt ? <span className="shrink-0 whitespace-nowrap">{formatTime(createdAt)}</span> : null}
            <ChevronDown
              className={cn(
                'h-4 w-4 shrink-0 transition-transform',
                expanded && 'rotate-180'
              )}
            />
          </div>
        </div>
      </button>

      {expanded ? (
        <div className="ds-studio-bash-shell mt-2 overflow-hidden rounded-none border border-black/[0.05] bg-black/[0.03] p-0 dark:border-white/[0.06] dark:bg-white/[0.03]">
          <McpBashExecView
            toolContent={toolContent}
            live={label === 'tool_call' || status === 'running' || status === 'terminating'}
            sessionId={eventMetadata.session_id}
            projectId={questId}
            readOnly={false}
            panelMode="inline"
            chrome="bare"
            onLiveStateChange={(state) => {
              setLiveProgress(state.progress)
              setLiveStatus(state.status)
              setLiveExitCode(state.exitCode)
              setLiveStopReason(state.stopReason)
            }}
          />
        </div>
      ) : null}
    </motion.article>
  )
}

export default QuestBashExecOperation
