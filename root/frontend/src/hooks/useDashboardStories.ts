import { useMemo } from "react"
import {
  useQuery,
  useQueryClient,
  type QueryClient,
  type QueryFunction,
} from "@tanstack/react-query"

import { fetchStories } from "@/api/stories"
import type { StoryItem } from "@/types/Story"

export const dashboardStoriesQueryKey = ["dashboard", "stories"] as const

type DashboardStoriesQueryKey = typeof dashboardStoriesQueryKey

const parseStoriesPayload = (payload: unknown): StoryItem[] => {
  if (!Array.isArray(payload)) {
    return []
  }
  return payload.filter(Boolean) as StoryItem[]
}

const createStoriesQueryFn = (
  queryClient: QueryClient
): QueryFunction<StoryItem[], DashboardStoriesQueryKey> => {
  return async ({ signal }) => {
    const previous = queryClient.getQueryData<StoryItem[]>(dashboardStoriesQueryKey)

    try {
      const response = await fetchStories()

      if (response.status === 304) {
        return previous ?? []
      }

      return parseStoriesPayload(response.data)
    } catch (error) {
      if (signal?.aborted) {
        throw error
      }

      if (previous) {
        return previous
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
    placeholderData: (previous: StoryItem[] | undefined) => previous ?? [],
    staleTime: 2 * 60_000,
    gcTime: 30 * 60_000,
  } as const
}

export const useDashboardStories = () => {
  const queryClient = useQueryClient()

  const queryOptions = useMemo(() => createDashboardStoriesQueryOptions(queryClient), [queryClient])

  return useQuery(queryOptions)
}

export const prefetchDashboardStories = (queryClient: QueryClient) =>
  queryClient.prefetchQuery(createDashboardStoriesQueryOptions(queryClient))
