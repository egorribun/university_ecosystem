import { describe, expect, it } from "vitest"
import { sanitizeEmailAddress, sanitizeHttpUrl, sanitizeTelegramUrl } from "../sanitize"

describe("sanitizeHttpUrl", () => {
  it("resolves same-origin relative URLs against the page origin", () => {
    expect(sanitizeHttpUrl("/news/1?x=2")).toBe(`${window.location.origin}/news/1?x=2`)
  })

  it("normalizes the scheme and host of absolute URLs", () => {
    expect(sanitizeHttpUrl("HTTPS://News.TEST/Path")).toBe("https://news.test/Path")
    expect(sanitizeHttpUrl("http://news.test")).toBe("http://news.test/")
  })

  it.each([
    ["a username", "https://user@news.test/"],
    ["a password", "https://:secret@news.test/"], // pragma: allowlist secret
    ["both credentials", "https://user:secret@news.test/"], // pragma: allowlist secret
  ])("rejects URLs with %s", (_label, url) => {
    expect(sanitizeHttpUrl(url)).toBeNull()
  })

  it.each(["javascript:alert(1)", "ftp://files.test/a", "mailto:a@b.test", "http://", ""])(
    "rejects %j",
    (url) => {
      expect(sanitizeHttpUrl(url)).toBeNull()
    }
  )
})

describe("sanitizeEmailAddress", () => {
  it("trims a valid address", () => {
    expect(sanitizeEmailAddress("  student@uni.test  ")).toBe("student@uni.test")
  })

  it.each([null, undefined, "", "not-an-email", "a@b", "a b@uni.test"])("rejects %j", (raw) => {
    expect(sanitizeEmailAddress(raw)).toBe("")
  })
})

describe("sanitizeTelegramUrl", () => {
  it.each([
    ["https://t.me/university", "https://t.me/university"],
    ["https://T.ME/university", "https://t.me/university"],
    ["  https://telegram.me/university  ", "https://telegram.me/university"],
    ["@university", "https://t.me/university"],
    ["@@university_2026", "https://t.me/university_2026"],
  ])("accepts %j", (raw, expected) => {
    expect(sanitizeTelegramUrl(raw)).toBe(expected)
  })

  it.each([
    "https://evil.test/university",
    "https://t.me.evil.test/university",
    "https://user@t.me/university",
    "http://",
    "httpx",
    "@abc",
    "../../admin",
  ])("rejects %j", (raw) => {
    expect(sanitizeTelegramUrl(raw)).toBe("")
  })
})
