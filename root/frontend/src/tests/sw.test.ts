import "fake-indexeddb/auto"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

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
}))

vi.mock("workbox-expiration", () => ({
  ExpirationPlugin: vi.fn(() => ({})),
}))

const CLICK_DB_NAME = "notification-interactions"

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

type ServiceWorkerTestingApi = {
  storePendingNavigation: (record: PendingNavigation) => Promise<void>
  storePendingReport: (record: PendingReport) => Promise<void>
  readPendingNavigations: () => Promise<PendingNavigation[]>
  readPendingReports: () => Promise<PendingReport[]>
  processPendingNavigations: () => Promise<void>
  processPendingReports: () => Promise<void>
  processAllQueues: () => Promise<void>
}

const deleteDatabase = async () => {
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase(CLICK_DB_NAME)
    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error ?? new Error("Failed to delete IndexedDB"))
  })
}

type TestServiceWorkerScope = ServiceWorkerGlobalScope &
  typeof globalThis & {
    clients: {
      matchAll: ReturnType<typeof vi.fn>
      openWindow?: (url: string | URL) => Promise<WindowClient | null>
    }
    navigator: Navigator & { setOnline: (value: boolean) => void }
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

beforeEach(async () => {
  vi.resetModules()
  const created = createServiceWorkerScope()
  listeners = created.listeners
  originalSelf = self
  Object.assign(globalThis as typeof globalThis & { self: TestServiceWorkerScope }, {
    self: created.scope,
  })
  await import("@/sw")
})

afterEach(async () => {
  await deleteDatabase()
  vi.restoreAllMocks()
  vi.clearAllMocks()
  Object.assign(globalThis as typeof globalThis & { self: typeof originalSelf }, {
    self: originalSelf,
  })
})

const getListener = (type: string) => {
  const registered = listeners.get(type)
  if (!registered?.length) {
    throw new Error(`Expected listener for ${type}`)
  }
  return registered[registered.length - 1]
}

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
    expect(typeof stored[0].id).toBe("number")
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
})
