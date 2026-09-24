/** @vitest-environment node */

import { afterEach, describe, expect, it, vi } from "vitest"

import { resolveLoaderLang } from "../loaderLang"

const originalGetter = globalThis.__ssrLangGetter__

afterEach(() => {
  globalThis.__ssrLangGetter__ = originalGetter
  vi.unstubAllGlobals()
})

describe("resolveLoaderLang on the server", () => {
  it("uses the default when neither an SSR getter nor a browser exists", () => {
    globalThis.__ssrLangGetter__ = undefined

    expect(typeof window).toBe("undefined")
    expect(resolveLoaderLang()).toBe("ru")
  })

  it("never reads a process-global localStorage outside the browser", () => {
    globalThis.__ssrLangGetter__ = undefined
    // Node can expose a process-wide Web Storage shared by every request.
    vi.stubGlobal("localStorage", { getItem: () => "en" })

    expect(typeof window).toBe("undefined")
    expect(resolveLoaderLang()).toBe("ru")
  })
})
