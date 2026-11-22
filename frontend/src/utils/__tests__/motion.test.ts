import { describe, expect, it, vi } from "vitest"
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
    { property: "transitionDuration", duration: "0s, 0.25s", computed: "0s, 0.25s" },
    { property: "transitionDuration", duration: "0ms, 250ms", computed: "0s, 0.25s" },
    { property: "animationDuration", duration: "0s, 0.25s", computed: "0s, 0.25s" },
    { property: "animationDuration", duration: "0ms, 250ms", computed: "0s, 0.25s" },
  ] as const)(
    "detects the second component of $property=$duration",
    ({ property, duration, computed }) => {
      const root = document.createElement("div")
      root.id = "motion-list"
      root.style.transitionDuration = "0s"
      root.style.animationDuration = "0s"
      root.style[property] = duration
      document.body.append(root)

      try {
        const styles = getComputedStyle(root)
        // Computed durations serialize in seconds, as browsers report them.
        expect(styles[property]).toBe(computed)
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
    }
  )

  it("does not apply the final component's unit to the first duration", () => {
    const root = document.createElement("div")
    root.style.transitionDuration = "1ms, 0s"
    root.style.animationDuration = "0s"
    document.body.append(root)

    try {
      expect(getComputedStyle(root).transitionDuration).toBe("0.001s, 0s")
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
    { duration: "1ms", computed: "0.001s", expectedCount: 0 },
    { duration: "0.001s", computed: "0.001s", expectedCount: 0 },
    { duration: "2ms", computed: "0.002s", expectedCount: 1 },
    { duration: "0.002s", computed: "0.002s", expectedCount: 1 },
  ])(
    "preserves the one-millisecond boundary for $duration",
    ({ duration, computed, expectedCount }) => {
      const root = document.createElement("div")
      root.id = "motion-boundary"
      root.style.transitionDuration = duration
      root.style.animationDuration = duration
      document.body.append(root)

      try {
        const styles = getComputedStyle(root)
        expect(styles.transitionDuration).toBe(computed)
        expect(styles.animationDuration).toBe(computed)
        const violations = collectMotionDurationViolations(root)
        expect(violations).toHaveLength(expectedCount)
        if (expectedCount === 1) {
          expect(violations).toEqual([
            {
              selector: "div#motion-boundary",
              transitionDuration: computed,
              animationDuration: computed,
            },
          ])
        }
      } finally {
        root.remove()
      }
    }
  )

  it("reads each component of a millisecond serialization in its own unit", () => {
    // Browsers and jsdom serialize computed durations in seconds; the collector
    // still accepts engines that keep milliseconds.
    const root = document.createElement("div")
    root.id = "motion-ms"
    document.body.append(root)
    const computed = vi.spyOn(globalThis, "getComputedStyle").mockReturnValue({
      transitionDuration: "1ms, 0s",
      animationDuration: "0ms, 250ms",
    } as CSSStyleDeclaration)

    try {
      expect(collectMotionDurationViolations(root)).toEqual([
        {
          selector: "div#motion-ms",
          transitionDuration: "1ms, 0s",
          animationDuration: "0ms, 250ms",
        },
      ])
      computed.mockReturnValue({
        transitionDuration: "1ms, 0s",
        animationDuration: "2ms",
      } as CSSStyleDeclaration)
      expect(collectMotionDurationViolations(root)).toHaveLength(1)
      computed.mockReturnValue({
        transitionDuration: "1ms, 0s",
        animationDuration: "0s",
      } as CSSStyleDeclaration)
      expect(collectMotionDurationViolations(root)).toEqual([])
    } finally {
      computed.mockRestore()
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
      expect(getComputedStyle(root).transitionDuration).toBe("0.002s")
      expect(getComputedStyle(child).transitionDuration).toBe("0.003s")
      expect(getComputedStyle(svg).transitionDuration).toBe("0.004s")
      expect(getComputedStyle(circle).transitionDuration).toBe("0.006s")
      expect(getComputedStyle(hidden).transitionDuration).toBe("0.005s")
      expect(getComputedStyle(hidden).display).toBe("none")
      expect(collectMotionDurationViolations(root)).toEqual([
        {
          selector: "section#motion-root.first.second.third",
          transitionDuration: "0.002s",
          animationDuration: "0s",
        },
        {
          selector: "div#motion-child",
          transitionDuration: "0.003s",
          animationDuration: "0s",
        },
        {
          selector: "circle#motion-circle",
          transitionDuration: "0.006s",
          animationDuration: "0s",
        },
        {
          selector: "div#motion-hidden",
          transitionDuration: "0.005s",
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
        expect(getComputedStyle(child).transitionDuration).toBe("0.002s")
        expect(getComputedStyle(child).animationDuration).toBe("0s")
      }
      expect(collectMotionDurationViolations(root)).toEqual(
        children.slice(0, 10).map((child) => ({
          selector: `div#${child.id}`,
          transitionDuration: "0.002s",
          animationDuration: "0s",
        }))
      )
    } finally {
      root.remove()
    }
  })
})
