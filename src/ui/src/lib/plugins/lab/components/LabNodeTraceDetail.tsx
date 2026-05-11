'use client'

import * as React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useOpenFile } from '@/hooks/useOpenFile'
import { client } from '@/lib/api'
import type { LabQuestNodeTrace } from '@/lib/api/lab'
import { openWorkspaceFileReference } from '@/components/workspace/open-workspace-file-reference'
import ScienceNodeDetailPanel from '@/components/science/ScienceNodeDetailPanel'
import { normalizeScienceTrace } from '@/lib/science/normalize'
import { useFileTreeStore } from '@/lib/stores/file-tree'

const formatStateLabel = (value?: string | null) => {
  const normalized = String(value || '')
    .trim()
    .replace(/[_-]+/g, ' ')
  if (!normalized) return 'N/A'
  return normalized.replace(/\b\w/g, (char) => char.toUpperCase())
}

const prettyJson = (value: unknown) => {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

const asRecord = (value: unknown) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

const asString = (value: unknown) => {
  if (typeof value === 'string') return value.trim() || null
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
}

function MetaCard({
  label,
  value,
}: {
  label: string
  value: React.ReactNode
}) {
  return (
    <div className="rounded-[14px] border border-[var(--lab-border)] bg-[var(--lab-background)] px-3 py-2.5">
      <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--lab-text-secondary)]">
        {label}
      </div>
      <div className="mt-1 text-sm text-[var(--lab-text-primary)]">{value}</div>
    </div>
  )
}

