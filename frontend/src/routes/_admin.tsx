import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"
import { useReducedMotion } from "framer-motion"
import { breakpoints } from "@/theme/tokens"
import useMediaQuery from "@/hooks/useMediaQuery"
import { AdminBackdrop } from "@/features/admin/components/AdminBackdrop"

// Wave 150 SW1 — `.admin-theme` scope wrapper + AdminBackdrop on all
// /admin routes (mirrors W84 ActivityFeature pattern). Indigo/slate palette
// scoped via tokens/admin.css. `overflow-x-clip` clips backdrop orbs without
// breaking position: sticky (W77-FIX-77-05 pattern).
function AdminLayout() {
  const prefersReducedMotion = useReducedMotion() ?? false
  const isNarrow = useMediaQuery(`(max-width: ${breakpoints.dashboard})`)
  return (
    <div className="admin-theme relative overflow-x-clip">
      <AdminBackdrop isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />
      <div className="relative z-[1]">
        <Outlet />
      </div>
    </div>
  )
}

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
  component: AdminLayout,
})
