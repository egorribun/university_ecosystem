import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"

const Settings = lazy(() => import("@/pages/Settings"))

export const Route = createFileRoute("/_auth/settings")({
  component: Settings,
})
