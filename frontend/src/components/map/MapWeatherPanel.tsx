/**
 * MapWeatherPanel.tsx — Expanded weather information panel.
 * Shows feels-like temp, wind, humidity, UV + 12h hourly forecast.
 * Opened by clicking MapWeatherBadge. Wave 108.
 */

import { useEffect, useRef } from "react"
import { AnimatePresence, m } from "framer-motion"
import { useTranslation } from "react-i18next"
import useMediaQuery from "@/hooks/useMediaQuery"
import {
  Thermometer,
  Wind,
  Droplets,
  Sun,
  X,
  Cloud,
  CloudRain,
  Snowflake,
  CloudFog,
  CloudLightning,
  Moon,
  type LucideIcon,
} from "lucide-react"
import type { MapWeatherData, HourlyPoint } from "@/hooks/useMapWeather"
import { WEATHER_CONDITION_CLEAR, type WeatherCondition } from "@/utils/weatherCodes"

/**
 * Resolve a weather condition to an icon at runtime.  Keeping the mapping in
 * an exhaustive switch makes the fallback behaviour explicit for data coming
 * from older API versions (or a future condition), and gives callers a small,
 * deterministic contract they can verify independently of the panel DOM.
 */
export function getConditionIcon(condition: WeatherCondition): LucideIcon {
  switch (condition) {
    case WEATHER_CONDITION_CLEAR:
      return Sun
    case "cloudy":
      return Cloud
    case "rain":
      return CloudRain
    case "snow":
      return Snowflake
    case "fog":
      return CloudFog
    case "storm":
      return CloudLightning
    default:
      return Sun
  }
}

interface MapWeatherPanelProps {
  data: MapWeatherData
  open: boolean
  onClose: () => void
}

export function MapWeatherPanel({ data, open, onClose }: MapWeatherPanelProps) {
  const { t } = useTranslation("map")
  // Wave 189 SW3 — migrated from framer-motion's `useReducedMotion()` (jsdom-
  // incompat per W184 SW6 Gotcha) to project's `useMediaQuery` DEFAULT export.
  // Behaviour preserved: hook returns boolean (was `boolean | null`).
  const prefersReduced = useMediaQuery("(prefers-reduced-motion: reduce)")
  const panelRef = useRef<HTMLDivElement>(null)

  /* ── Close on click outside ── */
  useEffect(() => {
    if (!open) return
    const handle = (e: PointerEvent) => {
      const target = e.target as Node | null
      if (target && panelRef.current && !panelRef.current.contains(target)) {
        onClose()
      }
    }
    // Delay to avoid the badge click also triggering close
    const id = setTimeout(() => document.addEventListener("pointerdown", handle), 0)
    return () => {
      clearTimeout(id)
      document.removeEventListener("pointerdown", handle)
    }
  }, [open, onClose])

  /* ── Close on Escape ── */
  useEffect(() => {
    if (!open) return
    const handle = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", handle)
    return () => window.removeEventListener("keydown", handle)
  }, [open, onClose])

  const motionProps = prefersReduced
    ? {}
    : {
        initial: { opacity: 0, y: -8, scale: 0.96 },
        animate: { opacity: 1, y: 0, scale: 1 },
        exit: { opacity: 0, y: -8, scale: 0.96 },
        transition: { duration: 0.2 },
      }

  return (
    <AnimatePresence>
      {open && (
        <m.div
          ref={panelRef}
          className="map-weather-panel"
          role="dialog"
          aria-label={t("weather.hourlyForecast")}
          {...motionProps}
        >
          {/* Close button */}
          <button
            type="button"
            onClick={onClose}
            className="absolute top-2 right-2 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg hover:bg-[var(--bg-surface-hover)] transition-colors"
            aria-label={t("common:buttons.close")}
          >
            <X className="h-4 w-4" />
          </button>

          {/* Current details grid */}
          <div className="grid grid-cols-2 gap-3 mb-4">
            <StatCard
              icon={Thermometer}
              label={t("weather.feelsLike")}
              value={`${data.feelsLike > 0 ? "+" : ""}${data.feelsLike}°`}
            />
            <StatCard
              icon={Wind}
              label={t("weather.wind")}
              value={`${data.windSpeed} ${t("weather.speedUnit")}`}
            />
            <StatCard icon={Droplets} label={t("weather.humidity")} value={`${data.humidity}%`} />
            <StatCard icon={Sun} label={t("weather.uvIndex")} value={`${data.uvIndex}`} />
          </div>

          {/* Hourly forecast */}
          {data.hourlyForecast.length > 0 && (
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)] mb-2">
                {t("weather.hourlyForecast")}
              </p>
              <div className="map-weather-panel-hourly">
                {data.hourlyForecast.map((point) => (
                  <HourlyColumn key={point.hour} point={point} isDay={data.isDay} />
                ))}
              </div>
            </div>
          )}
        </m.div>
      )}
    </AnimatePresence>
  )
}

/* ── Stat card ── */
function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon
  label: string
  value: string
}) {
  return (
    <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-[var(--bg-surface-hover)]">
      <Icon className="h-3.5 w-3.5 text-[var(--map-accent-icon)] shrink-0" />
      <div className="min-w-0">
        <p className="text-[9px] text-[var(--text-tertiary)] truncate">{label}</p>
        <p className="text-xs font-bold text-text-primary">{value}</p>
      </div>
    </div>
  )
}

/* ── Hourly column ── */
function HourlyColumn({ point, isDay }: { point: HourlyPoint; isDay: boolean }) {
  const Icon =
    point.condition === WEATHER_CONDITION_CLEAR && !isDay ? Moon : getConditionIcon(point.condition)
  return (
    <div className="map-weather-panel-hour">
      <span className="text-[9px] text-[var(--text-tertiary)]">
        {String(point.hour).padStart(2, "0")}
      </span>
      <Icon className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
      <span className="text-[10px] font-bold text-text-primary">
        {point.temperature > 0 ? "+" : ""}
        {point.temperature}°
      </span>
    </div>
  )
}
