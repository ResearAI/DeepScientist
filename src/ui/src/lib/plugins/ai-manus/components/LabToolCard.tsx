'use client'

import * as React from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  Archive,
  Clock,
  GitCommit,
  HelpCircle,
  UserPlus,
} from 'lucide-react'
import type { ToolContent } from '../types'
import { getMcpToolKind } from '../lib/mcp-tools'
import { formatRelativeTime } from '../lib/time'
import { cn } from '@/lib/utils'
import { truncateText } from '@/lib/bugbash/sanitize'
import {
  listLabPendingQuestions,
  listLabQuestionHistory,
  type LabPendingQuestion,
  type LabQuestionHistoryItem,
} from '@/lib/api/lab'
import {
  normalizeQuestions,
  type QuestionPromptArgs,
} from '@/lib/plugins/ai-manus/lib/question-prompt-utils'

type LabToolDetail = { label: string; value: string }
type LabToolAction = { id: string; label: string; onClick: () => void }

const TOOL_ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  lab_quests: UserPlus,
  lab_pi_sleep: Clock,
  status_update: Activity,
  write_question: HelpCircle,
  write_memory: Archive,
  lab_baseline: Archive,
  default: GitCommit,
}

const isLabSurface = (tool: ToolContent) => {
  const surface = tool.metadata?.surface
  return typeof surface === 'string' && surface.startsWith('lab-')
}

const normalizeText = (value: unknown) =>
  typeof value === 'string' && value.trim() ? value.trim() : ''

const normalizeMode = (value: unknown) => normalizeText(value).toLowerCase()

const normalizeList = (value: unknown): string[] => {
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).map((item) => item.trim()).filter(Boolean)
  }
  if (typeof value === 'string') {
    return value.split(',').map((item) => item.trim()).filter(Boolean)
  }
  return []
}

const formatActorLabel = (raw: string) => {
  const trimmed = raw.trim()
  if (!trimmed) return ''
  return trimmed.startsWith('@') ? trimmed : `@${trimmed}`
}

const toOneLine = (value: string, limit = 120) =>
  truncateText(value.replace(/\s+/g, ' ').trim(), limit)

const extractFirstLine = (value: string, limit = 160) => {
  if (!value) return ''
  const first = value.split(/\r?\n/).find((line) => line.trim()) || ''
  return truncateText(first.replace(/\s+/g, ' ').trim(), limit)
}

const stripPiLaunchMarker = (value: string) => {
  if (!value) return ''
  const lines = value.split(/\r?\n/)
  const cleaned = lines
    .map((line) => line.trim())
    .filter((line) => line && line !== '[PI-LAUNCHED]')
  return cleaned.join('\n').trim()
}

const formatEventAction = (eventType: string) => {
  const normalized = eventType.trim().toLowerCase()
  if (!normalized) return 'updated quest'
  const map: Record<string, string> = {
    'idea.created': 'created idea',
    'idea.review_ready': 'reviewed idea',
    'experiment.started': 'started experiment',
    'experiment.finished': 'finished experiment',
    'write.started': 'started writing',
    'write.completed': 'completed draft',
    'write.revision_ready': 'revision ready',
    'write.review_ready': 'reviewed draft',
    'write.self_review_ready': 'self-review ready',
    'baseline.ready': 'prepared baseline',
    'pi.question': 'asked PI',
    'pi.answer': 'answered PI',
    'agent.spawned': 'spawned agent',
    'error.reported': 'reported error',
  }
  if (map[normalized]) return map[normalized]
  if (normalized.startsWith('write.')) {
    return `write ${normalized.replace('write.', '').replace(/_/g, ' ')}`
  }
  return normalized.replace(/[._]/g, ' ')
}

const extractQuestionTitle = (raw: unknown) => {
  if (!raw || typeof raw !== 'object') return ''
  const record = raw as Record<string, unknown>
  const title = normalizeText(record.title)
  if (title) return title
  const question = normalizeText(record.question)
  if (question) return question
  const description = normalizeText(record.description)
  if (description) return description
  return ''
}

