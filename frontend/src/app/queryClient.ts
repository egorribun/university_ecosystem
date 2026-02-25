import { QueryClient } from "@tanstack/react-query"
import { get, set, del } from "idb-keyval"
import type { PersistedClient, Persister } from "@tanstack/react-query-persist-client"

const DEFAULT_STALE_MS = 10_000 // 10 seconds - keep data fresh
const DEFAULT_CACHE_MS = 10 * 60_000

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
  mutations: { retry: 0 },
} as const

export const createQueryClient = () =>
  new QueryClient({
    defaultOptions,
  })

export const queryClient = createQueryClient()

export function createIDBPersister(idbValidKey: IDBValidKey = "reactQuery") {
  return {
    persistClient: async (client: PersistedClient) => {
      await set(idbValidKey, client)
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
