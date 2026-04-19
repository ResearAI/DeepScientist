import * as React from 'react'

import { SettingsGuideCard } from '@/components/settings/SettingsGuideCard'
import { pickAdminCopy } from '@/components/settings/settingsOpsCopy'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { getAdminSearch } from '@/lib/api/admin'
import { useI18n } from '@/lib/i18n/useI18n'

const surfaceClassName =
  'rounded-[28px] border border-black/[0.06] bg-[rgba(255,251,246,0.76)] shadow-[0_18px_40px_-30px_rgba(18,24,32,0.24)] backdrop-blur-sm dark:border-white/[0.08] dark:bg-white/[0.03]'
const dividerClassName = 'border-black/[0.06] dark:border-white/[0.08]'

const PAGE_COPY = {
  en: {
    title: 'Cross-Quest Search',
    subtitle: 'Search across quest summaries and recent event summaries.',
    guide: `
### What this page is for

- Use **Cross-Quest Search** when you know a term, quest id, or event summary and need to find it quickly.
- Search is intentionally bounded to admin-visible summary surfaces.

### Good queries

- quest ids
- branch or runner names
- failure phrases
- short incident summaries
`,
    search: 'Search',
    placeholder: 'Search quests, recent event summaries, and admin-visible surfaces',
    kind: 'Kind',
    quest: 'Quest',
    summary: 'Summary',
    noResults: 'No results yet.',
  },
  zh: {
    title: '跨 Quest 搜索',
    subtitle: '在 quest 摘要与最近事件摘要之间做搜索。',
    guide: `
### 这一页用来做什么

- 当你已经知道一个术语、quest id 或事件摘要，并且想快速定位时，用 **跨 Quest 搜索**。
- 搜索范围刻意限制在 admin 可见的摘要面。

### 好的查询方式

- quest id
- 分支或 runner 名称
- 失败相关短语
- 简短事故摘要
`,
    search: '搜索',
    placeholder: '搜索 quests、最近事件摘要和 admin 可见面',
    kind: '类型',
    quest: 'Quest',
    summary: '摘要',
    noResults: '当前还没有结果。',
  },
} as const

export function SettingsSearchSection() {
  const { language } = useI18n('admin')
  const copy = pickAdminCopy(language, PAGE_COPY)
  const [query, setQuery] = React.useState('')
  const [items, setItems] = React.useState<Array<Record<string, unknown>>>([])
  const [loading, setLoading] = React.useState(false)

  const runSearch = React.useCallback(async () => {
    const trimmed = query.trim()
    if (!trimmed) return
    setLoading(true)
    try {
      const payload = await getAdminSearch(trimmed, 200)
      setItems(payload.items || [])
    } finally {
      setLoading(false)
    }
  }, [query])

  return (
    <div className="space-y-5">
      <SettingsGuideCard markdown={copy.guide} />

      <section className={`${surfaceClassName} overflow-hidden`}>
        <div className={`flex flex-col gap-4 border-b ${dividerClassName} px-5 py-4 xl:flex-row xl:items-center xl:justify-between`}>
          <div>
            <div className="text-sm font-medium">{copy.title}</div>
            <div className="mt-1 text-xs text-muted-foreground">{copy.subtitle}</div>
          </div>
          <div className="flex gap-3">
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  void runSearch()
                }
              }}
              placeholder={copy.placeholder}
              className="min-w-[320px]"
            />
            <Button variant="secondary" onClick={() => void runSearch()} isLoading={loading}>
              {copy.search}
            </Button>
          </div>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{copy.kind}</TableHead>
              <TableHead>{copy.quest}</TableHead>
              <TableHead>{copy.summary}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.length > 0 ? (
              items.map((item, index) => (
                <TableRow key={`${String(item.kind || 'item')}-${index}`}>
                  <TableCell>{String(item.kind || '')}</TableCell>
                  <TableCell>{String(item.quest_id || '—')}</TableCell>
                  <TableCell className="max-w-[920px] truncate text-xs text-soft-text-secondary">{String(item.summary || item.title || '')}</TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={3} className="py-8 text-center text-sm text-soft-text-secondary">
                  {copy.noResults}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </section>
    </div>
  )
}
