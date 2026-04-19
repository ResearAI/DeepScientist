import * as React from 'react'
import { Link } from 'react-router-dom'
import { Activity, ArrowUpRight, HeartPulse, RefreshCw, ShieldAlert, Wrench } from 'lucide-react'

import { SettingsGuideCard } from '@/components/settings/SettingsGuideCard'
import { SettingsSystemTrendChart } from '@/components/settings/SettingsSystemTrendChart'
import { adminEnumLabel, adminLocaleFromLanguage, pickAdminCopy } from '@/components/settings/settingsOpsCopy'
import { SettingsTaskProgress } from '@/components/settings/SettingsTaskProgress'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  getAdminOverview,
  getAdminDoctor,
  getAdminSystemHardware,
  listAdminTasks,
  startAdminDoctorTask,
  startAdminSystemUpdateCheckTask,
} from '@/lib/api/admin'
import { useAdminTaskStream } from '@/lib/hooks/useAdminTaskStream'
import { useI18n } from '@/lib/i18n/useI18n'
import { cn } from '@/lib/utils'
import type { AdminOverviewPayload, AdminSystemHardwarePayload, AdminTask } from '@/lib/types/admin'

function asNumber(value: unknown) {
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function formatPercent(value: unknown) {
  const numeric = asNumber(value)
  return numeric === null ? '—' : `${numeric.toFixed(numeric >= 100 ? 0 : 1)}%`
}

function formatGb(value: unknown) {
  const numeric = asNumber(value)
  return numeric === null ? '—' : `${numeric.toFixed(numeric >= 100 ? 0 : 1)} GB`
}

function selectedGpuLabel(payload: AdminSystemHardwarePayload | null) {
  const effective = payload?.preferences?.effective_gpu_ids || []
  if (!effective.length) return 'all'
  return effective.join(',')
}

function statusTone(status?: string | null): 'secondary' | 'warning' | 'success' | 'destructive' {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'completed') return 'success'
  if (normalized === 'failed' || normalized === 'error') return 'destructive'
  if (normalized === 'running' || normalized === 'active') return 'warning'
  return 'secondary'
}

function displayCount(value: unknown, ready: boolean) {
  if (!ready) return '—'
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) ? String(numeric) : '—'
}

const surfaceClassName =
  'rounded-[28px] border border-black/[0.06] bg-[rgba(255,251,246,0.76)] shadow-[0_18px_40px_-30px_rgba(18,24,32,0.24)] backdrop-blur-sm dark:border-white/[0.08] dark:bg-white/[0.03]'
const dividerClassName = 'border-black/[0.06] dark:border-white/[0.08]'

