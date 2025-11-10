import { useMemo } from "react"
import type { QueryClient } from "@tanstack/react-query"

import type { NewsItem } from "@/api/news"
import { useNewsFeed, newsFeedQueryKey, createNewsFeedQueryOptions } from "@/hooks/useNewsFeed"
import type { SupportedLanguage } from "@/contexts/LanguageContext"

const DASHBOARD_NEWS_LIMIT = 4

type MaybePinnedNewsItem = NewsItem & { pinned?: boolean | null }

const getPinnedRank = (item: NewsItem) => {
  const candidate = item as MaybePinnedNewsItem
  return typeof candidate.pinned === "boolean" ? Number(candidate.pinned) : 0
}

const sortNewsItems = (items: readonly NewsItem[] | undefined) => {
  if (!items?.length) {
    return [] as NewsItem[]
  }

  return [...items]
    .filter(Boolean)
    .sort((a, b) => getPinnedRank(b) - getPinnedRank(a))
    .slice(0, DASHBOARD_NEWS_LIMIT)
}

export const useDashboardNews = (language: SupportedLanguage) => {
  const query = useNewsFeed(language)

  const sorted = useMemo(() => sortNewsItems(query.data), [query.data])

  return {
    ...query,
    data: sorted,
  }
}

export const prefetchDashboardNews = (queryClient: QueryClient, language: SupportedLanguage) => {
  const options = createNewsFeedQueryOptions(queryClient, language)
  return queryClient.prefetchQuery(options)
}

export const dashboardNewsQueryKey = newsFeedQueryKey
