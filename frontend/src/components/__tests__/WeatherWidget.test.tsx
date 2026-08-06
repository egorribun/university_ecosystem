import { describe, it, expect, beforeEach, vi } from "vitest"
import { render, screen } from "@testing-library/react"

import WeatherWidget from "../ui/WeatherWidget"
import type { WeatherAnimationVariant } from "@/utils/weatherIcons"

const translations: Record<string, string> = {
  "common:loading": "Loading",
  "dashboard:weather.label": "Weather",
  "dashboard:weather.tooltip": "{{label}} · {{condition}} · {{temperature}}",
  "dashboard:weather.conditions.clear": "Clear sky",
  "dashboard:weather.conditions.unknown": "Weather unavailable",
  "dashboard:weather.aria.status": "{{label}}. {{condition}}. Temperature {{temperature}}°C.",
  "dashboard:weather.aria.statusNoTemp": "{{label}}. {{condition}}. Temperature unavailable.",
}

let mockLanguage: "en" | "ru" = "en"

type WeatherSnapshotMock = {
  conditionCode: number
  conditionLabel: string
  temperatureC: number
  observedAt: string
  icon: string
  translationKeySuffix: string
  translationKey: string
  animation: WeatherAnimationVariant
}

const weatherStore = vi.hoisted(() => {
  function baseSnapshot(): WeatherSnapshotMock {
    return {
      conditionCode: 0,
      conditionLabel: "Clear sky",
      temperatureC: 21,
      observedAt: new Date("2025-09-15T08:45:00Z").toISOString(),
      icon: "☀️",
      translationKeySuffix: "clear",
      translationKey: "dashboard:weather.conditions.clear",
      animation: "glow",
    }
  }

  const createData = (overrides: Partial<WeatherSnapshotMock> = {}) => ({
    ...baseSnapshot(),
    ...overrides,
  })

  type WeatherState = {
    data: WeatherSnapshotMock | null
    isLoading: boolean
    error: Error | null
    refresh: ReturnType<typeof vi.fn>
  }

  let state: WeatherState = {
    data: baseSnapshot(),
    isLoading: false,
    error: null,
    refresh: vi.fn(),
  }

  return {
    createData,
    getState: () => state,
    setState: (next: Partial<WeatherState>) => {
      state = { ...state, ...next }
    },
    reset: () => {
      state = {
        data: baseSnapshot(),
        isLoading: false,
        error: null,
        refresh: vi.fn(),
      }
    },
  }
})

vi.mock("react-i18next", () => ({
  useTranslation: (namespaces: string | string[] = "common") => {
    const defaultNamespace = Array.isArray(namespaces) ? namespaces[0] : namespaces
    return {
      t: (key: string, options: Record<string, unknown> = {}) => {
        const namespacedKey = key.includes(":") ? key : `${defaultNamespace}:${key}`
        const template = translations[namespacedKey] ?? namespacedKey
        return template.replace(/{{\s*(\w+)\s*}}/g, (_, token) => {
          const value = options[token]
          return value === undefined || value === null ? "" : String(value)
        })
      },
      i18n: { language: mockLanguage },
    }
  },
}))

vi.mock("@/contexts/LanguageContext", () => ({
  useLanguage: () => ({ language: mockLanguage }),
  getLocaleForLanguage: (language: string) => (language === "ru" ? "ru-RU" : "en-US"),
}))

vi.mock("@/hooks/useWeather", () => ({
  useWeather: vi.fn(() => weatherStore.getState()),
}))

describe("WeatherWidget", () => {
  beforeEach(() => {
    mockLanguage = "en"
    weatherStore.reset()
  })

  it("renders the current weather with tooltip details", () => {
    render(<WeatherWidget />)

    expect(screen.getByText("☀️")).toBeInTheDocument()
    expect(screen.getByText("+21°")).toBeInTheDocument()

    const badge = screen.getByLabelText("Weather. Clear sky. Temperature +21°C.")
    expect(badge).toHaveAttribute("title", "Weather · Clear sky · +21°")
    expect(badge).toHaveAttribute("data-animation", "glow")
  })

  it("disables icon animation when reduced motion is requested", () => {
    const originalMatchMedia = window.matchMedia
    if (!originalMatchMedia) {
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        writable: true,
        value: vi.fn(() => ({
          matches: false,
          media: "",
          onchange: null,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          addListener: vi.fn(),
          removeListener: vi.fn(),
          dispatchEvent: vi.fn(),
        })),
      })
    }

    const matchMediaSpy = vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) =>
        ({
          matches: query.includes("prefers-reduced-motion"),
          media: query,
          onchange: null,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          addListener: vi.fn(),
          removeListener: vi.fn(),
          dispatchEvent: vi.fn(),
        }) as unknown as MediaQueryList
    )

    weatherStore.setState({ data: weatherStore.createData({ animation: "none" }) })

    try {
      render(<WeatherWidget />)
      const badge = screen.getByLabelText("Weather. Clear sky. Temperature +21°C.")
      expect(badge).toHaveAttribute("data-animation", "none")
    } finally {
      matchMediaSpy.mockRestore()
      if (!originalMatchMedia) {
        delete (window as { matchMedia?: typeof window.matchMedia }).matchMedia
      }
    }
  })

  it("renders nothing when weather data is unavailable", () => {
    weatherStore.setState({ data: null, isLoading: false })

    const { container } = render(<WeatherWidget />)

    expect(container.firstChild).toBeNull()
  })

  it("renders the loading skeleton while weather data is being fetched", () => {
    weatherStore.setState({ isLoading: true })

    render(<WeatherWidget />)

    expect(screen.getByLabelText("Loading")).toBeInTheDocument()
  })

  it("renders nothing when the temperature is not finite", () => {
    weatherStore.setState({ data: weatherStore.createData({ temperatureC: Number.NaN }) })

    const { container } = render(<WeatherWidget />)

    expect(container.firstChild).toBeNull()
  })
})
