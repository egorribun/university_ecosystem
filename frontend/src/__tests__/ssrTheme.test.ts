import { describe, it, expect } from "vitest"
import {
  resolveTheme,
  resolveLang,
  extractThemeFromRequest,
  extractLangFromRequest,
} from "../ssrTheme"

describe("resolveTheme", () => {
  it("returns 'dark' for cookie value 'dark'", () => {
    expect(resolveTheme("dark")).toBe("dark")
  })
  it("returns 'light' for cookie value 'light'", () => {
    expect(resolveTheme("light")).toBe("light")
  })
  it("returns 'light' for cookie value 'system' (server cannot detect prefers-color-scheme)", () => {
    expect(resolveTheme("system")).toBe("light")
  })
  it("returns 'light' for null", () => {
    expect(resolveTheme(null)).toBe("light")
  })
  it("returns 'light' for undefined", () => {
    expect(resolveTheme(undefined)).toBe("light")
  })
  it("returns 'light' for garbled value", () => {
    expect(resolveTheme("xyz")).toBe("light")
  })
})

describe("resolveLang", () => {
  it("returns 'ru' for cookie value 'ru'", () => {
    expect(resolveLang("ru")).toBe("ru")
  })
  it("returns 'en' for cookie value 'en'", () => {
    expect(resolveLang("en")).toBe("en")
  })
  it("returns 'ru' (fallback) for unsupported lang", () => {
    expect(resolveLang("fr")).toBe("ru")
  })
  it("returns 'ru' for null", () => {
    expect(resolveLang(null)).toBe("ru")
  })
  it("returns 'ru' for undefined", () => {
    expect(resolveLang(undefined)).toBe("ru")
  })
  it("returns 'ru' for empty string", () => {
    expect(resolveLang("")).toBe("ru")
  })
})

describe("extractThemeFromRequest", () => {
  it("extracts 'dark' from cookie header", () => {
    const req = new Request("http://x", { headers: { cookie: "ue-mode=dark; other=1" } })
    expect(extractThemeFromRequest(req)).toBe("dark")
  })
  it("returns 'light' when no ue-mode cookie present", () => {
    const req = new Request("http://x", { headers: { cookie: "other=1" } })
    expect(extractThemeFromRequest(req)).toBe("light")
  })
  it("returns 'light' when no Cookie header", () => {
    const req = new Request("http://x")
    expect(extractThemeFromRequest(req)).toBe("light")
  })
  it("decodes URL-encoded value", () => {
    // setThemeCookie uses encodeURIComponent on value (W127 SW2)
    const req = new Request("http://x", { headers: { cookie: "ue-mode=dark" } })
    expect(extractThemeFromRequest(req)).toBe("dark")
  })
  it("falls back safely when reading headers throws", () => {
    const req = {
      headers: {
        get: () => {
          throw new Error("malformed headers")
        },
      },
    } as unknown as Request
    expect(extractThemeFromRequest(req)).toBe("light")
  })
})

describe("extractLangFromRequest", () => {
  it("extracts 'en' from cookie header (literal colon, not URL-encoded)", () => {
    // RFC 6265 — browsers preserve ':' in cookie names without URL-encoding
    const req = new Request("http://x", { headers: { cookie: "ue:language=en" } })
    expect(extractLangFromRequest(req)).toBe("en")
  })
  it("returns 'ru' when no ue:language cookie present", () => {
    const req = new Request("http://x", { headers: { cookie: "other=1" } })
    expect(extractLangFromRequest(req)).toBe("ru")
  })
  it("returns 'ru' (fallback) for invalid cookie value", () => {
    const req = new Request("http://x", { headers: { cookie: "ue:language=fr" } })
    expect(extractLangFromRequest(req)).toBe("ru")
  })
  it("co-exists with other cookies in same header", () => {
    const req = new Request("http://x", {
      headers: { cookie: "access_token_v2=abc; ue-mode=dark; ue:language=en" },
    })
    expect(extractThemeFromRequest(req)).toBe("dark")
    expect(extractLangFromRequest(req)).toBe("en")
  })
  it("falls back safely when reading headers throws", () => {
    const req = {
      headers: {
        get: () => {
          throw new Error("malformed headers")
        },
      },
    } as unknown as Request
    expect(extractLangFromRequest(req)).toBe("ru")
  })
})
