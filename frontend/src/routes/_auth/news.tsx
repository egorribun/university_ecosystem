import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"

const News = lazy(() => import("@/pages/News"))

export const Route = createFileRoute("/_auth/news")({
  component: News,
})
