import { beforeEach, describe, expect, it, vi } from "vitest"

const { registerRouteMock, getSessionHashMock, fetchMock, publicCache, privateCache, cachesMock } =
  vi.hoisted(() => {
    const publicCache = {
      match: vi.fn(),
      put: vi.fn(),
    }
    const privateCache = {
      match: vi.fn(),
      put: vi.fn(),
    }
    return {
      registerRouteMock: vi.fn(),
      getSessionHashMock: vi.fn(),
      fetchMock: vi.fn(),
      publicCache,
      privateCache,
      cachesMock: {
        open: vi.fn(async (name: string) => (name === "media-public" ? publicCache : privateCache)),
        has: vi.fn(),
      },
    }
  })

vi.mock("workbox-routing", () => ({
  registerRoute: registerRouteMock,
}))

vi.mock("workbox-cacheable-response", () => ({
  CacheableResponsePlugin: class {
    constructor(public readonly options: unknown) {}
  },
}))

vi.mock("workbox-expiration", () => ({
  ExpirationPlugin: class {
    constructor(public readonly options: unknown) {}
  },
}))

vi.mock("workbox-strategies", () => ({
  CacheFirst: class {
    constructor(public readonly options: unknown) {}

    async handle() {
      return new Response("shared-image-cache")
    }
  },
  StaleWhileRevalidate: class {
    constructor(public readonly options: unknown) {}
  },
}))

vi.mock("@/sw/api", () => ({
  getSessionHash: getSessionHashMock,
}))

const loadMediaModule = async () => {
  vi.resetModules()
  const { handleMediaRequest, initMediaCaching } = await import("../media")
  return { handleMediaRequest, initMediaCaching }
}

beforeEach(() => {
  vi.clearAllMocks()
  publicCache.match.mockResolvedValue(null)
  publicCache.put.mockResolvedValue(undefined)
  privateCache.match.mockResolvedValue(null)
  privateCache.put.mockResolvedValue(undefined)
  cachesMock.has.mockResolvedValue(false)
  getSessionHashMock.mockReturnValue(null)
  fetchMock.mockResolvedValue(new Response("network", { status: 200 }))
  vi.stubGlobal("self", { caches: cachesMock })
  vi.stubGlobal("fetch", fetchMock)
})

