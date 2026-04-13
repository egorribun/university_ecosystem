import { useTranslation } from "react-i18next"
import {
  Sun, Moon, Cloud, CloudRain, Snowflake, CloudFog, CloudLightning,
  type LucideIcon,
} from "lucide-react"
import { useMapWeather } from "@/hooks/useMapWeather"

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

  if (isLoading || !data) return null

  const icons = CONDITION_ICONS[data.condition] ?? CONDITION_ICONS.clear
  const Icon = data.isDay ? icons.day : icons.night
  const conditionText = t(`weather.${data.condition}`)

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={t("weather.ariaLabel", { condition: conditionText, temp: data.temperature })}
      className="map-weather-badge"
    >
      <Icon size={14} strokeWidth={2.5} />
      <span className="font-bold">{data.temperature > 0 ? "+" : ""}{data.temperature}°</span>
      <span className="hidden sm:inline text-[var(--text-tertiary)]">{conditionText}</span>
    </div>
  )
}
