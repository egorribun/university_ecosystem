import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"

const UserActivity = lazy(() => import("@/pages/Activity"))

export const Route = createFileRoute("/_auth/activity")({
  component: UserActivity,
})
