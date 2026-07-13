import { IDBFactory } from "fake-indexeddb"
import { afterEach, beforeEach, describe, expect, it, vi, type SpyInstance } from "vitest"
import {
  initOfflineQueue,
  storePendingNavigation,
  storePendingReport,
  readPendingReports,
  processPendingReports,
} from "../offline"

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
  let onlineSpy: SpyInstance

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

    it("preserves offline reports during 24+ hour offline periods and flushes them when online", async () => {
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

      // 6. Flush queue
      await processPendingReports()

      // Fetch should be called and queue cleared
      expect(fetchMock).toHaveBeenCalledTimes(1)
      stored = await readPendingReports()
      expect(stored).toHaveLength(0)
    })
  })
})
