'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { useReducedMotion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { useThemeStore } from '@/lib/stores/theme'
import StarBorder from '@/components/react-bits/StarBorder'

const TOOL_STEP_MIN = 3
const TOOL_STEP_MAX = 4
const STATUS_TEXT = [
  'Thinking...',
  'Reasoning...',
  'Analyzing...',
  'Exploring...',
  'Planning...',
  'Drafting...',
  'Synthesizing...',
  'Calculating...',
  'Searching...',
  'Checking...',
  'Compiling...',
  'Refining...',
  'Modeling...',
  'Comparing...',
  'Interpreting...',
  'Mapping...',
  'Validating...',
  'Verifying...',
  'Revising...',
  'Composing...',
]

const ORBIT_FRAME_COUNT = 36
const ORBIT_FRAME_RATE = 18
const ORBIT_FRAME_INTERVAL_MS = 1000 / ORBIT_FRAME_RATE
const resolveAssetBase = (segment: string) => {
  const baseUrl = (import.meta.env.BASE_URL || '/').replace(/\/+$/, '')
  const cleanSegment = segment.replace(/^\/+/, '')
  return `${baseUrl}/${cleanSegment}`
}
const buildOrbitFrames = (basePath: string) =>
  Array.from({ length: ORBIT_FRAME_COUNT }, (_, index) => {
    const value = String(index).padStart(2, '0')
    return `${basePath}/frame_${value}.svg`
  })

