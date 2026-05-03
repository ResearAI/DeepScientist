import * as React from 'react'

import { MarkdownDocument } from '@/components/plugins/MarkdownDocument'
import { SettingsGuideCard } from '@/components/settings/SettingsGuideCard'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { createAdminIssue, createAdminIssueDraft } from '@/lib/api/admin'
import { useI18n } from '@/lib/i18n/useI18n'
import { useAdminIssueDraftStore } from '@/lib/stores/admin-issue-draft'
import { pickAdminCopy } from '@/components/settings/settingsOpsCopy'
import type { AdminIssueCreatePayload } from '@/lib/types/admin'

const surfaceClassName =
  'rounded-[28px] border border-black/[0.06] bg-[rgba(255,251,246,0.76)] shadow-[0_18px_40px_-30px_rgba(18,24,32,0.24)] backdrop-blur-sm dark:border-white/[0.08] dark:bg-white/[0.03]'
const dividerClassName = 'border-black/[0.06] dark:border-white/[0.08]'
const defaultIssueBase = 'https://github.com/ResearAI/DeepScientist/issues/new'

const PAGE_COPY = {
  en: {
    title: 'Issue Report',
    subtitle: 'Turn local errors, logs, and detected system settings into a GitHub issue draft, then create or open it in one click.',
    guide: `
### What this page is for

- Use **Issue Report** to turn local errors and logs into a GitHub issue draft.
- The page keeps one live draft so you can review and edit it before creating the issue or opening GitHub.

### What gets collected

- device and hardware snapshot
- safe detected system settings
- local runtime health
- degraded connectors
- recent runtime failures
- failed admin tasks
- cached doctor summary when available
- suggested fixes and workarounds inferred from known failures

### Operator workflow

1. add or refine a short summary and notes if needed
2. refresh the draft if you want to regenerate it from the latest local errors and logs
3. adjust the generated title or markdown body only if you need a final edit
4. click **Create GitHub Issue** to create it through the local authenticated GitHub CLI, or **Open GitHub Draft** for the browser fallback
`,
    draftTitle: 'GitHub Issue Draft',
    summaryPlaceholder: 'Optional short summary line',
    notesPlaceholder: 'Optional operator notes to include in the generated issue.',
    issueTitleLabel: 'Issue Title',
    issueBodyLabel: 'Issue Body',
    issueTitlePlaceholder: 'Issue title',
    refreshDraft: 'Refresh Draft',
    createIssue: 'Create GitHub Issue',
    openDraft: 'Open GitHub Draft',
    createSuccess: 'Created GitHub issue:',
    createFallback: 'Issue was not created. Open the GitHub draft or authenticate the local `gh` CLI, then retry.',
    markdownPreview: 'Markdown Preview',
    emptyDraft: '_No issue draft yet._',
  },
  zh: {
    title: '问题报告',
    subtitle: '把本地错误、日志和检测到的系统设置整理成 GitHub issue 草稿，然后一键创建或打开。',
    guide: `
### 这一页用来做什么

- 用 **问题报告** 把本地错误和日志整理成 GitHub issue 草稿。
- 页面只保留一份当前草稿，方便你检查和修改后再创建 issue 或打开 GitHub。

### 会收集什么

- 设备与硬件快照
- 安全的系统设置检测结果
- 本地运行时健康状态
- 退化连接器
- 最近运行时失败
- 失败的 admin 任务
- 如果存在，则包含缓存的 Doctor 摘要
- 根据已知失败自动推断的推荐修复方案 / 临时绕过方案

### 使用流程

1. 如有需要，补充或修改简短总结与备注
2. 如果想按最新的本地错误和日志重新生成，就刷新草稿
3. 只在需要最终微调时修改标题或 Markdown 正文
4. 点击 **创建 GitHub Issue** 通过本机已认证的 GitHub CLI 直接创建；或者点 **打开 GitHub 草稿** 使用浏览器兜底
`,
    draftTitle: 'GitHub Issue 草稿',
    summaryPlaceholder: '可选的简短总结',
    notesPlaceholder: '可选的运维备注，会一起写入生成的 issue。',
    issueTitleLabel: 'Issue 标题',
    issueBodyLabel: 'Issue 正文',
    issueTitlePlaceholder: 'Issue 标题',
    refreshDraft: '刷新草稿',
    createIssue: '创建 GitHub Issue',
    openDraft: '打开 GitHub 草稿',
    createSuccess: '已创建 GitHub issue：',
    createFallback: 'Issue 未直接创建。可以打开 GitHub 草稿，或先认证本机 `gh` CLI 后重试。',
    markdownPreview: 'Markdown 预览',
    emptyDraft: '_当前还没有 issue 草稿。_',
  },
} as const

function buildIssueUrl(base: string, title: string, body: string) {
  const params = new URLSearchParams({ title, body })
  return `${base}?${params.toString()}`
}

