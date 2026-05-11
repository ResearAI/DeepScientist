import fs from 'node:fs'

import { expect, test, type Page } from '@playwright/test'

type LabCanvasFixture = {
  quest_id: string
  current_title: string
  sibling_title: string
  paper_branch: string
  metric_keys: string[]
  science_run_title: string
  science_claim_title: string
}

function loadFixture(): LabCanvasFixture {
  const fixturePath = process.env.E2E_FIXTURE_JSON
  if (!fixturePath) {
    throw new Error('E2E_FIXTURE_JSON is required to run lab canvas E2E tests.')
  }
  return JSON.parse(fs.readFileSync(fixturePath, 'utf-8')) as LabCanvasFixture
}

const fixture = loadFixture()

async function setLabCanvasPathFilter(page: Page, pathFilterMode: 'all' | 'current') {
  const response = await page.request.post(`/api/quests/${encodeURIComponent(fixture.quest_id)}/layout`, {
    data: {
      layout_json: {
        branch: {},
        event: {},
        stage: {},
        preferences: {
          pathFilterMode,
          showAnalysis: true,
        },
      },
    },
  })
  expect(response.ok()).toBeTruthy()
}

test.describe('lab canvas workflow', () => {
  test('persists path filtering and exposes all metric selector options', async ({ page }) => {
    await setLabCanvasPathFilter(page, 'current')
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

    await setLabCanvasPathFilter(page, 'all')

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

  test('stage canvas renders science evidence graph nodes', async ({ page }) => {
    await page.goto(`/projects/${fixture.quest_id}`)

    await page.getByRole('button', { name: 'Stage flow' }).click()
    await expect(page.getByText(fixture.science_claim_title).first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('Scientific Claim').first()).toBeVisible()
    await expect(page.getByText(/Evidence:/).first()).toBeVisible()

    await page.getByRole('button', { name: 'Event trace' }).click()
    await expect(page.getByText(fixture.science_run_title).first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('Computational Run').first()).toBeVisible()

    const traces = await page.evaluate(async ({ questId }) => {
      const response = await fetch(
        `/api/quests/${encodeURIComponent(questId)}/node-traces?selection_type=event_node`,
      )
      if (!response.ok) {
        throw new Error(`node traces failed: ${response.status}`)
      }
      const payload = (await response.json()) as {
        items?: Array<{
          artifact_kind?: string | null
          payload_json?: { kind?: string | null; summary?: string | null; title?: string | null } | null
        }>
      }
      return (payload.items ?? [])
        .map((item) => ({
          kind: item.artifact_kind || item.payload_json?.kind || '',
          summary: item.payload_json?.summary || '',
          title: item.payload_json?.title || '',
        }))
        .filter((item) => item.kind.startsWith('science.'))
    }, { questId: fixture.quest_id })

    expect(traces.map((trace) => trace.kind)).toEqual(
      expect.arrayContaining(['science.computational_run', 'science.validation_result', 'science.claim']),
    )
    expect(traces).toContainEqual(
      expect.objectContaining({
        kind: 'science.claim',
        title: fixture.science_claim_title,
        summary: 'The fixture run records a computed water HF/STO-3G total energy with linked validation evidence.',
      }),
    )
  })
})
