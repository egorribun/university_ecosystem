import { act, render, screen } from "@testing-library/react"
import { useLayoutEffect, useRef } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useCountUp } from "../useCountUp"

let intersectionCallback: IntersectionObserverCallback | undefined
const observe = vi.fn()
const disconnect = vi.fn()

function Probe({ target, disabled = false }: { target: number; disabled?: boolean }) {
  const elementRef = useRef<HTMLDivElement>(null)
  const { ref, value } = useCountUp(target, { disabled })

  useLayoutEffect(() => {
    if (elementRef.current) ref(elementRef.current)
  }, [ref])

  return (
    <div ref={elementRef}>
      <output data-testid="count-value">{value}</output>
    </div>
  )
}

beforeEach(() => {
  intersectionCallback = undefined
  observe.mockReset()
  disconnect.mockReset()
  class TestIntersectionObserver {
    constructor(callback: IntersectionObserverCallback) {
      intersectionCallback = callback
    }

    observe(target: Element) {
      observe(target)
    }

    disconnect() {
      disconnect()
    }
  }
  window.IntersectionObserver = TestIntersectionObserver as unknown as typeof IntersectionObserver
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("useCountUp closure", () => {
  it("observes visibility, ignores non-intersecting entries, animates, and cleans up", () => {
    const frames: FrameRequestCallback[] = []
    const requestAnimationFrame = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((callback) => {
        frames.push(callback)
        return frames.length
      })
    const cancelAnimationFrame = vi.spyOn(window, "cancelAnimationFrame")

    const { unmount } = render(<Probe target={100} />)

    expect(observe).toHaveBeenCalledOnce()
    expect(intersectionCallback).toBeDefined()

    act(() => {
      intersectionCallback?.(
        [{ isIntersecting: false } as IntersectionObserverEntry],
        {} as IntersectionObserver
      )
    })
    expect(requestAnimationFrame).not.toHaveBeenCalled()

    act(() => {
      intersectionCallback?.(
        [{ isIntersecting: true } as IntersectionObserverEntry],
        {} as IntersectionObserver
      )
    })
    expect(disconnect).toHaveBeenCalled()
    expect(requestAnimationFrame).toHaveBeenCalledOnce()

    act(() => {
      frames.shift()?.(1)
    })
    expect(requestAnimationFrame).toHaveBeenCalledTimes(2)
    act(() => {
      frames.shift()?.(1401)
    })
    expect(screen.getByTestId("count-value")).toHaveTextContent("100")

    unmount()
    expect(cancelAnimationFrame).toHaveBeenCalled()
  })

  it("keeps the optional entry guard safe for an empty observer notification", () => {
    render(<Probe target={10} />)

    act(() => {
      intersectionCallback?.([], {} as IntersectionObserver)
    })

    expect(screen.getByTestId("count-value")).toHaveTextContent("0")
  })
})
