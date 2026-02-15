import SmartImage from "@/components/SmartImage"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import { User } from "@/types/User"

import { AnimatePresence, motion } from "framer-motion"
import { X } from "lucide-react"
import { useTranslation } from "react-i18next"

interface ProfileModalProps {
  user: User | null
  loading: boolean
  error: string | null
  onClose: () => void
}

export function ProfileModal({ user, loading, error, onClose }: ProfileModalProps) {
  const { t } = useTranslation(["messenger", "common"])

  // Fixed early return logic for AnimatePresence
  // if (!user && !loading && !error) return null

  return (
    <AnimatePresence>
      {(user || loading || error) && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-overlay flex items-center justify-center bg-overlay/(--opacity-strong) p-(--space-4) backdrop-blur-md"
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.9, opacity: 0, y: 20 }}
            className="z-modal w-full max-w-lg overflow-hidden rounded-2xl border border-white/(--opacity-subtle) bg-(--bg-surface) shadow-2xl dark:bg-(--bg-page)"
          >
            <div className="flex items-center justify-between border-b border-msg-border p-(--space-6) pb-(--space-4)">
              <h3 className="sf-pro text-xl font-bold tracking-tight">
                {user?.full_name || t("messenger:profile", "Profile")}
              </h3>
              <motion.button
                whileHover={{ rotate: 90, scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                onClick={onClose}
                className="rounded-full p-2 transition-colors hover:bg-[--bg-surface-hover]"
              >
                <X className="h-5 w-5" />
              </motion.button>
            </div>

            <div className="p-(--space-8)">
              {loading && (
                <div className="flex flex-col items-center py-8">
                  <div className="h-12 w-12 animate-spin rounded-full border-4 border-t-[--primary-main] border-[--primary-main]/[--opacity-dim]"></div>
                  <p className="mt-4 text-sm font-medium text-[--text-secondary]">
                    {t("messenger:loadingProfile", "Loading profile...")}
                  </p>
                </div>
              )}

              {error && (
                <div className="rounded-sm bg-[--error-text]/[--opacity-subtle] p-4 text-center">
                  <p className="text-sm font-semibold text-[--error-text]"> {error}</p>
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
                        className="size-(--space-24) rounded-md border-4 border-(--bg-surface) object-cover shadow-xl"
                      />
                      {user.is_active && (
                        <span className="msg-online-indicator absolute -bottom-(--space-1) -right-(--space-1) size-(--space-6) border-4 border-(--bg-surface)"></span>
                      )}
                    </div>
                    <h4 className="sf-pro text-2xl font-bold tracking-tight">{user.full_name}</h4>
                    <p className="font-medium text-[--text-secondary]">{user.email}</p>
                  </div>

                  <div className="grid grid-cols-2 gap-(--space-3) pb-(--space-2)">
                    <div className="rounded-md border border-subtle bg-(--bg-surface-hover)/(--opacity-medium) p-(--space-4)">
                      <p className="mb-1 text-xs font-bold uppercase tracking-widest text-[--text-secondary]/[--opacity-strong]">
                        {t("messenger:status", "Status")}
                      </p>
                      <p className="flex items-center gap-1.5 text-sm font-bold">
                        {user.is_active ? (
                          <>
                            <span className="h-2 w-2 rounded-full bg-[--success-text]"></span>
                            {t("common:active", "Active")}
                          </>
                        ) : (
                          <>
                            <span className="h-2 w-2 rounded-full bg-[--text-tertiary]"></span>
                            {t("common:inactive", "Inactive")}
                          </>
                        )}
                      </p>
                    </div>
                    {user.avatar_url && (
                      <a
                        href={user.avatar_url}
                        target="_blank"
                        rel="noreferrer"
                        className="rounded-md border border-(--primary-main)/(--opacity-subtle) bg-(--primary-main)/(--opacity-subtle) p-(--space-4) transition-colors hover:bg-(--primary-main)/(--opacity-subtle)"
                      >
                        <p className="mb-1 text-xs font-bold uppercase tracking-widest text-[--primary-main]">
                          {t("messenger:avatar", "Avatar")}
                        </p>
                        <p className="text-sm font-bold text-[--primary-main]">
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
      )}
    </AnimatePresence>
  )
}
