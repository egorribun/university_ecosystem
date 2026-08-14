/**
 * @fileoverview Wave 126 Phase 3 — SSR-side auth extraction.
 *
 * Pure utility module (no Node-specific imports) — safe to unit-test in jsdom.
 * Reads the HttpOnly `access_token_v2` cookie that backend issues via
 * LoginSessionManager._set_access_token_cookie (app/services/auth/login_session_manager.py:148-165),
 * validates the JWT via jose + JWKS endpoint at backend's
 * `/.well-known/jwks.json` (app/api/well_known.py — RS256 public keys).
 *
 * Used by `src/server.ts` to populate per-request auth state into
 * AsyncLocalStorage, which `src/router.ts:getRouter()` reads to construct
 * a router with real auth context for SSR-rendered routes (replaces W125
 * Phase 2 SSR_STUB_AUTH placeholder).
 *
 * VITE_LHCI bypass preserved per W116 SW3 (mirrored in
 * `src/hooks/auth/useProfileSync.ts:877`): when env flag is "true", returns
 * a synthetic mock user without cookie validation. Tree-shakes from prod
 * via Rolldown DCE (verified `grep -l "lhci-mock-user" dist/client/assets/*.js`
 * empty in prod build per W116 SW3 contract).
 */
import { createRemoteJWKSet, jwtVerify } from "jose"
import { resolveSsrBackendOrigin } from "@/api/backendOrigin"

export interface SsrAuthState {
  isAuth: boolean
  user: { role: string } | null
  loading: boolean
}

export const SSR_AUTH_UNAUTH: SsrAuthState = {
  isAuth: false,
  user: null,
  loading: false,
}

/** Explicit auth marker used by browser-mocked E2E sessions. */
export const SSR_E2E_AUTH_COOKIE = "ue-e2e-auth"

export const SSR_AUTH_LHCI_MOCK: SsrAuthState = {
  isAuth: true,
  user: { role: "student" },
  loading: false,
}

/**
 * Parse a single named cookie value out of a `Cookie` request header.
 * Returns the URL-decoded value, or null if not present.
 *
 * Pattern matches W125 backend logout handler (app/auth/handlers/logout.py:44)
 * which uses `request.cookies.get("access_token_v2")` — same cookie name.
 */
export function parseCookie(header: string | null | undefined, name: string): string | null {
  if (!header) return null
  // RFC 6265 cookie syntax: "name=value; name2=value2; ..." — split on "; "
  // is safe because cookie values cannot contain bare ";" per spec.
  // String-based parsing (no RegExp) avoids security/detect-non-literal-regexp
  // and any escaping concerns with the cookie name.
  const parts = header.split(/;\s*/)
  const prefix = `${name}=`
  for (const part of parts) {
    if (part.startsWith(prefix)) {
      const raw = part.slice(prefix.length)
      try {
        return decodeURIComponent(raw)
      } catch {
        return null
      }
    }
  }
  return null
}

/**
 * Resolve the JWKS endpoint URL.
 *
 * Uses the same runtime-first origin resolver as the SSR API client. This keeps
 * JWKS verification aligned with route-loader requests while allowing one
 * immutable image to run under arbitrary service names.
 */
function resolveJwksUrl(): URL {
  return new URL("/.well-known/jwks.json", resolveSsrBackendOrigin())
}

let cachedJwks: ReturnType<typeof createRemoteJWKSet> | null = null
function getJwks() {
  if (!cachedJwks) {
    cachedJwks = createRemoteJWKSet(resolveJwksUrl())
  }
  return cachedJwks
}

/**
 * Test seam — allow unit tests to inject a stub jwtVerify wrapper without
 * spinning up a real JWKS server. Test path sets this; prod path uses the
 * real createRemoteJWKSet flow.
 */
let jwtVerifyOverride:
  null | ((token: string) => Promise<{ payload: Record<string, unknown> } | null>) = null

export function _setJwtVerifyOverrideForTests(
  fn: ((token: string) => Promise<{ payload: Record<string, unknown> } | null>) | null
) {
  jwtVerifyOverride = fn
}

/**
 * Validate the JWT extracted from the cookie. Returns auth state on success,
 * SSR_AUTH_UNAUTH on any failure (signature, expiry, claim mismatch).
 *
 * Audience check matches backend's `app/core/config/mixins/jwt_settings.py:32`
 * default `university-ecosystem-api`. Override at deploy time via
 * VITE_JWT_AUDIENCE env var if backend is configured with a different audience.
 *
 * Required claims match backend's `app/auth/security.py:641` decode_token:
 * exp, iat, sub, jti, aud — jose's `jwtVerify` enforces exp + aud automatically;
 * sub validation done explicitly below.
 */
export async function validateJwt(token: string): Promise<SsrAuthState> {
  const audience = import.meta.env.VITE_JWT_AUDIENCE || "university-ecosystem-api"
  try {
    const result = jwtVerifyOverride
      ? await jwtVerifyOverride(token)
      : await jwtVerify(token, getJwks(), { audience })
    if (!result) return SSR_AUTH_UNAUTH
    const payload = result.payload as Record<string, unknown>
    if (typeof payload.sub !== "string" || !payload.sub) return SSR_AUTH_UNAUTH
    const role = typeof payload.role === "string" ? payload.role : "student"
    return { isAuth: true, user: { role }, loading: false }
  } catch {
    return SSR_AUTH_UNAUTH
  }
}

/**
 * Main entry — given an incoming Request, return the SSR auth state to pass
 * into the router context for that request.
 *
 * Order of precedence:
 * 1. VITE_LHCI bypass (test/perf measurement — synthetic mock user).
 * 2. `access_token_v2` cookie present + valid JWT → real auth from JWT claims.
 * 3. Otherwise → SSR_AUTH_UNAUTH (route guards see isAuth:false → redirect).
 *
 * The cookie name `access_token_v2` mirrors the backend's
 * `LoginSessionManager._set_access_token_cookie` chokepoint (issued for ALL
 * login flows: password, passkey, MFA verify, OAuth). No new cookie is added
 * by W126 — Phase 3 reuses existing infrastructure.
 */
export async function extractAuthFromRequest(request: Request): Promise<SsrAuthState> {
  if (import.meta.env.VITE_LHCI === "true") {
    return SSR_AUTH_LHCI_MOCK
  }
  const cookieHeader = request.headers.get("cookie")
  // Browser-mocked E2E sessions cannot set the real HttpOnly auth cookie.
  // Accept their explicit marker only in builds with the E2E feature flag.
  if (
    import.meta.env.VITE_E2E_MODE === "1" &&
    parseCookie(cookieHeader, SSR_E2E_AUTH_COOKIE) === "mock"
  ) {
    return SSR_AUTH_LHCI_MOCK
  }
  const token = parseCookie(cookieHeader, "access_token_v2")
  if (!token) return SSR_AUTH_UNAUTH
  return validateJwt(token)
}
