import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

const weatherState = vi.hoisted(() => ({
  value: null as null | { condition: string; isDay: boolean; temperature: number },
  loading: false,
}))
const useTranslationMock = vi.hoisted(() => vi.fn())

vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock.mockImplementation(() => ({
    t: (key: string, options?: { condition?: string; temp?: number }) =>
      options ? `${key}:${options.condition ?? ""}:${options.temp ?? ""}` : key,
  })),
}))

vi.mock("@/hooks/useMapWeather", () => ({
  useMapWeather: () => ({ data: weatherState.value, isLoading: weatherState.loading }),
}))

vi.mock("../MapWeatherPanel", () => ({
  MapWeatherPanel: ({ open, onClose }: { open: boolean; onClose: () => void }) => (
    <div data-testid="weather-panel">
      {String(open)}
      <button type="button" onClick={onClose}>
        close weather
      </button>
    </div>
  ),
}))

import { MapWeatherBadge } from "../MapWeatherBadge"

describe("MapWeatherBadge defensive branches", () => {
  afterEach(() => {
    weatherState.value = null
    weatherState.loading = false
  })

  it("uses the clear-night fallback icon and renders negative temperatures", () => {
    weatherState.value = { condition: "unlisted", isDay: false, temperature: -5 }
    render(<MapWeatherBadge />)

    expect(screen.getByRole("button", { name: /weather\.ariaLabel/ })).toHaveAttribute(
      "aria-expanded",
      "false"
    )
    expect(screen.getByText("-5°")).toBeInTheDocument()
    expect(screen.getByTestId("weather-panel")).toHaveTextContent("false")
  })

  it("renders the positive-temperature sign and toggles the detail panel", () => {
    weatherState.value = { condition: "clear", isDay: true, temperature: 5 }
    render(<MapWeatherBadge />)

    expect(screen.getByText("+5°")).toBeInTheDocument()
    const weatherButton = screen.getByRole("button", { name: /weather\.ariaLabel/ })
    fireEvent.click(weatherButton)
    expect(weatherButton).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByTestId("weather-panel")).toHaveTextContent("true")

    fireEvent.click(screen.getByRole("button", { name: "close weather" }))
    expect(screen.getByTestId("weather-panel")).toHaveTextContent("false")
  })

  it("preserves the map namespace, aria interpolation, and condition label", () => {
    weatherState.value = { condition: "rain", isDay: true, temperature: 0 }
    render(<MapWeatherBadge />)

    expect(useTranslationMock).toHaveBeenCalledWith("map")
    const weatherButton = screen.getByRole("button", { name: "weather.ariaLabel:weather.rain:0" })
    expect(weatherButton).toBeInTheDocument()
    expect(screen.getByText("weather.rain")).toBeInTheDocument()
    expect(weatherButton.querySelector("svg")).toHaveClass("lucide-cloud-rain")
  })

  it("selects the day/night icon for every supported condition", () => {
    const { container, rerender } = render(<MapWeatherBadge />)
    const conditions = [
      ["clear", "sun", "moon"],
      ["cloudy", "cloud", "cloud"],
      ["rain", "cloud-rain", "cloud-rain"],
      ["snow", "snowflake", "snowflake"],
      ["fog", "cloud-fog", "cloud-fog"],
      ["storm", "cloud-lightning", "cloud-lightning"],
    ] as const

    for (const [condition, dayIcon, nightIcon] of conditions) {
      weatherState.value = { condition, isDay: true, temperature: 1 }
      rerender(<MapWeatherBadge />)
      expect(container.querySelector("svg")).toHaveClass(`lucide-${dayIcon}`)

      weatherState.value = { condition, isDay: false, temperature: 1 }
      rerender(<MapWeatherBadge />)
      expect(container.querySelector("svg")).toHaveClass(`lucide-${nightIcon}`)
    }
  })

  it("does not add a plus sign at the zero-degree boundary", () => {
    weatherState.value = { condition: "clear", isDay: true, temperature: 0 }
    render(<MapWeatherBadge />)

    expect(screen.getByText("0°")).toBeInTheDocument()
    expect(screen.queryByText("+0°")).not.toBeInTheDocument()
  })
})
