import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { SERVICE_WORKER_MESSAGE_TYPES } from "../constants/serviceWorkerMessages"

const mocks = vi.hoisted(() => ({
  clientsClaim: vi.fn(),
  initApiCaching: vi.fn(),
  clearSessionCaches: vi.fn(),
  setSessionHash: vi.fn(),
  log: vi.fn(),
  error: vi.fn(),
  initMediaCaching: vi.fn(),
  handleMediaRequest: vi.fn(),
  initOfflineQueue: vi.fn(),
  processOfflineQueues: vi.fn(),
  initPrecaching: vi.fn(),
  initPushHandlers: vi.fn(),
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

vi.mock("workbox-core", () => ({ clientsClaim: mocks.clientsClaim }))
vi.mock("../sw/api", () => ({
  initApiCaching: mocks.initApiCaching,
  clearSessionCaches: mocks.clearSessionCaches,
  setSessionHash: mocks.setSessionHash,
}))
vi.mock("../sw/logger", () => ({ log: mocks.log, error: mocks.error }))
vi.mock("../sw/media", () => ({
  initMediaCaching: mocks.initMediaCaching,
  handleMediaRequest: mocks.handleMediaRequest,
}))
vi.mock("../sw/offline", () => ({
  initOfflineQueue: mocks.initOfflineQueue,
  processOfflineQueues: mocks.processOfflineQueues,
  storePendingNavigation: mocks.storePendingNavigation,
  readPendingNavigations: mocks.readPendingNavigations,
  storePendingReport: mocks.storePendingReport,
  readPendingReports: mocks.readPendingReports,
  storePendingMutation: mocks.storePendingMutation,
  readPendingMutations: mocks.readPendingMutations,
  processPendingNavigations: mocks.processPendingNavigations,
  processPendingReports: mocks.processPendingReports,
  processPendingMutations: mocks.processPendingMutations,
  sanitizeReportPayload: mocks.sanitizeReportPayload,
}))
vi.mock("../sw/precaching", () => ({ initPrecaching: mocks.initPrecaching }))
vi.mock("../sw/push", () => ({ initPushHandlers: mocks.initPushHandlers }))

type Listener = (event: Record<string, unknown>) => void

type FakeScope = {
  addEventListener: ReturnType<typeof vi.fn>
  skipWaiting: ReturnType<typeof vi.fn>
  location: URL
  __SW_TESTING__?: unknown
}

const createScope = () => {
  const listeners = new Map<string, Listener>()
  const scope: FakeScope = {
    addEventListener: vi.fn((type: string, listener: Listener) => {
      listeners.set(type, listener)
    }),
    skipWaiting: vi.fn(),
    location: new URL("https://app.example/sw.js"),
  }
  return { scope, listeners }
}

let scope: FakeScope
let listeners: Map<string, Listener>

const loadServiceWorker = async () => {
  const module = await import("../sw")
  await vi.waitFor(() => expect(mocks.initPushHandlers).toHaveBeenCalled())
  return module
}

const message = (overrides: Record<string, unknown> = {}) => ({
  data: { type: "UNKNOWN" },
  source: { url: "https://app.example/" },
  origin: "https://app.example",
  waitUntil: vi.fn(),
  ...overrides,
})

beforeEach(() => {
  vi.resetModules()
  vi.unstubAllEnvs()
  vi.clearAllMocks()
  const created = createScope()
  scope = created.scope
  listeners = created.listeners
  vi.stubGlobal("self", scope)

  vi.stubEnv("MODE", "test")
  vi.stubEnv("DEV", false)
  mocks.initOfflineQueue.mockResolvedValue(undefined)
  mocks.processOfflineQueues.mockResolvedValue(undefined)
  mocks.clearSessionCaches.mockResolvedValue(undefined)
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("service-worker entrypoint", () => {
  it("bootstraps modules and exposes the real queue protocol surface", async () => {
    const module = await loadServiceWorker()

    expect(mocks.clientsClaim).toHaveBeenCalledOnce()
    expect(scope.skipWaiting).toHaveBeenCalledOnce()
    expect(mocks.initPrecaching).toHaveBeenCalledOnce()
    expect(mocks.initApiCaching).toHaveBeenCalledOnce()
    expect(mocks.initMediaCaching).toHaveBeenCalledOnce()
    expect(mocks.initOfflineQueue).toHaveBeenCalledOnce()
    expect(mocks.initPushHandlers).toHaveBeenCalledOnce()
    expect(mocks.processOfflineQueues).not.toHaveBeenCalled()
    expect(scope.__SW_TESTING__).toMatchObject({
      processAllQueues: mocks.processOfflineQueues,
      handleMediaRequest: mocks.handleMediaRequest,
    })
    expect(module.queueStores.storePendingMutation).toBe(mocks.storePendingMutation)
    expect(module.queueProcessors.processPendingMutations).toBe(mocks.processPendingMutations)
    expect(module.queueSanitizers.sanitizeReportPayload).toBe(mocks.sanitizeReportPayload)
  })

  it("runs initial synchronization and development logging outside test mode", async () => {
    vi.stubEnv("MODE", "production")
    vi.stubEnv("DEV", true)

    await loadServiceWorker()

    expect(mocks.processOfflineQueues).toHaveBeenCalledOnce()
    expect(mocks.log).toHaveBeenCalledWith("Bootstrap complete")
  })

  it("reports bootstrap failures without registering incomplete helpers", async () => {
    const failure = new Error("indexeddb unavailable")
    mocks.initOfflineQueue.mockRejectedValue(failure)

    await import("../sw")

    await vi.waitFor(() => expect(mocks.error).toHaveBeenCalledWith("SW bootstrap failed", failure))
    expect(scope.__SW_TESTING__).toBeUndefined()
  })

  it("rejects malformed and untraceable messages before dispatch", async () => {
    await loadServiceWorker()
    const listener = listeners.get("message")
    expect(listener).toBeTypeOf("function")

    listener?.(message({ data: null }))
    listener?.(message({ data: "SKIP_WAITING" }))
    listener?.(message({ source: null }))
    listener?.(message({ source: {} }))

    expect(scope.skipWaiting).toHaveBeenCalledOnce()
    expect(mocks.setSessionHash).not.toHaveBeenCalled()
  })

  it("rejects missing and foreign origins and warns only in development", async () => {
    vi.stubEnv("DEV", true)
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined)
    await loadServiceWorker()
    const listener = listeners.get("message")

    listener?.(message({ origin: "" }))
    listener?.(message({ origin: "https://attacker.example" }))

    expect(warn).toHaveBeenCalledTimes(2)
    expect(warn).toHaveBeenCalledWith(
      "[SW] Rejected postMessage from foreign origin:",
      "https://attacker.example"
    )
  })

  it("silently rejects a foreign origin outside development", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined)
    await loadServiceWorker()

    listeners.get("message")?.(message({ origin: "https://attacker.example" }))

    expect(warn).not.toHaveBeenCalled()
  })

  it("dispatches supported messages and validates session hashes", async () => {
    await loadServiceWorker()
    const listener = listeners.get("message")
    const waitUntil = vi.fn()

    listener?.(message({ data: { type: SERVICE_WORKER_MESSAGE_TYPES.SKIP_WAITING } }))
    listener?.(
      message({
        data: {
          type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY,
          sessionHash: 42,
        },
      })
    )
    listener?.(
      message({
        data: {
          type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY,
          sessionHash: "",
        },
      })
    )
    listener?.(
      message({
        data: {
          type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY,
          sessionHash: "x".repeat(129),
        },
      })
    )
    listener?.(
      message({
        data: {
          type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY,
          sessionHash: "session-a",
        },
      })
    )
    listener?.(message({ data: { type: SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE }, waitUntil }))
    listener?.(
      message({
        data: { type: SERVICE_WORKER_MESSAGE_TYPES.PROCESS_NOTIFICATION_CLICK_QUEUE },
        waitUntil,
      })
    )
    listener?.(
      message({
        data: { type: SERVICE_WORKER_MESSAGE_TYPES.PROCESS_OFFLINE_QUEUES },
        waitUntil,
      })
    )
    listener?.(message())

    expect(scope.skipWaiting).toHaveBeenCalledTimes(2)
    expect(mocks.setSessionHash).toHaveBeenCalledOnce()
    expect(mocks.setSessionHash).toHaveBeenCalledWith("session-a")
    expect(waitUntil).toHaveBeenCalledTimes(3)
    expect(waitUntil).toHaveBeenCalledWith(expect.any(Promise))
  })

  it.each([
    "news-interaction:sync",
    "navigation-sync",
    "sync-offline-mutations",
    "offline-mutations-sync",
  ])("processes the %s background-sync tag", async (tag) => {
    await loadServiceWorker()
    const waitUntil = vi.fn()

    listeners.get("sync")?.({ tag, waitUntil })

    expect(waitUntil).toHaveBeenCalledWith(expect.any(Promise))
  })

  it("ignores unrelated background-sync tags", async () => {
    await loadServiceWorker()
    const waitUntil = vi.fn()

    listeners.get("sync")?.({ tag: "unrelated", waitUntil })

    expect(waitUntil).not.toHaveBeenCalled()
  })
})
