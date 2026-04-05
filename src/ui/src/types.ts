export type Locale = 'en' | 'zh'

export interface ProjectionStatus {
  projection_id: string
  state: 'missing' | 'queued' | 'building' | 'ready' | 'stale' | 'failed' | string
  progress_current?: number
  progress_total?: number
  current_step?: string | null
  source_signature?: string | null
  generated_at?: string | null
  last_success_at?: string | null
  error?: string | null
}

export interface GuidanceRoute {
  action: string
  label: string
  when: string
  tradeoff: string
}

export interface GuidanceArtifactCall {
  name: string
  purpose: string
}

export interface GuidanceVm {
  current_anchor: string
  recommended_skill: string
  recommended_action: string
  summary: string
  why_now: string
  complete_when: string[]
  alternative_routes?: GuidanceRoute[]
  suggested_artifact_calls?: GuidanceArtifactCall[]
  requires_user_decision?: boolean
  pending_interaction_id?: string | null
  source_artifact_kind?: string | null
  source_artifact_id?: string | null
  related_paths?: string[]
  stage_status?: string | null
}

export interface QuestSummary {
  quest_id: string
  title: string
  status: string
  active_anchor: string
  workspace_mode?: string
  runner?: string
  branch?: string
  head?: string
  created_at?: string
  updated_at?: string
  quest_root?: string
  bound_conversations?: string[]
  baseline_gate?: string | null
  active_baseline_id?: string | null
  active_baseline_variant_id?: string | null
  requested_baseline_ref?: {
    baseline_id?: string | null
    variant_id?: string | null
  } | null
  startup_contract?: Record<string, unknown> | null
  confirmed_baseline_ref?: {
    baseline_id?: string | null
    variant_id?: string | null
    baseline_path?: string | null
    baseline_root_rel_path?: string | null
    source_mode?: string | null
    confirmed_at?: string | null
    comment?: unknown
  } | null
  active_run_id?: string | null
  history_count?: number
  artifact_count?: number
  summary?: {
    status_line?: string
    latest_metric?: {
      key?: string
      value?: string | number
      delta_vs_baseline?: string | number
      label?: string | null
      direction?: string | null
      unit?: string | null
      decimals?: number | null
    }
    latest_bash_session?: Record<string, unknown> | null
  }
  pending_decisions?: string[]
  waiting_interaction_id?: string | null
  latest_thread_interaction_id?: string | null
  default_reply_interaction_id?: string | null
  runtime_status?: string
  display_status?: string
  continuation_policy?: string
  pending_user_message_count?: number
  stop_reason?: string | null
  active_interaction_id?: string | null
  last_artifact_interact_at?: string | null
  last_delivered_batch_id?: string | null
  last_delivered_at?: string | null
  counts?: {
    memory_cards?: number
    artifacts?: number
    pending_decision_count?: number
    analysis_run_count?: number
    bash_session_count?: number
    bash_running_count?: number
    pending_user_message_count?: number
  }
  guidance?: GuidanceVm | null
  paths?: Record<string, string | null | undefined>
  recent_artifacts?: RecentArtifact[]
  recent_runs?: RecentRun[]
  idea_lines?: Array<{
    idea_line_id: string
    idea_id: string
    idea_branch?: string | null
    idea_title?: string | null
    lineage_intent?: string | null
    parent_branch?: string | null
    latest_main_run_id?: string | null
    latest_main_run_branch?: string | null
    paper_line_id?: string | null
    paper_branch?: string | null
    selected_outline_ref?: string | null
    analysis_campaign_count?: number
    analysis_slice_count?: number
    completed_analysis_slice_count?: number
    mapped_analysis_slice_count?: number
    required_count?: number
    ready_required_count?: number
    unmapped_count?: number
    open_supplementary_count?: number
    draft_status?: string | null
    bundle_status?: string | null
    updated_at?: string | null
    paths?: Record<string, string | null | undefined>
  }>
  active_idea_line_ref?: string | null
  paper_lines?: Array<{
    paper_line_id: string
    paper_branch?: string | null
    paper_root?: string | null
    workspace_root?: string | null
    source_branch?: string | null
    source_run_id?: string | null
    source_idea_id?: string | null
    selected_outline_ref?: string | null
    title?: string | null
    required_count?: number
    ready_required_count?: number
    section_count?: number
    ready_section_count?: number
    unmapped_count?: number
    open_supplementary_count?: number
    draft_status?: string | null
    bundle_status?: string | null
    updated_at?: string | null
    paths?: Record<string, string | null | undefined>
  }>
  active_paper_line_ref?: string | null
  paper_contract_health?: {
    paper_line_id?: string | null
    paper_branch?: string | null
    selected_outline_ref?: string | null
    contract_ok?: boolean
    writing_ready?: boolean
    finalize_ready?: boolean
    required_count?: number
    ready_required_count?: number
    section_count?: number
    ready_section_count?: number
    ledger_item_count?: number
    unresolved_required_count?: number
    unmapped_completed_count?: number
    open_supplementary_count?: number
    blocking_open_supplementary_count?: number
    draft_status?: string | null
    bundle_status?: string | null
    blocking_reasons?: string[]
    recommended_next_stage?: string | null
    recommended_action?: string | null
    unresolved_required_items?: Array<{
      section_id?: string | null
      section_title?: string | null
      item_id?: string | null
      status?: string | null
    }>
    unmapped_completed_items?: Array<{
      campaign_id?: string | null
      slice_id?: string | null
      item_id?: string | null
      section_id?: string | null
      title?: string | null
    }>
    blocking_pending_slices?: Array<{
      campaign_id?: string | null
      slice_id?: string | null
      item_id?: string | null
      section_id?: string | null
      title?: string | null
    }>
  } | null
  paper_contract?: {
    paper_root?: string | null
    workspace_root?: string | null
    paper_branch?: string | null
    source_branch?: string | null
    selected_outline_ref?: string | null
    title?: string | null
    story?: string | null
    research_questions?: string[]
    experimental_designs?: string[]
    contributions?: string[]
    evidence_contract?: Record<string, unknown> | null
    evidence_summary?: {
      item_count?: number
      main_text_ready_count?: number
      appendix_item_count?: number
      unmapped_item_count?: number
    } | null
    summary?: string | null
    sections?: Array<{
      section_id: string
      title: string
      paper_role?: string | null
      status?: string | null
      claims?: string[]
      required_items?: string[]
      optional_items?: string[]
      result_table?: Array<{
        item_id?: string | null
        title?: string | null
        kind?: string | null
        paper_role?: string | null
        status?: string | null
        claim_links?: string[]
        metric_summary?: string | null
        result_summary?: string | null
        source_paths?: string[]
        updated_at?: string | null
      }>
    }>
    paths?: Record<string, string | null | undefined>
    bundle_manifest?: Record<string, unknown> | null
    outline_payload?: Record<string, unknown> | null
  } | null
  paper_evidence?: {
    paper_root?: string | null
    workspace_root?: string | null
    selected_outline_ref?: string | null
    item_count?: number
    main_text_ready_count?: number
    appendix_item_count?: number
    unmapped_item_count?: number
    paths?: Record<string, string | null | undefined>
    items?: Array<{
      item_id?: string | null
      title?: string | null
      kind?: string | null
      paper_role?: string | null
      section_id?: string | null
      status?: string | null
      claim_links?: string[]
      setup?: string | null
      result_summary?: string | null
      source_paths?: string[]
      key_metrics?: Array<{
        metric_id?: string | null
        value?: unknown
        direction?: string | null
        decimals?: number | null
      }>
    }>
  } | null
  analysis_inventory?: {
    campaign_count?: number
    slice_count?: number
    completed_slice_count?: number
    mapped_slice_count?: number
    campaigns?: Array<{
      campaign_id: string
      title?: string | null
      active_idea_id?: string | null
      parent_run_id?: string | null
      parent_branch?: string | null
      paper_line_id?: string | null
      paper_line_branch?: string | null
      paper_line_root?: string | null
      selected_outline_ref?: string | null
      todo_manifest_path?: string | null
      campaign_path?: string | null
      summary_path?: string | null
      summary_excerpt?: string | null
      slice_count?: number
      completed_slice_count?: number
      mapped_slice_count?: number
      pending_slice_count?: number
      slices?: Array<{
        slice_id: string
        title?: string | null
        status?: string | null
        tier?: string | null
        exp_id?: string | null
        paper_role?: string | null
        section_id?: string | null
        item_id?: string | null
        claim_links?: string[]
        branch?: string | null
        worktree_root?: string | null
        mapped?: boolean | null
        research_question?: string | null
        experimental_design?: string | null
        result_path?: string | null
        result_excerpt?: string | null
      }>
    }>
  } | null
}

