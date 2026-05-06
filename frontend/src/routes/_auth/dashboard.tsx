import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import { createDashboardEventsQueryOptions } from "@/hooks/useDashboardEvents"
import { createDashboardStoriesQueryOptions } from "@/hooks/useDashboardStories"

const Dashboard = lazy(() => import("@/pages/Dashboard"))

export const Route = createFileRoute("/_auth/dashboard")({
  // Wave 128 SW3 — first per-route SSR enable on the Phase 5 foundation.
  // /dashboard now renders server-side with critical Dashboard queries
  // (events + stories) pre-fetched into per-request QueryClient. Server
  // emits HTML with cards filled with real content (not skeletons) —
  // first authenticated route to deliver visible LCP win on the W125-W127
  // SSR investment (target: 12s → 2-4s LCP).
  //
  // Excluded from prefetch (medium scope per W128 plan):
  //   - News: useInfiniteQuery, requires prefetchInfiniteQuery (different
  //     API + 200-400ms server-time). Stays client-rendered post-hydration.
  //   - Weather: non-Query hook reading localStorage at render time —
  //     would crash SSR. Stays client-only via existing useEffect-gated
  //     mount path.
  //   - Schedule: depends on user.group_id which requires /users/me to
  //     resolve full user (loader has only role from JWT cookie, not
  //     group_id). W129+ may add /users/me to loader for full schedule
  //     SSR; W128 keeps schedule client-side post-hydration.
  ssr: true,
  loader: async ({ context }) => {
    const { queryClient } = context
    // Prefetch in parallel — both queries are independent. ensureQueryData
    // returns cached data if present (idempotent across SSR + client
    // hydration). Server-side: populates routerContext.queryClient cache
    // before render. Client-side (during SPA navigation): same.
    await Promise.all([
      queryClient.ensureQueryData(createDashboardEventsQueryOptions(queryClient)),
      queryClient.ensureQueryData(createDashboardStoriesQueryOptions(queryClient)),
    ])
  },
  component: Dashboard,
})
