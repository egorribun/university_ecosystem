import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const state = vi.hoisted(() => ({ storiesInHero: false }))
const mediaQueryMock = vi.hoisted(() => vi.fn(() => state.storiesInHero))

vi.mock("@/hooks/useMediaQuery", () => ({ default: mediaQueryMock }))

import { DashboardSkeleton } from "@/components/dashboard/DashboardSkeleton"

describe("DashboardSkeleton", () => {
  beforeEach(() => {
    state.storiesInHero = false
    mediaQueryMock.mockClear()
  })

  it("renders mobile story placeholders below the hero", () => {
    render(<DashboardSkeleton />)

    expect(mediaQueryMock).toHaveBeenCalledWith("(min-width: 1220px)")
    expect(screen.getAllByLabelText("Loading story")).toHaveLength(5)
  })

  it("renders desktop story placeholders inside the hero", () => {
    state.storiesInHero = true
    render(<DashboardSkeleton />)

    expect(mediaQueryMock).toHaveBeenCalledWith("(min-width: 1220px)")
    expect(screen.queryByLabelText("Loading story")).not.toBeInTheDocument()
    expect(
      document.querySelectorAll('.flex-1.overflow-hidden [style*="border-radius: 50%"]')
    ).toHaveLength(6)
  })

  it("preserves the gradient shell and deterministic card skeleton geometry", () => {
    const { container } = render(<DashboardSkeleton />)

    const root = container.firstElementChild
    expect(root).toHaveClass("flex", "min-h-screen", "w-full", "flex-col")
    expect(root).toHaveAttribute(
      "style",
      expect.stringContaining(
        "background: linear-gradient(145deg, var(--hero-grad-start), var(--hero-grad-end))"
      )
    )

    const cards = [...container.querySelectorAll(".card-matte")]
    expect(cards).toHaveLength(4)
    // Hero card, schedule card, news card, events card. Exact counts make
    // every Array.from/map branch observable to mutation testing.
    expect(cards.slice(1).map((card) => card.querySelectorAll(".skeleton").length)).toEqual([
      10, 7, 12,
    ])
    expect(cards[1]).toHaveClass("col-span-12", "lg:col-span-4", "min-h-[400px]")
    expect(cards[2]).toHaveClass("col-span-12", "lg:col-span-4", "min-h-[400px]")
    expect(cards[3]).toHaveClass("col-span-12", "lg:col-span-4", "min-h-[400px]")
  })
})
