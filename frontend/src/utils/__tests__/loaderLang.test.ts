/**
 * @fileoverview Wave 129 polish — direct unit tests for `resolveLoaderLang()`.
 *
 * Closes part of the W129 vitest-delta-zero honesty caveat. The helper's
 * dual-path (SSR via globalThis getter / client via localStorage) needs
 * explicit coverage because the loader path differs from existing usage
 * patterns in the codebase.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { resolveLoaderLang } from "../loaderLang"

describe("resolveLoaderLang", () => {
  const ORIGINAL_GETTER = globalThis.__ssrLangGetter__

  beforeEach(() => {
    // Reset any test-installed getter from prior test
    globalThis.__ssrLangGetter__ = ORIGINAL_GETTER
    // Clear localStorage between tests so client-path scenarios are isolated.
    // jsdom defines localStorage so this is safe; tests below explicitly cover
    // the typeof window === "undefined" branch via getter manipulation.
    try {
      localStorage.clear()
    } catch {
      // private-browsing path; tests cover this explicitly
    }
  })

  afterEach(() => {
    globalThis.__ssrLangGetter__ = ORIGINAL_GETTER
  })

  // ---------------------------------------------------------------------------
  // SSR path — globalThis.__ssrLangGetter__ populated by server.ts
  // ---------------------------------------------------------------------------

  it("returns 'ru' from SSR getter when cookie is 'ru'", () => {
    globalThis.__ssrLangGetter__ = () => "ru"
    expect(resolveLoaderLang()).toBe("ru")
  })

  it("returns 'en' from SSR getter when cookie is 'en'", () => {
    globalThis.__ssrLangGetter__ = () => "en"
    expect(resolveLoaderLang()).toBe("en")
  })

  it("falls through to client path when SSR getter returns undefined", () => {
    globalThis.__ssrLangGetter__ = () => undefined
    localStorage.setItem("ue:language", "en")
    expect(resolveLoaderLang()).toBe("en")
  })

  it("falls through to client path when SSR getter is undefined", () => {
    globalThis.__ssrLangGetter__ = undefined
    localStorage.setItem("ue:language", "ru")
    expect(resolveLoaderLang()).toBe("ru")
  })

  // ---------------------------------------------------------------------------
  // Client path — localStorage `ue:language` mirror
  // ---------------------------------------------------------------------------

  it("returns 'ru' from localStorage when getter is undefined", () => {
    globalThis.__ssrLangGetter__ = undefined
    localStorage.setItem("ue:language", "ru")
    expect(resolveLoaderLang()).toBe("ru")
  })

  it("returns 'en' from localStorage when getter is undefined", () => {
    globalThis.__ssrLangGetter__ = undefined
    localStorage.setItem("ue:language", "en")
    expect(resolveLoaderLang()).toBe("en")
  })

  it("falls back to 'ru' when localStorage has unsupported value", () => {
    globalThis.__ssrLangGetter__ = undefined
    localStorage.setItem("ue:language", "fr") // unsupported lang
    expect(resolveLoaderLang()).toBe("ru")
  })

  it("falls back to 'ru' when localStorage has empty string", () => {
    globalThis.__ssrLangGetter__ = undefined
    localStorage.setItem("ue:language", "")
    expect(resolveLoaderLang()).toBe("ru")
  })

  it("falls back to 'ru' when localStorage key is absent", () => {
    globalThis.__ssrLangGetter__ = undefined
    // Don't set the key
    expect(resolveLoaderLang()).toBe("ru")
  })

  // ---------------------------------------------------------------------------
  // Defensive — try/catch around localStorage (Safari private-browsing pattern)
  // ---------------------------------------------------------------------------

  it("falls back to 'ru' when localStorage.getItem throws (private-browsing)", () => {
    globalThis.__ssrLangGetter__ = undefined
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("Safari private browsing — quota exceeded")
    })

    expect(resolveLoaderLang()).toBe("ru")

    spy.mockRestore()
  })

  // ---------------------------------------------------------------------------
  // Priority — SSR path takes precedence over client path
  // ---------------------------------------------------------------------------

  it("SSR getter result wins over localStorage when both are set", () => {
    globalThis.__ssrLangGetter__ = () => "en"
    localStorage.setItem("ue:language", "ru") // would otherwise resolve to "ru"
    expect(resolveLoaderLang()).toBe("en")
  })

  it("SSR getter undefined value falls through to localStorage", () => {
    globalThis.__ssrLangGetter__ = () => undefined
    localStorage.setItem("ue:language", "en")
    expect(resolveLoaderLang()).toBe("en")
  })
})