export type BaselineRegistryVariant = {
  variant_id: string
  label?: string | null
  summary?: string | null
  path?: string | null
  metrics_summary?: Record<string, unknown> | null
}

export type BaselineRegistryEntry = {
  registry_kind?: string | null
  schema_version?: number | null
  entry_id?: string | null
  baseline_id: string
  status?: string | null
  summary?: string | null
  task?: string | null
  path?: string | null
  created_at?: string | null
  updated_at?: string | null
  confirmed_at?: string | null
  source_mode?: string | null
  source_quest_id?: string | null
  source_baseline_path?: string | null
  selected_variant_id?: string | null
  materializable?: boolean | null
  availability?: string | null
  primary_metric?: Record<string, unknown> | null
  baseline_variants?: BaselineRegistryVariant[] | null
  default_variant_id?: string | null
  metric_contract?: Record<string, unknown> | null
  metrics_summary?: Record<string, unknown> | null
}

export interface ConnectorSnapshot {
  name: string
  display_mode?: string
  mode?: string
  transport?: string
  relay_url?: string | null
  main_chat_id?: string | null
  last_conversation_id?: string | null
  enabled?: boolean
  connection_state?: string
  auth_state?: string
  last_error?: string | null
  inbox_count?: number
  outbox_count?: number
  ignored_count?: number
  binding_count?: number
  target_count?: number
  bindings?: ConnectorBindingSnapshot[]
  known_targets?: ConnectorTargetSnapshot[]
  recent_conversations?: ConnectorRecentConversation[]
  recent_events?: ConnectorRecentEvent[]
  default_target?: ConnectorTargetSnapshot | null
  discovered_targets?: ConnectorTargetSnapshot[]
  profiles?: ConnectorProfileSnapshot[]
  details?: Record<string, unknown>
}

