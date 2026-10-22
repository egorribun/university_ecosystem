import { useCallback } from "react"
import { useQueryClient, type QueryClient } from "@tanstack/react-query"
import { useAuth } from "@/contexts/AuthContext"
import { currentUserQueryKey, fetchCurrentUser } from "@/hooks/auth/useProfileSync"
import type { User } from "@/types/User"

const profileRefreshTails = new WeakMap<QueryClient, Promise<void>>()

/** Keep the original action guard through the write, query cache, and profile adoption. */
export function useSessionProfileRefresh() {
  const { user, setUser } = useAuth()
  const queryClient = useQueryClient()
  const userId = user?.id

  return useCallback(
    async (isCurrent: () => boolean) => {
      if (!isCurrent()) return null

      // Refreshes share one QueryClient cache key. Serialize them so one
      // committed action cannot cancel another action's post-commit request.
      const previousRefresh = profileRefreshTails.get(queryClient) ?? Promise.resolve()
      let releaseRefresh!: () => void
      const refreshTail = new Promise<void>((resolve) => {
        releaseRefresh = resolve
      })
      profileRefreshTails.set(queryClient, refreshTail)

      try {
        await previousRefresh
        if (!isCurrent()) return null

        // The mutation response follows the server commit. Do not let an older
        // in-flight profile request satisfy this post-commit refresh.
        await queryClient.cancelQueries({ queryKey: currentUserQueryKey, exact: true })
        if (!isCurrent()) return null

        const fresh = await queryClient.fetchQuery<User>({
          queryKey: currentUserQueryKey,
          queryFn: async ({ signal }) => {
            if (!isCurrent()) throw new DOMException("Obsolete profile operation", "AbortError")
            const profile = await fetchCurrentUser({ signal })
            if (!isCurrent() || profile.id !== userId) {
              throw new DOMException("Obsolete profile response", "AbortError")
            }
            return profile
          },
          staleTime: 0,
        })
        if (!isCurrent() || fresh?.id !== userId) return null
        setUser(fresh)
        return fresh
      } finally {
        if (profileRefreshTails.get(queryClient) === refreshTail) {
          profileRefreshTails.delete(queryClient)
        }
        // The tail never contains the operation result, so a failed refresh
        // still releases queued callers without sharing its rejection.
        releaseRefresh()
      }
    },
    [queryClient, setUser, userId]
  )
}
