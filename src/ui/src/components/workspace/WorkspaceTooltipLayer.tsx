'use client'

import * as React from 'react'
import { createPortal } from 'react-dom'

const TOOLTIP_ROOT_ID = 'workspace-tooltip-root'
const TOOLTIP_TARGET_SELECTOR = '[data-tooltip], [aria-label], [title]'
const INTERACTIVE_SELECTOR =
  'button, a, [role="button"], [role="menuitem"], .ds-copilot-icon-btn, .ghost-btn'
const VIEWPORT_PADDING = 8
const TOOLTIP_GAP = 8
const TOOLTIP_HIDE_DELAY_MS = 220

type TooltipSource = 'data' | 'aria' | 'title'

type TooltipPosition = {
  top: number
  left: number
  placement: 'top' | 'bottom'
}

function getTooltipLabel(el: HTMLElement): { label: string; source: TooltipSource } | null {
  const dataLabel = el.getAttribute('data-tooltip')
  if (dataLabel?.trim()) {
    return { label: dataLabel.trim(), source: 'data' }
  }

  const ariaLabel = el.getAttribute('aria-label')
  if (ariaLabel?.trim()) {
    return { label: ariaLabel.trim(), source: 'aria' }
  }

  const titleLabel = el.getAttribute('title')
  if (titleLabel?.trim()) {
    return { label: titleLabel.trim(), source: 'title' }
  }

  return null
}

function findTooltipAnchor(target: EventTarget | null, root: HTMLElement | null) {
  if (!root || !(target instanceof Element)) return null
  let candidate: Element | null = target
  while (candidate && root.contains(candidate)) {
    if (
      candidate instanceof HTMLElement &&
      candidate.matches(TOOLTIP_TARGET_SELECTOR) &&
      (candidate.matches(INTERACTIVE_SELECTOR) || candidate.hasAttribute('data-tooltip'))
    ) {
      return candidate
    }
    candidate = candidate.parentElement
  }

  return null
}

