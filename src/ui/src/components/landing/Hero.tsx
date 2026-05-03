'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useReducedMotion } from 'framer-motion'
import { FolderOpen, Sparkles } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { CreateCopilotProjectDialog } from '@/components/projects/CreateCopilotProjectDialog'
import { CreateProjectDialog } from '@/components/projects/CreateProjectDialog'
import { ExperimentLaunchModeDialog } from '@/components/projects/ExperimentLaunchModeDialog'
import { OpenQuestDialog } from '@/components/projects/OpenQuestDialog'
import { BenchStoreDialog } from '@/components/landing/BenchStoreDialog'
import { Button } from '@/components/ui/button'
import { FadeContent, GlareHover } from '@/components/react-bits'
import { client } from '@/lib/api'
import { useMobileViewport } from '@/lib/hooks/useMobileViewport'
import { useI18n } from '@/lib/i18n'
import { filterProjectsVisibleQuests } from '@/lib/questVisibility'
import { useOnboardingStore } from '@/lib/stores/onboarding'
import { useUILanguageStore } from '@/lib/stores/ui-language'
import { runtimeVersion } from '@/lib/runtime/quest-runtime'
import { normalizeBuiltinRunnerName, runnerLabel } from '@/lib/runnerBranding'
import type { StartResearchTemplate } from '@/lib/startResearch'
import type { QuestMessageAttachmentDraft } from '@/lib/hooks/useQuestMessageAttachments'
import { getHeroBundle } from './hero-content'
import type { ConnectorAvailabilitySnapshot, QuestSummary } from '@/types'
import type { BenchEntry, BenchSetupPacket } from '@/lib/types/benchstore'
import { EntryCoachDialog } from './EntryCoachDialog'
import HeroNav from './HeroNav'
import HeroScene from './HeroScene'
import HeroProgress from './HeroProgress'
import { UpdateReminderDialog } from './UpdateReminderDialog'

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max)

export type LandingDialogRequest = 'quests' | 'copilot' | 'autonomous' | 'benchstore'

type ActiveLandingDialog = LandingDialogRequest | 'launch' | null

function sortQuests(items: QuestSummary[]) {
  return [...items].sort((left, right) => {
    const leftAt = Date.parse(left.updated_at || '')
    const rightAt = Date.parse(right.updated_at || '')
    return rightAt - leftAt
  })
}

function buildBenchstoreContextFromEntry(entry: BenchEntry | null | undefined, setupAgentLabel: string) {
  if (!entry) return null
  return {
    entry_id: entry.id,
    entry_name: entry.name,
    one_line: entry.one_line ?? null,
    task_description: entry.task_description ?? null,
    paper: entry.paper ?? {},
    capability_tags: entry.capability_tags ?? [],
    track_fit: entry.track_fit ?? [],
    task_mode: entry.task_mode ?? null,
    requires_execution: entry.requires_execution ?? null,
    requires_paper: entry.requires_paper ?? null,
    resources: entry.resources ?? {},
    environment: entry.environment ?? {},
    image_path: entry.image_path ?? null,
    image_url: entry.image_url ?? null,
    recommended_when: entry.recommended_when ?? null,
    not_recommended_when: entry.not_recommended_when ?? null,
    download: entry.download ?? {},
    dataset_download: entry.dataset_download ?? {},
    credential_requirements: entry.credential_requirements ?? {},
    compatibility: entry.compatibility ?? {},
    benchmark_local_path: entry.install_state?.local_path ?? null,
    setup_agent_label: setupAgentLabel,
    catalog_source_file: entry.source_file ?? null,
    risk_flags: entry.risk_flags ?? [],
    risk_notes: entry.risk_notes ?? [],
    integrity_level: entry.integrity_level ?? null,
    snapshot_status: entry.snapshot_status ?? null,
    support_level: entry.support_level ?? null,
    primary_outputs: entry.primary_outputs ?? [],
    launch_profiles: entry.launch_profiles ?? [],
    version: entry.version ?? null,
    commercial: entry.commercial ?? {},
    display: entry.display ?? {},
  }
}

