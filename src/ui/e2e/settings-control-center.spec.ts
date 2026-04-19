import fs from 'node:fs'

import { expect, test } from '@playwright/test'

type AdminFixture = {
  quest_id: string
  title: string
}

function loadFixture(): AdminFixture {
  const fixturePath = process.env.E2E_FIXTURE_JSON
  if (!fixturePath) {
    throw new Error('E2E_FIXTURE_JSON is required to run settings control center E2E tests.')
  }
  return JSON.parse(fs.readFileSync(fixturePath, 'utf-8')) as AdminFixture
}

const fixture = loadFixture()
const baseUrl = process.env.E2E_BASE_URL || 'http://127.0.0.1:20999'

test.describe('settings control center', () => {
  test('runtime config is the default page and copilot rail opens as a fresh admin session', async ({ page }) => {
    await page.goto(`${baseUrl}/settings`)

    await expect(page.getByRole('heading', { name: 'Runtime', exact: true })).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('Home path', { exact: true }).last()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('settings-copilot-launcher')).toBeVisible()
    await expect(page.getByTestId('settings-copilot-rail')).toHaveCount(0)

    await page.getByTestId('settings-copilot-launcher').click()
    const rail = page.getByTestId('settings-copilot-rail')
    await expect(rail).toBeVisible({ timeout: 10_000 })
    await expect(rail.getByText('Admin Copilot')).toBeVisible({ timeout: 10_000 })
    await expect(rail.getByRole('button', { name: 'Clear Context' })).toBeVisible({ timeout: 10_000 })
  })

  test('runtime route exposes hardware controls and session evidence', async ({ page }) => {
    await page.goto(`${baseUrl}/settings/runtime`)

    await expect(page.getByRole('heading', { name: 'Sessions & Hardware', exact: true })).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('System Hardware')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByRole('button', { name: /Save Hardware Policy|保存硬件策略/ })).toBeVisible()
    await expect(page.getByText('Runtime Sessions', { exact: true }).first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('Selected Output', { exact: true })).toBeVisible({ timeout: 30_000 })
  })

  test('summary stays compact while stats exposes detailed charts on demand', async ({ page }) => {
    await page.goto(`${baseUrl}/settings/summary`)

    await expect(page.getByText(/System Summary|系统摘要/).first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText(/System Trajectory|系统轨迹/)).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('summary-chart-range-1h')).toHaveCount(0)

    const statsChartsResponse = page.waitForResponse(
      (response) => response.url().includes('/api/system/charts/query') && response.request().method() === 'POST'
    )
    await page.goto(`${baseUrl}/settings/stats`)

    await expect(page.getByText(/Stats|统计/).first()).toBeVisible({ timeout: 30_000 })
    await page.getByTestId('stats-detailed-charts-toggle').click()
    const statsChartsPayload = await (await statsChartsResponse).json()
    expect(statsChartsPayload.ok).toBeTruthy()
    expect(statsChartsPayload.items?.length ?? 0).toBeGreaterThan(0)
    await expect(page.getByTestId('auto-chart-system-cpu_memory_disk')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('auto-chart-tools-by_tool')).toBeVisible({ timeout: 30_000 })
    const statsRangeResponse = page.waitForResponse(
      (response) => response.url().includes('/api/system/charts/query') && response.request().method() === 'POST'
    )
    await page.getByTestId('stats-chart-range-7d').click()
    const statsRangePayload = await (await statsRangeResponse).json()
    expect(statsRangePayload.ok).toBeTruthy()
    await expect(page.getByTestId('auto-chart-tools-calls_total')).toBeVisible({ timeout: 30_000 })

    await page.getByRole('link', { name: /Weekly activity|周活动/ }).first().click()
    await expect(page).toHaveURL(new RegExp(`/settings/quests/${fixture.quest_id}\\?view=settings&focus=activity-hourly`))
    await expect(page.getByTestId('quest-settings-analytics')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('quest-settings-focus-activity-hourly')).toBeVisible({ timeout: 30_000 })
  })
})
