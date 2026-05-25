import { useState, useEffect, useCallback, useMemo, useOptimistic, useRef } from "react"
import { useNavigate, useParams } from "@tanstack/react-router"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { formatDate, presets } from "@/utils/date"
import { useAuth } from "@/contexts/AuthContext"
import { useMessenger } from "@/contexts/MessengerContext"
import {
  chatApi,
  type Chat,
  type ChatMaintenanceResult,
  type ChatsListResponse,
  type MessagesListResponse,
} from "@/api/chat"
// Wave 180 SW3 — extracted queryOptions factories close W134 §Honesty #10
// (W161 SW2 concern #1: query gate inconsistency). See api/hooks/messenger.ts
// header docblock for the full rationale.
import { chatsQueryOptions, chatQueryOptions, messagesQueryOptions } from "@/api/hooks/messenger"
import client from "@/api/client"
import type { User } from "@/types/User"
import type { Message as UiMessage } from "@/components/messenger"

// dayjs.extend(utc) removed in favor of native Intl utility

const formatMessageTime = (dateString: string) => {
  if (!dateString) return ""
  return formatDate(dateString, presets.chatTime)
}

export const useMessengerController = () => {
  const { t } = useTranslation(["messenger", "common"])
  const { user } = useAuth()
  // W145 SW2 — `as` cast removed; TanStack v1 `useParams({ strict: false })`
  // returns the union of all route params, so destructured `chatId` is
  // `string | undefined` natively. Matches NewsDetail.tsx + EventDetail.tsx +
  // ResetPassword.tsx codebase convention (4 callsites; all use strict:false).
  const { chatId } = useParams({ strict: false })
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

  // Wave 183 SW3 — track Blob URLs created by optimistic message attachments
  // so they can be revoked on cleanup (component unmount) AND on mutation
  // success (when the optimistic message is replaced by the server-returned
  // message with real URLs). Pre-W183 `URL.createObjectURL(f)` in handleSendMessage
  // was called per attached file but never revoked, leaking memory across
  // long messenger sessions (each attached image = ~10-100 KB in the URL
  // table, accumulating until tab close).
  const blobUrlsRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    // Snapshot the ref to a local variable so the cleanup closure references
    // the SAME Set instance even if React's StrictMode double-invokes (or if
    // the ref is reassigned in a future refactor). Per react-hooks/exhaustive-deps
    // ESLint rule recommendation.
    const blobUrls = blobUrlsRef.current
    return () => {
      // Revoke all outstanding Blob URLs on unmount to release native resources.
      blobUrls.forEach((url) => URL.revokeObjectURL(url))
      blobUrls.clear()
    }
  }, [])

  // Sync selection with URL
  useEffect(() => {
    setSelectedChatId(chatId || null)
  }, [chatId])

  // --- Queries ---

  // Wave 180 SW3 — chat list useQuery spreads chatsQueryOptions() factory +
  // adds `enabled: !!user` gate. Closes W161 SW2 concern #1 (query gate
  // inconsistency): pre-W180 this fired without the `enabled: isAuth` gate
  // that MessengerContext.tsx:66-70 already had. Cache identity preserved
  // via chatsQueryKey = ["chats"] (unchanged tuple shape).
  // Wave 184 SW3 (Path B) — additionally surface `isError` + `refetch` so
  // ContactList can render a fetch-failure error state with retry button.
  // Pre-W184 fetch failures resulted in the empty-state "No conversations
  // yet" branch flashing wrongly — the user had no way to distinguish
  // "no chats" from "network error".
  const {
    data: chatsData,
    isLoading: chatsLoading,
    isError: chatsError,
    refetch: refetchChats,
  } = useQuery({
    ...chatsQueryOptions(),
    enabled: !!user,
  })
  const chats = useMemo(() => chatsData?.items ?? [], [chatsData?.items])

  // Wave 180 SW3 — single-chat fallback useQuery (fires when chat is NOT in
  // the cached list yet, e.g. direct URL navigation). Spreads chatQueryOptions
  // factory + preserves pre-W180 `enabled` gate (chatId present AND not already
  // in list) + `retry: false` override (chat-not-found should surface quickly
  // without exponential backoff, matching pre-W180 line 78 behaviour).
  const { data: singleChatData } = useQuery({
    ...chatQueryOptions(chatId),
    enabled: !!chatId && !chats.some((c) => c.id === chatId),
    retry: false,
  })

  // Wave 180 SW3 — messages useQuery spreads messagesQueryOptions factory.
  // Pre-W180 `enabled: !!selectedChatId` gate preserved (no other changes).
  // Wave 184 SW3 (Path B) — additionally surface `isError` + `refetch` for
  // ChatWindow fetch-failure error state. Same rationale as chats (above).
  const {
    data: messagesData,
    isLoading: messagesLoading,
    isError: messagesError,
    refetch: refetchMessages,
  } = useQuery({
    ...messagesQueryOptions(selectedChatId),
    enabled: !!selectedChatId,
  })
  const messages = useMemo(() => messagesData?.items ?? [], [messagesData?.items])

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
      // Wave 183 SW3 — revoke Blob URLs created by the optimistic message
      // now that the server-returned message with real URLs has replaced it.
      // Pre-W183 these URLs leaked until tab close.
      blobUrlsRef.current.forEach((url) => URL.revokeObjectURL(url))
      blobUrlsRef.current.clear()
    },
    onError: () => {
      // Wave 183 SW3 — revoke Blob URLs on send failure too. The optimistic
      // message may be retained by the user (e.g., retry pending) but the
      // Blob URLs become orphaned because React will re-render the
      // optimistic state from scratch on next attempt.
      blobUrlsRef.current.forEach((url) => URL.revokeObjectURL(url))
      blobUrlsRef.current.clear()
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
      navigate({ to: "/messenger/$chatId", params: { chatId: newChat.id } })
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
    onSettled: (_data, _error, chatId) => {
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
        navigate({ to: "/messenger" })
      }

      return { previousChats }
    },
    onError: (_error, _chatId, context) => {
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

  const markAsRead = useCallback(
    (chatId: string) => {
      markReadMutation.mutate(chatId)
    },
    [markReadMutation]
  )

  useEffect(() => {
    if (selectedChatId) {
      markAsRead(selectedChatId)
    }
  }, [selectedChatId, markAsRead])

  const handleSendMessage = (text: string, files: File[]) => {
    if (!selectedChatId) return

    const tempId = crypto.randomUUID()
    const now = new Date()

    // Wave 183 SW3 — track Blob URLs created here so the mutation onSuccess/
    // onError handlers can revoke them (preventing memory leak per-attachment).
    // UI-only message for optimistic update.
    const optimisticMsg: UiMessage = {
      id: tempId,
      senderId: String(user?.id),
      senderName: user?.full_name ?? undefined,
      senderAvatar: user?.avatar_url || "",
      text,
      timestamp: formatMessageTime(now.toISOString()),
      isMe: true,
      status: "sent",
      attachments: files.map((f, i) => {
        const blobUrl = URL.createObjectURL(f)
        blobUrlsRef.current.add(blobUrl)
        return {
          id: `${tempId}-${i}`,
          url: blobUrl,
          type: f.type.startsWith("image/") ? "image" : "file",
          name: f.name,
          size: f.size,
        }
      }),
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
      // Wave 183 SW3 — removed positional `t(key, fallback)` antipattern
      // (W175 SW7 + W150 SW3 + W182 SW2 baseline). All 5 keys verified
      // present in messenger.json EN + RU locales pre-W183 (clearChatTitle,
      // confirmClear, deleteChatTitle, confirmDelete, profileLoadError).
      title: t("messenger:clearChatTitle"),
      message: t("messenger:confirmClear"),
      variant: "warning",
      confirmText: t("common:buttons.clear"),
      cancelText: t("common:buttons.cancel"),
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
      title: t("messenger:deleteChatTitle"),
      message: t("messenger:confirmDelete"),
      variant: "danger",
      confirmText: t("common:buttons.delete"),
      cancelText: t("common:buttons.cancel"),
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
      .catch(() => setProfileError(t("messenger:profileLoadError")))
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
    // Wave 184 SW3 (Path B) — fetch-failure flags + refetch handles for
    // ContactList + ChatWindow error empty-state branches with retry CTA.
    chatsError,
    refetchChats,
    messagesError,
    refetchMessages,

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
