'use client'

import * as React from 'react'
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Loader2,
  Square,
  TerminalSquare,
} from 'lucide-react'

import { McpBashExecView } from '@/components/chat/toolViews/McpBashExecView'
import { useI18n } from '@/lib/i18n/useI18n'
import type { ToolContent } from '@/lib/plugins/ai-manus/types'
import type { EventMetadata } from '@/lib/types/chat-events'
import type { BashProgress } from '@/lib/types/bash'
import { formatProgressLabel, formatProgressMeta, getProgressPercent } from '@/lib/utils/bash-progress'
import { cn } from '@/lib/utils'
import type { AgentComment } from '@/types'

function parseStructuredValue(value?: string) {
  if (!value) return null
  try {
    return JSON.parse(value) as unknown
  } catch {
    return null
  }
}

function asRecord(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }
  return value as Record<string, unknown>
}

function unwrapStructuredRecord(value: unknown): Record<string, unknown> | null {
  const record = asRecord(value)
  if (!record) return null
  if (record.structured_content && record.structured_content !== value) {
    return unwrapStructuredRecord(record.structured_content)
  }
  if (record.structured_result && record.structured_result !== value) {
    return unwrapStructuredRecord(record.structured_result)
  }
  if (record.result && record.result !== value) {
    return unwrapStructuredRecord(record.result)
  }
  if (Array.isArray(record.content)) {
    for (const entry of record.content) {
      const contentRecord = asRecord(entry)
      if (!contentRecord) continue
      const nested = unwrapStructuredRecord(contentRecord)
      if (nested) return nested
      if (typeof contentRecord.text === 'string') {
        const parsedText = parseStructuredValue(contentRecord.text)
        const parsedRecord = unwrapStructuredRecord(parsedText)
        if (parsedRecord) return parsedRecord
      }
    }
  }
  return record
}

