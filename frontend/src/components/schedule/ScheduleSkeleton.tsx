import { Skeleton } from "@/components/ui"

export function ScheduleSkeleton() {
  return (
    <div className="skeleton-morph-container w-full min-h-screen py-8 sm:py-10">
      <div className="px-2 md:px-4">
        {/* Header Skeleton */}
        <div className="mb-6 flex flex-wrap items-center gap-4 sm:gap-5">
          <Skeleton width={48} height={48} rounded="full" />
          <Skeleton width={200} height={40} />
          <Skeleton width={100} height={28} rounded="full" />
        </div>

        {/* Toolbar Skeleton */}
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <Skeleton width={200} height={36} rounded="xl" />
          <Skeleton width={160} height={36} rounded="xl" />
        </div>

        {/* Week Selector Skeleton */}
        <div className="mb-6 flex items-center gap-3">
          <Skeleton width={60} height={20} />
          <Skeleton width={200} height={36} rounded="xl" />
        </div>

        {/* Current Lesson Card Skeleton */}
        <div className="mb-6 max-w-4xl">
          <Skeleton width="100%" height={100} rounded="xl" />
        </div>

        {/* Desktop Grid Skeleton */}
        <div className="hidden md:block">
          <div className="overflow-hidden rounded-xl border border-glass-border bg-surface/(--opacity-medium) p-1 backdrop-blur-md shadow-glass">
            {/* Header row */}
            <div className="mb-1 flex gap-1">
              <Skeleton className="w-14 h-12 shrink-0" rounded="lg" />
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="flex-1 h-12" rounded="lg" />
              ))}
            </div>
            {/* Data rows */}
            <div className="space-y-1">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="flex gap-1">
                  <Skeleton className="w-14 h-28 shrink-0" rounded="lg" />
                  {Array.from({ length: 6 }).map((_, j) => (
                    <Skeleton key={j} className="flex-1 h-28" rounded="xl" />
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Mobile Skeleton */}
        <div className="md:hidden space-y-4">
          {/* Day chips */}
          <div className="flex gap-2 pb-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} width={56} height={32} rounded="full" />
            ))}
          </div>
          {/* Day columns */}
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="space-y-3 rounded-2xl border border-glass-border p-4">
              <Skeleton width={120} height={24} />
              <Skeleton width="100%" height={100} rounded="xl" />
              <Skeleton width="100%" height={100} rounded="xl" />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
