import type { FeedItem } from '@/types'

type OperationFeedItem = Extract<FeedItem, { type: 'operation' }>

export type RenderOperationFeedItem = OperationFeedItem & {
  renderId: string
  startedAt?: string
  completedAt?: string
  hasResult: boolean
  callItem?: OperationFeedItem
  resultItem?: OperationFeedItem
}

export type RenderFeedItem = Exclude<FeedItem, { type: 'operation' }> | RenderOperationFeedItem

function normalizeComparableText(value?: string | null) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
}

function textsLookEquivalent(left: string | undefined | null, right: string | undefined | null) {
  const normalizedLeft = normalizeComparableText(left)
  const normalizedRight = normalizeComparableText(right)
  if (!normalizedLeft || !normalizedRight) return false
  if (normalizedLeft === normalizedRight) return true
  const [shorter, longer] =
    normalizedLeft.length <= normalizedRight.length
      ? [normalizedLeft, normalizedRight]
      : [normalizedRight, normalizedLeft]
  return shorter.length >= 48 && longer.includes(shorter)
}

function parseTimestampMs(value?: string) {
  if (!value) return null
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : null
}

function withinDuplicateWindow(left?: string, right?: string, seconds = 90) {
  const leftMs = parseTimestampMs(left)
  const rightMs = parseTimestampMs(right)
  if (leftMs == null || rightMs == null) return true
  return Math.abs(leftMs - rightMs) <= seconds * 1000
}

function isInteractiveArtifact(item: FeedItem): item is Extract<FeedItem, { type: 'artifact' }> {
  return item.type === 'artifact' && Boolean(item.interactionId && normalizeComparableText(item.content))
}

function isVisibleAssistantMessage(item: FeedItem): item is Extract<FeedItem, { type: 'message' }> {
  return (
    item.type === 'message' &&
    item.role === 'assistant' &&
    !item.reasoning &&
    normalizeComparableText(item.content).length > 0
  )
}

function isVisibleUserMessage(item: FeedItem): item is Extract<FeedItem, { type: 'message' }> {
  return item.type === 'message' && item.role === 'user' && normalizeComparableText(item.content).length > 0
}

function shouldSuppressDuplicateArtifact(
  rendered: FeedItem[],
  candidate: Extract<FeedItem, { type: 'artifact' }>
) {
  for (let index = rendered.length - 1; index >= 0; index -= 1) {
    const previous = rendered[index]
    if (isVisibleUserMessage(previous)) {
      return false
    }
    if (!isInteractiveArtifact(previous)) {
      continue
    }
    if (previous.kind !== candidate.kind) {
      continue
    }
    if (!withinDuplicateWindow(previous.createdAt, candidate.createdAt)) {
      continue
    }
    if (textsLookEquivalent(previous.content, candidate.content)) {
      return true
    }
  }
  return false
}

function dropEquivalentInteractiveArtifacts(
  rendered: FeedItem[],
  candidate: Extract<FeedItem, { type: 'message' }>
) {
  for (let index = rendered.length - 1; index >= 0; index -= 1) {
    const previous = rendered[index]
    if (isVisibleUserMessage(previous)) {
      break
    }
    if (!isInteractiveArtifact(previous)) {
      continue
    }
    if (!withinDuplicateWindow(previous.createdAt, candidate.createdAt)) {
      continue
    }
    if (textsLookEquivalent(previous.content, candidate.content)) {
      rendered.splice(index, 1)
    }
  }
}

export function dedupeVisibleFeedItems(items: FeedItem[]): FeedItem[] {
  const deduped: FeedItem[] = []
  for (const item of items) {
    if (isInteractiveArtifact(item) && shouldSuppressDuplicateArtifact(deduped, item)) {
      continue
    }
    if (isVisibleAssistantMessage(item)) {
      dropEquivalentInteractiveArtifacts(deduped, item)
    }
    deduped.push(item)
  }
  return deduped
}

