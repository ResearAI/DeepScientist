import type { QuestArtifactRecord, QuestNodeTrace } from '@/types'
import type { ScienceKeyResult, ScienceNodeData } from './types'

type ArtifactLike = { kind?: unknown; payload?: Record<string, unknown> | null; path?: string | null }

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asString(value: unknown): string | null {
  if (typeof value === 'string') return value.trim() || null
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  const seen = new Set<string>()
  const items: string[] = []
  value.forEach((entry) => {
    const text = asString(entry)
    if (!text || seen.has(text)) return
    seen.add(text)
    items.push(text)
  })
  return items
}

function keyResults(value: unknown): ScienceKeyResult[] {
  if (!Array.isArray(value)) return []
  return value
    .map((entry) => {
      const record = asRecord(entry)
      if (!record) return null
      const label = asString(record.label) || asString(record.name)
      if (!label) return null
      return { ...record, label } as ScienceKeyResult
    })
    .filter((entry): entry is ScienceKeyResult => Boolean(entry))
}

export function isScienceArtifact(artifact: { kind?: unknown } | null | undefined) {
  return typeof artifact?.kind === 'string' && artifact.kind.startsWith('science.')
}

export function isScienceKind(kind?: unknown) {
  return typeof kind === 'string' && kind.startsWith('science.')
}

export function scienceNodeTypeLabel(nodeType?: string | null) {
  switch (nodeType) {
    case 'science.package_check':
      return 'Package Check'
    case 'science.computational_run':
      return 'Computational Run'
    case 'science.dataset_analysis':
      return 'Dataset Analysis'
    case 'science.parameter_sweep':
      return 'Parameter Sweep'
    case 'science.validation_result':
      return 'Validation'
    case 'science.claim':
      return 'Scientific Claim'
    default:
      return 'Science Node'
  }
}

export function normalizeScienceNode(artifact: QuestArtifactRecord | ArtifactLike): ScienceNodeData {
  const payload = artifact.payload ?? {}
  const artifactId =
    asString(payload.artifact_id) ||
    asString(payload.id) ||
    asString((artifact as ArtifactLike).path)?.split('/').pop()?.replace(/\.json$/i, '') ||
    'science-artifact'
  const kind = asString(payload.kind) || asString(artifact.kind) || 'science.unknown'
  return {
    artifactId,
    nodeId: asString(payload.node_id) || artifactId,
    nodeType: asString(payload.node_type) || kind,
    title: asString(payload.title) || scienceNodeTypeLabel(kind),
    summary: asString(payload.summary) || '',
    status: asString(payload.status) || 'unknown',
    domain: asString(payload.domain),
    packageId: asString(payload.package_id),
    taskType: asString(payload.task_type),
    keyResults: keyResults(payload.key_results),
    evidencePaths: stringList(payload.evidence_paths),
    inputPaths: stringList(payload.input_paths),
    outputPaths: stringList(payload.output_paths),
    logPaths: stringList(payload.log_paths),
    validationPaths: stringList(payload.validation_paths),
    parentNodeIds: stringList(payload.parent_node_ids),
    relatedNodeIds: stringList(payload.related_node_ids),
    claimType: asString(payload.claim_type),
    trust: asString(payload.trust),
  }
}

export function normalizeScienceTrace(trace: QuestNodeTrace): ScienceNodeData | null {
  const payload = asRecord(trace.payload_json)
  const kind = asString(trace.artifact_kind) || asString(payload?.kind)
  if (!isScienceKind(kind)) return null
  return normalizeScienceNode({
    kind,
    path: trace.artifact_id || trace.selection_ref,
    payload: {
      ...(payload || {}),
      artifact_id: payload?.artifact_id ?? trace.artifact_id,
      kind,
      title: payload?.title ?? trace.title,
      summary: payload?.summary ?? trace.summary,
      status: payload?.status ?? trace.status,
    },
  })
}

export function formatScienceValue(result: ScienceKeyResult) {
  const raw = result.value
  const value =
    typeof raw === 'number'
      ? Number.isInteger(raw)
        ? String(raw)
        : String(Number(raw.toPrecision(6)))
      : raw === undefined || raw === null
        ? ''
        : String(raw)
  const unit = asString(result.unit)
  return [value, unit].filter(Boolean).join(' ')
}
