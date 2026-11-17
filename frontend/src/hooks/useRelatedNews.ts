import { useMemo } from "react"
import { useCachedRelatedLists } from "./useCachedRelatedLists"
import { isCurrentBrowserSession } from "@/stores/sessionEpoch"
import { type NewsItem } from "@/api/news"
import { inferNewsCategory, type NewsCategory } from "@/features/news/categories"

/**
 * Returns related news articles from the cached query data.
 * Filters by matching inferred category, excluding current article.
 */
export function useRelatedNews(currentId: string, category: NewsCategory, limit = 3): NewsItem[] {
  const queries = useCachedRelatedLists<NewsItem>("news")
  const sessionIsCurrent = typeof window === "undefined" || isCurrentBrowserSession()

  return useMemo(() => {
    if (!sessionIsCurrent) return []
    const allItems: NewsItem[] = []
    for (const [, data] of queries) {
      if (data?.pages) {
        for (const page of data.pages) {
          if (page.items) allItems.push(...page.items)
        }
      }
    }

    // Deduplicate
    const seen = new Set<string>()
    const unique: NewsItem[] = []
    for (const item of allItems) {
      if (!seen.has(item.id) && item.id !== currentId) {
        seen.add(item.id)
        unique.push(item)
      }
    }

    // Filter by same category, then by recent
    const sameCategory = unique.filter((n) => inferNewsCategory(n) === category)

    // If not enough in same category, fill with recent from other categories
    if (sameCategory.length >= limit) return sameCategory.slice(0, limit)

    const remaining = unique
      .filter((n) => inferNewsCategory(n) !== category)
      .slice(0, limit - sameCategory.length)

    return [...sameCategory, ...remaining].slice(0, limit)
  }, [queries, currentId, category, limit, sessionIsCurrent])
}
