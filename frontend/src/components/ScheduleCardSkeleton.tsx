import { memo } from "react"
import { Skeleton } from "@/components/ui/skeleton"

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
export function ScheduleCardSkeleton({ items = 3, className = "" }: ScheduleCardSkeletonProps) {
  return (
    <div
      className={`rounded-ue-xl border border-white/12 bg-input-mix p-4 sm:p-5 ${className}`}
      aria-busy="true"
      aria-label="Loading schedule"
    >
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <Skeleton width={140} height={24} ariaLabel="Loading date" />
        <Skeleton width={80} height={20} />
      </div>

      {/* Lesson items */}
      <div className="space-y-3">
        {Array.from({ length: items }).map((_, index) => (
          <div
            key={index}
            className="flex items-start gap-3 rounded-lg border border-white/8 bg-black/20 p-3"
          >
            {/* Time column */}
            <div className="flex flex-col items-center gap-1">
              <Skeleton width={40} height={14} />
              <Skeleton width={36} height={12} />
            </div>

            {/* Divider */}
            <div className="h-12 w-[2px] bg-white/10" />

            {/* Content */}
            <div className="flex flex-1 flex-col gap-2">
              <Skeleton width="75%" height={16} ariaLabel="Loading subject" />
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

export default memo(ScheduleCardSkeleton)