describe("service-worker media cache", () => {
  it("serves a public cache hit before consulting the network", async () => {
    const cached = new Response("public-cache")
    publicCache.match.mockResolvedValue(cached)
    const { handleMediaRequest } = await loadMediaModule()

    await expect(handleMediaRequest("https://cdn.example.test/photo.jpg")).resolves.toBe(cached)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(cachesMock.open).toHaveBeenCalledWith("media-public")
  })

  it("serves an authenticated private cache hit when the session cache exists", async () => {
    getSessionHashMock.mockReturnValue("session-123")
    cachesMock.has.mockResolvedValue(true)
    const cached = new Response("private-cache")
    privateCache.match.mockResolvedValue(cached)
    const { handleMediaRequest } = await loadMediaModule()

    await expect(
      handleMediaRequest(new Request("https://cdn.example.test/private.jpg"))
    ).resolves.toBe(cached)
    expect(cachesMock.has).toHaveBeenCalledWith("media-private:session-123")
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("caches successful public, private, and signed responses but not errors", async () => {
    const { handleMediaRequest } = await loadMediaModule()

    fetchMock.mockResolvedValueOnce(
      new Response("public-network", {
        status: 200,
        headers: { "Cache-Control": "public, max-age=60" },
      })
    )
    await handleMediaRequest("https://app.test/media/public.jpg")
    expect(publicCache.put).toHaveBeenCalledTimes(1)

    getSessionHashMock.mockReturnValue("session-456")
    fetchMock.mockResolvedValueOnce(
      new Response("private-network", {
        status: 200,
        headers: { "Cache-Control": "private" },
      })
    )
    await handleMediaRequest("https://app.test/media/private.jpg")
    expect(privateCache.put).toHaveBeenCalledTimes(1)

    getSessionHashMock.mockReturnValue(null)
    fetchMock.mockResolvedValueOnce(
      new Response("signed-network", {
        status: 200,
        headers: { "x-media-signed-url": "true" },
      })
    )
    await handleMediaRequest("https://app.test/media/signed.jpg")
    expect(publicCache.put).toHaveBeenCalledTimes(2)

    fetchMock.mockResolvedValueOnce(new Response("not-found", { status: 404 }))
    await handleMediaRequest("https://app.test/media/missing.jpg")
    expect(publicCache.put).toHaveBeenCalledTimes(2)
    expect(privateCache.put).toHaveBeenCalledTimes(1)
  })

  it("falls through a private-cache miss without caching an unclassified response", async () => {
    getSessionHashMock.mockReturnValue("session-789")
    cachesMock.has.mockResolvedValue(true)
    privateCache.match.mockResolvedValue(null)
    fetchMock.mockResolvedValue(
      new Response("uncacheable", { status: 200, headers: { "Cache-Control": "no-store" } })
    )
    const { handleMediaRequest } = await loadMediaModule()

    await expect(handleMediaRequest("https://app.test/media/no-store.jpg")).resolves.toBeInstanceOf(
      Response
    )
    expect(privateCache.match).toHaveBeenCalledOnce()
    expect(publicCache.put).not.toHaveBeenCalled()
    expect(privateCache.put).not.toHaveBeenCalled()
  })

  it("registers static, image, and explicit media routes", async () => {
    const { initMediaCaching } = await loadMediaModule()
    initMediaCaching()

    expect(registerRouteMock).toHaveBeenCalledTimes(3)
    const staticMatcher = registerRouteMock.mock.calls[0]?.[0] as (input: { url: URL }) => boolean
    const explicitMatcher = registerRouteMock.mock.calls[1]?.[0] as (input: { url: URL }) => boolean
    const imageMatcher = registerRouteMock.mock.calls[2]?.[0] as (input: {
      request: Request
    }) => boolean
    expect(staticMatcher({ url: new URL("https://app.test/static/app.js") })).toBe(true)
    expect(imageMatcher({ request: { destination: "image" } as Request })).toBe(true)
    expect(explicitMatcher({ url: new URL("https://app.test/media/avatar.jpg") })).toBe(true)
    expect(explicitMatcher({ url: new URL("https://app.test/api/profile") })).toBe(false)

    const explicitHandler = registerRouteMock.mock.calls[1]?.[1] as (input: {
      request: Request
    }) => Promise<Response>
    const cached = new Response("explicit-cache")
    publicCache.match.mockResolvedValue(cached)
    await expect(
      explicitHandler({ request: new Request("https://app.test/media/explicit.jpg") })
    ).resolves.toBe(cached)
  })

  it("resolves private media images through the session-isolated route before image-cache", async () => {
    getSessionHashMock.mockReturnValue("session-123")
    cachesMock.has.mockResolvedValue(true)
    const cached = new Response("private-cache")
    privateCache.match.mockResolvedValue(cached)
    const { initMediaCaching } = await loadMediaModule()
    initMediaCaching()

    const url = new URL("https://app.test/media/private-avatar.jpg")
    const request = new Request(url)
    Object.defineProperty(request, "destination", { value: "image" })

    const matchingRoute = registerRouteMock.mock.calls.find(([matcher]) =>
      (matcher as (input: { request: Request; url: URL }) => boolean)({ request, url })
    )
    expect(matchingRoute).toBeDefined()

    const handler = matchingRoute?.[1] as
      | ((input: { request: Request; url: URL }) => Promise<Response>)
      | { handle: (input: { request: Request; url: URL }) => Promise<Response> }
    const response =
      typeof handler === "function"
        ? await handler({ request, url })
        : await handler.handle({ request, url })

    expect(response).toBe(cached)
    expect(cachesMock.has).toHaveBeenCalledWith("media-private:session-123")
  })
})
