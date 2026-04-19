import { apiClient } from '@/lib/api/client'
import type { LatexBuildError } from '@/lib/api/latex'

export type CopilotFocusedErrorPayload = {
  kind: 'latex_error'
  tabId?: string
  fileId?: string
  resourceId?: string
  resourcePath?: string
  resourceName?: string
  line?: number
  message: string
  severity: 'error' | 'warning'
  excerpt?: string
}

export type CopilotAttachmentUploadResponse = {
  file_id: string
  name: string
  size: number
  mime: string
  sha256?: string
}

export async function uploadCopilotAttachment({
  projectId,
  sessionId,
  file,
  onProgress,
}: {
  projectId: string
  sessionId: string
  file: File
  onProgress?: (progress: number) => void
}): Promise<CopilotAttachmentUploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('project_id', projectId)
  formData.append('session_id', sessionId)

  const response = await apiClient.post<CopilotAttachmentUploadResponse>(
    '/api/copilot/files',
    formData,
    {
      headers: {
        'Content-Type': undefined,
      },
      onUploadProgress: (event) => {
        if (!onProgress || !event.total) return
        const progress = Math.round((event.loaded * 100) / event.total)
        onProgress(progress)
      },
    }
  )

  return response.data
}

export type CopilotFixWithAIRequest = {
  folder_id: string
  build_id?: string | null
  log_text?: string | null
  log_items?: LatexBuildError[]
  message?: string
  metadata?: Record<string, unknown>
  recent_files?: string[]
  focused_error?: CopilotFocusedErrorPayload | null
  max_items?: number
}

export type CopilotToolEvent = {
  tool_call_id: string
  name: string
  status: 'calling' | 'called' | 'failed'
  function: string
  args?: Record<string, unknown>
  content?: Record<string, unknown>
}

export type CopilotPatchChange = {
  path: string
  patch: string
}

export type CopilotPatchResponse = {
  patch_id: string
  title: string
  changes: CopilotPatchChange[]
  explanations: string[]
}

export type CopilotTimelineEvent = {
  type: 'tool_call' | 'tool_result' | 'patch'
  data: CopilotToolEvent | CopilotPatchResponse
}

export type CopilotFixWithAIErrorResponse = {
  ok: false
  request_id: string
  code: string
  message: string
  suggestion?: string
  details?: Record<string, unknown>
}

export async function runCopilotFixWithAi(
  projectId: string,
  payload: CopilotFixWithAIRequest
): Promise<CopilotTimelineEvent[]> {
  const response = await apiClient.post<CopilotTimelineEvent[]>(
    `/api/v1/projects/${projectId}/copilot/actions/fix-with-ai`,
    payload
  )
  return Array.isArray(response.data) ? response.data : []
}
