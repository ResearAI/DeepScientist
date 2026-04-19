import { expect, test, type Page } from '@playwright/test'

const entryId = 'aisb.t3.tdc_admet'
const setupQuestId = 'setup-bench-running-001'

function createSetupRunningStateTracker() {
  return {
    sessionPollCount: 0,
    streamConnectionCount: 0,
    runFinishedDelivered: false,
  }
}

async function installSetupRunningStateStubs(
  page: Page,
  options?: {
    includePatchInAssistantMessage?: boolean
    finishAfterReconnect?: boolean
    exposeDurableSuggestedForm?: boolean
  },
) {
  const tracker = createSetupRunningStateTracker()
  const includePatchInAssistantMessage = options?.includePatchInAssistantMessage !== false
  const finishAfterReconnect = options?.finishAfterReconnect !== false
  const exposeDurableSuggestedForm = options?.exposeDurableSuggestedForm !== false

  await Promise.all([
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
        body: JSON.stringify({ quest_id: '902' }),
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
    page.route('**/api/quests', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          snapshot: {
            quest_id: setupQuestId,
            title: 'SetupAgent · TDC ADMET Discovery Autonomous Research',
            status: 'idle',
            workspace_mode: 'copilot',
            active_anchor: 'decision',
            continuation_policy: 'wait_for_user_or_resume',
            summary: {
              status_line: 'SetupAgent is preparing a launch draft.',
            },
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
    }),
    page.route(`**/api/quests/${setupQuestId}/session`, async (route) => {
      tracker.sessionPollCount += 1
      const stillRunning = finishAfterReconnect ? !tracker.runFinishedDelivered : true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          quest_id: setupQuestId,
          snapshot: {
            quest_id: setupQuestId,
            title: 'SetupAgent · TDC ADMET Discovery Autonomous Research',
            status: stillRunning ? 'running' : 'active',
            runtime_status: stillRunning ? 'running' : 'active',
            workspace_mode: 'copilot',
            active_anchor: 'decision',
            active_run_id: stillRunning ? 'run-setup-001' : null,
            continuation_policy: 'wait_for_user_or_resume',
            last_tool_activity_at: stillRunning
              ? new Date().toISOString()
              : '2026-04-16T00:00:00+00:00',
            startup_contract: {
              workspace_mode: 'copilot',
              launch_mode: 'custom',
              custom_profile: 'freeform',
              start_setup_session: {
                source: 'benchstore',
                locale: 'zh',
                suggested_form: exposeDurableSuggestedForm
                  ? {
                      title: 'TDC ADMET Discovery Autonomous Research',
                      goal: 'Run the benchmark faithfully and prepare an autonomous launch packet.',
                      runtime_constraints: '- benchmark_local_path: /tmp/AISB/installs/tdc_admet',
                    }
                  : {},
              },
            },
            summary: {
              status_line: stillRunning ? 'SetupAgent is still running.' : 'SetupAgent finished and is ready.',
            },
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
    }),
    page.route(`**/api/quests/${setupQuestId}/events**`, async (route) => {
      const url = new URL(route.request().url())
      if (url.searchParams.get('format') !== 'acp') {
        await route.continue()
        return
      }
      const accept = String(route.request().headers()['accept'] || '')
      if (accept.includes('text/event-stream')) {
        tracker.streamConnectionCount += 1
        const update =
          tracker.streamConnectionCount === 1 || !finishAfterReconnect
            ? {
                cursor: 1,
                envelope: {
                  event: 'acp_update',
                  data: '',
                },
                data: {
                  label: 'run_started',
                  run_id: 'run-setup-001',
                  summary: 'SetupAgent running.',
                },
              }
            : {
                cursor: 2,
                envelope: {
                  event: 'acp_update',
                  data: '',
                },
                data: {
                  label: 'run_finished',
                  run_id: 'run-setup-001',
                  summary: 'SetupAgent finished.',
                },
              }
        if (finishAfterReconnect && tracker.streamConnectionCount > 1) {
          tracker.runFinishedDelivered = true
        }
        const ssePayload = `id: ${update.cursor}\nevent: acp_update\ndata: ${JSON.stringify({ params: { update } })}\n\n`
        await route.fulfill({
          status: 200,
          headers: {
            'content-type': 'text/event-stream',
            'cache-control': 'no-cache',
            connection: 'keep-alive',
          },
          body: ssePayload,
        })
        return
      }
      const after = Number(url.searchParams.get('after') || '0')
      if (finishAfterReconnect && after > 0) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ok: true,
            cursor: 2,
            acp_updates: [
              {
                params: {
                  update: {
                    cursor: 2,
                    envelope: {
                      event: 'acp_update',
                      data: '',
                    },
                    data: {
                      label: 'run_finished',
                      run_id: 'run-setup-001',
                      summary: 'SetupAgent finished.',
                    },
                  },
                },
              },
            ],
            oldest_cursor: 1,
            newest_cursor: 2,
            has_more: false,
          }),
        })
        return
      }

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
                        content: includePatchInAssistantMessage
                          ? '我已经先整理出一版启动草案。运行结束后前端应该立刻解除运行状态，而不是继续卡住。\n\n```start_setup_patch\n{"title":"TDC ADMET Discovery Autonomous Research","goal":"Run the benchmark faithfully and prepare an autonomous launch packet."}\n```'
                          : '我已经给出结论，但这次不会再提交新的表单 patch。只要运行结束，前端也应该立刻解除锁定并允许创建。',
                        timestamp: Math.floor(Date.now() / 1000),
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
    }),
    page.route(`**/api/quests/${setupQuestId}/chat`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      })
    }),
    page.route(`**/api/quests/${setupQuestId}`, async (route) => {
      if (route.request().method() === 'DELETE') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ok: true, quest_id: setupQuestId, deleted: true }),
        })
        return
      }
      await route.continue()
    }),
    page.route('**/api/benchstore/entries**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          device_summary: 'CPU: Test CPU (16 logical cores) | Memory: 32GB | Disk: 120GB free on / | GPUs: 0:Test GPU 16GB | Selected GPUs: 0',
          invalid_entries: [],
          items: [
            {
              id: entryId,
              name: 'TDC ADMET Discovery',
              one_line: 'Evaluate whether an AI Scientist can improve molecular property prediction through hypothesis-driven experiments.',
              aisb_direction: 'T3',
              task_mode: 'experiment_driven',
              paper: {
                title: 'TDC ADMET Discovery',
                venue: 'Benchmark Track',
                year: 2026,
                url: 'https://example.com/paper',
              },
              download: {
                url: 'https://example.com/benchmark.zip',
              },
              environment: {
                python: '3.10',
                cuda: '11.8',
                pytorch: '2.1.0',
                key_packages: ['deepspeed==0.15.4', 'transformers==4.46.3'],
              },
              image_path: '../../../AISB/image/001_aisb.t3.001_tdc_admet.jpg',
              image_url: `/api/benchstore/entries/${entryId}/image`,
              compatibility: {
                recommended_ok: true,
                minimum_ok: true,
                score: 100,
                recommendation_tier: 'recommended',
                device_summary: 'CPU: Test CPU (16 logical cores) | Memory: 32GB | Disk: 120GB free on / | GPUs: 0:Test GPU 16GB | Selected GPUs: 0',
              },
              install_state: {
                status: 'installed',
                local_path: '/tmp/AISB/installs/tdc_admet',
              },
            },
          ],
          total: 1,
        }),
      })
    }),
    page.route(`**/api/benchstore/entries/${entryId}**`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          entry: {
            id: entryId,
            name: 'TDC ADMET Discovery',
            task_description: 'Use this benchmark to evaluate autonomous launch readiness.',
            image_url: `/api/benchstore/entries/${entryId}/image`,
            install_state: {
              status: 'installed',
              local_path: '/tmp/AISB/installs/tdc_admet',
            },
            setup_prompt_preview: 'BenchStore Autonomous Launch',
          },
        }),
      })
    }),
    page.route(`**/api/benchstore/entries/${entryId}/setup-packet**`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          entry_id: entryId,
          setup_packet: {
            entry_id: entryId,
            assistant_label: 'BenchStore Setup Agent · Codex',
            project_title: 'TDC ADMET Discovery Autonomous Research',
            benchmark_local_path: '/tmp/AISB/installs/tdc_admet',
            device_fit: 'recommended',
            benchmark_goal: 'Run the benchmark faithfully and prepare an autonomous launch packet.',
            constraints: ['- benchmark_local_path: /tmp/AISB/installs/tdc_admet'],
            suggested_form: {
              title: 'TDC ADMET Discovery Autonomous Research',
              goal: 'Run the benchmark faithfully and prepare an autonomous launch packet.',
              runtime_constraints: '- benchmark_local_path: /tmp/AISB/installs/tdc_admet',
              need_research_paper: true,
              research_intensity: 'balanced',
              decision_policy: 'autonomous',
              launch_mode: 'standard',
              standard_profile: 'canonical_research_graph',
              custom_profile: 'freeform',
              user_language: 'zh',
            },
          },
        }),
      })
    }),
    page.route(`**/api/benchstore/entries/${entryId}/image**`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'image/svg+xml',
        body: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 90"><rect width="160" height="90" fill="#d9c7b5"/><text x="80" y="49" text-anchor="middle" font-size="12" fill="#2f2924">Bench</text></svg>',
      })
    }),
  ])

  return tracker
}

