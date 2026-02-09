import { Badge, Skeleton, Tooltip } from "@/components/ui"
import { useWeather } from "@/hooks/useWeather"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"
import { useLocaleFormatters } from "@/i18n/formatters"

type WeatherWidgetProps = {
  className?: string
}

const TEMPERATURE_PRECISION = 0

const isFiniteNumber = (value: number | null | undefined): value is number =>
  typeof value === "number" && Number.isFinite(value)

export default function WeatherWidget({ className }: WeatherWidgetProps) {
  const { data, isLoading } = useWeather()
  const { t } = useTranslation(["dashboard", "common"])
  const { formatNumber } = useLocaleFormatters()

  const wrapperClassName = cn("inline-flex", className)

  if (isLoading) {
    return (
      <span className={wrapperClassName}>
        <Skeleton
          width={88}
          height={30}
          rounded="999px"
          ariaLabel={t("common:loading")}
          className="chip-weather__skeleton"
        />
      </span>
    )
  }

  if (!data || !isFiniteNumber(data.temperatureC)) {
    return null
  }

  const conditionText = t(data.translationKey, {
    defaultValue: data.conditionLabel,
  })

  const labelText = t("dashboard:weather.label", {
    defaultValue: "Weather",
  })

  const roundedTemperature = Math.round(data.temperatureC)
  const signedTemperature = formatNumber(roundedTemperature, {
    maximumFractionDigits: TEMPERATURE_PRECISION,
    signDisplay: "always",
  })
  const displayTemperature = `${signedTemperature}°`

  const tooltipContent = t("dashboard:weather.tooltip", {
    label: labelText,
    condition: conditionText,
    temperature: displayTemperature,
    defaultValue: `${conditionText} · ${displayTemperature}`,
  })

  const ariaLabel = t("dashboard:weather.aria.status", {
    label: labelText,
    condition: conditionText,
    temperature: signedTemperature,
    defaultValue: `${conditionText}. Temperature ${signedTemperature}°C.`,
  })

  return (
    <span className={wrapperClassName}>
      <Tooltip content={tooltipContent}>
        <Badge
          size="sm"
          className="chip-weather focus-visible:outline-none focus-visible:shadow-[var(--ue-focus-ring)]"
          aria-live="polite"
          aria-label={ariaLabel}
          role="status"
          tabIndex={0}
          data-animation={data.animation}
        >
          <span aria-hidden className="chip-weather__icon">
            {data.icon}
          </span>
          <span className="chip-weather__temp" aria-hidden>
            {displayTemperature}
          </span>
        </Badge>
      </Tooltip>
    </span>
  )
}




