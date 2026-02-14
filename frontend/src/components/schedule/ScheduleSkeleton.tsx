import { Skeleton } from "@/components/ui"

export function ScheduleSkeleton() {
  return (
    <div className="w-screen min-h-screen bg-(--bg-page) py-8 sm:py-10">
      <div className="px-2 md:px-4">
        {/* Header Skeleton */}
        <div className="mb-8 flex flex-wrap items-center gap-4 sm:gap-5">
          <Skeleton width={48} height={48} rounded="full" />
          <Skeleton width={200} height={40} />
        </div>

        {/* Week Selector Skeleton */}
        <div className="mb-6 flex gap-2">
          <Skeleton width={120} height={36} rounded="full" />
          <Skeleton width={120} height={36} rounded="full" />
        </div>

        {/* Current Lesson Card Skeleton (Desktop/Mobile) */}
        <div className="mb-6 max-w-4xl">
          <Skeleton width="100%" height={120} rounded="24px" />
        </div>

        {/* Table/List Skeleton */}
        <div className="hidden md:block">
          {/* Desktop Table Mock */}
          <div className="rounded-2xl border border-white/(--opacity-subtle) bg-(--bg-surface) p-4">
            <div className="flex gap-4 mb-4">
              {Array.from({ length: 7 }).map((_, i) => (
                <Skeleton key={i} className="flex-1 h-10" />
              ))}
            </div>
            <div className="space-y-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex gap-4">
                  {Array.from({ length: 7 }).map((_, j) => (
                    <Skeleton key={j} className="flex-1 h-24" />
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="md:hidden space-y-6">
          {/* Mobile List Mock */}
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="space-y-3">
              <Skeleton width={100} height={24} />
              <Skeleton width="100%" height={100} rounded="24px" />
              <Skeleton width="100%" height={100} rounded="24px" />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
