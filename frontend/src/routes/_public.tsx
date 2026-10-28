import { useEffect, useRef } from "react"
import {
  createFileRoute,
  Outlet,
  redirect,
  useNavigate,
  useRouterState,
} from "@tanstack/react-router"
import { useAuthStore } from "@/stores/useAuthStore"
import { resolveRedirectPath } from "@/utils/redirect"
import { evaluatePublicGuard } from "./guards"
import { PageRouteSEO } from "@/components/ui/PageRouteSEO"

/**
 * Wave 178 SW1 — Approach 1 extension closing W177 §Honesty #2.
 *
 * Adds reactive layout-level watcher in _public.tsx covering ALL routes
 * under /_public (/login, /forgot-password, /register, /reset-password,
 * /reset-password/$token) via a single mechanism, parallel to W177 SW1's
 * Login.tsx-specific useEffect.
 *
 * Defense-in-depth design: Login.tsx's W177 SW1 useEffect REMAINS unchanged.
 * React 19 child-effect-before-parent-effect ordering means both fire when
 * the user transition null→set occurs; both navigate({ to: "/dashboard",
 * replace: true }); the second call is a no-op once the route already
 * changed. Removing Login.tsx's would orphan the W177 §Honesty #3
 * regression test and break Login.test.tsx — W178 is purely additive.
 *
 * The beforeLoad guard below (W174 SW1) runs only ONCE on initial route
 * mount; this useEffect catches subsequent user transitions that
 * beforeLoad cannot see — e.g. authed user opens /forgot-password via
 * bookmark → AuthProvider's useProfileSync settles /users/me → setUser
 * populates useAuthStore → this effect observes the transition →
 * redirect to /dashboard with replace:true (no /forgot-password etc.
 * in back-button history for authed users).
 *
 * Hardcoded /dashboard target matches W177 SW1's choice. Preserving
 * state.from / search.redirect is a DIFFERENT mechanism (W177 §Honesty
 * #3 / Q0 option C) explicitly out of W178 scope.
 *
 * Exported as a named function (not inline arrow) so the dedicated unit
 * test at routes/__tests__/_public.test.tsx can mount it under a custom
 * route tree. The standard `renderWithRouter` helper builds a FLAT route
 * tree (per its docstring caveat at lines 50-54) and does NOT exercise
 * layout components.
 */
export function PublicLayout() {
  const user = useAuthStore((s) => s.user)
  const navigate = useNavigate()
  // Wave 179 SW4 — honor search.redirect param across all 5 /_public routes.
  // Pre-W179: hardcoded /dashboard ignored writer at _auth.tsx:47 → user
  // intended destination (e.g., /events) was lost on re-auth. Closes W177
  // §Honesty #3 race at the LAYOUT level (parallel to Login.tsx useEffect).
  // resolveRedirectPath defaults to /dashboard for missing/malformed/cross-
  // origin redirect param.
  //
  // Wave 179 SW4 ref-guard: prevent re-fire after initial redirect (same
  // pattern as Login.tsx). navigate({to: target}) clears location.search →
  // useEffect re-fires with undefined → falls back to /dashboard, overriding
  // the original /events navigation. ref blocks subsequent fires.
  const search = useRouterState({ select: (s) => s.location.search })
  const redirectedRef = useRef(false)
  useEffect(() => {
    if (user && !redirectedRef.current) {
      redirectedRef.current = true
      const target = resolveRedirectPath((search as { redirect?: unknown } | null)?.redirect)
      navigate({ to: target, replace: true })
    }
  }, [user, navigate, search])
  return (
    <>
      <PageRouteSEO />
      <Outlet />
    </>
  )
}

function containsUnsafeRedirectCharacters(value: string): boolean {
  return Array.from(value).some((character) => {
    const code = character.charCodeAt(0)
    return code < 32 || code === 127 || character === "\\"
  })
}

function resolveSsrPublicRedirect(value: unknown): string | undefined {
  if (typeof value !== "string" || !value || containsUnsafeRedirectCharacters(value)) return

  const isRelative = value.startsWith("/") && !value.startsWith("//")
  try {
    const origin = globalThis.__ssrOriginGetter__?.()
    if (!isRelative && (!origin || !/^https?:\/\//iu.test(value))) return
    const base = new URL(origin ?? "https://public-redirect.invalid")
    const target = new URL(value, base)
    if (
      !["http:", "https:"].includes(target.protocol) ||
      target.origin !== base.origin ||
      target.username ||
      target.password ||
      target.pathname.startsWith("//") ||
      /%(?:2f|5c|25)/iu.test(target.pathname)
    ) {
      return
    }

    const pathname = decodeURIComponent(target.pathname)
    // HTTP URL paths always begin with '/', so this segment is present.
    const firstSegment = pathname.split("/")[1]!.toLowerCase()
    if (
      containsUnsafeRedirectCharacters(pathname) ||
      ["login", "register", "forgot-password", "reset-password"].includes(firstSegment)
    ) {
      return
    }

    return `${target.pathname}${target.search}${target.hash}`
  } catch {
    return
  }
}

export const Route = createFileRoute("/_public")({
  // Wave 154 SW1 — removed `ssr: false` workaround (W150 polish-followup commit
  // 7c97de583) since W153 SW2 (commit d931492e3) closed the React #418
  // hydration mismatch root cause via SSR-aware `defaultPendingComponent`
  // (router.ts:88, `import.meta.env.SSR ? null : <Loading…>` literal split).
  // `_public.tsx` now inherits `ssr: true` from root (W128 SW2 inheritance
  // contract: child can only be MORE restrictive). If hydration hazards from
  // ParticleAuthBackground canvas, useId form fields, or theme/lang cookies
  // re-fire post-revert, W155+ scope can re-add explicit `ssr: false` here OR
  // SSR-suppress the specific offending component via `import.meta.env.SSR`
  // pattern matching W153 SW2.
  //
  // SSR uses request-scoped auth; the client uses live Zustand state because
  // its router context does not update when authentication changes.
  //
  // Wave 178 SW1 — beforeLoad still runs ONCE on initial route mount; the
  // PublicLayout component above adds the reactive useEffect that catches
  // post-mount user transitions across all 5 child routes via a single
  // mechanism (closes W177 §Honesty #2).
  // Wave 179 SW8 — beforeLoad extracted to pure `evaluatePublicGuard`
  // (closes W174 §Honesty #4-routeGuards). Behavior preserved exactly.
  beforeLoad: ({ context, location }) => {
    if (!import.meta.env.SSR) return evaluatePublicGuard(useAuthStore.getState())

    const auth = {
      user: context.auth.isAuth ? context.auth.user : null,
      loading: context.auth.loading,
    }
    if (!auth.loading && auth.user) {
      const target = resolveSsrPublicRedirect((location.search as { redirect?: unknown }).redirect)
      if (target) throw redirect({ href: target })
    }
    evaluatePublicGuard(auth)
  },
  component: PublicLayout,
})
