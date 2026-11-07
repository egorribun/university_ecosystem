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
type JwtVerifyResult = { payload: Record<string, unknown> } | null

let jwtVerifyOverride: null | ((token: string) => Promise<JwtVerifyResult>) = null

export function _setJwtVerifyOverrideForTests(
  fn: ((token: string) => Promise<JwtVerifyResult>) | null
) {
  jwtVerifyOverride = fn
}

const DEFAULT_JWT_ISSUER = "university-ecosystem"

/** Python str.strip() whitespace, excluding U+FEFF and including NEL/FS-US. */
const PYTHON_STRIP_EDGE_WHITESPACE = new Set([
  "\u0009",
  "\u000A",
  "\u000B",
  "\u000C",
  "\u000D",
  "\u001C",
  "\u001D",
  "\u001E",
  "\u001F",
  "\u0020",
  "\u0085",
  "\u00A0",
  "\u1680",
  "\u2000",
  "\u2001",
  "\u2002",
  "\u2003",
  "\u2004",
  "\u2005",
  "\u2006",
  "\u2007",
  "\u2008",
  "\u2009",
  "\u200A",
  "\u2028",
  "\u2029",
  "\u202F",
  "\u205F",
  "\u3000",
])

type SsrNodeProcessLike = {
  env?: Record<string, string | undefined>
}

/**
 * Resolve the issuer that backend access tokens must carry.
 *
 * The deployed frontend receives the same runtime JWT_ISSUER value as the
 * backend. An omitted value uses the backend settings default outside
 * production; an explicitly blank value and any unconfigured production
 * process fail closed.
 */
function normalizeJwtIssuer(value: string): string | null {
  const characters = Array.from(value)
  let start = 0
  let end = characters.length
  while (start < end && PYTHON_STRIP_EDGE_WHITESPACE.has(characters[start]!)) start++
  while (end > start && PYTHON_STRIP_EDGE_WHITESPACE.has(characters[end - 1]!)) end--

  if (start === end) return null
  const normalizedCharacters = characters.slice(start, end)
  if (normalizedCharacters.length > 512) return null
  if (normalizedCharacters.some((character) => character.charCodeAt(0) < 0x20)) return null
  return normalizedCharacters.join("")
}
function resolveJwtIssuer(): string | null {
  const runtimeProcess = Object(
    (globalThis as typeof globalThis & { process?: SsrNodeProcessLike }).process
  ) as SsrNodeProcessLike
  const runtimeEnv = Object(runtimeProcess.env) as Record<string, unknown>
  const configuredIssuer = runtimeEnv.JWT_ISSUER
  if (typeof configuredIssuer === "string") return normalizeJwtIssuer(configuredIssuer)
  if (runtimeEnv.NODE_ENV === "production") return null
  return DEFAULT_JWT_ISSUER
}

/**
 * Validate the JWT extracted from the cookie. Returns auth state on success,
 * SSR_AUTH_UNAUTH on any failure (signature, expiry, or claim mismatch).
 *
 * The audience follows the backend's `jwt_audience` setting. The issuer comes
 * from the backend's runtime `JWT_ISSUER`; its local default is kept in sync
 * with `app/core/config/mixins/jwt_settings.py`. jose verifies exp, audience,
 * and issuer; subject validation remains explicit below.
 */
export async function validateJwt(token: string): Promise<SsrAuthState> {
  const issuer = resolveJwtIssuer()
  if (!issuer) return SSR_AUTH_UNAUTH
  const audience = import.meta.env.VITE_JWT_AUDIENCE || "university-ecosystem-api"
  let result: JwtVerifyResult = null
  try {
    result = jwtVerifyOverride
      ? await jwtVerifyOverride(token)
      : await jwtVerify(token, getJwks(), { audience, issuer })
  } catch {
    // A rejected verification leaves `result` null, i.e. unauthenticated.
  }
  const payload = result?.payload
  if (!payload || payload.iss !== issuer) return SSR_AUTH_UNAUTH
  if (typeof payload.sub !== "string" || !payload.sub) return SSR_AUTH_UNAUTH
  const role = typeof payload.role === "string" ? payload.role : "student"
  return { isAuth: true, user: { role }, loading: false }
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
 * login flows: password, MFA verify, OAuth). No new cookie is added
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