export interface ConnectorProfileSnapshot {
  profile_id: string
  label?: string | null
  bot_name?: string | null
  app_id?: string | null
  transport?: string | null
  main_chat_id?: string | null
  default_conversation_id?: string | null
  last_conversation_id?: string | null
  connection_state?: string | null
  auth_state?: string | null
  last_error?: string | null
  inbox_count?: number
  outbox_count?: number
  ignored_count?: number
  discovered_targets?: ConnectorTargetSnapshot[]
  recent_conversations?: ConnectorRecentConversation[]
  bindings?: ConnectorBindingSnapshot[]
  target_count?: number
  binding_count?: number
}

export interface ConnectorBindingSnapshot {
  conversation_id: string
  quest_id?: string | null
  quest_title?: string | null
  updated_at?: string | null
  profile_id?: string | null
  profile_label?: string | null
}

export interface ConnectorAvailabilitySnapshot {
  has_enabled_external_connector: boolean
  has_bound_external_connector: boolean
  should_recommend_binding: boolean
  preferred_connector_name?: string | null
  preferred_conversation_id?: string | null
  available_connectors: Array<{
    name: string
    enabled: boolean
    connection_state?: string | null
    binding_count?: number
    target_count?: number
    has_delivery_target?: boolean
  }>
}

export interface WeixinQrLoginStartPayload {
  ok: boolean
  session_key?: string | null
  qrcode_content?: string | null
  qrcode_url?: string | null
  message?: string | null
}

export interface WeixinQrLoginWaitPayload {
  ok: boolean
  connected: boolean
  status?: string | null
  session_key?: string | null
  qrcode_content?: string | null
  qrcode_url?: string | null
  account_id?: string | null
  login_user_id?: string | null
  base_url?: string | null
  snapshot?: ConnectorSnapshot | null
  message?: string | null
}

export interface ConnectorRecentConversation {
  conversation_id: string
  connector?: string
  chat_type: string
  chat_id: string
  chat_id_raw?: string | null
  profile_id?: string | null
  profile_label?: string | null
  label?: string | null
  source?: string | null
  sender_id?: string | null
  sender_name?: string | null
  quest_id?: string | null
  message_id?: string | null
  updated_at?: string | null
}

export interface ConnectorRecentEvent {
  event_type: 'inbound' | 'outbound' | 'ignored'
  created_at?: string | null
  conversation_id?: string | null
  chat_type?: string | null
  chat_id?: string | null
  profile_id?: string | null
  profile_label?: string | null
  label?: string | null
  kind?: string | null
  message?: string | null
  reason?: string | null
  ok?: boolean | null
  queued?: boolean | null
  transport?: string | null
}

export interface ConnectorTargetSnapshot {
  conversation_id: string
  connector?: string
  chat_type: string
  chat_id: string
  chat_id_raw?: string | null
  profile_id?: string | null
  profile_label?: string | null
  label?: string | null
  source?: string | null
  sources?: string[]
  quest_id?: string | null
  updated_at?: string | null
  is_default?: boolean
  selectable?: boolean
  is_bound?: boolean
  bound_quest_id?: string | null
  bound_quest_title?: string | null
  warning?: string | null
  first_seen_at?: string | null
}

export interface SystemUpdateResult {
  ok?: boolean
  target_version?: string | null
  message?: string | null
  log_path?: string | null
}

