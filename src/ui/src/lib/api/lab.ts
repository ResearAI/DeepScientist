import { client as questClient } from '@/lib/api'
import {
  getDemoLabLayout,
  getDemoLabQuestGraph,
  listDemoLabAgents,
  listDemoLabMemory,
  listDemoLabPapers,
  listDemoLabQuestEvents,
  saveDemoLabLayout,
} from '@/demo/adapter'
import { isDemoProjectId } from '@/demo/projects'
import { shouldUseQuestProject } from '@/lib/runtime/quest-runtime'
import type {
  GuidanceVm,
  GitBranchNode,
  GitBranchesPayload,
  GitComparePayload,
  MainExperimentResultPayload,
  MemoryCard,
  OpenDocumentPayload,
  ProjectionStatus,
  QuestArtifactListPayload,
  QuestArtifactRecord,
  QuestEventRecord,
  QuestNodeTrace,
  QuestNodeTraceAction,
  QuestNodeTraceDetailPayload,
  QuestNodeTraceListPayload,
  QuestRawEventListPayload,
  QuestSummary,
  WorkflowEntry,
  WorkflowPayload,
} from '@/types'

import { apiClient } from './client'

const LAB_BASE = (projectId: string) => `/api/v1/projects/${projectId}/lab`
const LOCAL_QUEST_SESSION_TTL_MS = 3000
const LOCAL_QUEST_BRANCHES_TTL_MS = 1200
const LOCAL_QUEST_LAYOUT_TTL_MS = 5000

type LocalQuestRequestCacheEntry<T> = {
  expiresAt: number
  promise: Promise<T>
}

const localQuestSummaryCache = new Map<string, LocalQuestRequestCacheEntry<QuestSummary>>()
const localQuestBranchesCache = new Map<string, LocalQuestRequestCacheEntry<GitBranchesPayload | null>>()
const localQuestLayoutCache = new Map<
  string,
  LocalQuestRequestCacheEntry<{ layout_json?: Record<string, unknown> | null; updated_at?: string | null } | null>
>()

type LabRequestOptions = {
  silent?: boolean
}

function buildLabRequestConfig(options?: LabRequestOptions) {
  if (!options?.silent) return undefined
  return {
    headers: {
      'x-skip-error-toast': '1',
    },
  }
}

function isLocalLabFallbackError(error: unknown) {
  if (!error || typeof error !== 'object') return false
  const status = (error as { response?: { status?: number } }).response?.status
  return status === 401 || status === 403 || status === 404 || status === 405 || status === 501 || status === 502 || status === 503
}

function loadWithShortCache<T>(
  cache: Map<string, LocalQuestRequestCacheEntry<T>>,
  key: string,
  ttlMs: number,
  loader: () => Promise<T>
): Promise<T> {
  const now = Date.now()
  const cached = cache.get(key)
  if (cached && cached.expiresAt > now) {
    return cached.promise
  }
  const promise = loader().catch((error) => {
    if (cache.get(key)?.promise === promise) {
      cache.delete(key)
    }
    throw error
  })
  cache.set(key, {
    expiresAt: now + ttlMs,
    promise,
  })
  return promise
}

async function shouldUseLocalQuestLab(projectId: string): Promise<boolean> {
  return shouldUseQuestProject(projectId)
}

export type LabListResponse<T> = {
  items: T[]
}

export type LabTemplate = {
  template_id: string
  template_key: string
  name: string
  label?: string | null
  role?: string | null
  purpose?: string | null
  description?: string | null
  prompt_scope?: string | null
  agent_engine?: string | null
  execution_target?: string | null
  logo_svg_path?: string | null
  default_skills?: string[] | null
  typical_dod?: string | null
  recommended_subagents?: string[] | null
  init_question?: string | null
  init_answer?: string | null
  mcp_servers?: string[] | null
}

export type LabPromptPool = {
  template_id: string
  template_key: string
  name_prompts: string[]
  capability_prompts: string[]
  strength_prompts: string[]
  motto_prompts: string[]
}

export type LabAgentInstance = {
  instance_id: string
  agent_id: string
  mention_label?: string | null
  display_name?: string | null
  template_id?: string | null
  created_by_agent_instance_id?: string | null
  prompt_template_md?: string | null
  status?: string | null
  stats_json?: Record<string, number> | null
  profile_md?: string | null
  profile_json?: Record<string, unknown> | null
  avatar_frame_color?: string | null
  avatar_logo?: string | null
  direct_session_id?: string | null
  active_quest_id?: string | null
  active_quest_node_id?: string | null
  active_quest_branch?: string | null
  active_quest_stage_key?: string | null
  cli_server_id?: string | null
  status_updated_at?: string | null
  created_at?: string | null
}

export type LabAgentDeleteResponse = {
  agent_instance_id: string
  deleted: boolean
}

export type LabAgentPromptResponse = {
  content: string
  updated_at?: string | null
}

export type LabQuest = {
  quest_id: string
  title: string
  summary?: string | null
  status?: string | null
  description?: string | null
  tags?: string[] | null
  baseline_root_id?: string | null
  research_contract?: Record<string, unknown> | null
  pi_agent_instance_id?: string | null
  pi_state?: string | null
  cli_server_id?: string | null
  git_head_branch?: string | null
  last_event_at?: string | null
  pending_question_count?: number | null
  github_push_default_enabled?: boolean
  github_push?: Record<string, unknown> | null
  runtime?: QuestRuntimeVM | null
  governance?: QuestGovernanceStateVM | null
  summary_vm?: QuestSummaryVM | null
  created_at?: string | null
}

export type LabStartResearchGithubPushPayload = {
  enabled: boolean
  repo_owner?: string | null
  repo_name?: string | null
  create_if_missing?: boolean
  private_repo?: boolean
}

export type LabStartResearchResponse = {
  quest: LabQuest
  pi_agent: LabAgentInstance
  direct_session_id: string
  kickoff_queued: boolean
  kickoff_started?: boolean
  kickoff_dispatch_mode?: string | null
  quest_created: boolean
  pi_created: boolean
  github_push?: Record<string, unknown> | null
  warnings: string[]
}

export type LabQuestNode = {
  node_id: string
  quest_id: string
  node_key: string
  title?: string | null
  status?: string | null
  position?: number | null
  report_md?: string | null
  report_updated_at?: string | null
}

export type LabMetricObjective = {
  key: string
  label?: string | null
  direction?: 'higher' | 'lower' | null
  importance?: number | null
  unit?: string | null
  target?: number | null
}

export type LabBranchWorkflowState = {
  analysis_state?: 'none' | 'pending' | 'active' | 'completed' | string | null
  writing_state?: 'not_ready' | 'blocked_by_analysis' | 'ready' | 'active' | 'completed' | string | null
  analysis_campaign_id?: string | null
  total_slices?: number | null
  completed_slices?: number | null
  next_pending_slice_id?: string | null
  paper_parent_branch?: string | null
  paper_parent_run_id?: string | null
  status_reason?: string | null
}

export type LabCanvasPreferences = {
  curveMetric?: string | null
  curveMode?: 'sota' | 'full' | null
  nodeDisplayMode?: 'summary' | 'metric' | null
  showAnalysis?: boolean | null
  pathFilterMode?: 'all' | 'current' | 'selected' | null
}

export type LabMetricCurvePoint = {
  seq?: number | null
  ts?: string | null
  value?: number | null
  run_id?: string | null
  event_id?: string | null
  is_sota?: boolean
}

export type LabMetricCurve = {
  full?: LabMetricCurvePoint[] | null
  sota?: LabMetricCurvePoint[] | null
  direction?: 'higher' | 'lower' | null
  label?: string | null
  importance?: number | null
}

export type LabQuestGraphNode = {
  node_id: string
  branch_name: string
  parent_branch?: string | null
  branch_no?: string | null
  idea_title?: string | null
  idea_problem?: string | null
  next_target?: string | null
  foundation_ref?: Record<string, unknown> | null
  foundation_reason?: string | null
  foundation_label?: string | null
  latest_main_experiment?: Record<string, unknown> | null
  experiment_count?: number | null
  branch_class?: 'main' | 'idea' | 'analysis' | 'paper' | null
  node_kind?: 'branch' | 'baseline_root' | 'placeholder' | null
  placeholder?: boolean | null
  worktree_rel_path?: string | null
  latest_commit?: string | null
  latest_result?: MainExperimentResultPayload | null
  status?: string | null
  idea_id?: string | null
  idea_json?: Record<string, unknown> | null
  metrics_json?: Record<string, unknown> | null
  verdict?: string | null
  claim_verdict?: 'support' | 'refute' | 'inconclusive' | null
  go_decision?: 'go' | 'no-go' | null
  created_at?: string | null
  stage_key?: string | null
  stage_title?: string | null
  event_ids?: string[] | null
  event_count?: number | null
  baseline_state?: string | null
  push_state?: string | null
  writer_state?: string | null
  runtime_state?: string | null
  protected_state?: string | null
  divergence_state?: string | null
  reconcile_state?: string | null
  proof_state?: string | null
  submission_state?: string | null
  retire_state?: string | null
  claim_evidence_state?: string | null
  commit_trust?: string | null
  target_label?: string | null
  scope_paths?: string[] | null
  compare_base?: string | null
  compare_head?: string | null
  workflow_state?: LabBranchWorkflowState | null
  node_summary?: {
    last_event_type?: string | null
    last_reply?: string | null
    last_error?: string | null
    metrics_delta?: Record<string, unknown> | null
    latest_metrics?: Record<string, unknown> | null
    trend_preview?: Array<{ ts?: string | null; value?: number | null }> | null
    metric_curves?: Record<string, LabMetricCurve> | null
    claim_verdict?: 'support' | 'refute' | 'inconclusive' | null
    go_decision?: 'go' | 'no-go' | null
  } | null
}

export type BranchWorkbenchVM = {
  branchName: string
  branchClass: 'main' | 'idea' | 'analysis' | 'paper' | string
  parentBranch?: string | null
  worktreeRelPath?: string | null
  isHead?: boolean
  stage?: string | null
  nowDoing?: string | null
  decisionReason?: string | null
  evidenceStatus?: string | null
  baselineState?: string | null
  pushState?: string | null
  writerState?: string | null
  runtimeState?: string | null
  protectedState?: string | null
  divergenceState?: string | null
  reconcileState?: string | null
  proofState?: string | null
  submissionState?: string | null
  retireState?: string | null
  claimEvidenceState?: string | null
  commitTrust?: string | null
  latestMetrics?: Record<string, unknown> | null
  metricDelta?: Record<string, unknown> | null
  trendPreview?: Array<Record<string, unknown>> | null
  memorySummary?: Record<string, unknown> | null
}

export type QuestRuntimeVM = {
  runningAgents: number
  runningPiAgents: number
  runningWorkerAgents?: number
  lastHeartbeatAt?: string | null
  piState?: string | null
  parallelLimit?: number
  activeSlots?: number
  availableSlots?: number
  blockedReasons?: string[] | null
  cliStatus?: string | null
  cliLastSeenAt?: string | null
}

export type LabQuestRuntimeScheduler = {
  parallel_limit: number
  active_slots: number
  available_slots: number
  blocked_reasons: string[]
}

export type LabQuestRuntimeRun = {
  run_id: string
  session_id?: string | null
  agent_id?: string | null
  agent_instance_id?: string | null
  template_key?: string | null
  branch_name: string
  route_id?: string | null
  stage_key?: string | null
  status: string
  pi_launched?: boolean
  resource_hint?: string | null
  worktree_rel_path?: string | null
  role?: string | null
  started_at?: string | null
  last_heartbeat_at?: string | null
}

export type LabQuestRuntimeRoute = {
  route_id: string
  branch_name: string
  worktree_rel_path?: string | null
  status: string
  parallel_group?: string | null
  active_run_count: number
  stage_keys: string[]
  template_keys: string[]
  agent_instance_ids: string[]
  session_ids: string[]
  last_heartbeat_at?: string | null
  blocked_reasons?: string[] | null
}

export type LabQuestRuntimeCommand = {
  command_id: string
  run_id?: string | null
  session_id?: string | null
  agent_instance_id?: string | null
  branch_name?: string | null
  route_id?: string | null
  tool_name: string
  workdir?: string | null
  summary: string
  status: string
  timestamp?: string | null
}

export type QuestGovernanceStateVM = {
  formalBaselineState?: string | null
  autoPushState?: string | null
  lastPushStatus?: string | null
  lastPushAt?: string | null
  lastPushCommit?: string | null
  writerConflict?: boolean
  commitTrust?: string | null
}

export type QuestSummaryVM = {
  questAgeSeconds: number
  activeSpanSeconds: number
  branchCount: number
  ideaCount: number
  experimentCount: number
  writeCount: number
  completedCount: number
  progressingCount: number
  staleCount: number
  pushFailedCount: number
  writerConflictCount: number
}

export type QuestTopologyVM = {
  headBranch?: string | null
  branchCount: number
  edgeCount: number
}

export type QuestGovernanceVM = {
  questId: string
  title: string
  topology: QuestTopologyVM
  runtime: QuestRuntimeVM
  governance: QuestGovernanceStateVM
  summary: QuestSummaryVM
  branches: BranchWorkbenchVM[]
  continuityVm?: Record<string, unknown> | null
}

export type LabProjectGovernanceVM = {
  projectId: string
  questCount: number
  pendingDecisionCount: number
  runningBranchCount: number
  pushFailedCount: number
  writerConflictCount: number
}

export type LabGraphVM = {
  project: LabProjectGovernanceVM
  quests: QuestGovernanceVM[]
}

export type LabQuestSelectionContext = {
  selection_type: string
  selection_ref: string
  quest_id: string
  branch_name?: string | null
  branch_no?: string | null
  parent_branch?: string | null
  foundation_ref?: Record<string, unknown> | null
  foundation_reason?: string | null
  foundation_label?: string | null
  idea_title?: string | null
  stage_key?: string | null
  edge_id?: string | null
  agent_instance_id?: string | null
  worktree_rel_path?: string | null
  trace_node_id?: string | null
  compare_base?: string | null
  compare_head?: string | null
  scope_paths?: string[] | null
  node_kind?: string | null
  baseline_gate?: string | null
}

export type LabQuestNodeTraceAction = QuestNodeTraceAction
export type LabQuestNodeTrace = QuestNodeTrace
export type LabQuestNodeTraceListResponse = QuestNodeTraceListPayload
export type LabQuestNodeTraceResponse = QuestNodeTraceDetailPayload

