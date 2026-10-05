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

export type DashboardStory = Pick<
  StoryItem,
  | "id"
  | "created_at"
  | "expires_at"
  | "is_active"
  | "published_at"
  | "short_text"
  | "title"
  | "cover_url"
  | "cover_url_optimized"
  | "cta_url"
>

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value)

const optionalStringOrNull = (value: unknown): value is string | null | undefined =>
  value === undefined || value === null || typeof value === "string"

const readDashboardStory = (value: unknown): DashboardStory | undefined => {
  if (!isRecord(value)) return undefined
  const {
    id,
    created_at: createdAt,
    expires_at: expiresAt,
    is_active: isActive,
    published_at: publishedAt,
    short_text: shortText,
    title,
    cover_url: coverUrl,
    cover_url_optimized: coverUrlOptimized,
    cta_url: ctaUrl,
  } = value
  if (
    typeof id !== "string" ||
    typeof createdAt !== "string" ||
    typeof expiresAt !== "string" ||
    typeof isActive !== "boolean" ||
    typeof publishedAt !== "string" ||
    typeof shortText !== "string" ||
    typeof title !== "string" ||
    !optionalStringOrNull(coverUrl) ||
    !optionalStringOrNull(coverUrlOptimized) ||
    !optionalStringOrNull(ctaUrl)
  ) {
    return undefined
  }

  const story: DashboardStory = {
    id,
    created_at: createdAt,
    expires_at: expiresAt,
    is_active: isActive,
    published_at: publishedAt,
    short_text: shortText,
    title,
  }
  if (coverUrl !== undefined) story.cover_url = coverUrl
  if (coverUrlOptimized !== undefined) story.cover_url_optimized = coverUrlOptimized
  if (ctaUrl !== undefined) story.cta_url = ctaUrl
  return story
}

/** Validate and project stories onto the dashboard UI contract. */
export function projectDashboardStories(value: unknown): DashboardStory[] | undefined {
  if (!Array.isArray(value)) return undefined
  const stories: DashboardStory[] = []
  for (const item of value) {
    const story = readDashboardStory(item)
    if (story) stories.push(story)
  }
  return stories
}

const createStoriesQueryFn = (
  queryClient: QueryClient
): QueryFunction<DashboardStory[], DashboardStoriesQueryKey> => {
  return async ({ signal }) => {
    try {
      const response = await fetchStories()

      if (response.status === 304) {
        return projectDashboardStories(queryClient.getQueryData(dashboardStoriesQueryKey)) ?? []
      }

      return projectDashboardStories(response.data) ?? []
    } catch (error) {
      if (signal?.aborted) throw error
      const fallback = projectDashboardStories(queryClient.getQueryData(dashboardStoriesQueryKey))
      if (fallback) return fallback
      throw error
    }
  }
}

export const createDashboardStoriesQueryOptions = (queryClient: QueryClient) => {
  const queryFn = createStoriesQueryFn(queryClient)

  return {
    queryKey: dashboardStoriesQueryKey,
    queryFn,
    placeholderData: (previous: DashboardStory[] | undefined) => previous ?? [],
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