function buildBenchstoreSuggestedFormFromEntry(entry: BenchEntry | null | undefined, locale: 'en' | 'zh') {
  if (!entry) return null
  return {
    title: `${entry.name} Autonomous Research`,
    goal:
      entry.task_description ||
      entry.one_line ||
      (locale === 'zh'
        ? `先评估并整理 benchmark「${entry.name}」的启动方案。`
        : `Evaluate and prepare the launch plan for benchmark "${entry.name}".`),
    baseline_urls: entry.download?.url || '',
    paper_urls: entry.paper?.url || '',
    need_research_paper: entry.requires_paper ?? true,
    user_language: locale,
  }
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(reader.error || new Error('Failed to read file.'))
    reader.onload = () => {
      const result = String(reader.result || '')
      const base64 = result.includes(',') ? result.split(',', 2)[1] : result
      resolve(base64)
    }
    reader.readAsDataURL(file)
  })
}

async function uploadLocalAttachmentsToQuest(questId: string, attachments: QuestMessageAttachmentDraft[] = []) {
  const draftIds: string[] = []
  for (const attachment of attachments) {
    if (attachment.status !== 'success' || !attachment.file) continue
    const contentBase64 = await fileToBase64(attachment.file)
    const payload = await client.uploadChatAttachment(questId, {
      draft_id: attachment.draftId,
      file_name: attachment.name,
      mime_type: attachment.contentType || undefined,
      content_base64: contentBase64,
    })
    if (payload.ok && payload.draft_id) {
      draftIds.push(String(payload.draft_id))
    }
  }
  return draftIds
}

async function importSetupAttachmentsToQuest(
  questId: string,
  sourceQuestId?: string | null,
  attachments: Array<Record<string, unknown>> = []
) {
  const normalizedAttachments = attachments.filter((item) => {
    const questRelativePath = String(item.questRelativePath || item.quest_relative_path || '').trim()
    const path = String(item.path || '').trim()
    return Boolean(questRelativePath || path)
  })
  if (!sourceQuestId || normalizedAttachments.length === 0) return []
  const payload = await client.importQuestChatAttachments(questId, {
    source_quest_id: sourceQuestId,
    attachments: normalizedAttachments.map((item) => ({
      name: item.label || item.name || item.file_name,
      file_name: item.label || item.file_name || item.name,
      content_type: item.contentType || item.content_type || item.mime_type || null,
      quest_relative_path: item.questRelativePath || item.quest_relative_path || null,
      path: item.path || null,
    })),
  })
  if (!payload.ok) {
    throw new Error(payload.message || 'Failed to import launch attachments.')
  }
  return (payload.attachments || [])
    .map((item) => String(item.draft_id || '').trim())
    .filter(Boolean)
}

