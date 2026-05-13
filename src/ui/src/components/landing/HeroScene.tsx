'use client'

import { useEffect, useRef } from 'react'
import Shimmer from '@/components/effects/Shimmer'
import { assetUrl } from '@/lib/assets'
import { cn } from '@/lib/utils'

const VIEWBOX = {
  width: 1536,
  height: 600,
}

const NODE_POSITIONS = {
  start: { x: 16.3, y: 28.9 },
  local: { x: 38.1, y: 36.4 },
  mid: { x: 50.4, y: 26.1 },
  global: { x: 53.4, y: 2.2 },
}

const NODE_LABELS = {
  local: 'Local optimum',
  mid: 'Midpoint',
  global: 'Global optimum',
}

const DEFAULT_NODE_STOPS = {
  local: 0.22,
  mid: 0.58,
  global: 0.9,
}

const STAGE_STOPS = [0.12, 0.44, 0.7, 1]
const MOUNTAIN_SRC = assetUrl('hero/mountain.png')
const LOCAL_SRC = assetUrl('hero/Local.png')
const MID_SRC = assetUrl('hero/Mid.png')
const GLOBAL_SRC = assetUrl('hero/Global.png')
const ORB_SRC = assetUrl('logo.svg')
const FOG_A_SRC = assetUrl('hero/subtle_watercolor.png')
const FOG_B_SRC = assetUrl('hero/watercolor.png')
const SEAL_SRC = assetUrl('hero/seal.png')

const clampProgress = (value: number) => Math.min(1, Math.max(0, value))

type HeroSceneProps = {
  progress: number
  stageIndex: number
  reducedMotion: boolean
  isMobile: boolean
}

