import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const { cleanupOutdatedCaches, precacheAndRoute, registerRoute, networkOptions } = vi.hoisted(
  () => ({
    cleanupOutdatedCaches: vi.fn(),
    precacheAndRoute: vi.fn(),
    registerRoute: vi.fn(),
    networkOptions: [] as Array<{ plugins: Array<{ handlerDidError: () => Promise<Response> }> }>,
  })
)

vi.mock("workbox-precaching", () => ({ cleanupOutdatedCaches, precacheAndRoute }))
vi.mock("workbox-routing", () => ({
  NavigationRoute: class {
    constructor(public readonly handler: unknown) {}
  },
  registerRoute,
}))
vi.mock("workbox-strategies", () => ({
  NetworkOnly: class {
    constructor(public readonly options: (typeof networkOptions)[number]) {
      networkOptions.push(options)
    }
  },
}))

import { initPrecaching } from "../precaching"

beforeEach(() => {
  vi.clearAllMocks()
  networkOptions.length = 0
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("service-worker precaching", () => {
  it("registers the manifest and returns the cached navigation shell", async () => {
    const shell = new Response("shell")
    const match = vi.fn().mockResolvedValue(shell)
    const manifest = [{ url: "/app.js", revision: "1" }]
    vi.stubGlobal("self", { __WB_MANIFEST: manifest, caches: { match } })

    initPrecaching()

    expect(precacheAndRoute).toHaveBeenCalledWith(manifest)
    expect(cleanupOutdatedCaches).toHaveBeenCalledOnce()
    expect(registerRoute).toHaveBeenCalledOnce()
    await expect(networkOptions[0]!.plugins[0]!.handlerDidError()).resolves.toBe(shell)
  })

  it("returns an error response when the navigation shell is unavailable", async () => {
    const match = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal("self", { __WB_MANIFEST: [], caches: { match } })

    initPrecaching()

    const response = await networkOptions[0]!.plugins[0]!.handlerDidError()
    expect(response.type).toBe("error")
    expect(match).toHaveBeenCalledWith("index.html")
  })
})
