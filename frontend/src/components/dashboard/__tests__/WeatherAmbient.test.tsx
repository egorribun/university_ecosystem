import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { WeatherAmbient } from "@/components/dashboard/WeatherAmbient"

describe("WeatherAmbient", () => {
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
    expect(particles[0]).toHaveClass("bg-sky-300/40")
    expect(particles[0]).toHaveStyle({ animationName: "weather-rain-fall", width: "1px" })
  })

  it("renders deterministic snow particles with snow styling", () => {
    const { container } = render(<WeatherAmbient animation="snow" />)
    const particles = Array.from(container.querySelectorAll("span"))

    expect(particles).toHaveLength(14)
    expect(particles[0]).toHaveClass("bg-white")
    expect(particles[0]).toHaveStyle({
      animationName: "weather-snow-fall",
      animationTimingFunction: "ease-in-out",
      width: "2px",
      height: "2px",
    })
  })

  it("falls back to no particles for an unknown animation variant", () => {
    const { container } = render(<WeatherAmbient animation={"unknown" as never} />)
    expect(container.firstChild).toBeNull()
  })
})
