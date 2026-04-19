import * as React from 'react'

import { SettingsGuideCard } from '@/components/settings/SettingsGuideCard'
import { pickAdminCopy } from '@/components/settings/settingsOpsCopy'
import { SettingsTaskProgress } from '@/components/settings/SettingsTaskProgress'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { getAdminDoctor, getAdminFailures, getAdminRuntimeTools, startAdminDoctorTask, startAdminSystemUpdateActionTask, startAdminSystemUpdateCheckTask } from '@/lib/api/admin'
import { useAdminTaskStream } from '@/lib/hooks/useAdminTaskStream'
import { useI18n } from '@/lib/i18n/useI18n'

const surfaceClassName =
  'rounded-[28px] border border-black/[0.06] bg-[rgba(255,251,246,0.76)] shadow-[0_18px_40px_-30px_rgba(18,24,32,0.24)] backdrop-blur-sm dark:border-white/[0.08] dark:bg-white/[0.03]'
const dividerClassName = 'border-black/[0.06] dark:border-white/[0.08]'

function summarizeToolPayload(payload: Record<string, unknown>) {
  const items = Object.entries(payload)
    .filter(([, value]) => value !== null && value !== undefined && !Array.isArray(value) && typeof value !== 'object')
    .slice(0, 6)
    .map(([key, value]) => `${key}: ${String(value)}`)
  return items.join(' · ')
}

const PAGE_COPY = {
  en: {
    title: 'Diagnostics',
    subtitle: 'Manual diagnosis, failure triage, and runtime tool visibility.',
    guide: `
### What this page is for

- Use **Diagnostics** when you need explicit health checks, recent failure evidence, and runtime tool status.
- This page is **manual-first**. It avoids background-heavy work unless you explicitly start a task.

### Doctor

- **Run Doctor** starts a background admin task.
- Progress is reported step by step rather than blocking the page.
- The latest result is cached so reopening the page does not rerun the full diagnosis.

### System update

- **Check update** only checks the current package state.
- **Install latest** requests the launcher-managed update flow.
- **Remind later** and **Skip version** are operator actions, not passive status reads.
`,
    doctor: 'Doctor',
    runDoctor: 'Run Doctor',
    doctorTask: 'Doctor Task',
    latestCachedResult: 'Latest Cached Result',
    noCachedDoctor: 'No cached doctor report yet.',
    runtimeTools: 'Runtime Tools And Update Actions',
    checkUpdate: 'Check Update',
    installLatest: 'Install Latest',
    remindLater: 'Remind Later',
    skipVersion: 'Skip Version',
    systemUpdateTask: 'System Update Task',
    recentFailures: 'Recent Failures',
    quest: 'Quest',
    type: 'Type',
    run: 'Run',
    summary: 'Summary',
  },
  zh: {
    title: '诊断',
    subtitle: '手动诊断、失败分诊与运行时工具可见性。',
    guide: `
### 这一页用来做什么

- 当你需要显式健康检查、最近失败证据和运行时工具状态时，用 **诊断** 页面。
- 这一页是 **人工触发优先** 的，除非你明确启动任务，否则不会主动做重型后台工作。

### Doctor

- **运行 Doctor** 会启动一个后台管理任务。
- 页面会逐步展示进度，而不是整页阻塞。
- 最新结果会被缓存，重新打开页面时不会重新跑完整诊断。

### 系统更新

- **检查更新** 只检查当前包状态。
- **安装最新版** 会请求 launcher 管理的更新流程。
- **稍后提醒** 和 **跳过版本** 都是运维动作，不是被动状态读取。
`,
    doctor: 'Doctor',
    runDoctor: '运行 Doctor',
    doctorTask: 'Doctor 任务',
    latestCachedResult: '最近缓存结果',
    noCachedDoctor: '当前还没有缓存的 Doctor 报告。',
    runtimeTools: '运行时工具与更新动作',
    checkUpdate: '检查更新',
    installLatest: '安装最新版',
    remindLater: '稍后提醒',
    skipVersion: '跳过版本',
    systemUpdateTask: '系统更新任务',
    recentFailures: '最近失败',
    quest: 'Quest',
    type: '类型',
    run: '运行',
    summary: '摘要',
  },
} as const

