import { describe, expect, it, vi, beforeEach } from "vitest"
import { mixColorWithWhite, lightenColor } from "@/utils/color"

describe("color utilities", () => {
  describe("mixColorWithWhite", () => {
    beforeEach(() => {
      // Default: CSS.supports unavailable — forces hex fallback path
      vi.stubGlobal("CSS", undefined)
    })

    it("returns original color when coefficient is 0 (hex path)", () => {
      const result = mixColorWithWhite("#ff0000", 0)
      expect(result).toBe("#ff0000")
    })

    it("returns white when coefficient is 1 (hex path)", () => {
      const result = mixColorWithWhite("#000000", 1)
      expect(result).toBe("#ffffff")
    })

    it("mixes black with 50% white → #808080 (hex path)", () => {
      const result = mixColorWithWhite("#000000", 0.5)
      // Each channel: Math.round(0 + (255 - 0) * 0.5) = 128 = 0x80
      expect(result).toBe("#808080")
    })

    it("handles shorthand hex (#f00)", () => {
      const result = mixColorWithWhite("#f00", 0)
      expect(result).toBe("#ff0000")
    })

    it("handles hex without # prefix", () => {
      const result = mixColorWithWhite("ff0000", 0)
      expect(result).toBe("#ff0000")
    })

    it("clamps coefficient below 0 to 0", () => {
      const result = mixColorWithWhite("#ff0000", -0.5)
      expect(result).toBe("#ff0000")
    })

    it("clamps coefficient above 1 to 1", () => {
      const result = mixColorWithWhite("#000000", 1.5)
      expect(result).toBe("#ffffff")
    })

    it("trims whitespace from color input", () => {
      const result = mixColorWithWhite("  #ff0000  ", 0)
      expect(result).toBe("#ff0000")
    })

    it("returns original color for non-hex CSS color when CSS.supports unavailable", () => {
      // rgb(), hsl(), named colors can't be parsed as hex → fallback to trimmed input
      const result = mixColorWithWhite("rgb(255, 0, 0)", 0.5)
      expect(result).toBe("rgb(255, 0, 0)")
    })

    it("uses color-mix expression when CSS.supports is available and supports it", () => {
      vi.stubGlobal("CSS", {
        supports: vi.fn().mockReturnValue(true),
      })

      const result = mixColorWithWhite("#ff0000", 0.3)
      expect(result).toContain("color-mix")
      expect(result).toContain("srgb")
    })

    it("falls back to hex when CSS.supports returns false", () => {
      vi.stubGlobal("CSS", {
        supports: vi.fn().mockReturnValue(false),
      })

      const result = mixColorWithWhite("#ff0000", 0.5)
      expect(result).toMatch(/^#[0-9a-f]{6}$/)
    })

    it("handles case-insensitive hex", () => {
      const result = mixColorWithWhite("#FF0000", 0)
      expect(result).toBe("#ff0000")
    })

    it("returns empty string color as-is for invalid input", () => {
      const result = mixColorWithWhite("", 0.5)
      expect(result).toBe("")
    })
  })

  describe("lightenColor", () => {
    it("is an alias for mixColorWithWhite", () => {
      expect(lightenColor).toBe(mixColorWithWhite)
    })
  })
})
