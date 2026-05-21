import { client as questClient } from '@/lib/api'
import { openDemoDocumentAsFileNode } from '@/demo/adapter'
import { isDemoProjectId } from '@/demo/projects'
import type { FileAPIResponse, FileNode, FileTextPreviewResponse, FileTreeResponse } from '@/lib/types/file'
import { transformToFileNode } from '@/lib/types/file'
import type { ExplorerNode, ExplorerPayload, OpenDocumentPayload, QuestDocumentAssetUploadPayload } from '@/types'

const QUEST_FILE_PREFIX = 'quest-file::'
const QUEST_DIR_PREFIX = 'quest-dir::'
const TREE_CACHE_TTL_MS = 4000

type QuestNodeRef =
  | {
      type: 'file'
      projectId: string
      documentId: string
      path: string
    }
  | {
      type: 'dir'
      projectId: string
      path: string
    }

type CachedQuestFile = FileAPIResponse & {
  document_id?: string
}

export type QuestFileContentSnapshot = {
  file_id: string
  content: string
  revision?: string | null
  updated_at?: string | null
  size?: number
  mime_type?: string | null
  project_id?: string
}

export type QuestFileSaveOptions = {
  revision?: string | null
  force?: boolean
}

type QuestMutationItem = {
  name: string
  path: string
  kind: 'file' | 'directory'
  folder_kind?: string
  document_id?: string
  open_kind?: string
  updated_at?: string
  size?: number
  mime_type?: string
}

const treeCache = new Map<string, { expiresAt: number; payload: FileTreeResponse }>()
const treeInFlight = new Map<string, Promise<FileTreeResponse>>()
const fileCache = new Map<string, CachedQuestFile>()

type QuestTreeOptions = {
  force?: boolean
}

function nowIso() {
  return new Date().toISOString()
}

function encodePath(value: string) {
  return encodeURIComponent(value)
}

function decodePath(value: string) {
  return decodeURIComponent(value)
}

function extname(path: string) {
  const clean = path.split('/').pop() || path
  const idx = clean.lastIndexOf('.')
  return idx >= 0 ? clean.slice(idx).toLowerCase() : ''
}

function mimeTypeForPath(path: string, kind?: string) {
  if (kind === 'markdown') return 'text/markdown'
  const ext = extname(path)
  switch (ext) {
    case '.md':
    case '.markdown':
    case '.mdx':
      return 'text/markdown'
    case '.json':
      return 'application/json'
    case '.yaml':
    case '.yml':
      return 'text/yaml'
    case '.py':
      return 'text/x-python'
    case '.ts':
      return 'text/typescript'
    case '.tsx':
      return 'text/tsx'
    case '.js':
      return 'text/javascript'
    case '.jsx':
      return 'text/jsx'
    case '.sh':
      return 'text/x-shellscript'
    case '.txt':
      return 'text/plain'
    case '.html':
      return 'text/html'
    case '.css':
      return 'text/css'
    case '.svg':
      return 'image/svg+xml'
    case '.png':
      return 'image/png'
    case '.jpg':
    case '.jpeg':
      return 'image/jpeg'
    case '.pdf':
      return 'application/pdf'
    default:
      return 'text/plain'
  }
}

function encodeQuestFileId(projectId: string, documentId: string, path: string) {
  return `${QUEST_FILE_PREFIX}${projectId}::${encodePath(documentId)}::${encodePath(path)}`
}

function encodeQuestDirId(projectId: string, path: string) {
  return `${QUEST_DIR_PREFIX}${projectId}::${encodePath(path)}`
}

export function buildQuestDirectoryId(projectId: string, path: string) {
  return encodeQuestDirId(projectId, path)
}

export function buildQuestFileIdFromDocument(projectId: string, documentId: string, path: string) {
  return encodeQuestFileId(projectId, documentId, path)
}

export function isQuestNodeId(fileId: string) {
  return fileId.startsWith(QUEST_FILE_PREFIX) || fileId.startsWith(QUEST_DIR_PREFIX)
}

