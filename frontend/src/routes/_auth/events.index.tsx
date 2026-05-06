import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import * as v from "valibot"

const Events = lazy(() => import("@/pages/Events"))

export const Route = createFileRoute("/_auth/events/")({
  // Wave 128 SW2 — explicit opt-down (W129+ candidate after SSR audit;
  // /events is content-heavy, prime SSR candidate after /news + /dashboard).
  ssr: false,
  validateSearch: (search: Record<string, unknown>) =>
    v.parse(
      v.object({
        tab: v.optional(v.string()),
        q: v.optional(v.string()),
        dr: v.optional(v.string()),
        loc: v.optional(v.string()),
        sort: v.optional(v.string()),
        cat: v.optional(v.string()),
      }),
      search
    ),
  component: Events,
})
