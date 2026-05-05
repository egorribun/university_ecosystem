// Wave 125 Phase 2 — TanStack Start v1 server entry.
// Wave 126 Phase 3 (this revision) — cookie-based auth-at-edge.
//
// This file is the SSR / build-time prerender handler for our SPA shell.
// `createServerEntry` produces a `{ fetch }` interface that:
//   - During build: tanstackStart's prerender pipeline calls
//     `handler.fetch(new Request("/"))` to generate `dist/client/_shell.html`
//   - During preview / production deploy: tanstackStart's preview-server
//     plugin (and Caddy SSR forwarding rules from Phase 4) routes
//     incoming HTTP requests through this handler, which delegates to
//     `@tanstack/react-start/server-entry`'s default `handler.fetch`
//     (renders the matched route via `renderRouterToStream`).
//
// Wave 126 Phase 3 — auth-at-edge:
//   1. Read `access_token_v2` HttpOnly cookie from request (issued by backend
//      LoginSessionManager._set_access_token_cookie — see SW1 audit notes).
//   2. Validate JWT via jose + JWKS endpoint at `/.well-known/jwks.json`
//      (RS256 public keys — app/api/well_known.py).
//   3. Stash auth state in an AsyncLocalStorage scoped to the request, expose
//      via globalThis getter so `src/router.ts:getRouter()` can read it
//      synchronously when constructing the router for SSR.
//   4. VITE_LHCI bypass mirrored from W116 SW3 (synthetic mock user).
//
// Per-route SSR opt-in (W126 SW5+) gates which routes actually consume this
// auth context server-side; until a route enables `ssr: true`, it stays SPA
// and the auth context is irrelevant for that route.
import { AsyncLocalStorage } from "node:async_hooks"
import handler, { createServerEntry } from "@tanstack/react-start/server-entry"
import { extractAuthFromRequest, SSR_AUTH_UNAUTH, type SsrAuthState } from "./ssrAuth"

// Per-request auth storage — node:async_hooks AsyncLocalStorage scopes the
// auth state to the async context spawned for THIS request. Nested awaits
// inside `handler.fetch` (which calls `getRouter()` to construct the router)
// see the same store via `requestAuthStorage.getStore()`.
//
// node:async_hooks is server-only — Vite's environments build keeps this
// import in the server chunk only; client bundle never loads it.
const requestAuthStorage = new AsyncLocalStorage<SsrAuthState>()

// Globally-accessible getter so `src/router.ts` can read the per-request auth
// state without a circular import (router.ts is also imported by client code,
// so it cannot import server.ts directly). The getter is set ONCE at module
// load; the value it returns is the per-request store from AsyncLocalStorage.
declare global {
  // `var` is required in `declare global` to type a globalThis property —
  // `let`/`const` cannot augment the global namespace. ESLint's `no-var` /
  // `vars-on-top` rules do not flag declarations inside `declare global`.
  var __ssrAuthGetter__: (() => SsrAuthState | undefined) | undefined
}
globalThis.__ssrAuthGetter__ = () => requestAuthStorage.getStore()

export default createServerEntry({
  async fetch(request) {
    let auth: SsrAuthState
    try {
      auth = await extractAuthFromRequest(request)
    } catch {
      // Defensive — extractAuthFromRequest already swallows JWT errors and
      // returns SSR_AUTH_UNAUTH; this catch only fires on infrastructure
      // failures (e.g. JWKS endpoint unreachable during cold start).
      auth = SSR_AUTH_UNAUTH
    }
    return requestAuthStorage.run(auth, () => handler.fetch(request))
  },
})
