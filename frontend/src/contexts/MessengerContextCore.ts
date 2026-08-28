import { createContext, useContext } from "react"

/**
 * Dependency-free context contract used by the application shell.  The full
 * chat provider is mounted by the lazy messenger route, so authenticated
 * pages do not pull the WebSocket and chat API graph into the critical entry.
 */
export interface MessengerContextType {
  unreadCount: number
  presenceMap: Record<string, { active: boolean; last_seen_at: string | null }>
  isConnected: boolean
  sendTyping: (chatId: string) => void
  sendRead: (chatId: string) => void
  sendJoin: (chatId: string) => void
  sendLeave: (chatId: string) => void
  getTypingUsersForChat: (chatId: string) => { userId: string; userName: string }[]
}

export const DEFAULT_MESSENGER_CONTEXT: MessengerContextType = Object.freeze({
  unreadCount: 0,
  presenceMap: Object.freeze({}),
  isConnected: false,
  sendTyping: () => undefined,
  sendRead: () => undefined,
  sendJoin: () => undefined,
  sendLeave: () => undefined,
  getTypingUsersForChat: () => [],
})

/**
 * Keeps optional chat-list consumers fail-closed when an interrupted or
 * malformed response reaches the client cache. The API contract supplies a
 * Chat[] here, but the navigation shell must never turn a missing optional
 * badge payload into a route-wide render failure.
 */
export function getUnreadChatCount(items: unknown): number {
  if (!Array.isArray(items)) return 0

  return items.reduce((total, item) => {
    if (typeof item !== "object" || item === null) return total

    const unreadCount = (item as { unread_count?: unknown }).unread_count
    return typeof unreadCount === "number" && Number.isSafeInteger(unreadCount)
      ? total + Math.max(0, unreadCount)
      : total
  }, 0)
}

export const MessengerContext = createContext<MessengerContextType | undefined>(undefined)

export const useMessenger = (): MessengerContextType => {
  const context = useContext(MessengerContext)
  if (!context) {
    throw new Error("useMessenger must be used within MessengerProvider")
  }
  return context
}
