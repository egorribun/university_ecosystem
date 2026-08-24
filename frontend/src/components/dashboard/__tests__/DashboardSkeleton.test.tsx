import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const state = vi.hoisted(() => ({ storiesInHero: false }))

vi.mock("@/hooks/useMediaQuery", () => ({ default: () => state.storiesInHero }))

import { DashboardSkeleton } from "@/components/dashboard/DashboardSkeleton"

describe("DashboardSkeleton", () => {
  beforeEach(() => {
    state.storiesInHero = false
  })

  it("renders mobile story placeholders below the hero", () => {
    render(<DashboardSkeleton />)

    expect(screen.getAllByLabelText("Loading story")).toHaveLength(5)
  })

  it("renders desktop story placeholders inside the hero", () => {
    state.storiesInHero = true
    render(<DashboardSkeleton />)

    expect(screen.queryByLabelText("Loading story")).not.toBeInTheDocument()
    expect(
      document.querySelectorAll('.flex-1.overflow-hidden [style*="border-radius: 50%"]')
    ).toHaveLength(6)
  })
})
