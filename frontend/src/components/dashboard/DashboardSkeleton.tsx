import { memo } from "react"
import { Skeleton, Card } from "@/components/ui"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"

/**
 * DashboardSkeleton - Full-page loading state for the Dashboard.
 * Wave 45: Matte glass skeleton matching the real dashboard aesthetic.
 * Wave 118 (FIX-118-01): Aligned paddings with DashboardHero and grid to zero out CLS.
 */
export const DashboardSkeleton = memo(function DashboardSkeleton() {
  const isStoriesInHero = useMediaQuery(`(min-width: ${breakpoints.storiesInHero})`)

  return (
    <div
      className="flex min-h-screen w-full flex-col"
      style={{
        background: "linear-gradient(145deg, var(--hero-grad-start), var(--hero-grad-end))",
      }}
    >
      {/* Hero Skeleton area — matches DashboardHero pt and px */}
      <div className="w-full px-4 pt-5 sm:px-6 md:px-10 lg:px-14">
        <div className="card-matte glass-noise mb-8 rounded-2xl p-8 md:p-10">
          <div className="flex flex-col gap-4 min-[1220px]:flex-row min-[1220px]:items-center min-[1220px]:gap-6">
            <div className="shrink-0 space-y-4">
              <Skeleton width="14rem" height="2.25rem" ariaLabel="Loading greeting" />
              <div className="flex items-center gap-3">
                <Skeleton width="5rem" height="1.5rem" rounded="9999rem" ariaLabel="Loading time" />
                <Skeleton width="4rem" height="1.25rem" ariaLabel="Loading weather" />
                <Skeleton width="8rem" height="1rem" ariaLabel="Loading date" />
              </div>
            </div>

            {/* Stories inside hero if desktop */}
            {isStoriesInHero && (
              <div className="flex-1 overflow-hidden pl-4">
                <div className="flex gap-4">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <Skeleton key={i} width="4.5rem" height="4.5rem" rounded="50%" />
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Main content grid area — matches Dashboard.tsx px */}
      <div className="px-4 sm:px-6 md:px-10 lg:px-14">
        {/* Stories below hero if mobile/tablet */}
        {!isStoriesInHero && (
          <div className="mb-6 flex gap-4 overflow-hidden">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton
                key={i}
                width="5rem"
                height="5rem"
                rounded="50%"
                ariaLabel="Loading story"
              />
            ))}
          </div>
        )}

        {/* Cards grid — aligned with real grid gap and columns */}
        <div className="mt-4 grid w-full grid-cols-12 gap-4 md:mt-5 md:gap-3.5 lg:gap-4">
          {/* Schedule Card Skeleton */}
          <Card className="col-span-12 card-matte glass-noise p-6 lg:col-span-4 min-h-[400px]">
            <Skeleton width="60%" height="1.5rem" className="mb-5" />
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <div
                  key={i}
                  className="flex flex-col gap-2 rounded-xl bg-(--bg-matte-list) px-4 py-3"
                >
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
          <Card className="col-span-12 card-matte glass-noise p-6 lg:col-span-4 min-h-[400px]">
            <Skeleton width="50%" height="1.5rem" className="mb-5" />
            <div className="space-y-3">
              {Array.from({ length: 2 }).map((_, i) => (
                <div
                  key={i}
                  className="flex items-start gap-4 rounded-xl bg-(--bg-matte-list) px-4 py-3"
                >
                  <Skeleton
                    width="2.75rem"
                    height="2.75rem"
                    rounded="9999rem"
                    className="shrink-0"
                  />
                  <div className="flex-1 space-y-2">
                    <Skeleton width="90%" height="1rem" />
                    <Skeleton width="70%" height="0.875rem" />
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {/* Events Card Skeleton */}
          <Card className="col-span-12 card-matte glass-noise p-6 lg:col-span-4 min-h-[400px]">
            <Skeleton width="55%" height="1.5rem" className="mb-5" />
            <div className="mb-4 flex gap-2">
              <Skeleton width="4rem" height="2rem" rounded="0.75rem" />
              <Skeleton width="4rem" height="2rem" rounded="0.75rem" />
            </div>
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <div
                  key={i}
                  className="flex flex-col gap-2 rounded-xl bg-(--bg-matte-list) px-4 py-3"
                >
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
    </div>
  )
})

export default DashboardSkeleton
