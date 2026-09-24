import { describe, expect, it } from "vitest"
import { ANIMATION_VARIANTS, DURATIONS, EASING } from "../motion"
import { motion as motionTokens } from "@/theme/tokens"

describe("motion presets", () => {
  it("fades and scales in from, and back out to, an invisible state", () => {
    expect(ANIMATION_VARIANTS).toStrictEqual({
      fadeIn: {
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        exit: { opacity: 0 },
      },
      scaleIn: {
        initial: { opacity: 0, scale: 0.95 },
        animate: { opacity: 1, scale: 1 },
        exit: { opacity: 0, scale: 0.95 },
      },
    })
  })

  it("derives durations from the theme motion tokens", () => {
    expect(DURATIONS).toStrictEqual({
      fast: motionTokens.durationFast,
      medium: motionTokens.durationMedium,
      slow: 0.5,
    })
    expect(EASING.springSoft).toStrictEqual({ type: "spring", stiffness: 400, damping: 30 })
  })
})
