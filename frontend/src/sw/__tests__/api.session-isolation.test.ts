import { MessageChannel } from "node:worker_threads"
import { act, renderHook } from "@testing-library/react"
import { useSessionCrypto } from "@/hooks/auth/useSessionCrypto"
import { SERVICE_WORKER_MESSAGE_TYPES } from "@/constants/serviceWorkerMessages"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// Exercise the real Workbox NetworkFirst lifecycle, including asynchronous
// cache.put and event.waitUntil, rather than a mock strategy returning a fixture.
const routes = vi.hoisted(
  () =>
    [] as Array<{
      match: (context: { url: URL; request: Request }) => boolean
      handle: (context: { request: Request; event: ExtendableEvent }) => Promise<Response>
    }>
)
vi.mock("workbox-routing", () => ({
  registerRoute: (
    match: (typeof routes)[number]["match"],
    handle: (typeof routes)[number]["handle"]
  ) => routes.push({ match, handle }),
}))
vi.mock("workbox-expiration", () => ({ ExpirationPlugin: class {} }))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

const entries = new Map<string, Map<string, Response>>()
let beforePut: (() => Promise<void>) | undefined
const storage = {
  async open(name: string) {
    if (!entries.has(name)) entries.set(name, new Map())
    const cache = entries.get(name)!
    return {
      async match(request: Request | string) {
        return cache.get(typeof request === "string" ? request : request.url)?.clone()
      },
      async put(request: Request, response: Response) {
        await beforePut?.()
        cache.set(request.url, response.clone())
      },
      async delete(request: Request) {
        return cache.delete(request.url)
      },
      async keys() {
        return [...cache.keys()].map((url) => new Request(url))
      },
    }
  },
  async keys() {
    return [...entries.keys()]
  },
  async delete(name: string) {
    return entries.delete(name)
  },
  async match(request: Request, options: { cacheName: string }) {
    return (await this.open(options.cacheName)).match(request)
  },
}
let api: typeof import("../api")
const fetchMock = vi.fn<typeof fetch>()
async function request(path = "/api/v1/events/my", init?: RequestInit, clientId = "client-a") {
  const req = new Request(`https://app.test${path}`, init)
  const waits: Promise<unknown>[] = []
  const event = Object.assign(new Event("fetch"), {
    clientId,

    waitUntil: (pending: Promise<unknown>) => {
      waits.push(pending)
    },
  }) as unknown as ExtendableEvent
  const route = routes.find((item) => item.match({ url: new URL(req.url), request: req }))!
  const response = await route.handle({ request: req, event })
  await Promise.all(waits)
  return response
}