export function getQuestNodeProjectId(fileId: string): string | null {
  const ref = parseQuestNodeId(fileId)
  return ref?.projectId || null
}

export function getQuestNodeDocumentId(fileId: string): string | null {
  const ref = parseQuestNodeId(fileId)
  return ref?.type === 'file' ? ref.documentId : null
}

function parseQuestNodeId(fileId: string): QuestNodeRef | null {
  if (fileId.startsWith(QUEST_FILE_PREFIX)) {
    const raw = fileId.slice(QUEST_FILE_PREFIX.length)
    const [projectId, encodedDocumentId = '', encodedPath = ''] = raw.split('::')
    if (!projectId || !encodedDocumentId) return null
    return {
      type: 'file',
      projectId,
      documentId: decodePath(encodedDocumentId),
      path: decodePath(encodedPath || encodedDocumentId),
    }
  }
  if (fileId.startsWith(QUEST_DIR_PREFIX)) {
    const raw = fileId.slice(QUEST_DIR_PREFIX.length)
    const [projectId, encodedPath = ''] = raw.split('::')
    if (!projectId) return null
    return {
      type: 'dir',
      projectId,
      path: decodePath(encodedPath),
    }
  }
  return null
}

function parentPath(path: string): string | null {
  const parts = path.split('/').filter(Boolean)
  if (parts.length <= 1) return null
  return parts.slice(0, -1).join('/')
}

function basename(path: string): string {
  const parts = path.split('/').filter(Boolean)
  return parts[parts.length - 1] || path
}

function toQuestFileApiResponse(projectId: string, item: QuestMutationItem): FileAPIResponse {
  const updatedAt = item.updated_at || nowIso()
  const currentParentPath = parentPath(item.path)

  if (item.kind === 'directory') {
    return {
      id: encodeQuestDirId(projectId, item.path),
      name: item.name,
      type: 'folder',
      folder_kind: item.folder_kind,
      parent_id: currentParentPath ? encodeQuestDirId(projectId, currentParentPath) : null,
      path: item.path,
      created_at: updatedAt,
      updated_at: updatedAt,
      project_id: projectId,
    }
  }

  const documentId = item.document_id || `path::${item.path}`
  return {
    id: encodeQuestFileId(projectId, documentId, item.path),
    name: item.name,
    type: 'file',
    parent_id: currentParentPath ? encodeQuestDirId(projectId, currentParentPath) : null,
    path: item.path,
    size: item.size,
    mime_type: item.mime_type || mimeTypeForPath(item.path, item.open_kind),
    created_at: updatedAt,
    updated_at: updatedAt,
    project_id: projectId,
  }
}

function resolveQuestParentPath(parentId?: string | null): string | null {
  if (!parentId) return null
  const ref = parseQuestNodeId(parentId)
  if (!ref) {
    throw new Error(`Unknown quest parent id: ${parentId}`)
  }
  return ref.type === 'dir' ? ref.path : parentPath(ref.path)
}

function resolveQuestNodePath(nodeId: string): string {
  const ref = parseQuestNodeId(nodeId)
  if (!ref) {
    throw new Error(`Unknown quest node id: ${nodeId}`)
  }
  return ref.path
}

function resolveQuestProjectId(nodeIds: string[]): string {
  const first = nodeIds[0]
  const projectId = first ? getQuestNodeProjectId(first) : null
  if (!projectId) {
    throw new Error('Quest node id is required.')
  }
  for (const nodeId of nodeIds) {
    if (getQuestNodeProjectId(nodeId) !== projectId) {
      throw new Error('Quest file operations must stay within one project.')
    }
  }
  return projectId
}

