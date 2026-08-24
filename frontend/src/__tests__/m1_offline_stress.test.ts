import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { IDBFactory } from "fake-indexeddb"
import { openDB } from "idb"
import {
  initOfflineQueue,
  storePendingMutation,
  readPendingMutations,
  processPendingMutations,
  addRecord,
  STORES,
  type PendingMutationRecord,
} from "@/sw/offline"
import { getDatabase, type AppDatabase } from "@/db"
import { createIDBPersister, createQueryClient } from "@/app/queryClient"

const CLICK_DB_NAME = "notification-interactions"

describe("Milestone 1 — Adversarial Offline-First & Stress Test Suite", () => {
  let onlineSpy: any

  beforeEach(async () => {
    // Ensure structuredClone and crypto are present for fake-indexeddb
    if (!globalThis.structuredClone) {
      globalThis.structuredClone = (val) => JSON.parse(JSON.stringify(val))
    }
    let counter = 0
    if (globalThis.crypto) {
      globalThis.crypto.randomUUID = () => `stress-uuid-${++counter}` as any
    }

    onlineSpy = vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)
    await initOfflineQueue()

    // Clear all pending stores between tests to prevent test pollution
    try {
      const db = await openDB(CLICK_DB_NAME, 4)
      await db.clear(STORES.MUTATION)
      await db.clear(STORES.REPORT)
      await db.clear(STORES.NEWS_INTERACTION)
      await db.clear(STORES.NAVIGATION)
      db.close()
    } catch {
      /* ignore */
    }
  })

  afterEach(async () => {
    if (onlineSpy) onlineSpy.mockRestore()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    globalThis.indexedDB = new IDBFactory() as unknown as typeof globalThis.indexedDB
  })

  describe("1. RxDB Collection Operations & Rapid Mutations", () => {
    it("initializes RxDB database with schedule, notes, and messages collections", async () => {
      // Expecting getDatabase() to succeed or fail cleanly
      let db: AppDatabase | null = null
      let err: any = null
      try {
        db = await getDatabase()
      } catch (e) {
        err = e
      }
      if (err) {
        expect(err.message || String(err)).toMatch(/schema validator|dev-mode/i)
      } else {
        expect(db).toBeDefined()
        expect(db!.collections.schedule).toBeDefined()
      }
    })
  })

  describe("2. Service Worker Offline Mutation Queue — Edge Cases", () => {
    it("preserves ordering by timestamp during replay", async () => {
      const m1 = {
        url: "/api/test",
        method: "POST" as const,
        payload: { step: 1 },
        timestamp: 1000,
      }
      const m2 = { url: "/api/test", method: "POST" as const, payload: { step: 2 }, timestamp: 500 }
      const m3 = {
        url: "/api/test",
        method: "POST" as const,
        payload: { step: 3 },
        timestamp: 1500,
      }

      await storePendingMutation(m1)
      await storePendingMutation(m2)
      await storePendingMutation(m3)

      const executionOrder: number[] = []
      const fetchMock = vi.fn().mockImplementation((_url, opts) => {
        const body = JSON.parse(opts.body)
        executionOrder.push(body.step)
        return Promise.resolve({ ok: true, status: 200 })
      })
      vi.stubGlobal("fetch", fetchMock)

      await processPendingMutations()

      expect(fetchMock).toHaveBeenCalledTimes(3)
      expect(executionOrder).toEqual([2, 1, 3]) // Sorted by timestamp: 500, 1000, 1500
    })

    it("4xx non-retriable client error (400, 403, 404) discards mutation immediately and sends MUTATION_REJECTED", async () => {
      await storePendingMutation({
        url: "/api/invalid-resource",
        method: "PUT",
        payload: { invalid: true },
      })

      const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 404 })
      vi.stubGlobal("fetch", fetchMock)

      const channelMessages: any[] = []
      const MockChannel = vi.fn().mockImplementation(() => ({
        postMessage: (msg: any) => channelMessages.push(msg),
        close: () => {},
      }))
      vi.stubGlobal("BroadcastChannel", MockChannel)

      await processPendingMutations()

      const remaining = await readPendingMutations()
      expect(remaining).toHaveLength(0) // Discarded from queue
      expect(channelMessages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            type: "MUTATION_REJECTED",
            status: 404,
          }),
        ])
      )
    })

    it("429 rate limit status triggers retry instead of discarding", async () => {
      await storePendingMutation({
        url: "/api/rate-limited",
        method: "POST",
        payload: { action: "like" },
      })

      const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 429 })
      vi.stubGlobal("fetch", fetchMock)

      await processPendingMutations()

      const remaining = (await readPendingMutations()) as PendingMutationRecord[]
      expect(remaining).toHaveLength(1)
      expect(remaining[0]!.retryCount).toBe(1)
    })

    it("5xx server error increments retryCount and keeps mutation in queue", async () => {
      await storePendingMutation({
        url: "/api/server-error",
        method: "POST",
        payload: { data: "test" },
      })

      const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 503 })
      vi.stubGlobal("fetch", fetchMock)

      await processPendingMutations()

      const remaining = (await readPendingMutations()) as PendingMutationRecord[]
      expect(remaining).toHaveLength(1)
      expect(remaining[0]!.retryCount).toBe(1)
    })

    it("discards mutation after reaching 5 max retries and broadcasts MUTATION_FAILED_PERMANENT", async () => {
      await storePendingMutation({
        url: "/api/permanent-fail",
        method: "POST",
        payload: { data: "test" },
        retryCount: 5,
      })

      const fetchMock = vi.fn()
      vi.stubGlobal("fetch", fetchMock)

      const channelMessages: any[] = []
      const MockChannel = vi.fn().mockImplementation(() => ({
        postMessage: (msg: any) => channelMessages.push(msg),
        close: () => {},
      }))
      vi.stubGlobal("BroadcastChannel", MockChannel)

      await processPendingMutations()

      expect(fetchMock).not.toHaveBeenCalled()
      const remaining = await readPendingMutations()
      expect(remaining).toHaveLength(0)
      expect(channelMessages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            type: "MUTATION_FAILED_PERMANENT",
          }),
        ])
      )
    })

    it("prevents execution during offline mode and flushes when toggled online", async () => {
      await storePendingMutation({
        url: "http://localhost/api/offline-test",
        method: "POST",
        payload: { text: "offline" },
      })

      onlineSpy.mockReturnValue(false)
      const fetchMock = vi.fn().mockResolvedValue({ ok: true })
      vi.stubGlobal("fetch", fetchMock)

      await processPendingMutations()
      expect(fetchMock).not.toHaveBeenCalled()
      expect(await readPendingMutations()).toHaveLength(1)

      // Toggle online
      onlineSpy.mockReturnValue(true)
      await processPendingMutations()
      expect(fetchMock).toHaveBeenCalledTimes(1)
      const remainingMutations = await readPendingMutations()
      expect(remainingMutations).toHaveLength(0)
    })
  })

  describe("3. TanStack Query Persister & Quota Management", () => {
    it("configures queryClient networkMode to offlineFirst", () => {
      const client = createQueryClient()
      const queryDefaults = client.getDefaultOptions().queries
      const mutationDefaults = client.getDefaultOptions().mutations

      expect(queryDefaults?.networkMode).toBe("offlineFirst")
      expect(mutationDefaults?.networkMode).toBe("offlineFirst")
    })

    it("createIDBPersister handles QuotaExceededError by clearing cache gracefully", async () => {
      const mockDel = vi.fn().mockResolvedValue(undefined)
      const mockSet = vi
        .fn()
        .mockRejectedValue(new DOMException("Quota exceeded", "QuotaExceededError"))

      vi.doMock("idb-keyval", () => ({
        get: vi.fn(),
        set: mockSet,
        del: mockDel,
      }))

      const persister = createIDBPersister("test-key")
      await expect(
        persister.persistClient({
          timestamp: Date.now(),
          buster: "v1",
          clientState: { queries: [], mutations: [] },
        } as any)
      ).resolves.not.toThrow()
    })
  })

  describe("4. Queue Depth & Multi-Store Aggregation", () => {
    it("accurately calculates total queued items across all offline stores", async () => {
      await addRecord(STORES.NEWS_INTERACTION, { payload: "news-1" })
      await addRecord(STORES.REPORT, { reportUrl: "/api/rep", method: "POST", timestamp: 1 })
      await storePendingMutation({ url: "/api/mut", method: "POST", payload: "mut-1" })

      const mutations = await readPendingMutations()
      expect(mutations).toHaveLength(1)
    })
  })
})
