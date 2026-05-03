import * as React from 'react'
import { Link } from 'react-router-dom'

import { SettingsGuideCard } from '@/components/settings/SettingsGuideCard'
import { adminEnumLabel, adminLocaleFromLanguage, pickAdminCopy } from '@/components/settings/settingsOpsCopy'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { getAdminErrors } from '@/lib/api/admin'
import { useI18n } from '@/lib/i18n/useI18n'

const surfaceClassName =
  'rounded-[28px] border border-black/[0.06] bg-[rgba(255,251,246,0.76)] shadow-[0_18px_40px_-30px_rgba(18,24,32,0.24)] backdrop-blur-sm dark:border-white/[0.08] dark:bg-white/[0.03]'
const dividerClassName = 'border-black/[0.06] dark:border-white/[0.08]'

const PAGE_COPY = {
  en: {
    title: 'Error Console',
    subtitle: 'One place to see the most important local errors and decide what to check next.',
    guide: `
### What this page is for

- Use **Error Console** when you want the most important problems in one place.
- This page brings together connector problems, runtime failures, daemon errors, and failed admin tasks.

### How to use it

- Start here before opening detailed logs or a project page.
- If the problem should be reported upstream, continue to **Issue Report** with one click.
`,
    degradedConnectors: 'Degraded connectors',
    runtimeFailures: 'Runtime failures',
    daemonErrors: 'Daemon errors',
    failedTasks: 'Failed tasks',
    action: 'Action',
    prepareIssue: 'Open Issue Report',
    issueHelp:
      'Use Issue Report to prepare a GitHub issue draft with environment info, recent failures, connector status, doctor results, and local creation fallback.',
    runtimeFailuresTitle: 'Runtime Failures',
    connectorErrors: 'Connector Errors',
    quest: 'Quest',
    type: 'Type',
    summary: 'Summary',
  },
  zh: {
    title: '错误控制台',
    subtitle: '把当前最重要的本地错误集中放在一个地方，方便判断下一步该检查什么。',
    guide: `
### 这一页用来做什么

- 当你想先快速看清当前最重要的问题时，就用 **错误控制台**。
- 这一页会把连接器异常、运行时失败、daemon 错误，以及失败的管理任务放在一起。

### 怎么使用

- 在打开更细的日志页或项目页之前，先看这里。
- 如果问题值得提交给上游，可以一键继续到 **问题报告**。
`,
    degradedConnectors: '退化连接器',
    runtimeFailures: '运行时失败',
    daemonErrors: 'Daemon 错误',
    failedTasks: '失败任务',
    action: '动作',
    prepareIssue: '打开问题报告',
    issueHelp: '用问题报告生成 GitHub issue 草稿，其中会包含环境信息、最近失败、连接器状态、Doctor 结果，以及本地创建兜底。',
    runtimeFailuresTitle: '运行时失败',
    connectorErrors: '连接器错误',
    quest: 'Quest',
    type: '类型',
    summary: '摘要',
  },
} as const

export function SettingsErrorsSection() {
  const { language } = useI18n('admin')
  const locale = adminLocaleFromLanguage(language)
  const copy = pickAdminCopy(language, PAGE_COPY)
  const [payload, setPayload] = React.useState<Record<string, any> | null>(null)

  const load = React.useCallback(async () => {
    const next = await getAdminErrors(100)
    setPayload(next)
  }, [])

  React.useEffect(() => {
    void load()
  }, [load])

  const totals = payload?.totals || {}

  return (
    <div className="space-y-5">
      <SettingsGuideCard markdown={copy.guide} />

      <section className={`${surfaceClassName} overflow-hidden`}>
        <div className={`grid divide-y ${dividerClassName} md:grid-cols-2 md:divide-y-0 xl:grid-cols-4 xl:divide-x`}>
          {[
            [copy.degradedConnectors, Number(totals.degraded_connectors || 0)],
            [copy.runtimeFailures, Number(totals.runtime_failures || 0)],
            [copy.daemonErrors, Number(totals.daemon_errors || 0)],
            [copy.failedTasks, Number(totals.failed_tasks || 0)],
          ].map(([label, value]) => (
            <div key={String(label)} className="px-5 py-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
              <div className="mt-2 text-3xl font-semibold tracking-tight">{value}</div>
            </div>
          ))}
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[0.72fr_1.28fr]">
        <section className={`${surfaceClassName} px-5 py-5`}>
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{copy.action}</div>
              <div className="mt-1 text-sm text-muted-foreground">{copy.issueHelp}</div>
            </div>
            <Button variant="secondary" size="sm" asChild>
              <Link to="/settings/issues">{copy.prepareIssue}</Link>
            </Button>
          </div>
        </section>

        <section className={`${surfaceClassName} px-5 py-5`}>
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{copy.connectorErrors}</div>
          <div className={`mt-4 divide-y ${dividerClassName}`}>
            {(payload?.degraded_connectors || []).map((item: Record<string, unknown>, index: number) => (
              <div key={`${item.name || 'connector'}-${index}`} className="py-4">
                <div className="flex items-center gap-3">
                  <div className="font-medium">{String(item.name || '')}</div>
                  <Badge variant="warning">{adminEnumLabel(item.connection_state || 'degraded', locale)}</Badge>
                </div>
                <div className="mt-2 text-xs text-soft-text-secondary">{String(item.last_error || '')}</div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className={`${surfaceClassName} overflow-hidden`}>
        <div className={`border-b ${dividerClassName} px-5 py-4`}>
          <div className="text-sm font-medium">{copy.runtimeFailuresTitle}</div>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{copy.quest}</TableHead>
              <TableHead>{copy.type}</TableHead>
              <TableHead>{copy.summary}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(payload?.runtime_failures || []).map((item: Record<string, unknown>, index: number) => (
              <TableRow key={`${item.quest_id || 'failure'}-${index}`}>
                <TableCell>{String(item.quest_id || '')}</TableCell>
                <TableCell>{String(item.event_type || '')}</TableCell>
                <TableCell className="max-w-[920px] truncate text-xs text-soft-text-secondary">{String(item.summary || '')}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
    </div>
  )
}
