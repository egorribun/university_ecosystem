import { act, render, renderHook, screen } from "@testing-library/react"
import type { MouseEvent as ReactMouseEvent } from "react"
import { describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", async () => {
  const base = (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
  return {
    ...base,
    useMotionValue: (initial: number) => {
      let value = initial
      return {
        get: () => value,
        set: (next: number) => {
          value = next
        },
        on: () => () => undefined,
        destroy: () => undefined,
        clearListeners: () => undefined,
        toString: () => String(value),
      }
    },
  }
})

import { Spotlight, SpotlightOverlay, useSpotlight } from "@/components/ui/Spotlight"

describe("Spotlight", () => {
  it("tracks pointer coordinates relative to the target element", () => {
    const { result } = renderHook(() => useSpotlight())
    const currentTarget = {
      getBoundingClientRect: () => ({ left: 11, top: 17 }),
    }

    act(() => {
      result.current.onMouseMove({
        currentTarget,
        clientX: 41,
        clientY: 67,
      } as unknown as ReactMouseEvent<HTMLElement>)
    })

    expect(result.current.mouseX.get()).toBe(30)
    expect(result.current.mouseY.get()).toBe(50)
  })

  it("renders the wrapper, children, and default overlay", () => {
    const { container } = render(
      <Spotlight className="custom-shell">
        <span>Spotlight child</span>
      </Spotlight>
    )

    expect(screen.getByText("Spotlight child").parentElement).toHaveClass(
      "group",
      "relative",
      "overflow-hidden",
      "custom-shell"
    )
    expect(container.querySelector(".pointer-events-none")).toBeInTheDocument()
  })

  it("allows an overlay class override", () => {
    const { result } = renderHook(() => useSpotlight())
    const { container } = render(
      <SpotlightOverlay
        mouseX={result.current.mouseX}
        mouseY={result.current.mouseY}
        className="overlay-override"
      />
    )

    expect(container.firstElementChild).toHaveClass("overlay-override")
  })
})
