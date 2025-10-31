import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
  type InfiniteData,
  type UseInfiniteQueryOptions,
  type UseInfiniteQueryResult,
  type UseQueryOptions,
  type UseQueryResult,
} from "@tanstack/react-query"
import { useMemo } from "react"

import api, { type ApiRequestConfig } from "../client"
import type { Event } from "@/types/Event"
import type { PaginatedResponse } from "@/types/Pagination"

export const EVENTS_PAGE_SIZE = 12

export type EventsListFilters = {
  language: string
  is_active?: boolean | null
  search?: string
  type?: string
  location?: string
  limit?: number
}

type NormalizedEventsListFilters = {
  language: string
  is_active: boolean | null
  search: string
  type: string
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
    type: filters.type?.trim() ?? "",
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
    filters.type,
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

  const positions = new Map<number, number>()
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
  const queryKey: EventsListQueryKey = ["events", "list", normalized]
  const { enabled = true, ...rest } = options ?? {}

  const query = useInfiniteQuery<
    PaginatedResponse<Event>,
    Error,
    InfiniteData<PaginatedResponse<Event>, string | null>,
    EventsListQueryKey,
    string | null
  >({
    queryKey,
    enabled,
    initialPageParam: null,
    getNextPageParam: (lastPage) => lastPage?.next_cursor ?? null,
    queryFn: async ({ pageParam, signal }) => {
      const etagKey = pageParam == null ? createEventsListEtagKey(normalized) : undefined
      const params: Record<string, unknown> = {
        limit: normalized.limit,
        search: normalized.search,
        type: normalized.type,
        location: normalized.location,
      }
      if (normalized.is_active !== null) {
        params.is_active = normalized.is_active
      }
      if (pageParam != null) {
        params.cursor = pageParam
      }

      const requestConfig: ApiRequestConfig = {
        params,
        signal,
        validateStatus: (status) => status >= 200 && status < 400,
      }
      if (etagKey) {
        requestConfig.etagCacheKey = etagKey
      }

      const response = await api.get<PaginatedResponse<Event>>("/events", requestConfig)

      if (response.status === 304) {
        const cached =
          queryClient.getQueryData<InfiniteData<PaginatedResponse<Event>, string | null>>(queryKey)
        return ensurePaginatedResponse(cached?.pages?.[0], normalized.limit)
      }

      return ensurePaginatedResponse(response.data, normalized.limit)
    },
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

export type MyEventsQueryParams = {
  language: string
  userId?: number | string | null
}

type NormalizedMyEventsParams = {
  language: string
  userId: number | string | null
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

  const query = useQuery<Event[], Error, Event[], MyEventsQueryKey>({
    queryKey,
    enabled: effectiveEnabled,
    queryFn: async ({ signal }) => {
      const etagKey = createMyEventsEtagKey(normalized)
      const config: ApiRequestConfig = {
        signal,
        validateStatus: (status) => status >= 200 && status < 400,
        etagCacheKey: etagKey,
      }

      const response = await api.get<Event[]>("/events/my", config)

      if (response.status === 304) {
        return queryClient.getQueryData<Event[]>(queryKey) ?? []
      }

      return Array.isArray(response.data) ? response.data : []
    },
    ...rest,
  })

  return {
    ...query,
    queryKey,
  }
}
