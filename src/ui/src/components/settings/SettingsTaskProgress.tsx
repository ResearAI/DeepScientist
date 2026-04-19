import { AlertCircle, CheckCircle2, Loader2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { useI18n } from '@/lib/i18n/useI18n'
import type { AdminTask } from '@/lib/types/admin'

import { adminEnumLabel, adminLocaleFromLanguage } from './settingsOpsCopy'

function statusVariant(status?: string | null): 'default' | 'secondary' | 'success' | 'warning' | 'destructive' {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'completed') return 'success'
  if (normalized === 'failed') return 'destructive'
  if (normalized === 'running') return 'warning'
  return 'secondary'
}

export function SettingsTaskProgress({
  title,
  task,
  compact = false,
}: {
  title: string
  task: AdminTask | null | undefined
  compact?: boolean
}) {
  const { language, t } = useI18n('admin')
  if (!task) return null
  const locale = adminLocaleFromLanguage(language)
  const status = String(task.status || '').trim().toLowerCase()
  const progressValue = Number(task.progress_percent || 0)
  const Icon = status === 'completed' ? CheckCircle2 : status === 'failed' ? AlertCircle : Loader2

  return (
    <Card variant="elevated" className="border-soft-border bg-soft-bg-surface/80 backdrop-blur-sm">
      <CardHeader className={compact ? 'p-4 pb-2' : 'p-5 pb-3'}>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">{title}</CardTitle>
          <Badge variant={statusVariant(status)}>{adminEnumLabel(status || 'queued', locale)}</Badge>
        </div>
      </CardHeader>
      <CardContent className={compact ? 'p-4 pt-0' : 'p-5 pt-0'}>
        <div className="flex items-center gap-2 text-sm text-soft-text-secondary">
          <Icon className={`h-4 w-4 ${status === 'running' ? 'animate-spin' : ''}`} />
          <span>{task.message || task.current_step || t('task_processing')}</span>
        </div>
        <div className="mt-3">
          <Progress value={progressValue} />
          <div className="mt-2 flex items-center justify-between text-xs text-soft-text-tertiary">
            <span>{task.current_step || t('task_queued')}</span>
            <span>
              {typeof task.progress_current === 'number' && typeof task.progress_total === 'number' && task.progress_total
                ? `${task.progress_current}/${task.progress_total}`
                : `${Math.round(progressValue)}%`}
            </span>
          </div>
        </div>
        {task.error ? <div className="mt-3 text-xs text-destructive">{task.error}</div> : null}
      </CardContent>
    </Card>
  )
}
