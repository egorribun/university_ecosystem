import { createFileRoute } from "@tanstack/react-router"
import { lazy, Suspense } from "react"

import { eventDetailQueryOptions } from "@/api/hooks/events"
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
  // Wave 129 SW2 — per-route SSR enabled. Inherits `_auth.tsx` ssr:true
  // (W128 SW2). Loader pre-fetches the event by id into per-request
  // QueryClient so the SSR HTML emits with hero + body + about content
  // populated rather than skeleton. `eventDetailQueryOptions` is the
  // pure factory extracted alongside in events.ts SW2.
  loader: async ({ context, params }) => {
    // Promise.allSettled — best-effort prefetch; backend-down doesn't
    // crash the loader → no NO_FCP. EventDetail's own useQuery refetches
    // on mount with normal error handling (cached or error UI).
    await Promise.allSettled([
      context.queryClient.ensureQueryData(eventDetailQueryOptions(params.id)),
    ])
  },
  component: EventDetailRoute,
})