function ensureDirectory(
  projectId: string,
  directoryPath: string,
  items: Map<string, CachedQuestFile>,
  timestamps: { createdAt: string; updatedAt: string }
) {
  if (!directoryPath) return

  const pathParts = directoryPath.split('/').filter(Boolean)
  for (let index = 0; index < pathParts.length; index += 1) {
    const currentPath = pathParts.slice(0, index + 1).join('/')
    const parent = index === 0 ? null : pathParts.slice(0, index).join('/')
    const id = encodeQuestDirId(projectId, currentPath)
    if (items.has(id)) continue
    const node: CachedQuestFile = {
      id,
      name: pathParts[index],
      type: 'folder',
      parent_id: parent ? encodeQuestDirId(projectId, parent) : null,
      path: currentPath,
      created_at: timestamps.createdAt,
      updated_at: timestamps.updatedAt,
      project_id: projectId,
    }
    items.set(id, node)
    fileCache.set(id, node)
  }
}

export function flattenQuestExplorerPayload(
  projectId: string,
  payload: ExplorerPayload
): FileTreeResponse {
  const createdAt = nowIso()
  const items = new Map<string, CachedQuestFile>()

  function visit(node: ExplorerNode) {
    const updatedAt = node.updated_at || createdAt
    const timestamps = { createdAt, updatedAt }
    const currentParentPath = parentPath(node.path)

    if (currentParentPath) {
      ensureDirectory(projectId, currentParentPath, items, timestamps)
    }

    if (node.kind === 'directory') {
      const id = encodeQuestDirId(projectId, node.path)
      const meta: CachedQuestFile = {
        id,
        name: node.name,
        type: 'folder',
        folder_kind: node.folder_kind,
        parent_id: currentParentPath ? encodeQuestDirId(projectId, currentParentPath) : null,
        path: node.path,
        created_at: createdAt,
        updated_at: updatedAt,
        project_id: projectId,
      }
      items.set(id, meta)
      fileCache.set(id, meta)
      for (const child of node.children || []) {
        visit(child)
      }
      return
    }

    const documentId = node.document_id || `path::${node.path}`
    const id = encodeQuestFileId(projectId, documentId, node.path)
    const meta: CachedQuestFile = {
      id,
      name: node.name,
      type: 'file',
      parent_id: currentParentPath ? encodeQuestDirId(projectId, currentParentPath) : null,
      path: node.path,
      size: node.size,
      mime_type: mimeTypeForPath(node.path, node.open_kind),
      created_at: createdAt,
      updated_at: updatedAt,
      project_id: projectId,
      document_id: documentId,
    }
    items.set(id, meta)
    fileCache.set(id, meta)
  }

  for (const section of payload.sections) {
    for (const node of section.nodes) {
      visit(node)
    }
  }

  const files = Array.from(items.values()).sort((left, right) => {
    if (left.type !== right.type) {
      return left.type === 'folder' ? -1 : 1
    }
    return (left.path || left.name).localeCompare(right.path || right.name)
  })

  return {
    files,
    total: files.length,
  }
}

async function loadQuestTree(projectId: string, force = false): Promise<FileTreeResponse> {
  if (force) {
    invalidateQuestFileTree(projectId)
  }
  const cached = treeCache.get(projectId)
  if (!force && cached && cached.expiresAt > Date.now()) {
    return cached.payload
  }
  const inFlight = treeInFlight.get(projectId)
  if (inFlight) {
    return inFlight
  }

  const promise = questClient
    .explorer(projectId, { profile: 'workspace' })
    .then((explorer) => {
      const payload = flattenQuestExplorerPayload(projectId, explorer)
      treeCache.set(projectId, {
        expiresAt: Date.now() + TREE_CACHE_TTL_MS,
        payload,
      })
      return payload
    })
    .finally(() => {
      if (treeInFlight.get(projectId) === promise) {
        treeInFlight.delete(projectId)
      }
    })

  treeInFlight.set(projectId, promise)
  return promise
}

export function invalidateQuestFileTree(projectId?: string | null) {
  const normalizedProjectId = typeof projectId === 'string' ? projectId.trim() : ''
  if (!normalizedProjectId) {
    treeCache.clear()
    treeInFlight.clear()
    fileCache.clear()
    return
  }

  treeCache.delete(normalizedProjectId)
  treeInFlight.delete(normalizedProjectId)
  for (const key of Array.from(fileCache.keys())) {
    const ref = parseQuestNodeId(key)
    if (ref?.projectId === normalizedProjectId) {
      fileCache.delete(key)
    }
  }
}

