/** @vitest-environment node */

import { describe, expect, it, vi } from "vitest"

vi.mock("wasm-sanitizer", () => ({
  sanitize_rich_text: vi.fn((source: string) => `[server]${source}`),
  strip_html: vi.fn((source: string) => source),
}))

vi.mock("@/app/logger", () => ({ logWarning: vi.fn() }))

import { sanitizeNewsHtml } from "../sanitize"

describe("sanitizeNewsHtml on the server", () => {
  it("uses the sanitizer directly without accessing Trusted Types", async () => {
    expect(typeof window).toBe("undefined")
    await expect(sanitizeNewsHtml("<p>safe</p>")).resolves.toBe("[server]<p>safe</p>")
  })
})
