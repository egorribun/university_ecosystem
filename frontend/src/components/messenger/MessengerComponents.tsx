import React, { useRef, useEffect, useState, useCallback, memo } from "react"
import { motion, AnimatePresence, LayoutGroup } from "framer-motion"
import { sanitizeUrl } from "@/utils/media"
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

interface ContactListProps {
  contacts: Contact[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export const ContactList: React.FC<ContactListProps> = ({ contacts, selectedId, onSelect }) => {
  return (
    <div
      className="flex-1 overflow-y-auto custom-scrollbar p-2"
      style={{ background: "var(--msg-sidebar-bg)" }}
    >
      <LayoutGroup>
        {contacts.map((contact) => (
          <motion.div
            layout
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
            whileHover={{ x: 4 }}
            whileTap={{ scale: 0.98 }}
            className={`msg-contact-item flex items-center gap-3 p-3 mb-1 rounded-2xl cursor-pointer ${
              selectedId === contact.id ? "active" : ""
            }`}
          >
            <div className="relative flex-shrink-0">
              <SmartImage
                srcRaw={contact.avatar || AVATAR_PLACEHOLDER_URL}
                fallback={AVATAR_PLACEHOLDER_URL}
                alt={contact.name}
                className="w-12 h-12 rounded-full object-cover shadow-sm"
              />
              {contact.online && (
                <span className="msg-online-indicator absolute bottom-0 right-0 w-3 h-3"></span>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex justify-between items-center mb-0.5">
                <h3
                  className={`font-bold text-[15px] truncate ${
                    selectedId === contact.id ? "text-white" : "text-gray-900 dark:text-gray-100"
                  } sf-pro`}
                >
                  {contact.name}
                </h3>
                <span
                  className={`text-[11px] flex-shrink-0 ml-2 font-medium ${
                    selectedId === contact.id ? "text-white/70" : "text-gray-500 dark:text-gray-400"
                  }`}
                >
                  {contact.lastMessageTime}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <p
                  className={`text-[13px] truncate flex-1 leading-tight ${
                    selectedId === contact.id ? "text-white/80" : "text-gray-500 dark:text-gray-400"
                  }`}
                >
                  {contact.lastMessage}
                </p>
                {contact.unread > 0 && (
                  <motion.span
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    className="msg-unread-badge"
                  >
                    {contact.unread > 99 ? "99+" : contact.unread}
                  </motion.span>
                )}
              </div>
            </div>
          </motion.div>
        ))}
      </LayoutGroup>
    </div>
  )
}

interface ChatWindowProps {
  messages: Message[]
}

const ChatWindow: React.FC<ChatWindowProps> = memo(({ messages }) => {
  const containerRef = useRef<HTMLDivElement>(null)

  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => 80,
    overscan: 5,
  })

  const prevMessagesLengthRef = useRef(0)

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (messages.length > prevMessagesLengthRef.current) {
      virtualizer.scrollToIndex(messages.length - 1, { align: "end", behavior: "auto" })
    }
    prevMessagesLengthRef.current = messages.length
  }, [messages.length, virtualizer])

  // Initial scroll to bottom
  useEffect(() => {
    if (messages.length > 0) {
      virtualizer.scrollToIndex(messages.length - 1, { align: "end", behavior: "auto" })
    }
  }, [])

  return (
    <div
      ref={containerRef}
      className="msg-chat-area flex-1 min-h-0 overflow-y-auto p-4 custom-scrollbar"
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
          if (!msg) return null

          return (
            <div
              key={virtualRow.key}
              ref={virtualizer.measureElement}
              data-index={virtualRow.index}
              className="absolute top-0 left-0 w-full"
              style={{
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              <motion.div
                initial={{ opacity: 0, y: 10, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
                className={`flex items-end gap-2 md:gap-3 py-1 w-full md:flex-row ${
                  msg.isMe
                    ? "flex-row-reverse justify-start md:justify-start"
                    : "flex-row justify-start"
                } group`}
              >
                <div className="flex-shrink-0 mb-1">
                  <SmartImage
                    srcRaw={msg.senderAvatar || AVATAR_PLACEHOLDER_URL}
                    fallback={AVATAR_PLACEHOLDER_URL}
                    alt={msg.senderName || ""}
                    className="w-8 h-8 md:w-9 md:h-9 rounded-full object-cover shadow-sm ring-1 ring-black/5 dark:ring-white/5"
                  />
                </div>

                <div
                  className={`max-w-[80%] md:max-w-[70%] px-4 py-2.5 text-[15px] relative ${
                    msg.isMe
                      ? "msg-bubble-sent text-white rounded-2xl rounded-br-sm md:rounded-br-2xl md:rounded-bl-sm"
                      : "msg-bubble-received text-gray-900 dark:text-gray-100 rounded-2xl rounded-bl-sm shadow-sm"
                  }`}
                >
                  {msg.attachments && msg.attachments.length > 0 && (
                    <div className="mb-2 space-y-2">
                      {msg.attachments.map((att) => (
                        <div key={att.id} className="overflow-hidden rounded-xl">
                          {att.type === "image" ? (
                            sanitizeUrl(att.url) ? (
                              <SmartImage
                                srcRaw={att.url}
                                alt={att.name}
                                className="w-full h-auto max-h-72 object-cover cursor-pointer hover:scale-[1.02] transition-transform duration-500"
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
                              className={`flex items-center gap-3 p-3 rounded-xl ${
                                msg.isMe
                                  ? "bg-white/15 hover:bg-white/25"
                                  : "bg-gray-200/50 dark:bg-gray-700/50 hover:bg-gray-300/50 dark:hover:bg-gray-600/50"
                              } transition-colors border border-white/5`}
                            >
                              <div className="p-2 rounded-lg bg-white/10">
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
                                    d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
                                  />
                                </svg>
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="truncate text-sm font-medium">{att.name}</p>
                                <p className="text-[10px] opacity-60">
                                  {(att.size / 1024).toFixed(1)} KB
                                </p>
                              </div>
                            </a>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  )}
                  <p className="break-words leading-relaxed whitespace-pre-wrap">{msg.text}</p>
                  <div className="flex items-center justify-end gap-1.5 mt-1 opacity-80">
                    <span
                      className="text-[10px] font-medium"
                      style={{
                        color: msg.isMe
                          ? "var(--msg-timestamp-sent)"
                          : "var(--msg-timestamp-received)",
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
                            strokeWidth={2.5}
                            className="w-3 h-3"
                          >
                            <polyline
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              points="1,8 4,11 11,4"
                            />
                            <polyline
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              points="7,11 14,4"
                            />
                          </svg>
                        ) : (
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth={3}
                            className="w-3 h-3"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M4.5 12.5l5 5L19 8"
                            />
                          </svg>
                        )}
                      </span>
                    )}
                  </div>
                </div>
              </motion.div>
            </div>
          )
        })}
      </div>
    </div>
  )
})
ChatWindow.displayName = "ChatWindow"
export { ChatWindow }

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
                  <SmartImage
                    srcRaw={
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
      <div className="msg-input-container flex items-end gap-1 px-3 py-2 pb-[calc(0.25rem+env(safe-area-inset-bottom))]">
        <div className="relative">
          <motion.button
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            onClick={() => setShowAttachMenu(!showAttachMenu)}
            className="p-2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 transition-colors rounded-full hover:bg-gray-100/50 dark:hover:bg-gray-800/50"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke="currentColor"
              className={`w-6 h-6 transition-transform duration-300 ${showAttachMenu ? "rotate-45 text-blue-500" : ""}`}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13"
              />
            </svg>
          </motion.button>

          <AnimatePresence>
            {showAttachMenu && (
              <motion.div
                initial={{ opacity: 0, scale: 0.8, y: 10, x: -10 }}
                animate={{ opacity: 1, scale: 1, y: 0, x: 0 }}
                exit={{ opacity: 0, scale: 0.8, y: 10 }}
                className="msg-attach-menu absolute bottom-full left-0 mb-3 py-2 min-w-[200px] z-20 overflow-hidden"
              >
                {[
                  {
                    id: "photo",
                    icon: "M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z",
                    color: "bg-blue-500",
                    label: "Photo",
                  },
                  {
                    id: "document",
                    icon: "M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z",
                    color: "bg-green-500",
                    label: "Document",
                  },
                  {
                    id: "file",
                    icon: "M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5",
                    color: "bg-purple-500",
                    label: "File",
                  },
                ].map((item, idx) => (
                  <motion.button
                    key={item.id}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: idx * 0.05 }}
                    onClick={() => handleAttachmentClick(item.id as any)}
                    className="w-full px-4 py-2.5 text-left hover:bg-gray-100 dark:hover:bg-gray-800 flex items-center gap-3 text-gray-700 dark:text-gray-200 transition-colors"
                  >
                    <div
                      className={`w-8 h-8 rounded-full ${item.color} flex items-center justify-center shadow-sm`}
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        fill="none"
                        viewBox="0 0 24 24"
                        strokeWidth={2}
                        stroke="white"
                        className="w-4 h-4"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d={item.icon} />
                      </svg>
                    </div>
                    <span className="text-[14px] font-semibold">
                      {t(`messenger:attach${item.label}`)}
                    </span>
                  </motion.button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>

          <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileSelect} />
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t("messenger:typeMessage", "Message")}
          className="flex-1 bg-transparent border-none focus:ring-0 outline-none resize-none max-h-48 py-2.5 px-2 text-[15px] text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400"
          rows={1}
          style={{ minHeight: "24px" }}
        />
        <motion.button
          whileHover={text.trim() || selectedFiles.length > 0 ? { scale: 1.1 } : {}}
          whileTap={text.trim() || selectedFiles.length > 0 ? { scale: 0.9 } : {}}
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
        </motion.button>
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
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 bg-black/60 backdrop-blur-md flex items-center justify-center z-[3000] p-4"
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.9, opacity: 0, y: 20 }}
            className="bg-white dark:bg-[#0f172a] rounded-[2rem] shadow-2xl w-full max-w-md overflow-hidden border border-white/10"
          >
            <div
              className="p-6 pb-4 flex items-center justify-between"
              style={{ borderBottom: "1px solid var(--msg-header-border)" }}
            >
              <h3 className="text-xl font-bold tracking-tight sf-pro">
                {t("messenger:newChat", "New Chat")}
              </h3>
              <motion.button
                whileHover={{ rotate: 90, scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                onClick={onClose}
                className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={2}
                  stroke="currentColor"
                  className="w-5 h-5"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </motion.button>
            </div>

            <div className="p-6 pt-4">
              <div className="relative group mb-4">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={2}
                  stroke="currentColor"
                  className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 group-focus-within:text-blue-500 transition-colors"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
                  />
                </svg>
                <input
                  type="text"
                  autoFocus
                  placeholder={t("messenger:searchUsers", "Search Users")}
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 rounded-2xl border-none focus:ring-2 focus:ring-blue-500/30 outline-none transition-all text-[15px] shadow-sm bg-black/5 dark:bg-white/5"
                />
              </div>

              <div className="max-h-[350px] overflow-y-auto custom-scrollbar pr-1">
                {isLoading && (
                  <div className="flex flex-col items-center py-6">
                    <div className="w-8 h-8 border-3 border-blue-500/20 border-t-blue-500 rounded-full animate-spin"></div>
                  </div>
                )}

                {!isLoading && users.length === 0 && search.length > 1 && (
                  <p className="text-center py-8 text-sm text-gray-500 font-medium">
                    {t("messenger:noUsersFound", "No users found")}
                  </p>
                )}

                <div className="space-y-1">
                  {users.map((user) => (
                    <motion.button
                      key={user.id}
                      whileHover={{ x: 4, backgroundColor: "var(--msg-sidebar-hover)" }}
                      whileTap={{ scale: 0.98 }}
                      onClick={() => onSelect(String(user.id))}
                      className="w-full flex items-center gap-3 p-3 rounded-2xl transition-all text-left"
                    >
                      <Avatar
                        src={user.avatar_url || undefined}
                        alt={user.full_name || ""}
                        sx={{ width: 44, height: 44, borderRadius: "14px" }}
                      >
                        {user.full_name?.[0] || "?"}
                      </Avatar>
                      <div className="flex-1 min-w-0">
                        <p className="text-[15px] font-bold truncate leading-tight sf-pro">
                          {user.full_name}
                        </p>
                        <p className="text-[13px] text-gray-500 truncate">{user.email}</p>
                      </div>
                    </motion.button>
                  ))}
                </div>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
