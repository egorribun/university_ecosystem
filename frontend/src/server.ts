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
import {
  extractThemeFromRequest,
  extractLangFromRequest,
  type ResolvedTheme,
  type ResolvedLang,
} from "./ssrTheme"

// Per-request storages — node:async_hooks AsyncLocalStorage scopes the per-
// request state to the async context spawned for THIS request. Nested awaits
// inside `handler.fetch` (which calls `getRouter()` to construct the router,
// and may also nest into RootShell rendering) see the same stores via the
// `getStore()` calls below.
//
// node:async_hooks is server-only — Vite's environments build keeps this
// import in the server chunk only; client bundle never loads it.
//
// Three storages (W126 + W127):
//   - requestAuthStorage: SSR auth state from access_token_v2 cookie (W126 SW3)
//   - requestThemeStorage: resolved theme from ue-mode cookie (W127 SW4)
//   - requestLangStorage: resolved lang from ue:language cookie (W127 SW4)
//
// Layered as nested .run() calls so all three are visible to the handler.
const requestAuthStorage = new AsyncLocalStorage<SsrAuthState>()
const requestThemeStorage = new AsyncLocalStorage<ResolvedTheme>()
const requestLangStorage = new AsyncLocalStorage<ResolvedLang>()

// Globally-accessible getters so `src/router.ts` (W126 SW4) and
// `src/routes/__root.tsx` RootShell (W127 SW5) can read per-request state
// without a circular import (router.ts + __root.tsx are also imported by
// client code, so they cannot import server.ts directly). Getters set ONCE
// at module load; the values they return are the per-request stores.
declare global {
  // `var` is required in `declare global` to type a globalThis property —
  // `let`/`const` cannot augment the global namespace. ESLint's `no-var` /
  // `vars-on-top` rules do not flag declarations inside `declare global`.
  var __ssrAuthGetter__: (() => SsrAuthState | undefined) | undefined
  var __ssrThemeGetter__: (() => ResolvedTheme | undefined) | undefined
  var __ssrLangGetter__: (() => ResolvedLang | undefined) | undefined
}
globalThis.__ssrAuthGetter__ = () => requestAuthStorage.getStore()
globalThis.__ssrThemeGetter__ = () => requestThemeStorage.getStore()
globalThis.__ssrLangGetter__ = () => requestLangStorage.getStore()

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
    // Theme + lang extraction is sync + has try/catch internally; safe to call
    // directly without await.
    const theme = extractThemeFromRequest(request)
    const lang = extractLangFromRequest(request)
    return requestAuthStorage.run(auth, () =>
      requestThemeStorage.run(theme, () =>
        requestLangStorage.run(lang, () => handler.fetch(request)),
      ),
    )
  },
})
