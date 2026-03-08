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
    <Card className={cn("p-5 h-full", className)}>
      <Skeleton width="55%" height="1.5rem" className="mb-6" />

      <div className="space-y-5">
        {type === "schedule" && (
          <>
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4">
                <Skeleton width="3rem" height="3rem" rounded="sm" />
                <div className="flex-1 space-y-2.5">
                  <Skeleton width="85%" height="1rem" />
                  <Skeleton width="45%" height="0.75rem" />
                </div>
              </div>
            ))}
          </>
        )}

        {type === "news" && (
          <>
            {Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="space-y-3 pb-2">
                <Skeleton width="100%" height="1.125rem" />
                <Skeleton width="90%" height="1.125rem" />
                <Skeleton width="60%" height="0.875rem" />
              </div>
            ))}
          </>
        )}

        {type === "events" && (
          <>
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4">
                <Skeleton width="3.5rem" height="3.5rem" rounded="0.875rem" />
                <div className="flex-1 space-y-2.5">
                  <Skeleton width="92%" height="1rem" />
                  <Skeleton width="40%" height="0.75rem" />
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
