import { useEffect, useId } from "react"
import { m, AnimatePresence } from "framer-motion"
import useMediaQuery from "@/hooks/useMediaQuery"
import { useTranslation } from "react-i18next"
import { Forward, X } from "lucide-react"
import SmartImage from "@/components/media/SmartImage"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import useFocusTrap from "@/hooks/useFocusTrap"
import type { Contact } from "./types"

interface ForwardModalProps {
  /** Open when a message is selected for forwarding (forwardSourceMessageId !== null). */
  open: boolean
  onClose: () => void
  /** The chat list (same UI Contact shape ContactList renders) — the forward destinations. */
  contacts: Contact[]
  /** The chat the message is being forwarded FROM — marked "(current)" in the list. */
  currentChatId?: string | null
  /** Dispatch the forward to the chosen destination chat id. */
  onSelect: (chatId: string) => void
  /** Forward mutation in-flight — disables the destination rows. */
  isForwarding?: boolean
}

/**
 * Wave 211 — forward destination picker. Mirrors NewChatModal's a11y + matte
 * shell (focus trap, Escape, role=dialog, reduced-motion guards) but lists CHATS
 * (the user's conversations) as forward destinations instead of users to start a
 * DM with. A row tap dispatches the single-message snapshot-copy forward to that
 * chat; the controller navigates to the destination on success (Telegram-style
 * confirmation), which closes this modal.
 */
export function ForwardModal({
  open,
  onClose,
  contacts,
  currentChatId,
  onSelect,
  isForwarding = false,
}: ForwardModalProps) {
  const { t } = useTranslation(["messenger", "common"])
  const titleId = useId()
  // Wave 181 SW5 pattern — explicit reduced-motion guard on the dialog
  // entrance scale+y and the per-row whileHover x; subtle scale-on-tap is
  // handled globally by AppProviders MotionConfig reducedMotion="user".
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  // Wave 175 SW3 — focus trap + Escape. initialFocus: false (no search field to
  // win the focus, and avoids auto-scrolling into a long chat list — W110 finding).
  const containerRef = useFocusTrap<HTMLDivElement>({
    active: open,
    onDeactivate: onClose,
    initialFocus: false,
    returnFocus: true,
  })

  useEffect(() => {
    if (!open) return
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault()
        onClose()
      }
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open && (
        <m.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 flex items-center justify-center z-modal p-4"
          role="presentation"
        >
          <div
            className="absolute inset-0 bg-black/(--opacity-strong) backdrop-blur-md cursor-default"
            onClick={onClose}
            aria-hidden="true"
          />
          <m.div
            ref={containerRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            initial={prefersReducedMotion ? false : { scale: 0.95, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={prefersReducedMotion ? { opacity: 0 } : { scale: 0.95, opacity: 0, y: 20 }}
            transition={prefersReducedMotion ? { duration: 0 } : undefined}
            className="messenger-card-matte w-full max-w-[28rem] backdrop-blur-2xl"
          >
            <div className="p-6 pb-4 flex items-center justify-between border-b border-(--glass-border)/(--opacity-subtle) bg-(--bg-surface)/(--opacity-medium)">
              <h3
                id={titleId}
                className="text-xl font-black tracking-tight text-text-primary sf-pro"
              >
                {t("messenger:forwardTo")}
              </h3>
              <button
                type="button"
                onClick={onClose}
                aria-label={t("common:buttons.close")}
                className="min-h-[44px] min-w-[44px] p-2 rounded-xl flex items-center justify-center hover:bg-(--bg-surface-hover)/(--opacity-medium) text-(--text-secondary) transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)"
              >
                <X className="w-5 h-5" aria-hidden="true" />
              </button>
            </div>

            <div className="p-6">
              <div className="max-h-96 overflow-y-auto custom-scrollbar pr-1 -mr-1">
                {contacts.length === 0 ? (
                  <div
                    className="text-center py-12 px-4 space-y-2"
                    role="status"
                    aria-live="polite"
                  >
                    <div
                      className="messenger-card-matte mb-5 mx-auto flex size-16 items-center justify-center"
                      style={{ background: "var(--messenger-card-bg)" }}
                    >
                      <Forward
                        className="size-8 text-(--color-violet-500)"
                        style={{ opacity: "var(--opacity-strong)" }}
                        strokeWidth={1.5}
                        aria-hidden="true"
                      />
                    </div>
                    <p className="text-sm font-bold text-(--text-secondary) opacity-medium">
                      {t("messenger:forwardNoChats")}
                    </p>
                  </div>
                ) : (
                  <div
                    className="space-y-1"
                    role="listbox"
                    aria-label={t("messenger:forwardTo")}
                    aria-busy={isForwarding}
                  >
                    {contacts.map((contact) => (
                      <m.button
                        key={contact.id}
                        type="button"
                        role="option"
                        aria-selected="false"
                        disabled={isForwarding}
                        whileHover={
                          prefersReducedMotion || isForwarding
                            ? undefined
                            : { x: 4, backgroundColor: "var(--bg-surface-hover)" }
                        }
                        whileTap={
                          prefersReducedMotion || isForwarding ? undefined : { scale: 0.98 }
                        }
                        onClick={() => onSelect(contact.id)}
                        className="w-full min-h-[60px] flex items-center gap-4 p-3.5 rounded-2xl transition-all text-left group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface) disabled:opacity-medium disabled:cursor-not-allowed"
                      >
                        <div className="relative shrink-0">
                          <SmartImage
                            srcRaw={contact.avatar || AVATAR_PLACEHOLDER_URL}
                            fallback={AVATAR_PLACEHOLDER_URL}
                            alt=""
                            className="w-11 h-11 rounded-2xl object-cover shadow-sm ring-1 ring-black/(--opacity-faint)"
                          />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-base font-black truncate leading-tight text-text-primary group-hover:text-brand transition-colors sf-pro">
                            {contact.name}
                            {contact.id === currentChatId ? (
                              <span className="ml-2 text-micro font-semibold uppercase tracking-wide text-(--text-secondary) opacity-medium">
                                {t("messenger:forwardCurrentChat")}
                              </span>
                            ) : null}
                          </p>
                          {contact.lastMessage ? (
                            <p className="text-xs text-(--text-secondary) truncate font-medium opacity-medium">
                              {contact.lastMessage}
                            </p>
                          ) : null}
                        </div>
                        <Forward
                          className="size-4 shrink-0 text-(--text-secondary) opacity-medium transition-colors group-hover:text-brand"
                          strokeWidth={2}
                          aria-hidden="true"
                        />
                      </m.button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </m.div>
        </m.div>
      )}
    </AnimatePresence>
  )
}
