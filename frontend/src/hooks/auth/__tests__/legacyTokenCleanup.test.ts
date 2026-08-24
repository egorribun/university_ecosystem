import { afterEach, describe, expect, it, vi } from "vitest"

import { clearLegacyAccessToken, LEGACY_ACCESS_TOKEN_STORAGE_KEY } from "../legacyTokenCleanup"

describe("clearLegacyAccessToken", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("removes the token persisted by pre-cookie application versions", () => {
    const removeItem = vi.fn()

    clearLegacyAccessToken({ removeItem })

    expect(removeItem).toHaveBeenCalledWith(LEGACY_ACCESS_TOKEN_STORAGE_KEY)
  })

  it("is safe without browser storage", () => {
    expect(() => clearLegacyAccessToken(null)).not.toThrow()
  })

  it("uses browser storage by default", () => {
    window.localStorage.setItem(LEGACY_ACCESS_TOKEN_STORAGE_KEY, "legacy-token")

    clearLegacyAccessToken()

    expect(window.localStorage.getItem(LEGACY_ACCESS_TOKEN_STORAGE_KEY)).toBeNull()
  })

  it("is safe during server-side rendering", () => {
    vi.stubGlobal("window", undefined)

    expect(() => clearLegacyAccessToken()).not.toThrow()
  })

  it("fails closed when browser storage rejects access", () => {
    const removeItem = vi.fn(() => {
      throw new DOMException("blocked", "SecurityError")
    })

    expect(() => clearLegacyAccessToken({ removeItem })).not.toThrow()
  })
})
