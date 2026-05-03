// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react'

import { SettingsIssueReportSection } from '@/components/settings/SettingsIssueReportSection'
import { useAdminIssueDraftStore } from '@/lib/stores/admin-issue-draft'

const { createAdminIssueDraftMock } = vi.hoisted(() => ({
  createAdminIssueDraftMock: vi.fn(),
}))

vi.mock('@/lib/api/admin', () => ({
  createAdminIssueDraft: createAdminIssueDraftMock,
}))

describe('SettingsIssueReportSection', () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    createAdminIssueDraftMock.mockReset()
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
    const { getByDisplayValue, getByRole, getAllByRole } = render(<SettingsIssueReportSection />)

    expect(getByDisplayValue('Prefilled issue title')).toBeInTheDocument()
    expect(getAllByRole('textbox').some((item) => (item as HTMLTextAreaElement).value.includes('Prefilled body'))).toBe(true)
    expect(getByRole('button', { name: 'Submit GitHub Issue' })).toBeInTheDocument()
  })

  it('excludes system quirks by default and can include them on refresh', async () => {
    useAdminIssueDraftStore.getState().clearDraft()
    createAdminIssueDraftMock.mockResolvedValue({
      ok: true,
      title: 'Generated issue title',
      body_markdown: '# Summary\n\nGenerated body\n',
      issue_url_base: 'https://github.com/ResearAI/DeepScientist/issues/new',
      repo_url: 'https://github.com/ResearAI/DeepScientist',
      generated_at: '2026-04-14T00:00:00+00:00',
    })

    const { findByRole } = render(<SettingsIssueReportSection />)

    const includeSystemQuirks = await findByRole('checkbox', {
      name: 'Include system quirks',
    })
    expect(includeSystemQuirks).not.toBeChecked()

    await waitFor(() => {
      expect(createAdminIssueDraftMock).toHaveBeenCalledWith(
        expect.objectContaining({
          include_doctor: true,
          include_logs: true,
          include_system_quirks: false,
        })
      )
    })

    fireEvent.click(includeSystemQuirks)
    expect(includeSystemQuirks).toBeChecked()

    await waitFor(() => {
      expect(createAdminIssueDraftMock).toHaveBeenLastCalledWith(
        expect.objectContaining({
          include_doctor: true,
          include_logs: true,
          include_system_quirks: true,
        })
      )
    })
  })
})
