/* eslint-disable @typescript-eslint/no-explicit-any */
import "fake-indexeddb/auto"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"
import { http, HttpResponse } from "msw"
import { SERVICE_WORKER_MESSAGE_TYPES } from "@/constants/serviceWorkerMessages"
import { server } from "@/tests/mocks/server"

vi.mock("workbox-precaching", () => ({
  cleanupOutdatedCaches: vi.fn(),
  precacheAndRoute: vi.fn(),
  createHandlerBoundToURL: vi.fn(() => vi.fn()),
}))

vi.mock("workbox-core", () => ({
  clientsClaim: vi.fn(),
}))

vi.mock("workbox-routing", () => ({
  registerRoute: vi.fn(),
  NavigationRoute: vi.fn(),
}))

vi.mock("workbox-strategies", () => ({
  StaleWhileRevalidate: vi.fn(() => ({})),
  CacheFirst: vi.fn(() => ({})),
  NetworkFirst: vi.fn(() => ({})),
  NetworkOnly: vi.fn(() => ({})),
}))

vi.mock("workbox-expiration", () => {
  const CacheExpiration = vi.fn(() => ({
    updateTimestamp: vi.fn(async () => {}),
    expireEntries: vi.fn(async () => {}),
    delete: vi.fn(async () => {}),
  }))
  return {
    ExpirationPlugin: vi.fn(() => ({})),
    CacheExpiration,
  }
})

type PendingNavigation = {
  id?: number
  url: string
  action?: string | null
  timestamp: number
}

type PendingReport = PendingNavigation & {
  reportUrl: string
  payload?: Record<string, unknown>
}

type CacheEntryStore = Map<string, Response>

type CacheStorageMock = CacheStorage & { __store: Map<string, CacheEntryStore> }

type SyncEvent = Event & {
  tag: string
  waitUntil: (promise: Promise<unknown>) => void
}

const resolveRequestKey = (request: RequestInfo | URL): string => {
  if (typeof request === "string") return request
  if (request instanceof URL) return request.toString()
  if (request instanceof Request) return request.url
  return String(request)
}

const createCacheInstance = (store: CacheEntryStore): Cache => {
  const put = async (request: RequestInfo | URL, response: Response) => {
    store.set(resolveRequestKey(request), response.clone())
  }

  return {
    match: async (request: RequestInfo | URL) => store.get(resolveRequestKey(request)),
    matchAll: async (
      request?: RequestInfo | URL,
      _options?: CacheQueryOptions
    ): Promise<readonly Response[]> => {
      if (typeof request === "undefined") {
        return Array.from(store.values())
      }
      const match = store.get(resolveRequestKey(request))
      return match ? [match] : []
    },
    put,
    delete: async (request: RequestInfo | URL) => store.delete(resolveRequestKey(request)),
    keys: async () => Array.from(store.keys()).map((url) => new Request(url)),
    add: async (request: RequestInfo | URL) => {
      if (typeof request === "string") {
        const response = await fetch(request)
        await put(request, response)
      }
    },
    addAll: async (requests: (RequestInfo | URL)[]) => {
      await Promise.all(requests.map((entry) => put(entry, new Response(null))))
    },
  } as Cache
}

const createCacheStorageMock = (): CacheStorageMock => {
  const cacheStore = new Map<string, CacheEntryStore>()
  const ensureStore = (name: string) => {
    let store = cacheStore.get(name)
    if (!store) {
      store = new Map<string, Response>()
      cacheStore.set(name, store)
    }
    return store
  }

  return {
    __store: cacheStore,
    match: async (request: RequestInfo | URL) => {
      const key = resolveRequestKey(request)
      for (const store of cacheStore.values()) {
        if (store.has(key)) {
          return store.get(key)
        }
      }
      return undefined
    },
    has: async (name: string) => cacheStore.has(name),
    open: async (name: string) => createCacheInstance(ensureStore(name)),
    delete: async (name: string) => cacheStore.delete(name),
    keys: async () => Array.from(cacheStore.keys()),
  }
}

type ServiceWorkerTestingApi = {
  storePendingNavigation: (record: PendingNavigation) => Promise<void>
  storePendingReport: (record: PendingReport) => Promise<void>
  readPendingNavigations: () => Promise<PendingNavigation[]>
  readPendingReports: () => Promise<PendingReport[]>
  processPendingNavigations: () => Promise<void>
  processPendingReports: () => Promise<void>
  processAllQueues: () => Promise<void>
  handleMediaRequest: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
}

