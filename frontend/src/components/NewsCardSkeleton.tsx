import { memo } from "react"
import { Skeleton } from "@/components/ui"

const NewsCardSkeleton = () => {
  return (
    <article
      className="relative flex h-full flex-col overflow-hidden rounded-ue-xl border border-white/12 bg-[color:color-mix(in_srgb,var(--card-bg)_94%,white_6%)] text-[color:var(--page-text)] shadow-surface"
      style={{ maxWidth: "500px", width: "100%" }}
    >
      <Skeleton
        width="100%"
        height="220px"
        className="h-[180px] sm:h-[220px]"
        aria-hidden
      />
      <div className="flex flex-1 flex-col gap-4 px-4 py-5 sm:px-5 sm:py-6">
        <Skeleton width="75%" height={20} rounded="6px" aria-hidden />
        <div className="space-y-3">
          <Skeleton width="100%" height={14} rounded="6px" aria-hidden />
          <Skeleton width="92%" height={14} rounded="6px" aria-hidden />
          <Skeleton width="83%" height={14} rounded="6px" aria-hidden />
        </div>
        <Skeleton
          className="mt-auto"
          width="33%"
          height={16}
          rounded="6px"
          aria-hidden
        />
      </div>
    </article>
  )
}

export default memo(NewsCardSkeleton)
