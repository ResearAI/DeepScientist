/**
 * Projects API Client
 *
 * API client for project management operations
 *
 * @module api/projects
 */

import { apiClient } from "./client";
import { client as questClient } from "@/lib/api";
import { hasQuestApi, isQuestRuntimeSurface, shouldUseQuestProject } from "@/lib/runtime/quest-runtime";
import type { QuestSummary } from "@/types";

const PROJECTS_BASE = "/api/v1/projects";
const LOCAL_OWNER = {
  id: "local",
  username: "DeepScientist",
  email: "local@deepscientist",
};

/**
 * Project data from API
 */
export interface Project {
  id: string;
  name: string;
  description?: string;
  owner_id: string;
  is_public: boolean;
  created_at: string;
  updated_at: string;
  settings: Record<string, unknown>;
  storage_used: number;
  file_count: number;
  owner?: {
    id: string;
    username: string;
    email: string;
  };
  agents?: AgentDescriptor[];
}

export interface AgentDescriptor {
  id: string;
  label: string;
  description?: string | null;
  role?: string | null;
  source?: string | null;
  execution_target?: string | null;
  agent_engine?: string | null;
}

/**
 * Project member data
 */
export interface ProjectMember {
  id: string;
  user_id: string;
  role: "owner" | "admin" | "editor" | "viewer";
  joined_at: string;
  annotation_color: string;
  user?: {
    id: string;
    username: string;
    email: string;
  };
}

/**
 * Create project request
 */
export interface CreateProjectRequest {
  name: string;
  description?: string;
  is_public?: boolean;
  settings?: Record<string, unknown>;
}

/**
 * Update project request
 */
export interface UpdateProjectRequest {
  name?: string;
  description?: string;
  is_public?: boolean;
  settings?: Record<string, unknown>;
}

/**
 * Project list response (matches backend format)
 */
export interface ProjectListResponse {
  items: Project[];
  total: number;
  skip: number;
  limit: number;
}

function normalizeTimestamp(value?: string | null): string {
  return value && value.trim() ? value : new Date().toISOString();
}

function preferLocalQuestProjects(): boolean {
  return isQuestRuntimeSurface();
}

async function shouldUseLocalQuestProject(projectId: string): Promise<boolean> {
  return shouldUseQuestProject(projectId);
}

function mapQuestSummaryToProject(summary: QuestSummary): Project {
  const startupContract =
    summary.startup_contract && typeof summary.startup_contract === 'object'
      ? (summary.startup_contract as Record<string, unknown>)
      : null
  const projectDisplay =
    startupContract?.project_display && typeof startupContract.project_display === 'object'
      ? (startupContract.project_display as Record<string, unknown>)
      : null
  return {
    id: summary.quest_id,
    name: summary.title || summary.quest_id,
    description: summary.summary?.status_line || "",
    owner_id: LOCAL_OWNER.id,
    is_public: false,
    created_at: normalizeTimestamp(summary.updated_at),
    updated_at: normalizeTimestamp(summary.updated_at),
    settings: {
      source: "quest",
      quest_root: summary.quest_root || null,
      quest_status: summary.status,
      active_anchor: summary.active_anchor,
      branch: summary.branch || null,
      head: summary.head || null,
      pending_decisions: summary.pending_decisions || [],
      counts: summary.counts || {},
      paths: summary.paths || {},
      workspace_mode: summary.workspace_mode || startupContract?.workspace_mode || null,
      project_display: projectDisplay || {
        template: 'blank',
        accent_color: 'graphite',
      },
    },
    storage_used: 0,
    file_count:
      Number(summary.counts?.memory_cards || 0) +
      Number(summary.counts?.artifacts || 0),
    owner: LOCAL_OWNER,
    agents: [
      {
        id: `${summary.quest_id}:lead`,
        label: summary.runner || "codex",
        description: summary.summary?.status_line || null,
        role: "lead",
        source: "local",
        execution_target: "local",
        agent_engine: summary.runner || "codex",
      },
    ],
  };
}

function shouldFallbackToLocalQuest(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const response = (error as { response?: { status?: number } }).response;
  const status = response?.status;
  if (status && [401, 403, 404, 405, 501, 502, 503].includes(status)) {
    return true;
  }
  const code = (error as { code?: string }).code;
  return code === "ERR_NETWORK" || code === "ECONNABORTED";
}

/**
 * List all projects for the current user
 */
