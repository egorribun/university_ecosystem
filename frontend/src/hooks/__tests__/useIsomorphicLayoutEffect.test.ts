import { afterEach, describe, expect, it, vi } from "vitest"

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("useIsomorphicLayoutEffect runtime selection", () => {
  it("selects layout effects in browsers and passive effects during SSR", async () => {
    const browserWindow = globalThis.window

    vi.resetModules()
    const browserReact = await import("react")
    const browserModule = await import("../useIsomorphicLayoutEffect")
    expect(browserModule.useIsomorphicLayoutEffect).toBe(browserReact.useLayoutEffect)

    vi.stubGlobal("window", undefined)
    vi.resetModules()
    const serverReact = await import("react")
    const serverModule = await import("../useIsomorphicLayoutEffect")
    expect(serverModule.useIsomorphicLayoutEffect).toBe(serverReact.useEffect)

    vi.stubGlobal("window", browserWindow)
  })
})
