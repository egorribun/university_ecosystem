import { ChatArea, MessengerSidebar, NewChatModal } from "@/components/messenger"
import { ProfileModal } from "@/components/messenger/ProfileModal"
import { ConfirmDialog } from "@/components/ui/ConfirmDialog"
import { useMessengerController } from "@/hooks/features/useMessengerController"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { AnimatePresence } from "framer-motion"
import { useTranslation } from "react-i18next"
// dayjs imports removed

export default function Messenger() {
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
        confirmText={confirmDialog?.confirmText || t("common:confirm", "Confirm")}
        cancelText={confirmDialog?.cancelText || t("common:cancel", "Cancel")}
        variant={confirmDialog?.variant}
        onConfirm={confirmDialog?.onConfirm ?? (() => {})}
        onCancel={() => setConfirmDialog(null)}
      />
    </div>
  )
}
