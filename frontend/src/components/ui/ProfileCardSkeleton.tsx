import { useTranslation } from "react-i18next"
import { memo } from "react"
import { Skeleton } from "@/components/ui/Skeleton"

interface ProfileCardSkeletonProps {
  /** Show cover image skeleton */
  showCover?: boolean
  /** Optional CSS class */
  className?: string
}

/**
 * ProfileCardSkeleton - Loading state for Profile page header.
 * Displays placeholders for avatar, name, bio, and stats.
 */
function ProfileCardSkeletonInner({ showCover = true, className = "" }: ProfileCardSkeletonProps) {
  const { t } = useTranslation()
  return (
    <div
      className={`rounded-2xl border border-white/(--opacity-subtle) bg-input-mix overflow-hidden ${className}`}
      aria-busy="true"
      aria-label={t("common:aria.loadingProfile")}
    >
      {/* Cover image */}
      {showCover && (
        <div
          className="h-32 w-full animate-skeleton-wave bg-skeleton sm:h-40 lg:h-48"
          aria-hidden
        />
      )}

      {/* Profile content */}
      <div className="relative px-4 pb-5 sm:px-6">
        {/* Avatar - positioned to overlap cover */}
        <div className={`${showCover ? "-mt-12" : "mt-4"} mb-4 sm:-mt-16`}>
          <Skeleton
            width={80}
            height={80}
            rounded="50%"
            className="border-4 border-(--bg-surface) sm:h-24 sm:w-24"
            ariaLabel={t("common:aria.loadingAvatar")}
          />
        </div>

        {/* Name and username */}
        <div className="space-y-2 mb-4">
          <Skeleton width={180} height={24} ariaLabel={t("common:aria.loadingName")} />
          <Skeleton width={120} height={16} />
        </div>

        {/* Bio lines */}
        <div className="space-y-2 mb-4">
          <Skeleton width="100%" height={14} />
          <Skeleton width="75%" height={14} />
        </div>

        {/* Stats row */}
        <div className="flex gap-6 pt-3 border-t border-white/(--opacity-subtle)">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex flex-col items-center gap-1">
              <Skeleton width={32} height={20} />
              <Skeleton width={48} height={12} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export const ProfileCardSkeleton = memo(ProfileCardSkeletonInner)

export default ProfileCardSkeleton
