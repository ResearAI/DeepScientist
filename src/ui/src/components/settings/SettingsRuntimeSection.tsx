import * as React from 'react'

import { SettingsGuideCard } from '@/components/settings/SettingsGuideCard'
import { SettingsSystemTrendChart } from '@/components/settings/SettingsSystemTrendChart'
import { adminEnumLabel, adminLocaleFromLanguage, pickAdminCopy } from '@/components/settings/settingsOpsCopy'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/toast'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { getAdminRuntimeSessions, getAdminSystemHardware, saveAdminSystemHardware } from '@/lib/api/admin'
import { getBashLogs, stopBashSession } from '@/lib/api/bash'
import { useI18n } from '@/lib/i18n/useI18n'
import { useAdminOpsStore } from '@/lib/stores/admin-ops'
import { cn } from '@/lib/utils'
import type { AdminGpuInfo, AdminSystemHardwarePayload } from '@/lib/types/admin'

function formatGb(value: unknown) {
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric) || numeric <= 0) return '—'
  return `${numeric.toFixed(numeric >= 100 ? 0 : 1)} GB`
}

function cpuSummary(system: AdminSystemHardwarePayload['system'] | null | undefined) {
  const cpu = system?.cpu || {}
  const model = String(cpu.model || '').trim() || 'Unknown CPU'
  const physical = Number(cpu.physical_cores || 0)
  const logical = Number(cpu.logical_cores || 0)
  if (physical > 0 && logical > 0) {
    return `${model} · ${physical}P / ${logical}T`
  }
  if (logical > 0) {
    return `${model} · ${logical}T`
  }
  return model
}

function rootDiskSummary(system: AdminSystemHardwarePayload['system'] | null | undefined) {
  const disks = Array.isArray(system?.disks) ? system?.disks || [] : []
  const root = (disks.find((item) => String(item.mount || '') === '/') || disks[0]) as Record<string, unknown> | undefined
  if (!root) return '—'
  const free = formatGb(root.free_gb)
  const total = formatGb(root.total_gb)
  return `${free} free / ${total}`
}

function formatPercent(value: unknown) {
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return `${numeric.toFixed(numeric >= 100 ? 0 : 1)}%`
}

function latestUsageText(summary: Record<string, unknown> | undefined, prefix: string, labels: { current: string; average: string; peak: string }) {
  if (!summary) return prefix
  const latest = formatPercent(summary.latest_usage_percent)
  const avg = formatPercent(summary.avg_usage_percent)
  const peak = formatPercent(summary.max_usage_percent)
  return `${prefix} · ${labels.current} ${latest} · ${labels.average} ${avg} · ${labels.peak} ${peak}`
}

function gpuLabel(gpu: AdminGpuInfo) {
  const memory = typeof gpu.memory_total_gb === 'number' ? ` · ${gpu.memory_total_gb} GB` : ''
  return `${gpu.gpu_id}: ${gpu.name}${memory}`
}

const surfaceClassName =
  'rounded-[28px] border border-black/[0.06] bg-[rgba(255,251,246,0.76)] shadow-[0_18px_40px_-30px_rgba(18,24,32,0.24)] backdrop-blur-sm dark:border-white/[0.08] dark:bg-white/[0.03]'
const dividerClassName = 'border-black/[0.06] dark:border-white/[0.08]'