function extractBashResult(value?: string) {
  return unwrapStructuredRecord(parseStructuredValue(value))
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

function formatStatusLabel(value: string) {
  return value.replace(/_/g, ' ')
}

function describeBashActivity(args: {
  isFailed: boolean
  isStopped: boolean
  isRunning: boolean
  workdir: string
  mode: string
  commandSummary: string
}) {
  if (args.mode === 'list') {
    return args.isRunning ? 'Checking background terminals' : 'Checked background terminals'
  }
  if (args.mode === 'history') {
    return args.isRunning ? 'Reading terminal history' : 'Read terminal history'
  }
  if (args.commandSummary) {
    if (args.isFailed) {
      return `Command failed · ${args.commandSummary}`
    }
    if (args.isStopped) {
      return `Command stopped · ${args.commandSummary}`
    }
    if (args.isRunning) {
      return `Running ${args.commandSummary}`
    }
    return `Ran ${args.commandSummary}`
  }
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
  comment,
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
  const { t } = useI18n('workspace')
  const timestamp = createdAt ? Date.parse(createdAt) : Date.now()
  const resolvedTimestamp = Number.isFinite(timestamp) ? timestamp : Date.now()
  const parsedArgs = asRecord(parseStructuredValue(args))
  const parsedOutput = extractBashResult(output)
  const initialProgress = extractInitialProgress(parsedOutput)
  const mode = typeof parsedArgs?.mode === 'string' ? parsedArgs.mode.trim().toLowerCase() : ''
  const command =
    typeof parsedArgs?.command === 'string'
      ? parsedArgs.command
      : typeof parsedArgs?.cmd === 'string'
        ? parsedArgs.cmd
        : typeof parsedOutput?.command === 'string'
          ? parsedOutput.command
          : typeof metadata?.command === 'string'
            ? metadata.command
            : ''
  const workdir =
    typeof parsedArgs?.workdir === 'string'
      ? parsedArgs.workdir
      : typeof parsedOutput?.workdir === 'string'
        ? parsedOutput.workdir
        : typeof parsedOutput?.cwd === 'string'
          ? parsedOutput.cwd
          : typeof metadata?.workdir === 'string'
            ? metadata.workdir
            : typeof metadata?.cwd === 'string'
              ? metadata.cwd
            : ''
  const bashId =
    typeof parsedOutput?.bash_id === 'string'
      ? parsedOutput.bash_id
      : typeof metadata?.bash_id === 'string'
        ? metadata.bash_id
        : typeof parsedArgs?.id === 'string'
          ? parsedArgs.id
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
  const commandSummary = summarizeCommand(command)
  const title = describeBashActivity({
    isFailed,
    isStopped,
    isRunning,
    workdir,
    mode,
    commandSummary,
  })
  const progressPercent = getProgressPercent(liveProgress)
  const progressLabel = formatProgressLabel(liveProgress)
  const progressMeta = formatProgressMeta(liveProgress)
  const progressReason = liveStopReason.trim()
  const commentSummary = comment?.summary?.trim() || ''
  const commentWhyNow = comment?.whyNow?.trim() || ''
  const commentNext = comment?.next?.trim() || ''
  const summary =
    commentSummary ||
    title ||
    commandSummary ||
    (typeof parsedArgs?.comment === 'string' ? parsedArgs.comment : '') ||
    'bash_exec'
  const secondaryText = selectSecondaryText(summary, [
    commentSummary ? title : '',
    commandSummary,
    commentWhyNow,
    commentNext,
    workdir ? `workdir: ${workdir}` : '',
  ])
  const compactProgressLabel = formatPercentLabel(progressPercent)
  const progressSummary = [progressLabel, compactProgressLabel, progressMeta || progressReason]
    .filter(Boolean)
    .join(' · ')
  const showProgress = liveProgress != null
  const showProgressSummary = showProgress && Boolean(progressSummary)
  const collapsedDetailText = selectSecondaryText(summary, [
    showProgressSummary ? progressSummary : '',
    secondaryText,
  ])
  const StatusIcon = isFailed ? AlertCircle : isStopped ? Square : isRunning ? Loader2 : CheckCircle2
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

  return (
    <article
      className={cn(
        'min-w-0 overflow-hidden border-l border-black/[0.08] py-1 pl-3 dark:border-white/[0.10]',
        isRunning && 'border-[#9b8352]/60'
      )}
    >
      <button
        type="button"
        className="flex w-full min-w-0 items-start gap-2.5 py-1 text-left"
        onClick={() => {
          setExpanded((current) => {
            const next = !current
            expandModeRef.current = next ? 'manual-open' : 'manual-close'
            return next
          })
        }}
      >
        <div
          title={toolName?.trim() || 'bash_exec'}
          aria-label={toolName?.trim() || 'bash_exec'}
          className="mt-0.5 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-sm bg-[rgba(151,164,179,0.14)] text-foreground dark:bg-[rgba(231,223,210,0.08)]"
        >
          {isRunning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <TerminalSquare className="h-3.5 w-3.5" />}
        </div>

        <div className="min-w-0 flex-1">
          <div className="break-words text-[12.5px] font-medium leading-[1.65] text-foreground [overflow-wrap:anywhere]" title={summary}>
            {summary}
          </div>
          {collapsedDetailText ? (
            <div
              className="break-words pt-0.5 text-[12px] leading-[1.5] text-muted-foreground [overflow-wrap:anywhere]"
              title={collapsedDetailText}
            >
              {collapsedDetailText}
            </div>
          ) : null}
        </div>

        <div className="ml-auto flex shrink-0 flex-col items-end gap-0.5 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1 font-medium text-muted-foreground">
            <StatusIcon className={cn('h-3.5 w-3.5', isRunning && 'animate-spin')} />
            {statusLabel}
          </span>
          <div className="flex items-center gap-1.5">
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
        <div className="ml-[20px] mt-2 space-y-2 border-l border-black/[0.06] pl-3 dark:border-white/[0.08]">
          {commentSummary || commentWhyNow || commentNext ? (
            <div className="border-l-2 border-black/[0.08] pl-3 text-[12px] leading-[1.6] text-muted-foreground dark:border-white/[0.10]">
              {comment?.summary ? (
                <div className="break-words [overflow-wrap:anywhere]">
                  <span className="font-medium text-foreground">{t('copilot_trace_summary')}:</span> {comment.summary}
                </div>
              ) : null}
              {comment?.whyNow ? (
                <div className="break-words [overflow-wrap:anywhere]">
                  <span className="font-medium text-foreground">{t('copilot_trace_why_now')}:</span> {comment.whyNow}
                </div>
              ) : null}
              {comment?.next ? (
                <div className="break-words [overflow-wrap:anywhere]">
                  <span className="font-medium text-foreground">{t('copilot_trace_next')}:</span> {comment.next}
                </div>
              ) : null}
            </div>
          ) : null}

          {!showProgressSummary && progressSummary ? (
            <div className="text-[12px] leading-[1.5] text-muted-foreground">{progressSummary}</div>
          ) : null}

          <div className="ds-studio-bash-shell overflow-hidden rounded-[10px] border border-black/[0.05] bg-black/[0.03] p-0 dark:border-white/[0.06] dark:bg-white/[0.03]">
            <McpBashExecView
              toolContent={toolContent}
              live={label === 'tool_call' || status === 'running' || status === 'terminating'}
              sessionId={eventMetadata.session_id}
              projectId={questId}
              readOnly={false}
              panelMode="inline"
              chrome="bare"
              preferBashTerminalRender
              onLiveStateChange={(state) => {
                setLiveProgress(state.progress)
                setLiveStatus(state.status)
                setLiveExitCode(state.exitCode)
                setLiveStopReason(state.stopReason)
              }}
            />
          </div>
        </div>
      ) : null}
    </article>
  )
}

export default QuestBashExecOperation