function parseJsonRecord(value?: string) {
  if (!value) return null
  try {
    const parsed = JSON.parse(value)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
  } catch {
    return null
  }
  return null
}

function deriveOperationBashId(item: OperationFeedItem) {
  const metadataBashId =
    typeof item.metadata?.bash_id === 'string'
      ? item.metadata.bash_id
      : typeof item.metadata?.bashId === 'string'
        ? item.metadata.bashId
        : ''
  if (metadataBashId.trim()) return metadataBashId.trim()
  const outputRecord = parseJsonRecord(item.output)
  const nestedOutput =
    outputRecord?.result && typeof outputRecord.result === 'object' && !Array.isArray(outputRecord.result)
      ? (outputRecord.result as Record<string, unknown>)
      : outputRecord
  const outputBashId =
    typeof nestedOutput?.bash_id === 'string'
      ? nestedOutput.bash_id
      : typeof nestedOutput?.bashId === 'string'
        ? nestedOutput.bashId
        : ''
  if (outputBashId.trim()) return outputBashId.trim()
  return ''
}

function normalizeOperationArgs(args?: string) {
  return String(args || '').replace(/\s+/g, ' ').trim()
}

export function buildOperationIdentity(
  item: Pick<OperationFeedItem, 'id' | 'runId' | 'toolCallId'>
) {
  const runId = item.runId?.trim() || ''
  const toolCallId = item.toolCallId?.trim() || ''
  if (runId && toolCallId) {
    return `tool:${runId}:${toolCallId}`
  }
  if (toolCallId) {
    return `tool:${toolCallId}`
  }
  return item.id
}

function resolveOperationMergeKey(item: OperationFeedItem) {
  const toolCallId = item.toolCallId?.trim() || ''
  const runId = item.runId?.trim() || ''
  if (toolCallId) return buildOperationIdentity(item)
  const toolName = String(item.toolName || '').trim().toLowerCase()
  const mcpServer = String(item.mcpServer || '').trim().toLowerCase()
  const mcpTool = String(item.mcpTool || '').trim().toLowerCase()
  const isBashExec =
    mcpServer === 'bash_exec' ||
    toolName === 'bash_exec' ||
    toolName === 'bash_exec.bash_exec' ||
    (mcpServer === 'bash_exec' && mcpTool === 'bash_exec')
  if (!isBashExec) return ''
  const bashId = deriveOperationBashId(item)
  if (bashId) return `bash:${runId || 'unknown'}:${bashId}`
  const normalizedArgs = normalizeOperationArgs(item.args)
  if (normalizedArgs) return `bash-args:${runId || 'unknown'}:${toolName || 'bash_exec'}:${normalizedArgs}`
  return ''
}

function mergeMetadata(
  ...values: Array<Record<string, unknown> | undefined>
): Record<string, unknown> | undefined {
  const merged = values.reduce<Record<string, unknown>>((accumulator, value) => {
    if (!value) return accumulator
    return {
      ...accumulator,
      ...value,
    }
  }, {})
  return Object.keys(merged).length > 0 ? merged : undefined
}

function createRenderOperation(item: OperationFeedItem): RenderOperationFeedItem {
  const isResult = item.label === 'tool_result'
  return {
    ...item,
    renderId: buildOperationIdentity(item),
    startedAt: isResult ? undefined : item.createdAt,
    completedAt: isResult ? item.createdAt : undefined,
    hasResult: isResult,
    callItem: isResult ? undefined : item,
    resultItem: isResult ? item : undefined,
  }
}

