import { render, renderHook, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/hooks/useAnimatedFloat", () => ({
  useAnimatedFloat: (value: number) => value,
}))

import AnimatedRing, { useAnimatedNumber } from "../AnimatedRing"

describe("AnimatedRing mode and numeric guards", () => {
  it("renders a clamped percent ring", () => {
    render(<AnimatedRing value={50} size={80} ariaLabel="half" />)
    expect(screen.getByRole("img", { name: "half" })).toBeInTheDocument()
    expect(screen.getByText("50%")).toBeInTheDocument()
  })

  it("renders gauge labels with the four-point display convention", () => {
    render(<AnimatedRing value={2} max={4} mode="gauge" size={80} />)
    expect(screen.getByText("2.0")).toBeInTheDocument()
    expect(screen.getByText("/ 4.0")).toBeInTheDocument()
  })

  it("renders count mode with zero max and an explicit fraction", () => {
    render(<AnimatedRing value={7} max={0} mode="count" fraction={2} colorVar="red" />)
    expect(screen.getByText("7")).toBeInTheDocument()
    expect(screen.queryByText(/\//)).not.toBeInTheDocument()
    expect(document.querySelector("[style*='--_ring-color']")).toBeInTheDocument()
  })

  it("guards NaN values and exposes the exported animated-number helper", () => {
    render(<AnimatedRing value={Number.NaN} mode="gauge" max={0} />)
    expect(screen.getByText("0.0")).toBeInTheDocument()

    const { result } = renderHook(() => useAnimatedNumber(3.14159, 100, 2))
    expect(result.current).toBe("3.14")
  })
})
