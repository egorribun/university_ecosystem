import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"

const MapPage = lazy(() => import("@/pages/Map"))

export const Route = createFileRoute("/_auth/map")({
  component: MapPage,
})
