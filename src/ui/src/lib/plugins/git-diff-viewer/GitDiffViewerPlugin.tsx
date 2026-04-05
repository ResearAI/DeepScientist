'use client'

import * as React from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, GitCompare, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { buildQuestFileNodeFromDocument } from '@/lib/api/quest-files'
import ImageViewerPlugin from '@/lib/plugins/image-viewer/ImageViewerPlugin'
import MarkdownViewerPlugin from '@/lib/plugins/markdown-viewer/MarkdownViewerPlugin'
import NotebookEditor from '@/lib/plugins/notebook/components/NotebookEditor'
import PdfViewerPlugin from '@/lib/plugins/pdf-viewer/PdfViewerPlugin'
import {
  formatGitDiffPathLabel,
  inferSnapshotContentKind,
  inferSnapshotPreviewKind,
} from '@/lib/plugins/git-diff-viewer/viewer-meta'
import { GitDiffViewer } from '@/components/workspace/GitDiffViewer'
import { GitSnapshotViewer } from '@/components/workspace/GitSnapshotViewer'
import { client } from '@/lib/api'
import { useI18n } from '@/lib/i18n/useI18n'
import { useWorkspaceSurfaceStore } from '@/lib/stores/workspace-surface'
import type { PluginComponentProps } from '@/lib/types/tab'
import { cn } from '@/lib/utils'
import { toFilesResourcePath } from '@/lib/utils/resource-paths'
import type { FileChangeDiffPayload, GitDiffPayload, OpenDocumentPayload } from '@/types'

type ViewerMode = 'snapshot' | 'diff'

type DiffViewerContext = {
  projectId?: string
  resolver?: 'git' | 'file_change' | 'git_commit'
  initialMode?: ViewerMode
  snapshotRevision?: string | null
  snapshotDocumentId?: string | null
  allowSnapshot?: boolean
  allowDiff?: boolean
  sha?: string | null
  base?: string
  head?: string
  path?: string
  queryPath?: string
  displayPath?: string
  runId?: string
  eventId?: string
  status?: string | null
  oldPath?: string | null
  added?: number | null
  removed?: number | null
}

const normalizeBoolean = (value: unknown) => {
  if (typeof value === 'boolean') return value
  return null
}

const normalizeNumber = (value: unknown) => {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  return null
}

const normalizeString = (value: unknown) => {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed || null
}

const isFileChangeDiffPayload = (
  value: GitDiffPayload | FileChangeDiffPayload | null
): value is FileChangeDiffPayload => Boolean(value && 'available' in value)

