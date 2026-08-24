import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { openDB } from "idb"
import { IDBFactory } from "fake-indexeddb"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useSyncStatus } from "@/hooks/useSyncStatus"

const { queryState } = vi.hoisted(() => {
  const listeners = new Set<(online: boolean) => void>()
  return {
    queryState: {
      isOnline: true,
      isFetching: 0,
      mutations: [] as unknown[],
      listeners,
      queryClient: {
        resumePausedMutations: vi.fn().mockResolvedValue(undefined),
        refetchQueries: vi.fn().mockResolvedValue(undefined),
      },
    },
  }
})

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => queryState.queryClient,
  useIsFetching: () => queryState.isFetching,
  useMutationState: ({ select }: { select: (mutation: unknown) => unknown }) =>
    queryState.mutations.map(select),
  onlineManager: {
    isOnline: () => queryState.isOnline,
    setOnline: (online: boolean) => {
      queryState.isOnline = online
      queryState.listeners.forEach((listener) => listener(online))
    },
    subscribe: (listener: (online: boolean) => void) => {
      queryState.listeners.add(listener)
      return () => queryState.listeners.delete(listener)
    },
  },
}))

const DB_NAME = "notification-interactions"
const NEWS_STORE = "pending-news-interactions"
const MUTATION_STORE = "pending-mutations"
const REPORT_STORE = "pending-reports"

async function seedPendingQueues({ news = 0, mutations = 0, reports = 0 } = {}) {
  const db = await openDB(DB_NAME, 4, {
    upgrade(database) {
      if (!database.objectStoreNames.contains("pending-navigations")) {
        database.createObjectStore("pending-navigations", { keyPath: "id", autoIncrement: true })
      }
      if (!database.objectStoreNames.contains(REPORT_STORE)) {
        database.createObjectStore(REPORT_STORE, { keyPath: "id", autoIncrement: true })
      }
      if (!database.objectStoreNames.contains(NEWS_STORE)) {
        database.createObjectStore(NEWS_STORE, { keyPath: "id", autoIncrement: true })
      }
      if (!database.objectStoreNames.contains(MUTATION_STORE)) {
        database.createObjectStore(MUTATION_STORE, { keyPath: "id", autoIncrement: true })
      }
    },
  })

  for (let i = 0; i < news; i += 1) await db.add(NEWS_STORE, { value: `news-${i}` })
  for (let i = 0; i < mutations; i += 1) await db.add(MUTATION_STORE, { value: `mutation-${i}` })
  for (let i = 0; i < reports; i += 1) await db.add(REPORT_STORE, { value: `report-${i}` })
  db.close()
}

