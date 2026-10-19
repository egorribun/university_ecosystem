import { Badge } from "@/components/ui/Badge"
import { TrendingUp as TrendingUpIcon, TrendingDown as TrendingDownIcon } from "lucide-react"
import { useTranslation } from "react-i18next"

type TrendUnit = "percent" | "percentagePoints" | "points" | "events"

export default function TrendChip({
  value,
  unit = "percent",
}: {
  value?: number
  unit?: TrendUnit
}) {
  const { t, i18n } = useTranslation(["activity"])
  if (typeof value !== "number" || !Number.isFinite(value)) return null

  const digits = unit === "events" ? 0 : 1
  // Normalize rounded negative zero so the sign, icon, and displayed amount agree.
  const rounded = Number(value.toFixed(digits)) || 0
  const amount =
    unit === "percent"
      ? rounded.toFixed(digits)
      : new Intl.NumberFormat(i18n.resolvedLanguage || i18n.language || "en", {
          minimumFractionDigits: digits,
          maximumFractionDigits: digits,
        }).format(rounded)
  const suffix =
    unit === "percent"
      ? "%"
      : unit === "percentagePoints"
        ? ` ${t("activity:trendUnits.percentagePoints")}`
        : unit === "points"
          ? ` ${t("activity:trendUnits.points", { count: Math.abs(rounded) })}`
          : ` ${t("activity:trendUnits.events", { count: Math.abs(rounded) })}`

  return (
    <Badge
      size="xs"
      variant="outline"
      tone={rounded >= 0 ? "success" : "danger"}
      leadingIcon={
        rounded >= 0 ? (
          <TrendingUpIcon className="activity-trend-icon" />
        ) : (
          <TrendingDownIcon className="activity-trend-icon" />
        )
      }
      className="font-extrabold"
    >
      {`${rounded > 0 ? "+" : ""}${amount}${suffix}`}
    </Badge>
  )
}
