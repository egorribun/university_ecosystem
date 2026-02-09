import { useMemo } from "react"
import type { QueryClient } from "@tanstack/react-query"

import type { NewsItem } from "@/api/news"
import { useNewsListQuery, newsListQueryKey } from "@/api/hooks/news"
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
  const { news, ...query } = useNewsListQuery({ language, limit: DASHBOARD_NEWS_LIMIT })

  const sorted = useMemo(() => sortNewsItems(news), [news])

  return {
    ...query,
    data: sorted,
  }
}

export const prefetchDashboardNews = async (
  queryClient: QueryClient,
  language: SupportedLanguage
) => {
  // Prefetching optimization temporarily disabled during refactor
  return Promise.resolve()
}

export const dashboardNewsQueryKey = (language: SupportedLanguage) => {
  return newsListQueryKey({ language, limit: DASHBOARD_NEWS_LIMIT })
}




