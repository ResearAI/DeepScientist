'use client'

import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from 'framer-motion'
import { useMobileViewport } from '@/lib/hooks/useMobileViewport'
import { cn } from '@/lib/utils'
import type { Locale } from '@/types'
import { getHeroBundle, type HeroFeature } from './hero-content'
import HeroTerminal from './HeroTerminal'
import HeroFooter from './HeroFooter'
import { FadeContent, GlareHover, SpotlightCard } from '@/components/react-bits'
import { PngIcon } from '@/components/ui/png-icon'
import {
  BarChart3,
  BookOpen,
  Braces,
  Database,
  FileText,
  Folder,
} from 'lucide-react'

const STEP_FALLBACK_ICONS = {
  BookOpen,
  Braces,
  BarChart3,
  File: FileText,
}

const FEATURE_FALLBACK_ICONS = {
  FolderIcon: Folder,
  File: FileText,
  Database,
}

function FeaturePreview({ feature, animate, locale }: { feature: HeroFeature; animate: boolean; locale: Locale }) {
  if (feature.id === 'welcome') {
    return (
      <div className="mt-auto rounded-2xl border border-black/5 bg-[#F7F3EC] p-3 text-[11px] text-[#6F6B66]">
        <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.22em] text-[#9A948C]">
          <span>{locale === 'zh' ? '快捷提示' : 'Quick prompts'}</span>
          <span className="flex items-center gap-1 text-[#9FB1C2]">
            <span className="ds-hero-pulse h-1.5 w-1.5 rounded-full bg-[#9FB1C2]" />
            {locale === 'zh' ? '实时' : 'live'}
          </span>
        </div>
        <div className="mt-2 space-y-1 font-mono text-[11px] text-[#5D5A55]">
          <div>{locale === 'zh' ? '> 总结 CRISPR 论文中的冲突点' : '> Summarize contradictions in CRISPR papers'}</div>
          <div className="text-[#7E8B97]">{locale === 'zh' ? '已新增 12 条证据链接' : '12 evidence links added'}</div>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {feature.chips.map((chip) => (
            <span
              key={chip}
              className="rounded-full border border-black/5 bg-white/70 px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] text-[#7E8B97]"
            >
              {chip}
            </span>
          ))}
        </div>
      </div>
    )
  }

  if (feature.id === 'workspace') {
    return (
      <div className="mt-auto rounded-2xl border border-black/5 bg-[#F7F3EC] p-3 text-[11px] text-[#6F6B66]">
        <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.22em] text-[#9A948C]">
          <span>{locale === 'zh' ? '实时工作区' : 'Live workspace'}</span>
          <span className="flex items-center gap-1 text-[#9FB1C2]">
            <span className="ds-hero-pulse h-1.5 w-1.5 rounded-full bg-[#9FB1C2]" />
            {locale === 'zh' ? '已同步' : 'synced'}
          </span>
        </div>
        <div className="mt-2 space-y-1">
          {[
            { name: 'notebook.md', icon: 'File' },
            { name: 'sources.bib', icon: 'Database' },
            { name: 'figures/', icon: 'FolderIcon' },
          ].map((item) => {
            const IconFallback =
              FEATURE_FALLBACK_ICONS[item.icon as keyof typeof FEATURE_FALLBACK_ICONS] ?? FileText
            return (
              <div key={item.name} className="flex items-center gap-2">
                <PngIcon
                  name={item.icon}
                  size={12}
                  className="h-3 w-3"
                  fallback={<IconFallback className="h-3 w-3" />}
                />
                {item.name}
              </div>
            )
          })}
        </div>
        <div className="mt-2 border-t border-black/5 pt-2 font-mono text-[10px] text-[#7E8B97]">
          {locale === 'zh' ? '> 导出 arxiv-ready.zip' : '> export arxiv-ready.zip'}
        </div>
      </div>
    )
  }

  return null
}

