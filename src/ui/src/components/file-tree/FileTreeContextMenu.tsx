"use client";

import * as React from "react";
import type { NodeApi } from "react-arborist";
import type { FileNode } from "@/lib/types/file";
import { useFileTreeStore } from "@/lib/stores/file-tree";
import {
  ExternalLink,
  FilePlus,
  FolderPlus,
  FolderOpen,
  Pencil,
  Copy,
  Scissors,
  Clipboard,
  Braces,
  Play,
  Trash2,
  Download,
  RefreshCw,
} from "lucide-react";
import { PngIcon } from "@/components/ui/png-icon";
import { copyToClipboard } from "@/lib/clipboard";
import { useToast } from "@/components/ui/toast";
import { useI18n } from "@/lib/i18n/useI18n";
import { toProjectRelativeDisplayPath } from "@/lib/utils/project-relative-path";

function withPngFallback(
  name: string,
  Fallback: React.ComponentType<{ className?: string }>
): React.ComponentType<{ className?: string }> {
  return function PngWrapped({ className }: { className?: string }) {
    return (
      <PngIcon
        name={name}
        size={16}
        className={className}
        fallback={<Fallback className={className} />}
      />
    );
  };
}

const ExternalLinkIcon = withPngFallback("ExternalLink", ExternalLink);
const CopyIcon = withPngFallback("Copy", Copy);
const ScissorsIcon = withPngFallback("Scissors", Scissors);
const ClipboardIcon = withPngFallback("Clipboard", Clipboard);
const BracesIcon = withPngFallback("Braces", Braces);
const PlayIcon = withPngFallback("Play", Play);
const DownloadIcon = withPngFallback("Download", Download);
const RefreshCwIcon = withPngFallback("RefreshCw", RefreshCw);
const FolderOpenIcon = withPngFallback("FolderOpen", FolderOpen);

/**
 * FileTreeContextMenu props
 */
export interface FileTreeContextMenuProps {
  /** The node that was right-clicked */
  node: NodeApi<FileNode>;

  /** Position for the menu */
  position: { x: number; y: number };

  /** Callback when menu should close */
  onClose: () => void;

  /** Callback when file should be opened */
  onOpen?: (node: FileNode) => void;

  /** Callback when download is requested */
  onDownload?: (node: FileNode) => void;

  /** Callback when "New File" is requested (folder context) */
  onNewFile?: (parentId: string | null) => void;

  /** Callback when "New LaTeX Project" is requested (folder context) */
  onNewLatexProject?: (parentId: string | null) => void;

  /** Callback when "Compile LaTeX" is requested (tex file context) */
  onCompileLatexSource?: (node: FileNode) => void;

  /** Callback when delete should be confirmed externally */
  onRequestDelete?: (node: FileNode) => void;

  /** Callback when the node should be revealed in the full explorer */
  onRevealInExplorer?: (node: FileNode) => void;

  /** Callback when the node's containing folder should be opened */
  onOpenContainingFolder?: (node: FileNode) => void;

  /** When true, show only non-mutating actions (open/download). */
  readOnly?: boolean;
}

/**
 * Context menu item component
 */
function MenuItem({
  icon: Icon,
  label,
  shortcut,
  onClick,
  disabled = false,
  destructive = false,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  shortcut?: string;
  onClick: () => void;
  disabled?: boolean;
  destructive?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`
        flex items-center w-full px-3 py-1.5 text-sm text-left
        ${disabled ? "opacity-50 cursor-not-allowed" : "hover:bg-soft-bg-elevated"}
        ${destructive ? "text-red-500 hover:text-red-600" : "text-soft-text-primary"}
      `}
    >
      <Icon className="h-4 w-4 mr-3" />
      <span className="flex-1">{label}</span>
      {shortcut && (
        <span className="text-xs text-soft-text-muted ml-4">{shortcut}</span>
      )}
    </button>
  );
}

/**
 * Separator component
 */
function Separator() {
  return <div className="h-px bg-soft-border my-1" />;
}

/**
 * FileTreeContextMenu - Context menu for file tree nodes
 *
 * Provides actions like open, create, rename, copy, paste, delete
 */
