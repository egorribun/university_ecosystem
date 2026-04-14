import { useMemo } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { type NewsItem } from "@/api/news"

interface ArticleNav {
  prevId: string | null
  nextId: string | null
  prevTitle: string | null
  nextTitle: string | null
}

/**
 * Determines previous and next article IDs from the cached news list.
 * Used for swipe navigation and prev/next buttons on article detail.
 */
export function useArticleNavigation(currentId: string): ArticleNav {
  const queryClient = useQueryClient()

  return useMemo(() => {
    const fallback: ArticleNav = { prevId: null, nextId: null, prevTitle: null, nextTitle: null }

    // Pull from cached news list queries
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

    // Deduplicate preserving order
    const seen = new Set<string>()
    const ordered: NewsItem[] = []
    for (const item of allItems) {
      if (!seen.has(item.id)) {
        seen.add(item.id)
        ordered.push(item)
      }
    }

    const currentIndex = ordered.findIndex((n) => n.id === currentId)
    if (currentIndex === -1) return fallback

    const prev = currentIndex > 0 ? ordered[currentIndex - 1] : null
    const next = currentIndex < ordered.length - 1 ? ordered[currentIndex + 1] : null

    return {
      prevId: prev?.id ?? null,
      nextId: next?.id ?? null,
      prevTitle: prev?.title ?? null,
      nextTitle: next?.title ?? null,
    }
  }, [queryClient, currentId])
}
