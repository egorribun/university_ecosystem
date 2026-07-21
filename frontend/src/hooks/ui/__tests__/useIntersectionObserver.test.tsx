import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, render, screen } from "@testing-library/react"
import { useIntersectionObserver } from "../useIntersectionObserver"

class TestIntersectionObserver {
  static instances: TestIntersectionObserver[] = []
  readonly observe = vi.fn()
  readonly disconnect = vi.fn()

  constructor(
    private readonly callback: IntersectionObserverCallback,
    readonly options?: IntersectionObserverInit
  ) {
    TestIntersectionObserver.instances.push(this)
  }

  emit(isIntersecting: boolean) {
    this.callback(
      [{ isIntersecting } as IntersectionObserverEntry],
      this as unknown as IntersectionObserver
    )
  }
}

function Probe({ freezeOnceVisible = false }: { freezeOnceVisible?: boolean }) {
  const [ref, isVisible] = useIntersectionObserver({
    threshold: 0.5,
    rootMargin: "12px",
    freezeOnceVisible,
  })
  return <div ref={ref} data-testid="probe" data-visible={String(isVisible)} />
}

describe("useIntersectionObserver", () => {
  const original = window.IntersectionObserver

  beforeEach(() => {
    TestIntersectionObserver.instances = []
    Object.defineProperty(window, "IntersectionObserver", {
      configurable: true,
      value: TestIntersectionObserver,
    })
    Object.defineProperty(globalThis, "IntersectionObserver", {
      configurable: true,
      value: TestIntersectionObserver,
    })
  })

  afterEach(() => {
    Object.defineProperty(window, "IntersectionObserver", {
      configurable: true,
      value: original,
    })
    Object.defineProperty(globalThis, "IntersectionObserver", {
      configurable: true,
      value: original,
    })
  })

  it("observes the node with supplied options and freezes after first visibility", () => {
    render(<Probe freezeOnceVisible />)

    const observer = TestIntersectionObserver.instances[0]
    if (observer === undefined) {
      throw new Error("expected the hook to create an IntersectionObserver")
    }
    expect(observer.observe).toHaveBeenCalledTimes(1)
    expect(observer.options).toEqual({ threshold: 0.5, root: null, rootMargin: "12px" })
    expect(screen.getByTestId("probe")).toHaveAttribute("data-visible", "false")

    act(() => {
      observer.emit(true)
    })

    expect(screen.getByTestId("probe")).toHaveAttribute("data-visible", "true")
    expect(observer.disconnect).toHaveBeenCalledTimes(1)
  })

  it("returns a false visibility state without creating an observer when unsupported", () => {
    Object.defineProperty(window, "IntersectionObserver", { configurable: true, value: undefined })
    Object.defineProperty(globalThis, "IntersectionObserver", {
      configurable: true,
      value: undefined,
    })

    render(<Probe />)

    expect(screen.getByTestId("probe")).toHaveAttribute("data-visible", "false")
    expect(TestIntersectionObserver.instances).toHaveLength(0)
  })
})
