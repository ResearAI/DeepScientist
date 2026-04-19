import { expect, test } from '@playwright/test'

function installLandingStubs(page: import('@playwright/test').Page) {
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
    page.route('**/api/quest-id/next', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ quest_id: '903' }),
      })
    }),
    page.route('**/api/connectors', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
    }),
    page.route('**/api/baselines', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
    }),
  ])
}

async function openAutonomousDialog(page: import('@playwright/test').Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      'ds:onboarding:v1',
      JSON.stringify({
        firstRunHandled: true,
        completed: true,
        neverRemind: true,
        language: 'zh',
      })
    )
    window.localStorage.setItem('ds:ui-language', 'zh')
    ;(window as typeof window & { __DEEPSCIENTIST_RUNTIME__?: unknown }).__DEEPSCIENTIST_RUNTIME__ = {
      auth: {
        enabled: false,
        tokenQueryParam: 'token',
        storageKey: 'ds_local_auth_token',
      },
    }
  })

  await installLandingStubs(page)
  await page.goto('/')
  await expect(page.locator('[data-onboarding-id="landing-hero"]')).toBeVisible({ timeout: 30_000 })
  await page.locator('[data-onboarding-id="landing-start-research"]').click()
  await expect(page.locator('[data-onboarding-id="experiment-launch-dialog"]')).toBeVisible({ timeout: 30_000 })
  await page.locator('[data-onboarding-id="launch-mode-autonomous-card"]').click()
  await expect(page.getByRole('dialog')).toBeVisible({ timeout: 20_000 })
}

test.describe('start research required fields', () => {
  test('create remains clickable and missing required fields trigger a validation dialog plus field focus', async ({ page }) => {
    await openAutonomousDialog(page)

    const titleInput = page.locator('[data-onboarding-id="start-research-title"] input')
    const goalTextarea = page.locator('[data-onboarding-id="start-research-goal"] textarea')

    await titleInput.fill('')
    await goalTextarea.fill('')

    const createButton = page.locator('[data-onboarding-id="start-research-create"]')
    await expect(createButton).toBeEnabled()
    await createButton.click()

    await expect(page.getByText('还有必填项未填写')).toBeVisible({ timeout: 10_000 })
    await expect(goalTextarea).toBeInViewport()
  })
})
