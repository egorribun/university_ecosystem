import type { RxJsonSchema } from "rxdb"

export interface MessageDoc {
  id: string
  chat_id: string
  sender_id: string
  content: string
  created_at: string
  read_status?: boolean
  read_at?: string | null
  edited_at?: string | null
  deleted_at?: string | null
  attachments?: any[]
  reactions?: any[]
  sync_status?: string
}

export const messagesSchema: RxJsonSchema<MessageDoc> = {
  version: 0,
  primaryKey: "id",
  type: "object",
  properties: {
    id: { type: "string", maxLength: 100 },
    chat_id: { type: "string", maxLength: 100 },
    sender_id: { type: "string" },
    content: { type: "string" },
    created_at: { type: "string", maxLength: 50 },
    read_status: { type: "boolean" },
    read_at: { type: ["string", "null"] },
    edited_at: { type: ["string", "null"] },
    deleted_at: { type: ["string", "null"] },
    attachments: { type: "array" },
    reactions: { type: "array" },
    sync_status: { type: "string" },
  },
  required: ["id", "chat_id", "sender_id", "content", "created_at"],
  indexes: ["chat_id", "created_at", ["chat_id", "created_at"]],
}
