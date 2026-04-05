export const WORKSPACE_LEFT_VISIBILITY_EVENT = 'ds:workspace:left-visibility'
export const QUEST_WORKSPACE_VIEW_EVENT = 'ds:quest:workspace-view'

export type WorkspaceLeftVisibilityDetail = {
  projectId: string
  visible: boolean
}

export type QuestStageSelection = {
  quest_id?: string | null
  selection_ref?: string | null
  selection_type?: string | null
  branch_name?: string | null
  branch_no?: string | null
  parent_branch?: string | null
  foundation_ref?: Record<string, unknown> | null
  foundation_reason?: string | null
  foundation_label?: string | null
  idea_title?: string | null
  stage_key?: string | null
  worktree_rel_path?: string | null
  scope_paths?: string[] | null
  compare_base?: string | null
  compare_head?: string | null
  label?: string | null
  summary?: string | null
  baseline_gate?: string | null
}

export type QuestWorkspaceView = 'canvas' | 'details' | 'memory' | 'terminal' | 'settings' | 'stage'

export type QuestWorkspaceViewDetail = {
  projectId: string
  view: QuestWorkspaceView
  stageSelection?: QuestStageSelection | null
}

export function dispatchWorkspaceLeftVisibility(detail: WorkspaceLeftVisibilityDetail) {
  if (typeof window === 'undefined') return
  window.dispatchEvent(
    new CustomEvent<WorkspaceLeftVisibilityDetail>(WORKSPACE_LEFT_VISIBILITY_EVENT, {
      detail,
    })
  )
}

export function dispatchQuestWorkspaceView(detail: QuestWorkspaceViewDetail) {
  if (typeof window === 'undefined') return
  window.dispatchEvent(
    new CustomEvent<QuestWorkspaceViewDetail>(QUEST_WORKSPACE_VIEW_EVENT, {
      detail,
    })
  )
}
