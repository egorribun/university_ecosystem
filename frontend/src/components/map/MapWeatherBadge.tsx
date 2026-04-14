/**
 * MapWeatherBadge.tsx — Compact weather indicator with expandable panel.
 * Click to expand → MapWeatherPanel with detailed forecast.
 * Wave 106; Wave 108 — click-to-expand panel.
 */

import { useState } from "react"
import { useTranslation } from "react-i18next"
import {
  Sun, Moon, Cloud, CloudRain, Snowflake, CloudFog, CloudLightning,
  type LucideIcon,
} from "lucide-react"
import { useMapWeather } from "@/hooks/useMapWeather"
import { MapWeatherPanel } from "./MapWeatherPanel"

const CONDITION_ICONS: Record<string, { day: LucideIcon; night: LucideIcon }> = {
  clear: { day: Sun, night: Moon },
  cloudy: { day: Cloud, night: Cloud },
  rain: { day: CloudRain, night: CloudRain },
  snow: { day: Snowflake, night: Snowflake },
  fog: { day: CloudFog, night: CloudFog },
  storm: { day: CloudLightning, night: CloudLightning },
}

export function MapWeatherBadge() {
  const { t } = useTranslation("map")
  const { data, isLoading } = useMapWeather()
  const [isExpanded, setIsExpanded] = useState(false)

  if (isLoading || !data) return null

  const icons = CONDITION_ICONS[data.condition] ?? CONDITION_ICONS.clear
  const Icon = data.isDay ? icons.day : icons.night
  const conditionText = t(`weather.${data.condition}`)

  return (
    <div className="relative mb-4">
      <button
        type="button"
        role="status"
        aria-live="polite"
        aria-expanded={isExpanded}
        aria-label={t("weather.ariaLabel", { condition: conditionText, temp: data.temperature })}
        className="map-weather-badge cursor-pointer"
        onClick={() => setIsExpanded((prev) => !prev)}
      >
        <Icon size={14} strokeWidth={2.5} />
        <span className="font-bold">{data.temperature > 0 ? "+" : ""}{data.temperature}°</span>
        <span className="hidden sm:inline text-[var(--text-tertiary)]">{conditionText}</span>
      </button>

      <MapWeatherPanel
        data={data}
        open={isExpanded}
        onClose={() => setIsExpanded(false)}
      />
    </div>
  )
}
