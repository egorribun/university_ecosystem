import { memo } from "react"
import { Skeleton } from "@/components/ui"
import { cn } from "@/utils/cn"

interface NewsCardSkeletonProps {
  featured?: boolean
}

export const NewsCardSkeleton = memo(({ featured }: NewsCardSkeletonProps) => {
  return (
    <article
      className={cn(
        "relative flex h-full w-full overflow-hidden rounded-2xl card-matte glass-noise",
        featured ? "lg:flex-row flex-col" : "flex-col"
      )}
    >
      {/* Image area */}
      <div
        className={cn(
          "shrink-0 bg-input-mix",
          featured ? "h-56 sm:h-64 lg:w-[55%] lg:h-auto lg:min-h-[20rem]" : "h-48 sm:h-52"
        )}
      >
        <Skeleton className="h-full w-full" rounded={false} aria-hidden />
      </div>

      {/* Content area */}
      <div
        className={cn(
          "flex flex-1 flex-col gap-4 p-5",
          featured && "sm:p-6 lg:p-8 lg:justify-center"
        )}
      >
        <Skeleton
          width={featured ? "85%" : "70%"}
          height={featured ? "1.5rem" : "1.25rem"}
          aria-hidden
        />

        <div className="space-y-2">
          <Skeleton width="100%" height="0.875rem" aria-hidden />
          <Skeleton width="90%" height="0.875rem" aria-hidden />
          {featured && <Skeleton width="75%" height="0.875rem" aria-hidden />}
        </div>

        <div className="mt-auto flex items-center gap-4 border-t border-glass-border/(--opacity-soft) pt-3">
          <Skeleton width="3rem" height="1rem" aria-hidden />
          <Skeleton width="3rem" height="1rem" aria-hidden />
        </div>
      </div>
    </article>
  )
})

NewsCardSkeleton.displayName = "NewsCardSkeleton"

export default NewsCardSkeleton
