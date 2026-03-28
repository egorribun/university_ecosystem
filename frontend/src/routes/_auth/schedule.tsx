import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"

const Schedule = lazy(() => import("@/pages/Schedule"))

export const Route = createFileRoute("/_auth/schedule")({
  component: Schedule,
})