const PAGE_COPY = {
  en: {
    title: 'Runtime Sessions',
    guide: `
### What this page is for

- Use **Runtime Sessions** for two things: local system capacity and quest-local execution evidence.
- This page is the operator-facing place to see detected CPU / memory / disk / GPU state and to choose which GPUs the runtime should treat as available by default.

### How to use it

1. Refresh hardware detection when the machine state changed.
2. Keep GPU mode on **All detected GPUs** unless you intentionally want to reserve or isolate devices.
3. When you switch to **Selected GPU subset**, save the exact GPU ids you want the prompt/runtime to treat as available.
4. Then inspect bash sessions below when you need current execution evidence.
`,
    hardware: 'System Hardware',
    refreshHardware: 'Refresh Hardware',
    saveHardware: 'Save Hardware Policy',
    promptSummary: 'Prompt Summary',
    gpuSelection: 'Execution boundary',
    gpuSelectionHint: 'Choose a hardware mode first, then refine GPU ids only when the selected-subset route is active.',
    gpuModeAll: 'All detected GPUs',
    gpuModeAllBody: 'Expose every detected GPU to the runtime. This is the best default for single-user local machines.',
    gpuModeSelected: 'Selected GPU subset',
    gpuModeSelectedBody: 'Keep GPU execution enabled, but explicitly choose which GPU ids the runtime can treat as available.',
    gpuModeCpuOnly: 'CPU-only / no GPU',
    gpuModeCpuOnlyBody: 'Force the runtime to behave as if no GPU is available by saving an empty selected subset.',
    promptVisibility: 'Prompt visibility',
    promptVisible: 'Include hardware in prompt',
    promptVisibleBody: 'Let prompts see the selected hardware boundary and current machine summary.',
    promptHidden: 'Hide hardware from prompt',
    promptHiddenBody: 'Keep the runtime policy locally enforced, but omit the hardware summary from prompts.',
    host: 'Host',
    cpu: 'CPU',
    memory: 'Memory',
    rootDisk: 'Root Disk',
    systemTrajectory: 'System Trajectory',
    current: 'now',
    average: 'avg',
    peak: 'peak',
    gpus: 'GPUs',
    selectedSubsetHint: 'Toggle the exact GPU ids below. Only the selected ids will remain available after save.',
    cpuOnlyHint: 'No GPU ids are selected. Saving now will force a CPU-only boundary.',
    noGpu: 'No GPU detected.',
    hardwareSaved: 'Hardware preference saved.',
    sessions: 'Sessions',
    refresh: 'Refresh',
    quest: 'Quest',
    bash: 'Bash',
    kind: 'Kind',
    status: 'Status',
    command: 'Command',
    selectedOutput: 'Selected Output',
    stop: 'Stop',
    noOutput: 'No output loaded.',
    selectSession: 'Select a session to inspect recent output.',
  },
  zh: {
    title: '运行时会话',
    guide: `
### 这一页用来做什么

- 用 **运行时会话** 同时查看两类东西：本机系统资源，以及 quest 本地执行证据。
- 这里也是运维侧查看 CPU / 内存 / 硬盘 / GPU，并指定默认可用 GPU 集合的地方。

### 怎么使用

1. 当机器状态变化后，先刷新硬件检测。
2. 默认保持 **全部检测到的 GPU**。
3. 只有当你明确想保留或隔离设备时，再切到 **指定 GPU 子集** 并保存。
4. 然后再在下面查看 bash 会话与最近输出。
`,
    hardware: '系统硬件',
    refreshHardware: '刷新硬件',
    saveHardware: '保存硬件策略',
    promptSummary: 'Prompt 摘要',
    gpuSelection: '执行边界',
    gpuSelectionHint: '先选择硬件模式；只有在“指定 GPU 子集”模式下，才需要进一步挑选 GPU id。',
    gpuModeAll: '全部检测到的 GPU',
    gpuModeAllBody: '把所有检测到的 GPU 都暴露给运行时。这是单机本地使用的默认推荐模式。',
    gpuModeSelected: '指定 GPU 子集',
    gpuModeSelectedBody: '仍然使用 GPU，但明确指定哪些 GPU id 能被运行时视为可用。',
    gpuModeCpuOnly: '仅 CPU / 不使用 GPU',
    gpuModeCpuOnlyBody: '保存一个空的 GPU 子集，让运行时按“无 GPU 可用”的方式工作。',
    promptVisibility: 'Prompt 可见性',
    promptVisible: '将硬件注入 prompt',
    promptVisibleBody: '让 prompt 能看到当前选择的硬件边界和机器摘要。',
    promptHidden: '对 prompt 隐藏硬件',
    promptHiddenBody: '仅在本地运行时层面执行硬件限制，但不把硬件摘要写进 prompt。',
    host: '主机',
    cpu: 'CPU',
    memory: '内存',
    rootDisk: '根分区',
    systemTrajectory: '系统轨迹',
    current: '当前',
    average: '平均',
    peak: '峰值',
    gpus: 'GPU',
    selectedSubsetHint: '在下方切换具体 GPU id。保存后，只有选中的 GPU 会继续对运行时可见。',
    cpuOnlyHint: '当前没有选择任何 GPU id。现在保存，就会变成 CPU-only 边界。',
    noGpu: '当前未检测到 GPU。',
    hardwareSaved: '已保存硬件偏好。',
    sessions: '会话',
    refresh: '刷新',
    quest: 'Quest',
    bash: 'Bash',
    kind: '类型',
    status: '状态',
    command: '命令',
    selectedOutput: '当前输出',
    stop: '停止',
    noOutput: '当前没有加载到输出。',
    selectSession: '请选择一个会话来检查最近输出。',
  },
} as const

