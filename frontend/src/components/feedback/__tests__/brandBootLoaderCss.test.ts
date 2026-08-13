import { describe, expect, it } from "vitest"

import { BRAND_BOOT_LOADER_CSS } from "../brandBootLoaderCss"

const ruleBody = (selector: string) => {
  const selectorStart = BRAND_BOOT_LOADER_CSS.indexOf(`${selector} {`)
  if (selectorStart === -1) return ""

  const bodyStart = BRAND_BOOT_LOADER_CSS.indexOf("{", selectorStart) + 1
  const bodyEnd = BRAND_BOOT_LOADER_CSS.indexOf("}", bodyStart)
  return BRAND_BOOT_LOADER_CSS.slice(bodyStart, bodyEnd)
}

describe("BRAND_BOOT_LOADER_CSS", () => {
  it("preserves exact brand colors and the six-second master timing", () => {
    expect(BRAND_BOOT_LOADER_CSS).toContain("--brand-boot-loader-navy: #033167")
    expect(BRAND_BOOT_LOADER_CSS).toContain("--brand-boot-loader-red: #e40137")
    expect(BRAND_BOOT_LOADER_CSS).toContain("--brand-boot-loader-cycle: 6s")
    expect(BRAND_BOOT_LOADER_CSS).toContain("--brand-boot-loader-hold: 2500ms")
    expect(BRAND_BOOT_LOADER_CSS).toContain("43.5%,")
    expect(BRAND_BOOT_LOADER_CSS).toContain("85.1667%")
    expect(BRAND_BOOT_LOADER_CSS).toContain("92.6667%")
  })

  it("scales fluidly through 4K and suppresses the covered document scrollbar", () => {
    expect(BRAND_BOOT_LOADER_CSS).toContain("--brand-boot-loader-size: clamp(9rem, 22vmin, 30rem)")
    expect(BRAND_BOOT_LOADER_CSS).toContain(
      "--brand-boot-loader-status-size: clamp(0.6875rem, 1.4vmin, 1.125rem)"
    )
    expect(BRAND_BOOT_LOADER_CSS).toContain("html:has(.brand-boot-loader)")
    expect(ruleBody("html:has(.brand-boot-loader)")).toContain("overflow-y: clip")
    expect(ruleBody("html:has(.brand-boot-loader)")).toContain(
      "animation: brand-boot-loader-scroll-unlock 1ms linear 12s forwards"
    )
    expect(ruleBody(".brand-boot-loader ~ #root")).toContain("overflow-x: clip")
  })

  it("fades both colors through the common mark and never cycles the status opacity", () => {
    expect(ruleBody(".brand-boot-loader__mark")).toContain("animation: brand-boot-loader-mark-exit")
    expect(ruleBody(".brand-boot-loader__status")).not.toMatch(/\banimation\s*:/)
    expect(BRAND_BOOT_LOADER_CSS).not.toContain("status-exit")
  })

  it("contains no animated transform, rocking, pulse, glow, or halo", () => {
    const keyframes = BRAND_BOOT_LOADER_CSS.split("@keyframes").slice(1).join("@keyframes")
    expect(keyframes).not.toMatch(/\btransform\s*:/)
    expect(BRAND_BOOT_LOADER_CSS).not.toMatch(/rock|pulse|glow|halo/i)
  })

  it("provides final exit, no-JS failsafe, reduced motion, and hidden-tab pause", () => {
    expect(ruleBody('.brand-boot-loader[data-state="exiting"]')).toContain("opacity: 0")
    expect(BRAND_BOOT_LOADER_CSS).toContain("12s")
    expect(BRAND_BOOT_LOADER_CSS).toContain("@keyframes brand-boot-loader-scroll-unlock")
    expect(BRAND_BOOT_LOADER_CSS).toContain("@media (prefers-reduced-motion: reduce)")
    expect(BRAND_BOOT_LOADER_CSS).toContain('[data-paused="true"]')
    expect(BRAND_BOOT_LOADER_CSS).toContain(".lhci-mode .brand-boot-loader")
  })
})
