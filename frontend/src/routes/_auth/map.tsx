import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import * as v from "valibot"
import { mapSearchSchema } from "@/features/map/schema"

const MapPage = lazy(() => import("@/pages/Map"))

export const Route = createFileRoute("/_auth/map")({
  validateSearch: (search: Record<string, unknown>) => v.parse(mapSearchSchema, search),
  component: MapPage,
})