function getCachedFile(fileId: string) {
  return fileCache.get(fileId) || null
}

function upsertFileFromDocument(fileId: string, ref: Extract<QuestNodeRef, { type: 'file' }>, document: OpenDocumentPayload) {
  const current = getCachedFile(fileId)
  const next: CachedQuestFile = {
    id: fileId,
    name: basename(ref.path),
    type: 'file',
    parent_id: parentPath(ref.path) ? encodeQuestDirId(ref.projectId, parentPath(ref.path) || '') : null,
    path: ref.path,
    size: document.size_bytes ?? current?.size,
    mime_type: document.mime_type || current?.mime_type || mimeTypeForPath(ref.path, document.kind),
    created_at: current?.created_at || document.updated_at || nowIso(),
    updated_at: document.updated_at || nowIso(),
    project_id: ref.projectId,
    document_id: ref.documentId,
  }
  fileCache.set(fileId, next)
  return next
}

function resolveQuestDocumentPath(document: OpenDocumentPayload): string | null {
  if (typeof document.path === 'string' && document.path.trim()) {
    return document.path.trim()
  }
  if (document.document_id.startsWith('path::')) {
    const candidate = document.document_id.slice('path::'.length).trim()
    return candidate || null
  }
  if (document.document_id.startsWith('questpath::')) {
    const candidate = document.document_id.slice('questpath::'.length).trim()
    return candidate || null
  }
  return null
}

export async function listQuestFiles(
  projectId: string,
  parentId?: string | null,
  options: QuestTreeOptions = {}
): Promise<FileAPIResponse[]> {
  const tree = await loadQuestTree(projectId, options.force === true)
  if (parentId === undefined || parentId === null) {
    return tree.files.filter((item) => item.parent_id === null)
  }
  return tree.files.filter((item) => item.parent_id === parentId)
}

export async function getQuestFileTree(
  projectId: string,
  options: QuestTreeOptions = {}
): Promise<FileTreeResponse> {
  return await loadQuestTree(projectId, options.force === true)
}

export async function getQuestFile(fileId: string): Promise<FileAPIResponse> {
  const cached = getCachedFile(fileId)
  if (cached) {
    return cached
  }
  const ref = parseQuestNodeId(fileId)
  if (!ref) {
    throw new Error(`Unknown quest file id: ${fileId}`)
  }
  if (ref.type === 'dir') {
    const updatedAt = nowIso()
    const next: CachedQuestFile = {
      id: fileId,
      name: basename(ref.path),
      type: 'folder',
      parent_id: parentPath(ref.path) ? encodeQuestDirId(ref.projectId, parentPath(ref.path) || '') : null,
      path: ref.path,
      created_at: updatedAt,
      updated_at: updatedAt,
      project_id: ref.projectId,
    }
    fileCache.set(fileId, next)
    return next
  }

  const document = await questClient.openDocument(ref.projectId, ref.documentId)
  return upsertFileFromDocument(fileId, ref, document)
}

export async function openQuestNodeDocument(fileId: string): Promise<OpenDocumentPayload> {
  const ref = parseQuestNodeId(fileId)
  if (!ref || ref.type !== 'file') {
    throw new Error('Only quest files can be opened as documents.')
  }
  const document = await questClient.openDocument(ref.projectId, ref.documentId)
  upsertFileFromDocument(fileId, ref, document)
  return document
}

export function buildQuestFileNodeFromDocument(
  projectId: string,
  document: OpenDocumentPayload
): FileNode | null {
  const path = resolveQuestDocumentPath(document)
  if (!path) {
    return null
  }
  const ref: Extract<QuestNodeRef, { type: 'file' }> = {
    type: 'file',
    projectId,
    documentId: document.document_id,
    path,
  }
  const fileId = encodeQuestFileId(projectId, document.document_id, path)
  return transformToFileNode(upsertFileFromDocument(fileId, ref, document))
}

