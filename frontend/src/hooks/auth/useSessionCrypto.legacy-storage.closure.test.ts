// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest"

const { logWarning } = vi.hoisted(() => ({ logWarning: vi.fn() }))
vi.mock("@/app/logger", () => ({ logWarning }))

afterEach(() => {
  vi.unstubAllGlobals()
  logWarning.mockClear()
})

describe("useSessionCrypto legacy storage cleanup", () => {
  it("ignores a storage failure while removing the legacy signing key", async () => {
    const removeItem = vi.fn(() => {
      throw new Error("storage unavailable")
    })
    vi.stubGlobal("sessionStorage", { removeItem })
    vi.resetModules()
    logWarning.mockClear()

    await expect(import("./useSessionCrypto")).resolves.toBeDefined()
    expect(removeItem).toHaveBeenCalledWith("ecosystem.profile.cache.sessionKey")
    expect(logWarning).toHaveBeenCalledWith("Failed to remove legacy session signing key")
  })

  it("loads without legacy cleanup when sessionStorage is unavailable", async () => {
    vi.stubGlobal("sessionStorage", undefined)
    vi.resetModules()

    await expect(import("./useSessionCrypto")).resolves.toBeDefined()
  })
})
