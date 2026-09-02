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

  it("preserves the hero orb geometry and visual tokens", () => {
    const { container } = render(<MapBackdrop isNarrow={false} prefersReducedMotion={false} />)
    const hero = (container.firstChild as HTMLElement).children[0] as HTMLElement

    expect(hero.style.width).toBe("800px")
    expect(hero.style.height).toBe("500px")
    expect(hero.style.background).toContain("var(--map-hero-orb)")
    expect(hero.style.background).toContain("transparent 72%")
    expect(hero.style.filter).toBe("blur(40px)")
  })

  it("preserves the highlight orb geometry and visual tokens", () => {
    const { container } = render(<MapBackdrop isNarrow={false} prefersReducedMotion={false} />)
    const highlight = (container.firstChild as HTMLElement).children[1] as HTMLElement

    expect(highlight.style.width).toBe("450px")
    expect(highlight.style.height).toBe("350px")
    expect(highlight.style.background).toContain("var(--map-hero-highlight)")
    expect(highlight.style.background).toContain("transparent 60%")
    expect(highlight.style.filter).toBe("blur(50px)")
  })

  it("preserves the conic orb geometry and visual tokens", () => {
    const { container } = render(<MapBackdrop isNarrow={false} prefersReducedMotion={false} />)
    const conic = (container.firstChild as HTMLElement).children[2] as HTMLElement

    expect(conic.style.width).toBe("400px")
    expect(conic.style.height).toBe("400px")
    expect(conic.style.background).toBe("var(--grad-map-conic)")
    expect(conic.style.filter).toBe("blur(60px)")
  })

  it("preserves the bottom orb geometry and visual tokens", () => {
    const { container } = render(<MapBackdrop isNarrow={false} prefersReducedMotion={false} />)
    const bottom = (container.firstChild as HTMLElement).children[3] as HTMLElement

    expect(bottom.style.width).toBe("400px")
    expect(bottom.style.height).toBe("300px")
    expect(bottom.style.background).toContain("var(--map-orb-3)")
    expect(bottom.style.background).toContain("transparent 65%")
    expect(bottom.style.filter).toBe("blur(50px)")
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
