type LegacyTokenStorage = Pick<Storage, "removeItem">

export const LEGACY_ACCESS_TOKEN_STORAGE_KEY = "ecosystem.access.token"

/** Remove access tokens persisted by pre-cookie application versions. */
export const clearLegacyAccessToken = (
  storage: LegacyTokenStorage | null | undefined = undefined
) => {
  try {
    const resolvedStorage =
      storage === null
        ? undefined
        : (storage ?? (typeof window === "undefined" ? undefined : window.localStorage))
    resolvedStorage?.removeItem(LEGACY_ACCESS_TOKEN_STORAGE_KEY)
  } catch {
    // Access to the storage getter itself may also be blocked by the browser.
    // Cookie auth remains authoritative in either case.
  }
}
