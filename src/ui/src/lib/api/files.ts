/**
 * File API Client
 *
 * API client for file operations including CRUD, upload, and download
 *
 * @module api/files
 */

import { apiClient } from "./client";
import { downloadCliFile, readCliFile, writeCliFile } from "@/lib/api/cli";
import { getCliFileName, parseCliFileId } from "@/lib/api/cli-file-id";
import {
  buildDemoFileTree,
  getDemoFile,
  getDemoFileContent,
  isDemoFileId,
} from "@/demo/adapter";
import {
  buildQuestFileIdFromDocument,
  createQuestFolder,
  deleteQuestNodes,
  getQuestFile,
  getQuestFileBlob,
  getQuestFileContent,
  getQuestFileContentSnapshot,
  getQuestFileTextPreview,
  getQuestFileTree,
  getQuestNodeAssetUrl,
  isQuestNodeId,
  listQuestFiles,
  moveQuestNodes,
  renameQuestNode,
  uploadQuestFile,
  updateQuestFileContent,
} from "@/lib/api/quest-files";
import { client as questClient } from "@/lib/api";
import type {
  FileAPIResponse,
  FileTreeResponse,
  FileSearchParams,
  FileSearchResponse,
  CreateFolderRequest,
  RenameRequest,
  MoveRequest,
  DeleteRequest,
  MultipartUploadInit,
  UploadPart,
} from "@/lib/types/file";

const FILES_BASE = "/api/v1/files";

export interface FileContentOptions {
  /** When true, backend responds with Content-Disposition: attachment */
  download?: boolean;
}

export interface FileTextPreviewResponse {
  file_id: string;
  name: string;
  mime_type?: string | null;
  size?: number | null;
  content: string;
  truncated: boolean;
  encoding: string;
}

export interface FileContentSnapshot {
  file_id: string;
  content: string;
  revision?: string | null;
  updated_at?: string | null;
  size?: number;
  mime_type?: string | null;
  project_id?: string;
}

export interface FileSaveOptions {
  revision?: string | null;
  force?: boolean;
}

/**
 * List files in a directory
 */
export async function listFiles(
  projectId: string,
  parentId?: string | null
): Promise<FileAPIResponse[]> {
  return await listQuestFiles(projectId, parentId);
}

/**
 * Get complete file tree for a project
 *
 * Note: Backend returns `FileTreeNode[]` directly (already nested structure).
 * We convert it to `FileTreeResponse` format for consistency with the rest of the API.
 */
export async function getFileTree(
  projectId: string,
  options: { force?: boolean } = {}
): Promise<FileTreeResponse> {
  const demoTree = buildDemoFileTree(projectId);
  if (demoTree) {
    return demoTree;
  }
  return await getQuestFileTree(projectId, options);
}

/**
 * Search files by glob pattern
 */
export async function searchFiles(
  projectId: string,
  params: FileSearchParams
): Promise<FileSearchResponse> {
  const payload = await questClient.search(projectId, params.pattern, params.limit ?? 50);
  const normalizedDir = params.dir_path?.trim().replace(/^\/+/, "").replace(/\/+$/, "") || "";
  const items = payload.items
    .filter((item) =>
      normalizedDir ? item.path === normalizedDir || item.path.startsWith(`${normalizedDir}/`) : true
    )
    .map((item) => ({
      id: buildQuestFileIdFromDocument(projectId, item.document_id, item.path),
      path: item.path,
      name: item.title,
      type: "file" as const,
      size: undefined,
      mime_type: item.mime_type,
      updated_at: undefined,
    }));
  return {
    items,
    total: items.length,
    truncated: payload.truncated,
  };
}

/**
 * Flatten nested file tree to flat list for buildFileTree function
 */
