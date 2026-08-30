import { type FC } from "react"
import { ContentCard, Skeleton } from "@/components/ui"

export const EventCardSkeleton: FC = () => {
  return (
    <ContentCard className="card-glass w-full rounded-fluid-lg">
      <ContentCard.Body className="p-fluid-card-p flex flex-col h-full">
        {/* Media Skeleton */}
        <div className="mb-4">
          <Skeleton
            // Keep the fallback geometry identical to EventCardView's
            // responsive hero (h-48 / sm:h-52). The previous fluid height
            // was substantially taller than the rendered card and made the
            // loading grid reserve avoidable space on narrow and desktop
            // viewports.
            className="w-full h-48 sm:h-52 rounded-lg"
          />
        </div>

        {/* Info Skeleton */}
        <div className="space-y-4">
          {/* Title */}
          <Skeleton height="2rem" width="75%" className="mb-2" />

          {/* Speaker */}
          <Skeleton height="1.25rem" width="50%" className="mb-4" />

          {/* Date & Location */}
          <div className="space-y-3 py-2">
            <div className="flex items-center gap-2">
              <Skeleton height="1.25rem" width="1.25rem" rounded="full" />
              <Skeleton height="1.25rem" width="60%" />
            </div>
            <div className="flex items-center gap-2">
              <Skeleton height="1.25rem" width="1.25rem" rounded="full" />
              <Skeleton height="1.25rem" width="40%" />
            </div>
          </div>

          <div className="my-3 h-px bg-linear-to-r from-transparent via-event-divider/(--opacity-dim) to-transparent" />

          {/* Description */}
          <div className="space-y-2 mb-4">
            <Skeleton height="1rem" className="w-full" />
            <Skeleton height="1rem" className="w-full" />
            <Skeleton height="1rem" className="w-2/3" />
          </div>
        </div>

        {/* Action Skeleton */}
        <div className="mt-auto pt-6 flex gap-3">
          <Skeleton height="3rem" className="flex-1 rounded-xl" />
          <Skeleton height="3rem" width="3rem" className="rounded-xl" />
        </div>
      </ContentCard.Body>
    </ContentCard>
  )
}
