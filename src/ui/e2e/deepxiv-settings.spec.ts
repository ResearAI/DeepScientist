import fs from "node:fs"

import { expect, test } from "@playwright/test"

type AdminFixture = {
  quest_id: string
}

function loadFixture(): AdminFixture {
  const fixturePath = process.env.E2E_FIXTURE_JSON
  if (!fixturePath) {
    throw new Error("E2E_FIXTURE_JSON is required to run DeepXiv settings E2E tests.")
  }
  return JSON.parse(fs.readFileSync(fixturePath, "utf-8")) as AdminFixture
}

loadFixture()
const baseUrl = process.env.E2E_BASE_URL || "http://127.0.0.1:20999"

test.describe("DeepXiv settings", () => {
  test("uses the new step flow and keeps save available after a failed test", async ({ page }) => {
    await page.goto(`${baseUrl}/settings/deepxiv`)

    const startButton = page.getByRole("button", { name: /Start setup|开始配置/ })
    await expect(startButton).toBeVisible({ timeout: 30_000 })
    await startButton.click()

    const dialog = page.locator('[data-onboarding-id="deepxiv-setup-dialog"]')
    await expect(dialog).toBeVisible({ timeout: 10_000 })
    await expect(dialog.getByText(/Register and fill the token|注册并填写 Token/)).toBeVisible()

    const tokenInput = dialog.locator('input[type="password"]').first()
    await tokenInput.fill('token-for-e2e')
    await page.getByRole('button', { name: /Next|下一步/ }).click()

    await expect(dialog.getByText(/Confirm the defaults|确认默认值/)).toBeVisible()
    const inputs = dialog.locator('input')
    await expect(inputs.nth(0)).toHaveValue('20')
    await expect(inputs.nth(1)).toHaveValue('5000')
    await expect(inputs.nth(2)).toHaveValue('90')
    await page.getByRole('button', { name: /Next|下一步/ }).click()

    await expect(dialog.getByText(/Test and preview|测试与预览/)).toBeVisible()
    await page.route('**/api/config/deepxiv/test', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          ok: false,
          summary: 'DeepXiv returned no search results for `transformers`.',
          errors: ['No results were returned for `transformers`.'],
          preview: '{\n  "total": 0,\n  "results": []\n}',
        }),
      })
    })

    await dialog.getByRole('button', { name: /Test `transformers`|测试 `transformers`/ }).click()
    await expect(dialog.getByText(/DeepXiv returned no search results|No results were returned for `transformers`\./).first()).toBeVisible({ timeout: 10_000 })
    await expect(dialog.getByText('"results": []', { exact: false })).toBeVisible({ timeout: 10_000 })

    const saveButton = dialog.getByRole('button', { name: /Save config|保存配置/ })
    await expect(saveButton).toBeEnabled()
    await saveButton.click()
    await expect(dialog).toHaveCount(0, { timeout: 10_000 })
  })
})
