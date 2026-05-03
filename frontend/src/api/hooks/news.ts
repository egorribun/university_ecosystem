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
 */
import {
  useInfiniteQuery,
  useQueryClient,
  type InfiniteData,
  type QueryClient,
  type UseInfiniteQueryOptions,
  type UseInfiniteQueryResult,
} from "@tanstack/react-query"
import { useMemo } from "react"

import { newsListApiV1NewsGet } from "@/api/generated/sdk.gen"
import type { NewsItem } from "@/api/news"
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
      return ensurePaginatedResponse(cached?.pages?.[0], normalized.limit)
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
    if (typeof window === "undefined") return undefined
    try {
      const storage = new StorageItem<NewsItem[]>(`news:list:${normalized.language}`)
      const items = storage.get()
      if (!Array.isArray(items) || items.length === 0) return undefined
      // Wrap in the expected InfiniteData structure
      return {
        pages: [
          {
            items,
            total: items.length,
            limit: 12,
            cursor: null,
            next_cursor: null,
            has_more: false,
          },
        ],
        pageParams: [null],
      }
    } catch {
      return undefined
    }
  }, [normalized.language])

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

  return {
    ...query,
    news,
    pagination,
    queryKey,
  }
}
