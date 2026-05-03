import { expect, test, type Page } from '@playwright/test'

const baseUrl = process.env.E2E_BASE_URL || 'http://127.0.0.1:20999'

function appUrl(path: string) {
  const normalizedBase = baseUrl.replace(/\/$/, '')
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${normalizedBase}${normalizedPath}`
}

async function installCommonStubs(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      'ds:onboarding:v1',
      JSON.stringify({ firstRunHandled: true, completed: true, neverRemind: true, language: 'en' })
    )
    window.localStorage.setItem('ds:ui-language', 'en')
    ;(window as typeof window & { __DEEPSCIENTIST_RUNTIME__?: unknown }).__DEEPSCIENTIST_RUNTIME__ = {
      auth: { enabled: false, tokenQueryParam: 'token', storageKey: 'ds_local_auth_token' },
    }
  })

  await page.route('**/api/auth/token', async (route) => route.fulfill({ json: { token: null } }))
  await page.route('**/api/quests', async (route) => route.fulfill({ json: [] }))
  await page.route('**/api/baselines', async (route) => route.fulfill({ json: [] }))
  await page.route('**/api/connectors', async (route) => route.fulfill({ json: [] }))
  await page.route('**/api/connectors/availability', async (route) =>
    route.fulfill({
      json: {
        has_enabled_external_connector: false,
        has_bound_external_connector: false,
        should_recommend_binding: false,
        preferred_connector_name: null,
        preferred_conversation_id: null,
        available_connectors: [],
      },
    })
  )
  await page.route('**/api/system/update', async (route) =>
    route.fulfill({
      json: {
        ok: true,
        current_version: '1.5.17',
        latest_version: '1.5.17',
        update_available: false,
        prompt_recommended: false,
        busy: false,
        manual_update_command: 'npm install -g @researai/deepscientist@latest',
      },
    })
  )
  await page.route('**/api/config/files', async (route) =>
    route.fulfill({
      json: [
        { name: 'config', path: '/tmp/config.yaml', required: true, exists: true },
        { name: 'runners', path: '/tmp/runners.yaml', required: true, exists: true },
        { name: 'connectors', path: '/tmp/connectors.yaml', required: true, exists: true },
        { name: 'baselines', path: '/tmp/baselines.yaml', required: false, exists: true },
        { name: 'plugins', path: '/tmp/plugins.yaml', required: false, exists: true },
        { name: 'mcp_servers', path: '/tmp/mcp_servers.yaml', required: false, exists: true },
      ],
    })
  )
  await page.route('**/api/config/*', async (route) => {
    const url = new URL(route.request().url())
    const name = url.pathname.split('/').pop() || 'config'
    if (name === 'files') {
      await route.fulfill({
        json: [
          { name: 'config', path: '/tmp/config.yaml', required: true, exists: true },
          { name: 'runners', path: '/tmp/runners.yaml', required: true, exists: true },
          { name: 'connectors', path: '/tmp/connectors.yaml', required: true, exists: true },
          { name: 'baselines', path: '/tmp/baselines.yaml', required: false, exists: true },
          { name: 'plugins', path: '/tmp/plugins.yaml', required: false, exists: true },
          { name: 'mcp_servers', path: '/tmp/mcp_servers.yaml', required: false, exists: true },
        ],
      })
      return
    }
    if (route.request().method() === 'PUT') {
      await route.fulfill({ json: { ok: true, revision: `test-${name}-revision-next` } })
      return
    }
    await route.fulfill({
      json: {
        document_id: name,
        title: `${name}.yaml`,
        path: `/tmp/${name}.yaml`,
        kind: 'code',
        scope: 'config',
        writable: true,
        encoding: 'utf-8',
        source_scope: 'config',
        content: '{}',
        revision: `test-${name}-revision`,
        updated_at: new Date().toISOString(),
        meta: {
          tags: [name],
          source_kind: 'config_file',
          renderer_hint: 'code',
          help_markdown: '',
          system_testable: ['config', 'runners', 'connectors'].includes(name),
          structured_config: {},
        },
      },
    })
  })
  await page.route('**/api/docs', async (route) =>
    route.fulfill({
      json: [
        {
          document_id: 'en/00_QUICK_START.md',
          title: 'Quick Start',
          path: '/tmp/docs/en/00_QUICK_START.md',
          kind: 'markdown',
          updated_at: new Date().toISOString(),
        },
        {
          document_id: 'en/configuration/GEMINI.md',
          title: 'Gemini configuration',
          path: '/tmp/docs/en/configuration/GEMINI.md',
          kind: 'markdown',
          updated_at: new Date().toISOString(),
        },
      ],
    })
  )
  await page.route('**/api/docs/open', async (route) => {
    const body = JSON.parse(route.request().postData() || '{}')
    const documentId = String(body.document_id || 'en/00_QUICK_START.md')
    await route.fulfill({
      json: {
        document_id: documentId,
        title: documentId.includes('GEMINI') ? 'Gemini configuration' : 'Quick Start',
        path: `/tmp/docs/${documentId}`,
        kind: 'markdown',
        scope: 'system',
        writable: false,
        encoding: 'utf-8',
        source_scope: 'docs',
        updated_at: new Date().toISOString(),
        content: documentId.includes('GEMINI')
          ? '# Gemini configuration\n\nUse API keys or an OpenAI-compatible proxy.\n\n## Long command\n\n```bash\nexport GEMINI_API_KEY=test-key && codex --model gemini-2.5-pro --provider google\n```\n'
          : '# Quick Start\n\nStart with `npm install -g @researai/deepscientist`, then open Settings to configure runners.\n\n## Configure\n\nOpen the settings links for Runtime, Models, Connectors, and DeepXiv.\n',
        meta: {},
      },
    })
  })
}

test.describe('mobile navigation and onboarding', () => {
  test('shows mobile directories and tutorial highlights', async ({ page }) => {
    await installCommonStubs(page)
    await page.setViewportSize({ width: 390, height: 844 })

    await page.goto(appUrl('/docs'), { waitUntil: 'networkidle' })
    await expect(page.locator('[data-onboarding-id="docs-mobile-directory"]')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Quick Start' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Gemini configuration' })).toBeVisible()
    await expect(page.locator('[data-onboarding-id="docs-mobile-outline-button"]')).toHaveCount(0)
    await page.getByRole('button', { name: 'Gemini configuration' }).click()
    await expect(page.getByRole('heading', { name: 'Gemini configuration' }).first()).toBeVisible()
    await expect(page.locator('[data-onboarding-id="docs-mobile-directory"]')).toBeHidden()
    await expect(page.locator('[data-onboarding-id="docs-mobile-outline-button"]')).toBeVisible()
    await page.locator('[data-onboarding-id="docs-mobile-back"]').click()
    await expect(page.locator('[data-onboarding-id="docs-mobile-directory"]')).toBeVisible()
    await expect(page.locator('[data-onboarding-id="docs-mobile-outline-button"]')).toHaveCount(0)

    await page.goto(appUrl('/settings'), { waitUntil: 'networkidle' })
    await expect(page.locator('[data-onboarding-id="settings-mobile-directory"]')).toBeVisible()
    await expect(page.getByRole('button', { name: /Sessions & Hardware/ })).toBeVisible()
    await expect(page.getByRole('heading', { level: 1, name: 'Sessions & Hardware' })).toHaveCount(0)
    await page.getByRole('button', { name: /Sessions & Hardware/ }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Sessions & Hardware' })).toBeVisible()
    await expect(page.locator('[data-onboarding-id="settings-mobile-directory"]')).toBeHidden()
    await page.locator('[data-onboarding-id="settings-mobile-back"]').click()
    await expect(page.locator('[data-onboarding-id="settings-mobile-directory"]')).toBeVisible()
    await expect(page.getByRole('heading', { level: 1, name: 'Sessions & Hardware' })).toHaveCount(0)

    await page.goto(appUrl('/'), { waitUntil: 'networkidle' })
    await page.locator('[data-onboarding-id="landing-mobile-replay-tutorial"]').click()
    await expect(page.getByText(/Step\s+1\s*\/\s*\d+/i)).toBeVisible()
    await page.getByRole('button', { name: 'Next' }).click()
    await expect(page.locator('[data-onboarding-id="landing-start-research"]')).toBeVisible()
    await page.getByRole('button', { name: 'Next' }).click()
    await expect(page.locator('[data-onboarding-id="landing-benchstore"]')).toBeVisible()
    await page.getByRole('button', { name: 'Next' }).click()
    await page.getByRole('button', { name: 'Next' }).click()
    await expect(page).toHaveURL(appUrl('/'))
  })
})
