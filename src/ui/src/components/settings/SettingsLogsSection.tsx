import * as React from 'react'

import { clearAdminFrontendLogs, listAdminFrontendLogs, type AdminFrontendLogEntry } from '@/lib/adminFrontendLogs'
import { getAdminLogSources, getAdminLogTail } from '@/lib/api/admin'
import { SettingsGuideCard } from '@/components/settings/SettingsGuideCard'
import { adminEnumLabel, adminLocaleFromLanguage, pickAdminCopy } from '@/components/settings/settingsOpsCopy'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/lib/i18n/useI18n'
import { useAdminOpsStore } from '@/lib/stores/admin-ops'
import type { AdminLogSourceInfo } from '@/lib/types/admin'
import { cn } from '@/lib/utils'

type LogViewMode = 'backend' | 'frontend'

const PAGE_COPY = {
  en: {
    title: 'System Logs',
    subtitle: 'Operator-facing backend and frontend log views.',
    guide: `
### What this page is for

- Use **System Logs** to inspect backend and frontend evidence without leaving Settings.
- Backend logs now expose one **system-level** runtime source instead of many fragmented candidates.
- Frontend logs capture browser console, page errors, and unhandled rejections from the current session.
`,
    backend: 'Backend',
    frontend: 'Frontend',
    refresh: 'Refresh',
    clear: 'Clear',
    tail: 'Latest Log',
    searchPlaceholder: 'Filter log lines',
    newestFirst: 'Newest first',
    backendLog: 'System Backend Log',
    noBackendLogs: 'No backend log lines available yet.',
    frontendEvents: 'Frontend Events',
    level: 'Level',
    message: 'Message',
    createdAt: 'Created',
    noFrontendLogs: 'No frontend logs captured in this browser session yet.',
  },
  zh: {
    title: '系统日志',
    subtitle: '在 Settings 内查看后端与前端日志证据。',
    guide: `
### 这一页用来做什么

- 用 **系统日志** 在不离开 Settings 的情况下查看后端与前端证据。
- 后端日志现在只暴露一个**系统级**运行时日志源，不再出现很多碎片化候选项。
- 前端日志会捕获当前浏览器会话里的 console、页面报错和未处理的 Promise 拒绝。
`,
    backend: '后端',
    frontend: '前端',
    refresh: '刷新',
    clear: '清空',
    tail: '最新日志',
    searchPlaceholder: '过滤日志内容',
    newestFirst: '最新在前',
    backendLog: '系统后端日志',
    noBackendLogs: '当前还没有可显示的后端日志。',
    frontendEvents: '前端事件',
    level: '级别',
    message: '内容',
    createdAt: '时间',
    noFrontendLogs: '当前浏览器会话里还没有捕获到前端日志。',
  },
} as const

function matchesFrontendFilter(entry: AdminFrontendLogEntry, query: string) {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return `${entry.level} ${entry.source} ${entry.message}`.toLowerCase().includes(q)
}

const surfaceClassName =
  'rounded-[28px] border border-black/[0.06] bg-[rgba(255,251,246,0.76)] shadow-[0_18px_40px_-30px_rgba(18,24,32,0.24)] backdrop-blur-sm dark:border-white/[0.08] dark:bg-white/[0.03]'
const dividerClassName = 'border-black/[0.06] dark:border-white/[0.08]'

