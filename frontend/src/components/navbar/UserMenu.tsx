import { useMemo } from "react"
import NotificationsBell from "@/components/feedback/NotificationsBell"
import MessengerButton from "@/components/layout/MessengerButton"
import SmartImage from "@/components/media/SmartImage"
import { Settings as SettingsIcon } from "lucide-react"
import { type User } from "@/types/User"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import { parseCacheVersion } from "@/utils/cache"
import { Skeleton } from "@/components/ui"
import { cn } from "@/utils/cn"

interface UserMenuProps {
  user: User | null
  isAuth: boolean
  loading: boolean
  go: (to: string) => void
  t: (key: string) => string
  isCompact?: boolean
  prefersReducedMotion?: boolean
}

/**
 * UserMenu — all transitions use CSS only.
 * Every child shares 500ms ease-premium timing with the pill container.
 */
export const UserMenu = ({
  user,
  isAuth,
  loading,
  go,
  t,
  isCompact = false,
  prefersReducedMotion = false,
}: UserMenuProps) => {
  const avatarCacheV = useMemo(() => {
    const raw = user?.avatar_updated_at ?? user?.avatar_version ?? user?.updated_at ?? undefined
    return parseCacheVersion(raw)
  }, [user])

  const avatarSource = user?.avatar_url || ""
  const hasAvatar = Boolean(avatarSource)
  const profileAlt = user?.full_name
    ? t("navigation:aria.profileAvatarNamed")
    : t("navigation:aria.profileAvatar")
  const profileTitle = t("navigation:aria.openProfile")

  const dur = prefersReducedMotion ? "duration-0" : "duration-500"
  const ease = "ease-[var(--ease-premium)]"

  if (loading) {
    return (
      <div
        className="ml-auto flex items-center gap-3"
        role="status"
        aria-busy="true"
        aria-label={t("common:aria.loadingUserMenu")}
      >
        <Skeleton className="rounded-full w-9 h-9 bg-brand/(--opacity-dim)" />
        {!isCompact && <Skeleton className="w-24 h-5 rounded-md bg-brand/(--opacity-dim)" />}
      </div>
    )
  }

  if (!isAuth || !user) return null

  return (
    <div
      className={cn(
        "ml-auto flex min-w-0 items-center whitespace-nowrap",
        "transition-[transform,opacity]",
        dur,
        ease,
        isCompact ? "gap-2" : "gap-3"
      )}
    >
      <MessengerButton />
      <NotificationsBell />

      <div
        className={cn(
          "flex items-center",
          "transition-[transform,opacity]",
          dur,
          ease,
          isCompact ? "gap-2 ml-1 h-8" : "gap-3 ml-3 h-10"
        )}
      >
        <button
          type="button"
          className={cn(
            "flex size-11 shrink-0 items-center justify-center rounded-full border-none bg-transparent p-0",
            "transition-[transform,opacity]",
            dur,
            ease,
            !prefersReducedMotion && "hover:scale-105 active:scale-95"
          )}
          onClick={() => go("/profile")}
          aria-label={profileTitle}
          title={profileTitle}
        >
          <SmartImage
            srcRaw={hasAvatar ? avatarSource : AVATAR_PLACEHOLDER_URL}
            cacheV={hasAvatar ? avatarCacheV : undefined}
            fallback={AVATAR_PLACEHOLDER_URL}
            alt={profileAlt}
            className={cn(
              "pointer-events-none block rounded-full border border-(--border-subtle) bg-(--bg-surface-raised) object-cover",
              isCompact ? "h-7 w-7" : "h-9 w-9"
            )}
          />
        </button>

        {/* User name — instant hide/show, no visible fade */}
        <div
          className={cn(
            "overflow-hidden",
            isCompact ? "max-w-0 opacity-0" : "max-w-48 opacity-100"
          )}
        >
          <button
            type="button"
            onClick={() => go("/profile")}
            aria-label={profileTitle}
            title={profileTitle}
            className="m-0 min-h-11 cursor-pointer whitespace-nowrap border-none bg-transparent p-0 font-bold tracking-tight text-base text-text-primary transition-colors hover:text-brand"
          >
            {user.full_name}
          </button>
        </div>

        {/* Settings gear — smooth rotation with will-change */}
        <button
          id="navbar-settings-btn"
          type="button"
          className={cn(
            "flex items-center justify-center rounded-2xl text-text-primary cursor-pointer border-none",
            "size-11 transition-[transform,opacity,background-color]",
            dur,
            ease,
            "hover:bg-(--bg-surface-hover)/(--opacity-soft)",
            !prefersReducedMotion && "hover:scale-105 active:scale-95"
          )}
          onClick={() => go("/settings")}
          aria-label={t("navigation:menu.settings")}
          title={t("navigation:menu.settings")}
        >
          <SettingsIcon
            className={cn("transition-[transform,opacity]", isCompact ? "h-4 w-4" : "h-5 w-5")}
          />
        </button>
      </div>
    </div>
  )
}