type SwModule = typeof import("@/sw")

type TestServiceWorkerScope = ServiceWorkerGlobalScope &
  typeof globalThis & {
    clients: {
      matchAll: ReturnType<typeof vi.fn>
      openWindow?: (url: string | URL) => Promise<WindowClient | null>
    }
    navigator: Navigator & { setOnline: (value: boolean) => void }
    caches: CacheStorageMock
  }

const createServiceWorkerScope = () => {
  const listeners = new Map<string, ((event: Event) => void)[]>()

  let online = true
  const navigator = Object.assign(Object.create(null), {
    sendBeacon: undefined,
    setOnline: (value: boolean) => {
      online = value
    },
  }) as Navigator & { setOnline: (value: boolean) => void }

  Object.defineProperty(navigator, "onLine", {
    configurable: true,
    get: () => online,
  })

  const caches = createCacheStorageMock()

  const scope: TestServiceWorkerScope = Object.assign(Object.create(null), {
    __WB_MANIFEST: [],
    addEventListener: vi.fn(<T extends Event>(type: string, listener: (event: T) => void) => {
      const existing = listeners.get(type) ?? []
      existing.push(listener as (event: Event) => void)
      listeners.set(type, existing)
    }),
    clients: {
      matchAll: vi.fn(async () => []),
      openWindow: undefined,
    },
    console,
    fetch: globalThis.fetch.bind(globalThis),
    indexedDB: globalThis.indexedDB,
    IDBKeyRange: globalThis.IDBKeyRange,
    location: new URL("https://example.com/"),
    navigator,
    registration: {
      scope: "https://example.com/",
      showNotification: vi.fn(),
      sync: undefined,
    },
    skipWaiting: vi.fn(),
    caches,
  })

  return { scope, listeners }
}

const loadServiceWorker = async () => {
  const testing = (
    self as unknown as ServiceWorkerGlobalScope & {
      __SW_TESTING__?: ServiceWorkerTestingApi
    }
  ).__SW_TESTING__
  if (!testing) {
    throw new Error("Service worker testing helpers were not registered")
  }
  return testing
}

let originalSelf: typeof globalThis
let listeners: Map<string, ((event: Event) => void)[]>
let originalCaches: CacheStorage | undefined
let swModule: SwModule | undefined

beforeEach(async () => {
  vi.resetModules()
  const created = createServiceWorkerScope()
  listeners = created.listeners
  originalSelf = self
  const globalWithCaches = globalThis as typeof globalThis & { caches?: CacheStorage }
  originalCaches = globalWithCaches.caches
  Object.assign(globalThis as typeof globalThis & { self: TestServiceWorkerScope }, {
    self: created.scope,
  })
  globalWithCaches.caches = created.scope.caches
  swModule = await import("@/sw")
  // Explicitly initialize offline queue to ensure IndexedDB stores exist
  // even if bootstrap fails due to mock issues
  const offlineModule = await import("@/sw/offline")
  await offlineModule.initOfflineQueue()
})

afterEach(async () => {
  // Note: deleteDatabase() removed to prevent hook timeouts with fake-indexeddb
  vi.restoreAllMocks()
  vi.clearAllMocks()
  const globalWithCaches = globalThis as typeof globalThis & { caches?: CacheStorage }
  if (originalCaches) {
    globalWithCaches.caches = originalCaches
  } else {
    Reflect.deleteProperty(globalWithCaches, "caches")
  }
  Object.assign(globalThis as typeof globalThis & { self: typeof originalSelf }, {
    self: originalSelf,
  })
  swModule = undefined
})

const getListener = (type: string) => {
  const registered = listeners.get(type)
  if (!registered?.length) {
    throw new Error(`Expected listener for ${type}`)
  }
  return registered[registered.length - 1]!
}

const getSwModule = () => {
  if (!swModule) {
    throw new Error("SW module was not loaded")
  }
  return swModule
}

const getQueueModules = () => {
  const module = getSwModule()
  return {
    stores: module.queueStores,
    processors: module.queueProcessors,
    sanitizers: module.queueSanitizers,
    syncTags: module.queueSyncTags,
  }
}

