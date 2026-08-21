import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const { cleanupOutdatedCaches, matchPrecache, precacheAndRoute, registerRoute, networkOptions } =
  vi.hoisted(() => ({
    cleanupOutdatedCaches: vi.fn(),
    matchPrecache: vi.fn(),
    precacheAndRoute: vi.fn(),
    registerRoute: vi.fn(),
    networkOptions: [] as Array<{ plugins: Array<{ handlerDidError: () => Promise<Response> }> }>,
  }))

vi.mock("workbox-precaching", () => ({
  cleanupOutdatedCaches,
  matchPrecache,
  precacheAndRoute,
}))
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
    matchPrecache.mockResolvedValue(shell)
    const manifest = [{ url: "/app.js", revision: "1" }]
    vi.stubGlobal("self", { __WB_MANIFEST: manifest, caches: {} })

    initPrecaching()

    expect(precacheAndRoute).toHaveBeenCalledWith(manifest)
    expect(cleanupOutdatedCaches).toHaveBeenCalledOnce()
    expect(registerRoute).toHaveBeenCalledOnce()
    await expect(networkOptions[0]!.plugins[0]!.handlerDidError()).resolves.toBe(shell)
    expect(matchPrecache).toHaveBeenCalledWith("_shell.html")
  })

  it("returns an error response when the navigation shell is unavailable", async () => {
    matchPrecache.mockResolvedValue(undefined)
    vi.stubGlobal("self", { __WB_MANIFEST: [], caches: {} })

    initPrecaching()

    const response = await networkOptions[0]!.plugins[0]!.handlerDidError()
    expect(response.type).toBe("error")
    expect(matchPrecache).toHaveBeenCalledWith("_shell.html")
  })
})