describe("useSyncStatus", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryState.isOnline = true
    queryState.isFetching = 0
    queryState.mutations = []
    queryState.listeners.clear()
    queryState.queryClient.resumePausedMutations.mockResolvedValue(undefined)
    queryState.queryClient.refetchQueries.mockResolvedValue(undefined)
    globalThis.indexedDB = new IDBFactory() as unknown as typeof globalThis.indexedDB
    vi.stubGlobal("navigator", { onLine: true })
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it("tracks online/offline events and cleans up listeners", () => {
    const { result, unmount } = renderHook(() => useSyncStatus())

    expect(result.current.isOnline).toBe(true)
    expect(result.current.syncState).toBe("idle")

    act(() => window.dispatchEvent(new Event("offline")))
    expect(result.current.isOnline).toBe(false)
    expect(result.current.syncState).toBe("offline")

    act(() => window.dispatchEvent(new Event("online")))
    expect(result.current.isOnline).toBe(true)

    unmount()
    expect(queryState.listeners.size).toBe(0)
  })

  it("counts pending React Query mutations and IndexedDB queues", async () => {
    queryState.isFetching = 2
    queryState.mutations = [{}, {}]
    await seedPendingQueues({ news: 2, mutations: 1, reports: 1 })

    const { result } = renderHook(() => useSyncStatus())

    await waitFor(() => expect(result.current.totalPendingCount).toBe(6))
    expect(result.current.pendingMutationsCount).toBe(2)
    expect(result.current.isFetchingCount).toBe(2)
    expect(result.current.syncState).toBe("syncing")
  })

  it("shows a transient synced state after active work drains", () => {
    vi.useFakeTimers()
    try {
      queryState.isFetching = 1
      const { result, rerender } = renderHook(() => useSyncStatus())

      expect(result.current.syncState).toBe("syncing")

      act(() => {
        queryState.isFetching = 0
        rerender()
      })

      expect(result.current.syncState).toBe("synced")

      act(() => vi.advanceTimersByTime(3000))
      expect(result.current.syncState).toBe("idle")
    } finally {
      vi.useRealTimers()
    }
  })

  it("handles an initially offline browser without querying service workers", () => {
    queryState.isOnline = false
    vi.stubGlobal("navigator", { onLine: false })

    const { result } = renderHook(() => useSyncStatus())

    expect(result.current.isOnline).toBe(false)
    expect(result.current.syncState).toBe("offline")
  })

  it("defaults to online when the browser navigator is unavailable", () => {
    vi.stubGlobal("navigator", undefined)

    const { result } = renderHook(() => useSyncStatus())

    expect(result.current.isOnline).toBe(true)
    expect(result.current.syncState).toBe("idle")
  })

  it("ignores an IndexedDB open error", async () => {
    const request = {} as IDBOpenDBRequest
    const open = vi.fn(() => {
      queueMicrotask(() => request.onerror?.(new Event("error")))
      return request
    })
    vi.stubGlobal("indexedDB", { open })

    const { result } = renderHook(() => useSyncStatus())

    await waitFor(() => expect(open).toHaveBeenCalledOnce())
    expect(result.current.totalPendingCount).toBe(0)
  })

  it("treats an IndexedDB transaction failure as an empty queue", async () => {
    const request = {} as IDBOpenDBRequest
    const db = {
      objectStoreNames: { contains: (name: string) => name === NEWS_STORE },
      transaction: vi.fn(() => {
        throw new Error("transaction unavailable")
      }),
      close: vi.fn(),
    } as unknown as IDBDatabase
    const open = vi.fn(() => {
      queueMicrotask(() => {
        Object.defineProperty(request, "result", { value: db })
        request.onsuccess?.(new Event("success"))
      })
      return request
    })
    vi.stubGlobal("indexedDB", { open })

    const { result } = renderHook(() => useSyncStatus())

    await waitFor(() => expect(db.close).toHaveBeenCalledOnce())
    expect(result.current.totalPendingCount).toBe(0)
  })

  it("preserves every existing object store during an upgrade", async () => {
    const request = {} as IDBOpenDBRequest
    const db = {
      objectStoreNames: { contains: vi.fn(() => true) },
      createObjectStore: vi.fn(),
      transaction: vi.fn(() => {
        throw new Error("not needed for this branch")
      }),
      close: vi.fn(),
    } as unknown as IDBDatabase
    const open = vi.fn(() => {
      queueMicrotask(() => {
        Object.defineProperty(request, "result", { value: db })
        request.onupgradeneeded?.(new Event("upgradeneeded") as IDBVersionChangeEvent)
        request.onsuccess?.(new Event("success"))
      })
      return request
    })
    vi.stubGlobal("indexedDB", { open })

    renderHook(() => useSyncStatus())

    await waitFor(() => expect(db.close).toHaveBeenCalledOnce())
    expect(db.createObjectStore).not.toHaveBeenCalled()
  })

  it("treats an IndexedDB count error as zero pending items", async () => {
    const openRequest = {} as IDBOpenDBRequest
    const countRequest = {} as IDBRequest<number>
    const db = {
      objectStoreNames: { contains: (name: string) => name === NEWS_STORE },
      transaction: vi.fn(() => ({
        objectStore: vi.fn(() => ({
          count: vi.fn(() => {
            queueMicrotask(() => countRequest.onerror?.(new Event("error")))
            return countRequest
          }),
        })),
      })),
      close: vi.fn(),
    } as unknown as IDBDatabase
    const open = vi.fn(() => {
      queueMicrotask(() => {
        Object.defineProperty(openRequest, "result", { value: db })
        openRequest.onsuccess?.(new Event("success"))
      })
      return openRequest
    })
    vi.stubGlobal("indexedDB", { open })

    const { result } = renderHook(() => useSyncStatus())

    await waitFor(() => expect(db.close).toHaveBeenCalledOnce())
    expect(result.current.totalPendingCount).toBe(0)
  })

  it("manually resumes queries and registers the background sync tag", async () => {
    const register = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal("navigator", {
      onLine: true,
      serviceWorker: {
        ready: Promise.resolve({ sync: { register } }),
      },
    })

    const { result } = renderHook(() => useSyncStatus())
    await act(async () => result.current.triggerManualSync())

    expect(queryState.queryClient.resumePausedMutations).toHaveBeenCalledOnce()
    expect(queryState.queryClient.refetchQueries).toHaveBeenCalledWith({ type: "active" })
    expect(register).toHaveBeenCalledWith("sync-offline-mutations")
  })

  it("falls back to the service worker controller when sync registration is unavailable", async () => {
    const postMessage = vi.fn()
    vi.stubGlobal("navigator", {
      onLine: true,
      serviceWorker: {
        ready: Promise.resolve({ controller: { postMessage } }),
        controller: { postMessage },
      },
    })

    const { result } = renderHook(() => useSyncStatus())
    await act(async () => result.current.triggerManualSync())

    expect(postMessage).toHaveBeenCalledWith({ type: "PROCESS_OFFLINE_QUEUES" })
  })

  it("continues the service-worker sync after a query resume failure", async () => {
    const register = vi.fn().mockResolvedValue(undefined)
    queryState.queryClient.resumePausedMutations.mockRejectedValue(new Error("query unavailable"))
    vi.stubGlobal("navigator", {
      onLine: true,
      serviceWorker: {
        ready: Promise.resolve({ sync: { register } }),
      },
    })

    const { result } = renderHook(() => useSyncStatus())
    await act(async () => result.current.triggerManualSync())

    expect(register).toHaveBeenCalledWith("sync-offline-mutations")
  })

  it("posts to the controller when service-worker readiness rejects", async () => {
    const postMessage = vi.fn()
    vi.stubGlobal("navigator", {
      onLine: true,
      serviceWorker: {
        ready: Promise.reject(new Error("worker unavailable")),
        controller: { postMessage },
      },
    })

    const { result } = renderHook(() => useSyncStatus())
    await act(async () => result.current.triggerManualSync())

    expect(postMessage).toHaveBeenCalledWith({ type: "PROCESS_OFFLINE_QUEUES" })
  })

  it("does not require a query client or service-worker API for manual sync", async () => {
    const originalQueryClient = queryState.queryClient
    ;(queryState as unknown as { queryClient: null }).queryClient = null
    vi.stubGlobal("navigator", { onLine: true })

    try {
      const { result } = renderHook(() => useSyncStatus())
      await expect(act(async () => result.current.triggerManualSync())).resolves.toBeUndefined()
    } finally {
      ;(queryState as unknown as { queryClient: typeof originalQueryClient }).queryClient =
        originalQueryClient
    }
  })

  it("does nothing when a ready worker has neither sync nor a controller", async () => {
    vi.stubGlobal("navigator", {
      onLine: true,
      serviceWorker: { ready: Promise.resolve({}), controller: null },
    })

    const { result } = renderHook(() => useSyncStatus())
    await expect(act(async () => result.current.triggerManualSync())).resolves.toBeUndefined()
  })

  it("does nothing when worker readiness fails without a controller", async () => {
    vi.stubGlobal("navigator", {
      onLine: true,
      serviceWorker: {
        ready: Promise.reject(new Error("worker unavailable")),
        controller: null,
      },
    })

    const { result } = renderHook(() => useSyncStatus())
    await expect(act(async () => result.current.triggerManualSync())).resolves.toBeUndefined()
  })

  it("returns immediately from manual sync while offline", async () => {
    queryState.isOnline = false
    const register = vi.fn()
    vi.stubGlobal("navigator", {
      onLine: false,
      serviceWorker: {
        ready: Promise.resolve({ sync: { register } }),
      },
    })

    const { result } = renderHook(() => useSyncStatus())
    await act(async () => result.current.triggerManualSync())

    expect(queryState.queryClient.resumePausedMutations).not.toHaveBeenCalled()
    expect(register).not.toHaveBeenCalled()
  })
})
