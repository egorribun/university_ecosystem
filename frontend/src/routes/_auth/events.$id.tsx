import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"

const EventDetail = lazy(() => import("@/pages/EventDetail"))

export const Route = createFileRoute("/_auth/events/$id")({
  component: EventDetail,
})
