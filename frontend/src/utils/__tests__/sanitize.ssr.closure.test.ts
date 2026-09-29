/** @vitest-environment node */

import { describe, expect, it, vi } from "vitest"

vi.mock("wasm-sanitizer", () => ({
  sanitize_rich_text: vi.fn((source: string) => `[server]${source}`),
  strip_html: vi.fn((source: string) => source),
}))

vi.mock("@/app/logger", () => ({ logWarning: vi.fn() }))

import { sanitizeHttpUrl, sanitizeNewsHtml, sanitizeTelegramUrl } from "../sanitize"

describe("sanitizeNewsHtml on the server", () => {
  it("uses the sanitizer directly without accessing Trusted Types", async () => {
    expect(typeof window).toBe("undefined")
    await expect(sanitizeNewsHtml("<p>safe</p>")).resolves.toBe("[server]<p>safe</p>")
  })
})

describe("URL helpers on the server", () => {
  it("accepts absolute http(s) URLs without a window", () => {
    expect(sanitizeHttpUrl("https://news.test/a?b=1")).toBe("https://news.test/a?b=1")
    expect(sanitizeTelegramUrl("https://t.me/university")).toBe("https://t.me/university")
  })

  it("rejects relative URLs without a window to resolve them against", () => {
    expect(sanitizeHttpUrl("/news/1")).toBeNull()
  })
})
