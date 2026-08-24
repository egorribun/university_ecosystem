import { create } from "zustand"
import { useShallow } from "zustand/react/shallow"
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

// PERF-01 (audit 2026-03): Strict selectors to prevent entire-tree re-renders
// when authOperation or pendingMfa flash during background state syncs.
export const useAuthUser = () => useAuthStore((state) => state.user)
export const useAuthLoading = () => useAuthStore((state) => state.loading)
export const useAuthPendingMfa = () => useAuthStore((state) => state.pendingMfa)
export const useAuthOperation = () => useAuthStore((state) => state.authOperation)

const authActionsSelector = (state: AuthState) => ({
  setUser: state.setUser,
  setLoading: state.setLoading,
  setPendingMfa: state.setPendingMfa,
  setAuthOperation: state.setAuthOperation,
})

export const useAuthActions = () => useAuthStore(useShallow(authActionsSelector))
