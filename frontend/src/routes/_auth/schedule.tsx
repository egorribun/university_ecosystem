import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import * as v from "valibot"
import { scheduleGroupsQueryOptions } from "@/api/hooks/schedule"
import { scheduleSearchSchema } from "@/features/schedule/schema"

const Schedule = lazy(() => import("@/pages/Schedule"))

export const Route = createFileRoute("/_auth/schedule")({
  // Wave 130 SW2 — partial SSR via /groups prefetch only.
  // Inherits parent _auth.tsx ssr:true (W128 SW2). Schedule.tsx is
  // verified SSR-safe per W130 plan exploration: all browser APIs
  // (IntersectionObserver, ResizeObserver, document.getElementById,
  // scrollIntoView, focus-trap) are guarded inside useEffect or
  // run only in conditionally-rendered dialogs.
  //
  // Loader prefetches only GET /groups (auth-only, no group_id needed).
  // Lessons fetch client-side post-hydration once useScheduleData's
  // auto-select effect resolves user.group_id from /users/me cache.
  // Full lessons SSR deferred to W131+ (needs server-side cookie
  // forwarding for /users/me prefetch — own scope per W125 design).
  validateSearch: (search: Record<string, unknown>) => v.parse(scheduleSearchSchema, search),
  loader: async ({ context }) =>
    Promise.allSettled([context.queryClient.ensureQueryData(scheduleGroupsQueryOptions())]),
  component: Schedule,
})
