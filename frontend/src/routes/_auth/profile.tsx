import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"

const Profile = lazy(() => import("@/pages/Profile"))

export const Route = createFileRoute("/_auth/profile")({
  component: Profile,
})
