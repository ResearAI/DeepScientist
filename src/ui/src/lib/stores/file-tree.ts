/**
 * File Tree Store
 *
 * Manages file tree state for the workspace including:
 * - File/folder nodes
 * - Expanded/collapsed states
 * - Selection states
 * - File operations (create, rename, delete, move)
 * - Upload tracking
 *
 * @module stores/file-tree
 */

import { create } from "zustand";
import type {
  FileNode,
  ClipboardData,
  UploadTask,
} from "@/lib/types/file";
import { buildFileTree } from "@/lib/types/file";
import * as fileApi from "@/lib/api/files";
import * as latexApi from "@/lib/api/latex";
import { normalizeProjectRelativePath } from "@/lib/utils/project-relative-path";

/**
 * Transfer task for file operations (move, copy, etc.)
 */
export interface TransferTask {
  id: string;
  label: string;
  status: "in_progress" | "completed" | "error";
  error?: string;
}

/**
 * File tree state interface
 */
export interface FileTreeState {
  /** Root nodes of the file tree */
  nodes: FileNode[];

  /** Set of expanded folder IDs */
  expandedIds: Set<string>;

  /** Set of selected node IDs */
  selectedIds: Set<string>;

  /** Currently focused node ID */
  focusedId: string | null;

  /** Node being renamed */
  renamingId: string | null;

  /** Loading state */
  isLoading: boolean;

  /** Error message */
  error: string | null;

  /** Current project ID */
  projectId: string | null;

  /** Clipboard data for copy/paste */
  clipboard: ClipboardData | null;

  /** Active upload tasks */
  uploadTasks: UploadTask[];

  /** Active transfer tasks (move, copy, etc.) */
  transferTasks: TransferTask[];

  /** Currently highlighted file ID (for AI effect animation) */
  highlightedFileId: string | null;

  /** File IDs with a recent read effect */
  readingFileIds: Set<string>;

  /** File IDs flagged as recently written */
  writingFileIds: Set<string>;

  /** File IDs with a recent move effect */
  movedFileIds: Set<string>;

  /** File IDs with a recent rename effect */
  renamedFileIds: Set<string>;
}

/**
 * File tree actions interface
 */
export interface FileTreeActions {
  /** Load files for a project */
  loadFiles: (projectId: string, options?: { force?: boolean }) => Promise<void>;

  /** Refresh file tree */
  refresh: () => Promise<void>;

  /** Toggle folder expanded state */
  toggleExpand: (nodeId: string) => void;

  /** Expand a folder */
  expand: (nodeId: string) => void;

  /** Collapse a folder */
  collapse: (nodeId: string) => void;

  /** Select node(s) */
  select: (
    nodeId: string,
    options?: { multi?: boolean; range?: boolean }
  ) => void;

  /** Clear selection */
  clearSelection: () => void;

  /** Set focused node */
  setFocused: (nodeId: string | null) => void;

  /** Start renaming a node */
  startRenaming: (nodeId: string) => void;

  /** Cancel renaming */
  cancelRenaming: () => void;

  /** Create a new folder */
  createFolder: (parentId: string | null, name: string) => Promise<FileNode>;

  /** Create a LaTeX project folder (special folderKind=latex + default files). */
  createLatexProject: (
    parentId: string | null,
    name: string,
    options?: { template?: string; compiler?: latexApi.LatexCompiler }
  ) => Promise<FileNode>;

  /** Rename a node */
  rename: (nodeId: string, newName: string) => Promise<void>;

  /** Delete nodes */
  delete: (nodeIds: string[]) => Promise<void>;

  /** Move nodes to a new parent */
  move: (nodeIds: string[], targetParentId: string | null) => Promise<void>;

  /** Copy nodes to clipboard */
  copy: (nodeIds: string[]) => void;

  /** Cut nodes to clipboard */
  cut: (nodeIds: string[]) => void;

  /** Paste nodes from clipboard */
  paste: (targetParentId: string | null) => Promise<void>;

  /** Upload files */
  upload: (parentId: string | null, files: File[]) => Promise<FileNode[]>;

  /** Cancel upload task */
  cancelUpload: (taskId: string) => void;

