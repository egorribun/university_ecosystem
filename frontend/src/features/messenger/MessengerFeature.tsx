import { ChatArea, MessengerBackdrop, MessengerSidebar, NewChatModal } from "@/components/messenger"
import { ProfileModal } from "@/components/messenger/ProfileModal"
import { ConfirmDialog } from "@/components/ui/ConfirmDialog"
import { useMessenger } from "@/contexts/MessengerContext"
import { useMessengerController } from "@/hooks/features/useMessengerController"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { AnimatePresence, m } from "framer-motion"
import { WifiOff } from "lucide-react"
import { useTranslation } from "react-i18next"

/**
 * MessengerFeature — Wave 145 SW2 orchestrator.
 *
 * Mirror of `features/activity/ActivityFeature.tsx` + `features/events/EventsFeature.tsx`
 * convention (W112 SW2). Owns content + state; page wrapper (pages/Messenger.tsx)
 * owns FeatureErrorBoundary chrome.
 *
 * Routes `messenger.tsx` (list) + `messenger.$chatId.tsx` (detail) both lazy-import
 * the same `pages/Messenger.tsx` thin wrapper which delegates here. `selectedChatId`
 * is URL-derived via `useMessengerController` (`useParams({ strict: false })`) so
 * both routes render the same component with different `chatId` param.
 */
export default function MessengerFeature() {
  const { t } = useTranslation(["messenger", "common"])
  const {
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
    messages,
    // Wave 184 SW2 (Path B) — lifted query loading flags from useMessengerController
    // return value (chatsLoading + messagesLoading already exposed at lines 451-452
    // pre-W184 but never consumed by orchestrator). Now threaded through
    // MessengerSidebar → ContactList and ChatArea → ChatWindow so skeleton rows
    // can render while async fetches are in-flight. Defensive UX for low-bandwidth
    // users + first-paint feedback.
    chatsLoading,
    messagesLoading,
    // Wave 184 SW3 (Path B) — lifted query error flags + refetch handles
    // for ContactList + ChatWindow fetch-failure empty-state branches with
    // retry CTA. Pre-W184 fetch failures flashed the "No conversations
    // yet" / "Say hi" empty states wrongly — user had no way to distinguish
    // "empty" from "network error" + no path to retry without page reload.
    chatsError,
    refetchChats,
    messagesError,
    refetchMessages,

    // Profile
    profileUser,
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
  } = useMessengerController()

  // Wave 183 SW6 — surface WS connection status. useMessenger().isConnected
  // flips false when ws-hub disconnects (e.g., backend down, network blip,
  // or W183 SW3 MAX_RECONNECT_ATTEMPTS cap reached). Banner gives user
  // visual feedback that messages may be delayed; ARIA live region
  // announces status change to screen-reader users.
  const { isConnected } = useMessenger()

  const isMobile = useMediaQuery(`(max-width: ${breakpoints.mobile})`)
  const isNarrow = useMediaQuery(`(max-width: ${breakpoints.content})`)
  const reducedMotionPref = useMediaQuery("(prefers-reduced-motion: reduce)")
  const prefersReducedMotion = reducedMotionPref ?? false

  // Mobile view logic
  const showList = !isMobile || !selectedChatId
  const showChat = !isMobile || selectedChatId
  const isBottomNavVisible = isMobile

  return (
    <div
      className="messenger-theme relative flex h-full overflow-hidden bg-msg-chat font-sans text-text-primary"
      style={{
        paddingBottom: isBottomNavVisible
          ? "calc(var(--bn-h, 4rem) + env(safe-area-inset-bottom, 0px) + var(--space-2))"
          : 0,
      }}
    >
      <MessengerBackdrop
        isNarrow={isNarrow}
        isMobile={isMobile}
        prefersReducedMotion={prefersReducedMotion}
      />

      {/* Wave 183 SW6 — WS disconnection banner. Mounted absolute at top
          of messenger viewport (above both sidebar + chat area) so it's
          visible regardless of mobile/desktop layout. AnimatePresence +
          slide-down entrance, useReducedMotion guard. role="status" +
          aria-live="polite" + aria-label so SR users hear status change
          on disconnect/reconnect without interrupting in-progress reading.
          z-overlay so it's above messenger content but below modals. */}
      <AnimatePresence>
        {!isConnected && (
          <m.div
            key="ws-disconnect-banner"
            role="status"
            aria-live="polite"
            aria-label={t("messenger:aria.connectionStatus")}
            initial={prefersReducedMotion ? false : { y: -40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={prefersReducedMotion ? { opacity: 0 } : { y: -40, opacity: 0 }}
            transition={
              prefersReducedMotion
                ? { duration: 0 }
                : { duration: 0.3, ease: [0.22, 1, 0.36, 1] as const }
            }
            className="absolute left-1/2 top-3 z-overlay flex max-w-[28rem] -translate-x-1/2 items-center gap-3 rounded-full bg-(--warning-bg)/(--opacity-heavy) px-4 py-2 text-(--warning-text) shadow-xl backdrop-blur-md"
          >
            <WifiOff className="size-4 shrink-0" strokeWidth={2.5} aria-hidden="true" />
            <div className="flex flex-col leading-tight">
              <span className="text-sm font-semibold">{t("messenger:connectionStatus.lost")}</span>
              <span className="text-xs opacity-medium">
                {t("messenger:connectionStatus.reconnecting")}
              </span>
            </div>
          </m.div>
        )}
      </AnimatePresence>

      <AnimatePresence mode="wait">
        {/* Sidebar */}
        {showList && (
          <MessengerSidebar
            isMobile={isMobile}
            contacts={contacts}
            selectedChatId={selectedChatId}
            setIsNewChatModalOpen={setIsNewChatModalOpen}
            isLoading={chatsLoading}
            isError={chatsError}
            onRetry={() => {
              void refetchChats()
            }}
          />
        )}

        {/* Chat Area */}
        {showChat && (
          <ChatArea
            isMobile={isMobile}
            selectedChatId={selectedChatId}
            activeChat={activeChat}
            messages={messages}
            messagesLoading={messagesLoading}
            messagesError={messagesError}
            onRetryMessages={() => {
              void refetchMessages()
            }}
            showSearchInChat={showSearchInChat}
            setShowSearchInChat={setShowSearchInChat}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            showChatMenu={showChatMenu}
            setShowChatMenu={setShowChatMenu}
            handleSendMessage={handleSendMessage}
            handleViewProfile={handleViewProfile}
            handleClearChat={handleClearChat}
            handleDeleteChat={handleDeleteChat}
            getOtherParticipant={getOtherParticipant}
            presenceMap={presenceMap}
          />
        )}
      </AnimatePresence>

      <NewChatModal
        open={isNewChatModalOpen}
        onClose={() => setIsNewChatModalOpen(false)}
        onSelect={(userId) => handleCreateChat(userId)}
      />

      <ProfileModal
        user={profileUser}
        loading={isProfileLoading}
        error={profileError}
        onClose={handleCloseProfile}
      />

      <ConfirmDialog
        open={confirmDialog?.open ?? false}
        title={confirmDialog?.title ?? ""}
        message={confirmDialog?.message ?? ""}
        confirmText={confirmDialog?.confirmText || t("common:buttons.confirm")}
        cancelText={confirmDialog?.cancelText || t("common:buttons.cancel")}
        variant={confirmDialog?.variant}
        onConfirm={confirmDialog?.onConfirm ?? (() => {})}
        onCancel={() => setConfirmDialog(null)}
      />
    </div>
  )
}
