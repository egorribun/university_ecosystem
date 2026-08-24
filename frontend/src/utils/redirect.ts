/**
 * Wave 179 SW4 — TanStack Router canonical `search.redirect` parsing helper.
 *
 * Resolves the post-login redirect target from `search.redirect` URL parameter
 * (written by `_auth.tsx:47` beforeLoad on unauth-deflect via
 * `search: { redirect: location.href }`) into a safe same-origin pathname for
 * `navigate({ to: target })`.
 *
 * Background — W177 §Honesty #3 race condition: writer-side at `_auth.tsx:47`
 * used TanStack canonical `search.redirect`, but reader-side at
 * `useLoginFlow.ts:71` used LEGACY React Router pattern
 * `useRouterState({ select: (s) => s.location.state })` → `state?.from?.pathname`.
 * Pattern mismatch meant `state.from` was always undefined (writer never set
 * it), so `redirectPath` defaulted to `/dashboard` regardless of the unauth
 * deep-link origin (e.g., `/events` → `/login?redirect=...` → `/dashboard`
 * instead of `/events`). Login.tsx + _public.tsx useEffects further hardcoded
 * `/dashboard` ignoring both patterns.
 *
 * Fix: unify on TanStack canonical `search.redirect` across all 3 consumers
 * via this helper. Returns `fallback` ("/dashboard" by default) for:
 *  - non-string / empty input
 *  - malformed URL (URL constructor throws)
 *  - cross-origin redirect (security — prevents open redirect attack vector)
 *
 * Accepts both absolute URLs (writer produces `location.href` = full URL) and
 * relative path-only strings (defensive for tests + future hand-written calls).
 *
 * @param redirect - raw search.redirect value from URL query string (URL-decoded by TanStack Router)
 * @param fallback - default pathname if redirect is invalid (default "/dashboard")
 * @returns safe same-origin pathname or fallback
 */
export function resolveRedirectPath(redirect: unknown, fallback = "/dashboard"): string {
  if (typeof redirect !== "string" || redirect.length === 0) return fallback

  // Relative path-only (e.g., "/events"); protocol-relative `//evil.com` excluded
  if (redirect.startsWith("/") && !redirect.startsWith("//")) {
    return redirect
  }

  // Absolute URL — verify same-origin to prevent open-redirect attack
  try {
    const url = new URL(redirect)
    if (typeof window !== "undefined" && url.origin !== window.location.origin) {
      return fallback
    }
    return url.pathname
  } catch {
    return fallback
  }
}
