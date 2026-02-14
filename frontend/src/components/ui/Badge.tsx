import { cn } from "@/utils/cn"
import { cva, type VariantProps } from "class-variance-authority"
import type { ComponentPropsWithoutRef, ElementType, ReactNode } from "react"

const badgeVariants = cva(
  "inline-flex items-center justify-center gap-1 font-semibold tracking-tight transition-colors duration-200 ease-out leading-none",
  {
    variants: {
      variant: {
        solid: "shadow-sm",
        outline: "bg-transparent border",
      },
      tone: {
        default: "",
        primary: "",
        success: "",
        danger: "",
        info: "",
      },
      shape: {
        pill: "rounded-full",
        circle: "rounded-full aspect-square",
      },
      size: {
        xs: "",
        sm: "",
        md: "",
      },
    },
    compoundVariants: [
      // --- Sizing ---
      // Pill shape
      { shape: "pill", size: "xs", class: "min-h-(--space-6) px-(length:--space-2) text-(length:--fs-badge)" },
      { shape: "pill", size: "sm", class: "min-h-(--space-7) px-(length:--space-2.5) text-(length:--fs-badge-sm)" },
      { shape: "pill", size: "md", class: "min-h-(--space-8) px-(length:--space-3) text-(length:--fs-sm)" },
      // Circle shape
      { shape: "circle", size: "xs", class: "h-(--space-7) w-(--space-7) text-(length:--fs-badge)" },
      { shape: "circle", size: "sm", class: "h-(--space-8) w-(--space-8) text-(length:--fs-sm)" },
      { shape: "circle", size: "md", class: "h-(--space-10) w-(--space-10) text-(length:--fs-base)" },

      // --- Tones & Variants ---
      // Default
      {
        tone: "default",
        variant: "solid",
        class: "bg-(--bg-surface-hover) text-(--text-primary) shadow-none",
      },
      {
        tone: "default",
        variant: "outline",
        class: "border-border-strong text-(--text-secondary)",
      },
      // Primary
      { tone: "primary", variant: "solid", class: "bg-brand text-inverse-text" },
      { tone: "primary", variant: "outline", class: "border-brand text-brand" },
      // Success
      { tone: "success", variant: "solid", class: "bg-success-bg text-success-text" },
      { tone: "success", variant: "outline", class: "border-success-text text-success-text" },
      // Danger
      { tone: "danger", variant: "solid", class: "bg-error-bg text-error-text" },
      { tone: "danger", variant: "outline", class: "border-error-text text-error-text" },
      // Info
      { tone: "info", variant: "solid", class: "bg-brand-subtle text-brand shadow-none" },
      { tone: "info", variant: "outline", class: "border-brand text-brand" },
    ],
    defaultVariants: {
      variant: "solid",
      tone: "default",
      shape: "pill",
      size: "sm",
    },
  }
)

type BadgeOwnProps = VariantProps<typeof badgeVariants> & {
  as?: ElementType
  leadingIcon?: ReactNode
  trailingIcon?: ReactNode
  label?: ReactNode
  className?: string
}

export type BadgeProps<T extends ElementType = "span"> = BadgeOwnProps &
  Omit<ComponentPropsWithoutRef<T>, keyof BadgeOwnProps>

export const Badge = <T extends ElementType = "span">({
  as,
  variant,
  tone,
  shape,
  size,
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
    <Component className={cn(badgeVariants({ variant, tone, shape, size }), className)} {...rest}>
      {leadingIcon ? <span className="inline-flex items-center">{leadingIcon}</span> : null}
      <span>{content}</span>
      {trailingIcon ? <span className="inline-flex items-center">{trailingIcon}</span> : null}
    </Component>
  )
}

Badge.displayName = "Badge"

export const Chip = Badge
