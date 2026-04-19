'use client'

import * as React from 'react'

import { useToast } from '@/components/ui/toast'
import { client } from '@/lib/api'

export type QuestMessageAttachmentDraft = {
  draftId: string
  name: string
  contentType?: string | null
  sizeBytes: number
  status: 'queued' | 'uploading' | 'success' | 'failed'
  progress: number
  error?: string
  assetUrl?: string | null
  assetDocumentId?: string | null
  questRelativePath?: string | null
  path?: string | null
  extractedTextPath?: string | null
  kind?: string | null
  previewUrl?: string | null
  file?: File | null
}

const MAX_ATTACHMENTS = 10
const MAX_ATTACHMENT_SIZE_BYTES = 20 * 1024 * 1024

function makeDraftId() {
  return `draft-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(reader.error || new Error('Failed to read file.'))
    reader.onload = () => {
      const result = String(reader.result || '')
      const base64 = result.includes(',') ? result.split(',', 2)[1] : result
      resolve(base64)
    }
    reader.readAsDataURL(file)
  })
}

function isImageMime(value?: string | null) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .startsWith('image/')
}

export function useQuestMessageAttachments(questId?: string | null) {
  const { addToast } = useToast()
  const [attachments, setAttachments] = React.useState<QuestMessageAttachmentDraft[]>([])
  const canceledDraftsRef = React.useRef<Set<string>>(new Set())
  const attachmentsRef = React.useRef<QuestMessageAttachmentDraft[]>([])

  React.useEffect(() => {
    attachmentsRef.current = attachments
  }, [attachments])

  React.useEffect(() => {
    setAttachments((current) => {
      current.forEach((item) => {
        if (item.previewUrl?.startsWith('blob:')) {
          URL.revokeObjectURL(item.previewUrl)
        }
      })
      return []
    })
    canceledDraftsRef.current = new Set()
  }, [questId])

  React.useEffect(() => {
    return () => {
      attachmentsRef.current.forEach((item) => {
        if (item.previewUrl?.startsWith('blob:')) {
          URL.revokeObjectURL(item.previewUrl)
        }
      })
    }
  }, [])

  const uploadDraft = React.useCallback(
    async (draft: QuestMessageAttachmentDraft) => {
      if (!questId || !draft.file) {
        setAttachments((current) =>
          current.map((item) =>
            item.draftId === draft.draftId
              ? { ...item, status: 'failed', error: 'No active quest.' }
              : item
          )
        )
        return
      }

      setAttachments((current) =>
        current.map((item) =>
          item.draftId === draft.draftId
            ? { ...item, status: 'uploading', progress: 0, error: undefined }
            : item
        )
      )

      try {
        const contentBase64 = await fileToBase64(draft.file)
        const payload = await client.uploadChatAttachment(
          questId,
          {
            draft_id: draft.draftId,
            file_name: draft.name,
            mime_type: draft.contentType || undefined,
            content_base64: contentBase64,
          },
          {
            onUploadProgress: (progress) => {
              if (canceledDraftsRef.current.has(draft.draftId)) return
              setAttachments((current) =>
                current.map((item) =>
                  item.draftId === draft.draftId
                    ? { ...item, status: 'uploading', progress }
                    : item
                )
              )
            },
          }
        )
        if (canceledDraftsRef.current.has(draft.draftId)) {
          void client.deleteChatAttachment(questId, draft.draftId).catch(() => undefined)
          setAttachments((current) => current.filter((item) => item.draftId !== draft.draftId))
          return
        }
        if (!payload.ok) {
          throw new Error(payload.message || 'Upload failed.')
        }
        setAttachments((current) =>
          current.map((item) =>
            item.draftId === draft.draftId
              ? {
                  ...item,
                  status: 'success',
                  progress: 100,
                  assetUrl: payload.asset_url,
                  assetDocumentId: payload.asset_document_id,
                  questRelativePath: payload.quest_relative_path,
                  path: payload.path,
                  extractedTextPath: payload.extracted_text_path,
                  kind: payload.kind || item.kind,
                  file: null,
                }
              : item
          )
        )
      } catch (caught) {
        if (canceledDraftsRef.current.has(draft.draftId)) {
          setAttachments((current) => current.filter((item) => item.draftId !== draft.draftId))
          return
        }
        const message = caught instanceof Error ? caught.message : String(caught)
        setAttachments((current) =>
          current.map((item) =>
            item.draftId === draft.draftId
              ? { ...item, status: 'failed', error: message }
              : item
          )
        )
      }
    },
    [questId]
  )

  const queueFiles = React.useCallback(
    (files: File[]) => {
      if (!questId) {
        addToast({
          type: 'error',
          title: 'Upload failed',
          description: 'Open a quest before uploading attachments.',
        })
        return
      }
      if (!files.length) return

      const availableSlots = Math.max(0, MAX_ATTACHMENTS - attachments.length)
      const nextFiles = files.slice(0, availableSlots)
      if (files.length > nextFiles.length) {
        addToast({
          type: 'warning',
          title: 'Attachment limit reached',
          description: `You can attach up to ${MAX_ATTACHMENTS} files.`,
        })
      }

      const drafts: QuestMessageAttachmentDraft[] = []
      for (const file of nextFiles) {
        if (file.size > MAX_ATTACHMENT_SIZE_BYTES) {
          addToast({
            type: 'warning',
            title: 'File too large',
            description: 'Each attachment must be under 20 MB.',
          })
          continue
        }
        const draftId = makeDraftId()
        drafts.push({
          draftId,
          name: file.name,
          contentType: file.type || undefined,
          sizeBytes: file.size,
          status: 'queued',
          progress: 0,
          kind: isImageMime(file.type) ? 'image' : 'path',
          previewUrl: isImageMime(file.type) ? URL.createObjectURL(file) : null,
          file,
        })
      }
      if (!drafts.length) return
      setAttachments((current) => [...current, ...drafts])
      drafts.forEach((draft) => {
        void uploadDraft(draft)
      })
    },
    [addToast, attachments.length, questId, uploadDraft]
  )

  const removeAttachment = React.useCallback(
    async (draftId: string) => {
      canceledDraftsRef.current.add(draftId)
      const current = attachments.find((item) => item.draftId === draftId) || null
      if (current?.previewUrl?.startsWith('blob:')) {
        URL.revokeObjectURL(current.previewUrl)
      }
      setAttachments((items) => items.filter((item) => item.draftId !== draftId))
      if (!questId) return
      if (current?.status === 'success' || current?.status === 'uploading') {
        try {
          await client.deleteChatAttachment(questId, draftId)
        } catch {
          // Best-effort cleanup for staged uploads.
        }
      }
    },
    [attachments, questId]
  )

  const clearAll = React.useCallback(async () => {
    const draftIds = attachments.map((item) => item.draftId)
    await Promise.all(draftIds.map((draftId) => removeAttachment(draftId)))
  }, [attachments, removeAttachment])

  const hasUploading = attachments.some((item) => item.status === 'uploading' || item.status === 'queued')
  const hasFailures = attachments.some((item) => item.status === 'failed')
  const successfulAttachments = attachments.filter((item) => item.status === 'success')

  return {
    attachments,
    queueFiles,
    removeAttachment,
    clearAll,
    hasUploading,
    hasFailures,
    successfulAttachments,
  }
}

export default useQuestMessageAttachments
