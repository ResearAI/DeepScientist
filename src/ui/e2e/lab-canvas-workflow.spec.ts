import fs from 'node:fs'

import { expect, test } from '@playwright/test'

type LabCanvasFixture = {
  quest_id: string
  current_title: string
  sibling_title: string
  paper_branch: string
  metric_keys: string[]
}

function loadFixture(): LabCanvasFixture {
  const fixturePath = process.env.E2E_FIXTURE_JSON
  if (!fixturePath) {
    throw new Error('E2E_FIXTURE_JSON is required to run lab canvas E2E tests.')
  }
  return JSON.parse(fs.readFileSync(fixturePath, 'utf-8')) as LabCanvasFixture
}

const fixture = loadFixture()

test.describe('lab canvas workflow', () => {
  test('persists path filtering and exposes all metric selector options', async ({ page }) => {
    await page.goto(`/projects/${fixture.quest_id}`)

    const currentNode = page.locator('.lab-quest-graph-node', {
      hasText: fixture.current_title,
    })
    const siblingNode = page.locator('.lab-quest-graph-node', {
      hasText: fixture.sibling_title,
    })
    const paperNode = page
      .locator('.lab-quest-graph-node.is-head')
      .filter({ hasText: fixture.paper_branch })

    await expect(currentNode).toBeVisible({ timeout: 30_000 })
    await expect(paperNode).toBeVisible()
    await expect(siblingNode).toHaveCount(0)

    await page.evaluate(async ({ questId }) => {
      const response = await fetch(`/api/quests/${encodeURIComponent(questId)}/layout`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          layout_json: {
            branch: {},
            event: {},
            stage: {},
            preferences: {
              pathFilterMode: 'all',
              showAnalysis: true,
            },
          },
        }),
      })
      if (!response.ok) {
        throw new Error(`Failed to update layout: ${response.status}`)
      }
    }, { questId: fixture.quest_id })

    await page.reload()
    await expect(siblingNode).toBeVisible({ timeout: 30_000 })

    await page.getByRole('button', { name: 'Metric' }).click()
    const metricSelect = page.locator('select.lab-quest-time-filter').first()
    await expect(metricSelect).toBeVisible()

    const optionTexts = await metricSelect.locator('option').allTextContents()
    expect(optionTexts).toEqual(expect.arrayContaining(fixture.metric_keys))
  })

  test('details view exposes the paper-line audit surfaces', async ({ page }) => {
    await page.goto(`/projects/${fixture.quest_id}`)

    const detailsNav = page.getByText('Details', { exact: true }).first()
    await expect(detailsNav).toBeVisible({ timeout: 30_000 })
    await detailsNav.click()

    await expect(page.getByText('Idea Lines', { exact: true }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('Paper Contract Health', { exact: true }).filter({ visible: true }).first()).toBeVisible()
    await expect(page.getByText('Paper Contract', { exact: true }).filter({ visible: true }).first()).toBeVisible()
    await expect(page.getByText('Paper Lines', { exact: true }).filter({ visible: true }).first()).toBeVisible()
  })
})
