import { createFileRoute } from "@tanstack/react-router"
import { lazy, Suspense } from "react"
import { FeatureErrorBoundary } from "@/components/error"

const EventDetail = lazy(() => import("@/pages/EventDetail"))

function EventDetailRoute() {
  return (
    <FeatureErrorBoundary>
      <Suspense
        fallback={
          <div className="events-theme flex min-h-(--h-hero-md) w-full items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand border-t-transparent" />
          </div>
        }
      >
        <EventDetail />
      </Suspense>
    </FeatureErrorBoundary>
  )
}

export const Route = createFileRoute("/_auth/events/$id")({
  component: EventDetailRoute,
})
