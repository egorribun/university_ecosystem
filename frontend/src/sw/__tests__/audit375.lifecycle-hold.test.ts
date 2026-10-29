import { IDBFactory } from "fake-indexeddb"
import { openDB } from "idb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  NOTIFICATION_INTERACTIONS_DB_NAME,
  NOTIFICATION_INTERACTIONS_DB_VERSION,
} from "../../constants/notificationInteractionsDb"
import { SERVICE_WORKER_MESSAGE_TYPES } from "../../constants/serviceWorkerMessages"

vi.mock("workbox-core", () => ({ clientsClaim: vi.fn() }))
vi.mock("../api", () => ({
  initApiCaching: vi.fn(),
  clearSessionCaches: vi.fn(),
  purgeLegacyCaches: vi.fn().mockResolvedValue(undefined),
  setSessionHash: vi.fn(),
}))
vi.mock("../logger", () => ({ log: vi.fn(), error: vi.fn() }))
vi.mock("../media", () => ({ initMediaCaching: vi.fn(), handleMediaRequest: vi.fn() }))
vi.mock("../precaching", () => ({ initPrecaching: vi.fn() }))
vi.mock("../push", () => ({ initPushHandlers: vi.fn() }))

type Listener = (event: Record<string, unknown>) => void

function makeScope() {
  const listeners = new Map<string, Listener>()
  const scope = {
    addEventListener: vi.fn((type: string, listener: Listener) => listeners.set(type, listener)),
    clients: { openWindow: vi.fn().mockResolvedValue(null) },
    location: new URL("https://app.example/sw.js"),
    navigator: { onLine: true },
    __SW_TESTING__: undefined as unknown,
  }
  return { scope, listeners }
}

async function startWorker() {
  vi.resetModules()
  const worker = makeScope()
  vi.stubGlobal("self", worker.scope)
  await import("../../sw")
  await vi.waitFor(() => expect(worker.scope.__SW_TESTING__).toBeDefined())
  return worker
}

function sendMessage(
  listeners: Map<string, Listener>,
  type: string = SERVICE_WORKER_MESSAGE_TYPES.PROCESS_OFFLINE_QUEUES
) {
  const waitUntil = vi.fn<(promise: Promise<void>) => void>()
  listeners.get("message")?.({
    data: { type },
    source: { url: "https://app.example/" },
    origin: "https://app.example",
    waitUntil,
  })
  expect(waitUntil).toHaveBeenCalledOnce()
  const promise = waitUntil.mock.calls[0]?.[0]
  if (!promise) throw new Error("message did not extend worker lifetime")
  return promise
}

function sendSync(listeners: Map<string, Listener>, tag: string) {
  const waitUntil = vi.fn<(promise: Promise<void>) => void>()
  listeners.get("sync")?.({ tag, waitUntil })
  expect(waitUntil).toHaveBeenCalledOnce()
  const promise = waitUntil.mock.calls[0]?.[0]
  if (!promise) throw new Error("sync did not extend worker lifetime")
  return promise
}

describe("AUD-375: worker lifecycle keeps legacy queues on hold", () => {
  beforeEach(() => {
    vi.stubGlobal("indexedDB", new IDBFactory())
    vi.stubEnv("MODE", "production")
    vi.stubEnv("DEV", false)
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it("retains every legacy store across bootstrap, message, and sync triggers", async () => {
    const offline = await import("../offline")
    await offline.storePendingNavigation({ url: "/target", timestamp: 1 })
    await offline.storePendingReport({
      url: "/target",
      reportUrl: "/api/v1/notifications/click",
      timestamp: 2,
      payload: { action: "open" },
    })
    await offline.addRecord(offline.STORES.NEWS_INTERACTION, {
      url: "/api/v1/news/1/like",
      method: "POST",
      payload: {},
      timestamp: 3,
    })
    await offline.storePendingMutation({
      url: "/api/v1/profile",
      method: "PATCH",
      payload: { displayName: "queued" },
      mutationId: "queued-mutation",
      idempotencyKey: "queued-operation",
      timestamp: 4,
    })
    const db = await openDB(NOTIFICATION_INTERACTIONS_DB_NAME, NOTIFICATION_INTERACTIONS_DB_VERSION)
    const stores = Object.values(offline.STORES)
    const before = await Promise.all(stores.map((store) => db.getAll(store)))
    expect(before.map((records) => records.length)).toEqual([1, 1, 1, 1])
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 403 }))
    const openWindow = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    vi.stubGlobal("clients", { openWindow })

    try {
      const worker = await startWorker()
      await Promise.all([
        sendMessage(worker.listeners),
        sendMessage(worker.listeners, SERVICE_WORKER_MESSAGE_TYPES.PROCESS_NOTIFICATION_CLICK_QUEUE),
        sendSync(worker.listeners, "navigation-sync"),
        sendSync(worker.listeners, "news-interaction:sync"),
        sendSync(worker.listeners, "sync-offline-mutations"),
        sendSync(worker.listeners, "offline-mutations-sync"),
      ])

      expect(fetchMock).not.toHaveBeenCalled()
      expect(openWindow).not.toHaveBeenCalled()
      expect(worker.scope.clients.openWindow).not.toHaveBeenCalled()
      expect(await Promise.all(stores.map((store) => db.getAll(store)))).toEqual(before)
    } finally {
      db.close()
    }
  })

  it("retains a queue when separately evaluated current worker modules are triggered together", async () => {
    const offline = await import("../offline")
    await offline.storePendingMutation({
      url: "/api/v1/profile",
      method: "PATCH",
      payload: { displayName: "queued" },
      mutationId: "queued-mutation",
      idempotencyKey: "queued-operation",
      timestamp: 1,
    })
    const db = await openDB(NOTIFICATION_INTERACTIONS_DB_NAME, NOTIFICATION_INTERACTIONS_DB_VERSION)
    const before = await db.getAll(offline.STORES.MUTATION)
    expect(before).toHaveLength(1)
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 403 }))
    vi.stubGlobal("fetch", fetchMock)

    try {
      const first = await startWorker()
      await sendMessage(first.listeners)
      const second = await startWorker()
      await Promise.all([
        sendSync(first.listeners, "sync-offline-mutations"),
        sendMessage(second.listeners),
      ])

      expect(fetchMock).not.toHaveBeenCalled()
      expect(await db.getAll(offline.STORES.MUTATION)).toEqual(before)
    } finally {
      db.close()
    }
  })
})
