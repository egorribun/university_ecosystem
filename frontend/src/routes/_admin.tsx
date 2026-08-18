import { useEffect, useState } from "react"
import { createFileRoute, Outlet, useNavigate } from "@tanstack/react-router"
import { breakpoints } from "@/theme/tokens"
import useMediaQuery from "@/hooks/useMediaQuery"
import { AdminBackdrop } from "@/features/admin/components/AdminBackdrop"
import { useAuthStore } from "@/stores/useAuthStore"
import { evaluateAdminGuard, getAdminRedirectTarget } from "./guards"

// Wave 150 SW1 — `.admin-theme` scope wrapper + AdminBackdrop on all
// /admin routes (mirrors W84 ActivityFeature pattern). Indigo/slate palette
// scoped via tokens/admin.css. `overflow-x-clip` clips backdrop orbs without
// breaking position: sticky (W77-FIX-77-05 pattern).
//
// W166 SW2 — mounted-state pattern (W156 SW3 LiveRegionProvider canonical
// at frontend/src/components/ui/LiveRegionProvider.tsx:50-115) closes the
// React #418 hydration mismatch caused by `useReducedMotion()` +
// `useMediaQuery()` returning SSR defaults (`false` + `false`) vs CSR
// browser values (e.g., `true` + `true` on mobile). Pre-W166 SW2,
// AdminBackdrop received divergent props across the SSR→CSR boundary:
// SSR rendered all 4 orbs (no conditional skips); CSR on mobile rendered
// only orbs #1 and #3 (skipping #2 highlight + #4 conic drift) → DOM
// subtree mismatch → React #418 with args[]=HTML&args[]= (verified
// Admin smoke sidecar at frontend/.screenshots/admin-visual-smoke/
// admin_audit_light.json:24,56 — same error class as W155 SW3.A).
//
// Standard pattern: server + client first render both see `mounted=false`
// → both pass safe defaults (matching DOM output). useEffect fires
// post-hydration → setMounted(true) triggers re-render with real hook
// values. Single-frame visual flicker on mobile (~16ms at 60fps) is
// imperceptible and acceptable per W156 SW3 trade-off.
export function AdminLayout() {
  const [mounted, setMounted] = useState(false)
  const user = useAuthStore((state) => state.user)
  const loading = useAuthStore((state) => state.loading)
  const navigate = useNavigate()
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const isNarrow = useMediaQuery(`(max-width: ${breakpoints.dashboard})`)
  const redirectTarget = getAdminRedirectTarget({ user, loading })
  useEffect(() => {
    setMounted(true)
  }, [])
  useEffect(() => {
    if (redirectTarget) void navigate({ to: redirectTarget, replace: true })
  }, [navigate, redirectTarget])

  if (mounted && redirectTarget) return null
  // Server + client initial render: pass defaults (mounted=false branch).
  // After hydration: useEffect → re-render with actual hook values.
  const ssrSafeIsNarrow = mounted ? isNarrow : false
  const ssrSafePrefersReducedMotion = mounted ? prefersReducedMotion : false
  return (
    <div className="admin-theme relative overflow-x-clip">
      <AdminBackdrop
        isNarrow={ssrSafeIsNarrow}
        prefersReducedMotion={ssrSafePrefersReducedMotion}
      />
      <div className="relative z-[1]">
        <Outlet />
      </div>
    </div>
  )
}

export const Route = createFileRoute("/_admin")({
  // Wave 168 SW1 — removed Wave 126 polish `ssr: false` override.
  // _admin now inherits `ssr: true` from _auth.tsx (W128 SW2 baseline)
  // since W127 SW1 provider hoisting + W128 SW3 SsrRoot + W149 SW2
  // hydrateRoot + W156 SW3 .ready class + W166 SW2 AdminLayout
  // mounted-state + W167 SW2 Navbar mounted-state are all in place.
  // Testing Path C-3 simplest test — does this close admin React #418
  // Mismatch A (MainLayout structural <main> vs <nav> swap)?
  //
  // Outcome handling per W141 anti-pattern #1 STRICT 1-iter cap:
  //  - Branch A (SSR works + Mismatch A closed): SHIP IT
  //  - Branch B (SSR works + Mismatch A persists): revert + theory disproved
  //  - Branch C (SSR crash): revert + W126 polish rationale validated
  // Wave 174 SW1 — read live Zustand state via useAuthStore.getState()
  // instead of stale `context.auth.*`. See _auth.tsx for full rationale
  // (W152 Phase 1.7 removed the App.tsx reactive context bridge).
  // Wave 179 SW8 — beforeLoad extracted to pure `evaluateAdminGuard`
  // (closes W174 §Honesty #4-routeGuards). Behavior preserved exactly:
  // unauth → /login, non-admin → /dashboard, admin → proceed.
  beforeLoad: () => evaluateAdminGuard(useAuthStore.getState()),
  component: AdminLayout,
})
