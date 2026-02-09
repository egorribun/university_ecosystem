import { cn } from "@/utils/cn"
import type { ComponentPropsWithoutRef, ElementType, ReactNode } from "react"

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
    solid: "bg-(--bg-surface-hover) text-(--text-primary)",
    outline: "border border-border-strong text-(--text-secondary)",
  },
  primary: {
    solid: "bg-brand text-inverse-text shadow-sm",
    outline: "border border-brand text-brand",
  },
  success: {
    solid: "bg-success-bg text-success-text",
    outline: "border border-success-text text-success-text",
  },
  danger: {
    solid: "bg-error-bg text-error-text",
    outline: "border border-error-text text-error-text",
  },
  info: {
    solid: "bg-brand-subtle text-brand",
    outline: "border border-brand text-brand",
  },
}

type BadgeOwnProps = {
  as?: ElementType
  variant?: BadgeVariant
  tone?: BadgeTone
  shape?: BadgeShape
  size?: BadgeSize
  leadingIcon?: ReactNode
  trailingIcon?: ReactNode
  label?: ReactNode
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





