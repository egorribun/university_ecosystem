import { act, render, screen } from "@testing-library/react"
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

type MediaQueryHarness = Omit<MediaQueryList, "matches"> & {
  matches: boolean
  emitChange: () => void
}

let PageFadeIn: typeof import("@/components/motion/PageFadeIn").default

function createMediaQuery(matches: boolean, mode: "event" | "legacy" | "none"): MediaQueryHarness {
  let changeListener: (() => void) | undefined
  let legacyListener: (() => void) | undefined

  const query = {
    matches,
    media: "(prefers-reduced-motion: reduce)",
    onchange: null,
    addEventListener:
      mode === "event"
        ? vi.fn((_type: string, listener: EventListener) => {
            changeListener = listener as unknown as () => void
          })
        : undefined,
    removeEventListener:
      mode === "event"
        ? vi.fn(() => {
            changeListener = undefined
          })
        : undefined,
    addListener:
      mode === "legacy"
        ? vi.fn((listener: () => void) => {
            legacyListener = listener
          })
        : undefined,
    removeListener:
      mode === "legacy"
        ? vi.fn(() => {
            legacyListener = undefined
          })
        : undefined,
    dispatchEvent: vi.fn(() => true),
    emitChange: () => {
      if (mode === "event") changeListener?.()
      if (mode === "legacy") legacyListener?.()
    },
  }

  return query as unknown as MediaQueryHarness
}

beforeAll(async () => {
  vi.stubEnv("MODE", "production")
  vi.resetModules()
  ;({ default: PageFadeIn } = await import("@/components/motion/PageFadeIn"))
})

beforeEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

afterAll(() => {
  vi.unstubAllEnvs()
})

describe("PageFadeIn — production scheduling and media-query fallbacks", () => {
  it("waits for RAF and responds to modern media-query change events", () => {
    let frameCallback: FrameRequestCallback | undefined
    const requestAnimationFrame = vi.fn((callback: FrameRequestCallback) => {
      frameCallback = callback
      return 17
    })
    const cancelAnimationFrame = vi.fn()
    vi.stubGlobal("requestAnimationFrame", requestAnimationFrame)
    vi.stubGlobal("cancelAnimationFrame", cancelAnimationFrame)

    const query = createMediaQuery(false, "event")
    vi.spyOn(window, "matchMedia").mockReturnValue(query)

    const { rerender, unmount } = render(<PageFadeIn effect="soft-blur">content</PageFadeIn>)
    const root = screen.getByText("content").closest("[data-page-fade]")!

    expect(root).toHaveAttribute("data-ready", "false")
    expect(root).toHaveAttribute("data-effect", "soft-blur")
    expect(requestAnimationFrame).toHaveBeenCalledOnce()

    act(() => frameCallback?.(0))
    expect(root).toHaveAttribute("data-ready", "true")

    query.matches = true
    act(() => query.emitChange())
    expect(root).not.toHaveAttribute("data-effect")

    query.matches = false
    act(() => query.emitChange())
    rerender(<PageFadeIn effect="soft-blur">content</PageFadeIn>)
    expect(root).toHaveAttribute("data-effect", "soft-blur")

    unmount()
    expect(cancelAnimationFrame).toHaveBeenCalledWith(17)
    expect(query.removeEventListener).toHaveBeenCalledOnce()
  })

  it("falls back to a timeout and the legacy media-query listener", () => {
    let timeoutCallback: (() => void) | undefined
    const setTimeout = vi.spyOn(window, "setTimeout").mockImplementation((handler) => {
      timeoutCallback = handler as unknown as () => void
      return 23 as unknown as ReturnType<typeof globalThis.setTimeout>
    })
    const clearTimeout = vi.spyOn(window, "clearTimeout")
    const query = createMediaQuery(false, "legacy")
    vi.spyOn(window, "matchMedia").mockReturnValue(query)
    vi.stubGlobal("requestAnimationFrame", undefined)

    const { unmount } = render(<PageFadeIn effect="soft-blur">legacy</PageFadeIn>)
    const root = screen.getByText("legacy").closest("[data-page-fade]")!
    expect(root).toHaveAttribute("data-ready", "false")
    expect(setTimeout).toHaveBeenCalledWith(expect.any(Function), 16)

    act(() => timeoutCallback?.())
    expect(root).toHaveAttribute("data-ready", "true")

    query.matches = true
    act(() => query.emitChange())
    expect(root).not.toHaveAttribute("data-effect")

    unmount()
    expect(clearTimeout).toHaveBeenCalledWith(23)
    expect(query.removeListener).toHaveBeenCalledOnce()
  })

  it("does not install a media listener when neither API exists", () => {
    const query = createMediaQuery(false, "none")
    vi.spyOn(window, "matchMedia").mockReturnValue(query)
    vi.stubGlobal("requestAnimationFrame", undefined)
    vi.spyOn(window, "setTimeout").mockImplementation((handler) => {
      ;(handler as () => void)()
      return 24 as unknown as ReturnType<typeof globalThis.setTimeout>
    })

    render(<PageFadeIn>no listener</PageFadeIn>)
    expect(screen.getByText("no listener").closest("[data-page-fade]")).toHaveAttribute(
      "data-ready",
      "true"
    )
  })

  it("keeps the ready state when matchMedia is unavailable", () => {
    const originalMatchMedia = window.matchMedia
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: undefined,
    })
    vi.stubGlobal("requestAnimationFrame", undefined)
    vi.spyOn(window, "setTimeout").mockImplementation((handler) => {
      ;(handler as () => void)()
      return 25 as unknown as ReturnType<typeof globalThis.setTimeout>
    })

    try {
      render(<PageFadeIn>without media query</PageFadeIn>)
      expect(screen.getByText("without media query").closest("[data-page-fade]")).toHaveAttribute(
        "data-ready",
        "true"
      )
    } finally {
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        value: originalMatchMedia,
      })
    }
  })
})
