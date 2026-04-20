import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { expect, test, type Page } from '@playwright/test'

type AdminFixture = {
  quest_id: string
}

function loadFixture(): AdminFixture {
  const fixturePath = process.env.E2E_FIXTURE_JSON
  if (!fixturePath) {
    throw new Error('E2E_FIXTURE_JSON is required to capture settings docs screenshots.')
  }
  return JSON.parse(fs.readFileSync(fixturePath, 'utf-8')) as AdminFixture
}

const fixture = loadFixture()
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const repoRoot = path.resolve(__dirname, '../../..')
const docsImageRoot = process.env.E2E_DOCS_CAPTURE_DIR || path.join(repoRoot, 'docs', 'images')
const settingsImageDir = path.join(docsImageRoot, 'settings')
const adminImageDir = path.join(docsImageRoot, 'admin')
const connectorsImageDir = path.join(docsImageRoot, 'connectors')
const baseUrl = process.env.E2E_BASE_URL || 'http://127.0.0.1:20999'

type ShotSpec = {
  route: string
  path: string
  waitForText: RegExp
  waitForTestId?: string
  beforeGoto?: (page: Page) => Promise<void>
  prepare?: (page: Page) => Promise<void>
}

function ensureDir(dir: string) {
  fs.mkdirSync(dir, { recursive: true })
}

async function prepareEnglish(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem('ds:ui-language', 'en')
  })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.setViewportSize({ width: 1600, height: 900 })
}

async function captureViewport(page: Page, spec: ShotSpec) {
  if (spec.beforeGoto) {
    await spec.beforeGoto(page)
  }
  await page.goto(`${baseUrl}${spec.route}`, { waitUntil: 'networkidle' })
  if (spec.waitForTestId) {
    await expect(page.getByTestId(spec.waitForTestId)).toBeVisible({ timeout: 30_000 })
  } else {
    await expect(page.getByText(spec.waitForText).first()).toBeVisible({ timeout: 30_000 })
  }
  if (spec.prepare) {
    await spec.prepare(page)
  }
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.waitForTimeout(600)
  ensureDir(path.dirname(spec.path))
  await page.screenshot({ path: spec.path })
}

const coreShots: ShotSpec[] = [
  {
    route: '/settings/config',
    path: path.join(settingsImageDir, 'settings-config-en.png'),
    waitForText: /^Runtime$/,
    prepare: async (page) => {
      const field = page.getByText('Home path', { exact: true }).last()
      await field.scrollIntoViewIfNeeded()
      await page.waitForTimeout(500)
    },
  },
  {
    route: '/settings/runners',
    path: path.join(settingsImageDir, 'settings-runners-en.png'),
    waitForText: /Global runner|Default runner|Models/,
  },
  {
    route: '/settings/connector',
    path: path.join(settingsImageDir, 'settings-connectors-overview-en.png'),
    waitForText: /^Connectors$/,
  },
  {
    route: '/settings/baselines',
    path: path.join(settingsImageDir, 'settings-baselines-en.png'),
    waitForText: /^Baselines$/,
  },
  {
    route: '/settings/deepxiv',
    path: path.join(settingsImageDir, 'settings-deepxiv-en.png'),
    waitForText: /DeepXiv/,
  },
  {
    route: '/settings/plugins',
    path: path.join(settingsImageDir, 'settings-plugins-en.png'),
    waitForText: /^Extensions$/,
  },
  {
    route: '/settings/mcp_servers',
    path: path.join(settingsImageDir, 'settings-mcp-servers-en.png'),
    waitForText: /^MCP$/,
  },
]

const connectorShots: ShotSpec[] = [
  {
    route: '/settings/connector/qq',
    path: path.join(connectorsImageDir, 'connector-qq-en.png'),
    waitForText: /^QQ$/,
  },
  {
    route: '/settings/connector/weixin',
    path: path.join(connectorsImageDir, 'connector-weixin-en.png'),
    waitForText: /WeChat/,
  },
  {
    route: '/settings/connector/telegram',
    path: path.join(connectorsImageDir, 'connector-telegram-en.png'),
    waitForText: /Telegram/,
  },
  {
    route: '/settings/connector/discord',
    path: path.join(connectorsImageDir, 'connector-discord-en.png'),
    waitForText: /Discord/,
  },
  {
    route: '/settings/connector/slack',
    path: path.join(connectorsImageDir, 'connector-slack-en.png'),
    waitForText: /Slack/,
  },
  {
    route: '/settings/connector/feishu',
    path: path.join(connectorsImageDir, 'connector-feishu-en.png'),
    waitForText: /Feishu/,
  },
  {
    route: '/settings/connector/whatsapp',
    path: path.join(connectorsImageDir, 'connector-whatsapp-en.png'),
    waitForText: /WhatsApp/,
  },
  {
    route: '/settings/connector/lingzhu',
    path: path.join(connectorsImageDir, 'connector-lingzhu-en.png'),
    waitForText: /Lingzhu|Rokid/,
  },
]

