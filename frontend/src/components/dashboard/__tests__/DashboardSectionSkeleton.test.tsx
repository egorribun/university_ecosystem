import { render } from "@testing-library/react"
import { describe, it, expect } from "vitest"
import { DashboardSectionSkeleton } from "@/components/dashboard/DashboardSectionSkeleton"

describe("DashboardSectionSkeleton", () => {
  it("renders the schedule variant with 3 list rows", () => {
    const { container } = render(<DashboardSectionSkeleton type="schedule" />)
    const card = container.querySelector(".card-matte")
    expect(card).toBeInTheDocument()
    expect(card).toHaveClass("glass-noise")
    // 3 schedule rows, each with bg-(--bg-matte-list)
    const rows = container.querySelectorAll('[class*="bg-(--bg-matte-list)"]')
    expect(rows.length).toBe(3)
  })

  it("renders the news variant with 2 list rows", () => {
    const { container } = render(<DashboardSectionSkeleton type="news" />)
    const card = container.querySelector(".card-matte")
    expect(card).toBeInTheDocument()
    const rows = container.querySelectorAll('[class*="bg-(--bg-matte-list)"]')
    expect(rows.length).toBe(2)
  })

  it("renders the events variant with 3 list rows", () => {
    const { container } = render(<DashboardSectionSkeleton type="events" />)
    expect(container.querySelector(".card-matte")).toBeInTheDocument()
    const rows = container.querySelectorAll('[class*="bg-(--bg-matte-list)"]')
    expect(rows.length).toBe(3)
  })

  it("forwards a custom className onto the Card", () => {
    const { container } = render(
      <DashboardSectionSkeleton type="schedule" className="custom-test-class" />
    )
    const card = container.querySelector(".card-matte")
    expect(card).toHaveClass("custom-test-class")
    expect(card).toHaveClass("p-6", "h-full")
  })

  it("always renders the heading skeleton regardless of variant", () => {
    const { container } = render(<DashboardSectionSkeleton type="news" />)
    // The heading Skeleton has mb-5; at least one skeleton element should exist
    const skeletons = container.querySelectorAll(".mb-5")
    expect(skeletons.length).toBeGreaterThan(0)
  })
})
