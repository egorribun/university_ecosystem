/**
 * @fileoverview News list infinite-query hook + query-key factory.
 *
 * The news feed uses cursor-based pagination (server returns
 * `next_cursor` in the page payload) and per-language ETag caching.
 * On a 304 Not Modified response the queryFn falls back to the cached
 * first page from TanStack Query's cache, so a soft refetch never
 * re-renders empty pages.
 *
 * Query key shape: ``["news", "list", { language, limit }]`` —
 * ``newsListQueryKey()`` is the canonical factory; never hand-write
 * keys, otherwise cache invalidation across components misses.
 *
 * Filters are NORMALISED before keying (limit defaulted to
 * NEWS_PAGE_SIZE, NaN/negative values clamped). This means
 * ``useNewsListQuery({ language, limit: undefined })`` and
 * ``useNewsListQuery({ language, limit: 12 })`` share the same cache.
 *
 * Cache layers (outermost first):
 *  1. ``placeholderData`` from ``StorageItem("news:list:<lang>")``
 *     — populated by the news detail/list pages on a successful load,
 *     served on cold mount in offline mode so the user sees something
 *     before the network resolves.
 *  2. TanStack Query's in-memory cache (``staleTime: 30_000``) — keeps
 *     subsequent mounts within 30 s from refetching, matches the news
 *     interaction query so likes/bookmarks don't trigger a list reload.
 *  3. Server-side ETag cache key ``"news:list:<language>:<limit>"``
 *     — only the first page (``pageParam == null``) participates;
 *     subsequent cursor pages bypass the ETag layer because their
 *     payloads are unique by cursor.
 */
import {
  useInfiniteQuery,
  useQueryClient,
  type InfiniteData,
  type QueryClient,
  type UseInfiniteQueryOptions,
  type UseInfiniteQueryResult,
} from "@tanstack/react-query"
import { useEffect, useMemo } from "react"

import { newsListApiV1NewsGet } from "@/api/generated/sdk.gen"
import { fetchNewsItem, type NewsItem } from "@/api/news"
import type { PaginatedResponse } from "@/types/Pagination"
import { StorageItem } from "@/utils/storage"

/** Server-side default page size; mirror this in tests + msw handlers. */
export const NEWS_PAGE_SIZE = 12

export type NewsListFilters = {
  language: string
  limit?: number
}

type NormalizedNewsListFilters = {
  language: string
  limit: number
}

const normalizeNewsListFilters = (filters: NewsListFilters): NormalizedNewsListFilters => {
  const normalizeLimit = (value: number | undefined) => {
    if (typeof value === "number" && Number.isFinite(value) && value > 0) {
      return Math.floor(value)
    }
    return NEWS_PAGE_SIZE
  }

  return {
    language: filters.language,
    limit: normalizeLimit(filters.limit),
  }
}

type NewsListQueryKeyTuple = readonly ["news", "list", NormalizedNewsListFilters]

export type NewsListQueryKey = NewsListQueryKeyTuple

const createNewsListEtagKey = (filters: NormalizedNewsListFilters) => {
  return ["news", "list", filters.language, filters.limit].join(":")
}

/**
 * Canonical TanStack Query key factory for the news list.
 *
 * Always use this factory rather than hand-rolling the tuple — it
 * normalises ``filters.limit`` so callers passing ``undefined`` and
 * callers passing the explicit page size land on the same cache entry.
 *
 * @param filters - Per-call filters: ``language`` is required, ``limit``
 *   defaults to ``NEWS_PAGE_SIZE``.
 * @returns Tuple ``["news", "list", normalized]`` suitable for
 *   ``queryClient.invalidateQueries({ queryKey })`` etc.
 */
export const newsListQueryKey = (filters: NewsListFilters) => {
  const normalized = normalizeNewsListFilters(filters)
  return ["news", "list", normalized] as NewsListQueryKey
}

const ensurePaginatedResponse = (
  payload: PaginatedResponse<NewsItem> | null | undefined,
  fallbackLimit: number
): PaginatedResponse<NewsItem> => {
  if (!payload) {
    return {
      items: [],
      total: 0,
      limit: fallbackLimit,
      cursor: null,
      next_cursor: null,
      has_more: false,
    }
  }

  const items = Array.isArray(payload.items) ? payload.items : []
  const total = typeof payload.total === "number" ? payload.total : items.length
  const limit = typeof payload.limit === "number" ? payload.limit : fallbackLimit

  return {
    items,
    total,
    limit,
    cursor: payload.cursor ?? null,
    next_cursor: payload.next_cursor ?? null,
    has_more: Boolean(payload.has_more),
  }
}

