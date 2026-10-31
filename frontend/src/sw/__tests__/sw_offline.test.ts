import { IDBFactory } from "fake-indexeddb"
import { openDB } from "idb"
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest"
import {
  addRecord,
  initOfflineQueue,
  processOfflineQueues,
  storePendingNavigation,
  storePendingReport,
  readPendingReports,
  readPendingNavigations,
  processPendingReports,
  processPendingNavigations,
  STORES,
} from "../offline"
import { warn } from "../logger"

vi.mock("../logger", () => ({
  log: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}))

vi.mock("idb", async (importOriginal) => {
  const original = await importOriginal<Record<string, unknown>>()
  return {
    ...original,
    openDB: vi.fn((...args: unknown[]) => {
      const mockFn = (globalThis as Record<string, unknown>).__mock_openDB_fn__ as (
        ...args: unknown[]
      ) => unknown
      if (mockFn) {
        return mockFn(...args)
      }
      const originalOpenDB = original.openDB as (...args: unknown[]) => unknown
      return originalOpenDB(...args)
    }),
  }
})

describe("Service Worker — Offline / Database Failures & Network Outage", () => {
  let onlineSpy: MockInstance

  beforeEach(async () => {
    const { structuredClone } = globalThis
    if (!structuredClone) {
      globalThis.structuredClone = (val) => JSON.parse(JSON.stringify(val))
    }
    onlineSpy = vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)
    ;(globalThis as Record<string, unknown>).__mock_openDB_fn__ = null
    await initOfflineQueue()
  })

  afterEach(async () => {
    if (onlineSpy) {
      onlineSpy.mockRestore()
    }
    ;(globalThis as Record<string, unknown>).__mock_openDB_fn__ = null
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    globalThis.indexedDB = new IDBFactory() as unknown as typeof globalThis.indexedDB
  })

  describe("IndexedDB Write Failures (QuotaExceededError)", () => {
    it("handles QuotaExceededError when storing pending navigation gracefully", async () => {
      ;(globalThis as Record<string, unknown>).__mock_openDB_fn__ = async () => {
        return {
          add: vi
            .fn()
            .mockRejectedValue(
              new DOMException(
                "The write operation exceeded the remaining storage quota.",
                "QuotaExceededError"
              )
            ),
          close: vi.fn(),
        }
      }

      await expect(
        storePendingNavigation({ url: "http://localhost/home", timestamp: Date.now() })
      ).rejects.toThrowError(/storage quota/)
    })

    it("handles QuotaExceededError when storing pending reports", async () => {
      ;(globalThis as Record<string, unknown>).__mock_openDB_fn__ = async () => {
        return {
          add: vi.fn().mockRejectedValue(new DOMException("Storage full", "QuotaExceededError")),
          close: vi.fn(),
        }
      }

      await expect(
        storePendingReport({
          url: "http://localhost/news",
          reportUrl: "http://localhost/api/news",
          timestamp: Date.now(),
          payload: { text: "post text" },
          method: "POST",
        })
      ).rejects.toThrowError(/Storage full/)
    })
  })

  describe("Long-term network outage (> 24 hours)", () => {
    beforeEach(() => {
      vi.useFakeTimers({ toFake: ["Date"] })
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    it("preserves offline reports during a 24+ hour outage and after reconnection", async () => {
      const report = {
        url: "http://localhost/page",
        reportUrl: "http://localhost/api/report",
        timestamp: Date.now(),
        payload: { event: "click" },
        method: "POST",
      }

      // 1. Store report while online
      await storePendingReport(report)
      let stored = await readPendingReports()
      expect(stored).toHaveLength(1)

      // 2. Network goes offline
      onlineSpy.mockReturnValue(false)

      // 3. Fast forward time by 25 hours (more than 24 hours)
      vi.advanceTimersByTime(25 * 60 * 60 * 1000)

      // 4. Try processing queues while offline
      const fetchMock = vi.fn().mockResolvedValue({ ok: true })
      vi.stubGlobal("fetch", fetchMock)

      await processPendingReports()

      // Should not call fetch because client is offline
      expect(fetchMock).not.toHaveBeenCalled()

      // Messages must be preserved in the queue
      stored = await readPendingReports()
      expect(stored).toHaveLength(1)

      // 5. Network comes back online
      onlineSpy.mockReturnValue(true)

      // 6. The legacy report has no session owner, even after reconnection.
      await processPendingReports()

      expect(fetchMock).not.toHaveBeenCalled()
      stored = await readPendingReports()
      expect(stored).toHaveLength(1)
      expect(stored[0]).toMatchObject(report)
    })
  })

  it("retains report records without optional method or idempotency key", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 })
    vi.stubGlobal("fetch", fetchMock)
    await addRecord(STORES.REPORT, {
      url: "http://localhost/page",
      reportUrl: "http://localhost/api/report-get",
      timestamp: Date.now(),
      payload: null,
    })

    await processPendingReports()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(await readPendingReports()).toEqual([
      expect.objectContaining({ reportUrl: "http://localhost/api/report-get", payload: null }),
    ])
  })

  it("does not open any offline queue while the service worker is offline", async () => {
    onlineSpy.mockReturnValue(false)
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)

    await processOfflineQueues()

    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("retains pending navigations with and without an available window client", async () => {
    const openWindow = vi.fn().mockRejectedValue(new Error("window blocked"))
    vi.stubGlobal("clients", { openWindow })
    await storePendingNavigation({ url: "http://localhost/first", timestamp: 1 })

    await processPendingNavigations()

    expect(openWindow).not.toHaveBeenCalled()

    vi.stubGlobal("clients", undefined)
    await storePendingNavigation({ url: "http://localhost/second", timestamp: 2 })
    await processPendingNavigations()
    expect(openWindow).not.toHaveBeenCalled()
    expect(await readPendingNavigations()).toEqual([
      expect.objectContaining({ url: "http://localhost/first", timestamp: 1 }),
      expect.objectContaining({ url: "http://localhost/second", timestamp: 2 }),
    ])
  })

  it("keeps pending navigations untouched while offline", async () => {
    onlineSpy.mockReturnValue(false)
    await storePendingNavigation({ url: "http://localhost/offline", timestamp: 1 })

    await processPendingNavigations()

    onlineSpy.mockReturnValue(true)
    const openWindow = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal("clients", { openWindow })
    await processPendingNavigations()
    expect(openWindow).not.toHaveBeenCalled()
    expect(await readPendingNavigations()).toEqual([
      expect.objectContaining({ url: "http://localhost/offline", timestamp: 1 }),
    ])
  })

  it("keeps unbound reports without attempting or logging a network failure", async () => {
    await storePendingReport({
      url: "http://localhost/page",
      reportUrl: "http://localhost/api/rejected-report",
      timestamp: Date.now(),
      method: "POST",
    })
    const failure = new Error("network unavailable")
    const fetchMock = vi.fn().mockRejectedValue(failure)
    vi.stubGlobal("fetch", fetchMock)

    await processPendingReports()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(warn).not.toHaveBeenCalled()
    expect(await readPendingReports()).toHaveLength(1)
  })

  it("retains legacy news interactions without network requests", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, status: 200 })
      .mockResolvedValueOnce({ ok: false, status: 500 })
    vi.stubGlobal("fetch", fetchMock)
    await addRecord(STORES.NEWS_INTERACTION, {
      url: "http://localhost/api/news/read",
      method: "GET",
      payload: { id: "read-1" },
    })
    await addRecord(STORES.NEWS_INTERACTION, {
      url: "http://localhost/api/news/bookmark",
      method: "POST",
      payload: { id: "bookmark-1" },
    })

    await processOfflineQueues()

    expect(fetchMock).not.toHaveBeenCalled()
    const db = await openDB("notification-interactions", 4)
    expect(await db.getAll(STORES.NEWS_INTERACTION)).toEqual([
      expect.objectContaining({ method: "GET", payload: { id: "read-1" } }),
      expect.objectContaining({ method: "POST", payload: { id: "bookmark-1" } }),
    ])
    db.close()
  })

  it("does not replay or log an unbound news interaction", async () => {
    const failure = new Error("news endpoint unavailable")
    const fetchMock = vi.fn().mockRejectedValue(failure)
    vi.stubGlobal("fetch", fetchMock)
    await addRecord(STORES.NEWS_INTERACTION, {
      url: "http://localhost/api/news/rejected",
      method: "POST",
      payload: { id: "rejected" },
    })

    await processOfflineQueues()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(warn).not.toHaveBeenCalled()
    const db = await openDB("notification-interactions", 4)
    expect(await db.getAll(STORES.NEWS_INTERACTION)).toEqual([
      expect.objectContaining({ payload: { id: "rejected" } }),
    ])
    db.close()
  })
})
