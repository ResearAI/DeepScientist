'use client'

import * as React from 'react'
import { animate, motion, useMotionValue, useReducedMotion } from 'framer-motion'
import { FolderOpen, Loader2, PanelLeft, Plus, Sparkles, X } from 'lucide-react'
import type {
  AiManusChatActions,
  AiManusChatMeta,
  CopilotPrefill,
  CopilotSuggestionItem,
  CopilotSuggestionPayload,
} from '@/lib/plugins/ai-manus/view-types'
import OrbitLogoStatus from '@/lib/plugins/ai-manus/components/OrbitLogoStatus'
import type { ChatSurface } from '@/lib/types/chat-events'
import { Noise } from '@/components/react-bits'
import RotatingText from '@/components/RotatingText'
import { cn } from '@/lib/utils'
import { COPILOT_FILES_ENABLED } from '@/lib/feature-flags'
import {
  COPILOT_DOCK_DEFAULTS,
  clampCopilotDockWidth,
  getCopilotDockMaxWidth,
  type CopilotDockSide,
  type CopilotDockState,
} from '@/hooks/useCopilotDockState'
import { useTabsStore } from '@/lib/stores/tabs'
import { useFileTreeStore } from '@/lib/stores/file-tree'
import type { Tab } from '@/lib/types/tab'
import { BUILTIN_PLUGINS } from '@/lib/types/plugin'
import { useMaxEntitlement } from '@/lib/hooks/useMaxEntitlement'
import { useI18n } from '@/lib/i18n/useI18n'
import { useWorkspaceSurfaceStore, type WorkspaceTabViewState } from '@/lib/stores/workspace-surface'
import { getWorkspaceContentKind, getWorkspaceContentKindBadge } from '@/lib/workspace/content-meta'

const CopilotDockHeaderPortalContext = React.createContext<HTMLElement | null>(null)

export const useCopilotDockHeaderPortal = () => React.useContext(CopilotDockHeaderPortalContext)

const CopilotDockCallbacksContext = React.createContext<{
  onActionsChange: (actions: AiManusChatActions | null) => void
  onMetaChange: (meta: AiManusChatMeta) => void
  onHeaderExtraChange: (content: React.ReactNode | null) => void
} | null>(null)

export const useCopilotDockCallbacks = () => React.useContext(CopilotDockCallbacksContext)

type CopilotDockOverlayProps = {
  projectId: string
  stageWidth: number
  state: CopilotDockState
  readOnly?: boolean
  surfaceMode?: ChatSurface
  prefill?: CopilotPrefill | null
  headerContent?: React.ReactNode
  bodyContent?: React.ReactNode
  hideNewChat?: boolean
  hideHistory?: boolean
  hideFixWithAi?: boolean
  forceOpen?: boolean
  visible?: boolean
  keepAlive?: boolean
  onClose: () => void
  hideHeaderOrbit?: boolean
  setSide: (side: CopilotDockSide) => void
  toggleSide: () => void
  setWidth: (width: number) => void
  setMaxRatio?: (maxRatio: number) => void
  onActionsChange?: (actions: AiManusChatActions | null) => void
}

const SPRING = {
  type: 'tween',
  ease: [0.4, 0, 0.2, 1],
} as const

