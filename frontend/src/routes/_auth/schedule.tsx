import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import * as v from "valibot"
import { scheduleSearchSchema } from "@/features/schedule/schema"

const Schedule = lazy(() => import("@/pages/Schedule"))

export const Route = createFileRoute("/_auth/schedule")({
  validateSearch: (search: Record<string, unknown>) => v.parse(scheduleSearchSchema, search),
  component: Schedule,
})
