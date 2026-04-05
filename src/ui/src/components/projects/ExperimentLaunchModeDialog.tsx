import { ChevronRight } from 'lucide-react'

import { OverlayDialog } from '@/components/home/OverlayDialog'
import { LAUNCH_DIALOG_SHELL_CLASS, LaunchModeIllustration, type LaunchModeKind } from '@/components/projects/LaunchModeVisuals'
import { cn } from '@/lib/utils'

type ExperimentLaunchModeDialogProps = {
  open: boolean
  locale?: string
  onClose: () => void
  onSelectMode: (mode: 'copilot' | 'autonomous') => void
}

const copy = {
  en: {
    title: 'Choose the start style',
    body: 'Either way, DeepScientist stays with you.',
    copilot: {
      hero: 'Copilot Mode',
      title: 'Create first. You decide when to start.',
      cta: 'Enter Copilot',
      badge: 'Fast',
    },
    autonomous: {
      hero: 'Autonomous Mode',
      title: 'Create and run immediately.',
      cta: 'Start Research',
      badge: 'Recommended',
    },
  },
  zh: {
    title: '选择启动方式',
    body: '无论哪种，DeepScientist 都会在你身边。',
    copilot: {
      hero: '协作模式',
      title: '先创建，再由你决定何时开始。',
      cta: '进入 Copilot',
      badge: '快速',
    },
    autonomous: {
      hero: '全自动模式',
      title: '创建后立即开始推进。',
      cta: '开始研究',
      badge: '推荐',
    },
  },
} as const

function ModeChoiceCard(props: {
  mode: LaunchModeKind
  hero: string
  title: string
  cta: string
  badge?: string
  onClick: () => void
  onboardingId?: string
}) {
  const isCopilot = props.mode === 'copilot'

  return (
    <button
      type="button"
      onClick={props.onClick}
      data-onboarding-id={props.onboardingId}
      className={cn(
        'group w-full overflow-hidden rounded-[30px] border text-left transition duration-200',
        'shadow-[0_24px_80px_-54px_rgba(42,38,33,0.24)] backdrop-blur-xl',
        isCopilot
          ? 'border-[rgba(187,158,136,0.16)] bg-[rgba(255,249,243,0.92)] hover:border-[rgba(173,142,118,0.32)]'
          : 'border-[rgba(122,148,159,0.18)] bg-[rgba(247,250,251,0.94)] hover:border-[rgba(103,132,145,0.32)] hover:shadow-[0_28px_90px_-54px_rgba(66,95,110,0.22)]'
      )}
    >
      <div className="relative h-[230px] overflow-hidden">
        <LaunchModeIllustration mode={props.mode} className="h-full w-full rounded-none" />
        <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.08),rgba(255,255,255,0.02)_42%,rgba(20,20,20,0.14)_100%)]" />
        {props.badge ? (
          <div className="absolute right-5 top-5 inline-flex rounded-full border border-white/45 bg-white/56 px-4 py-1.5 text-[16px] font-semibold uppercase tracking-[0.18em] text-[#2D2A26] shadow-[0_12px_30px_-20px_rgba(0,0,0,0.2)] backdrop-blur-md">
            {props.badge}
          </div>
        ) : null}
        <div className="absolute inset-x-6 bottom-7">
          <div className={cn(
            'text-[42px] font-semibold tracking-[-0.06em] text-[#2D2A26] drop-shadow-[0_10px_24px_rgba(255,255,255,0.22)] sm:text-[52px]',
            props.mode === 'autonomous' && 'sm:text-[56px]',
            props.hero.length > 10 && 'sm:text-[46px]'
          )}>
            {props.hero}
          </div>
        </div>
      </div>

      <div className="bg-white/92 px-6 py-5">
        <div className="text-[24px] font-semibold tracking-[-0.03em] text-[#2D2A26]">
          {props.title}
        </div>
        <div
          className={cn(
            'mt-5 inline-flex w-full items-center justify-center gap-2 rounded-full px-5 py-3.5 text-sm font-semibold transition',
            isCopilot
              ? 'bg-[rgba(45,42,38,0.92)] text-white group-hover:bg-[rgba(45,42,38,1)]'
              : 'bg-[rgba(28,40,46,0.95)] text-white group-hover:bg-[rgba(28,40,46,1)]'
          )}
        >
          <span>{props.cta}</span>
          <ChevronRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
        </div>
      </div>
    </button>
  )
}

export function ExperimentLaunchModeDialog({
  open,
  locale,
  onClose,
  onSelectMode,
}: ExperimentLaunchModeDialogProps) {
  const t = String(locale || '').startsWith('zh') ? copy.zh : copy.en

  return (
    <OverlayDialog
      open={open}
      title={t.title}
      description={t.body}
      onClose={onClose}
      className={cn(LAUNCH_DIALOG_SHELL_CLASS, 'h-auto lg:max-h-[78svh]')}
    >
      <div className="feed-scrollbar h-full min-h-0 overflow-y-auto p-4 sm:p-6 lg:p-7">
        <div className="grid gap-5 lg:grid-cols-2 lg:gap-6">
          <ModeChoiceCard
            mode="copilot"
            hero={t.copilot.hero}
            title={t.copilot.title}
            cta={t.copilot.cta}
            badge={t.copilot.badge}
            onboardingId="launch-mode-copilot-card"
            onClick={() => onSelectMode('copilot')}
          />
          <ModeChoiceCard
            mode="autonomous"
            hero={t.autonomous.hero}
            title={t.autonomous.title}
            cta={t.autonomous.cta}
            badge={t.autonomous.badge}
            onboardingId="launch-mode-autonomous-card"
            onClick={() => onSelectMode('autonomous')}
          />
        </div>
      </div>
    </OverlayDialog>
  )
}

export default ExperimentLaunchModeDialog
