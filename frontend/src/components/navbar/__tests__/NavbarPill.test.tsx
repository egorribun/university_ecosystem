import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"

import { NavbarPill } from "@/components/navbar/NavbarPill"

// Pure prop-driven (only cn) — the 2×2 isCompact × prefersReducedMotion matrix is
// the branch ROI: gradient overlay (compact only) + duration / pill-breathe classes.

describe("NavbarPill", () => {
  it("toggles the gradient overlay + breathing animation between states", () => {
    const { container, rerender } = render(
      <NavbarPill isCompact={false} prefersReducedMotion={false}>
        <span>nav</span>
      </NavbarPill>
    )
    expect(screen.getByText("nav")).toBeInTheDocument()
    // Expanded → no gradient overlay.
    expect(container.querySelector('[aria-hidden="true"]')).toBeNull()

    rerender(
      <NavbarPill isCompact prefersReducedMotion={false}>
        <span>nav</span>
      </NavbarPill>
    )
    const outer = container.firstChild as HTMLElement
    expect(outer.className).toContain("duration-500")
    expect(outer.className).toContain("animate-pill-breathe")
    // Compact → gradient overlay present.
    expect(container.querySelector('[aria-hidden="true"]')).not.toBeNull()
  })

  it("disables animation under reduced motion (compact)", () => {
    const { container } = render(
      <NavbarPill isCompact prefersReducedMotion>
        <span>nav</span>
      </NavbarPill>
    )
    const outer = container.firstChild as HTMLElement
    expect(outer.className).toContain("duration-0")
    expect(outer.className).not.toContain("animate-pill-breathe")
  })

  it("uses duration-0 in the expanded reduced-motion state", () => {
    const { container } = render(
      <NavbarPill isCompact={false} prefersReducedMotion>
        <span>nav</span>
      </NavbarPill>
    )
    expect((container.firstChild as HTMLElement).className).toContain("duration-0")
  })
})
