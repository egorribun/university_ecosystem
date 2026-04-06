import { useMemo } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { type NewsItem } from "@/api/news"
import { inferCategory, type NewsCategory } from "@/features/news/categories"

/**
 * Returns related news articles from the cached query data.
 * Filters by matching inferred category, excluding current article.
 */
export function useRelatedNews(
  currentId: string,
  category: NewsCategory,
  limit = 3
): NewsItem[] {
  const queryClient = useQueryClient()

  return useMemo(() => {
    // Pull from all cached news list queries
    const queries = queryClient.getQueriesData<{ pages?: Array<{ items?: NewsItem[] }> }>({
      queryKey: ["news", "list"],
    })

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
    const sameCategory = unique.filter(
      (n) => inferCategory(n.title, n.content) === category
    )

    // If not enough in same category, fill with recent from other categories
    if (sameCategory.length >= limit) return sameCategory.slice(0, limit)

    const remaining = unique
      .filter((n) => inferCategory(n.title, n.content) !== category)
      .slice(0, limit - sameCategory.length)

    return [...sameCategory, ...remaining].slice(0, limit)
  }, [queryClient, currentId, category, limit])
}
