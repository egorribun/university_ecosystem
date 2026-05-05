import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_auth")({
  // Wave 126 polish — `ssr: false` overrides root's `ssr: true` for
  // authenticated routes (more restrictive override per TanStack Start
  // v1 SSR inheritance contract). MainLayout's provider chain
  // (`AppShellProvider`, `AuthProvider`, etc.) is not yet hoisted
  // above `<StartClient />`, so authenticated routes that depend on
  // those providers must render client-only until Phase 5. /login
  // under `_public.tsx` (no override) inherits root's `ssr: true`
  // and renders server-side as the smallest blast radius.
  ssr: false,
  beforeLoad: ({ context, location }) => {
    if (context.auth.loading) return
    // Wave 116 SW3 — LHCI bypass for authenticated-route a11y/perf scoring.
    // scripts/run-lhci.mjs:14 sets process.env.VITE_LHCI="true" which Vite
    // substitutes at build time; useProfileSync short-circuits the /users/me
    // call and populates a mock user so this guard sees isAuth=true and
    // authenticated pages render their real content for LHCI. Tree-shakes in
    // prod — CI's .lighthouserc.js builds the regular dist without the flag.
    if (import.meta.env.VITE_LHCI === "true") return
    if (!context.auth.isAuth) {
      throw redirect({
        to: "/login",
        search: { redirect: location.href },
      })
    }
  },
  component: () => <Outlet />,
})
