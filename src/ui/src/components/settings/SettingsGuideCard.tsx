import { BookOpenText, ChevronDown } from 'lucide-react'

import { MarkdownDocument } from '@/components/plugins/MarkdownDocument'
import { useI18n } from '@/lib/i18n/useI18n'

export function SettingsGuideCard({
  title,
  markdown,
  defaultOpen = false,
}: {
  title?: string
  markdown: string
  defaultOpen?: boolean
}) {
  const { t } = useI18n('admin')

  return (
    <details
      open={defaultOpen}
      className="group rounded-[20px] border border-black/[0.06] bg-white/[0.34] px-4 py-3 backdrop-blur-sm dark:border-white/[0.08] dark:bg-white/[0.03]"
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
        <span className="flex min-w-0 items-center gap-2">
          <BookOpenText className="h-4 w-4 shrink-0 text-[#7E8B97]" />
          <span className="truncate text-sm font-medium">{title || t('guide_title')}</span>
        </span>
        <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <div className="mt-3 border-t border-black/[0.06] pt-3 dark:border-white/[0.08]">
        <MarkdownDocument
          content={markdown}
          hideFrontmatter
          containerClassName="gap-0"
          bodyClassName="max-h-none overflow-visible rounded-none bg-transparent px-0 py-0 text-sm leading-7 break-words [overflow-wrap:anywhere]"
        />
      </div>
    </details>
  )
}
