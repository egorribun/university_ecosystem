import { act, renderHook } from "@testing-library/react"
import type { RefObject } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useStableListHeight } from "@/hooks/ui/useStableListHeight"

type Props = { resetKey: string; settling: boolean }

describe("useStableListHeight", () => {
  let resizeCallback: ResizeObserverCallback | undefined
  const observe = vi.fn()
  const disconnect = vi.fn()
  let height = 0

  const container = document.createElement("div")
  vi.spyOn(container, "getBoundingClientRect").mockImplementation(() => ({ height }) as DOMRect)

  const resize = (next: number) => {
    height = next
    act(() => resizeCallback?.([], {} as ResizeObserver))
  }

  const renderStableHeight = (
    ref: RefObject<HTMLElement | null> = { current: container },
    initialProps: Props = { resetKey: "all", settling: false }
  ) =>
    renderHook(({ resetKey, settling }: Props) => useStableListHeight(ref, resetKey, settling), {
      initialProps,
    })

  beforeEach(() => {
    resizeCallback = undefined
    height = 0
    observe.mockReset()
    // A disconnected observer never reports again.
    disconnect.mockReset().mockImplementation(() => {
      resizeCallback = undefined
    })
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
  })

  it("holds the last settled height while a new filter settles", () => {
    const { result, rerender } = renderStableHeight()
    expect(observe).toHaveBeenCalledExactlyOnceWith(container)
    resize(2169.6)
    expect(result.current).toBeUndefined()

    rerender({ resetKey: "lecture", settling: true })
    expect(result.current).toBe(2170)
    expect(disconnect).toHaveBeenCalledOnce()

    rerender({ resetKey: "lecture", settling: false })
    expect(result.current).toBeUndefined()
    expect(observe).toHaveBeenCalledTimes(2)
  })

  it("never holds a floor when the new list is already complete", () => {
    const { result, rerender } = renderStableHeight()
    resize(900)

    rerender({ resetKey: "lecture", settling: false })
    expect(result.current).toBeUndefined()
  })

  it("keeps the settled height, not the held floor, across quick switches", () => {
    const { result, rerender } = renderStableHeight()
    resize(1200)
    rerender({ resetKey: "lecture", settling: true })
    // A held list never reports its floor as the next settled height.
    resize(400)
    rerender({ resetKey: "seminar", settling: true })
    expect(result.current).toBe(1200)
  })

  it("does not start holding when a refetch begins without a filter change", () => {
    const { result, rerender } = renderStableHeight()
    resize(1200)

    rerender({ resetKey: "all", settling: true })
    expect(result.current).toBeUndefined()
  })

  it("stops observing on unmount and skips a missing container", () => {
    const { unmount } = renderStableHeight()
    unmount()
    expect(disconnect).toHaveBeenCalledOnce()

    const { result } = renderStableHeight({ current: null })
    expect(observe).toHaveBeenCalledOnce()
    expect(result.current).toBeUndefined()
  })
})
