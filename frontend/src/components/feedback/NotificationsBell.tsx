import { useState, useRef, useEffect } from "react"
import { createPortal } from "react-dom"
import { useTranslation } from "react-i18next"
import { AnimatePresence, m, Variants } from "framer-motion"
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
import useMediaQuery from "@/hooks/useMediaQuery"

/** @internal Positioning starts only for an open panel with a live trigger. */
export function canUpdateNotificationPosition(
  isOpen: boolean,
  button: HTMLButtonElement | null
): button is HTMLButtonElement {
  return isOpen && button !== null
}

/** @internal Focus restoration is a no-op when the trigger was removed. */
export const focusNotificationTrigger = (button: HTMLButtonElement | null): void => {
  if (button !== null) button.focus()
}

/** @internal Outside-click policy kept pure for exhaustive interaction tests. */
export const shouldCloseNotificationDropdown = (
  isOpen: boolean,
  button: Node | null,
  dropdown: Node | null,
  target: Node
): boolean => {
  if (!isOpen || button === null || dropdown === null) return false
  return !button.contains(target) && !dropdown.contains(target)
}

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
  // Coordinates are populated only while the panel is open. Keeping the
  // closed state empty avoids carrying an object that can never be observed
  // by users or assistive technology before the positioning effect runs.
  const [coords, setCoords] = useState<{ top: number; right: number | null }>()
  const [isMobile, setIsMobile] = useState<boolean | null>(null)
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  // Update position when opening
  useEffect(() => {
    const button = buttonRef.current
    if (!canUpdateNotificationPosition(isOpen, button)) return
    const updatePosition = () => {
      const mobile = window.innerWidth < 640
      setIsMobile(mobile)
      const rect = button.getBoundingClientRect()
      setCoords({
        top: rect.bottom + 12,
        right: mobile ? null : window.innerWidth - rect.right,
      })
    }
    updatePosition()
    window.addEventListener("resize", updatePosition)
    return () => window.removeEventListener("resize", updatePosition)
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return
      setIsOpen(false)
      focusNotificationTrigger(buttonRef.current)
    }
    document.addEventListener("keydown", handleEscape)
    return () => document.removeEventListener("keydown", handleEscape)
  }, [isOpen])

  // Close when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      const button = buttonRef.current
      const dropdown = dropdownRef.current
      const target = event.target as Node
      if (shouldCloseNotificationDropdown(isOpen, button, dropdown, target)) setIsOpen(false)
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [isOpen])

  const hasNotifications = data.length > 0
  const actionsDisabled = Boolean(
    isLoading || isError || isRefetching || !hasNotifications || isMarkingAll || isClearing
  )

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
        duration: prefersReducedMotion ? 0 : 0.2,
        ease: "easeOut",
        staggerChildren: 0.05,
      },
    },
    exit: {
      opacity: 0,
      y: -10,
      scale: 0.95,
      x: isMobile ? "-50%" : 0,
      transition: { duration: prefersReducedMotion ? 0 : 0.15, ease: "easeIn" },
    },
  }

  const itemVariants: Variants = {
    hidden: { opacity: 0, x: -10 },
    visible: { opacity: 1, x: 0 },
  }

  return (
    <>
      <button
        ref={buttonRef}
        id="global-notifications-btn"
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "relative nav-action-btn group",
          isOpen
            ? "bg-(--primary-main)/(--opacity-subtle) !border-(--primary-main)/(--opacity-soft) shadow-sm text-(--primary-main)"
            : "text-text-primary hover:text-(--primary-main)"
        )}
        data-unread={unreadCount ? "" : undefined}
        aria-label={t("system:notificationsBell.open")}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        aria-controls="notifications-center"
      >
        <Bell
          className={cn("nav-action-icon bell-wiggle", isOpen && "rotate-[-10deg]")}
          strokeWidth={2}
        />
        {unreadCount ? (
          <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center">
            <span className="animate-ping absolute inline-flex h-2.5 w-2.5 rounded-full bg-error-border opacity-strong" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-(--error-text) border-2 border-(--bg-surface) dark:border-(--bg-page)" />
          </span>
        ) : null}
      </button>

      {typeof document !== "undefined"
        ? createPortal(
            <AnimatePresence>
              {isOpen && (
                <m.div
                  id="notifications-center"
                  role="dialog"
                  aria-modal="false"
                  aria-labelledby="notifications-center-title"
                  initial="hidden"
                  animate="visible"
                  exit="exit"
                  variants={listVariants}
                  className={cn(
                    "fixed z-popover origin-top-right",
                    // Mobile styles: we handle translation in framer motion to avoid conflict
                    "max-sm:left-1/2",
                    // Desktop styles
                    "sm:w-96",
                    // Glass styles applied directly to motion component for immediate effect
                    "bg-glass backdrop-blur-xl border border-glass-border rounded-2xl shadow-glass overflow-hidden ring-1 ring-black/(--opacity-faint)"
                  )}
                  style={{
                    top: coords?.top ?? 0,
                    right: coords?.right ?? undefined,
                    width: isMobile ? "calc(100vw - 2rem)" : undefined,
                  }}
                  ref={dropdownRef}
                >
                  {/* Header */}
                  <div className="p-4 border-b border-glass-border flex items-center justify-between bg-(--bg-surface)/(--opacity-soft)">
                    <div className="flex items-center gap-2">
                      <h3
                        id="notifications-center-title"
                        className="font-semibold text-text-primary tracking-tight"
                      >
                        {t("system:notificationsBell.title")}
                      </h3>
                      {unreadCount > 0 && (
                        <span className="bg-brand-subtle-bg text-brand text-xs px-2 py-0.5 rounded-full font-medium border border-brand/(--opacity-dim)">
                          {unreadCount} {t("system:notificationsBell.new")}
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => markAll()}
                        disabled={actionsDisabled}
                        className="min-h-11 min-w-11 p-2 text-(--text-secondary) hover:text-text-primary hover:bg-(--text-secondary)/(--opacity-faint) rounded-lg transition-colors focus-ring-premium disabled:opacity-soft disabled:hover:bg-transparent"
                        aria-label={t("system:notificationsBell.markAll")}
                        title={t("system:notificationsBell.markAll")}
                      >
                        <CheckCheck className="w-4 h-4" aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          clearAll(undefined, {
                            onSuccess: () => setIsOpen(false),
                          })
                        }
                        disabled={actionsDisabled}
                        className="min-h-11 min-w-11 p-2 text-(--text-secondary) hover:text-error-text hover:bg-error-bg/(--opacity-subtle) rounded-lg transition-colors focus-ring-premium disabled:opacity-soft disabled:hover:bg-transparent"
                        aria-label={t("system:notificationsBell.clear")}
                        title={t("system:notificationsBell.clear")}
                      >
                        <Trash2 className="w-4 h-4" aria-hidden="true" />
                      </button>
                    </div>
                  </div>

                  {/* Content */}
                  <div className="max-h-(--h-hero-lg) sm:max-h-(--h-hero-md) overflow-y-auto custom-scrollbar">
                    {isError && !isRefetching ? (
                      <div className="p-8 text-center flex flex-col items-center gap-3">
                        <div className="w-12 h-12 rounded-full bg-error-bg/(--opacity-dim) flex items-center justify-center text-error-text mb-2">
                          <Info className="w-6 h-6" />
                        </div>
                        <p className="text-sm text-error-text/(--opacity-hover)">
                          {t("system:notificationsBell.error")}
                        </p>
                        <button
                          onClick={() => refetch()}
                          className="text-xs bg-(--border-subtle) hover:bg-(--border-strong) text-text-primary px-3 py-1.5 rounded-lg transition-colors"
                        >
                          {t("system:errorBoundary.retry")}
                        </button>
                      </div>
                    ) : isLoading && !hasNotifications ? (
                      <div className="p-12 flex justify-center">
                        <Loader2 className="w-8 h-8 text-brand animate-spin" />
                      </div>
                    ) : data.length === 0 ? (
                      <div className="p-12 text-center text-(--text-secondary) flex flex-col items-center gap-3">
                        <div className="w-16 h-16 rounded-2xl bg-(--text-secondary)/(--opacity-faint) flex items-center justify-center mb-2">
                          <Bell className="w-8 h-8 opacity-dim" />
                        </div>
                        <p className="text-sm opacity-medium font-medium">
                          {t("system:notificationsBell.empty")}
                        </p>
                      </div>
                    ) : (
                      <div className="flex flex-col">
                        {data.map((n) => (
                          <m.div
                            key={n.id}
                            variants={itemVariants}
                            className={cn(
                              "relative group border-b border-glass-border last:border-0 p-4 transition-all hover:bg-(--text-secondary)/(--opacity-faint)",
                              !n.read ? "bg-brand/(--opacity-faint)" : ""
                            )}
                          >
                            <a
                              href={n.link || "#"}
                              onClick={(e) => {
                                if (!n.link) e.preventDefault()
                                if (!n.read) markRead(n.id)
                              }}
                              className={cn(
                                "flex gap-3",
                                n.link ? "cursor-pointer" : "cursor-default"
                              )}
                            >
                              <div
                                className={cn(
                                  "w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-opacity",
                                  !n.read
                                    ? "bg-brand/(--opacity-subtle) text-brand dark:text-brand"
                                    : "bg-(--border-subtle) text-(--text-secondary)"
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
                                    !n.read ? "text-text-primary" : "text-(--text-secondary)"
                                  )}
                                >
                                  {n.title}
                                </p>
                                <p className="text-xs text-(--text-secondary) leading-relaxed text-pretty">
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
                                className="absolute top-2 right-2 min-h-11 min-w-11 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity p-1.5 rounded-lg text-(--text-secondary) hover:text-text-primary hover:bg-(--border-strong) bg-(--bg-surface)/(--opacity-medium) backdrop-blur-sm"
                                title={t("system:notificationsBell.markRead")}
                              >
                                <CheckCheck className="w-3.5 h-3.5" />
                              </button>
                            )}
                          </m.div>
                        ))}

                        {hasMore && (
                          <div className="p-3 border-t border-glass-border bg-(--text-secondary)/(--opacity-faint)">
                            {isFetchMoreError && (
                              <p className="text-xs text-error-text text-center mb-2">
                                {t("system:notificationsBell.loadMoreError")}
                              </p>
                            )}
                            <button
                              onClick={() => fetchMore(nextCursor)}
                              disabled={!nextCursor || isFetchingMore}
                              className="w-full py-2 flex items-center justify-center gap-2 text-xs font-medium text-(--text-secondary) hover:text-text-primary bg-(--text-secondary)/(--opacity-faint) hover:bg-(--border-strong) rounded-lg transition-all disabled:opacity-medium"
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
                </m.div>
              )}
            </AnimatePresence>,
            document.body
          )
        : null}
    </>
  )
}
