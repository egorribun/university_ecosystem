import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"

const Register = lazy(() => import("@/pages/Register"))

export const Route = createFileRoute("/_public/register")({
  component: Register,
})
