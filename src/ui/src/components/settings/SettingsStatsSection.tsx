import * as React from 'react'
import { Activity, AlertTriangle, BarChart3, ChevronDown, ChevronUp, GitBranch, MessagesSquare, Wrench } from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Link } from 'react-router-dom'

import { ChartSkeleton } from '@/components/settings/ChartSkeleton'
import { SettingsAutoChartPanel } from '@/components/settings/SettingsAutoChartPanel'
import { SettingsGuideCard } from '@/components/settings/SettingsGuideCard'
import { adminEnumLabel, adminLocaleFromLanguage, pickAdminCopy } from '@/components/settings/settingsOpsCopy'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { getAdminChartCatalog, getAdminStatsSummary, queryAdminCharts } from '@/lib/api/admin'
import { useI18n } from '@/lib/i18n/useI18n'
import type { AdminChartCatalogItem, AdminChartPayload, AdminQuestFocusItem, AdminStatsSummaryPayload } from '@/lib/types/admin'
import { cn } from '@/lib/utils'

const surfaceClassName =
  'rounded-[28px] border border-black/[0.06] bg-[rgba(255,251,246,0.76)] shadow-[0_18px_40px_-30px_rgba(18,24,32,0.24)] backdrop-blur-sm dark:border-white/[0.08] dark:bg-white/[0.03]'

const palette = ['#C47A5A', '#6E9774', '#6E88B7', '#B88A4A', '#7B86C8', '#5F9EA0', '#BE6A6A', '#7D8A91']
const RANGE_OPTIONS = ['1h', '24h', '7d', '30d'] as const