export type LabQuestGraphAction = {
  proposal_id: string
  action_type: string
  status:
    | 'submitted'
    | 'acknowledged'
    | 'accepted'
    | 'rejected'
    | 'executed'
    | 'cancelled'
    | 'stale'
    | string
  quest_id: string
  selection_ref: string
  branch_name?: string | null
  target_agent_instance_ids?: string[] | null
  payload: Record<string, unknown>
  selection_context?: LabQuestSelectionContext | null
  user_prompt?: string | null
  generated_prompt?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type LabQuestGraphEdge = {
  edge_id?: string | null
  source: string
  target: string
  edge_type?: string | null
}

export type LabQuestGraphResponse = {
  view: 'branch' | 'event' | 'stage'
  nodes: LabQuestGraphNode[]
  edges: LabQuestGraphEdge[]
  head_branch?: string | null
  projection_status?: ProjectionStatus | null
  layout_json?: Record<string, unknown> | null
  metric_catalog?: LabMetricObjective[] | null
  governance_vm?: QuestGovernanceVM | null
  overlay_actions?: LabQuestGraphAction[] | null
}

export type LabQuestDiffFile = {
  path: string
  status?: string | null
  additions?: string | null
  deletions?: string | null
}

export type LabQuestDiffResponse = {
  files: LabQuestDiffFile[]
  next_cursor?: number | null
  has_more?: boolean
}

export type LabQuestDiffHunk = {
  header: string
  lines: string[]
}

export type LabQuestDiffFileResponse = {
  path: string
  hunks: LabQuestDiffHunk[]
  next_hunk_cursor?: number | null
  has_more?: boolean
  truncated?: boolean | null
  base_content?: string | null
  branch_content?: string | null
  content_truncated?: boolean | null
}

export type LabQuestGitFileResponse = {
  path: string
  content?: string | null
  size?: number
  truncated?: boolean
  ref?: string | null
}

export type LabQuestGitCommitItem = {
  commit_hash: string
  short_hash?: string | null
  parents?: string[]
  title?: string | null
  author?: string | null
  committed_at?: string | null
}

export type LabQuestGitCommitListResponse = {
  items: LabQuestGitCommitItem[]
  next_cursor?: number | null
  has_more?: boolean
}

export type LabQuestGitMergeRequest = {
  source_branch: string
  target_branch?: string
  message?: string | null
  ff_only?: boolean
}

export type LabQuestGitMergeResponse = {
  source_branch: string
  target_branch: string
  previous_head: string
  merge_commit: string
  fast_forward?: boolean
  head_branch?: string | null
}

export type LabQuestGitRevertRequest = {
  commit_hash: string
  branch?: string
  message?: string | null
}

export type LabQuestGitRevertResponse = {
  branch: string
  reverted_commit: string
  previous_head: string
  revert_commit: string
  head_branch?: string | null
  action_id?: string | null
  action_status?: string | null
  push_status?: string | null
  incident_ids?: string[] | null
  reconciliation_ids?: string[] | null
}

export type LabQuestGitBundleExportRequest = {
  branch_name?: string | null
  source_ref?: string | null
}

export type LabQuestGitBundleExportResponse = {
  action_id?: string | null
  action_status?: string | null
  export?: LabQuestGitExport | null
  result: Record<string, unknown>
}

export type LabQuestGitBundleRestoreRequest = {
  export_id: string
}

export type LabQuestGitBundleRestoreResponse = {
  action_id?: string | null
  action_status?: string | null
  export?: LabQuestGitExport | null
  result: Record<string, unknown>
}

export type LabQuestGitReconcileRequest = {
  branch_name?: string | null
  reason?: string | null
  related_incident_id?: string | null
}

export type LabQuestGitReconcileResponse = {
  action_id?: string | null
  action_status?: string | null
  reconciliation?: LabQuestGitReconciliation | null
  result: Record<string, unknown>
}

export type LabQuestGitIncident = {
  incident_id: string
  project_id: string
  quest_id: string
  related_action_id?: string | null
  source_cli_server_id?: string | null
  incident_type: string
  severity: string
  status: string
  branch_name?: string | null
  title?: string | null
  message?: string | null
  details?: Record<string, unknown> | null
  acknowledged_at?: string | null
  resolved_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type LabQuestGitIncidentListResponse = {
  items: LabQuestGitIncident[]
}

export type LabQuestWorktreeLease = {
  lease_id: string
  project_id: string
  quest_id: string
  source_cli_server_id?: string | null
  branch_name: string
  worktree_rel_path: string
  agent_instance_id: string
  template_key?: string | null
  stage_key?: string | null
  status: string
  resource_policy?: string | null
  resource_hint?: string | null
  gpu_allocation?: Record<string, unknown> | null
  metadata?: Record<string, unknown> | null
  last_heartbeat_at?: string | null
  expires_at?: string | null
  released_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type LabQuestWorktreeLeaseListResponse = {
  items: LabQuestWorktreeLease[]
}

export type LabQuestGitExport = {
  export_id: string
  project_id: string
  quest_id: string
  related_action_id?: string | null
  source_cli_server_id?: string | null
  restored_from_export_id?: string | null
  export_type: string
  status: string
  branch_name?: string | null
  source_ref?: string | null
  archive_path?: string | null
  checksum_sha256?: string | null
  manifest?: Record<string, unknown> | null
  result?: Record<string, unknown> | null
  completed_at?: string | null
  restored_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type LabQuestGitExportListResponse = {
  items: LabQuestGitExport[]
}

export type LabQuestGitReconciliation = {
  reconciliation_id: string
  project_id: string
  quest_id: string
  related_action_id?: string | null
  related_incident_id?: string | null
  source_cli_server_id?: string | null
  branch_name?: string | null
  status: string
  reason?: string | null
  local_state?: Record<string, unknown> | null
  db_state?: Record<string, unknown> | null
  remote_state?: Record<string, unknown> | null
  result?: Record<string, unknown> | null
  acknowledged_at?: string | null
  resolved_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type LabQuestGitReconciliationListResponse = {
  items: LabQuestGitReconciliation[]
}

export type LabQuestEventItem = {
  event_id: string
  event_type: string
  branch_name?: string | null
  stage_key?: string | null
  commit_hash?: string | null
  payload_summary?: string | null
  reply_to_pi?: string | null
  payload_hash?: string | null
  payload_path?: string | null
  payload_truncated?: boolean | null
  validation_status?: string | null
  validation_errors?: unknown
  created_at?: string | null
  payload_json?: Record<string, unknown> | null
}

export type LabQuestEventListResponse = {
  items: LabQuestEventItem[]
  next_cursor?: string | null
  has_more?: boolean
}

export type LabQuestSearchItem = {
  item_type: 'event' | 'branch'
  event?: LabQuestEventItem | null
  branch?: LabQuestGraphNode | null
}

export type LabQuestSearchResponse = {
  items: LabQuestSearchItem[]
  next_cursor?: string | null
  has_more?: boolean
  total_estimate?: number | null
}

export type LabQuestSnapshotResponse = {
  snapshot_md: string
  source?: string | null
}

export type LabQuestSyncStatus = {
  quest_id: string
  events_total: number
  last_event_id?: string | null
  last_event_commit?: string | null
  cli_server_id?: string | null
  pi_state?: string | null
  runtime?: Record<string, unknown> | null
}

export type LabMemorySyncStatus = {
  pending_count: number
  failed_count: number
  last_error?: string | null
  last_synced_at?: string | null
  updated_at?: string | null
  cli_server_id?: string | null
  cli_status?: string | null
  cli_last_seen_at?: string | null
}

export type LabPiControlRequest = {
  action: 'pause' | 'resume' | 'stop'
  reason?: string | null
  force_kill?: boolean | null
}

export type LabPiControlResponse = {
  success: boolean
  action: string
  pi_state?: string | null
  event_id?: string | null
  commit_hash?: string | null
  state_unchanged?: boolean | null
  force_kill?: boolean | null
  stopped_session_ids?: string[] | null
  stopped_sessions_count?: number | null
  error?: string | null
}

export type LabQuestEventPayloadResponse = {
  event_id: string
  payload_json?: Record<string, unknown> | null
  payload_hash?: string | null
  payload_path?: string | null
  truncated?: boolean | null
  source?: string | null
  available?: boolean | null
}

export type LabBaselineResult = {
  baseline_run_id?: string | null
  run_id: string
  status?: string | null
  metrics_json?: Record<string, unknown> | null
  summary_path?: string | null
  run_manifest_path?: string | null
  dataset_refs?: unknown
  external_refs?: unknown
  baseline_commit?: string | null
  source_cli_server_id?: string | null
  updated_at?: string | null
  created_at?: string | null
}

export type LabBaselineResultsResponse = {
  baseline_root_id: string
  items: LabBaselineResult[]
  next_cursor?: string | null
  metric_objectives?: LabMetricObjective[] | null
}

export type LabQuestLayoutResponse = {
  layout_json?: Record<string, unknown> | null
  updated_at?: string | null
}

export type LabQuestArtifactContent = {
  path: string
  content?: string | null
  encoding?: string | null
  size?: number | null
  content_hash?: string | null
  content_type?: string | null
  source?: string | null
  available?: boolean
}

export type LabQuestDeleteResponse = {
  quest_id: string
  deleted: boolean
}

export type LabQuestGithubPushStatus = {
  configured: boolean
  prerequisites: Record<string, boolean>
  disabled_reason?: string | null
  binding?: Record<string, unknown> | null
}

export type LabGithubPushDefaultStatus = {
  auto_push_default_enabled: boolean
  prerequisites: Record<string, boolean>
  disabled_reason?: string | null
}

export type LabQuestGithubPushCredential = {
  success: boolean
  token?: string | null
  expires_at?: string | null
  repo_full_name?: string | null
  repo_owner?: string | null
  repo_name?: string | null
  repo_html_url?: string | null
  default_branch?: string | null
  auto_push_effective_enabled?: boolean
  reason?: string | null
}

export type LabMoment = {
  moment_id: string
  project_id: string
  agent_instance_id?: string | null
  session_id?: string | null
  quest_id?: string | null
  quest_node_id?: string | null
  status_json?: Record<string, unknown> | null
  media_json?: Record<string, unknown> | null
  importance?: string | null
  like_count?: number | null
  comment_count?: number | null
  created_at?: string | null
  source_ts?: string | null
  content?: string | null
}

export type LabMomentComment = {
  comment_id: string
  moment_id: string
  user_id: string
  content: string
  created_at?: string | null
}

export type LabMomentsResponse = {
  items: LabMoment[]
  next_cursor?: string | null
}

export type LabLikeResponse = {
  like_count: number
}

export type LabMomentCommentResponse = {
  comment: LabMomentComment
}

export type LabOverview = {
  agents?: Record<string, unknown> | null
  quests?: Record<string, unknown> | null
  assets?: Record<string, unknown> | null
  achievements?: Record<string, unknown> | null
  recent_activity?: Array<Record<string, unknown>> | null
  github_push?: Record<string, unknown> | null
  graph_vm?: LabGraphVM | null
}

export type LabQuestTimelineEntry = {
  event_id: string
  event_type: string
  branch_name?: string | null
  created_at?: string | null
  payload_summary?: string | null
  source?: string | null
  source_ref?: string | null
  origin_event_id?: string | null
  origin_commit_hash?: string | null
  authority_level?: string | null
}

export type LabQuestTimelineResponse = {
  items: LabQuestTimelineEntry[]
}

export type LabQuestCompareSeries = {
  label: string
  points: Array<Record<string, unknown>>
}

export type LabQuestCompareResponse = {
  baseline_branch?: string | null
  head_branch?: string | null
  selected_branch?: string | null
  metric_table: Record<string, unknown>
  series: LabQuestCompareSeries[]
  key_findings: string[]
  git_diff: Array<Record<string, unknown>>
  artifact_diff: Array<Record<string, unknown>>
}

export type LabQuestAuditArtifact = {
  path: string
  available: boolean
  content_type?: string | null
  content_hash?: string | null
  size?: number | null
  preview?: string | null
  truncated?: boolean
}

export type LabQuestRunAuditClaim = {
  claim_id?: string | null
  statement?: string | null
  section?: string | null
  figure?: string | null
  table?: string | null
  verdict?: string | null
}

export type LabQuestRunAuditResponse = {
  quest_id: string
  run_id: string
  branch_name?: string | null
  event_id?: string | null
  stage_key?: string | null
  status?: string | null
  created_at?: string | null
  audit_level?: string | null
  audit_score: number
  validation_status?: string | null
  validation_errors?: unknown
  missing_artifacts: string[]
  run: Record<string, unknown>
  idea: Record<string, unknown>
  decision: Record<string, unknown>
  code: Record<string, unknown>
  command: Record<string, unknown>
  logs: Record<string, unknown>
  result: Record<string, unknown>
  claims: LabQuestRunAuditClaim[]
  related_memory: Array<Record<string, unknown>>
}

export type LabQuestBranchAuditResponse = {
  quest_id: string
  branch_name: string
  head_branch?: string | null
  parent_branch?: string | null
  latest_commit?: string | null
  stage?: string | null
  audit_level?: string | null
  branch_summary: Record<string, unknown>
  idea: Record<string, unknown>
  diff: Record<string, unknown>
  experiments: Array<Record<string, unknown>>
  decisions: Array<Record<string, unknown>>
  related_memory: Array<Record<string, unknown>>
  claim_map_path?: string | null
  bundle_manifest_path?: string | null
  compare_context: Record<string, unknown>
}

export type LabQuestSummaryResponse = {
  quest: QuestGovernanceVM
}

export type LabQuestRuntimeResponse = {
  quest_id: string
  runtime: QuestRuntimeVM
  scheduler: LabQuestRuntimeScheduler
  active_runs: LabQuestRuntimeRun[]
  routes: LabQuestRuntimeRoute[]
  recent_commands: LabQuestRuntimeCommand[]
  worktree_leases: LabQuestWorktreeLease[]
}

export type LabQuestGraphActionListResponse = {
  items: LabQuestGraphAction[]
}

export type LabQuestGraphActionResponse = {
  action: LabQuestGraphAction
}

export type LabQuestAgentGroupMessageCreateResponse = {
  group_message_id: string
  dispatch_count: number
}

export type LabPendingQuestion = {
  tool_call_id: string
  session_id: string
  agent_instance_id?: string | null
  agent_display_name?: string | null
  agent_label?: string | null
  question_set: Record<string, unknown>
  created_at?: string | null
}

export type LabPendingQuestionListResponse = {
  items: LabPendingQuestion[]
  total: number
}

export type LabQuestionHistoryItem = {
  tool_call_id: string
  session_id: string
  agent_instance_id?: string | null
  agent_display_name?: string | null
  agent_label?: string | null
  question_set: Record<string, unknown>
  answers?: Record<string, unknown> | null
  summary?: string | null
  answered_at?: string | null
}

export type LabQuestionHistoryResponse = {
  items: LabQuestionHistoryItem[]
  next_cursor?: string | null
}

export type LabAchievementDefinition = {
  key: string
  title: string
  description?: string | null
  trigger_event?: string | null
  category?: string | null
  icon?: string | null
}

export type LabAchievement = {
  id: string
  key: string
  unlocked_at?: string | null
  unlocked_by_agent_instance_id?: string | null
  metadata_json?: Record<string, unknown> | null
}

export type LabBaseline = {
  baseline_root_id: string
  title?: string | null
  status?: string | null
  last_reproduced_at?: string | null
  archive_file_id?: string | null
}

export type LabPaperVersionSummary = {
  paper_version_id: string
  version_index?: number | null
  status?: string | null
  created_at?: string | null
  archive_file_id?: string | null
  main_tex_path?: string | null
  main_tex_file_id?: string | null
  archive_error_code?: string | null
  archive_error_detail?: string | null
}

export type LabPaper = {
  paper_root_id: string
  quest_id?: string | null
  title?: string | null
  status?: string | null
  folder_name?: string | null
  root_path?: string | null
  latest_version?: LabPaperVersionSummary | null
}

export type LabPaperDetail = LabPaper & {
  project_id?: string | null
  metadata_json?: Record<string, unknown> | null
  versions?: LabPaperVersionSummary[]
}

export type LabMemoryEntry = {
  entry_id: string
  kind: string
  title?: string | null
  summary?: string | null
  severity?: string | null
  quest_id?: string | null
  branch_name?: string | null
  stage_key?: string | null
  worktree_rel_path?: string | null
  origin_event_id?: string | null
  origin_event_type?: string | null
  origin_commit_hash?: string | null
  agent_instance_id?: string | null
  idea_id?: string | null
  run_id?: string | null
  occurred_at?: string | null
  artifact_paths?: string[] | null
  evidence_refs?: unknown[] | null
  authority_level?: string | null
  review_status?: string | null
  tags?: string[] | null
  confidence?: number | null
  content_md?: string | null
  content_hash?: string | null
  source_path?: string | null
  deleted_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type LabMemoryListResponse = {
  items: LabMemoryEntry[]
}

export type LabAssetContent = {
  path: string
  content: string
  encoding: string
  size: number
  modified_at?: string | null
  truncated?: boolean
}

const LOCAL_LAB_TEMPLATE_CATALOG: LabTemplate[] = [
  {
    template_id: 'local-principal-investigator',
    template_key: 'principal-investigator',
    name: 'Principal Investigator',
    label: 'PI',
    role: 'lead',
    purpose: 'Drive the quest, make decisions, and keep the evidence coherent.',
    description: 'Local DeepScientist PI agent for quest planning, branching, and milestone decisions.',
    prompt_scope: 'quest',
    agent_engine: 'codex',
    execution_target: 'local',
    default_skills: ['scout', 'idea', 'decision', 'experiment', 'analysis-campaign', 'write', 'finalize'],
    typical_dod: 'Produces durable artifacts, explicit decisions, and a clear next action.',
    init_question: 'What is the best next research step for this quest?',
    init_answer: 'Inspect the latest artifact, compare against the active baseline, then decide whether to branch, run, analyse, or write.',
    mcp_servers: ['memory', 'artifact'],
  },
]

function nowIso() {
  return new Date().toISOString()
}

function normalizeTimestamp(value?: string | null) {
  return value && value.trim() ? value : nowIso()
}

function normalizeLabWorkingStatus(status?: string | null) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'running' || normalized === 'active' || normalized === 'working') return 'working'
  if (normalized === 'completed' || normalized === 'done' || normalized === 'finalized') return 'done'
  if (normalized === 'failed' || normalized === 'blocked' || normalized === 'error') return 'blocked'
  if (normalized === 'waiting' || normalized === 'paused') return 'waiting'
  return 'idle'
}

const CANONICAL_STAGE_ORDER = [
  'scout',
  'baseline',
  'idea',
  'experiment',
  'analysis-campaign',
  'write',
  'finalize',
] as const

const LOCAL_QUEST_EVENT_FETCH_CHUNK = 1000
const LOCAL_QUEST_EVENT_FETCH_MAX = 8000

function resolveStageKey(anchor?: string | null) {
  const normalized = String(anchor || '').trim().toLowerCase()
  if (!normalized) return 'baseline'
  if (normalized.includes('scout') || normalized.includes('literature') || normalized.includes('research')) {
    return 'scout'
  }
  if (normalized.includes('baseline') || normalized.includes('reproduce')) return 'baseline'
  if (normalized.includes('idea')) return 'idea'
  if (normalized.includes('decision')) return 'decision'
  if (normalized.includes('analysis')) return 'analysis-campaign'
  if (normalized.includes('write') || normalized.includes('paper')) return 'write'
  if (normalized.includes('final')) return 'finalize'
  if (normalized.includes('experiment')) return 'experiment'
  return normalized
}

function resolveStageRank(stage?: string | null) {
  const normalized = resolveStageKey(stage)
  const index = CANONICAL_STAGE_ORDER.indexOf(normalized as (typeof CANONICAL_STAGE_ORDER)[number])
  return index >= 0 ? index : Number.MAX_SAFE_INTEGER
}

function isCanonicalStage(stage?: string | null) {
  const normalized = resolveStageKey(stage)
  return CANONICAL_STAGE_ORDER.includes(normalized as (typeof CANONICAL_STAGE_ORDER)[number])
}

function formatStageTitle(stage?: string | null) {
  const normalized = resolveStageKey(stage)
  if (!normalized) return 'General'
  return normalized
    .split('-')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function asRecordValue(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asArrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function asStringValue(value: unknown): string | null {
  if (typeof value === 'string') {
    const text = value.trim()
    return text || null
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  return null
}

function safeJsonParse(value: unknown): unknown | null {
  if (!value) return null
  if (typeof value !== 'string') {
    return typeof value === 'object' ? value : null
  }
  const text = value.trim()
  if (!text) return null
  if (!(text.startsWith('{') || text.startsWith('['))) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

function compactText(value: unknown, limit = 240): string | null {
  const text =
    typeof value === 'string'
      ? value.trim()
      : value && typeof value === 'object'
        ? JSON.stringify(value)
        : asStringValue(value) || ''
  if (!text) return null
  if (text.length <= limit) return text
  return `${text.slice(0, Math.max(0, limit - 1)).trimEnd()}…`
}

function stageKeyFromArtifactKind(kind?: string | null) {
  const normalized = String(kind || '').trim().toLowerCase()
  if (!normalized) return null
  if (normalized === 'baseline') return 'baseline'
  if (normalized === 'idea') return 'idea'
  if (normalized === 'decision' || normalized === 'approval') return 'decision'
  if (normalized === 'run') return 'experiment'
  if (normalized === 'report') return 'write'
  if (normalized === 'milestone') return 'finalize'
  return null
}

function resolveArtifactStageKey(payload?: Record<string, unknown> | null, fallback?: string | null) {
  if (payload) {
    const explicitFields = [
      payload.stage_key,
      payload.protocol_step,
      payload.flow_type,
      payload.run_kind,
      payload.skill_id,
      payload.current_anchor,
      payload.active_anchor,
    ]
    for (const candidate of explicitFields) {
      const stage = resolveStageKey(asStringValue(candidate))
      if (isCanonicalStage(stage)) {
        return stage
      }
    }
    const fromKind = stageKeyFromArtifactKind(asStringValue(payload.kind))
    if (fromKind) return fromKind
  }
  const fallbackStage = resolveStageKey(fallback)
  return isCanonicalStage(fallbackStage) ? fallbackStage : 'baseline'
}

function resolveDecisionActionStage(payload?: Record<string, unknown> | null, fallback?: string | null) {
  const action = String(payload?.action || '').trim().toLowerCase()
  if (!action) return resolveArtifactStageKey(null, fallback)
  if (
    action === 'attach_baseline' ||
    action === 'reuse_baseline' ||
    action === 'publish_baseline'
  ) {
    return 'baseline'
  }
  if (action === 'launch_experiment' || action === 'prepare_branch' || action === 'branch') {
    return 'experiment'
  }
  if (action === 'launch_analysis_campaign') {
    return 'analysis-campaign'
  }
  if (action === 'write') return 'write'
  if (action === 'finalize') return 'finalize'
  return resolveArtifactStageKey(null, fallback)
}

function normalizePathMap(value: unknown): Record<string, string | null> | null {
  if (Array.isArray(value)) {
    const result: Record<string, string | null> = {}
    value.forEach((entry, index) => {
      const normalized = asStringValue(entry)
      if (normalized) {
        result[String(index)] = normalized
      }
    })
    return Object.keys(result).length ? result : null
  }
  const record = asRecordValue(value)
  if (!record) return null
  const result: Record<string, string | null> = {}
  Object.entries(record).forEach(([key, raw]) => {
    result[key] = asStringValue(raw)
  })
  return Object.keys(result).length ? result : null
}

function normalizeRelativePath(path: string, workspaceRoot?: string | null) {
  const normalized = path.trim()
  if (!normalized) return null
  if (!normalized.startsWith('/')) {
    return normalized.replace(/^[.][/\\]/, '').replace(/\\/g, '/')
  }
  const root = String(workspaceRoot || '').trim()
  if (root && normalized.startsWith(root)) {
    return normalized
      .slice(root.length)
      .replace(/^[/\\]+/, '')
      .replace(/\\/g, '/')
  }
  return null
}

function collectArtifactChangedFiles(payload?: Record<string, unknown> | null) {
  if (!payload) return [] as string[]
  const workspaceRoot = asStringValue(payload.workspace_root)
  const rawLists = [
    ...asArrayValue(payload.changed_files),
    ...asArrayValue(payload.files_changed),
    ...asArrayValue(payload.evidence_paths),
    ...asArrayValue(payload.related_paths),
  ]
  const fromLists = rawLists
    .map((entry) => asStringValue(entry))
    .filter((entry): entry is string => Boolean(entry))
    .map((entry) => normalizeRelativePath(entry, workspaceRoot) || entry)
  const fromPaths = Object.values(normalizePathMap(payload.paths) || {})
    .map((entry) => (entry ? normalizeRelativePath(entry, workspaceRoot) || entry : null))
    .filter((entry): entry is string => Boolean(entry))
  return [...new Set([...fromLists, ...fromPaths])]
}

function extractArtifactIdFromUnknown(value: unknown): string | null {
  const record = asRecordValue(value)
  if (!record) return null
  const direct = asStringValue(record.artifact_id) || asStringValue(record.id)
  if (direct) return direct
  const structured = extractArtifactIdFromUnknown(record.structured_content)
  if (structured) return structured
  const payload = extractArtifactIdFromUnknown(record.payload)
  if (payload) return payload
  return null
}

function isArtifactToolEvent(event: QuestEventRecord) {
  const server = String(event.mcp_server || '').trim().toLowerCase()
  const tool = String(event.mcp_tool || event.tool_name || '').trim().toLowerCase()
  return server === 'artifact' || tool.startsWith('artifact.')
}

function isCanvasRelevantToolEvent(event: QuestEventRecord) {
  const type = String(event.type || '').trim().toLowerCase()
  if (type !== 'runner.tool_call' && type !== 'runner.tool_result') {
    return false
  }
  if (isArtifactToolEvent(event)) {
    return true
  }
  const tool = String(event.tool_name || event.mcp_tool || '').trim().toLowerCase()
  const status = String(event.status || '').trim().toLowerCase()
  if (status === 'failed' || status === 'error') {
    return true
  }
  return tool === 'web_search' || tool === 'file_change'
}

function extractArtifactIdFromRawEvent(event: QuestEventRecord): string | null {
  const direct = asStringValue(event.artifact_id)
  if (direct) return direct
  const parsedOutput = extractArtifactIdFromUnknown(safeJsonParse(event.output))
  if (parsedOutput) return parsedOutput
  const parsedArgs = extractArtifactIdFromUnknown(safeJsonParse(event.args))
  if (parsedArgs) return parsedArgs
  return null
}

function resolveRawEventStageKey(
  event: QuestEventRecord,
  artifactPayload?: Record<string, unknown> | null,
  fallback?: string | null
) {
  if (artifactPayload) {
    return resolveArtifactStageKey(artifactPayload, fallback)
  }
  const explicit = resolveStageKey(asStringValue(event.skill_id))
  if (isCanonicalStage(explicit)) return explicit
  if (event.type === 'quest.control') return 'decision'
  if (isArtifactToolEvent(event)) {
    const argsJson = asRecordValue(safeJsonParse(event.args))
    const stage = resolveArtifactStageKey(argsJson, fallback)
    if (stage) return stage
  }
  return resolveArtifactStageKey(null, fallback)
}

function resolveRawEventBranchName(
  event: QuestEventRecord,
  artifactPayload?: Record<string, unknown> | null,
  fallback?: string | null
) {
  return (
    asStringValue(event.branch) ||
    asStringValue(artifactPayload?.branch) ||
    asStringValue(asRecordValue(safeJsonParse(event.args))?.branch) ||
    asStringValue(fallback) ||
    'main'
  )
}

function resolveRawEventSummary(event: QuestEventRecord, artifactPayload?: Record<string, unknown> | null) {
  return (
    compactText(artifactPayload?.summary) ||
    compactText(artifactPayload?.reason) ||
    compactText(event.summary) ||
    compactText(event.reason) ||
    compactText(event.content) ||
    compactText(event.status ? `${event.type}: ${event.status}` : event.type)
  )
}

function buildEventPayloadEnvelope(
  event: QuestEventRecord,
  artifactPayload?: Record<string, unknown> | null
) {
  const normalizedEvent = {
    ...event,
    args_json: safeJsonParse(event.args),
    output_json: safeJsonParse(event.output),
  }
  return {
    payload: artifactPayload ?? normalizedEvent,
    event: normalizedEvent,
  }
}

function resolveBranchClass(node: GitBranchNode): 'main' | 'idea' | 'analysis' | 'paper' {
  const branchKind = String(node.branch_kind || '').toLowerCase()
  const mode = String(node.mode || '').toLowerCase()
  if (branchKind === 'analysis' || mode === 'analysis') return 'analysis'
  if (branchKind === 'idea') return 'idea'
  if (branchKind === 'paper' || branchKind === 'write') return 'paper'
  return 'main'
}

type LocalBaselineGate = 'pending' | 'confirmed' | 'waived'

function resolveBaselineGate(summary: QuestSummary): LocalBaselineGate {
  const normalized = String(summary.baseline_gate || '').trim().toLowerCase()
  if (normalized === 'confirmed') return 'confirmed'
  if (normalized === 'waived') return 'waived'
  return 'pending'
}

function resolveConfirmedBaselineRelPath(summary: QuestSummary): string | null {
  const ref = summary.confirmed_baseline_ref
  if (!ref || typeof ref !== 'object') return null
  const candidate = String(ref.baseline_root_rel_path || '').trim()
  if (candidate) return candidate
  const baselineId = String(ref.baseline_id || '').trim()
  if (!baselineId) return null
  const sourceMode = String(ref.source_mode || '').trim().toLowerCase()
  if (sourceMode === 'imported') {
    return `baselines/imported/${baselineId}`
  }
  return `baselines/local/${baselineId}`
}

function resolveBaselineNodeId(summary: QuestSummary): string {
  const baselineGate = resolveBaselineGate(summary)
  const ref = summary.confirmed_baseline_ref
  const baselineId = String(ref?.baseline_id || summary.active_baseline_id || '').trim()
  if (baselineGate === 'confirmed' && baselineId) {
    return `baseline:${baselineId}`
  }
  if (baselineGate === 'waived') {
    return `baseline:${summary.quest_id}:waived`
  }
  return `baseline:${summary.quest_id}:pending`
}

function resolveBaselineRootLabel(summary: QuestSummary): string {
  const baselineGate = resolveBaselineGate(summary)
  const ref = summary.confirmed_baseline_ref
  const baselineId = String(ref?.baseline_id || summary.active_baseline_id || '').trim()
  if (baselineGate === 'confirmed') {
    return baselineId ? `Baseline · ${baselineId}` : 'Baseline · confirmed'
  }
  if (baselineGate === 'waived') {
    return 'Baseline (waived)'
  }
  return 'Baseline (pending)'
}

function resolveBaselineRootSummary(summary: QuestSummary): string {
  const baselineGate = resolveBaselineGate(summary)
  const ref = summary.confirmed_baseline_ref
  if (baselineGate === 'confirmed') {
    const variantId = String(ref?.variant_id || summary.active_baseline_variant_id || '').trim()
    const relPath = resolveConfirmedBaselineRelPath(summary)
    if (variantId && relPath) {
      return `Confirmed variant ${variantId} at ${relPath}.`
    }
    if (relPath) {
      return `Confirmed baseline root at ${relPath}.`
    }
    return 'Baseline gate confirmed.'
  }
  if (baselineGate === 'waived') {
    return 'Baseline gate was explicitly waived. Downstream stages may proceed with caveats.'
  }
  return 'Attach/import/reproduce first, then call artifact.confirm_baseline(...) or artifact.waive_baseline(...).'
}

function resolveBaselineScopePaths(summary: QuestSummary): string[] {
  const relPath = resolveConfirmedBaselineRelPath(summary)
  if (relPath) return [relPath]
  return ['baselines/local', 'baselines/imported']
}

function resolveFormalBaselineState(summary: QuestSummary) {
  const baselineGate = resolveBaselineGate(summary)
  if (baselineGate === 'confirmed') return 'confirmed'
  if (baselineGate === 'waived') return 'waived'
  return 'pending'
}

function resolveBranchCompareBase(node: GitBranchNode): string | null {
  const parent = String(node.parent_ref || '').trim()
  if (parent) return parent
  const ref = String(node.ref || '').trim()
  if (ref && ref !== 'main') return 'main'
  return null
}

function resolveWorkflowBranchStageKey(workflowState?: LabBranchWorkflowState | null): string | null {
  if (!workflowState || typeof workflowState !== 'object') return null
  const writingState = String(workflowState.writing_state || '').trim().toLowerCase()
  if (writingState === 'completed') return 'finalize'
  if (writingState === 'active') return 'write'
  if (writingState === 'blocked_by_analysis') return 'analysis-campaign'
  const analysisState = String(workflowState.analysis_state || '').trim().toLowerCase()
  if (analysisState === 'pending' || analysisState === 'active' || analysisState === 'completed') {
    return 'analysis-campaign'
  }
  return null
}

function resolveGraphBranchStageKey(
  summary: QuestSummary,
  node: GitBranchNode | null,
  branchTrace?: LabQuestNodeTrace | null
) {
  const traced = resolveStageKey(branchTrace?.stage_key)
  if (isCanonicalStage(traced)) return traced
  const workflowStage = resolveStageKey(resolveWorkflowBranchStageKey(node?.workflow_state as LabBranchWorkflowState | null))
  if (isCanonicalStage(workflowStage)) return workflowStage
  const runKind = resolveStageKey(node?.run_kind || null)
  if (isCanonicalStage(runKind)) return runKind
  const inferredClass = node ? resolveBranchClass(node) : 'main'
  if (inferredClass === 'idea') return 'idea'
  if (inferredClass === 'analysis') return 'analysis-campaign'
  if (inferredClass === 'paper') return 'write'
  return 'baseline'
}

function resolveHighestObservedStage(
  summary: QuestSummary,
  nodes: LabQuestGraphNode[]
): (typeof CANONICAL_STAGE_ORDER)[number] {
  let best = resolveBaselineGate(summary) === 'pending' ? 'baseline' : resolveStageKey(summary.active_anchor)
  nodes.forEach((node) => {
    const stage = resolveStageKey(node.stage_key)
    if (resolveStageRank(stage) > resolveStageRank(best)) {
      best = stage
    }
  })
  return (CANONICAL_STAGE_ORDER.includes(best as (typeof CANONICAL_STAGE_ORDER)[number]) ? best : 'baseline') as
    (typeof CANONICAL_STAGE_ORDER)[number]
}

function buildLocalBranchGraphNodes(
  summary: QuestSummary,
  branches: GitBranchesPayload | null,
  branchTraceByName: Map<string, LabQuestNodeTrace>
): LabQuestGraphNode[] {
  const baselineGate = resolveBaselineGate(summary)
  const baselineRootId = resolveBaselineNodeId(summary)
  const baselineSnapshot = collectBaselineMetricsFromBranches(branches)
  const realNodes =
    branches?.nodes?.length
      ? branches.nodes.map((node) =>
          mapGitNodeToLabQuestGraphNode(summary.quest_id, summary, node, branchTraceByName.get(node.ref) || null)
        )
      : [buildFallbackGraphNode(summary, branchTraceByName.get(summary.branch || 'main') || null)]

  const baselineNode: LabQuestGraphNode = {
    node_id: baselineRootId,
    branch_name: 'baseline',
    parent_branch: null,
    branch_class: 'main',
    node_kind: 'baseline_root',
    placeholder: baselineGate === 'pending',
    worktree_rel_path: resolveConfirmedBaselineRelPath(summary),
    latest_commit: null,
    metrics_json: baselineSnapshot.metrics,
    status: baselineGate,
    stage_key: 'baseline',
    stage_title: 'Baseline',
    event_count: 0,
    baseline_state: baselineGate,
    runtime_state: baselineGate === 'pending' ? 'waiting' : 'idle',
    target_label: resolveBaselineRootLabel(summary),
    scope_paths: resolveBaselineScopePaths(summary),
    node_summary: {
      last_event_type: 'baseline_gate',
      last_reply: resolveBaselineRootSummary(summary),
      latest_metrics: baselineSnapshot.metrics,
    },
  }

  const nodes: LabQuestGraphNode[] = [baselineNode, ...realNodes]
  const workspaceMode = String(summary.workspace_mode || '').trim().toLowerCase()
  const allowOperationalNodesWithoutBaseline = workspaceMode === 'copilot'
  if (baselineGate === 'pending' && !allowOperationalNodesWithoutBaseline) {
    return [baselineNode]
  }

  const highestStage = resolveHighestObservedStage(summary, realNodes)
  const nextRank = resolveStageRank(highestStage) + 1
  const nextStage =
    nextRank >= 0 && nextRank < CANONICAL_STAGE_ORDER.length
      ? CANONICAL_STAGE_ORDER[nextRank]
      : null
  const hasPendingAnalysis = Boolean(
    summary.active_analysis_campaign_id ||
      summary.next_pending_slice_id ||
      String(summary.workspace_mode || '').trim().toLowerCase() === 'analysis'
  )
  if (!nextStage || nextStage === 'baseline') {
    return nodes
  }
  if (nextStage === 'write' && hasPendingAnalysis) {
    return nodes
  }
  const alreadyCovered = realNodes.some((node) => resolveStageRank(node.stage_key) >= resolveStageRank(nextStage))
  if (alreadyCovered) {
    return nodes
  }

  const anchorNode =
    realNodes.find((node) => node.branch_name === (summary.branch || 'main')) ||
    realNodes
      .slice()
      .sort((left, right) => resolveStageRank(right.stage_key) - resolveStageRank(left.stage_key))[0] ||
    baselineNode
  const placeholderId = `${summary.quest_id}:next:${nextStage}`
  nodes.push({
    node_id: placeholderId,
    branch_name: `${nextStage}:next`,
    parent_branch: anchorNode.node_id,
    branch_class:
      nextStage === 'idea' ? 'idea' : nextStage === 'analysis-campaign' ? 'analysis' : nextStage === 'write' ? 'paper' : 'main',
    node_kind: 'placeholder',
    placeholder: true,
    worktree_rel_path: null,
    latest_commit: null,
    status: 'pending',
    stage_key: nextStage,
    stage_title: formatStageTitle(nextStage),
    baseline_state: baselineGate,
    runtime_state: 'idle',
    target_label: formatStageTitle(nextStage),
    scope_paths: null,
    compare_base: null,
    compare_head: null,
    node_summary: {
      last_event_type: 'next_stage',
      last_reply: `Next durable stage after ${formatStageTitle(highestStage)}.`,
    },
  })
  return nodes
}

export function resolveLocalBaselineAnchorNode(
  nodes: LabQuestGraphNode[],
  summaryBranch?: string | null
): LabQuestGraphNode | null {
  const operationalNodes = nodes.filter(
    (node) =>
      node.node_kind !== 'baseline_root' &&
      node.node_kind !== 'placeholder'
  )
  if (!operationalNodes.length) return null

  const rootNode = operationalNodes.find((node) => !String(node.parent_branch || '').trim())
  if (rootNode) return rootNode

  const mainNode = operationalNodes.find((node) => node.branch_name === 'main')
  if (mainNode) return mainNode

  const activeNode = operationalNodes.find((node) => node.branch_name === (summaryBranch || 'main'))
  if (activeNode) return activeNode

  return operationalNodes[0] ?? null
}

function buildGraphMetricCatalogFromNodes(nodes: LabQuestGraphNode[]): LabMetricObjective[] {
  const catalog = new Map<string, LabMetricObjective>()

  const upsert = (entry: LabMetricObjective) => {
    if (!entry.key) return
    const current = catalog.get(entry.key)
    catalog.set(entry.key, {
      key: entry.key,
      label: entry.label || current?.label || entry.key,
      direction: entry.direction || current?.direction || null,
      importance: entry.importance ?? current?.importance ?? null,
      unit: entry.unit ?? current?.unit ?? null,
      target: entry.target ?? current?.target ?? null,
    })
  }

  nodes.forEach((node) => {
    extractLatestResultMetricCatalog(node.latest_result).forEach(upsert)
    Object.entries(node.metrics_json ?? {}).forEach(([key, value]) => {
      if (typeof value !== 'number' || !Number.isFinite(value)) return
      upsert({ key, label: key, direction: null, importance: null, unit: null, target: null })
    })
  })

  return [...catalog.values()].sort((left, right) => {
    const leftImportance = typeof left.importance === 'number' ? left.importance : -1
    const rightImportance = typeof right.importance === 'number' ? right.importance : -1
    if (leftImportance !== rightImportance) return rightImportance - leftImportance
    return left.key.localeCompare(right.key)
  })
}

function buildLocalBranchGraphEdges(
  summary: QuestSummary,
  nodes: LabQuestGraphNode[],
  branches: GitBranchesPayload | null
): LabQuestGraphEdge[] {
  const baselineRootId = resolveBaselineNodeId(summary)
  const edges: LabQuestGraphEdge[] = []
  const branchEdges = branches?.edges ?? []
  branchEdges.forEach((edge, index) => {
    edges.push({
      edge_id: `edge:${index}:${edge.from}:${edge.to}`,
      source: edge.from,
      target: edge.to,
      edge_type: edge.relation || 'branch',
    })
  })

  const firstOperationalNode = resolveLocalBaselineAnchorNode(nodes, summary.branch || 'main')
  if (firstOperationalNode) {
    edges.unshift({
      edge_id: `${baselineRootId}->${firstOperationalNode.node_id}`,
      source: baselineRootId,
      target: firstOperationalNode.node_id,
      edge_type: 'baseline',
    })
  }

  const placeholderNode = nodes.find((node) => node.node_kind === 'placeholder')
  if (placeholderNode) {
    const anchorNode =
      nodes.find((node) => node.node_id === placeholderNode.parent_branch) ||
      firstOperationalNode ||
      nodes.find((node) => node.node_id === baselineRootId)
    if (anchorNode) {
      edges.push({
        edge_id: `${anchorNode.node_id}->${placeholderNode.node_id}`,
        source: anchorNode.node_id,
        target: placeholderNode.node_id,
        edge_type: 'placeholder',
      })
    }
  }
  return edges
}

function latestMetrics(summary: QuestSummary) {
  const metric = summary.summary?.latest_metric
  if (!metric?.key) return null
  return {
    [metric.key]: metric.value ?? null,
  }
}

function normalizeGraphMetricDirection(value: unknown): 'higher' | 'lower' | null {
  const text = String(value || '').trim().toLowerCase().replace(/[- ]+/g, '_')
  if (text === 'higher' || text === 'maximize' || text === 'higher_better' || text === 'more_is_better') {
    return 'higher'
  }
  if (text === 'lower' || text === 'minimize' || text === 'lower_better' || text === 'less_is_better') {
    return 'lower'
  }
  return null
}

function extractLatestResultMetrics(result?: MainExperimentResultPayload | null) {
  if (!result) return null
  const metrics: Record<string, number> = {}
  ;(result.metric_rows ?? []).forEach((row) => {
    if (!row || typeof row !== 'object' || Array.isArray(row)) return
    const record = row as Record<string, unknown>
    const key = String(record.metric_id || record.name || record.metric || '').trim()
    const value = typeof record.numeric_value === 'number' ? record.numeric_value : record.value
    if (!key || typeof value !== 'number' || !Number.isFinite(value)) return
    metrics[key] = Number(value)
  })
  Object.entries(result.metrics_summary ?? {}).forEach(([key, value]) => {
    if (key in metrics) return
    if (typeof value === 'number' && Number.isFinite(value)) {
      metrics[key] = Number(value)
    }
  })
  return Object.keys(metrics).length ? metrics : null
}

function extractLatestResultMetricDeltas(result?: MainExperimentResultPayload | null) {
  if (!result) return null
  const deltas: Record<string, number> = {}
  ;(result.baseline_comparisons?.items ?? []).forEach((item) => {
    if (!item?.metric_id || typeof item.delta !== 'number' || !Number.isFinite(item.delta)) return
    deltas[item.metric_id] = Number(item.delta)
  })
  ;(result.metric_rows ?? []).forEach((row) => {
    if (!row || typeof row !== 'object' || Array.isArray(row)) return
    const record = row as Record<string, unknown>
    const key = String(record.metric_id || record.name || record.metric || '').trim()
    const delta = record.delta
    if (!key || key in deltas || typeof delta !== 'number' || !Number.isFinite(delta)) return
    deltas[key] = Number(delta)
  })
  return Object.keys(deltas).length ? deltas : null
}

function extractLatestResultMetricCatalog(result?: MainExperimentResultPayload | null) {
  if (!result) return []
  const catalog = new Map<string, LabMetricObjective>()
  ;(result.metric_contract?.metrics ?? []).forEach((item) => {
    if (!item?.metric_id) return
    const key = String(item.metric_id).trim()
    if (!key) return
    catalog.set(key, {
      key,
      label: String(item.label || key).trim() || key,
      direction: normalizeGraphMetricDirection(item.direction),
      importance: key === result.metric_contract?.primary_metric_id ? 1 : null,
      unit: item.unit ?? null,
    })
  })
  ;(result.metric_rows ?? []).forEach((row) => {
    if (!row || typeof row !== 'object' || Array.isArray(row)) return
    const record = row as Record<string, unknown>
    const key = String(record.metric_id || record.name || record.metric || '').trim()
    if (!key) return
    const current = catalog.get(key)
    catalog.set(key, {
      key,
      label: String(record.label || record.name || current?.label || key).trim() || key,
      direction: normalizeGraphMetricDirection(record.direction) || current?.direction || null,
      importance: current?.importance ?? (key === result.metric_contract?.primary_metric_id ? 1 : null),
      unit: (typeof record.unit === 'string' ? record.unit : current?.unit) ?? null,
    })
  })
  return [...catalog.values()]
}

function collectBaselineMetricsFromBranches(branches?: GitBranchesPayload | null) {
  const metrics: Record<string, number> = {}
  const catalog = new Map<string, LabMetricObjective>()
  ;(branches?.nodes ?? []).forEach((node) => {
    ;(node.latest_result?.baseline_comparisons?.items ?? []).forEach((item) => {
      if (!item?.metric_id || typeof item.baseline_value !== 'number' || !Number.isFinite(item.baseline_value)) return
      metrics[item.metric_id] = Number(item.baseline_value)
      const current = catalog.get(item.metric_id)
      catalog.set(item.metric_id, {
        key: item.metric_id,
        label: String(item.label || current?.label || item.metric_id).trim() || item.metric_id,
        direction: normalizeGraphMetricDirection(item.direction) || current?.direction || null,
        importance: current?.importance ?? null,
        unit: item.unit ?? current?.unit ?? null,
      })
    })
  })
  return {
    metrics: Object.keys(metrics).length ? metrics : null,
    catalog: [...catalog.values()],
  }
}

function buildLocalQuestNodes(summary: QuestSummary): LabQuestNode[] {
  const stages = [
    { key: 'scout', title: 'Scout' },
    { key: 'baseline', title: 'Baseline' },
    { key: 'idea', title: 'Idea' },
    { key: 'experiment', title: 'Experiment' },
    { key: 'analysis-campaign', title: 'Analysis Campaign' },
    { key: 'write', title: 'Write' },
    { key: 'finalize', title: 'Finalize' },
  ]
  const currentKey = resolveStageKey(summary.active_anchor)
  const currentIndex = Math.max(
    0,
    stages.findIndex((stage) => stage.key === currentKey)
  )

  return stages.map((stage, index) => ({
    node_id: `${summary.quest_id}:${stage.key}`,
    quest_id: summary.quest_id,
    node_key: stage.key,
    title: stage.title,
    status: index < currentIndex ? 'done' : index === currentIndex ? 'running' : 'pending',
    position: index,
    report_md: index === currentIndex ? summary.summary?.status_line ?? '' : '',
    report_updated_at: normalizeTimestamp(summary.updated_at),
  }))
}

function buildLocalBranchWorkbench(summary: QuestSummary, branches?: GitBranchesPayload | null): BranchWorkbenchVM[] {
  if (!branches?.nodes?.length) {
    return [
      {
        branchName: summary.branch || 'main',
        branchClass: 'main',
        isHead: true,
        stage: 'baseline',
        nowDoing: summary.summary?.status_line ?? null,
        latestMetrics: null,
      },
    ]
  }

  return branches.nodes.map((node) => ({
    branchName: node.ref,
    branchClass: resolveBranchClass(node),
    parentBranch: node.parent_ref ?? null,
    worktreeRelPath: node.worktree_root ?? null,
    isHead: Boolean(node.research_head),
    stage: resolveGraphBranchStageKey(summary, node, null),
    nowDoing: node.latest_summary ?? node.subject ?? null,
    latestMetrics: extractLatestResultMetrics(node.latest_result),
  }))
}

function buildLocalGovernanceVm(summary: QuestSummary, branches?: GitBranchesPayload | null): QuestGovernanceVM {
  const branchCount = branches?.nodes?.length ?? 1
  const analysisCount = Number(summary.counts?.analysis_run_count || 0)
  const pendingDecisionCount = summary.pending_decisions?.length ?? 0
  const runtimeActive = normalizeLabWorkingStatus(summary.status) === 'working' ? 1 : 0
  const guidance = (summary.guidance ?? null) as GuidanceVm | null

  return {
    questId: summary.quest_id,
    title: summary.title || summary.quest_id,
    topology: {
      headBranch: branches?.research_head_ref || summary.research_head_branch || summary.branch || 'main',
      branchCount,
      edgeCount: branches?.edges?.length ?? 0,
    },
    runtime: {
      runningAgents: runtimeActive,
      runningPiAgents: runtimeActive,
      runningWorkerAgents: 0,
      lastHeartbeatAt: normalizeTimestamp(summary.updated_at),
      piState: summary.status,
      parallelLimit: Math.max(1, analysisCount || 1),
      activeSlots: runtimeActive,
      availableSlots: Math.max(0, Math.max(1, analysisCount || 1) - runtimeActive),
      blockedReasons: pendingDecisionCount > 0 ? ['pending_decision'] : [],
      cliStatus: 'online',
      cliLastSeenAt: normalizeTimestamp(summary.updated_at),
    },
    governance: {
      formalBaselineState: resolveFormalBaselineState(summary),
      autoPushState: 'disabled',
      lastPushStatus: 'local_only',
      writerConflict: false,
      commitTrust: 'local',
    },
    summary: {
      questAgeSeconds: 0,
      activeSpanSeconds: 0,
      branchCount,
      ideaCount: branchCount,
      experimentCount: analysisCount,
      writeCount: 0,
      completedCount: normalizeLabWorkingStatus(summary.status) === 'done' ? 1 : 0,
      progressingCount: runtimeActive,
      staleCount: 0,
      pushFailedCount: 0,
      writerConflictCount: 0,
    },
    branches: buildLocalBranchWorkbench(summary, branches),
    continuityVm: guidance
      ? {
          currentAnchor: guidance.current_anchor,
          recommendedSkill: guidance.recommended_skill,
          recommendedAction: guidance.recommended_action,
          summary: guidance.summary,
          whyNow: guidance.why_now,
          completeWhen: guidance.complete_when || [],
          alternativeRoutes: guidance.alternative_routes || [],
          suggestedArtifactCalls: guidance.suggested_artifact_calls || [],
          requiresUserDecision: Boolean(guidance.requires_user_decision),
          pendingInteractionId: guidance.pending_interaction_id ?? null,
          stageStatus: guidance.stage_status ?? null,
          sourceArtifactKind: guidance.source_artifact_kind ?? null,
          sourceArtifactId: guidance.source_artifact_id ?? null,
          relatedPaths: guidance.related_paths || [],
        }
      : null,
  }
}

function buildLocalRecentActivity(summary: QuestSummary): Array<Record<string, unknown>> {
  const items: Array<Record<string, unknown>> = []

  for (const run of summary.recent_runs || []) {
    items.push({
      title: run.summary || run.skill_id || 'Run updated',
      created_at: normalizeTimestamp(run.updated_at || run.created_at),
      ts: normalizeTimestamp(run.updated_at || run.created_at),
      source: 'run',
      run_id: run.run_id,
      agent_instance_id: `${summary.quest_id}:pi`,
    })
  }

  for (const artifact of summary.recent_artifacts || []) {
    items.push({
      title:
        artifact.payload?.summary ||
        artifact.payload?.reason ||
        artifact.payload?.artifact_id ||
        artifact.kind ||
        'Artifact updated',
      created_at: normalizeTimestamp(artifact.payload?.updated_at || summary.updated_at),
      ts: normalizeTimestamp(artifact.payload?.updated_at || summary.updated_at),
      source: 'artifact',
      agent_instance_id: `${summary.quest_id}:pi`,
    })
  }

  return items
    .sort((left, right) => String(right.created_at || '').localeCompare(String(left.created_at || '')))
    .slice(0, 20)
}

function buildLocalTemplatePools(): LabPromptPool[] {
  return LOCAL_LAB_TEMPLATE_CATALOG.map((template) => ({
    template_id: template.template_id,
    template_key: template.template_key,
    name_prompts: [template.name],
    capability_prompts: [template.purpose || template.description || 'Research orchestration'],
    strength_prompts: ['Precise', 'Auditable', 'Local-first'],
    motto_prompts: ['Think clearly, write durably, branch only with evidence.'],
  }))
}

function mapQuestSummaryToLabQuest(summary: QuestSummary, branches?: GitBranchesPayload | null): LabQuest {
  const governanceVm = buildLocalGovernanceVm(summary, branches)
  const baselineGate = resolveBaselineGate(summary)
  const confirmedBaselineId = String(
    summary.confirmed_baseline_ref?.baseline_id || summary.active_baseline_id || ''
  ).trim()
  const baselineRootId =
    baselineGate === 'confirmed'
      ? confirmedBaselineId || null
      : baselineGate === 'waived'
        ? confirmedBaselineId || 'waived'
        : null
  return {
    quest_id: summary.quest_id,
    title: summary.title || summary.quest_id,
    summary: summary.summary?.status_line || null,
    status: summary.status || 'idle',
    description: summary.summary?.status_line || null,
    tags: summary.branch ? [summary.branch] : null,
    baseline_root_id: baselineRootId,
    pi_agent_instance_id: `${summary.quest_id}:pi`,
    pi_state: summary.status || 'idle',
    cli_server_id: `local:${summary.quest_id}`,
    git_head_branch: summary.branch || 'main',
    last_event_at: normalizeTimestamp(summary.updated_at),
    pending_question_count: summary.pending_decisions?.length ?? 0,
    github_push_default_enabled: false,
    github_push: {
      enabled: false,
      mode: 'local_only',
    },
    runtime: governanceVm.runtime,
    governance: governanceVm.governance,
    summary_vm: governanceVm.summary,
    created_at: normalizeTimestamp(summary.updated_at),
  }
}

function mapQuestSummaryToLabAgent(summary: QuestSummary): LabAgentInstance {
  return {
    instance_id: `${summary.quest_id}:pi`,
    agent_id: `${summary.quest_id}:pi`,
    mention_label: 'pi',
    display_name: 'Dr-PIer',
    template_id: 'local-principal-investigator',
    status: normalizeLabWorkingStatus(summary.status),
    stats_json: {
      artifacts: Number(summary.counts?.artifacts || 0),
      memories: Number(summary.counts?.memory_cards || 0),
      analysis: Number(summary.counts?.analysis_run_count || 0),
    },
    profile_md: summary.summary?.status_line || null,
    profile_json: {
      quest_root: summary.quest_root || null,
      branch: summary.branch || 'main',
    },
    avatar_frame_color: '#8FA3B8',
    avatar_logo: null,
    direct_session_id: `quest:${summary.quest_id}`,
    active_quest_id: summary.quest_id,
    active_quest_branch: summary.branch || 'main',
    active_quest_stage_key: resolveStageKey(summary.active_anchor),
    cli_server_id: `local:${summary.quest_id}`,
    status_updated_at: normalizeTimestamp(summary.updated_at),
    created_at: normalizeTimestamp(summary.updated_at),
  }
}

function extractTraceMetrics(trace?: LabQuestNodeTrace | null) {
  const payload = asRecordValue(trace?.payload_json)
  const metricsSummary = asRecordValue(payload?.metrics_summary)
  if (metricsSummary) return metricsSummary
  const details = asRecordValue(payload?.details)
  return asRecordValue(details?.metrics_summary)
}

function extractDurableRunTraceMetrics(trace?: LabQuestNodeTrace | null) {
  const payload = asRecordValue(trace?.payload_json)
  const artifactKind = String(trace?.artifact_kind || payload?.kind || '').trim().toLowerCase()
  const resultKind = String(payload?.result_kind || '').trim().toLowerCase()
  const stageKey = String(trace?.stage_key || '').trim().toLowerCase()
  const hasRunIdentity =
    Boolean(asStringValue(payload?.run_id)) ||
    Array.isArray(payload?.metric_rows) ||
    Boolean(asRecordValue(payload?.metrics_summary))
  const isDurableRunTrace =
    artifactKind === 'run' ||
    resultKind === 'main_experiment' ||
    resultKind === 'analysis_slice' ||
    (hasRunIdentity && (stageKey === 'experiment' || stageKey === 'analysis-campaign' || stageKey === 'analysis'))
  if (!isDurableRunTrace) return null
  return extractTraceMetrics(trace)
}

function formatFoundationLabel(node: GitBranchNode) {
  const foundation = node.foundation_ref
  if (!foundation || typeof foundation !== 'object' || Array.isArray(foundation)) {
    return node.parent_ref || null
  }
  const kind = asStringValue((foundation as Record<string, unknown>).kind)
  const ref = asStringValue((foundation as Record<string, unknown>).ref)
  const branch = asStringValue((foundation as Record<string, unknown>).branch)
  if (kind && ref) return `${kind} · ${ref}`
  if (branch) return branch
  return node.parent_ref || null
}

function resolveBranchScopePaths(node: GitBranchNode): string[] | null {
  const scopes: string[] = []
  const push = (value?: string | null) => {
    const normalized = String(value || '').trim().replace(/^\/+|\/+$/g, '')
    if (!normalized || scopes.includes(normalized)) return
    scopes.push(normalized)
  }

  push('brief.md')
  push('plan.md')
  push('status.md')
  push('SUMMARY.md')
  push('artifacts/ideas')
  push('artifacts/runs')
  push('artifacts/reports')

  if (node.idea_id) {
    push(`memory/ideas/${node.idea_id}`)
    push('literature')
  }
  const latestRun = node.latest_main_experiment
  if (latestRun && typeof latestRun === 'object' && !Array.isArray(latestRun)) {
    const runId = asStringValue((latestRun as Record<string, unknown>).run_id)
    if (runId) push(`experiments/main/${runId}`)
  }
  if (String(node.branch_kind || '').trim().toLowerCase() === 'analysis') {
    push('experiments/analysis')
  }
  if (String(node.branch_kind || '').trim().toLowerCase() === 'paper' || node.next_target === 'write') {
    push('paper')
  }
  const foundation = node.foundation_ref
  if (foundation && typeof foundation === 'object' && !Array.isArray(foundation)) {
    const kind = asStringValue((foundation as Record<string, unknown>).kind)
    const ref = asStringValue((foundation as Record<string, unknown>).ref)
    if (kind === 'baseline' && ref) {
      push(`baselines/imported/${ref}`)
      push(`baselines/local/${ref}`)
    }
  }

  return scopes.length ? scopes : null
}

function mapGitNodeToLabQuestGraphNode(
  questId: string,
  summary: QuestSummary,
  node: GitBranchNode,
  branchTrace?: LabQuestNodeTrace | null
): LabQuestGraphNode {
  const traceMetrics = extractDurableRunTraceMetrics(branchTrace)
  const traceWorktreeRelPath = String(branchTrace?.worktree_rel_path || '').trim() || null
  const metrics = extractLatestResultMetrics(node.latest_result) || traceMetrics
  const metricDeltas = extractLatestResultMetricDeltas(node.latest_result)
  const stageKey = resolveGraphBranchStageKey(summary, node, branchTrace)

  return {
    node_id: node.ref,
    branch_name: node.ref,
    parent_branch: node.parent_ref ?? null,
    branch_no: node.branch_no ?? null,
    idea_title: node.idea_title ?? null,
    idea_problem: node.idea_problem ?? null,
    next_target: node.next_target ?? null,
    foundation_ref: node.foundation_ref ?? null,
    foundation_reason: node.foundation_reason ?? null,
    foundation_label: formatFoundationLabel(node),
    latest_main_experiment: node.latest_main_experiment ?? null,
    experiment_count: node.experiment_count ?? null,
    branch_class: resolveBranchClass(node),
    node_kind: 'branch',
    placeholder: false,
    worktree_rel_path: traceWorktreeRelPath,
    latest_commit: branchTrace?.head_commit || node.head || null,
    latest_result: node.latest_result ?? null,
    status: node.active_workspace ? 'active' : node.research_head ? 'head' : 'ready',
    idea_id: (asStringValue(asRecordValue(branchTrace?.payload_json)?.idea_id) || node.idea_id) ?? null,
    metrics_json: metrics,
    verdict: branchTrace?.summary || node.latest_summary || null,
    claim_verdict: null,
    go_decision: null,
    created_at: normalizeTimestamp(branchTrace?.updated_at || node.updated_at || summary.updated_at),
    stage_key: stageKey,
    stage_title: formatStageTitle(stageKey),
    event_ids: branchTrace?.actions
      ?.map((action) => String(action.action_id || '').trim())
      .filter((value): value is string => Boolean(value)),
    event_count: branchTrace?.counts?.actions ?? node.commit_count ?? 0,
    baseline_state: resolveBaselineGate(summary),
    runtime_state: node.active_workspace ? normalizeLabWorkingStatus(summary.status) : 'idle',
    target_label: node.label,
    scope_paths: resolveBranchScopePaths(node),
    compare_base: resolveBranchCompareBase(node),
    compare_head: node.ref,
    workflow_state: (node.workflow_state as LabBranchWorkflowState | null) ?? null,
    node_summary: {
      last_event_type:
        branchTrace?.artifact_kind ||
        branchTrace?.actions?.[branchTrace.actions.length - 1]?.raw_event_type ||
        stageKey,
      last_reply: branchTrace?.summary || node.latest_summary || node.subject || null,
      metrics_delta: metricDeltas,
      latest_metrics: metrics,
      trend_preview: null,
      claim_verdict: null,
      go_decision: null,
    },
  }
}

function buildFallbackGraphNode(summary: QuestSummary, branchTrace?: LabQuestNodeTrace | null): LabQuestGraphNode {
  const stageKey = resolveGraphBranchStageKey(summary, null, branchTrace)
  const traceMetrics = extractDurableRunTraceMetrics(branchTrace)
  return {
    node_id: summary.branch || 'main',
    branch_name: summary.branch || 'main',
    parent_branch: null,
    branch_class: 'main',
    node_kind: 'branch',
    placeholder: false,
    worktree_rel_path: null,
    latest_commit: branchTrace?.head_commit || summary.head || null,
    status: 'active',
    metrics_json: traceMetrics,
    verdict: branchTrace?.summary || summary.summary?.status_line || null,
    created_at: normalizeTimestamp(branchTrace?.updated_at || summary.updated_at),
    stage_key: stageKey,
    stage_title: formatStageTitle(stageKey),
    event_ids: branchTrace?.actions
      ?.map((action) => String(action.action_id || '').trim())
      .filter((value): value is string => Boolean(value)),
    event_count: branchTrace?.counts?.actions ?? Number(summary.counts?.artifacts || 0),
    baseline_state: resolveBaselineGate(summary),
    runtime_state: normalizeLabWorkingStatus(summary.status),
    target_label: summary.title || summary.quest_id,
    scope_paths: null,
    compare_base: null,
    compare_head: summary.branch || 'main',
    node_summary: {
      last_event_type:
        branchTrace?.artifact_kind ||
        branchTrace?.actions?.[branchTrace.actions.length - 1]?.raw_event_type ||
        stageKey,
      last_reply: branchTrace?.summary || summary.summary?.status_line || null,
      latest_metrics: traceMetrics,
      trend_preview: null,
      claim_verdict: null,
      go_decision: null,
    },
  }
}

function traceMatchesSearch(trace: LabQuestNodeTrace, query?: string | null): boolean {
  const normalized = String(query || '').trim().toLowerCase()
  if (!normalized) return true
  const haystack = [
    trace.selection_ref,
    trace.title,
    trace.summary,
    trace.branch_name,
    trace.stage_key,
    trace.stage_title,
    ...(trace.actions ?? []).flatMap((action) => [
      action.title,
      action.summary,
      action.raw_event_type,
      action.tool_name,
      action.args,
      action.output,
    ]),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return haystack.includes(normalized)
}

function mapTraceToGraphNode(
  trace: LabQuestNodeTrace,
  summary: QuestSummary,
  view: 'event' | 'stage'
): LabQuestGraphNode {
  const lastAction = trace.actions[trace.actions.length - 1] ?? null
  const branchName = trace.branch_name || summary.branch || 'main'
  const status =
    trace.artifact_kind ||
    trace.status ||
    lastAction?.artifact_kind ||
    lastAction?.raw_event_type ||
    lastAction?.kind ||
    (view === 'stage' ? trace.stage_key : 'event')
  const actionIds = trace.actions
    .map((action) => String(action.action_id || '').trim())
    .filter((actionId): actionId is string => Boolean(actionId))
  const payload = asRecordValue(trace.payload_json)
  const metrics = extractTraceMetrics(trace)
  const ideaId = asStringValue(payload?.idea_id)
  return {
    node_id: trace.selection_ref,
    branch_name: branchName,
    parent_branch: null,
    branch_class: branchName === 'main' ? 'main' : branchName.startsWith('analysis/') ? 'analysis' : null,
    worktree_rel_path: trace.worktree_rel_path || null,
    latest_commit: trace.head_commit || null,
    status,
    idea_id: ideaId,
    idea_json: ideaId ? payload : null,
    metrics_json: metrics,
    verdict: trace.summary || null,
    claim_verdict: null,
    go_decision: null,
    created_at: trace.updated_at || null,
    stage_key: trace.stage_key || null,
    stage_title: trace.stage_title || null,
    event_ids: actionIds,
    event_count: trace.counts?.actions ?? actionIds.length,
    baseline_state: null,
    push_state: null,
    writer_state: null,
    runtime_state: null,
    protected_state: null,
    divergence_state: null,
    reconcile_state: null,
    proof_state: null,
    submission_state: null,
    retire_state: null,
    claim_evidence_state: null,
    commit_trust: null,
    target_label: trace.title,
    node_summary: {
      last_event_type: trace.artifact_kind || lastAction?.artifact_kind || lastAction?.raw_event_type || lastAction?.kind || null,
      last_reply: trace.summary || lastAction?.summary || null,
      last_error:
        String(lastAction?.status || '').toLowerCase().includes('fail') ||
        String(lastAction?.status || '').toLowerCase().includes('error')
          ? trace.summary || lastAction?.summary || lastAction?.output || null
          : null,
      metrics_delta: null,
      latest_metrics: metrics,
      trend_preview: null,
      metric_curves: null,
      claim_verdict: null,
      go_decision: null,
    },
  }
}

function buildTraceEdges(
  traces: LabQuestNodeTrace[],
  view: 'event' | 'stage'
): LabQuestGraphEdge[] {
  const grouped = new Map<string, LabQuestNodeTrace[]>()
  traces.forEach((trace) => {
    const branchName = trace.branch_name || 'main'
    const items = grouped.get(branchName) ?? []
    items.push(trace)
    grouped.set(branchName, items)
  })
  const edges: LabQuestGraphEdge[] = []
  grouped.forEach((items, branchName) => {
    const ordered = [...items].sort((left, right) => {
      if (view === 'stage') {
        const rankDelta = resolveStageRank(left.stage_key) - resolveStageRank(right.stage_key)
        if (rankDelta !== 0) return rankDelta
      }
      return String(left.updated_at || '').localeCompare(String(right.updated_at || ''))
    })
    ordered.forEach((item, index) => {
      if (index === 0) return
      const previous = ordered[index - 1]
      edges.push({
        edge_id: `${view}:${branchName}:${previous.selection_ref}:${item.selection_ref}`,
        source: previous.selection_ref,
        target: item.selection_ref,
        edge_type: view === 'stage' ? 'stage' : 'sequence',
      })
    })
  })
  return edges
}

async function loadLocalQuestSummary(projectId: string): Promise<QuestSummary> {
  return loadWithShortCache(localQuestSummaryCache, projectId, LOCAL_QUEST_SESSION_TTL_MS, async () => {
    const session = await questClient.session(projectId)
    return session.snapshot as QuestSummary
  })
}

async function loadLocalQuestWorkflow(projectId: string): Promise<WorkflowPayload | null> {
  try {
    return await questClient.workflow(projectId)
  } catch {
    return null
  }
}

async function loadLocalQuestNodeTraces(
  projectId: string
): Promise<LabQuestNodeTraceListResponse | null> {
  try {
    return await questClient.nodeTraces(projectId)
  } catch {
    try {
      const summary = await loadLocalQuestSummary(projectId)
      const artifacts = await loadLocalQuestArtifacts(projectId)
      const events = await loadLocalQuestEvents(projectId)
      return buildLocalTracePayload(summary, artifacts, events)
    } catch {
      return null
    }
  }
}

async function loadLocalQuestBranches(projectId: string): Promise<GitBranchesPayload | null> {
  return loadWithShortCache(localQuestBranchesCache, projectId, LOCAL_QUEST_BRANCHES_TTL_MS, async () => {
    try {
      return await questClient.gitBranches(projectId)
    } catch {
      return null
    }
  })
}

async function loadLocalQuestLayout(
  projectId: string
): Promise<{ layout_json?: Record<string, unknown> | null; updated_at?: string | null } | null> {
  return loadWithShortCache(localQuestLayoutCache, projectId, LOCAL_QUEST_LAYOUT_TTL_MS, async () => {
    try {
      return await questClient.layout(projectId)
    } catch {
      return null
    }
  })
}

async function loadLocalQuestArtifacts(projectId: string): Promise<QuestArtifactListPayload | null> {
  try {
    return await questClient.artifacts(projectId)
  } catch {
    return null
  }
}

async function loadLocalQuestEvents(projectId: string): Promise<QuestRawEventListPayload | null> {
  try {
    let after = 0
    let hasMore = true
    let questId = projectId
    const events: QuestEventRecord[] = []
    while (hasMore && events.length < LOCAL_QUEST_EVENT_FETCH_MAX) {
      const response = await questClient.rawEvents(projectId, {
        after,
        limit: Math.min(LOCAL_QUEST_EVENT_FETCH_CHUNK, LOCAL_QUEST_EVENT_FETCH_MAX - events.length),
      })
      questId = response.quest_id || questId
      events.push(...(response.events || []))
      hasMore = Boolean(response.has_more)
      after = response.cursor || after + (response.events?.length || 0)
      if (!(response.events?.length || 0)) {
        break
      }
    }
    return {
      quest_id: questId,
      cursor: after,
      has_more: hasMore,
      format: 'raw',
      events,
    }
  } catch {
    return null
  }
}

function buildArtifactTitle(item: QuestArtifactRecord, payload?: Record<string, unknown> | null) {
  const artifactId =
    asStringValue(payload?.artifact_id) ||
    asStringValue(payload?.id) ||
    item.path.split('/').pop()?.replace(/\.json$/i, '') ||
    item.kind
  const stage = formatStageTitle(resolveArtifactStageKey(payload))
  return `${stage} · ${artifactId}`
}

function mapRawEventToTimeline(
  event: QuestEventRecord,
  artifactPayload?: Record<string, unknown> | null
): LabQuestTimelineEntry {
  return {
    event_id: event.event_id,
    event_type: event.type,
    branch_name: resolveRawEventBranchName(event, artifactPayload, null),
    created_at: asStringValue(event.created_at) || nowIso(),
    payload_summary: resolveRawEventSummary(event, artifactPayload),
    source: event.type,
    source_ref: asStringValue(event.run_id),
    authority_level: null,
  }
}

function isDisplayableQuestEvent(event: QuestEventRecord) {
  if (event.type === 'artifact.recorded') return true
  if (event.type === 'conversation.message') return true
  if (event.type === 'interaction.reply_received') return true
  if (event.type === 'quest.control') return true
  if (event.type === 'runner.tool_call' || event.type === 'runner.tool_result') {
    return isCanvasRelevantToolEvent(event)
  }
  return false
}

function mapRawEventToQuestEvent(
  event: QuestEventRecord,
  artifactPayload?: Record<string, unknown> | null,
  includePayload = false,
  fallbackStage?: string | null
): LabQuestEventItem {
  return {
    event_id: event.event_id,
    event_type: event.type,
    branch_name: resolveRawEventBranchName(event, artifactPayload, null),
    stage_key: resolveRawEventStageKey(event, artifactPayload, fallbackStage),
    commit_hash: asStringValue(event.head_commit) || asStringValue(artifactPayload?.head_commit),
    payload_summary: resolveRawEventSummary(event, artifactPayload),
    reply_to_pi:
      asStringValue(event.content) ||
      asStringValue(artifactPayload?.reason) ||
      asStringValue(artifactPayload?.summary),
    created_at: asStringValue(event.created_at) || nowIso(),
    payload_json: includePayload ? buildEventPayloadEnvelope(event, artifactPayload) : null,
  }
}

function buildTraceCounts(actions: LabQuestNodeTraceAction[]) {
  return {
    actions: actions.length,
    tool_calls: actions.filter((action) => action.kind === 'tool_call').length,
    tool_results: actions.filter((action) => action.kind === 'tool_result').length,
    artifacts: actions.filter((action) => action.kind === 'artifact').length,
    messages: actions.filter((action) => action.raw_event_type === 'conversation.message').length,
  }
}

function dedupeTraceActions(actions: LabQuestNodeTraceAction[]) {
  const byId = new Map<string, LabQuestNodeTraceAction>()
  actions.forEach((action) => {
    const key = String(action.action_id || '').trim()
    if (key) {
      byId.set(key, action)
    }
  })
  return [...byId.values()].sort((left, right) =>
    String(left.created_at || left.action_id || '').localeCompare(String(right.created_at || right.action_id || ''))
  )
}

function buildTraceSummary(actions: LabQuestNodeTraceAction[], fallback?: string | null) {
  for (let index = actions.length - 1; index >= 0; index -= 1) {
    const action = actions[index]
    const summary = compactText(action.summary) || compactText(action.output) || compactText(action.title)
    if (summary) return summary
  }
  return fallback || null
}

function mapRawEventToTraceAction(
  event: QuestEventRecord,
  artifactPayload?: Record<string, unknown> | null,
  artifactItem?: QuestArtifactRecord | null,
  fallbackStage?: string | null
): LabQuestNodeTraceAction {
  const branchName = resolveRawEventBranchName(event, artifactPayload, null)
  const stageKey = resolveRawEventStageKey(event, artifactPayload, fallbackStage)
  const pathsMap = normalizePathMap(artifactPayload?.paths || event.paths)
  const title =
    event.type === 'artifact.recorded'
      ? `${String(artifactPayload?.kind || artifactItem?.kind || 'artifact')} recorded`
      : event.type === 'conversation.message'
        ? `${String(event.role || 'message')} message`
        : String(event.tool_name || event.mcp_tool || event.type || 'event')
  const kind =
    event.type === 'artifact.recorded'
      ? 'artifact'
      : event.type === 'runner.tool_call'
        ? 'tool_call'
        : event.type === 'runner.tool_result'
          ? 'tool_result'
          : event.type
  return {
    action_id: event.event_id,
    kind,
    title,
    summary: resolveRawEventSummary(event, artifactPayload),
    status: asStringValue(event.status),
    created_at: asStringValue(event.created_at) || nowIso(),
    run_id: asStringValue(event.run_id),
    skill_id: asStringValue(event.skill_id),
    branch_name: branchName,
    stage_key: stageKey,
    worktree_rel_path: asStringValue(artifactPayload?.workspace_rel_path),
    tool_name: asStringValue(event.tool_name) || asStringValue(event.mcp_tool),
    tool_call_id: asStringValue(event.tool_call_id),
    mcp_server: asStringValue(event.mcp_server),
    mcp_tool: asStringValue(event.mcp_tool),
    args: asStringValue(event.args),
    output: asStringValue(event.output) || asStringValue(event.content),
    reason: asStringValue(event.reason) || asStringValue(artifactPayload?.reason),
    raw_event_type: event.type,
    paths: Object.values(pathsMap || {}).filter((entry): entry is string => Boolean(entry)),
    paths_map: pathsMap,
    artifact_id:
      asStringValue(artifactPayload?.artifact_id) ||
      asStringValue(artifactPayload?.id) ||
      extractArtifactIdFromRawEvent(event),
    artifact_kind: asStringValue(artifactPayload?.kind) || artifactItem?.kind || asStringValue(event.kind),
    artifact_path: artifactItem?.path || asStringValue(event.artifact_path),
    head_commit: asStringValue(artifactPayload?.head_commit) || asStringValue(event.head_commit),
    payload_json: artifactPayload || buildEventPayloadEnvelope(event).payload,
    details_json: asRecordValue(artifactPayload?.details) || asRecordValue(event.details),
    checkpoint_json: asRecordValue(event.checkpoint),
    changed_files: collectArtifactChangedFiles(artifactPayload),
    trace_confidence: artifactPayload ? 'artifact' : isArtifactToolEvent(event) ? 'tool_event' : 'event',
  }
}

function buildLocalTracePayload(
  summary: QuestSummary,
  artifacts: QuestArtifactListPayload | null,
  rawEvents: QuestRawEventListPayload | null
): LabQuestNodeTraceListResponse {
  const rawEventItems = [...(rawEvents?.events || [])].sort((left, right) =>
    String(left.created_at || left.event_id || '').localeCompare(String(right.created_at || right.event_id || ''))
  )
  const artifactItems = [...(artifacts?.items || [])]
  const artifactPayloadById = new Map<string, Record<string, unknown>>()
  artifactItems.forEach((item) => {
    const payload = asRecordValue(item.payload)
    const artifactId = asStringValue(payload?.artifact_id) || asStringValue(payload?.id)
    if (payload && artifactId) {
      artifactPayloadById.set(artifactId, payload)
    }
  })
  const relatedEventsByArtifactId = new Map<string, QuestEventRecord[]>()
  rawEventItems.forEach((event) => {
    const artifactId = extractArtifactIdFromRawEvent(event)
    if (!artifactId) return
    const bucket = relatedEventsByArtifactId.get(artifactId) || []
    bucket.push(event)
    relatedEventsByArtifactId.set(artifactId, bucket)
  })

  const eventTraces: LabQuestNodeTrace[] = artifactItems.map((item) => {
    const payload = asRecordValue(item.payload) || {}
    const artifactId =
      asStringValue(payload.artifact_id) ||
      asStringValue(payload.id) ||
      item.path.split('/').pop()?.replace(/\.json$/i, '') ||
      item.kind
    const relatedEvents = relatedEventsByArtifactId.get(artifactId) || []
    const recordedEvent =
      relatedEvents.find((event) => event.type === 'artifact.recorded') ||
      ({
        event_id: `artifact:${artifactId}`,
        type: 'artifact.recorded',
        artifact_id: artifactId,
        created_at: asStringValue(payload.updated_at) || asStringValue(payload.created_at) || nowIso(),
        branch: asStringValue(payload.branch) || summary.branch || 'main',
        head_commit: asStringValue(payload.head_commit),
        kind: item.kind,
        status: asStringValue(payload.status),
        summary: asStringValue(payload.summary),
        reason: asStringValue(payload.reason),
      } satisfies QuestEventRecord)
    const branchName = resolveRawEventBranchName(recordedEvent, payload, summary.branch || 'main')
    const stageKey = resolveArtifactStageKey(payload, summary.active_anchor)
    const actions = dedupeTraceActions(
      [...relatedEvents, recordedEvent].map((event) =>
        mapRawEventToTraceAction(event, payload, item, summary.active_anchor)
      )
    )
    return {
      selection_type: 'event_node',
      selection_ref: String(recordedEvent.event_id || `artifact:${artifactId}`),
      title: buildArtifactTitle(item, payload),
      summary: buildTraceSummary(actions, compactText(payload.summary) || compactText(payload.reason)),
      status: asStringValue(payload.status) || item.kind,
      branch_name: branchName,
      stage_key: stageKey,
      stage_title: formatStageTitle(stageKey),
      worktree_rel_path: asStringValue(payload.workspace_rel_path),
      updated_at:
        asStringValue(payload.updated_at) ||
        asStringValue(recordedEvent.created_at) ||
        normalizeTimestamp(summary.updated_at),
      counts: buildTraceCounts(actions),
      run_ids: [...new Set(actions.map((action) => action.run_id).filter((value): value is string => Boolean(value)))],
      skill_ids: [...new Set(actions.map((action) => action.skill_id).filter((value): value is string => Boolean(value)))],
      artifact_id: artifactId,
      artifact_kind: item.kind,
      head_commit: asStringValue(payload.head_commit),
      payload_json: payload,
      details_json: asRecordValue(payload.details),
      paths_map: normalizePathMap(payload.paths),
      changed_files: collectArtifactChangedFiles(payload),
      actions,
    }
  })

  const stageGroups = new Map<string, LabQuestNodeTrace[]>()
  const branchGroups = new Map<string, LabQuestNodeTrace[]>()
  const latestCanonicalStageByBranch = new Map<string, string>()
  ;[...eventTraces]
    .sort((left, right) => String(left.updated_at || '').localeCompare(String(right.updated_at || '')))
    .forEach((trace) => {
    const branchName = trace.branch_name || 'main'
    const payload = asRecordValue(trace.payload_json)
    const stageKey =
      trace.stage_key === 'decision'
        ? resolveDecisionActionStage(payload, latestCanonicalStageByBranch.get(branchName) || summary.active_anchor)
        : trace.stage_key || 'baseline'
    if (isCanonicalStage(stageKey)) {
      latestCanonicalStageByBranch.set(branchName, stageKey)
    }
    stageGroups.set(`${branchName}:${stageKey}`, [...(stageGroups.get(`${branchName}:${stageKey}`) || []), trace])
    branchGroups.set(branchName, [...(branchGroups.get(branchName) || []), trace])
    })

  const stageTraces: LabQuestNodeTrace[] = [...stageGroups.entries()].map(([groupKey, traces]) => {
    const latest = [...traces].sort((left, right) =>
      String(left.updated_at || '').localeCompare(String(right.updated_at || ''))
    )[traces.length - 1]
    const mergedActions = dedupeTraceActions(traces.flatMap((trace) => trace.actions))
    const [branchName, stageKey] = groupKey.split(':', 2)
    return {
      selection_type: 'stage_node',
      selection_ref: `stage:${branchName}:${stageKey}`,
      title: `${branchName} · ${formatStageTitle(stageKey)}`,
      summary: buildTraceSummary(mergedActions, latest?.summary),
      status: stageKey,
      branch_name: branchName,
      stage_key: stageKey,
      stage_title: formatStageTitle(stageKey),
      worktree_rel_path: latest?.worktree_rel_path || null,
      updated_at: latest?.updated_at || normalizeTimestamp(summary.updated_at),
      counts: buildTraceCounts(mergedActions),
      run_ids: [...new Set(traces.flatMap((trace) => trace.run_ids || []))],
      skill_ids: [...new Set(traces.flatMap((trace) => trace.skill_ids || []))],
      artifact_id: latest?.artifact_id || null,
      artifact_kind: latest?.artifact_kind || null,
      head_commit: latest?.head_commit || null,
      payload_json: latest?.payload_json || null,
      details_json: latest?.details_json || null,
      paths_map: latest?.paths_map || null,
      changed_files: latest?.changed_files || null,
      actions: mergedActions,
    }
  })

  const branchTraces: LabQuestNodeTrace[] = [...branchGroups.entries()].map(([branchName, traces]) => {
    const latest = [...traces].sort((left, right) =>
      String(left.updated_at || '').localeCompare(String(right.updated_at || ''))
    )[traces.length - 1]
    const mergedActions = dedupeTraceActions(traces.flatMap((trace) => trace.actions))
    return {
      selection_type: 'branch_node',
      selection_ref: branchName,
      title: branchName,
      summary: buildTraceSummary(mergedActions, latest?.summary),
      status: latest?.status || null,
      branch_name: branchName,
      stage_key: latest?.stage_key || null,
      stage_title: latest?.stage_title || null,
      worktree_rel_path: latest?.worktree_rel_path || null,
      updated_at: latest?.updated_at || normalizeTimestamp(summary.updated_at),
      counts: buildTraceCounts(mergedActions),
      run_ids: [...new Set(traces.flatMap((trace) => trace.run_ids || []))],
      skill_ids: [...new Set(traces.flatMap((trace) => trace.skill_ids || []))],
      artifact_id: latest?.artifact_id || null,
      artifact_kind: latest?.artifact_kind || null,
      head_commit: latest?.head_commit || null,
      payload_json: latest?.payload_json || null,
      details_json: latest?.details_json || null,
      paths_map: latest?.paths_map || null,
      changed_files: latest?.changed_files || null,
      actions: mergedActions,
    }
  })

  const items = [...branchTraces, ...stageTraces, ...eventTraces].sort((left, right) => {
    const typeDelta = String(left.selection_type || '').localeCompare(String(right.selection_type || ''))
    if (typeDelta !== 0) return typeDelta
    return String(left.updated_at || '').localeCompare(String(right.updated_at || ''))
  })

  return {
    quest_id: summary.quest_id,
    generated_at: nowIso(),
    materialized_path: null,
    items,
  }
}

function buildLocalQuestGraphResponse(
  summary: QuestSummary,
  branches: GitBranchesPayload | null,
  params?: { view?: 'branch' | 'event' | 'stage'; search?: string; atEventId?: string | null },
  nodeTraces?: LabQuestNodeTraceListResponse | null,
  layoutJson?: Record<string, unknown> | null
): LabQuestGraphResponse {
  const view = params?.view ?? 'branch'
  const items = nodeTraces?.items ?? []
  const branchTraceByName = new Map(
    items
      .filter((trace) => trace.selection_type === 'branch_node' && trace.selection_ref)
      .map((trace) => [trace.selection_ref, trace] as const)
  )
  if (view === 'event' || view === 'stage') {
    const selectionType = view === 'event' ? 'event_node' : 'stage_node'
    const traces = items
      .filter((trace) => trace.selection_type === selectionType)
      .filter((trace) => traceMatchesSearch(trace, params?.search))
      .sort((left, right) => String(left.updated_at || '').localeCompare(String(right.updated_at || '')))
    return {
      view,
      nodes: traces.map((trace) => mapTraceToGraphNode(trace, summary, view)),
      edges: buildTraceEdges(traces, view),
      head_branch: summary.branch || 'main',
      projection_status: null,
      layout_json: layoutJson ?? null,
      metric_catalog: [],
      governance_vm: buildLocalGovernanceVm(summary, branches),
      overlay_actions: [],
    }
  }
  const branchNodes = buildLocalBranchGraphNodes(summary, branches, branchTraceByName)
  const branchEdges = buildLocalBranchGraphEdges(summary, branchNodes, branches)
  return {
    view,
    nodes: branchNodes,
    edges: branchEdges,
    head_branch: summary.branch || 'main',
    projection_status: branches?.projection_status ?? null,
    layout_json: layoutJson ?? null,
    metric_catalog: buildGraphMetricCatalogFromNodes(branchNodes),
    governance_vm: buildLocalGovernanceVm(summary, branches),
    overlay_actions: [],
  }
}

function mapWorkflowEntryToTimeline(entry: WorkflowEntry): LabQuestTimelineEntry {
  return {
    event_id: entry.id,
    event_type: entry.raw_event_type || entry.kind,
    branch_name: null,
    created_at: entry.created_at || nowIso(),
    payload_summary: entry.summary || entry.title,
    source: entry.kind,
    source_ref: entry.run_id || null,
    authority_level: null,
  }
}

function mapWorkflowEntryToQuestEvent(entry: WorkflowEntry): LabQuestEventItem {
  return {
    event_id: entry.id,
    event_type: entry.raw_event_type || entry.kind,
    branch_name: null,
    stage_key: entry.skill_id || null,
    payload_summary: entry.summary || entry.title,
    created_at: entry.created_at || nowIso(),
    payload_json: {
      title: entry.title,
      summary: entry.summary,
      tool_name: entry.tool_name,
      status: entry.status,
      args: entry.args,
      output: entry.output,
    },
  }
}

function mapMemoryCardKind(card: MemoryCard): string {
  const type = String(card.type || '').toLowerCase()
  if (type.includes('incident')) return 'incident'
  if (type.includes('episode')) return 'episode'
  return 'knowledge'
}

function mapMemoryCardToEntry(card: MemoryCard): LabMemoryEntry {
  return {
    entry_id: card.document_id || card.path || card.title || crypto.randomUUID(),
    kind: mapMemoryCardKind(card),
    title: card.title || card.document_id || 'Memory',
    summary: card.excerpt || null,
    source_path: card.path || null,
    updated_at: nowIso(),
    created_at: nowIso(),
  }
}

async function resolveLocalMemoryEntry(projectId: string, entryId: string): Promise<LabMemoryEntry> {
  const documentId = entryId.startsWith('memory::') ? entryId : null
  if (!documentId) {
    const cards = await questClient.memory(projectId)
    const matched = cards.find((card) => (card.document_id || card.path || card.title) === entryId)
    if (matched?.document_id) {
      return resolveLocalMemoryEntry(projectId, matched.document_id)
    }
    return {
      entry_id: entryId,
      kind: 'knowledge',
      title: entryId,
      summary: null,
      content_md: null,
      updated_at: nowIso(),
      created_at: nowIso(),
    }
  }

  const opened = await questClient.openDocument(projectId, documentId)
  return {
    entry_id: documentId,
    kind: 'knowledge',
    title: opened.title,
    summary: null,
    content_md: opened.content,
    source_path: opened.path || null,
    updated_at: opened.updated_at || nowIso(),
    created_at: opened.updated_at || nowIso(),
  }
}

export async function listLabTemplates(projectId: string): Promise<LabListResponse<LabTemplate>> {
  if (await shouldUseLocalQuestLab(projectId)) {
    return { items: LOCAL_LAB_TEMPLATE_CATALOG }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/templates`)
    return response.data ?? { items: [] }
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    return { items: LOCAL_LAB_TEMPLATE_CATALOG }
  }
}

export async function listLabPromptPools(projectId: string): Promise<LabListResponse<LabPromptPool>> {
  if (await shouldUseLocalQuestLab(projectId)) {
    return { items: buildLocalTemplatePools() }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/prompt-pools`)
    return response.data ?? { items: [] }
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    return { items: buildLocalTemplatePools() }
  }
}

export async function listLabAgents(
  projectId: string,
  options?: LabRequestOptions
): Promise<LabListResponse<LabAgentInstance>> {
  if (isDemoProjectId(projectId)) {
    return listDemoLabAgents(projectId) ?? { items: [] }
  }
  if (await shouldUseLocalQuestLab(projectId)) {
    const summary = await loadLocalQuestSummary(projectId)
    return { items: [mapQuestSummaryToLabAgent(summary)] }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/agents`, buildLabRequestConfig(options))
    return response.data ?? { items: [] }
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    const summary = await loadLocalQuestSummary(projectId)
    return { items: [mapQuestSummaryToLabAgent(summary)] }
  }
}

export async function createLabAgent(
  projectId: string,
  payload: {
    template_key: string
    agent_id?: string
    request_id?: string
    display_name?: string
    profile_json?: Record<string, unknown>
    stats_json?: Record<string, unknown>
    avatar_frame_color?: string
    cli_server_id?: string
  }
): Promise<{ agent: LabAgentInstance }> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/agents`, payload)
  return response.data
}

export async function updateLabAgent(
  projectId: string,
  agentInstanceId: string,
  payload: {
    display_name?: string
    mention_label?: string
    stats_json?: Record<string, unknown>
    profile_json?: Record<string, unknown>
    avatar_frame_color?: string
    cli_server_id?: string
  }
): Promise<{ agent: LabAgentInstance }> {
  const response = await apiClient.patch(`${LAB_BASE(projectId)}/agents/${agentInstanceId}`, payload)
  return response.data
}

export async function assignLabAgent(
  projectId: string,
  agentInstanceId: string,
  payload: { quest_id?: string | null; quest_node_id?: string | null }
): Promise<{ agent: LabAgentInstance }> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/agents/${agentInstanceId}/assign`, payload)
  return response.data
}

export async function getLabAgentDirectSession(
  projectId: string,
  agentInstanceId: string
): Promise<{ session_id: string; created: boolean }> {
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/agents/${agentInstanceId}/direct-session`)
    return response.data
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    return {
      session_id: `quest:${projectId}`,
      created: false,
    }
  }
}

export type LabSurfaceSession = {
  session_id: string
  surface: 'group' | 'friends'
}

export async function getLabGroupSession(
  projectId: string,
  questId: string
): Promise<LabSurfaceSession> {
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/group/session`)
    return response.data
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    return { session_id: `quest:${questId}`, surface: 'group' }
  }
}

export async function getLabFriendsSession(
  projectId: string,
  questId: string
): Promise<LabSurfaceSession> {
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/friends/session`)
    return response.data
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    return { session_id: `quest:${questId}`, surface: 'friends' }
  }
}

export async function listLabMoments(
  projectId: string,
  params?: { questId?: string | null; cursor?: string | null; limit?: number }
): Promise<LabMomentsResponse> {
  const response = await apiClient.get(`${LAB_BASE(projectId)}/moments`, {
    params: {
      quest_id: params?.questId ?? undefined,
      cursor: params?.cursor ?? undefined,
      limit: params?.limit ?? undefined,
    },
  })
  return response.data ?? { items: [] }
}

export async function likeLabMoment(
  projectId: string,
  momentId: string
): Promise<LabLikeResponse> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/moments/${momentId}/like`)
  return response.data
}

export async function unlikeLabMoment(
  projectId: string,
  momentId: string
): Promise<LabLikeResponse> {
  const response = await apiClient.delete(`${LAB_BASE(projectId)}/moments/${momentId}/like`)
  return response.data
}

export async function commentLabMoment(
  projectId: string,
  momentId: string,
  payload: { content: string }
): Promise<LabMomentCommentResponse> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/moments/${momentId}/comments`, payload)
  return response.data
}

export async function getLabAgentPrompt(
  projectId: string,
  agentInstanceId: string
): Promise<LabAgentPromptResponse> {
  const response = await apiClient.get(`${LAB_BASE(projectId)}/agents/${agentInstanceId}/prompt`)
  return response.data ?? { content: '', updated_at: null }
}

export async function updateLabAgentPrompt(
  projectId: string,
  agentInstanceId: string,
  payload: { content: string }
): Promise<LabAgentPromptResponse> {
  const response = await apiClient.put(`${LAB_BASE(projectId)}/agents/${agentInstanceId}/prompt`, payload)
  return response.data
}

export async function listLabAgentHistory(
  projectId: string,
  agentInstanceId: string
): Promise<{
  items: Array<{
    history_id: string
    agent_instance_id: string
    quest_id?: string | null
    quest_node_id?: string | null
    assigned_by?: string | null
    assigned_at: string
  }>
}> {
  const response = await apiClient.get(`${LAB_BASE(projectId)}/agents/${agentInstanceId}/history`)
  return response.data ?? { items: [] }
}

export async function deleteLabAgent(
  projectId: string,
  agentInstanceId: string,
  cliServerId?: string
): Promise<LabAgentDeleteResponse> {
  const response = await apiClient.delete(`${LAB_BASE(projectId)}/agents/${agentInstanceId}`, {
    params: cliServerId ? { cli_server_id: cliServerId } : undefined,
  })
  return response.data
}

export async function getLabSkillManifest(
  projectId: string,
  cliServerId: string
): Promise<LabAssetContent> {
  const response = await apiClient.get(`${LAB_BASE(projectId)}/assets/knowledge/skills/manifest`, {
    params: { cli_server_id: cliServerId },
  })
  return response.data
}

export async function getLabSkillDetail(
  projectId: string,
  cliServerId: string,
  skillId: string
): Promise<LabAssetContent> {
  const response = await apiClient.get(`${LAB_BASE(projectId)}/assets/knowledge/skills/${skillId}`, {
    params: { cli_server_id: cliServerId },
  })
  return response.data
}

export async function getLabKnowledgeIndex(
  projectId: string,
  cliServerId: string,
  kind: 'knowledge' | 'episodes' | 'incidents'
): Promise<LabAssetContent> {
  const response = await apiClient.get(`${LAB_BASE(projectId)}/assets/knowledge/index/${kind}`, {
    params: { cli_server_id: cliServerId },
  })
  return response.data
}

export async function getLabAssetFile(
  projectId: string,
  cliServerId: string,
  path: string
): Promise<LabAssetContent> {
  const response = await apiClient.get(`${LAB_BASE(projectId)}/assets/knowledge/file`, {
    params: { cli_server_id: cliServerId, path },
  })
  return response.data
}

export async function listLabQuests(
  projectId: string,
  options?: LabRequestOptions
): Promise<LabListResponse<LabQuest>> {
  if (await shouldUseLocalQuestLab(projectId)) {
    const summary = await loadLocalQuestSummary(projectId)
    const branches = await loadLocalQuestBranches(projectId)
    return { items: [mapQuestSummaryToLabQuest(summary, branches)] }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/quests`, buildLabRequestConfig(options))
    return response.data ?? { items: [] }
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    const summary = await loadLocalQuestSummary(projectId)
    const branches = await loadLocalQuestBranches(projectId)
    return { items: [mapQuestSummaryToLabQuest(summary, branches)] }
  }
}

export async function getLabQuest(
  projectId: string,
  questId: string,
  options?: LabRequestOptions
): Promise<{ quest: LabQuest; nodes: LabQuestNode[]; blockers?: { count: number } }> {
  if (await shouldUseLocalQuestLab(projectId)) {
    const summary = await loadLocalQuestSummary(projectId)
    const branches = await loadLocalQuestBranches(projectId)
    return {
      quest: mapQuestSummaryToLabQuest(summary, branches),
      nodes: buildLocalQuestNodes(summary),
      blockers: { count: summary.pending_decisions?.length ?? 0 },
    }
  }
  try {
    const response = await apiClient.get(
      `${LAB_BASE(projectId)}/quests/${questId}`,
      buildLabRequestConfig(options)
    )
    return response.data
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    const summary = await loadLocalQuestSummary(projectId)
    const branches = await loadLocalQuestBranches(projectId)
    const nodes = buildLocalQuestNodes(summary)
    return {
      quest: mapQuestSummaryToLabQuest(summary, branches),
      nodes,
      blockers: { count: summary.pending_decisions?.length ?? 0 },
    }
  }
}

export async function getLabQuestGithubPushStatus(
  projectId: string,
  questId: string
): Promise<LabQuestGithubPushStatus> {
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/github-push/status`)
    return response.data
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    return {
      configured: false,
      prerequisites: {
        cli_server_bound: true,
        cli_server_online: true,
        cli_server_remote: false,
        github_identity_bound: false,
        github_push_authorized: false,
        repo_bound: false,
      },
      disabled_reason: 'Local quest mode keeps GitHub push disabled by default.',
      binding: null,
    }
  }
}

