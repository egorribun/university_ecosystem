import { describe, expect, it, vi } from "vitest"
import type { ParsedLocation } from "@tanstack/react-router"

import {
  evaluateAuthGuard,
  evaluatePublicGuard,
  evaluateAdminGuard,
  type GuardState,
  type GuardUser,
} from "../guards"

/**
 * Wave 179 SW8 — Unit tests for route guard pure functions (closes W174
 * §Honesty #4-routeGuards). 11 test cases covering all branches:
 *  - loading short-circuit (3 guards × 1 case = 3 tests)
 *  - unauth/authed branches (auth: 2, public: 2, admin: 3)
 *  - VITE_LHCI bypass (auth: 1)
 *  - Admin role check (admin: 2)
 *
 * Tests verify the throw-based redirect semantics that TanStack Router's
 * `redirect()` returns. The thrown value is a Response-like object with shape
 * `{ options: { to, search, statusCode } }` (verified via probe). We catch
 * + assert on `r.options.to` + `r.options.search?.redirect` rather than
 * relying on TanStack Router runtime (which requires a router context).
 */

interface RedirectThrown {
  options?: {
    to?: string
    search?: { redirect?: string }
    statusCode?: number
  }
}

const adminUser: GuardUser = { role: "admin" }
const studentUser: GuardUser = { role: "student" }

const mockLocation: ParsedLocation = {
  href: "http://localhost/events",
  pathname: "/events",
  search: {},
  searchStr: "",
  hash: "",
  state: {},
} as unknown as ParsedLocation

describe("guards.ts (W179 SW8)", () => {
  describe("evaluateAuthGuard", () => {
    it("returns void on loading state (no throw)", () => {
      const state: GuardState = { user: null, loading: true }
      expect(() => evaluateAuthGuard(state, mockLocation)).not.toThrow()
    })

    it("returns void when user is authed", () => {
      const state: GuardState = { user: studentUser, loading: false }
      expect(() => evaluateAuthGuard(state, mockLocation)).not.toThrow()
    })

    it("throws redirect to /login with search.redirect when unauth", () => {
      const state: GuardState = { user: null, loading: false }
      let caught: unknown
      try {
        evaluateAuthGuard(state, mockLocation)
      } catch (e) {
        caught = e
      }
      expect(caught).toBeDefined()
      const r = caught as RedirectThrown
      expect(r.options?.to).toBe("/login")
      expect(r.options?.search?.redirect).toBe("http://localhost/events")
      expect(r.options?.statusCode).toBe(307)
    })

    it("returns void under VITE_LHCI bypass even when unauth", () => {
      // Mock VITE_LHCI bypass — Vite literally substitutes at build time, but
      // for tests we use vi.stubEnv to simulate the truthy branch.
      vi.stubEnv("VITE_LHCI", "true")
      const state: GuardState = { user: null, loading: false }
      expect(() => evaluateAuthGuard(state, mockLocation)).not.toThrow()
      vi.unstubAllEnvs()
    })
  })

  describe("evaluatePublicGuard", () => {
    it("returns void on loading state (no throw)", () => {
      const state: GuardState = { user: null, loading: true }
      expect(() => evaluatePublicGuard(state)).not.toThrow()
    })

    it("returns void when user is unauthed (proceed to /login form)", () => {
      const state: GuardState = { user: null, loading: false }
      expect(() => evaluatePublicGuard(state)).not.toThrow()
    })

    it("throws redirect to /dashboard when user is authed", () => {
      const state: GuardState = { user: studentUser, loading: false }
      let caught: unknown
      try {
        evaluatePublicGuard(state)
      } catch (e) {
        caught = e
      }
      expect(caught).toBeDefined()
      const r = caught as RedirectThrown
      expect(r.options?.to).toBe("/dashboard")
    })
  })

  describe("evaluateAdminGuard", () => {
    it("returns void on loading state (no throw)", () => {
      const state: GuardState = { user: null, loading: true }
      expect(() => evaluateAdminGuard(state)).not.toThrow()
    })

    it("throws redirect to /login when unauth", () => {
      const state: GuardState = { user: null, loading: false }
      let caught: unknown
      try {
        evaluateAdminGuard(state)
      } catch (e) {
        caught = e
      }
      expect(caught).toBeDefined()
      const r = caught as RedirectThrown
      expect(r.options?.to).toBe("/login")
    })

    it("throws redirect to /dashboard when authed non-admin", () => {
      const state: GuardState = { user: studentUser, loading: false }
      let caught: unknown
      try {
        evaluateAdminGuard(state)
      } catch (e) {
        caught = e
      }
      expect(caught).toBeDefined()
      const r = caught as RedirectThrown
      expect(r.options?.to).toBe("/dashboard")
    })

    it("returns void when authed admin", () => {
      const state: GuardState = { user: adminUser, loading: false }
      expect(() => evaluateAdminGuard(state)).not.toThrow()
    })
  })
})
