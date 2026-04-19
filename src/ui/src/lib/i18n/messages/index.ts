import type { UILanguage } from '@/lib/i18n/types'
import { commonMessages } from '@/lib/i18n/messages/common'
import { settingsMessages } from '@/lib/i18n/messages/settings'
import { labMessages } from '@/lib/i18n/messages/lab'
import { latexMessages } from '@/lib/i18n/messages/latex'
import { workspaceMessages } from '@/lib/i18n/messages/workspace'
import { searchMessages } from '@/lib/i18n/messages/search'
import { markdownViewerMessages } from '@/lib/i18n/messages/markdown_viewer'
import { notebookMessages } from '@/lib/i18n/messages/notebook'
import { pdfViewerMessages } from '@/lib/i18n/messages/pdf_viewer'
import { aiManusMessages } from '@/lib/i18n/messages/ai_manus'
import { cliMessages } from '@/lib/i18n/messages/cli'
import { docViewerMessages } from '@/lib/i18n/messages/doc_viewer'
import { codeViewerMessages } from '@/lib/i18n/messages/code_viewer'
import { adminMessages } from '@/lib/i18n/messages/admin'

export type I18nNamespace =
  | 'common'
  | 'settings'
  | 'lab'
  | 'latex'
  | 'workspace'
  | 'search'
  | 'markdown_viewer'
  | 'notebook'
  | 'pdf_viewer'
  | 'ai_manus'
  | 'cli'
  | 'doc_viewer'
  | 'code_viewer'
  | 'admin'

export type I18nMessages = Partial<Record<UILanguage, Record<string, string>>>

export const I18N_MESSAGES: Record<I18nNamespace, I18nMessages> = {
  common: commonMessages,
  settings: settingsMessages,
  lab: labMessages,
  latex: latexMessages,
  workspace: workspaceMessages,
  search: searchMessages,
  markdown_viewer: markdownViewerMessages,
  notebook: notebookMessages,
  pdf_viewer: pdfViewerMessages,
  ai_manus: aiManusMessages,
  cli: cliMessages,
  doc_viewer: docViewerMessages,
  code_viewer: codeViewerMessages,
  admin: adminMessages,
}
