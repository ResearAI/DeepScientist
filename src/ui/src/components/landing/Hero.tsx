'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useReducedMotion } from 'framer-motion'
import { FolderOpen } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { CreateProjectDialog } from '@/components/projects/CreateProjectDialog'
import { OpenQuestDialog } from '@/components/projects/OpenQuestDialog'
import { Button } from '@/components/ui/button'
import { FadeContent, GlareHover } from '@/components/react-bits'
import { client } from '@/lib/api'
import { runtimeVersion } from '@/lib/runtime/quest-runtime'
import { HERO_COPY, HERO_STAGES } from './hero-content'
import type { QuestSummary } from '@/types'
import HeroNav from './HeroNav'
import HeroScene from './HeroScene'
import HeroProgress from './HeroProgress'
import { UpdateReminderDialog } from './UpdateReminderDialog'

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max)
const FINAL_SCROLL_HOLD = 0.2

function sortQuests(items: QuestSummary[]) {
  return [...items].sort((left, right) => {
    const leftTime = new Date(left.updated_at || 0).getTime()
    const rightTime = new Date(right.updated_at || 0).getTime()
    return rightTime - leftTime
  })
}

export default function Hero() {
  const navigate = useNavigate()
  const heroRef = useRef<HTMLElement | null>(null)
  const prefersReducedMotion = useReducedMotion()
  const reducedMotion = prefersReducedMotion ?? false
  const [progress, setProgress] = useState(0)
  const [isMobile, setIsMobile] = useState(false)
  const [isPortraitMode, setIsPortraitMode] = useState(false)
  const [showProgress, setShowProgress] = useState(true)
  const progressRef = useRef(0)
  const targetRef = useRef(0)
  const holdRef = useRef(0)
  const rafRef = useRef<number | null>(null)
  const allowScrollProgressRef = useRef(true)
  const lastScrollYRef = useRef(0)
  const lockedScrollYRef = useRef<number | null>(null)
  const scheduleTickRef = useRef<() => void>(() => {})
  const [questDialogOpen, setQuestDialogOpen] = useState(false)
  const [quests, setQuests] = useState<QuestSummary[]>([])
  const [questsLoading, setQuestsLoading] = useState(false)
  const [deletingQuestId, setDeletingQuestId] = useState<string | null>(null)
  const [questError, setQuestError] = useState<string | null>(null)
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const currentVersion = useMemo(() => runtimeVersion(), [])

  useEffect(() => {
    document.body.classList.add('font-project')
    return () => document.body.classList.remove('font-project')
  }, [])

  useEffect(() => {
    const updateSize = () => {
      setIsMobile(window.innerWidth < 1024)
    }
    updateSize()
    window.addEventListener('resize', updateSize)
    return () => window.removeEventListener('resize', updateSize)
  }, [])

  useEffect(() => {
    const query = window.matchMedia('(orientation: portrait) and (max-width: 1023px)')
    const updateOrientation = () => {
      setIsPortraitMode(query.matches)
    }

    updateOrientation()
    query.addEventListener('change', updateOrientation)
    window.addEventListener('resize', updateOrientation)

    return () => {
      query.removeEventListener('change', updateOrientation)
      window.removeEventListener('resize', updateOrientation)
    }
  }, [])

  useEffect(() => {
    if (isPortraitMode) {
      targetRef.current = 0
      progressRef.current = 0
      holdRef.current = 0
      setProgress(0)
      setShowProgress(false)
      return
    }

    const element = heroRef.current
    if (!element) return

    const updateVisibility = (heroTop: number, heroHeight: number) => {
      const viewportTop = window.scrollY
      const viewportBottom = viewportTop + window.innerHeight
      const heroBottom = heroTop + heroHeight
      const isVisible = viewportBottom > heroTop && viewportTop < heroBottom
      setShowProgress((prev) => (prev === isVisible ? prev : isVisible))
    }

    const tick = () => {
      const target = targetRef.current
      const current = progressRef.current
      const next = reducedMotion ? target : current + (target - current) * 0.12

      progressRef.current = next
      setProgress(next)

      if (Math.abs(target - next) > 0.001) {
        rafRef.current = requestAnimationFrame(tick)
      } else {
        rafRef.current = null
      }
    }

    const scheduleTick = () => {
      if (rafRef.current === null) {
        rafRef.current = requestAnimationFrame(tick)
      }
    }

    scheduleTickRef.current = scheduleTick

    const updateTarget = () => {
      const scrollY = window.scrollY
      const heroTop = element.getBoundingClientRect().top + scrollY
      const heroHeight = element.offsetHeight
      const travel = Math.max(1, heroHeight - window.innerHeight)

      updateVisibility(heroTop, heroHeight)

      if (!allowScrollProgressRef.current) {
        if (scrollY > heroTop + 2) {
          allowScrollProgressRef.current = true
          lockedScrollYRef.current = null
        } else {
          if (lockedScrollYRef.current === null) {
            lockedScrollYRef.current = scrollY
          }
          if (scrollY !== lockedScrollYRef.current) {
            window.scrollTo({ top: lockedScrollYRef.current, behavior: 'auto' })
          }
          lastScrollYRef.current = lockedScrollYRef.current
          return
        }
      }

      const scrolled = clamp(scrollY - heroTop, 0, travel)
      const nextTarget = scrolled / travel
      const lastScrollY = lastScrollYRef.current
      lastScrollYRef.current = scrollY
      targetRef.current =
        scrollY < lastScrollY ? nextTarget : Math.max(targetRef.current, nextTarget)
      if (targetRef.current < 1) {
        holdRef.current = 0
      }
      scheduleTick()
    }

    updateTarget()
    window.addEventListener('scroll', updateTarget, { passive: true })
    window.addEventListener('resize', updateTarget)

    return () => {
      window.removeEventListener('scroll', updateTarget)
      window.removeEventListener('resize', updateTarget)
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
  }, [reducedMotion, isPortraitMode])

  useEffect(() => {
    if (isMobile || isPortraitMode) {
      allowScrollProgressRef.current = true
      lockedScrollYRef.current = null
      return
    }

    const handleWheel = (event: WheelEvent) => {
      const element = heroRef.current
      if (!element) return

      const heroTop = element.getBoundingClientRect().top + window.scrollY
      const heroHeight = element.offsetHeight
      const heroBottom = heroTop + heroHeight
      const viewportTop = window.scrollY
      const viewportBottom = viewportTop + window.innerHeight
      const isVisible = viewportBottom > heroTop && viewportTop < heroBottom

      if (!isVisible) return

      const virtualProgress = clamp(targetRef.current + holdRef.current, 0, 1 + FINAL_SCROLL_HOLD)
      const shouldLock = viewportTop <= heroTop + 2 && virtualProgress < 1 + FINAL_SCROLL_HOLD

      if (!shouldLock) {
        if (!allowScrollProgressRef.current) {
          allowScrollProgressRef.current = true
          lockedScrollYRef.current = null
        }
        return
      }

      event.preventDefault()
      if (allowScrollProgressRef.current) {
        lockedScrollYRef.current = window.scrollY
      }
      allowScrollProgressRef.current = false
      if (lockedScrollYRef.current !== null && window.scrollY !== lockedScrollYRef.current) {
        window.scrollTo({ top: lockedScrollYRef.current, behavior: 'auto' })
        lastScrollYRef.current = lockedScrollYRef.current
      }

      const delta = event.deltaY / (window.innerHeight * 1.6)
      const nextVirtual = clamp(virtualProgress + delta, 0, 1 + FINAL_SCROLL_HOLD)
      targetRef.current = Math.min(1, nextVirtual)
      holdRef.current = Math.max(0, nextVirtual - 1)
      scheduleTickRef.current()
    }

    window.addEventListener('wheel', handleWheel, { passive: false })
    return () => window.removeEventListener('wheel', handleWheel)
  }, [isMobile, isPortraitMode])

  useEffect(() => {
    if (!questDialogOpen) {
      return
    }

    let active = true

    const loadQuests = async () => {
      setQuestsLoading(true)
      try {
        const payload = await client.quests()
        if (!active) {
          return
        }
        setQuests(sortQuests(payload))
        setQuestError(null)
      } catch (caught) {
        if (!active) {
          return
        }
        setQuestError(caught instanceof Error ? caught.message : 'Failed to load quests.')
      } finally {
        if (active) {
          setQuestsLoading(false)
        }
      }
    }

    void loadQuests()

    return () => {
      active = false
    }
  }, [questDialogOpen])

  const createAndOpen = async (payload: {
    title: string
    goal: string
    quest_id?: string
    requested_connector_bindings?: Array<{ connector: string; conversation_id?: string | null }>
    requested_baseline_ref?: { baseline_id: string; variant_id?: string | null } | null
    startup_contract?: Record<string, unknown> | null
  }) => {
    if (!payload.goal.trim()) {
      return
    }

    setCreating(true)
    setCreateError(null)
    try {
      const result = await client.createQuestWithOptions({
        goal: payload.goal.trim(),
        title: payload.title.trim() || undefined,
        quest_id: payload.quest_id?.trim() || undefined,
        source: 'web-react',
        auto_start: true,
        initial_message: payload.goal.trim(),
        requested_connector_bindings: payload.requested_connector_bindings,
        requested_baseline_ref: payload.requested_baseline_ref ?? undefined,
        startup_contract: payload.startup_contract ?? undefined,
      })
      setCreateDialogOpen(false)
      navigate(`/projects/${result.snapshot.quest_id}`)
    } catch (caught) {
      setCreateError(caught instanceof Error ? caught.message : 'Failed to create quest.')
    } finally {
      setCreating(false)
    }
  }

  const deleteQuest = async (questId: string) => {
    const trimmed = questId.trim()
    if (!trimmed) return
    setDeletingQuestId(trimmed)
    try {
      await client.deleteQuest(trimmed)
      setQuests((current) => current.filter((item) => item.quest_id !== trimmed))
      setQuestError(null)
    } catch (caught) {
      setQuestError(caught instanceof Error ? caught.message : 'Failed to delete quest.')
    } finally {
      setDeletingQuestId(null)
    }
  }

  const scrollStage = useMemo(() => {
    if (progress < 0.25) return 0
    if (progress < 0.5) return 1
    if (progress < 0.75) return 2
    return 3
  }, [progress])

  const sceneStageIndex = scrollStage
  const barProgress = progress

  return (
    <>
      <div
        className="relative min-h-[100svh] overflow-x-hidden bg-[#F5F2EC] text-[#2D2A26]"
        style={{
          backgroundImage:
            'radial-gradient(900px circle at 15% 15%, rgba(185, 199, 214, 0.28), transparent 60%), radial-gradient(700px circle at 85% 0%, rgba(215, 198, 174, 0.32), transparent 58%), linear-gradient(180deg, #F5F2EC 0%, #EEE7DD 60%, #F5F2EC 100%)',
        }}
      >
        <HeroNav />

        <section
          ref={heroRef}
          className={`relative min-h-[100svh] ${
            isPortraitMode ? '' : 'lg:min-h-[200vh]'
          }`}
        >
          <div className="relative flex min-h-[100svh] items-start lg:sticky lg:top-0 lg:min-h-screen">
            <div className="mx-auto w-full max-w-[90vw] px-6 pb-16 pt-10 lg:pb-24">
              <div
                className={`grid grid-cols-1 items-start gap-12 ${
                  isPortraitMode ? '' : 'lg:grid-cols-[0.9fr_1.6fr]'
                }`}
              >
                <FadeContent duration={0.6} y={18} blur={false} className="min-w-0">
                  <div className="space-y-6">
                    <div className="inline-flex items-center gap-2 rounded-full border border-black/10 bg-white/60 px-3 py-1 text-xs uppercase tracking-[0.2em] text-[#7E8B97]">
                      Automated Research
                    </div>
                    <h1 className="text-4xl font-semibold leading-tight md:text-5xl">
                      {HERO_COPY.headline}
                    </h1>
                    {HERO_COPY.subhead ? (
                      <p className="max-w-xl text-base text-[#5D5A55] md:text-lg">
                        {HERO_COPY.subhead}
                      </p>
                    ) : null}
                    <div className="text-sm uppercase tracking-[0.22em] text-[#9FB1C2]">
                      {HERO_COPY.tagline}
                    </div>

                    <div className="flex flex-wrap items-center gap-3">
                      <GlareHover className="rounded-full">
                        <Button
                          className="h-12 rounded-full bg-[#C7AD96] px-7 text-[#2D2A26] shadow-[0_12px_28px_-14px_rgba(45,42,38,0.55)] transition-all duration-200 hover:-translate-y-0.5 hover:bg-[#D7C6AE]"
                          onClick={() => {
                            setCreateError(null)
                            setCreateDialogOpen(true)
                          }}
                        >
                          {HERO_COPY.primaryCta}
                        </Button>
                      </GlareHover>
                      <Button
                        variant="outline"
                        className="h-11 rounded-full border-black/15 bg-white/70 px-6 text-[#2D2A26] hover:bg-white"
                        onClick={() => {
                          setQuestError(null)
                          setQuestDialogOpen(true)
                        }}
                      >
                        <FolderOpen className="mr-2 h-4 w-4" />
                        {HERO_COPY.secondaryCta}
                      </Button>
                    </div>

                    <div className="space-y-1 text-xs text-[#7E8B97]">
                      <div>{HERO_COPY.supportLine}</div>
                      {currentVersion ? <div>{`DeepScientist v${currentVersion}`}</div> : null}
                    </div>
                  </div>
                </FadeContent>

                {!isPortraitMode ? (
                  <div className="relative min-w-0">
                    <HeroScene
                      progress={progress}
                      stageIndex={sceneStageIndex}
                      reducedMotion={reducedMotion}
                      isMobile={isMobile}
                    />
                  </div>
                ) : null}
              </div>
            </div>
            {!isPortraitMode ? (
              <HeroProgress
                progress={barProgress}
                stageIndex={scrollStage}
                className={`relative mt-8 w-full transition-opacity duration-300 lg:fixed lg:bottom-4 lg:left-0 lg:right-0 lg:mt-0 lg:z-[60] ${
                  showProgress ? 'opacity-100' : 'opacity-0'
                }`}
              />
            ) : null}
          </div>
        </section>

      </div>

      <CreateProjectDialog
        open={createDialogOpen}
        loading={creating}
        error={createError}
        onClose={() => setCreateDialogOpen(false)}
        onCreate={createAndOpen}
      />

      <OpenQuestDialog
        open={questDialogOpen}
        quests={quests}
        loading={questsLoading}
        error={questError}
        onClose={() => setQuestDialogOpen(false)}
        onOpenQuest={(questId) => {
          setQuestDialogOpen(false)
          navigate(`/projects/${questId}`)
        }}
        onDeleteQuest={deleteQuest}
        deletingQuestId={deletingQuestId}
      />
      <UpdateReminderDialog />
    </>
  )
}
