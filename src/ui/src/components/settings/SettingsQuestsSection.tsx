import * as React from 'react'
import { Link } from 'react-router-dom'

import { SettingsGuideCard } from '@/components/settings/SettingsGuideCard'
import { adminEnumLabel, adminLocaleFromLanguage, pickAdminCopy } from '@/components/settings/settingsOpsCopy'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { getAdminQuests } from '@/lib/api/admin'
import { client } from '@/lib/api'
import { useI18n } from '@/lib/i18n/useI18n'
import { useAdminOpsStore } from '@/lib/stores/admin-ops'
import type { QuestSummary } from '@/types'

const surfaceClassName =
  'rounded-[28px] border border-black/[0.06] bg-[rgba(255,251,246,0.76)] shadow-[0_18px_40px_-30px_rgba(18,24,32,0.24)] backdrop-blur-sm dark:border-white/[0.08] dark:bg-white/[0.03]'
const dividerClassName = 'border-black/[0.06] dark:border-white/[0.08]'

const PAGE_COPY = {
  en: {
    title: 'Quest Supervision',
    subtitle: 'Filter, inspect, and control all quests from one table.',
    guide: `
### What this page is for

- Use **Quest Supervision** to filter the full quest list and quickly decide which quest needs attention.
- This table is deliberately **summary-based**. It should stay fast even when the number of quests grows.

### How to use it

- Filter by free text when you know the quest id, title, runner, or anchor.
- Use **Open** for deeper inspection.
- Use **Pause / Resume / Stop** only when you already understand the blast radius.

### Signals

- **decisions** means the quest is waiting for a human or operator judgment.
- **queued** means user requests are waiting in the mailbox.
- **bash** means quest-local execution is still active in the background.
`,
    allQuests: 'All Quests',
    searchPlaceholder: 'Search by id, title, anchor, runner, or mode',
    allStatuses: 'All statuses',
    refresh: 'Refresh',
    quest: 'Quest',
    status: 'Status',
    mode: 'Mode',
    anchor: 'Anchor',
    runner: 'Runner',
    signals: 'Signals',
    actions: 'Actions',
    open: 'Open',
    analytics: 'Activity',
    pause: 'Pause',
    resume: 'Resume',
    stop: 'Stop',
    decisions: 'decisions',
    queued: 'queued',
    bash: 'bash',
  },
  zh: {
    title: 'Quest 监管',
    subtitle: '在一张表里筛选、检查并控制所有 quests。',
    guide: `
### 这一页用来做什么

- 用 **Quest 监管** 快速筛查完整 quest 列表，并判断哪个 quest 需要优先关注。
- 这张表刻意保持 **摘要化**，即使 quest 数量增加，也应当保持足够快。

### 怎么使用

- 当你已经知道 quest id、标题、runner 或阶段时，可以先用自由文本过滤。
- 需要更深检查时，再点 **打开**。
- 只有在你已经清楚影响范围时，才去使用 **暂停 / 恢复 / 停止**。

### 信号说明

- **决策** 表示这个 quest 正在等待人工或运维判断。
- **排队** 表示用户请求还在邮箱里等待处理。
- **bash** 表示 quest 本地执行仍在后台进行。
`,
    allQuests: '全部 Quests',
    searchPlaceholder: '按 id、标题、阶段、runner 或模式搜索',
    allStatuses: '全部状态',
    refresh: '刷新',
    quest: 'Quest',
    status: '状态',
    mode: '模式',
    anchor: '阶段',
    runner: 'Runner',
    signals: '信号',
    actions: '操作',
    open: '打开',
    analytics: '活动',
    pause: '暂停',
    resume: '恢复',
    stop: '停止',
    decisions: '决策',
    queued: '排队',
    bash: 'bash',
  },
} as const

function matchesFilter(item: QuestSummary, query: string, status: string) {
  const q = query.trim().toLowerCase()
  if (q) {
    const fields = [item.quest_id, item.title, item.active_anchor, item.runner, item.workspace_mode]
    if (!fields.some((value) => String(value || '').toLowerCase().includes(q))) {
      return false
    }
  }
  if (status && String(item.runtime_status || item.status || '').trim().toLowerCase() !== status) {
    return false
  }
  return true
}

function statusVariant(status?: string | null): 'secondary' | 'warning' | 'success' | 'destructive' {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'completed') return 'success'
  if (normalized === 'failed' || normalized === 'error') return 'destructive'
  if (normalized === 'running' || normalized === 'active') return 'warning'
  return 'secondary'
}

