import { CancelledError, QueryClient } from "@tanstack/react-query"
import { get, set, del, keys } from "idb-keyval"
import type { PersistedClient, Persister } from "@tanstack/react-query-persist-client"
import { createSessionMutationCache } from "./sessionMutationCache"
import {
  captureSessionEpoch,
  invalidateSessionEpoch,
  getBrowserSessionGeneration,
  isCurrentBrowserSession,
} from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import {
  ENCRYPTED_CACHE_PLACEHOLDER_USER_ID,
  SSR_STUB_USER_ID,
  getConfirmedUserId,
  waitForConfirmedUserId,
} from "@/stores/authIdentity"
import type { UserState } from "@/types/Auth"

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
  const client = new QueryClient({
    defaultOptions,
    mutationCache: createSessionMutationCache(),
  })
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
const cacheIdentityListeners = new Set<() => void>()

/** Subscribe render barriers to cache-owner changes after retired data is cleared. */
export function subscribeQueryCacheIdentity(listener: () => void) {
  cacheIdentityListeners.add(listener)
  return () => cacheIdentityListeners.delete(listener)
}

/** Read the committed owner used to namespace the browser query cache. */
export const getQueryCacheIdentity = (): string | null => cacheIdentity

/** Whether the current query cache has been committed for this auth owner. */
export const isQueryCacheIdentity = (owner: string | null): boolean => cacheIdentity === owner

const retireBrowserQueryState = () => {
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

const updateQueryCacheIdentity = (
  owner: string | null,
  beforeNotify: (() => void) | undefined,
  retireUnchangedIdentity: boolean
): boolean => {
  if (owner === cacheIdentity && !retireUnchangedIdentity) {
    beforeNotify?.()
    return false
  }
  cacheIdentity = owner
  retireBrowserQueryState()
  beforeNotify?.()
  for (const listener of cacheIdentityListeners) listener()
  return true
}

/** Publish the identity before rendering a new profile or clearing its caches. */
export function setQueryCacheIdentity(owner: string | null, beforeNotify?: () => void): boolean {
  return updateQueryCacheIdentity(owner, beforeNotify, false)
}

const isBootstrapUser = (user: UserState): boolean => {
  const id: unknown = user?.id
  return id === SSR_STUB_USER_ID || id === ENCRYPTED_CACHE_PLACEHOLDER_USER_ID || id === -1
}

useAuthStore.subscribe((state, previousState) => {
  // A refresh may mark an already-confirmed account loading temporarily.
  if (state.loading && state.user?.id === cacheIdentity) return
  const owner = getConfirmedUserId(state)
  // A role-only SSR hint or encrypted-cache placeholder is not a settled
  // signed-out result. Preserve its request snapshot only in the current
  // browser generation; owner changes still retire prior-account data below.
  const currentBootstrap = isBootstrapUser(state.user) && isCurrentBrowserSession()
  const previousBootstrap = isBootstrapUser(previousState.user)
  const settledWithoutOwner =
    !state.loading &&
    owner === null &&
    !currentBootstrap &&
    (previousState.loading || previousBootstrap)
  // The profile commit may already have published an explicit signed-out
  // marker before its passive store bridge runs. Retire all private state, but
  // preserve that null marker only on clients which already committed it.
  const signedOutClients: QueryClient[] = []
  const profileKey = ["users", "me"] as const
  if (settledWithoutOwner && state.user === null) {
    for (const reference of browserClients) {
      const client = reference.deref()
      if (client?.getQueryData(profileKey) === null) signedOutClients.push(client)
    }
  }
  const publishSignedOutSnapshots =
    signedOutClients.length > 0
      ? () => {
          for (const client of signedOutClients) client.setQueryData(profileKey, null)
        }
      : undefined
  updateQueryCacheIdentity(owner, publishSignedOutSnapshots, settledWithoutOwner)
})

const scopedKey = (owner: string) => `reactQuery:v2:${encodeURIComponent(owner)}`
// Reject malformed snapshots before filtering, owner checks, or restore.
const isObjectRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value)

