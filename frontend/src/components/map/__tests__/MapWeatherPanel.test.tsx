import { render, screen } from "@testing-library/react"
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
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => true }))

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
})
