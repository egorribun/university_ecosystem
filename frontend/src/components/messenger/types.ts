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
  attachments?: Attachment[]
}
