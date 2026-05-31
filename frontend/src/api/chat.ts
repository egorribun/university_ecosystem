import client from "./client"
import type { User } from "@/types/User"

export interface Attachment {
  id: string
  url: string
  file_type: "image" | "video" | "file"
  filename: string
  size: number
}

export interface PresenceStatus {
  active: boolean
  last_seen_at: string | null
}

export interface Message {
  id: string
  chat_id: string
  sender_id: string
  content: string
  created_at: string
  read_status: boolean
  read_at?: string | null // Wave 203 — ISO read-receipt timestamp (null until read)
  edited_at?: string | null // Wave 205 — ISO edit timestamp (null until edited)
  deleted_at?: string | null // Wave 205 — ISO soft-delete timestamp (null = not deleted)
  sender?: User
  sender_presence?: PresenceStatus
  attachments?: Attachment[]
  // Wave 206 — per-emoji reaction aggregates. reacted_by_me is server-computed for
  // the requesting user on GET /messages; on the WS delta frame the hook patches
  // count only (reacted_by_me is per-viewer, never broadcast).
  reactions?: { emoji: string; count: number; reacted_by_me: boolean }[]
}

export interface Chat {
  id: string
  participants: User[]
  last_message?: Message
  unread_count: number
  created_at: string
  updated_at: string
  presence?: Record<string, PresenceStatus>
}

// Paginated response types
export interface ChatsListResponse {
  items: Chat[]
  has_more: boolean
  next_cursor: string | null
}

export interface MessagesListResponse {
  items: Message[]
  has_more: boolean
  next_cursor: string | null
}

export interface ChatMaintenanceResult {
  chat_id: string
  status: string
  deleted_messages: number
  deleted_attachments: number
}

export const chatApi = {
  getChats: async (cursor?: string, limit: number = 20): Promise<ChatsListResponse> => {
    const params = new URLSearchParams()
    if (cursor) params.append("cursor", cursor)
    params.append("limit", String(limit))
    const response = await client.get<ChatsListResponse>(`/chats?${params.toString()}`)
    return response.data
  },

  getChat: async (chatId: string): Promise<Chat> => {
    const response = await client.get<Chat>(`/chats/${chatId}`)
    return response.data
  },

  createChat: async (participantId: string) => {
    const response = await client.post<Chat>("/chats", { participant_id: participantId })
    return response.data
  },

  getMessages: async (
    chatId: string,
    cursor?: string,
    limit: number = 50
  ): Promise<MessagesListResponse> => {
    const params = new URLSearchParams()
    if (cursor) params.append("cursor", cursor)
    params.append("limit", String(limit))
    const response = await client.get<MessagesListResponse>(
      `/chats/${chatId}/messages?${params.toString()}`
    )
    return response.data
  },

  sendMessage: async (chatId: string, content: string, files?: File[]) => {
    const formData = new FormData()
    formData.append("content", content)
    if (files && files.length > 0) {
      files.forEach((file) => {
        formData.append("files", file)
      })
    }
    const response = await client.post<Message>(`/chats/${chatId}/messages`, formData)
    return response.data
  },

  markRead: async (chatId: string) => {
    const response = await client.post(`/chats/${chatId}/read`)
    return response.data
  },

  // Wave 205 — author-only edit / soft-delete. Edit sends FormData (the backend
  // PATCH parses `content` as a Form field, matching sendMessage). Both flip live
  // for the other participant via the W204 bridge; the author sees the optimistic
  // mutation. 404 if not the author / message missing / already deleted.
  editMessage: async (chatId: string, messageId: string, content: string) => {
    const formData = new FormData()
    formData.append("content", content)
    const response = await client.patch(`/chats/${chatId}/messages/${messageId}`, formData)
    return response.data
  },

  deleteMessage: async (chatId: string, messageId: string) => {
    const response = await client.delete(`/chats/${chatId}/messages/${messageId}`)
    return response.data
  },

  // Wave 206 — emoji reactions (any participant, any message). add posts `emoji`
  // as a Form field (matching the backend POST); remove passes `emoji` as a query
  // param (SW7 — query params decode unambiguously, the robust shape for arbitrary
  // multi-codepoint content; verified live two-browser cross-user). Both flip live
  // for other participants via the W204 bridge; the actor sees the optimistic
  // toggleReactionMutation. Idempotent server-side.
  addReaction: async (chatId: string, messageId: string, emoji: string) => {
    const formData = new FormData()
    formData.append("emoji", emoji)
    const response = await client.post(`/chats/${chatId}/messages/${messageId}/reactions`, formData)
    return response.data
  },

  removeReaction: async (chatId: string, messageId: string, emoji: string) => {
    // W206 SW7 — emoji as a query param (not a URL-path segment): query params
    // decode unambiguously, the robust shape for an arbitrary multi-codepoint emoji
    // sub-resource selector. Verified live (real 👍 cross-user remove, no refetch).
    const response = await client.delete(
      `/chats/${chatId}/messages/${messageId}/reactions?emoji=${encodeURIComponent(emoji)}`
    )
    return response.data
  },

  clearChat: async (chatId: string) => {
    const response = await client.post<ChatMaintenanceResult>(`/chats/${chatId}/clear`)
    return response.data
  },

  deleteChat: async (chatId: string) => {
    const response = await client.delete<ChatMaintenanceResult>(`/chats/${chatId}`)
    return response.data
  },
}
