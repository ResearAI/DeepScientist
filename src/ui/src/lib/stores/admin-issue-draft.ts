import { create } from 'zustand'

import type { AdminIssueDraftPayload } from '@/lib/types/admin'

export type AdminIssueDraftState = {
  draft: AdminIssueDraftPayload | null
  setDraft: (draft: AdminIssueDraftPayload | null) => void
  updateDraft: (updates: Partial<AdminIssueDraftPayload>) => void
  clearDraft: () => void
}

export const useAdminIssueDraftStore = create<AdminIssueDraftState>((set) => ({
  draft: null,
  setDraft: (draft) => set({ draft }),
  updateDraft: (updates) =>
    set((state) => ({
      draft: state.draft ? { ...state.draft, ...updates } : state.draft,
    })),
  clearDraft: () => set({ draft: null }),
}))
