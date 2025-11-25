import React, { useRef, useEffect, useState } from "react"
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
    <div className="flex-1 overflow-y-auto custom-scrollbar">
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
          className={`flex items-center gap-3 p-3 mx-2 my-1 rounded-xl cursor-pointer transition-all duration-200 ${selectedId === contact.id
            ? "bg-blue-500 text-white shadow-md shadow-blue-500/20"
            : "hover:bg-gray-100 dark:hover:bg-gray-800"
            }`}
        >
          <div className="relative flex-shrink-0">
            <SmartImage
              srcRaw={contact.avatar || AVATAR_PLACEHOLDER_URL}
              fallback={AVATAR_PLACEHOLDER_URL}
              alt={contact.name}
              className="w-12 h-12 rounded-full object-cover bg-gray-200"
            />
            {contact.online && (
              <span
                className={`absolute bottom-0 right-0 w-3.5 h-3.5 border-2 rounded-full ${selectedId === contact.id ? "border-blue-500 bg-white" : "border-white dark:border-[#0b111e] bg-green-500"}`}
              ></span>
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex justify-between items-baseline">
              <h3
                className={`font-semibold text-sm truncate ${selectedId === contact.id ? "text-white" : "text-gray-900 dark:text-gray-100"}`}
              >
                {contact.name}
              </h3>
              <span
                className={`text-xs ${selectedId === contact.id ? "text-blue-100" : "text-gray-500"}`}
              >
                {contact.lastMessageTime}
              </span>
            </div>
            <p
              className={`text-sm truncate ${selectedId === contact.id ? "text-blue-100" : "text-gray-500 dark:text-gray-400"}`}
            >
              {contact.lastMessage}
            </p>
          </div>
          {contact.unread > 0 && (
            <span
              className={`flex items-center justify-center min-w-[20px] h-5 px-1.5 text-xs font-bold rounded-full ${selectedId === contact.id ? "bg-white text-blue-600" : "bg-blue-500 text-white"}`}
            >
              {contact.unread}
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

interface ChatWindowProps {
  messages: Message[]
}

export const ChatWindow: React.FC<ChatWindowProps> = ({ messages }) => {
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [messages])

  return (
    <div
      ref={containerRef}
      className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4 custom-scrollbar relative bg-white/95 dark:bg-[#060b14]/95"
    >
      <div className="relative z-0 space-y-4">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.isMe ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[75%] md:max-w-[60%] px-4 py-2 rounded-2xl shadow-sm text-sm md:text-base relative group ${msg.isMe
                ? "bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-br-none"
                : "bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-bl-none border border-gray-100 dark:border-gray-700"
                }`}
            >
              {msg.attachments && msg.attachments.length > 0 && (
                <div className="mb-2 space-y-2">
                  {msg.attachments.map((att) => (
                    <div key={att.id}>
                      {att.type === "image" ? (
                        <img
                          src={att.url}
                          alt={att.name}
                          className="rounded-lg max-w-full h-auto max-h-64 object-cover cursor-pointer hover:opacity-90 transition-opacity"
                          onClick={() => window.open(att.url, "_blank")}
                        />
                      ) : (
                        <a
                          href={att.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={`flex items-center gap-2 p-2 rounded-lg ${msg.isMe
                            ? "bg-blue-500/50 hover:bg-blue-500/70"
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
                          <span className="truncate max-w-[150px]">{att.name}</span>
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              )}
              <p className="break-words">{msg.text}</p>
              <div className="flex items-center justify-end gap-1 mt-1">
                <span
                  className={`text-[10px] ${msg.isMe ? "text-blue-100" : "text-gray-400"
                    }`}
                >
                  {msg.timestamp}
                </span>
                {msg.isMe && (
                  <span className={msg.isMe ? "text-blue-100" : "text-gray-400"}>
                    {msg.status === "read" ? (
                      <div className="flex -space-x-1">
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          viewBox="0 0 20 20"
                          fill="currentColor"
                          className="w-3 h-3"
                        >
                          <path
                            fillRule="evenodd"
                            d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"
                            clipRule="evenodd"
                          />
                        </svg>
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          viewBox="0 0 20 20"
                          fill="currentColor"
                          className="w-3 h-3"
                        >
                          <path
                            fillRule="evenodd"
                            d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"
                            clipRule="evenodd"
                          />
                        </svg>
                      </div>
                    ) : (
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 20 20"
                        fill="currentColor"
                        className="w-3 h-3"
                      >
                        <path
                          fillRule="evenodd"
                          d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"
                          clipRule="evenodd"
                        />
                      </svg>
                    )}
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

interface MessageInputProps {
  onSend: (text: string, files: File[]) => void
}

export const MessageInput: React.FC<MessageInputProps> = ({ onSend }) => {
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

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      const filteredFiles = Array.from(files).filter(
        (file) => !(file.type === "image/svg+xml") && !file.name.toLowerCase().endsWith(".svg")
      )
      setSelectedFiles((prev) => [...prev, ...filteredFiles])
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
    <div className="flex-shrink-0 p-4 bg-white dark:bg-[#0b111e] border-t border-gray-200 dark:border-gray-800 z-10">
      {selectedFiles.length > 0 && (
        <div className="flex gap-2 mb-2 overflow-x-auto pb-2 custom-scrollbar">
          {selectedFiles.map((file, index) =>
            file.type === "image/svg+xml" || file.name.toLowerCase().endsWith(".svg") ? null : (
              <div key={index} className="relative flex-shrink-0 group">
                {file.type.startsWith("image/") ? (
                  <img
                    src={URL.createObjectURL(file)}
                    alt={file.name}
                    className="w-16 h-16 object-cover rounded-lg border border-gray-200 dark:border-gray-700"
                  />
                ) : (
                  <div className="w-16 h-16 flex items-center justify-center bg-gray-100 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
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
                  className="absolute -top-1 -right-1 bg-red-500 text-white rounded-full p-0.5 opacity-0 group-hover:opacity-100 transition-opacity shadow-sm"
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
      <div className="flex items-end gap-2 bg-gray-100 dark:bg-gray-800/50 p-2 rounded-2xl border border-transparent focus-within:border-blue-500/50 focus-within:bg-white dark:focus-within:bg-gray-800 transition-all duration-200">
        <div className="relative">
          <button
            onClick={() => setShowAttachMenu(!showAttachMenu)}
            className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="w-6 h-6"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13"
              />
            </svg>
          </button>

          {showAttachMenu && (
            <div className="absolute bottom-full left-0 mb-2 bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 py-2 min-w-[180px] z-20">
              <button
                onClick={() => handleAttachmentClick("photo")}
                className="w-full px-4 py-2 text-left hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-3 text-gray-700 dark:text-gray-200"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={1.5}
                  stroke="currentColor"
                  className="w-5 h-5 text-blue-500"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z"
                  />
                </svg>
                <span className="text-sm">Photo</span>
              </button>
              <button
                onClick={() => handleAttachmentClick("document")}
                className="w-full px-4 py-2 text-left hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-3 text-gray-700 dark:text-gray-200"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={1.5}
                  stroke="currentColor"
                  className="w-5 h-5 text-green-500"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
                  />
                </svg>
                <span className="text-sm">Document</span>
              </button>
              <button
                onClick={() => handleAttachmentClick("file")}
                className="w-full px-4 py-2 text-left hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-3 text-gray-700 dark:text-gray-200"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={1.5}
                  stroke="currentColor"
                  className="w-5 h-5 text-purple-500"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m6.75 12l-3-3m0 0l-3 3m3-3v6m-1.5-15H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
                  />
                </svg>
                <span className="text-sm">File</span>
              </button>
            </div>
          )}

          <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileSelect} />
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Write a message..."
          className="flex-1 bg-transparent border-none focus:ring-0 outline-none resize-none max-h-32 py-2 text-gray-900 dark:text-gray-100 placeholder-gray-500"
          rows={1}
          style={{ minHeight: "24px" }}
        />
        <button
          onClick={handleSend}
          disabled={!text.trim() && selectedFiles.length === 0}
          className={`p-2 rounded-xl transition-all duration-200 ${text.trim() || selectedFiles.length > 0
            ? "bg-blue-600 text-white shadow-lg shadow-blue-600/30 hover:bg-blue-700 transform hover:scale-105"
            : "bg-gray-200 dark:bg-gray-700 text-gray-400 cursor-not-allowed"
            }`}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            className="w-5 h-5"
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
        New Chat
        <IconButton onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent>
        <TextField
          autoFocus
          margin="dense"
          label="Search Users"
          type="text"
          fullWidth
          variant="outlined"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <List>
          {isLoading && <ListItem>Loading...</ListItem>}
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