function flattenFileTree(nodes: FileAPIResponse[]): FileAPIResponse[] {
  const result: FileAPIResponse[] = [];

  const flatten = (items: FileAPIResponse[]) => {
    for (const item of items) {
      const raw = item as unknown as {
        mimeType?: string;
        parentId?: string | null;
        createdAt?: string;
        updatedAt?: string;
        folderKind?: string;
        latex?: { mainFileId?: string | null } | null;
        children?: unknown;
        isDeleted?: boolean;
      };

      // Add the item itself
      result.push({
        id: item.id,
        name: item.name,
        type: item.type,
        folder_kind: raw.folderKind,
        latex: raw.latex ?? null,
        mime_type: raw.mimeType ?? item.mime_type,
        size: item.size,
        parent_id: raw.parentId ?? item.parent_id,
        path: item.path,
        created_at: raw.createdAt || item.created_at,
        updated_at: raw.updatedAt || item.updated_at,
        is_deleted: raw.isDeleted ?? item.is_deleted,
      });

      // Recursively flatten children
      const children = raw.children;
      if (children && Array.isArray(children)) {
        flatten(children as FileAPIResponse[]);
      }
    }
  };

  flatten(nodes);
  return result;
}

/**
 * Get file details
 */
export async function getFile(fileId: string): Promise<FileAPIResponse> {
  if (isDemoFileId(fileId)) {
    const demoFile = getDemoFile(fileId);
    if (!demoFile) {
      throw new Error(`Unknown demo file \`${fileId}\`.`);
    }
    return demoFile;
  }
  if (isQuestNodeId(fileId)) {
    return await getQuestFile(fileId);
  }
  const response = await apiClient.get<FileAPIResponse>(
    `${FILES_BASE}/detail/${fileId}`
  );
  return response.data;
}

/**
 * Create a new folder
 */
export async function createFolder(
  projectId: string,
  data: CreateFolderRequest
): Promise<FileAPIResponse> {
  return await createQuestFolder(projectId, data.name, data.parent_id);
}

/**
 * Upload a small file (< 5MB)
 */
export async function uploadFile(
  projectId: string,
  file: File,
  parentId?: string | null,
  onProgress?: (progress: number) => void
): Promise<FileAPIResponse> {
  return await uploadQuestFile(projectId, file, parentId, onProgress);
}

/**
 * Initialize multipart upload for large files
 */
export async function initMultipartUpload(
  projectId: string,
  fileName: string,
  fileSize: number,
  mimeType: string,
  parentId?: string | null
): Promise<MultipartUploadInit> {
  const response = await apiClient.post<MultipartUploadInit>(
    `${FILES_BASE}/${projectId}/upload/init`,
    {
      file_name: fileName,
      file_size: fileSize,
      mime_type: mimeType,
      parent_id: parentId,
    }
  );
  return response.data;
}

/**
 * Complete multipart upload
 *
 * @param taskId - Upload task ID
 * @param parts - Array of uploaded parts with partNumber and etag
 */
export async function completeMultipartUpload(
  taskId: string,
  parts: UploadPart[]
): Promise<FileAPIResponse> {
  const response = await apiClient.post<FileAPIResponse>(
    `${FILES_BASE}/upload/complete`,
    {
      task_id: taskId,
      parts: parts.map((p) => ({
        partNumber: p.partNumber,
        etag: p.etag,
      })),
    }
  );
  return response.data;
}

/**
 * Abort multipart upload
 */
export async function abortMultipartUpload(taskId: string): Promise<void> {
  await apiClient.delete(`${FILES_BASE}/upload/${taskId}`);
}

/**
 * Get upload task status
 */
export async function getUploadStatus(
  taskId: string
): Promise<{ status: string; progress: number; uploaded_parts: number[] }> {
  const response = await apiClient.get(`${FILES_BASE}/upload/${taskId}`);
  return response.data;
}

/**
 * Rename a file or folder
 */
export async function renameFile(
  fileId: string,
  newName: string
): Promise<FileAPIResponse> {
  if (isQuestNodeId(fileId)) {
    return await renameQuestNode(fileId, newName);
  }
  const data: RenameRequest = { name: newName };
  const response = await apiClient.patch<FileAPIResponse>(
    `${FILES_BASE}/${fileId}/rename`,
    data
  );
  return response.data;
}

