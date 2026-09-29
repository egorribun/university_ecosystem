import { afterEach, describe, expect, it, vi } from "vitest"

import { toMediaQueryList } from "@/hooks/useMediaQuery"

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("useMediaQuery media-query resolver", () => {
  it("fails closed to null when no browser window is available", () => {
    vi.stubGlobal("window", undefined)

    expect(toMediaQueryList("(prefers-reduced-motion: reduce)")).toBeNull()
  })

  it("fails closed to null when matchMedia is not supported", () => {
    vi.stubGlobal("window", { matchMedia: undefined })

    expect(toMediaQueryList("(prefers-reduced-motion: reduce)")).toBeNull()
  })

  it("returns the browser media-query list for supported matchMedia", () => {
    const mediaQueryList = {
      matches: true,
      media: "(prefers-reduced-motion: reduce)",
    } as MediaQueryList
    const matchMedia = vi.fn(() => mediaQueryList)
    vi.stubGlobal("window", { matchMedia })

    expect(toMediaQueryList(mediaQueryList.media)).toBe(mediaQueryList)
    expect(matchMedia).toHaveBeenCalledWith(mediaQueryList.media)
  })
})
