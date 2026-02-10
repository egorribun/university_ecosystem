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
    typeof rounded === "string" ? rounded : rounded ? "var(--radius-ue-md)" : undefined

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={ariaLabel}
      className={cn("skeleton", rounded ? "rounded-lg" : "", className)}
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