/**
 * Move files to a new parent folder
 */
export async function moveFiles(
  fileIds: string[],
  targetParentId: string | null
): Promise<void> {
  if (fileIds.length > 0 && isQuestNodeId(fileIds[0])) {
    await moveQuestNodes(fileIds, targetParentId);
    return;
  }
  const data: MoveRequest = {
    file_ids: fileIds,
    target_parent_id: targetParentId,
  };
  await apiClient.post(`${FILES_BASE}/move`, data);
}

/**
 * Delete files (soft delete by default)
 */
export async function deleteFiles(
  fileIds: string[],
  permanent: boolean = false
): Promise<void> {
  if (fileIds.length > 0 && isQuestNodeId(fileIds[0])) {
    await deleteQuestNodes(fileIds);
    return;
  }
  const data: DeleteRequest = {
    file_ids: fileIds,
    permanent,
  };
  await apiClient.post(`${FILES_BASE}/delete`, data);
}

/**
 * Restore soft-deleted files
 */
export async function restoreFiles(fileIds: string[]): Promise<void> {
  await apiClient.post(`${FILES_BASE}/restore`, { file_ids: fileIds });
}

/**
 * Get file content as text
 */
export async function getFileContent(fileId: string): Promise<string> {
  if (isDemoFileId(fileId)) {
    const demoContent = getDemoFileContent(fileId);
    if (demoContent == null) {
      throw new Error(`Unknown demo file content for \`${fileId}\`.`);
    }
    return demoContent;
  }
  const cliRef = parseCliFileId(fileId);
  if (cliRef) {
    const response = await readCliFile(cliRef.projectId, cliRef.serverId, cliRef.path);
    return response.content;
  }
  if (isQuestNodeId(fileId)) {
    return await getQuestFileContent(fileId);
  }
  const response = await apiClient.get(`${FILES_BASE}/${fileId}/content`, {
    responseType: "text",
  });
  return response.data as string;
}

/**
 * Get file content plus the backend revision used for optimistic save checks.
 */
export async function getFileContentSnapshot(fileId: string): Promise<FileContentSnapshot> {
  if (isDemoFileId(fileId)) {
    const demoContent = getDemoFileContent(fileId);
    if (demoContent == null) {
      throw new Error(`Unknown demo file content for \`${fileId}\`.`);
    }
    return {
      file_id: fileId,
      content: demoContent,
      revision: null,
      updated_at: null,
      size: demoContent.length,
      mime_type: "text/plain",
    };
  }
  const cliRef = parseCliFileId(fileId);
  if (cliRef) {
    const response = await readCliFile(cliRef.projectId, cliRef.serverId, cliRef.path);
    return {
      file_id: fileId,
      content: response.content,
      revision: response.modified_at ? `modified:${response.modified_at}` : null,
      updated_at: response.modified_at ?? null,
      size: typeof response.size === "number" ? response.size : response.content.length,
      mime_type: "text/plain",
      project_id: cliRef.projectId,
    };
  }
  if (isQuestNodeId(fileId)) {
    return await getQuestFileContentSnapshot(fileId);
  }
  const content = await getFileContent(fileId);
  return {
    file_id: fileId,
    content,
    revision: null,
    updated_at: null,
    size: content.length,
    mime_type: "text/plain",
  };
}

/**
 * Get a truncated text preview for a file.
 */
export async function getFileTextPreview(
  fileId: string,
  options: { maxChars?: number; maxBytes?: number; encoding?: string } = {}
): Promise<FileTextPreviewResponse> {
  if (isQuestNodeId(fileId)) {
    return await getQuestFileTextPreview(fileId, options.maxChars ?? options.maxBytes ?? 4000);
  }
  const response = await apiClient.get(`${FILES_BASE}/${fileId}/preview`, {
    params: {
      max_chars: options.maxChars,
      max_bytes: options.maxBytes,
      encoding: options.encoding,
    },
  });
  return response.data as FileTextPreviewResponse;
}

