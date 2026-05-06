import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import * as v from "valibot"
import { scheduleSearchSchema } from "@/features/schedule/schema"

const Schedule = lazy(() => import("@/pages/Schedule"))

export const Route = createFileRoute("/_auth/schedule")({
  // Wave 128 SW2 — explicit opt-down (W129+ candidate after SSR audit;
  // schedule has heavy interactive calendar UI — needs careful audit
  // before opting in to SSR).
  ssr: false,
  validateSearch: (search: Record<string, unknown>) => v.parse(scheduleSearchSchema, search),
  component: Schedule,
})