export async function bindLabQuestGithubPushRepo(
  projectId: string,
  questId: string,
  payload: {
    installation_id?: string
    repo_owner?: string
    repo_name?: string
    create_if_missing?: boolean
    private_repo?: boolean
  }
): Promise<LabQuestGithubPushStatus> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/quests/${questId}/github-push/bind-repo`, payload)
  return response.data
}

export async function updateLabQuestGithubPushConfig(
  projectId: string,
  questId: string,
  payload: { auto_push_desired_enabled: boolean }
): Promise<LabQuestGithubPushStatus> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/quests/${questId}/github-push/config`, payload)
  return response.data
}

export async function createLabQuest(
  projectId: string,
  payload: {
    title: string
    description: string
    tags?: string[]
    baseline_root_id?: string
    node_schema_json?: Record<string, unknown>
    research_contract?: Record<string, unknown>
  }
): Promise<{ quest: LabQuest; nodes: LabQuestNode[] }> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/quests`, payload)
  return response.data
}

export async function startLabQuestResearch(
  projectId: string,
  payload: {
    quest_id?: string
    cli_server_id: string
    title?: string
    description?: string
    baseline_root_id?: string
    research_contract?: Record<string, unknown>
    runtime_profile?: {
      model?: string
      base_url?: string
      api_key?: string
      async_generation?: boolean
      batch_size?: number
      user_language?: string
    }
    kickoff_prompt: string
    pi_agent?: {
      template_key: string
      agent_id?: string
      request_id?: string
      agent_instance_id?: string
      display_name?: string
      profile_json?: Record<string, unknown>
      stats_json?: Record<string, unknown>
      avatar_frame_color?: string
    }
    github_push?: LabStartResearchGithubPushPayload
    reuse_existing_pi?: boolean
  }
): Promise<LabStartResearchResponse> {
  try {
    const response = await apiClient.post(`${LAB_BASE(projectId)}/research/start`, payload)
    return response.data
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    const summary = await loadLocalQuestSummary(projectId)
    const branches = await loadLocalQuestBranches(projectId)
    return {
      quest: mapQuestSummaryToLabQuest(summary, branches),
      pi_agent: mapQuestSummaryToLabAgent(summary),
      direct_session_id: `quest:${summary.quest_id}`,
      kickoff_queued: false,
      kickoff_started: false,
      kickoff_dispatch_mode: 'local-reuse',
      quest_created: false,
      pi_created: false,
      github_push: {
        enabled: false,
        mode: 'local_only',
      },
      warnings: ['Local DeepScientist workspace reuses the current quest repository.'],
    }
  }
}

export async function updateLabQuest(
  projectId: string,
  questId: string,
  payload: {
    title?: string
    description?: string
    baseline_root_id?: string | null
    node_schema_json?: Record<string, unknown>
    research_contract?: Record<string, unknown>
  }
): Promise<{ quest: LabQuest }> {
  const response = await apiClient.patch(`${LAB_BASE(projectId)}/quests/${questId}`, payload)
  return response.data
}

export async function bindLabQuestBaseline(
  projectId: string,
  questId: string,
  payload: { baseline_root_id: string }
): Promise<{ quest: LabQuest; nodes: LabQuestNode[]; blockers: { count: number }; binding_action: string }> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/quests/${questId}/baseline-binding`, payload)
  return response.data
}