function GitSnapshotContent({
  document,
  projectId,
  parentTabId,
}: {
  document: OpenDocumentPayload | null | undefined
  projectId: string
  parentTabId: string
}) {
  const clearWorkspaceTabState = useWorkspaceSurfaceStore((state) => state.clearTabState)
  const clearWorkspaceTabReferences = useWorkspaceSurfaceStore((state) => state.clearTabReferences)
  const previewKind = React.useMemo(() => inferSnapshotPreviewKind(document), [document])
  const snapshotFileNode = React.useMemo(
    () => (document ? buildQuestFileNodeFromDocument(projectId, document) : null),
    [document, projectId]
  )
  const previewTabId = React.useMemo(
    () => `${parentTabId}::snapshot-preview::${previewKind}`,
    [parentTabId, previewKind]
  )

  const pluginProps = React.useMemo<PluginComponentProps | null>(() => {
    if (!snapshotFileNode) return null
    const resourcePath = snapshotFileNode.path ? toFilesResourcePath(snapshotFileNode.path) : undefined
    const fileMeta = {
      updatedAt: snapshotFileNode.updatedAt,
      sizeBytes: snapshotFileNode.size,
      mimeType: snapshotFileNode.mimeType,
    }
    return {
      context: {
        type: previewKind === 'notebook' ? 'notebook' : 'file',
        resourceId: snapshotFileNode.id,
        resourceName: snapshotFileNode.name,
        resourcePath,
        mimeType: snapshotFileNode.mimeType,
        customData: {
          projectId,
          readonly: true,
          readOnlyMode: true,
          size: snapshotFileNode.size,
          fileMeta,
        },
      },
      tabId: previewTabId,
      setDirty: () => undefined,
      setTitle: () => undefined,
    }
  }, [previewKind, previewTabId, projectId, snapshotFileNode])

  React.useEffect(() => {
    return () => {
      clearWorkspaceTabReferences(previewTabId)
      clearWorkspaceTabState(previewTabId)
    }
  }, [clearWorkspaceTabReferences, clearWorkspaceTabState, previewTabId])

  if (!document || previewKind === 'plain' || !pluginProps) {
    return (
      <GitSnapshotViewer
        document={document}
        className="border border-black/[0.06] bg-white/[0.92] shadow-none dark:border-white/[0.08] dark:bg-[rgba(24,26,31,0.92)]"
      />
    )
  }

  if (previewKind === 'markdown') {
    return (
      <div className="h-full min-h-0 overflow-hidden">
        <MarkdownViewerPlugin {...pluginProps} />
      </div>
    )
  }
  if (previewKind === 'notebook') {
    return (
      <div className="h-full min-h-0 overflow-hidden">
        <NotebookEditor {...pluginProps} className="h-full" />
      </div>
    )
  }
  if (previewKind === 'pdf') {
    return (
      <div className="h-full min-h-0 overflow-hidden">
        <PdfViewerPlugin {...pluginProps} />
      </div>
    )
  }
  if (previewKind === 'image') {
    return (
      <div className="h-full min-h-0 overflow-hidden">
        <ImageViewerPlugin {...pluginProps} />
      </div>
    )
  }

  return (
    <GitSnapshotViewer
      document={document}
      className="border border-black/[0.06] bg-white/[0.92] shadow-none dark:border-white/[0.08] dark:bg-[rgba(24,26,31,0.92)]"
    />
  )
}

