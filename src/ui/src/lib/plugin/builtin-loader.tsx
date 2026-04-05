/**
 * Builtin Plugin Loader
 *
 * Manages loading and lifecycle of builtin plugins using React.lazy for code splitting.
 *
 * @module lib/plugin/builtin-loader
 */

import { lazy, type LazyExoticComponent, type ComponentType } from "react";
import type {
  UnifiedPluginManifest,
  PluginInstance,
  PluginContext,
} from "@/lib/types/plugin";
import type { PluginComponentProps } from "@/lib/types/tab";
import { wrapRecoverableImport } from "@/lib/utils/dynamic-import-recovery";

// ============================================================
// Types
// ============================================================

/**
 * Import function type for dynamic imports
 */
type ComponentImportFn = () => Promise<{
  default: ComponentType<PluginComponentProps>;
}>;

/**
 * Plugin module with optional lifecycle hooks
 */
interface PluginModule {
  default: ComponentType<PluginComponentProps>;
  activate?: (context: PluginContext) => void | Promise<void>;
  deactivate?: () => void | Promise<void>;
  [key: string]: unknown;
}

// ============================================================
// Builtin Plugin Component Registry
// ============================================================

/**
 * Registry of builtin plugin components
 *
 * Maps plugin IDs to their dynamic import functions.
 * Components are loaded lazily for code splitting.
 *
 * Note: These paths point to where plugin components will be implemented.
 * Initially they may not exist - placeholder components will be used.
 */
const BUILTIN_PLUGIN_IMPORTS: Record<string, ComponentImportFn> = {
  // ============================================================
  // Implemented Plugins
  // ============================================================

  // Code Viewer Plugin
  "@ds/plugin-code-viewer": () =>
    import("@/lib/plugins/code-viewer/CodeViewerPlugin").then((m) => ({
      default: m.default,
    })),

  // Code Editor Plugin (Monaco)
  "@ds/plugin-code-editor": () =>
    import("@/lib/plugins/code-editor/CodeEditorPlugin").then((m) => ({
      default: m.default,
    })),

  // Text Viewer Plugin
  "@ds/plugin-text-viewer": () =>
    import("@/lib/plugins/text-viewer/TextViewerPlugin").then((m) => ({
      default: m.default,
    })),

  // Markdown Viewer Plugin
  "@ds/plugin-markdown-viewer": () =>
    import("@/lib/plugins/markdown-viewer/MarkdownViewerPlugin").then((m) => ({
      default: m.default,
    })),

  // Image Viewer Plugin
  "@ds/plugin-image-viewer": () =>
    import("@/lib/plugins/image-viewer/ImageViewerPlugin").then((m) => ({
      default: m.default,
    })),

  // Document Viewer Plugin (Office documents)
  "@ds/plugin-doc-viewer": () =>
    import("@/lib/plugins/doc-viewer/DocViewerPlugin").then((m) => ({
      default: m.default,
    })),

  // PDF Viewer Plugin (Stage 06)
  "@ds/plugin-pdf-viewer": () =>
    import("@/lib/plugins/pdf-viewer/PdfViewerPlugin").then((m) => ({
      default: m.default,
    })),
  // PDF Markdown Plugin (MinerU)
  "@ds/plugin-pdf-markdown": () =>
    import("@/lib/plugins/pdf-markdown/PdfMarkdownPlugin").then((m) => ({
      default: m.default,
    })),

  // CLI Plugin
  "@ds/plugin-cli": () =>
    import("@/lib/plugins/cli/CliPlugin").then((m) => ({
      default: m.default,
    })),

  // Lab Plugin (Home)
  "@ds/plugin-lab": () =>
    import("@/lib/plugins/lab/LabPlugin").then((m) => ({
      default: m.default,
    })),

  // ============================================================
  // Notebook Plugin (Novel Integration)
  // ============================================================

  // Notebook plugin with Novel editor
  "@ds/plugin-notebook": () =>
    import("@/lib/plugins/notebook").then((m) => ({
      default: m.default,
    })),

  // ============================================================
  // LaTeX Plugin (Stage 11)
  // ============================================================

  "@ds/plugin-latex": () =>
    import("@/lib/plugins/latex/LatexPlugin").then((m) => ({
      default: m.default,
    })),

  "@ds/plugin-git-diff-viewer": () =>
    import("@/lib/plugins/git-diff-viewer/GitDiffViewerPlugin").then((m) => ({
      default: m.default,
    })),

  "@ds/plugin-git-commit-viewer": () =>
    import("@/lib/plugins/git-commit-viewer/GitCommitViewerPlugin").then((m) => ({
      default: m.default,
    })),

  // ============================================================
  // Placeholder Plugins - to be implemented
  // ============================================================

  "@ds/plugin-search": () =>
    import("@/lib/plugins/search/SearchPlugin").then((m) => ({
      default: m.default,
    })),

  "@ds/plugin-analysis": () =>
    import("@/lib/plugins/analysis/AnalysisPlugin").then((m) => ({
      default: m.default,
    })),

  "@ds/plugin-marketplace": () =>
    import("@/lib/plugins/marketplace/MarketplacePlugin").then((m) => ({
      default: m.default,
    })),
};

