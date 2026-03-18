'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/components/ui/toast'
import { getBashLogs, getBashSession, stopBashSession } from '@/lib/api/bash'
import { useBashLogStream } from '@/lib/hooks/useBashLogStream'
import { EnhancedTerminal } from '@/lib/plugins/cli/components/EnhancedTerminal'
import { useChatScrollState } from '@/lib/plugins/ai-manus/lib/chat-scroll-context'
import type { BashProgress, BashSessionStatus } from '@/lib/types/bash'
import {
  isBashProgressMarker,
  parseBashProgressMarker,
  parseBashStatusMarker,
  splitBashLogLine,
} from '@/lib/utils/bash-log'
import { formatProgressLabel, formatProgressMeta, getProgressPercent } from '@/lib/utils/bash-progress'
import type { ToolViewProps } from './types'
import '@/lib/plugins/cli/styles/terminal.css'

function extractBashResult(content?: Record<string, unknown> | null) {
  if (!content || typeof content !== 'object') return {}
  const result = content.result
  if (result && typeof result === 'object') {
    return result as Record<string, unknown>
  }
  return content
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

export function BashToolView({
  toolContent,
  projectId,
  readOnly,
  panelMode,
  chrome = 'default',
}: ToolViewProps) {
  const { addToast } = useToast()
  const args = toolContent.args as Record<string, unknown>
  const command = typeof args?.command === 'string' ? args.command : ''
  const workdir = typeof args?.workdir === 'string' ? args.workdir : ''
  const content = toolContent.content as Record<string, unknown> | undefined
  const resultPayload = useMemo(() => extractBashResult(content), [content])
  const bashId = typeof resultPayload.bash_id === 'string' ? resultPayload.bash_id : ''
  const initialStatus =
    typeof resultPayload.status === 'string' ? (resultPayload.status as BashSessionStatus) : null
  const initialExitCode =
    typeof resultPayload.exit_code === 'number' ? resultPayload.exit_code : null
  const initialStopReason =
    typeof resultPayload.stop_reason === 'string' ? resultPayload.stop_reason : ''
  const isInline = panelMode === 'inline'
  const chatScrollState = useChatScrollState()
  const isChatNearBottom = chatScrollState?.isNearBottom ?? true

  const [sessionStatus, setSessionStatus] = useState<BashSessionStatus | null>(initialStatus)
  const [exitCode, setExitCode] = useState<number | null>(initialExitCode)
  const [stopReason, setStopReason] = useState<string>(initialStopReason)
  const [progress, setProgress] = useState<BashProgress | null>(null)
  const [loadingLogs, setLoadingLogs] = useState(false)
  const [stopDialogOpen, setStopDialogOpen] = useState(false)
  const [stopNote, setStopNote] = useState('')
  const [stopLoading, setStopLoading] = useState(false)
  const [lastSeq, setLastSeq] = useState<number | null>(null)
  const lastSeqRef = useRef<number | null>(null)
  const [logMeta, setLogMeta] = useState<{ tailLimit?: number | null; tailStartSeq?: number | null } | null>(
    null
  )
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
    setProgress(null)
  }, [bashId])

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
        // Ignore session fetch errors; progress is optional.
      }
    }
    void fetchProgress()
    return () => {
      active = false
    }
  }, [bashId, projectId])

  useEffect(() => {
    resetTerminal()
    const prompt = resolvePromptLabel(workdir)
    appendToTerminal(`${prompt}% ${command || 'bash_exec'}\n\n`)
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
  }, [appendToTerminal, command, resetTerminal, bashId, workdir])

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

  const loadInitialLogs = useCallback(async () => {
    if (!projectId || !bashId) return
    initialLoadAttemptedRef.current = true
    setLoadingLogs(true)
    try {
      const { entries, meta } = await getBashLogs(projectId, bashId, { limit: 200, order: 'desc' })
      const ordered = [...entries].reverse()
      setLogMeta(meta)
      if (meta?.tailStartSeq && meta.tailStartSeq > 1) {
        setLogTruncated(true)
      }
      let latestMarker: ReturnType<typeof parseBashStatusMarker> | null = null
      let maxSeq: number | null = null
      const lines: string[] = []
      for (const entry of ordered) {
        if (typeof entry.seq === 'number') {
          maxSeq = maxSeq == null || entry.seq > maxSeq ? entry.seq : maxSeq
        }
        const marker = parseBashStatusMarker(entry.line)
        if (marker) {
          latestMarker = marker
          continue
        }
        lines.push(entry.line)
      }
      if (maxSeq != null) {
        setLastSeq(maxSeq)
      }
      if (latestMarker) {
        setSessionStatus(latestMarker.status)
        setExitCode(latestMarker.exitCode)
        setStopReason(latestMarker.reason)
      }
      if (lines.length > 0) {
        const prompt = resolvePromptLabel(workdir)
        resetTerminal()
        appendToTerminal(`${prompt}% ${command || 'bash_exec'}\n\n`)
        lines.forEach((line) => {
          handleLogLine(line)
        })
      } else {
        const prompt = resolvePromptLabel(workdir)
        resetTerminal()
        appendToTerminal(`${prompt}% ${command || 'bash_exec'}\n\n`)
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
    projectId,
    resetTerminal,
    workdir,
  ])

  const streamEnabled = Boolean(bashId && projectId)

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
      setLoadingLogs(false)
      resetTerminal()
      const prompt = resolvePromptLabel(workdir)
      appendToTerminal(`${prompt}% ${command || 'bash_exec'}\n\n`)
      lastSeqRef.current = null
      const tailLimit = typeof event.tail_limit === 'number' ? event.tail_limit : null
      const latestSeq = typeof event.latest_seq === 'number' ? event.latest_seq : null
      const tailStartSeq =
        tailLimit && latestSeq ? Math.max(1, latestSeq - tailLimit + 1) : null
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
      if (event.lines?.length) {
        hasSnapshotRef.current = true
        setLoadingLogs(false)
      }
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
      if (maxSeq != null) {
        const nextSeq = maxSeq
        setLastSeq((prev) => (prev == null || nextSeq > prev ? nextSeq : prev))
      }
    },
    [handleLogLine]
  )

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
      setLoadingLogs(false)
      if (typeof event?.seq === 'number') {
        if (lastSeqRef.current != null && event.seq <= lastSeqRef.current) {
          return
        }
        setLastSeq(event.seq)
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
      setLoadingLogs(false)
      if (event?.status) {
        setSessionStatus(event.status as BashSessionStatus)
      }
      if (typeof event?.exit_code === 'number') {
        setExitCode(event.exit_code)
      }
    },
  })

  useEffect(() => {
    if (!streamEnabled || !bashId) return
    if (hasSnapshotRef.current || initialLoadAttemptedRef.current) return
    if (snapshotTimerRef.current != null) return
    setLoadingLogs(true)
    snapshotTimerRef.current = window.setTimeout(() => {
      snapshotTimerRef.current = null
      if (hasSnapshotRef.current || initialLoadAttemptedRef.current) return
      void loadInitialLogs()
    }, 700)
    return () => {
      if (snapshotTimerRef.current != null) {
        window.clearTimeout(snapshotTimerRef.current)
        snapshotTimerRef.current = null
      }
    }
  }, [bashId, loadInitialLogs, streamEnabled])

  useEffect(() => {
    if (!streamEnabled || !bashId) return
    if (hasSnapshotRef.current || initialLoadAttemptedRef.current) return
    if (streamConnection.status !== 'error') return
    void loadInitialLogs()
  }, [bashId, loadInitialLogs, streamConnection.status, streamEnabled])

  const showStopButton = Boolean(!readOnly && bashId && isActiveBashStatus(sessionStatus))
  const statusLabel = sessionStatus ?? (toolContent.status === 'calling' ? 'running' : 'completed')
  const exitCodeLabel = exitCode == null ? '' : ` | exit ${exitCode}`
  const isRunning = isActiveBashStatus(statusLabel)
  const statusReason =
    stopReason && stopReason !== 'none' ? stopReason.replace(/\n/g, ' ') : ''
  const truncatedLabel =
    logTruncated && logMeta?.tailLimit
      ? `Showing last ${logMeta.tailLimit} lines (older logs truncated).`
      : logTruncated
        ? 'Showing a truncated tail of the log.'
        : ''
  const inlineExit = exitCode == null ? '' : `exit ${exitCode}`
  const inlineParts = [statusLabel, inlineExit, statusReason, workdir].filter(Boolean)
  const inlineMeta = inlineParts.join(' | ')
  const terminalBodyClass = isInline ? 'cli-inline-terminal-body' : 'flex-1 min-h-[220px]'
  const showInlineHeader = isInline && chrome !== 'bare'
  const progressPercent = getProgressPercent(progress)
  const progressLabel = formatProgressLabel(progress)
  const progressMeta = formatProgressMeta(progress)
  const showProgress = progress != null
  const progressPercentLabel =
    progressPercent != null ? `${progressPercent.toFixed(1)}%` : 'working'

  const handleStop = useCallback(async () => {
    if (!projectId || !bashId) return
    setStopLoading(true)
    try {
      await stopBashSession(projectId, bashId, {
        reason: stopNote.trim() || undefined,
      })
      setStopDialogOpen(false)
      setStopNote('')
      addToast({
        type: 'success',
        title: 'Stop requested',
        description: 'The bash session is being terminated.',
      })
    } catch (error) {
      addToast({
        type: 'error',
        title: 'Stop failed',
        description: error instanceof Error ? error.message : 'Unable to stop bash session.',
      })
    } finally {
      setStopLoading(false)
    }
  }, [addToast, bashId, projectId, stopNote])

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
          {showStopButton ? (
            <Button
              variant="destructive"
              size="sm"
              className="cli-inline-terminal-stop"
              onClick={() => setStopDialogOpen(true)}
            >
              STOP
            </Button>
          ) : null}
        </div>
      ) : !isInline ? (
        <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-[var(--text-tertiary)]">
          <span className="break-words [overflow-wrap:anywhere]">
            Status: {statusLabel}
            {exitCodeLabel}
            {statusReason ? ` | ${statusReason}` : ''}
          </span>
          {showStopButton ? (
            <Button variant="destructive" size="sm" onClick={() => setStopDialogOpen(true)}>
              STOP
            </Button>
          ) : null}
        </div>
      ) : null}
      {isInline && chrome === 'bare' && showStopButton ? (
        <div className="flex justify-end">
          <Button
            variant="destructive"
            size="sm"
            className="cli-inline-terminal-stop"
            onClick={() => setStopDialogOpen(true)}
          >
            STOP
          </Button>
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

      {!isInline && loadingLogs ? <div className="text-[11px] text-[var(--text-tertiary)]">Loading logs...</div> : null}

      <Dialog open={stopDialogOpen} onOpenChange={setStopDialogOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Stop this bash session?</DialogTitle>
            <DialogDescription>
              This will terminate the running command and append a stop marker to the log.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <div className="text-xs text-[var(--text-secondary)]">Optional reason</div>
            <Textarea
              value={stopNote}
              onChange={(event) => setStopNote(event.target.value)}
              placeholder="Why stop this run?"
              className="min-h-[100px] text-xs"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setStopDialogOpen(false)} disabled={stopLoading}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleStop} isLoading={stopLoading}>
              STOP
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default BashToolView
