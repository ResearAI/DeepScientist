import fs from 'node:fs'

import { expect, test } from '@playwright/test'

type CopilotFixture = {
  quest_id: string
}

function loadFixture(): CopilotFixture {
  const fixturePath = process.env.E2E_FIXTURE_JSON
  if (!fixturePath) {
    throw new Error('E2E_FIXTURE_JSON is required to run workspace tooltip E2E tests.')
  }
  return JSON.parse(fs.readFileSync(fixturePath, 'utf-8')) as CopilotFixture
}

const fixture = loadFixture()

test.describe('workspace tooltip layer', () => {
  test('uses the quest copilot panel on /projects routes', async ({ page }) => {
    await page.goto(`/projects/${fixture.quest_id}`)

    const dock = page.locator('.ds-copilot-dock')
    const panel = page.locator('[data-onboarding-id="workspace-copilot-panel"]')

    await expect(dock).toBeVisible({ timeout: 30_000 })
    await expect(panel).toBeVisible({ timeout: 30_000 })
    await expect(page.locator('.welcome-copilot-view')).toHaveCount(0)
    await expect(page.locator('.ai-manus-mode-welcome')).toHaveCount(0)
  })

  test('keeps the right dock visible after repeated pointer transitions', async ({ page }) => {
    await page.goto(`/projects/${fixture.quest_id}`)

    const dock = page.locator('.ds-copilot-dock')
    const panel = page.locator('[data-onboarding-id="workspace-copilot-panel"]')
    await expect(dock).toBeVisible({ timeout: 30_000 })
    await expect(panel).toBeVisible({ timeout: 30_000 })

    const dockBox = await dock.boundingBox()
    expect(dockBox).not.toBeNull()
    if (!dockBox) {
      throw new Error('Dock bounding box missing.')
    }

    for (let index = 0; index < 10; index += 1) {
      await page.mouse.move(dockBox.x + dockBox.width / 2, dockBox.y + 48)
      await page.waitForTimeout(60)
      await page.mouse.move(12, 12)
      await page.waitForTimeout(60)
    }

    await expect(dock).toBeVisible()
    await expect(panel).toBeVisible()

    const computed = await dock.evaluate((el) => {
      const style = window.getComputedStyle(el)
      return {
        display: style.display,
        visibility: style.visibility,
        opacity: style.opacity,
      }
    })

    expect(computed.display).toBe('flex')
    expect(computed.visibility).toBe('visible')
    expect(Number(computed.opacity)).toBeGreaterThan(0.9)
  })

  test('keeps tooltip readable when moving from trigger onto the tooltip bubble', async ({ page }) => {
    await page.goto(`/projects/${fixture.quest_id}`)

    const dock = page.locator('.ds-copilot-dock')
    await expect(dock).toBeVisible({ timeout: 30_000 })

    const trigger = dock.getByRole('button', { name: 'Hide Copilot' })
    const tooltip = page.locator('#workspace-tooltip-root .workspace-tooltip')

    await trigger.hover()
    await expect(tooltip).toBeVisible({ timeout: 5_000 })
    await expect(tooltip).toHaveText('Hide Copilot')

    const box = await tooltip.boundingBox()
    expect(box).not.toBeNull()
    if (!box) {
      throw new Error('Tooltip bounding box missing.')
    }

    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await page.waitForTimeout(300)
    await expect(tooltip).toBeVisible()
    await expect(tooltip).toHaveText('Hide Copilot')

    await page.mouse.move(8, 8)
    await expect(tooltip).toBeHidden({ timeout: 2_000 })
  })

  test('resolves the nearest interactive ancestor even when the hovered child has its own title', async ({ page }) => {
    await page.goto(`/projects/${fixture.quest_id}`)

    await expect(page.locator('.ds-copilot-dock')).toBeVisible({ timeout: 30_000 })

    await page.evaluate(() => {
      const root = document.getElementById('workspace-root')
      if (!root) {
        throw new Error('workspace-root missing')
      }

      const existing = document.getElementById('workspace-tooltip-e2e-anchor')
      existing?.remove()

      const host = document.createElement('button')
      host.id = 'workspace-tooltip-e2e-anchor'
      host.type = 'button'
      host.setAttribute('aria-label', 'Injected outer action')
      host.style.position = 'fixed'
      host.style.top = '112px'
      host.style.left = '112px'
      host.style.width = '160px'
      host.style.height = '48px'
      host.style.zIndex = '200'
      host.style.border = '1px solid rgba(0,0,0,0.12)'
      host.style.borderRadius = '12px'
      host.style.background = 'rgba(255,255,255,0.96)'
      host.style.color = '#111'

      const child = document.createElement('span')
      child.id = 'workspace-tooltip-e2e-inner'
      child.setAttribute('title', 'Injected inner title')
      child.textContent = 'Injected child'
      child.style.display = 'inline-flex'
      child.style.width = '100%'
      child.style.height = '100%'
      child.style.alignItems = 'center'
      child.style.justifyContent = 'center'

      host.appendChild(child)
      root.appendChild(host)
    })

    const child = page.locator('#workspace-tooltip-e2e-inner')
    const tooltip = page.locator('#workspace-tooltip-root .workspace-tooltip')

    await child.hover()
    await expect(tooltip).toBeVisible({ timeout: 5_000 })
    await expect(tooltip).toHaveText('Injected outer action')

    await page.evaluate(() => {
      document.getElementById('workspace-tooltip-e2e-anchor')?.remove()
    })
  })
})
