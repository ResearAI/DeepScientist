import { useFileTreeStore } from '@/lib/stores/file-tree'
import { useAdminIssueDraftStore } from '@/lib/stores/admin-issue-draft'
import { useTabsStore } from '@/lib/stores/tabs'
import type { FileNode } from '@/lib/types/file'
import type { TabContext } from '@/lib/types/tab'
import { BUILTIN_PLUGINS, getPluginIdFromExtension, getPluginIdFromMimeType } from '@/lib/types/plugin'
import { toFilesResourcePath } from '@/lib/utils/resource-paths'
import type { NormalizedCitation } from '@/lib/types/citations'
import type {
  Effect,
  FileEffectData,
  FileJumpEffectData,
  PdfAnnotationEffectData,
  PdfJumpEffectData,
  RouteNavigateEffectData,
  StartSetupPatchEffectData,
} from '@/lib/types/ui-effects'
import { queueFileJumpEffect } from '@/lib/ai/file-jump-queue'
import { queuePdfEffect } from '@/lib/ai/pdf-effect-queue'

type UIEffectContext = {
  surface?: 'welcome' | 'copilot' | 'lab-direct' | 'lab-group' | 'lab-friends'
}

type PdfFileReference = {
  fileId?: string
  filePath?: string
  fileName?: string
}

export type PdfToolPreview = PdfFileReference & {
  page?: number
  annotationId?: string
  mode?: 'guide' | 'annotate'
}

const PDF_QUEUE_EVENT = 'ds:pdf:queue'
const FILE_QUEUE_EVENT = 'ds:file:queue'
const FILE_JUMP_EVENT = 'ds:file:jump'
const ROUTE_NAVIGATE_EVENT = 'ds:route:navigate'
const START_SETUP_PATCH_EVENT = 'ds:start-setup:patch'

function dispatchCustomEvent(name: string, detail: unknown) {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(name, { detail }))
}

function requestCopilotOpen() {
  dispatchCustomEvent('ds:copilot:open', { source: 'ui-effect' })
}

function findLatexFolderForFile(file: FileNode): FileNode | null {
  if (!file.parentId) return null
  const findNode = useFileTreeStore.getState().findNode
  let currentId: string | null = file.parentId
  while (currentId) {
    const parent = findNode(currentId)
    if (!parent) return null
    if (parent.type === 'folder' && parent.folderKind === 'latex') {
      return parent
    }
    currentId = parent.parentId
  }
  return null
}

function isLatexSourceFile(filename: string): boolean {
  const lower = filename.toLowerCase()
  return lower.endsWith('.tex') || lower.endsWith('.bib')
}

function isMarkdownFileName(filename: string): boolean {
  const lower = filename.toLowerCase()
  return lower.endsWith('.md') || lower.endsWith('.markdown') || lower.endsWith('.mdx')
}

function resolvePluginId(file: FileNode, options?: { preferEditor?: boolean }): string | null {
  if (file.type === 'notebook') return BUILTIN_PLUGINS.NOTEBOOK
  const extPluginId = getPluginIdFromExtension(file.name)
  if (extPluginId === BUILTIN_PLUGINS.NOTEBOOK && isMarkdownFileName(file.name)) {
    return extPluginId
  }
  if (file.mimeType) {
    const mimePluginId = getPluginIdFromMimeType(file.mimeType)
    if (mimePluginId) {
      if (mimePluginId === BUILTIN_PLUGINS.TEXT_VIEWER && extPluginId) {
        return options?.preferEditor && extPluginId === BUILTIN_PLUGINS.CODE_VIEWER
          ? BUILTIN_PLUGINS.CODE_EDITOR
          : extPluginId
      }
      if (options?.preferEditor && mimePluginId === BUILTIN_PLUGINS.CODE_VIEWER) {
        return BUILTIN_PLUGINS.CODE_EDITOR
      }
      return mimePluginId
    }
  }
  if (options?.preferEditor && extPluginId === BUILTIN_PLUGINS.CODE_VIEWER) {
    return BUILTIN_PLUGINS.CODE_EDITOR
  }
  return extPluginId ?? null
}

