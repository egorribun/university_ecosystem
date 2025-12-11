import {
    useInfiniteQuery,
    useQuery,
    useQueryClient,
    type InfiniteData,
    type QueryClient,
    type UseInfiniteQueryOptions,
    type UseInfiniteQueryResult,
} from "@tanstack/react-query"
import { useMemo } from "react"

import { apiClient, type TypedRequestOptions } from "../client"
import type { NewsItem } from "@/api/news"
import type { PaginatedResponse } from "@/types/Pagination"

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
    return [
        "news",
        "list",
        filters.language,
        filters.limit,
    ].join(":")
}

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

    const positions = new Map<number, number>()
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
    (
        queryClient: QueryClient,
        normalized: NormalizedNewsListFilters,
        queryKey: NewsListQueryKey
    ) =>
        async ({ pageParam, signal }: { pageParam?: string | null; signal?: AbortSignal }) => {
            const etagKey = pageParam == null ? createNewsListEtagKey(normalized) : undefined
            const params: Record<string, unknown> = {
                limit: normalized.limit,
            }
            if (pageParam != null) {
                params.cursor = pageParam
            }

            const requestConfig: TypedRequestOptions<"/api/v1/news", "get"> = {
                params,
                signal,
                validateStatus: (status) => status >= 200 && status < 400,
                ...(etagKey ? { etagCacheKey: etagKey } : {}),
            }

            const response = await apiClient.get("/api/v1/news", requestConfig)

            if (response.status === 304) {
                const cached =
                    queryClient.getQueryData<InfiniteData<PaginatedResponse<NewsItem>, string | null>>(queryKey)
                return ensurePaginatedResponse(cached?.pages?.[0], normalized.limit)
            }

            return ensurePaginatedResponse(response.data as any, normalized.limit)
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
    const queryKey: NewsListQueryKey = ["news", "list", normalized]
    const { enabled = true, ...rest } = options ?? {}

    const queryFn = useMemo(
        () => createNewsListQueryFn(queryClient, normalized, queryKey),
        [queryClient, normalized, queryKey]
    )

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
