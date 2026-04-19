// @vitest-environment jsdom

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SetupAgentQuestPanel } from '@/components/projects/SetupAgentQuestPanel'

const questWorkspaceMock = vi.fn()

vi.mock('@/lib/acp', () => ({
  useQuestWorkspace: (...args: unknown[]) => questWorkspaceMock(...args),
}))

vi.mock('@/components/workspace/QuestCopilotDockPanel', () => ({
  QuestCopilotDockPanel: () => <div>Dock</div>,
}))

describe('SetupAgentQuestPanel', () => {
  it('shows running when the setup quest still has a live run', () => {
    questWorkspaceMock.mockReturnValue({
      loading: false,
      hasLiveRun: true,
      streaming: false,
      activeToolCount: 1,
      snapshot: {
        runtime_status: 'running',
      },
    })

    render(<SetupAgentQuestPanel questId="B-001" locale="en" />)

    expect(screen.getByText('Running')).toBeInTheDocument()
  })

  it('shows ready when the setup quest is idle and a durable suggested form exists', () => {
    questWorkspaceMock.mockReturnValue({
      loading: false,
      hasLiveRun: false,
      streaming: false,
      activeToolCount: 0,
      snapshot: {
        runtime_status: 'active',
        startup_contract: {
          start_setup_session: {
            suggested_form: {
              title: 'Prepared setup draft',
            },
          },
        },
      },
    })

    render(<SetupAgentQuestPanel questId="B-002" locale="en" />)

    expect(screen.getByText('Ready')).toBeInTheDocument()
  })
})
