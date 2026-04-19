'use client'

import * as React from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BookOpen,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Ellipsis,
  File,
  FileCode2,
  FileImage,
  FileJson,
  FileText,
  FolderOpen,
  GitBranch,
  Info,
  MessageSquareText,
  Settings,
  Terminal,
  X,
} from 'lucide-react'

import { PluginRenderer } from '@/components/plugin'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { SegmentedControl, type SegmentedItem } from '@/components/ui/segmented-control'
import { client } from '@/lib/api'
import { flattenQuestExplorerPayload, openQuestDocumentAsFileNode } from '@/lib/api/quest-files'
import { useI18n } from '@/lib/i18n/useI18n'
import { useTabsStore } from '@/lib/stores/tabs'
import { buildFileTree, type FileAPIResponse, type FileNode } from '@/lib/types/file'
import type { Tab } from '@/lib/types/tab'
import { cn } from '@/lib/utils'
import type { QuestDocument } from '@/types'

import { useOpenFile } from '@/hooks/useOpenFile'
import { QuestConnectorChatView } from './QuestConnectorChatView'
import { QuestStudioTraceView } from './QuestStudioTraceView'
import type { QuestWorkspaceState } from './QuestWorkspaceSurface'
import { QuestWorkspaceSurface } from './QuestWorkspaceSurface'
import type { QuestStageSelection, QuestWorkspaceView } from './workspace-events'
import { ArxivPanel } from '@/components/arxiv'
import { supportsArxiv } from '@/lib/runtime/quest-runtime'

const QUEST_WORKSPACE_PLUGIN_ID = '@ds/plugin-quest-workspace'

type MobilePrimaryTab = 'explorer' | 'chat' | 'canvas'
type MobileOverlay = 'details' | 'memory' | 'terminal' | 'settings' | 'stage' | null
type MobileChatMode = 'chat' | 'studio'
type MobileExplorerMode = 'workspace' | 'documents'

const MOBILE_DOC_FILE_PREFIX = 'mobile-doc::'
const MOBILE_DOC_DIR_PREFIX = 'mobile-doc-dir::'

function mimeTypeFromDocumentPath(path: string, kind?: string | null) {
  if (kind === 'markdown') return 'text/markdown'
  const lower = path.toLowerCase()
  if (lower.endsWith('.md') || lower.endsWith('.markdown') || lower.endsWith('.mdx')) return 'text/markdown'
  if (lower.endsWith('.json')) return 'application/json'
  if (lower.endsWith('.yaml') || lower.endsWith('.yml')) return 'text/yaml'
  if (lower.endsWith('.py')) return 'text/x-python'
  if (lower.endsWith('.ts')) return 'text/typescript'
  if (lower.endsWith('.tsx')) return 'text/tsx'
  if (lower.endsWith('.js')) return 'text/javascript'
  if (lower.endsWith('.jsx')) return 'text/jsx'
  if (lower.endsWith('.sh')) return 'text/x-shellscript'
  if (lower.endsWith('.svg')) return 'image/svg+xml'
  if (lower.endsWith('.png')) return 'image/png'
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg'
  if (lower.endsWith('.pdf')) return 'application/pdf'
  return 'text/plain'
}

function basename(path: string) {
  const normalized = String(path || '').replace(/\\/g, '/')
  const parts = normalized.split('/').filter(Boolean)
  return parts[parts.length - 1] || normalized
}

function parentPath(path: string) {
  const normalized = String(path || '').replace(/\\/g, '/')
  const parts = normalized.split('/').filter(Boolean)
  if (parts.length <= 1) return null
  return parts.slice(0, -1).join('/')
}

function resolveDocumentRelativePath(
  projectId: string,
  document: QuestDocument,
  questRoot?: string | null
) {
  const rawPath = String(document.path || '').trim()
  if (rawPath) {
    const normalizedRoot = String(questRoot || '').trim().replace(/\\/g, '/')
    const normalizedPath = rawPath.replace(/\\/g, '/')
    if (normalizedRoot && normalizedPath.startsWith(`${normalizedRoot}/`)) {
      return normalizedPath.slice(normalizedRoot.length + 1)
    }
    const questMarker = `/quests/${projectId}/`
    const markerIndex = normalizedPath.indexOf(questMarker)
    if (markerIndex >= 0) {
      return normalizedPath.slice(markerIndex + questMarker.length)
    }
    return basename(normalizedPath)
  }
  const documentId = String(document.document_id || '').trim()
  if (documentId.startsWith('memory::')) {
    return `memory/${documentId.slice('memory::'.length)}`
  }
  if (documentId.startsWith('path::')) {
    return documentId.slice('path::'.length)
  }
  if (documentId.startsWith('questpath::')) {
    return documentId.slice('questpath::'.length)
  }
  return document.title || documentId
}

function buildMobileDocumentTree(
  projectId: string,
  documents: QuestDocument[],
  questRoot?: string | null
) {
  const now = new Date().toISOString()
  const items = new Map<string, FileAPIResponse>()
  const documentIds = new Map<string, string>()

  const ensureDirectory = (path: string) => {
    const normalized = String(path || '').replace(/\\/g, '/').trim()
    if (!normalized) return
    const parts = normalized.split('/').filter(Boolean)
    for (let index = 0; index < parts.length; index += 1) {
      const currentPath = parts.slice(0, index + 1).join('/')
      const currentId = `${MOBILE_DOC_DIR_PREFIX}${projectId}::${currentPath}`
      if (items.has(currentId)) continue
      const parent = index === 0 ? null : `${MOBILE_DOC_DIR_PREFIX}${projectId}::${parts.slice(0, index).join('/')}`
      items.set(currentId, {
        id: currentId,
        name: parts[index],
        type: 'folder',
        parent_id: parent,
        path: currentPath,
        created_at: now,
        updated_at: now,
        project_id: projectId,
      })
    }
  }

  for (const document of documents) {
    const relativePath = resolveDocumentRelativePath(projectId, document, questRoot)
    if (!relativePath) continue
    const normalizedPath = relativePath.replace(/\\/g, '/').replace(/^\/+/, '')
    const parent = parentPath(normalizedPath)
    if (parent) ensureDirectory(parent)
    const fileId = `${MOBILE_DOC_FILE_PREFIX}${projectId}::${document.document_id}`
    items.set(fileId, {
      id: fileId,
      name: basename(normalizedPath),
      type: 'file',
      parent_id: parent ? `${MOBILE_DOC_DIR_PREFIX}${projectId}::${parent}` : null,
      path: normalizedPath,
      created_at: now,
      updated_at: now,
      project_id: projectId,
      mime_type: mimeTypeFromDocumentPath(normalizedPath, document.kind),
    })
    documentIds.set(fileId, document.document_id)
  }

  return {
    nodes: buildFileTree(Array.from(items.values())),
    documentIds,
  }
}

