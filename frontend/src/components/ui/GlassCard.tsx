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
    low: "bg-white/5 backdrop-blur-md",
    medium: "bg-white/10 backdrop-blur-xl",
    high: "bg-white/20 backdrop-blur-2xl",
  }

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-ue-xl border border-white/10 shadow-premium",
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