beforeEach(async () => {
  entries.clear()
  routes.length = 0
  beforePut = undefined
  vi.resetModules()
  vi.stubGlobal("MessageChannel", MessageChannel)
  vi.stubGlobal("caches", storage)
  vi.stubGlobal("self", {
    caches: storage,
    location: new URL("https://app.test/"),
    __WB_DISABLE_DEV_LOGS: true,
    clients: {
      get: async () => ({
        type: "window",
        postMessage: (_data: unknown, ports: MessagePort[]) =>
          ports[0]!.postMessage({
            sessionHash: api.getSessionHash(),
            sessionScope: api.getSessionCacheScope(),
          }),
      }),
    },
  })
  vi.stubGlobal("FetchEvent", class extends Event {})
  vi.stubGlobal("ExtendableEvent", Event)
  vi.stubGlobal("fetch", fetchMock)
  fetchMock.mockReset().mockImplementation(async () => new Response("private A"))
  api = await import("../api")
  api.initApiCaching()
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe("private API session isolation", () => {
  it.each([undefined, { type: "sharedworker", postMessage: vi.fn() }])(
    "rejects an absent or non-window requesting client: %j",
    async (client) => {
      api.setSessionHash("account-a", "account-a:live-page-nonce")
      vi.stubGlobal("self", { clients: { get: async () => client } })

      await expect(
        api.ensureSessionIdentity(Object.assign(new Event("fetch"), { clientId: "untrusted" }))
      ).resolves.toBe(false)
      expect(api.getSessionCacheScope()).toBe("account-a:live-page-nonce")
      expect(fetchMock).not.toHaveBeenCalled()
    }
  )

  it("abandons identity recovery when the session changes during client lookup", async () => {
    const lookup = deferred<{ type: string; postMessage: ReturnType<typeof vi.fn> }>()
    const postMessage = vi.fn()
    vi.stubGlobal("self", { clients: { get: () => lookup.promise } })
    const result = api.ensureSessionIdentity(
      Object.assign(new Event("fetch"), { clientId: "client-a" })
    )

    api.setSessionHash("account-b", "account-b:new-page-nonce")
    lookup.resolve({ type: "window", postMessage })

    await expect(result).resolves.toBe(false)
    expect(postMessage).not.toHaveBeenCalled()
    expect(api.getSessionCacheScope()).toBe("account-b:new-page-nonce")
  })

  it("times out a silent controlled client and releases the handshake timer", async () => {
    vi.useFakeTimers()
    const entered = deferred<void>()
    const postMessage = vi.fn(() => entered.resolve())
    vi.stubGlobal("self", {
      clients: { get: async () => ({ type: "window", postMessage }) },
    })
    let settled = false
    const result = api
      .ensureSessionIdentity(Object.assign(new Event("fetch"), { clientId: "silent-client" }))
      .then((confirmed) => {
        settled = true
        return confirmed
      })
    await entered.promise

    await vi.advanceTimersByTimeAsync(999)
    expect(settled).toBe(false)
    await vi.advanceTimersByTimeAsync(1)

    await expect(result).resolves.toBe(false)
    expect(postMessage).toHaveBeenCalledExactlyOnceWith(
      { type: SERVICE_WORKER_MESSAGE_TYPES.REQUEST_API_SESSION_CACHE_KEY },
      [expect.anything()]
    )
    expect(api.getSessionHash()).toBeNull()
    expect(vi.getTimerCount()).toBe(0)
  })

  it("purges legacy shared caches without removing scoped or static caches", async () => {
    const legacy = [
      "api-cache",
      "api-news-cache",
      "api-news-interactions",
      "api-events-cache",
      "media-public",
    ]
    const retained = ["api-cache:account-a:live", "media-private:account-a:live", "media-public:v2"]
    for (const name of [...legacy, ...retained]) await storage.open(name)

    await api.purgeLegacyCaches()

    expect(await storage.keys()).toEqual(retained)
  })

  it("preserves a newer login's caches when an earlier logout purge resumes", async () => {
    api.setSessionHash("account-a", "account-a:old")
    await storage.open("api-cache:account-a:old")
    await storage.open("media-private:account-a:old")
    const names = deferred<string[]>()
    vi.spyOn(storage, "keys").mockReturnValueOnce(names.promise)
    const clearing = api.clearSessionCaches()
    expect(api.getSessionHash()).toBeNull()

    api.setSessionHash("account-b", "account-b:new")
    await storage.open("api-cache:account-b:new")
    await storage.open("media-private:account-b:new")
    names.resolve([...entries.keys()])
    await clearing

    expect([...entries.keys()]).toEqual(["api-cache:account-b:new", "media-private:account-b:new"])
    expect(api.getSessionCacheScope()).toBe("account-b:new")
  })

  it("rejects a stale A tab after B rotates the browser session, before broadcasts arrive", async () => {
    const listeners = new Map<string, (event: MessageEvent) => void>()
    const controller = {
      postMessage: (message: { type: string; sessionHash?: string; sessionScope?: string }) => {
        if (message.type === SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE)
          void api.clearSessionCaches()
        if (
          message.type === SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY &&
          message.sessionHash
        )
          api.setSessionHash(message.sessionHash, message.sessionScope)
      },
    }
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: {
        controller,
        addEventListener: (type: string, callback: (event: MessageEvent) => void) =>
          listeners.set(type, callback),
        removeEventListener: (type: string) => listeners.delete(type),
      },
    })
    const tabA = renderHook(() => useSessionCrypto())
    await act(() => tabA.result.current.updateSessionSigningKey("live-key-A"))
    await request()
    expect([...entries.values()].some((cache) => cache.size > 0)).toBe(true)
    // Another tab changes the shared browser session. Deliberately deliver no
    // storage/BroadcastChannel/controllerchange event to the existing A tab.
    localStorage.setItem(
      "ecosystem.session.generation.v1",
      JSON.stringify({ nonce: "new-B-generation", hash: "B-session-hash" })
    )
    expect(tabA.result.current.sessionSigningKeyRef.current).toBe("live-key-A")
    vi.resetModules()
    routes.length = 0
    const client = {
      type: "window",
      postMessage: (data: unknown, ports: MessagePort[]) =>
        listeners.get("message")!({ source: controller, data, ports } as unknown as MessageEvent),
    }
    vi.stubGlobal("self", {
      caches: storage,
      location: new URL("https://app.test/"),
      __WB_DISABLE_DEV_LOGS: true,
      clients: { get: async () => client },
    })
    api = await import("../api")
    api.initApiCaching()
    fetchMock.mockRejectedValue(new TypeError("offline"))
    await expect(request(undefined, undefined, "client-a")).rejects.toThrow("offline")
    expect(api.getSessionHash()).toBeNull()
    tabA.unmount()
  })

  it.each(["", undefined])(
    "never uses global identity for a missing requesting client: %s",
    async (clientId) => {
      api.setSessionHash("account-a")
      await request()
      fetchMock.mockRejectedValue(new TypeError("offline"))
      // undefined is represented by an actual event without clientId, not the
      // helper's controlled-client default.
      const req = new Request("https://app.test/api/v1/events/my")
      const event = Object.assign(new Event("fetch"), {
        ...(clientId === undefined ? {} : { clientId }),
        waitUntil: () => undefined,
      }) as unknown as ExtendableEvent
      await expect(routes[0]!.handle({ request: req, event })).rejects.toThrow("offline")
    }
  )

  it("does not give an unconfirmed caller another controlled client's cached response", async () => {
    api.setSessionHash("account-a")
    await request()
    const client = {
      type: "window",
      postMessage: (_message: unknown, ports: MessagePort[]) =>
        ports[0]!.postMessage({ sessionHash: null, sessionScope: null }),
    }
    vi.stubGlobal("self", {
      caches: storage,
      location: new URL("https://app.test/"),
      __WB_DISABLE_DEV_LOGS: true,
      clients: { get: async () => client },
    })
    fetchMock.mockRejectedValue(new TypeError("offline"))
    await expect(request(undefined, undefined, "new-unconfirmed-tab")).rejects.toThrow("offline")
    expect(api.getSessionHash()).toBe("account-a")
  })

  it("recovers a confirmed open client's offline cache after a routine worker restart", async () => {
    api.setSessionHash("account-a", "account-a:live-page-nonce")
    await request()
    const scope = api.getSessionCacheScope()
    vi.resetModules()
    routes.length = 0
    const postMessage = vi.fn((_message, ports) =>
      ports[0].postMessage({ sessionHash: "account-a", sessionScope: scope })
    )
    vi.stubGlobal("self", {
      caches: storage,
      location: new URL("https://app.test/"),
      __WB_DISABLE_DEV_LOGS: true,
      clients: {
        get: async (id: string) =>
          id === "client-a" ? { type: "window", postMessage } : undefined,
      },
    })
    api = await import("../api")
    api.initApiCaching()
    await api.purgeLegacyCaches()
    fetchMock.mockRejectedValue(new TypeError("offline"))
    expect(await (await request(undefined, undefined, "client-a")).text()).toBe("private A")
    expect(postMessage).toHaveBeenCalledOnce()
    expect(api.getSessionCacheScope()).toBe(scope)
  })

  it.each([
    "/api/v1/events/my",
    "/api/v1/events/1/attachments/2",
    "/api/v1/schedule",
    "/api/v1/news/1/comments",
  ])("keeps legitimate offline responses within one session: %s", async (path) => {
    api.setSessionHash("account-a")
    expect(await (await request(path)).text()).toBe("private A")
    fetchMock.mockRejectedValue(new TypeError("offline"))
    expect(await (await request(path)).text()).toBe("private A")
    api.setSessionHash("account-b")
    await expect(request(path)).rejects.toThrow()
  })

  it("never reads legacy/shared caches before identity is established", async () => {
    for (const name of ["api-cache", "api-events-cache", "api-news-cache", "api-cache:old-session"])
      await (
        await storage.open(name)
      ).put(new Request("https://app.test/api/v1/events/my"), new Response("legacy private"))
    fetchMock.mockRejectedValue(new TypeError("offline"))
    await expect(request()).rejects.toThrow("offline")
    await api.clearSessionCaches()
    expect(entries.size).toBe(0)
    expect(api.getSessionHash()).toBeNull()
  })

  it("does not restore a previous worker's session on a cold restart", async () => {
    api.setSessionHash("account-a")
    await request()
    vi.resetModules()
    routes.length = 0
    api = await import("../api")
    api.initApiCaching()
    fetchMock.mockRejectedValue(new TypeError("offline"))
    await expect(request()).rejects.toThrow("offline")
  })

  it.each(["private, no-store", "public, no-store", "no-cache"])(
    "respects %s and removes earlier stored copies",
    async (cacheControl) => {
      api.setSessionHash("account-a")
      await request()
      fetchMock.mockResolvedValue(
        new Response("uncacheable", { headers: { "Cache-Control": cacheControl } })
      )
      expect(await (await request()).text()).toBe("uncacheable")
      fetchMock.mockRejectedValue(new TypeError("offline"))
      await expect(request()).rejects.toThrow()
    }
  )

  it.each([{ cache: "no-store" as const }, { headers: { "Cache-Control": "no-store" } }])(
    "bypasses stored data for a no-store request %j",
    async (options) => {
      api.setSessionHash("account-a")
      await request()
      fetchMock.mockRejectedValue(new TypeError("offline"))
      await expect(request(undefined, options)).rejects.toThrow("offline")
    }
  )

  it("rejects a network response delayed across account changes", async () => {
    api.setSessionHash("account-a")
    const delayed = deferred<Response>()
    const entered = deferred<void>()
    fetchMock.mockImplementationOnce(() => {
      entered.resolve()
      return delayed.promise
    })
    const result = request()
    await entered.promise
    api.setSessionHash("account-b")
    delayed.resolve(new Response("old private payload"))
    expect((await result).type).toBe("error")
    expect([...entries.values()].every((cache) => cache.size === 0)).toBe(true)
  })

  it("removes writes that complete after logout and cannot reuse them on same-account login", async () => {
    api.setSessionHash("account-a")
    const entered = deferred<void>()
    const release = deferred<void>()
    beforePut = async () => {
      entered.resolve()
      await release.promise
    }
    const result = request()
    await entered.promise
    await api.clearSessionCaches()
    api.setSessionHash("account-a")
    release.resolve()
    await result
    expect(entries.size).toBe(0)
    fetchMock.mockRejectedValue(new TypeError("offline"))
    await expect(request()).rejects.toThrow()
  })

  it("revokes the namespace on 401 without replacing it with an offline success", async () => {
    api.setSessionHash("account-a")
    await request()
    fetchMock.mockResolvedValue(new Response("expired", { status: 401 }))
    expect((await request()).status).toBe(401)
    expect(api.getSessionHash()).toBeNull()
    expect([...entries.values()].every((cache) => cache.size === 0)).toBe(true)
  })
})