export function SettingsLogsSection() {
  const { language } = useI18n('admin')
  const locale = adminLocaleFromLanguage(language)
  const copy = pickAdminCopy(language, PAGE_COPY)
  const [mode, setMode] = React.useState<LogViewMode>('backend')
  const [query, setQuery] = React.useState('')
  const [sources, setSources] = React.useState<AdminLogSourceInfo[]>([])
  const [selected, setSelected] = React.useState<AdminLogSourceInfo | null>(null)
  const [tail, setTail] = React.useState<string[]>([])
  const [frontendLogs, setFrontendLogs] = React.useState<AdminFrontendLogEntry[]>([])
  const [loading, setLoading] = React.useState(false)
  const setContext = useAdminOpsStore((state) => state.setContext)

  const loadTail = React.useCallback(async (source: string) => {
    setLoading(true)
    try {
      const payload = await getAdminLogTail(source, 240)
      setTail(payload.lines || [])
    } finally {
      setLoading(false)
    }
  }, [])

  const loadSources = React.useCallback(async () => {
    const payload = await getAdminLogSources()
    const items = payload.items || []
    const nextSelected = items[0] || null
    setSources(items)
    setSelected(nextSelected)
    if (nextSelected?.source) {
      await loadTail(nextSelected.source)
    } else {
      setTail([])
    }
  }, [loadTail])

  const loadFrontendLogs = React.useCallback(() => {
    setFrontendLogs(listAdminFrontendLogs())
  }, [])

  React.useEffect(() => {
    void loadSources()
    loadFrontendLogs()
    const timer = window.setInterval(() => {
      loadFrontendLogs()
    }, 1000)
    return () => window.clearInterval(timer)
  }, [loadFrontendLogs, loadSources])

  React.useEffect(() => {
    if (mode !== 'backend' || !selected?.source) {
      if (mode === 'backend') {
        setTail([])
      }
      return
    }
    setContext({
      sourcePage: '/settings/logs',
      scope: 'log',
      targets: { log_sources: [selected.source] },
      selectedPaths: selected.path ? [selected.path] : [],
    })
  }, [mode, selected, setContext])

  const filteredTail = React.useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return tail
    return tail.filter((line) => line.toLowerCase().includes(q))
  }, [query, tail])
  const filteredFrontendLogs = React.useMemo(() => frontendLogs.filter((item) => matchesFrontendFilter(item, query)), [frontendLogs, query])

  return (
    <div className="space-y-5">
      <SettingsGuideCard markdown={copy.guide} />

      <div className={surfaceClassName}>
        <div className="px-4 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{copy.title}</div>
              <div className="mt-1 text-xs leading-5 text-muted-foreground">{copy.subtitle}</div>
            </div>
            <div className="flex flex-wrap gap-2" role="tablist" aria-label={copy.title}>
              {([
                { key: 'backend', label: copy.backend },
                { key: 'frontend', label: copy.frontend },
              ] as const).map((item) => (
                <button
                  key={item.key}
                  type="button"
                  role="tab"
                  aria-selected={mode === item.key}
                  onClick={() => setMode(item.key)}
                  className={cn(
                    'relative inline-flex items-center rounded-full border px-3 py-2 text-sm font-medium transition',
                    mode === item.key
                      ? 'border-[#C7A57A] bg-[linear-gradient(180deg,rgba(222,196,158,0.28),rgba(222,196,158,0.12))] text-foreground shadow-[0_12px_24px_-18px_rgba(145,102,53,0.45)] dark:border-[#C7A57A]/70 dark:bg-[linear-gradient(180deg,rgba(199,165,122,0.18),rgba(199,165,122,0.06))]'
                      : 'border-black/[0.08] bg-white/65 text-muted-foreground hover:border-black/[0.12] hover:text-foreground dark:border-white/[0.08] dark:bg-white/[0.03] dark:hover:border-white/[0.14]'
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-3">
            <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={copy.searchPlaceholder} className="max-w-md" />
            {mode === 'backend' ? (
              <Button variant="outline" size="sm" onClick={() => void loadSources()} isLoading={loading}>
                {copy.refresh}
              </Button>
            ) : (
              <>
                <Button variant="outline" size="sm" onClick={() => loadFrontendLogs()}>
                  {copy.refresh}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    clearAdminFrontendLogs()
                    loadFrontendLogs()
                  }}
                >
                  {copy.clear}
                </Button>
              </>
            )}
          </div>
        </div>
      </div>

      {mode === 'backend' ? (
        <section className={`${surfaceClassName} overflow-hidden`}>
          <div className={`flex items-center justify-between gap-3 border-b ${dividerClassName} px-5 py-4`}>
            <div>
              <div className="text-sm font-medium">{selected?.filename || copy.backendLog}</div>
              <div className="mt-1 text-xs text-muted-foreground">{copy.newestFirst}</div>
            </div>
            <div className="flex items-center gap-3">
              <Badge variant="secondary">{sources.length || 1}</Badge>
              <Button variant="outline" size="sm" onClick={() => selected?.source && void loadTail(selected.source)} isLoading={loading}>
                {copy.refresh}
              </Button>
            </div>
          </div>
          <div className="min-h-0 px-5 py-5">
            <div className="max-h-[70vh] min-h-[360px] overflow-auto rounded-[22px] bg-black px-4 py-3 font-mono text-xs leading-6 text-[#EAE7E0]">
              {filteredTail.length ? filteredTail.map((line, index) => <div key={`${index}-${line}`}>{line}</div>) : <div>{copy.noBackendLogs}</div>}
            </div>
          </div>
        </section>
      ) : (
        <section className={`${surfaceClassName} overflow-hidden`}>
          <div className={`flex items-center justify-between gap-3 border-b ${dividerClassName} px-5 py-4`}>
            <div className="text-sm font-medium">{copy.frontendEvents}</div>
            <Badge variant="secondary">{filteredFrontendLogs.length}</Badge>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{copy.createdAt}</TableHead>
                <TableHead>{copy.level}</TableHead>
                <TableHead>{copy.message}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredFrontendLogs.length > 0 ? (
                filteredFrontendLogs.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="whitespace-nowrap text-xs text-soft-text-secondary">{item.created_at}</TableCell>
                    <TableCell>
                      <Badge variant={item.level === 'error' || item.level === 'pageerror' || item.level === 'rejection' ? 'destructive' : item.level === 'warn' ? 'warning' : 'secondary'}>
                        {item.level}
                      </Badge>
                    </TableCell>
                    <TableCell className="max-w-[920px] whitespace-pre-wrap break-words font-mono text-xs leading-6 text-soft-text-secondary">{item.message}</TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={3} className="py-8 text-center text-sm text-soft-text-secondary">
                    {copy.noFrontendLogs}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </section>
      )}
    </div>
  )
}
