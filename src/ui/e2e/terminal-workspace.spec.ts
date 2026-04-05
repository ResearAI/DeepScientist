import fs from 'node:fs'

import { expect, test } from '@playwright/test'

type TerminalFixture = {
  quest_id: string
}

function loadFixture(): TerminalFixture {
  const fixturePath = process.env.E2E_FIXTURE_JSON
  if (!fixturePath) {
    throw new Error('E2E_FIXTURE_JSON is required to run terminal workspace E2E tests.')
  }
  return JSON.parse(fs.readFileSync(fixturePath, 'utf-8')) as TerminalFixture
}

const fixture = loadFixture()
const baseUrl = process.env.E2E_BASE_URL || 'http://127.0.0.1:20999'

test.describe('terminal workspace', () => {
  test('opens the interactive terminal and reports attach timing', async ({ page }) => {
    test.slow()

    const startedAt = Date.now()
    const requestStarted = new Map<string, number>()
    const timeline: Array<{ t: number; type: string; detail: string }> = []

    const push = (type: string, detail: string) => {
      timeline.push({
        t: Date.now() - startedAt,
        type,
        detail,
      })
    }

    page.on('console', (msg) => {
      push('console', `${msg.type()}: ${msg.text()}`)
    })

    page.on('pageerror', (error) => {
      push('pageerror', error.stack || error.message)
    })

    page.on('request', (request) => {
      const url = request.url()
      if (!url.includes('/terminal/') && !url.includes('/bash/sessions/stream')) {
        return
      }
      const key = `${request.method()} ${url}`
      requestStarted.set(key, Date.now())
      push('request', key)
    })

    page.on('response', (response) => {
      const url = response.url()
      if (!url.includes('/terminal/') && !url.includes('/bash/sessions/stream')) {
        return
      }
      const key = `${response.request().method()} ${url}`
      const started = requestStarted.get(key) || Date.now()
      push('response', `${response.status()} ${url} +${Date.now() - started}ms`)
    })

    page.on('websocket', (ws) => {
      if (!ws.url().includes('/terminal/attach')) {
        return
      }
      push('websocket', `open ${ws.url()}`)
      ws.on('framereceived', (frame) => {
        const payload = typeof frame.payload === 'string' ? frame.payload : '<binary>'
        push('ws:recv', payload.slice(0, 160))
      })
      ws.on('framesent', (frame) => {
        const payload = typeof frame.payload === 'string' ? frame.payload : '<binary>'
        push('ws:send', payload.slice(0, 160))
      })
      ws.on('socketerror', (error) => {
        push('websocket:error', String(error))
      })
      ws.on('close', () => {
        push('websocket', 'close')
      })
    })

    try {
      await page.goto(`${baseUrl}/projects/${fixture.quest_id}`)
      push('marker', 'project page loaded')

      const terminalSidebarButton = page.locator(
        '[data-onboarding-id="quest-workspace-tab-terminal"]'
      )
      await expect(terminalSidebarButton).toBeVisible({ timeout: 30_000 })
      push('marker', 'terminal sidebar button visible')
      await terminalSidebarButton.click()
      push('marker', 'terminal sidebar button clicked')

      await expect(page.getByText(/Terminal workspace|终端工作区/)).toBeVisible({
        timeout: 30_000,
      })
      push('marker', 'terminal workspace visible')

      const sessionLabel = page.getByText(/terminal-main/)
      await expect(sessionLabel.first()).toBeVisible({ timeout: 30_000 })
      push('marker', 'terminal-main visible')

      await expect
        .poll(
          () =>
            timeline.some(
              (entry) =>
                entry.type === 'ws:recv' &&
                /"type"\s*:\s*"ready"/.test(entry.detail)
            ),
          { timeout: 20_000 }
        )
        .toBe(true)
      push('marker', 'ready frame received')

      const terminalViewport = page.locator('.cli-terminal .xterm')
      await expect(terminalViewport.first()).toBeVisible({ timeout: 20_000 })
      push('marker', 'xterm viewport visible')

      await page.waitForTimeout(1500)

      const resizeCounts = new Map<string, number>()
      for (const entry of timeline) {
        if (entry.type !== 'ws:send' || !entry.detail.includes('"type":"resize"')) {
          continue
        }
        resizeCounts.set(entry.detail, (resizeCounts.get(entry.detail) || 0) + 1)
      }
      const maxRepeatedResizeCount = Math.max(0, ...resizeCounts.values())
      expect(maxRepeatedResizeCount).toBeLessThanOrEqual(3)

      const attachRequest = timeline.find(
        (entry) =>
          entry.type === 'response' &&
          entry.detail.includes('/terminal/sessions/terminal-main/attach')
      )
      const ensureRequest = timeline.find(
        (entry) =>
          entry.type === 'response' &&
          entry.detail.includes('/terminal/session/ensure')
      )

      expect(attachRequest).toBeTruthy()
      expect(ensureRequest).toBeTruthy()
    } finally {
      console.log('[terminal-e2e] timeline')
      console.log(JSON.stringify(timeline, null, 2))
    }
  })
})
