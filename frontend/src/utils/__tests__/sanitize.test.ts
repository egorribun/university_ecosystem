import { describe, expect, it, vi, beforeEach } from "vitest"

const mocks = vi.hoisted(() => ({
  sanitize_rich_text: vi.fn((s: string) => s),
  strip_html: vi.fn((s: string) => s.replace(/<[^>]*>/g, "")),
  logWarning: vi.fn(),
}))

vi.mock("wasm-sanitizer", () => ({
  sanitize_rich_text: mocks.sanitize_rich_text,
  strip_html: mocks.strip_html,
}))

vi.mock("@/app/logger", () => ({
  logWarning: mocks.logWarning,
}))

import {
  sanitizeNewsHtml,
  sanitizeNewsText,
  sanitizeHttpUrl,
  sanitizeEmailAddress,
  sanitizeTelegramUrl,
} from "@/utils/sanitize"

beforeEach(() => {
  vi.clearAllMocks()
})

describe("sanitize utilities", () => {
  describe("sanitizeNewsHtml", () => {
    it("returns empty string for null input", async () => {
      const result = await sanitizeNewsHtml(null)
      expect(mocks.sanitize_rich_text).toHaveBeenCalledWith("")
    })

    it("returns empty string for undefined input", async () => {
      await sanitizeNewsHtml(undefined)
      expect(mocks.sanitize_rich_text).toHaveBeenCalledWith("")
    })

    it("passes source through sanitize_rich_text", async () => {
      mocks.sanitize_rich_text.mockReturnValue("<p>safe</p>")
      const result = await sanitizeNewsHtml("<p>safe</p><script>alert(1)</script>")
      expect(result).toBe("<p>safe</p>")
    })

    it("falls back to regex strip when wasm-sanitizer throws", async () => {
      mocks.sanitize_rich_text.mockImplementation(() => {
        throw new Error("WASM unavailable")
      })

      const result = await sanitizeNewsHtml("<p>hello</p><script>bad</script>")
      expect(result).toBe("hellobad")
    })
  })

  describe("sanitizeNewsText", () => {
    it("strips HTML tags via strip_html", async () => {
      mocks.strip_html.mockReturnValue("plain text")
      const result = await sanitizeNewsText("<p>plain text</p>")
      expect(result).toBe("plain text")
    })

    it("returns empty string for null input", async () => {
      const result = await sanitizeNewsText(null)
      expect(mocks.strip_html).toHaveBeenCalledWith("")
    })

    it("falls back to regex strip when wasm-sanitizer throws", async () => {
      mocks.strip_html.mockImplementation(() => {
        throw new Error("WASM unavailable")
      })

      const result = await sanitizeNewsText("<div>content</div>")
      expect(result).toBe("content")
    })
  })

  describe("sanitizeHttpUrl", () => {
    it("returns null for null input", () => {
      expect(sanitizeHttpUrl(null)).toBeNull()
    })

    it("returns null for undefined input", () => {
      expect(sanitizeHttpUrl(undefined)).toBeNull()
    })

    it("returns null for empty string", () => {
      expect(sanitizeHttpUrl("")).toBeNull()
    })

    it("allows valid http URL", () => {
      const result = sanitizeHttpUrl("http://example.com/page")
      expect(result).toBe("http://example.com/page")
    })

    it("allows valid https URL", () => {
      const result = sanitizeHttpUrl("https://example.com/page")
      expect(result).toBe("https://example.com/page")
    })

    it("rejects javascript: protocol", () => {
      expect(sanitizeHttpUrl("javascript:alert(1)")).toBeNull()
    })

    it("rejects data: protocol", () => {
      expect(sanitizeHttpUrl("data:text/html,<h1>hello</h1>")).toBeNull()
    })

    it("rejects ftp: protocol", () => {
      expect(sanitizeHttpUrl("ftp://files.example.com/file")).toBeNull()
    })

    it("rejects URLs with username/password", () => {
      expect(sanitizeHttpUrl("https://admin:pass@evil.com")).toBeNull()
    })

    it("handles relative URLs by resolving against window.location.origin", () => {
      const result = sanitizeHttpUrl("/path/to/page")
      expect(result).toMatch(/^https?:\/\//)
      expect(result).toContain("/path/to/page")
    })
  })

  describe("sanitizeEmailAddress", () => {
    it("returns empty string for null", () => {
      expect(sanitizeEmailAddress(null)).toBe("")
    })

    it("returns empty string for undefined", () => {
      expect(sanitizeEmailAddress(undefined)).toBe("")
    })

    it("returns empty string for empty string", () => {
      expect(sanitizeEmailAddress("")).toBe("")
    })

    it("returns valid email as-is", () => {
      expect(sanitizeEmailAddress("user@example.com")).toBe("user@example.com")
    })

    it("trims whitespace around valid email", () => {
      expect(sanitizeEmailAddress("  user@example.com  ")).toBe("user@example.com")
    })

    it("rejects email without @", () => {
      expect(sanitizeEmailAddress("userexample.com")).toBe("")
    })

    it("rejects email without domain", () => {
      expect(sanitizeEmailAddress("user@")).toBe("")
    })

    it("rejects email with spaces", () => {
      expect(sanitizeEmailAddress("user @example.com")).toBe("")
    })

    it("rejects email without TLD", () => {
      expect(sanitizeEmailAddress("user@example")).toBe("")
    })
  })

  describe("sanitizeTelegramUrl", () => {
    it("returns empty string for null", () => {
      expect(sanitizeTelegramUrl(null)).toBe("")
    })

    it("returns empty string for undefined", () => {
      expect(sanitizeTelegramUrl(undefined)).toBe("")
    })

    it("returns empty string for empty string", () => {
      expect(sanitizeTelegramUrl("")).toBe("")
    })

    it("converts @username to https://t.me/username", () => {
      expect(sanitizeTelegramUrl("@university")).toBe("https://t.me/university")
    })

    it("accepts valid t.me URL", () => {
      const result = sanitizeTelegramUrl("https://t.me/university")
      expect(result).toContain("t.me")
    })

    it("accepts valid telegram.me URL", () => {
      const result = sanitizeTelegramUrl("https://telegram.me/university")
      expect(result).toContain("telegram.me")
    })

    it("rejects non-telegram HTTP URLs", () => {
      expect(sanitizeTelegramUrl("https://evil.com/phish")).toBe("")
    })

    it("rejects short usernames (less than 5 chars)", () => {
      expect(sanitizeTelegramUrl("@abc")).toBe("")
    })

    it("rejects usernames with special characters", () => {
      expect(sanitizeTelegramUrl("@user!name")).toBe("")
    })

    it("rejects path traversal attempts", () => {
      expect(sanitizeTelegramUrl("../../admin")).toBe("")
    })

    it("handles double @ prefix", () => {
      expect(sanitizeTelegramUrl("@@username_valid")).toBe("https://t.me/username_valid")
    })

    it("rejects usernames longer than 32 characters", () => {
      const longUsername = "@" + "a".repeat(33)
      expect(sanitizeTelegramUrl(longUsername)).toBe("")
    })

    it("accepts username at exactly 32 characters", () => {
      const exactUsername = "@" + "a".repeat(32)
      expect(sanitizeTelegramUrl(exactUsername)).toBe("https://t.me/" + "a".repeat(32))
    })

    it("accepts username at exactly 5 characters", () => {
      expect(sanitizeTelegramUrl("@abcde")).toBe("https://t.me/abcde")
    })
  })
})
