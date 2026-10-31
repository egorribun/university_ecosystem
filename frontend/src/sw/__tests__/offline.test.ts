import { IDBFactory } from "fake-indexeddb"
import { openDB } from "idb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  initOfflineQueue,
  storePendingNavigation,
  readPendingNavigations,
  storePendingReport,
  readPendingReports,
  storePendingMutation,
  readPendingMutations,
  sanitizeReportPayload,
  processPendingReports,
  addRecord,
  processOfflineQueues,
  STORES,
} from "../offline"

vi.mock("../logger", () => ({
  log: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}))

async function readPendingNews() {
  const db = await openDB("notification-interactions", 4)
  try {
    return await db.getAll(STORES.NEWS_INTERACTION)
  } finally {
    db.close()
  }
}

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

    it("deduplicates bodyless idempotent requests using a null payload", async () => {
      const report = {
        url: "http://localhost/news",
        reportUrl: "http://localhost/api/news",
        timestamp: 1000,
        method: "GET",
      }

      await storePendingReport(report)
      await storePendingReport(report)

      const pending = await readPendingReports()
      expect(pending).toHaveLength(1)
      expect(pending[0]).toMatchObject({
        method: "GET",
        dedupeKey: expect.stringMatching(/^[a-f0-9]{64}$/),
      })
    })

    it("keeps different idempotent methods distinct for the same URL and payload", async () => {
      const baseReport = {
        url: "http://localhost/news",
        reportUrl: "http://localhost/api/news/1",
        timestamp: 1000,
        payload: { read: true },
      }

      await storePendingReport({ ...baseReport, method: "put" })
      await storePendingReport({ ...baseReport, method: "DELETE" })

      const pending = await readPendingReports()
      expect(pending.map((record) => record.method)).toEqual(["PUT", "DELETE"])
      expect(new Set(pending.map((record) => record.dedupeKey)).size).toBe(2)
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

    it("defaults a report without an explicit method to POST", async () => {
      await storePendingReport({
        url: "http://localhost/news",
        reportUrl: "http://localhost/api/news",
        timestamp: 1000,
      })

      const [pending] = await readPendingReports()
      expect(pending).toMatchObject({ method: "POST", idempotencyKey: "mocked-uuid-1234" })
    })

    it("creates the complete queue schema and mutation indexes", async () => {
      const db = await new Promise<IDBDatabase>((resolve, reject) => {
        const request = indexedDB.open("notification-interactions", 4)
        request.onsuccess = () => resolve(request.result)
        request.onerror = () => reject(request.error)
      })

      expect([...db.objectStoreNames]).toEqual(expect.arrayContaining(Object.values(STORES)))
      const reports = db.transaction(STORES.REPORT, "readonly").objectStore(STORES.REPORT)
      expect([...reports.indexNames]).toContain("dedupeKey")

      const mutations = db.transaction(STORES.MUTATION, "readonly").objectStore(STORES.MUTATION)
      expect([...mutations.indexNames]).toEqual(
        expect.arrayContaining(["mutationId", "category", "dedupeKey"])
      )
      expect(mutations.index("mutationId").unique).toBe(true)
      expect(mutations.index("category").unique).toBe(false)
      expect(mutations.index("dedupeKey").unique).toBe(false)
      db.close()
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

    it("drops function-valued report fields", () => {
      const sanitized = sanitizeReportPayload({
        keep: "value",
        callback: () => "not serializable",
      }) as Record<string, unknown>

      expect(sanitized).toEqual({ keep: "value" })
      expect(sanitized).not.toHaveProperty("callback")
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
    it("retains an unbound report even when a successful response is available", async () => {
      const report = {
        url: "http://localhost/page",
        reportUrl: "http://localhost/api/report",
        timestamp: 1000,
        payload: { event: "click" },
        method: "POST",
      }

      await storePendingReport(report)

      const fetchMock = vi.fn().mockResolvedValue({ ok: true })
      vi.stubGlobal("fetch", fetchMock)

      await processPendingReports()

      expect(fetchMock).not.toHaveBeenCalled()

      const remaining = await readPendingReports()
      expect(remaining).toHaveLength(1)
      expect(remaining[0]).toMatchObject(report)
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

      expect(fetchMock).not.toHaveBeenCalled()
      const remaining = await readPendingReports()
      expect(remaining).toHaveLength(1)
      expect(remaining[0]).toMatchObject(report)
    })

    it.each(["GET", "HEAD"])("retains unbound %s reports without sending", async (method) => {
      await storePendingReport({
        url: "http://localhost/page",
        reportUrl: "http://localhost/api/report",
        timestamp: 1000,
        payload: { stale: true },
        method,
      })
      const fetchMock = vi.fn().mockResolvedValue({ ok: true })
      vi.stubGlobal("fetch", fetchMock)

      await processPendingReports()

      expect(fetchMock).not.toHaveBeenCalled()
      expect(await readPendingReports()).toEqual([
        expect.objectContaining({ method, payload: { stale: true } }),
      ])
    })

    it("preserves idempotency keys and JSON payloads without sending", async () => {
      await storePendingReport({
        url: "http://localhost/page",
        reportUrl: "http://localhost/api/report-with-headers",
        timestamp: 1000,
        payload: { event: "click" },
        method: "POST",
      })
      const [stored] = await readPendingReports()
      const fetchMock = vi.fn().mockResolvedValue({ ok: true })
      vi.stubGlobal("fetch", fetchMock)

      await processPendingReports()

      expect(fetchMock).not.toHaveBeenCalled()
      expect(await readPendingReports()).toEqual([stored])
      expect(stored).toMatchObject({
        method: "POST",
        payload: { event: "click" },
        idempotencyKey: expect.any(String),
      })
    })
  })

  describe("Session binding (AUD-375)", () => {
    it("records the supplied session nonce on navigations, reports and mutations", async () => {
      await storePendingNavigation({
        url: "http://localhost/a",
        timestamp: 1,
        sessionNonce: "session-A",
      })
      await storePendingReport({
        url: "http://localhost/a",
        reportUrl: "http://localhost/api/a",
        timestamp: 2,
        method: "PUT",
        payload: { a: 1 },
        sessionNonce: "session-A",
      })
      await storePendingMutation({
        url: "http://localhost/api/m",
        method: "PATCH",
        payload: {},
        mutationId: "m-session",
        idempotencyKey: "k-session",
        timestamp: 3,
        sessionNonce: "session-A",
      })

      expect(await readPendingNavigations()).toEqual([
        expect.objectContaining({ sessionNonce: "session-A" }),
      ])
      expect(await readPendingReports()).toEqual([
        expect.objectContaining({ sessionNonce: "session-A" }),
      ])
      expect(await readPendingMutations()).toEqual([
        expect.objectContaining({ sessionNonce: "session-A" }),
      ])
    })

    it("leaves a record unbound when the caller supplies no nonce or an explicit null", async () => {
      await storePendingNavigation({ url: "http://localhost/b", timestamp: 1 })
      await storePendingReport({
        url: "http://localhost/b",
        reportUrl: "http://localhost/api/b",
        timestamp: 2,
        sessionNonce: null,
      })
      await storePendingMutation({
        url: "http://localhost/api/b",
        method: "POST",
        payload: {},
        mutationId: "m-unbound",
        idempotencyKey: "k-unbound",
        timestamp: 3,
      })

      expect(await readPendingNavigations()).toEqual([
        expect.objectContaining({ sessionNonce: null }),
      ])
      expect(await readPendingReports()).toEqual([expect.objectContaining({ sessionNonce: null })])
      expect(await readPendingMutations()).toEqual([
        expect.objectContaining({ sessionNonce: null }),
      ])
    })

    it("keeps identical idempotent reports from different sessions distinct", async () => {
      const report = {
        url: "http://localhost/news",
        reportUrl: "http://localhost/api/news/1",
        timestamp: 1000,
        payload: { read: true },
        method: "PUT",
      }

      await storePendingReport({ ...report, sessionNonce: "session-A" })
      await storePendingReport({ ...report, sessionNonce: "session-B" })
      await storePendingReport({ ...report, sessionNonce: "session-A" })

      expect((await readPendingReports()).map((record) => record.sessionNonce)).toEqual([
        "session-A",
        "session-B",
      ])
    })
  })

  describe("Background Sync - News interactions", () => {
    it("retains a legacy interaction with a missing method without sending", async () => {
      await addRecord(STORES.NEWS_INTERACTION, {
        url: "http://localhost/api/news/default-method",
        payload: { id: "default-method" },
      })
      const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 })
      vi.stubGlobal("fetch", fetchMock)

      await processOfflineQueues()

      expect(fetchMock).not.toHaveBeenCalled()
      expect(await readPendingNews()).toEqual([
        expect.objectContaining({
          url: "http://localhost/api/news/default-method",
          payload: { id: "default-method" },
        }),
      ])
    })

    it.each([400, 404])(
      "retains a legacy interaction regardless of a possible %s",
      async (status) => {
        await addRecord(STORES.NEWS_INTERACTION, {
          url: `http://localhost/api/news/drop-${status}`,
          method: "POST",
          payload: { status },
        })
        const fetchMock = vi.fn().mockResolvedValue({ ok: false, status })
        vi.stubGlobal("fetch", fetchMock)

        await processOfflineQueues()

        expect(fetchMock).not.toHaveBeenCalled()
        expect(await readPendingNews()).toEqual([
          expect.objectContaining({ method: "POST", payload: { status } }),
        ])
      }
    )
  })
})
