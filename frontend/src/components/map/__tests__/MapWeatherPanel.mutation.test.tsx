import { createElement, type ReactNode } from "react"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { MapWeatherData } from "@/hooks/useMapWeather"

const state = vi.hoisted(() => ({
  reducedMotion: true,
  navigate: vi.fn(),
  t: vi.fn((key: string) => key),
  useTranslation: vi.fn(),
  useMediaQuery: vi.fn(),
}))

vi.mock("react-i18next", () => ({
  useTranslation: state.useTranslation,
}))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: state.useMediaQuery,
}))

vi.mock("lucide-react", () => {
  const icon = (name: string) => {
    const Component = ({ className, size }: { className?: string; size?: number }) => (
      <svg data-testid={`weather-icon-${name}`} data-size={size} className={className} />
    )
    Component.displayName = name
    return Component
  }

  return {
    Thermometer: icon("thermometer"),
    Wind: icon("wind"),
    Droplets: icon("droplets"),
    Sun: icon("sun"),
    X: icon("close"),
    Cloud: icon("cloud"),
    CloudRain: icon("cloud-rain"),
    Snowflake: icon("snowflake"),
    CloudFog: icon("cloud-fog"),
    CloudLightning: icon("cloud-lightning"),
    Moon: icon("moon"),
  }
})

vi.mock("framer-motion", () => {
  const MotionDiv = ({
    children,
    initial,
    animate,
    exit,
    transition,
    ...props
  }: {
    children?: ReactNode
    initial?: Record<string, unknown>
    animate?: Record<string, unknown>
    exit?: Record<string, unknown>
    transition?: Record<string, unknown>
    className?: string
    role?: string
    "aria-label"?: string
  }) =>
    createElement(
      "div",
      {
        ...props,
        "data-motion-initial": initial === undefined ? undefined : JSON.stringify(initial),
        "data-motion-animate": animate === undefined ? undefined : JSON.stringify(animate),
        "data-motion-exit": exit === undefined ? undefined : JSON.stringify(exit),
        "data-motion-transition": transition === undefined ? undefined : JSON.stringify(transition),
      },
      children
    )
  MotionDiv.displayName = "MotionDiv"

  return {
    AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
    m: { div: MotionDiv },
  }
})

import { MapWeatherPanel, getConditionIcon } from "@/components/map/MapWeatherPanel"
import { Cloud, CloudFog, CloudLightning, CloudRain, Moon, Snowflake, Sun } from "lucide-react"

const WEATHER: MapWeatherData = {
  temperature: 5,
  weatherCode: 1,
  isDay: true,
  condition: "clear",
  feelsLike: 0,
  windSpeed: 4,
  humidity: 60,
  uvIndex: 2,
  hourlyForecast: [
    { hour: 0, temperature: 0, condition: "clear" },
    { hour: 1, temperature: -1, condition: "cloudy" },
    { hour: 2, temperature: 6, condition: "rain" },
    { hour: 3, temperature: 7, condition: "unknown" as never },
  ],
}

function renderPanel(
  overrides: Partial<{ data: MapWeatherData; open: boolean; onClose: () => void }> = {}
) {
  return render(
    <MapWeatherPanel
      data={overrides.data ?? WEATHER}
      open={overrides.open ?? true}
      onClose={overrides.onClose ?? vi.fn()}
    />
  )
}

function parseMotion(element: HTMLElement) {
  return {
    initial: JSON.parse(element.dataset.motionInitial ?? "null"),
    animate: JSON.parse(element.dataset.motionAnimate ?? "null"),
    exit: JSON.parse(element.dataset.motionExit ?? "null"),
    transition: JSON.parse(element.dataset.motionTransition ?? "null"),
  }
}

