import { memo } from "react"
import { Skeleton } from "@/components/ui"

const NewsCardSkeleton = () => {
  return (
    <article
      className="relative flex h-full flex-col overflow-hidden rounded-2xl border border-white/12 bg-input-mix text-(--text-primary) shadow-surface"
      style={{ maxWidth: "500px", width: "100%" }}
    >
      <Skeleton width="100%" height="220px" className="h-[180px] sm:h-[220px]" aria-hidden />
      <div className="flex flex-1 flex-col gap-4 px-4 py-5 sm:px-5 sm:py-6">
        <Skeleton width="75%" height={20} aria-hidden />
        <div className="space-y-3">
          <Skeleton width="100%" height={14} aria-hidden />
          <Skeleton width="92%" height={14} aria-hidden />
          <Skeleton width="83%" height={14} aria-hidden />
        </div>
        <Skeleton className="mt-auto" width="33%" height={16} aria-hidden />
      </div>
    </article>
  )
}

export default memo(NewsCardSkeleton)