const readPersistedNewsPage = (
  language: string,
  limit: number
): PaginatedResponse<NewsItem> | null => {
  if (typeof window === "undefined") return null
  const items = new StorageItem<NewsItem[]>(`news:list:${language}`).get()
  if (!Array.isArray(items) || items.length === 0) return null
  return {
    items,
    total: items.length,
    limit,
    cursor: null,
    next_cursor: null,
    has_more: false,
  }
}

const mergeNewsPages = (pages: PaginatedResponse<NewsItem>[] | undefined): NewsItem[] => {
  if (!pages?.length) {
    return []
  }

  const positions = new Map<string, number>()
  const merged: NewsItem[] = []

  for (const page of pages) {
    for (const item of page.items) {
      const existingIndex = positions.get(item.id)
      if (existingIndex != null) {
        merged[existingIndex] = item
      } else {
        positions.set(item.id, merged.length)
        merged.push(item)
      }
    }
  }

  return merged
}

const createNewsListQueryFn =
  (queryClient: QueryClient, normalized: NormalizedNewsListFilters, queryKey: NewsListQueryKey) =>
  async ({ pageParam, signal }: { pageParam?: string | null; signal?: AbortSignal }) => {
    const etagKey = pageParam == null ? createNewsListEtagKey(normalized) : undefined
    const params: Record<string, unknown> = {
      limit: normalized.limit,
    }
    if (pageParam != null) {
      params.cursor = pageParam
    }

    const requestConfig = {
      query: params,
      signal,
      validateStatus: (status: number) => status >= 200 && status < 400,
      ...(etagKey ? { etagCacheKey: etagKey } : {}),
    }

    const response = await newsListApiV1NewsGet(
      requestConfig as Parameters<typeof newsListApiV1NewsGet>[0]
    )

    if (response.status === 304) {
      const cached =
        queryClient.getQueryData<InfiniteData<PaginatedResponse<NewsItem>, string | null>>(queryKey)
      return ensurePaginatedResponse(
        cached?.pages?.[0] ?? readPersistedNewsPage(normalized.language, normalized.limit),
        normalized.limit
      )
    }

    return ensurePaginatedResponse(response.data as PaginatedResponse<NewsItem>, normalized.limit)
  }

type UseNewsListQueryOptions = Omit<
  UseInfiniteQueryOptions<
    PaginatedResponse<NewsItem>,
    Error,
    InfiniteData<PaginatedResponse<NewsItem>, string | null>,
    NewsListQueryKey,
    string | null
  >,
  "queryKey" | "queryFn" | "initialPageParam" | "getNextPageParam"
>

export type UseNewsListQueryResult = UseInfiniteQueryResult<
  InfiniteData<PaginatedResponse<NewsItem>, string | null>,
  Error
> & {
  news: NewsItem[]
  pagination: PaginatedResponse<NewsItem> | null
  queryKey: NewsListQueryKey
}

/**
 * Infinite-query hook for the paginated news feed.
 *
 * Wraps ``@tanstack/react-query``'s ``useInfiniteQuery`` with the
 * project's cursor pagination + ETag + offline placeholder logic so
 * callers don't need to remember any of the wiring. Also flattens
 * ``query.data.pages`` into a deduplicated ``news`` array (last write
 * wins per ``id``) and exposes the latest page payload as ``pagination``
 * for cursor + total + has_more without indexing into ``pages``.
 *
 * @param filters - ``language`` is the i18n locale used for both the
 *   ETag cache key and the offline placeholder localStorage key.
 *   ``limit`` is optional; defaults to ``NEWS_PAGE_SIZE`` (12).
 * @param options - Standard ``useInfiniteQuery`` options EXCEPT
 *   ``queryKey``, ``queryFn``, ``initialPageParam`` and
 *   ``getNextPageParam`` — those are owned by this hook. ``enabled``
 *   defaults to ``true``.
 * @returns The full ``useInfiniteQuery`` result extended with:
 *   - ``news``: flattened, deduplicated array of ``NewsItem`` across
 *     all loaded pages (memoised on ``query.data``).
 *   - ``pagination``: the last loaded page's ``PaginatedResponse``,
 *     or ``null`` while still loading.
 *   - ``queryKey``: the canonical key for use with
 *     ``queryClient.invalidateQueries()`` etc.
 *
 * @example
 * const { news, fetchNextPage, hasNextPage, queryKey } =
 *   useNewsListQuery({ language: i18n.language })
 * // …
 * await queryClient.invalidateQueries({ queryKey })
 */
