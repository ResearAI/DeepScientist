import fs from 'node:fs'

import { expect, test } from '@playwright/test'

type GitDiffFixture = {
  quest_id: string
  branch_ref: string
  old_path: string
  new_path: string
  document_heading: string
  diff_path: string
  diff_heading: string
}

function loadFixture(): GitDiffFixture {
  const fixturePath = process.env.E2E_FIXTURE_JSON
  if (!fixturePath) {
    throw new Error('E2E_FIXTURE_JSON is required to run git diff viewer E2E tests.')
  }
  return JSON.parse(fs.readFileSync(fixturePath, 'utf-8')) as GitDiffFixture
}

const fixture = loadFixture()

test.describe('git diff viewer', () => {
  test('renders rename-aware line diffs and explorer snapshot toggle', async ({ page }) => {
    await page.goto(`/projects/${fixture.quest_id}`)

    const branchNode = page.locator('.lab-quest-graph-node', {
      hasText: fixture.branch_ref,
    }).first()
    await expect(branchNode).toBeVisible({ timeout: 30_000 })
    await branchNode.click()

    const snapshotTab = page.getByRole('tab', { name: /snapshot/i })
    await expect(snapshotTab).toBeVisible({ timeout: 15_000 })
    await snapshotTab.click()

    const tree = page.getByRole('tabpanel').getByRole('tree')
    const docsFolder = tree.locator('[data-node-id]', { hasText: 'docs' }).first()
    await expect(docsFolder).toBeVisible({ timeout: 15_000 })
    const renamedFile = tree.getByRole('treeitem', { name: /new-name\.md/i })
    if ((await renamedFile.count()) === 0) {
      await docsFolder.getByRole('button').first().click()
    }
    await expect(renamedFile).toBeVisible()

    const fileNode = tree.locator('[data-node-id]', { hasText: 'notes.md' }).first()
    await expect(fileNode).toBeVisible()
    await fileNode.dblclick()

    const plugin = page.locator('[data-testid="git-diff-viewer-plugin"]:visible').first()
    await expect(plugin).toBeVisible()
    await expect(plugin.getByTestId('git-diff-viewer-snapshot-toggle')).toBeVisible()
    await expect(
      plugin.getByRole('heading', { name: fixture.diff_heading })
    ).toBeVisible({ timeout: 15_000 })

    await plugin.getByTestId('git-diff-viewer-diff-toggle').click()
    const pluginDiff = plugin.getByTestId('git-unified-diff-viewer')
    await expect(pluginDiff).toBeVisible()
    await expect(pluginDiff.getByText(fixture.diff_path)).toBeVisible()
    await expect(
      pluginDiff.getByText(/No patch lines available\.|@@/)
    ).toBeVisible()
  })
})