export async function unbindLabQuestBaseline(
  projectId: string,
  questId: string
): Promise<{ quest: LabQuest; nodes: LabQuestNode[]; blockers: { count: number }; binding_action: string }> {
  const response = await apiClient.delete(`${LAB_BASE(projectId)}/quests/${questId}/baseline-binding`)
  return response.data
}

export async function deleteLabQuest(
  projectId: string,
  questId: string
): Promise<LabQuestDeleteResponse> {
  const response = await apiClient.delete(`${LAB_BASE(projectId)}/quests/${questId}`)
  return response.data
}

export async function updateLabQuestNode(
  projectId: string,
  nodeId: string,
  payload: { status: string }
): Promise<{ node: LabQuestNode }> {
  const response = await apiClient.patch(`${LAB_BASE(projectId)}/quest-nodes/${nodeId}`, payload)
  return response.data
}

export async function getLabQuestGraph(
  projectId: string,
  questId: string,
  params?: { view?: 'branch' | 'event' | 'stage'; search?: string; atEventId?: string | null }
): Promise<LabQuestGraphResponse> {
  if (isDemoProjectId(projectId)) {
    const payload = getDemoLabQuestGraph(projectId, { view: params?.view })
    if (!payload) {
      throw new Error(`Unknown demo graph for ${projectId}`)
    }
    const layout = getDemoLabLayout(projectId)
    return {
      ...payload,
      layout_json: layout?.layout_json ?? payload.layout_json ?? null,
    }
  }
  if (await shouldUseLocalQuestLab(projectId)) {
    const requestedView = params?.view ?? 'branch'
    const [summary, branches, layoutState, nodeTraces] = await Promise.all([
      loadLocalQuestSummary(projectId),
      loadLocalQuestBranches(projectId),
      loadLocalQuestLayout(projectId),
      requestedView === 'branch' ? Promise.resolve(null) : loadLocalQuestNodeTraces(projectId),
    ])
    return buildLocalQuestGraphResponse(
      summary,
      branches,
      params,
      nodeTraces,
      (layoutState?.layout_json as Record<string, unknown> | null) ?? null
    )
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/graph`, {
      params: {
        view: params?.view ?? undefined,
        search: params?.search ?? undefined,
        at_event_id: params?.atEventId ?? undefined,
      },
    })
    return response.data
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    const [summary, branches, layoutState] = await Promise.all([
      loadLocalQuestSummary(projectId),
      loadLocalQuestBranches(projectId),
      loadLocalQuestLayout(projectId),
    ])
    const branchNodes = buildLocalBranchGraphNodes(summary, branches, new Map())
    const branchEdges = buildLocalBranchGraphEdges(summary, branchNodes, branches)
    return {
      view: params?.view ?? 'branch',
      nodes: branchNodes,
      edges: branchEdges,
      head_branch: summary.branch || 'main',
      projection_status: branches?.projection_status ?? null,
      layout_json: (layoutState?.layout_json as Record<string, unknown> | null) ?? null,
      metric_catalog: buildGraphMetricCatalogFromNodes(branchNodes),
      governance_vm: buildLocalGovernanceVm(summary, branches),
      overlay_actions: [],
    }
  }
}

export async function listLabQuestNodeTraces(
  projectId: string,
  questId: string,
  params?: { selectionType?: string | null }
): Promise<LabQuestNodeTraceListResponse> {
  if (await shouldUseLocalQuestLab(projectId)) {
    const response = await loadLocalQuestNodeTraces(projectId)
    return {
      quest_id: questId,
      items: (response?.items ?? []).filter((trace) =>
        params?.selectionType ? trace.selection_type === params.selectionType : true
      ),
      generated_at: response?.generated_at ?? null,
      materialized_path: response?.materialized_path ?? null,
    }
  }
  const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/node-traces`, {
    params: {
      selection_type: params?.selectionType ?? undefined,
    },
  })
  return response.data ?? { quest_id: questId, items: [] }
}

