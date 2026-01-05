import { useState, useEffect, useCallback, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate, useParams } from "react-router-dom"
import {
  ContactList,
  ChatWindow,
  MessageInput,
  NewChatModal,
} from "../components/messenger/MessengerComponents"
import { useMediaQuery } from "@mui/material"
import { useAuth } from "../contexts/AuthContext"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  chatApi,
  type Chat,
  type ChatMaintenanceResult,
  type ChatsListResponse,
  type Message,
  type MessagesListResponse,
  type PresenceStatus,
} from "../api/chat"
import { useChatWebSocket } from "../hooks/useChatWebSocket"
import SmartImage from "@/components/SmartImage"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import type { User } from "@/types/User"
import client from "@/api/client"
import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"

dayjs.extend(utc)

const formatMessageTime = (dateString: string) => {
  if (!dateString) return ""

  // Fix: Remove microseconds which confuse the parser in some environments
  // 2025-12-16T01:53:34.310903Z -> 2025-12-16T01:53:34Z
  const cleanDate = dateString.replace(/(\.\d+)(Z|[+-]\d{2}:?\d{2})?$/, "$2")

  // Parse as UTC and convert to local timezone
  const parsed = dayjs.utc(cleanDate)

  return parsed.local().format("HH:mm")
}

interface ConfirmDialogProps {
  open: boolean
  title: string
  message: string
  confirmText: string
  cancelText: string
  variant?: "danger" | "warning" | "default"
  onConfirm: () => void
  onCancel: () => void
}

