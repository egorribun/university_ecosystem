import {
  forwardRef,
  type ElementType,
  type ReactElement,
  type ReactNode,
  type MouseEvent,
} from "react"
import { cn } from "@/utils/cn"
import type { PolymorphicComponentProps, PolymorphicRef } from "@/types/polymorphic"
import { useHaptics } from "@/hooks/useHaptics"

type ButtonVariant = "solid" | "outline" | "ghost" | "glass" | "gradient"
type ButtonSize = "sm" | "md" | "lg"

type ButtonOwnProps = {
  variant?: ButtonVariant
  size?: ButtonSize
  fullWidth?: boolean
  loading?: boolean
  leadingIcon?: ReactNode
  trailingIcon?: ReactNode
  className?: string
  disabled?: boolean
  haptics?: boolean | "light" | "medium" | "heavy"
}

export type ButtonProps<T extends ElementType = "button"> = PolymorphicComponentProps<
  T,
  ButtonOwnProps
>

const sizeStyles: Record<ButtonSize, string> = {
  sm: "min-h-10 px-3 py-2 text-sm",
  md: "min-h-(--space-12) px-5 py-2.5 text-base",
  lg: "min-h-14 px-7 py-3 text-lg",
}

const variantStyles: Record<ButtonVariant, string> = {
  solid: cn(
    "bg-linear-brand text-inverse-text shadow-surface ring-brand/20 transition-all duration-500",
    "hover:shadow-premium-lift hover:scale-[1.02] hover:opacity-95",
    "active:scale-95",
    "motion-reduce:hover:translate-y-0 motion-reduce:hover:scale-100 motion-reduce:active:translate-y-0 motion-reduce:active:scale-100",
    "disabled:bg-(--border-subtle) disabled:text-(--text-tertiary)"
  ),
  outline: cn(
    "border border-border-subtle text-(--text-primary) shadow-surface bg-transparent",
    "hover:border-brand hover:text-brand hover:bg-brand-subtle hover:shadow-surface-strong",
    "active:scale-95",
    "motion-reduce:hover:translate-y-0 motion-reduce:active:translate-y-0",
    "disabled:border-(--border-subtle) disabled:text-(--text-tertiary)"
  ),
  ghost: cn(
    "bg-transparent text-(--text-secondary)",
    "hover:bg-(--bg-surface-hover) hover:text-(--text-primary)",
    "active:bg-(--bg-surface-hover)",
    "motion-reduce:transition-none"
  ),
  glass: cn(
    "bg-glass backdrop-blur-glass text-(--text-primary) border border-glass-border shadow-glass",
    "hover:bg-(--glass-tint1) hover:scale-[1.02]",
    "active:scale-95 transition-all duration-300"
  ),
  gradient: cn(
    "bg-linear-to-r from-blue-500 to-indigo-600 text-white hover:from-blue-600 hover:to-indigo-700 shadow-lg hover:shadow-xl border-none",
    "hover:shadow-premium-lift hover:saturate-150 hover:scale-[1.02]",
    "active:scale-95 transition-all duration-500"
  ),
}

const ButtonBase = <T extends ElementType = "button">(
  {
    as,
    variant = "solid",
    size = "md",
    fullWidth = false,
    loading = false,
    leadingIcon,
    trailingIcon,
    className,
    children,
    ...rest
  }: ButtonProps<T>,
  ref: PolymorphicRef<T>
) => {
  const {
    disabled,
    haptics = true,
    onClick,
    ...otherProps
  } = rest as typeof rest & {
    disabled?: boolean
    onClick?: (e: MouseEvent) => void
  }
  const { trigger } = useHaptics()
  const Component = (as ?? "button") as ElementType
  const isButtonElement = typeof Component === "string" && Component === "button"
  const isDisabled = Boolean(disabled || loading)

  const handleClick = (e: MouseEvent) => {
    if (isDisabled) return
    if (haptics) {
      trigger(typeof haptics === "string" ? haptics : "light")
    }
    onClick?.(e)
  }

  const sharedProps: Record<string, unknown> = {}
  if (isDisabled) {
    sharedProps["aria-disabled"] = "true"
  }

  return (
    <Component
      ref={ref}
      className={cn(
        "group/button relative inline-flex items-center justify-center gap-2 overflow-hidden rounded-xl font-bold tracking-tight text-base transition-premium focus-visible:outline-none focus-visible:shadow-focus",
        "no-underline hover:no-underline focus-visible:no-underline",
        "motion-reduce:transition-shadow motion-reduce:hover:translate-y-0 motion-reduce:active:translate-y-0",
        sizeStyles[size],
        variantStyles[variant],
        fullWidth ? "w-full" : "w-auto",
        isDisabled && "pointer-events-none opacity-60",
        className
      )}
      disabled={isButtonElement ? isDisabled : undefined}
      aria-busy={loading ? "true" : undefined}
      onClick={handleClick}
      {...sharedProps}
      {...otherProps}
    >
      {leadingIcon ? <span className="-ml-1 inline-flex items-center">{leadingIcon}</span> : null}
      <span className={cn("relative", loading && "opacity-0")}>{children}</span>
      {trailingIcon ? <span className="-mr-1 inline-flex items-center">{trailingIcon}</span> : null}
      {loading ? (
        <span
          className="pointer-events-none absolute inset-0 flex items-center justify-center"
          aria-hidden
        >
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent opacity-50" />
        </span>
      ) : null}
    </Component>
  )
}

export const Button = forwardRef(
  ButtonBase as unknown as (
    props: ButtonProps<ElementType>,
    ref: PolymorphicRef<ElementType>
  ) => ReactElement | null
) as <T extends ElementType = "button">(
  props: ButtonProps<T> & { ref?: PolymorphicRef<T> }
) => ReactElement | null
;(Button as { displayName?: string }).displayName = "Button"
