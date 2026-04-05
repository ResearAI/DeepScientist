'use client'

import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'

export function useTerminalResize(
  containerRef: RefObject<HTMLElement>,
  onResize: (cols: number, rows: number) => void,
  getSize: () => { cols: number; rows: number } | null,
  resetKey?: string | number | null
) {
  const onResizeRef = useRef(onResize)
  const getSizeRef = useRef(getSize)
  const lastSizeRef = useRef<{ cols: number; rows: number } | null>(null)

  useEffect(() => {
    onResizeRef.current = onResize
  }, [onResize])

  useEffect(() => {
    getSizeRef.current = getSize
  }, [getSize])

  useEffect(() => {
    lastSizeRef.current = null
  }, [resetKey])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    let frameId: number | null = null
    let initialFrameId: number | null = null
    const notifyResize = () => {
      if (!container.isConnected) return
      const size = getSizeRef.current()
      if (!size) return
      const lastSize = lastSizeRef.current
      if (lastSize && lastSize.cols === size.cols && lastSize.rows === size.rows) {
        return
      }
      lastSizeRef.current = size
      try {
        onResizeRef.current(size.cols, size.rows)
      } catch {
        // Ignore resize errors triggered after unmount/dispose.
      }
    }
    const observer = new ResizeObserver(() => {
      if (frameId) {
        window.cancelAnimationFrame(frameId)
      }
      frameId = window.requestAnimationFrame(() => {
        frameId = null
        notifyResize()
      })
    })
    observer.observe(container)
    initialFrameId = window.requestAnimationFrame(() => {
      initialFrameId = null
      notifyResize()
    })
    return () => {
      if (frameId) {
        window.cancelAnimationFrame(frameId)
      }
      if (initialFrameId) {
        window.cancelAnimationFrame(initialFrameId)
      }
      observer.disconnect()
    }
  }, [containerRef])
}
