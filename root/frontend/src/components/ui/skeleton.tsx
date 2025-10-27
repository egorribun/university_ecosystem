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
        "skeleton relative overflow-hidden bg-skeleton",
        rounded ? "rounded-ue-md" : "",
        "motion-reduce:animate-none",
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
