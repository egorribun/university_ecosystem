import { render, screen } from "@testing-library/react"
import { createInstance } from "i18next"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it, vi } from "vitest"

import enMap from "@/i18n/locales/en/map.json"
import ruMap from "@/i18n/locales/ru/map.json"

const weather = vi.hoisted(() => ({ temperature: 0 }))
vi.mock("@/hooks/useMapWeather", () => ({
  useMapWeather: () => ({
    data: { condition: "clear", isDay: true, temperature: weather.temperature },
    isLoading: false,
  }),
}))
vi.mock("../MapWeatherPanel", () => ({ MapWeatherPanel: () => null }))

import { MapWeatherBadge } from "../MapWeatherBadge"

describe("MapWeatherBadge visible label", () => {
  it.each([
    ["en", 5, "+5°", "Clear"],
    ["en", 0, "0°", "Clear"],
    ["en", -5, "-5°", "Clear"],
    ["en", 2.5, "+2.5°", "Clear"],
    ["ru", 5, "+5°", "Ясно"],
    ["ru", 0, "0°", "Ясно"],
    ["ru", -5, "-5°", "Ясно"],
    ["ru", 2.5, "+2.5°", "Ясно"],
  ])(
    "includes the visible %s temperature %s and condition in its accessible name",
    async (language, temperature, temperatureText, conditionText) => {
      weather.temperature = temperature
      const i18n = createInstance()
      await i18n.init({
        lng: language,
        defaultNS: "map",
        resources: { [language]: { map: language === "ru" ? ruMap : enMap } },
        interpolation: { escapeValue: false },
      })
      render(
        <I18nextProvider i18n={i18n}>
          <MapWeatherBadge />
        </I18nextProvider>
      )
      const button = screen.getByRole("button", { expanded: false })
      expect(screen.getByText(temperatureText)).toBeInTheDocument()
      expect(screen.getByText(conditionText)).toBeInTheDocument()
      expect(button.getAttribute("aria-label")).toContain(`${temperatureText} ${conditionText}`)
    }
  )
})
