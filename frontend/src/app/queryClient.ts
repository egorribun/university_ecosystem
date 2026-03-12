import { QueryClient } from "@tanstack/react-query"
import { get, set, del } from "idb-keyval"
import type { PersistedClient, Persister } from "@tanstack/react-query-persist-client"

const DEFAULT_STALE_MS = 5 * 60_000 // 5 minutes - standard freshness
const DEFAULT_CACHE_MS = 30 * 60_000 // 30 minutes - persistent window

const parseDuration = (value: string | number | undefined, fallback: number) => {
  if (typeof value === "number") {
    return Number.isFinite(value) && value > 0 ? value : fallback
  }

  if (!value) return fallback

  const parsed = Number.parseInt(String(value), 10)
  if (!Number.isFinite(parsed) || parsed <= 0) return fallback

  return parsed
}

const staleTime = parseDuration(import.meta.env.VITE_QUERY_STALE_TIME_MS, DEFAULT_STALE_MS)
const gcTime = parseDuration(import.meta.env.VITE_QUERY_CACHE_TTL_MS, DEFAULT_CACHE_MS)

const defaultOptions = {
  queries: {
    staleTime,
    gcTime,
    retry: 1,
    refetchOnWindowFocus: true, // Refresh when user returns to tab
    refetchOnReconnect: "always",
  },
  mutations: { retry: 0, gcTime: 0 },
} as const

export const createQueryClient = () =>
  new QueryClient({
    defaultOptions,
  })

export const queryClient = createQueryClient()

// FE-02 (audit 2026-03-08 Wave 5): Limit IDB persist size to 50 MB.
// Without a guard, a large query cache (many chats + long event lists) triggers
// a QuotaExceededError that propagates as an unhandled rejection and crashes the
// app silently. Graceful degradation: skip persist when too large, clear when
// the quota is already exhausted.
const MAX_IDB_PERSIST_BYTES = 50 * 1024 * 1024 // 50 MB

export function createIDBPersister(idbValidKey: IDBValidKey = "reactQuery") {
  return {
    persistClient: async (client: PersistedClient) => {
      try {
        const serialized = JSON.stringify(client)
        if (serialized.length > MAX_IDB_PERSIST_BYTES) {
          // Length in JS is UTF-16 code units ≈ bytes for ASCII-heavy JSON.
          if (import.meta.env.DEV) {
            console.warn(
              `[IDBPersister] Cache too large (${(serialized.length / 1024 / 1024).toFixed(1)} MB) — skipping IDB persist`
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
