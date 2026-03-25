import { Skeleton } from "@/components/ui"

const NewsCardSkeleton = () => {
  return (
    <article className="relative flex h-full w-full max-w-lg flex-col overflow-hidden rounded-md border border-white/(--opacity-subtle) bg-input-mix text-text-primary shadow-surface">
      <Skeleton className="h-56 w-full sm:h-56" aria-hidden />
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

// PERF-27-02: Removed React.memo() — React Compiler "infer" mode handles memoization
export default NewsCardSkeleton
