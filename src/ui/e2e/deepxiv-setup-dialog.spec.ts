import { expect, test } from '@playwright/test'

function json(body: unknown) {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  }
}

async function installLandingStubs(page: import('@playwright/test').Page) {
  page.on('pageerror', (error) => {
    throw error
  })

  await Promise.all([
    page.route('**/api/connectors/availability', async (route) => {
      await route.fulfill(json({
        has_enabled_external_connector: false,
        has_bound_external_connector: false,
        should_recommend_binding: false,
        preferred_connector_name: null,
        preferred_conversation_id: null,
        available_connectors: [],
      }))
    }),
    page.route('**/api/system/update', async (route) => {
      await route.fulfill(json({
        ok: true,
        current_version: '1.0.0',
        latest_version: '1.0.0',
        update_available: false,
        prompt_recommended: false,
        busy: false,
      }))
    }),
    page.route('**/api/auth/token', async (route) => {
      await route.fulfill(json({ token: null }))
    }),
    page.route('**/api/quest-id/next', async (route) => {
      await route.fulfill(json({ quest_id: '904' }))
    }),
    page.route('**/api/connectors', async (route) => {
      await route.fulfill(json([]))
    }),
    page.route('**/api/baselines', async (route) => {
      await route.fulfill(json([]))
    }),
    page.route('**/api/config/config', async (route) => {
      await route.fulfill(json({
        document_id: 'config',
        title: 'config.yaml',
        path: '/tmp/config.yaml',
        kind: 'code',
        scope: 'config',
        writable: true,
        encoding: 'utf-8',
        source_scope: 'config',
        content: '',
        revision: 'sha256:test-config',
        updated_at: '2026-04-19T00:00:00Z',
        meta: {
          structured_config: {
            literature: {
              deepxiv: {
                enabled: false,
                base_url: 'https://data.rag.ac.cn',
                token: null,
                token_env: 'DEEPXIV_TOKEN',
                default_result_size: 20,
                preview_characters: 5000,
                request_timeout_seconds: 90,
              },
            },
          },
        },
      }))
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
        language: 'en',
      })
    )
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

test.describe('DeepXiv setup dialog from start research', () => {
  test('uses the Step 1 token directly in Step 3 and renders only one dialog instance', async ({ page }) => {
    await openAutonomousDialog(page)

    await page.locator('[data-onboarding-id="start-research-deepxiv-setup"]').click()

    const dialog = page.locator('[data-onboarding-id="deepxiv-setup-dialog"]')
    await expect(dialog).toHaveCount(1)
    await expect(dialog).toBeVisible()

    const tokenInput = dialog.locator('input[type="password"]').first()
    await tokenInput.fill('token-first-pass')
    await page.getByRole('button', { name: /Next|下一步/ }).click()
    await page.getByRole('button', { name: /Next|下一步/ }).click()

    let seenToken = ''
    await page.route('**/api/config/deepxiv/test', async (route) => {
      const body = route.request().postDataJSON() as {
        structured?: {
          literature?: {
            deepxiv?: {
              token?: string | null
            }
          }
        }
      }
      seenToken = body?.structured?.literature?.deepxiv?.token || ''
      await route.fulfill(json({
        ok: true,
        summary: 'DeepXiv returned search results for `transformers`.',
        warnings: [],
        errors: [],
        preview: '{\n  "total": 1,\n  "results": [{ "title": "Transformers" }]\n}',
      }))
    })

    await page.getByRole('button', { name: /Test `transformers`|测试 `transformers`/ }).click()
    await expect.poll(() => seenToken).toBe('token-first-pass')
    await expect(dialog.getByText('"title": "Transformers"', { exact: false })).toBeVisible({ timeout: 10_000 })
  })
})
