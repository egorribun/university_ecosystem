import { useState, useEffect, useCallback, useMemo, useOptimistic } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { useTranslation } from "react-i18next"
import { useNavigate, useParams } from "react-router-dom"
import {
  ContactList,
  ChatWindow,
  type Message as UiMessage,
  MessageInput,
  NewChatModal,
} from "../components/messenger/MessengerComponents"
import useMediaQuery from "@/hooks/useMediaQuery"
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
import { useMessenger } from "../contexts/MessengerContext"
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
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 bg-black/60 backdrop-blur-md flex items-center justify-center z-4000 p-4"
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.9, opacity: 0, y: 20 }}
            className="bg-white dark:bg-[#0b111e] rounded-4xl shadow-2xl w-full max-w-md overflow-hidden border border-white/10"
          >
            <div className="p-8 space-y-4">
              <h3 className="text-xl font-bold tracking-tight sf-pro">{title}</h3>
              <p className="text-[15px] text-gray-500 font-medium leading-relaxed">{message}</p>
              <div className="flex gap-3 justify-end pt-4">
                <motion.button
                  whileHover={{ scale: 1.05, backgroundColor: "rgba(0,0,0,0.05)" }}
                  whileTap={{ scale: 0.95 }}
                  onClick={onCancel}
                  className="px-6 py-2.5 text-sm font-bold rounded-xl border border-gray-200 dark:border-gray-800 transition-colors"
                >
                  {cancelText}
                </motion.button>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={onConfirm}
                  className={`px-6 py-2.5 text-sm font-bold rounded-xl shadow-lg transition-all ${
                    variant === "danger"
                      ? "bg-red-500 text-white shadow-red-500/20"
                      : variant === "warning"
                        ? "bg-yellow-500 text-white shadow-yellow-500/20"
                        : "bg-blue-500 text-white shadow-blue-500/20"
                  }`}
                >
                  {confirmText}
                </motion.button>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export default function Messenger() {
  const { t } = useTranslation(["messenger", "common"])
  const { user } = useAuth()
  const { chatId } = useParams<{ chatId: string }>()
  const navigate = useNavigate()
  const isMobile = useMediaQuery("(max-width: 768px)")
  const queryClient = useQueryClient()
  const { presenceMap, sendTyping, getTypingUsersForChat } = useMessenger()

  const [selectedChatId, setSelectedChatId] = useState<string | null>(null)
  const [isNewChatModalOpen, setIsNewChatModalOpen] = useState(false)
  const [showSearchInChat, setShowSearchInChat] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [showChatMenu, setShowChatMenu] = useState(false)
  const [profileUser, setProfileUser] = useState<User | null>(null)
  const [isProfileLoading, setIsProfileLoading] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean
    title: string
    message: string
    variant: "danger" | "warning" | "default"
    onConfirm: () => void
  } | null>(null)

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
    return messages.map((m) => {
      const isMe = m.sender_id === user?.id
      return {
        id: m.id,
        senderId: String(m.sender_id),
        senderName: isMe ? (user?.full_name ?? "Me") : (m.sender?.full_name ?? "User"),
        senderAvatar: isMe ? user?.avatar_url || "" : m.sender?.avatar_url || "",
        text: m.content,
        timestamp: formatMessageTime(m.created_at),
        isMe,
        status: (m.read_status ? "read" : "sent") as "read" | "sent",
        attachments: m.attachments?.map((a) => ({
          id: a.id,
          url: a.url,
          type: a.file_type,
          name: a.filename,
          size: a.size,
        })),
      }
    })
  }, [messages, user?.id, user?.full_name, user?.avatar_url])

  // React 19 useOptimistic for instant message feedback
  const [optimisticMessages, addOptimisticMessage] = useOptimistic(
    transformedMessages,
    (state: UiMessage[], newMessage: UiMessage) => [...state, newMessage]
  )

  // Send Message Mutation
  const sendMessageMutation = useMutation({
    mutationFn: ({ chatId, content, files }: { chatId: string; content: string; files?: File[] }) =>
      chatApi.sendMessage(chatId, content, files),
    onSuccess: (newMessage) => {
      queryClient.setQueryData<MessagesListResponse | undefined>(
        ["messages", selectedChatId],
        (old) => {
          const items = old?.items ?? []
          // Check if message already exists (from optimistic to real update ideally, but here simplicity)
          if (items.some((m) => m.id === newMessage.id)) return old

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

    // Optimistic update
    const tempId = crypto.randomUUID()
    const now = new Date()
    addOptimisticMessage({
      id: tempId,
      senderId: String(user?.id),
      senderName: user?.full_name ?? undefined,
      senderAvatar: user?.avatar_url || "",
      text,
      timestamp: formatMessageTime(now.toISOString()),
      isMe: true,
      status: "sent",
      attachments: files.map((f, i) => ({
        id: `${tempId}-${i}`,
        url: URL.createObjectURL(f), // Temporary preview URL
        type: f.type.startsWith("image/") ? "image" : "file",
        name: f.name,
        size: f.size,
      })),
    } as any) // Type cast as our optimistic message shape matches UI needs

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

  const isBottomNavVisible = useMediaQuery("(max-width: 768px)")

  return (
    <div
      className="flex overflow-hidden text-gray-900 dark:text-gray-100 font-sans"
      style={{
        height: "100%",
        paddingBottom: isBottomNavVisible
          ? "calc(var(--bn-h, 4rem) + env(safe-area-inset-bottom, 0px) + 8px)"
          : 0,
        background: "var(--msg-chat-bg)",
      }}
    >
      <AnimatePresence mode="wait">
        {/* Sidebar */}
        {showList && (
          <motion.div
            key="sidebar"
            initial={isMobile ? { x: -300, opacity: 0 } : undefined}
            animate={{ x: 0, opacity: 1 }}
            exit={isMobile ? { x: -300, opacity: 0 } : undefined}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
            className="w-full md:w-80 lg:w-96 flex flex-col border-r h-full relative z-20"
            style={{
              background: "var(--msg-sidebar-bg)",
              borderColor: "var(--msg-header-border)",
            }}
          >
            <div
              className="p-4 flex justify-between items-center sticky top-0 z-20 backdrop-blur-xl"
              style={{
                background: "var(--msg-header-bg)",
                borderBottom: "1px solid var(--msg-header-border)",
              }}
            >
              <h1 className="text-2xl font-bold tracking-tight sf-pro">
                {t("messenger:title", "Messages")}
              </h1>
              <motion.button
                whileHover={{ scale: 1.1, backgroundColor: "var(--msg-sidebar-hover)" }}
                whileTap={{ scale: 0.9 }}
                onClick={() => setIsNewChatModalOpen(true)}
                className="p-2 rounded-full transition-colors bg-blue-500/10"
                style={{ color: "var(--msg-sidebar-active)" }}
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={2.5}
                  stroke="currentColor"
                  className="w-5 h-5"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10"
                  />
                </svg>
              </motion.button>
            </div>

            <div className="p-4" style={{ background: "var(--msg-sidebar-bg)" }}>
              <div className="relative group">
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
                  placeholder={t("messenger:search", "Search")}
                  className="w-full pl-10 pr-4 py-2.5 rounded-2xl border-none focus:ring-2 focus:ring-blue-500/30 outline-none transition-all text-[15px] shadow-sm bg-black/5 dark:bg-white/5"
                />
              </div>
            </div>

            <ContactList
              contacts={contacts}
              selectedId={selectedChatId}
              onSelect={(id) => navigate(`/messenger/${id}`)}
            />
          </motion.div>
        )}

        {/* Chat Area */}
        {showChat && (
          <motion.div
            key="chat-area"
            initial={isMobile ? { x: 300, opacity: 0 } : undefined}
            animate={{ x: 0, opacity: 1 }}
            exit={isMobile ? { x: 300, opacity: 0 } : undefined}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
            className="flex-1 flex flex-col overflow-hidden h-full relative z-10"
            style={{ background: "var(--msg-chat-bg)" }}
          >
            {selectedChatId && activeChat ? (
              <>
                <AnimatePresence mode="wait">
                  {!showSearchInChat ? (
                    <motion.div
                      key="header-normal"
                      initial={{ y: -20, opacity: 0 }}
                      animate={{ y: 0, opacity: 1 }}
                      exit={{ y: -20, opacity: 0 }}
                      className="msg-header shrink-0 h-16 flex items-center px-4 justify-between z-10"
                    >
                      <div className="flex items-center gap-3">
                        {isMobile && (
                          <motion.button
                            whileTap={{ scale: 0.9 }}
                            onClick={() => navigate("/messenger")}
                            className="p-1.5 -ml-1 rounded-full hover:bg-gray-100/50 dark:hover:bg-gray-800/50 transition-colors"
                          >
                            <svg
                              xmlns="http://www.w3.org/2000/svg"
                              fill="none"
                              viewBox="0 0 24 24"
                              strokeWidth={2.5}
                              stroke="currentColor"
                              className="w-5 h-5"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M15.75 19.5L8.25 12l7.5-7.5"
                              />
                            </svg>
                          </motion.button>
                        )}
                        <motion.button
                          whileHover={{ scale: 1.02 }}
                          whileTap={{ scale: 0.98 }}
                          className="flex items-center gap-3 cursor-pointer outline-none border-none bg-transparent text-left"
                          onClick={() => handleViewProfile()}
                        >
                          <div className="relative">
                            <SmartImage
                              srcRaw={
                                getOtherParticipant(activeChat)?.avatar_url ||
                                AVATAR_PLACEHOLDER_URL
                              }
                              fallback={AVATAR_PLACEHOLDER_URL}
                              alt={getOtherParticipant(activeChat)?.full_name || ""}
                              className="w-11 h-11 rounded-full object-cover border-2 border-white/10"
                            />
                            {presenceMap[getOtherParticipant(activeChat)?.id ?? ""]?.active && (
                              <span className="msg-online-indicator absolute bottom-0 right-0 w-3.5 h-3.5"></span>
                            )}
                          </div>
                          <div>
                            <h2 className="font-bold text-[16px] leading-tight sf-pro">
                              {getOtherParticipant(activeChat)?.full_name}
                            </h2>
                            <AnimatePresence mode="wait">
                              {presenceMap[getOtherParticipant(activeChat)?.id ?? ""]?.active ? (
                                <motion.p
                                  key="online"
                                  initial={{ opacity: 0, y: 5 }}
                                  animate={{ opacity: 1, y: 0 }}
                                  exit={{ opacity: 0, y: -5 }}
                                  className="text-[11px] font-semibold uppercase tracking-wider"
                                  style={{ color: "var(--msg-online-color)" }}
                                >
                                  {t("messenger:online", "online")}
                                </motion.p>
                              ) : (
                                <motion.p
                                  key="offline"
                                  initial={{ opacity: 0, y: 5 }}
                                  animate={{ opacity: 1, y: 0 }}
                                  exit={{ opacity: 0, y: -5 }}
                                  className="text-[11px] text-gray-500 font-medium"
                                >
                                  {t("messenger:offline", "offline")}
                                </motion.p>
                              )}
                            </AnimatePresence>
                          </div>
                        </motion.button>
                      </div>

                      <div className="flex items-center gap-1.5">
                        <motion.button
                          whileHover={{ scale: 1.05 }}
                          whileTap={{ scale: 0.95 }}
                          onClick={() => setShowSearchInChat(true)}
                          className="p-2.5 rounded-full hover:bg-gray-100/50 dark:hover:bg-gray-800/50 transition-colors"
                        >
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            fill="none"
                            viewBox="0 0 24 24"
                            strokeWidth={2}
                            stroke="currentColor"
                            className="w-5 h-5 text-gray-600 dark:text-gray-300"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
                            />
                          </svg>
                        </motion.button>
                        <div className="relative">
                          <motion.button
                            whileHover={{ scale: 1.05 }}
                            whileTap={{ scale: 0.95 }}
                            onClick={() => setShowChatMenu(!showChatMenu)}
                            className={`p-2.5 rounded-full transition-colors ${showChatMenu ? "bg-gray-100 dark:bg-gray-800" : "hover:bg-gray-100/50 dark:hover:bg-gray-800/50"}`}
                          >
                            <svg
                              xmlns="http://www.w3.org/2000/svg"
                              fill="none"
                              viewBox="0 0 24 24"
                              strokeWidth={2}
                              stroke="currentColor"
                              className="w-5 h-5 text-gray-600 dark:text-gray-300"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M12 6.75a.75.75 0 110-1.5.75.75 0 010 1.5zM12 12.75a.75.75 0 110-1.5.75.75 0 010 1.5zM12 18.75a.75.75 0 110-1.5.75.75 0 010 1.5z"
                              />
                            </svg>
                          </motion.button>
                          <AnimatePresence>
                            {showChatMenu && (
                              <motion.div
                                initial={{ opacity: 0, scale: 0.9, y: 10, x: 5 }}
                                animate={{ opacity: 1, scale: 1, y: 0, x: 0 }}
                                exit={{ opacity: 0, scale: 0.9, y: 10 }}
                                className="absolute right-0 top-full mt-2 bg-white/90 dark:bg-gray-900/90 backdrop-blur-xl rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-800 py-2 min-w-[220px] z-20 overflow-hidden"
                              >
                                {[
                                  {
                                    icon: "M17.982 18.725A7.488 7.488 0 0012 15.75a7.488 7.488 0 00-5.982 2.975m11.963 0a9 9 0 10-11.963 0m11.963 0A8.966 8.966 0 0112 21a8.966 8.966 0 01-5.982-2.275M15 9.75a3 3 0 11-6 0 3 3 0 016 0z",
                                    label: t("messenger:viewProfile"),
                                    color: "text-blue-500",
                                    action: handleViewProfile,
                                  },
                                  {
                                    icon: "M12 9.75v6.75m0 0l-3-3m3 3l3-3m-8.25 6a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z",
                                    label: t("messenger:clearChat"),
                                    color: "text-yellow-500",
                                    action: handleClearChat,
                                  },
                                  {
                                    icon: "M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0",
                                    label: t("messenger:deleteChat"),
                                    color: "text-red-500",
                                    action: handleDeleteChat,
                                  },
                                ].map((item, idx) => (
                                  <button
                                    key={idx}
                                    onClick={item.action}
                                    className="w-full px-4 py-2.5 text-left hover:bg-gray-100 dark:hover:bg-gray-800 flex items-center gap-3 text-gray-700 dark:text-gray-200 transition-colors"
                                  >
                                    <svg
                                      xmlns="http://www.w3.org/2000/svg"
                                      fill="none"
                                      viewBox="0 0 24 24"
                                      strokeWidth={1.5}
                                      stroke="currentColor"
                                      className={`w-5 h-5 ${item.color}`}
                                    >
                                      <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        d={item.icon}
                                      />
                                    </svg>
                                    <span className="text-sm font-medium">{item.label}</span>
                                  </button>
                                ))}
                              </motion.div>
                            )}
                          </AnimatePresence>
                        </div>
                      </div>
                    </motion.div>
                  ) : (
                    <motion.div
                      key="header-search"
                      initial={{ y: -20, opacity: 0 }}
                      animate={{ y: 0, opacity: 1 }}
                      exit={{ y: -20, opacity: 0 }}
                      className="shrink-0 h-16 border-b border-gray-200 dark:border-gray-800 flex items-center px-4 bg-white/90 dark:bg-[#0b111e]/90 backdrop-blur-xl z-20"
                    >
                      <motion.button
                        whileTap={{ scale: 0.9 }}
                        onClick={() => {
                          setShowSearchInChat(false)
                          setSearchQuery("")
                        }}
                        className="p-1.5 mr-3 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                      >
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          fill="none"
                          viewBox="0 0 24 24"
                          strokeWidth={2}
                          stroke="currentColor"
                          className="w-6 h-6"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M6 18L18 6M6 6l12 12"
                          />
                        </svg>
                      </motion.button>
                      <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder={t("messenger:searchMessages", "Search messages...")}
                        className="flex-1 px-4 py-2.5 rounded-2xl bg-black/5 dark:bg-white/5 border-none focus:ring-2 focus:ring-blue-500/50 outline-none transition-all text-[15px]"
                        autoFocus
                      />
                    </motion.div>
                  )}
                </AnimatePresence>

                <ChatWindow messages={optimisticMessages} />
                <MessageInput onSend={handleSendMessage} />
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-gray-50/30 dark:bg-black/30">
                <motion.div
                  initial={{ scale: 0.8, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  whileHover={{ rotate: 5, scale: 1.1 }}
                  className="w-32 h-32 rounded-[2.5rem] flex items-center justify-center mb-8 shadow-2xl"
                  style={{
                    background:
                      "linear-gradient(135deg, var(--msg-sidebar-hover), var(--msg-header-bg))",
                    border: "1px solid var(--msg-header-border)",
                  }}
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={1}
                    stroke="currentColor"
                    className="w-16 h-16"
                    style={{ color: "var(--msg-sidebar-active)", opacity: 0.6 }}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M8.625 9.75a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375m-13.5 3.01c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.184-4.183a1.14 1.14 0 01.778-.332 48.294 48.294 0 005.83-.498c1.585-.233 2.708-1.626 2.708-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z"
                    />
                  </svg>
                </motion.div>
                <h3 className="text-xl font-bold text-gray-800 dark:text-gray-200 sf-pro">
                  {t("messenger:selectChat", "Choose a conversation")}
                </h3>
                <p className="mt-2 text-gray-500 max-w-xs">
                  {t(
                    "messenger:selectChatDesc",
                    "Connect with anyone across the university ecosystem."
                  )}
                </p>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <NewChatModal
        open={isNewChatModalOpen}
        onClose={() => setIsNewChatModalOpen(false)}
        onSelect={(userId) => createChatMutation.mutate(userId)}
      />

      {(profileUser || isProfileLoading || profileError) && (
        <AnimatePresence>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-md flex items-center justify-center z-[3000] p-4"
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.9, y: 20 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.9, opacity: 0, y: 20 }}
              className="bg-white dark:bg-[#0f172a] rounded-4xl shadow-2xl w-full max-w-lg overflow-hidden border border-white/10 z-4000"
            >
              <div
                className="p-6 pb-4 flex items-center justify-between"
                style={{ borderBottom: "1px solid var(--msg-header-border)" }}
              >
                <h3 className="text-xl font-bold tracking-tight sf-pro">
                  {profileUser?.full_name || t("messenger:profile", "Profile")}
                </h3>
                <motion.button
                  whileHover={{ rotate: 90, scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  onClick={() => {
                    setProfileUser(null)
                    setIsProfileLoading(false)
                    setProfileError(null)
                  }}
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

              <div className="p-8">
                {isProfileLoading && (
                  <div className="flex flex-col items-center py-8">
                    <div className="w-12 h-12 border-4 border-blue-500/20 border-t-blue-500 rounded-full animate-spin"></div>
                    <p className="mt-4 text-sm font-medium text-gray-500">
                      {t("messenger:loadingProfile", "Loading profile...")}
                    </p>
                  </div>
                )}

                {profileError && (
                  <div className="p-4 bg-red-500/10 rounded-xl text-center">
                    <p className="text-sm font-semibold text-red-600 dark:text-red-400">
                      {profileError}
                    </p>
                  </div>
                )}

                {profileUser && (
                  <div className="space-y-6">
                    <div className="flex flex-col items-center text-center">
                      <div className="relative mb-4">
                        <SmartImage
                          srcRaw={profileUser.avatar_url || AVATAR_PLACEHOLDER_URL}
                          fallback={AVATAR_PLACEHOLDER_URL}
                          alt={profileUser.full_name ?? ""}
                          className="w-24 h-24 rounded-[2rem] object-cover border-4 border-white dark:border-gray-800 shadow-xl"
                        />
                        {profileUser.is_active && (
                          <span className="msg-online-indicator absolute -bottom-1 -right-1 w-6 h-6 border-4 border-white dark:border-gray-800"></span>
                        )}
                      </div>
                      <h4 className="text-2xl font-bold tracking-tight sf-pro">
                        {profileUser.full_name}
                      </h4>
                      <p className="text-gray-500 dark:text-gray-400 font-medium">
                        {profileUser.email}
                      </p>
                    </div>

                    <div className="grid grid-cols-2 gap-3 pb-2">
                      <div className="p-4 rounded-2xl bg-gray-50 dark:bg-white/5 border border-black/5 dark:border-white/5">
                        <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-1">
                          {t("messenger:status", "Status")}
                        </p>
                        <p className="text-sm font-bold flex items-center gap-1.5">
                          {profileUser.is_active ? (
                            <>
                              <span className="w-2 h-2 rounded-full bg-green-500"></span>
                              {t("common:active", "Active")}
                            </>
                          ) : (
                            <>
                              <span className="w-2 h-2 rounded-full bg-gray-400"></span>
                              {t("common:inactive", "Inactive")}
                            </>
                          )}
                        </p>
                      </div>
                      {profileUser.avatar_url && (
                        <a
                          href={profileUser.avatar_url}
                          target="_blank"
                          rel="noreferrer"
                          className="p-4 rounded-2xl bg-blue-500/5 border border-blue-500/10 hover:bg-blue-500/10 transition-colors"
                        >
                          <p className="text-[10px] font-bold uppercase tracking-widest text-blue-500 mb-1">
                            {t("messenger:avatar", "Avatar")}
                          </p>
                          <p className="text-sm font-bold text-blue-600 dark:text-blue-400">
                            {t("messenger:viewAvatar", "Open full size")}
                          </p>
                        </a>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>
        </AnimatePresence>
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
