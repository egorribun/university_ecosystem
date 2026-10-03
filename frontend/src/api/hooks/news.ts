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
 *  1. ``placeholderData`` from ``StorageItem("news:list:account:<userId>:<lang>")``
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
import { getConfirmedUserId } from "@/stores/authIdentity"
import { captureSessionEpoch, getSessionEpoch } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { pickPrivateListControls, type PrivateListControls } from "./privateListControls"

/** Server-side default page size; mirror this in tests + msw handlers. */
export const NEWS_PAGE_SIZE = 12

const getCurrentConfirmedUserId = () => getConfirmedUserId(useAuthStore.getState())

export type NewsListFilters = {
  language: string
  limit?: number
}

type NormalizedNewsListFilters = {
  language: string
  limit: number
}

/**
 * Normalise the caller-provided page size before it participates in a query
 * key or request.  Keeping this as a pure named helper makes the boundary
 * contract explicit for both consumers and mutation tests.
 */
export const normalizeNewsListLimit = (value: number | undefined): number => {
  if (typeof value === "number" && Number.isFinite(value) && value >= 1) {
    return Math.floor(value)
  }
  return NEWS_PAGE_SIZE
}

const normalizeNewsListFilters = (filters: NewsListFilters): NormalizedNewsListFilters => {
  return {
    language: filters.language,
    limit: normalizeNewsListLimit(filters.limit),
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
  limit: number,
  owner: string | null
): PaginatedResponse<NewsItem> | null => {
  if (typeof window === "undefined" || !owner || getCurrentConfirmedUserId() !== owner) return null
  // Never adopt the legacy shared entry: its is_liked values have no owner.
  const items = new StorageItem<NewsItem[]>(
    `news:list:account:${encodeURIComponent(owner)}:${language}`
  ).get()
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

/**
 * Return the cursor for the next news page, treating an absent page as the
 * terminal state.  TanStack Query normally supplies a page object here, but
 * keeping the guard explicit makes the pagination contract safe for hydrated
 * or manually seeded cache data as well.
 */
export const getNewsNextPageParam = (
  lastPage: PaginatedResponse<NewsItem> | null | undefined
): string | null => {
  if (!lastPage) return null
  return lastPage.next_cursor ?? null
}

/**
 * Resolve the latest cached page without exposing an undefined array access
 * to callers.  The wider element type is intentional: persisted or manually
 * seeded query data can contain a nullish tail even though API responses are
 * validated before normal use.
 */
export const getLatestNewsPage = (
  pages: readonly (PaginatedResponse<NewsItem> | null | undefined)[] | undefined
): PaginatedResponse<NewsItem> | null => {
  if (!pages || pages.length === 0) return null
  return pages[pages.length - 1] ?? null
}

const createNewsListQueryFn =
  (
    queryClient: QueryClient,
    normalized: NormalizedNewsListFilters,
    queryKey: NewsListQueryKey,
    owner: string | null
  ) =>
  async ({ pageParam, signal }: { pageParam?: string | null; signal?: AbortSignal }) => {
    const currentEpoch = captureSessionEpoch()
    const ownsSession = () =>
      typeof window === "undefined" ||
      (owner !== null && currentEpoch() && getCurrentConfirmedUserId() === owner)
    if (!ownsSession()) throw new DOMException("Session changed", "AbortError")
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
      // The generated client returns AxiosError values when throwOnError is
      // omitted. Let TanStack Query enter its error state so the persisted
      // offline snapshot can be selected instead of silently normalising the
      // transport failure into an empty successful page.
      throwOnError: true,
      validateStatus: (status: number) => status >= 200 && status < 400,
      ...(etagKey ? { etagCacheKey: etagKey } : {}),
    }

    const response = await newsListApiV1NewsGet(
      requestConfig as Parameters<typeof newsListApiV1NewsGet>[0]
    )

    if (!ownsSession()) throw new DOMException("Session changed", "AbortError")

    if (response.status === 304) {
      const cached =
        queryClient.getQueryData<InfiniteData<PaginatedResponse<NewsItem>, string | null>>(queryKey)
      return ensurePaginatedResponse(
        cached?.pages?.[0] ?? readPersistedNewsPage(normalized.language, normalized.limit, owner),
        normalized.limit
      )
    }

    return ensurePaginatedResponse(response.data as PaginatedResponse<NewsItem>, normalized.limit)
  }

type UseNewsListQueryOptions = PrivateListControls<
  UseInfiniteQueryOptions<
    PaginatedResponse<NewsItem>,
    Error,
    InfiniteData<PaginatedResponse<NewsItem>, string | null>,
    NewsListQueryKey,
    string | null
  >
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
 * @param options - Timing, enabled/retry/refetch, error presentation,
 *   notification, and pagination controls. Data sources, transformations,
 *   and query identity are owned by this hook. ``enabled`` defaults to true.
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
  const owner = useAuthStore(getConfirmedUserId)
  const epoch = getSessionEpoch()
  const isCurrentSession = useMemo(() => {
    const ownsEpoch = captureSessionEpoch()
    return () => epoch === getSessionEpoch() && ownsEpoch()
  }, [epoch])
  const queryKey = newsListQueryKey(filters)
  const { enabled = true, ...rest } = pickPrivateListControls(options)

  // The query closure is cheap and must follow the normalized filter object on
  // every render. Keeping it direct also avoids a stale placeholder/query
  // contract when a caller changes locale or page size in place.
  const queryFn = createNewsListQueryFn(queryClient, normalized, queryKey, owner)

  // Read once per locale/page-size pair. SSR can hydrate an already-created
  // query with an empty/error result, in which case TanStack Query does not
  // apply `placeholderData`; the same snapshot is therefore also used below
  // as the final offline fallback.
  const persistedPage = useMemo(
    () =>
      isCurrentSession()
        ? readPersistedNewsPage(normalized.language, normalized.limit, owner)
        : null,
    [normalized.language, normalized.limit, owner, isCurrentSession]
  )

  // Read from localStorage as fallback for offline mode
  const placeholderData = persistedPage
    ? {
        pages: [persistedPage],
        pageParams: [null],
      }
    : undefined

  const query = useInfiniteQuery<
    PaginatedResponse<NewsItem>,
    Error,
    InfiniteData<PaginatedResponse<NewsItem>, string | null>,
    NewsListQueryKey,
    string | null
  >({
    staleTime: 30_000,
    ...rest,
    queryKey,
    enabled: (typeof window === "undefined" || owner !== null) && enabled,
    initialPageParam: null as string | null,
    getNextPageParam: getNewsNextPageParam,
    queryFn,
    placeholderData,
    // A tab can observe a changed origin-wide session before the auth broadcast
    // arrives. Do not expose its previously warm list through this observer.
    select: (data) => {
      if (!isCurrentSession()) return { pages: [], pageParams: [] }
      return data
    },
  })

  const news = useMemo(() => {
    if (!isCurrentSession()) return []
    const liveNews = mergeNewsPages(query.data?.pages)
    if (liveNews.length > 0 || !query.isError) return liveNews
    return persistedPage?.items ?? []
  }, [persistedPage, query.data, query.isError, isCurrentSession])
  let pagination: PaginatedResponse<NewsItem> | null = null
  const queryData = query.data
  if (queryData) {
    pagination = getLatestNewsPage(queryData.pages)
  }

  useEffect(() => {
    if (
      !query.isSuccess ||
      query.isPlaceholderData ||
      !owner ||
      !isCurrentSession() ||
      getCurrentConfirmedUserId() !== owner
    )
      return
    new StorageItem<NewsItem[]>(
      `news:list:account:${encodeURIComponent(owner)}:${normalized.language}`
    ).set(news)
  }, [news, normalized.language, query.isPlaceholderData, query.isSuccess, owner, isCurrentSession])

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
  const queryKey = newsListQueryKey(filters)
  const queryFn = createNewsListQueryFn(
    queryClient,
    normalized,
    queryKey,
    getCurrentConfirmedUserId()
  )

  return queryClient.prefetchInfiniteQuery({
    queryKey,
    queryFn,
    initialPageParam: null as string | null,
    getNextPageParam: getNewsNextPageParam,
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