export async function getLabQuestNodeTrace(
  projectId: string,
  questId: string,
  selectionRef: string,
  params?: { selectionType?: string | null }
): Promise<LabQuestNodeTraceResponse> {
  if (await shouldUseLocalQuestLab(projectId)) {
    const response = await loadLocalQuestNodeTraces(projectId)
    const trace =
      (response?.items ?? []).find((item) => {
        if (item.selection_ref !== selectionRef) return false
        return params?.selectionType ? item.selection_type === params.selectionType : true
      }) ?? null
    if (!trace) {
      throw new Error(`Unknown node trace \`${selectionRef}\`.`)
    }
    return {
      quest_id: questId,
      generated_at: response?.generated_at ?? null,
      materialized_path: response?.materialized_path ?? null,
      trace,
    }
  }
  const response = await apiClient.get(
    `${LAB_BASE(projectId)}/quests/${questId}/node-traces/${encodeURIComponent(selectionRef)}`,
    {
      params: {
        selection_type: params?.selectionType ?? undefined,
      },
    }
  )
  return response.data
}

export async function listLabQuestGraphActions(
  projectId: string,
  questId: string
): Promise<LabQuestGraphActionListResponse> {
  if (await shouldUseLocalQuestLab(projectId)) {
    return { items: [] }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/graph-actions`)
    return response.data ?? { items: [] }
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    return { items: [] }
  }
}

export async function createLabQuestGraphAction(
  projectId: string,
  questId: string,
  payload: {
    action_type: string
    status?: string
    selection_ref: string
    branch_name?: string | null
    target_agent_instance_ids?: string[]
    payload?: Record<string, unknown>
    selection_context?: LabQuestSelectionContext | null
    user_prompt?: string | null
    generated_prompt?: string | null
  }
): Promise<LabQuestGraphActionResponse> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/quests/${questId}/graph-actions`, payload)
  return response.data
}