  /** Clear completed/errored uploads */
  clearCompletedUploads: () => void;

  /** Clear completed/errored transfers */
  clearCompletedTransfers: () => void;

  /** Find node by ID */
  findNode: (nodeId: string) => FileNode | null;

  /** Highlight a file (for AI effect animation) */
  highlightFile: (fileId: string) => void;

  /** Mark a file as read (temporary visual effect) */
  markFileRead: (fileId: string) => void;

  /** Mark a file as written (persistent visual effect) */
  markFileWrite: (fileId: string) => void;

  /** Clear the write effect for a file */
  clearWriteEffect: (fileId: string) => void;

  /** Mark a file as moved (temporary visual effect) */
  markFileMove: (fileId: string) => void;

  /** Clear the move effect for a file */
  clearMoveEffect: (fileId: string) => void;

  /** Mark a file as renamed (temporary visual effect) */
  markFileRename: (fileId: string) => void;

  /** Clear the rename effect for a file */
  clearRenameEffect: (fileId: string) => void;

  /** Expand tree to make a file visible */
  expandToFile: (fileId: string) => void;

  /** Clear file highlight */
  clearHighlight: () => void;

  /** Find node by path (project-relative) */
  findNodeByPath: (path: string) => FileNode | null;

  /** Update a file's metadata (updatedAt/size/mimeType) */
  updateFileMeta: (
    fileId: string,
    meta: Partial<Pick<FileNode, "updatedAt" | "size" | "mimeType">>
  ) => void;
}

/**
 * Find node by ID in tree structure
 */
function findNodeInTree(nodes: FileNode[], id: string): FileNode | null {
  for (const node of nodes) {
    if (node.id === id) {
      return node;
    }
    if (node.children) {
      const found = findNodeInTree(node.children, id);
      if (found) {
        return found;
      }
    }
  }
  return null;
}

/**
 * Get parent ID of a node
 */
function getParentId(nodes: FileNode[], id: string): string | null {
  const node = findNodeInTree(nodes, id);
  return node?.parentId ?? null;
}

/**
 * Get all parent folder IDs for a node (for expanding path)
 */
function getAncestorIds(nodes: FileNode[], id: string): string[] {
  const ancestors: string[] = [];
  let currentId: string | null = id;

  while (currentId) {
    const node = findNodeInTree(nodes, currentId);
    if (node?.parentId) {
      ancestors.push(node.parentId);
      currentId = node.parentId;
    } else {
      break;
    }
  }

  return ancestors;
}

function cloneFileTree(nodes: FileNode[]): FileNode[] {
  return nodes.map((node) => ({
    ...node,
    children: node.children ? cloneFileTree(node.children) : node.children,
  }));
}

function buildParentMap(
  nodes: FileNode[],
  parentId: string | null = null,
  map = new Map<string, string | null>()
): Map<string, string | null> {
  for (const node of nodes) {
    map.set(node.id, parentId);
    if (node.children) {
      buildParentMap(node.children, node.id, map);
    }
  }
  return map;
}

function filterMoveIds(
  nodeIds: string[],
  parentMap: Map<string, string | null>
): string[] {
  const idSet = new Set(nodeIds);
  return nodeIds.filter((id) => {
    let parentId = parentMap.get(id) ?? null;
    while (parentId) {
      if (idSet.has(parentId)) return false;
      parentId = parentMap.get(parentId) ?? null;
    }
    return true;
  });
}

function hasAncestorInSet(
  startId: string | null,
  parentMap: Map<string, string | null>,
  idSet: Set<string>
): boolean {
  let currentId = startId;
  while (currentId) {
    if (idSet.has(currentId)) return true;
    currentId = parentMap.get(currentId) ?? null;
  }
  return false;
}

function sortFileNodes(nodes: FileNode[]): void {
  nodes.sort((a, b) => {
    if (a.type !== b.type) {
      return a.type === "folder" ? -1 : 1;
    }
    return a.name.localeCompare(b.name);
  });
  for (const node of nodes) {
    if (node.children) {
      sortFileNodes(node.children);
    }
  }
}