export async function openQuestDocumentAsFileNode(
  projectId: string,
  documentId: string
): Promise<FileNode> {
  if (isDemoProjectId(projectId)) {
    const demoNode = openDemoDocumentAsFileNode(projectId, documentId)
    if (!demoNode) {
      throw new Error(`Cannot resolve demo file node for document ${documentId}`)
    }
    return demoNode
  }
  const document = await questClient.openDocument(projectId, documentId)
  const node = buildQuestFileNodeFromDocument(projectId, document)
  if (!node) {
    throw new Error(`Cannot resolve quest file node for document ${documentId}`)
  }
  return node
}

export async function getQuestFileContent(fileId: string): Promise<string> {
  const ref = parseQuestNodeId(fileId)
  if (!ref || ref.type !== 'file') {
    throw new Error('Only quest files can be opened as text.')
  }
  const document = await questClient.openDocument(ref.projectId, ref.documentId)
  upsertFileFromDocument(fileId, ref, document)
  return document.content || ''
}

export async function getQuestFileContentSnapshot(fileId: string): Promise<QuestFileContentSnapshot> {
  const ref = parseQuestNodeId(fileId)
  if (!ref || ref.type !== 'file') {
    throw new Error('Only quest files can be opened as text.')
  }
  const document = await questClient.openDocument(ref.projectId, ref.documentId)
  upsertFileFromDocument(fileId, ref, document)
  return {
    file_id: fileId,
    content: document.content || '',
    revision: typeof document.revision === 'string' ? document.revision : null,
    updated_at: typeof document.updated_at === 'string' ? document.updated_at : null,
    size: typeof document.size_bytes === 'number' ? document.size_bytes : undefined,
    mime_type: document.mime_type ?? null,
    project_id: ref.projectId,
  }
}

export async function getQuestFileTextPreview(
  fileId: string,
  maxChars = 4000
): Promise<FileTextPreviewResponse> {
  const meta = await getQuestFile(fileId)
  const content = await getQuestFileContent(fileId)
  const truncated = content.length > maxChars
  return {
    file_id: fileId,
    name: meta.name,
    mime_type: meta.mime_type ?? 'text/plain',
    size: meta.size ?? content.length,
    content: truncated ? `${content.slice(0, maxChars)}\n…` : content,
    truncated,
    encoding: 'utf-8',
  }
}

export async function updateQuestFileContent(
  fileId: string,
  content: string,
  options: QuestFileSaveOptions = {}
): Promise<FileAPIResponse & { revision?: string | null; conflict?: boolean; current_revision?: string | null }> {
  const ref = parseQuestNodeId(fileId)
  if (!ref || ref.type !== 'file') {
    throw new Error('Only quest files can be saved.')
  }
  const expectedRevision =
    options.force === true
      ? undefined
      : options.revision === null
        ? undefined
        : options.revision
  const saved = await questClient.saveDocument(ref.projectId, ref.documentId, content, expectedRevision)
  const updated = saved.updated_payload
  if (!saved.ok || !updated) {
    const error = new Error(saved.message || 'Failed to save quest file.') as Error & {
      conflict?: boolean
      currentRevision?: string | null
      updatedPayload?: OpenDocumentPayload
    }
    error.conflict = Boolean(saved.conflict)
    error.currentRevision = typeof saved.current_revision === 'string' ? saved.current_revision : null
    error.updatedPayload = updated
    throw error
  }
  treeCache.delete(ref.projectId)
  return {
    ...upsertFileFromDocument(fileId, ref, updated),
    revision: typeof saved.revision === 'string'
      ? saved.revision
      : typeof updated.revision === 'string'
        ? updated.revision
        : null,
    conflict: false,
  }
}

