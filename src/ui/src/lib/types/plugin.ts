/**
 * Plugin System Type Definitions
 *
 * Types for the plugin system that enables "Everything is a Plugin" architecture.
 * Plugins render content in tabs and can provide tools for the AI agent.
 *
 * @module types/plugin
 */

import type { ComponentType } from "react";
import type { TabContext, PluginComponentProps as TabPluginComponentProps } from "./tab";

// Re-export PluginComponentProps for convenience
export type { PluginComponentProps } from "./tab";

// ============================================================
// Basic Types
// ============================================================

/**
 * Plugin type classification
 */
export type PluginType = "builtin" | "external";

/**
 * Plugin render mode for frontend
 */
export type PluginRenderMode = "react" | "iframe";

/**
 * File association for plugins
 * Defines which files a plugin can handle
 */
export interface FileAssociation {
  /** File extensions this plugin can handle (e.g., [".pdf", ".PDF"]) */
  extensions: string[];

  /** MIME types this plugin can handle */
  mimeTypes?: string[];

  /** Priority for conflict resolution (higher = preferred, 100+ for builtin) */
  priority: number;

  /** Whether this plugin can edit the file (not just view) */
  isEditor?: boolean;
}

// ============================================================
// Sandbox Configuration (for external plugins)
// ============================================================

/**
 * Sandbox feature types for iframe
 */
export type SandboxFeature =
  | "allow-scripts"
  | "allow-same-origin"
  | "allow-forms"
  | "allow-popups"
  | "allow-modals"
  | "allow-downloads";

/**
 * Sandbox configuration for iframe plugins
 */
export interface SandboxConfig {
  /** Allowed sandbox features */
  allowedFeatures?: SandboxFeature[];

  /** Allow network requests */
  allowNetwork?: boolean;

  /** Allowed origins for network requests */
  allowedOrigins?: string[];
}

// ============================================================
// Frontend Configuration
// ============================================================

/**
 * Frontend plugin configuration
 */
export interface PluginFrontendConfig {
  /** Entry point (component path or iframe URL) */
  entry: string;

  /** How the plugin should be rendered */
  renderMode: PluginRenderMode;

  /** File types this plugin can open */
  fileAssociations?: FileAssociation[];

  /** Sandbox configuration (for iframe mode) */
  sandbox?: SandboxConfig;

  /** Style resources (for external plugins) */
  styles?: string[];

  /** Whether the plugin supports multiple instances */
  multiInstance?: boolean;
}

// ============================================================
// Backend Configuration
// ============================================================

/**
 * Backend plugin configuration
 */
export interface PluginBackendConfig {
  /** Python module entry point */
  entry: string;

  /** AI tools provided by this plugin */
  tools?: string[];

  /** Custom API routes */
  routes?: Record<string, string>;

  /** Python dependencies */
  pythonDependencies?: string[];

  /** Runtime configuration */
  runtime?: {
    timeout?: number;
    maxConcurrency?: number;
  };
}

// ============================================================
// Permission Configuration
// ============================================================

/**
 * Frontend permission types
 */
export type FrontendPermission =
  // File system
  | "file:read"
  | "file:write"
  | "file:delete"
  | "file:upload"
  // Notebook
  | "notebook:read"
  | "notebook:write"
  // Annotation
  | "annotation:read"
  | "annotation:write"
  // AI
  | "ai:chat"
  | "ai:invoke-tool"
  // Project
  | "project:read"
  | "project:write"
  // User
  | "user:read"
  // System
  | "clipboard"
  | "notification"
  | "storage"
  | "network";

/**
 * Backend permission types
 */
export type BackendPermission =
  // AI related
  | "ai:tool"
  | "ai:context"
  // API related
  | "api:route"
  // Database
  | "database:read"
  | "database:write"
  // File system
  | "file:read"
  | "file:write"
  // Network
  | "network:outbound"
  // System (dangerous)
  | "system:exec";

/**
 * Permission configuration
 */
export interface PermissionConfig {
  /** Frontend permissions */
  frontend?: FrontendPermission[];

  /** Backend permissions */
  backend?: BackendPermission[];
}

