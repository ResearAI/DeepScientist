import { Bug, ChevronDown, ChevronUp, Clipboard, Download } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useWebDebug } from '@/lib/debug/useWebDebug'
import { cn } from '@/lib/utils'
import { webDebugSnapshotToJson } from '@/lib/debug/debugSnapshot'

function copyText(text: string) {
  if (navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text)
  }
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', 'true')
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  document.body.appendChild(textarea)
  textarea.select()
  document.execCommand('copy')
  document.body.removeChild(textarea)
  return Promise.resolve()
}

function downloadJsonl(text: string) {
  const blob = new Blob([text.endsWith('\n') ? text : `${text}\n`], { type: 'application/x-ndjson;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `deepscientist-web-debug-${new Date().toISOString().replace(/[:.]/g, '-')}.jsonl`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

function fieldRows(items: Array<[string, string | number | boolean | null | undefined]>) {
  return items.map(([label, value]) => (
    <div key={label} className="grid grid-cols-[96px_minmax(0,1fr)] gap-2 text-xs leading-5">
      <span className="text-muted-foreground">{label}</span>
      <span className="min-w-0 break-all font-mono text-[11px] text-foreground">{value === null || value === undefined || value === '' ? '-' : String(value)}</span>
    </div>
  ))
}

export function WebDebugInspector() {
  const { enabled, snapshot, logEnabled, logLines, clearLog } = useWebDebug()
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)
  const jsonText = useMemo(() => webDebugSnapshotToJson(snapshot), [snapshot])

  if (!enabled) {
    return null
  }

  const latestApi = snapshot.api.recent[0] ?? null
  const jsonlText = logLines.length > 0 ? logLines.join('\n') : jsonText

  return (
    <div className="fixed bottom-4 right-4 z-[110] max-w-[calc(100vw-2rem)] font-project" data-testid="web-debug-inspector">
      {expanded ? (
        <div className="w-[min(520px,calc(100vw-2rem))] overflow-hidden rounded-lg border border-black/15 bg-background/95 text-foreground shadow-[0_24px_80px_-36px_rgba(15,23,42,0.55)] backdrop-blur-xl dark:border-white/15">
          <div className="flex items-center justify-between gap-3 border-b border-black/10 px-3 py-2 dark:border-white/10">
            <div className="flex min-w-0 items-center gap-2">
              <Bug className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="truncate text-sm font-semibold">Web Debug</span>
              <Badge variant={snapshot.api.last_error ? 'destructive' : 'secondary'} size="sm">
                {snapshot.connection_state}
              </Badge>
            </div>
            <button
              type="button"
              className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition hover:bg-black/5 hover:text-foreground dark:hover:bg-white/10"
              aria-label="Collapse Web Debug"
              onClick={() => setExpanded(false)}
            >
              <ChevronDown className="h-4 w-4" />
            </button>
          </div>

          <div className="max-h-[min(72vh,720px)] overflow-y-auto px-3 py-3">
            <div className="space-y-1">
              {fieldRows([
                ['surface', snapshot.surface],
                ['route', `${snapshot.route.pathname}${snapshot.route.search}${snapshot.route.hash}`],
                ['selected', snapshot.screen.selected],
                ['status', snapshot.status_line],
                ['api', latestApi ? `${latestApi.method} ${latestApi.path} -> ${latestApi.status ?? 'ERR'} (${latestApi.duration_ms}ms)` : null],
              ])}
            </div>

            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {Object.entries(snapshot.counts).map(([name, value]) => (
                <div key={name} className="rounded-md border border-black/10 px-2 py-1.5 dark:border-white/10">
                  <div className="truncate text-[10px] uppercase text-muted-foreground">{name}</div>
                  <div className="mt-0.5 font-mono text-sm">{value}</div>
                </div>
              ))}
            </div>

            <div className="mt-3 grid gap-1">
              {Object.entries(snapshot.flags).map(([name, value]) => (
                <div key={name} className="flex items-center justify-between gap-2 text-xs">
                  <span className="text-muted-foreground">{name}</span>
                  <Badge variant={value ? 'warning' : 'secondary'} size="sm">
                    {String(value)}
                  </Badge>
                </div>
              ))}
            </div>

            <div className="mt-3 border-t border-black/10 pt-3 dark:border-white/10">
              <div className="mb-2 text-[11px] font-semibold uppercase text-muted-foreground">Actions</div>
              <div className="space-y-1">
                {Object.entries(snapshot.actions).map(([name, action]) => (
                  <div key={name} className="grid grid-cols-[92px_72px_minmax(0,1fr)] gap-2 text-xs leading-5">
                    <span className="font-mono text-[11px]">{name}</span>
                    <span className={cn(action.enabled ? 'text-emerald-700 dark:text-emerald-300' : 'text-muted-foreground')}>
                      {action.enabled ? 'enabled' : 'disabled'}
                    </span>
                    <span className="min-w-0 break-words text-muted-foreground">{action.reason || '-'}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-3 border-t border-black/10 pt-3 dark:border-white/10">
              <div className="mb-2 flex items-center justify-between gap-2">
              <div className="text-[11px] font-semibold uppercase text-muted-foreground">Snapshot JSON</div>
              <Badge variant={snapshot.redaction.applied ? 'warning' : 'secondary'} size="sm">
                  {logEnabled ? `${logLines.length} log lines` : `redaction ${snapshot.redaction.applied ? 'on' : 'ready'}`}
              </Badge>
              </div>
              <pre
                className="max-h-52 overflow-auto rounded-md border border-black/10 bg-black/[0.035] p-2 text-[11px] leading-5 dark:border-white/10 dark:bg-white/[0.045]"
                data-testid="web-debug-json"
              >
                {jsonText}
              </pre>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2 border-t border-black/10 px-3 py-2 dark:border-white/10">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="rounded-md"
              onClick={() => {
                void copyText(jsonText).then(() => {
                  setCopied(true)
                  window.setTimeout(() => setCopied(false), 1200)
                })
              }}
            >
              <Clipboard className="mr-2 h-3.5 w-3.5" />
              {copied ? 'Copied' : 'Copy JSON'}
            </Button>
            <Button type="button" variant="outline" size="sm" className="rounded-md" onClick={() => downloadJsonl(jsonlText)}>
              <Download className="mr-2 h-3.5 w-3.5" />
              Download JSONL
            </Button>
            {logLines.length > 0 ? (
              <Button type="button" variant="ghost" size="sm" className="rounded-md" onClick={clearLog}>
                Clear Log
              </Button>
            ) : null}
          </div>
        </div>
      ) : (
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-lg border border-black/15 bg-background/95 px-3 py-2 text-xs font-semibold shadow-[0_18px_64px_-32px_rgba(15,23,42,0.6)] backdrop-blur-xl transition hover:bg-accent dark:border-white/15"
          onClick={() => setExpanded(true)}
          data-testid="web-debug-toggle"
        >
          <Bug className="h-4 w-4 text-muted-foreground" />
          Web Debug
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        </button>
      )}
    </div>
  )
}