export function OrbitLogoStatus({
  compact,
  className,
  textClassName,
  toolCount,
  resetKey,
  sizePx,
  size = 'sm',
  animated = true,
}: {
  compact?: boolean
  className?: string
  textClassName?: string
  toolCount?: number
  resetKey?: string
  sizePx?: number
  size?: 'sm' | 'lg'
  animated?: boolean
}) {
  const resolvedTheme = useThemeStore((state) => state.resolvedTheme)
  const [label, setLabel] = useState('')
  const lastLabelRef = useRef<string>('')
  const lastToolCountRef = useRef(0)
  const nextChangeAtRef = useRef(0)
  const prefersReducedMotion = useReducedMotion()
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const framesRef = useRef<HTMLImageElement[]>([])
  const readyRef = useRef(false)
  const rafRef = useRef<number | null>(null)
  const lastTimeRef = useRef(0)
  const accumulatorRef = useRef(0)
  const frameRef = useRef(0)
  const sizeRef = useRef(0)
  const orbitFrames = useMemo(
    () =>
      buildOrbitFrames(
        resolveAssetBase(resolvedTheme === 'dark' ? 'logo_orbit_inverted' : 'logo_orbit')
      ),
    [resolvedTheme]
  )
  const haloColor =
    resolvedTheme === 'dark' ? 'rgba(210, 176, 119, 0.9)' : 'rgba(196, 160, 102, 0.85)'
  const haloSpeed = compact ? '9s' : '7s'
  const haloThickness = compact ? 1 : 1.5
  const haloSpread = compact ? 4 : 6
  const shouldAnimate = animated && !prefersReducedMotion
  const normalizedResetKey = useMemo(() => {
    if (typeof resetKey === 'string' || typeof resetKey === 'number') {
      return String(resetKey)
    }
    if (typeof resetKey === 'boolean') {
      return resetKey ? 'true' : 'false'
    }
    return null
  }, [resetKey])
  const lastResetKeyRef = useRef<string | null>(null)

  const pickLabel = useCallback(() => {
    if (STATUS_TEXT.length === 0) return ''
    if (STATUS_TEXT.length === 1) return STATUS_TEXT[0]
    let next = STATUS_TEXT[Math.floor(Math.random() * STATUS_TEXT.length)]
    if (next === lastLabelRef.current) {
      next = STATUS_TEXT[(STATUS_TEXT.indexOf(next) + 1) % STATUS_TEXT.length]
    }
    lastLabelRef.current = next
    return next
  }, [])

  const pickToolStep = useCallback(
    () => TOOL_STEP_MIN + Math.floor(Math.random() * (TOOL_STEP_MAX - TOOL_STEP_MIN + 1)),
    []
  )

  const resetLabelCycle = useCallback(
    (count: number) => {
      lastToolCountRef.current = count
      nextChangeAtRef.current = count + pickToolStep()
      setLabel(pickLabel())
    },
    [pickLabel, pickToolStep]
  )

  useEffect(() => {
    const token = normalizedResetKey ?? '__default__'
    if (lastResetKeyRef.current === token) return
    lastResetKeyRef.current = token
    resetLabelCycle(typeof toolCount === 'number' ? toolCount : 0)
  }, [normalizedResetKey, resetLabelCycle, toolCount])

  useEffect(() => {
    if (typeof toolCount !== 'number' || !Number.isFinite(toolCount)) return
    if (toolCount < lastToolCountRef.current) {
      resetLabelCycle(toolCount)
      return
    }
    lastToolCountRef.current = toolCount
    if (toolCount >= nextChangeAtRef.current) {
      resetLabelCycle(toolCount)
    }
  }, [resetLabelCycle, toolCount])

  const drawFrame = useCallback((index: number) => {
    const canvas = canvasRef.current
    const frames = framesRef.current
    if (!canvas || frames.length === 0) return
    const img = frames[index] || frames[0]
    if (!img || !img.complete || img.naturalWidth <= 0 || img.naturalHeight <= 0) return
    const sizePx = sizeRef.current
    if (!sizePx) return
    const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1
    const targetSize = Math.max(1, Math.round(sizePx * dpr))
    if (canvas.width !== targetSize || canvas.height !== targetSize) {
      canvas.width = targetSize
      canvas.height = targetSize
      canvas.style.width = `${sizePx}px`
      canvas.style.height = `${sizePx}px`
    }
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
  }, [])

  const stopAnimation = useCallback(() => {
    if (rafRef.current) {
      window.cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
  }, [])

  const startAnimation = useCallback(() => {
    if (rafRef.current || !shouldAnimate) return
    lastTimeRef.current = performance.now()
    accumulatorRef.current = 0
    const tick = (now: number) => {
      if (!readyRef.current) {
        rafRef.current = window.requestAnimationFrame(tick)
        return
      }
      const delta = now - lastTimeRef.current
      lastTimeRef.current = now
      accumulatorRef.current += delta
      if (accumulatorRef.current >= ORBIT_FRAME_INTERVAL_MS) {
        const steps = Math.floor(accumulatorRef.current / ORBIT_FRAME_INTERVAL_MS)
        accumulatorRef.current -= steps * ORBIT_FRAME_INTERVAL_MS
        frameRef.current = (frameRef.current + steps) % ORBIT_FRAME_COUNT
        drawFrame(frameRef.current)
      }
      rafRef.current = window.requestAnimationFrame(tick)
    }
    rafRef.current = window.requestAnimationFrame(tick)
  }, [drawFrame, shouldAnimate])

  useEffect(() => {
    if (prefersReducedMotion) {
      frameRef.current = 0
      accumulatorRef.current = 0
      drawFrame(0)
    }
  }, [drawFrame, prefersReducedMotion])

  useEffect(() => {
    if (typeof window === 'undefined') return
    let cancelled = false
    stopAnimation()
    readyRef.current = false
    frameRef.current = 0
    accumulatorRef.current = 0
    const images = orbitFrames.map((src) => {
      const img = new Image()
      img.src = src
      return img
    })
    framesRef.current = images
    let loaded = 0
    const handleReady = () => {
      loaded += 1
      if (loaded >= images.length && !cancelled) {
        readyRef.current = true
        drawFrame(frameRef.current)
        if (shouldAnimate) {
          startAnimation()
        }
      }
    }
    images.forEach((img) => {
      if (img.complete) {
        handleReady()
      } else {
        img.onload = handleReady
        img.onerror = handleReady
      }
    })
    return () => {
      cancelled = true
      images.forEach((img) => {
        img.onload = null
        img.onerror = null
      })
    }
  }, [drawFrame, orbitFrames, shouldAnimate, startAnimation, stopAnimation])

  useEffect(() => {
    if (!shouldAnimate) {
      stopAnimation()
      frameRef.current = 0
      drawFrame(0)
      return
    }
    if (readyRef.current) {
      startAnimation()
    }
    return stopAnimation
  }, [drawFrame, shouldAnimate, startAnimation, stopAnimation])

  useEffect(() => {
    frameRef.current = 0
    accumulatorRef.current = 0
    lastTimeRef.current = performance.now()
    drawFrame(0)
  }, [drawFrame, resetKey])

  const fallbackSizePx = size === 'lg' ? (compact ? 40 : 48) : compact ? 28 : 40
  const resolvedSizePx = typeof sizePx === 'number' && sizePx > 0 ? sizePx : fallbackSizePx

  useEffect(() => {
    sizeRef.current = resolvedSizePx
    drawFrame(frameRef.current)
  }, [drawFrame, resolvedSizePx])

  return (
    <div
      className={cn(
        'flex items-center gap-3 text-[var(--text-tertiary)]',
        compact ? 'text-[10px]' : 'text-[11px]',
        className
      )}
    >
      {!compact ? <span className={cn('max-w-[160px] truncate', textClassName)}>{label}</span> : null}
      <StarBorder
        as="div"
        className="ds-orbit-star-border"
        color={haloColor}
        speed={haloSpeed}
        thickness={haloThickness}
        spread={haloSpread}
        data-reduced-motion={!shouldAnimate ? 'true' : 'false'}
      >
        <div
          className="ai-manus-orbit-logo"
          style={
            {
              '--orbit-size': `${resolvedSizePx}px`,
            } as CSSProperties
          }
        >
          <canvas
            ref={canvasRef}
            className="ai-manus-orbit-canvas"
            role="img"
            aria-label="DeepScientist logo"
          />
        </div>
      </StarBorder>
    </div>
  )
}

export default OrbitLogoStatus
