import type { HTMLAttributes } from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/utils/cn"

const glassCardVariants = cva(
  "relative overflow-hidden rounded-2xl border border-glass-border shadow-glass",
  {
    variants: {
      intensity: {
        low: "bg-(--glass-bg-low) dark:bg-(--glass-bg-low-dark) backdrop-blur-md",
        medium: "bg-glass backdrop-blur-xl",
        high: "bg-(--glass-bg-high) backdrop-blur-2xl",
      },
      interactive: {
        true: "transition-transform duration-300 hover:scale-[1.01] hover:bg-glass-tint1",
        false: "",
      },
    },
    defaultVariants: {
      intensity: "medium",
      interactive: false,
    },
  }
)

type GlassCardProps = VariantProps<typeof glassCardVariants> & HTMLAttributes<HTMLDivElement>

export function GlassCard({
  intensity,
  interactive,
  className,
  children,
  ...rest
}: GlassCardProps) {
  return (
    <div className={cn(glassCardVariants({ intensity, interactive }), className)} {...rest}>
      {/* Premium Sheen Effect */}
      <div className="pointer-events-none absolute inset-0 bg-linear-to-br from-white/(--opacity-subtle) via-transparent to-transparent opacity-(--opacity-medium)" />

      <div className="relative z-(--z-surface)">{children}</div>
    </div>
  )
}
