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
import { chatDisplayInfo } from "@/components/messenger/chatDisplay"
import type { User } from "@/types/User"
import type { Message as UiMessage, Contact } from "@/components/messenger"

// dayjs.extend(utc) removed in favor of native Intl utility

const formatMessageTime = (dateString: string) => {
  if (!dateString) return ""
  return formatDate(dateString, presets.chatTime)
}

// Wave 208 SW5 — group consecutive messages from the same sender within this
// window (ms) under one avatar (Telegram-style). A larger gap, a different
// sender, or a new calendar day starts a fresh group.
const GROUP_GAP_MS = 5 * 60 * 1000

// Wave 208 SW5 — same-calendar-day check (local time) for date dividers + group
// boundaries. Pure (no locale / t) so it stays a module-level helper.
const isSameCalendarDay = (a: Date, b: Date): boolean =>
  a.getFullYear() === b.getFullYear() &&
  a.getMonth() === b.getMonth() &&
  a.getDate() === b.getDate()

// Wave 206 — API reaction aggregate shape (snake_case, as carried on @/api/chat
// Message.reactions). The optimistic toggle below operates on this shape in the
// ["messages", chatId] cache; the transform maps it to the camelCase UI shape.
type ApiReaction = { emoji: string; count: number; reacted_by_me: boolean }

/**
 * Wave 206 — optimistic toggle of one emoji on a message's reaction aggregate.
 * Unlike applyReactionChangedFrame (which patches count only for a PEER's delta),
 * this is the ACTOR's optimistic patch, so it ALSO flips reacted_by_me. removing →
 * count-1 + reacted_by_me=false (drop at 0); adding → count+1 + reacted_by_me=true
 * (or push a fresh {count:1, reacted_by_me:true}). noUncheckedIndexedAccess-safe.
 */
const toggleReactionAggregate = (
  reactions: ApiReaction[] | undefined,
  emoji: string,
  currentlyReacted: boolean
): ApiReaction[] => {
  const next = [...(reactions ?? [])]
  const idx = next.findIndex((r) => r.emoji === emoji)
  const existing = next[idx] // idx === -1 → undefined (noUncheckedIndexedAccess)
  if (currentlyReacted) {
    if (existing) {
      const count = existing.count - 1
      if (count <= 0) next.splice(idx, 1)
      else next[idx] = { ...existing, count, reacted_by_me: false }
    }
  } else if (existing) {
    next[idx] = { ...existing, count: existing.count + 1, reacted_by_me: true }
  } else {
    next.push({ emoji, count: 1, reacted_by_me: true })
  }
  return next
}

