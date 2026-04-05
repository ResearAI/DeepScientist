import fs from 'node:fs'

import { expect, test } from '@playwright/test'

type CopilotFixture = {
  quest_id: string
  latest_subject: string
  changed_path: string
  snapshot_heading: string
}

function loadFixture(): CopilotFixture {
  const fixturePath = process.env.E2E_FIXTURE_JSON
  if (!fixturePath) {
    throw new Error('E2E_FIXTURE_JSON is required to run Copilot workspace E2E tests.')
  }
  return JSON.parse(fs.readFileSync(fixturePath, 'utf-8')) as CopilotFixture
}

const fixture = loadFixture()

test.describe('copilot workspace', () => {
  test('creates a new copilot project and lands in an idle workspace', async ({ page }) => {
    await page.goto('/projects/new/copilot')

    await expect(
      page.getByText(/Create a quieter project first|先创建一个安静待命的项目/)
    ).toBeVisible({ timeout: 30_000 })

    const title = `Playwright Copilot ${Date.now()}`
    await page
      .getByPlaceholder(/A short project title|输入一个简短项目标题/)
      .fill(title)

    await page.getByRole('button', { name: /Create project|一键新建/ }).click()

    await expect(page).toHaveURL(/\/projects\/[^/]+$/, { timeout: 30_000 })
    await expect(
      page.getByText(/I am DeepScientist|我是 DeepScientist，任何事情都可以找我帮忙/)
    ).toBeVisible({ timeout: 30_000 })

    const sessionPayload = await page.evaluate(async () => {
      const match = window.location.pathname.match(/\/projects\/([^/]+)/)
      const questId = match?.[1]
      if (!questId) {
        throw new Error('Quest id missing from URL.')
      }
      const response = await fetch(`/api/quests/${encodeURIComponent(questId)}/session`)
      if (!response.ok) {
        throw new Error(`Failed to load session: ${response.status}`)
      }
      return response.json()
    })

    expect(sessionPayload.snapshot.workspace_mode).toBe('copilot')
    expect(String(sessionPayload.snapshot.status || '').toLowerCase()).toBe('idle')
  })

  test('opens git commit nodes and routes explorer files through the commit-aware diff viewer', async ({ page }) => {
    await page.goto(`/projects/${fixture.quest_id}`)

    await expect(page.getByText('Copilot Git Canvas')).toBeVisible({ timeout: 30_000 })

    const commitCard = page.locator('button', { hasText: fixture.latest_subject }).first()
    await expect(commitCard).toBeVisible({ timeout: 15_000 })
    await commitCard.click()

    await page.getByRole('button', { name: 'Open Commit Tab' }).click()

    const commitViewer = page.getByTestId('git-commit-viewer-plugin')
    await expect(commitViewer).toBeVisible({ timeout: 15_000 })
    await expect(commitViewer.getByText(fixture.latest_subject)).toBeVisible({ timeout: 15_000 })
    await expect(commitViewer.getByRole('button', { name: 'Snapshot' })).toBeVisible()
    await expect(commitViewer.getByRole('button', { name: 'Diff' })).toBeVisible()

    const explorerTabs = page.getByRole('tablist', { name: /Explorer views/i })
    await expect(explorerTabs.getByRole('tab', { name: /Snapshot|快照/ })).toBeVisible({ timeout: 15_000 })
    await explorerTabs.getByRole('tab', { name: /Snapshot|快照/ }).click()

    const visibleExplorerPanel = page.locator('[role="tabpanel"]:visible').first()
    const scopedFileNode = visibleExplorerPanel.locator('[data-node-id]', { hasText: fixture.changed_path }).first()
    await expect(scopedFileNode).toBeVisible({ timeout: 15_000 })
    await scopedFileNode.dblclick()

    const diffPlugin = page.locator('[data-testid="git-diff-viewer-plugin"]:visible').first()
    await expect(diffPlugin).toBeVisible({ timeout: 15_000 })
    await diffPlugin.getByTestId('git-diff-viewer-snapshot-toggle').click()
    await expect(diffPlugin.getByText(fixture.snapshot_heading)).toBeVisible({ timeout: 15_000 })
  })
})