const hasPersistedClientShape = (value: unknown): value is PersistedClient => {
  if (
    !isObjectRecord(value) ||
    typeof value.timestamp !== "number" ||
    !Number.isFinite(value.timestamp) ||
    typeof value.buster !== "string" ||
    !isObjectRecord(value.clientState)
  )
    return false

  const { queries, mutations } = value.clientState
  return (
    Array.isArray(queries) &&
    Array.isArray(mutations) &&
    queries.every(
      (query) =>
        isObjectRecord(query) &&
        typeof query.queryHash === "string" &&
        Array.isArray(query.queryKey) &&
        typeof query.dehydratedAt === "number" &&
        Number.isFinite(query.dehydratedAt) &&
        isObjectRecord(query.state) &&
        (query.meta === undefined || isObjectRecord(query.meta))
    ) &&
    mutations.every(
      (mutation) =>
        isObjectRecord(mutation) &&
        (mutation.mutationKey === undefined || Array.isArray(mutation.mutationKey)) &&
        isObjectRecord(mutation.state) &&
        (mutation.meta === undefined || isObjectRecord(mutation.meta))
    )
  )
}
const isCurrentUserProfileKey = (queryKey: readonly unknown[]) =>
  queryKey.length === 2 && queryKey[0] === "users" && queryKey[1] === "me"
const isCurrentUserProfileQuery = (query: PersistedClient["clientState"]["queries"][number]) =>
  isCurrentUserProfileKey(query.queryKey)

// When a profile witness is present, validate it before removing it. New
// snapshots omit the profile, so their owner is established by the confirmed
// auth identity and the exact per-owner storage namespace instead.
const belongsToOwner = (client: PersistedClient, owner: string) => {
  const profiles = client.clientState.queries.filter(isCurrentUserProfileQuery)
  if (profiles.length > 1) return false

  const profile = profiles[0]
  if (!profile) return true
  const data = profile.state.data as { id?: unknown } | undefined
  return data?.id === owner
}

const withoutSensitiveQueries = (client: PersistedClient): PersistedClient => ({
  ...client,
  clientState: {
    ...client.clientState,
    queries: client.clientState.queries.filter(
      (query) => query.meta?.persist !== false && !isCurrentUserProfileQuery(query)
    ),
  },
})

const withoutNonPersistentMutations = (client: PersistedClient): PersistedClient => ({
  ...client,
  clientState: {
    ...client.clientState,
    mutations: client.clientState.mutations.filter((mutation) => mutation.meta?.persist !== false),
  },
})

const isExactNewsListQueryKey = (queryKey: readonly unknown[]): boolean => {
  if (queryKey.length !== 3) return false
  if (queryKey[0] !== "news") return false
  if (queryKey[1] !== "list" && queryKey[1] !== "anonymous-list") return false

  const filters = queryKey[2]
  if (!isObjectRecord(filters)) return false
  return (
    typeof filters.language === "string" &&
    typeof filters.limit === "number" &&
    Number.isInteger(filters.limit) &&
    filters.limit >= 1
  )
}

const isOptionalString = (value: unknown): boolean =>
  value === undefined || value === null || typeof value === "string"

const hasSafeNewsListInfiniteData = (value: unknown): boolean => {
  if (!isObjectRecord(value)) return false
  const { pages, pageParams } = value
  if (!Array.isArray(pages) || !Array.isArray(pageParams) || pages.length !== pageParams.length)
    return false
  if (
    !Array.from(pageParams).every(
      (pageParam) => pageParam === null || typeof pageParam === "string"
    )
  )
    return false

  return Array.from(pages).every(
    (page) =>
      isObjectRecord(page) &&
      Array.isArray(page.items) &&
      isOptionalString(page.cursor) &&
      isOptionalString(page.next_cursor) &&
      (page.has_more === undefined || typeof page.has_more === "boolean")
  )
}

const withoutMalformedNewsListQueries = (client: PersistedClient): PersistedClient => ({
  ...client,
  clientState: {
    ...client.clientState,
    queries: client.clientState.queries.filter(
      (query) =>
        !isExactNewsListQueryKey(query.queryKey) || hasSafeNewsListInfiniteData(query.state.data)
    ),
  },
})

