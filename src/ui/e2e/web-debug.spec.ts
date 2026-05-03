import { expect, test, type Page } from '@playwright/test'

const SECRET = 'SUPERSECRET-WEB-DEBUG'
const baseUrl = process.env.E2E_BASE_URL || 'http://127.0.0.1:20999'

function json(body: unknown) {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  }
}

async function installSettingsStubs(page: Page) {
  page.on('pageerror', (error) => {
    throw error
  })

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

  await page.route('**/api/auth/token', async (route) => {
    await route.fulfill(json({ ok: true, auth_enabled: false, token: null }))
  })
  await page.route('**/api/connectors/availability', async (route) => {
    await route.fulfill(json({
      has_enabled_external_connector: true,
      has_bound_external_connector: false,
      should_recommend_binding: false,
      preferred_connector_name: 'qq',
      preferred_conversation_id: null,
      available_connectors: [{ name: 'qq', enabled: true, connection_state: 'ready', binding_count: 0, target_count: 1 }],
    }))
  })
  await page.route('**/api/system/update', async (route) => {
    await route.fulfill(json({
      ok: true,
      current_version: '1.5.17',
      latest_version: '1.5.17',
      update_available: false,
      prompt_recommended: false,
      busy: false,
    }))
  })
  await page.route('**/api/config/files', async (route) => {
    await route.fulfill(json([
      { name: 'config', path: '/tmp/config.yaml', required: true, exists: true },
      { name: 'runners', path: '/tmp/runners.yaml', required: true, exists: true },
      { name: 'connectors', path: '/tmp/connectors.yaml', required: true, exists: true },
      { name: 'plugins', path: '/tmp/plugins.yaml', required: false, exists: true },
      { name: 'mcp_servers', path: '/tmp/mcp_servers.yaml', required: false, exists: true },
    ]))
  })
  await page.route('**/api/connectors', async (route) => {
    await route.fulfill(json([
      {
        name: 'qq',
        enabled: true,
        connection_state: 'ready',
        auth_state: 'ready',
        inbox_count: 1,
        outbox_count: 0,
        ignored_count: 0,
        target_count: 1,
        binding_count: 0,
        discovered_targets: [
          {
            conversation_id: 'qq:private:openid-test',
            connector: 'qq',
            chat_type: 'private',
            chat_id: 'openid-test',
            label: 'QQ test user',
            selectable: true,
          },
        ],
      },
      { name: 'lingzhu', enabled: false, connection_state: 'idle', auth_state: 'missing' },
    ]))
  })
  await page.route('**/api/baselines', async (route) => {
    await route.fulfill(json([{ baseline_id: 'baseline-demo', status: 'ready', summary: 'Demo baseline' }]))
  })
  await page.route('**/api/quests', async (route) => {
    await route.fulfill(json([{ quest_id: 'Q-100', title: 'Debug parity quest', status: 'idle', active_anchor: 'scout' }]))
  })
  await page.route('**/api/config/connectors', async (route) => {
    await route.fulfill(json({
      document_id: 'connectors',
      title: 'connectors.yaml',
      path: '/tmp/connectors.yaml',
      kind: 'code',
      scope: 'config',
      writable: true,
      encoding: 'utf-8',
      source_scope: 'config',
      content: `qq:\n  app_secret: ${SECRET}\n`,
      revision: 'sha256:web-debug-connectors',
      updated_at: '2026-05-02T00:00:00Z',
      meta: {
        structured_config: {
          qq: {
            enabled: true,
            app_id: 'qq-app-id',
            app_secret: SECRET,
            api_key: SECRET,
            delivery: { milestones: true },
          },
        },
      },
    }))
  })
}

test.describe('Web debug inspector', () => {
  test('shows a settings connector snapshot without leaking connector secrets', async ({ page }) => {
    await installSettingsStubs(page)
    await page.goto(`${baseUrl}/settings/connector/qq?debug=1`)

    await expect(page.getByRole('heading', { level: 2, name: 'QQ' })).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('web-debug-toggle')).toBeVisible()

    await page.getByTestId('web-debug-toggle').click()
    const debugJson = page.getByTestId('web-debug-json')
    await expect(debugJson).toBeVisible()
    await expect.poll(async () => {
      const text = (await debugJson.textContent()) || ''
      try {
        return JSON.parse(text).surface
      } catch {
        return ''
      }
    }).toBe('settings:connectors:qq')

    const text = (await debugJson.textContent()) || ''
    expect(text).not.toContain(SECRET)
    const snapshot = JSON.parse(text) as {
      surface: string
      route: { pathname: string }
      selected: { connector_label?: string | null }
      flags: { dirty?: boolean }
      redaction: { applied?: boolean; fields?: string[] }
    }
    expect(snapshot.route.pathname).toBe('/settings/connector/qq')
    expect(snapshot.selected.connector_label).toBe('QQ')
    expect(typeof snapshot.flags.dirty).toBe('boolean')
    expect(snapshot.redaction.applied).toBe(true)
    expect(snapshot.redaction.fields || []).toContain('document.content')
  })

  test('stays hidden when debug is not enabled', async ({ page }) => {
    await installSettingsStubs(page)
    await page.goto(`${baseUrl}/settings/connector/qq`)

    await expect(page.getByRole('heading', { level: 2, name: 'QQ' })).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('web-debug-inspector')).toHaveCount(0)
  })

  test('can be enabled from localStorage without a query flag', async ({ page }) => {
    await installSettingsStubs(page)
    await page.addInitScript(() => {
      window.localStorage.setItem('deepscientist.debug', '1')
    })
    await page.goto(`${baseUrl}/settings/connector/qq`)

    await expect(page.getByRole('heading', { level: 2, name: 'QQ' })).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('web-debug-toggle')).toBeVisible()
  })

  test('shows in-browser JSONL capture state when debug log is enabled', async ({ page }) => {
    await installSettingsStubs(page)
    await page.addInitScript(() => {
      window.localStorage.setItem('deepscientist.debug', '1')
      window.localStorage.setItem('deepscientist.debug.log', '1')
    })
    await page.goto(`${baseUrl}/settings/connector/qq`)

    await expect(page.getByRole('heading', { level: 2, name: 'QQ' })).toBeVisible({ timeout: 30_000 })
    await page.getByTestId('web-debug-toggle').click()
    await expect(page.getByText(/log lines/)).toBeVisible()
    await expect(page.getByRole('button', { name: 'Clear Log' })).toBeVisible()
  })
})
