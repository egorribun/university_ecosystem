import React, { useRef, useEffect, useState, useCallback } from "react"
import { useVirtualizer } from "@tanstack/react-virtual"
import { useTranslation } from "react-i18next"
import {
  Dialog,
  DialogTitle,
  DialogContent,
  TextField,
  List,
  ListItem,
  ListItemButton,
  ListItemAvatar,
  Avatar,
  ListItemText,
  IconButton,
} from "@mui/material"
import CloseIcon from "@mui/icons-material/Close"
import { useQuery } from "@tanstack/react-query"
import client from "../../api/client"
import type { User } from "../../types/User"
import SmartImage from "@/components/SmartImage"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"

// Sanitize URLs to prevent XSS attacks
function sanitizeUrl(url: string): string | null {
  try {
    const parsed = new URL(url, window.location.origin)
    const protocol = parsed.protocol.toLowerCase()
    // Only allow http, https, and blob (for local object URLs)
    if (protocol === "javascript:" || protocol === "data:" || protocol === "vbscript:") {
      return null
    }
    return url
  } catch {
    return null
  }
}

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
  text: string
  timestamp: string
  isMe: boolean
  status?: "sent" | "read"
  attachments?: Attachment[]
}

interface ContactListProps {
  contacts: Contact[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export const ContactList: React.FC<ContactListProps> = ({ contacts, selectedId, onSelect }) => {
  return (
    <div
      className="flex-1 overflow-y-auto custom-scrollbar"
      style={{ background: "var(--msg-sidebar-bg)" }}
    >
      {contacts.map((contact) => (
        <div
          key={contact.id}
          role="button"
          tabIndex={0}
          onClick={() => onSelect(contact.id)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault()
              onSelect(contact.id)
            }
          }}
          className={`msg-contact-item flex items-center gap-3 p-3 mx-2 my-0.5 rounded-xl cursor-pointer ${selectedId === contact.id ? "active" : ""
            }`}
        >
          <div className="relative flex-shrink-0">
            <SmartImage
              srcRaw={contact.avatar || AVATAR_PLACEHOLDER_URL}
              fallback={AVATAR_PLACEHOLDER_URL}
              alt={contact.name}
              className="w-[52px] h-[52px] rounded-full object-cover"
            />
            {contact.online && (
              <span className="msg-online-indicator absolute bottom-0 right-0"></span>
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex justify-between items-center mb-0.5">
              <h3
                className={`font-semibold text-[15px] truncate ${selectedId === contact.id ? "text-white" : "text-gray-900 dark:text-gray-100"
                  }`}
              >
                {contact.name}
              </h3>
              <span
                className={`text-xs flex-shrink-0 ml-2 ${selectedId === contact.id ? "text-white/70" : "text-gray-500 dark:text-gray-400"
                  }`}
              >
                {contact.lastMessageTime}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <p
                className={`text-[14px] truncate flex-1 ${selectedId === contact.id ? "text-white/80" : "text-gray-500 dark:text-gray-400"
                  }`}
              >
                {contact.lastMessage}
              </p>
              {contact.unread > 0 && (
                <span className="msg-unread-badge">
                  {contact.unread > 99 ? "99+" : contact.unread}
                </span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

interface ChatWindowProps {
  messages: Message[]
}

export const ChatWindow: React.FC<ChatWindowProps> = ({ messages }) => {
  const containerRef = useRef<HTMLDivElement>(null)
  const [isAtBottom, setIsAtBottom] = useState(true)

  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => 80, // Estimated height for a message bubble
    overscan: 5, // Render 5 extra items above/below viewport
    getItemKey: (index) => messages[index].id,
  })

  // Auto-scroll to bottom when new messages arrive (if already at bottom)
  useEffect(() => {
    if (isAtBottom && messages.length > 0) {
      virtualizer.scrollToIndex(messages.length - 1, { align: "end" })
    }
  }, [messages.length, isAtBottom, virtualizer])

  // Track if user is at bottom of scroll
  const handleScroll = useCallback(() => {
    if (!containerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 100
    setIsAtBottom(isNearBottom)
  }, [])

  // Scroll to bottom on initial mount
  useEffect(() => {
    if (messages.length > 0) {
      virtualizer.scrollToIndex(messages.length - 1, { align: "end" })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="msg-chat-area flex-1 min-h-0 overflow-y-auto p-4 custom-scrollbar relative"
    >
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: "100%",
          position: "relative",
        }}
      >
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const msg = messages[virtualRow.index]
          return (
            <div
              key={virtualRow.key}
              data-index={virtualRow.index}
              ref={virtualizer.measureElement}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              <div
                className={`flex py-0.5 ${msg.isMe ? "justify-end md:justify-start" : "justify-start"}`}
              >
                <div
                  className={`max-w-[75%] md:max-w-[60%] px-3.5 py-2 text-[15px] relative ${msg.isMe
                    ? "msg-bubble-sent text-white rounded-2xl rounded-br-md"
                    : "msg-bubble-received text-gray-900 dark:text-gray-100 rounded-2xl rounded-bl-md"
                    }`}
                >
                  {msg.attachments && msg.attachments.length > 0 && (
                    <div className="mb-2 space-y-2">
                      {msg.attachments.map((att) => (
                        <div key={att.id}>
                          {att.type === "image" ? (
                            sanitizeUrl(att.url) ? (
                              <img
                                src={sanitizeUrl(att.url)!}
                                alt={att.name}
                                className="rounded-xl max-w-full h-auto max-h-64 object-cover cursor-pointer hover:opacity-90 transition-opacity"
                                onClick={() => {
                                  const safe = sanitizeUrl(att.url)
                                  if (safe) window.open(safe, "_blank", "noopener,noreferrer")
                                }}
                              />
                            ) : null
                          ) : sanitizeUrl(att.url) ? (
                            <a
                              href={sanitizeUrl(att.url)!}
                              target="_blank"
                              rel="noopener noreferrer"
                              className={`flex items-center gap-2 p-2.5 rounded-xl ${msg.isMe
                                ? "bg-white/20 hover:bg-white/30"
                                : "bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600"
                                } transition-colors`}
                            >
                              <svg
                                xmlns="http://www.w3.org/2000/svg"
                                fill="none"
                                viewBox="0 0 24 24"
                                strokeWidth={1.5}
                                stroke="currentColor"
                                className="w-5 h-5"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
                                />
                              </svg>
                              <span className="truncate max-w-[150px] text-sm">{att.name}</span>
                            </a>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  )}
                  <p className="break-words leading-snug">{msg.text}</p>
                  <div className="flex items-center justify-end gap-1 mt-1">
                    <span
                      className="text-[11px]"
                      style={{
                        color: msg.isMe ? "var(--msg-timestamp-sent)" : "var(--msg-timestamp-received)",
                      }}
                    >
                      {msg.timestamp}
                    </span>
                    {msg.isMe && (
                      <span style={{ color: "var(--msg-timestamp-sent)" }}>
                        {msg.status === "read" ? (
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            viewBox="0 0 16 16"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth={2}
                            className="w-4 h-4"
                          >
                            <polyline
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              points="1,8 4,11 11,4"
                            />
                            <polyline strokeLinecap="round" strokeLinejoin="round" points="7,11 14,4" />
                          </svg>
                        ) : (
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth={2.5}
                            className="w-4 h-4"
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.5l5 5L19 8" />
                          </svg>
                        )}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

interface MessageInputProps {
  onSend: (text: string, files: File[]) => void
}

export const MessageInput: React.FC<MessageInputProps> = ({ onSend }) => {
  const { t } = useTranslation(["messenger"])
  const [text, setText] = useState("")
  const [showAttachMenu, setShowAttachMenu] = useState(false)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleSend = () => {
    console.log("MessageInput handleSend:", {
      text,
      filesCount: selectedFiles.length,
      files: selectedFiles,
    })
    if (text.trim() || selectedFiles.length > 0) {
      onSend(text, selectedFiles)
      setText("")
      setSelectedFiles([])
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleAttachmentClick = (type: "photo" | "file" | "document") => {
    setShowAttachMenu(false)
    if (fileInputRef.current) {
      switch (type) {
        case "photo":
          fileInputRef.current.accept = "image/png,image/jpeg,image/gif,image/webp"
          break
        case "document":
          fileInputRef.current.accept = ".pdf,.doc,.docx,.txt"
          break
        case "file":
          fileInputRef.current.accept = "*"
          break
      }
      fileInputRef.current.click()
    }
  }

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      const filteredFiles = await Promise.all(
        Array.from(files).map(async (file) => {
          // Exclude by MIME type and extension
          if (file.type === "image/svg+xml" || file.name.toLowerCase().endsWith(".svg")) {
            return null
          }
          // Additional check for actual file content starting with <svg or <?xml ... <svg
          if (file.type.startsWith("image/")) {
            try {
              const text = await file.slice(0, 512).text()
              if (/^\s*(<\?xml[^>]*>\s*)?<svg[\s>]/i.test(text)) {
                // Found SVG content, exclude it
                return null
              }
            } catch {
              // Ignore parse error, allow file
            }
          }
          return file
        })
      )
      setSelectedFiles((prev) => [...prev, ...filteredFiles.filter((f) => !!f)])
    }
    // Reset input value to allow selecting the same file again
    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
  }

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index))
  }

  return (
    <div
      className="flex-shrink-0 p-3 z-[2500] relative"
      style={{ background: "var(--msg-sidebar-bg)" }}
    >
      {selectedFiles.length > 0 && (
        <div className="flex gap-2 mb-3 overflow-x-auto pb-2 custom-scrollbar">
          {selectedFiles.map((file, index) =>
            file.type === "image/svg+xml" || file.name.toLowerCase().endsWith(".svg") ? null : (
              <div key={index} className="relative flex-shrink-0 group">
                {file.type.startsWith("image/") ? (
                  <img
                    src={
                      ["image/png", "image/jpeg", "image/gif", "image/webp"].includes(file.type)
                        ? URL.createObjectURL(file)
                        : ""
                    }
                    alt={file.name}
                    className="w-16 h-16 object-cover rounded-xl border border-gray-200 dark:border-gray-700"
                  />
                ) : (
                  <div className="w-16 h-16 flex items-center justify-center bg-gray-100 dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                      strokeWidth={1.5}
                      stroke="currentColor"
                      className="w-8 h-8 text-gray-400"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
                      />
                    </svg>
                  </div>
                )}
                <button
                  onClick={() => removeFile(index)}
                  className="absolute -top-1.5 -right-1.5 bg-red-500 text-white rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity shadow-md hover:bg-red-600"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    className="w-3 h-3"
                  >
                    <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                  </svg>
                </button>
              </div>
            )
          )}
        </div>
      )}
      <div className="msg-input-container flex items-end gap-1 px-2 py-1.5">
        <div className="relative">
          <button
            onClick={() => setShowAttachMenu(!showAttachMenu)}
            className="p-2.5 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 transition-colors rounded-full hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke="currentColor"
              className="w-5 h-5"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13"
              />
            </svg>
          </button>

          {showAttachMenu && (
            <div className="msg-attach-menu absolute bottom-full left-0 mb-2 py-2 min-w-[180px] z-20">
              <button
                onClick={() => handleAttachmentClick("photo")}
                className="w-full px-4 py-2.5 text-left hover:bg-gray-100 dark:hover:bg-gray-800 flex items-center gap-3 text-gray-700 dark:text-gray-200 transition-colors"
              >
                <div className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={2}
                    stroke="white"
                    className="w-4 h-4"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z"
                    />
                  </svg>
                </div>
                <span className="text-[15px] font-medium">
                  {t("messenger:attachPhoto", "Photo")}
                </span>
              </button>
              <button
                onClick={() => handleAttachmentClick("document")}
                className="w-full px-4 py-2.5 text-left hover:bg-gray-100 dark:hover:bg-gray-800 flex items-center gap-3 text-gray-700 dark:text-gray-200 transition-colors"
              >
                <div className="w-8 h-8 rounded-full bg-green-500 flex items-center justify-center">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={2}
                    stroke="white"
                    className="w-4 h-4"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
                    />
                  </svg>
                </div>
                <span className="text-[15px] font-medium">
                  {t("messenger:attachDocument", "Document")}
                </span>
              </button>
              <button
                onClick={() => handleAttachmentClick("file")}
                className="w-full px-4 py-2.5 text-left hover:bg-gray-100 dark:hover:bg-gray-800 flex items-center gap-3 text-gray-700 dark:text-gray-200 transition-colors"
              >
                <div className="w-8 h-8 rounded-full bg-purple-500 flex items-center justify-center">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={2}
                    stroke="white"
                    className="w-4 h-4"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
                    />
                  </svg>
                </div>
                <span className="text-[15px] font-medium">{t("messenger:attachFile", "File")}</span>
              </button>
            </div>
          )}

          <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileSelect} />
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t("messenger:typeMessage", "Message")}
          className="flex-1 bg-transparent border-none focus:ring-0 outline-none resize-none max-h-32 py-2.5 px-1 text-[15px] text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400"
          rows={1}
          style={{ minHeight: "24px" }}
        />
        <button
          onClick={handleSend}
          disabled={!text.trim() && selectedFiles.length === 0}
          className={`msg-send-btn flex-shrink-0 relative z-10 ${text.trim() || selectedFiles.length > 0 ? "" : "opacity-40"}`}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            className="w-5 h-5 pointer-events-none"
          >
            <path d="M3.478 2.405a.75.75 0 00-.926.94l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.405z" />
          </svg>
        </button>
      </div>
    </div>
  )
}

interface NewChatModalProps {
  open: boolean
  onClose: () => void
  onSelect: (userId: string) => void
}

export const NewChatModal: React.FC<NewChatModalProps> = ({ open, onClose, onSelect }) => {
  const { t } = useTranslation(["messenger", "common"])
  const [search, setSearch] = useState("")

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["users", search],
    queryFn: async () => {
      if (!search) return []
      const response = await client.get<User[]>(`/users?limit=10&search=${search}`)
      return response.data
    },
    enabled: open && search.length > 1,
  })

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        {t("messenger:newChat", "New Chat")}
        <IconButton onClick={onClose} aria-label={t("common:close", "Close")}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent>
        <TextField
          autoFocus
          margin="dense"
          label={t("messenger:searchUsers", "Search Users")}
          type="text"
          fullWidth
          variant="outlined"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <List>
          {isLoading && <ListItem>{t("common:loading", "Loading...")}</ListItem>}
          {users.map((user) => (
            <ListItem key={user.id} disablePadding>
              <ListItemButton onClick={() => onSelect(String(user.id))}>
                <ListItemAvatar>
                  <Avatar src={user.avatar_url || undefined} alt={user.full_name || ""}>
                    {user.full_name?.[0] || "?"}
                  </Avatar>
                </ListItemAvatar>
                <ListItemText primary={user.full_name} secondary={user.email} />
              </ListItemButton>
            </ListItem>
          ))}
        </List>
      </DialogContent>
    </Dialog>
  )
}
