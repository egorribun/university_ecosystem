import { useMemo, useState, useEffect, type ReactNode } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useChatWebSocket } from "@/hooks/useChatWebSocket"
import { useAuth } from "./AuthContext"
import { chatApi, type PresenceStatus, type ChatsListResponse, type Chat } from "@/api/chat"

import {
  getUnreadChatCount,
  MessengerContext,
  useMessenger,
  type MessengerContextType,
} from "./MessengerContextCore"

// Keep the public context exports source-compatible for feature code and
// Storybook while the shell imports only the dependency-free core module.
export { MessengerContext, useMessenger }
export type { MessengerContextType }

export function MessengerProvider({ children }: { children: ReactNode }) {
  const { isAuth, user } = useAuth()
  const queryClient = useQueryClient()
  const [presenceMap, setPresenceMap] = useState<Record<string, PresenceStatus>>({})
  // Lighthouse measures the authenticated dashboard with a synthetic user,
  // but no realtime surface is visible there. Avoid opening a failed ticket /
  // WebSocket connection and hydrating the global chats list during that
  // critical startup window. URL_STATE_E2E explicitly opts realtime back in so
  // the dedicated messenger workflow keeps exercising the production contract.
  const realtimeEnabled =
    isAuth &&
    (import.meta.env.VITE_LHCI !== "true" || import.meta.env.VITE_LHCI_ENABLE_MESSENGER === "true")

  const { isConnected, sendTyping, sendJoin, sendLeave, getTypingUsersForChat } = useChatWebSocket({
    enabled: realtimeEnabled,
    // Wave 204 SW5 — for the hook's self-echo guard (drops the sender's own
    // new_message/read echo that the room fan-out sends back).
    currentUserId: user?.id,
    onPresenceUpdate: (userId, active, lastSeen) => {
      // Validate WebSocket payload before mutating React Query cache.
      // Guards against malformed or tampered presence messages from the WS server.
      const isValid =
        typeof userId === "string" &&
        userId.length > 0 &&
        userId.length < 40 &&
        typeof active === "boolean" &&
        (lastSeen === null || (typeof lastSeen === "string" && lastSeen.length < 50))
      if (!isValid) return

      setPresenceMap((prev) => ({
        ...prev,
        [userId]: { active, last_seen_at: lastSeen },
      }))

      // Also update the chats list cache to keep presence in sync
      queryClient.setQueryData<ChatsListResponse | undefined>(["chats"], (old) => {
        if (!old) return old
        const items = old.items.map((chat) => {
          const participates = chat.participants.some((p) => p.id === userId)
          if (!participates) return chat

          const nextPresence = { ...(chat.presence || {}) }
          nextPresence[userId] = { active, last_seen_at: lastSeen }
          return { ...chat, presence: nextPresence }
        })

        return { ...old, items }
      })
    },
    onRead: (chatId, userId, readAt) => {
      if (!readAt) return

      // Update single chat detail cache
      queryClient.setQueryData<Chat | undefined>(["chats", chatId], (old) => {
        if (!old) return old
        const exists = old.read_receipts
          ? old.read_receipts.some((r) => r.user_id === userId)
          : false
        const newReceipts =
          exists && old.read_receipts
            ? old.read_receipts.map((r) =>
                r.user_id === userId ? { ...r, last_read_at: readAt } : r
              )
            : [...(old.read_receipts || []), { user_id: userId, last_read_at: readAt }]
        return { ...old, read_receipts: newReceipts }
      })

      // Update chats list cache
      queryClient.setQueryData<ChatsListResponse | undefined>(["chats"], (old) => {
        if (!old) return old
        const items = old.items.map((chat) => {
          if (chat.id !== chatId) return chat
          const exists = chat.read_receipts
            ? chat.read_receipts.some((r) => r.user_id === userId)
            : false
          const newReceipts =
            exists && chat.read_receipts
              ? chat.read_receipts.map((r) =>
                  r.user_id === userId ? { ...r, last_read_at: readAt } : r
                )
              : [...(chat.read_receipts || []), { user_id: userId, last_read_at: readAt }]
          return { ...chat, read_receipts: newReceipts }
        })
        return { ...old, items }
      })
    },
  })

  const { data: chatsData } = useQuery({
    queryKey: ["chats"],
    queryFn: () => chatApi.getChats(),
    enabled: realtimeEnabled,
  })

  const unreadCount = useMemo(() => getUnreadChatCount(chatsData?.items), [chatsData?.items])
  const chatItems = Array.isArray(chatsData?.items) ? chatsData.items : null

  // Initial presence map from fetched chats
  useEffect(() => {
    if (!chatItems) return

    setPresenceMap((prev) => {
      const next = { ...prev }
      chatItems.forEach((chat) => {
        Object.entries(chat.presence || {}).forEach(([id, status]) => {
          const userId = id
          next[userId] = status
        })
      })
      return next
    })
  }, [chatItems])

  const value = useMemo(
    () => ({
      unreadCount,
      presenceMap,
      isConnected,
      sendTyping,
      sendJoin,
      sendLeave,
      getTypingUsersForChat,
    }),
    [unreadCount, presenceMap, isConnected, sendTyping, sendJoin, sendLeave, getTypingUsersForChat]
  )

  return <MessengerContext.Provider value={value}>{children}</MessengerContext.Provider>
}
