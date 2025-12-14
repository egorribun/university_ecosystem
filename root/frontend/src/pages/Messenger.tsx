import { useState, useEffect } from "react"
import { useTranslation } from "react-i18next"
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

export default function Messenger() {
  const { t } = useTranslation(["messenger", "common"])
  const { user } = useAuth()
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

  // Fetch Chats with paginated response
  const { data: chatsData, isLoading: chatsLoading } = useQuery({
    queryKey: ["chats"],
    queryFn: () => chatApi.getChats(),
  })
  const chats = chatsData?.items ?? []

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

  // Mark messages as read when opening a chat
  useEffect(() => {
    if (selectedChatId) {
      markReadMutation.mutate(selectedChatId)
    }
  }, [selectedChatId])

  const activeChat = chats.find((c) => c.id === selectedChatId)

  // Helper to get the other participant
  const getOtherParticipant = (chat: Chat) => {
    return chat.participants.find((p) => p.id !== user?.id)
  }

  const handleSendMessage = (text: string, files: File[]) => {
    console.log("Messenger handleSendMessage:", {
      chatId: selectedChatId,
      text,
      filesCount: files.length,
    })
    if (!selectedChatId) return
    sendMessageMutation.mutate({ chatId: selectedChatId, content: text, files })
  }

  const handleClearChat = () => {
    if (!selectedChatId) return
    const confirmed = window.confirm(
      t("messenger:confirmClear", "Clear chat history for everyone?")
    )
    if (!confirmed) return
    clearChatMutation.mutate(selectedChatId)
  }

  const handleDeleteChat = () => {
    if (!selectedChatId) return
    const confirmed = window.confirm(
      t("messenger:confirmDelete", "Delete this chat for all participants?")
    )
    if (!confirmed) return
    deleteChatMutation.mutate(selectedChatId)
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
      lastMessageTime: chat.last_message
        ? new Date(chat.last_message.created_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })
        : "",
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
      className="flex overflow-hidden bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 font-sans"
      style={{
        height: isBottomNavVisible ? "calc(100vh - 64px - var(--bn-h))" : "calc(100vh - 64px)",
      }}
    >
      {/* Sidebar */}
      <div
        className={`${
          showList ? "flex" : "hidden"
        } w-full md:w-80 lg:w-96 flex-col border-r border-gray-200 dark:border-gray-800 bg-white dark:bg-[#0b111e] transition-all duration-300`}
      >
        <div className="p-4 border-b border-gray-200 dark:border-gray-800 flex justify-between items-center sticky top-0 bg-white/80 dark:bg-[#0b111e]/80 backdrop-blur-md z-10">
          <h1 className="text-xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
            {t("messenger:title", "Messages")}
          </h1>
          <button
            onClick={() => setIsNewChatModalOpen(true)}
            className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="w-6 h-6 text-gray-600 dark:text-gray-300"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10"
              />
            </svg>
          </button>
        </div>

        <div className="p-3">
          <input
            type="text"
            placeholder={t("messenger:search", "Search messages...")}
            className="w-full px-4 py-2 rounded-xl bg-gray-100 dark:bg-gray-800 border-none focus:ring-2 focus:ring-blue-500 outline-none transition-all text-sm"
          />
        </div>

        <ContactList
          contacts={contacts}
          selectedId={selectedChatId}
          onSelect={(id) => setSelectedChatId(id)}
        />
      </div>

      {/* Chat Area */}
      <div
        className={`${
          showChat ? "flex" : "hidden"
        } flex-1 flex flex-col bg-white/50 dark:bg-[#060b14] overflow-hidden`}
      >
        {selectedChatId && activeChat ? (
          <>
            {/* Chat Header - Fixed */}
            {!showSearchInChat ? (
              <div className="flex-shrink-0 h-16 border-b border-gray-200 dark:border-gray-800 flex items-center px-4 justify-between bg-white/80 dark:bg-[#0b111e]/80 backdrop-blur-md z-10">
                <div className="flex items-center gap-3">
                  {isMobile && (
                    <button
                      onClick={() => setSelectedChatId(null)}
                      className="p-1 -ml-2 mr-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800"
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
                          d="M15.75 19.5L8.25 12l7.5-7.5"
                        />
                      </svg>
                    </button>
                  )}
                  <SmartImage
                    srcRaw={getOtherParticipant(activeChat)?.avatar_url || AVATAR_PLACEHOLDER_URL}
                    fallback={AVATAR_PLACEHOLDER_URL}
                    alt={getOtherParticipant(activeChat)?.full_name || ""}
                    className="w-10 h-10 rounded-full object-cover border border-gray-200 dark:border-gray-700"
                  />
                  <h2 className="font-semibold text-base leading-tight">
                    {getOtherParticipant(activeChat)?.full_name}
                  </h2>
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
                          <span className="text-sm">View Profile</span>
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
                          <span className="text-sm">Clear Chat</span>
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
                          <span className="text-sm">Delete Chat</span>
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

            <ChatWindow
              messages={messages.map((m) => ({
                id: m.id,
                senderId: String(m.sender_id),
                text: m.content,
                timestamp: new Date(m.created_at).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                }),
                isMe: m.sender_id === user?.id,
                status: m.read_status ? "read" : "sent",
                attachments: m.attachments?.map((a) => ({
                  id: a.id,
                  url: a.url,
                  type: a.file_type,
                  name: a.filename,
                  size: a.size,
                })),
              }))}
            />
            <MessageInput onSend={handleSendMessage} />
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-400 p-8 text-center">
            <div className="w-24 h-24 bg-gray-100 dark:bg-gray-800 rounded-full flex items-center justify-center mb-4">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                className="w-12 h-12 text-gray-400"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M8.625 9.75a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375m-13.5 3.01c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.184-4.183a1.14 1.14 0 01.778-.332 48.294 48.294 0 005.83-.498c1.585-.233 2.708-1.626 2.708-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z"
                />
              </svg>
            </div>
            <h3 className="text-lg font-medium text-gray-600 dark:text-gray-300">
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
    </div>
  )
}
