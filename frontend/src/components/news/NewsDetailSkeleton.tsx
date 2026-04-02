import { Skeleton } from "@/components/ui"
import { NewsBackdrop } from "./NewsBackdrop"

interface NewsDetailSkeletonProps {
  isNarrow: boolean
  prefersReducedMotion: boolean
}

export function NewsDetailSkeleton({ isNarrow, prefersReducedMotion }: NewsDetailSkeletonProps) {
  return (
    <div className="news-theme aurora-mesh relative min-h-screen">
      <NewsBackdrop isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />
      <div className="relative z-base px-4 sm:px-6 md:px-10 lg:px-14 py-8">
        <div className="max-w-4xl space-y-6">
          <Skeleton width="6rem" height="2.5rem" rounded="9999rem" />
          <Skeleton width="65%" height="2.75rem" />
          <div className="flex flex-wrap gap-3">
            <Skeleton width="10rem" height="1.75rem" rounded="9999rem" />
            <Skeleton width="7rem" height="1.75rem" rounded="9999rem" />
          </div>
          <div className="rounded-2xl overflow-hidden glass-layer-elevated glass-noise">
            <Skeleton className="w-full" height="22rem" rounded={false} />
          </div>
          <div className="glass-layer-surface glass-noise rounded-2xl p-8 space-y-4">
            <Skeleton width="100%" height="1rem" />
            <Skeleton width="96%" height="1rem" />
            <Skeleton width="90%" height="1rem" />
            <Skeleton width="80%" height="1rem" />
          </div>
        </div>
      </div>
    </div>
  )
}
