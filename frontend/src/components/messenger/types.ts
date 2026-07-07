export interface Contact {
  id: string
  name: string
  avatar: string
  lastMessage: string
  lastMessageTime: string
  unread: number
  online: boolean
  // Wave 211 G4 — group identity (absent/false for a DM). isGroup => render the
  // GroupAvatar glyph instead of the photo + suppress the presence dot;
  // memberCount drives the group header subtitle.
  isGroup?: boolean
  memberCount?: number
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
  // Wave 212 — Seen by N of M receipts for group chats
  seenByCount?: number
  seenByTotal?: number
  // Wave 205 — edit + soft-delete. editedAtLabel is the pre-formatted "(edited)"
  // time tooltip; deletedAt set => render the "Message deleted" tombstone (drops
  // the bubble content, attachments and the edit/delete affordance).
  editedAt?: string | null
  editedAtLabel?: string
  deletedAt?: string | null
  attachments?: Attachment[]
  // Wave 206 — per-emoji reaction aggregates (camelCase UI shape; mapped from
  // the API snake_case in useMessengerController's transform). reactedByMe drives
  // the active-pill styling + toggle direction.
  reactions?: { emoji: string; count: number; reactedByMe: boolean }[]
  // Wave 207 — reply/quote preview. `isMe` is resolved at transform time
  // (reply_to.sender_id === user.id) so ChatWindow can render the "You" vs name
  // author label without threading currentUserId; `deletedAt` set => render the
  // "original deleted" placeholder. null/absent when this message isn't a reply.
  replyTo?: {
    id: string
    senderName: string | null
    isMe: boolean
    text: string
    deletedAt: string | null
  } | null
  // Wave 211 — denormalized "Forwarded from X" label (null/absent = not a forward).
  // Snapshot-copy forwarding: ChatWindow renders a "Forwarded from {name}" chip
  // above the bubble content. Mapped from the API `forwarded_from_name` in
  // useMessengerController's transform.
  forwardedFromName?: string | null
  // Wave 208 SW5 — message-list annotations computed in useMessengerController's
  // transform. showDateDivider marks the first message of a new calendar day
  // (ChatWindow renders a "Today / Yesterday / <date>" divider above the bubble);
  // dateLabel is the pre-resolved divider text. isGroupStart marks the first
  // message of a sender-run (different sender, a > 5min gap, or a new day) — when
  // explicitly false ChatWindow hides the avatar + tightens spacing (Telegram
  // grouping). All optional so optimistic / standalone messages render without
  // them (undefined === "show avatar, no grouping").
  showDateDivider?: boolean
  dateLabel?: string
  isGroupStart?: boolean
}
