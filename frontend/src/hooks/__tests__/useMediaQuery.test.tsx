import { act, renderHook } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import useMediaQuery from "../useMediaQuery"

describe("useMediaQuery", () => {
  const listeners = new Map<string, (event: MediaQueryListEvent) => void>()

  const createMediaQueryList = (query: string, initial = false): MediaQueryList => {
    const matches = initial
    return {
      media: query,
      matches,
      onchange: null,
      addEventListener: vi.fn((_, cb) => {
        listeners.set(query, cb as (event: MediaQueryListEvent) => void)
      }),
      removeEventListener: vi.fn((_, cb) => {
        const stored = listeners.get(query)
        if (stored === cb) listeners.delete(query)
      }),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    } as unknown as MediaQueryList
  }

  beforeEach(() => {
    listeners.clear()
    vi.spyOn(window, "matchMedia").mockImplementation((query: string) =>
      createMediaQueryList(query, query.includes("max-width"))
    )
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("returns the current match result", () => {
    const { result } = renderHook(() => useMediaQuery("(max-width: 1350px)"))
    expect(result.current).toBe(true)
  })

  it("uses defaultValue during SSR when window is unavailable", () => {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, "window")
    Reflect.deleteProperty(globalThis, "window")

    try {
      const Probe = () => <span>{String(useMediaQuery("(ssr)", { defaultValue: true }))}</span>
      expect(renderToString(<Probe />)).toContain(">true<")
    } finally {
      if (descriptor) Object.defineProperty(globalThis, "window", descriptor)
    }
  })

  it("updates when the media query changes", () => {
    const { result } = renderHook(() => useMediaQuery("(prefers-reduced-motion: reduce)"))
    expect(result.current).toBe(false)

    const listener = listeners.get("(prefers-reduced-motion: reduce)")
    expect(listener).toBeDefined()

    act(() => {
      listener?.({ matches: true } as MediaQueryListEvent)
    })

    expect(result.current).toBe(true)
  })

  it("uses defaultValue when matchMedia is unavailable or throws", () => {
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: undefined,
    })
    const unavailable = renderHook(() =>
      useMediaQuery("(forced-unavailable)", { defaultValue: true })
    )
    expect(unavailable.result.current).toBe(true)
    unavailable.unmount()

    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn(() => {
        throw new Error("matchMedia unavailable")
      }),
    })
    const throwing = renderHook(() => useMediaQuery("(forced-throw)", { defaultValue: true }))
    expect(throwing.result.current).toBe(true)
  })

  it("supports legacy addListener/removeListener media-query APIs", () => {
    let listener: ((event: MediaQueryListEvent) => void) | undefined
    const addListener = vi.fn((cb: (event: MediaQueryListEvent) => void) => {
      listener = cb
    })
    const removeListener = vi.fn()
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn(
        () =>
          ({
            matches: false,
            media: "(legacy)",
            addEventListener: undefined,
            removeEventListener: undefined,
            addListener,
            removeListener,
          }) as unknown as MediaQueryList
      ),
    })

    const { result, unmount } = renderHook(() => useMediaQuery("(legacy)"))
    expect(result.current).toBe(false)
    act(() => listener?.({ matches: true } as MediaQueryListEvent))
    expect(result.current).toBe(true)
    unmount()
    expect(addListener).toHaveBeenCalledOnce()
    expect(removeListener).toHaveBeenCalledOnce()
  })

  it("tolerates media-query lists without either listener API", () => {
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn(
        () =>
          ({
            matches: true,
            media: "(static)",
            addEventListener: undefined,
            removeEventListener: undefined,
            addListener: undefined,
            removeListener: undefined,
          }) as unknown as MediaQueryList
      ),
    })

    const { result, unmount } = renderHook(() => useMediaQuery("(static)"))
    expect(result.current).toBe(true)
    expect(() => unmount()).not.toThrow()
  })
})
