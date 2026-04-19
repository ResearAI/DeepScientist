import type { CitationPayload } from '@/lib/types/citations'
import type { Effect } from '@/lib/types/ui-effects'

export type ChatEventType =
  | 'message'
  | 'tool'
  | 'step'
  | 'status'
  | 'reasoning'
  | 'plan'
  | 'recovery'
  | 'error'
  | 'done'
  | 'title'
  | 'wait'
  | 'attachments'
  | 'receipt'
  | 'text_delta'
  | 'reasoning_delta'
  | 'tool_call'
  | 'tool_result'

export type ExecutionTarget = 'sandbox' | 'cli'
export type ChatSurface = 'welcome' | 'copilot' | 'lab-direct' | 'lab-group' | 'lab-friends'

export interface EventMetadata {
  surface?: ChatSurface
  reply_to_surface?: ChatSurface
  execution_target?: ExecutionTarget
  cli_server_id?: string | null
  context?: Record<string, unknown>
  question_tool?: boolean
  quote?: boolean
  mcp_status?: boolean
  agent_id?: string
  agent_label?: string
  agent_role?: string
  agent_source?: string
  agent_instance_id?: string
  agent_display_name?: string
  agent_logo?: string
  agent_avatar_color?: string
  sender_type?: 'user' | 'agent' | 'system'
  sender_id?: string
  sender_instance_id?: string
  sender_name?: string
  sender_label?: string
  sender_avatar_url?: string
  sender_avatar_color?: string
  message_kind?: 'text' | 'status' | 'system' | 'moment' | string
  message_importance?: 'low' | 'high' | 'friend' | string
  delivery_state?: 'sending' | 'sent' | 'delivered' | 'failed' | string
  delivery_target_count?: number
  delivery_delivered_count?: number
  mention_targets?: string[]
  moment_id?: string
  moment_like_count?: number
  moment_comment_count?: number
  moment_media?: unknown
  source_ts?: string
  session_id?: string
  quest_id?: string
  mcp_server?: string
  mcp_tool?: string
  bash_id?: string
  bash_status?: string
  bash_mode?: string
  bash_command?: string
  bash_workdir?: string
  quest_event_type?: string
  quest_run_id?: string
  quest_skill_id?: string
  quest_node_id?: string
  group_message_id?: string
  reply_state?: string
  lab_mode?: string
  lab_response_phase?: string
  lab_response_strategy?: string
  lab_required_status_importance?: string
  lab_event_origin?: string
  citations?: CitationPayload[]
  ai_usage?: {
    requests?: number
    input_tokens: number
    output_tokens: number
    total_tokens: number
    cached_tokens?: number
    reasoning_tokens?: number
    estimated?: boolean
  }
}

export interface BaseEventData {
  event_id: string
  timestamp: number
  seq?: number
  created_at?: string
  metadata?: EventMetadata
}

export interface AttachmentInfo {
  file_id: string
  filename: string
  content_type?: string
  size: number
  upload_date?: string
  metadata?: Record<string, unknown>
  file_url?: string
  file_path?: string
  include_in_context?: boolean
  status?: 'queued' | 'uploading' | 'success' | 'failed'
  progress?: number
  error?: string
}

export interface AttachmentContextPayload {
  file_id: string
  name: string
  mime?: string | null
  size?: number | null
  status?: string
}

export interface ToolEventData extends BaseEventData {
  tool_call_id: string
  name: string
  status: 'calling' | 'called' | 'failed'
  function: string
  args: Record<string, unknown>
  content?: Record<string, unknown>
  ui_effect?: Effect
  ui_effects?: Effect[]
}

export interface StepEventData extends BaseEventData {
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked' | 'paused'
  id: string
  description: string
}

export interface StatusEventData extends BaseEventData {
  message?: string
  text?: string
  status?: string
  importance?: string
  phase?: string
  step?: string
  event_type?: string
  completed?: string[]
  blocked?: string[]
  next?: string[]
  evidence_refs?: string[]
  related_files?: string[]
  artifacts?: string[]
  diff_ref?: string
  tags?: string[]
  reply_to_message_id?: string
  source_ts?: string
  tool_call_id?: string
}

export interface ReasoningEventData extends BaseEventData {
  reasoning_id: string
  reasoning_stream_id?: string
  status: 'in_progress' | 'completed'
  delta?: string
  content?: string
  kind?: 'full' | 'summary'
}

export interface MessageEventData extends BaseEventData {
  content?: string
  role: 'user' | 'assistant'
  attachments?: AttachmentInfo[]
  delta?: string
}

export interface AttachmentsEventData extends BaseEventData {
  role: 'user' | 'assistant'
  attachments: AttachmentInfo[]
}

export interface ErrorEventData extends BaseEventData {
  error: string
}

export interface DoneEventData extends BaseEventData {}

export interface WaitEventData extends BaseEventData {}

export interface ReceiptEventData extends BaseEventData {
  message_ref: string
  delivery_state: 'sent' | 'delivered' | 'failed'
  reply_state?: string
  target_count?: number
  delivered_count?: number
}

export interface RecoveryEventData extends BaseEventData {
  status: 'recovering' | 'recovered' | 'failed'
  missed_event_count?: number
  last_seq?: number
  reason?: string
}

export interface TitleEventData extends BaseEventData {
  title: string
}

export interface PlanEventData extends BaseEventData {
  steps: StepEventData[]
  task_plan?: {
    path?: string
    hash?: string
    tasks: TaskPlanItem[]
  }
}

export interface TaskPlanItem {
  task: string
  status?: string | null
  change_reason: string
  detail: string
  sub_tasks: string[]
}

export type AgentSSEEvent = {
  event: ChatEventType
  data:
    | ToolEventData
    | StepEventData
    | StatusEventData
    | ReasoningEventData
    | MessageEventData
    | AttachmentsEventData
    | ErrorEventData
    | DoneEventData
    | TitleEventData
    | WaitEventData
    | PlanEventData
    | ReceiptEventData
    | RecoveryEventData
}
