import { useTranslation } from "react-i18next"
import { TrendingUp, TrendingDown, Minus } from "lucide-react"
import { cn } from "@/utils/cn"

type ActivityComparativeCardProps = {
  label: string
  current: number
  previous: number
  delta: number
  format?: "percent" | "decimal" | "count"
  colorVar: string
}

function formatValue(value: number, format: "percent" | "decimal" | "count"): string {
  const safe = Number.isFinite(value) ? value : 0 // NaN guard (L4)
  if (format === "percent") return `${Math.round(safe)}%`
  if (format === "decimal") return safe.toFixed(1)
  return String(Math.round(safe))
}

export function ActivityComparativeCard({
  label,
  current,
  previous,
  delta,
  format = "count",
  colorVar,
}: ActivityComparativeCardProps) {
  const { t } = useTranslation(["activity"])

  const isPositive = delta > 0
  const isNegative = delta < 0
  const isNeutral = delta === 0

  return (
    <div className="activity-comparative-card min-w-0">
      <p className="text-micro mb-1 truncate font-semibold uppercase tracking-wider text-text-tertiary">
        {label}
      </p>
      <div className="flex flex-wrap items-end gap-x-2">
        <span
          className="text-2xl font-black tracking-tighter tabular-nums lining-nums"
          style={{ color: colorVar }}
        >
          {formatValue(current, format)}
        </span>
        <span className="mb-0.5 text-xs text-text-tertiary">
          {t("activity:comparative.vsPrevious", { value: formatValue(previous, format) })}
        </span>
      </div>
      <div className="mt-1.5 flex items-center gap-1">
        {isPositive && (
          <TrendingUp
            size={14}
            className="text-[var(--activity-positive-accent)]"
            aria-hidden="true"
          />
        )}
        {isNegative && (
          <TrendingDown
            size={14}
            className="text-[var(--activity-negative-accent)]"
            aria-hidden="true"
          />
        )}
        {isNeutral && <Minus size={14} className="text-text-tertiary" aria-hidden="true" />}
        <span
          className={cn(
            "text-xs font-bold",
            isPositive && "text-[var(--activity-positive-accent)]",
            isNegative && "text-[var(--activity-negative-accent)]",
            isNeutral && "text-text-tertiary"
          )}
        >
          {isNeutral
            ? t("activity:comparative.unchanged")
            : `${isPositive ? "+" : ""}${delta.toFixed(1)}%`}
        </span>
      </div>
    </div>
  )
}
