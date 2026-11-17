import { useMemo, useSyncExternalStore } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { isCurrentBrowserSession, subscribeSessionIdentity } from "@/stores/sessionEpoch"

/** Read-only cache observer: never starts a request or creates a query. */
export function useCachedRelatedLists<T>(root: "news" | "events") {
  const queryClient = useQueryClient()
  const store = useMemo(() => {
    const read = () =>
      queryClient.getQueriesData<{ pages?: Array<{ items?: T[] }> }>({
        queryKey: [root, "list"],
      })
    const empty: ReturnType<typeof read> = []
    let snapshot = empty
    const getSnapshot = () => {
      if (typeof window !== "undefined" && !isCurrentBrowserSession()) {
        snapshot = empty
        return snapshot
      }
      const next = read()
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
      const stopCache = queryClient.getQueryCache().subscribe((event) => {
        const key = event.query.queryKey
        if (key[0] === root && key[1] === "list") listener()
      })
      const stopSession = subscribeSessionIdentity(listener)
      return () => {
        stopCache()
        stopSession()
      }
    }
    return { getSnapshot, subscribe }
  }, [queryClient, root])
  return useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot)
}
