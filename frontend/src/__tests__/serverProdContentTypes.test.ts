/**
 * @vitest-environment node
 *
 * Wave 175 SW8 — regression tests for W173 SW1 Fix B
 * (server-prod.mjs `.wasm: application/wasm` invariant).
 *
 * Tests live in `__tests__/` (next to ssrCookie.test.ts which also uses
 * @vitest-environment node directive — see setupTests.ts guards added
 * in W133 SW1 for SSR test compatibility).
 *
 * The CONTENT_TYPES map was extracted from server-prod.mjs into
 * `scripts/contentTypes.mjs` so this test can import without launching
 * the actual HTTP server (top-level `createServer` + `listen` side
 * effects). server-prod.mjs imports the same map; the test verifies
 * runtime behavior matches the spec.
 *
 * W173 SW1 dormancy context: W131 SW7 added the CONTENT_TYPES map
 * without `.wasm` entry → fallthrough to `application/octet-stream` →
 * `WebAssembly.instantiateStreaming` refused compilation with
 * "Incorrect response MIME type" → uni_wasm_crypto + wasm_sanitizer
 * fell back to regex implementations (per RZ-24-04). This regression
 * lay dormant ≥17 waves between W131 SW7 (introduction) and W173 SW1
 * (discovery via real user testing) because /messenger (the only
 * feature exercising the crypto.worker) was Phase 5 explicitly
 * punted per W134 §Honesty #10 + W161 SW2.
 */
import { describe, expect, it } from "vitest"

import { CONTENT_TYPES, getContentType } from "../../scripts/contentTypes.mjs"

describe("W173 SW1 — CONTENT_TYPES.wasm regression guard", () => {
  it("resolves .wasm to application/wasm (NOT application/octet-stream)", () => {
    expect(CONTENT_TYPES[".wasm"]).toBe("application/wasm")
  })

  it("getContentType('uni_wasm_crypto_bg-DxJygs7L.wasm') returns application/wasm", () => {
    // Matches the real Vite-hashed WASM filename pattern observed in
    // dist/client/assets/. Critical path for crypto.worker bootstrap.
    expect(getContentType("uni_wasm_crypto_bg-DxJygs7L.wasm")).toBe("application/wasm")
  })

  it("does NOT fall through to application/octet-stream for .wasm", () => {
    // The pre-W173 SW1 fallthrough was the root-cause bug. Explicit
    // negative assertion catches any future regression where someone
    // removes the .wasm entry.
    expect(getContentType("anything.wasm")).not.toBe("application/octet-stream")
  })
})

describe("W175 SW8 — CONTENT_TYPES core extensions", () => {
  it.each([
    [".js", "application/javascript; charset=utf-8"],
    [".mjs", "application/javascript; charset=utf-8"],
    [".css", "text/css; charset=utf-8"],
    [".html", "text/html; charset=utf-8"],
    [".json", "application/json; charset=utf-8"],
    [".webmanifest", "application/manifest+json; charset=utf-8"],
    [".svg", "image/svg+xml"],
    [".png", "image/png"],
    [".jpg", "image/jpeg"],
    [".jpeg", "image/jpeg"],
    [".webp", "image/webp"],
    [".ico", "image/x-icon"],
    [".woff2", "font/woff2"],
    [".woff", "font/woff"],
    [".ttf", "font/ttf"],
  ])("CONTENT_TYPES[%s] === %s", (ext, expected) => {
    expect(CONTENT_TYPES[ext]).toBe(expected)
  })

  it("text content types include UTF-8 charset suffix", () => {
    for (const textExt of [".js", ".mjs", ".css", ".html", ".json", ".webmanifest", ".txt"]) {
      expect(CONTENT_TYPES[textExt]).toMatch(/charset=utf-8/i)
    }
  })

  it("binary content types do NOT include charset suffix", () => {
    for (const binExt of [".png", ".woff2", ".wasm", ".ico", ".jpg"]) {
      expect(CONTENT_TYPES[binExt]).not.toMatch(/charset=/i)
    }
  })
})

describe("W175 SW8 — getContentType fallback behavior", () => {
  it("returns application/octet-stream for unknown extension", () => {
    expect(getContentType("mysterious.xyz")).toBe("application/octet-stream")
  })

  it("returns application/octet-stream for path with no extension", () => {
    expect(getContentType("Makefile")).toBe("application/octet-stream")
    expect(getContentType("/etc/passwd")).toBe("application/octet-stream")
  })

  it("is case-insensitive on extension (.PNG === .png)", () => {
    expect(getContentType("photo.PNG")).toBe("image/png")
    expect(getContentType("photo.JPG")).toBe("image/jpeg")
    expect(getContentType("font.WOFF2")).toBe("font/woff2")
  })

  it("resolves multi-dot filenames by trailing extension only", () => {
    expect(getContentType("index-DqqHVXgy.js")).toBe("application/javascript; charset=utf-8")
    expect(getContentType("vendor.min.js")).toBe("application/javascript; charset=utf-8")
    expect(getContentType("manifest.en.webmanifest")).toBe(
      "application/manifest+json; charset=utf-8"
    )
  })
})

describe("W175 SW8 — CONTENT_TYPES map immutability", () => {
  it("is frozen via Object.freeze (prevents accidental mutation)", () => {
    expect(Object.isFrozen(CONTENT_TYPES)).toBe(true)
  })

  it("attempts to add new extension are silently ignored", () => {
    // In strict mode this would throw; in non-strict it silently
    // no-ops. Either way, the map stays unchanged.
    try {
      ;(CONTENT_TYPES as any)[".xyz"] = "test/test"
    } catch {
      // strict mode TypeError — expected, also fine
    }
    expect(CONTENT_TYPES[".xyz"]).toBeUndefined()
  })
})
