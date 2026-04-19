/**
 * Plugin System Initialization
 *
 * Registers all builtin plugins at application startup.
 * This module should be called once during app initialization.
 *
 * @module lib/plugin/init
 */

import { pluginRegistry } from "./registry";
import { builtinPluginLoader } from "./builtin-loader";
import type { UnifiedPluginManifest } from "@/lib/types/plugin";
import { cliPluginManifest } from "@/lib/plugins/cli/manifest";
import { codeEditorManifest } from "@/lib/plugins/code-editor/manifest";
import { labPluginManifest } from "@/lib/plugins/lab/manifest";

// ============================================================
// Builtin Plugin Manifests
// ============================================================

/**
 * PDF Viewer Plugin Manifest
 */
const pdfViewerManifest: UnifiedPluginManifest = {
  id: "@ds/plugin-pdf-viewer",
  name: "PDF Viewer",
  version: "1.0.0",
  description: "View and annotate PDF documents",
  type: "builtin",
  frontend: {
    entry: "components/plugins/pdf-viewer",
    renderMode: "react",
    fileAssociations: [
      {
        extensions: [".pdf"],
        mimeTypes: ["application/pdf"],
        priority: 100,
      },
    ],
  },
  contributes: {
    sidebarMenus: [
      {
        id: "pdf-viewer",
        title: "PDF Viewer",
        icon: "file-text",
        order: 10,
      },
    ],
  },
  permissions: {
    frontend: ["file:read", "annotation:read", "annotation:write"],
  },
  lifecycle: {
    activationEvents: ["onFileType:pdf"],
  },
};

/**
 * PDF Markdown Plugin Manifest
 */
const pdfMarkdownManifest: UnifiedPluginManifest = {
  id: "@ds/plugin-pdf-markdown",
  name: "PDF Markdown",
  version: "1.0.0",
  description: "View MinerU Markdown output for PDFs",
  type: "builtin",
  frontend: {
    entry: "plugins/pdf-markdown/PdfMarkdownPlugin",
    renderMode: "react",
  },
  contributes: {
    tabIcon: "file-text",
  },
  permissions: {
    frontend: ["file:read"],
  },
};


/**
 * Notebook Editor Plugin Manifest
 */
const notebookManifest: UnifiedPluginManifest = {
  id: "@ds/plugin-notebook",
  name: "Notebook Editor",
  version: "1.0.0",
  description: "Novel-based notebook editor with real-time collaboration",
  type: "builtin",
  frontend: {
    entry: "plugins/notebook/components/NotebookEditor",
    renderMode: "react",
    fileAssociations: [
      {
        extensions: [".ds", ".notebook", ".dsnb"],
        mimeTypes: ["application/x-blocksuite-notebook"],
        priority: 100,
      },
      {
        extensions: [".md", ".markdown"],
        mimeTypes: ["text/markdown", "text/x-markdown"],
        priority: 95,
      },
    ],
    multiInstance: true,
  },
  backend: {
    entry: "app.plugins.builtin.notebook_tools",
    tools: [],
  },
  contributes: {
    sidebarMenus: [
      {
        id: "notebook",
        title: "Notebooks",
        icon: "book-open",
        order: 5,
      },
    ],
    tabIcon: "file-text",
    // Slash commands are handled inside the Novel editor UI.
  },
  permissions: {
    frontend: [
      "file:read",
      "file:write",
      "notebook:read",
      "notebook:write",
    ],
    backend: [
      "database:read",
      "database:write",
      "file:read",
      "file:write",
    ],
  },
  lifecycle: {
    activationEvents: ["onFileType:notebook", "onCommand:newNotebook"],
    onActivate: "activate",
    onDeactivate: "deactivate",
  },
};

/**
 * LaTeX Plugin Manifest (Stage 11)
 */
const latexManifest: UnifiedPluginManifest = {
  id: "@ds/plugin-latex",
  name: "LaTeX",
  version: "1.0.0",
  description: "Overleaf-like LaTeX project editor",
  type: "builtin",
  frontend: {
    entry: "plugins/latex/LatexPlugin",
    renderMode: "react",
    multiInstance: true,
  },
  contributes: {
    tabIcon: "file-text",
  },
  permissions: {
    frontend: ["file:read", "file:write"],
  },
  lifecycle: {
    activationEvents: ["onCommand:openLatex"],
  },
};