// ============================================================
// UI Contributions (Contributes)
// ============================================================

/**
 * Sidebar menu contribution
 */
export interface SidebarContribution {
  /** Entry ID (unique within plugin) */
  id: string;

  /** Display title */
  title: string;

  /** Icon name (Lucide icon) */
  icon: string;

  /** Sort order (lower = higher priority) */
  order?: number;

  /** Command to execute on click */
  command?: string;

  /** Display condition expression */
  when?: string;
}

/**
 * Tab title configuration
 */
export interface TabTitleConfig {
  /** Static title */
  static?: string;

  /** Dynamic title rule: 'resourceName' | 'custom' */
  dynamic?: "resourceName" | "custom";
}

/**
 * Toolbar button contribution
 */
export interface ToolbarContribution {
  id: string;
  title: string;
  icon: string;
  command: string;
  position?: "left" | "right";
  when?: string;
}

/**
 * Slash command contribution (for Notebook editor)
 */
export interface SlashCommandContribution {
  /** Command name (user input) */
  name: string;

  /** Command description */
  description: string;

  /** Internal command to execute */
  command: string;

  /** Icon name */
  icon?: string;

  /** Command group */
  group?: string;

  /** Search keywords */
  keywords?: string[];
}

/**
 * Settings page contribution
 */
export interface SettingsContribution {
  id: string;
  title: string;
  component?: string;
  autoGenerate?: boolean;
}

/**
 * Context menu contribution
 */
export interface ContextMenuContribution {
  id: string;
  title: string;
  command: string;
  context: "fileTree" | "tab" | "editor" | "annotation";
  when?: string;
  group?: string;
  order?: number;
}

/**
 * Keybinding contribution
 */
export interface KeybindingContribution {
  command: string;
  key: string;
  mac?: string;
  when?: string;
}

/**
 * Status bar item contribution
 */
export interface StatusBarContribution {
  id: string;
  text: string;
  icon?: string;
  command?: string;
  position?: "left" | "right";
  priority?: number;
  when?: string;
}

/**
 * UI contributions configuration
 */
export interface ContributesConfig {
  /** Sidebar menu entries */
  sidebarMenus?: SidebarContribution[];

  /** Tab icon (when plugin is shown in a tab) */
  tabIcon?: string;

  /** Tab title configuration */
  tabTitle?: string | TabTitleConfig;

  /** Toolbar buttons */
  toolbar?: ToolbarContribution[];

  /** Slash commands for Notebook editor */
  slashCommands?: SlashCommandContribution[];

  /** Settings pages */
  settings?: SettingsContribution[];

  /** Context menu items */
  contextMenus?: ContextMenuContribution[];

  /** Keyboard shortcuts */
  keybindings?: KeybindingContribution[];

  /** Status bar items */
  statusBarItems?: StatusBarContribution[];
}

// ============================================================
// Lifecycle Configuration
// ============================================================

/**
 * Plugin lifecycle configuration
 */
export interface LifecycleConfig {
  /**
   * Activation events - when to load the plugin
   * - '*': Always load
   * - 'onProject': Load when entering a project
   * - 'onFile:{extension}': Load when opening a specific file type
   * - 'onCommand:{commandId}': Load when executing a command
   * - 'onView:{viewId}': Load when showing a view
   */
  activationEvents?: string[];

  /** Frontend activation hook function name */
  onActivate?: string;

  /** Frontend deactivation hook function name */
  onDeactivate?: string;

  /** Backend activation hook function name */
  onBackendActivate?: string;

  /** Backend deactivation hook function name */
  onBackendDeactivate?: string;
}

// ============================================================
// Unified Plugin Manifest
// ============================================================

/**
 * Author information
 */
export interface PluginAuthor {
  name: string;
  email?: string;
  url?: string;
}

/**
 * Repository information
 */
export interface PluginRepository {
  type: "git" | "svn";
  url: string;
}

/**
 * Plugin signature for integrity verification
 */
export interface PluginSignature {
  algorithm: "RSA-PSS" | "ECDSA";
  value: string;
  publicKey?: string;
}