function openFileInTab(file: FileNode, data: FileEffectData, options?: { preferEditor?: boolean }) {
  const tabsStore = useTabsStore.getState()
  const projectId = data.projectId ?? useFileTreeStore.getState().projectId ?? undefined

  if (projectId && isLatexSourceFile(file.name)) {
    const latexFolder = findLatexFolderForFile(file)
    if (latexFolder) {
      const tabId = tabsStore.openTab({
        pluginId: BUILTIN_PLUGINS.LATEX,
        context: {
          type: 'custom',
          resourceId: latexFolder.id,
          resourceName: latexFolder.name,
          customData: {
            projectId,
            latexFolderId: latexFolder.id,
            mainFileId: latexFolder.latex?.mainFileId ?? null,
            openFileId: file.id,
          },
        },
        title: latexFolder.name,
      })
      return tabId
    }
  }

  const pluginId = resolvePluginId(file, options)
  if (!pluginId) return null
  const context: TabContext = {
    type: file.type === 'notebook' ? 'notebook' : 'file',
    resourceId: file.id,
    resourcePath: file.path ? toFilesResourcePath(file.path) : undefined,
    resourceName: file.name,
    mimeType: file.mimeType,
    customData: projectId ? { projectId } : undefined,
  }
  const existing = tabsStore.findTabByContext(context)
  if (existing) {
    if (existing.pluginId !== pluginId) {
      tabsStore.updateTabPlugin(existing.id, pluginId, context)
    }
    tabsStore.setActiveTab(existing.id)
    return existing.id
  }
  return tabsStore.openTab({
    pluginId,
    context,
    title: file.name,
  })
}

function resolveFileNode(data: FileEffectData): FileNode | null {
  const store = useFileTreeStore.getState()
  if (data.fileId) {
    const node = store.findNode(data.fileId)
    if (node) return node
  }
  if (data.filePath) {
    const node = store.findNodeByPath(data.filePath)
    if (node) return node
  }
  return null
}

function normalizeEffectPath(path?: string): string {
  if (!path) return ''
  return path.replace(/^\/FILES\/?/, '').replace(/^\/+/, '').replace(/\/+$/, '')
}

