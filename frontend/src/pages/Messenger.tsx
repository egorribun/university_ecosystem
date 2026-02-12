import { useState, useEffect, useCallback, useMemo, useOptimistic } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router-dom"
import {
  ContactList,
  ChatWindow,
  type Message as UiMessage,
  MessageInput,
  NewChatModal,
} from "../components/messenger/MessengerComponents"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { cn } from "@/utils/cn"
import { useAuth } from "../contexts/AuthContext"
import { useMessengerController } from "@/hooks/features/useMessengerController"
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
          className="fixed inset-0 bg-overlay/(--opacity-strong) backdrop-blur-md flex items-center justify-center z-(--z-modal) p-4"
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.9, opacity: 0, y: 20 }}
            className="bg-(--bg-surface) dark:bg-(--bg-page) rounded-4xl shadow-premium w-full max-w-md overflow-hidden border border-glass-border"
          >
            <div className="p-8 space-y-4">
              <h3 className="text-xl font-bold tracking-tight sf-pro">{title}</h3>
              <p className="text-base text-(--text-secondary) font-medium leading-relaxed">
                {message}
              </p>
              <div className="flex gap-3 justify-end pt-4">
                <motion.button
                  whileHover={{ scale: 1.05, backgroundColor: "var(--bg-surface-hover)" }}
                  whileTap={{ scale: 0.95 }}
                  onClick={onCancel}
                  className="px-6 py-2.5 text-sm font-bold rounded-xl border border-subtle transition-colors"
                >
                  {cancelText}
                </motion.button>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={onConfirm}
                  className={cn(
                    "px-6 py-2.5 text-sm font-bold rounded-xl shadow-surface transition-all text-white",
                    variant === "danger"
                      ? "bg-(--error-text) shadow-glow-error"
                      : variant === "warning"
                        ? "bg-(--warning-text) shadow-glow-warning"
                        : "bg-(--primary-main) shadow-glow-primary"
                  )}
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
    setProfileUser,
    isProfileLoading,
    profileError,
    activeChat: _activeChat, // alias if needed or just use activeChat
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

  const navigate = useNavigate()
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.mobile})`)

  // Mobile view logic
  const showList = !isMobile || !selectedChatId
  const showChat = !isMobile || selectedChatId
  const isBottomNavVisible = isMobile

  return (
    <div
      className="flex overflow-hidden text-(--text-primary) font-sans h-full bg-msg-chat"
      style={{
        paddingBottom: isBottomNavVisible
          ? "calc(var(--bn-h, 4rem) + env(safe-area-inset-bottom, 0px) + 8px)"
          : 0,
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
            className="w-full md:w-80 lg:w-96 flex flex-col border-r border-msg-border h-full relative z-(--z-deep) bg-msg-sidebar"
          >
            <div className="p-4 flex justify-between items-center sticky top-0 z-(--z-deep) backdrop-blur-xl bg-msg-header border-b border-msg-border">
              <h1 className="text-2xl font-bold tracking-tight sf-pro">
                {t("messenger:title", "Messages")}
              </h1>
              <motion.button
                whileHover={{ scale: 1.1, backgroundColor: "var(--msg-sidebar-hover)" }}
                whileTap={{ scale: 0.9 }}
                onClick={() => setIsNewChatModalOpen(true)}
                className="p-2 rounded-full transition-colors bg-(--primary-main)/(--opacity-subtle) text-msg-active"
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

            <div className="p-4 bg-msg-sidebar">
              <div className="relative group">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={2}
                  stroke="currentColor"
                  className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-(--text-tertiary) group-focus-within:text-(--primary-main) transition-colors"
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
                  className="w-full pl-10 pr-4 py-2.5 rounded-2xl border-none focus:ring-2 focus:ring-(--brand-main)/(--opacity-soft) outline-none transition-all text-md shadow-sm bg-black/(--opacity-subtle) dark:bg-white/(--opacity-subtle)"
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
            className="flex-1 flex flex-col overflow-hidden h-full relative z-(--z-base) bg-msg-chat"
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
                      className="msg-header shrink-0 h-16 flex items-center px-4 justify-between z-(--z-deep)"
                    >
                      <div className="flex items-center gap-3">
                        {isMobile && (
                          <motion.button
                            whileTap={{ scale: 0.9 }}
                            onClick={() => navigate("/messenger")}
                            className="p-1.5 -ml-1 rounded-full hover:bg-(--bg-surface-hover)/(--opacity-medium) transition-colors"
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
                              className="w-11 h-11 rounded-full object-cover border-2 border-glass-border-subtle"
                            />
                            {presenceMap[getOtherParticipant(activeChat)?.id ?? ""]?.active && (
                              <span className="msg-online-indicator absolute bottom-0 right-0 w-3.5 h-3.5"></span>
                            )}
                          </div>
                          <div>
                            <h2 className="font-bold text-lg leading-tight sf-pro">
                              {getOtherParticipant(activeChat)?.full_name}
                            </h2>
                            <AnimatePresence mode="wait">
                              {presenceMap[getOtherParticipant(activeChat)?.id ?? ""]?.active ? (
                                <motion.p
                                  key="online"
                                  initial={{ opacity: 0, y: 5 }}
                                  animate={{ opacity: 1, y: 0 }}
                                  exit={{ opacity: 0, y: -5 }}
                                  className="text-xs font-semibold uppercase tracking-wider text-msg-online"
                                >
                                  {t("messenger:online", "online")}
                                </motion.p>
                              ) : (
                                <motion.p
                                  key="offline"
                                  initial={{ opacity: 0, y: 5 }}
                                  animate={{ opacity: 1, y: 0 }}
                                  exit={{ opacity: 0, y: -5 }}
                                  className="text-xs text-(--text-secondary) font-medium"
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
                          className="p-2.5 rounded-full hover:bg-(--bg-surface-hover)/(--opacity-medium) transition-colors"
                        >
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            fill="none"
                            viewBox="0 0 24 24"
                            strokeWidth={2}
                            stroke="currentColor"
                            className="w-5 h-5 text-(--text-secondary)"
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
                            className={`p-2.5 rounded-full transition-colors ${showChatMenu ? "bg-(--bg-surface-hover)" : "hover:bg-(--bg-surface-hover)/(--opacity-medium)"}`}
                          >
                            <svg
                              xmlns="http://www.w3.org/2000/svg"
                              fill="none"
                              viewBox="0 0 24 24"
                              strokeWidth={2}
                              stroke="currentColor"
                              className="w-5 h-5 text-(--text-secondary)"
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
                                className="absolute right-0 top-full mt-2 bg-glass-elevated backdrop-blur-xl rounded-2xl shadow-premium border border-glass-border-subtle py-2 min-w-(--min-w-sidebar) z-(--z-navbar) overflow-hidden"
                              >
                                {[
                                  {
                                    icon: "M17.982 18.725A7.488 7.488 0 0012 15.75a7.488 7.488 0 00-5.982 2.975m11.963 0a9 9 0 10-11.963 0m11.963 0A8.966 8.966 0 0112 21a8.966 8.966 0 01-5.982-2.275M15 9.75a3 3 0 11-6 0 3 3 0 016 0z",
                                    label: t("messenger:viewProfile"),
                                    color: "text-(--primary-main)",
                                    action: handleViewProfile,
                                  },
                                  {
                                    icon: "M12 9.75v6.75m0 0l-3-3m3 3l3-3m-8.25 6a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z",
                                    label: t("messenger:clearChat"),
                                    color: "text-(--warning-text)",
                                    action: handleClearChat,
                                  },
                                  {
                                    icon: "M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0",
                                    label: t("messenger:deleteChat"),
                                    color: "text-(--error-text)",
                                    action: handleDeleteChat,
                                  },
                                ].map((item, idx) => (
                                  <button
                                    key={idx}
                                    onClick={item.action}
                                    className="w-full px-4 py-2.5 text-left hover:bg-(--bg-surface-hover) flex items-center gap-3 text-(--text-primary) transition-colors"
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
                      className="shrink-0 h-16 border-b border-glass-border-subtle flex items-center px-4 bg-glass-elevated backdrop-blur-xl z-(--z-deep)"
                    >
                      <motion.button
                        whileTap={{ scale: 0.9 }}
                        onClick={() => {
                          setShowSearchInChat(false)
                          setSearchQuery("")
                        }}
                        className="p-1.5 mr-3 rounded-full hover:bg-(--bg-surface-hover) transition-colors"
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
                        onChange={(event) => setSearchQuery(event.target.value)}
                        placeholder={t("messenger:searchMessages", "Search messages...")}
                        className="flex-1 px-4 py-2.5 rounded-2xl bg-black/(--opacity-subtle) dark:bg-white/(--opacity-subtle) border-none focus:ring-2 focus:ring-(--brand-main)/(--opacity-medium) outline-none transition-all text-md"
                        autoFocus
                      />
                    </motion.div>
                  )}
                </AnimatePresence>

                <ChatWindow messages={messages} />
                <MessageInput onSend={handleSendMessage} />
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-(--bg-surface-hover)/(--opacity-soft)">
                <motion.div
                  initial={{ scale: 0.8, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  whileHover={{ rotate: 5, scale: 1.1 }}
                  className="w-32 h-32 rounded-4xl flex items-center justify-center mb-8 shadow-premium"
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
                    className="w-16 h-16 text-msg-active opacity-(--opacity-strong)"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M8.625 9.75a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375m-13.5 3.01c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.184-4.183a1.14 1.14 0 01.778-.332 48.294 48.294 0 005.83-.498c1.585-.233 2.708-1.626 2.708-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z"
                    />
                  </svg>
                </motion.div>
                <h3 className="text-xl font-bold text-(--text-primary) sf-pro">
                  {t("messenger:selectChat", "Choose a conversation")}
                </h3>
                <p className="mt-2 text-(--text-secondary) max-w-xs">
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
        onSelect={(userId) => handleCreateChat(userId)}
      />

      {(profileUser || isProfileLoading || profileError) && (
        <AnimatePresence>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-overlay/(--opacity-strong) backdrop-blur-md flex items-center justify-center z-(--z-overlay) p-4"
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.9, y: 20 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.9, opacity: 0, y: 20 }}
              className="bg-(--bg-surface) dark:bg-(--bg-page) rounded-4xl shadow-2xl w-full max-w-lg overflow-hidden border border-white/(--opacity-subtle) z-(--z-modal)"
            >
              <div className="p-6 pb-4 flex items-center justify-between border-b border-msg-border">
                <h3 className="text-xl font-bold tracking-tight sf-pro">
                  {profileUser?.full_name || t("messenger:profile", "Profile")}
                </h3>
                <motion.button
                  whileHover={{ rotate: 90, scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  onClick={handleCloseProfile}
                  className="p-2 rounded-full hover:bg-(--bg-surface-hover) transition-colors"
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
                    <div className="w-12 h-12 border-4 border-(--primary-main)/(--opacity-dim) border-t-(--primary-main) rounded-full animate-spin"></div>
                    <p className="mt-4 text-sm font-medium text-(--text-secondary)">
                      {t("messenger:loadingProfile", "Loading profile...")}
                    </p>
                  </div>
                )}

                {profileError && (
                  <div className="p-4 bg-(--error-text)/(--opacity-subtle) rounded-xl text-center">
                    <p className="text-sm font-semibold text-(--error-text)">{profileError}</p>
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
                          className="w-24 h-24 rounded-3xl object-cover border-4 border-(--bg-surface) shadow-xl"
                        />
                        {profileUser.is_active && (
                          <span className="msg-online-indicator absolute -bottom-1 -right-1 w-6 h-6 border-4 border-(--bg-surface)"></span>
                        )}
                      </div>
                      <h4 className="text-2xl font-bold tracking-tight sf-pro">
                        {profileUser.full_name}
                      </h4>
                      <p className="text-(--text-secondary) font-medium">{profileUser.email}</p>
                    </div>

                    <div className="grid grid-cols-2 gap-3 pb-2">
                      <div className="p-4 rounded-2xl bg-(--bg-surface-hover)/(--opacity-medium) border border-subtle">
                        <p className="text-xs font-bold uppercase tracking-widest text-(--text-secondary)/(--opacity-strong) mb-1">
                          {t("messenger:status", "Status")}
                        </p>
                        <p className="text-sm font-bold flex items-center gap-1.5">
                          {profileUser.is_active ? (
                            <>
                              <span className="w-2 h-2 rounded-full bg-(--success-text)"></span>
                              {t("common:active", "Active")}
                            </>
                          ) : (
                            <>
                              <span className="w-2 h-2 rounded-full bg-(--text-tertiary)"></span>
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
                          className="p-4 rounded-2xl bg-(--primary-main)/(--opacity-subtle) border border-(--primary-main)/(--opacity-subtle) hover:bg-(--primary-main)/(--opacity-subtle) transition-colors"
                        >
                          <p className="text-xs font-bold uppercase tracking-widest text-(--primary-main) mb-1">
                            {t("messenger:avatar", "Avatar")}
                          </p>
                          <p className="text-sm font-bold text-(--primary-main)">
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
        confirmText={confirmDialog?.confirmText || t("common:confirm", "Confirm")}
        cancelText={confirmDialog?.cancelText || t("common:cancel", "Cancel")}
        variant={confirmDialog?.variant}
        onConfirm={confirmDialog?.onConfirm ?? (() => {})}
        onCancel={() => setConfirmDialog(null)}
      />
    </div>
  )
}
