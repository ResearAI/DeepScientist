import fs from 'node:fs'

import { expect, test } from '@playwright/test'

type CopilotFixture = {
  quest_id: string
}

function loadFixture(): CopilotFixture {
  const fixturePath = process.env.E2E_FIXTURE_JSON
  if (!fixturePath) {
    throw new Error('E2E_FIXTURE_JSON is required to run Copilot tool event E2E tests.')
  }
  return JSON.parse(fs.readFileSync(fixturePath, 'utf-8')) as CopilotFixture
}

const fixture = loadFixture()

test.describe('copilot tool events', () => {
  test('renders MCP tool operations in both Studio and Chat surfaces', async ({ page }) => {
    await page.goto(`/projects/${fixture.quest_id}`)

    const dock = page.locator('.ds-copilot-dock')
    await expect(dock).toBeVisible({ timeout: 30_000 })

    await page.getByRole('radio', { name: /^Studio$/ }).click()
    await expect(
      dock.locator('[data-copilot-tool-surface="studio"][data-copilot-tool-server="artifact"][data-copilot-tool-name="get_quest_state"]').first()
    ).toBeVisible({ timeout: 15_000 })
    await expect(
      dock.locator('[data-copilot-tool-kind="bash_exec"][data-copilot-tool-server="bash_exec"][data-copilot-tool-name="bash_exec"]').first()
    ).toBeVisible({ timeout: 15_000 })
    await expect(dock.getByText('pwd', { exact: false }).first()).toBeVisible({ timeout: 15_000 })
    await expect(dock.getByText('Thinking', { exact: true }).first()).toBeVisible({ timeout: 15_000 })
    await expect(dock.getByText('Thinking through the benchmark handoff before using tools.', { exact: false }).first()).toBeVisible({ timeout: 15_000 })

    await page.getByRole('radio', { name: /^Chat$/ }).click()
    await expect(
      dock.locator('[data-copilot-tool-surface="chat"][data-copilot-tool-server="artifact"][data-copilot-tool-name="get_quest_state"]').first()
    ).toBeVisible({ timeout: 15_000 })
    await expect(
      dock.locator('[data-copilot-tool-surface="chat"][data-copilot-tool-server="bash_exec"][data-copilot-tool-name="bash_exec"]').first()
    ).toBeVisible({ timeout: 15_000 })
    await expect(dock.getByText('pwd', { exact: false }).last()).toBeVisible({ timeout: 15_000 })
  })
})
