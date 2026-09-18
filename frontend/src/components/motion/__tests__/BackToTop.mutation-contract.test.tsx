import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const state = vi.hoisted(() => ({
  namespaces: [] as unknown[],
}))

vi.mock("react-i18next", () => ({
  useTranslation: (namespaces: unknown) => {
    state.namespaces.push(namespaces)
    return { t: (key: string) => key }
  },
}))

vi.mock("framer-motion", async () => {
  const React = await import("react")
  type Props = Record<string, unknown> & { children?: React.ReactNode }
  const serialise = (value: unknown) => (value === undefined ? "undefined" : JSON.stringify(value))
  const MotionButton = React.forwardRef<HTMLButtonElement, Props>(function MotionButton(
    { children, initial, animate, exit, transition, whileHover, whileTap, ...props },
    ref
  ) {
    return React.createElement(
      "button",
      {
        ...props,
        ref,
        "data-motion-initial": serialise(initial),
        "data-motion-animate": serialise(animate),
        "data-motion-exit": serialise(exit),
        "data-motion-transition": serialise(transition),
        "data-motion-while-hover": serialise(whileHover),
        "data-motion-while-tap": serialise(whileTap),
      },
      children as React.ReactNode
    )
  })
  return {
    m: { button: MotionButton },
    AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  }
})

import { disconnectBackToTopObserver, default as BackToTop } from "@/components/motion/BackToTop"

const setScrollY = (value: number) => {
  Object.defineProperty(window, "scrollY", { value, configurable: true })
}

beforeEach(() => {
  state.namespaces.length = 0
  setScrollY(0)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("BackToTop mutation contract", () => {
  it("keeps mount effects stable and observer cleanup null-safe", () => {
    expect(() => disconnectBackToTopObserver(null)).not.toThrow()
    const disconnect = vi.fn()
    disconnectBackToTopObserver({ disconnect } as unknown as IntersectionObserver)
    expect(disconnect).toHaveBeenCalledOnce()
  })

  it("registers the scroll listener only once across rerenders", () => {
    const addEventListener = vi.spyOn(window, "addEventListener")
    const removeEventListener = vi.spyOn(window, "removeEventListener")
    const { rerender, unmount } = render(<BackToTop />)

    rerender(<BackToTop />)

    expect(addEventListener.mock.calls.filter(([type]) => String(type) === "scroll")).toHaveLength(
      1
    )
    unmount()
    expect(
      removeEventListener.mock.calls.filter(([type]) => String(type) === "scroll")
    ).toHaveLength(1)
  })

  it("creates and observes the footer once across rerenders", () => {
    const observe = vi.fn()
    const disconnect = vi.fn()
    const footer = document.createElement("footer")
    footer.setAttribute("role", "contentinfo")
    document.body.appendChild(footer)
    class MockIntersectionObserver {
      constructor() {
        // The callback is not needed for this lifecycle contract.
      }

      observe = observe
      disconnect = disconnect
    }
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver)

    const { rerender, unmount } = render(<BackToTop />)
    rerender(<BackToTop />)

    expect(observe).toHaveBeenCalledOnce()
    unmount()
    expect(disconnect).toHaveBeenCalledOnce()
    footer.remove()
  })

  it("passes the common namespace and exact motion contract to the FAB", async () => {
    render(<BackToTop />)
    expect(state.namespaces).toContainEqual(["common"])

    setScrollY(500)
    fireEvent.scroll(window)
    const button = await waitFor(() =>
      screen.getByRole("button", { name: "common:buttons.backToTop" })
    )
    expect(button).toHaveAttribute(
      "data-motion-initial",
      JSON.stringify({ opacity: 0, scale: 0.5, y: 20 })
    )
    expect(button).toHaveAttribute(
      "data-motion-animate",
      JSON.stringify({ opacity: 1, scale: 1, y: 0 })
    )
    expect(button).toHaveAttribute(
      "data-motion-exit",
      JSON.stringify({ opacity: 0, scale: 0.5, y: 20 })
    )
    expect(button).toHaveAttribute(
      "data-motion-transition",
      JSON.stringify({ type: "spring", stiffness: 400, damping: 25 })
    )
    expect(button).toHaveAttribute("data-motion-while-hover", JSON.stringify({ scale: 1.1, y: -3 }))
    expect(button).toHaveAttribute("data-motion-while-tap", JSON.stringify({ scale: 0.92 }))
  })

  it("keeps the footer offset clamped when the footer is below the viewport", async () => {
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
    callback?.(
      [{ isIntersecting: true, boundingClientRect: { top: 900 } } as IntersectionObserverEntry],
      {} as IntersectionObserver
    )
    setScrollY(500)
    fireEvent.scroll(window)
    const button = await waitFor(() =>
      screen.getByRole("button", { name: "common:buttons.backToTop" })
    )
    expect(button.parentElement?.parentElement).toHaveStyle("bottom: 24px")

    unmount()
    expect(disconnect).toHaveBeenCalledOnce()
    footer.remove()
  })

  it("falls back to the legacy scroll API when smooth scrolling is unavailable", async () => {
    const scrollTo = vi
      .spyOn(window, "scrollTo")
      .mockImplementationOnce(() => {
        throw new Error("smooth scrolling is unavailable")
      })
      .mockImplementationOnce(() => undefined)

    render(<BackToTop />)
    setScrollY(500)
    fireEvent.scroll(window)
    const button = await waitFor(() =>
      screen.getByRole("button", { name: "common:buttons.backToTop" })
    )

    fireEvent.click(button)

    expect(scrollTo).toHaveBeenNthCalledWith(1, { top: 0, behavior: "smooth" })
    expect(scrollTo).toHaveBeenNthCalledWith(2, 0, 0)
  })
})
