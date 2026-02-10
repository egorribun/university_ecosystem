import type { HTMLAttributes } from "react"
import { cn } from "@/utils/cn"

type GlassCardProps = {
  intensity?: "low" | "medium" | "high"
  interactive?: boolean
  className?: string
} & HTMLAttributes<HTMLDivElement>

export function GlassCard({
  intensity = "medium",
  interactive = false,
  className,
  children,
  ...rest
}: GlassCardProps) {
  const intensities = {
    low: "bg-(--glass-bg-low) dark:bg-(--glass-bg-low-dark) backdrop-blur-md",
    medium: "bg-glass backdrop-blur-xl",
    high: "bg-(--glass-bg-high) backdrop-blur-2xl",
  }

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-2xl border border-glass-border shadow-glass",
        intensities[intensity],
        interactive && "transition-transform duration-300 hover:scale-[1.01] hover:bg-glass-tint1",
        className
      )}
      {...rest}
    >
      {/* Premium Sheen Effect */}
      <div className="pointer-events-none absolute inset-0 bg-linear-to-br from-white/10 via-transparent to-transparent opacity-50" />

      <div className="relative z-(--z-surface)">{children}</div>
    </div>
  )
}