export interface SystemUpdateStatus {
  ok: boolean
  package_name?: string
  install_mode?: string
  can_check?: boolean
  can_self_update?: boolean
  current_version: string
  latest_version?: string | null
  update_available: boolean
  prompt_recommended?: boolean
  busy?: boolean
  last_checked_at?: string | null
  last_check_error?: string | null
  last_prompted_at?: string | null
  last_prompted_version?: string | null
  last_deferred_at?: string | null
  last_skipped_version?: string | null
  last_update_started_at?: string | null
  last_update_finished_at?: string | null
  last_update_result?: SystemUpdateResult | null
  target_version?: string | null
  manual_update_command?: string | null
  reason?: string | null
}

export interface ConfigFileEntry {
  name: string
  path: string
  required: boolean
  exists?: boolean
}

export interface RecentArtifact {
  kind: string
  path: string
  payload?: {
    artifact_id?: string
    run_id?: string
    summary?: string
    reason?: string
    status?: string
    updated_at?: string
    verdict?: string
    action?: string
    paths?: Record<string, string>
    guidance_vm?: GuidanceVm
  }
}

export interface RecentRun {
  run_id?: string
  skill_id?: string
  summary?: string
  status?: string
  created_at?: string
  updated_at?: string
  model?: string
  output_path?: string
}

export interface SessionPayload {
  ok: boolean
  quest_id: string
  snapshot: QuestSummary & Record<string, unknown>
  acp_session: {
    session_id: string
    slash_commands?: Array<{ name: string; description: string }>
    meta?: {
      quest_root?: string
      current_workspace_root?: string
      current_workspace_branch?: string
      research_head_branch?: string
      latest_metric?: { key?: string; value?: string | number }
      pending_decisions?: string[]
      runtime_status?: string
      stop_reason?: string | null
      pending_user_message_count?: number
      default_reply_interaction_id?: string | null
      waiting_interaction_id?: string | null
      latest_thread_interaction_id?: string | null
      last_artifact_interact_at?: string | null
      last_delivered_batch_id?: string | null
    }
  }
}

export interface QuestDocument {
  document_id: string
  title: string
  kind: string
  writable: boolean
  path?: string
  source_scope?: string
}

export interface OpenDocumentPayload {
  document_id: string
  quest_id?: string
  title: string
  path?: string
  content: string
  revision?: string
  writable: boolean
  kind: string
  scope?: string
  encoding?: string | null
  source_scope?: string
  updated_at?: string
  mime_type?: string
  size_bytes?: number
  asset_url?: string
  meta?: {
    tags?: string[]
    source_kind?: string
    renderer_hint?: string
    git_revision?: string
    git_path?: string
    help_markdown?: string
    system_testable?: boolean
    structured_config?: Record<string, unknown>
    highlight_line?: number
    highlight_query?: string
  }
}

export interface QuestSearchResultItem {
  id: string
  document_id: string
  title: string
  path: string
  scope: string
  writable: boolean
  line_number: number
  line_text: string
  snippet: string
  match_spans: Array<{ start: number; end: number }>
  open_kind: string
  mime_type?: string
}

export interface QuestSearchPayload {
  quest_id: string
  query: string
  items: QuestSearchResultItem[]
  limit: number
  truncated: boolean
  files_scanned: number
}

export interface QuestDocumentAssetUploadPayload {
  ok: boolean
  quest_id: string
  document_id: string
  asset_document_id: string
  asset_path: string
  relative_path: string
  asset_url: string
  mime_type?: string
  kind?: string
  saved_at?: string
  message?: string
}

export interface ConfigValidationPayload {
  ok: boolean
  name?: string
  warnings: string[]
  errors: string[]
}

export interface ConfigTestItem {
  name: string
  ok: boolean
  warnings: string[]
  errors: string[]
  details?: Record<string, unknown>
}

export interface ConfigTestPayload {
  ok: boolean
  name: string
  summary: string
  warnings: string[]
  errors: string[]
  items: ConfigTestItem[]
}

export interface MemoryCard {
  id?: string
  document_id?: string
  title?: string
  excerpt?: string
  type?: string
  path?: string
  updated_at?: string
  writable?: boolean
}

export interface GraphPayload {
  lines?: string[]
  branch?: string
  head?: string
  svg_path?: string
  png_path?: string
  json_path?: string
}

export interface GitBranchArtifactSummary {
  artifact_id?: string
  kind?: string
  summary?: string
  reason?: string
  updated_at?: string
  status?: string
}

export interface MetricComparisonItem {
  metric_id: string
  label?: string
  direction?: string
  unit?: string | null
  decimals?: number | null
  chart_group?: string | null
  run_value?: string | number | null
  baseline_value?: string | number | null
  delta?: number | null
  relative_delta?: number | null
  better?: boolean | null
}

export interface MetricContractPayload {
  contract_id?: string
  primary_metric_id?: string | null
  metrics?: Array<{
    metric_id: string
    label?: string
    direction?: string
    unit?: string | null
    decimals?: number | null
    chart_group?: string | null
  }>
}

