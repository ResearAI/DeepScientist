import type { ConnectorSnapshot, QuestSummary } from '@/types'

export type AdminTask = {
  task_id: string
  kind: string
  status: string
  progress_current?: number | null
  progress_total?: number | null
  progress_percent?: number | null
  current_step?: string | null
  message?: string | null
  created_at?: string | null
  started_at?: string | null
  finished_at?: string | null
  result_path?: string | null
  error?: string | null
  metadata?: Record<string, unknown> | null
  last_event_seq?: number | null
}

export type AdminTaskEvent = {
  seq?: number
  event: string
  message?: string | null
  created_at?: string | null
  data?: Record<string, unknown> | null
}

export type AdminOverviewPayload = {
  ok: boolean
  generated_at?: string
  daemon?: Record<string, unknown>
  cli_health?: Record<string, unknown>
  system_hardware?: AdminSystemHardwarePayload | null
  system_update?: Record<string, unknown> | null
  doctor?: Record<string, unknown> | null
  totals?: Record<string, number>
  latest_failure?: Record<string, unknown> | null
  latest_failure_scanned?: boolean
  quest_insights?: AdminQuestInsights | null
  connector_health?: AdminConnectorHealthSummary | null
  task_health?: AdminTaskHealthSummary | null
  quests?: QuestSummary[]
  connectors?: ConnectorSnapshot[]
  tasks?: AdminTask[]
}

export type AdminQuestSummaryPayload = {
  ok: boolean
  snapshot: QuestSummary & Record<string, unknown>
  workflow_preview?: Record<string, unknown>
  recent_failures?: Array<Record<string, unknown>>
}

export type AdminQuestListPayload = {
  ok: boolean
  items: QuestSummary[]
  total: number
}

export type AdminRuntimeSessionsPayload = {
  ok: boolean
  items: Array<Record<string, unknown>>
  total: number
}

export type AdminLogSourceInfo = {
  source: string
  filename: string
  path?: string
  exists: boolean
  size_bytes?: number | null
  updated_at?: string | number | null
  mtime?: number | null
}

export type AdminLogSourcesPayload = {
  ok: boolean
  items: AdminLogSourceInfo[]
}

export type AdminLogTailPayload = {
  ok: boolean
  source: string
  filename: string
  updated_at?: string | number | null
  lines: string[]
  truncated: boolean
}

export type AdminFailurePayload = {
  ok: boolean
  items: Array<Record<string, unknown>>
}

export type AdminErrorsPayload = {
  ok: boolean
  generated_at?: string
  totals?: Record<string, number>
  degraded_connectors?: Array<Record<string, unknown>>
  runtime_failures?: Array<Record<string, unknown>>
  daemon_errors?: Array<Record<string, unknown>>
  failed_tasks?: Array<Record<string, unknown>>
}

export type AdminRuntimeToolsPayload = {
  ok: boolean
  items: Record<string, Record<string, unknown>>
}

export type AdminGpuInfo = {
  gpu_id: string
  vendor?: string | null
  name: string
  memory_total_mb?: number | null
  memory_total_gb?: number | null
  driver_version?: string | null
  uuid?: string | null
  bus?: string | null
  selected?: boolean
}

export type AdminHardwareTrendPoint = {
  recorded_at: string
  cpu_usage_percent?: number | null
  memory_usage_percent?: number | null
  root_disk_usage_percent?: number | null
}

export type AdminHardwareMetricSummary = {
  latest_usage_percent?: number | null
  avg_usage_percent?: number | null
  max_usage_percent?: number | null
  latest_used_gb?: number | null
  total_gb?: number | null
}

export type AdminHardwareDiskSummary = {
  mount?: string | null
  latest_usage_percent?: number | null
  avg_usage_percent?: number | null
  max_usage_percent?: number | null
  free_gb?: number | null
}

export type AdminHardwareGpuSummary = {
  gpu_id?: string | null
  name?: string | null
  latest_utilization_gpu_percent?: number | null
  avg_utilization_gpu_percent?: number | null
  max_utilization_gpu_percent?: number | null
  latest_memory_used_gb?: number | null
  max_memory_used_gb?: number | null
  memory_total_gb?: number | null
}

export type AdminHardwareRecentStats = {
  sample_count?: number
  window_minutes?: number
  latest_sample?: Record<string, unknown> | null
  cpu?: AdminHardwareMetricSummary
  memory?: AdminHardwareMetricSummary
  root_disk?: AdminHardwareMetricSummary
  disks?: AdminHardwareDiskSummary[]
  gpus?: AdminHardwareGpuSummary[]
  series?: AdminHardwareTrendPoint[]
  log_path?: string | null
}

export type AdminSystemHardwarePayload = {
  ok: boolean
  generated_at?: string
  system: {
    generated_at?: string | null
    host?: Record<string, unknown>
    cpu?: Record<string, unknown>
    memory?: Record<string, unknown>
    disks?: Array<Record<string, unknown>>
    gpus?: AdminGpuInfo[]
    gpu_count?: number
  }
  preferences?: {
    gpu_selection_mode?: string
    selected_gpu_ids?: string[]
    available_gpu_ids?: string[]
    available_gpu_count?: number
    effective_gpu_ids?: string[]
    cuda_visible_devices?: string | null
    include_system_hardware_in_prompt?: boolean
  }
  prompt_hardware_summary?: string
  latest_sample?: Record<string, unknown> | null
  recent_stats?: AdminHardwareRecentStats | null
  save_result?: Record<string, unknown>
  runtime_reload?: Record<string, unknown>
}

