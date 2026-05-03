// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import { SettingsIssueReportSection } from '@/components/settings/SettingsIssueReportSection'
import { useAdminIssueDraftStore } from '@/lib/stores/admin-issue-draft'

describe('SettingsIssueReportSection', () => {
  beforeEach(() => {
    useAdminIssueDraftStore.getState().setDraft({
      ok: true,
      title: 'Prefilled issue title',
      body_markdown: '# Summary\n\nPrefilled body\n',
      issue_url_base: 'https://github.com/ResearAI/DeepScientist/issues/new',
      repo_url: 'https://github.com/ResearAI/DeepScientist',
      generated_at: '2026-04-14T00:00:00+00:00',
    })
  })

  it('renders the prefilled title and body from the shared issue draft store', () => {
    render(<SettingsIssueReportSection />)

    expect(screen.getByDisplayValue('Prefilled issue title')).toBeInTheDocument()
    const textareas = screen.getAllByRole('textbox').filter((element) => element.tagName === 'TEXTAREA') as HTMLTextAreaElement[]
    expect(textareas).toHaveLength(2)
    expect(textareas[1].value).toContain('Prefilled body')
    expect(screen.getByRole('button', { name: 'Create GitHub Issue' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open GitHub Draft' })).toBeInTheDocument()
  })
})