export interface EvaluationSummaryPayload {
  takeaway?: string | null
  claim_update?: string | null
  baseline_relation?: string | null
  comparability?: string | null
  failure_mode?: string | null
  next_action?: string | null
}

export interface MainExperimentResultPayload {
  run_id?: string
  run_kind?: string
  status?: string
  summary?: string
  verdict?: string
  updated_at?: string
  paths?: Record<string, string>
  details?: Record<string, unknown>
  metrics_summary?: Record<string, unknown>
  metric_rows?: Array<Record<string, unknown>>
  metric_contract?: MetricContractPayload
  baseline_ref?: {
    baseline_id?: string | null
    variant_id?: string | null
  }
  baseline_comparisons?: {
    primary_metric_id?: string | null
    items?: MetricComparisonItem[]
    summary?: Record<string, unknown>
  }
  progress_eval?: {
    primary_metric_id?: string | null
    run_value?: number | null
    baseline_value?: number | null
    delta_vs_baseline?: number | null
    previous_best_value?: number | null
    delta_vs_previous_best?: number | null
    beats_baseline?: boolean | null
    improved_over_previous_best?: boolean | null
    breakthrough?: boolean
    breakthrough_level?: string | null
    reason?: string | null
  }
  evaluation_summary?: EvaluationSummaryPayload | null
  files_changed?: string[]
  evidence_paths?: string[]
}

export interface GitBranchNode {
  ref: string
  label: string
  branch_kind: 'quest' | 'idea' | 'implementation' | 'analysis' | string
  tier: 'major' | 'minor' | string
  mode: 'ideas' | 'analysis' | string
  parent_ref?: string | null
  compare_base?: string | null
  current?: boolean
  active_workspace?: boolean
  research_head?: boolean
  head?: string
  updated_at?: string
  subject?: string
  commit_count?: number
  ahead?: number
  behind?: number
  run_id?: string
  run_kind?: string
  idea_id?: string
  parent_branch_recorded?: string
  worktree_root?: string
  latest_metric?: {
    key?: string
    value?: string | number
    delta_vs_baseline?: string | number
    label?: string | null
    direction?: string | null
    unit?: string | null
    decimals?: number | null
  }
  latest_summary?: string
  latest_result?: MainExperimentResultPayload | null
  breakthrough?: boolean
  breakthrough_level?: string | null
  recent_artifacts?: GitBranchArtifactSummary[]
  branch_no?: string | null
  idea_title?: string | null
  idea_problem?: string | null
  next_target?: string | null
  lineage_intent?: string | null
  parent_branch?: string | null
  foundation_ref?: Record<string, unknown> | null
  foundation_reason?: string | null
  idea_md_path?: string | null
  idea_draft_path?: string | null
  latest_main_experiment?: Record<string, unknown> | null
  experiment_count?: number | null
  workflow_state?: {
    analysis_state?: 'none' | 'pending' | 'active' | 'completed' | string | null
    writing_state?: 'not_ready' | 'blocked_by_analysis' | 'ready' | 'active' | 'completed' | string | null
    analysis_campaign_id?: string | null
    total_slices?: number | null
    completed_slices?: number | null
    next_pending_slice_id?: string | null
    paper_parent_branch?: string | null
    paper_parent_run_id?: string | null
    status_reason?: string | null
  } | null
}

export interface GitBranchEdge {
  from: string
  to: string
  relation: string
  tier?: 'major' | 'minor' | string
  mode?: 'ideas' | 'analysis' | string
}

export interface GitBranchesPayload {
  quest_id: string
  default_ref: string
  current_ref?: string
  active_workspace_ref?: string | null
  research_head_ref?: string | null
  workspace_mode?: string
  head?: string
  nodes: GitBranchNode[]
  edges: GitBranchEdge[]
  projection_status?: ProjectionStatus | null
  views?: {
    ideas?: string[]
    analysis?: string[]
  }
}

export interface MetricTimelinePoint {
  seq: number
  run_id?: string
  artifact_id?: string
  created_at?: string
  branch?: string
  idea_id?: string | null
  value?: number | null
  raw_value?: string | number | null
  delta_vs_baseline?: number | null
  relative_delta_vs_baseline?: number | null
  breakthrough?: boolean
  breakthrough_level?: string | null
  result_path?: string | null
}

export interface MetricTimelineBaseline {
  metric_id: string
  label: string
  baseline_id?: string | null
  variant_id?: string | null
  selected?: boolean
  value?: number | null
  raw_value?: string | number | null
}

export interface MetricTimelineSeries {
  metric_id: string
  label: string
  direction?: string
  unit?: string | null
  decimals?: number | null
  chart_group?: string | null
  baselines: MetricTimelineBaseline[]
  points: MetricTimelinePoint[]
}

