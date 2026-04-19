import * as React from 'react'

export function ChartSkeleton() {
  return (
    <div className="rounded-[28px] border border-black/[0.06] bg-white/[0.42] p-5 animate-pulse dark:border-white/[0.08] dark:bg-white/[0.03]">
      {/* 标题骨架 */}
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <div className="h-4 w-24 bg-gray-200 rounded dark:bg-gray-700" />
          <div className="h-3 w-48 bg-gray-200 rounded dark:bg-gray-700" />
        </div>
        <div className="h-6 w-16 bg-gray-200 rounded-full dark:bg-gray-700" />
      </div>

      {/* 图表骨架 */}
      <div className="mt-4 h-[280px] bg-gray-100 rounded-2xl flex items-end justify-around p-4 dark:bg-gray-800">
        {[40, 60, 45, 70, 55, 80, 50].map((height, i) => (
          <div
            key={i}
            className="w-8 bg-gray-200 rounded-t dark:bg-gray-700"
            style={{ height: `${height}%` }}
          />
        ))}
      </div>

      {/* 底部信息骨架 */}
      <div className="mt-3 flex items-center gap-3">
        <div className="h-3 w-32 bg-gray-200 rounded dark:bg-gray-700" />
        <div className="h-3 w-20 bg-gray-200 rounded dark:bg-gray-700" />
      </div>
    </div>
  )
}