const gitDiffViewerManifest: UnifiedPluginManifest = {
  id: "@ds/plugin-git-diff-viewer",
  name: "Git Diff Viewer",
  version: "1.0.0",
  description: "View quest diff files in a centered workspace tab",
  type: "builtin",
  frontend: {
    entry: "plugins/git-diff-viewer/GitDiffViewerPlugin",
    renderMode: "react",
    multiInstance: true,
  },
  contributes: {
    tabIcon: "git-compare",
  },
  permissions: {
    frontend: ["project:read", "file:read"],
  },
  lifecycle: {
    activationEvents: ["onCommand:openGitDiff"],
  },
};

const gitCommitViewerManifest: UnifiedPluginManifest = {
  id: "@ds/plugin-git-commit-viewer",
  name: "Git Commit Viewer",
  version: "1.0.0",
  description: "Inspect a git commit and browse its changed files in a centered workspace tab",
  type: "builtin",
  frontend: {
    entry: "plugins/git-commit-viewer/GitCommitViewerPlugin",
    renderMode: "react",
    multiInstance: true,
  },
  contributes: {
    tabIcon: "git-commit",
  },
  permissions: {
    frontend: ["project:read", "file:read"],
  },
  lifecycle: {
    activationEvents: ["onCommand:openGitCommit"],
  },
};

/**
 * Code Viewer Plugin Manifest
 */
const codeViewerManifest: UnifiedPluginManifest = {
  id: "@ds/plugin-code-viewer",
  name: "Code Viewer",
  version: "1.0.0",
  description: "View and edit source code with syntax highlighting",
  type: "builtin",
  frontend: {
    entry: "components/plugins/code-viewer",
    renderMode: "react",
    fileAssociations: [
      {
        extensions: [
          ".js",
          ".jsx",
          ".ts",
          ".tsx",
          ".py",
          ".java",
          ".c",
          ".cpp",
          ".h",
          ".hpp",
          ".cs",
          ".go",
          ".rs",
          ".rb",
          ".php",
          ".swift",
          ".kt",
          ".scala",
          ".r",
          ".m",
          ".mm",
          ".sh",
          ".bash",
          ".zsh",
          ".fish",
          ".ps1",
          ".sql",
          ".graphql",
          ".yaml",
          ".yml",
          ".toml",
          ".ini",
          ".cfg",
          ".conf",
          ".xml",
          ".html",
          ".htm",
          ".css",
          ".scss",
          ".sass",
          ".less",
          ".vue",
          ".svelte",
        ],
        mimeTypes: [
          "text/javascript",
          "text/typescript",
          "text/x-python",
          "text/x-java",
          "text/x-c",
          "text/x-cpp",
          "application/json",
          "text/html",
          "text/css",
        ],
        priority: 80,
      },
    ],
  },
  contributes: {},
  permissions: {
    frontend: ["file:read", "file:write"],
  },
  lifecycle: {
    activationEvents: ["onFileType:code"],
  },
};

/**
 * Image Viewer Plugin Manifest
 */
const imageViewerManifest: UnifiedPluginManifest = {
  id: "@ds/plugin-image-viewer",
  name: "Image Viewer",
  version: "1.0.0",
  description: "View images with zoom and pan support",
  type: "builtin",
  frontend: {
    entry: "components/plugins/image-viewer",
    renderMode: "react",
    fileAssociations: [
      {
        extensions: [
          ".png",
          ".jpg",
          ".jpeg",
          ".gif",
          ".webp",
          ".svg",
          ".bmp",
          ".ico",
          ".tiff",
          ".tif",
        ],
        mimeTypes: [
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "image/svg+xml",
          "image/bmp",
          "image/x-icon",
          "image/tiff",
        ],
        priority: 100,
      },
    ],
  },
  contributes: {},
  permissions: {
    frontend: ["file:read"],
  },
  lifecycle: {
    activationEvents: ["onFileType:image"],
  },
};

/**
 * Text Viewer Plugin Manifest
 */
const textViewerManifest: UnifiedPluginManifest = {
  id: "@ds/plugin-text-viewer",
  name: "Text Viewer",
  version: "1.0.0",
  description: "View and edit plain text files",
  type: "builtin",
  frontend: {
    entry: "components/plugins/text-viewer",
    renderMode: "react",
    fileAssociations: [
      {
        extensions: [".txt", ".log", ".text", ".readme"],
        mimeTypes: ["text/plain"],
        priority: 50,
      },
    ],
  },
  contributes: {},
  permissions: {
    frontend: ["file:read", "file:write"],
  },
  lifecycle: {
    activationEvents: ["onFileType:text"],
  },
};

/**
 * Markdown Viewer Plugin Manifest
 */