export interface MetricsTimelinePayload {
  quest_id: string
  primary_metric_id?: string | null
  total_runs?: number
  baseline_ref?: {
    baseline_id?: string | null
    variant_id?: string | null
  } | null
  series: MetricTimelineSeries[]
}

export interface BaselineCompareEntry {
  entry_key: string
  baseline_id?: string | null
  variant_id?: string | null
  label: string
  baseline_kind?: string | null
  summary?: string | null
  selected?: boolean
  updated_at?: string | null
  metric_count?: number
}

export interface BaselineCompareValue {
  entry_key: string
  label: string
  baseline_id?: string | null
  variant_id?: string | null
  selected?: boolean
  value?: number | null
  raw_value?: string | number | null
  baseline_kind?: string | null
  summary?: string | null
  updated_at?: string | null
}

export interface BaselineCompareSeries {
  metric_id: string
  label: string
  direction?: string
  unit?: string | null
  decimals?: number | null
  chart_group?: string | null
  values: BaselineCompareValue[]
}

export interface BaselineComparePayload {
  quest_id: string
  primary_metric_id?: string | null
  total_entries?: number
  baseline_ref?: {
    baseline_id?: string | null
    variant_id?: string | null
  } | null
  entries: BaselineCompareEntry[]
  series: BaselineCompareSeries[]
}

export interface GitCompareCommit {
  sha: string
  short_sha: string
  authored_at?: string
  author_name?: string
  subject: string
}

export interface GitCompareFile {
  path: string
  old_path?: string
  status: 'added' | 'deleted' | 'renamed' | 'copied' | 'modified' | string
  binary?: boolean
  added?: number
  removed?: number
}

export interface GitComparePayload {
  ok: boolean
  base: string
  head: string
  merge_base?: string | null
  ahead?: number
  behind?: number
  commit_count?: number
  file_count?: number
  commits: GitCompareCommit[]
  files: GitCompareFile[]
}

export interface GitDiffPayload {
  ok: boolean
  base?: string
  head?: string
  sha?: string
  path: string
  old_path?: string
  status?: string
  binary?: boolean
  added?: number
  removed?: number
  lines: string[]
  truncated?: boolean
}

export interface FileChangeDiffPayload extends GitDiffPayload {
  available: boolean
  source: 'patch_store' | 'run_range' | 'unavailable'
  display_path?: string
  run_id?: string
  event_id?: string
  branch?: string | null
  message?: string | null
}

export interface GitLogPayload {
  ok: boolean
  ref: string
  base?: string | null
  limit?: number
  commits: GitCompareCommit[]
}

export interface GitCommitDetailPayload {
  ok: boolean
  sha: string
  short_sha: string
  parents: string[]
  authored_at?: string
  author_name?: string
  author_email?: string
  subject: string
  body?: string
  file_count?: number
  files: GitCompareFile[]
  stats?: {
    added?: number
    removed?: number
  }
}

export interface WorkflowEntry {
  id: string
  kind: 'run' | 'tool_call' | 'tool_result' | 'thought' | 'artifact'
  run_id?: string
  skill_id?: string
  title: string
  summary?: string
  tool_name?: string
  tool_call_id?: string
  status?: string
  created_at?: string
  args?: string
  output?: string
  reason?: string
  paths?: string[]
  raw_event_type?: string
  mcp_server?: string
  mcp_tool?: string
  metadata?: Record<string, unknown>
}

