import { render } from "@testing-library/react"
import { describe, it, expect } from "vitest"

import { MessengerBackdrop } from "@/components/messenger/MessengerBackdrop"

/**
 * Wave 202 SW7 — MessengerBackdrop unit tests (one of the 3 previously
 * untested messenger wrappers). Pure presentational: 3 pixel-anchored
 * radial-gradient orbs in an `aria-hidden` layer; `dropBlur = prefersReducedMotion
 * || isMobile` removes the GPU-expensive `filter: blur(...)`; `isNarrow` scales
 * orb dimensions for sub-content-breakpoint viewports. No router/query/i18n,
 * so a plain `render` suffices.
 */
describe("MessengerBackdrop", () => {
  it("renders an aria-hidden, pointer-events-none decorative layer with 3 orbs", () => {
    const { container } = render(<MessengerBackdrop />)
    const layer = container.querySelector('[aria-hidden="true"]')
    expect(layer).toBeTruthy()
    expect(layer?.className).toContain("pointer-events-none")
    expect(container.querySelectorAll(".rounded-full")).toHaveLength(3)
  })

  it("applies blur to every orb by default (desktop, motion allowed)", () => {
    const { container } = render(<MessengerBackdrop />)
    const orbs = container.querySelectorAll<HTMLElement>(".rounded-full")
    orbs.forEach((orb) => expect(orb.style.filter).toMatch(/^blur\(\d+px\)$/))
  })

  it("drops blur on mobile (GPU-cost mitigation)", () => {
    const { container } = render(<MessengerBackdrop isMobile />)
    const orbs = container.querySelectorAll<HTMLElement>(".rounded-full")
    orbs.forEach((orb) => expect(orb.style.filter).toBe("none"))
  })

  it("drops blur when the user prefers reduced motion", () => {
    const { container } = render(<MessengerBackdrop prefersReducedMotion />)
    const orbs = container.querySelectorAll<HTMLElement>(".rounded-full")
    orbs.forEach((orb) => expect(orb.style.filter).toBe("none"))
  })

  it("scales the primary orb down for narrow viewports", () => {
    const { container: wide } = render(<MessengerBackdrop />)
    const { container: narrow } = render(<MessengerBackdrop isNarrow />)
    const wideOrb = wide.querySelector<HTMLElement>(".rounded-full")
    const narrowOrb = narrow.querySelector<HTMLElement>(".rounded-full")
    // Primary orb — wide: 85% / 520px; narrow: 120% / 380px.
    expect(wideOrb?.style.width).toBe("85%")
    expect(wideOrb?.style.height).toBe("520px")
    expect(narrowOrb?.style.width).toBe("120%")
    expect(narrowOrb?.style.height).toBe("380px")
  })
})
