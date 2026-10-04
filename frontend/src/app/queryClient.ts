import { CancelledError, QueryClient } from "@tanstack/react-query"
import { get, set, del } from "idb-keyval"
import type { PersistedClient, Persister } from "@tanstack/react-query-persist-client"
import { createSessionMutationCache } from "./sessionMutationCache"
import {
  captureSessionEpoch,
  invalidateSessionEpoch,
  getBrowserSessionGeneration,
} from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { getConfirmedUserId, waitForConfirmedUserId } from "@/stores/authIdentity"

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

const browserClients = new Set<WeakRef<QueryClient>>()

export const createQueryClient = () => {
  const client = new QueryClient({ defaultOptions, mutationCache: createSessionMutationCache() })
  const cancel = client.cancelQueries.bind(client)
  client.cancelQueries = (...args) => {
    const owns = captureSessionEpoch()
    return cancel(...args).then(() => {
      // Every asynchronous optimistic callback in this app suspends here before
      // reading/writing its snapshot. Reject it if the account changed meanwhile.
      if (!owns()) throw new CancelledError({ silent: true })
    })
  }
  if (typeof window !== "undefined") browserClients.add(new WeakRef(client))
  return client
}

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

export function createIDBPersister(idbValidKey: IDBValidKey) {
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

let cacheIdentity: string | null = null
let cacheEpoch = 0
let restoredClient: PersistedClient | undefined
let persistenceQueue: Promise<void> = Promise.resolve()

/** Publish the identity before rendering a new profile or clearing its caches. */
export function setQueryCacheIdentity(owner: string | null) {
  if (owner === cacheIdentity) return
  cacheIdentity = owner
  cacheEpoch += 1
  invalidateSessionEpoch()
  // PersistQueryClientProvider hydrates after awaiting restoreClient. Invalidate
  // the returned object too, closing the final restore-to-hydrate microtask gap.
  if (restoredClient) restoredClient.clientState = { queries: [], mutations: [] }
  restoredClient = undefined
  for (const reference of browserClients) {
    const client = reference.deref()
    if (client) client.clear()
    else browserClients.delete(reference)
  }
}

useAuthStore.subscribe((state) => {
  // A refresh may mark an already-confirmed account loading temporarily.
  if (state.loading && state.user?.id === cacheIdentity) return
  setQueryCacheIdentity(getConfirmedUserId(state))
})

const scopedKey = (owner: string) => `reactQuery:v2:${encodeURIComponent(owner)}`
const belongsToOwner = (client: PersistedClient, owner: string) =>
  client.clientState.queries.some((query) => {
    const data = query.state.data as { id?: unknown } | undefined
    return query.queryKey[0] === "users" && query.queryKey[1] === "me" && data?.id === owner
  })

/** The production persister never reads the legacy shared reactQuery key. */
export const idbPersister: Persister = {
  async persistClient(client) {
    const owner = cacheIdentity
    const epoch = cacheEpoch
    const session = captureSessionEpoch()
    if (!owner || !getBrowserSessionGeneration() || !belongsToOwner(client, owner)) return
    const key = scopedKey(owner)
    const owns = () => session() && cacheIdentity === owner && cacheEpoch === epoch
    const write = persistenceQueue.then(async () => {
      if (!owns()) return
      await createIDBPersister(key).persistClient(client)
      if (!owns()) await del(key)
    })
    persistenceQueue = write.catch(() => undefined)
    await write
  },
  async restoreClient() {
    await del("reactQuery")
    // Auth bootstrap fetchQuery is imperative and can resolve while the query
    // provider waits. Anonymous/cold workers must not hydrate account data.
    const owner = await waitForConfirmedUserId()
    if (!owner || !getBrowserSessionGeneration() || cacheIdentity !== owner) return undefined
    const epoch = cacheEpoch
    const session = captureSessionEpoch()
    const saved = await get<PersistedClient>(scopedKey(owner))
    if (
      !session() ||
      cacheIdentity !== owner ||
      cacheEpoch !== epoch ||
      !saved ||
      !belongsToOwner(saved, owner)
    )
      return undefined
    restoredClient = saved
    return saved
  },
  async removeClient() {
    const owner = cacheIdentity
    await del("reactQuery")
    if (owner) {
      const removal = persistenceQueue.then(() => del(scopedKey(owner)))
      persistenceQueue = removal.catch(() => undefined)
      await removal
    }
  },
}

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