function moveNodesInTree(
  nodes: FileNode[],
  nodeIds: string[],
  targetParentId: string | null
): FileNode[] {
  if (nodeIds.length === 0) return nodes;
  const parentMap = buildParentMap(nodes);
  const effectiveIds = filterMoveIds(nodeIds, parentMap);
  if (effectiveIds.length === 0) return nodes;

  const movingSet = new Set(effectiveIds);
  if (targetParentId && movingSet.has(targetParentId)) return nodes;
  if (targetParentId && hasAncestorInSet(targetParentId, parentMap, movingSet)) {
    return nodes;
  }

  const sameParent = effectiveIds.every(
    (id) => (parentMap.get(id) ?? null) === targetParentId
  );
  if (sameParent) return nodes;

  const cloned = cloneFileTree(nodes);
  let roots = cloned;

  const index = new Map<string, { node: FileNode; parent: FileNode | null }>();
  const indexTree = (list: FileNode[], parent: FileNode | null) => {
    for (const node of list) {
      index.set(node.id, { node, parent });
      if (node.children) {
        indexTree(node.children, node);
      }
    }
  };
  indexTree(roots, null);

  const movingNodes: FileNode[] = [];
  for (const id of effectiveIds) {
    const entry = index.get(id);
    if (!entry) continue;

    if (entry.parent) {
      entry.parent.children = (entry.parent.children ?? []).filter(
        (child) => child.id !== id
      );
    } else {
      roots = roots.filter((child) => child.id !== id);
    }

    entry.node.parentId = targetParentId;
    movingNodes.push(entry.node);
  }

  if (movingNodes.length === 0) return nodes;

  const targetEntry = targetParentId ? index.get(targetParentId) : null;
  if (targetParentId && targetEntry?.node.type === "folder") {
    const children = targetEntry.node.children ?? [];
    targetEntry.node.children = [...children, ...movingNodes];
  } else {
    roots = [...roots, ...movingNodes];
  }

  sortFileNodes(roots);
  return roots;
}

function cloneFileNode(node: FileNode): FileNode {
  return {
    ...node,
    children: node.children ? cloneFileTree(node.children) : node.children,
  };
}

function insertNodeIntoTree(nodes: FileNode[], nextNode: FileNode): FileNode[] {
  const clonedNode = cloneFileNode(nextNode);
  let inserted = false;

  const visit = (list: FileNode[]): FileNode[] =>
    list.map((node) => {
      if (inserted || node.id !== clonedNode.parentId || node.type !== "folder") {
        if (!inserted && node.children) {
          const nextChildren = visit(node.children);
          if (nextChildren !== node.children) {
            return { ...node, children: nextChildren };
          }
        }
        return node;
      }

      inserted = true;
      const children = [...(node.children ?? []), clonedNode];
      sortFileNodes(children);
      return { ...node, children };
    });

  const nextNodes = visit(nodes);
  if (inserted) {
    return nextNodes;
  }
  if (clonedNode.parentId) {
    return nodes;
  }

  const roots = [...nodes, clonedNode];
  sortFileNodes(roots);
  return roots;
}

function updateNodeMetaInTree(
  nodes: FileNode[],
  id: string,
  meta: Partial<Pick<FileNode, "updatedAt" | "size" | "mimeType">>
): FileNode[] {
  let changed = false;
  const next = nodes.map((node) => {
    if (node.id === id) {
      changed = true;
      return { ...node, ...meta };
    }
    if (node.children) {
      const nextChildren = updateNodeMetaInTree(node.children, id, meta);
      if (nextChildren !== node.children) {
        changed = true;
        return { ...node, children: nextChildren };
      }
    }
    return node;
  });
  return changed ? next : nodes;
}

const READ_EFFECT_DURATION_MS = 3500;
const MOVE_EFFECT_DURATION_MS = 3000;
const RENAME_EFFECT_DURATION_MS = 3000;
const readEffectTimers = new Map<string, number>();
const moveEffectTimers = new Map<string, number>();
const renameEffectTimers = new Map<string, number>();
let latestLoadRequestId = 0;

function findNodeByPathInTree(nodes: FileNode[], targetPath: string): FileNode | null {
  const normalized = normalizeProjectRelativePath(targetPath);
  for (const node of nodes) {
    if (node.path && normalizeProjectRelativePath(node.path) === normalized) {
      return node;
    }
    if (node.children) {
      const found = findNodeByPathInTree(node.children, normalized);
      if (found) return found;
    }
  }
  return null;
}

