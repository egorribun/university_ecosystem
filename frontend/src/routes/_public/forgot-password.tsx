import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"

const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"))

export const Route = createFileRoute("/_public/forgot-password")({
  component: ForgotPassword,
})
