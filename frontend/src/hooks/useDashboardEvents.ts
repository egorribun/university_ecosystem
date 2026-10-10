import { useMemo } from "react"
import {
  useQuery,
  useQueryClient,
  type QueryClient,
  type QueryFunction,
} from "@tanstack/react-query"

import api from "@/api/client"
import type { Event } from "@/types/Event"
import type { PaginatedResponse } from "@/types/Pagination"

export type DashboardEvent = Pick<Event, "id" | "title" | "starts_at" | "location">
export type DashboardEventsSnapshot = { items: DashboardEvent[] }

const DASHBOARD_EVENTS_ETAG_KEY = "dashboard:events"

export const dashboardEventsQueryKey = ["dashboard", "events"] as const

type DashboardEventsQueryKey = typeof dashboardEventsQueryKey

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value)

const toDashboardEvent = (event: DashboardEvent): DashboardEvent => ({
  id: event.id,
  title: event.title,
  starts_at: event.starts_at,
  ...(event.location === undefined ? {} : { location: event.location }),
})

/** Validate and project cached or serialized data onto the dashboard display contract. */
export function projectDashboardEventsSnapshot(
  value: unknown
): DashboardEventsSnapshot | undefined {
  if (!isRecord(value) || !Array.isArray(value.items)) return undefined

  const items: DashboardEvent[] = []
  for (const item of value.items) {
    if (!isRecord(item)) return undefined
    const { id, title, starts_at: startsAt, location } = item
    if (
      typeof id !== "string" ||
      typeof title !== "string" ||
      typeof startsAt !== "string" ||
      (location !== undefined && location !== null && typeof location !== "string")
    ) {
      return undefined
    }
    items.push({
      id,
      title,
      starts_at: startsAt,
      ...(location === undefined ? {} : { location }),
    })
  }

  return { items }
}

const ensureEventList = (payload: PaginatedResponse<Event> | null | undefined): Event[] => {
  if (!payload) {
    return []
  }
  const items = Array.isArray(payload.items) ? payload.items : []
  return items.filter(Boolean)
}

const sortEventsByStart = (items: Event[]): Event[] => {
  return [...items]
    .filter((event) => Boolean(event?.starts_at))
    .sort((a, b) => String(a.starts_at).localeCompare(String(b.starts_at)))
    .slice(0, 30)
}

const getSafePrevious = (queryClient: QueryClient) =>
  projectDashboardEventsSnapshot(queryClient.getQueryData(dashboardEventsQueryKey))

const createEventsQueryFn = (
  queryClient: QueryClient
): QueryFunction<DashboardEventsSnapshot, DashboardEventsQueryKey> => {
  return async ({ signal }) => {
    try {
      const response = await api.get<PaginatedResponse<Event>>("/events", {
        params: { is_active: true, limit: 50 },
        signal,
        validateStatus: (status: number) => status >= 200 && status < 400,
        etagCacheKey: DASHBOARD_EVENTS_ETAG_KEY,
      } as Parameters<typeof api.get>[1])

      if (response.status === 304) {
        const previous = getSafePrevious(queryClient)
        if (previous) return previous
      }

      const items = sortEventsByStart(ensureEventList(response.data)).map(toDashboardEvent)
      return { items }
    } catch (error) {
      if (signal?.aborted) throw error
      const fallback = getSafePrevious(queryClient)
      if (fallback) return fallback
      throw error
    }
  }
}

export const createDashboardEventsQueryOptions = (queryClient: QueryClient) => {
  const queryFn = createEventsQueryFn(queryClient)

  return {
    queryKey: dashboardEventsQueryKey,
    queryFn,
    select: (snapshot: DashboardEventsSnapshot) => snapshot.items,
    placeholderData: (previous: DashboardEventsSnapshot | undefined) => previous,
    staleTime: 2 * 60_000,
    gcTime: 30 * 60_000,
  } as const
}

export const useDashboardEvents = () => {
  const queryClient = useQueryClient()

  const queryOptions = useMemo(() => createDashboardEventsQueryOptions(queryClient), [queryClient])

  return useQuery(queryOptions)
}

export const prefetchDashboardEvents = (queryClient: QueryClient) =>
  queryClient.prefetchQuery(createDashboardEventsQueryOptions(queryClient))
