import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"

import { StaggerChildren } from "@/components/ui/motion/StaggerChildren"

// matchMedia + IntersectionObserver are polyfilled in setupTests.ts.

describe("StaggerChildren", () => {
  let callback: IntersectionObserverCallback
  const observe = vi.fn()
  const disconnect = vi.fn()
  const observer = { observe, disconnect } as unknown as IntersectionObserver
  let options: IntersectionObserverInit | undefined

  beforeEach(() => {
    observe.mockReset()
    disconnect.mockReset()
    options = undefined
    vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: false,
      media: "(prefers-reduced-motion: reduce)",
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    } as unknown as MediaQueryList)
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        constructor(
          nextCallback: IntersectionObserverCallback,
          nextOptions?: IntersectionObserverInit
        ) {
          callback = nextCallback
          options = nextOptions
          return observer
        }
      }
    )
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it("renders children + attaches an IntersectionObserver (motion enabled)", () => {
    const { container } = render(
      <StaggerChildren className="grid" rootMargin="10px" once>
        <div className="stagger-item">A</div>
      </StaggerChildren>
    )
    expect(screen.getByText("A")).toBeInTheDocument()
    expect(options).toEqual({ rootMargin: "10px" })
    expect(observe).toHaveBeenCalledWith(container.firstElementChild)

    callback([{ isIntersecting: true } as IntersectionObserverEntry], observer)
    expect(container.querySelector<HTMLElement>(".stagger-item")?.dataset.visible).toBe("true")
    expect(disconnect).toHaveBeenCalledOnce()
  })

  it("uses the documented defaults for root margin and one-shot visibility", () => {
    const { container } = render(
      <StaggerChildren>
        <div className="stagger-item">Default</div>
      </StaggerChildren>
    )

    expect(options).toEqual({ rootMargin: "0px 0px -80px 0px" })
    expect(window.matchMedia).toHaveBeenCalledWith("(prefers-reduced-motion: reduce)")
    callback([{ isIntersecting: true } as IntersectionObserverEntry], observer)
    expect(container.querySelector<HTMLElement>(".stagger-item")?.dataset.visible).toBe("true")
    expect(disconnect).toHaveBeenCalledOnce()
  })

  it("keeps observing non-intersecting entries when once is disabled", () => {
    const { container, unmount } = render(
      <StaggerChildren once={false}>
        <div className="stagger-item">C</div>
      </StaggerChildren>
    )

    callback([], observer)
    callback([{ isIntersecting: false } as IntersectionObserverEntry], observer)
    expect(container.querySelector<HTMLElement>(".stagger-item")?.dataset.visible).toBeUndefined()
    expect(disconnect).not.toHaveBeenCalled()

    callback([{ isIntersecting: true } as IntersectionObserverEntry], observer)
    expect(container.querySelector<HTMLElement>(".stagger-item")?.dataset.visible).toBe("true")
    expect(disconnect).not.toHaveBeenCalled()

    unmount()
    expect(disconnect).toHaveBeenCalledOnce()
  })

  it("marks stagger items visible immediately under reduced motion", () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: true,
      media: "(prefers-reduced-motion: reduce)",
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    } as unknown as MediaQueryList)

    const { container } = render(
      <StaggerChildren>
        <div className="stagger-item">B</div>
      </StaggerChildren>
    )
    const item = container.querySelector<HTMLElement>(".stagger-item")
    expect(item?.dataset.visible).toBe("true")
  })

  it("rebuilds the observer when its runtime options change", () => {
    const { container, rerender } = render(
      <StaggerChildren rootMargin="0px">
        <div className="stagger-item">Options</div>
      </StaggerChildren>
    )
    const firstCallback = callback
    expect(options).toEqual({ rootMargin: "0px" })

    rerender(
      <StaggerChildren rootMargin="20px" once={false}>
        <div className="stagger-item">Options</div>
      </StaggerChildren>
    )

    expect(disconnect).toHaveBeenCalledOnce()
    expect(options).toEqual({ rootMargin: "20px" })
    expect(observe).toHaveBeenCalledTimes(2)
    firstCallback([{ isIntersecting: true } as IntersectionObserverEntry], observer)
    expect(container.querySelector<HTMLElement>(".stagger-item")?.dataset.visible).toBe("true")
  })
})
