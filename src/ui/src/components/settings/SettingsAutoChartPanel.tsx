import * as React from 'react'
import { AlertTriangle, BarChart3, Clock3, Activity } from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { Badge } from '@/components/ui/badge'
import type { AdminBarChartPayload, AdminChartPayload, AdminLineChartPayload } from '@/lib/types/admin'

const surfaceClassName =
  'relative overflow-hidden rounded-[30px] border border-black/[0.06] bg-[linear-gradient(180deg,rgba(255,255,255,0.86),rgba(247,241,233,0.92))] px-5 py-5 shadow-[0_22px_52px_-34px_rgba(18,24,32,0.24)] backdrop-blur-sm dark:border-white/[0.08] dark:bg-[linear-gradient(180deg,rgba(255,255,255,0.06),rgba(255,255,255,0.03))]'

function formatLatest(value: number | null | undefined) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—'
  return value >= 100 ? value.toFixed(0) : value.toFixed(1)
}

function formatTimestamp(value: string) {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function buildLineRows(payload: AdminLineChartPayload) {
  const rows = new Map<string, Record<string, string | number | null>>()
  for (const series of payload.series || []) {
    for (const point of series.points || []) {
      const key = String(point.ts || '')
      if (!key) continue
      const existing = rows.get(key) || { ts: key, label: formatTimestamp(key) }
      existing[series.series_id] = typeof point.value === 'number' ? point.value : null
      rows.set(key, existing)
    }
  }
  return [...rows.values()].sort((left, right) => String(left.ts || '').localeCompare(String(right.ts || '')))
}

function lineSeriesStats(payload: AdminLineChartPayload) {
  return (payload.series || []).map((series) => {
    const values = (series.points || []).map((point) => point.value).filter((value): value is number => typeof value === 'number')
    return {
      series_id: series.series_id,
      label: series.label,
      color: series.color || '#6E88B7',
      latest: values.length ? values[values.length - 1] : null,
      peak: values.length ? Math.max(...values) : null,
    }
  })
}

function LineChartPanel({ payload }: { payload: AdminLineChartPayload }) {
  const rows = React.useMemo(() => buildLineRows(payload), [payload])
  const stats = React.useMemo(() => lineSeriesStats(payload), [payload])
  const timeBarRows = React.useMemo(
    () =>
      (payload.series?.[0]?.points || []).map((point) => ({
        ts: point.ts,
        label: formatTimestamp(point.ts),
        value: typeof point.value === 'number' ? point.value : 0,
      })),
    [payload.series]
  )
  return (
    <div className={surfaceClassName} data-testid={`auto-chart-${payload.chart_id.replace(/[^a-zA-Z0-9_-]+/g, '-')}`}>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-28 bg-[radial-gradient(circle_at_top_left,rgba(196,122,90,0.16),transparent_55%),radial-gradient(circle_at_top_right,rgba(110,136,183,0.14),transparent_48%)]" />
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-black/8 bg-white/65 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground dark:border-white/10 dark:bg-white/[0.04]">
            <Activity className="h-3.5 w-3.5" />
            {payload.range || 'live'}
          </div>
          <div className="mt-3 text-base font-semibold text-foreground">{payload.title}</div>
          {payload.description ? <div className="mt-1 text-sm leading-6 text-muted-foreground">{payload.description}</div> : null}
        </div>
        {payload.freshness?.is_stale ? (
          <Badge variant="secondary">
            <AlertTriangle className="mr-1 h-3.5 w-3.5" />
            stale
          </Badge>
        ) : null}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {stats.map((item) => (
          <div
            key={item.series_id}
            className="rounded-2xl border border-black/8 bg-white/68 px-3 py-2 text-xs dark:border-white/10 dark:bg-white/[0.03]"
          >
            <div className="font-medium" style={{ color: item.color }}>
              {item.label}
            </div>
            <div className="mt-1 text-soft-text-secondary">latest {formatLatest(item.latest)} · peak {formatLatest(item.peak)}</div>
          </div>
        ))}
      </div>
      <div className="mt-4 h-[280px]">
        <ResponsiveContainer width="100%" height="100%">
          {payload.render_hint === 'time_bar' ? (
            <BarChart data={timeBarRows} margin={{ top: 12, right: 12, left: -10, bottom: 0 }}>
              <CartesianGrid stroke="rgba(125,125,125,0.16)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" minTickGap={24} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} axisLine={false} tickLine={false} width={42} />
              <Tooltip labelFormatter={(_label, item) => String(item?.[0]?.payload?.ts || '')} />
              <Bar dataKey="value" radius={[8, 8, 0, 0]} fill={payload.series?.[0]?.color || '#6E88B7'} />
            </BarChart>
          ) : (
            <LineChart data={rows} margin={{ top: 12, right: 12, left: -10, bottom: 0 }}>
              <CartesianGrid stroke="rgba(125,125,125,0.16)" strokeDasharray="3 3" />
              <XAxis dataKey="label" minTickGap={24} axisLine={false} tickLine={false} />
              <YAxis allowDecimals axisLine={false} tickLine={false} width={42} />
              <Tooltip labelFormatter={(_label, item) => String(item?.[0]?.payload?.ts || '')} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {(payload.series || []).map((series) => (
                <Line
                  key={series.series_id}
                  type="monotone"
                  dataKey={series.series_id}
                  name={series.label}
                  stroke={series.color || '#6E88B7'}
                  strokeWidth={2.2}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-soft-text-secondary">
        {payload.freshness?.latest_recorded_at ? (
          <div className="inline-flex items-center gap-1.5">
            <Clock3 className="h-3.5 w-3.5" />
            Latest sample: {formatTimestamp(payload.freshness.latest_recorded_at)}
          </div>
        ) : null}
        {payload.freshness?.age_seconds != null ? <div>age {payload.freshness.age_seconds}s</div> : null}
      </div>
    </div>
  )
}

function BarChartPanel({ payload }: { payload: AdminBarChartPayload }) {
  const rows = payload.categories || []
  return (
    <div className={surfaceClassName} data-testid={`auto-chart-${payload.chart_id.replace(/[^a-zA-Z0-9_-]+/g, '-')}`}>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-[radial-gradient(circle_at_top_left,rgba(110,136,183,0.14),transparent_52%),radial-gradient(circle_at_top_right,rgba(94,158,160,0.12),transparent_48%)]" />
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-black/8 bg-white/65 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground dark:border-white/10 dark:bg-white/[0.04]">
            <BarChart3 className="h-3.5 w-3.5" />
            {payload.range || 'latest'}
          </div>
          <div className="mt-3 text-base font-semibold text-foreground">{payload.title}</div>
          {payload.description ? <div className="mt-1 text-sm leading-6 text-muted-foreground">{payload.description}</div> : null}
        </div>
        {payload.freshness?.is_stale ? (
          <Badge variant="secondary">
            <AlertTriangle className="mr-1 h-3.5 w-3.5" />
            stale
          </Badge>
        ) : null}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {rows.slice(0, 4).map((item) => (
          <div
            key={item.key}
            className="rounded-2xl border border-black/8 bg-white/68 px-3 py-2 text-xs dark:border-white/10 dark:bg-white/[0.03]"
          >
            <div className="font-medium text-foreground">{item.label}</div>
            <div className="mt-1 text-soft-text-secondary">{item.value}</div>
          </div>
        ))}
      </div>
      <div className="mt-4 h-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
            <CartesianGrid stroke="rgba(125,125,125,0.16)" strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" allowDecimals={false} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="label" width={100} axisLine={false} tickLine={false} />
            <Tooltip />
            <Bar dataKey="value" radius={[0, 10, 10, 0]}>
              {rows.map((item) => (
                <Cell key={item.key} fill={item.color || '#6E88B7'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-soft-text-secondary">
        {payload.freshness?.latest_recorded_at ? (
          <div className="inline-flex items-center gap-1.5">
            <Clock3 className="h-3.5 w-3.5" />
            Latest sample: {formatTimestamp(payload.freshness.latest_recorded_at)}
          </div>
        ) : null}
      </div>
    </div>
  )
}

export function SettingsAutoChartPanel({ payload }: { payload: AdminChartPayload }) {
  if (payload.kind === 'line') {
    return <LineChartPanel payload={payload} />
  }
  return <BarChartPanel payload={payload} />
}
