import { memo } from "react"

const NewsCardSkeleton = () => {
  return (
    <article className="relative flex h-full w-full flex-col overflow-hidden rounded-ue-xl border border-white/12 bg-[color:color-mix(in_srgb,var(--card-bg)_94%,white_6%)] text-[color:var(--page-text)] shadow-surface">
      <div className="h-[180px] w-full animate-skeleton-wave bg-skeleton sm:h-[220px]" aria-hidden />
      <div className="flex flex-1 flex-col gap-4 px-4 py-5 sm:px-5 sm:py-6">
        <div className="h-5 w-3/4 rounded-md animate-skeleton-wave bg-skeleton" aria-hidden />
        <div className="space-y-3">
          <div className="h-[14px] w-full rounded-md animate-skeleton-wave bg-skeleton" aria-hidden />
          <div className="h-[14px] w-11/12 rounded-md animate-skeleton-wave bg-skeleton" aria-hidden />
          <div className="h-[14px] w-5/6 rounded-md animate-skeleton-wave bg-skeleton" aria-hidden />
        </div>
        <div className="mt-auto h-4 w-1/3 rounded-md animate-skeleton-wave bg-skeleton" aria-hidden />
      </div>
    </article>
  )
}

export default memo(NewsCardSkeleton)
