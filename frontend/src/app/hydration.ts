export const APP_HYDRATED_EVENT = "ue:app-hydrated"

export function markAppHydrated(): void {
  if (typeof window === "undefined" || window.__APP_HYDRATED) {
    return
  }

  window.__APP_HYDRATED = true
  window.dispatchEvent(new Event(APP_HYDRATED_EVENT))
}
