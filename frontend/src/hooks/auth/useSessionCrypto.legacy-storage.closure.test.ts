// @vitest-environment jsdom

import { describe, expect, it, vi } from "vitest"

describe("useSessionCrypto legacy storage cleanup", () => {
  it("ignores a storage failure while removing the legacy signing key", async () => {
    const removeItem = vi.fn(() => {
      throw new Error("storage unavailable")
    })
    vi.stubGlobal("sessionStorage", { removeItem })
    vi.resetModules()

    await expect(import("./useSessionCrypto")).resolves.toBeDefined()
    expect(removeItem).toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})
