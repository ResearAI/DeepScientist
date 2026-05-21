/**
 * Tabs Store
 *
 * Manages tab state for the workspace including:
 * - Open tabs and their order
 * - Active tab selection
 * - Tab dirty states
 * - Tab operations (open, close, reorder)
 *
 * Core concept: Tab = Plugin Instance
 * Each tab is defined by (pluginId, context) and rendered by the corresponding plugin.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import { nanoid } from "nanoid";
import { safeStableStringify, sanitizeJsonRecord } from "@/lib/safe-json";
import type { Tab, TabContext, OpenTabOptions } from "@/lib/types/tab";

/**
 * Tabs state interface
 */
export interface TabsState {
  /** All open tabs */
  tabs: Tab[];

  /** Currently active tab ID */
  activeTabId: string | null;
  hasHydrated: boolean;

  // Tab Actions
  setHasHydrated: (value: boolean) => void;
  openTab: (options: OpenTabOptions) => string;
  resetTabs: () => void;
  closeTab: (tabId: string) => void;
  closeAllTabs: () => void;
  closeOtherTabs: (tabId: string) => void;
  closeTabsToRight: (tabId: string) => void;
  closeDirtyTabs: () => string[]; // Returns IDs of dirty tabs that need confirmation
  setActiveTab: (tabId: string) => void;
  setTabDirty: (tabId: string, isDirty: boolean) => void;
  setTabPinned: (tabId: string, isPinned: boolean) => void;
  updateTab: (tabId: string, updates: Partial<Pick<Tab, "title" | "icon">>) => void;
  updateTabPlugin: (tabId: string, pluginId: string, context?: TabContext) => void;
  reorderTabs: (fromIndex: number, toIndex: number) => void;

  // Query methods
  findTabByContext: (context: TabContext) => Tab | undefined;
  getActiveTab: () => Tab | undefined;
  getDirtyTabs: () => Tab[];
}

/**
 * Check if two contexts are equivalent (same resource)
 */
function contextEquals(a: TabContext, b: TabContext): boolean {
  if (a.type !== b.type) return false;

  const latexA = latexContextIdentity(a);
  const latexB = latexContextIdentity(b);
  if (latexA && latexB) {
    return latexA === latexB;
  }

  // For file and notebook types, compare resourceId
  if (a.type === "file" || a.type === "notebook") {
    return a.resourceId === b.resourceId;
  }

  // For custom type, compare customData
  if (a.type === "custom") {
    return safeStableStringify(a.customData) === safeStableStringify(b.customData);
  }

  return false;
}

function customStringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function latexContextIdentity(context: TabContext): string | null {
  if (context.type !== "custom") return null;
  const customData = context.customData;
  if (!customData || typeof customData !== "object" || Array.isArray(customData)) return null;
  const record = customData as Record<string, unknown>;
  const hasLatexMarker = record.kind === "latex-workspace" || customStringValue(record.latexFolderId);
  if (!hasLatexMarker) return null;
  const projectId = customStringValue(record.projectId);
  const latexFolderId = customStringValue(record.latexFolderId) ?? customStringValue(context.resourceId);
  if (!projectId || !latexFolderId) return null;
  return [
    "latex-workspace",
    projectId,
    latexFolderId,
    Boolean(record.readOnly || record.readonly) ? "readonly" : "writable",
  ].join("::");
}

/**
 * Generate default title for a tab based on context
 */
function getDefaultTitle(context: TabContext): string {
  if (context.resourceName) {
    return context.resourceName;
  }
  if (context.type === "file") {
    return "Untitled File";
  }
  if (context.type === "notebook") {
    return "Untitled Notebook";
  }
  return "New Tab";
}

/**
 * Tabs store with persistence
 */