/**
 * Plugin checksum for file integrity
 */
export interface PluginChecksum {
  algorithm: "SHA-256" | "SHA-512";
  files: Record<string, string>;
}

/**
 * Unified Plugin Manifest
 *
 * Complete plugin definition including both frontend and backend parts.
 * One manifest defines the full capabilities of a plugin.
 */
export interface UnifiedPluginManifest {
  // ============================================================
  // Basic Information
  // ============================================================

  /**
   * Unique plugin identifier
   * - Builtin: @ds/plugin-{name}
   * - External: {org}/{name} or {reverse-domain}.{name}
   * @example '@ds/plugin-pdf-viewer', 'com.example.my-plugin'
   */
  id: string;

  /** Human-readable plugin name */
  name: string;

  /** Plugin version (semver) */
  version: string;

  /** Plugin description */
  description?: string;

  /** Plugin author */
  author?: string | PluginAuthor;

  /** Plugin homepage URL */
  homepage?: string;

  /** Bug report URL */
  bugs?: string;

  /** Code repository */
  repository?: string | PluginRepository;

  /** License identifier */
  license?: string;

  /** Plugin signature (for integrity verification) */
  signature?: PluginSignature;

  /** File checksums (for integrity verification) */
  checksum?: PluginChecksum;

  /** Search keywords */
  keywords?: string[];

  /** Plugin icon (lucide icon name or URL) */
  icon?: string;

  // ============================================================
  // Type
  // ============================================================

  /**
   * Plugin type
   * - builtin: Built-in plugin, shipped with the app, fully trusted
   * - external: External plugin, requires sandbox isolation
   */
  type: PluginType;

  // ============================================================
  // Configuration
  // ============================================================

  /** Frontend configuration (optional for backend-only plugins) */
  frontend?: PluginFrontendConfig;

  /** Backend configuration (optional for frontend-only plugins) */
  backend?: PluginBackendConfig;

  /** Permission declaration */
  permissions?: PermissionConfig;

  /** UI contributions */
  contributes?: ContributesConfig;

  /** Plugin configuration JSON Schema */
  configSchema?: Record<string, unknown>;

  /** Default configuration values */
  defaultConfig?: Record<string, unknown>;

  /** Lifecycle hooks */
  lifecycle?: LifecycleConfig;

  // ============================================================
  // Dependencies
  // ============================================================

  /** Plugin dependencies (pluginId -> version range) */
  dependencies?: Record<string, string>;

  /** Minimum DeepScientist version requirement */
  engines?: {
    deepscientist: string;
  };
}

// ============================================================
// Plugin Instance Types
// ============================================================

/**
 * Plugin instance state
 */
export type PluginInstanceState =
  | "unloaded"
  | "loading"
  | "initializing"
  | "active"
  | "error"
  | "destroying";

/**
 * Plugin context for plugin instances
 */
export interface PluginContext {
  /** Context type */
  type: "file" | "notebook" | "custom";

  /** Resource ID (file ID, Notebook ID, etc.) */
  resourceId?: string;

  /** Resource path */
  resourcePath?: string;

  /** Resource name */
  resourceName?: string;

  /** MIME type */
  mimeType?: string;

  /** Custom data */
  customData?: Record<string, unknown>;
}

/**
 * Plugin instance represents a loaded plugin
 */
export interface PluginInstance {
  /** Instance ID (pluginId:resourceId) */
  id: string;

  /** Plugin ID */
  pluginId: string;

  /** Plugin manifest */
  manifest: UnifiedPluginManifest;

  /** Instance type */
  type: PluginType;

  /** Current state */
  state: PluginInstanceState;

  /** React component (for builtin plugins) */
  Component?: ComponentType<TabPluginComponentProps>;

  /** iframe element (for external plugins) */
  iframe?: HTMLIFrameElement;

  /** Plugin context */
  context: PluginContext;

  /** Session token (for external plugins) */
  sessionToken?: string;
}

// ============================================================
// Plugin Registry Interface (Re-export for compatibility)
// ============================================================

/**
 * Plugin Registry Query Interface
 * Extended interface for querying and managing the plugin registry
 */
