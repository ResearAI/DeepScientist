import fs from 'node:fs'
import { Buffer } from 'node:buffer'

import { expect, test } from '@playwright/test'

type CopilotFixture = {
  quest_id: string
  readnow_quest_id: string
  withdraw_quest_id: string
  latest_subject: string
  changed_path: string
  jump_target_path: string
  jump_target_folder: string
  hidden_jump_target_path: string
  snapshot_heading: string
  unread_message: string
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
      page.getByText(/Create first\. Start later\.|先创建/i)
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

  test('opens branch route nodes into a scoped snapshot workspace tab', async ({ page }) => {
    await page.goto(`/projects/${fixture.quest_id}`)

    const commitCard = page.getByText(fixture.latest_subject, { exact: true }).first()
    await expect(commitCard).toBeVisible({ timeout: 15_000 })
    await commitCard.click()

    const explorerTabs = page.getByRole('tablist', { name: /Explorer views/i })
    await expect(page.getByRole('tab', { name: 'main Close' })).toBeVisible({ timeout: 15_000 })
    await expect(explorerTabs.getByRole('tab', { name: /Snapshot|快照/ })).toBeVisible({ timeout: 15_000 })
    await explorerTabs.getByRole('tab', { name: /Snapshot|快照/ }).click()

    const visibleExplorerPanel = page.locator('[role="tabpanel"]:visible').first()
    await expect(visibleExplorerPanel.getByText('brief.md', { exact: true })).toBeVisible({ timeout: 15_000 })
    await expect(visibleExplorerPanel.getByText('plan.md', { exact: true })).toBeVisible({ timeout: 15_000 })
    await expect(visibleExplorerPanel.getByText('status.md', { exact: true })).toBeVisible({ timeout: 15_000 })
    await expect(visibleExplorerPanel.getByText('SUMMARY.md', { exact: true })).toBeVisible({ timeout: 15_000 })
  })

  test('supports explorer path jumping, reveal scrolling, and open containing folder', async ({ page }) => {
    await page.goto(`/projects/${fixture.quest_id}`)

    const pathInput = page.locator('[data-explorer-path-input="true"]')
    await expect(pathInput).toBeVisible({ timeout: 15_000 })

    await pathInput.fill(`/${fixture.jump_target_path.replace(/\.md$/, '')}`)

    const jumpOption = page
      .locator('[data-explorer-path-option]')
      .filter({ hasText: fixture.jump_target_path })
      .first()
    await expect(jumpOption).toBeVisible({ timeout: 15_000 })

    await pathInput.press('Enter')

    const visibleExplorerPanel = page.locator('[role="tabpanel"]:visible').first()
    await expect(visibleExplorerPanel.getByText('zz-jump-targets', { exact: true })).toBeVisible({
      timeout: 15_000,
    })
    await expect(visibleExplorerPanel.getByText('alpha', { exact: true })).toBeVisible({ timeout: 15_000 })
    await expect(visibleExplorerPanel.getByText('beta', { exact: true })).toBeVisible({ timeout: 15_000 })
    await expect(visibleExplorerPanel.getByText('gamma', { exact: true })).toBeVisible({ timeout: 15_000 })
    await expect(visibleExplorerPanel.getByText('final-note.md', { exact: true })).toBeVisible({
      timeout: 15_000,
    })

    const selectedName = page.locator('.file-tree-node.is-selected .file-tree-name').last()
    await expect(selectedName).toHaveText('final-note.md')

    const treeScroll = page.locator('[role="tabpanel"]:visible .file-tree-scroll').first()
    const scrollTop = await treeScroll.evaluate((node) => node.scrollTop)
    expect(scrollTop).toBeGreaterThan(0)

    const finalNoteNode = page
      .locator('.file-tree-node')
      .filter({ has: page.getByText('final-note.md', { exact: true }) })
      .first()
    await finalNoteNode.click({ button: 'right' })
    await page.getByRole('button', { name: /Open containing folder|打开所在文件夹/ }).click()

    await expect(page.locator('.file-tree-node.is-selected').filter({ hasText: 'gamma' }).first()).toBeVisible({
      timeout: 15_000,
    })
  })

  test('reveals hidden files from the explorer path bar and unhides dotfiles when needed', async ({ page }) => {
    await page.goto(`/projects/${fixture.quest_id}`)

    const pathInput = page.locator('[data-explorer-path-input="true"]')
    await expect(pathInput).toBeVisible({ timeout: 15_000 })
    const visibleExplorerPanel = page.locator('[role="tabpanel"]:visible').first()

    await pathInput.fill(`/${fixture.hidden_jump_target_path}`)
    const hiddenOption = page
      .locator('[data-explorer-path-option]')
      .filter({ hasText: fixture.hidden_jump_target_path })
      .first()
    await expect(hiddenOption).toBeVisible({ timeout: 15_000 })
    await pathInput.press('Enter')

    await expect(visibleExplorerPanel.getByText('.jump-hidden', { exact: true })).toBeVisible({
      timeout: 15_000,
    })
    await expect(visibleExplorerPanel.getByText('secret-note.md', { exact: true })).toBeVisible({
      timeout: 15_000,
    })
  })

  test('keeps the chat composer responsive after typing and pointer leave', async ({ page }) => {
    await page.goto(`/projects/${fixture.quest_id}`)

    const dock = page.locator('.ds-copilot-dock')
    await expect(dock).toBeVisible({ timeout: 30_000 })

    const chatMode = page.getByRole('radio', { name: /^Chat$/ })
    await expect(chatMode).toBeVisible({ timeout: 15_000 })
    await chatMode.click()

    const textarea = page.locator('[data-copilot-textarea="true"]').first()
    await expect(textarea).toBeVisible({ timeout: 15_000 })

    const sample = 'Firefox chat typing regression check.'
    await textarea.click()
    const startedAt = Date.now()
    await page.keyboard.type(sample)
    const elapsedMs = Date.now() - startedAt

    await expect(textarea).toHaveValue(sample)
    expect(elapsedMs).toBeLessThan(5_000)

    await page.mouse.move(12, 12)
    await expect(dock).toBeVisible()
    await expect(textarea).toHaveValue(sample)
  })

  test('uploads and sends a quest chat attachment', async ({ page }) => {
    await page.goto(`/projects/${fixture.quest_id}`)

    await expect(page.locator('.ds-copilot-dock')).toBeVisible({ timeout: 30_000 })
    await page.getByRole('radio', { name: /^Chat$/ }).click()

    const composer = page.locator('[data-copilot-composer="true"]').first()
    await composer.locator('input[type="file"]').setInputFiles({
      name: 'note.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('Attachment body for Playwright'),
    })

    await expect(composer.getByText('note.txt', { exact: true })).toBeVisible({ timeout: 15_000 })
    await expect(composer.getByText(/^File$/)).toBeVisible({ timeout: 15_000 })

    await page.locator('[data-copilot-textarea="true"]').fill('Please read the attached note.')
    await page.getByRole('button', { name: /Send/i }).click()

    const userBubble = page.locator('.ds-copilot-dock').getByText('Please read the attached note.').first()
    await expect(userBubble).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('note.txt', { exact: true }).last()).toBeVisible({ timeout: 15_000 })
  })

})