const adminShots: ShotSpec[] = [
  {
    route: '/settings/summary',
    path: path.join(adminImageDir, 'admin-summary-en.png'),
    waitForText: /System Overview/,
  },
  {
    route: '/settings/runtime',
    path: path.join(adminImageDir, 'admin-runtime-en.png'),
    waitForText: /Runtime Sessions/,
  },
  {
    route: '/settings/connectors-health',
    path: path.join(adminImageDir, 'admin-connectors-health-en.png'),
    waitForText: /Connector Health/,
  },
  {
    route: '/settings/diagnostics',
    path: path.join(adminImageDir, 'admin-diagnostics-en.png'),
    waitForText: /^Diagnostics$/,
    beforeGoto: async (page) => {
      await page.route('**/api/system/doctor', async (route) => {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            ok: true,
            cached: {
              ok: false,
              generated_at: '2026-04-20T08:00:00Z',
              failures: [
                {
                  code: 'runner_probe_failed',
                  problem: 'Codex startup probe failed for the configured profile.',
                  why: 'The provider endpoint returned a protocol mismatch.',
                  fix: ['Verify the Codex profile endpoint.', 'Retry with model: inherit.'],
                },
              ],
            },
          }),
        })
      })
      await page.route('**/api/system/failures**', async (route) => {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            ok: true,
            items: [
              {
                quest_id: 'e2e-admin-quest',
                event_type: 'runner.tool_result',
                run_id: 'admin-e2e-main-001',
                summary: 'Tool result order mismatch from provider response.',
              },
            ],
          }),
        })
      })
      await page.route('**/api/system/runtime-tools', async (route) => {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            ok: true,
            items: {
              tinytex: {
                ok: true,
                summary: 'Local pdflatex runtime is available.',
              },
              codex: {
                ok: false,
                summary: 'Codex probe failed with the current provider profile.',
              },
            },
          }),
        })
      })
    },
  },
  {
    route: '/settings/errors',
    path: path.join(adminImageDir, 'admin-errors-en.png'),
    waitForText: /Errors/,
    beforeGoto: async (page) => {
      await page.route('**/api/system/errors**', async (route) => {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            ok: true,
            generated_at: '2026-04-20T08:10:00Z',
            totals: {
              degraded_connectors: 2,
              runtime_failures: 3,
              daemon_errors: 1,
              failed_tasks: 1,
            },
            degraded_connectors: [
              {
                name: 'telegram',
                connection_state: 'degraded',
                last_error: 'Polling token probe failed after reconnect.',
              },
              {
                name: 'feishu',
                connection_state: 'degraded',
                last_error: 'Long connection auth expired.',
              },
            ],
            runtime_failures: [
              {
                quest_id: 'e2e-admin-quest',
                event_type: 'runner.error',
                summary: 'Codex provider returned invalid tool-call JSON arguments.',
              },
              {
                quest_id: 'B-001',
                event_type: 'connector.delivery_failed',
                summary: 'Telegram outbound send failed for the bound conversation.',
              },
            ],
          }),
        })
      })
    },
  },
  {
    route: '/settings/issues',
    path: path.join(adminImageDir, 'admin-issues-en.png'),
    waitForText: /Issue Report/,
  },
  {
    route: '/settings/logs',
    path: path.join(adminImageDir, 'admin-logs-en.png'),
    waitForText: /^Logs$/,
  },
  {
    route: '/settings/quests',
    path: path.join(adminImageDir, 'admin-quests-en.png'),
    waitForText: /^Quests$/,
  },
  {
    route: '/settings/quests',
    path: path.join(adminImageDir, 'admin-quest-detail-en.png'),
    waitForText: /^Quests$/,
    prepare: async (page) => {
      await page.getByRole('link', { name: 'Activity' }).first().click()
      await expect(page).toHaveURL(new RegExp(`/settings/quests/${fixture.quest_id}\\?view=activity&focus=activity-hourly`))
      await expect(page.getByTestId('quest-activity-surface')).toBeVisible({ timeout: 30_000 })
    },
  },
  {
    route: '/settings/repairs',
    path: path.join(adminImageDir, 'admin-repairs-en.png'),
    waitForText: /Repairs/,
  },
  {
    route: '/settings/controllers',
    path: path.join(adminImageDir, 'admin-controllers-en.png'),
    waitForText: /Controllers/,
  },
  {
    route: '/settings/stats',
    path: path.join(adminImageDir, 'admin-stats-en.png'),
    waitForText: /^Stats$/,
    prepare: async (page) => {
      const toggle = page.getByTestId('stats-detailed-charts-toggle')
      if (await toggle.isVisible().catch(() => false)) {
        await toggle.click()
        await page.waitForTimeout(1500)
      }
    },
  },
  {
    route: '/settings/search',
    path: path.join(adminImageDir, 'admin-search-en.png'),
    waitForText: /^Search$/,
    beforeGoto: async (page) => {
      await page.route('**/api/system/search**', async (route) => {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            ok: true,
            items: [
              {
                kind: 'quest',
                quest_id: 'e2e-admin-quest',
                summary: 'Admin E2E Quest · seeded operator fixture with baseline and main run.',
              },
              {
                kind: 'event',
                quest_id: 'e2e-admin-quest',
                summary: 'Recent event summary: provider tool-call mismatch during admin fixture.',
              },
            ],
          }),
        })
      })
    },
    prepare: async (page) => {
      const panel = page.locator('section').filter({ hasText: 'Cross-Quest Search' }).first()
      const input = panel.locator('input').first()
      await expect(input).toBeVisible({ timeout: 30_000 })
      await input.fill('Admin E2E Quest')
      await panel.getByRole('button', { name: 'Search', exact: true }).click()
      await expect(page.getByText(/Admin E2E Quest · seeded operator fixture/i).first()).toBeVisible({ timeout: 30_000 })
    },
  },
]

test.describe('docs settings gallery', () => {
  test.beforeEach(async ({ page }) => {
    await prepareEnglish(page)
  })

  test('captures core settings pages', async ({ page }) => {
    for (const spec of coreShots) {
      await captureViewport(page, spec)
    }
  })

  test('captures connector settings pages', async ({ page }) => {
    for (const spec of connectorShots) {
      await captureViewport(page, spec)
    }
  })

  test('captures admin settings pages', async ({ page }) => {
    for (const spec of adminShots) {
      await captureViewport(page, spec)
    }
  })
})
