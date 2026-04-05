"use client";

/**
 * useOpenFile Hook
 *
 * Provides unified file opening logic that integrates with the plugin system
 * and tab management.
 *
 * @module hooks/useOpenFile
 */

import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useTabsStore } from "@/lib/stores/tabs";
import { useFileTreeStore } from "@/lib/stores/file-tree";
import { builtinPluginLoader } from "@/lib/plugin/builtin-loader";
import type { FileNode } from "@/lib/types/file";
import type { TabContext } from "@/lib/types/tab";
import {
  getPluginIdFromExtension,
  getPluginIdFromMimeType,
  BUILTIN_PLUGINS,
} from "@/lib/types/plugin";
import { downloadFileById } from "@/lib/api/files";
import { toFilesResourcePath } from "@/lib/utils/resource-paths";

/**
 * Options for opening a file
 */
export interface OpenFileOptions {
  /** Force use a specific plugin */
  pluginId?: string;

  /** Additional custom data to pass to the plugin */
  customData?: Record<string, unknown>;
}

/**
 * Result of opening a file
 */
export interface OpenFileResult {
  /** Whether the file was opened successfully */
  success: boolean;

  /** Tab ID if file was opened in a tab */
  tabId?: string;

  /** Error message if opening failed */
  error?: string;

  /** Whether the file was downloaded instead of opened */
  downloaded?: boolean;
}

/**
 * useOpenFile - Hook for opening files in tabs
 *
 * Determines the appropriate plugin for a file and opens it in a new tab.
 * Falls back to download if no plugin can handle the file type.
 */
