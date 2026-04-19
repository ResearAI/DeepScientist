import { ArrowUpRight, BookOpenText, FolderOpen, Sparkles, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ConfirmModal } from '@/components/ui/modal'
import type { BaselineRegistryEntry, Locale } from '@/types'

const copy = {
  en: {
    title: 'Reusable baselines',
    hint: 'Published baselines that can be attached to quests before new work starts.',
    actionsTitle: 'Quick routes',
    actionsHint: 'Use these entry points first, then inspect or clean up concrete baseline records below.',
    attachTitle: 'Attach published baseline',
    attachBody: 'Open the start flow and choose an existing baseline before new research begins.',
    attachCta: 'Start research',
    publishTitle: 'Publish from a quest',
    publishBody: 'Open the quest table, enter a quest detail page, and publish the accepted baseline into the shared registry.',
    publishCta: 'Open quests',
    freshTitle: 'Start without baseline',
    freshBody: 'Use the same start flow when you intentionally want a fresh route instead of binding a reusable baseline.',
    freshCta: 'Open blank launch',
    empty: 'No reusable baselines have been published yet.',
    summaryFallback: 'No summary provided.',
    status: 'Status',
    sourceMode: 'Source',
    availability: 'Availability',
    sourceQuest: 'Source quest',
    variants: 'Variants',
    updatedAt: 'Updated',
    openSourceQuest: 'Open source quest',
    deleteTitle: 'Delete this baseline?',
    deleteDescription:
      'This removes the baseline from the registry, clears bound quest references, and deletes materialized copies so future agent turns cannot attach or reuse it.',
    deleteConfirm: 'Delete baseline',
    cancel: 'Cancel',
  },
  zh: {
    title: 'Baseline 列表',
    hint: '这里显示所有可复用的已发布 baseline，新建 quest 时可以直接绑定它们。',
    actionsTitle: '快捷入口',
    actionsHint: '先从这些入口卡片进入，再在下面检查或清理具体的 baseline 记录。',
    attachTitle: '绑定已发布 baseline',
    attachBody: '打开启动流程，在开始新研究之前选择一个已存在的 baseline。',
    attachCta: '开始研究',
    publishTitle: '从 quest 发布 baseline',
    publishBody: '打开 quest 列表，进入具体 quest 详情页，然后把接受后的 baseline 发布进共享 registry。',
    publishCta: '打开 quests',
    freshTitle: '无 baseline 启动',
    freshBody: '如果你有意从空白路线开始，也可以走同一个启动流程而不绑定任何复用 baseline。',
    freshCta: '打开空白启动',
    empty: '当前还没有可复用的 baseline。',
    summaryFallback: '暂无摘要。',
    status: '状态',
    sourceMode: '来源',
    availability: '可用性',
    sourceQuest: '来源 quest',
    variants: '变体数',
    updatedAt: '更新时间',
    openSourceQuest: '打开来源 quest',
    deleteTitle: '确认删除这个 baseline？',
    deleteDescription:
      '删除后会同时移除 registry 记录、清空 quest 上的绑定引用，并删除已经 materialize 到 quest/worktree 里的副本，后续 agent 轮次将不能再 attach 或复用它。',
    deleteConfirm: '删除 baseline',
    cancel: '取消',
  },
} satisfies Record<Locale, Record<string, string>>

function formatTimestamp(value: string | null | undefined) {
  const normalized = String(value || '').trim()
  if (!normalized) return '—'
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) return normalized
  return date.toLocaleString()
}

function statusVariant(status: string) {
  const normalized = status.trim().toLowerCase()
  if (normalized === 'active' || normalized === 'quest_confirmed' || normalized === 'quest_local') return 'success' as const
  if (normalized === 'missing' || normalized === 'unhealthy') return 'warning' as const
  return 'secondary' as const
}

function availabilityVariant(value: string) {
  const normalized = value.trim().toLowerCase()
  if (normalized === 'ready') return 'success' as const
  if (normalized === 'missing') return 'warning' as const
  return 'secondary' as const
}

