import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"

const ResetPassword = lazy(() => import("@/pages/ResetPassword"))

export const Route = createFileRoute("/_public/reset-password")({
  component: ResetPassword,
  // AUD-178: the reset token must never reach a Referer header from this page.
  head: () => ({ meta: [{ name: "referrer", content: "no-referrer" }] }),
})
