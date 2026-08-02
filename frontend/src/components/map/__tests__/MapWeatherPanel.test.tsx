import { act, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
const hoisted = vi.hoisted(() => ({ reducedMotion: true }))

vi.mock("@/hooks/useMediaQuery", () => ({ default: () => hoisted.reducedMotion }))

import { MapWeatherPanel } from "@/components/map/MapWeatherPanel"
import type { MapWeatherData } from "@/hooks/useMapWeather"

const WEATHER: MapWeatherData = {
  temperature: 5,
  weatherCode: 1,
  isDay: true,
  condition: "clear",
  feelsLike: 3,
  windSpeed: 4,
  humidity: 60,
  uvIndex: 2,
  hourlyForecast: [
    { hour: 9, temperature: 4, condition: "clear" },
    { hour: 10, temperature: 6, condition: "cloudy" },
  ],
}

const baseProps = { data: WEATHER, open: true, onClose: vi.fn() }

describe("MapWeatherPanel", () => {
  it("renders nothing when closed", () => {
    render(<MapWeatherPanel {...baseProps} open={false} />)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("renders the weather dialog with stat cards when open", () => {
    render(<MapWeatherPanel {...baseProps} />)
    expect(screen.getByRole("dialog", { name: "weather.hourlyForecast" })).toBeInTheDocument()
    expect(screen.getByText("weather.feelsLike")).toBeInTheDocument()
    expect(screen.getByText("weather.humidity")).toBeInTheDocument()
    expect(screen.getByText("+3°")).toBeInTheDocument()
    expect(screen.getByText("60%")).toBeInTheDocument()
  })

  it("renders the hourly forecast columns", () => {
    render(<MapWeatherPanel {...baseProps} />)
    expect(screen.getByText("weather.hourlyForecast")).toBeInTheDocument()
    expect(screen.getByText("09")).toBeInTheDocument()
    expect(screen.getByText("10")).toBeInTheDocument()
  })

  it("fires onClose from the close button", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<MapWeatherPanel {...baseProps} onClose={onClose} />)
    await user.click(screen.getByRole("button", { name: "common:buttons.close" }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("closes on outside pointer and Escape, while ignoring inside and unrelated keys", () => {
    vi.useFakeTimers()
    try {
      const onClose = vi.fn()
      render(<MapWeatherPanel {...baseProps} onClose={onClose} />)
      const dialog = screen.getByRole("dialog")

      act(() => {
        vi.runOnlyPendingTimers()
      })

      fireEvent.pointerDown(dialog)
      fireEvent.keyDown(window, { key: "Enter" })
      expect(onClose).not.toHaveBeenCalled()

      fireEvent.pointerDown(document.body)
      fireEvent.keyDown(window, { key: "Escape" })
      expect(onClose).toHaveBeenCalledTimes(2)
    } finally {
      vi.useRealTimers()
    }
  })

  it("renders motion, negative values, night clear, unknown conditions, and an empty forecast", () => {
    hoisted.reducedMotion = false
    const data: MapWeatherData = {
      ...WEATHER,
      feelsLike: -3,
      isDay: false,
      hourlyForecast: [
        { hour: 0, temperature: -2, condition: "clear" },
        { hour: 1, temperature: -1, condition: "unknown" as never },
      ],
    }

    const { rerender } = render(<MapWeatherPanel {...baseProps} data={data} />)
    expect(screen.getByText("-3°")).toBeInTheDocument()
    expect(screen.getByText("-2°")).toBeInTheDocument()
    expect(screen.getByText("00")).toBeInTheDocument()

    rerender(<MapWeatherPanel {...baseProps} data={{ ...data, hourlyForecast: [] }} />)
    expect(screen.queryByText("weather.hourlyForecast")).not.toBeInTheDocument()
  })
})