export function useOpenFile() {
  const navigate = useNavigate();
  const openTab = useTabsStore((state) => state.openTab);
  const findTabByContext = useTabsStore((state) => state.findTabByContext);
  const setActiveTab = useTabsStore((state) => state.setActiveTab);
  const updateTabPlugin = useTabsStore((state) => state.updateTabPlugin);
  const findNode = useFileTreeStore((state) => state.findNode);
  const storeProjectId = useFileTreeStore((state) => state.projectId);

  const findLatexFolderForFile = useCallback(
    (file: FileNode): FileNode | null => {
      if (!file.parentId) return null;
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

  const isLatexSourceFile = useCallback((fileName: string): boolean => {
    const lower = fileName.toLowerCase();
    return lower.endsWith(".tex") || lower.endsWith(".bib");
  }, []);

  const isMarkdownFileName = useCallback((fileName: string): boolean => {
    const lower = fileName.toLowerCase();
    return (
      lower.endsWith(".md") ||
      lower.endsWith(".markdown") ||
      lower.endsWith(".mdx")
    );
  }, []);

  const isMarkdownMimeType = useCallback((mimeType?: string | null): boolean => {
    if (!mimeType) return false;
    const normalized = mimeType.toLowerCase();
    return normalized === "text/markdown" || normalized === "text/x-markdown";
  }, []);

  const preloadPlugin = useCallback((pluginId?: string | null) => {
    if (!pluginId) return;
    void builtinPluginLoader.preload([pluginId]);
  }, []);

  /**
   * Get the best plugin ID for a file
   */
  const getPluginForFile = useCallback(
    (file: FileNode): string | null => {
      // Notebook nodes are handled by the notebook plugin directly
      if (file.type === "notebook") {
        return BUILTIN_PLUGINS.NOTEBOOK;
      }

      if (isMarkdownFileName(file.name) || isMarkdownMimeType(file.mimeType)) {
        return BUILTIN_PLUGINS.NOTEBOOK;
      }

      // Prefer extension-based resolution when MIME type is too generic.
      const extPluginId = getPluginIdFromExtension(file.name);

      // Try MIME type first (more reliable when accurate)
      if (file.mimeType) {
        const mimePluginId = getPluginIdFromMimeType(file.mimeType);
        if (mimePluginId) {
          // If backend/client reports text/plain for code files, extension should win.
          if (mimePluginId === BUILTIN_PLUGINS.TEXT_VIEWER && extPluginId) {
            return extPluginId;
          }
          return mimePluginId;
        }
      }

      // Fall back to extension
      if (extPluginId) return extPluginId;

      // No plugin found
      return null;
    },
    [isMarkdownFileName, isMarkdownMimeType]
  );

  /**
   * Download a file
   */
  const downloadFile = useCallback(async (file: FileNode): Promise<void> => {
    try {
      await downloadFileById(file.id, file.name);
    } catch (error) {
      console.error("Failed to download file:", error);
      throw error;
    }
  }, []);

  /**
   * Open a file in a tab
   */
  const openFileInTab = useCallback(
    async (file: FileNode, options: OpenFileOptions = {}): Promise<OpenFileResult> => {
      const resolvedProjectId =
        typeof options.customData?.projectId === "string"
          ? options.customData.projectId
          : storeProjectId ?? undefined;
      const mergedCustomData =
        resolvedProjectId != null
          ? { ...options.customData, projectId: resolvedProjectId }
          : options.customData;

      if (resolvedProjectId && isLatexSourceFile(file.name)) {
        const latexFolder = findLatexFolderForFile(file);
        if (latexFolder) {
          preloadPlugin(BUILTIN_PLUGINS.LATEX);
          const readOnly =
            Boolean(options.customData?.readOnly) ||
            Boolean(options.customData?.readonly);
          const tabId = openTab({
            pluginId: BUILTIN_PLUGINS.LATEX,
            context: {
              type: "custom",
              resourceId: latexFolder.id,
              resourceName: latexFolder.name,
              customData: {
                projectId: resolvedProjectId,
                latexFolderId: latexFolder.id,
                mainFileId: latexFolder.latex?.mainFileId ?? null,
                openFileId: file.id,
                readOnly,
              },
            },
            title: latexFolder.name,
          });

          return { success: true, tabId };
        }
      }

      // Determine plugin to use
      const pluginId = options.pluginId || getPluginForFile(file);

      if (!pluginId) {
        // No plugin available - offer download
        try {
          await downloadFile(file);
          return {
            success: true,
            downloaded: true,
          };
        } catch (error) {
          return {
            success: false,
            error: error instanceof Error ? error.message : "Download failed",
          };
        }
      }

      // Build context for the plugin
      preloadPlugin(pluginId);
      const context: TabContext = {
        type: file.type === "notebook" ? "notebook" : "file",
        resourceId: file.id,
        resourcePath: toFilesResourcePath(file.path),
        resourceName: file.name,
        mimeType: file.mimeType,
        customData: mergedCustomData,
      };

      const existing = findTabByContext(context);
      if (existing) {
        if (existing.pluginId !== pluginId) {
          preloadPlugin(pluginId);
          updateTabPlugin(existing.id, pluginId, context);
        }
        setActiveTab(existing.id);
        return { success: true, tabId: existing.id };
      }

      // Open tab
      const tabId = openTab({
        pluginId,
        context,
        title: file.name,
      });

      return {
        success: true,
        tabId,
      };
    },
    [
      downloadFile,
      findLatexFolderForFile,
      findTabByContext,
      getPluginForFile,
      isLatexSourceFile,
      openTab,
      setActiveTab,
      storeProjectId,
      preloadPlugin,
      updateTabPlugin,
    ]
  );

  /**
   * Get all plugins that can open a file
   */
  const getPluginsForFile = useCallback(
    (file: FileNode): string[] => {
      const plugins: string[] = [];

      // Check extension-based plugins
      const extPlugin = getPluginIdFromExtension(file.name);
      if (extPlugin) plugins.push(extPlugin);

      // Check MIME-based plugins
      if (file.mimeType) {
        const mimePlugin = getPluginIdFromMimeType(file.mimeType);
        if (mimePlugin && !plugins.includes(mimePlugin)) {
          plugins.push(mimePlugin);
        }
      }

      return plugins;
    },
    []
  );

  /**
   * Check if a file can be opened in the app
   */
  const canOpenFile = useCallback(
    (file: FileNode): boolean => {
      return getPluginForFile(file) !== null;
    },
    [getPluginForFile]
  );

  // Convenience methods for specific file types

  /**
   * Open a notebook file
   */
  const openNotebook = useCallback(
    (
      resourceId: string,
      resourceName: string,
      projectId?: string,
      options: { readonly?: boolean; customData?: Record<string, unknown> } = {}
    ): string => {
      const mergedCustomData =
        projectId || options.readonly || options.customData
          ? {
              ...(options.customData || {}),
              ...(projectId ? { projectId } : {}),
              ...(options.readonly ? { readonly: Boolean(options.readonly) } : {}),
            }
          : undefined
      const context: TabContext = {
        type: "notebook",
        resourceId,
        resourceName,
        customData: mergedCustomData,
      };

      return openTab({
        pluginId: BUILTIN_PLUGINS.NOTEBOOK,
        context,
        title: resourceName,
      });
    },
    [openTab]
  );

  /**
   * Open settings
   */
  const openSettings = useCallback(
    (section?: string): string => {
      navigate(section ? `/settings/${section}` : "/settings");
      return section ? `route:/settings/${section}` : "route:/settings";
    },
    [navigate]
  );

  /**
   * Open search
   */
  const openSearch = useCallback(
    (query?: string): string => {
      const context: TabContext = {
        type: "custom",
        customData: { query },
      };

      return openTab({
        pluginId: BUILTIN_PLUGINS.SEARCH,
        context,
        title: "Search",
      });
    },
    [openTab]
  );

  return {
    // Main functions
    openFileInTab,
    downloadFile,
    getPluginForFile,
    getPluginsForFile,
    canOpenFile,

    // Convenience functions
    openNotebook,
    openSettings,
    openSearch,
  };
}

export default useOpenFile;
