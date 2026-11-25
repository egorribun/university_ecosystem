import { create } from "zustand"

type LogoutNotice = "server-unconfirmed"

type LogoutNoticeState = {
  notice: LogoutNotice | null
  /** Sign-out removed offline changes that had not reached the server. */
  offlineChangesDiscarded: boolean
  markUnconfirmed: () => void
  clear: () => void
  markOfflineChangesDiscarded: () => void
  clearOfflineChangesDiscarded: () => void
}

/**
 * Volatile, identity-free feedback for a logout whose server outcome is unknown.
 * This store is intentionally not persisted and contains no response or account data.
 */
export const useLogoutNoticeStore = create<LogoutNoticeState>((set) => ({
  notice: null,
  offlineChangesDiscarded: false,
  markUnconfirmed: () => set({ notice: "server-unconfirmed" }),
  clear: () => set({ notice: null }),
  markOfflineChangesDiscarded: () => set({ offlineChangesDiscarded: true }),
  clearOfflineChangesDiscarded: () => set({ offlineChangesDiscarded: false }),
}))

export const markLogoutUnconfirmed = () => useLogoutNoticeStore.getState().markUnconfirmed()

export const clearLogoutNotice = () => useLogoutNoticeStore.getState().clear()

export const markOfflineChangesDiscarded = () =>
  useLogoutNoticeStore.getState().markOfflineChangesDiscarded()