export function SettingsDiagnosticsSection() {
  const { language } = useI18n('admin')
  const copy = pickAdminCopy(language, PAGE_COPY)
  const [doctor, setDoctor] = React.useState<Record<string, unknown> | null>(null)
  const [failures, setFailures] = React.useState<Array<Record<string, unknown>>>([])
  const [runtimeTools, setRuntimeTools] = React.useState<Record<string, Record<string, unknown>>>({})
  const [doctorTaskId, setDoctorTaskId] = React.useState<string | null>(null)
  const [updateTaskId, setUpdateTaskId] = React.useState<string | null>(null)
  const doctorStream = useAdminTaskStream(doctorTaskId)
  const updateStream = useAdminTaskStream(updateTaskId)

  const load = React.useCallback(async () => {
    const [doctorPayload, failurePayload, runtimeToolsPayload] = await Promise.all([
      getAdminDoctor(),
      getAdminFailures(100),
      getAdminRuntimeTools(),
    ])
    setDoctor(doctorPayload.cached || null)
    setFailures(failurePayload.items || [])
    setRuntimeTools(runtimeToolsPayload.items || {})
    const latestTask = doctorPayload.latest_task
    if (latestTask && ['queued', 'running'].includes(String(latestTask.status || ''))) {
      setDoctorTaskId(latestTask.task_id)
    }
  }, [])

  React.useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="space-y-5">
      <SettingsGuideCard markdown={copy.guide} />
      <div className="grid gap-4 xl:grid-cols-[0.92fr_1.08fr]">
        <section className={`${surfaceClassName} px-5 py-5`}>
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{copy.doctor}</div>
              <div className="mt-1 text-sm text-muted-foreground">{copy.latestCachedResult}</div>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={async () => {
                const response = await startAdminDoctorTask()
                setDoctorTaskId(response.task.task_id)
              }}
            >
              {copy.runDoctor}
            </Button>
          </div>
          {doctorStream.task ? (
            <div className="mt-4">
              <SettingsTaskProgress title={copy.doctorTask} task={doctorStream.task} />
            </div>
          ) : null}
          <div className={`mt-5 border-t ${dividerClassName} pt-5`}>
            {doctor ? (
              <pre className="max-h-[360px] overflow-auto rounded-[20px] bg-black px-4 py-4 font-mono text-xs leading-6 text-[#EAE7E0]">
                {JSON.stringify(doctor, null, 2)}
              </pre>
            ) : (
              <div className="text-sm text-soft-text-secondary">{copy.noCachedDoctor}</div>
            )}
          </div>
        </section>

        <section className={`${surfaceClassName} px-5 py-5`}>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{copy.runtimeTools}</div>
            <div className="mt-1 text-sm text-muted-foreground">{copy.systemUpdateTask}</div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={async () => {
                const response = await startAdminSystemUpdateCheckTask()
                setUpdateTaskId(response.task.task_id)
              }}
            >
              {copy.checkUpdate}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                const response = await startAdminSystemUpdateActionTask('install_latest')
                setUpdateTaskId(response.task.task_id)
              }}
            >
              {copy.installLatest}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                const response = await startAdminSystemUpdateActionTask('remind_later')
                setUpdateTaskId(response.task.task_id)
              }}
            >
              {copy.remindLater}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                const response = await startAdminSystemUpdateActionTask('skip_version')
                setUpdateTaskId(response.task.task_id)
              }}
            >
              {copy.skipVersion}
            </Button>
          </div>
          {updateStream.task ? (
            <div className="mt-4">
              <SettingsTaskProgress title={copy.systemUpdateTask} task={updateStream.task} />
            </div>
          ) : null}
          <div className={`mt-5 divide-y border-t ${dividerClassName} pt-1`}>
            {Object.entries(runtimeTools).map(([name, payload]) => (
              <div key={name} className="py-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium">{name}</div>
                  <Badge variant="secondary">{String(payload.status || payload.ok || 'available')}</Badge>
                </div>
                <div className="mt-2 text-xs leading-6 text-soft-text-secondary">
                  {summarizeToolPayload(payload) || JSON.stringify(payload)}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className={`${surfaceClassName} overflow-hidden`}>
        <div className={`border-b ${dividerClassName} px-5 py-4`}>
          <div className="text-sm font-medium">{copy.recentFailures}</div>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{copy.quest}</TableHead>
              <TableHead>{copy.type}</TableHead>
              <TableHead>{copy.run}</TableHead>
              <TableHead>{copy.summary}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {failures.map((item, index) => (
              <TableRow key={`${item.quest_id || 'failure'}-${item.run_id || index}`}>
                <TableCell>{String(item.quest_id || '')}</TableCell>
                <TableCell>{String(item.event_type || '')}</TableCell>
                <TableCell>{String(item.run_id || '—')}</TableCell>
                <TableCell className="max-w-[720px] truncate text-xs text-soft-text-secondary">{String(item.summary || '')}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
    </div>
  )
}