type ActionCardProps = {
  to: string
  title: string
  body: string
  cta: string
  icon: typeof FolderOpen
}

function ActionCard({ to, title, body, cta, icon: Icon }: ActionCardProps) {
  return (
    <Link
      to={to}
      className="group rounded-[24px] border border-black/[0.08] bg-white/[0.72] p-5 transition hover:border-black/[0.16] hover:shadow-[0_18px_42px_-28px_rgba(18,24,32,0.2)] dark:border-white/[0.08] dark:bg-white/[0.03]"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex h-11 w-11 items-center justify-center rounded-[16px] border border-black/[0.08] bg-[rgba(243,236,228,0.92)] text-foreground dark:border-white/[0.08] dark:bg-white/[0.06]">
          <Icon className="h-5 w-5" />
        </div>
        <ArrowUpRight className="h-4 w-4 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
      </div>
      <div className="mt-4 text-lg font-semibold tracking-tight text-foreground">{title}</div>
      <div className="mt-2 text-sm leading-7 text-muted-foreground">{body}</div>
      <div className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-foreground">
        {cta}
        <ArrowUpRight className="h-4 w-4" />
      </div>
    </Link>
  )
}

export function BaselineSettingsPanel({
  locale,
  entries,
  deletingBaselineId,
  onDeleteBaseline,
}: {
  locale: Locale
  entries: BaselineRegistryEntry[]
  deletingBaselineId: string
  onDeleteBaseline: (baselineId: string) => Promise<void> | void
}) {
  const t = copy[locale]
  const [deleteTarget, setDeleteTarget] = useState<BaselineRegistryEntry | null>(null)
  const sortedEntries = useMemo(
    () =>
      [...entries].sort((left, right) =>
        String(right.updated_at || right.created_at || '').localeCompare(String(left.updated_at || left.created_at || ''))
      ),
    [entries]
  )

  return (
    <>
      <section className="rounded-[28px] border border-black/[0.08] bg-white/[0.5] p-5 shadow-[0_20px_70px_-50px_rgba(15,23,42,0.45)] dark:border-white/[0.08] dark:bg-white/[0.03] sm:p-6">
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-xl font-semibold tracking-tight">{t.title}</h2>
            <div className="mt-2 text-sm text-muted-foreground">{t.hint}</div>
          </div>
          <Badge variant="secondary">{sortedEntries.length}</Badge>
        </div>

        <div className="mt-6 rounded-[24px] border border-black/[0.08] bg-[linear-gradient(145deg,rgba(253,247,241,0.94),rgba(239,229,220,0.84)_42%,rgba(226,235,239,0.82))] p-5 shadow-[0_20px_56px_-44px_rgba(18,24,32,0.18)] dark:border-white/[0.08] dark:bg-white/[0.03]">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            <Sparkles className="h-4 w-4" />
            {t.actionsTitle}
          </div>
          <div className="mt-2 text-sm leading-7 text-muted-foreground">{t.actionsHint}</div>
          <div className="mt-5 grid gap-4 xl:grid-cols-3">
            <ActionCard to="/projects/new/auto" title={t.attachTitle} body={t.attachBody} cta={t.attachCta} icon={BookOpenText} />
            <ActionCard to="/settings/quests" title={t.publishTitle} body={t.publishBody} cta={t.publishCta} icon={FolderOpen} />
            <ActionCard to="/projects/new/auto" title={t.freshTitle} body={t.freshBody} cta={t.freshCta} icon={Sparkles} />
          </div>
        </div>

        {sortedEntries.length === 0 ? (
          <div className="mt-6 rounded-[22px] border border-dashed border-black/[0.08] bg-white/[0.38] px-4 py-8 text-sm text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.02]">
            {t.empty}
          </div>
        ) : (
          <div className="mt-6 grid gap-4 xl:grid-cols-2">
            {sortedEntries.map((entry) => {
              const baselineId = String(entry.baseline_id || '').trim()
              const variantCount = Array.isArray(entry.baseline_variants) ? entry.baseline_variants.length : 0
              const status = String(entry.status || 'unknown').trim() || 'unknown'
              const sourceMode = String(entry.source_mode || 'unknown').trim() || 'unknown'
              const availability = String(entry.availability || '').trim()
              const sourceQuestId = String(entry.source_quest_id || '').trim()
              return (
                <article
                  key={baselineId}
                  className="rounded-[24px] border border-black/[0.08] bg-white/[0.72] p-5 dark:border-white/[0.08] dark:bg-white/[0.03]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="break-all text-lg font-semibold tracking-tight">{baselineId}</div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Badge variant={statusVariant(status)}>{status}</Badge>
                        <Badge variant="secondary">{sourceMode}</Badge>
                        {availability ? <Badge variant={availabilityVariant(availability)}>{availability}</Badge> : null}
                      </div>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => setDeleteTarget(entry)}
                      disabled={deletingBaselineId === baselineId}
                      aria-label={t.deleteConfirm}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>

                  <p className="mt-4 text-sm leading-6 text-muted-foreground">
                    {String(entry.summary || '').trim() || t.summaryFallback}
                  </p>

                  <dl className="mt-5 space-y-3 text-sm">
                    <div className="flex items-start justify-between gap-3">
                      <dt className="text-muted-foreground">{t.status}</dt>
                      <dd className="text-right text-foreground">{status}</dd>
                    </div>
                    <div className="flex items-start justify-between gap-3">
                      <dt className="text-muted-foreground">{t.sourceMode}</dt>
                      <dd className="text-right text-foreground">{sourceMode}</dd>
                    </div>
                    <div className="flex items-start justify-between gap-3">
                      <dt className="text-muted-foreground">{t.variants}</dt>
                      <dd className="text-right text-foreground">{variantCount}</dd>
                    </div>
                    {availability ? (
                      <div className="flex items-start justify-between gap-3">
                        <dt className="text-muted-foreground">{t.availability}</dt>
                        <dd className="text-right text-foreground">{availability}</dd>
                      </div>
                    ) : null}
                    {sourceQuestId ? (
                      <div className="flex items-start justify-between gap-3">
                        <dt className="text-muted-foreground">{t.sourceQuest}</dt>
                        <dd className="break-all text-right text-foreground">{sourceQuestId}</dd>
                      </div>
                    ) : null}
                    <div className="flex items-start justify-between gap-3">
                      <dt className="text-muted-foreground">{t.updatedAt}</dt>
                      <dd className="text-right text-foreground">{formatTimestamp(entry.updated_at || entry.created_at)}</dd>
                    </div>
                  </dl>

                  {sourceQuestId ? (
                    <div className="mt-5 border-t border-black/[0.08] pt-4 dark:border-white/[0.08]">
                      <Button variant="outline" asChild>
                        <Link to={`/settings/quests/${encodeURIComponent(sourceQuestId)}`}>
                          {t.openSourceQuest}
                          <ArrowUpRight className="ml-2 h-4 w-4" />
                        </Link>
                      </Button>
                    </div>
                  ) : null}
                </article>
              )
            })}
          </div>
        )}
      </section>

      <ConfirmModal
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (!deleteTarget) return
          Promise.resolve(onDeleteBaseline(deleteTarget.baseline_id))
            .then(() => setDeleteTarget(null))
            .catch(() => undefined)
        }}
        title={t.deleteTitle}
        description={`${t.deleteDescription}${deleteTarget ? `\n\n${deleteTarget.baseline_id}` : ''}`}
        confirmText={t.deleteConfirm}
        cancelText={t.cancel}
        variant="danger"
        loading={Boolean(deleteTarget) && deletingBaselineId === deleteTarget?.baseline_id}
      />
    </>
  )
}