async function openSetupAgentFlow(page: Page) {
  await page.goto('/')
  await expect(page.locator('[data-onboarding-id="landing-hero"]')).toBeVisible({ timeout: 30_000 })

  await page.locator('[data-onboarding-id="landing-benchstore"]').click({ force: true })
  await expect(page.locator('[data-onboarding-id="benchstore-dialog"]')).toBeVisible({ timeout: 20_000 })
  await page.getByRole('button', { name: 'Start' }).click({ force: true })
  await expect(page.getByText('Start Research')).toBeVisible({ timeout: 20_000 })
}

function installUiInitScript(page: Page) {
  return page.addInitScript(() => {
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
}

test.describe('setup agent running state', () => {
  test('unlocks create immediately after the setup run finishes', async ({ page }) => {
    await installUiInitScript(page)
    await installSetupRunningStateStubs(page, { includePatchInAssistantMessage: true })
    await openSetupAgentFlow(page)

    const createButton = page.getByRole('button', { name: '创建项目' })
    await expect(page.getByText('可创建').first()).toBeVisible({ timeout: 20_000 })
    await expect(createButton).toBeEnabled({ timeout: 20_000 })
  })

  test('also unlocks after finish when the setup agent only sends an answer without a new form patch', async ({ page }) => {
    await installUiInitScript(page)
    await installSetupRunningStateStubs(page, { includePatchInAssistantMessage: false })
    await openSetupAgentFlow(page)

    const createButton = page.getByRole('button', { name: '创建项目' })
    await expect(page.getByText('可创建').first()).toBeVisible({ timeout: 20_000 })
    await expect(createButton).toBeEnabled({ timeout: 20_000 })
  })

  test('unlocks once the setup agent patches the form even if the helper run is still active', async ({ page }) => {
    await installUiInitScript(page)
    await installSetupRunningStateStubs(page, {
      includePatchInAssistantMessage: false,
      finishAfterReconnect: false,
      exposeDurableSuggestedForm: false,
    })
    await openSetupAgentFlow(page)

    const createButton = page.getByRole('button', { name: '创建项目' })
    await expect(page.getByText('Start Research')).toBeVisible({ timeout: 20_000 })
    await expect(createButton).toBeDisabled({ timeout: 20_000 })
    await page.evaluate(() => {
      window.dispatchEvent(
        new CustomEvent('ds:start-setup:patch', {
          detail: {
            patch: {
              runtime_constraints: '- patched by Playwright while SetupAgent is still running',
            },
          },
        }),
      )
    })
    await expect(createButton).toBeEnabled({ timeout: 20_000 })
  })
})
