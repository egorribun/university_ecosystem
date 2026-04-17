import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import * as v from "valibot"
import { activitySearchSchema } from "@/features/activity/schema"

const UserActivity = lazy(() => import("@/pages/Activity"))

export const Route = createFileRoute("/_auth/activity")({
  validateSearch: (search: Record<string, unknown>) => v.parse(activitySearchSchema, search),
  component: UserActivity,
})