export async function updateLabQuestGraphAction(
  projectId: string,
  questId: string,
  actionId: string,
  payload: {
    status?: string
    generated_prompt?: string | null
    payload?: Record<string, unknown>
  }
): Promise<LabQuestGraphActionResponse> {
  const response = await apiClient.patch(
    `${LAB_BASE(projectId)}/quests/${questId}/graph-actions/${actionId}`,
    payload
  )
  return response.data
}

export async function getLabQuestSummary(
  projectId: string,
  questId: string,
  params?: { atEventId?: string | null }
): Promise<LabQuestSummaryResponse> {
  if (await shouldUseLocalQuestLab(projectId)) {
    const summary = await loadLocalQuestSummary(projectId)
    const branches = await loadLocalQuestBranches(projectId)
    return {
      quest: buildLocalGovernanceVm(summary, branches),
    }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/summary`, {
      params: {
        at_event_id: params?.atEventId ?? undefined,
      },
    })
    return response.data
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    const summary = await loadLocalQuestSummary(projectId)
    const branches = await loadLocalQuestBranches(projectId)
    return {
      quest: buildLocalGovernanceVm(summary, branches),
    }
  }
}

export async function getLabQuestTimeline(
  projectId: string,
  questId: string,
  params?: { limit?: number }
): Promise<LabQuestTimelineResponse> {
  if (await shouldUseLocalQuestLab(projectId)) {
    const workflow = await loadLocalQuestWorkflow(projectId)
    const limit = Math.max(1, params?.limit ?? 80)
    return {
      items: (workflow?.entries ?? [])
        .map(mapWorkflowEntryToTimeline)
        .sort((left, right) => String(right.created_at || '').localeCompare(String(left.created_at || '')))
        .slice(0, limit),
    }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/timeline`, {
      params: {
        limit: params?.limit ?? undefined,
      },
    })
    return response.data ?? { items: [] }
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    const workflow = await loadLocalQuestWorkflow(projectId)
    const limit = Math.max(1, params?.limit ?? 80)
    return {
      items: (workflow?.entries ?? [])
        .map(mapWorkflowEntryToTimeline)
        .sort((left, right) => String(right.created_at || '').localeCompare(String(left.created_at || '')))
        .slice(0, limit),
    }
  }
}