export const useMessengerController = () => {
  const { t, i18n } = useTranslation(["messenger", "common"])
  const { user } = useAuth()
  // W145 SW2 — `as` cast removed; TanStack v1 `useParams({ strict: false })`
  // returns the union of all route params, so destructured `chatId` is
  // `string | undefined` natively. Matches NewsDetail.tsx + EventDetail.tsx +
  // ResetPassword.tsx codebase convention (4 callsites; all use strict:false).
  const { chatId } = useParams({ strict: false })
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { presenceMap, sendJoin, sendLeave, isConnected } = useMessenger()

  // UI State
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null)
  const [isNewChatModalOpen, setIsNewChatModalOpen] = useState(false)
  const [showSearchInChat, setShowSearchInChat] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [showChatMenu, setShowChatMenu] = useState(false)
  // Wave 205 SW6 — inline-edit state: which message is being edited + its draft.
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null)
  const [editingMessageContent, setEditingMessageContent] = useState("")

  // Wave 207 — reply/quote compose state. Set by handleStartReply when the user
  // taps "reply" on a bubble; the MessageInput chip renders it; the send handler
  // threads reply_to_message_id + builds the optimistic message's replyTo;
  // cleared on send + on cancel. `isMe` is the ORIGINAL (quoted) message's isMe —
  // copied into the optimistic replyTo so the "You" vs name label resolves
  // identically to a server-fetched reply.
  const [replyingTo, setReplyingTo] = useState<{
    id: string
    senderName: string | null
    isMe: boolean
    text: string
  } | null>(null)

  // Wave 211 — forward compose state. The id of the message being forwarded
  // (null = ForwardModal closed). Set by handleStartForward when the user taps
  // "forward" on a bubble; the ForwardModal destination picker renders while
  // non-null; cleared on cancel + on a successful forward.
  const [forwardSourceMessageId, setForwardSourceMessageId] = useState<string | null>(null)

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
  // Wave 211 G4 (SW10) — group info / member-management panel open state.
  const [showGroupInfo, setShowGroupInfo] = useState(false)

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
    // Wave 203 SW6 — find the LAST message the current user sent that has been
    // read, so only THAT one renders the "Seen · HH:MM" marker (Telegram 1-on-1
    // style). Survives a newer *unread* sent message: the marker stays on the
    // last *read* one. Single reverse scan (≤200 buffered messages).
    let lastReadId: string | null = null
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i]
      if (m && m.sender_id === user?.id && m.read_at) {
        lastReadId = m.id
        break
      }
    }
    const now = new Date()
    const yesterdayStart = new Date(now)
    yesterdayStart.setDate(yesterdayStart.getDate() - 1)
    return messages.map((m, i) => {
      const isMe = m.sender_id === user?.id
      // Wave 208 SW5 — date dividers + sender grouping. `prev` is the previous
      // message in chronological (ascending) order. A new calendar day shows a
      // divider AND always starts a new group (the avatar reappears); a different
      // sender or a > GROUP_GAP_MS gap also starts a new group. The absolute-date
      // label MUST pass i18n.language (formatMessageTime above is locale-less →
      // always en-US; the divider must localize). `now`/`yesterdayStart` are
      // current-time snapshots computed once per memo run — intentionally NOT in
      // the dep array (they'd defeat memoization; the relative labels refresh on
      // the next message/auth/language change, which is sufficient).
      const prev = i > 0 ? messages[i - 1] : undefined
      const createdAt = new Date(m.created_at)
      const showDateDivider = !prev || !isSameCalendarDay(createdAt, new Date(prev.created_at))
      let dateLabel: string | undefined
      if (showDateDivider) {
        if (isSameCalendarDay(createdAt, now)) {
          dateLabel = t("messenger:dateDivider.today")
        } else if (isSameCalendarDay(createdAt, yesterdayStart)) {
          dateLabel = t("messenger:dateDivider.yesterday")
        } else {
          dateLabel = formatDate(m.created_at, presets.chatGroup, i18n.language)
        }
      }
      const isGroupStart =
        !prev ||
        showDateDivider ||
        prev.sender_id !== m.sender_id ||
        createdAt.getTime() - new Date(prev.created_at).getTime() > GROUP_GAP_MS

      let seenByCount: number | undefined
      let seenByTotal: number | undefined
      if (activeChat?.chat_type === "group" && isMe) {
        const others = activeChat.participants.filter((p) => p.id !== user?.id)
        seenByTotal = others.length
        seenByCount = others.filter((p) => {
          const receipt = activeChat.read_receipts?.find((r) => r.user_id === p.id)
          if (!receipt) return false
          return new Date(receipt.last_read_at).getTime() >= new Date(m.created_at).getTime()
        }).length
      }

      return {
        id: m.id,
        senderId: String(m.sender_id),
        senderName: isMe ? (user?.full_name ?? "Me") : (m.sender?.full_name ?? "User"),
        senderAvatar: isMe ? user?.avatar_url || "" : m.sender?.avatar_url || "",
        text: m.content,
        timestamp: formatMessageTime(m.created_at),
        isMe,
        status: (m.read_status ? "read" : "sent") as "read" | "sent",
        readAt: m.read_at ?? null,
        readAtLabel: m.read_at ? formatMessageTime(m.read_at) : undefined,
        isLastRead: m.id === lastReadId,
        seenByCount,
        seenByTotal,
        // Wave 205 SW6 — edit/soft-delete UI fields. editedAtLabel feeds the
        // "(edited)" tooltip; deletedAt set => ChatWindow renders the tombstone.
        editedAt: m.edited_at ?? null,
        editedAtLabel: m.edited_at ? formatMessageTime(m.edited_at) : undefined,
        deletedAt: m.deleted_at ?? null,
        attachments: m.attachments?.map((a) => ({
          id: a.id,
          url: a.url,
          type: a.file_type,
          name: a.filename,
          size: a.size,
        })),
        // Wave 206 — map API reaction aggregates (snake_case) → UI shape
        // (camelCase reactedByMe). Server-computed reacted_by_me on GET /messages;
        // the optimistic toggle + WS delta keep it live thereafter.
        reactions: m.reactions?.map((r) => ({
          emoji: r.emoji,
          count: r.count,
          reactedByMe: r.reacted_by_me,
        })),
        // Wave 207 — map the API reply preview (snake_case) → UI shape. isMe is
        // resolved HERE (reply_to.sender_id === user.id) so ChatWindow renders the
        // "You" vs name author label without a currentUserId prop. null when not a
        // reply (or the target was hard-deleted → SET NULL nulled the ref).
        replyTo: m.reply_to
          ? {
              id: m.reply_to.id,
              senderName: m.reply_to.sender_name,
              isMe: m.reply_to.sender_id === user?.id,
              text: m.reply_to.content,
              deletedAt: m.reply_to.deleted_at ?? null,
            }
          : null,
        // Wave 211 — denormalized "Forwarded from X" label (snapshot-copy
        // forwarding). null/absent for non-forwards; ChatWindow renders the chip.
        forwardedFromName: m.forwarded_from_name ?? null,
        // Wave 208 SW5 — message-list annotations (date divider + grouping).
        showDateDivider,
        dateLabel,
        isGroupStart,
      }
    })
  }, [messages, user?.id, user?.full_name, user?.avatar_url, t, i18n.language, activeChat])

  // --- Optimistic UI ---

  const [optimisticMessages, addOptimisticMessage] = useOptimistic(
    transformedMessages,
    (state: UiMessage[], newMessage: UiMessage) => [...state, newMessage]
  )

  // --- Mutations ---

  const sendMessageMutation = useMutation({
    // Wave 207 — replyToMessageId threaded into the existing send mutation (no
    // separate mutation): the FormData append is conditional in chatApi.sendMessage.
    mutationFn: ({
      chatId,
      content,
      files,
      replyToMessageId,
    }: {
      chatId: string
      content: string
      files?: File[]
      replyToMessageId?: string
    }) => chatApi.sendMessage(chatId, content, files, replyToMessageId),
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

  // Wave 211 G4 — create a named group chat (creator auto-included by the
  // backend). On success: invalidate the chat list, navigate to the new group,
  // close the modal. No optimism — the server assigns the id + the member set.
  const createGroupMutation = useMutation({
    mutationFn: ({ name, participantIds }: { name: string; participantIds: string[] }) =>
      chatApi.createGroup(name, participantIds),
    onSuccess: (newChat) => {
      queryClient.invalidateQueries({ queryKey: ["chats"] })
      navigate({ to: "/messenger/$chatId", params: { chatId: newChat.id } })
      setIsNewChatModalOpen(false)
    },
  })

  // Wave 211 G4 (SW10) — group member management. Each invalidates the chat list
  // + the active chat detail so the panel + header reflect the change (W210
  // read_receipts ride the ["chats", id] slot, so its detail is refreshed too).
  const renameChatMutation = useMutation({
    mutationFn: ({ chatId, name }: { chatId: string; name: string }) =>
      chatApi.renameChat(chatId, name),
    onSuccess: (_data, { chatId }) => {
      queryClient.invalidateQueries({ queryKey: ["chats"] })
      queryClient.invalidateQueries({ queryKey: ["chats", chatId] })
    },
  })

  const addParticipantMutation = useMutation({
    mutationFn: ({ chatId, userId }: { chatId: string; userId: string }) =>
      chatApi.addParticipant(chatId, userId),
    onSuccess: (_data, { chatId }) => {
      queryClient.invalidateQueries({ queryKey: ["chats"] })
      queryClient.invalidateQueries({ queryKey: ["chats", chatId] })
    },
  })

  const removeParticipantMutation = useMutation({
    mutationFn: ({ chatId, userId }: { chatId: string; userId: string }) =>
      chatApi.removeParticipant(chatId, userId),
    onSuccess: (_data, { chatId, userId }) => {
      queryClient.invalidateQueries({ queryKey: ["chats"] })
      queryClient.invalidateQueries({ queryKey: ["chats", chatId] })
      // Leaving (removing self) exits the chat + closes the panel.
      if (userId === user?.id) {
        setShowGroupInfo(false)
        navigate({ to: "/messenger" })
      }
    },
  })

  // Wave 211 — forward a message (snapshot-copy) into a destination chat. On
  // success: invalidate the dest message list + the chat list (the forward is a
  // new message there), close the picker, and navigate to the destination so
  // the user sees the forwarded message land (Telegram-style confirmation).
  const forwardMutation = useMutation({
    mutationFn: ({
      destChatId,
      sourceChatId,
      messageIds,
    }: {
      destChatId: string
      sourceChatId: string
      messageIds: string[]
    }) => chatApi.forwardMessages(destChatId, sourceChatId, messageIds),
    onSuccess: (_messages, { destChatId }) => {
      queryClient.invalidateQueries({ queryKey: ["messages", destChatId] })
      queryClient.invalidateQueries({ queryKey: ["chats"] })
      setForwardSourceMessageId(null)
      navigate({ to: "/messenger/$chatId", params: { chatId: destChatId } })
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

      // Confirmation can outlive the route it was opened on. Do not kick the
      // user out of a different chat if they navigated before confirming.
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

  // Wave 205 SW6 — author-only edit (optimistic): write the new content +
  // client-time edited_at to the cache immediately; the W205 SW3 broadcast echo
  // reconciles to the authoritative server edited_at (applyMessageEditedFrame is
  // idempotent). Rollback on error. Mirrors clearChatMutation's onMutate/onError/
  // onSettled snapshot pattern, scoped to one message.
  const editMessageMutation = useMutation({
    mutationFn: ({
      chatId,
      messageId,
      content,
    }: {
      chatId: string
      messageId: string
      content: string
    }) => chatApi.editMessage(chatId, messageId, content),
    onMutate: async ({ chatId, messageId, content }) => {
      await queryClient.cancelQueries({ queryKey: ["messages", chatId] })
      const previousMessages = queryClient.getQueryData<MessagesListResponse>(["messages", chatId])
      const editedAt = new Date().toISOString()
      queryClient.setQueryData<MessagesListResponse>(["messages", chatId], (old) =>
        old
          ? {
              ...old,
              items: old.items.map((m) =>
                m.id === messageId ? { ...m, content, edited_at: editedAt } : m
              ),
            }
          : old
      )
      return { previousMessages, chatId }
    },
    onError: (_error, _vars, context) => {
      if (context?.previousMessages) {
        queryClient.setQueryData(["messages", context.chatId], context.previousMessages)
      }
    },
    onSettled: (_data, _error, { chatId }) => {
      queryClient.invalidateQueries({ queryKey: ["messages", chatId], refetchType: "none" })
      queryClient.invalidateQueries({ queryKey: ["chats"], refetchType: "none" })
    },
  })

  // Wave 205 SW6 — author-only soft-delete (optimistic): stamp deleted_at + clear
  // content/attachments (the tombstone) immediately; rollback on error.
  const deleteMessageMutation = useMutation({
    mutationFn: ({ chatId, messageId }: { chatId: string; messageId: string }) =>
      chatApi.deleteMessage(chatId, messageId),
    onMutate: async ({ chatId, messageId }) => {
      await queryClient.cancelQueries({ queryKey: ["messages", chatId] })
      const previousMessages = queryClient.getQueryData<MessagesListResponse>(["messages", chatId])
      const deletedAt = new Date().toISOString()
      queryClient.setQueryData<MessagesListResponse>(["messages", chatId], (old) =>
        old
          ? {
              ...old,
              items: old.items.map((m) =>
                m.id === messageId
                  ? { ...m, deleted_at: deletedAt, content: "", attachments: [] }
                  : m
              ),
            }
          : old
      )
      return { previousMessages, chatId }
    },
    onError: (_error, _vars, context) => {
      if (context?.previousMessages) {
        queryClient.setQueryData(["messages", context.chatId], context.previousMessages)
      }
    },
    onSettled: (_data, _error, { chatId }) => {
      queryClient.invalidateQueries({ queryKey: ["messages", chatId], refetchType: "none" })
      queryClient.invalidateQueries({ queryKey: ["chats"], refetchType: "none" })
    },
  })

  // Wave 206 — emoji reaction toggle (optimistic). mutationFn picks add/remove
  // from currentlyReacted; onMutate flips the aggregate in the ["messages",chatId]
  // cache immediately (toggleReactionAggregate), rollback on error. The server's
  // delta broadcast is self-echo-guarded for the actor, so the optimistic patch is
  // the actor's source of truth; refetch reconciles. Mirrors editMessageMutation.
  const toggleReactionMutation = useMutation({
    mutationFn: ({
      chatId,
      messageId,
      emoji,
      currentlyReacted,
    }: {
      chatId: string
      messageId: string
      emoji: string
      currentlyReacted: boolean
    }) =>
      currentlyReacted
        ? chatApi.removeReaction(chatId, messageId, emoji)
        : chatApi.addReaction(chatId, messageId, emoji),
    onMutate: async ({ chatId, messageId, emoji, currentlyReacted }) => {
      await queryClient.cancelQueries({ queryKey: ["messages", chatId] })
      const previousMessages = queryClient.getQueryData<MessagesListResponse>(["messages", chatId])
      queryClient.setQueryData<MessagesListResponse>(["messages", chatId], (old) =>
        old
          ? {
              ...old,
              items: old.items.map((m) =>
                m.id === messageId
                  ? {
                      ...m,
                      reactions: toggleReactionAggregate(m.reactions, emoji, currentlyReacted),
                    }
                  : m
              ),
            }
          : old
      )
      return { previousMessages, chatId }
    },
    onError: (_error, _vars, context) => {
      if (context?.previousMessages) {
        queryClient.setQueryData(["messages", context.chatId], context.previousMessages)
      }
    },
    onSettled: (_data, _error, { chatId }) => {
      queryClient.invalidateQueries({ queryKey: ["messages", chatId], refetchType: "none" })
    },
  })

  // --- Handlers ---

  // Wave 203 SW8 — depend on the STABLE `.mutate`, not the whole mutation
  // object. React Query v5 returns a new result object on every status
  // transition (idle→pending→success), so `[markReadMutation]` makes this
  // callback unstable. The open-effect below fires markAsRead unconditionally
  // and lists it as a dependency → an unstable markAsRead is an infinite
  // re-fire loop (mutate → status change → new object → new callback → effect
  // re-fires → mutate…), which only the rate-limiter (429) capped. `.mutate`
  // is referentially stable for the mutation's lifetime; React Compiler
  // re-derives memoization from this captured value, so the compiled callback
  // stays stable too.
  const markReadMutate = markReadMutation.mutate
  const markAsRead = useCallback(
    (chatId: string) => {
      markReadMutate(chatId)
    },
    [markReadMutate]
  )

  useEffect(() => {
    if (selectedChatId) {
      markAsRead(selectedChatId)
    }
  }, [selectedChatId, markAsRead])

  // Wave 203 SW7 — mark-read while the chat is open AND focused. Pre-W203,
  // markAsRead fired only on selectedChatId change (the effect above). If a
  // message arrived while the user was LOOKING at the open chat, it was never
  // marked read → the sender never saw "Seen" until the reader navigated away
  // and back. This closes the gap: when the live `messages` cache (which the WS
  // hub updates on `new_message`) grows with a message NOT sent by me, and the
  // tab is visible, re-fire markAsRead → REST mark_read → SW4 broadcast → the
  // sender's bubble flips to "Seen · HH:MM" live. No cross-subtree wiring — it
  // piggybacks on the cache the WS hub already mutates. The dual refs
  // distinguish "switched chats" (reset, don't fire — the open-effect handles
  // it) from "new message in the same chat" (fire). No infinite loop:
  // markAsRead invalidates ["chats"], not ["messages"], so it can't re-trigger.
  const lastReadChatRef = useRef<string | null>(null)
  const lastMessagesLenRef = useRef(0)
  useEffect(() => {
    if (!selectedChatId) {
      lastReadChatRef.current = null
      lastMessagesLenRef.current = 0
      return
    }
    const chatChanged = lastReadChatRef.current !== selectedChatId
    const grew = !chatChanged && messages.length > lastMessagesLenRef.current
    lastReadChatRef.current = selectedChatId
    lastMessagesLenRef.current = messages.length
    if (chatChanged || !grew) return
    const newest = messages[messages.length - 1]
    if (newest && newest.sender_id !== user?.id && document.visibilityState === "visible") {
      markAsRead(selectedChatId)
    }
  }, [messages, selectedChatId, markAsRead, user?.id])

  // Wave 203 SW7 — refocusing the tab with a chat open marks it read too. The
  // growth effect above can't fire on a pure refocus (messages.length is
  // unchanged — messages that arrived while hidden bumped the length ref without
  // firing). markAsRead is idempotent server-side (mark_read broadcasts only
  // when affected > 0), so an unconditional fire on refocus is a cheap no-op
  // when nothing is unread.
  useEffect(() => {
    if (!selectedChatId) return
    const onVisible = () => {
      if (document.visibilityState === "visible") markAsRead(selectedChatId)
    }
    document.addEventListener("visibilitychange", onVisible)
    return () => document.removeEventListener("visibilitychange", onVisible)
  }, [selectedChatId, markAsRead])

  // Wave 204 SW6 — join the ws-hub room for the open chat so the browser
  // receives live chat.{chatId} fan-out (new_message + read frames the backend
  // bridges in W204 SW2). Without joining, ws-hub's collectRecipients returns
  // nil for the empty room and nothing is delivered. Re-runs on selectedChatId
  // change (cleanup leaves the previous room, then joins the new one) AND on
  // isConnected flipping true (rejoin after a (re)connect — complements the
  // hook's ws.onopen rejoin; both idempotent server-side). This completes the
  // live flip: end of W204 SW6 = new_message + read receipts flip without a
  // refetch. Independent of the W203 SW7/SW8 markRead effects above.
  useEffect(() => {
    if (!selectedChatId || !isConnected) return
    sendJoin(selectedChatId)
    return () => sendLeave(selectedChatId)
  }, [selectedChatId, isConnected, sendJoin, sendLeave])

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
      // Wave 207 — optimistic reply preview from the in-compose replyingTo state
      // (copied verbatim; the server-confirmed message replaces this with the real
      // ReplyPreview). isMe is the QUOTED message's isMe so the bubble renders the
      // same "You" vs name label the refetch would. null when not replying.
      replyTo: replyingTo
        ? {
            id: replyingTo.id,
            senderName: replyingTo.senderName,
            isMe: replyingTo.isMe,
            text: replyingTo.text,
            deletedAt: null,
          }
        : null,
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
    sendMessageMutation.mutate({
      chatId: selectedChatId,
      content: text,
      files,
      replyToMessageId: replyingTo?.id,
    })
    // Wave 207 — clear the reply context once the send is dispatched (the chip
    // disappears; the optimistic bubble already carries its own replyTo copy).
    setReplyingTo(null)
  }

  // Wave 207 — start replying to a message. Resolves from transformedMessages
  // (server-confirmed truth, NOT optimisticMessages): replying to a not-yet-sent
  // optimistic message would thread its tempId as reply_to_message_id → backend
  // 404. Deleted targets are skipped (you can't quote a tombstone). `isMe` +
  // senderName are carried so the chip + optimistic bubble label resolve identically.
  const handleStartReply = useCallback(
    (messageId: string) => {
      const target = transformedMessages.find((m) => m.id === messageId)
      if (!target || target.deletedAt) return
      setReplyingTo({
        id: target.id,
        senderName: target.senderName!,
        isMe: target.isMe,
        text: target.text,
      })
    },
    [transformedMessages]
  )

  const handleCancelReply = useCallback(() => setReplyingTo(null), [])

  // Wave 211 — forward handlers. handleStartForward opens the ForwardModal for a
  // message (resolved from transformedMessages — server-confirmed truth, not an
  // optimistic temp id; deleted tombstones are skipped). handleCancelForward
  // closes it; handleForwardToChat dispatches the single-message forward to the
  // chosen destination (the backend endpoint accepts 1..N — the UI forwards one).
  const handleStartForward = useCallback(
    (messageId: string) => {
      const target = transformedMessages.find((m) => m.id === messageId)
      if (!target || target.deletedAt) return
      setForwardSourceMessageId(messageId)
    },
    [transformedMessages]
  )

  const handleCancelForward = useCallback(() => setForwardSourceMessageId(null), [])

  const forwardMutate = forwardMutation.mutate
  const handleForwardToChat = useCallback(
    (destChatId: string) => {
      if (!forwardSourceMessageId || !selectedChatId) return
      forwardMutate({
        destChatId,
        sourceChatId: selectedChatId,
        messageIds: [forwardSourceMessageId],
      })
    },
    [forwardSourceMessageId, selectedChatId, forwardMutate]
  )

  const getOtherParticipant = useCallback(
    (chat: Chat) => {
      return chat.participants.find((p) => p.id !== user?.id)
    },
    [user?.id]
  )

  const handleCreateChat = (participantId: string) => {
    createChatMutation.mutate(participantId)
  }

  // Wave 211 G4 — create a group (name + ≥2 selected members; the backend
  // requires ≥3 total incl. the creator, W209). NewChatModal validates before
  // calling, so this just dispatches.
  const handleCreateGroup = (name: string, participantIds: string[]) => {
    createGroupMutation.mutate({ name, participantIds })
  }

  // Wave 211 G4 (SW10) — group member-management handlers (the panel validates
  // owner-gating in the UI; the backend enforces it authoritatively).
  const handleRenameGroup = (name: string) => {
    const chatId = selectedChatId
    const trimmed = name.trim()
    if (!chatId || !trimmed) return
    renameChatMutation.mutate({ chatId, name: trimmed })
  }

  const handleAddMember = (userId: string) => {
    const chatId = selectedChatId
    if (!chatId) return
    addParticipantMutation.mutate({ chatId, userId })
  }

  const handleRemoveMember = (userId: string) => {
    const chatId = selectedChatId
    if (!chatId) return
    const isSelf = userId === user?.id
    setConfirmDialog({
      open: true,
      title: isSelf ? t("messenger:leaveGroup") : t("messenger:removeMemberTitle"),
      message: isSelf ? t("messenger:confirmLeaveGroup") : t("messenger:confirmRemoveMember"),
      variant: "danger",
      confirmText: isSelf ? t("messenger:leaveGroup") : t("messenger:removeMemberConfirm"),
      cancelText: t("common:buttons.cancel"),
      onConfirm: () => {
        removeParticipantMutation.mutate({ chatId, userId })
        setConfirmDialog(null)
      },
    })
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

  // Wave 205 SW6 — inline message edit + soft-delete handlers.
  const handleEditMessage = (messageId: string, currentText: string) => {
    setEditingMessageId(messageId)
    setEditingMessageContent(currentText)
  }

  const handleCancelEdit = () => {
    setEditingMessageId(null)
    setEditingMessageContent("")
  }

  const handleSaveEdit = (messageId: string) => {
    if (!selectedChatId) return
    const content = editingMessageContent.trim()
    // Close the editor immediately (optimistic — the mutation's onMutate already
    // updates the bubble). Empty edit = no-op (deletion is a separate action).
    setEditingMessageId(null)
    setEditingMessageContent("")
    if (content) {
      editMessageMutation.mutate({ chatId: selectedChatId, messageId, content })
    }
  }

  const handleDeleteMessage = (messageId: string) => {
    if (!selectedChatId) return
    const chatId = selectedChatId
    setConfirmDialog({
      open: true,
      title: t("messenger:deleteMessageTitle"),
      message: t("messenger:confirmDeleteMessage"),
      variant: "danger",
      confirmText: t("common:buttons.delete"),
      cancelText: t("common:buttons.cancel"),
      onConfirm: () => {
        deleteMessageMutation.mutate({ chatId, messageId })
        setConfirmDialog(null)
      },
    })
  }

  // Wave 206 — toggle an emoji reaction on a message (any participant, any
  // message). Reads currentlyReacted from the LIVE cache (not the `messages`
  // closure) so the deps stay stable; depends on the referentially-stable
  // `.mutate` (W203 SW8 lesson — the mutation object changes per status).
  const toggleReactionMutate = toggleReactionMutation.mutate
  const handleToggleReaction = useCallback(
    (messageId: string, emoji: string) => {
      if (!selectedChatId) return
      const current = queryClient.getQueryData<MessagesListResponse>(["messages", selectedChatId])
      const msg = current?.items.find((m) => m.id === messageId)
      const currentlyReacted =
        msg?.reactions?.some((r) => r.emoji === emoji && r.reacted_by_me) ?? false
      toggleReactionMutate({ chatId: selectedChatId, messageId, emoji, currentlyReacted })
    },
    [selectedChatId, queryClient, toggleReactionMutate]
  )

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
  // Wave 211 G4 — branch DM vs group via chatDisplayInfo. A group row shows
  // chat.name + the GroupAvatar glyph (avatar="") + no presence dot; a DM keeps
  // the peer's profile name/avatar/presence (the prior path, now centralized).
  const contacts = useMemo<Contact[]>(
    () =>
      chats.map((chat) => {
        const display = chatDisplayInfo(chat, user?.id, t)
        const status = display.otherParticipant
          ? presenceMap[display.otherParticipant.id]
          : undefined
        return {
          id: chat.id,
          name: display.name,
          avatar: display.avatar,
          lastMessage: chat.last_message?.content || "",
          lastMessageTime: chat.last_message ? formatMessageTime(chat.last_message.created_at) : "",
          unread: chat.unread_count,
          online: display.isGroup ? false : (status?.active ?? false),
          isGroup: display.isGroup,
          memberCount: display.memberCount,
        }
      }),
    [chats, user?.id, t, presenceMap]
  )

  // Wave 211 G4 — the active chat's resolved identity for the ChatArea header
  // (group name + "{n} members" vs the DM peer's name + presence).
  const activeChatDisplay = useMemo(
    () => (activeChat ? chatDisplayInfo(activeChat, user?.id, t) : null),
    [activeChat, user?.id, t]
  )

  return {
    // State
    selectedChatId,
    activeChat,
    activeChatDisplay,
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
    handleCreateGroup,
    isCreatingGroup: createGroupMutation.isPending,

    // Wave 211 G4 (SW10) — group info panel + member management
    currentUserId: user?.id,
    showGroupInfo,
    setShowGroupInfo,
    handleRenameGroup,
    handleAddMember,
    handleRemoveMember,
    isRenamingGroup: renameChatMutation.isPending,
    isAddingMember: addParticipantMutation.isPending,
    isRemovingMember: removeParticipantMutation.isPending,
    handleClearChat,
    handleDeleteChat,

    // Wave 205 SW6 — message edit + soft-delete
    editingMessageId,
    editingMessageContent,
    setEditingMessageContent,
    handleEditMessage,
    handleSaveEdit,
    handleCancelEdit,
    handleDeleteMessage,

    // Wave 206 — message reactions
    handleToggleReaction,

    // Wave 207 — reply/quote
    replyingTo,
    handleStartReply,
    handleCancelReply,

    // Wave 211 — message forwarding (snapshot-copy)
    forwardSourceMessageId,
    handleStartForward,
    handleCancelForward,
    handleForwardToChat,
    isForwarding: forwardMutation.isPending,
  }
}