const PAGE_COPY = {
  en: {
    title: 'System Statistics',
    guide: `
### What this page shows

- **System Statistics** helps you understand overall system health, workload distribution, and recent activity.
- Use this page to spot bottlenecks, identify which quests need attention, and track trends over time.

### How to read it

1. Check the key metrics at the top for a quick health overview.
2. Expand distribution charts to see how work is spread across different categories.
3. Expand trend charts to understand how the system has changed over time.
4. Use the watchlists to jump directly into quests that need your attention.
`,
    totals: 'Key Metrics',
    questDist: 'Quest Distribution',
    operationsDist: 'Operations Distribution',
    backlog: 'Backlog Pressure',
    activity7d: '7 Day Activity',
    distributionsSection: 'Distribution Details',
    distributionsSectionHint: 'See how quests, runners, and workspaces are distributed across the system.',
    showDistributions: 'Show distribution charts',
    hideDistributions: 'Hide distribution charts',
    trendsSection: 'Time Trends',
    trendsSectionHint: 'Track system load, error rates, and resource usage over time.',
    showTrends: 'Show trend charts',
    hideTrends: 'Hide trend charts',
    trendsNote: 'Use these charts to explain patterns you noticed in the summary above.',
    questAnalytics: 'Quest Analytics',
    openSettings: 'Open settings analytics',
    openTools: 'Top tools',
    openActivity: 'Weekly activity',
    chartRange: 'Time Range',
    range1h: 'Last hour',
    range24h: 'Last 24 hours',
    range7d: 'Last 7 days',
    range30d: 'Last 30 days',
    activeWatchlist: 'Active Watchlist',
    decisionQueue: 'Decision Queue',
    messageQueue: 'Waiting Messages',
    recentlyUpdated: 'Recently Updated',
    noData: 'No statistics available yet.',
    quests: 'Total Quests',
    activeQuests: 'Active quests',
    decisions: 'Pending decisions',
    waitingMessages: 'Waiting messages',
    runningBash: 'Running bash',
    failures: 'Failures (7d)',
    repairs: 'Repairs',
    degradedConnectors: 'Degraded connectors',
    runningTasks: 'Running tasks',
    failedTasks: 'Failed tasks',
    statusCounts: 'Quest Status',
    anchorCounts: 'Quest Stage',
    workspaceModes: 'Workspace Mode',
    runnerCounts: 'Runner Type',
    connectorStates: 'Connector Status',
    taskStatuses: 'Task Status',
    taskKinds: 'Task Type',
    failureTypes: 'Failure Type',
    decisionsBucket: 'Decisions',
    messagesBucket: 'Messages',
    created: 'Created',
    updated: 'Updated',
    openAll: 'View all quests',
    openQuest: 'Open quest',
    ageHours: 'Age',
    updatedAt: 'Updated',
    status: 'Status',
    anchor: 'Stage',
    runner: 'Runner',
    emptyList: 'No items in this view.',
    one: '1',
    twoToThree: '2-3',
    fourPlus: '4+',
    none: '0',
    hours: 'h',
  },
  zh: {
    title: '系统统计',
    guide: `
### 这个页面显示什么

- **系统统计** 帮助你了解整体系统健康度、工作负载分布和最近活动情况。
- 使用这个页面来发现瓶颈、识别需要关注的 quest，以及追踪随时间的变化趋势。

### 如何阅读

1. 查看顶部的关键指标，快速了解系统健康状况。
2. 展开分布图表，查看工作在不同类别中的分布情况。
3. 展开趋势图表，了解系统随时间的变化。
4. 使用关注列表直接跳转到需要处理的 quest。
`,
    totals: '关键指标',
    questDist: 'Quest 分布',
    operationsDist: '运维分布',
    backlog: '积压情况',
    activity7d: '最近 7 天活动',
    distributionsSection: '分布详情',
    distributionsSectionHint: '查看 quest、runner、工作区在系统中的分布情况。',
    showDistributions: '展开分布图表',
    hideDistributions: '收起分布图表',
    trendsSection: '时间趋势',
    trendsSectionHint: '追踪系统负载、错误率、资源使用随时间的变化。',
    showTrends: '展开趋势图表',
    hideTrends: '收起趋势图表',
    trendsNote: '当你想解释上面摘要中看到的模式时，再展开这些图表。',
    questAnalytics: 'Quest 分析',
    openSettings: '打开设置分析',
    openTools: 'Top tools',
    openActivity: '周活动',
    chartRange: '时间范围',
    range1h: '最近 1 小时',
    range24h: '最近 24 小时',
    range7d: '最近 7 天',
    range30d: '最近 30 天',
    activeWatchlist: '活跃关注列表',
    decisionQueue: '待决策队列',
    messageQueue: '待消息队列',
    recentlyUpdated: '最近更新',
    noData: '暂时还没有统计数据。',
    quests: 'Quest 总数',
    activeQuests: '活动中的 quests',
    decisions: '待决策',
    waitingMessages: '待处理消息',
    runningBash: '运行中的 bash',
    failures: '失败次数（7天）',
    repairs: '修复总数',
    degradedConnectors: '降级连接器',
    runningTasks: '运行中任务',
    failedTasks: '失败任务',
    statusCounts: 'Quest 状态',
    anchorCounts: 'Quest 阶段',
    workspaceModes: '工作区模式',
    runnerCounts: 'Runner 类型',
    connectorStates: '连接器状态',
    taskStatuses: '任务状态',
    taskKinds: '任务类型',
    failureTypes: '失败类型',
    decisionsBucket: '决策',
    messagesBucket: '消息',
    created: '新建',
    updated: '更新',
    openAll: '查看全部 quest',
    openQuest: '打开 quest',
    ageHours: '停留',
    updatedAt: '更新于',
    status: '状态',
    anchor: '阶段',
    runner: 'Runner',
    emptyList: '当前视图没有条目。',
    one: '1',
    twoToThree: '2-3',
    fourPlus: '4+',
    none: '0',
    hours: '小时',
  },
} as const

function asNumber(value: unknown) {
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) ? numeric : 0
}

