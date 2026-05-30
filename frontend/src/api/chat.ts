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
  sender?: User
  sender_presence?: PresenceStatus
  attachments?: Attachment[]
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

  clearChat: async (chatId: string) => {
    const response = await client.post<ChatMaintenanceResult>(`/chats/${chatId}/clear`)
    return response.data
  },

  deleteChat: async (chatId: string) => {
    const response = await client.delete<ChatMaintenanceResult>(`/chats/${chatId}`)
    return response.data
  },
}