export type AdminAuditPayload = {
  ok: boolean
  items: Array<Record<string, unknown>>
}

export type AdminChartCatalogItem = {
  chart_id: string
  kind: 'line' | 'bar'
  title: string
  description?: string
  default_range?: string
  default_step_seconds?: number
  surfaces?: string[]
  priority?: number
  source?: string
  supports_filters?: Record<string, boolean>
  render_hint?: string
}

export type AdminChartCatalogPayload = {
  ok: boolean
  generated_at?: string
  items: AdminChartCatalogItem[]
}

export type AdminLineChartSeries = {
  series_id: string
  label: string
  color?: string
  points: Array<{
    ts: string
    value?: number | null
  }>
}

export type AdminChartFreshness = {
  latest_recorded_at?: string | null
  age_seconds?: number | null
  stale_after_seconds?: number | null
  is_stale?: boolean
}

export type AdminLineChartPayload = {
  chart_id: string
  kind: 'line'
  title: string
  description?: string
  source?: string
  range?: string
  step_seconds?: number
  generated_at?: string
  freshness?: AdminChartFreshness
  filters?: Record<string, unknown>
  render_hint?: string | null
  series: AdminLineChartSeries[]
}

export type AdminBarChartPayload = {
  chart_id: string
  kind: 'bar'
  title: string
  description?: string
  source?: string
  range?: string
  step_seconds?: number
  generated_at?: string
  freshness?: AdminChartFreshness
  filters?: Record<string, unknown>
  render_hint?: string | null
  categories: Array<{
    key: string
    label: string
    value: number
    color?: string
  }>
}

export type AdminChartPayload = AdminLineChartPayload | AdminBarChartPayload

export type AdminChartQueryPayload = {
  ok: boolean
  generated_at?: string
  items: AdminChartPayload[]
}

export type AdminQuestFocusItem = {
  quest_id: string
  title?: string | null
  runtime_status?: string | null
  active_anchor?: string | null
  workspace_mode?: string | null
  runner?: string | null
  updated_at?: string | null
  pending_decisions?: number
  pending_user_messages?: number
  running_bash?: number
  status_line?: string | null
  age_hours?: number | null
}

export type AdminQuestInsights = {
  status_counts?: Record<string, number>
  anchor_counts?: Record<string, number>
  workspace_mode_counts?: Record<string, number>
  runner_counts?: Record<string, number>
  recent_activity?: Record<string, number>
  decision_backlog_buckets?: Record<string, number>
  message_backlog_buckets?: Record<string, number>
  activity_timeline_7d?: Array<Record<string, string | number>>
  top_pending_decisions?: AdminQuestFocusItem[]
  top_waiting_messages?: AdminQuestFocusItem[]
  recently_updated?: AdminQuestFocusItem[]
  active_watchlist?: AdminQuestFocusItem[]
}

export type AdminConnectorHealthSummary = {
  state_counts?: Record<string, number>
  degraded_total?: number
  degraded_items?: Array<Record<string, unknown>>
}

export type AdminTaskHealthSummary = {
  total?: number
  status_counts?: Record<string, number>
  kind_counts?: Record<string, number>
  queued_total?: number
  running_total?: number
  failed_total?: number
  active_items?: AdminTask[]
  failed_items?: AdminTask[]
}

export type AdminStatsSummaryPayload = {
  ok: boolean
  generated_at?: string
  totals?: Record<string, number>
  status_counts?: Record<string, number>
  anchor_counts?: Record<string, number>
  workspace_mode_counts?: Record<string, number>
  runner_counts?: Record<string, number>
  connector_state_counts?: Record<string, number>
  task_status_counts?: Record<string, number>
  task_kind_counts?: Record<string, number>
  failure_type_counts?: Record<string, number>
  decision_backlog_buckets?: Record<string, number>
  message_backlog_buckets?: Record<string, number>
  recent_activity?: Record<string, number>
  activity_timeline_7d?: Array<Record<string, string | number>>
  top_pending_decisions?: AdminQuestFocusItem[]
  top_waiting_messages?: AdminQuestFocusItem[]
  recently_updated?: AdminQuestFocusItem[]
  active_watchlist?: AdminQuestFocusItem[]
}

export type AdminSearchPayload = {
  ok: boolean
  items: Array<Record<string, unknown>>
}

export type AdminIssueDraftPayload = {
  ok: boolean
  title: string
  body_markdown: string
  issue_url_base: string
  repo_url: string
  generated_at?: string
  context?: Record<string, unknown>
}

export type AdminControllersPayload = {
  ok: boolean
  items: Array<Record<string, unknown>>
}

export type AdminDoctorPayload = {
  ok: boolean
  cached?: Record<string, unknown> | null
  latest_task?: AdminTask | null
}

export type AdminRepair = {
  repair_id: string
  status: string
  scope: string
  source_page?: string | null
  targets?: Record<string, unknown> | null
  repair_policy?: string | null
  selected_paths?: string[]
  user_request?: string | null
  ops_quest_id?: string | null
  created_at?: string | null
  updated_at?: string | null
  closed_at?: string | null
}

export type AdminRepairsPayload = {
  ok: boolean
  items: AdminRepair[]
}

export type AdminRepairResponse = {
  ok: boolean
  repair: AdminRepair
}
