import { expect, test } from '@playwright/test'

test.describe('CreateProjectDialog button enable after agent completion', () => {
  test('Create button should be enabled when setup agent completes without live signals', async ({ page }) => {
    // Setup initial state
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

    // Mock API responses
    await page.route('**/api/connectors/availability', async (route) => {
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
    })

    await page.route('**/api/system/update', async (route) => {
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
        }),
      })
    })

    await page.route('**/api/auth/token', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ token: null }),
      })
    })

    await page.route('**/api/connectors', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
    })

    await page.route('**/api/baselines', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
    })

    await page.route('**/api/quest-id/next', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ quest_id: '999' }),
      })
    })

    const setupQuestId = 'setup-test-001'
    const oldTimestamp = new Date(Date.now() - 120_000).toISOString() // 2 minutes ago

    await page.route('**/api/quests', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.continue()
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          snapshot: {
            quest_id: setupQuestId,
            title: 'SetupAgent Test',
            status: 'idle',
            runtime_status: 'idle',
            workspace_mode: 'copilot',
            active_anchor: 'decision',
            active_run_id: '',
            last_tool_activity_at: oldTimestamp,
            last_transition_at: oldTimestamp,
            counts: {
              bash_running_count: 0,
            },
          },
          startup: {
            scheduled: true,
            started: true,
            queued: false,
          },
        }),
      })
    })

    await page.route(`**/api/quests/${setupQuestId}/session`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          quest_id: setupQuestId,
          snapshot: {
            quest_id: setupQuestId,
            title: 'SetupAgent Test',
            status: 'idle',
            runtime_status: 'idle',
            workspace_mode: 'copilot',
            active_anchor: 'decision',
            active_run_id: '',
            last_tool_activity_at: oldTimestamp,
            last_transition_at: oldTimestamp,
            counts: {
              bash_running_count: 0,
            },
          },
          acp_session: {
            session_id: `quest:${setupQuestId}`,
            slash_commands: [],
            meta: {
              default_reply_interaction_id: null,
            },
          },
        }),
      })
    })

    await page.route(`**/api/quests/${setupQuestId}/events**`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          cursor: 1,
          acp_updates: [
            {
              params: {
                update: {
                  cursor: 1,
                  envelope: {
                    event: 'message',
                    message: {
                      role: 'assistant',
                      content:
                        'I have prepared the launch draft for you.\n\n```start_setup_patch\n{"title":"Test Project","goal":"Test goal for validation."}\n```',
                      timestamp: Math.floor(Date.now() / 1000) - 120,
                    },
                  },
                },
              },
            },
          ],
          oldest_cursor: 1,
          newest_cursor: 1,
          has_more: false,
        }),
      })
    })

    // Navigate and open dialog
    await page.goto('/')
    await expect(page.locator('[data-onboarding-id="landing-hero"]')).toBeVisible({ timeout: 30_000 })

    // Simulate opening create dialog with setup agent
    await page.evaluate((qid) => {
      const event = new CustomEvent('ds:open-create-dialog', {
        detail: {
          setupQuestId: qid,
          setupPacket: {
            entry_id: 'test',
            project_title: 'Test Project',
            benchmark_goal: 'Test goal',
          },
        },
      })
      window.dispatchEvent(event)
    }, setupQuestId)

    // Wait for dialog to open
    await expect(page.getByText('Start Research')).toBeVisible({ timeout: 10_000 })

    // Wait a bit for the agent state to be processed
    await page.waitForTimeout(2000)

    // Check that the Create button is enabled
    const createButton = page.locator('[data-onboarding-id="start-research-create"]')
    await expect(createButton).toBeVisible({ timeout: 5_000 })

    // The button should NOT be disabled since the agent completed > 90 seconds ago
    const isDisabled = await createButton.isDisabled()
    expect(isDisabled).toBe(false)

    console.log('✓ Create button is enabled after agent completion')
  })
})
