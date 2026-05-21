/**
 * LaTeX API Client (Stage 11_latex)
 */

import { apiClient } from "./client";

export type LatexCompiler = "pdflatex" | "xelatex" | "lualatex";

export interface LatexInitRequest {
  name: string;
  parent_id?: string | null;
  template?: string;
  compiler?: LatexCompiler;
}

export interface LatexInitCreatedItem {
  id: string;
  name: string;
  type: "folder" | "file" | "notebook" | string;
}

export interface LatexInitResponse {
  folder_id: string;
  main_file_id: string;
  created: LatexInitCreatedItem[];
}

export type LatexBuildStatus = "queued" | "running" | "success" | "error" | "canceled";

export interface LatexCompileRequest {
  compiler?: LatexCompiler;
  main_file_id?: string | null;
  stop_on_first_error?: boolean;
  auto?: boolean;
}

export interface LatexBuildError {
  path?: string | null;
  line?: number | null;
  message: string;
  severity: "error" | "warning";
}

export interface LatexLogItem {
  severity: "error" | "warning";
  file?: string | null;
  line?: number | null;
  message: string;
  raw: string;
}

export interface LatexBuildResponse {
  build_id: string;
  project_id: string;
  folder_id: string;
  main_file_id?: string | null;
  compiler: LatexCompiler;
  status: LatexBuildStatus;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  exit_code?: number | null;
  error_message?: string | null;
  pdf_ready: boolean;
  log_ready: boolean;
  synctex_ready?: boolean;
  errors: LatexBuildError[];
  log_items?: LatexLogItem[];
  synctex_path?: string | null;
  source_commit?: string | null;
  source_version_id?: string | null;
  source_version?: LatexVersionSummary | null;
  source_version_error?: string | null;
}

export interface LatexManifestFile {
  id: string;
  name: string;
  path: string;
  relative_path?: string;
  role: "main" | "tex" | "bib" | "style" | "resource" | "other" | string;
  editable: boolean;
  size?: number;
  dependencies?: Array<{ kind: string; path: string }>;
}

export interface LatexManifestResponse {
  folder_id: string;
  folder_path: string;
  folder_name?: string;
  main_file_id?: string | null;
  main_file_path?: string | null;
  compiler?: LatexCompiler;
  files: LatexManifestFile[];
}

export type LatexVersionSource = "manual" | "auto" | "compile" | "ai" | "restore" | string;

export interface LatexVersionSummary {
  version_id: string;
  commit: string;
  short_commit?: string;
  parents?: string[];
  compare_base?: string | null;
  folder_id?: string;
  folder_path: string;
  main_file_path?: string | null;
  label: string;
  description?: string | null;
  source: LatexVersionSource;
  author?: string | null;
  created_at: string;
  build_id?: string | null;
  changed_paths?: string[];
  file_count?: number;
  added?: number;
  removed?: number;
}

export interface LatexVersionListResponse {
  ok: boolean;
  message?: string;
  folder_id: string;
  folder_path: string;
  head?: string | null;
  versions: LatexVersionSummary[];
  limit?: number;
}

export interface LatexVersionCreateRequest {
  label?: string | null;
  description?: string | null;
  source?: LatexVersionSource;
  author?: string | null;
  build_id?: string | null;
  allow_empty?: boolean;
}

export interface LatexVersionCreateResponse extends LatexVersionSummary {
  ok: boolean;
  created?: boolean;
  message?: string;
  head?: string | null;
  previous_head?: string | null;
  version?: LatexVersionSummary;
}

export interface LatexVersionFileEntry {
  id: string;
  name: string;
  path: string;
  relative_path?: string;
  role?: string;
  editable?: boolean;
  document_id?: string;
}

export interface LatexVersionFilesResponse {
  ok: boolean;
  folder_id: string;
  folder_path: string;
  version?: LatexVersionSummary | null;
  commit: string;
  files: LatexVersionFileEntry[];
}

export interface LatexVersionRestoreRequest {
  mode?: "file" | "folder";
  path?: string | null;
  expected_head?: string | null;
  conflict_policy?: "fail" | "force";
}

export interface LatexVersionRestoreResponse {
  ok: boolean;
  conflict?: boolean;
  message?: string;
  restored_from?: LatexVersionSummary | null;
  restored_paths?: string[];
  restore_version?: LatexVersionSummary | null;
  head?: string | null;
  current_head?: string | null;
}

export interface LatexVersionCompareResponse {
  ok: boolean;
  base: string;
  head: string;
  folder_id: string;
  folder_path: string;
  base_version?: LatexVersionSummary | null;
  head_version?: LatexVersionSummary | null;
  files: Array<{
    path: string;
    old_path?: string | null;
    status?: string;
    added?: number;
    removed?: number;
    binary?: boolean;
  }>;
  file_count?: number;
  commit_count?: number;
  ahead?: number;
  behind?: number;
}

export interface LatexSyncTexEditRequest {
  page: number;
  x: number;
  y: number;
  pdf_word?: string | null;
  pdf_context_words?: string[] | null;
  pdf_context_index?: number | null;
  pdf_word_bbox?: {
    left: number;
    top: number;
    right: number;
    bottom: number;
    width?: number;
    height?: number;
  } | null;
  pdf_word_center?: { x: number; y: number } | null;
}

export interface LatexSyncTexSelection {
  start_line: number;
  start_column: number;
  end_line: number;
  end_column: number;
  text?: string;
  precision?: "exact_word" | "nearest_token" | "line_column" | "line_only" | string;
  confidence?: number;
}

