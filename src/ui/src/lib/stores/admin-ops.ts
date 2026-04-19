// TODO(upstream ea21104): the real admin-ops store (dock/repair/session surfaces)
// was never committed upstream. This stub provides a no-op shape so SettingsPage
// and anything else that imports `useAdminOpsStore` can compile and run.
// Replace with the real store once it lands.
import { create } from 'zustand'

interface ActiveRepair {
  repair_id: string
}

interface AdminOpsState {
  dockOpen: boolean
  activeRepair: ActiveRepair | null
  closeDock: () => void
  startFreshSession: (path: string) => void
  resetContext: (path: string) => void
}

export const useAdminOpsStore = create<AdminOpsState>(() => ({
  dockOpen: false,
  activeRepair: null,
  closeDock: () => {},
  startFreshSession: () => {},
  resetContext: () => {},
}))
