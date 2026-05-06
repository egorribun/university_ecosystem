import { describe, it, expect } from "vitest"
import {
  buildSsrStubUser,
  resolveSsrInitialUserState,
  resolveSsrInitialInitializing,
  type SsrAuthHint,
} from "@/hooks/auth/useProfileSync"

describe("buildSsrStubUser", () => {
  it("creates a User with the supplied role and stub id", () => {
    const user = buildSsrStubUser("student")
    expect(user.id).toBe("ssr-stub")
    expect(user.role).toBe("student")
  })

  it("uses empty strings/nulls for PII fields (no SSR HTML leakage)", () => {
    const user = buildSsrStubUser("student")
    expect(user.email).toBe("")
    expect(user.full_name).toBe("")
    expect(user.avatar_url).toBeNull()
    expect(user.cover_url).toBeNull()
    expect(user.group_id).toBeNull()
    expect(user.profile_detail).toBeUndefined()
    expect(user.education_path).toBeUndefined()
  })

  it("preserves role 'teacher' through to the stub", () => {
    expect(buildSsrStubUser("teacher").role).toBe("teacher")
  })

  it("preserves role 'admin' through to the stub", () => {
    expect(buildSsrStubUser("admin").role).toBe("admin")
  })

  it("returns is_active=true so route guards see authenticated state", () => {
    expect(buildSsrStubUser("student").is_active).toBe(true)
  })

  it("returns mfa_required=false (no MFA gate on SSR; client re-evaluates)", () => {
    expect(buildSsrStubUser("student").mfa_required).toBe(false)
  })

  it("coerces unknown role to 'student' fallback (defensive)", () => {
    // SsrAuthState.user.role is typed as `string` (extracted from JWT
    // payload by validateJwt). Unknown values fall back to "student"
    // matching ssrAuth.ts validateJwt's default-on-missing pattern.
    expect(buildSsrStubUser("hacker").role).toBe("student")
    expect(buildSsrStubUser("").role).toBe("student")
  })

  it("preserves role 'superuser' through coercion", () => {
    expect(buildSsrStubUser("superuser").role).toBe("superuser")
  })

  it("preserves role 'anonymous' through coercion", () => {
    expect(buildSsrStubUser("anonymous").role).toBe("anonymous")
  })
})

describe("resolveSsrInitialUserState", () => {
  it("returns null when hint is undefined", () => {
    expect(resolveSsrInitialUserState(undefined)).toBeNull()
  })

  it("returns null when hint.isAuth is false", () => {
    const hint: SsrAuthHint = { isAuth: false, user: null }
    expect(resolveSsrInitialUserState(hint)).toBeNull()
  })

  it("returns null when hint.isAuth is true but user is null", () => {
    // Defensive — should not happen in practice, but guard against malformed
    // SsrAuthState slipping through validateJwt's role-extraction path
    const hint: SsrAuthHint = { isAuth: true, user: null }
    expect(resolveSsrInitialUserState(hint)).toBeNull()
  })

  it("returns SSR stub User when hint.isAuth is true and user has role", () => {
    const hint: SsrAuthHint = { isAuth: true, user: { role: "student" } }
    const result = resolveSsrInitialUserState(hint)
    expect(result).not.toBeNull()
    expect(result?.id).toBe("ssr-stub")
    expect(result?.role).toBe("student")
  })

  it("threads role 'teacher' through to the resolved User stub", () => {
    const hint: SsrAuthHint = { isAuth: true, user: { role: "teacher" } }
    expect(resolveSsrInitialUserState(hint)?.role).toBe("teacher")
  })
})

describe("resolveSsrInitialInitializing", () => {
  it("returns true when hint is undefined (client init useEffect must run)", () => {
    expect(resolveSsrInitialInitializing(undefined)).toBe(true)
  })

  it("returns true when hint.isAuth is false (no SSR-resolved user)", () => {
    const hint: SsrAuthHint = { isAuth: false, user: null }
    expect(resolveSsrInitialInitializing(hint)).toBe(true)
  })

  it("returns false when hint.isAuth is true (init complete via SSR stub)", () => {
    const hint: SsrAuthHint = { isAuth: true, user: { role: "student" } }
    expect(resolveSsrInitialInitializing(hint)).toBe(false)
  })
})
