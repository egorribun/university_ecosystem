import { render } from "@testing-library/react"
import { describe, it, expect } from "vitest"
import { MapBackdrop } from "@/components/map/MapBackdrop"

describe("MapBackdrop", () => {
  it("renders the decorative aria-hidden container", () => {
    const { container } = render(<MapBackdrop isNarrow={false} prefersReducedMotion={false} />)
    const root = container.firstChild as HTMLElement
    expect(root).not.toBeNull()
    expect(root).toHaveAttribute("aria-hidden", "true")
    expect(root.className).toContain("pointer-events-none")
    expect(root.className).toContain("overflow-hidden")
  })

  it("renders all four orbs when wide and motion enabled", () => {
    const { container } = render(<MapBackdrop isNarrow={false} prefersReducedMotion={false} />)
    const root = container.firstChild as HTMLElement
    // hero + highlight + conic + bottom = 4 child orb divs
    expect(root.children).toHaveLength(4)
  })

  it("omits the highlight and conic orbs when narrow", () => {
    const { container } = render(<MapBackdrop isNarrow={true} prefersReducedMotion={false} />)
    const root = container.firstChild as HTMLElement
    // hero + bottom only (highlight + conic both gated by !isNarrow)
    expect(root.children).toHaveLength(2)
  })

  it("omits the drifting conic orb when reduced motion is preferred", () => {
    const { container } = render(<MapBackdrop isNarrow={false} prefersReducedMotion={true} />)
    const root = container.firstChild as HTMLElement
    // hero + highlight + bottom = 3 (conic gated by !prefersReducedMotion)
    expect(root.children).toHaveLength(3)
    // no element should carry the orb-drift animation
    const drifting = Array.from(root.children).find((el) =>
      (el as HTMLElement).style.animation.includes("orb-drift")
    )
    expect(drifting).toBeUndefined()
  })

  it("applies the orb-drift animation to the conic orb only when wide + motion", () => {
    const { container } = render(<MapBackdrop isNarrow={false} prefersReducedMotion={false} />)
    const root = container.firstChild as HTMLElement
    const drifting = Array.from(root.children).find((el) =>
      (el as HTMLElement).style.animation.includes("orb-drift")
    )
    expect(drifting).toBeDefined()
  })

  it("renders nothing extra when narrow + reduced motion (minimal orbs)", () => {
    const { container } = render(<MapBackdrop isNarrow={true} prefersReducedMotion={true} />)
    const root = container.firstChild as HTMLElement
    // only hero + bottom survive both gates
    expect(root.children).toHaveLength(2)
  })
})
