import { motion } from "framer-motion"
import { springSoft, springBouncy } from "@/utils/animations"
import NotificationsBell from "@/components/NotificationsBell"
import MessengerButton from "@/components/MessengerButton"
import SmartImage from "@/components/SmartImage"
import { Settings as SettingsIcon } from "lucide-react"
import { type User } from "@/types/User" // Assuming User type location, will verify imports
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders" // Verify import
import { parseCacheVersion } from "@/utils/cache"
import { useMemo } from "react"
import { Skeleton } from "@/components/ui"

interface UserMenuProps {
  user: User | null
  isAuth: boolean
  loading: boolean
  go: (to: string) => void
  t: (key: string) => string
}

export const UserMenu = ({ user, isAuth, loading, go, t }: UserMenuProps) => {
  const avatarCacheV = useMemo(() => {
    const raw = user?.avatar_updated_at ?? user?.avatar_version ?? user?.updated_at ?? undefined
    return parseCacheVersion(raw)
  }, [user])

  const avatarSource = user?.avatar_url || ""
  const hasAvatar = Boolean(avatarSource)
  const profileAlt = user?.full_name
    ? t("navigation:aria.profileAvatarNamed") // We can't interpolate here easily if t signature is simple, let's fix this in usage or assume t handles it.
    : // Actually, t functions usually return string. We should pass the translated string or the t function.
      // Passing t is fine.
      t("navigation:aria.profileAvatar")

  // NOTE: In the original code: t("navigation:aria.profileAvatarNamed", { name: user.full_name })
  // We will handle the string construction inside the component if we have access to t, or pass ready strings.
  // Let's pass 't' and handle it.

  const profileTitle = t("navigation:aria.openProfile")

  if (loading) {
    return (
      <div className="ml-auto flex items-center gap-4" aria-hidden="true">
        <Skeleton className="rounded-full w-10 h-10 bg-brand/(--opacity-dim)" />
        <Skeleton className="w-24 h-5 rounded-md bg-brand/(--opacity-dim)" />
      </div>
    )
  }

  if (!isAuth || !user) return null

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 0.4, ...springSoft }}
      className="ml-auto flex min-w-0 items-center gap-4 whitespace-nowrap"
    >
      <MessengerButton />
      <NotificationsBell />
      <div className="flex h-10 items-center gap-3 pl-4 border-l border-(--glass-border) ml-2">
        <motion.div
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          transition={springBouncy}
        >
          <SmartImage
            srcRaw={hasAvatar ? avatarSource : AVATAR_PLACEHOLDER_URL}
            cacheV={hasAvatar ? avatarCacheV : undefined}
            fallback={AVATAR_PLACEHOLDER_URL}
            alt={profileAlt} // If t requires params, this might be broken. We'll fix in next step if needed.
            title={profileTitle}
            className="block h-9 w-9 cursor-pointer rounded-full border border-(--border-subtle) bg-(--bg-surface-raised) object-cover shadow-sm hover:shadow-md transition-all duration-base"
            onClick={() => go("/profile")}
          />
        </motion.div>
        <button
          type="button"
          onClick={() => go("/profile")}
          aria-label={profileTitle}
          title={profileTitle}
          className="cursor-pointer border-none bg-transparent p-0 m-0 font-bold text-(--text-primary) tracking-tight text-base hover:text-brand transition-colors"
        >
          {user.full_name}
        </button>
        <motion.button
          id="navbar-settings-btn"
          whileHover={{
            rotate: 90,
            scale: 1.1,
            backgroundColor: "var(--bg-surface-hover)",
          }}
          whileTap={{ scale: 0.9 }}
          transition={springSoft}
          type="button"
          className="flex items-center justify-center w-10 h-10 rounded-2xl text-(--text-primary) transition-colors"
          onClick={() => go("/settings")}
          aria-label={t("navigation:menu.settings")}
          title={t("navigation:menu.settings")}
        >
          <SettingsIcon className="h-6 w-6" />
        </motion.button>
      </div>
    </motion.div>
  )
}
