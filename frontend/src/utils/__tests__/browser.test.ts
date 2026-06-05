import { describe, it, expect, afterEach } from "vitest"

import { isIOS, isSafari, isSafariIOS } from "../browser"

const overridden = new Set<string>()

function setNavigator(props: Record<string, unknown>): void {
  for (const [key, value] of Object.entries(props)) {
    Object.defineProperty(window.navigator, key, {
      value,
      configurable: true,
      writable: true,
    })
    overridden.add(key)
  }
}

afterEach(() => {
  for (const key of overridden) {
    delete (window.navigator as unknown as Record<string, unknown>)[key]
  }
  overridden.clear()
})

describe("isIOS", () => {
  it("detects iPhone/iPad/iPod platforms", () => {
    setNavigator({ platform: "iPhone", userAgent: "", maxTouchPoints: 0 })
    expect(isIOS()).toBe(true)
  })

  it("detects iPadOS reporting MacIntel with multi-touch support", () => {
    setNavigator({ platform: "MacIntel", userAgent: "", maxTouchPoints: 5 })
    expect(isIOS()).toBe(true)
  })

  it("detects iOS via the user-agent when the platform is generic", () => {
    setNavigator({
      platform: "",
      userAgent: "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)",
      maxTouchPoints: 5,
    })
    expect(isIOS()).toBe(true)
  })

  it("returns false on a desktop platform", () => {
    setNavigator({
      platform: "Win32",
      userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
      maxTouchPoints: 0,
    })
    expect(isIOS()).toBe(false)
  })
})

describe("isSafari", () => {
  it("returns true for genuine desktop Safari", () => {
    setNavigator({
      userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/605.1 Safari/605.1",
      vendor: "Apple Computer, Inc.",
    })
    expect(isSafari()).toBe(true)
  })

  it("returns false for Chrome on iOS (CriOS)", () => {
    setNavigator({
      userAgent: "Mozilla/5.0 (iPhone) AppleWebKit/605.1 CriOS/120 Safari/605.1",
      vendor: "Apple Computer, Inc.",
    })
    expect(isSafari()).toBe(false)
  })

  it("returns false for desktop Chrome", () => {
    setNavigator({
      userAgent: "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/120 Safari/537.36",
      vendor: "Google Inc.",
    })
    expect(isSafari()).toBe(false)
  })
})

describe("isSafariIOS", () => {
  it("is true only when the browser is both iOS and Safari", () => {
    setNavigator({
      platform: "iPhone",
      userAgent: "Mozilla/5.0 (iPhone) AppleWebKit/605.1 Safari/605.1",
      vendor: "Apple Computer, Inc.",
    })
    expect(isSafariIOS()).toBe(true)
  })
})
