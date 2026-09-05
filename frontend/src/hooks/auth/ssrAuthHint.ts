import type { SsrAuthState } from "@/ssrAuth"

/**
 * @fileoverview Wave 128 SW1 — Strategy A bridge for AuthProvider.
 *
 * Reads the per-request SSR auth state injected by `src/server.ts` via
 * `globalThis.__ssrAuthGetter__` (W126 SW4 pattern). The server also emits a
 * role-only marker on `#root`; reading that marker on the browser keeps the
 * first client render aligned with the authenticated SSR tree until the
 * authoritative `/users/me` request resolves. No token or PII is serialized.
 *
 * NOT a React Hook — this is a plain function (no `use` prefix). The
 * value must be read at `useState` initFn time (or any non-render time)
 * — never inside the component body where the React Compiler would
 * mistake it for a hook.
 *
 * Defensive try/catch around the getter invocation: any unexpected
 * throw (extremely unlikely — getter just calls AsyncLocalStorage
 * `getStore()`) returns undefined so the AuthProvider initFn falls
 * back to the safe `null` user state.
 */
export function readSsrAuthHint(): SsrAuthState | undefined {
  let serverHint: SsrAuthState | undefined
  try {
    serverHint = globalThis.__ssrAuthGetter__?.()
  } catch {
    return undefined
  }

  if (serverHint) return serverHint

  // Keep the DOM bridge safe in the Node SSR runtime without a separate
  // `typeof document` branch. The no-op object also lets the marker chain stay
  // total when a browser document has not mounted the root element yet.
  const documentRef = globalThis.document ?? { getElementById: () => null }
  const marker = documentRef.getElementById("root")?.getAttribute("data-ssr-auth")
  if (!marker?.startsWith("authenticated:")) return undefined
  const role = marker.slice("authenticated:".length)
  if (!role || role.trim() !== role) return undefined
  return { isAuth: true, user: { role }, loading: false }
}
