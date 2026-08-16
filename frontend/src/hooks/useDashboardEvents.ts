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

type EventsSnapshot = {
  items: Event[]
}

const DASHBOARD_EVENTS_ETAG_KEY = "dashboard:events"

export const dashboardEventsQueryKey = ["dashboard", "events"] as const

type DashboardEventsQueryKey = typeof dashboardEventsQueryKey

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

const createEventsQueryFn = (
  queryClient: QueryClient
): QueryFunction<EventsSnapshot, DashboardEventsQueryKey> => {
  return async ({ signal }) => {
    const previous = queryClient.getQueryData<EventsSnapshot>(dashboardEventsQueryKey)

    try {
      const response = await api.get<PaginatedResponse<Event>>("/events", {
        params: { is_active: true, limit: 50 },
        signal,
        validateStatus: (status: number) => status >= 200 && status < 400,
        etagCacheKey: DASHBOARD_EVENTS_ETAG_KEY,
      } as Parameters<typeof api.get>[1])

      if (response.status === 304 && previous) {
        return previous
      }

      const normalized = sortEventsByStart(ensureEventList(response.data))
      return { items: normalized }
    } catch (error) {
      if (signal?.aborted) {
        throw error
      }

      const fallback = queryClient.getQueryData<EventsSnapshot>(dashboardEventsQueryKey)
      if (fallback) {
        return fallback
      }

      throw error
    }
  }
}

export const createDashboardEventsQueryOptions = (queryClient: QueryClient) => {
  const queryFn = createEventsQueryFn(queryClient)

  return {
    queryKey: dashboardEventsQueryKey,
    queryFn,
    select: (snapshot: EventsSnapshot) => snapshot.items,
    placeholderData: (previous: EventsSnapshot | undefined) => previous,
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
