import { describe, expect, it } from "vitest"
import { resolveRedirectPath } from "../redirect"

/**
 * Wave 179 SW4 — Unit tests for `resolveRedirectPath` (closes W177 §Honesty #3).
 *
 * Covers race-regression scenarios + security (cross-origin) + malformed-URL
 * fallback. Pairs with extended Login.test.tsx + _public.test.tsx integration
 * tests that exercise the full useLoginFlow → navigate chain.
 */

describe("resolveRedirectPath (W179 SW4)", () => {
  it("returns absolute URL pathname for same-origin (writer-canonical case)", () => {
    // _auth.tsx:47 writes `redirect: location.href` = full URL like
    // "http://localhost/events"; helper extracts the pathname.
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { origin: "http://localhost" },
    })
    expect(resolveRedirectPath("http://localhost/events")).toBe("/events")
    expect(resolveRedirectPath("http://localhost/news/article-123")).toBe("/news/article-123")
    expect(resolveRedirectPath("http://localhost/schedule")).toBe("/schedule")
  })

  it("returns relative path verbatim", () => {
    // Defensive — supports hand-written or test-injected relative paths
    expect(resolveRedirectPath("/events")).toBe("/events")
    expect(resolveRedirectPath("/news/article-123")).toBe("/news/article-123")
    expect(resolveRedirectPath("/dashboard")).toBe("/dashboard")
  })

  it("returns fallback for cross-origin URL (security)", () => {
    // Open-redirect attack vector — attacker injects ?redirect=http://evil.com/x
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { origin: "http://localhost" },
    })
    expect(resolveRedirectPath("http://evil.com/phishing")).toBe("/dashboard")
    expect(resolveRedirectPath("https://attacker.example/login")).toBe("/dashboard")
  })

  it("returns fallback for protocol-relative URL (security)", () => {
    // `//evil.com/x` is protocol-relative — browser inherits scheme from page
    // and treats as cross-origin. URL constructor with no base throws here.
    expect(resolveRedirectPath("//evil.com/phishing")).toBe("/dashboard")
  })

  it("returns fallback for malformed URL", () => {
    expect(resolveRedirectPath("not-a-url")).toBe("/dashboard")
    expect(resolveRedirectPath("javascript:alert(1)")).toBe("/dashboard") // XSS attempt
    expect(resolveRedirectPath("http:///")).toBe("/dashboard") // missing host
  })

  it("returns fallback for non-string input", () => {
    expect(resolveRedirectPath(undefined)).toBe("/dashboard")
    expect(resolveRedirectPath(null)).toBe("/dashboard")
    expect(resolveRedirectPath(123)).toBe("/dashboard")
    expect(resolveRedirectPath({})).toBe("/dashboard")
    expect(resolveRedirectPath([])).toBe("/dashboard")
  })

  it("returns fallback for empty string", () => {
    expect(resolveRedirectPath("")).toBe("/dashboard")
  })

  it("respects custom fallback", () => {
    expect(resolveRedirectPath(undefined, "/")).toBe("/")
    expect(resolveRedirectPath("not-a-url", "/login")).toBe("/login")
    expect(resolveRedirectPath("http://evil.com/x", "/")).toBe("/")
  })

  it("returns fallback when same-origin URL has empty pathname", () => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { origin: "http://localhost" },
    })
    // URL constructor sets pathname to "/" for "http://localhost" (no path)
    // — that's a valid pathname, not empty, so should return "/"
    expect(resolveRedirectPath("http://localhost")).toBe("/")
    expect(resolveRedirectPath("http://localhost/")).toBe("/")
  })
})
