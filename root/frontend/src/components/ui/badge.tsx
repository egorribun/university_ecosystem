import { cn } from "@/utils/cn"
import type { ComponentPropsWithoutRef, ElementType } from "react"

type BadgeVariant = "solid" | "outline"
type BadgeTone = "default" | "primary" | "success" | "danger" | "info"
type BadgeShape = "pill" | "circle"
type BadgeSize = "xs" | "sm" | "md"

const pillSizeMap: Record<BadgeSize, string> = {
  xs: "min-h-6 px-2 text-[0.7rem]",
  sm: "min-h-7 px-2.5 text-[0.78rem]",
  md: "min-h-8 px-3 text-sm",
}

const circleSizeMap: Record<BadgeSize, string> = {
  xs: "h-7 w-7 text-[0.7rem]",
  sm: "h-8 w-8 text-sm",
  md: "h-10 w-10 text-base",
}

const toneVariantStyles: Record<BadgeTone, Record<BadgeVariant, string>> = {
  default: {
    solid: "bg-surface-accent text-nav-text",
    outline: "border border-button-border text-nav-text",
  },
  primary: {
    solid: "bg-btn-gradient text-white shadow-surface",
    outline: "border border-[color:rgba(37,99,235,0.65)] text-[color:rgba(37,99,235,0.95)]",
  },
  success: {
    solid: "bg-[color:rgba(16,185,129,0.18)] text-[color:rgba(6,95,70,0.95)]",
    outline: "border border-[color:rgba(16,185,129,0.45)] text-[color:rgba(6,95,70,0.95)]",
  },
  danger: {
    solid: "bg-[color:rgba(244,63,94,0.15)] text-[color:rgba(159,18,57,0.9)]",
    outline: "border border-[color:rgba(244,63,94,0.45)] text-[color:rgba(159,18,57,0.9)]",
  },
  info: {
    solid: "bg-[color:rgba(59,130,246,0.18)] text-[color:rgba(37,99,235,0.95)]",
    outline: "border border-[color:rgba(59,130,246,0.4)] text-[color:rgba(37,99,235,0.95)]",
  },
}

type BadgeOwnProps = {
  as?: ElementType
  variant?: BadgeVariant
  tone?: BadgeTone
  shape?: BadgeShape
  size?: BadgeSize
  leadingIcon?: React.ReactNode
  trailingIcon?: React.ReactNode
  label?: React.ReactNode
  className?: string
}

export type BadgeProps<T extends ElementType = "span"> = BadgeOwnProps &
  Omit<ComponentPropsWithoutRef<T>, keyof BadgeOwnProps>

export const Badge = <T extends ElementType = "span">({
  as,
  variant = "solid",
  tone = "default",
  shape = "pill",
  size = "sm",
  leadingIcon,
  trailingIcon,
  className,
  label,
  children,
  ...rest
}: BadgeProps<T>) => {
  const Component = (as ?? "span") as ElementType
  const content = children ?? label

  return (
    <Component
      className={cn(
        "inline-flex items-center justify-center gap-1 font-semibold tracking-tight transition-colors duration-200 ease-out",
        shape === "pill" ? "rounded-ue-pill" : "rounded-full",
        shape === "pill" ? pillSizeMap[size] : circleSizeMap[size],
        shape === "circle" ? "aspect-square" : "",
        toneVariantStyles[tone][variant],
        variant === "outline" ? "bg-transparent" : "",
        className
      )}
      {...rest}
    >
      {leadingIcon ? <span className="inline-flex items-center">{leadingIcon}</span> : null}
      <span className="leading-none">{content}</span>
      {trailingIcon ? <span className="inline-flex items-center">{trailingIcon}</span> : null}
    </Component>
  )
}

Badge.displayName = "Badge"

export const Chip = Badge

