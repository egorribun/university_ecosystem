import SmartImage from "@/components/media/SmartImage"
import { ChatWindow, MessageInput, TypingIndicator } from "@/components/messenger"
import { GroupAvatar } from "./GroupAvatar"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import { useMessenger } from "@/contexts/MessengerContext"
import { useMessengerController } from "@/hooks/features/useMessengerController"
import useMediaQuery from "@/hooks/useMediaQuery"
import { motion as motionTokens } from "@/theme/tokens"
import { cn } from "@/utils/cn"
import { AnimatePresence, m } from "framer-motion"
import {
  ChevronLeft,
  MessageCircleOff,
  MessageSquare,
  MoreVertical,
  Search,
  Trash2,
  User,
  X,
} from "lucide-react"
import { memo, Dispatch, SetStateAction, useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "@tanstack/react-router"

interface ChatAreaProps {
  isMobile: boolean
  selectedChatId: string | null
  activeChat: ReturnType<typeof useMessengerController>["activeChat"]
  /**
   * Wave 211 G4 — the active chat's resolved display identity (group name +
   * member count vs the DM peer's name + presence), from useMessengerController.
   * Optional so ChatArea stays mountable in tests without the full wiring; the
   * header falls back to the DM path (getOtherParticipant) when absent.
   */
  activeChatDisplay?: ReturnType<typeof useMessengerController>["activeChatDisplay"]
  /**
   * Wave 211 G4 — open the group info / member-management panel (the group
   * header's avatar+title button). Undefined for a DM (the header opens the peer
   * profile via handleViewProfile instead). Wired in SW10.
   */
  onOpenGroupInfo?: () => void
  messages: ReturnType<typeof useMessengerController>["messages"]
  /**
   * Wave 184 SW2 (Path B) — messages query loading flag lifted from
   * useMessengerController (`messagesLoading` at hook line 452). Passed
   * through to ChatWindow which renders skeleton message bubbles BEFORE
   * the no-messages-yet empty state. Defensive UX for low-bandwidth
   * users during message history fetch.
   */
  messagesLoading?: boolean
  /**
   * Wave 184 SW3 (Path B) — messages query error flag lifted from
   * useMessengerController. ChatWindow renders a fetch-failure empty
   * state with Retry CTA BEFORE the no-messages-yet branch. Distinguishes
   * "new chat" from "network error" so users have an actionable retry
   * path without page reload.
   */
  messagesError?: boolean
  /**
   * Wave 184 SW3 (Path B) — retry callback wired to React Query's
   * `refetch()` for the messages query (via MessengerFeature →
   * useMessengerController). Invoked by the Retry button inside the
   * error empty state.
   */
  onRetryMessages?: () => void
  showSearchInChat: boolean
  setShowSearchInChat: Dispatch<SetStateAction<boolean>>
  searchQuery: string
  setSearchQuery: Dispatch<SetStateAction<string>>
  showChatMenu: boolean
  setShowChatMenu: Dispatch<SetStateAction<boolean>>
  handleSendMessage: (text: string, files: File[]) => void
  handleViewProfile: () => void
  handleClearChat: () => void
  handleDeleteChat: () => void
  getOtherParticipant: ReturnType<typeof useMessengerController>["getOtherParticipant"]
  presenceMap: ReturnType<typeof useMessengerController>["presenceMap"]
  /**
   * Wave 205 SW6 — inline message edit + soft-delete, threaded from
   * useMessengerController through MessengerFeature into ChatWindow. See
   * ChatWindowProps for the per-field contract. All optional so ChatArea
   * stays mountable in tests without the full messenger wiring.
   */
  editingMessageId?: string | null
  editingMessageContent?: string
  onEditingContentChange?: (content: string) => void
  onEditMessage?: (messageId: string, currentText: string) => void
  onSaveEdit?: (messageId: string) => void
  onCancelEdit?: () => void
  onDeleteMessage?: (messageId: string) => void
  /**
   * Wave 206 — toggle an emoji reaction on a message, threaded from
   * useMessengerController through MessengerFeature into ChatWindow.
   */
  onToggleReaction?: (messageId: string, emoji: string) => void
  /**
   * Wave 207 — reply/quote, threaded from useMessengerController through
   * MessengerFeature. `replyingTo` drives the MessageInput compose chip;
   * `onStartReply` wires each ChatWindow bubble's reply button; `onCancelReply`
   * clears the reply context.
   */
  replyingTo?: { senderName: string | null; isMe: boolean; text: string } | null
  onStartReply?: (messageId: string) => void
  onCancelReply?: () => void
  /**
   * Wave 211 — forward, threaded from useMessengerController through
   * MessengerFeature. Wires each ChatWindow bubble's forward button → opens the
   * ForwardModal destination picker (mounted in MessengerFeature).
   */
  onForward?: (messageId: string) => void
}

export const ChatArea = memo(function ChatArea({
  isMobile,
  selectedChatId,
  activeChat,
  activeChatDisplay,
  onOpenGroupInfo,
  messages,
  messagesLoading = false,
  messagesError = false,
  onRetryMessages,
  showSearchInChat,
  setShowSearchInChat,
  searchQuery,
  setSearchQuery,
  showChatMenu,
  setShowChatMenu,
  handleSendMessage,
  handleViewProfile,
  handleClearChat,
  handleDeleteChat,
  getOtherParticipant,
  presenceMap,
  editingMessageId,
  editingMessageContent,
  onEditingContentChange,
  onEditMessage,
  onSaveEdit,
  onCancelEdit,
  onDeleteMessage,
  onToggleReaction,
  replyingTo,
  onStartReply,
  onCancelReply,
  onForward,
}: ChatAreaProps) {
  const { t } = useTranslation(["messenger", "common"])
  const navigate = useNavigate()
  const searchInputRef = useRef<HTMLInputElement>(null)
  // Wave 181 SW4 — TypingIndicator wired to existing WebSocket presence channel
  // via useMessenger().getTypingUsersForChat (MessengerContext). No backend
  // changes needed; typing events flow through ws-hub presence subscription
  // already (W134+ infra).
  const { getTypingUsersForChat, sendTyping } = useMessenger()
  const typingUsers = selectedChatId ? getTypingUsersForChat(selectedChatId) : []
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  // Wave 183 SW3 — cancel rAF on unmount/re-fire to prevent focus attempts
  // on a detached DOM node (memory leak + console error potential when the
  // component unmounts mid-focus-frame, e.g., rapid navigation away from
  // /messenger immediately after toggling chat search).
  useEffect(() => {
    if (showSearchInChat && searchInputRef.current) {
      const rafId = requestAnimationFrame(() => searchInputRef.current?.focus())
      return () => cancelAnimationFrame(rafId)
    }
    return undefined
  }, [showSearchInChat])

  return (
    <m.div
      key="chat-area"
      initial={isMobile && !prefersReducedMotion ? { x: 300, opacity: 0 } : undefined}
      animate={{ x: 0, opacity: 1 }}
      exit={isMobile && !prefersReducedMotion ? { x: 300, opacity: 0 } : undefined}
      transition={
        prefersReducedMotion
          ? { duration: 0 }
          : { duration: motionTokens.durationMedium, ease: [0.22, 1, 0.36, 1] }
      }
      className="relative z-base flex h-full flex-1 flex-col overflow-hidden bg-msg-chat"
    >
      {selectedChatId && activeChat ? (
        <>
          <AnimatePresence mode="wait">
            {!showSearchInChat ? (
              <m.div
                key="header-normal"
                initial={prefersReducedMotion ? false : { y: -20, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                exit={prefersReducedMotion ? { opacity: 0 } : { y: -20, opacity: 0 }}
                className="z-deep flex h-(--navbar-h-base) shrink-0 items-center justify-between px-(--spacing-4)"
              >
                <div className="flex items-center gap-3">
                  {isMobile && (
                    <m.button
                      whileTap={prefersReducedMotion ? undefined : { scale: 0.9 }}
                      onClick={() => navigate({ to: "/messenger" })}
                      className="-ml-1 rounded-full p-1.5 transition-colors hover:bg-(--bg-surface-hover)/(--opacity-medium)"
                    >
                      <ChevronLeft className="h-5 w-5" strokeWidth={2.5} />
                    </m.button>
                  )}
                  <m.button
                    whileHover={prefersReducedMotion ? undefined : { scale: 1.02 }}
                    whileTap={prefersReducedMotion ? undefined : { scale: 0.98 }}
                    className="flex cursor-pointer items-center gap-3 border-none bg-transparent text-left outline-none"
                    onClick={() =>
                      activeChatDisplay?.isGroup ? onOpenGroupInfo?.() : handleViewProfile()
                    }
                  >
                    <div className="relative">
                      {/* Wave 211 G4 — group header: the GroupAvatar Users glyph +
                          "{n} members" (no per-user photo, no presence). DM header:
                          the peer photo + the Wave 202 SW5 pulsing presence ring
                          (ONE infinite animation, only on the open conversation —
                          ContactList rows keep the static dot). */}
                      {activeChatDisplay?.isGroup ? (
                        <GroupAvatar className="size-11" iconSize={20} />
                      ) : (
                        <>
                          <SmartImage
                            srcRaw={
                              getOtherParticipant(activeChat)?.avatar_url || AVATAR_PLACEHOLDER_URL
                            }
                            fallback={AVATAR_PLACEHOLDER_URL}
                            alt={getOtherParticipant(activeChat)?.full_name || ""}
                            className="size-11 rounded-full border-2 border-(--glass-border-subtle) object-cover"
                          />
                          {presenceMap[getOtherParticipant(activeChat)?.id ?? ""]?.active && (
                            <span
                              className="messenger-online-pulse absolute bottom-0 right-0"
                              aria-hidden="true"
                            />
                          )}
                        </>
                      )}
                    </div>
                    <div>
                      <h2 className="sf-pro text-lg font-bold leading-tight">
                        {activeChatDisplay?.name ?? getOtherParticipant(activeChat)?.full_name}
                      </h2>
                      {activeChatDisplay?.isGroup ? (
                        <p className="text-xs font-medium text-text-secondary">
                          {t("messenger:group.members", { count: activeChatDisplay.memberCount })}
                        </p>
                      ) : (
                        <AnimatePresence mode="wait">
                          {presenceMap[getOtherParticipant(activeChat)?.id ?? ""]?.active ? (
                            <m.p
                              key="online"
                              initial={{ opacity: 0, y: 5 }}
                              animate={{ opacity: 1, y: 0 }}
                              exit={{ opacity: 0, y: -5 }}
                              className="text-xs font-semibold uppercase tracking-wider text-msg-online"
                            >
                              {t("messenger:online")}
                            </m.p>
                          ) : (
                            <m.p
                              key="offline"
                              initial={{ opacity: 0, y: 5 }}
                              animate={{ opacity: 1, y: 0 }}
                              exit={{ opacity: 0, y: -5 }}
                              className="text-xs font-medium text-text-secondary"
                            >
                              {t("messenger:offline")}
                            </m.p>
                          )}
                        </AnimatePresence>
                      )}
                    </div>
                  </m.button>
                </div>

                <div className="flex items-center gap-1.5">
                  <m.button
                    id="chat-search-toggle"
                    aria-label={t("messenger:searchMessages")}
                    whileHover={prefersReducedMotion ? undefined : { scale: 1.05 }}
                    whileTap={prefersReducedMotion ? undefined : { scale: 0.95 }}
                    onClick={() => setShowSearchInChat(true)}
                    className="rounded-full p-2.5 transition-colors hover:bg-(--bg-surface-hover)/(--opacity-medium)"
                  >
                    <Search className="h-5 w-5 text-text-secondary" strokeWidth={2} />
                  </m.button>
                  <div className="relative">
                    <m.button
                      id="chat-menu-toggle"
                      aria-label={t("messenger:chatActions")}
                      whileHover={prefersReducedMotion ? undefined : { scale: 1.05 }}
                      whileTap={prefersReducedMotion ? undefined : { scale: 0.95 }}
                      onClick={() => setShowChatMenu(!showChatMenu)}
                      className={cn(
                        "rounded-full p-2.5 transition-colors",
                        showChatMenu
                          ? "bg-(--bg-surface-hover)"
                          : "hover:bg-(--bg-surface-hover)/(--opacity-medium)"
                      )}
                    >
                      <MoreVertical className="h-5 w-5 text-text-secondary" strokeWidth={2} />
                    </m.button>
                    <AnimatePresence>
                      {showChatMenu && (
                        <m.div
                          initial={
                            prefersReducedMotion ? false : { opacity: 0, scale: 0.9, y: 10, x: 5 }
                          }
                          animate={{ opacity: 1, scale: 1, y: 0, x: 0 }}
                          exit={
                            prefersReducedMotion
                              ? { opacity: 0 }
                              : { opacity: 0, scale: 0.9, y: 10 }
                          }
                          className="card-glass z-navbar absolute right-0 top-full mt-2 min-w-sidebar overflow-hidden rounded-md py-2"
                        >
                          {[
                            {
                              id: "view-profile",
                              icon: User,
                              label: t("messenger:viewProfile"),
                              color: "text-primary-main",
                              action: handleViewProfile,
                            },
                            {
                              id: "clear-chat",
                              icon: MessageCircleOff,
                              label: t("messenger:clearChat"),
                              color: "text-warning-text",
                              action: handleClearChat,
                            },
                            {
                              id: "delete-chat",
                              icon: Trash2,
                              label: t("messenger:deleteChat"),
                              color: "text-error-text",
                              action: handleDeleteChat,
                            },
                          ].map((item) => (
                            <button
                              id={`chat-action-${item.id}`}
                              key={item.id}
                              type="button"
                              onClick={item.action}
                              className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-text-primary transition-colors hover:bg-(--bg-surface-hover)/(--opacity-medium) focus-visible:outline-none focus-visible:bg-(--bg-surface-hover)/(--opacity-medium) focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-(--color-violet-500)"
                            >
                              <item.icon className={`h-5 w-5 ${item.color}`} aria-hidden="true" />
                              <span className="text-sm font-medium">{item.label}</span>
                            </button>
                          ))}
                        </m.div>
                      )}
                    </AnimatePresence>
                  </div>
                </div>
              </m.div>
            ) : (
              <m.div
                key="header-search"
                initial={prefersReducedMotion ? false : { y: -20, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                exit={prefersReducedMotion ? { opacity: 0 } : { y: -20, opacity: 0 }}
                className="sticky top-0 z-deep flex h-(--navbar-h-base) shrink-0 items-center bg-surface/(--opacity-medium) px-(--spacing-4) backdrop-blur-xl"
              >
                <m.button
                  type="button"
                  whileTap={prefersReducedMotion ? undefined : { scale: 0.9 }}
                  onClick={() => {
                    setShowSearchInChat(false)
                    setSearchQuery("")
                  }}
                  className="mr-3 flex min-h-[44px] min-w-[44px] items-center justify-center rounded-full transition-colors hover:bg-(--bg-surface-hover)/(--opacity-medium) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500)"
                  aria-label={t("common:buttons.close")}
                >
                  <X className="h-6 w-6" strokeWidth={2} aria-hidden="true" />
                </m.button>
                <input
                  id="chat-search-input"
                  type="text"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  ref={searchInputRef}
                  autoComplete="off"
                  autoCorrect="off"
                  spellCheck="false"
                  placeholder={t("messenger:searchMessages")}
                  aria-label={t("messenger:searchMessages")}
                  className="matte-input text-md flex-1 rounded-md border-none px-4 py-2.5 outline-none transition-all focus-visible:ring-2 focus-visible:ring-(--color-violet-500)/(--opacity-medium)"
                />
              </m.div>
            )}
          </AnimatePresence>

          {/* Wave 184 SW1 (Path A) — searchQuery + onClearSearch threaded so
              ChatWindow can filter messages + render search-empty empty state.
              The raw `searchQuery` is passed through; ChatWindow applies
              `useDebounced(searchQuery, "search")` (200ms) internally so the
              per-keystroke render does NOT re-filter the message array.
              onClearSearch clears the query but keeps the search input
              mounted (showSearchInChat stays true) so the user can type a
              new query immediately — matches W183 SW1 ContactList pattern. */}
          <ChatWindow
            key={selectedChatId}
            chatId={selectedChatId}
            messages={messages}
            isLoading={messagesLoading}
            isError={messagesError}
            onRetry={onRetryMessages}
            searchQuery={showSearchInChat ? searchQuery : ""}
            onClearSearch={() => setSearchQuery("")}
            editingMessageId={editingMessageId}
            editingMessageContent={editingMessageContent}
            onEditingContentChange={onEditingContentChange}
            onEditMessage={onEditMessage}
            onSaveEdit={onSaveEdit}
            onCancelEdit={onCancelEdit}
            onDeleteMessage={onDeleteMessage}
            onToggleReaction={onToggleReaction}
            onStartReply={onStartReply}
            onForward={onForward}
          />
          <TypingIndicator users={typingUsers} prefersReducedMotion={prefersReducedMotion} />
          <MessageInput
            onSend={handleSendMessage}
            replyingTo={replyingTo}
            onCancelReply={onCancelReply}
            onTyping={() => {
              if (selectedChatId) sendTyping(selectedChatId)
            }}
          />
        </>
      ) : (
        <div
          className="messenger-empty-mesh relative flex flex-1 flex-col items-center justify-center overflow-hidden px-8 pt-12 pb-16 text-center"
          role="status"
          aria-label={t("messenger:selectChat")}
        >
          {/* Wave 183 SW2 — decorative ambient orb behind icon. Uses the
              same --messenger-orb-1 token as MessengerBackdrop (violet
              tint at 10%/22% in light/dark) but at a smaller scale (~520px)
              and tighter blur to add visual weight under the icon without
              competing with MessengerBackdrop's full-viewport orbs. Pure
              CSS, pointer-events:none, aria-hidden. */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute left-1/2 top-1/2 -z-1 size-[520px] -translate-x-1/2 -translate-y-[55%] rounded-full"
            style={{
              background: "radial-gradient(circle, var(--messenger-orb-1) 0%, transparent 65%)",
              filter: "blur(50px)",
            }}
          />
          <m.div
            initial={prefersReducedMotion ? false : { scale: 0.85, opacity: 0, y: 8 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            whileHover={prefersReducedMotion ? undefined : { rotate: 3, scale: 1.05 }}
            transition={
              prefersReducedMotion
                ? { duration: 0 }
                : { duration: 0.6, ease: [0.22, 1, 0.36, 1] as const }
            }
            className="messenger-card-matte relative mb-7 flex size-40 items-center justify-center"
            style={{
              background: "var(--messenger-card-bg)",
            }}
          >
            <MessageSquare
              className="size-20 text-(--color-violet-500)"
              style={{ opacity: "var(--opacity-strong)" }}
              strokeWidth={1.5}
              aria-hidden="true"
            />
          </m.div>
          {/* W182 SW3 structural fix replacing W181 polish-v1 inline-style
              workaround. Root cause (per Agent 2 investigation): on a
              `flex flex-col items-center` parent, the cross-axis is
              horizontal. `align-items: center` (the default behavior of
              `items-center`) makes children shrink to intrinsic content
              width unless they explicitly opt out via `align-self`. Fix:
              `self-stretch` overrides to `align-self: stretch` so the
              child fills the cross-axis; `max-w-2xl` caps render width at
              42rem; `mx-auto` centers the capped element within the parent.
              Cross-page audit (W182 SW3) examined 4 candidates: none
              reproduce the same `w-full + max-w-N` child pattern, so the
              bug is specific to this empty-state structure. */}
          <h3
            className="sf-pro mx-auto max-w-[42rem] self-stretch text-center font-bold text-(--text-primary)"
            style={{ fontSize: "var(--fs-messenger-hero)" }}
          >
            {t("messenger:selectChat")}
          </h3>
          <p
            className="mx-auto mt-3 max-w-[32rem] self-stretch text-center text-(--text-secondary)"
            style={{ fontSize: "var(--fs-messenger-subtitle)" }}
          >
            {t("messenger:selectChatDesc")}
          </p>
        </div>
      )}
    </m.div>
  )
})

export default ChatArea