export async function listProjects(): Promise<ProjectListResponse> {
  if (preferLocalQuestProjects() || (await hasQuestApi())) {
    const items = (await questClient.quests()).map(mapQuestSummaryToProject);
    return {
      items,
      total: items.length,
      skip: 0,
      limit: Math.max(items.length, 50),
    };
  }
  try {
    const response = await apiClient.get<ProjectListResponse>(PROJECTS_BASE);
    return {
      items: response.data?.items || [],
      total: response.data?.total || 0,
      skip: response.data?.skip || 0,
      limit: response.data?.limit || 50,
    };
  } catch (error) {
    if (!shouldFallbackToLocalQuest(error)) {
      throw error;
    }
    const items = (await questClient.quests()).map(mapQuestSummaryToProject);
    return {
      items,
      total: items.length,
      skip: 0,
      limit: Math.max(items.length, 50),
    };
  }
}

/**
 * Get project details
 */
export async function getProject(projectId: string): Promise<Project> {
  if (await shouldUseLocalQuestProject(projectId)) {
    const summary = await questClient.session(projectId);
    return mapQuestSummaryToProject(summary.snapshot);
  }
  try {
    const response = await apiClient.get<Project>(`${PROJECTS_BASE}/${projectId}`);
    return response.data;
  } catch (error) {
    if (!shouldFallbackToLocalQuest(error)) {
      throw error;
    }
    const summary = await questClient.session(projectId);
    return mapQuestSummaryToProject(summary.snapshot);
  }
}

/**
 * Create a new project
 */
export async function createProject(
  data: CreateProjectRequest
): Promise<Project> {
  if (preferLocalQuestProjects() || (await hasQuestApi())) {
    const created = await questClient.createQuestWithOptions({
      goal: data.description || data.name,
      title: data.name,
      source: 'web-react',
      auto_start: true,
      initial_message: data.description || data.name,
    });
    return mapQuestSummaryToProject(created.snapshot);
  }
  try {
    const response = await apiClient.post<Project>(PROJECTS_BASE, data);
    return response.data;
  } catch (error) {
    if (!shouldFallbackToLocalQuest(error)) {
      throw error;
    }
    const created = await questClient.createQuestWithOptions({
      goal: data.description || data.name,
      title: data.name,
      source: 'web-react',
      auto_start: true,
      initial_message: data.description || data.name,
    });
    return mapQuestSummaryToProject(created.snapshot);
  }
}

/**
 * Update project
 */
export async function updateProject(
  projectId: string,
  data: UpdateProjectRequest
): Promise<Project> {
  const applyLocalOverlay = (project: Project): Project => ({
    ...project,
    ...("description" in data ? { description: data.description } : {}),
    is_public: data.is_public ?? project.is_public,
    settings: {
      ...project.settings,
      ...(data.settings || {}),
    },
  });

  if (await shouldUseLocalQuestProject(projectId)) {
    if (typeof data.name === "string" && data.name.trim()) {
      const updated = await questClient.updateQuestSettings(projectId, {
        title: data.name,
      });
      return applyLocalOverlay(mapQuestSummaryToProject(updated.snapshot));
    }
    const summary = await questClient.session(projectId);
    return applyLocalOverlay(mapQuestSummaryToProject(summary.snapshot));
  }
  try {
    const response = await apiClient.patch<Project>(
      `${PROJECTS_BASE}/${projectId}`,
      data
    );
    return response.data;
  } catch (error) {
    if (!shouldFallbackToLocalQuest(error)) {
      throw error;
    }
    if (typeof data.name === "string" && data.name.trim()) {
      const updated = await questClient.updateQuestSettings(projectId, {
        title: data.name,
      });
      return applyLocalOverlay(mapQuestSummaryToProject(updated.snapshot));
    }
    const summary = await questClient.session(projectId);
    return applyLocalOverlay(mapQuestSummaryToProject(summary.snapshot));
  }
}

/**
 * Delete project
 */
export async function deleteProject(projectId: string): Promise<void> {
  try {
    await apiClient.delete(`${PROJECTS_BASE}/${projectId}`);
  } catch (error) {
    if (!shouldFallbackToLocalQuest(error)) {
      throw error;
    }
  }
}

export async function leaveProject(projectId: string): Promise<void> {
  try {
    await apiClient.delete(`${PROJECTS_BASE}/${projectId}/members/me`);
  } catch (error) {
    if (!shouldFallbackToLocalQuest(error)) {
      throw error;
    }
  }
}

/**
 * List project members
 */
