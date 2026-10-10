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
import type { i18n as I18nInstance } from "i18next"
import { createI18nInstance } from "./i18n/config"
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
// Six storages (W126 + W127 + W133):
//   - requestAuthStorage: SSR auth state from access_token_v2 cookie (W126 SW3)
//   - requestCookieStorage: raw Cookie header for SSR-side authenticated
//     backend calls via axios interceptor (W133 SW1 — see api/client.ts)
//   - requestFingerprintHeadersStorage: original browser UA/language for the
//     same SSR backend calls, preserving the session security binding
//   - requestThemeStorage: resolved theme from ue-mode cookie (W127 SW4)
//   - requestLangStorage: resolved lang from ue:language cookie (W127 SW4)
//
// Layered as nested .run() calls so all four are visible to the handler.
const requestAuthStorage = new AsyncLocalStorage<SsrAuthState>()
const requestCookieStorage = new AsyncLocalStorage<string>()
type SsrFingerprintHeaders = { userAgent: string; acceptLanguage: string }
const requestFingerprintHeadersStorage = new AsyncLocalStorage<SsrFingerprintHeaders>()
const requestThemeStorage = new AsyncLocalStorage<ResolvedTheme>()
const requestLangStorage = new AsyncLocalStorage<ResolvedLang>()
const requestI18nStorage = new AsyncLocalStorage<I18nInstance>()

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
  var __ssrCookieGetter__: (() => string | undefined) | undefined
  var __ssrFingerprintHeadersGetter__: (() => SsrFingerprintHeaders | undefined) | undefined
  var __ssrThemeGetter__: (() => ResolvedTheme | undefined) | undefined
  var __ssrLangGetter__: (() => ResolvedLang | undefined) | undefined
  var __ssrI18nGetter__: (() => I18nInstance | undefined) | undefined
}
globalThis.__ssrAuthGetter__ = () => requestAuthStorage.getStore()
globalThis.__ssrCookieGetter__ = () => requestCookieStorage.getStore()
globalThis.__ssrFingerprintHeadersGetter__ = () => requestFingerprintHeadersStorage.getStore()
globalThis.__ssrThemeGetter__ = () => requestThemeStorage.getStore()
globalThis.__ssrLangGetter__ = () => requestLangStorage.getStore()
globalThis.__ssrI18nGetter__ = () => requestI18nStorage.getStore()

// Wave 131 SW2 — Phase 4 deploy infrastructure /healthz endpoint.
// Caddy `health_uri /healthz` (Caddyfile, W131 SW4) + k8s livenessProbe /
// readinessProbe (deployment.yaml, W131 SW5) need a fast non-SSR endpoint
// that doesn't run JWT validation, theme/lang extraction, or full route
// render. Probes typically have a 5s timeout; SSR cold-start can exceed
// that on first request (router construction, JWKS fetch, etc.).
// The early-return below short-circuits BEFORE `requestAuthStorage.run()`
// so it returns a 200 in <10ms with no AsyncLocalStorage overhead.
const HEALTHZ_RESPONSE_BODY = JSON.stringify({ status: "ok" })
const HEALTHZ_RESPONSE_INIT: ResponseInit = {
  status: 200,
  headers: {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  },
}

// Authenticated SSR responses can contain per-user loader data and query
// hydration state, so browsers and shared intermediaries must never store
// them. Keep the existing /messenger protection for unauthenticated requests
// too, since that route handles private relationship state when logged in.
// Vary: Cookie also protects deployments with misconfigured intermediary
// caching, and Cache-Control overrides any upstream public policy.
const PRIVATE_SSR_CACHE_CONTROL = "no-store, private, max-age=0"
const PRIVATE_SSR_VARY = "Cookie"
const MESSENGER_PATH_PREFIX = "/messenger"

/** Mark a potentially user-specific SSR document private without changing its body or status. */
const augmentResponseForPrivateSsr = (response: Response): Response => {
  const headers = new Headers(response.headers)
  headers.set("cache-control", PRIVATE_SSR_CACHE_CONTROL)
  const existingVary = headers.get("vary")
  if (existingVary) {
    // Preserve any existing Vary entries (e.g. Accept-Encoding from
    // upstream gzip middleware); only append Cookie if not already listed.
    const varyTokens = existingVary
      .split(",")
      .map((token) => token.trim().toLowerCase())
      .filter(Boolean)
    // A wildcard already signals variation by any request header, so keep it
    // as supplied rather than redundantly appending Cookie.
    if (!varyTokens.includes("cookie") && !varyTokens.includes("*")) {
      headers.set("vary", `${existingVary}, ${PRIVATE_SSR_VARY}`)
    }
  } else {
    headers.set("vary", PRIVATE_SSR_VARY)
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  })
}

export default createServerEntry({
  async fetch(request) {
    // Wave 131 SW2 — Phase 4 healthz fast path. URL parsing is cheap; we
    // explicitly do NOT hit `extractAuthFromRequest` (avoids JWKS network
    // round-trip on cold start) or `extractThemeFromRequest` /
    // `extractLangFromRequest` (cookie parse). Returns inside the worker
    // even before the AsyncLocalStorage chain is set up.
    const url = new URL(request.url)
    if (url.pathname === "/healthz") {
      return new Response(HEALTHZ_RESPONSE_BODY, HEALTHZ_RESPONSE_INIT)
    }

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
    const requestI18n = createI18nInstance(lang)
    // Wave 133 SW1 — raw Cookie header for SSR-side authenticated backend
    // calls. The axios client interceptor (frontend/src/api/client.ts)
    // forwards this header on outgoing /api/v1 requests when running on
    // Node SSR (typeof window === "undefined"). Stores empty string on
    // unauthenticated requests so the getter never returns undefined when
    // the chain is active. NEVER log or surface the raw value — it
    // contains the access_token_v2 HttpOnly cookie.
    const cookie = request.headers.get("cookie") ?? ""
    const fingerprintHeaders: SsrFingerprintHeaders = {
      userAgent: request.headers.get("user-agent") ?? "",
      acceptLanguage: request.headers.get("accept-language") ?? "",
    }
    // Authenticated SSR may serialize request-specific loader data. Protect it
    // alongside messenger responses, which remain private even when unauthenticated.
    const isMessengerPath = url.pathname.startsWith(MESSENGER_PATH_PREFIX)
    return requestAuthStorage.run(auth, () =>
      requestCookieStorage.run(cookie, () =>
        requestFingerprintHeadersStorage.run(fingerprintHeaders, () =>
          requestThemeStorage.run(theme, () =>
            requestLangStorage.run(lang, () =>
              requestI18nStorage.run(requestI18n, async () => {
                const response = await handler.fetch(request)
                return auth.isAuth || isMessengerPath
                  ? augmentResponseForPrivateSsr(response)
                  : response
              })
            )
          )
        )
      )
    )
  },
})
