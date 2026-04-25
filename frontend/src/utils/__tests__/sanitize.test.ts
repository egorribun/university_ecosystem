import { describe, expect, it } from "vitest"
import { sanitizeHttpUrl, sanitizeEmailAddress, sanitizeTelegramUrl } from "../sanitize"

// ---------------------------------------------------------------------------
// sanitizeHttpUrl
// ---------------------------------------------------------------------------
describe("sanitizeHttpUrl", () => {
  // Allowed protocols
  it("passes through a valid https URL", () => {
    const url = "https://example.com/path?q=1"
    expect(sanitizeHttpUrl(url)).toBe(url)
  })

  it("passes through a valid http URL", () => {
    const url = "http://example.com/"
    expect(sanitizeHttpUrl(url)).toBe(url)
  })

  // Protocol blocking
  it("blocks javascript: protocol", () => {
    expect(sanitizeHttpUrl("javascript:alert(1)")).toBeNull()
  })

  it("blocks data: protocol", () => {
    expect(sanitizeHttpUrl("data:text/html,<h1>hi</h1>")).toBeNull()
  })

  it("blocks ftp: protocol", () => {
    expect(sanitizeHttpUrl("ftp://files.example.com/")).toBeNull()
  })

  // Credentials in URL
  it("blocks URLs with username", () => {
    expect(sanitizeHttpUrl("https://user@example.com")).toBeNull()
  })

  it("blocks URLs with password", () => {
    expect(sanitizeHttpUrl("https://user:pass@example.com")).toBeNull() // pragma: allowlist secret
  })

  // Null / empty / invalid
  it("returns null for null input", () => {
    expect(sanitizeHttpUrl(null)).toBeNull()
  })

  it("returns null for empty string", () => {
    expect(sanitizeHttpUrl("")).toBeNull()
  })

  it("returns null for undefined", () => {
    expect(sanitizeHttpUrl(undefined)).toBeNull()
  })

  it("resolves bare words against window.location.origin (jsdom localhost) — returns a valid http URL, not null", () => {
    // In a browser context, new URL("not a url", "http://localhost") succeeds;
    // the function only blocks by protocol (javascript:, ftp:, etc.) and credentials.
    // Truly unparseable inputs like pure whitespace return null.
    const result = sanitizeHttpUrl("not a url")
    // jsdom resolves this as http://localhost/not%20a%20url — valid http → passes through
    expect(result).not.toBeNull()
    expect(result).toMatch(/^http:\/\//)
  })
})

// ---------------------------------------------------------------------------
// sanitizeEmailAddress
// ---------------------------------------------------------------------------
describe("sanitizeEmailAddress", () => {
  it("returns a valid email unchanged", () => {
    expect(sanitizeEmailAddress("user@example.com")).toBe("user@example.com")
  })

  it("trims surrounding whitespace", () => {
    expect(sanitizeEmailAddress("  user@example.com  ")).toBe("user@example.com")
  })

  it("returns empty string for null", () => {
    expect(sanitizeEmailAddress(null)).toBe("")
  })

  it("returns empty string for undefined", () => {
    expect(sanitizeEmailAddress(undefined)).toBe("")
  })

  it("returns empty string for invalid email (no @)", () => {
    expect(sanitizeEmailAddress("notanemail")).toBe("")
  })

  it("returns empty string for email with spaces", () => {
    expect(sanitizeEmailAddress("user @example.com")).toBe("")
  })

  it("returns empty string for empty string", () => {
    expect(sanitizeEmailAddress("")).toBe("")
  })
})

// ---------------------------------------------------------------------------
// sanitizeTelegramUrl
// ---------------------------------------------------------------------------
describe("sanitizeTelegramUrl", () => {
  // Username format
  it("converts @username to t.me URL", () => {
    expect(sanitizeTelegramUrl("@username123")).toBe("https://t.me/username123")
  })

  it("converts bare username to t.me URL", () => {
    expect(sanitizeTelegramUrl("username123")).toBe("https://t.me/username123")
  })

  it("passes through a valid t.me URL", () => {
    expect(sanitizeTelegramUrl("https://t.me/username123")).toBe("https://t.me/username123")
  })

  it("passes through telegram.me URL", () => {
    expect(sanitizeTelegramUrl("https://telegram.me/channel")).toBe(
      "https://telegram.me/channel"
    )
  })

  // Invalid usernames
  it("rejects username shorter than 5 chars", () => {
    expect(sanitizeTelegramUrl("@ab")).toBe("")
  })

  it("rejects username longer than 32 chars", () => {
    expect(sanitizeTelegramUrl("a".repeat(33))).toBe("")
  })

  it("rejects username with invalid characters", () => {
    expect(sanitizeTelegramUrl("user name")).toBe("") // space not allowed
    expect(sanitizeTelegramUrl("user-name")).toBe("") // hyphen not allowed
  })

  // Path traversal
  it("rejects path-traversal attempts", () => {
    expect(sanitizeTelegramUrl("../../admin")).toBe("")
  })

  // Non-Telegram https URLs
  it("rejects non-Telegram https URL", () => {
    expect(sanitizeTelegramUrl("https://evil.com/page")).toBe("")
  })

  // Null / empty
  it("returns empty string for null", () => {
    expect(sanitizeTelegramUrl(null)).toBe("")
  })

  it("returns empty string for empty string", () => {
    expect(sanitizeTelegramUrl("")).toBe("")
  })
})
