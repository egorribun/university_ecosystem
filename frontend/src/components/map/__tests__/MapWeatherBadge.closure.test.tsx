import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

const weatherState = vi.hoisted(() => ({
  value: null as null | { condition: string; isDay: boolean; temperature: number },
  loading: false,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { condition?: string; temp?: number }) =>
      options ? `${key}:${options.condition ?? options.temp ?? ""}` : key,
  }),
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
})
