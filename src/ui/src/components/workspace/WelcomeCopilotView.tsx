'use client'
import * as React from 'react'
import dynamic from 'next/dynamic'
import type { AiManusChatActions, AiManusChatMeta, CopilotPrefill } from '@/lib/plugins/ai-manus/view-types'

const AiManusChatView = dynamic(() => import('@/lib/plugins/ai-manus/AiManusChatView'), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
      Loading Copilot…
    </div>
  ),
})

type WelcomeCopilotViewProps = {
  projectId: string
  readOnly?: boolean
  visible?: boolean
  prefill?: CopilotPrefill | null
  onActionsChange?: (actions: AiManusChatActions | null) => void
  onMetaChange?: (meta: AiManusChatMeta) => void
  historyPanelId?: string
  historyOpenOverride?: boolean
  onHistoryOpenChange?: (open: boolean) => void
}

export function WelcomeCopilotView({
  projectId,
  readOnly,
  visible,
  prefill,
  onActionsChange,
  onMetaChange,
  historyPanelId,
  historyOpenOverride,
  onHistoryOpenChange,
}: WelcomeCopilotViewProps) {
  return (
    <div className="welcome-copilot-view flex h-full min-h-0 min-w-0 flex-1 flex-col">
      <AiManusChatView
        mode="welcome"
        uiMode="copilot"
        projectId={projectId}
        readOnly={readOnly}
        visible={visible}
        prefill={prefill}
        deferSessionList
        embedded
        historyMode="overlay"
        hideCopilotGreeting
        historyPanelId={historyPanelId}
        historyOpenOverride={historyOpenOverride}
        onHistoryOpenChange={onHistoryOpenChange}
        onActionsChange={onActionsChange}
        onMetaChange={onMetaChange}
      />
    </div>
  )
}

export default WelcomeCopilotView