export async function getLabQuestCompare(
  projectId: string,
  questId: string,
  params?: { selectedBranch?: string | null; atEventId?: string | null }
): Promise<LabQuestCompareResponse> {
  if (await shouldUseLocalQuestLab(projectId)) {
    const summary = await loadLocalQuestSummary(projectId)
    const branches = await loadLocalQuestBranches(projectId)
    const selectedBranch = params?.selectedBranch || summary.branch || branches?.current_ref || 'main'
    const selectedNode = branches?.nodes?.find((node) => node.ref === selectedBranch) ?? null
    const baseBranch = selectedNode?.compare_base || selectedNode?.parent_ref || branches?.default_ref || 'main'
    let compare: GitComparePayload | null = null
    try {
      compare = await questClient.gitCompare(projectId, baseBranch, selectedBranch)
    } catch {
      compare = null
    }
    return {
      baseline_branch: baseBranch,
      head_branch: summary.branch || selectedBranch,
      selected_branch: selectedBranch,
      metric_table: latestMetrics(summary) ?? {},
      series: [],
      key_findings: summary.summary?.status_line ? [summary.summary.status_line] : [],
      git_diff:
        compare?.files?.map((file) => ({
          path: file.path,
          status: file.status,
          added: file.added,
          removed: file.removed,
        })) ?? [],
      artifact_diff: (summary.recent_artifacts || []).map((artifact) => ({
        kind: artifact.kind,
        summary: artifact.payload?.summary || artifact.payload?.reason || null,
        status: artifact.payload?.status || null,
      })),
    }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/compare`, {
      params: {
        selected_branch: params?.selectedBranch ?? undefined,
        at_event_id: params?.atEventId ?? undefined,
      },
    })
    return response.data ?? {
      metric_table: {},
      series: [],
      key_findings: [],
      git_diff: [],
      artifact_diff: [],
    }
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    const summary = await loadLocalQuestSummary(projectId)
    const branches = await loadLocalQuestBranches(projectId)
    const selectedBranch = params?.selectedBranch || summary.branch || branches?.current_ref || 'main'
    const selectedNode = branches?.nodes?.find((node) => node.ref === selectedBranch) ?? null
    const baseBranch = selectedNode?.compare_base || selectedNode?.parent_ref || branches?.default_ref || 'main'
    let compare: GitComparePayload | null = null
    try {
      compare = await questClient.gitCompare(projectId, baseBranch, selectedBranch)
    } catch {
      compare = null
    }
    return {
      baseline_branch: baseBranch,
      head_branch: summary.branch || selectedBranch,
      selected_branch: selectedBranch,
      metric_table: latestMetrics(summary) ?? {},
      series: [],
      key_findings: summary.summary?.status_line ? [summary.summary.status_line] : [],
      git_diff:
        compare?.files?.map((file) => ({
          path: file.path,
          status: file.status,
          added: file.added,
          removed: file.removed,
        })) ?? [],
      artifact_diff: (summary.recent_artifacts || []).map((artifact) => ({
        kind: artifact.kind,
        summary: artifact.payload?.summary || artifact.payload?.reason || null,
        status: artifact.payload?.status || null,
      })),
    }
  }
}

export async function getLabQuestRunAudit(
  projectId: string,
  questId: string,
  runId: string,
  params?: { atEventId?: string | null }
): Promise<LabQuestRunAuditResponse> {
  const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/runs/${encodeURIComponent(runId)}/audit`, {
    params: {
      at_event_id: params?.atEventId ?? undefined,
    },
  })
  return response.data
}

export async function getLabQuestBranchAudit(
  projectId: string,
  questId: string,
  branchName: string,
  params?: { atEventId?: string | null }
): Promise<LabQuestBranchAuditResponse> {
  if (await shouldUseLocalQuestLab(projectId)) {
    const summary = await loadLocalQuestSummary(projectId)
    const branches = await loadLocalQuestBranches(projectId)
    const selectedNode = branches?.nodes?.find((node) => node.ref === branchName) ?? null
    const baseBranch = selectedNode?.compare_base || selectedNode?.parent_ref || branches?.default_ref || 'main'
    let compare: GitComparePayload | null = null
    try {
      compare = await questClient.gitCompare(projectId, baseBranch, branchName)
    } catch {
      compare = null
    }
    return {
      quest_id: questId,
      branch_name: branchName,
      head_branch: summary.branch || branchName,
      parent_branch: selectedNode?.parent_ref || baseBranch,
      latest_commit: selectedNode?.head || summary.head || null,
      stage: selectedNode?.run_kind ? resolveStageKey(selectedNode.run_kind) : resolveStageKey(summary.active_anchor),
      audit_level: 'local',
      branch_summary: {
        title: selectedNode?.label || branchName,
        status_line: summary.summary?.status_line || null,
      },
      idea: {
        idea_id: selectedNode?.idea_id || null,
        summary: selectedNode?.latest_summary || null,
      },
      diff: {
        base: baseBranch,
        head: branchName,
        file_count: compare?.file_count ?? 0,
        commit_count: compare?.commit_count ?? 0,
      },
      experiments: (summary.recent_runs || []).map((run) => ({
        run_id: run.run_id,
        status: run.status,
        summary: run.summary,
      })),
      decisions: (summary.pending_decisions || []).map((decision) => ({
        decision,
        status: 'pending',
      })),
      related_memory: [],
      claim_map_path: null,
      bundle_manifest_path: null,
      compare_context: {
        selected_branch: branchName,
        base_branch: baseBranch,
      },
    }
  }
  try {
    const response = await apiClient.get(
      `${LAB_BASE(projectId)}/quests/${questId}/branches/${encodeURIComponent(branchName)}/audit`,
      {
        params: {
          at_event_id: params?.atEventId ?? undefined,
        },
      }
    )
    return response.data
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    const summary = await loadLocalQuestSummary(projectId)
    const branches = await loadLocalQuestBranches(projectId)
    const selectedNode = branches?.nodes?.find((node) => node.ref === branchName) ?? null
    const baseBranch = selectedNode?.compare_base || selectedNode?.parent_ref || branches?.default_ref || 'main'
    let compare: GitComparePayload | null = null
    try {
      compare = await questClient.gitCompare(projectId, baseBranch, branchName)
    } catch {
      compare = null
    }
    return {
      quest_id: questId,
      branch_name: branchName,
      head_branch: summary.branch || branchName,
      parent_branch: selectedNode?.parent_ref || baseBranch,
      latest_commit: selectedNode?.head || summary.head || null,
      stage: selectedNode?.run_kind ? resolveStageKey(selectedNode.run_kind) : resolveStageKey(summary.active_anchor),
      audit_level: 'local',
      branch_summary: {
        title: selectedNode?.label || branchName,
        status_line: summary.summary?.status_line || null,
      },
      idea: {
        idea_id: selectedNode?.idea_id || null,
        summary: selectedNode?.latest_summary || null,
      },
      diff: {
        base: baseBranch,
        head: branchName,
        file_count: compare?.file_count ?? 0,
        commit_count: compare?.commit_count ?? 0,
      },
      experiments: (summary.recent_runs || []).map((run) => ({
        run_id: run.run_id,
        status: run.status,
        summary: run.summary,
      })),
      decisions: (summary.pending_decisions || []).map((decision) => ({
        decision,
        status: 'pending',
      })),
      related_memory: [],
      claim_map_path: null,
      bundle_manifest_path: null,
      compare_context: {
        selected_branch: branchName,
        base_branch: baseBranch,
      },
    }
  }
}

export async function createLabQuestAgentGroupMessage(
  projectId: string,
  questId: string,
  payload: {
    message_id?: string
    author_agent_instance_id: string
    target_agent_instance_ids: string[]
    content: string
    quote_message_id?: string | null
    proposal_id?: string | null
    selection_context?: LabQuestSelectionContext | null
    await_answer?: boolean
    message_kind?: string | null
    branch_name?: string | null
  }
): Promise<LabQuestAgentGroupMessageCreateResponse> {
  const response = await apiClient.post(
    `${LAB_BASE(projectId)}/quests/${questId}/group/agent-messages`,
    payload
  )
  return response.data
}

export async function getLabQuestDiff(
  projectId: string,
  questId: string,
  params?: { base?: string; branch?: string; cursor?: number; limitFiles?: number }
): Promise<LabQuestDiffResponse> {
  const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/diff`, {
    params: {
      base: params?.base ?? undefined,
      branch: params?.branch ?? undefined,
      cursor: params?.cursor ?? undefined,
      limit_files: params?.limitFiles ?? undefined,
    },
  })
  return response.data
}

export async function getLabQuestDiffFile(
  projectId: string,
  questId: string,
  params: {
    base?: string
    branch?: string
    path: string
    hunkCursor?: number
    hunkLimit?: number
    context?: number
    includeContents?: boolean
  }
): Promise<LabQuestDiffFileResponse> {
  const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/diff/file`, {
    params: {
      base: params.base ?? undefined,
      branch: params.branch ?? undefined,
      path: params.path,
      hunk_cursor: params.hunkCursor ?? undefined,
      hunk_limit: params.hunkLimit ?? undefined,
      context: params.context ?? undefined,
      include_contents: params.includeContents ?? undefined,
    },
  })
  return response.data
}

export async function getLabQuestGitFile(
  projectId: string,
  questId: string,
  params: { path: string; ref?: string; maxBytes?: number }
): Promise<LabQuestGitFileResponse> {
  const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/git/file`, {
    params: {
      path: params.path,
      ref: params.ref ?? undefined,
      max_bytes: params.maxBytes ?? undefined,
    },
  })
  return response.data
}

export async function getLabQuestGitCommits(
  projectId: string,
  questId: string,
  params?: { ref?: string; cursor?: number; limit?: number }
): Promise<LabQuestGitCommitListResponse> {
  const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/git/commits`, {
    params: {
      ref: params?.ref ?? undefined,
      cursor: params?.cursor ?? undefined,
      limit: params?.limit ?? undefined,
    },
  })
  return response.data
}

export async function mergeLabQuestGitBranch(
  projectId: string,
  questId: string,
  payload: LabQuestGitMergeRequest
): Promise<LabQuestGitMergeResponse> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/quests/${questId}/git/merge`, payload)
  return response.data
}

export async function revertLabQuestGitCommit(
  projectId: string,
  questId: string,
  payload: LabQuestGitRevertRequest
): Promise<LabQuestGitRevertResponse> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/quests/${questId}/git/revert`, payload)
  return response.data
}

export async function exportLabQuestGitBundle(
  projectId: string,
  questId: string,
  payload: LabQuestGitBundleExportRequest
): Promise<LabQuestGitBundleExportResponse> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/quests/${questId}/git/export-bundle`, payload)
  return response.data
}

export async function restoreLabQuestGitBundle(
  projectId: string,
  questId: string,
  payload: LabQuestGitBundleRestoreRequest
): Promise<LabQuestGitBundleRestoreResponse> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/quests/${questId}/git/restore-bundle`, payload)
  return response.data
}

export async function reconcileLabQuestGitBranch(
  projectId: string,
  questId: string,
  payload: LabQuestGitReconcileRequest
): Promise<LabQuestGitReconcileResponse> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/quests/${questId}/git/reconcile`, payload)
  return response.data
}

export async function listLabQuestGitIncidents(
  projectId: string,
  questId: string
): Promise<LabQuestGitIncidentListResponse> {
  const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/git-incidents`)
  return response.data
}

export async function listLabQuestWorktreeLeases(
  projectId: string,
  questId: string
): Promise<LabQuestWorktreeLeaseListResponse> {
  const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/worktree-leases`)
  return response.data
}

export async function listLabQuestGitExports(
  projectId: string,
  questId: string
): Promise<LabQuestGitExportListResponse> {
  const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/git-exports`)
  return response.data
}

export async function listLabQuestGitReconciliations(
  projectId: string,
  questId: string
): Promise<LabQuestGitReconciliationListResponse> {
  const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/git-reconciliations`)
  return response.data
}

export async function listLabQuestEvents(
  projectId: string,
  questId: string,
  params?: {
    branch?: string
    eventIds?: string[]
    eventTypes?: string[]
    eventPrefixes?: string[]
    atEventId?: string | null
    cursor?: string
    limit?: number
    includePayload?: boolean
    }
  ): Promise<LabQuestEventListResponse> {
  if (isDemoProjectId(projectId)) {
    const payload = listDemoLabQuestEvents(projectId, { limit: params?.limit })
    if (!payload) {
      throw new Error(`Unknown demo quest events for ${projectId}`)
    }
    return payload
  }
  if (await shouldUseLocalQuestLab(projectId)) {
    const summary = await loadLocalQuestSummary(projectId)
    const artifacts = await loadLocalQuestArtifacts(projectId)
    const rawEvents = await loadLocalQuestEvents(projectId)
    const artifactPayloadById = new Map<string, Record<string, unknown>>()
    ;(artifacts?.items || []).forEach((item) => {
      const payload = asRecordValue(item.payload)
      const artifactId = asStringValue(payload?.artifact_id) || asStringValue(payload?.id)
      if (payload && artifactId) {
        artifactPayloadById.set(artifactId, payload)
      }
    })
    const sourceEvents = [...(rawEvents?.events || [])]
    const cutoffIndex = params?.atEventId
      ? sourceEvents.findIndex((event) => event.event_id === params.atEventId)
      : -1
    const boundedEvents =
      cutoffIndex >= 0 ? sourceEvents.slice(0, cutoffIndex + 1) : sourceEvents
    const items = boundedEvents
      .filter(isDisplayableQuestEvent)
      .map((event) => {
        const artifactPayload = artifactPayloadById.get(extractArtifactIdFromRawEvent(event) || '')
        return mapRawEventToQuestEvent(event, artifactPayload, Boolean(params?.includePayload), summary.active_anchor)
      })
      .filter((event) => (params?.branch ? (event.branch_name || 'main') === params.branch : true))
      .filter((event) => (params?.eventIds?.length ? params.eventIds.includes(event.event_id) : true))
      .filter((event) => (params?.eventTypes?.length ? params.eventTypes.includes(event.event_type) : true))
      .filter((event) =>
        params?.eventPrefixes?.length
          ? params.eventPrefixes.some((prefix) => event.event_type.startsWith(prefix))
          : true
      )
    return {
      items: items
        .sort((left, right) => String(right.created_at || '').localeCompare(String(left.created_at || '')))
        .slice(0, Math.max(1, params?.limit ?? 80)),
      next_cursor: null,
      has_more: false,
    }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/events`, {
      params: {
        branch: params?.branch ?? undefined,
        event_ids: params?.eventIds?.length ? params.eventIds.join(',') : undefined,
        event_types: params?.eventTypes?.length ? params.eventTypes.join(',') : undefined,
        event_prefixes: params?.eventPrefixes?.length ? params.eventPrefixes.join(',') : undefined,
        at_event_id: params?.atEventId ?? undefined,
        cursor: params?.cursor ?? undefined,
        limit: params?.limit ?? undefined,
        include_payload: params?.includePayload ?? undefined,
      },
    })
    return response.data
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    const summary = await loadLocalQuestSummary(projectId)
    const artifacts = await loadLocalQuestArtifacts(projectId)
    const rawEvents = await loadLocalQuestEvents(projectId)
    const artifactPayloadById = new Map<string, Record<string, unknown>>()
    ;(artifacts?.items || []).forEach((item) => {
      const payload = asRecordValue(item.payload)
      const artifactId = asStringValue(payload?.artifact_id) || asStringValue(payload?.id)
      if (payload && artifactId) {
        artifactPayloadById.set(artifactId, payload)
      }
    })
    const items = (rawEvents?.events || [])
      .filter(isDisplayableQuestEvent)
      .map((event) =>
        mapRawEventToQuestEvent(
          event,
          artifactPayloadById.get(extractArtifactIdFromRawEvent(event) || '') || null,
          Boolean(params?.includePayload),
          summary.active_anchor
        )
      )
      .filter((event) => (params?.branch ? (event.branch_name || 'main') === params.branch : true))
      .filter((event) => (params?.eventIds?.length ? params.eventIds.includes(event.event_id) : true))
      .filter((event) => (params?.eventTypes?.length ? params.eventTypes.includes(event.event_type) : true))
      .filter((event) =>
        params?.eventPrefixes?.length
          ? params.eventPrefixes.some((prefix) => event.event_type.startsWith(prefix))
          : true
      )
    return {
      items: items
        .sort((left, right) => String(right.created_at || '').localeCompare(String(left.created_at || '')))
        .slice(0, Math.max(1, params?.limit ?? 80)),
      next_cursor: null,
      has_more: false,
    }
  }
}

