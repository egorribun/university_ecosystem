/**
 * EventDetailSkeleton — loading placeholder matching detail page layout.
 * Pattern source: components/news/NewsDetailSkeleton.tsx
 */

import { EventsBackdrop } from "./EventsBackdrop"

interface EventDetailSkeletonProps {
  isNarrow?: boolean
  prefersReducedMotion?: boolean
}

export function EventDetailSkeleton({
  isNarrow = false,
  prefersReducedMotion = false,
}: EventDetailSkeletonProps) {
  return (
    <div className="events-theme aurora-mesh relative min-h-screen overflow-clip">
      <EventsBackdrop isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />

      <div className="relative z-[1] px-4 sm:px-6 md:px-10 lg:px-14 pb-20 pt-6 sm:pt-8">
        <div className="max-w-4xl 2xl:max-w-5xl space-y-6">
          {/* Back button skeleton */}
          <div className="h-10 w-28 rounded-xl glass-layer-surface animate-pulse" />

          {/* Category badge */}
          <div className="h-6 w-24 rounded-full glass-layer-surface animate-pulse" />

          {/* Title */}
          <div className="space-y-2">
            <div className="h-8 w-[65%] rounded-lg glass-layer-surface animate-pulse" />
            <div className="h-8 w-[40%] rounded-lg glass-layer-surface animate-pulse" />
          </div>

          {/* Meta pills */}
          <div className="flex gap-2">
            <div className="h-8 w-32 rounded-full glass-layer-surface animate-pulse" />
            <div className="h-8 w-40 rounded-full glass-layer-surface animate-pulse" />
            <div className="h-8 w-28 rounded-full glass-layer-surface animate-pulse" />
          </div>

          {/* Hero image placeholder */}
          <div className="w-full aspect-video rounded-2xl glass-layer-elevated glass-noise overflow-hidden animate-pulse" />

          {/* Body content */}
          <div className="space-y-3">
            <div className="h-4 w-[96%] rounded glass-layer-surface animate-pulse" />
            <div className="h-4 w-[90%] rounded glass-layer-surface animate-pulse" />
            <div className="h-4 w-[80%] rounded glass-layer-surface animate-pulse" />
            <div className="h-4 w-[70%] rounded glass-layer-surface animate-pulse" />
          </div>

          {/* Related events skeleton */}
          <div className="pt-8 space-y-4">
            <div className="h-6 w-40 rounded glass-layer-surface animate-pulse" />
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="rounded-xl glass-layer-surface glass-noise overflow-hidden animate-pulse"
                >
                  <div className="h-32 bg-input-mix" />
                  <div className="p-4 space-y-2">
                    <div className="h-4 w-[80%] rounded bg-input-mix" />
                    <div className="h-3 w-[50%] rounded bg-input-mix" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
