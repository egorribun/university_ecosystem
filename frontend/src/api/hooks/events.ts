import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
  useSuspenseQuery,
  type InfiniteData,
  type QueryClient,
  type UseInfiniteQueryOptions,
  type UseInfiniteQueryResult,
  type UseQueryOptions,
  type UseQueryResult,
  type UseSuspenseQueryResult,
} from "@tanstack/react-query"
import { useMemo } from "react"

import { allEventsApiV1EventsGet, myEventsApiV1EventsMyGet } from "@/api/generated/sdk.gen"
import type { Event } from "@/types/Event"
import type { PaginatedResponse } from "@/types/Pagination"
import { StorageItem } from "@/utils/storage"

export const EVENTS_PAGE_SIZE = 12

export type EventsListFilters = {
  language: string
  is_active?: boolean | null
  search?: string
  location?: string
  limit?: number
}

type NormalizedEventsListFilters = {
  language: string
  is_active: boolean | null
  search: string
  location: string
  limit: number
}

const normalizeEventsListFilters = (filters: EventsListFilters): NormalizedEventsListFilters => {
  const normalizeBoolean = (value: boolean | null | undefined) =>
    typeof value === "boolean" ? value : null

  const normalizeLimit = (value: number | undefined) => {
    if (typeof value === "number" && Number.isFinite(value) && value > 0) {
      return Math.floor(value)
    }
    return EVENTS_PAGE_SIZE
  }

  return {
    language: filters.language,
    is_active: normalizeBoolean(filters.is_active ?? null),
    search: filters.search?.trim() ?? "",
    location: filters.location?.trim() ?? "",
    limit: normalizeLimit(filters.limit),
  }
}

type EventsListQueryKeyTuple = readonly ["events", "list", NormalizedEventsListFilters]

export type EventsListQueryKey = EventsListQueryKeyTuple

const createEventsListEtagKey = (filters: NormalizedEventsListFilters) => {
  const activity = filters.is_active === null ? "all" : filters.is_active ? "active" : "archive"
  return [
    "events",
    "list",
    filters.language,
    activity,
    filters.search,
    filters.location,
    filters.limit,
  ].join(":")
}

export const eventsListQueryKey = (filters: EventsListFilters) => {
  const normalized = normalizeEventsListFilters(filters)
  return ["events", "list", normalized] as EventsListQueryKey
}

