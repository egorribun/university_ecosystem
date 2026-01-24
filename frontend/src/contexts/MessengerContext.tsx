import React, { createContext, useContext, useMemo, useState, useEffect } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useChatWebSocket } from "../hooks/useChatWebSocket"
import { useAuth } from "./AuthContext"
import { chatApi, type PresenceStatus, type ChatsListResponse } from "../api/chat"

interface MessengerContextType {
  unreadCount: number
  presenceMap: Record<number, PresenceStatus>
  isConnected: boolean
  sendTyping: (chatId: string) => void
  sendRead: (chatId: string, messageId: string) => void
  getTypingUsersForChat: (chatId: string) => { userId: number; userName: string }[]
}

const MessengerContext = createContext<MessengerContextType | undefined>(undefined)

export const useMessenger = () => {
  const context = useContext(MessengerContext)
  if (!context) {
    throw new Error("useMessenger must be used within MessengerProvider")
  }
  return context
}

export const MessengerProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isAuth } = useAuth()
  const queryClient = useQueryClient()
  const [presenceMap, setPresenceMap] = useState<Record<number, PresenceStatus>>({})

  const { isConnected, sendTyping, sendRead, getTypingUsersForChat } = useChatWebSocket({
    enabled: isAuth,
    onPresenceUpdate: (userId, active, lastSeen) => {
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
            const userId = Number(id)
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
      getTypingUsersForChat,
    }),
    [unreadCount, presenceMap, isConnected, sendTyping, sendRead, getTypingUsersForChat]
  )

  return <MessengerContext.Provider value={value}>{children}</MessengerContext.Provider>
}