const resolveResultRecord = (tool: ToolContent) => {
  const content =
    tool.content && typeof tool.content === 'object' && !Array.isArray(tool.content)
      ? (tool.content as Record<string, unknown>)
      : null
  const result =
    content?.result && typeof content.result === 'object' && !Array.isArray(content.result)
      ? (content.result as Record<string, unknown>)
      : null
  return result ?? content ?? null
}

const resolveQuestId = (tool: ToolContent, args: Record<string, unknown>, result: Record<string, unknown> | null) =>
  normalizeText(args.quest_id) ||
  normalizeText(result?.quest_id) ||
  normalizeText(tool.metadata?.quest_id)

const resolveBranch = (args: Record<string, unknown>, result: Record<string, unknown> | null) =>
  normalizeText(args.branch) || normalizeText(result?.branch)

const resolveStageKey = (args: Record<string, unknown>, result: Record<string, unknown> | null) =>
  normalizeText(args.stage_key) || normalizeText(result?.stage_key)

const resolveEventId = (args: Record<string, unknown>, result: Record<string, unknown> | null) =>
  normalizeText(args.event_id) || normalizeText(result?.event_id)

export function LabToolCard({
  tool,
  compact,
  projectId,
}: {
  tool: ToolContent
  compact?: boolean
  projectId?: string
}) {
  const isLab = isLabSurface(tool)
  const args =
    tool.args && typeof tool.args === 'object' && !Array.isArray(tool.args)
      ? (tool.args as Record<string, unknown>)
      : {}
  const hydratePhase =
    tool.metadata && typeof tool.metadata === 'object'
      ? (tool.metadata as Record<string, unknown>).hydrate_phase
      : undefined
  const isHydrating = hydratePhase === 'skeleton'
  const result = resolveResultRecord(tool)
  const kind = getMcpToolKind(tool.function || '') ?? 'lab_quests'
  const mode = normalizeMode(args.mode)
  const details: LabToolDetail[] = []
  const actions: LabToolAction[] = []

  const hasError = normalizeText(result?.error) || normalizeText(tool.content?.error)
  const successFlag =
    typeof (result as Record<string, unknown> | null)?.success === 'boolean'
      ? Boolean((result as Record<string, unknown>).success)
      : null
  const failed = Boolean(hasError) || successFlag === false

  const questId = resolveQuestId(tool, args, result)
  const branch = resolveBranch(args, result)
  const stageKey = resolveStageKey(args, result)
  const eventId = resolveEventId(args, result)

  const dispatchFocus = (payload: Record<string, unknown>) => {
    if (typeof window === 'undefined') return
    window.dispatchEvent(new CustomEvent('ds:lab:focus', { detail: payload }))
  }

  let label = 'Tool'
  let summary = ''
  let status =
    tool.status === 'calling' ? 'Running' : tool.status === 'failed' ? 'Failed' : 'Done'
  let waiting = false

  const questionIdCandidate =
    normalizeText(args.question_id) ||
    normalizeText(args.questionId) ||
    normalizeText(result?.question_id) ||
    normalizeText(result?.questionId)

  const questionTextCandidate =
    normalizeText(args.question) ||
    normalizeText(result?.question) ||
    normalizeText(args.context_md)

  const shouldLookupQuestion =
    isLab &&
    kind === 'lab_quests' &&
    (mode === 'pi_ask' || mode === 'pi_answer') &&
    Boolean(projectId && questionIdCandidate && !questionTextCandidate)

  const questionLookupQuery = useQuery({
    queryKey: ['lab-question-lookup', projectId],
    queryFn: async () => {
      if (!projectId) {
        return { pending: [] as LabPendingQuestion[], history: [] as LabQuestionHistoryItem[] }
      }
      const [pending, history] = await Promise.all([
        listLabPendingQuestions(projectId),
        listLabQuestionHistory(projectId),
      ])
      return {
        pending: pending.items ?? [],
        history: history.items ?? [],
      }
    },
    enabled: shouldLookupQuestion,
    staleTime: 30000,
  })

  const resolveQuestionFromSet = React.useCallback(
    (raw: unknown, questionId?: string) => {
      if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return ''
      const args = raw as QuestionPromptArgs & Record<string, unknown>
      const normalized = normalizeQuestions(args)
      const normalizedId = questionId ? String(questionId).trim() : ''
      if (normalizedId) {
        const match = normalized.find((question) => question.id === normalizedId)
        if (match?.text) return match.text
      }
      if (normalized.length === 1 && normalized[0]?.text) {
        return normalized[0].text
      }
      const fallback =
        normalizeText(args.question) ||
        normalizeText(args.title) ||
        normalizeText(args.prompt) ||
        normalizeText(args.text)
      return fallback
    },
    []
  )

  const resolvedQuestionFromLookup = React.useMemo(() => {
    if (!questionIdCandidate || !questionLookupQuery.data) return ''
    const items = [
      ...(questionLookupQuery.data.pending ?? []),
      ...(questionLookupQuery.data.history ?? []),
    ]
    for (const item of items) {
      const resolved = resolveQuestionFromSet(item.question_set, questionIdCandidate)
      if (resolved) return resolved
    }
    return ''
  }, [questionIdCandidate, questionLookupQuery.data, resolveQuestionFromSet])

  if (kind === 'lab_quests') {
    if (mode === 'agent') {
      label = 'Recruiting'
      const templateKey = normalizeText(args.template_key) || normalizeText(result?.template_key)
      const instructionRaw =
        normalizeText(args.initial_instruction) || normalizeText(result?.initial_instruction)
      const instruction = stripPiLaunchMarker(instructionRaw)
      summary = templateKey
        ? `DeepScientist is recruiting @${templateKey}`
        : 'DeepScientist is recruiting an agent'
      const agentInstanceId =
        normalizeText(result?.agent_instance_id) || normalizeText(args.agent_instance_id)
      const agentId = normalizeText(result?.agent_id) || normalizeText(args.agent_id)
      if (agentInstanceId) {
        actions.push({
          id: 'open-agent',
          label: 'Open Agent',
          onClick: () => dispatchFocus({ focusType: 'agent', focusId: agentInstanceId }),
        })
        actions.push({
          id: 'open-team',
          label: 'Open TEAM',
          onClick: () => dispatchFocus({ focusType: 'agent', focusId: agentInstanceId }),
        })
      }
      if (agentId) details.push({ label: 'agent_id', value: agentId })
      if (agentInstanceId) details.push({ label: 'instance_id', value: agentInstanceId })
      if (instruction) details.push({ label: 'instruction', value: instruction })
      details.push(...[
        { label: 'branch', value: branch },
        { label: 'stage', value: stageKey },
      ].filter((item) => item.value))
    } else if (mode === 'event') {
      label = 'Quest Event'
      const eventType = normalizeText(args.event_type) || normalizeText(result?.event_type)
      const actorRaw =
        normalizeText(tool.metadata?.agent_label) ||
        normalizeText(tool.metadata?.agent_id) ||
        normalizeText(tool.metadata?.agent_role)
      const actorLabel = formatActorLabel(actorRaw) || 'Agent'
      summary = `${actorLabel} ${formatEventAction(eventType)}`
      if (questId) {
        actions.push({
          id: 'open-quest',
          label: 'Open Quest',
          onClick: () => dispatchFocus({ focusType: 'quest', focusId: questId }),
        })
      }
      if (questId && branch) {
        actions.push({
          id: 'open-branch',
          label: 'Open Branch',
          onClick: () => dispatchFocus({ focusType: 'quest-branch', focusId: questId, branch }),
        })
      }
      if (eventId) details.push({ label: 'event_id', value: eventId })
      const commitHash = normalizeText(result?.commit_hash)
      if (commitHash) details.push({ label: 'commit', value: commitHash })
      const syncStatus = normalizeText(result?.sync_status)
      if (syncStatus) details.push({ label: 'sync', value: syncStatus })
      const payloadSummary = normalizeText(result?.payload_summary)
      if (payloadSummary) details.push({ label: 'summary', value: payloadSummary })
    } else if (mode === 'pi_ask') {
      label = 'Ask PI'
      const question =
        normalizeText(args.question) ||
        normalizeText(result?.question) ||
        normalizeText(args.context_md) ||
        resolvedQuestionFromLookup
      summary = question ? 'DeepScientist is asking PI' : 'DeepScientist is asking PI'
      waiting = tool.status === 'calling'
      status = waiting ? 'Waiting' : 'Done'
      if (questId) {
        actions.push({
          id: 'open-pi',
          label: 'Open PI',
          onClick: () => dispatchFocus({ focusType: 'quest', focusId: questId }),
        })
      }
      const options = normalizeList(args.options)
      if (options.length) details.push({ label: 'options', value: options.slice(0, 3).join(', ') })
      const deadline = normalizeText(args.reply_deadline_hint)
      if (deadline) details.push({ label: 'deadline', value: deadline })
      const questionId = questionIdCandidate
      if (questionId) details.push({ label: 'question_id', value: questionId })
      const answer = normalizeText(result?.answer)
      if (question) details.push({ label: 'question', value: question })
      if (answer) details.push({ label: 'answer', value: answer })
    } else if (mode === 'pi_answer') {
      label = 'PI Answer'
      const answer = normalizeText(args.answer) || normalizeText(result?.answer)
      const question =
        normalizeText(args.question) ||
        normalizeText(result?.question) ||
        normalizeText(args.context_md) ||
        resolvedQuestionFromLookup
      summary = 'DeepScientist received PI response'
      if (questId) {
        actions.push({
          id: 'open-quest',
          label: 'Open Quest',
          onClick: () => dispatchFocus({ focusType: 'quest', focusId: questId }),
        })
      }
      const decision = normalizeText(args.decision)
      if (decision) details.push({ label: 'decision', value: decision })
      const nextActions = normalizeList(args.next_actions)
      if (nextActions.length) details.push({ label: 'next', value: nextActions.slice(0, 3).join(', ') })
      const questionId = questionIdCandidate
      if (questionId) details.push({ label: 'question_id', value: questionId })
      if (question) details.push({ label: 'question', value: question })
      if (answer) details.push({ label: 'answer', value: answer })
    } else if (mode === 'events') {
      label = 'Events'
      const items = Array.isArray(result?.items) ? (result?.items as unknown[]) : []
      summary = `${items.length || 0} events${branch ? ` · ${branch}` : ''}`
      if (questId) {
        actions.push({
          id: 'view-all',
          label: 'View All',
          onClick: () => dispatchFocus({ focusType: 'quest', focusId: questId }),
        })
      }
    } else if (mode === 'audit') {
      label = 'Audit'
      const errors = Array.isArray(result?.errors) ? (result?.errors as unknown[]).length : 0
      const warnings = Array.isArray(result?.warnings) ? (result?.warnings as unknown[]).length : 0
      summary = `errors ${errors} · warnings ${warnings}`
      if (questId) {
        actions.push({
          id: 'open-report',
          label: 'Open Report',
          onClick: () => dispatchFocus({ focusType: 'quest', focusId: questId }),
        })
      }
    } else if (mode === 'inbox' || mode === 'inbox_wait') {
      label = 'Inbox'
      const items = Array.isArray(result?.items) ? (result?.items as unknown[]) : []
      waiting = tool.status === 'calling' && mode === 'inbox_wait'
      status = waiting ? 'Waiting' : 'Done'
      summary = waiting ? 'Waiting' : `${items.length || 0} new`
      if (questId) {
        actions.push({
          id: 'open-quest',
          label: 'Open',
          onClick: () => dispatchFocus({ focusType: 'quest', focusId: questId }),
        })
      }
    } else if (mode === 'baseline_bind') {
      label = 'Baseline'
      const baselinePath = normalizeText(result?.baseline_rel_path) || normalizeText(args.target_path)
      summary = baselinePath || 'Bound'
      const baselineId = normalizeText(result?.baseline_root_id) || normalizeText(args.baseline_root_id)
      if (baselineId) details.push({ label: 'baseline_id', value: baselineId })
    } else if (mode === 'create') {
      label = 'Creating Quest'
      const questTitle = normalizeText(args.title) || normalizeText(result?.title)
      const questSummary = normalizeText(args.summary) || normalizeText(result?.summary)
      summary = questTitle
        ? `DeepScientist is creating "${questTitle}"`
        : 'DeepScientist is creating a quest'
      if (questTitle) details.push({ label: 'title', value: questTitle })
      if (questSummary) details.push({ label: 'summary', value: questSummary })
      const createdQuestId = normalizeText(result?.quest_id)
      if (createdQuestId) details.push({ label: 'quest_id', value: createdQuestId })
    } else if (mode === 'read') {
      label = 'Quest'
      summary = 'Reading quests'
    }
  } else if (kind === 'lab_pi_sleep') {
    label = 'PI Waiting'
    const sleepMode = normalizeMode(args.mode)
    if (sleepMode === 'snapshot') {
      label = 'Snapshot'
      summary = 'Quest snapshot'
      if (questId) {
        actions.push({
          id: 'open-quest',
          label: 'Open Quest',
          onClick: () => dispatchFocus({ focusType: 'quest', focusId: questId }),
        })
      }
    } else if (sleepMode === 'control') {
      label = 'PI Control'
      const action = normalizeText(args.action)
      const state = normalizeText(result?.pi_state)
      summary = [action, state ? `→ ${state}` : ''].filter(Boolean).join(' ')
    } else {
      waiting = tool.status === 'calling'
      status = waiting ? 'Waiting' : 'Done'
      summary = waiting ? 'Polling for events…' : 'Wait complete'
      if (questId) {
        actions.push({
          id: 'open-latest',
          label: 'Open Latest',
          onClick: () => {
            const items = Array.isArray(result?.events) ? (result?.events as Record<string, unknown>[]) : []
            const latest = items[0]
            const eventIdValue = normalizeText(latest?.event_id)
            const branchValue = normalizeText(latest?.branch)
            if (eventIdValue) {
              dispatchFocus({
                focusType: 'quest-event',
                focusId: questId,
                branch: branchValue || branch,
                eventId: eventIdValue,
              })
              return
            }
            dispatchFocus({ focusType: 'quest', focusId: questId })
          },
        })
      }
    }
  } else if (kind === 'status_update') {
    label = 'Status'
    const message = normalizeText(args.message) || normalizeText(args.text)
    summary = message || 'Status update'
    const phase = normalizeText(args.phase)
    const step = normalizeText(args.step)
    const nextItems = normalizeList(args.next)
    if (phase) details.push({ label: 'phase', value: phase })
    if (step) details.push({ label: 'step', value: step })
    if (nextItems.length) details.push({ label: 'next', value: nextItems.slice(0, 3).join(', ') })
  } else if (kind === 'write_question') {
    label = 'Question'
    const questionSet = args.question_set
    summary = extractQuestionTitle(questionSet) || 'Awaiting answer'
    waiting = tool.status === 'calling'
    status = waiting ? 'Waiting' : 'Done'
  } else if (kind === 'write_memory') {
    label = 'Memory'
    const memMode = normalizeMode(args.mode)
    const memKind = normalizeText(args.kind)
    const memTitle = normalizeText(args.title)
    const memContent =
      normalizeText(args.content_md) ||
      normalizeText(result?.content_md) ||
      normalizeText(args.content) ||
      ''
    const memSummary =
      memTitle || extractFirstLine(memContent) || [memMode, memKind].filter(Boolean).join(' · ')
    summary = memTitle
      ? `DeepScientist is saving memory "${memTitle}"`
      : 'DeepScientist is saving memory'
    const memId = normalizeText(result?.id) || normalizeText(args.id)
    const tags = normalizeList(args.tags)
    const confidence = normalizeText(args.confidence)
    if (memId) details.push({ label: 'id', value: memId })
    if (memMode) details.push({ label: 'mode', value: memMode })
    if (memKind) details.push({ label: 'kind', value: memKind })
    if (confidence) details.push({ label: 'confidence', value: confidence })
    if (tags.length) details.push({ label: 'tags', value: tags.slice(0, 3).join(', ') })
    if (memSummary && memSummary !== memTitle) details.push({ label: 'summary', value: memSummary })
  } else if (kind === 'lab_baseline') {
    label = 'Baseline'
    const baselineMode = normalizeMode(args.mode)
    const path = normalizeText(args.target_path) || normalizeText(args.source_path)
    const modeLabel = baselineMode || 'processing'
    summary = path
      ? `DeepScientist is ${modeLabel.replace(/_/g, ' ')} ${path}`
      : `DeepScientist is ${modeLabel.replace(/_/g, ' ')} baseline`
    const baselineId = normalizeText(args.baseline_root_id) || normalizeText(result?.baseline_root_id)
    if (baselineId) details.push({ label: 'baseline_id', value: baselineId })
  }

  if (failed) status = 'Error'
  if (!summary) summary = isHydrating ? '' : '—'
  summary = toOneLine(summary)

  const statusTone = status === 'Error'
    ? 'ds-lab-status-error'
    : status === 'Done'
      ? 'ds-lab-status-done'
      : status === 'Waiting'
        ? 'ds-lab-status-waiting'
        : 'ds-lab-status-running'

  const Icon = TOOL_ICON_MAP[kind] || TOOL_ICON_MAP.default
  const timeLabel = formatRelativeTime(tool.timestamp)
  const formatElapsed = (value: number) => {
    if (!Number.isFinite(value) || value < 0) return ''
    const seconds = Math.floor(value)
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    if (mins > 0) return `${mins}:${secs.toString().padStart(2, '0')}`
    return `0:${secs.toString().padStart(2, '0')}`
  }
  const [elapsedLabel, setElapsedLabel] = React.useState(() =>
    waiting ? formatElapsed(Date.now() / 1000 - (tool.timestamp || Date.now() / 1000)) : ''
  )
  React.useEffect(() => {
    if (!waiting) return undefined
    const update = () =>
      setElapsedLabel(formatElapsed(Date.now() / 1000 - (tool.timestamp || Date.now() / 1000)))
    update()
    const timer = window.setInterval(update, 1000)
    return () => window.clearInterval(timer)
  }, [waiting, tool.timestamp])
  const [expanded, setExpanded] = React.useState(false)
  const [justUpdated, setJustUpdated] = React.useState(false)
  const prevStatus = React.useRef(tool.status)

  React.useEffect(() => {
    if (prevStatus.current !== tool.status && tool.status === 'called') {
      setJustUpdated(true)
      const timer = window.setTimeout(() => setJustUpdated(false), 180)
      return () => window.clearTimeout(timer)
    }
    prevStatus.current = tool.status
    return undefined
  }, [tool.status])

  const detailItems = details.filter((item) => item.value).slice(0, 6)
  const hiddenDetailCount = Math.max(details.filter((item) => item.value).length - detailItems.length, 0)
  const isQuestRead = kind === 'lab_quests' && mode === 'read'
  const qaQuestion = normalizeText(
    kind === 'lab_quests' && (mode === 'pi_ask' || mode === 'pi_answer')
      ? normalizeText(args.question) ||
          normalizeText(result?.question) ||
          normalizeText(args.context_md)
      : ''
  )
  const qaAnswer = normalizeText(
    kind === 'lab_quests' && (mode === 'pi_ask' || mode === 'pi_answer')
      ? normalizeText(result?.answer) || normalizeText(args.answer)
      : ''
  )

  if (!isLab) return null

  if (isQuestRead) {
    const Icon = TOOL_ICON_MAP[kind] || TOOL_ICON_MAP.default
    const timeLabel = formatRelativeTime(tool.timestamp)
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
            className={cn(
              'ai-manus-tool-chip flex w-full items-start gap-2 rounded-[12px] border border-[var(--border-light)] px-3 py-2 text-left',
              compact ? 'text-[10px]' : 'text-[11px]',
              'bg-[var(--fill-tsp-white-light)] text-[var(--text-secondary)]'
            )}
          >
            <span className="mt-[2px] inline-flex h-4 w-4 items-center justify-center text-[var(--icon-primary)]">
              <Icon className="h-4 w-4" />
            </span>
            <span className="min-w-0 flex-1 break-words">
              <span
                className={cn(
                  'block break-words font-medium text-[var(--text-secondary)]',
                  compact ? 'text-[10px]' : 'text-[11px]'
                )}
              >
                DeepScientist is reading quests...
              </span>
            </span>
          </div>
        </div>
        {!compact ? (
          <div className="text-[9px] text-[var(--text-tertiary)] opacity-0 transition group-hover:opacity-100">
            {timeLabel}
          </div>
        ) : null}
      </div>
    )
  }

  return (
    <div
      className={cn(
        'ds-lab-tool-card',
        compact && 'ds-lab-tool-card--compact',
        justUpdated && 'is-updated'
      )}
      data-status={status.toLowerCase()}
    >
      <div className="ds-lab-tool-card__header">
        <div className="ds-lab-tool-card__title">
          <Icon className="ds-lab-tool-card__icon" />
          <span className="ds-lab-tool-card__label">{label}</span>
        </div>
        <div className="ds-lab-tool-card__meta">
          <span className={cn('ds-lab-tool-card__status', statusTone)}>
            <span className={cn('ds-lab-tool-card__dot', waiting ? 'is-pulse-slow' : tool.status === 'calling' ? 'is-pulse-fast' : '')} />
            {status}
            {waiting && elapsedLabel ? ` ${elapsedLabel}` : ''}
          </span>
          <span className="ds-lab-tool-card__time">{timeLabel}</span>
        </div>
      </div>
      {isHydrating ? (
        <div className="ds-lab-tool-card__skeleton" aria-hidden="true">
          <span className="ds-lab-tool-card__skeleton-line" />
          <span className="ds-lab-tool-card__skeleton-line is-short" />
        </div>
      ) : kind === 'lab_pi_sleep' && waiting ? (
        <div className="ds-lab-tool-card__summary ds-lab-terminal-line">
          waiting for events
          <span className="ds-lab-terminal-cursor" aria-hidden="true" />
        </div>
      ) : (
        <div className="ds-lab-tool-card__summary">{summary}</div>
      )}
      {!isHydrating && (qaQuestion || qaAnswer) ? (
        <div className="ds-lab-qa">
          {qaQuestion ? (
            <div className="ds-lab-qa__row">
              <span className="ds-lab-qa__label ds-lab-qa__label--q">Q</span>
              <span className="ds-lab-qa__text">{qaQuestion}</span>
            </div>
          ) : null}
          {qaAnswer ? (
            <div className="ds-lab-qa__row">
              <span className="ds-lab-qa__label ds-lab-qa__label--a">A</span>
              <span className="ds-lab-qa__text">{qaAnswer}</span>
            </div>
          ) : null}
        </div>
      ) : null}
      {!isHydrating && actions.length > 0 ? (
        <div className="ds-lab-tool-card__actions">
          {actions.map((action) => (
            <button
              key={action.id}
              type="button"
              className="ds-lab-tool-card__action"
              onClick={action.onClick}
            >
              {action.label}
            </button>
          ))}
        </div>
      ) : null}
      {!isHydrating && detailItems.length > 0 ? (
        <div className="ds-lab-tool-card__details">
          <button
            type="button"
            className="ds-lab-tool-card__details-toggle"
            onClick={() => setExpanded((prev) => !prev)}
          >
            Details
            <span className={cn('ds-lab-tool-card__chevron', expanded && 'is-open')} />
          </button>
          {expanded ? (
            <div className="ds-lab-tool-card__details-body">
              {detailItems.map((item) => (
                <div key={item.label} className="ds-lab-tool-card__detail-row">
                  <span className="ds-lab-tool-card__detail-label">{item.label}</span>
                  <span
                    className={cn(
                      'ds-lab-tool-card__detail-value',
                      item.label === 'instruction' && 'ds-lab-tool-card__detail-value--multiline'
                    )}
                  >
                    {item.value}
                  </span>
                </div>
              ))}
              {hiddenDetailCount > 0 ? (
                <div className="ds-lab-tool-card__detail-row">
                  <span className="ds-lab-tool-card__detail-label">more</span>
                  <span className="ds-lab-tool-card__detail-value">
                    +{hiddenDetailCount} more
                  </span>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

export default LabToolCard
