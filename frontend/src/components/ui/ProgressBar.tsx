import type { HTMLAttributes } from "react"
import { cn } from "@/utils/cn"

type ProgressBarProps = {
  value?: number | null
  max?: number
  animated?: boolean
  className?: string
  barClassName?: string
  ariaLabel?: string
  /** Wave 54: Only set aria-live on active bars to avoid screen reader flood (A11Y-54-01) */
  liveRegion?: boolean
} & Omit<HTMLAttributes<HTMLDivElement>, "role">

export function ProgressBar({
  value = null,
  max = 100,
  animated = true,
  className,
  barClassName,
  ariaLabel,
  liveRegion = false,
  ...rest
}: ProgressBarProps) {
  const safeMax = max > 0 ? max : 100
  const normalized =
    typeof value === "number" && Number.isFinite(value) ? Math.min(Math.max(value, 0), safeMax) : null
  const percent = normalized === null ? 0 : (normalized / safeMax) * 100

  return (
    <div
      role="progressbar"
      aria-live={liveRegion ? "polite" : undefined}
      aria-valuemin={0}
      aria-valuemax={safeMax}
      aria-valuenow={normalized ?? undefined}
      aria-label={ariaLabel}
      className={cn(
        "relative h-2.5 w-full overflow-hidden rounded-full bg-progress-track",
        className
      )}
      {...rest}
    >
      <div
        className={cn(
          "h-full rounded-full bg-progress-bar",
          animated ? "transition-all duration-base ease-out motion-reduce:transition-none" : "",
          barClassName
        )}
        style={{ width: `${percent}%` }}
      />
    </div>
  )
}

ProgressBar.displayName = "ProgressBar"
