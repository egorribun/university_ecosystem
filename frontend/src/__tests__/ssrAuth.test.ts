/**
 * Wave 126 Phase 3 SW3 — unit tests for cookie parser + JWT validation
 * stubs in ssrAuth.ts. Real JWKS verification happens in dev/prod via the
 * jose library; here we use the test seam (`_setJwtVerifyOverrideForTests`)
 * to bypass network access.
 */
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest"
import {
  parseCookie,
  validateJwt,
  extractAuthFromRequest,
  SSR_AUTH_UNAUTH,
  SSR_AUTH_LHCI_MOCK,
  _setJwtVerifyOverrideForTests,
} from "../ssrAuth"

describe("ssrAuth.parseCookie", () => {
  it("returns null for null/undefined/empty header", () => {
    expect(parseCookie(null, "x")).toBeNull()
    expect(parseCookie(undefined, "x")).toBeNull()
    expect(parseCookie("", "x")).toBeNull()
  })

  it("returns null when name not present", () => {
    expect(parseCookie("foo=bar; baz=qux", "missing")).toBeNull()
  })

  it("extracts a value from a single-cookie header", () => {
    expect(parseCookie("access_token_v2=abc123", "access_token_v2")).toBe("abc123")
  })

  it("extracts a value when surrounded by other cookies", () => {
    expect(
      parseCookie("csrf_token=tok; access_token_v2=abc123; ue-mode=dark", "access_token_v2")
    ).toBe("abc123")
  })

  it("extracts the first cookie at the start of the header", () => {
    expect(parseCookie("access_token_v2=at_v2; csrf_token=ct", "access_token_v2")).toBe("at_v2")
  })

  it("URL-decodes the value", () => {
    expect(parseCookie("foo=hello%20world", "foo")).toBe("hello world")
  })

  it("returns null when URL decoding fails", () => {
    // Lone %ZZ is invalid percent-encoding → decodeURIComponent throws.
    expect(parseCookie("foo=%ZZ", "foo")).toBeNull()
  })

  it("does not match a name that is a prefix of another cookie", () => {
    // "access_token_v2_OTHER=..." should not match name "access_token_v2".
    // Our regex requires the next char to be `=`.
    expect(parseCookie("access_token_v2_legacy=legacy_value; csrf=x", "access_token_v2")).toBeNull()
  })

  it("escapes regex metacharacters in the name", () => {
    // Cookie names rarely contain regex metas, but the function should not
    // misinterpret a literal `.` or `*` as a wildcard.
    expect(parseCookie("a.b=value", "a.b")).toBe("value")
    // A different cookie that would match if `.` were a wildcard:
    expect(parseCookie("axb=other", "a.b")).toBeNull()
  })
})

describe("ssrAuth.validateJwt", () => {
  beforeEach(() => {
    _setJwtVerifyOverrideForTests(null)
  })

  afterEach(() => {
    _setJwtVerifyOverrideForTests(null)
  })

  it("returns SSR_AUTH_UNAUTH when override resolves null (verify failed)", async () => {
    _setJwtVerifyOverrideForTests(async () => null)
    const auth = await validateJwt("any.token.value")
    expect(auth).toEqual(SSR_AUTH_UNAUTH)
  })

  it("returns SSR_AUTH_UNAUTH when override throws", async () => {
    _setJwtVerifyOverrideForTests(async () => {
      throw new Error("invalid signature")
    })
    const auth = await validateJwt("any.token.value")
    expect(auth).toEqual(SSR_AUTH_UNAUTH)
  })

  it("returns SSR_AUTH_UNAUTH when sub claim missing", async () => {
    _setJwtVerifyOverrideForTests(async () => ({
      payload: { aud: "university-ecosystem-api", exp: Date.now() / 1000 + 60 },
    }))
    const auth = await validateJwt("any.token.value")
    expect(auth).toEqual(SSR_AUTH_UNAUTH)
  })

  it("returns isAuth=true with role from claims when JWT is valid", async () => {
    _setJwtVerifyOverrideForTests(async () => ({
      payload: { sub: "user-uuid-1", role: "teacher", aud: "university-ecosystem-api" },
    }))
    const auth = await validateJwt("any.token.value")
    expect(auth).toEqual({
      isAuth: true,
      user: { role: "teacher" },
      loading: false,
    })
  })

  it("defaults role to 'student' when claim missing or non-string", async () => {
    _setJwtVerifyOverrideForTests(async () => ({
      payload: { sub: "user-uuid-2", aud: "university-ecosystem-api" },
    }))
    expect(await validateJwt("any.token.value")).toEqual({
      isAuth: true,
      user: { role: "student" },
      loading: false,
    })
  })
})

describe("ssrAuth.extractAuthFromRequest", () => {
  beforeEach(() => {
    _setJwtVerifyOverrideForTests(null)
    vi.unstubAllEnvs()
  })

  afterEach(() => {
    _setJwtVerifyOverrideForTests(null)
    vi.unstubAllEnvs()
  })

  it("returns LHCI mock user when VITE_LHCI=true regardless of cookie", async () => {
    vi.stubEnv("VITE_LHCI", "true")
    const request = new Request("http://localhost/dashboard")
    const auth = await extractAuthFromRequest(request)
    expect(auth).toEqual(SSR_AUTH_LHCI_MOCK)
  })

  it("returns SSR_AUTH_UNAUTH when no cookie header", async () => {
    const request = new Request("http://localhost/dashboard")
    const auth = await extractAuthFromRequest(request)
    expect(auth).toEqual(SSR_AUTH_UNAUTH)
  })

  it("returns SSR_AUTH_UNAUTH when cookie header has no access_token_v2", async () => {
    const request = new Request("http://localhost/dashboard", {
      headers: { Cookie: "csrf_token=abc; ue-mode=dark" },
    })
    const auth = await extractAuthFromRequest(request)
    expect(auth).toEqual(SSR_AUTH_UNAUTH)
  })

  it("returns auth state when cookie present + JWT validates", async () => {
    _setJwtVerifyOverrideForTests(async () => ({
      payload: { sub: "user-1", role: "admin", aud: "university-ecosystem-api" },
    }))
    const request = new Request("http://localhost/dashboard", {
      headers: { Cookie: "access_token_v2=valid.jwt.token" },
    })
    const auth = await extractAuthFromRequest(request)
    expect(auth).toEqual({
      isAuth: true,
      user: { role: "admin" },
      loading: false,
    })
  })

  it("returns SSR_AUTH_UNAUTH when cookie present but JWT invalid", async () => {
    _setJwtVerifyOverrideForTests(async () => null)
    const request = new Request("http://localhost/dashboard", {
      headers: { Cookie: "access_token_v2=tampered.jwt.token" },
    })
    const auth = await extractAuthFromRequest(request)
    expect(auth).toEqual(SSR_AUTH_UNAUTH)
  })
})
