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
import { motion as motionTokens } from "@/theme/tokens"

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

  it("defines complete enter and exit states for the reusable variants", () => {
    expect(fadeVariants).toStrictEqual({
      hidden: { opacity: 0 },
      visible: {
        opacity: 1,
        transition: { duration: motionTokens.durationSlower, ease: easePremium },
      },
      exit: { opacity: 0, transition: { duration: motionTokens.durationMedium } },
    })
    expect(slideUpVariants).toStrictEqual({
      hidden: { opacity: 0, y: 30 },
      visible: { opacity: 1, y: 0, transition: { ...springSoft } },
      exit: {
        opacity: 0,
        y: -20,
        transition: { duration: motionTokens.durationBase, ease: "easeOut" },
      },
    })
    expect(scaleInVariants).toStrictEqual({
      hidden: { opacity: 0, scale: 0.94, filter: "blur(var(--blur-xs))" },
      visible: { opacity: 1, scale: 1, filter: "blur(var(--blur-none))", transition: springHeavy },
      exit: { opacity: 0, scale: 0.98, transition: { duration: motionTokens.durationMedium } },
    })
    expect(staggerContainerVariants()).toStrictEqual({
      hidden: { opacity: 0 },
      visible: { opacity: 1, transition: { staggerChildren: 0.05, delayChildren: 0 } },
    })
  })

  it("uses snappy springs for hover and tap feedback", () => {
    const spring = (stiffness: number) => ({ type: "spring", stiffness, damping: 20 })
    expect(hoverScale).toStrictEqual({
      hover: { scale: 1.02, transition: spring(400) },
      tap: { scale: 0.97, transition: spring(400) },
    })
    expect(hoverLift).toStrictEqual({
      hover: { y: -8, transition: spring(300) },
      tap: { y: -2, transition: spring(400) },
    })
  })

  it("reveals from a blurred offset to a sharp resting position", () => {
    expect(revealVariants("left")).toStrictEqual({
      hidden: { opacity: 0, x: 40, y: 0, filter: "blur(var(--blur-sm))" },
      visible: {
        opacity: 1,
        x: 0,
        y: 0,
        filter: "blur(var(--blur-none))",
        transition: { duration: motionTokens.navTransition, ease: easePremium },
      },
    })
  })
})
