import SmartImage from "@/components/media/SmartImage"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import { User } from "@/types/User"

import { AnimatePresence, m } from "framer-motion"
import { X } from "lucide-react"
import { useEffect, useId } from "react"
import { useTranslation } from "react-i18next"
import useFocusTrap from "@/hooks/useFocusTrap"
import useMediaQuery from "@/hooks/useMediaQuery"

interface ProfileModalProps {
  user: User | null
  loading: boolean
  error: string | null
  onClose: () => void
}

export function ProfileModal({ user, loading, error, onClose }: ProfileModalProps) {
  const { t } = useTranslation(["messenger", "common"])
  const titleId = useId()
  const isOpen = Boolean(user || loading || error)
  // Wave 181 SW4 — useReducedMotion guards on dialog entrance + close button
  // rotate. Framer rotation is the most disorienting interaction for users
  // with vestibular sensitivities; explicit gate ensures the X button just
  // scales rather than rotating under reduced motion preference.
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  // Wave 175 SW3 — focus trap activates whenever modal is open (any of
  // user/loading/error truthy). returnFocus restores focus to the element
  // that opened the modal (chat header avatar, typically).
  const containerRef = useFocusTrap<HTMLDivElement>({
    active: isOpen,
    onDeactivate: onClose,
    returnFocus: true,
  })

  useEffect(() => {
    if (!isOpen) return
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault()
        onClose()
      }
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [isOpen, onClose])

  return (
    <AnimatePresence>
      {isOpen && (
        <m.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-overlay flex items-center justify-center bg-overlay/(--opacity-strong) p-4 backdrop-blur-md"
          role="presentation"
          onClick={onClose}
        >
          <m.div
            ref={containerRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.92, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={prefersReducedMotion ? { opacity: 0 } : { scale: 0.92, opacity: 0, y: 20 }}
            transition={prefersReducedMotion ? { duration: 0 } : undefined}
            className="messenger-card-matte z-modal w-full max-w-[28rem] md:max-w-[32rem] lg:max-w-[36rem]"
            onClick={(event) => event.stopPropagation()}
          >
            {/* Wave 183 SW4 — border-msg-border (undefined token) →
                border-(--glass-border)/(--opacity-subtle) (verified existing
                token in semantics.css). Pre-W183 the bare `border-msg-border`
                class produced NO border (CSS variable `--msg-border` doesn't
                exist), making the header→body separator invisible. */}
            <div className="flex items-center justify-between border-b border-(--glass-border)/(--opacity-subtle) p-6 pb-4">
              <h3 id={titleId} className="sf-pro text-xl font-bold tracking-tight">
                {user?.full_name || t("messenger:profile")}
              </h3>
              {/* Wave 183 SW4 — removed `rotate: 90` from whileHover.
                  Rotation animations on icon buttons are disorienting for
                  users with vestibular sensitivities (WCAG 2.3.3 Level AAA
                  + axe-core accessibility heuristics). useReducedMotion guard
                  already prevented the rotation under OS preference, but the
                  rotation still fired for default-preference users. Scale
                  alone provides sufficient affordance. Also fixed invalid
                  Tailwind class `hover:bg-surface-hover` →
                  `hover:bg-(--bg-surface-hover)/(--opacity-medium)`. */}
              <m.button
                type="button"
                whileHover={prefersReducedMotion ? undefined : { scale: 1.08 }}
                whileTap={prefersReducedMotion ? undefined : { scale: 0.92 }}
                onClick={onClose}
                aria-label={t("common:buttons.close")}
                className="min-h-[44px] min-w-[44px] rounded-full p-2 flex items-center justify-center transition-colors hover:bg-(--bg-surface-hover)/(--opacity-medium) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)"
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </m.button>
            </div>

            <div className="p-8">
              {loading && (
                <div className="flex flex-col items-center py-8">
                  <div className="h-12 w-12 animate-spin rounded-full border-4 border-t-brand border-brand/(--opacity-dim)"></div>
                  <p className="mt-4 text-sm font-medium text-(--text-secondary)">
                    {t("messenger:loadingProfile")}
                  </p>
                </div>
              )}

              {error && (
                <div className="rounded-sm bg-(--error-text)/(--opacity-subtle) p-4 text-center">
                  <p className="text-sm font-semibold text-(--error-text)"> {error}</p>
                </div>
              )}

              {user && (
                <div className="space-y-6">
                  <div className="flex flex-col items-center text-center">
                    <div className="relative mb-4">
                      <SmartImage
                        srcRaw={user.avatar_url || AVATAR_PLACEHOLDER_URL}
                        fallback={AVATAR_PLACEHOLDER_URL}
                        alt={user.full_name ?? ""}
                        className={`size-24 rounded-2xl border-4 border-(--bg-surface) object-cover shadow-xl ${
                          user.is_active ? "messenger-avatar-ring" : ""
                        }`}
                      />
                      {user.is_active && (
                        <span
                          className="messenger-online-indicator absolute -bottom-1 -right-1 size-6 border-4 border-(--bg-surface)"
                          aria-hidden="true"
                        />
                      )}
                    </div>
                    <h4 className="sf-pro text-2xl font-bold tracking-tight">{user.full_name}</h4>
                    <p className="font-medium text-(--text-secondary)">{user.email}</p>
                  </div>

                  <div className="grid grid-cols-2 gap-3 pb-2">
                    <div className="rounded-md border border-subtle bg-(--bg-surface-hover)/(--opacity-medium) p-4">
                      <p className="mb-1 text-xs font-bold uppercase tracking-widest text-(--text-secondary)/(--opacity-strong)">
                        {t("messenger:status")}
                      </p>
                      <span
                        className="messenger-status-badge"
                        data-status={user.is_active ? "online" : "offline"}
                      >
                        <span
                          className="h-2 w-2 rounded-full"
                          style={{
                            background: user.is_active
                              ? "var(--messenger-status-online-text)"
                              : "var(--messenger-status-offline-text)",
                          }}
                          aria-hidden="true"
                        />
                        {user.is_active ? t("common:active") : t("common:inactive")}
                      </span>
                    </div>
                    {user.avatar_url && (
                      <a
                        href={user.avatar_url}
                        target="_blank"
                        rel="noreferrer"
                        className="rounded-md border border-(--primary-main)/(--opacity-subtle) bg-(--primary-main)/(--opacity-subtle) p-4 transition-colors hover:bg-(--primary-main)/(--opacity-subtle)"
                      >
                        <p className="mb-1 text-xs font-bold uppercase tracking-widest text-brand">
                          {t("messenger:avatar")}
                        </p>
                        <p className="text-sm font-bold text-brand">{t("messenger:viewAvatar")}</p>
                      </a>
                    )}
                  </div>
                </div>
              )}
            </div>
          </m.div>
        </m.div>
      )}
    </AnimatePresence>
  )
}
