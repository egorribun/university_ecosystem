import type { HTMLAttributes } from "react"
import { cn } from "@/utils/cn"

type SkeletonProps = {
  width?: number | string
  height?: number | string
  rounded?: boolean | string
  className?: string
  ariaLabel?: string
} & HTMLAttributes<HTMLDivElement>

export function Skeleton({
  width,
  height,
  rounded = true,
  className,
  ariaLabel,
  style,
  ...rest
}: SkeletonProps) {
  const borderRadius =
    typeof rounded === "string" ? rounded : rounded ? "var(--ue-radius-md)" : undefined

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={ariaLabel}
      className={cn(
        "skeleton relative overflow-hidden bg-[color:var(--skeleton-bg,theme(colors.white/5))] before:absolute before:inset-0 before:-translate-x-full before:animate-skeleton-shimmer before:bg-gradient-to-r before:from-transparent before:via-white/10 before:to-transparent dark:before:via-white/5",
        rounded ? "rounded-ue-md" : "",
        "motion-reduce:before:hidden",
        className
      )}
      style={{
        width,
        height,
        borderRadius,
        ...style,
      }}
      {...rest}
    />
  )
}

Skeleton.displayName = "Skeleton"