export function WorkspaceTooltipLayer({ rootId = 'workspace-root' }: { rootId?: string }) {
  const [label, setLabel] = React.useState('')
  const [visible, setVisible] = React.useState(false)
  const [position, setPosition] = React.useState<TooltipPosition>({
    top: 0,
    left: 0,
    placement: 'top',
  })
  const [portalTarget, setPortalTarget] = React.useState<HTMLElement | null>(null)

  const anchorRef = React.useRef<HTMLElement | null>(null)
  const tooltipRef = React.useRef<HTMLDivElement | null>(null)
  const titleAnchorRef = React.useRef<HTMLElement | null>(null)
  const rafRef = React.useRef<number | null>(null)
  const hideTimeoutRef = React.useRef<number | null>(null)
  const tooltipHoveredRef = React.useRef(false)

  const cancelScheduledHide = React.useCallback(() => {
    if (hideTimeoutRef.current !== null) {
      window.clearTimeout(hideTimeoutRef.current)
      hideTimeoutRef.current = null
    }
  }, [])

  const restoreTitle = React.useCallback(() => {
    if (!titleAnchorRef.current) return
    const original = titleAnchorRef.current.getAttribute('data-tooltip-original-title')
    if (original !== null) {
      titleAnchorRef.current.setAttribute('title', original)
      titleAnchorRef.current.removeAttribute('data-tooltip-original-title')
    }
    titleAnchorRef.current = null
  }, [])

  const suppressTitle = React.useCallback((el: HTMLElement, value: string) => {
    if (!el.hasAttribute('data-tooltip-original-title')) {
      el.setAttribute('data-tooltip-original-title', value)
      el.removeAttribute('title')
    }
    titleAnchorRef.current = el
  }, [])

  const hideTooltip = React.useCallback(() => {
    cancelScheduledHide()
    tooltipHoveredRef.current = false
    restoreTitle()
    anchorRef.current = null
    setVisible(false)
    setLabel('')
  }, [cancelScheduledHide, restoreTitle])

  const scheduleHide = React.useCallback(
    (delay = TOOLTIP_HIDE_DELAY_MS) => {
      cancelScheduledHide()
      hideTimeoutRef.current = window.setTimeout(() => {
        hideTimeoutRef.current = null
        if (tooltipHoveredRef.current) return
        hideTooltip()
      }, delay)
    },
    [cancelScheduledHide, hideTooltip]
  )

  const showTooltip = React.useCallback(
    (anchor: HTMLElement, nextLabel: string) => {
      if (!nextLabel) return
      cancelScheduledHide()
      tooltipHoveredRef.current = false
      restoreTitle()
      const titleValue = anchor.getAttribute('title')
      if (titleValue?.trim()) {
        suppressTitle(anchor, titleValue.trim())
      }
      anchorRef.current = anchor
      setLabel(nextLabel)
      setVisible(true)
    },
    [cancelScheduledHide, restoreTitle, suppressTitle]
  )

  const updatePosition = React.useCallback(() => {
    const anchor = anchorRef.current
    const tooltip = tooltipRef.current
    if (!anchor || !tooltip) return
    if (!anchor.isConnected) {
      hideTooltip()
      return
    }

    const rect = anchor.getBoundingClientRect()
    const tooltipRect = tooltip.getBoundingClientRect()
    const viewportWidth = window.innerWidth
    const viewportHeight = window.innerHeight

    let placement: TooltipPosition['placement'] = 'top'
    let top = rect.top - tooltipRect.height - TOOLTIP_GAP
    if (top < VIEWPORT_PADDING) {
      placement = 'bottom'
      top = rect.bottom + TOOLTIP_GAP
    }
    if (placement === 'bottom' && top + tooltipRect.height > viewportHeight - VIEWPORT_PADDING) {
      placement = 'top'
      top = rect.top - tooltipRect.height - TOOLTIP_GAP
    }

    top = Math.min(
      Math.max(top, VIEWPORT_PADDING),
      viewportHeight - VIEWPORT_PADDING - tooltipRect.height
    )

    let left = rect.left + rect.width / 2 - tooltipRect.width / 2
    left = Math.min(
      Math.max(left, VIEWPORT_PADDING),
      viewportWidth - VIEWPORT_PADDING - tooltipRect.width
    )

    setPosition((prev) => {
      if (
        Math.abs(prev.top - top) < 0.5 &&
        Math.abs(prev.left - left) < 0.5 &&
        prev.placement === placement
      ) {
        return prev
      }
      return { top, left, placement }
    })
  }, [hideTooltip])

  React.useEffect(() => {
    let created = false
    let root = document.getElementById(TOOLTIP_ROOT_ID) as HTMLElement | null
    if (!root) {
      root = document.createElement('div')
      root.id = TOOLTIP_ROOT_ID
      root.setAttribute('aria-hidden', 'true')
      root.style.position = 'fixed'
      root.style.inset = '0'
      root.style.pointerEvents = 'none'
      root.style.overflow = 'hidden'
      root.style.zIndex = '140'
      document.body.appendChild(root)
      created = true
    }
    setPortalTarget(root)
    return () => {
      if (created && root) {
        root.remove()
      }
    }
  }, [])

  React.useEffect(() => {
    const root = document.getElementById(rootId)
    if (!root) return

    const handlePointerOver = (event: PointerEvent) => {
      cancelScheduledHide()
      const anchor = findTooltipAnchor(event.target, root)
      if (!anchor) {
        scheduleHide()
        return
      }
      const next = getTooltipLabel(anchor)
      if (!next) {
        scheduleHide()
        return
      }
      if (anchor === anchorRef.current && next.label === label && visible) return
      showTooltip(anchor, next.label)
    }

    const handlePointerOut = (event: PointerEvent) => {
      const related = event.relatedTarget
      if (related instanceof Element && anchorRef.current?.contains(related)) {
        return
      }
      if (related instanceof Element && tooltipRef.current?.contains(related)) {
        return
      }
      const nextAnchor = findTooltipAnchor(related, root)
      if (nextAnchor) return
      scheduleHide()
    }

    const handleFocusIn = (event: FocusEvent) => {
      cancelScheduledHide()
      const anchor = findTooltipAnchor(event.target, root)
      if (!anchor) return
      const next = getTooltipLabel(anchor)
      if (!next) return
      showTooltip(anchor, next.label)
    }

    const handleFocusOut = (event: FocusEvent) => {
      const related = event.relatedTarget
      if (related instanceof Element && anchorRef.current?.contains(related)) {
        return
      }
      hideTooltip()
    }

    root.addEventListener('pointerover', handlePointerOver)
    root.addEventListener('pointerout', handlePointerOut)
    root.addEventListener('focusin', handleFocusIn)
    root.addEventListener('focusout', handleFocusOut)

    return () => {
      root.removeEventListener('pointerover', handlePointerOver)
      root.removeEventListener('pointerout', handlePointerOut)
      root.removeEventListener('focusin', handleFocusIn)
      root.removeEventListener('focusout', handleFocusOut)
    }
  }, [cancelScheduledHide, hideTooltip, label, rootId, scheduleHide, showTooltip, visible])

  React.useEffect(() => {
    if (!visible) return
    updatePosition()

    const handle = () => {
      if (rafRef.current !== null) {
        window.cancelAnimationFrame(rafRef.current)
      }
      rafRef.current = window.requestAnimationFrame(() => {
        rafRef.current = null
        updatePosition()
      })
    }

    window.addEventListener('scroll', handle, true)
    window.addEventListener('resize', handle)
    return () => {
      if (rafRef.current !== null) {
        window.cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
      window.removeEventListener('scroll', handle, true)
      window.removeEventListener('resize', handle)
    }
  }, [updatePosition, visible])

  React.useLayoutEffect(() => {
    if (!visible) return
    updatePosition()
  }, [label, updatePosition, visible])

  React.useEffect(() => {
    return () => {
      cancelScheduledHide()
      restoreTitle()
    }
  }, [cancelScheduledHide, restoreTitle])

  if (!portalTarget || !visible || !label) return null

  return createPortal(
    <div
      ref={tooltipRef}
      className="workspace-tooltip"
      style={{ top: position.top, left: position.left, position: 'fixed', pointerEvents: 'auto' }}
      data-placement={position.placement}
      role="tooltip"
      onPointerEnter={() => {
        tooltipHoveredRef.current = true
        cancelScheduledHide()
      }}
      onPointerLeave={(event) => {
        tooltipHoveredRef.current = false
        const related = event.relatedTarget
        if (related instanceof Element && anchorRef.current?.contains(related)) {
          return
        }
        scheduleHide(0)
      }}
    >
      {label}
    </div>,
    portalTarget
  )
}