const markdownViewerManifest: UnifiedPluginManifest = {
  id: "@ds/plugin-markdown-viewer",
  name: "Markdown Viewer",
  version: "1.0.0",
  description: "View and edit Markdown documents with live preview",
  type: "builtin",
  frontend: {
    entry: "components/plugins/markdown-viewer",
    renderMode: "react",
    fileAssociations: [
      {
        extensions: [".mdx"],
        mimeTypes: ["text/markdown", "text/x-markdown"],
        priority: 98,
      },
    ],
  },
  contributes: {},
  permissions: {
    frontend: ["file:read", "file:write"],
  },
  lifecycle: {
    activationEvents: ["onFileType:markdown"],
  },
};

/**
 * Search Plugin Manifest
 */
const searchManifest: UnifiedPluginManifest = {
  id: "@ds/plugin-search",
  name: "Search",
  version: "1.0.0",
  description: "Search across files and projects",
  type: "builtin",
  frontend: {
    entry: "components/plugins/search",
    renderMode: "react",
  },
  contributes: {
    sidebarMenus: [
      {
        id: "search",
        title: "Search",
        icon: "search",
        order: 15,
      },
    ],
  },
  permissions: {
    frontend: ["file:read", "project:read"],
  },
  lifecycle: {
    activationEvents: ["onCommand:openSearch"],
  },
};

/**
 * Document Viewer Plugin Manifest (Office documents)
 */
const docViewerManifest: UnifiedPluginManifest = {
  id: "@ds/plugin-doc-viewer",
  name: "Document Viewer",
  version: "1.0.0",
  description: "View Office documents including Word, Excel, and PowerPoint",
  type: "builtin",
  frontend: {
    entry: "components/plugins/doc-viewer",
    renderMode: "react",
    fileAssociations: [
      {
        extensions: [".docx", ".doc"],
        mimeTypes: [
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          "application/msword",
        ],
        priority: 70,
      },
      {
        extensions: [".xlsx", ".xls"],
        mimeTypes: [
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          "application/vnd.ms-excel",
        ],
        priority: 70,
      },
      {
        extensions: [".pptx", ".ppt"],
        mimeTypes: [
          "application/vnd.openxmlformats-officedocument.presentationml.presentation",
          "application/vnd.ms-powerpoint",
        ],
        priority: 70,
      },
      {
        extensions: [".odt", ".ods", ".odp"],
        mimeTypes: [
          "application/vnd.oasis.opendocument.text",
          "application/vnd.oasis.opendocument.spreadsheet",
          "application/vnd.oasis.opendocument.presentation",
        ],
        priority: 70,
      },
    ],
  },
  contributes: {},
  permissions: {
    frontend: ["file:read"],
  },
  lifecycle: {
    activationEvents: ["onFileType:document"],
  },
};

// ============================================================
// All Builtin Plugin Manifests
// ============================================================

/**
 * Array of all builtin plugin manifests
 */
export const BUILTIN_PLUGIN_MANIFESTS: UnifiedPluginManifest[] = [
  labPluginManifest,
  cliPluginManifest,
  pdfViewerManifest,
  pdfMarkdownManifest,
  notebookManifest,
  latexManifest,
  gitDiffViewerManifest,
  gitCommitViewerManifest,
  codeEditorManifest,
  codeViewerManifest,
  imageViewerManifest,
  textViewerManifest,
  markdownViewerManifest,
  docViewerManifest,
  searchManifest,
];

/**
 * Plugin IDs that should be preloaded for better UX
 */
export const PRELOAD_PLUGIN_IDS: string[] = [
  "@ds/plugin-code-editor",
  "@ds/plugin-code-viewer",
  "@ds/plugin-cli",
  "@ds/plugin-text-viewer",
  "@ds/plugin-markdown-viewer",
];

let commonPluginPreloadPromise: Promise<void> | null = null;
let commonPluginPreloadScheduled = false;

// ============================================================
// Initialization Functions
// ============================================================

/**
 * Initialize all builtin plugins
 *
 * This function should be called once during application startup.
 * It registers all builtin plugin manifests with the plugin registry.
 *
 * @example
 * ```typescript
 * // In your app initialization code
 * import { initializeBuiltinPlugins } from '@/lib/plugin/init';
 *
 * export default function App() {
 *   useEffect(() => {
 *     initializeBuiltinPlugins();
 *   }, []);
 *
 *   return <YourApp />;
 * }
 * ```
 */
