import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"

const NewsDetail = lazy(() => import("@/pages/NewsDetail"))

export const Route = createFileRoute("/_auth/news/$id")({
  component: NewsDetail,
})
