/* eslint-disable @typescript-eslint/no-explicit-any */
import { IDBFactory } from "fake-indexeddb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  initOfflineQueue,
  storePendingNavigation,
  readPendingNavigations,
  storePendingReport,
  readPendingReports,
  sanitizeReportPayload,
  processPendingReports,
} from "../offline"

vi.mock("../logger", () => ({
  log: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}))

describe("Service Worker - Offline Storage & Sync", () => {
  let onlineSpy: any

  beforeEach(async () => {
    // Reset fakeIndexedDB before each test to guarantee fresh state
    const { structuredClone } = globalThis
    // globalThis.structuredClone needs to be present, fake-indexeddb uses it
    if (!structuredClone) {
      globalThis.structuredClone = (val) => JSON.parse(JSON.stringify(val))
    }

    if (globalThis.crypto) {
      globalThis.crypto.randomUUID = () => "mocked-uuid-1234" as any
    }

    onlineSpy = vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)

    await initOfflineQueue()
  })

  afterEach(async () => {
    if (onlineSpy) {
      onlineSpy.mockRestore()
    }
    vi.restoreAllMocks()

    // Reset fakeIndexedDB state synchronously to avoid hangs on deleteDatabase due to locks
    globalThis.indexedDB = new IDBFactory() as unknown as typeof globalThis.indexedDB
  })

  describe("Pending Navigations", () => {
    it("can store and read pending navigations", async () => {
      const nav1 = { url: "http://localhost/dashboard", timestamp: 1000 }
      const nav2 = { url: "http://localhost/profile", timestamp: 2000 }

      await storePendingNavigation(nav1)
      await storePendingNavigation(nav2)

      const pending = await readPendingNavigations()
      expect(pending).toHaveLength(2)
      expect(pending[0]).toMatchObject(nav1)
      expect(pending[1]).toMatchObject(nav2)
    })
  })

  describe("Pending Reports & Deduplication", () => {
    it("deduplicates idempotent requests (GET/PUT/DELETE) with same body & URL", async () => {
      const report = {
        url: "http://localhost/news",
        reportUrl: "http://localhost/api/news",
        timestamp: 1000,
        payload: { id: 1 },
        method: "PUT",
      }

      await storePendingReport(report)
      await storePendingReport(report) // duplicate attempt

      const pending = await readPendingReports()
      expect(pending).toHaveLength(1) // Should deduplicate
    })

    it("does not deduplicate non-idempotent requests (POST)", async () => {
      const report = {
        url: "http://localhost/news",
        reportUrl: "http://localhost/api/news",
        timestamp: 1000,
        payload: { text: "hello" },
        method: "POST",
      }

      await storePendingReport(report)
      await storePendingReport(report)

      const pending = await readPendingReports()
      expect(pending).toHaveLength(2) // Both enqueued with distinct random UUIDs
      expect(pending[0].idempotencyKey).toBe("mocked-uuid-1234")
    })
  })

  describe("Sanitize Report Payload", () => {
    it("strips blocked prototype keys", () => {
      const payload = {
        title: "Test",
        __proto__: { admin: true },
        nested: {
          constructor: "blocked",
          valid: 123,
        },
      }

      const sanitized: any = sanitizeReportPayload(payload)
      expect(sanitized.title).toBe("Test")
      expect(sanitized.__proto__).toBeUndefined()
      expect(sanitized.nested.constructor).toBeUndefined()
      expect(sanitized.nested.valid).toBe(123)
    })

    it("truncates arrays and caps recursion depth", () => {
      const hugeArray = Array.from({ length: 200 }, (_, i) => i)
      const sanitizedArray: any = sanitizeReportPayload(hugeArray)
      expect(sanitizedArray).toHaveLength(100) // Truncated to MAX_ARRAY_LENGTH

      // Recursive objects deeper than MAX_SANITIZE_DEPTH
      const deepObj: any = { depth: 0 }
      let cur = deepObj
      for (let i = 1; i <= 12; i++) {
        cur.next = { depth: i }
        cur = cur.next
      }

      const sanitizedDeep: any = sanitizeReportPayload(deepObj)
      let check = sanitizedDeep
      for (let i = 0; i <= 10; i++) {
        check = check.next
      }
      expect(check).toBe("[truncated]")
    })
  })

  describe("Background Sync - Processing queues", () => {
    it("fetches and deletes pending reports when online and successful", async () => {
      const report = {
        url: "http://localhost/page",
        reportUrl: "http://localhost/api/report",
        timestamp: 1000,
        payload: { event: "click" },
        method: "POST",
      }

      await storePendingReport(report)

      // Mock successful fetch
      const fetchMock = vi.fn().mockResolvedValue({ ok: true })
      vi.stubGlobal("fetch", fetchMock)

      await processPendingReports()

      expect(fetchMock).toHaveBeenCalledTimes(1)
      expect(fetchMock.mock.calls[0]?.[0]).toBe("http://localhost/api/report")

      const remaining = await readPendingReports()
      expect(remaining).toHaveLength(0) // Successful reports are deleted
    })

    it("does not delete pending reports if fetch fails", async () => {
      const report = {
        url: "http://localhost/page",
        reportUrl: "http://localhost/api/report",
        timestamp: 1000,
        payload: { event: "click" },
        method: "POST",
      }

      await storePendingReport(report)

      // Mock failed fetch
      const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 500 })
      vi.stubGlobal("fetch", fetchMock)

      await processPendingReports()

      const remaining = await readPendingReports()
      expect(remaining).toHaveLength(1) // Kept for retry
    })
  })
})
