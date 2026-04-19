import { FolderOpen, Loader2, Search, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { OverlayDialog } from '@/components/home/OverlayDialog'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { ConfirmModal } from '@/components/ui/modal'
import { useI18n } from '@/lib/i18n'
import { filterProjectsVisibleQuests } from '@/lib/questVisibility'
import { resolveProjectDisplay, resolveProjectTemplate } from '@/lib/projectDisplayCatalog'
import { runtimeHomePath } from '@/lib/runtime/quest-runtime'
import type { QuestSummary } from '@/types'

function formatTime(value?: string, locale?: string) {
  if (!value) {
    return '...'
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat(locale === 'zh' ? 'zh-CN' : 'en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed)
}

export function OpenQuestDialog({
  open,
  quests,
  loading,
  error,
  onClose,
  onOpenQuest,
  onDeleteQuest,
  deletingQuestId,
}: {
  open: boolean
  quests: QuestSummary[]
  loading: boolean
  error?: string | null
  onClose: () => void
  onOpenQuest: (questId: string) => void
  onDeleteQuest: (questId: string) => Promise<void> | void
  deletingQuestId?: string | null
}) {
  const { locale, t } = useI18n()
  const [search, setSearch] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmQuest, setConfirmQuest] = useState<QuestSummary | null>(null)
  const activeRuntimeHome = useMemo(() => runtimeHomePath(), [])
  const visibleQuests = useMemo(() => filterProjectsVisibleQuests(quests), [quests])

  useEffect(() => {
    if (!open) {
      setSearch('')
      setConfirmOpen(false)
      setConfirmQuest(null)
    }
  }, [open])

  const filteredQuests = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    if (!keyword) {
      return visibleQuests
    }
    return visibleQuests.filter((quest) =>
      `${quest.title} ${quest.quest_id} ${quest.branch || ''} ${quest.summary?.status_line || ''}`
        .toLowerCase()
        .includes(keyword)
    )
  }, [visibleQuests, search])
  const emptyBecauseNoProjects = filteredQuests.length === 0 && visibleQuests.length === 0 && !search.trim()

  return (
    <OverlayDialog
      open={open}
      title={t('openQuestTitle')}
      description={t('openQuestBody')}
      onClose={onClose}
      className="h-[min(92vh,760px)] max-w-4xl"
    >
      <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-0 md:grid-cols-[280px_minmax(0,1fr)] md:grid-rows-1">
        <aside className="feed-scrollbar min-h-0 overflow-auto border-b border-black/[0.06] px-5 py-5 dark:border-[rgba(45,42,38,0.08)] md:border-b-0 md:border-r">
          <div className="mb-4 flex items-center gap-2 text-sm font-semibold">
            <FolderOpen className="h-4 w-4 text-muted-foreground" />
            {t('openQuestTitle')}
          </div>

          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t('openQuestSearchPlaceholder')}
              className="pl-10"
            />
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <Badge>{t('landingQuestCount')}: {visibleQuests.length}</Badge>
            {visibleQuests[0]?.updated_at ? <Badge>{t('openQuestLatest')}: {formatTime(visibleQuests[0].updated_at, locale)}</Badge> : null}
          </div>
        </aside>

        <div className="feed-scrollbar min-h-0 overflow-y-auto px-4 py-4 sm:px-5">
          {loading ? (
            <div className="flex min-h-[420px] items-center justify-center gap-3 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t('loading')}
            </div>
          ) : error ? (
            <div className="rounded-[24px] border border-rose-500/20 bg-rose-500/8 px-4 py-4 text-sm text-rose-700 dark:text-rose-300">
              {error}
            </div>
          ) : filteredQuests.length === 0 ? (
            <div className="flex min-h-[420px] items-center justify-center">
              <div className="w-full max-w-xl rounded-[26px] border border-dashed border-black/[0.10] bg-white/[0.52] px-6 py-6 text-center dark:border-white/[0.12]">
                <div className="text-sm font-medium text-[rgba(38,36,33,0.92)]">
                  {emptyBecauseNoProjects ? t('openQuestNoProjects') : t('openQuestEmpty')}
                </div>
                {emptyBecauseNoProjects ? (
                  <div className="mt-4 space-y-3 text-sm text-muted-foreground">
                    {activeRuntimeHome ? (
                      <div className="space-y-1">
                        <div>{t('openQuestCurrentHome')}</div>
                        <code className="inline-block rounded-xl bg-black/[0.04] px-3 py-2 font-mono text-[12px] text-[rgba(38,36,33,0.88)]">
                          <span className="break-all">{activeRuntimeHome}</span>
                        </code>
                      </div>
                    ) : null}
                    <div>{t('openQuestHomeHint')}</div>
                  </div>
                ) : null}
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {filteredQuests.map((quest) => {
                const pendingCount = quest.pending_decisions?.length ?? quest.counts?.pending_decision_count ?? 0
                const isDeleting = Boolean(deletingQuestId && deletingQuestId === quest.quest_id)
                const settings = quest.settings && typeof quest.settings === 'object' ? quest.settings : {}
                const display = resolveProjectDisplay(
                  settings && typeof settings === 'object' && 'project_display' in settings
                    ? { project_display: (settings as Record<string, unknown>).project_display as Record<string, unknown> | null }
                    : null
                )
                const templateMeta = resolveProjectTemplate(display.template)
                return (
                  <div key={quest.quest_id} className="group relative">
                    <button
                      type="button"
                      onClick={() => onOpenQuest(quest.quest_id)}
                      className="home-card w-full rounded-[28px] px-5 py-4 text-left"
                      disabled={isDeleting}
                    >
                      <div className="relative z-[1]">
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                          <div className="min-w-0">
                            <div className="truncate text-base font-semibold tracking-tight text-black dark:text-black">
                              {quest.title || quest.quest_id}
                            </div>
                            <div className="mt-1 truncate text-sm text-muted-foreground">
                              {quest.summary?.status_line || t('openQuestNoDescription')}
                            </div>
                          </div>
                          <div className="shrink-0 text-xs text-muted-foreground">
                            {t('openQuestUpdated')}: {formatTime(quest.updated_at, locale)}
                          </div>
                        </div>

                        <div className="mt-3 flex flex-wrap gap-2">
                          <Badge>{quest.quest_id}</Badge>
                          <Badge>{templateMeta.label}</Badge>
                          {quest.branch ? <Badge>{t('openQuestBranch')}: {quest.branch}</Badge> : null}
                          {pendingCount > 0 ? <Badge>{t('openQuestPending')}: {pendingCount}</Badge> : null}
                        </div>

                        <div className="mt-4 inline-flex rounded-full border border-black/[0.08] bg-white/[0.72] px-3 py-1.5 text-xs font-medium text-[rgba(38,36,33,0.9)] dark:border-black/[0.08] dark:bg-white/[0.78] dark:text-[rgba(38,36,33,0.9)]">
                          {t('landingOpen')}
                        </div>
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation()
                        setConfirmQuest(quest)
                        setConfirmOpen(true)
                      }}
                      disabled={isDeleting}
                      aria-label={t('openQuestDelete')}
                      title={t('openQuestDelete')}
                      className="absolute right-4 top-4 z-10 flex h-8 w-8 items-center justify-center rounded-full border border-black/10 bg-white/80 text-muted-foreground opacity-0 shadow-sm backdrop-blur-md transition-all group-hover:opacity-100 hover:border-black/20 hover:text-foreground disabled:pointer-events-none disabled:opacity-40 dark:border-white/10 dark:bg-black/30 dark:hover:border-white/20"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      <ConfirmModal
        open={confirmOpen}
        onClose={() => {
          if (deletingQuestId) return
          setConfirmOpen(false)
        }}
        onConfirm={() => {
          if (!confirmQuest) return
          void Promise.resolve(onDeleteQuest(confirmQuest.quest_id)).finally(() => {
            setConfirmOpen(false)
            setConfirmQuest(null)
          })
        }}
        loading={Boolean(confirmQuest && deletingQuestId === confirmQuest.quest_id)}
        title={t('openQuestDeleteTitle')}
        description={`${t('openQuestDeleteBody')}\n\n${confirmQuest ? `${confirmQuest.title || confirmQuest.quest_id} · ${confirmQuest.quest_id}` : ''}`}
        confirmText={t('openQuestDeleteConfirm')}
        cancelText={t('openQuestDeleteCancel')}
        variant="danger"
      />
    </OverlayDialog>
  )
}