/**
 * Create a placeholder module for plugins not yet implemented
 */
function createPlaceholderModule(
  pluginName: string
): { default: ComponentType<PluginComponentProps> } {
  const PlaceholderComponent: ComponentType<PluginComponentProps> = ({
    context,
    tabId,
  }) => {
    return (
      <div className="flex items-center justify-center h-full bg-muted/30">
        <div className="text-center space-y-4 p-8">
          <div className="text-6xl opacity-20">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="64"
              height="64"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
              <path d="M18.375 2.625a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4Z" />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-semibold text-muted-foreground">
              {pluginName}
            </h3>
            <p className="text-sm text-muted-foreground/70 mt-1">
              Plugin coming soon
            </p>
          </div>
          {context.resourceName && (
            <div className="text-xs text-muted-foreground/50 font-mono bg-muted/50 rounded px-2 py-1">
              {context.resourceName}
            </div>
          )}
        </div>
      </div>
    );
  };

  PlaceholderComponent.displayName = `${pluginName}Placeholder`;

  return { default: PlaceholderComponent };
}

// ============================================================
// Builtin Plugin Loader
// ============================================================

/**
 * Builtin Plugin Loader
 *
 * Manages loading of builtin plugins using React.lazy for code splitting.
 * Provides lifecycle hook management and preloading capabilities.
 */
export class BuiltinPluginLoader {
  private getRecoverableImport(
    pluginId: string,
    importFn: ComponentImportFn
  ): ComponentImportFn {
    return wrapRecoverableImport(importFn, `builtin-plugin:${pluginId}`);
  }

  /**
   * Cache of lazy-loaded components
   */
  private lazyComponents = new Map<
    string,
    LazyExoticComponent<ComponentType<PluginComponentProps>>
  >();

  /**
   * Cache of preloaded modules
   */
  private preloadedModules = new Map<string, PluginModule>();

  /**
   * In-flight plugin module loads keyed by plugin ID.
   * This prevents duplicate work when preload and first-open race each other.
   */
  private loadingModules = new Map<string, Promise<PluginModule | null>>();

  /**
   * Get or create a lazy component for a plugin
   *
   * @param pluginId - Plugin ID
   * @returns Lazy component or null if not found
   */
  getLazyComponent(
    pluginId: string
  ): LazyExoticComponent<ComponentType<PluginComponentProps>> | null {
    // Check cache first
    const cached = this.lazyComponents.get(pluginId);
    if (cached) {
      return cached;
    }

    // Get import function
    const importFn = BUILTIN_PLUGIN_IMPORTS[pluginId];
    if (!importFn) {
      console.warn(
        `[BuiltinPluginLoader] No import function for plugin: ${pluginId}`
      );
      return null;
    }

    // Create lazy component
    const LazyComponent = lazy(this.getRecoverableImport(pluginId, importFn));
    this.lazyComponents.set(pluginId, LazyComponent);

    return LazyComponent;
  }

