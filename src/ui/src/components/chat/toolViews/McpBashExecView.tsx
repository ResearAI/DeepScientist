'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useToast } from '@/components/ui/toast'
import { getBashLogs, getBashSession } from '@/lib/api/bash'
import { useBashLogStream } from '@/lib/hooks/useBashLogStream'
import { useBashSessionStream } from '@/lib/hooks/useBashSessionStream'
import { useBashSessionResolver } from '@/lib/hooks/useBashSessionResolver'
import { EnhancedTerminal } from '@/lib/plugins/cli/components/EnhancedTerminal'
import type { ToolContent } from '@/lib/plugins/ai-manus/types'
import { useChatScrollState } from '@/lib/plugins/ai-manus/lib/chat-scroll-context'
import type { BashProgress, BashSession, BashSessionStatus } from '@/lib/types/bash'
import { formatProgressLabel, formatProgressMeta, getProgressPercent } from '@/lib/utils/bash-progress'
import {
  BASH_CARRIAGE_RETURN_PREFIX,
  isBashProgressMarker,
  parseBashProgressMarker,
  parseBashStatusMarker,
  splitBashLogLine,
  type BashStatusMarker,
} from '@/lib/utils/bash-log'
import { BashToolView } from './BashToolView'
import type { ToolViewProps } from './types'
import '@/lib/plugins/cli/styles/terminal.css'

const BASH_RESULT_KEYS = [
  'bash_id',
  'bashId',
  'status',
  'log',
  'output',
  'exit_code',
  'stop_reason',
]

const parseJsonRecord = (value: string): Record<string, unknown> | null => {
  const trimmed = value.trim()
  if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) return null
  try {
    const parsed = JSON.parse(trimmed)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
  } catch {
    return null
  }
  return null
}

const extractBashPayloadFromContent = (content: unknown) => {
  const candidates: string[] = []
  if (typeof content === 'string') {
    candidates.push(content)
  } else if (Array.isArray(content)) {
    content.forEach((entry) => {
      if (typeof entry === 'string') {
        candidates.push(entry)
        return
      }
      if (entry && typeof entry === 'object' && !Array.isArray(entry)) {
        const text = (entry as Record<string, unknown>).text
        if (typeof text === 'string') {
          candidates.push(text)
        }
      }
    })
  } else if (content && typeof content === 'object') {
    const text = (content as Record<string, unknown>).text
    if (typeof text === 'string') {
      candidates.push(text)
    }
  }

  for (const candidate of candidates) {
    const parsed = parseJsonRecord(candidate)
    if (!parsed) continue
    if (BASH_RESULT_KEYS.some((key) => key in parsed)) {
      return parsed
    }
  }
  return null
}

function extractBashResult(content?: Record<string, unknown> | null) {
  if (!content || typeof content !== 'object') return {}
  const unwrap = (value: unknown, depth = 0): Record<string, unknown> => {
    if (depth > 4) return {}
    if (typeof value === 'string') {
      const parsed = parseJsonRecord(value)
      if (parsed && BASH_RESULT_KEYS.some((key) => key in parsed)) {
        return parsed
      }
      return { log: value }
    }
    if (Array.isArray(value)) {
      const parsed = extractBashPayloadFromContent(value)
      if (parsed) return parsed
      return {}
    }
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return {}
    }
    const record = value as Record<string, unknown>
    const contentPayload = extractBashPayloadFromContent(record.content)
    if (contentPayload) return contentPayload
    const hasSignal = [...BASH_RESULT_KEYS, 'content'].some((key) => key in record)
    if (hasSignal) return record
    const nestedCandidates = [record.result, record.data, record.payload]
    for (const candidate of nestedCandidates) {
      if (!candidate) continue
      if (typeof candidate === 'string') return { log: candidate }
      if (typeof candidate === 'object' && !Array.isArray(candidate)) {
        const inner = unwrap(candidate, depth + 1)
        if (Object.keys(inner).length > 0) return inner
      }
    }
    return record
  }
  const base = (content as Record<string, unknown>).result ?? content
  return unwrap(base)
}

