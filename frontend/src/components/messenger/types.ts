export interface Contact {
  id: string
  name: string
  avatar: string
  lastMessage: string
  lastMessageTime: string
  unread: number
  online: boolean
}

export interface Attachment {
  id: string
  url: string
  type: "image" | "video" | "file"
  name: string
  size: number
}

export interface Message {
  id: string
  senderId: string
  senderName?: string
  senderAvatar?: string
  text: string
  timestamp: string
  isMe: boolean
  status?: "sent" | "read"
  // Wave 203 SW6 — read receipts. readAtLabel is the pre-formatted HH:MM string;
  // isLastRead marks the single most-recent read sent message that renders the
  // "Seen · HH:MM" marker (computed in useMessengerController's transform).
  readAt?: string | null
  readAtLabel?: string
  isLastRead?: boolean
  // Wave 205 — edit + soft-delete. editedAtLabel is the pre-formatted "(edited)"
  // time tooltip; deletedAt set => render the "Message deleted" tombstone (drops
  // the bubble content, attachments and the edit/delete affordance).
  editedAt?: string | null
  editedAtLabel?: string
  deletedAt?: string | null
  attachments?: Attachment[]
}
