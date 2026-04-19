import * as React from 'react'

import { SettingsGuideCard } from '@/components/settings/SettingsGuideCard'
import { adminEnumLabel, adminLocaleFromLanguage, pickAdminCopy } from '@/components/settings/settingsOpsCopy'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { client } from '@/lib/api'
import { useI18n } from '@/lib/i18n/useI18n'
import { useAdminOpsStore } from '@/lib/stores/admin-ops'
import type { ConnectorSnapshot } from '@/types'

const surfaceClassName =
  'rounded-[28px] border border-black/[0.06] bg-[rgba(255,251,246,0.76)] shadow-[0_18px_40px_-30px_rgba(18,24,32,0.24)] backdrop-blur-sm dark:border-white/[0.08] dark:bg-white/[0.03]'
const dividerClassName = 'border-black/[0.06] dark:border-white/[0.08]'

const PAGE_COPY = {
  en: {
    title: 'Connector Supervision',
    subtitle: 'Inspect runtime connector state, bindings, and discovered targets.',
    guide: `
### What this page is for

- Use **Connector Supervision** to inspect delivery surfaces such as QQ, Weixin, Telegram, Slack, and other configured channels.
- This page is for **runtime state**, not long-form connector documentation.

### How to read it

- **enabled** tells you whether the connector is configured to run.
- **state** tells you whether the runtime currently looks healthy.
- **bindings** tells you how many quest routes currently point at this connector.
- **targets** tells you how many delivery or conversation targets are currently visible.
- **last error** is the fastest operator clue when a connector degrades.
`,
    connectors: 'Connectors',
    refresh: 'Refresh',
    name: 'Name',
    enabled: 'Enabled',
    state: 'State',
    bindings: 'Bindings',
    targets: 'Targets',
    lastError: 'Last error',
  },
  zh: {
    title: '连接器监管',
    subtitle: '检查运行时连接器状态、绑定关系与已发现目标。',
    guide: `
### 这一页用来做什么

- 用 **连接器监管** 检查 QQ、微信、Telegram、Slack 等配置过的消息投递面。
- 这一页关注的是 **运行时状态**，不是长篇连接器文档。

### 怎么读

- **启用** 表示这个连接器当前是否被配置为运行。
- **状态** 表示运行时现在看起来是否健康。
- **绑定数** 表示当前有多少 quest 路由指向这个连接器。
- **目标数** 表示当前看见了多少投递或会话目标。
- **最近错误** 是连接器退化时最快的运维线索。
`,
    connectors: '连接器',
    refresh: '刷新',
    name: '名称',
    enabled: '启用',
    state: '状态',
    bindings: '绑定数',
    targets: '目标数',
    lastError: '最近错误',
  },
} as const

export function SettingsConnectorHealthSection() {
  const { language } = useI18n('admin')
  const locale = adminLocaleFromLanguage(language)
  const copy = pickAdminCopy(language, PAGE_COPY)
  const [items, setItems] = React.useState<ConnectorSnapshot[]>([])
  const [loading, setLoading] = React.useState(true)
  const setContext = useAdminOpsStore((state) => state.setContext)

  const load = React.useCallback(async () => {
    setLoading(true)
    try {
      setItems(await client.connectors())
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(), 10000)
    return () => window.clearInterval(timer)
  }, [load])

  return (
    <div className="space-y-5">
      <SettingsGuideCard markdown={copy.guide} />

      <section className={`${surfaceClassName} overflow-hidden`}>
        <div className={`flex items-center justify-between gap-3 border-b ${dividerClassName} px-5 py-4`}>
          <div>
            <div className="text-sm font-medium">{copy.connectors}</div>
            <div className="mt-1 text-xs text-muted-foreground">{copy.subtitle}</div>
          </div>
          <div className="flex items-center gap-3">
            <Badge variant="secondary">{items.length}</Badge>
            <Button variant="outline" size="sm" onClick={() => void load()} isLoading={loading}>
              {copy.refresh}
            </Button>
          </div>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{copy.name}</TableHead>
              <TableHead>{copy.enabled}</TableHead>
              <TableHead>{copy.state}</TableHead>
              <TableHead>{copy.bindings}</TableHead>
              <TableHead>{copy.targets}</TableHead>
              <TableHead>{copy.lastError}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow
                key={item.name}
                onMouseEnter={() =>
                  setContext({
                    sourcePage: '/settings/connectors-health',
                    scope: 'connector',
                    targets: { connectors: [item.name] },
                  })
                }
              >
                <TableCell className="font-medium">{item.name}</TableCell>
                <TableCell>
                  <Badge variant={item.enabled ? 'success' : 'secondary'}>
                    {item.enabled ? adminEnumLabel('enabled', locale) : adminEnumLabel('disabled', locale)}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge variant={item.connection_state === 'degraded' ? 'warning' : 'secondary'}>
                    {adminEnumLabel(item.connection_state || item.auth_state || 'unknown', locale)}
                  </Badge>
                </TableCell>
                <TableCell>{item.binding_count || 0}</TableCell>
                <TableCell>{item.target_count || 0}</TableCell>
                <TableCell className="max-w-[460px] truncate text-xs text-soft-text-secondary">{item.last_error || '—'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
    </div>
  )
}