const sanitizePersistedClient = (client: PersistedClient): PersistedClient =>
  withoutMalformedNewsListQueries(withoutSensitiveQueries(client))
const ownerFromStorageKey = (key: string): string | undefined => {
  const prefix = "reactQuery:v2:"
  // sanitizeStoredSnapshots filters to this prefix before calling the helper.
  try {
    const owner = decodeURIComponent(key.slice(prefix.length))
    return owner.length > 0 && scopedKey(owner) === key ? owner : undefined
  } catch {
    return undefined
  }
}

/** Migrate every legacy v2 account snapshot before any one is hydrated. */
async function sanitizeStoredSnapshots(owns: () => boolean): Promise<void> {
  const migration = persistenceQueue.then(async () => {
    for (const key of await keys()) {
      if (!owns()) return
      if (typeof key !== "string" || !key.startsWith("reactQuery:v2:")) continue
      const owner = ownerFromStorageKey(key)
      if (!owner) {
        await del(key)
        continue
      }
      const saved = await get<PersistedClient>(key)
      if (!owns()) return
      if (saved === undefined) continue
      if (!hasPersistedClientShape(saved) || !belongsToOwner(saved, owner)) {
        await del(key)
        continue
      }
      const sanitized = sanitizePersistedClient(saved)
      if (sanitized.clientState.queries.length !== saved.clientState.queries.length) {
        await set(key, sanitized)
      }
    }
  })
  persistenceQueue = migration.catch(() => undefined)
  await migration
}

/** The production persister never reads the legacy shared reactQuery key. */
export const idbPersister: Persister = {
  async persistClient(client) {
    const owner = cacheIdentity
    const epoch = cacheEpoch
    const session = captureSessionEpoch()
    if (!owner || !getBrowserSessionGeneration() || !hasPersistedClientShape(client)) return
    // Check an available profile witness before filtering it out. The current
    // cache identity and per-owner namespace bind new profile-free snapshots.
    if (!belongsToOwner(client, owner)) return
    const persistableClient = withoutNonPersistentMutations(withoutSensitiveQueries(client))
    const key = scopedKey(owner)
    const owns = () => session() && cacheIdentity === owner && cacheEpoch === epoch
    const write = persistenceQueue.then(async () => {
      if (!owns()) return
      await createIDBPersister(key).persistClient(persistableClient)
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
    const owns = () => session() && cacheIdentity === owner && cacheEpoch === epoch
    await sanitizeStoredSnapshots(owns)
    if (!owns()) return undefined
    const saved = await get<PersistedClient>(scopedKey(owner))
    if (!owns() || !saved || !hasPersistedClientShape(saved) || !belongsToOwner(saved, owner))
      return undefined
    const sanitized = sanitizePersistedClient(saved)
    if (sanitized.clientState.queries.length !== saved.clientState.queries.length) {
      const write = persistenceQueue.then(async () => {
        if (owns()) await set(scopedKey(owner), sanitized)
      })
      persistenceQueue = write.catch(() => undefined)
      await write
      if (!owns()) return undefined
    }
    // Keep the stored legacy snapshot intact; only the hydration view excludes
    // mutations that explicitly opted out of persistence.
    restoredClient = withoutNonPersistentMutations(sanitized)
    return restoredClient
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
const APP_VERSION_BUSTER =
  import.meta.env.VITE_APP_RELEASE || (import.meta.env.VITE_APP_VERSION as string) || "1.0.0"

export const persistOptions: Omit<PersistQueryClientOptions, "queryClient"> = {
  persister: idbPersister,
  maxAge: PERSIST_MAX_AGE_MS,
  buster: APP_VERSION_BUSTER,
  dehydrateOptions: {
    shouldDehydrateQuery: (query) =>
      query.state.status === "success" &&
      query.meta?.persist !== false &&
      !isCurrentUserProfileKey(query.queryKey),
    shouldDehydrateMutation: (mutation) =>
      mutation.options.meta?.persist !== false &&
      (mutation.state.isPaused || mutation.state.status === "pending"),
  },
}