function ConfirmDialog({
  open,
  title,
  message,
  confirmText,
  cancelText,
  variant = "default",
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null

  const confirmButtonClasses =
    variant === "danger"
      ? "bg-red-500 hover:bg-red-600 text-white"
      : variant === "warning"
        ? "bg-yellow-500 hover:bg-yellow-600 text-white"
        : "bg-blue-500 hover:bg-blue-600 text-white"

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-sm p-6 space-y-4 border border-gray-200 dark:border-gray-800">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{title}</h3>
        <p className="text-sm text-gray-600 dark:text-gray-400">{message}</p>
        <div className="flex gap-3 justify-end pt-2">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            className={`px-4 py-2 text-sm rounded-lg transition-colors ${confirmButtonClasses}`}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Messenger() {
  const { t } = useTranslation(["messenger", "common"])
  const { user } = useAuth()
  const { chatId } = useParams<{ chatId: string }>()
  const navigate = useNavigate()
  const isMobile = useMediaQuery("(max-width: 768px)")
  const queryClient = useQueryClient()

  const [selectedChatId, setSelectedChatId] = useState<string | null>(null)
  const [isNewChatModalOpen, setIsNewChatModalOpen] = useState(false)
  const [showSearchInChat, setShowSearchInChat] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [showChatMenu, setShowChatMenu] = useState(false)
  const [profileUser, setProfileUser] = useState<User | null>(null)
  const [isProfileLoading, setIsProfileLoading] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)
  const [presenceMap, setPresenceMap] = useState<Record<number, PresenceStatus>>({})
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean
    title: string
    message: string
    variant: "danger" | "warning" | "default"
    onConfirm: () => void
  } | null>(null)

  // WebSocket for real-time updates (uses cookie-based auth)
  const { isConnected, sendTyping, sendRead, getTypingUsersForChat } = useChatWebSocket({
    enabled: !!user,
    onPresenceUpdate: (userId, active, lastSeen) => {
      setPresenceMap((prev) => ({
        ...prev,
        [userId]: { active, last_seen_at: lastSeen },
      }))

      queryClient.setQueryData<ChatsListResponse | undefined>(["chats"], (old) => {
        if (!old) return old
        const items = old.items.map((chat) => {
          const participates = chat.participants.some((p) => p.id === userId)
          if (!participates) return chat

          const nextPresence = { ...(chat.presence || {}) }
          nextPresence[userId] = { active, last_seen_at: lastSeen }
          return { ...chat, presence: nextPresence }
        })

        return { ...old, items }
      })
    },
  })

  // Update selectedChatId when chatId param changes (e.g. from notification)
  // Fetch Chats with paginated response
  const { data: chatsData, isLoading: chatsLoading } = useQuery({
    queryKey: ["chats"],
    queryFn: () => chatApi.getChats(),
  })
  const chats = chatsData?.items ?? []

  // Fetch single chat data if specified via URL but not in the first page of chats
  const { data: singleChatData } = useQuery({
    queryKey: ["chats", chatId],
    queryFn: () => (chatId ? chatApi.getChat(chatId) : Promise.reject("No chatId")),
    enabled: !!chatId && !chats.some((c) => c.id === chatId),
    retry: false,
  })

  // Ensure selectedChatId stays in sync with URL
  useEffect(() => {
    if (chatId) {
      setSelectedChatId(chatId)
    } else {
      setSelectedChatId(null)
    }
  }, [chatId])

  // Get current active chat object (either from list or direct fetch)
  const activeChat = useMemo(() => {
    if (!selectedChatId) return null
    const inList = chats.find((c) => c.id === selectedChatId)
    if (inList) return inList
    if (singleChatData && singleChatData.id === selectedChatId) return singleChatData
    return null
  }, [selectedChatId, chats, singleChatData])

  useEffect(() => {
    if (!chatsData?.items) return

    setPresenceMap((prev) => {
      const next = { ...prev }
      chatsData.items.forEach((chat) => {
        Object.entries(chat.presence || {}).forEach(([id, status]) => {
          const userId = Number(id)
          next[userId] = status
        })
      })
      return next
    })
  }, [chatsData])

  // Fetch Messages for selected chat with paginated response
  const { data: messagesData, isLoading: messagesLoading } = useQuery({
    queryKey: ["messages", selectedChatId],
    queryFn: () =>
      selectedChatId
        ? chatApi.getMessages(selectedChatId)
        : Promise.resolve({ items: [], has_more: false, next_cursor: null }),
    enabled: !!selectedChatId,
    // No more polling needed - WebSocket handles real-time updates
  })
  const messages = messagesData?.items ?? []

  // Memoize transformed messages to prevent infinite re-renders in ChatWindow
  const transformedMessages = useMemo(() => {
    return messages.map((m) => ({
      id: m.id,
      senderId: String(m.sender_id),
      text: m.content,
      timestamp: formatMessageTime(m.created_at),
      isMe: m.sender_id === user?.id,
      status: (m.read_status ? "read" : "sent") as "read" | "sent",
      attachments: m.attachments?.map((a) => ({
        id: a.id,
        url: a.url,
        type: a.file_type,
        name: a.filename,
        size: a.size,
      })),
    }))
  }, [messages, user?.id])

  // Send Message Mutation
  const sendMessageMutation = useMutation({
    mutationFn: ({ chatId, content, files }: { chatId: string; content: string; files?: File[] }) =>
      chatApi.sendMessage(chatId, content, files),
    onSuccess: (newMessage) => {
      queryClient.setQueryData<MessagesListResponse | undefined>(
        ["messages", selectedChatId],
        (old) => {
          const items = old?.items ?? []
          return {
            has_more: old?.has_more ?? false,
            next_cursor: old?.next_cursor ?? null,
            items: [...items, newMessage],
          }
        }
      )
      queryClient.invalidateQueries({ queryKey: ["chats"] })
    },
  })

  // Mark Read Mutation
  const markReadMutation = useMutation({
    mutationFn: (chatId: string) => chatApi.markRead(chatId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chats"] })
    },
  })

  // Create Chat Mutation
  const createChatMutation = useMutation({
    mutationFn: (participantId: string) => chatApi.createChat(participantId),
    onSuccess: (newChat) => {
      queryClient.invalidateQueries({ queryKey: ["chats"] })
      setSelectedChatId(newChat.id)
      setIsNewChatModalOpen(false)
    },
  })

  const clearChatMutation = useMutation({
    mutationFn: (chatId: string) => chatApi.clearChat(chatId),
    onMutate: async (chatId) => {
      await queryClient.cancelQueries({ queryKey: ["messages", chatId] })
      await queryClient.cancelQueries({ queryKey: ["chats"] })

      const previousMessages = queryClient.getQueryData<MessagesListResponse>(["messages", chatId])
      const previousChats = queryClient.getQueryData<ChatsListResponse>(["chats"])

      queryClient.setQueryData<MessagesListResponse>(["messages", chatId], {
        items: [],
        has_more: false,
        next_cursor: null,
      })

      if (previousChats) {
        queryClient.setQueryData<ChatsListResponse>(["chats"], {
          ...previousChats,
          items: previousChats.items.map((chat) =>
            chat.id === chatId
              ? {
                  ...chat,
                  last_message: undefined,
                  unread_count: 0,
                  updated_at: new Date().toISOString(),
                }
              : chat
          ),
        })
      }

      return { previousMessages, previousChats }
    },
    onError: (_error, chatId, context) => {
      if (context?.previousMessages) {
        queryClient.setQueryData(["messages", chatId], context.previousMessages)
      }
      if (context?.previousChats) {
        queryClient.setQueryData(["chats"], context.previousChats)
      }
    },
    onSuccess: () => {
      setShowChatMenu(false)
    },
    onSettled: (data, error, chatId) => {
      queryClient.invalidateQueries({ queryKey: ["messages", chatId] })
      queryClient.invalidateQueries({ queryKey: ["chats"] })
    },
  })

  const deleteChatMutation = useMutation({
    mutationFn: (chatId: string) => chatApi.deleteChat(chatId),
    onMutate: async (chatId) => {
      await queryClient.cancelQueries({ queryKey: ["chats"] })
      const previousChats = queryClient.getQueryData<ChatsListResponse>(["chats"])

      if (previousChats) {
        queryClient.setQueryData<ChatsListResponse>(["chats"], {
          ...previousChats,
          items: previousChats.items.filter((chat) => chat.id !== chatId),
        })
      }

      if (selectedChatId === chatId) {
        setSelectedChatId(null)
      }

      return { previousChats }
    },
    onError: (_error, chatId, context) => {
      if (context?.previousChats) {
        queryClient.setQueryData(["chats"], context.previousChats)
      }
    },
    onSuccess: (_data: ChatMaintenanceResult, chatId) => {
      queryClient.removeQueries({ queryKey: ["messages", chatId] })
      setShowChatMenu(false)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["chats"] })
    },
  })

  // Stable callback for marking messages as read
  const markAsRead = useCallback((chatId: string) => {
    markReadMutation.mutate(chatId)
  }, [])

  // Mark messages as read when opening a chat
  useEffect(() => {
    if (selectedChatId) {
      markAsRead(selectedChatId)
    }
  }, [selectedChatId, markAsRead])

  // Helper to get the other participant
  const getOtherParticipant = (chat: Chat) => {
    return chat.participants.find((p) => p.id !== user?.id)
  }

  const handleSendMessage = (text: string, files: File[]) => {
    if (!selectedChatId) return
    sendMessageMutation.mutate({ chatId: selectedChatId, content: text, files })
  }

  const handleClearChat = () => {
    if (!selectedChatId) return
    const chatId = selectedChatId
    setConfirmDialog({
      open: true,
      title: t("messenger:clearChatTitle", "Clear Chat"),
      message: t("messenger:confirmClear", "Clear chat history for everyone?"),
      variant: "warning",
      onConfirm: () => {
        clearChatMutation.mutate(chatId)
        setConfirmDialog(null)
      },
    })
  }

  const handleDeleteChat = () => {
    if (!selectedChatId) return
    const chatId = selectedChatId
    setConfirmDialog({
      open: true,
      title: t("messenger:deleteChatTitle", "Delete Chat"),
      message: t("messenger:confirmDelete", "Delete this chat for all participants?"),
      variant: "danger",
      onConfirm: () => {
        deleteChatMutation.mutate(chatId)
        setConfirmDialog(null)
      },
    })
  }

  const handleViewProfile = () => {
    setShowChatMenu(false)
    const other = activeChat && getOtherParticipant(activeChat)
    if (!other) return
    setIsProfileLoading(true)
    setProfileError(null)
    client
      .get<User>(`/users/${other.id}`)
      .then((response) => setProfileUser(response.data))
      .catch(() =>
        setProfileError(t("messenger:profileLoadError", "Unable to load participant profile"))
      )
      .finally(() => setIsProfileLoading(false))
  }

  // Transform chats for ContactList component
  const contacts = chats.map((chat) => {
    const other = getOtherParticipant(chat)
    const status = other ? presenceMap[other.id] : undefined
    return {
      id: chat.id,
      name: other?.full_name || "Unknown User",
      avatar: other?.avatar_url || "",
      lastMessage: chat.last_message?.content || "",
      lastMessageTime: chat.last_message ? formatMessageTime(chat.last_message.created_at) : "",
      unread: chat.unread_count,
      online: status?.active ?? false,
    }
  })

  // Mobile view logic
  const showList = !isMobile || !selectedChatId
  const showChat = !isMobile || selectedChatId

  const isBottomNavVisible = useMediaQuery("(max-width: 900px)")

  return (
    <div
      className="flex overflow-hidden text-gray-900 dark:text-gray-100 font-sans"
      style={{
        height: "100%",
        paddingBottom: isBottomNavVisible
          ? "calc(var(--bn-h) + env(safe-area-inset-bottom) + 16px)"
          : 0,
        background: "var(--msg-chat-bg)",
      }}
    >
      {/* Sidebar */}
      <div
        className={`${
          showList ? "flex" : "hidden"
        } w-full md:w-80 lg:w-96 flex-col border-r transition-all duration-300 h-full`}
        style={{
          background: "var(--msg-sidebar-bg)",
          borderColor: "var(--msg-header-border)",
        }}
      >
        <div
          className="p-4 flex justify-between items-center sticky top-0 z-10 backdrop-blur-md"
          style={{
            background: "var(--msg-header-bg)",
            borderBottom: "1px solid var(--msg-header-border)",
          }}
        >
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
            {t("messenger:title", "Messages")}
          </h1>
          <button
            onClick={() => setIsNewChatModalOpen(true)}
            className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            style={{ color: "var(--msg-sidebar-active)" }}
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
                d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10"
              />
            </svg>
          </button>
        </div>

        <div className="p-3" style={{ background: "var(--msg-sidebar-bg)" }}>
          <div className="relative">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
              />
            </svg>
            <input
              type="text"
              placeholder={t("messenger:search", "Search")}
              className="w-full pl-9 pr-4 py-2.5 rounded-xl border-none focus:ring-2 outline-none transition-all text-sm"
              style={{
                background: "var(--msg-input-bg)",
              }}
            />
          </div>
        </div>

        <ContactList
          contacts={contacts}
          selectedId={selectedChatId}
          onSelect={(id) => navigate(`/messenger/${id}`)}
        />
      </div>

      {/* Chat Area */}
      <div
        className={`${showChat ? "flex" : "hidden"} flex-1 flex flex-col overflow-hidden`}
        style={{ background: "var(--msg-chat-bg)" }}
      >
        {selectedChatId && activeChat ? (
          <>
            {/* Chat Header - Fixed */}
            {!showSearchInChat ? (
              <div className="msg-header flex-shrink-0 h-16 flex items-center px-4 justify-between z-10">
                <div className="flex items-center gap-3">
                  {isMobile && (
                    <button
                      onClick={() => setSelectedChatId(null)}
                      className="p-1.5 -ml-2 mr-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
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
                          d="M15.75 19.5L8.25 12l7.5-7.5"
                        />
                      </svg>
                    </button>
                  )}
                  <div className="relative">
                    <SmartImage
                      srcRaw={getOtherParticipant(activeChat)?.avatar_url || AVATAR_PLACEHOLDER_URL}
                      fallback={AVATAR_PLACEHOLDER_URL}
                      alt={getOtherParticipant(activeChat)?.full_name || ""}
                      className="w-10 h-10 rounded-full object-cover"
                    />
                    {presenceMap[getOtherParticipant(activeChat)?.id ?? 0]?.active && (
                      <span className="msg-online-indicator absolute bottom-0 right-0 w-3 h-3"></span>
                    )}
                  </div>
                  <div>
                    <h2 className="font-semibold text-[15px] leading-tight">
                      {getOtherParticipant(activeChat)?.full_name}
                    </h2>
                    {presenceMap[getOtherParticipant(activeChat)?.id ?? 0]?.active && (
                      <p className="text-xs" style={{ color: "var(--msg-online-color)" }}>
                        {t("messenger:online", "online")}
                      </p>
                    )}
                  </div>
                </div>

                {/* Search and Menu buttons */}
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowSearchInChat(true)}
                    className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                      strokeWidth={1.5}
                      stroke="currentColor"
                      className="w-5 h-5 text-gray-600 dark:text-gray-300"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
                      />
                    </svg>
                  </button>
                  <div className="relative">
                    <button
                      onClick={() => setShowChatMenu(!showChatMenu)}
                      className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        fill="none"
                        viewBox="0 0 24 24"
                        strokeWidth={1.5}
                        stroke="currentColor"
                        className="w-5 h-5 text-gray-600 dark:text-gray-300"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M12 6.75a.75.75 0 110-1.5.75.75 0 010 1.5zM12 12.75a.75.75 0 110-1.5.75.75 0 010 1.5zM12 18.75a.75.75 0 110-1.5.75.75 0 010 1.5z"
                        />
                      </svg>
                    </button>
                    {showChatMenu && (
                      <div className="absolute right-0 top-full mt-2 bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 py-2 min-w-[200px] z-20">
                        <button
                          onClick={handleViewProfile}
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
                              d="M17.982 18.725A7.488 7.488 0 0012 15.75a7.488 7.488 0 00-5.982 2.975m11.963 0a9 9 0 10-11.963 0m11.963 0A8.966 8.966 0 0112 21a8.966 8.966 0 01-5.982-2.275M15 9.75a3 3 0 11-6 0 3 3 0 016 0z"
                            />
                          </svg>
                          <span className="text-sm">
                            {t("messenger:viewProfile", "View Profile")}
                          </span>
                        </button>
                        <button
                          onClick={handleClearChat}
                          className="w-full px-4 py-2 text-left hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-3 text-gray-700 dark:text-gray-200"
                        >
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            fill="none"
                            viewBox="0 0 24 24"
                            strokeWidth={1.5}
                            stroke="currentColor"
                            className="w-5 h-5 text-yellow-500"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M12 9.75v6.75m0 0l-3-3m3 3l3-3m-8.25 6a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z"
                            />
                          </svg>
                          <span className="text-sm">{t("messenger:clearChat", "Clear Chat")}</span>
                        </button>
                        <button
                          onClick={handleDeleteChat}
                          className="w-full px-4 py-2 text-left hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-3 text-gray-700 dark:text-gray-200"
                        >
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            fill="none"
                            viewBox="0 0 24 24"
                            strokeWidth={1.5}
                            stroke="currentColor"
                            className="w-5 h-5 text-red-500"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"
                            />
                          </svg>
                          <span className="text-sm">
                            {t("messenger:deleteChat", "Delete Chat")}
                          </span>
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex-shrink-0 h-16 border-b border-gray-200 dark:border-gray-800 flex items-center px-4 bg-white/80 dark:bg-[#0b111e]/80 backdrop-blur-md z-10">
                <button
                  onClick={() => {
                    setShowSearchInChat(false)
                    setSearchQuery("")
                  }}
                  className="p-1 mr-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={1.5}
                    stroke="currentColor"
                    className="w-6 h-6"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={t("messenger:searchMessages", "Search messages...")}
                  className="flex-1 px-4 py-2 rounded-xl bg-gray-100 dark:bg-gray-800 border-none focus:ring-2 focus:ring-blue-500 outline-none transition-all text-sm"
                  autoFocus
                />
              </div>
            )}

            <ChatWindow messages={transformedMessages} />
            <MessageInput onSend={handleSendMessage} />
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
            <div
              className="w-28 h-28 rounded-full flex items-center justify-center mb-5"
              style={{ background: "var(--msg-sidebar-hover)" }}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1}
                stroke="currentColor"
                className="w-14 h-14"
                style={{ color: "var(--msg-empty-icon)" }}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M8.625 9.75a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375m-13.5 3.01c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.184-4.183a1.14 1.14 0 01.778-.332 48.294 48.294 0 005.83-.498c1.585-.233 2.708-1.626 2.708-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z"
                />
              </svg>
            </div>
            <h3 className="text-lg font-medium text-gray-600 dark:text-gray-400">
              {t("messenger:selectChat", "Select a chat to start messaging")}
            </h3>
          </div>
        )}
      </div>

      <NewChatModal
        open={isNewChatModalOpen}
        onClose={() => setIsNewChatModalOpen(false)}
        onSelect={(userId) => createChatMutation.mutate(userId)}
      />

      {(profileUser || isProfileLoading || profileError) && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-30 p-4">
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-md p-6 space-y-4 border border-gray-200 dark:border-gray-800">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                {profileUser?.full_name || t("messenger:profile", "Profile")}
              </h3>
              <button
                onClick={() => {
                  setProfileUser(null)
                  setProfileError(null)
                }}
                className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={1.5}
                  stroke="currentColor"
                  className="w-5 h-5"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {isProfileLoading && (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {t("messenger:loadingProfile", "Loading profile...")}
              </p>
            )}

            {profileError && (
              <p className="text-sm text-red-600 dark:text-red-400">{profileError}</p>
            )}

            {profileUser && (
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <SmartImage
                    srcRaw={profileUser.avatar_url || AVATAR_PLACEHOLDER_URL}
                    fallback={AVATAR_PLACEHOLDER_URL}
                    alt={profileUser.full_name ?? ""}
                    className="w-14 h-14 rounded-full object-cover border border-gray-200 dark:border-gray-700"
                  />
                  <div>
                    <p className="font-semibold text-gray-900 dark:text-gray-100">
                      {profileUser.full_name}
                    </p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">{profileUser.email}</p>
                  </div>
                </div>
                <div className="text-sm text-gray-600 dark:text-gray-300 space-y-1">
                  <p>
                    {t("messenger:status", "Status")}:{" "}
                    {profileUser.is_active
                      ? t("common:active", "Active")
                      : t("common:inactive", "Inactive")}
                  </p>
                  {profileUser.avatar_url && (
                    <a
                      className="text-blue-600 dark:text-blue-400 underline"
                      href={profileUser.avatar_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {t("messenger:viewAvatar", "Open avatar")}
                    </a>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Custom Confirmation Dialog */}
      <ConfirmDialog
        open={confirmDialog?.open ?? false}
        title={confirmDialog?.title ?? ""}
        message={confirmDialog?.message ?? ""}
        confirmText={t("common:confirm", "Confirm")}
        cancelText={t("common:cancel", "Cancel")}
        variant={confirmDialog?.variant}
        onConfirm={confirmDialog?.onConfirm ?? (() => {})}
        onCancel={() => setConfirmDialog(null)}
      />
    </div>
  )
}