const dispatchSwMessage = async (data: Record<string, unknown>) => {
  const listener = getListener("message")
  const waitUntil = vi.fn((promise: Promise<unknown>) => promise)
  listener({
    data,
    origin: self.location.origin,
    source: { url: self.location.href } as unknown as Client,
    waitUntil,
  } as unknown as ExtendableMessageEvent)
  const pending = waitUntil.mock.calls[0]?.[0]
  if (pending instanceof Promise) {
    await pending
  }
}

describe("queue helper module exports", () => {
  test("sanitizes report payloads deeply", () => {
    const { sanitizers } = getQueueModules()
    const payload = {
      ok: "value",
      nested: {
        valid: 1,
        invalid: () => {},
      },
    }

    const sanitized = sanitizers.sanitizeReportPayload(payload)

    expect(sanitized).toEqual({
      ok: "value",
      nested: { valid: 1 },
    })
    expect("invalid" in ((sanitized as any)?.nested as Record<string, unknown>)).toBe(false)
  })

  test("report queue waits for connectivity before flushing", async () => {
    const { stores, processors } = getQueueModules()
    const scope = self as unknown as TestServiceWorkerScope
    scope.navigator.setOnline(false)

    await stores.storePendingReport({
      url: "https://example.com/events",
      reportUrl: "https://example.com/api/report",
      timestamp: Date.now(),
      payload: { keep: true },
    })

    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true } as Response)

    await processors.processPendingReports()
    expect(fetchMock).not.toHaveBeenCalled()

    scope.navigator.setOnline(true)
    await processors.processPendingReports()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(await stores.readPendingReports()).toHaveLength(0)
  })
})

describe("background sync integration", () => {
  test("navigation sync drains queued targets once back online", async () => {
    const { stores, syncTags } = getQueueModules()
    const scope = self as unknown as TestServiceWorkerScope
    scope.navigator.setOnline(false)
    scope.clients.openWindow = vi.fn(async () => null)

    await stores.storePendingNavigation({
      url: "https://example.com/home",
      timestamp: Date.now(),
    })

    scope.navigator.setOnline(true)

    const syncListener = getListener("sync")
    const waitUntil = vi.fn((promise: Promise<unknown>) => promise)

    const syncEvent = Object.assign(new Event("sync"), {
      tag: syncTags.navigation,
      waitUntil,
    }) as SyncEvent

    syncListener(syncEvent)

    const pending = waitUntil.mock.calls[0]?.[0]
    if (pending instanceof Promise) {
      await pending
    }

    expect(await stores.readPendingNavigations()).toHaveLength(0)
    expect(scope.clients.openWindow).toHaveBeenCalledWith("https://example.com/home")
  })
})

