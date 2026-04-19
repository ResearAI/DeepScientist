import { expect, test, type Page } from '@playwright/test'

const entryId = 'aisb.t3.tdc_admet'

async function installBenchStoreStubs(page: Page) {
  const setupQuestId = 'setup-bench-001'
  page.on('pageerror', (error) => {
    throw error
  })

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
        body: JSON.stringify({ quest_id: '901' }),
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
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          quest_id: setupQuestId,
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
                        '我已经根据 AI Scientist Bench 的任务信息、当前设备和本地安装路径，先帮你整理出一版启动草案。你现在可以直接检查并启动；如果你想让我改得更保守、更偏论文，或者更贴近你的实际限制，也可以直接告诉我。\n\n```start_setup_patch\n{\"title\":\"TDC ADMET Discovery Autonomous Research\",\"goal\":\"Run the benchmark faithfully and prepare an autonomous launch packet.\"}\n```',
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
    page.route('**/api/benchstore/entries', async (route) => {
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
                notes: ['Use the repository requirements file for the full dependency set.'],
              },
              image_path: '../../../AISB/image/001_aisb.t3.001_tdc_admet.jpg',
              image_url: `/api/benchstore/entries/${entryId}/image`,
              resources: {
                minimum: { cpu_cores: 8, ram_gb: 16, gpu_count: 1, gpu_vram_gb: 8 },
                recommended: { cpu_cores: 16, ram_gb: 32, gpu_count: 1, gpu_vram_gb: 16 },
              },
              compatibility: {
                recommended_ok: true,
                minimum_ok: true,
                score: 100,
                recommendation_tier: 'recommended',
                recommended_reasons: ['GPU VRAM: 16 available, need 16.'],
                minimum_reasons: ['GPU VRAM: 16 available, need 8.'],
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
    page.route(`**/api/benchstore/entries/${entryId}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          entry: {
            id: entryId,
            name: 'TDC ADMET Discovery',
            one_line: 'Evaluate whether an AI Scientist can improve molecular property prediction through hypothesis-driven experiments.',
            task_description: 'Use this benchmark to evaluate whether a research agent can generate a justified hypothesis, run the required experiments, and improve molecular property prediction.',
            recommended_when: 'Use this benchmark to test hypothesis-driven experimental improvement with real logged experiments.',
            not_recommended_when: 'Do not use this for pure reasoning or theorem proving.',
            aisb_direction: 'T3',
            task_mode: 'experiment_driven',
            requires_execution: true,
            requires_paper: true,
            source_file: 'AISB/catalog/aisb.t3.tdc_admet.yaml',
            environment: {
              python: '3.10',
              cuda: '11.8',
              pytorch: '2.1.0',
              key_packages: ['deepspeed==0.15.4', 'transformers==4.46.3'],
              notes: ['Use the repository requirements file for the full dependency set.'],
            },
            image_path: '../../../AISB/image/001_aisb.t3.001_tdc_admet.jpg',
            image_url: `/api/benchstore/entries/${entryId}/image`,
            paper: {
              title: 'TDC ADMET Discovery',
              venue: 'Benchmark Track',
              year: 2026,
              url: 'https://example.com/paper',
            },
            download: {
              url: 'https://example.com/benchmark.zip',
            },
            resources: {
              minimum: { cpu_cores: 8, ram_gb: 16, gpu_count: 1, gpu_vram_gb: 8 },
              recommended: { cpu_cores: 16, ram_gb: 32, gpu_count: 1, gpu_vram_gb: 16 },
            },
            compatibility: {
              recommended_ok: true,
              minimum_ok: true,
              score: 100,
              recommendation_tier: 'recommended',
              recommended_reasons: ['GPU VRAM: 16 available, need 16.'],
              minimum_reasons: ['GPU VRAM: 16 available, need 8.'],
              device_summary: 'CPU: Test CPU (16 logical cores) | Memory: 32GB | Disk: 120GB free on / | GPUs: 0:Test GPU 16GB | Selected GPUs: 0',
            },
            install_state: {
              status: 'installed',
              local_path: '/tmp/AISB/installs/tdc_admet',
            },
            setup_prompt_preview: 'BenchStore Autonomous Launch',
          },
        }),
      })
    }),
    page.route(`**/api/benchstore/entries/${entryId}/setup-packet`, async (route) => {
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
            constraints: [
              '- benchmark_local_path: /tmp/AISB/installs/tdc_admet',
              '- device_fit: recommended',
            ],
            suggested_form: {
              title: 'TDC ADMET Discovery Autonomous Research',
              goal: 'Run the benchmark faithfully and prepare an autonomous launch packet.',
              baseline_urls: 'https://example.com/benchmark.zip',
              paper_urls: 'https://example.com/paper',
              runtime_constraints: '- benchmark_local_path: /tmp/AISB/installs/tdc_admet\n- device_fit: recommended',
              objectives: '1. 建立可信起点。\n2. 启动全自动模式。',
              need_research_paper: true,
              research_intensity: 'balanced',
              decision_policy: 'autonomous',
              launch_mode: 'standard',
              standard_profile: 'canonical_research_graph',
              custom_profile: 'freeform',
              user_language: 'zh',
            },
            startup_instruction: 'BenchStore Autonomous Launch\n- benchmark_id: aisb.t3.tdc_admet',
          },
        }),
      })
    }),
    page.route(`**/api/benchstore/entries/${entryId}/image**`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'image/svg+xml',
        body: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 90"><rect width="160" height="90" fill="#d9c7b5"/><rect x="12" y="12" width="136" height="66" rx="10" fill="#9db9c6"/><text x="80" y="49" text-anchor="middle" font-size="12" fill="#2f2924">Bench</text></svg>',
      })
    }),
  ])
}

test.describe('benchstore storefront', () => {
  test('opens the storefront, renders the detail surface, and moves benchmark start into the autonomous dialog', async ({ page }, testInfo) => {
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

    await installBenchStoreStubs(page)
    await page.goto('/')
    await expect(page.locator('[data-onboarding-id="landing-hero"]')).toBeVisible({ timeout: 30_000 })

    await page.getByRole('button', { name: 'BenchStore' }).first().click()
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 20_000 })
    await expect(page.getByText('SetupAgent').first()).toBeVisible({ timeout: 20_000 })
    const discoveryCard = page.getByRole('button', { name: /TDC ADMET Discovery/ }).first()
    await expect(discoveryCard).toBeVisible({ timeout: 20_000 })
    await expect
      .poll(
        async () =>
          page.evaluate(() => {
            const image = document.querySelector('img')
            if (!(image instanceof HTMLImageElement)) return 0
            return image.naturalWidth
          }),
        { timeout: 20_000 }
      )
      .toBeGreaterThan(0)

    await discoveryCard.click()
    await expect(page.getByText('任务描述')).toBeVisible({ timeout: 20_000 })
    await expect(page.getByRole('button', { name: 'Start' })).toBeVisible({ timeout: 20_000 })

    await page.getByRole('button', { name: 'Start' }).click()
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 20_000 })
    await expect(page.getByText('Start Research')).toBeVisible({ timeout: 20_000 })
    await expect(page.getByText('SetupAgent').first()).toBeVisible({ timeout: 20_000 })
    const titleInput = page.locator('input').first()
    const goalTextarea = page.locator('textarea').first()
    await expect(titleInput).toHaveValue('TDC ADMET Discovery Autonomous Research', { timeout: 20_000 })
    await expect(goalTextarea).toHaveValue(/Run the benchmark faithfully and prepare an autonomous launch packet\./, { timeout: 20_000 })

    await page.screenshot({ path: testInfo.outputPath('benchstore-to-autonomous-dialog.png'), fullPage: true })
  })
})
