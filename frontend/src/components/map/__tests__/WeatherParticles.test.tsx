import { render } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const hoisted = vi.hoisted(() => ({ reducedMotion: false }))

vi.mock("@/hooks/useMediaQuery", () => ({ default: () => hoisted.reducedMotion }))

import { WeatherParticles } from "@/components/map/WeatherParticles"

const DRAWING_CONDITIONS = ["rain", "snow", "storm", "fog"] as const

describe("WeatherParticles", () => {
  beforeEach(() => {
    hoisted.reducedMotion = false
    let n = 0
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      if (n++ < 2) {
        cb(16)
      }
      return 1
    })
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("renders null for the clear condition", () => {
    const { container } = render(<WeatherParticles condition="clear" isDark={false} />)
    expect(container.querySelector("canvas")).toBeNull()
  })

  it("renders null for the cloudy condition", () => {
    const { container } = render(<WeatherParticles condition="cloudy" isDark={false} />)
    expect(container.querySelector("canvas")).toBeNull()
  })

  it("renders null when prefers-reduced-motion is enabled", () => {
    hoisted.reducedMotion = true
    const { container } = render(<WeatherParticles condition="rain" isDark={false} />)
    expect(container.querySelector("canvas")).toBeNull()
  })

  it.each(DRAWING_CONDITIONS)("draws a canvas for the %s condition (light)", (condition) => {
    const { container } = render(<WeatherParticles condition={condition} isDark={false} />)
    expect(container.querySelector("canvas")).not.toBeNull()
    const wrapper = container.querySelector("[aria-hidden='true']")
    expect(wrapper).not.toBeNull()
  })

  it.each(DRAWING_CONDITIONS)("draws a canvas for the %s condition (dark)", (condition) => {
    const { container } = render(<WeatherParticles condition={condition} isDark={true} />)
    expect(container.querySelector("canvas")).not.toBeNull()
  })

  it("exercises the particle-recycle branches when particles fall out of bounds", () => {
    // Force particles to spawn near the bottom edge so the y-update pushes them
    // out of bounds, hitting recycleParticle (rain/snow/storm) and the fog
    // horizontal-recycle branch on the second animation frame.
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(0.999)
    try {
      for (const condition of DRAWING_CONDITIONS) {
        const { container } = render(<WeatherParticles condition={condition} isDark={false} />)
        expect(container.querySelector("canvas")).not.toBeNull()
      }
    } finally {
      randomSpy.mockRestore()
    }
  })

  it("walks the storm flash scheduling branch", () => {
    // Low Math.random pushes the flash schedule toward its minimum window; this
    // still walks the storm flash scheduling + fade arithmetic.
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(0.001)
    try {
      const { container } = render(<WeatherParticles condition="storm" isDark={true} />)
      expect(container.querySelector("canvas")).not.toBeNull()
    } finally {
      randomSpy.mockRestore()
    }
  })

  it("cleans up on unmount without throwing", () => {
    const { container, unmount } = render(<WeatherParticles condition="rain" isDark={false} />)
    expect(container.querySelector("canvas")).not.toBeNull()
    expect(() => unmount()).not.toThrow()
  })

  it("re-runs the effect when the condition prop changes", () => {
    const { container, rerender } = render(<WeatherParticles condition="rain" isDark={false} />)
    expect(container.querySelector("canvas")).not.toBeNull()
    rerender(<WeatherParticles condition="snow" isDark={false} />)
    expect(container.querySelector("canvas")).not.toBeNull()
    rerender(<WeatherParticles condition="clear" isDark={false} />)
    expect(container.querySelector("canvas")).toBeNull()
  })
})
