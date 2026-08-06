/**
 * Wave 126 polish — unit tests for `src/router.ts:getRouter()` factory's
 * SSR auth context flow.
 *
 * Verifies the contract introduced in W126 SW3 + SW4: per-request auth
 * state set by `src/server.ts` via `node:async_hooks` AsyncLocalStorage,
 * exposed via `globalThis.__ssrAuthGetter__` getter, consumed by
 * `getRouter()` to construct routers with real auth context for SSR.
 *
 * Tests run in jsdom — `node:async_hooks` import in `src/server.ts` is
 * NOT exercised here; we directly stub `globalThis.__ssrAuthGetter__` to
 * simulate what server.ts would set at runtime, then assert the factory
 * reads from it.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { getRouter, type RouterContext } from "../router"

type SsrAuthGetter = (() => RouterContext["auth"] | undefined) | undefined

declare global {
  // mirrors src/server.ts declaration so tests can stub the getter directly.

  var __ssrAuthGetter__: SsrAuthGetter
}

describe("router.getRouter() — Wave 126 SSR auth context", { timeout: 60000 }, () => {
  let originalGetter: SsrAuthGetter

  beforeEach(() => {
    originalGetter = globalThis.__ssrAuthGetter__
  })

  afterEach(() => {
    globalThis.__ssrAuthGetter__ = originalGetter
  })

  it("falls back to DEFAULT_AUTH (loading:false, isAuth:false) when getter is undefined", () => {
    globalThis.__ssrAuthGetter__ = undefined
    const router = getRouter()
    expect(router.options.context).toBeDefined()
    expect(router.options.context.auth).toEqual({
      isAuth: false,
      user: null,
      loading: false,
    })
  })

  it("falls back to DEFAULT_AUTH when getter returns undefined explicitly", () => {
    globalThis.__ssrAuthGetter__ = () => undefined
    const router = getRouter()
    expect(router.options.context.auth).toEqual({
      isAuth: false,
      user: null,
      loading: false,
    })
  })

  it("uses SSR auth state when getter returns authenticated user", () => {
    const ssrAuth: RouterContext["auth"] = {
      isAuth: true,
      user: { role: "student" },
      loading: false,
    }
    globalThis.__ssrAuthGetter__ = () => ssrAuth
    const router = getRouter()
    expect(router.options.context.auth).toEqual(ssrAuth)
  })

  it("uses SSR auth state with admin role when getter returns admin user", () => {
    globalThis.__ssrAuthGetter__ = () => ({
      isAuth: true,
      user: { role: "admin" },
      loading: false,
    })
    const router = getRouter()
    expect(router.options.context.auth.user?.role).toBe("admin")
    expect(router.options.context.auth.isAuth).toBe(true)
  })

  it("calls getter fresh on each invocation (per-request scope)", () => {
    let callCount = 0
    globalThis.__ssrAuthGetter__ = () => {
      callCount += 1
      return {
        isAuth: callCount % 2 === 0,
        user: null,
        loading: false,
      }
    }
    const r1 = getRouter()
    const r2 = getRouter()
    expect(callCount).toBe(2)
    expect(r1.options.context.auth.isAuth).toBe(false)
    expect(r2.options.context.auth.isAuth).toBe(true)
  })

  it("provides a fresh QueryClient per call (no shared cache state)", () => {
    globalThis.__ssrAuthGetter__ = undefined
    const r1 = getRouter()
    const r2 = getRouter()
    expect(r1.options.context.queryClient).not.toBe(r2.options.context.queryClient)
  })

  it("provides an accessible visible pending component for suspended routes", () => {
    globalThis.__ssrAuthGetter__ = undefined
    const pending = getRouter().options.defaultPendingComponent?.({})

    expect(pending).toMatchObject({
      type: "div",
      props: {
        role: "status",
        "aria-live": "polite",
        children: expect.objectContaining({
          type: "span",
          props: { children: "Loading…" },
        }),
      },
    })
  })
})
