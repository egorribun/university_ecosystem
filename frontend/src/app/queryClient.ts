import { QueryClient } from "@tanstack/react-query"
import { get, set, del } from "idb-keyval"
import type { PersistedClient, Persister } from "@tanstack/react-query-persist-client"

const DEFAULT_STALE_MS = 5 * 60_000 // 5 minutes - standard freshness
const DEFAULT_CACHE_MS = 30 * 60_000 // 30 minutes - persistent window

const parseDuration = (value: string | undefined, fallback: number) => {
  if (!value) return fallback

  const parsed = Number.parseInt(String(value), 10)
  if (!Number.isFinite(parsed) || parsed <= 0) return fallback

  return parsed
}

const staleTime = parseDuration(import.meta.env.VITE_QUERY_STALE_TIME_MS, DEFAULT_STALE_MS)
const gcTime = parseDuration(import.meta.env.VITE_QUERY_CACHE_TTL_MS, DEFAULT_CACHE_MS)

import type { PersistQueryClientOptions } from "@tanstack/react-query-persist-client"

const defaultOptions = {
  queries: {
    staleTime,
    gcTime,
    retry: 1,
    refetchOnWindowFocus: true, // Refresh when user returns to tab
    refetchOnReconnect: "always",
    networkMode: "offlineFirst" as const,
  },
  mutations: {
    retry: 0,
    gcTime: 0,
    networkMode: "offlineFirst" as const,
  },
} as const

export const createQueryClient = () =>
  new QueryClient({
    defaultOptions,
  })

export const queryClient = createQueryClient()

// FE-02 (audit 2026-03-08 Wave 5): Limit IDB persist size.
// Without a guard, a large query cache (many chats + long event lists) triggers
// a QuotaExceededError that propagates as an unhandled rejection and crashes the
// app silently. Graceful degradation: skip persist when too large, clear when
// the quota is already exhausted.
//
// PERF-21-01 (audit 2026-03-25 Wave 21): Reduced default from 50 MB to 20 MB.
// 50 MB is aggressive for mobile devices with limited storage. The responsive
// helper uses navigator.storage.estimate() to pick a device-appropriate limit.
const DEFAULT_IDB_QUOTA_BYTES = 20 * 1024 * 1024 // 20 MB
const MAX_IDB_QUOTA_BYTES = 50 * 1024 * 1024 // 50 MB cap

let _resolvedQuota: number | null = null

function isPositiveFiniteQuota(value: unknown): value is number {
  if (!Number.isFinite(value)) return false
  return (value as number) > 0
}

async function readStorageEstimate(): Promise<StorageEstimate | undefined> {
  if (typeof navigator === "undefined") return undefined

  const storage = navigator.storage
  if (storage === undefined) return undefined

  const estimate = storage.estimate
  if (typeof estimate !== "function") return undefined

  // Keep the synchronous guard operations outside this rejection handler so
  // only the browser API's asynchronous failure is degraded to the default
  // quota.  Using Promise.catch also keeps that contract explicit without a
  // redundant try/catch whose empty-body mutant would be equivalent.
  const pendingEstimate = estimate.call(storage)
  return await pendingEstimate.catch(() => undefined)
}

async function getIdbQuotaBytes(): Promise<number> {
  if (_resolvedQuota !== null) return _resolvedQuota
  const estimate = await readStorageEstimate()
  if (estimate !== undefined) {
    const availableQuota = estimate.quota
    if (isPositiveFiniteQuota(availableQuota)) {
      // Use at most 5% of available storage, capped at 50 MB
      _resolvedQuota = Math.min(Math.floor(availableQuota * 0.05), MAX_IDB_QUOTA_BYTES)
      return _resolvedQuota
    }
  }
  _resolvedQuota = DEFAULT_IDB_QUOTA_BYTES
  return _resolvedQuota
}

export function createIDBPersister(idbValidKey: IDBValidKey = "reactQuery") {
  return {
    persistClient: async (client: PersistedClient) => {
      try {
        const serialized = JSON.stringify(client)
        const quota = await getIdbQuotaBytes()
        if (serialized.length > quota) {
          // Length in JS is UTF-16 code units ≈ bytes for ASCII-heavy JSON.
          if (import.meta.env.DEV) {
            console.warn(
              `[IDBPersister] Cache too large (${(serialized.length / 1024 / 1024).toFixed(1)} MB, quota ${(quota / 1024 / 1024).toFixed(0)} MB) — skipping IDB persist`
            )
          }
          return
        }
        await set(idbValidKey, client)
      } catch (err) {
        if (err instanceof DOMException && err.name === "QuotaExceededError") {
          // IndexedDB quota hit: wipe the cache so the app can continue.
          if (import.meta.env.DEV) {
            console.warn("[IDBPersister] IndexedDB quota exceeded — clearing persisted cache")
          }
          await del(idbValidKey)
        } else {
          throw err
        }
      }
    },
    restoreClient: async () => {
      return await get<PersistedClient>(idbValidKey)
    },
    removeClient: async () => {
      await del(idbValidKey)
    },
  } satisfies Persister
}

export const idbPersister = createIDBPersister()

const PERSIST_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000 // 7 days
const APP_VERSION_BUSTER = (import.meta.env.VITE_APP_VERSION as string) || "1.0.0"

export const persistOptions: Omit<PersistQueryClientOptions, "queryClient"> = {
  persister: idbPersister,
  maxAge: PERSIST_MAX_AGE_MS,
  buster: APP_VERSION_BUSTER,
  dehydrateOptions: {
    shouldDehydrateQuery: (query) => query.state.status === "success",
    shouldDehydrateMutation: (mutation) =>
      mutation.state.isPaused || mutation.state.status === "pending",
  },
}
