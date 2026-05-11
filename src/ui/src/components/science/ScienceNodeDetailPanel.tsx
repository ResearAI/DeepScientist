'use client'

import * as React from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatScienceValue, scienceNodeTypeLabel } from '@/lib/science/normalize'
import type { ScienceNodeData } from '@/lib/science/types'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-[8px] border border-[var(--lab-border)] bg-[var(--lab-surface)] px-4 py-3">
      <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--lab-text-secondary)]">
        {title}
      </div>
      <div className="mt-2">{children}</div>
    </div>
  )
}

function PathList({
  label,
  paths,
  onOpenPath,
}: {
  label: string
  paths: string[]
  onOpenPath?: (path: string) => void
}) {
  if (!paths.length) return null
  return (
    <div>
      <div className="text-[11px] font-semibold text-[var(--lab-text-secondary)]">{label}</div>
      <div className="mt-1 space-y-1">
        {paths.map((path) => (
          <div key={`${label}:${path}`} className="flex items-center gap-2 rounded-[6px] bg-[var(--lab-background)] px-2 py-1.5">
            <span className="min-w-0 flex-1 truncate text-[11px] text-[var(--lab-text-primary)]" title={path}>
              {path}
            </span>
            {onOpenPath ? (
              <Button type="button" variant="outline" size="sm" className="h-6 px-2 text-[10px]" onClick={() => onOpenPath(path)}>
                Open
              </Button>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  )
}

export function ScienceNodeDetailPanel({
  node,
  onOpenPath,
}: {
  node: ScienceNodeData
  onOpenPath?: (path: string) => void
}) {
  const allRelated = [...node.parentNodeIds, ...node.relatedNodeIds]
  const hasEvidence =
    node.inputPaths.length ||
    node.logPaths.length ||
    node.outputPaths.length ||
    node.validationPaths.length ||
    node.evidencePaths.length

  return (
    <div className="space-y-3" data-testid="science-node-detail">
      <Section title={scienceNodeTypeLabel(node.nodeType)}>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{node.status}</Badge>
          {node.claimType ? <Badge variant="outline">{node.claimType}</Badge> : null}
          {node.trust ? <Badge variant="outline">trust: {node.trust}</Badge> : null}
        </div>
        <div className="mt-3 text-sm font-semibold text-[var(--lab-text-primary)]">{node.title}</div>
        {node.summary ? <div className="mt-1 text-xs leading-5 text-[var(--lab-text-secondary)]">{node.summary}</div> : null}
      </Section>

      <div className="grid gap-3 sm:grid-cols-2">
        <Section title="Package">
          <div className="text-sm text-[var(--lab-text-primary)]">{node.packageId || 'N/A'}</div>
          {node.domain || node.taskType ? (
            <div className="mt-1 text-xs text-[var(--lab-text-secondary)]">
              {[node.domain, node.taskType].filter(Boolean).join(' · ')}
            </div>
          ) : null}
        </Section>
        <Section title="Node Id">
          <div className="break-all text-sm text-[var(--lab-text-primary)]">{node.nodeId}</div>
        </Section>
      </div>

      {node.keyResults.length ? (
        <Section title="Key Results">
          <div className="space-y-1.5">
            {node.keyResults.map((result, index) => (
              <div key={`${result.label}:${index}`} className="rounded-[6px] bg-[var(--lab-background)] px-2 py-1.5 text-xs">
                <span className="font-medium text-[var(--lab-text-primary)]">{result.label}</span>
                {formatScienceValue(result) ? <span className="text-[var(--lab-text-secondary)]"> = {formatScienceValue(result)}</span> : null}
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      {hasEvidence ? (
        <Section title="Evidence">
          <div className="space-y-3">
            <PathList label="Input" paths={node.inputPaths} onOpenPath={onOpenPath} />
            <PathList label="Log" paths={node.logPaths} onOpenPath={onOpenPath} />
            <PathList label="Output" paths={node.outputPaths} onOpenPath={onOpenPath} />
            <PathList label="Validation" paths={node.validationPaths} onOpenPath={onOpenPath} />
            <PathList label="Evidence" paths={node.evidencePaths} onOpenPath={onOpenPath} />
          </div>
        </Section>
      ) : null}

      {allRelated.length ? (
        <Section title="Related Nodes">
          <div className="flex flex-wrap gap-1.5">
            {allRelated.map((id) => (
              <Badge key={id} variant="outline" className="max-w-full truncate">
                {id}
              </Badge>
            ))}
          </div>
        </Section>
      ) : null}

      {node.nodeType === 'science.claim' && node.claimType !== 'computed' ? (
        <Section title="Warnings">
          <div className="text-xs leading-5 text-[var(--lab-text-secondary)]">
            This claim is classified as {node.claimType || 'unknown'}, not computed evidence.
          </div>
        </Section>
      ) : null}
    </div>
  )
}

export default ScienceNodeDetailPanel
