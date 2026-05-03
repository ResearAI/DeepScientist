import { apiClient } from '@/lib/api/client'
import type {
  AdminAuditPayload,
  AdminControllersPayload,
  AdminDoctorPayload,
  AdminErrorsPayload,
  AdminFailurePayload,
  AdminIssueDraftRequest,
  AdminIssueDraftPayload,
  AdminLogSourcesPayload,
  AdminLogTailPayload,
  AdminOverviewPayload,
  AdminQuestListPayload,
  AdminQuestSummaryPayload,
  AdminRepairResponse,
  AdminRepairsPayload,
  AdminRuntimeSessionsPayload,
  AdminSystemHardwarePayload,
  AdminRuntimeToolsPayload,
  AdminSearchPayload,
  AdminStatsSummaryPayload,
  AdminTask,
  AdminChartCatalogPayload,
  AdminChartQueryPayload,
} from '@/lib/types/admin'

const SYSTEM_BASE = '/api/system'

export async function getAdminOverview() {
  const response = await apiClient.get<AdminOverviewPayload>(`${SYSTEM_BASE}/overview`)
  return response.data
}

export async function getAdminQuests(limit = 100) {
  const response = await apiClient.get<AdminQuestListPayload>(`${SYSTEM_BASE}/quests`, {
    params: { limit },
  })
  return response.data
}

export async function getAdminQuestSummary(questId: string) {
  const response = await apiClient.get<AdminQuestSummaryPayload>(`${SYSTEM_BASE}/quests/${encodeURIComponent(questId)}/summary`)
  return response.data
}

export async function getAdminRuntimeSessions(limit = 200) {
  const response = await apiClient.get<AdminRuntimeSessionsPayload>(`${SYSTEM_BASE}/runtime/sessions`, {
    params: { limit },
  })
  return response.data
}

export async function getAdminLogSources() {
  const response = await apiClient.get<AdminLogSourcesPayload>(`${SYSTEM_BASE}/logs/sources`)
  return response.data
}

export async function getAdminLogTail(source: string, lineCount = 200) {
  const response = await apiClient.get<AdminLogTailPayload>(`${SYSTEM_BASE}/logs/tail`, {
    params: { source, line_count: lineCount },
  })
  return response.data
}

export async function getAdminFailures(limit = 100) {
  const response = await apiClient.get<AdminFailurePayload>(`${SYSTEM_BASE}/failures`, {
    params: { limit },
  })
  return response.data
}

export async function getAdminErrors(limit = 100) {
  const response = await apiClient.get<AdminErrorsPayload>(`${SYSTEM_BASE}/errors`, {
    params: { limit },
  })
  return response.data
}

export async function getAdminRuntimeTools() {
  const response = await apiClient.get<AdminRuntimeToolsPayload>(`${SYSTEM_BASE}/runtime-tools`)
  return response.data
}

export async function getAdminSystemHardware() {
  const response = await apiClient.get<AdminSystemHardwarePayload>(`${SYSTEM_BASE}/hardware`)
  return response.data
}

export async function getAdminChartCatalog() {
  const response = await apiClient.get<AdminChartCatalogPayload>(`${SYSTEM_BASE}/charts/catalog`)
  return response.data
}

export async function queryAdminCharts(
  items: Array<{ chart_id: string; range?: string; step_seconds?: number; quest_id?: string; limit?: number }>
) {
  const response = await apiClient.post<AdminChartQueryPayload>(`${SYSTEM_BASE}/charts/query`, { items })
  return response.data
}

export async function saveAdminSystemHardware(payload: {
  gpu_selection_mode?: string
  selected_gpu_ids?: string[]
  include_system_hardware_in_prompt?: boolean
  memory_read_visibility_mode?: string
}) {
  const response = await apiClient.post<AdminSystemHardwarePayload>(`${SYSTEM_BASE}/hardware`, payload)
  return response.data
}

