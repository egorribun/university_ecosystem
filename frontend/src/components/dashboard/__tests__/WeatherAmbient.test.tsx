import { render } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { WeatherAmbient } from "@/components/dashboard/WeatherAmbient"

describe("WeatherAmbient", () => {
  it("does not allocate a zero-length particle array when disabled", () => {
    const originalArrayFrom = Array.from
    const arrayFromSpy = vi.spyOn(Array, "from").mockImplementation(((items, mapFn) => {
      if (typeof items === "object" && items !== null && "length" in items && items.length === 0) {
        throw new Error("zero-length particle allocation")
      }
      return originalArrayFrom(items, mapFn)
    }) as typeof Array.from)

    try {
      expect(() => render(<WeatherAmbient animation="drizzle" disabled />)).not.toThrow()
      expect(() => render(<WeatherAmbient animation="none" />)).not.toThrow()
    } finally {
      arrayFromSpy.mockRestore()
    }
  })

  it("renders no particles for disabled and zero-particle variants", () => {
    expect(render(<WeatherAmbient animation="drizzle" disabled />).container.firstChild).toBeNull()
    expect(render(<WeatherAmbient animation="none" />).container.firstChild).toBeNull()
    expect(render(<WeatherAmbient animation="glow" />).container.firstChild).toBeNull()
    expect(render(<WeatherAmbient animation="breeze" />).container.firstChild).toBeNull()
  })

  it.each([
    ["drizzle", 18],
    ["storm", 22],
  ] as const)("renders %s rain particles", (animation, count) => {
    const { container } = render(<WeatherAmbient animation={animation} />)
    const particles = Array.from(container.querySelectorAll("span"))

    expect(particles).toHaveLength(count)
    expect(container.firstElementChild).toHaveClass("weather-ambient")
    expect(particles[0]).toHaveClass("absolute", "rounded-full", "bg-sky-300/40")
    expect(particles[0]).not.toHaveClass("bg-white")
    expect(particles[0]).toHaveStyle({
      animationName: "weather-rain-fall",
      animationTimingFunction: "linear",
      animationDuration: "0.8s",
      animationDelay: "0s",
      width: "1px",
      height: "8px",
      left: "0%",
      top: "-5%",
    })
  })

  it("renders deterministic snow particles with snow styling", () => {
    const { container } = render(<WeatherAmbient animation="snow" />)
    const particles = Array.from(container.querySelectorAll("span"))

    expect(particles).toHaveLength(14)
    expect(particles[0]).toHaveClass("absolute", "rounded-full", "bg-white")
    expect(particles[0]).not.toHaveClass("bg-sky-300/40")
    expect(particles[0]).toHaveStyle({
      animationName: "weather-snow-fall",
      animationTimingFunction: "ease-in-out",
      animationDuration: "3s",
      animationDelay: "0s",
      left: "0%",
      top: "-5%",
      width: "2px",
      height: "2px",
    })
  })

  it("keeps particle positions, timings, opacity, and sizes deterministic", () => {
    const { container } = render(<WeatherAmbient animation="snow" />)
    const particles = Array.from(container.querySelectorAll("span"))
    const expectedSnow = [
      ["0%", "0s", "3s", "0.15", "2px"],
      ["61.8%", "0.37s", "3.8s", "0.25", "3px"],
      ["23.6%", "0.74s", "4.6s", "0.35", "4px"],
      ["85.4%", "1.11s", "5.4s", "0.15", "2px"],
      ["47.2%", "1.48s", "3s", "0.25", "3px"],
    ] as const

    expectedSnow.forEach(([left, delay, duration, opacity, size], index) => {
      expect(particles[index]?.style.left).toBe(left)
      expect(particles[index]?.style.animationDelay).toBe(delay)
      expect(particles[index]?.style.animationDuration).toBe(duration)
      expect(particles[index]?.style.getPropertyValue("--_particle-opacity")).toBe(opacity)
      expect(particles[index]?.style.width).toBe(size)
      expect(particles[index]?.style.height).toBe(size)
    })

    const { container: rainContainer } = render(<WeatherAmbient animation="drizzle" />)
    const rainParticles = Array.from(rainContainer.querySelectorAll("span"))
    const expectedRain = [
      ["61.8%", "0.37s", "0.9500000000000001s", "0.25", "12px"],
      ["47.2%", "1.48s", "1.4s", "0.25", "8px"],
      ["9%", "1.85s", "0.8s", "0.35", "12px"],
    ] as const

    ;[1, 4, 5].forEach((index, expectedIndex) => {
      const [left, delay, duration, opacity, height] = expectedRain[expectedIndex]!
      expect(rainParticles[index]?.style.left).toBe(left)
      expect(rainParticles[index]?.style.animationDelay).toBe(delay)
      expect(rainParticles[index]?.style.animationDuration).toBe(duration)
      expect(rainParticles[index]?.style.height).toBe(height)
      expect(rainParticles[index]?.style.getPropertyValue("--_particle-opacity")).toBe(opacity)
      expect(rainParticles[index]?.style.width).toBe("1px")
    })
  })

  it("recomputes particles when animation changes", () => {
    const { container, rerender } = render(<WeatherAmbient animation="drizzle" />)
    expect(container.querySelectorAll("span")).toHaveLength(18)

    rerender(<WeatherAmbient animation="snow" />)
    expect(container.querySelectorAll("span")).toHaveLength(14)
    expect(container.querySelector("span")).toHaveClass("bg-white")
    expect(container.querySelector("span")).toHaveStyle({ animationName: "weather-snow-fall" })

    rerender(<WeatherAmbient animation="none" />)
    expect(container.firstChild).toBeNull()
  })

  it("falls back to no particles for an unknown animation variant", () => {
    const { container } = render(<WeatherAmbient animation={"unknown" as never} />)
    expect(container.firstChild).toBeNull()
  })
})
