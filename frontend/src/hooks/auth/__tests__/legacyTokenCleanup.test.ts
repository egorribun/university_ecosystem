import { afterEach, describe, expect, it, vi } from "vitest"

import { clearLegacyAccessToken, LEGACY_ACCESS_TOKEN_STORAGE_KEY } from "../legacyTokenCleanup"

describe("clearLegacyAccessToken", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("removes the token persisted by pre-cookie application versions", () => {
    const removeItem = vi.fn()

    clearLegacyAccessToken({ removeItem })

    // Keep this assertion independent from the exported constant so a mutated
    // storage key cannot update both sides of the expectation.
    expect(removeItem).toHaveBeenCalledWith("ecosystem.access.token")
    expect(LEGACY_ACCESS_TOKEN_STORAGE_KEY).toBe("ecosystem.access.token")
  })

  it("is safe without browser storage", () => {
    window.localStorage.setItem(LEGACY_ACCESS_TOKEN_STORAGE_KEY, "must-remain")
    expect(() => clearLegacyAccessToken(null)).not.toThrow()
    expect(window.localStorage.getItem(LEGACY_ACCESS_TOKEN_STORAGE_KEY)).toBe("must-remain")
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

  it("fails closed when browser storage access throws", () => {
    const blockedWindow = {}
    Object.defineProperty(blockedWindow, "localStorage", {
      configurable: true,
      get: () => {
        throw new DOMException("blocked", "SecurityError")
      },
    })
    vi.stubGlobal("window", blockedWindow)

    expect(() => clearLegacyAccessToken()).not.toThrow()
  })

  it("fails closed when browser storage rejects access", () => {
    const removeItem = vi.fn(() => {
      throw new DOMException("blocked", "SecurityError")
    })

    expect(() => clearLegacyAccessToken({ removeItem })).not.toThrow()
  })
})
