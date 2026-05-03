import * as React from 'react'
import { ArrowUpRight, BookOpen, Sparkles, X } from 'lucide-react'

import { QuestCopilotComposer } from '@/components/workspace/QuestCopilotComposer'
import { Button } from '@/components/ui/button'
import type { QuestMessageAttachmentDraft } from '@/lib/hooks/useQuestMessageAttachments'
import { cn } from '@/lib/utils'

type AutonomousSetupIntakeSurfaceProps = {
  locale: 'en' | 'zh'
  assistantLabel?: string | null
  value: string
  onValueChange: (value: string) => void
  attachments: QuestMessageAttachmentDraft[]
  onQueueFiles: (files: File[]) => void
  onRemoveAttachment: (draftId: string) => void
  onSubmit: () => Promise<void> | void
  submitting?: boolean
  error?: string | null
  onSwitchToForm: () => void
  onSwitchToCopilot: () => void
  onOpenBenchStore?: () => void
  onClose?: () => void
}

function copy(locale: 'en' | 'zh') {
  return locale === 'zh'
    ? {
        title: '你想研究什么？',
        body:
          '直接描述目标、已有材料、约束和期望产出；可以把论文、代码、数据或 reviewer comments 一起拖进来。SetupAgent 会先帮你整理计划，再判断更适合全自动还是协作模式。',
        placeholder:
          '可以这样写：\n我想基于这篇论文和已有代码复现 baseline，并继续优化方法。已有材料包括……\n运行限制：1 张 GPU，最多跑 24 小时；可以/不可以使用外部 API；数据需要保密。\n希望产出：可信 baseline、改进实验、分析图表，最终可能写成论文。',
        sendLabel: '交给 SetupAgent',
        stopLabel: '停止',
        enterHint: '拖入文件 · Enter 发送 · Shift+Enter 换行',
        assistantLabel: 'SetupAgent 只做启动规划，不会直接开始研究执行',
        manualAutonomous: '手动进入全自动',
        manualCopilot: '手动进入协作模式',
        benchText: '还不确定任务 → 点击“BenchStore”阅读开放任务',
        closeLabel: '关闭',
      }
    : {
        title: 'What do you want to research?',
        body:
          'Describe the goal, materials, constraints, and desired output. Drop in papers, code, data, or reviewer comments. SetupAgent will plan first, then recommend autonomous or Copilot mode.',
        placeholder:
          'You can write:\nI want to reproduce the baseline from this paper and existing repo, then keep optimizing the method. Available materials include…\nConstraints: 1 GPU, up to 24 hours; external APIs allowed/not allowed; data must stay private.\nDesired output: trusted baseline, improved experiments, analysis figures, and possibly a paper draft.',
        sendLabel: 'Send to SetupAgent',
        stopLabel: 'Stop',
        enterHint: 'Drop files · Enter to send · Shift+Enter for newline',
        assistantLabel: 'SetupAgent plans the launch only. It will not start research execution yet.',
        manualAutonomous: 'Manual autonomous',
        manualCopilot: 'Manual Copilot',
        benchText: 'Not sure yet → click “BenchStore” to browse open tasks',
        closeLabel: 'Close',
      }
}

export function AutonomousSetupIntakeSurface(props: AutonomousSetupIntakeSurfaceProps) {
  const t = copy(props.locale)

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden bg-[#F6F1EA]">
      <div className="pointer-events-none absolute inset-0 opacity-90" aria-hidden="true">
        <div className="absolute left-[-14%] top-[-24%] h-[520px] w-[520px] rounded-full bg-[rgba(198,213,217,0.42)] blur-3xl" />
        <div className="absolute right-[-12%] top-[-28%] h-[540px] w-[540px] rounded-full bg-[rgba(225,207,178,0.48)] blur-3xl" />
        <div className="absolute bottom-[-30%] left-[24%] h-[600px] w-[600px] rounded-full bg-[rgba(226,232,218,0.4)] blur-3xl" />
      </div>

      <div className="absolute right-4 top-4 z-20">
        <Button type="button" variant="ghost" size="icon" className="rounded-full bg-white/48" onClick={props.onClose} aria-label={t.closeLabel}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="feed-scrollbar modal-scrollbar relative z-10 min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-8 sm:py-8">
        <div className="mx-auto flex min-h-full w-full max-w-6xl flex-col justify-start gap-5 pt-10 sm:justify-center sm:gap-7 sm:pt-0">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <div className="inline-flex items-center gap-2 rounded-full border border-[rgba(45,42,38,0.08)] bg-white/58 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.16em] text-[rgba(107,103,97,0.78)] backdrop-blur-xl">
                <Sparkles className="h-3.5 w-3.5" />
                Start Research
              </div>
              <h1 className="mt-4 max-w-3xl text-[32px] font-semibold leading-[1.04] text-[rgba(38,36,33,0.97)] sm:text-6xl sm:leading-[0.98]">
                {t.title}
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-[rgba(86,82,77,0.82)] sm:text-[15px]">
                {t.body}
              </p>
              <p className="mt-2 text-xs leading-5 text-[rgba(107,103,97,0.72)]">
                {props.assistantLabel || t.assistantLabel}
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2 sm:justify-end">
              <Button type="button" variant="outline" className="w-full rounded-full bg-white/64 sm:w-auto" onClick={props.onSwitchToCopilot}>
                <ArrowUpRight className="mr-1.5 h-4 w-4" />
                {t.manualCopilot}
              </Button>
              <Button type="button" variant="secondary" className="w-full rounded-full sm:w-auto" onClick={props.onSwitchToForm}>
                {t.manualAutonomous}
              </Button>
            </div>
          </div>

          <div
            className={cn(
              'mx-auto w-full rounded-[26px] border border-[rgba(45,42,38,0.08)] bg-[linear-gradient(180deg,rgba(255,255,255,0.9),rgba(251,248,243,0.93))] p-3 shadow-[0_44px_120px_-62px_rgba(45,42,38,0.46)] backdrop-blur-2xl sm:rounded-[38px] sm:p-5',
              props.error && 'border-[rgba(154,27,27,0.24)]'
            )}
          >
            <QuestCopilotComposer
              value={props.value}
              onValueChange={props.onValueChange}
              onSubmit={props.onSubmit}
              submitting={props.submitting}
              placeholder={t.placeholder}
              enterHint={t.enterHint}
              sendLabel={t.sendLabel}
              stopLabel={t.stopLabel}
              attachments={props.attachments}
              onQueueFiles={props.onQueueFiles}
              onRemoveAttachment={props.onRemoveAttachment}
              shellClassName="rounded-[22px] bg-[rgba(252,250,246,0.96)] shadow-[0_20px_54px_-38px_rgba(24,28,32,0.24)] sm:rounded-[28px]"
              textareaClassName="min-h-[170px] px-4 pt-4 pb-16 text-[14px] leading-7 sm:min-h-[320px] sm:px-5 sm:pt-5 sm:text-[15px] lg:min-h-[360px]"
            />
            {props.error ? (
              <div className="px-1 pt-3 text-sm text-[var(--function-error)]">{props.error}</div>
            ) : null}
          </div>

          <div className="mx-auto flex w-full max-w-3xl items-center justify-center text-center text-sm leading-6 text-[rgba(86,82,77,0.78)]">
            <button
              type="button"
              className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-[rgba(45,42,38,0.08)] bg-white/62 px-4 py-2 text-[rgba(45,42,38,0.9)] transition hover:bg-white"
              onClick={props.onOpenBenchStore}
            >
              <BookOpen className="h-3.5 w-3.5" />
              {t.benchText}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default AutonomousSetupIntakeSurface
