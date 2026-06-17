import { render } from "@testing-library/react"
import { describe, it, expect } from "vitest"

import { EventDetailSkeleton } from "@/components/events/EventDetailSkeleton"

describe("EventDetailSkeleton", () => {
  it("renders the themed skeleton scaffold with default props", () => {
    const { container } = render(<EventDetailSkeleton />)
    const root = container.firstElementChild
    expect(root).not.toBeNull()
    expect(root).toHaveClass("events-theme")
    expect(root).toHaveClass("aurora-mesh")
    expect(root).toHaveClass("overflow-clip")
    // EventsBackdrop (aria-hidden decorative layer) renders inside.
    expect(container.querySelector("[aria-hidden='true']")).not.toBeNull()
  })

  it("renders the full set of pulsing placeholder blocks", () => {
    const { container } = render(<EventDetailSkeleton />)
    // Back button, badge, title (x2), meta pills (x3), hero, body (x4),
    // related header + 3 cards — all use animate-pulse.
    const pulses = container.querySelectorAll(".animate-pulse")
    expect(pulses.length).toBeGreaterThanOrEqual(10)
    // Hero image placeholder.
    expect(container.querySelector(".aspect-video")).not.toBeNull()
    // Three related-event card skeletons.
    expect(container.querySelectorAll(".grid > .rounded-xl")).toHaveLength(3)
  })

  it("renders the same structure for the narrow + reduced-motion combination", () => {
    const { container } = render(<EventDetailSkeleton isNarrow prefersReducedMotion />)
    const root = container.firstElementChild
    expect(root).toHaveClass("events-theme")
    // Structure is prop-independent — backdrop still present, blocks unchanged.
    expect(container.querySelector("[aria-hidden='true']")).not.toBeNull()
    expect(container.querySelector(".aspect-video")).not.toBeNull()
    expect(container.querySelectorAll(".grid > .rounded-xl")).toHaveLength(3)
  })

  it("renders without crashing for each explicit prop combination", () => {
    expect(() =>
      render(<EventDetailSkeleton isNarrow={false} prefersReducedMotion={false} />)
    ).not.toThrow()
    expect(() =>
      render(<EventDetailSkeleton isNarrow prefersReducedMotion={false} />)
    ).not.toThrow()
    expect(() =>
      render(<EventDetailSkeleton isNarrow={false} prefersReducedMotion />)
    ).not.toThrow()
  })
})