export interface IPluginRegistry {
  /** Register a plugin */
  register(manifest: UnifiedPluginManifest, component?: ComponentType<TabPluginComponentProps>): void;

  /** Unregister a plugin */
  unregister(pluginId: string): void;

  /** Get plugin by ID */
  getPlugin(pluginId: string): UnifiedPluginManifest | undefined;

  /** Check if plugin is registered */
  hasPlugin(pluginId: string): boolean;

  /** Get all registered plugins */
  getAllPlugins(): UnifiedPluginManifest[];

  /** Find plugin that can handle a file */
  findPluginForFile(fileName: string, mimeType?: string): UnifiedPluginManifest | undefined;

  /** Find all plugins that can handle a file */
  findAllPluginsForFile(fileName: string, mimeType?: string): UnifiedPluginManifest[];

  /** Get React component for a builtin plugin */
  getPluginComponent(pluginId: string): ComponentType<TabPluginComponentProps> | null;

  /** Get all sidebar contributions */
  getSidebarContributions(): Array<{ pluginId: string; contribution: SidebarContribution }>;

  /** Get all slash command contributions */
  getSlashCommandContributions(): Array<{ pluginId: string; contribution: SlashCommandContribution }>;

  /** Get all status bar contributions */
  getStatusBarContributions(): Array<{ pluginId: string; contribution: StatusBarContribution }>;
}

/**
 * Plugin Renderer Props
 * Props for the PluginRenderer component that renders plugin content
 */
export interface PluginRendererProps {
  /** Plugin ID to render */
  pluginId: string;

  /** Context data for the plugin */
  context: TabContext;

  /** Tab ID */
  tabId: string;

  /** Project ID */
  projectId?: string;
}

// ============================================================
// Built-in Plugin Constants
// ============================================================

/**
 * Built-in plugin IDs
 */
export const BUILTIN_PLUGINS = {
  LAB: "@ds/plugin-lab",
  GIT_DIFF_VIEWER: "@ds/plugin-git-diff-viewer",
  GIT_COMMIT_VIEWER: "@ds/plugin-git-commit-viewer",
  PDF_VIEWER: "@ds/plugin-pdf-viewer",
  PDF_MARKDOWN: "@ds/plugin-pdf-markdown",
  NOTEBOOK: "@ds/plugin-notebook",
  LATEX: "@ds/plugin-latex",
  CODE_EDITOR: "@ds/plugin-code-editor",
  CODE_VIEWER: "@ds/plugin-code-viewer",
  IMAGE_VIEWER: "@ds/plugin-image-viewer",
  TEXT_VIEWER: "@ds/plugin-text-viewer",
  MARKDOWN_VIEWER: "@ds/plugin-markdown-viewer",
  SETTINGS: "@ds/plugin-settings",
  SEARCH: "@ds/plugin-search",
  CLI: "@ds/plugin-cli",
} as const;

/**
 * Built-in plugin ID type
 */
export type BuiltinPluginId = (typeof BUILTIN_PLUGINS)[keyof typeof BUILTIN_PLUGINS];

/**
 * Default plugin mappings for common MIME types
 */
