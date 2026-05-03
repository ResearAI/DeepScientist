import { ArrowLeft, ChevronRight, FileText, ListTree, Loader2, Search } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { slugifyHeading, splitFrontmatter } from '@/components/plugins/MarkdownDocument'
import { ProjectsAppBar } from '@/components/projects/ProjectsAppBar'
import type { ConfigDocumentName } from '@/components/settings/SettingsPage'
import { HintDot } from '@/components/ui/hint-dot'
import { Input } from '@/components/ui/input'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { MarkdownPreview } from './MarkdownPreview'
import { client } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { Locale, OpenDocumentPayload, QuestDocument } from '@/types'

const copy = {
  en: {
    title: 'Docs',
    repoTitle: 'Docs',
    search: 'Search',
    empty: 'No match.',
    loading: 'Loading...',
    openHint: 'Pick a file.',
    outline: 'Outline',
    openDocs: 'Docs',
    openOutline: 'Outline',
    shortcuts: 'Links',
    shortcutsHint: 'Jump to the matching settings category.',
    pathHint: 'Current file path.',
    back: 'Back',
    categories: 'Categories',
    documents: 'Documents',
    rootGroup: 'Root',
  },
  zh: {
    title: '文档',
    repoTitle: '文档',
    search: '搜索',
    empty: '没有匹配项。',
    loading: '加载中...',
    openHint: '选择一个文件。',
    outline: '目录',
    openDocs: '文档',
    openOutline: '目录',
    shortcuts: '链接',
    shortcutsHint: '跳转到对应的设置分类。',
    pathHint: '当前文件路径。',
    back: '返回',
    categories: '目录',
    documents: '文档',
    rootGroup: '根目录',
  },
} satisfies Record<Locale, Record<string, string>>

type ConfigShortcut = {
  id: string
  title: Record<Locale, string>
  configName: ConfigDocumentName
}

type HeadingEntry = {
  id: string
  text: string
  level: number
}

const DOCS_LANG_PREFIX: Record<Locale, string> = {
  en: 'en/',
  zh: 'zh/',
}

type GroupedDoc = {
  group: string
  items: Array<{
    item: QuestDocument
    depth: number
    leaf: string
    parentLabel: string
  }>
}

const CONFIG_SHORTCUTS: ConfigShortcut[] = [
  { id: 'config', title: { en: 'Runtime', zh: '运行时' }, configName: 'config' },
  { id: 'runners', title: { en: 'Models', zh: '模型' }, configName: 'runners' },
  { id: 'connectors', title: { en: 'Connectors', zh: '连接器' }, configName: 'connectors' },
  { id: 'plugins', title: { en: 'Extensions', zh: '扩展' }, configName: 'plugins' },
  { id: 'mcp_servers', title: { en: 'MCP', zh: 'MCP' }, configName: 'mcp_servers' },
]

