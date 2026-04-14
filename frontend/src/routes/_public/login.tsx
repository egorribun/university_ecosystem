import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import * as v from "valibot"

const Login = lazy(() => import("@/pages/Login"))

export const Route = createFileRoute("/_public/login")({
  validateSearch: (search: Record<string, unknown>) =>
    v.parse(
      v.object({
        redirect: v.optional(v.string()),
      }),
      search
    ),
  component: Login,
})
