import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_auth")({
  // Wave 128 SW2 — flip `ssr: false` → `ssr: true` so /dashboard
  // (W128 SW3) can opt INTO server-rendered component, and W127 SW6
  // annotations on /map + /activity (`ssr: 'data-only'`) finally
  // take effect (they were silently ignored under the more-restrictive
  // `false` parent). Per TanStack Start v1 SSR inheritance contract:
  // a child can ONLY make MORE restrictive (`false > 'data-only' >
  // true`). With parent now `true`, children opt DOWN to 'data-only'
  // (map + activity) or `false` (8 siblings that haven't been
  // SSR-audited yet — see explicit `ssr: false` annotations on
  // messenger.*, profile, settings, news.*, events.*, schedule).
  //
  // W127 SW1 hoisted AppProviders + ThemeProvider + AuthProvider into
  // __root.tsx RootComponent so MainLayout becomes SSR-safe. W128 SW1
  // bridges AuthProvider to RouterContext.auth via readSsrAuthHint so
  // Navbar renders with role-only stub on cold-load /dashboard.
  ssr: true,
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