function normalizeWorkdir(value?: string | null) {
  if (!value) return ''
  const trimmed = value.trim()
  if (!trimmed || trimmed === '.') return ''
  return trimmed.replace(/^\.\//, '')
}

function resolvePromptLabel(workdir?: string | null) {
  const normalized = normalizeWorkdir(workdir)
  return normalized || '~'
}

function isActiveBashStatus(status?: string | null) {
  const normalized = String(status || '')
    .trim()
    .toLowerCase()
  return ['running', 'calling', 'pending', 'queued', 'starting', 'terminating'].includes(normalized)
}

const filterMarkerLines = (log: string) => {
  if (!log) return ''
  return log
    .split(/\r?\n/)
    .filter((line) => !line.startsWith('__DS_PROGRESS__') && !line.startsWith('__DS_BASH_STATUS__'))
    .filter((line) => !line.startsWith(BASH_CARRIAGE_RETURN_PREFIX))
    .join('\n')
}

function BashSessionListView({ toolContent, projectId, sessionId, panelMode, chrome }: ToolViewProps) {
  const args = toolContent.args as Record<string, unknown>
  const limit = typeof args?.limit === 'number' ? Math.max(1, Math.min(args.limit, 200)) : 80
  const statusFilter = typeof args?.status === 'string' ? args.status : undefined
  const [selectedBashId, setSelectedBashId] = useState<string | null>(
    typeof args?.id === 'string' ? args.id : null
  )
  const { sessions, connection } = useBashSessionStream({
    projectId,
    status: statusFilter,
    enabled: Boolean(projectId),
    limit,
  })

  useEffect(() => {
    if (sessions.length === 0) {
      setSelectedBashId(null)
      return
    }
    if (selectedBashId && sessions.some((session) => session.bash_id === selectedBashId)) {
      return
    }
    const next =
      sessions.find((session) => session.status === 'running' || session.status === 'terminating') ??
      sessions[0]
    setSelectedBashId(next?.bash_id ?? null)
  }, [selectedBashId, sessions])

  const selectedSession =
    sessions.find((session) => session.bash_id === selectedBashId) ?? sessions[0] ?? null
  const selectedToolContent = useMemo<ToolContent | null>(() => {
    if (!selectedSession) return null
    return {
      event_id: `${toolContent.event_id}:${selectedSession.bash_id}`,
      timestamp: Date.parse(selectedSession.started_at) || Date.now(),
      tool_call_id: selectedSession.bash_id,
      name: 'bash_exec',
      function: 'bash_exec',
      status: 'called',
      args: {
        command: selectedSession.command,
        workdir: selectedSession.workdir,
      },
      content: {
        result: {
          bash_id: selectedSession.bash_id,
          status: selectedSession.status,
          exit_code: selectedSession.exit_code,
          stop_reason: selectedSession.stop_reason,
          last_progress: selectedSession.last_progress,
        },
      },
      metadata: {
        ...(toolContent.metadata ?? {}),
        session_id:
          typeof toolContent.metadata?.session_id === 'string'
            ? toolContent.metadata.session_id
            : sessionId,
        agent_id: selectedSession.agent_id,
        agent_instance_id: selectedSession.agent_instance_id ?? undefined,
      },
    }
  }, [selectedSession, sessionId, toolContent])

  if (!projectId) {
    return <div className="text-[12px] text-[var(--text-tertiary)]">Quest context is required for bash session listing.</div>
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-[12px] border border-[var(--border-light)] bg-[var(--fill-tsp-white-light)] p-3">
        <div className="mb-2 flex min-w-0 items-center justify-between gap-3 text-[11px] text-[var(--text-tertiary)]">
          <span className="min-w-0 break-words [overflow-wrap:anywhere]">
            {sessions.length} session{sessions.length === 1 ? '' : 's'}
          </span>
          <span className="min-w-0 text-right break-words [overflow-wrap:anywhere]">
            {connection.status}
          </span>
        </div>
        <div className="flex max-h-[220px] flex-col gap-2 overflow-y-auto">
          {sessions.map((session) => {
            const progressPercent = getProgressPercent(session.last_progress)
            const progressLabel = formatProgressLabel(session.last_progress)
            const progressMeta = formatProgressMeta(session.last_progress)
            const active = session.bash_id === (selectedSession?.bash_id ?? null)
            return (
              <button
                key={session.bash_id}
                type="button"
                onClick={() => setSelectedBashId(session.bash_id)}
                className={`rounded-[12px] border px-3 py-2 text-left transition ${
                  active
                    ? 'border-[var(--border-main)] bg-[var(--background-main)]'
                    : 'border-[var(--border-light)] bg-transparent hover:bg-[var(--fill-tsp-white-light)]'
                }`}
              >
                <div className="flex min-w-0 items-start justify-between gap-3 text-[11px] text-[var(--text-tertiary)]">
                  <span className="min-w-0 break-words [overflow-wrap:anywhere]">{session.status}</span>
                  <span className="min-w-0 text-right break-words [overflow-wrap:anywhere]">
                    {session.bash_id}
                  </span>
                </div>
                <div className="mt-1 break-words text-[12px] font-medium text-[var(--text-primary)] [overflow-wrap:anywhere]">
                  {session.command}
                </div>
                <div className="mt-1 break-words text-[11px] text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
                  {session.workdir || '~'}
                  {progressPercent != null ? ` · ${progressPercent.toFixed(0)}%` : ''}
                  {progressLabel ? ` · ${progressLabel}` : ''}
                  {progressMeta ? ` · ${progressMeta}` : ''}
                </div>
              </button>
            )
          })}
          {sessions.length === 0 ? (
            <div className="rounded-[12px] border border-dashed border-[var(--border-light)] px-3 py-4 text-[12px] text-[var(--text-tertiary)]">
              No bash sessions recorded for this quest yet.
            </div>
          ) : null}
        </div>
      </div>

      {selectedToolContent ? (
        <BashToolView
          toolContent={selectedToolContent}
          live={selectedSession?.status === 'running' || selectedSession?.status === 'terminating'}
          projectId={projectId}
          panelMode={panelMode}
          chrome={chrome}
        />
      ) : null}
    </div>
  )
}

export function McpBashExecView(props: ToolViewProps) {
  const args = props.toolContent.args as Record<string, unknown>
  const rawMode = typeof args?.mode === 'string' ? args.mode : 'detach'
  const normalizedMode = rawMode.trim().toLowerCase()
  const mode = normalizedMode === 'create' ? 'await' : normalizedMode || 'detach'
  if (mode === 'list') {
    return <BashSessionListView {...props} />
  }
  return <McpBashExecSessionView {...props} />
}

function McpBashExecSessionView({
  toolContent,
  projectId,
  sessionId,
  panelMode,
  chrome = 'default',
  onLiveStateChange,
}: ToolViewProps) {
  const { addToast } = useToast()
  const args = toolContent.args as Record<string, unknown>
  const command =
    typeof args?.command === 'string'
      ? args.command
      : typeof args?.cmd === 'string'
        ? args.cmd
        : ''
  const workdir = typeof args?.workdir === 'string' ? args.workdir : ''
  const rawMode = typeof args?.mode === 'string' ? args.mode : 'detach'
  const normalizedMode = rawMode.trim().toLowerCase()
  const mode = normalizedMode === 'create' ? 'await' : normalizedMode || 'detach'
  const isInline = panelMode === 'inline'
  const showInlineHeader = isInline && chrome !== 'bare'
  const chatScrollState = useChatScrollState()
  const isChatNearBottom = chatScrollState?.isNearBottom ?? true
  const content = toolContent.content as Record<string, unknown> | undefined
  const resultPayload = useMemo(() => extractBashResult(content), [content])
  const resultBashId =
    typeof resultPayload.bash_id === 'string'
      ? resultPayload.bash_id
      : typeof (resultPayload as Record<string, unknown>).bashId === 'string'
        ? String((resultPayload as Record<string, unknown>).bashId)
        : typeof (content?.result as Record<string, unknown>)?.bash_id === 'string'
          ? String((content?.result as Record<string, unknown>)?.bash_id)
          : typeof (content?.result as Record<string, unknown>)?.bashId === 'string'
            ? String((content?.result as Record<string, unknown>)?.bashId)
            : typeof (content as Record<string, unknown>)?.bash_id === 'string'
              ? String((content as Record<string, unknown>)?.bash_id)
              : typeof (content as Record<string, unknown>)?.bashId === 'string'
                ? String((content as Record<string, unknown>)?.bashId)
                : ''
  const resultLog =
    typeof resultPayload.log === 'string'
      ? resultPayload.log
      : typeof (resultPayload as Record<string, unknown>).output === 'string'
        ? String((resultPayload as Record<string, unknown>).output)
        : typeof (resultPayload as Record<string, unknown>).content === 'string'
          ? String((resultPayload as Record<string, unknown>).content)
          : ''
  const initialStatus =
    typeof resultPayload.status === 'string' ? (resultPayload.status as BashSessionStatus) : null
  const initialExitCode =
    typeof resultPayload.exit_code === 'number' ? resultPayload.exit_code : null
  const initialStopReason =
    typeof resultPayload.stop_reason === 'string' ? resultPayload.stop_reason : ''
  const agentInstanceId =
    typeof toolContent.metadata?.agent_instance_id === 'string'
      ? toolContent.metadata?.agent_instance_id
      : null
  const agentId =
    typeof toolContent.metadata?.agent_id === 'string' ? toolContent.metadata?.agent_id : null
  const metadataSessionId =
    typeof toolContent.metadata?.session_id === 'string' ? toolContent.metadata?.session_id : null
  const isCalling = toolContent.status === 'calling'
  const keepResolverAlive = isCalling || (mode === 'detach' && !resultBashId)
  const resolverSessionId = sessionId || metadataSessionId

  const resolver = useBashSessionResolver({
    projectId,
    chatSessionId: resolverSessionId,
    agentInstanceId,
    agentId,
    command,
    workdir,
    timestamp: toolContent.timestamp,
    enabled: Boolean(
      projectId && !resultBashId && mode !== 'read' && mode !== 'kill'
    ),
    keepAlive: keepResolverAlive,
    preferChatSession: false,
  })

  const bashId = resultBashId || resolver.bashId || ''
  const showTerminal = mode !== 'read' && mode !== 'kill'
  const [sessionStatus, setSessionStatus] = useState<BashSessionStatus | null>(initialStatus)
  const [exitCode, setExitCode] = useState<number | null>(initialExitCode)
  const [stopReason, setStopReason] = useState<string>(initialStopReason)
  const [progress, setProgress] = useState<BashProgress | null>(null)
  const [loadingLogs, setLoadingLogs] = useState(false)
  const [lastSeq, setLastSeq] = useState<number | null>(null)
  const lastSeqRef = useRef<number | null>(null)
  const [logMeta, setLogMeta] = useState<{
    tailLimit?: number | null
    tailStartSeq?: number | null
  } | null>(null)
  const [logTruncated, setLogTruncated] = useState(false)

  const terminalWriteRef = useRef<(data: string, onComplete?: () => void) => void>(() => {})
  const terminalClearRef = useRef<() => void>(() => {})
  const terminalScrollRef = useRef<() => void>(() => {})
  const terminalIsAtBottomRef = useRef<() => boolean>(() => true)
  const terminalReadyRef = useRef(false)
  const pendingOutputRef = useRef('')
  const isChatNearBottomRef = useRef(isChatNearBottom)
  const hasSnapshotRef = useRef(false)
  const initialLoadAttemptedRef = useRef(false)
  const snapshotTimerRef = useRef<number | null>(null)

  useEffect(() => {
    lastSeqRef.current = lastSeq
  }, [lastSeq])

  useEffect(() => {
    isChatNearBottomRef.current = isChatNearBottom
  }, [isChatNearBottom])

  const appendToTerminal = useCallback((data: string) => {
    if (!data) return
    if (!terminalReadyRef.current) {
      pendingOutputRef.current += data
      return
    }
    const shouldAutoScroll = isInline
      ? isChatNearBottomRef.current
      : (terminalIsAtBottomRef.current?.() ?? true)
    terminalWriteRef.current?.(data, () => {
      if (shouldAutoScroll) {
        terminalScrollRef.current?.()
      }
    })
  }, [isInline])

  const resetTerminal = useCallback(() => {
    pendingOutputRef.current = ''
    if (terminalReadyRef.current) {
      terminalClearRef.current?.()
    }
  }, [])

  useEffect(() => {
    if (!isInline || !isChatNearBottom) return
    if (!terminalReadyRef.current) return
    terminalScrollRef.current?.()
  }, [isChatNearBottom, isInline])

  useEffect(() => {
    setSessionStatus(initialStatus)
    setExitCode(initialExitCode)
    setStopReason(initialStopReason)
  }, [initialExitCode, initialStatus, initialStopReason, bashId])

  useEffect(() => {
    if (resolver.session?.status) {
      setSessionStatus(resolver.session.status as BashSessionStatus)
    }
  }, [resolver.session?.status])

  useEffect(() => {
    setProgress(null)
  }, [bashId])

  useEffect(() => {
    onLiveStateChange?.({
      status: sessionStatus,
      exitCode,
      stopReason,
      progress,
    })
  }, [exitCode, onLiveStateChange, progress, sessionStatus, stopReason])

  useEffect(() => {
    const fromResult =
      resultPayload &&
      typeof resultPayload === 'object' &&
      'last_progress' in resultPayload
        ? (resultPayload as { last_progress?: BashProgress | null }).last_progress ?? null
        : null
    const fromResolver = resolver.session?.last_progress ?? null
    const nextProgress = fromResult ?? fromResolver
    if (nextProgress) {
      setProgress(nextProgress)
    }
  }, [resolver.session?.last_progress, resultPayload])

  useEffect(() => {
    if (!projectId || !bashId) return
    let active = true
    const fetchProgress = async () => {
      try {
        const session = await getBashSession(projectId, bashId)
        if (!active) return
        if (session.last_progress) {
          setProgress(session.last_progress)
        }
      } catch {
        // Ignore progress fetch errors.
      }
    }
    void fetchProgress()
    return () => {
      active = false
    }
  }, [bashId, projectId])

  useEffect(() => {
    resetTerminal()
    if (showTerminal) {
      const prompt = resolvePromptLabel(workdir)
      appendToTerminal(`${prompt}% ${command || 'bash_exec'}\n\n`)
    }
    lastSeqRef.current = null
    setLastSeq(null)
    setLogMeta(null)
    setLogTruncated(false)
    hasSnapshotRef.current = false
    initialLoadAttemptedRef.current = false
    if (snapshotTimerRef.current != null) {
      window.clearTimeout(snapshotTimerRef.current)
      snapshotTimerRef.current = null
    }
  }, [appendToTerminal, command, resetTerminal, bashId, workdir, showTerminal])

  const handleLogLine = useCallback(
    (line: string) => {
      if (isBashProgressMarker(line)) {
        const nextProgress = parseBashProgressMarker(line)
        if (nextProgress) {
          setProgress(nextProgress)
        }
        return
      }
      const marker = parseBashStatusMarker(line)
      if (marker) {
        setSessionStatus(marker.status)
        setExitCode(marker.exitCode)
        setStopReason(marker.reason)
        return
      }
      const parsed = splitBashLogLine(line)
      if (parsed.kind === 'carriage') {
        appendToTerminal(`\r\x1b[K${parsed.text}`)
        return
      }
      appendToTerminal(`${parsed.text}\n`)
    },
    [appendToTerminal]
  )

  const handleSnapshot = useCallback(
    (event: {
      bash_id: string
      tail_limit?: number | null
      latest_seq?: number | null
      lines: Array<{ seq: number; line: string }>
      progress?: BashProgress | null
    }) => {
      hasSnapshotRef.current = true
      if (snapshotTimerRef.current != null) {
        window.clearTimeout(snapshotTimerRef.current)
        snapshotTimerRef.current = null
      }
      resetTerminal()
      const prompt = resolvePromptLabel(workdir)
      appendToTerminal(`${prompt}% ${command || 'bash_exec'}\n\n`)
      lastSeqRef.current = null
      const tailLimit = typeof event.tail_limit === 'number' ? event.tail_limit : null
      const latestSeq = typeof event.latest_seq === 'number' ? event.latest_seq : null
      const tailStartSeq = tailLimit && latestSeq ? Math.max(1, latestSeq - tailLimit + 1) : null
      setLogMeta({ tailLimit, tailStartSeq })
      if (tailLimit && latestSeq && latestSeq > tailLimit) {
        setLogTruncated(true)
      } else {
        setLogTruncated(false)
      }
      if (event.progress) {
        setProgress(event.progress)
      }
      let maxSeq: number | null = latestSeq ?? null
      event.lines?.forEach((line) => {
        if (typeof line.seq === 'number') {
          maxSeq = maxSeq == null || line.seq > maxSeq ? line.seq : maxSeq
        }
        handleLogLine(line.line ?? '')
      })
      if (maxSeq != null) {
        setLastSeq(maxSeq)
      }
    },
    [appendToTerminal, command, handleLogLine, resetTerminal, workdir]
  )

  const handleLogBatch = useCallback(
    (event: { lines: Array<{ seq: number; line: string }> }) => {
      let maxSeq: number | null = null
      event.lines?.forEach((line) => {
        if (typeof line.seq === 'number') {
          if (lastSeqRef.current != null && line.seq <= lastSeqRef.current) {
            return
          }
          maxSeq = maxSeq == null || line.seq > maxSeq ? line.seq : maxSeq
        }
        handleLogLine(line.line ?? '')
      })
      if (event.lines?.length) {
        hasSnapshotRef.current = true
      }
      if (maxSeq != null) {
        const nextSeq = maxSeq
        setLastSeq((prev) => (prev == null || nextSeq > prev ? nextSeq : prev))
      }
    },
    [handleLogLine]
  )

  const loadInitialLogs = useCallback(async () => {
    if (!projectId || !bashId || mode === 'read' || mode === 'kill') return
    initialLoadAttemptedRef.current = true
    setLoadingLogs(true)
    try {
      const { entries, meta } = await getBashLogs(projectId, bashId, { limit: 200, order: 'desc' })
      const ordered = [...entries].reverse()
      setLogMeta(meta)
      if (meta?.tailStartSeq && meta.tailStartSeq > 1) {
        setLogTruncated(true)
      }
      let latestMarker: BashStatusMarker | null = null
      let maxSeq: number | null = null
      const lines: string[] = []
      ordered.forEach((entry) => {
        if (typeof entry.seq === 'number') {
          maxSeq = maxSeq == null || entry.seq > maxSeq ? entry.seq : maxSeq
        }
        const marker = parseBashStatusMarker(entry.line)
        if (marker) {
          latestMarker = marker
          return
        }
        lines.push(entry.line)
      })
      resetTerminal()
      const prompt = resolvePromptLabel(workdir)
      appendToTerminal(`${prompt}% ${command || 'bash_exec'}\n\n`)
      if (latestMarker) {
        const marker = latestMarker as BashStatusMarker
        setSessionStatus(marker.status)
        setExitCode(marker.exitCode)
        setStopReason(marker.reason)
      }
      if (lines.length > 0) {
        lines.forEach((line) => {
          handleLogLine(line)
        })
      }
      if (maxSeq != null) {
        setLastSeq(maxSeq)
      }
    } catch (error) {
      addToast({
        type: 'error',
        title: 'Failed to load logs',
        description: error instanceof Error ? error.message : 'Unable to load bash logs.',
      })
    } finally {
      setLoadingLogs(false)
    }
  }, [
    addToast,
    appendToTerminal,
    bashId,
    command,
    handleLogLine,
    mode,
    projectId,
    resetTerminal,
    workdir,
  ])

  useEffect(() => {
    if (mode !== 'read' || !resultLog) return
    if (!showTerminal) return
    resetTerminal()
    const prompt = resolvePromptLabel(workdir)
    appendToTerminal(`${prompt}% ${command || 'bash_exec'}\n\n`)
    appendToTerminal(resultLog)
  }, [appendToTerminal, command, mode, resetTerminal, resultLog, showTerminal, workdir])

  const streamEnabled = Boolean(projectId && bashId && showTerminal)
  useEffect(() => {
    if (!projectId || !bashId || mode === 'read' || mode === 'kill') return
    if (streamEnabled || loadingLogs) return
    if (lastSeq != null) return
    void loadInitialLogs()
  }, [bashId, lastSeq, loadInitialLogs, loadingLogs, mode, projectId, streamEnabled])
  const streamConnection = useBashLogStream({
    projectId,
    bashId,
    enabled: streamEnabled,
    lastEventId: lastSeq ?? undefined,
    onSnapshot: handleSnapshot,
    onLogBatch: handleLogBatch,
    onProgress: (event) => {
      setProgress(event)
    },
    onLog: (event) => {
      hasSnapshotRef.current = true
      if (snapshotTimerRef.current != null) {
        window.clearTimeout(snapshotTimerRef.current)
        snapshotTimerRef.current = null
      }
      setLoadingLogs(false)
      if (typeof event?.seq === 'number') {
        if (lastSeqRef.current != null && event.seq <= lastSeqRef.current) {
          return
        }
        setLastSeq((prev) => (prev == null || event.seq > prev ? event.seq : prev))
      }
      handleLogLine(event.line)
    },
    onGap: (event) => {
      if (event?.tail_limit) {
        setLogMeta((prev) =>
          prev?.tailLimit
            ? prev
            : { tailLimit: event.tail_limit, tailStartSeq: event.to_seq ?? null }
        )
      }
      setLogTruncated(true)
    },
    onDone: (event) => {
      if (event?.status) {
        setSessionStatus(event.status as BashSessionStatus)
      }
      if (typeof event?.exit_code === 'number') {
        setExitCode(event.exit_code)
      }
    },
  })
  useEffect(() => {
    if (!streamEnabled || !bashId || mode === 'read' || mode === 'kill') return
    if (hasSnapshotRef.current || initialLoadAttemptedRef.current) return
    if (snapshotTimerRef.current != null) return
    snapshotTimerRef.current = window.setTimeout(() => {
      snapshotTimerRef.current = null
      if (hasSnapshotRef.current || initialLoadAttemptedRef.current) return
      initialLoadAttemptedRef.current = true
      void loadInitialLogs()
    }, 1200)
    return () => {
      if (snapshotTimerRef.current != null) {
        window.clearTimeout(snapshotTimerRef.current)
        snapshotTimerRef.current = null
      }
    }
  }, [bashId, loadInitialLogs, mode, streamEnabled])
  useEffect(() => {
    if (!streamEnabled || !bashId || mode === 'read' || mode === 'kill') return
    if (hasSnapshotRef.current || initialLoadAttemptedRef.current) return
    if (streamConnection.status !== 'error') return
    initialLoadAttemptedRef.current = true
    void loadInitialLogs()
  }, [bashId, loadInitialLogs, mode, streamConnection.status, streamEnabled])

  const statusLabel = sessionStatus ?? (toolContent.status === 'calling' ? 'running' : 'completed')
  const exitCodeLabel = exitCode == null ? '' : ` | exit ${exitCode}`
  const isRunning = isActiveBashStatus(statusLabel)
  const statusReason = stopReason && stopReason !== 'none' ? stopReason.replace(/\n/g, ' ') : ''
  const truncatedLabel =
    logTruncated && logMeta?.tailLimit
      ? `Showing last ${logMeta.tailLimit} lines (older logs truncated).`
      : logTruncated
        ? 'Showing a truncated tail of the log.'
        : ''
  const showResolverHint =
    showTerminal &&
    !bashId &&
    mode !== 'read' &&
    mode !== 'kill' &&
    !keepResolverAlive &&
    (resolver.exhausted || Boolean(resolver.error))
  const inlineExit = exitCode == null ? '' : `exit ${exitCode}`
  const inlineParts = [
    statusLabel,
    inlineExit,
    statusReason,
    mode,
    workdir,
  ].filter(Boolean)
  const inlineMeta = inlineParts.join(' | ')
  const terminalBodyClass = showTerminal
    ? isInline
      ? 'cli-inline-terminal-body'
      : 'flex-1 min-h-[220px]'
    : ''
  const promptLabel = resolvePromptLabel(workdir)
  const sanitizedLog = filterMarkerLines(resultLog)
  const readOutput = sanitizedLog
    ? `${promptLabel}% ${command || 'bash_exec'}\n\n${sanitizedLog}`
    : `${promptLabel}% ${command || 'bash_exec'}\n\nNo log output returned.`
  const progressPercent = getProgressPercent(progress)
  const progressLabel = formatProgressLabel(progress)
  const progressMeta = formatProgressMeta(progress)
  const showProgress = progress != null
  const progressPercentLabel =
    progressPercent != null ? `${progressPercent.toFixed(1)}%` : 'working'

  return (
    <div
      className={
        isInline
          ? `cli-root cli-inline-terminal flex min-h-0 flex-col gap-2${isRunning ? ' cli-inline-terminal-running' : ''}${chrome === 'bare' ? ' cli-inline-terminal-bare' : ''}`
          : 'cli-root flex h-full min-h-0 flex-col gap-2'
      }
    >
      {showInlineHeader ? (
        <div className="cli-inline-terminal-header">
          <div className="cli-inline-terminal-dots" aria-hidden="true">
            <span className="cli-inline-terminal-dot cli-inline-terminal-dot-red" />
            <span className="cli-inline-terminal-dot cli-inline-terminal-dot-amber" />
            <span className="cli-inline-terminal-dot cli-inline-terminal-dot-green" />
          </div>
          <div className="cli-inline-terminal-title">bash_exec</div>
          <div className="cli-inline-terminal-meta">{inlineMeta || statusLabel}</div>
        </div>
      ) : !isInline ? (
        <div className="flex flex-wrap items-center justify-between text-[11px] text-[var(--text-tertiary)]">
          <span className="break-words [overflow-wrap:anywhere]">
            Status: {statusLabel}
            {exitCodeLabel}
            {statusReason ? ` | ${statusReason}` : ''}
            {mode ? ` | ${mode}` : ''}
            {workdir ? ` | ${workdir}` : ''}
          </span>
        </div>
      ) : null}
      {showProgress ? (
        <div
          className={isInline ? 'cli-progress cli-progress-inline' : 'cli-progress cli-progress-panel'}
        >
          <div
            className={progressPercent == null ? 'cli-progress-track cli-progress-track-pulse' : 'cli-progress-track'}
          >
            <div
              className={progressPercent == null ? 'cli-progress-bar cli-progress-bar-indeterminate' : 'cli-progress-bar'}
              style={{
                width: progressPercent == null ? '35%' : `${progressPercent}%`,
              }}
            />
          </div>
          <div className="cli-progress-meta">
            {progressLabel ? <span className="cli-progress-label">{progressLabel}</span> : null}
            <span className="cli-progress-percent">{progressPercentLabel}</span>
            {progressMeta ? <span className="cli-progress-extra">{progressMeta}</span> : null}
          </div>
        </div>
      ) : null}
      {!isInline && truncatedLabel ? <div className="text-[11px] text-amber-600">{truncatedLabel}</div> : null}
      {!isInline && showResolverHint ? (
        <div className="text-[11px] text-[var(--text-tertiary)]">
          Waiting for the durable bash session to bind. Output will appear here as soon as the session id is resolved.
        </div>
      ) : null}

      {showTerminal ? (
        <div className={terminalBodyClass}>
          <EnhancedTerminal
            onInput={() => {}}
            onResize={() => {}}
            onReady={(handlers) => {
              terminalWriteRef.current = handlers.write
              terminalClearRef.current = handlers.clear
              terminalScrollRef.current = handlers.scrollToBottom
              terminalIsAtBottomRef.current = handlers.isScrolledToBottom ?? (() => true)
            terminalReadyRef.current = true
            if (pendingOutputRef.current) {
              const shouldAutoScroll = isInline
                ? isChatNearBottomRef.current
                : (handlers.isScrolledToBottom?.() ?? true)
              handlers.write(pendingOutputRef.current, () => {
                if (shouldAutoScroll) {
                    handlers.scrollToBottom()
                  }
                })
                pendingOutputRef.current = ''
              }
            }}
            searchOpen={false}
            onSearchOpenChange={() => {}}
            appearance={isInline ? 'ui' : 'terminal'}
            autoFocus={false}
            showHeader={false}
            scrollback={logMeta?.tailLimit ?? undefined}
          />
        </div>
      ) : mode === 'read' ? (
        <div className={isInline ? 'cli-inline-terminal-read' : 'min-h-[220px]'}>
          <pre className="cli-inline-terminal-log">{readOutput}</pre>
        </div>
      ) : (
        <div className={isInline ? 'cli-inline-terminal-note' : 'min-h-[220px]'}>
          <div className="cli-inline-terminal-note-title">Command termination requested.</div>
          <div className="cli-inline-terminal-note-body">
            {statusReason ? `Reason: ${statusReason}` : 'No additional reason provided.'}
          </div>
        </div>
      )}
    </div>
  )
}

export default McpBashExecView
