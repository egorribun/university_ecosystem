import { describe, expect, it, vi } from "vitest"

describe("storage utilities in SSR", () => {
  it("keep all operations inert when window is unavailable", async () => {
    const originalWindow = globalThis.window
    vi.stubGlobal("window", undefined)
    vi.resetModules()

    const { IS_BROWSER, StorageItem } = await import("@/utils/storage")
    const item = new StorageItem<string>("ssr-key", "fallback")

    expect(IS_BROWSER).toBe(false)
    expect(item.get()).toBe("fallback")
    expect(item.set("value")).toBe(false)
    expect(() => item.remove()).not.toThrow()
    expect(item.exists()).toBe(false)

    vi.stubGlobal("window", originalWindow)
    vi.resetModules()
  })
})
