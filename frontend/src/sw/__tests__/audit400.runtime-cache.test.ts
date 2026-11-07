import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const workbox = vi.hoisted(() => ({
  routes: [] as Array<{
    match: (context: { url: URL; request: Request }) => boolean
    handler: (context: { request: Request; event: Event }) => Promise<Response>
  }>,
  strategies: [] as Array<Record<string, unknown>>,
}))

vi.mock("workbox-core", () => ({ clientsClaim: vi.fn() }))
vi.mock("workbox-routing", () => ({
  registerRoute: (
    match: (context: { url: URL; request: Request }) => boolean,
    handler: unknown
  ) => {
    workbox.routes.push({
      match,
      handler: handler as (context: { request: Request; event: Event }) => Promise<Response>,
    })
  },
}))
vi.mock("workbox-strategies", () => ({
  NetworkFirst: class {
    constructor(options: Record<string, unknown>) {
      workbox.strategies.push(options)
    }

    async handle() {
      return new Response("strategy response")
    }
  },
}))
vi.mock("workbox-expiration", () => ({ ExpirationPlugin: class {} }))
vi.mock("../precaching", () => ({ initPrecaching: vi.fn() }))
vi.mock("../media", () => ({ initMediaCaching: vi.fn(), handleMediaRequest: vi.fn() }))
vi.mock("../push", () => ({ initPushHandlers: vi.fn() }))
vi.mock("../logger", () => ({ log: vi.fn(), warn: vi.fn(), error: vi.fn() }))
vi.mock("../offline", () => ({
  initOfflineQueue: vi.fn(async () => {}),
  processOfflineQueues: vi.fn(async () => {}),
  storePendingNavigation: vi.fn(),
  readPendingNavigations: vi.fn(),
  storePendingReport: vi.fn(),
  readPendingReports: vi.fn(),
  storePendingMutation: vi.fn(),
  readPendingMutations: vi.fn(),
  processPendingNavigations: vi.fn(),
  processPendingReports: vi.fn(),
  processPendingMutations: vi.fn(),
  sanitizeReportPayload: vi.fn(),
}))

class TestMessageChannel {
  port1 = {
    onmessage: null as null | ((event: { data: unknown }) => void),
    close: vi.fn(),
  }
  port2 = {
    postMessage: (data: unknown) => queueMicrotask(() => this.port1.onmessage?.({ data })),
    close: vi.fn(),
  }
}

function requestContext(path: string, method = "GET", cache?: RequestCache) {
  const url = new URL(path, "http://localhost")
  return {
    url,
    request: new Request(url, { method, cache }),
    event: Object.assign(new Event("fetch"), { clientId: "page" }),
  }
}

describe("AUD-400: the custom worker registers its real API cache route", () => {
  const getClient = vi.fn()
  const fetchNetwork = vi.fn(async () => new Response("network response"))

  beforeEach(async () => {
    vi.resetModules()
    workbox.routes.length = 0
    workbox.strategies.length = 0
    getClient.mockReset()
    fetchNetwork.mockClear()
    vi.stubGlobal("MessageChannel", TestMessageChannel)
    vi.stubGlobal("fetch", fetchNetwork)
    vi.stubGlobal("caches", { keys: vi.fn(async () => []), delete: vi.fn() })
    vi.stubGlobal("self", {
      addEventListener: vi.fn(),
      clients: { get: getClient },
      location: new URL("http://localhost/"),
      navigator: { onLine: true },
    })
    await import("../../sw")
    await vi.waitFor(() => expect(workbox.routes).toHaveLength(1))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it.each(["/api/v1/news", "/api/v1/events", "/api/v1/schedule"])(
    "matches the current versioned GET path %s",
    (path) => {
      expect(workbox.routes[0]!.match(requestContext(path))).toBe(true)
    }
  )

  it.each(["/api/v1/users/me", "/api/v1/auth/csrf-cookie", "/api/v1/csrf", "/api/v1/public/news"])(
    "does not intercept sensitive or public GET path %s",
    (path) => {
      expect(workbox.routes[0]!.match(requestContext(path))).toBe(false)
    }
  )

  it("does not intercept API mutations", () => {
    expect(workbox.routes[0]!.match(requestContext("/api/v1/news/1/like", "POST"))).toBe(false)
  })

  it("uses the network when no controlled window confirms the session", async () => {
    getClient.mockResolvedValue(null)
    const context = requestContext("/api/v1/news")

    const response = await workbox.routes[0]!.handler(context)

    expect(await response.text()).toBe("network response")
    expect(fetchNetwork).toHaveBeenCalledWith(context.request)
    expect(workbox.strategies).toHaveLength(0)
  })

  it("uses a confirmed session namespace and refuses no-store responses", async () => {
    getClient.mockResolvedValue({
      type: "window",
      postMessage: (_message: unknown, ports: MessagePort[]) =>
        ports[0]!.postMessage({ sessionHash: "account", sessionScope: "account:session" }),
    })
    const context = requestContext("/api/v1/news")

    const response = await workbox.routes[0]!.handler(context)

    expect(await response.text()).toBe("strategy response")
    const options = workbox.strategies[0]!
    expect(options.cacheName).toBe("api-cache:account:session")
    const plugin = (
      options.plugins as Array<{
        cacheWillUpdate: (context: { response: Response }) => Promise<Response | null>
      }>
    )[0]!
    await expect(
      plugin.cacheWillUpdate({
        response: new Response("private", { headers: { "Cache-Control": "no-store" } }),
      })
    ).resolves.toBeNull()
  })
})
