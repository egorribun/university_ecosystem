import SmartImage from "@/components/media/SmartImage"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import { parseCacheVersion } from "@/utils/cache"
import { useMemo } from "react"
import type { User } from "@/types/User"

interface MobileDrawerProfileProps {
  user: User
  onProfileClick: () => void
  t: (key: string) => string
}

export function MobileDrawerProfile({ user, onProfileClick, t }: MobileDrawerProfileProps) {
  const avatarCacheV = useMemo(() => {
    const raw = user.avatar_updated_at ?? user.avatar_version ?? user.updated_at ?? undefined
    return parseCacheVersion(raw)
  }, [user])

  const avatarSource = user.avatar_url || ""
  const hasAvatar = Boolean(avatarSource)
  const roleKey = user.role === "admin" ? "admin" : user.role === "teacher" ? "teacher" : "student"

  return (
    <button
      type="button"
      onClick={onProfileClick}
      className="flex w-full items-center gap-4 rounded-2xl border-none p-4 text-left transition-[transform,opacity,background-color] duration-200 hover:bg-(--bg-surface-hover)/(--opacity-soft) cursor-pointer"
      style={{
        background: "linear-gradient(135deg, var(--quick-action-icon-bg), transparent 60%)",
      }}
      aria-label={t("navigation:aria.openProfile")}
    >
      {/* Avatar with gradient ring */}
      <div className="relative shrink-0">
        <div
          className="absolute -inset-0.5 rounded-full"
          style={{ background: "var(--drawer-accent-gradient)" }}
          aria-hidden="true"
        />
        <SmartImage
          srcRaw={hasAvatar ? avatarSource : AVATAR_PLACEHOLDER_URL}
          cacheV={hasAvatar ? avatarCacheV : undefined}
          fallback={AVATAR_PLACEHOLDER_URL}
          alt={user.full_name || t("navigation:aria.profileAvatar")}
          className="relative block h-12 w-12 rounded-full border-2 border-(--bg-surface) object-cover shadow-sm"
        />
      </div>
      <div className="flex flex-col min-w-0">
        <span className="font-bold text-base text-(--text-primary) truncate">{user.full_name}</span>
        {user.role && (
          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-(--text-secondary) mt-0.5">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-(--nav-active-color)" />
            {t(`navigation:role.${roleKey}`)}
          </span>
        )}
      </div>
    </button>
  )
}
