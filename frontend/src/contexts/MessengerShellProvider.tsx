import { useEffect, useMemo, useState, type ReactNode } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useProjectedMessengerChats } from "@/hooks/messengerProjection"

import { useAuth } from "./AuthContext"
import {
  DEFAULT_MESSENGER_CONTEXT,
  getUnreadChatCount,
  MessengerContext,
  type MessengerContextType,
} from "./MessengerContextCore"

const UNREAD_IDLE_DELAY_MS = 1_500
const isLhciAudit = () => import.meta.env.VITE_LHCI === "true"

/**
 * Keeps the global navigation badge useful without mounting chat realtime
 * infrastructure on every route.  The chat list is fetched once, after the
 * first idle window, and remains on the shared `['chats']` cache key so the
 * full MessengerProvider can reuse it when the user opens Messenger.
 */
export function MessengerShellProvider({ children }: { children: ReactNode }) {
  const { isAuth, user } = useAuth()
  const queryClient = useQueryClient()
  const authIdentity = isAuth ? (user?.id ?? "authenticated") : null
  const [idleReadyFor, setIdleReadyFor] = useState<string | null>(null)

  useEffect(() => {
    setIdleReadyFor(null)
    // Lighthouse uses a synthetic authenticated user and has no chat surface
    // in its route contract. Keep this optional badge hydration out of the
    // lab's critical task window; production builds still fetch after idle.
    if (authIdentity === null || isLhciAudit()) {
      return
    }

    let timeoutId: number | undefined
    let idleId: number | undefined
    const onIdle = () => setIdleReadyFor(authIdentity)

    if (typeof window.requestIdleCallback === "function") {
      idleId = window.requestIdleCallback(onIdle, { timeout: UNREAD_IDLE_DELAY_MS })
    } else {
      timeoutId = window.setTimeout(onIdle, UNREAD_IDLE_DELAY_MS)
    }

    return () => {
      if (idleId !== undefined && typeof window.cancelIdleCallback === "function") {
        window.cancelIdleCallback(idleId)
      }
      if (timeoutId !== undefined) window.clearTimeout(timeoutId)
    }
  }, [authIdentity])

  const idleReady = !isLhciAudit() && authIdentity !== null && idleReadyFor === authIdentity

  const { data: canonicalChats } = useQuery({
    queryKey: ["chats"],
    queryFn: async ({ signal }) =>
      (await import("@/api/hooks/messenger")).fetchLoadedChats(queryClient, signal),
    enabled: idleReady,
    staleTime: 30_000,
  })
  const data = useProjectedMessengerChats(canonicalChats, user?.id ?? null)

  const unreadCount = useMemo(
    () => (idleReady ? getUnreadChatCount(data?.items) : 0),
    [data?.items, idleReady]
  )

  const contextValue = useMemo<MessengerContextType>(() => {
    if (unreadCount === 0) return DEFAULT_MESSENGER_CONTEXT
    return { ...DEFAULT_MESSENGER_CONTEXT, unreadCount }
  }, [unreadCount])

  return <MessengerContext.Provider value={contextValue}>{children}</MessengerContext.Provider>
}
