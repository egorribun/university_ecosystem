import { useMemo, useSyncExternalStore } from "react"
import { useQueryClient, type QueryClient } from "@tanstack/react-query"
import { isCurrentBrowserSession } from "@/stores/sessionEpoch"
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
function createArticleNavigationStore(queryClient: QueryClient, sessionIsCurrent: boolean) {
  const readQueries = () =>
    queryClient.getQueriesData<{ pages?: Array<{ items?: NewsItem[] }> }>({
      queryKey: ["news", "list"],
    })

  let snapshot: ReturnType<typeof readQueries> = []

  const getSnapshot = () => {
    if (!sessionIsCurrent) return snapshot

    const next = readQueries()
    const unchanged =
      next.length === snapshot.length &&
      next.every(([key, data], index) => {
        const previous = snapshot[index]
        return previous?.[0] === key && previous?.[1] === data
      })

    if (!unchanged) snapshot = next
    return snapshot
  }

  const subscribe = (listener: () => void) => {
    if (!sessionIsCurrent) return () => undefined

    return queryClient.getQueryCache().subscribe((event) => {
      const key = event.query.queryKey
      if (key[0] === "news" && key[1] === "list") listener()
    })
  }

  return { getSnapshot, subscribe }
}

export function useArticleNavigation(currentId: string): ArticleNav {
  const queryClient = useQueryClient()
  const sessionIsCurrent = typeof window === "undefined" || isCurrentBrowserSession()

  const store = useMemo(
    () => createArticleNavigationStore(queryClient, sessionIsCurrent),
    [queryClient, sessionIsCurrent]
  )

  const queries = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot)

  return useMemo(() => {
    const fallback: ArticleNav = { prevId: null, nextId: null, prevTitle: null, nextTitle: null }
    if (!sessionIsCurrent) return fallback

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
  }, [queries, currentId, sessionIsCurrent])
}