const PAGE_COPY = {
  en: {
    title: 'System Overview',
    guide: `
### What this page shows

- **System Overview** provides a quick snapshot of your runtime health and current activity.
- Use this page to answer: what is running right now, what needs attention, and what hardware resources are available.

### How to use it

1. Check the top cards to see active quests and current workload.
2. Review the hardware section to understand CPU, memory, disk, and GPU usage.
3. Use the action buttons to run diagnostics, check for updates, or view detailed logs.
4. Monitor the system trajectory chart to spot resource usage trends.
`,
    quests: 'Quests',
    activeQuests: 'Active quests',
    pendingDecisions: 'Pending decisions',
    runningBash: 'Running bash sessions',
    runtimeIdentity: 'Runtime Information',
    daemonVersion: 'Version',
    daemonPid: 'Process ID',
    daemonHome: 'Home Directory',
    daemonAuth: 'Authentication',
    hardware: 'Hardware Resources',
    host: 'Host',
    cpuUsage: 'CPU usage',
    memoryUsage: 'Memory usage',
    rootDiskUsage: 'Root disk',
    selectedGpus: 'Active GPUs',
    gpuUtil: 'GPU utilization',
    systemTrajectory: 'Resource Usage Trends',
    lastHour: 'Last 60 minutes',
    noGpu: 'No GPU detected',
    operations: 'Quick Actions',
    refresh: 'Refresh',
    runDoctor: 'Run Diagnostics',
    checkUpdate: 'Check Update',
    diagnostics: 'Diagnostics',
    repairs: 'Repairs',
    doctorTask: 'Doctor Task',
    systemUpdateTask: 'System Update Task',
    attention: 'Attention',
    latestFailure: 'Latest failure',
    openRepairs: 'Open repairs',
    degradedConnectors: 'Degraded connectors',
    waitingMessages: 'Waiting messages',
    tasksRunning: 'Running tasks',
    tasksFailed: 'Failed tasks',
    recentMovement: 'Recent movement',
    updated24h: 'Updated in 24h',
    created7d: 'Created in 7d',
    stale7d: 'Stale over 7d',
    connectorStates: 'Connector states',
    taskHealth: 'Task health',
    questBacklog: 'Quest backlog',
    decisionBacklog: 'Decision backlog',
    messageBacklog: 'Message backlog',
    attentionQueue: 'Attention queue',
    operationsPulse: 'Operations Pulse',
    operationsPulseBody: 'Time-range aware charts generated from the shared admin chart pipeline.',
    recentQuests: 'Recent Quests',
    openAll: 'Open all',
    quest: 'Quest',
    status: 'Status',
    anchor: 'Anchor',
    runner: 'Runner',
    signals: 'Signals',
    decisions: 'decisions',
    bash: 'bash',
    dive: 'Open detail',
    totalQuestBody: 'Open the quest table to inspect or filter every quest.',
    activeQuestBody: 'Jump into the quest table and focus on currently active work.',
    pendingDecisionBody: 'Open quest details to resolve waiting decisions and user gates.',
    runningBashBody: 'Inspect runtime sessions and running bash evidence.',
    waitingMessagesBody: 'Review quests waiting for user replies or queued deliveries.',
    hardwareBoundary: 'Hardware boundary',
    hardwareBoundaryBody: 'Open runtime hardware controls and review the saved GPU / prompt policy.',
    diagnosticsBody: 'Run doctor, inspect runtime tools, and review recent failures.',
    connectorHealthBody: 'Inspect degraded connectors, bindings, and discovered targets.',
    repairsBody: 'Review or reopen operator repair sessions.',
    tasksRunningBody: 'Inspect currently executing admin tasks and recent operations.',
    tasksFailedBody: 'Open diagnostics and failed task records for repair.',
    recentMovementBody: 'Check whether the fleet is still moving or has gone stale.',
    connectorStatesBody: 'Use connector state counts to spot degraded or disabled edges.',
    taskHealthBody: 'Track queued, running, and failed admin jobs from one place.',
    questBacklogBody: 'Check whether decision or message pressure is concentrating in a few quests.',
  },
  zh: {
    title: '系统概览',
    guide: `
### 这个页面显示什么

- **系统概览** 提供运行时健康状况和当前活动的快速快照。
- 使用这个页面来回答：现在正在运行什么、什么需要关注、有哪些硬件资源可用。

### 如何使用

1. 查看顶部卡片，了解活跃 quest 和当前工作负载。
2. 查看硬件部分，了解 CPU、内存、磁盘和 GPU 使用情况。
3. 使用快速操作按钮来运行诊断、检查更新或查看详细日志。
4. 监控资源使用趋势图表，发现资源使用模式。
`,
    quests: 'Quests',
    activeQuests: '活动中的 quests',
    pendingDecisions: '待决策',
    runningBash: '运行中的 bash 会话',
    runtimeIdentity: '运行时信息',
    daemonVersion: '版本',
    daemonPid: '进程 ID',
    daemonHome: '主目录',
    daemonAuth: '认证',
    hardware: '硬件资源',
    host: '主机',
    cpuUsage: 'CPU 使用率',
    memoryUsage: '内存使用率',
    rootDiskUsage: '根分区',
    selectedGpus: '活跃 GPU',
    gpuUtil: 'GPU 利用率',
    systemTrajectory: '资源使用趋势',
    lastHour: '最近 60 分钟',
    noGpu: '未检测到 GPU',
    operations: '快速操作',
    refresh: '刷新',
    runDoctor: '运行诊断',
    checkUpdate: '检查更新',
    diagnostics: '诊断',
    repairs: '修复',
    doctorTask: 'Doctor 任务',
    systemUpdateTask: '系统更新任务',
    attention: '关注项',
    latestFailure: '最新失败',
    openRepairs: '打开中的修复',
    degradedConnectors: '退化连接器',
    waitingMessages: '待处理消息',
    tasksRunning: '运行中任务',
    tasksFailed: '失败任务',
    recentMovement: '最近变化',
    updated24h: '24 小时内更新',
    created7d: '7 天内新建',
    stale7d: '超过 7 天未更新',
    connectorStates: '连接器状态',
    taskHealth: '任务健康',
    questBacklog: 'Quest 积压',
    decisionBacklog: '决策积压',
    messageBacklog: '消息积压',
    attentionQueue: '关注队列',
    operationsPulse: '运行脉搏',
    operationsPulseBody: '基于统一 admin chart 管线生成的时间范围图表。',
    recentQuests: '最近 Quests',
    openAll: '查看全部',
    quest: 'Quest',
    status: '状态',
    anchor: '阶段',
    runner: 'Runner',
    signals: '信号',
    decisions: '决策',
    bash: 'bash',
    dive: '进入详情',
    totalQuestBody: '打开 quest 表，统一检查或筛选全部 quest。',
    activeQuestBody: '进入 quest 表，重点查看当前正在运行的工作。',
    pendingDecisionBody: '进入具体 quest 详情，处理等待中的决策和用户门槛。',
    runningBashBody: '查看运行时会话和正在执行的 bash 证据。',
    waitingMessagesBody: '查看等待用户回复或等待投递处理的 quests。',
    hardwareBoundary: '硬件边界',
    hardwareBoundaryBody: '打开运行时硬件控制，检查保存后的 GPU / prompt 策略。',
    diagnosticsBody: '运行 doctor、检查运行时工具，并查看最近失败。',
    connectorHealthBody: '查看退化连接器、绑定关系与已发现目标。',
    repairsBody: '查看或重新进入运维修复会话。',
    tasksRunningBody: '检查当前执行中的 admin 任务和最近操作。',
    tasksFailedBody: '打开诊断页，查看失败任务与修复路径。',
    recentMovementBody: '检查整个队列最近是否仍在推进，还是已经变陈旧。',
    connectorStatesBody: '通过连接器状态计数，快速识别退化或禁用边。',
    taskHealthBody: '统一跟踪排队、运行和失败的 admin 作业。',
    questBacklogBody: '查看决策或消息压力是否集中在少数 quest 上。',
  },
} as const

