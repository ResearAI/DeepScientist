import { expect, test, type Page } from '@playwright/test'

const baseUrl = process.env.E2E_BASE_URL || 'http://127.0.0.1:20999'

function appUrl(path: string) {
  const normalizedBase = baseUrl.replace(/\/$/, '')
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${normalizedBase}${normalizedPath}`
}

function stepProgressPattern(step: number) {
  return new RegExp(`\\b(?:Step\\s+)?${step}\\s*\\/\\s*\\d+\\b`, 'i')
}

async function expectStepProgress(page: Page, step: number) {
  await expect(page.getByText(stepProgressPattern(step))).toBeVisible()
}

async function readCurrentStep(page: Page) {
  const bodyText = await page.locator('body').innerText()
  const match = bodyText.match(/\bStep\s+(\d+)\s*\/\s*(\d+)\b/i)
  return match ? { current: Number(match[1]), total: Number(match[2]) } : null
}

async function advanceToStep(page: Page, targetStep: number, maxClicks = 20) {
  for (let attempt = 0; attempt <= maxClicks; attempt += 1) {
    const step = await readCurrentStep(page)
    if (step?.current === targetStep) return
    if (step && step.current > targetStep) {
      throw new Error(`Onboarding advanced past Step ${targetStep}; current step is ${step.current}/${step.total}.`)
    }
    if (attempt === maxClicks) break
    await page.getByRole('button', { name: 'Next' }).click()
    await page.waitForTimeout(500)
  }
  throw new Error(`Unable to reach onboarding Step ${targetStep}.`)
}

function installLandingStubs(page: Page) {
  page.on('pageerror', (error) => {
    throw error
  })

  return Promise.all([
    page.route('**/api/quests', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
    }),
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
          current_version: '1.5.17',
          latest_version: '1.5.17',
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
    page.route('**/api/benchstore/entries', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          device_summary: 'CPU: Test CPU | Memory: 32GB | GPU: Test GPU 16GB',
          invalid_entries: [],
          shelves: {
            best_match_ids: ['tutorial-bench-001'],
          },
          items: [
            {
              id: 'tutorial-bench-001',
              name: 'Tutorial Benchmark',
              one_line: 'A stable benchmark fixture used by onboarding tests.',
              task_description: 'Inspect a benchmark, then hand it into the launch flow.',
              task_mode: 'experiment_driven',
              track_fit: ['llm'],
              paper: {
                title: 'Tutorial Benchmark',
                venue: 'OnboardingConf',
                year: 2026,
              },
              compatibility: {
                recommended_ok: true,
                minimum_ok: true,
                recommendation_tier: 'recommended',
                recommended_reasons: ['The current GPU is sufficient for this tutorial fixture.'],
                minimum_reasons: ['The current machine can run this tutorial fixture.'],
              },
              recommendation: {
                shelf_bucket: 'best_match',
                reasons: ['Selected as the primary onboarding tutorial benchmark.'],
              },
              resources: {
                minimum: {
                  cpu_cores: 8,
                  ram_gb: 16,
                  gpu_count: 1,
                  gpu_vram_gb: 8,
                },
                recommended: {
                  cpu_cores: 16,
                  ram_gb: 32,
                  gpu_count: 1,
                  gpu_vram_gb: 16,
                },
              },
              install_state: {
                status: 'installed',
                local_path: '/tmp/tutorial-bench-001',
              },
            },
          ],
          total: 1,
        }),
      })
    }),
    page.route('**/api/benchstore/entries/tutorial-bench-001', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          entry: {
            id: 'tutorial-bench-001',
            name: 'Tutorial Benchmark',
            one_line: 'A stable benchmark fixture used by onboarding tests.',
            task_description: 'Inspect a benchmark, then hand it into the launch flow.',
            task_mode: 'experiment_driven',
            track_fit: ['llm'],
            paper: {
              title: 'Tutorial Benchmark',
              venue: 'OnboardingConf',
              year: 2026,
            },
            compatibility: {
              recommended_ok: true,
              minimum_ok: true,
              recommendation_tier: 'recommended',
              recommended_reasons: ['The current GPU is sufficient for this tutorial fixture.'],
              minimum_reasons: ['The current machine can run this tutorial fixture.'],
            },
            recommendation: {
              shelf_bucket: 'best_match',
              reasons: ['Selected as the primary onboarding tutorial benchmark.'],
            },
            resources: {
              minimum: {
                cpu_cores: 8,
                ram_gb: 16,
                gpu_count: 1,
                gpu_vram_gb: 8,
              },
              recommended: {
                cpu_cores: 16,
                ram_gb: 32,
                gpu_count: 1,
                gpu_vram_gb: 16,
              },
            },
            install_state: {
              status: 'installed',
              local_path: '/tmp/tutorial-bench-001',
            },
          },
        }),
      })
    }),
  ])
}

async function openLandingTutorial(page: Page, locale: 'en' | 'zh' = 'en') {
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
  await page.goto(appUrl('/'))
  await expect(page.locator('[data-onboarding-id="landing-replay-tutorial"]')).toBeVisible({ timeout: 30_000 })
  await page.locator('[data-onboarding-id="landing-replay-tutorial"]').click()
}

async function openProjectTutorial(page: Page, locale: 'en' | 'zh' = 'en') {
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

  await page.goto(appUrl('/projects/demo-memory'))
  await expect(page.getByLabel('Tutorial')).toBeVisible({ timeout: 30_000 })
  await page.getByLabel('Tutorial').click()
}

async function openMobileLandingFirstRun(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.removeItem('ds:onboarding:v1')
    window.localStorage.setItem('ds:ui-language', 'en')
    ;(window as typeof window & { __DEEPSCIENTIST_RUNTIME__?: unknown }).__DEEPSCIENTIST_RUNTIME__ = {
      auth: {
        enabled: false,
        tokenQueryParam: 'token',
        storageKey: 'ds_local_auth_token',
      },
    }
  })

  await installLandingStubs(page)
  await page.goto(appUrl('/'))
  await expect(page.locator('[data-onboarding-id="landing-hero"]')).toBeVisible({ timeout: 30_000 })
}

test.describe('onboarding launch flow', () => {
  test('the landing tutorial can pass through BenchStore and reach the launch-mode dialog', async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 1000 })
    await openLandingTutorial(page, 'en')

    await expectStepProgress(page, 1)
    await expect(page.getByRole('heading', { name: 'This is the launch surface' })).toBeVisible()

    await page.getByRole('button', { name: 'Next' }).click()
    await expectStepProgress(page, 2)
    await expect(page.getByRole('heading', { name: 'These are the three main entry paths' })).toBeVisible()

    await page.getByRole('button', { name: 'Next' }).click()
    await expectStepProgress(page, 3)
    await expect(page.getByRole('heading', { name: 'Open BenchStore first' })).toBeVisible()

    await page.getByRole('button', { name: 'Next' }).click()
    await expect(page.locator('[data-onboarding-id="benchstore-dialog"]')).toBeVisible({ timeout: 30_000 })
    await expectStepProgress(page, 4)
    await expect(page.getByRole('heading', { name: 'BenchStore starts as a storefront view' })).toBeVisible()

    await advanceToStep(page, 10, 12)

    await expect(page.locator('[data-onboarding-id="experiment-launch-dialog"]')).toBeVisible({ timeout: 30_000 })
    await expectStepProgress(page, 10)
    await expect(page.getByRole('heading', { name: 'First choose between Copilot and Autonomous' })).toBeVisible()
    await expect(page.locator('[data-onboarding-id="launch-mode-copilot-card"]')).toBeVisible()
    await expect(page.locator('[data-onboarding-id="launch-mode-autonomous-card"]')).toBeVisible()
  })

  test('uses the compact mobile onboarding card on phone-sized screens', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await openMobileLandingFirstRun(page)

    await page.getByRole('button', { name: 'Close' }).click()
    await expect(page.locator('[data-onboarding-id="landing-mobile-replay-tutorial"]')).toBeVisible()
    await page.locator('[data-onboarding-id="landing-mobile-replay-tutorial"]').click()

    await expect(page.locator('[data-onboarding-id="mobile-onboarding-card"]')).toBeVisible()
    await expect(page.getByText(/Step\s+1\s*\/\s*15/i)).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Start from one clear research request' })).toBeVisible()
    await expect(page.getByLabel('Close tutorial')).toHaveCount(0)
    await expect(page.locator('[data-onboarding-id="landing-mobile-replay-tutorial"]')).toBeVisible()

    await page.locator('[data-onboarding-id="mobile-onboarding-next"]').click()
    await expect(page.getByText(/Step\s+2\s*\/\s*15/i)).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Let SetupAgent organize the launch' })).toBeVisible()

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    expect(overflow).toBeLessThanOrEqual(1)
  })

  test('the project tutorial still reaches the canvas stage with a connected graph', async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 1000 })
    await openProjectTutorial(page, 'en')

    for (let attempt = 0; attempt < 20; attempt += 1) {
      const step = await readCurrentStep(page)
      if (step && step.current >= 30) {
        break
      }
      await page.getByRole('button', { name: 'Next' }).click()
      await page.waitForTimeout(700)
    }

    await expectStepProgress(page, 30)
    await expect(page.getByRole('heading', { name: 'Canvas shows the research map' })).toBeVisible()

    const nodeCount = await page.locator('.react-flow__node').count()
    const edgeCount = await page.locator('.react-flow__edge-path').count()

    expect(nodeCount).toBeGreaterThan(5)
    expect(edgeCount).toBeGreaterThan(5)
  })
})
