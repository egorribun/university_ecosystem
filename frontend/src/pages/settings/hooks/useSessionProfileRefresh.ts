import { useCallback } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useAuth } from "@/contexts/AuthContext"
import { currentUserQueryKey, fetchCurrentUser } from "@/hooks/auth/useProfileSync"
import type { User } from "@/types/User"

/** Keep the original action guard through the write, query cache, and profile adoption. */
export function useSessionProfileRefresh() {
  const { user, setUser } = useAuth()
  const queryClient = useQueryClient()
  const userId = user?.id

  return useCallback(
    async (isCurrent: () => boolean) => {
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
    },
    [queryClient, setUser, userId]
  )
}
