import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import * as v from "valibot"
import { newsSearchSchema } from "@/features/news/schema"

const News = lazy(() => import("@/pages/News"))

export const Route = createFileRoute("/_auth/news/")({
  validateSearch: (search: Record<string, unknown>) => v.parse(newsSearchSchema, search),
  component: News,
})