export function FileTreeContextMenu({
  node,
  position,
  onClose,
  onOpen,
  onDownload,
  onNewFile,
  onNewLatexProject,
  onCompileLatexSource,
  onRequestDelete,
  onRevealInExplorer,
  onOpenContainingFolder,
  readOnly = false,
}: FileTreeContextMenuProps) {
  const menuRef = React.useRef<HTMLDivElement>(null);
  const { addToast } = useToast();
  const { t } = useI18n("workspace");
  const {
    createFolder,
    startRenaming,
    copy,
    cut,
    paste,
    delete: deleteNodes,
    clipboard,
    refresh,
  } = useFileTreeStore();

  const isFolder = node.data.type === "folder";
  const isTexFile =
    node.data.type === "file" && node.data.name.toLowerCase().endsWith(".tex");
  const readOnlyMode = Boolean(readOnly);
  const hasContainingFolder = Boolean(node.data.parentId);
  const hasProjectPath = Boolean(node.data.path || node.data.name);

  // Close on click outside
  React.useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  // Adjust menu position to stay within viewport
  const [adjustedPosition, setAdjustedPosition] = React.useState(position);

  React.useEffect(() => {
    if (menuRef.current) {
      const rect = menuRef.current.getBoundingClientRect();
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;

      let x = position.x;
      let y = position.y;

      if (x + rect.width > viewportWidth) {
        x = viewportWidth - rect.width - 8;
      }
      if (y + rect.height > viewportHeight) {
        y = viewportHeight - rect.height - 8;
      }

      setAdjustedPosition({ x, y });
    }
  }, [position]);

  // Handlers
  const handleOpen = () => {
    if (onOpen) {
      onOpen(node.data);
    }
    onClose();
  };

  const handleNewFile = async () => {
    const parentId = isFolder ? node.data.id : node.data.parentId;
    try {
      onNewFile?.(parentId);
    } catch (error) {
      console.error("Failed to create file:", error);
    }
    onClose();
  };

  const handleNewFolder = async () => {
    const parentId = isFolder ? node.data.id : node.data.parentId;
    try {
      await createFolder(parentId, "New Folder");
    } catch (error) {
      console.error("Failed to create folder:", error);
    }
    onClose();
  };

  const handleNewLatexProject = async () => {
    const parentId = isFolder ? node.data.id : node.data.parentId;
    try {
      onNewLatexProject?.(parentId);
    } catch (error) {
      console.error("Failed to create LaTeX project:", error);
    }
    onClose();
  };

  const handleCompileLatexSource = () => {
    try {
      onCompileLatexSource?.(node.data);
    } catch (error) {
      console.error("Failed to compile LaTeX project:", error);
    }
    onClose();
  };

  const handleRename = () => {
    startRenaming(node.data.id);
    node.edit();
    onClose();
  };

  const handleCopy = () => {
    copy([node.data.id]);
    onClose();
  };

  const handleCut = () => {
    cut([node.data.id]);
    onClose();
  };

  const handlePaste = async () => {
    const targetId = isFolder ? node.data.id : node.data.parentId;
    try {
      await paste(targetId);
    } catch (error) {
      console.error("Failed to paste:", error);
    }
    onClose();
  };

  const handleDelete = async () => {
    if (onRequestDelete) {
      onRequestDelete(node.data);
      onClose();
      return;
    }

    try {
      await deleteNodes([node.data.id]);
    } catch (error) {
      console.error("Failed to delete:", error);
    }
    onClose();
  };

  const handleDownload = () => {
    if (onDownload) {
      onDownload(node.data);
    }
    onClose();
  };

  const handleRefresh = async () => {
    try {
      await refresh();
    } catch (error) {
      console.error("Failed to refresh:", error);
    }
    onClose();
  };

  const handleRevealInExplorer = () => {
    onRevealInExplorer?.(node.data);
    onClose();
  };

  const handleOpenContainingFolder = () => {
    onOpenContainingFolder?.(node.data);
    onClose();
  };

  const handleCopyPath = async () => {
    const projectPath = toProjectRelativeDisplayPath(node.data.path || node.data.name);
    const copied = await copyToClipboard(projectPath);
    addToast({
      type: copied ? "success" : "error",
      title: copied
        ? t("explorer_path_copied", undefined, "Path copied")
        : t("explorer_path_copy_failed", undefined, "Failed to copy path"),
      description: projectPath,
      duration: copied ? 1800 : 2400,
    });
    onClose();
  };

  return (
    <div
      ref={menuRef}
      className="fixed z-[10002] min-w-[180px] bg-soft-bg-base border border-soft-border rounded-soft-sm shadow-soft-md py-1"
      style={{
        left: adjustedPosition.x,
        top: adjustedPosition.y,
      }}
    >
      {/* Open (files only) */}
      {!isFolder && (
        <>
          <MenuItem
            icon={ExternalLinkIcon}
            label={t("explorer_open_file", undefined, "Open")}
            onClick={handleOpen}
          />
          <Separator />
        </>
      )}

      {isTexFile && !readOnlyMode && (
        <>
          <MenuItem
            icon={PlayIcon}
            label={t("explorer_compile_latex", undefined, "Compile LaTeX")}
            onClick={handleCompileLatexSource}
          />
          <Separator />
        </>
      )}

      {/* New items (for folders) */}
      {isFolder && !readOnlyMode && (
        <>
          <MenuItem
            icon={FilePlus}
            label={t("explorer_new_file")}
            onClick={handleNewFile}
          />
          <MenuItem
            icon={BracesIcon}
            label={t("explorer_new_latex_project", undefined, "New LaTeX project")}
            onClick={handleNewLatexProject}
          />
          <MenuItem
            icon={FolderPlus}
            label={t("explorer_new_folder")}
            onClick={handleNewFolder}
          />
          <Separator />
        </>
      )}

      <MenuItem
        icon={FolderOpenIcon}
        label={t("explorer_reveal_in_files", undefined, "Reveal in Explorer")}
        onClick={handleRevealInExplorer}
        disabled={!onRevealInExplorer}
      />
      <MenuItem
        icon={FolderOpenIcon}
        label={t("explorer_open_containing_folder", undefined, "Open containing folder")}
        onClick={handleOpenContainingFolder}
        disabled={!onOpenContainingFolder || !hasContainingFolder}
      />
      <MenuItem
        icon={CopyIcon}
        label={t("explorer_copy_path", undefined, "Copy Path")}
        onClick={handleCopyPath}
        disabled={!hasProjectPath}
      />

      <Separator />

      {!readOnlyMode && (
        <>
          <MenuItem
            icon={Pencil}
            label={t("explorer_rename", undefined, "Rename")}
            shortcut="F2"
            onClick={handleRename}
          />

          <Separator />

          <MenuItem
            icon={CopyIcon}
            label={t("explorer_copy", undefined, "Copy")}
            shortcut="Ctrl+C"
            onClick={handleCopy}
          />
          <MenuItem
            icon={ScissorsIcon}
            label={t("explorer_cut", undefined, "Cut")}
            shortcut="Ctrl+X"
            onClick={handleCut}
          />
          {isFolder && (
            <MenuItem
              icon={ClipboardIcon}
              label={t("explorer_paste", undefined, "Paste")}
              shortcut="Ctrl+V"
              onClick={handlePaste}
              disabled={!clipboard}
            />
          )}

          <Separator />
        </>
      )}

      {/* Download (files only) */}
      {!isFolder && (
        <MenuItem
          icon={DownloadIcon}
          label={t("explorer_download", undefined, "Download")}
          onClick={handleDownload}
        />
      )}

      {/* Refresh (folders only) */}
      {isFolder && (
        <MenuItem
          icon={RefreshCwIcon}
          label={t("explorer_refresh")}
          onClick={handleRefresh}
        />
      )}

      {!readOnlyMode && (
        <>
          <Separator />
          <MenuItem
            icon={Trash2}
            label={t("explorer_delete", undefined, "Delete")}
            shortcut="Del"
            onClick={handleDelete}
            destructive
          />
        </>
      )}
    </div>
  );
}

export default FileTreeContextMenu;