export function initializeBuiltinPlugins(): void {
  console.log("[PluginInit] Initializing builtin plugins...");

  // Register all builtin plugin manifests
  BUILTIN_PLUGIN_MANIFESTS.forEach((manifest) => {
    try {
      // Guard against duplicate registrations when init runs more than once.
      if (pluginRegistry.hasPlugin(manifest.id)) {
        console.debug(`[PluginInit] Plugin already registered: ${manifest.id}`);
        return;
      }
      pluginRegistry.register(manifest);
      console.log(`[PluginInit] Registered: ${manifest.id}`);
    } catch (error) {
      console.error(
        `[PluginInit] Failed to register plugin ${manifest.id}:`,
        error
      );
    }
  });

  console.log(
    `[PluginInit] Initialized ${BUILTIN_PLUGIN_MANIFESTS.length} builtin plugins`
  );
}

/**
 * Preload frequently used plugins for better UX
 *
 * This function preloads commonly used plugins to improve
 * initial load times when users first open them.
 *
 * @example
 * ```typescript
 * // After initializing plugins
 * await preloadCommonPlugins();
 * ```
 */
export async function preloadCommonPlugins(): Promise<void> {
  if (commonPluginPreloadPromise) {
    return commonPluginPreloadPromise;
  }
  console.log("[PluginInit] Preloading common plugins...");

  commonPluginPreloadPromise = (async () => {
    try {
      await builtinPluginLoader.preload(PRELOAD_PLUGIN_IDS);
      console.log(
        `[PluginInit] Preloaded ${PRELOAD_PLUGIN_IDS.length} plugins`
      );
    } catch (error) {
      console.warn("[PluginInit] Failed to preload some plugins:", error);
    }
  })();

  return commonPluginPreloadPromise;
}

export function scheduleCommonPluginPreload(
  delayMs = 80
): () => void {
  if (
    typeof window === "undefined" ||
    commonPluginPreloadPromise ||
    commonPluginPreloadScheduled
  ) {
    return () => {};
  }

  commonPluginPreloadScheduled = true;
  let cancelled = false;
  let timeoutId: number | null = null;
  let idleId: number | null = null;

  const run = () => {
    if (cancelled) {
      commonPluginPreloadScheduled = false;
      return;
    }
    commonPluginPreloadScheduled = false;
    void preloadCommonPlugins();
  };

  if (typeof window.requestIdleCallback === "function") {
    idleId = window.requestIdleCallback(run, { timeout: 900 });
  } else {
    timeoutId = window.setTimeout(run, delayMs);
  }

  return () => {
    cancelled = true;
    commonPluginPreloadScheduled = false;
    if (idleId != null && typeof window.cancelIdleCallback === "function") {
      window.cancelIdleCallback(idleId);
    }
    if (timeoutId != null) {
      window.clearTimeout(timeoutId);
    }
  };
}

/**
 * Initialize the complete plugin system
 *
 * This is a convenience function that initializes builtin plugins
 * and optionally preloads common plugins.
 *
 * @param options - Initialization options
 * @returns Promise that resolves when initialization is complete
 *
 * @example
 * ```typescript
 * // Full initialization with preloading
 * await initializePluginSystem({ preload: true });
 *
 * // Quick initialization without preloading
 * await initializePluginSystem({ preload: false });
 * ```
 */
export async function initializePluginSystem(
  options: { preload?: boolean } = {}
): Promise<void> {
  const { preload = true } = options;

  // Initialize builtin plugins
  initializeBuiltinPlugins();

  // Optionally preload common plugins
  if (preload) {
    await preloadCommonPlugins();
  }
}

/**
 * Check if the plugin system has been initialized
 */
export function isPluginSystemInitialized(): boolean {
  // Check if at least one builtin plugin is registered
  return pluginRegistry.hasPlugin("@ds/plugin-notebook");
}

/**
 * Get all registered builtin plugin IDs
 */
export function getRegisteredBuiltinPluginIds(): string[] {
  return BUILTIN_PLUGIN_MANIFESTS.filter((manifest) =>
    pluginRegistry.hasPlugin(manifest.id)
  ).map((manifest) => manifest.id);
}

/**
 * Reset the plugin system (for testing)
 *
 * This function unregisters all builtin plugins and resets the registry.
 * Should only be used in testing environments.
 */
export function resetPluginSystem(): void {
  console.log("[PluginInit] Resetting plugin system...");

  // Unregister all builtin plugins
  BUILTIN_PLUGIN_MANIFESTS.forEach((manifest) => {
    if (pluginRegistry.hasPlugin(manifest.id)) {
      pluginRegistry.unregister(manifest.id);
    }
  });

  // Clear builtin loader cache
  builtinPluginLoader.clearCache();
  commonPluginPreloadPromise = null;
  commonPluginPreloadScheduled = false;

  console.log("[PluginInit] Plugin system reset complete");
}
