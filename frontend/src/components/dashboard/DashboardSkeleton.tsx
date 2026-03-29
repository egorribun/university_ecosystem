import { Skeleton, Card } from "@/components/ui"

/**
 * DashboardSkeleton - Full-page loading state for the Dashboard.
 * Wave 45: Matte glass skeleton matching the real dashboard aesthetic.
 */
export function DashboardSkeleton() {
  return (
    <div
      className="flex min-h-screen w-full flex-col px-4 pb-16 pt-10 sm:px-8 md:px-12 lg:px-16"
      style={{
        background: "linear-gradient(145deg, var(--hero-grad-start), var(--hero-grad-end))",
      }}
    >
      {/* Header area — matches hero card */}
      <div className="card-matte glass-noise mb-8 space-y-3 rounded-2xl p-6 md:p-10">
        <Skeleton width="14rem" height="2.25rem" ariaLabel="Loading greeting" />
        <div className="flex items-center gap-3">
          <Skeleton width="5rem" height="1.5rem" rounded="9999rem" ariaLabel="Loading time" />
          <Skeleton width="4rem" height="1.25rem" ariaLabel="Loading weather" />
          <Skeleton width="8rem" height="1rem" ariaLabel="Loading date" />
        </div>
      </div>

      {/* Stories row */}
      <div className="mb-8 flex gap-4 overflow-hidden">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} width="5rem" height="5rem" rounded="50%" ariaLabel="Loading story" />
        ))}
      </div>

      {/* Cards grid — matte glass cards */}
      <div className="grid gap-5 md:gap-6 md:grid-cols-2 lg:grid-cols-3 lg:gap-7">
        {/* Schedule Card Skeleton */}
        <Card className="card-matte glass-noise p-6">
          <Skeleton width="60%" height="1.5rem" className="mb-5" />
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex flex-col gap-2 rounded-xl bg-(--bg-matte-list) px-4 py-3">
                <div className="flex items-center gap-2">
                  <Skeleton width="5rem" height="1.125rem" />
                  <Skeleton width="7.5rem" height="1.25rem" />
                </div>
                <Skeleton width="60%" height="0.875rem" />
              </div>
            ))}
          </div>
        </Card>

        {/* News Card Skeleton */}
        <Card className="card-matte glass-noise p-6">
          <Skeleton width="50%" height="1.5rem" className="mb-5" />
          <div className="space-y-3">
            {Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="flex items-start gap-4 rounded-xl bg-(--bg-matte-list) px-4 py-3">
                <Skeleton width="2.75rem" height="2.75rem" rounded="9999rem" className="shrink-0" />
                <div className="flex-1 space-y-2">
                  <Skeleton width="90%" height="1rem" />
                  <Skeleton width="70%" height="0.875rem" />
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Events Card Skeleton */}
        <Card className="card-matte glass-noise p-6">
          <Skeleton width="55%" height="1.5rem" className="mb-5" />
          <div className="mb-4 flex gap-2">
            <Skeleton width="4rem" height="2rem" rounded="0.75rem" />
            <Skeleton width="4rem" height="2rem" rounded="0.75rem" />
          </div>
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex flex-col gap-2 rounded-xl bg-(--bg-matte-list) px-4 py-3">
                <Skeleton width="80%" height="1rem" />
                <div className="flex items-center gap-2">
                  <Skeleton width="7.5rem" height="0.875rem" />
                  <Skeleton width="5rem" height="0.875rem" />
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}

// PERF-27-02: Removed React.memo() — React Compiler "infer" mode handles memoization
export default DashboardSkeleton
