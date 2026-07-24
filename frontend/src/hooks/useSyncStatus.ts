import { useState, useEffect, useCallback } from "react"
import {
  useIsFetching,
  useMutationState,
  useQueryClient,
  onlineManager,
} from "@tanstack/react-query"
import { SERVICE_WORKER_MESSAGE_TYPES } from "@/constants/serviceWorkerMessages"

export type SyncState = "offline" | "syncing" | "synced" | "idle"

export interface SyncStatusResult {
  isOnline: boolean
  syncState: SyncState
  pendingMutationsCount: number
  isFetchingCount: number
  totalPendingCount: number
  triggerManualSync: () => Promise<void>
}

const CLICK_DB_NAME = "notification-interactions"
const CLICK_DB_VERSION = 4
const NEWS_INTERACTION_STORE = "pending-news-interactions"
const MUTATION_STORE = "pending-mutations"

function useSafeQueryClient() {
  try {
    return useQueryClient()
  } catch {
    return null
  }
}

function useSafeIsFetching() {
  try {
    return useIsFetching()
  } catch {
    return 0
  }
}

function useSafePendingMutationsCount() {
  try {
    const pendingMutations = useMutationState({
      filters: { status: "pending" },
      select: (mutation) => mutation.state,
    })
    return pendingMutations.length
  } catch {
    return 0
  }
}

export function useSyncStatus(): SyncStatusResult {
  const queryClient = useSafeQueryClient()
  const [isOnline, setIsOnline] = useState(
    () => (typeof navigator !== "undefined" && typeof navigator.onLine === "boolean" ? navigator.onLine : true)
  )
  const [idbPendingCount, setIdbPendingCount] = useState(0)
  const [justSynced, setJustSynced] = useState(false)

  // 1. Reactive network status
  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true)
      onlineManager.setOnline(true)
    }
    const handleOffline = () => {
      setIsOnline(false)
      onlineManager.setOnline(false)
    }

    window.addEventListener("online", handleOnline)
    window.addEventListener("offline", handleOffline)

    const unsubscribe = onlineManager.subscribe((online) => {
      setIsOnline(online)
    })

    return () => {
      window.removeEventListener("online", handleOnline)
      window.removeEventListener("offline", handleOffline)
      unsubscribe()
    }
  }, [])

  // 2. Count active fetching queries & pending mutations safely
  const isFetchingCount = useSafeIsFetching()
  const pendingMutationsCount = useSafePendingMutationsCount()

  // 3. Poll IndexedDB for pending background queues
  useEffect(() => {
    let isCancelled = false
    const checkQueue = async () => {
      try {
        const db = await new Promise<IDBDatabase>((resolve, reject) => {
          const request = indexedDB.open(CLICK_DB_NAME, CLICK_DB_VERSION)
          request.onupgradeneeded = () => {
            const database = request.result
            if (!database.objectStoreNames.contains("pending-navigations")) {
              database.createObjectStore("pending-navigations", { keyPath: "id", autoIncrement: true })
            }
            if (!database.objectStoreNames.contains("pending-reports")) {
              database.createObjectStore("pending-reports", { keyPath: "id", autoIncrement: true })
            }
            if (!database.objectStoreNames.contains(NEWS_INTERACTION_STORE)) {
              database.createObjectStore(NEWS_INTERACTION_STORE, { keyPath: "id", autoIncrement: true })
            }
            if (!database.objectStoreNames.contains(MUTATION_STORE)) {
              database.createObjectStore(MUTATION_STORE, { keyPath: "id", autoIncrement: true })
            }
          }
          request.onsuccess = () => resolve(request.result)
          request.onerror = () => reject(request.error)
        })

        let total = 0
        const stores = [NEWS_INTERACTION_STORE, MUTATION_STORE, "pending-reports"].filter((s) =>
          db.objectStoreNames.contains(s)
        )

        for (const storeName of stores) {
          const count = await new Promise<number>((resolve) => {
            try {
              const tx = db.transaction(storeName, "readonly")
              const store = tx.objectStore(storeName)
              const req = store.count()
              req.onsuccess = () => resolve(req.result)
              req.onerror = () => resolve(0)
            } catch {
              resolve(0)
            }
          })
          total += count
        }

        db.close()
        if (!isCancelled) setIdbPendingCount(total)
      } catch {
        // DB not ready or blocked
      }
    }

    const interval = setInterval(checkQueue, 3000)
    checkQueue()

    return () => {
      isCancelled = true
      clearInterval(interval)
    }
  }, [])

  const totalPendingCount = pendingMutationsCount + idbPendingCount

  // 4. Derive high-level sync state
  let syncState: SyncState = "idle"
  if (!isOnline) {
    syncState = "offline"
  } else if (isFetchingCount > 0 || totalPendingCount > 0) {
    syncState = "syncing"
  } else if (justSynced) {
    syncState = "synced"
  } else {
    syncState = "idle"
  }

  // Transient "synced" status transition
  useEffect(() => {
    if (isOnline && isFetchingCount === 0 && totalPendingCount === 0 && syncState === "syncing") {
      setJustSynced(true)
      const timer = setTimeout(() => setJustSynced(false), 3000)
      return () => clearTimeout(timer)
    }
  }, [isOnline, isFetchingCount, totalPendingCount, syncState])

  // 5. Manual force sync trigger
  const triggerManualSync = useCallback(async () => {
    if (!onlineManager.isOnline()) return
    if (queryClient) {
      try {
        await queryClient.resumePausedMutations()
        await queryClient.refetchQueries({ type: "active" })
      } catch {
        /* ignore */
      }
    }

    if (typeof navigator !== "undefined" && "serviceWorker" in navigator) {
      try {
        const reg = await navigator.serviceWorker.ready
        if ("sync" in reg) {
          await (reg as any).sync.register("sync-offline-mutations")
        } else if (navigator.serviceWorker.controller) {
          navigator.serviceWorker.controller.postMessage({
            type: SERVICE_WORKER_MESSAGE_TYPES.PROCESS_OFFLINE_QUEUES,
          })
        }
      } catch {
        if (navigator.serviceWorker.controller) {
          navigator.serviceWorker.controller.postMessage({
            type: SERVICE_WORKER_MESSAGE_TYPES.PROCESS_OFFLINE_QUEUES,
          })
        }
      }
    }
  }, [queryClient])

  return {
    isOnline,
    syncState,
    pendingMutationsCount,
    isFetchingCount,
    totalPendingCount,
    triggerManualSync,
  }
}