const ensurePaginatedResponse = (
  payload: PaginatedResponse<Event> | null | undefined,
  fallbackLimit: number
): PaginatedResponse<Event> => {
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

const mergeEventPages = (pages: PaginatedResponse<Event>[] | undefined): Event[] => {
  if (!pages?.length) {
    return []
  }

  const positions = new Map<string, number>()
  const merged: Event[] = []

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

const createEventsListQueryFn =
  (
    queryClient: QueryClient,
    normalized: NormalizedEventsListFilters,
    queryKey: EventsListQueryKey
  ) =>
  async ({ pageParam, signal }: { pageParam?: string | null; signal?: AbortSignal }) => {
    const etagKey = pageParam == null ? createEventsListEtagKey(normalized) : undefined
    const params: Record<string, unknown> = {
      limit: normalized.limit,
      search: normalized.search,
      location: normalized.location,
    }
    if (normalized.is_active !== null) {
      params.is_active = normalized.is_active
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

    const response = await allEventsApiV1EventsGet(
      requestConfig as Parameters<typeof allEventsApiV1EventsGet>[0]
    )

    if (response.status === 304) {
      const cached =
        queryClient.getQueryData<InfiniteData<PaginatedResponse<Event>, string | null>>(queryKey)
      return ensurePaginatedResponse(cached?.pages?.[0], normalized.limit)
    }

    return ensurePaginatedResponse(response.data, normalized.limit)
  }

type UseEventsListQueryOptions = Omit<
  UseInfiniteQueryOptions<
    PaginatedResponse<Event>,
    Error,
    InfiniteData<PaginatedResponse<Event>, string | null>,
    EventsListQueryKey,
    string | null
  >,
  "queryKey" | "queryFn" | "initialPageParam" | "getNextPageParam"
>

export type UseEventsListQueryResult = UseInfiniteQueryResult<
  InfiniteData<PaginatedResponse<Event>, string | null>,
  Error
> & {
  events: Event[]
  pagination: PaginatedResponse<Event> | null
  queryKey: EventsListQueryKey
}

export const useEventsListQuery = (
  filters: EventsListFilters,
  options?: UseEventsListQueryOptions
): UseEventsListQueryResult => {
  const queryClient = useQueryClient()
  const normalized = normalizeEventsListFilters(filters)
  const queryKey: EventsListQueryKey = useMemo(() => ["events", "list", normalized], [normalized])
  const { enabled = true, ...rest } = options ?? {}

  const queryFn = useMemo(
    () => createEventsListQueryFn(queryClient, normalized, queryKey),
    [queryClient, normalized, queryKey]
  )

  // Read from localStorage as fallback for offline mode
  const placeholderData = useMemo(() => {
    if (typeof window === "undefined") return undefined
    const activity =
      normalized.is_active === null ? "all" : normalized.is_active ? "active" : "archive"
    // StorageItem#get is itself fail-closed (including blocked browser storage
    // getters). Keeping this read path free of a second catch makes the
    // persistence contract single-owner and prevents an unexpected adapter
    // implementation from silently bypassing the typed fallback below.
    const storage = new StorageItem<Event[]>(`events:list:${normalized.language}:${activity}`)
    const items = storage.get()
    if (!Array.isArray(items) || items.length === 0) return undefined
    return {
      pages: [
        {
          items,
          total: items.length,
          limit: normalized.limit,
          cursor: null,
          next_cursor: null,
          has_more: false,
        },
      ],
      pageParams: [null],
    }
  }, [normalized.language, normalized.is_active, normalized.limit])

  const query = useInfiniteQuery<
    PaginatedResponse<Event>,
    Error,
    InfiniteData<PaginatedResponse<Event>, string | null>,
    EventsListQueryKey,
    string | null
  >({
    queryKey,
    enabled,
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage: PaginatedResponse<Event>) => lastPage?.next_cursor ?? null,
    queryFn,
    placeholderData,
    ...rest,
  })

  const events = useMemo(() => mergeEventPages(query.data?.pages), [query.data])
  const pagination = query.data?.pages?.[query.data.pages.length - 1] ?? null

  return {
    ...query,
    events,
    pagination,
    queryKey,
  }
}

export const prefetchEventsListQuery = (queryClient: QueryClient, filters: EventsListFilters) => {
  const normalized = normalizeEventsListFilters(filters)
  const queryKey: EventsListQueryKey = ["events", "list", normalized]
  const queryFn = createEventsListQueryFn(queryClient, normalized, queryKey)

  return queryClient.prefetchInfiniteQuery({
    queryKey,
    queryFn,
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage: PaginatedResponse<Event>) => lastPage?.next_cursor ?? null,
  })
}

export type MyEventsQueryParams = {
  language: string
  userId?: string | null
}

type NormalizedMyEventsParams = {
  language: string
  userId: string | null
}

const normalizeMyEventsParams = (params: MyEventsQueryParams): NormalizedMyEventsParams => ({
  language: params.language,
  userId: params.userId ?? null,
})

type MyEventsQueryKeyTuple = readonly ["events", "my", NormalizedMyEventsParams]

export type MyEventsQueryKey = MyEventsQueryKeyTuple

const createMyEventsEtagKey = (params: NormalizedMyEventsParams) =>
  ["events", "my", params.language, params.userId ?? "anon"].join(":")

export const myEventsQueryKey = (params: MyEventsQueryParams) => {
  const normalized = normalizeMyEventsParams(params)
  return ["events", "my", normalized] as MyEventsQueryKey
}

type UseMyEventsQueryOptions = Omit<
  UseQueryOptions<Event[], Error, Event[], MyEventsQueryKey>,
  "queryKey" | "queryFn"
>

export type UseMyEventsQueryResult = UseQueryResult<Event[], Error> & {
  queryKey: MyEventsQueryKey
}

export const useMyEventsQuery = (
  params: MyEventsQueryParams,
  options?: UseMyEventsQueryOptions
): UseMyEventsQueryResult => {
  const queryClient = useQueryClient()
  const normalized = normalizeMyEventsParams(params)
  const queryKey: MyEventsQueryKey = ["events", "my", normalized]
  const { enabled = true, ...rest } = options ?? {}
  const effectiveEnabled = enabled && normalized.userId != null

  const placeholderData = useMemo(() => {
    if (typeof window === "undefined") return undefined
    try {
      const storage = new StorageItem<Event[]>(
        `events:my:${normalized.language}:${normalized.userId}`
      )
      const items = storage.get()
      return Array.isArray(items) ? items : undefined
    } catch {
      return undefined
    }
  }, [normalized.language, normalized.userId])

  const query = useQuery<Event[], Error, Event[], MyEventsQueryKey>({
    queryKey,
    enabled: effectiveEnabled,
    placeholderData,
    queryFn: async ({ signal }) => {
      const etagKey = createMyEventsEtagKey(normalized)
      const config = {
        signal,
        validateStatus: (status: number) => status >= 200 && status < 400,
        etagCacheKey: etagKey,
      }

      const response = await myEventsApiV1EventsMyGet(
        config as Parameters<typeof myEventsApiV1EventsMyGet>[0]
      )

      if (response.status === 304) {
        return queryClient.getQueryData<Event[]>(queryKey) ?? []
      }

      return Array.isArray(response.data) ? (response.data as Event[]) : []
    },
    ...rest,
  })

  return {
    ...query,
    queryKey,
  }
}

// ---------------------------------------------------------------------------
// MOD-23-02 (audit 2026-03-25 Wave 23): Suspense-compatible event query.
//
// Use inside a <Suspense> boundary when offline fallback and conditional
// fetching (enabled) are NOT needed.  `data` is guaranteed defined — no
// loading/error states to handle in the component.
//
// NOTE: useSuspenseQuery does NOT support `enabled`, `placeholderData`, or
// `throwOnError`.  If you need offline fallback, use useMyEventsQuery instead.
// ---------------------------------------------------------------------------

type MySuspenseEventsParams = {
  language: string
  userId: string
}

export type UseSuspenseMyEventsResult = UseSuspenseQueryResult<Event[], Error> & {
  queryKey: MyEventsQueryKey
}

export const useSuspenseMyEventsQuery = (
  params: MySuspenseEventsParams
): UseSuspenseMyEventsResult => {
  const queryClient = useQueryClient()
  const normalized = normalizeMyEventsParams(params)
  const queryKey: MyEventsQueryKey = ["events", "my", normalized]

  const query = useSuspenseQuery<Event[], Error, Event[], MyEventsQueryKey>({
    queryKey,
    queryFn: async ({ signal }) => {
      const etagKey = createMyEventsEtagKey(normalized)
      const config = {
        signal,
        validateStatus: (status: number) => status >= 200 && status < 400,
        etagCacheKey: etagKey,
      }

      const response = await myEventsApiV1EventsMyGet(
        config as Parameters<typeof myEventsApiV1EventsMyGet>[0]
      )

      if (response.status === 304) {
        return queryClient.getQueryData<Event[]>(queryKey) ?? []
      }

      return Array.isArray(response.data) ? (response.data as Event[]) : []
    },
  })

  return {
    ...query,
    queryKey,
  }
}

// ---------------------------------------------------------------------------
// EVENT DETAIL QUERY (Wave 76; Wave 129 SW2 factory extraction)
// ---------------------------------------------------------------------------

type EventDetailQueryKey = readonly ["events", "detail", string]

export type UseEventDetailQueryResult = UseQueryResult<Event, Error>

/**
 * Pure query options factory for a single event by id. Used by both:
 *
 *   - `useEventDetailQuery` (component context, with `enabled: !!id` guard)
 *   - `/events/$id` route loader for SSR pre-fetch via
 *     `queryClient.ensureQueryData(eventDetailQueryOptions(params.id))`
 *
 * Caller is responsible for passing a defined id. The route loader path
 * always has a defined `params.id` (TanStack Router params validation);
 * the hook path handles `undefined` separately via the `enabled` guard.
 *
 * `staleTime: 60_000` matches the prior in-hook config; retry 1 limits
 * SSR loader latency on network blips. Dynamic-imported SDK keeps the
 * detail-route bundle lean — hot path on /events/$id only.
 */
export const eventDetailQueryOptions = (id: string) => ({
  queryKey: ["events", "detail", id] as EventDetailQueryKey,
  queryFn: async ({ signal }: { signal?: AbortSignal }): Promise<Event> => {
    const { getEventApiV1EventsEventIdGet } = await import("@/api/generated/sdk.gen")
    const response = await getEventApiV1EventsEventIdGet({
      path: { event_id: id },
      signal,
    } as Parameters<typeof getEventApiV1EventsEventIdGet>[0])
    return response.data as Event
  },
  staleTime: 60_000,
  retry: 1,
})

export const useEventDetailQuery = (
  id: string | undefined,
  options?: Omit<UseQueryOptions<Event, Error, Event, EventDetailQueryKey>, "queryKey" | "queryFn">
): UseEventDetailQueryResult => {
  const baseOptions = eventDetailQueryOptions(id ?? "")
  return useQuery<Event, Error, Event, EventDetailQueryKey>({
    ...baseOptions,
    enabled: !!id,
    ...options,
  })
}

// ---------------------------------------------------------------------------
// EVENT NAVIGATION (Wave 76)
// Reads from cached events list to determine prev/next event.
// Pattern source: hooks/useArticleNavigation.ts
// ---------------------------------------------------------------------------

interface EventNav {
  prevId: string | null
  nextId: string | null
  prevTitle: string | null
  nextTitle: string | null
}

export function useEventNavigation(currentId: string): EventNav {
  const queryClient = useQueryClient()

  return useMemo(() => {
    const fallback: EventNav = { prevId: null, nextId: null, prevTitle: null, nextTitle: null }

    const queries = queryClient.getQueriesData<{
      pages?: Array<{ items?: Event[] }>
    }>({
      queryKey: ["events", "list"],
    })

    const allItems: Event[] = queries.flatMap(
      ([, data]) =>
        data?.pages?.flatMap((page) => page.items ?? new Array<Event>()) ?? new Array<Event>()
    )

    // Deduplicate preserving order
    const seen = new Set<string>()
    const orderedById = new Map<string, Event>()
    for (const item of allItems) {
      if (!seen.has(item.id)) {
        seen.add(item.id)
        orderedById.set(item.id, item)
      }
    }
    const ordered = Array.from(orderedById.values())

    const currentIndex = ordered.findIndex((e) => e.id === currentId)
    if (currentIndex === -1) return fallback

    // `currentIndex` is known to be in bounds above. Indexing with nullish
    // fallback keeps the boundary contract explicit without duplicating
    // arithmetic comparisons that can drift from the array semantics.
    const prev = ordered[currentIndex - 1] ?? null
    const next = ordered[currentIndex + 1] ?? null

    return {
      prevId: prev?.id ?? null,
      nextId: next?.id ?? null,
      prevTitle: prev?.title ?? null,
      nextTitle: next?.title ?? null,
    }
  }, [queryClient, currentId])
}
