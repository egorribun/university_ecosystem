import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { renderToString } from "react-dom/server"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import BackToTop from "@/components/motion/BackToTop"
import i18n from "@/i18n/config"

const getLabel = () => i18n.t("common:buttons.backToTop")

const setScrollY = (value: number) => {
  Object.defineProperty(window, "scrollY", { value, configurable: true })
  Object.defineProperty(window, "pageYOffset", { value, configurable: true })
}

describe("BackToTop", () => {
  beforeEach(() => {
    setScrollY(0)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("does not render button when not scrolled", () => {
    render(<BackToTop />)
    const button = screen.queryByRole("button", { name: getLabel() })
    expect(button).not.toBeInTheDocument()
  })

  it("renders button after scrolling past threshold", async () => {
    render(<BackToTop />)

    setScrollY(500)
    fireEvent.scroll(window)

    await waitFor(() => {
      const button = screen.getByRole("button", { name: getLabel() })
      expect(button).toBeInTheDocument()
    })
  })

  it("hides button when scrolled back to top", async () => {
    render(<BackToTop />)

    setScrollY(500)
    fireEvent.scroll(window)

    await waitFor(() => {
      expect(screen.getByRole("button", { name: getLabel() })).toBeInTheDocument()
    })

    setScrollY(0)
    fireEvent.scroll(window)

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: getLabel() })).not.toBeInTheDocument()
    })
  })

  it("scrolls smoothly to top when clicked", async () => {
    const user = userEvent.setup()
    const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => {})
    render(<BackToTop />)

    setScrollY(500)
    fireEvent.scroll(window)

    await waitFor(() => {
      expect(screen.getByRole("button", { name: getLabel() })).toBeInTheDocument()
    })

    const button = screen.getByRole("button", { name: getLabel() })
    await user.click(button)

    expect(scrollTo).toHaveBeenCalledTimes(1)
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" })
  })

  it("moves above an intersecting footer and disconnects the observer", async () => {
    const observe = vi.fn()
    const disconnect = vi.fn()
    let callback: IntersectionObserverCallback | undefined
    class MockIntersectionObserver {
      constructor(next: IntersectionObserverCallback) {
        callback = next
      }

      observe = observe
      disconnect = disconnect
    }
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver)
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 800 })
    const footer = document.createElement("footer")
    footer.setAttribute("role", "contentinfo")
    document.body.appendChild(footer)

    const { unmount } = render(<BackToTop />)
    expect(observe).toHaveBeenCalledWith(footer)

    setScrollY(500)
    fireEvent.scroll(window)
    await waitFor(() =>
      expect(screen.getByRole("button", { name: getLabel() })).toBeInTheDocument()
    )

    callback?.(
      [{ isIntersecting: true, boundingClientRect: { top: 700 } } as IntersectionObserverEntry],
      {} as IntersectionObserver
    )
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: getLabel() }).parentElement?.parentElement
      ).toHaveStyle("bottom: 140px")
    )

    callback?.([{ isIntersecting: false } as IntersectionObserverEntry], {} as IntersectionObserver)
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: getLabel() }).parentElement?.parentElement
      ).toHaveStyle("bottom: 24px")
    )

    unmount()
    expect(disconnect).toHaveBeenCalledOnce()
    footer.remove()
  })

  it("falls back to the legacy scrollTo signature when smooth scrolling throws", async () => {
    const scrollTo = vi.spyOn(window, "scrollTo").mockImplementationOnce(() => {
      throw new Error("unsupported options")
    })
    render(<BackToTop />)
    setScrollY(500)
    fireEvent.scroll(window)
    await waitFor(() =>
      expect(screen.getByRole("button", { name: getLabel() })).toBeInTheDocument()
    )

    fireEvent.click(screen.getByRole("button", { name: getLabel() }))
    expect(scrollTo).toHaveBeenNthCalledWith(2, 0, 0)
  })

  it("keeps the SSR initial state hidden until the client reads scroll position", () => {
    expect(renderToString(<BackToTop />)).not.toContain(getLabel())
  })

  it("uses a strict scroll threshold and does not show at exactly 420px", async () => {
    render(<BackToTop />)

    setScrollY(420)
    fireEvent.scroll(window)
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: getLabel() })).not.toBeInTheDocument()
    )

    setScrollY(421)
    fireEvent.scroll(window)
    await waitFor(() =>
      expect(screen.getByRole("button", { name: getLabel() })).toBeInTheDocument()
    )
  })

  it("registers and removes a passive scroll listener exactly once", () => {
    const addEventListener = vi.spyOn(window, "addEventListener")
    const removeEventListener = vi.spyOn(window, "removeEventListener")
    const { unmount } = render(<BackToTop />)

    const scrollRegistration = addEventListener.mock.calls.find(
      ([type]) => String(type) === "scroll"
    )
    expect(scrollRegistration).toEqual(["scroll", expect.any(Function), { passive: true }])

    unmount()
    expect(removeEventListener).toHaveBeenCalledWith("scroll", scrollRegistration?.[1])
  })

  it("does not construct an IntersectionObserver when there is no footer", () => {
    const construct = vi.fn()
    class MockIntersectionObserver {
      constructor() {
        construct()
      }

      observe = vi.fn()
      disconnect = vi.fn()
    }
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver)

    render(<BackToTop />)

    expect(construct).not.toHaveBeenCalled()
  })

  it("configures a dense footer threshold and shifts by the visible footer pixels", async () => {
    const observe = vi.fn()
    const disconnect = vi.fn()
    let callback: IntersectionObserverCallback | undefined
    let options: IntersectionObserverInit | undefined
    class MockIntersectionObserver {
      constructor(next: IntersectionObserverCallback, nextOptions?: IntersectionObserverInit) {
        callback = next
        options = nextOptions
      }

      observe = observe
      disconnect = disconnect
    }
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver)
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 800 })
    const footer = document.createElement("footer")
    footer.setAttribute("role", "contentinfo")
    document.body.appendChild(footer)

    render(<BackToTop />)

    expect(options?.threshold).toEqual(Array.from({ length: 21 }, (_, i) => i / 20))
    expect(observe).toHaveBeenCalledWith(footer)
    callback?.(
      [{ isIntersecting: true, boundingClientRect: { top: 700 } } as IntersectionObserverEntry],
      {} as IntersectionObserver
    )
    setScrollY(500)
    fireEvent.scroll(window)
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: getLabel() }).parentElement?.parentElement
      ).toHaveStyle("bottom: 140px")
    )

    footer.remove()
  })

  it("keeps the FAB shell and pointer interaction contract stable", async () => {
    render(<BackToTop />)
    setScrollY(500)
    fireEvent.scroll(window)

    await waitFor(() =>
      expect(screen.getByRole("button", { name: getLabel() })).toBeInTheDocument()
    )
    const wrap = screen.getByRole("button", { name: getLabel() }).parentElement?.parentElement
    expect(wrap).toHaveClass("fixed", "right-6", "z-tooltip", "back-to-top-wrap")
    expect(wrap).toHaveStyle({ pointerEvents: "auto" })
  })
})