describe("service worker offline queues", () => {
  test("storePendingNavigation persists navigation requests", async () => {
    const sw = await loadServiceWorker()
    const record: PendingNavigation = {
      url: "https://example.com/profile",
      action: null,
      timestamp: Date.now(),
    }

    await sw.storePendingNavigation(record)
    const stored = await sw.readPendingNavigations()

    expect(stored).toHaveLength(1)
    expect(stored[0]).toMatchObject({ url: record.url, action: record.action })
    expect(typeof stored[0]!.id).toBe("number")
  })

  test("processPendingNavigations and processPendingReports clear processed entries", async () => {
    const sw = await loadServiceWorker()
    const timestamp = Date.now()

    await sw.storePendingNavigation({ url: "https://example.com/dashboard", timestamp })
    await sw.storePendingReport({
      url: "https://example.com/dashboard",
      timestamp,
      reportUrl: "https://example.com/api/report",
    })

    const scope = self as unknown as TestServiceWorkerScope

    scope.navigator.setOnline(true)
    scope.clients.matchAll = vi.fn(async () => [])
    scope.clients.openWindow = vi.fn(async () => null)

    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true } as Response)

    await sw.processPendingNavigations()
    await sw.processPendingReports()

    expect(await sw.readPendingNavigations()).toHaveLength(0)
    expect(await sw.readPendingReports()).toHaveLength(0)
    expect(scope.clients.openWindow).toHaveBeenCalledWith("https://example.com/dashboard")
    expect(fetchMock).toHaveBeenCalledWith("https://example.com/api/report", expect.any(Object))
  })

  test("notificationclick queues offline interactions and clears them via processAllQueues", async () => {
    const scope = self as unknown as TestServiceWorkerScope

    scope.navigator.setOnline(false)
    scope.clients.matchAll = vi.fn(async () => [])
    scope.clients.openWindow = vi.fn(async () => {
      throw new Error("offline")
    })

    const notificationClick = getListener("notificationclick")
    const waitUntil = vi.fn((promise: Promise<unknown>) => promise)

    await notificationClick({
      action: undefined,
      notification: {
        close: vi.fn(),
        data: {
          url: "/courses",
          reportUrl: "/api/notifications/report",
        },
      },
      waitUntil,
    } as unknown as NotificationEvent)

    const waitResult = waitUntil.mock.results[0]?.value
    if (waitResult instanceof Promise) {
      await waitResult
    }

    const sw = await loadServiceWorker()
    const navigationsBefore = await sw.readPendingNavigations()
    const reportsBefore = await sw.readPendingReports()

    expect(navigationsBefore).toHaveLength(1)
    expect(navigationsBefore[0]).toMatchObject({ url: "https://example.com/courses" })
    expect(reportsBefore).toHaveLength(1)
    expect(reportsBefore[0]).toMatchObject({
      reportUrl: "https://example.com/api/notifications/report",
    })

    scope.navigator.setOnline(true)
    scope.clients.openWindow = vi.fn(async () => null)
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true } as Response)

    await sw.processAllQueues()

    expect(await sw.readPendingNavigations()).toHaveLength(0)
    expect(await sw.readPendingReports()).toHaveLength(0)
    expect(scope.clients.openWindow).toHaveBeenCalledWith("https://example.com/courses")
    expect(fetchMock).toHaveBeenCalledWith(
      "https://example.com/api/notifications/report",
      expect.any(Object)
    )
  })

  test("notificationclick sanitizes report payloads before sending", async () => {
    const scope = self as unknown as TestServiceWorkerScope
    scope.navigator.setOnline(true)
    scope.clients.matchAll = vi.fn(async () => [])
    scope.clients.openWindow = vi.fn(async () => null)

    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true } as Response)

    const notificationClick = getListener("notificationclick")
    const waitUntil = vi.fn((promise: Promise<unknown>) => promise)
    const timestamp = Date.now()

    notificationClick({
      action: undefined,
      notification: {
        close: vi.fn(),
        data: {
          url: "/sanitized",
          reportUrl: "/api/notifications/report",
          reportPayload: {
            keep: "yes",
            nested: { ok: true, drop: () => {} },
            arr: [1, { keep: "a", drop: () => {} }],
          },
          notificationId: "abc",
        },
      },
      waitUntil,
      timeStamp: timestamp,
    } as unknown as NotificationEvent)

    const pending = waitUntil.mock.calls[0]?.[0]
    if (pending instanceof Promise) {
      await pending
    }

    const [, requestInit] = fetchMock.mock.calls[0]!
    const parsed = JSON.parse((requestInit?.body as string) ?? "{}")
    expect(parsed.keep).toBe("yes")
    expect(parsed.nested).toEqual({ ok: true })
    expect(parsed.arr).toEqual([1, { keep: "a" }])
    expect(parsed.drop).toBeUndefined()
    expect(parsed.notificationId).toBe("abc")
  })
})

describe("service worker push handling", () => {
  test("in-app push notifications send toast messages to visible clients", async () => {
    const scope = self as unknown as TestServiceWorkerScope
    const postMessage = vi.fn()
    scope.clients.matchAll = vi.fn(async () => [
      {
        postMessage,
        visibilityState: "visible",
      } as unknown as WindowClient,
    ])

    const pushListener = getListener("push")
    const waitUntil = vi.fn((promise: Promise<unknown>) => promise)

    pushListener({
      data: {
        json: () => ({
          title: "Campus alert",
          body: "Tap to view",
          url: "/alerts",
          data: { type: "in-app" },
        }),
      },
      waitUntil,
    } as unknown as PushEvent)

    const pending = waitUntil.mock.calls[0]?.[0]
    if (pending instanceof Promise) {
      await pending
    }

    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "PUSH_NOTIFICATION",
        toast: expect.objectContaining({
          title: "Campus alert",
          body: "Tap to view",
          url: "/alerts",
        }),
      })
    )
    expect(scope.registration.showNotification).not.toHaveBeenCalled()
  })
})