export default function HeroScene({ progress, stageIndex, reducedMotion, isMobile }: HeroSceneProps) {
  const pathRef = useRef<SVGPathElement | null>(null)
  const orbRef = useRef<HTMLDivElement | null>(null)
  const layerRef = useRef<HTMLDivElement | null>(null)
  const mountainRef = useRef<HTMLImageElement | null>(null)
  const pathLayerRef = useRef<SVGSVGElement | null>(null)
  const fogARef = useRef<HTMLImageElement | null>(null)
  const fogBRef = useRef<HTMLImageElement | null>(null)
  const pathLengthRef = useRef(0)
  const nodeStopsRef = useRef(DEFAULT_NODE_STOPS)

  useEffect(() => {
    const path = pathRef.current
    if (!path) return
    const length = path.getTotalLength()
    pathLengthRef.current = length
    path.style.strokeDasharray = `${length}`
    path.style.strokeDashoffset = `${length}`

    const toViewboxPoint = (position: { x: number; y: number }) => ({
      x: (position.x / 100) * VIEWBOX.width,
      y: (position.y / 100) * VIEWBOX.height,
    })

    const samples = Array.from({ length: 240 }, (_, index) => {
      const t = index / 239
      const point = path.getPointAtLength(length * t)
      return { t, x: point.x, y: point.y }
    })

    const findClosest = (target: { x: number; y: number }) => {
      let best = 0
      let bestDist = Number.POSITIVE_INFINITY
      samples.forEach((sample) => {
        const dx = sample.x - target.x
        const dy = sample.y - target.y
        const dist = dx * dx + dy * dy
        if (dist < bestDist) {
          bestDist = dist
          best = sample.t
        }
      })
      return best
    }

    const localStop = findClosest(toViewboxPoint(NODE_POSITIONS.local))
    const midStop = findClosest(toViewboxPoint(NODE_POSITIONS.mid))
    const globalStop = findClosest(toViewboxPoint(NODE_POSITIONS.global))

    if (localStop < midStop && midStop < globalStop) {
      nodeStopsRef.current = {
        local: localStop,
        mid: midStop,
        global: globalStop,
      }
    }
  }, [])

  useEffect(() => {
    const path = pathRef.current
    if (!path) return
    const length = pathLengthRef.current || path.getTotalLength()
    const clamped = clampProgress(progress)
    const stageProgress = STAGE_STOPS[stageIndex] ?? 1
    const pathProgress = reducedMotion ? 1 : isMobile ? stageProgress : clamped
    const orbProgress = reducedMotion ? stageProgress : isMobile ? stageProgress : clamped

    path.style.strokeDashoffset = `${length * (1 - pathProgress)}`

    if (!orbRef.current) return
    const point = path.getPointAtLength(length * orbProgress)
    const xPercent = (point.x / VIEWBOX.width) * 100
    const yPercent = (point.y / VIEWBOX.height) * 100

    orbRef.current.style.left = `${xPercent}%`
    orbRef.current.style.top = `${yPercent}%`
  }, [progress, reducedMotion, stageIndex, isMobile])

  useEffect(() => {
    const layer = layerRef.current
    if (!layer || reducedMotion || isMobile) return

    let rafId: number | null = null

    const handleMove = (event: MouseEvent) => {
      if (!layer) return
      const rect = layer.getBoundingClientRect()
      const x = (event.clientX - rect.left) / rect.width - 0.5
      const y = (event.clientY - rect.top) / rect.height - 0.5

      if (rafId) cancelAnimationFrame(rafId)
      rafId = requestAnimationFrame(() => {
        if (mountainRef.current) {
          mountainRef.current.style.transform = `translate3d(${x * 6}px, ${y * 4}px, 0)`
        }
        if (pathLayerRef.current) {
          pathLayerRef.current.style.transform = `translate3d(${x * 3}px, ${y * 2}px, 0)`
        }
        if (fogARef.current) {
          fogARef.current.style.transform = `translate3d(${x * 8}px, ${y * 6}px, 0)`
        }
        if (fogBRef.current) {
          fogBRef.current.style.transform = `translate3d(${x * 10}px, ${y * 8}px, 0)`
        }
      })
    }

    const handleLeave = () => {
      if (rafId) cancelAnimationFrame(rafId)
      if (mountainRef.current) mountainRef.current.style.transform = 'translate3d(0, 0, 0)'
      if (pathLayerRef.current) pathLayerRef.current.style.transform = 'translate3d(0, 0, 0)'
      if (fogARef.current) fogARef.current.style.transform = 'translate3d(0, 0, 0)'
      if (fogBRef.current) fogBRef.current.style.transform = 'translate3d(0, 0, 0)'
    }

    layer.addEventListener('mousemove', handleMove)
    layer.addEventListener('mouseleave', handleLeave)

    return () => {
      layer.removeEventListener('mousemove', handleMove)
      layer.removeEventListener('mouseleave', handleLeave)
      if (rafId) cancelAnimationFrame(rafId)
    }
  }, [reducedMotion, isMobile])

  const stageProgress = STAGE_STOPS[stageIndex] ?? 1
  const clampedProgress = clampProgress(isMobile ? stageProgress : progress)
  const nodeStops = nodeStopsRef.current
  const localVisible =
    clampedProgress >= (0 + nodeStops.local) / 2 &&
    clampedProgress < (nodeStops.local + nodeStops.mid) / 2
  const midVisible =
    clampedProgress >= (nodeStops.local + nodeStops.mid) / 2 &&
    clampedProgress < (nodeStops.mid + nodeStops.global) / 2
  const globalVisible =
    clampedProgress >= (nodeStops.mid + nodeStops.global) / 2 &&
    clampedProgress < (nodeStops.global + 1) / 2

  return (
    <div
      ref={layerRef}
      className="relative mx-auto w-full max-w-full origin-top scale-100 translate-y-4 overflow-hidden sm:translate-y-6 lg:origin-top lg:scale-[0.94] lg:translate-y-4 lg:overflow-visible xl:scale-[0.97] xl:translate-y-6"
      style={{ aspectRatio: '1536 / 600' }}
    >
      <div className="pointer-events-none absolute left-1/2 top-3 z-40 max-w-[85%] -translate-x-1/2 rounded-full bg-white/80 px-3 py-1 text-center text-[9px] uppercase tracking-[0.18em] text-[#6F6B66] shadow-[0_6px_16px_rgba(45,42,38,0.12)] backdrop-blur sm:left-auto sm:top-4 sm:max-w-none sm:translate-x-0 sm:text-left sm:text-[10px] sm:tracking-[0.2em] sm:right-4">
        Exploring Unknown Scientific Frontiers
      </div>
      <img
        ref={mountainRef}
        src={MOUNTAIN_SRC}
        alt="Watercolor mountain"
        className="absolute inset-0 z-10 h-full w-full object-contain"
        style={{ transition: reducedMotion ? 'none' : 'transform 160ms ease-out' }}
        draggable={false}
      />

      <svg
        ref={pathLayerRef}
        viewBox="0 0 1536 600"
        className="absolute inset-0 z-20 h-full w-full"
        preserveAspectRatio="xMidYMid meet"
        style={{
          color: 'rgba(45, 42, 38, 0.65)',
          transition: reducedMotion ? 'none' : 'transform 160ms ease-out',
        }}
      >
        <path
          ref={pathRef}
          d="M251 175.011C264.926 174.011 308.395 184.412 370.864 234.015C433.332 283.618 482.438 278.018 499.182 269.017L581.246 215.514C594.509 218.681 624.417 223.114 645.903 215.514C667.389 207.913 741.723 166.907 771.398 149.906C817.487 186.408 907.277 254.713 949.453 207.91C991.629 161.106 970.347 115.507 952.773 99.5062L817.989 7"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          fill="none"
          vectorEffect="non-scaling-stroke"
        />
      </svg>

      <div
        className="ds-hero-start z-40"
        style={{ left: `${NODE_POSITIONS.start.x}%`, top: `${NODE_POSITIONS.start.y}%` }}
      />

      <img
        src={LOCAL_SRC}
        alt="Local optimum"
        className={cn(
          'absolute z-40 h-10 w-10 -translate-x-1/2 -translate-y-1/2 transition-all duration-300',
          localVisible ? 'opacity-100 scale-105' : 'opacity-0 scale-95'
        )}
        style={{ left: `${NODE_POSITIONS.local.x}%`, top: `${NODE_POSITIONS.local.y}%` }}
        draggable={false}
      />
      <div
        className={cn(
          'pointer-events-none absolute z-40 -translate-x-[110%] -translate-y-1/2 whitespace-nowrap rounded-full bg-white/85 px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-[#6F6B66] shadow-[0_8px_20px_rgba(45,42,38,0.14)] backdrop-blur transition-all duration-300',
          localVisible ? 'opacity-100 scale-100' : 'opacity-0 scale-95'
        )}
        style={{ left: `${NODE_POSITIONS.local.x}%`, top: `${NODE_POSITIONS.local.y}%` }}
      >
        {NODE_LABELS.local}
      </div>

      <img
        src={MID_SRC}
        alt="Midpoint"
        className={cn(
          'absolute z-40 h-9 w-9 -translate-x-1/2 -translate-y-1/2 transition-all duration-300',
          midVisible ? 'opacity-100 scale-105' : 'opacity-0 scale-95'
        )}
        style={{ left: `${NODE_POSITIONS.mid.x}%`, top: `${NODE_POSITIONS.mid.y}%` }}
        draggable={false}
      />
      <div
        className={cn(
          'pointer-events-none absolute z-40 -translate-x-[110%] -translate-y-1/2 whitespace-nowrap rounded-full bg-white/85 px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-[#6F6B66] shadow-[0_8px_20px_rgba(45,42,38,0.14)] backdrop-blur transition-all duration-300',
          midVisible ? 'opacity-100 scale-100' : 'opacity-0 scale-95'
        )}
        style={{ left: `${NODE_POSITIONS.mid.x}%`, top: `${NODE_POSITIONS.mid.y}%` }}
      >
        {NODE_LABELS.mid}
      </div>

      <div
        className={cn(
          'absolute z-40 -translate-x-1/2 -translate-y-1/2 transition-all duration-300',
          globalVisible ? 'opacity-100 scale-105' : 'opacity-0 scale-95'
        )}
        style={{ left: `${NODE_POSITIONS.global.x}%`, top: `${NODE_POSITIONS.global.y}%` }}
      >
        <Shimmer duration="6s" width="22%" color="rgba(255, 255, 255, 0.22)" angle="42deg">
          <img
            src={GLOBAL_SRC}
            alt="Global optimum"
            className="h-11 w-11"
            draggable={false}
          />
        </Shimmer>
      </div>
      <div
        className={cn(
          'pointer-events-none absolute z-40 -translate-x-[110%] -translate-y-1/2 whitespace-nowrap rounded-full bg-white/85 px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-[#6F6B66] shadow-[0_8px_20px_rgba(45,42,38,0.14)] backdrop-blur transition-all duration-300',
          globalVisible ? 'opacity-100 scale-100' : 'opacity-0 scale-95'
        )}
        style={{ left: `${NODE_POSITIONS.global.x}%`, top: `${NODE_POSITIONS.global.y}%` }}
      >
        {NODE_LABELS.global}
      </div>

      <div
        ref={orbRef}
        className={cn(
          'ds-hero-orb absolute z-40 -translate-x-1/2 -translate-y-1/2',
          reducedMotion || isMobile ? 'ds-hero-orb-static' : ''
        )}
        style={{ left: `${NODE_POSITIONS.start.x}%`, top: `${NODE_POSITIONS.start.y}%` }}
      >
        <img src={ORB_SRC} alt="Explorer orb" className="h-5 w-5" draggable={false} />
      </div>

      <img
        src={FOG_A_SRC}
        alt="Fog layer"
        className="ds-hero-fog ds-hero-fog-a z-30"
        ref={fogARef}
        draggable={false}
      />
      <img
        src={FOG_B_SRC}
        alt="Fog layer"
        className="ds-hero-fog ds-hero-fog-b z-30"
        ref={fogBRef}
        draggable={false}
      />

      <img
        src={SEAL_SRC}
        alt="Seal"
        className="ds-hero-seal z-50"
        draggable={false}
      />

    </div>
  )
}