export const useNewsListQuery = (
  filters: NewsListFilters,
  options?: UseNewsListQueryOptions
): UseNewsListQueryResult => {
  const queryClient = useQueryClient()
  const normalized = normalizeNewsListFilters(filters)
  const queryKey: NewsListQueryKey = useMemo(() => ["news", "list", normalized], [normalized])
  const { enabled = true, ...rest } = options ?? {}

  const queryFn = useMemo(
    () => createNewsListQueryFn(queryClient, normalized, queryKey),
    [queryClient, normalized, queryKey]
  )

  // Read from localStorage as fallback for offline mode
  const placeholderData = useMemo(() => {
    const page = readPersistedNewsPage(normalized.language, normalized.limit)
    if (!page) return undefined
    return {
      pages: [page],
      pageParams: [null],
    }
  }, [normalized.language, normalized.limit])

  const query = useInfiniteQuery<
    PaginatedResponse<NewsItem>,
    Error,
    InfiniteData<PaginatedResponse<NewsItem>, string | null>,
    NewsListQueryKey,
    string | null
  >({
    queryKey,
    enabled,
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage: PaginatedResponse<NewsItem>) => lastPage?.next_cursor ?? null,
    queryFn,
    staleTime: 30_000, // 30s — matches interaction query; prevents refetch on mount/focus
    placeholderData,
    ...rest,
  })

  const news = useMemo(() => mergeNewsPages(query.data?.pages), [query.data])
  const pagination = query.data?.pages?.[query.data.pages.length - 1] ?? null

  useEffect(() => {
    if (!query.isSuccess || query.isPlaceholderData) return
    new StorageItem<NewsItem[]>(`news:list:${normalized.language}`).set(news)
  }, [news, normalized.language, query.isPlaceholderData, query.isSuccess])

  return {
    ...query,
    news,
    pagination,
    queryKey,
  }
}

/**
 * Pre-fetch the first page of the news feed into the given QueryClient
 * for server-side rendering loaders. Mirrors `prefetchEventsListQuery`
 * (events.ts:261-272) — same cursor-pagination shape (`initialPageParam:
 * null`, `getNextPageParam: lastPage?.next_cursor ?? null`) so the SSR
 * pre-fetched page is the same identity that `useNewsListQuery` reads
 * on the client (per-request QueryClient via SsrRoot, W128 SW3).
 *
 * First page only — `prefetchInfiniteQuery` defaults to `pages: 1`.
 * Multi-page prefetch is possible via `{ pages: 2 }` but adds
 * 200-400ms per extra page to server-time, with diminishing LCP
 * return; W129 sticks with first-page-only for the LCP-perf balance.
 *
 * Reuses `createNewsListQueryFn` (the same closure useNewsListQuery
 * builds inside `useMemo`) so ETag cache key resolution + 304-fallback
 * behaviour is shared across SSR + client paths.
 */
export const prefetchNewsListQuery = (queryClient: QueryClient, filters: NewsListFilters) => {
  const normalized = normalizeNewsListFilters(filters)
  const queryKey: NewsListQueryKey = ["news", "list", normalized]
  const queryFn = createNewsListQueryFn(queryClient, normalized, queryKey)

  return queryClient.prefetchInfiniteQuery({
    queryKey,
    queryFn,
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage: PaginatedResponse<NewsItem>) => lastPage?.next_cursor ?? null,
  })
}

// ---------------------------------------------------------------------------
// NEWS DETAIL QUERY (Wave 129 SW5 factory extraction)
//
// Pulled out of `pages/NewsDetail.tsx`'s inline `useQuery` + local `fetchNews`
// helper so the same options shape is shared across:
//   - The component (`useQuery({ ...newsDetailQueryOptions(id, language) })`)
//   - The /news/$id route loader (`queryClient.ensureQueryData(...)`) for SSR
//     pre-fetch into the per-request QueryClient (SsrRoot W128 SW3).
//
// Query key includes language because the article body has `title`/`content`
// + locale fallbacks (`title_en`/`content_en`) — different language requests
// could resolve to different displayed content even when the underlying
// resource id is the same. Matches the prior in-component key shape so
// existing cache entries continue to hit.
// ---------------------------------------------------------------------------

const fetchNewsDetail = async (id: string, signal?: AbortSignal): Promise<NewsItem> => {
  const response = await fetchNewsItem(id, { signal })
  if (response.status === 304) throw new Error("Not modified")
  if (!response.data) throw new Error("Item not found")
  return response.data
}

export const newsDetailQueryOptions = (id: string, language: string) => ({
  queryKey: ["news", id, language] as const,
  queryFn: ({ signal }: { signal?: AbortSignal }) => fetchNewsDetail(id, signal),
  staleTime: 60_000,
  retry: 1,
})
