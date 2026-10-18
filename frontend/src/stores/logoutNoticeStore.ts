import { create } from "zustand"

type LogoutNotice = "server-unconfirmed"

type LogoutNoticeState = {
  notice: LogoutNotice | null
  markUnconfirmed: () => void
  clear: () => void
}

/**
 * Volatile, identity-free feedback for a logout whose server outcome is unknown.
 * This store is intentionally not persisted and contains no response or account data.
 */
export const useLogoutNoticeStore = create<LogoutNoticeState>((set) => ({
  notice: null,
  markUnconfirmed: () => set({ notice: "server-unconfirmed" }),
  clear: () => set({ notice: null }),
}))

export const markLogoutUnconfirmed = () => useLogoutNoticeStore.getState().markUnconfirmed()

export const clearLogoutNotice = () => useLogoutNoticeStore.getState().clear()