export function SettingsQuestsSection() {
  const { language } = useI18n('admin')
  const locale = adminLocaleFromLanguage(language)
  const copy = pickAdminCopy(language, PAGE_COPY)
  const [items, setItems] = React.useState<QuestSummary[]>([])
  const [loading, setLoading] = React.useState(true)
  const [query, setQuery] = React.useState('')
  const [status, setStatus] = React.useState('')
  const [actionKey, setActionKey] = React.useState('')
  const setContext = useAdminOpsStore((state) => state.setContext)

  const load = React.useCallback(async () => {
    setLoading(true)
    try {
      const payload = await getAdminQuests(200)
      setItems(payload.items || [])
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(), 10000)
    return () => window.clearInterval(timer)
  }, [load])

  const filtered = React.useMemo(() => items.filter((item) => matchesFilter(item, query, status)), [items, query, status])

  const runAction = React.useCallback(async (questId: string, action: 'pause' | 'resume' | 'stop') => {
    setActionKey(`${questId}:${action}`)
    try {
      await client.controlQuest(questId, action)
      await load()
    } finally {
      setActionKey('')
    }
  }, [load])

  return (
    <div className="space-y-5">
      <SettingsGuideCard markdown={copy.guide} />

      <section className={`${surfaceClassName} overflow-hidden`}>
        <div className={`flex flex-col gap-4 border-b ${dividerClassName} px-5 py-4 xl:flex-row xl:items-center xl:justify-between`}>
          <div>
            <div className="text-sm font-medium">{copy.allQuests}</div>
            <div className="mt-1 text-xs text-muted-foreground">{copy.subtitle}</div>
          </div>
          <div className="flex flex-wrap gap-3">
            <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={copy.searchPlaceholder} className="min-w-[260px] max-w-md" />
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              className="h-9 rounded-full border border-input bg-background px-4 text-sm"
            >
              <option value="">{copy.allStatuses}</option>
              <option value="active">{adminEnumLabel('active', locale)}</option>
              <option value="running">{adminEnumLabel('running', locale)}</option>
              <option value="paused">{adminEnumLabel('paused', locale)}</option>
              <option value="stopped">{adminEnumLabel('stopped', locale)}</option>
              <option value="completed">{adminEnumLabel('completed', locale)}</option>
            </select>
            <Button variant="outline" size="sm" onClick={() => void load()} isLoading={loading}>
              {copy.refresh}
            </Button>
          </div>
        </div>

        <div className={`flex items-center justify-between gap-3 border-b ${dividerClassName} px-5 py-3 text-xs text-muted-foreground`}>
          <span>{filtered.length} / {items.length}</span>
          <span>{copy.signals}</span>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{copy.quest}</TableHead>
              <TableHead>{copy.status}</TableHead>
              <TableHead>{copy.mode}</TableHead>
              <TableHead>{copy.anchor}</TableHead>
              <TableHead>{copy.runner}</TableHead>
              <TableHead>{copy.signals}</TableHead>
              <TableHead>{copy.actions}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((item) => (
              <TableRow
                key={item.quest_id}
                onMouseEnter={() =>
                  setContext({
                    sourcePage: '/settings/quests',
                    scope: 'quest',
                    targets: { quest_ids: [item.quest_id] },
                  })
                }
              >
                <TableCell>
                  <Link to={`/settings/quests/${encodeURIComponent(item.quest_id)}`} className="font-medium hover:underline">
                    {item.title || item.quest_id}
                  </Link>
                  <div className="text-xs text-soft-text-secondary">{item.quest_id}</div>
                </TableCell>
                <TableCell>
                  <Badge variant={statusVariant(item.runtime_status || item.status)}>
                    {adminEnumLabel(item.runtime_status || item.status, locale)}
                  </Badge>
                </TableCell>
                <TableCell>{adminEnumLabel(item.workspace_mode || 'quest', locale)}</TableCell>
                <TableCell>{item.active_anchor || 'baseline'}</TableCell>
                <TableCell>{item.runner || 'codex'}</TableCell>
                <TableCell className="text-xs text-soft-text-secondary">
                  {(item.counts?.pending_decision_count || 0)} {copy.decisions} · {(item.counts?.pending_user_message_count || 0)} {copy.queued} · {(item.counts?.bash_running_count || 0)} {copy.bash}
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" asChild>
                      <Link to={`/settings/quests/${encodeURIComponent(item.quest_id)}`}>{copy.open}</Link>
                    </Button>
                    <Button size="sm" variant="outline" asChild>
                      <Link to={`/settings/quests/${encodeURIComponent(item.quest_id)}?view=activity&focus=activity-hourly`}>{copy.analytics}</Link>
                    </Button>
                    <Button size="sm" variant="outline" isLoading={actionKey === `${item.quest_id}:pause`} onClick={() => void runAction(item.quest_id, 'pause')}>
                      {copy.pause}
                    </Button>
                    <Button size="sm" variant="outline" isLoading={actionKey === `${item.quest_id}:resume`} onClick={() => void runAction(item.quest_id, 'resume')}>
                      {copy.resume}
                    </Button>
                    <Button size="sm" variant="destructive" isLoading={actionKey === `${item.quest_id}:stop`} onClick={() => void runAction(item.quest_id, 'stop')}>
                      {copy.stop}
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
    </div>
  )
}