export interface WorkflowPayload {
  quest_id: string
  quest_root?: string
  entries: WorkflowEntry[]
  changed_files: Array<{
    path: string
    source: string
    document_id?: string
    writable?: boolean
  }>
  projection_status?: ProjectionStatus | null
  optimization_frontier?: {
    mode?: string | null
    frontier_reason?: string | null
    active_anchor?: string | null
    best_branch?: {
      branch_name?: string | null
      branch_no?: string | null
      idea_id?: string | null
      idea_title?: string | null
      lineage_intent?: string | null
      updated_at?: string | null
    } | null
    best_run?: {
      run_id?: string | null
      summary?: string | null
      verdict?: string | null
      status?: string | null
      delta_vs_baseline?: number | null
      recommended_next_route?: string | null
      updated_at?: string | null
    } | null
    top_branches?: Array<{
      branch_name?: string | null
      branch_no?: string | null
      idea_id?: string | null
      idea_title?: string | null
      method_brief?: string | null
      selection_scores?: Record<string, unknown> | null
      mechanism_family?: string | null
      change_layer?: string | null
      source_lens?: string | null
      lineage_intent?: string | null
      has_main_result?: boolean
      updated_at?: string | null
      latest_main_experiment?: {
        run_id?: string | null
        delta_vs_baseline?: number | null
        recommended_next_route?: string | null
        breakthrough?: boolean | null
        updated_at?: string | null
      } | null
    }>
    candidate_briefs?: Array<{
      idea_id?: string | null
      title?: string | null
      problem?: string | null
      method_brief?: string | null
      selection_scores?: Record<string, unknown> | null
      mechanism_family?: string | null
      change_layer?: string | null
      source_lens?: string | null
      next_target?: string | null
      candidate_root?: string | null
      idea_md_path?: string | null
      idea_draft_path?: string | null
      updated_at?: string | null
    }>
    implementation_candidates?: Array<{
      candidate_id?: string | null
      idea_id?: string | null
      branch?: string | null
      strategy?: string | null
      status?: string | null
      summary?: string | null
      linked_run_id?: string | null
      artifact_path?: string | null
      updated_at?: string | null
    }>
    candidate_backlog?: {
      candidate_brief_count?: number
      implementation_candidate_count?: number
      active_implementation_candidate_count?: number
      failed_implementation_candidate_count?: number
    } | null
    stagnant_branches?: Array<{
      branch_name?: string | null
      branch_no?: string | null
      idea_id?: string | null
      idea_title?: string | null
    }>
    fusion_candidates?: Array<{
      branch_name?: string | null
      idea_id?: string | null
      idea_title?: string | null
      latest_main_run_id?: string | null
    }>
    recommended_next_actions?: string[]
  } | null
}

export interface QuestArtifactRecord {
  kind: string
  path: string
  workspace_root?: string
  payload?: Record<string, unknown>
}

export interface QuestArtifactListPayload {
  quest_id: string
  items: QuestArtifactRecord[]
}

export interface QuestEventRecord {
  cursor: number
  event_id: string
  type: string
  quest_id?: string
  run_id?: string | null
  source?: string | null
  skill_id?: string | null
  tool_call_id?: string | null
  tool_name?: string | null
  mcp_server?: string | null
  mcp_tool?: string | null
  status?: string | null
  args?: string | null
  output?: string | null
  raw_event_type?: string | null
  created_at?: string | null
  role?: string | null
  content?: string | null
  branch?: string | null
  head_commit?: string | null
  artifact_id?: string | null
  kind?: string | null
  summary?: string | null
  reason?: string | null
  guidance?: string | null
  paths?: Record<string, string | null> | string[] | null
  details?: Record<string, unknown> | null
  checkpoint?: Record<string, unknown> | null
  payload?: Record<string, unknown> | null
  metadata?: Record<string, unknown> | null
  [key: string]: unknown
}

export interface QuestRawEventListPayload {
  quest_id: string
  cursor: number
  has_more?: boolean
  format?: string
  session_id?: string
  events: QuestEventRecord[]
}

export interface QuestNodeTraceAction {
  action_id: string
  kind?: string
  title?: string
  summary?: string
  status?: string
  created_at?: string
  run_id?: string | null
  skill_id?: string | null
  branch_name?: string | null
  stage_key?: string | null
  worktree_rel_path?: string | null
  tool_name?: string | null
  tool_call_id?: string | null
  mcp_server?: string | null
  mcp_tool?: string | null
  args?: string | null
  output?: string | null
  reason?: string | null
  raw_event_type?: string | null
  paths?: string[]
  paths_map?: Record<string, string | null> | null
  artifact_id?: string | null
  artifact_kind?: string | null
  artifact_path?: string | null
  head_commit?: string | null
  payload_json?: Record<string, unknown> | null
  details_json?: Record<string, unknown> | null
  checkpoint_json?: Record<string, unknown> | null
  changed_files?: string[] | null
  trace_confidence?: string | null
}

export interface QuestNodeTrace {
  selection_type: string
  selection_ref: string
  title: string
  summary?: string | null
  status?: string | null
  branch_name?: string | null
  stage_key?: string | null
  stage_title?: string | null
  worktree_rel_path?: string | null
  updated_at?: string | null
  counts?: Record<string, number> | null
  run_ids?: string[] | null
  skill_ids?: string[] | null
  artifact_id?: string | null
  artifact_kind?: string | null
  head_commit?: string | null
  payload_json?: Record<string, unknown> | null
  details_json?: Record<string, unknown> | null
  paths_map?: Record<string, string | null> | null
  changed_files?: string[] | null
  actions: QuestNodeTraceAction[]
}

export interface QuestNodeTraceListPayload {
  quest_id: string
  generated_at?: string | null
  materialized_path?: string | null
  items: QuestNodeTrace[]
}

export interface QuestNodeTraceDetailPayload {
  quest_id: string
  generated_at?: string | null
  materialized_path?: string | null
  trace: QuestNodeTrace
}

