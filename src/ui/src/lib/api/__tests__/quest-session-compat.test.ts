import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGetMock } = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
}))

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    get: apiGetMock,
  },
  getApiBaseUrl: () => 'http://example.com',
}))

import {
  getQuestLatestSession,
  normalizeQuestAcpUpdateEnvelope,
} from '@/lib/api/quest-session-compat'

describe('normalizeQuestAcpUpdateEnvelope', () => {
  beforeEach(() => {
    apiGetMock.mockReset()
  })

  it('extracts ui effects from structured tool result payloads', () => {
    const events = normalizeQuestAcpUpdateEnvelope({
      params: {
        sessionId: 'quest:q-issue',
        update: {
          quest_id: 'q-issue',
          cursor: 7,
          event_id: 'evt-issue',
          created_at: '2026-04-14T00:00:00+00:00',
          event_type: 'runner.tool_result',
          data: {
            tool_name: 'artifact.prepare_github_issue',
            tool_call_id: 'call-issue',
            status: 'completed',
            output: JSON.stringify({
              ok: true,
              title: 'Prefilled issue title',
              body_markdown: '# Summary\n\nPrefilled body\n',
              issue_url_base: 'https://github.com/ResearAI/DeepScientist/issues/new',
              repo_url: 'https://github.com/ResearAI/DeepScientist',
              ui_effects: [
                {
                  name: 'route:navigate',
                  data: {
                    to: '/settings/issues',
                    issueDraft: {
                      ok: true,
                      title: 'Prefilled issue title',
                      body_markdown: '# Summary\n\nPrefilled body\n',
                      issue_url_base: 'https://github.com/ResearAI/DeepScientist/issues/new',
                      repo_url: 'https://github.com/ResearAI/DeepScientist',
                    },
                  },
                },
              ],
            }),
          },
        },
      },
    })

    expect(events).toHaveLength(1)
    expect(events[0].event).toBe('tool')
    const toolData = events[0].data as {
      ui_effects?: Array<{ name: string; data: Record<string, unknown> }>
    }
    expect(toolData.ui_effects).toHaveLength(1)
    expect(toolData.ui_effects?.[0].name).toBe('route:navigate')
    expect(toolData.ui_effects?.[0].data.to).toBe('/settings/issues')
  })

  it('does not treat a terminal quest snapshot as running when the fetched tail lacks a done event', async () => {
    apiGetMock.mockImplementation((url: string) => {
      if (url === '/api/quests/q-terminal/session') {
        return Promise.resolve({
          data: {
            ok: true,
            quest_id: 'q-terminal',
            snapshot: {
              quest_id: 'q-terminal',
              title: 'Terminal quest',
              updated_at: '2026-04-15T00:00:05+00:00',
              runner: 'claude',
              workspace_mode: 'copilot',
              continuation_policy: 'manual',
              status: 'active',
              runtime_status: 'completed',
              active_run_id: null,
              stop_reason: 'runner_completed',
              summary: {},
              counts: {
                bash_running_count: 0,
              },
            },
          },
        })
      }
      if (url === '/api/quests/q-terminal/events') {
        return Promise.resolve({
          data: {
            acp_updates: [
              {
                params: {
                  sessionId: 'quest:q-terminal',
                  update: {
                    quest_id: 'q-terminal',
                    cursor: 41,
                    event_id: 'evt-tool-call',
                    created_at: '2026-04-15T00:00:01+00:00',
                    event_type: 'runner.tool_call',
                    data: {
                      tool_name: 'artifact.write_note',
                      tool_call_id: 'call-1',
                      status: 'calling',
                      args: '{"path":"SUMMARY.md"}',
                    },
                  },
                },
              },
              {
                params: {
                  sessionId: 'quest:q-terminal',
                  update: {
                    quest_id: 'q-terminal',
                    cursor: 42,
                    event_id: 'evt-final-msg',
                    created_at: '2026-04-15T00:00:04+00:00',
                    event_type: 'conversation.message',
                    message: {
                      role: 'assistant',
                      content: 'All requested changes are complete.',
                    },
                  },
                },
              },
            ],
            cursor: 42,
            has_more: false,
          },
        })
      }
      throw new Error(`Unexpected GET ${url}`)
    })

    const latest = await getQuestLatestSession('q-terminal', 80)

    expect(latest.status).toBe('completed')
    expect(latest.is_active).toBe(false)
    expect(latest.latest_message).toBe('All requested changes are complete.')
  })
})
