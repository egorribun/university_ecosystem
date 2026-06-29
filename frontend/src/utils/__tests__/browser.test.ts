import { describe, expect, it, vi, afterEach } from "vitest"
import { isIOS, isSafari, isSafariIOS } from "@/utils/browser"

const mockNavigator = (overrides: Partial<Navigator> = {}) => {
  const base: Partial<Navigator> = {
    platform: "",
    userAgent: "",
    vendor: "",
    maxTouchPoints: 0,
    ...overrides,
  }
  vi.stubGlobal("navigator", base)
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("browser utilities", () => {
  describe("isIOS", () => {
    it("returns false when navigator is undefined", () => {
      vi.stubGlobal("navigator", undefined)
      expect(isIOS()).toBe(false)
    })

    it("returns true for iPhone platform", () => {
      mockNavigator({ platform: "iPhone" })
      expect(isIOS()).toBe(true)
    })

    it("returns true for iPad platform", () => {
      mockNavigator({ platform: "iPad" })
      expect(isIOS()).toBe(true)
    })

    it("returns true for iPod platform", () => {
      mockNavigator({ platform: "iPod" })
      expect(isIOS()).toBe(true)
    })

    it("returns true for iPadOS 13+ (MacIntel with touch)", () => {
      mockNavigator({ platform: "MacIntel", maxTouchPoints: 5 })
      expect(isIOS()).toBe(true)
    })

    it("returns false for MacIntel without touch (real Mac)", () => {
      mockNavigator({ platform: "MacIntel", maxTouchPoints: 0 })
      expect(isIOS()).toBe(false)
    })

    it("returns false for MacIntel with single touch point", () => {
      mockNavigator({ platform: "MacIntel", maxTouchPoints: 1 })
      expect(isIOS()).toBe(false)
    })

    it("returns true for iOS userAgent fallback", () => {
      mockNavigator({
        platform: "Linux",
        userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
      })
      expect(isIOS()).toBe(true)
    })

    it("returns false for Android", () => {
      mockNavigator({
        platform: "Linux",
        userAgent: "Mozilla/5.0 (Linux; Android 13)",
      })
      expect(isIOS()).toBe(false)
    })

    it("returns false for Windows", () => {
      mockNavigator({
        platform: "Win32",
        userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
      })
      expect(isIOS()).toBe(false)
    })
  })

  describe("isSafari", () => {
    it("returns false when navigator is undefined", () => {
      vi.stubGlobal("navigator", undefined)
      expect(isSafari()).toBe(false)
    })

    it("returns true for genuine Safari", () => {
      mockNavigator({
        userAgent:
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        vendor: "Apple Computer, Inc.",
      })
      expect(isSafari()).toBe(true)
    })

    it("returns false for Chrome (contains Chrome in UA)", () => {
      mockNavigator({
        userAgent:
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        vendor: "Google Inc.",
      })
      expect(isSafari()).toBe(false)
    })

    it("returns false for Firefox on iOS (FxiOS)", () => {
      mockNavigator({
        userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) FxiOS/120.0 Safari/605.1.15",
        vendor: "Apple Computer, Inc.",
      })
      expect(isSafari()).toBe(false)
    })

    it("returns false for Chrome on iOS (CriOS)", () => {
      mockNavigator({
        userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) CriOS/120.0 Safari/605.1.15",
        vendor: "Apple Computer, Inc.",
      })
      expect(isSafari()).toBe(false)
    })

    it("returns false for Edge (Edg in UA)", () => {
      mockNavigator({
        userAgent:
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/537.36 Edg/120.0",
        vendor: "Apple Computer, Inc.",
      })
      expect(isSafari()).toBe(false)
    })

    it("returns false for Opera (OPR in UA)", () => {
      mockNavigator({
        userAgent:
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/537.36 OPR/100.0",
        vendor: "Apple Computer, Inc.",
      })
      expect(isSafari()).toBe(false)
    })

    it("returns false when vendor is not Apple", () => {
      mockNavigator({
        userAgent: "Mozilla/5.0 Safari/537.36",
        vendor: "Google Inc.",
      })
      expect(isSafari()).toBe(false)
    })
  })

  describe("isSafariIOS", () => {
    it("returns true for Safari on iOS", () => {
      mockNavigator({
        platform: "iPhone",
        userAgent:
          "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        vendor: "Apple Computer, Inc.",
      })
      expect(isSafariIOS()).toBe(true)
    })

    it("returns false for Safari on macOS", () => {
      mockNavigator({
        platform: "MacIntel",
        maxTouchPoints: 0,
        userAgent:
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        vendor: "Apple Computer, Inc.",
      })
      expect(isSafariIOS()).toBe(false)
    })

    it("returns false for Chrome on iOS", () => {
      mockNavigator({
        platform: "iPhone",
        userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0) CriOS/120.0 Safari/605.1.15",
        vendor: "Apple Computer, Inc.",
      })
      expect(isSafariIOS()).toBe(false)
    })
  })
})