export default function GitDiffViewerPlugin({
  context,
  tabId,
  setTitle,
}: PluginComponentProps) {
  const { t } = useI18n('workspace')
  const custom = (context.customData ?? {}) as DiffViewerContext
  const updateWorkspaceTabState = useWorkspaceSurfaceStore((state) => state.updateTabState)
  const projectId = normalizeString(custom.projectId)
  const resolver =
    custom.resolver === 'file_change'
      ? 'file_change'
      : custom.resolver === 'git_commit'
        ? 'git_commit'
        : 'git'
  const initialMode = custom.initialMode === 'snapshot' ? 'snapshot' : 'diff'
  const sha = normalizeString(custom.sha)
  const base = normalizeString(custom.base)
  const head = normalizeString(custom.head)
  const path = normalizeString(custom.path)
  const queryPath = normalizeString(custom.queryPath)
  const displayPath = normalizeString(custom.displayPath)
  const runId = normalizeString(custom.runId)
  const eventId = normalizeString(custom.eventId)
  const status = normalizeString(custom.status)
  const oldPath = normalizeString(custom.oldPath)
  const added = normalizeNumber(custom.added)
  const removed = normalizeNumber(custom.removed)
  const snapshotRevision = normalizeString(custom.snapshotRevision)
  const snapshotDocumentId = normalizeString(custom.snapshotDocumentId)

  const hasValidDiffContext =
    resolver === 'file_change'
      ? Boolean(projectId && runId && queryPath)
      : resolver === 'git_commit'
        ? Boolean(projectId && sha && path)
        : Boolean(projectId && base && head && path)
  const resolvedSnapshotDocumentId =
    snapshotDocumentId || (snapshotRevision && path ? `git::${snapshotRevision}::${path}` : null)
  const hasValidSnapshotContext = Boolean(projectId && resolvedSnapshotDocumentId)

  const explicitAllowSnapshot = normalizeBoolean(custom.allowSnapshot)
  const explicitAllowDiff = normalizeBoolean(custom.allowDiff)
  const allowSnapshot = explicitAllowSnapshot ?? hasValidSnapshotContext
  const allowDiff = explicitAllowDiff ?? hasValidDiffContext

  const [viewMode, setViewMode] = React.useState<ViewerMode>(() => {
    if (initialMode === 'snapshot' && allowSnapshot) return 'snapshot'
    return 'diff'
  })

  React.useEffect(() => {
    if (viewMode === 'snapshot' && !allowSnapshot && allowDiff) {
      setViewMode('diff')
      return
    }
    if (viewMode === 'diff' && !allowDiff && allowSnapshot) {
      setViewMode('snapshot')
    }
  }, [allowDiff, allowSnapshot, viewMode])

  const snapshotQuery = useQuery({
    queryKey: ['git-diff-viewer', 'snapshot', projectId, resolvedSnapshotDocumentId],
    queryFn: () => client.openDocument(projectId!, resolvedSnapshotDocumentId!),
    enabled: Boolean(projectId && resolvedSnapshotDocumentId && allowSnapshot && viewMode === 'snapshot'),
    staleTime: 30_000,
  })

  const diffQuery = useQuery({
    queryKey: ['git-diff-viewer', 'diff', resolver, projectId, sha, base, head, path, queryPath, runId, eventId],
    queryFn: () =>
      resolver === 'file_change'
        ? client.fileChangeDiff(projectId!, runId!, queryPath!, eventId || undefined)
        : resolver === 'git_commit'
          ? client.gitCommitFile(projectId!, sha!, path!)
        : client.gitDiffFile(projectId!, base!, head!, path!),
    enabled: Boolean(hasValidDiffContext && allowDiff && viewMode === 'diff'),
    staleTime: 30_000,
  })

  const mergedDiff = React.useMemo<GitDiffPayload | FileChangeDiffPayload | null>(() => {
    const payload = diffQuery.data ?? null
    if (!payload) return payload
    if (resolver === 'file_change') {
      return {
        ...payload,
        display_path:
          (isFileChangeDiffPayload(payload) ? payload.display_path : null) ||
          displayPath ||
          undefined,
        run_id:
          isFileChangeDiffPayload(payload) ? payload.run_id || runId || undefined : runId || undefined,
        event_id:
          isFileChangeDiffPayload(payload) ? payload.event_id || eventId || undefined : eventId || undefined,
      }
    }
    if (resolver === 'git_commit') {
      if (!path) return payload
      return {
        ...payload,
        path,
        sha: payload?.sha || sha || undefined,
        old_path: payload.old_path || oldPath || undefined,
        status: payload.status || status || undefined,
        added: payload.added ?? added ?? undefined,
        removed: payload.removed ?? removed ?? undefined,
      }
    }
    if (!path || !base || !head) return payload
    return {
      ...payload,
      path,
      base,
      head,
      old_path: payload.old_path || oldPath || undefined,
      status: payload.status || status || undefined,
      added: payload.added ?? added ?? undefined,
      removed: payload.removed ?? removed ?? undefined,
    }
  }, [added, base, diffQuery.data, displayPath, eventId, head, oldPath, path, removed, resolver, runId, sha, status])

  const resolvedBase = mergedDiff?.base || base || ''
  const resolvedHead = mergedDiff?.head || head || ''
  const resolvedSha = normalizeString((mergedDiff as { sha?: string | null } | null)?.sha) || sha || ''
  const resolvedStatus = mergedDiff?.status || status || 'modified'
  const resolvedOldPath = mergedDiff?.old_path || oldPath || null
  const resolvedAdded = mergedDiff?.added ?? added
  const resolvedRemoved = mergedDiff?.removed ?? removed
  const snapshotContentKind = React.useMemo(
    () => inferSnapshotContentKind(snapshotQuery.data),
    [snapshotQuery.data]
  )
  const snapshotPreviewKind = React.useMemo(
    () => inferSnapshotPreviewKind(snapshotQuery.data),
    [snapshotQuery.data]
  )
  const resolvedPathLabel =
    resolver === 'file_change'
      ? (isFileChangeDiffPayload(mergedDiff) ? mergedDiff.display_path : null) ||
        displayPath ||
        mergedDiff?.path ||
        queryPath ||
        t('git_viewer_diff', undefined, 'Diff')
      : formatGitDiffPathLabel(
          path || mergedDiff?.path || displayPath,
          resolvedOldPath,
          t('git_viewer_diff', undefined, 'Diff')
        )

  React.useEffect(() => {
    setTitle(resolvedPathLabel)
  }, [resolvedPathLabel, setTitle])

  React.useEffect(() => {
    updateWorkspaceTabState(tabId, {
      contentKind: viewMode === 'snapshot' ? snapshotContentKind : 'code',
      documentMode: viewMode,
      isReadOnly: true,
      resourceName: resolvedPathLabel,
      resourcePath:
        viewMode === 'snapshot'
          ? snapshotQuery.data?.path || path || undefined
          : mergedDiff?.path || path || queryPath || undefined,
    })
  }, [
    mergedDiff?.path,
    path,
    queryPath,
    resolvedPathLabel,
    snapshotContentKind,
    snapshotQuery.data?.path,
    tabId,
    updateWorkspaceTabState,
    viewMode,
  ])

  const unavailableMessage =
    resolver === 'file_change' && isFileChangeDiffPayload(mergedDiff) && !mergedDiff.available
      ? mergedDiff.message || t('git_viewer_historical_patch_unavailable', undefined, 'Historical patch unavailable.')
      : null

  const currentQuery = viewMode === 'snapshot' ? snapshotQuery : diffQuery
  const useEmbeddedSnapshotShell =
    viewMode === 'snapshot' &&
    Boolean(snapshotQuery.data) &&
    snapshotPreviewKind !== 'plain'

  if (!projectId || (!hasValidSnapshotContext && !hasValidDiffContext)) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-sm text-muted-foreground">
        {t('git_viewer_missing_context', undefined, 'Missing diff context.')}
      </div>
    )
  }

  return (
    <div
      data-testid="git-diff-viewer-plugin"
      className="flex h-full min-h-0 flex-col bg-[rgba(250,248,244,0.86)] dark:bg-[rgba(18,20,24,0.92)]"
    >
      <div className="border-b border-black/[0.06] px-6 py-5 dark:border-white/[0.08]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                {viewMode === 'snapshot' ? (
                  <FileText className="h-3.5 w-3.5" />
                ) : (
                  <GitCompare className="h-3.5 w-3.5" />
                )}
                {viewMode === 'snapshot'
                  ? t('git_viewer_snapshot', undefined, 'Snapshot')
                  : resolver === 'file_change'
                    ? t('git_viewer_historical_diff', undefined, 'Historical Diff')
                    : t('git_viewer_diff', undefined, 'Diff')}
              </span>
              {viewMode === 'diff' ? (
                <>
                  <span>·</span>
                  <span>{resolvedStatus}</span>
                </>
              ) : null}
            </div>
            <div className="mt-2 break-words text-[24px] font-semibold tracking-[-0.03em] text-foreground">
              {resolvedPathLabel}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              {viewMode === 'snapshot' ? (
                <>
                  {snapshotRevision ? <span>{snapshotRevision}</span> : null}
                  {allowDiff && resolver === 'git_commit' && resolvedSha ? <span>{resolvedSha}</span> : null}
                  {allowDiff && resolver !== 'git_commit' && resolvedBase ? <span>{resolvedBase}</span> : null}
                  {allowDiff && resolver !== 'git_commit' && resolvedBase && resolvedHead ? <span>→</span> : null}
                  {allowDiff && resolver !== 'git_commit' && resolvedHead ? <span>{resolvedHead}</span> : null}
                </>
              ) : (
                <>
                  {resolver === 'git_commit' ? (
                    resolvedSha ? <span>{resolvedSha}</span> : null
                  ) : (
                    <>
                      {resolvedBase ? <span>{resolvedBase}</span> : null}
                      {resolvedBase && resolvedHead ? <span>→</span> : null}
                      {resolvedHead ? <span>{resolvedHead}</span> : null}
                    </>
                  )}
                </>
              )}
              {resolvedAdded != null ? (
                <span className="text-emerald-700 dark:text-emerald-300">+{resolvedAdded}</span>
              ) : null}
              {resolvedRemoved != null ? (
                <span className="text-rose-700 dark:text-rose-300">-{resolvedRemoved}</span>
              ) : null}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {allowSnapshot || allowDiff ? (
              <div className="flex items-center rounded-full border border-black/[0.08] bg-white/[0.86] p-1 dark:border-white/[0.1] dark:bg-white/[0.03]">
                {allowSnapshot ? (
                  <button
                    type="button"
                    onClick={() => setViewMode('snapshot')}
                    data-testid="git-diff-viewer-snapshot-toggle"
                    className={cn(
                      'rounded-full px-3 py-1.5 text-[12px] font-medium transition-colors',
                      viewMode === 'snapshot'
                        ? 'bg-black/[0.06] text-foreground dark:bg-white/[0.12]'
                        : 'text-muted-foreground hover:text-foreground'
                    )}
                  >
                    {t('git_viewer_snapshot', undefined, 'Snapshot')}
                  </button>
                ) : null}
                {allowDiff ? (
                  <button
                    type="button"
                    onClick={() => setViewMode('diff')}
                    data-testid="git-diff-viewer-diff-toggle"
                    className={cn(
                      'rounded-full px-3 py-1.5 text-[12px] font-medium transition-colors',
                      viewMode === 'diff'
                        ? 'bg-black/[0.06] text-foreground dark:bg-white/[0.12]'
                        : 'text-muted-foreground hover:text-foreground'
                    )}
                  >
                    {t('git_viewer_diff', undefined, 'Diff')}
                  </button>
                ) : null}
              </div>
            ) : null}
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                void currentQuery.refetch()
              }}
              className="h-9 rounded-full border-black/[0.08] bg-white/[0.86] px-3 text-[12px] shadow-none hover:bg-black/[0.03] dark:border-white/[0.1] dark:bg-white/[0.03] dark:hover:bg-white/[0.06]"
            >
              <RefreshCw className={cn('mr-1.5 h-3.5 w-3.5', currentQuery.isFetching && 'animate-spin')} />
              {t('explorer_refresh')}
            </Button>
          </div>
        </div>
      </div>

      <div
        className={cn(
          'min-h-0 flex-1 px-6 py-6',
          useEmbeddedSnapshotShell ? 'overflow-hidden' : 'overflow-y-auto'
        )}
      >
        {viewMode === 'snapshot' ? (
          !allowSnapshot || !hasValidSnapshotContext ? (
            <div className="rounded-[20px] border border-black/[0.08] bg-white/[0.82] px-4 py-4 text-sm leading-7 text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.04]">
              {t('git_viewer_snapshot_unavailable', undefined, 'Snapshot preview is unavailable for this file.')}
            </div>
          ) : snapshotQuery.isLoading ? (
            <div className="text-sm leading-7 text-muted-foreground">
              {t('git_viewer_loading_snapshot', undefined, 'Loading snapshot…')}
            </div>
          ) : snapshotQuery.isError ? (
            <div className="rounded-[20px] border border-rose-200/80 bg-rose-50/70 px-4 py-4 text-sm text-rose-700 dark:border-rose-400/20 dark:bg-rose-500/10 dark:text-rose-200">
              {t('git_viewer_failed_snapshot', undefined, 'Failed to load snapshot.')}
            </div>
          ) : (
            <GitSnapshotContent
              document={snapshotQuery.data}
              projectId={projectId}
              parentTabId={tabId}
            />
          )
        ) : !allowDiff || !hasValidDiffContext ? (
          <div className="rounded-[20px] border border-black/[0.08] bg-white/[0.82] px-4 py-4 text-sm leading-7 text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.04]">
            {t('git_viewer_diff_unavailable', undefined, 'Diff preview is unavailable for this file.')}
          </div>
        ) : diffQuery.isLoading ? (
          <div className="text-sm leading-7 text-muted-foreground">
            {t('git_viewer_loading_diff', undefined, 'Loading patch…')}
          </div>
        ) : diffQuery.isError ? (
          <div className="rounded-[20px] border border-rose-200/80 bg-rose-50/70 px-4 py-4 text-sm text-rose-700 dark:border-rose-400/20 dark:bg-rose-500/10 dark:text-rose-200">
            {t('git_viewer_failed_diff', undefined, 'Failed to load diff.')}
          </div>
        ) : unavailableMessage ? (
          <div className="rounded-[20px] border border-black/[0.08] bg-white/[0.82] px-4 py-4 text-sm leading-7 text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.04]">
            {unavailableMessage}
          </div>
        ) : (
          <GitDiffViewer
            diff={mergedDiff}
            pathLabel={resolvedPathLabel}
            className="border border-black/[0.06] bg-white/[0.92] shadow-none dark:border-white/[0.08] dark:bg-[rgba(24,26,31,0.92)]"
          />
        )}
      </div>
    </div>
  )
}
