import { Clock3, Sparkles } from 'lucide-react'

import {
  resolveProjectAccent,
  resolveProjectBackgroundStyle,
  resolveProjectTemplate,
  type ProjectAccentId,
  type ProjectBackgroundStyleId,
  type ProjectTemplateId,
} from '@/lib/projectDisplayCatalog'
import { cn } from '@/lib/utils'

type ProjectDisplayPreviewCardProps = {
  title: string
  subtitle?: string | null
  template?: ProjectTemplateId | string | null
  accentColor?: ProjectAccentId | string | null
  backgroundStyle?: ProjectBackgroundStyleId | string | null
  meta?: string | null
  modeLabel?: string | null
  className?: string
}

export function ProjectDisplayPreviewCard({
  title,
  subtitle,
  template,
  accentColor,
  backgroundStyle,
  meta,
  modeLabel,
  className,
}: ProjectDisplayPreviewCardProps) {
  const accent = resolveProjectAccent(accentColor)
  const templateMeta = resolveProjectTemplate(template)
  const backgroundMeta = resolveProjectBackgroundStyle(backgroundStyle)

  const backgroundOverlayClassName =
    backgroundMeta.id === 'grid'
      ? 'bg-[linear-gradient(180deg,rgba(255,255,255,0.34),rgba(255,255,255,0.08)),linear-gradient(90deg,rgba(56,52,47,0.08)_1px,transparent_1px),linear-gradient(rgba(56,52,47,0.08)_1px,transparent_1px)] bg-[size:auto,24px_24px,24px_24px]'
      : backgroundMeta.id === 'archive'
        ? 'bg-[linear-gradient(180deg,rgba(255,255,255,0.2),rgba(255,255,255,0.04)),radial-gradient(circle_at_top_left,rgba(255,255,255,0.36),transparent_32%),linear-gradient(135deg,rgba(98,81,65,0.08),transparent_44%)]'
        : backgroundMeta.id === 'cloud'
          ? 'bg-[radial-gradient(circle_at_18%_20%,rgba(255,255,255,0.42),transparent_28%),radial-gradient(circle_at_74%_26%,rgba(255,255,255,0.22),transparent_24%),radial-gradient(circle_at_56%_78%,rgba(255,255,255,0.24),transparent_24%)]'
          : backgroundMeta.id === 'studio'
            ? 'bg-[linear-gradient(180deg,rgba(255,255,255,0.16),rgba(255,255,255,0.02)),linear-gradient(135deg,rgba(28,32,36,0.08),transparent_40%)]'
            : 'bg-[linear-gradient(180deg,rgba(255,255,255,0.38),rgba(255,255,255,0.08))]'

  const templateDecoration =
    templateMeta.id === 'experiment' ? (
      <div className="absolute inset-x-5 top-[72px] flex items-center gap-2 opacity-90" aria-hidden>
        <div className="h-2 w-2 rounded-full bg-white/80" />
        <div className="h-[2px] flex-1 rounded-full bg-white/52" />
        <div className="h-2 w-2 rounded-full bg-white/72" />
        <div className="h-[2px] w-16 rounded-full bg-white/38" />
      </div>
    ) : templateMeta.id === 'literature' ? (
      <div className="absolute right-5 top-[72px] w-24 space-y-2 opacity-85" aria-hidden>
        <div className="h-[3px] rounded-full bg-white/74" />
        <div className="h-[3px] w-4/5 rounded-full bg-white/58" />
        <div className="h-[3px] w-3/5 rounded-full bg-white/46" />
      </div>
    ) : templateMeta.id === 'analysis' ? (
      <div className="absolute right-5 top-[66px] flex h-14 items-end gap-1.5 opacity-85" aria-hidden>
        <div className="w-3 rounded-t-full bg-white/42" style={{ height: '36%' }} />
        <div className="w-3 rounded-t-full bg-white/58" style={{ height: '68%' }} />
        <div className="w-3 rounded-t-full bg-white/78" style={{ height: '94%' }} />
      </div>
    ) : (
      <div className="absolute right-5 top-[70px] rounded-full border border-white/44 bg-white/20 px-3 py-1 text-[10px] uppercase tracking-[0.16em] text-white/92" aria-hidden>
        Ready
      </div>
    )

  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-[28px] border border-black/10 bg-white/80 p-5 shadow-[0_28px_90px_-52px_rgba(42,38,33,0.35)] backdrop-blur-xl',
        className
      )}
    >
      <div className={cn('absolute inset-0 bg-gradient-to-br', accent.previewClassName)} aria-hidden />
      <div className={cn('absolute inset-0 opacity-90', accent.washClassName)} aria-hidden />
      <div className={cn('absolute inset-0 opacity-85', backgroundOverlayClassName)} aria-hidden />
      <div className="absolute right-5 top-5 flex items-center gap-2">
        <span className={cn('h-2.5 w-2.5 rounded-full shadow-sm', accent.dotClassName)} />
        {modeLabel ? (
          <span className="rounded-full border border-black/10 bg-white/65 px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.16em] text-[#5D5A55]">
            {modeLabel}
          </span>
        ) : null}
      </div>

      <div className="relative flex min-h-[224px] flex-col justify-between">
        {templateDecoration}
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-black/10 bg-white/68 px-3 py-1 text-[11px] font-medium text-[#5D5A55]">
            <Sparkles className="h-3.5 w-3.5" />
            {templateMeta.label}
          </div>
          <div className="mt-5 max-w-[18rem] text-2xl font-semibold tracking-[-0.02em] text-[#2D2A26]">
            {title}
          </div>
          <div className="mt-3 max-w-[22rem] text-sm leading-6 text-[#5D5A55]">
            {subtitle || templateMeta.description}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-[11px] text-[#6F6B65]">
          <div className="rounded-full border border-black/10 bg-white/68 px-3 py-1.5">
            {templateMeta.label}
          </div>
          <div className="rounded-full border border-black/10 bg-white/68 px-3 py-1.5">
            {backgroundMeta.label}
          </div>
          {meta ? (
            <div className="inline-flex items-center gap-2 rounded-full border border-black/10 bg-white/68 px-3 py-1.5">
              <Clock3 className="h-3.5 w-3.5" />
              {meta}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

export default ProjectDisplayPreviewCard
