import { useTranslation } from "react-i18next"
import { Tooltip } from "@/components/ui"
import { cn } from "@/utils/cn"
import { pad } from "@/utils/scheduleUtils"

interface DateBulletProps {
  date?: string
  locale: string
  /** Compact mode for event lists (slightly smaller) */
  size?: "default" | "compact"
}

const MONTH_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

export function DateBullet({ date, locale, size = "default" }: DateBulletProps) {
  const { t } = useTranslation("common")
  const d = date ? new Date(date) : null
  const dd = d ? pad(d.getDate()) : "—"
  const mmLabel = d ? MONTH_SHORT[d.getMonth()] ?? pad(d.getMonth() + 1) : "--"
  const fallback = t("dateUnknown")
  const full = d
    ? d.toLocaleString(locale, {
        day: "2-digit",
        month: "long",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : fallback

  const isCompact = size === "compact"
  const outerSize = isCompact ? "h-10 w-10 min-h-10 min-w-10" : "h-12 w-12 min-h-12 min-w-12"

  return (
    <Tooltip content={full}>
      <span
        aria-label={t("ariaDatePublished", { date: full })}
        className={cn(
          "relative flex flex-col items-center justify-center rounded-full",
          outerSize,
          // Premium layered background — radial gradient for depth
          "date-bullet-premium",
          // Transition for hover lift
          "transition-transform duration-base hover:scale-105"
        )}
      >
        {/* Day number */}
        <span className={cn(
          "relative z-[1] font-black leading-none tracking-tight text-brand",
          isCompact ? "text-sm" : "text-base"
        )}>
          {dd}
        </span>
        {/* Month abbreviation */}
        <span className={cn(
          "relative z-[1] font-bold uppercase leading-tight text-brand/(--opacity-strong)",
          isCompact ? "text-[0.5rem]" : "text-[0.6rem]"
        )}>
          {mmLabel}
        </span>
      </span>
    </Tooltip>
  )
}
