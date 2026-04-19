'use client'

import { AgentCommentBlock } from '@/components/feed/AgentCommentBlock'
import { McpToolView } from '@/components/chat/toolViews/McpToolView'
import { deriveMcpIdentity } from '@/lib/mcpIdentity'
import type { ToolContent } from '@/lib/plugins/ai-manus/types'
import type { EventMetadata } from '@/lib/types/chat-events'
import type { AgentComment } from '@/types'

function parseStructuredValue(value?: string) {
  if (!value) return null
  try {
    return JSON.parse(value) as Record<string, unknown>
  } catch {
    return null
  }
}

function unwrapToolResult(value: unknown): unknown {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value
  const record = value as Record<string, unknown>
  if (record.structured_content && record.structured_content !== value) {
    return unwrapToolResult(record.structured_content)
  }
  if (record.structured_result && record.structured_result !== value) {
    return unwrapToolResult(record.structured_result)
  }
  return value
}

export function QuestMcpOperation({
  questId,
  itemId,
  toolCallId,
  toolName,
  label,
  status,
  args,
  output,
  createdAt,
  metadata,
  mcpServer,
  mcpTool,
  comment,
}: {
  questId: string
  itemId: string
  toolCallId?: string
  toolName?: string
  label: 'tool_call' | 'tool_result'
  status?: string
  args?: string
  output?: string
  createdAt?: string
  metadata?: Record<string, unknown>
  mcpServer?: string
  mcpTool?: string
  comment?: AgentComment | null
}) {
  const timestamp = createdAt ? Date.parse(createdAt) : Date.now()
  const resolvedTimestamp = Number.isFinite(timestamp) ? timestamp : Date.now()
  const parsedArgs = parseStructuredValue(args)
  const parsedOutput = unwrapToolResult(parseStructuredValue(output))
  const resolvedIdentity = deriveMcpIdentity(toolName, mcpServer, mcpTool)
  const resolvedFunction =
    resolvedIdentity.server && resolvedIdentity.tool
      ? `mcp__${resolvedIdentity.server}__${resolvedIdentity.tool}`
      : toolName || 'mcp'

  const eventMetadata: EventMetadata = {
    surface: 'copilot',
    quest_id: questId,
    session_id:
      typeof metadata?.session_id === 'string' && metadata.session_id.trim()
        ? metadata.session_id
        : `quest:${questId}`,
    sender_type: 'agent',
    sender_label: 'DeepScientist',
    sender_name: 'DeepScientist',
    ...(resolvedIdentity.server ? { mcp_server: resolvedIdentity.server } : {}),
    ...(resolvedIdentity.tool ? { mcp_tool: resolvedIdentity.tool } : {}),
    ...(metadata as EventMetadata | undefined),
  }

  const toolContent: ToolContent = {
    event_id: itemId,
    timestamp: resolvedTimestamp,
    tool_call_id: toolCallId || itemId,
    name: resolvedIdentity.tool || toolName || resolvedIdentity.server || 'mcp',
    function: resolvedFunction,
    status: label === 'tool_call' ? 'calling' : 'called',
    args: parsedArgs ?? (args ? { raw: args } : {}),
    content:
      label === 'tool_result'
        ? {
            ...(parsedOutput ? { result: parsedOutput } : {}),
            ...(output && !parsedOutput ? { text: output } : {}),
            ...(status ? { status } : {}),
          }
        : {},
    metadata: eventMetadata,
  }

  return (
    <div
      className="flex min-w-0 flex-col gap-2"
      data-copilot-tool-kind="mcp"
      data-copilot-tool-server={resolvedIdentity.server || undefined}
      data-copilot-tool-name={resolvedIdentity.tool || toolName || undefined}
    >
      {comment ? <AgentCommentBlock comment={comment} /> : null}
      <div className="min-w-0 overflow-hidden rounded-[12px]">
        <McpToolView
          toolContent={toolContent}
          live={label === 'tool_call'}
          sessionId={eventMetadata.session_id}
          projectId={questId}
          readOnly={false}
          panelMode="inline"
        />
      </div>
    </div>
  )
}

export default QuestMcpOperation
