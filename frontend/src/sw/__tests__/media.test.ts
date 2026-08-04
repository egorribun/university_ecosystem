import { beforeEach, describe, expect, it, vi } from "vitest"

const {
  registerRouteMock,
  getSessionHashMock,
  fetchMock,
  publicCache,
  privateCache,
  cachesMock,
} = vi.hoisted(() => {
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
      open: vi.fn(async (name: string) =>
        name === "media-public" ? publicCache : privateCache
      ),
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

    await expect(handleMediaRequest(new Request("https://cdn.example.test/private.jpg"))).resolves.toBe(
      cached
    )
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

  it("registers static, image, and explicit media routes", async () => {
    const { handleMediaRequest, initMediaCaching } = await loadMediaModule()
    initMediaCaching()

    expect(registerRouteMock).toHaveBeenCalledTimes(3)
    const staticMatcher = registerRouteMock.mock.calls[0]?.[0] as (input: { url: URL }) => boolean
    const imageMatcher = registerRouteMock.mock.calls[1]?.[0] as (
      input: { request: Request }
    ) => boolean
    expect(staticMatcher({ url: new URL("https://app.test/static/app.js") })).toBe(true)
    expect(imageMatcher({ request: { destination: "image" } as Request })).toBe(true)

    const explicitHandler = registerRouteMock.mock.calls[2]?.[1] as (input: {
      request: Request
    }) => Promise<Response>
    const cached = new Response("explicit-cache")
    publicCache.match.mockResolvedValue(cached)
    await expect(
      explicitHandler({ request: new Request("https://app.test/media/explicit.jpg") })
    ).resolves.toBe(cached)
  })
})
