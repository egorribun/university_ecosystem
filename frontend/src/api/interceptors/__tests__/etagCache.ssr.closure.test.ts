import { describe, expect, it, vi } from "vitest"

describe("etag cache SSR guards", () => {
  it("keeps cache hydration, scheduling, and visibility setup inert without browser globals", async () => {
    const originalWindow = globalThis.window
    const originalDocument = globalThis.document
    vi.stubGlobal("window", undefined)
    vi.stubGlobal("document", undefined)
    vi.resetModules()

    const { etagCache } = await import("../etagCache")
    expect(etagCache.get("ssr")).toBeUndefined()
    etagCache.set("ssr", '"tag"')
    expect(etagCache.get("ssr")).toBe('"tag"')

    vi.stubGlobal("window", originalWindow)
    vi.stubGlobal("document", originalDocument)
    vi.resetModules()
  })

  it("keeps a visibility flush inert before lazy cache hydration", async () => {
    const originalDocument = globalThis.document
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem")
    let visibilityListener: (() => void) | undefined
    vi.stubGlobal("document", {
      visibilityState: "hidden",
      addEventListener: vi.fn((type: string, listener: () => void) => {
        if (type === "visibilitychange") visibilityListener = listener
      }),
    })
    vi.resetModules()

    await import("../etagCache")
    expect(visibilityListener).toBeTypeOf("function")
    expect(() => visibilityListener?.()).not.toThrow()
    expect(setItemSpy).not.toHaveBeenCalled()

    setItemSpy.mockRestore()
    vi.stubGlobal("document", originalDocument)
    vi.resetModules()
  })
})
