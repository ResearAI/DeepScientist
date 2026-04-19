import * as React from 'react'
import { ArrowUpRight, Sparkles } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import type { BenchSetupPacket } from '@/lib/types/benchstore'

type SetupAgentRailProps = {
  locale: 'en' | 'zh'
  setupPacket?: BenchSetupPacket | null
  loading?: boolean
  error?: string | null
  assistantLabel?: string | null
  onStartAssist: (message: string) => Promise<void> | void
}

function copy(locale: 'en' | 'zh') {
  return locale === 'zh'
    ? {
        title: 'SetupAgent',
        intro:
          '你可以直接填写左侧表单并启动。如果你想让我帮你整理，也可以直接告诉我任务目标、现有材料和限制，我会启动真实后端助手来补齐表单。',
        benchmarkIntro:
          '这个 benchmark 已经带来了一版草案。你可以直接启动后端 SetupAgent，让它结合当前设备、安装路径和任务信息继续帮你补齐表单。',
        placeholder:
          '请帮我找一个适合本机的 LLM 方向的任务',
        cta: '启动协助',
        note: '启动后，右侧会切换成真实的实时 copilot；它会直接把建议写回左侧表单。',
      }
    : {
        title: 'SetupAgent',
        intro:
          'You can fill the form on the left and launch directly. If you want help, tell me the goal, the materials you already have, and the main limits, and I will start a real backend assistant to complete the form.',
        benchmarkIntro:
          'This benchmark already comes with a draft. You can start the backend SetupAgent to keep refining the form from the benchmark, the device, and the local install path.',
        placeholder:
          'Please help me find an LLM-oriented task that fits this machine.',
        cta: 'Start Assist',
        note: 'Once started, the right side switches into a realtime copilot and writes suggestions back into the left form.',
      }
}

export function SetupAgentRail(props: SetupAgentRailProps) {
  const t = copy(props.locale)
  const [input, setInput] = React.useState('')

  const handleStart = React.useCallback(async () => {
    const fallback =
      props.locale === 'zh'
        ? '请根据当前启动表单内容，帮我整理并补齐最关键的启动信息。'
        : 'Please use the current start form and help me complete the most important launch details.'
    await props.onStartAssist(input.trim() || fallback)
  }, [input, props])

  return (
    <div className="ai-manus-root ai-manus-copilot ai-manus-embedded flex h-full min-h-0 flex-col overflow-hidden rounded-[24px] border border-[var(--border-light)] bg-[var(--background-surface-strong)] shadow-[0_24px_70px_-54px_var(--shadow-M)] backdrop-blur-xl">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--border-light)] px-4 py-3">
        <div>
          <div className="text-sm font-semibold text-[var(--text-primary)]">{t.title}</div>
          <div className="mt-1 text-xs text-[var(--text-tertiary)]">
            {props.setupPacket?.assistant_label || props.assistantLabel || t.title}
          </div>
        </div>
        <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border-light)] bg-[var(--fill-tsp-white-light)] px-3 py-1 text-[11px] text-[var(--text-secondary)]">
          <Sparkles className="h-3.5 w-3.5" />
          {props.locale === 'zh' ? '待命中' : 'Standby'}
        </div>
      </div>

      <div className="feed-scrollbar modal-scrollbar min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div className="space-y-4 pr-1">
          <div className="rounded-[18px] border border-[var(--border-light)] bg-[var(--fill-tsp-white-light)] px-4 py-3 text-sm leading-7 text-[var(--text-primary)]">
            {props.setupPacket ? t.benchmarkIntro : t.intro}
          </div>
        </div>
      </div>

      <div className="shrink-0 border-t border-[var(--border-light)] px-4 py-4">
        <div className="space-y-3">
          <Textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={t.placeholder}
            className="min-h-[140px] rounded-[16px] border-[var(--border-light)] bg-white/72 text-sm leading-6 text-[var(--text-primary)]"
          />
          <div className="text-xs text-[var(--text-tertiary)]">{t.note}</div>
          {props.error ? <div className="text-sm text-[var(--function-error)]">{props.error}</div> : null}
        </div>
        <div className="mt-3 flex justify-end">
          <Button onClick={() => void handleStart()} isLoading={props.loading} className="rounded-full">
            <ArrowUpRight className="h-4 w-4" />
            {t.cta}
          </Button>
        </div>
      </div>
    </div>
  )
}

export default SetupAgentRail
