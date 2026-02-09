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
    low: "bg-[rgba(255,255,255,var(--glass-alpha-low))] backdrop-blur-md",
    medium: "bg-glass backdrop-blur-xl",
    high: "bg-[rgba(255,255,255,var(--glass-alpha-high))] backdrop-blur-2xl",
  }

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-ue-xl border border-glass-border shadow-glass",
        intensities[intensity],
        interactive && "transition-transform duration-300 hover:scale-[1.01] hover:bg-white/15",
        className
      )}
      {...rest}
    >
      {/* Premium Sheen Effect */}
      <div className="pointer-events-none absolute inset-0 bg-linear-to-br from-white/10 via-transparent to-transparent opacity-50" />

      <div className="relative z-10">{children}</div>
    </div>
  )
}

GlassCard.displayName = "GlassCard"




