import { describe, expect, it } from "vitest"
import { collectMotionDurationViolations } from "../../../tests/e2e/utils/motionDurationViolations"
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

describe("regular E2E reduced-motion duration collector", () => {
  it.each([
    { property: "transitionDuration", duration: "0s, 0.25s" },
    { property: "transitionDuration", duration: "0ms, 250ms" },
    { property: "animationDuration", duration: "0s, 0.25s" },
    { property: "animationDuration", duration: "0ms, 250ms" },
  ] as const)("detects the second component of $property=$duration", ({ property, duration }) => {
    const root = document.createElement("div")
    root.id = "motion-list"
    root.style.transitionDuration = "0s"
    root.style.animationDuration = "0s"
    root.style[property] = duration
    document.body.append(root)

    try {
      const styles = getComputedStyle(root)
      expect(styles[property]).toBe(duration)
      expect(collectMotionDurationViolations(root)).toEqual([
        {
          selector: "div#motion-list",
          transitionDuration: styles.transitionDuration,
          animationDuration: styles.animationDuration,
        },
      ])
    } finally {
      root.remove()
    }
  })

  it("does not apply the final component's unit to the first duration", () => {
    const root = document.createElement("div")
    root.style.transitionDuration = "1ms, 0s"
    root.style.animationDuration = "0s"
    document.body.append(root)

    try {
      expect(getComputedStyle(root).transitionDuration).toBe("1ms, 0s")
      expect(collectMotionDurationViolations(root)).toEqual([])
    } finally {
      root.remove()
    }
  })

  it("accepts lists whose transition and animation durations are all within the limit", () => {
    const root = document.createElement("div")
    root.style.transitionDuration = "0s, 0.001s"
    root.style.animationDuration = "0s, 0.001s"
    document.body.append(root)

    try {
      const styles = getComputedStyle(root)
      expect(styles.transitionDuration).toBe("0s, 0.001s")
      expect(styles.animationDuration).toBe("0s, 0.001s")
      expect(collectMotionDurationViolations(root)).toEqual([])
    } finally {
      root.remove()
    }
  })

  it.each([
    { duration: "1ms", expectedCount: 0 },
    { duration: "0.001s", expectedCount: 0 },
    { duration: "2ms", expectedCount: 1 },
    { duration: "0.002s", expectedCount: 1 },
  ])("preserves the one-millisecond boundary for $duration", ({ duration, expectedCount }) => {
    const root = document.createElement("div")
    root.id = "motion-boundary"
    root.style.transitionDuration = duration
    root.style.animationDuration = duration
    document.body.append(root)

    try {
      const styles = getComputedStyle(root)
      expect(styles.transitionDuration).toBe(duration)
      expect(styles.animationDuration).toBe(duration)
      const violations = collectMotionDurationViolations(root)
      expect(violations).toHaveLength(expectedCount)
      if (expectedCount === 1) {
        expect(violations).toEqual([
          {
            selector: "div#motion-boundary",
            transitionDuration: duration,
            animationDuration: duration,
          },
        ])
      }
    } finally {
      root.remove()
    }
  })

  it("includes root and hidden descendants but excludes only the svg element", () => {
    const root = document.createElement("section")
    root.id = "motion-root"
    root.className = "first second third fourth"
    root.style.transitionDuration = "2ms"
    root.style.animationDuration = "0s"

    const child = document.createElement("div")
    child.id = "motion-child"
    child.style.transitionDuration = "3ms"
    child.style.animationDuration = "0s"

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg")
    svg.id = "motion-svg"
    svg.style.transitionDuration = "4ms"
    svg.style.animationDuration = "0s"

    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle")
    circle.id = "motion-circle"
    circle.style.transitionDuration = "6ms"
    circle.style.animationDuration = "0s"
    svg.append(circle)

    const hidden = document.createElement("div")
    hidden.id = "motion-hidden"
    hidden.style.display = "none"
    hidden.style.transitionDuration = "5ms"
    hidden.style.animationDuration = "0s"

    root.append(child, svg, hidden)
    document.body.append(root)

    try {
      expect(getComputedStyle(root).transitionDuration).toBe("2ms")
      expect(getComputedStyle(child).transitionDuration).toBe("3ms")
      expect(getComputedStyle(svg).transitionDuration).toBe("4ms")
      expect(getComputedStyle(circle).transitionDuration).toBe("6ms")
      expect(getComputedStyle(hidden).transitionDuration).toBe("5ms")
      expect(getComputedStyle(hidden).display).toBe("none")
      expect(collectMotionDurationViolations(root)).toEqual([
        {
          selector: "section#motion-root.first.second.third",
          transitionDuration: "2ms",
          animationDuration: "0s",
        },
        {
          selector: "div#motion-child",
          transitionDuration: "3ms",
          animationDuration: "0s",
        },
        {
          selector: "circle#motion-circle",
          transitionDuration: "6ms",
          animationDuration: "0s",
        },
        {
          selector: "div#motion-hidden",
          transitionDuration: "5ms",
          animationDuration: "0s",
        },
      ])
    } finally {
      root.remove()
    }
  })

  it("caps reported offenders at the first ten in document order", () => {
    const root = document.createElement("div")
    root.style.transitionDuration = "0s"
    root.style.animationDuration = "0s"
    const children = Array.from({ length: 11 }, (_, index) => {
      const child = document.createElement("div")
      child.id = `motion-offender-${index}`
      child.style.transitionDuration = "2ms"
      child.style.animationDuration = "0s"
      return child
    })
    root.append(...children)
    document.body.append(root)

    try {
      for (const child of children) {
        expect(getComputedStyle(child).transitionDuration).toBe("2ms")
        expect(getComputedStyle(child).animationDuration).toBe("0s")
      }
      expect(collectMotionDurationViolations(root)).toEqual(
        children.slice(0, 10).map((child) => ({
          selector: `div#${child.id}`,
          transitionDuration: "2ms",
          animationDuration: "0s",
        }))
      )
    } finally {
      root.remove()
    }
  })
})
