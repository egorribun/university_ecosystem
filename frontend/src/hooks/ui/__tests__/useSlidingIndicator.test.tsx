import { act, renderHook } from "@testing-library/react"
import type { RefObject } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useSlidingIndicator } from "@/hooks/ui/useSlidingIndicator"

describe("useSlidingIndicator", () => {
  let resizeCallback: ResizeObserverCallback
  const observe = vi.fn()
  const disconnect = vi.fn()

  beforeEach(() => {
    observe.mockReset()
    disconnect.mockReset()
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(callback: ResizeObserverCallback) {
          resizeCallback = callback
        }
        observe = observe
        disconnect = disconnect
        unobserve = vi.fn()
      }
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it("returns null without a container or active key", () => {
    const emptyRef = { current: null } as RefObject<HTMLElement | null>
    const { result, rerender } = renderHook(
      ({ keyValue }) => useSlidingIndicator(emptyRef, keyValue),
      { initialProps: { keyValue: "first" as string | null } }
    )
    expect(result.current).toBeNull()

    const container = document.createElement("div")
    emptyRef.current = container
    rerender({ keyValue: null })
    expect(result.current).toBeNull()
  })

  it("measures the active item, reacts to resize, and clears a missing target", () => {
    const container = document.createElement("div")
    const first = document.createElement("button")
    first.dataset.tabKey = "first"
    container.appendChild(first)
    container.getBoundingClientRect = () =>
      ({ left: 10, top: 20, width: 300, height: 50 }) as DOMRect
    first.getBoundingClientRect = () => ({ left: 40, top: 25, width: 80, height: 32 }) as DOMRect
    const ref = { current: container } as RefObject<HTMLElement | null>

    const { result, rerender, unmount } = renderHook(
      ({ keyValue }) => useSlidingIndicator(ref, keyValue),
      { initialProps: { keyValue: "first" } }
    )
    expect(result.current).toEqual({ left: 30, top: 5, width: 80, height: 32 })
    expect(observe).toHaveBeenCalledWith(first)
    expect(observe).toHaveBeenCalledWith(container)

    first.getBoundingClientRect = () => ({ left: 55, top: 30, width: 90, height: 36 }) as DOMRect
    act(() => resizeCallback([], {} as ResizeObserver))
    expect(result.current).toEqual({ left: 45, top: 10, width: 90, height: 36 })

    rerender({ keyValue: "missing" })
    expect(result.current).toBeNull()
    unmount()
    expect(disconnect).toHaveBeenCalled()
  })
})
