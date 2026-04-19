"use client";

import * as React from "react";
import { Tree, TreeApi } from "react-arborist";
import { DndProvider } from "react-dnd";
import { HTML5Backend } from "react-dnd-html5-backend";
import { Loader2, Upload } from "lucide-react";
import type { FileNode } from "@/lib/types/file";
import { useFileTreeStore, useHighlightedFile } from "@/lib/stores/file-tree";
import { FileTreeNode } from "./FileTreeNode";
import { FileTreeContextMenu } from "./FileTreeContextMenu";
import { CreateFileDialog } from "./CreateFileDialog";
import { CreateLatexProjectDialog } from "./CreateLatexProjectDialog";
import { FileTreeDragContext } from "./FileTreeDragContext";
import { FileTreeDragPreview } from "./FileTreeDragPreview";
import { Icon3D } from "@/components/ui/icon-3d";
import { ConfirmModal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { compileLatex } from "@/lib/api/latex";

/**
 * FileTree props
 */
export interface FileTreeProps {
  /** Project ID to load files for */
  projectId: string;

  /** Callback when a file is double-clicked */
  onFileOpen?: (file: FileNode) => void;

  /** Callback when file download is requested */
  onFileDownload?: (file: FileNode) => void;

  /** Callback when a node should be revealed in the full explorer */
  onRevealInExplorer?: (node: FileNode) => void;

  /** Callback when a node's parent folder should be opened in the full explorer */
  onOpenContainingFolder?: (node: FileNode) => void;

  /** Additional class names */
  className?: string;

  /** Height of the tree (defaults to 100%) */
  height?: number | string;

  /** Row height for each tree item (defaults to 28). */
  rowHeight?: number;

  /** When true, disables all mutating actions (drag/rename/create/upload/delete). */
  readOnly?: boolean;

  /** When true, hide files/folders starting with a dot (.) */
  hideDotfiles?: boolean;

  /** Optional externally-scoped tree nodes. */
  nodesOverride?: FileNode[] | null;

  /** Optional external loading state for overridden nodes. */
  loadingOverride?: boolean;

  /** Optional empty label for overridden trees. */
  emptyLabel?: string;

  /** Optional explicit reveal target in the live tree. */
  revealFileId?: string | null;

  /** Token to retrigger reveal for the same file id. */
  revealToken?: number | null;
}

function filterDotfiles(nodes: FileNode[]): FileNode[] {
  const filtered: FileNode[] = [];

  for (const node of nodes) {
    if (node.name.startsWith(".")) {
      continue;
    }

    if (node.children && node.children.length > 0) {
      const nextChildren = filterDotfiles(node.children);
      const childrenChanged =
        nextChildren.length !== node.children.length ||
        nextChildren.some((child, index) => child !== node.children![index]);

      filtered.push(childrenChanged ? { ...node, children: nextChildren } : node);
      continue;
    }

    filtered.push(node);
  }

  return filtered;
}

/**
 * FileTree - Main file tree component
 *
 * Uses react-arborist for virtualized, drag-and-drop tree rendering.
 *
 * Features:
 * - Virtualized rendering for large file trees
 * - Drag and drop to reorder/move files
 * - External file drop to upload
 * - Right-click context menu
 * - Keyboard navigation
 * - Inline renaming
 */
export function FileTree({
  projectId,
  onFileOpen,
  onFileDownload,
  onRevealInExplorer,
  onOpenContainingFolder,
  className,
  height = "100%",
  rowHeight = 28,
  readOnly = false,
  hideDotfiles = false,
  nodesOverride,
  loadingOverride,
  emptyLabel,
  revealFileId = null,
  revealToken = null,
}: FileTreeProps) {
  const treeRef = React.useRef<TreeApi<FileNode>>(null);
  const containerRef = React.useRef<HTMLDivElement>(null);
  const { addToast } = useToast();

  const {
    nodes,
    expandedIds,
    focusedId,
    isLoading,
    error,
    loadFiles,
    projectId: loadedProjectId,
    expand,
    move,
    rename,
    findNode,
    upload,
  } = useFileTreeStore();

  const highlightedFileId = useHighlightedFile();
  const selectionTargetId = highlightedFileId || focusedId || undefined;

  // Context menu state
  const [contextMenu, setContextMenu] = React.useState<{
    node: ReturnType<TreeApi<FileNode>["get"]>;
    position: { x: number; y: number };
  } | null>(null);

  const [createFileState, setCreateFileState] = React.useState<{
    open: boolean;
    parentId: string | null;
  }>({ open: false, parentId: null });

  const [createLatexState, setCreateLatexState] = React.useState<{
    open: boolean;
    parentId: string | null;
  }>({ open: false, parentId: null });

  const [deleteState, setDeleteState] = React.useState<{
    open: boolean;
    node: FileNode | null;
    loading: boolean;
  }>({ open: false, node: null, loading: false });

  const [dragArmedId, setDragArmedId] = React.useState<string | null>(null);
  const [externalDropTargetId, setExternalDropTargetId] = React.useState<string | null>(
    null
  );
  const [externalDropTargetPath, setExternalDropTargetPath] = React.useState<
    string | null
  >(null);
  // Drag-over state for external file drops
  const [isDragOver, setIsDragOver] = React.useState(false);
  const externalAutoExpandRef = React.useRef<{
    targetId: string | null;
    timerId: number | null;
  }>({
    targetId: null,
    timerId: null,
  });

  const dragContextValue = React.useMemo(
    () => ({
      armedId: dragArmedId,
      setArmedId: setDragArmedId,
      readOnly,
      externalDragActive: isDragOver,
      externalDropTargetId,
    }),
    [dragArmedId, externalDropTargetId, isDragOver, readOnly]
  );

  // Calculate container dimensions
  const [dimensions, setDimensions] = React.useState({ width: 240, height: 400 });

  React.useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const measureTarget = node.parentElement ?? node;
    let rafId: number | null = null;

    const updateDimensions = (rect?: DOMRectReadOnly) => {
      const targetRect = rect ?? measureTarget.getBoundingClientRect();
      const nextWidth = Math.round(targetRect.width);
      const nextHeight = Math.round(
        typeof height === "number" ? height : targetRect.height
      );
      const width = nextWidth || 240;
      const resolvedHeight = nextHeight || 400;
      setDimensions((prev) =>
        prev.width === width && prev.height === resolvedHeight
          ? prev
          : { width, height: resolvedHeight }
      );
    };

    const scheduleUpdate = (rect?: DOMRectReadOnly) => {
      if (rafId != null) return;
      rafId = window.requestAnimationFrame(() => {
        rafId = null;
        updateDimensions(rect);
      });
    };

    scheduleUpdate();
    const observer = new ResizeObserver((entries) => {
      scheduleUpdate(entries[0]?.contentRect);
    });
    observer.observe(measureTarget);

    return () => {
      if (rafId != null) window.cancelAnimationFrame(rafId);
      observer.disconnect();
    };
  }, [height]);

  // Load files on mount and when projectId changes
  React.useEffect(() => {
    if (loadedProjectId !== projectId) {
      loadFiles(projectId);
    }
  }, [projectId, loadedProjectId, loadFiles]);

  React.useEffect(() => {
    if (readOnly && dragArmedId) {
      setDragArmedId(null);
    }
  }, [readOnly, dragArmedId]);

  const clearExternalAutoExpand = React.useCallback(() => {
    if (externalAutoExpandRef.current.timerId != null) {
      window.clearTimeout(externalAutoExpandRef.current.timerId);
    }
    externalAutoExpandRef.current = {
      targetId: null,
      timerId: null,
    };
  }, []);

  React.useEffect(() => {
    return () => {
      clearExternalAutoExpand();
    };
  }, [clearExternalAutoExpand]);

  const visibleNodes = React.useMemo(
    () => (hideDotfiles ? filterDotfiles(nodesOverride ?? nodes) : nodesOverride ?? nodes),
    [hideDotfiles, nodes, nodesOverride]
  );
  const syncedExpandedIdsRef = React.useRef<Set<string>>(new Set());

  // Reveal highlighted file (AI effect)
  React.useEffect(() => {
    if (!highlightedFileId || !treeRef.current) return;
    treeRef.current.scrollTo(highlightedFileId, "center");
  }, [highlightedFileId]);

  React.useEffect(() => {
    if (!revealFileId) return;

    let cancelled = false;
    let timerId: number | null = null;

    const reveal = (attempt = 0) => {
      if (cancelled) return;
      const tree = treeRef.current;
      if (!tree) {
        if (attempt < 10) {
          timerId = window.setTimeout(() => reveal(attempt + 1), 80 * (attempt + 1));
        }
        return;
      }

      tree.select(revealFileId, { focus: false, align: "center" });
      tree.scrollTo(revealFileId, "center");
      const node = tree.get(revealFileId);
      const listReady = Boolean(tree.list.current);
      if ((node && listReady) || attempt >= 10) {
        return;
      }
      timerId = window.setTimeout(() => reveal(attempt + 1), 100 * (attempt + 1));
    };

    reveal();

    return () => {
      cancelled = true;
      if (timerId != null) {
        window.clearTimeout(timerId);
      }
    };
  }, [revealFileId, revealToken, visibleNodes.length, dimensions.height, dimensions.width]);

  // Handle move (drag and drop within tree)
  const handleMove = React.useCallback(
    async (args: {
      dragIds: string[];
      parentId: string | null;
      index: number;
    }) => {
      if (readOnly) return;
      try {
        await move(args.dragIds, args.parentId);
      } catch (error) {
        console.error("Failed to move files:", error);
        addToast({
          type: "error",
          title: "Move failed",
          description: error instanceof Error ? error.message : "Unable to move files.",
        });
      }
    },
    [addToast, move, readOnly]
  );

  // Handle rename
  const handleRename = React.useCallback(
    async (args: { id: string; name: string }) => {
      if (readOnly) return;
      try {
        await rename(args.id, args.name);
      } catch (error) {
        console.error("Failed to rename:", error);
      }
    },
    [rename, readOnly]
  );

  // Handle double-click on row
  const handleActivate = React.useCallback(
    (node: ReturnType<TreeApi<FileNode>["get"]>) => {
      if (
        node &&
        (node.data.type === "file" ||
          node.data.type === "notebook" ||
          (node.data.type === "folder" && node.data.folderKind === "latex")) &&
        onFileOpen
      ) {
        onFileOpen(node.data);
      }
    },
    [onFileOpen]
  );

  // Handle right-click
  const handleContextMenu = React.useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();

      // Find the node element
      const nodeElement = (e.target as HTMLElement).closest("[data-node-id]");
      if (!nodeElement) return;

      const nodeId = nodeElement.getAttribute("data-node-id");
      if (!nodeId || !treeRef.current) return;

      const node = treeRef.current.get(nodeId);
      if (!node) return;

      // Select the node if not already selected
      if (!node.isSelected) {
        node.select();
      }

      setContextMenu({
        node,
        position: { x: e.clientX, y: e.clientY },
      });
    },
    []
  );

  const resolveExternalDropTarget = React.useCallback(
    (element: HTMLElement | null): { parentId: string | null; parentPath: string | null } => {
      const nodeElement = element?.closest("[data-node-id]");
      if (!nodeElement || !treeRef.current) {
        return { parentId: null, parentPath: null };
      }
      const nodeId = nodeElement.getAttribute("data-node-id");
      if (!nodeId) {
        return { parentId: null, parentPath: null };
      }
      const node = treeRef.current.get(nodeId);
      if (!node) {
        return { parentId: null, parentPath: null };
      }
      if (node.data.type === "folder") {
        return {
          parentId: node.data.id,
          parentPath: node.data.path || node.data.name || null,
        };
      }
      if (!node.data.parentId) {
        return { parentId: null, parentPath: null };
      }
      const parentNode = treeRef.current.get(node.data.parentId);
      return {
        parentId: node.data.parentId,
        parentPath: parentNode?.data.path || parentNode?.data.name || null,
      };
    },
    []
  );

  const syncExternalDropTarget = React.useCallback(
    (target: { parentId: string | null; parentPath: string | null }) => {
      setExternalDropTargetId((prev) =>
        prev === target.parentId ? prev : target.parentId
      );
      setExternalDropTargetPath((prev) =>
        prev === target.parentPath ? prev : target.parentPath
      );

      if (!target.parentId || !treeRef.current) {
        clearExternalAutoExpand();
        return;
      }

      const folderNode = treeRef.current.get(target.parentId);
      if (!folderNode || folderNode.data.type !== "folder" || folderNode.isOpen) {
        clearExternalAutoExpand();
        return;
      }

      if (externalAutoExpandRef.current.targetId === target.parentId) {
        return;
      }

      clearExternalAutoExpand();
      const timerId = window.setTimeout(() => {
        if (externalAutoExpandRef.current.targetId !== target.parentId) {
          return;
        }
        const currentNode = treeRef.current?.get(target.parentId);
        if (currentNode && currentNode.data.type === "folder" && !currentNode.isOpen) {
          currentNode.open();
          expand(target.parentId);
        }
      }, 320);
      externalAutoExpandRef.current = {
        targetId: target.parentId,
        timerId,
      };
    },
    [clearExternalAutoExpand, expand]
  );

  // Handle external file drop
  const handleDrop = React.useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragOver(false);
      clearExternalAutoExpand();
      if (readOnly) return;

      const files = Array.from(e.dataTransfer.files);
      if (files.length === 0) return;
      const targetParentId = externalDropTargetId;
      setExternalDropTargetId(null);
      setExternalDropTargetPath(null);

      try {
        await upload(targetParentId, files);
      } catch (error) {
        console.error("Upload failed:", error);
      }
    },
    [clearExternalAutoExpand, externalDropTargetId, readOnly, upload]
  );

  const findLatexFolderForFile = React.useCallback(
    (file: FileNode): FileNode | null => {
      let currentId: string | null = file.parentId;
      while (currentId) {
        const parent = findNode(currentId);
        if (!parent) return null;
        if (parent.type === "folder" && parent.folderKind === "latex") {
          return parent;
        }
        currentId = parent.parentId;
      }
      return null;
    },
    [findNode]
  );

  const handleCompileLatexSource = React.useCallback(
    async (node: FileNode) => {
      if (readOnly) return;
      if (node.type !== "file" || !node.name.toLowerCase().endsWith(".tex")) return;

      const folder = findLatexFolderForFile(node);
      if (!folder) {
        addToast({
          type: "error",
          title: "LaTeX compile failed",
          description: "This file is not inside a LaTeX project folder.",
        });
        return;
      }

      try {
        const build = await compileLatex(projectId, folder.id, {
          main_file_id: node.id,
          stop_on_first_error: false,
        });
        addToast({
          type: "success",
          title: "LaTeX compile started",
          description: `${folder.name} · ${node.name}`,
          duration: 1800,
        });
        if (typeof window !== "undefined") {
          window.dispatchEvent(
            new CustomEvent("ds:latex-build", {
              detail: {
                projectId,
                folderId: folder.id,
                buildId: build.build_id,
                status: build.status,
                errorMessage: build.error_message ?? null,
              },
            })
          );
        }
      } catch (error) {
        console.error("Failed to compile LaTeX file:", error);
        addToast({
          type: "error",
          title: "LaTeX compile failed",
          description: error instanceof Error ? error.message : "Please try again.",
        });
      }
    },
    [addToast, findLatexFolderForFile, projectId, readOnly]
  );

  const handleDragOver = React.useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (!e.dataTransfer.types.includes("Files")) return;
    if (readOnly) return;
    setIsDragOver(true);
    const pointElement =
      typeof document !== "undefined"
        ? (document.elementFromPoint(e.clientX, e.clientY) as HTMLElement | null)
        : null;
    syncExternalDropTarget(
      resolveExternalDropTarget(pointElement ?? (e.target as HTMLElement))
    );
  }, [readOnly, resolveExternalDropTarget, syncExternalDropTarget]);

  const handleDragLeave = React.useCallback((e: React.DragEvent) => {
    e.preventDefault();
    // Only set to false if leaving the container entirely
    if (!containerRef.current?.contains(e.relatedTarget as Node)) {
      setIsDragOver(false);
      setExternalDropTargetId(null);
      setExternalDropTargetPath(null);
      clearExternalAutoExpand();
    }
  }, [clearExternalAutoExpand]);

  React.useEffect(() => {
    if (!selectionTargetId) return;

    let cancelled = false;
    let timerId: number | null = null;

    const reveal = (attempt = 0) => {
      if (cancelled) return;
      const tree = treeRef.current;
      if (!tree) {
        if (attempt < 8) {
          timerId = window.setTimeout(() => reveal(attempt + 1), 60 * (attempt + 1));
        }
        return;
      }

      tree.select(selectionTargetId, { focus: false, align: "center" });
      const node = tree.get(selectionTargetId);
      const listReady = Boolean(tree.list.current);
      if ((node && listReady) || attempt >= 8) {
        return;
      }

      timerId = window.setTimeout(() => reveal(attempt + 1), 80 * (attempt + 1));
    };

    reveal();

    return () => {
      cancelled = true;
      if (timerId != null) {
        window.clearTimeout(timerId);
      }
    };
  }, [selectionTargetId, visibleNodes.length, dimensions.height, dimensions.width]);

  React.useEffect(() => {
    if (nodesOverride) {
      syncedExpandedIdsRef.current = new Set();
      return;
    }
    const tree = treeRef.current;
    if (!tree) return;

    for (const id of syncedExpandedIdsRef.current) {
      if (expandedIds.has(id)) continue;
      const currentNode = tree.get(id);
      if (currentNode?.data.type === "folder" && currentNode.isOpen) {
        tree.close(id);
      }
    }

    const synced = new Set<string>();
    for (const id of expandedIds) {
      const currentNode = tree.get(id);
      if (currentNode?.data.type !== "folder") continue;
      synced.add(id);
      if (!currentNode.isOpen) {
        tree.open(id);
      }
    }

    syncedExpandedIdsRef.current = synced;
  }, [expandedIds, nodesOverride, visibleNodes]);

  const effectiveLoading = loadingOverride ?? isLoading;
  const showLoadingState = effectiveLoading && visibleNodes.length === 0;
  const showEmptyState = !effectiveLoading && !error && visibleNodes.length === 0;

  return (
    <div
      ref={containerRef}
      className={cn(
        "file-tree h-full relative",
        isDragOver && "bg-white/[0.03] ring-1 ring-inset ring-white/15",
        isDragOver && !externalDropTargetId && "file-tree-root-drop-active",
        className
      )}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onContextMenu={handleContextMenu}
    >
      {showLoadingState ? (
        <div className="flex h-full items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-[var(--file-tree-icon-muted)]" />
        </div>
      ) : error ? (
        <div className="flex h-full flex-col items-center justify-center p-4 text-center">
          <p className="mb-2 text-sm text-red-500">Failed to load files</p>
          <p className="text-xs text-soft-text-muted">{error}</p>
          <button
            onClick={() => loadFiles(projectId)}
            className="mt-4 rounded-soft-sm bg-soft-primary px-3 py-1.5 text-sm text-white transition-colors hover:bg-soft-primary/90"
          >
            Retry
          </button>
        </div>
      ) : showEmptyState ? (
        <div
          className={cn(
            "flex flex-col items-center justify-center h-full p-4 text-center",
            "rounded-2xl",
            "text-white/80",
            isDragOver &&
              "bg-white/[0.06] border border-dashed border-white/20 shadow-[0_10px_30px_rgba(0,0,0,0.35)]"
          )}
        >
          <div className="mb-4">
            <Icon3D name="folder-open" size="lg" className="opacity-95" />
          </div>
          <p className="text-sm font-medium mb-1">{emptyLabel || "No files yet"}</p>
          <p className="text-xs text-white/55 mb-4">
            Drop files here, or upload a starter file to begin.
          </p>
          <div className="flex gap-2">
            {!readOnly && (
              <label className="px-3 py-1.5 text-sm bg-white/10 text-white rounded-lg hover:bg-white/15 transition-colors cursor-pointer border border-white/10">
                <Upload className="h-4 w-4 inline mr-1" />
                Upload
                <input
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(e) => {
                    const files = Array.from(e.target.files || []);
                    if (files.length > 0) {
                      upload(null, files);
                    }
                    e.target.value = "";
                  }}
                />
              </label>
            )}
          </div>
        </div>
      ) : (
        <>
          {/* Drag overlay */}
          {isDragOver && (
            <div className="absolute inset-0 z-10 pointer-events-none">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.10),rgba(0,0,0,0.18))]" />
              <div className="absolute left-1/2 top-4 -translate-x-1/2">
                <div className="flex items-center gap-2 rounded-full border border-white/18 bg-black/35 px-3 py-1.5 text-[11px] font-medium text-white shadow-[0_12px_32px_rgba(0,0,0,0.28)] backdrop-blur-xl">
                  <Upload className="h-3.5 w-3.5" />
                  <span>Release to upload</span>
                </div>
              </div>
              <div className="absolute bottom-4 left-1/2 -translate-x-1/2">
                <div className="flex min-w-[220px] items-center gap-2 rounded-2xl border border-dashed border-white/22 bg-black/45 px-4 py-2 text-xs text-white shadow-[0_18px_40px_rgba(0,0,0,0.3)] backdrop-blur-xl">
                  <Icon3D name="folder-open" size="sm" className="opacity-95" />
                  <span className="font-medium">
                    {externalDropTargetPath
                      ? `Drop into ${externalDropTargetPath}`
                      : "Drop into workspace root"}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Tree */}
          <FileTreeDragContext.Provider value={dragContextValue}>
            <DndProvider backend={HTML5Backend}>
              <Tree
                ref={treeRef}
                data={visibleNodes}
                selection={selectionTargetId}
                idAccessor="id"
                childrenAccessor="children"
                openByDefault={Boolean(nodesOverride?.length)}
                className="file-tree-scroll"
                width={dimensions.width}
                height={typeof dimensions.height === "number" ? dimensions.height : 400}
                indent={16}
                rowHeight={rowHeight}
                paddingTop={4}
                paddingBottom={4}
                renderDragPreview={FileTreeDragPreview}
                // Handlers
                onMove={readOnly ? undefined : handleMove}
                onRename={readOnly ? undefined : handleRename}
                onActivate={handleActivate}
                // Require long-press to arm dragging
                disableDrag={(data) => readOnly || dragArmedId !== data.id}
                // Only folders can receive drops
                disableDrop={(args) =>
                  args.parentNode !== null && args.parentNode.data.type !== "folder"
                }
              >
                {FileTreeNode}
              </Tree>
            </DndProvider>
          </FileTreeDragContext.Provider>
        </>
      )}

      {/* Context menu */}
      {contextMenu && (
        <FileTreeContextMenu
          node={contextMenu.node!}
          position={contextMenu.position}
          onClose={() => setContextMenu(null)}
          onOpen={onFileOpen}
          onDownload={onFileDownload}
          onRevealInExplorer={onRevealInExplorer}
          onOpenContainingFolder={onOpenContainingFolder}
          onNewFile={(parentId) => {
            setCreateFileState({ open: true, parentId });
          }}
          onNewLatexProject={(parentId) => {
            setCreateLatexState({ open: true, parentId });
          }}
          onCompileLatexSource={handleCompileLatexSource}
          onRequestDelete={(node) => {
            setDeleteState({ open: true, node, loading: false });
          }}
          readOnly={readOnly}
        />
      )}

      {/* New file dialog */}
      {!readOnly && (
        <CreateFileDialog
          open={createFileState.open}
          parentId={createFileState.parentId}
          onOpenChange={(open) =>
            setCreateFileState((prev) => ({ ...prev, open }))
          }
          onCreated={(file) => {
            onFileOpen?.(file);
            treeRef.current?.scrollTo(file.id, "center");
          }}
        />
      )}

      {!readOnly && (
        <CreateLatexProjectDialog
          open={createLatexState.open}
          parentId={createLatexState.parentId}
          onOpenChange={(open) =>
            setCreateLatexState((prev) => ({ ...prev, open }))
          }
          onCreated={(folder) => {
            onFileOpen?.(folder);
            treeRef.current?.scrollTo(folder.id, "center");
          }}
        />
      )}

      {/* Delete confirmation */}
      <ConfirmModal
        open={deleteState.open}
        onClose={() => setDeleteState({ open: false, node: null, loading: false })}
        onConfirm={async () => {
          const target = deleteState.node;
          if (!target || deleteState.loading) return;
          try {
            setDeleteState((s) => ({ ...s, loading: true }));
            await useFileTreeStore.getState().delete([target.id]);
            setDeleteState({ open: false, node: null, loading: false });
          } catch (err) {
            console.error("Failed to delete:", err);
            setDeleteState((s) => ({ ...s, loading: false }));
          }
        }}
        title={
          deleteState.node
            ? `Delete ${deleteState.node.type === "folder" ? "folder" : "file"}`
            : "Delete"
        }
        description={
          deleteState.node
            ? `“${deleteState.node.name}” will be permanently deleted.`
            : "This item will be permanently deleted."
        }
        confirmText="Delete"
        cancelText="Cancel"
        variant="danger"
        loading={deleteState.loading}
      />
    </div>
  );
}

export default FileTree;
