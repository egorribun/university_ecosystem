import { memo } from "react"
import { Skeleton, Card } from "@/components/ui"
import { cn } from "@/utils/cn"

interface DashboardSectionSkeletonProps {
  type: "schedule" | "news" | "events"
  className?: string
}

export const DashboardSectionSkeleton = memo(function DashboardSectionSkeleton({
  type,
  className,
}: DashboardSectionSkeletonProps) {
  return (
    <Card className={cn("card-matte glass-noise p-6 h-full", className)}>
      <Skeleton width="55%" height="1.5rem" className="mb-5" />

      <div className="space-y-3">
        {type === "schedule" && (
          <>
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="flex flex-col gap-2 rounded-xl bg-(--bg-matte-list) px-4 py-3"
              >
                <div className="flex items-center gap-2">
                  <Skeleton width="5rem" height="1rem" />
                  <Skeleton width="7.5rem" height="1.25rem" />
                </div>
                <Skeleton width="45%" height="0.75rem" />
              </div>
            ))}
          </>
        )}

        {type === "news" && (
          <>
            {Array.from({ length: 2 }).map((_, i) => (
              <div
                key={i}
                className="flex items-start gap-4 rounded-xl bg-(--bg-matte-list) px-4 py-3"
              >
                <Skeleton width="2.75rem" height="2.75rem" rounded="9999rem" className="shrink-0" />
                <div className="flex-1 space-y-2">
                  <Skeleton width="90%" height="1.125rem" />
                  <Skeleton width="60%" height="0.875rem" />
                </div>
              </div>
            ))}
          </>
        )}

        {type === "events" && (
          <>
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="flex flex-col gap-2 rounded-xl bg-(--bg-matte-list) px-4 py-3"
              >
                <Skeleton width="80%" height="1rem" />
                <div className="flex items-center gap-2">
                  <Skeleton width="7.5rem" height="0.75rem" />
                  <Skeleton width="5rem" height="0.75rem" />
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </Card>
  )
})

export default DashboardSectionSkeleton