type ModeCardProps = {
  title: string
  body: string
  active: boolean
  meta?: string
  onClick: () => void
}

function ModeCard({ title, body, active, meta, onClick }: ModeCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-[22px] border px-4 py-4 text-left transition',
        active
          ? 'border-black/[0.22] bg-[linear-gradient(145deg,rgba(241,230,215,0.92),rgba(230,236,240,0.72))] shadow-[0_16px_36px_-26px_rgba(18,24,32,0.28)]'
          : 'border-black/[0.08] bg-white/[0.52] hover:border-black/[0.14] dark:border-white/[0.12] dark:bg-white/[0.04]'
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-semibold text-foreground">{title}</div>
        {active ? <Badge variant="secondary">Active</Badge> : null}
      </div>
      <div className="mt-2 text-sm leading-6 text-muted-foreground">{body}</div>
      {meta ? <div className="mt-3 text-xs text-muted-foreground">{meta}</div> : null}
    </button>
  )
}

export function SettingsRuntimeSection() {
  const { language } = useI18n('admin')
  const { addToast } = useToast()
  const locale = adminLocaleFromLanguage(language)
  const copy = pickAdminCopy(language, PAGE_COPY)
  const [items, setItems] = React.useState<Array<Record<string, unknown>>>([])
  const [selected, setSelected] = React.useState<Record<string, unknown> | null>(null)
  const [logs, setLogs] = React.useState<string[]>([])
  const [hardware, setHardware] = React.useState<AdminSystemHardwarePayload | null>(null)
  const [hardwareSaving, setHardwareSaving] = React.useState(false)
  const [gpuModeDraft, setGpuModeDraft] = React.useState<'all' | 'selected'>('all')
  const [gpuDraft, setGpuDraft] = React.useState<string[]>([])
  const [includePromptDraft, setIncludePromptDraft] = React.useState(true)
  const setContext = useAdminOpsStore((state) => state.setContext)

  const load = React.useCallback(async () => {
    const payload = await getAdminRuntimeSessions(400)
    setItems(payload.items || [])
  }, [])

  const loadHardware = React.useCallback(async () => {
    const payload = await getAdminSystemHardware()
    setHardware(payload)
    const preferences = payload.preferences || {}
    setGpuModeDraft((String(preferences.gpu_selection_mode || 'all') === 'selected' ? 'selected' : 'all'))
    setGpuDraft(Array.isArray(preferences.selected_gpu_ids) ? preferences.selected_gpu_ids.map((item) => String(item)) : [])
    setIncludePromptDraft(Boolean(preferences.include_system_hardware_in_prompt ?? true))
  }, [])

  React.useEffect(() => {
    void load()
    void loadHardware()
  }, [load, loadHardware])

  React.useEffect(() => {
    const questId = String(selected?.quest_id || '').trim()
    const bashId = String(selected?.bash_id || '').trim()
    if (!questId || !bashId) {
      setLogs([])
      return
    }
    void getBashLogs(questId, bashId, { limit: 120 }).then((payload) => {
      setLogs((payload.entries || []).map((item) => String(item.line || '')))
    })
    setContext({
      sourcePage: '/settings/runtime',
      scope: 'runtime',
      targets: { quest_ids: [questId], bash_ids: [bashId] },
    })
  }, [selected, setContext])

  const availableGpus = React.useMemo(() => (hardware?.system?.gpus || []) as AdminGpuInfo[], [hardware])
  const recentStats = React.useMemo(() => (hardware?.recent_stats || {}) as Record<string, unknown>, [hardware?.recent_stats])
  const usageLabels = React.useMemo(
    () => ({ current: copy.current, average: copy.average, peak: copy.peak }),
    [copy.average, copy.current, copy.peak]
  )
  const effectiveGpuIds = React.useMemo(() => {
    if (gpuModeDraft !== 'selected') {
      return availableGpus.map((item) => String(item.gpu_id))
    }
    const availableIds = new Set(availableGpus.map((item) => String(item.gpu_id)))
    return gpuDraft.filter((item) => availableIds.has(item))
  }, [availableGpus, gpuDraft, gpuModeDraft])
  const isCpuOnly = gpuModeDraft === 'selected' && effectiveGpuIds.length === 0

  const persistHardware = React.useCallback(async () => {
    setHardwareSaving(true)
    try {
      const payload = await saveAdminSystemHardware({
        gpu_selection_mode: gpuModeDraft,
        selected_gpu_ids: gpuDraft,
        include_system_hardware_in_prompt: includePromptDraft,
      })
      setHardware(payload)
      const preferences = payload.preferences || {}
      setGpuModeDraft((String(preferences.gpu_selection_mode || 'all') === 'selected' ? 'selected' : 'all'))
      setGpuDraft(Array.isArray(preferences.selected_gpu_ids) ? preferences.selected_gpu_ids.map((item) => String(item)) : [])
      setIncludePromptDraft(Boolean(preferences.include_system_hardware_in_prompt ?? true))
      addToast({ title: copy.hardwareSaved, variant: 'success' })
    } catch (caught) {
      addToast({
        title: copy.hardware,
        message: caught instanceof Error ? caught.message : String(caught),
        variant: 'error',
      })
    } finally {
      setHardwareSaving(false)
    }
  }, [addToast, copy.hardware, copy.hardwareSaved, gpuDraft, gpuModeDraft, includePromptDraft])

  return (
    <div className="space-y-5">
      <SettingsGuideCard markdown={copy.guide} title={copy.title} />
      <div className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
        <section className={`${surfaceClassName} px-5 py-5`}>
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{copy.hardware}</div>
              <div className="mt-1 text-sm text-muted-foreground">{String(hardware?.system?.host?.hostname || '—')}</div>
            </div>
            <Button variant="outline" size="sm" onClick={() => void loadHardware()}>
              {copy.refreshHardware}
            </Button>
          </div>

          <div className="mt-5 overflow-hidden rounded-[22px] bg-white/[0.42] dark:bg-white/[0.03]">
            <div className={`grid divide-y ${dividerClassName} md:grid-cols-2 md:divide-y-0 xl:grid-cols-4 xl:divide-x`}>
              <div className="px-4 py-4">
                <div className="text-xs text-soft-text-secondary">{copy.host}</div>
                <div className="mt-2 text-sm font-medium">{String(hardware?.system?.host?.hostname || '—')}</div>
              </div>
              <div className="px-4 py-4">
                <div className="text-xs text-soft-text-secondary">{copy.cpu}</div>
                <div className="mt-2 text-sm font-medium">{cpuSummary(hardware?.system)}</div>
                <div className="mt-1 text-[11px] text-soft-text-secondary">
                  {latestUsageText((recentStats.cpu as Record<string, unknown> | undefined) || undefined, copy.cpu, usageLabels)}
                </div>
              </div>
              <div className="px-4 py-4">
                <div className="text-xs text-soft-text-secondary">{copy.memory}</div>
                <div className="mt-2 text-sm font-medium">{formatGb(hardware?.system?.memory?.total_gb)}</div>
                <div className="mt-1 text-[11px] text-soft-text-secondary">
                  {latestUsageText((recentStats.memory as Record<string, unknown> | undefined) || undefined, formatGb((recentStats.memory as Record<string, unknown> | undefined)?.latest_used_gb), usageLabels)}
                </div>
              </div>
              <div className="px-4 py-4">
                <div className="text-xs text-soft-text-secondary">{copy.rootDisk}</div>
                <div className="mt-2 text-sm font-medium">{rootDiskSummary(hardware?.system)}</div>
                <div className="mt-1 text-[11px] text-soft-text-secondary">
                  {latestUsageText((recentStats.root_disk as Record<string, unknown> | undefined) || undefined, copy.rootDisk, usageLabels)}
                </div>
              </div>
            </div>
          </div>

          <div className={`mt-5 border-t ${dividerClassName} pt-5`}>
            <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
              <div>
                <div className="text-sm font-medium">{copy.gpuSelection}</div>
                <div className="mt-1 text-xs leading-6 text-soft-text-secondary">{copy.gpuSelectionHint}</div>
              </div>
              <Button variant="secondary" size="sm" isLoading={hardwareSaving} onClick={() => void persistHardware()}>
                {copy.saveHardware}
              </Button>
            </div>

            <div className="mt-4 grid gap-3 lg:grid-cols-3">
              <ModeCard
                title={copy.gpuModeAll}
                body={copy.gpuModeAllBody}
                active={gpuModeDraft === 'all'}
                meta={`${availableGpus.length} GPU${availableGpus.length === 1 ? '' : 's'}`}
                onClick={() => {
                  setGpuModeDraft('all')
                  setGpuDraft(availableGpus.map((item) => String(item.gpu_id)))
                }}
              />
              <ModeCard
                title={copy.gpuModeSelected}
                body={copy.gpuModeSelectedBody}
                active={gpuModeDraft === 'selected' && !isCpuOnly}
                meta={effectiveGpuIds.length > 0 ? effectiveGpuIds.join(', ') : undefined}
                onClick={() => {
                  setGpuModeDraft('selected')
                  if (gpuDraft.length === 0 && availableGpus.length > 0) {
                    setGpuDraft([String(availableGpus[0].gpu_id)])
                  }
                }}
              />
              <ModeCard
                title={copy.gpuModeCpuOnly}
                body={copy.gpuModeCpuOnlyBody}
                active={isCpuOnly}
                meta={copy.cpuOnlyHint}
                onClick={() => {
                  setGpuModeDraft('selected')
                  setGpuDraft([])
                }}
              />
            </div>

            {gpuModeDraft === 'selected' ? (
              <div className="mt-4">
                <div className="mb-2 text-xs text-soft-text-secondary">{copy.gpus}</div>
                {availableGpus.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {availableGpus.map((gpu) => {
                      const gpuId = String(gpu.gpu_id)
                      const selectedByDraft = effectiveGpuIds.includes(gpuId)
                      return (
                        <Button
                          key={gpuId}
                          type="button"
                          size="sm"
                          variant={selectedByDraft ? 'secondary' : 'outline'}
                          onClick={() => {
                            setGpuModeDraft('selected')
                            setGpuDraft((current) =>
                              current.includes(gpuId) ? current.filter((item) => item !== gpuId) : [...current, gpuId]
                            )
                          }}
                        >
                          {gpuLabel(gpu)}
                        </Button>
                      )
                    })}
                  </div>
                ) : (
                  <div className="text-sm text-soft-text-secondary">{copy.noGpu}</div>
                )}
                <div className="mt-3 text-xs text-soft-text-secondary">
                  {effectiveGpuIds.length > 0 ? copy.selectedSubsetHint : copy.cpuOnlyHint}
                </div>
              </div>
            ) : null}

            <div className={`mt-5 border-t ${dividerClassName} pt-5`}>
              <div className="text-sm font-medium">{copy.promptVisibility}</div>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <ModeCard
                  title={copy.promptVisible}
                  body={copy.promptVisibleBody}
                  active={includePromptDraft}
                  onClick={() => setIncludePromptDraft(true)}
                />
                <ModeCard
                  title={copy.promptHidden}
                  body={copy.promptHiddenBody}
                  active={!includePromptDraft}
                  onClick={() => setIncludePromptDraft(false)}
                />
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              <Badge variant="secondary">mode: {isCpuOnly ? 'cpu-only' : gpuModeDraft}</Badge>
              <Badge variant="secondary">effective: {effectiveGpuIds.length > 0 ? effectiveGpuIds.join(',') : 'none'}</Badge>
              <Badge variant="secondary">
                CUDA_VISIBLE_DEVICES: {String(hardware?.preferences?.cuda_visible_devices || (effectiveGpuIds.length > 0 ? effectiveGpuIds.join(',') : 'unset'))}
              </Badge>
            </div>
          </div>

          <div className={`mt-5 grid gap-5 border-t ${dividerClassName} pt-5 xl:grid-cols-[0.8fr_1.2fr]`}>
            <div>
              <div className="text-sm font-medium">{copy.promptSummary}</div>
              <div className="mt-2 text-xs leading-6 text-soft-text-secondary">{String(hardware?.prompt_hardware_summary || '—')}</div>
            </div>
            <div>
              <div className="mb-3 text-sm font-medium">{copy.systemTrajectory}</div>
              <SettingsSystemTrendChart recentStats={hardware?.recent_stats} locale={locale} />
            </div>
          </div>
        </section>

        <section className={`${surfaceClassName} flex min-h-0 flex-col px-5 py-5`}>
          <div className="flex flex-row items-center justify-between gap-3">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{copy.selectedOutput}</div>
              {selected ? (
                <div className="mt-1 text-xs text-soft-text-secondary">
                  {String(selected.quest_id || '')} · {String(selected.bash_id || '')}
                </div>
              ) : null}
            </div>
            {selected ? (
              <Button
                size="sm"
                variant="destructive"
                onClick={async () => {
                  const questId = String(selected.quest_id || '')
                  const bashId = String(selected.bash_id || '')
                  if (!questId || !bashId) return
                  await stopBashSession(questId, bashId, { reason: 'Stopped from settings runtime page' })
                  await load()
                }}
              >
                {copy.stop}
              </Button>
            ) : null}
          </div>
          <div className="mt-4 min-h-0 flex-1">
            {selected ? (
              <div className="max-h-[70vh] min-h-[320px] overflow-auto rounded-[22px] bg-black px-4 py-3 font-mono text-xs leading-6 text-[#EAE7E0]">
                {logs.length ? logs.map((line, index) => <div key={`${index}-${line}`}>{line}</div>) : <div>{copy.noOutput}</div>}
              </div>
            ) : (
              <div className="text-sm text-soft-text-secondary">{copy.selectSession}</div>
            )}
          </div>
        </section>
      </div>

      <section className={`${surfaceClassName} overflow-hidden`}>
        <div className={`flex items-center justify-between gap-3 border-b ${dividerClassName} px-5 py-4`}>
          <div className="text-sm font-medium">{copy.sessions}</div>
          <Button variant="outline" size="sm" onClick={() => void load()}>
            {copy.refresh}
          </Button>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{copy.quest}</TableHead>
              <TableHead>{copy.bash}</TableHead>
              <TableHead>{copy.kind}</TableHead>
              <TableHead>{copy.status}</TableHead>
              <TableHead>{copy.command}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={`${item.quest_id}:${item.bash_id}`} onClick={() => setSelected(item)} className="cursor-pointer">
                <TableCell>{String(item.quest_id || '')}</TableCell>
                <TableCell>{String(item.bash_id || '')}</TableCell>
                <TableCell>{String(item.kind || 'exec')}</TableCell>
                <TableCell>
                  <Badge variant={['running', 'terminating'].includes(String(item.status || '')) ? 'warning' : 'secondary'}>
                    {adminEnumLabel(item.status || 'unknown', locale)}
                  </Badge>
                </TableCell>
                <TableCell className="max-w-[340px] truncate text-xs text-soft-text-secondary">{String(item.command || 'bash_exec')}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
    </div>
  )
}
