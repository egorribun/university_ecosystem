import type { HTMLAttributes } from "react"
import { cn } from "@/utils/cn"

type ProgressBarProps = {
  value?: number | null
  max?: number
  animated?: boolean
  className?: string
  barClassName?: string
  ariaLabel?: string
} & Omit<HTMLAttributes<HTMLDivElement>, "role">

export function ProgressBar({
  value = null,
  max = 100,
  animated = true,
  className,
  barClassName,
  ariaLabel,
  ...rest
}: ProgressBarProps) {
  const normalized =
    typeof value === "number" && Number.isFinite(value) ? Math.min(Math.max(value, 0), max) : null
  const percent = normalized === null ? 0 : (normalized / max) * 100

  return (
    <div
      role="progressbar"
      aria-live="polite"
      aria-valuemin={0}
      aria-valuemax={max}
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
          animated ? "transition-[width] duration-base ease-out motion-reduce:transition-none" : "",
          barClassName
        )}
        style={{ width: `${percent}%` }}
      />
    </div>
  )
}

ProgressBar.displayName = "ProgressBar"
