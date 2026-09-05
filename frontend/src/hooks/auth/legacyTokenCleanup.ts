import { logWarning } from "@/app/logger"

type LegacyTokenStorage = Pick<Storage, "removeItem">

export const LEGACY_ACCESS_TOKEN_STORAGE_KEY = "ecosystem.access.token"

/** Remove access tokens persisted by pre-cookie application versions. */
export const clearLegacyAccessToken = (
  storage: LegacyTokenStorage | null | undefined = undefined
): boolean => {
  if (storage === null) return false

  const removeFromStorage = (target: LegacyTokenStorage): boolean => {
    try {
      // Resolve and invoke the method inside the same guard: browser storage
      // implementations may expose a getter that throws before the call.
      target.removeItem(LEGACY_ACCESS_TOKEN_STORAGE_KEY)
      return true
    } catch (error) {
      // A storage implementation may still reject writes/removals at call time.
      logWarning("Unable to remove a legacy access token", error)
      return false
    }
  }

  if (storage !== undefined) return removeFromStorage(storage)
  if (typeof globalThis.window === "undefined") return false

  try {
    return removeFromStorage(globalThis.window.localStorage)
  } catch (error) {
    // Access to the storage getter itself may also be blocked by the browser.
    // Cookie auth remains authoritative in either case.
    logWarning("Unable to access legacy token storage", error)
    return false
  }
}