function tabBelongsToProject(tab: Tab | null | undefined, projectId: string) {
  if (!tab) return false
  const customData = tab.context?.customData as Record<string, unknown> | undefined
  return customData?.projectId === projectId
}

function isQuestWorkspaceTab(tab: Tab | null | undefined, projectId: string) {
  return Boolean(tab && tab.pluginId === QUEST_WORKSPACE_PLUGIN_ID && tabBelongsToProject(tab, projectId))
}

function formatRelativeTime(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function formatStatusLine(workspace: QuestWorkspaceState) {
  if (workspace.error) return workspace.error
  if (workspace.connectionState === 'reconnecting') return 'Reconnecting'
  if (workspace.connectionState === 'connecting') return 'Connecting'
  if (workspace.hasLiveRun && workspace.activeToolCount > 0) {
    return `${workspace.activeToolCount} tool${workspace.activeToolCount > 1 ? 's' : ''} active`
  }
  if (workspace.hasLiveRun || workspace.streaming) return 'Working'
  return workspace.snapshot?.summary?.status_line || workspace.snapshot?.display_status || 'Ready'
}

function isParkedCopilotWorkspace(workspace: QuestWorkspaceState) {
  const snapshot = workspace.snapshot
  const workspaceMode = String(snapshot?.workspace_mode || '').trim().toLowerCase()
  const continuationPolicy = String(snapshot?.continuation_policy || '').trim().toLowerCase()
  const activeRunId = String(snapshot?.active_run_id || '').trim()
  const bashRunningCount = Number(snapshot?.counts?.bash_running_count || 0)
  const latestBashSession =
    snapshot?.summary?.latest_bash_session &&
    typeof snapshot.summary.latest_bash_session === 'object' &&
    !Array.isArray(snapshot.summary.latest_bash_session)
      ? snapshot.summary.latest_bash_session
      : null
  const latestBashKind = String((latestBashSession as Record<string, unknown> | null)?.kind || '')
    .trim()
    .toLowerCase()
  const latestBashId = String((latestBashSession as Record<string, unknown> | null)?.bash_id || '')
    .trim()
  return (
    workspaceMode === 'copilot' &&
    continuationPolicy === 'wait_for_user_or_resume' &&
    !activeRunId &&
    !workspace.loading &&
    !workspace.restoring &&
    !workspace.error &&
    (bashRunningCount === 0 ||
      (bashRunningCount === 1 &&
        latestBashKind === 'terminal' &&
        (latestBashId === '' || latestBashId === 'terminal-main')))
  )
}

function statusDotClass(workspace: QuestWorkspaceState) {
  if (workspace.error || workspace.connectionState === 'error') {
    return 'bg-[#d06c6c]'
  }
  if (workspace.hasLiveRun || workspace.streaming || workspace.activeToolCount > 0) {
    return 'bg-[#d0a85f]'
  }
  return 'bg-[#8aa2bc]'
}

function sortNodesForMobile(nodes: FileNode[]) {
  return [...nodes].sort((left, right) => {
    if (left.type !== right.type) {
      if (left.type === 'folder') return -1
      if (right.type === 'folder') return 1
    }
    return left.name.localeCompare(right.name, undefined, { numeric: true, sensitivity: 'base' })
  })
}

function isImageFile(node: FileNode) {
  const mime = String(node.mimeType || '').toLowerCase()
  const path = String(node.path || node.name || '').toLowerCase()
  return (
    mime.startsWith('image/') ||
    /\.(png|jpe?g|gif|webp|svg|bmp|ico|avif)$/i.test(path)
  )
}

function isJsonFile(node: FileNode) {
  const mime = String(node.mimeType || '').toLowerCase()
  const path = String(node.path || node.name || '').toLowerCase()
  return mime.includes('json') || /\.(json|jsonl)$/i.test(path)
}

function isMarkdownFile(node: FileNode) {
  const mime = String(node.mimeType || '').toLowerCase()
  const path = String(node.path || node.name || '').toLowerCase()
  return mime.includes('markdown') || /\.(md|markdown|mdx|txt)$/i.test(path)
}

function isCodeFile(node: FileNode) {
  const mime = String(node.mimeType || '').toLowerCase()
  const path = String(node.path || node.name || '').toLowerCase()
  return (
    mime.startsWith('text/') ||
    /\.(py|ts|tsx|js|jsx|sh|bash|zsh|yml|yaml|toml|ini|cfg|conf|c|cc|cpp|h|hpp|rs|go|java|kt|swift|css|scss|html|sql)$/i.test(
      path
    )
  )
}

function iconForFileNode(node: FileNode) {
  if (node.type === 'folder') return FolderOpen
  if (isImageFile(node)) return FileImage
  if (isJsonFile(node)) return FileJson
  if (isMarkdownFile(node)) return FileText
  if (isCodeFile(node)) return FileCode2
  return File
}

function MobileSurface({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'mx-4 mb-3 mt-2 flex min-h-0 flex-1 flex-col overflow-hidden rounded-[28px]',
        'bg-[rgba(255,255,255,0.66)] shadow-[0_18px_42px_-28px_rgba(31,27,21,0.22)] backdrop-blur-[22px]',
        'dark:bg-[rgba(255,255,255,0.045)] dark:shadow-[0_20px_44px_-30px_rgba(0,0,0,0.62)]',
        className
      )}
    >
      {children}
    </div>
  )
}