export default function Hero(props: {
  dialogRequest?: LandingDialogRequest | null
  onDialogRequestConsumed?: () => void
}) {
  const navigate = useNavigate()
  const { locale } = useI18n()
  const hero = useMemo(() => getHeroBundle(locale), [locale])
  const saveLanguagePreference = useUILanguageStore((state) => state.saveLanguagePreference)
  const {
    hydrated: onboardingHydrated,
    firstRunHandled,
    neverRemind,
    startTutorial,
    skipFirstRun,
    neverShowAgain,
  } = useOnboardingStore((state) => ({
    hydrated: state.hydrated,
    firstRunHandled: state.firstRunHandled,
    neverRemind: state.neverRemind,
    startTutorial: state.startTutorial,
    skipFirstRun: state.skipFirstRun,
    neverShowAgain: state.neverShowAgain,
  }))
  const heroRef = useRef<HTMLElement | null>(null)
  const prefersReducedMotion = useReducedMotion()
  const reducedMotion = prefersReducedMotion ?? false
  const [progress, setProgress] = useState(0)
  const isMobile = useMobileViewport()
  const isPortraitMode = useMobileViewport()
  const [showProgress, setShowProgress] = useState(true)
  const progressRef = useRef(0)
  const targetRef = useRef(0)
  const rafRef = useRef<number | null>(null)
  const [activeDialog, setActiveDialog] = useState<ActiveLandingDialog>(null)

  useEffect(() => {
    let active = true
    void client.configDocument('config').then((payload) => {
      if (!active) return
      const structured = payload.meta?.structured_config && typeof payload.meta.structured_config === 'object'
        ? (payload.meta.structured_config as Record<string, unknown>)
        : {}
      setActiveRunnerName(normalizeBuiltinRunnerName(structured.default_runner))
    }).catch(() => {})
    return () => {
      active = false
    }
  }, [])
  const [connectorAvailability, setConnectorAvailability] = useState<ConnectorAvailabilitySnapshot | null>(null)
  const [connectorAvailabilityResolved, setConnectorAvailabilityResolved] = useState(false)
  const [entryCoachDismissed, setEntryCoachDismissed] = useState(false)
  const [quests, setQuests] = useState<QuestSummary[]>([])
  const [questsLoading, setQuestsLoading] = useState(false)
  const [questsError, setQuestsError] = useState<string | null>(null)
  const [deletingQuestId, setDeletingQuestId] = useState<string | null>(null)
  const [autonomousCreating, setAutonomousCreating] = useState(false)
  const [autonomousError, setAutonomousError] = useState<string | null>(null)
  const [benchSetupPacket, setBenchSetupPacket] = useState<BenchSetupPacket | null>(null)
  const [activeRunnerName, setActiveRunnerName] = useState(() => normalizeBuiltinRunnerName("codex"))
  const [setupQuestId, setSetupQuestId] = useState<string | null>(null)
  const [setupQuestCreating, setSetupQuestCreating] = useState(false)
  const [copilotSeed, setCopilotSeed] = useState<{
    title?: string
    message?: string
    setupQuestId?: string | null
    setupAttachments?: Array<Record<string, unknown>>
    localAttachments?: QuestMessageAttachmentDraft[]
  } | null>(null)
  const currentVersion = useMemo(() => runtimeVersion(), [])
  const landingModalOpen = activeDialog !== null

  useEffect(() => {
    document.body.classList.add('font-project')
    return () => document.body.classList.remove('font-project')
  }, [])

  useEffect(() => {
    if (!props.dialogRequest) {
      return
    }
    setActiveDialog(props.dialogRequest)
    props.onDialogRequestConsumed?.()
  }, [props.dialogRequest, props.onDialogRequestConsumed])

  useEffect(() => {
    if (!onboardingHydrated) {
      return
    }
    let active = true
    void client
      .connectorsAvailability()
      .then((payload) => {
        if (!active) return
        setConnectorAvailability(payload)
      })
      .catch(() => {
        if (!active) return
        setConnectorAvailability(null)
      })
      .finally(() => {
        if (active) {
          setConnectorAvailabilityResolved(true)
        }
      })
    return () => {
      active = false
    }
  }, [onboardingHydrated])

  const connectorCoachMode = useMemo(() => {
    if (!connectorAvailability?.should_recommend_binding) {
      return null
    }
    if (!connectorAvailability.has_enabled_external_connector) {
      return 'no_enabled' as const
    }
    const hasDeliveryTarget = connectorAvailability.available_connectors.some(
      (item) => item.enabled && item.has_delivery_target
    )
    if (!hasDeliveryTarget) {
      return 'no_target' as const
    }
    return 'recommended' as const
  }, [connectorAvailability])

  useEffect(() => {
    if (activeDialog !== 'quests') {
      return
    }
    let alive = true
    setQuestsLoading(true)
    void client
      .quests()
      .then((payload) => {
        if (!alive) return
        setQuests(sortQuests(filterProjectsVisibleQuests(payload)))
        setQuestsError(null)
      })
      .catch((caught) => {
        if (!alive) return
        setQuestsError(caught instanceof Error ? caught.message : 'Failed to load quests.')
      })
      .finally(() => {
        if (alive) {
          setQuestsLoading(false)
        }
      })
    return () => {
      alive = false
    }
  }, [activeDialog])

  useEffect(() => {
    if (activeDialog !== 'autonomous') {
      setAutonomousCreating(false)
      setAutonomousError(null)
    }
  }, [activeDialog])

  const cleanupSetupQuest = useCallback(async () => {
    if (!setupQuestId) return
    const questId = setupQuestId
    setSetupQuestId(null)
    try {
      await client.deleteQuest(questId)
    } catch {
      return
    }
  }, [setupQuestId])

  const openBenchStoreDialog = useCallback(() => {
    setBenchSetupPacket(null)
    if (setupQuestId) {
      void cleanupSetupQuest()
    }
    window.setTimeout(() => {
      setActiveDialog('benchstore')
    }, 120)
  }, [cleanupSetupQuest, setupQuestId])

  const ensureSetupQuest = useCallback(
    async (args: {
      message: string
      source: 'benchstore' | 'manual'
      form?: StartResearchTemplate | null
      setupPacket?: BenchSetupPacket | null
      entry?: BenchEntry | null
      attachments?: QuestMessageAttachmentDraft[]
      createOnly?: boolean
    }) => {
      const normalizedMessage = args.message.trim()
      const pendingAttachments = (args.attachments || []).filter(
        (item) => item.status === 'success' && item.file
      )
      if (!normalizedMessage && pendingAttachments.length === 0 && !args.createOnly) return null
      const suggestedForm =
        args.setupPacket?.suggested_form && typeof args.setupPacket.suggested_form === 'object'
          ? args.setupPacket.suggested_form
          : args.form
            ? { ...args.form }
            : args.source === 'benchstore'
              ? buildBenchstoreSuggestedFormFromEntry(args.entry, locale)
              : null
      const benchmarkContext =
        args.setupPacket?.launch_payload?.startup_contract &&
        typeof args.setupPacket.launch_payload.startup_contract === 'object' &&
        typeof args.setupPacket.launch_payload.startup_contract.benchstore_context === 'object'
          ? args.setupPacket.launch_payload.startup_contract.benchstore_context
          : args.source === 'benchstore'
            ? buildBenchstoreContextFromEntry(args.entry)
            : null

      const uploadAttachmentDrafts = async (questId: string) => {
        const uploadedDraftIds: string[] = []
        for (const attachment of pendingAttachments) {
          if (!attachment.file) continue
          const contentBase64 = await fileToBase64(attachment.file)
          const payload = await client.uploadChatAttachment(questId, {
            draft_id: attachment.draftId,
            file_name: attachment.name,
            mime_type: attachment.contentType || undefined,
            content_base64: contentBase64,
          })
          if (payload.ok) {
            uploadedDraftIds.push(attachment.draftId)
          }
        }
        return uploadedDraftIds
      }

      if (setupQuestId) {
        if (!args.createOnly) {
          const attachmentDraftIds = await uploadAttachmentDrafts(setupQuestId)
          await client.sendChat(
            setupQuestId,
            normalizedMessage,
            undefined,
            undefined,
            attachmentDraftIds
          )
        }
        return setupQuestId
      }

      setSetupQuestCreating(true)
      try {
        const titleBase =
          args.setupPacket?.project_title ||
          args.entry?.name ||
          args.form?.title ||
          (locale === 'zh' ? '启动协助' : 'Start setup')
        const nextIdPayload = await client.nextQuestId()
        const setupQuestIdValue = `B-${String(nextIdPayload?.quest_id || '').trim() || '001'}`
        const result = await client.createQuestWithOptions({
          goal: normalizedMessage,
          title: `SetupAgent · ${titleBase}`,
          quest_id: setupQuestIdValue,
          source: 'web-react',
          auto_start: !args.createOnly && pendingAttachments.length === 0 && Boolean(normalizedMessage),
          initial_message: !args.createOnly && pendingAttachments.length === 0 ? normalizedMessage : undefined,
          auto_bind_latest_connectors: false,
          startup_contract: {
            schema_version: 1,
            workspace_mode: 'copilot',
            launch_mode: 'custom',
            custom_profile: 'freeform',
            project_display: {
              template: 'blank',
              accent_color: 'mist',
              background_style: 'cloud',
            },
            start_setup_session: {
              source: args.source,
              locale,
              benchmark_context: benchmarkContext,
              suggested_form: suggestedForm,
            },
          },
        })
        setSetupQuestId(result.snapshot.quest_id)
        if (!args.createOnly && pendingAttachments.length > 0) {
          const attachmentDraftIds = await uploadAttachmentDrafts(result.snapshot.quest_id)
          if (attachmentDraftIds.length > 0) {
            await client.sendChat(
              result.snapshot.quest_id,
              normalizedMessage || (locale === 'zh' ? '请结合这些附件整理启动规划。' : 'Please prepare the launch plan from these attachments.'),
              undefined,
              undefined,
              attachmentDraftIds
            )
          }
        }
        return result.snapshot.quest_id
      } finally {
        setSetupQuestCreating(false)
      }
    },
    [locale, setupQuestId]
  )

  const shouldShowConnectorCoach = connectorAvailabilityResolved && connectorCoachMode !== null
  const shouldShowTutorialCoach = onboardingHydrated && !firstRunHandled && !neverRemind
  const entryCoachOpen =
    !entryCoachDismissed &&
    !landingModalOpen &&
    (shouldShowConnectorCoach || shouldShowTutorialCoach)

  useEffect(() => {
    if (isPortraitMode) {
      targetRef.current = 0
      progressRef.current = 0
      setProgress(0)
      setShowProgress(false)
      return
    }

    setShowProgress(true)

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

    const handleWheel = (event: WheelEvent) => {
      if (landingModalOpen || entryCoachOpen) {
        return
      }
      if (Math.abs(event.deltaY) < 0.5) {
        return
      }
      event.preventDefault()
      const delta = event.deltaY
      const nextTarget = clamp(targetRef.current + delta * 0.0012, 0, 1)
      targetRef.current = nextTarget
      scheduleTick()
    }

    window.addEventListener('wheel', handleWheel, { passive: false })

    return () => {
      window.removeEventListener('wheel', handleWheel)
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
  }, [entryCoachOpen, landingModalOpen, reducedMotion, isPortraitMode])

  const scrollStage = useMemo(() => {
    if (progress < 0.25) return 0
    if (progress < 0.5) return 1
    if (progress < 0.75) return 2
    return 3
  }, [progress])

  const sceneStageIndex = scrollStage
  const barProgress = progress

  useEffect(() => {
    const htmlStyle = document.documentElement.style
    const bodyStyle = document.body.style
    const previousHtmlOverflowY = htmlStyle.overflowY
    const previousHtmlOverflowX = htmlStyle.overflowX
    const previousBodyOverflow = bodyStyle.overflow
    const previousBodyOverflowX = bodyStyle.overflowX
    const previousBodyOverflowY = bodyStyle.overflowY

    const shouldLockBackground = landingModalOpen || entryCoachOpen || !isPortraitMode
    htmlStyle.overflowX = 'hidden'
    htmlStyle.overflowY = shouldLockBackground ? 'hidden' : 'auto'
    bodyStyle.overflow = shouldLockBackground ? 'hidden' : 'auto'
    bodyStyle.overflowX = 'hidden'
    bodyStyle.overflowY = shouldLockBackground ? 'hidden' : 'auto'

    return () => {
      htmlStyle.overflowY = previousHtmlOverflowY
      htmlStyle.overflowX = previousHtmlOverflowX
      bodyStyle.overflow = previousBodyOverflow
      bodyStyle.overflowX = previousBodyOverflowX
      bodyStyle.overflowY = previousBodyOverflowY
    }
  }, [entryCoachOpen, landingModalOpen, isPortraitMode])

  return (
    <>
      <div
        className="relative min-h-[100svh] overflow-x-hidden bg-[#F5F2EC] text-[#2D2A26]"
        style={{
          backgroundImage:
            'radial-gradient(900px circle at 15% 15%, rgba(185, 199, 214, 0.28), transparent 60%), radial-gradient(700px circle at 85% 0%, rgba(215, 198, 174, 0.32), transparent 58%), linear-gradient(180deg, #F5F2EC 0%, #EEE7DD 60%, #F5F2EC 100%)',
        }}
      >
        <HeroNav onOpenBenchStore={openBenchStoreDialog} />

        <section
          ref={heroRef}
          className="relative min-h-[100svh]"
        >
          <div className="relative flex min-h-[100svh] items-start lg:min-h-screen">
            <div className="mx-auto w-full max-w-[90vw] px-6 pb-16 pt-10 lg:pb-24">
              <div
                className={`grid grid-cols-1 items-start gap-12 ${
                  isPortraitMode ? '' : 'lg:grid-cols-[0.9fr_1.6fr]'
                }`}
              >
                <FadeContent duration={0.6} y={18} blur={false} className="min-w-0">
                  <div className="space-y-6" data-onboarding-id="landing-hero">
                    <div className="inline-flex items-center gap-2 rounded-full border border-black/10 bg-white/60 px-3 py-1 text-xs uppercase tracking-[0.2em] text-[#7E8B97]">
                      {locale === 'zh' ? '自动化科研' : 'Automated Research'}
                    </div>
                    <h1 className="text-4xl font-semibold leading-tight md:text-5xl">
                      {hero.copy.headline}
                    </h1>
                    {hero.copy.subhead ? (
                      <p className="max-w-xl text-base text-[#5D5A55] md:text-lg">
                        {hero.copy.subhead}
                      </p>
                    ) : null}
                    <div className="text-sm uppercase tracking-[0.22em] text-[#9FB1C2]">
                      {hero.copy.tagline}
                    </div>

                    <div className="flex flex-wrap items-center gap-3" data-onboarding-id="landing-entry-actions">
                      <GlareHover className="rounded-full">
                        <Button
                          className="h-12 rounded-full bg-[#C7AD96] px-7 text-[#2D2A26] shadow-[0_12px_28px_-14px_rgba(45,42,38,0.55)] transition-all duration-200 hover:-translate-y-0.5 hover:bg-[#D7C6AE]"
                          onClick={() => {
                            window.setTimeout(() => {
                              setActiveDialog(isPortraitMode ? 'autonomous' : 'launch')
                            }, 120)
                          }}
                          data-onboarding-id="landing-start-research"
                        >
                          {hero.copy.primaryCta}
                        </Button>
                      </GlareHover>
                      <Button
                        variant="outline"
                        className="h-11 rounded-full border-black/15 bg-white/70 px-6 text-[#2D2A26] hover:bg-white"
                        onClick={() => setActiveDialog('quests')}
                      >
                        <FolderOpen className="mr-2 h-4 w-4" />
                        {hero.copy.secondaryCta}
                      </Button>
                      <Button
                        variant="outline"
                        className="h-11 rounded-full border-black/15 bg-[rgba(246,241,235,0.86)] px-6 text-[#2D2A26] shadow-[0_16px_36px_-24px_rgba(57,52,46,0.45)] hover:bg-white"
                        onClick={openBenchStoreDialog}
                        data-onboarding-id="landing-benchstore"
                      >
                        <Sparkles className="mr-2 h-4 w-4" />
                        BenchStore
                      </Button>
                    </div>

                    <div className="space-y-1 text-xs text-[#7E8B97]">
                      <div>{hero.copy.supportLine}</div>
                      <div>
                        {hero.copy.moreContentLine}{' '}
                        <a
                          href={hero.copy.moreContentUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="underline decoration-[#9FB1C2] underline-offset-4 transition-colors hover:text-[#5D5A55]"
                        >
                          {hero.copy.moreContentUrl}
                        </a>
                        .
                      </div>
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
                locale={locale}
                className={`relative mt-8 w-full transition-opacity duration-300 lg:fixed lg:bottom-4 lg:left-0 lg:right-0 lg:mt-0 lg:z-[60] ${
                  showProgress ? 'opacity-100' : 'opacity-0'
                }`}
              />
            ) : null}
          </div>
        </section>

      </div>

      <ExperimentLaunchModeDialog
        open={activeDialog === 'launch'}
        locale={locale}
        onClose={() => setActiveDialog(null)}
        onSelectMode={(mode) => {
          setActiveDialog(mode === 'copilot' ? 'copilot' : 'autonomous')
        }}
      />
      <OpenQuestDialog
        open={activeDialog === 'quests'}
        quests={quests}
        loading={questsLoading}
        error={questsError}
        deletingQuestId={deletingQuestId}
        onClose={() => setActiveDialog(null)}
        onOpenQuest={(questId) => {
          setActiveDialog(null)
          navigate(`/projects/${questId}`)
        }}
        onDeleteQuest={async (questId) => {
          setDeletingQuestId(questId)
          try {
            await client.deleteQuest(questId)
            setQuests((current) => current.filter((item) => item.quest_id !== questId))
            setQuestsError(null)
          } catch (caught) {
            setQuestsError(caught instanceof Error ? caught.message : 'Failed to delete quest.')
          } finally {
            setDeletingQuestId(null)
          }
        }}
      />
      <BenchStoreDialog
        open={activeDialog === 'benchstore'}
        locale={locale}
        onClose={() => setActiveDialog(null)}
        setupQuestId={setupQuestId}
        setupQuestCreating={setupQuestCreating}
        onRequestSetupAgent={async ({ message, entry, setupPacket, attachments, createOnly }) => {
          await ensureSetupQuest({
            message,
            source: 'benchstore',
            entry: entry ?? null,
            setupPacket: setupPacket ?? benchSetupPacket,
            attachments,
            createOnly,
          })
        }}
        onStartWithSetupPacket={async (setupPacket) => {
          setBenchSetupPacket(setupPacket)
          setAutonomousError(null)
          if (setupQuestId) {
            void cleanupSetupQuest()
          }
          setActiveDialog('autonomous')
        }}
      />
      <CreateCopilotProjectDialog
        open={activeDialog === 'copilot'}
        onClose={() => {
          setCopilotSeed(null)
          setBenchSetupPacket(null)
          setActiveDialog(null)
          void cleanupSetupQuest()
        }}
        onBack={() => {
          setCopilotSeed(null)
          setBenchSetupPacket(null)
          setActiveDialog('autonomous')
          void cleanupSetupQuest()
        }}
        initialTitle={copilotSeed?.title || ''}
        initialMessage={copilotSeed?.message || ''}
        initialSetupQuestId={copilotSeed?.setupQuestId || null}
        initialSetupAttachments={copilotSeed?.setupAttachments || []}
        initialLocalAttachments={copilotSeed?.localAttachments || []}
        onCreated={(questId) => {
          setCopilotSeed(null)
          setActiveDialog(null)
          setBenchSetupPacket(null)
          void cleanupSetupQuest()
          navigate(`/projects/${questId}`)
        }}
      />
      <CreateProjectDialog
        open={activeDialog === 'autonomous'}
        onClose={() => {
          setBenchSetupPacket(null)
          setActiveDialog(null)
          void cleanupSetupQuest()
        }}
        onBack={() => {
          setBenchSetupPacket(null)
          setActiveDialog('launch')
          void cleanupSetupQuest()
        }}
        loading={autonomousCreating}
        error={autonomousError}
        setupPacket={benchSetupPacket}
        setupQuestId={setupQuestId}
        setupQuestCreating={setupQuestCreating}
        onRequestSetupAgent={async ({ message, form, setupPacket, attachments, createOnly }) => {
          await ensureSetupQuest({
            message,
            source: setupPacket ? 'benchstore' : 'manual',
            form,
            setupPacket,
            attachments,
            createOnly,
          })
        }}
        onSwitchToCopilot={async ({ title, message, setupQuestId, setupAttachments, localAttachments }) => {
          setCopilotSeed({
            title,
            message,
            setupQuestId,
            setupAttachments: (setupAttachments || []).map((item) => ({ ...item })),
            localAttachments: [...(localAttachments || [])],
          })
          setActiveDialog('copilot')
        }}
        onOpenBenchStore={openBenchStoreDialog}
        onCreate={async (payload) => {
          if (!payload.goal.trim()) {
            return
          }
          setAutonomousCreating(true)
          setAutonomousError(null)
          try {
            const result = await client.createQuestWithOptions({
              goal: payload.goal.trim(),
              title: payload.title.trim() || undefined,
              quest_id: payload.quest_id?.trim() || undefined,
              source: 'web-react',
              auto_start: false,
              auto_bind_latest_connectors: false,
              requested_connector_bindings: payload.requested_connector_bindings,
              requested_baseline_ref: payload.requested_baseline_ref ?? undefined,
              startup_contract: payload.startup_contract ?? undefined,
            })
            const importedDraftIds = await importSetupAttachmentsToQuest(
              result.snapshot.quest_id,
              payload.launch_materials?.setup_quest_id || null,
              (payload.launch_materials?.setup_attachments || []).map((item) => ({ ...item }))
            )
            const localDraftIds = await uploadLocalAttachmentsToQuest(
              result.snapshot.quest_id,
              payload.launch_materials?.local_attachments || []
            )
            await client.sendChat(
              result.snapshot.quest_id,
              payload.goal.trim(),
              undefined,
              undefined,
              [...importedDraftIds, ...localDraftIds]
            )
            setActiveDialog(null)
            setBenchSetupPacket(null)
            setCopilotSeed(null)
            await cleanupSetupQuest()
            navigate(`/projects/${result.snapshot.quest_id}`)
          } catch (caught) {
            setAutonomousError(caught instanceof Error ? caught.message : 'Failed to create quest.')
          } finally {
            setAutonomousCreating(false)
          }
        }}
      />
      <UpdateReminderDialog />
      <EntryCoachDialog
        open={entryCoachOpen}
        locale={locale}
        connectorMode={connectorCoachMode || 'recommended'}
        showConnectorStep={shouldShowConnectorCoach}
        showTutorialStep={shouldShowTutorialCoach}
        onClose={() => setEntryCoachDismissed(true)}
        onSetLanguage={(language) => {
          void saveLanguagePreference(language)
        }}
        onOpenConnectorSettings={() => {
          setEntryCoachDismissed(true)
          navigate('/settings/connector', { state: { configName: 'connectors' } })
        }}
        onStartTutorial={(language) => {
          setEntryCoachDismissed(true)
          startTutorial(language, '/', 'auto')
        }}
        onSkipTutorial={() => {
          skipFirstRun()
        }}
        onNeverShowTutorial={() => {
          neverShowAgain()
        }}
      />
    </>
  )
}
