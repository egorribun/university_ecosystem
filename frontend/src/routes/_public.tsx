import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_public")({
  beforeLoad: ({ context }) => {
    if (context.auth.loading) return
    if (context.auth.isAuth) {
      throw redirect({ to: "/dashboard" })
    }
  },
  component: () => <Outlet />,
})
