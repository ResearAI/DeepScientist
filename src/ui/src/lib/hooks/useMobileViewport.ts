'use client'

import * as React from 'react'

export const MOBILE_VIEWPORT_MAX_WIDTH = 1023
export const MOBILE_VIEWPORT_MAX_ASPECT_RATIO = 1
export const ONBOARDING_MOBILE_VIEWPORT_MAX_WIDTH = 767

type MobileViewportOptions = {
  maxWidth?: number
  maxAspectRatio?: number
}

export function isMobileViewportMatch(
  width: number,
  height: number,
  options: MobileViewportOptions = {}
) {
  const maxWidth = options.maxWidth ?? MOBILE_VIEWPORT_MAX_WIDTH
  const maxAspectRatio = options.maxAspectRatio ?? MOBILE_VIEWPORT_MAX_ASPECT_RATIO

  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return false
  }

  return width <= maxWidth && width / height <= maxAspectRatio
}

export function useMobileViewport(options: MobileViewportOptions = {}) {
  const { maxWidth = MOBILE_VIEWPORT_MAX_WIDTH, maxAspectRatio = MOBILE_VIEWPORT_MAX_ASPECT_RATIO } = options
  const [isMobile, setIsMobile] = React.useState(() => {
    if (typeof window === 'undefined') return false
    return isMobileViewportMatch(window.innerWidth, window.innerHeight, {
      maxWidth,
      maxAspectRatio,
    })
  })

  React.useEffect(() => {
    if (typeof window === 'undefined') return

    const update = () => {
      setIsMobile(
        isMobileViewportMatch(window.innerWidth, window.innerHeight, {
          maxWidth,
          maxAspectRatio,
        })
      )
    }

    update()
    window.addEventListener('resize', update)
    window.addEventListener('orientationchange', update)

    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('orientationchange', update)
    }
  }, [maxAspectRatio, maxWidth])

  return isMobile
}
