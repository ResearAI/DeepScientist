import * as React from 'react'

import { MarkdownDocument } from '@/components/plugins/MarkdownDocument'
import { SettingsGuideCard } from '@/components/settings/SettingsGuideCard'
import { AnimatedCheckbox } from '@/components/ui/animated-checkbox'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { createAdminIssueDraft } from '@/lib/api/admin'
import { useI18n } from '@/lib/i18n/useI18n'
import { useAdminIssueDraftStore } from '@/lib/stores/admin-issue-draft'
import { pickAdminCopy } from '@/components/settings/settingsOpsCopy'

const surfaceClassName =
  'rounded-[28px] border border-black/[0.06] bg-[rgba(255,251,246,0.76)] shadow-[0_18px_40px_-30px_rgba(18,24,32,0.24)] backdrop-blur-sm dark:border-white/[0.08] dark:bg-white/[0.03]'
const dividerClassName = 'border-black/[0.06] dark:border-white/[0.08]'
const defaultIssueBase = 'https://github.com/ResearAI/DeepScientist/issues/new'

const PAGE_COPY = {
  en: {
    title: 'Issue Report',
    subtitle: 'Turn local errors and logs into a GitHub issue draft, then open the submission page in one click.',
    guide: `
### What this page is for

- Use **Issue Report** to turn local errors and logs into a GitHub issue draft.
- The page keeps one live draft so you can review and edit it before opening GitHub.

### What gets collected

- device and hardware snapshot
- local runtime health
- degraded connectors
- recent runtime failures
- failed admin tasks
- cached doctor summary when available
- detected system settings when the operator keeps them enabled
- suggested fixes and workarounds inferred from known failures

### Operator workflow

1. add or refine a short summary and notes if needed
2. refresh the draft if you want to regenerate it from the latest local errors and logs
3. keep detected system settings enabled unless you want a privacy-reduced report
4. adjust the generated title or markdown body only if you need a final edit
5. click **Submit GitHub Issue** to open the prefilled GitHub issue page
`,
    draftTitle: 'GitHub Issue Draft',
    summaryPlaceholder: 'Optional short summary line',
    notesPlaceholder: 'Optional operator notes to include in the generated issue.',
    issueTitleLabel: 'Issue Title',
    issueBodyLabel: 'Issue Body',
    issueTitlePlaceholder: 'Issue title',
    refreshDraft: 'Refresh Draft',
    submitIssue: 'Submit GitHub Issue',
    includeSystemSettingsLabel: 'Include detected system settings',
    markdownPreview: 'Markdown Preview',
    emptyDraft: '_No issue draft yet._',
  },
  zh: {
    title: '问题报告',
    subtitle: '把本地错误和日志整理成 GitHub issue 草稿，然后一键打开 GitHub 提交页。',
    guide: `
### 这一页用来做什么

- 用 **问题报告** 把本地错误和日志整理成 GitHub issue 草稿。
- 页面只保留一份当前草稿，方便你检查和修改后再打开 GitHub。

### 会收集什么

- 设备与硬件快照
- 本地运行时健康状态
- 退化连接器
- 最近运行时失败
- 失败的 admin 任务
- 如果存在，则包含缓存的 Doctor 摘要
- 当运维保持开启时，也会附带检测到的系统设置
- 根据已知失败自动推断的推荐修复方案 / 临时绕过方案

### 使用流程

1. 如有需要，补充或修改简短总结与备注
2. 如果想按最新的本地错误和日志重新生成，就刷新草稿
3. 如果想发起更保守的公开 issue，可以关闭系统设置附带项
4. 只在需要最终微调时修改标题或 Markdown 正文
5. 点击 **提交 GitHub Issue** 打开 GitHub 预填页面
`,
    draftTitle: 'GitHub Issue 草稿',
    summaryPlaceholder: '可选的简短总结',
    notesPlaceholder: '可选的运维备注，会一起写入生成的 issue。',
    issueTitleLabel: 'Issue 标题',
    issueBodyLabel: 'Issue 正文',
    issueTitlePlaceholder: 'Issue 标题',
    refreshDraft: '刷新草稿',
    submitIssue: '提交 GitHub Issue',
    includeSystemSettingsLabel: '包含检测到的系统设置',
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
  const [includeSystemSettings, setIncludeSystemSettings] = React.useState(true)
  const [loading, setLoading] = React.useState(false)
  const lastIncludeSystemSettingsRef = React.useRef(includeSystemSettings)

  const generateDraft = React.useCallback(async (options?: { force?: boolean }) => {
    setLoading(true)
    try {
      const payload = await createAdminIssueDraft({
        summary: summary.trim() || undefined,
        user_notes: notes.trim() || undefined,
        include_doctor: true,
        include_logs: true,
        include_system_settings: includeSystemSettings,
      })
      if (!options?.force && useAdminIssueDraftStore.getState().draft) {
        return
      }
      setDraft(payload)
    } finally {
      setLoading(false)
    }
  }, [includeSystemSettings, notes, setDraft, summary])

  React.useEffect(() => {
    if (draft) return
    void generateDraft({ force: false })
  }, [draft, generateDraft])

  React.useEffect(() => {
    if (!draft) {
      lastIncludeSystemSettingsRef.current = includeSystemSettings
      return
    }
    if (lastIncludeSystemSettingsRef.current === includeSystemSettings) return
    lastIncludeSystemSettingsRef.current = includeSystemSettings
    void generateDraft({ force: true })
  }, [draft, generateDraft, includeSystemSettings])

  const issueUrl = React.useMemo(
    () => buildIssueUrl(draft?.issue_url_base || defaultIssueBase, draft?.title || '', draft?.body_markdown || ''),
    [draft]
  )

  const handleSubmitIssue = React.useCallback(() => {
    if (!draft?.title || !draft.body_markdown) return
    window.open(issueUrl, '_blank', 'noopener,noreferrer')
  }, [draft, issueUrl])

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
              onClick={handleSubmitIssue}
              disabled={loading || !draft?.title || !draft?.body_markdown}
              className="bg-black text-white hover:bg-black/90 dark:bg-black dark:text-white dark:hover:bg-black/90"
            >
              {copy.submitIssue}
            </Button>
          </div>
        </div>

        <div className={`mt-5 grid gap-4 border-t ${dividerClassName} pt-5`}>
          <Input value={summary} onChange={(event) => setSummary(event.target.value)} placeholder={copy.summaryPlaceholder} />
          <Textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder={copy.notesPlaceholder} className="min-h-[120px]" />
          <AnimatedCheckbox
            checked={includeSystemSettings}
            onChange={setIncludeSystemSettings}
            label={copy.includeSystemSettingsLabel}
            size="sm"
          />
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
