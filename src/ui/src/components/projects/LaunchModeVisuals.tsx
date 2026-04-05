import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export type LaunchModeKind = 'copilot' | 'autonomous'

export const LAUNCH_DIALOG_SHELL_CLASS =
  'h-[90svh] w-[96vw] max-w-none rounded-[32px] border border-white/10 bg-[rgba(252,248,242,0.98)] shadow-[0_40px_120px_-52px_rgba(15,23,42,0.5)] lg:w-[88vw]'

function launchModeWash(mode: LaunchModeKind) {
  if (mode === 'copilot') {
    return {
      surface:
        'linear-gradient(135deg, rgba(205,219,224,0.96) 0%, rgba(228,233,229,0.94) 34%, rgba(184,203,211,0.96) 100%)',
      mistA: 'rgba(255,255,255,0.38)',
      mistB: 'rgba(173,197,205,0.24)',
      mistC: 'rgba(205,214,217,0.18)',
      vein: 'rgba(103,133,146,0.08)',
      grain: 'rgba(255,255,255,0.08)',
    }
  }
  return {
    surface:
      'linear-gradient(135deg, rgba(224,205,190,0.96) 0%, rgba(238,223,210,0.94) 34%, rgba(198,166,145,0.96) 100%)',
    mistA: 'rgba(255,244,236,0.38)',
    mistB: 'rgba(210,169,145,0.22)',
    mistC: 'rgba(173,124,101,0.16)',
    vein: 'rgba(154,96,68,0.08)',
    grain: 'rgba(255,248,244,0.08)',
  }
}

export function LaunchModeIllustration({
  mode,
  className,
}: {
  mode: LaunchModeKind
  className?: string
}) {
  const wash = launchModeWash(mode)
  return (
    <div
      className={cn('relative aspect-[12/8] w-full overflow-hidden rounded-[28px]', className)}
      style={{ backgroundImage: wash.surface }}
    >
      <div
        className="absolute inset-0 opacity-90"
        style={{
          backgroundImage: [
            `radial-gradient(circle at 18% 24%, ${wash.mistA} 0%, transparent 30%)`,
            `radial-gradient(circle at 74% 22%, ${wash.mistB} 0%, transparent 26%)`,
            `radial-gradient(circle at 64% 74%, ${wash.mistC} 0%, transparent 28%)`,
            `radial-gradient(circle at 28% 72%, rgba(255,255,255,0.22) 0%, transparent 24%)`,
          ].join(','),
        }}
      />
      <div
        className="absolute inset-0 opacity-70 mix-blend-multiply"
        style={{
          backgroundImage: [
            `radial-gradient(ellipse at 16% 34%, ${wash.vein} 0%, transparent 42%)`,
            `radial-gradient(ellipse at 72% 30%, ${wash.vein} 0%, transparent 38%)`,
            `radial-gradient(ellipse at 58% 74%, ${wash.vein} 0%, transparent 34%)`,
            `repeating-linear-gradient(16deg, transparent 0 11px, ${wash.grain} 12px 13px, transparent 14px 24px)`,
            `repeating-linear-gradient(112deg, transparent 0 17px, ${wash.grain} 18px 19px, transparent 20px 32px)`,
          ].join(','),
        }}
      />
      <div className="absolute -left-[8%] top-[8%] h-[54%] w-[46%] rounded-full bg-white/20 blur-3xl" />
      <div className="absolute right-[-6%] top-[18%] h-[46%] w-[40%] rounded-full bg-white/12 blur-3xl" />
      <div className="absolute bottom-[-10%] left-[28%] h-[40%] w-[48%] rounded-full bg-white/16 blur-3xl" />
    </div>
  )
}

export function LaunchModeSummaryCard({
  mode,
  title,
  subtitle,
  keywords,
  badge,
  className,
}: {
  mode: LaunchModeKind
  title: string
  subtitle: string
  keywords: string[]
  badge?: ReactNode
  className?: string
}) {
  const tone =
    mode === 'copilot'
      ? {
          frame: 'bg-[rgba(255,249,244,0.94)]',
          chip: 'border-[rgba(177,145,122,0.16)] bg-white/82 text-[rgba(109,84,67,0.8)]',
        }
      : {
          frame: 'bg-[rgba(246,249,250,0.94)]',
          chip: 'border-[rgba(95,122,134,0.16)] bg-white/82 text-[rgba(74,97,108,0.82)]',
        }

  return (
    <div
      className={cn(
        'rounded-[20px] border border-black/8 bg-white/[0.8] p-3.5 shadow-[0_18px_54px_-44px_rgba(42,38,33,0.24)] backdrop-blur-xl',
        className
      )}
    >
      <div className={cn('relative overflow-hidden rounded-[16px] border border-black/6 p-3', tone.frame)}>
        {badge ? <div className="absolute right-3 top-3 z-10">{badge}</div> : null}
        <LaunchModeIllustration mode={mode} className="mx-auto max-w-[320px]" />
      </div>
      <div className="mt-3.5">
        <div className="text-[18px] font-semibold tracking-[-0.03em] text-[#2D2A26]">{title}</div>
        <div className="mt-1.5 text-sm leading-6 text-[#5D5A55]">{subtitle}</div>
        <div className="mt-3 flex flex-wrap gap-2">
          {keywords.slice(0, 2).map((keyword) => (
            <span
              key={`${mode}-${keyword}`}
              className={cn('rounded-full border px-3 py-1 text-[11px] font-medium uppercase tracking-[0.16em]', tone.chip)}
            >
              {keyword}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