export default function LabNodeTraceDetail({
  projectId,
  questId,
  trace,
  isLoading,
  payloadJson,
  payloadTruncated,
}: {
  projectId?: string | null
  questId?: string | null
  trace?: LabQuestNodeTrace | null
  isLoading?: boolean
  payloadJson?: Record<string, unknown> | null
  payloadTruncated?: boolean | null
}) {
  const primaryPayload = trace?.payload_json || asRecord(payloadJson)?.payload || payloadJson || null
  const primaryAction =
    [...(trace?.actions || [])].reverse().find((action) => action.artifact_id || action.head_commit) || null
  const headCommit = trace?.head_commit || primaryAction?.head_commit || null
  const artifactKind = trace?.artifact_kind || primaryAction?.artifact_kind || null
  const artifactId = trace?.artifact_id || primaryAction?.artifact_id || null
  const scienceNode = trace ? normalizeScienceTrace(trace) : null
  const { openFileInTab } = useOpenFile()
  const findNode = useFileTreeStore((state) => state.findNode)
  const findNodeByPath = useFileTreeStore((state) => state.findNodeByPath)
  const refreshTree = useFileTreeStore((state) => state.refresh)

  const commitQuery = useQuery({
    queryKey: ['lab-trace-commit', questId, headCommit],
    queryFn: () => client.gitCommit(questId as string, headCommit as string),
    enabled: Boolean(questId && headCommit),
    staleTime: 15000,
  })

  const fileCandidates = React.useMemo(() => {
    const explicit = [...(trace?.changed_files || [])].filter(Boolean)
    const commitFiles = commitQuery.data?.files?.map((file) => file.path).filter(Boolean) || []
    const payloadPaths = Object.values(trace?.paths_map || {})
      .map((entry) => asString(entry))
      .filter((entry): entry is string => Boolean(entry && !entry.startsWith('/')))
    return [...new Set([...explicit, ...commitFiles, ...payloadPaths])]
  }, [commitQuery.data?.files, trace?.changed_files, trace?.paths_map])

  const [selectedPath, setSelectedPath] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!fileCandidates.length) {
      setSelectedPath(null)
      return
    }
    if (!selectedPath || !fileCandidates.includes(selectedPath)) {
      setSelectedPath(fileCandidates[0] || null)
    }
  }, [fileCandidates, selectedPath])

  const commitFileQuery = useQuery({
    queryKey: ['lab-trace-commit-file', questId, headCommit, selectedPath],
    queryFn: () => client.gitCommitFile(questId as string, headCommit as string, selectedPath as string),
    enabled: Boolean(questId && headCommit && selectedPath),
    staleTime: 15000,
  })

  const openScienceEvidencePath = React.useCallback(
    async (path: string) => {
      const resolvedProjectId = projectId || questId || null
      if (!resolvedProjectId) return
      await openWorkspaceFileReference({
        href: path,
        projectId: resolvedProjectId,
        currentOrigin: typeof window !== 'undefined' ? window.location.origin : null,
        findNode,
        findNodeByPath,
        refreshTree,
        openFileInTab,
      })
    },
    [findNode, findNodeByPath, openFileInTab, projectId, questId, refreshTree]
  )

  if (isLoading && !trace) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-24 w-full rounded-[18px]" />
        <Skeleton className="h-20 w-full rounded-[18px]" />
        <Skeleton className="h-32 w-full rounded-[18px]" />
      </div>
    )
  }

  if (!trace) {
    return (
      <div className="rounded-[18px] border border-[var(--lab-border)] bg-[var(--lab-surface)] px-4 py-4 text-sm text-[var(--lab-text-secondary)]">
        No trace is attached to this node yet.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="rounded-[18px] border border-[var(--lab-border)] bg-[var(--lab-surface)] px-4 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{formatStateLabel(trace.selection_type)}</Badge>
          {trace.stage_title ? <Badge variant="outline">{trace.stage_title}</Badge> : null}
          {trace.status ? <Badge variant="outline">{formatStateLabel(trace.status)}</Badge> : null}
          {artifactKind ? <Badge variant="outline">{formatStateLabel(artifactKind)}</Badge> : null}
        </div>
        <div className="mt-3 text-sm font-semibold text-[var(--lab-text-primary)]">{trace.title}</div>
        <div className="mt-1 text-xs leading-5 text-[var(--lab-text-secondary)]">
          {trace.summary || 'No normalized summary is available for this node.'}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <MetaCard label="Branch" value={trace.branch_name || 'N/A'} />
        <MetaCard label="Stage" value={trace.stage_title || 'N/A'} />
        <MetaCard label="Artifact" value={artifactId || 'N/A'} />
        <MetaCard label="Commit" value={headCommit || 'N/A'} />
        <MetaCard label="Actions" value={trace.counts?.actions ?? trace.actions.length} />
        <MetaCard label="Updated" value={trace.updated_at || 'N/A'} />
      </div>

      {scienceNode ? (
        <ScienceNodeDetailPanel
          node={scienceNode}
          onOpenPath={(path) => {
            void openScienceEvidencePath(path)
          }}
        />
      ) : null}

      {primaryPayload && !scienceNode ? (
        <div className="rounded-[18px] border border-[var(--lab-border)] bg-[var(--lab-surface)] px-4 py-4">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--lab-text-secondary)]">
              Artifact Payload
            </div>
            {payloadTruncated ? <Badge variant="outline">Truncated</Badge> : null}
          </div>
          <pre className="mt-3 max-h-[280px] overflow-auto whitespace-pre-wrap rounded-[14px] bg-[var(--lab-background)] p-3 text-[11px] leading-5 text-[var(--lab-text-primary)]">
            {prettyJson(primaryPayload)}
          </pre>
        </div>
      ) : null}

      {headCommit ? (
        <div className="rounded-[18px] border border-[var(--lab-border)] bg-[var(--lab-surface)] px-4 py-4">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--lab-text-secondary)]">
            Commit
          </div>
          {commitQuery.isLoading ? (
            <Skeleton className="mt-3 h-20 w-full rounded-[14px]" />
          ) : commitQuery.data ? (
            <div className="mt-3 space-y-2 text-xs text-[var(--lab-text-secondary)]">
              <div className="text-sm font-semibold text-[var(--lab-text-primary)]">{commitQuery.data.subject}</div>
              <div>{commitQuery.data.short_sha} · {commitQuery.data.author_name || 'Unknown author'}</div>
              <div>{commitQuery.data.authored_at || 'Unknown time'}</div>
              <div>
                {commitQuery.data.file_count || 0} files · +{commitQuery.data.stats?.added || 0} / -
                {commitQuery.data.stats?.removed || 0}
              </div>
            </div>
          ) : (
            <div className="mt-3 text-sm text-[var(--lab-text-secondary)]">Commit metadata is unavailable.</div>
          )}
        </div>
      ) : null}

      {fileCandidates.length ? (
        <div className="rounded-[18px] border border-[var(--lab-border)] bg-[var(--lab-surface)] px-4 py-4">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--lab-text-secondary)]">
            Changed Files
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {fileCandidates.slice(0, 12).map((path) => (
              <button
                key={path}
                type="button"
                className={`rounded-full border px-2.5 py-1 text-[11px] ${
                  selectedPath === path
                    ? 'border-[var(--lab-accent-strong)] bg-[rgba(64,113,175,0.1)] text-[var(--lab-text-primary)]'
                    : 'border-[var(--lab-border)] bg-[var(--lab-background)] text-[var(--lab-text-secondary)]'
                }`}
                onClick={() => setSelectedPath(path)}
              >
                {path}
              </button>
            ))}
          </div>
          {selectedPath ? (
            <div className="mt-3">
              <div className="text-xs font-semibold text-[var(--lab-text-primary)]">{selectedPath}</div>
              {commitFileQuery.isLoading ? (
                <Skeleton className="mt-2 h-36 w-full rounded-[14px]" />
              ) : commitFileQuery.data?.lines?.length ? (
                <pre className="mt-2 max-h-[320px] overflow-auto whitespace-pre-wrap rounded-[14px] bg-[var(--lab-background)] p-3 text-[11px] leading-5 text-[var(--lab-text-primary)]">
                  {commitFileQuery.data.lines.join('\n')}
                </pre>
              ) : (
                <div className="mt-2 text-sm text-[var(--lab-text-secondary)]">
                  {projectId && questId ? 'Preview unavailable for this file.' : 'Preview unavailable.'}
                </div>
              )}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="rounded-[18px] border border-[var(--lab-border)] bg-[var(--lab-surface)] px-4 py-4">
        <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--lab-text-secondary)]">
          Trace Actions
        </div>
        <div className="mt-3 space-y-3">
          {trace.actions.length ? (
            trace.actions.map((action) => (
              <div
                key={action.action_id}
                className="rounded-[14px] border border-[var(--lab-border)] bg-[var(--lab-background)] px-3 py-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <div className="text-sm font-semibold text-[var(--lab-text-primary)]">
                    {action.title || action.tool_name || action.raw_event_type || action.kind || action.action_id}
                  </div>
                  {action.kind ? <Badge variant="outline">{formatStateLabel(action.kind)}</Badge> : null}
                  {action.status ? <Badge variant="outline">{formatStateLabel(action.status)}</Badge> : null}
                  {action.artifact_kind ? <Badge variant="outline">{formatStateLabel(action.artifact_kind)}</Badge> : null}
                </div>
                <div className="mt-1 text-[11px] text-[var(--lab-text-secondary)]">
                  {action.created_at || 'N/A'}
                </div>
                {action.summary ? (
                  <div className="mt-2 text-xs leading-5 text-[var(--lab-text-secondary)]">{action.summary}</div>
                ) : null}
                {action.head_commit ? (
                  <div className="mt-2 text-xs text-[var(--lab-text-secondary)]">
                    Commit: <span className="font-semibold text-[var(--lab-text-primary)]">{action.head_commit}</span>
                  </div>
                ) : null}
                {action.tool_name ? (
                  <div className="mt-2 text-xs text-[var(--lab-text-secondary)]">
                    Tool: <span className="font-semibold text-[var(--lab-text-primary)]">{action.tool_name}</span>
                  </div>
                ) : null}
                {action.mcp_server || action.mcp_tool ? (
                  <div className="mt-2 text-xs text-[var(--lab-text-secondary)]">
                    MCP:{' '}
                    <span className="font-semibold text-[var(--lab-text-primary)]">
                      {action.mcp_server || 'unknown'}
                      {action.mcp_tool ? `.${action.mcp_tool}` : ''}
                    </span>
                  </div>
                ) : null}
                {action.args ? (
                  <pre className="mt-2 max-h-36 overflow-auto whitespace-pre-wrap rounded-[12px] bg-[rgba(15,23,42,0.04)] p-2 text-[11px] leading-5 text-[var(--lab-text-primary)]">
                    {action.args}
                  </pre>
                ) : null}
                {action.output ? (
                  <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded-[12px] bg-[rgba(15,23,42,0.04)] p-2 text-[11px] leading-5 text-[var(--lab-text-primary)]">
                    {action.output}
                  </pre>
                ) : null}
              </div>
            ))
          ) : (
            <div className="text-sm text-[var(--lab-text-secondary)]">No action records yet.</div>
          )}
        </div>
      </div>
    </div>
  )
}
