import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import * as v from "valibot"
import { activitySearchSchema } from "@/features/activity/schema"

const UserActivity = lazy(() => import("@/pages/Activity"))

export const Route = createFileRoute("/_auth/activity")({
  // Wave 127 SW6 — explicit 'data-only' override (same caveat as /map):
  // SILENTLY IGNORED today because parent `_auth.tsx` is `ssr: false`
  // (more restrictive). Annotation preserves intent for W128+ work — when
  // `_auth.tsx` flips, this child stays at `'data-only'` because /activity
  // uses recharts + Framer Motion + html-to-image + jspdf (lazy via W116
  // INFRA-100-04 pattern). Charts + animations rely on browser-only frame-
  // time APIs not safe for SSR component render.
  ssr: "data-only",
  validateSearch: (search: Record<string, unknown>) => v.parse(activitySearchSchema, search),
  component: UserActivity,
})
