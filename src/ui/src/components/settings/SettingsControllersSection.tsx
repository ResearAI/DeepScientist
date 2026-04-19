import * as React from 'react'

import { SettingsGuideCard } from '@/components/settings/SettingsGuideCard'
import { adminEnumLabel, adminLocaleFromLanguage, pickAdminCopy } from '@/components/settings/settingsOpsCopy'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { getAdminControllers, runAdminController, toggleAdminController } from '@/lib/api/admin'
import { useI18n } from '@/lib/i18n/useI18n'

const surfaceClassName =
  'rounded-[28px] border border-black/[0.06] bg-[rgba(255,251,246,0.76)] shadow-[0_18px_40px_-30px_rgba(18,24,32,0.24)] backdrop-blur-sm dark:border-white/[0.08] dark:bg-white/[0.03]'
const dividerClassName = 'border-black/[0.06] dark:border-white/[0.08]'

const PAGE_COPY = {
  en: {
    title: 'Controllers',
    subtitle: 'Built-in governance controllers and their persisted state.',
    guide: `
### What this page is for

- Use **Controllers** to inspect and manually trigger governance rules that supervise the runtime from outside ordinary quest prompting.
- Controllers should be **specific and explainable**. They are not a hidden scheduler replacement.

### What the actions mean

- **Run** executes the controller immediately and records its latest result.
- **Enable / Disable** only changes persisted controller state. It does not retroactively mutate quests.
`,
    registry: 'Controller Registry',
    controller: 'Controller',
    description: 'Description',
    enabled: 'Enabled',
    lastRun: 'Last run',
    actions: 'Actions',
    refresh: 'Refresh',
    run: 'Run',
    disable: 'Disable',
    enable: 'Enable',
  },
  zh: {
    title: '控制器',
    subtitle: '内建治理控制器及其持久化状态。',
    guide: `
### 这一页用来做什么

- 用 **控制器** 检查并手动触发那些在普通 quest prompting 之外监管运行时的治理规则。
- 控制器应该是 **具体且可解释的**，而不是隐藏的调度器替代品。

### 这些动作分别是什么意思

- **运行** 会立刻执行一次控制器，并记录最新结果。
- **启用 / 禁用** 只会修改持久化的控制器状态，不会追溯性地修改已有 quest。
`,
    registry: '控制器注册表',
    controller: '控制器',
    description: '说明',
    enabled: '启用',
    lastRun: '上次运行',
    actions: '操作',
    refresh: '刷新',
    run: '运行',
    disable: '禁用',
    enable: '启用',
  },
} as const

export function SettingsControllersSection() {
  const { language } = useI18n('admin')
  const locale = adminLocaleFromLanguage(language)
  const copy = pickAdminCopy(language, PAGE_COPY)
  const [items, setItems] = React.useState<Array<Record<string, unknown>>>([])
  const [loading, setLoading] = React.useState(false)
  const [actionKey, setActionKey] = React.useState('')

  const load = React.useCallback(async () => {
    setLoading(true)
    try {
      const payload = await getAdminControllers()
      setItems(payload.items || [])
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="space-y-5">
      <SettingsGuideCard markdown={copy.guide} />

      <section className={`${surfaceClassName} overflow-hidden`}>
        <div className={`flex items-center justify-between gap-3 border-b ${dividerClassName} px-5 py-4`}>
          <div>
            <div className="text-sm font-medium">{copy.registry}</div>
            <div className="mt-1 text-xs text-muted-foreground">{copy.subtitle}</div>
          </div>
          <Button variant="outline" size="sm" onClick={() => void load()} isLoading={loading}>
            {copy.refresh}
          </Button>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{copy.controller}</TableHead>
              <TableHead>{copy.description}</TableHead>
              <TableHead>{copy.enabled}</TableHead>
              <TableHead>{copy.lastRun}</TableHead>
              <TableHead>{copy.actions}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => {
              const controllerId = String(item.controller_id || '')
              const enabled = Boolean(item.enabled)
              return (
                <TableRow key={controllerId}>
                  <TableCell className="font-medium">{controllerId}</TableCell>
                  <TableCell className="max-w-[720px] truncate text-xs text-soft-text-secondary">{String(item.description || '')}</TableCell>
                  <TableCell>
                    <Badge variant={enabled ? 'success' : 'secondary'}>
                      {enabled ? adminEnumLabel('enabled', locale) : adminEnumLabel('disabled', locale)}
                    </Badge>
                  </TableCell>
                  <TableCell>{String(item.last_run_at || '—')}</TableCell>
                  <TableCell>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        isLoading={actionKey == `${controllerId}:run`}
                        onClick={async () => {
                          setActionKey(`${controllerId}:run`)
                          try {
                            await runAdminController(controllerId)
                            await load()
                          } finally {
                            setActionKey('')
                          }
                        }}
                      >
                        {copy.run}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        isLoading={actionKey == `${controllerId}:toggle`}
                        onClick={async () => {
                          setActionKey(`${controllerId}:toggle`)
                          try {
                            await toggleAdminController(controllerId, !enabled)
                            await load()
                          } finally {
                            setActionKey('')
                          }
                        }}
                      >
                        {enabled ? copy.disable : copy.enable}
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </section>
    </div>
  )
}
