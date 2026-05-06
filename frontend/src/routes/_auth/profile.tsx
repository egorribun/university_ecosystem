import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"

const Profile = lazy(() => import("@/pages/Profile"))

export const Route = createFileRoute("/_auth/profile")({
  // Wave 128 SW2 — explicit opt-down (W129+ candidate after audit).
  ssr: false,
  component: Profile,
})
