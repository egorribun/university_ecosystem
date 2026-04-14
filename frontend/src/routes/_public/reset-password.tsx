import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"

const ResetPassword = lazy(() => import("@/pages/ResetPassword"))

export const Route = createFileRoute("/_public/reset-password")({
  component: ResetPassword,
})
