import { useEffect, useRef } from "react"
import { createFileRoute, Outlet, useNavigate, useRouterState } from "@tanstack/react-router"
import { useAuthStore } from "@/stores/useAuthStore"
import { evaluateAuthGuard } from "./guards"

function AuthLayout() {
  const user = useAuthStore((state) => state.user)
  const loading = useAuthStore((state) => state.loading)
  const navigate = useNavigate()
  const destination = useRouterState({ select: (state) => state.location.href })
  const needsLogin = !loading && !user && import.meta.env.VITE_LHCI !== "true"
  const redirectedRef = useRef(false)

  useEffect(() => {
    if (!needsLogin) {
      redirectedRef.current = false
    } else if (!redirectedRef.current) {
      // Pending navigation changes the URL before this layout unmounts.
      redirectedRef.current = true
      void navigate({ to: "/login", search: { redirect: destination }, replace: true })
    }
  }, [destination, navigate, needsLogin])

  if (needsLogin) return null
  return <Outlet />
}

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
  // RouterContext.auth is request-scoped during SSR but static on the
  // client. SSR guards use the verified request state; client navigation
  // uses Zustand, which useProfileSync keeps current after login.
  // Wave 179 SW8 — beforeLoad logic extracted to pure function
  // `evaluateAuthGuard` at `./guards.ts` for unit testability (closes
  // W174 §Honesty #4-routeGuards). All branches (loading + VITE_LHCI
  // bypass + unauth redirect with search.redirect) preserved exactly —
  // see guards.ts for full rationale + __tests__/guards.test.ts for
  // 11 unit tests covering the decision tree.
  beforeLoad: ({ context, location }) =>
    evaluateAuthGuard(
      import.meta.env.SSR
        ? {
            user: context.auth.isAuth ? context.auth.user : null,
            loading: context.auth.loading,
          }
        : useAuthStore.getState(),
      location
    ),
  component: AuthLayout,
})