export async function searchLabQuest(
  projectId: string,
  questId: string,
  params?: { query?: string; types?: string; limit?: number; cursor?: string }
): Promise<LabQuestSearchResponse> {
  if (await shouldUseLocalQuestLab(projectId)) {
    const query = String(params?.query || '').trim().toLowerCase()
    const limit = Math.max(1, Math.min(100, params?.limit ?? 20))
    const summary = await loadLocalQuestSummary(projectId)
    const branches = await loadLocalQuestBranches(projectId)
    const events = await listLabQuestEvents(projectId, questId, {
      limit: Math.max(80, limit * 4),
      includePayload: false,
    })
    const branchItems = (branches?.nodes ?? [buildFallbackGraphNode(summary)])
      .filter((branch) => {
        if (!query) return true
        const haystack = [
          branch.branch_name,
          branch.target_label,
          branch.status,
          branch.verdict,
          branch.node_summary?.last_reply,
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase()
        return haystack.includes(query)
      })
      .map((branch) => ({ item_type: 'branch' as const, branch, event: null }))
    const eventItems = (events.items ?? [])
      .filter((entry) => {
        if (!query) return true
        const haystack = [entry.event_type, entry.payload_summary, entry.reply_to_pi, entry.stage_key]
          .filter(Boolean)
          .join(' ')
          .toLowerCase()
        return haystack.includes(query)
      })
      .map((entry) => ({ item_type: 'event' as const, event: entry, branch: null }))
    const items = [...branchItems, ...eventItems].slice(0, limit)
    return {
      items,
      next_cursor: null,
      has_more: false,
      total_estimate: items.length,
    }
  }
  const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/search`, {
    params: {
      q: params?.query ?? undefined,
      types: params?.types ?? undefined,
      limit: params?.limit ?? undefined,
      cursor: params?.cursor ?? undefined,
    },
  })
  return response.data
}

export async function getLabQuestEventPayload(
  projectId: string,
  questId: string,
  eventId: string,
  params?: { source?: string; maxBytes?: number }
): Promise<LabQuestEventPayloadResponse> {
  if (await shouldUseLocalQuestLab(projectId)) {
    const artifacts = await loadLocalQuestArtifacts(projectId)
    const rawEvents = await loadLocalQuestEvents(projectId)
    const artifactPayloadById = new Map<string, Record<string, unknown>>()
    ;(artifacts?.items || []).forEach((item) => {
      const payload = asRecordValue(item.payload)
      const artifactId = asStringValue(payload?.artifact_id) || asStringValue(payload?.id)
      if (payload && artifactId) {
        artifactPayloadById.set(artifactId, payload)
      }
    })
    const matched = (rawEvents?.events || []).find((entry) => entry.event_id === eventId)
    const artifactPayload = matched ? artifactPayloadById.get(extractArtifactIdFromRawEvent(matched) || '') : null
    return {
      event_id: eventId,
      payload_json: matched ? buildEventPayloadEnvelope(matched, artifactPayload || null) : null,
      payload_hash: null,
      payload_path: null,
      truncated: false,
      source: params?.source ?? 'local-events',
      available: Boolean(matched),
    }
  }
  const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/events/${eventId}/payload`, {
    params: {
      source: params?.source ?? undefined,
      max_bytes: params?.maxBytes ?? undefined,
    },
  })
  return response.data
}

export async function getLabQuestSnapshot(
  projectId: string,
  questId: string
): Promise<LabQuestSnapshotResponse> {
  if (await shouldUseLocalQuestLab(projectId)) {
    const summary = await loadLocalQuestSummary(projectId)
    const workflow = await loadLocalQuestWorkflow(projectId)
    const recentEntries = (workflow?.entries ?? []).slice(-6).reverse()
    const snapshotMd = [
      `# ${summary.title || questId}`,
      '',
      `- Quest ID: \`${summary.quest_id}\``,
      `- Branch: \`${summary.branch || 'main'}\``,
      `- Status: ${summary.status || 'idle'}`,
      `- Updated: ${normalizeTimestamp(summary.updated_at)}`,
      summary.summary?.status_line ? `- Summary: ${summary.summary.status_line}` : null,
      '',
      '## Recent Activity',
      recentEntries.length
        ? recentEntries
            .map(
              (entry) =>
                `- ${entry.title || entry.raw_event_type || entry.kind} — ${entry.summary || entry.status || 'no summary'}`
            )
            .join('\n')
        : '- No workflow events yet.',
    ]
      .filter(Boolean)
      .join('\n')
    return {
      snapshot_md: snapshotMd,
      source: 'local-summary',
    }
  }
  const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/snapshot`)
  return response.data
}

export async function getLabQuestSyncStatus(
  projectId: string,
  questId: string
): Promise<LabQuestSyncStatus> {
  if (await shouldUseLocalQuestLab(projectId)) {
    const summary = await loadLocalQuestSummary(projectId)
    const workflow = await loadLocalQuestWorkflow(projectId)
    const lastEntry = workflow?.entries?.[workflow.entries.length - 1]
    return {
      quest_id: questId,
      events_total: workflow?.entries?.length ?? 0,
      last_event_id: lastEntry?.id ?? null,
      last_event_commit: summary.head || null,
      cli_server_id: `local:${projectId}`,
      pi_state: summary.status || null,
      runtime: {
        branch: summary.branch || 'main',
      },
    }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/sync/status`)
    return response.data
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    const summary = await loadLocalQuestSummary(projectId)
    const workflow = await loadLocalQuestWorkflow(projectId)
    const lastEntry = workflow?.entries?.[workflow.entries.length - 1]
    return {
      quest_id: questId,
      events_total: workflow?.entries?.length ?? 0,
      last_event_id: lastEntry?.id ?? null,
      last_event_commit: summary.head || null,
      cli_server_id: `local:${projectId}`,
      pi_state: summary.status || null,
      runtime: {
        branch: summary.branch || 'main',
      },
    }
  }
}

export async function getLabQuestRuntime(
  projectId: string,
  questId: string
): Promise<LabQuestRuntimeResponse> {
  if (await shouldUseLocalQuestLab(projectId)) {
    const summary = await loadLocalQuestSummary(projectId)
    const working = normalizeLabWorkingStatus(summary.status) === 'working'
    return {
      quest_id: questId,
      runtime: {
        runningAgents: working ? 1 : 0,
        runningPiAgents: working ? 1 : 0,
        runningWorkerAgents: 0,
        lastHeartbeatAt: normalizeTimestamp(summary.updated_at),
        piState: summary.status || 'idle',
        parallelLimit: 1,
        activeSlots: working ? 1 : 0,
      },
    }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/runtime`)
    return response.data
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    const summary = await loadLocalQuestSummary(projectId)
    const working = normalizeLabWorkingStatus(summary.status) === 'working'
    return {
      quest_id: questId,
      runtime: {
        runningAgents: working ? 1 : 0,
        runningPiAgents: working ? 1 : 0,
        runningWorkerAgents: 0,
        lastHeartbeatAt: normalizeTimestamp(summary.updated_at),
        piState: summary.status || 'idle',
        parallelLimit: 1,
        activeSlots: working ? 1 : 0,
        availableSlots: working ? 0 : 1,
        blockedReasons: summary.pending_decisions?.length ? ['pending_decision'] : [],
        cliStatus: 'online',
        cliLastSeenAt: normalizeTimestamp(summary.updated_at),
      },
      scheduler: {
        parallel_limit: 1,
        active_slots: working ? 1 : 0,
        available_slots: working ? 0 : 1,
        blocked_reasons: summary.pending_decisions?.length ? ['pending_decision'] : [],
      },
      active_runs: (summary.recent_runs || [])
        .filter((run) => normalizeLabWorkingStatus(run.status) === 'working')
        .map((run) => ({
          run_id: run.run_id || `run:${questId}`,
          session_id: `quest:${questId}`,
          agent_id: `${questId}:pi`,
          agent_instance_id: `${questId}:pi`,
          template_key: 'principal-investigator',
          branch_name: summary.branch || 'main',
          stage_key: resolveStageKey(summary.active_anchor),
          status: run.status || 'running',
          pi_launched: true,
          role: 'lead',
          started_at: normalizeTimestamp(run.created_at),
          last_heartbeat_at: normalizeTimestamp(run.updated_at || run.created_at),
        })),
      routes: [
        {
          route_id: `route:${questId}:${summary.branch || 'main'}`,
          branch_name: summary.branch || 'main',
          worktree_rel_path: null,
          status: working ? 'active' : 'idle',
          parallel_group: null,
          active_run_count: working ? 1 : 0,
          stage_keys: [resolveStageKey(summary.active_anchor)],
          template_keys: ['principal-investigator'],
          agent_instance_ids: [`${questId}:pi`],
          session_ids: [`quest:${questId}`],
          last_heartbeat_at: normalizeTimestamp(summary.updated_at),
          blocked_reasons: summary.pending_decisions?.length ? ['pending_decision'] : [],
        },
      ],
      recent_commands: [],
      worktree_leases: [],
    }
  }
}

export async function getLabMemorySyncStatus(
  projectId: string,
  params?: { questId?: string | null; cliServerId?: string | null }
): Promise<LabMemorySyncStatus> {
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/memory/sync/status`, {
      params: {
        quest_id: params?.questId ?? undefined,
        cli_server_id: params?.cliServerId ?? undefined,
      },
    })
    return response.data
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    return {
      pending_count: 0,
      failed_count: 0,
      last_error: null,
      last_synced_at: nowIso(),
      updated_at: nowIso(),
      cli_server_id: params?.cliServerId ?? `local:${projectId}`,
      cli_status: 'online',
      cli_last_seen_at: nowIso(),
    }
  }
}

export async function controlLabPi(
  projectId: string,
  questId: string,
  payload: LabPiControlRequest
): Promise<LabPiControlResponse> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/quests/${questId}/pi/control`, payload)
  return response.data
}

export async function updateLabQuestLayout(
  projectId: string,
  questId: string,
  layoutJson: Record<string, unknown>
): Promise<LabQuestLayoutResponse> {
  if (isDemoProjectId(projectId)) {
    return saveDemoLabLayout(projectId, layoutJson)
  }
  if (await shouldUseLocalQuestLab(projectId)) {
    return questClient.updateLayout(projectId, {
      layout_json: layoutJson,
    })
  }
  const response = await apiClient.post(`${LAB_BASE(projectId)}/quests/${questId}/layout`, {
    layout_json: layoutJson,
  })
  return response.data
}

export async function getLabQuestArtifact(
  projectId: string,
  questId: string,
  path: string
): Promise<LabQuestArtifactContent> {
  const response = await apiClient.get(`${LAB_BASE(projectId)}/quests/${questId}/artifacts`, {
    params: { path },
  })
  return response.data
}

export async function listLabBaselines(projectId: string): Promise<LabListResponse<LabBaseline>> {
  if (await shouldUseLocalQuestLab(projectId)) {
    try {
      const entries = await questClient.baselines()
      const items = (Array.isArray(entries) ? entries : []).map((entry) => ({
        baseline_root_id: entry.baseline_id,
        title: entry.summary ? `${entry.baseline_id} · ${entry.summary}` : entry.baseline_id,
        status: entry.status ?? null,
        last_reproduced_at: normalizeTimestamp(entry.updated_at || entry.created_at),
        archive_file_id: null,
      }))
      return { items }
    } catch {
      return { items: [] }
    }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/assets/baselines`)
    return response.data ?? { items: [] }
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    try {
      const entries = await questClient.baselines()
      const items = (Array.isArray(entries) ? entries : []).map((entry) => ({
        baseline_root_id: entry.baseline_id,
        title: entry.summary ? `${entry.baseline_id} · ${entry.summary}` : entry.baseline_id,
        status: entry.status ?? null,
        last_reproduced_at: normalizeTimestamp(entry.updated_at || entry.created_at),
        archive_file_id: null,
      }))
      return { items }
    } catch {
      return { items: [] }
    }
  }
}

export async function listLabPapers(
  projectId: string,
  params?: { questId?: string | null }
): Promise<LabListResponse<LabPaper>> {
  if (isDemoProjectId(projectId)) {
    return listDemoLabPapers(projectId) ?? { items: [] }
  }
  if (await shouldUseLocalQuestLab(projectId)) {
    return { items: [] }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/assets/papers`, {
      params: params?.questId ? { quest_id: params.questId } : undefined,
    })
    return response.data ?? { items: [] }
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    return { items: [] }
  }
}

export async function listLabBaselineResults(
  projectId: string,
  baselineId: string,
  params?: { cursor?: string; limit?: number }
): Promise<LabBaselineResultsResponse> {
  const response = await apiClient.get(`${LAB_BASE(projectId)}/assets/baselines/${baselineId}/results`, {
    params: {
      cursor: params?.cursor ?? undefined,
      limit: params?.limit ?? undefined,
    },
  })
  return response.data
}

export async function createLabBaselineFromAgent(
  projectId: string,
  payload: {
    agent_instance_id: string
    title?: string
    description?: string
    archive_source_path?: string
  }
): Promise<{ baseline_root_id: string }> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/assets/baselines/from-agent`, payload)
  return response.data
}

export async function archiveLabBaseline(
  projectId: string,
  baselineId: string
): Promise<{ archive_file_id: string }> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/assets/baselines/${baselineId}/archive`)
  return response.data
}

export async function restoreLabBaseline(
  projectId: string,
  baselineId: string,
  payload: { target_path: string; cli_server_id: string }
): Promise<{ restore_job_id: string }> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/assets/baselines/${baselineId}/restore`, payload)
  return response.data
}

export async function getLabOverview(projectId: string, options?: LabRequestOptions): Promise<LabOverview> {
  if (await shouldUseLocalQuestLab(projectId)) {
    const summary = await loadLocalQuestSummary(projectId)
    const branches = await loadLocalQuestBranches(projectId)
    return {
      agents: { total: 1 },
      quests: {
        active: normalizeLabWorkingStatus(summary.status) === 'done' ? 0 : 1,
        blocked: normalizeLabWorkingStatus(summary.status) === 'blocked' ? 1 : 0,
        completed: normalizeLabWorkingStatus(summary.status) === 'done' ? 1 : 0,
      },
      assets: {
        baselines: 1,
        papers: 0,
        branches: Math.max(1, branches?.nodes?.length ?? 1),
      },
      decisions: {
        pending: summary.pending_decisions?.length ?? 0,
      },
      achievements: { total: 0 },
    }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/overview`, buildLabRequestConfig(options))
    return response.data ?? {}
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    const summary = await loadLocalQuestSummary(projectId)
    const branches = await loadLocalQuestBranches(projectId)
    return {
      agents: { total: 1 },
      quests: {
        active: normalizeLabWorkingStatus(summary.status) === 'done' ? 0 : 1,
        blocked: normalizeLabWorkingStatus(summary.status) === 'blocked' ? 1 : 0,
        completed: normalizeLabWorkingStatus(summary.status) === 'done' ? 1 : 0,
      },
      assets: {
        baselines: 1,
        papers: 0,
      },
      achievements: { total: 0 },
      recent_activity: buildLocalRecentActivity(summary),
      github_push: {
        enabled: false,
        mode: 'local_only',
      },
      graph_vm: {
        project: {
          projectId,
          questCount: 1,
          pendingDecisionCount: summary.pending_decisions?.length ?? 0,
          runningBranchCount: normalizeLabWorkingStatus(summary.status) === 'working' ? 1 : 0,
          pushFailedCount: 0,
          writerConflictCount: 0,
        },
        quests: [buildLocalGovernanceVm(summary, branches)],
      },
    }
  }
}

export async function getLabGithubPushDefault(
  projectId: string,
  options?: LabRequestOptions
): Promise<LabGithubPushDefaultStatus> {
  if (await shouldUseLocalQuestLab(projectId)) {
    return {
      auto_push_default_enabled: false,
      github_identity_bound: false,
      github_push_authorized: false,
      bound_installation_id: null,
      repositories: [],
    } as LabGithubPushDefaultStatus
  }
  try {
    const response = await apiClient.get(
      `${LAB_BASE(projectId)}/github-push/default`,
      buildLabRequestConfig(options)
    )
    return response.data
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    return {
      auto_push_default_enabled: false,
      github_identity_bound: false,
      github_push_authorized: false,
      bound_installation_id: null,
      repositories: [],
    } as LabGithubPushDefaultStatus
  }
}

export async function updateLabGithubPushDefault(
  projectId: string,
  payload: { auto_push_default_enabled: boolean }
): Promise<LabGithubPushDefaultStatus> {
  const response = await apiClient.post(`${LAB_BASE(projectId)}/github-push/default`, payload)
  return response.data
}

export async function listLabPendingQuestions(
  projectId: string
): Promise<LabPendingQuestionListResponse> {
  if (await shouldUseLocalQuestLab(projectId)) {
    return { items: [], total: 0 }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/questions/pending`)
    return response.data ?? { items: [], total: 0 }
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    return { items: [], total: 0 }
  }
}

export async function listLabQuestionHistory(
  projectId: string,
  cursor?: string | null
): Promise<LabQuestionHistoryResponse> {
  if (await shouldUseLocalQuestLab(projectId)) {
    return { items: [], next_cursor: null }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/questions/history`, {
      params: { cursor: cursor ?? undefined },
    })
    return response.data ?? { items: [], next_cursor: null }
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    return { items: [], next_cursor: null }
  }
}

export async function listLabAchievements(projectId: string): Promise<LabListResponse<LabAchievement>> {
  if (await shouldUseLocalQuestLab(projectId)) {
    return { items: [] }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/achievements`)
    return response.data ?? { items: [] }
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    return { items: [] }
  }
}

export async function listLabMemory(
  projectId: string,
  params?: {
    kind?: string
    query?: string
    tags?: string[]
    questId?: string | null
    branchName?: string | null
    stageKey?: string | null
    originEventId?: string | null
    ideaId?: string | null
    runId?: string | null
    agentInstanceId?: string | null
    authorityLevel?: string | null
    reviewStatus?: string | null
    atEventId?: string | null
    limit?: number
  }
): Promise<LabMemoryListResponse> {
  const normalizedLimit =
    typeof params?.limit === 'number'
      ? Math.max(1, Math.min(100, Math.trunc(params.limit)))
      : undefined
  if (isDemoProjectId(projectId)) {
    const payload = listDemoLabMemory(projectId) ?? { items: [] }
    let items = payload.items
    if (params?.kind) {
      items = items.filter((item) => item.kind === params.kind)
    }
    if (params?.query) {
      const query = params.query.toLowerCase()
      items = items.filter((item) =>
        `${item.title || ''} ${item.summary || ''}`.toLowerCase().includes(query)
      )
    }
    if (params?.branchName) {
      items = items.filter((item) => item.branch_name === params.branchName)
    }
    if (params?.stageKey) {
      items = items.filter((item) => item.stage_key === params.stageKey)
    }
    return { items: items.slice(0, normalizedLimit ?? 50) }
  }
  if (await shouldUseLocalQuestLab(projectId)) {
    const cards = await questClient.memory(projectId)
    let items = cards.map(mapMemoryCardToEntry)
    if (params?.kind) {
      items = items.filter((item) => item.kind === params.kind)
    }
    if (params?.query) {
      const query = params.query.toLowerCase()
      items = items.filter((item) =>
        `${item.title || ''} ${item.summary || ''}`.toLowerCase().includes(query)
      )
    }
    return { items: items.slice(0, normalizedLimit ?? 50) }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/memory`, {
      params: {
        kind: params?.kind ?? undefined,
        query: params?.query ?? undefined,
        tags: params?.tags?.join(',') ?? undefined,
        quest_id: params?.questId ?? undefined,
        branch_name: params?.branchName ?? undefined,
        stage_key: params?.stageKey ?? undefined,
        origin_event_id: params?.originEventId ?? undefined,
        idea_id: params?.ideaId ?? undefined,
        run_id: params?.runId ?? undefined,
        agent_instance_id: params?.agentInstanceId ?? undefined,
        authority_level: params?.authorityLevel ?? undefined,
        review_status: params?.reviewStatus ?? undefined,
        at_event_id: params?.atEventId ?? undefined,
        limit: normalizedLimit,
      },
    })
    return response.data ?? { items: [] }
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    const cards = await questClient.memory(projectId)
    let items = cards.map(mapMemoryCardToEntry)
    if (params?.kind) {
      items = items.filter((item) => item.kind === params.kind)
    }
    if (params?.query) {
      const query = params.query.toLowerCase()
      items = items.filter((item) =>
        `${item.title || ''} ${item.summary || ''}`.toLowerCase().includes(query)
      )
    }
    return { items: items.slice(0, normalizedLimit ?? 50) }
  }
}

export async function getLabMemoryEntry(
  projectId: string,
  entryId: string
): Promise<LabMemoryEntry> {
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/memory/${entryId}`)
    return response.data
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    return resolveLocalMemoryEntry(projectId, entryId)
  }
}

export async function listLabAchievementDefinitions(
  projectId: string
): Promise<LabListResponse<LabAchievementDefinition>> {
  if (await shouldUseLocalQuestLab(projectId)) {
    return { items: [] }
  }
  try {
    const response = await apiClient.get(`${LAB_BASE(projectId)}/achievements/definitions`)
    return response.data ?? { items: [] }
  } catch (error) {
    if (!isLocalLabFallbackError(error)) {
      throw error
    }
    return { items: [] }
  }
}
