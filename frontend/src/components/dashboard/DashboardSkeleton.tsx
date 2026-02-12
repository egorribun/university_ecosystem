import { memo } from "react"
import { Skeleton, Card } from "@/components/ui"


/**
 * DashboardSkeleton - Full-page loading state for the Dashboard.
 * Mimics the layout of the real dashboard with placeholder elements.
 */
export function DashboardSkeleton() {
  return (
    <div className="flex min-h-screen w-full flex-col px-4 pb-16 pt-10 sm:px-8 md:px-12 lg:px-16">
      {/* Header area */}
      <div className="mb-8 space-y-3">
        <Skeleton width={200} height={32} ariaLabel="Loading greeting" />
        <Skeleton width={120} height={20} ariaLabel="Loading time" />
      </div>

      {/* Stories row */}
      <div className="mb-8 flex gap-4 overflow-hidden">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} width={80} height={80} rounded="50%" ariaLabel="Loading story" />
        ))}
      </div>

      {/* Cards grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {/* Schedule Card Skeleton */}
        <Card className="p-5">
          <Skeleton width="60%" height={24} className="mb-4" />
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3">
                <Skeleton width={48} height={48} rounded="10px" />
                <div className="flex-1 space-y-2">
                  <Skeleton width="80%" height={16} />
                  <Skeleton width="50%" height={12} />
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* News Card Skeleton */}
        <Card className="p-5">
          <Skeleton width="50%" height={24} className="mb-4" />
          <div className="space-y-3">
            {Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="space-y-2">
                <Skeleton width="100%" height={16} />
                <Skeleton width="70%" height={12} />
              </div>
            ))}
          </div>
        </Card>

        {/* Events Card Skeleton */}
        <Card className="p-5">
          <Skeleton width="55%" height={24} className="mb-4" />
          <div className="space-y-3">
            {Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3">
                <Skeleton width={60} height={60} rounded="12px" />
                <div className="flex-1 space-y-2">
                  <Skeleton width="90%" height={16} />
                  <Skeleton width="40%" height={12} />
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Weather widget placeholder */}
      <div className="mt-8">
        <Card className="inline-flex items-center gap-3 p-4">
          <Skeleton width={48} height={48} rounded="50%" />
          <div className="space-y-2">
            <Skeleton width={80} height={20} />
            <Skeleton width={100} height={14} />
          </div>
        </Card>
      </div>
    </div>
  )
}

export default memo(DashboardSkeleton)