export async function getQuestFileBlob(fileId: string): Promise<Blob> {
  const ref = parseQuestNodeId(fileId)
  if (!ref || ref.type !== 'file') {
    throw new Error('Only quest files can be downloaded.')
  }
  const document = await questClient.openDocument(ref.projectId, ref.documentId)
  upsertFileFromDocument(fileId, ref, document)
  if (document.asset_url) {
    const response = await fetch(document.asset_url)
    if (!response.ok) {
      throw new Error(`Failed to fetch asset for ${document.title}.`)
    }
    return await response.blob()
  }
  return new Blob([document.content || ''], {
    type: document.mime_type || mimeTypeForPath(ref.path, document.kind),
  })
}

export function getQuestNodeAssetUrl(fileId: string): string {
  const ref = parseQuestNodeId(fileId)
  if (!ref || ref.type !== 'file') {
    throw new Error('Only quest files can resolve an asset URL.')
  }
  return `/api/quests/${ref.projectId}/documents/asset?document_id=${encodeURIComponent(ref.documentId)}`
}

export async function createQuestFolder(
  projectId: string,
  name: string,
  parentId?: string | null
): Promise<FileAPIResponse> {
  const parentPath = resolveQuestParentPath(parentId)
  const payload = await questClient.createQuestFolder(projectId, {
    name,
    parent_path: parentPath,
  })
  invalidateQuestFileTree(projectId)
  return toQuestFileApiResponse(projectId, payload.item)
}

export async function uploadQuestFile(
  projectId: string,
  file: File,
  parentId?: string | null,
  onProgress?: (progress: number) => void
): Promise<FileAPIResponse> {
  const contentBase64 = await fileToBase64(file)
  onProgress?.(25)
  const payload = await questClient.uploadQuestFile(projectId, {
    file_name: file.name,
    mime_type: file.type || undefined,
    parent_path: resolveQuestParentPath(parentId),
    content_base64: contentBase64,
  })
  onProgress?.(100)
  invalidateQuestFileTree(projectId)
  return toQuestFileApiResponse(projectId, payload.item)
}

export async function renameQuestNode(
  fileId: string,
  newName: string
): Promise<FileAPIResponse> {
  const projectId = resolveQuestProjectId([fileId])
  const payload = await questClient.renameQuestFile(projectId, {
    path: resolveQuestNodePath(fileId),
    new_name: newName,
  })
  invalidateQuestFileTree(projectId)
  return toQuestFileApiResponse(projectId, payload.item)
}

export async function moveQuestNodes(
  fileIds: string[],
  targetParentId: string | null
): Promise<void> {
  if (fileIds.length === 0) return
  const projectId = resolveQuestProjectId(fileIds)
  await questClient.moveQuestFiles(projectId, {
    paths: fileIds.map((fileId) => resolveQuestNodePath(fileId)),
    target_parent_path: resolveQuestParentPath(targetParentId),
  })
  invalidateQuestFileTree(projectId)
}

export async function deleteQuestNodes(fileIds: string[]): Promise<void> {
  if (fileIds.length === 0) return
  const projectId = resolveQuestProjectId(fileIds)
  await questClient.deleteQuestFiles(projectId, {
    paths: fileIds.map((fileId) => resolveQuestNodePath(fileId)),
  })
  invalidateQuestFileTree(projectId)
}

async function fileToBase64(file: File): Promise<string> {
  return await new Promise<string>((resolve, reject) => {
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

export async function uploadQuestDocumentAsset(
  projectId: string,
  documentId: string,
  file: File,
  kind = 'image'
): Promise<QuestDocumentAssetUploadPayload> {
  const contentBase64 = await fileToBase64(file)
  const payload = await questClient.uploadDocumentAsset(projectId, {
    document_id: documentId,
    file_name: file.name,
    mime_type: file.type || undefined,
    kind,
    content_base64: contentBase64,
  })
  if (!payload.ok) {
    throw new Error(payload.message || 'Failed to upload quest document asset.')
  }
  treeCache.delete(projectId)
  return payload
}