/**
 * Update file content (text files)
 *
 * Backend should persist bytes and return updated file metadata.
 */
export async function updateFileContent(
  fileId: string,
  content: string,
  options: FileSaveOptions = {}
): Promise<FileAPIResponse & { checksum?: string; project_id?: string; revision?: string | null; conflict?: boolean; current_revision?: string | null }> {
  const cliRef = parseCliFileId(fileId);
  if (cliRef) {
    await writeCliFile(cliRef.projectId, cliRef.serverId, {
      path: cliRef.path,
      content,
      operation: "write",
    });
    let updatedAt = new Date().toISOString();
    let size = content.length;
    try {
      const readback = await readCliFile(cliRef.projectId, cliRef.serverId, cliRef.path);
      if (readback?.modified_at) {
        updatedAt = String(readback.modified_at);
      }
      if (typeof readback?.size === "number") {
        size = readback.size;
      }
    } catch {
      // Ignore readback errors for CLI writes.
    }
    return {
      id: fileId,
      name: getCliFileName(cliRef.path),
      type: "file",
      parent_id: null,
      path: cliRef.path,
      size,
      created_at: updatedAt,
      updated_at: updatedAt,
      project_id: cliRef.projectId,
    };
  }
  if (isQuestNodeId(fileId)) {
    return await updateQuestFileContent(fileId, content, options);
  }
  const response = await apiClient.put(
    `${FILES_BASE}/${fileId}/content`,
    { content },
    { headers: { "Content-Type": "application/json" } }
  );
  return response.data as FileAPIResponse & { checksum?: string; project_id?: string };
}

/**
 * Get file content as blob (for binary files)
 */
export async function getFileBlob(
  fileId: string,
  options: FileContentOptions = {}
): Promise<Blob> {
  const cliRef = parseCliFileId(fileId);
  if (cliRef) {
    return await downloadCliFile(cliRef.projectId, cliRef.serverId, cliRef.path);
  }
  if (isQuestNodeId(fileId)) {
    return await getQuestFileBlob(fileId);
  }
  const response = await apiClient.get(`${FILES_BASE}/${fileId}/content`, {
    responseType: "blob",
    params: { download: options.download ? true : undefined },
  });
  return response.data as Blob;
}

export function resolveFileContentUrl(
  fileId: string,
  options: FileContentOptions = {}
): string {
  if (isQuestNodeId(fileId)) {
    return getQuestNodeAssetUrl(fileId);
  }
  const params = new URLSearchParams();
  if (options.download) {
    params.set("download", "true");
  }
  const suffix = params.toString();
  return `${FILES_BASE}/${fileId}/content${suffix ? `?${suffix}` : ""}`;
}

/**
 * Create an object URL for a file (caller should revoke when done)
 */
export async function createFileObjectUrl(
  fileId: string,
  options: FileContentOptions = {}
): Promise<string> {
  const blob = await getFileBlob(fileId, options);
  return URL.createObjectURL(blob);
}

/**
 * Download a file through the backend (token-validated).
 */
export async function downloadFileById(
  fileId: string,
  fileName: string
): Promise<void> {
  const cliRef = parseCliFileId(fileId);
  if (cliRef) {
    const blob = await downloadCliFile(cliRef.projectId, cliRef.serverId, cliRef.path);
    const url = URL.createObjectURL(blob);
    try {
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      link.remove();
    } finally {
      URL.revokeObjectURL(url);
    }
    return;
  }
  const blob = await getFileBlob(fileId, { download: true });
  const url = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

/**
 * Upload file with automatic chunking for large files
 */
export async function uploadFileAuto(
  projectId: string,
  file: File,
  parentId?: string | null,
  onProgress?: (progress: number) => void
): Promise<FileAPIResponse> {
  return await uploadFile(projectId, file, parentId, onProgress);
}
