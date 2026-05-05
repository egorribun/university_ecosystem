import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_admin")({
  // Wave 126 polish — `ssr: false` overrides root's `ssr: true` for
  // admin routes (same rationale as `_auth.tsx`: provider chain
  // client-only until Phase 5 hoisting).
  ssr: false,
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