type SummaryCardProps = {
  to: string
  title: string
  value: string
  body: string
  badge?: string
  tone?: 'default' | 'warning' | 'destructive' | 'success'
}

function SummaryCard({ to, title, value, body, badge, tone = 'default' }: SummaryCardProps) {
  return (
    <Link
      to={to}
      className={cn(
        'group rounded-[24px] border p-5 transition hover:shadow-[0_18px_40px_-28px_rgba(18,24,32,0.18)]',
        tone === 'destructive'
          ? 'border-rose-200 bg-[rgba(255,245,245,0.92)] dark:border-rose-500/30 dark:bg-rose-500/10'
          : tone === 'warning'
            ? 'border-amber-200 bg-[rgba(255,250,240,0.92)] dark:border-amber-500/30 dark:bg-amber-500/10'
            : tone === 'success'
              ? 'border-emerald-200 bg-[rgba(244,255,249,0.92)] dark:border-emerald-500/30 dark:bg-emerald-500/10'
              : 'border-black/[0.08] bg-white/[0.72] dark:border-white/[0.08] dark:bg-white/[0.03]'
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{title}</div>
        <ArrowUpRight className="h-4 w-4 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
      </div>
      <div className="mt-3 text-3xl font-semibold tracking-tight text-foreground">{value}</div>
      <div className="mt-2 text-sm leading-6 text-muted-foreground">{body}</div>
      {badge ? <div className="mt-4"><Badge variant="secondary">{badge}</Badge></div> : null}
    </Link>
  )
}

export function SettingsSummarySection() {
  const { language } = useI18n('admin')
  const locale = adminLocaleFromLanguage(language)
  const copy = pickAdminCopy(language, PAGE_COPY)
  const [overview, setOverview] = React.useState<AdminOverviewPayload | null>(null)
  const [hardware, setHardware] = React.useState<AdminSystemHardwarePayload | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [doctorTaskId, setDoctorTaskId] = React.useState<string | null>(null)
  const [updateTaskId, setUpdateTaskId] = React.useState<string | null>(null)
  const doctorStream = useAdminTaskStream(doctorTaskId)
  const updateStream = useAdminTaskStream(updateTaskId)

  const loadOverview = React.useCallback(async () => {
    setLoading(true)
    try {
      const [nextOverview, doctorPayload, taskPayload] = await Promise.all([
        getAdminOverview(),
        getAdminDoctor(),
        listAdminTasks(undefined, 20),
      ])
      setOverview(nextOverview)
      const runningDoctor = [doctorPayload.latest_task, ...(taskPayload.items || [])].find(
        (item): item is AdminTask => Boolean(item) && String(item.kind || '').trim() === 'doctor' && ['queued', 'running'].includes(String(item.status || '').trim())
      )
      const runningUpdate = (taskPayload.items || []).find(
        (item) =>
          ['system_update_check', 'system_update_action'].includes(String(item.kind || '').trim()) &&
          ['queued', 'running'].includes(String(item.status || '').trim())
      )
      setDoctorTaskId(runningDoctor?.task_id || null)
      setUpdateTaskId(runningUpdate?.task_id || null)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadHardware = React.useCallback(async () => {
    try {
      setHardware(await getAdminSystemHardware())
    } catch {
      return
    }
  }, [])

  React.useEffect(() => {
    void loadOverview()
    void loadHardware()
    const timer = window.setInterval(() => {
      void loadOverview()
      void loadHardware()
    }, 30000)
    return () => window.clearInterval(timer)
  }, [loadHardware, loadOverview])

  const totals = overview?.totals || {}
  const activeDoctorTask = doctorStream.task || (overview?.tasks || []).find((item) => String(item.kind || '') === 'doctor') || null
  const activeUpdateTask = updateStream.task || (overview?.tasks || []).find((item) => String(item.kind || '').startsWith('system_update')) || null
  const overviewReady = Boolean(overview?.ok)
  const latestFailureScanned = overview?.latest_failure_scanned !== false
  const effectiveHardware = hardware || overview?.system_hardware || null
  const latestSample = (effectiveHardware?.latest_sample || {}) as Record<string, unknown>
  const recentStats = (effectiveHardware?.recent_stats || {}) as Record<string, unknown>
  const latestCpu = ((latestSample.cpu as Record<string, unknown> | undefined) || {})
  const latestMemory = ((latestSample.memory as Record<string, unknown> | undefined) || {})
  const latestDisks = Array.isArray(latestSample.disks) ? (latestSample.disks as Array<Record<string, unknown>>) : []
  const rootDisk = latestDisks.find((item) => String(item.mount || '') === '/') || latestDisks[0] || null
  const gpuStats = Array.isArray(recentStats.gpus) ? (recentStats.gpus as Array<Record<string, unknown>>) : []
  const questInsights = (overview?.quest_insights || {}) as Record<string, unknown>
  const activeWatchlist = Array.isArray(questInsights.active_watchlist) ? (questInsights.active_watchlist as Array<Record<string, unknown>>) : []

  return (
    <div className="space-y-5">
      <SettingsGuideCard markdown={copy.guide} title={copy.title} />

      <section className="grid gap-4 xl:grid-cols-4">
        <SummaryCard
          to="/settings/quests"
          title={copy.quests}
          value={displayCount(totals.quests_total, overviewReady)}
          body={copy.totalQuestBody}
        />
        <SummaryCard
          to="/settings/quests"
          title={copy.activeQuests}
          value={displayCount(totals.quests_active, overviewReady)}
          body={copy.activeQuestBody}
          tone={Number(totals.quests_active || 0) > 0 ? 'warning' : 'default'}
        />
        <SummaryCard
          to="/settings/quests"
          title={copy.pendingDecisions}
          value={displayCount(totals.pending_decisions_total, overviewReady)}
          body={copy.pendingDecisionBody}
          tone={Number(totals.pending_decisions_total || 0) > 0 ? 'warning' : 'default'}
        />
        <SummaryCard
          to="/settings/runtime"
          title={copy.runningBash}
          value={displayCount(totals.running_bash_total, overviewReady)}
          body={copy.runningBashBody}
          tone={Number(totals.running_bash_total || 0) > 0 ? 'warning' : 'default'}
        />
        <SummaryCard
          to="/settings/quests"
          title={copy.waitingMessages}
          value={displayCount(totals.queued_user_messages_total, overviewReady)}
          body={copy.waitingMessagesBody}
          tone={Number(totals.queued_user_messages_total || 0) > 0 ? 'warning' : 'default'}
        />
        <SummaryCard
          to="/settings/diagnostics"
          title={copy.recentMovement}
          value={displayCount(totals.quests_updated_last_24h, overviewReady)}
          body={copy.recentMovementBody}
          tone={Number(totals.quests_updated_last_24h || 0) > 0 ? 'success' : 'default'}
        />
      </section>

      <section className={`${surfaceClassName} px-5 py-5`}>
        <div className="flex items-center justify-between gap-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{copy.hardware}</div>
          <Button variant="outline" size="sm" asChild>
            <Link to="/settings/runtime">
              {copy.dive}
              <ArrowUpRight className="ml-2 h-4 w-4" />
            </Link>
          </Button>
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <SummaryCard to="/settings/runtime" title={copy.host} value={String(effectiveHardware?.system?.host?.hostname || '—')} body={copy.hardwareBoundaryBody} />
          <SummaryCard to="/settings/runtime" title={copy.cpuUsage} value={formatPercent(latestCpu.usage_percent)} body={`${copy.lastHour}: ${formatPercent((recentStats.cpu as Record<string, unknown> | undefined)?.avg_usage_percent)}`} />
          <SummaryCard to="/settings/runtime" title={copy.memoryUsage} value={formatPercent(latestMemory.usage_percent)} body={`${formatGb(latestMemory.used_gb)} / ${formatGb((recentStats.memory as Record<string, unknown> | undefined)?.total_gb)}`} />
          <SummaryCard to="/settings/runtime" title={copy.rootDiskUsage} value={formatPercent(rootDisk?.usage_percent)} body={`${formatGb(rootDisk?.free_gb)} free`} />
          <SummaryCard to="/settings/runtime" title={copy.selectedGpus} value={selectedGpuLabel(effectiveHardware)} body={gpuStats.length > 0 ? copy.gpuUtil : copy.noGpu} />
        </div>
        <div className={`mt-4 border-t ${dividerClassName} pt-4`}>
          <div className="flex flex-wrap gap-2">
            {gpuStats.length > 0 ? (
              gpuStats.map((gpu, index) => (
                <Badge key={`${String(gpu.gpu_id || gpu.name || 'gpu')}-${index}`} variant="secondary">
                  {String(gpu.gpu_id || '?')} · {formatPercent(gpu.latest_utilization_gpu_percent)} · {formatGb(gpu.latest_memory_used_gb)} / {formatGb(gpu.memory_total_gb)}
                </Badge>
              ))
            ) : (
              <div className="text-sm text-soft-text-secondary">{copy.noGpu}</div>
            )}
          </div>
        </div>
        {effectiveHardware?.prompt_hardware_summary ? (
          <div className={`mt-4 border-t ${dividerClassName} pt-4 text-xs leading-6 text-soft-text-secondary`}>
            {effectiveHardware.prompt_hardware_summary}
          </div>
        ) : null}
        <div className={`mt-4 border-t ${dividerClassName} pt-4`}>
          <div className="mb-3 text-sm font-medium">{copy.systemTrajectory}</div>
          <SettingsSystemTrendChart recentStats={effectiveHardware?.recent_stats} locale={locale} />
        </div>
      </section>

      <section className={`${surfaceClassName} px-5 py-5`}>
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{copy.operations}</div>
              <div className="mt-1 text-sm text-muted-foreground">{copy.attention}</div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void loadOverview()
                void loadHardware()
              }}
              isLoading={loading}
            >
              <RefreshCw className="mr-2 h-4 w-4" />
              {copy.refresh}
            </Button>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={async () => {
                const response = await startAdminDoctorTask()
                setDoctorTaskId(response.task.task_id)
              }}
            >
              <HeartPulse className="mr-2 h-4 w-4" />
              {copy.runDoctor}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={async () => {
                const response = await startAdminSystemUpdateCheckTask()
                setUpdateTaskId(response.task.task_id)
              }}
            >
              <Activity className="mr-2 h-4 w-4" />
              {copy.checkUpdate}
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to="/settings/diagnostics">
                <ShieldAlert className="mr-2 h-4 w-4" />
                {copy.diagnostics}
              </Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to="/settings/repairs">
                <Wrench className="mr-2 h-4 w-4" />
                {copy.repairs}
              </Link>
            </Button>
          </div>
          {activeDoctorTask ? (
            <div className="mt-4">
              <SettingsTaskProgress title={copy.doctorTask} task={activeDoctorTask} compact />
            </div>
          ) : null}
          {activeUpdateTask ? (
            <div className="mt-4">
              <SettingsTaskProgress title={copy.systemUpdateTask} task={activeUpdateTask} compact />
            </div>
          ) : null}
          <div className="mt-5 grid gap-3 md:grid-cols-3">
            <SummaryCard
              to="/settings/errors"
              title={copy.latestFailure}
              value={!overviewReady ? '—' : !latestFailureScanned ? '—' : overview?.latest_failure ? adminEnumLabel('present', locale) : adminEnumLabel('clear', locale)}
              body={copy.diagnosticsBody}
              tone={!overviewReady || !latestFailureScanned ? 'default' : overview?.latest_failure ? 'destructive' : 'success'}
            />
            <SummaryCard
              to="/settings/repairs"
              title={copy.openRepairs}
              value={displayCount(totals.open_repairs, overviewReady)}
              body={copy.repairsBody}
              tone={Number(totals.open_repairs || 0) > 0 ? 'warning' : 'default'}
            />
            <SummaryCard
              to="/settings/connectors-health"
              title={copy.degradedConnectors}
              value={displayCount(totals.connectors_degraded, overviewReady)}
              body={copy.connectorHealthBody}
              tone={Number(totals.connectors_degraded || 0) > 0 ? 'warning' : 'default'}
            />
          </div>
      </section>

      <section className={`${surfaceClassName} px-5 py-5`}>
        <div className="flex items-center justify-between gap-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{copy.attentionQueue}</div>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/settings/quests">{copy.openAll}</Link>
          </Button>
        </div>
        <div className="mt-4 space-y-3">
          {activeWatchlist.length > 0 ? (
            activeWatchlist.map((item, index) => (
              <Link
                key={`${String(item.quest_id || 'quest')}-${index}`}
                to={`/settings/quests/${encodeURIComponent(String(item.quest_id || ''))}`}
                className="block rounded-[20px] border border-black/[0.08] bg-white/[0.68] p-4 transition hover:shadow-[0_14px_32px_-20px_rgba(18,24,32,0.2)] dark:border-white/[0.08] dark:bg-white/[0.03]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium">{String(item.title || item.quest_id || '—')}</div>
                    <div className="mt-1 text-xs text-soft-text-secondary">{String(item.quest_id || '')}</div>
                  </div>
                  <Badge variant={statusTone(String(item.runtime_status || ''))}>
                    {adminEnumLabel(String(item.runtime_status || ''), locale)}
                  </Badge>
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-soft-text-secondary">
                  <Badge variant="outline">{copy.anchor}: {String(item.active_anchor || '—')}</Badge>
                  <Badge variant="outline">{copy.decisions}: {displayCount(item.pending_decisions, overviewReady)}</Badge>
                  <Badge variant="outline">{copy.waitingMessages}: {displayCount(item.pending_user_messages, overviewReady)}</Badge>
                  <Badge variant="outline">{copy.runningBash}: {displayCount(item.running_bash, overviewReady)}</Badge>
                </div>
                {item.status_line ? <div className="mt-3 text-sm text-muted-foreground">{String(item.status_line)}</div> : null}
              </Link>
            ))
          ) : (
            <div className="text-sm text-soft-text-secondary">—</div>
          )}
        </div>
      </section>
    </div>
  )
}
