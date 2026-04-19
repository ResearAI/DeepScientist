import * as React from 'react'
import { Sparkles } from 'lucide-react'

import { QuestCopilotDockPanel } from '@/components/workspace/QuestCopilotDockPanel'
import { useQuestWorkspace } from '@/lib/acp'

function resolveSetupAgentBadge(args: {
  locale: 'en' | 'zh'
  loading: boolean
  hasLiveRun: boolean
  streaming: boolean
  activeToolCount: number
  runtimeStatus?: string | null
  hasSuggestedForm: boolean
}) {
  const { locale, loading, hasLiveRun, streaming, activeToolCount, runtimeStatus, hasSuggestedForm } = args
  const normalizedStatus = String(runtimeStatus || '').trim().toLowerCase()
  if (loading) return locale === 'zh' ? '加载中' : 'Loading'
  if (hasLiveRun || streaming || activeToolCount > 0 || normalizedStatus === 'running' || normalizedStatus === 'retrying') {
    return locale === 'zh' ? '运行中' : 'Running'
  }
  if (normalizedStatus === 'waiting_for_user' || normalizedStatus === 'waiting' || normalizedStatus === 'paused') {
    return locale === 'zh' ? '等待确认' : 'Waiting'
  }
  if (hasSuggestedForm) {
    return locale === 'zh' ? '可创建' : 'Ready'
  }
  return locale === 'zh' ? '已停驻' : 'Idle'
}

export function SetupAgentQuestPanel({
  questId,
  locale,
}: {
  questId: string
  locale: 'en' | 'zh'
}) {
  const workspace = useQuestWorkspace(questId)
  const suggestedForm =
    workspace.snapshot?.startup_contract &&
    typeof workspace.snapshot.startup_contract === 'object' &&
    !Array.isArray(workspace.snapshot.startup_contract) &&
    (workspace.snapshot.startup_contract as Record<string, unknown>).start_setup_session &&
    typeof (workspace.snapshot.startup_contract as Record<string, unknown>).start_setup_session === 'object' &&
    !Array.isArray((workspace.snapshot.startup_contract as Record<string, unknown>).start_setup_session) &&
    ((workspace.snapshot.startup_contract as Record<string, unknown>).start_setup_session as Record<string, unknown>)
      .suggested_form &&
    typeof ((workspace.snapshot.startup_contract as Record<string, unknown>).start_setup_session as Record<string, unknown>)
      .suggested_form === 'object' &&
    !Array.isArray(
      ((workspace.snapshot.startup_contract as Record<string, unknown>).start_setup_session as Record<string, unknown>)
        .suggested_form
    )
      ? (((workspace.snapshot.startup_contract as Record<string, unknown>).start_setup_session as Record<string, unknown>)
          .suggested_form as Record<string, unknown>)
      : null
  const badge = resolveSetupAgentBadge({
    locale,
    loading: workspace.loading,
    hasLiveRun: workspace.hasLiveRun,
    streaming: workspace.streaming,
    activeToolCount: workspace.activeToolCount,
    runtimeStatus: String(workspace.snapshot?.runtime_status || workspace.snapshot?.status || ''),
    hasSuggestedForm: Boolean(suggestedForm && Object.keys(suggestedForm).length > 0),
  })

  return (
    <div className="ai-manus-root ai-manus-copilot ai-manus-embedded flex h-full min-h-0 flex-col overflow-hidden rounded-[24px] border border-[var(--border-light)] bg-[var(--background-surface-strong)] shadow-[0_24px_70px_-54px_var(--shadow-M)] backdrop-blur-xl">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--border-light)] px-4 py-3">
        <div>
          <div className="text-sm font-semibold text-[var(--text-primary)]">SetupAgent</div>
          <div className="mt-1 text-xs text-[var(--text-tertiary)]">
            {locale === 'zh' ? '实时后端协助' : 'Realtime backend assist'}
          </div>
        </div>
        <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border-light)] bg-[var(--fill-tsp-white-light)] px-3 py-1 text-[11px] text-[var(--text-secondary)]">
          <Sparkles className="h-3.5 w-3.5" />
          {badge}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        <QuestCopilotDockPanel questId={questId} title="SetupAgent" workspace={workspace} />
      </div>
    </div>
  )
}

export default SetupAgentQuestPanel