export async function listProjectMembers(
  projectId: string
): Promise<ProjectMember[]> {
  if (await shouldUseLocalQuestProject(projectId)) {
    return [
      {
        id: `${projectId}:owner`,
        user_id: LOCAL_OWNER.id,
        role: "owner",
        joined_at: new Date().toISOString(),
        annotation_color: "#8FA3B8",
        user: LOCAL_OWNER,
      },
    ];
  }
  try {
    const response = await apiClient.get<ProjectMember[]>(
      `${PROJECTS_BASE}/${projectId}/members`
    );
    return response.data;
  } catch (error) {
    if (!shouldFallbackToLocalQuest(error)) {
      throw error;
    }
    return [
      {
        id: `${projectId}:owner`,
        user_id: LOCAL_OWNER.id,
        role: "owner",
        joined_at: new Date().toISOString(),
        annotation_color: "#8FA3B8",
        user: LOCAL_OWNER,
      },
    ];
  }
}

/**
 * Add project member
 */
export async function addProjectMember(
  projectId: string,
  userId: string,
  role: ProjectMember["role"]
): Promise<ProjectMember> {
  try {
    const response = await apiClient.post<ProjectMember>(
      `${PROJECTS_BASE}/${projectId}/members`,
      { user_id: userId, role }
    );
    return response.data;
  } catch (error) {
    if (!shouldFallbackToLocalQuest(error)) {
      throw error;
    }
    return {
      id: `${projectId}:${userId}`,
      user_id: userId,
      role,
      joined_at: new Date().toISOString(),
      annotation_color: "#8FA3B8",
      user: {
        id: userId,
        username: userId,
        email: `${userId}@local`,
      },
    };
  }
}

/**
 * Update project member role
 */
export async function updateProjectMemberRole(
  projectId: string,
  userId: string,
  role: ProjectMember["role"]
): Promise<ProjectMember> {
  try {
    const response = await apiClient.patch<ProjectMember>(
      `${PROJECTS_BASE}/${projectId}/members/${userId}`,
      { role }
    );
    return response.data;
  } catch (error) {
    if (!shouldFallbackToLocalQuest(error)) {
      throw error;
    }
    return {
      id: `${projectId}:${userId}`,
      user_id: userId,
      role,
      joined_at: new Date().toISOString(),
      annotation_color: "#8FA3B8",
      user: {
        id: userId,
        username: userId,
        email: `${userId}@local`,
      },
    };
  }
}

/**
 * Remove project member
 */
export async function removeProjectMember(
  projectId: string,
  userId: string
): Promise<void> {
  try {
    await apiClient.delete(`${PROJECTS_BASE}/${projectId}/members/${userId}`);
  } catch (error) {
    if (!shouldFallbackToLocalQuest(error)) {
      throw error;
    }
  }
}

/**
 * Check project access for current user
 */
export async function checkProjectAccess(
  projectId: string
): Promise<{ has_access: boolean; role?: ProjectMember["role"] }> {
  if (await shouldUseLocalQuestProject(projectId)) {
    return {
      has_access: true,
      role: "owner",
    };
  }
  try {
    const response = await apiClient.get<{
      has_access: boolean;
      role?: ProjectMember["role"];
    }>(`${PROJECTS_BASE}/${projectId}/access`);
    return response.data;
  } catch (error) {
    if (!shouldFallbackToLocalQuest(error)) {
      throw error;
    }
    return {
      has_access: true,
      role: "owner",
    };
  }
}

// ==================== Project Copy (Fork) ====================

export type ProjectCopyTaskStatus = "pending" | "running" | "completed" | "failed" | "canceled";

export interface ProjectCopyProgress {
  phase: string;
  files_total?: number;
  files_done?: number;
  notebooks_total?: number;
  notebooks_done?: number;
}

export interface CreateProjectCopyTaskRequest {
  new_name: string;
  new_description?: string | null;
  share_token?: string | null;
  options?: {
    copy_annotations?: boolean;
    copy_notebooks?: boolean;
  };
}

export interface CreateProjectCopyTaskResponse {
  task_id: string;
  status: ProjectCopyTaskStatus;
  source_project_id: string;
  target_project_id: string | null;
  poll_url: string;
}

export interface ProjectCopyTaskResponse {
  task_id: string;
  status: ProjectCopyTaskStatus;
  source_project_id: string | null;
  target_project_id: string | null;
  progress: ProjectCopyProgress;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export async function createProjectCopyTask(
  projectId: string,
  data: CreateProjectCopyTaskRequest
): Promise<CreateProjectCopyTaskResponse> {
  const response = await apiClient.post<CreateProjectCopyTaskResponse>(`${PROJECTS_BASE}/${projectId}/copy`, data);
  return response.data;
}

export async function getProjectCopyTask(taskId: string): Promise<ProjectCopyTaskResponse> {
  const response = await apiClient.get<ProjectCopyTaskResponse>(`${PROJECTS_BASE}/copy-tasks/${taskId}`);
  return response.data;
}