describe("MapWeatherPanel mutation contracts", () => {
  beforeEach(() => {
    state.reducedMotion = true
    state.t.mockReset().mockImplementation((key: string) => key)
    state.useTranslation.mockReset().mockReturnValue({ t: state.t })
    state.useMediaQuery.mockReset().mockImplementation(() => state.reducedMotion)
  })

  it("resolves every weather condition to its canonical icon and safely falls back", () => {
    expect(getConditionIcon("clear")).toBe(Sun)
    expect(getConditionIcon("cloudy")).toBe(Cloud)
    expect(getConditionIcon("rain")).toBe(CloudRain)
    expect(getConditionIcon("snow")).toBe(Snowflake)
    expect(getConditionIcon("fog")).toBe(CloudFog)
    expect(getConditionIcon("storm")).toBe(CloudLightning)
    expect(getConditionIcon("unknown" as never)).toBe(Sun)
    expect(Moon).not.toBe(Sun)
  })

  it("keeps translated stats, sign formatting, hourly condition icons, and accessibility", () => {
    renderPanel({ data: { ...WEATHER, isDay: false } })

    expect(state.useTranslation).toHaveBeenCalledWith("map")
    expect(state.useMediaQuery).toHaveBeenCalledWith("(prefers-reduced-motion: reduce)")
    expect(state.t).toHaveBeenCalledWith("weather.hourlyForecast")
    expect(state.t).toHaveBeenCalledWith("common:buttons.close")
    expect(state.t).toHaveBeenCalledWith("weather.feelsLike")
    expect(state.t).toHaveBeenCalledWith("weather.wind")
    expect(state.t).toHaveBeenCalledWith("weather.speedUnit")
    expect(state.t).toHaveBeenCalledWith("weather.humidity")
    expect(state.t).toHaveBeenCalledWith("weather.uvIndex")

    const dialog = screen.getByRole("dialog", { name: "weather.hourlyForecast" })
    expect(dialog).toHaveClass("map-weather-panel")
    expect(screen.getByRole("button", { name: "common:buttons.close" })).toHaveClass(
      "absolute",
      "min-h-[44px]",
      "min-w-[44px]",
      "rounded-lg"
    )
    const feelsLike = screen.getByText("weather.feelsLike").parentElement
    expect(feelsLike).toHaveTextContent("0°")
    expect(feelsLike).not.toHaveTextContent("+0°")
    expect(screen.getByText("4 weather.speedUnit")).toBeInTheDocument()
    expect(screen.getByText("60%")).toBeInTheDocument()
    expect(screen.getByText("2")).toBeInTheDocument()

    const hours = screen.getAllByText(/^(00|01|02|03)$/)
    expect(hours).toHaveLength(4)
    expect(screen.getByTestId("weather-icon-moon")).toBeInTheDocument()
    expect(screen.getByTestId("weather-icon-cloud")).toBeInTheDocument()
    expect(screen.getByTestId("weather-icon-cloud-rain")).toBeInTheDocument()
    expect(screen.getAllByTestId("weather-icon-sun")).toHaveLength(2)
    expect(screen.getAllByText(/^[+-]?\d+°$/).map((node) => node.textContent)).toEqual([
      "0°",
      "0°",
      "-1°",
      "+6°",
      "+7°",
    ])
  })

  it("passes the complete motion object only when reduced motion is disabled", () => {
    state.reducedMotion = false
    renderPanel()

    expect(parseMotion(screen.getByRole("dialog"))).toEqual({
      initial: { opacity: 0, y: -8, scale: 0.96 },
      animate: { opacity: 1, y: 0, scale: 1 },
      exit: { opacity: 0, y: -8, scale: 0.96 },
      transition: { duration: 0.2 },
    })
  })

  it("does not register handlers while closed and cleans both handlers on unmount", () => {
    vi.useFakeTimers()
    const addDocument = vi.spyOn(document, "addEventListener")
    const removeDocument = vi.spyOn(document, "removeEventListener")
    const addWindow = vi.spyOn(window, "addEventListener")
    const removeWindow = vi.spyOn(window, "removeEventListener")
    const clearTimeoutSpy = vi.spyOn(globalThis, "clearTimeout")
    const onClose = vi.fn()

    try {
      const closed = renderPanel({ open: false, onClose })
      act(() => {
        vi.runOnlyPendingTimers()
      })
      fireEvent.pointerDown(document.body)
      fireEvent.keyDown(window, { key: "Escape" })
      expect(onClose).not.toHaveBeenCalled()
      expect(addDocument.mock.calls.some(([type]) => type === "pointerdown")).toBe(false)
      const windowAddCalls = addWindow.mock.calls as unknown as Array<[string, unknown]>
      expect(windowAddCalls.some(([type]) => type === "keydown")).toBe(false)

      closed.rerender(<MapWeatherPanel data={WEATHER} open onClose={onClose} />)
      act(() => {
        vi.runOnlyPendingTimers()
      })
      closed.unmount()

      expect(clearTimeoutSpy).toHaveBeenCalled()
      expect(removeDocument.mock.calls.some(([type]) => type === "pointerdown")).toBe(true)
      const windowRemoveCalls = removeWindow.mock.calls as unknown as Array<[string, unknown]>
      expect(windowRemoveCalls.some(([type]) => type === "keydown")).toBe(true)
    } finally {
      addDocument.mockRestore()
      removeDocument.mockRestore()
      addWindow.mockRestore()
      removeWindow.mockRestore()
      clearTimeoutSpy.mockRestore()
      vi.useRealTimers()
    }
  })

  it("guards null pointer targets and refreshes outside/Escape callbacks when onClose changes", () => {
    vi.useFakeTimers()
    const firstClose = vi.fn()
    const secondClose = vi.fn()
    const addDocument = vi.spyOn(document, "addEventListener")

    try {
      const view = renderPanel({ onClose: firstClose })
      act(() => {
        vi.runOnlyPendingTimers()
      })

      // A null event target must not be treated as an outside click.
      const pointerRegistration = addDocument.mock.calls.find(([type]) => type === "pointerdown")
      expect(pointerRegistration).toBeDefined()
      const pointerHandler = pointerRegistration?.[1]
      expect(typeof pointerHandler).toBe("function")
      if (typeof pointerHandler === "function") {
        pointerHandler({ target: null } as unknown as PointerEvent)
      }
      expect(firstClose).not.toHaveBeenCalled()

      fireEvent.pointerDown(screen.getByRole("dialog"))
      expect(firstClose).not.toHaveBeenCalled()
      fireEvent.pointerDown(document.body)
      expect(firstClose).toHaveBeenCalledOnce()

      view.rerender(<MapWeatherPanel data={WEATHER} open onClose={secondClose} />)
      act(() => {
        vi.runOnlyPendingTimers()
      })
      fireEvent.pointerDown(document.body)
      fireEvent.keyDown(window, { key: "Escape" })
      expect(firstClose).toHaveBeenCalledOnce()
      expect(secondClose).toHaveBeenCalledTimes(2)
    } finally {
      addDocument.mockRestore()
      vi.useRealTimers()
    }
  })
})