export default function HeroSections({ locale }: { locale: Locale }) {
  const prefersReducedMotion = useReducedMotion()
  const hero = getHeroBundle(locale)
  const [activeStep, setActiveStep] = useState(0)
  const isMobile = useMobileViewport()
  const stepRefs = useRef<(HTMLElement | null)[]>([])
  const carouselRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (isMobile) return
    const nodes = stepRefs.current.filter(Boolean) as HTMLElement[]
    if (!nodes.length) return

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return
          const index = Number(entry.target.getAttribute('data-step'))
          if (!Number.isNaN(index)) {
            setActiveStep(index)
          }
        })
      },
      {
        threshold: prefersReducedMotion ? 0.4 : 0.55,
        rootMargin: '-10% 0px -40% 0px',
      }
    )

    nodes.forEach((node) => observer.observe(node))
    return () => observer.disconnect()
  }, [isMobile, prefersReducedMotion])

  useEffect(() => {
    if (!isMobile) return
    const scroller = carouselRef.current
    if (!scroller) return

    const updateStage = () => {
      const width = scroller.getBoundingClientRect().width || 1
      const nextIndex = Math.round(scroller.scrollLeft / width)
      setActiveStep(
        Math.min(hero.researchSteps.length - 1, Math.max(0, nextIndex))
      )
    }

    updateStage()
    scroller.addEventListener('scroll', updateStage, { passive: true })
    window.addEventListener('resize', updateStage)

    return () => {
      scroller.removeEventListener('scroll', updateStage)
      window.removeEventListener('resize', updateStage)
    }
  }, [isMobile])

  return (
    <div className="relative pb-20 pt-6">
      <section className="relative py-16">
        <div className="mx-auto w-full max-w-[90vw] px-6">
          <FadeContent duration={0.6} y={16} blur={false}>
            <div className="max-w-2xl space-y-3">
              <div className="text-xs uppercase tracking-[0.24em] text-[#7E8B97]">
                {locale === 'zh' ? '自治研究循环' : 'Autonomous Research Loop'}
              </div>
              <h2 className="text-2xl font-semibold text-[#2D2A26] md:text-3xl">
                {locale === 'zh' ? '从问题走向可发表证据' : 'From question to publishable evidence'}
              </h2>
              <p className="text-sm text-[#5D5A55] md:text-base">
                {locale === 'zh'
                  ? '向下滚动，观察 CLI 叙事如何随着每一步研究逐渐变得具体、可复现并最终可交付。'
                  : 'Scroll to watch the CLI narrative evolve as each research step becomes concrete, reproducible, and ready to ship.'}
              </p>
            </div>
          </FadeContent>

          {isMobile ? (
            <div className="mt-8 space-y-4">
              <div id="cli" className="scroll-mt-24">
                <HeroTerminal className="w-full" activeIndex={activeStep} locale={locale} />
              </div>
              <div
                ref={carouselRef}
                className="flex snap-x snap-mandatory gap-4 overflow-x-auto pb-2"
              >
                {hero.researchSteps.map((step, index) => {
                  const FallbackIcon =
                    STEP_FALLBACK_ICONS[step.icon as keyof typeof STEP_FALLBACK_ICONS] ||
                    BookOpen
                  return (
                    <div key={step.id} className="w-full shrink-0 snap-start px-1">
                      <SpotlightCard
                        className={cn(
                          'relative rounded-3xl border border-black/5 bg-white/70 p-5',
                          'shadow-[0_18px_40px_-30px_rgba(45,42,38,0.5)]',
                          index === activeStep && 'border-[#9FB1C2]/60 bg-white/80'
                        )}
                      >
                        <FadeContent duration={0.5} y={14} blur={false}>
                          <div className="flex items-start gap-4">
                            <span
                              className={cn(
                                'flex h-11 w-11 items-center justify-center rounded-2xl border border-black/10',
                                step.tone === 'warm' ? 'bg-[#EFE5D6]' : 'bg-[#E1E7EF]'
                              )}
                            >
                              <PngIcon
                                name={step.icon}
                                size={18}
                                className="h-5 w-5"
                                fallback={<FallbackIcon className="h-5 w-5" />}
                              />
                            </span>
                            <div className="space-y-2">
                              <div className="text-[10px] uppercase tracking-[0.22em] text-[#9A948C]">
                                Step {index + 1} - {step.subtitle}
                              </div>
                              <h3 className="text-lg font-semibold text-[#2D2A26]">
                                {step.title}
                              </h3>
                              <p className="text-sm text-[#5D5A55]">
                                {step.body}
                              </p>
                              <div className="flex flex-wrap gap-2 text-xs text-[#6F6B66]">
                                {step.tags.map((tag) => (
                                  <span
                                    key={tag}
                                    className="rounded-full border border-black/5 bg-white/60 px-2 py-0.5"
                                  >
                                    {tag}
                                  </span>
                                ))}
                              </div>
                            </div>
                          </div>
                        </FadeContent>
                      </SpotlightCard>
                    </div>
                  )
                })}
              </div>
              <div className="flex items-center justify-between text-xs text-[#7E8B97]">
                <span>
                  {locale === 'zh' ? `步骤 ${activeStep + 1} / ${hero.researchSteps.length}` : `Step ${activeStep + 1} / ${hero.researchSteps.length}`}
                </span>
                <span>{locale === 'zh' ? '左右滑动继续探索' : 'Swipe to explore'}</span>
              </div>
            </div>
          ) : (
            <div className="mt-10 grid gap-10 lg:grid-cols-[1.15fr_0.85fr]">
              <div className="relative space-y-6 pl-10">
                <div className="absolute left-4 top-4 h-[calc(100%-32px)] w-px bg-[#D7C6AE]/60" />
                {hero.researchSteps.map((step, index) => {
                  const FallbackIcon =
                    STEP_FALLBACK_ICONS[step.icon as keyof typeof STEP_FALLBACK_ICONS] ||
                    BookOpen
                  const isActive = index === activeStep
                  return (
                    <SpotlightCard
                      key={step.id}
                      ref={(node) => {
                        stepRefs.current[index] = node
                      }}
                      data-step={index}
                      className={cn(
                        'relative rounded-3xl border border-black/5 bg-white/70 p-5',
                        'shadow-[0_20px_45px_-32px_rgba(45,42,38,0.5)]',
                        'transition-all duration-300',
                        isActive && 'border-[#9FB1C2]/60 bg-white/85'
                      )}
                    >
                      <span
                        className={cn(
                          'absolute left-[-2.35rem] top-8 h-3 w-3 rounded-full border border-white/70',
                          isActive ? 'bg-[#9FB1C2]' : 'bg-[#D7C6AE]/70'
                        )}
                      />
                      <FadeContent duration={0.55} y={14} blur={false}>
                        <div className="flex items-start gap-4">
                          <span
                            className={cn(
                              'flex h-11 w-11 items-center justify-center rounded-2xl border border-black/10',
                              step.tone === 'warm' ? 'bg-[#EFE5D6]' : 'bg-[#E1E7EF]'
                            )}
                          >
                            <PngIcon
                              name={step.icon}
                              size={18}
                              className="h-5 w-5"
                              fallback={<FallbackIcon className="h-5 w-5" />}
                            />
                          </span>
                          <div className="space-y-2">
                            <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] text-[#9A948C]">
                              <span className="rounded-full border border-black/5 bg-white/60 px-2 py-0.5">
                                {locale === 'zh' ? `步骤 ${index + 1}` : `Step ${index + 1}`}
                              </span>
                              <span>{step.subtitle}</span>
                            </div>
                            <h3 className="text-lg font-semibold text-[#2D2A26]">
                              {step.title}
                            </h3>
                            <p className="text-sm text-[#5D5A55]">
                              {step.body}
                            </p>
                            <div className="flex flex-wrap gap-2 text-xs text-[#6F6B66]">
                              {step.tags.map((tag) => (
                                <span
                                  key={tag}
                                  className="rounded-full border border-black/5 bg-white/60 px-2 py-0.5"
                                >
                                  {tag}
                                </span>
                              ))}
                            </div>
                          </div>
                        </div>
                      </FadeContent>
                    </SpotlightCard>
                  )
                })}
              </div>
                <div
                  className="space-y-4 scroll-mt-24 lg:sticky lg:top-24 lg:self-start"
                  id="cli"
                >
                <HeroTerminal activeIndex={activeStep} locale={locale} />
                <div className="flex items-center gap-2 text-xs text-[#7E8B97]">
                  <span className="h-1.5 w-1.5 rounded-full bg-[#9FB1C2]" />
                  {locale === 'zh' ? '滚动以推进 CLI 叙事' : 'Scroll to advance the CLI narrative'}
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="relative py-16 scroll-mt-24">
        <div className="mx-auto w-full max-w-[90vw] px-6">
          <FadeContent duration={0.6} y={18} blur={false}>
            <div className="max-w-2xl space-y-3">
              <div className="text-xs uppercase tracking-[0.24em] text-[#7E8B97]">
                {locale === 'zh' ? '协同工作区' : 'Connected Workspace'}
              </div>
              <h2 className="text-2xl font-semibold text-[#2D2A26] md:text-3xl">
                {locale === 'zh' ? '研究推进过程中，所有工具始终保持联动' : 'Every tool stays connected as the research evolves'}
              </h2>
              <p className="text-sm text-[#5D5A55] md:text-base">
                {locale === 'zh'
                  ? '在提示、图表和文件之间切换时，不会丢失来源脉络。每个插件都会更新同一份研究记录。'
                  : 'Move between prompts, figures, and files without losing provenance. Each plugin updates the same research record.'}
              </p>
            </div>
          </FadeContent>

          <div className="mt-10 grid gap-6 lg:grid-cols-3">
            {hero.features.map((feature) => (
              <FadeContent
                key={feature.id}
                duration={0.6}
                y={16}
                blur={false}
                className="h-full"
              >
                <GlareHover className="h-full rounded-3xl">
                  <SpotlightCard
                    id={feature.id === 'welcome' ? undefined : feature.id}
                    className={cn(
                      'relative h-full min-h-[320px] rounded-3xl border border-black/5 bg-white/70 p-6 scroll-mt-24 md:min-h-[360px]',
                      'shadow-[0_22px_48px_-32px_rgba(45,42,38,0.5)]'
                    )}
                  >
                    <div
                      aria-hidden
                      className="absolute inset-0 opacity-70"
                      style={{
                        backgroundImage:
                          feature.tone === 'warm'
                            ? 'radial-gradient(260px circle at 18% 14%, rgba(215, 198, 174, 0.38), transparent 60%)'
                            : 'radial-gradient(260px circle at 18% 14%, rgba(159, 177, 194, 0.35), transparent 60%)',
                      }}
                    />
                    <div className="relative flex h-full flex-col gap-4">
                      <div className="flex items-start gap-3">
                        <img
                          src={feature.icon}
                          alt={feature.kicker}
                          className="ds-hero-float h-10 w-10 object-contain"
                          draggable={false}
                        />
                        <div className="space-y-2">
                          <div className="text-xs uppercase tracking-[0.2em] text-[#7E8B97]">
                            {feature.kicker}
                          </div>
                          <h3 className="text-xl font-semibold text-[#2D2A26]">
                            {feature.title}
                          </h3>
                          <p className="text-sm text-[#5D5A55]">{feature.body}</p>
                        </div>
                      </div>
                      <ul className="space-y-2 text-sm text-[#5D5A55]">
                        {feature.bullets.map((bullet) => (
                          <li key={bullet} className="flex items-start gap-2">
                            <span className="mt-2 h-1.5 w-1.5 rounded-full bg-[#9FB1C2]" />
                            <span>{bullet}</span>
                          </li>
                        ))}
                      </ul>
                      <FeaturePreview feature={feature} animate={!prefersReducedMotion} locale={locale} />
                    </div>
                  </SpotlightCard>
                </GlareHover>
              </FadeContent>
            ))}
          </div>
        </div>
      </section>

      <section className="relative py-16">
        <div className="mx-auto w-full max-w-[90vw] px-6">
          <div className="relative overflow-hidden rounded-3xl border border-black/5 bg-white/70 p-8">
            <div
              aria-hidden
              className="absolute inset-0 opacity-70"
              style={{
                backgroundImage:
                  'radial-gradient(420px circle at 20% 20%, rgba(159, 177, 194, 0.35), transparent 65%), radial-gradient(320px circle at 80% 0%, rgba(215, 198, 174, 0.3), transparent 60%)',
              }}
            />
            <div className="relative flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
              <div className="space-y-2">
                <div className="text-xs uppercase tracking-[0.22em] text-[#7E8B97]">
                  Ready to run the loop
                </div>
                <h3 className="text-2xl font-semibold text-[#2D2A26]">
                  Launch a new experiment today
                </h3>
                <p className="text-sm text-[#5D5A55]">
                  Start in seconds, then connect the CLI, workspace, and
                  reproducible outputs as your research evolves.
                </p>
              </div>
              <div className="rounded-full border border-black/10 bg-white/75 px-4 py-2 text-sm text-[#5D5A55]">
                Use the two main actions above to start or resume a quest.
              </div>
            </div>
          </div>
        </div>
      </section>

      <HeroFooter />
    </div>
  )
}