export function SettingsIssueReportSection() {
  const { language } = useI18n('admin')
  const copy = pickAdminCopy(language, PAGE_COPY)
  const draft = useAdminIssueDraftStore((state) => state.draft)
  const setDraft = useAdminIssueDraftStore((state) => state.setDraft)
  const updateDraft = useAdminIssueDraftStore((state) => state.updateDraft)
  const [summary, setSummary] = React.useState('')
  const [notes, setNotes] = React.useState('')
  const [loading, setLoading] = React.useState(false)
  const [creating, setCreating] = React.useState(false)
  const [createResult, setCreateResult] = React.useState<AdminIssueCreatePayload | null>(null)
  const [createError, setCreateError] = React.useState<string | null>(null)

  const generateDraft = React.useCallback(async (options?: { force?: boolean }) => {
    setLoading(true)
    try {
      const payload = await createAdminIssueDraft({
        summary: summary.trim() || undefined,
        user_notes: notes.trim() || undefined,
        include_doctor: true,
        include_logs: true,
      })
      if (!options?.force && useAdminIssueDraftStore.getState().draft) {
        return
      }
      setDraft(payload)
    } finally {
      setLoading(false)
    }
  }, [notes, setDraft, summary])

  React.useEffect(() => {
    if (draft) return
    void generateDraft({ force: false })
  }, [draft, generateDraft])

  const issueUrl = React.useMemo(
    () => buildIssueUrl(draft?.issue_url_base || defaultIssueBase, draft?.title || '', draft?.body_markdown || ''),
    [draft]
  )

  const handleSubmitIssue = React.useCallback(() => {
    if (!draft?.title || !draft.body_markdown) return
    window.open(issueUrl, '_blank', 'noopener,noreferrer')
  }, [draft, issueUrl])

  const handleCreateIssue = React.useCallback(async () => {
    if (!draft?.title || !draft.body_markdown) return
    setCreating(true)
    setCreateError(null)
    try {
      const result = await createAdminIssue({
        title: draft.title,
        body_markdown: draft.body_markdown,
        include_system_settings: true,
      })
      setCreateResult(result)
      if (result.created && result.issue_url) {
        window.open(result.issue_url, '_blank', 'noopener,noreferrer')
      }
    } catch (error) {
      setCreateResult(null)
      setCreateError(error instanceof Error ? error.message : 'Failed to create the GitHub issue.')
    } finally {
      setCreating(false)
    }
  }, [draft])

  return (
    <div className="space-y-5">
      <SettingsGuideCard markdown={copy.guide} />

      <section className={`${surfaceClassName} px-5 py-5`}>
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="text-sm font-medium">{copy.draftTitle}</div>
            <div className="mt-1 text-xs text-muted-foreground">{copy.subtitle}</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => void generateDraft({ force: true })} isLoading={loading}>
              {copy.refreshDraft}
            </Button>
            <Button
              type="button"
              onClick={() => void handleCreateIssue()}
              disabled={!draft?.title || !draft?.body_markdown}
              isLoading={creating}
              className="bg-black text-white hover:bg-black/90 dark:bg-black dark:text-white dark:hover:bg-black/90"
            >
              {copy.createIssue}
            </Button>
            <Button type="button" variant="outline" onClick={handleSubmitIssue} disabled={!draft?.title || !draft?.body_markdown}>
              {copy.openDraft}
            </Button>
          </div>
        </div>

        {createResult ? (
          <div className={`mt-4 rounded-2xl border ${dividerClassName} px-4 py-3 text-xs leading-6 text-soft-text-secondary`}>
            {createResult.created && createResult.issue_url ? (
              <span>
                {copy.createSuccess}{' '}
                <a className="font-medium text-foreground underline underline-offset-4" href={createResult.issue_url} target="_blank" rel="noreferrer">
                  {createResult.issue_url}
                </a>
              </span>
            ) : (
              <span>
                {copy.createFallback}{' '}
                <a className="font-medium text-foreground underline underline-offset-4" href={createResult.fallback_url || issueUrl} target="_blank" rel="noreferrer">
                  {createResult.message || copy.openDraft}
                </a>
              </span>
            )}
          </div>
        ) : createError ? (
          <div className={`mt-4 rounded-2xl border ${dividerClassName} px-4 py-3 text-xs leading-6 text-soft-text-secondary`}>
            {createError}
          </div>
        ) : null}

        <div className={`mt-5 grid gap-4 border-t ${dividerClassName} pt-5`}>
          <Input value={summary} onChange={(event) => setSummary(event.target.value)} placeholder={copy.summaryPlaceholder} />
          <Textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder={copy.notesPlaceholder} className="min-h-[120px]" />
          <div className="space-y-2">
            <div className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">{copy.issueTitleLabel}</div>
            <Input
              value={draft?.title || ''}
              onChange={(event) => updateDraft({ title: event.target.value })}
              placeholder={copy.issueTitlePlaceholder}
            />
          </div>
          <div className="space-y-2">
            <div className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">{copy.issueBodyLabel}</div>
            <Textarea
              value={draft?.body_markdown || ''}
              onChange={(event) => updateDraft({ body_markdown: event.target.value })}
              className="min-h-[640px] font-mono text-xs leading-6"
            />
          </div>
        </div>
      </section>

      <section className={`${surfaceClassName} px-5 py-5`}>
        <div className="text-sm font-medium">{copy.markdownPreview}</div>
        <div className={`mt-4 border-t ${dividerClassName} pt-4`}>
          <MarkdownDocument
            content={draft?.body_markdown || copy.emptyDraft}
            hideFrontmatter
            containerClassName="gap-0"
            bodyClassName="max-h-none overflow-visible rounded-none bg-transparent px-0 py-0 text-sm leading-7 break-words [overflow-wrap:anywhere]"
          />
        </div>
      </section>
    </div>
  )
}
