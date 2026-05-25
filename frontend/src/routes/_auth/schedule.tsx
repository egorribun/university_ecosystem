import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import * as v from "valibot"
import { scheduleGroupsQueryOptions, pageScheduleQueryOptions } from "@/api/hooks/schedule"
import { currentUserQueryOptions } from "@/api/hooks/users"
import { scheduleSearchSchema } from "@/features/schedule/schema"

const Schedule = lazy(() => import("@/pages/Schedule"))

export const Route = createFileRoute("/_auth/schedule")({
  // Wave 130 SW2 / Wave 133 SW3 — full SSR via sequential prefetch chain.
  // Inherits parent _auth.tsx ssr:true (W128 SW2). Schedule.tsx is
  // verified SSR-safe per W130 plan exploration: all browser APIs
  // (IntersectionObserver, ResizeObserver, document.getElementById,
  // scrollIntoView, focus-trap) are guarded inside useEffect or
  // run only in conditionally-rendered dialogs.
  //
  // Phase 1 (parallel): /users/me + /groups. Both prefetches run via
  // ensureQueryData; the underlying axios.get goes through the W133 SW1
  // cookie-forwarding interceptor which injects access_token_v2 from
  // requestCookieStorage on Node SSR.
  //
  // Phase 2 (conditional): if /users/me resolved with a string group_id,
  // prefetch /schedule/{group_id} lessons. Wrapped in .catch(() =>
  // undefined) so a backend hiccup on the lessons endpoint doesn't fail
  // the loader (which would render a blank page); useScheduleData
  // re-fetches client-side on hydration.
  validateSearch: (search: Record<string, unknown>) => v.parse(scheduleSearchSchema, search),
  loader: async ({ context }) => {
    const [userResult] = await Promise.allSettled([
      context.queryClient.ensureQueryData(currentUserQueryOptions()),
      context.queryClient.ensureQueryData(scheduleGroupsQueryOptions()),
    ])
    if (
      userResult.status === "fulfilled" &&
      userResult.value &&
      typeof userResult.value.group_id === "string"
    ) {
      await context.queryClient
        .ensureQueryData(pageScheduleQueryOptions(userResult.value.group_id))
        .catch(() => undefined)
    }
  },
  component: Schedule,
})
