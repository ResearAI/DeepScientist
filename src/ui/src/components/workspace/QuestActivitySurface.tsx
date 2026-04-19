'use client'

import * as React from 'react'

import { SettingsAutoChartPanel } from '@/components/settings/SettingsAutoChartPanel'
import { Button } from '@/components/ui/button'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { queryAdminCharts } from '@/lib/api/admin'
import { useI18n } from '@/lib/i18n/useI18n'
import { cn } from '@/lib/utils'
import type { AdminChartPayload } from '@/lib/types/admin'
import type { QuestSummary } from '@/types'

type AnalyticsRange = '24h' | '7d'

const ANALYTICS_RANGE_OPTIONS: Array<{ value: AnalyticsRange; label: string }> = [
  { value: '24h', label: '24h' },
  { value: '7d', label: '7d' },
]

export function QuestActivitySurface({
  questId,
  snapshot,
  focusTarget,
  layout = 'document',
}: {
  questId: string
  snapshot: QuestSummary | null
  focusTarget?: string | null
  layout?: 'bounded' | 'document'
}) {
  const { language } = useI18n('workspace')
  const [analyticsRange, setAnalyticsRange] = React.useState<AnalyticsRange>('24h')
  const [overviewChart, setOverviewChart] = React.useState<AdminChartPayload | null>(null)
  const [detailCharts, setDetailCharts] = React.useState<AdminChartPayload[]>([])
  const [overviewLoading, setOverviewLoading] = React.useState(true)
  const [detailLoading, setDetailLoading] = React.useState(false)
  const [analyticsExpanded, setAnalyticsExpanded] = React.useState(Boolean(focusTarget && focusTarget !== 'activity-hourly'))
  const [highlightedFocus, setHighlightedFocus] = React.useState<string | null>(null)

  React.useEffect(() => {
    let cancelled = false

    async function loadOverviewChart() {
      setOverviewLoading(true)
      try {
        const response = await queryAdminCharts([
          { chart_id: 'quest.activity.hourly_7d', quest_id: questId, range: '7d', step_seconds: 3600 },
        ])
        if (cancelled) return
        const [nextOverviewChart] = response.items || []
        setOverviewChart(nextOverviewChart || null)
      } catch {
        if (cancelled) return
        setOverviewChart(null)
      } finally {
        if (!cancelled) setOverviewLoading(false)
      }
    }

    void loadOverviewChart()
    const timer = window.setInterval(() => {
      void loadOverviewChart()
    }, 60000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [questId])

  React.useEffect(() => {
    if (!analyticsExpanded) {
      setDetailCharts([])
      setDetailLoading(false)
      return
    }

    let cancelled = false

    async function loadDetailCharts() {
      setDetailLoading(true)
      try {
        const response = await queryAdminCharts([
          { chart_id: 'quest.activity.calls_total', quest_id: questId, range: analyticsRange },
          { chart_id: 'quest.activity.errors_total', quest_id: questId, range: analyticsRange },
          { chart_id: 'quest.tools.by_tool', quest_id: questId, range: analyticsRange, limit: 8 },
          { chart_id: 'quest.tools.by_namespace', quest_id: questId, range: analyticsRange, limit: 8 },
        ])
        if (cancelled) return
        setDetailCharts(response.items || [])
      } catch {
        if (cancelled) return
        setDetailCharts([])
      } finally {
        if (!cancelled) setDetailLoading(false)
      }
    }

    void loadDetailCharts()
    const timer = window.setInterval(() => {
      void loadDetailCharts()
    }, 60000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [analyticsExpanded, analyticsRange, questId])

  React.useEffect(() => {
    if (focusTarget && focusTarget !== 'activity-hourly') {
      setAnalyticsExpanded(true)
    }
  }, [focusTarget])

  React.useEffect(() => {
    if (!focusTarget) return
    if (focusTarget !== 'activity-hourly' && !analyticsExpanded) return
    const targetId = `quest-settings-focus-${focusTarget}`
    const timer = window.setTimeout(() => {
      const node = document.getElementById(targetId)
      if (!node) return
      node.scrollIntoView({ behavior: 'smooth', block: 'start' })
      setHighlightedFocus(focusTarget)
      window.setTimeout(() => {
        setHighlightedFocus((current) => (current === focusTarget ? null : current))
      }, 2500)
    }, 120)
    return () => window.clearTimeout(timer)
  }, [analyticsExpanded, detailCharts, focusTarget, overviewChart, questId])

  const copy = React.useMemo(
    () =>
      language === 'zh'
        ? {
            title: 'Quest 活动',
            subtitle: '先看最近是否还在推进；只有当你要解释变化时，再展开更细的原因。',
            lastTool: '最近工具',
            lastActivity: '最近活动',
            recentCounter: '自上次 artifact 交互后',
            none: '暂无',
            weekly: '最近一周每小时调用量',
            calls: '调用趋势',
            errors: '错误趋势',
            tools: '工具使用',
            namespaces: '工具分组',
            range: '时间范围',
            showDetails: '展开原因细项',
            hideDetails: '收起原因细项',
            showDetailsBody: '如果你想知道变化来自调用量、错误还是工具选择，再展开下面的细项。',
          }
        : {
            title: 'Quest Activity',
            subtitle: 'Start with whether the quest is still moving. Expand the details only when you need to explain the change.',
            lastTool: 'Last tool',
            lastActivity: 'Last activity',
            recentCounter: 'Since last artifact interact',
            none: 'N/A',
            weekly: 'Weekly Hourly Activity',
            calls: 'Calls Trend',
            errors: 'Errors Trend',
            tools: 'Tool Usage',
            namespaces: 'Tool Groups',
            range: 'Range',
            showDetails: 'Open why it changed',
            hideDetails: 'Hide why it changed',
            showDetailsBody: 'Open the detailed charts only when you need to tell whether the change came from calls, errors, or tool choice.',
          },
    [language]
  )

  const analyticsChartMap = React.useMemo(() => {
    const map = new Map<string, AdminChartPayload>()
    for (const item of detailCharts) {
      map.set(item.chart_id, item)
    }
    return map
  }, [detailCharts])

  const summaryStats = React.useMemo(
    () => ({
      lastTool: String(snapshot?.last_tool_activity_name || '').trim() || copy.none,
      lastActivity: String(snapshot?.last_tool_activity_at || '').trim() || copy.none,
      recentCounter:
        typeof snapshot?.tool_calls_since_last_artifact_interact === 'number'
          ? String(snapshot.tool_calls_since_last_artifact_interact)
          : '0',
    }),
    [copy.none, snapshot?.last_tool_activity_at, snapshot?.last_tool_activity_name, snapshot?.tool_calls_since_last_artifact_interact]
  )

  return (
    <div className={layout === 'document' ? 'space-y-5 p-4 sm:p-5' : 'feed-scrollbar h-full min-h-0 space-y-5 overflow-y-auto p-4 sm:p-5'}>
      <section className="rounded-[28px] border border-black/[0.06] bg-[rgba(255,251,246,0.76)] p-5 shadow-[0_18px_40px_-30px_rgba(18,24,32,0.24)] backdrop-blur-sm dark:border-white/[0.08] dark:bg-white/[0.03]">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <div className="text-sm font-medium text-foreground">{copy.title}</div>
            <div className="mt-1 text-sm leading-6 text-muted-foreground">{copy.subtitle}</div>
          </div>
          <Button
            type="button"
            size="sm"
            variant={analyticsExpanded ? 'secondary' : 'outline'}
            data-testid="quest-activity-toggle"
            onClick={() => setAnalyticsExpanded((current) => !current)}
          >
            {analyticsExpanded ? copy.hideDetails : copy.showDetails}
          </Button>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-3">
          <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.72] px-4 py-3 dark:border-white/[0.08] dark:bg-white/[0.04]">
            <div className="text-xs text-muted-foreground">{copy.lastTool}</div>
            <div className="mt-1 text-sm font-medium text-foreground">{summaryStats.lastTool}</div>
          </div>
          <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.72] px-4 py-3 dark:border-white/[0.08] dark:bg-white/[0.04]">
            <div className="text-xs text-muted-foreground">{copy.lastActivity}</div>
            <div className="mt-1 text-sm font-medium text-foreground">{summaryStats.lastActivity}</div>
          </div>
          <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.72] px-4 py-3 dark:border-white/[0.08] dark:bg-white/[0.04]">
            <div className="text-xs text-muted-foreground">{copy.recentCounter}</div>
            <div className="mt-1 text-sm font-medium text-foreground">{summaryStats.recentCounter}</div>
          </div>
        </div>

        <div
          id="quest-settings-focus-activity-hourly"
          data-testid="quest-activity-surface"
          className={cn(
            'mt-5 rounded-[26px] transition',
            highlightedFocus === 'activity-hourly' && 'ring-2 ring-[#C7A57A] ring-offset-2 ring-offset-transparent'
          )}
        >
          {overviewChart ? (
            <SettingsAutoChartPanel payload={overviewChart} />
          ) : (
            <div className="rounded-[28px] border border-dashed border-black/[0.08] bg-white/[0.58] px-5 py-5 text-sm text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.03]">
              {overviewLoading ? copy.weekly : copy.none}
            </div>
          )}
        </div>

        {!analyticsExpanded ? <div className="mt-4 text-sm text-soft-text-secondary">{copy.showDetailsBody}</div> : null}
      </section>

      {analyticsExpanded ? (
        <section className="space-y-4 rounded-[28px] border border-black/[0.06] bg-[rgba(255,251,246,0.76)] p-5 shadow-[0_18px_40px_-30px_rgba(18,24,32,0.24)] backdrop-blur-sm dark:border-white/[0.08] dark:bg-white/[0.03]">
          <div className="flex justify-end">
            <SegmentedControl
              value={analyticsRange}
              onValueChange={(value) => setAnalyticsRange(value)}
              items={ANALYTICS_RANGE_OPTIONS}
              size="sm"
              ariaLabel={copy.range}
            />
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <div
              id="quest-settings-focus-calls-trend"
              className={cn(
                'rounded-[26px] transition',
                highlightedFocus === 'calls-trend' && 'ring-2 ring-[#C7A57A] ring-offset-2 ring-offset-transparent'
              )}
            >
              {analyticsChartMap.get('quest.activity.calls_total') ? (
                <SettingsAutoChartPanel payload={analyticsChartMap.get('quest.activity.calls_total') as AdminChartPayload} />
              ) : (
                <div className="rounded-[28px] border border-dashed border-black/[0.08] bg-white/[0.58] px-5 py-5 text-sm text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.03]">
                  {detailLoading ? copy.calls : copy.none}
                </div>
              )}
            </div>
            <div
              id="quest-settings-focus-errors-trend"
              className={cn(
                'rounded-[26px] transition',
                highlightedFocus === 'errors-trend' && 'ring-2 ring-[#C7A57A] ring-offset-2 ring-offset-transparent'
              )}
            >
              {analyticsChartMap.get('quest.activity.errors_total') ? (
                <SettingsAutoChartPanel payload={analyticsChartMap.get('quest.activity.errors_total') as AdminChartPayload} />
              ) : (
                <div className="rounded-[28px] border border-dashed border-black/[0.08] bg-white/[0.58] px-5 py-5 text-sm text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.03]">
                  {detailLoading ? copy.errors : copy.none}
                </div>
              )}
            </div>
            <div
              id="quest-settings-focus-tools-top"
              className={cn(
                'rounded-[26px] transition',
                highlightedFocus === 'tools-top' && 'ring-2 ring-[#C7A57A] ring-offset-2 ring-offset-transparent'
              )}
            >
              {analyticsChartMap.get('quest.tools.by_tool') ? (
                <SettingsAutoChartPanel payload={analyticsChartMap.get('quest.tools.by_tool') as AdminChartPayload} />
              ) : (
                <div className="rounded-[28px] border border-dashed border-black/[0.08] bg-white/[0.58] px-5 py-5 text-sm text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.03]">
                  {detailLoading ? copy.tools : copy.none}
                </div>
              )}
            </div>
            <div
              id="quest-settings-focus-tools-namespace"
              className={cn(
                'rounded-[26px] transition',
                highlightedFocus === 'tools-namespace' && 'ring-2 ring-[#C7A57A] ring-offset-2 ring-offset-transparent'
              )}
            >
              {analyticsChartMap.get('quest.tools.by_namespace') ? (
                <SettingsAutoChartPanel payload={analyticsChartMap.get('quest.tools.by_namespace') as AdminChartPayload} />
              ) : (
                <div className="rounded-[28px] border border-dashed border-black/[0.08] bg-white/[0.58] px-5 py-5 text-sm text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.03]">
                  {detailLoading ? copy.namespaces : copy.none}
                </div>
              )}
            </div>
          </div>
        </section>
      ) : null}
    </div>
  )
}

export default QuestActivitySurface
