import { ChatArea, MessengerSidebar, NewChatModal } from "@/components/messenger"
import { ProfileModal } from "@/components/messenger/ProfileModal"
import { ConfirmDialog } from "@/components/ui/ConfirmDialog"
import { useMessengerController } from "@/hooks/features/useMessengerController"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { AnimatePresence } from "framer-motion"
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

  const isMobile = useMediaQuery(`(max-width: ${breakpoints.mobile})`)

  // Mobile view logic
  const showList = !isMobile || !selectedChatId
  const showChat = !isMobile || selectedChatId
  const isBottomNavVisible = isMobile

  return (
    <div
      className="flex h-full overflow-hidden bg-msg-chat font-sans text-text-primary"
      style={{
        paddingBottom: isBottomNavVisible
          ? "calc(var(--bn-h, 4rem) + env(safe-area-inset-bottom, 0px) + var(--space-2))"
          : 0,
      }}
    >
      <AnimatePresence mode="wait">
        {/* Sidebar */}
        {showList && (
          <MessengerSidebar
            isMobile={isMobile}
            contacts={contacts}
            selectedChatId={selectedChatId}
            setIsNewChatModalOpen={setIsNewChatModalOpen}
          />
        )}

        {/* Chat Area */}
        {showChat && (
          <ChatArea
            isMobile={isMobile}
            selectedChatId={selectedChatId}
            activeChat={activeChat}
            messages={messages}
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
