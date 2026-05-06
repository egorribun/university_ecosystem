import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import * as v from "valibot"
import { newsSearchSchema } from "@/features/news/schema"

const News = lazy(() => import("@/pages/News"))

export const Route = createFileRoute("/_auth/news/")({
  // Wave 128 SW2 — explicit opt-down (W129+ candidate after SSR audit;
  // /news is content-heavy, prime SSR candidate for next per-route enable).
  ssr: false,
  validateSearch: (search: Record<string, unknown>) => v.parse(newsSearchSchema, search),
  component: News,
})
