import { render, renderHook, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/hooks/useAnimatedFloat", () => ({
  useAnimatedFloat: (value: number) => value,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { value?: string }) => options?.value ?? key,
  }),
}))

import AnimatedRing, { useAnimatedNumber } from "../AnimatedRing"
import { ParticipationCard } from "../ParticipationCard"

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

  it("fills count mode relative to a positive goal", () => {
    render(<AnimatedRing value={5} max={10} mode="count" />)
    expect(screen.getByText("5")).toBeInTheDocument()
  })

  it("guards NaN values and exposes the exported animated-number helper", () => {
    render(<AnimatedRing value={Number.NaN} mode="gauge" max={0} />)
    expect(screen.getByText("0.0")).toBeInTheDocument()

    const { result } = renderHook(() => useAnimatedNumber(3.14159, 100, 2))
    expect(result.current).toBe("3.14")
  })
})

describe("ParticipationCard", () => {
  it("renders its loading contract and null-data defaults", () => {
    const { rerender } = render(
      <ParticipationCard
        participation={null}
        hasInitiallyLoaded={false}
        separator=" · "
        ringSize={80}
      />
    )
    expect(document.querySelector(".animate-pulse")).toBeInTheDocument()

    rerender(
      <ParticipationCard participation={null} hasInitiallyLoaded separator=" · " ringSize={80} />
    )
    expect(screen.getByText("activity:sections.participation.title")).toBeInTheDocument()
  })

  it("joins available participation summary fields and renders trend data", () => {
    const { rerender } = render(
      <ParticipationCard
        participation={{ events: 3, hours: 5, groups: 2, trend: 1, recent: [] }}
        hasInitiallyLoaded
        separator=" · "
        ringSize={80}
      />
    )
    expect(screen.getByText(/activity:sections\.participation\.summaryHours/)).toBeInTheDocument()

    rerender(
      <ParticipationCard
        participation={{ events: 3, trend: 0, recent: [] }}
        hasInitiallyLoaded
        separator=" · "
        ringSize={80}
      />
    )
    expect(screen.getByText("activity:sections.participation.title")).toBeInTheDocument()
  })
})