const WELCOME_WIDE_RATIO = COPILOT_DOCK_DEFAULTS.welcomeMaxRatio
const WELCOME_STAGE_MIN_CONTENT = COPILOT_DOCK_DEFAULTS.welcomeStageMinContent
const isCopilotMetaEqual = (prev: AiManusChatMeta | null, next: AiManusChatMeta) => {
  if (!prev) return false
  return (
    prev.threadId === next.threadId &&
    prev.historyOpen === next.historyOpen &&
    prev.isResponding === next.isResponding &&
    prev.toolCount === next.toolCount &&
    prev.ready === next.ready &&
    prev.isRestoring === next.isRestoring &&
    prev.restoreAttempted === next.restoreAttempted &&
    prev.hasHistory === next.hasHistory &&
    prev.error === next.error &&
    prev.title === next.title &&
    prev.statusText === next.statusText &&
    prev.statusPrevText === next.statusPrevText &&
    prev.statusKey === next.statusKey &&
    prev.toolPanelVisible === next.toolPanelVisible &&
    prev.toolToggleVisible === next.toolToggleVisible &&
    prev.attachmentsDrawerOpen === next.attachmentsDrawerOpen &&
    prev.fixWithAiRunning === next.fixWithAiRunning
  )
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function getFileLabel(tab: Tab): string {
  return (
    tab.context.resourceName ||
    tab.context.resourcePath ||
    tab.title ||
    'this file'
  )
}

function isNotebookTab(tab: Tab): boolean {
  return tab.context.type === 'notebook'
}

function buildSuggestionPayload(args: {
  tab: Tab
  t: (key: string, variables?: Record<string, string | number>, fallback?: string) => string
  viewState?: WorkspaceTabViewState | null
  activeReference?: {
    selectedText?: string
    pageNumber?: number
    markdownExcerpt?: string
  } | null
}): CopilotSuggestionPayload | null {
  const { tab, t, viewState, activeReference } = args
  if (tab.context.type !== 'file' && tab.context.type !== 'notebook') return null

  const fileLabel = getFileLabel(tab)
  const title = t('copilot_suggestions_title')
  const contentKind = getWorkspaceContentKind(tab, viewState || undefined)
  const pageNumber = activeReference?.pageNumber ?? viewState?.pageNumber
  const promptVars = {
    name: fileLabel,
    page: pageNumber ?? '',
    quote:
      (activeReference?.selectedText || activeReference?.markdownExcerpt || '')
        .replace(/\s+/g, ' ')
        .trim()
        .slice(0, 160),
  }

  if (contentKind === 'pdf') {
    const subtitle = activeReference?.selectedText
      ? t('copilot_suggestions_pdf_quote_subtitle', { page: pageNumber ?? '' })
      : t('copilot_suggestions_pdf_subtitle')
    return {
      tabId: tab.id,
      title,
      subtitle,
      items: activeReference?.selectedText
        ? [
            {
              label: t('copilot_suggestion_pdf_explain_label'),
              prompt: t('copilot_suggestion_pdf_explain_prompt', promptVars),
            },
            {
              label: t('copilot_suggestion_pdf_context_label'),
              prompt: t('copilot_suggestion_pdf_context_prompt', promptVars),
            },
            {
              label: t('copilot_suggestion_pdf_review_label'),
              prompt: t('copilot_suggestion_pdf_review_prompt', promptVars),
            },
            {
              label: t('copilot_suggestion_pdf_evidence_label'),
              prompt: t('copilot_suggestion_pdf_evidence_prompt', promptVars),
            },
          ]
        : [
            {
              label: t('copilot_suggestion_pdf_summary_label'),
              prompt: t('copilot_suggestion_pdf_summary_prompt', promptVars),
            },
            {
              label: t('copilot_suggestion_pdf_claims_label'),
              prompt: t('copilot_suggestion_pdf_claims_prompt', promptVars),
            },
            {
              label: t('copilot_suggestion_pdf_weakness_label'),
              prompt: t('copilot_suggestion_pdf_weakness_prompt', promptVars),
            },
            {
              label: t('copilot_suggestion_pdf_annotation_label'),
              prompt: t('copilot_suggestion_pdf_annotation_prompt', promptVars),
            },
          ],
    }
  }

  if (contentKind === 'latex') {
    const hasCompileErrors = (viewState?.diagnostics?.errors || 0) > 0
    return {
      tabId: tab.id,
      title,
      subtitle: hasCompileErrors
        ? t('copilot_suggestions_latex_error_subtitle')
        : t('copilot_suggestions_latex_subtitle'),
      items: [
        {
          label: t('copilot_suggestion_latex_fix_label'),
          prompt: t('copilot_suggestion_latex_fix_prompt', promptVars),
        },
        {
          label: t('copilot_suggestion_latex_citation_label'),
          prompt: t('copilot_suggestion_latex_citation_prompt', promptVars),
        },
        {
          label: t('copilot_suggestion_latex_ref_label'),
          prompt: t('copilot_suggestion_latex_ref_prompt', promptVars),
        },
        {
          label: t('copilot_suggestion_latex_structure_label'),
          prompt: t('copilot_suggestion_latex_structure_prompt', promptVars),
        },
      ],
    }
  }

  if (contentKind === 'html') {
    const isRenderedMode = viewState?.documentMode === 'rendered'
    return {
      tabId: tab.id,
      title,
      subtitle: isRenderedMode
        ? t('copilot_suggestions_html_rendered_subtitle')
        : t('copilot_suggestions_html_source_subtitle'),
      items: [
        {
          label: t('copilot_suggestion_html_summary_label'),
          prompt: t('copilot_suggestion_html_summary_prompt', promptVars),
        },
        {
          label: t('copilot_suggestion_html_structure_label'),
          prompt: t('copilot_suggestion_html_structure_prompt', promptVars),
        },
        {
          label: t('copilot_suggestion_html_accessibility_label'),
          prompt: t('copilot_suggestion_html_accessibility_prompt', promptVars),
        },
        {
          label: t('copilot_suggestion_html_source_label'),
          prompt: t('copilot_suggestion_html_source_prompt', promptVars),
        },
      ],
    }
  }

  if (contentKind === 'mdx') {
    return {
      tabId: tab.id,
      title,
      subtitle: t('copilot_suggestions_mdx_subtitle'),
      items: [
        {
          label: t('copilot_suggestion_mdx_summary_label'),
          prompt: t('copilot_suggestion_mdx_summary_prompt', promptVars),
        },
        {
          label: t('copilot_suggestion_mdx_structure_label'),
          prompt: t('copilot_suggestion_mdx_structure_prompt', promptVars),
        },
        {
          label: t('copilot_suggestion_mdx_static_label'),
          prompt: t('copilot_suggestion_mdx_static_prompt', promptVars),
        },
      ],
    }
  }

  if (contentKind === 'markdown') {
    return {
      tabId: tab.id,
      title,
      subtitle: t('copilot_suggestions_markdown_subtitle'),
      items: [
        {
          label: t('copilot_suggestion_markdown_summary_label'),
          prompt: t('copilot_suggestion_markdown_summary_prompt', promptVars),
        },
        {
          label: t('copilot_suggestion_markdown_outline_label'),
          prompt: t('copilot_suggestion_markdown_outline_prompt', promptVars),
        },
        {
          label: t('copilot_suggestion_markdown_logic_label'),
          prompt: t('copilot_suggestion_markdown_logic_prompt', promptVars),
        },
      ],
    }
  }

  if (isNotebookTab(tab)) {
    return {
      tabId: tab.id,
      title,
      subtitle: t('copilot_suggestions_notebook_subtitle'),
      items: [
        {
          label: t('copilot_suggestion_notebook_summary_label'),
          prompt: t('copilot_suggestion_notebook_summary_prompt', promptVars),
        },
        {
          label: t('copilot_suggestion_notebook_assumptions_label'),
          prompt: t('copilot_suggestion_notebook_assumptions_prompt', promptVars),
        },
        {
          label: t('copilot_suggestion_notebook_experiments_label'),
          prompt: t('copilot_suggestion_notebook_experiments_prompt', promptVars),
        },
        {
          label: t('copilot_suggestion_notebook_risks_label'),
          prompt: t('copilot_suggestion_notebook_risks_prompt', promptVars),
        },
      ],
    }
  }

  return {
    tabId: tab.id,
    title,
    subtitle: t('copilot_suggestions_file_subtitle'),
    items: [
      {
        label: t('copilot_suggestion_file_summary_label'),
        prompt: t('copilot_suggestion_file_summary_prompt', promptVars),
      },
      {
        label: t('copilot_suggestion_file_note_label'),
        prompt: t('copilot_suggestion_file_note_prompt', promptVars),
      },
      {
        label: t('copilot_suggestion_file_risks_label'),
        prompt: t('copilot_suggestion_file_risks_prompt', promptVars),
      },
      {
        label: t('copilot_suggestion_file_refactor_label'),
        prompt: t('copilot_suggestion_file_refactor_prompt', promptVars),
      },
    ],
  }
}

function getSnapDuration(distancePx: number) {
  return clampNumber(distancePx / 900, 0.28, 0.82)
}

type CopilotHeaderBadge = {
  key: string
  label: string
  tone: 'pdf' | 'latex' | 'markdown' | 'html' | 'neutral' | 'attention'
}

export function CopilotDockOverlay({
  projectId,
  stageWidth,
  state,
  readOnly,
  surfaceMode = 'copilot',
  prefill,
  headerContent,
  bodyContent,
  hideNewChat,
  hideHistory,
  hideFixWithAi = false,
  forceOpen,
  visible,
  keepAlive = true,
  onClose,
  hideHeaderOrbit = false,
  setSide,
  setWidth,
  setMaxRatio,
  onActionsChange,
}: CopilotDockOverlayProps) {
  const { t } = useI18n('workspace')
  const readOnlyMode = Boolean(readOnly)
  const maxEntitlement = useMaxEntitlement('copilot.use')
  const copilotLocked = !maxEntitlement.isEntitlementLoading && !maxEntitlement.isMaxEntitled
  const prefersReducedMotion = useReducedMotion()

  const edgeInset = COPILOT_DOCK_DEFAULTS.edgeInset
  const gap = COPILOT_DOCK_DEFAULTS.gap
  const minWidth = COPILOT_DOCK_DEFAULTS.minWidth

  const dragBoundsRef = React.useRef<HTMLDivElement | null>(null)
  const panelRef = React.useRef<HTMLDivElement | null>(null)
  const x = useMotionValue(0)
  const dragCleanupRef = React.useRef<(() => void) | null>(null)

  const [isDragging, setIsDragging] = React.useState(false)
  const [snapHint, setSnapHint] = React.useState<CopilotDockSide>(state.side)
  const [squishToken, setSquishToken] = React.useState(0)
  const [copilotActions, setCopilotActions] = React.useState<AiManusChatActions | null>(null)
  const [copilotMeta, setCopilotMeta] = React.useState<AiManusChatMeta | null>(null)
  const [headerPortalEl, setHeaderPortalEl] = React.useState<HTMLDivElement | null>(null)
  const [headerExtraContent, setHeaderExtraContent] = React.useState<React.ReactNode | null>(null)
  const [historyOpenOverride, setHistoryOpenOverride] = React.useState(false)
  const historyPanelId = React.useId()
  const [suggestions, setSuggestions] = React.useState<CopilotSuggestionPayload | null>(null)
  const pendingSuggestionRef = React.useRef<CopilotSuggestionPayload | null>(null)
  const isWelcomeSurface = surfaceMode === 'welcome'
  const attachmentsDrawerOpen = Boolean(copilotMeta?.attachmentsDrawerOpen)
  const attachmentsToggleDisabled = !copilotActions?.toggleAttachmentsDrawer || !copilotMeta?.ready
  const attachmentsToggleLabel = attachmentsDrawerOpen
    ? t('copilot_hide_knowledge')
    : t('copilot_show_knowledge')
  const attachmentsToggleVisible = COPILOT_FILES_ENABLED && Boolean(copilotActions?.toggleAttachmentsDrawer)
  const isOpen = Boolean(forceOpen || state.open)
  const isVisible = Boolean((visible ?? true) && isOpen)
  const chatVisible = keepAlive ? true : isVisible
  const hasCustomHeader = Boolean(headerContent)
  const hasCustomBody = Boolean(bodyContent)
  const wideModeActive = isWelcomeSurface && copilotMeta?.toolPanelVisible === false
  const resizeMaxRatio = isWelcomeSurface
    ? Math.max(state.maxRatio, WELCOME_WIDE_RATIO)
    : state.maxRatio
  const resizeStageMinContent = isWelcomeSurface ? WELCOME_STAGE_MIN_CONTENT : undefined
  const prevWidthRef = React.useRef<number | null>(null)
  const prevMaxRatioRef = React.useRef<number | null>(null)
  const wideModeRef = React.useRef(false)
  const latestDockRef = React.useRef({ width: state.width, maxRatio: state.maxRatio })
  const prevSideRef = React.useRef<CopilotDockSide>(state.side)
  const prevOpenRef = React.useRef(isOpen)

  const activeTab = useTabsStore((store) =>
    store.tabs.find((tab) => tab.id === store.activeTabId)
  )
  const activeTabViewState = useWorkspaceSurfaceStore((store) =>
    activeTab?.id ? store.tabState[activeTab.id] : undefined
  )
  const activeTabReference = useWorkspaceSurfaceStore((store) => {
    if (!activeTab?.id) return null
    const referenceId = store.activeReferenceByTabId[activeTab.id]
    return referenceId ? store.references[referenceId] || null : null
  })
  const activeTabIssue = useWorkspaceSurfaceStore((store) =>
    activeTab?.id ? store.activeIssueByTabId[activeTab.id] : null
  )
  const findNode = useFileTreeStore((store) => store.findNode)

  const boundsWidth = Math.max(0, stageWidth - edgeInset * 2)
  const maxX = Math.max(0, boundsWidth - state.width)
  const targetX = state.side === 'left' ? 0 : maxX

  React.useEffect(() => {
    if (!isOpen) {
      prevOpenRef.current = false
      return
    }
    if (isDragging) return
    const wasOpen = prevOpenRef.current
    const sideChanged = prevSideRef.current !== state.side
    prevSideRef.current = state.side
    prevOpenRef.current = isOpen
    if (!stageWidth) return
    if (prefersReducedMotion) {
      x.set(targetX)
      return
    }
    if (sideChanged || (!wasOpen && isOpen)) {
      const distance = Math.abs(x.get() - targetX)
      const controls = animate(x, targetX, {
        ...SPRING,
        duration: getSnapDuration(distance),
      })
      return () => controls.stop()
    }
    if (Math.abs(x.get() - targetX) > 0.5) {
      x.set(targetX)
    }
  }, [isDragging, isOpen, prefersReducedMotion, stageWidth, state.side, targetX, x])

  React.useEffect(() => {
    if (!isOpen) return
    const next = clampNumber(x.get(), 0, maxX)
    if (Math.abs(next - x.get()) > 0.5) {
      x.set(next)
    }
    setSnapHint(state.side)
  }, [isOpen, maxX, state.side, x])

  React.useEffect(() => {
    latestDockRef.current = { width: state.width, maxRatio: state.maxRatio }
  }, [state.maxRatio, state.width])

  React.useEffect(() => {
    if (!setMaxRatio) return
    if (!stageWidth) return

    if (wideModeActive) {
      if (!wideModeRef.current) {
        prevWidthRef.current = latestDockRef.current.width
        prevMaxRatioRef.current = latestDockRef.current.maxRatio
        wideModeRef.current = true
      }
      const targetWidth = clampNumber(
        Math.round(stageWidth * WELCOME_WIDE_RATIO),
        minWidth,
        boundsWidth
      )
      setMaxRatio(WELCOME_WIDE_RATIO)
      setWidth(targetWidth)
      return
    }

    if (!wideModeRef.current) return
    wideModeRef.current = false
    const restoredRatio = prevMaxRatioRef.current ?? COPILOT_DOCK_DEFAULTS.maxRatio
    setMaxRatio(restoredRatio)
    if (prevWidthRef.current !== null) {
      const restoredWidth = clampCopilotDockWidth({
        width: prevWidthRef.current,
        stageWidth,
        minWidth,
        maxRatio: restoredRatio,
        stageMinContent: resizeStageMinContent,
      })
      setWidth(restoredWidth)
    }
    prevWidthRef.current = null
    prevMaxRatioRef.current = null
  }, [boundsWidth, minWidth, resizeStageMinContent, setMaxRatio, setWidth, stageWidth, wideModeActive])

  const computeHintSide = React.useCallback((): CopilotDockSide => {
    const center = x.get() + state.width / 2
    return center < boundsWidth / 2 ? 'left' : 'right'
  }, [boundsWidth, state.width, x])

  const handleHeaderDrag = React.useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) return
      const target = event.target as HTMLElement | null
      if (target?.closest('button, [role="button"], a')) return
      event.preventDefault()
      const startClientX = event.clientX
      const startX = x.get()
      setIsDragging(true)
      setSnapHint(computeHintSide())

      const finishDrag = () => {
        dragCleanupRef.current = null
        setIsDragging(false)
        const hint = computeHintSide()
        const nextX = hint === 'left' ? 0 : maxX
        prevSideRef.current = hint
        setSide(hint)
        if (prefersReducedMotion) {
          x.set(nextX)
        } else {
          const distance = Math.abs(x.get() - nextX)
          animate(x, nextX, {
            ...SPRING,
            duration: getSnapDuration(distance),
          })
        }
        setSquishToken(Date.now())
      }

      const handlePointerMove = (moveEvent: PointerEvent) => {
        const delta = moveEvent.clientX - startClientX
        const nextX = clampNumber(startX + delta, 0, maxX)
        x.set(nextX)
        const hint = computeHintSide()
        setSnapHint((prev) => (prev === hint ? prev : hint))
      }

      const handlePointerUp = () => {
        cleanup()
        finishDrag()
      }

      const cleanup = () => {
        window.removeEventListener('pointermove', handlePointerMove)
        window.removeEventListener('pointerup', handlePointerUp)
        window.removeEventListener('pointercancel', handlePointerUp)
      }

      dragCleanupRef.current = cleanup
      window.addEventListener('pointermove', handlePointerMove)
      window.addEventListener('pointerup', handlePointerUp, { once: true })
      window.addEventListener('pointercancel', handlePointerUp, { once: true })
    },
    [computeHintSide, maxX, prefersReducedMotion, setSide, x]
  )

  React.useEffect(
    () => () => {
      dragCleanupRef.current?.()
      dragCleanupRef.current = null
    },
    []
  )

  const resizeRef = React.useRef<{
    startClientX: number
    startWidth: number
    side: CopilotDockSide
    stageWidth: number
    maxRatio: number
    stageMinContent?: number
  } | null>(null)

  const handleResizePointerDown = (e: React.PointerEvent) => {
    if (readOnlyMode) return
    e.preventDefault()
    e.stopPropagation()
    const start = {
      startClientX: e.clientX,
      startWidth: state.width,
      side: state.side,
      stageWidth,
      maxRatio: resizeMaxRatio,
      stageMinContent: resizeStageMinContent,
    }
    resizeRef.current = start
    ;(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId)

    const onMove = (ev: PointerEvent) => {
      const active = resizeRef.current
      if (!active) return
      const dx = ev.clientX - active.startClientX
      const nextRaw =
        active.side === 'right' ? active.startWidth - dx : active.startWidth + dx
      const nextWidth = clampCopilotDockWidth({
        width: nextRaw,
        stageWidth: active.stageWidth,
        maxRatio: active.maxRatio,
        stageMinContent: active.stageMinContent,
      })

      const maxWidth = getCopilotDockMaxWidth({
        stageWidth: active.stageWidth,
        maxRatio: active.maxRatio,
        stageMinContent: active.stageMinContent,
      })
      const clamped = clampNumber(nextWidth, minWidth, Math.max(minWidth, maxWidth))

      setWidth(clamped)

      if (active.side === 'right') {
        const nextMaxX = Math.max(0, boundsWidth - clamped)
        x.set(clampNumber(x.get(), 0, nextMaxX))
      } else {
        x.set(0)
      }
    }

    const onUp = () => {
      resizeRef.current = null
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      setSquishToken(Date.now())
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }

  const handleSuggestionSelect = React.useCallback(
    (item: CopilotSuggestionItem) => {
      if (!copilotActions) return
      copilotActions.setComposerValue(item.prompt, true)
      setSuggestions(null)
    },
    [copilotActions]
  )

  const handleActionsChange = React.useCallback(
    (next: AiManusChatActions | null) => {
      setCopilotActions(next)
      onActionsChange?.(next)
    },
    [onActionsChange]
  )

  const handleMetaChange = React.useCallback((next: AiManusChatMeta) => {
    setCopilotMeta((prev) => (isCopilotMetaEqual(prev, next) ? prev : next))
  }, [])

  const logHistoryToggle = React.useCallback((next: boolean) => {
    if (typeof window === 'undefined') return
    if (process.env.NODE_ENV !== 'production' || window.localStorage.getItem('ds_debug_copilot') === '1') {
      console.info('[CopilotHistory][dock-toggle]', { open: next })
    }
  }, [])

  const handleHistoryToggle = React.useCallback(() => {
    setHistoryOpenOverride((prev) => {
      const next = !prev
      logHistoryToggle(next)
      return next
    })
  }, [logHistoryToggle])

  const handleNewThread = React.useCallback(() => {
    if (!copilotActions || readOnlyMode) return
    copilotActions.startNewThread()
    pendingSuggestionRef.current = null
    setSuggestions(null)
    window.setTimeout(() => copilotActions.focusComposer(), 0)
  }, [copilotActions, readOnlyMode])

  const fixWithAiContext = React.useMemo(() => {
    if (!activeTab) return null
    const custom = activeTab.context.customData ?? {}
    if (activeTab.pluginId === BUILTIN_PLUGINS.LATEX) {
      const folderId =
        typeof custom.latexFolderId === 'string'
          ? custom.latexFolderId
          : typeof activeTab.context.resourceId === 'string'
            ? activeTab.context.resourceId
            : null
      if (!folderId) return null
      return { folderId, label: getFileLabel(activeTab) }
    }
    if (activeTab.context.type === 'file' && typeof activeTab.context.resourceId === 'string') {
      const node = findNode(activeTab.context.resourceId)
      if (!node) return null
      let currentId = node.parentId
      while (currentId) {
        const parent = findNode(currentId)
        if (!parent) break
        if (parent.type === 'folder' && parent.folderKind === 'latex') {
          return { folderId: parent.id, label: parent.name || getFileLabel(activeTab) }
        }
        currentId = parent.parentId
      }
    }
    return null
  }, [activeTab, findNode])

  const fixWithAiRunning = Boolean(copilotMeta?.fixWithAiRunning)
  const fixWithAiDisabled =
    readOnlyMode ||
    !copilotActions?.runFixWithAi ||
    !fixWithAiContext?.folderId ||
    fixWithAiRunning
  const fixWithAiTooltip = !fixWithAiContext?.folderId
    ? t('copilot_fix_with_ai_latex_hint')
    : fixWithAiRunning
      ? t('copilot_fix_with_ai_running')
      : t('copilot_fix_with_ai')

  const handleFixWithAi = React.useCallback(() => {
    if (!copilotActions?.runFixWithAi || readOnlyMode) return
    if (!fixWithAiContext?.folderId) return
    copilotActions.runFixWithAi({ folderId: fixWithAiContext.folderId })
  }, [copilotActions, fixWithAiContext?.folderId, readOnlyMode])

  const headerBadges = React.useMemo(() => {
    if (!activeTab) return []

    const badges: CopilotHeaderBadge[] = []
    const contentKind = getWorkspaceContentKind(activeTab, activeTabViewState)
    const kindBadge = getWorkspaceContentKindBadge(contentKind, t)

    if (kindBadge) {
      badges.push({
        key: `kind-${contentKind}`,
        label: kindBadge.label,
        tone: kindBadge.tone,
      })
    }

    if (activeTabViewState?.documentMode === 'rendered') {
      badges.push({
        key: 'mode-rendered',
        label: t('tab_badge_rendered'),
        tone: 'neutral',
      })
    } else if (activeTabViewState?.documentMode === 'source') {
      badges.push({
        key: 'mode-source',
        label: t('tab_badge_source'),
        tone: 'neutral',
      })
    }

    if (activeTabReference) {
      badges.push({
        key: 'has-quote',
        label: t('tab_badge_quote'),
        tone: 'neutral',
      })
    }

    const pageNumber =
      contentKind === 'pdf'
        ? activeTabReference?.pageNumber ?? activeTabViewState?.pageNumber
        : undefined
    if (typeof pageNumber === 'number' && pageNumber > 0) {
      badges.push({
        key: `page-${pageNumber}`,
        label: t('tab_badge_page', { page: pageNumber }),
        tone: 'neutral',
      })
    }

    if (activeTabIssue?.kind === 'latex_error') {
      badges.push({
        key: 'focused-error',
        label: t('copilot_badge_focused_error'),
        tone: 'attention',
      })
    } else if ((activeTabViewState?.diagnostics?.errors || 0) > 0) {
      badges.push({
        key: 'has-error',
        label: t('tab_badge_error'),
        tone: 'attention',
      })
    }

    return badges.slice(0, 5)
  }, [activeTab, activeTabIssue?.kind, activeTabReference, activeTabViewState, t])

  const statusText = typeof copilotMeta?.statusText === 'string' ? copilotMeta.statusText : ''
  const statusPrevText =
    typeof copilotMeta?.statusPrevText === 'string' ? copilotMeta.statusPrevText : ''
  const statusKey = copilotMeta?.statusKey ?? 0
  const statusTexts = statusText
    ? statusPrevText && statusPrevText !== statusText
      ? [statusPrevText, statusText]
      : [statusText]
    : []
  const showStatus = statusTexts.length > 0
  const statusAnimate = statusTexts.length > 1
  const historyOpen = historyOpenOverride
  const headerOrbitResetKey = `${copilotMeta?.threadId ?? projectId}:${copilotMeta?.statusKey ?? 0}:${
    copilotMeta?.isResponding ? 'busy' : 'idle'
  }`

  React.useEffect(() => {
    if (!activeTab) {
      pendingSuggestionRef.current = null
      setSuggestions(null)
      return
    }
    const payload = buildSuggestionPayload({
      tab: activeTab,
      t,
      viewState: activeTabViewState || undefined,
      activeReference: activeTabReference || undefined,
    })
    if (!payload) {
      pendingSuggestionRef.current = null
      setSuggestions(null)
      return
    }
    const shouldDefer =
      !copilotMeta?.ready || copilotMeta?.isResponding || historyOpen
    if (shouldDefer) {
      pendingSuggestionRef.current = payload
      return
    }
    pendingSuggestionRef.current = null
    setSuggestions(payload)
  }, [
    activeTab?.id,
    activeTabReference?.id,
    activeTabReference?.pageNumber,
    activeTabViewState?.contentKind,
    activeTabViewState?.documentMode,
    activeTabViewState?.pageNumber,
    activeTabViewState?.selectionCount,
    activeTabViewState?.diagnostics?.errors,
    activeTabViewState?.diagnostics?.warnings,
    historyOpen,
    copilotMeta?.isResponding,
    copilotMeta?.ready,
    t,
  ])

  React.useEffect(() => {
    if (!copilotMeta?.ready || copilotMeta.isResponding || historyOpen) {
      return
    }
    const pending = pendingSuggestionRef.current
    if (!pending) return
    if (activeTab?.id !== pending.tabId) {
      pendingSuggestionRef.current = null
      return
    }
    setSuggestions(pending)
    pendingSuggestionRef.current = null
  }, [activeTab?.id, historyOpen, copilotMeta?.isResponding, copilotMeta?.ready])

  React.useEffect(() => {
    if (!copilotMeta) return
    if (copilotMeta.isResponding || historyOpen) {
      setSuggestions(null)
    }
  }, [historyOpen, copilotMeta?.isResponding])

  React.useEffect(() => {
    setHeaderExtraContent(null)
  }, [projectId, surfaceMode])

  if (readOnlyMode) return null

  return (
    <div
      ref={dragBoundsRef}
      className={cn(
        'ds-copilot-drag-bounds',
        isDragging && 'is-dragging',
        state.side === 'left' ? 'dock-left' : 'dock-right'
      )}
      style={{
        ['--ds-copilot-inset' as any]: `${edgeInset}px`,
        ['--ds-copilot-gap' as any]: `${gap}px`,
        display: isVisible ? 'block' : 'none',
      }}
      aria-hidden={!isVisible}
      aria-label={t('copilot_dock')}
    >
      {isDragging && (
        <>
          <div
            aria-hidden
            className={cn(
              'ds-copilot-snapzone left',
              snapHint === 'left' && 'is-active'
            )}
          />
          <div
            aria-hidden
            className={cn(
              'ds-copilot-snapzone right',
              snapHint === 'right' && 'is-active'
            )}
          />
        </>
      )}

      <motion.div
        ref={panelRef}
        className="ds-copilot-dock"
        style={{
          left: x,
          width: state.width,
        }}
        animate={
          prefersReducedMotion
            ? undefined
            : squishToken
              ? { scaleX: [1, 0.972, 1], scaleY: [1, 1.008, 1] }
              : undefined
        }
        transition={prefersReducedMotion ? undefined : { duration: 0.18 }}
      >
        <div className="relative h-full w-full overflow-hidden rounded-[18px]">
          <div className="ds-copilot-glass">
            <Noise size={260} className="ds-copilot-noise opacity-[0.06]" />

            <div className="ds-copilot-glass-inner">
              <div className="ds-copilot-header" onPointerDown={handleHeaderDrag}>
                {hasCustomHeader ? (
                  <div className="ds-copilot-header-left ds-copilot-drag-area">
                    {headerContent}
                  </div>
                ) : (
                  <div className="ds-copilot-header-left ds-copilot-drag-area">
                    {!hideHeaderOrbit ? (
                      <div className="ds-copilot-header-orbit-wrap" aria-hidden="true">
                        <OrbitLogoStatus
                          compact
                          sizePx={20}
                          className="ds-copilot-header-orbit"
                          toolCount={copilotMeta?.toolCount}
                          resetKey={headerOrbitResetKey}
                          animated={Boolean(copilotMeta?.isResponding)}
                        />
                      </div>
                    ) : null}
                    <div className="ds-copilot-title-stack">
                      <div className="ds-copilot-title-row">
                        <span className="ds-copilot-title">{t('copilot_title')}</span>
                        {showStatus ? (
                          <>
                            <span className="ds-copilot-title-sep">·</span>
                            <RotatingText
                              key={`copilot-status-${statusKey}`}
                              texts={statusTexts}
                              auto={statusAnimate}
                              loop={false}
                              rotationInterval={1200}
                              staggerFrom="last"
                              staggerDuration={0.02}
                              initial={{ y: '90%', opacity: 0 }}
                              animate={{ y: 0, opacity: 1 }}
                              exit={{ y: '-120%', opacity: 0 }}
                              animatePresenceInitial
                              maxWords={14}
                              mainClassName="ds-copilot-status-text"
                              splitLevelClassName="ds-copilot-status-text-split"
                              elementLevelClassName="ds-copilot-status-text-element"
                            />
                          </>
                        ) : null}
                      </div>
                      {headerBadges.length > 0 ? (
                        <motion.div
                          data-testid="copilot-header-badges"
                          className="ds-copilot-header-badges"
                          initial={prefersReducedMotion ? false : { opacity: 0, y: 4 }}
                          animate={prefersReducedMotion ? undefined : { opacity: 1, y: 0 }}
                          transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                        >
                          {headerBadges.map((badge) => (
                            <span
                              key={badge.key}
                              className="ds-copilot-header-badge"
                              data-tone={badge.tone}
                            >
                              {badge.label}
                            </span>
                          ))}
                        </motion.div>
                      ) : null}
                    </div>
                  </div>
                )}
                <div className="ds-copilot-header-right" role="toolbar" aria-label={t('copilot_controls')}>
                  {!hasCustomHeader && !hideNewChat ? (
                    <button
                      type="button"
                      onClick={handleNewThread}
                      className="ds-copilot-icon-btn"
                      aria-label={t('copilot_new_chat')}
                      data-tooltip={t('copilot_new_chat')}
                      disabled={!copilotActions}
                    >
                      <Plus size={16} />
                    </button>
                  ) : null}
                  {!hasCustomHeader && !hideHistory ? (
                    <button
                      type="button"
                      onClick={handleHistoryToggle}
                      className={cn('ds-copilot-icon-btn', historyOpen && 'is-active')}
                      aria-label={t('copilot_history')}
                      aria-expanded={historyOpen}
                      aria-controls={historyPanelId}
                      data-tooltip={t('copilot_history')}
                      data-ai-manus-history-toggle="true"
                    >
                      <PanelLeft size={16} />
                    </button>
                  ) : null}
                  {!hasCustomHeader && attachmentsToggleVisible ? (
                    <button
                      type="button"
                      onClick={() => copilotActions?.toggleAttachmentsDrawer?.()}
                      className={cn('ds-copilot-icon-btn', attachmentsDrawerOpen && 'is-active')}
                      aria-label={attachmentsToggleLabel}
                      aria-expanded={attachmentsDrawerOpen}
                      aria-controls="copilot-attachments-drawer"
                      data-tooltip={attachmentsToggleLabel}
                      disabled={attachmentsToggleDisabled}
                    >
                      <FolderOpen size={16} />
                    </button>
                  ) : null}
                  {!hasCustomHeader && !hideFixWithAi && copilotActions?.runFixWithAi ? (
                    <button
                      type="button"
                      onClick={handleFixWithAi}
                      className={cn('ds-copilot-fix-btn', fixWithAiRunning && 'is-active')}
                      aria-label={t('copilot_fix_with_ai')}
                      data-tooltip={fixWithAiTooltip}
                      disabled={fixWithAiDisabled}
                    >
                      {fixWithAiRunning ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Sparkles size={14} />
                      )}
                      <span>{fixWithAiRunning ? t('copilot_fix_with_ai_running') : t('copilot_fix_with_ai')}</span>
                    </button>
                  ) : null}
                  <div ref={setHeaderPortalEl} className="ds-copilot-header-extra">
                    {headerExtraContent}
                  </div>
                  {!isWelcomeSurface ? (
                    <button
                      type="button"
                      onClick={onClose}
                      className="ds-copilot-icon-btn"
                      aria-label={t('navbar_hide_copilot')}
                      data-tooltip={t('navbar_hide_copilot')}
                    >
                      <X size={16} />
                    </button>
                  ) : null}
                </div>
              </div>
              <div className="ds-copilot-body">
                <div className="ds-copilot-chat">
                  <CopilotDockHeaderPortalContext.Provider value={headerPortalEl}>
                    <CopilotDockCallbacksContext.Provider
                      value={{
                        onActionsChange: handleActionsChange,
                        onMetaChange: handleMetaChange,
                        onHeaderExtraChange: setHeaderExtraContent,
                      }}
                    >
                      {hasCustomBody ? (
                        bodyContent
                      ) : copilotLocked ? (
                          <div className="flex h-full items-center justify-center p-6 text-center">
                            <div>
                              <div className="text-sm font-medium">{t('copilot_plan_access_required')}</div>
                              <div className="mt-1 text-xs text-muted-foreground">
                                {t('copilot_max_only_desc')}
                              </div>
                            </div>
                          </div>
                        ) : null}
                    </CopilotDockCallbacksContext.Provider>
                  </CopilotDockHeaderPortalContext.Provider>
                </div>
              </div>

              <div
                className={cn(
                  'ds-copilot-resize-handle',
                  state.side === 'right' ? 'on-left' : 'on-right'
                )}
                onPointerDown={handleResizePointerDown}
                role="separator"
                aria-orientation="vertical"
                aria-label={t('copilot_resize')}
                tabIndex={0}
              />
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  )
}

export default CopilotDockOverlay
