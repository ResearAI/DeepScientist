// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { handleUIEffect } from '@/lib/ai/effect-dispatcher'
import { useAdminIssueDraftStore } from '@/lib/stores/admin-issue-draft'

describe('handleUIEffect route:navigate', () => {
  beforeEach(() => {
    useAdminIssueDraftStore.getState().clearDraft()
  })

  it('stores the prefilled issue draft and dispatches a route navigation event', () => {
    const listener = vi.fn()
    window.addEventListener('ds:route:navigate', listener as EventListener)

    handleUIEffect({
      name: 'route:navigate',
      data: {
        to: '/settings/issues',
        issueDraft: {
          ok: true,
          title: 'Prefilled issue title',
          body_markdown: '# Summary\n\nPrefilled body\n',
          issue_url_base: 'https://github.com/ResearAI/DeepScientist/issues/new',
          repo_url: 'https://github.com/ResearAI/DeepScientist',
          generated_at: '2026-04-14T00:00:00+00:00',
        },
      },
    })

    const draft = useAdminIssueDraftStore.getState().draft
    expect(draft?.title).toBe('Prefilled issue title')
    expect(draft?.body_markdown).toContain('Prefilled body')
    expect(listener).toHaveBeenCalledTimes(1)
    const event = listener.mock.calls[0][0] as CustomEvent<{ to: string }>
    expect(event.detail.to).toBe('/settings/issues')

    window.removeEventListener('ds:route:navigate', listener as EventListener)
  })

  it('dispatches start setup form patch events', () => {
    const listener = vi.fn()
    window.addEventListener('ds:start-setup:patch', listener as EventListener)

    handleUIEffect({
      name: 'start_setup:patch',
      data: {
        patch: {
          title: 'Bench Demo Autonomous Research',
          goal: 'Run the benchmark faithfully.',
        },
        message: 'Prepared the start form.',
      },
    })

    expect(listener).toHaveBeenCalledTimes(1)
    const event = listener.mock.calls[0][0] as CustomEvent<{ patch: Record<string, unknown> }>
    expect(event.detail.patch.title).toBe('Bench Demo Autonomous Research')
    expect(event.detail.patch.goal).toBe('Run the benchmark faithfully.')

    window.removeEventListener('ds:start-setup:patch', listener as EventListener)
  })
})
