import { IDBFactory } from "fake-indexeddb"
import { openDB } from "idb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  NOTIFICATION_INTERACTIONS_DB_NAME,
  NOTIFICATION_INTERACTIONS_DB_VERSION,
} from "../../constants/notificationInteractionsDb"
import {
  addRecord,
  initOfflineQueue,
  processOfflineQueues,
  processPendingMutations,
  processPendingNavigations,
  processPendingReports,
  readPendingMutations,
  readPendingNavigations,
  readPendingReports,
  storePendingMutation,
  storePendingNavigation,
  storePendingReport,
  STORES,
} from "../offline"

vi.mock("../logger", () => ({ log: vi.fn(), warn: vi.fn(), error: vi.fn() }))

describe("AUD-375: legacy news records have no session owner", () => {
  beforeEach(async () => {
    vi.stubGlobal("indexedDB", new IDBFactory())
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)
    await initOfflineQueue()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it("retains unbound records without sending them under the current browser session", async () => {
    const records = [
      { url: "/api/v1/news/1/like", method: "POST", payload: {}, timestamp: 1 },
      {
        url: "/api/v1/news/1/comment",
        method: "POST",
        payload: { content: "unsent text" },
        timestamp: 2,
      },
      {
        url: "/api/v1/news/comments/1",
        method: "PATCH",
        payload: { content: "edited text" },
        timestamp: 3,
      },
      { url: "/api/v1/news/comments/2", method: "DELETE", payload: {}, timestamp: 4 },
    ]
    for (const record of records) await addRecord(STORES.NEWS_INTERACTION, record)
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 403 }))
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    const db = await openDB(NOTIFICATION_INTERACTIONS_DB_NAME, NOTIFICATION_INTERACTIONS_DB_VERSION)
    try {
      const retained = await db.getAll(STORES.NEWS_INTERACTION)
      expect(retained).toHaveLength(records.length)
      expect(retained.map(({ url }: { url: string }) => url)).toEqual(records.map(({ url }) => url))
      expect(fetchMock).not.toHaveBeenCalled()
    } finally {
      db.close()
    }
  })

  it("retains unbound navigation, report and mutation records in every processor", async () => {
    await storePendingNavigation({ url: "http://localhost/private-page", timestamp: 1 })
    await storePendingReport({
      url: "http://localhost/private-page",
      reportUrl: "http://localhost/api/v1/notifications/report",
      method: "POST",
      payload: { action: "click" },
      timestamp: 2,
    })
    await storePendingMutation({
      url: "http://localhost/api/v1/profile",
      method: "PATCH",
      payload: { text: "queued text" },
      headers: { "X-Test-Header": "kept" },
      mutationId: "mutation-one",
      idempotencyKey: "operation-one",
    })
    const before = {
      navigations: await readPendingNavigations(),
      reports: await readPendingReports(),
      mutations: await readPendingMutations(),
    }
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 403 }))
    const openWindow = vi.fn().mockResolvedValue(null)
    const postMessage = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    vi.stubGlobal("clients", { openWindow })
    vi.stubGlobal(
      "BroadcastChannel",
      class {
        postMessage = postMessage
        close() {}
      }
    )

    await processOfflineQueues()
    await processPendingNavigations()
    await processPendingReports()
    await processPendingMutations()

    expect.soft(fetchMock).not.toHaveBeenCalled()
    expect.soft(openWindow).not.toHaveBeenCalled()
    expect.soft(postMessage).not.toHaveBeenCalled()
    expect.soft(await readPendingNavigations()).toEqual(before.navigations)
    expect.soft(await readPendingReports()).toEqual(before.reports)
    expect.soft(await readPendingMutations()).toEqual(before.mutations)
  })

  it("keeps unbound records held even when a live window answers the replay-credential request", async () => {
    await storePendingNavigation({ url: "http://localhost/private-page", timestamp: 1 })
    await storePendingReport({
      url: "http://localhost/private-page",
      reportUrl: "http://localhost/api/v1/notifications/report",
      method: "POST",
      payload: { action: "click" },
      timestamp: 2,
    })
    await storePendingMutation({
      url: "http://localhost/api/v1/profile",
      method: "PATCH",
      payload: { text: "queued text" },
      mutationId: "mutation-live-window",
      idempotencyKey: "operation-live-window",
      timestamp: 3,
    })
    const before = {
      navigations: await readPendingNavigations(),
      reports: await readPendingReports(),
      mutations: await readPendingMutations(),
    }
    const answeringWindow = {
      postMessage: vi.fn((_message: unknown, transfer: MessagePort[]) => {
        transfer[0]?.postMessage({ csrfToken: "csrf-live", sessionNonce: "session-live" })
      }),
    }
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }))
    vi.stubGlobal("fetch", fetchMock)
    vi.stubGlobal("clients", { matchAll: vi.fn().mockResolvedValue([answeringWindow]) })

    await processOfflineQueues()

    expect(answeringWindow.postMessage).toHaveBeenCalledOnce()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(await readPendingNavigations()).toEqual(before.navigations)
    expect(await readPendingReports()).toEqual(before.reports)
    expect(await readPendingMutations()).toEqual(before.mutations)
  })
})
