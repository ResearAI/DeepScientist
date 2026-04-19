import * as React from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { AdminHardwareMetricSummary, AdminHardwareRecentStats, AdminHardwareTrendPoint } from '@/lib/types/admin'
import type { Locale } from '@/types'

type ChartMetric = {
  key: keyof AdminHardwareTrendPoint
  label: string
  color: string
  summary?: AdminHardwareMetricSummary | null
}

type TrendPoint = {
  recorded_at: string
  label: string
  cpu_usage_percent?: number | null
  memory_usage_percent?: number | null
  root_disk_usage_percent?: number | null
}

const COPY = {
  en: {
    title: 'System Trajectory',
    empty: 'Recent hardware samples are not available yet.',
    sampled: 'Sampled {count} points from the last {window} minutes.',
    latest: 'Latest',
    average: 'Avg',
    peak: 'Peak',
    cpu: 'CPU',
    memory: 'Memory',
    rootDisk: 'Root Disk',
  },
  zh: {
    title: '系统轨迹',
    empty: '最近的硬件采样暂时还不可用。',
    sampled: '最近 {window} 分钟内共采样 {count} 个点。',
    latest: '当前',
    average: '平均',
    peak: '峰值',
    cpu: 'CPU',
    memory: '内存',
    rootDisk: '根分区',
  },
} satisfies Record<Locale, Record<string, string>>

function formatPercent(value: unknown) {
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return `${numeric.toFixed(numeric >= 100 ? 0 : 1)}%`
}

function formatChartTick(recordedAt: string) {
  if (!recordedAt) return ''
  const parsed = new Date(recordedAt)
  if (Number.isNaN(parsed.getTime())) return recordedAt
  return parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function interpolate(template: string, values: Record<string, string | number>) {
  return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (_match, key) => String(values[key] ?? ''))
}

export function SettingsSystemTrendChart({
  recentStats,
  locale,
  className,
}: {
  recentStats?: AdminHardwareRecentStats | null
  locale: Locale
  className?: string
}) {
  const copy = COPY[locale]
  const points = React.useMemo<TrendPoint[]>(() => {
    const raw = Array.isArray(recentStats?.series) ? recentStats?.series || [] : []
    return raw
      .filter((item): item is AdminHardwareTrendPoint => Boolean(item) && typeof item === 'object' && typeof item.recorded_at === 'string')
      .map((item) => ({
        recorded_at: item.recorded_at,
        label: formatChartTick(item.recorded_at),
        cpu_usage_percent: typeof item.cpu_usage_percent === 'number' ? item.cpu_usage_percent : null,
        memory_usage_percent: typeof item.memory_usage_percent === 'number' ? item.memory_usage_percent : null,
        root_disk_usage_percent: typeof item.root_disk_usage_percent === 'number' ? item.root_disk_usage_percent : null,
      }))
  }, [recentStats?.series])

  const metrics = React.useMemo<ChartMetric[]>(
    () => [
      {
        key: 'cpu_usage_percent',
        label: copy.cpu,
        color: '#C47A5A',
        summary: recentStats?.cpu || null,
      },
      {
        key: 'memory_usage_percent',
        label: copy.memory,
        color: '#6E9774',
        summary: recentStats?.memory || null,
      },
      {
        key: 'root_disk_usage_percent',
        label: copy.rootDisk,
        color: '#6E88B7',
        summary: recentStats?.root_disk || null,
      },
    ],
    [copy.cpu, copy.memory, copy.rootDisk, recentStats?.cpu, recentStats?.memory, recentStats?.root_disk]
  )

  if (points.length === 0) {
    return <div className={className ? className : 'text-sm text-soft-text-secondary'}>{copy.empty}</div>
  }

  return (
    <div className={className ? className : 'space-y-4'}>
      <div className="flex flex-wrap gap-2">
        {metrics.map((metric) => (
          <div
            key={String(metric.key)}
            className="rounded-2xl border border-black/8 bg-white/55 px-3 py-2 text-xs leading-5 dark:border-white/10 dark:bg-white/[0.03]"
          >
            <div className="font-medium" style={{ color: metric.color }}>
              {metric.label}
            </div>
            <div className="text-soft-text-secondary">
              {copy.latest}: {formatPercent(metric.summary?.latest_usage_percent)} · {copy.average}: {formatPercent(metric.summary?.avg_usage_percent)} · {copy.peak}:{' '}
              {formatPercent(metric.summary?.max_usage_percent)}
            </div>
          </div>
        ))}
      </div>

      <div className="h-[240px] w-full rounded-2xl border border-black/8 bg-white/45 px-3 py-3 dark:border-white/10 dark:bg-white/[0.03]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 12, right: 12, left: -10, bottom: 0 }}>
            <CartesianGrid stroke="rgba(125,125,125,0.16)" strokeDasharray="3 3" />
            <XAxis
              dataKey="label"
              minTickGap={24}
              tick={{ fill: 'rgba(78,88,98,0.88)', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              domain={[0, 100]}
              tickFormatter={(value) => `${value}%`}
              tick={{ fill: 'rgba(78,88,98,0.88)', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              width={42}
            />
            <Tooltip
              formatter={(value: number | string | null | undefined, name: string) => [formatPercent(value), name]}
              labelFormatter={(label: string, payload) => {
                const point = payload?.[0]?.payload as TrendPoint | undefined
                return point?.recorded_at || label
              }}
              contentStyle={{
                borderRadius: 16,
                border: '1px solid rgba(0,0,0,0.08)',
                background: 'rgba(255,251,246,0.96)',
                boxShadow: '0 18px 40px -24px rgba(18,24,32,0.28)',
              }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {metrics.map((metric) => (
              <Line
                key={String(metric.key)}
                type="monotone"
                dataKey={metric.key}
                name={metric.label}
                stroke={metric.color}
                strokeWidth={2.2}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="text-xs leading-5 text-soft-text-secondary">
        {interpolate(copy.sampled, {
          count: recentStats?.sample_count || points.length,
          window: recentStats?.window_minutes || points.length,
        })}
      </div>
    </div>
  )
}