/**
 * File tree store
 */
export const useFileTreeStore = create<FileTreeState & FileTreeActions>(
  (set, get) => ({
    // Initial state
    nodes: [],
    expandedIds: new Set(),
    selectedIds: new Set(),
    focusedId: null,
    renamingId: null,
    isLoading: false,
    error: null,
    projectId: null,
    clipboard: null,
    uploadTasks: [],
    transferTasks: [],
    highlightedFileId: null,
    readingFileIds: new Set(),
    writingFileIds: new Set(),
    movedFileIds: new Set(),
    renamedFileIds: new Set(),

    // Load files for a project
    loadFiles: async (projectId: string, options = {}) => {
      const force = Boolean(options.force);
      const currentState = get();
      const sameProject = currentState.projectId === projectId;
      if (!force && sameProject && currentState.nodes.length > 0) {
        return;
      }
      if (!force && sameProject && currentState.isLoading) {
        return;
      }

      const requestId = ++latestLoadRequestId;
      set((state) => ({
        isLoading: true,
        error: null,
        projectId,
        nodes: state.projectId === projectId ? state.nodes : [],
      }));
      try {
        const response = await fileApi.getFileTree(projectId, { force });
        if (requestId !== latestLoadRequestId) {
          return;
        }
        // Defensive: handle cases where response might not have files array
        const files = response?.files;
        const nodes = buildFileTree(files);
        set({ nodes, isLoading: false, error: null });
      } catch (error) {
        if (requestId !== latestLoadRequestId) {
          return;
        }
        const message =
          error instanceof Error ? error.message : "Failed to load files";
        set((state) => ({
          error: message,
          isLoading: false,
          nodes: state.projectId === projectId && state.nodes.length > 0 ? state.nodes : [],
        }));
        // Don't throw - just log the error
        console.error("[FileTree] Failed to load files:", error);
      }
    },

    // Refresh file tree
    refresh: async () => {
      const { projectId } = get();
      if (projectId) {
        await get().loadFiles(projectId, { force: true });
      }
    },

    // Toggle folder expanded state
    toggleExpand: (nodeId: string) => {
      const { expandedIds } = get();
      const newExpanded = new Set(expandedIds);
      if (newExpanded.has(nodeId)) {
        newExpanded.delete(nodeId);
      } else {
        newExpanded.add(nodeId);
      }
      set({ expandedIds: newExpanded });
    },

    // Expand a folder
    expand: (nodeId: string) => {
      const { expandedIds } = get();
      const newExpanded = new Set(expandedIds);
      newExpanded.add(nodeId);
      set({ expandedIds: newExpanded });
    },

    // Collapse a folder
    collapse: (nodeId: string) => {
      const { expandedIds } = get();
      const newExpanded = new Set(expandedIds);
      newExpanded.delete(nodeId);
      set({ expandedIds: newExpanded });
    },

    // Select node(s)
    select: (nodeId: string, options?: { multi?: boolean; range?: boolean }) => {
      const { selectedIds, focusedId, nodes } = get();

      if (options?.multi) {
        // Multi-select (Ctrl/Cmd + click)
        const newSelected = new Set(selectedIds);
        if (newSelected.has(nodeId)) {
          newSelected.delete(nodeId);
        } else {
          newSelected.add(nodeId);
        }
        set({ selectedIds: newSelected, focusedId: nodeId });
      } else if (options?.range && focusedId) {
        // Range select (Shift + click) - simplified, just select both
        const newSelected = new Set(selectedIds);
        newSelected.add(nodeId);
        newSelected.add(focusedId);
        set({ selectedIds: newSelected, focusedId: nodeId });
      } else {
        // Single select
        set({ selectedIds: new Set([nodeId]), focusedId: nodeId });
      }
    },

    // Clear selection
    clearSelection: () => {
      set({ selectedIds: new Set() });
    },

    // Set focused node
    setFocused: (nodeId: string | null) => {
      set({ focusedId: nodeId });
    },

    // Start renaming
    startRenaming: (nodeId: string) => {
      set({ renamingId: nodeId });
    },

    // Cancel renaming
    cancelRenaming: () => {
      set({ renamingId: null });
    },

    // Create folder
    createFolder: async (parentId: string | null, name: string) => {
      const { projectId } = get();
      if (!projectId) {
        throw new Error("No project selected");
      }

      const response = await fileApi.createFolder(projectId, {
        name,
        parent_id: parentId,
      });

      // Refresh tree to show new folder
      await get().refresh();

      // Expand parent if it exists
      if (parentId) {
        get().expand(parentId);
      }

      // Return the created node
      const node = get().findNode(response.id);
      return node || {
        id: response.id,
        name: response.name,
        type: response.type as "folder" | "file",
        parentId: response.parent_id,
        createdAt: response.created_at,
        updatedAt: response.updated_at,
        children: [],
      };
    },

    createLatexProject: async (
      parentId: string | null,
      name: string,
      options?: { template?: string; compiler?: latexApi.LatexCompiler }
    ) => {
      const { projectId } = get();
      if (!projectId) {
        throw new Error("No project selected");
      }

      const response = await latexApi.initLatexProject(projectId, {
        name,
        parent_id: parentId,
        template: options?.template ?? "basic",
        compiler: options?.compiler ?? "pdflatex",
      });

      // Refresh tree to show new folder and files.
      await get().refresh();

      // Expand parent and the newly created folder.
      if (parentId) get().expand(parentId);
      get().expand(response.folder_id);

      const folderNode = get().findNode(response.folder_id);
      if (folderNode) return folderNode;

      // Fallback shape if tree refresh didn't include it yet.
      return {
        id: response.folder_id,
        name,
        type: "folder",
        folderKind: "latex",
        parentId,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        children: [],
      };
    },

    // Rename node
    rename: async (nodeId: string, newName: string) => {
      await fileApi.renameFile(nodeId, newName);
      await get().refresh();
      set({ renamingId: null });
    },

    // Delete nodes
    delete: async (nodeIds: string[]) => {
      await fileApi.deleteFiles(nodeIds);
      await get().refresh();

      // Remove deleted nodes from selection
      const { selectedIds } = get();
      const newSelected = new Set(selectedIds);
      for (const id of nodeIds) {
        newSelected.delete(id);
      }
      set({ selectedIds: newSelected });
    },

    // Move nodes
    move: async (nodeIds: string[], targetParentId: string | null) => {
      const previousNodes = get().nodes;
      const nextNodes = moveNodesInTree(previousNodes, nodeIds, targetParentId);
      if (nextNodes !== previousNodes) {
        set({ nodes: nextNodes });
      }
      if (targetParentId) {
        get().expand(targetParentId);
      }

      try {
        await fileApi.moveFiles(nodeIds, targetParentId);
        await get().refresh();
      } catch (error) {
        set({ nodes: previousNodes });
        throw error;
      }
    },

    // Copy nodes to clipboard
    copy: (nodeIds: string[]) => {
      const { nodes } = get();
      const sourceParentId = nodeIds.length > 0 ? getParentId(nodes, nodeIds[0]) : null;
      set({
        clipboard: {
          action: "copy",
          fileIds: nodeIds,
          sourceParentId,
        },
      });
    },

    // Cut nodes to clipboard
    cut: (nodeIds: string[]) => {
      const { nodes } = get();
      const sourceParentId = nodeIds.length > 0 ? getParentId(nodes, nodeIds[0]) : null;
      set({
        clipboard: {
          action: "cut",
          fileIds: nodeIds,
          sourceParentId,
        },
      });
    },

    // Paste nodes from clipboard
    paste: async (targetParentId: string | null) => {
      const { clipboard } = get();
      if (!clipboard) return;

      if (clipboard.action === "cut") {
        // Move files
        await get().move(clipboard.fileIds, targetParentId);
        set({ clipboard: null });
      } else {
        // Copy operation - for now, just show a message
        // Actual copy would require backend support
        console.warn("Copy operation not yet implemented on backend");
      }
    },

    // Upload files
    upload: async (parentId: string | null, files: File[]) => {
      const { projectId, uploadTasks } = get();
      if (!projectId) {
        throw new Error("No project selected");
      }

      const results: FileNode[] = [];
      const newTasks: UploadTask[] = [];

      // Create upload tasks
      for (const file of files) {
        const taskId = `upload-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        newTasks.push({
          id: taskId,
          fileName: file.name,
          fileSize: file.size,
          mimeType: file.type || "application/octet-stream",
          status: "pending",
          progress: 0,
          parentId,
        });
      }

      set({ uploadTasks: [...uploadTasks, ...newTasks] });

      // Upload files
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const task = newTasks[i];

        try {
          // Update status to uploading
          set((state) => ({
            uploadTasks: state.uploadTasks.map((t) =>
              t.id === task.id ? { ...t, status: "uploading" as const } : t
            ),
          }));

          // Upload file
          const response = await fileApi.uploadFileAuto(
            projectId,
            file,
            parentId,
            (progress) => {
              set((state) => ({
                uploadTasks: state.uploadTasks.map((t) =>
                  t.id === task.id ? { ...t, progress } : t
                ),
              }));
            }
          );

          // Update status to completed
          const createdNode: FileNode = {
            id: response.id,
            name: response.name,
            type: response.type as "folder" | "file",
            mimeType: response.mime_type,
            size: response.size,
            parentId: response.parent_id,
            path: response.path,
            createdAt: response.created_at,
            updatedAt: response.updated_at,
          };

          set((state) => ({
            uploadTasks: state.uploadTasks.map((t) =>
              t.id === task.id
                ? {
                    ...t,
                    status: "completed" as const,
                    progress: 100,
                    createdFile: createdNode,
                  }
                : t
            ),
            nodes: insertNodeIntoTree(state.nodes, createdNode),
          }));

          if (parentId) {
            get().expand(parentId);
          }
          get().expandToFile(createdNode.id);
          get().markFileWrite(createdNode.id);
          get().highlightFile(createdNode.id);
          results.push(createdNode);
        } catch (error) {
          // Update status to error
          const message =
            error instanceof Error ? error.message : "Upload failed";
          set((state) => ({
            uploadTasks: state.uploadTasks.map((t) =>
              t.id === task.id ? { ...t, status: "error" as const, error: message } : t
            ),
          }));
        }
      }

      // Refresh tree
      await get().refresh();

      // Expand parent if exists
      if (parentId) {
        get().expand(parentId);
      }

      return results;
    },

    // Cancel upload
    cancelUpload: (taskId: string) => {
      set((state) => ({
        uploadTasks: state.uploadTasks.map((t) =>
          t.id === taskId && (t.status === "uploading" || t.status === "pending")
            ? { ...t, status: "cancelled" as const }
            : t
        ),
      }));
    },

    // Clear completed uploads
    clearCompletedUploads: () => {
      set((state) => ({
        uploadTasks: state.uploadTasks.filter((t) => t.status === "uploading" || t.status === "pending"),
      }));
    },

    // Clear completed transfers
    clearCompletedTransfers: () => {
      set((state) => ({
        transferTasks: state.transferTasks.filter((t) => t.status === "in_progress"),
      }));
    },

    // Find node by ID
    findNode: (nodeId: string) => {
      const { nodes } = get();
      return findNodeInTree(nodes, nodeId);
    },

    // Highlight a file (for AI effect animation)
    highlightFile: (fileId: string) => {
      set({ highlightedFileId: fileId });

      // Auto-clear highlight after 3 seconds
      setTimeout(() => {
        const state = get();
        if (state.highlightedFileId === fileId) {
          set({ highlightedFileId: null });
        }
      }, 3000);
    },

    markFileRead: (fileId: string) => {
      set((state) => {
        const next = new Set(state.readingFileIds);
        next.add(fileId);
        return { readingFileIds: next };
      });

      const existing = readEffectTimers.get(fileId);
      if (existing) {
        window.clearTimeout(existing);
      }
      const timer = window.setTimeout(() => {
        readEffectTimers.delete(fileId);
        set((state) => {
          if (!state.readingFileIds.has(fileId)) return state;
          const next = new Set(state.readingFileIds);
          next.delete(fileId);
          return { readingFileIds: next };
        });
      }, READ_EFFECT_DURATION_MS);
      readEffectTimers.set(fileId, timer);
    },

    markFileWrite: (fileId: string) => {
      set((state) => {
        const next = new Set(state.writingFileIds);
        next.add(fileId);
        return { writingFileIds: next };
      });
    },

    clearWriteEffect: (fileId: string) => {
      set((state) => {
        if (!state.writingFileIds.has(fileId)) return state;
        const next = new Set(state.writingFileIds);
        next.delete(fileId);
        return { writingFileIds: next };
      });
    },

    markFileMove: (fileId: string) => {
      set((state) => {
        const next = new Set(state.movedFileIds);
        next.add(fileId);
        return { movedFileIds: next };
      });

      const existing = moveEffectTimers.get(fileId);
      if (existing) {
        window.clearTimeout(existing);
      }
      const timer = window.setTimeout(() => {
        moveEffectTimers.delete(fileId);
        set((state) => {
          if (!state.movedFileIds.has(fileId)) return state;
          const next = new Set(state.movedFileIds);
          next.delete(fileId);
          return { movedFileIds: next };
        });
      }, MOVE_EFFECT_DURATION_MS);
      moveEffectTimers.set(fileId, timer);
    },

    clearMoveEffect: (fileId: string) => {
      set((state) => {
        if (!state.movedFileIds.has(fileId)) return state;
        const next = new Set(state.movedFileIds);
        next.delete(fileId);
        return { movedFileIds: next };
      });
    },

    markFileRename: (fileId: string) => {
      set((state) => {
        const next = new Set(state.renamedFileIds);
        next.add(fileId);
        return { renamedFileIds: next };
      });

      const existing = renameEffectTimers.get(fileId);
      if (existing) {
        window.clearTimeout(existing);
      }
      const timer = window.setTimeout(() => {
        renameEffectTimers.delete(fileId);
        set((state) => {
          if (!state.renamedFileIds.has(fileId)) return state;
          const next = new Set(state.renamedFileIds);
          next.delete(fileId);
          return { renamedFileIds: next };
        });
      }, RENAME_EFFECT_DURATION_MS);
      renameEffectTimers.set(fileId, timer);
    },

    clearRenameEffect: (fileId: string) => {
      set((state) => {
        if (!state.renamedFileIds.has(fileId)) return state;
        const next = new Set(state.renamedFileIds);
        next.delete(fileId);
        return { renamedFileIds: next };
      });
    },

    // Expand tree to make a file visible
    expandToFile: (fileId: string) => {
      const { nodes, expandedIds } = get();

      // Get all ancestor folder IDs
      const ancestorIds = getAncestorIds(nodes, fileId);

      if (ancestorIds.length > 0) {
        // Add all ancestors to expanded set
        const newExpanded = new Set(expandedIds);
        for (const id of ancestorIds) {
          newExpanded.add(id);
        }
        set({ expandedIds: newExpanded });
      }
    },

    // Clear file highlight
    clearHighlight: () => {
      set({ highlightedFileId: null });
    },

    findNodeByPath: (path: string) => {
      const { nodes } = get();
      if (!path) return null;
      return findNodeByPathInTree(nodes, path);
    },

    updateFileMeta: (fileId, meta) => {
      set((state) => ({
        nodes: updateNodeMetaInTree(state.nodes, fileId, meta),
      }));
    },
  })
);

/**
 * Selector hooks for specific state slices
 */
export const useFileNodes = () => useFileTreeStore((state) => state.nodes);

export const useFileTreeLoading = () =>
  useFileTreeStore((state) => state.isLoading);

export const useSelectedFiles = () =>
  useFileTreeStore((state) => state.selectedIds);

export const useUploadTasks = () =>
  useFileTreeStore((state) => state.uploadTasks);

export const useTransferTasks = () =>
  useFileTreeStore((state) => state.transferTasks);

export const useHighlightedFile = () =>
  useFileTreeStore((state) => state.highlightedFileId);

export const useReadingFiles = () =>
  useFileTreeStore((state) => state.readingFileIds);

export const useWritingFiles = () =>
  useFileTreeStore((state) => state.writingFileIds);
