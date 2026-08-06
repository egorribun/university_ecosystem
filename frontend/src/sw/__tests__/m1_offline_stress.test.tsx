import { render, screen, fireEvent } from "@testing-library/react"
import { IDBFactory } from "fake-indexeddb"
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest"
import {
  initOfflineQueue,
  storePendingMutation,
  readPendingMutations,
  processPendingMutations,
} from "../offline"
import { enqueueOfflineMutation } from "../../api/offlineMutationQueue"
import { SyncStatus } from "../../components/feedback/SyncStatus"
import * as useSyncStatusModule from "../../hooks/useSyncStatus"

// Mock logger
vi.mock("../logger", () => ({
  log: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}))

// Mock react-i18next
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: any) => {
      if (key === "common:sync.offline") return `Offline (${options?.count ?? 0} queued)`
      if (key === "common:sync.online") return "All synced"
      return options?.defaultValue || key
    },
  }),
}))

describe("Milestone 1 — Offline-First & SyncStatus Adversarial Stress Tests", () => {
  let onlineSpy: MockInstance

  beforeEach(async () => {
    // Ensure structuredClone and crypto primitives exist in test environment
    if (!globalThis.structuredClone) {
      globalThis.structuredClone = (val) => JSON.parse(JSON.stringify(val))
    }
    if (globalThis.crypto) {
      let counter = 0
      globalThis.crypto.randomUUID = () => `mock-uuid-${++counter}` as any
    }

    onlineSpy = vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)
    await initOfflineQueue()
  })

  afterEach(async () => {
    if (onlineSpy) onlineSpy.mockRestore()
    vi.restoreAllMocks()
    globalThis.indexedDB = new IDBFactory() as unknown as typeof globalThis.indexedDB
  })

  describe("1. Offline Mutation Persistence Across Page Reload & SW Lifecycle Resets", () => {
    it("persists offline mutations in IndexedDB when enqueued while offline", async () => {
      onlineSpy.mockReturnValue(false)

      await enqueueOfflineMutation({
        url: "http://localhost/api/events/register",
        method: "POST",
        payload: { eventId: "evt-101", userId: "usr-42" },
        category: "events",
        headers: { "X-Custom-Header": "test-val" },
      })

      const pending = await readPendingMutations()
      expect(pending).toHaveLength(1)
      expect(pending[0]).toMatchObject({
        url: "http://localhost/api/events/register",
        method: "POST",
        payload: { eventId: "evt-101", userId: "usr-42" },
        category: "events",
        headers: { "X-Custom-Header": "test-val" },
        retryCount: 0,
      })
      expect(pending[0].mutationId).toBeDefined()
      expect(pending[0].idempotencyKey).toBeDefined()
    })

    it("maintains intact state across simulated page reloads and SW re-initializations", async () => {
      onlineSpy.mockReturnValue(false)

      // Step A: Enqueue 3 mutations across different categories
      await storePendingMutation({
        url: "/api/schedule/update",
        method: "PUT",
        payload: { day: 1, slot: 2 },
        category: "schedule",
      })
      await storePendingMutation({
        url: "/api/messenger/send",
        method: "POST",
        payload: { text: "Hello offline" },
        category: "messenger",
      })
      await storePendingMutation({
        url: "/api/news/like",
        method: "POST",
        payload: { newsId: 5 },
        category: "news",
      })

      // Step B: Simulate Page Reload / Environment Reset (clear in-memory references)
      const initialRecords = await readPendingMutations()
      expect(initialRecords).toHaveLength(3)

      // Simulate re-running SW initialization sequence
      await initOfflineQueue()

      // Step C: Verify all 3 records are unchanged after reset
      const reloadedRecords = await readPendingMutations()
      expect(reloadedRecords).toHaveLength(3)
      expect(reloadedRecords.map((r) => r.category).sort()).toEqual([
        "messenger",
        "news",
        "schedule",
      ])
      expect(reloadedRecords[0].timestamp).toBeLessThanOrEqual(reloadedRecords[2].timestamp)
    })

    it("preserves retryCount and remaining queue items across SW restarts after network errors", async () => {
      onlineSpy.mockReturnValue(true)

      await storePendingMutation({
        url: "/api/profile/update",
        method: "PATCH",
        payload: { bio: "Updated Bio" },
        category: "profile",
      })

      // Mock network failure (500 Internal Server Error)
      const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 500 })
      vi.stubGlobal("fetch", fetchMock)

      // Attempt processing
      await processPendingMutations()

      // Record should NOT be deleted, retryCount should be incremented to 1
      const records1 = await readPendingMutations()
      expect(records1).toHaveLength(1)
      expect(records1[0].retryCount).toBe(1)

      // Simulate SW process restart / re-init
      await initOfflineQueue()

      const records2 = await readPendingMutations()
      expect(records2).toHaveLength(1)
      expect(records2[0].retryCount).toBe(1)
    })

    it("discards mutation after reaching max retries (5) and broadcasts PERMANENT_FAILURE", async () => {
      onlineSpy.mockReturnValue(true)

      await storePendingMutation({
        url: "/api/test/retry-cap",
        method: "POST",
        payload: { attempt: "max" },
        retryCount: 4, // 5th failure will increment retryCount to 5
      })

      const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 500 })
      vi.stubGlobal("fetch", fetchMock)

      // 1st processing: fetch fails, retryCount incremented from 4 to 5
      await processPendingMutations()
      const records = await readPendingMutations()
      expect(records[0].retryCount).toBe(5)

      // 2nd processing: loop detects retryCount >= 5, evicts record, broadcasts failure
      await processPendingMutations()
      const remaining = await readPendingMutations()
      expect(remaining).toHaveLength(0) // Deleted from IDB after max retries
    })
  })

  describe("2. SyncStatus UI Component Under Various States", () => {
    it("renders nothing (returns null) when offline with 0 pending mutations", () => {
      vi.spyOn(useSyncStatusModule, "useSyncStatus").mockReturnValue({
        isOnline: false,
        syncState: "offline",
        pendingMutationsCount: 0,
        isFetchingCount: 0,
        totalPendingCount: 0,
        triggerManualSync: vi.fn(),
      })

      const { container } = render(<SyncStatus />)
      expect(container.firstChild).toBeNull()
    })

    it("renders offline warning indicator with badge count when offline with pending mutations", () => {
      vi.spyOn(useSyncStatusModule, "useSyncStatus").mockReturnValue({
        isOnline: false,
        syncState: "offline",
        pendingMutationsCount: 3,
        isFetchingCount: 0,
        totalPendingCount: 3,
        triggerManualSync: vi.fn(),
      })

      render(<SyncStatus />)

      const statusEl = screen.getByRole("status")
      expect(statusEl).toBeInTheDocument()
      expect(statusEl).toHaveAttribute("title", "Offline (3 queued)")
      expect(screen.getByText("3")).toBeInTheDocument()
    })

    it("renders syncing state with spinner icon and count when syncing online", () => {
      vi.spyOn(useSyncStatusModule, "useSyncStatus").mockReturnValue({
        isOnline: true,
        syncState: "syncing",
        pendingMutationsCount: 2,
        isFetchingCount: 1,
        totalPendingCount: 2,
        triggerManualSync: vi.fn(),
      })

      render(<SyncStatus />)

      const statusEl = screen.getByRole("status")
      expect(statusEl).toBeInTheDocument()
      expect(statusEl).toHaveAttribute("title", "All synced")
      expect(screen.getByText("2")).toBeInTheDocument()
    })

    it("renders synced state with checkmark icon when recently completed sync", () => {
      vi.spyOn(useSyncStatusModule, "useSyncStatus").mockReturnValue({
        isOnline: true,
        syncState: "synced",
        pendingMutationsCount: 0,
        isFetchingCount: 0,
        totalPendingCount: 0,
        triggerManualSync: vi.fn(),
      })

      render(<SyncStatus />)

      const statusEl = screen.getByRole("status")
      expect(statusEl).toBeInTheDocument()
      expect(statusEl.className).toContain("bg-success-bg")
    })

    it("triggers manual sync on user click", () => {
      const manualSyncSpy = vi.fn().mockResolvedValue(undefined)
      vi.spyOn(useSyncStatusModule, "useSyncStatus").mockReturnValue({
        isOnline: true,
        syncState: "idle",
        pendingMutationsCount: 0,
        isFetchingCount: 0,
        totalPendingCount: 0,
        triggerManualSync: manualSyncSpy,
      })

      render(<SyncStatus />)

      const statusEl = screen.getByRole("status")
      fireEvent.click(statusEl)

      expect(manualSyncSpy).toHaveBeenCalledTimes(1)
    })
  })

  describe("3. Stress & Security Edge Cases", () => {
    it("sanitizes malicious payload structures (__proto__, deep recursion, huge arrays)", async () => {
      const maliciousPayload = {
        title: "Legit title",
        __proto__: { admin: true },
        nested: {
          constructor: "hacked",
          validField: 42,
        },
        hugeList: Array.from({ length: 150 }, (_, i) => i),
      }

      await storePendingMutation({
        url: "/api/security/test",
        method: "POST",
        payload: maliciousPayload,
      })

      const records = await readPendingMutations()
      expect(records).toHaveLength(1)
      const sanitized = records[0].payload as any

      expect(sanitized.title).toBe("Legit title")
      expect(sanitized.__proto__).not.toHaveProperty("admin")
      expect(Object.prototype.hasOwnProperty.call(sanitized.nested, "constructor")).toBe(false)
      expect(sanitized.nested.validField).toBe(42)
      expect(sanitized.hugeList).toHaveLength(100) // Truncated array
    })

    it("handles non-retriable 4xx HTTP responses by discarding mutation immediately", async () => {
      onlineSpy.mockReturnValue(true)

      await storePendingMutation({
        url: "/api/bad-request",
        method: "POST",
        payload: { invalid: "data" },
      })

      // 400 Bad Request
      const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 400 })
      vi.stubGlobal("fetch", fetchMock)

      await processPendingMutations()

      const records = await readPendingMutations()
      expect(records).toHaveLength(0) // Deleted immediately (non-retriable)
    })
  })
})
