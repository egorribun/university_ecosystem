import { useMemo } from "react"
import {
  useQuery,
  useQueryClient,
  type QueryClient,
  type QueryFunction,
} from "@tanstack/react-query"

import { fetchStories } from "@/api/stories"
import type { StoryItem } from "@/types/Story"

type StoriesSnapshot = {
  items: StoryItem[]
  etag: string | null
}

export const dashboardStoriesQueryKey = [
  "dashboard",
  "stories",
] as const

type DashboardStoriesQueryKey = typeof dashboardStoriesQueryKey

const parseStoriesPayload = (payload: unknown): StoryItem[] => {
  if (!Array.isArray(payload)) {
    return []
  }
  return payload.filter(Boolean) as StoryItem[]
}

const extractEtag = (headers: unknown): string | null => {
  if (!headers || typeof headers !== "object") {
    return null
  }

  const lowercase = headers as Record<string, unknown>
  const direct = lowercase?.etag
  if (typeof direct === "string" && direct.trim()) {
    return direct
  }

  const upper = lowercase?.ETag
  if (typeof upper === "string" && upper.trim()) {
    return upper
  }

  return null
}

const createStoriesQueryFn = (
  queryClient: QueryClient
): QueryFunction<StoriesSnapshot, DashboardStoriesQueryKey> => {
  return async ({ signal }) => {
    if (signal?.aborted) {
      throw new DOMException("Aborted", "AbortError")
    }

    const previous = queryClient.getQueryData<StoriesSnapshot>(dashboardStoriesQueryKey)
    const previousEtag = previous?.etag ?? null

    try {
      const response = await fetchStories(previousEtag)

      const nextEtag = extractEtag(response.headers) ?? previousEtag

      if (response.status === 304) {
        if (previous) {
          return previous
        }
        return { items: [], etag: nextEtag }
      }

      const items = parseStoriesPayload(response.data)
      return { items, etag: nextEtag }
    } catch (error) {
      if (signal?.aborted) {
        throw error
      }

      const fallback = queryClient.getQueryData<StoriesSnapshot>(dashboardStoriesQueryKey)
      if (fallback) {
        return fallback
      }

      throw error
    }
  }
}

export const createDashboardStoriesQueryOptions = (queryClient: QueryClient) => {
  const queryFn = createStoriesQueryFn(queryClient)

  return {
    queryKey: dashboardStoriesQueryKey,
    queryFn,
    select: (snapshot: StoriesSnapshot) => snapshot.items,
    placeholderData: (previous: StoriesSnapshot | undefined) => previous,
    staleTime: 2 * 60_000,
    gcTime: 30 * 60_000,
  } as const
}

export const useDashboardStories = () => {
  const queryClient = useQueryClient()

  const queryOptions = useMemo(
    () => createDashboardStoriesQueryOptions(queryClient),
    [queryClient]
  )

  return useQuery(queryOptions)
}

export const prefetchDashboardStories = (queryClient: QueryClient) =>
  queryClient.prefetchQuery(createDashboardStoriesQueryOptions(queryClient))