export async function getAdminAudit(limit = 200) {
  const response = await apiClient.get<AdminAuditPayload>(`${SYSTEM_BASE}/audit`, {
    params: { limit },
  })
  return response.data
}

export async function getAdminStatsSummary() {
  const response = await apiClient.get<AdminStatsSummaryPayload>(`${SYSTEM_BASE}/stats/summary`)
  return response.data
}

export async function getAdminSearch(query: string, limit = 100) {
  const response = await apiClient.get<AdminSearchPayload>(`${SYSTEM_BASE}/search`, {
    params: { q: query, limit },
  })
  return response.data
}

export async function createAdminIssueDraft(payload?: AdminIssueDraftRequest) {
  const response = await apiClient.post<AdminIssueDraftPayload>(`${SYSTEM_BASE}/issues/draft`, payload || {})
  return response.data
}

export async function getAdminControllers() {
  const response = await apiClient.get<AdminControllersPayload>(`${SYSTEM_BASE}/controllers`)
  return response.data
}

export async function runAdminController(controllerId: string) {
  const response = await apiClient.post<{ ok: boolean; controller_id: string; result: Record<string, unknown> }>(
    `${SYSTEM_BASE}/controllers/${encodeURIComponent(controllerId)}/run`,
    {}
  )
  return response.data
}

export async function toggleAdminController(controllerId: string, enabled: boolean) {
  const response = await apiClient.post<{ ok: boolean; controller: Record<string, unknown> }>(
    `${SYSTEM_BASE}/controllers/${encodeURIComponent(controllerId)}/toggle`,
    { enabled }
  )
  return response.data
}

export async function getAdminDoctor() {
  const response = await apiClient.get<AdminDoctorPayload>(`${SYSTEM_BASE}/doctor`)
  return response.data
}

export async function listAdminTasks(kind?: string, limit = 50) {
  const response = await apiClient.get<{ ok: boolean; items: AdminTask[] }>(`${SYSTEM_BASE}/tasks`, {
    params: { kind, limit },
  })
  return response.data
}

export async function getAdminTask(taskId: string) {
  const response = await apiClient.get<{ ok: boolean; task: AdminTask }>(`${SYSTEM_BASE}/tasks/${encodeURIComponent(taskId)}`)
  return response.data
}

export async function startAdminDoctorTask() {
  const response = await apiClient.post<{ ok: boolean; task: AdminTask }>(`${SYSTEM_BASE}/tasks/doctor`, {})
  return response.data
}

export async function startAdminSystemUpdateCheckTask() {
  const response = await apiClient.post<{ ok: boolean; task: AdminTask }>(`${SYSTEM_BASE}/tasks/system-update-check`, {})
  return response.data
}

export async function startAdminSystemUpdateActionTask(action: string) {
  const response = await apiClient.post<{ ok: boolean; task: AdminTask }>(`${SYSTEM_BASE}/tasks/system-update-action`, {
    action,
  })
  return response.data
}

export async function getAdminRepairs(limit = 50) {
  const response = await apiClient.get<AdminRepairsPayload>(`${SYSTEM_BASE}/repairs`, {
    params: { limit },
  })
  return response.data
}

export async function getAdminRepair(repairId: string) {
  const response = await apiClient.get<AdminRepairResponse>(`${SYSTEM_BASE}/repairs/${encodeURIComponent(repairId)}`)
  return response.data
}

export async function createAdminRepair(payload: {
  request_text: string
  source_page?: string
  scope?: string
  targets?: Record<string, unknown>
  repair_policy?: string
  selected_paths?: string[]
}) {
  const response = await apiClient.post<AdminRepairResponse>(`${SYSTEM_BASE}/repairs`, payload)
  return response.data
}

export async function closeAdminRepair(repairId: string) {
  const response = await apiClient.post<AdminRepairResponse>(`${SYSTEM_BASE}/repairs/${encodeURIComponent(repairId)}/close`, {})
  return response.data
}