function MobilePanelDialog({
  open,
  onOpenChange,
  title,
  children,
  fullscreen = false,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  children: React.ReactNode
  fullscreen?: boolean
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        aria-describedby={undefined}
        showCloseButton={false}
        className={cn(
          '!gap-0 !overflow-hidden !border-0 !bg-transparent !p-0 shadow-none',
          fullscreen
            ? '!left-0 !top-0 !bottom-0 !h-[100svh] !w-full !max-w-none !translate-x-0 !translate-y-0 rounded-none'
            : '!left-0 !top-auto !bottom-0 !h-[90svh] !w-full !max-w-none !translate-x-0 !translate-y-0 rounded-t-[28px] rounded-b-none'
        )}
      >
        <div
          className={cn(
            'flex h-full min-h-0 flex-col overflow-hidden bg-[linear-gradient(180deg,rgba(250,247,243,0.92),rgba(242,238,233,0.98))] shadow-[0_-24px_64px_-36px_rgba(45,42,38,0.38)] backdrop-blur-[24px]',
            'dark:bg-[linear-gradient(180deg,rgba(18,19,22,0.96),rgba(11,12,14,0.995))]',
            fullscreen ? 'rounded-none' : 'rounded-t-[28px]'
          )}
        >
          <DialogHeader className="shrink-0 px-4 pb-3 pt-[calc(env(safe-area-inset-top)+0.8rem)]">
            {!fullscreen ? (
              <div className="mb-3 flex justify-center">
                <div className="h-1.5 w-10 rounded-full bg-black/[0.10] dark:bg-white/[0.14]" />
              </div>
            ) : null}
            <div className="flex items-center justify-between gap-3">
              <DialogTitle className="truncate text-[15px] font-semibold text-[rgba(38,36,33,0.95)] dark:text-white">
                {title}
              </DialogTitle>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-9 w-9 shrink-0 rounded-full bg-black/[0.04] text-[rgba(38,36,33,0.95)] hover:bg-black/[0.06] dark:bg-white/[0.06] dark:text-white dark:hover:bg-white/[0.1]"
                onClick={() => onOpenChange(false)}
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </DialogHeader>
          <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function MobileExplorerList({
  nodes,
  loading,
  emptyLabel,
  activePath,
  onOpenFile,
}: {
  nodes: FileNode[]
  loading: boolean
  emptyLabel?: string
  activePath?: string | null
  onOpenFile: (file: FileNode) => void | Promise<void>
}) {
  const [expandedIds, setExpandedIds] = React.useState<Set<string>>(new Set())

  React.useEffect(() => {
    const availableFolderIds = new Set<string>()
    const defaultExpandedIds = new Set<string>()

    const walk = (items: FileNode[], depth: number) => {
      for (const item of sortNodesForMobile(items)) {
        if (item.type !== 'folder') continue
        availableFolderIds.add(item.id)
        if (depth < 2 || item.uiMeta?.emphasis === 'scope-root') {
          defaultExpandedIds.add(item.id)
        }
        if (item.children?.length) {
          walk(item.children, depth + 1)
        }
      }
    }

    walk(nodes, 0)
    setExpandedIds((previous) => {
      const next = new Set<string>()
      for (const id of previous) {
        if (availableFolderIds.has(id)) next.add(id)
      }
      for (const id of defaultExpandedIds) {
        next.add(id)
      }
      return next
    })
  }, [nodes])

  const toggleFolder = React.useCallback((folderId: string) => {
    setExpandedIds((previous) => {
      const next = new Set(previous)
      if (next.has(folderId)) next.delete(folderId)
      else next.add(folderId)
      return next
    })
  }, [])

  const renderRows = React.useCallback(
    (items: FileNode[], depth = 0): React.ReactNode =>
      sortNodesForMobile(items).map((node) => {
        const isFolder = node.type === 'folder'
        const isExpanded = isFolder ? expandedIds.has(node.id) : false
        const Icon = iconForFileNode(node)
        const isActive =
          !isFolder &&
          activePath &&
          (node.path === activePath ||
            basename(node.path || '') === basename(activePath))

        return (
          <React.Fragment key={node.id}>
            <button
              type="button"
              onClick={() => {
                if (isFolder) {
                  toggleFolder(node.id)
                  return
                }
                void onOpenFile(node)
              }}
              className={cn(
                'group flex w-full items-center gap-3 px-4 py-3 text-left transition',
                isActive
                  ? 'bg-[rgba(163,185,212,0.18)] text-[rgba(28,34,41,0.96)] dark:bg-[rgba(112,136,166,0.22)] dark:text-white'
                  : 'text-[rgba(44,41,38,0.92)] hover:bg-black/[0.035] dark:text-white/88 dark:hover:bg-white/[0.05]'
              )}
              style={{ paddingLeft: `${16 + depth * 16}px` }}
            >
              <span className="flex h-5 w-5 shrink-0 items-center justify-center text-[rgba(132,126,118,0.86)] dark:text-white/45">
                {isFolder ? (
                  isExpanded ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )
                ) : (
                  <span className="h-4 w-4" />
                )}
              </span>
              <span
                className={cn(
                  'flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] bg-[rgba(255,255,255,0.78)] text-[rgba(109,132,159,0.92)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.04)] dark:bg-white/[0.06] dark:text-white/75 dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)]',
                  isFolder && 'text-[rgba(183,150,91,0.94)] dark:text-[rgba(216,188,128,0.94)]',
                  isActive &&
                    'bg-[rgba(255,255,255,0.9)] text-[rgba(86,110,138,0.96)] dark:bg-white/[0.09]'
                )}
              >
                <Icon className="h-[18px] w-[18px]" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[15px] font-medium">{node.name}</span>
                {node.path && !isFolder ? (
                  <span className="mt-0.5 block truncate text-[11px] text-[rgba(125,119,112,0.8)] dark:text-white/42">
                    {node.path}
                  </span>
                ) : null}
              </span>
            </button>
            {isFolder && isExpanded && node.children?.length ? (
              <div className="border-l border-black/[0.035] dark:border-white/[0.045]">
                {renderRows(node.children, depth + 1)}
              </div>
            ) : null}
          </React.Fragment>
        )
      }),
    [activePath, expandedIds, onOpenFile, toggleFolder]
  )

  if (loading && nodes.length === 0) {
    return (
      <div className="h-full overflow-y-auto overscroll-contain px-2 pb-[calc(env(safe-area-inset-bottom)+1rem)]">
        <div className="overflow-hidden rounded-[24px] bg-[rgba(255,255,255,0.62)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.035)] dark:bg-white/[0.03] dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)]">
          {Array.from({ length: 7 }).map((_, index) => (
            <div
              key={`skeleton-${index}`}
              className="flex items-center gap-3 px-4 py-3"
            >
              <div className="h-4 w-4 rounded-full bg-black/[0.05] dark:bg-white/[0.06]" />
              <div className="flex h-9 w-9 items-center justify-center rounded-[12px] bg-white/[0.78] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.04)] dark:bg-white/[0.06] dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)]">
                <div className="h-4 w-4 rounded bg-black/[0.06] dark:bg-white/[0.08]" />
              </div>
              <div className="min-w-0 flex-1 space-y-2">
                <div
                  className="h-3 rounded-full bg-black/[0.06] dark:bg-white/[0.08]"
                  style={{ width: `${56 + (index % 3) * 12}%` }}
                />
                <div
                  className="h-2.5 rounded-full bg-black/[0.04] dark:bg-white/[0.05]"
                  style={{ width: `${34 + (index % 4) * 10}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-6">
        <div className="max-w-xs text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-[20px] bg-[linear-gradient(135deg,rgba(188,168,157,0.22),rgba(145,166,188,0.16),rgba(216,197,170,0.2))] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.3)] dark:bg-[linear-gradient(135deg,rgba(188,168,157,0.18),rgba(109,128,149,0.15),rgba(174,151,118,0.15))]">
            <FolderOpen className="h-6 w-6 text-[rgba(128,116,105,0.88)] dark:text-white/68" />
          </div>
          <div className="text-[15px] font-medium text-[rgba(44,41,38,0.9)] dark:text-white/88">
            No files yet
          </div>
          <div className="mt-2 text-[13px] leading-6 text-[rgba(107,103,97,0.78)] dark:text-white/55">
            {emptyLabel || 'Files and notes recorded during the project will appear here.'}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto overscroll-contain px-2 pb-[calc(env(safe-area-inset-bottom)+1rem)]">
      <div className="overflow-hidden rounded-[24px] bg-[rgba(255,255,255,0.62)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.035)] dark:bg-white/[0.03] dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)]">
        {renderRows(nodes)}
      </div>
    </div>
  )
}

function MobileExplorerPanel({
  projectId,
  readOnly,
  focusSelection,
  onOpenFile,
  onOpenStage,
  nodes,
  loading,
  emptyLabel,
  sourceMode,
  sourceHint,
  activePath,
}: {
  projectId: string
  readOnly?: boolean
  focusSelection: QuestStageSelection | null
  onOpenFile: (file: FileNode) => void | Promise<void>
  onOpenStage: () => void
  nodes: FileNode[]
  loading: boolean
  emptyLabel?: string
  sourceMode: MobileExplorerMode
  sourceHint?: string | null
  activePath?: string | null
}) {
  const showArxivPanel = supportsArxiv() && Boolean(projectId)
  return (
    <MobileSurface className="overflow-hidden bg-transparent shadow-none dark:bg-transparent">
      <div className="shrink-0 px-5 pb-3 pt-2">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[rgba(107,103,97,0.66)] dark:text-white/45">
              Explorer
            </div>
            <div className="mt-1 text-[22px] font-semibold tracking-[-0.03em] text-[rgba(38,36,33,0.95)] dark:text-white">
              {sourceMode === 'workspace' ? 'All project files' : 'Documents first'}
            </div>
            {sourceHint ? (
              <div className="mt-2 max-w-[32rem] text-[12px] leading-5 text-[rgba(107,103,97,0.78)] dark:text-white/55">
                {sourceHint}
              </div>
            ) : null}
            {sourceMode === 'documents' && loading ? (
              <div className="mt-1 text-[11px] leading-5 text-[rgba(107,103,97,0.78)] dark:text-white/55">
                Full workspace is still loading in the background.
              </div>
            ) : null}
            {sourceMode === 'workspace' && loading ? (
              <div className="mt-1 text-[11px] leading-5 text-[rgba(107,103,97,0.78)] dark:text-white/55">
                Refreshing workspace tree…
              </div>
            ) : null}
            {sourceMode === 'documents' && !loading ? (
              <div className="mt-1 text-[11px] leading-5 text-[rgba(107,103,97,0.78)] dark:text-white/55">
                Showing indexed project documents.
              </div>
            ) : null}
          </div>
          {focusSelection?.label ? (
            <div className="flex shrink-0 items-center gap-2 pt-1">
              {sourceMode === 'documents' ? (
                <span className="inline-flex items-center rounded-full bg-white/72 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[rgba(107,103,97,0.78)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.04)] dark:bg-white/[0.06] dark:text-white/55 dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)]">
                  Docs
                </span>
              ) : null}
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-8 rounded-full bg-white/72 px-3 text-[11px] text-[rgba(38,36,33,0.95)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.04)] hover:bg-white/90 dark:bg-white/[0.06] dark:text-white dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)] dark:hover:bg-white/[0.10]"
                onClick={onOpenStage}
              >
                {focusSelection.label}
              </Button>
            </div>
          ) : null}
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <MobileExplorerList
          nodes={nodes}
          loading={loading}
          emptyLabel={emptyLabel}
          activePath={activePath}
          onOpenFile={onOpenFile}
        />
      </div>
      {showArxivPanel ? (
        <div className="mt-3 shrink-0">
          <div className="overflow-hidden rounded-[24px] bg-[rgba(255,255,255,0.62)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.035)] dark:bg-white/[0.03] dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)]">
            <ArxivPanel projectId={projectId} readOnly={readOnly} variant="compact" />
          </div>
        </div>
      ) : null}
    </MobileSurface>
  )
}

export function MobileQuestWorkspaceShell({
  projectId,
  projectName,
  readOnly = false,
  workspace,
}: {
  projectId: string
  projectName: string
  readOnly?: boolean
  workspace: QuestWorkspaceState
}) {
  const navigate = useNavigate()
  const { t } = useI18n('workspace')
  const { openFileInTab } = useOpenFile()
  const tabs = useTabsStore((state) => state.tabs)
  const activeTabId = useTabsStore((state) => state.activeTabId)
  const setActiveTab = useTabsStore((state) => state.setActiveTab)
  const [primaryTab, setPrimaryTab] = React.useState<MobilePrimaryTab>('chat')
  const [chatMode, setChatMode] = React.useState<MobileChatMode>('studio')
  const [overlay, setOverlay] = React.useState<MobileOverlay>(null)
  const [stageSelection, setStageSelection] = React.useState<QuestStageSelection | null>(null)
  const [viewerTabId, setViewerTabId] = React.useState<string | null>(null)
  const [explorerNodes, setExplorerNodes] = React.useState<FileNode[]>([])
  const [explorerLoading, setExplorerLoading] = React.useState(false)
  const [explorerMode, setExplorerMode] = React.useState<MobileExplorerMode>('workspace')
  const [explorerHint, setExplorerHint] = React.useState<string | null>(null)
  const initializedRef = React.useRef(false)
  const explorerBootstrappedRef = React.useRef(false)
  const fullExplorerReadyRef = React.useRef(false)
  const fallbackDocumentIdsRef = React.useRef<Map<string, string>>(new Map())

  const projectTabs = React.useMemo(
    () => tabs.filter((tab) => tabBelongsToProject(tab, projectId)),
    [projectId, tabs]
  )

  const activeProjectTab = React.useMemo(
    () => projectTabs.find((tab) => tab.id === activeTabId) ?? null,
    [activeTabId, projectTabs]
  )

  const questWorkspaceTab = React.useMemo(() => {
    const candidates = projectTabs.filter((tab) => isQuestWorkspaceTab(tab, projectId))
    if (candidates.length === 0) return null
    const activeQuestTab = candidates.find((tab) => tab.id === activeTabId)
    if (activeQuestTab) return activeQuestTab
    return [...candidates].sort((left, right) => (right.lastAccessedAt || 0) - (left.lastAccessedAt || 0))[0]
  }, [activeTabId, projectId, projectTabs])

  const activeViewerTab = React.useMemo(
    () => projectTabs.find((tab) => tab.id === viewerTabId) ?? null,
    [projectTabs, viewerTabId]
  )

  React.useEffect(() => {
    const storageKey = `ds:quest:${projectId}:mobile-primary-tab`
    const stored = typeof window !== 'undefined' ? window.sessionStorage.getItem(storageKey) : null
    if (stored === 'explorer' || stored === 'chat' || stored === 'canvas') {
      setPrimaryTab(stored)
    }
  }, [projectId])

  React.useEffect(() => {
    if (typeof window === 'undefined') return
    window.sessionStorage.setItem(`ds:quest:${projectId}:mobile-primary-tab`, primaryTab)
  }, [primaryTab, projectId])

  React.useEffect(() => {
    explorerBootstrappedRef.current = false
    fullExplorerReadyRef.current = false
    fallbackDocumentIdsRef.current = new Map()
    setExplorerNodes([])
    setExplorerLoading(false)
    setExplorerMode('workspace')
    setExplorerHint(null)
  }, [projectId])

  React.useEffect(() => {
    if (!initializedRef.current) {
      initializedRef.current = true
      if (activeProjectTab && !isQuestWorkspaceTab(activeProjectTab, projectId) && questWorkspaceTab) {
        setActiveTab(questWorkspaceTab.id)
      }
      return
    }
    if (activeProjectTab && !isQuestWorkspaceTab(activeProjectTab, projectId)) {
      setViewerTabId(activeProjectTab.id)
    }
  }, [activeProjectTab, projectId, questWorkspaceTab, setActiveTab])

  React.useEffect(() => {
    if (viewerTabId && !activeViewerTab) {
      setViewerTabId(null)
    }
  }, [activeViewerTab, viewerTabId])

  const statusLine = React.useMemo(() => formatStatusLine(workspace), [workspace])
  const latestMetric = workspace.snapshot?.summary?.latest_metric
  const subtitle = React.useMemo(() => {
    if (latestMetric?.key && latestMetric.value != null) {
      return `${latestMetric.key}: ${String(latestMetric.value)}`
    }
    return formatRelativeTime(workspace.snapshot?.updated_at)
  }, [latestMetric?.key, latestMetric?.value, workspace.snapshot?.updated_at])

  const parkedCopilot = React.useMemo(() => isParkedCopilotWorkspace(workspace), [workspace])
  const effectiveHasLiveRun = parkedCopilot ? false : workspace.hasLiveRun
  const effectiveStreaming = parkedCopilot ? false : workspace.streaming
  const effectiveActiveToolCount = parkedCopilot ? 0 : workspace.activeToolCount
  const showStopButton = effectiveHasLiveRun || effectiveActiveToolCount > 0 || effectiveStreaming

  const chatItems = React.useMemo<SegmentedItem<MobileChatMode>[]>(
    () => [
      { value: 'studio', label: t('copilot_studio_tab') },
      { value: 'chat', label: t('copilot_chat_tab') },
    ],
    [t]
  )

  React.useEffect(() => {
    setChatMode('studio')
  }, [projectId])

  const handleQuestViewChange = React.useCallback(
    (view: QuestWorkspaceView, nextStageSelection?: QuestStageSelection | null) => {
      if (view === 'stage') {
        setStageSelection(nextStageSelection ?? null)
        setOverlay('stage')
        return
      }
      if (view === 'memory') {
        setOverlay('memory')
        return
      }
      if (view === 'terminal') {
        setOverlay('terminal')
        return
      }
      if (view === 'settings') {
        setOverlay('settings')
        return
      }
      if (view === 'details') {
        setOverlay('details')
        return
      }
      if (view === 'canvas') {
        setPrimaryTab('canvas')
      }
    },
    []
  )

  const handleFileOpen = React.useCallback(
    async (file: FileNode) => {
      const fallbackDocumentId = fallbackDocumentIdsRef.current.get(file.id)
      const resolvedFile = fallbackDocumentId
        ? await openQuestDocumentAsFileNode(projectId, fallbackDocumentId)
        : file
      const result = await openFileInTab(resolvedFile, {
        customData: {
          projectId,
          fileMeta: {
            updatedAt: resolvedFile.updatedAt,
            sizeBytes: resolvedFile.size,
            mimeType: resolvedFile.mimeType,
          },
        },
      })
      if (result.success && result.tabId) {
        setViewerTabId(result.tabId)
      }
    },
    [openFileInTab, projectId]
  )

  React.useEffect(() => {
    if (primaryTab !== 'explorer' || explorerBootstrappedRef.current) {
      return
    }

    explorerBootstrappedRef.current = true
    let cancelled = false
    let hasFallbackNodes = false

    const applyFallbackDocuments = (documents: QuestDocument[]) => {
      if (cancelled || fullExplorerReadyRef.current || documents.length === 0) {
        return
      }
      const fallbackTree = buildMobileDocumentTree(
        projectId,
        documents,
        workspace.snapshot?.quest_root || null
      )
      fallbackDocumentIdsRef.current = fallbackTree.documentIds
      hasFallbackNodes = fallbackTree.nodes.length > 0
      if (fallbackTree.nodes.length > 0) {
        setExplorerNodes(fallbackTree.nodes)
        setExplorerMode('documents')
        setExplorerHint('Showing a fast document index while the full workspace tree is loading.')
      }
    }

    setExplorerLoading(true)
    setExplorerHint(null)

    if (workspace.documents.length > 0) {
      applyFallbackDocuments(workspace.documents)
    } else {
      void client
        .documents(projectId)
        .then((documents) => {
          applyFallbackDocuments(documents)
        })
        .catch((error) => {
          if (cancelled || hasFallbackNodes) return
          setExplorerHint(
            error instanceof Error ? error.message : 'Failed to load indexed project documents.'
          )
        })
    }

    void client
      .explorer(projectId, { profile: 'mobile' })
      .then((payload) => {
        if (cancelled) return
        const flatTree = flattenQuestExplorerPayload(projectId, payload)
        fullExplorerReadyRef.current = true
        fallbackDocumentIdsRef.current = new Map()
        setExplorerNodes(buildFileTree(flatTree.files))
        setExplorerMode('workspace')
        setExplorerHint(null)
      })
      .catch((error) => {
        if (cancelled) return
        if (hasFallbackNodes) {
          setExplorerHint('Full workspace tree is unavailable right now. Showing indexed documents.')
          return
        }
        setExplorerHint(error instanceof Error ? error.message : 'Failed to load workspace tree.')
      })
      .finally(() => {
        if (cancelled) return
        setExplorerLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [primaryTab, projectId, workspace.documents, workspace.snapshot?.quest_root])

  const handleBack = React.useCallback(() => {
    if (window.history.length > 1) {
      navigate(-1)
      return
    }
    navigate('/')
  }, [navigate])

  const closeViewer = React.useCallback(() => {
    setViewerTabId(null)
    if (questWorkspaceTab) {
      setActiveTab(questWorkspaceTab.id)
    }
  }, [questWorkspaceTab, setActiveTab])

  const canvasLooksEmpty = React.useMemo(() => {
    return (
      (workspace.snapshot?.history_count || 0) === 0 &&
      (workspace.snapshot?.recent_artifacts?.length || 0) === 0 &&
      (workspace.snapshot?.recent_runs?.length || 0) === 0
    )
  }, [workspace.snapshot?.history_count, workspace.snapshot?.recent_artifacts, workspace.snapshot?.recent_runs])

  return (
    <div className="relative flex h-[100svh] max-h-[100svh] flex-col overflow-hidden bg-[linear-gradient(180deg,#F4F0EB_0%,#EEE7DF_52%,#E8E2DA_100%)] dark:bg-[linear-gradient(180deg,#0C0D10,#101216)] lg:hidden">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -left-14 top-[-5rem] h-56 w-56 rounded-full bg-[radial-gradient(circle,rgba(164,182,204,0.26)_0%,rgba(164,182,204,0.12)_36%,transparent_72%)] blur-2xl" />
        <div className="absolute right-[-3rem] top-24 h-52 w-52 rounded-full bg-[radial-gradient(circle,rgba(216,196,171,0.3)_0%,rgba(216,196,171,0.12)_40%,transparent_72%)] blur-2xl" />
        <div className="absolute bottom-14 left-1/4 h-44 w-44 rounded-full bg-[radial-gradient(circle,rgba(188,164,173,0.18)_0%,rgba(188,164,173,0.08)_42%,transparent_74%)] blur-2xl" />
      </div>
      <header className="shrink-0 px-3 pb-3 pt-[calc(env(safe-area-inset-top)+0.65rem)]">
        <div className="grid grid-cols-[44px_minmax(0,1fr)_88px] items-start gap-2">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-11 w-11 rounded-full bg-white/[0.62] text-[rgba(38,36,33,0.95)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.04)] hover:bg-white/[0.82] dark:bg-white/[0.06] dark:text-white dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)] dark:hover:bg-white/[0.10]"
            onClick={handleBack}
            aria-label="Back"
          >
            <ChevronLeft className="h-5 w-5" />
          </Button>

          <div className="min-w-0 pt-0.5 text-center">
            <div className="truncate text-[17px] font-semibold tracking-[-0.03em] text-[rgba(38,36,33,0.95)] dark:text-white">
              {projectName}
            </div>
            <div className="mt-1 flex items-center justify-center gap-2">
              <span className={cn('h-2 w-2 rounded-full', statusDotClass(workspace))} />
              <span className="truncate text-[12px] font-medium text-[rgba(86,80,73,0.82)] dark:text-white/62">
                {statusLine}
              </span>
              {subtitle ? (
                <span className="truncate text-[12px] text-[rgba(126,119,111,0.72)] dark:text-white/40">
                  · {subtitle}
                </span>
              ) : null}
            </div>
          </div>

          <div className="flex items-center justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-11 w-11 rounded-full bg-white/[0.62] text-[rgba(38,36,33,0.95)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.04)] hover:bg-white/[0.82] dark:bg-white/[0.06] dark:text-white dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)] dark:hover:bg-white/[0.10]"
              onClick={() => setOverlay('details')}
              aria-label={t('quest_workspace_details')}
            >
              <Info className="h-[18px] w-[18px]" />
            </Button>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-11 w-11 rounded-full bg-white/[0.62] text-[rgba(38,36,33,0.95)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.04)] hover:bg-white/[0.82] dark:bg-white/[0.06] dark:text-white dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)] dark:hover:bg-white/[0.10]"
                  aria-label="More"
                >
                  <Ellipsis className="h-[18px] w-[18px]" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                className="w-48 rounded-[22px] border-0 bg-[rgba(255,255,255,0.88)] p-2 shadow-[0_18px_48px_-28px_rgba(23,19,13,0.32)] backdrop-blur-xl dark:bg-[rgba(22,24,28,0.92)]"
              >
                <DropdownMenuItem className="rounded-2xl" onClick={() => setOverlay('memory')}>
                  <BookOpen className="mr-2 h-4 w-4" />
                  {t('quest_workspace_memory')}
                </DropdownMenuItem>
                <DropdownMenuItem className="rounded-2xl" onClick={() => setOverlay('terminal')}>
                  <Terminal className="mr-2 h-4 w-4" />
                  {t('quest_workspace_terminal')}
                </DropdownMenuItem>
                <DropdownMenuItem className="rounded-2xl" onClick={() => setOverlay('settings')}>
                  <Settings className="mr-2 h-4 w-4" />
                  {t('quest_workspace_settings')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </header>

      <main className="relative z-[1] flex min-h-0 flex-1 flex-col overflow-hidden">
        {primaryTab === 'chat' ? (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-3 pb-2">
            <div className="shrink-0 px-2 pb-3 pt-1">
              <SegmentedControl
                value={chatMode}
                onValueChange={(value) => setChatMode(value as MobileChatMode)}
                items={chatItems}
                size="sm"
                ariaLabel={t('copilot_mode_tabs')}
                className="w-full border-0 bg-[rgba(255,255,255,0.62)] shadow-[0_14px_32px_-28px_rgba(28,22,15,0.18),inset_0_0_0_1px_rgba(255,255,255,0.38)] backdrop-blur-[18px] dark:bg-white/[0.06] dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)]"
              />
            </div>
            <div className="min-h-0 flex-1 overflow-hidden rounded-[34px] bg-[linear-gradient(180deg,rgba(255,255,255,0.46),rgba(255,255,255,0.3))] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.34),0_18px_40px_-34px_rgba(28,22,15,0.22)] backdrop-blur-[18px] dark:bg-[linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.02))] dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)]">
              <div className="h-full min-h-0 overflow-hidden [&_.feed-scrollbar]:px-4 [&_.feed-scrollbar]:pt-4 [&_textarea]:border-0 [&_textarea]:bg-white/[0.82] [&_textarea]:shadow-[0_14px_30px_-26px_rgba(28,22,15,0.18),inset_0_0_0_1px_rgba(0,0,0,0.04)] dark:[&_textarea]:bg-white/[0.05]">
                {chatMode === 'chat' ? (
                  <QuestConnectorChatView
                    questId={projectId}
                    feed={workspace.feed}
                    loading={workspace.loading}
                    restoring={workspace.restoring}
                    streaming={effectiveStreaming}
                    activeToolCount={effectiveActiveToolCount}
                    connectionState={workspace.connectionState}
                    error={workspace.error}
                    stopping={false}
                    showStopButton={showStopButton}
                    slashCommands={workspace.slashCommands}
                    hasOlderHistory={workspace.hasOlderHistory}
                    loadingOlderHistory={workspace.loadingOlderHistory}
                    onLoadOlderHistory={workspace.loadOlderHistory}
                    onSubmit={workspace.submit}
                    onReadNow={workspace.readNow}
                    onWithdraw={workspace.withdraw}
                    onStopRun={workspace.stopRun}
                  />
                ) : (
                  <QuestStudioTraceView
                    questId={projectId}
                    feed={workspace.feed}
                    snapshot={workspace.snapshot}
                    loading={workspace.loading}
                    restoring={workspace.restoring}
                    streaming={effectiveStreaming}
                    activeToolCount={effectiveActiveToolCount}
                    connectionState={workspace.connectionState}
                    error={workspace.error}
                    stopping={false}
                    showStopButton={showStopButton}
                    slashCommands={workspace.slashCommands}
                    hasOlderHistory={workspace.hasOlderHistory}
                    loadingOlderHistory={workspace.loadingOlderHistory}
                    onLoadOlderHistory={workspace.loadOlderHistory}
                    onSubmit={workspace.submit}
                    onReadNow={workspace.readNow}
                    onWithdraw={workspace.withdraw}
                    onStopRun={workspace.stopRun}
                  />
                )}
              </div>
            </div>
          </div>
        ) : primaryTab === 'explorer' ? (
          <MobileExplorerPanel
            projectId={projectId}
            readOnly={readOnly}
            focusSelection={stageSelection}
            onOpenFile={handleFileOpen}
            onOpenStage={() => setOverlay('stage')}
            nodes={explorerNodes}
            loading={explorerLoading}
            emptyLabel="No files available."
            sourceMode={explorerMode}
            sourceHint={explorerHint}
            activePath={
              activeViewerTab?.context.resourcePath ||
              activeViewerTab?.context.resourceName ||
              null
            }
          />
        ) : (
          <div className="relative min-h-0 flex-1 overflow-hidden px-2 pb-2">
            <div className="pointer-events-none absolute inset-x-8 top-3 z-[2] flex items-center justify-between gap-3">
              <div className="inline-flex items-center gap-2 rounded-full bg-[rgba(255,255,255,0.68)] px-3 py-1.5 text-[11px] font-medium text-[rgba(61,56,50,0.82)] shadow-[0_14px_30px_-24px_rgba(28,22,15,0.18),inset_0_0_0_1px_rgba(255,255,255,0.34)] backdrop-blur-[18px] dark:bg-[rgba(26,28,32,0.74)] dark:text-white/78 dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)]">
                <GitBranch className="h-3.5 w-3.5" />
                <span>{workspace.snapshot?.branch || 'main'}</span>
              </div>
              <div className="inline-flex items-center gap-2 rounded-full bg-[rgba(255,255,255,0.68)] px-3 py-1.5 text-[11px] font-medium text-[rgba(61,56,50,0.82)] shadow-[0_14px_30px_-24px_rgba(28,22,15,0.18),inset_0_0_0_1px_rgba(255,255,255,0.34)] backdrop-blur-[18px] dark:bg-[rgba(26,28,32,0.74)] dark:text-white/78 dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)]">
                <span className={cn('h-2 w-2 rounded-full', statusDotClass(workspace))} />
                <span>{workspace.snapshot?.display_status || 'Ready'}</span>
              </div>
            </div>
            {canvasLooksEmpty ? (
              <div className="pointer-events-none absolute inset-0 z-[1] flex items-center justify-center px-8">
                <div className="max-w-xs rounded-[28px] bg-[rgba(255,255,255,0.48)] px-6 py-5 text-center shadow-[0_20px_44px_-30px_rgba(28,22,15,0.18),inset_0_0_0_1px_rgba(255,255,255,0.34)] backdrop-blur-[20px] dark:bg-[rgba(26,28,32,0.58)] dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)]">
                  <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-[18px] bg-[linear-gradient(135deg,rgba(164,182,204,0.24),rgba(216,196,171,0.24),rgba(188,164,173,0.2))]">
                    <GitBranch className="h-5 w-5 text-[rgba(103,96,88,0.86)] dark:text-white/72" />
                  </div>
                  <div className="text-[15px] font-medium text-[rgba(44,41,38,0.92)] dark:text-white/88">
                    Canvas is ready
                  </div>
                  <div className="mt-2 text-[13px] leading-6 text-[rgba(107,103,97,0.78)] dark:text-white/55">
                    Branches, runs, and artifact milestones will appear here as the project evolves.
                  </div>
                </div>
              </div>
            ) : null}
            <div className="h-full overflow-hidden rounded-[34px] bg-[linear-gradient(180deg,rgba(255,255,255,0.18),rgba(255,255,255,0.08))] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.22)] backdrop-blur-[10px] dark:bg-transparent dark:shadow-none">
              <QuestWorkspaceSurface
                questId={projectId}
                safePaddingLeft={0}
                safePaddingRight={0}
                view="canvas"
                stageSelection={stageSelection}
                onViewChange={handleQuestViewChange}
                workspace={workspace}
              />
            </div>
          </div>
        )}
      </main>

      <div className="relative z-[2] shrink-0 px-4 pb-[calc(env(safe-area-inset-bottom)+0.7rem)] pt-2">
        <nav className="mx-auto grid grid-cols-3 gap-1 rounded-[28px] bg-[rgba(255,255,255,0.72)] p-1.5 shadow-[0_20px_40px_-26px_rgba(31,27,21,0.28)] backdrop-blur-[24px] dark:bg-[rgba(22,24,28,0.78)] dark:shadow-[0_22px_48px_-30px_rgba(0,0,0,0.62)]">
          {[
            { key: 'explorer', label: 'Explorer', icon: FolderOpen },
            { key: 'chat', label: 'Chat', icon: MessageSquareText },
            { key: 'canvas', label: 'Canvas', icon: GitBranch },
          ].map((item) => {
            const Icon = item.icon
            const active = primaryTab === item.key
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => setPrimaryTab(item.key as MobilePrimaryTab)}
                className={cn(
                  'flex min-h-[54px] flex-col items-center justify-center gap-1 rounded-[22px] px-3 py-2 text-center transition',
                  active
                    ? 'bg-[rgba(255,255,255,0.9)] text-[rgba(38,36,33,0.96)] shadow-[0_10px_22px_-18px_rgba(28,22,15,0.22)] dark:bg-white/[0.11] dark:text-white'
                    : 'text-[rgba(107,103,97,0.74)] dark:text-white/52'
                )}
              >
                <Icon className="h-[18px] w-[18px]" />
                <span className="text-[11px] font-medium tracking-[-0.01em]">{item.label}</span>
              </button>
            )
          })}
        </nav>
      </div>

      <MobilePanelDialog
        open={overlay === 'details'}
        onOpenChange={(open) => setOverlay(open ? 'details' : null)}
        title={t('quest_workspace_details')}
      >
        <QuestWorkspaceSurface
          questId={projectId}
          safePaddingLeft={0}
          safePaddingRight={0}
          view="details"
          onViewChange={handleQuestViewChange}
          workspace={workspace}
        />
      </MobilePanelDialog>

      <MobilePanelDialog
        open={overlay === 'memory'}
        onOpenChange={(open) => setOverlay(open ? 'memory' : null)}
        title={t('quest_workspace_memory')}
      >
        <QuestWorkspaceSurface
          questId={projectId}
          safePaddingLeft={0}
          safePaddingRight={0}
          view="memory"
          onViewChange={handleQuestViewChange}
          workspace={workspace}
        />
      </MobilePanelDialog>

      <MobilePanelDialog
        open={overlay === 'terminal'}
        onOpenChange={(open) => setOverlay(open ? 'terminal' : null)}
        title={t('quest_workspace_terminal')}
      >
        <QuestWorkspaceSurface
          questId={projectId}
          safePaddingLeft={0}
          safePaddingRight={0}
          view="terminal"
          onViewChange={handleQuestViewChange}
          workspace={workspace}
        />
      </MobilePanelDialog>

      <MobilePanelDialog
        open={overlay === 'settings'}
        onOpenChange={(open) => setOverlay(open ? 'settings' : null)}
        title={t('quest_workspace_settings')}
      >
        <QuestWorkspaceSurface
          questId={projectId}
          safePaddingLeft={0}
          safePaddingRight={0}
          view="settings"
          onViewChange={handleQuestViewChange}
          workspace={workspace}
        />
      </MobilePanelDialog>

      <MobilePanelDialog
        open={overlay === 'stage'}
        onOpenChange={(open) => setOverlay(open ? 'stage' : null)}
        title={stageSelection?.label || 'Node details'}
      >
        <QuestWorkspaceSurface
          questId={projectId}
          safePaddingLeft={0}
          safePaddingRight={0}
          view="stage"
          stageSelection={stageSelection}
          onViewChange={handleQuestViewChange}
          workspace={workspace}
        />
      </MobilePanelDialog>

      <MobilePanelDialog
        open={Boolean(activeViewerTab)}
        onOpenChange={(open) => {
          if (!open) closeViewer()
        }}
        title={activeViewerTab?.title || 'File'}
        fullscreen
      >
        {activeViewerTab ? (
          <div className="min-h-0 flex-1 overflow-hidden bg-[rgba(248,245,241,0.98)] dark:bg-[#0B0C0E]">
            <div className="flex h-full min-h-0 flex-col overflow-hidden">
              <div className="shrink-0 px-4 pb-3 pt-1">
                <div className="truncate text-[17px] font-semibold tracking-[-0.03em] text-[rgba(38,36,33,0.95)] dark:text-white">
                  {activeViewerTab.context.resourceName || activeViewerTab.title}
                </div>
                <div className="mt-1 truncate text-[12px] text-[rgba(107,103,97,0.74)] dark:text-white/48">
                  {activeViewerTab.context.resourcePath || activeViewerTab.context.resourceName || activeViewerTab.title}
                </div>
              </div>
              <div className="min-h-0 flex-1 overflow-hidden">
                <PluginRenderer
                  pluginId={activeViewerTab.pluginId}
                  context={activeViewerTab.context}
                  tabId={activeViewerTab.id}
                  projectId={projectId}
                />
              </div>
            </div>
          </div>
        ) : null}
      </MobilePanelDialog>
    </div>
  )
}

export default MobileQuestWorkspaceShell
