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
        constructor(nextCallback: IntersectionObserverCallback, nextOptions?: IntersectionObserverInit) {
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
})
