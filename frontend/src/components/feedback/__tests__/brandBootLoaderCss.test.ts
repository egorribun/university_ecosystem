import { describe, expect, it } from "vitest"

import { BRAND_BOOT_LOADER_CSS } from "../brandBootLoaderCss"

const ruleBody = (selector: string) => {
  const selectorStart = BRAND_BOOT_LOADER_CSS.indexOf(`\n${selector} {`)
  if (selectorStart === -1) return ""

  const bodyStart = BRAND_BOOT_LOADER_CSS.indexOf("{", selectorStart) + 1
  const bodyEnd = BRAND_BOOT_LOADER_CSS.indexOf("}", bodyStart)
  return BRAND_BOOT_LOADER_CSS.slice(bodyStart, bodyEnd)
}

function relativeLuminance(hex: string): number {
  const channels = hex.match(/[0-9a-f]{2}/giu)
  if (!channels || channels.length !== 3) throw new Error(`Unsupported color: ${hex}`)
  const [red, green, blue] = channels
  if (red === undefined || green === undefined || blue === undefined) {
    throw new Error(`Unsupported color: ${hex}`)
  }
  const linearize = (channel: string) => {
    const value = Number.parseInt(channel, 16) / 255
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  }
  return linearize(red) * 0.2126 + linearize(green) * 0.7152 + linearize(blue) * 0.0722
}

function contrastRatio(first: string, second: string): number {
  const firstLuminance = relativeLuminance(first)
  const secondLuminance = relativeLuminance(second)
  return (
    (Math.max(firstLuminance, secondLuminance) + 0.05) /
    (Math.min(firstLuminance, secondLuminance) + 0.05)
  )
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

  it("keeps active light-mode status text at WCAG AA contrast", () => {
    const statusColor = ruleBody(":root").match(
      /--brand-boot-loader-status-color:\s*(#[0-9a-f]{6})/iu
    )?.[1]
    const launchSurface = ruleBody(".brand-boot-loader").match(
      /background:\s*var\(--initial-bg,\s*(#[0-9a-f]{6})\)/iu
    )?.[1]

    if (statusColor === undefined || launchSurface === undefined) {
      throw new Error("Loader status foreground or launch surface color is missing")
    }
    expect(contrastRatio(statusColor, launchSurface)).toBeGreaterThanOrEqual(4.5)
    expect(ruleBody(".brand-boot-loader__status")).toContain(
      "color: var(--brand-boot-loader-status-color)"
    )
  })

  it("removes status text from paint during the decorative mark exit", () => {
    expect(
      ruleBody('.brand-boot-loader[data-state="exiting"] .brand-boot-loader__status')
    ).toContain("visibility: hidden")
    expect(ruleBody('.brand-boot-loader[data-state="exiting"]')).toContain("opacity: 0")
    expect(ruleBody(".brand-boot-loader__mark")).toContain("brand-boot-loader-mark-exit")
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
    expect(ruleBody("#root:has(> .brand-boot-loader)")).toContain("overflow-x: clip")
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
