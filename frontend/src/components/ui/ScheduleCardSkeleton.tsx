import { memo } from "react"
import { useTranslation } from "react-i18next"
import { Skeleton } from "@/components/ui/Skeleton"

interface ScheduleCardSkeletonProps {
  /** Number of lesson items to show in skeleton */
  items?: number
  /** Optional CSS class */
  className?: string
}

/**
 * ScheduleCardSkeleton - Loading state for ScheduleCard component.
 * Displays placeholder lesson items matching the real component structure.
 */
function ScheduleCardSkeletonInner({ items = 3, className = "" }: ScheduleCardSkeletonProps) {
  const { t } = useTranslation()
  return (
    <div
      className={`rounded-2xl border border-glass-border-subtle bg-glass-elevated p-4 sm:p-5 ${className}`}
      aria-busy="true"
      aria-label={t("common:aria.loadingSchedule")}
    >
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <Skeleton width={140} height={24} ariaLabel={t("common:aria.loadingDate")} />
        <Skeleton width={80} height={20} />
      </div>

      {/* Lesson items */}
      <div className="space-y-3">
        {Array.from({ length: items }).map((_, index) => (
          <div
            key={`skeleton-${index}`}
            className="flex items-start gap-3 rounded-lg border border-glass-border-subtle/(--opacity-medium) bg-black/(--opacity-faint) dark:bg-black/(--opacity-dim) p-3"
          >
            {/* Time column */}
            <div className="flex flex-col items-center gap-1">
              <Skeleton width={40} height={14} />
              <Skeleton width={36} height={12} />
            </div>

            {/* Divider */}
            <div className="h-12 w-0.5 bg-glass-border-subtle/(--opacity-medium)" />

            {/* Content */}
            <div className="flex flex-1 flex-col gap-2">
              <Skeleton width="75%" height={16} ariaLabel={t("common:aria.loadingSubject")} />
              <div className="flex items-center gap-2">
                <Skeleton width={12} height={12} rounded="50%" />
                <Skeleton width="45%" height={12} />
              </div>
              <div className="flex items-center gap-2">
                <Skeleton width={12} height={12} rounded="50%" />
                <Skeleton width="30%" height={12} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export const ScheduleCardSkeleton = memo(ScheduleCardSkeletonInner)

export default ScheduleCardSkeleton
