type LegacyTokenStorage = Pick<Storage, "removeItem">

export const LEGACY_ACCESS_TOKEN_STORAGE_KEY = "ecosystem.access.token"

/** Remove access tokens persisted by pre-cookie application versions. */
export const clearLegacyAccessToken = (
  storage: LegacyTokenStorage | null | undefined = undefined
) => {
  let resolvedStorage: LegacyTokenStorage | undefined
  try {
    resolvedStorage = storage === null ? undefined : (storage ?? globalThis.window?.localStorage)
  } catch {
    // Access to the storage getter itself may also be blocked by the browser.
    // Cookie auth remains authoritative in either case.
    return
  }

  if (resolvedStorage === undefined) return

  try {
    // Resolve and invoke the method inside the same guard: browser storage
    // implementations may expose a getter that throws before the call.
    resolvedStorage.removeItem(LEGACY_ACCESS_TOKEN_STORAGE_KEY)
  } catch {
    // A storage implementation may still reject writes/removals at call time.
  }
}
