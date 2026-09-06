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

import BackToTop from "@/components/motion/BackToTop"

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
})
