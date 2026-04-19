import fs from 'node:fs'

import { expect, test } from '@playwright/test'

type CopilotFixture = {
  quest_id: string
  studio_link_path: string
  studio_link_text: string
  studio_link_content: string
}

function loadFixture(): CopilotFixture {
  const fixturePath = process.env.E2E_FIXTURE_JSON
  if (!fixturePath) {
    throw new Error('E2E_FIXTURE_JSON is required to run copilot Studio file link E2E tests.')
  }
  return JSON.parse(fs.readFileSync(fixturePath, 'utf-8')) as CopilotFixture
}

const fixture = loadFixture()
const contentAssertionLine = fixture.studio_link_content.split('\n').find((line) => line.trim()) || fixture.studio_link_content

test.describe('copilot studio file links', () => {
  test('opens linked workspace files inside Explorer and the center tab instead of navigating away', async ({
    page,
  }) => {
    await page.goto(`/projects/${fixture.quest_id}`)

    const dock = page.locator('.ds-copilot-dock')
    await expect(dock).toBeVisible({ timeout: 30_000 })

    const hideExplorerButton = page.getByRole('button', {
      name: /Hide Explorer|隐藏资源管理器/,
    })
    await expect(hideExplorerButton).toBeVisible({ timeout: 15_000 })
    await hideExplorerButton.click()

    await expect(page.locator('[data-onboarding-id="workspace-explorer"]')).toHaveCount(0)

    const projectUrl = new RegExp(`/projects/${fixture.quest_id}$`)
    const link = dock.getByRole('link', { name: fixture.studio_link_text }).first()
    await expect(link).toBeVisible({ timeout: 15_000 })
    await link.click()

    await expect(page).toHaveURL(projectUrl)
    await expect(page.locator('[data-onboarding-id="workspace-explorer"]')).toBeVisible({
      timeout: 15_000,
    })

    await page.waitForFunction(
      (targetPath) =>
        Array.from(document.querySelectorAll('[role="treeitem"]')).some((element) =>
          (element.textContent || '').includes(String(targetPath))
        ),
      fixture.studio_link_path,
      { timeout: 15_000 }
    )

    const fileTab = page.getByRole('tab', { name: fixture.studio_link_path }).first()
    await expect(fileTab).toBeVisible({ timeout: 15_000 })
    await expect(fileTab).toHaveAttribute('aria-selected', 'true')

    await expect(page.getByText(contentAssertionLine, { exact: false })).toBeVisible({
      timeout: 15_000,
    })
  })
})
