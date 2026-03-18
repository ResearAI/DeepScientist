export type BashSessionStatus = 'running' | 'terminating' | 'completed' | 'failed' | 'terminated'

export type BashSessionMode = 'detach' | 'await'

export type BashProgress = {
  current: number
  total?: number | null
  percent?: number | null
  unit?: string | null
  desc?: string | null
  phase?: string | null
  rate?: number | null
  eta?: number | null
  next_reply_in?: number | null
  next_check_in?: number | null
  next_reply_at?: string | null
  next_check_at?: string | null
  ts?: string | null
  source?: string | null
  extra?: Record<string, unknown> | null
}

export type BashSession = {
  bash_id: string
  project_id: string
  chat_session_id?: string | null
  task_id: string
  cli_server_id: string
  agent_id: string
  agent_instance_id?: string | null
  started_by_user_id: string
  stopped_by_user_id?: string | null
  kind?: string
  label?: string | null
  comment?: string | Record<string, unknown> | null
  command: string
  workdir: string
  cwd?: string
  log_path: string
  mode: BashSessionMode
  status: BashSessionStatus
  exit_code?: number | null
  stop_reason?: string | null
  last_progress?: BashProgress | null
  last_progress_at?: string | null
  last_output_at?: string | null
  last_output_seq?: number | null
  run_age_seconds?: number | null
  status_age_seconds?: number | null
  silent_seconds?: number | null
  progress_age_seconds?: number | null
  latest_signal_at?: string | null
  signal_age_seconds?: number | null
  watchdog_after_seconds?: number | null
  watchdog_overdue?: boolean | null
  started_at: string
  finished_at?: string | null
  updated_at?: string
}

export type BashLogEntry = {
  seq: number
  stream: string
  line: string
  timestamp: string
}

export type BashTranscriptLine = {
  kind: 'prompt' | 'output' | 'spacer'
  bash_id?: string | null
  seq?: number | null
  stream?: string | null
  text?: string | null
  timestamp?: string | null
}

export type BashTranscriptPage = {
  page: number
  page_size: number
  total_lines: number
  page_count: number
  lines: BashTranscriptLine[]
  latest_seq_by_bash_id: Record<string, number | null>
  tail_limit?: number | null
  tail_start_seq_by_bash_id?: Record<string, number | null>
}

export type BashLogMeta = {
  tailLimit?: number | null
  tailStartSeq?: number | null
  latestSeq?: number | null
  afterSeq?: number | null
  beforeSeq?: number | null
}

export type BashStopResponse = {
  success: boolean
  status: string
  session?: BashSession
}
