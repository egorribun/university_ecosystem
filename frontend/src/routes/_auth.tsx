import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_auth")({
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
