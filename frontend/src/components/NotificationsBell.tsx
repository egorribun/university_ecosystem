import { useState, useRef, useEffect } from "react"
import { createPortal } from "react-dom"
import { useTranslation } from "react-i18next"
import { AnimatePresence, motion, Variants } from "framer-motion"
import {
  Bell,
  CheckCheck,
  Trash2,
  Loader2,
  Info,
  ChevronDown,
  MessageCircle,
  Calendar,
} from "lucide-react"
import { useNotifications } from "@/hooks/useNotifications"
import { cn } from "@/utils/cn"

export default function NotificationsBell() {
  const { t } = useTranslation(["system"])
  const {
    data,
    unreadCount,
    hasMore,
    nextCursor,
    isLoading,
    markRead,
    markAll,
    clearAll,
    isMarkingAll,
    isClearing,
    isError,
    isRefetching,
    refetch,
    fetchMore,
    isFetchingMore,
    isFetchMoreError,
  } = useNotifications()

  const [isOpen, setIsOpen] = useState(false)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const [coords, setCoords] = useState<{ top: number; right: number | null }>({ top: 0, right: 0 })
  const [isMobile, setIsMobile] = useState(false)

  // Update position when opening
  useEffect(() => {
    if (isOpen && buttonRef.current) {
      const updatePosition = () => {
        const mobile = window.innerWidth < 640
        setIsMobile(mobile)
        const rect = buttonRef.current!.getBoundingClientRect()
        setCoords({
          top: rect.bottom + 12,
          right: mobile ? null : window.innerWidth - rect.right,
        })
      }
      updatePosition()
      window.addEventListener("resize", updatePosition)
      return () => window.removeEventListener("resize", updatePosition)
    }
  }, [isOpen])

  // Close when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        isOpen &&
        buttonRef.current &&
        !buttonRef.current.contains(event.target as Node) &&
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [isOpen])

  const hasNotifications = data.length > 0
  const actionsDisabled =
    isLoading || isError || isRefetching || !hasNotifications || isMarkingAll || isClearing

  const listVariants: Variants = {
    hidden: {
      opacity: 0,
      y: -10,
      scale: 0.95,
      x: isMobile ? "-50%" : 0,
    },
    visible: {
      opacity: 1,
      y: 0,
      scale: 1,
      x: isMobile ? "-50%" : 0,
      transition: {
        duration: 0.2,
        ease: "easeOut",
        staggerChildren: 0.05,
      },
    },
    exit: {
      opacity: 0,
      y: -10,
      scale: 0.95,
      x: isMobile ? "-50%" : 0,
      transition: { duration: 0.15, ease: "easeIn" },
    },
  }

  const itemVariants: Variants = {
    hidden: { opacity: 0, x: -10 },
    visible: { opacity: 1, x: 0 },
  }

  return (
    <>
      <motion.button
        ref={buttonRef}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "relative flex items-center justify-center rounded-xl transition-all duration-300 outline-none group",
          "w-[clamp(32px,7vw,40px)] h-[clamp(32px,7vw,40px)] border border-transparent",
          isOpen
            ? "bg-[var(--nav-link-active-bg)] border-[var(--glass-border)] shadow-sm"
            : "hover:bg-[var(--glass-tint-2)] hover:border-[var(--glass-border)]"
        )}
        style={{
          color: isOpen ? "var(--nav-link)" : "var(--nav-text)",
        }}
        aria-label={t("system:notificationsBell.open")}
      >
        <Bell
          className={cn(
            "w-[clamp(18px,4.5vw,22px)] h-[clamp(18px,4.5vw,22px)] transition-transform duration-500",
            isOpen && "rotate-[-10deg]"
          )}
          strokeWidth={1.8}
        />
        {unreadCount ? (
          <span className="absolute top-1.5 right-1.5 flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500 border-2 border-white dark:border-[#0F172A]"></span>
          </span>
        ) : null}
      </motion.button>

      {createPortal(
        <AnimatePresence>
          {isOpen && (
            <motion.div
              initial="hidden"
              animate="visible"
              exit="exit"
              variants={listVariants}
              className={cn(
                "fixed z-[9999] origin-top-right",
                // Mobile styles: we handle translation in framer motion to avoid conflict
                "max-sm:left-1/2 max-sm:w-[calc(100vw-2rem)]",
                // Desktop styles
                "sm:w-[400px]",
                // Glass styles applied directly to motion component for immediate effect
                "bg-glass backdrop-blur-xl border border-glass-border rounded-2xl shadow-glass overflow-hidden ring-1 ring-black/5"
              )}
              style={{
                top: coords.top,
                right: coords.right ?? undefined,
              }}
              ref={dropdownRef}
            >
              {/* Header */}
              <div className="p-4 border-b border-glass-border flex items-center justify-between bg-surface/30">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-page-foreground tracking-tight">
                    {t("system:notificationsBell.title")}
                  </h3>
                  {unreadCount > 0 && (
                    <span className="bg-indigo-500/20 text-indigo-500 dark:text-indigo-300 text-xs px-2 py-0.5 rounded-full font-medium border border-indigo-500/20">
                      {unreadCount} New
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-1">
                  <button
                    onClick={() => markAll()}
                    disabled={actionsDisabled}
                    className="p-1.5 text-secondary hover:text-page-foreground hover:bg-slate-5 rounded-lg transition-colors disabled:opacity-30 disabled:hover:bg-transparent"
                    title={t("system:notificationsBell.markAll")}
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 16 16"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={2}
                      className="w-4 h-4"
                    >
                      <polyline
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        points="1,8 4,11 11,4"
                      />
                      <polyline strokeLinecap="round" strokeLinejoin="round" points="7,11 14,4" />
                    </svg>
                  </button>
                  <button
                    onClick={() =>
                      clearAll(undefined, {
                        onSuccess: () => setIsOpen(false),
                      })
                    }
                    disabled={actionsDisabled}
                    className="p-1.5 text-secondary hover:text-red-500 hover:bg-red-500/10 rounded-lg transition-colors disabled:opacity-30 disabled:hover:bg-transparent"
                    title={t("system:notificationsBell.clear")}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Content */}
              <div className="max-h-[80vh] sm:max-h-[60vh] overflow-y-auto custom-scrollbar">
                {isError && !isRefetching ? (
                  <div className="p-8 text-center flex flex-col items-center gap-3">
                    <div className="w-12 h-12 rounded-full bg-red-500/10 flex items-center justify-center text-red-500 mb-2">
                      <Info className="w-6 h-6" />
                    </div>
                    <p className="text-sm text-red-500/80">{t("system:notificationsBell.error")}</p>
                    <button
                      onClick={() => refetch()}
                      className="text-xs bg-slate-10 hover:bg-slate-20 text-page-foreground px-3 py-1.5 rounded-lg transition-colors"
                    >
                      {t("system:errorBoundary.retry")}
                    </button>
                  </div>
                ) : isLoading && !hasNotifications ? (
                  <div className="p-12 flex justify-center">
                    <Loader2 className="w-8 h-8 text-indigo-400 animate-spin" />
                  </div>
                ) : data.length === 0 ? (
                  <div className="p-12 text-center text-secondary flex flex-col items-center gap-3">
                    <div className="w-16 h-16 rounded-2xl bg-slate-5 flex items-center justify-center mb-2">
                      <Bell className="w-8 h-8 opacity-20" />
                    </div>
                    <p className="text-sm opacity-60 font-medium">
                      {t("system:notificationsBell.empty")}
                    </p>
                  </div>
                ) : (
                  <div className="flex flex-col">
                    {data.map((n) => (
                      <motion.div
                        key={n.id}
                        variants={itemVariants}
                        className={cn(
                          "relative group border-b border-glass-border last:border-0 p-4 transition-all hover:bg-slate-5",
                          !n.read ? "bg-indigo-500/5" : ""
                        )}
                      >
                        <a
                          href={n.link || "#"}
                          onClick={(e) => {
                            if (!n.link) e.preventDefault()
                            if (!n.read) markRead(n.id)
                          }}
                          className={cn("flex gap-3", n.link ? "cursor-pointer" : "cursor-default")}
                          target={n.link ? "_blank" : undefined}
                          rel={n.link ? "noopener noreferrer" : undefined}
                        >
                          <div
                            className={cn(
                              "w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-opacity",
                              !n.read
                                ? "bg-indigo-500/10 text-indigo-500 dark:text-indigo-400"
                                : "bg-slate-10 text-secondary"
                            )}
                          >
                            {n.type === "chat.message" ? (
                              <MessageCircle className="w-4 h-4" />
                            ) : n.type === "schedule.reminder" ? (
                              <Calendar className="w-4 h-4" />
                            ) : (
                              <Bell className="w-4 h-4" />
                            )}
                          </div>

                          <div className="flex-1 space-y-1">
                            <p
                              className={cn(
                                "text-sm font-medium leading-tight",
                                !n.read ? "text-page-foreground" : "text-secondary"
                              )}
                            >
                              {n.title}
                            </p>
                            <p className="text-xs text-secondary leading-relaxed text-pretty">
                              {n.body}
                            </p>
                            {/* Timestamp if available could go here */}
                          </div>
                        </a>

                        {/* Mark read button (appears on hover) */}
                        {!n.read && (
                          <button
                            onClick={(e) => {
                              e.preventDefault()
                              e.stopPropagation()
                              markRead(n.id)
                            }}
                            className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 transition-all p-1.5 rounded-lg text-secondary hover:text-page-foreground hover:bg-slate-10 bg-surface/50 backdrop-blur-sm"
                            title={t("system:notificationsBell.markRead")}
                          >
                            <CheckCheck className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </motion.div>
                    ))}

                    {hasMore && (
                      <div className="p-3 border-t border-glass-border bg-slate-5/20">
                        {isFetchMoreError && (
                          <p className="text-xs text-red-500 text-center mb-2">
                            {t("system:notificationsBell.loadMoreError")}
                          </p>
                        )}
                        <button
                          onClick={() => fetchMore(nextCursor)}
                          disabled={!nextCursor || isFetchingMore}
                          className="w-full py-2 flex items-center justify-center gap-2 text-xs font-medium text-secondary hover:text-page-foreground bg-slate-5 hover:bg-slate-10 rounded-lg transition-all disabled:opacity-50"
                        >
                          {isFetchingMore ? (
                            <>
                              <Loader2 className="w-3 h-3 animate-spin" />
                              {t("system:notificationsBell.loadingMore")}
                            </>
                          ) : (
                            <>
                              <ChevronDown className="w-3 h-3" />
                              {t("system:notificationsBell.loadMore")}
                            </>
                          )}
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>,
        document.body
      )}
    </>
  )
}