function parseHeadings(content: string): HeadingEntry[] {
  const { body } = splitFrontmatter(content)
  const lines = body.split('\n')
  const headings: HeadingEntry[] = []
  for (const line of lines) {
    const match = /^(#{1,3})\s+(.+?)\s*$/.exec(line.trim())
    if (!match) {
      continue
    }
    const text = match[2].replace(/\s+#*$/, '').trim()
    if (!text) {
      continue
    }
    headings.push({
      id: slugifyHeading(text),
      text,
      level: match[1].length,
    })
  }
  return headings
}

function stripLangPrefix(documentId: string): string {
  for (const prefix of Object.values(DOCS_LANG_PREFIX)) {
    if (documentId.startsWith(prefix)) {
      return documentId.slice(prefix.length)
    }
  }
  return documentId
}

function resolveDocsForLocale(items: QuestDocument[], locale: Locale): { items: QuestDocument[]; prefix: string } {
  const desiredPrefix = DOCS_LANG_PREFIX[locale] ?? 'en/'
  const localized = items.filter((item) => item.document_id?.startsWith(desiredPrefix))
  if (localized.length > 0) {
    return { items: localized, prefix: desiredPrefix }
  }
  const fallbackPrefix = DOCS_LANG_PREFIX.en
  const fallback = items.filter((item) => item.document_id?.startsWith(fallbackPrefix))
  if (fallback.length > 0) {
    return { items: fallback, prefix: fallbackPrefix }
  }
  return { items, prefix: '' }
}

function pickDefaultDocId(items: QuestDocument[]): string | null {
  const preferred = items.find((item) => stripLangPrefix(item.document_id || '').endsWith('00_QUICK_START.md'))
  return preferred?.document_id ?? items[0]?.document_id ?? null
}

function toDocumentSlug(documentId: string): string {
  return documentId.replace(/\.(md|markdown|txt)$/i, '')
}

function docsPathForDocument(documentId: string): string {
  return `/docs/${toDocumentSlug(documentId)
    .split('/')
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join('/')}`
}

function findDocumentIdForSlug(items: QuestDocument[], slug?: string | null): string | null {
  const normalized = String(slug || '')
    .trim()
    .replace(/^\/+/, '')
    .replace(/\/+$/, '')
  if (!normalized) {
    return null
  }
  const match = items.find((item) => toDocumentSlug(item.document_id || '') === normalized)
  return match?.document_id ?? null
}

function resolveDocsPrefixForDocument(documentId?: string | null): string | null {
  const normalized = String(documentId || '').trim()
  if (!normalized) {
    return null
  }
  return Object.values(DOCS_LANG_PREFIX).find((prefix) => normalized.startsWith(prefix)) ?? null
}

function groupDocs(items: QuestDocument[], options?: { stripPrefix?: string }): GroupedDoc[] {
  const groups = new Map<string, GroupedDoc>()
  for (const item of items) {
    const rawId = item.document_id || item.title || 'doc'
    const raw = options?.stripPrefix && rawId.startsWith(options.stripPrefix) ? rawId.slice(options.stripPrefix.length) : rawId
    const segments = raw.split('/').filter(Boolean)
    const group = segments.length > 1 ? segments[0] : 'root'
    const depth = Math.max(segments.length - 1, 0)
    const leaf = segments[segments.length - 1] || raw
    const parentLabel = segments.length > 2 ? segments.slice(1, -1).join(' / ') : segments.length > 1 ? segments[0] : ''
    const groupEntry = groups.get(group) || { group, items: [] }
    groupEntry.items.push({ item, depth, leaf, parentLabel })
    groups.set(group, groupEntry)
  }
  return Array.from(groups.values())
    .map((group) => ({
      ...group,
      items: group.items.sort((left, right) => left.item.document_id.localeCompare(right.item.document_id)),
    }))
    .sort((left, right) => left.group.localeCompare(right.group))
}

export function DocsPage({
  locale,
  requestedDocumentSlug = null,
  onOpenSettings,
}: {
  locale: Locale
  requestedDocumentSlug?: string | null
  onOpenSettings: (name?: ConfigDocumentName, hash?: string) => void
}) {
  const t = copy[locale]
  const navigate = useNavigate()
  const [docs, setDocs] = useState<QuestDocument[]>([])
  const [docsPrefix, setDocsPrefix] = useState('')
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [active, setActive] = useState<OpenDocumentPayload | null>(null)
  const [mobileDocsView, setMobileDocsView] = useState<'directory' | 'document'>(
    requestedDocumentSlug ? 'document' : 'directory'
  )
  const [opening, setOpening] = useState(false)
  const [headings, setHeadings] = useState<HeadingEntry[]>([])
  const [activeHeadingId, setActiveHeadingId] = useState<string>('')
  const [outlineOpen, setOutlineOpen] = useState(false)
  const scrollRootRef = useRef<HTMLElement | null>(null)
  const articleRef = useRef<HTMLDivElement | null>(null)
  const outlineRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    setMobileDocsView(requestedDocumentSlug ? 'document' : 'directory')
  }, [requestedDocumentSlug])

  useEffect(() => {
    let mounted = true
    const run = async () => {
      setLoading(true)
      try {
        const payload = await client.docsIndex()
        if (!mounted) {
          return
        }
        const requestedDocId = findDocumentIdForSlug(payload, requestedDocumentSlug)
        const requestedPrefix = resolveDocsPrefixForDocument(requestedDocId)
        const localized = requestedPrefix
          ? {
              items: payload.filter((item) => item.document_id?.startsWith(requestedPrefix)),
              prefix: requestedPrefix,
            }
          : resolveDocsForLocale(payload, locale)
        const nextDocs = localized.items
        setDocsPrefix(localized.prefix)
        setDocs(nextDocs)
        const previousActiveId = active?.document_id || null
        const nextCandidateId = previousActiveId
          ? `${localized.prefix}${stripLangPrefix(previousActiveId)}`
          : null
        const firstId =
          (requestedDocId && nextDocs.some((item) => item.document_id === requestedDocId) ? requestedDocId : null) ??
          (nextCandidateId && nextDocs.some((item) => item.document_id === nextCandidateId) ? nextCandidateId : null) ??
          pickDefaultDocId(nextDocs)
        if (firstId) {
          setOpening(true)
          const first = await client.openSystemDoc(firstId)
          if (!mounted) {
            return
          }
          setActive(first)
          setHeadings(parseHeadings(first.content))
        }
      } finally {
        if (mounted) {
          setOpening(false)
          setLoading(false)
        }
      }
    }
    void run()
    return () => {
      mounted = false
    }
  }, [locale, requestedDocumentSlug])

  useEffect(() => {
    const article = articleRef.current
    const scrollRoot = scrollRootRef.current
    if (!article || !scrollRoot) {
      return
    }
    const nodes = Array.from(article.querySelectorAll<HTMLElement>('h1[id], h2[id], h3[id]'))
    if (nodes.length === 0) {
      setActiveHeadingId('')
      return
    }
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => left.boundingClientRect.top - right.boundingClientRect.top)[0]
        if (visible?.target instanceof HTMLElement) {
          setActiveHeadingId(visible.target.id)
        }
      },
      {
        root: scrollRoot,
        threshold: 0.4,
        rootMargin: '0px 0px -55% 0px',
      }
    )
    nodes.forEach((node) => observer.observe(node))
    return () => observer.disconnect()
  }, [active])

  useEffect(() => {
    const outline = outlineRef.current
    if (!outline || !activeHeadingId) {
      return
    }
    const activeItem = outline.querySelector<HTMLElement>(`[data-heading-id="${CSS.escape(activeHeadingId)}"]`)
    activeItem?.scrollIntoView({ block: 'nearest' })
  }, [activeHeadingId])

  const mobileGroupedDocs = useMemo(() => groupDocs(docs, { stripPrefix: docsPrefix }), [docs, docsPrefix])

  const groupedDocs = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    if (!keyword) {
      return mobileGroupedDocs
    }
    return groupDocs(
      docs.filter((item) =>
        `${item.title} ${item.document_id} ${item.path || ''}`.toLowerCase().includes(keyword)
      ),
      { stripPrefix: docsPrefix }
    )
  }, [docs, docsPrefix, mobileGroupedDocs, search])

  const handleOpenDocument = async (documentId: string) => {
    setOpening(true)
    try {
      const payload = await client.openSystemDoc(documentId)
      setActive(payload)
      setHeadings(parseHeadings(payload.content))
    } finally {
      setOpening(false)
    }
  }

  const handleOpenMobileDocument = (documentId: string) => {
    setMobileDocsView('document')
    setOutlineOpen(false)
    navigate(docsPathForDocument(documentId))
    void handleOpenDocument(documentId)
  }

  const handleBackToMobileDocsDirectory = () => {
    setMobileDocsView('directory')
    setOutlineOpen(false)
    navigate('/docs')
  }

  const jumpToHeading = (id: string) => {
    const article = articleRef.current
    const scrollRoot = scrollRootRef.current
    const target = article?.querySelector<HTMLElement>(`#${CSS.escape(id)}`)
    if (!article || !scrollRoot || !target) {
      return
    }
    const top =
      scrollRoot.scrollTop +
      target.getBoundingClientRect().top -
      scrollRoot.getBoundingClientRect().top -
      20
    scrollRoot.scrollTop = Math.max(top, 0)
    setActiveHeadingId(id)
    setOutlineOpen(false)
  }

  const formatDocGroupLabel = (group: string) => (group === 'root' ? t.rootGroup : group)

  const mobileDocsTree = (
    <>
      <div className="feed-scrollbar mt-5 min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t.loading}
          </div>
        ) : mobileGroupedDocs.length === 0 ? (
          <div className="text-sm text-muted-foreground">{t.empty}</div>
        ) : (
          mobileGroupedDocs.map((group) => (
            <section
              key={group.group}
              className="rounded-[18px] border border-black/[0.08] bg-white/[0.42] p-3 dark:border-white/[0.10] dark:bg-white/[0.04]"
            >
              <div className="mb-2 flex items-center justify-between gap-3">
                <div className="min-w-0 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  {formatDocGroupLabel(group.group)}
                </div>
                <div className="shrink-0 rounded-full bg-black/[0.04] px-2.5 py-1 text-[11px] text-muted-foreground dark:bg-white/[0.06]">
                  {group.items.length} {t.documents}
                </div>
              </div>
              <div className="space-y-1">
                {group.items.map(({ item, depth, leaf, parentLabel }) => (
                  <button
                    key={item.document_id}
                    type="button"
                    data-onboarding-id="docs-mobile-document-button"
                    onClick={() => handleOpenMobileDocument(item.document_id)}
                    className={cn(
                      'flex w-full items-start gap-2 rounded-[14px] px-2.5 py-2.5 text-left transition hover:bg-black/[0.03] dark:hover:bg-white/[0.04]',
                      active?.document_id === item.document_id && 'bg-black/[0.05] dark:bg-white/[0.06]'
                    )}
                    style={{ paddingLeft: `${10 + depth * 10}px` }}
                  >
                    <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0">
                      <div className="line-clamp-2 break-words text-sm">{item.title || leaf}</div>
                      {parentLabel ? <div className="mt-0.5 line-clamp-2 break-words text-[11px] text-muted-foreground">{parentLabel}</div> : null}
                    </div>
                  </button>
                ))}
              </div>
            </section>
          ))
        )}
      </div>
    </>
  )

  const docsTree = (
    <>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t.search} className="rounded-[18px] border-black/[0.08] bg-white/[0.44] pl-10 shadow-none dark:bg-white/[0.03]" />
      </div>

      <div className="mt-5">
        <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          <span>{t.shortcuts}</span>
          <HintDot label={t.shortcutsHint} />
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-2">
          {CONFIG_SHORTCUTS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onOpenSettings(item.configName)}
              className="text-xs text-muted-foreground transition hover:text-foreground"
            >
              {item.title[locale]}
            </button>
          ))}
        </div>
      </div>

      <div className="feed-scrollbar mt-6 min-h-0 flex-1 space-y-5 overflow-auto pr-1">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t.loading}
          </div>
        ) : groupedDocs.length === 0 ? (
          <div className="text-sm text-muted-foreground">{t.empty}</div>
        ) : (
          groupedDocs.map((group) => (
            <div key={group.group}>
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{group.group}</div>
              <div className="space-y-0.5">
                {group.items.map(({ item, depth, leaf, parentLabel }) => (
                  <button
                    key={item.document_id}
                    type="button"
                    onClick={() => void handleOpenDocument(item.document_id)}
                    className={cn(
                      'flex w-full items-start gap-2 rounded-[14px] px-2.5 py-2 text-left transition hover:bg-black/[0.03] dark:hover:bg-white/[0.04]',
                      active?.document_id === item.document_id && 'bg-black/[0.05] dark:bg-white/[0.06]'
                    )}
                    style={{ paddingLeft: `${10 + depth * 10}px` }}
                  >
                    <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0">
                      <div className="truncate text-sm">{item.title || leaf}</div>
                      {parentLabel ? <div className="truncate text-[11px] text-muted-foreground">{parentLabel}</div> : null}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </>
  )

  const outlineTree = (
    <div ref={outlineRef} className="feed-scrollbar min-h-0 space-y-1 overflow-auto pr-1 xl:max-h-[calc(100vh-14rem)]">
      {headings.length === 0 ? (
        <div className="text-sm text-muted-foreground">{t.empty}</div>
      ) : (
        headings.map((heading) => (
          <button
            key={heading.id}
            type="button"
            data-heading-id={heading.id}
            onClick={() => jumpToHeading(heading.id)}
            className={cn(
              'flex w-full items-center gap-2 rounded-[14px] px-2.5 py-2 text-left text-sm transition hover:bg-black/[0.03] dark:hover:bg-white/[0.04]',
              heading.level === 2 && 'pl-4',
              heading.level === 3 && 'pl-6 text-muted-foreground',
              activeHeadingId === heading.id && 'bg-black/[0.05] dark:bg-white/[0.06]'
            )}
          >
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <span className="line-clamp-2">{heading.text}</span>
          </button>
        ))
      )}
    </div>
  )

  return (
    <div className="font-project flex h-screen flex-col overflow-hidden px-4 pb-4 pt-4 sm:px-6 sm:pb-6">
      <ProjectsAppBar title={t.title} />

      <main className="mx-auto mt-6 min-h-0 w-full flex-1 overflow-hidden">
        <div
          className={cn(
            'mx-auto grid h-full min-h-0 w-full max-w-[94vw] gap-0 sm:max-w-[90vw] xl:grid-cols-[260px_minmax(0,1fr)_220px] xl:grid-rows-1',
            mobileDocsView === 'document' ? 'grid-rows-[auto_minmax(0,1fr)]' : 'grid-rows-[minmax(0,1fr)]'
          )}
        >
          {mobileDocsView === 'document' ? (
            <div className="mb-3 flex shrink-0 items-center justify-between gap-2 xl:hidden">
              <button
                type="button"
                onClick={handleBackToMobileDocsDirectory}
                data-onboarding-id="docs-mobile-back"
                className="inline-flex h-10 items-center gap-2 rounded-[16px] border border-black/[0.08] bg-white/[0.58] px-3 text-sm font-medium text-foreground shadow-[0_12px_28px_-24px_rgba(45,42,38,0.26)] backdrop-blur-xl dark:border-white/[0.10] dark:bg-white/[0.05]"
              >
                <ArrowLeft className="h-4 w-4" />
                <span>{t.back}</span>
              </button>
              <button
                type="button"
                onClick={() => setOutlineOpen(true)}
                data-onboarding-id="docs-mobile-outline-button"
                className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-[16px] border border-black/[0.08] bg-white/[0.58] text-muted-foreground shadow-[0_12px_28px_-24px_rgba(45,42,38,0.26)] backdrop-blur-xl dark:border-white/[0.10] dark:bg-white/[0.05]"
                aria-label={t.openOutline}
              >
                <ListTree className="h-4 w-4" />
              </button>
            </div>
          ) : null}
          <aside
            data-onboarding-id="docs-mobile-directory"
            className={cn(
              'min-h-0 flex-col border-b border-black/[0.08] pb-6 xl:hidden dark:border-white/[0.08]',
              mobileDocsView === 'directory' ? 'flex' : 'hidden'
            )}
          >
            <div className="flex items-center gap-2 text-sm font-medium">
              <span>{t.repoTitle}</span>
              <HintDot label={`${docs.length} files`} />
            </div>
            {mobileDocsTree}
          </aside>

          <aside className="hidden min-h-0 flex-col border-b border-black/[0.08] pb-6 xl:flex xl:border-b-0 xl:border-r xl:pb-0 xl:pr-6 dark:border-white/[0.08]">
            <div className="flex items-center gap-2 text-sm font-medium">
              <span>{t.repoTitle}</span>
              <HintDot label={`${docs.length} files`} />
            </div>
            {docsTree}
          </aside>

          <section
            ref={scrollRootRef}
            className={cn(
              'feed-scrollbar min-h-0 overflow-y-auto py-6 xl:flex xl:flex-col xl:px-10',
              mobileDocsView === 'document' ? 'block' : 'hidden'
            )}
          >
            {active ? (
              <>
                <div className="border-b border-black/[0.08] pb-5 dark:border-white/[0.08]">
                  <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                    <span>{t.title}</span>
                    {opening ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                  </div>
                  <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">{active.title}</h1>
                  {active.path ? (
                    <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
                      <span className="break-all">{active.path}</span>
                      <HintDot label={t.pathHint} />
                    </div>
                  ) : null}
                </div>

                <div ref={articleRef} className="min-h-0 py-6">
                  <MarkdownPreview
                    content={splitFrontmatter(active.content).body || ''}
                    baseFilePath={active.document_id}
                    className="markdown-body ds-docs-markdown overflow-visible rounded-none bg-transparent px-0 py-0"
                  />
                </div>
              </>
            ) : (
              <div className="py-16 text-sm text-muted-foreground">{t.openHint}</div>
            )}
          </section>

          <aside className="feed-scrollbar hidden min-h-0 overflow-auto border-l border-black/[0.08] py-6 pl-6 xl:block dark:border-white/[0.08]">
            <div className="xl:sticky xl:top-6 xl:max-h-[calc(100vh-11rem)] xl:min-h-0 xl:overflow-hidden">
              <div className="mb-4 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.outline}</div>
              {outlineTree}
            </div>
          </aside>
        </div>
      </main>
      <Sheet open={outlineOpen} onOpenChange={setOutlineOpen} modal={false}>
        <SheetContent side="bottom" data-onboarding-id="docs-mobile-outline-sheet" className="h-[70svh] rounded-t-[28px] border-black/[0.08] bg-[rgba(250,247,243,0.98)] p-4 shadow-[0_-24px_64px_-36px_rgba(45,42,38,0.38)] xl:hidden">
          <SheetHeader className="shrink-0 pb-3 pr-8">
            <SheetTitle>{t.openOutline}</SheetTitle>
          </SheetHeader>
          <div className="min-h-0 flex-1 overflow-hidden">
            {outlineTree}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}
