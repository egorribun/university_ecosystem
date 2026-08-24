/** @vitest-environment node */

import { afterEach, describe, expect, it } from "vitest"

import { resolveLoaderLang } from "../loaderLang"

const originalGetter = globalThis.__ssrLangGetter__

afterEach(() => {
  globalThis.__ssrLangGetter__ = originalGetter
})

describe("resolveLoaderLang on the server", () => {
  it("uses the default when neither an SSR getter nor a browser exists", () => {
    globalThis.__ssrLangGetter__ = undefined

    expect(typeof window).toBe("undefined")
    expect(resolveLoaderLang()).toBe("ru")
  })
})
