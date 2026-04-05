'use client'

import * as React from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, GitCommit, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { GitDiffViewer } from '@/components/workspace/GitDiffViewer'
import { GitSnapshotViewer } from '@/components/workspace/GitSnapshotViewer'
import { client } from '@/lib/api'
import { formatGitDiffPathLabel } from '@/lib/plugins/git-diff-viewer/viewer-meta'
import { useI18n } from '@/lib/i18n/useI18n'
import { useWorkspaceSurfaceStore } from '@/lib/stores/workspace-surface'
import type { PluginComponentProps } from '@/lib/types/tab'
import { cn } from '@/lib/utils'

type ViewerMode = 'snapshot' | 'diff'

type CommitViewerContext = {
  projectId?: string
  sha?: string
  initialPath?: string | null
  initialMode?: ViewerMode
}

const normalizeString = (value: unknown) => {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed || null
}

export default function GitCommitViewerPlugin({
  context,
  tabId,
  setTitle,
}: PluginComponentProps) {
  const { t } = useI18n('workspace')
  const custom = (context.customData ?? {}) as CommitViewerContext
  const updateWorkspaceTabState = useWorkspaceSurfaceStore((state) => state.updateTabState)
  const projectId = normalizeString(custom.projectId)
  const sha = normalizeString(custom.sha)
  const [selectedPath, setSelectedPath] = React.useState<string | null>(normalizeString(custom.initialPath))
  const [viewMode, setViewMode] = React.useState<ViewerMode>(
    custom.initialMode === 'snapshot' ? 'snapshot' : 'diff'
  )

  const commitQuery = useQuery({
    queryKey: ['git-commit-viewer', 'commit', projectId, sha],
    queryFn: () => client.gitCommit(projectId!, sha!),
    enabled: Boolean(projectId && sha),
    staleTime: 30_000,
  })

  React.useEffect(() => {
    const files = commitQuery.data?.files || []
    if (!files.length) {
      if (selectedPath) {
        setSelectedPath(null)
      }
      return
    }
    if (selectedPath && files.some((item) => item.path === selectedPath)) {
      return
    }
    setSelectedPath(files[0].path)
  }, [commitQuery.data?.files, selectedPath])

  const diffQuery = useQuery({
    queryKey: ['git-commit-viewer', 'diff', projectId, sha, selectedPath],
    queryFn: () => client.gitCommitFile(projectId!, sha!, selectedPath!),
    enabled: Boolean(projectId && sha && selectedPath && viewMode === 'diff'),
    staleTime: 30_000,
  })

  const snapshotQuery = useQuery({
    queryKey: ['git-commit-viewer', 'snapshot', projectId, sha, selectedPath],
    queryFn: () => client.openDocument(projectId!, `git::${sha}::${selectedPath}`),
    enabled: Boolean(projectId && sha && selectedPath && viewMode === 'snapshot'),
    staleTime: 30_000,
  })

  const selectedFile = React.useMemo(
    () => commitQuery.data?.files?.find((item) => item.path === selectedPath) || null,
    [commitQuery.data?.files, selectedPath]
  )
  const pathLabel = React.useMemo(
    () =>
      formatGitDiffPathLabel(
        selectedPath || snapshotQuery.data?.path || undefined,
        selectedFile?.old_path || null,
        t('git_viewer_diff', undefined, 'Diff')
      ),
    [selectedFile?.old_path, selectedPath, snapshotQuery.data?.path, t]
  )

  React.useEffect(() => {
    const commitTitle =
      commitQuery.data?.subject || commitQuery.data?.short_sha || sha || t('git_viewer_diff', undefined, 'Commit')
    setTitle(commitTitle)
  }, [commitQuery.data?.short_sha, commitQuery.data?.subject, setTitle, sha, t])

  React.useEffect(() => {
    updateWorkspaceTabState(tabId, {
      contentKind: viewMode === 'snapshot' ? 'text' : 'code',
      documentMode: viewMode,
      isReadOnly: true,
      resourceName: pathLabel,
      resourcePath: selectedPath || undefined,
    })
  }, [pathLabel, selectedPath, tabId, updateWorkspaceTabState, viewMode])

  if (!projectId || !sha) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-sm text-muted-foreground">
        {t('git_viewer_missing_context', undefined, 'Missing diff context.')}
      </div>
    )
  }

  return (
    <div
      data-testid="git-commit-viewer-plugin"
      className="flex h-full min-h-0 flex-col bg-[rgba(250,248,244,0.86)] dark:bg-[rgba(18,20,24,0.92)]"
    >
      <div className="border-b border-black/[0.06] px-6 py-5 dark:border-white/[0.08]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <GitCommit className="h-3.5 w-3.5" />
                Commit
              </span>
              {commitQuery.data?.short_sha ? (
                <>
                  <span>·</span>
                  <span>{commitQuery.data.short_sha}</span>
                </>
              ) : null}
            </div>
            <div className="mt-2 break-words text-[24px] font-semibold tracking-[-0.03em] text-foreground">
              {commitQuery.data?.subject || sha}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              {commitQuery.data?.author_name ? <span>{commitQuery.data.author_name}</span> : null}
              {commitQuery.data?.authored_at ? <span>{commitQuery.data.authored_at}</span> : null}
              {typeof commitQuery.data?.file_count === 'number' ? <span>{commitQuery.data.file_count} files</span> : null}
              {typeof commitQuery.data?.stats?.added === 'number' ? (
                <span className="text-emerald-700 dark:text-emerald-300">+{commitQuery.data.stats.added}</span>
              ) : null}
              {typeof commitQuery.data?.stats?.removed === 'number' ? (
                <span className="text-rose-700 dark:text-rose-300">-{commitQuery.data.stats.removed}</span>
              ) : null}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center rounded-full border border-black/[0.08] bg-white/[0.86] p-1 dark:border-white/[0.1] dark:bg-white/[0.03]">
              <button
                type="button"
                onClick={() => setViewMode('snapshot')}
                className={cn(
                  'rounded-full px-3 py-1.5 text-[12px] font-medium transition-colors',
                  viewMode === 'snapshot'
                    ? 'bg-black/[0.06] text-foreground dark:bg-white/[0.12]'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                Snapshot
              </button>
              <button
                type="button"
                onClick={() => setViewMode('diff')}
                className={cn(
                  'rounded-full px-3 py-1.5 text-[12px] font-medium transition-colors',
                  viewMode === 'diff'
                    ? 'bg-black/[0.06] text-foreground dark:bg-white/[0.12]'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                Diff
              </button>
            </div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                void commitQuery.refetch()
                void diffQuery.refetch()
                void snapshotQuery.refetch()
              }}
              className="h-9 rounded-full border-black/[0.08] bg-white/[0.86] px-3 text-[12px] shadow-none hover:bg-black/[0.03] dark:border-white/[0.1] dark:bg-white/[0.03] dark:hover:bg-white/[0.06]"
            >
              <RefreshCw
                className={cn(
                  'mr-1.5 h-3.5 w-3.5',
                  (commitQuery.isFetching || diffQuery.isFetching || snapshotQuery.isFetching) && 'animate-spin'
                )}
              />
              {t('explorer_refresh')}
            </Button>
          </div>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[280px_minmax(0,1fr)]">
        <div className="border-r border-black/[0.06] bg-white/[0.46] p-4 dark:border-white/[0.08] dark:bg-white/[0.02]">
          <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Changed Files
          </div>
          <div className="space-y-2">
            {(commitQuery.data?.files || []).map((file) => (
              <button
                key={file.path}
                type="button"
                onClick={() => setSelectedPath(file.path)}
                className={cn(
                  'w-full rounded-[18px] border px-3 py-3 text-left transition',
                  selectedPath === file.path
                    ? 'border-black/[0.12] bg-white shadow-sm dark:border-white/[0.12] dark:bg-white/[0.04]'
                    : 'border-black/[0.06] bg-white/[0.72] hover:border-black/[0.1] dark:border-white/[0.08] dark:bg-white/[0.02]'
                )}
              >
                <div className="truncate text-sm font-medium text-foreground">{file.path}</div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                  <span>{file.status || 'modified'}</span>
                  {typeof file.added === 'number' ? <span className="text-emerald-700 dark:text-emerald-300">+{file.added}</span> : null}
                  {typeof file.removed === 'number' ? <span className="text-rose-700 dark:text-rose-300">-{file.removed}</span> : null}
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="min-h-0 overflow-hidden px-6 py-6">
          {!selectedPath ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              Select one changed file to inspect this commit.
            </div>
          ) : viewMode === 'snapshot' ? (
            snapshotQuery.isLoading ? (
              <div className="text-sm leading-7 text-muted-foreground">Loading snapshot…</div>
            ) : snapshotQuery.isError ? (
              <div className="rounded-[20px] border border-rose-200/80 bg-rose-50/70 px-4 py-4 text-sm text-rose-700 dark:border-rose-400/20 dark:bg-rose-500/10 dark:text-rose-200">
                Failed to load snapshot.
              </div>
            ) : (
              <GitSnapshotViewer
                document={snapshotQuery.data}
                className="border border-black/[0.06] bg-white/[0.92] shadow-none dark:border-white/[0.08] dark:bg-[rgba(24,26,31,0.92)]"
              />
            )
          ) : diffQuery.isLoading ? (
            <div className="text-sm leading-7 text-muted-foreground">Loading patch…</div>
          ) : diffQuery.isError ? (
            <div className="rounded-[20px] border border-rose-200/80 bg-rose-50/70 px-4 py-4 text-sm text-rose-700 dark:border-rose-400/20 dark:bg-rose-500/10 dark:text-rose-200">
              Failed to load diff.
            </div>
          ) : (
            <GitDiffViewer
              diff={diffQuery.data}
              pathLabel={pathLabel}
              className="border border-black/[0.06] bg-white/[0.92] shadow-none dark:border-white/[0.08] dark:bg-[rgba(24,26,31,0.92)]"
            />
          )}

          {commitQuery.data?.body ? (
            <div className="mt-5 rounded-[20px] border border-black/[0.06] bg-white/[0.68] px-4 py-4 text-sm leading-7 text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.03]">
              <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                <FileText className="h-3.5 w-3.5" />
                Body
              </div>
              <div className="whitespace-pre-wrap">{commitQuery.data.body}</div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