describe("service worker api cache controls", () => {
  test("clears cached news responses after session changes", async () => {
    const scope = self as unknown as TestServiceWorkerScope
    const cacheStorage = scope.caches
    const cacheName = "api-cache:session-test"
    const cache = await cacheStorage.open(cacheName)
    await cache.put("https://example.com/api/news", new Response(JSON.stringify({ id: 1 })))

    const messageListener = getListener("message")
    const waitUntil = vi.fn((promise: Promise<unknown>) => promise)
    messageListener({
      data: { type: SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE },
      origin: self.location.origin,
      source: { url: self.location.href } as unknown as Client,
      waitUntil,
    } as unknown as ExtendableMessageEvent)

    const pending = waitUntil.mock.calls[0]?.[0]
    if (pending instanceof Promise) {
      await pending
    }

    expect(cacheStorage.__store.has(cacheName)).toBe(false)
  })
})

describe("service worker media cache controls", () => {
  test("clears session-specific media caches when requested", async () => {
    const scope = self as unknown as TestServiceWorkerScope
    const cacheName = "media-private:session-alpha"
    const cache = await scope.caches.open(cacheName)
    await cache.put("https://example.com/media/private.png", new Response("alpha"))

    await dispatchSwMessage({ type: SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE })

    expect(scope.caches.__store.has(cacheName)).toBe(false)
  })

  test("private media responses are not reused across sessions", async () => {
    const sw = await loadServiceWorker()
    const scope = self as unknown as TestServiceWorkerScope
    const mediaUrl = "https://example.com/media/private.png"
    let requestCount = 0

    server.use(
      http.get(mediaUrl, () => {
        requestCount += 1
        return HttpResponse.text(`private-response-${requestCount}`, {
          headers: { "Cache-Control": "private" },
        })
      })
    )

    await dispatchSwMessage({
      type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY,
      sessionHash: "alpha",
    })

    const first = await sw.handleMediaRequest(mediaUrl)
    await expect(first.text()).resolves.toBe("private-response-1")
    expect(scope.caches.__store.has("media-private:alpha")).toBe(true)

    await dispatchSwMessage({ type: SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE })
    expect(scope.caches.__store.has("media-private:alpha")).toBe(false)

    await dispatchSwMessage({
      type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY,
      sessionHash: "beta",
    })

    server.use(
      http.get(mediaUrl, () => {
        return HttpResponse.error()
      })
    )

    await expect(sw.handleMediaRequest(mediaUrl)).rejects.toThrow()
    const betaCache = await scope.caches.open("media-private:beta")
    await expect(betaCache.match(mediaUrl)).resolves.toBeUndefined()
  })

  test("public media responses fall back to the shared cache when offline", async () => {
    const sw = await loadServiceWorker()
    const scope = self as unknown as TestServiceWorkerScope
    const mediaUrl = "https://example.com/media/banner.png"
    let requestCount = 0

    server.use(
      http.get(mediaUrl, () => {
        requestCount += 1
        if (requestCount === 1) {
          return HttpResponse.text("public-response", {
            headers: { "Cache-Control": "public, max-age=60" },
          })
        }
        return HttpResponse.error()
      })
    )

    const first = await sw.handleMediaRequest(mediaUrl)
    await expect(first.text()).resolves.toBe("public-response")
    expect(scope.caches.__store.has("media-public")).toBe(true)

    const second = await sw.handleMediaRequest(mediaUrl)
    await expect(second.text()).resolves.toBe("public-response")
  })

  test("signed media responses are cached publicly even during authenticated sessions", async () => {
    const sw = await loadServiceWorker()
    const scope = self as unknown as TestServiceWorkerScope
    const mediaUrl = "https://example.com/media/signed.png"

    await dispatchSwMessage({
      type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY,
      sessionHash: "gamma",
    })

    server.use(
      http.get(mediaUrl, () =>
        HttpResponse.text("signed-media", {
          headers: { "x-media-signed-url": "true" },
        })
      )
    )

    const first = await sw.handleMediaRequest(mediaUrl)
    await expect(first.text()).resolves.toBe("signed-media")
    expect(scope.caches.__store.has("media-public")).toBe(true)
    expect(scope.caches.__store.has("media-private:gamma")).toBe(false)

    server.use(
      http.get(mediaUrl, () => {
        return HttpResponse.error()
      })
    )

    const second = await sw.handleMediaRequest(mediaUrl)
    await expect(second.text()).resolves.toBe("signed-media")
  })
})
