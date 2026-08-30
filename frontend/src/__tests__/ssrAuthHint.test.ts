import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { readSsrAuthHint } from "../hooks/auth/ssrAuthHint"
import type { SsrAuthState } from "../ssrAuth"

describe("readSsrAuthHint", () => {
  // Track original getter to restore after each test
  let originalGetter: typeof globalThis.__ssrAuthGetter__ | undefined

  beforeEach(() => {
    originalGetter = globalThis.__ssrAuthGetter__
    delete (globalThis as { __ssrAuthGetter__?: unknown }).__ssrAuthGetter__
    document.body.innerHTML = ""
  })

  afterEach(() => {
    if (originalGetter) {
      globalThis.__ssrAuthGetter__ = originalGetter
    } else {
      delete (globalThis as { __ssrAuthGetter__?: unknown }).__ssrAuthGetter__
    }
    document.body.innerHTML = ""
  })

  it("returns undefined when getter is not installed", () => {
    expect(readSsrAuthHint()).toBeUndefined()
  })

  it("fails closed when the document is unavailable during SSR", () => {
    const originalDocument = globalThis.document
    // The helper is also called from server-side initialization where no DOM
    // exists. Exercise that branch directly without creating a fake document.
    vi.stubGlobal("document", undefined)
    try {
      expect(readSsrAuthHint()).toBeUndefined()
    } finally {
      vi.stubGlobal("document", originalDocument)
    }
  })

  it("reads the role-only marker emitted on the SSR root shell", () => {
    const root = document.createElement("div")
    root.id = "root"
    root.dataset.ssrAuth = "authenticated:teacher"
    document.body.append(root)

    expect(readSsrAuthHint()).toEqual({
      isAuth: true,
      user: { role: "teacher" },
      loading: false,
    })
  })

  it("ignores malformed or anonymous root markers", () => {
    const root = document.createElement("div")
    root.id = "root"
    document.body.append(root)

    for (const marker of ["anonymous", "authenticated:", "authenticated: "]) {
      root.setAttribute("data-ssr-auth", marker)
      expect(readSsrAuthHint()).toBeUndefined()
    }
  })

  it("returns undefined when getter returns undefined (no per-request store)", () => {
    globalThis.__ssrAuthGetter__ = () => undefined
    expect(readSsrAuthHint()).toBeUndefined()
  })

  it("returns the auth state when getter is installed (authenticated)", () => {
    const state: SsrAuthState = {
      isAuth: true,
      user: { role: "student" },
      loading: false,
    }
    globalThis.__ssrAuthGetter__ = () => state
    expect(readSsrAuthHint()).toEqual(state)
  })

  it("returns the unauth state when getter returns SSR_AUTH_UNAUTH", () => {
    const state: SsrAuthState = {
      isAuth: false,
      user: null,
      loading: false,
    }
    globalThis.__ssrAuthGetter__ = () => state
    expect(readSsrAuthHint()).toEqual(state)
  })

  it("returns the LHCI mock state when getter returns SSR_AUTH_LHCI_MOCK", () => {
    const state: SsrAuthState = {
      isAuth: true,
      user: { role: "student" },
      loading: false,
    }
    globalThis.__ssrAuthGetter__ = () => state
    expect(readSsrAuthHint()).toEqual(state)
  })

  it("returns role 'teacher' for non-student authenticated state", () => {
    const state: SsrAuthState = {
      isAuth: true,
      user: { role: "teacher" },
      loading: false,
    }
    globalThis.__ssrAuthGetter__ = () => state
    expect(readSsrAuthHint()).toEqual(state)
  })

  it("returns role 'admin' for admin authenticated state", () => {
    const state: SsrAuthState = {
      isAuth: true,
      user: { role: "admin" },
      loading: false,
    }
    globalThis.__ssrAuthGetter__ = () => state
    expect(readSsrAuthHint()).toEqual(state)
  })

  it("returns undefined when getter throws (defensive try/catch)", () => {
    globalThis.__ssrAuthGetter__ = () => {
      throw new Error("synthetic getter failure")
    }
    expect(readSsrAuthHint()).toBeUndefined()
  })

  it("preserves auth state across multiple read() calls (no caching layer interferes)", () => {
    const state: SsrAuthState = {
      isAuth: true,
      user: { role: "student" },
      loading: false,
    }
    globalThis.__ssrAuthGetter__ = () => state
    expect(readSsrAuthHint()).toEqual(state)
    expect(readSsrAuthHint()).toEqual(state)
    expect(readSsrAuthHint()).toEqual(state)
  })

  it("reads fresh state when getter return value changes between calls", () => {
    let currentState: SsrAuthState = {
      isAuth: false,
      user: null,
      loading: false,
    }
    globalThis.__ssrAuthGetter__ = () => currentState
    expect(readSsrAuthHint()).toEqual(currentState)

    currentState = { isAuth: true, user: { role: "student" }, loading: false }
    expect(readSsrAuthHint()).toEqual(currentState)
  })
})
