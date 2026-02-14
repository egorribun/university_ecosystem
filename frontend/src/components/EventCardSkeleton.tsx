import { memo } from "react"
import { Skeleton } from "@/components/ui/Skeleton"

/**
 * EventCardSkeleton - Loading state for EventCard component.
 * Displays a placeholder with the same dimensions and structure as a real event card.
 */
export function EventCardSkeleton() {
  return (
    <article
      className="relative flex flex-col overflow-hidden rounded-2xl border border-white/(--opacity-subtle) bg-input-mix text-(--text-primary) shadow-surface"
      style={{ width: "100%", maxWidth: "420px" }}
      aria-busy="true"
      aria-label="Loading event"
    >
      {/* Image placeholder */}
      <div
        className="h-[160px] w-full animate-skeleton-wave bg-skeleton sm:h-[180px]"
        aria-hidden
      />

      {/* Content area */}
      <div className="flex flex-1 flex-col gap-3 px-4 py-4 sm:px-5">
        {/* Title */}
        <Skeleton width="70%" height={20} ariaLabel="Loading title" />

        {/* Date/time row */}
        <div className="flex items-center gap-2">
          <Skeleton width={16} height={16} rounded="50%" />
          <Skeleton width="40%" height={14} />
        </div>

        {/* Location row */}
        <div className="flex items-center gap-2">
          <Skeleton width={16} height={16} rounded="50%" />
          <Skeleton width="55%" height={14} />
        </div>

        {/* Description lines */}
        <div className="mt-2 space-y-2">
          <Skeleton width="100%" height={12} />
          <Skeleton width="85%" height={12} />
        </div>

        {/* Action button placeholder */}
        <div className="mt-auto pt-3">
          <Skeleton width={100} height={36} rounded="9999px" />
        </div>
      </div>
    </article>
  )
}

export default memo(EventCardSkeleton)
