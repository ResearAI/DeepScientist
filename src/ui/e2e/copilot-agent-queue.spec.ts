import fs from 'node:fs'

import { expect, test } from '@playwright/test'

type CopilotAgentFixture = {
  agent_readnow_quest_id: string
  agent_withdraw_quest_id: string
  unread_message: string
  agent_start_message: string
  agent_reply_text: string
}

function loadFixture(): CopilotAgentFixture {
  const fixturePath = process.env.E2E_FIXTURE_JSON
  if (!fixturePath) {
    throw new Error('E2E_FIXTURE_JSON is required to run Copilot agent queue E2E tests.')
  }
  return JSON.parse(fs.readFileSync(fixturePath, 'utf-8')) as CopilotAgentFixture
}

const fixture = loadFixture()

async function queueMessageWhileAgentRuns(page: import('@playwright/test').Page, questId: string, text: string) {
  return page.evaluate(
    async ({ qid, bodyText }) => {
      const response = await fetch(`/api/quests/${encodeURIComponent(qid)}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: bodyText,
          source: 'web-react',
        }),
      })
      if (!response.ok) {
        throw new Error(`queue message failed: ${response.status}`)
      }
      return response.json()
    },
    { qid: questId, bodyText: text }
  )
}

test.describe('copilot agent queue actions', () => {
  test('starts an agent run, then read-now consumes the queued message and syncs chat/studio', async ({ page }) => {
    await page.goto(`/projects/${fixture.agent_readnow_quest_id}`)

    const copilotPanel = page.locator('[data-onboarding-id="workspace-copilot-panel"]')
    const modeTabs = page.locator('[data-onboarding-id="quest-copilot-mode-tabs"]')
    const chatTab = page.getByRole('radio', { name: 'Chat' })

    await expect(copilotPanel).toBeVisible({ timeout: 30_000 })
    await expect(copilotPanel.getByPlaceholder(/Send a note|发送备注/)).toBeVisible({ timeout: 30_000 })

    await copilotPanel.getByPlaceholder(/Send a note|发送备注/).fill(fixture.agent_start_message)
    await copilotPanel.getByRole('button', { name: 'Send' }).click()

    await expect(copilotPanel.getByRole('button', { name: 'Stop' })).toBeVisible({ timeout: 15_000 })

    const queuePayload = await queueMessageWhileAgentRuns(page, fixture.agent_readnow_quest_id, fixture.unread_message)
    expect(queuePayload.ok).toBeTruthy()

    await expect(copilotPanel.getByText(fixture.unread_message)).toBeVisible({ timeout: 15_000 })
    await expect(copilotPanel.getByText('Unread', { exact: true })).toBeVisible({ timeout: 15_000 })

    await copilotPanel.getByRole('button', { name: 'Read now' }).click()

    await expect(copilotPanel.getByText('Read', { exact: true })).toBeVisible({ timeout: 15_000 })
    await expect(copilotPanel.getByText(fixture.agent_reply_text)).toBeVisible({ timeout: 15_000 })
    await expect(copilotPanel.getByRole('button', { name: 'Read now' })).toHaveCount(0)
    await expect(copilotPanel.getByRole('button', { name: 'Withdraw' })).toHaveCount(0)

    await chatTab.click()
    await expect(chatTab).toBeChecked({ timeout: 15_000 })
    await expect(copilotPanel.getByText(fixture.unread_message)).toBeVisible({ timeout: 15_000 })
    await expect(copilotPanel.getByText('Read', { exact: true }).first()).toBeVisible({ timeout: 15_000 })
    await expect(copilotPanel.getByRole('button', { name: 'Read now' })).toHaveCount(0)
  })

  test('starts an agent run, then withdraw removes the queued message from waiting queue and syncs chat/studio', async ({ page }) => {
    await page.goto(`/projects/${fixture.agent_withdraw_quest_id}`)

    const copilotPanel = page.locator('[data-onboarding-id="workspace-copilot-panel"]')
    const chatTab = page.getByRole('radio', { name: 'Chat' })

    await expect(copilotPanel).toBeVisible({ timeout: 30_000 })
    await expect(copilotPanel.getByPlaceholder(/Send a note|发送备注/)).toBeVisible({ timeout: 30_000 })

    await copilotPanel.getByPlaceholder(/Send a note|发送备注/).fill(fixture.agent_start_message)
    await copilotPanel.getByRole('button', { name: 'Send' }).click()

    await expect(copilotPanel.getByRole('button', { name: 'Stop' })).toBeVisible({ timeout: 15_000 })

    const queuePayload = await queueMessageWhileAgentRuns(page, fixture.agent_withdraw_quest_id, fixture.unread_message)
    expect(queuePayload.ok).toBeTruthy()

    await expect(copilotPanel.getByText(fixture.unread_message)).toBeVisible({ timeout: 15_000 })
    await expect(copilotPanel.getByText('Unread', { exact: true })).toBeVisible({ timeout: 15_000 })

    await copilotPanel.getByRole('button', { name: 'Withdraw' }).click()

    await expect(copilotPanel.getByText('Withdrawn', { exact: true })).toBeVisible({ timeout: 15_000 })
    await expect(copilotPanel.getByRole('button', { name: 'Read now' })).toHaveCount(0)
    await expect(copilotPanel.getByRole('button', { name: 'Withdraw' })).toHaveCount(0)

    await chatTab.click()
    await expect(chatTab).toBeChecked({ timeout: 15_000 })
    await expect(copilotPanel.getByText(fixture.unread_message)).toBeVisible({ timeout: 15_000 })
    await expect(copilotPanel.getByText('Withdrawn', { exact: true })).toBeVisible({ timeout: 15_000 })

    const stopButton = copilotPanel.getByRole('button', { name: 'Stop' })
    if (await stopButton.count()) {
      await stopButton.click()
    }
  })
})
