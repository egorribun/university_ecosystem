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
      <Skeleton width="55%" height={24} className="mb-6" />

      <div className="space-y-5">
        {type === "schedule" && (
          <>
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4">
                <Skeleton width={48} height={48} rounded="12px" />
                <div className="flex-1 space-y-2.5">
                  <Skeleton width="85%" height={16} />
                  <Skeleton width="45%" height={12} />
                </div>
              </div>
            ))}
          </>
        )}

        {type === "news" && (
          <>
            {Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="space-y-3 pb-2">
                <Skeleton width="100%" height={18} />
                <Skeleton width="90%" height={18} />
                <Skeleton width="60%" height={14} />
              </div>
            ))}
          </>
        )}

        {type === "events" && (
          <>
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4">
                <Skeleton width={56} height={56} rounded="14px" />
                <div className="flex-1 space-y-2.5">
                  <Skeleton width="92%" height={16} />
                  <Skeleton width="40%" height={12} />
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