export interface QuestStageField {
  id: string
  label: string
  value: unknown
  display_value?: string | null
  tone?: string | null
}

export interface QuestStageFileEntry {
  id: string
  label: string
  description?: string | null
  path: string
  absolute_path?: string | null
  document_id?: string | null
  kind: 'file' | 'directory' | string
  exists: boolean
  scope?: string | null
}

export interface QuestStageHistoryEntry {
  id: string
  artifact_id?: string | null
  artifact_kind?: string | null
  title: string
  summary?: string | null
  status?: string | null
  created_at?: string | null
  path?: string | null
  document_id?: string | null
  run_id?: string | null
  campaign_id?: string | null
  slice_id?: string | null
}

export interface QuestStageViewPayload {
  quest_id: string
  stage_key: string
  stage_label: string
  selection_ref?: string | null
  selection_type?: string | null
  branch_name?: string | null
  title: string
  note: string
  status?: string | null
  tags?: string[]
  scope_paths?: string[]
  compare_base?: string | null
  compare_head?: string | null
  snapshot_revision?: string | null
  branch_no?: string | null
  lineage_intent?: string | null
  parent_branch?: string | null
  foundation_ref?: Record<string, unknown> | null
  foundation_reason?: string | null
  foundation_label?: string | null
  idea_draft_path?: string | null
  draft_available?: boolean
  subviews?: string[]
  sections: {
    overview: QuestStageField[]
    key_facts: QuestStageField[]
    key_files: QuestStageFileEntry[]
    history: QuestStageHistoryEntry[]
  }
  details?: Record<string, unknown>
}

export interface ExplorerNode {
  id: string
  name: string
  path: string
  kind: 'file' | 'directory'
  scope: string
  folder_kind?: string
  writable?: boolean
  document_id?: string
  open_kind?: 'markdown' | 'code' | 'text' | string
  git_status?: string
  recently_changed?: boolean
  updated_at?: string
  size?: number
  children?: ExplorerNode[]
}

export interface ExplorerSection {
  id: string
  title: string
  nodes: ExplorerNode[]
}

export interface ExplorerPayload {
  quest_id: string
  quest_root?: string
  view?: {
    mode: 'live' | 'ref' | 'commit' | string
    revision?: string | null
    label?: string | null
    read_only?: boolean
  }
  sections: ExplorerSection[]
}

export interface FeedEnvelope {
  cursor: number
  has_more?: boolean
  oldest_cursor?: number | null
  newest_cursor?: number | null
  direction?: 'after' | 'before' | 'tail' | string
  quest_id?: string
  format?: string
  session_id?: string
  acp_updates: Array<{
    method: string
    params: {
      sessionId: string
      update: Record<string, unknown>
    }
  }>
}

export type FeedItem =
  | {
      id: string
      type: 'message'
      role: 'user' | 'assistant'
      source?: string
      content: string
      createdAt?: string
      stream?: boolean
      streamId?: string | null
      messageId?: string | null
      runId?: string | null
      skillId?: string | null
      reasoning?: boolean
      eventType?: string | null
      clientMessageId?: string | null
      deliveryState?: 'sending' | 'sent' | 'delivered' | 'failed' | string | null
    }
  | {
      id: string
      type: 'artifact'
      artifactId?: string
      kind: string
      status?: string
      content: string
      reason?: string
      guidance?: string
      createdAt?: string
      paths?: Record<string, string>
      artifactPath?: string
      workspaceRoot?: string
      branch?: string
      headCommit?: string
      flowType?: string
      protocolStep?: string
      ideaId?: string | null
      campaignId?: string | null
      sliceId?: string | null
      details?: Record<string, unknown>
      checkpoint?: Record<string, unknown> | null
      attachments?: Array<Record<string, unknown>>
      interactionId?: string | null
      expectsReply?: boolean
      replyMode?: string | null
      comment?: AgentComment | null
    }
  | {
      id: string
      type: 'operation'
      eventId?: string
      runId?: string | null
      label: 'tool_call' | 'tool_result'
      content: string
      toolName?: string
      toolCallId?: string
      status?: string
      subject?: string | null
      args?: string
      output?: string
      createdAt?: string
      mcpServer?: string
      mcpTool?: string
      metadata?: Record<string, unknown>
      comment?: AgentComment | null
      monitorPlanSeconds?: number[]
      monitorStepIndex?: number | null
      nextCheckAfterSeconds?: number | null
    }
  | {
      id: string
      type: 'event'
      label: string
      content: string
      createdAt?: string
    }

export type AgentComment = {
  raw?: string
  summary?: string
  whyNow?: string
  next?: string
  checkAfterSeconds?: number | null
  checkStage?: string | null
  risks?: string[]
}
