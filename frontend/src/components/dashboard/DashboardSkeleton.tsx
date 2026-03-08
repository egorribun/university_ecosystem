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
        <Skeleton width="12.5rem" height="2rem" ariaLabel="Loading greeting" />
        <Skeleton width="7.5rem" height="1.25rem" ariaLabel="Loading time" />
      </div>

      {/* Stories row */}
      <div className="mb-8 flex gap-4 overflow-hidden">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} width="5rem" height="5rem" rounded="50%" ariaLabel="Loading story" />
        ))}
      </div>

      {/* Cards grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {/* Schedule Card Skeleton */}
        <Card className="p-5">
          <Skeleton width="60%" height="1.5rem" className="mb-4" />
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3">
                <Skeleton width="3rem" height="3rem" rounded="lg" />
                <div className="flex-1 space-y-2">
                  <Skeleton width="80%" height="1rem" />
                  <Skeleton width="50%" height="0.75rem" />
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* News Card Skeleton */}
        <Card className="p-5">
          <Skeleton width="50%" height="1.5rem" className="mb-4" />
          <div className="space-y-3">
            {Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="space-y-2">
                <Skeleton width="100%" height="1rem" />
                <Skeleton width="70%" height="0.75rem" />
              </div>
            ))}
          </div>
        </Card>

        {/* Events Card Skeleton */}
        <Card className="p-5">
          <Skeleton width="55%" height="1.5rem" className="mb-4" />
          <div className="space-y-3">
            {Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3">
                <Skeleton width="3.75rem" height="3.75rem" rounded="xl" />
                <div className="flex-1 space-y-2">
                  <Skeleton width="90%" height="1rem" />
                  <Skeleton width="40%" height="0.75rem" />
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Weather widget placeholder */}
      <div className="mt-8">
        <Card className="inline-flex items-center gap-3 p-4">
          <Skeleton width="3rem" height="3rem" rounded="full" />
          <div className="space-y-2">
            <Skeleton width="5rem" height="1.25rem" />
            <Skeleton width="6.25rem" height="0.875rem" />
          </div>
        </Card>
      </div>
    </div>
  )
}

export default memo(DashboardSkeleton)
