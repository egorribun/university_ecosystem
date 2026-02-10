import React, { useRef, useEffect, useState, useCallback, memo } from "react"
import { motion, AnimatePresence, LayoutGroup } from "framer-motion"
import { sanitizeUrl } from "@/utils/media"
import { useVirtualizer } from "@tanstack/react-virtual"
import { useTranslation } from "react-i18next"
import { Search, X, FileText, Image as ImageIcon, File, Paperclip, Send } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import client from "../../api/client"
import type { User } from "../../types/User"
import SmartImage from "@/components/SmartImage"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import { cn } from "@/utils/cn"

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
    <div className="flex-1 overflow-y-auto custom-scrollbar p-2 bg-(--msg-sidebar-bg)">
      <LayoutGroup>
        {contacts.map((contact) => (
          <motion.div
            layout
            key={contact.id}
            role="button"
            tabIndex={0}
            onClick={() => onSelect(contact.id)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault()
                onSelect(contact.id)
              }
            }}
            whileHover={{ x: 4 }}
            whileTap={{ scale: 0.98 }}
            className={cn(
              "msg-contact-item flex items-center gap-3 p-3 mb-1 rounded-2xl cursor-pointer transition-all duration-300",
              selectedId === contact.id
                ? "active bg-(--brand-main) text-white"
                : "hover:bg-(--bg-surface-hover)/10"
            )}
          >
            <div className="relative shrink-0">
              <SmartImage
                srcRaw={contact.avatar || AVATAR_PLACEHOLDER_URL}
                fallback={AVATAR_PLACEHOLDER_URL}
                alt={contact.name}
                className="w-12 h-12 rounded-full object-cover shadow-sm"
              />
              {contact.online && (
                <span className="msg-online-indicator absolute bottom-0 right-0 w-3.5 h-3.5 rounded-full bg-(--success-bg) border-2 border-(--bg-surface) dark:border-(--bg-page)"></span>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex justify-between items-center mb-0.5">
                <h3
                  className={cn(
                    "font-bold text-base truncate sf-pro",
                    selectedId === contact.id ? "text-white" : "text-(--text-primary)"
                  )}
                >
                  {contact.name}
                </h3>
                <span
                  className={cn(
                    "text-xs shrink-0 ml-2 font-medium uppercase tracking-tight",
                    selectedId === contact.id
                      ? "text-white/70"
                      : "text-(--text-secondary) opacity-60"
                  )}
                >
                  {contact.lastMessageTime}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <p
                  className={cn(
                    "text-sm truncate flex-1 leading-tight",
                    selectedId === contact.id ? "text-white/80" : "text-(--text-secondary)"
                  )}
                >
                  {contact.lastMessage}
                </p>
                {contact.unread > 0 && (
                  <motion.span
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    className="msg-unread-badge min-w-5 h-5 px-1 bg-(--error-text) text-white rounded-full text-[0.6rem] font-black flex items-center justify-center shadow-lg shadow-(--error-text)/20"
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
          const message = messages[virtualRow.index]
          if (!message) return null

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
                className={cn(
                  "flex items-end gap-2 md:gap-3 py-1 w-full md:flex-row group",
                  message.isMe
                    ? "flex-row-reverse justify-start md:justify-start"
                    : "flex-row justify-start"
                )}
              >
                <div className="shrink-0 mb-1">
                  <SmartImage
                    srcRaw={message.senderAvatar || AVATAR_PLACEHOLDER_URL}
                    fallback={AVATAR_PLACEHOLDER_URL}
                    alt={message.senderName || ""}
                    className="w-8 h-8 md:w-9 md:h-9 rounded-full object-cover shadow-sm ring-1 ring-black/5 dark:ring-white/5"
                  />
                </div>

                <div
                  className={cn(
                    "max-w-[80%] md:max-w-[70%] px-4 py-2.5 text-base relative",
                    message.isMe
                      ? "msg-bubble-sent text-white rounded-2xl rounded-br-sm md:rounded-br-2xl md:rounded-bl-sm"
                      : "msg-bubble-received text-(--text-primary) rounded-2xl rounded-bl-sm shadow-sm"
                  )}
                >
                  {message.attachments && message.attachments.length > 0 && (
                    <div className="mb-2 space-y-2">
                      {message.attachments.map((attachment) => (
                        <div key={attachment.id} className="overflow-hidden rounded-xl">
                          {attachment.type === "image" ? (
                            sanitizeUrl(attachment.url) ? (
                              <SmartImage
                                srcRaw={attachment.url}
                                alt={attachment.name}
                                className="w-full h-auto max-h-72 object-cover cursor-pointer hover:scale-[1.02] transition-transform duration-500"
                                onClick={() => {
                                  const safe = sanitizeUrl(attachment.url)
                                  if (safe) window.open(safe, "_blank", "noopener,noreferrer")
                                }}
                              />
                            ) : null
                          ) : sanitizeUrl(attachment.url) ? (
                            <a
                              href={sanitizeUrl(attachment.url)!}
                              target="_blank"
                              rel="noopener noreferrer"
                              className={cn(
                                "flex items-center gap-3 p-3 rounded-xl transition-colors border border-white/5",
                                message.isMe
                                  ? "bg-white/15 hover:bg-white/25"
                                  : "bg-(--bg-surface-raised)/50 hover:bg-(--bg-surface-hover)/50"
                              )}
                            >
                              <div className="p-2 rounded-lg bg-white/10 text-(--brand-main)">
                                <File className="w-5 h-5" />
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="truncate text-sm font-bold">{attachment.name}</p>
                                <p className="text-[0.65rem] opacity-60 font-medium">
                                  {(attachment.size / 1024).toFixed(1)} KB
                                </p>
                              </div>
                            </a>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  )}
                  <p className="wrap-break-word leading-relaxed whitespace-pre-wrap">
                    {message.text}
                  </p>
                  <div className="flex items-center justify-end gap-1.5 mt-1 opacity-80">
                    <span
                      className="text-[0.65rem] font-bold uppercase tracking-wider"
                      style={{
                        color: message.isMe ? "var(--primary-subtle)" : "var(--text-secondary)",
                      }}
                    >
                      {message.timestamp}
                    </span>
                    {message.isMe && (
                      <span className="flex items-center opacity-80">
                        {message.status === "read" ? (
                          <svg
                            viewBox="0 0 16 16"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth={2.5}
                            className="w-3 h-3 text-white"
                          >
                            <polyline points="1,8 4,11 11,4" />
                            <polyline points="7,11 14,4" />
                          </svg>
                        ) : (
                          <svg
                            viewBox="0 0 16 16"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth={2.5}
                            className="w-3 h-3 text-white opacity-60"
                          >
                            <polyline points="4,12 8,16 16,8" />
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
    if (text.trim() || selectedFiles.length > 0) {
      onSend(text, selectedFiles)
      setText("")
      setSelectedFiles([])
      setShowAttachMenu(false)
    }
  }

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault()
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

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files
    if (files && files.length > 0) {
      const filteredFiles = await Promise.all(
        Array.from(files).map(async (file) => {
          if (file.type === "image/svg+xml" || file.name.toLowerCase().endsWith(".svg")) {
            return null
          }
          if (file.type.startsWith("image/")) {
            try {
              const fileText = await file.slice(0, 512).text()
              if (/^\s*(<\?xml[^>]*>\s*)?<svg[\s>]/i.test(fileText)) return null
            } catch {}
          }
          return file
        })
      )
      setSelectedFiles((previousFiles) => [
        ...previousFiles,
        ...filteredFiles.filter((file) => !!file),
      ])
    }
    if (fileInputRef.current) fileInputRef.current.value = ""
  }

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index))
  }

  return (
    <div className="shrink-0 p-3 z-(--z-popover) relative border-t border-(--glass-border)/10 bg-(--bg-surface)/30 backdrop-blur-xl">
      {selectedFiles.length > 0 && (
        <div className="flex gap-2 mb-3 overflow-x-auto pb-2 custom-scrollbar">
          {selectedFiles.map((file, index) => (
            <div key={index} className="relative shrink-0 group">
              {file.type.startsWith("image/") ? (
                <SmartImage
                  srcRaw={URL.createObjectURL(file)}
                  alt={file.name}
                  className="w-16 h-16 object-cover rounded-xl border border-(--glass-border)/20 shadow-sm"
                />
              ) : (
                <div className="shrink-0 flex items-center justify-center h-10 w-10 md:h-12 md:w-12 bg-(--bg-surface-raised) rounded-xl border border-(--glass-border)/20 shadow-sm text-(--text-secondary)">
                  <FileText className="w-8 h-8" />
                </div>
              )}
              <button
                onClick={() => removeFile(index)}
                className="absolute -top-1.5 -right-1.5 bg-(--error-text) text-white rounded-full p-1 shadow-lg hover:bg-(--error-text)/80 transition-colors"
                aria-label="Remove"
              >
                <X className="w-3 h-3" strokeWidth={3} />
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2 bg-(--bg-surface-hover)/10 rounded-2xl border border-(--glass-border)/20 p-2 focus-within:ring-4 focus-within:ring-(--brand-main)/5 focus-within:border-(--brand-main)/30 transition-all duration-300">
        <div className="relative">
          <motion.button
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            onClick={() => setShowAttachMenu(!showAttachMenu)}
            className={cn(
              "p-2.5 rounded-xl transition-colors hover:bg-(--bg-surface-hover)/30",
              showAttachMenu
                ? "text-(--brand-main) bg-(--brand-main)/10"
                : "text-(--text-secondary)"
            )}
            aria-label="Attachments"
          >
            <Paperclip
              className={cn(
                "w-5 h-5 transition-transform duration-300",
                showAttachMenu && "rotate-45"
              )}
            />
          </motion.button>

          <AnimatePresence>
            {showAttachMenu && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 10 }}
                className="absolute bottom-full left-0 mb-4 py-2 min-w-[200px] bg-(--bg-surface)/90 backdrop-blur-2xl rounded-2xl border border-(--glass-border) shadow-2xl overflow-hidden ring-1 ring-black/5"
              >
                {[
                  {
                    id: "photo",
                    icon: ImageIcon,
                    label: "Photo",
                    color: "text-(--primary-main) bg-(--primary-main)/10",
                  },
                  {
                    id: "document",
                    icon: FileText,
                    label: "Document",
                    color: "text-(--success-text) bg-(--success-text)/10",
                  },
                  {
                    id: "file",
                    icon: File,
                    label: "File",
                    color: "text-(--warning-text) bg-(--warning-text)/10",
                  },
                ].map((item, index) => (
                  <button
                    key={item.id}
                    onClick={() => handleAttachmentClick(item.id as any)}
                    className="w-full px-4 py-3 flex items-center gap-3 hover:bg-(--bg-surface-hover) transition-colors text-left group"
                  >
                    <div
                      className={cn(
                        "w-8 h-8 rounded-lg flex items-center justify-center transition-transform group-hover:scale-110",
                        item.color
                      )}
                    >
                      <item.icon className="w-4.5 h-4.5" />
                    </div>
                    <span className="text-sm font-bold text-(--text-primary)">
                      {t(`messenger:attach${item.label}`)}
                    </span>
                  </button>
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
          placeholder={t("messenger:typeMessage", "Message...")}
          className="flex-1 bg-transparent border-none focus:ring-0 outline-none resize-none max-h-48 py-2 md:py-2.5 px-1 text-base text-(--text-primary) placeholder:text-(--text-secondary) placeholder:opacity-50"
          rows={1}
        />
        <motion.button
          whileHover={text.trim() || selectedFiles.length > 0 ? { scale: 1.1 } : {}}
          whileTap={text.trim() || selectedFiles.length > 0 ? { scale: 0.9 } : {}}
          onClick={handleSend}
          disabled={!text.trim() && selectedFiles.length === 0}
          className={cn(
            "p-2.5 rounded-xl transition-all duration-300",
            text.trim() || selectedFiles.length > 0
              ? "bg-(--brand-main) text-white shadow-lg shadow-(--brand-main)/30"
              : "bg-(--bg-surface-hover)/10 text-(--text-secondary) opacity-30 cursor-not-allowed"
          )}
        >
          <Send className="w-5 h-5" fill="currentColor" />
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
          className="fixed inset-0 bg-black/60 backdrop-blur-md flex items-center justify-center z-(--z-modal) p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.95, opacity: 0, y: 20 }}
            className="bg-(--bg-surface)/90 backdrop-blur-2xl rounded-3xl shadow-2xl w-full max-w-md overflow-hidden border border-(--glass-border) ring-1 ring-white/10"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="p-6 pb-4 flex items-center justify-between border-b border-(--glass-border)/10 bg-(--bg-surface)/50">
              <h3 className="text-xl font-black tracking-tight text-(--text-primary) sf-pro">
                {t("messenger:newChat", "New Chat")}
              </h3>
              <button
                onClick={onClose}
                className="p-2 rounded-xl hover:bg-(--bg-surface-hover)/50 text-(--text-secondary) transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6">
              <div className="relative group mb-6">
                <Search className="w-4.5 h-4.5 absolute left-3.5 top-1/2 -translate-y-1/2 text-(--text-secondary) group-focus-within:text-(--brand-main) transition-colors" />
                <input
                  type="text"
                  autoFocus
                  placeholder={t("messenger:searchUsers", "Search users by name or email...")}
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  className="w-full pl-11 pr-4 py-3 rounded-2xl border border-(--glass-border)/20 bg-(--bg-surface-raised)/40 focus:ring-4 focus:ring-(--brand-main)/10 focus:border-(--brand-main)/40 outline-none transition-all text-base font-medium text-(--text-primary) placeholder:text-(--text-secondary) placeholder:opacity-50"
                />
              </div>

              <div className="max-h-[350px] overflow-y-auto custom-scrollbar pr-1 -mr-1">
                {isLoading && (
                  <div className="flex flex-col items-center py-10">
                    <div className="w-10 h-10 border-4 border-(--brand-main)/10 border-t-(--brand-main) rounded-full animate-spin"></div>
                  </div>
                )}

                {!isLoading && users.length === 0 && search.length > 1 && (
                  <div className="text-center py-12 px-4 space-y-2">
                    <div className="w-16 h-16 rounded-full bg-(--bg-surface-raised) mx-auto flex items-center justify-center text-(--text-secondary) opacity-20">
                      <Search className="w-8 h-8" />
                    </div>
                    <p className="text-sm font-bold text-(--text-secondary) opacity-60">
                      {t("messenger:noUsersFound", "No users found matching your search")}
                    </p>
                  </div>
                )}

                <div className="space-y-1">
                  {users.map((user) => (
                    <motion.button
                      key={user.id}
                      whileHover={{ x: 4, backgroundColor: "var(--bg-surface-hover)" }}
                      whileTap={{ scale: 0.98 }}
                      onClick={() => onSelect(String(user.id))}
                      className="w-full flex items-center gap-4 p-3.5 rounded-2xl transition-all text-left group"
                    >
                      <div className="relative shrink-0">
                        <SmartImage
                          srcRaw={user.avatar_url || AVATAR_PLACEHOLDER_URL}
                          fallback={AVATAR_PLACEHOLDER_URL}
                          alt={user.full_name || ""}
                          className="w-11 h-11 rounded-2xl object-cover shadow-sm ring-1 ring-black/5"
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-base font-black truncate leading-tight text-(--text-primary) group-hover:text-(--brand-main) transition-colors sf-pro">
                          {user.full_name}
                        </p>
                        <p className="text-xs text-(--text-secondary) truncate font-medium opacity-60">
                          {user.email}
                        </p>
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






