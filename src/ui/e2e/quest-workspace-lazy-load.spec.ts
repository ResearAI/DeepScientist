import { expect, test } from '@playwright/test'

function jsonResponse(body: unknown) {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  }
}

function workspaceRoute(path: string) {
  const baseUrl = process.env.E2E_BASE_URL || ''
  return baseUrl.includes('/ui') ? `/ui${path}` : path
}

test.describe('quest workspace lazy loading', () => {
  test('keeps canvas boot fast and defers details payloads until the details view opens', async ({
    page,
  }) => {
    const questId = 'lazy-quest-001'
    const now = '2026-04-19T12:00:00Z'
    const requests = {
      session: 0,
      explorer: 0,
      layout: 0,
      branches: 0,
      workflow: 0,
      memory: 0,
      documents: 0,
    }

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
        surface: 'quest',
        auth: {
          enabled: false,
          tokenQueryParam: 'token',
          storageKey: 'ds_local_auth_token',
        },
      }
    })

    await page.route('**/api/connectors/availability', async (route) => {
      await route.fulfill(
        jsonResponse({
          has_enabled_external_connector: false,
          has_bound_external_connector: false,
          should_recommend_binding: false,
          preferred_connector_name: null,
          preferred_conversation_id: null,
          available_connectors: [],
        })
      )
    })

    await page.route('**/api/system/update', async (route) => {
      await route.fulfill(
        jsonResponse({
          ok: true,
          current_version: '1.0.0',
          latest_version: '1.0.0',
          update_available: false,
          prompt_recommended: false,
          busy: false,
        })
      )
    })

    await page.route('**/api/auth/token', async (route) => {
      await route.fulfill(jsonResponse({ token: null }))
    })

    await page.route('**/api/connectors', async (route) => {
      await route.fulfill(jsonResponse([]))
    })

    await page.route('**/api/baselines', async (route) => {
      await route.fulfill(jsonResponse([]))
    })

    await page.route(`**/api/quests/${questId}/session`, async (route) => {
      requests.session += 1
      await route.fulfill(
        jsonResponse({
          ok: true,
          quest_id: questId,
          snapshot: {
            quest_id: questId,
            title: 'Lazy Load Quest',
            status: 'idle',
            runtime_status: 'idle',
            workspace_mode: 'copilot',
            active_anchor: 'idea',
            branch: 'main',
            head: 'abc1234',
            updated_at: now,
            counts: {
              bash_running_count: 0,
              artifacts: 0,
              memory_cards: 0,
            },
            summary: {
              status_line: 'Ready for inspection',
            },
          },
          acp_session: {
            session_id: `quest:${questId}`,
            slash_commands: [],
            meta: {
              default_reply_interaction_id: null,
            },
          },
        })
      )
    })

    await page.route(`**/api/quests/${questId}/events**`, async (route) => {
      const url = new URL(route.request().url())
      const accept = String(route.request().headers().accept || '')
      const streamRequested = url.searchParams.get('stream') === '1' || accept.includes('text/event-stream')
      if (streamRequested) {
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: 'event: cursor\ndata: {"cursor":0}\n\n',
        })
        return
      }
      await route.fulfill(
        jsonResponse({
          cursor: 0,
          oldest_cursor: 0,
          newest_cursor: 0,
          has_more: false,
          acp_updates: [],
        })
      )
    })

    await page.route(`**/api/quests/${questId}/explorer**`, async (route) => {
      requests.explorer += 1
      await route.fulfill(
        jsonResponse({
          quest_id: questId,
          sections: [
            {
              id: 'workspace',
              title: 'Workspace',
              nodes: [
                {
                  id: 'brief-md',
                  name: 'brief.md',
                  path: 'brief.md',
                  kind: 'file',
                  scope: 'workspace',
                  document_id: 'path::brief.md',
                  open_kind: 'markdown',
                  updated_at: now,
                  size: 128,
                },
              ],
            },
          ],
        })
      )
    })

    await page.route(`**/api/quests/${questId}/layout`, async (route) => {
      requests.layout += 1
      await route.fulfill(
        jsonResponse({
          layout_json: {},
          updated_at: now,
        })
      )
    })

    await page.route(`**/api/quests/${questId}/git/branches`, async (route) => {
      requests.branches += 1
      await route.fulfill(
        jsonResponse({
          quest_id: questId,
          default_ref: 'main',
          current_ref: 'main',
          workspace_mode: 'copilot',
          head: 'abc1234',
          nodes: [],
          edges: [],
          projection_status: {
            state: 'ready',
            generated_at: now,
          },
        })
      )
    })

    await page.route(`**/api/quests/${questId}/workflow`, async (route) => {
      requests.workflow += 1
      await route.fulfill(
        jsonResponse({
          quest_id: questId,
          entries: [],
          changed_files: [],
          projection_status: {
            state: 'ready',
            generated_at: now,
          },
          optimization_frontier: null,
        })
      )
    })

    await page.route(`**/api/quests/${questId}/memory`, async (route) => {
      requests.memory += 1
      await route.fulfill(jsonResponse([]))
    })

    await page.route(`**/api/quests/${questId}/documents`, async (route) => {
      requests.documents += 1
      await route.fulfill(jsonResponse([]))
    })

    await page.goto(workspaceRoute(`/projects/${questId}`))

    await expect(page.locator('.lab-quest-graph-node').first()).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('[data-onboarding-id="workspace-explorer"]')).toBeVisible()

    expect(requests.session).toBeGreaterThan(0)
    expect(requests.explorer).toBeGreaterThan(0)
    expect(requests.layout).toBeGreaterThan(0)
    expect(requests.workflow).toBe(0)
    expect(requests.memory).toBe(0)
    expect(requests.documents).toBe(0)

    await page.locator('[data-onboarding-id="quest-workspace-tab-details"]').click()

    await expect.poll(() => requests.workflow > 0).toBe(true)
    await expect.poll(() => requests.memory > 0).toBe(true)
    await expect.poll(() => requests.documents > 0).toBe(true)
    await expect.poll(() => requests.branches > 0).toBe(true)
  })
})
