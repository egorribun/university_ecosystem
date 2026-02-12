import { useState, useEffect, useCallback, useMemo, useOptimistic } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import { useAuth } from "../../contexts/AuthContext"
import { useMessenger } from "../../contexts/MessengerContext"
import {
  chatApi,
  type Chat,
  type ChatMaintenanceResult,
  type ChatsListResponse,
  type MessagesListResponse,
} from "../../api/chat"
import client from "../../api/client"
import type { User } from "../../types/User"
import type { Message as UiMessage } from "../../components/messenger/MessengerComponents"

dayjs.extend(utc)

const formatMessageTime = (dateString: string) => {
  if (!dateString) return ""
  const cleanDate = dateString.replace(/(\.\d+)(Z|[+-]\d{2}:?\d{2})?$/, "$2")
  const parsed = dayjs.utc(cleanDate)
  return parsed.local().format("HH:mm")
}

export const useMessengerController = () => {
  const { t } = useTranslation(["messenger", "common"])
  const { user } = useAuth()
  const { chatId } = useParams<{ chatId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { presenceMap } = useMessenger()

  // UI State
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null)
  const [isNewChatModalOpen, setIsNewChatModalOpen] = useState(false)
  const [showSearchInChat, setShowSearchInChat] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [showChatMenu, setShowChatMenu] = useState(false)

  // Profile State
  const [profileUser, setProfileUser] = useState<User | null>(null)
  const [isProfileLoading, setIsProfileLoading] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)

  // Dialog State
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean
    title: string
    message: string
    variant: "danger" | "warning" | "default"
    confirmText?: string
    cancelText?: string
    onConfirm: () => void
  } | null>(null)

  // Sync selection with URL
  useEffect(() => {
    setSelectedChatId(chatId || null)
  }, [chatId])

  // --- Queries ---

  const { data: chatsData, isLoading: chatsLoading } = useQuery({
    queryKey: ["chats"],
    queryFn: () => chatApi.getChats(),
  })
  const chats = chatsData?.items ?? []

  const { data: singleChatData } = useQuery({
    queryKey: ["chats", chatId],
    queryFn: () => (chatId ? chatApi.getChat(chatId) : Promise.reject("No chatId")),
    enabled: !!chatId && !chats.some((c) => c.id === chatId),
    retry: false,
  })

  const { data: messagesData, isLoading: messagesLoading } = useQuery({
    queryKey: ["messages", selectedChatId],
    queryFn: () =>
      selectedChatId
        ? chatApi.getMessages(selectedChatId)
        : Promise.resolve({ items: [], has_more: false, next_cursor: null }),
    enabled: !!selectedChatId,
  })
  const messages = messagesData?.items ?? []

  // --- Computed ---

  const activeChat = useMemo(() => {
    if (!selectedChatId) return null
    const inList = chats.find((c) => c.id === selectedChatId)
    if (inList) return inList
    if (singleChatData && singleChatData.id === selectedChatId) return singleChatData
    return null
  }, [selectedChatId, chats, singleChatData])

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

  // --- Optimistic UI ---

  const [optimisticMessages, addOptimisticMessage] = useOptimistic(
    transformedMessages,
    (state: UiMessage[], newMessage: UiMessage) => [...state, newMessage]
  )

  // --- Mutations ---

  const sendMessageMutation = useMutation({
    mutationFn: ({ chatId, content, files }: { chatId: string; content: string; files?: File[] }) =>
      chatApi.sendMessage(chatId, content, files),
    onSuccess: (newMessage) => {
      queryClient.setQueryData<MessagesListResponse | undefined>(
        ["messages", selectedChatId],
        (old) => {
          const items = old?.items ?? []
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

  const markReadMutation = useMutation({
    mutationFn: (chatId: string) => chatApi.markRead(chatId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chats"] })
    },
  })

  const createChatMutation = useMutation({
    mutationFn: (participantId: string) => chatApi.createChat(participantId),
    onSuccess: (newChat) => {
      queryClient.invalidateQueries({ queryKey: ["chats"] })
      navigate(`/messenger/${newChat.id}`)
      setIsNewChatModalOpen(false)
    },
  })

  // Complex mutations with cache manipulation

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
        navigate("/messenger")
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

  // --- Handlers ---

  const markAsRead = useCallback((chatId: string) => {
    markReadMutation.mutate(chatId)
  }, [])

  useEffect(() => {
    if (selectedChatId) {
      markAsRead(selectedChatId)
    }
  }, [selectedChatId, markAsRead])

  const handleSendMessage = (text: string, files: File[]) => {
    if (!selectedChatId) return

    const tempId = crypto.randomUUID()
    const now = new Date()

    // UI-only message for optimistic update
    const optimisticMsg: UiMessage = {
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
        url: URL.createObjectURL(f),
        type: f.type.startsWith("image/") ? "image" : "file",
        name: f.name,
        size: f.size,
      })),
    }

    addOptimisticMessage(optimisticMsg)
    sendMessageMutation.mutate({ chatId: selectedChatId, content: text, files })
  }

  const getOtherParticipant = useCallback(
    (chat: Chat) => {
      return chat.participants.find((p) => p.id !== user?.id)
    },
    [user?.id]
  )

  const handleCreateChat = (participantId: string) => {
    createChatMutation.mutate(participantId)
  }

  const handleClearChat = () => {
    if (!selectedChatId) return
    setConfirmDialog({
      open: true,
      title: t("messenger:clearChatTitle", "Clear Chat"),
      message: t("messenger:confirmClear", "Clear chat history for everyone?"),
      variant: "warning",
      confirmText: t("common:clear", "Clear"),
      cancelText: t("common:cancel", "Cancel"),
      onConfirm: () => {
        clearChatMutation.mutate(selectedChatId)
        setConfirmDialog(null)
      },
    })
  }

  const handleDeleteChat = () => {
    if (!selectedChatId) return
    setConfirmDialog({
      open: true,
      title: t("messenger:deleteChatTitle", "Delete Chat"),
      message: t("messenger:confirmDelete", "Delete this chat for all participants?"),
      variant: "danger",
      confirmText: t("common:delete", "Delete"),
      cancelText: t("common:cancel", "Cancel"),
      onConfirm: () => {
        deleteChatMutation.mutate(selectedChatId)
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

  const handleCloseProfile = () => {
    setProfileUser(null)
    setIsProfileLoading(false)
    setProfileError(null)
  }

  // Derived Data
  const contacts = useMemo(
    () =>
      chats.map((chat) => {
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
      }),
    [chats, getOtherParticipant, presenceMap]
  )

  return {
    // State
    selectedChatId,
    activeChat,
    isNewChatModalOpen,
    setIsNewChatModalOpen,
    showSearchInChat,
    setShowSearchInChat,
    searchQuery,
    setSearchQuery,
    showChatMenu,
    setShowChatMenu,

    // Data
    contacts,
    messages: optimisticMessages,
    chatsLoading,
    messagesLoading,

    // Profile
    profileUser,
    setProfileUser,
    isProfileLoading,
    profileError,
    handleViewProfile,
    handleCloseProfile,
    getOtherParticipant,
    presenceMap,

    // Dialogs
    confirmDialog,
    setConfirmDialog,

    // Actions
    handleSendMessage,
    handleCreateChat,
    handleClearChat,
    handleDeleteChat,
  }
}
