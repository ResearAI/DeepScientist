import { describe, expect, it } from 'vitest'

import {
  isMobileViewportMatch,
  MOBILE_VIEWPORT_MAX_WIDTH,
} from '../hooks/useMobileViewport'

describe('useMobileViewport helpers', () => {
  it('treats narrow portrait viewports as mobile', () => {
    expect(
      isMobileViewportMatch(430, 932, {
        maxWidth: MOBILE_VIEWPORT_MAX_WIDTH,
      })
    ).toBe(true)
  })

  it('does not treat landscape layouts wider than 1:1 as mobile', () => {
    expect(
      isMobileViewportMatch(900, 700, {
        maxWidth: MOBILE_VIEWPORT_MAX_WIDTH,
      })
    ).toBe(false)
  })

  it('does not treat wide desktop viewports as mobile even when tall', () => {
    expect(
      isMobileViewportMatch(1200, 1600, {
        maxWidth: MOBILE_VIEWPORT_MAX_WIDTH,
      })
    ).toBe(false)
  })
})