function mergeRenderOperation(
  current: RenderOperationFeedItem,
  next: OperationFeedItem
): RenderOperationFeedItem {
  const callItem = next.label === 'tool_call' ? next : current.callItem
  const resultItem = next.label === 'tool_result' ? next : current.resultItem
  const primary = callItem ?? resultItem ?? next

  return {
    ...primary,
    id: current.id,
    renderId: current.renderId,
    eventId: resultItem?.eventId ?? callItem?.eventId ?? current.eventId ?? next.eventId,
    runId: callItem?.runId ?? resultItem?.runId ?? current.runId ?? next.runId,
    label: resultItem ? 'tool_result' : 'tool_call',
    content: resultItem?.content || callItem?.content || current.content || next.content,
    toolName: callItem?.toolName || resultItem?.toolName || current.toolName || next.toolName,
    toolCallId: current.toolCallId || next.toolCallId,
    status: resultItem?.status || callItem?.status || current.status || next.status,
    subject: resultItem?.subject ?? callItem?.subject ?? current.subject ?? next.subject,
    args: callItem?.args ?? resultItem?.args ?? current.args ?? next.args,
    output: resultItem?.output ?? callItem?.output ?? current.output ?? next.output,
    createdAt: callItem?.createdAt ?? resultItem?.createdAt ?? current.createdAt ?? next.createdAt,
    mcpServer: callItem?.mcpServer || resultItem?.mcpServer || current.mcpServer || next.mcpServer,
    mcpTool: callItem?.mcpTool || resultItem?.mcpTool || current.mcpTool || next.mcpTool,
    metadata: mergeMetadata(current.metadata, callItem?.metadata, resultItem?.metadata, next.metadata),
    comment: resultItem?.comment ?? callItem?.comment ?? current.comment ?? next.comment,
    monitorPlanSeconds:
      resultItem?.monitorPlanSeconds ??
      callItem?.monitorPlanSeconds ??
      current.monitorPlanSeconds ??
      next.monitorPlanSeconds,
    monitorStepIndex:
      resultItem?.monitorStepIndex ??
      callItem?.monitorStepIndex ??
      current.monitorStepIndex ??
      next.monitorStepIndex,
    nextCheckAfterSeconds:
      resultItem?.nextCheckAfterSeconds ??
      callItem?.nextCheckAfterSeconds ??
      current.nextCheckAfterSeconds ??
      next.nextCheckAfterSeconds,
    startedAt: callItem?.createdAt ?? current.startedAt ?? resultItem?.createdAt ?? next.createdAt,
    completedAt: resultItem?.createdAt ?? current.completedAt,
    hasResult: Boolean(resultItem),
    callItem,
    resultItem,
  }
}

export function mergeFeedItemsForRender(items: FeedItem[]): RenderFeedItem[] {
  const dedupedItems = dedupeVisibleFeedItems(items)
  const merged: RenderFeedItem[] = []
  const operationIndexByMergeKey = new Map<string, number>()

  for (const item of dedupedItems) {
    if (item.type !== 'operation') {
      merged.push(item)
      continue
    }

    const mergeKey = resolveOperationMergeKey(item)
    if (!mergeKey) {
      merged.push(createRenderOperation(item))
      continue
    }

    const existingIndex = operationIndexByMergeKey.get(mergeKey)
    if (existingIndex == null) {
      merged.push(createRenderOperation(item))
      operationIndexByMergeKey.set(mergeKey, merged.length - 1)
      continue
    }

    const existing = merged[existingIndex]
    if (!existing || existing.type !== 'operation') {
      merged.push(createRenderOperation(item))
      operationIndexByMergeKey.set(mergeKey, merged.length - 1)
      continue
    }

    merged[existingIndex] = mergeRenderOperation(existing, item)
  }

  return merged
}

export function countActiveRenderedOperations(items: FeedItem[]) {
  return mergeFeedItemsForRender(items).reduce((count, item) => {
    if (item.type !== 'operation') return count
    return item.hasResult ? count : count + 1
  }, 0)
}

export function findLatestRenderedOperationId(
  items: RenderFeedItem[],
  predicate?: (item: RenderOperationFeedItem) => boolean
) {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index]
    if (item.type !== 'operation') continue
    if (predicate && !predicate(item)) continue
    return item.renderId
  }
  return null
}
