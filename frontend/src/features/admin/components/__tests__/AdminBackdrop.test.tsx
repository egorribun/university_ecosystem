/**
 * Coverage tests for AdminBackdrop (testing session 9).
 *
 * Pure presentational orb layer (previously ~3% covered). Verifies the
 * aria-hidden decorative discipline + the isNarrow / prefersReducedMotion
 * conditional orb matrix (W118 SW3 pixel-anchored pattern).
 */
import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { AdminBackdrop } from "@/features/admin/components/AdminBackdrop"

const orbCount = (container: HTMLElement): number =>
  container.querySelectorAll("[aria-hidden='true'] > div").length

describe("AdminBackdrop", () => {
  it("renders all four orbs on wide viewports with motion enabled", () => {
    const { container } = render(<AdminBackdrop isNarrow={false} prefersReducedMotion={false} />)
    const wrapper = container.querySelector("[aria-hidden='true']")
    expect(wrapper).not.toBeNull()
    expect(wrapper?.className).toContain("pointer-events-none")
    expect(orbCount(container)).toBe(4)
  })

  it("drops the highlight and conic orbs on narrow viewports", () => {
    const { container } = render(<AdminBackdrop isNarrow={true} prefersReducedMotion={false} />)
    expect(orbCount(container)).toBe(2)
  })

  it("suppresses the drifting conic orb under reduced motion", () => {
    const { container } = render(<AdminBackdrop isNarrow={false} prefersReducedMotion={true} />)
    expect(orbCount(container)).toBe(3)
    const html = container.innerHTML
    expect(html).not.toContain("orb-drift")
  })
})