export interface LatexSyncTexEditResponse {
  ok: boolean;
  message?: string;
  reason?: string;
  file_id?: string;
  file_path?: string;
  file_name?: string;
  line?: number;
  column?: number | null;
  selection?: LatexSyncTexSelection | null;
  precision?: string;
  confidence?: number | null;
  pdf_word?: string | null;
  pdf_context_words?: string[] | null;
  pdf_context_index?: number | null;
  synctex_line?: number;
  synctex_column?: number | null;
  sample_count?: number;
  candidate_count?: number;
  page?: number;
  x?: number;
  y?: number;
  folder_id?: string;
  folder_path?: string;
}

export async function initLatexProject(
  projectId: string,
  request: LatexInitRequest
): Promise<LatexInitResponse> {
  const res = await apiClient.post<LatexInitResponse>(
    `/api/v1/projects/${projectId}/latex/init`,
    request
  );
  return res.data;
}

export async function compileLatex(
  projectId: string,
  folderId: string,
  request: LatexCompileRequest
): Promise<LatexBuildResponse> {
  const res = await apiClient.post<LatexBuildResponse>(
    `/api/v1/projects/${projectId}/latex/${folderId}/compile`,
    request
  );
  return res.data;
}

export async function getLatexManifest(
  projectId: string,
  folderId: string
): Promise<LatexManifestResponse> {
  const res = await apiClient.get<LatexManifestResponse>(
    `/api/v1/projects/${projectId}/latex/${folderId}/manifest`
  );
  return res.data;
}

export async function listLatexVersions(
  projectId: string,
  folderId: string,
  limit = 30
): Promise<LatexVersionListResponse> {
  const res = await apiClient.get<LatexVersionListResponse>(
    `/api/v1/projects/${projectId}/latex/${folderId}/versions`,
    { params: { limit } }
  );
  return res.data;
}

export async function createLatexVersion(
  projectId: string,
  folderId: string,
  request: LatexVersionCreateRequest
): Promise<LatexVersionCreateResponse> {
  const res = await apiClient.post<LatexVersionCreateResponse>(
    `/api/v1/projects/${projectId}/latex/${folderId}/versions`,
    request
  );
  return res.data;
}

export async function getLatexVersion(
  projectId: string,
  folderId: string,
  versionId: string
): Promise<LatexVersionCreateResponse> {
  const res = await apiClient.get<LatexVersionCreateResponse>(
    `/api/v1/projects/${projectId}/latex/${folderId}/versions/${versionId}`
  );
  return res.data;
}

export async function listLatexVersionFiles(
  projectId: string,
  folderId: string,
  versionId: string
): Promise<LatexVersionFilesResponse> {
  const res = await apiClient.get<LatexVersionFilesResponse>(
    `/api/v1/projects/${projectId}/latex/${folderId}/versions/${versionId}/files`
  );
  return res.data;
}

export async function compareLatexVersions(
  projectId: string,
  folderId: string,
  base: string,
  head: string
): Promise<LatexVersionCompareResponse> {
  const res = await apiClient.get<LatexVersionCompareResponse>(
    `/api/v1/projects/${projectId}/latex/${folderId}/versions/compare`,
    { params: { base, head } }
  );
  return res.data;
}

export async function restoreLatexVersion(
  projectId: string,
  folderId: string,
  versionId: string,
  request: LatexVersionRestoreRequest
): Promise<LatexVersionRestoreResponse> {
  const res = await apiClient.post<LatexVersionRestoreResponse>(
    `/api/v1/projects/${projectId}/latex/${folderId}/versions/${versionId}/restore`,
    request
  );
  return res.data;
}

export async function getLatexBuild(
  projectId: string,
  folderId: string,
  buildId: string
): Promise<LatexBuildResponse> {
  const res = await apiClient.get<LatexBuildResponse>(
    `/api/v1/projects/${projectId}/latex/${folderId}/builds/${buildId}`
  );
  return res.data;
}

export async function listLatexBuilds(
  projectId: string,
  folderId: string,
  limit = 10
): Promise<LatexBuildResponse[]> {
  const res = await apiClient.get<LatexBuildResponse[]>(
    `/api/v1/projects/${projectId}/latex/${folderId}/builds`,
    { params: { limit } }
  );
  return Array.isArray(res.data) ? res.data : [];
}

export async function getLatexBuildPdfBlob(
  projectId: string,
  folderId: string,
  buildId: string
): Promise<Blob> {
  const res = await apiClient.get(
    `/api/v1/projects/${projectId}/latex/${folderId}/builds/${buildId}/pdf`,
    { responseType: "blob" }
  );
  return res.data as Blob;
}

export async function getLatexBuildLogText(
  projectId: string,
  folderId: string,
  buildId: string
): Promise<string> {
  const res = await apiClient.get(
    `/api/v1/projects/${projectId}/latex/${folderId}/builds/${buildId}/log`,
    { responseType: "text" }
  );
  return String(res.data ?? "");
}

export async function syncTexEditLatexBuild(
  projectId: string,
  folderId: string,
  buildId: string,
  request: LatexSyncTexEditRequest
): Promise<LatexSyncTexEditResponse> {
  const res = await apiClient.post<LatexSyncTexEditResponse>(
    `/api/v1/projects/${projectId}/latex/${folderId}/builds/${buildId}/synctex/edit`,
    request
  );
  return res.data;
}

export async function getLatexSourcesArchiveBlob(
  projectId: string,
  folderId: string
): Promise<Blob> {
  const res = await apiClient.get(
    `/api/v1/projects/${projectId}/latex/${folderId}/archive`,
    { responseType: "blob" }
  );
  return res.data as Blob;
}