describe("private media session isolation", () => {
  const mediaUrl = "https://app.test/media/attachment.jpg"
  const mediaEvent = () => Object.assign(new Event("fetch"), { clientId: "client-a" })

  it.each([{ cache: "no-store" as const }, { headers: { "Cache-Control": "no-store" } }])(
    "bypasses cached media and avoids replacement writes for %j",
    async (options) => {
      api.setSessionHash("account-a", "account-a:live")
      const req = new Request(mediaUrl, options)
      await (await storage.open("media-public:v2")).put(req, new Response("old public"))
      await (
        await storage.open("media-private:account-a:live")
      ).put(req, new Response("old private"))
      const { handleMediaRequest } = await import("../media")

      const response = await handleMediaRequest(req, mediaEvent())

      expect(await response.text()).toBe("private A")
      expect(fetchMock).toHaveBeenCalledExactlyOnceWith(req)
      expect(await (await (await storage.open("media-public:v2")).match(req))!.text()).toBe(
        "old public"
      )
      expect(
        await (await (await storage.open("media-private:account-a:live")).match(req))!.text()
      ).toBe("old private")
    }
  )

  it("rejects a media response that arrives after the account changes", async () => {
    api.setSessionHash("account-a", "account-a:live")
    const entered = deferred<void>()
    const network = deferred<Response>()
    fetchMock.mockImplementationOnce(() => {
      entered.resolve()
      return network.promise
    })
    const { handleMediaRequest } = await import("../media")
    const response = handleMediaRequest(mediaUrl, mediaEvent())
    await entered.promise
    api.setSessionHash("account-b", "account-b:new")
    network.resolve(new Response("old private media"))

    expect((await response).type).toBe("error")
    expect([...entries.values()].every((cache) => cache.size === 0)).toBe(true)
  })

  it("rejects a private write when the session changes while its cache opens", async () => {
    api.setSessionHash("account-a", "account-a:live")
    const entered = deferred<void>()
    const release = deferred<void>()
    const open = storage.open.bind(storage)
    vi.spyOn(storage, "open")
      .mockImplementationOnce(open)
      .mockImplementationOnce(open)
      .mockImplementationOnce(async (name) => {
        entered.resolve()
        await release.promise
        return open(name)
      })
    const { handleMediaRequest } = await import("../media")
    const response = handleMediaRequest(mediaUrl, mediaEvent())
    await entered.promise
    api.setSessionHash("account-b", "account-b:new")
    release.resolve()

    expect((await response).type).toBe("error")
    expect([...entries.values()].every((cache) => cache.size === 0)).toBe(true)
  })

  it("deletes a private media write that finishes after the account changes", async () => {
    api.setSessionHash("account-a", "account-a:live")
    const entered = deferred<void>()
    const release = deferred<void>()
    beforePut = async () => {
      entered.resolve()
      await release.promise
    }
    const { handleMediaRequest } = await import("../media")
    const response = handleMediaRequest(mediaUrl, mediaEvent())
    await entered.promise
    api.setSessionHash("account-b", "account-b:new")
    expect(entries.has("media-private:account-a:live")).toBe(true)
    release.resolve()

    expect((await response).type).toBe("error")
    expect(entries.has("media-private:account-a:live")).toBe(false)
    expect(api.getSessionCacheScope()).toBe("account-b:new")
    fetchMock.mockRejectedValueOnce(new TypeError("offline"))
    await expect(handleMediaRequest(mediaUrl, mediaEvent())).rejects.toThrow("offline")
  })
})