function formatTimestamp(value: unknown) {
  const text = String(value || '').trim()
  if (!text) return '—'
  const parsed = new Date(text)
  if (Number.isNaN(parsed.getTime())) return text
  return parsed.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function chartDataFromRecord(record?: Record<string, number> | null) {
  return Object.entries(record || {})
    .map(([name, value], index) => ({
      name,
      value,
      fill: palette[index % palette.length],
    }))
    .filter((item) => item.value > 0)
}

function KpiCard({
  title,
  value,
  icon,
  tone = 'default',
}: {
  title: string
  value: string
  icon: React.ReactNode
  tone?: 'default' | 'warning' | 'destructive' | 'success'
}) {
  return (
    <div
      className={cn(
        'rounded-[24px] border p-5',
        tone === 'destructive'
          ? 'border-rose-200 bg-[rgba(255,245,245,0.92)] dark:border-rose-500/30 dark:bg-rose-500/10'
          : tone === 'warning'
            ? 'border-amber-200 bg-[rgba(255,250,240,0.92)] dark:border-amber-500/30 dark:bg-amber-500/10'
            : tone === 'success'
              ? 'border-emerald-200 bg-[rgba(244,255,249,0.92)] dark:border-emerald-500/30 dark:bg-emerald-500/10'
              : 'border-black/[0.08] bg-white/[0.72] dark:border-white/[0.08] dark:bg-white/[0.03]'
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{title}</div>
        <div className="text-muted-foreground">{icon}</div>
      </div>
      <div className="mt-3 text-3xl font-semibold tracking-tight text-foreground">{value}</div>
    </div>
  )
}

function DistributionPanel({
  title,
  items,
}: {
  title: string
  items?: Record<string, number> | null
}) {
  const data = React.useMemo(() => chartDataFromRecord(items), [items])

  return (
    <section className={`${surfaceClassName} px-5 py-5`}>
      <div className="text-sm font-medium">{title}</div>
      {data.length > 0 ? (
        <>
          <div className="mt-4 h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
                <CartesianGrid stroke="rgba(125,125,125,0.16)" strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" allowDecimals={false} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="name" width={92} axisLine={false} tickLine={false} />
                <Tooltip />
                <Bar dataKey="value" radius={[0, 10, 10, 0]}>
                  {data.map((entry) => (
                    <Cell key={entry.name} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {data.map((item) => (
              <Badge key={item.name} variant="secondary">
                {item.name}: {item.value}
              </Badge>
            ))}
          </div>
        </>
      ) : (
        <div className="mt-4 text-sm text-soft-text-secondary">—</div>
      )}
    </section>
  )
}

function ActivityTimelinePanel({
  title,
  items,
  copy,
}: {
  title: string
  items?: Array<Record<string, string | number>> | null
  copy: Record<string, string>
}) {
  const data = Array.isArray(items) ? items : []
  return (
    <section className={`${surfaceClassName} px-5 py-5`}>
      <div className="text-sm font-medium">{title}</div>
      {data.length > 0 ? (
        <div className="mt-4 h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="rgba(125,125,125,0.16)" strokeDasharray="3 3" />
              <XAxis dataKey="label" axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} axisLine={false} tickLine={false} />
              <Tooltip />
              <Legend />
              <Bar dataKey="quests_created" name={copy.created} fill="#C47A5A" radius={[8, 8, 0, 0]} />
              <Line type="monotone" dataKey="quests_updated" name={copy.updated} stroke="#6E88B7" strokeWidth={2.2} dot={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="mt-4 text-sm text-soft-text-secondary">—</div>
      )}
    </section>
  )
}

function QuestFocusList({
  title,
  items,
  locale,
  copy,
}: {
  title: string
  items?: AdminQuestFocusItem[] | null
  locale: 'en' | 'zh'
  copy: Record<string, string>
}) {
  const list = Array.isArray(items) ? items : []
  return (
    <section className={`${surfaceClassName} px-5 py-5`}>
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-medium">{title}</div>
        <Button variant="ghost" size="sm" asChild>
          <Link to="/settings/quests">{copy.openAll}</Link>
        </Button>
      </div>
      <div className="mt-4 space-y-3">
        {list.length > 0 ? (
          list.map((item) => (
            <Link
              key={`${title}-${item.quest_id}`}
              to={`/settings/quests/${encodeURIComponent(item.quest_id)}`}
              className="block rounded-[20px] border border-black/[0.08] bg-white/[0.7] p-4 transition hover:shadow-[0_12px_28px_-18px_rgba(18,24,32,0.22)] dark:border-white/[0.08] dark:bg-white/[0.03]"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-foreground">{item.title || item.quest_id}</div>
                  <div className="mt-1 text-xs text-soft-text-secondary">{item.quest_id}</div>
                </div>
                <Badge variant="secondary">{adminEnumLabel(item.runtime_status, locale)}</Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-soft-text-secondary">
                {item.active_anchor ? <Badge variant="outline">{copy.anchor}: {item.active_anchor}</Badge> : null}
                {item.runner ? <Badge variant="outline">{copy.runner}: {item.runner}</Badge> : null}
                {typeof item.pending_decisions === 'number' ? <Badge variant="outline">{copy.decisions}: {item.pending_decisions}</Badge> : null}
                {typeof item.pending_user_messages === 'number' ? <Badge variant="outline">{copy.waitingMessages}: {item.pending_user_messages}</Badge> : null}
                {typeof item.running_bash === 'number' ? <Badge variant="outline">{copy.runningBash}: {item.running_bash}</Badge> : null}
                {typeof item.age_hours === 'number' ? <Badge variant="outline">{copy.ageHours}: {item.age_hours}{copy.hours}</Badge> : null}
              </div>
              {item.status_line ? <div className="mt-3 text-sm leading-6 text-muted-foreground">{item.status_line}</div> : null}
              <div className="mt-3 text-xs text-soft-text-secondary">
                {copy.updatedAt}: {formatTimestamp(item.updated_at)}
              </div>
            </Link>
          ))
        ) : (
          <div className="text-sm text-soft-text-secondary">{copy.emptyList}</div>
        )}
      </div>
    </section>
  )
}

export function SettingsStatsSection() {
  const { language } = useI18n('admin')
  const locale = adminLocaleFromLanguage(language)
  const copy = pickAdminCopy(language, PAGE_COPY)
  const [payload, setPayload] = React.useState<AdminStatsSummaryPayload | null>(null)
  const [chartCatalog, setChartCatalog] = React.useState<AdminChartCatalogItem[]>([])
  const [charts, setCharts] = React.useState<AdminChartPayload[]>([])
  const [chartsLoading, setChartsLoading] = React.useState(false)
  const [selectedRange, setSelectedRange] = React.useState<(typeof RANGE_OPTIONS)[number]>('24h')
  const [distributionsOpen, setDistributionsOpen] = React.useState(false)
  const [detailedChartsOpen, setDetailedChartsOpen] = React.useState(false)

  React.useEffect(() => {
    void getAdminStatsSummary().then((next) => setPayload(next))
  }, [])

  React.useEffect(() => {
    let cancelled = false

    if (!detailedChartsOpen) {
      setCharts([])
      setChartCatalog([])
      setChartsLoading(false)
      return () => {
        cancelled = true
      }
    }

    async function loadCharts() {
      setChartsLoading(true)
      try {
        const catalog = await getAdminChartCatalog()
        if (cancelled) return
        const statsCharts = (catalog.items || [])
          .filter((item) => Array.isArray(item.surfaces) && item.surfaces.includes('stats'))
          .sort((left, right) => Number(left.priority || 0) - Number(right.priority || 0))
          .slice(0, 14)
        setChartCatalog(statsCharts)
        if (!statsCharts.length) {
          setCharts([])
          return
        }
        const response = await queryAdminCharts(
          statsCharts.map((item) => ({
            chart_id: item.chart_id,
            range: item.kind === 'line' ? selectedRange : item.default_range,
            step_seconds: item.kind === 'line' ? undefined : item.default_step_seconds,
            limit: item.chart_id === 'tools.by_tool' || item.chart_id === 'tools.top_quests_by_calls' ? 8 : undefined,
          }))
        )
        if (cancelled) return
        setCharts(response.items || [])
      } catch {
        if (cancelled) return
        setCharts([])
      } finally {
        if (!cancelled) setChartsLoading(false)
      }
    }

    void loadCharts()
    const timer = window.setInterval(() => {
      void loadCharts()
    }, 60000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [detailedChartsOpen, selectedRange])

  const totals = payload?.totals || {}
  const recentActivity = payload?.recent_activity || {}
  const decisionBuckets = payload?.decision_backlog_buckets || {}
  const messageBuckets = payload?.message_backlog_buckets || {}
  const topQuestChart = charts.find((item) => item.chart_id === 'tools.top_quests_by_calls' && item.kind === 'bar')

  const backlogChart = React.useMemo(
    () => [
      { name: copy.none, decisions: asNumber(decisionBuckets.none), messages: asNumber(messageBuckets.none) },
      { name: copy.one, decisions: asNumber(decisionBuckets.one), messages: asNumber(messageBuckets.one) },
      { name: copy.twoToThree, decisions: asNumber(decisionBuckets.two_to_three), messages: asNumber(messageBuckets.two_to_three) },
      { name: copy.fourPlus, decisions: asNumber(decisionBuckets.four_plus), messages: asNumber(messageBuckets.four_plus) },
    ],
    [copy.fourPlus, copy.none, copy.one, copy.twoToThree, decisionBuckets, messageBuckets]
  )

  return (
    <div className="space-y-5">
      <SettingsGuideCard markdown={copy.guide} title={copy.title} />

      {/* Key Metrics - Always visible */}
      <section className="grid gap-4 xl:grid-cols-4">
        <KpiCard title={copy.quests} value={String(asNumber(totals.quests))} icon={<BarChart3 className="h-4 w-4" />} />
        <KpiCard
          title={copy.activeQuests}
          value={String(asNumber(totals.active_quests))}
          icon={<Activity className="h-4 w-4" />}
          tone={asNumber(totals.active_quests) > 0 ? 'warning' : 'default'}
        />
        <KpiCard
          title={copy.decisions}
          value={String(asNumber(totals.pending_decisions_total))}
          icon={<GitBranch className="h-4 w-4" />}
          tone={asNumber(totals.pending_decisions_total) > 0 ? 'warning' : 'default'}
        />
        <KpiCard
          title={copy.waitingMessages}
          value={String(asNumber(totals.queued_user_messages_total))}
          icon={<MessagesSquare className="h-4 w-4" />}
          tone={asNumber(totals.queued_user_messages_total) > 0 ? 'warning' : 'default'}
        />
        <KpiCard
          title={copy.runningBash}
          value={String(asNumber(totals.running_bash_total))}
          icon={<Activity className="h-4 w-4" />}
          tone={asNumber(totals.running_bash_total) > 0 ? 'warning' : 'default'}
        />
        <KpiCard
          title={copy.failures}
          value={String(asNumber(totals.failures_last_7d))}
          icon={<AlertTriangle className="h-4 w-4" />}
          tone={asNumber(totals.failures_last_7d) > 0 ? 'destructive' : 'success'}
        />
        <KpiCard
          title={copy.degradedConnectors}
          value={String(asNumber(totals.degraded_connectors))}
          icon={<AlertTriangle className="h-4 w-4" />}
          tone={asNumber(totals.degraded_connectors) > 0 ? 'warning' : 'success'}
        />
        <KpiCard
          title={copy.runningTasks}
          value={`${asNumber(totals.running_tasks)} / ${asNumber(totals.failed_tasks)}`}
          icon={<Wrench className="h-4 w-4" />}
          tone={asNumber(totals.failed_tasks) > 0 ? 'warning' : 'default'}
        />
      </section>

      {/* Distribution Charts - Collapsible */}
      <Collapsible open={distributionsOpen} onOpenChange={setDistributionsOpen}>
        <div className={`${surfaceClassName} px-5 py-5`}>
          <CollapsibleTrigger asChild>
            <button className="flex w-full items-center justify-between text-left">
              <div>
                <div className="text-sm font-medium">{copy.distributionsSection}</div>
                <div className="mt-1 text-xs text-muted-foreground">{copy.distributionsSectionHint}</div>
              </div>
              {distributionsOpen ? <ChevronUp className="h-5 w-5 text-muted-foreground" /> : <ChevronDown className="h-5 w-5 text-muted-foreground" />}
            </button>
          </CollapsibleTrigger>

          <CollapsibleContent>
            {distributionsOpen && (
              <div className="mt-4 space-y-4">
                <div className="grid gap-4 xl:grid-cols-2">
                  <DistributionPanel title={copy.statusCounts} items={payload?.status_counts} />
                  <DistributionPanel title={copy.anchorCounts} items={payload?.anchor_counts} />
                  <DistributionPanel title={copy.workspaceModes} items={payload?.workspace_mode_counts} />
                  <DistributionPanel title={copy.runnerCounts} items={payload?.runner_counts} />
                </div>

                <div className="grid gap-4 xl:grid-cols-2">
                  <DistributionPanel title={copy.connectorStates} items={payload?.connector_state_counts} />
                  <DistributionPanel title={copy.taskStatuses} items={payload?.task_status_counts} />
                  <DistributionPanel title={copy.taskKinds} items={payload?.task_kind_counts} />
                  <DistributionPanel title={copy.failureTypes} items={payload?.failure_type_counts} />
                </div>
              </div>
            )}
          </CollapsibleContent>
        </div>
      </Collapsible>

      {/* Backlog and Activity - Always visible */}
      <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
        <section className={`${surfaceClassName} px-5 py-5`}>
          <div className="text-sm font-medium">{copy.backlog}</div>
          <div className="mt-4 h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={backlogChart} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="rgba(125,125,125,0.16)" strokeDasharray="3 3" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} axisLine={false} tickLine={false} />
                <Tooltip />
                <Legend />
                <Bar dataKey="decisions" name={copy.decisionsBucket} fill="#C47A5A" radius={[8, 8, 0, 0]} />
                <Bar dataKey="messages" name={copy.messagesBucket} fill="#6E88B7" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <div className="rounded-2xl border border-black/[0.08] bg-white/[0.66] px-4 py-3 text-sm dark:border-white/[0.08] dark:bg-white/[0.03]">
              <div className="text-soft-text-secondary">{copy.activeQuests}</div>
              <div className="mt-1 text-2xl font-semibold">{asNumber(recentActivity.updated_last_24h)}</div>
            </div>
            <div className="rounded-2xl border border-black/[0.08] bg-white/[0.66] px-4 py-3 text-sm dark:border-white/[0.08] dark:bg-white/[0.03]">
              <div className="text-soft-text-secondary">{copy.repairs}</div>
              <div className="mt-1 text-2xl font-semibold">{asNumber(totals.repairs_total)}</div>
            </div>
          </div>
        </section>

        <ActivityTimelinePanel title={copy.activity7d} items={payload?.activity_timeline_7d} copy={copy} />
      </div>

      {/* Trend Charts - Collapsible */}
      <Collapsible open={detailedChartsOpen} onOpenChange={setDetailedChartsOpen}>
        <div className={`${surfaceClassName} px-5 py-5`}>
          <CollapsibleTrigger asChild>
            <button className="flex w-full items-center justify-between text-left">
              <div>
                <div className="text-sm font-medium">{copy.trendsSection}</div>
                <div className="mt-1 text-xs text-muted-foreground">{copy.trendsSectionHint}</div>
              </div>
              {detailedChartsOpen ? <ChevronUp className="h-5 w-5 text-muted-foreground" /> : <ChevronDown className="h-5 w-5 text-muted-foreground" />}
            </button>
          </CollapsibleTrigger>

          {!detailedChartsOpen && (
            <div className="mt-3 text-xs text-soft-text-secondary">{copy.trendsNote}</div>
          )}

          <CollapsibleContent>
            {detailedChartsOpen && (
              <div className="mt-4 space-y-4">
                <div className="flex justify-end">
                  <div className="inline-flex items-center gap-1 rounded-full border border-black/[0.08] bg-white/[0.72] p-1 dark:border-white/[0.08] dark:bg-white/[0.04]">
                    {RANGE_OPTIONS.map((option) => (
                      <button
                        key={option}
                        type="button"
                        onClick={() => setSelectedRange(option)}
                        data-testid={`stats-chart-range-${option}`}
                        className={cn(
                          'rounded-full px-3 py-1.5 text-xs font-medium transition',
                          selectedRange === option
                            ? 'bg-[#2D2A26] text-white shadow-[0_10px_22px_-18px_rgba(18,24,32,0.42)]'
                            : 'text-muted-foreground hover:bg-black/[0.04] dark:hover:bg-white/[0.06]'
                        )}
                      >
                        {copy[`range${option}` as keyof typeof copy] || option}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="grid gap-4 xl:grid-cols-2">
                  {chartsLoading ? (
                    <>
                      <ChartSkeleton />
                      <ChartSkeleton />
                      <ChartSkeleton />
                      <ChartSkeleton />
                    </>
                  ) : charts.length > 0 ? (
                    charts.map((chart) => <SettingsAutoChartPanel key={chart.chart_id} payload={chart} />)
                  ) : (
                    <div className="col-span-2 text-center text-sm text-muted-foreground py-8">{copy.noData}</div>
                  )}
                </div>
              </div>
            )}
          </CollapsibleContent>
        </div>
      </Collapsible>

      {/* Quest Analytics - Only show when trends are open and data available */}
      {detailedChartsOpen && topQuestChart && topQuestChart.kind === 'bar' && topQuestChart.categories.length > 0 ? (
        <section className={`${surfaceClassName} px-5 py-5`}>
          <div className="text-sm font-medium">{copy.questAnalytics}</div>
          <div className="mt-4 grid gap-3 xl:grid-cols-2">
            {topQuestChart.categories.map((item) => (
              <div
                key={`quest-analytics-${item.key}`}
                className="rounded-[22px] border border-black/[0.08] bg-white/[0.68] p-4 dark:border-white/[0.08] dark:bg-white/[0.03]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-foreground">{item.label}</div>
                    <div className="mt-1 text-xs text-soft-text-secondary">{item.value} calls</div>
                  </div>
                  <Badge variant="secondary">quest</Badge>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" asChild>
                    <Link to={`/settings/quests/${encodeURIComponent(item.key)}?view=activity&focus=activity-hourly`}>
                      {copy.openActivity}
                    </Link>
                  </Button>
                  <Button size="sm" variant="outline" asChild>
                    <Link to={`/settings/quests/${encodeURIComponent(item.key)}?view=activity&focus=tools-top`}>
                      {copy.openTools}
                    </Link>
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-2">
        <QuestFocusList title={copy.activeWatchlist} items={payload?.active_watchlist} locale={locale} copy={copy} />
        <QuestFocusList title={copy.decisionQueue} items={payload?.top_pending_decisions} locale={locale} copy={copy} />
        <QuestFocusList title={copy.messageQueue} items={payload?.top_waiting_messages} locale={locale} copy={copy} />
        <QuestFocusList title={copy.recentlyUpdated} items={payload?.recently_updated} locale={locale} copy={copy} />
      </div>

      {!payload?.ok ? <div className="text-sm text-soft-text-secondary">{copy.noData}</div> : null}
    </div>
  )
}
