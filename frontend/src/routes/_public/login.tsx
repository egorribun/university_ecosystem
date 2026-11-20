import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import * as v from "valibot"

import { searchText } from "@/utils/searchParams"

const Login = lazy(() => import("@/pages/Login"))

export const Route = createFileRoute("/_public/login")({
  validateSearch: (search: Record<string, unknown>) =>
    v.parse(
      v.object({
        redirect: searchText(),
      }),
      search
    ),
  component: Login,
})
