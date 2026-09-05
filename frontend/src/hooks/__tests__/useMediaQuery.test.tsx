import { act, renderHook } from "@testing-library/react"
import { hydrateRoot } from "react-dom/client"
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

  it("uses the server snapshot during hydration before applying the client match", async () => {
    const Probe = () => <span>{String(useMediaQuery("(prefers-reduced-motion: reduce)"))}</span>
    const html = renderToString(<Probe />)
    expect(html).toContain(">false<")

    vi.mocked(window.matchMedia).mockImplementation((query: string) =>
      createMediaQueryList(query, true)
    )
    const container = document.createElement("div")
    container.innerHTML = html
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined)

    let root: ReturnType<typeof hydrateRoot> | undefined
    await act(async () => {
      root = hydrateRoot(container, <Probe />)
    })

    expect(container.textContent).toBe("true")
    expect(
      consoleError.mock.calls.some(([message]) =>
        String(message).toLowerCase().includes("hydration")
      )
    ).toBe(false)

    await act(async () => root?.unmount())
  })

  it("refreshes the external subscription when its fallback store is recreated", () => {
    const mediaQueryList = createMediaQueryList("(fallback-store)", false)
    const addEventListener = vi.spyOn(mediaQueryList, "addEventListener")
    const removeEventListener = vi.spyOn(mediaQueryList, "removeEventListener")
    vi.mocked(window.matchMedia).mockReturnValue(mediaQueryList)

    const { rerender, unmount } = renderHook(
      ({ defaultValue }) => useMediaQuery("(fallback-store)", { defaultValue }),
      { initialProps: { defaultValue: false } }
    )

    rerender({ defaultValue: true })

    // Changing the fallback creates a new store.  React must detach the
    // listener that closes over the old store and attach one for the new one.
    expect(removeEventListener).toHaveBeenCalledTimes(1)
    expect(addEventListener).toHaveBeenCalledTimes(2)
    unmount()
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

  it("rebinds subscriptions when the query changes", () => {
    const { result, rerender, unmount } = renderHook(({ query }) => useMediaQuery(query), {
      initialProps: { query: "(prefers-reduced-motion: reduce)" },
    })
    expect(result.current).toBe(false)
    expect(listeners.has("(prefers-reduced-motion: reduce)")).toBe(true)

    rerender({ query: "(max-width: 600px)" })

    expect(result.current).toBe(true)
    expect(listeners.has("(prefers-reduced-motion: reduce)")).toBe(false)
    expect(listeners.has("(max-width: 600px)")).toBe(true)
    unmount()
    expect(listeners.size).toBe(0)
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

  it("updates the fallback snapshot when defaultValue changes", () => {
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: undefined,
    })

    const { result, rerender } = renderHook(
      ({ defaultValue }) => useMediaQuery("(fallback)", { defaultValue }),
      { initialProps: { defaultValue: false } }
    )
    expect(result.current).toBe(false)

    rerender({ defaultValue: true })

    expect(result.current).toBe(true)
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

  it("uses the standard change event name and removes modern listeners on unmount", () => {
    const addEventListener = vi.fn()
    const removeEventListener = vi.fn()
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn(
        () =>
          ({
            matches: false,
            media: "(modern)",
            addEventListener,
            removeEventListener,
          }) as unknown as MediaQueryList
      ),
    })

    const { unmount } = renderHook(() => useMediaQuery("(modern)"))
    expect(addEventListener).toHaveBeenCalledWith("change", expect.any(Function))
    unmount()
    expect(removeEventListener).toHaveBeenCalledWith("change", expect.any(Function))
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