export const DEFAULT_MIME_PLUGINS: Record<string, string> = {
  // PDF
  "application/pdf": BUILTIN_PLUGINS.PDF_VIEWER,

  // Markdown / Notebook
  "text/markdown": BUILTIN_PLUGINS.NOTEBOOK,
  "application/x-ipynb+json": BUILTIN_PLUGINS.NOTEBOOK,
  "application/x-blocksuite-notebook": BUILTIN_PLUGINS.NOTEBOOK,

  // Text
  "text/plain": BUILTIN_PLUGINS.CODE_EDITOR,
  "text/x-tex": BUILTIN_PLUGINS.CODE_EDITOR,
  "application/x-tex": BUILTIN_PLUGINS.CODE_EDITOR,
  "text/x-bibtex": BUILTIN_PLUGINS.CODE_EDITOR,
  "application/x-bibtex": BUILTIN_PLUGINS.CODE_EDITOR,

  // Code
  "text/x-python": BUILTIN_PLUGINS.CODE_EDITOR,
  "application/javascript": BUILTIN_PLUGINS.CODE_EDITOR,
  "application/typescript": BUILTIN_PLUGINS.CODE_EDITOR,
  "text/javascript": BUILTIN_PLUGINS.CODE_EDITOR,
  "text/typescript": BUILTIN_PLUGINS.CODE_EDITOR,
  "application/json": BUILTIN_PLUGINS.CODE_EDITOR,
  "text/html": BUILTIN_PLUGINS.CODE_EDITOR,
  "text/css": BUILTIN_PLUGINS.CODE_EDITOR,

  // Images
  "image/png": BUILTIN_PLUGINS.IMAGE_VIEWER,
  "image/jpeg": BUILTIN_PLUGINS.IMAGE_VIEWER,
  "image/gif": BUILTIN_PLUGINS.IMAGE_VIEWER,
  "image/webp": BUILTIN_PLUGINS.IMAGE_VIEWER,
  "image/svg+xml": BUILTIN_PLUGINS.IMAGE_VIEWER,
};

/**
 * Default plugin mappings for file extensions
 */
