import fs from "node:fs"

import { expect, test } from "@playwright/test"

type AdminFixture = { quest_id: string }

function loadFixture(): AdminFixture {
  const fixturePath = process.env.E2E_FIXTURE_JSON
  if (!fixturePath) {
    throw new Error("E2E_FIXTURE_JSON is required to run runner settings E2E tests.")
  }
  return JSON.parse(fs.readFileSync(fixturePath, "utf-8")) as AdminFixture
}

loadFixture()
const baseUrl = process.env.E2E_BASE_URL || "http://127.0.0.1:20999"

test.describe("runner settings", () => {
  test("uses single-select cards and persists the global runner", async ({ page }) => {
    await page.goto(`${baseUrl}/settings/runners`)

    await expect(page.getByText(/Global runner|全局 Runner/)).toBeVisible({ timeout: 30_000 })
    await expect(page.locator('[data-runner-card="codex"]')).toBeVisible()
    await expect(page.locator('[data-runner-card="claude"]')).toBeVisible()
    await expect(page.locator('[data-runner-card="opencode"]')).toBeVisible()
    await expect(page.getByText(/^Enabled$/)).toHaveCount(0)

    await page.locator('[data-runner-card="claude"]').click()
    await expect(page.locator('[data-runner-card="claude"][data-runner-selected="true"]')).toBeVisible({ timeout: 10_000 })
    const payload = await page.evaluate(async () => {
      const [configResponse, runnersResponse] = await Promise.all([
        fetch('/api/config/config'),
        fetch('/api/config/runners'),
      ])
      return {
        config: await configResponse.json(),
        runners: await runnersResponse.json(),
      }
    })

    expect(payload.config.meta.structured_config.default_runner).toBe('claude')
    expect(payload.runners.meta.structured_config.claude.enabled).toBe(true)
    expect(payload.runners.meta.structured_config.codex.enabled).toBe(false)
    expect(payload.runners.meta.structured_config.opencode.enabled).toBe(false)
  })
})
