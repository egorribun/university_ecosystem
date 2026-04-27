import { describe, expect, it } from "vitest"
import { mixColorWithWhite, lightenColor } from "../color"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Helper to check if the returned value is a color-mix CSS expression.
 * In jsdom, CSS.supports is available but may not support color-mix(),
 * so we handle both the hex-fallback and the CSS function path.
 */
const isCssMix = (value: string) => value.startsWith("color-mix(")
const isHex = (value: string) => /^#[0-9a-f]{6}$/i.test(value)

describe("mixColorWithWhite", () => {
  // ---------------------------------------------------------------------------
  // Coefficient clamping
  // ---------------------------------------------------------------------------
  it("clamps coefficient below 0 to 0 (no mixing)", () => {
    const result = mixColorWithWhite("#ff0000", -0.5)
    // coefficient 0 → 0% white mixed in → original color unchanged or base expression
    if (isCssMix(result)) {
      expect(result).toContain("0%") // 0% white
    } else {
      // hex path: 0% white → channel + 0 = original
      expect(result).toBe("#ff0000")
    }
  })

  it("clamps coefficient above 1 to 1 (pure white)", () => {
    const result = mixColorWithWhite("#000000", 2)
    if (isCssMix(result)) {
      expect(result).toContain("100%")
    } else {
      expect(result).toBe("#ffffff")
    }
  })

  // ---------------------------------------------------------------------------
  // Hex fallback path (when CSS.supports is unavailable or returns false)
  // ---------------------------------------------------------------------------
  describe("hex fallback (CSS.supports mocked away)", () => {
    it("mixes black with white at 0.5 → mid-grey #7f7f7f or #808080", () => {
      // Temporarily disable CSS.supports so hex path is forced
      const originalCSS = globalThis.CSS
      Object.defineProperty(globalThis, "CSS", { value: undefined, writable: true })

      const result = mixColorWithWhite("#000000", 0.5)

      Object.defineProperty(globalThis, "CSS", { value: originalCSS, writable: true })

      // Mid-grey: channel = 0 + (255 - 0) * 0.5 = 127 or 128 due to rounding
      expect(isHex(result)).toBe(true)
      expect(result).toMatch(/^#[78][0-9a-f]{5}$/)
    })

    it("mixes pure red (#ff0000) with white at 0.5", () => {
      const originalCSS = globalThis.CSS
      Object.defineProperty(globalThis, "CSS", { value: undefined, writable: true })

      const result = mixColorWithWhite("#ff0000", 0.5)

      Object.defineProperty(globalThis, "CSS", { value: originalCSS, writable: true })

      expect(isHex(result)).toBe(true)
      // red channel stays 255, g and b channels become ~128
      expect(result.toUpperCase()).toMatch(/^#FF/)
    })

    it("expands 3-char hex shorthand (#f00 → #ff0000)", () => {
      const originalCSS = globalThis.CSS
      Object.defineProperty(globalThis, "CSS", { value: undefined, writable: true })

      const result = mixColorWithWhite("#f00", 0)

      Object.defineProperty(globalThis, "CSS", { value: originalCSS, writable: true })

      // With coefficient 0, no white mixed in → pure red
      expect(result.toUpperCase()).toBe("#FF0000")
    })

    it("returns original color unchanged for unrecognised format", () => {
      const originalCSS = globalThis.CSS
      Object.defineProperty(globalThis, "CSS", { value: undefined, writable: true })

      const result = mixColorWithWhite("var(--primary)", 0.3)

      Object.defineProperty(globalThis, "CSS", { value: originalCSS, writable: true })

      // Not a hex → tryMixHexWithWhite returns null → fallback to original
      expect(result).toBe("var(--primary)")
    })

    it("trims whitespace from color input", () => {
      const originalCSS = globalThis.CSS
      Object.defineProperty(globalThis, "CSS", { value: undefined, writable: true })

      const result = mixColorWithWhite("  #000000  ", 1)

      Object.defineProperty(globalThis, "CSS", { value: originalCSS, writable: true })

      expect(isHex(result)).toBe(true)
      expect(result).toBe("#ffffff")
    })
  })
})

// ---------------------------------------------------------------------------
// lightenColor — alias for mixColorWithWhite
// ---------------------------------------------------------------------------
describe("lightenColor", () => {
  it("is the same reference as mixColorWithWhite", () => {
    expect(lightenColor).toBe(mixColorWithWhite)
  })
})