export const DEFAULT_EXTENSION_PLUGINS: Record<string, string> = {
  // PDF
  ".pdf": BUILTIN_PLUGINS.PDF_VIEWER,

  // Notebook / Markdown
  ".md": BUILTIN_PLUGINS.NOTEBOOK,
  ".markdown": BUILTIN_PLUGINS.NOTEBOOK,
  ".ipynb": BUILTIN_PLUGINS.NOTEBOOK,
  ".dsnb": BUILTIN_PLUGINS.NOTEBOOK,
  ".notebook": BUILTIN_PLUGINS.NOTEBOOK,
  ".ds": BUILTIN_PLUGINS.NOTEBOOK,

  // Code
  ".py": BUILTIN_PLUGINS.CODE_EDITOR,
  ".pyw": BUILTIN_PLUGINS.CODE_EDITOR,
  ".pyi": BUILTIN_PLUGINS.CODE_EDITOR,
  ".js": BUILTIN_PLUGINS.CODE_EDITOR,
  ".jsx": BUILTIN_PLUGINS.CODE_EDITOR,
  ".mjs": BUILTIN_PLUGINS.CODE_EDITOR,
  ".ts": BUILTIN_PLUGINS.CODE_EDITOR,
  ".tsx": BUILTIN_PLUGINS.CODE_EDITOR,
  ".mts": BUILTIN_PLUGINS.CODE_EDITOR,
  ".json": BUILTIN_PLUGINS.CODE_EDITOR,
  ".jsonc": BUILTIN_PLUGINS.CODE_EDITOR,
  ".json5": BUILTIN_PLUGINS.CODE_EDITOR,
  ".html": BUILTIN_PLUGINS.CODE_EDITOR,
  ".htm": BUILTIN_PLUGINS.CODE_EDITOR,
  ".css": BUILTIN_PLUGINS.CODE_EDITOR,
  ".scss": BUILTIN_PLUGINS.CODE_EDITOR,
  ".sass": BUILTIN_PLUGINS.CODE_EDITOR,
  ".less": BUILTIN_PLUGINS.CODE_EDITOR,
  ".vue": BUILTIN_PLUGINS.CODE_EDITOR,
  ".svelte": BUILTIN_PLUGINS.CODE_EDITOR,
  ".yaml": BUILTIN_PLUGINS.CODE_EDITOR,
  ".yml": BUILTIN_PLUGINS.CODE_EDITOR,
  ".toml": BUILTIN_PLUGINS.CODE_EDITOR,
  ".ini": BUILTIN_PLUGINS.CODE_EDITOR,
  ".cfg": BUILTIN_PLUGINS.CODE_EDITOR,
  ".conf": BUILTIN_PLUGINS.CODE_EDITOR,
  ".xml": BUILTIN_PLUGINS.CODE_EDITOR,
  ".xsl": BUILTIN_PLUGINS.CODE_EDITOR,
  ".xslt": BUILTIN_PLUGINS.CODE_EDITOR,
  ".sh": BUILTIN_PLUGINS.CODE_EDITOR,
  ".bash": BUILTIN_PLUGINS.CODE_EDITOR,
  ".zsh": BUILTIN_PLUGINS.CODE_EDITOR,
  ".fish": BUILTIN_PLUGINS.CODE_EDITOR,
  ".ps1": BUILTIN_PLUGINS.CODE_EDITOR,
  ".sql": BUILTIN_PLUGINS.CODE_EDITOR,
  ".graphql": BUILTIN_PLUGINS.CODE_EDITOR,
  ".java": BUILTIN_PLUGINS.CODE_EDITOR,
  ".c": BUILTIN_PLUGINS.CODE_EDITOR,
  ".cc": BUILTIN_PLUGINS.CODE_EDITOR,
  ".cpp": BUILTIN_PLUGINS.CODE_EDITOR,
  ".cxx": BUILTIN_PLUGINS.CODE_EDITOR,
  ".h": BUILTIN_PLUGINS.CODE_EDITOR,
  ".hpp": BUILTIN_PLUGINS.CODE_EDITOR,
  ".hxx": BUILTIN_PLUGINS.CODE_EDITOR,
  ".cs": BUILTIN_PLUGINS.CODE_EDITOR,
  ".go": BUILTIN_PLUGINS.CODE_EDITOR,
  ".rs": BUILTIN_PLUGINS.CODE_EDITOR,
  ".rb": BUILTIN_PLUGINS.CODE_EDITOR,
  ".php": BUILTIN_PLUGINS.CODE_EDITOR,
  ".swift": BUILTIN_PLUGINS.CODE_EDITOR,
  ".kt": BUILTIN_PLUGINS.CODE_EDITOR,
  ".kts": BUILTIN_PLUGINS.CODE_EDITOR,
  ".scala": BUILTIN_PLUGINS.CODE_EDITOR,
  ".r": BUILTIN_PLUGINS.CODE_EDITOR,
  ".m": BUILTIN_PLUGINS.CODE_EDITOR,
  ".mm": BUILTIN_PLUGINS.CODE_EDITOR,

  // Text
  ".txt": BUILTIN_PLUGINS.CODE_EDITOR,
  ".text": BUILTIN_PLUGINS.CODE_EDITOR,
  ".log": BUILTIN_PLUGINS.CODE_EDITOR,
  ".readme": BUILTIN_PLUGINS.CODE_EDITOR,
  ".csv": BUILTIN_PLUGINS.CODE_EDITOR,
  ".env": BUILTIN_PLUGINS.CODE_EDITOR,
  ".tex": BUILTIN_PLUGINS.CODE_EDITOR,
  ".bib": BUILTIN_PLUGINS.CODE_EDITOR,

  // Images
  ".png": BUILTIN_PLUGINS.IMAGE_VIEWER,
  ".jpg": BUILTIN_PLUGINS.IMAGE_VIEWER,
  ".jpeg": BUILTIN_PLUGINS.IMAGE_VIEWER,
  ".gif": BUILTIN_PLUGINS.IMAGE_VIEWER,
  ".webp": BUILTIN_PLUGINS.IMAGE_VIEWER,
  ".svg": BUILTIN_PLUGINS.IMAGE_VIEWER,
};

// ============================================================
// Utility Functions
// ============================================================

/**
 * Get file extension from filename (lowercase, with dot)
 */
export function getFileExtension(fileName: string): string | undefined {
  const lastDot = fileName.lastIndexOf(".");
  if (lastDot < 0) return undefined;
  return fileName.slice(lastDot).toLowerCase();
}

/**
 * Get plugin ID from file extension
 */
export function getPluginIdFromExtension(fileName: string): string | undefined {
  const ext = getFileExtension(fileName);
  return ext ? DEFAULT_EXTENSION_PLUGINS[ext] : undefined;
}

/**
 * Get plugin ID from MIME type
 */
export function getPluginIdFromMimeType(mimeType: string): string | undefined {
  return DEFAULT_MIME_PLUGINS[mimeType];
}
