import type { FileNode } from '@/lib/types/file'
import type { TabContext } from '@/lib/types/tab'

export const LATEX_OPEN_FILE_EVENT = 'ds:latex:open-file'

export type LatexOpenFileRequest = {
  projectId?: string
  latexFolderId?: string
  fileId?: string | null
  filePath?: string | null
  line?: number | null
  column?: number | null
  word?: string | null
}

const pendingRequests: LatexOpenFileRequest[] = []

function sameLatexProject(request: LatexOpenFileRequest, projectId?: string, latexFolderId?: string) {
  if (!request.latexFolderId || !latexFolderId || request.latexFolderId !== latexFolderId) return false
  if (request.projectId && projectId && request.projectId !== projectId) return false
  return true
}

export function queueLatexOpenFile(request: LatexOpenFileRequest) {
  pendingRequests.push(request)
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(LATEX_OPEN_FILE_EVENT, { detail: request }))
  }
}

export function consumeLatexOpenFileRequests(projectId?: string, latexFolderId?: string) {
  if (!latexFolderId) return []
  const matched: LatexOpenFileRequest[] = []
  for (let index = pendingRequests.length - 1; index >= 0; index -= 1) {
    const request = pendingRequests[index]
    if (!sameLatexProject(request, projectId, latexFolderId)) continue
    pendingRequests.splice(index, 1)
    matched.unshift(request)
  }
  return matched
}

export function buildLatexTabContext(args: {
  projectId: string
  latexFolder: FileNode
  readOnly?: boolean
}): TabContext {
  const { projectId, latexFolder, readOnly } = args
  return {
    type: 'custom',
    resourceId: latexFolder.id,
    resourceName: latexFolder.name,
    resourcePath: latexFolder.path ? `/FILES/${latexFolder.path.replace(/^\/+/, '')}` : undefined,
    customData: {
      kind: 'latex-workspace',
      projectId,
      latexFolderId: latexFolder.id,
      readOnly: Boolean(readOnly),
    },
  }
}

export function findLatexRootFolderForFile(
  file: FileNode,
  findNode: (nodeId: string) => FileNode | null | undefined,
): FileNode | null {
  let currentId: string | null = file.parentId
  let found: FileNode | null = null
  while (currentId) {
    const parent = findNode(currentId)
    if (!parent) break
    if (parent.type === 'folder' && parent.folderKind === 'latex') {
      found = parent
    }
    currentId = parent.parentId
  }
  return found
}

export function isLatexSourceFileName(fileName: string): boolean {
  const lower = fileName.toLowerCase()
  return (
    lower.endsWith('.tex') ||
    lower.endsWith('.bib') ||
    lower.endsWith('.cls') ||
    lower.endsWith('.sty') ||
    lower.endsWith('.bst') ||
    lower.endsWith('.bbx') ||
    lower.endsWith('.cbx')
  )
}
