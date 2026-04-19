import * as React from 'react'

import { SettingsGuideCard } from '@/components/settings/SettingsGuideCard'
import { adminEnumLabel, adminLocaleFromLanguage, pickAdminCopy } from '@/components/settings/settingsOpsCopy'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { closeAdminRepair, createAdminRepair, getAdminRepairs } from '@/lib/api/admin'
import { useI18n } from '@/lib/i18n/useI18n'
import { useAdminOpsStore } from '@/lib/stores/admin-ops'
import type { AdminRepair } from '@/lib/types/admin'

const surfaceClassName =
  'rounded-[28px] border border-black/[0.06] bg-[rgba(255,251,246,0.76)] shadow-[0_18px_40px_-30px_rgba(18,24,32,0.24)] backdrop-blur-sm dark:border-white/[0.08] dark:bg-white/[0.03]'
const dividerClassName = 'border-black/[0.06] dark:border-white/[0.08]'

const PAGE_COPY = {
  en: {
    title: 'Repairs',
    subtitle: 'Manage admin repair sessions and reopen them in the left-side copilot dock.',
    guide: `
### What this page is for

- Use **Repairs** to manage administrator repair sessions that open in the left-side AdminOps dock.
- Each repair session is backed by an **ops quest**, so it reuses the normal quest event stream and copilot surfaces.

### Workflow

1. Create a repair with a precise request.
2. Open it in the dock.
3. Continue diagnosis or repair inside the dock.
4. Close the repair when the operator workflow is done.
`,
    newRepair: 'New Repair',
    requestPlaceholder: 'Describe the issue to diagnose or fix',
    create: 'Create',
    repairSessions: 'Repair Sessions',
    refresh: 'Refresh',
    repair: 'Repair',
    status: 'Status',
    scope: 'Scope',
    quest: 'Quest',
    request: 'Request',
    actions: 'Actions',
    open: 'Open',
    close: 'Close',
  },
  zh: {
    title: '修复',
    subtitle: '管理管理员修复会话，并在左下 Copilot Dock 中重新打开它们。',
    guide: `
### 这一页用来做什么

- 用 **修复** 管理管理员修复会话，这些会话会在左侧 AdminOps Dock 中打开。
- 每个修复会话背后都是一个 **ops quest**，因此会复用正常 quest 的事件流与 copilot 面。

### 工作流

1. 用明确请求创建一个修复会话。
2. 在 Dock 中打开它。
3. 在 Dock 里继续诊断或修复。
4. 当运维流程结束后，再关闭这个修复会话。
`,
    newRepair: '新建修复',
    requestPlaceholder: '描述需要诊断或修复的问题',
    create: '创建',
    repairSessions: '修复会话',
    refresh: '刷新',
    repair: '修复',
    status: '状态',
    scope: '范围',
    quest: 'Quest',
    request: '请求',
    actions: '操作',
    open: '打开',
    close: '关闭',
  },
} as const

export function SettingsRepairsSection() {
  const { language } = useI18n('admin')
  const locale = adminLocaleFromLanguage(language)
  const copy = pickAdminCopy(language, PAGE_COPY)
  const [items, setItems] = React.useState<AdminRepair[]>([])
  const [requestText, setRequestText] = React.useState('')
  const [loading, setLoading] = React.useState(false)
  const [closingId, setClosingId] = React.useState('')
  const activeRepair = useAdminOpsStore((state) => state.activeRepair)
  const clearActiveRepair = useAdminOpsStore((state) => state.clearActiveRepair)
  const openRepair = useAdminOpsStore((state) => state.openRepair)

  const load = React.useCallback(async () => {
    setLoading(true)
    try {
      const payload = await getAdminRepairs(100)
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

      <section className={`${surfaceClassName} px-5 py-5`}>
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="text-sm font-medium">{copy.newRepair}</div>
            <div className="mt-1 text-xs text-muted-foreground">{copy.subtitle}</div>
          </div>
          {activeRepair ? <Badge variant="warning">{activeRepair.repair_id}</Badge> : null}
        </div>
        <div className={`mt-5 flex gap-3 border-t ${dividerClassName} pt-5`}>
          <Input value={requestText} onChange={(event) => setRequestText(event.target.value)} placeholder={copy.requestPlaceholder} />
          <Button
            variant="secondary"
            onClick={async () => {
              const trimmed = requestText.trim()
              if (!trimmed) return
              const response = await createAdminRepair({ request_text: trimmed, source_page: '/settings/repairs', scope: 'system' })
              openRepair(response.repair)
              setRequestText('')
              await load()
            }}
          >
            {copy.create}
          </Button>
        </div>
      </section>

      <section className={`${surfaceClassName} overflow-hidden`}>
        <div className={`flex items-center justify-between gap-3 border-b ${dividerClassName} px-5 py-4`}>
          <div className="text-sm font-medium">{copy.repairSessions}</div>
          <Button variant="outline" size="sm" onClick={() => void load()} isLoading={loading}>
            {copy.refresh}
          </Button>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{copy.repair}</TableHead>
              <TableHead>{copy.status}</TableHead>
              <TableHead>{copy.scope}</TableHead>
              <TableHead>{copy.quest}</TableHead>
              <TableHead>{copy.request}</TableHead>
              <TableHead>{copy.actions}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.repair_id}>
                <TableCell className="font-medium">{item.repair_id}</TableCell>
                <TableCell>
                  <Badge variant={item.status === 'open' ? 'warning' : 'secondary'}>
                    {adminEnumLabel(item.status, locale)}
                  </Badge>
                </TableCell>
                <TableCell>{adminEnumLabel(item.scope, locale)}</TableCell>
                <TableCell>{item.ops_quest_id || '—'}</TableCell>
                <TableCell className="max-w-[520px] truncate text-xs text-soft-text-secondary">{item.user_request || ''}</TableCell>
                <TableCell>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={() => openRepair(item)}>
                      {copy.open}
                    </Button>
                    {item.status === 'open' ? (
                      <Button
                        size="sm"
                        variant="destructive"
                        isLoading={closingId === item.repair_id}
                        onClick={async () => {
                          setClosingId(item.repair_id)
                          try {
                            await closeAdminRepair(item.repair_id)
                            if (activeRepair?.repair_id === item.repair_id) {
                              clearActiveRepair()
                            }
                            await load()
                          } finally {
                            setClosingId('')
                          }
                        }}
                      >
                        {copy.close}
                      </Button>
                    ) : null}
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