export const useTabsStore = create<TabsState>()(
  persist(
    (set, get) => ({
      // Initial state
      tabs: [],
      activeTabId: null,
      hasHydrated: false,

      setHasHydrated: (value: boolean) => {
        set({ hasHydrated: value });
      },

      // Reset all tabs (used when switching projects)
      resetTabs: () => {
        set({ tabs: [], activeTabId: null });
      },

      // Open a new tab or focus existing one with same context
      openTab: (options: OpenTabOptions): string => {
        const { pluginId, context, title, icon } = options;
        const state = get();

        // Check if a tab with the same context already exists
        const existingTab = state.tabs.find(
          (tab) => tab.pluginId === pluginId && contextEquals(tab.context, context)
        );

        if (existingTab) {
          // Focus the existing tab and update lastAccessedAt
          set({
            activeTabId: existingTab.id,
            tabs: state.tabs.map((tab) =>
              tab.id === existingTab.id
                ? { ...tab, lastAccessedAt: Date.now() }
                : tab
            ),
          });
          return existingTab.id;
        }

        // Create new tab
        const now = Date.now();
        const newTab: Tab = {
          id: nanoid(),
          pluginId,
          context,
          title: title || getDefaultTitle(context),
          icon,
          isDirty: false,
          isPinned: false,
          createdAt: now,
          lastAccessedAt: now,
        };

        set({
          tabs: [...state.tabs, newTab],
          activeTabId: newTab.id,
        });

        return newTab.id;
      },

      // Close a specific tab
      closeTab: (tabId: string) => {
        const state = get();
        const tabIndex = state.tabs.findIndex((t) => t.id === tabId);

        if (tabIndex === -1) return;

        const tab = state.tabs[tabIndex];

        // Don't close pinned tabs
        if (tab.isPinned) return;

        const newTabs = state.tabs.filter((t) => t.id !== tabId);

        // Determine new active tab
        let newActiveTabId = state.activeTabId;
        if (state.activeTabId === tabId) {
          if (newTabs.length === 0) {
            newActiveTabId = null;
          } else if (tabIndex >= newTabs.length) {
            // Was last tab, select previous
            newActiveTabId = newTabs[newTabs.length - 1].id;
          } else {
            // Select tab at same position
            newActiveTabId = newTabs[tabIndex].id;
          }
        }

        set({
          tabs: newTabs,
          activeTabId: newActiveTabId,
        });
      },

      // Close all tabs (except pinned)
      closeAllTabs: () => {
        const state = get();
        const pinnedTabs = state.tabs.filter((t) => t.isPinned);

        set({
          tabs: pinnedTabs,
          activeTabId: pinnedTabs.length > 0 ? pinnedTabs[0].id : null,
        });
      },

      // Close all tabs except the specified one (and pinned tabs)
      closeOtherTabs: (tabId: string) => {
        const state = get();
        const keptTabs = state.tabs.filter(
          (t) => t.id === tabId || t.isPinned
        );

        set({
          tabs: keptTabs,
          activeTabId: tabId,
        });
      },

      // Close tabs to the right of the specified tab (except pinned)
      closeTabsToRight: (tabId: string) => {
        const state = get();
        const tabIndex = state.tabs.findIndex((t) => t.id === tabId);

        if (tabIndex === -1) return;

        const keptTabs = state.tabs.filter(
          (t, index) => index <= tabIndex || t.isPinned
        );

        // If active tab was closed, switch to the specified tab
        let newActiveTabId = state.activeTabId;
        if (!keptTabs.find((t) => t.id === state.activeTabId)) {
          newActiveTabId = tabId;
        }

        set({
          tabs: keptTabs,
          activeTabId: newActiveTabId,
        });
      },

      // Get dirty tabs that need confirmation before closing
      closeDirtyTabs: (): string[] => {
        const state = get();
        return state.tabs.filter((t) => t.isDirty).map((t) => t.id);
      },

      // Set active tab
      setActiveTab: (tabId: string) => {
        const state = get();
        const tab = state.tabs.find((t) => t.id === tabId);

        if (!tab) return;

        set({
          activeTabId: tabId,
          tabs: state.tabs.map((t) =>
            t.id === tabId ? { ...t, lastAccessedAt: Date.now() } : t
          ),
        });
      },

      // Set tab dirty state
      setTabDirty: (tabId: string, isDirty: boolean) => {
        set((state) => ({
          tabs: state.tabs.map((t) =>
            t.id === tabId ? { ...t, isDirty } : t
          ),
        }));
      },

      // Set tab pinned state
      setTabPinned: (tabId: string, isPinned: boolean) => {
        set((state) => {
          const tabs = [...state.tabs];
          const tabIndex = tabs.findIndex((t) => t.id === tabId);

          if (tabIndex === -1) return state;

          const tab = { ...tabs[tabIndex], isPinned };

          // Move pinned tabs to the front
          tabs.splice(tabIndex, 1);
          if (isPinned) {
            // Find the last pinned tab index
            const lastPinnedIndex = tabs.findLastIndex((t) => t.isPinned);
            tabs.splice(lastPinnedIndex + 1, 0, tab);
          } else {
            // Keep at current position relative to unpinned tabs
            const unpinnedTabs = tabs.filter((t) => !t.isPinned);
            const pinnedCount = tabs.length - unpinnedTabs.length;
            tabs.splice(pinnedCount, 0, tab);
          }

          return { tabs };
        });
      },

      // Update tab properties
      updateTab: (tabId: string, updates: Partial<Pick<Tab, "title" | "icon">>) => {
        set((state) => ({
          tabs: state.tabs.map((t) =>
            t.id === tabId ? { ...t, ...updates } : t
          ),
        }));
      },

      updateTabPlugin: (tabId: string, pluginId: string, context?: TabContext) => {
        set((state) => ({
          tabs: state.tabs.map((t) =>
            t.id === tabId
              ? {
                  ...t,
                  pluginId,
                  context: context || t.context,
                  lastAccessedAt: Date.now(),
                }
              : t
          ),
        }));
      },

      // Reorder tabs via drag & drop
      reorderTabs: (fromIndex: number, toIndex: number) => {
        set((state) => {
          const tabs = [...state.tabs];
          const [removed] = tabs.splice(fromIndex, 1);
          tabs.splice(toIndex, 0, removed);
          return { tabs };
        });
      },

      // Find tab by context
      findTabByContext: (context: TabContext): Tab | undefined => {
        return get().tabs.find((tab) => contextEquals(tab.context, context));
      },

      // Get active tab
      getActiveTab: (): Tab | undefined => {
        const state = get();
        return state.tabs.find((t) => t.id === state.activeTabId);
      },

      // Get all dirty tabs
      getDirtyTabs: (): Tab[] => {
        return get().tabs.filter((t) => t.isDirty);
      },
    }),
    {
      name: "ds-tabs-state",
      // Persist tabs but clear dirty state on reload
      partialize: (state) => ({
        tabs: state.tabs.map((tab) => ({
          ...tab,
          context: {
            ...tab.context,
            customData:
              tab.context.customData && typeof tab.context.customData === "object"
                ? sanitizeJsonRecord(tab.context.customData)
                : tab.context.customData,
          },
          isDirty: false, // Clear dirty state on reload
        })),
        activeTabId: state.activeTabId,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
    }
  )
);

/**
 * Selector hooks for specific state slices
 */
export const useActiveTab = () =>
  useTabsStore((state) => state.tabs.find((t) => t.id === state.activeTabId));

export const useTabs = () => useTabsStore((state) => state.tabs);
export const useTabsHydrated = () => useTabsStore((state) => state.hasHydrated);

export const useTabActions = () =>
  useTabsStore((state) => ({
    openTab: state.openTab,
    closeTab: state.closeTab,
    closeAllTabs: state.closeAllTabs,
    closeOtherTabs: state.closeOtherTabs,
    setActiveTab: state.setActiveTab,
    setTabDirty: state.setTabDirty,
    setTabPinned: state.setTabPinned,
    updateTab: state.updateTab,
    updateTabPlugin: state.updateTabPlugin,
    reorderTabs: state.reorderTabs,
  }));
