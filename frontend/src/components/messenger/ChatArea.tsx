import SmartImage from "@/components/media/SmartImage"
import { ChatWindow, MessageInput, TypingIndicator } from "@/components/messenger"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import { useMessenger } from "@/contexts/MessengerContext"
import { useMessengerController } from "@/hooks/features/useMessengerController"
import { motion as motionTokens } from "@/theme/tokens"
import { AnimatePresence, m, useReducedMotion } from "framer-motion"
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
import { Dispatch, SetStateAction, useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "@tanstack/react-router"

interface ChatAreaProps {
  isMobile: boolean
  selectedChatId: string | null
  activeChat: ReturnType<typeof useMessengerController>["activeChat"]
  messages: ReturnType<typeof useMessengerController>["messages"]
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
}

export function ChatArea({
  isMobile,
  selectedChatId,
  activeChat,
  messages,
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
}: ChatAreaProps) {
  const { t } = useTranslation(["messenger", "common"])
  const navigate = useNavigate()
  const searchInputRef = useRef<HTMLInputElement>(null)
  // Wave 181 SW4 — TypingIndicator wired to existing WebSocket presence channel
  // via useMessenger().getTypingUsersForChat (MessengerContext). No backend
  // changes needed; typing events flow through ws-hub presence subscription
  // already (W134+ infra).
  const { getTypingUsersForChat } = useMessenger()
  const typingUsers = selectedChatId ? getTypingUsersForChat(selectedChatId) : []
  const prefersReducedMotion = useReducedMotion() ?? false

  useEffect(() => {
    if (showSearchInChat && searchInputRef.current) {
      requestAnimationFrame(() => searchInputRef.current?.focus())
    }
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
                      whileTap={{ scale: 0.9 }}
                      onClick={() => navigate({ to: "/messenger" })}
                      className="-ml-1 rounded-full p-1.5 transition-colors hover:bg-(--bg-surface-hover)/(--opacity-medium)"
                    >
                      <ChevronLeft className="h-5 w-5" strokeWidth={2.5} />
                    </m.button>
                  )}
                  <m.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    className="flex cursor-pointer items-center gap-3 border-none bg-transparent text-left outline-none"
                    onClick={handleViewProfile}
                  >
                    <div className="relative">
                      <SmartImage
                        srcRaw={
                          getOtherParticipant(activeChat)?.avatar_url || AVATAR_PLACEHOLDER_URL
                        }
                        fallback={AVATAR_PLACEHOLDER_URL}
                        alt={getOtherParticipant(activeChat)?.full_name || ""}
                        className="size-11 rounded-full border-2 border-(--glass-border-subtle) object-cover"
                      />
                      {presenceMap[getOtherParticipant(activeChat)?.id ?? ""]?.active && (
                        <span className="msg-online-indicator absolute bottom-0 right-0 size-3" />
                      )}
                    </div>
                    <div>
                      <h2 className="sf-pro text-lg font-bold leading-tight">
                        {getOtherParticipant(activeChat)?.full_name}
                      </h2>
                      <AnimatePresence mode="wait">
                        {presenceMap[getOtherParticipant(activeChat)?.id ?? ""]?.active ? (
                          <m.p
                            key="online"
                            initial={{ opacity: 0, y: 5 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -5 }}
                            className="text-xs font-semibold uppercase tracking-wider text-msg-online"
                          >
                            {t("messenger:online", "online")}
                          </m.p>
                        ) : (
                          <m.p
                            key="offline"
                            initial={{ opacity: 0, y: 5 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -5 }}
                            className="text-xs font-medium text-text-secondary"
                          >
                            {t("messenger:offline", "offline")}
                          </m.p>
                        )}
                      </AnimatePresence>
                    </div>
                  </m.button>
                </div>

                <div className="flex items-center gap-1.5">
                  <m.button
                    id="chat-search-toggle"
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => setShowSearchInChat(true)}
                    className="rounded-full p-2.5 transition-colors hover:bg-(--bg-surface-hover)/(--opacity-medium)"
                  >
                    <Search className="h-5 w-5 text-text-secondary" strokeWidth={2} />
                  </m.button>
                  <div className="relative">
                    <m.button
                      id="chat-menu-toggle"
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                      onClick={() => setShowChatMenu(!showChatMenu)}
                      className={`rounded-full p-2.5 transition-colors ${showChatMenu ? "bg-(--bg-surface-hover)" : "hover:bg-(--bg-surface-hover)/(--opacity-medium)"}`}
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
                              icon: User,
                              label: t("messenger:viewProfile"),
                              color: "text-primary-main",
                              action: handleViewProfile,
                            },
                            {
                              icon: MessageCircleOff,
                              label: t("messenger:clearChat"),
                              color: "text-warning-text",
                              action: handleClearChat,
                            },
                            {
                              icon: Trash2,
                              label: t("messenger:deleteChat"),
                              color: "text-error-text",
                              action: handleDeleteChat,
                            },
                          ].map((item, idx) => (
                            <button
                              id={`chat-action-${item.label.toLowerCase().replace(/\s+/g, "-")}`}
                              key={idx}
                              onClick={item.action}
                              className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-text-primary transition-colors hover:bg-bg-surface-hover"
                            >
                              <item.icon className={`h-5 w-5 ${item.color}`} />
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
                className="header-glass z-deep flex h-(--navbar-h-base) shrink-0 items-center border-b border-glass-border bg-surface/(--opacity-medium) px-(--spacing-4) backdrop-blur-xl"
              >
                <m.button
                  whileTap={{ scale: 0.9 }}
                  onClick={() => {
                    setShowSearchInChat(false)
                    setSearchQuery("")
                  }}
                  className="mr-3 rounded-full p-1.5 transition-colors hover:bg-bg-surface-hover"
                >
                  <X className="h-6 w-6" strokeWidth={2} />
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
                  placeholder={t("messenger:searchMessages", "Search messages...")}
                  className="text-md flex-1 rounded-md border-none bg-black/(--opacity-subtle) px-4 py-2.5 outline-none transition-all focus:ring-2 focus:ring-brand-main/(--opacity-medium) dark:bg-white/(--opacity-subtle)"
                />
              </m.div>
            )}
          </AnimatePresence>

          <ChatWindow messages={messages} />
          <TypingIndicator users={typingUsers} prefersReducedMotion={prefersReducedMotion} />
          <MessageInput onSend={handleSendMessage} />
        </>
      ) : (
        <div className="messenger-empty-mesh flex flex-1 flex-col items-center justify-center p-8 text-center">
          <m.div
            initial={prefersReducedMotion ? false : { scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            whileHover={prefersReducedMotion ? undefined : { rotate: 5, scale: 1.06 }}
            transition={prefersReducedMotion ? { duration: 0 } : undefined}
            className="messenger-card-matte mb-(--space-8) flex size-32 items-center justify-center"
            style={{
              background: "var(--messenger-card-bg)",
            }}
          >
            <MessageSquare
              className="size-16 text-(--color-violet-500)"
              style={{ opacity: "var(--opacity-strong)" }}
              strokeWidth={1.5}
              aria-hidden="true"
            />
          </m.div>
          <h3
            className="sf-pro font-bold text-(--text-primary)"
            style={{ fontSize: "var(--fs-messenger-hero)" }}
          >
            {t("messenger:selectChat", "Choose a conversation")}
          </h3>
          <p
            className="mt-3 max-w-md text-(--text-secondary)"
            style={{ fontSize: "var(--fs-messenger-subtitle)" }}
          >
            {t("messenger:selectChatDesc", "Connect with anyone across the university ecosystem.")}
          </p>
        </div>
      )}
    </m.div>
  )
}
