import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_admin")({
  beforeLoad: ({ context }) => {
    if (context.auth.loading) return
    if (!context.auth.isAuth) {
      throw redirect({ to: "/login" })
    }
    if (!context.auth.user || context.auth.user.role !== "admin") {
      throw redirect({ to: "/dashboard" })
    }
  },
  component: () => <Outlet />,
})
