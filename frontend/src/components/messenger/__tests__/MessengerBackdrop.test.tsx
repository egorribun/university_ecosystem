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

  it("keeps the secondary and tertiary orbs top-anchored with their theme gradients", () => {
    const { container } = render(<MessengerBackdrop />)
    const orbs = container.querySelectorAll<HTMLElement>(".rounded-full")
    expect(orbs).toHaveLength(3)
    expect(orbs[0]).toHaveStyle({
      left: "50%",
      transform: "translateX(-50%)",
      background: "radial-gradient(ellipse at center, var(--messenger-orb-1), transparent 70%)",
      opacity: "0.6",
      top: "-160px",
    })
    expect(orbs[1]).toHaveStyle({
      width: "42%",
      height: "320px",
      top: "100px",
      right: "-6%",
      background: "radial-gradient(ellipse at center, var(--messenger-orb-2), transparent 70%)",
      opacity: "0.5",
    })
    expect(orbs[2]).toHaveStyle({
      width: "38%",
      height: "300px",
      top: "400px",
      left: "5%",
      background: "radial-gradient(ellipse at center, var(--messenger-orb-3), transparent 70%)",
      opacity: "0.4",
    })
  })

  it("uses the compact top geometry for every orb on a narrow mobile stage", () => {
    const { container } = render(<MessengerBackdrop isNarrow isMobile />)
    const orbs = container.querySelectorAll<HTMLElement>(".rounded-full")
    expect(orbs[0]).toHaveStyle({ width: "120%", height: "380px", top: "-120px", left: "50%" })
    expect(orbs[1]).toHaveStyle({ width: "60%", height: "240px", top: "60px", right: "-12%" })
    expect(orbs[2]).toHaveStyle({ width: "70%", height: "240px", top: "320px", left: "-10%" })
    orbs.forEach((orb) => expect(orb.style.filter).toBe("none"))
  })
})
