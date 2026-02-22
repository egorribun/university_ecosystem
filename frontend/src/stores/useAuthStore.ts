import { create } from "zustand"
import type { PendingMfaState, UserState } from "@/types/Auth"

// Ensure we have access to the constants and functions we need,
// or we can just initialize empty and let useProfileSync set the initial state.
// It's safer to let useProfileSync handle the complex cache hydration logic.
// We'll just provide the store.

interface AuthState {
  user: UserState
  loading: boolean
  pendingMfa: PendingMfaState | null
  authOperation: boolean

  setUser: (userOrUpdater: UserState | ((prev: UserState) => UserState)) => void
  setLoading: (loading: boolean) => void
  setPendingMfa: (pendingMfa: PendingMfaState | null) => void
  setAuthOperation: (authOperation: boolean) => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: true, // Optimistically true until useProfileSync mounts
  pendingMfa: null,
  authOperation: false,

  setUser: (userOrUpdater) =>
    set((state) => ({
      user: typeof userOrUpdater === "function" ? userOrUpdater(state.user) : userOrUpdater,
    })),
  setLoading: (loading) => set({ loading }),
  setPendingMfa: (pendingMfa) => set({ pendingMfa }),
  setAuthOperation: (authOperation) => set({ authOperation }),
}))
