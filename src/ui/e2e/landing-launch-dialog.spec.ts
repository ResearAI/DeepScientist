import { expect, test, type Page } from '@playwright/test'

function installLandingStubs(page: Page) {
  page.on('pageerror', (error) => {
    throw error
  })

  return Promise.all([
    page.route('**/api/connectors/availability', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          has_enabled_external_connector: false,
          has_bound_external_connector: false,
          should_recommend_binding: false,
          preferred_connector_name: null,
          preferred_conversation_id: null,
          available_connectors: [],
        }),
      })
    }),
    page.route('**/api/system/update', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          current_version: '1.0.0',
          latest_version: '1.0.0',
          update_available: false,
          prompt_recommended: false,
          busy: false,
          manual_update_command: 'npm install -g @researai/deepscientist@latest',
        }),
      })
    }),
    page.route('**/api/auth/token', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ token: null }),
      })
    }),
  ])
}

async function openLanding(page: Page, locale: 'zh' | 'en') {
  await page.addInitScript((requestedLocale) => {
    window.localStorage.setItem(
      'ds:onboarding:v1',
      JSON.stringify({
        firstRunHandled: true,
        completed: true,
        neverRemind: true,
        language: requestedLocale,
      })
    )
    window.localStorage.setItem('ds:ui-language', requestedLocale)
    ;(window as typeof window & { __DEEPSCIENTIST_RUNTIME__?: unknown }).__DEEPSCIENTIST_RUNTIME__ = {
      auth: {
        enabled: false,
        tokenQueryParam: 'token',
        storageKey: 'ds_local_auth_token',
      },
    }
  }, locale)

  await installLandingStubs(page)
  await page.goto('/')
  await expect(page.locator('[data-onboarding-id="landing-hero"]')).toBeVisible({ timeout: 30_000 })
}

async function openLaunchDialog(page: Page, locale: 'zh' | 'en') {
  await openLanding(page, locale)
  await page.locator('[data-onboarding-id="landing-start-research"]').click()
  await expect(page.locator('[data-onboarding-id="experiment-launch-dialog"]')).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('[data-onboarding-id="launch-mode-copilot-card"]')).toBeVisible()
  await expect(page.locator('[data-onboarding-id="launch-mode-autonomous-card"]')).toBeVisible()
}

test.describe('landing launch dialog', () => {
  test('desktop launch dialog remains readable and balanced', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1600, height: 1000 })
    await openLaunchDialog(page, 'zh')

    const dialog = page.locator('[data-onboarding-id="experiment-launch-dialog"]')
    const box = await dialog.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.width).toBeGreaterThan(860)
    expect(box!.height).toBeLessThan(940)

    await dialog.screenshot({ path: testInfo.outputPath('landing-launch-dialog-desktop-zh.png') })
    await page.screenshot({ path: testInfo.outputPath('landing-launch-dialog-desktop-page-zh.png'), fullPage: true })
  })

  test('mobile Start Research opens the SetupAgent intake directly', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 393, height: 852 })
    await openLanding(page, 'en')

    await page.locator('[data-onboarding-id="landing-start-research"]').click()
    await expect(page.getByRole('heading', { name: 'What do you want to research?' })).toBeVisible({ timeout: 30_000 })
    await expect(page.getByRole('button', { name: 'Send to SetupAgent' })).toBeVisible()
    await expect(page.locator('[data-onboarding-id="experiment-launch-dialog"]')).toHaveCount(0)

    const dialog = page.locator('[role="dialog"]')
    const box = await dialog.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.height).toBeLessThan(810)

    await expect(page.getByRole('button', { name: 'Send to SetupAgent' })).toBeInViewport()

    await dialog.screenshot({ path: testInfo.outputPath('landing-setup-agent-intake-mobile-en.png') })
    await page.screenshot({ path: testInfo.outputPath('landing-setup-agent-intake-mobile-page-en.png'), fullPage: true })
  })
})
