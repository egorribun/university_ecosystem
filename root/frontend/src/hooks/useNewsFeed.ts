import { useEffect, useMemo } from "react"
import {
  useQuery,
  useQueryClient,
  type QueryClient,
  type QueryKey,
  type UseQueryOptions,
} from "@tanstack/react-query"
import { isAxiosError } from "axios"

import { fetchNews, parseNewsList, type NewsItem } from "@/api/news"
import { ApiResponseValidationError } from "@/api/validation"
import type { SupportedLanguage } from "@/contexts/LanguageContext"

const NEWS_CACHE_NAME = "api-cache"
const NEWS_ENDPOINT = "/api/news"
const ACCEPT_LANGUAGE_HEADER = "Accept-Language"
const JSON_CONTENT_TYPE = "application/json"

const LEGACY_STORAGE_KEYS = [
  "news:list",
  "news:etag",
  "news:list:ru",
  "news:list:en",
  "news:etag:ru",
  "news:etag:en",
]

type NewsFeedSnapshot = {
  items: NewsItem[]
  etag: string | null
}

const buildCacheRequest = (language: SupportedLanguage) => {
  const base = typeof window !== "undefined" ? window.location.origin : ""
  const url = base ? new URL(NEWS_ENDPOINT, base).toString() : NEWS_ENDPOINT
  const headers = new Headers()
  headers.set(ACCEPT_LANGUAGE_HEADER, language)
  return new Request(url, {
    headers,
    credentials: "include",
  })
}

const readCacheSnapshot = async (language: SupportedLanguage) => {
  if (typeof window === "undefined" || !("caches" in window) || !window.caches) {
    return undefined
  }

  try {
    const cache = await window.caches.open(NEWS_CACHE_NAME)
    const response = await cache.match(buildCacheRequest(language), { ignoreMethod: true })
    if (!response) return undefined

    try {
      const payload = await response.clone().json()
      const items = parseNewsList(payload)
      const etag = response.headers.get("etag")
      return { items, etag: etag ?? null }
    } catch (error) {
      if (!(error instanceof ApiResponseValidationError)) {
        console.warn("useNewsFeed: failed to parse cached payload", error)
      }
      return undefined
    }
  } catch (error) {
    console.warn("useNewsFeed: failed to read cache", error)
    return undefined
  }
}

const persistCacheSnapshot = async (language: SupportedLanguage, snapshot: NewsFeedSnapshot) => {
  if (typeof window === "undefined" || !("caches" in window) || !window.caches) {
    return
  }

  try {
    const cache = await window.caches.open(NEWS_CACHE_NAME)
    const headers = new Headers({
      "Content-Type": JSON_CONTENT_TYPE,
    })
    if (snapshot.etag) {
      headers.set("ETag", snapshot.etag)
    }

    const response = new Response(JSON.stringify(snapshot.items), {
      status: 200,
      headers,
    })

    await cache.put(buildCacheRequest(language), response)
  } catch (error) {
    console.warn("useNewsFeed: failed to persist cache", error)
  }
}

const deleteCacheSnapshot = async (language: SupportedLanguage) => {
  if (typeof window === "undefined" || !("caches" in window) || !window.caches) {
    return
  }

  try {
    const cache = await window.caches.open(NEWS_CACHE_NAME)
    await cache.delete(buildCacheRequest(language), { ignoreMethod: true })
  } catch (error) {
    console.warn("useNewsFeed: failed to delete cached snapshot", error)
  }
}

let legacyKeysCleared = false

const clearLegacyStorageKeys = () => {
  if (legacyKeysCleared || typeof window === "undefined") {
    return
  }
  try {
    const storage = window.localStorage
    for (const key of LEGACY_STORAGE_KEYS) {
      storage.removeItem(key)
    }
  } catch {
    /* noop */
  }
  legacyKeysCleared = true
}

const buildQueryKey = (language: SupportedLanguage) =>
  ["news", "feed", language] as const satisfies QueryKey

const fetchNewsSnapshot = async (
  language: SupportedLanguage,
  signal: AbortSignal | undefined,
  getCached: () => NewsFeedSnapshot | undefined | Promise<NewsFeedSnapshot | undefined>
) => {
  let cached: NewsFeedSnapshot | undefined
  const resolveCached = async () => {
    if (cached) return cached
    const maybeCached = await getCached()
    if (maybeCached) {
      cached = maybeCached
    }
    return cached
  }

  const previous = await resolveCached()
  const ifNoneMatch = previous?.etag ?? undefined

  try {
    const response = await fetchNews({ ifNoneMatch, signal })
    if (response.status === 304) {
      return (
        previous ??
        (await resolveCached()) ?? {
          items: [],
          etag: ifNoneMatch ?? null,
        }
      )
    }

    const items = parseNewsList(response.data)
    const etagHeader = response.headers?.etag
    const etag = typeof etagHeader === "string" ? etagHeader : null
    const snapshot: NewsFeedSnapshot = { items, etag }
    await persistCacheSnapshot(language, snapshot)
    return snapshot
  } catch (error) {
    if (signal?.aborted) {
      throw error
    }
    if (isAxiosError(error) && error.code === "ERR_CANCELED") {
      throw error
    }

    const fallback = (await resolveCached()) ?? previous
    if (fallback) {
      return fallback
    }
    throw error
  }
}

export const createNewsFeedQueryOptions = (
  queryClient: QueryClient,
  language: SupportedLanguage
) => {
  const queryKey = buildQueryKey(language)

  const options: UseQueryOptions<NewsFeedSnapshot, Error, NewsItem[], NewsFeedQueryKey> = {
    queryKey,
    queryFn: async ({ signal }) =>
      fetchNewsSnapshot(
        language,
        signal,
        () => queryClient.getQueryData<NewsFeedSnapshot>(queryKey) ?? readCacheSnapshot(language)
      ),
    select: (snapshot) => snapshot.items,
    placeholderData: (previous) => previous,
    staleTime: 2 * 60_000,
    gcTime: 30 * 60_000,
    networkMode: "offlineFirst",
    retry: (failureCount, error) => {
      if (isAxiosError(error) && error.response?.status && error.response.status < 500) {
        return false
      }
      return failureCount < 2
    },
  }

  return options
}

export const useNewsFeed = (language: SupportedLanguage) => {
  const queryClient = useQueryClient()

  const queryOptions = useMemo(
    () => createNewsFeedQueryOptions(queryClient, language),
    [queryClient, language]
  )
  const queryKey = queryOptions.queryKey

  useEffect(() => {
    clearLegacyStorageKeys()
  }, [])

  useEffect(() => {
    let cancelled = false
    const syncFromCache = async () => {
      const existing = queryClient.getQueryData<NewsFeedSnapshot>(queryKey)
      if (existing?.items?.length) return
      const cached = await readCacheSnapshot(language)
      if (cancelled || !cached) return
      queryClient.setQueryData(queryKey, cached)
    }
    void syncFromCache()
    return () => {
      cancelled = true
    }
  }, [language, queryClient, queryKey])

  const query = useQuery(queryOptions)

  return query
}

export type UseNewsFeedResult = ReturnType<typeof useNewsFeed>
export type NewsFeedQueryKey = ReturnType<typeof buildQueryKey>

export const newsFeedQueryKey = buildQueryKey

export const invalidateNewsFeed = async (queryClient: QueryClient, language: SupportedLanguage) => {
  const queryKey = buildQueryKey(language)
  await deleteCacheSnapshot(language)
  await queryClient.invalidateQueries({ queryKey, refetchType: "all" })
}
