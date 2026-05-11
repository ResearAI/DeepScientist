'use client'

import * as React from 'react'
import { FlaskConical, ShieldCheck, Network, SearchCheck, PackageCheck, Sigma } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatScienceValue, scienceNodeTypeLabel } from '@/lib/science/normalize'
import type { ScienceNodeData } from '@/lib/science/types'

const iconForType = (nodeType: string) => {
  if (nodeType === 'science.package_check') return PackageCheck
  if (nodeType === 'science.validation_result') return ShieldCheck
  if (nodeType === 'science.claim') return SearchCheck
  if (nodeType === 'science.parameter_sweep') return Network
  if (nodeType === 'science.dataset_analysis') return Sigma
  return FlaskConical
}

export function ScienceNodeCard({
  node,
  compact = false,
  className,
}: {
  node: ScienceNodeData
  compact?: boolean
  className?: string
}) {
  const Icon = iconForType(node.nodeType)
  const firstResult = node.keyResults[0]
  const evidenceParts = [
    node.inputPaths.length ? 'input' : null,
    node.logPaths.length ? 'log' : null,
    node.outputPaths.length ? 'output' : null,
    node.validationPaths.length ? 'validation' : null,
    node.evidencePaths.length ? 'evidence' : null,
  ].filter(Boolean)
  const meta = [
    node.claimType,
    node.trust ? `trust: ${node.trust}` : null,
    node.packageId,
    node.taskType,
  ].filter(Boolean)

  return (
    <div
      className={cn(
        'science-node-card rounded-[8px] border border-[var(--lab-border)] bg-[var(--lab-surface)] px-3 py-3 text-[var(--lab-text-primary)] shadow-sm',
        compact && 'px-2.5 py-2.5',
        className
      )}
      data-testid="science-node-card"
    >
      <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--lab-text-secondary)]">
        <Icon className="h-3.5 w-3.5" aria-hidden />
        <span>{scienceNodeTypeLabel(node.nodeType)}</span>
        <span className="ml-auto rounded-full border border-[var(--lab-border)] px-2 py-0.5 normal-case tracking-[0]">
          {node.status}
        </span>
      </div>
      <div className="mt-2 line-clamp-2 text-sm font-semibold leading-5">{node.title}</div>
      {meta.length ? (
        <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] text-[var(--lab-text-muted)]">
          {meta.slice(0, 3).map((item) => (
            <span key={String(item)}>{item}</span>
          ))}
        </div>
      ) : null}
      {firstResult ? (
        <div className="mt-2 rounded-[6px] bg-[var(--lab-background)] px-2 py-1.5 text-[11px] leading-4">
          <span className="font-medium">{firstResult.label}</span>
          {formatScienceValue(firstResult) ? <span> = {formatScienceValue(firstResult)}</span> : null}
        </div>
      ) : node.summary && !compact ? (
        <div className="mt-2 line-clamp-2 text-[11px] leading-4 text-[var(--lab-text-secondary)]">{node.summary}</div>
      ) : null}
      {evidenceParts.length ? (
        <div className="mt-2 text-[10px] text-[var(--lab-text-secondary)]">
          Evidence: {evidenceParts.slice(0, 4).join(' · ')}
        </div>
      ) : null}
    </div>
  )
}

export default ScienceNodeCard
