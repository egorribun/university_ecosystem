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
        "transition-[gap]",
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
          "transition-[gap,padding,height]",
          dur,
          ease,
          isCompact ? "gap-2 ml-1 h-8" : "gap-3 ml-3 h-10"
        )}
      >
        {/* Avatar — premium ring glow on hover */}
        <SmartImage
          srcRaw={hasAvatar ? avatarSource : AVATAR_PLACEHOLDER_URL}
          cacheV={hasAvatar ? avatarCacheV : undefined}
          fallback={AVATAR_PLACEHOLDER_URL}
          alt={profileAlt}
          title={profileTitle}
          className={cn(
            "block cursor-pointer rounded-full border bg-(--bg-surface-raised) object-cover",
            "transition-[width,height,box-shadow,transform]",
            dur,
            ease,
            isCompact ? "h-7 w-7" : "h-9 w-9",
            "border-(--border-subtle)",
            "hover:shadow-[var(--avatar-ring-glow)]",
            !prefersReducedMotion && "hover:scale-105 active:scale-95"
          )}
          onClick={() => go("/profile")}
        />

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
            className="cursor-pointer border-none bg-transparent p-0 m-0 font-bold text-text-primary tracking-tight text-base hover:text-brand transition-colors whitespace-nowrap"
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
            "transition-[width,height,transform,background]",
            dur,
            ease,
            isCompact ? "w-8 h-8" : "w-10 h-10",
            "hover:bg-(--bg-surface-hover)/(--opacity-soft)",
            !prefersReducedMotion && "hover:rotate-90 hover:scale-110 active:scale-90"
          )}
          style={{ willChange: "transform" }}
          onClick={() => go("/settings")}
          aria-label={t("navigation:menu.settings")}
          title={t("navigation:menu.settings")}
        >
          <SettingsIcon
            className={cn(
              "transition-[width,height]",
              dur,
              ease,
              isCompact ? "h-4 w-4" : "h-5 w-5"
            )}
          />
        </button>
      </div>
    </div>
  )
}
