import { createContext, useContext, useMemo, useState, useEffect, type ReactNode } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useChatWebSocket } from "@/hooks/useChatWebSocket"
import { useAuth } from "./AuthContext"
import { chatApi, type PresenceStatus, type ChatsListResponse, type Chat } from "@/api/chat"

interface MessengerContextType {
  unreadCount: number
  presenceMap: Record<string, PresenceStatus>
  isConnected: boolean
  sendTyping: (chatId: string) => void
  sendRead: (chatId: string) => void // Wave 203 SW5 — chat-level (no message_id)
  // Wave 204 SW5 — join/leave a ws-hub room (room == chat_id) so this client
  // receives live chat.{room} fan-out. Driven by useMessengerController on
  // chat-select (W204 SW6).
  sendJoin: (chatId: string) => void
  sendLeave: (chatId: string) => void
  getTypingUsersForChat: (chatId: string) => { userId: string; userName: string }[]
}

// Wave 197 SW7 — exported so Storybook stories (ChatArea) can wrap a tsc-typed
// MessengerContext.Provider stub without running the real provider's WebSocket /
// query work. Additive, unused by the app graph → tree-shaken from the prod
// bundle (the only consumer is the story, which is outside the Vite app entry).
export const MessengerContext = createContext<MessengerContextType | undefined>(undefined)

export const useMessenger = () => {
  const context = useContext(MessengerContext)
  if (!context) {
    throw new Error("useMessenger must be used within MessengerProvider")
  }
  return context
}

export function MessengerProvider({ children }: { children: ReactNode }) {
  const { isAuth, user } = useAuth()
  const queryClient = useQueryClient()
  const [presenceMap, setPresenceMap] = useState<Record<string, PresenceStatus>>({})

  const { isConnected, sendTyping, sendRead, sendJoin, sendLeave, getTypingUsersForChat } =
    useChatWebSocket({
      enabled: isAuth,
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
    enabled: isAuth,
  })

  const unreadCount = useMemo(() => {
    return chatsData?.items.reduce((acc, chat) => acc + (chat.unread_count || 0), 0) ?? 0
  }, [chatsData])

  // Initial presence map from fetched chats
  useEffect(() => {
    if (chatsData?.items) {
      setPresenceMap((prev) => {
        const next = { ...prev }
        chatsData.items.forEach((chat) => {
          Object.entries(chat.presence || {}).forEach(([id, status]) => {
            const userId = id
            next[userId] = status
          })
        })
        return next
      })
    }
  }, [chatsData])

  const value = useMemo(
    () => ({
      unreadCount,
      presenceMap,
      isConnected,
      sendTyping,
      sendRead,
      sendJoin,
      sendLeave,
      getTypingUsersForChat,
    }),
    [
      unreadCount,
      presenceMap,
      isConnected,
      sendTyping,
      sendRead,
      sendJoin,
      sendLeave,
      getTypingUsersForChat,
    ]
  )

  return <MessengerContext.Provider value={value}>{children}</MessengerContext.Provider>
}