function createPdfEffectId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `pdf-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

function withPdfEffectId<T extends Record<string, unknown>>(data: T): T & { __dsEffectId: string } {
  const effectId = createPdfEffectId()
  return { ...data, __dsEffectId: effectId }
}

function createFileEffectId(): string {
  return createPdfEffectId()
}

function isPdfNode(node: FileNode): boolean {
  if (node.type !== 'file') return false
  const name = node.name.toLowerCase()
  const mime = (node.mimeType ?? '').toLowerCase()
  return name.endsWith('.pdf') || mime === 'application/pdf'
}

function findPdfNodeByName(name: string): FileNode | null {
  const normalized = name.trim().toLowerCase()
  if (!normalized) return null
  const nodes = useFileTreeStore.getState().nodes
  const stack = [...nodes]
  while (stack.length > 0) {
    const node = stack.shift()
    if (!node) continue
    if (isPdfNode(node) && node.name.toLowerCase() === normalized) {
      return node
    }
    if (node.children?.length) {
      stack.push(...node.children)
    }
  }
  return null
}

function resolvePdfNode(ref: PdfFileReference): FileNode | null {
  const store = useFileTreeStore.getState()
  if (ref.fileId) {
    const node = store.findNode(ref.fileId)
    if (node && isPdfNode(node)) return node
  }
  if (ref.filePath) {
    const node = store.findNodeByPath(normalizeEffectPath(ref.filePath))
    if (node && isPdfNode(node)) return node
  }
  if (ref.fileName) {
    const normalizedName = normalizeEffectPath(ref.fileName)
    if (normalizedName.includes('/')) {
      const node = store.findNodeByPath(normalizedName)
      if (node && isPdfNode(node)) return node
    }
    return findPdfNodeByName(ref.fileName)
  }
  return null
}

function ensurePdfFileOpen(ref: PdfFileReference, onResolve?: (node: FileNode) => void): FileNode | null {
  const applyOpen = (node: FileNode) => {
    const store = useFileTreeStore.getState()
    store.expandToFile(node.id)
    openFileInTab(node, {
      fileId: node.id,
      filePath: node.path,
      fileName: node.name,
    })
    onResolve?.(node)
  }
  const node = resolvePdfNode(ref)
  if (node) {
    applyOpen(node)
    return node
  }
  const store = useFileTreeStore.getState()
  if (typeof store.refresh === 'function') {
    void store.refresh().then(() => {
      const refreshed = resolvePdfNode(ref)
      if (refreshed) applyOpen(refreshed)
    })
  }
  return null
}

function queuePdfUiEffect(
  name: 'pdf:jump' | 'annotation:created' | 'pdf:annotation_created',
  data: PdfJumpEffectData | PdfAnnotationEffectData
) {
  if (!data.fileId) return null
  const payload = withPdfEffectId(data)
  queuePdfEffect({ id: payload.__dsEffectId, name, data: payload })
  dispatchCustomEvent(PDF_QUEUE_EVENT, { fileId: payload.fileId })
  return payload
}

function queueFileJumpUiEffect(data: FileJumpEffectData) {
  if (!data.fileId) return null
  const payload = { ...data, __dsEffectId: createFileEffectId() }
  queueFileJumpEffect({ id: payload.__dsEffectId, data: payload })
  dispatchCustomEvent(FILE_QUEUE_EVENT, { fileId: payload.fileId })
  return payload
}

function handleFileHighlight(data: FileEffectData) {
  const node = resolveFileNode(data)
  if (!node) return
  const store = useFileTreeStore.getState()
  store.highlightFile(node.id)
  store.expandToFile(node.id)
}

function dispatchFileDiff(data: FileEffectData) {
  if (!data.diff) return
  dispatchCustomEvent('ds:file:diff', {
    ...data,
    changeType: data.changeType ?? (data.created ? 'create' : 'update'),
  })
}

function shouldAutoOpen(context?: UIEffectContext) {
  return context?.surface !== 'welcome'
}

function handleFileRead(data: FileEffectData, context?: UIEffectContext) {
  const applyRead = (node: FileNode) => {
    const store = useFileTreeStore.getState()
    store.markFileRead(node.id)
    store.highlightFile(node.id)
    store.expandToFile(node.id)
    if (shouldAutoOpen(context) && node.type !== 'folder') {
      requestCopilotOpen()
      openFileInTab(node, data, { preferEditor: true })
    }
  }
  const node = resolveFileNode(data)
  if (node) {
    applyRead(node)
    return
  }
  const store = useFileTreeStore.getState()
  if (typeof store.refresh === 'function') {
    void store.refresh().then(() => {
      const refreshed = resolveFileNode(data)
      if (refreshed) applyRead(refreshed)
    })
  }
}

function handleFileWrite(data: FileEffectData, context?: UIEffectContext) {
  const applyWrite = (node: FileNode) => {
    const store = useFileTreeStore.getState()
    store.markFileWrite(node.id)
    store.highlightFile(node.id)
    store.expandToFile(node.id)
    const willOpen = shouldAutoOpen(context)
    if (willOpen) {
      requestCopilotOpen()
      openFileInTab(node, data, { preferEditor: true })
    }
    if (data.diff) {
      if (typeof window === 'undefined') {
        dispatchFileDiff(data)
      } else {
        const delay = willOpen ? 180 : 0
        window.setTimeout(() => dispatchFileDiff(data), delay)
      }
    }
  }
  const node = resolveFileNode(data)
  if (node) {
    applyWrite(node)
    return
  }
  const store = useFileTreeStore.getState()
  if (typeof store.refresh === 'function') {
    void store.refresh().then(() => {
      const refreshed = resolveFileNode(data)
      if (refreshed) applyWrite(refreshed)
    })
  }
}

function handleFileOpen(data: FileEffectData) {
  const node = resolveFileNode(data)
  if (!node) return
  requestCopilotOpen()
  openFileInTab(node, data)
  handleFileHighlight({ ...data, fileId: node.id, filePath: node.path })
}

function handleFileJump(data: FileJumpEffectData) {
  const applyJump = (node: FileNode) => {
    const lineStart = data.lineStart ?? data.line ?? data.lineEnd
    const lineEnd = data.lineEnd ?? data.line ?? data.lineStart
    openFileInTab(node, data, { preferEditor: true })
    const payload = queueFileJumpUiEffect({
      ...data,
      fileId: node.id,
      fileName: node.name,
      filePath: node.path ?? data.filePath,
      lineStart,
      lineEnd,
    })
    if (payload) {
      dispatchCustomEvent(FILE_JUMP_EVENT, payload)
    } else {
      dispatchCustomEvent(FILE_JUMP_EVENT, {
        ...data,
        fileId: node.id,
        fileName: node.name,
        filePath: node.path ?? data.filePath,
        lineStart,
        lineEnd,
      })
    }
  }
  const node = resolveFileNode(data)
  if (node) {
    applyJump(node)
    return
  }
  const store = useFileTreeStore.getState()
  if (typeof store.refresh === 'function') {
    void store.refresh().then(() => {
      const refreshed = resolveFileNode(data)
      if (refreshed) applyJump(refreshed)
    })
  }
}

function handleFileDelete(data: FileEffectData, context?: UIEffectContext) {
  const store = useFileTreeStore.getState()
  if (typeof store.refresh === 'function') {
    void store.refresh()
  }
  dispatchFileDiff({ ...data, changeType: data.changeType ?? 'delete' })
  if (shouldAutoOpen(context)) {
    if (data.fileId || data.filePath) {
      dispatchCustomEvent('ds:file:deleted', data)
    }
  }
}

function handleFileMove(data: FileEffectData, context?: UIEffectContext) {
  const store = useFileTreeStore.getState()
  const targetPath = data.filePath || data.targetPath
  const applyMove = (node: FileNode) => {
    store.markFileMove(node.id)
    store.highlightFile(node.id)
    store.expandToFile(node.id)
    if (shouldAutoOpen(context) && node.type !== 'folder') {
      openFileInTab(node, data, { preferEditor: true })
    }
  }
  const node = resolveFileNode(data)
  if (node && targetPath && normalizeEffectPath(node.path) !== normalizeEffectPath(targetPath)) {
    if (typeof store.refresh === 'function') {
      void store.refresh().then(() => {
        const refreshed = resolveFileNode(data)
        if (refreshed) applyMove(refreshed)
      })
      return
    }
  }
  if (node) {
    applyMove(node)
    return
  }
  if (typeof store.refresh === 'function') {
    void store.refresh().then(() => {
      const refreshed = resolveFileNode(data)
      if (refreshed) applyMove(refreshed)
    })
  }
}

function handleFileRename(data: FileEffectData, context?: UIEffectContext) {
  const store = useFileTreeStore.getState()
  const targetPath = data.filePath || data.targetPath
  const applyRename = (node: FileNode) => {
    store.markFileRename(node.id)
    store.highlightFile(node.id)
    store.expandToFile(node.id)
    if (shouldAutoOpen(context) && node.type !== 'folder') {
      openFileInTab(node, data, { preferEditor: true })
    }
  }
  const node = resolveFileNode(data)
  if (node && targetPath && normalizeEffectPath(node.path) !== normalizeEffectPath(targetPath)) {
    if (typeof store.refresh === 'function') {
      void store.refresh().then(() => {
        const refreshed = resolveFileNode(data)
        if (refreshed) applyRename(refreshed)
      })
      return
    }
  }
  if (node) {
    applyRename(node)
    return
  }
  if (typeof store.refresh === 'function') {
    void store.refresh().then(() => {
      const refreshed = resolveFileNode(data)
      if (refreshed) applyRename(refreshed)
    })
  }
}

function handlePdfJump(data: PdfJumpEffectData) {
  const resolved = ensurePdfFileOpen({
    fileId: data.fileId,
    fileName: data.fileName,
  })
  const payload = queuePdfUiEffect('pdf:jump', {
    ...data,
    fileId: resolved?.id ?? data.fileId,
    fileName: data.fileName ?? resolved?.name,
  })
  if (payload) {
    dispatchCustomEvent('pdf:navigate', payload)
  } else {
    dispatchCustomEvent('pdf:navigate', data)
  }
}

function handlePdfAnnotationCreated(data: PdfAnnotationEffectData) {
  const resolved = ensurePdfFileOpen({
    fileId: data.fileId,
    fileName: data.fileName,
  })
  const payload = queuePdfUiEffect('pdf:annotation_created', {
    ...data,
    fileId: resolved?.id ?? data.fileId,
    fileName: data.fileName ?? resolved?.name,
  })
  if (payload) {
    dispatchCustomEvent('pdf:annotation_created', payload)
  } else {
    dispatchCustomEvent('pdf:annotation_created', data)
  }
}

export function previewPdfToolEffect(preview: PdfToolPreview) {
  if (!preview.fileId && !preview.filePath && !preview.fileName) return
  const hasLocation = preview.page !== undefined || preview.annotationId

  if (preview.fileId && hasLocation) {
    const payload = queuePdfUiEffect('pdf:jump', {
      fileId: preview.fileId,
      fileName: preview.fileName,
      page: preview.page,
      annotationId: preview.annotationId,
      mode: preview.mode,
    })
    if (payload) {
      dispatchCustomEvent('pdf:navigate', payload)
    }
    ensurePdfFileOpen(preview)
    return
  }

  if (hasLocation) {
    ensurePdfFileOpen(preview, (node) => {
      const payload = queuePdfUiEffect('pdf:jump', {
        fileId: node.id,
        fileName: node.name,
        page: preview.page,
        annotationId: preview.annotationId,
        mode: preview.mode,
      })
      if (payload) {
        dispatchCustomEvent('pdf:navigate', payload)
      }
    })
    return
  }

  ensurePdfFileOpen(preview)
}

function handleRouteNavigate(data: RouteNavigateEffectData) {
  const target = typeof data.to === 'string' ? data.to.trim() : ''
  if (data.issueDraft && typeof data.issueDraft === 'object') {
    const draft = data.issueDraft
    const title = typeof draft.title === 'string' ? draft.title : ''
    const bodyMarkdown = typeof draft.body_markdown === 'string' ? draft.body_markdown : ''
    const issueUrlBase = typeof draft.issue_url_base === 'string' ? draft.issue_url_base : ''
    const repoUrl = typeof draft.repo_url === 'string' ? draft.repo_url : ''
    if (title && bodyMarkdown && issueUrlBase && repoUrl) {
      useAdminIssueDraftStore.getState().setDraft({
        ok: draft.ok !== false,
        title,
        body_markdown: bodyMarkdown,
        issue_url_base: issueUrlBase,
        repo_url: repoUrl,
        ...(typeof draft.generated_at === 'string' ? { generated_at: draft.generated_at } : {}),
      })
    }
  }
  if (!target) return
  dispatchCustomEvent(ROUTE_NAVIGATE_EVENT, {
    to: target,
    replace: Boolean(data.replace),
  })
}

function handleStartSetupPatch(data: StartSetupPatchEffectData) {
  const patch = data.patch && typeof data.patch === 'object' && !Array.isArray(data.patch) ? data.patch : null
  if (!patch) return
  dispatchCustomEvent(START_SETUP_PATCH_EVENT, {
    patch,
    message: typeof data.message === 'string' ? data.message : undefined,
  })
}

export function openCitationTarget(citation: NormalizedCitation) {
  if (!citation) return
  const fileRef = {
    fileId: citation.fileId,
    filePath: citation.filePath,
    fileName: citation.fileName,
  }
  if (citation.page) {
    previewPdfToolEffect({ ...fileRef, page: citation.page })
    return
  }
  const lineStart = citation.lineStart ?? citation.lineEnd
  const lineEnd = citation.lineEnd ?? citation.lineStart
  if (lineStart || lineEnd) {
    handleFileJump({ ...fileRef, lineStart, lineEnd })
    return
  }
  const node = resolveFileNode({
    fileId: citation.fileId,
    filePath: citation.filePath,
  })
  if (!node) return
  openFileInTab(node, { fileId: node.id, filePath: node.path, fileName: node.name }, { preferEditor: true })
}

export function handleUIEffect(effect: Effect, context?: UIEffectContext) {
  const { name, data } = effect

  switch (name) {
    case 'file:highlight':
      handleFileHighlight(data as FileEffectData)
      return
    case 'file:read':
      handleFileRead(data as FileEffectData, context)
      return
    case 'file:write':
      handleFileWrite(data as FileEffectData, context)
      return
    case 'file:delete':
      handleFileDelete(data as FileEffectData, context)
      return
    case 'file:move':
      handleFileMove(data as FileEffectData, context)
      return
    case 'file:rename':
      handleFileRename(data as FileEffectData, context)
      return
    case 'file:open':
      handleFileOpen(data as FileEffectData)
      return
    case 'file:jump':
      handleFileJump(data as FileJumpEffectData)
      return
    case 'pdf:jump':
      handlePdfJump(data as PdfJumpEffectData)
      return
    case 'annotation:created':
    case 'pdf:annotation_created':
      handlePdfAnnotationCreated(data as PdfAnnotationEffectData)
      return
    case 'notebook:focus':
    case 'notebook:block_inserted':
      dispatchCustomEvent(name, data)
      return
    case 'route:navigate':
      handleRouteNavigate(data as RouteNavigateEffectData)
      return
    case 'start_setup:patch':
      handleStartSetupPatch(data as StartSetupPatchEffectData)
      return
    default:
      if (process.env.NODE_ENV !== 'production') {
        console.warn('[AiManus] Unhandled UI effect:', name, data)
      }
  }
}
