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
  // Wave 207 — reply/quote preview (the lean ReplyPreview: the quoted message's
  // id + sender + a content snippet + a deleted flag). null when this message
  // isn't a reply, or when the reply target was hard-deleted (the SET NULL
  // self-FK nulled the ref). Both GET /messages + the live new_message frame
  // carry it.
  reply_to?: {
    id: string
    sender_id: string
    sender_name: string | null
    content: string
    deleted_at: string | null
  } | null
  // Wave 211 — denormalized "Forwarded from X" label (null/absent = not a forward).
  // Snapshot-copy forwarding: the source content + attachments are copied into this
  // message; this scalar is the only forwarded-from datum (the source is never
  // linked/dereferenced cross-chat — privacy). Both GET /messages + the live
  // new_message frame carry it.
  forwarded_from_name?: string | null
}

// Wave 207 — one user in the reactor-list ("who reacted") popover. Matches the
// backend ReactorOut {user_id, name, avatar_url}. Loaded on-demand via getReactors,
// NOT bundled into GET /messages (only the count aggregate is).
export interface Reactor {
  user_id: string
  name: string | null
  avatar_url: string | null
}

export interface Chat {
  id: string
  // Wave 209 G1 — group-chat identity. Optional so existing DM consumers compile
  // unchanged (absent/"dm" for a DM); the group-rendering UI that reads these is G4.
  chat_type?: "dm" | "group"
  name?: string | null
  created_by?: string | null
  participants: User[]
  last_message?: Message
  unread_count: number
  created_at: string
  updated_at: string
  presence?: Record<string, PresenceStatus>
  // Wave 210 G2 — per-member read high-water-marks (group-only; absent/[] for a
  // DM, which keeps using Message.read_status). Populated by GET /chats/{id}
  // (get_chat_details); the FE folds these + live `read` frames into a "seen by
  // N" map. API-surface only this wave — the group marker UI is G4.
  read_receipts?: { user_id: string; last_read_at: string }[]
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

  // Wave 209 G1 — group-chat surface. participantIds are the *other* members
  // (the creator is added server-side); the backend enforces the 3..100 bound.
  createGroup: async (name: string, participantIds: string[]) => {
    const response = await client.post<Chat>("/chats/groups", {
      name,
      participant_ids: participantIds,
    })
    return response.data
  },

  addParticipant: async (chatId: string, userId: string) => {
    const response = await client.post(`/chats/${chatId}/participants`, {
      user_id: userId,
    })
    return response.data
  },

  removeParticipant: async (chatId: string, userId: string) => {
    const response = await client.delete(`/chats/${chatId}/participants/${userId}`)
    return response.data
  },

  renameChat: async (chatId: string, name: string) => {
    const response = await client.patch(`/chats/${chatId}`, { name })
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

  sendMessage: async (
    chatId: string,
    content: string,
    files?: File[],
    replyToMessageId?: string
  ) => {
    const formData = new FormData()
    formData.append("content", content)
    if (files && files.length > 0) {
      files.forEach((file) => {
        formData.append("files", file)
      })
    }
    // Wave 207 — reply/quote. The backend send_message validates the target
    // exists AND is in this chat (404 otherwise); the new Message row carries
    // reply_to_message_id, and the response/broadcast embed the quote preview.
    if (replyToMessageId) {
      formData.append("reply_to_message_id", replyToMessageId)
    }
    const response = await client.post<Message>(`/chats/${chatId}/messages`, formData)
    return response.data
  },

  // Wave 211 — forward 1..N messages from a source chat into a destination chat
  // (snapshot-copy: the backend copies content + attachments + a "Forwarded from X"
  // label; the source is never dereferenced cross-chat — privacy). JSON body, no
  // file upload (the snapshot comes from the source). The actor must be a
  // participant of BOTH chats (403 otherwise). Returns the created messages in
  // source order; the single-message UI reads [0].
  forwardMessages: async (
    destChatId: string,
    sourceChatId: string,
    messageIds: string[]
  ): Promise<Message[]> => {
    const response = await client.post<Message[]>(`/chats/${destChatId}/forward`, {
      source_chat_id: sourceChatId,
      message_ids: messageIds,
    })
    return response.data
  },

  markRead: async (chatId: string) => {
    const response = await client.post(`/chats/${chatId}/read`)
    return response.data
  },

  // Wave 207 — fire-and-forget typing indicator. The frontend WS connects to
  // ws-hub, whose allowedMessageTypes drops "typing" frames — so the client posts
  // here instead; the backend broadcasts to the other participants via the W204
  // bridge. The hook throttles the call to 500ms; the caller swallows errors
  // (typing is ephemeral).
  sendTyping: async (chatId: string): Promise<void> => {
    await client.post(`/chats/${chatId}/typing`)
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

  // Wave 207 — list the users who reacted to a message with one emoji (the
  // reactor-list "who reacted" popover). On-demand; emoji as a query param,
  // matching the DELETE route shape (W206 SW7). GET coexists with POST + DELETE
  // at this path (backend routes by method).
  getReactors: async (chatId: string, messageId: string, emoji: string): Promise<Reactor[]> => {
    const response = await client.get<Reactor[]>(
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
