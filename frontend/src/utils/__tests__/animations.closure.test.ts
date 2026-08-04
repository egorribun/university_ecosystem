import { describe, expect, it } from "vitest"
import {
  easeBackOut,
  easeOutExpo,
  easePremium,
  fadeVariants,
  hoverLift,
  hoverScale,
  revealVariants,
  scaleInVariants,
  slideUpVariants,
  springBouncy,
  springHeavy,
  springSoft,
  staggerContainerVariants,
} from "@/utils/animations"

describe("animation tokens and variants", () => {
  it("exports the shared easing and spring presets", () => {
    expect(easePremium).toEqual([0.22, 1, 0.36, 1])
    expect(easeOutExpo).toEqual([0.16, 1, 0.3, 1])
    expect(easeBackOut).toEqual([0.34, 1.56, 0.64, 1])
    expect(springHeavy).toMatchObject({ type: "spring", stiffness: 200, damping: 30, mass: 1.5 })
    expect(springSoft).toMatchObject({ type: "spring", stiffness: 260, damping: 25, mass: 1 })
    expect(springBouncy).toMatchObject({ type: "spring", stiffness: 400, damping: 15, mass: 0.8 })
  })

  it("contains the reusable fade, slide, scale, and interaction variants", () => {
    expect(fadeVariants).toHaveProperty("hidden")
    expect(fadeVariants).toHaveProperty("visible")
    expect(fadeVariants).toHaveProperty("exit")
    expect(slideUpVariants.hidden).toMatchObject({ opacity: 0, y: 30 })
    expect(scaleInVariants.visible).toMatchObject({ opacity: 1, scale: 1 })
    expect(hoverScale.hover).toMatchObject({ scale: 1.02 })
    expect(hoverScale.tap).toMatchObject({ scale: 0.97 })
    expect(hoverLift.hover).toMatchObject({ y: -8 })
    expect(hoverLift.tap).toMatchObject({ y: -2 })
  })

  it("builds stagger and directional reveal variants for every direction", () => {
    expect(staggerContainerVariants(0.2, 0.3).visible).toMatchObject({
      transition: { staggerChildren: 0.2, delayChildren: 0.3 },
    })

    expect(revealVariants("up").hidden).toMatchObject({ x: 0, y: 40 })
    expect(revealVariants("down").hidden).toMatchObject({ x: 0, y: -40 })
    expect(revealVariants("left").hidden).toMatchObject({ x: 40, y: 0 })
    expect(revealVariants("right").hidden).toMatchObject({ x: -40, y: 0 })
    expect(revealVariants().hidden).toMatchObject({ x: 0, y: 40 })
  })
})
