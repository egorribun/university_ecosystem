import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"

const Settings = lazy(() => import("@/pages/Settings"))

export const Route = createFileRoute("/_auth/settings")({
  // Wave 128 SW2 — explicit opt-down (W129+ candidate after audit).
  ssr: false,
  component: Settings,
})
