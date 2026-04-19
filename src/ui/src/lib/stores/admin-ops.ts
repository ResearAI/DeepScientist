import { create } from 'zustand'

import type { AdminRepair } from '@/lib/types/admin'

export type AdminOpsContext = {
  sourcePage: string
  scope?: string
  targets?: Record<string, unknown>
  selectedPaths?: string[]
}

type AdminOpsState = {
  dockOpen: boolean
  activeRepair: AdminRepair | null
  context: AdminOpsContext
  setDockOpen: (value: boolean) => void
  setActiveRepair: (repair: AdminRepair | null) => void
  openRepair: (repair: AdminRepair) => void
  startFreshSession: (sourcePage: string) => void
  closeDock: () => void
  clearActiveRepair: () => void
  clearContext: (sourcePage?: string) => void
  setContext: (context: Partial<AdminOpsContext>) => void
  resetContext: (sourcePage: string) => void
}

export const useAdminOpsStore = create<AdminOpsState>((set) => ({
  dockOpen: false,
  activeRepair: null,
  context: {
    sourcePage: '/settings',
    scope: 'system',
    targets: {},
    selectedPaths: [],
  },
  setDockOpen: (value) => set({ dockOpen: value }),
  setActiveRepair: (repair) =>
    set((state) => ({
      activeRepair: repair,
      dockOpen: repair ? true : state.dockOpen,
    })),
  openRepair: (repair) =>
    set({
      dockOpen: true,
      activeRepair: repair,
      context: {
        sourcePage: String(repair.source_page || '/settings').trim() || '/settings',
        scope: String(repair.scope || 'system').trim() || 'system',
        targets: repair.targets || {},
        selectedPaths: repair.selected_paths || [],
      },
    }),
  startFreshSession: (sourcePage) =>
    set({
      dockOpen: true,
      activeRepair: null,
      context: {
        sourcePage,
        scope: 'system',
        targets: {},
        selectedPaths: [],
      },
    }),
  closeDock: () =>
    set((state) => ({
      dockOpen: false,
      activeRepair: null,
      context: {
        sourcePage: state.context.sourcePage,
        scope: 'system',
        targets: {},
        selectedPaths: [],
      },
    })),
  clearActiveRepair: () =>
    set((state) => ({
      activeRepair: null,
      dockOpen: state.dockOpen,
    })),
  clearContext: (sourcePage) =>
    set((state) => ({
      activeRepair: null,
      context: {
        sourcePage: String(sourcePage || state.context.sourcePage || '/settings').trim() || '/settings',
        scope: 'system',
        targets: {},
        selectedPaths: [],
      },
    })),
  setContext: (context) =>
    set((state) => ({
      context: {
        ...state.context,
        ...context,
      },
    })),
  resetContext: (sourcePage) =>
    set({
      context: {
        sourcePage,
        scope: 'system',
        targets: {},
        selectedPaths: [],
      },
    }),
}))