  /**
   * Load a plugin instance
   *
   * @param manifest - Plugin manifest
   * @param context - Plugin context
   * @returns Plugin instance
   */
  async load(
    manifest: UnifiedPluginManifest,
    context: PluginContext
  ): Promise<PluginInstance> {
    const importFn = BUILTIN_PLUGIN_IMPORTS[manifest.id];

    if (!importFn) {
      throw new Error(
        `[BuiltinPluginLoader] Builtin plugin not found: ${manifest.id}`
      );
    }

    // Get or create lazy component
    let LazyComponent = this.lazyComponents.get(manifest.id);
    if (!LazyComponent) {
      LazyComponent = lazy(this.getRecoverableImport(manifest.id, importFn));
      this.lazyComponents.set(manifest.id, LazyComponent);
    }

    // Load module for lifecycle hooks
    const pluginModule = await this.loadModule(manifest.id);

    // Call activation hook if exists
    if (manifest.lifecycle?.onActivate && pluginModule) {
      const activateFn = pluginModule[manifest.lifecycle.onActivate];
      if (typeof activateFn === "function") {
        await (activateFn as (context: PluginContext) => Promise<void>)(context);
      }
    }

    // Create instance
    const instanceId = `${manifest.id}:${context.resourceId || "default"}`;
    const instance: PluginInstance = {
      id: instanceId,
      pluginId: manifest.id,
      manifest,
      type: "builtin",
      state: "active",
      Component: LazyComponent as unknown as ComponentType<PluginComponentProps>,
      context,
    };

    return instance;
  }

  /**
   * Unload a plugin instance
   *
   * @param instance - Plugin instance to unload
   */
  async unload(instance: PluginInstance): Promise<void> {
    if (instance.type !== "builtin") {
      return;
    }

    // Call deactivation hook if exists
    if (instance.manifest.lifecycle?.onDeactivate) {
      const pluginModule = await this.loadModule(instance.pluginId);
      if (pluginModule) {
        const deactivateFn = pluginModule[instance.manifest.lifecycle.onDeactivate];
        if (typeof deactivateFn === "function") {
          await (deactivateFn as () => Promise<void>)();
        }
      }
    }
  }

  /**
   * Preload plugins for faster initial loading
   *
   * @param pluginIds - Array of plugin IDs to preload
   */
  async preload(pluginIds: string[]): Promise<void> {
    await Promise.all(
      pluginIds.map(async (pluginId) => {
        const importFn = BUILTIN_PLUGIN_IMPORTS[pluginId];
        if (!importFn) {
          return;
        }

        try {
          // Create lazy component if not exists
          if (!this.lazyComponents.has(pluginId)) {
            const LazyComponent = lazy(
              this.getRecoverableImport(pluginId, importFn)
            );
            this.lazyComponents.set(pluginId, LazyComponent);
          }

          // Preload module
          await this.loadModule(pluginId);
        } catch (error) {
          console.warn(
            `[BuiltinPluginLoader] Failed to preload plugin: ${pluginId}`,
            error
          );
        }
      })
    );
  }

  /**
   * Load and cache a plugin module
   */
  private async loadModule(pluginId: string): Promise<PluginModule | null> {
    // Check cache
    const cached = this.preloadedModules.get(pluginId);
    if (cached) {
      return cached;
    }

    const inFlight = this.loadingModules.get(pluginId);
    if (inFlight) {
      return inFlight;
    }

    // Load module
    const importFn = BUILTIN_PLUGIN_IMPORTS[pluginId];
    if (!importFn) {
      return null;
    }

    const loadPromise = (async () => {
      try {
        const pluginModule = (await this.getRecoverableImport(
          pluginId,
          importFn
        )()) as PluginModule;
        this.preloadedModules.set(pluginId, pluginModule);
        return pluginModule;
      } catch (error) {
        console.warn(
          `[BuiltinPluginLoader] Failed to load module: ${pluginId}`,
          error
        );
        return null;
      } finally {
        this.loadingModules.delete(pluginId);
      }
    })();

    this.loadingModules.set(pluginId, loadPromise);
    return loadPromise;
  }

  /**
   * Check if a plugin is a builtin plugin
   */
  isBuiltinPlugin(pluginId: string): boolean {
    return pluginId in BUILTIN_PLUGIN_IMPORTS;
  }

  /**
   * Get all builtin plugin IDs
   */
  getBuiltinPluginIds(): string[] {
    return Object.keys(BUILTIN_PLUGIN_IMPORTS);
  }

  /**
   * Clear all caches
   */
  clearCache(): void {
    this.lazyComponents.clear();
    this.preloadedModules.clear();
    this.loadingModules.clear();
  }
}

/**
 * Global builtin plugin loader singleton
 */
export const builtinPluginLoader = new BuiltinPluginLoader();
